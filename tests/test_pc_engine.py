"""The PC Engine (experimental, developer-only): HuCard reader, profile, identification report, paths, upstream.

Every HuCard image is built here from synthetic bytes (a reset vector and zeros) inside a temporary folder: no
ROM is read and nothing is written elsewhere. Nothing here reaches the user's preferences.
"""
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import (compilation_inputs, hostkit, path_profiles, pce_build, pce_conversion, psx_build, report_schema,
                         upstreams)
from retrorecomp.core import ConversionError
from retrorecomp.pce_rom import (BANK, HEADER, SF2_BYTES, HuCard, PcEngineRomError, board_for, decode,
                                 read_hucard)
from retrorecomp.systems import (ALL_PROFILES, PROFILES, ROM_CANDIDATE_EXTENSIONS, UnsupportedConsoleError,
                                 get_profile, profile_for_path)
from retrorecomp.systems.registry import convertible_profiles
from retrorecomp.systems.pc_engine import PC_ENGINE

KIB = 1024
MIB = 1024 * 1024
REVERSED = bytes(int(f'{value:08b}'[::-1], 2) for value in range(256))


def card(banks, vector=0xE000):
    """A synthetic HuCard of `banks` x 8 KiB: zeros, with the reset vector at $1FFE/$1FFF of bank 0."""
    data = bytearray(banks * BANK)
    data[0x1FFE] = vector & 0xFF
    data[0x1FFF] = vector >> 8
    return bytes(data)


def reverse_bits(data):
    return data.translate(REVERSED)


def plausible(vector):
    return 0xE000 <= vector <= 0xFFFF


def bit_reversed_vector(vector):
    """The vector read from a card whose bytes are stored bit-reversed: its two bytes reversed."""
    return REVERSED[vector & 0xFF] | REVERSED[vector >> 8] << 8


def vector_plausible_only_linearly():
    return next(value for value in range(0xE000, 0x10000) if not plausible(bit_reversed_vector(value)))


def vector_plausible_only_reversed():
    return next(value for value in range(0x10000) if not plausible(value) and plausible(bit_reversed_vector(value)))


def vector_plausible_both_ways():
    return next(value for value in range(0xE000, 0x10000) if plausible(bit_reversed_vector(value)))


def vector_plausible_neither_way():
    return next(value for value in range(0x10000)
                if not plausible(value) and not plausible(bit_reversed_vector(value)))


class TempFiles(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def write(self, data, name='Synthetic Game.pce'):
        path = self.root / name
        path.write_bytes(data)
        return path


class ReaderTests(TempFiles):
    def test_a_linear_card(self):
        data = card(32)                                      # 256 KiB
        path = self.write(data)
        found = read_hucard(path)
        self.assertIsInstance(found, HuCard)
        self.assertEqual('none', found.header)
        self.assertEqual('linear', found.encoding)
        self.assertEqual('base', found.board)
        self.assertEqual(256 * KIB, found.rom_bytes)
        self.assertEqual(256 * KIB, found.size)
        self.assertEqual(32, found.banks)
        self.assertEqual(0xE000, found.reset_vector)
        self.assertEqual(hashlib.sha256(data).hexdigest(), found.sha256)
        self.assertEqual(found.sha256, found.decoded_sha256)
        self.assertEqual(found.sha256, found.game_key)
        self.assertEqual('Synthetic Game', found.title)
        meta = found.metadata()
        for key in ('name', 'path', 'sha256', 'size', 'decoded_sha256', 'rom_bytes', 'header', 'encoding',
                    'board', 'reset_vector', 'system'):
            self.assertIn(key, meta)
        self.assertEqual('pce', meta['system'])
        self.assertEqual('Synthetic Game.pce', meta['name'])
        self.assertEqual(found.sha256, meta['sha256'])

    def test_a_copier_header_is_skipped(self):
        plain = card(16)
        headed = bytes(range(256)) * 2 + plain               # 512 bytes of anything
        self.assertEqual(HEADER, len(headed) - len(plain))
        found = read_hucard(self.write(headed))
        self.assertEqual('copier512', found.header)
        self.assertEqual(len(headed), found.size)
        self.assertEqual(len(plain), found.rom_bytes)
        self.assertEqual(hashlib.sha256(headed).hexdigest(), found.sha256)
        self.assertNotEqual(found.sha256, found.decoded_sha256)
        self.assertEqual(hashlib.sha256(plain).hexdigest(), found.decoded_sha256)
        self.assertEqual(read_hucard(self.write(plain, 'plain.pce')).decoded_sha256, found.decoded_sha256)

    def test_a_bit_reversed_card_is_decoded_to_linear(self):
        vector = vector_plausible_only_linearly()
        self.assertTrue(plausible(vector))
        linear = card(16, vector)
        reversed_card = reverse_bits(linear)
        # The stored vector, read as it is, is outside $E000-$FFFF: only the reversal makes it plausible.
        self.assertFalse(plausible(reversed_card[0x1FFE] | reversed_card[0x1FFF] << 8))
        found = read_hucard(self.write(reversed_card))
        self.assertEqual('bit-reversed', found.encoding)
        self.assertEqual(hashlib.sha256(linear).hexdigest(), found.decoded_sha256)
        self.assertEqual(hashlib.sha256(reversed_card).hexdigest(), found.sha256)
        self.assertNotEqual(found.sha256, found.decoded_sha256)
        self.assertEqual(vector, found.reset_vector)
        decoded, header, encoding = decode(reversed_card)
        self.assertEqual((linear, 'none', 'bit-reversed'), (decoded, header, encoding))

    def test_a_bit_reversed_card_with_a_header(self):
        vector = vector_plausible_only_linearly()
        linear = card(8, vector)
        found = read_hucard(self.write(bytes(HEADER) + reverse_bits(linear)))
        self.assertEqual(('copier512', 'bit-reversed'), (found.header, found.encoding))
        self.assertEqual(hashlib.sha256(linear).hexdigest(), found.decoded_sha256)

    def test_the_helper_finds_the_three_kinds_of_vector(self):
        self.assertTrue(plausible(vector_plausible_both_ways()))
        self.assertTrue(plausible(bit_reversed_vector(vector_plausible_both_ways())))
        self.assertFalse(plausible(vector_plausible_neither_way()))
        self.assertFalse(plausible(bit_reversed_vector(vector_plausible_neither_way())))

    def test_an_ambiguous_vector_stays_linear(self):
        vector = vector_plausible_both_ways()
        data = card(8, vector)
        found = read_hucard(self.write(data))
        self.assertEqual('linear', found.encoding)
        self.assertEqual(hashlib.sha256(data).hexdigest(), found.decoded_sha256)
        self.assertEqual(vector, found.reset_vector)

    def reset_card(self, vector, opcode):
        """A card whose reset code starts with `opcode` (the byte at the vector's offset in bank 0)."""
        data = bytearray(card(8, vector))
        data[vector - 0xE000] = opcode
        return bytes(data)

    def test_an_ambiguous_vector_is_decided_by_the_first_instruction(self):
        # $E7A3 reads as $E7C5 once the bits are turned: both point into $E000-$FFFF (Tiger Road, TaleSpin, Bravoman
        # and Legend of Hero Tonma are such cards).
        vector = 0xE7A3
        self.assertTrue(plausible(vector) and plausible(bit_reversed_vector(vector)))
        for opcode in (0x78, 0xEA, 0xD4):
            with self.subTest(f'SEI/NOP/CSH {opcode:02X}, as stored'):
                linear = self.reset_card(vector, opcode)
                found = read_hucard(self.write(linear))
                self.assertEqual('linear', found.encoding)
                self.assertEqual(hashlib.sha256(linear).hexdigest(), found.decoded_sha256)
            with self.subTest(f'SEI/NOP/CSH {opcode:02X}, bits reversed'):
                linear = self.reset_card(vector, opcode)
                found = read_hucard(self.write(reverse_bits(linear), 'rev.pce'))
                self.assertEqual('bit-reversed', found.encoding)
                self.assertEqual(vector, found.reset_vector)
                self.assertEqual(hashlib.sha256(linear).hexdigest(), found.decoded_sha256)

    def test_an_ambiguous_vector_with_no_reset_instruction_either_way_stays_linear(self):
        # Neither reading starts with SEI, NOP or CSH: nothing decides, the rule of the written order applies.
        vector = 0xE7A3
        for opcode in (0x00, 0x4C, 0xA9, 0x9C):
            with self.subTest(f'{opcode:02X}'):
                linear = self.reset_card(vector, opcode)
                self.assertEqual('linear', read_hucard(self.write(linear)).encoding)
                self.assertEqual('linear', read_hucard(self.write(reverse_bits(linear), 'rev.pce')).encoding)

    def test_a_vector_that_is_its_own_reversal(self):
        # $FF00 reads the same in both orders (Legend of Hero Tonma): the byte it points at decides, $78 as stored
        # (linear) or $1E, the reversal of $78 (bit-reversed).
        vector = 0xFF00
        self.assertEqual(vector, bit_reversed_vector(vector))
        data = self.reset_card(vector, 0x78)
        self.assertEqual('linear', read_hucard(self.write(data)).encoding)
        found = read_hucard(self.write(reverse_bits(data), 'rev.pce'))
        self.assertEqual(('bit-reversed', hashlib.sha256(data).hexdigest()), (found.encoding, found.decoded_sha256))

    def test_a_vector_plausible_in_neither_order_is_refused(self):
        data = card(8, vector_plausible_neither_way())
        with self.assertRaises(PcEngineRomError):
            read_hucard(self.write(data))
        with self.assertRaises(PcEngineRomError):
            decode(data)

    def test_the_vector_bounds(self):
        # $E000 is the first plausible vector and $FFFF the last; $DFFF fails linearly (and, reversed, too).
        self.assertEqual('linear', read_hucard(self.write(card(1, 0xE000), 'low.pce')).encoding)
        self.assertEqual('linear', read_hucard(self.write(card(1, 0xFFFF), 'high.pce')).encoding)
        self.assertEqual(0xFFFF, read_hucard(self.write(card(1, 0xFFFF), 'high.pce')).reset_vector)
        # The highest vector below $E000 that fails in both orders is refused; $E000 - 1 itself reads as
        # bit-reversed when its reversal is plausible, which is the rule, not a bound of the linear test.
        below = max(value for value in range(0xE000) if not plausible(bit_reversed_vector(value)))
        with self.assertRaises(PcEngineRomError):
            read_hucard(self.write(card(1, below), 'below.pce'))
        self.assertEqual('bit-reversed', read_hucard(self.write(card(1, 0xDFFF), 'rev.pce')).encoding)

    def test_sizes_that_are_not_banks_are_refused(self):
        for name, size in (('odd', BANK + 1), ('short bank', BANK - 1), ('bank and 511', BANK + 511),
                           ('bank and 513', BANK + 513), ('four banks less 1', 4 * BANK - 1)):
            with self.subTest(name):
                data = bytearray(size)
                with self.assertRaises(PcEngineRomError):
                    read_hucard(self.write(bytes(data), 'odd.pce'))
                with self.assertRaises(PcEngineRomError):
                    decode(bytes(data))

    def test_an_empty_file_and_a_bare_header_are_refused(self):
        for name, size in (('empty', 0), ('header only', HEADER)):
            with self.subTest(name):
                with self.assertRaises(PcEngineRomError):
                    read_hucard(self.write(bytes(size), 'none.pce'))
                with self.assertRaises(PcEngineRomError):
                    decode(bytes(size))

    def test_a_base_card_over_1_mib_is_refused_unless_it_is_the_sf2_size(self):
        for name, banks in (('1.5 MiB', 192), ('1 MiB + 1 bank', 129), ('2 MiB', 256)):
            with self.subTest(name):
                with self.assertRaises(PcEngineRomError):
                    read_hucard(self.write(card(banks), 'big.pce'))
        with self.assertRaises(PcEngineRomError):            # also with a header
            read_hucard(self.write(bytes(HEADER) + card(192), 'big.pce'))

    def test_a_file_over_2_5_mib_plus_the_header_is_refused(self):
        with self.assertRaises(PcEngineRomError):
            read_hucard(self.write(card(SF2_BYTES // BANK + 1), 'huge.pce'))
        with self.assertRaises(PcEngineRomError):
            read_hucard(self.write(bytes(HEADER) + card(SF2_BYTES // BANK + 1), 'huge.pce'))

    def test_a_wrong_extension_is_refused(self):
        for name in ('game.bin', 'game.rom', 'game', 'game.pce.bak'):
            with self.subTest(name):
                with self.assertRaises(PcEngineRomError):
                    read_hucard(self.write(card(8), name))

    def test_the_extension_is_case_insensitive(self):
        self.assertEqual('base', read_hucard(self.write(card(8), 'GAME.PCE')).board)

    def test_a_missing_file_is_not_a_card(self):
        with self.assertRaises(OSError):
            read_hucard(self.root / 'missing.pce')

    def test_boards(self):
        sf2 = card(SF2_BYTES // BANK)
        self.assertEqual(2621440, SF2_BYTES)
        self.assertEqual(2.5 * MIB, SF2_BYTES)
        found = read_hucard(self.write(sf2, 'sf2.pce'))
        self.assertEqual(('sf2', 'none', SF2_BYTES), (found.board, found.header, found.rom_bytes))
        found = read_hucard(self.write(bytes(HEADER) + sf2, 'sf2h.pce'))
        self.assertEqual(('sf2', 'copier512', SF2_BYTES), (found.board, found.header, found.rom_bytes))
        for name, banks in (('8 KiB', 1), ('1 MiB', MIB // BANK), ('384 KiB', 48), ('768 KiB', 96)):
            with self.subTest(name):
                found = read_hucard(self.write(card(banks), 'base.pce'))
                self.assertEqual('base', found.board)
                self.assertEqual(banks * BANK, found.rom_bytes)
                self.assertEqual(banks, found.banks)

    def test_board_for(self):
        self.assertEqual('sf2', board_for(SF2_BYTES))
        self.assertEqual('base', board_for(MIB))
        self.assertEqual('base', board_for(BANK))

    def test_engine_options(self):
        found = read_hucard(self.write(card(16)))
        self.assertEqual(['--hucard-reset', 'base', '--rom-header', 'none', '--rom-encoding', 'linear'],
                         found.engine_options())
        vector = vector_plausible_only_linearly()
        found = read_hucard(self.write(bytes(HEADER) + reverse_bits(card(SF2_BYTES // BANK, vector)), 'x.pce'))
        self.assertEqual(['--hucard-reset', 'sf2', '--rom-header', 'copier512', '--rom-encoding', 'bit-reversed'],
                         found.engine_options())


class ProfileTests(TempFiles):
    def test_the_profile_is_experimental_listed_and_available_with_its_files(self):
        profile = get_profile('pce')
        self.assertEqual('experimental', profile.status)
        self.assertFalse(profile.developer_only)
        self.assertTrue(profile.available())          # this checkout carries the native files
        self.assertIn(profile, ALL_PROFILES)
        self.assertIn(profile, PROFILES)
        self.assertIn(profile, convertible_profiles())
        self.assertEqual(1, len(profile.cpus))
        cpu = profile.cpus[0]
        self.assertEqual(('huc6280', 'main', 'instructions'), (cpu.arch, cpu.role, cpu.unit))
        self.assertEqual(('ntsc',), profile.video_modes)
        self.assertEqual(('.pce',), profile.extensions)

    def test_a_pce_file_is_a_candidate_and_identified(self):
        self.assertIn('.pce', ROM_CANDIDATE_EXTENSIONS)
        path = self.write(card(16))
        self.assertIs(get_profile('pce'), profile_for_path(path))

    def test_this_checkout_carries_the_converter_files(self):
        from retrorecomp.pce_rom import CONVERTER_FILES
        from retrorecomp.paths import ROOT
        for name in CONVERTER_FILES:
            self.assertTrue((ROOT / name).is_file(), name)

    def test_read_rom_is_the_reader(self):
        path = self.write(card(16))
        self.assertEqual(read_hucard(path), get_profile('pce').read_rom(path))


class ReportTests(TempFiles):
    def test_the_identification_report_claims_no_measure(self):
        found = read_hucard(self.write(card(16)))
        destination = self.root / 'report.json'
        written = pce_conversion.write_identification_report(destination, found)
        self.assertTrue(destination.is_file())
        self.assertEqual(report_schema.SCHEMA_VERSION, 2)
        self.assertEqual({'name': report_schema.SCHEMA_NAME, 'version': 2}, written['schema'])
        report = report_schema.read_report(destination)
        self.assertEqual({'name': report_schema.SCHEMA_NAME, 'version': 2}, report['schema'])
        self.assertEqual('pce', report['system']['id'])
        self.assertEqual('experimental', report['system']['status'])
        self.assertEqual('pce_conversion', report['read_from']['writer'])   # recognised by the marker hucard_checks
        self.assertEqual('pce', report['rom']['system'])
        self.assertEqual(found.sha256, report['rom']['sha256'])
        validation = report['validation']
        self.assertEqual('not converted', validation['native_code']['coverage_note'])
        self.assertFalse(validation['cpu_fidelity']['passed'])
        self.assertFalse(validation['hardware_fidelity']['validated'])
        self.assertFalse(validation['gameplay']['validated'])
        self.assertFalse(validation['latency']['measured'])
        self.assertIsNone(validation['latency']['ms'])
        honesty = report['honesty']
        self.assertFalse(honesty['cpu_fidelity_validated'])
        self.assertFalse(honesty['hardware_fidelity_validated'])
        self.assertFalse(honesty['full_game_validated'])
        self.assertFalse(honesty['physical_latency_measured'])
        self.assertFalse(honesty['independent_cpu_oracle'])

    def test_the_writer_keys_stay_beside_the_schema_2_keys(self):
        import json
        found = read_hucard(self.write(card(16)))
        destination = self.root / 'report.json'
        pce_conversion.write_identification_report(destination, found)
        raw = json.loads(destination.read_text(encoding='utf-8'))
        self.assertIn('hucard_checks', raw)                  # the marker of this writer
        self.assertEqual('experimental', raw['status'])
        self.assertEqual({'name': report_schema.SCHEMA_NAME, 'version': 2}, raw['schema'])
        self.assertFalse(raw['converted'])
        self.assertFalse(raw['hardware_accuracy_validated'])
        self.assertFalse(raw['full_game_validated'])
        self.assertIsNone(raw['latency_ms'])
        self.assertFalse(raw['native_validation']['cpu_fidelity_validated'])
        self.assertFalse(raw['native_validation']['independent_cpu_oracle'])

    def test_the_report_has_no_native_code_claim(self):
        found = read_hucard(self.write(card(16)))
        report = pce_conversion.identification_report(found)
        self.assertEqual('not converted', report['native_coverage'])
        self.assertEqual([], report['final_checks'])
        self.assertEqual('standard', report['scan_level'])
        self.assertEqual('Retro-Recomp', report['tool'])
        self.assertFalse(report['game_states']['supported'])


class PathsAndUpstreamTests(unittest.TestCase):
    def test_the_path_sections_and_bounds(self):
        self.assertEqual((('huc6280', 'pce'),), path_profiles.SYSTEM_SECTIONS['pce'])
        self.assertEqual(('pce',), path_profiles.PROFILES[('huc6280', 'pce')].systems)
        self.assertEqual((0x2000, 0x280000), tuple(path_profiles.SOURCE_BOUNDS['pce']['rom']))
        self.assertEqual(SF2_BYTES, path_profiles.SOURCE_BOUNDS['pce']['rom'][1])

    def test_an_experimental_machine_shares_nothing(self):
        self.assertNotIn('pce', path_profiles.SHARED_SYSTEMS)
        self.assertNotIn('pce', path_profiles.STABLE_SHARED)
        self.assertNotIn('pce', path_profiles.EXPERIMENTAL_SHARED)
        self.assertIsNone(get_profile('pce').shared_knowledge)

    def test_the_engine_upstream_is_pinned_in_the_code(self):
        declared = upstreams.MACHINE_UPSTREAMS['pce']
        self.assertEqual(['rages4calm/pcenginerecomp'], [item.repo for item in declared])
        pin = upstreams.read_pin(declared[0].pin)
        self.assertEqual(pce_conversion.ENGINE_REV, pin)
        self.assertRegex(pin, r'^[0-9a-f]{40}$')
        self.assertEqual(pin, upstreams.pin_of(declared[0]))
        self.assertEqual(pce_conversion.ENGINE_REPO, declared[0].repo)


# ---------------------------------------------------------------------------------------------------------------
# The conversion layer, without compiling, running a game, the network or a ROM.

IDENTITY = hashlib.sha256(b'synthetic identity one').hexdigest()
OTHER_IDENTITY = hashlib.sha256(b'synthetic identity two').hexdigest()
LEVEL_ROUTES = {'quick': ['play'], 'standard': ['attract', 'play'],
                'extended': ['attract', 'play', 'long-1'], 'thorough': ['attract', 'play', 'long-1', 'long-2']}


def parse_script(text):
    """The rules of load_script in native/pce_main.c: 'frame p1 p2' (frame decimal, masks hex), frames never going
    back, masks at most 0xfff, at most 8192 lines; '#' and blank lines are skipped. Returns [(frame, p1, p2)]."""
    rows, last = [], 0
    for line in text.splitlines(True):
        if line[0] in '#\r\n':
            continue
        assert len(rows) < 8192, 'more than 8192 lines'
        fields = line.split()
        assert len(fields) in (3, 5), f'bad field count: {line!r}'
        frame, masks = int(fields[0]), [int(field, 16) for field in fields[1:]]
        assert frame >= last, f'frame goes back: {line!r}'
        assert all(mask <= 0xFFF for mask in masks), f'mask over 0xfff: {line!r}'
        last = frame
        rows.append((frame, *masks[:2]))
    assert rows, 'an empty script'
    return rows


class RouteTests(unittest.TestCase):
    def test_the_routes_of_each_level(self):
        for level, names in LEVEL_ROUTES.items():
            with self.subTest(level):
                found = pce_conversion.routes(IDENTITY, frames=3600, level=level)
                self.assertEqual(names, [name for name, _, _ in found])

    def test_the_frame_counts_of_the_routes(self):
        found = {name: count for name, count, _ in pce_conversion.routes(IDENTITY, frames=3600, level='thorough')}
        self.assertEqual({'attract': 3600, 'play': 3600, 'long-1': 18000, 'long-2': 18000}, found)
        self.assertEqual(18000, pce_conversion.LONG_FRAMES)
        # A short request still plays at least 1800 frames; the attract route keeps the requested count.
        found = {name: count for name, count, _ in pce_conversion.routes(IDENTITY, frames=600, level='standard')}
        self.assertEqual({'attract': 600, 'play': 1800}, found)

    def test_every_script_follows_the_rules_of_the_native_reader(self):
        for frames in (600, 3600, 10000):
            for name, count, text in pce_conversion.routes(IDENTITY, frames=frames, level='thorough'):
                with self.subTest(name=name, frames=frames):
                    rows = parse_script(text)
                    self.assertLessEqual(len(rows), 8192)
                    self.assertTrue(text.endswith('\n'))
                    self.assertTrue(all(row[0] < count for row in rows) or name == 'attract')
                    self.assertEqual(rows, sorted(rows, key=lambda row: row[0]))

    def test_attract_presses_nothing(self):
        found = {name: text for name, _, text in pce_conversion.routes(IDENTITY, frames=3600, level='standard')}
        self.assertEqual([(0, 0, 0)], parse_script(found['attract']))

    def test_the_scripts_are_deterministic_and_depend_on_the_identity(self):
        first = pce_conversion.routes(IDENTITY, frames=3600, level='thorough')
        self.assertEqual(first, pce_conversion.routes(IDENTITY, frames=3600, level='thorough'))
        other = pce_conversion.routes(OTHER_IDENTITY, frames=3600, level='thorough')
        self.assertEqual([name for name, _, _ in first], [name for name, _, _ in other])
        for (name, _, mine), (_, _, theirs) in zip(first, other):
            if name != 'attract':
                with self.subTest(name):
                    self.assertNotEqual(mine, theirs)

    def test_the_long_routes_differ_from_each_other_and_from_play(self):
        texts = {name: text for name, _, text in pce_conversion.routes(IDENTITY, frames=3600, level='thorough')}
        self.assertEqual(3, len({texts['play'], texts['long-1'], texts['long-2']}))

    def runs(self, text):
        """The frames at which Run goes down (a press is a change from released to held)."""
        down, previous = [], False
        for frame, p1, _ in parse_script(text):
            held = bool(p1 & pce_conversion.RUN)
            if held and not previous:
                down.append(frame)
            previous = held
        return down

    def test_the_start_presses_come_every_240_frames(self):
        for presses in pce_conversion.START_PRESSES:
            with self.subTest(presses=presses):
                plan = {name: text for name, _, text in
                        pce_conversion.routes(IDENTITY, frames=10000, level='standard', presses=presses)}
                self.assertEqual([240 * k for k in range(1, presses + 1)],
                                 self.runs(plan['play'])[:presses])
                rows = {row[0]: row for row in parse_script(plan['play'])}
                for at in (240 * k for k in range(1, presses + 1)):
                    self.assertEqual((at, pce_conversion.RUN, 0), rows[at])
                    self.assertEqual((at + 6, 0, 0), rows[at + 6])      # released a few frames later

    def test_after_the_start_run_comes_only_as_a_pair_every_900_frames(self):
        for presses in pce_conversion.START_PRESSES:
            for name, _, text in pce_conversion.routes(IDENTITY, frames=10000, level='thorough', presses=presses):
                with self.subTest(presses=presses, name=name):
                    late = self.runs(text)[presses:]
                    self.assertEqual(0, len(late) % 2)
                    pairs = list(zip(late[::2], late[1::2]))
                    for first, second in pairs:
                        self.assertEqual(24, second - first)
                    firsts = [first for first, _ in pairs]
                    self.assertTrue(all(b - a >= pce_conversion.RUN_PAIR_EVERY for a, b in zip(firsts, firsts[1:])))
                    self.assertTrue(all(first >= pce_conversion.walk_start(presses) for first in firsts))

    def test_the_first_part_of_the_walk_uses_the_directions_only(self):
        for presses in pce_conversion.START_PRESSES:
            start = pce_conversion.walk_start(presses)
            buttons = pce_conversion.I | pce_conversion.II
            for name, _, text in pce_conversion.routes(IDENTITY, frames=10000, level='thorough', presses=presses):
                if name == 'attract':
                    continue
                with self.subTest(presses=presses, name=name):
                    quiet = [row for row in parse_script(text) if start <= row[0] < start + pce_conversion.QUIET_WALK]
                    self.assertTrue(quiet)
                    self.assertEqual([], [row for row in quiet if row[1] & buttons])
                    self.assertTrue(any(row[1] & buttons for row in parse_script(text) if row[0] >= start + pce_conversion.QUIET_WALK))

    def test_the_walk_starts_after_the_last_press_and_a_settling_time(self):
        for presses in pce_conversion.START_PRESSES:
            self.assertGreaterEqual(pce_conversion.walk_start(presses), 240 * presses + pce_conversion.WALK_SETTLE)
            self.assertGreaterEqual(pce_conversion.walk_start(presses), 900)

    def test_the_candidates_leave_ten_seconds_of_walk(self):
        self.assertEqual([1, 2, 3, 4, 6], pce_conversion.start_candidates(3600))
        self.assertEqual([1, 2, 3, 4], pce_conversion.start_candidates(1800))
        self.assertEqual([], pce_conversion.start_candidates(1000))

    def test_the_second_pad_stays_idle(self):
        for name, _, text in pce_conversion.routes(IDENTITY, frames=3600, level='thorough'):
            with self.subTest(name):
                self.assertEqual({0}, {row[2] for row in parse_script(text)})

    def test_the_script_helper_refuses_what_the_native_reader_refuses(self):
        for bad in ('10 000 000\n5 000 000\n', '0 1000 000\n', '0 000\n', '0 zzz 000\n'):
            with self.subTest(bad):
                with self.assertRaises((AssertionError, ValueError)):
                    parse_script(bad)


def write_trace(path, rows):
    header = 'frame,cpu,ram,image,pcm,samples\n'
    path.write_text(header + ''.join(','.join(str(field) for field in row) + '\n' for row in rows), encoding='ascii')


class LivenessTests(TempFiles):
    SAMPLES = 735

    def silent(self):
        from retrorecomp.delivery_evidence import silent_hash
        return silent_hash(self.SAMPLES)

    def trace(self, pictures, loud):
        """One row per frame from 1: the pictures named, audible where the frame number is in `loud`."""
        silent = self.silent()
        rows = [(frame, f'{frame:016x}', f'{frame + 1000:016x}', picture,
                 f'{0xDEADBEEF + frame:016x}' if frame in loud else silent, self.SAMPLES)
                for frame, picture in enumerate(pictures, 1)]
        path = self.root / 'route.csv'
        write_trace(path, rows)
        return path

    def test_the_rows_carry_the_picture_and_the_audible_flag(self):
        path = self.trace(['0000000000000001', '0000000000000001', '0000000000000002'], loud={2})
        rows = list(pce_conversion.trace_rows(path))
        self.assertEqual([1, 2, 3], [row.frame for row in rows])
        self.assertEqual(['0000000000000001', '0000000000000001', '0000000000000002'], [row.picture for row in rows])
        self.assertEqual([False, True, False], [row.audible for row in rows])
        self.assertEqual(f'{0xDEADBEEF + 2:016x}', rows[1].sound)
        self.assertEqual(self.silent(), rows[0].sound)

    def test_lines_that_are_not_frames_are_skipped(self):
        silent = self.silent()
        path = self.root / 'odd.csv'
        path.write_text('frame,cpu,ram,image,pcm,samples\n'
                        f'1,a,b,c,{silent},{self.SAMPLES}\n'
                        '# a comment\n\n'
                        '2,a,b,c\n'                                  # too few fields
                        f'x,a,b,c,{silent},{self.SAMPLES}\n'         # not a frame number
                        f'3,a,b,d,{silent},{self.SAMPLES}\n', encoding='ascii')
        self.assertEqual([1, 3], [row.frame for row in pce_conversion.trace_rows(path)])

    def test_the_liveness_of_a_moving_and_audible_route(self):
        pictures = ['p1', 'p1', 'p2', 'p2', 'p3', 'p3', 'p3']
        record = pce_conversion.route_liveness(self.trace(pictures, loud={2, 6}))
        self.assertEqual({'frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame',
                          'audible_frames', 'last_audible_frame'}, set(record))
        self.assertEqual(7, record['frames'])
        self.assertEqual(3, record['distinct_pictures'])
        self.assertEqual(2, record['picture_changes'])
        self.assertEqual(5, record['last_picture_change_frame'])
        self.assertEqual(2, record['audible_frames'])
        self.assertEqual(6, record['last_audible_frame'])

    def test_a_picture_that_comes_back_is_a_change_but_not_a_new_picture(self):
        record = pce_conversion.route_liveness(self.trace(['a', 'b', 'a', 'b'], loud=set()))
        self.assertEqual((2, 3, 4), (record['distinct_pictures'], record['picture_changes'],
                                     record['last_picture_change_frame']))

    def test_a_silent_frozen_route(self):
        from retrorecomp.delivery_evidence import frozen_route
        record = pce_conversion.route_liveness(self.trace(['same'] * 5, loud=set()))
        self.assertEqual((5, 1, 0, 0), (record['frames'], record['distinct_pictures'], record['picture_changes'],
                                        record['last_picture_change_frame']))
        self.assertEqual((0, 0), (record['audible_frames'], record['last_audible_frame']))   # silent, not unknown
        self.assertTrue(frozen_route(record))

    def test_a_moving_route_is_not_frozen(self):
        from retrorecomp.delivery_evidence import frozen_route
        self.assertFalse(frozen_route(pce_conversion.route_liveness(self.trace(['a', 'b'], loud=set()))))

    def test_the_silence_hash_depends_on_the_sample_count(self):
        from retrorecomp.delivery_evidence import silent_hash
        silent = silent_hash(self.SAMPLES)
        path = self.root / 'counts.csv'
        write_trace(path, [(1, 'c', 'r', 'p', silent, self.SAMPLES), (2, 'c', 'r', 'p', silent, self.SAMPLES + 2)])
        self.assertEqual([False, True], [row.audible for row in pce_conversion.trace_rows(path)])


class Sentinel(Exception):
    """What a patched build step raises: the test proves it is the first thing to run."""


class MissingFilesTests(TempFiles):
    def setUp(self):
        super().setUp()
        self.installed = False
        patches = [mock.patch('retrorecomp.pce_rom.converter_available', side_effect=lambda: self.installed),
                   mock.patch('retrorecomp.feedback.ingest', return_value={}),
                   mock.patch('retrorecomp.paths.ROOT', self.root / 'repo')]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.path = self.write(card(16))

    def steps(self, **errors):
        """ensure_engine, prepare_game and build_game replaced by mocks that raise their `errors` (default: Sentinel)."""
        mocks = {}
        for name in ('ensure_engine', 'prepare_game', 'build_game'):
            patch = mock.patch.object(pce_build, name, side_effect=errors.get(name, Sentinel(name)))
            mocks[name] = patch.start()
            self.addCleanup(patch.stop)
        return mocks

    def open_machine(self):
        self.installed = True

    def convert(self, **options):
        return pce_conversion.convert(self.path, output=self.root / 'out', emit=lambda *_: None, **options)

    def test_the_machine_needs_its_native_files(self):
        self.assertFalse(PC_ENGINE.available())
        self.installed = True
        self.assertTrue(PC_ENGINE.available())
        self.assertTrue(get_profile('pce').available())

    def test_missing_files_refuse_before_any_build(self):
        mocks = self.steps()
        with self.assertRaises(ConversionError) as caught:
            self.convert()
        self.assertEqual(pce_conversion.NOT_YET, str(caught.exception))
        for name, step in mocks.items():
            with self.subTest(name):
                step.assert_not_called()
        self.assertFalse((self.root / 'out').exists())              # nothing was written either

    def test_missing_files_still_read_the_card_first(self):
        mocks = self.steps()
        with self.assertRaises(PcEngineRomError):
            pce_conversion.convert(self.write(bytes(100), 'junk.pce'), output=self.root / 'out')
        mocks['ensure_engine'].assert_not_called()

    def test_an_installed_machine_reaches_the_engine_first(self):
        self.open_machine()
        mocks = self.steps()
        with self.assertRaises(Sentinel) as caught:
            self.convert()
        self.assertEqual('ensure_engine', str(caught.exception))
        mocks['ensure_engine'].assert_called_once()
        mocks['prepare_game'].assert_not_called()
        mocks['build_game'].assert_not_called()

    def test_an_installed_machine_then_prepares_the_game(self):
        self.open_machine()
        mocks = self.steps(ensure_engine=None)
        with self.assertRaises(Sentinel) as caught:
            self.convert()
        self.assertEqual('prepare_game', str(caught.exception))
        mocks['prepare_game'].assert_called_once()
        mocks['build_game'].assert_not_called()
        self.assertIsNone(mocks['prepare_game'].call_args.kwargs['module'])   # the first pass is all interpreted

    def test_a_pal_override_is_refused_before_any_step(self):
        self.open_machine()
        mocks = self.steps()
        for override in ('pal', 'PAL', 'secam'):
            with self.subTest(override), self.assertRaises(ConversionError):
                self.convert(standard_override=override)
        for step in mocks.values():
            step.assert_not_called()

    def test_ntsc_and_auto_overrides_are_accepted(self):
        self.open_machine()
        self.steps()
        for override in (None, 'ntsc', 'auto'):
            with self.subTest(override), self.assertRaises(Sentinel):
                self.convert(standard_override=override)

    def test_a_cartridge_profile_is_refused_before_any_step(self):
        self.open_machine()
        mocks = self.steps()
        with self.assertRaises(ConversionError) as caught:
            self.convert(profile=self.root / 'game.toml')
        self.assertIn('TOML', str(caught.exception))
        for step in mocks.values():
            step.assert_not_called()

    def test_a_bad_title_or_scan_level_is_refused_before_any_step(self):
        self.open_machine()
        mocks = self.steps()
        for options in ({'title': 'bad\ntitle'}, {'title': 'x' * 161}, {'scan_level': 'impossible'}):
            with self.subTest(options), self.assertRaises(ConversionError):
                self.convert(**options)
        for step in mocks.values():
            step.assert_not_called()


class BackupRamCheckTests(TempFiles):
    """pce_conversion.check_backup on a fake game that behaves as native/pce_backup.c says, unless a test breaks one thing."""

    SHA = 'ab' * 32

    def fake_run(self, *, uses_damaged=False, keeps_nothing_aside=False, loses_write=False, reference_differs=False,
                 writes_without_change=False, writes_on_route=True, unformatted=False):
        def run(executable, where, name, count, script, *extra, ends_at=None):
            path = Path(extra[extra.index('--backup') + 1])
            memory, notice = bytes(2048) if unformatted else pce_conversion.BACKUP_FORMATTED, 0
            if path.exists():
                data = path.read_bytes()
                header = data[:pce_conversion.BACKUP_HEADER]
                if len(data) == 2160 and header[:8] == pce_conversion.BACKUP_MAGIC and header[8:12] == b'\x01\0\0\0' \
                        and header[12:16] == b'\0\x08\0\0' and header[40:104] == self.SHA.encode() \
                        and header[16:24] == pce_conversion.fnv64(data[112:]).to_bytes(8, 'little'):
                    memory = data[112:]
                elif uses_damaged:
                    memory = data[:2048].ljust(2048, b'\0')
                else:
                    notice = 1
                    if not keeps_nothing_aside:
                        path.rename(path.with_name(path.name + '.unusable-1'))
            start = memory
            if name == 'backup-route' and writes_on_route:
                memory = b'SAVE' + memory[4:]
            if name.startswith('backup-same'):
                memory = b'SAME' + memory[4:]
            if name == 'backup-none' and writes_without_change:
                path.write_bytes(b'x')
            elif memory != start and not (loses_write and name == 'backup-route'):
                path.write_bytes(pce_conversion.backup_file(memory, self.SHA))
            trace = where / f'{name}.csv'
            trace.write_text('reference' if reference_differs and '--reference' in extra else 'same', encoding='ascii')
            return {'backup_start_hash': f'{pce_conversion.fnv64(start):016x}', 'backup_hash': f'{pce_conversion.fnv64(memory):016x}',
                    'backup_notice': notice, 'backup_beyond': 0, 'trace': trace}
        return run

    def check(self, **broken):
        with mock.patch.object(pce_conversion, 'run', self.fake_run(**broken)):
            return pce_conversion.check_backup(Path('game.exe'), self.root / 'backup', 3600, Path('play.inputs'), self.SHA)

    def test_the_file_format_is_the_one_the_game_reads(self):
        self.assertEqual(14695981039346656037, pce_conversion.fnv64(b''))
        self.assertEqual(0xaf63dc4c8601ec8c, pce_conversion.fnv64(b'a'))
        data = pce_conversion.backup_file(pce_conversion.BACKUP_FORMATTED, self.SHA)
        self.assertEqual(112 + 2048, len(data))
        self.assertEqual(b'RRPCEBR1', data[:8])
        self.assertEqual((1, 2048), (int.from_bytes(data[8:12], 'little'), int.from_bytes(data[12:16], 'little')))
        self.assertEqual(pce_conversion.fnv64(data[112:]), int.from_bytes(data[16:24], 'little'))
        self.assertEqual(self.SHA.encode(), data[40:104])
        source = (Path(__file__).parents[1] / 'native/pce_backup.c').read_text(encoding='utf-8')
        for fragment in ("'R', 'R', 'P', 'C', 'E', 'B', 'R', '1'", 'HEADER_BYTES = 112', 'header + 16', 'header + 20', 'header + 40'):
            self.assertIn(fragment, source)

    def test_the_formatted_memory_is_written_down_in_both_places(self):
        self.assertEqual(b'HUBM\x00\x88\x10\x80', pce_conversion.BACKUP_FORMATTED[:8])
        self.assertEqual(bytes(2040), pce_conversion.BACKUP_FORMATTED[8:])
        source = (Path(__file__).parents[1] / 'native/pce_machine.cpp').read_text(encoding='utf-8')
        self.assertIn("{'H', 'U', 'B', 'M', 0x00, 0x88, 0x10, 0x80}", source)

    def test_every_damaged_file_differs_from_the_good_one(self):
        good = pce_conversion.backup_file(pce_conversion.BACKUP_FORMATTED, self.SHA)
        damaged = pce_conversion.damaged_backups(good)
        self.assertGreaterEqual(len(damaged), 10)
        self.assertNotIn(good, damaged.values())

    def test_a_game_that_keeps_the_rules_passes(self):
        result = self.check()
        self.assertTrue(result['play_route_wrote_memory'])
        self.assertTrue(result['written_memory_survives_a_fresh_process'])
        self.assertTrue(result['same_memory_reference_match'])
        self.assertEqual("the play route's", result['same_memory_was'])
        self.assertIn('other-card', result['damaged_files_set_aside'])

    def test_a_route_that_writes_nothing_says_so_and_uses_an_authored_file(self):
        result = self.check(writes_on_route=False)
        self.assertFalse(result['play_route_wrote_memory'])
        self.assertIsNone(result['written_memory_survives_a_fresh_process'])
        self.assertEqual('an authored file', result['same_memory_was'])

    def test_each_broken_rule_is_refused(self):
        for broken in ({'uses_damaged': True}, {'keeps_nothing_aside': True}, {'loses_write': True},
                       {'reference_differs': True}, {'writes_without_change': True}, {'unformatted': True}):
            with self.subTest(broken), tempfile.TemporaryDirectory() as folder:
                self.root = Path(folder)
                with self.assertRaises(ConversionError):
                    self.check(**broken)


class QuickStateCheckTests(TempFiles):
    """pce_conversion.check_states on a fake game: every damaged state must be refused and left alone."""

    STATE = bytes(range(256)) * 16

    def check(self, *, accepts=(), rewrites=(), creates_missing=False):
        frames = 1200
        expected = self.root / 'expected.csv'
        rows = ['frame,cpu,ram,image,pcm,samples'] + [f'{n},a,b,c,d,1' for n in range(frames)]
        expected.write_text('\n'.join(rows) + '\n', encoding='ascii')
        folder = self.root / 'states'
        folder.mkdir()

        def run(executable, where, name, count, script, *extra, ends_at=None):
            if name == 'save':
                (where / 'quick.rrstate').write_bytes(self.STATE)
            else:
                (where / 'load.csv').write_text('\n'.join(rows) + '\n', encoding='ascii')
            return {}

        seen = []

        def spawn(command, **_):
            path = Path(command[command.index('--load-state') + 1])
            seen.append(path.name)
            if path.name in rewrites:
                path.write_bytes(b'rewritten')
            if creates_missing and path.name == 'missing.rrstate':
                path.write_bytes(b'')
            return mock.Mock(returncode=0 if path.name in accepts else 4)

        with mock.patch.object(pce_conversion, 'run', run), \
                mock.patch('retrorecomp.conversion_common.spawn', spawn), \
                mock.patch('retrorecomp.conversion_gates.continuation_difference', return_value=None):
            result = pce_conversion.check_states(Path('game.exe'), folder, 'play', frames, Path('s.txt'), expected)
        return result, seen

    def test_every_damaged_state_and_a_missing_one_are_tried(self):
        result, seen = self.check()
        damaged = pce_conversion.damaged_states(self.STATE)
        self.assertEqual({f'invalid-{name}.rrstate' for name in damaged} | {'missing.rrstate'}, set(seen))
        self.assertEqual(sorted(damaged), result['damaged_states_refused'])
        self.assertTrue(result['truncated_state_rejected'])
        self.assertTrue(result['missing_state_creates_nothing'])
        self.assertEqual(len(self.STATE), result['state_bytes'])

    def test_each_case_really_is_damaged(self):
        for name, data in pce_conversion.damaged_states(self.STATE).items():
            with self.subTest(name):
                self.assertNotEqual(self.STATE, data)

    def test_a_damaged_state_that_is_accepted_stops_the_conversion(self):
        for name in pce_conversion.damaged_states(self.STATE):
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                self.root = Path(folder)
                with self.assertRaisesRegex(ConversionError, name):
                    self.check(accepts={f'invalid-{name}.rrstate'})

    def test_a_refused_state_that_is_rewritten_stops_the_conversion(self):
        with self.assertRaisesRegex(ConversionError, 'rewrote'):
            self.check(rewrites={'invalid-payload.rrstate'})

    def test_a_missing_state_that_is_accepted_or_created_stops_the_conversion(self):
        with self.assertRaisesRegex(ConversionError, 'accepted a missing'):
            self.check(accepts={'missing.rrstate'})
        with tempfile.TemporaryDirectory() as folder:
            self.root = Path(folder)
            with self.assertRaisesRegex(ConversionError, 'created a file'):
                self.check(creates_missing=True)


class StateConfigTests(TempFiles):
    def config(self, title='Synthetic Game'):
        return pce_build.state_config(read_hucard(self.write(card(16))), title)

    def value(self, text, key):
        return re.search(rf'^#define {key} (.+)$', text, re.M).group(1)

    def test_the_defines(self):
        found = read_hucard(self.write(card(16)))
        text = pce_build.state_config(found, 'Synthetic Game')
        self.assertTrue(text.startswith('#pragma once\n'))
        self.assertTrue(text.endswith('\n'))
        self.assertEqual('5', self.value(text, 'RR16_STATE_SYSTEM'))
        self.assertEqual('0', self.value(text, 'RR16_STATE_PAL'))
        self.assertEqual(json.dumps(found.sha256), self.value(text, 'RR16_STATE_ROM'))
        self.assertEqual(found.sha256, json.loads(self.value(text, 'RR16_STATE_ROM')))
        abi = json.loads(self.value(text, 'RR16_STATE_ABI'))
        self.assertRegex(abi, r'^[0-9a-f]{64}$')
        name = json.loads(self.value(text, 'RR16_STATE_NAME'))
        self.assertTrue(name and name.isprintable())
        self.assertIn('Synthetic', name)

    def test_the_system_number_is_the_modules(self):
        self.assertEqual(5, pce_build.STATE_SYSTEM)

    def test_the_abi_follows_the_engine_revision(self):
        before = self.value(self.config(), 'RR16_STATE_ABI')
        self.assertEqual(before, self.value(self.config(), 'RR16_STATE_ABI'))
        with mock.patch.object(pce_conversion, 'ENGINE_REV', '0' * 40):
            after = self.value(self.config(), 'RR16_STATE_ABI')
        self.assertNotEqual(before, after)
        self.assertRegex(json.loads(after), r'^[0-9a-f]{64}$')
        self.assertEqual(before, self.value(self.config(), 'RR16_STATE_ABI'))     # the patch is gone

    def test_the_rom_follows_the_card_and_the_name_the_title(self):
        one = pce_build.state_config(read_hucard(self.write(card(16), 'a.pce')), 'First')
        two = pce_build.state_config(read_hucard(self.write(card(8), 'b.pce')), 'Second')
        self.assertNotEqual(self.value(one, 'RR16_STATE_ROM'), self.value(two, 'RR16_STATE_ROM'))
        self.assertNotEqual(self.value(one, 'RR16_STATE_NAME'), self.value(two, 'RR16_STATE_NAME'))
        self.assertEqual(self.value(one, 'RR16_STATE_ABI'), self.value(two, 'RR16_STATE_ABI'))

    def test_no_other_machine_uses_number_5(self):
        sources = Path(pce_build.__file__).parent
        numbers = {}
        for path in sorted(sources.rglob('*.py')):
            for line in path.read_text(encoding='utf-8').splitlines():
                if 'RR16_STATE_SYSTEM' not in line:
                    continue
                found = re.findall(r'RR16_STATE_SYSTEM (\d+)', line)
                if '{STATE_SYSTEM}' in line:   # pce_build.py and psx_build.py name their constant
                    found = [pce_build.STATE_SYSTEM if path.name == 'pce_build.py' else psx_build.STATE_SYSTEM]
                elif not found:                # console16_state.py picks it from the machine: '1' if md else '2'
                    found = re.findall(r"'(\d+)'", line)
                numbers.setdefault(path.name, set()).update(int(number) for number in found)
        self.assertEqual({'console16_state.py': {1, 2}, 'neogeo_build.py': {3}, 'cps1_build.py': {4},
                          'pce_build.py': {5}, 'psx_build.py': {6}}, numbers)
        everything = [number for found in numbers.values() for number in sorted(found)]
        self.assertEqual(len(everything), len(set(everything)))     # one number per machine


class GameCmakeTests(TempFiles):
    def test_without_a_module_the_engine_provides_none(self):
        text = pce_build.game_cmake(None, '1.2.3')
        engine = pce_build.checkout_path().as_posix()
        self.assertIn(f'pce_add_native_module(PCE_MODULE MODULE "{engine}/runtime/src/no_module.cpp")', text)
        self.assertNotIn('MANIFEST', text)

    def test_with_a_module_folder_the_module_and_its_manifest_are_named(self):
        module = self.root / 'module-1'
        text = pce_build.game_cmake(module, '1.2.3')
        self.assertIn(f'MODULE "{(module / "module.cpp").as_posix()}" MANIFEST "{(module / "module.json").as_posix()}"',
                      text)
        self.assertNotIn('no_module.cpp', text)

    def test_what_every_game_project_has(self):
        for module in (None, self.root / 'module-1'):
            text = pce_build.game_cmake(module, '1.2.3')
            engine = pce_build.checkout_path().as_posix()
            with self.subTest(module=module):
                self.assertIn(f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)', text)
                self.assertIn('target_link_libraries(game PRIVATE pce-runtime SDL2::SDL2-static)', text)
                self.assertIn('$<TARGET_OBJECTS:pce_module>', text)
                self.assertNotIn('TARGET_OBJECTS:${PCE_MODULE}', text)      # the engine's 75-character target is never built
                self.assertIn('get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)', text)
                self.assertLess(text.index('pce_add_native_module'), text.index('add_library(pce_module OBJECT'))
                self.assertLess(text.index('add_library(pce_module OBJECT'), text.index('add_executable(game'))
                self.assertIn('RR_RECOMP_VERSION="1.2.3"', text)
                self.assertTrue(text.endswith('\n'))
                self.assertLess(text.index('add_subdirectory'), text.index('pce_add_native_module'))
                self.assertLess(text.index('pce_add_native_module'), text.index('add_executable(game'))

    def test_the_sources_of_the_game_executable_are_in_one_statement(self):
        text = pce_build.game_cmake(None, '1.0')
        statement = text[text.index('add_executable(game'):]
        statement = statement[:statement.index(')\n') + 1]
        for name in ('pce_main.c', 'pce_machine.cpp', 'pce_backup.c', 'console16_state.c', *hostkit.sources('pce'),
                     '$<TARGET_OBJECTS:pce_module>'):
            self.assertIn(name, statement)

    def test_the_kit_has_the_shell_and_the_adapter(self):
        kit = hostkit.sources('pce')
        self.assertIn('hostkit/adapters/rrhk_pce.c', kit)
        self.assertTrue(all(name.endswith('.c') for name in kit))
        self.assertEqual(len(kit), len(set(kit)))


class ProfileWiringTests(unittest.TestCase):
    def test_the_quick_state_family_and_the_adapter(self):
        profile = get_profile('pce')
        self.assertEqual('rr16', profile.quick_state_family)
        self.assertEqual('adapters/rrhk_pce.c', profile.host_adapter)
        self.assertEqual('adapters/rrhk_pce.c', hostkit.ADAPTERS['pce'])
        from retrorecomp.paths import ASSETS
        self.assertTrue((ASSETS / 'native/hostkit' / profile.host_adapter).is_file())

    def test_the_compilation_inputs_of_the_machine(self):
        names = compilation_inputs.manifest_names('pce')
        for name in ('native/pce_main.c', 'native/pce_machine.cpp', 'native/pce_machine.h', 'native/pce_backup.c',
                     'native/pce_backup.h', 'retrorecomp.pce_build',
                     'retrorecomp.pce_conversion', 'retrorecomp.pce_rom'):
            with self.subTest(name):
                self.assertIn(name, names)
        # Native files are listed by their path below the repository root: the adapter below native/hostkit.
        self.assertIn('native/hostkit/adapters/rrhk_pce.c', names)
        self.assertIn(f'native/hostkit/{hostkit.ADAPTERS["pce"]}', names)

    def test_every_listed_native_input_exists(self):
        from retrorecomp.paths import ASSETS
        for name in compilation_inputs.manifest_names('pce'):
            if not name.startswith('retrorecomp'):
                with self.subTest(name):
                    self.assertTrue((ASSETS / name).is_file())


class StartChoiceTests(unittest.TestCase):
    def variant(self, last, divergence, reach=0):
        return {'liveness': {'last_picture_change_frame': last, 'picture_changes': 100, 'audible_frames': 0},
                'divergence': divergence, 'reach': reach}

    def test_bonks_adventure_of_5_november(self):
        # One press: the demo went on, no picture differs from the route without input. Three: the third pressed
        # pause at frame 720. Two: alive to the end and the input changed 3,118 pictures.
        variants = {1: self.variant(3600, 0), 2: self.variant(3597, 3118, 40), 3: self.variant(721, 3118, 40)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 2)

    def test_the_walk_that_reached_the_most_pictures_wins_over_the_input_that_changed_the_most(self):
        # Military Madness: one press leaves the continue screen (the input changes pictures there), three reach the map.
        variants = {1: self.variant(3600, 3300, 30), 3: self.variant(3600, 2900, 400), 4: self.variant(3600, 3000, 120)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 3)

    def test_a_variant_that_paused_is_never_chosen_for_its_reach(self):
        variants = {1: self.variant(3600, 10, 5), 2: self.variant(721, 3000, 900)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 1)

    def test_a_tie_keeps_the_fewest_presses(self):
        variants = {1: self.variant(3600, 50, 9), 2: self.variant(3600, 50, 9), 3: self.variant(3600, 50, 9)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 1)

    def test_when_none_stays_alive_the_livelier_is_kept(self):
        variants = {1: self.variant(900, 0), 2: self.variant(1500, 0), 3: self.variant(721, 10)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 2)

    def test_reach_counts_the_pictures_of_the_quiet_walk_that_no_input_never_showed(self):
        with tempfile.TemporaryDirectory() as folder:
            base, walk = Path(folder) / 'base.csv', Path(folder) / 'walk.csv'
            write_trace(base, [(n, 'c', 'r', 'a' if n < 1500 else 'b', 's', 735) for n in range(0, 3000)])
            start, quiet = 1000, pce_conversion.QUIET_WALK
            rows = []
            for n in range(0, 3000):
                if n < start:
                    image = 'a'
                elif n < start + quiet:
                    image = f'x{n // 100}' if n % 2 else 'a'          # ten novel pictures, and the demo's own
                else:
                    image = f'late{n}'                                # beyond the window: not counted
                rows.append((n, 'c', 'r', image, 's', 735))
            write_trace(walk, rows)
            self.assertEqual(pce_conversion.QUIET_WALK // 100, pce_conversion.reach(walk, base, start))
            self.assertEqual(0, pce_conversion.reach(base, base, start))

    def test_divergence_counts_pictures_only(self):
        with tempfile.TemporaryDirectory() as folder:
            head = 'frame,cpu,ram,image,pcm,samples\n'
            base, other = Path(folder) / 'base.csv', Path(folder) / 'other.csv'
            base.write_text(head + '1,a,r1,p1,s,0\n2,a,r2,p2,s,0\n', encoding='ascii')
            other.write_text(head + '1,b,x1,p1,s,0\n2,b,x2,q2,s,0\n', encoding='ascii')
            self.assertEqual(pce_conversion.divergence(other, base), 1)

    def test_the_presses_set_the_start_of_play_and_long_routes(self):
        for presses in pce_conversion.START_PRESSES:
            plan = pce_conversion.routes('ab' * 32, frames=3600, level='thorough', presses=presses)
            for name, _, text in plan:
                if name == 'attract':
                    continue
                pressed, down, held = [], [], False
                for line in text.splitlines():
                    frame, p1, _ = line.split()
                    now = bool(int(p1, 16) & pce_conversion.RUN)
                    if now and not held:
                        down.append(int(frame))
                    held = now
                self.assertEqual([240 * k for k in range(1, presses + 1)], down[:presses], name)
                self.assertTrue(all(frame >= pce_conversion.walk_start(presses) for frame in down[presses:]), name)



class RouteRepairTests(unittest.TestCase):
    """The walk's Run pairs can leave a game's pause on: one more press where the picture stands still, kept when the game answers."""
    FRAMES, SEED, PRESSES = 6000, 12345, 2

    def trace(self, folder, name, pictures):
        path = folder / f'{name}.csv'
        path.write_text('frame,cpu,ram,image,pcm,samples\n' + ''.join(f'{n},c,r,{value},p,0\n' for n, value in enumerate(pictures)), encoding='ascii', newline='\n')
        return {'trace': path}

    def pairs(self, rows=None):
        rows = rows or pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES)
        pressed = [row[0] for row in rows if row[1] & pce_conversion.RUN]
        return [frame for frame in pressed if frame + pce_conversion.PAIR_GAP in pressed]

    def still_from(self, frame):
        return [str(n) if n < frame else 'still' for n in range(self.FRAMES)]

    def test_a_route_with_no_repair_is_the_walk_of_before(self):
        rows = pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES)
        self.assertEqual(rows, pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES, ()))
        identity = 'ab' * 32
        self.assertEqual(pce_conversion.routes(identity, frames=3600, level='extended', presses=2),
                         pce_conversion.routes(identity, frames=3600, level='extended', presses=2, repairs={}))

    def test_a_repair_adds_one_press_and_keeps_the_rest_of_the_route(self):
        plain = pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES)
        press = self.pairs(plain)[0] + 300
        rows = pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES, [press])
        self.assertEqual([row[0] for row in rows], sorted(row[0] for row in rows))
        self.assertIn((press, pce_conversion.RUN, 0), rows)
        outside = lambda row: not press <= row[0] <= press + 6
        self.assertEqual([row for row in rows if outside(row)], [row for row in plain if outside(row)])

    def test_a_moving_picture_is_not_stuck_and_a_still_one_is(self):
        rows = pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES)
        self.assertIsNone(pce_conversion.stuck_stretch([str(n) for n in range(self.FRAMES)], rows))
        first = self.pairs(rows)[0]
        start, end = pce_conversion.stuck_stretch(self.still_from(first), rows)
        self.assertEqual(start, first + pce_conversion.PAIR_GAP + 6)
        self.assertGreater(end, start + pce_conversion.STUCK_FRAMES)

    def test_a_press_the_game_answers_is_kept_and_the_route_goes_on(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            first = self.pairs()[0]
            calls = []

            def play(name, frames, script):
                calls.append(name)
                return self.trace(folder, name, [str(n) for n in range(self.FRAMES)])
            repairs, result = pce_conversion.repair_route('long-1', self.FRAMES, self.SEED, self.PRESSES, folder,
                                                          self.trace(folder, 'long-1', self.still_from(first)), play, lambda text: None)
            self.assertEqual(repairs, [first + pce_conversion.PAIR_GAP + 6 + pce_conversion.REPAIR_DELAY])
            self.assertEqual(calls, ['long-1-repair1'])
            self.assertEqual(result['trace'].name, 'long-1-repair1.csv')

    def test_presses_that_get_no_answer_are_dropped_and_two_end_the_search(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            still = self.trace(folder, 'long-1', self.still_from(self.pairs()[0]))
            calls = []

            def play(name, frames, script):
                calls.append(name)
                return self.trace(folder, name, self.still_from(self.pairs()[0]))
            repairs, result = pce_conversion.repair_route('long-1', self.FRAMES, self.SEED, self.PRESSES, folder, still, play, lambda text: None)
            self.assertEqual(repairs, [])
            self.assertLessEqual(len(calls), pce_conversion.REPAIR_MISSES)
            self.assertEqual(result, still)

    def test_the_search_is_bounded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            calls = []
            rows = pce_conversion.play_rows(self.FRAMES, self.SEED, self.PRESSES)

            def play(name, frames, script):
                calls.append(name)
                # Each press wakes the game up to the next pair, where it stands still again.
                return self.trace(folder, name, self.still_from(self.pairs(rows)[min(len(calls), len(self.pairs(rows)) - 1)]))
            pce_conversion.repair_route('long-1', self.FRAMES, self.SEED, self.PRESSES, folder,
                                        self.trace(folder, 'long-1', self.still_from(self.pairs(rows)[0])), play, lambda text: None)
            self.assertLessEqual(len(calls), pce_conversion.REPAIR_ATTEMPTS)


if __name__ == '__main__':
    unittest.main()
