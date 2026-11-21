"""Inventory of a folder of Amstrad CPC disks (.dsk, or ZIPs holding one): numbers about each image, never its bytes.

    python -B tools/cpc_panel.py <folder> [--output .build/cpc-panel/inventory.json]

For each disk: its SHA-256 and size, standard or extended, cylinders and sides, the AMSDOS format of cylinder 0, the tracks
that are not plain AMSDOS tracks (the protections' tracks), the weak, deleted and error sectors an extended image recorded, the
sector sizes, and the start command the catalogue gives (RUN"..., |CPM, or undecided with its candidates). A summary
counts them. The disks are read in place and never changed; the folder is not walked below its own level.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.cpc_disk import read_disk


def inventory(folder: Path) -> dict:
    rows, refused = [], []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if path.suffix.casefold() not in ('.dsk', '.zip') or not path.is_file():
            continue
        try:
            disk = read_disk(path)
        except ValueError as error:
            refused.append({'file': path.name, 'reason': str(error)})
            continue
        rows.append({'file': path.name, 'sha256': disk.sha256, 'size': disk.size, **disk.features(),
                     'files': len(disk.files), 'run': disk.run_command, 'candidates': list(disk.candidates)})
    summary = {
        'disks': len(rows),
        'refused': len(refused),
        'extended': sum(row['extended'] for row in rows),
        'formats': dict(Counter(row['format'] for row in rows)),
        'with_odd_tracks': sum(1 for row in rows if row['odd_tracks']),
        'with_weak_sectors': sum(1 for row in rows if row['weak_sectors']),
        'with_error_sectors': sum(1 for row in rows if row['error_sectors']),
        'two_sides': sum(1 for row in rows if row['sides'] == 2),
        'start': dict(Counter('undecided' if row['run'] is None else 'RUN' if row['run'].startswith('RUN') else row['run']
                              for row in rows)),
    }
    return {'version': 1, 'folder': folder.name, 'summary': summary, 'disks': rows, 'refused': refused}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / '.build' / 'cpc-panel' / 'inventory.json')
    args = parser.parse_args()
    result = inventory(args.folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(result['summary']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
