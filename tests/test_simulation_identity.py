"""The simulation identity (retrorecomp/simulation_identity.py): what it hashes, what it never hashes.

No ROM and no build: the generated sources are small texts written here. The same checks on real conversions
of an authored program are tools/simulation_identity_selftest.py."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import simulation_identity as identity
from retrorecomp.report_schema import OPTIONAL_ON_DISK, REQUIRED_KEYS, read_report, with_schema_v2
from retrorecomp.systems import ALL_PROFILES, OptionKey, SimulationSource, get_profile

ROM = 'a' * 64
ENGINE = {'files': 2, 'pins': {'zzrecomp': 'abc'}, 'sha256': 'e' * 64}


class FakeProfile:
    id = 'zz'
    emulated = ''
    option_keys = (OptionKey('zz_ram', kind='choice', choices=(128, 256), default=256, changes_run=True),
                   OptionKey('zz_scan'), OptionKey('zz_bios', signature=False, kind='path'))
    simulation_sources = (SimulationSource('generated/*.c'),
                          SimulationSource('game.h', drop=('ZZ_TITLE', 'ZZ_VERSION')),
                          SimulationSource('CMakeLists.txt', keep=r'ZZ_(?:PAL|MAPPER)=\d+'))

    def simulation_files(self, project):
        return self.simulation_sources


def project(folder: Path, *, title='A Game', line_end='\n', pal=0, body='x = 1;', extra=None) -> Path:
    """A build project as a converter leaves it: translated code, a header that mixes the title with run settings,
    a CMake file with paths, and the files that must never count."""
    root = Path(folder)
    (root / 'generated').mkdir(parents=True, exist_ok=True)
    files = {'generated/b.c': f'/* second */{line_end}{body}{line_end}',
             'generated/a.c': f'/* first */{line_end}y = 2;{line_end}',
             'game.h': (f'#define ZZ_TITLE "{title}"{line_end}#define ZZ_VERSION "1.2.3"{line_end}'
                        f'#define ZZ_RAM_KB 64{line_end}'),
             'CMakeLists.txt': (f'set(GAME_DIR "{root.as_posix()}"){line_end}'
                                f'target_compile_definitions(game PRIVATE ZZ_PAL={pal} ZZ_MAPPER=4 RR_VERSION="1.2.3"){line_end}'),
             'embedded_rom.c': 'const unsigned char rom[] = {1,2,3};\n', 'game.ico': 'icon', 'game_resources.rc': title,
             'build/CMakeCache.txt': root.as_posix(), **(extra or {})}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
    return root


def record(folder, options=None, *, engine=ENGINE, rom=ROM, profile=None):
    return identity.compute(profile or FakeProfile(), rom, options or {}, folder, engine=engine)


class SimulationIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_same_inputs_same_identity_whatever_the_folder(self):
        first = record(project(self.root / 'one'))
        second = record(project(self.root / 'elsewhere' / 'deeper'))
        self.assertEqual(len(first['identity']), 64)
        self.assertEqual(first, second)
        self.assertTrue(identity.same_simulation(first, second))
        self.assertEqual(first['sources']['files'], 4)

    def test_title_version_icon_resources_and_build_tree_never_count(self):
        first = record(project(self.root / 'one', title='A Game'))
        other = record(project(self.root / 'two', title='Another Name', extra={
            'game.ico': 'another icon', 'cover.png': 'a cover', 'build/x.c': 'int stale;', 'notices.txt': 'text'}))
        self.assertEqual(first['identity'], other['identity'])

    def test_line_ends_are_normalised(self):
        self.assertEqual(record(project(self.root / 'lf'))['identity'],
                         record(project(self.root / 'crlf', line_end='\r\n'))['identity'])

    def test_generated_code_counts(self):
        first = record(project(self.root / 'one'))
        self.assertNotEqual(first['identity'], record(project(self.root / 'two', body='x = 2;'))['identity'])
        # One more generated file, or the same text under another name.
        self.assertNotEqual(first['identity'],
                            record(project(self.root / 'three', extra={'generated/c.c': 'z = 3;\n'}))['identity'])
        moved = project(self.root / 'four')
        (moved / 'generated' / 'b.c').rename(moved / 'generated' / 'd.c')
        self.assertNotEqual(first['identity'], record(moved)['identity'])

    def test_a_kept_value_of_a_mixed_file_counts_and_its_other_lines_do_not(self):
        first = record(project(self.root / 'one'))
        self.assertNotEqual(first['identity'], record(project(self.root / 'pal', pal=1))['identity'])
        entries = dict(identity.source_entries(self.root / 'one', FakeProfile.simulation_sources))
        self.assertEqual(entries['CMakeLists.txt'], b'ZZ_PAL=0\nZZ_MAPPER=4')
        self.assertEqual(entries['game.h'], b'#define ZZ_RAM_KB 64\n')

    def test_files_are_ordered_by_relative_path(self):
        entries = identity.source_entries(project(self.root / 'one'), tuple(reversed(FakeProfile.simulation_sources)))
        self.assertEqual([name for name, _ in entries], ['CMakeLists.txt', 'game.h', 'generated/a.c', 'generated/b.c'])

    def test_engine_stamp_rom_and_run_options_count(self):
        folder = project(self.root / 'one')
        first = record(folder)
        self.assertNotEqual(first['identity'], record(folder, engine={**ENGINE, 'sha256': 'f' * 64})['identity'])
        self.assertNotEqual(first['identity'], record(folder, rom='b' * 64)['identity'])
        self.assertNotEqual(first['identity'], record(folder, {'zz_ram': 128})['identity'])
        self.assertNotEqual(first['identity'], record(folder, {'standard_override': 'pal'})['identity'])

    def test_default_and_spelling_of_a_run_option(self):
        folder = project(self.root / 'one')
        first = record(folder)
        self.assertEqual(first['options'], {'standard_override': None, 'zz_ram': 256})
        self.assertEqual(first['identity'], record(folder, {'zz_ram': 256})['identity'])
        self.assertEqual(first['identity'], record(folder, {'zz_ram': '256'})['identity'])

    def test_other_options_never_count(self):
        folder = project(self.root / 'one')
        first = record(folder)
        other = record(folder, {'zz_scan': True, 'zz_bios': 'D:/Firmware/bios.bin', 'language': 'fr', 'title': 'T',
                                'cover': 'C:/covers/x.png', 'use_cover': False, 'online_cover': False, 'passes': 9,
                                'frames': 12345, 'scan_level': 'thorough', 'output': 'D:/Games'})
        self.assertEqual(first, other)

    def test_no_identity_rather_than_a_weaker_one(self):
        empty = self.root / 'empty'
        empty.mkdir()
        for folder, reason in ((None, 'names no build project'), (empty, 'no generated source was found')):
            with self.subTest(reason=reason):
                result = record(folder)
                self.assertIsNone(result['identity'])
                self.assertIsNone(result['sources'])
                self.assertIn(reason, result['reason'])
                self.assertFalse(identity.same_simulation(result, result))
        nothing = FakeProfile()
        nothing.simulation_sources = ()
        self.assertIn('lists no generated source', record(project(self.root / 'one'), profile=nothing)['reason'])

    def test_an_emulated_machine_has_an_identity_without_sources(self):
        emulated = FakeProfile()
        emulated.emulated = 'An emulator runs the game.'
        emulated.simulation_sources = ()
        first = record(None, profile=emulated)
        self.assertEqual(first['sources']['files'], 0)
        self.assertEqual(len(first['identity']), 64)
        self.assertNotEqual(first['identity'], record(None, {'zz_ram': 128}, profile=emulated)['identity'])

    def test_same_simulation_needs_two_identities(self):
        first = record(project(self.root / 'one'))
        self.assertFalse(identity.same_simulation(first, None))
        # A record of another schema (1 hashed the game stamp) is never comparable.
        self.assertFalse(identity.same_simulation(first, {**first, 'schema': 1}))
        self.assertFalse(identity.same_simulation({**first, 'identity': None}, {**first, 'identity': None}))

    def test_the_engine_content_of_the_machine_is_used(self):
        profile = get_profile('sms')
        folder = self.root / 'sms'
        (folder / 'generated').mkdir(parents=True)
        (folder / 'generated' / 'game_banked_index.c').write_text('int positions;\n', encoding='ascii')
        result = identity.compute(profile, ROM, {}, folder)
        self.assertEqual(result['engine'], identity.engine_content('sms'))
        self.assertEqual(result['sources']['files'], 1)
        self.assertEqual(len(result['identity']), 64)

    def test_an_unreadable_pin_gives_no_identity(self):
        folder = project(self.root / 'one')
        with mock.patch.object(identity, 'engine_pins', return_value={'zzrecomp': None}):
            result = identity.compute(FakeProfile(), ROM, {}, folder)
        self.assertIsNone(result['identity'])
        self.assertIn('zzrecomp', result['reason'])

    def test_for_conversion_reads_the_project_the_report_names(self):
        build = self.root / '.build'
        game = project(build / ('sms_A_Game_0000ABCD_' + ROM[:12] + '_banked'))
        report = {'build_directory': str(game), 'title': 'A Game', 'artwork': {'embedded': True},
                  'published_directory': 'D:/Games/Master System'}
        profile = FakeProfile()
        profile.id = 'sms'
        with mock.patch.object(identity, 'engine_content', return_value=ENGINE):
            first = identity.for_conversion(profile, ROM, {}, report, root=self.root)
            other = identity.for_conversion(profile, ROM, {}, {**report, 'title': 'B', 'artwork': {'embedded': False},
                                                                'published_directory': 'E:/Elsewhere'}, root=self.root)
            outside = identity.for_conversion(profile, ROM, {}, {'build_directory': str(self.root / 'not-a-project')},
                                              root=self.root)
        self.assertEqual(len(first['identity']), 64)
        self.assertEqual(first, other)
        self.assertIsNone(outside['identity'])


class EngineContentTest(unittest.TestCase):
    """The engine part: files and pins of one source tree, never the bytecode of a Python module."""

    def test_only_game_role_files_in_manifest_order(self):
        from retrorecomp.compilation_inputs import manifest_names, role
        for system in ('sms', 'md', 'cps2', 'x68', 'scummvm'):
            with self.subTest(machine=system):
                names = [name for name, _ in identity.engine_files(system)]
                self.assertTrue(names)
                self.assertFalse([name for name in names if name.startswith('retrorecomp')])
                self.assertFalse([name for name in names if role(name) != 'game'])
                self.assertFalse([name for name in names if name.startswith('native/hostkit/')])
                self.assertEqual(names, [name for name in manifest_names(system) if name in set(names)])

    def test_a_file_is_hashed_with_lf_line_ends(self):
        import hashlib
        from retrorecomp.compilation_inputs import input_bytes
        from retrorecomp.paths import ASSETS
        name, digest = next(entry for entry in identity.engine_files('sms') if entry[0].endswith(('.c', '.h', '.inc')))
        data = (ASSETS / name).read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())
        self.assertEqual(data, input_bytes(ASSETS / name, name))

    def test_every_machine_reads_its_pins_as_the_upstreams_page_does(self):
        from retrorecomp import upstreams
        for profile in ALL_PROFILES:
            with self.subTest(machine=profile.id):
                pins = identity.engine_pins(profile.id)
                expected = {item.key: upstreams.read_pin(item.pin) for item in upstreams.MACHINE_UPSTREAMS[profile.id]
                            if item.pin.kind != 'submodule'}
                self.assertEqual(pins, expected)
                self.assertTrue(pins)
                self.assertTrue(all(isinstance(value, str) and value for value in pins.values()))
                content = identity.engine_content(profile.id)
                self.assertEqual(len(content['sha256']), 64)
                self.assertEqual(content['pins'], pins)

    def test_a_pin_is_read_from_the_module_when_the_source_is_not_on_disk(self):
        from retrorecomp import upstreams
        pin = upstreams.MACHINE_UPSTREAMS['md'][0].pin
        self.assertEqual(pin.kind, 'dict')
        from_source = (upstreams.read_pin(pin), upstreams.read_pin(upstreams.MACHINE_UPSTREAMS['sms'][0].pin))
        self.assertTrue(all(from_source))
        with mock.patch.object(upstreams, 'read_pin', return_value=None):
            self.assertEqual((identity._pin_text(pin), identity._pin_text(upstreams.MACHINE_UPSTREAMS['sms'][0].pin)),
                             from_source)

    def test_a_file_or_a_pin_changes_the_content_and_python_modules_do_not_enter_it(self):
        first = identity.engine_content('sms')
        files = identity.engine_files('sms')
        changed = [(files[0][0], '0' * 64), *files[1:]]
        with mock.patch.object(identity, 'engine_files', return_value=changed):
            self.assertNotEqual(first['sha256'], identity.engine_content('sms')['sha256'])
        with mock.patch.object(identity, 'engine_pins', return_value={**first['pins'], 'smsggrecomp': 'another'}):
            self.assertNotEqual(first['sha256'], identity.engine_content('sms')['sha256'])
        # The game stamp's module fingerprints are never asked for.
        with mock.patch('retrorecomp.compilation_inputs.code_fingerprint', side_effect=AssertionError), \
                mock.patch('retrorecomp.compilation_inputs._code_digest', side_effect=AssertionError):
            self.assertEqual(first, identity.engine_content('sms'))


class ProfileDeclarationsTest(unittest.TestCase):
    def test_every_recompiled_machine_lists_its_sources(self):
        for profile in ALL_PROFILES:
            with self.subTest(machine=profile.id):
                if getattr(profile, 'emulated', ''):
                    self.assertEqual(profile.simulation_sources, ())
                else:
                    self.assertTrue(profile.simulation_sources)

    def test_patterns_are_relative_and_never_name_what_must_not_count(self):
        banned = ('.ico', '.png', '.bmp', '.rc', 'notices', 'legal', 'hostkit', 'build/', 'artwork', 'cover', '.log',
                  'retro16_state_config', 'runtime_feedback', 'blob-', '.bin', '.rom', '.pack', '.zip')
        for profile in ALL_PROFILES:
            for source in profile.simulation_sources:
                with self.subTest(machine=profile.id, pattern=source.pattern):
                    self.assertFalse(source.pattern.startswith(('/', '\\')) or ':' in source.pattern
                                     or '\\' in source.pattern or '..' in source.pattern.split('/'))
                    self.assertFalse(any(word in source.pattern.lower() for word in banned))
                    self.assertFalse(source.drop and source.keep)
                    self.assertTrue(all(source.drop))
                    re.compile(source.keep)

    def test_a_file_that_embeds_the_rom_is_only_read_for_named_values(self):
        for profile in ALL_PROFILES:
            for source in profile.simulation_sources:
                if 'embedded_rom' in source.pattern:
                    self.assertTrue(source.keep, profile.id)

    def test_run_options_are_values_never_paths(self):
        declared = {}
        for profile in ALL_PROFILES:
            for key in profile.option_keys:
                if key.changes_run:
                    self.assertNotIn(key.kind, ('path', 'count', 'plan', 'action'), key.name)
                    self.assertTrue(key.signature, key.name)
                    self.assertIsNotNone(key.default, key.name)
                    declared.setdefault(profile.id, []).append(key.name)
        self.assertEqual(declared, {'x68': ['x68_ram'], 'atarist': ['atarist_timer_d'], 'scummvm': ['scummvm_choice'],
                                    'msx2': ['msx2_ram'], 'msx2plus': ['msx2plus_ram']})

    def test_the_pc_engine_names_the_module_its_build_compiled(self):
        profile = get_profile('pce')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(profile.simulation_files(root), ())
            (root / 'n').mkdir()
            (root / 'n' / 'pce_game.h').write_text('#define RR_PCE_TITLE "T"\n#define RR_PCE_VERSION "1"\n'
                                                   '#define RR_PCE_PAD_BUTTONS 2\n', encoding='ascii')
            for number in (1, 2, 3):
                (root / f'module-{number}').mkdir()
                (root / f'module-{number}' / 'module.cpp').write_text(f'int pass{number};\n', encoding='ascii')
            (root / 'n' / 'CMakeLists.txt').write_text(
                f'pce_add_native_module(PCE_MODULE MODULE "{root.as_posix()}/module-2/module.cpp" '
                f'MANIFEST "{root.as_posix()}/module-2/module.json")\n', encoding='utf-8')
            names = [name for name, _ in identity.source_entries(root, profile.simulation_files(root))]
            self.assertEqual(names, ['module-2/module.cpp', 'n/pce_game.h'])
            (root / 'n' / 'CMakeLists.txt').write_text(
                'pce_add_native_module(PCE_MODULE MODULE "C:/engine/runtime/src/no_module.cpp")\n', encoding='utf-8')
            names = [name for name, _ in identity.source_entries(root, profile.simulation_files(root))]
            self.assertEqual(names, ['n/pce_game.h'])


class ReportFieldTest(unittest.TestCase):
    """`simulation_identity` in report schema 2: optional, additive, no new schema number."""

    def report(self):
        # The Master System writer's shape, as the report tests build it.
        from tests.test_report_schema import sms_report
        return sms_report()

    def test_it_is_optional_on_disk(self):
        self.assertIn('simulation_identity', REQUIRED_KEYS)
        self.assertIn('simulation_identity', OPTIONAL_ON_DISK)

    def test_absent_reads_none_and_a_record_is_kept(self):
        legacy = self.report()
        document = with_schema_v2(legacy)
        self.assertNotIn('simulation_identity', document)
        self.assertIsNone(read_report(document)['simulation_identity'])
        self.assertIsNone(read_report(legacy)['simulation_identity'])
        value = {'schema': 2, 'identity': 'c' * 64, 'engine': ENGINE, 'rom': ROM, 'options': {'standard_override': None},
                 'sources': {'files': 3, 'sha256': 'd' * 64}, 'reason': None}
        written = with_schema_v2({**legacy, 'simulation_identity': value})
        self.assertEqual(written['simulation_identity'], value)
        self.assertEqual(read_report(written)['simulation_identity'], value)
        # Written again by the batch (it adds its fields and derives the sections anew): unchanged.
        self.assertEqual(with_schema_v2(written)['simulation_identity'], value)
        # Every other section reads as it did without the field.
        plain, withfield = read_report(document), read_report(written)
        self.assertEqual({k: v for k, v in plain.items() if k != 'simulation_identity'},
                         {k: v for k, v in withfield.items() if k != 'simulation_identity'})

    def test_a_value_that_is_not_a_record_reads_none(self):
        legacy = self.report()
        for value in ('c' * 64, 7, ['x'], {'identity': 'c' * 64}, {'schema': 'one'}):
            with self.subTest(value=value):
                self.assertIsNone(read_report(with_schema_v2({**legacy, 'simulation_identity': value}))['simulation_identity'])
        refused = read_report(with_schema_v2({**legacy, 'simulation_identity': {'schema': 1, 'identity': 12, 'reason': 'x'}}))
        self.assertIsNone(refused['simulation_identity']['identity'])


if __name__ == '__main__':
    unittest.main()
