"""Independent MC68000 vectors of the instruction groups no other fixture holds, replayed through the Mega Drive generator (gate G10).

    python -B tools/megadrive_groups_selftest.py [--record]

The vectors are `tests/fixtures/m68k-groups` (2,895 SingleStepTests/m68000 vectors of 85 instruction groups, MIT, generated with MAME,
not recorded from hardware; synthetic instruction data, no cartridge; `tools/build_m68000_groups_fixture.py`). They are replayed the
way `tools/megadrive_prefetch_selftest.py` replays the other fixtures (imported, not copied): the Mega Drive generator's translated
steps and the same interpreter with every instruction interpreted, each on a flat 24-bit bus, compared with the vector's registers,
memory, prefetch queue, ordered bus transactions and clocks.

Unlike the other fixtures this one is not expected to pass whole: it was added because it holds the groups they do not, and the
pinned 68000 core differs from the vectors in some of them. The harness is run in its collecting mode (`RR_MD_COLLECT_FAILURES`:
every failing vector is listed instead of the first one ending the run) and each failing vector is sorted by the first thing that
differed: the final state (registers or memory), the clocks (the total of an instruction) or the bus (the number, order, address
or clock position of the transactions). `tests/fixtures/m68k-groups/deviations.json` is the list of what is known to differ, per
group and per kind; the replay fails when a group differs that is not listed, when a count changes in either direction (a fix has
to shrink the list, a regression is refused), or when the native steps and the reference path do not fail on the same vectors.
`--record` writes the observed counts to that file; the causes are written by hand in docs/CPU_68000.md.

What it shows and what it does not: CPU behaviour of the native steps and of the reference interpreter against an oracle neither was
written from. It shows nothing of the Mega Drive bus, of hardware fidelity (the oracle is MAME) or of gameplay.
"""
from __future__ import annotations
import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import megadrive_prefetch_selftest as replay

FIXTURE = 'm68k-groups'
DEVIATIONS = ROOT / 'tests/fixtures' / FIXTURE / 'deviations.json'
KINDS = ('state', 'clocks', 'bus')
LINE = re.compile(r'FAIL (\S+): (\d+) (.*) (native|reference) (.+?) expected=(\S+) actual=(\S+)$')


def kind(field: str) -> str:
    """What differed first: the final state, the clocks of the instruction or its bus transactions."""
    if field.startswith(('register[', 'memory[')):
        return 'state'
    if field in ('audio cycles', 'CPU cycles'):
        return 'clocks'
    return 'bus'


def failures(text: str) -> dict[str, dict[tuple[str, str], str]]:
    """The failing vectors of a collecting run: {'native': {(group, number): kind}, 'reference': {...}}."""
    found: dict = {'native': {}, 'reference': {}}
    for line in text.splitlines():
        match = LINE.match(line.strip())
        if match:
            found[match[4]][(match[1], match[2])] = kind(match[5])
    return found


def counts(found: dict[tuple[str, str], str]) -> dict[str, dict[str, int]]:
    result: dict = collections.defaultdict(lambda: dict.fromkeys(KINDS, 0))
    for (group, _), what in found.items():
        result[group][what] += 1
    return {group: {what: n for what, n in row.items() if n} for group, row in sorted(result.items())}


def problems(observed: dict, known: dict, same_paths: bool) -> list[str]:
    """Differences between what the replay saw and the list of known deviations (empty: the list is exact)."""
    text = [] if same_paths else ['the native steps and the reference path do not fail on the same vectors']
    for group in sorted(set(observed) | set(known)):
        if observed.get(group, {}) != known.get(group, {}):
            text.append(f'{group}: seen {observed.get(group, {}) or "none"}, listed {known.get(group, {}) or "none"}')
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true', help='write the observed counts to deviations.json')
    record = parser.parse_args().record
    project, checks, fixture, external, authored = replay.build(FIXTURE)
    done = subprocess.run([str(checks)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**os.environ, 'RR_MD_COLLECT_FAILURES': '1'},
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    found = failures(done.stderr)
    observed = counts(found['native'])
    result = {'fixture': FIXTURE, 'source': fixture['source'], 'revision': fixture['revision'], 'vectors': external,
              'failing_vectors': len(found['native']), 'passing_vectors': external - len(found['native']),
              'kinds': {what: sum(row.get(what, 0) for row in observed.values()) for what in KINDS},
              'groups_with_deviations': len(observed), 'same_failures_on_both_paths': found['native'] == found['reference']}
    if done.returncode not in (0, 1) or (done.returncode == 0 and found['native']):
        sys.exit(f'the replay ended with status {done.returncode}:\n{done.stderr[-2000:]}')
    if record:
        DEVIATIONS.write_text(json.dumps(observed, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    known = json.loads(DEVIATIONS.read_text(encoding='utf-8')) if DEVIATIONS.is_file() else {}
    problem = problems(observed, known, result['same_failures_on_both_paths'])
    result.update(problems=problem, passed=not problem)
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    for text in problem:
        print('PROBLEM', text)
    return 1 if problem else 0


if __name__ == '__main__':
    sys.exit(main())
