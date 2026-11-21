"""The PC Engine CD disc provider against two independent readers (no commercial disc needed, no System Card, no game).

    python -B tools/pcecd_disc_selftest.py [--disc IMAGE ...] [--keep]

It builds native/pcecd_disc.cpp with libchdr linked statically (the way a game is built: the pinned engine as a CMake subproject), with the probe
native/pcecd_disc_checks.cpp, and runs it on discs the tool authors itself (a CHD of version 5 with `cdzl` and `cdlz` hunks, a CHD of version 4, an
ISO, and each of them inside a larger file at an offset, as a disc appended to a game) and on the images given with --disc. For every disc the table of
contents, the user data of the first sectors of each data track and the samples of the first audio tracks that the provider reads must equal what the
pure-Python reader (retrorecomp/pcecd_disc.py, which checks every hunk against the CRC of the file's map) reads; for a CHD of version 5 they must also equal
what the engine's own provider reads (it loads a libchdr shared library by path, which this tool builds too). A version 4 CHD the engine refuses is
reported as such, and is only compared with the Python reader.

It says nothing of the machine, of gameplay or of speed. Exit status 0 when every disc passes. Work folder: `.build/pcecd-disc-selftest`.
"""
from pathlib import Path
import argparse
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from retrorecomp.paths import ASSETS

WORK = ROOT / '.build' / 'pcecd-disc-selftest'


def build(project: Path) -> Path:
    from retrorecomp import core, pce_build, pcecd_build
    from retrorecomp.platforms import build_executable
    pce_build.ensure_engine(print)
    pcecd_build.ensure_libchdr(print)
    engine = pce_build.checkout_path().as_posix()
    native = (ASSETS / 'native').as_posix()
    project.mkdir(parents=True, exist_ok=True)
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPcecdDiscChecks LANGUAGES C CXX)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)',
        *pcecd_build.libchdr_cmake_lines(),
        f'pce_add_native_module(PCE_MODULE MODULE "{engine}/runtime/src/no_module.cpp")',     # the engine's stub: nothing is translated here
        'get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)',
        'add_library(pce_module OBJECT ${PCE_MODULE_SOURCES})',
        'target_link_libraries(pce_module PUBLIC pce-runtime)',
        'set_target_properties(pce_module PROPERTIES CXX_EXTENSIONS OFF)',
        f'add_executable(pcecd_disc_checks "{native}/pcecd_disc_checks.cpp" "{native}/pcecd_disc.cpp" $<TARGET_OBJECTS:pce_module>)',
        f'target_include_directories(pcecd_disc_checks PRIVATE "{native}")',
        'target_link_libraries(pcecd_disc_checks PRIVATE pce-runtime chdr-static)',
    ]
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'pcecd_disc_checks', '--parallel', core.build_jobs()],
             log=log, timeout=3600)
    return build_executable(project / 'build', 'pcecd_disc_checks')


def build_shared_libchdr(folder: Path) -> Path:
    """libchdr as the shared library the engine's provider loads by path (the engine's own scripts/bootstrap_chd.py recipe)."""
    from retrorecomp import core, pcecd_build
    source = pcecd_build.ensure_libchdr(print)
    cmake, generator = core.toolchain()
    log = folder / 'build.log'
    folder.mkdir(parents=True, exist_ok=True)
    core.run([cmake, '-S', source, '-B', folder, '-G', generator, '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=ON', '-DCHDR_WANT_TESTS=OFF',
              *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', folder, '--target', 'chdr', '--parallel', core.build_jobs()], log=log, timeout=1800)
    for name in ('libchdr.dll', 'libchdr.so', 'libchdr.dylib'):
        for found in folder.rglob(name):
            return found
    raise RuntimeError('libchdr was not built as a shared library')


def fnv(data: bytes, hash_value: int = 14695981039346656037) -> int:
    for byte in data:
        hash_value = ((hash_value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return hash_value


def python_summary(path: Path) -> dict:
    """The table of contents and the hashes the probe prints, from the pure-Python reader."""
    from retrorecomp import pcecd_disc
    disc = pcecd_disc.open_disc(path)
    try:
        out = {'tracks': len(disc.tracks), 'leadout': disc.leadout, 'rows': []}
        audio_seen = 0
        for track in disc.tracks:
            data = audio = 0
            if not track.audio:
                hash_value = 14695981039346656037
                for lba in range(track.start, min(track.start + track.length, track.start + 64)):
                    try:
                        hash_value = fnv(disc.user(lba), hash_value)
                    except pcecd_disc.DiscError:                      # the provider's read error: only the fact is hashed
                        hash_value = fnv(b'E', hash_value)
                data = hash_value
            elif audio_seen < 3:
                audio_seen += 1
                hash_value = 14695981039346656037
                for lba in range(track.start, min(track.start + track.length, track.start + 8)):
                    try:
                        raw = disc.raw(lba)
                    except pcecd_disc.DiscError:                      # the audio codec (cdfl) is not read in Python: the engine's provider is the referee
                        hash_value = None
                        break
                    # the audio of a CHD is big-endian: the probe hashes host (little-endian) samples
                    swapped = bytearray(raw)
                    swapped[0::2], swapped[1::2] = raw[1::2], raw[0::2]
                    hash_value = fnv(bytes(swapped), hash_value)
                audio = hash_value
            out['rows'].append((track.start, 0 if track.audio else 4, data, audio))
        return out
    finally:
        disc.close()


def parse_probe(text: str, label: str) -> dict:
    out = {'rows': []}
    for line in text.splitlines():
        head = re.match(rf'{label} tracks=(\d+) leadout=(\d+)', line)
        if head:
            out['tracks'], out['leadout'] = int(head[1]), int(head[2])
        row = re.match(rf'{label} track \d+ start=(\d+) type=(\d+) data=([0-9a-f]+) audio=([0-9a-f]+)', line)
        if row:
            out['rows'].append((int(row[1]), int(row[2]), int(row[3], 16), int(row[4], 16)))
    return out


def run_probe(probe: Path, image: Path, sha: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(probe), str(image), sha, *extra], capture_output=True, text=True, timeout=1800,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def check(probe: Path, image: Path, label: str, libchdr: Path | None, *, offset: int = 0, length: int = 0, plain: Path | None = None) -> bool:
    sha = '0' * 64
    extra = []
    if offset or length:
        extra += ['--offset', str(offset), '--length', str(length)]
    done = run_probe(probe, image, sha, *extra)
    ours = parse_probe(done.stdout, 'ours')
    reference = python_summary(plain or image)
    expected = {'tracks': reference['tracks'], 'leadout': reference['leadout'], 'rows': []}
    for ours_row, row in zip(ours['rows'], reference['rows']):
        expected['rows'].append(ours_row if row[3] is None and row[:3] == ours_row[:3] else row)      # None: audio the Python reader does not decode
    good = done.returncode == 0 and ours == expected
    note = ''
    if good and libchdr and not (offset or length):
        theirs = run_probe(probe, image, sha, '--engine', str(libchdr))
        if 'engine SAME' in theirs.stdout:
            note = ', and the same as the engine\'s provider'
        elif 'FAULT' in theirs.stdout:
            note = ', the engine\'s provider refuses it: ' + theirs.stdout.strip().splitlines()[-1][:90]
        else:
            good = False
            note = ', DIFFERENT from the engine\'s provider'
    print(f'{label}: {"PASS" if good else "FAIL"}{note}')
    if not good:
        print(done.stdout.rstrip()[-600:], done.stderr.strip()[-300:])
    return good


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--disc', action='append', default=[], type=Path, help='a disc image to read (kept as it is)')
    parser.add_argument('--keep', action='store_true', help='keep the work folder (the build is reused either way)')
    arguments = parser.parse_args()
    import test_pcecd_disc as authored
    WORK.mkdir(parents=True, exist_ok=True)
    layout = authored.Layout()
    images = {'v5 cdzl': WORK / 'v5-cdzl.chd', 'v5 cdlz': WORK / 'v5-cdlz.chd', 'v4 zlib': WORK / 'v4-zlib.chd', 'v4 raw': WORK / 'v4-raw.chd',
              'iso': WORK / 'a.iso'}
    authored.write_chd_v5(images['v5 cdzl'], layout, 'cdzl')
    authored.write_chd_v5(images['v5 cdlz'], layout, 'cdlz')
    authored.write_chd_v4(images['v4 zlib'], layout, True)
    authored.write_chd_v4(images['v4 raw'], layout, False)
    authored.write_iso(images['iso'])
    probe = build(WORK / 'project')
    libchdr = build_shared_libchdr(WORK / 'libchdr-shared')
    good = True
    for label, image in images.items():
        good = check(probe, image, label, libchdr) and good
        # the same disc inside a larger file, as it is appended to a game
        data = image.read_bytes()
        embedded = WORK / (image.name + '.embedded')
        embedded.write_bytes(b'executable' * 1000 + data + b'trailer' * 100)
        plain = WORK / ('plain-' + image.name)
        plain.write_bytes(data)
        good = check(probe, embedded, label + ' embedded', None, offset=10000, length=len(data), plain=plain) and good
    for path in arguments.disc:
        good = check(probe, path, path.name, libchdr) and good
    print('PASS' if good else 'FAIL')
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
