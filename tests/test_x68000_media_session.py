"""The authored C helper of the X68000 media session (automatic disk changes, restart, snapshot, corruption, refusals), run on
authored files: no machine, no game, no firmware. libretro.h is the MIT API header kept with Geolith."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIBRETRO_INCLUDE = ROOT / '.deps/geolith-libretro/deps/libretro-common/include'


class MediaSessionRuntimeTests(unittest.TestCase):
    def test_original_c_media_transactions(self):
        if not (LIBRETRO_INCLUDE / 'libretro.h').is_file():
            self.skipTest('libretro.h (the MIT API header of Geolith) is not present')
        from retrorecomp.core import toolchain, ConversionError
        from retrorecomp.platforms import cmake_target_args
        try:
            cmake, generator = toolchain()
        except ConversionError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory(prefix='rr-x68k-media-') as directory:
            work = Path(directory)
            source = ROOT / 'native/x68000_reference/media_session.c'
            harness = ROOT / 'tests/x68000_media_session_harness.c'
            (work / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\nproject(media_checks C)\n'
                f'add_executable(media_checks "{source.as_posix()}" "{harness.as_posix()}")\n'
                f'target_include_directories(media_checks PRIVATE "{(ROOT / "native/x68000_reference").as_posix()}" '
                f'"{LIBRETRO_INCLUDE.as_posix()}")\n'
                'if(MSVC)\ntarget_compile_definitions(media_checks PRIVATE _CRT_SECURE_NO_WARNINGS)\nendif()\n',
                encoding='utf-8')
            build = work / 'build'
            for command in ([str(cmake), '-S', str(work), '-B', str(build), '-G', generator, *cmake_target_args()],
                            [str(cmake), '--build', str(build), '--config', 'Release', '--parallel', '2']):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            exe = next(path for path in (build / 'Release/media_checks.exe', build / 'media_checks.exe', build / 'media_checks')
                       if path.is_file())
            media = work / 'private media'
            media.mkdir()
            (media / 'game.m3u').write_text('disk-01.xdf\ndisk-02.dim\n')
            (media / 'disk-01.xdf').write_bytes(b'A' * 4096)
            (media / 'disk-02.dim').write_bytes(b'B' * 8192)
            three = work / 'three disks'
            three.mkdir()
            (three / 'game.m3u').write_text('disk-01.xdf\ndisk-02.dim\ndisk-03.dim\n')
            for n, byte in enumerate(b'DEF', 1):
                (three / f'disk-0{n}.{"xdf" if n == 1 else "dim"}').write_bytes(bytes([byte]) * 4096)
            result = subprocess.run([str(exe), str(media), str(three)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
