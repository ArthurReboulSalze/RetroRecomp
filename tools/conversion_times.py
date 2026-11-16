"""Measure typical conversion times from existing conversion reports, for the reviewed table assets/conversion-times.json.

Reads the ``conversion-report.json`` files under the folders given (an export folder's ``datas/reports``, a campaign's
output), read only, and prints, per machine and scan level, the quartiles of the recorded wall time of one game
(``timings.total``, else ``conversion_wall_seconds``) in the table's format. Nothing is converted, and no ROM is read.

Which reports count:

* Windows reports only (the reference PC of the table is a Windows PC), built with the portable toolchain (``llvm``) or
  recording none (a machine whose conversion compiles nothing); Visual Studio builds are left out.
* A total under ``--floor`` seconds is an export taken over as it was, not a conversion.
* The reports of ``--since`` or later when there are at least ``--min-reports`` of them for a machine and level; otherwise
  those of ``--fallback-since`` or later. A cell with fewer reports than ``--min-reports`` is printed apart, and the table
  derives that level from the machine's standard time instead (time_estimates.LEVEL_FACTORS).

The figures are those of games converted in batches, several at once (three by default on Windows): they are the time a
player waits for one game in such a batch, not the time of a game converted alone. The table is written by hand from this
output and reviewed; this tool never writes it.

    python -B tools/conversion_times.py <folder> [<folder> ...]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

SKIPPED_FOLDERS = frozenset(('.deps', 'node_modules', 'CMakeFiles', '_deps', 'tools', 'boxart-cache', '.git'))


def version_key(text) -> tuple:
    try:
        return tuple(int(part) for part in str(text).split('.')[:3])
    except ValueError:
        return (0,)


def report_row(data: dict) -> dict | None:
    """The machine, level, version and seconds of one report, or None when it does not count."""
    if not isinstance(data, dict):
        return None
    figures = data.get('timings') if isinstance(data.get('timings'), dict) else {}
    total = figures.get('total') or data.get('conversion_wall_seconds')
    system = data.get('system')
    system = system.get('id') if isinstance(system, dict) else system
    if not isinstance(total, (int, float)) or not isinstance(system, str):
        return None
    if 'linux' in str(data.get('target') or ''):
        return None
    toolchain = data.get('toolchain') or (data.get('build') or {}).get('toolchain')
    kind = toolchain.get('kind') if isinstance(toolchain, dict) else None
    if kind not in (None, 'llvm'):
        return None
    scan = data.get('scan') if isinstance(data.get('scan'), dict) else {}
    level = scan.get('level') or data.get('scan_level') or 'standard'
    return {'system': system, 'level': level, 'version': str(data.get('version') or ''),
            'seconds': float(total), 'created': str(data.get('created_utc') or '')}


def collect(folders) -> list[dict]:
    rows, seen = [], set()
    for folder in folders:
        for directory, subfolders, names in os.walk(folder):
            subfolders[:] = [name for name in subfolders if name not in SKIPPED_FOLDERS]
            if 'conversion-report.json' not in names:
                continue
            try:
                data = json.loads((Path(directory) / 'conversion-report.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            row = report_row(data)
            if row is None:
                continue
            key = (row['system'], row['created'], round(row['seconds'], 1))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def quartiles(values) -> list[int]:
    values = sorted(values)
    if len(values) == 1:
        return [round(values[0])] * 3
    low, middle, high = statistics.quantiles(values, n=4, method='inclusive')
    return [round(low), round(middle), round(high)]


def summarize(rows, *, since='1.7.0', fallback_since='1.6.0', min_reports=3, floor=5.0) -> dict:
    """{machine: {level: {'seconds': [p25, median, p75], 'longest': s, 'reports': n, 'versions': 'a..b'}}}; cells under min_reports
    are kept under the key 'few' of their machine."""
    cells: dict = {}
    for row in rows:
        if row['seconds'] >= floor and version_key(row['version']) >= version_key(fallback_since):
            cells.setdefault((row['system'], row['level']), []).append(row)
    table: dict = {}
    for (system, level), found in sorted(cells.items()):
        recent = [row for row in found if version_key(row['version']) >= version_key(since)]
        used = recent if len(recent) >= min_reports else found
        versions = sorted({row['version'] for row in used}, key=version_key)
        cell = {'seconds': quartiles(row['seconds'] for row in used),
                'longest': round(max(row['seconds'] for row in used)), 'reports': len(used),
                'versions': f'{versions[0]}..{versions[-1]}'}
        machine = table.setdefault(system, {})
        if len(used) >= min_reports:
            machine[level] = cell
        else:
            machine.setdefault('few', {})[level] = cell
    return table


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folders', nargs='+', type=Path)
    parser.add_argument('--since', default='1.7.0')
    parser.add_argument('--fallback-since', default='1.6.0')
    parser.add_argument('--min-reports', type=int, default=3)
    parser.add_argument('--floor', type=float, default=5.0)
    options = parser.parse_args(argv)
    rows = collect(options.folders)
    table = summarize(rows, since=options.since, fallback_since=options.fallback_since,
                      min_reports=options.min_reports, floor=options.floor)
    json.dump({'reports_read': len(rows), 'machines': table}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
