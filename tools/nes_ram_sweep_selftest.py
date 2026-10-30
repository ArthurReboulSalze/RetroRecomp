"""The end-of-run sweep of RAM code: authored routines with paths a run did not take (no ROM)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.nes_machine import prepare_machine
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args


def main():
    cmake, generator = toolchain()
    project = ROOT / '.build/nes-ram-sweep-selftest'
    project.mkdir(parents=True, exist_ok=True)
    machine = prepare_machine(project, ROOT / '.deps/nesrecomp')
    (project / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesRamSweepChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_executable(checks ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/nes_ram_sweep_checks.c" "{ROOT.as_posix()}/native/platform_io.c")
target_include_directories(checks PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} "{ROOT.as_posix()}/native" "{project.as_posix()}")
target_compile_definitions(checks PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL=0 RR_NES_ZAPPER=0)
target_link_libraries(checks PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    print(run([build_executable(project / 'build', 'checks')], timeout=120).strip())


if __name__ == '__main__':
    main()
