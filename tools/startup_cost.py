"""Size, packing time and start-up cost of UPX's two compression methods (NRV and LZMA) on finished game builds.

    python -B tools/startup_cost.py pack  [--work DIR] [--determinism] MACHINE:EXE [MACHINE:EXE ...]
    python -B tools/startup_cost.py start [--work DIR] [--runs 9] [--frames 1] [--core N] [--dry-run]
                                          MACHINE:EXE [MACHINE:EXE ...]

EXE is a game build as the conversion validated it (NOT packed); MACHINE is its console id (sms gg gb nes md snes ng cps1
x68), which decides the headless command line. Nothing is written outside --work (default `.build/startup-cost` under the
repository); never into Export. No window ever appears (SDL dummy video and audio drivers, CREATE_NO_WINDOW, output to
files) and nothing waits in a busy loop (the child is waited for with a timeout).

`pack` copies each build twice and packs one copy per method with the converter's own packing code
(`retrorecomp.packing.compact_executable`, the call-filter prefix and its checks included; only the method constant is
switched for the call), then times `upx -t` on each result. It prints, per game: unpacked, NRV and LZMA bytes, the LZMA
size against NRV, the pack time (the whole `compact_executable`: copy, packing, test, filter check) and the test time.
`--determinism` packs a second copy of each build with each method and compares the SHA-256 of the two results.

`start` measures the time from the creation of the process to its exit after `--frames` headless frames (default 1: the
loader's decompression, the host's start and one frame), for three files of each game: the unpacked build, its NRV copy
and its LZMA copy. Each repetition runs the three variants in a rotating order, each from a FRESH COPY of the file in a new
folder (so the file cache does not hold the file as a long-running process left it, and the antivirus sees a new file, as
for a player's first launch), twice: the first start of the copy ("first start") and the second start of the same copy
("second start"). Cache flushing needs administrator rights, so this is as cold as an unprivileged tool gets, and a fresh
copy is still in the cache for the system that just wrote it: say so when quoting the numbers. It reports the median, the
minimum, the maximum and the standard deviation of each series, and the LZMA minus NRV difference of the medians.

It measures one thing: the start-up wall time of a headless run. It says nothing about the native code share, CPU
fidelity, hardware fidelity, gameplay validation or physical latency. Run it on a quiet PC (stop the converter, builds and
other agents first, and say so to the owner); `--core N` pins the child to one core and raises its priority (Windows and
Linux), as the earlier timing tool did. `--dry-run` labels the output as NOT a measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import packing  # noqa: E402
from retrorecomp.paths import ASSETS  # noqa: E402

DEFAULT_WORK = ROOT / '.build' / 'startup-cost'
METHODS = ('nrv', 'lzma')
VARIANTS = ('unpacked', *METHODS)
MACHINES = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def headless_command(machine: str, game: Path, folder: Path, frames: int) -> list[str]:
    """The headless command line of one console's game (the flags retrorecomp's own probes use)."""
    # The X68000 host exits with 1 after a single frame (its first frame ends before the boot); it runs two at least.
    count = str(max(frames, 2) if machine == 'x68' else frames)
    if machine in ('sms', 'gg'):
        return [str(game), '--headless', '--frames', count, '--log', str(folder / 'runtime.log')]          # core.py probe
    if machine == 'gb':
        return [str(game), '--headless', '--limit-frames', count, '--log-file', str(folder / 'game.log')]  # gameboy.py
    if machine == 'nes':
        return [str(game), '--headless', '--frames', count]                                                 # nes.py probe
    if machine in ('md', 'snes'):
        return [str(game), '--frames', count]                                                               # console16.py
    if machine in ('ng', 'cps1', 'x68'):
        return [str(game), '--headless', '--frames', count]            # neogeo_conversion / cps1_conversion / x68000
    raise SystemExit(f'unknown machine {machine!r} (one of {", ".join(MACHINES)})')


def parse_games(items: list[str]) -> list[tuple[str, str, Path]]:
    """[(name, machine, path)] from MACHINE:EXE arguments; the names are made unique."""
    games, seen = [], {}
    for item in items:
        machine, separator, text = item.partition(':')
        # A Windows path starts with a drive letter and a colon: MACHINE:C:\\x.exe splits at the first colon only.
        path = Path(text)
        if not separator or machine not in MACHINES or not path.is_file():
            raise SystemExit(f'{item!r}: expected MACHINE:EXE with MACHINE in {MACHINES} and EXE an existing file')
        if b'UPX!' in path.read_bytes():
            raise SystemExit(f'{path}: already packed; give the build as the conversion validated it')
        base = path.stem
        seen[base] = seen.get(base, 0) + 1
        games.append((base if seen[base] == 1 else f'{base}-{seen[base]}', machine, path))
    return games


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def method_constant() -> str:
    """The name of the packing module's method constant of this OS."""
    return 'WINDOWS_METHOD' if os.name == 'nt' else 'LINUX_METHOD'


def pack_copy(source: Path, target: Path, method: str) -> dict:
    """Copy `source` to `target` and pack it with `method` through the converter's code: {packed, seconds, bytes, notice}."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)                     # keeps the executable bit (Linux), not the times
    name, saved = method_constant(), getattr(packing, method_constant())
    setattr(packing, name, method)
    try:
        started = time.perf_counter()
        outcome = packing.compact_executable(target, emit=lambda text: None)
        seconds = time.perf_counter() - started
    finally:
        setattr(packing, name, saved)
    return {'packed': outcome is None and b'UPX!' in target.read_bytes(), 'seconds': round(seconds, 2),
            'bytes': target.stat().st_size, 'notice': outcome['notice'] if outcome else None}


def upx_tool() -> Path:
    return ASSETS / ('assets/tools/upx.exe' if os.name == 'nt' else packing.UPX_LINUX)


def upx_test_seconds(path: Path) -> tuple[float, bool]:
    """(seconds, passed) of `upx -t` on one packed file."""
    started = time.perf_counter()
    result = subprocess.run([str(upx_tool()), '-t', str(path)], capture_output=True, text=True, creationflags=NO_WINDOW,
                            timeout=packing.upx_timeout(path))
    return round(time.perf_counter() - started, 2), result.returncode == 0


def pack_table(games, work: Path, determinism: bool) -> list[dict]:
    rows = []
    for name, machine, source in games:
        row = {'game': name, 'machine': machine, 'source': str(source), 'unpacked_bytes': source.stat().st_size}
        for method in METHODS:
            target = work / name / f'{name}.{method}.exe'
            record = pack_copy(source, target, method)
            if record['packed']:
                record['test_seconds'], record['test_passed'] = upx_test_seconds(target)
            if determinism:
                again = work / name / f'{name}.{method}.again.exe'
                pack_copy(source, again, method)
                record['deterministic'] = sha256(target) == sha256(again)
                again.unlink()
            row[method] = record
        rows.append(row)
        print(f'packed {name}', flush=True)
    return rows


def print_pack_table(rows: list[dict]) -> None:
    header = (f'{"game":24s} {"mach":5s} {"unpacked":>10s} {"NRV":>10s} {"LZMA":>10s} {"LZMA/NRV":>9s} '
              f'{"pack NRV s":>10s} {"pack LZMA s":>11s} {"test NRV s":>10s} {"test LZMA s":>11s}')
    print(header)
    for row in rows:
        nrv, lzma = row['nrv'], row['lzma']
        ratio = f'{lzma["bytes"] / nrv["bytes"]:.3f}' if nrv['packed'] and lzma['packed'] else 'n/a'
        print(f'{row["game"]:24s} {row["machine"]:5s} {row["unpacked_bytes"]:10d} {nrv["bytes"]:10d} {lzma["bytes"]:10d} '
              f'{ratio:>9s} {nrv["seconds"]:10.2f} {lzma["seconds"]:11.2f} {nrv.get("test_seconds", float("nan")):10.2f} '
              f'{lzma.get("test_seconds", float("nan")):11.2f}')
        for method in METHODS:
            record = row[method]
            if not record['packed'] or not record.get('test_passed', True) or record.get('deterministic') is False:
                print(f'  !! {method}: packed={record["packed"]} test_passed={record.get("test_passed")} '
                      f'deterministic={record.get("deterministic")} {record["notice"] or ""}')


# ---- the start-up measurement ----

def pin(process: subprocess.Popen, core: int) -> None:
    """One core and a raised priority for the child (best effort: a refusal changes nothing else)."""
    try:
        if os.name != 'nt':
            os.sched_setaffinity(process.pid, {core})
            return
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        kernel.SetProcessAffinityMask(ctypes.c_void_p(int(process._handle)), 1 << core)
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.SetPriorityClass(ctypes.c_void_p(int(process._handle)), 0x80)       # HIGH_PRIORITY_CLASS
    except (OSError, AttributeError, ValueError):
        pass


def start_once(machine: str, exe: Path, folder: Path, frames: int, core: int | None, timeout: float) -> float:
    """Seconds from the creation of the child to its exit after `frames` headless frames (SystemExit on a failed run)."""
    environment = {**os.environ, 'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy',
                   'RETRO_RECOMP_LIBRARY_DIR': str(folder / 'learning'), 'SMSRECOMP_LIBRARY_DIR': str(folder / 'learning'),
                   'RETRO_RECOMP_LEARNING': '0'}
    command = headless_command(machine, exe, folder, frames)
    with (folder / 'stdout.txt').open('wb') as out, (folder / 'stderr.txt').open('wb') as err:
        started = time.perf_counter()
        process = subprocess.Popen(command, cwd=folder, env=environment, stdout=out, stderr=err, creationflags=NO_WINDOW)
        if core is not None:
            pin(process, core)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise SystemExit(f'{exe.name}: no exit within {timeout:.0f} s')
        elapsed = time.perf_counter() - started
    if process.returncode:
        tail = (folder / 'stderr.txt').read_text(encoding='utf-8', errors='replace')[-300:]
        raise SystemExit(f'{exe.name}: exit code {process.returncode}\n  command: {" ".join(command)}\n  stderr: {tail}')
    return elapsed


def summary(values: list[float]) -> dict:
    ms = [round(v * 1000, 1) for v in values]
    return {'n': len(ms), 'median_ms': round(statistics.median(ms), 1), 'min_ms': min(ms), 'max_ms': max(ms),
            'stdev_ms': round(statistics.stdev(ms), 1) if len(ms) > 1 else 0.0, 'raw_ms': ms}


def start_table(games, work: Path, runs: int, frames: int, core: int | None) -> list[dict]:
    rows = []
    for name, machine, source in games:
        files = {'unpacked': source}
        for method in METHODS:
            target = work / name / f'{name}.{method}.exe'
            if not (target.is_file() and b'UPX!' in target.read_bytes()):
                record = pack_copy(source, target, method)
                if not record['packed']:
                    raise SystemExit(f'{name}: {method} copy could not be packed: {record["notice"]}')
            files[method] = target
        series = {variant: {'first': [], 'second': []} for variant in VARIANTS}
        for repetition in range(runs):
            shift = repetition % len(VARIANTS)
            for variant in VARIANTS[shift:] + VARIANTS[:shift]:                       # a rotating order
                folder = work / name / f'run-{variant}'
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True)
                copy = folder / files[variant].name.replace('.' + variant, '')
                shutil.copy(files[variant], copy)                                      # a fresh file every repetition, executable
                limit = max(120.0, 20 * source.stat().st_size / 1e6)
                series[variant]['first'].append(start_once(machine, copy, folder, frames, core, limit))
                series[variant]['second'].append(start_once(machine, copy, folder, frames, core, limit))
                shutil.rmtree(folder, ignore_errors=True)
        row = {'game': name, 'machine': machine, 'frames': frames, 'runs': runs, 'core': core,
               'bytes': {variant: files[variant].stat().st_size for variant in VARIANTS}}
        for variant in VARIANTS:
            row[variant] = {when: summary(values) for when, values in series[variant].items()}
        row['lzma_minus_nrv_ms'] = {when: round(row['lzma'][when]['median_ms'] - row['nrv'][when]['median_ms'], 1)
                                    for when in ('first', 'second')}
        row['lzma_minus_unpacked_ms'] = {when: round(row['lzma'][when]['median_ms'] - row['unpacked'][when]['median_ms'], 1)
                                         for when in ('first', 'second')}
        rows.append(row)
        print(f'measured {name}', flush=True)
    return rows


def print_start_table(rows: list[dict]) -> None:
    print(f'{"game":24s} {"mach":5s} {"start":6s} {"unpacked ms":>12s} {"NRV ms":>9s} {"LZMA ms":>9s} {"LZMA-NRV":>9s} '
          f'{"spread (stdev) unp/NRV/LZMA":>30s}')
    for row in rows:
        for when in ('first', 'second'):
            medians = [row[v][when]['median_ms'] for v in VARIANTS]
            spreads = '/'.join(f'{row[v][when]["stdev_ms"]:.1f}' for v in VARIANTS)
            print(f'{row["game"]:24s} {row["machine"]:5s} {when:6s} {medians[0]:12.1f} {medians[1]:9.1f} {medians[2]:9.1f} '
                  f'{row["lzma_minus_nrv_ms"][when]:9.1f} {spreads:>30s}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('pack', 'start'))
    parser.add_argument('games', nargs='+', metavar='MACHINE:EXE')
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK, help='scratch folder (default .build/startup-cost)')
    parser.add_argument('--determinism', action='store_true', help='pack: pack each method twice and compare the bytes')
    parser.add_argument('--runs', type=int, default=9, help='start: repetitions per variant (default 9)')
    parser.add_argument('--frames', type=int, default=1, help='start: headless frames per run (default 1)')
    parser.add_argument('--core', type=int, default=None, help='start: pin the child to this core and raise its priority')
    parser.add_argument('--dry-run', action='store_true', help='start: label the output as NOT a measurement')
    parser.add_argument('--results', type=Path, default=None, help='JSON file for the rows (default WORK/<command>.json)')
    args = parser.parse_args()
    work = args.work.resolve()
    if ROOT not in (work, *work.parents):
        raise SystemExit('--work must be inside the repository (no folder outside the project)')
    games = parse_games(args.games)
    work.mkdir(parents=True, exist_ok=True)
    label = 'DRY RUN - NOT A MEASUREMENT' if args.dry_run else 'measurement'
    if args.command == 'pack':
        rows = pack_table(games, work, args.determinism)
        print_pack_table(rows)
    else:
        print(label + ('' if args.dry_run else ' (needs a quiet PC: stop builds, conversions and other agents first)'))
        rows = start_table(games, work, max(1, args.runs), max(1, args.frames), args.core)
        print_start_table(rows)
        if args.dry_run:
            print('\n' + label + ': these numbers say nothing about start-up cost.')
    out = args.results or work / f'{args.command}.json'
    out.write_text(json.dumps({'command': args.command, 'label': label if args.command == 'start' else 'size and time',
                               'method_constant': method_constant(), 'packer': packing.UPX_VERSION, 'rows': rows},
                              indent=2), encoding='utf-8')
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
