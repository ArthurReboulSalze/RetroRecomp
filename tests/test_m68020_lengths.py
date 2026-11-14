"""The 68EC020's instruction lengths (retrorecomp/m68020_lengths.py) and the instruction-set hook of the shared 68000 media knowledge: the
68000 machines (X68000, Atari ST, Amiga 500) keep exactly the lengths they had."""
import random
import unittest

from retrorecomp import m68020_lengths as L
from retrorecomp import m68k_media_knowledge as media


def words(*values: int) -> bytes:
    return b''.join(value.to_bytes(2, 'big') for value in values)


class M68020LengthTests(unittest.TestCase):
    def test_lengths_of_the_manual_encodings(self):
        cases = [
            (words(0x4E71), 2),                                      # nop
            (words(0x2230, 0x0000), 4),                              # move.l (0,a0,d0.w),d1: brief extension word
            (words(0x2230, 0x0130, 0x1234, 0x5678), 8),              # move.l (bd.l,a0,d0.w),d1: full, long base displacement
            (words(0x2230, 0x0127, 0x0010, 0x0000, 0x0020), 10),     # move.l ([bd.w,a0],d0.w,od.l),d1: post-indexed, long outer
            (words(0x2230, 0x0111), 4),                              # move.l ([a0,d0.w]),d1: null base and outer displacements
            (words(0x23B0, 0x0000, 0x1000), 6),                      # move.l (d8,a0,d0),(d8,a1,d1): two brief words
            (words(0x23B0, 0x0130, 0, 0, 0x1130, 0, 0), 14),         # the same, both full with long base displacements
            (words(0x60FF, 0x0000, 0x0100), 6),                      # bra.l
            (words(0x6000, 0x0100), 4),                              # bra.w
            (words(0xE9D0, 0x0008), 4),                              # bfextu (a0){0:8},d0
            (words(0x4C01, 0x2000), 4),                              # mulu.l d1,d2
            (words(0x0EFC, 0x8042, 0x9043), 6),                      # cas2.l: its words hold registers, not a MOVES word
            (words(0x203C, 0x1234, 0x5678), 6),                      # move.l #imm,d0
        ]
        for raw, size in cases:
            with self.subTest(raw=raw.hex()):
                self.assertEqual(L.length(raw + bytes(24)), size)

    def test_reserved_and_short_encodings_are_refused(self):
        self.assertIsNone(L.length(words(0x2230, 0x0100) + bytes(8)))           # base displacement size 00 is reserved
        self.assertIsNone(L.length(words(0x2230, 0x0144) + bytes(8)))           # IS set with I/IS 100 is reserved
        self.assertIsNone(L.length(words(0x2230)))                              # the extension word is missing
        self.assertIsNone(L.length(words(0x2230, 0x0130, 0x1234)))              # the displacement is cut
        self.assertIsNone(L.length(words(0x0E10, 0x0001)))                      # MOVES with reserved bits: illegal on Moira

    def test_the_longest_instruction(self):
        raw = words(0x23B0, 0x0133, 0, 0, 0, 0, 0x1133, 0, 0, 0, 0)
        self.assertEqual(L.length(raw), L.LONGEST_INSTRUCTION)

    def test_the_table_is_whole(self):
        self.assertEqual(len(L.table()), 65536)
        self.assertEqual(L.brief_words(0x4E71), 1)
        self.assertEqual(L.extension_positions(0x23B0), (1, 2))
        self.assertEqual(L.extension_positions(0x4E71), ())


def old_instruction(text):
    if not isinstance(text, str) or len(text) % 4 or not 4 <= len(text) <= 32:
        return None
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        return None
    return raw if len(raw) == 2 * media.word_count(raw[0] << 8 | raw[1]) else None


def old_exact(text):
    if not isinstance(text, str) or len(text) % 4 or not 4 <= len(text) <= 32:
        return None
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        return None
    size = 2 * media.word_count(raw[0] << 8 | raw[1])
    return raw[:size].hex() if len(raw) >= size else None


def old_span(data, address):
    out, position = [], 0
    while position < len(data):
        if position + 2 > len(data):
            raise ValueError
        size = 2 * media.word_count(data[position] << 8 | data[position + 1])
        if size > 16 or position + size > len(data):
            raise ValueError
        out.append((address + position, data[position:position + size].hex()))
        position += size
    return out


class SixtyEightThousandUnchangedTests(unittest.TestCase):
    """The hook leaves every 68000 answer as it was (the lengths before 15 November 2026, written out again here)."""

    def test_windows_and_spans_give_the_old_answers(self):
        rng = random.Random(68000)
        for _ in range(20000):
            text = bytes(rng.randrange(256) for _ in range(2 * rng.randrange(1, 9))).hex()
            self.assertEqual(media.instruction(text), old_instruction(text))
            self.assertEqual(media.exact(text), old_exact(text))
        for _ in range(3000):
            data = bytes(rng.randrange(256) for _ in range(2 * rng.randrange(1, 24)))
            try:
                expected = old_span(data, 0x1000)
            except ValueError:
                expected = None
            try:
                got = media.instructions_of_span(data, 0x1000)
            except ValueError:
                got = None
            self.assertEqual(got, expected)
        for text in ('', 'zz', '4e7', '4e714e71' * 5, None, 123):
            self.assertEqual(media.instruction(text), old_instruction(text))
            self.assertEqual(media.exact(text), old_exact(text))

    def test_the_68000_machines_keep_the_68000_lengths(self):
        from retrorecomp import amiga_knowledge, atarist_knowledge, x68_knowledge
        for module in (x68_knowledge, atarist_knowledge, amiga_knowledge):
            knowledge = next(value for value in vars(module).values() if isinstance(value, media.MediaKnowledge))
            with self.subTest(module=module.__name__):
                self.assertIs(knowledge.isa, media.MC68000)


if __name__ == '__main__':
    unittest.main()
