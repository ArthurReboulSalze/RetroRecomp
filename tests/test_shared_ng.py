"""Neo Geo in the shared base: exchange, base, guidance, retry without, outcomes.

Neo Geo's discoveries are numeric offsets into the player's own cartridge and
BIOS (neogeo_knowledge), named by key(cartridge, BIOS). They travel like the
cartridge consoles' (collected from the player's library, exported, read back,
built into the base, downloaded by a player with the same cartridge and BIOS)
and guide that player's conversion, which still compares every route with the
fresh reference. Authored numbers only: no cartridge, firmware or code.
"""
import copy
import gzip
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange, neogeo_knowledge, online
from retrorecomp.core import ConversionError, StopRequested
from retrorecomp.neogeo_build import GEOLITH_REV, LITHOGEN_REV
from retrorecomp.neogeo_knowledge import (compact_record, entry_set, expanded_record, key, merged_record,
                                          salvaged_record, validate_record)
from tests import test_shared_base as shared_base
from tools.gui_patching import patch_gui

CART, BIOS, SET = 'a' * 64, 'b' * 64, 'c' * 64
IDENTITY = key(CART, BIOS)
GAME_KEY = f'ng:{IDENTITY}'


def ng_record(rom=((1, 0), (1, 2), (2, 0)), ram=((0xfc00, 1, 2, 4),), z80=((0xfffd, 4, 10, 1),), **fields):
    record = {'engine': GEOLITH_REV, 'loader': LITHOGEN_REV, 'cart': CART, 'bios': BIOS,
              'rom_bytes': 200000, 'p_bytes': 512, 'bios_bytes': 131072, 'm1_bytes': 65536, 'sm1_bytes': 131072,
              'rom_entries': [list(row) for row in rom], 'ram_refs': [list(row) for row in ram],
              'z80_refs': [list(row) for row in z80]}
    return {**record, **fields}


def bundled_only(records=None):
    """What the qualified bank holds for Neo Geo (nothing by default)."""
    return {'consoles': {'ng': records or {}}}


class Library:
    """A Neo Geo library in a temporary folder, without a real qualified bank."""

    def start(self, test, bundled=None):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        test.root = Path(temp.name).resolve()
        test.library = test.root / 'library' / 'ng'
        test.bank = test.root / 'datas' / 'knowledge' / 'imported.json.gz'
        environment = {name: value for name, value in os.environ.items()
                       if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR',
                                       'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
        replaced = bundled_only(bundled)
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.neogeo_knowledge.library_root', return_value=test.library),
                     patch('retrorecomp.knowledge.imported_path', return_value=test.bank),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=test.bank),
                     patch('retrorecomp.knowledge.qualified_bank', return_value=replaced['consoles'])):
            item.start()
            test.addCleanup(item.stop)
        test.addCleanup(knowledge._imported_bank.cache_clear)
        test.addCleanup(knowledge._observation_bank.cache_clear)
        test.addCleanup(setattr, neogeo_knowledge, 'SHARED_SOURCE', None)

    def keep(self, test, record, source=SET):
        directory = test.library / key(record['cart'], record['bios'])
        directory.mkdir(parents=True)
        (directory / 'compilation.json').write_text(json.dumps({
            'schema': 1, 'identity': key(record['cart'], record['bios']), 'title': 'Test Game',
            'source': {'sha256': source}, 'record': record, 'packed_reference_passed': True,
            'states_passed': True, 'zero_fallback': True}), encoding='utf-8')


def sources():
    return {1: bytes(range(256)) * 2, 2: bytes(131072), 3: bytes(65536), 4: bytes(131072)}


def current_fields(record=None):
    record = record or ng_record()
    return {name: record[name] for name in neogeo_knowledge.IDENTITY_FIELDS}


def import_bank(record):
    knowledge.write_packed(knowledge.imported_path(), {'schema': 1, 'consoles': {'ng': {IDENTITY: record}}})


def hints_of(project):
    context = (IDENTITY, {**current_fields(), 'rom_entries': [], 'ram_refs': [], 'z80_refs': []}, sources())
    with patch.object(neogeo_knowledge, 'context', return_value=context), \
            patch('retrorecomp.neogeo_knowledge.validate_bios', return_value={}):
        return neogeo_knowledge.hints(project)


class RecordTests(unittest.TestCase):
    def test_unions_are_compact_exact_and_never_mix_compilers(self):
        compact = compact_record(IDENTITY, ng_record(rom=((1, 0), (1, 6), (2, 0))))
        other = ng_record(rom=((1, 2), (1, 6)), ram=((0xfc00, 1, 2, 4), (0xfc10, 1, 4, 2)), z80=())
        merged = merged_record(IDENTITY, compact, other)
        self.assertEqual(merged['rom_entries'], [])
        self.assertEqual(expanded_record(IDENTITY, merged)['rom_entries'], [[1, 0], [1, 2], [1, 6], [2, 0]])
        self.assertEqual(len(merged['ram_refs']), 2)
        self.assertEqual(merged['z80_refs'], [[0xfffd, 4, 10, 1]])
        self.assertEqual(entry_set(merged), entry_set(compact) | entry_set(other))
        self.assertEqual(merged_record(IDENTITY, {}, other), other)
        self.assertEqual(merged_record(IDENTITY, other, {}), other)
        # Another compiler's record never mixes with this one's: the current one wins, else the first stays.
        older = ng_record(rom=((1, 100),), engine='9' * 40)
        self.assertEqual(merged_record(IDENTITY, older, other), other)
        self.assertEqual(merged_record(IDENTITY, other, older), other)
        oldest = ng_record(rom=((1, 8),), engine='8' * 40)
        self.assertEqual(merged_record(IDENTITY, older, oldest), older)
        # A union beyond the bound is refused, not truncated.
        with patch.dict(neogeo_knowledge.FIELDS, {'rom_entries': (2, 300)}):
            with self.assertRaises(ValueError):
                merged_record(IDENTITY, ng_record(rom=[(1, 2 * n) for n in range(200)], p_bytes=4096),
                              ng_record(rom=[(1, 2 * n + 400) for n in range(200)], p_bytes=4096))

    def test_a_malformed_row_is_left_out_alone(self):
        record = ng_record()
        record['rom_entries'] += [[1, 3], [1, 100000], [True, 0], 'x']
        record['ram_refs'] += [[0xfc00, 1, 2, 99]]
        record['z80_refs'] += [[1, 4, 0, 1]]
        kept = salvaged_record(IDENTITY, record)
        self.assertEqual(kept['rom_entries'], [[1, 0], [1, 2], [2, 0]])
        self.assertEqual(kept['ram_refs'], [[0xfc00, 1, 2, 4]])
        self.assertEqual(kept['z80_refs'], [[0xfffd, 4, 10, 1]])
        self.assertEqual(validate_record(IDENTITY, kept), kept)
        # The identity fields are all or nothing.
        for name, value in (('bios', 'd' * 64), ('engine', 'x'), ('p_bytes', 511), ('cart', 'e' * 64)):
            with self.subTest(name):
                self.assertIsNone(salvaged_record(IDENTITY, {**ng_record(), name: value}))
        self.assertIsNone(salvaged_record(IDENTITY, 'a record'))
        # A delta block that no longer fits is dropped with its block.
        delta = {**compact_record(IDENTITY, ng_record()), 'rom_deltas': [[1, 0, 2], [1, 4]]}
        self.assertEqual(salvaged_record(IDENTITY, delta)['rom_entries'], [])


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)
        self.project = self.root / 'project'
        self.project.mkdir()

    def test_imported_hints_guide_the_conversion_and_are_counted_apart(self):
        import_bank(compact_record(IDENTITY, ng_record(rom=((1, 10), (1, 12)), ram=(), z80=())))
        Library().keep(self, ng_record(rom=((1, 0),), ram=(), z80=()))
        physical, ram, z80, usage = hints_of(self.project)
        self.assertEqual(physical['p'], {0, 10, 12})
        self.assertEqual((usage['shared'], usage['local'], usage['imported']), (0, 1, 2))
        self.assertTrue(usage['fresh_validation_required'])
        self.assertEqual(neogeo_knowledge.imported_in_use(), IDENTITY)
        self.assertEqual(ram, [])

    def test_hints_of_another_cartridge_bios_or_compiler_do_not_apply(self):
        for other in (ng_record(rom=((1, 10),), engine='9' * 40), ng_record(rom=((1, 10),), loader='9' * 40),
                      ng_record(rom=((1, 10),), rom_bytes=300000)):
            with self.subTest(other['engine'] + other['loader'] + str(other['rom_bytes'])):
                import_bank(other)
                knowledge._imported_bank.cache_clear()
                physical, _, _, usage = hints_of(self.project)
                self.assertEqual((physical['p'], usage['imported']), (set(), 0))
                self.assertIsNone(neogeo_knowledge.imported_in_use())
        # A record for another BIOS is simply under another identity.
        knowledge.write_packed(knowledge.imported_path(), {'schema': 1, 'consoles': {
            'ng': {key(CART, 'd' * 64): ng_record(bios='d' * 64, rom=((1, 10),))}}})
        self.assertEqual(hints_of(self.project)[3]['imported'], 0)

    def test_imported_ram_rows_leave_room_for_the_conversions_own(self):
        rows = [(pc, 1, 0, 2) for pc in range(0, 2 * 3000, 2)]
        import_bank(ng_record(rom=(), ram=rows, z80=()))
        _, ram, _, usage = hints_of(self.project)
        self.assertEqual(len(ram), neogeo_knowledge.IMPORTED_RAM_LIMIT)
        self.assertEqual([row['offset'] for row in ram], [pc for pc, *_ in rows[:neogeo_knowledge.IMPORTED_RAM_LIMIT]])
        self.assertEqual(usage['imported'], neogeo_knowledge.IMPORTED_RAM_LIMIT)   # what guides this conversion

    def test_a_set_aside_cartridge_converts_without_them(self):
        import_bank(ng_record(rom=((1, 10),)))
        with knowledge.imported_set_aside('ng', IDENTITY):
            physical, _, _, usage = hints_of(self.project)
        self.assertEqual((physical['p'], usage['imported'], neogeo_knowledge.imported_in_use()), (set(), 0, None))
        self.assertEqual(hints_of(self.project)[0]['p'], {10})

    def test_hints_are_never_written_to_the_library(self):
        import_bank(ng_record(rom=((1, 10),)))
        hints_of(self.project)
        self.assertFalse(list(self.library.glob('*/compilation.json')) if self.library.exists() else [])

    def test_a_conversion_asks_the_shared_source_once_its_cartridge_is_prepared(self):
        asked = []
        def source(identity):
            asked.append(identity)
            import_bank(ng_record(rom=((1, 20),), ram=(), z80=()))   # the base served it just now
        neogeo_knowledge.SHARED_SOURCE = source
        physical, _, _, usage = hints_of(self.project)
        self.assertEqual((asked, physical['p'], usage['imported']), ([IDENTITY], {20}, 1))
        # Whatever the source does, the conversion goes on.
        neogeo_knowledge.SHARED_SOURCE = lambda identity: 1 / 0
        self.assertEqual(hints_of(self.project)[3]['imported'], 1)
        # A custom library folder opts out of every shared bank, the source included.
        neogeo_knowledge.SHARED_SOURCE = source
        asked.clear()
        with patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(self.root)}):
            self.assertEqual(hints_of(self.project)[3]['imported'], 0)
        self.assertEqual(asked, [])

    def write_project(self, reached):
        (self.project / 'native-discovery').mkdir(exist_ok=True)
        (self.project / 'native-validation.json').write_text(json.dumps(
            {'passed': True, 'routes': [{'route': 'play'}]}), encoding='utf-8')
        (self.project / 'native-discovery' / 'play-reference.json').write_text(json.dumps(
            {'m68k_ram_variants': [], 'z80_variants': [], 'reached_physical': {'p': reached, 'bios': []}}),
            encoding='utf-8')
        (self.project / 'native-analysis.json').write_text(json.dumps({'ram_source_refs': []}), encoding='utf-8')
        (self.project / 'z80-analysis.json').write_text('{}', encoding='utf-8')

    def test_only_what_the_fresh_reference_reached_enters_the_library(self):
        # The imported bank holds more than this player's own routes reached.
        import_bank(ng_record(rom=((1, 10), (1, 12), (1, 14)), ram=((0xfc00, 1, 2, 4),)))
        self.write_project([0, 2])
        context = (IDENTITY, {**current_fields(), 'rom_entries': [], 'ram_refs': [], 'z80_refs': []}, sources())
        checks, states = [{'reference_match': True, 'interpreted_opcodes': 0, 'audio_interpreted_opcodes': 0}], {'routes': [{'fresh_process_match': True}]}
        with patch.object(neogeo_knowledge, 'context', side_effect=lambda project: copy.deepcopy(context)):
            hints_of(self.project)
            self.assertEqual(neogeo_knowledge.imported_in_use(), IDENTITY)
            result = neogeo_knowledge.remember(self.project, checks, states, title='Test Game', source={'sha256': SET})
        stored = json.loads((self.library / IDENTITY / 'compilation.json').read_text(encoding='utf-8'))['record']
        self.assertEqual(stored['rom_entries'], [[1, 0], [1, 2]])
        self.assertEqual(stored['ram_refs'], [])
        self.assertEqual(result['numeric_entries']['rom_entries'], 2)
        # The next conversion keeps its own routes and adds the ones it reaches.
        self.write_project([0, 4])
        with patch.object(neogeo_knowledge, 'context', side_effect=lambda project: copy.deepcopy(context)):
            neogeo_knowledge.remember(self.project, checks, states, title='Test Game', source={'sha256': SET})
        stored = json.loads((self.library / IDENTITY / 'compilation.json').read_text(encoding='utf-8'))['record']
        self.assertEqual(stored['rom_entries'], [[1, 0], [1, 2], [1, 4]])
        # The set's prepared cartridge is remembered for the next batch.
        self.assertEqual(neogeo_knowledge.prepared_cartridge(SET), CART)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_a_neo_file_is_its_own_cartridge_and_a_zip_set_is_known_once_prepared(self):
        self.assertEqual(neogeo_knowledge.shared_identity(Path('game.NEO'), CART, BIOS), IDENTITY)
        self.assertIsNone(neogeo_knowledge.shared_identity(Path('game.zip'), SET, BIOS), 'never prepared')
        self.assertIsNone(neogeo_knowledge.shared_identity(Path('game.zip'), SET, None))
        neogeo_knowledge.remember_prepared(SET, CART)
        self.assertEqual(neogeo_knowledge.shared_identity(Path('game.zip'), SET, BIOS), IDENTITY)
        # With another BIOS it is another game of the base.
        self.assertEqual(neogeo_knowledge.shared_identity(Path('game.zip'), SET, 'd' * 64), key(CART, 'd' * 64))
        neogeo_knowledge.remember_prepared('nonsense', CART)
        self.assertNotIn('nonsense', json.loads((self.library / neogeo_knowledge.CACHE_NAME).read_text())['sets'])

    def test_the_library_of_earlier_conversions_gives_the_identity_without_a_cache(self):
        Library().keep(self, ng_record(), source=SET)
        self.assertFalse((self.library / neogeo_knowledge.CACHE_NAME).exists())
        self.assertEqual(neogeo_knowledge.shared_identity(Path('game.zip'), SET, BIOS), IDENTITY)
        self.assertEqual(json.loads((self.library / neogeo_knowledge.CACHE_NAME).read_text())['sets'], {SET: CART})
        # An unknown set does not read the whole library again while it is unchanged.
        with patch.object(neogeo_knowledge, '_library_entries', return_value=1), \
                patch.object(Path, 'glob', side_effect=AssertionError('library read again')):
            self.assertIsNone(neogeo_knowledge.shared_identity(Path('other.zip'), 'e' * 64, BIOS))
        # A damaged cache is ignored, not trusted.
        (self.library / neogeo_knowledge.CACHE_NAME).write_text('{"sets": {"x": 1}}', encoding='utf-8')
        self.assertEqual(neogeo_knowledge.shared_identity(Path('game.zip'), SET, BIOS), IDENTITY)


def report(**changes):
    value = {'tool': 'Retro-Recomp', 'created_utc': '2026-10-27T10:00:00+00:00', 'system': {'id': 'ng'},
             'rom': {'sha256': SET}, 'prepared_cartridge': {'sha256': CART}, 'bios': {'sha256': BIOS},
             'compiler': {'revision': GEOLITH_REV, 'loader_revision': LITHOGEN_REV},
             'native_validation': {'passed': True}, 'scan_level': 'extended',
             'knowledge': {'identity': IDENTITY}}
    return {**value, **changes}


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)
        self.path = self.root / 'report.json'

    def game(self, **changes):
        self.path.write_text(json.dumps(report(**changes)), encoding='utf-8')
        return SimpleNamespace(system='ng', identity=SET, title='Test Game', report=str(self.path), source='',
                               watch='', status='current')

    def test_the_library_record_of_a_qualified_conversion_is_collected_as_numbers(self):
        Library().keep(self, ng_record())
        found = knowledge_exchange.collect_knowledge([self.game()])
        self.assertEqual((found['games'], found['consoles'], found['discoveries']), (1, {'ng': 1}, 5))
        record = found['payload']['consoles']['ng'][IDENTITY]
        self.assertEqual(record['rom_entries'], [], 'compact')
        self.assertEqual(entry_set(record), entry_set(ng_record()))
        self.assertEqual(found['titles'], {'ng': {IDENTITY: 'Test Game'}})
        self.assertEqual(found['levels'], {'ng': {IDENTITY: 'extended'}})
        self.assertEqual(found['observations'], {})
        self.assertNotIn('words', json.dumps(found['payload']))
        # The exchange file is read back as the maintainer reads it.
        shared = self.root / 'share.rrknowledge'
        knowledge_exchange.write_knowledge(found, shared, channel='file')
        document = knowledge_exchange.read_exchange(shared)
        self.assertEqual(document['knowledge']['consoles']['ng'][IDENTITY], record)
        paths = knowledge_exchange.discovery_paths(document)
        self.assertEqual(sorted(paths), [('ng', IDENTITY)])
        self.assertEqual((len(paths[('ng', IDENTITY)]['hints']), paths[('ng', IDENTITY)]['known']), (5, False))
        # Unchanged since it was shared: nothing is pending, then a change is.
        self.assertEqual(knowledge_exchange.pending_since_shared('file', found), [])
        self.assertEqual(knowledge_exchange.pending_since_shared('account', found), [GAME_KEY])

    def test_what_is_not_qualified_for_this_cartridge_bios_and_compiler_is_not_shared(self):
        Library().keep(self, ng_record())
        cases = {'a report of another compiler': report(compiler={'revision': '9' * 40, 'loader_revision': LITHOGEN_REV}),
                 'another loader': report(compiler={'revision': GEOLITH_REV, 'loader_revision': '9' * 40}),
                 'another BIOS': report(bios={'sha256': 'd' * 64}),
                 'another cartridge': report(prepared_cartridge={'sha256': 'd' * 64}),
                 'no prepared cartridge': {key_: value for key_, value in report().items() if key_ != 'prepared_cartridge'},
                 'a conversion that did not pass': report(native_validation={'passed': False})}
        for name, value in cases.items():
            with self.subTest(name):
                self.path.write_text(json.dumps(value), encoding='utf-8')
                game = SimpleNamespace(system='ng', identity=SET, title='T', report=str(self.path), source='',
                                       watch='', status='current')
                found = knowledge_exchange.collect_knowledge([game])
                self.assertEqual((found['games'], found['payload']['consoles']), (0, {}))
        # A library record of another compiler (engine) stays private.
        other = self.library / IDENTITY / 'compilation.json'
        data = json.loads(other.read_text(encoding='utf-8'))
        data['record']['engine'] = '9' * 40
        other.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(knowledge_exchange.collect_knowledge([self.game()])['games'], 0)
        # An invalid or unverified library entry too.
        data['record'] = ng_record()
        data['states_passed'] = False
        other.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(knowledge_exchange.collect_knowledge([self.game()])['games'], 0)

    def test_a_conversion_with_nothing_new_is_noted_with_a_record_without_hints(self):
        Library().keep(self, ng_record())
        known = compact_record(IDENTITY, ng_record())
        with patch('retrorecomp.knowledge.qualified_bank', return_value=bundled_only({IDENTITY: known})['consoles']):
            found = knowledge_exchange.collect_knowledge([self.game()])
            self.assertEqual((found['games'], found['omitted']['already_known']), (0, 1))
            stub = found['converted']['ng'][IDENTITY]
            self.assertEqual((stub['record']['rom_entries'], stub['record']['ram_refs'], stub['title']),
                             ([], [], 'Test Game'))
            with patch('retrorecomp.online._converted_queue', return_value=[GAME_KEY]):
                sent = online._with_conversions(online._restrict(found, set()), found)
        self.assertEqual(sent['converted_keys'], [GAME_KEY])
        shared = self.root / 'converted.rrknowledge'
        knowledge_exchange.write_knowledge(sent, shared, channel=None)
        document = knowledge_exchange.read_exchange(shared)
        self.assertEqual(document['knowledge']['consoles']['ng'][IDENTITY]['rom_entries'], [])
        self.assertEqual(knowledge_exchange.discovery_paths(document)[('ng', IDENTITY)],
                         {'known': False, 'hints': [], 'observations': []})

    def test_the_file_format_stays_and_neo_geo_shares_no_raw_observation(self):
        self.assertEqual(knowledge_exchange.VERSION, 2)
        self.assertEqual(knowledge_exchange.CARTRIDGE_SYSTEMS, ('sms', 'gg', 'gb', 'nes', 'md', 'snes'))
        record = compact_record(IDENTITY, ng_record())
        def write(**changes):
            document = {'format': knowledge_exchange.FORMAT, 'version': 2, 'converter': '1.5.3', 'created_utc': '',
                        'titles': {'ng': {IDENTITY: 'Test Game'}},
                        'knowledge': {'schema': 1, 'consoles': {'ng': {IDENTITY: record}}}, 'observations': {}}
            document.update(changes)
            target = self.root / 'case.rrknowledge'
            target.write_bytes(gzip.compress(json.dumps(document).encode()))
            return target
        self.assertEqual(knowledge_exchange.read_exchange(write())['knowledge']['consoles']['ng'][IDENTITY], record)
        with self.assertRaises(ValueError):
            knowledge_exchange.read_exchange(write(observations={'ng': {IDENTITY: [[10, 0, 1, 2, 4]]}}))
        self.assertEqual(knowledge_exchange.read_exchange(write(observations={'ng': {IDENTITY: []}}))['observations'],
                         {'ng': {IDENTITY: []}})
        wrong = key('d' * 64, BIOS)
        with self.assertRaises(ValueError):   # a record under another cartridge/BIOS key
            knowledge_exchange.read_exchange(write(knowledge={'schema': 1, 'consoles': {'ng': {wrong: record}}},
                                                   titles={}))

    def test_a_fetched_record_joins_the_bank_row_by_row_and_parts_are_merged(self):
        first = compact_record(IDENTITY, ng_record(rom=((1, 0), (1, 2)), ram=(), z80=()))
        second = ng_record(rom=((1, 6),), ram=((0xfc00, 1, 2, 4),), z80=())
        second['rom_entries'] += [[1, 3]]   # an odd root: this row alone is left out
        outcome = knowledge_exchange.import_fetched({
            GAME_KEY: {'records': [first, second, 'garbage', {**ng_record(), 'bios': 'd' * 64}],
                       'observations': [[10, 0, 1, 2, 4]]},
            f'ng:{"e" * 64}': {'records': [ng_record()]}})   # not this key's record: refused whole
        self.assertEqual(outcome['accepted'][GAME_KEY], {'records': 2, 'observations': 0})
        self.assertEqual(outcome['accepted'][f'ng:{"e" * 64}'], {'records': 0, 'observations': 0})
        stored = knowledge.imported_record('ng', IDENTITY)
        self.assertEqual(entry_set(stored), entry_set(ng_record(rom=((1, 0), (1, 2), (1, 6)), z80=())))
        self.assertEqual(knowledge.imported_observations('ng', IDENTITY), [])
        self.assertEqual(knowledge.imported_record('ng', 'e' * 64), {})
        # Another batch adds without losing: the union is kept, compact.
        knowledge_exchange.import_fetched({GAME_KEY: {'records': [ng_record(rom=((2, 8),), ram=(), z80=())]}})
        stored = knowledge.imported_record('ng', IDENTITY)
        self.assertEqual(stored['rom_entries'], [])
        self.assertEqual({row for name, row in entry_set(stored) if name == 'rom_entries'},
                         {(1, 0), (1, 2), (1, 6), (2, 8)})
        # And what the player's own library holds is not mixed into it.
        self.assertFalse(list(self.library.glob('*/compilation.json')) if self.library.exists() else [])


class BaseTests(unittest.TestCase):
    stop_server = shared_base.PublishedBaseTests.stop_server
    sign_in = shared_base.PublishedBaseTests.sign_in
    publish = shared_base.PublishedBaseTests.publish
    later = shared_base.PublishedBaseTests.later
    state = shared_base.PublishedBaseTests.state

    def setUp(self):
        shared_base.PublishedBaseTests.setUp(self)   # the fake service and the data folder
        environment = {name: value for name, value in os.environ.items()
                       if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR',
                                       'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
        replaced = bundled_only()
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.neogeo_knowledge.library_root', return_value=self.root / 'library' / 'ng'),
                     patch('retrorecomp.knowledge.qualified_bank', return_value=replaced['consoles'])):
            item.start()
            self.addCleanup(item.stop)

    def part(self, source, level='standard', record=None):
        return {'source': source, 'level': level, 'record': record if record is not None else
                compact_record(IDENTITY, ng_record(rom=((1, 2 * source),), ram=(), z80=())), 'observations': []}

    def test_a_player_with_the_same_cartridge_and_bios_receives_the_base_entry(self):
        built = shared_base.entry(self.part(47, 'extended'), self.part(52, 'quick'), identity=IDENTITY, system='ng')
        self.publish(5, {GAME_KEY: (built[0], [47, 52])}, entries=[built])
        prepared = online.prepare_batch([GAME_KEY])
        self.assertEqual(prepared['base']['games'], 1)
        self.assertEqual(prepared['paths'], {GAME_KEY: {'level': 'extended', 'records': 2}})
        stored = knowledge.imported_record('ng', IDENTITY)
        self.assertEqual({row for name, row in entry_set(stored) if name == 'rom_entries'}, {(1, 94), (1, 104)})
        context = (IDENTITY, {**current_fields(), 'rom_entries': [], 'ram_refs': [], 'z80_refs': []}, sources())
        with patch.object(neogeo_knowledge, 'context', return_value=context), \
                patch('retrorecomp.neogeo_knowledge.validate_bios', return_value={}):
            physical, _, _, usage = neogeo_knowledge.hints(self.root)
        self.assertEqual((physical['p'], usage['imported']), ({94, 104}, 2))
        # The same cartridge with another BIOS is another game of the base: nothing comes.
        other = f'ng:{key(CART, "d" * 64)}'
        self.assertEqual(online.prepare_batch([other])['paths'], {})

    def test_a_revoked_source_withdraws_the_neo_geo_hints(self):
        built = shared_base.entry(self.part(47), self.part(52), identity=IDENTITY, system='ng')
        self.publish(1, {GAME_KEY: (built[0], [47, 52])}, entries=[built])
        online.sync_base([GAME_KEY])
        self.assertTrue(knowledge.imported_record('ng', IDENTITY))
        self.publish(2, {GAME_KEY: (built[0], [47, 52])}, revoked=[47, 52], entries=[built])
        summary = online.sync_base([GAME_KEY], now=self.later())
        self.assertEqual(summary['discarded'], 1)
        self.assertEqual(knowledge.imported_record('ng', IDENTITY), {})
        log = json.loads(knowledge.imported_path().with_name('imported-rejected.json').read_text(encoding='utf-8'))
        self.assertEqual((log[-1]['system'], log[-1]['rom_sha256']), ('ng', IDENTITY))

    def test_a_part_that_is_not_this_games_record_is_left_out_not_the_game(self):
        wrong = self.part(60, record=ng_record(bios='d' * 64))
        built = shared_base.entry(self.part(47), wrong, identity=IDENTITY, system='ng')
        self.publish(1, {GAME_KEY: (built[0], [47, 60])}, entries=[built])
        online.sync_base([GAME_KEY])
        use = self.state('base-use.json')[GAME_KEY]
        self.assertEqual((use['records'], use['sources']), (1, [47, 60]))
        self.assertEqual(len(entry_set(knowledge.imported_record('ng', IDENTITY))), 1)

    def test_the_outcome_travels_under_the_cartridge_and_bios_identity(self):
        built = shared_base.entry(self.part(47), identity=IDENTITY, system='ng')
        self.publish(3, {GAME_KEY: (built[0], [47])}, entries=[built])
        self.sign_in()
        online.sync_base([GAME_KEY])
        self.assertTrue(online.note_conversion('ng', IDENTITY, rejected=True))
        self.assertEqual(online.converted_outcomes(),
                         {GAME_KEY: {'base': 3, 'entry': built[0], 'sources': [47], 'outcome': 'rejected'}})
        # What the Neo Geo conversion does when it set the hints aside, then what the window does.
        knowledge.discard_imported('ng', IDENTITY, 'conversion broke')
        online.forget_shared([GAME_KEY])
        self.assertEqual(online.shared_paths([GAME_KEY]), {})
        # The index still names that entry: it is not imported again.
        online.sync_base([GAME_KEY], now=self.later())
        self.assertEqual(knowledge.imported_record('ng', IDENTITY), {})


class RetryTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)
        self.emitted = []

    def run_convert(self, effects):
        from retrorecomp import neogeo_conversion
        calls = []
        def fake(path, **options):
            calls.append(options)
            effect = effects[len(calls) - 1]
            if isinstance(effect, BaseException):
                raise effect
            if callable(effect):
                return effect(options)
            return effect
        with patch.object(neogeo_conversion, '_convert', side_effect=fake):
            try:
                return neogeo_conversion.convert(Path('game.zip'), emit=self.emitted.append), calls
            except Exception as error:
                return error, calls

    def broken_with_imports(self, options):
        neogeo_knowledge._IN_USE.identity = IDENTITY
        raise ConversionError('the native build differs from the reference')

    def test_a_conversion_that_fails_with_imported_hints_runs_again_without_them(self):
        import_bank(ng_record(rom=((1, 10),)))
        seen = []
        def second(options):
            seen.append((knowledge.imported_record('ng', IDENTITY), neogeo_knowledge.imported_in_use()))
            return Path('game.exe')
        result, calls = self.run_convert([self.broken_with_imports, second])
        self.assertEqual(result, Path('game.exe'))
        self.assertEqual(seen, [({}, None)], 'the cartridge is set aside during the second run')
        self.assertNotIn('_rejected', calls[0])
        self.assertEqual(calls[1]['_rejected'], {'identity': IDENTITY, 'reason': 'the native build differs from the reference'})
        self.assertEqual(knowledge.imported_record('ng', IDENTITY), {}, 'discarded once the run without them passed')
        log = json.loads(knowledge.imported_path().with_name('imported-rejected.json').read_text(encoding='utf-8'))
        self.assertEqual((log[-1]['system'], log[-1]['rom_sha256']), ('ng', IDENTITY))
        self.assertTrue(any('converting again without them' in line for line in self.emitted))

    def test_other_failures_are_not_retried_and_a_failed_retry_keeps_the_hints(self):
        import_bank(ng_record(rom=((1, 10),)))
        error, calls = self.run_convert([ConversionError('no imported hints were used')])
        self.assertIsInstance(error, ConversionError)
        self.assertEqual(len(calls), 1)
        error, calls = self.run_convert([lambda options: (_ for _ in ()).throw(StopRequested('stop'))])
        self.assertIsInstance(error, StopRequested)
        self.assertEqual(len(calls), 1)
        def stopped(options):
            neogeo_knowledge._IN_USE.identity = IDENTITY
            raise StopRequested('stop')
        error, calls = self.run_convert([stopped])
        self.assertIsInstance(error, StopRequested)
        self.assertEqual(len(calls), 1, 'Stop is never retried')
        error, calls = self.run_convert([self.broken_with_imports, ConversionError('still broken')])
        self.assertEqual((str(error), len(calls)), ('still broken', 2))
        self.assertTrue(knowledge.imported_record('ng', IDENTITY), 'it failed without them too: they are not the cause')


class WindowTests(unittest.TestCase):
    def setUp(self):
        from retrorecomp import gui
        self.gui = gui
        self.owner = gui.Application.__new__(gui.Application)
        self.owner.messages = queue.Queue()
        Library().start(self)

    def test_neo_geo_batch_keys_name_the_game_by_cartridge_and_bios(self):
        neogeo_knowledge.remember_prepared(SET, CART)
        entries = [('ng', SET, Path('a.zip')), ('ng', 'e' * 64, Path('never-prepared.zip')), ('ng', CART, Path('b.neo')),
                   ('gb', 'f' * 64, Path('c.gb'))]
        with patch('retrorecomp.shared_batch.selected_bios_path', return_value=Path('bios.zip')), \
                patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': BIOS}):
            keys = self.owner.shared_rom_keys(entries, {'ng_bios': 'bios.zip'})
            self.assertEqual(keys, [GAME_KEY, GAME_KEY, 'gb:' + 'f' * 64])
            self.assertEqual(self.owner.shared_rom_keys([('gb', 'f' * 64, Path('c.gb'))], {}), ['gb:' + 'f' * 64])
        with patch('retrorecomp.shared_batch.selected_bios_path', return_value=None):
            self.assertEqual(self.owner.shared_rom_keys(entries, {}), ['gb:' + 'f' * 64], 'no BIOS: no Neo Geo game is asked for')
        with patch('retrorecomp.shared_batch.selected_bios_path', return_value=Path('bios.zip')), \
                patch('retrorecomp.neogeo.validate_bios', side_effect=ValueError('wrong BIOS')):
            self.assertEqual(self.owner.shared_rom_keys(entries, {}), ['gb:' + 'f' * 64])

    def test_a_neo_geo_conversion_asks_the_base_once_per_game_and_quietly(self):
        calls = []
        with patch_gui('SENDING_AVAILABLE', True), \
                patch.object(online, 'prepare_batch', side_effect=lambda keys, enabled=True:
                             calls.append(keys) or {'paths': {}, 'summary': None, 'error': None, 'base': None}):
            self.owner.start_shared_source(True, [GAME_KEY], {'ng'})
            source = neogeo_knowledge.SHARED_SOURCE
            source(IDENTITY)                     # already in the batch's first request
            source(key(CART, 'd' * 64))
            source(key(CART, 'd' * 64))
            self.assertEqual(calls, [[f'ng:{key(CART, "d" * 64)}']])
            self.owner.stop_shared_source()
            self.assertIsNone(neogeo_knowledge.SHARED_SOURCE)
            self.owner.start_shared_source(True, [], {'gb', 'md'})
            self.assertIsNone(neogeo_knowledge.SHARED_SOURCE, 'no Neo Geo game, no source')
            # Without the option the cartridge still asks, for the local base's qualified paths alone.
            calls.clear()
            self.owner.start_shared_source(False, [], {'ng'})
            neogeo_knowledge.SHARED_SOURCE(IDENTITY)
            self.assertEqual(calls, [[GAME_KEY]])

    def test_the_note_and_the_rejection_read_the_neo_geo_report(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        rejected = folder / 'rejected.json'
        rejected.write_text(json.dumps(report(knowledge={'identity': IDENTITY,
                                                         'imported_hints_rejected': {'identity': IDENTITY}})), encoding='utf-8')
        clean = folder / 'clean.json'
        clean.write_text(json.dumps(report()), encoding='utf-8')
        game = SimpleNamespace(system='ng', identity=SET)
        with patch_gui('SENDING_AVAILABLE', True), patch.object(online, 'note_conversion') as note:
            self.owner.note_conversion({'status': 'success', 'report': str(rejected)}, game)
            self.owner.note_conversion({'status': 'success', 'report': str(clean)}, game)
            self.owner.note_conversion({'status': 'success', 'report': str(folder / 'missing.json')}, game)
            self.owner.note_conversion({'status': 'success'}, game)
        self.assertEqual([(call.args, call.kwargs) for call in note.call_args_list],
                         [(('ng', IDENTITY), {'rejected': True}), (('ng', IDENTITY), {'rejected': False})])
        with patch.object(online, 'forget_shared') as forget:
            self.owner.forget_rejected_shared({}, [
                {'system': 'ng', 'sha256': SET, 'report': str(rejected)},
                {'system': 'ng', 'sha256': 'e' * 64, 'report': str(clean)},
                {'system': 'gb', 'sha256': 'f' * 64, 'imported_hints_rejected': True}])
            forget.assert_called_once_with([GAME_KEY])
            forget.reset_mock()
            self.owner.forget_rejected_shared({'gb:' + 'f' * 64: {}}, [
                {'system': 'gb', 'sha256': 'f' * 64, 'imported_hints_rejected': True}])
            forget.assert_called_once_with(['gb:' + 'f' * 64])


class ConsolesOutsideTheBaseTests(unittest.TestCase):
    def test_cps1_and_the_x68000_know_nothing_and_never_fail(self):
        # The batch asks before every Standard conversion (1.5.2 failed here with a KeyError).
        for system in ('cps1', 'x68'):
            self.assertEqual(knowledge_exchange._entries(system, {}), set())
            self.assertEqual(knowledge_exchange._entries(system, knowledge_exchange._bundled(system, 'a' * 64)), set())
            self.assertEqual(knowledge_exchange.unknown_hints(system, {'rom_bytes': 1}, {}), 0)


if __name__ == '__main__':
    unittest.main()
