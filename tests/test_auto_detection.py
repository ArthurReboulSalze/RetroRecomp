"""Automatic console detection (the window's drop and `batch --system auto` share `systems.profile_for_path`).

Every file is authored here from the few header bytes a format needs: no ROM bytes, nothing from the player's library. The
audit of 27 November 2026 (.build/auto-detect-audit/REPORT.md) ran the same function over the owner's library; these cases pin
what it showed to be right and mark, with `expectedFailure`, the misdetections that are known and not fixed yet (each one
names the file whose edit moves a game stamp, so the change is the lead's decision).
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
import zipfile

from retrorecomp.rom_sources import disk_sets
from retrorecomp.systems import UnsupportedConsoleError, profile_for_path


def gb_header(flag: int, size: int = 0x8000) -> bytes:
    data = bytearray(size)
    data[0x134:0x13c] = b'AUTHORED'
    data[0x143] = flag
    checksum = 0
    for value in data[0x134:0x14d]:
        checksum = (checksum - value - 1) & 0xff
    data[0x14d] = checksum
    return bytes(data)


def sega_header(region: int) -> bytes:
    data = bytearray(0x8000)
    data[0x7ff0:0x7ff8] = b'TMR SEGA'
    data[0x7fff] = region << 4
    return bytes(data)


def msx_cartridge() -> bytes:
    data = bytearray(0x4000)
    data[0:2] = b'AB'
    data[2:4] = (0x4010).to_bytes(2, 'little')
    return bytes(data)


def coleco_cartridge() -> bytes:
    return b'\xaa\x55' + bytes(0x2000 - 2)


CPC_SIGNATURE = b'MV - CPCEMU Disk-File\r\nDisk-Info\r\n'


def cpc_disk() -> bytes:
    return CPC_SIGNATURE + bytes(0x100 - len(CPC_SIGNATURE)) + bytes(0x200)


def iso_volume(system_id: str) -> bytes:
    """An ISO 9660 primary volume descriptor with that system identifier, and nothing else."""
    return bytes(16 * 2048) + b'\x01CD001\x01\x00' + system_id.ljust(32).encode('ascii') + bytes(2048 * 4)


class AutoDetectionCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, relative: str, data: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def archive(self, relative: str, members: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as bundle:
            for name, data in members.items():
                bundle.writestr(name, data)
        return path

    def detect(self, path: Path, selected: str | None = None) -> str:
        return profile_for_path(path, selected).id

    def refused(self, path: Path) -> None:
        with self.assertRaises(UnsupportedConsoleError):
            profile_for_path(path, None)


class ContentWinsOverExtensionTests(AutoDetectionCase):
    def test_a_game_boy_file_with_the_color_flag_is_the_game_boy_color(self):
        self.assertEqual(self.detect(self.make('a/game.gb', gb_header(0xC0))), 'gbc')
        self.assertEqual(self.detect(self.archive('a/game.zip', {'game.gb': gb_header(0xC0)})), 'gbc')

    def test_a_dual_mode_or_monochrome_game_boy_cartridge_stays_a_game_boy(self):
        self.assertEqual(self.detect(self.make('a/dmg.gb', gb_header(0x00))), 'gb')
        self.assertEqual(self.detect(self.make('a/dual.gb', gb_header(0x80))), 'gb')

    def test_a_headerless_name_is_read_from_its_bytes(self):
        self.assertEqual(self.detect(self.make('x/one.bin', gb_header(0x00))), 'gb')
        self.assertEqual(self.detect(self.make('x/two.bin', gb_header(0xC0))), 'gbc')
        self.assertEqual(self.detect(self.make('x/three.bin', sega_header(4))), 'sms')
        self.assertEqual(self.detect(self.make('x/four.bin', sega_header(7))), 'gg')

    def test_the_master_system_and_the_game_gear_are_told_apart_by_the_region_nibble(self):
        self.assertEqual(self.detect(self.make('s/a.sms', sega_header(4))), 'sms')
        self.assertEqual(self.detect(self.make('s/b.sms', sega_header(6))), 'gg')
        self.assertEqual(self.detect(self.make('s/c.gg', sega_header(4))), 'sms')

    def test_an_msx_cartridge_is_found_by_its_header_and_its_folder_picks_the_generation(self):
        self.assertEqual(self.detect(self.make('any/a.rom', msx_cartridge())), 'msx')
        self.assertEqual(self.detect(self.make('msx2/b.rom', msx_cartridge())), 'msx2')
        self.assertEqual(self.detect(self.make('msx2+/c.rom', msx_cartridge())), 'msx2plus')


    def test_an_msx_game_with_text_over_its_header_fields_is_still_an_msx_cartridge(self):
        # Hydlide 3 spells its name over STATEMENT, DEVICE, TEXT and the reserved bytes: 76 of the 77 MSX1 games of the owner's
        # msx1 folder that a stricter sniff refused were of this kind.
        data = bytearray(msx_cartridge() * 2)
        data[4:16] = b'HYDLIDE3MSX2'
        self.assertEqual(self.detect(self.make('any/hydlide.rom', bytes(data))), 'msx')
        self.assertEqual(self.detect(self.archive('msx1/hydlide.zip', {'hydlide.rom': bytes(data)})), 'msx')


class FolderHintTests(AutoDetectionCase):
    """A cartridge with no header of its own is claimed by a folder name, never by its bytes alone."""

    def test_extensions_that_only_one_machine_uses_are_enough(self):
        self.assertEqual(self.detect(self.make('any/a.sg', bytes(0x8000))), 'sg1000')
        self.assertEqual(self.detect(self.make('any/b.col', coleco_cartridge())), 'coleco')
        self.assertEqual(self.detect(self.archive('any/c.zip', {'c.sg': bytes(0x8000)})), 'sg1000')
        self.assertEqual(self.detect(self.archive('any/d.zip', {'d.col': coleco_cartridge()})), 'coleco')

    def test_a_shared_name_needs_the_machine_folder(self):
        self.assertEqual(self.detect(self.make('sg1000/a.bin', bytes(0x8000))), 'sg1000')
        self.assertEqual(self.detect(self.make('colecovision/b.rom', coleco_cartridge())), 'coleco')
        self.refused(self.make('elsewhere/a.bin', bytes(0x8000)))
        self.refused(self.make('elsewhere/b.rom', coleco_cartridge()))

    def test_an_sc_3000_cartridge_is_not_taken_for_a_supported_machine(self):
        self.refused(self.make('mastersystem/game.sc', bytes(0x8000)))


class DiskTests(AutoDetectionCase):
    def test_a_cpcemu_signature_makes_a_dsk_an_amstrad_cpc_disk_whatever_its_folder(self):
        self.assertEqual(self.detect(self.make('msx2+/a.dsk', cpc_disk())), 'cpc')
        self.assertEqual(self.detect(self.make('any/b.dsk', b'EXTENDED CPC DSK File\r\nDisk-Info\r\n' + bytes(0x300))), 'cpc')
        self.assertEqual(self.detect(self.archive('any/c.zip', {'c.dsk': cpc_disk()})), 'cpc')

    def test_a_raw_dsk_without_signature_is_left_to_the_msx2_plus(self):
        self.assertEqual(self.detect(self.make('any/a.dsk', bytes(737280))), 'msx2plus')

    def test_the_disks_of_an_amstrad_cpc_game_are_never_grouped_into_an_msx_playlist(self):
        first = self.make('cpc/Game (Disk 1 of 2).dsk', cpc_disk())
        second = self.make('cpc/Game (Disk 2 of 2).dsk', cpc_disk())
        sets = disk_sets([first, second], self.root / 'datas')
        self.assertEqual(sets.grouped, 0)
        self.assertEqual(sets.paths, [first, second])
        self.assertEqual([self.detect(path) for path in sets.paths], ['cpc', 'cpc'])

    def test_the_disks_of_an_msx2_plus_game_are_still_grouped(self):
        first = self.make('msx/Quest (Disk 1 of 2).dsk', bytes(737280))
        second = self.make('msx/Quest (Disk 2 of 2).dsk', bytes(737280))
        sets = disk_sets([first, second], self.root / 'datas')
        self.assertEqual(sets.grouped, 1)
        self.assertEqual(self.detect(sets.paths[0]), 'msx2plus')


class DiscsOfOtherMachinesTests(AutoDetectionCase):
    def test_discs_the_converter_does_not_support_are_refused_not_guessed(self):
        self.refused(self.make('saturn/a.iso', iso_volume('SEGA SEGASATURN')))
        self.refused(self.make('segacd/b.iso', iso_volume('SEGADISCSYSTEM')))
        self.refused(self.make('any/c.iso', bytes(40000)))
        self.refused(self.make('any/d.cue', b'FILE "missing.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n'))

    def test_archives_the_converter_does_not_open_and_floppies_it_does_not_read_are_refused(self):
        self.refused(self.make('any/a.7z', b'7z\xbc\xaf\x27\x1c' + bytes(100)))
        self.refused(self.make('any/b.adf', b'DOS\x00' + bytes(901120 - 4)))
        self.refused(self.archive('any/c.zip', {'readme.txt': b'x'}))

    def test_firmware_without_a_cartridge_header_is_not_a_game(self):
        self.refused(self.make('bios/kickstart.rom', bytes(0x80000)))
        self.refused(self.make('bios/scph1001.bin', bytes(0x80000)))
        self.refused(self.make('bios/msx2.rom', bytes(0x20000)))
        self.refused(self.archive('bios/neogeo.zip', {'sp-s2.sp1': bytes(0x20000), 'sm1.sm1': bytes(0x20000)}))


class KnownGapTests(AutoDetectionCase):
    """Misdetections the audit measured and left for the lead (each one is an edit that moves a game stamp)."""

    @unittest.expectedFailure
    def test_a_chd_that_is_no_pc_engine_disc_is_not_claimed_by_its_extension(self):
        # A Sega CD, Dreamcast or Neo Geo CD image is a CHD too: `.chd` is listed by the PC Engine CD alone, so the extension
        # stage hands it that machine (systems/pc_engine_cd.py) when its content check has already said no.
        header = b'MComprHD' + struct.pack('>I', 124) + struct.pack('>I', 5) + bytes(200)
        self.refused(self.make('segacd/game.chd', header))

    @unittest.expectedFailure
    def test_a_disc_image_that_is_no_playstation_disc_is_not_claimed_by_its_extension(self):
        # Same fall-through for `.img` and `.ccd`, which only the PlayStation lists (a Saturn image, an Atari ST TOS).
        self.refused(self.make('saturn/game.img', bytes(300000)))
