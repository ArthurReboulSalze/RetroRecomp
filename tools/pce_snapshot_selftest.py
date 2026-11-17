"""The PC Engine snapshot's determinism probe (the multiplayer rollback contract, ROM-free): build and run native/pce_snapshot_checks.cpp.

    python -B tools/pce_snapshot_selftest.py [--keep]

It builds the probe the way a game is built (the pinned engine as a CMake subproject, the bridge `native/pce_machine.cpp` and the snapshot
`native/pce_snapshot.cpp`, the engine's no-module stub so every instruction runs on the interpreter), then runs it on two authored HuCards,
no commercial data: `pce_snapshot_rom.build_rom()` (the standard board; a program that keeps the VDC, its DMA, the raster and timer interrupts,
the PSG, the banks and block transfers busy) and a small program for the Street Fighter II board that cycles the bank latch.
For each, every frame of a first pass is a save point: the state is loaded back and the engine's own full checkpoint must equal the one
taken at the save, then the following frames must repeat the digest and the checkpoint of the first pass. It also checks that a save over
other bytes is the same save, that a load of a wrong size or of a damaged snapshot is refused and leaves the machine alone, and what the
digest reads and leaves out. The exit status is 0 only when both boards print PASS.

It says nothing of the native code (the translated code is proved against the interpreter apart), of speed (nothing here is timed), or of the
machine against hardware. Work folder: `.build/pce-snapshot-selftest` under the repository (kept with --keep; the build is reused).
"""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from retrorecomp.paths import ASSETS

WORK = ROOT / '.build' / 'pce-snapshot-selftest'


def sf2_rom() -> bytes:
    """A 2.5 MiB Street Fighter II board image: random filler in every bank (authored, seeded) and a program in bank 0 that writes the bank latch with
    each of its four values in turn, all the time, so a snapshot is taken with the window in any of its positions and with writes in flight."""
    import random
    image = bytearray(random.Random(0x5F2).randbytes(0x280000))
    code = bytes([
        0x78,                    # E000 SEI
        0xD4,                    # E001 CSH
        0xA2, 0x00,              # E002 LDX #0
        0x9D, 0xF0, 0xFF,        # E004 STA $FFF0,X   (the latch: offset $1FF0 + X of bank 0)
        0xE8,                    # E007 INX
        0xE0, 0x04,              # E008 CPX #4
        0xD0, 0x02,              # E00A BNE +2
        0xA2, 0x00,              # E00C LDX #0
        0xEE, 0x00, 0x20,        # E00E INC $2000     (work RAM: MPR1 is $F8 at reset)
        0x4C, 0x04, 0xE0,        # E011 JMP $E004
    ])
    image[:len(code)] = code
    image[0x1FFE:0x2000] = bytes([0x00, 0xE0])        # the reset vector: $E000
    return bytes(image)


def build(project: Path) -> Path:
    from retrorecomp import core
    from retrorecomp.pce_build import checkout_path, ensure_engine
    from retrorecomp.platforms import build_executable
    ensure_engine(print)
    engine = checkout_path().as_posix()
    native = (ASSETS / 'native').as_posix()
    project.mkdir(parents=True, exist_ok=True)
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPceSnapshotChecks LANGUAGES C CXX)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)',
        f'pce_add_native_module(PCE_MODULE MODULE "{engine}/runtime/src/no_module.cpp")',
        'get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)',
        'add_library(pce_module OBJECT ${PCE_MODULE_SOURCES})',
        'target_link_libraries(pce_module PUBLIC pce-runtime)',
        'set_target_properties(pce_module PROPERTIES CXX_EXTENSIONS OFF)',
        f'add_executable(pce_snapshot_checks "{native}/pce_snapshot_checks.cpp" "{native}/pce_machine.cpp" "{native}/pce_snapshot.cpp" $<TARGET_OBJECTS:pce_module>)',
        f'target_include_directories(pce_snapshot_checks PRIVATE "{native}")',
        'target_link_libraries(pce_snapshot_checks PRIVATE pce-runtime)',
    ]
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'pce_snapshot_checks', '--parallel', core.build_jobs()],
             log=log, timeout=3600)
    return build_executable(project / 'build', 'pce_snapshot_checks')


def run(executable: Path, rom: Path, label: str, *extra: str) -> bool:
    done = subprocess.run([str(executable), str(rom), *extra], capture_output=True, text=True, timeout=1800,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    print(done.stdout.rstrip())
    if done.stderr.strip():
        print(done.stderr.rstrip())
    print(f'{label}: exit {done.returncode}')
    return done.returncode == 0 and done.stdout.rstrip().endswith('PASS')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true', help='keep the work folder (the build is reused either way)')
    parser.parse_args()
    from pce_snapshot_rom import build_rom
    WORK.mkdir(parents=True, exist_ok=True)
    base, sf2 = WORK / 'base.pce', WORK / 'sf2.pce'
    base.write_bytes(build_rom())
    sf2.write_bytes(sf2_rom())
    executable = build(WORK / 'project')
    good = run(executable, base, 'base board')
    good = run(executable, sf2, 'sf2 board', '--sf2') and good
    print('PASS' if good else 'FAIL')
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
