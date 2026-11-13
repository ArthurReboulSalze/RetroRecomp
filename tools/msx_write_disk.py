"""An authored MSX disk that writes (no game data): a 720 KiB FAT12 image whose boot sector, once BASIC has started (through
the H.STKE hook the boot program sets), writes a 512-byte pattern to sector 20 of drive A through PHYDIO (0144h), then waits.
It proves the MSX2+ disk path end to end on a game-like disk: the controller's WRITE DATA, the copy kept beside the game and
read back by a fresh process (msx_conversion.check_disks). MIT, Retro-Recomp.

    python tools/msx_write_disk.py OUT.dsk
"""
import sys
from pathlib import Path

SECTOR = 512
SECTORS = 1440                     # 80 tracks, 2 sides, 9 sectors
TARGET = 20                        # a data-area sector of an empty disk
PATTERN = bytes((i * 7 + 0x5A) & 0xFF for i in range(SECTOR))


BASE = 0xC01E                      # where the disk ROM calls the boot sector's program


def boot_code() -> bytes:
    """The program at C01Eh (the boot sector is loaded at C000h). The disk ROM calls it with the carry reset while it starts
    (and with the carry set only to boot MSX-DOS, which this disk has not): it then hooks H.STKE (FEDAh), which BASIC calls
    once everything is started, and returns. From the hook it writes PATTERN (C100h, in this sector) to sector TARGET of
    drive A through PHYDIO and stops."""
    write = bytearray()
    write += bytes((0x3E, 0xC9, 0x32, 0xDA, 0xFE))          # LD A,C9h / LD (FEDAh),A   the hook is used once
    write += bytes((0x21, 0x00, 0xC1))                      # LD HL,C100h    the pattern
    write += bytes((0x11, TARGET & 0xFF, TARGET >> 8))      # LD DE,TARGET   the sector
    write += bytes((0x3E, 0x00))                            # LD A,0         drive A
    write += bytes((0x06, 0x01))                            # LD B,1         one sector
    write += bytes((0x0E, 0xF9))                            # LD C,F9h       media: 720 KiB, two sides
    write += bytes((0xFB,))                                 # EI             the disk ROM times its motor on interrupts
    write += bytes((0x37,))                                 # SCF            write
    write += bytes((0xCD, 0x44, 0x01))                      # CALL 0144h     PHYDIO
    write += bytes((0x18, 0xFE))                            # JR $           done: wait
    install_length = 12                                     # the install part, RET included
    write_at = BASE + 2 + install_length
    code = bytearray()
    code += bytes((0x38, install_length))                   # JR C,write     (the boot call: write at once)
    code += bytes((0x3E, 0xC3, 0x32, 0xDA, 0xFE))           # LD A,C3h / LD (FEDAh),A   JP ...
    code += bytes((0x21, write_at & 0xFF, write_at >> 8))   # LD HL,write
    code += bytes((0x22, 0xDB, 0xFE))                       # LD (FEDBh),HL
    assert len(code) == 2 + install_length - 1
    code += bytes((0xC9,))                                  # RET (carry still reset)
    return bytes(code + write)


def image() -> bytes:
    boot = bytearray(SECTOR)
    boot[0:3] = bytes((0xEB, 0xFE, 0x90))                   # the MSX-DOS boot sector's opening
    boot[3:11] = b'RRWRITE '
    bpb = (SECTOR.to_bytes(2, 'little') + bytes((2,)) + (1).to_bytes(2, 'little') + bytes((2,)) + (112).to_bytes(2, 'little')
           + SECTORS.to_bytes(2, 'little') + bytes((0xF9,)) + (3).to_bytes(2, 'little') + (9).to_bytes(2, 'little')
           + (2).to_bytes(2, 'little') + (0).to_bytes(2, 'little'))
    boot[11:11 + len(bpb)] = bpb
    code = boot_code()
    boot[0x1E:0x1E + len(code)] = code
    boot[0x100:0x100 + SECTOR - 0x100] = PATTERN[:SECTOR - 0x100]   # what fits; the rest of the written sector is boot code
    disk = bytearray(SECTOR * SECTORS)
    disk[0:SECTOR] = boot
    for fat in (1, 4):                                      # two FATs of three sectors: media byte, then FFh FFh
        disk[fat * SECTOR:fat * SECTOR + 3] = bytes((0xF9, 0xFF, 0xFF))
    return bytes(disk)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    Path(sys.argv[1]).write_bytes(image())
    return 0


if __name__ == '__main__':
    sys.exit(main())
