import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from remote.compute import Engine
from remote.iracing import IRacingReader,encode_metadata,AutoReader,split_metadata
from remote.iracing_compute import IRacingEngine,decode_metadata,TrackMap
from remote.tests.iracing_fixture import frame,BinaryFixture,sections


class IRacingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.engine=IRacingEngine(self.temp.name)
    def test_real_slots_classes_units_and_missing_channels(self):
        state=self.engine.update(frame())
        self.assertEqual(state['pilot']['id'],2)
        self.assertEqual(state['pilot']['gear'],5)
        self.assertAlmostEqual(state['pilot']['speedKph'],20*math.pi*3.6)
        self.assertEqual(state['cars'][1]['number'],'007')
        self.assertEqual(state['cars'][1]['classPlace'],1)
        self.assertIsNone(state['pilot']['wheels'][0]['wear'])
        self.assertIsNone(state['pilot']['wheels'][0]['brakeC'])
        self.assertIsNone(state['pilot']['lapValid'])
        self.assertEqual(state['overlays']['capabilities']['radar']['status'],'unsupported')
        self.assertEqual(len(state['overlays']['catalog']),76)
        self.assertTrue(next(car for car in state['cars'] if car['id']==2)['mapVisible'])
        self.assertFalse(next(car for car in state['cars'] if car['id']==0)['mapVisible'])
        json.dumps(state,allow_nan=False)
    def test_flags_bitfields_penalties_and_no_sector_invention(self):
        for bits,expected in [(4,'green'),(8,'yellow'),(0x4000,'caution'),(0x10,'stopped'),(1,'finished'),(2,'white'),(0x10000,'black'),(0x100000,'repair'),(0x40000000,'starting'),(0x80000000,'green')]:
            f=frame();f['iracingSnapshot']['values']['SessionFlags']=bits
            state=IRacingEngine(self.temp.name).update(f)
            self.assertEqual(state['overlays']['flags']['session'],expected)
            self.assertEqual(state['overlays']['flags']['sectorFlags'],['unknown']*3)
        f=frame();f['iracingSnapshot']['values']['CarIdxSessionFlags'][2]=0x20
        self.assertTrue(self.engine.update(f)['overlays']['flags']['pilotBlue'])
    def test_complete_lap_fuel_sector_boundaries_and_persistent_map(self):
        for i in range(1301):state=self.engine.update(frame(i*.025,i))
        self.assertAlmostEqual(state['fuel']['consumptionLPerLap'],2,places=4)
        self.assertEqual(state['trackmap']['status'],'recorded')
        self.assertTrue(state['trackmap']['approximate'])
        self.assertTrue(all(car['mapVisible'] for car in state['cars']))
        times=state['overlays']['sectorTiming']['last']
        for actual,expected in zip(times,[2,5,3]):self.assertAlmostEqual(actual,expected,places=2)
        self.assertTrue(state['overlays']['sectorTiming']['history'])
        loaded=IRacingEngine(self.temp.name).update(frame())
        self.assertEqual(loaded['trackmap']['status'],'recorded')
        self.assertEqual(loaded['trackmap']['sectorGeometry'],state['trackmap']['sectorGeometry'])
        self.assertTrue(0<state['trackmap']['sectorGeometry']['indices'][0]<state['trackmap']['sectorGeometry']['indices'][1])
    def test_sequence_gap_reset_and_unavailable_roster_positions(self):
        for i in range(801):self.engine.update(frame(i*.025,i))
        state=self.engine.update(frame(20.2,802))
        self.assertAlmostEqual(state['fuel']['consumptionLPerLap'],2)
        f=frame(20.3,803);f['iracingSnapshot']['values']['CarIdxLapDistPct'][0]=-1
        f['iracingSnapshot']['values']['CarIdxTrackSurface'][0]=-1
        state=self.engine.update(f)
        self.assertFalse(next(car for car in state['cars'] if car['id']==0)['mapVisible'])
        self.assertIsNone(next(car for car in state['cars'] if car['id']==0)['relativeGap'])
        state=self.engine.update(frame(22,804))
        self.assertIsNone(state['fuel']['consumptionLPerLap'])

    def test_iracing_clutch_is_pedal_travel_in_every_output(self):
        for i,value in enumerate((0.,.25,1.)):
            f=frame(i*.05,i);f['iracingSnapshot']['values']['Clutch']=value
            f['iracingSnapshot']['values']['ClutchRaw']=value
            state=self.engine.update(f)
            self.assertEqual(state['pilot']['clutch'],1-value)
            self.assertEqual(state['overlays']['values']['api.inputs.clutch']['value'],1-value)
            self.assertEqual(state['overlays']['values']['api.inputs.clutch_raw']['value'],1-value)
            self.assertEqual(state['overlays']['widgetMath']['trailing']['samples'][-1][3],1-value)

    def test_unknown_lap_and_player_channels_use_roster_and_scoring(self):
        f=frame(.05,1);v=f['iracingSnapshot']['values'];v['Lap']=-1;v['PlayerCarIdx']=-1
        v['LapDistPct']=.005;v['CarIdxLapDistPct'][2]=-1;v['TrackTemp']=28;v.pop('TrackTempCrew')
        v['SessionLapsRemainEx']=52;v['SessionLapsRemain']=32767;v['SessionUniqueID']=3_000_000_000
        for wheel in ('LF','RF','LR','RR'):v[wheel+'coldPressure']=165
        state=self.engine.update(f)
        self.assertEqual(state['pilot']['id'],2)
        self.assertEqual(state['pilot']['lap'],1)
        self.assertEqual(state['pilot']['wheels'][0]['pressureKpa'],165)
        self.assertIn('cold pressure',state['pilot']['wheels'][0]['pressureSource'])
        self.assertEqual(state['overlays']['values']['api.session.track_temperature']['value'],28)
        self.assertEqual(state['overlays']['values']['api.lap.remaining']['value'],52)
        self.assertEqual(state['cars'][1]['lapProgress'],.005)

    def test_map_records_with_duplicates_skipped_sequences_and_incidents(self):
        seq=0
        for i in range(801):
            t=i*.025
            if i in (400,650):continue
            seq+=2 if i%10==0 else 1
            f=frame(t,seq);f['iracingSnapshot']['values']['PlayerCarMyIncidentCount']=1 if i>=450 else 0
            f['iracingSnapshot']['values']['YawNorth']=f['iracingSnapshot']['values'].pop('Yaw')
            state=self.engine.update(f)
            if i%8==0:
                seq+=1;duplicate=copy.deepcopy(f);duplicate['seq']=seq;self.engine.update(duplicate)
        self.assertEqual(state['trackmap']['status'],'recorded')
        self.assertGreater(state['trackmap']['coveragePct'],99)
        self.assertTrue(all(car['mapVisible'] for car in state['cars']))

    def test_partial_map_is_visible_before_crossing_start_line(self):
        for i in range(60):state=self.engine.update(frame(3+i*.05,i))
        self.assertEqual(state['trackmap']['status'],'recording')
        self.assertGreater(len(state['trackmap']['points']),50)
        self.assertGreater(state['trackmap']['coveragePct'],25)
        self.assertTrue(next(car for car in state['cars'] if car['id']==2)['mapVisible'])

    def test_gps_map_without_heading_and_practice_gap_semantics(self):
        for i in range(401):
            t=i*.05;f=frame(t,i);v=f['iracingSnapshot']['values'];a=t/10*math.tau
            v.pop('Yaw');v['Lat']=52+100*math.sin(a)/111320
            v['Lon']=13+100*math.cos(a)/(111320*math.cos(math.radians(52)))
            state=self.engine.update(f)
        self.assertEqual(state['trackmap']['status'],'recorded')
        self.assertIn('Lat/Lon',state['trackmap']['source'])
        f=frame(20.1,402);source=sections();source['SessionInfo']=source['SessionInfo'].replace('Race','Practice')
        f['iracingSnapshot']['sessionData']=encode_metadata(source)
        self.assertTrue(all(car['gapBehindLeader'] is None for car in self.engine.update(f)['cars']))

    def test_raw_session_sections_do_not_require_blank_lines(self):
        raw=('---\n'+''.join(sections().values())+'CarSetup:\n Foo: 0\n\x00').encode()
        selected=split_metadata(raw,'utf-8')
        metadata=decode_metadata(encode_metadata(selected))
        self.assertEqual(metadata['DriverInfo']['Drivers'][1]['CarNumber'],'007')
        self.assertNotIn('CarSetup',selected)

    def test_capture_pause_keeps_visible_partial_map_and_short_gap_continues(self):
        for i in range(20):state=self.engine.update(frame(i*.05,i))
        points=state['trackmap']['points'];paused=frame(.95,20)
        paused['status']='waitingForGame';paused.pop('iracingSnapshot')
        self.assertEqual(self.engine.update(paused)['trackmap']['points'],points)
        resumed=self.engine.update(frame(1.55,21))
        self.assertGreater(len(resumed['trackmap']['points']),len(points))

    def test_constant_gps_is_not_saved_as_a_complete_map(self):
        for i in range(401):
            f=frame(i*.05,i);f['iracingSnapshot']['values'].update(Lat=52.,Lon=13.)
            state=self.engine.update(f)
        self.assertEqual(state['trackmap']['status'],'recording')
        self.assertFalse(list(Path(self.temp.name).rglob('track-*.json')))

    def test_invalid_optional_sensor_does_not_consume_sequence(self):
        self.engine.update(frame());bad=frame(.05,1);bad['iracingSnapshot']['values']['LFwearL']=1.5
        with self.assertRaises(ValueError):self.engine.update(bad)
        self.assertEqual(self.engine.update(frame(.05,1))['seq'],1)
    def test_session_unique_id_accepts_signed_sdk_int32(self):
        f=frame();f['iracingSnapshot']['values']['SessionUniqueID']=-2_000_000_000
        self.assertEqual(self.engine.update(f)['pilot']['id'],2)
    def test_validation_does_not_poison_good_sequence(self):
        self.engine.update(frame())
        for key,value in [('FuelLevel',float('nan')),('PlayerCarIdx',-2),('PlayerCarIdx',2.5),('Throttle',1.1),('CarIdxLapDistPct',.5)]:
            bad=frame(.05,1);bad['iracingSnapshot']['values'][key]=value
            with self.assertRaises(ValueError):self.engine.update(bad)
        self.assertEqual(self.engine.update(frame(.05,1))['seq'],1)
        with self.assertRaises(ValueError):self.engine.update(frame(.05,1))
    def test_tyres_are_pit_carcass_samples_not_live_surface_channels(self):
        f=frame()
        for prefix in ('LF','RF','LR','RR'):
            f['iracingSnapshot']['values'].update({prefix+'pressure':180.,prefix+'tempCL':80.,prefix+'tempCM':85.,
                prefix+'tempCR':90.,prefix+'wearL':.9,prefix+'wearM':.8,prefix+'wearR':.85})
        state=self.engine.update(f);wheel=state['pilot']['wheels'][0]
        self.assertAlmostEqual(wheel['wear'],.85);self.assertEqual(wheel['temperatureC'],85)
        self.assertEqual(wheel['status'],'pit-snapshot')
        self.assertEqual(wheel['carcassTemperaturesC'],[80,85,90])
        api=state['overlays']['values']
        self.assertEqual(api['api.tyre.carcass_temperature_ico']['value'],[90,85,80,80,85,90,90,85,80,80,85,90])
        self.assertNotIn('api.tyre.surface_temperature_ico',api)
        self.assertEqual(api['api.tyre.pressure']['value'],[180]*4)
        self.assertEqual(api['module.wheels.currentTreadDepth']['value'],[85]*4)
        self.assertEqual(api['module.fuel.amountCurrent']['value'],100)
        self.assertEqual(api['api.engine.gear']['value'],5)
    def test_bad_metadata_cannot_consume_sequence(self):
        self.engine.update(frame());bad=frame(.05,1);source=sections()
        source['WeekendInfo']='WeekendInfo:\n TrackLength: 999999 km\n'
        bad['iracingSnapshot']['sessionData']=encode_metadata(source)
        with self.assertRaises(ValueError):self.engine.update(bad)
        self.assertEqual(self.engine.update(frame(.05,1))['seq'],1)
    def test_garage_tyres_survive_missing_channels_and_reset_with_session(self):
        f=frame();f['status']='garage';v=f['iracingSnapshot']['values']
        v['IsOnTrack']=False;v['IsOnTrackCar']=False
        for prefix in ('LF','RF','LR','RR'):
            v.update({prefix+'tempCL':80.,prefix+'tempCM':85.,prefix+'tempCR':90.})
        state=self.engine.update(f)
        self.assertIsNone(state['pilot'])
        self.assertEqual(state['tyres'][0]['temperatureC'],85)
        self.assertEqual(state['overlays']['values']['api.tyre.carcass_temperature']['value'],[85]*4)
        state=self.engine.update(frame(.05,1))
        self.assertEqual(state['pilot']['wheels'][0]['temperatureC'],85)
        self.assertTrue(state['tyres'][0]['temperatureCached'])
        f=frame(.1,2);f['sessionId']='another-session';state=self.engine.update(f)
        self.assertIsNone(state['tyres'][0]['temperatureC'])
        self.assertEqual(state['overlays']['values']['api.tyre.carcass_temperature']['status'],'unavailable')
    def test_safe_metadata_and_leading_zero_numbers(self):
        metadata=decode_metadata(encode_metadata(sections()))
        self.assertEqual(metadata['DriverInfo']['Drivers'][1]['CarNumber'],'007')
        for source in ['DriverInfo: !!python/object/apply:os.system ["echo nope"]','DriverInfo: &a {Drivers: [*a]}']:
            with self.assertRaises(ValueError):decode_metadata(encode_metadata({'DriverInfo':source}))
    def test_non_three_sector_tracks_do_not_receive_fake_thirds(self):
        f=frame();source=sections();source['SplitTimeInfo']='SplitTimeInfo:\n Sectors: []\n'
        f['iracingSnapshot']['sessionData']=encode_metadata(source)
        state=self.engine.update(f)
        self.assertIsNone(state['overlays']['sectorTiming'])
        self.assertIsNone(state['trackmap']['sectorGeometry'])
    def test_replay_does_not_accumulate_fuel_or_map(self):
        f=frame();f['status']='paused';f['iracingSnapshot']['values']['IsReplayPlaying']=True
        state=self.engine.update(f)
        self.assertIsNone(state['pilot']);self.assertEqual(state['trackmap']['points'],[])
    @unittest.skipUnless(importlib.util.find_spec('irsdk'),'SDK is only installed on capture clients')
    def test_actual_sdk_reads_binary_fixture_consistently_and_reopens(self):
        fixture=BinaryFixture(Path(self.temp.name)/'sdk.bin')
        reader=IRacingReader(test_file=str(fixture.path));self.addCleanup(reader.close)
        sample=reader.read();self.assertEqual(sample['iracingSnapshot']['values']['PlayerCarIdx'],2)
        self.assertEqual(sample['status'],'live')
        f=frame();f['iracingSnapshot']=sample['iracingSnapshot'];self.assertEqual(self.engine.update(f)['pilot']['id'],2)
        fixture.write(3.125,2);sample=reader.read()
        self.assertEqual(sample['gameTime'],3.125)
        import struct
        struct.pack_into('<i',fixture.image,56,1)
        fixture.path.write_bytes(fixture.image)
        self.assertIsNone(reader.read())  # In-progress SDK buffer is never sent.
        fixture.write(3.15,3)
        self.assertAlmostEqual(reader.read()['gameTime'],3.15)
        reader.close();reader.next_open=0
        self.assertIsNotNone(reader.read())
    def test_auto_game_choice_does_not_switch_on_one_missing_tick(self):
        class Reader:
            def __init__(self,game,items):self.game=game;self.items=iter(items)
            def read(self):return next(self.items,None)
            def close(self):pass
        auto=AutoReader([Reader('iracing',[{'gameTime':0},None]),Reader('lmu',[{'gameTime':1}])])
        self.assertEqual(auto.read()['sourceMode'],'iracing')
        self.assertIsNone(auto.read());auto.close()
        self.assertEqual(auto.read()['sourceMode'],'lmu')
