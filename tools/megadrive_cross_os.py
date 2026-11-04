"""Mega Drive: one game converted on two systems, route by route (gate G13, the cross-OS witness).

    python -B tools/megadrive_cross_os.py compare REPORT_A REPORT_B [REPORT_A REPORT_B ...]

Each argument is the `conversion-report.json` of the same game converted on Windows and on Debian (same engine revision, same
converter tree, same scan level, an empty learning library, no shared base: `batch ... --no-shared-base --no-online-cover`). The
tool compares, route by route, what the conversion measured on the native run of the delivered build and keeps no picture and no
ROM byte: the hash of the last frame, the sequence hash, the CPU/prefetch hash, the counters of native and interpreted 68000 and
Z80 instructions, the bus budget and Z80 timing misses, the video mode counters and the Z80 learning record. A route is identical
when every one of those fields is equal; otherwise the fields that differ are listed. Fields that depend on the machine running the
conversion (times, paths) are not compared.

It says that the native run of the same converted game does the same thing on both systems on the routes of the conversion. It does
not say anything of the routes that were not run, of the original hardware or of speed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# What a route of `final_checks` holds that depends on the system running the conversion, not on the game.
IGNORED = {'scenario'}


def routes(report: Path) -> dict[str, dict]:
    data = json.loads(Path(report).read_text(encoding='utf-8'))
    if data.get('status') not in ('supported', 'experimental', 'validated'):
        raise SystemExit(f'{report}: status {data.get("status")!r}, not a finished conversion')
    return {check['scenario']: {key: value for key, value in check.items() if key not in IGNORED}
            for check in data.get('final_checks', [])}


def compare(first: Path, second: Path) -> dict:
    a, b = routes(first), routes(second)
    result = {'game': json.loads(Path(first).read_text(encoding='utf-8')).get('rom', {}).get('name'), 'routes': {}}
    for scenario in sorted(set(a) | set(b)):
        if scenario not in a or scenario not in b:
            result['routes'][scenario] = {'identical': False, 'differs': ['the route is not in both reports']}
            continue
        differing = sorted(key for key in set(a[scenario]) | set(b[scenario]) if a[scenario].get(key) != b[scenario].get(key))
        result['routes'][scenario] = {'identical': not differing, 'differs': differing,
                                      'frames': a[scenario].get('frames')}
    result['identical'] = bool(result['routes']) and all(row['identical'] for row in result['routes'].values())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['compare'])
    parser.add_argument('reports', nargs='+', type=Path, help='REPORT_A REPORT_B pairs')
    options = parser.parse_args()
    if len(options.reports) % 2:
        parser.error('the reports come in pairs: Windows, then Debian')
    results = [compare(options.reports[i], options.reports[i + 1]) for i in range(0, len(options.reports), 2)]
    total = sum(len(item['routes']) for item in results)
    same = sum(1 for item in results for row in item['routes'].values() if row['identical'])
    print(json.dumps({'games': results, 'routes': total, 'identical_routes': same}, indent=1))
    return 0 if same == total else 1


if __name__ == '__main__':
    sys.exit(main())
