"""Moira (MIT) against the Mega Drive's native 68000 steps on forms the SingleStepTests vectors do not hold (gate G10, slice 1: evidence only).

    python -B tools/megadrive_moira_vectors.py [--seed N] [--count N] [--skip-exhaustive] [--exhaustive-only] [--write FILE]
        (RETRO_RECOMP_TOOLCHAIN=llvm; needs a compiler and, on the first run, a build of vAmiga's Core; no ROM, no Kickstart, no window)

What it does, in order:
  1. builds the "Moira vector maker" (`native/amiga_machine/moira_vector_maker.cpp`): the Moira that vAmiga's Core compiles (MIT; the pinned
     revision, adapted by `retrorecomp/amiga_vamiga.py`) behind a flat 24-bit memory, linked the way `tools/amiga_vector_selftest.py` links
     its harness;
  2. chooses states for the forms below from a fixed seed, has Moira execute each one instruction, and writes what Moira did as a
     SingleStepTests-format fixture under `.build/md-moira/vectors/` (registers, queue, memory, ordered bus transactions with their clocks,
     total clocks). Made from MIT code, the fixture is not committed: every run regenerates it from the seed and prints the counts;
  3. replays that fixture through the Mega Drive's generator and native steps as `tools/megadrive_groups_selftest.py` replays the others
     (`tools/megadrive_prefetch_selftest.build`, with a copy of the harness that lists every field that differs, not only the first),
     and sorts every difference into a family (`classify`): a known difference of model, a decimal result on digits that are not decimal,
     a clock (a lead), or "unexplained" (the run fails);
  4. for ABCD, SBCD and NBCD (register forms) compares the native step and the reference path with Moira on every state: 256 x 256 operand
     bytes x X x Z x the initial N, V, C (all clear or all set); NBCD: 256 bytes x X x Z x the same. No bus there. V is told apart (the
     manual leaves it undefined after these instructions);
  5. runs Moira on the 114 decimal vectors of `tests/fixtures/m68k-groups` (22 of which the pinned native model does not reproduce) and counts
     the vectors it reproduces whole (registers, SR under the vector's mask, queue, memory, clocks, bus).

The forms: ADDI, SUBI, ANDI, ORI, EORI (long) and CMPI (byte, word, long) on every memory mode of the 68000: (An), (An)+, -(An),
(d16,An), (d8,An,Xn), abs.W, abs.L; the same five immediates in byte and word on -(An) and (d8,An,Xn) as a control; ABCD and SBCD (Dy,Dx and
-(Ay),-(Ax)); NBCD (Dn and every memory mode).

What it shows and what it does not: the native steps, and the interpreter text they come from, against one independent software model of the
chip on random states of these forms. Moira is a model, not silicon, and the SingleStepTests vectors were made with MAME: where the two
disagree (the order of the two writes of a long result, `FAMILIES`) the Mega Drive follows the vectors and this tool cannot arbitrate. A clock
difference found here is a lead, to be checked against a manual or MAME before any rule is touched, never a fault proved. Nothing is said of
hardware fidelity, gameplay or latency, and nothing of the Mega Drive's own bus, VDP or exceptions (flat bus, even addresses except bytes).
"""
from __future__ import annotations
import argparse
import collections
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = 174
COUNT = 48                      # vectors of each form (an operation, a size and an addressing mode)
CONTROL_COUNT = 24
CODE_BASE = 0x100000            # one instruction per 0x100 bytes: inside the 4 MiB image the replay builds, apart from every operand
DATA_LOW, DATA_HIGH = 0x200000, 0xF00000
REGS = [*(f'd{i}' for i in range(8)), *(f'a{i}' for i in range(7)), 'usp', 'ssp', 'sr', 'pc']
SR_MASK_DECIMAL = 0xfffd        # V is documented undefined after the decimal instructions (the groups fixture masks it too)

IMMEDIATE = {'ORI': 0x0000, 'ANDI': 0x0200, 'SUBI': 0x0400, 'ADDI': 0x0600, 'EORI': 0x0A00, 'CMPI': 0x0C00}
SIZE_BITS = {'b': 0, 'w': 1, 'l': 2}
SIZE_BYTES = {'b': 1, 'w': 2, 'l': 4}
MODES = ('(An)', '(An)+', '-(An)', '(d16,An)', '(d8,An,Xn)', 'abs.W', 'abs.L')
MODE_FIELDS = {'(An)': (2, None), '(An)+': (3, None), '-(An)': (4, None), '(d16,An)': (5, None), '(d8,An,Xn)': (6, None),
               'abs.W': (7, 0), 'abs.L': (7, 1)}
MAIN_IMMEDIATE = [(op, 'l') for op in ('ADDI', 'SUBI', 'ANDI', 'ORI', 'EORI')] + [('CMPI', 'b'), ('CMPI', 'w'), ('CMPI', 'l')]
CONTROL_IMMEDIATE = [(op, size) for op in ('ADDI', 'SUBI', 'ANDI', 'ORI', 'EORI') for size in ('b', 'w')]
CONTROL_MODES = ('-(An)', '(d8,An,Xn)')
DECIMAL = ('ABCD', 'SBCD', 'NBCD')
# The register forms the exhaustive check runs: the instruction word and its address in the replay image.
EXHAUSTIVE = {'abcd': 0xC101, 'sbcd': 0x8101, 'nbcd': 0x4800}      # ABCD D1,D0; SBCD D1,D0; NBCD D0
EXHAUSTIVE_PC = {'abcd': 0x100000, 'sbcd': 0x100100, 'nbcd': 0x100200}
FIELD_BITS = {'R': 1, 'X': 2, 'C': 4, 'N': 8, 'Z': 16, 'V': 32}


def form_name(form: dict) -> str:
    suffix = '' if form['op'] in DECIMAL else '.' + form['size']
    return f"{form['op']}{suffix} {form['mode']}"


def form_list(count: int = COUNT) -> list[dict]:
    """Every form in a fixed order: {'op', 'size', 'mode', 'count', 'role', 'group'}; a form is an operation, a size and an addressing mode."""
    forms = []
    for op, size in MAIN_IMMEDIATE:
        forms += [{'op': op, 'size': size, 'mode': mode, 'count': count, 'role': 'missing form'} for mode in MODES]
    for op, size in CONTROL_IMMEDIATE:
        forms += [{'op': op, 'size': size, 'mode': mode, 'count': CONTROL_COUNT, 'role': 'control'} for mode in CONTROL_MODES]
    for op in ('ABCD', 'SBCD'):
        forms += [{'op': op, 'size': 'b', 'mode': mode, 'count': count, 'role': 'decimal'} for mode in ('Dy,Dx', '-(Ay),-(Ax)')]
    forms += [{'op': 'NBCD', 'size': 'b', 'mode': mode, 'count': count, 'role': 'decimal'} for mode in ('Dn', *MODES)]
    for form in forms:
        form['group'] = form_name(form)
    return forms


# ------------------------------------------------------------------------------------------------------------------ choosing the states
def to_signed(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def corner_or_random(rng: random.Random, bits: int) -> int:
    """A value of `bits` bits: one time in three a corner (0, 1, all ones, the sign bit, the largest positive, the first negative), else random."""
    corners = (0, 1, (1 << bits) - 1, 1 << (bits - 1), (1 << (bits - 1)) - 1, (1 << (bits - 1)) + 1)
    return rng.choice(corners) if rng.random() < 1 / 3 else rng.getrandbits(bits)


def decimal_byte(rng: random.Random, decimal: bool) -> int:
    """A byte of two decimal digits when `decimal`, otherwise any byte."""
    return rng.randrange(10) << 4 | rng.randrange(10) if decimal else rng.getrandbits(8)


def is_decimal(value: int) -> bool:
    return (value >> 4) <= 9 and (value & 15) <= 9


def stack_key(state: dict) -> str:
    """The register that A7 is in this state: the supervisor stack pointer in supervisor mode, else the user one."""
    return 'ssp' if state['sr'] & 0x2000 else 'usp'


def set_address_register(state: dict, number: int, value: int) -> None:
    state[stack_key(state) if number == 7 else f'a{number}'] = value & 0xffffffff


def operand_address(rng: random.Random, size: int) -> int:
    """Where an operand is: even (an odd byte address one time in two for a byte), well away from the code and below the 24-bit limit."""
    return rng.randrange(DATA_LOW, DATA_HIGH) & ~1 | (1 if size == 1 and rng.random() < 0.5 else 0)


def effective_address(rng: random.Random, mode: str, state: dict, words: list[int], base: int, size: int) -> int:
    """Make a memory mode reach a chosen operand: sets the address register (and the index register) in `state`, appends the mode's extension
    words to `words`, puts the mode and register in the instruction word `words[0]` (`base` is the word without them) and returns the
    operand's address."""
    field, register = MODE_FIELDS[mode]
    address = operand_address(rng, size)
    if mode == 'abs.W':
        address = (rng.randrange(0x2000, 0x7ffe) if rng.random() < 0.5 else rng.randrange(0xff8000, 0xfffff0)) & ~1 | (address & 1)
        words.append(address & 0xffff)
        words[0] = base | field << 3 | register
        return address
    if mode == 'abs.L':
        words.extend([address >> 16, address & 0xffff])
        words[0] = base | field << 3 | register
        return address
    an = rng.randrange(8)
    parity = address & 1
    if mode in ('(An)', '(An)+'):
        value = address
    elif mode == '-(An)':
        value = address + (2 if an == 7 and size == 1 else size)
    elif mode == '(d16,An)':
        displacement = rng.randrange(-0x8000, 0x8000) & ~1 | parity
        value = address - to_signed(displacement, 16)
        words.append(displacement & 0xffff)
    else:
        displacement = to_signed(rng.randrange(-128, 128) & ~1 | parity, 8)
        index_is_address = rng.random() < 0.3
        index_long = rng.random() < 0.5
        index = rng.randrange(7 if index_is_address else 8)
        while index_is_address and index == an:
            index = rng.randrange(7)
        reach = 0x100000 if index_long else 0x4000
        index_value = rng.randrange(-reach, reach) & ~1                         # the value the instruction adds (sign-extended word or long)
        register_value = index_value & (0xffffffff if index_long else 0xffff)
        if not index_long and rng.random() < 0.5:
            register_value |= rng.getrandbits(16) << 16                          # the upper word of a word index is ignored
        value = address - displacement - index_value
        words.append((1 << 15 if index_is_address else 0) | index << 12 | (1 << 11 if index_long else 0) | displacement & 0xff)
        state[('a' if index_is_address else 'd') + str(index)] = register_value
    words[0] = base | field << 3 | an
    set_address_register(state, an, value)
    if an != 7 and rng.random() < 1 / 16:
        state[f'a{an}'] |= rng.getrandbits(8) << 24                              # the 24-bit bus ignores the upper byte
    return address


def make_state(rng: random.Random, form: dict, serial: int) -> dict:
    """The initial state of one vector: the registers, `words` (the instruction, then two words after it), `seed` and `over` (bytes to set,
    {address: byte}; every other byte Moira reads is a hash of the seed and the address), with `meta` for the classifier."""
    op, size, mode = form['op'], form['size'], form['mode']
    nbytes = SIZE_BYTES[size]
    state: dict = {name: rng.getrandbits(32) for name in REGS[:15]}
    state['usp'] = rng.randrange(DATA_LOW, DATA_HIGH) & ~1
    state['ssp'] = rng.randrange(DATA_LOW, DATA_HIGH) & ~1
    state['sr'] = (0x2000 if rng.random() < 0.75 else 0) | rng.randrange(8) << 8 | rng.getrandbits(5)
    state['pc'] = CODE_BASE + 0x100 * serial
    words: list[int] = []
    over: dict[int, int] = {}
    meta: dict = {}
    if op in IMMEDIATE:
        base = IMMEDIATE[op] | SIZE_BITS[size] << 6
        if size == 'l':
            immediate = corner_or_random(rng, 32)
            words = [0, immediate >> 16, immediate & 0xffff]
        else:
            immediate = corner_or_random(rng, 8 * nbytes)
            words = [0, immediate]
        address = effective_address(rng, mode, state, words, base, nbytes)
        value = corner_or_random(rng, 8 * nbytes)
        for n in range(nbytes):
            over[address + n] = value >> 8 * (nbytes - 1 - n) & 0xff
        meta = {'address': address}
    elif op in ('ABCD', 'SBCD') and mode == 'Dy,Dx':
        x, y = rng.randrange(8), rng.randrange(8)
        words = [(0xC100 if op == 'ABCD' else 0x8100) | x << 9 | y]
        decimal = rng.random() < 0.5
        for register in (x, y):
            state[f'd{register}'] = state[f'd{register}'] & ~0xff | decimal_byte(rng, decimal)
        meta = {'operands': [state[f'd{y}'] & 0xff, state[f'd{x}'] & 0xff]}
        if x == y:
            meta = {'operands': [state[f'd{x}'] & 0xff] * 2}
    elif op in ('ABCD', 'SBCD'):
        x, y = rng.randrange(8), rng.randrange(8)
        words = [(0xC108 if op == 'ABCD' else 0x8108) | x << 9 | y]
        decimal = rng.random() < 0.5
        step = lambda register: 2 if register == 7 else 1                        # a byte through A7 moves it by two
        source = rng.randrange(DATA_LOW, DATA_HIGH)
        destination = rng.randrange(DATA_LOW, DATA_HIGH)
        if x == y:
            source, destination = destination, destination - step(x)              # the same register: the source first, then the destination under it
            set_address_register(state, y, source + step(y))
        else:
            set_address_register(state, y, source + step(y))
            set_address_register(state, x, destination + step(x))
        over[source], over[destination] = decimal_byte(rng, decimal), decimal_byte(rng, decimal)
        meta = {'operands': [over[source], over[destination]]}
    elif op == 'NBCD' and mode == 'Dn':
        n = rng.randrange(8)
        words = [0x4800 | n]
        state[f'd{n}'] = state[f'd{n}'] & ~0xff | decimal_byte(rng, rng.random() < 0.5)
        meta = {'operands': [state[f'd{n}'] & 0xff]}
    else:                                                                         # NBCD on a memory operand
        words = [0]
        address = effective_address(rng, mode, state, words, 0x4800, 1)
        over[address] = decimal_byte(rng, rng.random() < 0.5)
        meta = {'operands': [over[address]], 'address': address}
    length = len(words)
    words += [rng.getrandbits(16), rng.getrandbits(16)]                            # the queue after the instruction holds the next word at least
    state.update(words=words, length=length, seed=rng.getrandbits(48), over=over, meta=meta)
    return state


def make_states(seed: int = SEED, count: int = COUNT) -> list[tuple[dict, dict]]:
    """[(form, state)] for every vector of every form, in a fixed order. The same seed and count always give the same states."""
    states, serial = [], 0
    for form in form_list(count):
        rng = random.Random(f'{seed}:{form["group"]}')
        for _ in range(form['count']):
            states.append((form, make_state(rng, form, serial)))
            serial += 1
    return states


# ------------------------------------------------------------------------------------------------------------------------- the maker
def input_line(index: int, state: dict) -> str:
    """One line of the maker's input (see native/amiga_machine/moira_vector_maker.cpp)."""
    fields = [index, *(state[name] for name in REGS), len(state['words']), *state['words'], state['seed'], len(state['over'])]
    for address, value in sorted(state['over'].items()):
        fields += [address, value]
    return ' '.join(str(field) for field in fields)


def parse_output_line(line: str) -> dict:
    """One line of the maker's output: the index, the clock, the registers, the accesses (kind, clock, address, size, value) and the bytes touched."""
    numbers = [int(token) for token in line.split()]
    index, clock, values, rest = numbers[0], numbers[1], numbers[2:23], numbers[23:]
    accesses = [tuple(rest[1 + 5 * n:6 + 5 * n]) for n in range(rest[0])]
    rest = rest[1 + 5 * rest[0]:]
    touched = [tuple(rest[1 + 3 * n:4 + 3 * n]) for n in range(rest[0])]
    return {'index': index, 'clock': clock, 'regs': dict(zip(REGS + ['ird', 'irc'], values)), 'accesses': accesses, 'bytes': touched}


def transactions(accesses: list[tuple], total: int, supervisor: bool, program: range) -> list[list]:
    """The bus cycles of a SingleStepTests vector from Moira's accesses: each takes four clocks and Moira makes it two clocks in; the gaps
    are idle periods ('n'). A byte at an even address is on the upper half of the bus, at an odd address on the lower half."""
    clock, found = 0, []
    for kind, at, address, size, value in accesses:
        start = at - 2
        if start < clock:
            raise ValueError('Two bus cycles overlap')
        if start > clock:
            found.append(['n', start - clock])
        odd = address & 1
        data = value if size == 2 or odd else value << 8
        space = 2 if address in program else 1
        found.append(['w' if kind else 'r', 4, space + (4 if supervisor else 0), address & 0xfffffe, '.w' if size == 2 else '.b', data,
                      int(size == 2 or not odd), int(size == 2 or bool(odd))])
        clock = start + 4
    if total < clock:
        raise ValueError('A bus cycle ends after the instruction')
    if total > clock:
        found.append(['n', total - clock])
    return found


def vector(number: int, form: dict, state: dict, run: dict) -> dict:
    """A SingleStepTests-format vector from a state and what Moira did with it. Its `group` is the number (the harness prints it first)."""
    pc, length = state['pc'], state['length']
    final = run['regs']
    if final['pc'] != pc + 2 * length:
        raise ValueError(f"{form['group']}: Moira did not run straight on (pc {final['pc']:06x})")
    ram_in = [[address, initial] for address, initial, _ in sorted(run['bytes'])]
    ram_out = [[address, after] for address, _, after in sorted(run['bytes'])]
    initial = {name: state[name] for name in REGS[:18]}
    initial.update(pc=pc + 4, prefetch=[state['words'][0], state['words'][1]], ram=ram_in)
    after = {name: final[name] for name in REGS[:18]}
    after.update(pc=final['pc'] + 4, prefetch=[final['ird'], final['irc']], ram=ram_out)
    program = range(pc, pc + 2 * len(state['words']))
    test = {'group': f'{number:05d}', 'name': form['group'], 'initial': initial, 'final': after, 'length': run['clock'],
            'transactions': transactions(run['accesses'], run['clock'], bool(state['sr'] & 0x2000), program)}
    if form['op'] in DECIMAL:
        test['sr_mask'] = SR_MASK_DECIMAL
    return test


def fixture_header(seed: int, count: int, vectors: int) -> dict:
    from retrorecomp import amiga_vamiga
    return {'source': 'Moira (MIT, Dirk W. Hoffmann) as vAmiga builds it, run by tools/megadrive_moira_vectors.py; not committed, regenerated from the seed',
            'revision': amiga_vamiga.VAMIGA_REV, 'seed': seed, 'count': count, 'vectors': vectors,
            'scope': 'ADDI/SUBI/ANDI/ORI/EORI.l and CMPI.b/.w/.l on every memory mode, ABCD, SBCD, NBCD; random states, flat bus, even addresses except bytes.',
            'excluded': 'Address errors, exceptions, interrupts, trace; V after the decimal instructions (masked by sr_mask).'}


def run_maker(maker: Path, work: Path, states: list[tuple[dict, dict]]) -> list[dict]:
    """Moira's result for every state (the maker, one process)."""
    from retrorecomp.core import run
    source, target = work / 'states.txt', work / 'moira-out.txt'
    source.write_text('\n'.join(input_line(i, state) for i, (_, state) in enumerate(states)) + '\n', encoding='ascii', newline='\n')
    run([maker, '--states', source, target], cwd=work)
    results = [parse_output_line(line) for line in target.read_text(encoding='ascii').splitlines() if line.strip()]
    if [row['index'] for row in results] != list(range(len(states))):
        raise RuntimeError('The maker did not run every state')
    return results


def write_fixture(folder: Path, states: list[tuple[dict, dict]], results: list[dict], seed: int, count: int) -> list[dict]:
    """`cases.json` of the fixture in `folder`, and `meta.json` (what the classifier needs from each state); returns the vectors."""
    tests = [vector(index, form, state, run) for index, ((form, state), run) in enumerate(zip(states, results))]
    folder.mkdir(parents=True, exist_ok=True)
    document = fixture_header(seed, count, len(tests)) | {'tests': tests}
    (folder / 'cases.json').write_text(json.dumps(document, separators=(',', ':')), encoding='utf-8', newline='\n')
    meta = [{'group': form['group'], 'op': form['op'], 'size': form['size'], 'mode': form['mode'], 'role': form['role'], **state['meta']}
            for form, state in states]
    (folder / 'meta.json').write_text(json.dumps(meta, separators=(',', ':')), encoding='utf-8', newline='\n')
    return tests


# --------------------------------------------------------------------------------------------------------------------------- the replay
ALL_FIELDS_PATCHES = (
    ('static unsigned failed_cases;\n', 'static unsigned failed_cases;\nstatic int case_flagged;   /* RR_MD_COLLECT_ALL */\n'),
    ('    ++failed_cases;\n    longjmp(case_failed, 1);\n',
     '    if (getenv("RR_MD_COLLECT_ALL")) { if (!case_flagged) { case_flagged = 1; ++failed_cases; } return; }\n'
     '    ++failed_cases;\n    longjmp(case_failed, 1);\n'),
    ('static void run_case(const CorpusCase *test) {\n', 'static void run_case(const CorpusCase *test) {\n    case_flagged = 0;\n'),
    ('    for(unsigned i=0;i<tx_count;++i) {\n', '    for(unsigned i=0;i<tx_count && i<test->transaction_count;++i) {\n'),
)


def all_fields_harness(text: str) -> str:
    """The text of `native/md_prefetch_checks.c` with one more mode: with `RR_MD_COLLECT_ALL` set (and `RR_MD_COLLECT_FAILURES`), a vector goes
    on after a field that differs and lists every one, instead of ending at the first. Each replacement must find its text exactly once;
    without the variable the program is the one the file holds. The file itself is a Mega Drive stamp input and stays as it is."""
    for old, new in ALL_FIELDS_PATCHES:
        if text.count(old) != 1:
            raise ValueError('The harness changed: ' + old.strip()[:40])
        text = text.replace(old, new)
    return text


FAIL = re.compile(r'^FAIL (\d+): (.*) (native|reference) (.+?) expected=(\S+) actual=(\S+)$')
TX = re.compile(r'(\w)@(\d+):([0-9a-f]+)=([0-9a-f]+)')


def category(field: str) -> str:
    """What a field of the harness's report is about: regs, sr, pc, memory, clocks, queue, bus, or other (the step's status, a fallback)."""
    if field.startswith('register['):
        number = int(field[9:-1])
        return 'sr' if number == 17 else 'pc' if number == 18 else 'regs'
    if field.startswith('memory['):
        return 'memory'
    if field in ('audio cycles', 'CPU cycles'):
        return 'clocks'
    if field.startswith('queue'):
        return 'queue'
    if field == 'transaction count' or field.startswith('bus['):
        return 'bus'
    return 'other'


def parse_report(text: str) -> dict[str, dict[int, dict]]:
    """The harness's stderr of a run with RR_MD_COLLECT_ALL and RR_MD_COLLECT_TX: {'native': {vector: {'fields': [(field, expected, actual)],
    'vector_tx': [...], 'actual_tx': [...]}}, 'reference': {...}}; a transaction is (kind, clock, address, data)."""
    found: dict = {'native': {}, 'reference': {}}
    current = None
    for line in text.splitlines():
        match = FAIL.match(line.strip())
        if match:
            record = found[match[3]].setdefault(int(match[1]), {'fields': [], 'vector_tx': None, 'actual_tx': None})
            record['fields'].append((match[4], int(match[5], 16), int(match[6], 16)))
            current = record
        elif current is not None and line.startswith('  vector:'):
            current['vector_tx'] = [(k, int(c), int(a, 16), int(d, 16)) for k, c, a, d in TX.findall(line)]
        elif current is not None and line.startswith('  actual:'):
            current['actual_tx'] = [(k, int(c), int(a, 16), int(d, 16)) for k, c, a, d in TX.findall(line)]
    return found


# ----------------------------------------------------------------------------------------------------------------------- the families
def bus_flags(vector_tx: list, actual_tx: list) -> tuple[set[str], list[int]] | None:
    """How two bus sequences of the same instruction differ, if every difference is one of three kinds: a cycle at another clock (same kind,
    address and data: 'clock placement'), the data of a write (same kind, clock and address: 'write data'), or two consecutive writes in the
    other order ('long write order': the same clocks, Moira's high word first, that is the lower address, the run's low word first). Returns the
    kinds and the clock shifts (run minus vector) of the cycles that moved; None when anything else differs or the lengths differ."""
    if not vector_tx or not actual_tx or len(vector_tx) != len(actual_tx):
        return None
    flags: set[str] = set()
    shifts: list[int] = []
    i = 0
    while i < len(vector_tx):
        (kind, clock, address, data), (kind2, clock2, address2, data2) = vector_tx[i], actual_tx[i]
        if vector_tx[i] == actual_tx[i]:
            i += 1
        elif (kind, address, data) == (kind2, address2, data2):
            flags.add('clock placement')
            shifts.append(clock2 - clock)
            i += 1
        elif (kind, clock, address) == (kind2, clock2, address2) and kind == 'w':
            flags.add('write data')
            i += 1
        elif (i + 1 < len(vector_tx) and kind == 'w' == kind2 and vector_tx[i + 1][0] == 'w' == actual_tx[i + 1][0] and clock == clock2
              and vector_tx[i + 1][1] == actual_tx[i + 1][1] and vector_tx[i + 1][2] == address + 2
              and actual_tx[i] == ('w', clock, address + 2, vector_tx[i + 1][3]) and actual_tx[i + 1] == ('w', vector_tx[i + 1][1], address, data)):
            flags.add('long write order')
            i += 2
        else:
            return None
    return flags, shifts


def swapped_long_writes(vector_tx: list, actual_tx: list) -> bool:
    """Whether the sequences are equal but for pairs of writes in the other order (see `bus_flags`)."""
    found = bus_flags(vector_tx, actual_tx)
    return found is not None and found[0] == {'long write order'}


class Family:
    """A named kind of difference between Moira and the native step: what it is, why, and how it was established."""

    def __init__(self, name: str, status: str, reason: str):
        self.name, self.status, self.reason = name, status, reason


FAMILIES = {
    'long write order': Family(
        'long write order', 'known model difference',
        'The two writes of a long result to memory: Moira writes the high word first, the SingleStepTests vectors (made with MAME) and the Mega '
        'Drive since 1.6.8 the low word first. Same clocks, same addresses and values, same final memory (tools/amiga_vector_selftest.py has '
        'the same family for ADD.l, SUB.l, ADDQ.l, SUBQ.l, ADDI.l, SUBI.l). Moira cannot arbitrate it.'),
    'undefined decimal digits': Family(
        'undefined decimal digits', 'known, expected',
        'ABCD, SBCD or NBCD on an operand that is not two decimal digits: the manual leaves the result undefined; the pinned interpreter '
        'rounds each nibble, Moira (like MAME) follows the chip. docs/CPU_68000.md lists the 22 vectors of the groups fixture. On a memory form '
        'the wrong byte is also the data of the write cycle.'),
    'idle clock placement': Family(
        'idle clock placement', 'lead',
        'Same cycles, same addresses, values and total clocks, but the first cycles come later in the run than in Moira: the two internal '
        'clocks of a -(An) or (d8,An,Xn) destination are spent before the first fetch, Moira spends them after the word that follows the '
        'immediate (native/md_prefetch.inc rr_pf_idle_after_first covers ADDI, SUBI, ANDI, ORI, EORI in byte and word and the bit instructions '
        'with an immediate bit number; not the long forms, not CMPI).'),
    'clocks': Family('clocks', 'lead', 'The total clocks differ: a lead (manual, MAME), not a fault proved; Moira is wrong against MAME in BTST and CHK.'),
}


def classify(outcome: dict, meta: dict) -> dict:
    """The families of one vector that differs (`outcome` is a record of `parse_report`, `meta` the vector's line of meta.json):
    {'categories': {...}, 'families': {...}, 'unexplained': {...}, 'shifts': [...]}. A category is explained by a family or stays in `unexplained`."""
    categories = {category(field) for field, _, _ in outcome['fields']}
    covered: set[str] = set()
    families: set[str] = set()
    shifts: list[int] = []
    operands = meta.get('operands')
    undefined = meta['op'] in DECIMAL and bool(operands) and not all(is_decimal(value) for value in operands)
    if undefined and categories & {'regs', 'sr', 'memory'}:
        covered |= categories & {'regs', 'sr', 'memory'}
        families.add('undefined decimal digits')
    if 'bus' in categories:
        found = bus_flags(outcome['vector_tx'] or [], outcome['actual_tx'] or [])
        if found is not None and ('write data' not in found[0] or (undefined and 'memory' in categories)):
            covered.add('bus')
            shifts = found[1]
            families |= {name for flag, name in (('long write order', 'long write order'), ('clock placement', 'idle clock placement')) if flag in found[0]}
    if 'clocks' in categories:
        families.add('clocks')
    return {'categories': categories, 'families': families, 'unexplained': categories - covered - {'clocks'}, 'shifts': shifts}


def clock_delta(outcome: dict) -> int | None:
    """The run's total clocks minus the vector's, where the harness reported them."""
    for field, expected, actual in outcome['fields']:
        if field == 'CPU cycles':
            return actual - expected
    return None


def evaluate(forms_meta: list[dict], tests: list[dict], report: dict) -> dict:
    """Per form: the vectors, how many agree on every check, in which categories the others differ and into which families they fall."""
    rows: dict[str, dict] = {}
    for number, (meta, test) in enumerate(zip(forms_meta, tests)):
        row = rows.setdefault(meta['group'], {'role': meta['role'], 'vectors': 0, 'whole': 0, 'categories': collections.Counter(),
                                              'families': collections.Counter(), 'unexplained': collections.Counter(),
                                              'clock_deltas': collections.Counter(), 'shifts': collections.Counter(), 'examples': []})
        row['vectors'] += 1
        outcome = report['native'].get(number)
        if outcome is None:
            row['whole'] += 1
            continue
        verdict = classify(outcome, meta)
        row['categories'].update(verdict['categories'])
        row['families'].update(verdict['families'])
        row['unexplained'].update(verdict['unexplained'])
        if verdict['shifts']:
            row['shifts']['/'.join(f'{shift:+d}' for shift in verdict['shifts'])] += 1
        delta = clock_delta(outcome)
        if delta is not None:
            row['clock_deltas'][delta] += 1
        if verdict['unexplained'] and len(row['examples']) < 3:
            row['examples'].append({'vector': number, 'name': test['name'], 'fields': outcome['fields'][:6]})
    return rows


def existing_vectors() -> collections.Counter:
    """How many vectors of the repository's four fixtures hold each form of this tool (by `form_name`): what exists today, to set beside
    the run. The immediate instructions and the decimal ones are told by their opcode and its mode field."""
    found: collections.Counter = collections.Counter()
    for name in ('m68k-groups', 'md-prefetch', 'm68k-shifts', 'md-exceptions'):
        tests = json.loads((ROOT / 'tests' / 'fixtures' / name / 'cases.json').read_text(encoding='utf-8'))['tests']
        if name == 'md-prefetch':
            tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
        for test in tests:
            word = test['initial']['prefetch'][0]
            mode, register = word >> 3 & 7, word & 7
            op = next((n for n, base in IMMEDIATE.items() if word >> 8 == base >> 8), None)
            if op and word >> 6 & 3 != 3 and (op != 'ORI' or word >> 8 == 0) and (word & 0xff3f) not in (0x003c, 0x007c, 0x023c, 0x027c, 0x0a3c, 0x0a7c):
                if mode == 7 and register > 1:
                    continue
                label = 'Dn' if mode == 0 else MODES[mode - 2] if mode < 7 else ('abs.W', 'abs.L')[register]
                found[f"{op}.{'bwl'[word >> 6 & 3]} {label}"] += 1
            elif word & 0xffc0 == 0x4800:
                label = 'Dn' if mode == 0 else MODES[mode - 2] if mode < 7 else ('abs.W', 'abs.L')[register] if register < 2 else '?'
                found[f'NBCD {label}'] += 1
            elif word & 0xf1f0 in (0xC100, 0x8100):
                found[('ABCD' if word >> 12 == 0xC else 'SBCD') + (' -(Ay),-(Ax)' if word & 8 else ' Dy,Dx')] += 1
    return found


# ----------------------------------------------------------------------------------------------------------------------------- running
def work_dir() -> Path:
    return ROOT / '.build' / 'md-moira'


def write_cmake(work: Path, core: Path) -> Path:
    """The CMake project of the maker: vAmiga's adapted Core as a static library and the maker's source, linked with the maker's definitions
    of the CPU's client API first (the first definition wins), as `tools/amiga_vector_selftest.py` links its harness."""
    maker = (ROOT / 'native' / 'amiga_machine' / 'moira_vector_maker.cpp').as_posix()
    folder = work / 'cmake'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroMoiraVectorMaker LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory("{core.as_posix()}" vacore)
# vAmiga's warnings-as-errors stay on its own files.
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
add_executable(moira_vector_maker "{maker}")
target_link_libraries(moira_vector_maker PRIVATE VACore)
if(MSVC)
    target_link_options(moira_vector_maker PRIVATE /FORCE:MULTIPLE)
else()
    target_link_options(moira_vector_maker PRIVATE -Wl,--allow-multiple-definition)
endif()
if(WIN32)
    target_link_libraries(moira_vector_maker PRIVATE ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    return folder


def build_maker(work: Path) -> Path:
    """The maker's executable (the adapted vAmiga Core is compiled on the first run, several minutes; later runs only link)."""
    from retrorecomp import amiga_vamiga
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    work.mkdir(parents=True, exist_ok=True)
    core = amiga_vamiga.adapt(amiga_vamiga.source(), work / 'vamiga')
    folder = write_cmake(work, core)
    build = work / 'build'
    cmake, generator = toolchain()
    run([cmake, '-S', folder, '-B', build, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=work / 'build.log', cwd=work)
    run([cmake, '--build', build, '--parallel', build_jobs(), '--target', 'moira_vector_maker'], log=work / 'build.log', timeout=7200, cwd=work)
    return build_executable(build, 'moira_vector_maker')


def replay_forms(work: Path, folder: Path, project_name: str = 'md-moira-forms', with_bus: bool = True) -> tuple[str, dict]:
    """Replay the fixture in `folder` through the Mega Drive's generator and steps with the harness that lists every field that differs;
    returns its report (stderr, with the bus lists of each failing vector when `with_bus`) and its own summary line."""
    from tools import megadrive_prefetch_selftest as replay
    harness = work / 'md_prefetch_checks_all.c'
    harness.write_text(all_fields_harness((ROOT / 'native' / 'md_prefetch_checks.c').read_text(encoding='utf-8')), encoding='utf-8', newline='\n')
    project, checks, _, _, _ = replay.build(project_name, folder=folder, harness=harness)
    done = subprocess.run([str(checks)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3600,
                          env={**os.environ, 'RR_MD_COLLECT_FAILURES': '1', 'RR_MD_COLLECT_ALL': '1', **({'RR_MD_COLLECT_TX': '1'} if with_bus else {})},
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if done.returncode not in (0, 1):
        sys.exit(f'the replay ended with status {done.returncode}:\n{done.stderr[-2000:]}')
    (work / f'{project_name}-stderr.txt').write_text(done.stderr, encoding='utf-8', newline='\n')
    summary = next((json.loads(line) for line in done.stdout.splitlines() if line.startswith('{')), {})
    return done.stderr, summary


def exhaustive(maker: Path, work: Path) -> dict:
    """The decimal instructions' register forms on every state, Moira against the native step and the reference path."""
    from retrorecomp.core import run
    from tools import megadrive_prefetch_selftest as replay
    folder = work / 'bcd-vectors'
    folder.mkdir(parents=True, exist_ok=True)
    tests = []
    for kind, word in EXHAUSTIVE.items():
        pc = EXHAUSTIVE_PC[kind]
        state = dict.fromkeys(REGS, 0) | {'ssp': 0x310000, 'sr': 0x2700, 'pc': pc + 4, 'prefetch': [word, 0x4e71]}
        code = [[pc + n, byte] for n, byte in enumerate(bytes([word >> 8, word & 255, 0x4e, 0x71, 0x4e, 0x71]))]
        tests.append({'group': kind, 'name': kind, 'initial': state | {'ram': code}, 'final': state | {'pc': pc + 6, 'ram': code},
                      'transactions': [], 'length': 0})
    (folder / 'cases.json').write_text(json.dumps({'source': 'code only: the instruction words of the exhaustive check', 'revision': '-', 'scope': '-',
                                                    'excluded': '-', 'tests': tests}), encoding='utf-8', newline='\n')
    project, checks, _, _, _ = replay.build('md-moira-bcd', folder=folder, harness=ROOT / 'native' / 'md_bcd_checks.c')
    results = {}
    for kind, word in EXHAUSTIVE.items():
        table = work / f'bcd-{kind}.bin'
        run([maker, '--bcd', kind, table], cwd=work)
        output = run([checks, kind, table, hex(EXHAUSTIVE_PC[kind]), hex(word)], cwd=work)
        results[kind] = {json.loads(line)['path']: json.loads(line) for line in output.splitlines() if line.startswith('{')}
    return results


def groups_decimal_vectors() -> list[dict]:
    """The 114 vectors of ABCD, SBCD and NBCD of `tests/fixtures/m68k-groups` (SingleStepTests, made with MAME; 22 of them are the ones the pinned
    68000 model does not reproduce: `tests/fixtures/m68k-groups/deviations.json`)."""
    tests = json.loads((ROOT / 'tests/fixtures/m68k-groups/cases.json').read_text(encoding='utf-8'))['tests']
    return [test for test in tests if test['group'] in DECIMAL]


def bus_cycle(item: list) -> list:
    """A transaction without its function code and its size, which the harnesses do not compare; an idle period as it is."""
    return item if item[0] == 'n' else [item[0], item[1], item[3], item[5], item[6], item[7]]


def moira_against_vector(test: dict, run: dict) -> list[str]:
    """What differs between Moira's run of a vector's initial state and the vector: the registers, SR under the vector's mask, the queue, the
    memory the vector lists, the total clocks and the bus (kind, clock, address and data of every cycle)."""
    final, mask, found = test['final'], test.get('sr_mask', 0xffff), []
    if any(run['regs'][name] != final[name] for name in REGS[:17]) or (run['regs']['sr'] ^ final['sr']) & mask:
        found.append('registers')
    if run['regs']['pc'] + 4 != final['pc'] or [run['regs']['ird'], run['regs']['irc']] != final['prefetch']:
        found.append('pc or queue')
    after = {address: value for address, _, value in run['bytes']}
    before = dict(test['initial']['ram'])
    if any(after.get(address, before.get(address)) != value for address, value in final['ram']):
        found.append('memory')
    if run['clock'] != test['length']:
        found.append('clocks')
    ours = transactions(run['accesses'], run['clock'], bool(test['initial']['sr'] & 0x2000), range(0))
    if [bus_cycle(item) for item in ours] != [bus_cycle(item) for item in test['transactions']]:
        found.append('bus')
    return found


def failing_vectors(text: str, path: str = 'native') -> set[tuple[str, str]]:
    """(group, name) of every vector the harness reported on `path`, for a fixture whose vectors have their own names."""
    pattern = re.compile(r'^FAIL (\S+): (.*?) (native|reference) (.+?) expected=')
    return {(match[1], match[2]) for match in map(pattern.match, text.splitlines()) if match and match[3] == path}


def decimal_fixture(maker: Path, work: Path) -> dict:
    """Moira, run by the maker, on the 114 decimal vectors of the groups fixture, and the pinned native steps on the same 114: which differ from
    the vector, and for the vectors the native steps do not reproduce, whether Moira does."""
    tests = groups_decimal_vectors()
    states = [({}, dict(zip(REGS[:18], (test['initial'][name] for name in REGS[:18])), pc=test['initial']['pc'] - 4, words=list(test['initial']['prefetch']),
                         seed=1, over=dict(test['initial']['ram']))) for test in tests]
    results = run_maker(maker, work, states)
    folder = work / 'groups-decimal'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'cases.json').write_text(json.dumps({'source': 'tests/fixtures/m68k-groups', 'revision': 'the decimal groups', 'scope': 'ABCD, SBCD, NBCD',
                                                    'excluded': '-', 'tests': tests}), encoding='utf-8', newline='\n')
    stderr, _ = replay_forms(work, folder, 'md-moira-groups-decimal', with_bus=False)
    failing = failing_vectors(stderr)
    deviating = [number for number, test in enumerate(tests) if (test['group'], test['name']) in failing]
    moira = [moira_against_vector(test, run) for test, run in zip(tests, results)]
    others = [number for number in range(len(tests)) if number not in set(deviating)]
    return {'vectors': len(tests), 'moira_equal_vector': sum(not found for found in moira),
            'moira_differences': dict(collections.Counter(item for found in moira for item in found)),
            'native_deviating': len(deviating), 'native_deviating_by_group': dict(collections.Counter(tests[n]['group'] for n in deviating)),
            'moira_equal_on_deviating': sum(not moira[n] for n in deviating), 'moira_equal_on_the_others': sum(not moira[n] for n in others)}


def split_combos(row: dict) -> dict:
    """The counts of an exhaustive row by operands (decimal or undefined) and by what differs: nothing, only V, or something outside V (the
    result byte, X, C, N or Z, with or without V)."""
    found = collections.Counter()
    for key, count in row['combos'].items():
        operands, fields = key.split(':')
        fields = int(fields)
        found[operands, 'equal' if not fields else 'V only' if fields == FIELD_BITS['V'] else 'outside V'] += count
    return {f'{operands} {what}': found[operands, what] for operands in ('valid', 'undefined') for what in ('equal', 'V only', 'outside V')}


def exhaustive_problems(results: dict) -> list[str]:
    """What must hold of an exhaustive run: on decimal operands nothing but V may differ, and no instruction touches the other bits of the
    registers, the queue or the PC, or leaves the native path."""
    found = []
    for kind, paths in results.items():
        for path, row in paths.items():
            if split_combos(row)['valid outside V']:
                found.append(f'{kind} {path}: {split_combos(row)["valid outside V"]} states with decimal operands differ outside V')
            for key in ('upper_bits_changed', 'queue_or_pc_wrong', 'status_wrong', 'wrong_path'):
                if row[key]:
                    found.append(f'{kind} {path}: {key} {row[key]}')
        if paths['native']['combos'] != paths['reference']['combos']:
            found.append(f'{kind}: the native step and the reference path differ from Moira in different states')
    return found


def summarise_exhaustive(results: dict) -> list[str]:
    """One line per instruction and path: the states, then for decimal operands and for the others how many equal Moira, differ only in V
    (documented undefined for these instructions) or differ outside V."""
    lines = []
    for kind, paths in results.items():
        for path, row in paths.items():
            c = split_combos(row)
            lines.append(f"{kind.upper()} {path:<9}{row['states']:>7} states | decimal operands {row['valid_states']:>6}: equal {c['valid equal']}, V only {c['valid V only']}, "
                         f"outside V {c['valid outside V']} | undefined {row['states'] - row['valid_states']:>6}: equal {c['undefined equal']}, "
                         f"V only {c['undefined V only']}, outside V {c['undefined outside V']} | upper bits changed {row['upper_bits_changed']}, "
                         f"queue/pc wrong {row['queue_or_pc_wrong']}, wrong path {row['wrong_path']}")
    return lines


def print_forms(rows: dict) -> list[str]:
    existing = existing_vectors()
    lines = [f"{'form':<22}{'role':<13}{'fixtures':>9}{'vectors':>8}{'whole':>7}  differences by category  |  families"]
    for group, row in rows.items():
        categories = ' '.join(f'{name}={n}' for name, n in sorted(row['categories'].items())) or '-'
        families = ', '.join(f'{name}={n}' for name, n in sorted(row['families'].items())) or '-'
        unexplained = ' UNEXPLAINED ' + ' '.join(f'{name}={n}' for name, n in sorted(row['unexplained'].items())) if row['unexplained'] else ''
        shifts = ' shifts ' + ' '.join(f'{name}x{n}' for name, n in sorted(row['shifts'].items())) if row['shifts'] else ''
        lines.append(f"{group:<22}{row['role']:<13}{existing[group]:>9}{row['vectors']:>8}{row['whole']:>7}  {categories}  |  {families}{shifts}{unexplained}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--count', type=int, default=COUNT, help='vectors of each form of the main groups (the control forms keep their own)')
    parser.add_argument('--skip-exhaustive', action='store_true')
    parser.add_argument('--exhaustive-only', action='store_true')
    parser.add_argument('--write', type=Path, help='write the results as JSON to this file')
    options = parser.parse_args()
    work = work_dir()
    maker = build_maker(work)
    result: dict = {'seed': options.seed, 'count': options.count}
    status = 0
    if not options.exhaustive_only:
        states = make_states(options.seed, options.count)
        results = run_maker(maker, work, states)
        folder = work / 'vectors'
        tests = write_fixture(folder, states, results, options.seed, options.count)
        meta = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
        text, summary = replay_forms(work, folder)
        report = parse_report(text)
        rows = evaluate(meta, tests, report)
        result.update(vectors=len(tests), forms=len(rows), harness=summary,
                      same_failures_on_both_paths=sorted(report['native']) == sorted(report['reference']),
                      rows={group: {**row, 'categories': dict(row['categories']), 'families': dict(row['families']),
                                    'unexplained': dict(row['unexplained']), 'clock_deltas': dict(row['clock_deltas']),
                                    'shifts': dict(row['shifts'])} for group, row in rows.items()})
        print(f"{len(tests)} vectors of {len(rows)} forms (seed {options.seed}); whole agreement "
              f"{sum(row['whole'] for row in rows.values())}/{len(tests)}; native and reference path fail on the same vectors: "
              f"{result['same_failures_on_both_paths']}")
        print('\n'.join(print_forms(rows)))
        status |= int(any(row['unexplained'] for row in rows.values()))
    if not options.skip_exhaustive:
        exhaustive_results = exhaustive(maker, work)
        result['exhaustive'] = exhaustive_results
        print('\n'.join(summarise_exhaustive(exhaustive_results)))
        problems = exhaustive_problems(exhaustive_results)
        print('\n'.join('PROBLEM ' + line for line in problems))
        status |= int(bool(problems))
        result['decimal_fixture'] = decimal_fixture(maker, work)
        print('decimal vectors of tests/fixtures/m68k-groups:', json.dumps(result['decimal_fixture']))
    (work / 'results.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    if options.write:
        options.write.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    return status


if __name__ == '__main__':
    sys.exit(main())
