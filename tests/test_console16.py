"""Synthetic cartridge checks; no commercial ROM is required."""
from pathlib import Path
from datetime import datetime, timezone
import json
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from smsrecomp.cartridge16 import read_megadrive_rom, read_snes_rom
from smsrecomp.console16 import conversion_rom, reference_differences, convert16, MD_AUDIO_FIELDS, MD_SRAM_FIELDS, SNES_AUDIO_FIELDS, _md_scan_script, _md_early_start_script, _md_menu_confirm_script
from smsrecomp.core import ConversionError, module_fingerprint
from smsrecomp.systems import profile_for_path, discover_roms
from smsrecomp.batch import identify, system_output
from smsrecomp.metadata import game_metadata


def md(region=b'JUE'):
    data = bytearray(32768)
    for offset, value in ((0, 0xffc000), (4, 0x200), (0x70, 0x220), (0x78, 0x240)):
        data[offset:offset + 4] = value.to_bytes(4, 'big')
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

    def test_previous_md_state_abi_requires_same_engine_and_disk_layout(self):
        from smsrecomp.console16 import REPOSITORIES
        from smsrecomp.console16_state import write_config
        rom = read_megadrive_rom(self.source('state.md', md()))
        (self.root/'retro_md_game.h').write_text('#define RR_MD_PAL 0\n')
        write_config(self.root, rom, 'md', 'Test', REPOSITORIES)
        self.assertIn('RR16_STATE_COMPAT_ABI "ea70d6ee',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_2 "9462ea4e',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_3 "66c19234',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_4 "ff419f0a',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_5 "70957023',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_6 "e9576d9f',
                      (self.root/'retro16_state_config.h').read_text())
        self.assertIn('RR16_STATE_COMPAT_ABI_7 "b5a707ff',
                      (self.root/'retro16_state_config.h').read_text())
        changed = {**REPOSITORIES, 'md': ('other/engine', '0'*40, 'other')}
        write_config(self.root, rom, 'md', 'Test', changed)
        self.assertNotIn('RR16_STATE_COMPAT_ABI', (self.root/'retro16_state_config.h').read_text())
        with patch('smsrecomp.console16_state.PORTABLE_STATE_ABI', 3):
            write_config(self.root, rom, 'md', 'Test', REPOSITORIES)
            self.assertNotIn('RR16_STATE_COMPAT_ABI', (self.root/'retro16_state_config.h').read_text())

    def test_bundled_compiler_fingerprint_needs_no_source_file(self):
        import sys
        from types import SimpleNamespace
        name = 'retro_test_bundled_adapter'
        body = 'def generate():\n    return lambda: 42\n'
        loader = SimpleNamespace(get_code=lambda name: compile(body, 'bundle-one/adapter.py', 'exec'))
        module = SimpleNamespace(__file__=str(self.root / 'absent.py'), __loader__=loader)
        with patch.dict(sys.modules, {name: module}):
            original = module_fingerprint(name)
            loader.get_code = lambda name: compile(body, 'bundle-two/adapter.py', 'exec')
            self.assertEqual(module_fingerprint(name), original)
            loader.get_code = lambda name: compile(body.replace('42', '43'), 'adapter.py', 'exec')
            self.assertNotEqual(module_fingerprint(name), original)
            loader.get_code = lambda name: None
            with self.assertRaises(ConversionError):
                module_fingerprint(name)

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

    def test_full_region_labels_override_a_misleading_filename_without_patching_rom(self):
        for label, expected in ((b'EUROPE', 'pal'), (b'Europe', 'pal'), (b'JAPAN', 'ntsc')):
            with self.subTest(label=label):
                payload = md(label)
                path = self.source('Wrong region (USA).md', payload)
                self.assertEqual(identify(path).video_hint, expected)
                self.assertEqual(conversion_rom(path, 'md').standard, expected)
                self.assertEqual(path.read_bytes(), payload)
        for label in (b'EUROPE???', b'JAPAN???'):
            path = self.source('Malformed (USA).md', md(label))
            with self.assertRaisesRegex(ConversionError, 'region header'):
                conversion_rom(path, 'md')

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

    def test_snes_japanese_header_titles_keep_identity_timing_and_hardware_checks(self):
        for mapping in ('lorom', 'hirom'):
            for region, standard in ((0, 'ntsc'), (2, 'pal')):
                with self.subTest(mapping=mapping, region=region):
                    payload = bytearray(snes(region, mapping, fast=True))
                    offset = 0x7fc0 if mapping == 'lorom' else 0xffc0
                    title = 'SFC ｶﾀｶﾅ'.encode('shift_jis')
                    payload[offset:offset+21] = title.ljust(21, b' ')
                    path = self.source('Japanese.sfc', payload)
                    self.assertEqual(profile_for_path(path).id, 'snes')
                    rom = conversion_rom(path, 'snes')
                    self.assertEqual((rom.title, rom.mapping, rom.standard), ('SFC ｶﾀｶﾅ', mapping, standard))
                    self.assertEqual(rom.data, payload)
                    self.assertEqual(path.read_bytes(), payload)
                    payload[offset+22] = 0x13
                    with patch('smsrecomp.console16.dependencies16') as dependencies:
                        with self.assertRaisesRegex(ConversionError, 'enhancement chip'):
                            conversion_rom(self.source('Japanese SuperFX.sfc', payload), 'snes')
                        dependencies.assert_not_called()

    def test_snes_header_titles_reject_non_jis_bytes_and_still_reject_bad_checksums(self):
        for invalid in (0x00, 0x1f, 0x7f, 0x80, 0xa0, 0xe0, 0xff):
            with self.subTest(byte=invalid):
                payload = bytearray(snes())
                payload[0x7fc3] = invalid
                with self.assertRaises(ConversionError):
                    read_snes_rom(self.source('Invalid title.sfc', payload))
        payload = bytearray(snes())
        payload[0x7fc0:0x7fd5] = 'ｶﾀｶﾅ'.encode('shift_jis').ljust(21, b' ')
        payload[0x7fde] ^= 1
        with self.assertRaises(ConversionError):
            read_snes_rom(self.source('Invalid checksum.sfc', payload))

    def test_corrupt_or_ambiguous_snes_header_rejected(self):
        broken = bytearray(snes())
        broken[0x7fde] ^= 1
        ambiguous = bytearray(snes())
        ambiguous[0xffc0:0x10000] = snes(mapping='hirom')[0xffc0:0x10000]
        for payload in (broken, ambiguous, bytes(65536)):
            with self.assertRaises(ConversionError):
                read_snes_rom(self.source('Invalid.sfc', payload))

    def test_nonstandard_map_requires_exact_image_checksum_size_and_reset(self):
        for mapping in ('lorom','hirom'):
            offset=0x7fc0 if mapping=='lorom' else 0xffc0
            original=bytearray(snes(mapping=mapping));original[offset+21]=ord('S')
            original[0]=0x18;original[0x8000]=0x78
            # Checksum/complement pairs always contribute 510 to the byte sum.
            original[offset+28:offset+32]=bytes.fromhex('ffff0000')
            checksum=sum(original)&0xffff
            original[offset+28:offset+30]=(checksum^0xffff).to_bytes(2,'little')
            original[offset+30:offset+32]=checksum.to_bytes(2,'little')
            path=self.source('Nonstandard.sfc',original)
            self.assertEqual(conversion_rom(path,'snes').mapping,mapping)
            self.assertEqual(path.read_bytes(),original)
            for address,value in ((100,1),(offset+23,7),(offset+21,0x23),
                                  (offset+22,0x13),(0 if mapping=='lorom' else 0x8000,0)):
                broken=bytearray(original);broken[address]=value
                # Even repairing the full checksum does not admit a foreign
                # mapping/circuit, wrong length or implausible reset opcode.
                broken[offset+28:offset+32]=bytes.fromhex('ffff0000')
                checksum=sum(broken)&0xffff
                broken[offset+28:offset+30]=(checksum^0xffff).to_bytes(2,'little')
                broken[offset+30:offset+32]=checksum.to_bytes(2,'little')
                if address==100:broken[101]^=1 # stale checksum must reject
                with self.assertRaises(ConversionError):conversion_rom(self.source('Invalid.sfc',broken),'snes')

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

    def test_unknown_rom_gets_its_own_profile_without_a_catalogue_entry(self):
        from smsrecomp import megadrive, supernintendo
        for system, path in (('md', self.source('Game.md', md())),
                             ('snes', self.source('Game.sfc', snes()))):
            adapter = megadrive if system == 'md' else supernintendo
            rom = conversion_rom(path, system)
            self.assertNotIn(rom.sha256, adapter.PROFILES)
            profile = adapter.profile_for(rom)
            self.assertEqual(profile['source'], 'cartridge')
            self.assertEqual(profile['id'], 'rom-' + rom.sha256)
            self.assertEqual(profile['title'], rom.title)
            self.assertFalse(profile.get('sonic', profile.get('legacy_functions')))
            original = path.read_bytes()
            changed = bytearray(original); changed[0x300] ^= 1
            other = conversion_rom(self.source('Other' + path.suffix, changed), system)
            self.assertNotEqual(adapter.profile_for(other)['id'], profile['id'])
            self.assertEqual(path.read_bytes(), original)

    def test_z80_timing_budget_rejects_shared_native_reference_error(self):
        for native, reference in ((1, 0), (0, 1), (1, 1), (0, None)):
            self.assertIn('z80_timing_budget', reference_differences('md',
                {'z80_timing_misses': native}, {'z80_timing_misses': reference}))
        self.assertNotIn('z80_timing_budget', reference_differences('md',
            {'z80_timing_misses': 0}, {'z80_timing_misses': 0}))
        self.assertNotIn('z80_timing_budget', reference_differences('snes',
            {'z80_timing_misses': 1}, {'z80_timing_misses': 1}))

    def test_md_compares_retirement_without_hiding_an_active_fallback(self):
        native = {'native_entries': 4, 'interpreted_opcodes': 0, 'retired_interpreted_opcodes': 0}
        reference = {'native_entries': 0, 'interpreted_opcodes': 5, 'retired_interpreted_opcodes': 4}
        self.assertNotIn('retired_instruction_count', reference_differences('md', native, reference))
        self.assertEqual(reference['interpreted_opcodes'], 5)
        for retired in (3, 5, None):
            changed = dict(reference, retired_interpreted_opcodes=retired)
            self.assertIn('retired_instruction_count', reference_differences('md', native, changed))
        del reference['retired_interpreted_opcodes']
        self.assertIn('retired_instruction_count', reference_differences('md', native, reference))
        self.assertIn('retired_instruction_count', reference_differences('snes', native, reference))

    def test_unsupported_16bit_hardware_rejected_before_dependencies(self):
        payload = bytearray(snes()); payload[0x7fd6] = 0x13
        with patch('smsrecomp.console16.dependencies16') as dependencies:
            from smsrecomp.console16 import prepare16
            with self.assertRaisesRegex(ConversionError, 'enhancement chip'):
                prepare16(self.source('SuperFX.sfc', payload), 'snes')
            large = md() + bytes(0x400000)
            with self.assertRaisesRegex(ConversionError, 'bank mapper'):
                prepare16(self.source('Banked.md', large), 'md')
            payload = bytearray(md()); payload[0x100:0x110] = b'SEGA 32X'.ljust(16, b' ')
            with self.assertRaisesRegex(ConversionError, '32X'):
                prepare16(self.source('32X.md', payload), 'md')
            dependencies.assert_not_called()

    def test_eeprom_save_limitation_does_not_disable_game_conversion(self):
        from smsrecomp import megadrive
        payload = bytearray(md()); payload[0x1b0:0x1b4] = b'RA\xe8\x40'
        rom = conversion_rom(self.source('EEPROM.md', payload), 'md')
        self.assertIn('EEPROM', megadrive.profile_for(rom)['limitations'][0])

    def test_unknown_snes_lorom_hirom_and_regions_use_instruction_maps(self):
        from smsrecomp import supernintendo
        for mapping in ('lorom', 'hirom'):
            for region, standard in ((1, 'ntsc'), (2, 'pal')):
                with self.subTest(mapping=mapping, standard=standard):
                    path = self.source('Unknown.sfc', snes(region, mapping, fast=True))
                    rom = conversion_rom(path, 'snes')
                    self.assertEqual(supernintendo.video_standard(rom), standard)
                    supernintendo.write_profile(self.root, rom, 'Unknown')
                    header = (self.root / 'retro_snes_game.h').read_text()
                    self.assertIn('#define RR_SN_SMW 0', header)
                    self.assertIn(f'#define RR_SN_PAL {int(standard == "pal")}', header)
                    self.assertIn(rom.sha256, (self.root / 'generated/instruction_program.c').read_text())

    def scan_conversion(self, *, advanced, fail_reference=False, learn_new=True, learned_scenario='advanced'):
        """Exercise real conversion scheduling/gates with authored probe results."""
        project = self.root / 'project'
        executable = project / 'build/Release/game.exe'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'authored test executable')
        source = self.source('Authored.md', md())
        rom = read_megadrive_rom(source)
        events = []
        scripts = {}
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
                if reference:
                    self.assertEqual(input_script.read_bytes(), scripts[scenario])
                else:
                    scripts[scenario] = input_script.read_bytes()
            fields = MD_AUDIO_FIELDS + MD_SRAM_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped','cpu_prefetch_hash',
                'frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash',
                'cpu_pc', 'vsram_hash', 'vdp_register_hash')
            # Later real attract scenes first reached new code after 18,000
            # frames. An authored branch at 20,366 verifies that the ordinary
            # advanced scan discovers it and validates it before learning.
            reached = scenario != 'demo' or frames >= 20366
            fallback = int(learn_new and reached and scenario == learned_scenario and pass_number == 1)
            data = dict.fromkeys(fields, 1)
            data.update(scenario=scenario, frames=frames, native_entries=0 if reference else 100 - fallback,
                interpreted_opcodes=100 if reference else fallback,
                audio_native_opcodes=0 if reference else 200, audio_interpreted_opcodes=200 if reference else 0,
                audio_native_cycles=0 if reference else 800, audio_interpreted_cycles=800 if reference else 0,
                rom_entries=[{'offset': 42}] if fallback else [], audio_cpu='native')
            failed_scenario = fail_reference if isinstance(fail_reference, str) else 'advanced'
            if fail_reference and reference and (not advanced or scenario == failed_scenario):
                data['cpu_hash'] = 2
            return data

        def learn(rom, checks):
            events.append('learn')
            return int(any(check['rom_entries'] for check in checks))

        with patch('smsrecomp.console16.prepare16', side_effect=prepare), \
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
        self.assertEqual(events[:12], ['build', 'native:demo', 'native:play', 'native:advanced', 'native:early-start',
                                      'native:menu-confirm', 'reference:demo', 'reference:play', 'reference:advanced',
                                      'reference:early-start', 'reference:menu-confirm', 'learn'])
        self.assertEqual(events.count('build'), 2)
        self.assertEqual([check['frames'] for check in report['final_checks']], [24000, 30, 6000, 1800, 6000])
        self.assertEqual(report['native_percentage'], [100.0] * 5)
        self.assertEqual(report['advanced_scan']['additional_frames'], 37770)
        self.assertEqual(report['advanced_scan']['demo_frames'], 24000)
        self.assertTrue(report['advanced_scan']['reference_before_learning'])
        self.assertTrue(report['native_validation']['passed'])
        self.assertEqual(datetime.fromisoformat(report['created_utc']).tzinfo, timezone.utc)

    def test_standard_md_scan_keeps_two_scenarios(self):
        events, report = self.scan_conversion(advanced=False)
        self.assertEqual(events.count('build'), 1)
        self.assertNotIn('native:advanced', events)
        self.assertFalse(report['advanced_scan']['enabled'])
        self.assertEqual([check['frames'] for check in report['final_checks']], [30, 30])
        self.assertEqual(events[:5], ['build', 'native:demo', 'native:play', 'reference:demo', 'reference:play'])
        self.assertTrue(report['native_validation']['reference_before_learning'])
        self.assertEqual(report['status'], 'supported')
        self.assertEqual(report['cartridge_profile']['source'], 'cartridge')
        self.assertFalse(report['cartridge_profile']['catalogue_required'])

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
            from smsrecomp.snes_cart import REPORT_FIELDS
            fields = SNES_AUDIO_FIELDS + REPORT_FIELDS + ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash',
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
            with patch('smsrecomp.console16.prepare16', side_effect=prepare), \
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
                    self.assertEqual(report['status'], 'supported')
                    self.assertEqual(report['audio_native_percentage'], [100.0, 100.0])
                    self.assertTrue(report['native_validation']['audio_pcm_match'])
                    self.assertTrue(report['native_validation']['reference_before_learning'])

    def test_failed_advanced_reference_never_teaches_the_library(self):
        self.scan_conversion(advanced=True, fail_reference=True)

    def test_late_attract_path_is_validated_before_learning_and_regeneration(self):
        events, report = self.scan_conversion(advanced=True, learned_scenario='demo')
        self.assertEqual(events.count('build'), 2)
        self.assertLess(events.index('reference:demo'), events.index('learn'))
        self.assertEqual(report['native_percentage'], [100.0] * 5)
        self.assertEqual(report['native_validation']['reference_frames'], 24000)

    def test_failed_long_attract_reference_never_teaches_the_library(self):
        self.scan_conversion(advanced=True, fail_reference='demo', learned_scenario='demo')

    def test_early_start_is_validated_before_learning_and_regeneration(self):
        events, report = self.scan_conversion(advanced=True, learned_scenario='early-start')
        self.assertEqual(events.count('build'), 2)
        self.assertLess(events.index('reference:early-start'), events.index('learn'))
        self.assertEqual(report['native_percentage'], [100.0] * 5)

    def test_failed_early_start_reference_never_teaches_the_library(self):
        self.scan_conversion(advanced=True, fail_reference='early-start')

    def test_menu_confirmation_paths_are_validated_before_learning(self):
        events, report = self.scan_conversion(advanced=True, learned_scenario='menu-confirm')
        self.assertEqual(events.count('build'), 2)
        self.assertLess(events.index('reference:menu-confirm'), events.index('learn'))
        self.assertEqual(report['native_percentage'], [100.0] * 5)

    def test_failed_menu_confirmation_reference_never_teaches_the_library(self):
        self.scan_conversion(advanced=True, fail_reference='menu-confirm')

    def test_menu_confirmation_releases_a_and_c_before_exploring_directions(self):
        for frames in (30, 6000):
            rows = [tuple(map(int, line.split())) for line in
                    _md_menu_confirm_script(self.root, frames).read_text().splitlines()]
            self.assertEqual(rows[0], (0, 0, 0))
            self.assertTrue(all(frame < frames and p2 == 0 for frame, _, p2 in rows))
            events = {frame: p1 for frame, p1, _ in rows}
            for frame, buttons in events.items():
                if buttons & 80 and frame + 3 < frames:
                    self.assertEqual(events[frame + 3] & 80, 0)
                    self.assertEqual(buttons & 80, 16 if (frame // 60) % 2 else 64)
            if frames == 6000:
                self.assertTrue(any(buttons & 16 for _, buttons, _ in rows))
                self.assertTrue(any(buttons & 64 for _, buttons, _ in rows))
                self.assertTrue(all(not buttons & 15 for frame, buttons, _ in rows if frame < 2000))
                self.assertTrue(any(buttons & 15 for _, buttons, _ in rows))

    def test_early_start_uses_fresh_boot_inputs_with_released_start(self):
        for frames in (30, 1800):
            script = _md_early_start_script(self.root, frames)
            rows = [tuple(map(int, line.split())) for line in script.read_text().splitlines()]
            self.assertEqual(rows[0], (0, 0, 0))
            self.assertTrue(all(0 <= frame < frames and p2 == 0 for frame, p1, p2 in rows))
            self.assertEqual([row[0] for row in rows], sorted(set(row[0] for row in rows)))
            self.assertEqual(rows[1:3], [(10, 128, 0), (12, 0, 0)])
        self.assertTrue(any(p1 & 8 and p1 & 64 for frame, p1, p2 in rows))

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
                    conversion_rom(path, 'md', 'ntsc')
            profile.assert_not_called()

    def test_md_timing_uses_header_without_requiring_revision_qualification(self):
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
            self.assertEqual(video_standard(rom, 'pal'), 'pal')
        with patch('smsrecomp.megadrive.profile_for', return_value={'standards': ('ntsc', 'pal')}):
            self.assertEqual(video_standard(rom, 'pal'), 'pal')

    def test_md_unknown_region_rejected_before_profile_analysis(self):
        with patch('smsrecomp.megadrive.profile_for') as profile:
            for override in (None, 'ntsc'):
                with self.assertRaisesRegex(ConversionError, 'unrecognized region'):
                    conversion_rom(self.source('Game (USA).md', md(b'???')), 'md', override)
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
        fields = MD_AUDIO_FIELDS + MD_SRAM_FIELDS + SNES_AUDIO_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped','cpu_prefetch_hash', 'frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash',
                  'cpu_pc', 'vsram_hash', 'vdp_register_hash', 'oam_hash', 'high_oam_hash',
                  'apu_ram_hash', 'cpu_cycles', 'master_cycles', 'apu_cycles',
                  'visible_width', 'visible_height', 'active_raster_height', 'interlace_mode',
                  'output_row_density', 'captured_rows', 'video_modes_seen', 'interlace_frames', 'field_parity')
        fields += ('sram_mapping',)
        from smsrecomp.snes_chips import REPORT_FIELDS
        fields += REPORT_FIELDS
        native = dict.fromkeys(fields, 1) | {'native_entries': 100, 'interpreted_opcodes': 0,
            'audio_native_opcodes': 90, 'audio_interpreted_opcodes': 10,
            'audio_native_cycles': 900, 'audio_interpreted_cycles': 100}
        reference = native | {'native_entries': 0, 'interpreted_opcodes': 100,
            'audio_native_opcodes': 0, 'audio_interpreted_opcodes': 100,
            'audio_native_cycles': 0, 'audio_interpreted_cycles': 1000}
        for system, key in (('md', 'vdp_register_hash'), ('md', 'fm_hash'), ('md', 'ym_timer_hash'),
                            ('md', 'z80_ram_hash'), ('md', 'console_version'), ('md', 'cpu_usp'), ('md', 'cpu_ssp'),
                            ('md', 'cpu_stopped'), ('md','cpu_prefetch_hash'), ('md', 'sram_hash'), ('md', 'sram_bytes'),
                            ('md', 'sram_control'), ('md', 'captured_rows'), ('md', 'visible_height'),
                            ('md', 'active_raster_height'), ('md', 'interlace_frames'),
                            ('snes', 'sram_hash'), ('snes', 'sram_bytes'), ('snes', 'sram_mapping'),
                            ('snes', 'master_cycles'), ('snes', 'oam_hash'),
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

    def test_md_bus_budget_rejects_shared_timing_errors(self):
        # The other missing fields are irrelevant to this independent guard.
        self.assertNotIn('bus_timing_budget', reference_differences('md',
            {'bus_budget_misses': 0}, {'bus_budget_misses': 0}))
        for native, reference in ((1, 1), (1, 0), (0, 1), (None, 0), (0, None)):
            self.assertIn('bus_timing_budget', reference_differences('md',
                {'bus_budget_misses': native}, {'bus_budget_misses': reference}))
        self.assertIn('bus_timing_budget', reference_differences('md',
            {'bus_budget_misses': 0}, {}))
        self.assertNotIn('bus_timing_budget', reference_differences('md', {}, {}))
        self.assertNotIn('bus_timing_budget', reference_differences('snes',
            {'bus_budget_misses': 1}, {'bus_budget_misses': 1}))
