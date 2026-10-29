"""The Neo Geo hardware profile never changes what the game does, and a failed training run never reaches an export."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import neogeo_optimization as module
from retrorecomp.core import ConversionError


class NeoGeoOptimizationTests(unittest.TestCase):
    def exercise(self, *, frames=3600, counters=True, merged=True, fail_use=False, fail_generate=False, exit_code=0):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        project = Path(temporary.name)
        built = project / 'build/game.exe'
        built.parent.mkdir()
        script = project / 'play.inputs'
        script.write_text('0 00 00 0 0\n')
        modes = []
        state = {}

        def plain(folder, target, extra):
            self.assertEqual((folder, target), (project, 'game'))
            mode = next((a.split('=', 1)[1] for a in extra if a.startswith('-DNG_PROFILE_MODE=')), '')
            state['profile'] = Path(next(a.split('=', 1)[1] for a in extra if a.startswith('-DNG_PROFILE_DIR=')))
            self.assertIn(f'-DNG_PROFILE_DATA={(project / "hardware-profile.profdata").as_posix()}', extra)
            modes.append(mode)
            if (mode == 'use' and fail_use) or (mode == 'generate' and fail_generate):
                raise ConversionError('authored optimization failure')
            (project / 'build/CMakeCache.txt').write_text(f'NG_PROFILE_MODE:STRING={mode}\n')
            built.write_bytes(b'instrumented' if mode == 'generate' else b'final')
            return built

        def probe(command, **kwargs):
            command = list(map(str, command))
            profile = state['profile']
            self.assertEqual(Path(command[0]).parent, profile / 'training')
            self.assertEqual(kwargs['cwd'], profile / 'training')
            self.assertIn('--headless', command)
            self.assertEqual(command[command.index('--script') + 1], str(script))
            Path(command[command.index('--report') + 1]).write_text(json.dumps({'frames': frames}))
            if counters:
                (profile / 'ng-1.profraw').write_bytes(b'private compiler counters')
            return subprocess.CompletedProcess(command, exit_code)

        def merge(args, **kwargs):
            args = list(map(str, args))
            self.assertEqual(args[1], 'merge')
            output = Path(next(a.split('=', 1)[1] for a in args if a.startswith('-output=')))
            self.assertEqual(output, project / 'hardware-profile.profdata')   # outside the temporary folder
            self.assertTrue(all(a.endswith('.profraw') for a in args[3:]) and len(args) > 3)
            if merged:
                output.write_bytes(b'merged profile')
            return ''

        def invoke(messages=None):
            with patch('retrorecomp.conversion_common.spawn', side_effect=probe), \
                 patch('retrorecomp.core.run', side_effect=merge), \
                 patch.object(module, 'clang_profile', return_value=Path('tools/llvm-profdata.exe')):
                return module.build_game(project, plain, (3600, script, []), (messages if messages is not None else []).append)

        return project, built, modes, invoke

    def test_completed_profile_rebuilds_final_and_removes_private_counters(self):
        project, built, modes, invoke = self.exercise()
        invoke()
        self.assertEqual(modes, ['generate', 'use'])
        self.assertEqual(built.read_bytes(), b'final')
        self.assertTrue((project / 'hardware-profile.profdata').is_file())
        self.assertFalse(list(project.glob('hardware-profile-*')))
        record = json.loads((project / 'hardware-optimization.json').read_text())
        self.assertEqual((record['profile_guided'], record['training_frames'], record['compiler_profile']),
                         (True, 3600, 'clang-thinlto'))

    def test_failed_training_or_build_goes_on_without_a_profile(self):
        """The profile only chooses layout: a training run that stops early, leaves no counters or no profile, or a build
        error of the instrumented or profiled code ends in an ordinary build, never in an instrumented export."""
        for kwargs, expected in (({'frames': 3599}, ['generate', '']), ({'counters': False}, ['generate', '']),
                                 ({'merged': False}, ['generate', '']), ({'exit_code': 3}, ['generate', '']),
                                 ({'fail_generate': True}, ['generate', '']), ({'fail_use': True}, ['generate', 'use', ''])):
            with self.subTest(kwargs=kwargs):
                project, built, modes, invoke = self.exercise(**kwargs)
                messages = []
                invoke(messages)
                self.assertEqual(modes, expected)
                self.assertEqual(built.read_bytes(), b'final')
                self.assertFalse((project / 'hardware-profile.profdata').exists())
                self.assertTrue(any('ordinary build' in message for message in messages))
                record = json.loads((project / 'hardware-optimization.json').read_text())
                self.assertEqual((record['profile_guided'], record['training_frames']), (False, 0))
                self.assertNotIn('compiler_profile', record)

    def test_no_training_or_no_tool_builds_once_as_before(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        calls = []

        def plain(project, target, extra):
            calls.append((target, tuple(extra)))
            return folder / 'game.exe'

        with patch.object(module, 'clang_profile', return_value=None):
            self.assertEqual(module.build_game(folder, plain, (3600, folder / 'x', []), lambda _: None), folder / 'game.exe')
        with patch.object(module, 'clang_profile', return_value=Path('tools/llvm-profdata.exe')):
            module.build_game(folder, plain, None, lambda _: None)
        self.assertEqual(calls, [('game', ()), ('game', ())])
        self.assertFalse((folder / 'hardware-optimization.json').exists())

    def test_clang_profile_only_on_the_portable_toolchain(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / 'llvm-mingw/bin').mkdir(parents=True)
        (folder / 'llvm-mingw/bin/llvm-profdata.exe').write_bytes(b'x')
        with patch.object(module.os, 'name', 'nt'), patch('retrorecomp.toolchain.active', return_value='llvm'), \
                patch('retrorecomp.toolchain.tools_directory', return_value=folder):
            self.assertEqual(module.clang_profile(), folder / 'llvm-mingw/bin/llvm-profdata.exe')
            with patch.dict(module.os.environ, {'RETRO_RECOMP_PGO': '0'}):
                self.assertIsNone(module.clang_profile())
            with patch('retrorecomp.toolchain.active', return_value='msvc'):
                self.assertIsNone(module.clang_profile())
        with patch.object(module.os, 'name', 'posix'):
            self.assertIsNone(module.clang_profile())

    def test_cmake_block_leaves_the_cartridge_translation_alone(self):
        text = module.CMAKE
        self.assertIn('NOT NG_SOURCE MATCHES "(^|/)steps/"', text)
        self.assertIn('-fprofile-instr-generate=', text)
        self.assertIn('-fprofile-instr-use=', text)
        self.assertIn('NG_PROFILE_MODE STREQUAL "generate" OR NG_PROFILE_MODE STREQUAL "use"', text)


if __name__ == '__main__':
    unittest.main()
