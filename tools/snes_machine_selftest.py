"""ROM-free multiplayer checks of the Super Nintendo adapter (rollback snapshot, digest), over an authored cartridge.

    python -B tools/snes_machine_selftest.py                 the authored cartridges (NTSC and PAL, with and without a raster interrupt)
    python -B tools/snes_machine_selftest.py --rom GAME.sfc  the same checks over a game the player owns (never in the repository)
"""
from pathlib import Path
import argparse
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.console16 import prepare16
from retrorecomp.core import run, toolchain

# Native mode, 8-bit registers, stack in WRAM. Reads $213F to set the region bit right, then arms the interrupts and idles:
# NMI alone, or NMI plus a vertical-counter interrupt at line 100 (the handler is the same).
RESET = bytes.fromhex('78 18 fb c2 30 a2 ff 1f 9a e2 30 ad 3f 21 29 10 c9')
# Every interrupt: acknowledge both, count in WRAM, put the pad and the counter into OAM, CGRAM and the sound ports, a DMA into
# VRAM from WRAM, an HDMA channel into a window register from a table in the ROM, then return.
HANDLER = bytes.fromhex(
    'ad 10 42 ad 11 42 ee 00 00 a5 00 ad 18 42 8d 04 21 ad 1a 42 8d 22 21 a5 00 8d 02 21 9c 03 21 8d 04 21 '
    'a5 00 8d 40 21 a5 01 8d 41 21 '
    'a9 80 8d 15 21 a9 00 8d 16 21 a5 00 29 3f 8d 17 21 '
    'a9 01 8d 00 43 a9 18 8d 01 43 a9 00 8d 02 43 a9 00 8d 03 43 a9 00 8d 04 43 a9 40 8d 05 43 a9 00 8d 06 43 a9 01 8d 0b 42 '
    'a9 00 8d 10 43 a9 26 8d 11 43 a9 00 8d 12 43 a9 82 8d 13 43 a9 00 8d 14 43 a9 02 8d 0c 42 '
    '40')
HDMA_TABLE = bytes.fromhex('10 11 10 22 10 33 10 44 10 55 00')


def cartridge(pal: bool, irq: bool) -> bytearray:
    rom = bytearray([0xea] * 0x8000)
    reset = RESET + bytes((0x10 if pal else 0,)) + bytes.fromhex('d0 fe a9 80 8d 00 21')
    reset += bytes.fromhex('a9 64 8d 09 42 a9 00 8d 0a 42 a9 a1 8d 00 42 58' if irq else 'a9 81 8d 00 42')
    reset += bytes.fromhex('cb 80 fd')
    rom[:len(reset)] = reset
    rom[0x100:0x100 + len(HANDLER)] = HANDLER
    rom[0x200:0x200 + len(HDMA_TABLE)] = HDMA_TABLE
    rom[0x7fc0:0x7fd5] = b'RR SNAPSHOT CHECKS'.ljust(21, b' ')
    rom[0x7fd5:0x7fdc] = bytes((0x20, 0, 5, 0, 2 if pal else 1, 0, 0))
    rom[0x7fdc:0x7fe0] = bytes.fromhex('cb ed 34 12')
    rom[0x7fea:0x7fec] = bytes.fromhex('00 81')
    rom[0x7fee:0x7ff0] = bytes.fromhex('00 81')
    rom[0x7ffc:0x7ffe] = bytes.fromhex('00 80')
    return rom


def check(path: Path, label: str, work: Path, frames: int, warm: int) -> dict:
    exe = prepare16(path, 'snes', emit=lambda _: None)
    project = next(parent for parent in exe.parents if (parent / 'CMakeLists.txt').is_file())
    (project / 'console16_main.c').write_text((ROOT / 'native/snes_cpu/machine_checks.c').read_text(), encoding='utf-8')
    cmake, _ = toolchain()
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=work / (label + '-build.log'))
    result = json.loads(run([exe, str(frames), str(warm)], cwd=work).strip().splitlines()[-1])
    return result | {'case': label}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rom', action='append', default=[], help='a game of the player instead of the authored cartridges')
    parser.add_argument('--frames', type=int, default=40)
    parser.add_argument('--warm-up', type=int, default=30)
    args = parser.parse_args()
    work = ROOT / '.build/snes-machine-selftest'
    work.mkdir(parents=True, exist_ok=True)
    cases = []
    if args.rom:
        for rom in args.rom:
            cases.append(check(Path(rom), Path(rom).stem, work, args.frames, args.warm_up))
    else:
        for pal in (False, True):
            for irq in (False, True):
                label = ('pal' if pal else 'ntsc') + ('-irq' if irq else '')
                path = work / (label + '.sfc')
                path.write_bytes(cartridge(pal, irq))
                case = check(path, label, work, args.frames, args.warm_up)
                # The authored cartridges make no sound; their pictures must repeat too.
                assert case['picture_differences'] == 0 and case['sound_differences'] == 0, case
                cases.append(case)
    result = {'cases': cases, 'checks': sum(c['checks'] for c in cases), 'passed': all(c['passed'] for c in cases)}
    (work / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
