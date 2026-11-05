"""CPS-2 opcode decryption: structure, the key file format, and the lookup-table evaluation against a direct transcription of MAME's.

No ROM and no real key here: the keys are synthetic. That the decryption equals MAME's on real romsets is the job of
tools/cps2_crypt_check.py (run against the player's own sets, results in docs/CPS2.md).
"""
import hashlib
from pathlib import Path
import random
import unittest

from retrorecomp import cps2_crypt, cps2_tables as tables
from tools import build_cps2_tables as builder

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.deps' / ('mame-cps1-' + builder.MAME_REVISION[:7])


def make_key(words: list) -> bytes:
    """A 20-byte key file holding the ten 16-bit words of MAME's decoding (the inverse of cps2_crypt.parse_key)."""
    key = bytearray(20)
    for bit_index in range(160):
        if words[bit_index // 16] & (0x8000 >> (bit_index % 16)):
            bit = (317 - bit_index) % 160
            key[bit // 8] |= 1 << ((bit ^ 7) % 8)
    return bytes(key)


def bit(value, position):
    return (value >> position) & 1


def reference_decrypt_word(value: int, address: int, master: tuple) -> int:
    """MAME's cps2_decrypt for one word, transcribed from the structure of cps2crypt.cpp (sbox objects, no lookup tables)."""
    def box_output(table, inputs, outputs, byte, key):
        selected = sum(bit(byte, position) << index for index, position in enumerate(inputs) if position >= 0)
        out = table[selected ^ (key & 0x3f)]
        return (1 << outputs[0] if out & 1 else 0) | (1 << outputs[1] if out & 2 else 0)

    def fn(byte, boxes, key):
        return (box_output(*boxes[0], byte, key >> 0) | box_output(*boxes[1], byte, key >> 6)
                | box_output(*boxes[2], byte, key >> 12) | box_output(*boxes[3], byte, key >> 18))

    def feistel(word, group_a, group_b, rounds, keys):
        left = sum(bit(word, group_b[i]) << i for i in range(8))
        right = sum(bit(word, group_a[i]) << i for i in range(8))
        left ^= fn(right, rounds[0], keys[0])
        right ^= fn(left, rounds[1], keys[1])
        left ^= fn(right, rounds[2], keys[2])
        right ^= fn(left, rounds[3], keys[3])
        return sum(bit(left, i) << group_a[i] for i in range(8)) | sum(bit(right, i) << group_b[i] for i in range(8))

    def expand(source_bits, source_words, count):
        out = [0, 0, 0, 0]
        for i in range(count):
            out[i // 24] |= bit(source_words[source_bits[i] // 32], source_bits[i] % 32) << (i % 24)
        return out

    def rounds(boxes):
        return [boxes[4 * r:4 * r + 4] for r in range(4)]

    key1 = expand(tables.EXPAND_FIRST_KEY, master, 96)
    key1[0] ^= bit(key1[0], 1) << 4
    key1[0] ^= bit(key1[0], 2) << 5
    key1[0] ^= bit(key1[0], 8) << 11
    key1[1] ^= bit(key1[1], 0) << 5
    key1[1] ^= bit(key1[1], 8) << 11
    key1[2] ^= bit(key1[2], 1) << 5
    key1[2] ^= bit(key1[2], 8) << 11
    seed = feistel(address, tables.FN1_GROUP_A, tables.FN1_GROUP_B, rounds(tables.FN1_BOXES), key1)
    subkey = [0, 0]
    for i in range(64):
        subkey[i // 32] |= bit(seed, tables.EXPAND_SUBKEY[i]) << (i % 32)
    subkey = [subkey[0] ^ master[0], subkey[1] ^ master[1]]
    key2 = expand(tables.EXPAND_SECOND_KEY, subkey, 96)
    key2[0] ^= bit(key2[0], 0) << 5
    key2[0] ^= bit(key2[0], 6) << 11
    key2[1] ^= bit(key2[1], 0) << 5
    key2[1] ^= bit(key2[1], 1) << 4
    key2[2] ^= bit(key2[2], 2) << 5
    key2[2] ^= bit(key2[2], 3) << 4
    key2[2] ^= bit(key2[2], 7) << 11
    key2[3] ^= bit(key2[3], 1) << 5
    return feistel(value, tables.FN2_GROUP_A, tables.FN2_GROUP_B, rounds(tables.FN2_BOXES), key2)


class KeyFileTests(unittest.TestCase):
    WORDS = [0x1234, 0x5678, 0x9abc, 0xdef0, 0x0011, 0x2233, 0x4455, 0x4000, 0x0900, 0x03fe]

    def test_a_synthetic_key_parses_to_its_words(self):
        info = cps2_crypt.parse_key(make_key(self.WORDS))
        self.assertEqual(info['master'], (0x12345678, 0x9abcdef0))
        self.assertEqual(info['watchdog'], (0x4455, 0x2233, 0x0011))
        self.assertEqual((info['lower'], info['upper']), (0, 0x8000))

    def test_the_whole_program_range_and_the_dead_board_range(self):
        whole = cps2_crypt.parse_key(make_key(self.WORDS[:9] + [0x0000]))
        self.assertEqual((whole['lower'], whole['upper']), (0, 0x1000000))
        dead = cps2_crypt.parse_key(make_key(self.WORDS[:9] + [0xffff]))
        self.assertEqual((dead['lower'], dead['upper']), (0xff0000, 0xffffff))

    def test_a_file_that_is_not_a_key_is_refused(self):
        with self.assertRaisesRegex(ValueError, '20 bytes'):
            cps2_crypt.parse_key(bytes(19))
        with self.assertRaisesRegex(ValueError, 'not a valid key'):
            cps2_crypt.parse_key(bytes(20))
        with self.assertRaisesRegex(ValueError, 'not a valid key'):
            cps2_crypt.parse_key(make_key(self.WORDS[:7] + [0x4001, 0x0900, 0x03fe]))


class DecryptionTests(unittest.TestCase):
    WORDS = KeyFileTests.WORDS

    def test_words_match_a_direct_transcription_of_mames_function(self):
        key = make_key(self.WORDS)
        master = cps2_crypt.parse_key(key)['master']
        generator = random.Random(2)
        program = bytes(generator.randrange(256) for _ in range(0x20000))
        decrypted = cps2_crypt.decrypt(program, key)
        for index in [0, 1, 2, 255, 256, 0x1000, 0x3fff, 0x4000] + [generator.randrange(0, 0x4000) for _ in range(40)]:
            value = int.from_bytes(program[2 * index:2 * index + 2], 'big')
            expected = reference_decrypt_word(value, index & 0xffff, master)
            self.assertEqual(int.from_bytes(decrypted[2 * index:2 * index + 2], 'big'), expected, index)

    def test_only_the_keys_range_is_decrypted_and_the_length_is_kept(self):
        key = make_key(self.WORDS)                           # range: the first 0x8000 bytes (words 0 to 0x4000)
        generator = random.Random(3)
        program = bytes(generator.randrange(256) for _ in range(0x20000))
        decrypted = cps2_crypt.decrypt(program, key)
        self.assertEqual(len(decrypted), len(program))
        self.assertEqual(decrypted[0x8002:], program[0x8002:])
        changed = sum(decrypted[2 * i:2 * i + 2] != program[2 * i:2 * i + 2] for i in range(0x4000))
        self.assertGreater(changed, 0x3000)
        self.assertEqual(cps2_crypt.decrypt(program, key), decrypted)
        self.assertNotEqual(cps2_crypt.decrypt(program, make_key(self.WORDS[:3] + [0xdef1] + self.WORDS[4:])), decrypted)

    def test_an_odd_length_is_refused(self):
        with self.assertRaises(ValueError):
            cps2_crypt.decrypt(bytes(3), make_key(self.WORDS))


class TablesTests(unittest.TestCase):
    def test_shapes(self):
        for boxes in (tables.FN1_BOXES, tables.FN2_BOXES):
            self.assertEqual(len(boxes), 16)
            for table, inputs, outputs in boxes:
                self.assertEqual((len(table), len(inputs), len(outputs)), (64, 6, 2))
                self.assertTrue(set(table) <= {0, 1, 2, 3})
        self.assertEqual((len(tables.EXPAND_FIRST_KEY), len(tables.EXPAND_SECOND_KEY), len(tables.EXPAND_SUBKEY)), (96, 96, 64))
        for group in (tables.FN1_GROUP_A + tables.FN1_GROUP_B, tables.FN2_GROUP_A + tables.FN2_GROUP_B):
            self.assertEqual(sorted(group), list(range(16)))

    @unittest.skipUnless((CACHE / 'cps2crypt.cpp').is_file(), 'pinned MAME sources are not cached')
    def test_tables_regenerate_byte_for_byte(self):
        generated = builder.build(CACHE, offline=True)
        self.assertEqual(generated, (ROOT / 'retrorecomp' / 'cps2_tables.py').read_text(encoding='ascii'))
        self.assertEqual(hashlib.sha256((CACHE / 'cps2crypt.cpp').read_bytes()).hexdigest(), tables.SOURCE_SHA256)


if __name__ == '__main__':
    unittest.main()
