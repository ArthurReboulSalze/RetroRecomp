"""The Z80 bus-cycle table (retrorecomp/z80_timing.py) against the SingleStepTests z80 vectors (MIT, JSMoo), ROM-free.

    python -B tools/fetch_z80_vectors.py            (once: caches the pinned sample in .deps/z80-vectors)
    python -B tools/z80_timing_vectors.py [--fetch] [--show N]

Each vector gives the address on the bus at every T-state of one instruction. The table's cycles for that encoding are expanded
into the same list from the vector's initial state (an M1 is its address twice then the refresh address, I and R before its
increment, twice; a memory cycle its address three times; an I/O cycle the port four times; an internal T-state its address
once), the extra cycles of a taken branch or a repeating block instruction added when the vector's length says it went that
way, and the two lists must be equal T-state for T-state. Every family of the sample is counted; a family the table does not
describe is named with its reason. Exit 0 when every compared vector agrees and no family is left unexplained.

A branch or a block repetition seen one way only in the sample (32 vectors a family) is completed from the whole family file
(1,000 vectors, the same pinned revision; `--fetch` caches the few it needs in .deps/z80-vectors/families). A repeating block
instruction whose random states always go round again (BC is almost never 1) has, as its last pass, exactly the cycles of its
single form (LDIR's are LDI's), which the table states and the single form's vectors check.

This is the independent evidence of the table (docs/ZX_SPECTRUM.md, contention): the chain's emitter and reference CPU both
read the same table, so their agreement says nothing about whether the table is right; these vectors do.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.z80_timing import cycles, length  # noqa: E402

GROUPS = {'': '', 'cb': 'cb', 'dd': 'dd', 'fd': 'fd', 'ed': 'ed', 'dd cb': 'ddcb', 'fd cb': 'fdcb'}


def family_encoding(name: str):
    """'dd cb __ 06' -> ('ddcb', 0x06); '34' -> ('', 0x34); None for a family that is not one encoding of the seven groups."""
    parts = name.lower().split()
    if parts[:2] in (['dd', 'cb'], ['fd', 'cb']) and len(parts) == 4 and parts[2] == '__':
        return GROUPS[' '.join(parts[:2])], int(parts[3], 16)
    if len(parts) == 2 and parts[0] in ('cb', 'dd', 'fd', 'ed'):
        return parts[0], int(parts[1], 16)
    if len(parts) == 1:
        return '', int(parts[0], 16)
    return None


def expand(group: str, cycle_list, state: dict, refresh_after: bool = False) -> list[int]:
    """The address on the bus at each T-state of `cycle_list`, from the instruction's initial `state` (a vector's `initial`)."""
    ram = {address: value for address, value in state['ram']}

    def mem(address: int) -> int:
        return ram.get(address & 0xFFFF, 0)

    pc, sp = state['pc'], state['sp']
    prefixed = group in ('dd', 'fd', 'ed', 'ddcb', 'fdcb')
    operand = pc + (2 if prefixed else 1)
    index = state['ix'] if group in ('dd', 'ddcb') else state['iy']
    displacement = mem(pc + 2)
    values = {'hl': state['h'] << 8 | state['l'], 'bc': state['b'] << 8 | state['c'], 'de': state['d'] << 8 | state['e'],
              'sp': sp, 'sp+1': sp + 1, 'sp-1': sp - 1, 'sp-2': sp - 2,
              'ixd': index + (displacement - 256 if displacement > 127 else displacement),
              'nn': mem(operand) | mem(operand + 1) << 8, 'an': state['a'] << 8 | mem(operand),
              'bc-': ((state['b'] - 1) & 0xFF) << 8 | state['c']}
    values['nn+1'] = values['nn'] + 1
    r, fetches, refresh, out = state['r'], 0, None, []

    def address(source: str) -> int:
        if source == 'ir':
            return refresh
        if source == 'pc':
            return pc
        if source.startswith('pc+'):
            return pc + int(source[3:])
        return values[source]

    for kind, source, count in cycle_list:
        if kind == 'm1':
            refresh = state['i'] << 8 | (r & 0x80) | ((r + fetches + refresh_after) & 0x7F)
            fetches += 1
            out += [address(source) & 0xFFFF] * 2 + [refresh] * 2
        else:
            out += [address(source) & 0xFFFF] * {'rd': 3, 'wr': 3, 'in': 4, 'out': 4, 'int': count}[kind]
    return out


FAMILIES = ROOT / '.deps' / 'z80-vectors' / 'families'
# The families whose taken (or repeating) path and other path the sample does not both hold; whole files complete them.
WHOLE_FAMILIES = ('dd 10', 'ed b0', 'ed b1', 'ed b3', 'ed b8', 'ed b9', 'ed ba', 'ed bb')


def fetch_families(names) -> None:
    """Whole family files of the pinned revision (tools/fetch_z80_vectors.REVISION), cached once."""
    import urllib.parse
    import urllib.request
    from fetch_z80_vectors import REVISION
    folder = FAMILIES / REVISION
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = folder / f'{name}.json'
        if target.is_file():
            continue
        url = f'https://raw.githubusercontent.com/SingleStepTests/z80/{REVISION}/v1/' + urllib.parse.quote(f'{name}.json')
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read()
        json.loads(raw)
        target.write_bytes(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--vectors', type=Path, default=None)
    parser.add_argument('--fetch', action='store_true', help='cache the whole family files the check completes the sample with')
    parser.add_argument('--show', type=int, default=5, help='mismatching families to print in detail')
    args = parser.parse_args()
    path = args.vectors or next(iter(sorted((ROOT / '.deps' / 'z80-vectors').glob('*.json'))), None)
    if path is None or not path.is_file():
        print('No cached vectors: run python -B tools/fetch_z80_vectors.py first.')
        return 2
    data = json.loads(path.read_text(encoding='utf-8'))
    families, unexplained, compared, failed, shown, extra_paths = {}, [], 0, {}, 0, {}
    for case in data['cases']:
        families.setdefault(case['family'], []).append(case)
    if args.fetch:
        sys.path.insert(0, str(ROOT / 'tools'))
        fetch_families(WHOLE_FAMILIES)
    whole = []
    for name in WHOLE_FAMILIES:
        file = FAMILIES / data.get('revision', '') / f'{name}.json'
        if file.is_file():
            whole.append(name)
            families[name] = [dict(case, family=name) for case in json.loads(file.read_text(encoding='utf-8'))]
    for family, cases in sorted(families.items()):
        encoding = family_encoding(family)
        if encoding is None:
            unexplained.append(family)
            continue
        base, extra = cycles(*encoding)
        for case in cases:
            bus = [address for address, _, _ in case['cycles']]
            route = list(base) + (list(extra) if len(bus) == length(base) + length(extra) and extra else [])
            if extra:
                took = len(bus) == length(base) + length(extra)
                extra_paths.setdefault(family, [0, 0])[took] += 1
            expected = expand(encoding[0], route, case['initial'])
            compared += 1
            if expected != bus:
                failed.setdefault(family, []).append(case['name'])
                if shown < args.show and len(failed[family]) == 1:
                    shown += 1
                    print(f'{family}: {case["name"]}')
                    print('  vector:', ' '.join(f'{a:04x}' for a in bus))
                    print('  table: ', ' '.join(f'{a:04x}' for a in expected))
    # Positive controls: the comparison must catch a wrong table and a wrong reading of the bus.
    push = [case for case in families.get('c5', [])]
    wrong_push = [cycle for cycle in cycles('', 0xC5)[0] if cycle[0] != 'int']
    control_push = sum(expand('', wrong_push, case['initial']) != [a for a, _, _ in case['cycles']] for case in push)
    sample = [case for cases in families.values() for case in cases[:1]]
    control_refresh = sum(expand(family_encoding(case['family'])[0], cycles(*family_encoding(case['family']))[0], case['initial'],
                                 refresh_after=True) != [a for a, _, _ in case['cycles']] for case in sample
                          if family_encoding(case['family']) and len([a for a, _, _ in case['cycles']]) ==
                          length(cycles(*family_encoding(case['family']))[0]))
    print(f'controls: PUSH without its internal cycle differs on {control_push}/{len(push)} vectors; the refresh read after its '
          f'increment differs on {control_refresh} of {len(sample)} families')
    controls_ok = push and control_push == len(push) and control_refresh >= len(sample) // 2
    # The encodings of the seven groups the corpus does not hold, by reason.
    from retrorecomp.z80_chain import COST_GROUPS
    held = {family_encoding(family) for family in families}
    prefixes = {('', 0xCB), ('', 0xDD), ('', 0xED), ('', 0xFD)} | {(g, o) for g in ('dd', 'fd') for o in (0xCB, 0xDD, 0xED, 0xFD)}
    missing = [(g, o) for g in COST_GROUPS for o in range(256) if (g, o) not in held and (g, o) not in prefixes]
    ed_nops = [(g, o) for g, o in missing if g == 'ed' and length(cycles(g, o)[0]) == 8 and not cycles(g, o)[1]]
    other = [(g, o) for g, o in missing if (g, o) not in ed_nops]
    print(f'not in the corpus: {len(prefixes)} prefix bytes (each the M1 of the encoding that follows, counted there); '
          f'{len(ed_nops)} ED encodings that execute as two M1 (8 T, the undefined EDs); others: {other}')
    both = sum(1 for pair in extra_paths.values() if pair[0] and pair[1])
    one_way = sorted(f for f, pair in extra_paths.items() if not (pair[0] and pair[1]))
    # A repeat seen repeating only: its last pass is its single form's cycles (opcode less 10h), checked by that form's vectors.
    last_pass = [f for f in one_way if extra_paths[f][1] and not extra_paths[f][0] and family_encoding(f)[0] == 'ed'
                 and cycles('ed', family_encoding(f)[1])[0] == cycles('ed', family_encoding(f)[1] - 0x10)[0]
                 and f'ed {family_encoding(f)[1] - 0x10:02x}' in families and f'ed {family_encoding(f)[1] - 0x10:02x}' not in failed]
    unseen = [f for f in one_way if f not in last_pass]
    print(f'branches and repeats: {len(extra_paths)} families with an extra path ({len(whole)} completed from whole files), {both} '
          f'seen both ways; {sum(pair[1] for pair in extra_paths.values())} vectors took it, '
          f'{sum(pair[0] for pair in extra_paths.values())} did not; last pass by the single form: {last_pass}; unseen: {unseen}')
    groups = {}
    for family in families:
        encoding = family_encoding(family)
        if encoding:
            groups[encoding[0] or '(none)'] = groups.get(encoding[0] or '(none)', 0) + 1
    print(f'{len(families)} families ({", ".join(f"{g} {n}" for g, n in sorted(groups.items()))}), {compared} vectors compared, '
          f'{sum(len(v) for v in failed.values())} differ in {len(failed)} families; {len(unexplained)} families not one encoding: '
          f'{unexplained[:12]}')
    return 0 if not failed and not unexplained and not other and not unseen and controls_ok else 1


if __name__ == '__main__':
    sys.exit(main())
