"""Pure checks for the shared fresh-process state helpers."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.state_checks import (controls_before, controls_text, first_trace_mismatch,
                                final_json, guest_differences, parse_two_player_script,
                                route_controls, run_captured, run_report_trace)


class StateCheckHelperTests(unittest.TestCase):
    def test_shared_route_has_start_pulses_then_repeated_right(self):
        controls = route_controls(831)
        self.assertEqual(controls[0], (0, 0, 0))
        starts = [frame for frame, player, _ in controls
                  if player == 8 and frame in (180, 300, 480, 550, 660, 720)]
        self.assertEqual(starts, [180, 300, 480, 550, 660, 720])
        events = dict((frame, (player, player_two)) for frame, player, player_two in controls)
        self.assertEqual(events[182], (0, 0))
        self.assertEqual(events[830], (128, 0))

    def test_route_selects_console_specific_buttons(self):
        self.assertIn((800, 128, 0), route_controls(801, md=False))
        self.assertIn((800, 8, 0), route_controls(801, md=True))

    def test_script_round_trip_and_prefix(self):
        controls = route_controls(20, player_two=7)
        text = controls_text(controls)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'inputs.txt'
            source.write_text(text + '\n900 1 2\n', encoding='ascii')
            self.assertEqual(parse_two_player_script(source, 20), controls)
        self.assertEqual(controls_before(controls, 10), [event for event in controls if event[0] < 10])

    def test_script_validation_rejects_bad_bounds_and_order(self):
        cases = (
            '0 1 2\n0 1 2\n',
            '1 1 2\n',
            '-1 1 2\n',
            '0 65536 2\n',
            '0 1 2 3\n',
        )
        for text in cases:
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as folder:
                    source = Path(folder) / 'inputs.txt'
                    source.write_text(text, encoding='ascii')
                    with self.assertRaises(ValueError):
                        parse_two_player_script(source, 10)

    def test_trace_and_guest_differences(self):
        previous = ({'video': 'a', 'native': 3}, {'video': 'b', 'native': 4})
        future = ({'video': 'a', 'native': 9}, {'video': 'c', 'native': 9})
        self.assertEqual(first_trace_mismatch(previous, future), 1)
        self.assertEqual(first_trace_mismatch([], []), None)
        self.assertEqual(guest_differences({'cpu_hash': 1, 'ram_hash': 2},
                                           {'cpu_hash': 1, 'ram_hash': 3}), ['ram_hash'])

    def test_report_trace_runner_reads_both_outputs(self):
        calls = []

        def fake_run(command, capture_output, text, timeout):
            calls.append((command, timeout))
            output = Path(command[command.index('--report') + 1])
            trace = Path(command[command.index('--trace') + 1])
            output.write_text(json.dumps({'cpu_hash': 'same'}), encoding='utf-8')
            trace.write_text('video,cpu\n1,2\n', encoding='ascii')
            return type('Result', (), {'returncode': 0, 'stderr': ''})()

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with patch('tools.state_checks.subprocess.run', side_effect=fake_run):
                report, rows = run_report_trace('game.exe', output, 'baseline', 12, '--play')
            self.assertEqual(report, {'cpu_hash': 'same'})
            self.assertEqual(rows, [{'video': '1', 'cpu': '2'}])
            command, timeout = calls[0]
            self.assertEqual(command[:4], ['game.exe', '--frames', '12', '--report'])
            self.assertEqual(command[-1], '--play')
            self.assertEqual(timeout, 300)

    def test_captured_child_and_final_status_json(self):
        calls = []

        def fake_run(command, cwd, capture_output, text, timeout, creationflags):
            calls.append(([str(item) for item in command], cwd, timeout, creationflags))
            return type('Result', (), {'returncode': 0, 'stdout': 'noise\n{"passed":true}\n',
                                       'stderr': ''})()

        with patch('tools.state_checks.subprocess.run', side_effect=fake_run):
            result = run_captured(('check.exe', 2), cwd=Path('work'), timeout=33)
        self.assertEqual(final_json('noise\n{"passed":true}\n'), {'passed': True})
        self.assertEqual(calls[0][0], ['check.exe', '2'])
        self.assertEqual((calls[0][1], calls[0][2]), (Path('work'), 33))


if __name__ == '__main__':
    unittest.main()
