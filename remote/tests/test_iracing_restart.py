"""Simulator process replacement, using the real SDK over separate mappings."""
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from remote.iracing import IRacingReader
from remote.recovery import CaptureState
from remote.tests.iracing_fixture import BinaryFixture, sections, values


@unittest.skipUnless(importlib.util.find_spec('irsdk'), 'SDK is installed on capture clients')
class SimulatorRestartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'simulator.bin'
        self.now = 0.
        clock = patch('remote.iracing.time.monotonic', lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def reader(self):
        reader = IRacingReader(test_file=str(self.path))
        self.addCleanup(reader.close)
        return reader

    def race(self, replace=True):
        def race_values(t):
            return {'SessionUniqueID': 456, **values(t), 'SessionNum': 1}
        def race_sections():
            return {k: v.replace('SDK fixture circuit', 'New race circuit') for k, v in sections().items()}
        fixture = BinaryFixture(self.path.with_name('race.bin'), values_fn=race_values, sections_fn=race_sections)
        fixture.write(.125, 2)
        if replace:os.replace(fixture.path, self.path)
        return fixture

    def test_failed_startup_releases_partial_mapping_before_new_process(self):
        practice = BinaryFixture(self.path)
        struct.pack_into('<i', practice.image, 0, 0)  # Simulator still loading.
        self.path.write_bytes(practice.image)
        reader = self.reader()
        self.assertIsNone(reader.read())
        self.assertIsNone(reader.sdk._shared_mem)
        self.race()
        self.now = 1.1
        sample = reader.read()
        self.assertAlmostEqual(sample['gameTime'], .125)
        self.assertEqual(sample['iracingSnapshot']['values']['SessionUniqueID'], 456)

    def test_stale_connected_mapping_reopens_new_simulator_without_collector_restart(self):
        practice = BinaryFixture(self.path)
        practice.write(12., 100)
        reader = self.reader()
        capture = CaptureState(False, self.now)
        first = capture.update(reader.read(), self.now, reader)
        previous_session = capture.session_id
        self.assertEqual(first['gameTime'], 12.)
        self.race()  # Old view still claims connected, but belongs to exited practice.
        self.now = 2.6
        self.assertIsNone(reader.read())
        self.now = 3.7
        sample = capture.update(reader.read(), self.now, reader)
        self.assertEqual(sample['status'], 'live')
        self.assertAlmostEqual(sample['gameTime'], .125)
        self.assertNotEqual(capture.session_id, previous_session)
        self.assertEqual(sample['iracingSnapshot']['values']['SessionNum'], 1)

    def test_reused_mapping_with_new_channel_layout_is_reopened(self):
        BinaryFixture(self.path)
        reader = self.reader()
        first = reader.read()
        old_generation = first['sourceSession'][1]
        race = self.race(replace=False)
        self.path.write_bytes(race.image)  # Simulator rewrites a retained named object.
        self.now = .1
        self.assertIsNone(reader.read())
        self.now = 1.2
        sample = reader.read()
        self.assertEqual(sample['iracingSnapshot']['values']['SessionUniqueID'], 456)
        self.assertGreater(sample['sourceSession'][1], old_generation)

    def test_tick_restart_reopens_even_when_channel_layout_is_unchanged(self):
        fixture = BinaryFixture(self.path)
        fixture.write(12., 100)
        reader = self.reader()
        generation = reader.read()['sourceSession'][1]
        fixture.write(.125, 2)
        self.now = .1
        self.assertIsNone(reader.read())
        self.now = 1.2
        sample = reader.read()
        self.assertAlmostEqual(sample['gameTime'], .125)
        self.assertGreater(sample['sourceSession'][1], generation)

    def test_startup_timeout_closes_discarded_windows_event_handles(self):
        ids = iter((101, 102))
        class SDK:
            is_initialized = False
            _data_valid_event = None
            def startup(self, **kwargs):
                self._data_valid_event = next(ids)
                if not self._wait_valid_data_event():
                    self._data_valid_event = None  # Mirrors pyirsdk's timeout.
                    return False
            def unfreeze_var_buffer_latest(self):pass
            def shutdown(self):self._data_valid_event = None
        class Kernel:
            def __init__(self):self.closed = []
            def OpenFileMappingW(self, *args):return 44
            def CloseHandle(self, handle):self.closed.append(handle)
            def WaitForSingleObject(self, *args):return 258
        reader = IRacingReader(sdk=SDK(), sdk_factory=SDK)
        kernel = reader.kernel = Kernel()
        self.assertIsNone(reader.read())
        self.now = 1.1
        self.assertIsNone(reader.read())
        reader.close()
        reader.close()
        self.assertEqual(kernel.closed.count(101), 1)
        self.assertEqual(kernel.closed.count(102), 1)
        self.assertEqual(reader.event_handles, set())


if __name__ == '__main__':
    unittest.main()
