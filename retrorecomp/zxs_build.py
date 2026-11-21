"""The ZX Spectrum on the banked Z80 chain: the machine image a converted snapshot starts from (docs/ZX_SPECTRUM.md).

The image is what native/zxs_machine/zxs_machine.c loads (`zxs_load_image`): a 64-byte header (the model, the ports, the
CPU's registers, the T-state within the frame) and the eight RAM banks of 16 KiB. It is built from the snapshot alone; the ROM
is the machine's other input (retrorecomp/zxs_roms.py). The generated bodies, the project and the runs come with the
conversion of stage 2.
"""
from __future__ import annotations

import struct

from .zxs_snapshot import JOYSTICKS, PAGE, Snapshot

IMAGE_HEADER = 64
IMAGE_BYTES = IMAGE_HEADER + 8 * PAGE
# The T-state a snapshot that does not say starts at: the end of the /INT pulse (32 T on the 48K, 36 T on the 128K), so that a
# snapshot taken in its interrupt handler is not interrupted again at once.
INT_END = {'16k': 32, '48k': 32, '128k': 36}
MODEL_BYTE = {'16k': 0, '48k': 0, '128k': 1}
REGISTERS = ('af', 'bc', 'de', 'hl', 'af_', 'bc_', 'de_', 'hl_', 'ix', 'iy', 'sp', 'pc')


def zxs_image(snapshot: Snapshot) -> bytes:
    """The machine image of `snapshot` (IMAGE_BYTES), as zxs_load_image reads it."""
    regs = snapshot.registers
    joystick = JOYSTICKS.index(snapshot.joystick) if snapshot.joystick in JOYSTICKS else 0xFF
    ay = snapshot.ay_registers or (0,) * 16
    header = bytearray(IMAGE_HEADER)
    header[0:4] = b'ZXS1'
    header[4] = MODEL_BYTE[snapshot.model]
    header[5] = 1 if snapshot.model == '16k' else 0
    header[6] = joystick
    header[7] = snapshot.border & 7
    header[8] = snapshot.port_7ffd or 0
    header[9] = (snapshot.ay_select or 0) & 15
    header[10:26] = bytes(value & 0xFF for value in ay)
    header[26:31] = bytes((regs['im'] & 3, regs['iff1'] & 1, regs['iff2'] & 1, regs['i'] & 0xFF, regs['r'] & 0xFF))
    header[32:56] = struct.pack('<12H', *(regs[name] & 0xFFFF for name in REGISTERS))
    tstates = snapshot.tstates if snapshot.tstates is not None else INT_END[snapshot.model]
    header[56:60] = struct.pack('<I', tstates)
    banks = b''.join(snapshot.banks.get(bank, bytes(PAGE)) for bank in range(8))
    return bytes(header) + banks
