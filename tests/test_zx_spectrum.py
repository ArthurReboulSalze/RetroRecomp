"""The ZX Spectrum profile, step 1 stage 1 (docs/ZX_SPECTRUM.md): the snapshot reader, the ROM pin, identification and the
report skeleton. No ROM and no game: every snapshot here is built by the test from authored bytes, and no ROM file is read."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from retrorecomp import zxs_roms, zxs_snapshot
from retrorecomp.report_schema import read_report
from retrorecomp.systems import (ALL_PROFILES, ConsoleMismatchError, UnsupportedConsoleError, get_profile,
                                 profile_for_path)
from retrorecomp.zxs_conversion import write_skeleton_report

PAGE = 0x4000


def _fill(seed: int) -> bytes:
    """16 KiB of authored filler, different per seed, with runs that the .z80 compression shortens."""
    return bytes(((index * 7 + seed) & 0xFF) if index % 64 else 0 for index in range(PAGE))


def _compress(block: bytes) -> bytes:
    """The .z80 compression, written here independently of the reader: runs of five or more (and any run of EDh of two
    or more) become ED ED nn bb; a single EDh is never followed by the next byte inside a run."""
    out, at = bytearray(), 0
    while at < len(block):
        byte, run = block[at], 1
        while at + run < len(block) and block[at + run] == byte and run < 255:
            run += 1
        if run >= 5 or (byte == 0xED and run >= 2):
            out += bytes((0xED, 0xED, run, byte))
            at += run
        elif byte == 0xED:
            out.append(0xED)
            at += 1
            if at < len(block):                      # the byte after a single EDh is written alone
                out.append(block[at])
                at += 1
        else:
            out.append(byte)
            at += 1
    return bytes(out)


def _header_v1(pc=0x8000, compressed=False, border=2, im=1, joystick=1) -> bytearray:
    header = bytearray(30)
    header[0], header[1] = 0x12, 0x34                # A, F
    header[2:4] = (0x5678).to_bytes(2, 'little')     # BC
    header[6:8] = pc.to_bytes(2, 'little')
    header[8:10] = (0xFF00).to_bytes(2, 'little')    # SP
    header[10], header[11] = 0x3F, 0x55              # I, R
    header[12] = 1 | border << 1 | (0x20 if compressed else 0)
    header[27] = header[28] = 1
    header[29] = im | joystick << 6
    return header


def z80_v1(banks: dict, compressed=False) -> bytes:
    ram = banks[5] + banks[2] + banks[0]
    body = (_compress(ram) + b'\x00\xED\xED\x00') if compressed else ram
    return bytes(_header_v1(compressed=compressed)) + body


def z80_v23(pages: dict, mode: int, version=3, modified=False, port=0x10, compress=True) -> bytes:
    header = _header_v1(pc=0)
    extra = 23 if version == 2 else 54
    header += bytearray(2 + extra)
    header[30:32] = extra.to_bytes(2, 'little')
    header[32:34] = (0x6000).to_bytes(2, 'little')
    header[34], header[35] = mode, port
    header[37] = 0x80 if modified else 0
    header[38] = 7
    header[39:55] = bytes(range(16))
    if version == 3:
        header[55:57] = (17000).to_bytes(2, 'little')
        header[57] = 3
    body = bytearray()
    for page, block in pages.items():
        if compress:
            packed = _compress(block)
            body += len(packed).to_bytes(2, 'little') + bytes((page,)) + packed
        else:
            body += b'\xFF\xFF' + bytes((page,)) + block
    return bytes(header + body)


def sna48(banks: dict, pc=0x7123) -> bytes:
    header = bytearray(27)
    header[0] = 0x3F
    header[19] = 4                                    # IFF2
    header[21:23] = (0x1234).to_bytes(2, 'little')
    sp = 0xFF00
    header[23:25] = sp.to_bytes(2, 'little')
    header[25], header[26] = 1, 3
    c000 = bytearray(banks[0])
    c000[sp - 0xC000:sp - 0xC000 + 2] = pc.to_bytes(2, 'little')
    return bytes(header) + banks[5] + banks[2] + bytes(c000)


def sna128(banks: dict, port: int) -> bytes:
    header = bytearray(27)
    header[23:25] = (0x8000).to_bytes(2, 'little')
    header[25] = 1
    paged = port & 7
    tail = (0x6123).to_bytes(2, 'little') + bytes((port, 0))
    rest = b''.join(banks[bank] for bank in range(8) if bank not in (5, 2, paged))
    return bytes(header) + banks[5] + banks[2] + banks[paged] + tail + rest


BANKS = {bank: _fill(bank) for bank in range(8)}


class SnapshotReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def write(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_the_compression_written_here_is_the_formats(self):
        for seed in range(3):
            self.assertEqual(zxs_snapshot._rle(_compress(BANKS[seed]), PAGE, False, 't'), BANKS[seed])
        self.assertEqual(zxs_snapshot._rle(b'\xED\xED\x03\x41\x10', None, False, 't'), b'AAA\x10')

    def test_a_version_1_z80_reads_as_a_48k_compressed_or_not(self):
        for compressed in (False, True):
            snap = zxs_snapshot.read_snapshot(self.write('a.z80', z80_v1(BANKS, compressed)))
            self.assertEqual((snap.format, snap.version, snap.model, snap.hardware), ('z80', 1, '48k', '48K'))
            self.assertEqual({bank: snap.banks[bank] for bank in (5, 2, 0)}, {bank: BANKS[bank] for bank in (5, 2, 0)})
            self.assertEqual((snap.registers['pc'], snap.registers['af'], snap.registers['bc']), (0x8000, 0x1234, 0x5678))
            self.assertEqual((snap.registers['r'], snap.border, snap.joystick, snap.registers['im']), (0xD5, 2, 'kempston', 1))
            self.assertIsNone(snap.port_7ffd)
        # The "SamRom" bit of byte 12 is set on plain 48K version 1 files of real libraries: it is not a SamRam.
        flagged = bytearray(z80_v1(BANKS, True))
        flagged[12] |= 0x10
        self.assertEqual(zxs_snapshot.read_snapshot(self.write('s.z80', bytes(flagged))).model, '48k')

    def test_versions_2_and_3_of_the_48k_16k_and_128k(self):
        pages48 = {8: BANKS[5], 4: BANKS[2], 5: BANKS[0]}
        snap = zxs_snapshot.read_snapshot(self.write('b.z80', z80_v23(pages48, 0, version=2)))
        self.assertEqual((snap.version, snap.model, snap.registers['pc']), (2, '48k', 0x6000))
        self.assertEqual(snap.banks[2], BANKS[2])
        snap = zxs_snapshot.read_snapshot(self.write('c.z80', z80_v23({8: BANKS[5]}, 0, modified=True)))
        self.assertEqual((snap.model, snap.hardware, sorted(snap.banks)), ('16k', '16K', [5]))
        pages128 = {3 + bank: BANKS[bank] for bank in range(8)}
        snap = zxs_snapshot.read_snapshot(self.write('d.z80', z80_v23(pages128, 4, port=0x13)))
        self.assertEqual((snap.version, snap.model, snap.port_7ffd, snap.ay_select), (3, '128k', 0x13, 7))
        self.assertEqual(snap.ay_registers, tuple(range(16)))
        self.assertEqual(snap.banks, BANKS)
        self.assertEqual(snap.tstates, 17727 - 17001)   # just after the interrupt (high counter 3), 17,000 left in the quarter
        snap = zxs_snapshot.read_snapshot(self.write('e.z80', z80_v23(pages128, 3, version=2, compress=False)))
        self.assertEqual((snap.model, snap.hardware), ('128k', '128K'))
        snap = zxs_snapshot.read_snapshot(self.write('f.z80', z80_v23(pages128, 12)))
        self.assertEqual((snap.model, snap.hardware), ('128k', '+2'))

    def test_sna_48k_and_128k(self):
        snap = zxs_snapshot.read_snapshot(self.write('a.sna', sna48(BANKS)))
        self.assertEqual((snap.format, snap.model, snap.registers['pc'], snap.registers['sp']), ('sna', '48k', 0x7123, 0xFF02))
        self.assertEqual((snap.border, snap.registers['iff2'], snap.joystick), (3, 1, None))
        for port in (0x10, 0x15, 0x12):               # bank 0 paged (131,103 bytes); bank 5 and bank 2 paged (147,487)
            data = sna128(BANKS, port)
            self.assertEqual(len(data), 131103 if port & 7 not in (2, 5) else 147487)
            snap = zxs_snapshot.read_snapshot(self.write('b.sna', data))
            self.assertEqual((snap.model, snap.port_7ffd, snap.registers['pc']), ('128k', port, 0x6123))
            self.assertEqual(snap.banks, BANKS)

    def test_a_zip_holding_one_snapshot(self):
        path = self.folder / 'game.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('Some Game (1984)(Somebody).z80', z80_v1(BANKS, True))
            bundle.writestr('readme.txt', 'text')
        self.assertTrue(zxs_snapshot.zip_holds_snapshot(path))
        snap = zxs_snapshot.read_snapshot(path)
        self.assertEqual((snap.member, snap.model), ('Some Game (1984)(Somebody).z80', '48k'))
        self.assertEqual(snap.sha256, hashlib.sha256(z80_v1(BANKS, True)).hexdigest())
        two = self.folder / 'two.zip'
        with zipfile.ZipFile(two, 'w') as bundle:
            bundle.writestr('a.z80', b'x')
            bundle.writestr('b.sna', b'y')
        self.assertFalse(zxs_snapshot.zip_holds_snapshot(two))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            zxs_snapshot.read_snapshot(two)

    def test_what_is_not_modelled_is_refused_with_a_sentence(self):
        pages128 = {3 + bank: BANKS[bank] for bank in range(8)}
        cases = {
            'a +3': (z80_v23(pages128, 7), r'\+3'),
            'a Pentagon': (z80_v23(pages128, 9), 'Pentagon'),
            'SamRam': (z80_v23({8: BANKS[5], 4: BANKS[2], 5: BANKS[0]}, 2), 'SamRam'),
            'a ROM page': (z80_v23({0: BANKS[1], 8: BANKS[5], 4: BANKS[2], 5: BANKS[0]}, 0), 'ROM page'),
            'a missing page': (z80_v23({8: BANKS[5], 4: BANKS[2]}, 0), 'missing'),
            'a short v1': (z80_v1(BANKS)[:-10], '48 KiB'),
            'a bad .sna size': (sna48(BANKS)[:-1], 'size'),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name):
                suffix = '.sna' if name.endswith('size') else '.z80'
                with self.assertRaisesRegex(ValueError, message):
                    zxs_snapshot.read_snapshot(self.write('x' + suffix, data))
        trdos = bytearray(sna128(BANKS, 0x10))
        trdos[zxs_snapshot.SNA48_BYTES + 3] = 1
        with self.assertRaisesRegex(ValueError, 'TR-DOS'):
            zxs_snapshot.read_snapshot(self.write('t.sna', bytes(trdos)))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_the_profile_is_experimental_developer_only_and_unlisted(self):
        profile = get_profile('zxs')
        self.assertEqual((profile.name, profile.status, profile.linux, profile.developer_only),
                         ('ZX Spectrum', 'experimental', 'pending', True))
        self.assertFalse(profile.available())
        from retrorecomp.systems import PROFILES, convertible_profiles
        self.assertNotIn(profile, PROFILES)
        self.assertNotIn(profile, convertible_profiles())
        self.assertIn(profile, ALL_PROFILES)

    def test_a_snapshot_says_the_machine_is_unavailable_and_steals_nothing(self):
        for name, data in (('a.z80', z80_v1(BANKS)), ('b.sna', sna48(BANKS))):
            path = self.folder / name
            path.write_bytes(data)
            with self.assertRaisesRegex(UnsupportedConsoleError, 'ZX Spectrum'):
                profile_for_path(path)
        bundle = self.folder / 'zx.zip'
        with zipfile.ZipFile(bundle, 'w') as archive:
            archive.writestr('game.z80', z80_v1(BANKS))
        with self.assertRaisesRegex(UnsupportedConsoleError, 'ZX Spectrum'):
            profile_for_path(bundle)
        # A ZIP of another machine is left to it: an MSX cartridge is not looked at by the Spectrum.
        other = self.folder / 'other.zip'
        with zipfile.ZipFile(other, 'w') as archive:
            archive.writestr('game.sms', b'\x00' * 0x8000)
        self.assertEqual(profile_for_path(other).id, 'sms')

    def test_when_available_a_snapshot_is_the_spectrums_and_a_mismatch_is_said(self):
        profile = get_profile('zxs')
        path = self.folder / 'a.z80'
        path.write_bytes(z80_v1(BANKS))
        original = type(profile).available
        type(profile).available = lambda self: True
        try:
            self.assertIs(profile_for_path(path), profile)
            with self.assertRaises(ConsoleMismatchError):
                profile_for_path(path, 'msx')
            self.assertEqual(profile.read_rom(path).model, '48k')
        finally:
            type(profile).available = original

    def test_the_skeleton_report_is_read_back_with_the_measures_unclaimed(self):
        path = self.folder / 'a.z80'
        path.write_bytes(z80_v1(BANKS))
        snap = zxs_snapshot.read_snapshot(path)
        target = self.folder / 'conversion-report.json'
        write_skeleton_report(target, snap, [('play', 600, 1000, 10)])
        stored = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual((stored['system']['id'], stored['status'], stored['latency_ms']), ('zxs', 'experimental', None))
        self.assertFalse(stored['hardware_accuracy_validated'])
        self.assertIn('contention is not modelled', stored['hardware_limits'][0])
        report = read_report(target)
        self.assertEqual(report['system']['id'], 'zxs')

    def test_the_conversion_refuses_plainly(self):
        from retrorecomp.core import ConversionError
        path = self.folder / 'a.z80'
        path.write_bytes(z80_v1(BANKS))
        with self.assertRaisesRegex(ConversionError, 'does not convert yet'):
            get_profile('zxs').convert(path)


class RomTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_the_pins_are_whole_and_consistent(self):
        self.assertEqual(len(zxs_roms.SOURCE_COMMIT), 40)
        self.assertEqual(set(zxs_roms.FILES), {'48.rom', '128-0.rom', '128-1.rom'})
        for size, digest in zxs_roms.FILES.values():
            self.assertEqual((size, len(digest)), (0x4000, 64))
        self.assertEqual({name for names in zxs_roms.MODEL_FILES.values() for name in names}, set(zxs_roms.FILES))
        options = get_profile('zxs').option_key_names
        self.assertEqual(set(zxs_roms.MODEL_OPTION.values()), options)

    def test_the_identity_is_the_pinned_image_without_a_valid_own_rom(self):
        self.assertEqual(zxs_roms.rom_identity(None, '48k'), zxs_roms.FILES['48.rom'][1])
        self.assertEqual(zxs_roms.rom_identity(None, '128k'), zxs_roms.PAIR_128_SHA256)
        stranger = self.folder / 'not-a-rom.bin'
        stranger.write_bytes(bytes(0x4000))
        self.assertEqual(zxs_roms.rom_identity(stranger, '16k'), zxs_roms.FILES['48.rom'][1])
        with self.assertRaisesRegex(ValueError, '48K ROM'):
            zxs_roms.own_rom(stranger, '48k')
        with self.assertRaisesRegex(ValueError, '128K ROM'):
            zxs_roms.own_rom(stranger, '128k')
        self.assertIsNone(zxs_roms.own_rom('', '48k'))
        self.assertIsNone(zxs_roms.known_digest(bytes(0x4000)))

    def test_the_firmware_search_knows_the_options_and_proposes_no_stranger(self):
        from retrorecomp import firmware_search
        self.assertIn('zxs_rom48', firmware_search.RECOGNISERS)
        self.assertIn('zxs_rom128', firmware_search.RECOGNISERS)
        stranger = self.folder / 'random.rom'
        stranger.write_bytes(_fill(9))
        self.assertEqual(firmware_search._zxs(stranger), [])

    def test_the_licence_page_is_declared_and_names_the_permission(self):
        profile = get_profile('zxs')
        self.assertIn('licenses/zx-spectrum-roms.md', profile.notice_files)
        text = zxs_roms.licence_text()
        self.assertIn('copyright Amstrad', text)
        self.assertIn(zxs_roms.SOURCE_COMMIT, text)


class MachineImageTests(unittest.TestCase):
    """The machine image the C machine loads (retrorecomp/zxs_build.zxs_image, native/zxs_machine/zxs_machine.c)."""

    def test_the_image_carries_the_model_the_ports_the_registers_and_the_banks(self):
        import struct
        from retrorecomp.zxs_build import IMAGE_BYTES, IMAGE_HEADER, zxs_image
        folder = Path(tempfile.mkdtemp())
        path = folder / 'a.z80'
        pages128 = {3 + bank: BANKS[bank] for bank in range(8)}
        path.write_bytes(z80_v23(pages128, 4, port=0x13))
        image = zxs_image(zxs_snapshot.read_snapshot(path))
        self.assertEqual(len(image), IMAGE_BYTES)
        self.assertEqual((image[:4], image[4], image[5], image[8], image[9]), (b'ZXS1', 1, 0, 0x13, 7))
        self.assertEqual(image[10:26], bytes(range(16)))
        self.assertEqual(struct.unpack('<12H', image[32:56])[11], 0x6000)          # PC
        self.assertEqual(struct.unpack('<I', image[56:60])[0], 17727 - 17001)
        for bank in range(8):
            self.assertEqual(image[IMAGE_HEADER + bank * PAGE:IMAGE_HEADER + (bank + 1) * PAGE], BANKS[bank])
        # A 48K .sna does not say where in the frame it was taken: the end of the /INT pulse.
        path = folder / 'b.sna'
        path.write_bytes(sna48(BANKS))
        image = zxs_image(zxs_snapshot.read_snapshot(path))
        self.assertEqual((image[4], struct.unpack('<I', image[56:60])[0]), (0, 32))
        self.assertEqual(image[IMAGE_HEADER + 1 * PAGE:IMAGE_HEADER + 2 * PAGE], bytes(PAGE))  # a bank a 48K never had

    def test_the_machine_core_passes_its_authored_checks(self):
        # tools/zxs_machine_selftest.py: the memory map, the paging, the frame, the ports, the picture, the beeper; skipped
        # without a C compiler.
        import importlib.util
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('zxs_machine_selftest', root / 'tools/zxs_machine_selftest.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.compiler()
        except SystemExit:
            self.skipTest('no C compiler')
        self.assertEqual(module.main(), 0)


if __name__ == '__main__':
    unittest.main()
