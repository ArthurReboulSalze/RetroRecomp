"""The multiplayer recipe (retrorecomp/netplay_recipe.py): the document, its refusals, recipe mode's isolation, and
the whole route on real conversions of an authored Master System program (tools/netplay_recipe_selftest.py).

No commercial ROM: the only program is authored in the tools. RETRO_RECOMP_LIBRARY_DIR is set only inside the
checks that need it and inside the conversions, never for the suite."""
import copy
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import __version__, feedback, knowledge, netplay_recipe as recipes
from retrorecomp.core import ENGINE_REV, dependencies_ready
from retrorecomp.knowledge_exchange import game_document, import_document
from retrorecomp.simulation_identity import SCHEMA
from retrorecomp.systems import ALL_PROFILES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import netplay_recipe_selftest as selftest   # noqa: E402

PROGRAM = selftest.authored_program()
SHA = hashlib.sha256(PROGRAM).hexdigest()
RECORD = {'engine': ENGINE_REV, 'rom_bytes': len(PROGRAM), 'rom_entries': [[0x200, 0, 1, 2, 0xBE661CED]],
          'pattern_refs': [[293]]}
LIBRARY_VARIABLES = ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE',
                     knowledge.RECIPE_VARIABLE)


def recipe(**changes) -> dict:
    """A recipe written by hand, as `make_recipe` would make it for the authored program."""
    document = {'format': recipes.FORMAT, 'version': recipes.VERSION, 'converter': __version__,
                'created_utc': '2026-11-16T20:00:00+00:00', 'system': 'sms', 'rom_sha256': SHA,
                'name': 'Authored Recipe (Europe)', 'title': 'Authored Recipe', 'options': {'standard_override': None},
                'identity': {'schema': SCHEMA, 'identity': 'c' * 64},
                'paths': game_document('sms', SHA, RECORD, (), 'Authored Recipe')}
    document.update(changes)
    return document


def entries(document: dict) -> dict:
    game = next(iter(document['paths']['knowledge']['games'].values()))
    return game['cpus']['z80']['paths']['entries'][0]['table']


class Environment(unittest.TestCase):
    """A folder of its own and an environment without any library switch; `mode` sets the ones a check needs."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for name in LIBRARY_VARIABLES:
            os.environ.pop(name, None)

    def mode(self, *, library=True, recipe_bank=True):
        if library:
            os.environ['RETRO_RECOMP_LIBRARY_DIR'] = str(self.root / 'library')
        if recipe_bank:
            os.environ[knowledge.RECIPE_VARIABLE] = str(self.root / 'knowledge')

    def refused(self, kind, action, *arguments):
        with self.assertRaises(recipes.RecipeError) as caught:
            action(*arguments)
        self.assertEqual(caught.exception.kind, kind, caught.exception.reason)
        self.assertTrue(caught.exception.reason)
        return caught.exception.reason


class RecipeDocumentTest(Environment):
    def test_every_machine_is_in_or_left_out_with_a_reason(self):
        known = {profile.id for profile in ALL_PROFILES}
        self.assertEqual(set(recipes.MACHINES) | set(recipes.LEFT_OUT), known)
        self.assertFalse(set(recipes.MACHINES) & set(recipes.LEFT_OUT))
        self.assertTrue(all(isinstance(reason, str) and len(reason) > 20 for reason in recipes.LEFT_OUT.values()))
        self.assertEqual(set(recipes._BUILDERS), set(recipes.MACHINES))

    def test_no_stamp_hashes_the_module_and_it_is_published(self):
        from retrorecomp.stamp_inputs import INTERFACE_MODULES
        self.assertIn('netplay_recipe', INTERFACE_MODULES)
        public = (ROOT / 'tools' / 'prepare_publication.py').read_text(encoding='utf-8')
        for name in ('retrorecomp/netplay_recipe.py', 'tests/test_netplay_recipe.py', 'tools/netplay_recipe_selftest.py'):
            self.assertIn(name, public)

    def test_round_trip_as_bytes_and_as_a_file(self):
        document = recipe()
        clean = recipes.validate_recipe(document)
        self.assertEqual(clean, document)
        self.assertEqual(recipes.parse_recipe(recipes.recipe_bytes(document)), clean)
        path = recipes.write_recipe(document, self.root / 'folder' / ('game' + recipes.SUFFIX))
        self.assertEqual(recipes.read_recipe(path), clean)
        self.assertLess(path.stat().st_size, 2048)
        self.assertEqual(recipes.recipe_bytes(document), recipes.recipe_bytes(clean))

    def test_a_recipe_holds_numbers_about_the_rom_and_none_of_its_bytes(self):
        """The paths are schema 3 tables of integers; the document's only texts are names, dates and identities."""
        def texts(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield from texts(item)
            elif isinstance(value, list):
                for item in value:
                    yield from texts(item)
            elif isinstance(value, str):
                yield value
        document = recipes.validate_recipe(recipe())
        allowed = {recipes.FORMAT, 'retro-recomp-knowledge', __version__, document['created_utc'],
                   document['paths']['created_utc'], 'sms', SHA, 'sms:' + SHA, document['name'], document['title'],
                   'c' * 64, ENGINE_REV, 'sega5', 'window4', 'rom', 'list'}
        self.assertEqual(set(texts(document)) - allowed, set())
        self.assertEqual([column['v'] for column in entries(document)['cols']], [[0x200], [0], [1], [2], [0xBE661CED]])

    def test_another_converter_version_is_refused_before_anything_else(self):
        reason = self.refused('converter', recipes.validate_recipe, {'format': recipes.FORMAT, 'converter': '9.9.9',
                                                                    'whatever': 'a newer format'})
        self.assertIn('9.9.9', reason)
        self.assertIn(__version__, reason)
        self.refused('converter', recipes.validate_recipe, recipe(converter='1.0.0'))

    def test_documents_that_do_not_validate(self):
        for bad in (None, [], {}, {'format': 'retro-recomp-knowledge'}, recipe(version=2), recipe(extra=1),
                    recipe(rom_sha256='A' * 64), recipe(rom_sha256=SHA[:63]), recipe(title=''), recipe(title='a\nb'),
                    recipe(created_utc=5), recipe(identity={'schema': SCHEMA, 'identity': 'c' * 63}),
                    recipe(identity={'schema': SCHEMA + 1, 'identity': 'c' * 64}),
                    recipe(identity={'schema': SCHEMA, 'identity': 'c' * 64, 'engine': {}}),
                    recipe(options={}), recipe(options={'standard_override': None, 'profile': 'C:/x.toml'}),
                    recipe(options={'standard_override': ['pal']}), recipe(options={'standard_override': 'p' * 65}),
                    recipe(paths=None), recipe(paths={'format': 'retro-recomp-knowledge', 'version': 3})):
            with self.subTest(bad=str(bad)[:80]):
                self.refused('invalid', recipes.validate_recipe, bad)
        without = recipe()
        del without['title']
        self.refused('invalid', recipes.validate_recipe, without)

    def test_a_dump_name_cannot_leave_the_work_folder(self):
        for name in ('', '..', '.', 'a/b', 'a\\b', '..\\..\\x', 'C:x', 'a*', 'a?', ' a', 'a ', 'a.', 'a\x00b', 'n' * 161, 7):
            with self.subTest(name=name):
                self.refused('invalid', recipes.validate_recipe, recipe(name=name))
        for name in ('Sonic The Hedgehog 2 (World) (Rev A)', "Dr. Robotnik's (USA, Europe)", 'été [!]'):
            self.assertEqual(recipes.validate_recipe(recipe(name=name))['name'], name)

    def test_a_tampered_record_is_refused_by_the_validators_of_path_sharing(self):
        def tampered(change):
            document = recipe()
            change(document)
            return document
        limit = knowledge.FIELDS['sms']['rom_entries'][1]

        def too_many(document):
            table = entries(document)
            for column in table['cols']:
                column['v'] = [column['v'][0]] * (limit + 1)
            table['cols'][0]['v'] = list(range(limit + 1))
            table['n'] = limit + 1

        def other_game(document):
            games = document['paths']['knowledge']['games']
            games['sms:' + 'b' * 64] = {**copy.deepcopy(games['sms:' + SHA]), 'game': 'sms:' + 'b' * 64}
        cases = {
            'a row of text': lambda d: entries(d)['cols'][0]['v'].__setitem__(0, 'C3 00 02'),
            'bytes instead of a position': lambda d: entries(d)['cols'][0].__setitem__('v', ['c30002']),
            'a float': lambda d: entries(d)['cols'][4]['v'].__setitem__(0, 1.5),
            'too many rows': too_many,
            'another game': other_game,
            'rows of another game': lambda d: d['paths']['observations'].__setitem__('sms', {'b' * 64: [[1, 0xC000, 0, 4, 0]]}),
            'another machine': lambda d: d['paths']['observations'].__setitem__('md', {SHA: [[1, 0, 0, 4, 0]]}),
            'a row with bytes': lambda d: d['paths']['observations'].__setitem__('sms', {SHA: [[1, 0xC000, 0, 4, 'dd360512']]}),
            'an unknown key': lambda d: d['paths'].__setitem__('code', 'x'),
            'version 2 paths': lambda d: d['paths'].update(version=2, knowledge={'schema': 1, 'consoles': {'sms': {SHA: RECORD}}}),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.refused('invalid', recipes.validate_recipe, tampered(change))
                self.refused('invalid', recipes.parse_recipe, self.packed(tampered(change)))

    def packed(self, document) -> bytes:
        import gzip
        import json
        return gzip.compress(json.dumps(document).encode('utf-8'))

    def test_a_recipe_too_large_or_not_a_recipe(self):
        import gzip
        for data in (b'', b'not gzip', gzip.compress(b'not json'), gzip.compress(b'[1, 2]')):
            self.refused('invalid', recipes.parse_recipe, data)
        with mock.patch.object(recipes, 'MAX_BYTES', 64):
            self.refused('invalid', recipes.parse_recipe, self.packed(recipe()))
            self.refused('record', recipes.recipe_bytes, recipe())
        self.refused('invalid', recipes.read_recipe, self.root / 'absent.rrrecipe')

    def test_a_machine_left_out_is_refused_with_its_reason(self):
        for system, reason in recipes.LEFT_OUT.items():
            with self.subTest(system=system):
                self.assertIn(reason, self.refused('machine', recipes.validate_recipe, recipe(system=system)))
        self.refused('invalid', recipes.validate_recipe, recipe(system='zz'))

    def test_the_dump_must_be_the_one_the_recipe_names(self):
        mine = self.root / 'my own dump.sms'
        mine.write_bytes(PROGRAM)
        checked, rom = recipes.check_recipe(recipe(), mine)
        self.assertEqual((checked['rom_sha256'], rom.sha256, bytes(rom.data)), (SHA, SHA, PROGRAM))
        other = self.root / 'another.sms'
        other.write_bytes(PROGRAM[:0x200] + bytes(2) + PROGRAM[0x202:])
        reason = self.refused('rom', recipes.check_recipe, recipe(), other)
        self.assertIn(SHA, reason)
        self.assertIn('Authored Recipe (Europe)', reason)
        self.refused('rom', recipes.check_recipe, recipe(), self.root / 'absent.sms')
        self.assertEqual(mine.read_bytes(), PROGRAM)

    def test_the_output_is_never_the_players_games_folder(self):
        from retrorecomp.paths import data_directory, games_root
        mine = self.root / 'my own dump.sms'
        mine.write_bytes(PROGRAM)
        with mock.patch.object(recipes.subprocess, 'Popen') as started:
            for folder in (games_root(), games_root() / 'Master System', games_root().parent, data_directory() / 'recipes'):
                with self.subTest(folder=folder):
                    self.refused('output', recipes.apply_recipe, recipe(), mine, folder)
            preferences = {'feedback_paths': {'sms': str(self.root / 'played')}}
            with mock.patch('retrorecomp.paths.load_preferences', return_value=preferences):
                self.refused('output', recipes.apply_recipe, recipe(), mine, self.root / 'played' / 'recipe')
        started.assert_not_called()

    def test_what_the_master_system_cannot_carry(self):
        from retrorecomp.systems import get_profile
        profile, rom = get_profile('sms'), types.SimpleNamespace(sha256=SHA, data=PROGRAM)
        learning = {'native_profiles': {'pending_windows': 0, 'windows_over_limit': 0}}
        self.assertIn('functions', self.refused('record', recipes._sega_paths, profile, rom, {'backend': 'functions'}))
        for name in ('pending_windows', 'windows_over_limit'):
            report = {'backend': 'banked', 'learning': {'native_profiles': {**learning['native_profiles'], name: 2}}}
            self.refused('record', recipes._sega_paths, profile, rom, report)
        report = {'backend': 'banked', 'learning': learning}
        with mock.patch('retrorecomp.knowledge_build.build_record', return_value=None):
            self.refused('record', recipes._sega_paths, profile, rom, report)

        def private(rom, system, report, engine, omitted, *, offered):
            self.assertTrue(offered)   # the whole of what the conversion used, received paths included
            omitted['ram_without_rom_source'] += 3
            return dict(RECORD)
        with mock.patch('retrorecomp.knowledge_build.build_record', side_effect=private):
            self.assertIn('3 piece(s)', self.refused('record', recipes._sega_paths, profile, rom, report))
        with mock.patch('retrorecomp.knowledge_build.build_record', return_value=dict(RECORD)):
            self.assertEqual(recipes._sega_paths(profile, rom, report), (RECORD, []))


class RecipeModeTest(Environment):
    """Recipe mode in the converter: the host's record is read whole, the player's banks, library, earlier exports
    and gameplay records are not."""
    rom = types.SimpleNamespace(sha256=SHA, data=PROGRAM, system_id='sms')

    def test_without_the_variable_nothing_changes(self):
        from retrorecomp.paths import data_directory
        self.assertIsNone(knowledge.recipe_directory())
        self.assertEqual(knowledge.imported_path(), data_directory() / 'knowledge' / 'imported.json.gz')
        self.assertEqual(knowledge.imported_v3_path(), data_directory() / 'knowledge' / 'imported-v3.json.gz')
        self.mode(recipe_bank=False)
        self.assertTrue(knowledge.disabled())
        self.assertEqual(knowledge.record_for('sms', self.rom, ENGINE_REV), {})
        self.assertEqual(knowledge.imported_observations('sms', SHA), [])

    def test_recipe_mode_needs_a_library_of_its_own(self):
        self.mode(library=False)
        with self.assertRaises(RuntimeError):
            knowledge.recipe_directory()
        with self.assertRaises(RuntimeError):
            knowledge.imported_path()

    def test_the_recipes_paths_are_imported_into_its_own_banks_and_read_from_there(self):
        from retrorecomp.paths import data_directory
        self.mode()
        document = recipe()
        document['paths'] = game_document('sms', SHA, RECORD, [[1, 0xC000, 0x020100, 4, 293]], 'Authored Recipe')
        counted = import_document(copy.deepcopy(recipes.validate_recipe(document)['paths']))
        self.assertEqual((counted['new'], counted['games']), (1, 1))
        bank = self.root / 'knowledge'
        self.assertEqual(knowledge.imported_path(), bank / 'imported.json.gz')
        self.assertTrue((bank / 'imported.json.gz').is_file())
        self.assertTrue((bank / 'imported-observations.json.gz').is_file())
        self.assertFalse(str(knowledge.imported_path()).startswith(str(data_directory())))
        # The record the conversion reads: the recipe's, whole; the player's qualified bank stays off.
        record = knowledge.record_for('sms', self.rom, ENGINE_REV)
        self.assertEqual((record['rom_entries'], record['pattern_refs']), (RECORD['rom_entries'], RECORD['pattern_refs']))
        self.assertEqual(knowledge.qualified_bank(), {})
        self.assertEqual(knowledge.imported_observations('sms', SHA), [[1, 0xC000, 0x020100, 4, 293]])
        from retrorecomp.library import GameMemory
        memory = GameMemory(types.SimpleNamespace(sha256=SHA, data=PROGRAM, system_id='sms', path=Path('x.sms')))
        self.assertEqual(memory.bundled['rom_entries'], RECORD['rom_entries'])
        self.assertTrue(str(memory.directory).startswith(str(self.root / 'library')))
        # Another game, or the same game once the variable is gone: nothing.
        self.assertEqual(knowledge.imported_record('sms', 'b' * 64), {})
        del os.environ[knowledge.RECIPE_VARIABLE]
        self.assertEqual(knowledge.record_for('sms', self.rom, ENGINE_REV), {})
        self.assertEqual(knowledge.imported_observations('sms', SHA), [])

    def test_no_gameplay_record_is_read_not_even_beside_the_output(self):
        output = self.root / 'games' / 'Master System'
        played = output / 'datas' / 'fallbacks' / f'sms-{SHA}.rrfb'
        played.parent.mkdir(parents=True)
        played.write_bytes(feedback.encode([feedback.Observation(1, 0xC000, 0x020100, bytes.fromhex('DD360512'))], 'sms', SHA))
        self.mode(recipe_bank=False)
        with mock.patch('retrorecomp.paths.load_preferences', return_value={}):
            self.assertEqual(feedback.ingest('sms', SHA, output)['unique_candidates'], 1)   # a library of its own reads it
            (self.root / 'library' / '_runtime-feedback' / (SHA + '.rrfb')).unlink()
            self.mode()
            self.assertEqual(feedback.ingest('sms', SHA, output)['unique_candidates'], 0)   # recipe mode does not
        self.assertEqual(feedback.records('sms', SHA), [])

    def test_no_earlier_export_is_read(self):
        from retrorecomp import core
        self.mode()
        with mock.patch.object(core, 'GameMemory', side_effect=AssertionError('an earlier export was looked for')), \
                mock.patch.object(core, 'games_directory', side_effect=AssertionError('the games folder was read')):
            self.assertEqual(core.import_previous(self.rom, self.root / 'games', None), 0)

    def test_a_failed_recipe_conversion_is_not_retried_without_the_paths(self):
        from retrorecomp import batch
        item = types.SimpleNamespace(system='sms', sha256=SHA, title='Authored Recipe')
        arguments = (0, item, 1, None, None, None, None, [], lambda message: None, {})
        failed = {'status': 'error', 'message': 'no'}
        with mock.patch.object(batch, '_convert_one', return_value=failed) as converted, \
                mock.patch('retrorecomp.knowledge.imported_record', return_value=dict(RECORD)), \
                mock.patch('retrorecomp.knowledge.discard_imported') as discarded:
            self.mode()
            self.assertIs(batch._convert_in_budget(1, *arguments), failed)
            self.assertEqual(converted.call_count, 1)
            del os.environ[knowledge.RECIPE_VARIABLE]
            batch._convert_in_budget(1, *arguments)
            self.assertEqual(converted.call_count, 3)   # outside recipe mode the retry is as before
        discarded.assert_not_called()

    def test_the_conversion_process_runs_in_recipe_mode_only(self):
        job = self.root / 'job.json'
        import json
        job.write_text(json.dumps({'recipe': recipe(), 'result': str(self.root / 'result.json')}), encoding='utf-8')
        with mock.patch('retrorecomp.batch.convert_batch') as converted:
            self.assertEqual(recipes.run_job(job), 1)
        converted.assert_not_called()
        self.assertIn('recipe mode', json.loads((self.root / 'result.json').read_text(encoding='utf-8'))['message'])


@unittest.skipUnless(dependencies_ready(), 'the shared dependencies of a conversion are not built here')
class RecipeConversionTest(unittest.TestCase):
    """Real conversions of the authored program (about a minute): host, guest, the guest in recipe mode."""

    def test_a_guest_reaches_the_hosts_identity_from_its_own_dump_and_keeps_its_library(self):
        result = selftest.run()
        self.assertEqual({name for name, passed in result['checks'].items() if not passed}, set())
        self.assertFalse(result['commercial_rom_used'])
        self.assertEqual(result['identity_guest_recipe'], result['identity_host'])
        self.assertNotEqual(result['identity_guest_plain'], result['identity_host'])
        self.assertEqual(result['guarded_before'], result['guarded_after'])


if __name__ == '__main__':
    unittest.main()
