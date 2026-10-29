"""Run authored APU regressions and upstream PPU/APU/DMA checks, without ROMs."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import _dependencies
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources


def main():
    project = ROOT / '.build/gb-hardware-20261011'
    project.mkdir(parents=True, exist_ok=True)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    rom = bytearray(32768)
    rom[0x100:0x103] = bytes.fromhex('c3 00 01')
    (project / 'fixture.gb').write_bytes(rom)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'hardware-fixture', '0' * 64, 'Authored hardware fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(project, {})   # the ELF counterpart of the .rc on Linux; nothing on Windows
    checks = {'rr_gb_audio': ROOT / 'native/gb_audio_checks.c',
              'rr_gb_ppu': engine / 'tests/test_ppu_dot_timing.c',
              'rr_gb_audio_chunks': engine / 'tests/test_audio_chunk_invariance.c',
              'rr_gb_dma': engine / 'tests/test_oam_dma_bus.c'}
    (project / 'no_guest_cpu.c').write_text(
        '#include "gbrt.h"\n#include <stdlib.h>\n'
        'void gb_dispatch(GBContext* ctx, uint16_t addr) { (void)ctx; (void)addr; abort(); }\n',
        encoding='utf-8')
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        for name, source in checks.items():
            stub = '' if name == 'rr_gb_audio' else ' no_guest_cpu.c'
            out.write(f'\nadd_executable({name} "{source.as_posix()}"{stub})\n'
                      f'target_link_libraries({name} PRIVATE gbrt)\n')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    audio = project / 'runtime/src/audio.c'
    adapted = audio.read_bytes()
    # Demonstrate the same fixture fails on the pristine upstream APU.
    try:
        shutil.copyfile(engine / 'runtime/src/audio.c', audio)
        run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'rr_gb_audio',
             '--parallel', '4'], log=log, timeout=600)
        baseline = subprocess.run([build_executable(project / 'build', 'rr_gb_audio')],
                                  capture_output=True, text=True, timeout=60)
        (project / 'baseline.log').write_text(baseline.stdout + baseline.stderr, encoding='utf-8')
    finally:
        audio.write_bytes(adapted)
    assert baseline.returncode == 1, baseline.stdout + baseline.stderr
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', *checks,
         '--parallel', '4'], log=log, timeout=600)
    results = {}
    for name in checks:
        output = run([build_executable(project / 'build', f'{name}')], timeout=60)
        (project / f'{name}.log').write_text(output, encoding='utf-8')
        results[name] = {'passed': True, 'output': output.strip()}
        print(name, output.strip() or 'PASS', flush=True)
    (project / 'results.json').write_text(json.dumps(
        {'baseline': baseline.stdout + baseline.stderr, 'adapted': results,
         'rom_free': True, 'hardware_accuracy_certified': False}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
