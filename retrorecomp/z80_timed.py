"""The delay a machine's bus adds to each Z80 instruction, from its bus cycles (MIT): the evaluator of memory contention on the chain.

retrorecomp/z80_timing.py lists, for every encoding, the cycles an instruction puts on the bus (checked against the SingleStepTests
vectors). A machine whose bus holds the CPU off by address and moment (the ZX Spectrum's ULA) gives two rules: the delay of a
memory or internal cycle that starts at T-state `t` on `address`, and the whole delay of an I/O cycle on `port` starting at `t`.
This module turns the table into:

- `render_c()`: one C text, the table as data plus its walker, which the emitter's bodies and the reference interpreter both
  include (z80_chain.Z80Machine.contention). One text from one table: the native code and the reference agree by construction,
  so the independent evidence stays the vectors' check of the table;
- `delay()`: the same walk in Python, the model the self-tests compare both programs with.

The walk, cycle after cycle, from the instruction's first T-state `t`: an M1 asks the memory rule on its address, then takes 4 T (its
refresh half is never contended: the refresh address is not the CPU's access); a read or a write asks the memory rule, then takes
3 T; an I/O cycle asks the I/O rule (the port's whole pattern), then takes 4 T; an internal cycle of `count` T asks the memory
rule before each of its T-states; an acknowledge (`ack`) takes its T-states with no rule. Each rule's delay moves every later
cycle. Sources are the registers and operands BEFORE the instruction runs (z80_timing); the extra cycles of a taken branch or a
repeat always come last and are walked from the moment the base cycles end.

Not instructions, so not in the vectors, and stated here from the Z80 user manual (UM0080), each matching the totals of
z80_chain.Z80Costs:

- `im1`: the /INT acknowledge in modes 0 and 1 (7 T, PC on the bus, not passed to the rule), then the pushes of PC
  (13 T in all; mode 0 is charged as mode 1, the RST 38h the Spectrum's idle bus reads);
- `im2`: the same acknowledge and pushes, then the two reads of the vector at I:bus (19 T); `vec` is that address;
- `nmi`: the /NMI acceptance (5 T, not passed to the rule), then the pushes (11 T);
- `halt`: one cycle of a HALT, an M1 on PC;
- `fragment`: a redundant DD or FD prefix, an M1 on PC.

Non-pure addresses (each with a self-test in tests/test_z80_timed.py): the IM2 vector (`vec`: I and the byte on the bus); EX
(SP),HL (reads at SP and SP+1, an internal T on SP+1, writes at SP+1 then SP, two internal T on SP); the block repeats (five
internal T on DE, HL or B-1:C as before the instruction); IN and OUT (the port is the I/O rule's; the value read, the floating bus,
is the machine's, not this module's).
"""
from __future__ import annotations

from typing import Callable

from .z80_chain import COST_GROUPS
from .z80_timing import cycles, length

KINDS = ('m1', 'rd', 'wr', 'in', 'out', 'int', 'ack')
SOURCES = ('pc', 'pc+1', 'pc+2', 'pc+3', 'hl', 'bc', 'de', 'sp', 'sp+1', 'sp-1', 'sp-2', 'ixd', 'nn', 'nn+1', 'an', 'bc-',
           'ir', 'vec', 'vec+1')
SPECIALS = {
    'im1': (('ack', 'pc', 7), ('wr', 'sp-1', 1), ('wr', 'sp-2', 1)),
    'im2': (('ack', 'pc', 7), ('wr', 'sp-1', 1), ('wr', 'sp-2', 1), ('rd', 'vec', 1), ('rd', 'vec+1', 1)),
    'nmi': (('ack', 'pc', 5), ('wr', 'sp-1', 1), ('wr', 'sp-2', 1)),
    'halt': (('m1', 'pc', 1),),
    'fragment': (('m1', 'pc', 1),),
}
_LENGTH = {'m1': 4, 'rd': 3, 'wr': 3, 'in': 4, 'out': 4}

Rule = Callable[[int, int], int]


def cycle_length(cycle_list) -> int:
    """The plain T-states of a list of cycles, acknowledges included."""
    return sum(_LENGTH.get(kind, count) for kind, _, count in cycle_list)


def address(group: str, source: str, state: dict, peek: Callable[[int], int], refresh: int) -> int:
    """The address `source` names for an instruction of `group` starting from `state` (registers by name: pc sp a b c d e h l i r
    ix iy, and `vec` for an acceptance in mode 2); `peek` reads memory without side effects; `refresh` is the last M1's."""
    pc = state['pc']
    if source == 'ir':
        return refresh
    if source == 'pc':
        return pc & 0xFFFF
    if source.startswith('pc+'):
        return (pc + int(source[3:])) & 0xFFFF
    if source in ('vec', 'vec+1'):
        return (state['vec'] + (source == 'vec+1')) & 0xFFFF
    sp = state['sp']
    if source.startswith('sp'):
        return (sp + {'sp': 0, 'sp+1': 1, 'sp-1': -1, 'sp-2': -2}[source]) & 0xFFFF
    pair = {'hl': ('h', 'l'), 'bc': ('b', 'c'), 'de': ('d', 'e')}
    if source in pair:
        high, low = pair[source]
        return state[high] << 8 | state[low]
    if source == 'bc-':
        return ((state['b'] - 1) & 0xFF) << 8 | state['c']
    operand = pc + (2 if group in ('dd', 'fd', 'ed', 'ddcb', 'fdcb') else 1)
    if source in ('nn', 'nn+1'):
        word = peek(operand & 0xFFFF) | peek((operand + 1) & 0xFFFF) << 8
        return (word + (source == 'nn+1')) & 0xFFFF
    if source == 'an':
        return state['a'] << 8 | peek(operand & 0xFFFF)
    if source == 'ixd':
        index = state['ix'] if group in ('dd', 'ddcb') else state['iy']
        displacement = peek((pc + 2) & 0xFFFF)
        return (index + (displacement - 256 if displacement > 127 else displacement)) & 0xFFFF
    raise ValueError(f'not a bus-cycle source: {source!r}')


def walk(group: str, cycle_list, state: dict, peek, t: int, memory: Rule, io: Rule) -> int:
    """The delay the rules add to `cycle_list` started at T-state `t` (the walk of the module's docstring)."""
    delay, fetches, refresh = 0, 0, 0
    for kind, source, count in cycle_list:
        where = address(group, source, state, peek, refresh)
        if kind == 'm1':
            wait = memory(t, where)
            r = state['r']
            refresh = state['i'] << 8 | (r & 0x80) | ((r + fetches) & 0x7F)
            fetches += 1
            delay, t = delay + wait, t + wait + 4
        elif kind in ('rd', 'wr'):
            wait = memory(t, where)
            delay, t = delay + wait, t + wait + 3
        elif kind in ('in', 'out'):
            wait = io(t, where)
            delay, t = delay + wait, t + wait + 4
        elif kind == 'int':
            for _ in range(count):
                wait = memory(t, where)
                delay, t = delay + wait, t + wait + 1
        else:
            t += count
    return delay


def delay(group: str, opcode: int, state: dict, peek, t: int, memory: Rule, io: Rule, taken: bool = False) -> int:
    """The whole delay of one instruction started at `t`: its base cycles, then, when `taken`, its extra cycles from where the
    base ends."""
    base, extra = cycles(group, opcode)
    wait = walk(group, base, state, peek, t, memory, io)
    if taken and extra:
        wait += walk(group, extra, state, peek, t + length(base) + wait, memory, io)
    return wait


def _pairs(cycle_list) -> list[int]:
    out = []
    for kind, source, count in cycle_list:
        if source not in SOURCES or kind not in KINDS or not 1 <= count <= 255:
            raise ValueError(f'a cycle the C table cannot hold: {(kind, source, count)!r}')
        out += [KINDS.index(kind) << 5 | SOURCES.index(source), count]
    return out


def render_c() -> str:
    """The C text of the evaluator (native code and reference interpreter alike). The includer defines RR_TIMED_PEEK(address),
    RR_TIMED_MEMORY(t, address) and RR_TIMED_IO(t, port) before including it; `t` is a uint64_t T-state."""
    data, index, counts = [], [], []
    for group in COST_GROUPS:
        row_index, row_counts = [], []
        for opcode in range(256):
            base, extra = cycles(group, opcode)
            if len(base) > 15 or len(extra) > 15:
                raise ValueError('a cycle list longer than the C table holds')
            row_index.append(len(data) // 2)
            row_counts.append(len(base) << 4 | len(extra))
            data += _pairs(base) + _pairs(extra)
        index.append(row_index)
        counts.append(row_counts)
    special_index = []
    for name, cycle_list in SPECIALS.items():
        special_index.append((name, len(data) // 2, len(cycle_list)))
        data += _pairs(cycle_list)
    if len(data) // 2 > 0xFFFF:
        raise ValueError('the C table outgrew its 16-bit index')

    def rows(values, width=24):
        return '\n'.join('    ' + ', '.join(str(v) for v in values[i:i + width]) + ',' for i in range(0, len(values), width))

    lines = ['/* The Z80\'s bus cycles and their walker: the delay a machine\'s contention rule adds to each instruction.',
             ' * Rendered by retrorecomp/z80_timed.py from retrorecomp/z80_timing.py (MIT); never edited by hand. The includer defines',
             ' * RR_TIMED_PEEK(address) (memory, no side effect), RR_TIMED_MEMORY(t, address) and RR_TIMED_IO(t, port) (the rules). */',
             '#include <stdint.h>',
             'typedef struct { uint16_t pc, sp, bc, de, hl, ix, iy, vec; uint8_t a, i, r; } RrTimedStart;',
             ''.join(f'enum {{ RR_TIMED_{name.upper()} = {position} }};\n' for position, (name, _, _) in enumerate(special_index)).rstrip(),
             f'static const uint8_t rr_timed_cycles[{len(data)}] = {{', rows(data, 32), '};',
             f'static const uint16_t rr_timed_index[{len(COST_GROUPS)}][256] = {{']
    lines += ['  {\n' + rows(row, 16) + '\n  },' for row in index]
    lines += ['};', f'static const uint8_t rr_timed_counts[{len(COST_GROUPS)}][256] = {{']
    lines += ['  {\n' + rows(row, 16) + '\n  },' for row in counts]
    lines += ['};', f'static const uint16_t rr_timed_special[{len(special_index)}][2] = {{',
              '    ' + ', '.join(f'{{{offset}, {count}}}' for _, offset, count in special_index), '};']
    lines.append(_WALKER)
    return '\n'.join(lines) + '\n'


_WALKER = r'''
/* The address of source `s` for an instruction of group `g` (0 '', 1 cb, 2 dd, 3 fd, 4 ed, 5 ddcb, 6 fdcb). */
static uint16_t rr_timed_address(int g, unsigned s, const RrTimedStart *st, uint16_t refresh)
{
    const uint16_t operand = (uint16_t)(st->pc + (g >= 2 ? 2 : 1));
    switch (s) {
    case 0: case 1: case 2: case 3: return (uint16_t)(st->pc + s);
    case 4: return st->hl;
    case 5: return st->bc;
    case 6: return st->de;
    case 7: return st->sp;
    case 8: return (uint16_t)(st->sp + 1);
    case 9: return (uint16_t)(st->sp - 1);
    case 10: return (uint16_t)(st->sp - 2);
    case 11: {
        const uint8_t d = RR_TIMED_PEEK((uint16_t)(st->pc + 2));
        return (uint16_t)((g == 2 || g == 5 ? st->ix : st->iy) + (int8_t)d);
    }
    case 12: case 13:
        return (uint16_t)((RR_TIMED_PEEK(operand) | RR_TIMED_PEEK((uint16_t)(operand + 1)) << 8) + (s == 13));
    case 14: return (uint16_t)(st->a << 8 | RR_TIMED_PEEK(operand));
    case 15: return (uint16_t)((uint8_t)((st->bc >> 8) - 1) << 8 | (st->bc & 0xFF));
    case 16: return refresh;
    case 17: return st->vec;
    default: return (uint16_t)(st->vec + 1);
    }
}

/* The delay the rules add to `n` cycles from `c`, started at T-state `t` (retrorecomp/z80_timed.walk). */
static uint32_t rr_timed_walk(int g, const uint8_t *c, unsigned n, const RrTimedStart *st, uint64_t t)
{
    uint32_t delay = 0;
    unsigned fetches = 0;
    uint16_t refresh = 0;
    for (unsigned k = 0; k < n; ++k, c += 2) {
        const unsigned kind = c[0] >> 5, count = c[1];
        const uint16_t at = rr_timed_address(g, c[0] & 31, st, refresh);
        unsigned wait;
        switch (kind) {
        case 0:
            wait = RR_TIMED_MEMORY(t, at);
            refresh = (uint16_t)(st->i << 8 | (st->r & 0x80) | ((st->r + fetches) & 0x7F));
            ++fetches;
            delay += wait; t += wait + 4;
            break;
        case 1: case 2:
            wait = RR_TIMED_MEMORY(t, at);
            delay += wait; t += wait + 3;
            break;
        case 3: case 4:
            wait = RR_TIMED_IO(t, at);
            delay += wait; t += wait + 4;
            break;
        case 5:
            for (unsigned i = 0; i < count; ++i) {
                wait = RR_TIMED_MEMORY(t, at);
                delay += wait; t += wait + 1;
            }
            break;
        default:
            t += count;
            break;
        }
    }
    return delay;
}

/* The delay of the base cycles of encoding (g, op) started at `t`. */
static uint32_t rr_timed_base(int g, unsigned op, const RrTimedStart *st, uint64_t t)
{
    return rr_timed_walk(g, rr_timed_cycles + 2u * rr_timed_index[g][op], rr_timed_counts[g][op] >> 4, st, t);
}

/* The delay of its extra cycles (a taken branch, a repeat), walked from `t`, the moment its base cycles ended. */
static uint32_t rr_timed_extra(int g, unsigned op, const RrTimedStart *st, uint64_t t)
{
    return rr_timed_walk(g, rr_timed_cycles + 2u * (rr_timed_index[g][op] + (rr_timed_counts[g][op] >> 4)),
                         rr_timed_counts[g][op] & 15, st, t);
}

/* The delay of an acceptance or a HALT cycle (RR_TIMED_IM1 ...) started at `t`. */
static uint32_t rr_timed_special_delay(int which, const RrTimedStart *st, uint64_t t)
{
    return rr_timed_walk(0, rr_timed_cycles + 2u * rr_timed_special[which][0], rr_timed_special[which][1], st, t);
}
'''
