"""Compare the machine with the cartridge's mapper number folded to a constant (RR_NES_STATIC_MAPPER) against the
original, on authored PPU, APU and register activity, NTSC and PAL, no ROMs."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.nes_machine import prepare_machine
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args

MAPPERS = (0, 1, 2, 4, 5, 69, 85, 153)
# (pal, zapper): the deferred NTSC clock without the Zapper, and the eager PAL clock with it
CONFIGS = ((0, 0), (1, 1))


def main():
    cmake, generator = toolchain()
    project = ROOT / '.build/nes-static-mapper-selftest'
    folder = project / 'machine'
    folder.mkdir(parents=True, exist_ok=True)
    machine = prepare_machine(folder, ROOT / '.deps/nesrecomp')
    (folder / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
    source = f'''cmake_minimum_required(VERSION 3.20)
project(NesStaticMapperChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c" "${{NESRECOMP_CYC_DIR}}/hw_machine.c" "${{NESRECOMP_CYC_DIR}}/hw_ppu.c" "${{NESRECOMP_CYC_DIR}}/hw_apu.c")
'''
    variants = [('dynamic', None)] + [(f'static{mapper}', mapper) for mapper in MAPPERS]
    for pal, zapper in CONFIGS:
        for name, mapper in variants:
            target = f'{name}_{pal}{zapper}'
            definitions = f'RR_NES_PAL={pal} RR_NES_ZAPPER={zapper} RR_NES_FAST_PPU=1'
            if mapper is not None:
                definitions += f' RR_NES_STATIC_MAPPER={mapper}'
            source += f'''add_executable({target} ${{NESRECOMP_CYC_SOURCES}} "{machine.as_posix()}/hw_machine.c" "{machine.as_posix()}/hw_ppu.c" "{machine.as_posix()}/hw_apu.c" "{ROOT.as_posix()}/native/nes_ppu_checks.c" "{ROOT.as_posix()}/native/platform_io.c")
target_include_directories({target} PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} "{machine.as_posix()}" "{ROOT.as_posix()}/native" "{folder.as_posix()}")
target_compile_definitions({target} PRIVATE _CRT_SECURE_NO_WARNINGS {definitions})
target_link_libraries({target} PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
'''
    (project / 'CMakeLists.txt').write_text(source, encoding='utf-8')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    results = []
    for pal, zapper in CONFIGS:
        for mapper in MAPPERS:
            traces = []
            for name in ('dynamic', f'static{mapper}'):
                text = run([build_executable(project / 'build', f'{name}_{pal}{zapper}'), str(mapper)], timeout=240)
                traces.append(text.splitlines())
            if len(traces[0]) != 2800 or traces[0] != traces[1]:
                first = next((i for i, pair in enumerate(zip(*traces)) if pair[0] != pair[1]), -1)
                raise RuntimeError(f'Static mapper mismatch: PAL={pal}, Zapper={zapper}, mapper={mapper}, checkpoint={first}')
            result = dict(pal=pal, zapper=zapper, mapper=mapper, checkpoints=2800, identical=True)
            print(json.dumps(result), flush=True)
            results.append(result)
    (project / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
