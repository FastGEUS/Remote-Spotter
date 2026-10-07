import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from remote.collector import demo_frame
from remote.demo_snapshot import build
from remote.overlays import OverlayEngine
from remote.snapshot import encode,decode,SIZE,LAYOUT


class OverlayTests(unittest.TestCase):
    def sample(self,time=0):
        frame=demo_frame(time)
        frame.update(mode='demo',capturedAt=1000+time*1000)
        return frame

    def test_raw_snapshot_id_join_units_and_bounded_decode(self):
        frame=self.sample(2)
        data=build(frame)
        data.paths.userData=b'PRIVATE-PATH-MUST-NOT-LEAVE-PC'
        # Telemetry and scoring orders differ in real sessions.
        first=bytes(data.telemetry.telemInfo[0]);last=bytes(data.telemetry.telemInfo[7])
        data.telemetry.telemInfo[0]=type(data.telemetry.telemInfo[0]).from_buffer_copy(last)
        data.telemetry.telemInfo[7]=type(data.telemetry.telemInfo[7]).from_buffer_copy(first)
        data.telemetry.playerVehicleIdx=7
        encoded=encode(data)
        raw=zlib.decompress(base64.b64decode(encoded['data']))
        self.assertNotIn(b'PRIVATE-PATH',raw)
        decoded=decode(encoded)
        with tempfile.TemporaryDirectory() as path:
            engine=OverlayEngine(path)
            try:
                frame['mode']='lmu';frame['rawSnapshot']=encoded
                result=engine.update(frame)
                self.assertEqual(engine.reader.vehicle.place(),1)
                self.assertAlmostEqual(result['values']['api.brake.temperature']['value'][0],410)
                self.assertEqual(result['values']['module.wheels.currentTreadDepth']['value'],[96]*4)
                self.assertEqual(len(result['catalog']),76)
                self.assertFalse(result['moduleErrors'])
            finally:engine.close()
        bomb={'layout':LAYOUT,'data':base64.b64encode(zlib.compress(b'\0'*(SIZE*3))).decode()}
        with self.assertRaises(ValueError):decode(bomb)
        with self.assertRaises(ValueError):decode({**encoded,'layout':'other'})

    def test_complete_modules_finish_energy_zero_and_persistent_maps(self):
        with tempfile.TemporaryDirectory() as path:
            engine=OverlayEngine(path)
            for i in range(350):
                result=engine.update(self.sample(i*.1))
            self.assertFalse(result['moduleErrors'])
            self.assertAlmostEqual(result['modules']['fuel']['estimatedConsumption'],2.5,places=6)
            self.assertAlmostEqual(result['modules']['energy']['estimatedConsumption'],2,places=4)
            self.assertEqual(result['finish']['status'],'estimated')
            self.assertEqual(result['finish']['pitStopsFuel'],1)
            self.assertGreater(result['finish']['fuel']['neededRelative'],49.9)
            self.assertEqual(result['trackmap']['status'],'recorded')
            self.assertTrue(result['widgetMath']['relative_finish_order']['scenarios'])
            coordinates=result['trackmap']['points']
            empty=self.sample(35);empty['pilot']['strategyInputs']['virtualEnergyFraction']=0
            result=engine.update(empty)
            self.assertTrue(result['modules']['energy']['available'])
            self.assertEqual(result['modules']['energy']['amountCurrent'],0)
            self.assertEqual(result['modules']['energy']['estimatedMinutes'],0)
            engine.close()
            self.assertTrue(list(Path(path,'track_map').glob('*.svg')))
            self.assertTrue(list(Path(path,'fuel_delta').glob('*.fuel')))
            self.assertTrue(list(Path(path,'sector_best').glob('*.sector')))
            fresh=OverlayEngine(path)
            try:
                again=fresh.update(self.sample(0))
                self.assertEqual(again['trackmap']['points'],coordinates)
                next_track=self.sample(.1);next_track['session']['track']='Second synthetic track'
                # New session engine, as in the protocol reset boundary.
            finally:fresh.close()
            fresh=OverlayEngine(path)
            try:
                for i in range(340):
                    sample=self.sample(i*.1);sample['session']['track']='Second synthetic track'
                    fresh.update(sample)
            finally:fresh.close()
            self.assertEqual(len(list(Path(path,'track_map').glob('*.svg'))),2)

    def test_unavailable_rest_and_invalid_laps_do_not_create_forecasts(self):
        with tempfile.TemporaryDirectory() as path:
            engine=OverlayEngine(path)
            try:
                for i in range(350):
                    sample=self.sample(i*.1);sample['pilot']['lapValid']=False
                    result=engine.update(sample)
                self.assertEqual(result['finish']['status'],'warming-up')
                self.assertIsNone(result['pit']['totalSeconds'])
                self.assertIsNone(result['values']['api.vehicle.pit_stop_time']['value'])
                self.assertEqual(result['values']['api.vehicle.pit_stop_time']['status'],'rest-unavailable')
                json.dumps(result,allow_nan=False)
            finally:engine.close()

    def test_pit_lane_geometry_is_recorded_separately_and_restored(self):
        with tempfile.TemporaryDirectory() as path:
            engine=OverlayEngine(path)
            try:
                for i in range(10):
                    sample=self.sample(i*.1);sample['cars'][0]['inPit']=i<9
                    result=engine.update(sample)
                points=result['trackmap']['pitLanePoints']
                self.assertGreater(len(points),4)
            finally:engine.close()
            fresh=OverlayEngine(path)
            try:self.assertEqual(fresh.update(self.sample(1))['trackmap']['pitLanePoints'],points)
            finally:fresh.close()


if __name__=='__main__':unittest.main()
