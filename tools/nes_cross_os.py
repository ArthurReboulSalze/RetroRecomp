"""NES: one game built on two systems, frame by frame (gate G13, the cross-OS witness).

    python tools/nes_cross_os.py trace ROM EXE --out DIR [--level thorough]
    python tools/nes_cross_os.py compare DIR_A DIR_B

`trace` writes the routes of the game from the ROM (the ones a conversion at that scan level plays), runs the delivered
executable on each of them headless from a cold start and keeps, for every route, the per-frame trace (program counter and
registers, work memory, mapper and PPU state, picture and sound hashes) and the SHA-256 of the sound it produced, in DIR with a
`summary.json`. Run it once on Windows and once on Debian, each on the game that system's converter built from the same
source; `compare` then says, route by route, whether the two traces are identical and, if not, the first frame and the
columns that differ. The ROM is only read; the executable runs from a private copy so no save is left beside it.
Only hashes and counters are kept: no ROM byte and no picture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def sha256(path: Path) -> str:
    """The SHA-256 of a text file as if it had Unix line ends: Windows writes the traces and the input scripts with CR LF."""
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def trace_command(args) -> int:
    from nes_route_captures import routes
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scripts = out / 'scripts'
    scripts.mkdir(exist_ok=True)
    plan = routes(args.rom, args.level, scripts)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    summary = {'schema': 1, 'system': sys.platform, 'level': args.level, 'executable': args.exe.name, 'routes': {}}
    with tempfile.TemporaryDirectory(dir=out) as scratch:
        game = Path(scratch) / ('game.exe' if os.name == 'nt' else 'game')
        shutil.copy2(args.exe, game)
        game.chmod(0o755)
        for name, (script, frames) in plan.items():
            trace, sound = out / f'{name}.hash', Path(scratch) / f'{name}.wav'
            trace.unlink(missing_ok=True)
            command = [str(game), '--frames', str(frames), '--hash-out', str(trace), '--wav-out', str(sound)]
            if script:
                command += ['--input', str(script)]
            done = subprocess.run(command, cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=NO_WINDOW, timeout=3600)
            if done.returncode or not trace.is_file():
                raise SystemExit(f'{name}: the game exited with {done.returncode}: {done.stdout[-400:]!r}')
            with wave.open(str(sound), 'rb') as stream:
                pcm = hashlib.sha256(stream.readframes(stream.getnframes())).hexdigest()
            sound.unlink()
            lines = trace.read_text(encoding='utf-8').splitlines()
            summary['routes'][name] = {'frames': frames, 'lines': len(lines), 'trace_sha256': sha256(trace),
                                       'pcm_sha256': pcm, 'script_sha256': sha256(script) if script else None,
                                       'last': lines[-1] if lines else None}
            print(f'{name}: {frames} frames, trace {summary["routes"][name]["trace_sha256"][:16]}', flush=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8', newline='\n')
    return 0


def columns(line: str) -> dict[str, str]:
    return dict(item.split('=', 1) for item in line.split()[1:] if '=' in item)


def compare_command(args) -> int:
    first, second = (json.loads((folder / 'summary.json').read_text(encoding='utf-8')) for folder in (args.a, args.b))
    for summary, folder in ((first, args.a), (second, args.b)):   # the files are read again: a summary made before the line-end rule is out of date
        for name, route in summary['routes'].items():
            route['trace_sha256'] = sha256(folder / f'{name}.hash')
            script = folder / 'scripts' / f'{name.replace("_", "-")}.input'
            route['script_sha256'] = sha256(script) if script.is_file() else route['script_sha256']
    status = 0
    print(f'A: {first["system"]} {first["executable"]}   B: {second["system"]} {second["executable"]}   level {first["level"]}/{second["level"]}')
    for name in sorted(set(first['routes']) | set(second['routes'])):
        one, two = first['routes'].get(name), second['routes'].get(name)
        if not one or not two:
            print(f'{name}: on one side only, not compared')
            continue
        if one['script_sha256'] != two['script_sha256']:
            print(f'{name}: the input scripts differ (not comparable)')
            status = 1
            continue
        verdict = 'same' if one['trace_sha256'] == two['trace_sha256'] and one['pcm_sha256'] == two['pcm_sha256'] else 'DIFFERENT'
        print(f'{name}: {one["frames"]} frames: trace {"=" if one["trace_sha256"] == two["trace_sha256"] else "!="}, '
              f'sound {"=" if one["pcm_sha256"] == two["pcm_sha256"] else "!="}  {verdict}')
        if verdict == 'DIFFERENT':
            status = 1
            rows_a = (args.a / f'{name}.hash').read_text(encoding='utf-8').splitlines()
            rows_b = (args.b / f'{name}.hash').read_text(encoding='utf-8').splitlines()
            for index, (left, right) in enumerate(zip(rows_a, rows_b)):
                if left != right:
                    cols_a, cols_b = columns(left), columns(right)
                    print(f'    first difference at frame {index}: ' + ', '.join(
                        f'{key} ({cols_a.get(key)} / {cols_b.get(key)})' for key in cols_a if cols_a[key] != cols_b.get(key)))
                    break
            else:
                print(f'    the traces agree on {min(len(rows_a), len(rows_b))} frames but have {len(rows_a)} and {len(rows_b)} lines')
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    trace = sub.add_parser('trace', help='replay the routes on an executable and keep the per-frame traces')
    trace.add_argument('rom', type=Path)
    trace.add_argument('exe', type=Path)
    trace.add_argument('--out', type=Path, required=True)
    trace.add_argument('--level', default='thorough')
    trace.set_defaults(run=trace_command)
    compare = sub.add_parser('compare', help='compare two trace folders route by route')
    compare.add_argument('a', type=Path)
    compare.add_argument('b', type=Path)
    compare.set_defaults(run=compare_command)
    args = parser.parse_args()
    return args.run(args)


if __name__ == '__main__':
    raise SystemExit(main())
