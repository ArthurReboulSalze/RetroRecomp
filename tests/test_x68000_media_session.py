"""The authored C helper of the X68000 media session (automatic disk changes, restart, snapshot, corruption, refusals), run on
authored files: no machine, no game, no firmware. libretro.h is the MIT API header kept with Geolith."""
import os
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
            media, three = authored_media(work)
            result = subprocess.run([str(exe), str(media), str(three)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('checks passed', result.stdout)
            # A library on a linked folder: the folders above the one that holds the media folder are the player's and
            # are never refused; the media folder and the folder that holds it are the session's and still are.
            real = work / 'real library'
            (real / 'game').mkdir(parents=True)
            authored_media(real / 'game')
            links = []
            try:
                linked = link(links, work / 'linked library', real)
                result = subprocess.run([str(exe), str(linked / 'game/private media'), str(linked / 'game/three disks')],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('checks passed', result.stdout)
                link(links, work / 'linked media', real / 'game/private media')
                link(links, work / 'linked game', real / 'game')
                for media_link in (work / 'linked media', work / 'linked game/private media'):
                    with self.subTest(link=media_link.parent.name + '/' + media_link.name):
                        result = subprocess.run([str(exe), str(media_link), str(linked / 'game/three disks')],
                                                capture_output=True, text=True)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn('rr_media_open', result.stderr)
            finally:
                # Only the links go, before the temporary folder: os.rmdir on a junction and os.unlink on a symbolic
                # link never touch the target.
                for made in reversed(links):
                    os.rmdir(made) if os.name == 'nt' else os.unlink(made)


def authored_media(folder):
    """A two-disk and a three-disk private set of authored bytes."""
    media = folder / 'private media'
    media.mkdir()
    (media / 'game.m3u').write_text('disk-01.xdf\ndisk-02.dim\n')
    (media / 'disk-01.xdf').write_bytes(b'A' * 4096)
    (media / 'disk-02.dim').write_bytes(b'B' * 8192)
    three = folder / 'three disks'
    three.mkdir()
    (three / 'game.m3u').write_text('disk-01.xdf\ndisk-02.dim\ndisk-03.dim\n')
    for n, byte in enumerate(b'DEF', 1):
        (three / f'disk-0{n}.{"xdf" if n == 1 else "dim"}').write_bytes(bytes([byte]) * 4096)
    return media, three


def link(links, made, target):
    """A folder link the player could have (a Windows junction, a POSIX symbolic link)."""
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(target), str(made))
    else:
        os.symlink(target, made, target_is_directory=True)
    links.append(made)
    return made


if __name__ == '__main__':
    unittest.main()
