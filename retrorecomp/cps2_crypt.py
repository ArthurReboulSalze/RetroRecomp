"""CPS-2 opcode decryption: the two Feistel networks of the A-board, keyed by the 20-byte key of the player's own romset.

The algorithm and its tables come from MAME's src/mame/capcom/cps2crypt.cpp (BSD-3-Clause, copyright-holders: Paul Leaman, Andreas Naive,
Nicola Salmoria, Charles MacDonald; the encryption was broken by Andreas Naive, see licenses/cps1-machine.md). The tables are in
cps2_tables.py (generated from that file by tools/build_cps2_tables.py); this module is written for the converter: the same function as
MAME's, evaluated through lookup tables so that a 4 MiB program is decrypted in seconds in plain Python.

Only the opcode stream is encrypted: the 68000 fetches instruction words (opcodes, extension words, immediates) and reads its PC-relative
operands through the decryption; every other read of the program ROM sees the stored words. `decrypt` therefore returns a second image of
the program, never a replacement: the converter keeps both (docs/CPS2.md). The key is data the player's romset carries; this module never
holds, ships or fetches one. The hardware's decryption watchdog (battery-backed key RAM that dies) is not modelled, as in MAME.
"""
from __future__ import annotations
from array import array
from functools import lru_cache
import sys

from . import cps2_tables as tables

KEY_BYTES = 20
# What the 160 key bits hold besides the 64-bit key (MAME's notes in init_cps2crypt): words 7 and 8 are constants of every real key.
CHECK_WORDS = (0x4000, 0x0900)


def parse_key(key: bytes) -> dict:
    """The master key (two 32-bit words), the decrypted byte range and the watchdog instruction of a 20-byte key file."""
    if len(key) != KEY_BYTES:
        raise ValueError('A CPS-2 key file is 20 bytes.')
    decoded = [0] * 10
    for bit_index in range(10 * 16):
        bit = (317 - bit_index) % 160
        if (key[bit // 8] >> ((bit ^ 7) % 8)) & 1:
            decoded[bit_index // 16] |= 0x8000 >> (bit_index % 16)
    if (decoded[7], decoded[8]) != CHECK_WORDS:
        raise ValueError('This CPS-2 key file is not a valid key (its constant words are wrong).')
    if decoded[9] == 0xffff:
        # A dead board: the only encrypted range is the upper half of a 128 KiB bank at the top of the address space.
        lower, upper = 0xff0000, 0xffffff
    else:
        lower, upper = 0, (((~decoded[9] & 0x3ff) << 14) | 0x3fff) + 1
    return {'master': ((decoded[0] << 16) | decoded[1], (decoded[2] << 16) | decoded[3]), 'lower': lower, 'upper': upper,
            'watchdog': (decoded[6], decoded[5], decoded[4])}


def _bit(value: int, position: int) -> int:
    return (value >> position) & 1


@lru_cache(maxsize=1)
def _network_tables():
    """Per network: the 16 box lookups (input byte and 6 key bits to output mask) and the bit split / merge tables."""
    result = []
    for boxes, group_a, group_b in ((tables.FN1_BOXES, tables.FN1_GROUP_A, tables.FN1_GROUP_B),
                                    (tables.FN2_BOXES, tables.FN2_GROUP_A, tables.FN2_GROUP_B)):
        luts = []
        for table, inputs, outputs in boxes:
            output = [(1 << outputs[0] if value & 1 else 0) | (1 << outputs[1] if value & 2 else 0) for value in table]
            lookup = []
            for byte in range(256):
                selected = sum(_bit(byte, position) << index for index, position in enumerate(inputs) if position >= 0)
                lookup.extend(output[selected ^ key] for key in range(64))
            luts.append(tuple(lookup))
        left = [sum(_bit(value, group_b[i]) << i for i in range(8)) for value in range(0x10000)]
        right = [sum(_bit(value, group_a[i]) << i for i in range(8)) for value in range(0x10000)]
        merge_left = [sum(_bit(value, i) << group_a[i] for i in range(8)) for value in range(256)]
        merge_right = [sum(_bit(value, i) << group_b[i] for i in range(8)) for value in range(256)]
        result.append((tuple(luts), left, right, merge_left, merge_right))
    return result


def _permutation_tables(bits: tuple, source_bytes: int):
    """A linear bit permutation as lookups: for each source byte and value, the output bits it contributes."""
    rows = []
    for index in range(source_bytes):
        row = []
        for value in range(256):
            out = 0
            for target, source in enumerate(bits):
                if source // 8 == index and _bit(value, source % 8):
                    out |= 1 << target
            row.append(out)
        rows.append(row)
    return rows


@lru_cache(maxsize=1)
def _expansions():
    first = _permutation_tables(tables.EXPAND_FIRST_KEY, 8)
    second = _permutation_tables(tables.EXPAND_SECOND_KEY, 8)
    seed = _permutation_tables(tables.EXPAND_SUBKEY, 2)      # the 16-bit seed expands to 64 bits: one table per seed byte
    return first, second, seed


def _expand(rows, value64: int) -> int:
    out = 0
    for index in range(8):
        out |= rows[index][(value64 >> (8 * index)) & 0xff]
    return out


def _words(key96: int) -> list:
    return [(key96 >> (24 * index)) & 0xffffff for index in range(4)]


def _first_key(master: tuple) -> list:
    first, _, _ = _expansions()
    k = _words(_expand(first, (master[1] << 32) | master[0]))
    k[0] ^= _bit(k[0], 1) << 4
    k[0] ^= _bit(k[0], 2) << 5
    k[0] ^= _bit(k[0], 8) << 11
    k[1] ^= _bit(k[1], 0) << 5
    k[1] ^= _bit(k[1], 8) << 11
    k[2] ^= _bit(k[2], 1) << 5
    k[2] ^= _bit(k[2], 8) << 11
    return k


def _second_key(sub64: int) -> list:
    _, second, _ = _expansions()
    k = _words(_expand(second, sub64))
    k[0] ^= _bit(k[0], 0) << 5
    k[0] ^= _bit(k[0], 6) << 11
    k[1] ^= _bit(k[1], 0) << 5
    k[1] ^= _bit(k[1], 1) << 4
    k[2] ^= _bit(k[2], 2) << 5
    k[2] ^= _bit(k[2], 3) << 4
    k[2] ^= _bit(k[2], 7) << 11
    k[3] ^= _bit(k[3], 1) << 5
    return k


def decrypt(program: bytes, key: bytes) -> bytes:
    """The decrypted opcode image of a program ROM, in the same byte order and length as `program` (the 68000's big-endian words).

    Words outside the key's range are copied unchanged. The input is the program as the 68000 sees it (the region the load operations
    assemble), not the file order of the ROM chips."""
    if len(program) % 2:
        raise ValueError('A CPS-2 program is a whole number of 16-bit words.')
    info = parse_key(key)
    luts_all = _network_tables()
    rom = array('H')
    rom.frombytes(program)
    if sys.byteorder == 'little':
        rom.byteswap()                              # the 68000's big-endian words to host words
    out = array('H', rom)
    words = len(rom)
    lower, upper = info['lower'] // 2, info['upper'] // 2
    keys1 = _first_key(info['master'])
    master = (info['master'][1] << 32) | info['master'][0]
    _, _, seed_rows = _expansions()
    luts1, left1, right1, merge_left1, merge_right1 = luts_all[0]
    luts2, left2, right2, merge_left2, merge_right2 = luts_all[1]
    k10, k11, k12, k13 = keys1
    b1, b2 = seed_rows
    for address in range(min(0x10000, words)):
        # the first network turns the low 16 address bits into a seed
        left, right = left1[address], right1[address]
        for round_, key in ((0, k10), (1, k11), (2, k12), (3, k13)):
            base = round_ * 4
            index = (right if round_ % 2 == 0 else left) << 6
            mask = (luts1[base][index | (key & 63)] | luts1[base + 1][index | ((key >> 6) & 63)]
                    | luts1[base + 2][index | ((key >> 12) & 63)] | luts1[base + 3][index | ((key >> 18) & 63)])
            if round_ % 2 == 0:
                left ^= mask
            else:
                right ^= mask
        seed = merge_left1[left] | merge_right1[right]
        subkey = (b1[seed & 0xff] | b2[seed >> 8]) ^ master
        k20, k21, k22, k23 = _second_key(subkey)
        lut = luts2
        for index in range(address, words, 0x10000):
            if lower <= index <= upper:
                value = rom[index]
                left, right = left2[value], right2[value]
                i = right << 6
                left ^= (lut[0][i | (k20 & 63)] | lut[1][i | ((k20 >> 6) & 63)] | lut[2][i | ((k20 >> 12) & 63)] | lut[3][i | ((k20 >> 18) & 63)])
                i = left << 6
                right ^= (lut[4][i | (k21 & 63)] | lut[5][i | ((k21 >> 6) & 63)] | lut[6][i | ((k21 >> 12) & 63)] | lut[7][i | ((k21 >> 18) & 63)])
                i = right << 6
                left ^= (lut[8][i | (k22 & 63)] | lut[9][i | ((k22 >> 6) & 63)] | lut[10][i | ((k22 >> 12) & 63)] | lut[11][i | ((k22 >> 18) & 63)])
                i = left << 6
                right ^= (lut[12][i | (k23 & 63)] | lut[13][i | ((k23 >> 6) & 63)] | lut[14][i | ((k23 >> 12) & 63)] | lut[15][i | ((k23 >> 18) & 63)])
                out[index] = merge_left2[left] | merge_right2[right]
    if sys.byteorder == 'little':
        out.byteswap()
    return out.tobytes()
