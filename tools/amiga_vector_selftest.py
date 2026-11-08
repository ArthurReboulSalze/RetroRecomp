"""Independent MC68000 vectors replayed through the Amiga's CPU, Moira as vAmiga builds it (gate G10, independent CPU evidence).

    python -B tools/amiga_vector_selftest.py [--workspace DIR] [--list] [fixture ...]
        (default: the four fixtures; needs a compiler and a first build of vAmiga's Core; no ROM, no Kickstart, no disk)

The vectors are the pinned SingleStepTests/m68000 fixtures of the repository (`tests/fixtures`, MIT, generated with MAME, not recorded from
hardware; synthetic instruction data), the same four and read the same way as `tools/atarist_vector_selftest.py`: every vector, none sampled,
the two authored vectors that expect the trace exception after the instruction left out and counted. The code under test is the Amiga's CPU:
the Moira that vAmiga's Core compiles (MIT; vAmiga is MPL-2.0), adapted at build time by `retrorecomp/amiga_vamiga.py`, with the CPU's client
API (`sync`, `read*`, `write*`) replaced by a flat 24-bit RAM that logs every access and its clock (`native/amiga_machine/amiga_vector_checks.cpp`).
No Amiga, no custom chip, no chip-RAM contention, no ROM overlay: the CPU alone. This shows Moira's behaviour against an oracle made with MAME;
it does not show the Amiga's hardware, gameplay or latency, and it is not a statement about silicon.

Three things are checked, each counted apart:
  1. the native steps equal the interpreter. The steps are the ones the converter's own generator writes (`amiga_conversion.generate`: the shared
     `m68k_observed.write_steps` with the Amiga's Moira hooks of `amiga_codegen.py`), from observations that put each vector's instruction at its
     own address. Each vector runs twice from the same state, through the jump table and through `rr_moira_native` -> `rr_amiga_lookup` (the
     live-word guard included); registers, SR, PC, the queue, the clock and every bus access (kind, address, size, value, clock) must be equal;
  2. Moira against the vectors: registers, SR (under the vector's mask), PC, the two queue words, every byte of RAM, the total clocks and, where
     the fixture lists the bus transactions, their order and the clock of each. Every vector that differs is classified into a family, a
     (fixture, group, kind) with a count and a written reason (`FAMILIES`); a difference in no family, or a family whose count changed, fails;
  3. the harness itself: every selected vector ran, and a vector corrupted on purpose is seen (`--self-check`, the default).
"""
from __future__ import annotations
import json
import os
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ('m68k-groups', 'm68k-shifts', 'md-prefetch', 'md-exceptions')
TRACE_DELIVERY = 'post-instruction trace'    # the name of the two authored vectors that expect the trace exception after the instruction
SAMPLE_BYTES = 12                            # the bytes read at a vector's address for the generator: six words, as a conversion observes
REGS = [*(f'd{i}' for i in range(8)), *(f'a{i}' for i in range(7)), 'usp', 'ssp', 'sr', 'pc']
KINDS = ('state', 'clocks', 'bus')

def s16(value: int) -> int:
    value &= 0xffff
    return value - 0x10000 if value >= 0x8000 else value


def opcode(test: dict) -> int:
    return test['initial']['prefetch'][0]


class Family:
    """A named kind of difference between Moira and the vectors: where it is (fixture, group, kind), which vectors of that place it covers
    (`applies(test, row)`), how many there are on the pinned fixtures (`count`), what differs (`reason`) and how it was established (`basis`).
    A difference that no family covers, or a family whose count moved, fails the run. None of this says which behaviour is the chip's: the
    oracle is MAME, and the account is of what the two sides do, from the bus sequences of this run and the lines of Moira named."""

    def __init__(self, name, fixture, group, kind, count, applies, reason, basis):
        self.name, self.fixture, self.group, self.kind, self.count = name, fixture, group, kind, count
        self.applies, self.reason, self.basis = applies, reason, basis

    @property
    def key(self) -> tuple[str, str, str]:
        return self.fixture, self.group, self.kind


def _memory_destination_long(test, row):
    """ADD.l and SUB.l (and ADDQ.l, SUBQ.l, ADDI.l and SUBI.l, which the groups hold) whose destination is a memory operand: a read-modify-write."""
    op = opcode(test)
    return (op >> 3) & 7 >= 2 and (((op >> 12) in (0xD, 0x9) and bool((op >> 8) & 1)) or (op >> 12) == 5 or (op >> 8) in (0x04, 0x06))


def _negative_dn(test, row):
    return s16(test['initial'][f'd{opcode(test) >> 9 & 7}']) < 0


_BUS = 'the bus sequences of this run'
_CCR = ('every vector: the vectors repeat the first prefetch address (A, A, A+2), Moira the second (A, A+2, A+2). '
        'State and clocks are equal.')
FAMILIES: tuple[Family, ...] = (
    Family('long result written to memory', 'm68k-groups', 'ADD.l', 'bus', 10, _memory_destination_long,
           'Order of the two writes of a long result stored back to memory (ADD Dn,<ea>, ADDQ.l and ADDI.l to memory): the vectors write the low word '
           'first, Moira the high word first. Same addresses, values, count and clocks.', _BUS),
    Family('long result written to memory', 'm68k-groups', 'SUB.l', 'bus', 4, _memory_destination_long,
           'Order of the two writes of a long result stored back to memory (SUB Dn,<ea>, SUBQ.l and SUBI.l to memory): the vectors write the low word '
           'first, Moira the high word first. Same addresses, values, count and clocks.', _BUS),
    Family('predecrement long operands', 'm68k-groups', 'ADDX.l', 'bus', 4, lambda test, row: bool(opcode(test) & 8),
           'ADDX.l -(Ay),-(Ax): the two words of each long operand are read low word (higher address) first by the vectors and high word '
           'first by Moira. The writes and the clocks are equal.', _BUS),
    Family('predecrement long operands', 'm68k-groups', 'SUBX.l', 'bus', 9, lambda test, row: bool(opcode(test) & 8),
           'SUBX.l -(Ay),-(Ax): the two words of each long operand are read low word (higher address) first by the vectors and high word '
           'first by Moira. The writes and the clocks are equal.', _BUS),
    Family('operations on the CCR', 'm68k-groups', 'ANDItoCCR', 'bus', 44, lambda test, row: True, 'ANDI to CCR, ' + _CCR, _BUS),
    Family('operations on the CCR', 'm68k-groups', 'EORItoCCR', 'bus', 40, lambda test, row: True, 'EORI to CCR, ' + _CCR, _BUS),
    Family('operations on the CCR', 'm68k-groups', 'ORItoCCR', 'bus', 40, lambda test, row: True, 'ORI to CCR, ' + _CCR, _BUS),
    Family('operations on the CCR', 'm68k-groups', 'MOVEtoCCR', 'bus', 23, lambda test, row: True,
           'MOVE to CCR, every vector: of the two prefetch reads after the operand, the vectors read A then A+2, Moira A+2 twice (one more '
           'address of the same kind as above). State and clocks are equal.', _BUS),
    Family('BTST Dn,#imm', 'm68k-groups', 'BTST', 'clocks', 2, lambda test, row: opcode(test) & 0xf1ff == 0x013c,
           'BTST Dn,#imm takes 8 clocks in Moira and 10 in the vectors; the bus accesses are the same. Moira\'s table for the immediate '
           'operand gives 8 (execBitDxEa, CYCLES_IM 8+c with c = 0 for BTST).', 'the clocks of this run and that line of Moira'),
    Family('JSR', 'md-prefetch', 'JSR', 'bus', 25, lambda test, row: True,
           'JSR, every vector: the vectors read the first word of the target before pushing the return address, Moira pushes the return '
           'address (two words) first. Same accesses, values and clocks.', _BUS),
    Family('MOVEM.l from memory', 'md-prefetch', 'MOVEM.l-phases', 'bus', 37, lambda test, row: bool(opcode(test) & 0x400),
           'MOVEM.l <ea>,<list>, every vector: the vectors read one extra word past the end of the list, last; Moira makes its extra read '
           'first, again at the first address. Clocks and state are equal.', _BUS),
    Family('MOVEM.l to -(An)', 'md-prefetch', 'MOVEM.l-phases', 'bus', 8,
           lambda test, row: not opcode(test) & 0x400 and (opcode(test) >> 3) & 7 == 4,
           'MOVEM.l <list>,-(An), every vector: each long register is written low word first by the vectors and high word first by Moira; '
           'the other store modes agree. Clocks and state are equal.', _BUS),
    Family('expired DBcc (authored)', 'md-prefetch', 'authored-variable', 'bus', 15, lambda test, row: 'condition=False counter=0' in test['name'],
           'DBcc with the condition false and the counter reaching -1 (15 conditions, authored cases): the vectors read the branch target '
           'first, then the next two words; Moira makes a dummy read at the next instruction first (execDbcc). Clocks and state are equal.',
           'the bus sequences of this run and that function of Moira'),
    Family('divide by zero frame (authored)', 'md-prefetch', 'authored-variable', 'state', 2, lambda test, row: 'divide by zero' in test['name'],
           'DIVU (N) and DIVS (Z) by zero: Moira leaves one flag set in the SR it saves in the exception frame and keeps, where the vectors '
           'keep it clear. N, Z, V and C after a divide by zero are undefined on a 68000 (the fixture\'s own note).',
           'the registers and RAM of this run'),
    Family('CHK with a negative Dn', 'md-prefetch', 'CHK-phases', 'clocks', 14, _negative_dn,
           'CHK that traps on a negative Dn: Moira takes 40 clocks, the vectors 38 when bound - Dn overflows 16 bits and 40 otherwise (the '
           'rule of docs/CPU_68000.md; cause_checks() verifies it on every register-operand vector); Moira has one delay for both (execChk).',
           'the clocks of this run and that function of Moira'),
    Family('CHK with a negative Dn', 'md-prefetch', 'CHK-phases', 'bus', 14, _negative_dn,
           'The same 14 vectors on the bus: every access after the exception sequence starts 2 clocks later in Moira (the order and the '
           'addresses are equal).', _BUS),
    Family('CHK with a negative Dn', 'md-exceptions', 'CHK', 'clocks', 13, _negative_dn,
           'The same difference of CHK in the exception fixture (negative Dn, 40 clocks in Moira, 38 in the vectors when bound - Dn overflows).',
           'the clocks of this run and that function of Moira'),
    Family('queue after a stopped STOP', 'md-exceptions', 'STOP', 'state', 32,
           lambda test, row: stops(test) == 1 and row['regs'].split() == ['irc'],
           'STOP that stops the CPU: the vectors keep IRC as it was, Moira reads one more word after the immediate (readI -> readExt) and IRC '
           'holds it (0 here: the flat RAM holds nothing at that address). Registers, SR, PC and clocks are equal. The fixture says it does '
           'not compare prefetch contents.', 'the registers of this run and that function of Moira'),
)
def workspace_of(argv: list[str]) -> tuple[Path, list[str]]:
    """The folder that holds `.deps` and `.build` (the tree itself, or `--workspace DIR` / RETRO_RECOMP_WORKSPACE for a worktree without them)."""
    rest, folder = [], os.environ.get('RETRO_RECOMP_WORKSPACE')
    it = iter(argv)
    for item in it:
        if item == '--workspace':
            folder = next(it)
        else:
            rest.append(item)
    return (Path(folder).resolve() if folder else ROOT), rest


def work_dir(workspace: Path) -> Path:
    return workspace / '.build' / 'amiga-vectors'


# ------------------------------------------------------------------------------------------------------------------ vectors
def fixture_tests(name: str) -> list[dict]:
    """Every vector of a fixture, as the other machines' replays read it (the Mega Drive prefetch fixture adds its authored cases)."""
    tests = list(json.loads((ROOT / 'tests/fixtures' / name / 'cases.json').read_text(encoding='utf-8'))['tests'])
    if name == 'md-prefetch':
        tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
    return tests


def cycles_of(test: dict) -> int:
    return test.get('length', test.get('cycles'))


def stops(test: dict) -> int:
    """1 when the vector ends with the CPU stopped (a STOP in supervisor mode: the fixtures give it 4 clocks)."""
    return int(test['group'] == 'STOP' and cycles_of(test) == 4)


def final_pc_offset(test: dict) -> int:
    """SingleStepTests PCs include the two prefetched words (4 bytes). The vectors of a stopped STOP perform no new prefetch, so their final PC
    already is the following instruction (md-exceptions' `pc_convention`): the offset is 0 for them and 4 for every other vector."""
    return 0 if stops(test) else 4


def architectural_pc(pc: int, offset: int = 4) -> int:
    """The address of the instruction (or of the next one) on the 24-bit bus: the vector's PC minus its prefetched words."""
    return (pc - offset) & 0xffffff


def state_values(state: dict, pc_offset: int = 4) -> list[int]:
    """d0-d7, a0-a6, usp, ssp, sr, pc (architectural), then the two queue words."""
    return [state[key] if key != 'pc' else architectural_pc(state[key], pc_offset) for key in REGS] + list(state['prefetch'])


def classify(test: dict) -> str:
    """Why a vector is not replayed, or 'run': only the post-instruction trace delivery (the single-step oracle does not deliver it)."""
    return 'trace_delivery' if TRACE_DELIVERY in test['name'] else 'run'


def selection(name: str) -> tuple[list[dict], dict]:
    """(the vectors that run, the count of every other category) for one fixture."""
    run, left = [], {}
    for test in fixture_tests(name):
        reason = classify(test)
        if reason == 'run':
            run.append(test)
        else:
            left[reason] = left.get(reason, 0) + 1
    return run, left


def transactions(test: dict) -> list[tuple[int, int, int, int]] | None:
    """(kind 0 read/1 write, clock at the start of the cycle, address, size) of each bus cycle of the vector; idle periods only advance the clock.
    None when the fixture has no transaction list (md-exceptions)."""
    if 'transactions' not in test:
        return None
    clock, found = 0, []
    for item in test['transactions']:
        if item[0] != 'n':
            if item[0] not in ('r', 'w'):
                raise ValueError('Unknown bus transaction kind: ' + str(item[0]))
            found.append((int(item[0] == 'w'), clock, item[3] & 0xffffff, 1 if item[4] == '.b' else 2))
        clock += item[1]
    return found


def vector_line(index: int, test: dict) -> str:
    """One line of the file the harness reads (see native/amiga_machine/amiga_vector_checks.cpp)."""
    initial, final = test['initial'], test['final']
    bus = transactions(test)
    fields = [index, cycles_of(test), test.get('sr_mask', 0xffff), stops(test), -1 if bus is None else len(bus)]
    for item in bus or ():
        fields.extend(item)
    fields.extend(state_values(initial))
    fields.extend(state_values(final, final_pc_offset(test)))
    for stage in (initial, final):
        pairs = stage['ram']
        fields.append(len(pairs))
        for address, value in pairs:
            fields.extend((address & 0xffffff, value))
    return ' '.join(str(field) for field in fields)


def code_sample(test: dict) -> tuple[int, str]:
    """(address, words) the way a conversion observes an executed instruction: the bytes at its address, here the two queue words and the
    vector's own RAM after them (a byte the vector does not list reads as zero, as in the harness's flat RAM)."""
    initial = test['initial']
    address = architectural_pc(initial['pc'])
    ram = {a & 0xffffff: b for a, b in initial['ram']}
    data = bytes([initial['prefetch'][0] >> 8, initial['prefetch'][0] & 0xff, initial['prefetch'][1] >> 8, initial['prefetch'][1] & 0xff])
    data += bytes(ram.get((address + n) & 0xffffff, 0) for n in range(4, SAMPLE_BYTES))
    return address, data.hex()


# ------------------------------------------------------------------------------------------------------------------ build
def ensure_core(workspace: Path, work: Path) -> Path:
    """The adapted vAmiga Core (the pinned checkout of the workspace's `.deps`, adapted by retrorecomp/amiga_vamiga.py into the work folder)."""
    from retrorecomp import amiga_vamiga
    return amiga_vamiga.adapt(amiga_vamiga.source(), work / 'vamiga')


def write_cmake(work: Path, core: Path) -> Path:
    machine = (ROOT / 'native' / 'amiga_machine').as_posix()
    folder = work / 'cmake'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAmigaVectors LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(RR_VECTOR_STEPS "" CACHE PATH "The generated native steps (steps/*, step_semantics.h)")
add_subdirectory("{core.as_posix()}" vacore)
# vAmiga's warnings-as-errors stay on its own files.
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
set(RR_SOURCES "{machine}/amiga_vector_checks.cpp")
if(RR_VECTOR_STEPS)
    file(GLOB RR_STEPS "${{RR_VECTOR_STEPS}}/steps/*.cpp" "${{RR_VECTOR_STEPS}}/steps/*.c")
    list(APPEND RR_SOURCES ${{RR_STEPS}})
endif()
add_executable(amiga_vector_checks ${{RR_SOURCES}})
if(RR_VECTOR_STEPS)
    target_include_directories(amiga_vector_checks PRIVATE "${{RR_VECTOR_STEPS}}")
    target_compile_definitions(amiga_vector_checks PRIVATE RR_VECTOR_STEPS=1)
endif()
target_link_libraries(amiga_vector_checks PRIVATE VACore)
# The harness's definitions of the CPU's client functions come first and shadow vAmiga's (Components/CPU/CPU.cpp).
if(MSVC)
    target_link_options(amiga_vector_checks PRIVATE /FORCE:MULTIPLE)
else()
    target_link_options(amiga_vector_checks PRIVATE -Wl,--allow-multiple-definition)
endif()
if(WIN32)
    target_link_libraries(amiga_vector_checks PRIVATE ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    return folder


def build_harness(work: Path, core: Path, steps: Path | None) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    folder = write_cmake(work, core)
    build = work / 'build'
    cmake, generator = toolchain()
    configure = [cmake, '-S', folder, '-B', build, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release',
                 f'-DRR_VECTOR_STEPS={steps.as_posix() if steps else ""}']
    run(configure, log=work / 'build.log', cwd=work)
    run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'amiga_vector_checks'], log=work / 'build.log', timeout=7200, cwd=work)
    return build_executable(build, 'amiga_vector_checks')


def generate_steps(work: Path, program: Path, samples: list[tuple[int, str]]) -> dict:
    """The converter's own generation of the native steps for these observations, from the opcode table the harness (vAmiga's Moira) wrote."""
    from retrorecomp import amiga_conversion
    from retrorecomp.core import run
    table = work / 'opcode-map.txt'
    run([program, '--opcode-map', table], cwd=work)
    folder = work / 'generated'
    folder.mkdir(parents=True, exist_ok=True)
    return amiga_conversion.generate(folder, samples, table)


# ------------------------------------------------------------------------------------------------------------------ results
def replay(name: str, program: Path, work: Path) -> dict:
    from retrorecomp.core import run
    tests, left = selection(name)
    path = work / f'{name}.vectors'
    path.write_text('\n'.join(vector_line(i, test) for i, test in enumerate(tests)) + '\n', encoding='ascii', newline='\n')
    output = run([program, path], cwd=work)
    rows = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    return {'fixture': name, 'total': len(fixture_tests(name)), 'selected': len(tests), 'left_out': left, 'rows': rows, 'tests': tests}


def deviations(row: dict, test: dict, main_offset: int) -> list[str]:
    """The kinds in which Moira's result for one vector differs from the vector's: its state (registers, SR under the mask, PC, queue, RAM), its
    total clocks, and its bus (the order, address and size of every access, and the clock of each against the vector's start of cycle)."""
    kinds = []
    if row['regs'] or row['ram']:
        kinds.append('state')
    if row['cyc'] != cycles_of(test):
        kinds.append('clocks')
    if transactions(test) is not None and (row['bo'] or row['bt'] or row['off'] != main_offset):
        kinds.append('bus')
    return kinds


def evaluate(result: dict, main_offset: int | None = None) -> dict:
    """The counts of one fixture: Moira against the vectors, every deviation put in a family (or left in none), and the native steps against
    the interpreter."""
    rows, tests = result['rows'], result['tests']
    offsets = Counter(row['off'] for row, test in zip(rows, tests) if transactions(test) is not None)
    main = main_offset if main_offset is not None else (offsets.most_common(1)[0][0] if offsets else 0)
    totals = {'run': len(rows), 'state_ok': 0, 'clocks_ok': 0, 'bus_ok': 0, 'bus_checked': 0, 'all_ok': 0, 'native_step': 0, 'native_equal': 0,
              'native_differ': 0, 'native_none': 0, 'deviating': 0, 'in_a_family': 0, 'unexplained': 0}
    seen: Counter = Counter()           # (fixture, group, kind) -> deviations found
    covered: Counter = Counter()        # (fixture, group, kind, family index) -> vectors a family explains
    unexplained: dict = {}
    native_none: Counter = Counter()
    for row, test in zip(rows, tests):
        kinds = deviations(row, test, main)
        totals['state_ok'] += 'state' not in kinds
        totals['clocks_ok'] += 'clocks' not in kinds
        totals['bus_checked'] += transactions(test) is not None
        totals['bus_ok'] += transactions(test) is not None and 'bus' not in kinds
        totals['all_ok'] += not kinds
        totals['deviating'] += bool(kinds)
        explained = True
        for kind in kinds:
            key = (result['fixture'], test['group'], kind)
            seen[key] += 1
            index = next((n for n, family in enumerate(FAMILIES) if family.key == key and family.applies(test, row)), None)
            if index is None:
                explained = False
                unexplained.setdefault(key, []).append((test['name'], row['regs'], row['cyc'] - cycles_of(test)))
            else:
                covered[key + (index,)] += 1
        totals['in_a_family'] += bool(kinds) and explained
        totals['unexplained'] += bool(kinds) and not explained
        if row['nat'] == 0:
            totals['native_none'] += 1
            native_none[test['group']] += 1
        else:
            totals['native_step'] += 1
            totals['native_equal' if row['nat'] == 1 else 'native_differ'] += 1
    return {'fixture': result['fixture'], 'main_offset': main, 'totals': totals, 'seen': dict(seen), 'covered': dict(covered),
            'unexplained': unexplained, 'native_without_step': dict(native_none),
            'bad_native': [(test['group'], test['name'], row['nd']) for row, test in zip(rows, tests) if row['nat'] == 2][:20]}


def cause_checks(result: dict) -> list[str]:
    """Checks of the causes the families name, where the run can verify them: a CHK on a data register that traps takes 38 clocks in the
    vectors when bound - Dn overflows 16 bits and 40 below zero otherwise (docs/CPU_68000.md), and Moira's clocks differ exactly where Moira's
    single 40 meets the 38."""
    found, seen = [], 0
    for row, test in zip(result['rows'], result['tests']):
        if test['group'] not in ('CHK', 'CHK-phases') or (opcode(test) >> 3) & 7:
            continue
        dn, bound = s16(test['initial'][f'd{opcode(test) >> 9 & 7}']), s16(test['initial'][f'd{opcode(test) & 7}'])
        seen += 1
        differs = row['cyc'] != cycles_of(test)
        rule = dn < 0 and not -32768 <= bound - dn <= 32767
        if differs != rule:
            found.append(f"{result['fixture']}: {test['name']}: Moira's clocks differ from the vector's: {differs}; bound - Dn overflows: {rule}")
    if not seen and result['fixture'] in ('md-prefetch', 'md-exceptions'):
        found.append(f"{result['fixture']}: no CHK on a data register to check the cause on")
    return found


def problems(evaluated: dict, result: dict) -> list[str]:
    """What must hold for the harness to be trusted, and for the run to pass."""
    found = []
    name, totals = evaluated['fixture'], evaluated['totals']
    if totals['run'] != result['selected']:
        found.append(f"{name}: {result['selected']} vectors selected, {totals['run']} ran")
    if totals['native_differ']:
        found.append(f"{name}: the native step differs from the interpreter for {totals['native_differ']} vectors: {evaluated['bad_native'][:3]}")
    if totals['native_none']:
        found.append(f"{name}: {totals['native_none']} vectors have no native step ({evaluated['native_without_step']})")
    for key, examples in sorted(evaluated['unexplained'].items()):
        found.append(f"{key}: {len(examples)} differences with the vectors in no family, e.g. {examples[0]}")
    for family_index, family in enumerate(FAMILIES):
        if family.fixture != name:
            continue
        count = evaluated['covered'].get(family.key + (family_index,), 0)
        if count != family.count:
            found.append(f"family {family.name} {family.key}: {count} vectors, {family.count} recorded")
    found.extend(cause_checks(result))
    return found


def summary(evaluated: dict, result: dict) -> str:
    t = evaluated['totals']
    left = ', '.join(f'{count} {reason}' for reason, count in sorted(result['left_out'].items())) or 'none'
    return (f"{result['fixture']:<13} {result['total']:>5} vectors, {result['selected']:>5} replayed (left out: {left}); "
            f"Moira against the vectors: state {t['state_ok']:>5}/{t['run']:<5} clocks {t['clocks_ok']:>5}/{t['run']:<5} "
            f"bus {t['bus_ok']:>5}/{t['bus_checked']:<5} whole {t['all_ok']:>5}/{t['run']:<5} "
            f"({t['deviating']} differ: {t['in_a_family']} in a family, {t['unexplained']} unexplained); "
            f"native steps ran for {t['native_step']:>5} (equal to the interpreter {t['native_equal']:>5}, differ {t['native_differ']}), no step {t['native_none']}")


def family_lines(evaluated: dict) -> list[str]:
    lines = []
    for family_index, family in enumerate(FAMILIES):
        if family.fixture == evaluated['fixture']:
            count = evaluated['covered'].get(family.key + (family_index,), 0)
            lines.append(f"    {family.group} {family.kind}: {count} ({family.name})")
    return lines


def self_check(program: Path, work: Path, result: dict) -> list[str]:
    """The check of the check: a vector whose expected D0 and clocks are changed must be seen by the harness."""
    from retrorecomp.core import run
    test = result['tests'][0]
    lines = vector_line(0, test).split(' ')
    ntx = int(lines[4])
    base = 5 + 4 * max(ntx, 0)
    lines[1] = str(int(lines[1]) + 2)                 # the expected clocks
    lines[base + 21] = str((int(lines[base + 21]) + 1) & 0xffffffff)    # the expected D0 of the final state
    path = work / 'self-check.vectors'
    path.write_text(' '.join(lines) + '\n', encoding='ascii', newline='\n')
    row = json.loads(next(line for line in run([program, path], cwd=work).splitlines() if line.startswith('{')))
    found = []
    if 'd0' not in row['regs'].split():
        found.append('self-check: a corrupted D0 was not seen')
    if row['cyc'] == int(lines[1]):
        found.append('self-check: corrupted clocks were not seen')
    return found


def main(argv: list[str]) -> int:
    workspace, rest = workspace_of(argv)
    import retrorecomp.paths as paths
    if workspace != ROOT:
        paths.ROOT, paths.ASSETS = workspace, ROOT       # the workspace's `.deps` and `.build`, this tree's sources
    names = [item for item in rest if not item.startswith('--')] or list(FIXTURES)
    work = work_dir(workspace)
    work.mkdir(parents=True, exist_ok=True)
    core = ensure_core(workspace, work)
    # Two builds of the harness: the first (no steps) writes the opcode table the generator names Moira's handlers from; the second links the steps.
    first = build_harness(work, core, None)
    samples = sorted({code_sample(test) for name in names for test in selection(name)[0]})
    stats = generate_steps(work, first, samples)
    program = build_harness(work, core, work / 'generated')
    print(f"native steps: {stats['instructions']} instructions of {len(samples)} observed, {stats['forms']} forms, "
          f"opcode table {stats['opcode_table_sha256'][:16]}")
    failed = 0
    evaluations, replayed = [], []
    for name in names:
        result = replay(name, program, work)
        evaluations.append(evaluate(result))
        replayed.append(result)
    main_offsets = {e['main_offset'] for e in evaluations if e['totals']['bus_checked']}
    if len(main_offsets) > 1:
        print('PROBLEM the fixtures disagree on the clock of an access relative to the vector:', sorted(main_offsets))
        failed += 1
    for evaluated, result in zip(evaluations, replayed):
        print(summary(evaluated, result))
        for line in family_lines(evaluated):
            print(line)
        for text in problems(evaluated, result):
            failed += 1
            print('PROBLEM', text)
    total = {key: sum(e['totals'][key] for e in evaluations) for key in evaluations[0]['totals']}
    print(f"all fixtures: {total['run']} vectors replayed; native steps ran for {total['native_step']}, equal to the interpreter {total['native_equal']}, "
          f"differ {total['native_differ']}, no step {total['native_none']}; Moira against the vectors: {total['all_ok']} agree on everything, "
          f"{total['deviating']} differ ({total['in_a_family']} in a family, {total['unexplained']} in none)")
    if '--no-self-check' not in argv:
        for text in self_check(program, work, replayed[0]):
            failed += 1
            print('PROBLEM', text)
    (work / 'results.json').write_text(json.dumps([
        {'fixture': e['fixture'], 'totals': e['totals'], 'main_offset': e['main_offset'],
         'families': [{'name': f.name, 'key': list(f.key), 'count': e['covered'].get(f.key + (n,), 0), 'recorded': f.count}
                      for n, f in enumerate(FAMILIES) if f.fixture == e['fixture']]} for e in evaluations], indent=1) + '\n', encoding='utf-8')
    print('main offset of an access against the vector start (clocks):', sorted(main_offsets))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
