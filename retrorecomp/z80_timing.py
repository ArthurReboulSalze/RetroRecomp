"""The Z80's bus cycles, encoding by encoding (MIT): what each instruction puts on the address bus, cycle after cycle, and for how long.

A machine whose bus holds the CPU off by the address and the moment of each cycle (the ZX Spectrum's ULA contention) needs, for every
encoding, the ordered list of its bus cycles, not only its total (z80_chain.Z80Costs). This module is that list, written from the
Zilog Z80 user manual (UM0080, the M-cycle tables) with Clock Signal (MIT) as a written reference, and checked independently against
the SingleStepTests z80 vectors (MIT), which give the address on the bus at every T-state: tools/z80_timing_vectors.py.

A cycle is (kind, source, count):

- `m1`: an opcode fetch, 4 T: the address `source` for two T-states, then the refresh address (I, R before its increment) for two;
- `rd`, `wr`: a memory read or write, 3 T on `source`;
- `in`, `out`: an I/O read or write, 4 T on `source` (the port);
- `int`: `count` internal T-states, each leaving `source` on the bus (`ir`: the last refresh address).

Sources are read from the state BEFORE the instruction runs (contention moves time, never data): `pc+k`, `hl`, `bc`, `de`, `sp`,
`sp+1`, `sp-1`, `sp-2`, `ixd` (IX or IY plus the displacement at pc+2), `nn` and `nn+1` (the operand word at pc+1, or at pc+2
after a prefix), `an` (A in the high byte, the operand byte at pc+1 in the low: IN A,(n) and OUT (n),A), `bc-` (B less one: OUTI,
OUTD and their repeats put the port out after B is decremented), `ir`.

`cycles(group, opcode)` gives (base, extra): the cycles every execution has, and those a conditional branch adds when taken or a
block instruction adds when it goes round again (empty when there is none). Groups are z80_chain.COST_GROUPS: '' (unprefixed), 'cb',
'dd', 'fd', 'ed', 'ddcb', 'fdcb'. A DD or FD prefix before an opcode that does not use HL is the opcode's own cycles after one more
M1; the interrupt acceptances and HALT come with the evaluator, which states them (they are not in the vectors).
"""
from __future__ import annotations

from functools import lru_cache

Cycle = tuple[str, str, int]


def _m1(source: str) -> Cycle:
    return ('m1', source, 1)


def _rd(source: str) -> Cycle:
    return ('rd', source, 1)


def _wr(source: str) -> Cycle:
    return ('wr', source, 1)


def _int(source: str, count: int) -> Cycle:
    return ('int', source, count)


def _shift(source: str, by: int) -> str:
    """`pc+k` moved by `by` bytes (a prefix before the opcode); other sources unchanged."""
    if source == 'pc':
        return f'pc+{by}' if by else 'pc'
    if source.startswith('pc+'):
        return f'pc+{int(source[3:]) + by}'
    return source


def _unprefixed(opcode: int) -> tuple[list[Cycle], list[Cycle]]:
    x, y, z = opcode >> 6, (opcode >> 3) & 7, opcode & 7
    p, q = y >> 1, y & 1
    m = [_m1('pc')]
    if x == 0:
        if z == 0:
            if y <= 1:                                   # NOP, EX AF,AF'
                return m, []
            if y == 2:                                   # DJNZ e
                return m + [_int('ir', 1), _rd('pc+1')], [_int('pc+1', 5)]
            if y == 3:                                   # JR e
                return m + [_rd('pc+1'), _int('pc+1', 5)], []
            return m + [_rd('pc+1')], [_int('pc+1', 5)]  # JR cc,e
        if z == 1:
            if q == 0:                                   # LD rp,nn
                return m + [_rd('pc+1'), _rd('pc+2')], []
            return m + [_int('ir', 7)], []               # ADD HL,rp
        if z == 2:
            if q == 0:
                if p == 0:
                    return m + [_wr('bc')], []           # LD (BC),A
                if p == 1:
                    return m + [_wr('de')], []           # LD (DE),A
                if p == 2:                               # LD (nn),HL
                    return m + [_rd('pc+1'), _rd('pc+2'), _wr('nn'), _wr('nn+1')], []
                return m + [_rd('pc+1'), _rd('pc+2'), _wr('nn')], []      # LD (nn),A
            if p == 0:
                return m + [_rd('bc')], []               # LD A,(BC)
            if p == 1:
                return m + [_rd('de')], []               # LD A,(DE)
            if p == 2:                                   # LD HL,(nn)
                return m + [_rd('pc+1'), _rd('pc+2'), _rd('nn'), _rd('nn+1')], []
            return m + [_rd('pc+1'), _rd('pc+2'), _rd('nn')], []          # LD A,(nn)
        if z == 3:                                       # INC rp, DEC rp
            return m + [_int('ir', 2)], []
        if z in (4, 5):                                  # INC r, DEC r
            return (m + [_rd('hl'), _int('hl', 1), _wr('hl')], []) if y == 6 else (m, [])
        if z == 6:                                       # LD r,n
            return (m + [_rd('pc+1'), _wr('hl')], []) if y == 6 else (m + [_rd('pc+1')], [])
        return m, []                                     # RLCA .. CCF
    if x == 1:
        if y == 6 and z == 6:                            # HALT
            return m, []
        if z == 6:
            return m + [_rd('hl')], []                   # LD r,(HL)
        if y == 6:
            return m + [_wr('hl')], []                   # LD (HL),r
        return m, []
    if x == 2:
        return (m + [_rd('hl')], []) if z == 6 else (m, [])                # ALU A,r
    if z == 0:                                           # RET cc
        return m + [_int('ir', 1)], [_rd('sp'), _rd('sp+1')]
    if z == 1:
        if q == 0 or p == 0:                             # POP rp2, RET
            return m + [_rd('sp'), _rd('sp+1')], []
        if p == 3:                                       # LD SP,HL
            return m + [_int('ir', 2)], []
        return m, []                                     # EXX, JP (HL)
    if z == 2:                                           # JP cc,nn
        return m + [_rd('pc+1'), _rd('pc+2')], []
    if z == 3:
        if y == 0:                                       # JP nn
            return m + [_rd('pc+1'), _rd('pc+2')], []
        if y == 2:                                       # OUT (n),A
            return m + [_rd('pc+1'), ('out', 'an', 1)], []
        if y == 3:                                       # IN A,(n)
            return m + [_rd('pc+1'), ('in', 'an', 1)], []
        if y == 4:                                       # EX (SP),HL
            return m + [_rd('sp'), _rd('sp+1'), _int('sp+1', 1), _wr('sp+1'), _wr('sp'), _int('sp', 2)], []
        return m, []                                     # CB (its own group), EX DE,HL, DI, EI
    if z == 4:                                           # CALL cc,nn
        return m + [_rd('pc+1'), _rd('pc+2')], [_int('pc+2', 1), _wr('sp-1'), _wr('sp-2')]
    if z == 5:
        if q == 0:                                       # PUSH rp2
            return m + [_int('ir', 1), _wr('sp-1'), _wr('sp-2')], []
        if p == 0:                                       # CALL nn
            return m + [_rd('pc+1'), _rd('pc+2'), _int('pc+2', 1), _wr('sp-1'), _wr('sp-2')], []
        return m, []                                     # DD, ED, FD prefixes (their own groups)
    if z == 6:                                           # ALU A,n
        return m + [_rd('pc+1')], []
    return m + [_int('ir', 1), _wr('sp-1'), _wr('sp-2')], []                # RST


# The unprefixed opcodes that address memory through (HL): under DD or FD they take (IX+d) or (IY+d).
_HL_MEMORY = frozenset([0x34, 0x35, 0x36] + [0x46 + 8 * r for r in range(8) if r != 6] + list(range(0x70, 0x76)) + [0x77]
                       + [0x86 + 8 * r for r in range(8)])


def _indexed(opcode: int) -> tuple[list[Cycle], list[Cycle]]:
    """DD or FD then `opcode`: (IX+d) for the (HL) forms, else the opcode's own cycles one M1 later."""
    m = [_m1('pc'), _m1('pc+1')]
    if opcode in (0x34, 0x35):                           # INC (IX+d), DEC (IX+d)
        return m + [_rd('pc+2'), _int('pc+2', 5), _rd('ixd'), _int('ixd', 1), _wr('ixd')], []
    if opcode == 0x36:                                   # LD (IX+d),n
        return m + [_rd('pc+2'), _rd('pc+3'), _int('pc+3', 2), _wr('ixd')], []
    if opcode in _HL_MEMORY:                             # LD r,(IX+d), LD (IX+d),r, ALU A,(IX+d)
        access = _wr('ixd') if 0x70 <= opcode <= 0x77 else _rd('ixd')
        return m + [_rd('pc+2'), _int('pc+2', 5), access], []
    base, extra = _unprefixed(opcode)
    return [_m1('pc')] + [(kind, _shift(source, 1), count) for kind, source, count in base], \
        [(kind, _shift(source, 1), count) for kind, source, count in extra]


def _cb(opcode: int) -> tuple[list[Cycle], list[Cycle]]:
    m = [_m1('pc'), _m1('pc+1')]
    if opcode & 7 != 6:
        return m, []
    if opcode >> 6 == 1:                                 # BIT b,(HL)
        return m + [_rd('hl'), _int('hl', 1)], []
    return m + [_rd('hl'), _int('hl', 1), _wr('hl')], []


def _index_cb(opcode: int) -> tuple[list[Cycle], list[Cycle]]:
    """DD CB d op: the displacement and the opcode are plain reads (no M1, no refresh)."""
    cycles = [_m1('pc'), _m1('pc+1'), _rd('pc+2'), _rd('pc+3'), _int('pc+3', 2), _rd('ixd'), _int('ixd', 1)]
    return (cycles if opcode >> 6 == 1 else cycles + [_wr('ixd')]), []


def _ed(opcode: int) -> tuple[list[Cycle], list[Cycle]]:
    x, y, z = opcode >> 6, (opcode >> 3) & 7, opcode & 7
    q = y & 1
    m = [_m1('pc'), _m1('pc+1')]
    if x == 1:
        if z == 0:
            return m + [('in', 'bc', 1)], []             # IN r,(C)
        if z == 1:
            return m + [('out', 'bc', 1)], []            # OUT (C),r
        if z == 2:
            return m + [_int('ir', 7)], []               # SBC HL,rp / ADC HL,rp
        if z == 3:                                       # LD (nn),rp / LD rp,(nn)
            access = (_rd, _rd) if q else (_wr, _wr)
            return m + [_rd('pc+2'), _rd('pc+3'), access[0]('nn'), access[1]('nn+1')], []
        if z == 5:                                       # RETN, RETI
            return m + [_rd('sp'), _rd('sp+1')], []
        if z == 7:
            if y <= 3:                                   # LD I,A  LD R,A  LD A,I  LD A,R
                return m + [_int('ir', 1)], []
            if y <= 5:                                   # RRD, RLD
                return m + [_rd('hl'), _int('hl', 4), _wr('hl')], []
        return m, []                                     # NEG, IM, the undocumented NOPs
    if x == 2 and z <= 3 and y >= 4:
        repeat = y >= 6
        if z == 0:                                       # LDI LDD LDIR LDDR
            return m + [_rd('hl'), _wr('de'), _int('de', 2)], ([_int('de', 5)] if repeat else [])
        if z == 1:                                       # CPI CPD CPIR CPDR
            return m + [_rd('hl'), _int('hl', 5)], ([_int('hl', 5)] if repeat else [])
        if z == 2:                                       # INI IND INIR INDR
            return m + [_int('ir', 1), ('in', 'bc', 1), _wr('hl')], ([_int('hl', 5)] if repeat else [])
        return m + [_int('ir', 1), _rd('hl'), ('out', 'bc-', 1)], ([_int('bc-', 5)] if repeat else [])    # OUTI .. OTDR
    return m, []                                         # ED NOPs


@lru_cache(maxsize=None)
def cycles(group: str, opcode: int) -> tuple[tuple[Cycle, ...], tuple[Cycle, ...]]:
    """(base, extra) of the encoding `opcode` of `group` (z80_chain.COST_GROUPS)."""
    if not 0 <= opcode <= 255:
        raise ValueError(f'not an opcode: {opcode!r}')
    if group == '':
        base, extra = _unprefixed(opcode)
    elif group == 'cb':
        base, extra = _cb(opcode)
    elif group in ('dd', 'fd'):
        base, extra = _indexed(opcode)
    elif group == 'ed':
        base, extra = _ed(opcode)
    elif group in ('ddcb', 'fdcb'):
        base, extra = _index_cb(opcode)
    else:
        raise ValueError(f'not a Z80 group: {group!r}')
    return tuple(base), tuple(extra)


def length(cycle_list) -> int:
    """The T-states of a list of cycles."""
    return sum({'m1': 4, 'rd': 3, 'wr': 3, 'in': 4, 'out': 4}.get(kind, count) for kind, _, count in cycle_list)
