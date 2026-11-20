"""Record this release's role stamps, per console, in assets/release-stamps.json (retrorecomp/compatibility.py).

At release time, on the tree that is published:
    python -B tools/release_stamps.py --write    adds (or replaces) the entry of the running version
    python -B tools/release_stamps.py --check    fails when that entry is missing or differs from the tree

The next releases read it to show an export of this release as compatible with them when its console's stamps did
not move. No ROM, no export is read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import __version__  # noqa: E402
from retrorecomp.compatibility import RESOURCE, ROLES, load, record  # noqa: E402
from retrorecomp.compilation_inputs import role_stamps  # noqa: E402
from retrorecomp.systems import system_ids  # noqa: E402


def tree_stamps() -> dict:
    return {system: {role: role_stamps(system)[role] for role in ROLES} for system in sorted(system_ids())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--write', action='store_true')
    action.add_argument('--check', action='store_true')
    parser.add_argument('--file', type=Path, default=ROOT / RESOURCE)
    options = parser.parse_args(argv)
    stamps = tree_stamps()
    if options.check:
        recorded = load(options.file).get(__version__)
        if recorded != stamps:
            print(f'{options.file.name}: the stamps of {__version__} are '
                  + ('missing' if recorded is None else 'not those of this tree') + ' (run --write)')
            return 1
        print(f'{options.file.name}: {__version__} recorded for {len(stamps)} consoles')
        return 0
    data = record(options.file, __version__, stamps)
    options.file.write_bytes((json.dumps(data, indent=1, sort_keys=False) + '\n').encode('utf-8'))
    print(f'{options.file.name}: {__version__} recorded for {len(stamps)} consoles ({len(data["releases"])} releases)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
