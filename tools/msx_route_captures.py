"""Pictures along each route of a converted MSX or MSX2 game (gate G9 evidence: did the route reach play?).

    python tools/msx_route_captures.py EXE REPORT [--pictures 12] [--out DIR] [--routes play long-1 ...]

The conversion's routes are written again from the report (the cartridge's hash, the scan level, the chosen start), and the
delivered game runs headless (`--headless`: no window, no sound device, nothing written beside it) with each route's script,
asking for evenly spaced raw pictures (`--pictures DIR --picture-every N`). One contact sheet per route goes under --out
(default `.build/msx-route-captures/<sha12>`), with a line per route saying how many distinct pictures it holds. A picture shows
what the screen held at that frame; it does not say how far into the game the route is, and a person (or a specialist agent)
still has to look at it. No ROM is read: the game holds its cartridge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
COLUMNS = 4
# The TMS9918A's sixteen colours, as the player shows them (rrhk_msx.inc; an approximation, not measured on a set).
PALETTE = ((0, 0, 0), (0, 0, 0), (33, 200, 66), (94, 220, 120), (84, 85, 237), (125, 118, 252), (212, 82, 77),
           (66, 235, 245), (252, 85, 84), (255, 121, 120), (212, 193, 84), (230, 206, 128), (33, 176, 59),
           (201, 91, 186), (204, 204, 204), (255, 255, 255))
TMS_BYTES = 192 * 256 + 192
V9938_BYTES = 212 * 512 * 2 + 212 * 2 * 2 + 212     # the picture, the borders, R#18's horizontal adjust per line


def plan(report: dict) -> list[tuple[str, int, str]]:
    """(route, frames, script) as the conversion that wrote `report` played them."""
    from retrorecomp import msx_routes
    start = report.get('route_start') or {}
    presses = int(start.get('presses') or 1)
    variant = (presses, start['confirm']) if start.get('confirm') else presses
    frames = {row['name']: row['frames'] for row in report['final_checks']}
    rows = msx_routes.routes(report['rom']['sha256'], frames=frames.get('attract', frames.get('play', 3600)),
                             level=report['scan_level'], variant=variant)
    return [row for row in rows if row[0] in frames]


def picture(path: Path):
    """A raw picture (msx_dump_frame) as a Pillow image: the TMS9918A's 256 x 192 indices, or the V9938's 512 x 212 9-bit
    colours with a 16-half-pixel border, each line moved by its horizontal adjust as the player shows it, at 544 x 424 (its
    half-pixels are half as wide)."""
    from PIL import Image
    data = path.read_bytes()
    if len(data) == TMS_BYTES:
        image = Image.new('RGB', (256, 192))
        image.putdata([PALETTE[index & 15] for index in data[:256 * 192]])
        return image.resize((512, 384), Image.NEAREST)
    if len(data) == V9938_BYTES:
        words = struct.unpack(f'<{512 * 212}H', data[:512 * 212 * 2])
        borders = struct.unpack(f'<{212 * 2}H', data[512 * 212 * 2:512 * 212 * 2 + 212 * 4])
        adjust = struct.unpack('<212b', data[-212:])

        def rgb(c):
            return ((c >> 4) & 7) * 255 // 7, ((c >> 8) & 7) * 255 // 7, (c & 7) * 255 // 7
        pixels = []
        for line in range(212):
            row = [rgb(borders[2 * line + (x & 1)]) for x in range(544)]
            left = 16 + 2 * adjust[line]
            row[left:left + 512] = [rgb(c) for c in words[line * 512:(line + 1) * 512]]
            pixels += row
        image = Image.new('RGB', (544, 212))
        image.putdata(pixels)
        return image.resize((544, 424), Image.NEAREST)
    raise ValueError(f'{path.name}: {len(data)} bytes is not an MSX picture')


def contact_sheet(pictures: list[Path], target: Path) -> int:
    """Write the pictures as a grid; returns how many of them differ from each other."""
    from PIL import Image
    images = [picture(path) for path in pictures]
    if not images:
        return 0
    width, height = images[0].width, images[0].height
    rows = (len(images) + COLUMNS - 1) // COLUMNS
    sheet = Image.new('RGB', (COLUMNS * (width + 4), rows * (height + 4)), (32, 32, 32))
    for index, image in enumerate(images):
        sheet.paste(image, ((index % COLUMNS) * (width + 4) + 2, (index // COLUMNS) * (height + 4) + 2))
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return len({image.tobytes() for image in images})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path, help='the delivered game')
    parser.add_argument('report', type=Path, help='its conversion report')
    parser.add_argument('--pictures', type=int, default=12)
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'msx-route-captures')
    parser.add_argument('--routes', nargs='*', help='route names (default: all those of the report)')
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    out = args.out.resolve() / report['rom']['sha256'][:12]
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    for name, frames, script in plan(report):
        if args.routes and name not in args.routes:
            continue
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob('frame-*.bin'):
            old.unlink()
        inputs = folder / 'route.inputs'
        inputs.write_text(script, encoding='ascii', newline='\n')
        every = max(1, frames // max(1, args.pictures))
        done = subprocess.run([str(args.exe.resolve()), '--headless', '--frames', str(frames), '--script', str(inputs),
                               '--pictures', str(folder), '--picture-every', str(every), '--report', str(folder / 'report.json')],
                              cwd=folder, env=env, timeout=max(600, frames // 5), capture_output=True, creationflags=NO_WINDOW)
        if done.returncode:
            print(f'{name}: the game stopped ({done.returncode})')
            continue
        pictures = sorted(folder.glob('frame-*.bin'))
        distinct = contact_sheet(pictures, out / f'{name}.png')
        print(f'{name}: {len(pictures)} pictures, {distinct} distinct: {out / f"{name}.png"}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
