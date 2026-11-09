"""Independent HuC6280 vectors (SingleStepTests/huc6280) against the pinned engine's translated (native) code (gate G10).

The interpreter tier (`tools/pce_huc6280_vector_selftest.py`) replays the whole corpus. This tool does the same for the code the
engine's emitter translates, on a selection of it: for each opcode the emitter translates, the first 40 usable vectors (corpus
order). A vector is usable when its mapping can be moved to a canonical one without changing what it means (eight pairwise
distinct pages, unchanged by the instruction, all of its cells inside them), it is not cut by the corpus cap, and its instruction
bytes form a guarded site. Each usable vector becomes one entry of a snapshot; the engine's own `analysis.analyze` and
`emitter.emit` turn the snapshot into a guarded native module, built here like the converter builds a game's module (the pinned
engine as a CMake subproject, `pce_add_native_module`). The module is then asked to execute every case, and the interpreter the
same, on the same flat bus; each is compared with the vector and with the other.

What it says: the translated code agrees with the vectors wherever the interpreter does, and with the interpreter on every case
(registers, flags, pc, mapping, cycles, ticks, memory); a guard that misses, an opcode the module does not translate or a fault is
a failure. What it does not say: the selection is 40 vectors per opcode, not 2,500, so it shows the emitter agrees with the
interpreter on those operands, not on every one; each case runs at the guarded mapping, which the selection keeps unchanged
(TAM and TMA are left to the interpreter tier); the oracle is another emulator's output (Mesen), not silicon.
Results: `.build/pce-huc6280-native-selftest/results.json`; `KNOWN` below lists each opcode that differs from the vectors and why
(the interpreter's own differences, pinned in `pce_huc6280_vector_selftest.KNOWN`).

The default sample is 40 usable vectors per opcode (about 9,100 cases, minutes). `--per-opcode 250` runs a larger one, 250 per
opcode: its cases are a superset of the default's (the first 40 usable vectors of an opcode are the first 40 of its first 250), it
builds about six times as many modules, and it has its own pinned counts (`LARGE`) and its own folder; the default stays what the
quick check runs.

    python tools/pce_huc6280_native_vector_selftest.py [--fetch] [--per-opcode 40|250]
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from retrorecomp.paths import ASSETS
import fetch_huc6280_vectors as corpus
import pce_huc6280_vector_selftest as interpreter

CANONICAL = tuple(range(0x20, 0x28))   # the mapping every case runs at: eight RAM pages of the flat bus, physical 0x40000-0x4FFFF
PER_OPCODE = 40                        # usable vectors kept per opcode, in corpus order
MODULE_SITES = 1200                    # sites per module at most (modules compile in parallel); the cap is part of the selection
CORPUS_CAP = 500                       # cycles the corpus records per vector at most: a vector that reaches it is cut
CLASSES = ('registers', 'flags', 'pc', 'mpr', 'memory')
# Why a vector is not used (the first reason that holds, in this order), counted over the vectors read to find the 40 of each opcode.
REASONS = ('TAM/TMA change or read the MPR latch', 'cut by the generator cap', 'MPR values not pairwise distinct',
           'cannot form a guarded site')

# The opcodes on which the translated code differs from the vectors, with the number of cases that differ on each and why: the
# interpreter's own differences (TMA is not in the selection). A new difference, or a changed number, fails the run.
KNOWN = {
    '03': {'cycles': 40, 'reason': interpreter.KNOWN['03']['reason']},
    '13': {'cycles': 40, 'reason': interpreter.KNOWN['13']['reason']},
    '23': {'cycles': 40, 'reason': interpreter.KNOWN['23']['reason']},
    '04': {'flags': 1, 'reason': interpreter.KNOWN['04']['reason']},
    '0C': {'flags': 3, 'reason': interpreter.KNOWN['0C']['reason']},
    '14': {'flags': 9, 'reason': interpreter.KNOWN['14']['reason']},
    '1C': {'flags': 13, 'reason': interpreter.KNOWN['1C']['reason']},
}
# What the pinned corpus and the pinned engine give in all (exact: the corpus and the emitter are pinned, the selection is
# deterministic).
EXPECTED = {'cases': 9097, 'executed': 9097, 'not_executed': 0, 'state_equal': 9071, 'both_equal': 8951, 'registers': 0,
            'flags': 26, 'pc': 0, 'mpr': 0, 'memory': 0, 'cycles_different': 120, 'native_vs_interpreter_different': 0}
EXPECTED_OPCODES = 231                 # opcodes with at least one case: the 234 the emitter translates less TAM, TMA and TII
EXPECTED_SHORT = {'C3': 2, 'D3': 4, 'E3': 4, 'F3': 7}        # the opcodes with fewer than PER_OPCODE cases, and how many they have
EXPECTED_MODULES = 9
EXPECTED_SELECTION = {'read': 27692, 'excluded': {REASONS[0]: 5000, REASONS[1]: 12481, REASONS[2]: 1108, REASONS[3]: 6},
                      'native_opcodes': 234, 'reserved_opcodes_skipped': 22}

# The second pinned configuration: the first 250 usable vectors of each opcode (`--per-opcode 250`). Same rules as above; `known` holds
# the counts of the differences of KNOWN (their reasons are the interpreter's), the others the counterparts of the EXPECTED_* names.
LARGE = {
    'known': {'03': {'cycles': 250}, '13': {'cycles': 250}, '23': {'cycles': 250},
              '04': {'flags': 18}, '0C': {'flags': 22}, '14': {'flags': 56}, '1C': {'flags': 61}},
    'expected': {'cases': 56767, 'executed': 56767, 'not_executed': 0, 'state_equal': 56610, 'both_equal': 55860, 'registers': 0,
                 'flags': 157, 'pc': 0, 'mpr': 0, 'memory': 0, 'cycles_different': 750, 'native_vs_interpreter_different': 0},
    'short': {'C3': 2, 'D3': 4, 'E3': 4, 'F3': 7},
    'modules': 49,
    'selection': {'read': 81156, 'excluded': {REASONS[0]: 5000, REASONS[1]: 12481, REASONS[2]: 6870, REASONS[3]: 38},
                  'native_opcodes': 234, 'reserved_opcodes_skipped': 22},
    'opcodes': EXPECTED_OPCODES,
}
DEFAULT = {'known': {opcode: {key: value for key, value in known.items() if key != 'reason'} for opcode, known in KNOWN.items()},
           'expected': EXPECTED, 'short': EXPECTED_SHORT, 'modules': EXPECTED_MODULES, 'selection': EXPECTED_SELECTION,
           'opcodes': EXPECTED_OPCODES}
PINNED = {PER_OPCODE: DEFAULT, 250: LARGE}


def use(per_opcode: int):
    """Switch the tool to one of its pinned samples: PER_OPCODE and every pin that depends on it."""
    global PER_OPCODE, KNOWN, EXPECTED, EXPECTED_SHORT, EXPECTED_MODULES, EXPECTED_SELECTION, EXPECTED_OPCODES
    pin = PINNED[per_opcode]
    KNOWN = {opcode: {**counts, 'reason': interpreter.KNOWN[opcode]['reason']} for opcode, counts in pin['known'].items()}
    EXPECTED, EXPECTED_SHORT, EXPECTED_MODULES = pin['expected'], pin['short'], pin['modules']
    EXPECTED_SELECTION, EXPECTED_OPCODES = pin['selection'], pin['opcodes']
    PER_OPCODE = per_opcode


# ------------------------------------------------------------------ the corpus

def read_state(buffer: bytes, at: int):
    at += 4
    a, x, y, s, p = struct.unpack_from('5B', buffer, at)
    at += 5
    pc = struct.unpack_from('<H', buffer, at)[0]
    at += 2
    mpr = tuple(struct.unpack_from('8B', buffer, at))
    at += 8
    count = struct.unpack_from('<i', buffer, at)[0]
    at += 4
    ram = []
    for _ in range(count):
        address, value = struct.unpack_from('<IB', buffer, at)
        at += 5
        ram.append((address, value))
    return at, {'a': a, 'x': x, 'y': y, 's': s, 'p': p, 'pc': pc, 'mpr': mpr, 'ram': ram}


def vectors(path: Path):
    """The vectors of one opcode file, in corpus order (the layout `native/pce_huc6280_vector_checks.cpp` reads)."""
    buffer = path.read_bytes()
    count = struct.unpack_from('<I', buffer, 0)[0]
    at = 4
    for _ in range(count):
        at += 4
        name = buffer[at:at + 50].rstrip(b'\0 ').decode('ascii')
        at += 50
        opcode = struct.unpack_from('<I', buffer, at)[0]
        at += 4
        at, init = read_state(buffer, at)
        at, final = read_state(buffer, at)
        cycles, recorded = struct.unpack_from('<II', buffer, at)
        at += 8 + 4 * recorded
        yield {'name': name, 'opcode': opcode, 'init': init, 'final': final, 'cycles': cycles, 'recorded': recorded}


# ------------------------------------------------------------------ the selection

def canonical_case(vector: dict, isa):
    """(case, None) with the vector moved to the canonical mapping, or (None, the reason it is not used)."""
    mapping = vector['init']['mpr']
    if vector['opcode'] in (0x43, 0x53) or vector['final']['mpr'] != mapping:
        return None, REASONS[0]
    if vector['recorded'] >= CORPUS_CAP:
        return None, REASONS[1]
    if len(set(mapping)) != 8:
        return None, REASONS[2]
    window = {page: index for index, page in enumerate(mapping)}

    def moved(state):
        ram = []
        for address, value in state['ram']:
            index = window.get(address >> 13)
            if index is None:
                return None
            ram.append(((CANONICAL[index] << 13) | (address & 0x1FFF), value))
        return dict(state, mpr=CANONICAL, ram=ram)

    init, final = moved(vector['init']), moved(vector['final'])
    if init is None or final is None:
        return None, REASONS[3]
    memory = dict(init['ram'])

    def physical(pc):
        return (CANONICAL[(pc & 0xFFFF) >> 13] << 13) | (pc & 0x1FFF)

    instruction = isa.decode(lambda pc: memory.get(physical(pc), 0), init['pc'], CANONICAL)
    length = len(instruction.data)
    site = {}
    for offset in range(length):
        address = physical(init['pc'] + offset)
        if address not in memory:
            return None, REASONS[3]
        site[address] = memory[address]
    flow = {instruction.next_pc} | ({instruction.target} if instruction.target is not None else set())
    if flow & {(init['pc'] + offset) & 0xFFFF for offset in range(1, length)}:
        return None, REASONS[3]
    return {'name': vector['name'], 'opcode': vector['opcode'], 'init': init, 'final': final, 'cycles': vector['cycles'],
            'site': site, 'length': length, 'flow': flow}, None


def select(folder: Path, isa) -> tuple[list[dict], dict]:
    """The first PER_OPCODE usable vectors of each opcode the emitter translates, and what was read and left out."""
    cases = []
    excluded = dict.fromkeys(REASONS, 0)
    read = 0
    reserved = 0
    native = 0
    for opcode in range(256):
        if opcode not in isa.NATIVE:
            reserved += 1
            continue
        native += 1
        kept = 0
        for vector in vectors(folder / f'{opcode:02x}.json.bin'):
            read += 1
            case, reason = canonical_case(vector, isa)
            if case is None:
                excluded[reason] += 1
                continue
            cases.append(case)
            kept += 1
            if kept >= PER_OPCODE:
                break
    return cases, {'read': read, 'excluded': excluded, 'native_opcodes': native, 'reserved_opcodes_skipped': reserved}


def group(cases: list[dict]) -> list[list[dict]]:
    """Modules, first fit: no two sites of a module overlap or flow into each other, MODULE_SITES at most."""
    modules = []
    for case in cases:
        pc = case['init']['pc']
        span = {(pc + offset) & 0xFFFF for offset in range(case['length'])}
        for module in modules:
            if (len(module['items']) < MODULE_SITES and not module['used'] & span and not module['flow'] & span
                    and not case['flow'] & module['used']):
                module['used'] |= span
                module['flow'] |= case['flow']
                module['items'].append(case)
                break
        else:
            modules.append({'used': set(span), 'flow': set(case['flow']), 'items': [case]})
    return [module['items'] for module in modules]


# ------------------------------------------------------------------ the modules

def write_cases(path: Path, items: list[dict]):
    lines = []
    for case in items:
        init, final = case['init'], case['final']
        fields = [case['name'].replace(' ', '_'), case['opcode'], case['cycles'], init['a'], init['x'], init['y'], init['s'],
                  init['p'], init['pc'], final['a'], final['x'], final['y'], final['s'], final['p'], final['pc'],
                  len(case['site']), *sorted(case['site']),
                  len(init['ram']), *(number for cell in init['ram'] for number in cell),
                  len(final['ram']), *(number for cell in final['ram'] for number in cell)]
        lines.append(' '.join(str(field) for field in fields))
    path.write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')


def emit_modules(project: Path, modules: list[list[dict]]) -> list[dict]:
    """One snapshot per module, analysed and emitted by the pinned engine's own toolkit; the cases next to each module."""
    from retrorecomp.pce_build import _engine_on_path
    emitted = []
    with _engine_on_path():
        from pcerecomp import analysis, emitter
        for index, items in enumerate(modules):
            memory = {}
            for case in items:
                memory.update(case['site'])
            entries = tuple(case['init']['pc'] for case in items)
            snapshot = analysis.Snapshot(CANONICAL, memory, entries, f'huc6280-vectors-{index}')
            result = analysis.analyze(snapshot, limit=len(entries) * 4 + 16)
            if result['unresolved'] and any(row['reason'] in ('instruction_limit', 'overlapping_instruction')
                                            for row in result['unresolved']):
                raise SystemExit(f'Module {index}: the analysis is not complete ({result["unresolved"][:3]}).')
            folder = project / 'modules' / f'mod_{index}'
            emitter.emit(result, folder)
            write_cases(folder / 'cases.txt', items)
            emitted.append({'index': index, 'sites': len(items),
                            'module_sha256': hashlib.sha256((folder / 'module.cpp').read_bytes()).hexdigest()})
    return emitted


def build(project: Path, count: int) -> list[Path]:
    from retrorecomp import core
    from retrorecomp.pce_build import checkout_path, ensure_engine
    from retrorecomp.platforms import build_executable
    ensure_engine(print)
    engine = checkout_path().as_posix()
    source = (ASSETS / 'native/pce_huc6280_native_checks.cpp').as_posix()
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPceNativeVectors LANGUAGES C CXX)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)']
    names = []
    for index in range(count):
        module = (project / 'modules' / f'mod_{index}').as_posix()
        name = f'retro_pce_huc6280_native_checks_{index}'
        names.append(name)
        lines += [
            # The module is validated and its sources listed by the engine's own function, then compiled in an object library
            # of a short name, as a game's module is (retrorecomp/pce_build.py game_cmake).
            f'pce_add_native_module(PCE_MODULE_{index} MODULE "{module}/module.cpp" MANIFEST "{module}/module.json")',
            f'get_target_property(PCE_MODULE_SOURCES_{index} ${{PCE_MODULE_{index}}} SOURCES)',
            f'add_library(pce_module_{index} OBJECT ${{PCE_MODULE_SOURCES_{index}}})',
            f'target_link_libraries(pce_module_{index} PUBLIC pce-runtime)',
            f'set_target_properties(pce_module_{index} PROPERTIES CXX_EXTENSIONS OFF)',
            f'add_executable({name} "{source}" $<TARGET_OBJECTS:pce_module_{index}>)',
            f'target_link_libraries({name} PRIVATE pce-runtime)']
    (project / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args()], log=log, timeout=900)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', *names, '--parallel', core.build_jobs()],
             log=log, timeout=3600)
    return [build_executable(project / 'build', name) for name in names]


# ------------------------------------------------------------------ the judgement

def aggregate(lines: list[dict]) -> list[dict]:
    """The per-opcode rows of the case lines the checks print."""
    rows = {}
    for line in lines:
        row = rows.setdefault(line['opcode'], {
            'opcode': line['opcode'], 'cases': 0, 'executed': 0, 'not_executed': 0, 'state_equal': 0, 'both_equal': 0,
            **dict.fromkeys(CLASSES, 0), 'cycles_different': 0, 'interpreter_not_executed': 0,
            'interpreter': {**dict.fromkeys(CLASSES, 0), 'cycles_different': 0}, 'native_vs_interpreter_different': 0,
            'first_difference': ''})
        row['cases'] += 1
        if line['interpreter'] != 'executed':
            row['interpreter_not_executed'] += 1
        else:
            for name in line['interpreter_vs_vector']:
                row['interpreter']['cycles_different' if name == 'cycles' else name] += 1
        if line['native'] != 'executed':
            row['not_executed'] += 1
            row.setdefault('stops', {}).setdefault(line['native'], 0)
            row['stops'][line['native']] += 1
            continue
        row['executed'] += 1
        classes = line['native_vs_vector']
        for name in classes:
            row['cycles_different' if name == 'cycles' else name] += 1
        if not any(name in CLASSES for name in classes):
            row['state_equal'] += 1
            if not classes:
                row['both_equal'] += 1
        if classes and not row['first_difference']:
            row['first_difference'] = line['vector']
        if line['native_vs_interpreter']:
            row['native_vs_interpreter_different'] += 1
            row.setdefault('tier_fields', {})
            for name in line['native_vs_interpreter']:
                row['tier_fields'][name] = row['tier_fields'].get(name, 0) + 1
    return [rows[opcode] for opcode in sorted(rows)]


def judge(rows: list[dict], selection: dict, modules: int) -> tuple[dict, list[str]]:
    """The totals of the per-opcode rows and what is not explained by KNOWN and EXPECTED."""
    totals = {key: sum(row[key] for row in rows) for key in EXPECTED}
    unexplained = []
    seen = set()
    for row in rows:
        opcode = row['opcode']
        if row['not_executed'] or row['interpreter_not_executed']:
            unexplained.append(f'{opcode}: not executed, native {row["not_executed"]} ({row.get("stops", {})}), '
                               f'interpreter {row["interpreter_not_executed"]}')
        if row['native_vs_interpreter_different']:
            unexplained.append(f'{opcode}: {row["native_vs_interpreter_different"]} cases differ from the interpreter '
                               f'({row.get("tier_fields", {})})')
        differs = {key: row[key] for key in (*CLASSES, 'cycles_different') if row[key]}
        if differs != {key: value for key, value in row['interpreter'].items() if value}:
            unexplained.append(f'{opcode}: differs {differs} from the vectors, the interpreter on the same cases '
                               f'{ {key: value for key, value in row["interpreter"].items() if value} }')
        if differs:
            known = KNOWN.get(opcode)
            wanted = {('cycles_different' if key == 'cycles' else key): value
                      for key, value in (known or {}).items() if key != 'reason'}
            if wanted != differs:
                unexplained.append(f'{opcode}: differs {differs}, known {wanted}')
            seen.add(opcode)
    unexplained += [f'{opcode}: known difference not seen' for opcode in sorted(set(KNOWN) - seen)]
    unexplained += [f'{key}: {totals[key]}, expected {value}' for key, value in EXPECTED.items() if totals[key] != value]
    short = {row['opcode']: row['cases'] for row in rows if row['cases'] != PER_OPCODE}
    if short != EXPECTED_SHORT:
        unexplained.append(f'opcodes with fewer than {PER_OPCODE} cases: {short}, expected {EXPECTED_SHORT}')
    if len(rows) != EXPECTED_OPCODES:
        unexplained.append(f'{len(rows)} opcodes with cases, expected {EXPECTED_OPCODES}')
    if selection != EXPECTED_SELECTION:
        unexplained.append(f'selection {selection}, expected {EXPECTED_SELECTION}')
    if modules != EXPECTED_MODULES:
        unexplained.append(f'{modules} modules, expected {EXPECTED_MODULES}')
    return totals, unexplained


def main():
    from retrorecomp import core
    from retrorecomp.pce_build import _engine_on_path, ensure_engine
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--fetch', action='store_true', help='fetch the corpus when it is not cached')
    parser.add_argument('--per-opcode', type=int, choices=sorted(PINNED), default=PER_OPCODE,
                        help=f'usable vectors kept per opcode (default {PER_OPCODE}); each value has its own pinned counts')
    args = parser.parse_args()
    default = args.per_opcode == PER_OPCODE
    use(args.per_opcode)
    if not corpus.cached():
        if not args.fetch:
            raise SystemExit('The HuC6280 vectors are not cached: run tools/fetch_huc6280_vectors.py (or pass --fetch).')
        corpus.fetch()
    started = time.monotonic()
    ensure_engine(print)
    project = ROOT / ('.build/pce-huc6280-native-selftest' if default else f'.build/pce-huc6280-native-selftest-{PER_OPCODE}')
    if (project / 'modules').exists():
        import shutil
        shutil.rmtree(project / 'modules')       # the emitter refuses a folder that exists; the build folder is kept
    project.mkdir(parents=True, exist_ok=True)
    with _engine_on_path():
        from pcerecomp import isa
        cases, selection = select(corpus.folder(), isa)
    modules = group(cases)
    emitted = emit_modules(project, modules)
    prepared = time.monotonic()
    executables = build(project, len(modules))
    built = time.monotonic()
    lines, counts = [], []
    for index, executable in enumerate(executables):
        output = core.run([executable, project / 'modules' / f'mod_{index}' / 'cases.txt'], timeout=3600)
        (project / 'modules' / f'mod_{index}' / 'checks.log').write_text(output, encoding='utf-8')
        found = [json.loads(line) for line in output.splitlines() if line.startswith('{"vector"')]
        counts.append(found and len(found) == len(modules[index]))
        lines += found
    rows = aggregate(lines)
    totals, unexplained = judge(rows, selection, len(modules))
    if not all(counts):
        unexplained.append('a module printed a different number of cases than it was given')
    ran = time.monotonic()
    result = {'revision': corpus.REVISION, 'corpus_sha256': corpus.CORPUS_SHA256, 'oracle': 'Mesen (expectations, not hardware)',
              'tier': 'native (the engine\'s emitter, guarded modules)', 'per_opcode': PER_OPCODE, 'selection': selection,
              'modules': emitted, 'totals': totals, 'known': KNOWN, 'unexplained': unexplained, 'opcodes': rows,
              'elapsed_seconds': {'select_and_emit': round(prepared - started, 1), 'build': round(built - prepared, 1),
                                  'run': round(ran - built, 1)}}
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'totals': totals, 'selection': selection, 'modules': len(modules), 'unexplained': unexplained}), flush=True)
    return 1 if unexplained else 0


if __name__ == '__main__':
    sys.exit(main())
