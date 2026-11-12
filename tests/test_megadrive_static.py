"""Anchored static discovery of 68000 code (retrorecomp/megadrive_static.py).

Authored bytes only, no ROM. A small fake decoder stands in for the pinned one with its flow rules; one test runs the
pinned decoder on the same authored images and is skipped when the tool is not built.
"""
from collections import deque
from pathlib import Path
import copy
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import megadrive_static as static
from retrorecomp.megadrive_static import anchored_roots

ROOT = Path(__file__).resolve().parents[1]
NOP, RTS = 0x4e71, 0x4e75
STUB = (NOP, RTS)                       # the smallest handler a tier 1 rule accepts
FOUR = (NOP, NOP, NOP, RTS)             # the smallest handler a tier 2 rule accepts
BAD = 0x7100                            # MOVEQ with bit 8 set: the decoder emits nothing for it


def long(value):
    return [value >> 16, value & 0xffff]


def image(*placements, size=0x1000):
    """An authored cartridge: the SEGA magic the decoder asks for and the words placed at their addresses."""
    data = bytearray(size)
    data[0x100:0x104] = b'SEGA'
    for address, *items in placements:
        for item in items:
            for word in (item if isinstance(item, (list, tuple)) else (item,)):
                data[address:address + 2] = word.to_bytes(2, 'big')
                address += 2
    return bytes(data)


def at(address, *items):
    return (address, *items)


def handlers(*addresses, body=STUB):
    return [at(address, *body) for address in addresses]


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


class FakeDecoder:
    """The forms the tests author, decoded with the flow rules of md_decode_dump.c (--follow-flow)."""
    FIXED = {0x4e71: 'MN_NOP', 0x4e75: 'MN_RTS', 0x4e73: 'MN_RTE', 0x4e77: 'MN_RTR', 0x4e76: 'MN_TRAPV',
             0x4e70: 'MN_RESET', 0x4afc: 'MN_ILLEGAL'}

    def __init__(self, data):
        self.data, self.calls = data, []

    def word(self, address):
        return int.from_bytes(self.data[address:address + 2], 'big')

    def decode_at(self, pc):
        w, size = self.word(pc), len(self.data)

        def make(name, count, target=None):
            if pc + 2 * count > size:
                return None
            words = [self.word(pc + 2 * n) for n in range(count)]
            return {'addr': pc, 'byte_length': 2 * count, 'words': words + [0] * (8 - count), 'word_count': count,
                    'mnemonic': NAMES.index(name), 'name': name, 'has_target': target is not None,
                    'target_addr': 0 if target is None else target & 0xffffff}

        if w in self.FIXED:
            return make(self.FIXED[w], 1)
        if w >> 12 in (0xa, 0xf):
            return make('MN_ILLEGAL', 1)
        if w == 0x4e72:
            return make('MN_STOP', 2)
        if w & 0xfff0 == 0x4e40:
            return make('MN_TRAP', 1)
        if w in (0x007c, 0x027c):
            return make('MN_ORI_TO_SR' if w == 0x007c else 'MN_ANDI_TO_SR', 2)
        if w == 0x0000:
            return make('MN_ORI', 2)
        if w & 0xfff8 in (0x4ed0, 0x4e90):
            return make('MN_JMP' if w & 0xfff8 == 0x4ed0 else 'MN_JSR', 1)
        if w & 0xfff8 in (0x4ef0, 0x4eb0):
            return make('MN_JMP' if w & 0xfff8 == 0x4ef0 else 'MN_JSR', 2)
        if w in (0x4efb, 0x4ebb):
            return make('MN_JMP' if w == 0x4efb else 'MN_JSR', 2)
        if w == 0x4efa:
            return make('MN_JMP', 2, pc + 2 + signed(self.word(pc + 2), 16))
        if w in (0x4ef9, 0x4eb9):
            return make('MN_JMP' if w == 0x4ef9 else 'MN_JSR', 3, (self.word(pc + 2) << 16) | self.word(pc + 4))
        if w & 0xf000 == 0x6000:
            condition, disp = (w >> 8) & 15, w & 0xff
            name = 'MN_BRA' if condition == 0 else 'MN_BSR' if condition == 1 else 'MN_Bcc'
            if disp == 0:
                return make(name, 2, pc + 2 + signed(self.word(pc + 2), 16))
            return None if disp == 0xff else make(name, 1, pc + 2 + signed(disp, 8))
        top = w & 0xf1ff
        if top in (0x41fa, 0x41f8, 0x41fb):
            return make('MN_LEA', 2)
        if top == 0x41f9:
            return make('MN_LEA', 3)
        if top == 0x207b:
            return make('MN_MOVEA', 2)
        if top == 0x207c:
            return make('MN_MOVEA', 3)
        if w & 0xf03f == 0x203c:
            return make('MN_MOVE', 3)
        if w & 0xf038 == 0x2030:
            return make('MN_MOVEA' if w & 0x01c0 == 0x0040 else 'MN_MOVE', 2)
        if w & 0xf038 in (0x2010, 0x2018):
            return make('MN_MOVEA' if w & 0x01c0 == 0x0040 else 'MN_MOVE', 1)
        if top == 0x303b or w & 0xf1f8 == 0x3030:
            return make('MN_MOVE', 2)
        if w & 0xf1f8 == 0xd0f0:
            return make('MN_ADDA', 2)
        if w & 0xf1f8 == 0xd0d0:
            return make('MN_ADDA', 1)
        if w & 0xfff8 == 0x0680:
            return make('MN_ADDI', 3)
        if w == 0x4879:
            return make('MN_PEA', 3)
        if w == 0x487a:
            return make('MN_PEA', 2)
        if w & 0xf100 == 0x7000:
            return make('MN_MOVEQ', 1)
        return None

    def __call__(self, pcs):
        self.calls.append(set(pcs))
        seen, queue, out = set(), deque(sorted(pcs)), []
        while queue:
            pc = queue.popleft()
            if pc & 1 or pc >= len(self.data) or pc in seen:
                continue
            seen.add(pc)
            ins = self.decode_at(pc)
            if ins is None:
                continue
            out.append(ins)
            if ins['name'] in static.FLOW and ins['has_target']:
                queue.append(ins['target_addr'])
            if ins['name'] not in static.TERMINATORS:
                queue.append(pc + ins['byte_length'])
        return sorted(out, key=lambda ins: ins['addr'])


NAMES = ['MN_OTHER', 'MN_NOP', 'MN_RTS', 'MN_RTE', 'MN_RTR', 'MN_TRAPV', 'MN_RESET', 'MN_ILLEGAL', 'MN_STOP', 'MN_TRAP',
         'MN_ORI_TO_SR', 'MN_ANDI_TO_SR', 'MN_ORI', 'MN_JMP', 'MN_JSR', 'MN_BRA', 'MN_BSR', 'MN_Bcc', 'MN_LEA',
         'MN_MOVEA', 'MN_MOVE', 'MN_ADDA', 'MN_ADDI', 'MN_PEA', 'MN_MOVEQ']


def discover(data, seeds=(0x200,), **options):
    decoder = FakeDecoder(data)
    roots, counters = anchored_roots(data, decoder, set(seeds), mapper=options.get('mapper', False))
    return roots, counters, decoder


class Checks(unittest.TestCase):
    def assertCounted(self, counters):
        """Every candidate of a rule ends as accepted or as exactly one counted refusal."""
        accepted = refused = 0
        for rule, count in counters['rules'].items():
            self.assertEqual(count['targets'], count['accepted'] + sum(count['refused'].values()), rule)
            accepted, refused = accepted + count['accepted'], refused + sum(count['refused'].values())
        self.assertEqual(accepted, counters['roots_accepted'])
        self.assertEqual(refused, counters['roots_refused'])

    def refusals(self, counters, rule):
        return {reason: n for reason, n in counters['rules'][rule]['refused'].items() if n}


TABLE = (0x220, 0x224, 0x228)


def a1c_image(jump=0x4ed0, extra=()):
    """`MOVEA.L (4,PC,D0.W),A0 ; JMP/JSR (A0)` and three long pointers to NOP/RTS handlers, then an invalid long."""
    return image(at(0x200, 0x207b, 0x0004, jump), at(0x206, *[long(t) for t in TABLE], long(0xffffffff)),
                 *handlers(*TABLE), *extra)


class LongTableTests(Checks):
    def test_a1c_reads_the_pointers_and_stops_on_the_invalid_long(self):
        roots, counters, decoder = discover(a1c_image())
        self.assertEqual(roots, set(TABLE))
        self.assertEqual(counters['rules']['a1c'], {'targets': 3, 'accepted': 3, 'refused': {r: 0 for r in static.REASONS}})
        self.assertEqual((counters['rounds'], counters['roots_accepted'], counters['roots_refused'],
                          counters['extra_instructions'], counters['skipped']), (1, 3, 0, 6, None))
        self.assertFalse(counters['rounds_exhausted'])
        self.assertCounted(counters)

    def test_jsr_and_the_lea_and_addi_forms(self):
        # JSR returns to the next instruction, so the table cannot follow it inline: it sits further on.
        jsr = image(at(0x200, 0x207b, 0x003e, 0x4e90, RTS), at(0x240, *[long(t) for t in TABLE], long(0xffffffff)),
                    *handlers(*TABLE))
        roots, counters, _ = discover(jsr)
        self.assertEqual(roots, set(TABLE))
        self.assertEqual(counters['rules']['a1c']['accepted'], 3)
        # LEA T(PC),A0 ; MOVEA.L (A0,D0.W),A1 ; JMP (A1): the LEA's own operand is a c0/c1 candidate too, a1c names it first.
        lea = image(at(0x200, 0x41fa, 0x0008, 0x2270, 0x0000, 0x4ed1), at(0x20a, *[long(t) for t in TABLE], long(0xffffffff)),
                    *handlers(*TABLE))
        roots, counters, _ = discover(lea)
        self.assertEqual(roots, set(TABLE))
        self.assertEqual(counters['rules']['a1c']['accepted'], 3)
        self.assertEqual(self.refusals(counters, 'c0'), {'zero_word': 1})
        self.assertCounted(counters)
        # ADDI.L #T,D0 ; JMP (0,A6,D0.L)
        addi = image(at(0x200, 0x0680, long(0x20a), 0x4ef6, 0x0800), at(0x20a, *[long(t) for t in TABLE], long(0xffffffff)),
                     *handlers(*TABLE))
        roots, counters, _ = discover(addi)
        self.assertEqual((roots, counters['rules']['a1c']['accepted']), (set(TABLE), 3))
        self.assertCounted(counters)


class OffsetTableTests(Checks):
    def test_a3_offsets_are_relative_to_the_entry_itself(self):
        # LEA (6,PC,D0.W),A0 ; ADDA.W (A0),A0 ; JMP (A0): the table at $208 holds target - entry address.
        data = image(at(0x200, 0x41fb, 0x0006, 0xd0d0, 0x4ed0),
                     at(0x208, 0x220 - 0x208, 0x224 - 0x20a, 0x228 - 0x20c, 0x0001), *handlers(*TABLE))
        roots, counters, _ = discover(data)
        self.assertEqual(roots, set(TABLE))
        self.assertEqual(counters['rules']['a3']['accepted'], 3)
        self.assertCounted(counters)

    def test_a2_offsets_are_relative_to_the_table_and_to_the_jump_base(self):
        # LEA T(PC),A0 ; ADDA.W (0,A0,D0.W),A0 ; JMP (A0): relative to T.
        data = image(at(0x200, 0x41fa, 0x0008, 0xd0f0, 0x0000, 0x4ed0), at(0x20a, 0x220 - 0x20a, 0x224 - 0x20a, 0x0001),
                     *handlers(0x220, 0x224))
        self.assertEqual(discover(data)[0], {0x220, 0x224})
        # LEA T(PC),A0 ; MOVE.W (2,A0,D0.W),D0 ; JMP (4,A0,D0.W): the table starts at T+2, the offsets count from T+4.
        data = image(at(0x200, 0x41fa, 0x000a, 0x3030, 0x0002, 0x4ef0, 0x0004), at(0x20e, 0x220 - 0x210, 0x224 - 0x210, 0x0001),
                     *handlers(0x220, 0x224))
        roots, counters, _ = discover(data)
        self.assertEqual(roots, {0x220, 0x224})
        self.assertEqual(counters['rules']['a2']['accepted'], 2)
        self.assertCounted(counters)

    def test_b1_offsets_count_from_the_jump_base_which_may_differ_from_the_table(self):
        # MOVE.W (6,PC,D0.W),D0 ; JMP (d8,PC,D0.W): the table is at $208; the base is the jump + 2 + d8.
        for d8, base in ((2, 0x208), (0, 0x206)):
            with self.subTest(base=base):
                data = image(at(0x200, 0x303b, 0x0006, 0x4efb, d8), at(0x208, 0x220 - base, 0x224 - base, 0x0001),
                             *handlers(0x220, 0x224))
                roots, counters, _ = discover(data)
                self.assertEqual(roots, {0x220, 0x224})
                self.assertEqual(counters['rules']['b1']['accepted'], 2)
                self.assertCounted(counters)


class RowTests(Checks):
    def rows(self, *rows, jump=0x4efb):
        return image(at(0x200, jump, 0x0002), at(0x204, *rows), *handlers(0x220, 0x224, 0x228))

    def test_rows_of_short_word_and_absolute_branches(self):
        short = self.rows(0x6000 + 0x220 - 0x206, 0x6000 + 0x224 - 0x208, 0x6000 + 0x228 - 0x20a, NOP)
        roots, counters, _ = discover(short)
        self.assertEqual(roots, {0x204, 0x206, 0x208})
        self.assertEqual(counters['rules']['b2']['accepted'], 3)
        word = self.rows(0x6000, 0x220 - 0x206, 0x6000, 0x224 - 0x20a, 0x6000, 0x228 - 0x20e, NOP)
        self.assertEqual(discover(word)[0], {0x204, 0x208, 0x20c})
        absolute = self.rows(0x4ef9, long(0x220), 0x4ef9, long(0x224), NOP)
        self.assertEqual(discover(absolute)[0], {0x204, 0x20a})
        # A JSR falls into the first row, which is then reached: the run still names the other rows (a PC-indexed jump enters
        # at any row), only the reached one is no candidate.
        self.assertEqual(discover(self.rows(0x4ef9, long(0x220), 0x4ef9, long(0x224), NOP, jump=0x4ebb))[0], {0x20a})

    def test_a_reached_row_does_not_end_the_run_whatever_its_place(self):
        short = self.rows(0x6000 + 0x220 - 0x206, 0x6000 + 0x224 - 0x208, NOP)
        # Row 0 in the seeds: the first row is reached, the second is still found.
        roots, counters, _ = discover(short, seeds=(0x200, 0x204))
        self.assertEqual(roots, {0x206})
        self.assertEqual(counters['rules']['b2']['accepted'], 1)
        self.assertCounted(counters)
        # The last row in the seeds: the first is still found.
        self.assertEqual(discover(short, seeds=(0x200, 0x206))[0], {0x204})

    def test_a_mixed_row_ends_the_run_and_a_single_row_is_accepted(self):
        mixed = self.rows(0x6000 + 0x220 - 0x206, 0x6000 + 0x224 - 0x208, 0x6000, 0x228 - 0x20c, NOP)
        self.assertEqual(discover(mixed)[0], {0x204, 0x206})
        # One row: the existing jump-table closure asks for three equal thunks, a PC-indexed jump anchors a single one.
        roots, counters, _ = discover(self.rows(0x6000 + 0x220 - 0x206, NOP))
        self.assertEqual(roots, {0x204})
        self.assertCounted(counters)


class BoundTests(Checks):
    def test_a_table_is_cut_at_256_entries_and_counted_once(self):
        data = image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, *[long(0x1000)] * 300), at(0x1000, *STUB), size=0x2000)
        self.assertEqual(len(static._longs(data, 0x206, {}, set())), 256)
        roots, counters, _ = discover(data)
        self.assertEqual((roots, counters['tables_cut']), ({0x1000}, 1))
        # Rescanned in every round, the same table is still one cut table.
        short = image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, *[long(0x1000)] * 3, long(0xffffffff)), at(0x1000, *STUB),
                      size=0x2000)
        self.assertEqual(discover(short)[1]['tables_cut'], 0)

    def test_a_table_stops_at_the_lowest_target_above_it_a_reached_start_and_an_odd_entry(self):
        # The pointers name $20e, the place after two entries, where the bytes would be another valid pointer.
        data = image(at(0x206, long(0x20e), long(0x20e), long(0x220)))
        self.assertEqual(static._longs(data, 0x206, {}, set()), [0x20e, 0x20e])
        data = image(at(0x206, long(0x220), long(0x224), long(0x228)))
        self.assertEqual(static._longs(data, 0x206, {0x20e: {}}, set()), [0x220, 0x224])
        self.assertEqual(static._longs(data, 0x206, {0x206: {}}, set()), [])
        data = image(at(0x206, long(0x220), long(0x221), long(0x224)))
        self.assertEqual(static._longs(data, 0x206, {}, set()), [0x220])
        # Below $200, beyond the image, odd: no pointer.
        data = image(at(0x206, long(0x1fe), long(0x220)))
        self.assertEqual(static._longs(data, 0x206, {}, set()), [])
        self.assertEqual(static._longs(image(at(0x206, long(0x2000))), 0x206, {}, set()), [])
        # Offsets: an entry pointing into the table itself ends it.
        data = image(at(0x208, 0x220 - 0x208, 0x20a - 0x20a))
        self.assertEqual(static._offsets(data, 0x208, None, {}, set()), [0x220])


class RefusalTests(Checks):
    def single(self, code, *, rule='a1c', **options):
        """One a1c table entry ($220) whose handler is `code`; reached code at $230 and beyond can be added."""
        data = image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, long(0x220), long(0xffffffff)),
                     at(0x220, *code), *options.get('extra', ()))
        return discover(data, seeds=options.get('seeds', (0x200,)))

    def test_illegal_opcode(self):
        roots, counters, _ = self.single((0xffff,))
        self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'illegal_opcode': 1}))
        self.assertEqual(self.single((NOP, 0xa000, RTS))[1]['rules']['a1c']['refused']['illegal_opcode'], 1)
        self.assertCounted(counters)

    def test_zero_word(self):
        roots, counters, _ = self.single((0x0000, 0x0000, RTS))
        self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'zero_word': 1}))

    def test_illegal_decode(self):
        roots, counters, _ = self.single((NOP, BAD, RTS))
        self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'illegal_decode': 1}))

    def test_target_out(self):
        for code in ((NOP, 0x6001), (NOP, 0x6000, 0x7ffe), (NOP, 0x6000, 0xfedc)):
            with self.subTest(code=code):
                roots, counters, _ = self.single(code)
                self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'target_out': 1}))

    def test_overlap(self):
        # $240 is a reached JMP abs.l; the table names $242, inside its extension words.
        data = image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, long(0x242), long(0xffffffff)),
                     at(0x240, 0x4ef9, long(0x300)), at(0x300, *STUB))
        roots, counters, _ = discover(data, seeds=(0x200, 0x240))
        self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'overlap': 1}))
        self.assertCounted(counters)

    def test_too_short_for_each_tier(self):
        roots, counters, _ = self.single((RTS,))
        self.assertEqual((roots, self.refusals(counters, 'a1c')), (set(), {'too_short': 1}))
        self.assertEqual(self.single(STUB)[0], {0x220})
        # A stub that falls into reached code is not short.
        roots, counters, _ = self.single((NOP,), extra=[at(0x222, RTS)], seeds=(0x200, 0x222))
        self.assertEqual(roots, {0x220})
        # Tier 2: a lone RTS behind a LEA operand is below the four instructions it asks for.
        lea = image(at(0x200, 0x41f9, long(0x230), RTS), at(0x230, RTS))
        roots, counters, _ = discover(lea)
        self.assertEqual((roots, self.refusals(counters, 'c0')), (set(), {'too_short': 1}))
        self.assertEqual(discover(image(at(0x200, 0x41f9, long(0x230), RTS), at(0x230, *FOUR)))[0], {0x230})

    def test_suspect_opcodes_are_refused_for_tier_2_only(self):
        def operand(*code):
            return discover(image(at(0x200, 0x41f9, long(0x230), RTS), at(0x230, *code)))
        roots, counters, _ = operand(NOP, NOP, 0x4e72, 0x2700, RTS)                      # STOP
        self.assertEqual((roots, self.refusals(counters, 'c0')), (set(), {'suspect_opcode': 1}))
        for code in ((NOP, NOP, 0x007c, 0x0700, RTS), (NOP, NOP, 0x4e40, RTS)):         # ORI to SR, TRAP #0
            with self.subTest(code=code):
                self.assertEqual(operand(*code)[0], {0x230})
        # Tier 1 (a jump consumes the table) accepts a handler that starts with STOP.
        roots, counters, _ = self.single((0x4e72, 0x2700, RTS))
        self.assertEqual(roots, {0x220})
        # A suspect instruction further down the closure (after a BRA.s) refuses the candidate as well.
        roots, counters, _ = operand(NOP, NOP, 0x6002, NOP, 0x4e72, 0x2700, RTS)
        self.assertEqual((roots, self.refusals(counters, 'c0')), (set(), {'suspect_opcode': 1}))


class WindowTests(Checks):
    def test_the_jump_must_follow_the_load_within_the_window(self):
        def program(between):
            jump = 0x204 + 2 * between
            table = jump + 2
            return image(at(0x200, 0x207b, table - 0x202, *[NOP] * between, 0x4ed0), at(table, long(0x220), long(0xffffffff)),
                         *handlers(0x220))
        self.assertEqual(discover(program(5))[0], {0x220})
        for between in (6, 7):
            roots, counters, _ = discover(program(between))
            self.assertEqual((roots, counters['rules']['a1c']['targets']), (set(), 0), between)

    def test_a_terminator_between_the_load_and_the_jump_ends_the_window(self):
        data = image(at(0x200, 0x207b, 0x000e, RTS), at(0x208, 0x4ed0), at(0x210, long(0x220), long(0xffffffff)),
                     *handlers(0x220))
        roots, counters, _ = discover(data, seeds=(0x200, 0x208))
        self.assertEqual((roots, counters['rules']['a1c']['targets']), (set(), 0))

    def test_a_reloaded_register_ends_the_window(self):
        data = image(at(0x200, 0x41fa, 0x0012, 0x41f9, long(0x300), 0x2270, 0x0000, 0x4ed1),
                     at(0x214, long(0x220), long(0x224), long(0xffffffff)), *handlers(0x220, 0x224), at(0x300, 0))
        roots, counters, _ = discover(data)
        # The first LEA's table is no a1c candidate (A0 is reloaded); only the second LEA's, which is empty.
        self.assertEqual(counters['rules']['a1c']['targets'], 0)


class OperandTests(Checks):
    def test_an_immediate_handler_address_is_one_tier_2_root(self):
        data = image(at(0x200, 0x20bc, long(0x220), RTS), at(0x220, *FOUR))
        roots, counters, _ = discover(data)
        self.assertEqual(roots, {0x220})
        self.assertEqual(counters['rules']['c0']['accepted'], 1)
        self.assertCounted(counters)

    def test_a_lea_table_of_two_longs_gives_two_roots(self):
        data = image(at(0x200, 0x41f9, long(0x210), RTS), at(0x210, long(0x220), long(0x240)),
                     at(0x220, *FOUR), at(0x240, *FOUR))
        roots, counters, _ = discover(data)
        self.assertEqual(roots, {0x220, 0x240})
        self.assertEqual(counters['rules']['c1']['accepted'], 2)
        self.assertEqual(self.refusals(counters, 'c0'), {'zero_word': 1})        # the table bytes decode as ORI #n,D0
        self.assertCounted(counters)
        one = image(at(0x200, 0x41f9, long(0x210), RTS), at(0x210, long(0x220), long(0xffffffff)), at(0x220, *FOUR))
        self.assertEqual(discover(one)[0], set())

    def test_a_ram_or_odd_operand_gives_nothing(self):
        for operand in (0xff0000, 0x221, 0x1f0):
            with self.subTest(operand=hex(operand)):
                data = image(at(0x200, 0x20bc, long(operand), RTS), at(0x220, *FOUR))
                roots, counters, _ = discover(data)
                self.assertEqual((roots, counters['rules']['c0']['targets']), (set(), 0))


class OptionalRuleTests(Checks):
    def test_a1u_and_c2_stay_off_and_run_through_the_same_test_when_switched_on(self):
        a1u = image(at(0x200, 0x207b, 0x0004, RTS), at(0x206, long(0x220), long(0x240), long(0xffffffff)),
                    at(0x220, *FOUR), at(0x240, *FOUR))
        c2 = image(at(0x200, 0x41f9, long(0x210), RTS), at(0x210, long(0x230), long(0x240), long(0xffffffff)),
                   at(0x230, long(0x250), long(0x258), long(0xffffffff)), at(0x240, long(0x260), long(0x268), long(0xffffffff)),
                   *[at(a, *FOUR) for a in (0x250, 0x258, 0x260, 0x268)])
        for data, rule, expected in ((a1u, 'a1u', {0x220, 0x240}), (c2, 'c2', {0x250, 0x258, 0x260, 0x268})):
            with self.subTest(rule=rule):
                roots, counters, _ = discover(data)
                self.assertEqual((roots, rule in counters['rules']), (set(), False))
                with patch.object(static, 'ENABLE_OPTIONAL_RULES', True):
                    roots, counters, _ = discover(data)
                self.assertEqual(roots, expected)
                self.assertEqual(counters['rules'][rule]['accepted'], len(expected))
                self.assertCounted(counters)


class FixedPointTests(Checks):
    def nested(self, bad=()):
        return image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, long(0x220), *[long(b) for b in bad], long(0xffffffff)),
                     at(0x220, 0x207b, 0x0004, 0x4ed0), at(0x226, long(0x240), long(0x244), long(0xffffffff)),
                     *handlers(0x240, 0x244), *[at(b, 0xffff) for b in bad])

    def test_a_handler_found_in_round_one_anchors_a_table_found_in_round_two(self):
        roots, counters, decoder = discover(self.nested(bad=(0x230,)))
        self.assertEqual(roots, {0x220, 0x240, 0x244})
        self.assertEqual(counters['rounds'], 2)
        self.assertFalse(counters['rounds_exhausted'])
        self.assertEqual((counters['rules']['a1c']['targets'], counters['rules']['a1c']['accepted']), (4, 3))
        self.assertEqual(self.refusals(counters, 'a1c'), {'illegal_opcode': 1})
        self.assertEqual(counters['roots_refused'], 1)
        self.assertCounted(counters)

    def test_the_round_limit_is_counted(self):
        with patch.object(static, 'ROUNDS', 1):
            roots, counters, _ = discover(self.nested())
        self.assertEqual((roots, counters['rounds'], counters['rounds_exhausted']), ({0x220}, 1, True))
        self.assertCounted(counters)

    def test_a_fixed_point_reached_exactly_at_the_last_round_is_not_exhausted(self):
        # Two rounds are all this program needs: the limit is met, but nothing is left for a third round.
        with patch.object(static, 'ROUNDS', 2):
            roots, counters, _ = discover(self.nested(bad=(0x230,)))
        self.assertEqual((roots, counters['rounds'], counters['rounds_exhausted']), ({0x220, 0x240, 0x244}, 2, False))
        self.assertCounted(counters)
        # The same program with a limit of one round still has candidates left.
        with patch.object(static, 'ROUNDS', 1):
            self.assertTrue(discover(self.nested(bad=(0x230,)))[1]['rounds_exhausted'])


class CapTests(Checks):
    def program(self):
        # A tier 1 table (handler of 2 instructions) and a tier 2 immediate (handler of 4), both within reach.
        return image(at(0x200, 0x207b, 0x0004, 0x4ed0), at(0x206, long(0x220), long(0xffffffff)),
                     at(0x300, 0x20bc, long(0x240), RTS), at(0x220, *STUB), at(0x240, *FOUR))

    def test_the_limit_refuses_the_lower_priority_roots_and_counts_them(self):
        data = self.program()
        with patch.object(static, 'ANCHORED_EXTRA_LIMIT', 3):
            roots, counters, _ = discover(data, seeds=(0x200, 0x300))
            again = discover(data, seeds=(0x200, 0x300))
        self.assertEqual(roots, {0x220})
        self.assertEqual(self.refusals(counters, 'c0'), {'cap': 1})
        self.assertEqual(counters['rules']['a1c']['accepted'], 1)
        self.assertCounted(counters)
        self.assertEqual((roots, counters), again[:2])                           # deterministic
        self.assertEqual(counters['extra_instructions'], 2)
        with patch.object(static, 'ANCHORED_EXTRA_LIMIT', 0):
            self.assertEqual(discover(data, seeds=(0x200, 0x300))[0], set())
        self.assertEqual(discover(data, seeds=(0x200, 0x300))[0], {0x220, 0x240})

    def test_the_summary_line_names_the_cap(self):
        with patch.object(static, 'ANCHORED_EXTRA_LIMIT', 3):
            counters = discover(self.program(), seeds=(0x200, 0x300))[1]
        self.assertEqual(static.summary_line(counters),
                         'Static discovery: 1 root from reached code (+2 instructions), 1 candidate refused (1 at the cap).')
        counters['roots_accepted'], counters['roots_refused'], counters['extra_instructions'] = 450, 555, 8959
        counters['rounds_exhausted'] = True
        self.assertEqual(static.summary_line(counters),
                         'Static discovery: 450 roots from reached code (+8,959 instructions), 555 candidates refused (1 at the cap).'
                         ' The round limit was reached.')
        skipped = anchored_roots(bytes(0x500000), self.fail, {0x200}, mapper=True)[1]
        self.assertIn('skipped', static.summary_line(skipped))

    def test_every_counter_is_json(self):
        counters = discover(self.program(), seeds=(0x200, 0x300))[1]
        self.assertEqual(json.loads(json.dumps(counters)), counters)
        self.assertEqual(counters['schema'], 1)


class MapperTests(Checks):
    def test_a_banked_cartridge_above_4_mib_is_skipped_and_counted(self):
        def decode(pcs):
            self.fail('the decoder must not run for a banked cartridge above 4 MiB')
        roots, counters = anchored_roots(bytes(0x500000), decode, {0x200}, mapper=True)
        self.assertEqual((roots, counters['skipped'], counters['roots_accepted']), (set(), 'mapper', 0))
        self.assertEqual(counters['rules'], static.new_counters()['rules'])
        # A banked cartridge within 4 MiB, and a flat one of any size, take the normal path.
        roots, counters, decoder = discover(a1c_image(), mapper=True)
        self.assertEqual((roots, counters['skipped']), (set(TABLE), None))
        self.assertTrue(decoder.calls)


class WrapperTests(Checks):
    """`megadrive_static.static_roots`: the decoder `generate_steps` uses, the names the module needs, the same RAM variants."""

    def wrapper(self, data, variants=(), seeds=(0x200,)):
        """Run `static_roots` with the decoder tool replaced by the fake decoder behind a patched `run`."""
        fake, runs = FakeDecoder(data), []

        def run(args, *, cwd=None, log=None, **options):
            tool, rom_file, listing, output, *flags = args
            lines = Path(listing).read_text(encoding='ascii').split()
            runs.append({'tool': tool, 'rom': rom_file, 'listing': listing, 'output': output, 'flags': flags, 'cwd': cwd,
                         'log': log, 'options': options, 'ram': [line for line in lines if ':' in line],
                         'pcs': sorted(int(line, 16) for line in lines if ':' not in line)})
            decoded = fake({int(line, 16) for line in lines if ':' not in line})
            for ins in decoded:
                del ins['name']                      # the tool's own output has the mnemonic number only
            Path(output).write_text(json.dumps(decoded), encoding='utf-8')
            return ''

        class Rom:
            pass
        rom = Rom()
        rom.data = data
        with tempfile.TemporaryDirectory() as folder, patch('retrorecomp.core.run', side_effect=run), \
                patch('retrorecomp.megadrive_codegen.decoder_tool', return_value=Path('md_decode')) as tool, \
                patch('retrorecomp.m68000.mnemonic_names', return_value=NAMES) as names:
            project = Path(folder)
            roots, counters = static.static_roots(Path('engine'), project, rom, set(seeds), list(variants))
        return roots, counters, runs, tool, names, project

    def test_the_wrapper_runs_the_decoder_directly_with_private_files_and_adds_the_mnemonic_names(self):
        variants = [{'address': 0xffa000, 'bytes': '4E71'}, {'address': 0xffa000, 'bytes': '4e71'},
                    {'address': 0x1000, 'bytes': '4e71'}]
        roots, counters, runs, tool, names, project = self.wrapper(a1c_image(), variants)
        self.assertEqual(roots, set(TABLE))
        self.assertEqual(counters['rules']['a1c']['accepted'], 3)
        self.assertGreaterEqual(len(runs), 3)
        tool.assert_called_once_with(Path('engine'), md_rules=True)
        names.assert_called_once_with(Path('engine'))
        for item in runs:
            self.assertEqual((item['tool'], item['rom'], item['cwd']), (Path('md_decode'), project / 'cartridge.bin', project))
            self.assertEqual((item['listing'], item['output'], item['log']),
                             (project / 'static-pcs.txt', project / 'static-decoded.json', project / 'decode.log'))
            self.assertEqual(item['flags'], ['--follow-flow'])
            self.assertEqual(item['ram'], ['e0a000:4e71'])           # normalised and unique, as generate_steps does
        # The pass leaves the generator's own files alone.
        self.assertFalse((project / 'instruction-pcs.txt').exists() or (project / 'decoded-instructions.json').exists())

    def test_the_decoder_tool_is_taken_once_for_a_discovery_of_several_rounds(self):
        roots, counters, runs, tool, names, _ = self.wrapper(FixedPointTests().nested(bad=(0x230,)))
        self.assertEqual((roots, counters['rounds']), ({0x220, 0x240, 0x244}, 2))
        self.assertGreaterEqual(len(runs), 5)
        self.assertEqual((tool.call_count, names.call_count), (1, 1))

    def test_the_jump_stub_closure_of_the_generators_decode_is_kept(self):
        # Three equal JMP abs.l stubs, one of them a seed: the listing carries all three, as the generators' decode writes it.
        data = image(at(0x200, 0x4ef9, long(0x220), 0x4ef9, long(0x224), 0x4ef9, long(0x228)), *handlers(0x220, 0x224, 0x228))
        _, _, runs, tool, _, _ = self.wrapper(data)
        self.assertEqual(tool.call_count, 1)
        self.assertEqual(runs[0]['pcs'], [0x200, 0x206, 0x20c])

    def test_the_conversion_report_carries_the_counters_of_the_last_pass(self):
        # The harness of tests/test_console16.py: an authored conversion whose pass wrote (or did not write) the counters file.
        try:
            import test_console16 as harness
        except ImportError:
            from tests import test_console16 as harness
        for written in (True, False):
            case = harness.Console16Tests('test_md_header_identifies_linear_bin_and_region')
            case.setUp()
            try:
                if written:
                    project = case.root / 'project'
                    project.mkdir()
                    counters = static.new_counters()
                    counters['roots_accepted'] = 7
                    (project / 'static-discovery.json').write_text(json.dumps(counters), encoding='utf-8')
                report = case.scan_conversion(advanced=False, passes=1)[1]
            finally:
                case.doCleanups()
            if written:
                self.assertEqual(report['static_discovery'], counters)
            else:
                self.assertNotIn('static_discovery', report)

    def test_prepare16_gives_the_roots_to_the_step_generator_only(self):
        from retrorecomp import console16, megadrive
        try:
            import test_console16 as harness
        except ImportError:
            from tests import test_console16 as harness
        events = []
        counters = static.new_counters()
        counters['roots_accepted'] = 2
        roots = {0x400, 0x402}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'Authored.md'
            source.write_bytes(harness.md())
            rom = console16.conversion_rom(source, 'md')
            profile = megadrive.profile_for(rom)
            project = root / '.build' / ('md-' + profile['id'])
            seen = {}

            def write_profile(project_path, engine, rom_, entries):
                (project_path / 'game.toml').write_text('[functions]\nextra = []\n', encoding='utf-8')
                return profile['prefix']

            def generate(compiler, project_path, rom_file, **options):
                events.append('generate')
                seen['toml'] = (project_path / 'game.toml').read_text(encoding='utf-8')
                (project_path / 'generated').mkdir(exist_ok=True)
                (project_path / f'generated/{profile["prefix"]}_cycles.c').write_text('{0x200u, 1},\n{0x210u, 2},\n', encoding='ascii')

            def static_roots(engine, project_path, rom_, seeds, ram_variants):
                events.append('roots')
                seen['seeds'] = set(seeds)
                seen['counters_at_roots'] = (project_path / console16.STATIC_DISCOVERY).exists()   # the earlier pass's file is gone
                return roots, counters

            def generate_steps(engine, project_path, rom_, addresses, ram_variants=(), **options):
                events.append('steps')
                seen['addresses'] = set(addresses)
                return {'translated_instructions': 1, 'guarded_ram_variants': 0}

            def write_build(project_path, engine, system_id, title, rom_):
                (project_path / 'z80-native-analysis.json').write_text(
                    json.dumps({'guarded_positions': 0, 'shared_native_bodies': 0}), encoding='utf-8')

            project.mkdir(parents=True)
            (project / console16.STATIC_DISCOVERY).write_text('{"stale": true}', encoding='utf-8')
            emitted = []
            with patch.object(console16, 'ROOT', root), \
                    patch.object(console16, 'dependencies16', return_value=(Path('engine'), 'compiler', 'sdl', 'cmake', 'generator')), \
                    patch.object(console16.guns16, 'write_header'), \
                    patch.object(console16, '_write_build', side_effect=write_build), \
                    patch.object(console16, 'build_executable', return_value=Path('game.exe')), \
                    patch.object(static, 'static_roots', side_effect=static_roots), \
                    patch.object(megadrive, 'read_entries', return_value={0x300}), \
                    patch.object(megadrive, 'read_ram_variants', return_value=[]), \
                    patch.object(megadrive, 'write_profile', side_effect=write_profile), \
                    patch.object(megadrive, 'write_spec'), \
                    patch.object(megadrive, 'analysis_identity', return_value={'identity': 1}), \
                    patch.object(megadrive, 'generate', side_effect=generate), \
                    patch('retrorecomp.megadrive_codegen.generate_steps', side_effect=generate_steps), \
                    patch('retrorecomp.resources.embed_resources'), \
                    patch('retrorecomp.console16_optimization.build_game'):
                console16.prepare16(source, 'md', emit=emitted.append)
            self.assertEqual(events, ['generate', 'roots', 'steps'])            # the engine pass ran before any root existed
            self.assertFalse(seen['counters_at_roots'])
            self.assertTrue({0x200, 0x210, 0x300} <= seen['seeds'])
            self.assertTrue(roots.isdisjoint(seen['seeds']))
            self.assertEqual(seen['addresses'], seen['seeds'] | roots)           # the step generator gets seeds and roots
            self.assertEqual((project / 'game.toml').read_text(encoding='utf-8'), seen['toml'])   # game.toml never receives a root
            self.assertEqual(json.loads((project / console16.STATIC_DISCOVERY).read_text(encoding='utf-8')), counters)
            self.assertTrue(any(line.startswith('Static discovery: 2 roots from reached code') for line in emitted), emitted)

    def test_the_counters_file_is_read_back_or_absent(self):
        from retrorecomp import console16
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(console16._read_static_discovery(Path(folder)))
            counters = discover(a1c_image())[1]
            (Path(folder) / console16.STATIC_DISCOVERY).write_text(json.dumps(counters), encoding='utf-8')
            self.assertEqual(console16._read_static_discovery(Path(folder)), counters)
            (Path(folder) / console16.STATIC_DISCOVERY).write_text('{', encoding='utf-8')
            self.assertIsNone(console16._read_static_discovery(Path(folder)))


def decoder_tool():
    for candidate in ('md_decode.exe', 'Release/md_decode.exe', 'md_decode'):
        path = ROOT / '.build/megadrive-step-decoder-rules/build' / candidate
        if path.is_file():
            return path
    return None


HEADER = ROOT / '.deps/segagenesisrecomp/external/m68k-recomp-core/common/m68k_decoder.h'


@unittest.skipUnless(decoder_tool() and HEADER.is_file(), 'the pinned decoder tool is not built in this tree')
class PinnedDecoderTests(Checks):
    @classmethod
    def setUpClass(cls):
        from retrorecomp.m68000 import mnemonic_names
        cls.names = mnemonic_names(ROOT / '.deps/segagenesisrecomp')

    @staticmethod
    def facts(decoded):
        return [(i['addr'], i['byte_length'], i['name'], i['has_target'], i['target_addr'] if i['has_target'] else None)
                for i in decoded]

    def real(self, data, directory):
        rom, listing, output = directory / 'rom.bin', directory / 'pcs.txt', directory / 'out.json'
        rom.write_bytes(data)

        def decode(pcs):
            listing.write_text(''.join(f'{pc:06x}\n' for pc in sorted(pcs)), encoding='ascii')
            subprocess.run([str(decoder_tool()), str(rom), str(listing), str(output), '--follow-flow'],
                           check=True, cwd=directory, capture_output=True)
            decoded = json.loads(output.read_text(encoding='utf-8'))
            for ins in decoded:
                ins['name'] = self.names[ins['mnemonic']]
            return sorted(decoded, key=lambda ins: ins['addr'])
        return decode

    def test_the_fake_decoder_agrees_with_the_pinned_one_and_a_root_decodes_its_own_bytes(self):
        scenarios = [a1c_image(), a1c_image(jump=0x4e90),
                     image(at(0x200, 0x41fa, 0x0008, 0x2270, 0x0000, 0x4ed1), at(0x20a, *[long(t) for t in TABLE]), *handlers(*TABLE)),
                     image(at(0x200, 0x41fb, 0x0006, 0xd0d0, 0x4ed0), at(0x208, 0x18, 0x1a, 0x1c, 1), *handlers(*TABLE)),
                     image(at(0x200, 0x41fa, 0x000a, 0x3030, 0x0002, 0x4ef0, 0x0004), at(0x20e, 0x10, 0x14), *handlers(0x220, 0x224)),
                     image(at(0x200, 0x303b, 0x0006, 0x4efb, 0x0002), at(0x208, 0x18, 0x1c), *handlers(0x220, 0x224)),
                     image(at(0x200, 0x4efb, 0x0002), at(0x204, 0x6000 + 0x1a, 0x6000 + 0x1c, NOP), *handlers(0x220, 0x224)),
                     image(at(0x200, 0x4efb, 0x0002), at(0x204, 0x4ef9, long(0x220), 0x4ef9, long(0x224)), *handlers(0x220, 0x224)),
                     image(at(0x200, 0x0680, long(0x20a), 0x4ef6, 0x0800), at(0x20a, *[long(t) for t in TABLE]), *handlers(*TABLE)),
                     image(at(0x200, 0x20bc, long(0x220), 0x4e72, 0x2700, 0x007c, 0x0700, 0x4e40, 0x6002, NOP, 0x4afc),
                           at(0x220, *FOUR))]
        with tempfile.TemporaryDirectory() as folder:
            for number, data in enumerate(scenarios):
                directory = Path(folder) / str(number)
                directory.mkdir()
                real, fake = self.real(data, directory), FakeDecoder(data)
                self.assertEqual(self.facts(real({0x200})), self.facts(fake({0x200})), number)
                roots, counters = anchored_roots(data, real, {0x200}, mapper=False)
                self.assertEqual(roots, discover(data)[0], number)
                self.assertCounted(counters)
                if number == 0:
                    self.assertEqual(roots, set(TABLE))
                    final = {i['addr']: i for i in real({0x200} | roots)}
                    for root in roots:                      # the decode of a root is the decode of its own bytes
                        words = final[root]['words'][:final[root]['word_count']]
                        self.assertEqual(words, [int.from_bytes(data[root + 2 * n:root + 2 * n + 2], 'big')
                                                 for n in range(len(words))])


if __name__ == '__main__':
    unittest.main()
