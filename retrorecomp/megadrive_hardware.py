"""Cartridge hardware declarations, independent of filenames and AOT roots.

Circuit identities follow Genesis Plus GX's published I2C board catalogue:
https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/cart_hw/eeprom_i2c.c
Supported devices use RetroRecomp's manufacturer-derived wire model.
"""
import re

# Chip and wiring family are different capabilities. In particular, the
# original X24C01 uses a seven-bit address command, not the 24Cxx device byte.
EEPROM_PRODUCTS = {
    'T-12046': ('X24C01', 'sega'),
    'T-12053': ('X24C01', 'sega'),
    'T-81033': ('X24C02', 'acclaim_16m'),
    'T-081326': ('X24C02', 'acclaim_16m'),
    'T-81406': ('24C04', 'acclaim_32m'),
}


def bank_mapper(rom):
    """Identify Sega's 512 KiB circuit from a declaration/product, never size.

    Register facts: https://www.plutiedev.com/beyond-4mb . The original
    MK-12056 image has an ordinary system header, so its product is necessary.
    Unknown oversized cartridges must not inherit this wiring automatically.
    """
    system = rom.data[0x100:0x110].decode('ascii', errors='replace').strip('\0 ').upper()
    product = rom.data[0x180:0x18e].decode('ascii', errors='replace').strip('\0 ')
    if system == 'SEGA SSF' or re.fullmatch(r'(?:GM\s+)?MK-12056(?:[\s-].*)?', product):
        return dict(kind='sega_512k', page_bytes=0x80000, guest_bytes=0x400000,
                    implemented=True, source='system' if system == 'SEGA SSF' else 'product')
    return None


def eeprom_device(rom):
    data = rom.data
    if len(data) < 0x1bc:
        return None
    declared = data[0x1b0:0x1b2] == b'RA' and data[0x1b3] == 0x40
    product = data[0x180:0x18e].decode('ascii', errors='replace').strip('\0 ')
    match = re.fullmatch(r'(?:GM\s+)?(T-\d+)(?:[\s-].*)?', product)
    board = EEPROM_PRODUCTS.get(match[1]) if match else None
    if board is not None:
        # Known Sega conversions can replace EEPROM with parallel SRAM. The
        # real header geometry outranks the original product identity there.
        start = int.from_bytes(data[0x1b4:0x1b8], 'big')
        end = int.from_bytes(data[0x1b8:0x1bc], 'big')
        parallel = data[0x1b0:0x1b2] == b'RA' and data[0x1b3] == 0x20 and end > start + 2
        if board[1] == 'sega' and parallel:
            return None
        return dict(chip=board[0], wiring=board[1], header_declared=declared, implemented=True)
    if declared:
        return dict(chip=None, wiring=None, header_declared=True, implemented=False)
    return None
