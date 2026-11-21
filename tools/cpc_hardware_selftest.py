"""The Amstrad CPC's CRTC, Gate Array and PPI with its keyboard (native/cpc_machine), stepped one character at a time (needs a C compiler).

    python -B tools/cpc_hardware_selftest.py

Builds `native/cpc_machine/cpc_hardware_checks.c` with the three chips and runs it: the firmware's 50 Hz frame (64 x 312
characters, 40 x 200 displayed, the HSYNC and VSYNC widths), the screen addresses (C000h, its lines, its rows), what differs by
CRTC type (when R12/R13 are taken, the VSYNC width, the registers read back, type 1's status), the 300 Hz interrupt with its
VSYNC phase and acknowledge, the pixels of each mode and the 27 colours, the 6128's RAM configurations, the picture of a known
screen (border, display window, a byte changed), the AY written through the PPI and the keyboard and joystick rows read back as
the firmware scans them, and the board through its 16-bit ports: the memory map with the ROMs, AMSDOS and the RAM
configurations, a sector read through FB7Fh, the frames and interrupts in T-states; and the boot key sequence
(native/hostkit/adapters/rrhk_boot_keys.h) of Bomb Jack's RUN"BOMB, written by retrorecomp/cpc_keys.py, read back through the
CPC's key matrix: every key once, the shifted ", two equal letters as two, a key the player holds kept apart; and the AY
through the PPI and its sound (A left, C right, B on both, a 553 Hz tone's pitch, the same samples whatever the steps); and the board's state (save, run, load, the same run again; damaged states refused;
the frame count in the digest). It says nothing about the Z80, the firmware or a game: those are the conversions' checks.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args


def run_checks(project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'cpc-hardware-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native' / 'cpc_machine').as_posix()
    upd765 = (ROOT / 'native' / 'upd765').as_posix()
    adapters = (ROOT / 'native' / 'hostkit' / 'adapters').as_posix()
    ay = (ROOT / 'native' / 'ay38910').as_posix()
    from retrorecomp.cpc_keys import boot_keys_header
    (project / 'boot_keys.h').write_text(boot_keys_header('RUN"BOMB\n', start_frame=10), encoding='utf-8', newline='\n')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroCpcHardware C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/cpc_hardware_checks.c" "{native}/cpc_crtc.c" "{native}/cpc_gate_array.c" "{native}/cpc_ppi.c"
               "{native}/cpc_machine.c" "{native}/cpc_state.c" "{upd765}/upd765.c" "{upd765}/dsk_image.c" "{ay}/ay38910.c")
target_include_directories(checks PRIVATE "{native}" "{upd765}" "{adapters}" "{ay}" "{(ROOT / 'native').as_posix()}" "{project.as_posix()}")
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log', timeout=600)
    output = run([build_executable(project / 'build', 'checks')], timeout=60)
    return json.loads(next(line for line in output.splitlines() if line.startswith('{')))


def main() -> int:
    result = run_checks()
    print(f'{result["passed"]} checks passed, {result["failed"]} failed')
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
