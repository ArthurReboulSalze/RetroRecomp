"""The start-up picture the packaged converter shows while it unpacks: step 1
of the start-up window that takes over once Python runs (gui.startup_picture):
the logo with its own outline (transparent on Windows, a dark card on Linux),
the first gold segment and the version. Packaging writes it next to its work
files, so the version always matches."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path, version: str, transparent: bool | None = None) -> Path:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from retrorecomp.gui import startup_picture
    transparent = sys.platform == 'win32' if transparent is None else transparent
    picture = startup_picture(1, '', version, transparent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    picture.save(destination, optimize=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--version')
    args = parser.parse_args()
    if args.version is None:
        sys.path.insert(0, str(ROOT))
        from retrorecomp import __version__
        args.version = __version__
    print(build(args.destination, args.version))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
