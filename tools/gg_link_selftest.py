"""Two Game Gears linked by the Gear-to-Gear cable, in one process (native/gg_link.inc), on authored ROMs.

Three programs written for this test (not commercial games; their expected RAM follows the Z80 program and the cable's wiring):
  serial   each console sends its own pad over the serial port, polling TFUL and RRDY, and stores what it receives;
  nmi      the same with the receive NMI: the handler at $0066 reads $04 and counts, and returns with RETN;
  parallel each console drives its pad on the seven EXT lines and stores what it reads back (the cable swaps the bits).
Seat i's pad drives console i (scripted here: RETRO_RECOMP_GG_LINK_PRESS0 / 1). The run is repeated: a linked run is deterministic.
All learning and output stay under .build/.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrorecomp.core import ROOT, convert

PRESS0 = '8:A'            # console 0: button 1 from frame 8 ($DC bit 4 low: $EF)
PRESS1 = '16:B'            # console 1: button 2 from frame 16 ($DC bit 5 low: $DF)
FRAMES = 160


def rom(program: dict) -> bytes:
    data = bytearray(32768)
    for address, text in program.items():
        code = bytes.fromhex(text)
        data[address:address + len(code)] = code
    data[0x7FF0:0x7FF8] = b'TMR SEGA'
    data[0x7FFF] = 0x70            # Game Gear, international
    return bytes(data)


SERIAL = {
    0x0000: 'F3 31 F0 DF 3E 30 D3 05 21 00 C0',                 # di; ld sp; serial on (SOUT|SIN, 4800); ld hl,$C000
    0x000B: 'DB DC 4F',                                         # loop: in a,($DC); ld c,a
    0x000E: 'DB 05 E6 01 20 FA',                                # wait TFUL clear
    0x0014: '79 D3 03',                                         # send
    0x0017: 'DB 05 E6 02 28 FA',                                # wait RRDY
    0x001D: 'DB 04 77 2C 20 E8 18 FE',                          # in a,($04); ld (hl),a; inc l; loop until 256 bytes are stored, then stop
}
NMI = {
    0x0000: 'C3 00 01',
    0x0066: 'F5 DB 04 32 00 C1 3A 01 C1 3C 32 01 C1 F1 ED 45',  # NMI: save the byte at $C100, count at $C101, retn
    0x0100: 'F3 31 F0 DF 3E 38 D3 05',                          # serial on with RINT
    0x0108: 'DB DC 4F DB 05 E6 01 20 FA 79 D3 03',              # loop: pad, wait TFUL clear, send
    0x0114: '11 00 20 1B 7A B3 20 FB 18 EA',                    # delay, jr loop
}
PARALLEL = {
    0x0000: 'F3 31 F0 DF 3E 80 D3 02 21 00 C0',                 # all seven lines outputs, NMI disabled
    0x000B: 'DB DC D3 01 DB 01 77 2C',                          # loop: pad -> lines; read the lines back; store
    0x0013: '11 00 08 1B 7A B3 20 FB 18 EE',                    # delay, jr loop
}


def program_rom(name: str) -> bytes:
    return rom({'serial': SERIAL, 'nmi': NMI, 'parallel': PARALLEL}[name])


def run_linked(exe: Path, directory: Path, tag: str, seat: int = 1) -> tuple[str, bytes, bytes]:
    environment = os.environ.copy()
    environment.update(RETRO_RECOMP_GG_LINK=str(seat), RETRO_RECOMP_GG_LINK_PRESS0=PRESS0, RETRO_RECOMP_GG_LINK_PRESS1=PRESS1,
        RETRO_RECOMP_GG_LINK_DUMP=str(directory / f'{tag}'), RETRO_RECOMP_GG_LINK_SELFTEST='60', SMSRECOMP_LIBRARY_DIR=str(directory / 'learning'),
        RETRO_RECOMP_LIBRARY_DIR=str(directory / 'learning'))
    log = directory / f'{tag}.log'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(exe), '--headless', '--frames', str(FRAMES), '--log', str(log)], cwd=directory, env=environment,
        capture_output=True, timeout=300, creationflags=flags)
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    if result.returncode or '[link] Gear-to-Gear cable' not in text:
        raise SystemExit(f'{tag}: exit {result.returncode}\n{text[-1500:]}\n{result.stderr.decode(errors="replace")[-800:]}')
    return text, (directory / f'{tag}.1.ram').read_bytes(), (directory / f'{tag}.2.ram').read_bytes()


def received(text: str, console: int) -> int:
    return int(re.search(rf'console {console}:.*?received=(\d+)', text).group(1))


def check(name: str, condition: bool, detail: str = '') -> None:
    print(('PASS ' if condition else 'FAIL ') + name + (f' ({detail})' if detail and not condition else ''))
    if not condition:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=('serial', 'nmi', 'parallel'))
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    directory = ROOT / '.build' / 'gg-link-selftest'
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['RETRO_RECOMP_STILL_ROUTE_OK'] = '1'      # the authored programs have no picture, only RAM
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(Path(tempfile.mkdtemp(prefix='learning-', dir=directory)))
    for name in ('serial', 'nmi', 'parallel'):
        if args.only and args.only != name:
            continue
        source = directory / f'GGLink_{name}.gg'
        source.write_bytes(program_rom(name))
        exe = convert(source, title=f'GGLink_{name}', backend='banked', output=directory / f'GGLink_{name}', frames=5, passes=1,
                      online_cover=False)
        work = directory / f'run_{name}'
        work.mkdir(exist_ok=True)
        text, ram1, ram2 = run_linked(exe, work, 'a')
        again_text, again1, again2 = run_linked(exe, work, 'b')
        check(f'{name}: two consoles ran, {FRAMES} frames each', all(f'console {c}: frame={FRAMES} ' in text for c in (1, 2)))
        check(f'{name}: a second linked run is identical (RAM of both consoles)', ram1 == again1 and ram2 == again2)
        check(f'{name}: rollback of the pair (save, 40 frames, load, same 40 frames: same digests)', 'rollback check PASS' in text, repr(re.findall(r'rollback check[^\n]*', text)[-3:]))
        check(f'{name}: no interpreter fallback is hidden', 'fallback_steps=0' in text, re.findall(r'\[banked\][^\n]*', text)[-1:][0] if '[banked]' in text else '')
        if name == 'serial':
            first, second = ram1[:256], ram2[:256]       # what console 1 received (console 2's pad) and what console 2 received
            check('serial: console 1 received the pad of console 2 (idle, then button 2)', {0xFF, 0xDF} <= set(first) and 0xEF not in set(first), f'{set(first)}')
            check('serial: console 2 received the pad of console 1 (idle, then button 1)', {0xFF, 0xEF} <= set(second) and 0xDF not in set(second), f'{set(second)}')
            check('serial: the bytes crossed in order, idle before the press', first[0] == 0xFF and second[0] == 0xFF and first.index(0xDF) > second.index(0xEF) - 1)
            check('serial: every byte sent was received but the last', received(text, 1) >= 250 and received(text, 2) >= 250, f'{received(text, 1)} / {received(text, 2)}')
        elif name == 'nmi':
            for console, ram in ((1, ram1), (2, ram2)):
                count = ram[0x101]
                check(f'nmi: console {console} took one NMI per byte received', count > 20 and abs(count - received(text, console)) <= 1,
                      f'{count} NMI, {received(text, console)} bytes')
            check('nmi: the handler read the other console\'s pad', ram1[0x100] == 0xDF and ram2[0x100] == 0xEF, f'{ram1[0x100]:02X} {ram2[0x100]:02X}')
        else:
            check('parallel: both consoles read the swapped, wired-AND lines', 0xEF in ram1[:256] and 0xDF in ram2[:256], f'{set(ram1[:256])} {set(ram2[:256])}')
            check('parallel: idle lines read high first', ram1[0] == 0xFF and ram2[0] == 0xFF)
    return 0


if __name__ == '__main__':
    sys.exit(main())
