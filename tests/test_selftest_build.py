"""No-compiler checks for the shared CMake self-test runner."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.selftest_build import compile_and_run


class SelftestBuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.commands = []

    def fake_toolchain(self):
        return Path('cmake-fake'), 'Fake Generator'

    def fake_run(self, command, log=None, timeout=None):
        self.commands.append(([str(item) for item in command], log, timeout))
        return 'combined-output'

    def test_builds_configures_and_runs_one_target(self):
        result = compile_and_run(
            self.project, ('first.c', 'second.c'), ('RR_TEST=1', 'QUIET'),
            include_dirs=('include',), compile_options=('/utf-8',),
            link_options=('/CETCOMPAT:NO',), link_libraries=('ws2_32',),
            arguments=('argument.txt',), parallel=2, log=True, timeout=17,
            toolchain_func=self.fake_toolchain,
            target_args_func=lambda: ['-DFAKE=1'],
            executable_func=lambda build, name: build / (name + '.fake'),
            run_func=self.fake_run)
        self.assertEqual(result, 'combined-output')
        configure, build, run = self.commands
        self.assertEqual(configure[0][1:7], ['-S', str(self.project), '-B', str(self.project / 'build'), '-G', 'Fake Generator'])
        self.assertIn('-DFAKE=1', configure[0])
        self.assertEqual(configure[1], self.project / 'build.log')
        self.assertIn('--parallel', build[0])
        self.assertEqual(build[0][-1], '2')
        self.assertEqual(run[0][-1], 'argument.txt')
        self.assertEqual(run[2], 17)
        cmake = (self.project / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('project(ChecksChecks C)', cmake)
        self.assertIn('add_executable(checks "first.c" "second.c")', cmake)
        self.assertIn('RR_TEST=1 QUIET', cmake)
        self.assertIn('"include"', cmake)
        self.assertIn('/utf-8', cmake)
        self.assertIn('/CETCOMPAT:NO', cmake)
        self.assertIn('ws2_32', cmake)

    def test_sdl_dependency_and_split_process_output(self):
        sdl_dir = self.project / ' sdl'

        def fake_sdl():
            sdl_dir.mkdir(exist_ok=True)
            return sdl_dir

        def fake_process(command, env, cwd, capture_output, text, timeout):
            self.assertEqual(command[-1], str(self.project / 'menus.bmp'))
            self.assertEqual(cwd, Path.cwd())
            self.assertEqual(env['SDL_VIDEODRIVER'], 'dummy')
            return subprocess.CompletedProcess(command, 0, 'split-stdout', 'split-stderr')

        result = compile_and_run(
            self.project, 'check.c', requires_sdl=True, sdl_func=fake_sdl,
            arguments=(self.project / 'menus.bmp',), env={'SDL_VIDEODRIVER': 'dummy'},
            toolchain_func=self.fake_toolchain,
            target_args_func=lambda: [],
            executable_func=lambda build, name: build / name,
            run_func=self.fake_run, process_func=fake_process, combined_output=False)
        self.assertEqual((result.stdout, result.stderr), ('split-stdout', 'split-stderr'))
        cmake = (self.project / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('find_package(SDL2 CONFIG REQUIRED)', cmake)
        configure = self.commands[0]
        self.assertIn('-DCMAKE_PREFIX_PATH=' + sdl_dir.as_posix(), configure[0])


if __name__ == '__main__':
    unittest.main()
