"""Driving activation, roster changes with frozen ET, optional overlay isolation."""
import os
import tempfile
import unittest
from unittest.mock import patch
from remote.compute import Engine
from remote.collector import demo_frame
from remote.demo_snapshot import build
from remote.native import NativeReader
from remote.tests.test_rest_recovery import lmu_frame


class DrivingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'SPOTTER_STATE_DIR':self.directory.name})
        self.env.start()
        self.engine=Engine()

    def tearDown(self):
        if self.engine.overlays:self.engine.overlays.close()
        self.env.stop();self.directory.cleanup()

    def test_garage_to_driving_reports_cold_then_warm_calculations(self):
        frame=lmu_frame();frame['status']='garage'
        garage=self.engine.update(frame)
        self.assertFalse(garage['compute']['overlaysReady'])
        driving=self.engine.update(lmu_frame(1))
        self.assertTrue(driving['compute']['overlaysReady'])
        self.assertEqual(driving['pilot']['speedKph'],225)
        self.assertIsNone(driving['overlayError'])

    def roster_frame(self,seq,count):
        sample=demo_frame(2)
        if count==13:sample['cars'].append({**sample['cars'][-1],'id':99,'place':13})
        else:sample['cars']=sample['cars'][:count]
        frame=NativeReader.extract(build(sample));frame.pop('sourceSession')
        frame.update(type='ingest',protocolVersion=1,overlayProtocolVersion=1,
                     mode='lmu',streamId='rest-test',sessionId='session',seq=seq,capturedAt=100000+seq*50)
        return frame

    def test_roster_increase_and_decrease_refresh_modules_even_with_frozen_time(self):
        self.engine.update(lmu_frame())
        for seq,count in [(1,13),(2,4),(3,12)]:
            result=self.engine.update(self.roster_frame(seq,count))
            self.assertIsNone(result['overlayError'])
            self.assertEqual(len(result['cars']),count)
            self.assertEqual(len(result['overlays']['race']),count)
            self.assertEqual({v['id'] for v in result['cars']},{v['id'] for v in result['overlays']['race']})

    def test_optional_overlay_failure_does_not_kill_valid_positions_and_recovers(self):
        self.engine.update(lmu_frame())
        overlay=self.engine.overlays
        with patch.object(overlay,'update',side_effect=IndexError('injected slot race')):
            with self.assertLogs(level='ERROR'):
                result=self.engine.update(lmu_frame(1))
            self.assertEqual(result['type'],'presentation')
            self.assertEqual(result['pilot']['speedKph'],225)
            self.assertEqual(len(result['cars']),12)
            self.assertIsNone(result['overlays'])
            self.assertIn('IndexError',result['overlayError'])
        recovered=self.engine.update(lmu_frame(2))
        self.assertIsNotNone(recovered['overlays'])
        self.assertIsNone(recovered['overlayError'])

    def test_constructor_failure_is_degraded_not_a_worker_exit(self):
        with patch('remote.overlays.OverlayEngine',side_effect=AttributeError('injected init error')):
            with self.assertLogs(level='ERROR'):
                result=self.engine.update(lmu_frame())
            self.assertEqual(result['type'],'presentation')
            self.assertEqual(len(result['cars']),12)
            self.assertFalse(result['compute']['overlaysReady'])
        recovered=self.engine.update(lmu_frame(1))
        self.assertTrue(recovered['compute']['overlaysReady'])

    def test_delivery_gap_resets_samples_without_reimporting_upstream_modules(self):
        self.engine.update(lmu_frame())
        overlay=self.engine.overlays
        initial_resets=overlay.runtime.state.resets
        with patch('remote.overlays.OverlayEngine',side_effect=AssertionError('must reuse loaded modules')):
            result=self.engine.update(lmu_frame(10))
            self.assertIs(self.engine.overlays,overlay)
            self.assertEqual(overlay.runtime.state.resets,initial_resets+1)
            self.assertIsNone(result['overlayError'])
            self.assertIsNotNone(result['overlays'])
            self.assertEqual(result['fuel']['completedSamples'],0)


if __name__=='__main__':unittest.main()
