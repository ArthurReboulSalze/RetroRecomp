"""Choosing the toolchain that builds games on Windows."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import toolchain


def install_fake(tools, version=None):
    for folder, (pinned, marker) in toolchain._pinned().items():
        path = tools / folder
        (path / marker).parent.mkdir(parents=True, exist_ok=True)
        (path / marker).write_bytes(b'MZ')
        (path / toolchain.STAMP).write_text(json.dumps({'version': version or pinned}), encoding='utf-8')


@unittest.skipUnless(os.name == 'nt', 'Windows toolchain selection')
class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tools = Path(self.directory.name) / 'tools'
        for patcher in (patch.object(toolchain, 'tools_directory', return_value=self.tools),
                        patch.dict(os.environ, {'PATH': os.environ.get('PATH', '')}, clear=False)):
            patcher.start()
            self.addCleanup(patcher.stop)
        os.environ.pop('RETRO_RECOMP_TOOLCHAIN', None)
        toolchain.visual_studio.cache_clear()
        self.addCleanup(toolchain.visual_studio.cache_clear)

    def studio(self):
        return patch.object(toolchain, 'visual_studio', return_value=(Path('C:/vs/cmake.exe'), 'Visual Studio 17 2022'))

    def nothing(self):
        return patch.object(toolchain, 'visual_studio', return_value=None)

    def test_portable_tools_come_first_and_extend_path(self):
        install_fake(self.tools)
        with self.studio():
            chosen = toolchain.select()
        self.assertEqual((chosen.kind, chosen.generator), (toolchain.LLVM, 'Ninja'))
        self.assertEqual(chosen.cmake, self.tools / 'cmake/bin/cmake.exe')
        entries = os.environ['PATH'].split(os.pathsep)
        self.assertEqual(entries[:3], [str(path) for path in toolchain.portable_path_entries()])

    def test_visual_studio_is_the_fallback_and_can_be_requested(self):
        with self.studio():
            self.assertEqual(toolchain.select().kind, toolchain.MSVC)
            self.assertEqual(toolchain.cmake_arguments(), ['-A', 'x64'])
            self.assertEqual(toolchain.suffix(), '')
        install_fake(self.tools)
        with self.studio(), patch.dict(os.environ, {'RETRO_RECOMP_TOOLCHAIN': 'msvc'}):
            self.assertEqual(toolchain.select().kind, toolchain.MSVC)

    def test_nothing_installed_is_reported_and_llvm_cannot_be_forced(self):
        with self.nothing():
            with self.assertRaises(toolchain.ToolchainError):
                toolchain.select()
            self.assertEqual(toolchain.active(), toolchain.MSVC)
        with self.studio(), patch.dict(os.environ, {'RETRO_RECOMP_TOOLCHAIN': 'llvm'}):
            with self.assertRaises(toolchain.ToolchainError):
                toolchain.select()

    def test_other_versions_or_missing_files_do_not_count_as_installed(self):
        install_fake(self.tools, version='0.0.1')
        self.assertFalse(toolchain.portable_installed())
        install_fake(self.tools)
        self.assertTrue(toolchain.portable_installed())
        (self.tools / 'ninja/ninja.exe').unlink()
        self.assertFalse(toolchain.portable_installed())

    def test_configure_arguments_name_every_tool_and_link_statically(self):
        install_fake(self.tools)
        arguments = toolchain.cmake_arguments()
        self.assertIn('-DCMAKE_BUILD_TYPE=Release', arguments)
        self.assertIn('-DCMAKE_EXE_LINKER_FLAGS=-static -s', arguments)
        for name in ('CMAKE_C_COMPILER=', 'CMAKE_CXX_COMPILER=', 'CMAKE_RC_COMPILER=', 'CMAKE_MAKE_PROGRAM='):
            self.assertTrue(any(part.startswith('-D' + name) and ':' in part for part in arguments), name)
        self.assertNotIn('-A', arguments)
        self.assertEqual(toolchain.suffix(), '-llvm')
        self.assertEqual(toolchain.describe()['kind'], toolchain.LLVM)

    def test_ninja_builds_do_not_use_a_configuration_folder(self):
        from retrorecomp.platforms import build_executable
        build = Path('build')
        install_fake(self.tools)
        self.assertEqual(build_executable(build, 'game'), build / 'game.exe')
        with self.studio(), patch.dict(os.environ, {'RETRO_RECOMP_TOOLCHAIN': 'msvc'}):
            self.assertEqual(build_executable(build, 'game'), build / 'Release' / 'game.exe')

    def test_a_build_folder_from_another_generator_or_compiler_is_discarded(self):
        install_fake(self.tools)
        root = Path(self.directory.name)
        compiler = (self.tools / 'llvm-mingw/bin/clang.exe').as_posix()

        def configured(name, generator, cc):
            build = root / name
            build.mkdir()
            (build / 'CMakeCache.txt').write_text(
                f'CMAKE_GENERATOR:INTERNAL={generator}\nCMAKE_C_COMPILER:FILEPATH={cc}\n', encoding='utf-8')
            return build
        command = lambda build, generator: ['cmake', '-S', 'src', '-B', str(build), '-G', generator,
                                            f'-DCMAKE_C_COMPILER={compiler}']
        same = configured('same', 'Ninja', compiler)
        toolchain.reset_incompatible_cache(command(same, 'Ninja'))
        self.assertTrue(same.exists())
        studio = configured('studio', 'Visual Studio 17 2022', 'C:/vs/cl.exe')
        toolchain.reset_incompatible_cache(command(studio, 'Ninja'))
        self.assertFalse(studio.exists())
        gcc = configured('gcc', 'Ninja', 'C:/other/gcc.exe')
        toolchain.reset_incompatible_cache(command(gcc, 'Ninja'))
        self.assertFalse(gcc.exists())
        fresh = root / 'fresh'
        toolchain.reset_incompatible_cache(command(fresh, 'Ninja'))
        self.assertFalse(fresh.exists())
        # Visual Studio asked for a folder the portable tools configured.
        ninja = configured('ninja', 'Ninja', compiler)
        toolchain.reset_incompatible_cache(['cmake', '-S', 'src', '-B', str(ninja), '-G', 'Visual Studio 17 2022', '-A', 'x64'])
        self.assertFalse(ninja.exists())


if __name__ == '__main__':
    unittest.main()
