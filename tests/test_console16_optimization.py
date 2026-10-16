"""An incomplete profiling pass must never become an exported game."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from smsrecomp.core import ConversionError
from smsrecomp.console16_optimization import build_game


class HardwareOptimizationTests(unittest.TestCase):
    def exercise(self, *, available=True, frames=600, counters=True, fail_use=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        project = Path(temporary.name)
        built = project / 'build/game'
        cache = project / 'build/CMakeCache.txt'
        built.parent.mkdir()
        modes = []
        profile = None

        def command(args, **kwargs):
            nonlocal profile
            args = list(map(str, args))
            if '-S' in args:
                mode = next(a.split('=', 1)[1] for a in args if a.startswith('-DRR16_PROFILE_MODE='))
                profile = Path(next(a.split('=', 1)[1] for a in args if a.startswith('-DRR16_PROFILE_DIR=')))
                modes.append(mode)
                cache.write_text(f'RR16_PGO_AVAILABLE:INTERNAL={"TRUE" if available else "FALSE"}\n'
                                 f'RR16_PROFILE_MODE:STRING={mode}\n')
            elif '--build' in args:
                if modes[-1] == 'use' and fail_use:
                    raise ConversionError('authored optimization failure')
                built.write_bytes(b'instrumented' if available and modes[-1] == 'generate' else b'final')
            else:
                self.assertEqual(Path(args[0]).parent, profile / 'training')
                self.assertEqual(kwargs['cwd'], profile / 'training')
                Path(args[args.index('--report') + 1]).write_text(json.dumps({'frames': frames}))
                if counters:
                    (profile / 'authored.gcda').write_bytes(b'private compiler counters')
            return ''

        def invoke():
            with patch('smsrecomp.console16_optimization.run', side_effect=command), \
                 patch('smsrecomp.console16_optimization.build_executable', return_value=built):
                build_game(project, Path('cmake'), 'Ninja', project / 'sdl', lambda _: None)

        return project, built, modes, invoke

    def test_completed_profile_rebuilds_final_and_removes_private_counters(self):
        project, built, modes, invoke = self.exercise()
        invoke()
        self.assertEqual(modes, ['generate', 'use'])
        self.assertEqual(built.read_bytes(), b'final')
        self.assertFalse(list(project.glob('hardware-profile-*')))
        self.assertTrue(json.loads((project / 'hardware-optimization.json').read_text())['profile_guided'])

    def test_incomplete_run_or_absent_counters_cannot_succeed(self):
        for kwargs in ({'frames': 599}, {'counters': False}):
            with self.subTest(kwargs=kwargs):
                project, _, modes, invoke = self.exercise(**kwargs)
                with self.assertRaises(ConversionError):
                    invoke()
                self.assertEqual(modes, ['generate'])
                self.assertFalse((project / 'hardware-optimization.json').exists())
                self.assertFalse(list(project.glob('hardware-profile-*')))

    def test_failed_optimized_build_cannot_succeed(self):
        project, _, _, invoke = self.exercise(fail_use=True)
        with self.assertRaises(ConversionError):
            invoke()
        self.assertFalse((project / 'hardware-optimization.json').exists())

    def test_unsupported_compiler_keeps_ordinary_build(self):
        project, built, modes, invoke = self.exercise(available=False)
        invoke()
        self.assertEqual(modes, ['generate'])
        self.assertEqual(built.read_bytes(), b'final')
        self.assertFalse(json.loads((project / 'hardware-optimization.json').read_text())['profile_guided'])


if __name__ == '__main__':
    unittest.main()
