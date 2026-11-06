#!/usr/bin/env python3
"""Draw the qualification progress and the readable matrix of docs/QUALIFICATION.md, and its short form in README.md, from the matrix in letters.

The matrix G1..G16 x nine consoles, written in letters (`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable), is
the one source of truth; test_machine_registry reads it too. This tool writes, between two markers of the same page,

* one gauge per console: its status (read from the profile registry, never typed), a ten-cell bar, a percentage and the
  count of each letter. The percentage is (Y + 0.5 x P) / the gates that apply to the console: `-` leaves the count,
  `?` and `N` count 0, the result is rounded half up to the unit. It says how far a console is through the qualification
  list. It is not a quality score, it mixes none of the five measures (native code, CPU fidelity, hardware fidelity,
  gameplay validation, physical latency) and it never decides a status: leaving the experimental status is the owner's
  decision (gate G14);
* the matrix with symbols, the console names and the short name of each gate (the third column of the "Gates" table);
* in README.md, between two markers of its own, the short form: one line per console with its bar, its percentage and its status.
  Both blocks come from the same matrix and the same `--check`, so the README cannot drift from it.

    python tools/qualification_gauges.py --check    # exit 1 when the page differs from what the matrix says
    python tools/qualification_gauges.py --write    # rewrite the block between the markers
    python tools/qualification_gauges.py --short    # print the compact form (one line per console), for a README
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / 'docs' / 'QUALIFICATION.md'
README = REPO / 'README.md'
BEGIN = '<!-- qualification-gauges:begin (written by tools/qualification_gauges.py: edit the matrix in letters, not this block) -->'
END = '<!-- qualification-gauges:end -->'
README_BEGIN = '<!-- qualification-gauges:begin (written by tools/qualification_gauges.py from docs/QUALIFICATION.md: edit the matrix there, not this block) -->'
ANCHOR = 'docs/QUALIFICATION.md#progress-through-the-qualification-list'
SYMBOLS = {'Y': '✅', 'P': '🟡', 'N': '❌', '?': '❔', '-': '➖'}
MEANING = {'Y': 'met', 'P': 'partial', 'N': 'no', '?': 'unknown', '-': 'not applicable'}
CELLS = 10


def _rows(text: str, header_start: str):
    """The rows of the first table whose header line starts with header_start: (header cells, [row cells])."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header_start))
    split = lambda line: [cell.strip() for cell in line.strip().strip('|').split('|')]
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith('| G'):
            break
        rows.append(split(line))
    return split(lines[start]), rows


def read_matrix(text: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    """(console ids in column order, {gate: {console id: letter}}) from the matrix in letters."""
    header, rows = _rows(text, '| Gate |')
    ids = header[1:]
    return ids, {row[0]: dict(zip(ids, row[1:])) for row in rows}


def read_pages(text: str) -> dict[str, str]:
    """{console id: file name of its page under docs/} from the "| Console | Page |" table below the matrix in letters."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('| Console | Page |'))
    pages = {}
    for line in lines[start + 2:]:
        if not line.startswith('| '):
            break
        console, link = (cell.strip() for cell in line.strip().strip('|').split('|'))
        pages[console] = link[link.index('](') + 2:link.rindex(')')]
    return pages


def read_short_names(text: str) -> dict[str, str]:
    """{gate: short name} from the third column of the "Gates" table."""
    header, rows = _rows(text, '| # | Gate |')
    column = header.index('Short name')
    return {row[0]: row[column] for row in rows}


def profile_facts() -> dict[str, tuple[str, str]]:
    """{console id: (name, status)} from the profile registry: the status is never written in the page by hand."""
    sys.path.insert(0, str(REPO))
    from retrorecomp.systems import ALL_PROFILES
    return {profile.id: (profile.name, profile.status) for profile in ALL_PROFILES}


def gauge(letters: list[str]) -> dict:
    """The progress of one console through the list: counts, applicable gates, percentage and bar."""
    counts = {key: letters.count(key) for key in SYMBOLS}
    applicable = len(letters) - counts['-']
    percent = int((counts['Y'] + 0.5 * counts['P']) / applicable * 100 + 0.5) if applicable else 0
    filled = int(percent / 100 * CELLS + 0.5)
    return {'counts': counts, 'applicable': applicable, 'percent': percent, 'bar': '█' * filled + '░' * (CELLS - filled)}


def _detail(counts: dict) -> str:
    parts = [f"{SYMBOLS['Y']} {counts['Y']}", f"{SYMBOLS['P']} {counts['P']}", f"{SYMBOLS['?']} {counts['?']}"]
    if counts['N']:
        parts.append(f"{SYMBOLS['N']} {counts['N']}")
    return ' · '.join(parts)


def gauges(text: str) -> list[dict]:
    ids, matrix = read_matrix(text)
    facts = profile_facts()
    out = []
    for console in ids:
        letters = [matrix[gate][console] for gate in matrix]
        out.append({'id': console, 'name': facts[console][0], 'status': facts[console][1], **gauge(letters)})
    return out


def render(text: str) -> str:
    """The block between the markers (markers excluded), built from the matrix in letters found in text."""
    ids, matrix = read_matrix(text)
    names = read_short_names(text)
    facts = profile_facts()
    rows = gauges(text)
    out = [
        'One line per console: how many of the gates that apply to it are met (a half for a partial',
        'one). `unknown` and `no` count 0 and `not applicable` is left out. It is **approximate and not a quality score**: it does not mix the five',
        'measures (native code, CPU fidelity, hardware fidelity, gameplay validation, physical latency), which stay separate in every report, and a',
        'console\'s status is never a threshold of this bar: leaving the experimental status is the owner\'s own decision (G14, see',
        '[Leaving the experimental status](#leaving-the-experimental-status)). The status column is read from the profile registry.',
        '',
        '| Console | Status | Progress | Gates |',
        '| --- | --- | --- | --- |',
    ]
    for row in rows:
        out.append(f"| {row['name']} | {row['status']} | `{row['bar']}` {row['percent']} % | {_detail(row['counts'])} |")
    out += ['',
            '**The matrix, with symbols** (the letters below are its source): ' + ', '.join(f"{SYMBOLS[key]} {MEANING[key]}" for key in SYMBOLS) + '.',
            '',
            '| Gate (short name) | ' + ' | '.join(facts[console][0] for console in ids) + ' |',
            '| --- | ' + ' | '.join(':---:' for _ in ids) + ' |']
    for gate, cells in matrix.items():
        out.append(f"| {gate} {names[gate]} | " + ' | '.join(SYMBOLS[cells[console]] for console in ids) + ' |')
    return '\n'.join(out)


def short(text: str) -> str:
    """The short form for the README: one line per console (linked to its page), its status and its bar, then a sentence."""
    pages = read_pages(text)
    lines = ['| Console | Status | Qualification progress |', '| --- | --- | --- |']
    for row in gauges(text):
        lines.append(f"| [{row['name']}](docs/{pages[row['id']]}) | {row['status']} | `{row['bar']}` {row['percent']} % |")
    lines += ['',
              '**Qualification progress**, approximate: the share of the gates that apply to a machine that are met (half a point for a',
              f'partial one), drawn from the matrix of [QUALIFICATION.md]({ANCHOR}). It is not a quality score, it mixes none of the five',
              "measures, and it never decides a status: leaving the experimental status is the owner's own decision."]
    return '\n'.join(lines)


def _split_block(text: str, begin: str = BEGIN, end: str = END) -> tuple[str, str, str]:
    start, stop = text.index(begin), text.index(end)
    return text[:start + len(begin)], text[start + len(begin):stop], text[stop:]


def current_block(text: str, begin: str = BEGIN, end: str = END) -> str:
    return _split_block(text, begin, end)[1].strip('\n')


def rewritten(text: str, readme: bool = False, matrix_text: str | None = None) -> str:
    """The page with its block rebuilt. For the README, matrix_text is the text of QUALIFICATION.md."""
    if readme:
        before, _, after = _split_block(text, README_BEGIN, END)
        return before + '\n\n' + short(matrix_text) + '\n\n' + after
    before, _, after = _split_block(text)
    return before + '\n\n' + render(text) + '\n\n' + after


def readme_in_agreement(readme_text: str, matrix_text: str) -> bool:
    return current_block(readme_text, README_BEGIN, END) == short(matrix_text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--short', action='store_true')
    args = parser.parse_args(argv)
    text = PAGE.read_text(encoding='utf-8')
    readme_text = README.read_text(encoding='utf-8')
    if args.short:
        print(short(text))
        return 0
    if args.write:
        for path, old, new in ((PAGE, text, rewritten(text)), (README, readme_text, rewritten(readme_text, True, text))):
            name = path.relative_to(REPO).as_posix()
            if new != old:
                path.write_text(new, encoding='utf-8', newline='')
                print(f'{name}: rewritten')
            else:
                print(f'{name}: already in agreement with the matrix')
        return 0
    bad = []
    if current_block(text) != render(text):
        bad.append('docs/QUALIFICATION.md')
    if not readme_in_agreement(readme_text, text):
        bad.append('README.md')
    if bad:
        print(f"{', '.join(bad)}: the block between the qualification-gauges markers does not match the matrix; "
              'run python tools/qualification_gauges.py --write')
        return 1
    print('docs/QUALIFICATION.md and README.md: the gauges match the matrix in letters')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
