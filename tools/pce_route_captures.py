"""Pictures along each route of a converted PC Engine game (gate G9 evidence: did the route reach play?).

    python tools/pce_route_captures.py ROM EXE REPORT [--pictures 12] [--out DIR] [--routes play long-1 ...]

The conversion's routes are written from the card: this tool writes them again from the card's hash, with the scan level and the
number of Run presses its report records, and runs the delivered executable headless (no window is opened) with each route's input
script, asking for evenly spaced pictures. One contact sheet per route goes under --out (default `.build/pce-route-captures`), plus
a line per route with how many distinct pictures the sheet holds. It reads the card and the game and writes only under --out. A
picture shows what the screen held at that frame; it does not say how far into the game the route is, and a person (or a specialist
agent) still has to look at it.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
COLUMNS = 4


def plan(report: dict) -> list[tuple[str, int, str]]:
    """(route, frames, input script) as the conversion that wrote `report` played them."""
    from retrorecomp.pce_conversion import routes
    presses = int((report.get('route_start') or {}).get('run_presses') or 3)
    frames = {row['name']: row['frames'] for row in report['final_checks']}
    rows = routes(report['rom']['sha256'], frames=frames.get('play', 3600), level=report['scan_level'], presses=presses)
    return [row for row in rows if row[0] in frames]


def spacing(frames: int, pictures: int) -> int:
    """The capture period that gives about `pictures` pictures of a route, the first one past the start."""
    return max(1, frames // max(1, pictures))


def read_ppm(path: Path):
    """A binary PPM as a Pillow image."""
    from PIL import Image
    return Image.open(path).convert('RGB')


def contact_sheet(pictures: list[Path], target: Path) -> int:
    """Write the pictures as a grid; returns how many of them differ from each other."""
    from PIL import Image
    images = [read_ppm(path) for path in pictures]
    if not images:
        return 0
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    rows = (len(images) + COLUMNS - 1) // COLUMNS
    sheet = Image.new('RGB', (COLUMNS * (width + 4), rows * (height + 4)), (32, 32, 32))
    for index, image in enumerate(images):
        sheet.paste(image, ((index % COLUMNS) * (width + 4) + 2, (index // COLUMNS) * (height + 4) + 2))
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return len({image.tobytes() for image in images})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('rom', type=Path, help='the card: only checked against the report')
    parser.add_argument('exe', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--pictures', type=int, default=12)
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'pce-route-captures')
    parser.add_argument('--routes', nargs='*', help='route names (default: all those of the report)')
    args = parser.parse_args()
    from retrorecomp.pce_rom import read_hucard
    report = json.loads(args.report.read_text(encoding='utf-8'))
    if read_hucard(args.rom).sha256 != report['rom']['sha256']:
        raise SystemExit('The card is not the one this report was written for.')
    out = args.out.resolve() / report['rom']['sha256'][:12]
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1')
    for name, frames, script in plan(report):
        if args.routes and name not in args.routes:
            continue
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob('frame-*.ppm'):
            old.unlink()
        inputs = folder / 'route.inputs'
        inputs.write_text(script, encoding='ascii', newline='\n')
        done = subprocess.run([str(args.exe.resolve()), '--headless', '--frames', str(frames), '--script', str(inputs),
                               '--capture', str(folder), '--capture-every', str(spacing(frames, args.pictures))],
                              cwd=folder, env=env, timeout=max(600, frames // 5), capture_output=True, text=True,
                              creationflags=NO_WINDOW)
        if done.returncode:
            print(f'{name}: the game stopped ({done.returncode}): {done.stderr.strip()[-200:]}')
            continue
        pictures = sorted(folder.glob('frame-*.ppm'))
        distinct = contact_sheet(pictures, out / f'{name}.png')
        print(f'{name}: {len(pictures)} pictures, {distinct} distinct: {out / f"{name}.png"}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
