"""Independent HuC6280 vectors (SingleStepTests/huc6280) against the pinned engine's interpreter (gate G10).

`tools/fetch_huc6280_vectors.py` caches the pinned corpus (640,000 vectors, 2,500 per opcode); this builds
native/pce_huc6280_vector_checks.cpp against the pinned runtime (`pce-runtime`) and replays every vector. The interpreter is the
reference the conversion compares the generated code with, so what it gets right here is what the lockstep comparison then carries
to the translated code; the vectors do not run the generated code itself. The oracle is another emulator's output (Mesen), not
silicon. Results: `.build/pce-huc6280-selftest/results.json`; `KNOWN` below lists each opcode that differs and why.

    python tools/pce_huc6280_vector_selftest.py [--fetch]
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from retrorecomp.paths import ASSETS
import fetch_huc6280_vectors as corpus

# The opcodes on which the pinned engine differs from the vectors, with the number of vectors that differ on each (the corpus is
# pinned, so the numbers are exact) and why. A new difference, or a changed number, fails the run.
KNOWN = {
    '03': {'cycles': 2500, 'reason': 'ST0: the engine adds a fixed wait for the VDC (5 cycles); the vectors give 4. State agrees.'},
    '13': {'cycles': 2500, 'reason': 'ST1: as ST0 (5 cycles against 4). State agrees.'},
    '23': {'cycles': 2500, 'reason': 'ST2: as ST0 (5 cycles against 4). State agrees.'},
    '04': {'flags': 254, 'reason': 'TSB zp: the Z flag. The engine tests the memory byte, the vectors the accumulator and the byte.'},
    '0C': {'flags': 250, 'reason': 'TSB abs: as TSB zp.'},
    '14': {'flags': 496, 'reason': 'TRB zp: as TSB zp.'},
    '1C': {'flags': 492, 'reason': 'TRB abs: as TSB zp.'},
    '43': {'registers': 13, 'reason': 'TMA with mask 0: the instruction reads the transfer latch, which the vectors do not carry; the '
                                      'engine returns its deterministic 0.'},
}
# The 22 reserved opcodes the engine stops on by design (they are never executed as NOPs); the vectors give them as 2-cycle NOPs.
REFUSED = {'0B', '1B', '2B', '33', '3B', '4B', '5B', '5C', '63', '6B', '7B', '8B', '9B', 'AB', 'BB', 'CB', 'DB', 'DC', 'E2', 'EB',
           'FB', 'FC'}
# What the pinned corpus gives in all (exact, since the corpus is pinned).
EXPECTED = {'vectors': 640000, 'executed': 585000, 'refused': 55000, 'faulted': 0, 'not_comparable': 12481, 'both_equal': 563514,
            'state_equal': 571014, 'cycles_equal': 577500, 'cycles_different': 7500}


def build(project: Path) -> Path:
    from retrorecomp import core
    from retrorecomp.pce_build import checkout_path, ensure_engine
    from retrorecomp.platforms import build_executable
    ensure_engine(print)
    project.mkdir(parents=True, exist_ok=True)
    engine = checkout_path().as_posix()
    source = (ASSETS / 'native/pce_huc6280_vector_checks.cpp').as_posix()
    (project / 'CMakeLists.txt').write_text('\n'.join([
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPceVectors LANGUAGES C CXX)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)',
        # No module: the interpreter is what is measured (the engine's own probes link its empty module the same way).
        f'add_executable(retro_pce_huc6280_vector_checks "{source}" "{engine}/runtime/src/no_module.cpp")',
        'target_link_libraries(retro_pce_huc6280_vector_checks PRIVATE pce-runtime)', '']), encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'retro_pce_huc6280_vector_checks',
              '--parallel', core.build_jobs()], log=log, timeout=1800)
    return build_executable(project / 'build', 'retro_pce_huc6280_vector_checks')


def judge(rows: list[dict]) -> tuple[dict, list[str]]:
    """The totals of the per-opcode rows and what is not explained by KNOWN, REFUSED and EXPECTED."""
    totals = {key: sum(row[key] for row in rows) for key in
              ('vectors', 'executed', 'refused', 'faulted', 'not_comparable', 'state_equal', 'both_equal', 'registers', 'flags',
               'pc', 'mpr', 'memory', 'cycles_equal', 'cycles_different')}
    unexplained = []
    seen = set()
    for row in rows:
        opcode = row['opcode']
        differs = {key: row[key] for key in ('registers', 'flags', 'pc', 'mpr', 'memory', 'cycles_different') if row[key]}
        refused = row['refused'] == row['vectors']
        if (opcode in REFUSED) != refused or row['refused'] not in (0, row['vectors']):
            unexplained.append(f'{opcode}: refused {row["refused"]} of {row["vectors"]}')
        if row['faulted']:
            unexplained.append(f'{opcode}: {row["faulted"]} faults')
        if differs:
            known = KNOWN.get(opcode)
            wanted = {('cycles_different' if key == 'cycles' else key): value
                      for key, value in (known or {}).items() if key != 'reason'}
            if wanted != differs:
                unexplained.append(f'{opcode}: differs {differs}, known {wanted}')
            seen.add(opcode)
    unexplained += [f'{opcode}: known difference not seen' for opcode in sorted(set(KNOWN) - seen)]
    unexplained += [f'{key}: {totals[key]}, expected {value}' for key, value in EXPECTED.items() if totals[key] != value]
    if len(rows) != corpus.FILES:
        unexplained.append(f'{len(rows)} opcode files, expected {corpus.FILES}')
    return totals, unexplained


def main():
    from retrorecomp import core
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--fetch', action='store_true', help='fetch the corpus when it is not cached')
    args = parser.parse_args()
    if not corpus.cached():
        if not args.fetch:
            raise SystemExit('The HuC6280 vectors are not cached: run tools/fetch_huc6280_vectors.py (or pass --fetch).')
        corpus.fetch()
    project = ROOT / '.build/pce-huc6280-selftest'
    executable = build(project)
    output = core.run([executable, corpus.folder()], timeout=3600)
    (project / 'checks.log').write_text(output, encoding='utf-8')
    rows = [json.loads(line) for line in output.splitlines() if line.startswith('{"opcode"')]
    totals, unexplained = judge(rows)
    result = {'revision': corpus.REVISION, 'corpus_sha256': corpus.CORPUS_SHA256, 'oracle': 'Mesen (expectations, not hardware)',
              'totals': totals, 'known': KNOWN, 'refused_by_design': sorted(REFUSED), 'unexplained': unexplained, 'opcodes': rows}
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'totals': totals, 'unexplained': unexplained}), flush=True)
    return 1 if unexplained else 0


if __name__ == '__main__':
    sys.exit(main())
