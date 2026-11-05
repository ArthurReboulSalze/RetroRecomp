"""The PC Engine (experimental, developer-only): HuCard reader, profile, identification report, paths, upstream.

Every HuCard image is built here from synthetic bytes (a reset vector and zeros) inside a temporary folder: no
ROM is read and nothing is written elsewhere. Nothing here reaches the user's preferences.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from retrorecomp import path_profiles, pce_conversion, report_schema, upstreams
from retrorecomp.core import ConversionError
from retrorecomp.pce_rom import (BANK, HEADER, SF2_BYTES, HuCard, PcEngineRomError, board_for, decode,
                                 read_hucard)
from retrorecomp.systems import (ALL_PROFILES, PROFILES, ROM_CANDIDATE_EXTENSIONS, UnsupportedConsoleError,
                                 get_profile, profile_for_path)
from retrorecomp.systems.registry import convertible_profiles

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
    def test_the_profile_is_experimental_developer_only_and_unavailable(self):
        profile = get_profile('pce')
        self.assertEqual('experimental', profile.status)
        self.assertTrue(profile.developer_only)
        self.assertFalse(profile.available())
        self.assertIn(profile, ALL_PROFILES)
        self.assertNotIn(profile, PROFILES)
        self.assertNotIn(profile, convertible_profiles())
        self.assertEqual(1, len(profile.cpus))
        cpu = profile.cpus[0]
        self.assertEqual(('huc6280', 'main', 'instructions'), (cpu.arch, cpu.role, cpu.unit))
        self.assertEqual(('ntsc',), profile.video_modes)
        self.assertEqual(('.pce',), profile.extensions)

    def test_a_pce_file_is_a_candidate_but_an_unknown_console(self):
        self.assertIn('.pce', ROM_CANDIDATE_EXTENSIONS)
        path = self.write(card(16))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(path)

    def test_read_rom_is_the_reader(self):
        path = self.write(card(16))
        self.assertEqual(read_hucard(path), get_profile('pce').read_rom(path))

    def test_convert_identifies_then_stops(self):
        profile = get_profile('pce')
        path = self.write(card(16))
        with self.assertRaises(ConversionError) as caught:
            profile.convert(path)
        self.assertEqual(pce_conversion.NOT_YET, str(caught.exception))
        with self.assertRaises(ConversionError):
            pce_conversion.convert(path)

    def test_a_file_that_is_not_a_hucard_fails_in_the_reader_first(self):
        profile = get_profile('pce')
        path = self.write(bytes(100), 'junk.pce')
        with self.assertRaises(PcEngineRomError):
            profile.convert(path)
        with self.assertRaises(PcEngineRomError):
            profile.read_rom(path)

    def test_the_default_video_mode_is_ntsc(self):
        self.assertEqual('ntsc', get_profile('pce').default_video_mode(self.write(card(8))))


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


if __name__ == '__main__':
    unittest.main()
