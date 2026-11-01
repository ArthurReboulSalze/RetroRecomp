"""Battery saves of a NES export, on an authored cartridge (no ROM of anyone's is used).

    python tools/nes_saves_check.py [--work DIR]

The cartridge is written here: MMC1 with 8 KiB of battery RAM and a tiny program that also gives the backdrop a new colour every frame, so that the conversion sees a moving picture. At reset it reads $6000. If the byte is
not $A5 it writes $A5 there and 1 at $6001 (the first run); otherwise it adds 1 to $6001. The tool converts it with the batch
command line, then, from the folder of the export (the game keeps its saves in `datas/games` beside the executable):

  1. runs the game for 60 frames, closes it, and finds the battery file with $A5 and 1;
  2. runs it again from the same folder: the file holds 2, which means the second launch loaded what the first one saved;
  3. converts the cartridge again over the same export and runs the new executable: 3, which means a rebuilt game finds the
     save of the previous build;
  4. checks that the conversion's own probes left the player's save as it was (they run on private copies).

It does not claim that a real game saves what it should: it shows that the battery file is written, read back, kept across a
second launch and across a second build. Everything goes under `.build/nes-saves-check` (or --work). The converter is the
checkout this file is in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
TITLE = 'Battery Check'


def authored_cartridge() -> bytes:
    """iNES 1.0, mapper 1, battery, 32 KiB PRG, 8 KiB CHR ROM; the program sits in the fixed bank at $C000."""
    program = bytes([
        0x78, 0xD8, 0xA2, 0xFF, 0x9A,          # SEI, CLD, LDX #$FF, TXS
        0xAD, 0x00, 0x60,                       # LDA $6000
        0xC9, 0xA5,                             # CMP #$A5
        0xF0, 0x0D,                             # BEQ have
        0xA9, 0xA5, 0x8D, 0x00, 0x60,           # LDA #$A5, STA $6000
        0xA9, 0x01, 0x8D, 0x01, 0x60,           # LDA #1, STA $6001
        0x4C, 0x1C, 0xC0,                       # JMP loop
        0xEE, 0x01, 0x60,                       # have: INC $6001
        # loop: each frame, wait for vblank and give the backdrop the next colour, so the picture changes
        0xAD, 0x02, 0x20, 0x10, 0xFB,           # loop: LDA $2002, BPL loop
        0xA9, 0x3F, 0x8D, 0x06, 0x20,           # LDA #$3F, STA $2006
        0xA9, 0x00, 0x8D, 0x06, 0x20,           # LDA #$00, STA $2006
        0xA5, 0x00, 0x8D, 0x07, 0x20,           # LDA $00, STA $2007
        0xA9, 0x3F, 0x8D, 0x06, 0x20,           # LDA #$3F, STA $2006   (the address back on $3F00, which the
        0xA9, 0x00, 0x8D, 0x06, 0x20,           # LDA #$00, STA $2006    picture shows while rendering is off)
        0xE6, 0x00,                             # INC $00
        0x4C, 0x1C, 0xC0,                       # JMP loop
    ])
    prg = bytearray([0xEA]) * 0x8000
    prg[0x4000:0x4000 + len(program)] = program
    for vector in (0x7FFA, 0x7FFC, 0x7FFE):    # NMI, reset, IRQ
        prg[vector:vector + 2] = bytes([0x00 if vector == 0x7FFC else 0x1C, 0xC0])
    header = bytes([0x4E, 0x45, 0x53, 0x1A, 2, 1, (1 << 4) | 2, 0]) + bytes(8)
    return header + bytes(prg) + bytes(0x2000)


def run(command, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(part) for part in command], creationflags=NO_WINDOW, **kwargs)


def convert(rom: Path, output: Path, library: Path, log: Path) -> Path:
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYINSTALLER_SUPPRESS_SPLASH_SCREEN='1',
               RETRO_RECOMP_LIBRARY_DIR=str(library), PYTHONDONTWRITEBYTECODE='1')
    env.pop('SMSRECOMP_LIBRARY_DIR', None)
    command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', rom, '--output', output, '--jobs', '1', '--force',
               '--no-shared-base', '--no-online-cover', '--system', 'nes']
    with log.open('wb') as stream:
        done = run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if done.returncode:
        raise SystemExit(f'conversion failed ({done.returncode}); see {log}')
    games = list((output / 'Nintendo NES').glob('*.exe'))
    if len(games) != 1:
        raise SystemExit(f'expected one executable, found {[game.name for game in games]}')
    return games[0]


def play(executable: Path) -> None:
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    done = run([executable, '--frames', '60'], cwd=executable.parent, env=env, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT, timeout=300)
    if done.returncode:
        raise SystemExit(f'the game exited with {done.returncode}: {done.stdout[-500:]!r}')


def battery_file(executable: Path) -> Path:
    files = sorted((executable.parent / 'datas' / 'games').glob('*.sav'))
    if len(files) != 1:
        raise SystemExit(f'expected one battery file under datas/games, found {[file.name for file in files]}')
    return files[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--work', type=Path, default=ROOT / '.build' / 'nes-saves-check')
    work = parser.parse_args().work.resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    rom = work / f'{TITLE}.nes'
    rom.write_bytes(authored_cartridge())
    output, library = work / 'output', work / 'library'
    library.mkdir()
    executable = convert(rom, output, library, work / 'conversion-1.log')
    if (executable.parent / 'datas' / 'games').exists() and list((executable.parent / 'datas' / 'games').glob('*.sav')):
        raise SystemExit('the conversion left a battery file beside the export: its probes must run on private copies')
    play(executable)
    first = battery_file(executable).read_bytes()
    play(executable)
    second = battery_file(executable).read_bytes()
    executable = convert(rom, output, library, work / 'conversion-2.log')
    kept = battery_file(executable).read_bytes()
    after_conversion = hashlib.sha256(kept).hexdigest()
    play(executable)
    third = battery_file(executable).read_bytes()
    result = {'first_launch': list(first[:2]), 'second_launch': list(second[:2]),
              'after_second_conversion_unchanged': kept == second,
              'new_build_launch': list(third[:2]), 'battery_bytes': len(third), 'sha256_after_conversion': after_conversion}
    ok = (first[:2] == bytes([0xA5, 1]) and second[:2] == bytes([0xA5, 2]) and result['after_second_conversion_unchanged']
          and third[:2] == bytes([0xA5, 3]))
    result['passed'] = ok
    print(json.dumps(result), flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
