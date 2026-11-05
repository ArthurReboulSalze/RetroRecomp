"""The resload services a WHDLoad slave calls (native/amiga_whdload/rr_resload.c), checked by an authored C harness.

The harness runs every provided service on a flat guest memory with authored files: loads, disk images, saves,
CRC-16, Control tags, the whole patch-list language including IF blocks and PL_NEXT, PatchSeg, Relocate (over itself,
into a CHIP area, as a LoadSeg list), and the refusals of what is not provided. No game, slave or ROM is involved.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResloadHarnessTest(unittest.TestCase):
    def test_the_authored_harness_passes(self):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        with tempfile.TemporaryDirectory(prefix='rr-amiga-resload-') as temp:
            project = Path(temp)
            native = (ROOT / 'native/amiga_whdload').as_posix()
            (project / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                'project(ResloadChecks LANGUAGES C)\n'
                'set(CMAKE_C_STANDARD 11)\n'
                f'add_executable(resload-checks "{ROOT.as_posix()}/tests/amiga_resload_harness.c" "{native}/rr_resload.c")\n'
                f'target_include_directories(resload-checks PRIVATE "{native}")\n'
                'if(MSVC)\n'
                'target_compile_options(resload-checks PRIVATE /W4 /WX /utf-8)\n'
                'target_compile_definitions(resload-checks PRIVATE _CRT_SECURE_NO_WARNINGS)\n'
                'else()\n'
                'target_compile_options(resload-checks PRIVATE -Wall -Wextra -Werror)\n'
                'endif()\n', encoding='utf-8')
            cmake, generator = toolchain()
            for command in ([str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator,
                             *cmake_target_args()],
                            [str(cmake), '--build', str(project / 'build'), '--config', 'Release']):
                built = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(build_executable(project / 'build', 'resload-checks'))],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('OK (0 failures)', result.stdout)


if __name__ == '__main__':
    unittest.main()
