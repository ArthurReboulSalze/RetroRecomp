"""Pictures from the end of each route of a converted NES game (gate G9 evidence: did the route reach play?).

    python tools/nes_route_captures.py ROM EXE [--level thorough] [--out DIR] [--routes play_right long_1 ...]

The conversion's routes are not stored with the game: they are written from the ROM by `nes._write_probe_scripts` and
`random_routes`, so this tool writes them again, the same way and at the same scan level, and runs the delivered executable
(headless, SDL dummy drivers, no window) with each route's input script, asking for the last frame as a PNG.
It reads the ROM and the game and writes only under --out (default `.build/nes-route-captures`). A picture
shows what the screen held at the end of a route; it does not say how far into the game the route is, and a person (or a
specialist agent) still has to look at it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def routes(rom_path: Path, level: str, folder: Path) -> dict[str, tuple[Path | None, int]]:
    """{route name: (input script, frames)} as a conversion at `level` plays them."""
    from retrorecomp import nes
    from retrorecomp.random_routes import long_routes as pseudo_random_routes
    from retrorecomp.scan_levels import nes_budget
    rom = nes.read_nes_rom(rom_path)
    scan = nes_budget(level)
    long_routes = ()
    if scan['route_count']:
        long_routes = pseudo_random_routes('nes', rom.sha256, count=scan['route_count'], frames=scan['route_frames'])
    scripts = nes._write_probe_scripts(folder, 3600, advanced=scan['advanced'], play_left=scan['play_left'],
                                       long_routes=long_routes)
    budgets = nes._scenario_frames(scripts, 3600, long_routes)
    return {name: (script, budgets[name]) for name, script in scripts.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('rom', type=Path)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--level', default='thorough')
    parser.add_argument('--out', type=Path, default=ROOT / '.build' / 'nes-route-captures')
    parser.add_argument('--routes', nargs='*', help='route names (default: all of the level)')
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.exe = args.exe.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    scripts_folder = args.out / 'scripts'
    scripts_folder.mkdir(exist_ok=True)
    plan = routes(args.rom, args.level, scripts_folder)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    for name, (script, frames) in plan.items():
        if args.routes and name not in args.routes:
            continue
        target = args.out / f'{name}.png'
        command = [str(args.exe), '--frames', str(frames), '--screenshot', str(target), '--shot-every', str(frames - 1)]
        if script:
            command += ['--input', str(script)]
        # The player keeps its battery file beside the executable: run a private copy of the folder's executable.
        done = subprocess.run(command, cwd=args.out, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              creationflags=NO_WINDOW, timeout=1200)
        if done.returncode:
            raise SystemExit(f'{name}: the game exited with {done.returncode}: {done.stdout[-400:]!r}')
        last = args.out / f'{name}_{frames - 1:05d}.png'
        print(f'{name}: {frames} frames -> {last.name if last.exists() else "(no picture)"}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
