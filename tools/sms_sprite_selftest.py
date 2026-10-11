"""Measure SMS sprite overflow and verify a display enhancement on an existing private build."""
import argparse
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
    parser.add_argument('--frames', type=int, default=3600)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    if report['system']['id'] != 'sms' or report['backend'] != 'banked':
        parser.error('Use an existing Master System banked conversion report.')
    directory = ROOT / '.build/sms-sprite-selftest' / slug(Path(report['executable']).stem)
    source = directory / 'source'
    source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    engine, sdl, cmake, generator = dependencies()
    build = directory / 'build'
    log = directory / 'build.log'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={Path(report["build_directory"]).as_posix()}',
         '-DGAME_NAME=SmsSpriteProbe', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_SPRITE_PROBE=ON'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target',
         'smsrecomp_sprite_probe', '--parallel', '4'], log=log)
    environment = os.environ.copy()
    environment['SMSRECOMP_STRICT'] = '1'
    environment['SMSRECOMP_LIBRARY_DIR'] = str(directory / 'private-library')
    results = {}
    for reference in (False, True):
        for improved in (False, True):
            name = ('reference' if reference else 'native') + ('_improved' if improved else '_console')
            command = [build / 'Release/smsrecomp_sprite_probe.exe', args.frames,
                       directory / f'{name}.csv', int(improved)]
            if reference: command.append('reference')
            result = subprocess.run([str(v) for v in command], cwd=directory,
                env=environment, capture_output=True, encoding='utf-8', errors='replace',
                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            (directory / f'{name}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode: raise RuntimeError(f'Sprite probe failed: {directory / name}')
            results[name] = json.loads(result.stdout.strip().splitlines()[-1])
    # Compare real CPU/RAM/banks/VDP/PSG/latches after the complete instruction,
    # excluding only pixel buffers, retaining the raster latches. Audio is
    # independently hashed across the whole route, not merely its final state.
    first = results['native_console']
    for name, value in results.items():
        for field in ('frames', 'guest_state_hash', 'pcm_hash', 'pcm_samples',
                      'affected_frames', 'overflow_lines', 'recoverable_pixels', 'max_sprites'):
            if value[field] != first[field]: raise RuntimeError(f'{name}: differing {field}')
        if name.startswith('native') and value['fallback_cycles']:
            raise RuntimeError(f'{name}: unexpected interpreter fallback')
        if (directory / f'{name}.csv').read_bytes() != (directory / 'native_console.csv').read_bytes():
            raise RuntimeError(f'{name}: differing sprite trace')
    for field in ('stabilized_frames', 'priority_adjusted_pixels'):
        if results['native_improved'][field] != results['reference_improved'][field]:
            raise RuntimeError(f'CPU paths differ in {field}')
        if results['native_console'][field] or results['reference_console'][field]:
            raise RuntimeError(f'Original console mode unexpectedly changes {field}')
    proof = {'rom_sha256': report['rom']['sha256'], 'runs': results,
             'guest_state_and_pcm_equal': True, 'sprite_traces_equal': True,
             'rendered_overflow_rows_match_selected_mode': True,
             'stabilized_composition_matches_reference': True,
             'visual_review_performed': False, 'full_hardware_fidelity': False,
             'input_script': ['120:AB', '125:', '240:R', '360:']}
    (directory / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__': main()
