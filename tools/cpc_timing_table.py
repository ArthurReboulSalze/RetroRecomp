"""The Amstrad CPC's Z80 instruction costs in microseconds (« NOPs »), derived from the SingleStepTests bus traces.

    python -B tools/cpc_timing_table.py           # print the table as retrorecomp/cpc_timing.py holds it
    python -B tools/cpc_timing_table.py --check   # exit 1 when the module's table differs from the derivation
    (--vectors <file> reads another checkout's copy of the vectors)

The vectors (SingleStepTests/z80, MIT, pinned in tools/fetch_z80_vectors.py and fetched there into .deps/z80-vectors) record
the bus T-state by T-state. On the CPC the Gate Array holds the Z80's WAIT line so that every bus access (an opcode fetch, a
memory read or write, an I/O cycle) falls on one phase of the 1 MHz clock: the cycle on which the access is strobed is moved
to T = 1 modulo 4 (retrorecomp/cpc_timing.cpc_nops). Each family's vectors give its cost; a conditional instruction gives two
(not taken / taken), a block instruction two (ends / repeats).

What the vectors do not hold comes from Z80 facts: the 176 undefined ED opcodes (two opcode fetches), the prefix bytes (0 in
their table: the prefixed table holds the cost; a DD or FD before DD, ED or FD is a lone prefix of one fetch), and two outcomes
not in the 32 samples: DJNZ behind a DD prefix (the FD form's, the prefix
acts the same), and the ending of LDIR, CPIR, INIR, OTIR and their decrementing forms (the one-shot LDI, CPI, INI, OUTI...: a
block instruction that stops has the same cycles).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import cpc_timing

PREFIXES = {'': 'base', 'cb': 'cb', 'ed': 'ed', 'dd': 'dd', 'fd': 'fd', 'dd cb __': 'ddcb', 'fd cb __': 'fdcb'}
BLOCK = {0xB0: 0xA0, 0xB1: 0xA1, 0xB2: 0xA2, 0xB3: 0xA3, 0xB8: 0xA8, 0xB9: 0xA9, 0xBA: 0xAA, 0xBB: 0xAB}


def vectors_path() -> Path:
    from fetch_z80_vectors import REVISION  # noqa: E402  (tools/ is on the path when run from here)
    return ROOT / '.deps' / 'z80-vectors' / f'{REVISION}-32.json'


def derive(path: Path | None = None) -> tuple[dict, dict]:
    """(costs, extra) from the vectors: costs[table][opcode] the cost not taken / not repeating, extra[table][opcode] what a
    taken branch or a repeating block instruction adds."""
    sys.path.insert(0, str(ROOT / 'tools'))
    path = path or vectors_path()
    data = json.loads(path.read_text(encoding='utf-8'))
    seen: dict[str, Counter] = defaultdict(Counter)
    for case in data['cases']:
        seen[case['family']][cpc_timing.cpc_nops([flags for _, _, flags in case['cycles']])] += 1
    costs = {table: [None] * 256 for table in PREFIXES.values()}
    extra = {table: {} for table in PREFIXES.values()}
    for family, counts in seen.items():
        prefix, _, opcode = family.rpartition(' ')
        table = PREFIXES[prefix]
        values = sorted(counts)
        costs[table][int(opcode, 16)] = values[0]
        if len(values) == 2:
            extra[table][int(opcode, 16)] = values[1] - values[0]
        elif len(values) > 2:
            raise ValueError(f'{family}: more than two costs {values}')
    # DJNZ behind DD: the FD form's two outcomes.
    if 0x10 not in extra['dd'] and 0x10 in extra['fd']:
        costs['dd'][0x10], extra['dd'][0x10] = costs['fd'][0x10], extra['fd'][0x10]
    # A block instruction that ends costs its one-shot form; the samples are the repeating case.
    for repeat, single in BLOCK.items():
        if repeat not in extra['ed']:
            observed = costs['ed'][repeat]
            costs['ed'][repeat] = costs['ed'][single]
            extra['ed'][repeat] = observed - costs['ed'][single]
    # The undefined ED opcodes are not in the vectors: each is two opcode fetches and nothing else (8 T-states).
    fetch = ['----', 'r-m-', '----', '----']
    for n, value in enumerate(costs['ed']):
        if value is None:
            costs['ed'][n] = cpc_timing.cpc_nops(fetch + fetch)
    # A prefix byte is no instruction of its table: 0, the cost is the prefixed table's (base CB, DD, ED, FD; DD CB and FD CB).
    # A DD or FD followed by DD, ED or FD is a lone prefix of one opcode fetch, and the next byte is decoded afresh.
    for prefix in (0xCB, 0xDD, 0xED, 0xFD):
        costs['base'][prefix] = 0
    for table in ('dd', 'fd'):
        costs[table][0xCB] = 0
        for prefix in (0xDD, 0xED, 0xFD):
            costs[table][prefix] = cpc_timing.cpc_nops(fetch)
    missing = [(table, n) for table, row in costs.items() for n, value in enumerate(row) if value is None]
    if missing:
        raise ValueError(f'no vector for {missing[:8]}')
    return costs, extra


def render(costs: dict, extra: dict) -> str:
    lines = ['COSTS = {']
    for table, row in costs.items():
        digits = ''.join(str(value) for value in row)
        lines.append(f"    '{table}': (")
        for at in range(0, 256, 64):
            lines.append(f"        '{digits[at:at + 64]}'")
        lines.append('    ),')
    lines.append('}')
    lines.append('EXTRA = {')
    for table, values in extra.items():
        items = ', '.join(f'0x{opcode:02X}: {value}' for opcode, value in sorted(values.items()))
        lines.append(f"    '{table}': {{{items}}},")
    lines.append('}')
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--vectors', type=Path, help='the vector file (default: .deps/z80-vectors of this checkout)')
    args = parser.parse_args()
    costs, extra = derive(args.vectors)
    if args.check:
        held = {table: [cpc_timing.cost(table, n) for n in range(256)] for table in costs}
        same = held == costs and {t: dict(v) for t, v in cpc_timing.EXTRA.items()} == extra
        print('the table equals the derivation' if same else 'the table differs from the derivation')
        return 0 if same else 1
    print(render(costs, extra))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
