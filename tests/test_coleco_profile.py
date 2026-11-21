"""The ColecoVision profile, stage 1 (docs/COLECOVISION.md): identification, the cartridge reader, the BIOS check and the refusal to convert.

Every file is built here from synthetic bytes: no ROM, no dump, no BIOS."""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from retrorecomp import coleco_bios, coleco_rom, firmware_search
from retrorecomp.core import ConversionError
from retrorecomp.systems import ConsoleMismatchError, UnsupportedConsoleError, get_profile, profile_for_path
from retrorecomp.systems.coleco import COLECO, COLECO_MACHINE

KIB = 1024
TITLE, DIRECT = b'\x55\xAA', b'\xAA\x55'


def cartridge(size: int, header: bytes = TITLE, fill: int = 0xC3) -> bytes:
    """Synthetic bytes of the given size that begin with a header word (not a program: the reader never looks past it)."""
    return header + bytes((fill + i) & 0xFF for i in range(size - len(header)))


class ProfileTests(unittest.TestCase):
    def test_the_profile_states_what_stage_one_is(self):
        self.assertIs(get_profile('coleco'), COLECO)
        self.assertEqual((COLECO.name, COLECO.status, COLECO.developer_only, COLECO.linux),
                         ('ColecoVision', 'experimental', True, 'pending'))
        self.assertEqual((COLECO.extensions, COLECO.export_folder, COLECO.video_modes), (('.col',), 'ColecoVision', ('ntsc', 'pal')))
        self.assertEqual([(cpu.arch, cpu.role, cpu.unit) for cpu in COLECO.cpus], [('z80', 'main', 'cycles')])
        self.assertEqual((COLECO.firmware, [key.name for key in COLECO.option_keys], COLECO.netplay_session, COLECO.feedback_kinds),
                         (('bios',), ['coleco_bios'], False, frozenset()))
        self.assertEqual(COLECO.default_video_mode(Path('game.col')), 'ntsc')

    def test_the_machine_has_the_bios_and_the_cartridge_as_sources_and_the_nmi_pin(self):
        self.assertIs(COLECO.z80_machine, COLECO_MACHINE)
        self.assertEqual((COLECO_MACHINE.key, COLECO_MACHINE.m1_wait, COLECO_MACHINE.irq_sample, COLECO_MACHINE.generator_tag),
                         ('coleco', 0, 'instruction_end', '-cv'))
        self.assertTrue(COLECO_MACHINE.nmi and COLECO_MACHINE.step_begin and COLECO_MACHINE.reference_state)
        self.assertEqual((COLECO_MACHINE.regions.region_bits, COLECO_MACHINE.regions.sources), (13, ('cartridge', 'bios')))

    def test_it_reuses_the_chain_the_two_chips_and_the_gates_and_the_bios_is_the_players_not_ours(self):
        self.assertEqual(COLECO.stamp_groups, ('z80_main', 'z80_chain_glue', 'tms9918', 'sn76489', 'audio_box', 'z80_chain_state', 'state_file', 'hostkit_keypad', 'conversion_gates'))
        self.assertEqual(COLECO.notice_files, ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md'))
        self.assertEqual(COLECO.optional_notice_files, ())

    def test_the_path_section_is_the_machines_own_with_a_rom_and_a_bios(self):
        spec = COLECO.path_spec
        self.assertEqual((spec.sections, [name for name, _ in spec.source_bounds], spec.required_sources, spec.hashed_sources),
                         ((('z80', 'coleco'),), ['rom', 'bios'], ('rom',), ('rom', 'bios')))
        self.assertEqual(dict(spec.source_bounds), {'rom': (0x1000, 0x8000), 'bios': (0x2000, 0x2000)})


class ReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_every_size_from_4_to_32_kib_in_1_kib_steps_is_read_and_its_header_word_reported(self):
        for kib, header, kind in ((4, TITLE, 'title'), (8, DIRECT, 'direct'), (16, TITLE, 'title'), (24, DIRECT, 'direct'), (32, TITLE, 'title')):
            with self.subTest(kib=kib):
                data = cartridge(kib * KIB, header)
                read = coleco_rom.read_cartridge(self.write(f'game{kib}.col', data))
                self.assertEqual((read.size, read.data, read.sha256, read.member, read.header),
                                 (len(data), data, hashlib.sha256(data).hexdigest(), '', kind))

    def test_a_col_without_a_header_word_is_still_read_and_says_so(self):
        read = coleco_rom.read_cartridge(self.write('plain.col', cartridge(8 * KIB, b'\x00\x00')))
        self.assertEqual(read.header, '')

    def test_a_size_that_is_not_a_whole_number_of_kilobytes_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'whole number of kilobytes'):
            coleco_rom.read_cartridge(self.write('odd.col', cartridge(8 * KIB + 1)))

    def test_a_file_outside_4_to_32_kib_is_refused_with_its_reason(self):
        with self.assertRaisesRegex(ValueError, 'larger than 32 KiB.*MegaCart'):
            coleco_rom.read_cartridge(self.write('big.col', cartridge(33 * KIB)))
        with self.assertRaisesRegex(ValueError, 'smaller than 4 KiB'):
            coleco_rom.read_cartridge(self.write('small.col', cartridge(2 * KIB)))
        with self.assertRaisesRegex(ValueError, 'smaller than 4 KiB'):
            coleco_rom.read_cartridge(self.write('empty.col', b''))

    def test_a_bin_or_rom_needs_a_header_word_and_another_name_is_refused(self):
        data = cartridge(8 * KIB)
        for name in ('game.bin', 'game.rom', 'GAME.COL'):
            with self.subTest(name=name):
                self.assertEqual(coleco_rom.read_cartridge(self.write(name, data)).data, data)
        with self.assertRaisesRegex(ValueError, 'header word'):
            coleco_rom.read_cartridge(self.write('nohead.bin', cartridge(8 * KIB, b'\x00\x00')))
        with self.assertRaisesRegex(ValueError, 'not a ColecoVision cartridge name'):
            coleco_rom.read_cartridge(self.write('game.nes', data))

    def test_a_zip_holding_exactly_one_cartridge_is_read(self):
        data = cartridge(32 * KIB, DIRECT)
        path = self.folder / 'game.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('Some Game (USA).col', data)
            bundle.writestr('readme.txt', b'not a cartridge')
        read = coleco_rom.read_cartridge(path)
        self.assertEqual((read.data, read.member), (data, 'Some Game (USA).col'))

    def test_a_zip_with_none_or_two_cartridges_or_a_bad_size_or_damaged_or_a_headerless_bin_is_refused(self):
        for name, members, message in (('none.zip', {'readme.txt': b'x'}, 'exactly one'),
                                       ('two.zip', {'a.col': cartridge(4 * KIB), 'b.col': cartridge(4 * KIB)}, 'exactly one'),
                                       ('big.zip', {'a.col': cartridge(64 * KIB)}, 'larger than 32 KiB'),
                                       ('nohead.zip', {'a.bin': cartridge(8 * KIB, b'\x01\x02')}, 'header word')):
            path = self.folder / name
            with zipfile.ZipFile(path, 'w') as bundle:
                for member, data in members.items():
                    bundle.writestr(member, data)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                coleco_rom.read_cartridge(path)
        with self.assertRaisesRegex(ValueError, 'not a readable ZIP'):
            coleco_rom.read_cartridge(self.write('broken.zip', b'PK\x03\x04 not a zip'))


class IdentificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def make(self, folder: str, name: str, data: bytes) -> Path:
        directory = self.root / folder
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_bytes(data)
        return path

    def zipped(self, folder: str, name: str, members: dict) -> Path:
        directory = self.root / folder
        directory.mkdir(exist_ok=True)
        path = directory / name
        with zipfile.ZipFile(path, 'w') as bundle:
            for member, data in members.items():
                bundle.writestr(member, data)
        return path

    def test_a_col_file_is_the_colecovision_whatever_its_folder_and_its_bytes(self):
        path = self.make('roms', 'game.col', cartridge(32 * KIB))
        self.assertIs(profile_for_path(path), COLECO)
        self.assertIs(profile_for_path(path, 'coleco'), COLECO)
        self.assertIs(profile_for_path(self.make('roms', 'blank.col', bytes(8 * KIB))), COLECO)

    def test_a_col_file_with_another_console_chosen_is_a_mismatch(self):
        path = self.make('roms', 'game.col', cartridge(32 * KIB))
        with self.assertRaises(ConsoleMismatchError) as caught:
            profile_for_path(path, 'sms')
        self.assertEqual(caught.exception.detected_system, 'coleco')

    def test_a_zip_holding_one_col_is_the_colecovisions_whatever_its_folder(self):
        path = self.zipped('roms', 'game.zip', {'game.col': cartridge(16 * KIB)})
        self.assertIs(profile_for_path(path), COLECO)

    def test_a_bin_or_rom_is_the_colecovisions_only_when_chosen_or_in_a_colecovision_folder_and_with_a_header_word(self):
        data = cartridge(16 * KIB)
        for folder in ('colecovision', 'ColecoVision', 'coleco', 'coleco vision'):
            for name in ('game.bin', 'game.rom'):
                with self.subTest(folder=folder, name=name):
                    self.assertIs(profile_for_path(self.make(folder, name, data)), COLECO)
        elsewhere = self.make('elsewhere', 'game.bin', data)
        self.assertIs(profile_for_path(elsewhere, 'coleco'), COLECO)           # the player's choice
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(elsewhere)                                          # no hint: nobody's, as before
        self.assertIs(profile_for_path(self.zipped('colecovision', 'two.zip', {'game.bin': data})), COLECO)
        headerless = self.make('colecovision', 'nohead.bin', cartridge(16 * KIB, b'\x00\x01'))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(headerless)

    def test_a_bin_in_a_colecovision_folder_that_is_not_a_cartridge_size_is_left_alone(self):
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(self.make('colecovision', 'odd.bin', cartridge(16 * KIB + 3)))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(self.make('colecovision', 'big.bin', cartridge(64 * KIB)))

    def test_the_colecovision_steals_no_file_of_another_machine(self):
        for name, selected in (('game.bin', 'sms'), ('game.rom', 'msx')):
            path = self.make('colecovision', name, cartridge(16 * KIB))
            self.assertIsNone(COLECO.identify_path(path, path.suffix, selected))
        other = self.root / 'plain.nes'
        other.write_bytes(b'NES\x1a' + bytes(60))
        self.assertIsNone(COLECO.identify_path(other, '.nes', None))
        self.assertEqual(profile_for_path(other).id, 'nes')

    def test_a_zip_of_an_other_machine_is_not_opened_as_a_cartridge(self):
        path = self.zipped('colecovision', 'other.zip', {'game.gb': cartridge(32 * KIB)})
        self.assertIsNone(COLECO.identify_path(path, '.zip', None))


class BiosTests(unittest.TestCase):
    """The BIOS check is by content: the digest is the only thing accepted, so the test stands one in for the real image."""
    IMAGE = bytes((i * 7 + 3) & 0xFF for i in range(coleco_bios.BIOS_BYTES))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        known = {hashlib.sha256(self.IMAGE).hexdigest(): 'ColecoVision BIOS (OS7)'}
        patch = mock.patch.object(coleco_bios, 'KNOWN', known)
        patch.start()
        self.addCleanup(patch.stop)

    def file(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_the_image_the_converter_knows_is_accepted_and_nothing_else(self):
        path = self.file('coleco.rom', self.IMAGE)
        self.assertEqual(coleco_bios.own_bios(str(path)), (self.IMAGE, hashlib.sha256(self.IMAGE).hexdigest()))
        self.assertEqual(coleco_bios.identify(path), ('ColecoVision BIOS (OS7)', hashlib.sha256(self.IMAGE).hexdigest()))
        with self.assertRaisesRegex(ValueError, 'not the ColecoVision BIOS'):
            coleco_bios.own_bios(str(self.file('other.rom', self.IMAGE[:-1] + b'\x00')))
        with self.assertRaisesRegex(ValueError, 'not the ColecoVision BIOS'):
            coleco_bios.own_bios(str(self.file('short.rom', self.IMAGE[:4096])))
        self.assertIsNone(coleco_bios.identify(self.file('other2.rom', bytes(coleco_bios.BIOS_BYTES))))

    def test_no_bios_is_a_sentence_that_says_where_to_choose_it(self):
        with self.assertRaisesRegex(ValueError, 'choose your own copy in Options'):
            coleco_bios.own_bios(None)
        with self.assertRaisesRegex(ValueError, 'cannot be read'):
            coleco_bios.own_bios(str(self.folder / 'missing.rom'))

    def test_the_request_carries_the_bios_digest_or_missing_and_never_its_path(self):
        path = self.file('coleco.rom', self.IMAGE)
        settings = {}
        COLECO.request_identity(None, {'coleco_bios': str(path)}, settings)
        self.assertEqual(settings, {'coleco_bios': hashlib.sha256(self.IMAGE).hexdigest()})
        settings = {}
        COLECO.request_identity(None, {}, settings)
        self.assertEqual(settings, {'coleco_bios': 'missing'})

    def test_the_firmware_search_finds_it_by_content_in_any_folder(self):
        self.file('anything.bin', self.IMAGE)
        self.file('decoy.bin', bytes(coleco_bios.BIOS_BYTES))
        recogniser = firmware_search.RECOGNISERS['coleco_bios']
        hits = [hit for path in sorted(self.folder.iterdir()) if recogniser.check.accepts(path.stat().st_size, path.suffix)
                for hit in recogniser.check.identify(path)]
        self.assertEqual([(hit[0], hit[1]) for hit in hits], [('coleco_bios', 'ColecoVision BIOS (OS7)')])



class RealDigestTests(unittest.TestCase):
    def test_the_one_image_the_converter_knows_is_a_digest_never_bytes(self):
        self.assertEqual(coleco_bios.BIOS_BYTES, 8192)
        self.assertEqual(list(coleco_bios.KNOWN.values()), ['ColecoVision BIOS (OS7)'])
        for digest in coleco_bios.KNOWN:
            self.assertRegex(digest, '^[0-9a-f]{64}$')


class ConversionTests(unittest.TestCase):
    def test_the_profile_converts_through_the_machines_own_conversion_and_refuses_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as folder:
            big = Path(folder) / 'big.col'
            big.write_bytes(cartridge(64 * KIB))                              # no board it can hold: refused before anything is written
            with self.assertRaisesRegex(ConversionError, 'larger than 32 KiB'):
                COLECO.convert(big, frames=3600, emit=print)
            path = Path(folder) / 'game.col'
            path.write_bytes(cartridge(16 * KIB))
            with self.assertRaisesRegex(ConversionError, 'choose your own copy in Options'):    # no BIOS: said before anything is built
                COLECO.convert(path, frames=3600, emit=print)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['big.col', 'game.col'])


if __name__ == '__main__':
    unittest.main()
