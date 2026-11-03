"""Authored ExHiROM cartridge (map $25/$35, an image above 4 MiB): which half of the ROM each bank reaches.

The ExHiROM map of the board (the address line A23 picks the half): banks $C0-$FF and $80-$BF (upper half of the bank, $8000-$FFFF)
reach the first 4 MiB of the ROM; banks $40-$7D and $00-$3F (upper half of the bank) reach the ROM from $400000 up. The reset vector
is read at $00:FFFC, so it sits at ROM $40FFFC: the header (and its vectors) is at $40FFC0, which is why such a cartridge has no
usable header in the first 4 MiB. This is the map of the SNES developer documentation, written here as the expected values: the
cartridge below has one marker byte in each half, at the same bank offset, and its program reads them through the four views and stops
in a loop that says whether each read gave the marker of its half. The image is 4 MiB and one 64 KiB bank (the smallest above 4 MiB
that the board map reaches). It checks the adapter's map against that documentation, not independent hardware accuracy, and it
contains no byte of any game.

    python tools/snes_exhirom_selftest.py
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import supernintendo  # noqa: E402
from retrorecomp.cartridge16 import read_snes_rom  # noqa: E402
from retrorecomp.console16 import prepare16, probe16, reference_differences  # noqa: E402
from tools.snes_saves_check import long_address  # noqa: E402

LOW, HIGH = 0x11, 0x22                 # the markers of the first and of the second 4 MiB
OFFSET = 0x9234                        # the same offset inside the upper half of a bank
IMAGE_BYTES = 0x410000                 # 4 MiB and one bank


def cartridge():
    rom = bytearray(IMAGE_BYTES)
    rom[OFFSET] = LOW                  # ROM $009234: $C0:9234 and $80:9234
    rom[0x400000 + OFFSET] = HIGH      # ROM $409234: $40:9234 and $00:9234
    # The program is at ROM $408000 = $00:8000 and $40:8000 (the reset vector points at $00:8000). Four reads, each compared with
    # the marker its half must give; a wrong one goes to its own failure loop. The picture changes every frame so that the
    # conversion's liveness check sees a running game.
    views = (('c0', 0xc00000 + OFFSET, LOW), ('80', 0x800000 + OFFSET, LOW), ('40', 0x400000 + OFFSET, HIGH), ('00', OFFSET, HIGH))
    code = bytearray.fromhex('78 18 fb c2 10 e2 20 a2 ff 1f 9a 9c 00 42 a9 80 8d 00 21')   # SEI CLC XCE REP #$10 SEP #$20 LDX/TXS ...
    fails = []
    for name, address, marker in views:
        code += long_address(0xaf, address)                       # LDA long
        code += bytes((0xc9, marker))                             # CMP #marker
        code += bytes((0xf0, 3))                                  # BEQ over the JMP
        code += bytes((0x4c, 0, 0))                               # JMP fail_<name> (patched below)
        fails.append((len(code) - 2, name))
    code += bytes.fromhex('a9 0f 8d 00 21 a9 81 8d 00 42 cb 80 fd')    # display on, NMI on, WAI loop: the verdict is "reached here"
    base = 0x408000
    failure_at = {}
    for position, name in fails:
        failure_at[name] = len(code)
        code += bytes((0x80, 0xfe))                               # BRA * : the view `name` did not give its marker
    for position, name in fails:
        code[position:position + 2] = (0x8000 + failure_at[name]).to_bytes(2, 'little')
    rom[base:base + len(code)] = code
    nmi = bytes.fromhex('9c 21 21 a5 10 1a 85 10 8d 22 21 9c 22 21 40')
    rom[base + 0x100:base + 0x100 + len(nmi)] = nmi
    header = 0x40ffc0
    rom[header:header + 21] = b'RR EXHIROM FIXTURE'.ljust(21, b' ')
    rom[header + 21:header + 28] = bytes((0x25, 0, 13, 0, 1, 0, 0))   # ExHiROM, no chip, 8 MiB declared, no RAM, NTSC
    rom[header + 0x2a:header + 0x2c] = rom[header + 0x2e:header + 0x30] = (0x8100).to_bytes(2, 'little')
    rom[header + 0x3a:header + 0x3c] = (0x8100).to_bytes(2, 'little')
    rom[header + 0x3c:header + 0x3e] = (0x8000).to_bytes(2, 'little')
    total = (sum(rom) - sum(rom[header + 28:header + 32]) + 0x1fe) & 0xffff
    rom[header + 28:header + 32] = (total ^ 0xffff).to_bytes(2, 'little') + total.to_bytes(2, 'little')
    return bytes(rom), failure_at


def main():
    work = ROOT / '.build/snes-exhirom-selftest'
    work.mkdir(parents=True, exist_ok=True)
    data, failure_at = cartridge()
    path = work / 'authored.sfc'
    path.write_bytes(data)
    rom = read_snes_rom(path)
    profiles = {rom.sha256: {'id': 'fixture-exhirom', 'title': 'exhirom', 'legacy_functions': False, 'standard': 'ntsc',
                             'mapping': rom.mapping}}
    with patch.dict(supernintendo.PROFILES, profiles):
        exe = prepare16(path, 'snes', title='exhirom', emit=lambda text: None)
        native = probe16(exe, work, 40)
        reference = probe16(exe, work, 40, reference=True)
    differences = reference_differences('snes', native, reference)
    assert not differences, differences
    assert not native['interpreted_opcodes'], native['interpreted_opcodes']
    pc = native['cpu_pc']
    failed = [name for name, at in failure_at.items() if pc == 0x8000 + at]
    assert not failed, f'the view of bank ${failed[0]} did not give the marker of its half'
    result = {'passed': True, 'image_bytes': len(data), 'mapping': rom.mapping, 'cpu_pc': pc,
              'views_checked': ['$C0', '$80', '$40', '$00'], 'native_equals_reference': True}
    (work / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
