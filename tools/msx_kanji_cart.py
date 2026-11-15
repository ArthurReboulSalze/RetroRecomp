"""An authored MSX2+ cartridge that reads the kanji font (no game data): a plain 16 KiB cartridge at 4000h that, once a frame,
selects the next of 64 glyphs of JIS level 1 row 4 (ports D8h-D9h), reads its 32 bytes from port D9h, adds them up and shows
the sum's low four bits as the border colour. Without a font every read is FFh and the border stays still; with the player's
font it follows the glyphs. It proves the kanji path end to end: the font in the game, the native run equal to the
reference. Our own code; MIT, Retro-Recomp.

    python tools/msx_kanji_cart.py OUT.rom
"""
import sys
from pathlib import Path

SIZE = 0x4000
BASE = 0x4000
COUNTER = 0xC100


def image() -> bytes:
    rom = bytearray(SIZE)
    rom[0:2] = b'AB'
    rom[2:4] = (BASE + 0x10).to_bytes(2, 'little')
    code = bytearray()
    code += bytes((0xAF, 0x32, COUNTER & 0xFF, COUNTER >> 8))            # XOR A / LD (C100h),A
    code += bytes((0xFB,))                                               # EI
    loop = len(code)
    code += bytes((0x76,))                                               # loop: HALT
    code += bytes((0x3A, COUNTER & 0xFF, COUNTER >> 8, 0x3C))            # LD A,(C100h) / INC A
    code += bytes((0x32, COUNTER & 0xFF, COUNTER >> 8))                  # LD (C100h),A
    code += bytes((0xE6, 0x3F, 0xD3, 0xD8))                              # AND 3Fh / OUT (D8h),A: the glyph in the row
    code += bytes((0x3E, 0x04, 0xD3, 0xD9))                              # LD A,4 / OUT (D9h),A: row 4
    code += bytes((0x01, 0x00, 0x20))                                    # LD BC,2000h: B = 32 bytes, C = 0
    read = len(code)
    code += bytes((0xDB, 0xD9, 0x81, 0x4F))                              # read: IN A,(D9h) / ADD A,C / LD C,A
    code += bytes((0x10, (read - (len(code) + 2)) & 0xFF))               # DJNZ read
    code += bytes((0x79, 0xE6, 0x0F, 0xD3, 0x99, 0x3E, 0x87, 0xD3, 0x99))   # LD A,C / AND 0Fh / border = A (VDP R#7)
    code += bytes((0x18, (loop - (len(code) + 2)) & 0xFF))               # JR loop
    rom[0x10:0x10 + len(code)] = code
    return bytes(rom)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    Path(sys.argv[1]).write_bytes(image())
    return 0


if __name__ == '__main__':
    sys.exit(main())
