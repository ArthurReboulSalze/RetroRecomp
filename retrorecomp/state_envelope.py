"""The quick-state envelope of the Z80 machines (native/state_envelope.h, with the build binding of native/state_file.h) seen from the
converter: the damaged copies of a state that a game must refuse. MIT, Retro-Recomp.

The envelope: magic at 0, schema at 8, machine at 12, the identity (64 characters) at 16, the body's length at 80, its CRC-32 at 84,
then the body at 88, whose first bytes are the build binding when the machine has one (state_file.h). The list below is the one the
MSX, the SG-1000, the Amiga and the Nintendo 64 conversions each carry for their own states; the Amstrad CPC is its first user here.
The others move onto it on their own branches (moving them would move their stamps), with the same labels, so their reports do not
change. Game role, the group shares:z80_chain_state of retrorecomp/stamp_inputs.py.
"""
from __future__ import annotations

HEADER = 88
OFFSETS = {'magic': 0, 'schema': 8, 'machine': 12, 'identity': 16, 'length': 80, 'crc': 84, 'binding': HEADER}


def damaged_states(state: bytes) -> dict[str, bytes]:
    """Damaged copies of a quick state, by what is wrong with them: the game must refuse every one (its exit code 4) and leave the
    file as it was. A field of the header or the binding with one bit flipped, the last byte of the body flipped, the state cut at
    several places, an empty file and a file that is not a state."""
    def flipped(offset: int) -> bytes:
        data = bytearray(state)
        data[offset] ^= 0x80
        return bytes(data)
    variants = {'empty': b'', 'header-cut': state[:40], 'one-byte-short': state[:-1], 'body-cut': state[:len(state) // 2]}
    variants.update({label: flipped(offset) for label, offset in OFFSETS.items() if offset < len(state)})
    variants.update({'payload': flipped(len(state) - 1), 'not-a-state': b'not a state.' * 4096})
    return variants
