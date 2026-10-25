"""Stop kills the running build or validation processes at once; the row is
reported as stopped, and the earlier export is untouched."""
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import core
from retrorecomp.batch import convert_batch, identify


class RunProcessTests(unittest.TestCase):
    def setUp(self):
        core.reset_stop()
        self.addCleanup(core.reset_stop)

    def test_stop_kills_a_running_process_and_raises_stop_requested(self):
        started = threading.Event()
        outcome = {}

        def run():
            try:
                core.run_process([sys.executable, '-c', 'import time; time.sleep(30)'], capture_output=True, timeout=60)
            except Exception as exc:  # noqa: BLE001 - the type is the assertion
                outcome['error'] = exc

        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not core._PROCESSES:
            time.sleep(0.02)
        self.assertTrue(core._PROCESSES, 'the process must be registered while it runs')
        begun = time.monotonic()
        self.assertEqual(core.stop_processes(), 1)
        worker.join(timeout=10)
        self.assertLess(time.monotonic() - begun, 5, 'Stop must not wait for the process to finish by itself')
        self.assertIsInstance(outcome.get('error'), core.StopRequested)
        self.assertFalse(core._PROCESSES)

    def test_after_stop_the_next_process_is_refused_until_reset(self):
        core.stop_processes()
        with self.assertRaises(core.StopRequested):
            core.run_process([sys.executable, '-c', 'pass'], capture_output=True)
        core.reset_stop()
        completed = core.run_process([sys.executable, '-c', 'print("ok")'], capture_output=True, text=True)
        self.assertEqual((completed.returncode, completed.stdout.strip()), (0, 'ok'))

    def test_run_process_matches_subprocess_run_for_output_and_timeout(self):
        completed = core.run_process([sys.executable, '-c', 'import sys; sys.stderr.write("e"); print("o")'],
                                     capture_output=True, text=True)
        self.assertEqual((completed.stdout.strip(), completed.stderr), ('o', 'e'))
        with self.assertRaises(subprocess.TimeoutExpired):
            core.run_process([sys.executable, '-c', 'import time; time.sleep(5)'], capture_output=True, timeout=0.2)
        self.assertFalse(core._PROCESSES)


class BatchStopTests(unittest.TestCase):
    EXT = '.exe' if os.name == 'nt' else ''

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.games = self.root / 'Games'
        core.reset_stop()
        self.addCleanup(core.reset_stop)
        packer = patch('retrorecomp.publishing.compact_executable')
        packer.start()
        self.addCleanup(packer.stop)

    def test_stopped_conversion_is_reported_and_keeps_the_earlier_export(self):
        rom = self.root / 'Same title (Europe).sms'
        rom.write_bytes(bytes([1]) * 8192)
        item = identify(rom)
        folder = self.games / 'Master System'
        folder.mkdir(parents=True)
        earlier = folder / ('Same title' + self.EXT)
        earlier.write_bytes(b'earlier export')
        stop = threading.Event()

        def compile(path, *, output, title, **options):
            stop.set()
            # What a long build step does once Stop killed its compiler.
            core.stop_processes()
            core.run_process([sys.executable, '-c', 'pass'], capture_output=True)
            raise AssertionError('must not get here')

        with patch('retrorecomp.systems.master_system.MasterSystemProfile.convert', side_effect=compile):
            record = convert_batch([item], self.games, cancel=stop, emit=lambda text: None)
        self.assertEqual(record['games'][0]['status'], 'stopped')
        self.assertEqual((record['stopped'], record['failed'], record['pending']), (1, 0, 1))
        self.assertEqual(earlier.read_bytes(), b'earlier export')


if __name__ == '__main__':
    unittest.main()
