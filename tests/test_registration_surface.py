"""Registering a machine edits no stamped file, and recognising files did not change when the hooks moved
into the profiles (1.6.3, package P1; docs/NEW_MACHINE.md, docs/STANDARDS.md rules 3 and 5).

The detection table is built from synthetic files only: authored headers, never ROM bytes. Its expected
results were taken from `profile_for_path` of 1.6.2 over 136 such files (the ones below are a selection)
before the identification hooks were moved from `systems/__init__.py` into the profiles.
"""
import hashlib
import importlib.util
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from retrorecomp import compilation_inputs, stamp_inputs
from retrorecomp import systems
from retrorecomp.systems import (ALL_PROFILES, ConsoleMismatchError, Cpu, Identify, SystemProfile, UnsupportedConsoleError,
                                 registry)
from retrorecomp.systems.specs import PathSpec

REPO = Path(__file__).resolve().parents[1]
CONSOLES = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1')

# The set of extensions `discover_roms` listed in 1.6.2, as a literal: it must not move silently.
TODAYS_EXTENSIONS = frozenset({
    '.sms', '.gg', '.gb', '.zip', '.bin', '.rom', '.gbc', '.gba', '.nes',
    '.fds', '.sfc', '.smc', '.n64', '.z64', '.v64', '.md', '.gen', '.smd', '.pce',
    '.a26', '.a78', '.7z', '.chd', '.cue', '.iso', '.neo',
    '.dim', '.xdf', '.m3u',
})


class SyntheticProfile(SystemProfile):
    """A tenth machine as a throwaway module would define it: data and hooks, nothing else."""
    id = 'zz'
    name = 'Synthetic Tenth'
    extensions = ('.zzd',)
    export_folder = 'Synthetic'
    video_modes = ('pal',)
    status = 'experimental'
    cpus = (Cpu('m68000', 'main', 'instructions'),)
    quick_state_family = 'rr16'
    feedback_kinds = frozenset({99})
    path_spec = PathSpec(order=9, sections=(('m68k', 'zz'),), source_bounds=(('rom', (1, 2)),))
    identify = Identify(path_order=40, content_order=6)

    def identify_path(self, path, suffix, selected_system):
        return self if suffix == '.zzp' else None

    def identify_content(self, data):
        return self if data.startswith(b'ZZ10') else None

    def read_rom(self, path):
        raise NotImplementedError

    def default_video_mode(self, path):
        return 'pal'

    def convert(self, path, **options):
        raise NotImplementedError


def module_digests():
    """sha256 of the source of every converter module a stamp lists (the files a new machine must not edit)."""
    digests = {}
    for name in compilation_inputs.manifest_names():
        if name.startswith('retrorecomp'):
            digests[name] = hashlib.sha256(Path(importlib.util.find_spec(name).origin).read_bytes()).hexdigest()
    return digests


class RegistrationSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.profile = SyntheticProfile()

    def register(self):
        registry.register(self.profile)
        self.addCleanup(lambda: registry.unregister('zz') if 'zz' in systems.system_ids() else None)

    def test_registering_a_machine_edits_and_moves_nothing_that_is_stamped(self):
        stamps = {system: (compilation_inputs.engine_stamp(system), compilation_inputs.role_stamps(system))
                  for system in CONSOLES}
        digests, names = module_digests(), compilation_inputs.manifest_names()
        self.register()
        self.assertEqual(systems.system_ids(), (*CONSOLES, 'zz'))
        # The registration list is the only thing that changed, and no stamp hashes it.
        self.assertEqual(module_digests(), digests)
        self.assertEqual(compilation_inputs.manifest_names(), names)
        self.assertEqual({system: (compilation_inputs.engine_stamp(system), compilation_inputs.role_stamps(system))
                          for system in CONSOLES}, stamps)
        self.assertIn('registry', stamp_inputs.INTERFACE_MODULES)
        self.assertNotIn('retrorecomp.systems.registry', names)

    def test_generic_code_names_no_console(self):
        # systems/__init__.py reads the registered profiles; a console id is never a literal there.
        source = (REPO / 'retrorecomp' / 'systems' / '__init__.py').read_text(encoding='utf-8')
        for system in CONSOLES:
            self.assertNotIn(f"'{system}'", source, system)
            self.assertNotIn(f'"{system}"', source, system)
        for module in ('master_system', 'game_gear', 'game_boy', 'neogeo', 'cps1', 'x68000', 'console16'):
            self.assertNotIn(module, source, module)

    def test_the_lists_follow_the_registration(self):
        self.assertNotIn('zz', systems.system_ids())
        self.register()
        self.assertEqual(systems.ALL_PROFILES[-1], self.profile)
        self.assertEqual(systems.system_ids()[-1], 'zz')
        self.assertIs(systems.get_profile('zz'), self.profile)
        self.assertIs(systems.find_profile('zz'), self.profile)
        self.assertIn(self.profile, systems.PROFILES)
        self.assertIn(self.profile, systems.available_profiles())
        self.assertIn(self.profile, systems.EXPERIMENTAL_PROFILES)
        self.assertIn('.zzd', systems.ROM_CANDIDATE_EXTENSIONS)
        # The CPU family of a machine is derived from its profile.
        self.assertIn('zz', tuple(profile.id for profile in systems.ALL_PROFILES
                                  if any(cpu.arch == 'm68000' for cpu in profile.cpus)))
        registry.unregister('zz')
        self.assertNotIn('zz', systems.system_ids())
        self.assertNotIn('.zzd', systems.ROM_CANDIDATE_EXTENSIONS)
        self.assertIsNone(systems.find_profile('zz'))

    def test_a_registered_machine_is_discovered_and_recognised(self):
        self.register()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'game.zzd').write_bytes(bytes(64))
            (root / 'game.zzp').write_bytes(bytes(64))
            (root / 'headerless.bin').write_bytes(b'ZZ10' + bytes(64))
            (root / 'other.bin').write_bytes(bytes(64))
            self.assertIn('game.zzd', [path.name for path in systems.discover_roms(root)])
            self.assertIs(systems.profile_for_path(root / 'game.zzd'), self.profile)
            self.assertIs(systems.profile_for_path(root / 'game.zzp'), self.profile)
            self.assertIs(systems.profile_for_path(root / 'headerless.bin'), self.profile)
            self.assertIs(systems.profile_for_path(root / 'headerless.bin', 'zz'), self.profile)
            with self.assertRaises(ConsoleMismatchError):
                systems.profile_for_path(root / 'headerless.bin', 'md')
            with self.assertRaises(UnsupportedConsoleError):
                systems.profile_for_path(root / 'other.bin')
            # The machines of 1.6.2 are recognised as before.
            (root / 'game.sms').write_bytes(bytes(0x8000))
            self.assertEqual(systems.profile_for_path(root / 'game.sms').id, 'sms')

    def test_a_registered_machines_options_are_filtered_like_the_others(self):
        from retrorecomp.systems import OptionKey
        profile = SyntheticProfile()
        profile.option_keys = (OptionKey('zz_firmware', kind='path'),)
        registry.register(profile)
        self.addCleanup(registry.unregister, 'zz')
        self.assertIn('zz_firmware', systems.console_option_keys())
        settings = {'zz_firmware': 1, 'md_advanced_scan': 1}
        systems.drop_foreign_options('md', settings)
        self.assertEqual(settings, {'md_advanced_scan': 1})
        settings = {'zz_firmware': 1, 'md_advanced_scan': 1}
        systems.drop_foreign_options('zz', settings)
        self.assertEqual(settings, {'zz_firmware': 1})

    def test_the_registry_refuses_what_would_make_recognition_ambiguous(self):
        self.register()
        with self.assertRaises(ValueError):
            registry.register(SyntheticProfile())  # the same id
        clash = SyntheticProfile()
        clash.id = 'zy'
        with self.assertRaises(ValueError):
            registry.register(clash)  # the same identification order as zz
        clash.identify = Identify(path_order=41, content_order=1)  # the order of the NES
        with self.assertRaises(ValueError):
            registry.register(clash)
        with self.assertRaises(TypeError):
            registry.register(object())
        self.assertEqual(systems.system_ids(), (*CONSOLES, 'zz'))


class ExtensionSetTests(unittest.TestCase):
    def test_the_extensions_discover_roms_lists_are_those_of_1_6_2(self):
        self.assertEqual(systems.ROM_CANDIDATE_EXTENSIONS, TODAYS_EXTENSIONS)

    def test_they_are_the_profiles_extensions_and_a_literal_foreign_list(self):
        own = frozenset(extension for profile in ALL_PROFILES for extension in profile.extensions)
        self.assertEqual(own | registry.FOREIGN_EXTENSIONS, TODAYS_EXTENSIONS)
        # Nothing of the foreign list is something a profile reads, but the containers and headerless names.
        self.assertTrue(registry.FOREIGN_EXTENSIONS.isdisjoint(own - {'.zip'}))
        self.assertLessEqual(own, systems.ROM_CANDIDATE_EXTENSIONS)
        self.assertEqual(own - {'.zip'}, {'.sms', '.gg', '.gb', '.nes', '.md', '.gen', '.sfc', '.smc', '.neo',
                                         '.dim', '.xdf', '.m3u'})


# --- the detection table ----------------------------------------------------------------------------


def blank(size):
    return bytearray(size)


def sms_rom(region=4, at=0x7ff0, size=0x8000, offset=0):
    data = blank(size)
    data[offset + at:offset + at + 8] = b'TMR SEGA'
    data[offset + at + 15] = region << 4
    return bytes(data)


def gb_rom(size_code=0, bad_checksum=False):
    data = blank((0x8000 << size_code) if size_code <= 8 else 72 * 0x4000)
    data[0x134:0x13c] = b'SYNTHGB1'
    data[0x148] = size_code
    checksum = 0
    for value in data[0x134:0x14d]:
        checksum = (checksum - value - 1) & 0xff
    data[0x14d] = checksum ^ (1 if bad_checksum else 0)
    return bytes(data)


def md_rom():
    data = blank(0x8000)
    data[0x100:0x104] = b'SEGA'
    return bytes(data)


def snes_rom(copier=False):
    data = blank(0x8000)
    base = 0x7fc0
    data[base:base + 21] = b'SYNTH SNES           '
    data[base + 21] = 0x20
    data[base + 23] = 0x08
    data[base + 28:base + 30] = struct.pack('<H', 0x5a5a ^ 0xffff)
    data[base + 30:base + 32] = struct.pack('<H', 0x5a5a)
    data[base + 60:base + 62] = struct.pack('<H', 0x8000)
    return (bytes(512) if copier else b'') + bytes(data)


def nes_rom():
    return b'NES\x1a' + bytes(16380)


def neo_file(bad=False):
    lengths = (0x200, 0x20000, 0x10000, 0, 0, 128)
    header = bytearray(4096)
    header[:4] = b'NEO\x01'
    struct.pack_into('<6I', header, 4, *lengths)
    return bytes(header) + (bytes(sum(lengths)) if not bad else b'\0' * 10)


def zipped(path, members, forged=None):
    """A ZIP of the given members; ``forged`` maps a member name to the CRC its header should carry."""
    forged = forged or {}
    current = {'crc': 0}
    original = zipfile.crc32

    def fake(data, value=0):
        return current['crc'] if current['crc'] else original(data, value)

    with patch('zipfile.crc32', fake):
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as archive:
            for name, data in members:
                current['crc'] = forged.get(name, 0)
                archive.writestr(name, data)
    return path


class DetectionTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.root = Path(folder.name)
        write = lambda name, data: (cls.root / name).write_bytes(data)  # noqa: E731
        for name, data in {
                'plain.sms': sms_rom(region=0), 'gg-header.sms': sms_rom(region=6), 'sms-header.gg': sms_rom(region=4),
                'plain.gg': bytes(0x8000), 'sms-3ff0.sms': sms_rom(region=5, at=0x3ff0),
                'sms-copier.sms': sms_rom(region=6, offset=512, size=0x8000 + 512),
                'short-header.sms': sms_rom(region=6)[:0x7ff0 + 15], 'UPPER.SMS': sms_rom(region=6),
                'game.gb': gb_rom(), 'game.nes': nes_rom(), 'game.md': md_rom(), 'game.gen': bytes(100),
                'game.sfc': snes_rom(), 'game.smc': snes_rom(copier=True), 'md.bin': md_rom(), 'md.rom': md_rom(),
                'md-short.bin': md_rom()[:0x3ff], 'nes.bin': nes_rom(),
                'nes-and-md.bin': nes_rom()[:0x100] + b'SEGA' + bytes(0x8000), 'sms.bin': sms_rom(region=4),
                'gg.rom': sms_rom(region=6), 'snes.bin': snes_rom(), 'snes-copier.rom': snes_rom(copier=True),
                'gb.bin': gb_rom(), 'gb-72banks.bin': gb_rom(size_code=0x52), 'gb-badsum.bin': gb_rom(bad_checksum=True),
                'zeros.bin': bytes(0x8000), 'tiny.bin': b'abc', 'disk.dim': bytes(1024), 'disk.xdf': bytes(1024),
                'disk.m3u': bytes(64), 'good.neo': neo_file(), 'bad.neo': neo_file(bad=True),
                'foreign.gba': bytes(0x8000), 'foreign': bytes(0x8000), 'z-corrupt.zip': b'PK\x03\x04 not a zip'}.items():
            write(name, data)
        zipped(cls.root / 'z-sms.zip', [('game.sms', sms_rom(region=0))])
        zipped(cls.root / 'z-gg.zip', [('game.gg', sms_rom(region=4))])
        zipped(cls.root / 'z-md.zip', [('game.md', md_rom())])
        zipped(cls.root / 'z-bin-nes.zip', [('game.bin', nes_rom())])
        zipped(cls.root / 'z-bin-snes.zip', [('game.bin', snes_rom())])
        zipped(cls.root / 'z-bin-sega.zip', [('game.bin', sms_rom(region=6))])
        zipped(cls.root / 'z-bin-zeros.zip', [('game.bin', bytes(0x8000))])
        zipped(cls.root / 'z-text.zip', [('readme.txt', b'x')])
        zipped(cls.root / 'z-two.zip', [('a.sms', sms_rom()), ('b.gb', gb_rom())])
        zipped(cls.root / 'ngset.zip', [('game-p1.bin', bytes(16)), ('game-c1.bin', bytes(16)),
                                        ('game-m1.bin', bytes(16))])
        zipped(cls.root / 'ngset-partial.zip', [('game-p1.bin', bytes(16)), ('game-c1.bin', bytes(16))])
        # A CPS-1 set is recognised by the CRC and size of its program ROMs; the headers are forged, the data zeros.
        from retrorecomp import cps1_catalogue
        programs = cps1_catalogue.program_files(cps1_catalogue.games()[0])[:2]
        zipped(cls.root / 'cpsset.zip', [(item['name'], bytes(item['bytes'])) for item in programs],
               {item['name']: item['crc32'] for item in programs})
        zipped(cls.root / 'cpsset-one.zip', [(programs[0]['name'], bytes(programs[0]['bytes']))],
               {programs[0]['name']: programs[0]['crc32']})

    TABLE = (
        # extension matches, settled by the Sega header
        ('plain.sms', None, 'sms'), ('gg-header.sms', None, 'gg'), ('sms-header.gg', None, 'sms'),
        ('plain.gg', None, 'gg'), ('sms-3ff0.sms', None, 'gg'), ('sms-copier.sms', None, 'gg'),
        ('short-header.sms', None, 'sms'), ('UPPER.SMS', None, 'gg'), ('missing.sms', None, 'sms'),
        ('game.gb', None, 'gb'), ('game.nes', None, 'nes'), ('game.md', None, 'md'), ('game.gen', None, 'md'),
        ('game.sfc', None, 'snes'), ('game.smc', None, 'snes'), ('missing.nes', None, 'nes'),
        # headerless dumps, sniffed in the order NES, Mega Drive, Sega, SNES, Game Boy
        ('md.bin', None, 'md'), ('md.rom', None, 'md'), ('nes.bin', None, 'nes'), ('nes-and-md.bin', None, 'nes'),
        ('sms.bin', None, 'sms'), ('gg.rom', None, 'gg'), ('snes.bin', None, 'snes'), ('snes-copier.rom', None, 'snes'),
        ('gb.bin', None, 'gb'), ('gb-72banks.bin', None, 'gb'),
        ('md-short.bin', None, UnsupportedConsoleError), ('gb-badsum.bin', None, UnsupportedConsoleError),
        ('zeros.bin', None, UnsupportedConsoleError), ('tiny.bin', None, UnsupportedConsoleError),
        ('missing.bin', None, FileNotFoundError),
        # an explicit choice resolves a headerless dump only
        ('zeros.bin', 'md', 'md'), ('zeros.bin', 'x68', 'x68'), ('md.bin', 'md', 'md'),
        ('md.bin', 'snes', ('mismatch', 'md')), ('plain.sms', 'gg', ('mismatch', 'sms')),
        ('gg-header.sms', 'gg', 'gg'), ('gg-header.sms', 'sms', ('mismatch', 'gg')),
        ('game.nes', 'gb', ('mismatch', 'nes')), ('plain.sms', 'zz', ValueError),
        # the X68000 claims its media by extension, before anything else
        ('disk.dim', None, 'x68'), ('disk.xdf', None, 'x68'), ('disk.m3u', None, 'x68'), ('disk.dim', 'x68', 'x68'),
        ('disk.xdf', 'sms', ('mismatch', 'x68')),
        # Neo Geo: a container, or a ZIP named like a cartridge set
        ('good.neo', None, 'ng'), ('good.neo', 'ng', 'ng'), ('good.neo', 'md', ('mismatch', 'ng')),
        ('bad.neo', None, ValueError), ('missing.neo', None, FileNotFoundError),
        ('ngset.zip', None, 'ng'), ('ngset.zip', 'ng', 'ng'), ('ngset.zip', 'sms', ('mismatch', 'ng')),
        ('ngset-partial.zip', None, ValueError),
        # CPS-1: a ZIP whose program ROMs are catalogued, or any ZIP when the player chose it
        ('cpsset.zip', None, 'cps1'), ('cpsset.zip', 'cps1', 'cps1'), ('cpsset.zip', 'ng', 'ng'),
        ('cpsset.zip', 'md', UnsupportedConsoleError), ('cpsset-one.zip', None, UnsupportedConsoleError),
        ('z-sms.zip', 'cps1', 'cps1'),
        # a cartridge inside a ZIP
        ('z-sms.zip', None, 'sms'), ('z-gg.zip', None, 'sms'), ('z-md.zip', None, 'md'), ('z-md.zip', 'snes', ('mismatch', 'md')),
        ('z-bin-nes.zip', None, 'nes'), ('z-bin-snes.zip', None, 'snes'), ('z-bin-sega.zip', None, 'gg'),
        ('z-bin-zeros.zip', None, UnsupportedConsoleError), ('z-text.zip', None, UnsupportedConsoleError),
        ('z-two.zip', None, ValueError), ('z-corrupt.zip', None, ValueError),
        # foreign files
        ('foreign.gba', None, UnsupportedConsoleError), ('foreign', None, UnsupportedConsoleError),
        ('foreign.gba', 'md', UnsupportedConsoleError),
    )

    def outcome(self, name, selected):
        try:
            profile = systems.profile_for_path(self.root / name, selected) if selected \
                else systems.profile_for_path(self.root / name)
        except ConsoleMismatchError as error:
            return 'mismatch', error.detected_system
        except Exception as error:  # noqa: BLE001 - the table records the type
            return type(error)
        return profile.id

    def test_every_case_gives_the_result_of_1_6_2(self):
        for name, selected, expected in self.TABLE:
            with self.subTest(name=name, selected=selected):
                got = self.outcome(name, selected)
                if isinstance(expected, type):
                    # UnsupportedConsoleError and ConsoleMismatchError are ValueErrors: compare the exact type.
                    self.assertIs(got, expected)
                else:
                    self.assertEqual(got, expected)

    def test_the_x68000_withdrawn_from_an_installation_is_refused_cleanly(self):
        with tempfile.TemporaryDirectory() as empty, patch('retrorecomp.x68000.ASSETS', Path(empty)):
            self.assertEqual([profile.id for profile in systems.available_profiles()],
                             ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1'])
            self.assertEqual([profile.id for profile in systems.EXPERIMENTAL_PROFILES], ['cps1'])
            for selected in (None, 'x68', 'sms'):
                with self.assertRaises(UnsupportedConsoleError) as caught:
                    systems.profile_for_path(self.root / 'disk.dim', selected)
                self.assertIs(type(caught.exception), UnsupportedConsoleError)
                self.assertIn('unavailable in this installation', str(caught.exception))
            self.assertEqual(systems.get_profile('x68').id, 'x68')  # still readable for an existing export
        self.assertEqual([profile.id for profile in systems.EXPERIMENTAL_PROFILES], ['cps1', 'x68'])

    def test_the_documented_orders_of_the_lists_are_kept(self):
        self.assertEqual(systems.system_ids(), CONSOLES)
        self.assertEqual([profile.id for profile in systems.PROFILES],
                         ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1'])
        self.assertEqual([profile.id for profile in systems.available_profiles()],
                         ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68'])


if __name__ == '__main__':
    unittest.main()
