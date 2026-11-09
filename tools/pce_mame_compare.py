"""Compare a converted PC Engine game with MAME 0.289, frame by frame, no input on either side (development check, nothing is shipped).

    python -B tools/pce_mame_compare.py GAME.exe CARD.pce --mame MAME.exe [--machine tg16|pce] [--frames 3000] [--no-sound]
                                        [--keep-oracle] [--work DIR]

Both sides start the same HuCard from power on and receive no input. The delivered game runs headless (`--headless --frames N`) and
writes, with options it already has, the picture of every frame (`--capture DIR --capture-every 1`), its sound (`--pcm`) and its
trace. MAME runs its `tg16` driver (the United States TurboGrafx-16; `--machine pce` for the Japanese console) headless
(`-video none -sound none`, no window, no input device) with a Lua script that saves the raw screen of every frame (a frame equal to
the one before is saved once) and `-wavwrite` for the sound at 44,100 Hz, the rate the game writes. The card is read with the
converter's own reader (retrorecomp/pce_rom.py) and given to MAME as a plain linear dump without header: a ZIP, a copier header or
a bit-reversed dump all reach MAME in the order its loader expects. The copy lives under --work and is deleted when the run ends.

Pictures. The game writes the active picture of the VDC (its width and height from the video registers, no border). MAME writes
1088 x 242 dots, the picture placed inside blank overscan, each pixel of the VDC repeated 4 times (256-pixel mode), 3 (320 to 352) or
2 (512) in a row. For every width and height the game shows, the tool finds once, on a frame where both sides show a picture, the
dots per pixel, the column and the row at which the game's picture sits inside MAME's frame (`geometry`: the first frame of that
size that matches on at least 90 percent of its pixels). The geometry is then the same for every frame of that size; the rows of
the game that MAME's window cuts off are not compared and are reported. A frame is *equal* when, over the compared pixels, every
pixel has the same level in each of its three channels. The VDC's colour has 8 levels a channel; the two emulators write them
differently (MAME 0, 36, 73, 109, 146, 182, 219, 255; the game 0, 36, 72, 109, 145, 182, 218, 255: read from a capture of each side), so
the equality of the 24-bit colours is reported apart (`identical_exact`): it is not a different picture, it is a different table,
and which table is closer to a real console is not known. The frame offset (MAME frame f against game frame f + offset) is chosen
among -3 to 3 by the number of equal frames on a sample, and reported, not corrected afterwards.

For a frame that is not equal the tool says why, in this order: `offset` (it equals the game's picture of a frame one or two away),
`shifted` (it equals the game's picture of a frame further away: the run is the same, the timing is not; the distance is reported),
`palette` (the same shape up to a one-to-one change of colours), `placement` (equal at another place in MAME's frame), `no_picture`
(the game shows none), `unplaced` (a one-colour picture of a size never seen with a picture: only its colour is checked), or
`content` (the share and the box of the pixels that differ, whether one side is blank).

Sound. Per window of one second from the first tenth of a second of both runs (MAME's output steps up to its DC offset in the first
70 ms), for each channel: the AC level (the mean, slope and curvature of each window are taken away first: MAME's output carries a DC
offset of about a quarter of full scale, the game's none) in dB, MAME minus game; the cosine of the magnitude spectra, per window and
averaged; the third-octave bands. MAME's frame is 263 lines (737.3 samples at 44.1 kHz) on every card; the game's engine follows the
card (Bonk's Adventure: 734.3 samples a frame, 262 lines; the three others 737.1): the samples per frame are reported, and the
windows of the two sides slide by up to 0.4 percent of the elapsed time, so no waveform correlation is claimed. Windows where one side
is silent are counted, not compared.

Which MAME driver. `tg16` runs the United States cards, and a Japanese card too (a picture appears on both drivers for Soldier Blade
(Japan)); on `pce` the two United States cards tried (Bonk's Adventure, Boxyboy) stay black, so `tg16` is the default. The game's
engine sets the `japanese` flag of its pad port (the console-region bit) whatever the card, while `tg16` answers as the TurboGrafx-16: a
card that reads that bit may take another path on the two sides. The tool reports where the pictures part, not why.
The Backup RAM. MAME gives every card one (its nvram), and the game does too: MAME's starts here with the same formatted memory as
the game with no save (`seed_backup`). The two still differ in one way: MAME's has a lock and its pad port always says a CD is attached;
the game's has no lock and its pad port says none is.

What this says: agreement of the game's pictures and sound level with MAME 0.289's on the first seconds after power on, no input,
for the cards run. It says nothing of the original hardware (MAME is not hardware), of gameplay, of input, of physical latency or of
what a card does after those seconds. MAME must be a local copy you obtained yourself; nothing of it, no frame, no sound file and
no ROM enters this repository: the card is read in place, the tool writes only under --work (default .build/pce-mame, which git
ignores) and deletes the frames, the sound and the cartridge copy when it ends unless --keep-oracle is given.
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
from typing import NamedTuple

try:
    import numpy
except ImportError:                                        # the comparison itself needs it
    numpy = None

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MAME_WIDTH, MAME_HEIGHT = 1088, 242         # the screen of MAME's tg16 and pce drivers, as `screen:pixels()` returns it
DOTS = (4, 3, 2)                            # the three dot clocks of the VDC: dots of MAME's screen per pixel of the VDC
MAX_TOP = 24                                # rows, either way, searched for the top of the picture inside MAME's frame
OFFSETS = (0, 1, -1, 2, -2, 3, -3)          # frame offsets tried, the likeliest first
AUDIO_RATE = 44100                          # PCE_AUDIO_RATE in native/pce_machine.h; MAME is asked for the same
SILENT = 2.0                                # AC level (16-bit units) under which a window counts as silent
MIN_GEOMETRY_SHARE = 0.9
MIN_CONTENT = 800                           # pixels that are not the background colour: fewer cannot pin a picture to a place
PLACEMENT_SEARCHES = 25                     # frames that are not equal for which the tool looks for another place of the picture
VOTES = 3                                   # frames that must agree on the place of a picture size
# The 8 values of one colour channel as each side writes them: read from a capture of each, not from a source.
LEVELS = {'mame': (0, 36, 73, 109, 146, 182, 219, 255), 'game': (0, 36, 72, 109, 145, 182, 218, 255)}

LUA = '''local out = "%(out)s"
local last = %(last)d
local screen = manager.machine.screens[":screen"]
local manifest = io.open(out .. "/manifest.tsv", "w")
manifest:write("frame\\twidth\\theight\\tfile\\n")
local previous, owner = nil, 0
subscription = emu.add_machine_frame_notifier(function()
  local f = screen:frame_number()
  if f > 0 then
    local px, w, h = screen:pixels()
    if px ~= previous then
      local fh = io.open(out .. string.format("/%%06d.raw", f), "wb")
      fh:write(px)
      fh:close()
      previous, owner = px, f
    end
    manifest:write(string.format("%%d\\t%%d\\t%%d\\t%%d\\n", f, w, h, owner))
  end
  if f >= last then
    manifest:close()
    manager.machine:exit()
  end
end)
'''


def level_table(name: str):
    """A 256-entry table: the value of a channel as `name` writes it -> its level 0 to 7 (the nearest of the 8)."""
    values = numpy.array(LEVELS[name])
    return numpy.array([int(numpy.argmin(numpy.abs(values - v))) for v in range(256)], dtype=numpy.uint8)


GAME_LUT, MAME_LUT = (level_table('game'), level_table('mame')) if numpy is not None else (None, None)


def read_ppm(path: Path):
    """The (height, width, 3) array of a binary PPM the game wrote ((0, 0, 3) for a frame with no picture yet)."""
    parts = Path(path).read_bytes().split(b'\n', 3)
    if len(parts) != 4 or parts[0] != b'P6':
        raise ValueError(f'{path}: not a binary PPM')
    width, height = (int(value) for value in parts[1].split())
    return numpy.frombuffer(parts[3], dtype=numpy.uint8, count=width * height * 3).reshape(height, width, 3)


def mame_rgb(raw: bytes):
    """The (242, 1088, 3) RGB array of a raw screen of MAME (BGRA)."""
    data = numpy.frombuffer(raw, dtype=numpy.uint8)
    if data.size != MAME_WIDTH * MAME_HEIGHT * 4:
        raise ValueError(f'a MAME frame of {data.size} bytes, expected {MAME_WIDTH * MAME_HEIGHT * 4}')
    return numpy.ascontiguousarray(data.reshape(MAME_HEIGHT, MAME_WIDTH, 4)[:, :, 2::-1])


class Geometry(NamedTuple):
    """Where a picture of the game sits in MAME's frame: `dots` columns of MAME per pixel, the first at column `left`, and the
    row `top` of MAME for the first row of the game's picture (negative: MAME's window cuts the first rows off)."""
    dots: int
    left: int
    top: int

    def columns(self, width: int):
        return self.left + self.dots * numpy.arange(width) + self.dots // 2

    def rows(self, height: int) -> tuple[int, int] | None:
        """(first, last + 1) of the rows of the game's picture that MAME shows."""
        first, last = max(0, -self.top), min(height, MAME_HEIGHT - self.top)
        return (first, last) if last > first else None

    def fits(self, width: int) -> bool:
        return width > 0 and self.dots in DOTS and self.left >= 0 and self.left + self.dots * width <= MAME_WIDTH

    def label(self) -> str:
        return f'{self.dots} dots a pixel, column {self.left}, row {self.top}'


def measure(game, mame, geometry: Geometry) -> dict | None:
    """The agreement of the game's picture (height, width, 3) with MAME's (242, 1088, 3) at `geometry` over the rows MAME shows.
    None when the geometry does not hold the picture."""
    height, width = game.shape[:2]
    rows = geometry.rows(height) if geometry.fits(width) else None
    if rows is None:
        return None
    first, last = rows
    ours = game[first:last]
    theirs = mame[first + geometry.top:last + geometry.top][:, geometry.columns(width)]
    exact = (ours == theirs).all(axis=2)
    same = (GAME_LUT[ours] == MAME_LUT[theirs]).all(axis=2)
    return {'pixels': int(same.size), 'equal': int(same.sum()), 'exact': int(exact.sum()), 'rows': (first, last), 'mask': same,
            'hidden_rows': height - (last - first)}


def outside_nonblack(mame, geometry: Geometry, width: int, height: int) -> bool:
    """True when MAME's frame has a pixel that is not black outside the window of the game's picture."""
    lit = mame.any(axis=2)
    rows = geometry.rows(height)
    if rows is None:
        return bool(lit.any())
    first, last = rows[0] + geometry.top, rows[1] + geometry.top
    return int(lit.sum()) > int(lit[first:last, geometry.left:geometry.left + geometry.dots * width].sum())


def grouped(theirs, geometry: Geometry, width: int, rows: tuple[int, int], top: int) -> float:
    """The share of the groups of dots of one pixel of the game (`theirs` is MAME's level picture) that are one colour."""
    block = theirs[rows[0] + top:rows[1] + top, geometry.left:geometry.left + geometry.dots * width]
    block = block.reshape(block.shape[0], width, geometry.dots, 3)
    return round(float((block == block[:, :, :1]).all(axis=(2, 3)).mean()), 6)


def outside_uniform(packed, geometry: Geometry, width: int, height: int) -> bool:
    """True when everything of MAME's frame outside the window of the game's picture is of one colour (`packed`: MAME's level
    picture as one number a pixel): the border of the console's screen is one colour, a picture placed too high or too low leaves some of
    itself outside."""
    rows = geometry.rows(height)
    if rows is None:
        return False
    first, last = rows[0] + geometry.top, rows[1] + geometry.top
    right = geometry.left + geometry.dots * width
    parts = [packed[:first].ravel(), packed[last:].ravel(), packed[first:last, :geometry.left].ravel(), packed[first:last, right:].ravel()]
    values = numpy.concatenate(parts)
    return bool(values.size == 0 or (values == values[0]).all())


def find_geometry(game, mame, minimum: float = MIN_GEOMETRY_SHARE, probes: int = 6):
    """(Geometry, equal share) of the best placement of the game's picture in MAME's frame, or None when no placement reaches
    `minimum` (a picture of one colour cannot be placed). The search compares a few of the busiest rows of the picture at every
    column and row first, then the whole picture for the best few. The dot clock the width usually goes with is tried first and the
    others only when it does not give a placement that is right to 99 percent. None also when two places are equally right (a
    picture that repeats from row to row does not say where it sits)."""
    height, width = game.shape[:2]
    if not width or not height:
        return None
    ours = GAME_LUT[game]
    theirs = MAME_LUT[mame]
    packed = theirs[..., 0].astype(numpy.int32) * 64 + theirs[..., 1] * 8 + theirs[..., 2]
    colours = [len(numpy.unique(ours[r].reshape(-1, 3), axis=0)) for r in range(height)]
    order = sorted(range(height), key=lambda r: -colours[r])[:probes]
    if colours[order[0]] < 2:
        return None
    usual = 4 if width <= 256 else 3 if width <= 400 else 2
    scored = []
    for dots in sorted(DOTS, key=lambda d: d != usual):
        span = dots * width
        if span > MAME_WIDTH:
            continue
        lefts = numpy.arange(0, MAME_WIDTH - span + 1)
        index = lefts[:, None] + dots * numpy.arange(width)[None, :] + dots // 2
        candidates = []
        for top in range(-MAX_TOP, MAX_TOP + 1):
            score, used = numpy.zeros(len(lefts)), 0
            for r in order:
                if 0 <= r + top < MAME_HEIGHT:
                    score += (theirs[r + top][index] == ours[r][None]).all(axis=2).mean(axis=1)
                    used += 1
            if used:
                for slot in numpy.argsort(score)[-3:]:
                    candidates.append((float(score[slot]) / used, dots, int(lefts[slot]), top))
        for _, _, left, top in sorted(candidates, reverse=True)[:40]:
            geometry = Geometry(dots, left, top)
            result = measure(game, mame, geometry)
            if result and result['pixels']:
                # a placement that cuts the groups of dots of one pixel in two is a column too far: the group must be one colour
                together = grouped(theirs, geometry, width, result['rows'], top)
                if together >= 0.99:
                    share = result['equal'] / result['pixels']
                    scored.append(((outside_uniform(packed, geometry, width, height), round(share, 3), together), geometry, share))
        if scored and max(scored, key=lambda item: item[0])[2] >= 0.99:
            break
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best = scored[0]
    if best[2] < minimum:
        return None
    for key, other, share in scored[1:]:
        if key[:2] >= (best[0][0], best[0][1]) and (other.dots, other.top) != (best[1].dots, best[1].top):
            return None             # two places are equally right (a periodic picture): it does not say where it sits
    return best[1], best[2]


def content_pixels(picture) -> int:
    """The number of pixels of a picture (height, width, 3) that are not of its most frequent colour."""
    packed = (picture[..., 0].astype(numpy.int32) << 16 | picture[..., 1].astype(numpy.int32) << 8 | picture[..., 2]).ravel()
    _, counts = numpy.unique(packed, return_counts=True)
    return int(packed.size - counts.max()) if packed.size else 0


def uniform(picture) -> bool:
    return picture.size == 0 or bool((picture == picture[0, 0]).all())


def shape_preserved(ours, theirs) -> bool:
    """True when the two level pictures (same size) have the same shape up to a one-to-one change of colours."""
    a = (ours[..., 0].astype(numpy.int32) * 64 + ours[..., 1] * 8 + ours[..., 2]).ravel()
    b = (theirs[..., 0].astype(numpy.int32) * 64 + theirs[..., 1] * 8 + theirs[..., 2]).ravel()
    pairs = numpy.unique(a * 512 + b)
    return len(pairs) == len(numpy.unique(a)) == len(numpy.unique(b))


def difference_box(mask, rows: tuple[int, int]) -> dict:
    """The share of pixels that differ in a mask of equal pixels and the box (game rows, game columns) that holds them."""
    wrong = ~mask
    ys, xs = numpy.nonzero(wrong.any(axis=1))[0], numpy.nonzero(wrong.any(axis=0))[0]
    return {'differing_share': round(float(wrong.mean()), 4), 'rows': [int(ys[0]) + rows[0], int(ys[-1]) + rows[0]],
            'columns': [int(xs[0]), int(xs[-1])]}


class Comparer:
    """The comparison of the pictures of a run: geometries by picture size, then one verdict per MAME frame."""

    def __init__(self, game_at, mame_at, frames: int, game_frames: int):
        self.game_at, self.mame_at, self.frames, self.game_frames = game_at, mame_at, frames, game_frames
        self.geometries: dict[tuple[int, int], Geometry] = {}
        self.offset = 0
        self.searches = PLACEMENT_SEARCHES
        self.index: dict | None = None

    def calibrate(self, offset: int, attempts: int = 8) -> int:
        """Place every picture size, from frames with enough in them to say where the picture sits: a placement found on one frame
        must hold on the next such frames (`VOTES` of them) to stand, and the placement with the most votes wins. Returns the number
        of sizes placed."""
        votes: dict[tuple[int, int], dict[Geometry, int]] = {}
        searches: dict[tuple[int, int], int] = {}
        for frame in range(1, self.frames + 1):
            game = self.game_at(frame + offset)
            if game is None or not game.size or content_pixels(game) < MIN_CONTENT:
                continue
            key = (game.shape[1], game.shape[0])
            if key in self.geometries:
                continue
            tally = votes.setdefault(key, {})
            mame = self.mame_at(frame)
            leader = max(tally, key=tally.get) if tally else None
            measured = measure(game, mame, leader) if leader else None
            if measured and measured['equal'] >= 0.99 * measured['pixels']:
                tally[leader] += 1
            elif searches.get(key, 0) < attempts:
                searches[key] = searches.get(key, 0) + 1
                found = find_geometry(game, mame)
                if found:
                    tally[found[0]] = tally.get(found[0], 0) + 1
            if tally and max(tally.values()) >= VOTES:
                self.geometries[key] = max(tally, key=tally.get)
        for key, tally in votes.items():
            if key not in self.geometries and tally:
                self.geometries[key] = max(tally, key=tally.get)
        return len(self.geometries)

    def score(self, offset: int, sample: list[int]) -> int:
        equal = 0
        for frame in sample:
            game = self.game_at(frame + offset)
            if game is None or not game.size:
                continue
            geometry = self.geometries.get((game.shape[1], game.shape[0]))
            result = measure(game, self.mame_at(frame), geometry) if geometry else None
            equal += bool(result and result['equal'] == result['pixels'])
        return equal

    def choose_offset(self, sample_size: int = 150) -> dict:
        """Calibrate and pick the frame offset: the geometries are searched at offset 0 first, then at the next ones until some
        size is placed; the offset is the one with the most equal frames on a sample (0 wins ties)."""
        used = 0
        for used in OFFSETS:
            if self.calibrate(used):
                break
        step = max(1, (self.frames - 4) // sample_size)
        sample = list(range(4, self.frames - 3, step))
        scores = {offset: self.score(offset, sample) for offset in sorted(OFFSETS)}
        best = max(sorted(scores, key=abs), key=lambda offset: scores[offset])
        self.offset = best
        if best != used:
            self.calibrate(best)
        return {'offset': best, 'sample_frames': len(sample), 'equal_on_sample': scores}

    @staticmethod
    def fingerprint(levels) -> str:
        return hashlib.blake2b(levels.tobytes(), digest_size=8).hexdigest()

    def index_pictures(self) -> int:
        """Index the game's frames by the levels of the pixels MAME shows of them, to find where else in the run a picture of MAME
        appears; returns the number of frames indexed. Needs the places of the picture sizes."""
        self.index = {}
        for frame in range(1, self.game_frames + 1):
            game = self.game_at(frame)
            if game is None or not game.size:
                continue
            geometry = self.geometries.get((game.shape[1], game.shape[0]))
            rows = geometry.rows(game.shape[0]) if geometry and geometry.fits(game.shape[1]) else None
            if rows:
                self.index.setdefault((game.shape[1], game.shape[0], self.fingerprint(GAME_LUT[game[rows[0]:rows[1]]])), []).append(frame)
        return sum(len(frames) for frames in self.index.values())

    def elsewhere(self, frame: int, game, mame, geometry: Geometry):
        """The frame of the game, nearest to `frame + offset`, that shows exactly the picture MAME shows at `frame`; None if none."""
        rows = geometry.rows(game.shape[0])
        theirs = MAME_LUT[mame[rows[0] + geometry.top:rows[1] + geometry.top][:, geometry.columns(game.shape[1])]]
        hits = (self.index or {}).get((game.shape[1], game.shape[0], self.fingerprint(theirs)))
        return min(hits, key=lambda other: abs(other - (frame + self.offset))) if hits else None

    def verdict(self, frame: int) -> dict:
        """The verdict on MAME frame `frame` against the game's frame `frame + offset`."""
        game, mame = self.game_at(frame + self.offset), self.mame_at(frame)
        result = {'frame': frame, 'status': None}
        if game is None:
            return {**result, 'status': 'missing', 'reason': 'the game has no such frame'}
        if not game.size:
            blank = not mame.any()
            return {**result, 'status': 'equal' if blank else 'no_picture',
                    'reason': 'the game shows no picture and MAME is black' if blank else 'the game shows no picture, MAME does'}
        key = (game.shape[1], game.shape[0])
        geometry = self.geometries.get(key)
        if geometry is None:
            return self.unplaced(frame, game, mame, result)
        measured = measure(game, mame, geometry)
        result.update(width=key[0], height=key[1], exact=measured['equal'] == measured['pixels'] and measured['exact'] == measured['pixels'],
                      share=round(measured['equal'] / measured['pixels'], 4), hidden_rows=measured['hidden_rows'])
        result['outside_nonblack'] = outside_nonblack(mame, geometry, key[0], key[1])
        if measured['equal'] == measured['pixels']:
            return {**result, 'status': 'equal', 'exact': measured['exact'] == measured['pixels']}
        result['exact'] = False
        for delta in (-1, 1, -2, 2):
            other = self.game_at(frame + self.offset + delta)
            if other is not None and other.shape == game.shape:
                again = measure(other, mame, geometry)
                if again and again['equal'] == again['pixels']:
                    return {**result, 'status': 'offset', 'reason': f'MAME frame {frame} equals game frame {frame + self.offset + delta} (offset {self.offset + delta})'}
        other = self.elsewhere(frame, game, mame, geometry) if self.index is not None else None
        if other is not None:
            return {**result, 'status': 'shifted', 'delta': other - (frame + self.offset),
                    'reason': f'MAME frame {frame} equals game frame {other} (offset {other - frame}), not the one at the usual offset'}
        ours = GAME_LUT[game][measured['rows'][0]:measured['rows'][1]]
        theirs = MAME_LUT[mame[measured['rows'][0] + geometry.top:measured['rows'][1] + geometry.top][:, geometry.columns(key[0])]]
        if shape_preserved(ours, theirs):
            return {**result, 'status': 'palette', 'reason': 'the same shape up to a one-to-one change of colours'}
        found = None
        if self.searches:                       # a search for another place costs seconds: only the first frames that need one get it
            self.searches -= 1
            found = find_geometry(game, mame, minimum=0.999)
        if found and found[0] != geometry:
            return {**result, 'status': 'placement', 'reason': f'equal at another place: {found[0].label()} (usual: {geometry.label()})'}
        box = difference_box(measured['mask'], measured['rows'])
        blank = ('MAME is black' if not mame.any() else 'the game is one colour' if uniform(game) else
                 'MAME is one colour' if uniform(mame) else None)
        return {**result, 'status': 'content', 'reason': blank or 'pixels differ', **box}

    def unplaced(self, frame: int, game, mame, result: dict) -> dict:
        """A picture of a size no frame placed: only possible for one colour, whose level must be the only one MAME shows besides black."""
        colour = GAME_LUT[game[0, 0]]
        shown = {tuple(int(v) for v in c) for c in numpy.unique(MAME_LUT[mame].reshape(-1, 3), axis=0)}
        if uniform(game) and shown <= {tuple(int(v) for v in colour), (0, 0, 0)}:
            return {**result, 'status': 'unplaced', 'reason': 'one colour on both sides, the size was never seen with a picture to place'}
        return {**result, 'status': 'content', 'reason': 'no placement of a picture of this size was found'}


def summarize_pictures(verdicts: list[dict], calibration: dict, geometries: dict) -> dict:
    """The numbers of the pictures: counts by verdict, the first frame that is not equal and why, the stretches of frames that differ."""
    counts: dict[str, int] = {}
    for item in verdicts:
        counts[item['status']] = counts.get(item['status'], 0) + 1
    compared = [item for item in verdicts if item['status'] != 'missing']
    first = next((item for item in compared if item['status'] != 'equal'), None)
    runs: list[dict] = []
    for item in compared:
        if item['status'] in ('equal', 'unplaced'):
            continue
        if runs and runs[-1]['status'] == item['status'] and runs[-1]['last'] + 1 == item['frame']:
            runs[-1]['last'] = item['frame']
        else:
            runs.append({'first': item['frame'], 'last': item['frame'], 'status': item['status'], 'reason': item.get('reason'),
                         **({k: item[k] for k in ('differing_share', 'rows', 'columns') if k in item})})
    placed = [item for item in compared if 'share' in item]
    shifts = sorted(item['delta'] for item in compared if item['status'] == 'shifted')
    return {'frames_compared': len(compared), 'frame_offset': calibration['offset'], 'offset_scores': {str(k): v for k, v in calibration['equal_on_sample'].items()},
            'by_status': counts, 'equal': counts.get('equal', 0),
            'shifted_frames': {'count': len(shifts), 'delta_min': shifts[0], 'delta_median': shifts[len(shifts) // 2], 'delta_max': shifts[-1]} if shifts else None,
            'equal_share': round(counts.get('equal', 0) / len(compared), 4) if compared else None,
            'identical_exact': sum(1 for item in placed if item.get('exact')),
            'first_not_equal': ({'frame': first['frame'], 'status': first['status'], 'reason': first.get('reason')} if first else None),
            'runs_not_equal': len(runs), 'first_runs': runs[:25],
            'mean_equal_pixel_share': round(sum(item['share'] for item in placed) / len(placed), 5) if placed else None,
            'frames_with_non_black_overscan': sum(1 for item in placed if item.get('outside_nonblack')),
            'geometries': {f'{w}x{h}': {'dots': g.dots, 'column': g.left, 'row': g.top,
                                         'rows_hidden_by_mame': h - (g.rows(h)[1] - g.rows(h)[0]) if g.rows(h) else h}
                           for (w, h), g in sorted(geometries.items())},
            'frames_by_size': {f'{item["width"]}x{item["height"]}': sum(1 for other in placed if (other['width'], other['height']) == (item['width'], item['height']))
                               for item in placed}}


# ---------------------------------------------------------------------------------------------------------------- sound

def read_wav(path: Path):
    """(samples as float (n, channels), rate) of a 16-bit PCM WAV."""
    import wave
    with wave.open(str(path), 'rb') as stream:
        channels, rate, count, width = stream.getnchannels(), stream.getframerate(), stream.getnframes(), stream.getsampwidth()
        if width != 2:
            raise ValueError(f'{path}: {8 * width}-bit samples, expected 16')
        data = numpy.frombuffer(stream.readframes(count), dtype='<i2').astype(numpy.float64)
    return data.reshape(-1, channels), rate


def third_octaves(total_a, total_b, rate: int) -> tuple[float | None, float | None]:
    """The largest difference in dB of the power of a third-octave band below 4 kHz and from 5 to 16 kHz, two summed power spectra
    of one-second windows (bin = Hz)."""
    frequencies = numpy.fft.rfftfreq(rate, 1.0 / rate)
    low, high, edge = [], [], 125.0
    while edge * 2 ** (1 / 3) <= 16000:
        upper = edge * 2 ** (1 / 3)
        band = (frequencies >= edge) & (frequencies < upper)
        if band.any() and total_a[band].sum() > 0 and total_b[band].sum() > 0:
            difference = abs(10 * numpy.log10(total_a[band].sum() / total_b[band].sum()))
            (low if upper <= 4000 else high if edge >= 5000 else []).append(float(difference))
        edge = upper
    return (max(low) if low else None), (max(high) if high else None)


def detrend(window):
    """A window without its mean and its slope and curvature (a quadratic fit): MAME's output sits on a DC offset that ramps in at the
    start, which a plain mean would leave in the first second. Local to the window, so silence stays silent next to a loud passage."""
    x = numpy.linspace(-1.0, 1.0, len(window))
    return window - numpy.polyval(numpy.polyfit(x, window, 2), x)


def compare_channel(mame, game, rate: int, seconds: int | None = None) -> dict:
    """One channel (1-D arrays), per window of one second from the start of each, the DC taken away: levels and spectra."""
    mame, game = mame[rate // 10:], game[rate // 10:]       # MAME's output steps up to its DC offset in the first 70 ms: those samples are not sound
    base_dc = {'dc_offset_mame': round(float(mame.mean()), 1), 'dc_offset_game': round(float(game.mean()), 1),
               'peak_mame': int(numpy.abs(mame).max()) if len(mame) else 0, 'peak_game': int(numpy.abs(game).max()) if len(game) else 0}
    windows = min(len(mame), len(game)) // rate
    if seconds:
        windows = min(windows, seconds)
    levels, cosines, silent_both, silent_mame, silent_game = [], [], 0, [], []
    total_a = total_b = 0.0
    for index in range(windows):
        a, b = mame[index * rate:(index + 1) * rate], game[index * rate:(index + 1) * rate]
        a, b = detrend(a), detrend(b)
        ra, rb = float(numpy.sqrt((a ** 2).mean())), float(numpy.sqrt((b ** 2).mean()))
        if ra < SILENT or rb < SILENT:
            if ra < SILENT and rb < SILENT:
                silent_both += 1
            elif ra < SILENT:
                silent_mame.append(index)
            else:
                silent_game.append(index)
            continue
        levels.append(20 * numpy.log10(ra / rb))
        fa, fb = numpy.abs(numpy.fft.rfft(a * numpy.hanning(len(a)))), numpy.abs(numpy.fft.rfft(b * numpy.hanning(len(b))))
        cosines.append(float(fa @ fb / (numpy.linalg.norm(fa) * numpy.linalg.norm(fb))))
        total_a, total_b = total_a + fa ** 2, total_b + fb ** 2
    base = {'windows': windows, 'silent_both': silent_both, 'silent_mame_only': len(silent_mame), 'silent_game_only': len(silent_game),
            'silent_mame_only_seconds': silent_mame, 'silent_game_only_seconds': silent_game, **base_dc}
    if not levels:
        return {**base, 'compared': False, 'reason': 'no window with sound on both sides'}
    averaged = float(numpy.sqrt(total_a) @ numpy.sqrt(total_b) / (numpy.linalg.norm(numpy.sqrt(total_a)) * numpy.linalg.norm(numpy.sqrt(total_b))))
    low, high = third_octaves(total_a, total_b, rate)
    return {**base, 'compared': True, 'windows_compared': len(levels),
            'level_difference_db_median': round(float(numpy.median(levels)), 2), 'level_difference_db_min': round(float(min(levels)), 2),
            'level_difference_db_max': round(float(max(levels)), 2), 'level_difference_db_spread': round(float(numpy.std(levels)), 2),
            'spectrum_cosine_median': round(float(numpy.median(cosines)), 4), 'spectrum_cosine_min': round(float(min(cosines)), 4),
            'averaged_spectrum_cosine': round(averaged, 4), 'third_octave_max_db_below_4khz': None if low is None else round(low, 2),
            'third_octave_max_db_5_to_16khz': None if high is None else round(high, 2)}


def compare_sound(wav: Path, pcm: Path, rate: int = AUDIO_RATE, seconds: int | None = None, mame_frames: int = 0,
                  game_samples: list[int] | None = None) -> dict:
    """MAME's WAV against the game's raw PCM (stereo, 16-bit, `rate` Hz), per channel, level in dB as MAME minus game."""
    mame, wav_rate = read_wav(wav)
    if wav_rate != rate or mame.shape[1] != 2:
        return {'compared': False, 'reason': f'MAME wrote {mame.shape[1]} channels at {wav_rate} Hz, expected 2 at {rate} Hz'}
    game = numpy.fromfile(pcm, dtype='<i2').astype(numpy.float64).reshape(-1, 2)
    result = {'compared': True, 'rate': rate, 'seconds_mame': round(len(mame) / rate, 3), 'seconds_game': round(len(game) / rate, 3),
              'left': compare_channel(mame[:, 0], game[:, 0], rate, seconds), 'right': compare_channel(mame[:, 1], game[:, 1], rate, seconds)}
    if mame_frames:
        result['samples_per_frame_mame'] = round(len(mame) / mame_frames, 2)
    if game_samples:
        result['samples_per_frame_game'] = round(sum(game_samples) / 2 / len(game_samples), 2)
    result['compared'] = bool(result['left'].get('compared') and result['right'].get('compared'))
    return result


# ------------------------------------------------------------------------------------------------------ the two runs

def prepare_cartridge(card: Path, folder: Path) -> tuple[Path, dict]:
    """The card as MAME's loader expects it: the decoded ROM, no header, bits in linear order, a copy under `folder`."""
    sys.path.insert(0, str(ROOT))
    from retrorecomp import pce_rom
    data = pce_rom.file_bytes(card)
    rom, header, encoding = pce_rom.decode(data)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'cartridge.pce'
    target.write_bytes(rom)
    return target, {'header': header, 'encoding': encoding, 'rom_bytes': len(rom)}


def mame_command(mame: Path, machine: str, cartridge: Path, lua: Path, work: Path, wav: Path | None, frames: int) -> list[str]:
    """The command line of the MAME run: no window, no sound device, no input device, every path absolute (MAME runs from its folder)."""
    command = [str(mame), machine, '-cart', str(cartridge.resolve()), '-video', 'none', '-sound', 'none', '-nothrottle',
               '-skip_gameinfo', '-nomouse', '-keyboardprovider', 'none', '-joystickprovider', 'none',
               '-seconds_to_run', str(frames // 59 + 120), '-autoboot_script', str(lua.resolve()),
               '-cfg_directory', str((work / 'cfg').resolve()), '-nvram_directory', str((work / 'nvram').resolve())]
    if wav is not None:
        command += ['-wavwrite', str(wav.resolve()), '-samplerate', str(AUDIO_RATE)]
    return command


def seed_backup(machine: str, work: Path) -> Path:
    """MAME's Backup RAM (its nvram, 2,048 raw bytes) starts as the game's does with no save: the same formatted memory."""
    from retrorecomp.pce_conversion import BACKUP_FORMATTED
    path = work / 'nvram' / machine / 'pce_cd_bram'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(BACKUP_FORMATTED)
    return path


def run_mame(mame: Path, machine: str, cartridge: Path, frames: int, work: Path, sound: bool) -> Path:
    out = work / 'mame'
    out.mkdir(parents=True, exist_ok=True)
    seed_backup(machine, work)
    lua = work / 'capture.lua'
    lua.write_text(LUA % {'out': out.resolve().as_posix(), 'last': frames}, encoding='utf-8')
    result = subprocess.run(mame_command(mame, machine, cartridge, lua, work, work / 'mame.wav' if sound else None, frames),
                            capture_output=True, text=True, timeout=7200, cwd=mame.resolve().parent, creationflags=NO_WINDOW)
    if result.returncode or not (out / 'manifest.tsv').is_file() or not any(out.glob('*.raw')):
        raise SystemExit('MAME failed: ' + (result.stdout + result.stderr)[-600:])
    return out


def run_game(exe: Path, frames: int, folder: Path) -> dict:
    """The delivered game, headless, with the options it has: a picture of every frame, its PCM, its trace and its report."""
    folder.mkdir(parents=True, exist_ok=True)
    pictures = folder / 'frames'
    pictures.mkdir(exist_ok=True)
    subprocess.run([str(exe), '--headless', '--frames', str(frames), '--trace', str(folder / 'trace.csv'), '--pcm', str(folder / 'game.pcm'),
                    '--capture', str(pictures), '--capture-every', '1', '--report', str(folder / 'report.json')],
                   check=True, capture_output=True, timeout=7200, creationflags=NO_WINDOW, cwd=folder,
                   env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1'))
    return json.loads((folder / 'report.json').read_text(encoding='utf-8'))


def trace_samples(path: Path) -> list[int]:
    """The number of PCM samples (both channels) the game wrote at each frame, from its trace."""
    with path.open(encoding='ascii') as stream:
        rows = list(csv.reader(stream))
    column = rows[0].index('samples')
    return [int(row[column]) for row in rows[1:] if len(row) == len(rows[0])]


class MameFrames:
    """The frames of MAME's run by number: the manifest says which saved file holds each (a frame equal to the one before is saved once)."""

    def __init__(self, folder: Path):
        self.folder = folder
        lines = (folder / 'manifest.tsv').read_text(encoding='utf-8').splitlines()[1:]
        self.owner = {int(f): int(o) for f, _, _, o in (line.split('\t') for line in lines)}
        self.cached: tuple[int, object] | None = None

    def __len__(self) -> int:
        return len(self.owner)

    def __call__(self, frame: int):
        owner = self.owner[frame]
        if self.cached is None or self.cached[0] != owner:
            self.cached = (owner, mame_rgb((self.folder / f'{owner:06d}.raw').read_bytes()))
        return self.cached[1]


class GameFrames:
    """The pictures of the game by number (frame 1 is the first), the last few kept."""

    def __init__(self, folder: Path, count: int):
        self.folder, self.count, self.kept = folder, count, {}

    def __call__(self, frame: int):
        if not 1 <= frame <= self.count:
            return None
        if frame not in self.kept:
            if len(self.kept) > 8:
                self.kept.pop(next(iter(self.kept)))
            self.kept[frame] = read_ppm(self.folder / f'frame-{frame:06d}.ppm')
        return self.kept[frame]


def progress(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def compare(exe: Path, card: Path, mame: Path, machine: str, frames: int, sound: bool, keep: bool, work: Path, reuse: Path | None = None) -> dict:
    """The whole comparison. `reuse`: the folder of an earlier run that kept its frames (--keep-oracle): its pictures and sound are
    compared again, nothing is run."""
    margin = 4
    if reuse:
        work, out, ours, keep = reuse, reuse / 'mame', reuse / 'game', True
        earlier = json.loads((reuse / 'report.json').read_text(encoding='utf-8')) if (reuse / 'report.json').is_file() else {}
        card_info, report = {**earlier.get('card_reading', {}), 'reused_from': reuse.name}, json.loads((reuse / 'game' / 'report.json').read_text(encoding='utf-8'))
        card, machine = Path(earlier.get('card', card.name)), earlier.get('machine', machine)
    else:
        cartridge, card_info = prepare_cartridge(card, work)
        try:
            out = run_mame(mame, machine, cartridge, frames, work, sound)
        finally:
            cartridge.unlink(missing_ok=True)       # no ROM byte is kept
        progress('MAME done')
        ours = work / 'game'
        report = run_game(exe, frames + margin, ours)
        progress('game done')
    mame_frames = MameFrames(out)
    comparer = Comparer(GameFrames(ours / 'frames', frames + margin), mame_frames, min(frames, len(mame_frames)), frames + margin)
    calibration = comparer.choose_offset()
    progress(f'offset {calibration["offset"]}, places {comparer.geometries}, {comparer.index_pictures()} pictures indexed')
    verdicts = []
    for frame in range(1, comparer.frames + 1):
        verdicts.append(comparer.verdict(frame))
        if frame % 500 == 0:
            progress(f'{frame} frames compared')
    summary = {'card': card.name, 'machine': machine, 'card_reading': card_info, 'mame_frames': len(mame_frames), 'game_frames': report.get('frames'),
               'game_native_instructions': report.get('native_instructions'), 'game_interpreted_instructions': report.get('interpreted_instructions'),
               'pictures': summarize_pictures(verdicts, calibration, comparer.geometries)}
    if sound:
        wav = work / 'mame.wav'
        summary['sound'] = (compare_sound(wav, ours / 'game.pcm', mame_frames=len(mame_frames), game_samples=trace_samples(ours / 'trace.csv'))
                            if wav.is_file() else {'compared': False, 'reason': 'MAME wrote no sound file'})
    summary['verdicts_not_equal'] = [item for item in verdicts if item['status'] not in ('equal', 'missing')][:200]
    if not keep:                                 # nothing of MAME's, and none of the game's pictures, stays on disk
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(ours / 'frames', ignore_errors=True)
        (work / 'mame.wav').unlink(missing_ok=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('exe', type=Path, help='the delivered game')
    parser.add_argument('card', type=Path, help='the HuCard the game was converted from (a .pce or a zip), read in place')
    parser.add_argument('--mame', type=Path, default=os.environ.get('RETRO_RECOMP_MAME'), help='mame.exe of MAME 0.289')
    parser.add_argument('--machine', choices=['tg16', 'pce'], default='tg16', help='tg16: United States TurboGrafx-16; pce: Japanese PC Engine')
    parser.add_argument('--frames', type=int, default=3000, help='frames of MAME compared (the game runs a few more)')
    parser.add_argument('--no-sound', action='store_true', help='compare the pictures only')
    parser.add_argument('--keep-oracle', action='store_true', help='keep the frames and the sound of both sides under --work')
    parser.add_argument('--reuse', type=Path, help='the run folder of an earlier --keep-oracle run: compare its frames and sound again, run nothing')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'pce-mame')
    options = parser.parse_args()
    if not options.mame:
        parser.error('--mame (or RETRO_RECOMP_MAME) is required')
    options.work.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f'run-{options.card.stem[:24].replace(" ", "_")}-', dir=options.work))
    summary = compare(options.exe, options.card, options.mame, options.machine, options.frames, not options.no_sound, options.keep_oracle, work, options.reuse)
    (work / 'report.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    brief = {key: value for key, value in summary.items() if key != 'verdicts_not_equal'}
    print(json.dumps(brief, indent=1))
    print(f'report: {work / "report.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
