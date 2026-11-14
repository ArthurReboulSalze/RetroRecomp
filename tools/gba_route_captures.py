"""Pictures along a route of a converted Game Boy Advance player (gate G9): the evidence that a route reaches play, to be READ.

    python -B tools/gba_route_captures.py --exe GAME.exe --keys tools/gba_routes/ROUTE.keys --frames N [--shots 12] [--work DIR]

The delivered player is copied (never run in place), run hidden and silent once on the route with the test switch `RETRORECOMP_GBA_SHOTS` (a list of frames) and
`RETRORECOMP_GBA_SHOT_DIR`: it writes the picture of each chosen frame. The tool makes a contact sheet (`contact-sheet.png`, the shots in order, left to right, top to
bottom, the frame number of each in the report) and a report with the hash of every picture, how many are different and how many instructions the interpreter ran.
It does not say what the pictures show: somebody reads the sheet and writes it down (the specialist's reading goes in the qualification entry, never in the report).
A sheet whose pictures are all alike, or a route that ends before its last shot, is reported (`verdict`), not hidden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gba_fresh_process as base  # noqa: E402

DEFAULT_WORK = base.ROOT / '.build' / 'gba-route-captures'
COLUMNS = 4


def shot_frames(frames: int, count: int) -> list[int]:
    """`count` frames spread over the route, the last one the last frame the player runs (the player counts frames from 1)."""
    if frames < 1 or count < 1:
        raise base.CheckError('--frames and --shots must be positive')
    count = min(count, frames)
    return sorted({max(1, round(frames * (index + 1) / count)) for index in range(count)})


def contact_sheet(pictures: list[Path], columns: int = COLUMNS) -> tuple[int, int, bytes]:
    """The pictures side by side in rows of `columns`: (width, height, RGB bytes)."""
    sizes = [base.ppm_pixels(path)[:2] for path in pictures]
    width, height = sizes[0]
    if any(size != (width, height) for size in sizes):
        raise base.CheckError('the pictures of a route have different sizes')
    rows = (len(pictures) + columns - 1) // columns
    sheet = bytearray(b'\x00' * (width * columns * height * rows * 3))
    for index, path in enumerate(pictures):
        pixels = base.ppm_pixels(path)[2]
        left, top = (index % columns) * width, (index // columns) * height
        for y in range(height):
            start = ((top + y) * width * columns + left) * 3
            sheet[start:start + width * 3] = pixels[y * width * 3:(y + 1) * width * 3]
    return width * columns, height * rows, bytes(sheet)


def run_captures(exe: Path, work: Path, keys: Path, frames: int, shots: int, timeout: int) -> dict:
    events = base.read_key_script(keys)
    frames_list = shot_frames(frames, shots)
    folder = work / 'captures'
    game = base.prepare_folder(exe, folder)
    shots_dir = folder / 'shots'
    shots_dir.mkdir()
    run = base.run_player(game, folder, 'route', frames, keys, '', timeout,
                          extra={'RETRORECOMP_GBA_SHOTS': ','.join(str(frame) for frame in frames_list), 'RETRORECOMP_GBA_SHOT_DIR': str(shots_dir)})
    pictures = [shots_dir / f'shot-{frame}.ppm' for frame in frames_list]
    missing = [frame for frame, path in zip(frames_list, pictures) if not path.is_file()]
    problems = []
    if run.returncode != 0:
        problems.append(f'the player ended with code {run.returncode}')
    if run.frames != frames:
        problems.append(f'the player ended at frame {run.frames} of {frames}')
    if missing:
        problems.append(f'no picture at frames {missing}')
    hashes = [base.picture_sha256(path) for path in pictures if path.is_file()]
    if hashes and len(set(hashes)) < max(2, len(hashes) // 3):
        problems.append('most of the pictures are alike: the route may stand still')
    sheet = None
    if not missing and pictures:
        width, height, rgb = contact_sheet(pictures)
        sheet = folder / 'contact-sheet.png'
        base.write_png(sheet, width, height, rgb, scale=1)
    verdict = {'verdict': 'error' if problems else 'pass', 'frames': run.frames, 'interpreted_instructions': run.interpreted,
               'shots': [{'frame': frame, 'sha256': digest} for frame, digest in zip(frames_list, hashes)], 'different_pictures': len(set(hashes)),
               'contact_sheet': str(sheet) if sheet else None, 'read_by': None, 'problems': problems}
    return base.build_report('captures', exe, {'route': run}, verdict,
                             {'keys': keys.name, 'keys_sha256': hashlib.sha256(keys.read_bytes()).hexdigest(), 'frames': frames, 'shots': frames_list,
                              'script_events': len(events)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--exe', type=Path, required=True, help='the converted player (copied, never run in place)')
    parser.add_argument('--keys', type=Path, required=True)
    parser.add_argument('--frames', type=int, required=True)
    parser.add_argument('--shots', type=int, default=12)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.exe.is_file():
            raise base.CheckError(f'{args.exe} is not a file')
        args.work.mkdir(parents=True, exist_ok=True)
        report = run_captures(args.exe.resolve(), args.work.resolve(), args.keys, args.frames, args.shots, args.timeout)
    except (base.CheckError, ValueError) as error:
        print(f'gba_route_captures: {error}', file=sys.stderr)
        return 2
    target = args.json or args.work / 'report-captures.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(base.render_text(report))
    print(f'report: {target}')
    return {'pass': 0}.get(report['result']['verdict'], 2)


if __name__ == '__main__':
    sys.exit(main())
