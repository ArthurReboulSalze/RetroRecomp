"""Synthetic cartridge checks; no commercial ROM is required."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from smsrecomp.cartridge16 import read_megadrive_rom, read_snes_rom
from smsrecomp.console16 import qualified_rom, reference_differences, convert16, MD_AUDIO_FIELDS, SNES_AUDIO_FIELDS, _md_scan_script
from smsrecomp.core import ConversionError
from smsrecomp.systems import profile_for_path, discover_roms
from smsrecomp.batch import identify, system_output
from smsrecomp.metadata import game_metadata


def md(region=b'JUE'):
    data = bytearray(32768)
    data[0x100:0x104] = b'SEGA'
    data[0x150:0x158] = b'TEST ROM'
    data[0x1f0:0x1f0 + len(region)] = region
    return bytes(data)


def snes(region=1, mapping='lorom', fast=False):
    data = bytearray(65536)
    offset = 0x7fc0 if mapping == 'lorom' else 0xffc0
    data[offset:offset + 21] = b'TEST ROM'.ljust(21, b' ')
    data[offset + 21] = (0x20 if mapping == 'lorom' else 0x21) | (0x10 if fast else 0)
    data[offset + 23] = 6
    data[offset + 25] = region
    data[offset + 28:offset + 32] = bytes.fromhex('cbed3412')
    data[offset + 60:offset + 62] = bytes.fromhex('0080')
    return bytes(data)


class Console16Tests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def source(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_md_header_identifies_linear_bin_and_region(self):
        for region, expected in ((b'J', 'ntsc'), (b'U', 'ntsc'), (b'E', 'pal'), (b'JUE', 'multi')):
            path = self.source('Game.bin', md(region))
            self.assertEqual(profile_for_path(path).id, 'md')
            self.assertEqual(read_megadrive_rom(path).standard, expected)

    def test_md_hexadecimal_regions_and_reserved_header_bytes(self):
        # Bit 0/2 = 60 Hz, bit 1/3 = 50 Hz. E retains the old Europe meaning.
        expected = ('unknown', 'ntsc', 'pal', 'multi', 'ntsc', 'ntsc', 'multi', 'multi',
                    'pal', 'multi', 'pal', 'multi', 'multi', 'multi', 'pal', 'multi')
        for digit, timing in zip('0123456789ABCDEF', expected):
            with self.subTest(digit=digit):
                payload = bytearray(md(digit.encode()))
                payload[0x1f3:0x200] = b'JUE RESERVED '.ljust(13, b' ')
                self.assertEqual(read_megadrive_rom(self.source('Game.md', payload)).standard, timing)
        for letters in (b' U ', b'J E', b'juE', b'   ', b'???'):
            timing = {b' U ': 'ntsc', b'J E': 'multi', b'juE': 'multi'}.get(letters, 'unknown')
            self.assertEqual(read_megadrive_rom(self.source('Game.md', md(letters))).standard, timing)

    def test_snes_header_identifies_pal_ntsc_and_fastrom(self):
        for mapping in ('lorom', 'hirom'):
            for region, expected in ((1, 'ntsc'), (2, 'pal')):
                path = self.source('Game.rom', snes(region, mapping, fast=True))
                self.assertEqual(profile_for_path(path).id, 'snes')
                self.assertEqual(read_snes_rom(path).standard, expected)
                self.assertEqual(read_snes_rom(path).mapping, mapping)

    def test_copier_header_removed_only_in_memory(self):
        payload = bytes(512) + snes()
        path = self.source('Game.smc', payload)
        rom = read_snes_rom(path)
        self.assertTrue(rom.copier_header)
        self.assertEqual(rom.data, snes())
        self.assertEqual(path.read_bytes(), payload)

    def test_corrupt_or_ambiguous_snes_header_rejected(self):
        broken = bytearray(snes())
        broken[0x7fde] ^= 1
        ambiguous = bytearray(snes())
        ambiguous[0xffc0:0x10000] = snes(mapping='hirom')[0xffc0:0x10000]
        for payload in (broken, ambiguous, bytes(65536)):
            with self.assertRaises(ConversionError):
                read_snes_rom(self.source('Invalid.sfc', payload))

    def test_archive_identifies_without_extraction_or_writes(self):
        for suffix, payload, expected in (('.md', md(), 'md'), ('.sfc', snes(), 'snes')):
            path = self.root / (expected + '.zip')
            with ZipFile(path, 'w') as archive:
                archive.writestr('folder/Game' + suffix, payload)
            before = path.read_bytes()
            self.assertEqual(identify(path).system, expected)
            self.assertEqual(profile_for_path(path).read_rom(path).data, payload)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_wrong_console_override_does_not_compile_foreign_rom(self):
        path = self.source('Game.bin', md())
        with self.assertRaises(ValueError):
            profile_for_path(path, 'snes')

    def test_unqualified_rom_is_rejected_before_dependencies(self):
        for system, path in (('md', self.source('Game.md', md())),
                             ('snes', self.source('Game.sfc', snes()))):
            with self.assertRaisesRegex(ConversionError, 'identified, but will not be compiled'):
                qualified_rom(path, system)

    def scan_conversion(self, *, advanced, fail_reference=False, learn_new=True):
        """Exercise real conversion scheduling/gates with authored probe results."""
        project = self.root / 'project'
        executable = project / 'build/Release/game.exe'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'authored test executable')
        source = self.source('Authored.md', md())
        rom = read_megadrive_rom(source)
        events = []
        pass_number = 0

        def prepare(*args, **options):
            nonlocal pass_number
            pass_number += 1
            events.append('build')
            return executable

        def probe(executable, directory, frames, *, play=False, reference=False,
                  gun_menu=None, scenario=None, input_script=None):
            scenario = scenario or ('play' if play else 'demo')
            events.append(('reference:' if reference else 'native:') + scenario)
            if input_script is not None:
                self.assertTrue(input_script.is_file())
            fields = MD_AUDIO_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped',
                'frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash',
                'cpu_pc', 'vsram_hash', 'vdp_register_hash')
            fallback = int(learn_new and scenario == 'advanced' and pass_number == 1)
            data = dict.fromkeys(fields, 1)
            data.update(scenario=scenario, frames=frames, native_entries=0 if reference else 100 - fallback,
                interpreted_opcodes=100 if reference else fallback,
                audio_native_opcodes=0 if reference else 200, audio_interpreted_opcodes=200 if reference else 0,
                audio_native_cycles=0 if reference else 800, audio_interpreted_cycles=800 if reference else 0,
                rom_entries=[{'offset': 42}] if fallback else [], audio_cpu='native')
            if fail_reference and reference and (not advanced or scenario == 'advanced'):
                data['cpu_hash'] = 2
            return data

        def learn(rom, checks):
            events.append('learn')
            return int(any(check['rom_entries'] for check in checks))

        with patch('smsrecomp.console16.qualified_rom', return_value=rom), \
                patch('smsrecomp.megadrive.profile_for', return_value={'title': 'Authored', 'id': 'authored'}), \
                patch('smsrecomp.console16.prepare16', side_effect=prepare), \
                patch('smsrecomp.console16.probe16', side_effect=probe), \
                patch('smsrecomp.megadrive.learn_entries', side_effect=learn), \
                patch('smsrecomp.megadrive_z80.learn_variants', return_value=0):
            if fail_reference:
                with self.assertRaisesRegex(ConversionError, 'reference comparison failed'):
                    convert16(source, system_id='md', output=self.root / 'reports',
                              frames=30, passes=3, md_advanced_scan=advanced, emit=lambda text: None)
                self.assertNotIn('learn', events)
                self.assertFalse((self.root / 'reports/conversion-report.json').exists())
                return events, None
            convert16(source, system_id='md', output=self.root / 'reports',
                      frames=30, passes=3, md_advanced_scan=advanced, emit=lambda text: None)
        report = json.loads((self.root / 'reports/conversion-report.json').read_text())
        return events, report

    def test_advanced_md_scan_validates_new_paths_before_learning_and_regeneration(self):
        events, report = self.scan_conversion(advanced=True)
        self.assertEqual(events[:8], ['build', 'native:demo', 'native:play', 'native:advanced',
                                     'reference:demo', 'reference:play', 'reference:advanced', 'learn'])
        self.assertEqual(events.count('build'), 2)
        self.assertEqual([check['frames'] for check in report['final_checks']], [30, 30, 6000])
        self.assertEqual(report['native_percentage'], [100.0, 100.0, 100.0])
        self.assertTrue(report['advanced_scan']['reference_before_learning'])
        self.assertTrue(report['native_validation']['passed'])

    def test_standard_md_scan_keeps_two_scenarios(self):
        events, report = self.scan_conversion(advanced=False)
        self.assertEqual(events.count('build'), 1)
        self.assertNotIn('native:advanced', events)
        self.assertFalse(report['advanced_scan']['enabled'])
        self.assertEqual([check['frames'] for check in report['final_checks']], [30, 30])
        self.assertEqual(events[:5], ['build', 'native:demo', 'native:play', 'reference:demo', 'reference:play'])
        self.assertTrue(report['native_validation']['reference_before_learning'])

    def test_standard_md_divergence_does_not_enter_the_memory_library(self):
        events, report = self.scan_conversion(advanced=False, fail_reference=True)
        self.assertIsNone(report)
        self.assertNotIn('learn', events)

    def test_snes_validates_sound_before_learning_and_regeneration(self):
        project = self.root / 'snes-project'
        executable = project / 'build/Release/game.exe'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'authored executable')
        source = self.source('Authored.sfc', snes())
        rom = read_snes_rom(source)
        events, passes = [], [0]

        def prepare(*args, **options):
            events.append('build'); passes[0] += 1
            return executable

        def probe(executable, directory, frames, *, play=False, reference=False, **options):
            scenario = 'play' if play else 'demo'
            events.append(('reference:' if reference else 'native:') + scenario)
            fields = SNES_AUDIO_FIELDS + ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash',
                'vram_hash', 'cram_hash', 'cpu_pc', 'oam_hash', 'high_oam_hash', 'apu_ram_hash',
                'cpu_cycles', 'master_cycles', 'apu_cycles')
            fallback = int(passes[0] == 1)
            data = dict.fromkeys(fields, 1)
            data.update(scenario=scenario, frames=frames, native_entries=0 if reference else 100,
                interpreted_opcodes=100 if reference else 0,
                audio_native_opcodes=0 if reference else 200 - fallback,
                audio_interpreted_opcodes=200 if reference else fallback,
                audio_native_cycles=0 if reference else 800 - 4 * fallback,
                audio_interpreted_cycles=800 if reference else 4 * fallback,
                spc_variants=[{'address': 42, 'opcode': 0xe8}] if fallback else [], audio_cpu='native')
            return data

        def learn(rom, checks):
            events.append('learn:spc')
            return int(passes[0] == 1)

        for fail in (True, False):
            events.clear(); passes[0] = 0
            with patch('smsrecomp.console16.qualified_rom', return_value=rom), \
                    patch('smsrecomp.supernintendo.profile_for', return_value={'title': 'Authored'}), \
                    patch('smsrecomp.console16.prepare16', side_effect=prepare), \
                    patch('smsrecomp.console16.probe16', side_effect=probe), \
                    patch('smsrecomp.supernintendo.learn_ram_variants', return_value=0), \
                    patch('smsrecomp.snes_spc.learn', side_effect=learn), \
                    patch('smsrecomp.console16.reference_differences', return_value=['pcm_hash'] if fail else []):
                if fail:
                    with self.assertRaisesRegex(ConversionError, 'reference comparison failed'):
                        convert16(source, system_id='snes', output=self.root / 'reports',
                                  frames=30, passes=3, emit=lambda text: None)
                    self.assertNotIn('learn:spc', events)
                else:
                    convert16(source, system_id='snes', output=self.root / 'reports',
                              frames=30, passes=3, emit=lambda text: None)
                    self.assertEqual(events[:6], ['build', 'native:demo', 'native:play',
                                                 'reference:demo', 'reference:play', 'learn:spc'])
                    self.assertEqual(events.count('build'), 2)
                    report = json.loads((self.root / 'reports/conversion-report.json').read_text())
                    self.assertEqual(report['audio_native_percentage'], [100.0, 100.0])
                    self.assertTrue(report['native_validation']['audio_pcm_match'])
                    self.assertTrue(report['native_validation']['reference_before_learning'])

    def test_failed_advanced_reference_never_teaches_the_library(self):
        self.scan_conversion(advanced=True, fail_reference=True)

    def test_advanced_scan_stops_when_no_new_paths_are_found(self):
        events, report = self.scan_conversion(advanced=True, learn_new=False)
        self.assertEqual(events.count('build'), 1)
        self.assertEqual(len(report['passes']), 1)

    def test_md_scan_six_buttons_and_t2_original_menu_inputs(self):
        script = _md_scan_script(self.root, 6000, six_buttons=True)
        rows = [tuple(map(int, line.split())) for line in script.read_text().splitlines()]
        self.assertTrue(any(p1 & 1024 for frame, p1, p2 in rows))
        self.assertTrue(any(p2 & 128 for frame, p1, p2 in rows))
        self.assertEqual([frame for frame, p1, p2 in rows], sorted(set(frame for frame, p1, p2 in rows)))
        script = _md_scan_script(self.root, 6000, gun_menu='t2')
        rows = {int(line.split()[0]): tuple(map(int, line.split()[1:])) for line in script.read_text().splitlines()}
        self.assertEqual(rows[1600], (2, 0))
        self.assertEqual(rows[1640], (2, 0))
        self.assertEqual(rows[2700], (128, 0))

    def test_md_pal_header_is_not_overridden_by_a_mislabelled_filename(self):
        with patch('smsrecomp.megadrive.profile_for') as profile:
            for region in (b'E', b'8', b'A', b'2'):
                path = self.source('Game (USA).md', md(region))
                with self.assertRaisesRegex(ConversionError, 'declares PAL'):
                    qualified_rom(path, 'md', 'ntsc')
            profile.assert_not_called()

    def test_md_timing_requires_both_header_and_revision_qualification(self):
        from smsrecomp.megadrive import video_standard
        for header in (b'E', b'8', b'A', b'2'):
            rom = read_megadrive_rom(self.source('Game (USA).md', md(header)))
            with patch('smsrecomp.megadrive.profile_for', return_value={'standards': ('pal',)}):
                self.assertEqual(video_standard(rom), 'pal')
                self.assertEqual(video_standard(rom, 'pal'), 'pal')
                with self.assertRaisesRegex(ConversionError, 'cannot be forced'):
                    video_standard(rom, 'ntsc')
        rom = read_megadrive_rom(self.source('Game.md', md()))
        with patch('smsrecomp.megadrive.profile_for', return_value={}):
            self.assertEqual(video_standard(rom), 'ntsc')
            with self.assertRaisesRegex(ConversionError, 'not been qualified'):
                video_standard(rom, 'pal')
        with patch('smsrecomp.megadrive.profile_for', return_value={'standards': ('ntsc', 'pal')}):
            self.assertEqual(video_standard(rom, 'pal'), 'pal')

    def test_md_unknown_region_rejected_before_profile_analysis(self):
        with patch('smsrecomp.megadrive.profile_for') as profile:
            for override in (None, 'ntsc'):
                with self.assertRaisesRegex(ConversionError, 'unrecognized region'):
                    qualified_rom(self.source('Game (USA).md', md(b'???')), 'md', override)
            profile.assert_not_called()

    def test_md_legacy_region_exception_is_bound_to_the_entire_rom(self):
        from smsrecomp import megadrive
        for header, mask in ((b'   ', 1), (b'US ', 4)):
            rom = read_megadrive_rom(self.source('Legacy (Europe).md', md(header)))
            profile = {'legacy_region_mask': mask}
            with patch.dict(megadrive.PROFILES, {rom.sha256: profile}):
                self.assertEqual(megadrive.video_standard(rom), 'ntsc')
                self.assertEqual(profile_for_path(rom.path).default_video_mode(rom.path), 'ntsc')
                self.assertEqual(megadrive.region_mask(rom), mask)
                with self.assertRaisesRegex(ConversionError, 'cannot be forced'):
                    megadrive.video_standard(rom, 'pal')
                modified = bytearray(rom.data)
                modified[0x300] ^= 1
                other = read_megadrive_rom(self.source('Legacy 2 (USA).md', modified))
                self.assertEqual(megadrive.region_mask(other), 0)
                with self.assertRaisesRegex(ConversionError, 'unrecognized region'):
                    megadrive.video_standard(other)

    def test_unsupported_md_formats_not_silently_deinterleaved(self):
        path = self.source('Game.smd', bytes(32768))
        with self.assertRaises(ConversionError):
            read_megadrive_rom(path)

    def test_mixed_folder_scans_roms_and_ignores_markdown(self):
        self.source('README.md', b'Documentation')
        first = self.source('Game.md', md())
        second = self.source('Game.sfc', snes())
        self.assertEqual(set(discover_roms(self.root)), {first, second})

    def test_export_names_and_metadata_are_console_specific(self):
        self.assertEqual(system_output(self.root, 'md').name, 'Mega Drive')
        self.assertEqual(system_output(self.root, 'snes').name, 'Super Nintendo')
        for system, console in (('md', 'Mega Drive'), ('snes', 'Super Nintendo')):
            metadata = game_metadata('Game', False, 'ntsc', system)
            self.assertEqual(metadata['Console'], console)
            self.assertIn(console + ' NTSC', metadata['FileDescription'])

    def test_empty_reports_cannot_validate_native_execution(self):
        for system in ('md', 'snes'):
            differences = reference_differences(system, {}, {})
            self.assertIn('cpu_hash', differences)
            self.assertIn('sequence_hash', differences)
            self.assertIn('retired_instruction_count', differences)

    def test_validation_rejects_memory_timing_and_retired_count_differences(self):
        from smsrecomp.console16 import MD_AUDIO_FIELDS
        fields = MD_AUDIO_FIELDS + SNES_AUDIO_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped', 'frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash',
                  'cpu_pc', 'vsram_hash', 'vdp_register_hash', 'oam_hash', 'high_oam_hash',
                  'apu_ram_hash', 'cpu_cycles', 'master_cycles', 'apu_cycles')
        native = dict.fromkeys(fields, 1) | {'native_entries': 100, 'interpreted_opcodes': 0,
            'audio_native_opcodes': 90, 'audio_interpreted_opcodes': 10,
            'audio_native_cycles': 900, 'audio_interpreted_cycles': 100}
        reference = native | {'native_entries': 0, 'interpreted_opcodes': 100,
            'audio_native_opcodes': 0, 'audio_interpreted_opcodes': 100,
            'audio_native_cycles': 0, 'audio_interpreted_cycles': 1000}
        for system, key in (('md', 'vdp_register_hash'), ('md', 'fm_hash'), ('md', 'ym_timer_hash'),
                            ('md', 'z80_ram_hash'), ('md', 'console_version'), ('md', 'cpu_usp'), ('md', 'cpu_ssp'),
                            ('md', 'cpu_stopped'), ('snes', 'master_cycles'), ('snes', 'oam_hash'),
                            ('snes', 'spc_cpu_hash'), ('snes', 'dsp_state_hash'), ('snes', 'pcm_hash')):
            self.assertEqual(reference_differences(system, native, reference), [])
            self.assertIn(key, reference_differences(system, native, reference | {key: 2}))
            self.assertIn(key, reference_differences(system, native, reference | {key: None}))
            self.assertIn('retired_instruction_count', reference_differences(system, native,
                reference | {'interpreted_opcodes': 99}))
        self.assertIn('z80_instruction_count', reference_differences('md', native,
            reference | {'audio_interpreted_opcodes': 99}))
        self.assertIn('z80_cycle_count', reference_differences('md', native,
            reference | {'audio_interpreted_cycles': 999}))
        self.assertIn('spc_instruction_count', reference_differences('snes', native,
            reference | {'audio_interpreted_opcodes': 99}))
        self.assertIn('spc_cycle_count', reference_differences('snes', native,
            reference | {'audio_interpreted_cycles': 999}))
