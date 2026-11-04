"""Compare a converted Mega Drive game with MAME 0.289 on its first seconds (development check, nothing here is shipped).

    python -B tools/megadrive_mame_compare.py GAME.exe ROM.zip --mame MAME.exe [--mame-frames 3000] [--game-frames 3100]
                                              [--min-run 15] [--work DIR]

Both sides start the same cartridge from power on and receive no input. MAME runs its `genesis` driver (NTSC, USA; no firmware is
needed) headless with a Lua script that saves the raw screen every 10 frames. The delivered game
replays headless with `--trace`; its trace gives a picture hash per frame, so the game is captured once for each run of at least
`--min-run` frames that stands still (`--frames N --frame-image FILE` keeps the picture of frame N). Every picture of MAME that stands
still (identical in three captures or more) is then looked up among those of the game.

Two measures per picture of MAME, both about the picture only (a picture that is black on both sides counts as a match):
  * `shape`: the two pictures have the same shape up to a one-to-one change of colours, after cutting each to the box of its
    non-black pixels (the two emulators may place a picture differently in their frames);
  * `identical`: the share of pixels that have the very same colour in the best placement of the same-shape picture.
Sound is NOT compared: the delivered executable has no option that writes its sound to a file yet (the plan in
docs/QUALIFICATION.md names the smallest change).

What this says: agreement of the game's pictures and sound level with MAME 0.289's, on the pictures that stand still in the boot and
the attract sequence. It does not say anything of the original hardware (MAME is not hardware), of gameplay, of timing (the two
sides may be offset by a few frames, which the tool reports and does not correct) or of anything that moves. MAME must be a local
copy you obtained yourself; nothing of it, and no ROM, enters this repository: the ROM is read in place, and the copy the tool makes
under --work to give MAME a file is deleted when it ends.
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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MAME_STEP = 10
MIN_MAME_RUN = 20       # frames: three captures of the same picture
ROM_SUFFIXES = ('.md', '.bin', '.gen', '.smd')

LUA = '''local out = "%(out)s"
local step = %(step)d
local last = %(last)d
local screen = nil
for _, candidate in pairs(manager.machine.screens) do screen = candidate break end
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


def cartridge(rom: Path, folder: Path) -> Path:
    """A plain ROM file for MAME: the cartridge inside a zip, or the file itself."""
    if rom.suffix.lower() != '.zip':
        return rom
    with zipfile.ZipFile(rom) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(ROM_SUFFIXES)]
        if len(names) != 1:
            raise SystemExit(f'{rom.name}: expected one cartridge file, found {names}')
        target = folder / ('cartridge' + Path(names[0]).suffix.lower())
        target.write_bytes(archive.read(names[0]))
    return target


def mame_runs(captures: list[tuple[int, str]], minimum: int = MIN_MAME_RUN) -> list[tuple[int, int, str]]:
    """(first, last, digest) of the runs of at least `minimum` frames over (frame, raw digest) captures that did not change."""
    runs: list[list] = []
    for frame, digest in captures:
        if runs and runs[-1][2] == digest:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame, digest])
    return [(first, last, digest) for first, last, digest in runs if last - first >= minimum]


def still_runs(rows: list[tuple[int, str]], minimum: int) -> list[tuple[int, int, str]]:
    """(first, last, hash) of the runs of at least `minimum` frames with the same picture hash."""
    runs: list[list] = []
    for frame, digest in rows:
        if runs and runs[-1][2] == digest:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame, digest])
    return [(first, last, digest) for first, last, digest in runs if last - first + 1 >= minimum]


def box(image):
    """The picture cut to the box of its non-black pixels (None for a black picture)."""
    from PIL import Image
    rgb = image.convert('RGB')
    area = rgb.convert('L').point(lambda value: 255 if value else 0).getbbox()
    return rgb.crop(area) if area else None


def shape_key(image) -> str | None:
    """The picture after a one-to-one renaming of its colours (numbered in order of first appearance), as a digest; 'black' for
    a picture with no pixel that is not black."""
    cut = box(image)
    if cut is None:
        return 'black'
    names: dict[tuple, int] = {}
    data = bytearray()
    for pixel in cut.getdata():
        data.append(names.setdefault(pixel, len(names)) & 0xff)
        if len(names) > 255:
            return None
    return hashlib.sha1(f'{cut.size}'.encode() + bytes(data)).hexdigest()


def identical_share(a, b) -> float:
    """The share of pixels that have the same colour, for two pictures of the same size after cutting."""
    first, second = box(a), box(b)
    if first is None and second is None:
        return 1.0
    if first is None or second is None or first.size != second.size:
        return 0.0
    same = sum(1 for p, q in zip(first.getdata(), second.getdata()) if p == q)
    return same / (first.size[0] * first.size[1])


def run_mame(mame: Path, rom: Path, frames: int, work: Path) -> Path:
    out = work / 'mame'
    out.mkdir(parents=True, exist_ok=True)
    lua = work / 'capture.lua'
    lua.write_text(LUA % {'out': out.as_posix(), 'step': MAME_STEP, 'last': frames}, encoding='utf-8')
    # MAME runs from its own folder, so every path is absolute.
    result = subprocess.run([str(mame), 'genesis', '-cart', str(rom.resolve()), '-video', 'none', '-sound', 'none',
                             '-nothrottle', '-skip_gameinfo', '-nomouse',
                             '-seconds_to_run', str(frames // 60 + 600), '-autoboot_script', str(lua.resolve()),
                             '-cfg_directory', str((work / 'cfg').resolve()), '-nvram_directory', str((work / 'nvram').resolve())],
                            capture_output=True, text=True, timeout=3600, cwd=mame.resolve().parent, creationflags=NO_WINDOW)
    if result.returncode or not (out / 'manifest.tsv').is_file() or not any(out.glob('*.raw')):
        raise SystemExit('MAME failed: ' + (result.stdout + result.stderr)[-600:])
    return out


def run_game(exe: Path, frames: int, folder: Path, *, trace: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    picture = folder / f'f{frames}.ppm'
    args = [str(exe), '--frames', str(frames)]
    args += ['--trace', str(folder / 'trace.csv')] if trace else ['--frame-image', str(picture)]
    subprocess.run(args, check=True, capture_output=True, timeout=3600, creationflags=NO_WINDOW,
                   env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'), cwd=folder)
    return picture


def trace_rows(path: Path) -> list[tuple[int, str]]:
    rows = list(csv.reader(path.open(encoding='ascii')))
    frame, picture = rows[0].index('frame'), rows[0].index('frame_hash')
    return [(int(row[frame]), row[picture]) for row in rows[1:] if len(row) == len(rows[0]) and row[frame].isdigit()]


def compare(exe: Path, rom: Path, mame: Path, mame_frames: int, game_frames: int, min_run: int, work: Path) -> dict:
    from PIL import Image
    cartridge_file = cartridge(rom, work)
    try:
        out = run_mame(mame, cartridge_file, mame_frames, work)
    finally:
        if cartridge_file != rom:
            cartridge_file.unlink(missing_ok=True)       # no ROM byte is kept
    ours = work / 'game'
    run_game(exe, game_frames, ours, trace=True)
    still = []
    for first, last, _ in still_runs(trace_rows(ours / 'trace.csv'), min_run):
        picture = run_game(exe, (first + last) // 2, ours)
        still.append((first, last, Image.open(picture).convert('RGB')))
    index: dict[str, list[tuple[int, int, object]]] = {}
    for first, last, image in still:
        key = shape_key(image)
        if key:
            index.setdefault(key, []).append((first, last, image))
    sizes = {int(frame): (int(width), int(height)) for frame, width, height in
             (line.split('\t') for line in (out / 'manifest.tsv').read_text(encoding='utf-8').splitlines()[1:])}
    digests = [(frame, hashlib.sha1((out / f'{frame:06d}.raw').read_bytes()).hexdigest()) for frame in sorted(sizes)]
    results = []
    for first, last, _ in mame_runs(digests):
        width, height = sizes[first]
        raw = (out / f'{first:06d}.raw').read_bytes()
        picture = Image.frombuffer('RGBA', (width, height), raw, 'raw', 'BGRA', 0, 1).convert('RGB')
        key = shape_key(picture)
        matches = index.get(key) if key else None
        row = {'mame_first': first, 'mame_last': last, 'shape': bool(matches), 'game_runs': None, 'identical': None}
        if matches:
            row['game_runs'] = [[a, b] for a, b, _ in matches]
            row['identical'] = round(max(identical_share(picture, image) for _, _, image in matches), 4)
        results.append(row)
    matched = [r for r in results if r['shape']]
    summary = {'rom': rom.name, 'mame_frames': mame_frames, 'game_frames': game_frames,
               'game_still_pictures': len(still), 'mame_still_pictures': len(results), 'shape_matched': len(matched),
               'identical_share_mean': (round(sum(r['identical'] for r in matched) / len(matched), 4) if matched else None),
               'unmatched_mame_runs': [[r['mame_first'], r['mame_last']] for r in results if not r['shape']]}
    return {**summary, 'results': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('exe', type=Path)
    parser.add_argument('rom', type=Path, help='the cartridge the game was converted from (a zip or a plain file), read in place')
    parser.add_argument('--mame', type=Path, default=os.environ.get('RETRO_RECOMP_MAME'), help='mame.exe of MAME 0.289')
    parser.add_argument('--mame-frames', type=int, default=3000)
    parser.add_argument('--game-frames', type=int, default=3100)
    parser.add_argument('--min-run', type=int, default=15, help='frames a picture of the game stands still to be captured')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'megadrive-mame-compare')
    options = parser.parse_args()
    if not options.mame:
        parser.error('--mame (or RETRO_RECOMP_MAME) is required')
    options.work.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=options.work))
    summary = compare(options.exe, options.rom, options.mame, options.mame_frames, options.game_frames, options.min_run, work)
    (work / 'report.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'results'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
