"""The PPU's batched drawing of a line with sprites (native/gb_ppu_object_span.h) against the pinned runtime's own one-dot-at-a-time drawing.

native/gb_ppu_span_checks.c runs a halted program and a host that writes the video memory, the sprite table and the registers of the video unit at random in
the middle of the lines (sprites at every x, 8x8 and 8x16, flipped, behind the background, the window at every WX, scroll, objects on and off) and prints a
hash of the whole picture after every frame, folded into one value. This tool builds that program twice, with the runtime as the converter adapts it ("new")
and with the same runtime and the pinned ppu.c as it is ("pinned": the dot path), runs both on several seeds and requires the same value from both.

    python -B tools/gameboy_ppu_span_selftest.py [--frames N] [--seeds A,B,C]    (writes .build/gb-ppu-span-selftest/results.json)
"""
from pathlib import Path
import json
import shutil
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import _dependencies
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources
from retrorecomp.paths import ASSETS

WORK = ROOT / '.build/gb-ppu-span-selftest'


def build(variant: str) -> Path:
    """`new`: the runtime as adapt_generated_project leaves it; `pinned`: the same with the pinned ppu.c in place of the adapted one."""
    folder = WORK / variant
    folder.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')     # an authored program; the runtime only needs a valid image
    (folder / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = folder / 'build.log'
    run([compiler, folder / 'fixture.gb', '-o', folder, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(folder, 'span-fixture', '0' * 64, 'Authored PPU span fixture')
    if variant == 'pinned':
        shutil.copyfile(engine / 'runtime/src/ppu.c', folder / 'runtime/src/ppu.c')
    (folder / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(folder, {})
    with (folder / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_ppu_span_checks "{(ASSETS / 'native/gb_ppu_span_checks.c').as_posix()}")
target_link_libraries(retro_gb_ppu_span_checks PRIVATE gbrt)
''')
    run([cmake, '-S', folder, '-B', folder / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', folder / 'build', '--config', 'Release', '--target', 'retro_gb_ppu_span_checks',
         '--parallel', '4'], log=log, timeout=900)
    return build_executable(folder / 'build', 'retro_gb_ppu_span_checks')


def main():
    frames = int(sys.argv[sys.argv.index('--frames') + 1]) if '--frames' in sys.argv else 600
    seeds = sys.argv[sys.argv.index('--seeds') + 1].split(',') if '--seeds' in sys.argv else ['1', '2', '3', '4', '5']
    executables = {variant: build(variant) for variant in ('pinned', 'new')}
    results = []
    for seed in seeds:
        values = {}
        for variant, executable in executables.items():
            output = run([executable, str(frames), seed], timeout=1800)
            values[variant] = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
        same = values['pinned'] == values['new']
        results.append({'seed': seed, 'equal': same, 'pinned': values['pinned'], 'new': values['new']})
        print(('equal ' if same else 'DIFFERENT ') + json.dumps(values['new']), flush=True)
    (WORK / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if all(entry['equal'] for entry in results) else 1)


if __name__ == '__main__':
    main()
