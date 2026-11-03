"""Independent SM83 vectors (SingleStepTests/sm83) against the pinned runtime's interpreter and our RAM executor (gate G10).

`tools/fetch_sm83_vectors.py` caches the pinned corpus; this builds native/gb_sm83_vector_checks.c against the pinned runtime and
runs every vector that touches plain memory (about 404,000 of 500,000). The interpreter is the reference the conversion compares the
generated code with, so what it gets right here is what the lockstep comparison then carries to the translated code; the vectors do
not run the generated code itself. Results: `.build/gb-sm83-selftest/results.json`; `KNOWN` below lists each family that differs and why.

    python tools/gameboy_sm83_vector_selftest.py [--fetch]
"""
from pathlib import Path
import argparse
import gzip
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import _dependencies
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources
from retrorecomp.paths import ASSETS
import fetch_sm83_vectors as corpus

# The two families on which the runtime differs from the vectors, with the number of vectors that differ on each path (the corpus is
# pinned, so the numbers are exact) and why: both are conventions of the vector model. A new difference, or a changed number, fails
# the run. EI was a third until 1.6.7: the pinned runtime set IME when EI completed (865 vectors); gameboy_runtime.adapt_ei_delay
# now delays it by one instruction, as the vectors and Pan Docs have it.
KNOWN = {
    '10': {'interpreter': 872, 'ram_executor': 0, 'ram_dispatch': 0,
           'reason': 'STOP: the vectors count it as one byte and three machine cycles; the runtime skips its padding byte (two bytes, '
                     'the usual encoding: Pan Docs says normally two bytes with the second ignored, and lists a one-byte reading as one '
                     'of the possible behaviours) and does not model the low-power wait as cycles. A modelling convention of the '
                     'vectors, not a measured behaviour of the console.'},
    '76': {'interpreter': 897, 'ram_executor': 0, 'ram_dispatch': 0,
           'reason': 'HALT: the vectors give three machine cycles; the runtime spends four cycles on the instruction and then ticks '
                     'while the CPU is halted until an interrupt is flagged. Registers, memory and PC agree; only the cycle count of '
                     'a model that has no wake-up differs.'}}
# What the pinned corpus gives on each path (exact, since the corpus is pinned).
EXPECTED = {'interpreter': (404358, 402589), 'ram_executor': (51654, 51654), 'ram_dispatch': (58153, 58153)}
# The opcodes the RAM dispatch leaves to an interpreter session (the documented limit of the executors: HALT, STOP and RST).
LEFT_TO_THE_INTERPRETER = {'10', '76', 'c7', 'cf', 'd7', 'df', 'e7', 'ef', 'f7', 'ff'}


def build(project: Path) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes.fromhex('00 c3 50 01')     # an authored program; the runtime only needs a valid image
    (project / 'fixture.gb').write_bytes(rom)
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'sm83-fixture', '0' * 64, 'Authored SM83 vector fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(project, {})
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_sm83_vector_checks "{(ASSETS / 'native/gb_sm83_vector_checks.c').as_posix()}")
target_link_libraries(retro_gb_sm83_vector_checks PRIVATE gbrt)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'retro_gb_sm83_vector_checks',
         '--parallel', '4'], log=log, timeout=600)
    return build_executable(project / 'build', 'retro_gb_sm83_vector_checks')


def plain_vectors(source: Path, destination: Path) -> int:
    """The vectors on plain memory, without their `plain` column."""
    kept = 0
    with gzip.open(source, 'rt', encoding='ascii') as lines, destination.open('w', encoding='ascii', newline='\n') as out:
        for text in lines:
            family, index, plain, rest = text.split(' ', 3)
            if plain == '1':
                out.write(f'{family} {index} {rest}')
                kept += 1
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--fetch', action='store_true', help='fetch the corpus when it is not cached')
    args = parser.parse_args()
    cached = corpus.CACHE / corpus.REVISION / 'vectors.txt.gz'
    if not cached.is_file():
        if not args.fetch:
            raise SystemExit('The SM83 vectors are not cached: run tools/fetch_sm83_vectors.py (or pass --fetch).')
        corpus.fetch()
    manifest = json.loads((cached.parent / 'families.json').read_text(encoding='utf-8'))
    project = ROOT / '.build/gb-sm83-selftest'
    executable = build(project)
    vectors = project / 'vectors.txt'
    kept = plain_vectors(cached, vectors)
    output = run([executable, vectors], timeout=1800)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    names = manifest['families']
    result['revision'] = corpus.REVISION
    result['corpus_sha256'] = manifest['corpus_sha256']
    result['vectors_on_plain_memory'] = kept
    result['mismatching_families'] = [{**row, 'name': names[row['family']]} for row in result['mismatching_families']]
    result['ram_executor_not_handled'] = [{**row, 'name': names[row['family']]} for row in result['ram_executor_not_handled']]
    result['ram_dispatch_left_to_the_interpreter'] = [{**row, 'name': names[row['family']]}
                                                      for row in result['ram_dispatch_left_to_the_interpreter']]
    result['mismatch_examples'] = [line for line in output.splitlines() if line.startswith('MISMATCH')]
    unexplained = [row['name'] for row in result['mismatching_families']
                   if row['name'] not in KNOWN or any(row[path] != KNOWN[row['name']][path]
                                                      for path in ('interpreter', 'ram_executor', 'ram_dispatch'))]
    unexplained += [name for name in KNOWN if name not in {row['name'] for row in result['mismatching_families']}]
    unexplained += [f'{path}: {result[path]["run"]} run, {result[path]["matched"]} matched'
                    for path, (run_count, matched) in EXPECTED.items()
                    if (result[path]['run'], result[path]['matched']) != (run_count, matched)]
    left = {row['name'] for row in result['ram_dispatch_left_to_the_interpreter']}
    unexplained += sorted(left ^ LEFT_TO_THE_INTERPRETER)
    result['unexplained_families'] = unexplained
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('interpreter', 'ram_executor', 'ram_dispatch', 'unexplained_families')}), flush=True)
    return 1 if unexplained else 0


if __name__ == '__main__':
    sys.exit(main())
