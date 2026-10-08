"""Run authored NTSC/PAL clock, APU, Zapper and state regressions (no ROMs)."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.nes_machine import prepare_machine

def main():
    cmake, generator = toolchain()
    project = ROOT / '.build/nes-machine-selftest'
    machine = prepare_machine(project, ROOT / '.deps/nesrecomp')
    (project / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesMachineChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
foreach(pal 0 1)
add_executable(checks${{pal}} ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/nes_machine_checks.c")
target_include_directories(checks${{pal}} PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} "{ROOT.as_posix()}/native" "{project.as_posix()}")
target_compile_definitions(checks${{pal}} PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL=${{pal}} RR_NES_ZAPPER=1)
target_link_libraries(checks${{pal}} PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
endforeach()
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    results = []
    for pal in (0, 1):
        for mapper in (0, 1, 2, 4, 85):
            output = run([project / f'build/Release/checks{pal}.exe', str(mapper)])
            print(output, flush=True)
            results.append(json.loads(output))
    (project / 'results.json').write_text(json.dumps(results, indent=2) + '\n')

if __name__ == '__main__':
    main()
