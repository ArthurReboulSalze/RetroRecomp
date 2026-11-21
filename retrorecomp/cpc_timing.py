"""The Amstrad CPC's Z80 instruction costs, in microseconds (« NOPs »: 1 us = 4 T-states at 4 MHz), as data for the shared
banked Z80 chain's per-instruction cost table (Z80Machine.costs, once it is on main). MIT, Retro-Recomp.

The rule. The CPC's Gate Array shares the RAM between the Z80 and the screen and holds the Z80's WAIT line so that every bus
access, an opcode fetch, a memory read or write or an I/O cycle, falls on one phase of its 1 MHz clock. In the T-state traces of
the Z80, the cycle on which the access is strobed moves to T = 1 modulo 4 (`cpc_nops`); an instruction then lasts a whole
number of microseconds. The documented consequences hold: NOP 1, LD r,(HL) 2, PUSH 4, POP 3, OUT (n),A 3, OUT (C),r 4, CALL 5,
EX (SP),HL 6, LD (IX+d),n 6, LDIR 6 (5 at its end), DJNZ 4 (3 when it falls through).

The table. `tools/cpc_timing_table.py` derives it from the SingleStepTests/z80 bus traces (MIT, the vectors G10 already pins):
COSTS[table][opcode] is the cost when a conditional branch is not taken (or a block instruction ends), EXTRA[table][opcode]
what a taken branch (JR cc, DJNZ, CALL cc, RET cc) or a repeating LDIR / CPIR / INIR / OTIR family adds. Tables: 'base',
'cb', 'ed', 'dd', 'fd', 'ddcb', 'fdcb' (the opcode after DD CB d / FD CB d); a prefix byte is 0 in its table (the
prefixed table holds the whole cost), a DD or FD before DD, ED or FD a lone prefix of 1 us. The rule was written from the CPC's documented
timing and checked on the values above; floooh/chips (zlib) and Clock Signal (MIT) were read as documentation, nothing copied.

Outside the vectors (derived with the same rule from the Z80 data sheet's cycle shapes, not checked against a CPC yet): HALT
repeats a 4-T opcode fetch, 1 us each; accepting an interrupt costs INTERRUPT[mode] (the acknowledge cycle with its two wait
states strobed on its fourth T-state, then the pushes, and the vector read in mode 2).
"""
from __future__ import annotations

STROBE_PHASE = 1        # the T-state, modulo 4, on which the Gate Array lets a bus access happen


def cpc_nops(trace) -> int:
    """The microseconds an instruction takes on a CPC, from its Z80 bus trace: one 'rwmi' flag string per T-state (r read,
    w write, m memory, i I/O), an access on each T-state flagged r or w. Every access is delayed to the CPC's phase; the end
    rounds up to the next microsecond (the next opcode fetch is strobed on the phase too)."""
    delay = 0
    for t, flags in enumerate(trace):
        if flags[0] == 'r' or flags[1] == 'w':
            delay += (STROBE_PHASE - (t + delay)) % 4
    return (len(trace) + delay + 3) // 4


def _interrupt(mode: int) -> int:
    acknowledge = ['----', '----', '----', 'r--i', '----', '----', '----']   # T1, T2, two waits, T3, T4 (+1)
    write = ['----', '-wm-', '----']
    read = ['----', 'r-m-', '----']
    trace = acknowledge + write + write + (read + read if mode == 2 else [])
    return cpc_nops(trace)


# Derived by tools/cpc_timing_table.py from SingleStepTests/z80 ebe1875 (32 vectors a family); do not edit by hand.
COSTS = {
    'base': (
        '1322112113221121332211213322112123521121235211212342333123421121'
        '1111112111111121111111211111112111111121111111212222221211111121'
        '1111112111111121111111211111112111111121111111211111112111111121'
        '2333342423303524233334242133302423363424213130242331342422313024'
    ),
    'cb': (
        '2222224222222242222222422222224222222242222222422222224222222242'
        '2222223222222232222222322222223222222232222222322222223222222232'
        '2222224222222242222222422222224222222242222222422222224222222242'
        '2222224222222242222222422222224222222242222222422222224222222242'
    ),
    'ed': (
        '2222222222222222222222222222222222222222222222222222222222222222'
        '4446242344462423444624234446242344462425444624254446242244462422'
        '2222222222222222222222222222222254552222545522225455222254552222'
        '2222222222222222222222222222222222222222222222222222222222222222'
    ),
    'dd': (
        '2433223224332232443322324433223234632232346322323453666234532232'
        '2222225222222252222222522222225222222252222222525555552522222252'
        '2222225222222252222222522222225222222252222222522222225222222252'
        '3444453534404635344445353244413534474535324241353442453533424135'
    ),
    'fd': (
        '2433223224332232443322324433223234632232346322323453666234532232'
        '2222225222222252222222522222225222222252222222525555552522222252'
        '2222225222222252222222522222225222222252222222522222225222222252'
        '3444453534404635344445353244413534474535324241353442453533424135'
    ),
    'ddcb': (
        '7777777777777777777777777777777777777777777777777777777777777777'
        '6666666666666666666666666666666666666666666666666666666666666666'
        '7777777777777777777777777777777777777777777777777777777777777777'
        '7777777777777777777777777777777777777777777777777777777777777777'
    ),
    'fdcb': (
        '7777777777777777777777777777777777777777777777777777777777777777'
        '6666666666666666666666666666666666666666666666666666666666666666'
        '7777777777777777777777777777777777777777777777777777777777777777'
        '7777777777777777777777777777777777777777777777777777777777777777'
    ),
}
EXTRA = {
    'base': {0x10: 1, 0x20: 1, 0x28: 1, 0x30: 1, 0x38: 1, 0xC0: 2, 0xC4: 2, 0xC8: 2, 0xCC: 2, 0xD0: 2, 0xD4: 2, 0xD8: 2, 0xDC: 2, 0xE0: 2, 0xE4: 2, 0xE8: 2, 0xEC: 2, 0xF0: 2, 0xF4: 2, 0xF8: 2, 0xFC: 2},
    'cb': {},
    'ed': {0xB0: 1, 0xB1: 2, 0xB2: 1, 0xB3: 1, 0xB8: 1, 0xB9: 2, 0xBA: 1, 0xBB: 1},
    'dd': {0x10: 1, 0x20: 1, 0x28: 1, 0x30: 1, 0x38: 1, 0xC0: 2, 0xC4: 2, 0xC8: 2, 0xCC: 2, 0xD0: 2, 0xD4: 2, 0xD8: 2, 0xDC: 2, 0xE0: 2, 0xE4: 2, 0xE8: 2, 0xEC: 2, 0xF0: 2, 0xF4: 2, 0xF8: 2, 0xFC: 2},
    'fd': {0x10: 1, 0x20: 1, 0x28: 1, 0x30: 1, 0x38: 1, 0xC0: 2, 0xC4: 2, 0xC8: 2, 0xCC: 2, 0xD0: 2, 0xD4: 2, 0xD8: 2, 0xDC: 2, 0xE0: 2, 0xE4: 2, 0xE8: 2, 0xEC: 2, 0xF0: 2, 0xF4: 2, 0xF8: 2, 0xFC: 2},
    'ddcb': {},
    'fdcb': {},
}

HALT = 1
INTERRUPT = {mode: _interrupt(mode) for mode in (0, 1, 2)}


# The chain's encoding groups (retrorecomp/z80_chain.COST_GROUPS) for this module's tables.
GROUPS = {'base': '', 'cb': 'cb', 'dd': 'dd', 'fd': 'fd', 'ed': 'ed', 'ddcb': 'ddcb', 'fdcb': 'fdcb'}
# What Z80Costs cannot say yet: its `repeat` is one value for every block instruction, but on a CPC a repeating CPIR or CPDR
# adds 2 us and LDIR, INIR, OTIR and their decrementing forms add 1 (asked of the lead, 21 Nov 2026).
UNEXPRESSED = frozenset({('ed', 0xB1), ('ed', 0xB9)})


def z80_costs():
    """The CPC's costs as the shared chain takes them (z80_chain.Z80Costs, in T-states, before M1 wait states: the CPC's
    Z80Machine states m1_wait 0). Every opcode of the seven tables is given; a prefix byte (0 here) is left to its table. The
    taken extras are uniform on a CPC (JR cc and DJNZ 1 us, RET cc and CALL cc 2 us, with or without a DD or FD prefix); the
    block repeat is LDIR's 1 us, CPIR and CPDR excepted (UNEXPRESSED)."""
    from .z80_chain import Z80Costs
    base = tuple((GROUPS[table], opcode, 4 * int(row[opcode])) for table, row in COSTS.items() for opcode in range(256)
                 if int(row[opcode]))
    return Z80Costs(base=base, jr_taken=4 * EXTRA['base'][0x20], djnz_taken=4 * EXTRA['base'][0x10],
                    ret_taken=4 * EXTRA['base'][0xC0], call_taken=4 * EXTRA['base'][0xC4], repeat=4 * EXTRA['ed'][0xB0],
                    irq=4 * INTERRUPT[1], irq_im2=4 * INTERRUPT[2], halt=4 * HALT, fragment=4 * int(COSTS['dd'][0xDD]))


def cost(table: str, opcode: int, taken: bool = False) -> int:
    """Microseconds of one instruction: its table, its opcode, and whether its branch is taken or its block repeats."""
    value = int(COSTS[table][opcode])
    return value + (EXTRA[table].get(opcode, 0) if taken else 0)
