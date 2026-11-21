"""The colour hardware of the Game Boy engine against the register pages of Pan Docs (native/gbc_hardware_checks.c).

An authored program and a host that drives the registers the way a game does: the seven work-RAM banks, the second video bank, the palette ports and
their auto-increment, the general-purpose and the horizontal-blank HDMA, the speed switch and the length of a frame in double speed, the registers that read as 1
in colour mode. The runtime is the one the converter adapts for the Color (`adapt_generated_project(..., variant=COLOR)`). The expectations are documentation: this
shows what the engine does, not what a console does (hardware fidelity stays unproved).

    python -B tools/gameboy_color_selftest.py        (writes .build/gb-color-selftest/results.json)
"""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import COLOR, _dependencies
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources
from retrorecomp.paths import ASSETS

WORK = ROOT / '.build/gb-color-selftest'


def build() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')     # an authored program; the runtime only needs a valid image
    rom[0x143] = 0x80
    (WORK / 'fixture.gbc').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = WORK / 'build.log'
    run([compiler, WORK / 'fixture.gbc', '-o', WORK, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(WORK, 'color-fixture', '0' * 64, 'Authored colour fixture', variant=COLOR)
    (WORK / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(WORK, {})
    with (WORK / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gbc_hardware_checks "{(ASSETS / 'native/gbc_hardware_checks.c').as_posix()}")
target_link_libraries(retro_gbc_hardware_checks PRIVATE gbrt)
''')
    run([cmake, '-S', WORK, '-B', WORK / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', WORK / 'build', '--config', 'Release', '--target', 'retro_gbc_hardware_checks',
         '--parallel', '4'], log=log, timeout=900)
    return build_executable(WORK / 'build', 'retro_gbc_hardware_checks')


def main():
    executable = build()
    output = run([executable], timeout=600)
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    (WORK / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
