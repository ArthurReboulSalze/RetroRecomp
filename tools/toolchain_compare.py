"""Compare two conversions of the same game: Visual Studio build and portable build.

    python tools/toolchain_compare.py MSVC_OUTPUT LLVM_OUTPUT [--frames N] [--runs N] [--core N]

Each argument is the --output folder of one `RetroRecomp.py convert` run (same
ROM, same commit, same scan level, one library folder per run). The measures
stay separate, as in AGENTS.md:

- native code: interpreter use and dispatch misses reported by the converter;
- CPU fidelity: identical final CPU state of the native run, the strict run
  and the reference interpreter (Master System / Game Gear reports);
- executable size: raw build and published (compacted) file;
- host time per frame: the published executable, run headless on one pinned
  core, median of several runs. It is a host cost, not a latency measure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def report_of(output: Path) -> tuple[Path, dict]:
    reports = sorted(output.rglob('conversion-report.json'))
    if len(reports) != 1:
        raise SystemExit(f'{output}: expected one conversion-report.json, found {len(reports)}')
    return reports[0], json.loads(reports[0].read_text(encoding='utf-8'))


def published_executable(output: Path, report: dict) -> Path:
    name = report.get('executable')
    matches = [path for path in output.rglob(name) if path.is_file()] if name else []
    if len(matches) != 1:
        raise SystemExit(f'{output}: expected one {name}, found {len(matches)}')
    return matches[0]


def final_states(report: dict) -> dict:
    states = {}
    for key in ('final_checks', 'strict_checks'):
        for index, check in enumerate(report.get(key) or []):
            cpu = check.get('final_cpu')
            states[f'{key}[{index}]'] = {
                'cpu': json.dumps(cpu, sort_keys=True) if cpu else None,
                'interpreter_cycles': check.get('interpreter_cycles'),
                'dispatch_misses': check.get('dispatch_misses'),
                'total_cycles': check.get('total_cycles'),
                'completed_frames': check.get('completed_frames')}
    reference = report.get('reference_check') or {}
    states['reference'] = {'cpu': json.dumps(reference.get('final_cpu'), sort_keys=True) if reference.get('final_cpu') else None}
    return states


def without_timing(value):
    """The same evidence with wall-clock fields removed."""
    if isinstance(value, dict):
        return {key: without_timing(item) for key, item in value.items() if key != 'wall_seconds'}
    if isinstance(value, list):
        return [without_timing(item) for item in value]
    return value


def pin(process: subprocess.Popen, core: int) -> None:
    if os.name != 'nt':
        os.sched_setaffinity(process.pid, {core})
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel.SetProcessAffinityMask(ctypes.c_void_p(int(process._handle)), 1 << core)
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel.SetPriorityClass(ctypes.c_void_p(int(process._handle)), 0x80)   # HIGH_PRIORITY_CLASS


def time_frames(executable: Path, frames: int, runs: int, core: int) -> list[float]:
    """Headless run of the published executable, copied beside nothing else."""
    seconds = []
    with tempfile.TemporaryDirectory(prefix='toolchain-bench-') as temp:
        directory = Path(temp)
        game = directory / executable.name
        shutil.copy2(executable, game)
        environment = {**os.environ, 'RETRO_RECOMP_LIBRARY_DIR': str(directory / 'learning'),
                       'SMSRECOMP_LIBRARY_DIR': str(directory / 'learning'), 'RETRO_RECOMP_LEARNING': '0'}
        for index in range(runs + 1):   # the first run warms the file cache and is dropped
            log = directory / f'run{index}.log'
            command = [str(game), '--headless', '--frames', str(frames), '--log', str(log)]
            started = time.perf_counter()
            process = subprocess.Popen(command, cwd=directory, env=environment, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            pin(process, core)
            process.wait(timeout=600)
            elapsed = time.perf_counter() - started
            if process.returncode:
                raise SystemExit(f'{executable}: exit code {process.returncode}')
            if index:
                seconds.append(elapsed)
    return seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('msvc', type=Path)
    parser.add_argument('llvm', type=Path)
    parser.add_argument('--frames', type=int, default=0, help='benchmark frames (0 skips the timing)')
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--core', type=int, default=4)
    parser.add_argument('--full', action='store_true', help='print the complete evidence of both reports')
    args = parser.parse_args()
    sides = {}
    for label, output in (('msvc', args.msvc), ('llvm', args.llvm)):
        path, report = report_of(output)
        sides[label] = {'path': path, 'report': report, 'exe': published_executable(output, report)}
    result = {'game': sides['msvc']['report'].get('rom', {}).get('name') or sides['msvc']['exe'].stem}
    for label, side in sides.items():
        report = side['report']
        result[label] = {'toolchain': report.get('toolchain', {'kind': 'msvc'}),
                         'raw_executable_bytes': report.get('executable_bytes'),
                         'published_executable_bytes': side['exe'].stat().st_size,
                         'conversion_wall_seconds': report.get('conversion_wall_seconds'),
                         'native_validation': without_timing(report.get('native_validation')),
                         'reference_final_cpu_match': report.get('reference_final_cpu_match'),
                         'reference_final_ram_match': report.get('reference_final_ram_match'),
                         'reference_final_vdp_match': report.get('reference_final_vdp_match'),
                         'reference_final_png_match': report.get('reference_final_png_match'),
                         'states': final_states(report)}
    first, second = result['msvc']['states'], result['llvm']['states']
    result['identical'] = {'final_states': first == second,
                           'native_validation': result['msvc']['native_validation'] == result['llvm']['native_validation']}
    if args.frames:
        for label, side in sides.items():
            runs = time_frames(side['exe'], args.frames, args.runs, args.core)
            result[label]['benchmark'] = {'frames': args.frames, 'runs': [round(value, 4) for value in runs],
                                          'median_seconds': round(statistics.median(runs), 4),
                                          'ms_per_frame': round(statistics.median(runs) * 1000 / args.frames, 4)}
        ratio = result['llvm']['benchmark']['median_seconds'] / result['msvc']['benchmark']['median_seconds']
        result['llvm_time_vs_msvc'] = round(ratio, 3)
    if not args.full:
        for label in ('msvc', 'llvm'):
            side = result[label]
            side['native_validation'] = {'passed': (side['native_validation'] or {}).get('passed'),
                                         'scenarios': [(item.get('scenario'), item.get('passed'))
                                                       for item in (side['native_validation'] or {}).get('scenarios', [])]}
            side['states'] = {name: {**{key: value for key, value in state.items() if key != 'cpu'},
                                     'cpu_pc': (json.loads(state['cpu'])['pc'] if state.get('cpu') else None)}
                              for name, state in side['states'].items()}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
