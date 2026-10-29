"""An incomplete profiling pass must never become an exported game."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.core import ConversionError
from retrorecomp.console16_optimization import build_game


class HardwareOptimizationTests(unittest.TestCase):
    def exercise(self, *, available=True, frames=600, counters=True, fail_use=False, clang=False, merged=True):
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
            if clang and Path(args[0]).name == 'llvm-profdata.exe':
                self.assertEqual(args[1], 'merge')
                output = Path(next(a.split('=', 1)[1] for a in args if a.startswith('-output=')))
                self.assertEqual(output, project / 'hardware-profile.profdata')   # outside the temporary folder
                self.assertTrue(all(a.endswith('.profraw') for a in args[3:]) and len(args) > 3)
                if merged:
                    output.write_bytes(b'merged profile')
                return ''
            if '-S' in args:
                mode = next(a.split('=', 1)[1] for a in args if a.startswith('-DRR16_PROFILE_MODE='))
                profile = Path(next(a.split('=', 1)[1] for a in args if a.startswith('-DRR16_PROFILE_DIR=')))
                modes.append(mode)
                self.assertEqual('-DRR16_CLANG_PGO=ON' in args, clang and mode != '')   # the fallback build is ordinary
                self.assertIn(f'-DRR16_PROFILE_DATA={(project / "hardware-profile.profdata").as_posix()}', args)
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
                    (profile / ('rr-1.profraw' if clang else 'authored.gcda')).write_bytes(b'private compiler counters')
            return ''

        def invoke():
            with patch('retrorecomp.console16_optimization.run', side_effect=command), \
                 patch('retrorecomp.console16_optimization.build_executable', return_value=built), \
                 patch('retrorecomp.console16_optimization.clang_profile',
                       return_value=Path('tools/llvm-profdata.exe') if clang else None):
                build_game(project, Path('cmake'), 'Ninja', project / 'sdl', lambda _: None, 'snes' if clang else None)

        invoke.command = command
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

    def test_clang_profile_is_merged_into_the_project_and_trained_longer(self):
        project, built, modes, invoke = self.exercise(clang=True, frames=1800)
        invoke()
        self.assertEqual(modes, ['generate', 'use'])
        self.assertEqual(built.read_bytes(), b'final')
        self.assertTrue((project / 'hardware-profile.profdata').is_file())
        self.assertFalse(list(project.glob('hardware-profile-*')))
        record = json.loads((project / 'hardware-optimization.json').read_text())
        self.assertEqual((record['profile_guided'], record['training_frames'], record['compiler_profile']),
                         (True, 1800, 'clang-thinlto'))

    def test_clang_run_without_counters_or_profile_builds_without_one(self):
        """A failed training run never exports the instrumented program; the Windows build then
        goes on without a profile (the validation that follows judges the game as before)."""
        for kwargs in ({'frames': 600}, {'counters': False}, {'merged': False}):
            with self.subTest(kwargs=kwargs):
                project, built, modes, invoke = self.exercise(clang=True, **{'frames': 1800, **kwargs})
                messages = []
                with patch('retrorecomp.console16_optimization.run', side_effect=invoke.command),                      patch('retrorecomp.console16_optimization.build_executable', return_value=built),                      patch('retrorecomp.console16_optimization.clang_profile', return_value=Path('tools/llvm-profdata.exe')):
                    build_game(project, Path('cmake'), 'Ninja', project / 'sdl', messages.append, 'snes')
                self.assertEqual(modes, ['generate', ''])
                self.assertEqual(built.read_bytes(), b'final')
                self.assertFalse((project / 'hardware-profile.profdata').exists())
                self.assertTrue(any('ordinary build' in message for message in messages))
                record = json.loads((project / 'hardware-optimization.json').read_text())
                self.assertEqual((record['profile_guided'], record['training_frames']), (False, 0))
                self.assertNotIn('compiler_profile', record)

    def test_clang_profile_only_for_snes_and_md_on_the_portable_toolchain(self):
        from retrorecomp import console16_optimization as module
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / 'llvm-mingw/bin').mkdir(parents=True)
        (folder / 'llvm-mingw/bin/llvm-profdata.exe').write_bytes(b'x')
        with patch.object(module.os, 'name', 'nt'), patch('retrorecomp.toolchain.active', return_value='llvm'), \
                patch('retrorecomp.toolchain.tools_directory', return_value=folder):
            self.assertEqual(module.clang_profile('snes'), folder / 'llvm-mingw/bin/llvm-profdata.exe')
            self.assertEqual(module.clang_profile('md'), folder / 'llvm-mingw/bin/llvm-profdata.exe')
            for other in ('ng', 'cps1', 'x68', 'sms', 'gg', 'gb', 'nes'):
                self.assertIsNone(module.clang_profile(other), other)
            self.assertIsNone(module.clang_profile(None))
            with patch.dict(module.os.environ, {'RETRO_RECOMP_PGO': '0'}):
                self.assertIsNone(module.clang_profile('snes'))
                self.assertIsNone(module.clang_profile('md'))
            with patch('retrorecomp.toolchain.active', return_value='msvc'):
                self.assertIsNone(module.clang_profile('snes'))
                self.assertIsNone(module.clang_profile('md'))
        with patch.object(module.os, 'name', 'posix'):
            self.assertIsNone(module.clang_profile('snes'))
            self.assertIsNone(module.clang_profile('md'))

    def test_unsupported_compiler_keeps_ordinary_build(self):
        project, built, modes, invoke = self.exercise(available=False)
        invoke()
        self.assertEqual(modes, ['generate'])
        self.assertEqual(built.read_bytes(), b'final')
        self.assertFalse(json.loads((project / 'hardware-optimization.json').read_text())['profile_guided'])


if __name__ == '__main__':
    unittest.main()
