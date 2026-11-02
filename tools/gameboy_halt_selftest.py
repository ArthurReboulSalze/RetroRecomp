"""The mode 3 bound of the halted fast-forward (1.6.7) against the pinned runtime without it: the state after every slice must be the same.

native/gb_halt_checks.c runs a program that waits in HALT, in short random slices, on random video memory, sprites, scroll and window, with an
interrupt source that wakes the CPU on a different PPU event in each variant, and writes a digest of the whole state after every slice. The
runtime is built twice from the same generated project, once as the converter adapts it and once without the bound
(`adapt_generated_project(..., halt_mode3_bound=False)`), and the two traces must be identical line by line, except for the two columns of the
sound unit's samples, which are compared on their own: the moment the pinned runtime hands samples out depends on how its ticks are cut.
The build with the bound must take long steps inside mode 3 and the other none, so that an equal result is not an empty one.
"""
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


def build(project: Path, bound: bool) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')     # an authored program; the runtime only needs a valid image
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'halt-fixture', '0' * 64, 'Authored halt fixture', halt_mode3_bound=bound)
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(project, {})
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_halt_checks "{(ASSETS / 'native/gb_halt_checks.c').as_posix()}")
target_link_libraries(retro_gb_halt_checks PRIVATE gbrt)
target_link_options(retro_gb_halt_checks PRIVATE -Wl,--wrap=ppu_tick)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'retro_gb_halt_checks',
         '--parallel', '4'], log=log, timeout=600)
    return build_executable(project / 'build', 'retro_gb_halt_checks')


def trace_of(project: Path, bound: bool) -> tuple[list[list[str]], dict]:
    executable = build(project, bound)
    trace = project / 'trace.txt'
    output = run([executable, trace], timeout=1800)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    summary = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    return [line.split() for line in trace.read_text(encoding='ascii').splitlines()], summary


def main():
    with_bound, summary_with = trace_of(ROOT / '.build/gb-halt-selftest/with-bound', True)
    without, summary_without = trace_of(ROOT / '.build/gb-halt-selftest/without-bound', False)
    assert len(with_bound) == len(without), (len(with_bound), len(without))
    # columns: variant, slice, cycles, frame end, digest of the state, samples so far, hash of the samples
    state_differences = [i for i, (x, y) in enumerate(zip(with_bound, without)) if x[:5] != y[:5]]
    frame_ends = [i for i, row in enumerate(with_bound) if row[3] == '1']
    sample_differences = [i for i in frame_ends if with_bound[i][5:] != without[i][5:]]
    result = {'slices': len(with_bound), 'state_differences': len(state_differences),
              'first_state_difference': state_differences[0] if state_differences else None,
              'frame_ends': len(frame_ends), 'frame_ends_with_other_samples': len(sample_differences),
              'with_bound': summary_with, 'without_bound': summary_without}
    assert summary_with['long_steps_inside_mode3'] > 0 and summary_without['long_steps_inside_mode3'] == 0, result
    assert summary_with['ei_and_halt_checks'] == summary_without['ei_and_halt_checks'] == 3, result      # EI and the dispatch, EI ; HALT
    assert not state_differences, result
    (ROOT / '.build/gb-halt-selftest/results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
