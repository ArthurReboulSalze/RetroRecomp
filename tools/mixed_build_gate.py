"""Mixed-build determinism gate: do two exports of one dump compute the same frames?

    python -B tools/mixed_build_gate.py convert SYSTEM DUMP --output DIR [--levels quick extended]
    python -B tools/mixed_build_gate.py compare SYSTEM A.exe B.exe --output DIR [--frames N] [--save-after K]

Two players may hold two exports of the same dump that differ only by their learned path record: more or less code
compiled natively, the rest run by the counted interpreter fallback. A multiplayer lobby may accept such a pair only
on a machine where this gate passes (docs of the multiplayer study, "Nothing breaks silently").

`convert` makes the pair by a route a player can reach: the same dump converted twice, each time with its own empty
scratch library, at two scan levels. `compare` then runs both exports headless, from power-on, with one scripted
input route (both pads), and compares what each machine's headless host records for every frame. It then saves a
quick state after K frames, resumes it in a fresh process and compares again, on each export and across the two.

What is compared is what the machine's own headless host writes (see `Host.covers`): the gate adds no probe to a
game. The counts of native and interpreted work of every run are kept beside the verdict, since the gate proves
nothing when the two exports ran the same code. The native code, CPU fidelity, hardware fidelity, gameplay and
latency measures stay separate: this gate is about none of them, only about two builds agreeing with each other.

Nothing of a dump is read here: the dump is handed to the converter, the exports are started as they are.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>

from state_checks import GUEST_FIELDS, TRACE_METADATA_FIELDS, first_trace_mismatch, run_captured  # noqa: E402

from retrorecomp.random_routes import CONSOLES, Route, Step, long_route, script_text, sega_press  # noqa: E402

SCHEMA = 1
DEFAULT_FRAMES = 6000
SAVE_TRIES = 60
OPENING_END = 700
LATE_STARTS = (1500, 3000)
PHASE_FRAMES = 90


# ---- the comparison (no game, no file: unit-tested) ----

def first_difference(first, second, *, ignore=(), offset=0):
    """Where two per-frame records stop agreeing: None, or the frame (counted from power-on, 1 = after the first
    frame), the columns that differ and their two values. A run that stops early differs at its last frame + 1."""
    if not first or not second:
        return None if not first and not second else {'frame': offset + 1, 'columns': ['length'],
                                                       'first': len(first), 'second': len(second)}
    columns = [key for key in first[0] if key not in ignore]
    index = first_trace_mismatch(first, second, columns)
    if index is None:
        if len(first) == len(second):
            return None
        return {'frame': offset + min(len(first), len(second)) + 1, 'columns': ['length'],
                'first': len(first), 'second': len(second)}
    differing = [key for key in columns if first[index][key] != second[index][key]]
    return {'frame': offset + index + 1, 'columns': differing,
            'first': {key: first[index][key] for key in differing},
            'second': {key: second[index][key] for key in differing}}


def check(name, first, second, *, ignore=(), offset=0):
    """One comparison of the gate, as it is written in the result."""
    difference = first_difference(first, second, ignore=ignore, offset=offset)
    return {'check': name, 'frames': min(len(first), len(second)), 'from_frame': offset + 1,
            'equal': difference is None, 'first_difference': difference}


def refused(name, reason):
    """A state the other export would not load: reported, never counted as agreement or as a failure."""
    return {'check': name, 'frames': 0, 'equal': None, 'refused': reason, 'first_difference': None}


def final_check(name, first, second, *, ignore=()):
    differing = sorted(key for key in set(first) | set(second)
                       if key not in ignore and first.get(key) != second.get(key))
    return {'check': name, 'frames': 1, 'equal': not differing,
            'first_difference': {'columns': differing} if differing else None}


def verdict(checks):
    """Passed only when something was compared and every comparison is equal; a refusal alone proves nothing."""
    compared = [item for item in checks if item['equal'] is not None]
    if any(item['equal'] is False for item in compared):
        return 'failed'
    return 'passed' if compared else 'nothing compared'


def differing_split(first, second):
    """Whether the two exports ran a different native/interpreted split on the route (else the gate is vacuous)."""
    return first != second


# ---- the input route ----

def gate_route(console, frames, *, players=2, limit=None):
    """An authored, reproducible route: leave the title (Start, Select, a confirmation, both pads), then phases of
    movement with a held button for each player, and two late pairs of Start presses. `limit` bounds the changes of player 1's pad (the Master System
    host holds 32 scripted presses)."""
    if console not in CONSOLES:
        raise ValueError(f'No button vocabulary for {console!r}.')
    if frames <= OPENING_END + PHASE_FRAMES:
        raise ValueError(f'The route needs more than {OPENING_END + PHASE_FRAMES} frames.')
    layout = CONSOLES[console]
    main = layout['main']
    start = 'start' if layout.get('start', True) else main[0]
    pads = ({}, {})

    def tap(pad, frame, button, length=4):
        pad[frame] = frozenset((button,))
        pad[frame + length] = frozenset()

    for frame in (150, 400, 560):
        tap(pads[0], frame, start)
    if layout['select']:
        tap(pads[0], 300, layout['select'])
    tap(pads[0], 640, main[0], 6)
    if players > 1:
        for frame in (220, 480, 610):
            tap(pads[1], frame, start)
    opening = len(pads[0]) + 2
    phases = (frames - OPENING_END) // PHASE_FRAMES
    if limit is not None:
        phases = min(phases, limit - opening)
    if phases < 1:
        raise ValueError('The press limit leaves no room for the route.')
    length = (frames - OPENING_END) // phases
    rng = random.Random(f'mixed-build-gate:{console}')
    directions = ('right', 'right', 'up', 'left', 'down', 'right')
    for phase in range(phases):
        frame = OPENING_END + phase * length
        for pad in pads[:players]:
            held = {rng.choice(directions)}
            if rng.random() < 0.75:
                held.add(rng.choice(main))
            pad[frame] = frozenset(held)
    if limit is None:
        # Start twice, 40 frames apart: a pause and its resume in a game, a late title screen and its menu otherwise.
        for frame in LATE_STARTS:
            if frame + 60 < frames:
                tap(pads[0], frame, start)
                tap(pads[0], frame + 40, start)
    pads[0][frames - 1] = frozenset()
    if players > 1:
        pads[1][frames - 1] = frozenset()
    steps, state = [], [frozenset(), frozenset()]
    for frame in sorted({0} | set(pads[0]) | set(pads[1])):
        state = [pads[0].get(frame, state[0]), pads[1].get(frame, state[1])]
        steps.append(Step(frame, state[0], state[1]))
    return Route('mixed-build-gate', console, f'mixed-build-gate:{console}', 0, frames, tuple(steps))


def idle_route(console, frames):
    """No button at all: the game's own attract mode."""
    return Route('idle', console, 'idle', 0, frames, (Step(0, frozenset(), frozenset()),))


def named_route(name, console, frames, *, players=2, limit=None):
    """`gate` (authored, both pads), `idle` (attract mode) or `long` (the converter's reproducible pseudo-random
    route, `random_routes.long_route`, seeded by this tool's name and not by a dump)."""
    if name == 'idle':
        return idle_route(console, frames)
    if name == 'long':
        return long_route(console, 'mixed-build-gate', 0, frames=frames, two_players=players > 1)
    return gate_route(console, frames, players=players, limit=limit)


# ---- the hosts ----

@dataclass
class Run:
    rows: list
    final: dict = field(default_factory=dict)
    split: dict = field(default_factory=dict)
    state: Path | None = None
    refused: str | None = None


def parse_nes_hash(text):
    """The NES host's `--hash-out` lines: `frame key=value …`."""
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if fields:
            rows.append({'frame': fields[0], **dict(item.split('=', 1) for item in fields[1:])})
    return rows


def _timeout(frames):
    return 180 + frames // 5


class NesHost:
    """`--input`, `--hash-out`, `--quick-save` / `--quick-save-frame` / `--quick-load` of the generated NES host."""
    console = 'nes'
    states = True
    limit = None
    ignore = ('frame',)
    # `trace` folds every CPU cycle since the process started: a resumed process starts it again.
    resume_ignore = ('frame', 'trace')
    covers = ('per frame: a running hash of every CPU cycle since power-on (address, value, read or write, data bus, '
              'instruction ends: trace), CPU registers and pending interrupts, the CPU cycle count, a hash of the '
              'work RAM, name tables, sprite memory, palette, cartridge RAM (CHR, work RAM, EEPROM, mapper RAM) and '
              'the frame buffer (mem), a hash of the PPU, APU, mapper and bus state (hw), the picture (pic) and the '
              '48 kHz sound samples of the frame (snd); a resumed run is compared on all of these but trace')

    def run(self, exe, folder, name, frames, route, *, save_after=None, load=None, start=0, interpreter=False):
        from retrorecomp.nes import INTERPRETED, OTHER, SUMMARY
        from retrorecomp.nes_checks import resume_input
        script = folder / f'{name}.input'
        script.write_text(script_text(route), encoding='ascii', newline='\n')
        if start:
            # This host cannot offset its script: the same route, counted again from the state's frame.
            script = resume_input(script, start, folder / f'{name}-resumed.input')
        trace = folder / f'{name}.hash'
        trace.unlink(missing_ok=True)
        command = [exe, '--frames', frames, '--input', script, '--hash-out', trace]
        state = None
        if save_after is not None:
            state = folder / f'{name}.rrstate'
            state.unlink(missing_ok=True)
            command += ['--quick-save', state, '--quick-save-frame', save_after - 1]
        if load is not None:
            command += ['--quick-load', load]
        if interpreter:
            command.append('--interp-only')
        result = run_captured(command, cwd=folder, timeout=_timeout(frames))
        if result.returncode:
            if load is not None:
                return Run([], refused=f'exit {result.returncode}: {(result.stderr or result.stdout).strip()[-200:]}')
            raise RuntimeError(f'{name}: exit {result.returncode}\n{(result.stdout + result.stderr)[-2000:]}')
        rows = parse_nes_hash(trace.read_text(encoding='ascii'))
        output = result.stdout + result.stderr
        summary, interpreted, other = SUMMARY.search(output), INTERPRETED.search(output), OTHER.search(output)
        split = {}
        if summary:
            split = {'cycles': int(summary[2]), 'native_cycles': int(summary[3]),
                     'interpreted_rom_cycles': int(interpreted[1]) if interpreted else 0,
                     'interpreted_ram_cycles': int(interpreted[2]) if interpreted else 0,
                     'interpreted_other_cycles': int(other[1]) if other else 0}
        return Run(rows, dict(rows[-1]) if rows else {}, split, state)


class Console16Host:
    """`--input-script`, `--trace`, `--report`, `--save-state`, `--load-state` and `--frame-offset` of the 16-bit
    headless host (native/console16_main.c). The state is written at the end of a run only."""
    states = True
    limit = None
    ignore = resume_ignore = TRACE_METADATA_FIELDS
    split_keys = ('native_entries', 'interpreted_opcodes', 'retired_interpreted_opcodes', 'rom_fallback_opcodes',
                  'ram_fallback_opcodes', 'audio_native_opcodes', 'audio_interpreted_opcodes')
    covers = ('per frame: the picture, the sound of the frame, the main CPU program counter, status register and '
              'stack pointer, the sound CPU program counter and bus lines, and whether each sound chip was audible; '
              'at the save point and at the last frame: hashes of the CPU, work RAM, video RAM, colour and scroll '
              'RAM, video registers, sound CPU and its RAM, sound-chip timers, cartridge memory and cycle counts')

    def __init__(self, console):
        self.console = console

    def run(self, exe, folder, name, frames, route, *, save_after=None, load=None, start=0, interpreter=False):
        script = folder / f'{name}-inputs.txt'
        # The host refuses a script that names a frame after the end of the run.
        kept = Route(route.name, route.console, route.seed, route.index, route.frames,
                     tuple(step for step in route.steps if step.frame < start + frames))
        script.write_text(script_text(kept), encoding='ascii', newline='\n')
        report, trace = folder / f'{name}.json', folder / f'{name}.csv'
        for stale in (report, trace):
            stale.unlink(missing_ok=True)
        command = [exe, '--frames', frames, '--report', report, '--trace', trace, '--input-script', script]
        state = None
        if save_after is not None:
            if save_after != frames:
                raise ValueError('The 16-bit host writes its state at the end of a run.')
            state = folder / f'{name}.rrstate'
            state.unlink(missing_ok=True)
            command += ['--save-state', state]
        if load is not None:
            command += ['--load-state', load, '--frame-offset', start]
        names = ('GENESIS_FORCE_INTERP', 'RR_SNES_FORCE_INTERP')
        saved = {key: os.environ.pop(key, None) for key in names}
        if interpreter:
            os.environ.update(dict.fromkeys(names, '1'))
        try:
            result = run_captured(command, cwd=folder, timeout=_timeout(frames) * (4 if interpreter else 1))
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None)
                if value is not None:
                    os.environ[key] = value
        if result.returncode:
            if load is not None and result.returncode == 7:
                return Run([], refused='exit 7: the state was not accepted')
            if save_after is not None and result.returncode == 8:
                # A CPU instruction or a sound-CPU bus transaction is suspended at this frame's end: the live host
                # defers F8 until both retire, the headless host only refuses.
                return Run([], refused='exit 8: the machine was not ready to be saved at this frame')
            raise RuntimeError(f'{name}: exit {result.returncode}\n{(result.stdout + result.stderr)[-2000:]}')
        with trace.open(newline='') as file:
            rows = list(csv.DictReader(file))
        data = json.loads(report.read_text(encoding='utf-8'))
        final = {key: data[key] for key in GUEST_FIELDS if key in data}
        split = {key: data[key] for key in self.split_keys if key in data}
        return Run(rows, final, split, state)


class SegaHost:
    """`--press`, `--vdp-trace` and `--dump-frame` of the Master System / Game Gear host, through the converter's
    own `core.probe`. The headless host has no quick-state option, and `--press` drives player 1 only."""
    states = False
    limit = 32
    ignore = ('frame',)
    # The reference interpreter is another engine: the converter's own comparison (validation.vdp_states) reads the
    # video and RAM hashes and the picture, not the stack pointer sampled at the frame's end nor the sound.
    reference_ignore = ('frame', 'sp', 'psg_h', 'psg_nz')
    dumps = ('frame.png', 'frame.png.ram', 'frame.png.vram', 'frame.png.cram', 'frame.png.regs', 'frame.png.cpu',
             'frame.png.psg')
    covers = ('per frame: hashes of the video RAM, colour RAM, video registers and work RAM, the stack pointer, '
              'four video registers, the picture and the sound samples of the frame; at the last frame: the picture, '
              'work RAM, video RAM, colour RAM, video registers, CPU registers and sound-chip state, byte for byte')

    def __init__(self, console):
        self.console = console

    def run(self, exe, folder, name, frames, route, *, save_after=None, load=None, start=0, interpreter=False):
        from retrorecomp.core import probe
        if save_after is not None or load is not None:
            raise ValueError('The Master System / Game Gear headless host has no quick-state option.')
        directory = folder / name
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        # The host holds `limit` presses and drops the rest: hand it only what it keeps.
        result = probe(exe, directory, frames, press=sega_press(route)[:self.limit], reference=interpreter)
        if not result['passed']:
            raise RuntimeError(f"{name}: exit {result['exit_code']}, {result['completed_frames']} frames")
        with (directory / 'vdp.csv').open(newline='') as file:
            rows = list(csv.DictReader(file))
        final = {dump: hashlib.sha256((directory / dump).read_bytes()).hexdigest()
                 for dump in self.dumps if (directory / dump).is_file()}
        final['cpu'] = result.get('final_cpu')
        split = {key: result.get(key) for key in ('interpreter_calls', 'interpreter_cycles', 'total_cycles',
                                                  'interpreter_percent', 'static_percent', 'banked')}
        return Run(rows, final, split)


HOSTS = {'nes': NesHost(), 'md': Console16Host('md'), 'snes': Console16Host('snes'),
         'sms': SegaHost('sms'), 'gg': SegaHost('gg')}


# ---- what the two conversion reports say ----

def export_summary(exe):
    """The scan level, the identities and the native/interpreted counts of the export's own conversion report."""
    summary = {'executable': exe.name, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    reports = [path for path in (exe.parent / 'datas' / 'reports').glob('*/conversion-report.json')]
    for path in reports:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('executable') != exe.name:
            continue
        identity = data.get('simulation_identity') or {}
        summary.update({
            'title': exe.stem, 'scan_level': (data.get('scan') or {}).get('level'),
            'simulation_identity': identity.get('identity'),
            'generated_sources': (identity.get('sources') or {}).get('sha256'),
            'game_stamp': (data.get('export_receipt') or {}).get('game'),
            'native_coverage': data.get('native_coverage'),
            'cpus': [{'id': cpu.get('id'), 'scenarios': [
                {key: row.get(key) for key in ('name', 'frames', 'native', 'interpreted', 'cycles')}
                for row in cpu.get('scenarios') or []]} for cpu in data.get('cpus') or []]})
    return summary


# ---- the gate ----

def compare(system, first, second, output, *, frames=DEFAULT_FRAMES, save_after=None, players=2, interpreter=False,
            route_name='gate'):
    host = HOSTS[system]
    save_after = frames * 2 // 5 if save_after is None else save_after
    if not 0 < save_after < frames:
        raise ValueError('The state is saved inside the run.')
    output.mkdir(parents=True, exist_ok=True)
    scratch = output / 'library'
    scratch.mkdir(exist_ok=True)
    os.environ.update(RETRO_RECOMP_LIBRARY_DIR=str(scratch), SMSRECOMP_LIBRARY_DIR=str(scratch),
                      SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    os.environ.pop('RETRO_RECOMP_LEARNING', None)
    route = named_route(route_name, host.console, frames, players=players, limit=host.limit)
    exports, folders = {}, {}
    for side, source in (('a', first), ('b', second)):
        folders[side] = output / side
        folders[side].mkdir(exist_ok=True)
        # A private copy: battery saves and states land beside it, never beside the player's export.
        exports[side] = folders[side] / ('game' + source.suffix)
        shutil.copy2(source, exports[side])
    result = {'schema': SCHEMA, 'system': system, 'frames': frames, 'save_after': save_after if host.states else None,
              'players_scripted': 1 if isinstance(host, SegaHost) else players,
              'route': {'name': route_name, 'steps': len(route.steps),
                        'sha256': hashlib.sha256(script_text(route).encode('ascii')).hexdigest()},
              'covers': host.covers, 'exports': {'a': export_summary(first), 'b': export_summary(second)},
              'runs': {}, 'checks': []}
    checks, runs = result['checks'], result['runs']

    def run(side, name, count, **options):
        outcome = host.run(exports[side], folders[side], name, count, route, **options)
        runs[f'{side}:{name}'] = {'frames': len(outcome.rows), 'split': outcome.split, 'refused': outcome.refused}
        return outcome

    whole = {side: run(side, 'whole', frames) for side in 'ab'}
    result['same_executable'] = result['exports']['a']['sha256'] == result['exports']['b']['sha256']
    result['split_differs'] = differing_split(whole['a'].split, whole['b'].split)
    checks.append(check('power-on, A against B', whole['a'].rows, whole['b'].rows, ignore=host.ignore))
    checks.append(final_check('last frame, A against B', whole['a'].final, whole['b'].final, ignore=host.ignore))
    if interpreter:
        reference = run('a', 'interpreter', frames, interpreter=True)
        for side in 'ab':
            checks.append(check(f'power-on, {side.upper()} against the interpreter alone',
                                whole[side].rows, reference.rows,
                                ignore=getattr(host, 'reference_ignore', host.ignore)))
    if host.states:
        saved, resumed = {}, {}
        result['save_deferrals'] = []
        for point in range(save_after, min(frames, save_after + SAVE_TRIES)):
            saved = {side: run(side, 'saved', point, save_after=point) for side in 'ab'}
            if not saved['a'].refused and not saved['b'].refused:
                break
            result['save_deferrals'].append({'frame': point, 'a': saved['a'].refused, 'b': saved['b'].refused})
        else:
            raise RuntimeError(f'No state could be saved in {SAVE_TRIES} frames from frame {save_after}.')
        if result['save_deferrals']:
            together = all(bool(item['a']) == bool(item['b']) for item in result['save_deferrals'])
            checks.append({'check': 'the state is ready at the same frames in A and B', 'frames': len(result['save_deferrals']),
                           'equal': together, 'first_difference': None if together else result['save_deferrals']})
        result['save_after'] = save_after = point
        for side in 'ab':
            checks.append(check(f'{side.upper()}: the run that saves against the whole run',
                                saved[side].rows, whole[side].rows[:save_after], ignore=host.ignore))
            resumed[side] = run(side, 'resumed', frames - save_after, load=saved[side].state, start=save_after)
            checks.append(check(f'{side.upper()}: resumed from its own state against its whole run', resumed[side].rows,
                                whole[side].rows[save_after:], ignore=host.resume_ignore, offset=save_after))
            checks.append(final_check(f'{side.upper()}: last frame, resumed against whole',
                                      resumed[side].final, whole[side].final, ignore=host.resume_ignore))
        checks.append(check('resumed A against resumed B', resumed['a'].rows, resumed['b'].rows,
                            ignore=host.resume_ignore, offset=save_after))
        checks.append(final_check('state point, A against B', saved['a'].final, saved['b'].final, ignore=host.ignore))
        states = {side: saved[side].state.read_bytes() for side in 'ab'}
        result['state_files'] = {'bytes': {side: len(states[side]) for side in 'ab'},
                                 'identical': states['a'] == states['b']}
        for writer, reader in ('ab', 'ba'):
            name = f'state of {writer.upper()} resumed in {reader.upper()} against the whole run of {reader.upper()}'
            crossed = run(reader, f'crossed-from-{writer}', frames - save_after, load=saved[writer].state,
                          start=save_after)
            checks.append(refused(name, crossed.refused) if crossed.refused else
                          check(name, crossed.rows, whole[reader].rows[save_after:], ignore=host.resume_ignore,
                                offset=save_after))
    result['verdict'] = verdict(checks)
    if result['verdict'] == 'passed' and not result['split_differs']:
        result['verdict'] = 'passed, but both exports ran the same native/interpreted split'
    (output / 'mixed-build-gate.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def convert(system, dump, output, levels):
    """The same dump converted twice, each time with its own empty scratch library, at two scan levels."""
    produced = []
    for side, level in zip('ab', levels):
        library, games = output / f'library-{side}', output / side
        for folder in (library, games):
            shutil.rmtree(folder, ignore_errors=True)
        library.mkdir(parents=True)
        environment = dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(library), SDL_VIDEODRIVER='dummy',
                           SDL_AUDIODRIVER='dummy')
        environment.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
        command = [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), 'batch', str(dump), '--system', system,
                   '--output', str(games), '--scan-level', level, '--no-shared-base', '--no-online-cover', '--no-cover',
                   '--no-compress', '--jobs', '1']
        with (output / f'convert-{side}.log').open('w', encoding='utf-8') as log:
            done = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if done.returncode:
            raise RuntimeError(f'Conversion {side} ({level}) failed: see {output / f"convert-{side}.log"}')
        games_found = [path for path in games.glob('*/*') if path.is_file() and path.suffix in ('.exe', '')]
        if len(games_found) != 1:
            raise RuntimeError(f'Conversion {side}: {len(games_found)} games published.')
        produced.append(games_found[0])
    return produced


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('convert', help='Convert one dump twice, at two scan levels, with empty scratch libraries.')
    make.add_argument('system', choices=sorted(HOSTS))
    make.add_argument('dump', type=Path)
    make.add_argument('--output', type=Path, required=True)
    make.add_argument('--levels', nargs=2, default=('quick', 'extended'), metavar=('A', 'B'))
    gate = commands.add_parser('compare', help='Run two exports of one dump and compare them frame by frame.')
    gate.add_argument('system', choices=sorted(HOSTS))
    gate.add_argument('first', type=Path)
    gate.add_argument('second', type=Path)
    gate.add_argument('--output', type=Path, required=True)
    gate.add_argument('--frames', type=int, default=DEFAULT_FRAMES)
    gate.add_argument('--save-after', type=int, help='Frames before the quick state (default: two fifths of the run).')
    gate.add_argument('--players', type=int, choices=(1, 2), default=2)
    gate.add_argument('--route', choices=('gate', 'idle', 'long'), default='gate',
                      help='gate: authored, both pads (default); idle: no button, the attract mode; long: the '
                           "converter's reproducible pseudo-random route.")
    gate.add_argument('--interpreter', action='store_true',
                      help='Also compare both exports with export A run by its interpreter alone.')
    args = parser.parse_args()
    if args.command == 'convert':
        for path in convert(args.system, args.dump.resolve(), args.output.resolve(), args.levels):
            print(path)
        return 0
    result = compare(args.system, args.first.resolve(), args.second.resolve(), args.output.resolve(),
                     frames=args.frames, save_after=args.save_after, players=args.players, interpreter=args.interpreter,
                     route_name=args.route)
    print(json.dumps({key: result[key] for key in ('system', 'frames', 'save_after', 'same_executable',
                                                    'split_differs', 'runs', 'checks', 'verdict')}, indent=2))
    return 0 if result['verdict'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
