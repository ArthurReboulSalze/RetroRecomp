"""SystemProfile v2: the profiles are the one list of consoles and of what each accepts.

The registries elsewhere in the converter read the profiles; these tests pin
that they still agree, and that the options reaching each console's converter
are exactly the ones the hard-coded branches used to let through.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import (batch, compilation_inputs, feedback, metadata, platforms, scan_levels)
from retrorecomp.systems import (ALL_PROFILES, PROFILES, STATUSES, EXPERIMENTAL_PROFILES, console_option_keys,
                                 drop_foreign_options, find_profile, get_profile, system_ids,
                                 unsigned_option_keys)

REPO = Path(__file__).resolve().parents[1]
IDS = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1')

# The console-specific option keys each console's converter receives.
OPTION_KEYS = {
    'sms': set(), 'gg': set(), 'cps1': set(),
    'gb': {'gb_deep_validation', 'gb_parallel_games'},
    'nes': {'nes_advanced_scan'},
    'md': {'md_advanced_scan'}, 'snes': {'md_advanced_scan'},
    'ng': {'ng_bios', 'ng_qualification_routes', 'ng_parallel_games'},
    'x68': {'x68_ipl', 'x68_cgrom', 'x68_ram'},
}
EVERY_KEY = set().union(*OPTION_KEYS.values())


class RegistryTests(unittest.TestCase):
    def test_nine_profiles_in_the_documented_order(self):
        self.assertEqual(system_ids(), IDS)
        self.assertEqual({profile.id for profile in PROFILES} | {'x68'}, set(IDS))
        for profile in ALL_PROFILES:
            self.assertIs(get_profile(profile.id), profile)
            self.assertIs(find_profile(profile.id), profile)
        self.assertIsNone(find_profile('zx'))
        self.assertTrue(set(EXPERIMENTAL_PROFILES) <= set(ALL_PROFILES))

    def test_every_console_list_equals_the_profiles_list(self):
        ids = set(system_ids())
        self.assertEqual(set(compilation_inputs.SYSTEMS), ids)
        self.assertEqual(tuple(scan_levels.CONSOLES), system_ids())
        self.assertEqual(set(scan_levels.DEFAULT_FRAMES), ids)
        self.assertEqual(set(scan_levels.QUICK_FRAMES), ids)
        self.assertEqual(set(feedback.SYSTEMS), ids)
        self.assertEqual(set(feedback.KINDS), ids)
        spec = importlib.util.spec_from_file_location('std_baseline_registry', REPO / 'tools' / 'std_baseline.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        self.assertEqual(set(baseline.SYSTEMS), ids)
        # RetroRecomp.py's package-qualification hook covers every console too.
        self.assertIn('system_ids()', (REPO / 'RetroRecomp.py').read_text(encoding='utf-8'))

    def test_partial_lists_only_name_known_consoles(self):
        # These lists have their own meaning (a subset, e.g. no gun layout for
        # the X68000); they may never name a console that has no profile.
        from retrorecomp import compiled_games_view, cover_references, cover_sources, game_metadata, knowledge_build, random_routes
        ids = set(system_ids())
        for name, listed in {
            'random_routes.CONSOLES': random_routes.CONSOLES,
            'compiled_games_view.SHARED_CONSOLES': compiled_games_view.SHARED_CONSOLES,
            'knowledge_build.SYSTEMS': knowledge_build.SYSTEMS,
            'cover_references.SYSTEMS': cover_references.SYSTEMS,
            'cover_sources.SS_SYSTEMS': cover_sources.SS_SYSTEMS,
            'cover_sources.TGDB_SYSTEMS': cover_sources.TGDB_SYSTEMS,
            'game_metadata.PLATFORMS': game_metadata.PLATFORMS,
        }.items():
            with self.subTest(name):
                self.assertTrue(set(listed) <= ids, set(listed) - ids)

    def test_feedback_kinds_are_disjoint_and_come_from_the_profiles(self):
        seen = set()
        for profile in ALL_PROFILES:
            self.assertEqual(feedback.KINDS[profile.id], set(profile.feedback_kinds))
            if profile.id != 'gg':  # Game Gear shares kind 1 with the Master System
                self.assertFalse(seen & set(profile.feedback_kinds), profile.id)
            seen |= set(profile.feedback_kinds)
        self.assertEqual(feedback.KINDS['sms'], feedback.KINDS['gg'])

    def test_metadata_reads_the_profile_name_and_standards(self):
        for profile in ALL_PROFILES:
            both = 'ntsc' in profile.video_modes and 'pal' in profile.video_modes
            for standard in (None, *profile.video_modes):
                with self.subTest(profile.id, standard=standard):
                    values = metadata.game_metadata('T', False, standard, profile.id)
                    self.assertEqual(values['Console'], profile.name)
                    expected = profile.name + (f' {standard.upper()}' if standard and both else '')
                    self.assertIn(f'| {expected} |', values['FileDescription'])
            with self.assertRaises(ValueError):
                metadata.game_metadata('T', False, 'secam', profile.id)
        with self.assertRaises(ValueError):
            metadata.game_metadata('T', False, None, 'zx')

    def test_linux_witnessed_consoles(self):
        from retrorecomp.core import ConversionError  # imported before os is replaced
        with patch.object(platforms, 'os', SimpleNamespace(name='posix')):
            for system in IDS:
                if system == 'cps1':
                    with self.assertRaises(ConversionError):
                        platforms.require_backend(system)
                else:
                    platforms.require_backend(system)
            with self.assertRaises(ConversionError):
                platforms.require_backend('zx')
        with patch.object(platforms, 'os', SimpleNamespace(name='nt')):
            platforms.require_backend('cps1')


class ProfileDataTests(unittest.TestCase):
    def test_status_replaces_the_ad_hoc_experimental_attribute(self):
        statuses = {profile.id: profile.status for profile in ALL_PROFILES}
        self.assertEqual(statuses, {'sms': 'supported', 'gg': 'supported', 'gb': 'supported', 'nes': 'supported',
                                    'md': 'supported', 'snes': 'supported', 'ng': 'supported',
                                    'cps1': 'experimental', 'x68': 'experimental'})
        for profile in ALL_PROFILES:
            self.assertIn(profile.status, STATUSES)
            # Read-only compatibility with the former attribute.
            self.assertEqual(profile.experimental, profile.status == 'experimental')
            with self.assertRaises(AttributeError):
                profile.experimental = True

    def test_cpus_and_roles(self):
        for profile in ALL_PROFILES:
            roles = [cpu.role for cpu in profile.cpus]
            self.assertEqual(roles.count('main'), 1, profile.id)
            self.assertTrue(set(roles) <= {'main', 'sound'}, profile.id)
            self.assertTrue(all(cpu.unit in ('cycles', 'instructions') for cpu in profile.cpus), profile.id)
        self.assertEqual([(cpu.arch, cpu.role) for cpu in get_profile('snes').cpus],
                         [('65816', 'main'), ('spc700', 'sound')])
        self.assertEqual(get_profile('snes').cartridge_devices, ('superfx', 'dsp1', 'cx4'))
        self.assertEqual([(cpu.arch, cpu.role) for cpu in get_profile('cps1').cpus],
                         [('m68000', 'main'), ('z80', 'sound')])

    def test_media_capabilities_and_quick_states(self):
        self.assertEqual(get_profile('x68').media_kinds, ('disk',))
        self.assertEqual(get_profile('cps1').media_kinds, ('romset',))
        self.assertTrue(get_profile('x68').capabilities.disks)
        self.assertTrue(get_profile('x68').capabilities.mouse and get_profile('x68').capabilities.keyboard)
        self.assertFalse(get_profile('cps1').capabilities.battery)
        self.assertEqual(get_profile('md').capabilities.guns, ('menacer', 'justifier'))
        self.assertEqual(get_profile('snes').capabilities.guns, ('super_scope',))
        # The shared 16-bit host writes one quick-state family.
        self.assertEqual({get_profile(system).quick_state_family for system in ('md', 'snes', 'ng', 'cps1')},
                         {'rr16'})
        for profile in ALL_PROFILES:
            self.assertTrue(profile.quick_state_family, profile.id)

    def test_gun_pairs_metadata_accepts_are_declared_capabilities(self):
        for system, gun in (('md', 'menacer'), ('md', 'justifier'), ('snes', 'super_scope')):
            self.assertIn(gun, get_profile(system).capabilities.guns)
            metadata.game_metadata('T', False, None, system, gun_device=gun)
        self.assertIn('light_phaser', get_profile('sms').capabilities.guns)
        self.assertIn('zapper', get_profile('nes').capabilities.guns)

    def test_option_keys_per_console(self):
        for system, keys in OPTION_KEYS.items():
            with self.subTest(system):
                self.assertEqual(get_profile(system).option_key_names, keys)
        self.assertEqual(console_option_keys(), EVERY_KEY)
        # Options that only size the work or name firmware never enter a request.
        self.assertEqual(unsigned_option_keys(), {'gb_parallel_games', 'ng_parallel_games', 'ng_bios'})
        parallel = {profile.id: profile.parallel_games_option for profile in ALL_PROFILES
                    if profile.parallel_games_option}
        self.assertEqual(parallel, {'gb': 'gb_parallel_games', 'ng': 'ng_parallel_games'})
        for profile in ALL_PROFILES:
            if profile.parallel_games_option:
                self.assertIn(profile.parallel_games_option, profile.option_key_names)

    def test_drop_foreign_options_keeps_only_the_consoles_own_keys(self):
        for system in IDS:
            with self.subTest(system):
                settings = {key: 1 for key in EVERY_KEY} | {'passes': 3, 'frames': 99, 'backend': 'banked'}
                drop_foreign_options(system, settings)
                self.assertEqual(set(settings), OPTION_KEYS[system] | {'passes', 'frames', 'backend'})


class ProfileContractTests(unittest.TestCase):
    """The data a profile carries equals what the registry elsewhere holds for the console (1.6.3, package P1).

    The registries still hold their own copy; these tests fail when the two disagree, so that the registries
    can later read the profile instead without a change of result."""

    def test_path_spec_equals_the_paths_schema_tables(self):
        from retrorecomp import path_profiles
        for profile in ALL_PROFILES:
            spec = profile.path_spec
            with self.subTest(profile.id):
                self.assertEqual(path_profiles.SYSTEMS[spec.order], profile.id)
                self.assertEqual(spec.sections, path_profiles.SYSTEM_SECTIONS[profile.id])
                self.assertEqual(dict(spec.source_bounds), path_profiles.SOURCE_BOUNDS[profile.id])
                self.assertEqual(spec.required_sources, path_profiles.REQUIRED_SOURCES.get(profile.id, ()))
                self.assertEqual(spec.hashed_sources, path_profiles.HASHED_SOURCES.get(profile.id, ()))
        # The schema's own order (CPS-1 before the X68000) is the profiles' `order`, which is not the documents' order.
        self.assertEqual(tuple(p.id for p in sorted(ALL_PROFILES, key=lambda p: p.path_spec.order)),
                         path_profiles.SYSTEMS)
        self.assertEqual(len({p.path_spec.order for p in ALL_PROFILES}), len(ALL_PROFILES))

    def test_report_shape_equals_the_report_schema_and_the_cpus(self):
        from retrorecomp import report_schema
        for profile in ALL_PROFILES:
            shape = report_schema._SHAPES[profile.id]
            with self.subTest(profile.id):
                self.assertEqual((profile.report_shape.writer, profile.report_shape.marker),
                                 (shape.writer, shape.marker))
                # The architectures and units of the report come from the CPUs, not from a second copy.
                main = next(cpu for cpu in profile.cpus if cpu.role == 'main')
                sound = next((cpu for cpu in profile.cpus if cpu.role == 'sound'), None)
                self.assertEqual((main.arch, main.unit), (shape.main_arch, shape.main_unit))
                self.assertEqual(sound.arch if sound else None, shape.audio_arch)

    def test_catalogues_equal_the_artwork_and_metadata_tables(self):
        from retrorecomp import artwork, cover_references, cover_sources, game_metadata, stamp_inputs
        for profile in ALL_PROFILES:
            catalogues = profile.catalogues
            with self.subTest(profile.id):
                self.assertEqual(catalogues.libretro, artwork.REPOSITORIES.get(profile.id))
                self.assertEqual(catalogues.screenscraper, cover_sources.SS_SYSTEMS.get(profile.id))
                self.assertEqual(catalogues.thegamesdb, cover_sources.TGDB_SYSTEMS.get(profile.id))
                self.assertEqual(set(catalogues.wikidata), set(game_metadata.PLATFORMS.get(profile.id, ())))
                self.assertEqual(catalogues.cover_references, profile.id in cover_references.SYSTEMS)
                if catalogues.local_catalogue:
                    self.assertIn(catalogues.local_catalogue, stamp_inputs.RAW_FILES)
                    self.assertTrue((REPO / catalogues.local_catalogue).is_file())
        self.assertEqual({p.id for p in ALL_PROFILES if p.catalogues.local_catalogue}, {'ng', 'cps1'})

    def test_library_layout_equals_the_library_root_and_the_memory_window(self):
        import os
        from retrorecomp import memory_view
        from retrorecomp.library import library_root
        # Since 1.6.3 the memory window reads the profile's layout itself: one record per console, laid out as
        # the profile says, is found by memory_view.summaries (a console without a reader has none).
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': folder}):
            base = Path(folder).resolve()
            for number, profile in enumerate(ALL_PROFILES, 1):
                layout = profile.library_layout
                with self.subTest(profile.id):
                    self.assertEqual(library_root(profile.id), base / layout.folder if layout.folder else base)
                    if not layout.summary_glob:
                        with self.assertRaises(KeyError):
                            memory_view.summaries(profile.id)
                        continue
                    identity = format(number, 'x').rjust(64, '0')
                    *folders, name = layout.summary_glob.split('/')
                    # The key is in the record's folder name ('folder_suffix') or in the folder above it.
                    parts = [identity if layout.identity == 'grandfolder' and index == 0 else f'title-{identity}'
                             for index, _ in enumerate(folders)]
                    record = library_root(profile.id).joinpath(*parts, name)
                    record.parent.mkdir(parents=True)
                    record.write_text('{"title": "Synthetic"}' if record.suffix == '.json' else 'a\n', encoding='utf-8')
                    rows, _ = memory_view.summaries(profile.id)
                    self.assertEqual([row['identity'] for row in rows], [identity])
        self.assertEqual({p.id for p in ALL_PROFILES if p.library_layout.identity == 'grandfolder'}, {'nes'})
        self.assertEqual({p.id: p.library_layout.companion for p in ALL_PROFILES if p.library_layout.companion},
                         {'sms': 'observations.log', 'gg': 'observations.log', 'gb': 'entries.trace'})

    def test_input_layout_equals_the_random_route_pads_and_scripts(self):
        from retrorecomp import random_routes as routes
        formats = {'console16': routes.console16_script, 'nes': routes.nes_script, 'neogeo': routes.neogeo_script,
                   'cps1': routes.cps1_script, 'gameboy': routes.gameboy_script,
                   'sega': lambda route: '\n'.join(routes.sega_press(route)) + '\n'}
        declared = {p.id for p in ALL_PROFILES if p.input_layout}
        self.assertEqual(declared, set(routes.CONSOLES))
        self.assertIsNone(get_profile('x68').input_layout)  # it plays routes of its own
        for system in sorted(declared):
            layout = get_profile(system).input_layout
            pad = routes.CONSOLES[system]
            with self.subTest(system):
                self.assertEqual((layout.main, layout.extra, layout.select, layout.opening),
                                 (pad['main'], pad['extra'], pad['select'], pad['opening']))
                self.assertEqual(layout.start, pad.get('start', True))
                route = routes.long_route(system, 'ab' * 32, 0)
                self.assertEqual(routes.script_text(route), formats[layout.script_format](route))
                with tempfile.TemporaryDirectory() as folder:
                    written = routes.write_route(route, Path(folder))
                    self.assertEqual(written.name, route.name + layout.script_suffix)

    def test_shared_knowledge_equals_the_sharing_lists(self):
        from retrorecomp import compiled_games_view, knowledge_build, path_profiles
        tiers = {tier: tuple(p.id for p in ALL_PROFILES
                             if p.shared_knowledge and p.shared_knowledge.tier == tier)
                 for tier in ('stable', 'experimental')}
        self.assertEqual(tiers['stable'], path_profiles.STABLE_SHARED)
        self.assertEqual(tiers['experimental'], path_profiles.EXPERIMENTAL_SHARED)
        self.assertEqual(tiers['stable'] + tiers['experimental'], path_profiles.SHARED_SYSTEMS)
        self.assertEqual(tiers['stable'], compiled_games_view.SHARED_CONSOLES)
        self.assertEqual(tuple(p.id for p in ALL_PROFILES if p.shared_knowledge and p.shared_knowledge.site_builder),
                         knowledge_build.SYSTEMS)
        self.assertEqual(tuple(p.id for p in ALL_PROFILES if p.shared_knowledge and p.shared_knowledge.withdrawable),
                         path_profiles.WITHDRAWABLE)
        self.assertIsNone(get_profile('x68').shared_knowledge)

    def test_host_adapter_equals_the_host_kit_table(self):
        from retrorecomp import hostkit
        self.assertEqual({p.id: p.host_adapter for p in ALL_PROFILES if p.host_adapter}, hostkit.ADAPTERS)

    def test_option_keys_say_what_they_are(self):
        from retrorecomp.i18n import STRINGS
        kinds = {'flag', 'path', 'choice', 'count', 'plan'}
        seen = {}
        for profile in ALL_PROFILES:
            for key in profile.option_keys:
                seen[key.name] = key
                with self.subTest(key.name):
                    self.assertIn(key.kind, kinds)
                    if key.label.isidentifier():
                        self.assertIn(key.label, STRINGS)
                    if key.hint:
                        self.assertIn(key.hint, STRINGS)
        self.assertEqual({name for name, key in seen.items() if key.kind == 'count'},
                         {'gb_parallel_games', 'ng_parallel_games'})
        self.assertEqual({name for name, key in seen.items() if key.kind == 'path'},
                         {'ng_bios', 'x68_ipl', 'x68_cgrom'})
        self.assertEqual({name for name, key in seen.items() if key.kind == 'plan'}, {'ng_qualification_routes'})
        self.assertEqual((seen['x68_ram'].choices, seen['x68_ram'].default), ((2, 4), 2))
        # Every firmware the user supplies has a path option named after it (tests/test_machine_registry.py).
        for profile in ALL_PROFILES:
            for firmware in profile.firmware:
                self.assertEqual(seen[f'{profile.id}_{firmware}'].kind, 'path')

    def test_options_tab_is_a_translated_string_of_the_interface(self):
        from retrorecomp.i18n import STRINGS
        for profile in ALL_PROFILES:
            self.assertIn(profile.options_tab, STRINGS, profile.id)
        self.assertEqual({p.id: p.options_tab for p in ALL_PROFILES if p.options_tab != 'options_' + p.id},
                         {'sms': 'options_master_system', 'gg': 'options_game_gear', 'gb': 'options_game_boy'})

    def test_identification_orders_follow_the_documented_priority(self):
        from retrorecomp.systems import registry
        self.assertEqual([p.id for p in registry.path_stage()], ['x68', 'cps1', 'ng'])
        # The iNES signature wins over the Mega Drive one; the Sega region header comes before the SNES map.
        self.assertEqual([p.id for p in registry.content_stage()], ['nes', 'md', 'sms', 'snes', 'gb'])
        self.assertEqual([p.id for p in PROFILES], ['sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1'])
        self.assertEqual([p.id for p in ALL_PROFILES if p.developer_only], ['x68'])
        self.assertEqual(tuple(p.id for p in registry.convertible_profiles()[-1:]),
                         ('x68',) if get_profile('x68').available() else ('cps1',))


class ConvertedOptionsTests(unittest.TestCase):
    """The keyword arguments reaching each converter through batch._convert_one."""

    class Stop(Exception):
        pass

    def run_one(self, system_id, **extra):
        profile = get_profile(system_id)
        seen = {}

        def converter(path, **arguments):
            seen.update(arguments)
            raise self.Stop

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rom = root / 'fixture.bin'
            rom.write_bytes(b'not a ROM')
            cover = root / 'cover.png'
            cover.write_bytes(b'cover')
            for name in ('games', 'reports'):
                (root / name).mkdir()
            item = batch.BatchItem(rom, 'Fixture', system_id, 'ab' * 32, 9, cover=cover, video_hint='ntsc')
            options = {key: ('fixture' if key in ('ng_bios', 'x68_ipl', 'x68_cgrom') else 1) for key in EVERY_KEY}
            options.update({'x68_ram': 2, 'use_cover': False, 'language': 'en', 'passes': 3, **extra})
            messages = []
            with patch.object(profile, 'convert', side_effect=converter), \
                    patch('retrorecomp.neogeo.validate_bios', return_value='bios-stand-in'), \
                    patch('retrorecomp.x68000.machine',
                          return_value=(None, SimpleNamespace(sha256='machine-stand-in'))):
                result = batch._convert_one(0, item, 1, profile, root / 'games', root / 'reports',
                                            root / 'games' / 'Fixture.exe', [], messages.append, options)
        self.assertEqual(result['status'], 'error', (result, messages))
        self.assertEqual(result['message'], '')
        return seen

    def test_each_converter_receives_only_its_own_console_options(self):
        for system in IDS:
            with self.subTest(system):
                seen = self.run_one(system)
                self.assertEqual(EVERY_KEY & set(seen), OPTION_KEYS[system])
                # Shared arguments are the same for every console.
                for name in ('title', 'output', 'cover', 'emit', 'passes', 'frames', 'language', 'use_cover'):
                    self.assertIn(name, seen)
                self.assertEqual(seen.get('publish_result'), False if system in ('sms', 'gg') else None)

    def test_scan_level_rewrites_the_legacy_switches_for_their_consoles(self):
        for system, key in (('md', 'md_advanced_scan'), ('snes', 'md_advanced_scan'), ('nes', 'nes_advanced_scan')):
            for level, expected in (('standard', False), ('extended', True), ('thorough', True), ('quick', False)):
                with self.subTest(system=system, level=level):
                    self.assertIs(self.run_one(system, scan_level=level)[key], expected)
        for system in ('sms', 'gg', 'gb', 'ng', 'x68', 'cps1'):
            self.assertNotIn('md_advanced_scan', self.run_one(system, scan_level='thorough'))
            self.assertNotIn('nes_advanced_scan', self.run_one(system, scan_level='thorough'))

    def test_batch_hands_every_converter_its_worker_count_option(self):
        seen = {}

        def record(parallel, index, item, count, system, game_output, reports, target, previous, emit, options):
            seen.update(options)
            return {'status': 'error', 'message': '', 'rom': str(item.path), 'title': item.title,
                    'system': item.system, 'sha256': item.sha256}

        with tempfile.TemporaryDirectory() as folder,                 patch.object(batch, '_convert_in_budget', side_effect=record):
            rom = Path(folder) / 'Fixture (Europe).sms'
            rom.write_bytes(bytes([7]) * 8192)
            batch.convert_batch([batch.identify(rom)], Path(folder) / 'out', jobs=3, emit=lambda _: None)
        self.assertEqual(seen['gb_parallel_games'], 3)
        self.assertEqual(seen['ng_parallel_games'], 3)
        self.assertEqual({key for key in seen if key.endswith('_parallel_games')},
                         {'gb_parallel_games', 'ng_parallel_games'})


if __name__ == '__main__':
    unittest.main()
