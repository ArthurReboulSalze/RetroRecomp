"""Compare optimized and original PPU/APU clocks on authored activity, no ROMs."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.nes_machine import prepare_machine
from smsrecomp.platforms import build_executable, build_jobs, cmake_target_args


def main():
    cmake, generator = toolchain()
    project = ROOT / '.build/nes-ppu-selftest'
    machines = {}
    for variant, optimized in (('baseline', False), ('optimized', True)):
        folder = project / variant
        folder.mkdir(parents=True, exist_ok=True)
        machines[variant] = prepare_machine(folder, ROOT / '.deps/nesrecomp',
                                            fast_ppu=optimized, fast_audio=optimized)
        (folder / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
    baseline = machines['baseline']
    source = f'''cmake_minimum_required(VERSION 3.20)
project(NesPpuChecks C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
include("{baseline.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c" "${{NESRECOMP_CYC_DIR}}/hw_machine.c" "${{NESRECOMP_CYC_DIR}}/hw_ppu.c" "${{NESRECOMP_CYC_DIR}}/hw_apu.c")
'''
    # The Zapper keeps the eager PPU clock; without it, mappers 0 and 2 also
    # exercise the deferred clock (nes_ppu_lazy.inc).
    configs = ((0, 1), (1, 1), (0, 0))
    for pal, zapper in configs:
        config = f'{pal}{zapper}'
        source += f'''add_library(common{config} OBJECT ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/platform_io.c")
target_include_directories(common{config} PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} "{ROOT.as_posix()}/native" "{project.as_posix()}/baseline")
target_compile_definitions(common{config} PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL={pal} RR_NES_ZAPPER={zapper})
'''
        for variant, machine in machines.items():
            name = f'{variant}{config}'
            source += f'''add_executable({name} "{machine.as_posix()}/hw_machine.c" "{machine.as_posix()}/hw_ppu.c" "{machine.as_posix()}/hw_apu.c" "{ROOT.as_posix()}/native/nes_ppu_checks.c" $<TARGET_OBJECTS:common{config}>)
target_include_directories({name} PRIVATE "{machine.as_posix()}" "{ROOT.as_posix()}/native" "{project.as_posix()}/{variant}")
target_compile_definitions({name} PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL={pal} RR_NES_ZAPPER={zapper} RR_NES_FAST_PPU={int(variant == 'optimized')})
target_link_libraries({name} PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
'''
    (project / 'CMakeLists.txt').write_text(source, encoding='utf-8')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()],
        log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()],
        log=project / 'build.log')
    results = []
    for pal, zapper in configs:
        config = f'{pal}{zapper}'
        for mapper in (0, 1, 2, 4, 5, 69, 85, 153):
            traces = []
            for variant in machines:
                text = run([build_executable(project / 'build', f'{variant}{config}'), str(mapper)], timeout=240)
                (project / f'{variant}-{config}-{mapper}.txt').write_text(text, encoding='ascii')
                traces.append(text.splitlines())
            if len(traces[0]) != 2800 or traces[0] != traces[1]:
                first = next((i for i, pair in enumerate(zip(*traces)) if pair[0] != pair[1]), -1)
                raise RuntimeError(f'PPU mismatch: PAL={pal}, Zapper={zapper}, mapper={mapper}, checkpoint={first}; traces in {project}')
            result = dict(pal=pal, zapper=zapper, mapper=mapper, alignments=4, checkpoints=2800,
                          hidden_ppu_apu_frame_bus_pcm_match=True)
            print(json.dumps(result), flush=True)
            results.append(result)
        # Host-only extra sprites (F5): deferred (Zapper off) and eager clocks.
        text = run([build_executable(project / 'build', f'optimized{config}'), '0', 'extra'], timeout=240)
        if 'PASS' not in text:
            raise RuntimeError(f'Extra sprite check failed: PAL={pal}, Zapper={zapper}: {text}')
        results.append(dict(pal=pal, zapper=zapper, extra_sprites=True, passed=True))
        print(json.dumps(results[-1]), flush=True)
    (project / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='ascii')


if __name__ == '__main__':
    main()
