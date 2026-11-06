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

    def test_run_is_pressed_at_240_480_and_720_of_play(self):
        for frames in (600, 3600):
            plan = {name: text for name, _, text in pce_conversion.routes(IDENTITY, frames=frames, level='standard')}
            with self.subTest(frames=frames):
                pressed = [row[0] for row in parse_script(plan['play']) if row[1] & pce_conversion.RUN]
                self.assertEqual([240, 480, 720], pressed)
                rows = {row[0]: row for row in parse_script(plan['play'])}
                for at in (240, 480, 720):
                    self.assertEqual((at, pce_conversion.RUN, 0), rows[at])
                    self.assertEqual((at + 6, 0, 0), rows[at + 6])      # released a few frames later

    def test_no_route_pushes_run_after_frame_900(self):
        for name, _, text in pce_conversion.routes(IDENTITY, frames=10000, level='thorough'):
            with self.subTest(name):
                late = [row for row in parse_script(text) if row[0] > 900 and (row[1] | row[2]) & pce_conversion.RUN]
                self.assertEqual([], late)

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
        for name in ('pce_main.c', 'pce_machine.cpp', 'console16_state.c', *hostkit.sources('pce'),
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
        for name in ('native/pce_main.c', 'native/pce_machine.cpp', 'native/pce_machine.h', 'retrorecomp.pce_build',
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
    def variant(self, last, divergence):
        return {'liveness': {'last_picture_change_frame': last, 'picture_changes': 100, 'audible_frames': 0},
                'divergence': divergence}

    def test_bonks_adventure_of_5_november(self):
        # One press: the demo went on, no picture differs from the route without input. Three: the third pressed
        # pause at frame 720. Two: alive to the end and the input changed 3,118 pictures.
        variants = {1: self.variant(3600, 0), 2: self.variant(3597, 3118), 3: self.variant(721, 3118)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 2)

    def test_a_tie_keeps_the_fewest_presses(self):
        variants = {1: self.variant(3600, 50), 2: self.variant(3600, 50), 3: self.variant(3600, 50)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 1)

    def test_when_none_stays_alive_the_livelier_is_kept(self):
        variants = {1: self.variant(900, 0), 2: self.variant(1500, 0), 3: self.variant(721, 10)}
        self.assertEqual(pce_conversion.choose_start(variants, 3600), 2)

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
                runs = [line for line in text.splitlines() if int(line.split()[1], 16) & pce_conversion.RUN]
                self.assertEqual(len(runs), presses, name)


if __name__ == '__main__':
    unittest.main()
