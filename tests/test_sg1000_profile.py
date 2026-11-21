"""The SG-1000 profile, stage 1 (docs/SG1000.md): identification, the cartridge reader and the refusal to convert.

Every file is built here from synthetic bytes: no ROM, no dump."""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from retrorecomp import sg1000_conversion, sg1000_rom
from retrorecomp.core import ConversionError
from retrorecomp.systems import ConsoleMismatchError, UnsupportedConsoleError, get_profile, profile_for_path
from retrorecomp.systems.sg1000 import SG1000, SG1000_MACHINE

KIB = 1024


def cartridge(size: int, fill: int = 0xC3) -> bytes:
    """Synthetic bytes of the given size (not a program: the reader never looks inside)."""
    return bytes((fill + i) & 0xFF for i in range(size))


class ProfileTests(unittest.TestCase):
    def test_the_profile_states_what_stage_one_is(self):
        self.assertIs(get_profile('sg1000'), SG1000)
        self.assertEqual((SG1000.name, SG1000.status, SG1000.developer_only, SG1000.linux),
                         ('SG-1000', 'experimental', True, 'pending'))
        self.assertEqual((SG1000.extensions, SG1000.export_folder, SG1000.video_modes), (('.sg',), 'SG-1000', ('ntsc', 'pal')))
        self.assertEqual([(cpu.arch, cpu.role, cpu.unit) for cpu in SG1000.cpus], [('z80', 'main', 'cycles')])
        self.assertEqual((SG1000.firmware, SG1000.option_keys, SG1000.netplay_session, SG1000.feedback_kinds),
                         ((), (), False, frozenset()))
        self.assertEqual(SG1000.default_video_mode(Path('game.sg')), 'ntsc')

    def test_the_machine_is_the_one_the_lead_described(self):
        self.assertIs(SG1000.z80_machine, SG1000_MACHINE)
        self.assertEqual((SG1000_MACHINE.key, SG1000_MACHINE.m1_wait, SG1000_MACHINE.irq_sample, SG1000_MACHINE.generator_tag),
                         ('sg1000', 0, 'instruction_end', '-sg'))
        self.assertTrue(SG1000_MACHINE.nmi and SG1000_MACHINE.step_begin and SG1000_MACHINE.reference_state)
        self.assertEqual((SG1000_MACHINE.regions.region_bits, SG1000_MACHINE.regions.sources), (13, ('cartridge',)))

    def test_it_reuses_the_chain_the_video_chip_and_the_gates_and_no_bios(self):
        self.assertEqual(SG1000.stamp_groups, ('z80_main', 'z80_chain_glue', 'tms9918', 'sn76489', 'audio_box', 'z80_chain_state', 'state_file', 'conversion_gates'))
        self.assertEqual(SG1000.notice_files, ('licenses/smsggrecomp.md', 'licenses/z80-recomp-core.md', 'licenses/superzazu-z80.md'))
        self.assertEqual(SG1000.optional_notice_files, ())


class ReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_every_size_from_2_to_48_kib_in_1_kib_steps_is_read(self):
        for kib in (2, 8, 16, 24, 32, 40, 47, 48):
            with self.subTest(kib=kib):
                data = cartridge(kib * KIB)
                read = sg1000_rom.read_cartridge(self.write(f'game{kib}.sg', data))
                self.assertEqual((read.size, read.data, read.sha256, read.member), (len(data), data, hashlib.sha256(data).hexdigest(), ''))

    def test_a_size_that_is_not_a_whole_number_of_kilobytes_is_refused(self):
        for size in (2 * KIB + 1, 16 * KIB + 512):         # 16 KiB + 512: a copier header is not removed, so the file is refused
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'whole number of kilobytes'):
                sg1000_rom.read_cartridge(self.write('odd.sg', cartridge(size)))

    def test_a_file_outside_2_to_48_kib_is_refused_with_its_reason(self):
        with self.assertRaisesRegex(ValueError, 'larger than 48 KiB.*bank-switched'):
            sg1000_rom.read_cartridge(self.write('big.sg', cartridge(49 * KIB)))
        with self.assertRaisesRegex(ValueError, 'smaller than 2 KiB'):
            sg1000_rom.read_cartridge(self.write('small.sg', cartridge(1 * KIB)))
        with self.assertRaisesRegex(ValueError, 'smaller than 2 KiB'):
            sg1000_rom.read_cartridge(self.write('empty.sg', b''))

    def test_a_bin_and_a_rom_are_read_and_another_name_is_refused(self):
        data = cartridge(8 * KIB)
        for name in ('game.bin', 'game.rom', 'GAME.SG'):
            with self.subTest(name=name):
                self.assertEqual(sg1000_rom.read_cartridge(self.write(name, data)).data, data)
        with self.assertRaisesRegex(ValueError, 'not an SG-1000 cartridge name'):
            sg1000_rom.read_cartridge(self.write('game.nes', data))

    def test_a_zip_holding_exactly_one_cartridge_is_read(self):
        data = cartridge(32 * KIB)
        path = self.folder / 'game.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('Some Game (Japan).sg', data)
            bundle.writestr('readme.txt', b'not a cartridge')
        read = sg1000_rom.read_cartridge(path)
        self.assertEqual((read.data, read.member), (data, 'Some Game (Japan).sg'))

    def test_a_zip_with_none_or_two_cartridges_or_a_bad_size_or_damaged_is_refused(self):
        for name, members, message in (('none.zip', {'readme.txt': b'x'}, 'exactly one'),
                                       ('two.zip', {'a.sg': cartridge(2 * KIB), 'b.sg': cartridge(2 * KIB)}, 'exactly one'),
                                       ('big.zip', {'a.sg': cartridge(64 * KIB)}, 'larger than 48 KiB')):
            path = self.folder / name
            with zipfile.ZipFile(path, 'w') as bundle:
                for member, data in members.items():
                    bundle.writestr(member, data)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                sg1000_rom.read_cartridge(path)
        with self.assertRaisesRegex(ValueError, 'not a readable ZIP'):
            sg1000_rom.read_cartridge(self.write('broken.zip', b'PK\x03\x04 not a zip'))


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

    def test_a_sg_file_is_the_sg_1000_whatever_its_folder_and_its_bytes(self):
        path = self.make('roms', 'game.sg', cartridge(32 * KIB))
        self.assertIs(profile_for_path(path), SG1000)
        self.assertIs(profile_for_path(path, 'sg1000'), SG1000)

    def test_a_sg_file_with_another_console_chosen_is_a_mismatch(self):
        path = self.make('roms', 'game.sg', cartridge(32 * KIB))
        with self.assertRaises(ConsoleMismatchError) as caught:
            profile_for_path(path, 'sms')
        self.assertEqual(caught.exception.detected_system, 'sg1000')

    def test_a_zip_holding_one_sg_is_the_sg_1000s_whatever_its_folder(self):
        path = self.zipped('roms', 'game.zip', {'game.sg': cartridge(16 * KIB)})
        self.assertIs(profile_for_path(path), SG1000)

    def test_a_bin_or_rom_is_the_sg_1000s_only_when_chosen_or_in_an_sg1000_folder(self):
        data = cartridge(16 * KIB)
        for folder in ('sg1000', 'SG-1000', 'sg_1000'):
            for name in ('game.bin', 'game.rom'):
                with self.subTest(folder=folder, name=name):
                    self.assertIs(profile_for_path(self.make(folder, name, data)), SG1000)
        elsewhere = self.make('elsewhere', 'game.bin', data)
        self.assertIs(profile_for_path(elsewhere, 'sg1000'), SG1000)           # the player's choice
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(elsewhere)                                          # no hint: nobody's, as before
        self.assertIs(profile_for_path(self.zipped('sg1000', 'two.zip', {'game.bin': data})), SG1000)

    def test_a_bin_in_an_sg1000_folder_that_is_not_a_cartridge_size_is_left_alone(self):
        path = self.make('sg1000', 'odd.bin', cartridge(16 * KIB + 3))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(path)
        big = self.make('sg1000', 'big.bin', cartridge(64 * KIB))
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(big)

    def test_the_sg_1000_steals_no_file_of_another_machine(self):
        for name, selected in (('game.bin', 'sms'), ('game.rom', 'msx')):
            path = self.make('sg1000', name, cartridge(16 * KIB))
            self.assertIsNone(SG1000.identify_path(path, path.suffix, selected))
        other = self.root / 'plain.nes'
        other.write_bytes(b'NES\x1a' + bytes(60))
        self.assertIsNone(SG1000.identify_path(other, '.nes', None))
        self.assertEqual(profile_for_path(other).id, 'nes')

    def test_a_zip_of_an_other_machine_is_not_opened_as_a_cartridge(self):
        path = self.zipped('sg1000', 'other.zip', {'game.gb': cartridge(32 * KIB)})
        self.assertIsNone(SG1000.identify_path(path, '.zip', None))


class ConversionTests(unittest.TestCase):
    def test_the_profile_converts_through_the_machines_own_conversion(self):
        self.assertFalse(hasattr(sg1000_conversion, 'NOT_YET'))              # stage 2: the refusal of stage 1 is gone
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'game.sg'
            path.write_bytes(cartridge(64 * KIB))                            # no board it can hold: refused before anything is written
            with self.assertRaisesRegex(ConversionError, 'larger than 48 KiB'):
                SG1000.convert(path, frames=3600, emit=print)
            self.assertEqual([p.name for p in Path(folder).iterdir()], ['game.sg'])


if __name__ == '__main__':
    unittest.main()
