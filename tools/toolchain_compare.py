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


def export_identity(executable: Path):
    """The cartridge identity the converter embeds, read from an unpacked copy
    (UPX hides it from a plain scan of the published file)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from retrorecomp.batch import _embedded_export_identity
    upx = Path(__file__).resolve().parents[1] / 'assets/tools/upx.exe'
    with tempfile.TemporaryDirectory(prefix='toolchain-identity-') as temp:
        unpacked = Path(temp) / 'game.exe'
        if upx.is_file():
            subprocess.run([str(upx), '-d', '-o', str(unpacked), str(executable)], capture_output=True)
        if not unpacked.is_file():
            shutil.copy2(executable, unpacked)
        return _embedded_export_identity(unpacked)


def published_executable(output: Path, report: dict) -> Path:
    name = report.get('executable')
    matches = [path for path in output.rglob(name) if path.is_file()] if name else []
    if len(matches) != 1:
        raise SystemExit(f'{output}: expected one {name}, found {len(matches)}')
    return matches[0]


VOLATILE = ('seconds', 'path', 'directory', 'executable', 'bytes', 'created', 'stamp', 'toolchain', 'receipt',
            'source_rom', 'timing', 'url')


def evidence(report: dict) -> dict:
    """What the converter checked, without wall-clock times, paths and sizes."""
    keys = ('final_checks', 'strict_checks', 'native_validation', 'reference_check', 'native_coverage',
            'reference_final_cpu_match', 'reference_final_ram_match', 'reference_final_vdp_match',
            'reference_final_png_match', 'reference_vdp_trace_match')
    return without_timing({key: report[key] for key in keys if key in report})


def differences(left, right, where='') -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        return [item for key in sorted(set(left) | set(right))
                for item in differences(left.get(key), right.get(key), f'{where}.{key}')]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [item for index, (a, b) in enumerate(zip(left, right))
                for item in differences(a, b, f'{where}[{index}]')]
    return [] if left == right else [f'{where}: {json.dumps(left)[:60]} != {json.dumps(right)[:60]}']


def interpreter_use(report: dict) -> dict:
    """Interpreter cycles / instructions / dispatch misses of every final check."""
    found = {}
    for key in ('final_checks', 'strict_checks'):
        for index, check in enumerate(report.get(key) or []):
            found[f'{key}[{index}]'] = {name: check[name] for name in (
                'interpreter_cycles', 'interpreter_instructions', 'interpreter_handoffs', 'interpreter_entries',
                'dispatch_misses', 'fallback_sites', 'interpreted_opcodes') if name in check}
    return found


def without_timing(value):
    """The same evidence with wall-clock fields removed."""
    if isinstance(value, dict):
        return {key: without_timing(item) for key, item in value.items()
                if not any(word in key.lower() for word in VOLATILE)}
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


DEFAULT_FLAGS = '--headless --frames {frames} --log {log}'


def time_frames(executable: Path, frames: int, runs: int, core: int, flags: str = DEFAULT_FLAGS) -> list[float]:
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
            command = [str(game), *flags.format(frames=frames, log=log).split()]
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
    parser.add_argument('--flags', default=DEFAULT_FLAGS,
                        help='headless command line of the exported game; {frames} and {log} are replaced')
    args = parser.parse_args()
    sides = {}
    for label, output in (('msvc', args.msvc), ('llvm', args.llvm)):
        path, report = report_of(output)
        sides[label] = {'path': path, 'report': report, 'exe': published_executable(output, report), 'output': output}
    result = {'game': sides['msvc']['exe'].stem}
    for label, side in sides.items():
        report = side['report']
        build = Path(report.get('build_executable', ''))
        result[label] = {'toolchain': report.get('toolchain', {'kind': 'msvc'}),
                         'raw_executable_bytes': report.get('executable_bytes') or next(
                             (path.stat().st_size for path in (build, side['output'] / 'raw-build.exe') if path.is_file()), None),
                         'published_executable_bytes': side['exe'].stat().st_size,
                         'export_identity': export_identity(side['exe']),
                         'conversion_wall_seconds': report.get('conversion_wall_seconds'),
                         'stage_seconds': report.get('stage_seconds'),
                         'interpreter_use': interpreter_use(report)}
    changes = differences(evidence(sides['msvc']['report']), evidence(sides['llvm']['report']))
    result['identical_evidence'] = not changes
    result['evidence_differences'] = changes[:20]
    result['same_export_identity'] = (result['msvc']['export_identity'] is not None
                                      and result['msvc']['export_identity'] == result['llvm']['export_identity'])
    result['same_interpreter_use'] = result['msvc']['interpreter_use'] == result['llvm']['interpreter_use']
    if args.frames:
        for label, side in sides.items():
            runs = time_frames(side['exe'], args.frames, args.runs, args.core, args.flags)
            result[label]['benchmark'] = {'frames': args.frames, 'runs': [round(value, 4) for value in runs],
                                          'median_seconds': round(statistics.median(runs), 4),
                                          'ms_per_frame': round(statistics.median(runs) * 1000 / args.frames, 4)}
        ratio = result['llvm']['benchmark']['median_seconds'] / result['msvc']['benchmark']['median_seconds']
        result['llvm_time_vs_msvc'] = round(ratio, 3)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
