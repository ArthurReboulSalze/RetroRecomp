"""CPU time per frame of a PC Engine CD game on a stretch that falls back to the interpreter (headless; needs a quiet PC).

    python -B tools/pcecd_fallback_cost.py GAME.exe LONG_ROUTE.inputs [--extra 6000] [--repeats 5] [--core 4]

A converted disc is native only where its routes ran; the code a player reaches later runs on the engine's interpreter, counted. This measures what that costs in a
window before the owner feels it: the same script is played for the frames of the route (covered: native) and for `--extra` more frames of the same walk, past
the route (uncovered: mostly interpreted), and the time of the longer run minus the time of the shorter one, over the extra frames, is the cost of a frame there.
The two runs share their first frames exactly (the walk is deterministic), so start-up, the System Card's boot and the route cancel in the difference.

The script is the game's own long route (`checks/inputs/long-1.inputs` of its conversion) continued by the same generator: this tool rebuilds the walk for the longer
length from the route's seed, so `LONG_ROUTE.inputs` only gives the frame count, the seed is read from its name. For a route that was played with another style
(pcecd_routes), pass `--style`. Runs are interleaved (short, long, short, long...), the child is pinned to one core and its priority raised, and the figure is the
median over the repeats with its spread. Per run it also prints the native and interpreted instructions the report counts.

It measures the host's CPU time of the emulation (no window, no video scaling, no sound device): a frame budget is 16.67 ms at 60 Hz, and the window adds its own
cost. Nothing here says the games are smooth; it says how much of the budget the interpreter takes. Timing needs a quiet PC: stop every other job first.
"""
from pathlib import Path
import argparse
import json
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def pin(process: subprocess.Popen, core: int) -> None:
    """One core and a raised priority for the child (Windows); elsewhere the OS decides."""
    if sys.platform != 'win32':
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.SetProcessAffinityMask(ctypes.c_void_p(int(process._handle)), 1 << core)
    kernel.SetPriorityClass(ctypes.c_void_p(int(process._handle)), 0x00000080)       # HIGH_PRIORITY_CLASS


def run(game: Path, script: Path, frames: int, core: int, folder: Path, name: str) -> tuple[float, dict]:
    report = folder / (name + '.json')
    command = [str(game), '--headless', '--frames', str(frames), '--script', str(script), '--report', str(report)]
    start = time.perf_counter()
    child = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    pin(child, core)
    _, err = child.communicate()
    elapsed = time.perf_counter() - start
    if child.returncode:
        raise SystemExit(f'{name}: exit {child.returncode}: {err.decode(errors="replace")[-300:]}')
    return elapsed, json.loads(report.read_text(encoding='utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('game', type=Path)
    parser.add_argument('route', type=Path)
    parser.add_argument('--extra', type=int, default=6000)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--core', type=int, default=4)
    parser.add_argument('--style', default='walk')
    parser.add_argument('--presses', type=int, default=3)
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--seed', type=lambda text: int(text, 0), help='the route seed (default: the one of the game\'s disc is not known here: give it)')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'pcecd-fallback-cost')
    arguments = parser.parse_args()
    from retrorecomp import pcecd_routes
    if arguments.seed is None:
        raise SystemExit('give --seed: the route seed (pce_conversion.route_seed(game sha256, "long-1"))')
    short = max(int(line.split()[0]) for line in arguments.route.read_text(encoding='ascii').splitlines() if line.strip()) + 600
    short = min(18000, short)
    longer = short + arguments.extra
    arguments.work.mkdir(parents=True, exist_ok=True)
    script = arguments.work / 'long.inputs'
    script.write_text(pcecd_routes.script(arguments.style, longer, arguments.seed, arguments.presses, arguments.confirm), encoding='ascii', newline='\n')
    covered, stretch, native, interpreted = [], [], [], []
    for repeat in range(arguments.repeats):
        a, ra = run(arguments.game, script, short, arguments.core, arguments.work, f'short-{repeat}')
        b, rb = run(arguments.game, script, longer, arguments.core, arguments.work, f'long-{repeat}')
        covered.append(1000 * a / short)
        stretch.append(1000 * (b - a) / arguments.extra)
        native.append((rb['native_instructions'] - ra['native_instructions']) / arguments.extra)
        interpreted.append((rb['interpreted_instructions'] - ra['interpreted_instructions']) / arguments.extra)
        print(f'repeat {repeat + 1}: route {covered[-1]:.3f} ms/frame; past the route {stretch[-1]:.3f} ms/frame '
              f'({native[-1]:,.0f} native and {interpreted[-1]:,.0f} interpreted instructions per frame)', flush=True)
    def figure(values):
        return f'{statistics.median(values):.3f} ms (spread {100 * (max(values) - min(values)) / statistics.median(values):.1f} %)'
    print(f'\nthe route ({short} frames, native): {figure(covered)} per frame')
    print(f'{arguments.extra} frames past the route: {figure(stretch)} per frame, {statistics.median(interpreted):,.0f} interpreted and {statistics.median(native):,.0f} '
          f'native instructions per frame; the budget of a 60 Hz frame is 16.67 ms')
    return 0


if __name__ == '__main__':
    sys.exit(main())
