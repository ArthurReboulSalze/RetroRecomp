"""The static SDL2 of the games (1.6.7): its source folder is mapped to `SDL`, and an install built another way is built again."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import core


class SdlInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / 'SDL' / 'install'
        self.source = self.root / 'SDL'
        for patcher in (patch.object(core, 'sdl_install', return_value=self.prefix),
                        patch.object(core, 'sdl_library', return_value='lib/libSDL2.a'),
                        patch.object(core, 'active_toolchain', return_value='llvm'),
                        patch.object(core, 'suffix', return_value='-llvm'),
                        patch.object(core, 'cmake_target_args', return_value=[]),
                        patch.object(core, 'build_jobs', return_value='2')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self, marker=None):
        (self.prefix / 'lib').mkdir(parents=True, exist_ok=True)
        (self.prefix / 'lib/libSDL2.a').write_bytes(b'!<arch>')
        if marker is not None:
            (self.prefix / core.SDL_INSTALL_MARKER).write_text(marker, encoding='utf-8')

    def test_the_source_folder_is_mapped_to_sdl_and_a_path_with_a_space_is_quoted(self):
        self.assertEqual(core.sdl_compiler_flags(Path('C:/Retro/.deps/SDL')), ['-DCMAKE_C_FLAGS=-ffile-prefix-map=C:/Retro/.deps/SDL=SDL'])
        self.assertEqual(core.sdl_compiler_flags(Path('C:/John Smith/.deps/SDL')),
                         ['-DCMAKE_C_FLAGS="-ffile-prefix-map=C:/John Smith/.deps/SDL=SDL"'])
        with patch.object(core, 'active_toolchain', return_value='msvc'):
            self.assertEqual(core.sdl_compiler_flags(Path('C:/Retro/.deps/SDL')), [])      # cl.exe has no such option

    def test_the_key_names_the_revision_the_flags_and_the_toolchain(self):
        key = core.sdl_install_key()
        self.assertIn(core.SDL_REV, key)
        self.assertIn(core.SDL_BUILD_FLAGS, key)
        self.assertIn('toolchain=llvm', key)
        with patch.object(core, 'active_toolchain', return_value='msvc'):
            self.assertNotEqual(core.sdl_install_key(), key)

    def test_an_install_is_current_only_with_the_marker_of_this_key(self):
        self.assertFalse(core.sdl_install_current())                    # nothing installed
        self.install()
        self.assertFalse(core.sdl_install_current())                    # an install of 1.6.6 or before: no marker
        self.install(marker='sdl=old;flags=none;toolchain=llvm\n')
        self.assertFalse(core.sdl_install_current())
        self.install(marker=core.sdl_install_key() + '\n')
        self.assertTrue(core.sdl_install_current())

    def run_ensure(self, fail_at=None):
        commands = []
        def run(command, **options):
            commands.append([str(part) for part in command])
            if fail_at is not None and len(commands) == fail_at:
                raise RuntimeError('build failed')
            if command[1] == '--install':
                self.install()
            return ''
        log = []
        with patch.object(core, 'run', side_effect=run):
            core.ensure_sdl('cmake', 'Ninja', self.source, self.prefix, self.root / 'setup.log', log.append)
        return commands, log

    def test_a_first_install_is_built_with_the_path_map_and_marked(self):
        commands, log = self.run_ensure()
        self.assertEqual([c[1] for c in commands], ['-S', '--build', '--install'])
        self.assertIn(f'-DCMAKE_C_FLAGS=-ffile-prefix-map={self.source.as_posix()}=SDL', commands[0])
        self.assertIn('première utilisation', log[0])
        self.assertTrue(core.sdl_install_current())
        commands, log = self.run_ensure()
        self.assertEqual((commands, log), ([], []))                       # current: nothing is built

    def test_an_old_install_is_built_again_from_a_clean_build_folder(self):
        self.install()                                                    # 1.6.6: a library, no marker
        stale = self.source / 'build-llvm'
        stale.mkdir(parents=True)
        (stale / 'old.o').write_bytes(b'x')
        commands, log = self.run_ensure()
        self.assertEqual(len(commands), 3)
        self.assertIn('nouvelle configuration', log[0])
        self.assertFalse((stale / 'old.o').exists())
        self.assertTrue(core.sdl_install_current())

    def test_a_build_that_fails_leaves_no_marker_so_it_is_tried_again_and_never_used_silently(self):
        self.install(marker='sdl=old;flags=none;toolchain=llvm\n')
        with self.assertRaises(RuntimeError):
            self.run_ensure(fail_at=2)
        self.assertFalse((self.prefix / core.SDL_INSTALL_MARKER).exists())
        self.assertFalse(core.sdl_install_current())

    def test_the_setup_check_of_the_window_sees_an_old_install_as_not_ready(self):
        self.install()
        with patch.object(core, 'ROOT', self.root):
            (self.root / '.deps/smsggrecomp/external/z80-recomp-core/include').mkdir(parents=True)
            (self.root / '.deps/smsggrecomp/external/z80-recomp-core/include/sms_runtime.h').write_text('x')
            with patch.object(core, 'build_executable', return_value=self.root / 'present'):
                (self.root / 'present').write_text('x')
                self.assertFalse(core.dependencies_ready())
                (self.prefix / core.SDL_INSTALL_MARKER).write_text(core.sdl_install_key(), encoding='utf-8')
                self.assertTrue(core.dependencies_ready())


if __name__ == '__main__':
    unittest.main()
