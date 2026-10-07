"""Regression for the live LMU garage REST crash reported on 2026-10-03."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remote.collector import demo_frame
from remote.compute import Engine
from remote.demo_snapshot import build
from remote.native import NativeReader


GARAGE = '/rest/garage/getPlayerGarageData'
GARAGE_DATA = json.loads((Path(__file__).parent/'fixtures/garage_setup.json').read_text())


def lmu_frame(seq=0):
    frame = NativeReader.extract(build(demo_frame(2+seq*.05)))
    frame.pop('sourceSession')
    frame.update(type='ingest', protocolVersion=1, overlayProtocolVersion=1,
                 mode='lmu', streamId='rest-test', sessionId='session', seq=seq,
                 capturedAt=100000+seq*50)
    frame['rest'] = {GARAGE: {'ok': True, 'capturedAt': frame['capturedAt'],
                             'data': copy.deepcopy(GARAGE_DATA)}}
    return frame


class RestRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'SPOTTER_STATE_DIR': self.directory.name})
        self.env.start()
        self.engine = Engine()

    def tearDown(self):
        if self.engine.overlays:
            self.engine.overlays.close()
        self.env.stop()
        self.directory.cleanup()

    def test_first_native_frame_with_garage_rest_binds_reader_before_setup_parser(self):
        result = self.engine.update(lmu_frame())
        reader = self.engine.overlays.reader
        self.assertEqual(result['type'], 'presentation')
        self.assertEqual(result['pilot']['speedKph'], 225)
        self.assertIn('lastCarSetup', reader.rest_available)
        self.assertIn('VehicleClassSetting="Hypercar"', reader.rest.lastCarSetup)
        self.assertIn('FuelSetting=102', reader.rest.lastCarSetup)
        self.assertEqual(reader.rest.steeringWheelRange, 404)

    def test_failing_optional_parser_resets_only_that_field_and_recovers_next_frame(self):
        self.engine.update(lmu_frame())
        reader = self.engine.overlays.reader
        saved = reader.tasks
        def fail(*args):
            raise AttributeError('injected optional parser failure')
        reader.tasks = tuple(task._replace(outputs=tuple(
            output._replace(parser=fail) if output.name == 'lastCarSetup' else output
            for output in task.outputs)) for task in saved)
        with self.assertLogs('remote.reader', level='WARNING') as logs:
            result = self.engine.update(lmu_frame(1))
            self.engine.update(lmu_frame(2))
        self.assertEqual(len(logs.output), 1, 'Repeated bad REST data must not flood logs')
        self.assertEqual(result['seq'], 1)
        self.assertEqual(result['pilot']['speedKph'], 225)
        self.assertEqual(reader.rest.lastCarSetup, ())
        self.assertNotIn('lastCarSetup', reader.rest_available)
        self.assertIn('steeringWheelRange', reader.rest_available)
        self.assertEqual(result['overlays']['restErrors'], {'lastCarSetup': 'AttributeError'})
        reader.tasks = saved
        recovered = self.engine.update(lmu_frame(3))
        self.assertEqual(recovered['overlays']['restErrors'], {})
        self.assertIn('lastCarSetup', reader.rest_available)

    def test_malformed_pit_value_does_not_destroy_telemetry_or_car_setup(self):
        frame = lmu_frame()
        frame['rest']['/rest/garage/UIScreen/RepairAndRefuel'] = {
            'ok': True, 'capturedAt': frame['capturedAt'],
            'data': {'pitMenu': {'pitMenu': [{'name': 'FUEL:'}]},
                     'fuelInfo': {'maxVirtualEnergy': 100}}}
        with self.assertLogs('remote.reader', level='WARNING'):
            result = self.engine.update(frame)
        self.assertEqual(result['pilot']['speedKph'], 225)
        self.assertIn('lastCarSetup', result['overlays']['restAvailable'])
        self.assertNotIn('absoluteRefill', result['overlays']['restAvailable'])
        self.assertIn('maxVirtualEnergy', result['overlays']['restAvailable'])
        self.assertEqual(self.engine.overlays.reader.rest.absoluteRefill, 0)
        self.assertIn('absoluteRefill', result['overlays']['restErrors'])
        self.assertEqual(self.engine.update(lmu_frame(1))['overlays']['restErrors'], {})

    def test_missing_stale_and_malformed_rest_records_are_unavailable(self):
        for rest in (None, [], {GARAGE: None}, {GARAGE: []},
                     {GARAGE: {'ok': True, 'capturedAt': 'bad', 'data': GARAGE_DATA}},
                     {GARAGE: {'ok': True, 'capturedAt': True, 'data': GARAGE_DATA}},
                     {GARAGE: {'ok': True, 'capturedAt': 10**400, 'data': GARAGE_DATA}},
                     {GARAGE: {'ok': True, 'capturedAt': float('nan'), 'data': GARAGE_DATA}},
                     {GARAGE: {'ok': True, 'capturedAt': 1, 'data': GARAGE_DATA}}):
            with self.subTest(rest=rest):
                seq = self.engine.seq+1
                frame = lmu_frame(seq)
                frame['rest'] = rest
                result = self.engine.update(frame)
                self.assertEqual(result['seq'], seq)
                self.assertEqual(result['overlays']['restAvailable'], [])


if __name__ == '__main__':
    unittest.main()
