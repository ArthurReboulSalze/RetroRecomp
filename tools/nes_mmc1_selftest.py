"""Compare the MMC1 with the PPU A12 rebuild skipped against the original, on authored register and A12 activity."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.nes_machine import prepare_machine
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args

# (mapper, submapper, PRG units of 16 KiB, CHR units of 8 KiB (0 = CHR RAM), NES 2.0 PRG RAM size shift)
BOARDS = (
    (1, 0, 8, 0, 7),     # 128 KiB, CHR RAM, 8 KiB work RAM
    (1, 0, 8, 16, 0),    # 128 KiB, 128 KiB CHR ROM, no work RAM
    (1, 0, 8, 16, 7),    # CHR ROM and 8 KiB work RAM (the SNROM RAM enable on CHR bit 4 does not apply)
    (1, 0, 8, 0, 8),     # 16 KiB work RAM (bank on CHR bit 3)
    (1, 0, 8, 0, 9),     # 32 KiB work RAM (bank on CHR bits 2-3)
    (1, 0, 16, 0, 7),    # 256 KiB
    (1, 0, 32, 0, 7),    # 512 KiB: outer PRG bank on CHR bit 4
    (1, 0, 32, 0, 9),    # 512 KiB and 32 KiB work RAM
    (1, 3, 8, 0, 7), (1, 5, 2, 4, 0), (1, 7, 8, 16, 0),
    (155, 0, 8, 0, 7), (155, 0, 8, 16, 0),
)


def build(project: Path, machine: Path, cmake, generator) -> Path:
    (project / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesMmc1Checks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_executable(checks ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/nes_mmc1_checks.c" "{ROOT.as_posix()}/native/platform_io.c")
target_include_directories(checks PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} "{ROOT.as_posix()}/native" "{project.as_posix()}")
target_compile_definitions(checks PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL=0 RR_NES_ZAPPER=0)
target_link_libraries(checks PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    return build_executable(project / 'build', 'checks')


def main():
    cmake, generator = toolchain()
    base = ROOT / '.build/nes-mmc1-selftest'
    executables = {}
    for variant, fast in (('original', False), ('skipped', True)):
        project = base / variant
        project.mkdir(parents=True, exist_ok=True)
        machine = prepare_machine(project, ROOT / '.deps/nesrecomp', fast_mmc1=fast)
        executables[variant] = build(project, machine, cmake, generator)
    results = []
    for board in BOARDS:
        outputs = [run([executables[variant], *map(str, board)], timeout=240).splitlines()
                   for variant in ('original', 'skipped')]
        if len(outputs[0]) < 10000 or outputs[0] != outputs[1]:
            first = next((i for i, pair in enumerate(zip(*outputs)) if pair[0] != pair[1]), -1)
            raise RuntimeError(f'MMC1 mismatch on board {board}, line {first} of {len(outputs[0])}/{len(outputs[1])}')
        result = dict(board=board, steps=len(outputs[0]) - 1, identical=True)
        print(json.dumps(result), flush=True)
        results.append(result)
    (base / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
