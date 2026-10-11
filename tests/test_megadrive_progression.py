"""Authored replay boundaries: defer unsafe snapshots, never mask divergence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.megadrive_progression_selftest import ProbeFailure, check


class ProgressionTests(unittest.TestCase):
    def exercise(self, *, failure=8, fail_all=False, diverge=False, resumed_fallback=(0, 0), gameplay_events=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'authored.exe'
            executable.write_bytes(b'authored fixture')
            calls = []

            def probe(exe, output, name, frames, script, *, reference=False, extra=()):
                calls.append((name, frames, tuple(extra)))
                if '-prefix-' in name and (fail_all or name.endswith('-0')):
                    raise ProbeFailure(name, failure, output)
                offset = int(extra[extra.index('--frame-offset') + 1]) if '--frame-offset' in extra else 0
                rows = [{'frame': str(frame + 1), 'frame_hash': str(frame),
                         'native': '0' if reference else '100',
                         'interpreted': '100' if reference else '0'}
                        for frame in range(offset, offset + frames)]
                if diverge and '-prefix-' in name:
                    rows[0]['frame_hash'] = 'mismatched saved prefix'
                data = {'frames': frames, 'cpu_hash': 'same guest',
                        'native_entries': 0 if reference else 100,
                        'retired_interpreted_opcodes': 100 if reference else 0,
                        'interpreted_opcodes': 100 if reference else 0,
                        'audio_interpreted_opcodes': 100 if reference else 0}
                if name.endswith('-restored'):
                    data['interpreted_opcodes'], data['audio_interpreted_opcodes'] = resumed_fallback
                return data, rows, 0.0

            with patch('tools.megadrive_progression_selftest.run', side_effect=probe), \
                    patch('tools.megadrive_progression_selftest.reference_differences', return_value=[]), \
                    patch('builtins.print'):
                result = check(executable, root / 'reports', 8, 3, gameplay_events=gameplay_events)
            self.assertEqual(json.loads((root / 'reports/result.json').read_text())['passed'], result['passed'])
            return result, calls

    def test_targeted_gameplay_retains_strict_reference_and_safe_state_replay(self):
        result, calls = self.exercise(gameplay_events={0: (0, 0), 2: (128, 0), 4: (8, 32), 9: (16, 64)})
        self.assertTrue(result['passed'])
        self.assertEqual([route['name'] for route in result['routes']], ['attract', 'gameplay'])
        self.assertTrue(any(name == 'gameplay-reference' for name, _, _ in calls))
        self.assertTrue(any(name == 'gameplay-restored' for name, _, _ in calls))

    def test_targeted_gameplay_rejects_invalid_controller_values(self):
        with self.assertRaisesRegex(AssertionError, 'Invalid gameplay replay'):
            self.exercise(gameplay_events={0: (0x1000, 0)})

    def test_unsafe_boundary_moves_checkpoint_and_compares_actual_remaining_frames(self):
        result, calls = self.exercise()
        self.assertTrue(result['passed'])
        for route in result['routes']:
            self.assertEqual(route['state_checkpoint_frame'], 9)
            self.assertEqual(route['state_replay_frames'], 2)
            self.assertEqual(route['checkpoint_attempts'],
                             [{'frame': 8, 'save_exit': 8}, {'frame': 9, 'save_exit': 0}])
        restored = [c for c in calls if c[0].endswith('-restored')]
        self.assertEqual([c[1] for c in restored], [2, 2])
        self.assertTrue(all(c[2][1] == 9 for c in restored))

    def test_other_exit_codes_are_not_treated_as_busy_snapshots(self):
        with self.assertRaisesRegex(ProbeFailure, 'exit 4'):
            self.exercise(failure=4)

    def test_all_unsafe_boundaries_fail_instead_of_qualifying_state_replay(self):
        with self.assertRaisesRegex(RuntimeError, 'no safe state boundary'):
            self.exercise(fail_all=True)

    def test_different_saved_prefix_is_rejected_before_restoring(self):
        with self.assertRaises(AssertionError):
            self.exercise(diverge=True)

    def test_interpreted_reload_is_not_qualified_as_native_despite_matching_guest(self):
        for counts in ((1, 0), (0, 1)):
            with self.subTest(counts=counts):
                result, _ = self.exercise(resumed_fallback=counts)
                self.assertFalse(result['passed'])
                self.assertTrue(all(not route['passed'] for route in result['routes']))
                self.assertEqual(result['routes'][0]['restored_main_fallback'], counts[0])
                self.assertEqual(result['routes'][0]['restored_sound_fallback'], counts[1])


if __name__ == '__main__':
    unittest.main()
