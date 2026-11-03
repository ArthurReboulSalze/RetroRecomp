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


QSOUND_RATE = 60e6 / 2 / 1248    # the QSound chip's sample rate (24,038.46 Hz); MAME is asked for 24,038 Hz, the game writes the exact one
AUDIO_RATE = 55930    # the YM2151 rate, CPS1_AUDIO_RATE in native/cps1_machine.h: both sides are brought to it


def read_wav(path: Path):
    """Mono float samples of a 16-bit PCM WAV (channels averaged) and its rate."""
    import numpy
    import wave
    with wave.open(str(path), 'rb') as stream:
        channels, rate, count = stream.getnchannels(), stream.getframerate(), stream.getnframes()
        data = numpy.frombuffer(stream.readframes(count), dtype='<i2').astype(numpy.float64)
    return data.reshape(-1, channels).mean(axis=1), rate


def read_wav_channels(path: Path):
    """The channels of a 16-bit PCM WAV, one array each, and its rate."""
    import numpy
    import wave
    with wave.open(str(path), 'rb') as stream:
        channels, rate, count = stream.getnchannels(), stream.getframerate(), stream.getnframes()
        data = numpy.frombuffer(stream.readframes(count), dtype='<i2').astype(numpy.float64)
    return [data[index::channels] for index in range(channels)], rate


def compare_sound(wav: Path, pcm: Path, seconds: int | None = None, rate: int = AUDIO_RATE, channels: int = 1) -> dict:
    """Agreement of MAME's sound with the game's, in one-second windows.

    Mono at the YM2151 rate, or the two channels of the QSound boards at their own rate (each channel compared on its own, under
    `left` and `right`). The game's samples start with its first frame and MAME's with its first frame, so the
    lag is searched within one frame (936 samples at the YM2151 rate). Per window: the RMS levels in dB, and the cosine similarity of the
    magnitude spectra. Reported apart: the waveform correlation, which the interpolation of the OKI and MAME's own filter keep
    below what the spectra suggest. Windows where either side is silent are counted, not compared."""
    import numpy
    ours_all = numpy.frombuffer(pcm.read_bytes(), dtype='<i2').astype(numpy.float64)
    if channels == 1:
        mame, wav_rate = read_wav(wav)
        return _compare_channel(mame, ours_all, wav_rate, rate, seconds)
    mame_channels, wav_rate = read_wav_channels(wav)
    if len(mame_channels) != channels:
        return {'compared': False, 'reason': f'MAME wrote {len(mame_channels)} channels, expected {channels}'}
    results = {name: _compare_channel(mame_channels[index], ours_all[index::channels], wav_rate, rate, seconds, aligned=True)
               for index, name in enumerate(('left', 'right'))}
    return {'compared': all(result.get('compared') for result in results.values()), **results}


def _compare_channel(mame, ours, wav_rate: int, rate: int, seconds: int | None, aligned: bool = False) -> dict:
    import numpy
    if wav_rate != rate:
        return {'compared': False, 'reason': f'MAME wrote {wav_rate} Hz, expected {rate}'}
    # the lag is searched within one frame: 936 samples at the YM2151 rate (steps of 4), 403 at the QSound rate (steps of 2)
    limit, step = (940, 4) if rate > 40000 else (410, 2)
    # the waveform lag within one frame, from the first seconds with sound
    usable = min(len(mame), len(ours))
    best_lag, best_value = 0, -2.0
    probe = slice(rate, min(usable, 6 * rate))
    for lag in range(-limit, limit + 1, step):
        a = mame[probe.start + max(lag, 0):probe.stop + min(lag, 0)] if lag >= 0 else mame[probe.start:probe.stop + lag]
        b = ours[probe.start:probe.stop - max(lag, 0)] if lag >= 0 else ours[probe.start - lag:probe.stop]
        n = min(len(a), len(b))
        if n and a[:n].std() and b[:n].std():
            value = float(numpy.corrcoef(a[:n], b[:n])[0, 1])
            if value > best_value:
                best_lag, best_value = lag, value
    if best_lag >= 0:
        mame, ours = mame[best_lag:], ours
    else:
        mame, ours = mame, ours[-best_lag:]
    windows = min(len(mame), len(ours)) // rate
    if seconds:
        windows = min(windows, seconds)
    levels, cosines, silent = [], [], 0
    total_a = total_b = 0.0
    for index in range(windows):
        a = mame[index * rate:(index + 1) * rate]
        b = ours[index * rate:(index + 1) * rate]
        ra, rb = float(numpy.sqrt((a ** 2).mean())), float(numpy.sqrt((b ** 2).mean()))
        if ra < 1.0 or rb < 1.0:
            silent += 1
            continue
        levels.append(20 * numpy.log10(ra / rb))
        fa, fb = numpy.abs(numpy.fft.rfft(a * numpy.hanning(len(a)))), numpy.abs(numpy.fft.rfft(b * numpy.hanning(len(b))))
        cosines.append(float(fa @ fb / (numpy.linalg.norm(fa) * numpy.linalg.norm(fb))))
        total_a, total_b = total_a + fa ** 2, total_b + fb ** 2
    if not levels:
        return {'compared': False, 'reason': 'no window with sound on both sides', 'windows': windows, 'silent_windows': silent}
    # the spectra averaged over all the windows with sound, and their third-octave bands (power in dB)
    averaged = float(numpy.sqrt(total_a) @ numpy.sqrt(total_b) / (numpy.linalg.norm(numpy.sqrt(total_a)) * numpy.linalg.norm(numpy.sqrt(total_b))))
    frequencies = numpy.fft.rfftfreq(rate, 1.0 / rate)
    low, high = [], []
    edge = 125.0
    while edge * 2 ** (1 / 3) <= 16000:
        upper = edge * 2 ** (1 / 3)
        band = (frequencies >= edge) & (frequencies < upper)
        if band.any() and total_a[band].sum() > 0 and total_b[band].sum() > 0:
            difference = abs(10 * numpy.log10(total_a[band].sum() / total_b[band].sum()))
            (low if upper <= 4000 else high if edge >= 5000 else []).append(float(difference))
        edge = upper
    correlation = float(numpy.corrcoef(mame[:windows * rate][:len(ours)], ours[:windows * rate][:len(mame)])[0, 1])
    result = {'compared': True, 'windows': windows, 'silent_windows': silent, 'lag_samples': best_lag,
            'level_difference_db_median': float(numpy.median(numpy.abs(levels))), 'level_difference_db_max': float(numpy.max(numpy.abs(levels))),
            'spectrum_cosine_min': float(min(cosines)), 'spectrum_cosine_median': float(numpy.median(cosines)),
            'averaged_spectrum_cosine': averaged,
            'third_octave_max_db_below_4khz': max(low) if low else None, 'third_octave_max_db_5_to_16khz': max(high) if high else None,
            'waveform_correlation': correlation}
    if aligned:
        # MAME resamples the QSound chip's 24,038.46 Hz to the 24,038 Hz it was asked for, so the two drift apart by half a sample
        # a second: the whole-signal correlation above is low whatever the sound. Aligned per window (the lag searched within 40
        # samples) the waveforms are compared without that drift.
        values = []
        for index in range(windows):
            first = index * rate
            best = -2.0
            for lag in range(-40, 41):
                a = mame[first + max(lag, 0):first + rate + max(lag, 0)]
                b = ours[first - min(lag, 0):first + rate - min(lag, 0)]
                n = min(len(a), len(b))
                if n > rate // 2 and a[:n].std() > 0 and b[:n].std() > 0:
                    best = max(best, float(numpy.corrcoef(a[:n], b[:n])[0, 1]))
            if best > -2.0:
                values.append(best)
        result['waveform_correlation_aligned_median'] = float(numpy.median(values)) if values else None
        result['waveform_correlation_aligned_min'] = float(min(values)) if values else None
    return result


def compare(name: str, exe: Path, mame: Path, roms: Path, frames: int, step: int, route: str, work: Path, offset: int,
            phase: int = 22, sound: bool = False) -> dict:
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
    qsound = game['machine'] == 'qsound'      # the CPS-1.5 boards: stereo at 24,038 Hz instead of mono at 55,930 Hz
    rate, channels = (24038, 2) if qsound else (AUDIO_RATE, 1)
    extra_game = ['--pcm', str(work / 'game.pcm')] if sound else []
    extra_mame = ['-wavwrite', str(work / 'mame.wav'), '-samplerate', str(rate)] if sound else []
    subprocess.run([str(exe), '--headless', '--frames', str(frames + 8), '--script', str(work / 'route.inputs'), '--capture',
                    str(work / 'game'), '--capture-every', str(step), *extra_game], env=environment, check=True, capture_output=True,
                   timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    mame_run = subprocess.run([str(mame), name, '-rompath', str(roms), '-video', 'none', '-sound', 'none', '-nothrottle',
                               '-skip_gameinfo', '-nomouse', '-autoboot_script', str(lua), '-cfg_directory', str(work / 'cfg'),
                               '-nvram_directory', str(work / 'nvram'), *extra_mame], capture_output=True, text=True, timeout=1800,
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
    if sound:
        summary['sound'] = (compare_sound(work / 'mame.wav', work / 'game.pcm', rate=rate, channels=channels) if (work / 'mame.wav').is_file()
                            else {'compared': False, 'reason': 'MAME wrote no sound file'})
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
    parser.add_argument('--sound', action='store_true', help='also compare the sound: the WAV MAME writes against the PCM of the game')
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'cps1-mame-compare')
    options = parser.parse_args()
    if not options.mame or not options.roms:
        parser.error('--mame and --roms (or RETRO_RECOMP_MAME and RETRO_RECOMP_MAME_ROMS) are required')
    summary = compare(options.set, options.exe, options.mame, options.roms, options.frames, options.step, options.route, options.work,
                      options.offset, options.phase, options.sound)
    print(json.dumps(summary))
    return 0 if summary.get('comparable') else 3


if __name__ == '__main__':
    sys.exit(main())
