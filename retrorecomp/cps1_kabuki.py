"""The "Kabuki" Z80 decryption of the CPS-1.5 (QSound) boards, and how the sound CPU's two views of its ROM are used.

The Kabuki is a Z80 module that runs encrypted code: the first 0x8000 bytes of the sound ROM decode to one byte when the CPU
fetches an instruction byte (the M1 cycle: opcodes and prefixes) and to another when it reads data (operands, tables). The
algorithm and the keys come from MAME's `src/mame/capcom/kabuki.cpp` (BSD-3-Clause, Nicola Salmoria; see
licenses/cps1-machine.md). The four key numbers of each game family are catalogue data (`assets/cps1-catalogue.json`,
"kabuki", written by tools/build_cps1_catalogue.py from the pinned MAME source): numbers about the algorithm, never ROM
bytes. Nothing here reads or writes a file.

`decode` returns the two images. The data image replaces the ROM in the board's sound ROM (the CPU's data map); the opcode
image is the view of M1 fetches (MAME's `AS_OPCODES`). Beyond the encrypted range both images are the ROM itself.
"""
from __future__ import annotations

# The bytes that start a longer instruction: the byte that follows each of them is fetched like an opcode (M1), except the
# final byte of DD CB d op / FD CB d op, which is an operand read.
PREFIXES = (0xcb, 0xed, 0xdd, 0xfd)


def keys_for(game: dict, catalogue: dict | None = None) -> dict | None:
    """The Kabuki keys of a set (its driver's init function names them), or None for a board without a Kabuki."""
    if catalogue is None:
        from . import cps1_catalogue
        catalogue = cps1_catalogue.catalogue()
    return catalogue.get('kabuki', {}).get(game.get('init'))


def _swap1(value: int, key: int, select: int) -> int:
    if select & (1 << ((key >> 0) & 7)):
        value = (value & 0xfc) | ((value & 0x01) << 1) | ((value & 0x02) >> 1)
    if select & (1 << ((key >> 4) & 7)):
        value = (value & 0xf3) | ((value & 0x04) << 1) | ((value & 0x08) >> 1)
    if select & (1 << ((key >> 8) & 7)):
        value = (value & 0xcf) | ((value & 0x10) << 1) | ((value & 0x20) >> 1)
    if select & (1 << ((key >> 12) & 7)):
        value = (value & 0x3f) | ((value & 0x40) << 1) | ((value & 0x80) >> 1)
    return value


def _swap2(value: int, key: int, select: int) -> int:
    if select & (1 << ((key >> 12) & 7)):
        value = (value & 0xfc) | ((value & 0x01) << 1) | ((value & 0x02) >> 1)
    if select & (1 << ((key >> 8) & 7)):
        value = (value & 0xf3) | ((value & 0x04) << 1) | ((value & 0x08) >> 1)
    if select & (1 << ((key >> 4) & 7)):
        value = (value & 0xcf) | ((value & 0x10) << 1) | ((value & 0x20) >> 1)
    if select & (1 << ((key >> 0) & 7)):
        value = (value & 0x3f) | ((value & 0x40) << 1) | ((value & 0x80) >> 1)
    return value


def _rol(value: int) -> int:
    return ((value & 0x7f) << 1) | ((value & 0x80) >> 7)


def decode_byte(value: int, swap_key1: int, swap_key2: int, xor_key: int, select: int) -> int:
    """One byte through the chip's steps: swap, rotate, swap, XOR with the key, rotate, swap, rotate, swap.
    `select` is the 16-bit word made of the byte's address and the address key; its low half picks the first two swaps."""
    value = _swap1(value, swap_key1 & 0xffff, select & 0xff)
    value = _rol(value)
    value = _swap2(value, swap_key1 >> 16, select & 0xff)
    value ^= xor_key
    value = _rol(value)
    value = _swap2(value, swap_key2 & 0xffff, select >> 8)
    value = _rol(value)
    return _swap1(value, swap_key2 >> 16, select >> 8)


def decode(rom: bytes, keys: dict) -> tuple[bytes, bytes]:
    """(opcode image, data image) of a sound ROM, each as long as the ROM.

    An opcode byte at address A uses the select word A + addr_key; a data byte uses (A xor 0x1fc0) + addr_key + 1. The
    address is taken on 16 bits by the chip, and the select word keeps its low 16 bits."""
    base, length = keys['base'], min(keys['length'], len(rom))
    operations = (keys['swap_key1'], keys['swap_key2'], keys['xor_key'])
    opcodes, data = bytearray(rom), bytearray(rom)
    for offset in range(length):
        address = offset + base
        raw = rom[offset]
        opcodes[offset] = decode_byte(raw, *operations, (address + keys['addr_key']) & 0xffff)
        data[offset] = decode_byte(raw, *operations, (((address ^ 0x1fc0) + keys['addr_key'] + 1)) & 0xffff)
    return bytes(opcodes), bytes(data)


def m1_positions(raw: bytes) -> tuple[int, ...]:
    """Which of the first four bytes of an instruction are fetched with M1 (opcode image), given a window whose
    instruction-form bytes are right: the opcode, a prefix byte after CB/ED/DD/FD, and any chain of DD/FD prefixes.
    Operands, displacements and the last byte of DD CB d op / FD CB d op are data reads."""
    positions, pos = [], 0
    while pos < 4:
        positions.append(pos)
        op = raw[pos]
        pos += 1
        if op in (0xcb, 0xed):
            if pos < 4:
                positions.append(pos)
            break
        if op in (0xdd, 0xfd):
            if pos < 4 and raw[pos] == 0xcb:
                positions.append(pos)
                break
            continue
        break
    return tuple(positions)


def window(opcodes: bytes, data: bytes, offset: int) -> bytes:
    """The four bytes the CPU would see from the sound ROM offset: opcode and prefix bytes from the opcode image, the rest
    from the data image. Past the end of the image the first bytes wrap, as the generator's plain window does."""
    size = len(data)
    pick = [(offset + n) % size for n in range(4)]
    # Only bytes that are themselves M1 fetches decide which byte follows an M1 fetch, so the opcode image can be asked for all.
    positions = m1_positions(bytes(opcodes[index] for index in pick))
    return bytes(opcodes[index] if n in positions else data[index] for n, index in enumerate(pick))


# --- The pinned Geolith Z80 core, with instruction fetches told apart from data reads ---------------------------------
#
# The core fetches an instruction byte and an operand with the same `nextb`. For a Kabuki board the opcode (and the prefix
# byte that follows CB, ED, DD or FD) is read from the opcode view through `rr_cps1_z80_read_op` (native/cps1_machine.c); the
# rest of the core, and the translated bodies (they read their operands live), are untouched. The patch is strict: a core that
# differs from the pin makes it fail, as every adaptation of a pinned engine does. A board with no Kabuki keeps the core of the
# pin: this text is only applied for a game whose catalogue entry names keys, or on the reference core, which is built once for
# every set (`rr_cps1_z80_read_op` answers like `nextb` when the board has no opcode image).
NEXT_BYTE = 'static inline uint8_t nextb(z80* const z) {\n  return rb(z, z->pc++);\n}\n'
NEXT_OP = NEXT_BYTE + '''
// Kabuki: an instruction byte is fetched from the opcode view of the sound ROM, an operand from the data view
extern uint8_t rr_cps1_z80_read_op(uint16_t address);
static inline uint8_t nextop(z80* const z) {
  return rr_cps1_z80_read_op(z->pc++);
}
'''
PREFIX_SITES = tuple(
    (f'  case {code}: cyc += 0; cyc += exec_opcode_{name}(z, nextb(z){extra}); break;\n',
     f'  case {code}: cyc += 0; cyc += exec_opcode_{name}(z, nextop(z){extra}); break;\n')
    for code, name, extra in (('0xCB', 'cb', ''), ('0xED', 'ed', ''), ('0xDD', 'ddfd', ', &z->ix'), ('0xFD', 'ddfd', ', &z->iy')))
DISPATCH = '    const uint8_t opcode = nextb(z);\n    cyc += exec_opcode(z, opcode);'
DISPATCH_OP = DISPATCH.replace('nextb', 'nextop')
# What the native dispatcher checks of the live bytes: a constant byte of the instruction form is an M1 fetch except the last
# byte of DD CB d op / FD CB d op.
NATIVE_CHECK = 'uint8_t actual;if(!rr_cps1_z80_code_byte((uint16_t)(z->pc+n),&actual) || actual!=op->bytes[n])return 0;'
NATIVE_CHECK_OP = ('uint8_t actual;if(!rr_cps1_z80_code_byte_m1((uint16_t)(z->pc+n),!(n==3 && (op->bytes[0]==0xdd || op->bytes[0]==0xfd)'
                   ' && op->bytes[1]==0xcb),&actual) || actual!=op->bytes[n])return 0;')


def _once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'Pinned Z80 core changed: cannot patch {what} for the Kabuki.')
    return text.replace(old, new, 1)


def patch_core(source: str) -> str:
    """The core text with the opcode fetch of the step and the four prefix fetches read from the opcode view."""
    source = _once(source, NEXT_BYTE, NEXT_OP, 'the byte fetch')
    for old, new in PREFIX_SITES:
        source = _once(source, old, new, 'a prefix fetch')
    return _once(source, DISPATCH, DISPATCH_OP, 'the opcode fetch')
