"""Compare a converted X68000 game with MAME 0.289 on the pictures that stand still (development check, nothing here is shipped).

    python -B tools/x68000_mame_compare.py GAME.exe DISK.dim --mame MAME.exe --ipl iplrom.dat --cgrom cgrom.dat
                                           [--mame-frames 4500] [--game-frames 4600] [--min-run 15] [--work DIR]

Both sides boot the same first disk and receive no input. MAME runs its `x68000` driver (BIOS `ipl10`, the IPL and font ROM this
tool is given) headless with a Lua script that saves the raw screen every 10 frames. The delivered game replays headless with
`--trace`; its trace gives a picture hash per frame, so the game is captured once for each run of at least `--min-run` frames that
stands still (`--capture` keeps the last frame of a run of N frames, hence one run per capture). Every picture of MAME that stands
still (identical in three captures or more) is then looked up among those of the game.

What a match is: the two pictures have the same shape up to a one-to-one change of colours, after cutting each to the box of its
non-black pixels (the two emulators place the same picture differently in their frames, and MAME shows a 256-line mode on 512
rows, of which the even rows are the picture). Colours are NOT compared by this tool (the match is up to a one-to-one change of colours;
the game's colour word reaches the picture as MAME's does for the intensity bit since 1.6.7, but the screen contrast of the system port is
applied by the base to the palette and by MAME at display, after the raw screen this tool reads). Sound is not compared, nor is anything that moves. The match says the two machines draw the same layers in the same places at the same moments
of a boot; it says nothing of hardware fidelity (MAME is not hardware, and its x68000 driver is marked imperfect), of gameplay or of
timing: a disk loads more slowly in MAME, so the pictures come at different frames, and the lag is reported, not corrected.

MAME must be a local copy you obtained yourself and the firmware is yours: both stay outside the repository, and the copy of the
firmware this tool makes under --work is deleted when it ends. A picture of MAME that has no match is reported with its frames.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MAME_STEP = 10
MIN_MAME_RUN = 20       # frames: three captures of the same picture

LUA = '''local out = "%(out)s"
local step = %(step)d
local last = %(last)d
local screen = manager.machine.screens[":screen"]
local manifest = io.open(out .. "/manifest.tsv", "w")
manifest:write("frame\\twidth\\theight\\n")
subscription = emu.add_machine_frame_notifier(function()
  local f = screen:frame_number()
  if f %% step == 0 then
    local px, w, h = screen:pixels()
    local fh = io.open(out .. string.format("/%%06d.raw", f), "wb")
    fh:write(px)
    fh:close()
    manifest:write(string.format("%%d\\t%%d\\t%%d\\n", f, w, h))
    manifest:flush()
  end
  if f >= last then
    manifest:close()
    manager.machine:exit()
  end
end)
'''


def canonical(image) -> tuple[str, int]:
    """(hash, colours) of the picture's shape: each pixel is replaced by the order in which its colour first appeared."""
    data = image.tobytes()
    labels: dict[bytes, int] = {}
    out = bytearray()
    for index in range(0, len(data), 3):
        colour = data[index:index + 3]
        label = labels.get(colour)
        if label is None:
            label = labels[colour] = len(labels)
        out += label.to_bytes(2, 'little')
    return hashlib.sha1(bytes(out) + image.width.to_bytes(4, 'little')).hexdigest(), len(labels)


def content(image):
    """The picture cut to the box of its non-black pixels (a 1x1 black picture when there is none)."""
    import numpy
    from PIL import Image
    mask = numpy.asarray(image).any(axis=2)
    if not mask.any():
        return Image.new('RGB', (1, 1))
    rows, columns = numpy.nonzero(mask.any(axis=1))[0], numpy.nonzero(mask.any(axis=0))[0]
    return image.crop((int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1))


def shape_key(image) -> str:
    return canonical(content(image))[0]


def even_rows(image):
    """The even rows of a picture MAME shows on twice as many rows as the machine draws."""
    from PIL import Image
    rows, width = image.tobytes(), image.width
    return Image.frombytes('RGB', (width, image.height // 2), b''.join(
        rows[row * width * 3:(row + 1) * width * 3] for row in range(0, image.height - 1, 2)))


def variants(image) -> dict:
    result = {'as-is': image}
    if image.height >= 2 and image.height % 2 == 0:
        result['even-rows'] = even_rows(image)
    return result


def still_runs(rows, minimum: int) -> list[tuple[int, int, str]]:
    """(first frame, last frame, picture hash) of every run of at least `minimum` frames with the same picture, from trace rows
    (frame, picture hash, width); frames before the first picture (width 0) are not pictures."""
    runs: list[list] = []
    for frame, digest, width in rows:
        if runs and runs[-1][2] == digest:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame, digest, width])
    return [(first, last, digest) for first, last, digest, width in runs if last - first + 1 >= minimum and width]


def mame_runs(captures: list[tuple[int, str]], minimum: int = MIN_MAME_RUN) -> list[tuple[int, int, str]]:
    """(first, last, digest) of the runs of at least `minimum` frames over (frame, raw digest) captures that did not change."""
    runs: list[list] = []
    for frame, digest in captures:
        if runs and runs[-1][2] == digest:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame, digest])
    return [(first, last, digest) for first, last, digest in runs if last - first >= minimum]


def match_runs(mame_pictures: list[tuple[int, int, object]], game_index: dict[str, list[tuple[int, int]]]) -> list[dict]:
    """For each (first, last, image) still picture of MAME: the runs of the game with the same shape, and which line variant."""
    results = []
    for first, last, image in mame_pictures:
        found = None
        for label, candidate in variants(image).items():
            key = shape_key(candidate)
            if game_index.get(key):
                found = {'variant': label, 'game_runs': game_index[key]}
                break
        results.append({'mame_first': first, 'mame_last': last, **(found or {'variant': None, 'game_runs': None})})
    return results


def summarize(results: list[dict], game_still: int, mame_frames: int, game_frames: int) -> dict:
    matched = [r for r in results if r['game_runs']]
    return {'mame_frames': mame_frames, 'game_frames': game_frames, 'game_still_pictures': game_still,
            'mame_still_pictures': len(results), 'matched': len(matched),
            'unmatched_mame_runs': [[r['mame_first'], r['mame_last']] for r in results if not r['game_runs']]}


def run_mame(mame: Path, ipl: Path, cgrom: Path, disk: Path, frames: int, work: Path) -> Path:
    out = work / 'mame'
    out.mkdir(parents=True, exist_ok=True)
    roms = work / 'roms' / 'x68000'
    roms.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ipl, roms / 'iplrom.dat')
    shutil.copyfile(cgrom, roms / 'cgrom.dat')
    lua = work / 'capture.lua'
    lua.write_text(LUA % {'out': out.as_posix(), 'step': MAME_STEP, 'last': frames}, encoding='utf-8')
    try:
        # MAME runs from its own folder, so every path is absolute.
        result = subprocess.run([str(mame), 'x68000', '-rompath', str((work / 'roms').resolve()), '-bios', 'ipl10', '-flop1',
                                 str(disk.resolve()), '-video', 'none', '-sound', 'none', '-nothrottle', '-skip_gameinfo', '-nomouse',
                                 '-seconds_to_run', str(frames // 50 + 600), '-autoboot_script', str(lua.resolve()),
                                 '-cfg_directory', str((work / 'cfg').resolve()), '-nvram_directory', str((work / 'nvram').resolve())],
                                capture_output=True, text=True, timeout=3600, cwd=mame.resolve().parent, creationflags=NO_WINDOW)
    finally:
        shutil.rmtree(work / 'roms', ignore_errors=True)    # the player's firmware is not kept
    if result.returncode or not (out / 'manifest.tsv').is_file():
        raise SystemExit('MAME failed: ' + (result.stdout + result.stderr)[-600:])
    return out


def run_game(exe: Path, frames: int, folder: Path, *, trace: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    picture = folder / f'f{frames}.ppm'
    args = [str(exe), '--headless', '--frames', str(frames)]
    args += ['--trace', str(folder / 'trace.tsv')] if trace else ['--capture', str(picture)]
    subprocess.run(args, check=True, capture_output=True, timeout=3600, creationflags=NO_WINDOW,
                   env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'))
    return picture


def trace_rows(path: Path) -> list[tuple[int, str, int]]:
    rows = list(csv.reader(path.open(encoding='utf-8'), delimiter='\t'))
    video, width = rows[0].index('video'), rows[0].index('width')
    return [(int(row[0]), row[video], int(row[width])) for row in rows[1:]]


def compare(exe: Path, disk: Path, mame: Path, ipl: Path, cgrom: Path, mame_frames: int, game_frames: int, min_run: int, work: Path) -> dict:
    from PIL import Image
    out = run_mame(mame, ipl, cgrom, disk, mame_frames, work)
    manifest = [line.split('\t') for line in (out / 'manifest.tsv').read_text(encoding='utf-8').splitlines()[1:]]
    ours = work / 'game'
    run_game(exe, game_frames, ours, trace=True)
    index: dict[str, list[tuple[int, int]]] = {}
    for first, last, _ in still_runs(trace_rows(ours / 'trace.tsv'), min_run):
        picture = run_game(exe, (first + last) // 2, ours)
        index.setdefault(shape_key(Image.open(picture).convert('RGB')), []).append((first, last))
    sizes = {int(frame): (int(width), int(height)) for frame, width, height in manifest}
    digests = [(frame, hashlib.sha1((out / f'{frame:06d}.raw').read_bytes()).hexdigest()) for frame in sorted(sizes)]
    pictures = []
    for first, last, _ in mame_runs(digests):
        width, height = sizes[first]
        raw = (out / f'{first:06d}.raw').read_bytes()
        pictures.append((first, last, Image.frombuffer('RGBA', (width, height), raw, 'raw', 'BGRA', 0, 1).convert('RGB')))
    results = match_runs(pictures, index)
    return {**summarize(results, sum(len(v) for v in index.values()), mame_frames, game_frames), 'results': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('exe', type=Path)
    parser.add_argument('disk', type=Path, help='the first disk of the game (a .dim, .xdf or .d88 file)')
    parser.add_argument('--mame', type=Path, default=os.environ.get('RETRO_RECOMP_MAME'), help='mame.exe of MAME 0.289')
    parser.add_argument('--ipl', type=Path, required=True)
    parser.add_argument('--cgrom', type=Path, required=True)
    parser.add_argument('--mame-frames', type=int, default=4500)
    parser.add_argument('--game-frames', type=int, default=4600)
    parser.add_argument('--min-run', type=int, default=15, help='frames a picture of the game stands still to be captured')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'x68000-mame-compare')
    options = parser.parse_args()
    if not options.mame:
        parser.error('--mame (or RETRO_RECOMP_MAME) is required')
    options.work.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=options.work))
    summary = compare(options.exe, options.disk, options.mame, options.ipl, options.cgrom, options.mame_frames, options.game_frames,
                      options.min_run, work)
    (work / 'report.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'results'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
