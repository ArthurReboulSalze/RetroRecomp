"""Pictures along each route of a converted Amiga game (gate G9 evidence: did the route reach play?).

    python tools/amiga_route_captures.py EXE REPORT [--pictures 12] [--out DIR] [--routes main long-1 ...]

The routes are written again from the install's hash and the slave's quit key, as the report records them; the delivered executable runs headless (no window is opened) with each route's input script and leaves
evenly spaced pictures. One contact sheet per route goes under --out (default `.build/amiga-route-captures`), and a line per route says how many distinct pictures the sheet holds. A game with a save writes it under a temporary folder.
A picture shows what the screen held at that frame; it does not say how far into the game the route is, and a person (or a specialist agent) still has to look at it. Reads the game, writes only under --out.
"""
from __future__ import annotations

import argparse
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


def plan(report: dict) -> list[tuple[str, int, list]]:
    """(route, frames, events) as the conversion that wrote `report` played them."""
    from retrorecomp import amiga_conversion
    key_exit = int(report['whdload'].get('key_exit') or 0)
    identity = report['source_identity']
    rows = []
    for row in report['final_checks']:
        name, frames = row['route'], int(row.get('frames_run') or row['frames'])
        written = int(row['frames'])
        if name == 'main':
            events = amiga_conversion.main_route(written, key_exit)
        elif name == 'explore':
            events = amiga_conversion.explore_route(written, key_exit)
        else:
            events = amiga_conversion.long_route(identity, int(name.split('-')[1]) - 1, written, key_exit)
        rows.append((name, frames, events))
    return rows


def main() -> int:
    from pce_route_captures import contact_sheet, spacing
    from retrorecomp import amiga_conversion
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--pictures', type=int, default=12)
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'amiga-route-captures')
    parser.add_argument('--routes', nargs='*')
    arguments = parser.parse_args()
    report = json.loads(arguments.report.read_text(encoding='utf-8'))
    title = arguments.exe.stem
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    for name, frames, events in plan(report):
        if arguments.routes and name not in arguments.routes:
            continue
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            script = amiga_conversion.write_events(work / 'inputs.txt', events)
            stem = work / 'picture'
            result = subprocess.run([str(arguments.exe), '--headless', '--frames', str(frames), '--input-events', str(script), '--saves', str(work / 'saves'),
                                     '--capture', str(stem), '--capture-every', str(spacing(frames, arguments.pictures))],
                                    cwd=work, env=environment, capture_output=True, creationflags=NO_WINDOW, timeout=max(1200, frames // 4))
            pictures = sorted(work.glob('picture.*.ppm'))
            distinct = contact_sheet(pictures, arguments.out / title / f'{name}.png')
            print(f'{title} {name}: {frames} frames, exit {result.returncode}, {len(pictures)} pictures, {distinct} distinct', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
