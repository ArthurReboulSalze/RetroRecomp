"""Headless technical VDP checks, optionally using one existing private game."""
import argparse
import csv
from itertools import zip_longest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, run, slug

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--probe', action='store_true', help='Compare VDP writes and raster hashes on both CPUs.')
    parser.add_argument('--frames', type=int, default=1800)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    directory = ROOT / '.build/video-selftest' / slug(Path(report['executable']).stem)
    directory.mkdir(parents=True, exist_ok=True)
    source = ROOT / '.build/native-source'
    source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    engine, sdl, cmake, generator = dependencies()
    build = directory / 'build'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={Path(report["build_directory"]).as_posix()}',
         f'-DGAME_NAME={slug(Path(report["executable"]).stem)}', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         f'-DSMSRECOMP_BANKED_AOT={"ON" if report["backend"] == "banked" else "OFF"}',
         '-DSMSRECOMP_VIDEO_CHECKS=ON', f'-DSMSRECOMP_VIDEO_PROBE={"ON" if args.probe else "OFF"}'])
    targets = ['smsrecomp_video_checks'] + (['smsrecomp_video_probe'] if args.probe else [])
    run([cmake, '--build', build, '--config', 'Release', '--target', *targets, '--parallel', '4'])
    log = run([build / 'Release/smsrecomp_video_checks.exe'])
    proof = {'chip_fixtures_passed': True, 'visual_review_performed': False}
    if args.probe:
        # Keep diagnostic learning outputs local to this private test directory.
        environment = os.environ.copy()
        environment['SMSRECOMP_LIBRARY_DIR'] = str(directory / 'learning')
        environment['SMSRECOMP_STRICT'] = '1'
        for reference in (False, True):
            trace = directory / ('reference.csv' if reference else 'native.csv')
            command = [build / 'Release/smsrecomp_video_probe.exe', str(args.frames), trace]
            if reference: command.append('reference')
            result = subprocess.run([str(p) for p in command], cwd=directory, env=environment,
                capture_output=True, encoding='utf-8', errors='replace', timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            log += result.stdout + result.stderr
            if result.returncode:
                (directory / 'checks.log').write_text(log, encoding='utf-8')
                raise RuntimeError('Raster probe failed: ' + str(directory / 'checks.log'))
        # Reference callbacks do not expose g_z80.cyc at the same point as the
        # native runner. Compare frame, raster line, write and pixel hash; the
        # last two columns are native-only diagnostic cycle timestamps.
        with (directory / 'native.csv').open(newline='') as native_file, \
             (directory / 'reference.csv').open(newline='') as reference_file:
            native_events = csv.reader(native_file)
            reference_events = csv.reader(reference_file)
            for index, (native, reference_row) in enumerate(
                    zip_longest(native_events, reference_events), 1):
                if native is None or reference_row is None or native[:5] != reference_row[:5]:
                    (directory / 'checks.log').write_text(log, encoding='utf-8')
                    raise RuntimeError(f'CPU paths differ in VDP events or rendered frames '
                                       f'at event {index}; see {directory}')
        proof.update(native_reference_writes_and_frames_equal=True, frames=args.frames)
    (directory / 'checks.log').write_text(log, encoding='utf-8')
    (directory / 'verification.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(log)

if __name__ == '__main__': main()
