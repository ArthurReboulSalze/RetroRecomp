"""Pictures along each route of a converted PlayStation game (gate G9 evidence: did the route reach play?).

    python tools/psx_route_captures.py EXE REPORT [--pictures 12] [--out DIR] [--routes play long-1 ...]

The routes are written again from the disc's hash and the scan level, as the report records them; a route whose script does not
have the digest the report recorded is refused. The delivered executable runs headless (no window is opened, nothing is written
beside it: no memory card) with each route's input script and leaves evenly spaced pictures. One contact sheet per route goes
under --out (default `.build/psx-route-captures`), and a line per route says how many distinct pictures the sheet holds.
A picture shows what the screen held at that frame; it does not say how far into the game the route is, and a person (or a
specialist agent) still has to look at it. Reads the game, writes only under --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def plan(report: dict) -> list[tuple[str, int, str]]:
    """(route, frames, script) as the conversion that wrote `report` played them; refused when a rewritten script's digest is
    not the one the report recorded (`script_sha256`)."""
    from retrorecomp import psx_conversion
    rows = report['final_checks']
    frames = next(int(row['frames']) for row in rows if row['name'] in ('attract', 'play'))
    if not any(row['name'] == 'attract' for row in rows):
        frames = max(psx_conversion.BOOT_FRAMES + 600, frames)
    written = {name: (count, text) for name, count, text in
               psx_conversion.routes(report['rom']['sha256'], frames=frames, level=report['scan_level'])}
    out = []
    for row in rows:
        count, text = written.get(row['name'], (None, None))
        if text is None or hashlib.sha256(text.encode('ascii')).hexdigest() != row['script_sha256']:
            raise SystemExit(f"The {row['name']} route written again differs from the one the report records "
                             '(script_sha256): another converter revision?')
        out.append((row['name'], count, text))
    return out


def main() -> int:
    from pce_route_captures import contact_sheet, spacing
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--pictures', type=int, default=12)
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'psx-route-captures')
    parser.add_argument('--routes', nargs='*')
    arguments = parser.parse_args()
    report = json.loads(arguments.report.read_text(encoding='utf-8'))
    title = arguments.exe.stem
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    for name, frames, text in plan(report):
        if arguments.routes and name not in arguments.routes:
            continue
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            script = work / 'inputs.txt'
            script.write_text(text, encoding='ascii', newline='\n')
            pictures = work / 'pictures'
            pictures.mkdir()
            result = subprocess.run([str(arguments.exe), '--headless', '--frames', str(frames), '--script', str(script),
                                     '--capture', str(pictures), '--capture-every', str(spacing(frames, arguments.pictures))],
                                    cwd=work, env=environment, capture_output=True, creationflags=NO_WINDOW,
                                    timeout=max(1200, frames // 3))
            found = sorted(pictures.glob('frame-*.ppm'))
            distinct = contact_sheet(found, arguments.out / title / f'{name}.png')
            print(f'{title} {name}: {frames} frames, exit {result.returncode}, {len(found)} pictures, {distinct} distinct',
                  flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
