"""The Stage 0 baseline photograph is stable and covers every console."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'tools' / 'std_baseline.py'
CONSOLES = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1')


class StdBaselineTests(unittest.TestCase):
    @staticmethod
    def run_baseline():
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'baseline.json'
            subprocess.run([sys.executable, '-B', str(SCRIPT), str(output)],
                           cwd=REPO, check=True, capture_output=True, text=True)
            return output.read_text(encoding='utf-8')

    def test_twice_identical_and_all_consoles_present(self):
        first = self.run_baseline()
        second = self.run_baseline()
        self.assertEqual(first, second)
        document = json.loads(first)
        from retrorecomp.systems import system_ids
        self.assertEqual(sorted(document['consoles']), sorted(system_ids()))  # every registered machine
        for system in document['consoles']:
            with self.subTest(system=system):
                entry = document['consoles'][system]
                self.assertEqual(len(entry['role_stamps']), 3)
                self.assertEqual(len(entry['engine_stamp']), 64)
                self.assertEqual(len(entry['request_parts']), 3)
                for item in entry['request_parts'].values():
                    self.assertEqual(len(item), 3)
        # The slow knowledge snapshot stays opt-in and absent by default.
        self.assertIsNone(document['snapshot_sha256'])
        self.assertTrue(document['owners'])


if __name__ == '__main__':
    unittest.main()
