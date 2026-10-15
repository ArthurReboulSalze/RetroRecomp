"""Bounded native Linux SMS qualification, using an authored ROM and optional private witness."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import convert, dependencies, run, prepare_native_source
from smsrecomp.paths import ROOT
from smsrecomp.platforms import cmake_target_args, build_jobs, target_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rom', type=Path)
    parser.add_argument('--frames', type=int, default=1200)
    args = parser.parse_args()
    if not target_id().startswith('linux-'):
        parser.error('Run on the Linux target itself.')
    work = ROOT / '.build' / target_id() / 'qualification'
    work.mkdir(parents=True, exist_ok=True)
    os.environ['RETRO_RECOMP_LIBRARY_DIR'] = str(work / 'library')
    synthetic = work / 'Two controller ports.sms'
    data = bytearray([0xC9] * 8192)
    data[:3] = bytes.fromhex('C3 00 01')
    program = bytes.fromhex('F3 31 F0 DF DB DC 32 00 C0 DB DD 32 01 C0 C3 04 01')
    data[0x100:0x100 + len(program)] = program
    synthetic.write_bytes(data)
    diagnostic = convert(synthetic, title='Linux input diagnostic', output=work/'diagnostic',
                         frames=3, passes=2, use_cover=False, online_cover=False)
    result = {'target': target_id(), 'synthetic': str(diagnostic)}
    run(['cc', '-std=gnu11', '-I', ROOT/'native', ROOT/'native/platform_posix_checks.c',
         ROOT/'native/platform_io.c', '-o', work/'platform-checks'])
    result['platform'] = run([work/'platform-checks', work/'UTF-8 cafÃƒÂ© settings'])
    if args.rom:
        executable = convert(args.rom, output=work/'Games/Master System', frames=args.frames,
                             passes=3, use_cover=False, online_cover=False)
        report = json.loads((executable.parent/'conversion-report.json').read_text())
        game = Path(report['build_directory'])
        engine, sdl, cmake, generator = dependencies()
        build = game/'build-native'
        run([cmake, '-S', prepare_native_source(), '-B', build, '-G', generator, *cmake_target_args(),
             f'-DENGINE_DIR={engine}', f'-DGAME_DIR={game}', '-DGAME_SYSTEM=sms',
             '-DSMSRECOMP_BANKED_AOT=ON', '-DGAME_NAME=Alex_Kidd_in_Miracle_World',
             f'-DCMAKE_PREFIX_PATH={sdl}', '-DSMSRECOMP_STATE_CHECKS=ON'])
        run([cmake, '--build', build, '--target', 'smsrecomp_state_checks',
             '--parallel', build_jobs()])
        states = work/'states'
        states.mkdir(exist_ok=True)
        result['save'] = run([build/'smsrecomp_state_checks', '1'], cwd=states)
        result['fresh_process_resume'] = run([build/'smsrecomp_state_checks', '2'], cwd=states)
        result['frame_stop'] = run([sys.executable, ROOT/'tools/frame_stop_selftest.py'])
        result['game'] = str(executable)
        result['report'] = str(executable.parent/'conversion-report.json')
    (work/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
