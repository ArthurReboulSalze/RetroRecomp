"""The static SDL2 of the games (1.6.7): its source folder is mapped to `SDL`, and each build setting has its own install."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import batch, core, gui_updates, i18n, platforms


class SdlInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / '.deps' / 'SDL'
        self.source.mkdir(parents=True)
        (self.source / 'INSTALL.txt').write_text('SDL ships a file with this name', encoding='utf-8')
        for patcher in (patch('retrorecomp.paths.ROOT', self.root),
                        patch('retrorecomp.toolchain.active', return_value='llvm'),
                        patch('retrorecomp.toolchain.suffix', return_value='-llvm'),
                        patch.object(core, 'active_toolchain', return_value='llvm'),
                        patch.object(core, 'cmake_target_args', return_value=[]),
                        patch.object(core, 'build_jobs', return_value='2')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.prefix = platforms.sdl_install()

    def install(self, prefix=None, marker=True):
        prefix = prefix or self.prefix
        (prefix / 'lib').mkdir(parents=True, exist_ok=True)
        (prefix / 'lib' / platforms.sdl_library().split('/')[-1]).write_bytes(b'!<arch>')
        if marker:
            (prefix / platforms.SDL_INSTALL_MARKER).write_text(platforms.sdl_install_key() + '\n', encoding='utf-8')

    def test_the_source_folder_is_mapped_to_sdl_and_a_path_with_a_space_is_quoted(self):
        self.assertEqual(platforms.sdl_compiler_flags(Path('C:/Retro/.deps/SDL')),
                         ['-DCMAKE_C_FLAGS=-ffile-prefix-map=C:/Retro/.deps/SDL=SDL'])
        self.assertEqual(platforms.sdl_compiler_flags(Path('C:/John Smith/.deps/SDL')),
                         ['-DCMAKE_C_FLAGS="-ffile-prefix-map=C:/John Smith/.deps/SDL=SDL"'])
        with patch('retrorecomp.toolchain.active', return_value='msvc'):
            self.assertEqual(platforms.sdl_compiler_flags(Path('C:/Retro/.deps/SDL')), [])      # cl.exe has no such option

    def test_each_key_has_its_own_install_and_build_folder(self):
        key = platforms.sdl_install_key()
        self.assertIn(core.SDL_REV, key)
        self.assertIn(platforms.SDL_BUILD_FLAGS, key)
        self.assertRegex(self.prefix.name, r'^install-llvm-[0-9a-f]{8}$')
        self.assertEqual(platforms.sdl_build_folder().name, self.prefix.name.replace('install', 'build', 1))
        self.assertEqual(self.prefix.parent, self.source)
        with patch.object(platforms, 'SDL_BUILD_FLAGS', 'path-map-2'):
            self.assertNotEqual(platforms.sdl_install(), self.prefix)
        with patch('retrorecomp.toolchain.active', return_value='msvc'):
            self.assertNotEqual(platforms.sdl_install_key(), key)

    def test_an_install_is_current_only_when_it_is_finished(self):
        self.assertFalse(platforms.sdl_install_current())                 # nothing installed
        self.install(marker=False)
        self.assertFalse(platforms.sdl_install_current())                 # the install stopped before its last step
        self.install()
        self.assertTrue(platforms.sdl_install_current())

    def run_ensure(self, fail_at=None):
        commands, options = [], []
        def run(command, **kwargs):
            commands.append([str(part) for part in command])
            options.append(kwargs)
            if fail_at is not None and len(commands) == fail_at:
                raise RuntimeError('build failed')
            if command[1] == '--install':
                self.install(marker=False)
            return ''
        log = []
        with patch.object(core, 'run', side_effect=run):
            core.ensure_sdl('cmake', 'Ninja', self.source, self.prefix, self.root / 'setup.log', log.append)
        return commands, options, log

    def test_a_first_install_is_built_with_the_path_map_a_long_limit_and_marked(self):
        commands, options, log = self.run_ensure()
        self.assertEqual([c[1] for c in commands], ['-S', '--build', '--install'])
        self.assertIn(f'-DCMAKE_C_FLAGS=-ffile-prefix-map={self.source.as_posix()}=SDL', commands[0])
        self.assertIn(self.prefix.as_posix(), ' '.join(commands[0]))
        self.assertEqual({o['timeout'] for o in options}, {core.SDL_STEP_TIMEOUT})
        self.assertGreaterEqual(core.SDL_STEP_TIMEOUT, 3600)
        self.assertIn('première utilisation', log[0])
        self.assertTrue(platforms.sdl_install_current())
        commands, _, log = self.run_ensure()
        self.assertEqual((commands, log), ([], []))                       # current: nothing is built

    def test_an_install_of_other_settings_is_left_alone_and_a_new_one_built_beside_it(self):
        old = self.source / 'install-llvm'                                 # 1.6.6: no key in its name
        self.install(prefix=old, marker=False)
        (old / 'lib' / 'libSDL2.a').write_bytes(b'old library')
        older_build = self.source / 'build-llvm'
        older_build.mkdir()
        (older_build / 'old.o').write_bytes(b'x')
        commands, _, log = self.run_ensure()
        self.assertEqual(len(commands), 3)
        self.assertIn('nouveaux réglages', log[0])
        self.assertEqual((old / 'lib' / 'libSDL2.a').read_bytes(), b'old library')       # not overwritten, not deleted
        self.assertTrue((older_build / 'old.o').exists())
        self.assertIn(self.prefix.name.replace('install', 'build', 1), commands[1][2])      # a build folder of its own
        self.assertTrue(platforms.sdl_install_current())

    def test_a_build_that_fails_or_times_out_keeps_its_build_folder_and_is_not_current(self):
        build = self.source / self.prefix.name.replace('install', 'build', 1)
        build.mkdir()
        (build / 'half.o').write_bytes(b'x')
        with self.assertRaises(RuntimeError):
            self.run_ensure(fail_at=2)
        self.assertTrue((build / 'half.o').exists())                       # the next build goes on from it
        self.assertFalse(platforms.sdl_install_current())
        commands, _, _ = self.run_ensure()
        self.assertEqual(len(commands), 3)
        self.assertTrue((build / 'half.o').exists())
        self.assertTrue(platforms.sdl_install_current())

    def test_the_setup_check_of_the_window_needs_the_install_of_the_current_settings(self):
        self.install(prefix=self.source / 'install-llvm', marker=False)   # an old install is not ready
        (self.root / '.deps/smsggrecomp/external/z80-recomp-core/include').mkdir(parents=True)
        (self.root / '.deps/smsggrecomp/external/z80-recomp-core/include/sms_runtime.h').write_text('x')
        with patch.object(core, 'ROOT', self.root), \
                patch.object(core, 'build_executable', return_value=self.root / 'present'):
            (self.root / 'present').write_text('x')
            self.assertFalse(core.dependencies_ready())
            self.install()
            self.assertTrue(core.dependencies_ready())

    def test_the_two_build_messages_are_translated_for_the_window_and_the_log(self):
        for text, key in (('Compilation de SDL2 statique (première utilisation)…', 'deps_step_sdl'),
                          ('Compilation de SDL2 statique (nouveaux réglages)…', 'deps_step_sdl_again')):
            self.assertEqual(i18n.STRINGS[key][1], text)
            self.assertIn(text, i18n.LOG_TRANSLATIONS)
            for code in ('it', 'es', 'de', 'zh', 'ja', 'ru'):
                self.assertTrue(i18n.catalog(code)['ui'][key])
        import inspect
        source = inspect.getsource(gui_updates)
        self.assertIn("'Compilation de SDL2 statique (nouveaux réglages)…': 'deps_step_sdl_again'", source)
        self.assertNotIn('first conversion', i18n.STRINGS['deps_intro'][0])      # the dialog is also the update dialog


class PrepareSharedTests(unittest.TestCase):
    """batch._prepare_shared: the shared pieces are built once, before the workers, outside any compilation budget."""

    def test_they_are_built_once_when_not_ready_and_not_at_all_when_ready(self):
        log = []
        with patch('retrorecomp.core.dependencies_ready', return_value=False), \
                patch('retrorecomp.core.dependencies') as dependencies:
            batch._prepare_shared(log.append)
        dependencies.assert_called_once_with(log.append)
        with patch('retrorecomp.core.dependencies_ready', return_value=True), \
                patch('retrorecomp.core.dependencies') as dependencies:
            batch._prepare_shared(log.append)
        dependencies.assert_not_called()

    def test_a_failure_is_reported_not_raised_and_stop_goes_through(self):
        log = []
        with patch('retrorecomp.core.dependencies_ready', return_value=False), \
                patch('retrorecomp.core.dependencies', side_effect=core.ConversionError('no compiler')):
            batch._prepare_shared(log.append)
        self.assertEqual(log, ['Shared dependencies: no compiler'])
        with patch('retrorecomp.core.dependencies_ready', return_value=False), \
                patch('retrorecomp.core.dependencies', side_effect=core.StopRequested('stop')):
            with self.assertRaises(core.StopRequested):
                batch._prepare_shared(log.append)

    def test_the_batch_asks_for_it_only_when_told_to(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(batch, '_prepare_shared') as prepare:
            batch.convert_batch([], Path(folder))
            prepare.assert_not_called()
            batch.convert_batch([], Path(folder), prepare_shared=True)
            prepare.assert_called_once()


if __name__ == '__main__':
    unittest.main()
