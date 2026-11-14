"""An authored MSX2+ cartridge that plays MSX-MUSIC (no game data): a plain 16 KiB cartridge at 4000h whose start sets channel 0 of
the YM2413 (ports 7Ch-7Dh) to a built-in instrument and, once a frame, steps a counter: every 16 frames it keys the next note of
an eight-note scale on, and it sets the border colour from the counter, so the picture moves too. It proves the MSX2+'s YM2413 end to
end: the chip in the mix, the native run equal to the reference, the quick state. Our own code; MIT, Retro-Recomp.

    python tools/msx_fm_cart.py OUT.rom
"""
import sys
from pathlib import Path

SIZE = 0x4000
BASE = 0x4000
COUNTER = 0xC100
# F-numbers of a C major scale in block 4 (YM2413 application manual, table of F-numbers for 3.58 MHz).
SCALE = (172, 193, 217, 230, 258, 290, 326, 345)


def out(register: int, value_from_a: bool = False, value: int = 0) -> bytes:
    """Write YM2413 register `register`: the value is A when `value_from_a`, else the constant `value`."""
    code = bytes((0xF5,)) if value_from_a else b''                       # PUSH AF
    code += bytes((0x3E, register, 0xD3, 0x7C))                          # LD A,reg / OUT (7Ch),A
    code += bytes((0xE3, 0xE3))                                          # EX (SP),HL twice: a short wait
    code += bytes((0xF1,)) if value_from_a else bytes((0x3E, value))     # POP AF / LD A,value
    code += bytes((0xD3, 0x7D))                                          # OUT (7Dh),A
    code += bytes((0xE3, 0xE3))
    return code


def image() -> bytes:
    rom = bytearray(SIZE)
    rom[0:2] = b'AB'
    init = BASE + 0x10
    rom[2:4] = init.to_bytes(2, 'little')
    scale_at = BASE + 0x300
    code = bytearray()
    code += bytes((0xF3,))                                               # DI
    code += out(0x30, value=0x10)                                        # channel 0: instrument 1 (violin), loudest
    code += bytes((0xAF, 0x32, COUNTER & 0xFF, COUNTER >> 8))            # XOR A / LD (C100h),A
    code += bytes((0xFB,))                                               # EI
    loop = len(code)
    code += bytes((0x76,))                                               # loop: HALT
    code += bytes((0x3A, COUNTER & 0xFF, COUNTER >> 8, 0x3C))            # LD A,(C100h) / INC A
    code += bytes((0x32, COUNTER & 0xFF, COUNTER >> 8))                  # LD (C100h),A
    code += bytes((0xF5, 0xE6, 0x0F, 0xD3, 0x99, 0x3E, 0x87, 0xD3, 0x99, 0xF1))   # border = A & 0Fh (VDP R#7)
    code += bytes((0xF5, 0xE6, 0x0F))                                    # PUSH AF / AND 0Fh
    skip = len(code)
    code += bytes((0x20, 0x00))                                          # JR NZ,next (patched below)
    code += bytes((0xF1, 0xF5))                                          # POP AF / PUSH AF
    code += bytes((0x0F, 0x0F, 0x0F, 0x0F, 0xE6, 0x07))                  # RRCA x4 / AND 7: the note
    code += bytes((0x5F, 0x16, 0x00, 0x21, scale_at & 0xFF, scale_at >> 8, 0x19, 0x19))   # LD E,A / LD D,0 / LD HL,scale / ADD HL,DE x2
    code += out(0x20, value=0x00)                                        # key off
    code += bytes((0x7E,)) + out(0x10, value_from_a=True)                # LD A,(HL): F-number low
    code += bytes((0x23, 0x7E)) + out(0x20, value_from_a=True)           # INC HL / LD A,(HL): key on, block, F-number high
    next_at = len(code)
    code[skip + 1] = (next_at - (skip + 2)) & 0xFF
    code += bytes((0xF1,))                                               # next: POP AF
    code += bytes((0x18, (loop - (len(code) + 2)) & 0xFF))               # JR loop
    assert len(code) < 0x2F0
    rom[0x10:0x10 + len(code)] = code
    for i, f in enumerate(SCALE):                                        # per note: F-number low, then key on | block 4 | bit 8
        rom[0x300 + 2 * i] = f & 0xFF
        rom[0x301 + 2 * i] = 0x10 | (4 << 1) | (f >> 8)
    return bytes(rom)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    Path(sys.argv[1]).write_bytes(image())
    return 0


if __name__ == '__main__':
    sys.exit(main())
