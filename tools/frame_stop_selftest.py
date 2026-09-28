"""Headless authored I/O instructions crossing a frame limit or host stop."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, read_rom, default_config, prepare_runtime, run

def main():
    directory = ROOT / '.build/frame-stop-selftest'
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(directory / 'learning')
    data = bytearray(8192)
    # IN A,(n), OUT (n),A, IN A,(C), OUT (C),A; all block I/O forms.
    codes = ('DB 7E', 'D3 BF', 'ED 78', 'ED 79', 'ED A2', 'ED AA',
             'ED B2', 'ED BA', 'ED A3', 'ED AB', 'ED B3', 'ED BB')
    for i, code in enumerate(codes): data[i*8:i*8+2] = bytes.fromhex(code)
    rom_path = directory / 'authored.sms'
    rom_path.write_bytes(data)
    rom = read_rom(rom_path)
    (directory / 'rom.sms').write_bytes(data)
    (directory / 'game.toml').write_text(default_config(rom), encoding='utf-8')
    (directory / 'dispatch_manifest.txt').write_text('', encoding='utf-8')
    engine, sdl, cmake, generator = dependencies()
    prepare_runtime(directory, rom, 'Authored frame-stop fixture', engine)
    log = directory / 'build.log'
    run([ROOT / '.deps/recompiler-build/Release/SmsRecomp.exe', '--game', directory / 'game.toml', '--banked-step'], log=log)
    source = ROOT / '.build/native-source'
    source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    build = directory / 'build'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={directory.as_posix()}',
         '-DGAME_NAME=AuthoredFrameStop', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_BANKED_AOT=ON', '-DSMSRECOMP_FRAME_STOP_CHECKS=ON'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'smsrecomp_frame_stop_checks', '--parallel', '4'], log=log)
    result = subprocess.run([str(build / 'Release/smsrecomp_frame_stop_checks.exe')], cwd=directory,
        capture_output=True, text=True, timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    output = result.stdout + result.stderr
    (directory / 'checks.log').write_text(output, encoding='utf-8')
    (directory / 'verification.json').write_text(json.dumps({'exit_code': result.returncode,
        'commercial_rom_used': False, 'visual_review_performed': False, 'result': result.stdout}, indent=2), encoding='utf-8')
    print(result.stdout)
    if result.returncode: raise SystemExit(result.returncode)

if __name__ == '__main__': main()
