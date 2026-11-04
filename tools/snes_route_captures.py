"""Pictures from the end of each route of a converted Super Nintendo game (gate G9 evidence: did the route reach play?).

    python tools/snes_route_captures.py EXE [--out DIR] [--routes play long-1 ...] [--checkpoints 4]

The conversion's routes are not stored with the game: `tools/snes_cross_os.py` writes them again from the report beside the
executable (the same pseudo-random and authored routes, the same seeds), and this tool runs the delivered executable headless
(SDL dummy drivers, no window) with each route's input script, asking for the last frame as a picture. Chained routes continue
from the end state of the one before, as in the conversion. It reads the game and writes only under --out (default
`.build/snes-route-captures/<game>`): one PNG per route and a `captures.json` with the frames and the report's picture counters.
With `--checkpoints K` a route is also run to K - 1 earlier frames (its script cut there: the host refuses a script longer than
the run), for a route whose last frame is a fade or a black screen: one more PNG per checkpoint, `<route>-<frame>.png`.
A picture shows what the screen held at the end of a route; it does not say how far into the game the route is, and a person
(or a specialist agent) still has to look at it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
_SPEC = importlib.util.spec_from_file_location('snes_cross_os', Path(__file__).with_name('snes_cross_os.py'))
cross_os = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cross_os)


def ppm_to_png(source: Path, target: Path) -> None:
    """A binary PPM (P6) as a PNG, with the standard library only."""
    data = source.read_bytes()
    if data[:2] != b'P6':
        raise ValueError(f'{source.name} is not a P6 picture')
    fields, position = [], 2
    while len(fields) < 3:
        while data[position:position + 1].isspace():
            position += 1
        start = position
        while not data[position:position + 1].isspace():
            position += 1
        fields.append(int(data[start:position]))
    position += 1
    width, height, _ = fields
    pixels = data[position:position + width * height * 3]
    rows = b''.join(b'\x00' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    target.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
                       chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def capture(exe: Path, out: Path, only: list[str] | None, checkpoints: int = 1) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    summary = {'executable': exe.name, 'routes': {}}
    with tempfile.TemporaryDirectory(dir=out) as folder:
        folder = Path(folder)
        plan = cross_os.routes_of(exe, folder)
        game = folder / exe.name
        shutil.copy2(exe, game)
        game.chmod(0o755)
        for item in plan:
            name = item['name']
            if only and name not in only and not any(other['continues_from'] == name and other['name'] in only for other in plan):
                continue
            picture, report = folder / f'{name}.ppm', folder / f'{name}.json'
            command = [str(game), '--frames', str(item['frames']), '--report', str(report), '--frame-image', str(picture)]
            if item['script']:
                command += ['--input-script', str(item['script'])]
            if item['play']:
                command.append('--play')
            if item['continues_from']:
                command += ['--load-state', str(folder / f"{item['continues_from']}.state")]
            if item['save_state']:
                command += ['--save-state', str(folder / f'{name}.state')]
            done = subprocess.run(command, cwd=folder, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=NO_WINDOW, timeout=7200)
            if done.returncode or not picture.is_file():
                raise SystemExit(f'{name}: the game exited with {done.returncode}: {done.stdout[-300:]!r}')
            if (not only or name in only) and checkpoints > 1 and item['script'] and not item['continues_from']:
                lines = Path(item['script']).read_text(encoding='ascii').splitlines()
                for step in range(1, checkpoints):
                    frames = item['frames'] * step // checkpoints
                    cut = folder / f'{name}-{frames}.txt'
                    kept = [line for line in lines if not line.strip() or line.startswith('#') or int(line.split()[0]) <= frames]
                    cut.write_text('\n'.join(kept) + '\n', encoding='ascii')
                    early = folder / f'{name}-{frames}.ppm'
                    done = subprocess.run([str(game), '--frames', str(frames), '--report', str(folder / f'{name}-{frames}.json'),
                                           '--frame-image', str(early), '--input-script', str(cut), '--play'], cwd=folder,
                                          env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          creationflags=NO_WINDOW, timeout=7200)
                    if done.returncode or not early.is_file():
                        raise SystemExit(f'{name} at {frames}: the game exited with {done.returncode}')
                    ppm_to_png(early, out / f'{name}-{frames}.png')
            if not only or name in only:
                ppm_to_png(picture, out / f'{name}.png')
                data = json.loads(report.read_text(encoding='utf-8'))
                summary['routes'][name] = {'frames': item['frames'],
                                           **{key: data.get(key) for key in ('visible_frames', 'pcm_nonzero', 'frame_hash')}}
                print(f'{name}: {item["frames"]} frames -> {name}.png', flush=True)
    (out / 'captures.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8', newline='\n')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('exe', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--routes', nargs='*')
    parser.add_argument('--checkpoints', type=int, default=1)
    args = parser.parse_args()
    out = args.out or Path('.build/snes-route-captures') / args.exe.stem
    capture(args.exe.resolve(), out.resolve(), args.routes, args.checkpoints)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
