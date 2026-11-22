"""The PC Engine CD snapshot's determinism probe (the multiplayer rollback contract on a real System Card and a real disc).

    python -B tools/pcecd_snapshot_selftest.py --card SYSCARD.pce --disc GAME.chd [--standard] [--frames 600] [--stride 20] [--keep]

It is the probe of tools/pce_snapshot_selftest.py (native/pce_snapshot_checks.cpp) built for a disc: the pinned engine as a CMake subproject, the bridge
`native/pce_machine.cpp` with RR_PCE_DISC, the snapshot `native/pce_snapshot.cpp`, the disc provider with libchdr linked statically, and the engine's no-module
stub, so that every instruction runs on the interpreter. It needs what a player has and the repository never holds: the System Card (`--card`, 256 KiB) and a
disc (`--disc`, a CHD or an ISO). Neither is read by the public checks, and nothing of them is written anywhere but the work folder's build log.

For a save point every `--stride` frames of `--frames` frames of a script of pseudo-random pads (the same one the HuCard probe plays), the state is loaded back and
the engine's own full checkpoint (every field of the machine, the drive, the ADPCM unit, the backup memory, both frame buffers, the audio side) must equal the one
taken at the save; the frames that follow must repeat the digest and the checkpoint of the first pass; the digest must read the drive, the ADPCM unit, the backup
memory and the card's RAM, and must not depend on how the host drank the sound (a second run that drains the PCM after every frame has the same digests).

It says nothing of the native code (the translated code is proved against the interpreter apart), of speed (nothing here is timed), of the disc's own
gameplay, or of the machine against hardware. Exit status 0 only when the probe prints PASS. Work folder: `.build/pcecd-snapshot-selftest` (the build is reused).
`--native DIR` builds from another copy of native/ (a developer's scratch tree).
"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.paths import ASSETS

WORK = ROOT / '.build' / 'pcecd-snapshot-selftest'


def build(project: Path, native_dir: Path) -> Path:
    from retrorecomp import core, pce_build, pcecd_build
    from retrorecomp.platforms import build_executable
    pce_build.ensure_engine(print)
    pcecd_build.ensure_libchdr(print)
    engine = pce_build.checkout_path().as_posix()
    native = native_dir.as_posix()
    project.mkdir(parents=True, exist_ok=True)
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPcecdSnapshotChecks LANGUAGES C CXX)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)',
        *pce_build.engine_patch_lines(engine, f'{native}/pce_engine'),
        *pcecd_build.libchdr_cmake_lines(),
        f'pce_add_native_module(PCE_MODULE MODULE "{engine}/runtime/src/no_module.cpp")',
        'get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)',
        'add_library(pce_module OBJECT ${PCE_MODULE_SOURCES})',
        'target_link_libraries(pce_module PUBLIC pce-runtime)',
        'set_target_properties(pce_module PROPERTIES CXX_EXTENSIONS OFF)',
        f'add_executable(pcecd_snapshot_checks "{native}/pce_snapshot_checks.cpp" "{native}/pce_machine.cpp" "{native}/pce_snapshot.cpp" '
        f'"{native}/pcecd_disc.cpp" $<TARGET_OBJECTS:pce_module>)',
        f'target_include_directories(pcecd_snapshot_checks PRIVATE "{native}")',
        'target_compile_definitions(pcecd_snapshot_checks PRIVATE RR_PCE_DISC=1)',
        'target_link_libraries(pcecd_snapshot_checks PRIVATE pce-runtime chdr-static)',
    ]
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'pcecd_snapshot_checks', '--parallel', core.build_jobs()],
             log=log, timeout=3600)
    return build_executable(project / 'build', 'pcecd_snapshot_checks')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--card', type=Path, required=True, help="the player's own System Card (256 KiB)")
    parser.add_argument('--disc', type=Path, required=True, help='a disc: CHD (version 4 or 5) or ISO')
    parser.add_argument('--standard', action='store_true', help="the original System Card's RAM instead of the Super System Card's")
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--stride', type=int, default=20)
    parser.add_argument('--replay', type=int, default=24)
    parser.add_argument('--digests', action='store_true', help='print the digest of every 60th frame: the lines of two machines (Windows, Linux) must be the same')
    parser.add_argument('--native', type=Path, default=ASSETS / 'native', help='the native/ folder to build from')
    parser.add_argument('--keep', action='store_true', help='keep the work folder (the build is reused either way)')
    arguments = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    executable = build(WORK / 'project', arguments.native.resolve())
    sha = sha256_of(arguments.disc)
    command = [str(executable), '--disc', str(arguments.card), str(arguments.disc), sha, '--frames', str(arguments.frames), '--stride', str(arguments.stride),
               '--replay', str(arguments.replay)]
    if arguments.standard:
        command.append('--standard')
    if arguments.digests:
        command.append('--digests')
    done = subprocess.run(command, capture_output=True, text=True, timeout=7200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    print(done.stdout.rstrip())
    if done.stderr.strip():
        print(done.stderr.rstrip())
    good = done.returncode == 0 and done.stdout.rstrip().endswith('PASS')
    print(f'exit {done.returncode}: {"PASS" if good else "FAIL"}')
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
