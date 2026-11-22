"""Which pads of the multitap does a converted PC Engine CD game read? (the evidence behind `pcecd.MULTITAP_PLAYERS`; needs the player's own game, never in the repository)

    python -B tools/pcecd_multitap_probe.py GAME.exe ROUTE.inputs [--frames 12000] [--from 2000] [--workers 2]

The converter builds every disc for two players unless a reviewed table says more (retrorecomp/pcecd.py, keyed by the disc, as the HuCards' `pce_build.MULTITAP_PLAYERS`).
A table entry needs evidence that the game reads the pads beyond the second, and this is it, measured the way the HuCard table's Bomberman '93 was: the game runs headless, with
the multitap plugged (every game is built with it), its own long route on pads 1 and 2, for `--frames` frames; once with the other pads idle (the control, run twice to show
it is deterministic) and once for each of pads 2, 3 and 4 pressed by a fixed pseudo-random pattern from frame `--from` on (Run pulses to join a game, then directions and buttons).
The engine answers a port with the pad of that port only while the game selects it, so a pad the game never reads cannot change anything: **a pad that changes the RAM, the CPU, the
picture or the sound hash of the run is a pad the game reads**; a pad that changes nothing is a pad the game did not read *in this route* (it may in another mode: the table
says only what was shown). It prints, for each pad, whether it changed each of the four hashes, and a verdict: the highest pad that changed something is the number of players
the route showed (pad 4 changed: four players, pad 3: three, pad 2: two).

It says nothing of the game's own rules (which players are human, a game's menu that has to ask the count), of a fifth player (the room seats four) or of speed. The runs are
independent processes (two at a time by default) and write only to the work folder (`.build/pcecd-multitap-probe`).
"""
from pathlib import Path
import argparse
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.build' / 'pcecd-multitap-probe'
RUN, I, II, UP, RIGHT, DOWN, LEFT = 0x008, 0x001, 0x002, 0x010, 0x020, 0x040, 0x080
HASHES = ('ram_hash', 'cpu_hash', 'image_hash', 'pcm_hash')


def route_rows(path: Path) -> list:
    rows = []
    for line in path.read_text(encoding='ascii').splitlines():
        line = line.split('#', 1)[0].split()
        if line:
            rows.append((int(line[0]), [int(word, 16) for word in line[1:]]))
    return rows


def pattern(pad: int, start: int, end: int) -> list:
    """(frame, word) changes for one extra pad: a Run pulse every 120 frames (a player joins), between them a held direction with I and II in bursts, fixed by the pad's number."""
    rng = random.Random(0x7A9 + pad)
    out = []
    frame = start
    while frame < end:
        if (frame - start) % 120 == 0:
            out += [(frame, RUN), (frame + 6, 0)]
        word = rng.choice((UP, RIGHT, DOWN, LEFT, UP | I, RIGHT | I, DOWN | II, LEFT | II, I, II))
        out += [(frame + 10, word), (frame + 14, word | I), (frame + 18, word), (frame + 28, 0)]
        frame += 30
    return [row for row in out if row[0] < end]


def script(route: list, extra: dict, frames: int) -> str:
    """The route's rows (pads 1 and 2) merged with the extra pads' changes: every change point holds the four words at that frame."""
    points = {frame for frame, _ in route} | {frame for rows in extra.values() for frame, _ in rows}
    held = {slot: 0 for slot in range(4)}
    route_at = dict(route)
    extra_at = {slot: dict(rows) for slot, rows in extra.items()}
    lines = []
    for frame in sorted(points):
        if frame >= frames:
            break
        if frame in route_at:
            words = route_at[frame] + [0] * (2 - len(route_at[frame]))
            held[0] = words[0]
            if 1 not in extra:              # the route's pad 2 stands unless pad 2 is the one under test
                held[1] = words[1]
        for slot, rows in extra_at.items():
            if frame in rows:
                held[slot] = rows[frame]
        lines.append(f'{frame} {held[0]:x} {held[1]:x} {held[2]:x} {held[3]:x}')
    return '\n'.join(lines) + '\n'


def run(exe: Path, name: str, text: str, frames: int) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    path, report = WORK / f'{name}.inputs', WORK / f'{name}.json'
    path.write_text(text, encoding='ascii', newline='\n')
    done = subprocess.run([str(exe), '--headless', '--frames', str(frames), '--script', str(path), '--report', str(report)], capture_output=True, text=True,
                          timeout=3600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if done.returncode:
        raise SystemExit(f'{name}: exit {done.returncode}: {done.stderr[-300:]}')
    data = json.loads(report.read_text(encoding='utf-8'))
    return {key: data[key] for key in HASHES} | {'fault': data.get('fault', '')}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('game', type=Path)
    parser.add_argument('route', type=Path)
    parser.add_argument('--frames', type=int, default=12000)
    parser.add_argument('--from', dest='start', type=int, default=2000)
    parser.add_argument('--workers', type=int, default=2)
    arguments = parser.parse_args()
    route = route_rows(arguments.route)
    jobs = {'control-a': {}, 'control-b': {}}
    for pad in (1, 2, 3):                       # slots of pads 2, 3 and 4
        jobs[f'pad{pad + 1}'] = {pad: pattern(pad, arguments.start, arguments.frames)}
    with ThreadPoolExecutor(max_workers=max(1, arguments.workers)) as pool:
        futures = {name: pool.submit(run, arguments.game, name, script(route, extra, arguments.frames), arguments.frames) for name, extra in jobs.items()}
        results = {name: future.result() for name, future in futures.items()}
    control = results['control-a']
    print(f'control run twice: {"identical" if results["control-b"] == control else "DIFFERENT (the probe is not deterministic: nothing below counts)"}; fault: {control["fault"] or "none"}')
    highest = 1
    for pad in (2, 3, 4):
        changed = [key for key in HASHES if results[f'pad{pad}'][key] != control[key]]
        print(f'pad {pad}: ' + (f'changes {", ".join(changed)}' if changed else 'changes nothing'))
        if changed:
            highest = pad
    print(f'verdict: the route showed the game reading {highest} pad(s) (only what this route reached; the table keeps what is shown)')
    return 0 if results['control-b'] == control else 1


if __name__ == '__main__':
    sys.exit(main())
