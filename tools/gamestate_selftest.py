"""Persistent state continuation with an authored ROM; no video or commercial games."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, ASSETS, dependencies, read_rom, default_config, prepare_runtime, run

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pal', action='store_true', help='Check the 313-line PAL machine state.')
    args = parser.parse_args()
    directory = ROOT / ('.build/gamestate-selftest-pal' if args.pal else '.build/gamestate-selftest')
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(directory / 'learning')
    data = bytearray(32768)
    data[:3] = bytes.fromhex('C3 00 01')
    # Interrupt handler reads/acknowledges status, modifies RAM, EI and RETI.
    handler = bytes.fromhex('F5 DB BF 3A 01 C0 3C 32 01 C0 F1 FB ED 4D')
    data[0x38:0x38+len(handler)] = handler
    init = bytes.fromhex('31 F0 DF ED 56 3E 60 D3 BF 3E 81 D3 BF 3E 0E D3 BF 3E 82 D3 BF 3E 7E D3 BF 3E 85 D3 BF 3E 90 D3 7F FB')
    loop = bytes.fromhex('21 00 C0 34 7E D3 7F D3 BF 3E 88 D3 BF 7E E6 01 32 FF FF 7E D3 BE DD FD 00')
    start = 0x100 + len(init)
    data[0x100:start] = init
    data[start:start+len(loop)] = loop
    data[start+len(loop):start+len(loop)+3] = bytes([0xC3, start & 255, start >> 8])
    rom_path = directory / 'authored.sms'; rom_path.write_bytes(data)
    rom = read_rom(rom_path); (directory / 'rom.sms').write_bytes(data)
    (directory / 'game.toml').write_text(default_config(rom), encoding='utf-8')
    (directory / 'dispatch_manifest.txt').write_text('', encoding='utf-8')
    engine, sdl, cmake, generator = dependencies()
    prepare_runtime(directory, rom, 'Authored persistent state fixture', engine,
                    'pal' if args.pal else 'ntsc')
    log = directory / 'build.log'
    run([ROOT / '.deps/recompiler-build/Release/SmsRecomp.exe', '--game', directory / 'game.toml', '--banked-step'], log=log)
    source = ROOT / '.build/native-source'; source.mkdir(parents=True, exist_ok=True)
    for file in (ASSETS / 'native').iterdir():
        if file.is_file(): shutil.copy2(file, source / file.name)
    build = directory / 'build'
    run([cmake, '-S', source, '-B', build, '-G', generator, '-A', 'x64',
         f'-DENGINE_DIR={engine.as_posix()}', f'-DGAME_DIR={directory.as_posix()}',
         '-DGAME_NAME=AuthoredState', f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}',
         '-DSMSRECOMP_BANKED_AOT=ON', '-DSMSRECOMP_STATE_CHECKS=ON'], log=log)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'smsrecomp_state_checks', '--parallel', '4'], log=log)
    outputs = []
    for mode in (1, 2):
        result = subprocess.run([str(build / 'Release/smsrecomp_state_checks.exe'), str(mode)], cwd=directory,
            capture_output=True, text=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        outputs.append(result.stdout + result.stderr)
        (directory / 'checks.log').write_text('\n'.join(outputs), encoding='utf-8')
        print(result.stdout)
        if result.returncode: raise SystemExit(result.returncode)
    (directory / 'verification.json').write_text(json.dumps({'exit_code': 0,
        'commercial_rom_used': False, 'visual_review_performed': False,
        'video_standard': 'pal' if args.pal else 'ntsc',
        'independent_processes': 2, 'results': outputs}, indent=2), encoding='utf-8')

if __name__ == '__main__': main()
