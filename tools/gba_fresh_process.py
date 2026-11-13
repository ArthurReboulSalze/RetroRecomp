"""The Game Boy Advance player's quick state and cartridge save survive the end of the process (gates G6 and G7).

Everything runs on a converted player (`--exe`), hidden, silent and bounded (SDL dummy drivers, `RETRORECOMP_HOST_TEST_FRAMES`),
in a scratch folder of its own that holds a copy of the executable and its `datas` (the delivered executable is never run in
place). Two checks, each of them with two or three separate processes:

  state   process A runs a key script to frame N, saves the quick state (what F8 does), runs M frames more and keeps its last
          picture; process B is a fresh process of the same folder: it loads the state (what F9 does) at its second frame, counts
          from N afterwards, runs the same M frames and keeps its last picture. The two pictures must have the same SHA-256.
          A control process that never loads the state and runs as long as B must give another picture, otherwise the picture
          would not tell the state from nothing and the check says so ("weak").
  refusals  the state file process A saved is damaged in eight ways (emptied, cut, grown, header and identity inverted, noise, one byte in
          the middle) and a fresh process tries to load each, then one tries to load none: every one must say `quick state refused` (the
          missing one nothing), end with code 0 as a run that never loaded a state (same picture and frame count as the control), and the
          missing one must create no state file. A byte inverted in the middle is reported, not required (memory has no checksum).
  save    process A plays a key script that makes the game write its cartridge save and ends; the save file is on disk, of the
          size the game keeps, and not one single byte value. Process B, fresh, starts with that file and plays a second script
          (to the file-select screen, say); a control process with no file plays the same second script. B's last picture must
          differ from the control's: the save was read back and the game shows it.

The headless player has no key for F8 and F9, so the state check needs the test switch `RETRORECOMP_GBA_STATE=save@N` /
`load@K=N` that native/gba_machine.cpp reads (an executable converted before it existed says so and the check stops).

    python -B tools/gba_fresh_process.py state --exe GAME.exe --keys ROUTE.keys [--save-frame 600] [--more 120]
    python -B tools/gba_fresh_process.py refusals --exe GAME.exe --keys ROUTE.keys [--save-frame 600] [--more 120]
    python -B tools/gba_fresh_process.py save  --exe GAME.exe --keys-a WRITE.keys --frames-a 3000 --keys-b SHOW.keys --frames-b 900
    python -B tools/gba_fresh_process.py keys  --out ROUTE.keys --header "what it reaches" --events "300:8,304:0" --pulse 1,700,6000,50,4

Key scripts are the engine's own format: one `frame,0xKEYS` per line, KEYS being KEYINPUT (active low: a bit at 0 is a pressed
button), the value holding until the next line. `keys` writes one from pressed-button masks (A=1 B=2 Select=4 Start=8 Right=0x10
Left=0x20 Up=0x40 Down=0x80 R=0x100 L=0x200) so that a route is numbers and nothing else.

What this shows: that a state and a save written by one process are read back by another, to the picture. It is neither a
gameplay validation nor a fidelity measure, and it says nothing about a save from real hardware (the saves here are the player's
own). The report holds hashes and counts, never a picture or a byte of the cartridge; the pictures stay in the work folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK = ROOT / '.build' / 'gba-fresh-process'
REPORT_VERSION = 1
KEYINPUT_MASK = 0x3FF
WIDTH, HEIGHT = 240, 160
BUTTONS = {'a': 0x1, 'b': 0x2, 'select': 0x4, 'start': 0x8, 'right': 0x10, 'left': 0x20, 'up': 0x40, 'down': 0x80, 'r': 0x100,
           'l': 0x200}
# Test switches of the player that an environment inherited from a shell must not leak into a check.
PLAYER_SWITCHES = ('RETRORECOMP_GBA_INPUT', 'RETRORECOMP_GBA_DUMP', 'RETRORECOMP_GBA_STATE', 'RETRORECOMP_GBA_SELFTEST',
                   'RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_HOST_TEST_NO_AUDIO', 'RETRORECOMP_HOST_TEST_FILTER')
STATS_LINE = re.compile(r'\[host\] frames=(\d+).*?interpreted=(\d+)')
STATE_LINE = re.compile(r'\[state\] (save|load) at frame (\d+) (ok|FAILED)')


class CheckError(Exception):
    """A check that could not be run (a missing file, a player that does not know the switch); never a verdict."""


# ------------------------------------------------------------------------------------------------------------- key scripts
def keyinput_from_pressed(pressed: int) -> int:
    return KEYINPUT_MASK & ~pressed


def key_script_text(events: list[tuple[int, int]], header: str = '') -> str:
    """`events` are (frame, pressed buttons mask); frame 0 is released unless the list says otherwise."""
    lines = [f'# {line}'.rstrip() for line in header.splitlines()]
    lines.append('# frame,keyinput_active_low (the value holds until the next line)')
    if not events or min(frame for frame, _ in events) > 0:
        lines.append(f'0,0x{KEYINPUT_MASK:04x}')
    last = -1
    for frame, pressed in sorted(events):
        if frame < 0:
            raise ValueError(f'negative frame {frame}')
        if frame == last:
            raise ValueError(f'two events on frame {frame}')
        last = frame
        lines.append(f'{frame},0x{keyinput_from_pressed(pressed):04x}')
    return '\n'.join(lines) + '\n'


def pulse_events(pressed: int, start: int, end: int, every: int, width: int) -> list[tuple[int, int]]:
    """The button pressed for `width` frames every `every` frames from `start` while the frame is below `end`."""
    if every <= width or width < 1 or start < 0:
        raise ValueError('a pulse needs 1 <= width < every and start >= 0')
    events: list[tuple[int, int]] = []
    frame = start
    while frame < end:
        events += [(frame, pressed), (frame + width, 0)]
        frame += every
    return events


def parse_events(text: str) -> list[tuple[int, int]]:
    """`300:8,304:0` (frame:pressed mask, a number or 0x...), the way the panel's lang_check tool writes them."""
    events = []
    for item in filter(None, (part.strip() for part in text.split(','))):
        frame, _, mask = item.partition(':')
        if not mask:
            raise ValueError(f'event {item!r} is not frame:mask')
        events.append((int(frame, 0), int(mask, 0) & KEYINPUT_MASK))
    return events


def read_key_script(path: Path) -> list[tuple[int, int]]:
    """The (frame, KEYINPUT) pairs of a script, with the checks the player does not make (it skips what it cannot read)."""
    pairs = []
    for number, raw in enumerate(Path(path).read_text(encoding='ascii').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'(\d+),(0[xX][0-9a-fA-F]+|[0-9]+)', line)
        if not match:
            raise CheckError(f'{path}:{number}: not "frame,0xKEYS": {raw!r}')
        keys = int(match.group(2), 0)
        if keys > KEYINPUT_MASK:
            raise CheckError(f'{path}:{number}: KEYINPUT 0x{keys:x} has bits above the ten buttons')
        pairs.append((int(match.group(1)), keys))
    frames = [frame for frame, _ in pairs]
    if frames != sorted(frames):
        raise CheckError(f'{path}: the frames are not in increasing order')
    return pairs


# ---------------------------------------------------------------------------------------------------------- pictures, saves
def ppm_pixels(path: Path) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    match = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', data)
    if not match:
        raise CheckError(f'{path} is not a binary PPM')
    width, height = int(match.group(1)), int(match.group(2))
    pixels = data[match.end():]
    if len(pixels) != width * height * 3:
        raise CheckError(f'{path}: {len(pixels)} picture bytes for {width}x{height}')
    return width, height, pixels


def picture_sha256(path: Path) -> str:
    """The hash of the pixels, the header left out."""
    return hashlib.sha256(ppm_pixels(path)[2]).hexdigest()


def write_png(path: Path, width: int, height: int, rgb: bytes, scale: int = 2) -> None:
    """A plain PNG (no Pillow needed), the picture repeated `scale` times in both directions."""
    rows = []
    for y in range(height):
        row = rgb[y * width * 3:(y + 1) * width * 3]
        line = b''.join(row[x * 3:x * 3 + 3] * scale for x in range(width))
        rows.extend([b'\x00' + line] * scale)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))

    header = struct.pack('>IIBBBBB', width * scale, height * scale, 8, 2, 0, 0, 0)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b''.join(rows), 6)) +
                           chunk(b'IEND', b''))


def save_stats(data: bytes) -> dict:
    """What a cartridge save looks like: its size, how many different byte values, the commonest one and how many bytes differ
    from it. A file that holds one value only (all 0xFF or all 0x00) has nothing a game wrote."""
    counts = Counter(data)
    fill, fill_count = counts.most_common(1)[0] if data else (0, 0)
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'distinct_values': len(counts), 'fill': fill,
            'bytes_differing_from_fill': len(data) - fill_count, 'trivial': len(counts) <= 1}


# -------------------------------------------------------------------------------------------------------- the player's run
@dataclass
class RunResult:
    label: str
    returncode: int
    frames: int | None = None
    interpreted: int | None = None
    state_lines: list[tuple[str, int, bool]] = field(default_factory=list)
    picture_sha256: str | None = None
    picture: str | None = None
    stderr_tail: str = ''
    refused: bool = False             # the player said "quick state refused" (a state it read and did not accept)

    def state_ok(self, kind: str) -> bool:
        return any(k == kind and ok for k, _, ok in self.state_lines)

    def as_dict(self) -> dict:
        return {'label': self.label, 'returncode': self.returncode, 'frames': self.frames, 'interpreted': self.interpreted,
                'state_lines': [f'{k}@{frame} {"ok" if ok else "FAILED"}' for k, frame, ok in self.state_lines],
                'picture_sha256': self.picture_sha256, **({'refused': True} if self.refused else {})}


def parse_player_output(text: str) -> tuple[int | None, int | None, list[tuple[str, int, bool]]]:
    stats = STATS_LINE.search(text)
    states = [(m.group(1), int(m.group(2)), m.group(3) == 'ok') for m in STATE_LINE.finditer(text)]
    return (int(stats.group(1)) if stats else None, int(stats.group(2)) if stats else None, states)


def state_switch(save_frame: int | None = None, load_frame: int | None = None, resume: int | None = None) -> str:
    """The value of RETRORECOMP_GBA_STATE: `save@N`, `load@K=N` (load at frame K, count from N afterwards), or both."""
    steps = []
    if save_frame is not None:
        steps.append(f'save@{save_frame}')
    if load_frame is not None:
        steps.append(f'load@{load_frame}' + (f'={resume}' if resume is not None else ''))
    return ','.join(steps)


def player_environment(folder: Path, frames: int, keys: Path | None, dump: Path, state: str = '') -> dict:
    env = {k: v for k, v in os.environ.items() if k not in PLAYER_SWITCHES}
    env.update(RETRORECOMP_HOST_TEST_FRAMES=str(frames), RETRORECOMP_HOST_TEST_NO_AUDIO='1', RETRORECOMP_GBA_DUMP=str(Path(dump).resolve()),
               SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    if keys is not None:
        env['RETRORECOMP_GBA_INPUT'] = str(Path(keys).resolve())      # the player runs in the check's folder, not in ours
    if state:
        env['RETRORECOMP_GBA_STATE'] = state
    return env


def run_player(exe: Path, folder: Path, label: str, frames: int, keys: Path | None, state: str = '', timeout: int = 1800) -> RunResult:
    """One process: hidden (no console window, dummy video and audio), bounded by the frame limit, killed at the timeout."""
    dump = folder / f'{label}.ppm'
    if dump.exists():
        dump.unlink()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        done = subprocess.run([str(exe)], cwd=folder, env=player_environment(folder, frames, keys, dump, state), capture_output=True,
                              text=True, errors='replace', timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired as error:
        raise CheckError(f'{label}: the player did not end within {timeout} s (killed)') from error
    text = (done.stdout or '') + (done.stderr or '')
    reached, interpreted, states = parse_player_output(text)
    result = RunResult(label, done.returncode, reached, interpreted, states, stderr_tail='\n'.join(text.strip().splitlines()[-6:]),
                       refused='quick state refused' in text)
    if dump.is_file():
        result.picture = str(dump)
        result.picture_sha256 = picture_sha256(dump)
        width, height, pixels = ppm_pixels(dump)
        write_png(folder / f'{label}.png', width, height, pixels)
    return result


def prepare_folder(exe: Path, folder: Path) -> Path:
    """A clean folder with a copy of the executable; its `datas` starts empty."""
    if not exe.is_file():
        raise CheckError(f'{exe} is not a file')
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    copy = folder / 'game.exe'
    shutil.copy2(exe, copy)
    return copy


def saves_in(folder: Path) -> list[Path]:
    return sorted((folder / 'datas' / 'saves').glob('*.sav'))


def states_in(folder: Path) -> list[Path]:
    return sorted((folder / 'datas' / 'states').glob('*.rrstate'))


# ---------------------------------------------------------------------------------------------------------------- verdicts
def state_verdict(a: RunResult, b: RunResult, control: RunResult | None, save_frame: int, state_file_size: int | None) -> dict:
    """The state check's decision from what the three processes said. Pure: no file, no process."""
    problems: list[str] = []          # what stops the check from being a check (verdict "error")
    if not a.state_lines and not b.state_lines:
        problems.append('the player printed no [state] line: it was built before RETRORECOMP_GBA_STATE, convert it again')
    else:
        if not a.state_ok('save'):
            problems.append('process A did not save the state')
        if not b.state_ok('load'):
            problems.append('process B did not load the state')
        if not state_file_size:
            problems.append('no state file on disk')
    for run in (a, b):
        if run.returncode != 0:
            problems.append(f'process {run.label} ended with code {run.returncode}')
        if run.picture_sha256 is None:
            problems.append(f'process {run.label} left no picture')
    if a.frames is not None and b.frames is not None and a.frames != b.frames:
        problems.append(f'the processes ended at frame {a.frames} and {b.frames}, so the pictures are not of the same moment')
    equal = a.picture_sha256 is not None and a.picture_sha256 == b.picture_sha256
    control_differs = None
    if control is not None and control.picture_sha256 and a.picture_sha256:
        control_differs = control.picture_sha256 != a.picture_sha256
    if problems:
        verdict = 'error'
    elif not equal:
        verdict = 'fail'
        problems.append('the picture of the restored process differs from the one of the process that saved the state')
    elif control_differs is False:
        verdict = 'weak'
        problems.append('a run that never loaded the state gives the same picture: the picture cannot tell the state from nothing')
    else:
        verdict = 'pass'
    return {'verdict': verdict, 'pictures_equal': equal, 'control_differs': control_differs, 'problems': problems}


def save_verdict(sav_a: dict | None, sav_fresh: dict | None, sav_b_after: dict | None, pic_b: str | None, pic_control: str | None,
                 runs: list[RunResult]) -> dict:
    """The save check's decision. `sav_*` are `save_stats` dicts: A after it ended, the control's after its own run (what a
    game with no save leaves), B after it ended. Pure."""
    problems: list[str] = []
    for run in runs:
        if run.returncode != 0:
            problems.append(f'process {run.label} ended with code {run.returncode}')
        if run.picture_sha256 is None:
            problems.append(f'process {run.label} left no picture')
    if sav_a is None:
        problems.append('process A left no save file')
    elif sav_a['trivial']:
        problems.append('the save file holds one byte value only: the game wrote nothing')
    elif sav_fresh is not None and sav_a['sha256'] == sav_fresh['sha256']:
        problems.append('the save of A is the same as the file of a run that played nothing')
    differs = pic_b is not None and pic_control is not None and pic_b != pic_control
    if pic_b is not None and pic_control is not None and not differs:
        problems.append('B and the control show the same picture: the save was not read back, or the second script does not show it')
    verdict = 'pass' if not problems else 'fail'
    return {'verdict': verdict, 'save_read_back_in_picture': differs, 'problems': problems,
            'save_unchanged_by_b': None if sav_a is None or sav_b_after is None else sav_a['sha256'] == sav_b_after['sha256']}


def build_report(kind: str, exe: Path, results: dict, verdict: dict, parameters: dict) -> dict:
    """The JSON report: hashes, counts and verdicts, no picture and no byte of a cartridge."""
    exe_hash = hashlib.sha256(Path(exe).read_bytes()).hexdigest() if Path(exe).is_file() else None
    return {'report_version': REPORT_VERSION, 'check': kind, 'exe': Path(exe).name, 'exe_sha256': exe_hash, 'parameters': parameters,
            'runs': {name: value.as_dict() if isinstance(value, RunResult) else value for name, value in results.items()},
            'result': verdict}


def render_text(report: dict) -> str:
    lines = [f'gba_fresh_process {report["check"]}: {report["result"]["verdict"].upper()}  ({report["exe"]})']
    for name, run in report['runs'].items():
        if 'picture_sha256' in run:
            sha = (run['picture_sha256'] or 'no picture')[:16]
            lines.append(f'  {name:<8} frames={run["frames"]} interpreted={run["interpreted"]} picture={sha} {" ".join(run["state_lines"])}'.rstrip())
        else:
            lines.append(f'  {name:<8} size={run.get("size")} distinct={run.get("distinct_values")} '
                         f'differing_from_fill={run.get("bytes_differing_from_fill")} sha={str(run.get("sha256"))[:16]}')
    for key, value in report['result'].items():
        if key not in ('verdict', 'problems'):
            lines.append(f'  {key}: {value}')
    lines.extend(f'  PROBLEM: {problem}' for problem in report['result']['problems'])
    return '\n'.join(lines)


# ---------------------------------------------------------------------------------------------------------------- the checks
def run_state_check(exe: Path, work: Path, keys: Path | None, save_frame: int, more: int, load_frame: int, timeout: int) -> dict:
    if load_frame < 1 or load_frame >= save_frame:
        raise CheckError('--load-frame must be at least 1 and below --save-frame')
    if keys is not None:
        read_key_script(keys)
    folder = work / 'state'
    game = prepare_folder(exe, folder)
    a = run_player(game, folder, 'A', save_frame + more, keys, state_switch(save_frame=save_frame), timeout)
    states = states_in(folder)
    size = states[0].stat().st_size if states else None
    b = run_player(game, folder, 'B', load_frame + more, keys, state_switch(load_frame=load_frame, resume=save_frame), timeout)
    control = run_player(game, folder, 'control', load_frame + more, keys, '', timeout) if a.picture_sha256 else None
    verdict = state_verdict(a, b, control, save_frame, size)
    verdict['state_file_bytes'] = size
    runs = {'A': a, 'B': b}
    if control:
        runs['control'] = control
    return build_report('state', exe, runs, verdict,
                        {'keys': keys.name if keys else None, 'save_frame': save_frame, 'more': more, 'load_frame': load_frame})


def damaged_states(data: bytes) -> dict[str, tuple[bytes, bool]]:
    """{name: (bytes, required)} the damaged forms of a quick state. `required`: the player must refuse it (it breaks the container: magic, identity or
    size). The one byte flipped in the middle is only reported: a state of memory has no checksum to refuse it by."""
    noise = bytearray()
    block = 0
    while len(noise) < len(data):
        noise += hashlib.sha256(b'gba-fresh-process noise %d' % block).digest()
        block += 1
    middle = bytearray(data)
    middle[len(data) // 2] ^= 0xFF
    return {
        'emptied': (b'', True),
        'cut in half': (data[: len(data) // 2], True),
        'last byte missing': (data[:-1], True),
        'grown by 64 bytes': (data + bytes(64), True),
        'first 16 bytes inverted': (bytes(byte ^ 0xFF for byte in data[:16]) + data[16:], True),
        'cartridge identity damaged': (data[:8] + bytes(byte ^ 0xFF for byte in data[8:28]) + data[28:], True),
        'noise of the same size': (bytes(noise[: len(data)]), True),
        'one byte inverted in the middle': (bytes(middle), False),
    }


def refusal_verdict(control: RunResult, variants: dict[str, tuple[RunResult, bool]], created: list[str]) -> dict:
    """A state the player must not accept: it said so (`quick state refused`, the load failed), went on from where a fresh start is (the picture
    and the frame count of a run that never loaded) and ended with code 0; a missing state is not an error and creates nothing."""
    problems: list[str] = []
    stopping: list[str] = []          # what stops the check from being a check (verdict "error")
    table: dict[str, dict] = {}
    if control.picture_sha256 is None or control.returncode != 0:
        stopping.append('the control process (no state loaded) did not end with a picture')
    if not any(kind == 'load' for run, _ in variants.values() for kind, _, _ in run.state_lines):
        stopping.append('the player printed no [state] line: it was built before RETRORECOMP_GBA_STATE, convert it again')
    for name, (run, required) in variants.items():
        failed = any(kind == 'load' and not ok for kind, _, ok in run.state_lines)
        same = run.picture_sha256 is not None and run.picture_sha256 == control.picture_sha256 and run.frames == control.frames
        row = {'required': required, 'load_failed': failed, 'refused_with_a_message': run.refused, 'picture_equals_a_fresh_start': same,
               'exit_code': run.returncode}
        row['ok'] = failed and same and run.returncode == 0 and (run.refused or name == 'missing')
        table[name] = row
        if required and not row['ok']:
            problems.append(f'{name}: not refused as it should be ({row})')
    if created:
        problems.append(f'a load of a missing state created {created}')
    verdict = 'error' if stopping else ('fail' if problems else 'pass')
    return {'verdict': verdict, 'variants': table, 'files_created_by_the_missing_state': created, 'problems': stopping + problems}


def run_refusal_check(exe: Path, work: Path, keys: Path | None, save_frame: int, more: int, load_frame: int, timeout: int) -> dict:
    """Damaged states are refused and a missing state creates nothing (gate G6): process A saves a state, then fresh processes try to load it damaged
    in eight ways and try to load none. Every one must end as a run that never loaded a state."""
    if load_frame < 1 or load_frame >= save_frame:
        raise CheckError('--load-frame must be at least 1 and below --save-frame')
    if keys is not None:
        read_key_script(keys)
    folder = work / 'refusals'
    game = prepare_folder(exe, folder)
    a = run_player(game, folder, 'A', save_frame + more, keys, state_switch(save_frame=save_frame), timeout)
    states = states_in(folder)
    if not states or not a.state_ok('save'):
        raise CheckError('process A saved no state (a player built before RETRORECOMP_GBA_STATE, or a game that cannot save one)')
    path = states[0]
    original = path.read_bytes()
    control = run_player(game, folder, 'control', load_frame + more, keys, '', timeout)
    variants: dict[str, tuple[RunResult, bool]] = {}
    for name, (data, required) in damaged_states(original).items():
        path.write_bytes(data)
        label = 'D-' + re.sub(r'[^a-z0-9]+', '-', name)
        variants[name] = (run_player(game, folder, label, load_frame + more, keys, state_switch(load_frame=load_frame, resume=save_frame), timeout),
                          required)
    for leftover in states_in(folder):
        leftover.unlink()
    missing = run_player(game, folder, 'missing', load_frame + more, keys, state_switch(load_frame=load_frame, resume=save_frame), timeout)
    variants['missing'] = (missing, True)
    created = [file.name for file in states_in(folder)]
    verdict = refusal_verdict(control, variants, created)
    verdict['state_file_bytes'] = len(original)
    runs = {'A': a, 'control': control, **{name: run for name, (run, _) in variants.items()}}
    return build_report('refusals', exe, runs, verdict,
                        {'keys': keys.name if keys else None, 'save_frame': save_frame, 'more': more, 'load_frame': load_frame})


def sav_of(folder: Path) -> tuple[dict | None, Path | None]:
    files = saves_in(folder)
    return (save_stats(files[0].read_bytes()), files[0]) if files else (None, None)


def run_save_check(exe: Path, work: Path, keys_a: Path, frames_a: int, keys_b: Path, frames_b: int, timeout: int) -> dict:
    read_key_script(keys_a)
    read_key_script(keys_b)
    folder = work / 'save'
    game = prepare_folder(exe, folder)
    a = run_player(game, folder, 'A', frames_a, keys_a, '', timeout)
    sav_a, sav_path = sav_of(folder)
    sav_bytes = sav_path.read_bytes() if sav_path else b''
    if sav_path:
        shutil.copy2(sav_path, work / 'save-A.sav')
    b = run_player(game, folder, 'B', frames_b, keys_b, '', timeout)
    sav_b, _ = sav_of(folder)
    control_folder = work / 'save-control'
    control_game = prepare_folder(exe, control_folder)
    control = run_player(control_game, control_folder, 'control', frames_b, keys_b, '', timeout)
    sav_fresh, _ = sav_of(control_folder)
    verdict = save_verdict(sav_a, sav_fresh, sav_b, b.picture_sha256, control.picture_sha256, [a, b, control])
    if sav_path:
        verdict['save_file'] = sav_path.name
    runs = {'A': a, 'B': b, 'control': control, 'save A': sav_a or {}, 'save fresh': sav_fresh or {}, 'save after B': sav_b or {}}
    return build_report('save', exe, runs, verdict, {'keys_a': keys_a.name, 'frames_a': frames_a, 'keys_b': keys_b.name,
                                                      'frames_b': frames_b, 'save_bytes': len(sav_bytes)})


# --------------------------------------------------------------------------------------------------------- the command line
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--exe', type=Path, required=True, help='the converted player (copied, never run in place)')
        p.add_argument('--work', type=Path, default=DEFAULT_WORK, help='scratch folder (default .build/gba-fresh-process)')
        p.add_argument('--timeout', type=int, default=1800, help='seconds before a process is killed')
        p.add_argument('--json', type=Path, help='where to write the report (default WORK/report-<check>.json)')

    state = sub.add_parser('state', help='a quick state saved by one process is loaded by another')
    common(state)
    state.add_argument('--keys', type=Path, help='key script played by every process (a route into play)')
    state.add_argument('--save-frame', type=int, default=600)
    state.add_argument('--more', type=int, default=120, help='frames run after the save (A) and after the load (B)')
    state.add_argument('--load-frame', type=int, default=2, help='frame at which the fresh process loads the state')
    refusals = sub.add_parser('refusals', help='damaged states are refused, a missing state creates nothing')
    common(refusals)
    refusals.add_argument('--keys', type=Path, help='key script played by every process (a route into play)')
    refusals.add_argument('--save-frame', type=int, default=600)
    refusals.add_argument('--more', type=int, default=120)
    refusals.add_argument('--load-frame', type=int, default=2)
    save = sub.add_parser('save', help='a cartridge save written by one process is read back by another')
    common(save)
    save.add_argument('--keys-a', type=Path, required=True)
    save.add_argument('--frames-a', type=int, required=True)
    save.add_argument('--keys-b', type=Path, required=True)
    save.add_argument('--frames-b', type=int, required=True)
    keys = sub.add_parser('keys', help='write a key script from pressed-button masks')
    keys.add_argument('--out', type=Path, required=True)
    keys.add_argument('--header', default='', help='comment lines at the top (what the route reaches)')
    keys.add_argument('--events', default='', help='frame:mask,frame:mask (mask 0 releases)')
    keys.add_argument('--pulse', action='append', default=[], metavar='MASK,START,END,EVERY,WIDTH',
                      help='a button pressed WIDTH frames every EVERY frames from START to END (repeatable)')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'keys':
            events = parse_events(args.events)
            for spec in args.pulse:
                events += pulse_events(*[int(x, 0) for x in spec.split(',')])
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(key_script_text(events, args.header), encoding='ascii', newline='\n')
            print(f'{args.out}: {len(events)} events')
            return 0
        exe = args.exe.resolve()
        if not exe.is_file():
            raise CheckError(f'{exe} is not a file')
        work = args.work.resolve()
        work.mkdir(parents=True, exist_ok=True)
        if args.command == 'state':
            report = run_state_check(exe, work, args.keys, args.save_frame, args.more, args.load_frame, args.timeout)
        elif args.command == 'refusals':
            report = run_refusal_check(exe, work, args.keys, args.save_frame, args.more, args.load_frame, args.timeout)
        else:
            report = run_save_check(exe, work, args.keys_a, args.frames_a, args.keys_b, args.frames_b, args.timeout)
    except (CheckError, ValueError) as error:
        print(f'gba_fresh_process: {error}', file=sys.stderr)
        return 2
    target = args.json or work / f'report-{report["check"]}.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(render_text(report))
    print(f'report: {target}')
    return {'pass': 0, 'fail': 1}.get(report['result']['verdict'], 2)


if __name__ == '__main__':
    sys.exit(main())
