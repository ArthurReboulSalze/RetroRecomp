"""The owner's X68000 play-test preparation (gate G14): the ROM-free parts of tools/x68000_owner_trial.py."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('x68000_owner_trial', ROOT / 'tools' / 'x68000_owner_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def write_report(work: Path, report: dict) -> None:
    folder = work / 'Sharp X68000' / 'datas' / 'reports' / 'Game-0123456789ab'
    folder.mkdir(parents=True)
    (folder / 'conversion-report.json').write_text(json.dumps(report), encoding='utf-8')


class TrialTests(unittest.TestCase):
    def test_the_games_name_the_panel_games_and_a_reason_each(self):
        self.assertEqual(sorted(trial.GAMES), ['bubblebobble', 'lemmings', 'metalsight', 'rtype', 'superhangon'])
        for start, why, what in trial.GAMES.values():
            self.assertTrue(start and why and what)

    def test_the_summary_reports_the_counted_interpreter_use_and_the_packed_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            write_report(work, {'final_checks': [{'interpreted_opcodes': 0}, {'interpreted_opcodes': 3}],
                                'packing': {'packed': True}, 'native_validation': {'packed_reference_match': True},
                                'game_states': {'validation': {'continuation_matches': True}}})
            text = trial.summary(work)
        self.assertIn('3 interpreted opcodes on 2 routes', text)
        self.assertIn('compressed, replayed identically', text)
        self.assertIn('fresh process: yes', text)

    def test_an_unpacked_delivery_and_a_mismatch_are_said_plainly(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            write_report(work, {'final_checks': [], 'packing': {'packed': False, 'unpacked_reason': 'failed twice'},
                                'native_validation': {}, 'game_states': {}})
            text = trial.summary(work)
        self.assertIn('delivered unpacked (failed twice)', text)
        self.assertIn('NOT identically', text)
        self.assertIn('fresh process: no', text)

    def test_no_report_is_said(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(trial.summary(Path(folder)), 'no report found')


if __name__ == '__main__':
    unittest.main()
