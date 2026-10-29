"""Compare a converted CPS-1 game with MAME 0.289, frame by frame (development check, nothing here is shipped).

    python -B tools/cps1_mame_compare.py SET --exe GAME.exe --mame MAME.exe --roms ROMS_FOLDER [--frames 3600] [--step 10]
                                         [--route play|attract] [--work DIR]

The delivered game and MAME run the same pseudo-random route (the conversion's own credited play route, rebuilt from the
set's catalogue entry and the set's SHA-256, which the conversion report states). The game replays it headless with its
`--script` option and saves a capture every `step` frames. MAME runs the set with a Lua script that saves the raw screen every
`step` frames and *replaces what the 68000 reads* at the input addresses (IN1 at 0x800000, IN0 at 0x800018 and, through the
CPS-B registers, IN2 and IN3) with the values the route gives for that frame, so both sides read each value in the same frame.
The captures are then compared pixel for pixel, MAME frame k with game frame k + OFFSET (calibrated by the attract route).

What it measures: agreement of the game's picture with MAME 0.289's, not with the original boards. Sound is not compared here.
MAME must be a local copy you obtained yourself; nothing of it, and no ROM, enters this repository. The romset folder is read
in place. A set MAME cannot run from the romsets (a missing PAL dump) is reported as not comparable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import cps1_catalogue
from retrorecomp.cps1_conversion import routes

CPS_B_BASE = 0x800140
LUA = r'''
local out = "%(out)s"
local last = %(last)d
local step = %(step)d
local events = %(events)s
local port_in2, port_in3 = %(in2)d, %(in3)d
local cpu = manager.machine.devices[":maincpu"]
local space = cpu.spaces["program"]
local screen = manager.machine.screens[":screen"]
local state = {%(initial)s}
-- The value a read sees depends on the frame the *game* is in: its pads are applied at line 0 of each frame, so frame n sees the
-- script lines up to frame n - 1. The game's line 0 falls %(phase)d lines (of 262) after MAME's vertical blank starts, which is
-- where MAME's machine time is a whole number of frame periods; the frame of a read follows from that time.
local period = screen.frame_period
local function game_frame()
  return math.floor(manager.machine.time:as_double() / period - %(phase)d / 262) + 1
end
local function pick(name, offset, data, mem_mask)
  local n = game_frame()
  local best = nil
  for _, e in ipairs(events) do
    if e[1] <= n - 1 then best = e else break end
  end
  if best then return {best[2], best[3], best[4], best[5]} end
  return state
end
taps = {}   -- global on purpose: a tap lives only as long as its handle
taps[1] = space:install_read_tap(0x800000, 0x800007, "rr_in1", function(offset, data, mem_mask) return pick("in1", offset, data, mem_mask)[2] end)
taps[2] = space:install_read_tap(0x800018, 0x800019, "rr_in0", function(offset, data, mem_mask) return ((pick("in0", offset, data, mem_mask)[1] & 0xff) << 8) | 0xff end)
if port_in2 > 0 then
  taps[3] = space:install_read_tap(%(base_address)d + port_in2, %(base_address)d + port_in2 + 1, "rr_in2", function(offset, data, mem_mask) return pick("in2", offset, data, mem_mask)[3] end)
end
if port_in3 > 0 then
  taps[4] = space:install_read_tap(%(base_address)d + port_in3, %(base_address)d + port_in3 + 1, "rr_in3", function(offset, data, mem_mask) return pick("in3", offset, data, mem_mask)[4] end)
end
subscription = emu.add_machine_frame_notifier(function()
  local f = screen:frame_number()
  if f %% step == 0 then
    local px, w, h = screen:pixels()
    local fh = io.open(out .. string.format("/%%06d.raw", f), "wb")
    fh:write(px)
    fh:close()
  end
  if f >= last then manager.machine:exit() end
end)
'''


def port_values(game: dict, script: str) -> list[tuple[int, int, int, int, int]]:
    """(frame, IN0, IN1, IN2, IN3): the raw active-low port values the game's host derives from each script line."""
    from retrorecomp.cps1_build import input_table
    table = input_table(game)
    default = [game['inputs'].get(port, {}).get('default', 0xffff) for port in ('IN0', 'IN1', 'IN2', 'IN3')]
    rows = []
    for line in script.splitlines():
        frame, p1, p2 = line.split()[:3]
        pads = (int(p1, 16), int(p2, 16), 0, 0)
        values = list(default)
        for port, mask, action, player in table:
            if 1 <= player <= 4 and pads[player - 1] & (1 << action):
                values[port] &= ~mask & 0xffff
        rows.append((int(frame), *values))
    return rows


def unrotate(image):
    """The game rotates vertical boards for display; MAME's raw screen is not rotated."""
    from PIL import Image
    return image.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.TRANSPOSE)


def compare(name: str, exe: Path, mame: Path, roms: Path, frames: int, step: int, route: str, work: Path, offset: int,
            phase: int = 22) -> dict:
    from PIL import Image, ImageChops
    game = cps1_catalogue.by_set()[name]
    six = any(n in ('button4', 'button5', 'button6') for port in game['inputs'].values() for _, n, _ in port.get('inputs', ()))
    report = json.loads(next((exe.parent / 'datas' / 'reports').glob('*/conversion-report.json')).read_text(encoding='utf-8'))
    plan = {row[0]: row for row in routes(report['rom']['sha256'], frames=3600, level='standard', six_buttons=six)}
    _, route_frames, script = plan[route]
    wanted = next(r['script_sha256'] for r in report['scan']['routes'] if r['name'] == route)
    assert hashlib.sha256(script.encode('ascii')).hexdigest() == wanted, 'the route script differs from the conversion\'s'
    frames = min(frames, route_frames)
    work = work / name / route
    (work / 'mame').mkdir(parents=True, exist_ok=True)
    (work / 'game').mkdir(parents=True, exist_ok=True)
    for old in list((work / 'mame').glob('*.raw')) + list((work / 'game').glob('*.bmp')):
        old.unlink()
    (work / 'route.inputs').write_text(script, encoding='ascii', newline='\n')
    events = port_values(game, script)
    initial = ','.join(str(v) for v in events[0][1:]) if events and events[0][0] == 0 else ','.join(
        str(game['inputs'].get(p, {}).get('default', 0xffff)) for p in ('IN0', 'IN1', 'IN2', 'IN3'))
    ports = game['ports']
    lua = work / 'capture.lua'
    lua.write_text(LUA % {'out': (work / 'mame').as_posix(), 'last': frames + 8, 'step': step, 'initial': initial, 'base_address': CPS_B_BASE, 'phase': phase,
                          'in2': ports[0], 'in3': ports[1],
                          'events': '{' + ','.join('{%d,%d,%d,%d,%d}' % e for e in events) + '}'}, encoding='utf-8')
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    subprocess.run([str(exe), '--headless', '--frames', str(frames + 8), '--script', str(work / 'route.inputs'), '--capture',
                    str(work / 'game'), '--capture-every', str(step)], env=environment, check=True, capture_output=True, timeout=900,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    mame_run = subprocess.run([str(mame), name, '-rompath', str(roms), '-video', 'none', '-sound', 'none', '-nothrottle',
                               '-skip_gameinfo', '-nomouse', '-autoboot_script', str(lua), '-cfg_directory', str(work / 'cfg'),
                               '-nvram_directory', str(work / 'nvram')], capture_output=True, text=True, timeout=1800,
                              cwd=mame.parent, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    captures = sorted((work / 'mame').glob('*.raw'))
    if mame_run.returncode or not captures:
        return {'set': name, 'route': route, 'comparable': False, 'reason': (mame_run.stdout + mame_run.stderr).strip()[-300:]}
    results, identical = [], 0
    for capture in captures:
        mame_frame = int(capture.stem)
        game_frame = mame_frame + offset
        picture = work / 'game' / f'frame-{game_frame:06d}.bmp'
        if mame_frame < step or not picture.is_file():
            continue
        raw = capture.read_bytes()
        mame_image = Image.frombuffer('RGBA', (384, 224), raw, 'raw', 'BGRA', 0, 1).convert('RGB')
        ours = Image.open(picture).convert('RGB')
        if ours.size != mame_image.size:
            ours = unrotate(ours)
        if ours.size == mame_image.size:
            delta = ImageChops.difference(mame_image, ours)
            different = 0 if delta.getbbox() is None else delta.convert('L').point(lambda v: 255 if v else 0).histogram()[255]
        else:
            different = -1
        identical += different == 0
        results.append({'mame_frame': mame_frame, 'game_frame': game_frame, 'different_pixels': different})
    first = next((r['mame_frame'] for r in results if r['different_pixels']), None)
    summary = {'set': name, 'route': route, 'comparable': True, 'offset': offset, 'compared': len(results), 'identical': identical,
               'first_difference_frame': first, 'frames_run': frames}
    (work / 'report.json').write_text(json.dumps({**summary, 'frames': results}, indent=1), encoding='utf-8')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('set')
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--mame', type=Path, default=os.environ.get('RETRO_RECOMP_MAME'))
    parser.add_argument('--roms', type=Path, default=os.environ.get('RETRO_RECOMP_MAME_ROMS'))
    parser.add_argument('--frames', type=int, default=3600)
    parser.add_argument('--step', type=int, default=10)
    parser.add_argument('--route', choices=('attract', 'play'), default='play')
    parser.add_argument('--offset', type=int, default=0, help='game frame = MAME frame + offset (calibrate on the attract route)')
    parser.add_argument('--phase', type=int, default=22, help='lines between the start of the vertical blank in MAME and line 0 of the game')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'cps1-mame-compare')
    options = parser.parse_args()
    if not options.mame or not options.roms:
        parser.error('--mame and --roms (or RETRO_RECOMP_MAME and RETRO_RECOMP_MAME_ROMS) are required')
    summary = compare(options.set, options.exe, options.mame, options.roms, options.frames, options.step, options.route, options.work,
                      options.offset, options.phase)
    print(json.dumps(summary))
    return 0 if summary.get('comparable') else 3


if __name__ == '__main__':
    sys.exit(main())
