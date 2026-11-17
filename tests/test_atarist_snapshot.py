"""The Atari ST's in-process snapshot (multiplayer rollback): the parts of tools/atarist_snapshot_check.py that need no compiler, and the files' shape.

The probe itself boots authored 68000 programs on the adapted Hatari and takes about a minute once the core is built: `python -B tools/atarist_snapshot_check.py`
(BUILDING.md). The integration test below runs it only when RR_ATARIST_SNAPSHOT_RUN is set (it builds a driver); otherwise it skips."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check = load('atarist_snapshot_check')


class FilesTests(unittest.TestCase):
    def test_the_files_are_lf_and_carry_no_firmware_or_game_bytes(self):
        for name in ('tools/atarist_snapshot_check.py', 'native/atarist_machine/atarist_snapshot_checks.c', 'native/atarist_machine/atarist_snapshot.h',
                     'retrorecomp/atarist_hatari_rollback.py', 'tests/test_atarist_snapshot.py'):
            data = (ROOT / name).read_bytes()
            with self.subTest(name):
                self.assertNotIn(b'\r', data)
                self.assertLess(len(data), 120_000)

    def test_the_snapshot_code_is_outside_the_engine_identity(self):
        """A snapshot file left out of the engine's native inputs keeps the Atari ST's qualified paths valid (the session and the player are not edited)."""
        from retrorecomp import atarist_knowledge as ak
        for name in ('native/atarist_machine/atarist_snapshot.h', 'native/atarist_machine/atarist_snapshot_checks.c'):
            self.assertNotIn(name, ak.NATIVE_INPUTS)

    def test_the_replacements_name_a_file_and_are_not_empty(self):
        from retrorecomp.atarist_hatari_rollback import ROLLBACK_REPLACEMENTS
        self.assertGreater(len(ROLLBACK_REPLACEMENTS), 10)
        for rel, old, new in ROLLBACK_REPLACEMENTS:
            with self.subTest(rel + ' ' + old[:30]):
                self.assertTrue(rel.startswith('src/'))
                self.assertTrue(old)
                self.assertNotEqual(old, new)

    def test_no_debug_output_is_left_in_the_patch(self):
        text = (ROOT / 'retrorecomp' / 'atarist_hatari_rollback.py').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'fprintf\s*\(\s*stderr', text))
        self.assertNotIn('getenv', text)


class ProgramsTests(unittest.TestCase):
    def test_every_program_saves_at_several_frames_inside_its_run(self):
        for name, (image, frames, disk, events, saves, span) in check.programs().items():
            with self.subTest(name):
                self.assertGreaterEqual(len(saves), 3)
                self.assertEqual(sorted(saves), list(saves))
                self.assertLessEqual(max(saves) + span, frames + 4096)
                self.assertLess(max(saves), frames)
                self.assertTrue(image)
                self.assertEqual(disk is not None, name == 'floppy')

    def test_the_input_program_gets_joystick_events_across_its_save_frames(self):
        image, frames, disk, events, saves, span = check.programs()['ikbd']
        self.assertTrue(events)
        frames_of_events = [int(line.split()[0]) for line in events]
        self.assertTrue(any(frame <= saves[0] for frame in frames_of_events), 'a pad is held when the first state is saved')
        self.assertTrue(any(frame > saves[0] for frame in frames_of_events), 'and the replay sees it change')


@unittest.skipUnless(os.environ.get('RR_ATARIST_SNAPSHOT_RUN'), 'builds a driver and the adapted Hatari: set RR_ATARIST_SNAPSHOT_RUN=1 (python -B tools/atarist_snapshot_check.py runs it)')
class ProbeTests(unittest.TestCase):
    def test_the_probe_passes(self):
        done = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'atarist_snapshot_check.py')], capture_output=True, text=True, timeout=3000)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-500:])


if __name__ == '__main__':
    unittest.main()
