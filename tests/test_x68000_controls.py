"""Execute the real frontend callbacks using SDL virtual controllers/events."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SDLControlsTests(unittest.TestCase):
    def test_actual_frontend_with_sdl_virtual_controllers(self):
        self.run_harness('controls')

    def test_shared_menus_and_fresh_process_settings(self):
        self.run_harness('menu', fresh=True)

    def run_harness(self, harness, fresh=False):
        from retrorecomp.core import toolchain, ConversionError
        from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
        sdl = sdl_install()
        # libretro.h is the MIT API header shipped by the pinned Geolith checkout.
        libretro = ROOT / '.deps/geolith-libretro/deps/libretro-common/include'
        if not sdl.is_dir():
            self.skipTest('Native SDL installation unavailable')
        if not (libretro / 'libretro.h').is_file():
            self.skipTest('Geolith libretro.h unavailable')
        try:
            cmake, generator = toolchain()
        except ConversionError as exc:
            self.skipTest(str(exc))
        work = ROOT / ('.build/x68000-stage6/menu' if fresh else '.build/x68000-stage5/controls')
        work.mkdir(parents=True, exist_ok=True)
        cmakelists = '''cmake_minimum_required(VERSION 3.20)
project(x68000_controls C)
find_package(SDL2 CONFIG REQUIRED)
set(ROOT "{root}")
add_executable(controls "${{ROOT}}/tests/x68000_{harness}_harness.c"
 "${{ROOT}}/native/retro_menu.c" "${{ROOT}}/native/platform_io.c"
 "${{ROOT}}/native/x68000_reference/media_session.c"
 "${{ROOT}}/native/x68000_reference/state_store.c")
target_include_directories(controls PRIVATE "{libretro}"
 "${{ROOT}}/native"
 "${{ROOT}}/native/x68000_reference")
target_compile_definitions(controls PRIVATE SDL_MAIN_HANDLED _CRT_SECURE_NO_WARNINGS)
if(TARGET SDL2::SDL2-static)
 target_link_libraries(controls PRIVATE SDL2::SDL2-static)
else()
 target_link_libraries(controls PRIVATE SDL2::SDL2)
endif()
if(NOT WIN32)
 target_link_libraries(controls PRIVATE m)
else()
 target_link_libraries(controls PRIVATE gdi32)
endif()
'''.format(root=ROOT.as_posix(), harness=harness, libretro=libretro.as_posix())
        (work / 'CMakeLists.txt').write_text(cmakelists, encoding='utf-8')
        # One build folder per generator: CMake refuses a folder configured by another one (Visual Studio, Ninja).
        build = work / ('build-' + re.sub(r'\W+', '-', generator).strip('-').lower())
        for command in ([str(cmake), '-S', str(work), '-B', str(build), '-G', generator,
                         *cmake_target_args(), f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],
                        [str(cmake), '--build', str(build), '--config', 'Release', '--parallel', '2']):
            result = subprocess.run(command, capture_output=True, text=True)
            (work / ('configure.log' if '-S' in command else 'build.log')).write_text(
                result.stdout + result.stderr, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        executable = build_executable(build, 'controls')
        result = subprocess.run([str(executable)], capture_output=True, text=True, encoding="utf-8", timeout=30)
        (work / 'result.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertGreaterEqual(report['checks'], 20 if fresh else 25)
        self.assertEqual(report['failures'], 0)
        if fresh:
            result = subprocess.run([str(executable), '--verify'], capture_output=True, text=True, encoding="utf-8", timeout=30)
            (work/'fresh-process.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertGreaterEqual(json.loads(result.stdout.splitlines()[-1])['checks'], 6)


if __name__ == '__main__':
    unittest.main()
