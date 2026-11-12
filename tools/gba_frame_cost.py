"""Host cost per frame of the Game Boy Advance engine, two probe builds side by side (A and B), on one pinned core.

    python -B tools/gba_frame_cost.py run --a EXE --b EXE --rom ROM --bios BIOS [--scenario generic] [--frames 3600]
                                          [--runs 5] [--core N] [--work DIR] [--results FILE] [--quiet-confirmed]
                                          [--timeout SECONDS] [--dry-run]
    python -B tools/gba_frame_cost.py report FILE

EXE is a headless probe host (`gba_probe.exe`) that a conversion keeps in `.build/gba_<title>_<sha12>_<engine8>/host-build/`
when it runs with --keep-build; ROM is your own cartridge dump and BIOS your own `gba_bios.bin`, both only read. Every run
happens in a fresh folder under --work (default `.build/gba-frame-cost` of the repository); no window ever appears (SDL dummy
video and audio drivers, `--no-window`, CREATE_NO_WINDOW, output to a file) and nothing waits in a busy loop (the child is
waited for with a timeout).

What it measures: the headless probe has no frame limiter, and when a bounded run ends the engine prints one line,
`bounded_run start_frame= end_frame= ... seconds= ...`, where `seconds` is a steady-clock span of the frame loop alone
(start-up and the dumps at exit are outside it). The cost per frame is `seconds / (end_frame - start_frame)`: the divisor is
the number of frames the engine reports having run, not the number asked for. As a cross-check the
tool also keeps the process's own wall time and the wall time of a 0-frame run of the same build (start-up and exit), and
reports (wall - start-up) per frame beside the engine's own figure.

So it is the cost of the engine's machine: the generated code, the interpreter bridge, the picture and sound models and the
input replay. It is host time only, on the machine it ran on. It is NOT the presentation, the audio device, the host kit or
the frame pacing, and it says nothing about the native code share, CPU fidelity, hardware fidelity, gameplay validation or
physical latency: those five measures stay separate and are reported elsewhere (the conversion report). The interpreter
instructions of coverage.json are printed only so that a cost change can be read next to the fallback that was counted.

Both builds run the converter's own key script of the scenario (`gba_build.input_script`, deterministic), with the converter's
guest-timed clock, so A and B do the same work. After every run the guest cycle count, the memory hash and the CPU hash of the
`vblank_snapshot` line are compared: when they differ between A and B (or are missing), the tool refuses to compare the two
builds (`work_identical` false) and says why; the raw values are still saved.

Method (as `tools/startup_cost.py` and `docs/RUNTIME_PERFORMANCE.md`): one core (`--core N`, the `pin` of
`tools/toolchain_compare.py`, which also raises the priority), one dropped warm-up run per build, A and B interleaved (A B A
B ...), best of N and the median, raw values kept. THE NUMBERS ARE VALID ONLY ON A QUIET PC: stop conversions, builds and
other agents first and ask the maintainer, who says when the PC is quiet. The JSON records `quiet_pc_confirmed: false` unless
`--quiet-confirmed` is passed, and the output then says it is not a cost measurement.
`--dry-run` prints the plan and the command lines and runs nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.conversion_common import probe_environment  # noqa: E402
from retrorecomp.gba_build import RTC_EPOCH, input_script  # noqa: E402
from tools.toolchain_compare import pin  # noqa: E402

DEFAULT_WORK = ROOT / '.build' / 'gba-frame-cost'
SCENARIOS = ('generic', 'boot')
SCHEMA = 1
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

QUIET_BANNER = ('THE NUMBERS ARE VALID ONLY ON A QUIET PC: no conversion, build, agent or other heavy process may run. '
                'The maintainer says when the PC is quiet; pass --quiet-confirmed only with his word.')
HONESTY = ('Host time of the engine\'s machine cost (generated code, interpreter bridge, picture and sound models, input '
           'replay) on the machine and the core it ran on. Not presentation, audio device, host kit or frame pacing. It says '
           'nothing about native code share, CPU fidelity, hardware fidelity, gameplay validation or physical latency.')
NOT_MEASURED = ('native code share', 'CPU fidelity', 'hardware fidelity', 'gameplay validation', 'physical latency',
                'presentation', 'audio device', 'host kit', 'frame pacing', 'start-up time')

BOUNDED = re.compile(r'bounded_run start_frame=(\d+) end_frame=(\d+) presented=(\d+) .*?seconds=([0-9.]+)')
SNAPSHOT = re.compile(r'vblank_snapshot frame=(\d+) cycles=(\d+) mem=([0-9a-f]+) cpu=([0-9a-f]+)')


class FrameCostError(Exception):
    """A run that cannot be read (failed, timed out, no bounded_run line)."""


@dataclass(frozen=True)
class Side:
    """One probe build: its label and the command prefix that starts it (the executable, or a launcher and its script)."""
    label: str
    prefix: tuple[str, ...]


@dataclass(frozen=True)
class Context:
    rom: Path
    rom_sha1: str
    bios: Path
    script: Path
    core: int | None
    timeout: float


# ---- parsing ----

def parse_bounded(text: str) -> dict | None:
    """{start_frame, end_frame, frames, seconds} of the engine's `bounded_run` line (the last one), or None."""
    found = BOUNDED.findall(text)
    if not found:
        return None
    start, end, _presented, seconds = found[-1]
    return {'start_frame': int(start), 'end_frame': int(end), 'frames': int(end) - int(start), 'seconds': float(seconds)}


def parse_snapshot(text: str) -> dict | None:
    """{cycles, mem, cpu} of the `vblank_snapshot` line (the first one, as the converter reads it), or None."""
    found = SNAPSHOT.search(text)
    return {'cycles': int(found[2]), 'mem': found[3], 'cpu': found[4]} if found else None


# ---- one run ----

def probe_command(side: Side, ctx: Context, frames: int, folder: Path) -> list[str]:
    """The headless command line of the converter's own scenario runs, without the dumps (they come after the timed loop)."""
    return [*side.prefix, '--rom', str(ctx.rom), '--rom-sha1', ctx.rom_sha1, '--bios', str(ctx.bios), '--frames', str(frames),
            '--no-window', '--uncapped', '--volume', '0', '--save', str(folder / 'game.sav')]


def probe_values(ctx: Context, folder: Path) -> dict[str, str]:
    return {'GBARECOMP_COVERAGE_JSON': str(folder / 'coverage.json'), 'GBARECOMP_MISS_FRAG': str(folder / 'miss.toml.frag'),
            'GBARECOMP_RTC_GUEST_EPOCH': RTC_EPOCH, 'GBARECOMP_VBLANK_SNAPSHOT': '1',
            'GBARECOMP_INPUT_REPLAY': str(ctx.script), 'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}


def probe_env(ctx: Context, folder: Path) -> dict[str, str]:
    return probe_environment(remove=('GBARECOMP_FORCE_INTERP', 'GBARECOMP_STRICT_STATIC'), **probe_values(ctx, folder))


def run_once(side: Side, ctx: Context, frames: int, folder: Path) -> dict:
    """One run in a fresh folder: {frames, seconds, wall_seconds, interpreted_insns, snapshot}. FrameCostError when unreadable."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    command = probe_command(side, ctx, frames, folder)
    log = folder / 'output.log'
    with log.open('wb') as out:
        started = time.perf_counter()
        process = subprocess.Popen(command, cwd=folder, env=probe_env(ctx, folder), stdout=out, stderr=subprocess.STDOUT,
                                   creationflags=NO_WINDOW)
        if ctx.core is not None:
            try:
                pin(process, ctx.core)
            except (OSError, AttributeError, ValueError):
                pass                                      # best effort: a refusal changes nothing else
        try:
            process.wait(timeout=ctx.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise FrameCostError(f'{side.label}: no exit within {ctx.timeout:.0f} s\n  command: {" ".join(command)}')
        wall = time.perf_counter() - started
    text = log.read_text(encoding='utf-8', errors='replace')
    if process.returncode:
        raise FrameCostError(f'{side.label}: exit code {process.returncode}\n  command: {" ".join(command)}\n  output: {text[-300:]}')
    bounded = parse_bounded(text)
    if bounded is None:
        raise FrameCostError(f'{side.label}: no bounded_run line in the output (an engine without it cannot be timed this way)\n'
                             f'  command: {" ".join(command)}\n  output: {text[-300:]}')
    try:
        interpreted = json.loads((folder / 'coverage.json').read_text(encoding='utf-8')).get('interpreted_insns')
    except (OSError, ValueError):
        interpreted = None
    return {**bounded, 'wall_seconds': wall, 'interpreted_insns': interpreted, 'snapshot': parse_snapshot(text)}


# ---- the measurement ----

def work_key(run: dict) -> tuple:
    """What two runs must share to have done the same work: frames run and the snapshot's cycles, memory and CPU values."""
    snapshot = run['snapshot']
    return (run['frames'], snapshot['cycles'], snapshot['mem'], snapshot['cpu']) if snapshot else (run['frames'], None)


def ms(seconds: float) -> float:
    return round(seconds * 1000, 4)


def side_record(side: Side, runs: list[dict], startup: dict | None, reference: tuple | None, executable: Path | None) -> dict:
    per_frame = [ms(run['seconds'] / run['frames']) if run['frames'] else None for run in runs]
    usable = [value for value in per_frame if value is not None]
    first = runs[0]['snapshot'] or {}
    cross = None
    if startup is not None:
        cross = [ms((run['wall_seconds'] - startup['wall_seconds']) / run['frames']) if run['frames'] else None for run in runs]
    key = work_key(runs[0])
    return {
        'label': side.label, 'command': list(side.prefix),
        'exe_sha256': hashlib.sha256(executable.read_bytes()).hexdigest() if executable and executable.is_file() else None,
        'raw_ms_per_frame': per_frame, 'best': min(usable) if usable else None,
        'median': round(statistics.median(usable), 4) if usable else None,
        'frames': [run['frames'] for run in runs], 'seconds': [round(run['seconds'], 6) for run in runs],
        'wall_seconds': [round(run['wall_seconds'], 4) for run in runs],
        'startup_wall_seconds': round(startup['wall_seconds'], 4) if startup else None,
        'wall_minus_startup_ms_per_frame': cross,
        'interpreted_insns': runs[0]['interpreted_insns'],
        'interpreted_insns_all_runs': [run['interpreted_insns'] for run in runs],
        'cycles': first.get('cycles'), 'mem_hash': first.get('mem', ''), 'cpu_hash': first.get('cpu', ''),
        'work_identical': all(work_key(run) == (reference or key) and run['snapshot'] is not None for run in runs),
    }


def measure(sides: tuple[Side, Side], ctx: Context, frames: int, runs: int, work: Path,
            executables: tuple[Path | None, Path | None] = (None, None), emit=print) -> dict:
    """Warm-up (dropped), 0-frame start-up run, then `runs` rounds of A, B; returns the result dict (see the module docstring)."""
    order, samples, startups = [], {side.label: [] for side in sides}, {}
    for side in sides:                                                     # one dropped warm-up per build
        order.append(f'warmup {side.label}')
        run_once(side, ctx, frames, work / side.label / 'warmup')
        emit(f'warm-up {side.label} done')
    for side in sides:                                                     # start-up and exit cost, for the wall-time cross-check
        order.append(f'startup {side.label}')
        try:
            startups[side.label] = run_once(side, ctx, 0, work / side.label / 'startup')
        except FrameCostError as error:
            startups[side.label] = None
            emit(f'{side.label}: the 0-frame run failed, no wall-time cross-check ({str(error).splitlines()[0]})')
    for index in range(runs):                                              # A B A B ...
        for side in sides:
            order.append(side.label)
            sample = run_once(side, ctx, frames, work / side.label / f'run-{index}')
            samples[side.label].append(sample)
            emit(f'run {index + 1}/{runs} {side.label}: {ms(sample["seconds"] / max(sample["frames"], 1)):.4f} ms per frame '
                 f'({sample["frames"]} frames)')
    reference = work_key(samples[sides[0].label][0])
    records = {side.label: side_record(side, samples[side.label], startups[side.label],
                                       reference if side is not sides[0] else None, exe)
               for side, exe in zip(sides, executables)}
    a, b = (records[side.label] for side in sides)
    identical = a['work_identical'] and b['work_identical']
    if identical:
        comparison = {'work_identical': True, 'refused': False, 'reason': None,
                      'ratio_best_b_over_a': round(b['best'] / a['best'], 4) if a['best'] else None,
                      'ratio_median_b_over_a': round(b['median'] / a['median'], 4) if a['median'] else None,
                      'delta_best_ms_per_frame': round(b['best'] - a['best'], 4)}
    else:
        missing = any(run['snapshot'] is None for label in samples for run in samples[label])
        comparison = {'work_identical': False, 'refused': True,
                      'reason': ('a run printed no vblank_snapshot line, so the work cannot be checked' if missing else
                                 'the frames run, guest cycles, memory hash or CPU hash differ between the runs of A and B: '
                                 'the two builds did not do the same work, so their costs are not comparable'),
                      'ratio_best_b_over_a': None, 'ratio_median_b_over_a': None, 'delta_best_ms_per_frame': None}
    return {'tool': 'tools/gba_frame_cost.py', 'schema': SCHEMA, 'machine': 'gba', 'measure': 'host_time_only',
            'honesty': HONESTY, 'not_measured': list(NOT_MEASURED), 'scenario': ctx.script.stem, 'frames_requested': frames,
            'runs': runs, 'core': ctx.core, 'quiet_pc_confirmed': False, 'order': order, 'sides': records,
            'comparison': comparison, 'rom_sha1': ctx.rom_sha1, 'python': sys.version.split()[0],
            'os': platform.platform(), 'cpu': cpu_name()}


# ---- host description, output ----

def cpu_name() -> str | None:
    try:
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                return winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        for line in Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith('model name'):
                return line.partition(':')[2].strip()
    except (OSError, ImportError):
        pass
    return platform.processor() or None


def render(result: dict) -> str:
    """The text report of a result dict (also what `report FILE` prints)."""
    lines = []
    if not result.get('quiet_pc_confirmed'):
        lines.append('QUIET PC NOT CONFIRMED: these numbers are not a cost measurement (plumbing check only).')
    lines.append(f'GBA engine frame cost, host time only: scenario {result["scenario"]}, {result["frames_requested"]} frames, '
                 f'{result["runs"]} runs, core {result["core"] if result["core"] is not None else "not pinned"}, '
                 f'{result.get("cpu") or "unknown CPU"}')
    lines.append(result['honesty'])
    lines.append('Not measured: ' + ', '.join(result['not_measured']) + '.')
    lines.append('')
    lines.append(f'{"side":5s} {"best ms/frame":>14s} {"median":>9s} {"wall cross-check":>17s} {"interpreted insns":>18s} {"work":>10s}')
    for label, side in result['sides'].items():
        cross = side.get('wall_minus_startup_ms_per_frame')
        low = min((v for v in cross if v is not None), default=None) if cross else None
        lines.append(f'{label:5s} {side["best"]:14.4f} {side["median"]:9.4f} '
                     f'{("%.4f" % low) if low is not None else "n/a":>17s} {str(side["interpreted_insns"]):>18s} '
                     f'{"identical" if side["work_identical"] else "DIFFERS":>10s}')
        lines.append(f'      raw ms per frame: {side["raw_ms_per_frame"]}')
    comparison = result['comparison']
    lines.append('')
    if comparison['refused']:
        lines.append('COMPARISON REFUSED: ' + comparison['reason'])
    else:
        lines.append(f'B / A: {comparison["ratio_best_b_over_a"]} on the best, {comparison["ratio_median_b_over_a"]} on the median '
                     f'({comparison["delta_best_ms_per_frame"]:+.4f} ms per frame on the best).')
    return '\n'.join(lines)


def plan_text(sides: tuple[Side, Side], ctx: Context, frames: int, runs: int, work: Path) -> str:
    folder = work / '<side>' / '<run>'
    lines = ['DRY RUN - NOT A MEASUREMENT: nothing is run.', QUIET_BANNER,
             f'Plan: per build one dropped warm-up, one 0-frame start-up run, then {runs} rounds of A B A B '
             f'(best of {runs} and the median), {frames} frames of scenario {ctx.script.stem}, core '
             f'{ctx.core if ctx.core is not None else "not pinned"}; every run in a fresh folder under {work}.',
             'Environment of every run: ' + ' '.join(f'{name}={value}' for name, value in probe_values(ctx, folder).items()),
             'Removed from the environment: GBARECOMP_FORCE_INTERP GBARECOMP_STRICT_STATIC']
    for side in sides:
        lines.append(f'{side.label} measured run: ' + ' '.join(probe_command(side, ctx, frames, folder)))
        lines.append(f'{side.label} start-up run:  ' + ' '.join(probe_command(side, ctx, 0, folder)))
    return '\n'.join(lines)


# ---- command line ----

def rom_sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def command_run(args) -> int:
    sides = (Side('A', (str(args.a.resolve()),)), Side('B', (str(args.b.resolve()),)))      # absolute: each run starts in its own folder
    work = args.work.resolve()
    frames, runs = max(1, args.frames), max(1, args.runs)
    exists = args.rom.is_file()
    ctx = Context(args.rom.resolve(), rom_sha1(args.rom) if exists else '<sha1 of the ROM>', args.bios.resolve(),
                  work / 'scripts' / f'{args.scenario}.txt', args.core, args.timeout)
    if args.dry_run:
        print(plan_text(sides, ctx, frames, runs, work))
        return 0
    for name, path in (('--a', args.a), ('--b', args.b), ('--rom', args.rom), ('--bios', args.bios)):
        if not Path(path).is_file():
            raise SystemExit(f'{name}: {path} is not a file')
    print(QUIET_BANNER)
    if not args.quiet_confirmed:
        print('--quiet-confirmed was not passed: the result will say the PC was not confirmed quiet.')
    ctx.script.parent.mkdir(parents=True, exist_ok=True)
    ctx.script.write_text(input_script(frames, args.scenario), encoding='ascii', newline='\n')
    try:
        result = measure(sides, ctx, frames, runs, work, (args.a, args.b))
    except FrameCostError as error:
        print(f'run failed: {error}', file=sys.stderr)
        return 1
    result['quiet_pc_confirmed'] = bool(args.quiet_confirmed)
    out = args.results or work / 'frame-cost.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('\n' + render(result))
    print(f'wrote {out}')
    return 2 if result['comparison']['refused'] else 0


def command_report(args) -> int:
    print(render(json.loads(args.file.read_text(encoding='utf-8'))))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='time two probe builds')
    run.add_argument('--a', type=Path, required=True, help='probe host A (gba_probe.exe)')
    run.add_argument('--b', type=Path, required=True, help='probe host B (may be the same file)')
    run.add_argument('--rom', type=Path, required=True, help='your own cartridge dump (only read)')
    run.add_argument('--bios', type=Path, required=True, help='your own gba_bios.bin (only read)')
    run.add_argument('--scenario', choices=SCENARIOS, default='generic', help="the converter's key script (default generic)")
    run.add_argument('--frames', type=int, default=3600, help='frames per run (default 3600)')
    run.add_argument('--runs', type=int, default=5, help='timed runs per build after the warm-up (default 5)')
    run.add_argument('--core', type=int, default=None, help='pin each run to this core and raise its priority (default: not pinned)')
    run.add_argument('--work', type=Path, default=DEFAULT_WORK, help='scratch folder (default .build/gba-frame-cost)')
    run.add_argument('--results', type=Path, default=None, help='JSON file (default WORK/frame-cost.json)')
    run.add_argument('--timeout', type=float, default=900, help='seconds a single run may last (default 900)')
    run.add_argument('--quiet-confirmed', action='store_true', help='the maintainer said the PC is quiet')
    run.add_argument('--dry-run', action='store_true', help='print the plan and the command lines; run nothing')
    run.set_defaults(handler=command_run)
    report = commands.add_parser('report', help='print a saved JSON again')
    report.add_argument('file', type=Path)
    report.set_defaults(handler=command_report)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == '__main__':
    sys.exit(main())
