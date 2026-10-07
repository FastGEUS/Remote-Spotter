import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from remote.compute import Engine
from remote.iracing import IRacingReader,encode_metadata,AutoReader
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
        self.assertTrue(all(car['x'] is None for car in state['cars']))
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
        self.assertIsNone(state['fuel']['consumptionLPerLap'])
        f=frame(20.3,803);f['iracingSnapshot']['values']['CarIdxLapDistPct'][0]=-1
        f['iracingSnapshot']['values']['CarIdxTrackSurface'][0]=-1
        state=self.engine.update(f)
        self.assertFalse(next(car for car in state['cars'] if car['id']==0)['mapVisible'])
        self.assertIsNone(next(car for car in state['cars'] if car['id']==0)['relativeGap'])
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
