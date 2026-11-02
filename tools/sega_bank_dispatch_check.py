"""Check that the "functions" engine dispatches a paged address on the bank mapped at run time (Master System / Game Gear).

    python tools/sega_bank_dispatch_check.py WORK

It writes a 128 KiB cartridge of its own (no commercial code) whose main loop pages slot 2 ($8000) from a RAM byte, so the
static walk cannot know the bank: bank 2 for the first LATE frames, bank 5 afterwards, each holding a different function at
$8000 that returns a different colour, painted on the backdrop. LATE is past the frames the conversion runs, so the conversion
learns bank 2 only. Then it checks, on the converted game:
  1. the generated dispatch for $8000 tests the live bank before it calls the one compiled variant (an unguarded call would run
     bank 2's code while bank 5 is mapped, and the run would not even leave a dispatch miss to learn from);
  2. a run of 6,000 frames, past LATE, matches the same run with every instruction interpreted (VDP trace columns except `sp` and
     the sound columns): the late bank went through the counted interpreter, not through the wrong code.
Nothing here says anything about hardware, other mappers, or a game that is not this cartridge."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATE, FRAMES = 5000, 6000


def cartridge() -> bytes:
    """128 KiB, 8 banks of 16 KiB. Main code in the fixed area; bank 2 and bank 5 each hold a function at $8000."""
    rom = bytearray(0x20000)

    def put(address: int, data: bytes) -> None:
        rom[address:address + len(data)] = data

    put(0x0000, bytes([0xF3, 0xED, 0x56, 0x31, 0xF0, 0xDF, 0xC3, 0x00, 0x01]))     # di; im 1; ld sp,$DFF0; jp $0100
    put(0x0038, bytes([0xF5, 0xDB, 0xBF, 0xF1, 0xFB, 0xED, 0x4D]))                  # push af; in a,($BF); pop af; ei; reti
    main = bytes([
        0x3E, 0x04, 0xD3, 0xBF, 0x3E, 0x80, 0xD3, 0xBF,         # VDP register 0 = $04 (mode 4)
        0x3E, 0x60, 0xD3, 0xBF, 0x3E, 0x81, 0xD3, 0xBF,         # VDP register 1 = $60 (display on, frame interrupt)
        0x3E, 0x02, 0x32, 0x00, 0xC0,                           # ld a,2; ld (n),a
        0x21, 0x00, 0x00, 0x22, 0x01, 0xC0,                     # ld hl,0; ld (count),hl
        0xFB,                                                   # ei
        0x76,                                                   # loop: halt
        0x2A, 0x01, 0xC0, 0x23, 0x22, 0x01, 0xC0,               # ld hl,(count); inc hl; ld (count),hl
        0x11, LATE & 0xFF, LATE >> 8, 0xB7, 0xED, 0x52,         # ld de,LATE; or a; sbc hl,de
        0x38, 0x05, 0x3E, 0x05, 0x32, 0x00, 0xC0,               # jr c,+5; ld a,5; ld (n),a   (late: the other bank)
        0x3A, 0x00, 0xC0, 0x32, 0xFF, 0xFF,                     # ld a,(n); ld ($FFFF),a   (the bank comes from RAM)
        0xCD, 0x00, 0x80,                                       # call $8000
        0x47,                                                   # ld b,a
        0x3A, 0x01, 0xC0, 0xE6, 0x03, 0xA8, 0x47,               # ld a,(count); and 3; xor b; ld b,a (the picture moves every frame)
        0x3E, 0x00, 0xD3, 0xBF, 0x3E, 0xC0, 0xD3, 0xBF,         # CRAM address 0 (every blank tile shows it)
        0x78, 0xD3, 0xBE,                                       # ld a,b; out ($BE),a
    ])
    loop = 0x0100 + 8 + 8 + 5 + 6 + 1
    put(0x0100, main + bytes([0x18, (loop - (0x0100 + len(main) + 2)) & 0xFF]))      # jr loop
    put(2 * 0x4000, bytes([0x3E, 0x03, 0xC9]))                  # bank 2 at $8000: ld a,3; ret
    put(5 * 0x4000, bytes([0x3E, 0x0C, 0xC9]))                  # bank 5 at $8000: ld a,12; ret
    rom[0x7FF0:0x7FF8] = b'TMR SEGA'
    rom[0x7FFF] = 0x40
    return bytes(rom)


def trace(path: Path) -> list:
    ignored = {'sp', 'psg_h', 'psg_nz'}
    with path.open(newline='', encoding='utf-8') as source:
        return [{key: value for key, value in row.items() if key not in ignored} for row in csv.DictReader(source)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    rom = work / 'Bank_Dispatch.sms'
    rom.write_bytes(cartridge())
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYTHONIOENCODING='utf-8',
               RETRO_RECOMP_LIBRARY_DIR=str(work / 'library'))
    command = [sys.executable, '-B', 'RetroRecomp.py', 'batch', '--system', 'sms', '--backend', 'functions', '--output', str(work / 'out'),
               '--no-shared-base', '--no-online-cover', '--keep-build', '--jobs', '1', str(rom)]
    done = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    reports = sorted((work / 'out').glob('**/conversion-report.json'))
    assert done.returncode == 0 and reports, 'the conversion failed:\n' + done.stdout[-1500:]
    game = Path(json.loads(reports[-1].read_text(encoding='utf-8'))['build_directory'])

    dispatch = next((game / 'generated').glob('*dispatch*')).read_text(encoding='utf-8')
    guarded = re.search(r'case 0x8000: if \(\(sms_slot_bank\(addr\) % 8\) == 2\) \{ \w+\(\); return; \} break;', dispatch)
    assert guarded, 'the dispatch of $8000 does not test the live bank before calling its one variant'
    print('PASS: the dispatch of $8000 tests the live bank before it calls the one compiled variant (bank 2).')

    executable = next((game / 'build-native').glob('*.exe' if os.name == 'nt' else 'Bank_Dispatch'))
    rows = {}
    for label, extra in (('native', []), ('interpreted', ['--interp'])):
        output = work / f'run-{label}'
        output.mkdir(exist_ok=True)
        subprocess.run([str(executable), '--headless', '--frames', str(FRAMES), '--log', str(output / 'run.log'),
                        '--vdp-trace', str(output / 'vdp.csv'), *extra], cwd=output, env=env, timeout=600,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rows[label] = trace(output / 'vdp.csv')
    log = (work / 'run-native' / 'run.log').read_text(encoding='utf-8', errors='replace')
    calls = int(re.search(r'hybrid\(interp\): (\d+) calls', log)[1])
    assert len(rows['native']) == len(rows['interpreted']) == FRAMES, 'a run stopped early'
    assert rows['native'] == rows['interpreted'], 'the native run differs from the interpreted one after the bank changed'
    assert len({row['cram_h'] for row in rows['native']}) >= 8, 'the backdrop never changed with the bank: the cartridge did not run'
    assert calls > 0, 'the late bank never went through the interpreter'
    print(f'PASS: {FRAMES} frames, past the bank change at frame {LATE}: the VDP trace equals the interpreted run; the late bank went through '
          f'the counted interpreter ({calls} calls).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
