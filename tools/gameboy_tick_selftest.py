"""Compare the inline gb_tick path of the generated Game Boy code with the real gb_tick of the pinned runtime."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import _dependencies
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources
from retrorecomp.paths import ASSETS


def main():
    project = ROOT / '.build/gb-tick-selftest'
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')     # an authored program: NOP, JP 0150; the runtime only needs a valid image
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'tick-fixture', '0' * 64, 'Authored tick fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(project, {})
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_tick_checks "{(ASSETS / 'native/gb_tick_checks.c').as_posix()}")
target_link_libraries(retro_gb_tick_checks PRIVATE gbrt)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'retro_gb_tick_checks',
         '--parallel', '4'], log=log, timeout=600)
    output = run([build_executable(project / 'build', 'retro_gb_tick_checks')], timeout=600)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
