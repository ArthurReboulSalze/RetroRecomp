"""MSX native code checked against the reference: the cartridge and the BIOS translated ahead of time by the shared banked
Z80 chain, run headless, compared with the reference interpreter state for state.

The machine description is the MSX profile's (systems/msx.py, MSX_MACHINE) and the pipeline is the conversion's
(retrorecomp/msx_build.py): for each cartridge a work folder (.build/msx-native/<name>/) gets the generated bodies of the
cartridge and of the BIOS (C-BIOS 0.29a's main and logo ROMs), the learning passes, and a project with the headless native
runner (native/msx_machine/msx_native_main.c) and the reference runner (msx_reference_main.c) built from the same machine.
Both run with the same options and are compared: CPU registers, RAM, VRAM, the picture, the sound, frames, cycles and
interrupts. A development check: nothing here makes a game.

    python -B tools/msx_native.py [--frames 300] [--only NAME]...
    python -B tools/msx_native.py --library <ROM folder> --game "msx1/Road Fighter (Japan).zip" ...

With --game the player's cartridges are converted the same way: the zip member is read into memory; the work folder
holds it only while the generator runs (then it is deleted; the runs read it on their standard input). Generated bodies
and pictures of a commercial game stay under .build, never committed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import msx_reference  # noqa: E402
from retrorecomp import msx_build, msx_rom  # noqa: E402
from retrorecomp.msx_build import COMPARED  # noqa: E402,F401  (the fields compared, named here for the tests)
from retrorecomp.systems.msx import MSX_MACHINE  # noqa: E402,F401

WORK = ROOT / '.build' / 'msx-native'


def _loop_cartridge(code: bytes) -> bytes:
    image = bytearray(b'\xFF' * 0x4000)
    image[0:16] = b'AB' + (0x4010).to_bytes(2, 'little') + bytes(12)
    image[0x10:0x10 + len(code)] = code
    return bytes(image)


def cartridge_prefix_io() -> bytes:
    """VDP register 7 (the border) written through OUT (C),A behind a redundant DD prefix, forever: the I/O of a prefix
    chain must happen at the chain's start, as the reference runs the chain as one instruction."""
    code = bytes([0x0E, 0x99,                          # 4010h: LD C,99h
                  0x3E, 0x01, 0xDD, 0xED, 0x79,        # 4012h: loop: LD A,1;   DD OUT (C),A
                  0x3E, 0x87, 0xDD, 0xED, 0x79,        #        LD A,87h; DD OUT (C),A   (R#7 = 1)
                  0x3E, 0x0F, 0xDD, 0xED, 0x79,        #        LD A,0Fh; DD OUT (C),A
                  0x3E, 0x87, 0xDD, 0xED, 0x79,        #        LD A,87h; DD OUT (C),A   (R#7 = 15)
                  0x18, 0xEA])                         # 4026h: JR loop (4028h - 22 = 4012h)
    return _loop_cartridge(code)


def cartridge_ei_ex() -> bytes:
    """EI; EX (SP),IX; JR back, forever: an interrupt is accepted after the EX, never right after the EI; the run must
    stop at the frame limit on the same instruction boundary as the reference."""
    return _loop_cartridge(bytes([0xFB, 0xDD, 0xE3, 0x18, 0xFB]))


def cartridge_scc_window() -> bytes:
    """A Konami SCC cartridge whose code runs at 8000h-97FFh while the SCC answers at 9800h-9FFFh, and calls two
    instructions it wrote into the SCC's wave memory (INC A; RET at 9800h): the guarded sub-window of the region."""
    init = (msx_reference.PAGE2 + msx_reference._ld_write(0x7000, 5) + msx_reference._ld_write(0xB000, 15)
            + msx_reference._ld_write(0x9000, 0x3F)                               # the SCC on: 8000h-9FFFh shows block 15
            + msx_reference._ld_write(0x9800, 0x3C) + msx_reference._ld_write(0x9801, 0xC9)
            + bytes([0xC3, 0x00, 0x80]))                                          # JP 8000h
    image = bytearray(msx_reference._cartridge(0x20000, init))
    for block in range(16):
        image[block * 0x2000 + 0x1FFF] = 0xC0 + block
    image[15 * 0x2000:15 * 0x2000 + 11] = bytes([0x3A, 0x00, 0xE0,               # 8000h: LD A,(E000h)
                                                 0xCD, 0x00, 0x98,               #        CALL 9800h
                                                 0x32, 0x00, 0xE0,               #        LD (E000h),A
                                                 0x18, 0xF5])                    #        JR 8000h
    return bytes(image)


def padded(image: bytes) -> bytes:
    """The cartridge as the machine sees it (msx_build.padded on the guessed mapper)."""
    return msx_build.padded(image, msx_rom.guess(image).mapper)


def compare(name: str, image: bytes | None, args: list[str], bios_image: bytes, keep_rom: bool = True) -> dict:
    """Learn the code the interpreter ran from RAM (msx_build.learn: at most three passes), then compare a run of the native
    runner with the reference runner built beside it."""
    work = WORK / name
    (work / 'native.patterns').unlink(missing_ok=True)
    cartridge = padded(image) if image is not None else b'\xFF' * 0x2000
    check, passes = msx_build.learn(work, cartridge, bios_image, args, keep_rom=keep_rom, insert=image is not None)
    inserted = cartridge if image is not None else None
    reference = msx_build.run(msx_build.build(work, ('msx_reference',))['msx_reference'], args, inserted)
    native = msx_build.run(check, args, inserted)
    native['passes'] = passes
    executed = native['native_steps'] + native['fallback_steps']           # instructions, HALT cycles apart
    return {'native': native, 'reference': reference, 'differences': msx_build.differences(native, reference),
            'native_share': native['native_steps'] / max(1, executed)}


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')     # the report holds non-ASCII names; a redirected Windows console is cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--only', action='append')
    parser.add_argument('--json', type=Path)
    parser.add_argument('--library', type=Path, help="the player's ROM folder, read in place (with --game)")
    parser.add_argument('--game', action='append', help='a cartridge of the library, e.g. "msx1/Road Fighter (Japan).zip"')
    parser.add_argument('--model', choices=('msx1', 'msx2'), default='msx1',
                        help='msx2: the MSX2 board (V9938, mapper RAM, RTC, C-BIOS MSX2 with its sub-ROM)')
    args = parser.parse_args()
    roms = msx_reference.cbios()
    if args.model == 'msx2':
        from retrorecomp import msx_cbios
        bios_image = msx_cbios.image('ntsc', lambda text: None, 'msx2')
        bios = ['--main', str(roms / 'cbios_main_msx2.rom'), '--logo', str(roms / 'cbios_logo_msx2.rom'),
                '--sub', str(roms / 'cbios_sub.rom')]
    else:
        bios_image = (roms / 'cbios_main_msx1.rom').read_bytes() + (roms / 'cbios_logo_msx1.rom').read_bytes()
        bios = ['--main', str(roms / 'cbios_main_msx1.rom'), '--logo', str(roms / 'cbios_logo_msx1.rom')]
    global WORK
    if args.model == 'msx2':
        WORK = WORK.with_name('msx2-native')
    frames = ['--frames', str(args.frames)]
    watch = [w for a in (0xE000, 0xE001, 0xE002, 0xE003, 0xFC9E, 0xFC9F) for w in ('--watch', f'{a:04X}')]
    cases = {'no-cartridge': None, 'authored16': msx_reference.cartridge_16k(), 'authored32': msx_reference.cartridge_32k(),
             'polling': msx_reference.cartridge_polling(), 'sound': msx_reference.cartridge_sound(),
             'odd-size-12k': msx_reference.cartridge_16k()[:0x3000], 'prefix-io': cartridge_prefix_io(),
             'ei-ex': cartridge_ei_ex(),
             # A size 512 bytes above 16 KB (a Sega parser would strip such a file), and the SCC window.
             'odd-size-16k-512': msx_reference.cartridge_16k() + bytes([0x00, 0xC9] * 256),
             'scc-window': cartridge_scc_window()}
    for kind in msx_reference.MAPPER_CARTRIDGES:
        cases[f'mapper-{kind}'] = msx_reference.cartridge_mapper(kind)
    if args.model == 'msx2':
        cases['msx2-screen'] = msx_reference.cartridge_msx2_screen()
        cases['msx2-commands'] = msx_reference.cartridge_msx2_commands()
    players = set()
    if args.game:
        import msx_first_read
        cases = {}
        for game in args.game:
            name = msx_first_read.slug(game)
            cases[name] = msx_first_read.read_rom(args.library / game)
            players.add(name)
    results, failures = {}, []
    for name, image in cases.items():
        if args.only and name not in args.only:
            continue
        extra = msx_rom.guess(image).arguments() if image is not None else []
        print(f'{name}: building and running', flush=True)
        start = (['--event', '600:key:8:0:1', '--event', '610:key:8:0:0', '--event', '660:joy:0:2F',
                  '--event', '670:joy:0:3F'] if name in players else [])
        result = compare(name, image, [*bios, *extra, *frames, *watch, *start], bios_image, name not in players)
        results[name] = result
        n = result['native']
        print(f"  guarded native steps {n['guarded_steps']}")
        print(f"  passes (fallback steps) {n['passes']}; native {n['native_steps']} + halt {n['halt_steps']} steps, fallback {n['fallback_steps']} steps "
              f"({n['fallback_cycles']} cycles) at {n['fallback_at']}; translated share of executed instructions {result['native_share']:.4%}")
        if result['differences']:
            failures.append(name)
            for key, (got, want) in result['differences'].items():
                print(f'  DIFFERS {key}: native {got}, reference {want}')
        else:
            print(f'  equal to the reference on {len(COMPARED)} fields (frame trace included) after {n["frames"]} frames')
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding='utf-8')
    print('MSX native:', 'PASS' if not failures else f'{len(failures)} differ: {", ".join(failures)}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
