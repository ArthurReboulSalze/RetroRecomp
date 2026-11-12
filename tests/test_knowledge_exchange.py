"""ROM-free knowledge export/import: format, additive merge and use."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange

ENGINE = 'a' * 40
OTHER = 'b' * 40


def md(entries, engine=ENGINE):
    return {'engine': engine, 'rom_bytes': 0x10000, 'rom_entries': [[e] for e in entries]}


class KnowledgeExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bank = self.root / 'datas/knowledge/imported.json.gz'
        self.engine = {'md': ENGINE}
        self.patches = [patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                        patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank),
                        patch('retrorecomp.knowledge_exchange.engines', side_effect=lambda: self.engine)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        knowledge._imported_bank.cache_clear()
        self.temp.cleanup()

    def document(self, consoles, titles=None, **header):
        return {'format': 'retro-recomp-knowledge', 'version': 1, 'converter': '1.2.5',
                'created_utc': '2026-10-23T18:00:00+00:00', 'titles': titles or {},
                'knowledge': {'schema': 1, 'consoles': consoles}, **header}

    def write(self, name, document):
        path = self.root / name
        path.write_bytes(gzip.compress(json.dumps(document).encode()))
        return path

    def test_machines_without_shared_knowledge_have_no_entries(self):
        # 1.5.2 raised KeyError here before every Standard CPS-1 or X68000 batch.
        for system in ('cps1', 'x68'):
            self.assertEqual(knowledge_exchange._entries(system, {}), set())
            self.assertEqual(knowledge_exchange._entries(system, {'rom_entries': [[1]]}), set())

    def test_merge_keeps_order_and_unions_every_field_including_spc(self):
        merged = knowledge.merge_records('md', md([0x200, 0x300]), md([0x300, 0x400]))
        self.assertEqual(merged['rom_entries'], [[0x200], [0x300], [0x400]])
        first = {'engine': ENGINE, 'rom_bytes': 0x10000, 'spc_ranges': [[0x200, 0x202, 7]]}
        second = {'engine': ENGINE, 'rom_bytes': 0x10000, 'spc_refs': [[0x202, 7], [0x300, 9]]}
        merged = knowledge.merge_records('snes', first, second)
        self.assertEqual(merged['spc_refs'], [[0x200, 7], [0x201, 7], [0x202, 7], [0x300, 9]])
        self.assertNotIn('spc_ranges', merged)

    def test_hints_are_compared_for_the_same_rom_whatever_the_compiler(self):
        self.assertFalse(knowledge_exchange.adds_to('md', md([0x200]), md([0x200, 0x300])))
        self.assertTrue(knowledge_exchange.adds_to('md', md([0x400]), md([0x200, 0x300])))
        self.assertFalse(knowledge_exchange.adds_to('md', md([0x200]), md([0x200], OTHER)))
        self.assertEqual(knowledge_exchange.unknown_hints('md', md([0x200, 0x300, 0x400]),
                                                         md([0x200]), md([0x300], OTHER)), 1)
        self.assertFalse(knowledge_exchange.adds_to('md', md([]), {}))

    def test_an_upload_carries_only_what_the_local_base_lacks(self):
        cut = knowledge_exchange.without_known('md', md([0x200, 0x300, 0x400]), md([0x200, 0x300]))
        self.assertEqual(cut['rom_entries'], [[0x400]])
        self.assertEqual((cut['engine'], cut['rom_bytes']), (ENGINE, 0x10000))
        self.assertIsNone(knowledge_exchange.without_known('md', md([0x200]), md([0x200, 0x300])))
        whole = md([0x200, 0x300])
        self.assertIs(knowledge_exchange.without_known('md', whole, {}), whole)
        other_rom = {**md([0x200]), 'rom_bytes': 0x20000}
        self.assertIs(knowledge_exchange.without_known('md', whole, other_rom), whole)
        # The SPC references of a Super Nintendo record are bound to each other: they travel whole.
        snes = {'engine': ENGINE, 'rom_bytes': 0x10000, 'ram_refs': [[0x200, 1, 2], [0x300, 1, 2]],
                'spc_refs': [[0x200, 7], [0x300, 9]]}
        known = {'engine': ENGINE, 'rom_bytes': 0x10000, 'ram_refs': [[0x200, 1, 2]], 'spc_refs': [[0x200, 7]]}
        self.assertIs(knowledge_exchange.without_known('snes', snes, known), snes)
        # Only main-CPU paths known: they are cut, the SPC part stays as it was.
        known_ram = {**known, 'spc_refs': []}
        cut = knowledge_exchange.without_known('snes', snes, known_ram)
        self.assertEqual((cut['ram_refs'], cut['spc_refs']), ([[0x300, 1, 2]], [[0x200, 7], [0x300, 9]]))

    def test_import_is_additive_and_reports_each_outcome(self):
        sha = [hashlib.sha256(bytes([n])).hexdigest() for n in range(4)]
        first = self.write('first.rrknowledge', self.document(
            {'md': {sha[0]: md([0x200]), sha[1]: md([0x200]), sha[2]: md([0x200])}},
            {'md': {sha[0]: 'Game One'}}))
        summary = knowledge_exchange.import_knowledge(first)
        self.assertEqual((summary['games'], summary['new']), (3, 3))
        second = self.write('second.rrknowledge', self.document(
            {'md': {sha[0]: md([0x300]), sha[1]: md([0x200]), sha[2]: md([0x500], OTHER), sha[3]: md([0x600])}},
            {'md': {sha[2]: 'Other engine', sha[3]: 'Game Four'}}))
        # The check before importing counts unknown hints of every compiler.
        preview = knowledge_exchange.preview_import(second)
        self.assertEqual({k: preview[k] for k in ('games', 'discoveries')}, {'games': 3, 'discoveries': 3})
        summary = knowledge_exchange.import_knowledge(second)
        self.assertEqual({k: summary[k] for k in ('new', 'enriched', 'unchanged')},
                         {'new': 1, 'enriched': 2, 'unchanged': 1})
        self.assertEqual(knowledge_exchange.preview_import(second)['discoveries'], 0)
        bank = knowledge.read(self.bank)['consoles']['md']
        self.assertEqual(bank[sha[0]]['rom_entries'], [[0x200], [0x300]])
        # Another compiler's hints are merged, not dropped.
        self.assertEqual(bank[sha[2]]['rom_entries'], [[0x200], [0x500]])
        titles = json.loads(self.bank.with_name('imported-titles.json').read_text(encoding='utf-8'))
        self.assertEqual(titles['md'], {sha[0]: 'Game One', sha[2]: 'Other engine', sha[3]: 'Game Four'})

    def test_rejects_foreign_or_unsafe_files(self):
        sha = hashlib.sha256(b'x').hexdigest()
        cases = [self.document({'md': {sha: md([0x200])}}, format='other'),
                 self.document({'md': {sha: md([0x200])}}, path='C:/ROMS/game.md'),
                 self.document({'md': {sha: {**md([0x200]), 'bytes': 'ff'}}}),
                 self.document({'md': {sha: md([0x201])}}),
                 self.document({'md': {sha: md([0x200])}}, {'md': {sha: 'bad\ntitle'}}),
                 self.document({'md': {sha: md([0x200])}}, {'gb': {sha: 'Elsewhere'}})]
        for index, document in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                knowledge_exchange.read_exchange(self.write(f'bad{index}.rrknowledge', document))
        self.assertFalse(self.bank.exists())

    def test_imported_hints_merge_with_bundled_ones_at_use(self):
        data = bytes(range(256)) * 256
        rom = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest(), data=data)
        bundled = {'schema': 1, 'consoles': {'md': {rom.sha256: md([0x200])}}}
        with patch('retrorecomp.knowledge.qualified_bank', return_value=bundled['consoles']):
            self.assertEqual(knowledge.record_for('md', rom, ENGINE)['rom_entries'], [[0x200]])
            knowledge_exchange.import_knowledge(self.write('share.rrknowledge', self.document(
                {'md': {rom.sha256: md([0x300])}})))
            self.assertEqual(knowledge.record_for('md', rom, ENGINE)['rom_entries'], [[0x200], [0x300]])
            # The qualified bank is bound to its compiler; imported hints are not.
            self.assertEqual(knowledge.record_for('md', rom, OTHER)['rom_entries'], [[0x300]])

    def test_failed_conversion_retries_without_imported_hints_and_sets_them_aside(self):
        from retrorecomp import batch
        sha = hashlib.sha256(b'cartridge').hexdigest()
        knowledge_exchange.import_knowledge(self.write('share.rrknowledge', self.document(
            {'md': {sha: md([0x200])}})))
        item = SimpleNamespace(system='md', sha256=sha, title='Shared')
        seen, messages = [], []

        def convert(*args):
            hints = knowledge.imported_record('md', sha)
            seen.append(bool(hints))
            return {'status': 'error', 'message': 'reference mismatch'} if hints else {'status': 'success'}

        with patch('retrorecomp.batch._convert_one', side_effect=convert):
            result = batch._convert_in_budget(1, 0, item, 1, None, None, None, None, [], messages.append, {})
        self.assertEqual(seen, [True, False])
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['imported_hints_rejected'])
        self.assertEqual(knowledge.imported_record('md', sha), {})
        rejected = json.loads(self.bank.with_name('imported-rejected.json').read_text(encoding='utf-8'))
        self.assertEqual((rejected[0]['rom_sha256'], rejected[0]['reason']), (sha, 'reference mismatch'))
        # A failure the hints did not cause keeps them.
        knowledge_exchange.import_knowledge(self.write('again.rrknowledge', self.document(
            {'md': {sha: md([0x200])}})))
        with patch('retrorecomp.batch._convert_one', return_value={'status': 'error', 'message': 'no'}):
            self.assertEqual(batch._convert_in_budget(1, 0, item, 1, None, None, None, None, [],
                                                      messages.append, {})['status'], 'error')
        self.assertTrue(knowledge.imported_record('md', sha))

    def test_export_holds_only_new_qualified_hints_without_paths(self):
        data = bytes(range(256)) * 256
        rom = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest(), data=data)
        source = self.root / 'ROMS/Fixture (Europe).md'
        source.parent.mkdir(); source.write_bytes(data)
        moved = SimpleNamespace(system='md', identity=rom.sha256, title='Fixture', source='', report='r')
        games = [moved,
                 SimpleNamespace(system='md', identity='0' * 64, title='Missing', source=str(self.root / 'none.md'), report='r'),
                 SimpleNamespace(system='md', identity='2' * 64, title='Old engine', source=str(source), report=''),
                 SimpleNamespace(system='psx', identity='1' * 64, title='Computer', source=str(source), report='')]
        bundled = {'schema': 1, 'consoles': {'md': {rom.sha256: md([0x200])}}}
        profile = SimpleNamespace(read_rom=lambda path: rom)
        qualified = {('md', rom.sha256): {}, ('md', '0' * 64): {}}
        destination = self.root / 'mine.rrknowledge'
        located = []

        def locate(pending):
            # Only qualified games are looked up; the moved one is found again.
            located.append([game.title for game in pending])
            return {('md', rom.sha256): source}

        def export(record):
            with patch('retrorecomp.knowledge.qualified_bank', return_value=bundled['consoles']), \
                    patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile), \
                    patch('retrorecomp.knowledge_exchange.qualified_reports', return_value=qualified), \
                    patch('retrorecomp.knowledge_exchange.engines', return_value={'md': ENGINE}), \
                    patch('retrorecomp.knowledge_exchange.build_record', return_value=record):
                return knowledge_exchange.export_knowledge(games, destination, locate)

        summary = export(md([0x200]))
        self.assertEqual(located, [['Fixture', 'Missing']])
        self.assertEqual({k: summary['omitted'][k] for k in ('already_known', 'missing_rom', 'unqualified')},
                         {'already_known': 1, 'missing_rom': 1, 'unqualified': 1})
        self.assertEqual(summary['games'], 0)
        # Converted with nothing new: kept apart for an account upload (online.pending), never exported;
        # its level is the deepest discovery the report completed.
        qualified[('md', rom.sha256)] = {'scan_level': 'quick', 'upgrade': {'discovery': {'scan_level': 'extended'}}}
        with patch('retrorecomp.knowledge.qualified_bank', return_value=bundled['consoles']), \
                patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile), \
                patch('retrorecomp.knowledge_exchange.qualified_reports', return_value=qualified), \
                patch('retrorecomp.knowledge_exchange.engines', return_value={'md': ENGINE}), \
                patch('retrorecomp.knowledge_exchange.build_record', return_value=md([0x200])):
            found = knowledge_exchange.collect_knowledge(games, locate)
        self.assertEqual(found['converted'], {'md': {rom.sha256: {
            'engine': ENGINE, 'rom_bytes': 0x10000, 'level': 'extended', 'title': 'Fixture'}}})
        self.assertEqual(found['payload']['consoles'], {})
        qualified[('md', rom.sha256)] = {}
        summary = export(md([0x200, 0x300]))
        self.assertEqual(summary['consoles'], {'md': 1})
        document = knowledge_exchange.read_exchange(destination)
        self.assertEqual(document['titles'], {'md': {rom.sha256: 'Fixture'}})
        self.assertEqual(document['knowledge']['consoles']['md'][rom.sha256]['rom_entries'], [[0x200], [0x300]])
        text = gzip.decompress(destination.read_bytes()).decode('ascii')
        self.assertNotIn('ROMS', text)
        self.assertNotIn(str(self.root).replace('\\', '/'), text.replace('\\\\', '/'))


class SchemaOneWritersTests(unittest.TestCase):
    """The writers read the schema 1 view and write schema 1: they never drop a game it cannot hold."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.imported = self.root / 'datas/knowledge/imported.json.gz'
        self.qualified = self.imported.with_name('qualified.json.gz')
        for item in (patch('retrorecomp.knowledge.imported_path', return_value=self.imported),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.imported)):
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(knowledge._imported_bank.cache_clear)

    def bank(self, path, with_cps1):
        from tests.test_paths_schema import FIXTURES, cps1_document
        from retrorecomp import path_profiles
        system, identity, record = FIXTURES['md']
        document = path_profiles.bank_to_v3({'schema': 1, 'consoles': {system: {identity: record}}})
        if with_cps1:
            cps1 = cps1_document()
            document['games'][cps1['game']] = cps1
        knowledge.write_packed(path, document)
        return path.read_bytes(), (system, identity, record)

    def test_every_writer_refuses_a_schema_3_bank_holding_a_game_without_a_schema_1_form(self):
        before, (system, identity, record) = self.bank(self.imported, with_cps1=True)
        with self.assertRaisesRegex(ValueError, 'schema 3 bank'):
            knowledge.discard_imported(system, identity, 'failed')
        with self.assertRaisesRegex(ValueError, 'schema 3 bank'):
            knowledge_exchange._import_document({'knowledge': {'schema': 1, 'consoles': {}}, 'observations': {}})
        self.assertEqual(self.imported.read_bytes(), before)
        self.assertFalse((self.imported.parent / 'imported-rejected.json').exists())
        qualified, _ = self.bank(self.qualified, with_cps1=True)
        with self.assertRaisesRegex(ValueError, 'schema 3 bank'):
            knowledge_exchange.write_qualified_bank({system: {identity: record}})
        self.assertEqual(self.qualified.read_bytes(), qualified)

    def test_a_schema_3_bank_whose_games_all_have_a_schema_1_form_is_still_rewritten(self):
        _, (system, identity, record) = self.bank(self.qualified, with_cps1=False)
        knowledge_exchange.write_qualified_bank({system: {identity: record}})
        self.assertEqual(knowledge.read(self.qualified), {'schema': 1, 'consoles': {system: {identity: record}}})
        self.bank(self.imported, with_cps1=False)
        self.assertTrue(knowledge.discard_imported(system, identity, 'failed'))
        self.assertEqual(knowledge.read(self.imported), {'schema': 1, 'consoles': {}})


class RawObservationTests(unittest.TestCase):
    """Raw gameplay observations travel as ROM positions, never ROM bytes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bank = self.root / 'datas/knowledge/imported.json.gz'
        self.library = self.root / 'library'
        self.patches = [patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                        patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank),
                        patch('retrorecomp.library.library_root', side_effect=lambda system: self.library / system),
                        patch('retrorecomp.knowledge_exchange.engines', return_value={'md': ENGINE})]
        for item in self.patches:
            item.start()
        data = b''.join(hashlib.sha256(n.to_bytes(4, 'little')).digest() for n in range(2048))
        self.rom = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.source = self.root / 'Game.md'
        self.source.write_bytes(data)
        from retrorecomp.feedback import Observation, encode, private_file
        self.in_rom = Observation(6, 0xff0000, 0, data[0x1234:0x1240])   # RAM code copied from the ROM
        self.ram_only = Observation(6, 0xff0100, 0, b'\xde\xad\xbe\xef\x01\x02')
        target = private_file('md', self.rom.sha256)
        target.parent.mkdir(parents=True)
        target.write_bytes(encode([self.in_rom, self.ram_only], 'md', self.rom.sha256))

    def tearDown(self):
        for item in self.patches:
            item.stop()
        knowledge._imported_bank.cache_clear()
        knowledge._observation_bank.cache_clear()
        self.temp.cleanup()

    def game(self, watch='', status='new_hints'):
        return SimpleNamespace(system='md', identity=self.rom.sha256, title='Shared game', source=str(self.source),
                               report='', status=status, watch=watch)

    def export(self, name='mine.rrknowledge'):
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile), \
                patch('retrorecomp.knowledge.qualified_bank', return_value={}):
            return knowledge_exchange.export_knowledge([self.game()], self.root / name)

    def test_only_rom_positions_are_shared(self):
        rows, ram_only = knowledge_exchange.shareable_observations('md', self.rom.sha256, self.rom)
        self.assertEqual((rows, ram_only), ([[6, 0xff0000, 0, 12, 0x1234]], 1))
        summary = self.export()
        self.assertEqual((summary['observation_count'], summary['omitted']['ram_only']), (1, 1))
        text = gzip.decompress((self.root / 'mine.rrknowledge').read_bytes()).decode('ascii')
        self.assertNotIn(self.in_rom.data.hex(), text)
        self.assertNotIn(str(self.root).replace('\\', '/'), text.replace('\\\\', '/'))

    def test_imported_observations_rebuild_from_the_players_rom(self):
        from retrorecomp.feedback import records, private_file
        self.export()
        private_file('md', self.rom.sha256).unlink()        # another player, same cartridge
        shared = self.root / 'mine.rrknowledge'
        self.assertEqual(knowledge_exchange.preview_import(shared)['discoveries'], 1)
        self.assertEqual(knowledge_exchange.import_knowledge(shared)['new'], 1)
        self.assertEqual(knowledge_exchange.preview_import(shared)['discoveries'], 0)
        self.assertEqual(records('md', self.rom.sha256), [])
        self.assertEqual(records('md', self.rom.sha256, 6, self.rom), [self.in_rom])
        with knowledge.imported_set_aside('md', self.rom.sha256):
            self.assertEqual(records('md', self.rom.sha256, 6, self.rom), [])
        from retrorecomp.compilation_inputs import knowledge_stamp
        before = knowledge_stamp('md', self.rom.sha256)
        self.assertTrue(knowledge.discard_imported('md', self.rom.sha256, 'failed'))
        self.assertEqual(records('md', self.rom.sha256, 6, self.rom), [])
        self.assertNotEqual(knowledge_stamp('md', self.rom.sha256), before)

    def test_reconverted_games_share_hints_not_raw_observations(self):
        game = self.game(status='covered')                    # feedback consumed by a conversion
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile):
            summary = knowledge_exchange.collect_knowledge([game])
        self.assertEqual((summary['observation_count'], summary['omitted']['unqualified']), (0, 1))

    def test_unchanged_games_come_from_the_cache_and_sharing_is_tracked(self):
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile) as reader:
            first = knowledge_exchange.collect_knowledge([self.game(watch='files-v1')])
            again = knowledge_exchange.collect_knowledge([self.game(watch='files-v1')])
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(again['observations'], first['observations'])
            knowledge_exchange.collect_knowledge([self.game(watch='files-v2')])
            self.assertEqual(reader.call_count, 2)
        key = f'md:{self.rom.sha256}'
        # A new converter version that changes no engine keeps the cache (1.5.5);
        # emptying it (Options › Disk space) makes the next count read the game again.
        with patch('retrorecomp.knowledge_exchange.profile_for_path', return_value=profile) as reader, \
                patch('retrorecomp.knowledge_exchange.__version__', '9.9.9'):
            steps = []
            knowledge_exchange.collect_knowledge([self.game(watch='files-v2')],
                                                 progress=lambda *step: steps.append(step))
            self.assertEqual((reader.call_count, steps), (0, []))
            self.assertTrue(knowledge_exchange.clear_discoveries_cache())
            self.assertFalse(knowledge_exchange.clear_discoveries_cache())
            knowledge_exchange.collect_knowledge([self.game(watch='files-v2')],
                                                 progress=lambda *step: steps.append(step))
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(steps, [('games', 0, 1)])
        self.assertEqual(knowledge_exchange.pending_since_shared('account', first), [key])
        knowledge_exchange.mark_shared('account', first)
        self.assertEqual(knowledge_exchange.pending_since_shared('account', first), [])
        self.assertEqual(knowledge_exchange.pending_since_shared('file', first), [key])


class DiscoveryPathTests(unittest.TestCase):
    """Keys of the online leaderboard: only what the bundled snapshot lacks."""
    def document(self, record, rows=()):
        observations = {'gb': {'f' * 64: [list(row) for row in rows]}} if rows else {}
        return {'knowledge': {'schema': 1, 'consoles': {'md': {'a' * 64: record}}}, 'observations': observations}

    def test_new_hints_and_observations_become_keys(self):
        bundled = md([0x200, 0x300])
        with patch('retrorecomp.knowledge_exchange._bundled', side_effect=lambda s, i: bundled if s == 'md' else {}):
            paths = knowledge_exchange.discovery_paths(self.document(md([0x200, 0x300, 0x400]),
                                                                     [(2, 0x4000, 1, 3, 9), (2, 0x4000, 1, 3, 77)]))
        game = paths[('md', 'a' * 64)]
        self.assertTrue(game['known'])
        self.assertEqual(len(game['hints']), 1, 'bundled hints are not discoveries')
        self.assertTrue(all(len(key) == 16 for key in game['hints']))
        played = paths[('gb', 'f' * 64)]
        self.assertFalse(played['known'])
        self.assertEqual(len(played['observations']), 1, 'the ROM offset is not part of the path')
        # Same path, same key, whoever sends it.
        with patch('retrorecomp.knowledge_exchange._bundled', return_value={}):
            again = knowledge_exchange.discovery_paths(self.document(md([0x400])))
        self.assertEqual(again[('md', 'a' * 64)]['hints'], game['hints'])

    def test_a_new_game_cannot_flood_the_board(self):
        with patch('retrorecomp.knowledge_exchange._bundled', return_value={}):
            paths = knowledge_exchange.discovery_paths(self.document(md(range(0x200, 0x200 + 2 * 5000, 2))))
        game = paths[('md', 'a' * 64)]
        self.assertFalse(game['known'])
        self.assertEqual(len(game['hints']), knowledge_exchange.PATH_LIMIT)
        self.assertEqual(game['hints'], sorted(game['hints']))


ROM_ID = 'a' * 64


def big(first, count):
    """A valid Mega Drive record with `count` distinct entries from `first` (an even address)."""
    return {'engine': ENGINE, 'rom_bytes': 0x400000, 'rom_entries': [[first + 2 * n] for n in range(count)]}


def watch_row(address, offset=0):
    return [6, 0xff0000 + address, 0, 4, offset]


def document(records=None, observations=None):
    return {'knowledge': {'schema': 1, 'consoles': {'md': records} if records else {}},
            'observations': {'md': observations} if observations else {}, 'titles': {}, 'converter': ''}


class DroppedCountTests(unittest.TestCase):
    """What an import leaves out is counted, never dropped silently: the valid rows lost to a bound
    apart from the invalid or duplicate rows refused. No ROM, no network: an in-memory exchange."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bank = self.root / 'datas/knowledge/imported.json.gz'
        self.patches = [patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                        patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank),
                        patch('retrorecomp.library.library_root', side_effect=lambda system: self.root / 'library' / system),
                        patch('retrorecomp.knowledge_exchange._bundled', return_value={}),
                        patch('retrorecomp.knowledge_exchange.engines', return_value={'md': ENGINE})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        knowledge._imported_bank.cache_clear()
        knowledge._observation_bank.cache_clear()
        self.temp.cleanup()

    def counted(self, outcome, **expected):
        """`outcome['dropped']` holds every key, zero but for `expected`."""
        self.assertEqual(set(outcome['dropped']), set(knowledge_exchange.DROPPED_KEYS))
        self.assertEqual(outcome['dropped'], {**knowledge_exchange.new_dropped(), **expected})

    def fetched(self, records=(), observations=(), system='md', identity=ROM_ID):
        return knowledge_exchange.import_fetched(
            {f'{system}:{identity}': {'records': list(records), 'observations': list(observations)}})

    def test_a_clean_fetch_counts_nothing(self):
        outcome = self.fetched([md([0x200, 0x300])], [watch_row(1), watch_row(2)])
        self.assertEqual(outcome['accepted'][f'md:{ROM_ID}'], {'records': 1, 'observations': 2})
        self.counted(outcome)

    def test_rows_past_a_fields_bound_are_counted_when_a_record_is_salvaged(self):
        # The record fails as a whole (one malformed row), so its good rows are salvaged one by one;
        # the field's bound is lowered to 5 so the test needs no 65,000 rows.
        record = {**big(0x200, 8), 'rom_entries': [*big(0x200, 8)['rom_entries'], ['not a row']]}
        with patch('retrorecomp.knowledge_exchange.FIELDS', {'md': {'rom_entries': (1, 5)}}):
            outcome = self.fetched([record])
        self.assertEqual(outcome['accepted'][f'md:{ROM_ID}']['records'], 1)
        self.counted(outcome, record_rows_over_limit=3, record_rows_invalid=1)
        self.assertEqual(len(knowledge.read(self.bank)['consoles']['md'][ROM_ID]['rom_entries']), 5)

    def test_rows_dropped_from_a_rejected_record_are_not_counted_twice(self):
        outcome = self.fetched([{'engine': 5, 'rom_bytes': 0x10000, 'rom_entries': [[0x200]]}, 'a record', None])
        self.assertEqual(outcome['accepted'][f'md:{ROM_ID}']['records'], 0)
        self.counted(outcome, records_invalid=3)

    def test_a_record_that_cannot_join_the_union_is_counted(self):
        # Each record is valid alone; together they exceed the 65,536 entries a field may hold.
        outcome = self.fetched([big(0x200, 40000), big(0x200 + 2 * 50000, 40000)])
        self.assertEqual(outcome['accepted'][f'md:{ROM_ID}']['records'], 2)
        self.counted(outcome, records_over_bounds=1)
        self.assertEqual(len(knowledge.read(self.bank)['consoles']['md'][ROM_ID]['rom_entries']), 40000)

    def test_observations_invalid_duplicate_and_over_the_limit_are_counted(self):
        limit = knowledge_exchange.OBSERVATION_LIMIT
        rows = [watch_row(n) for n in range(limit + 3)]
        rows += [watch_row(0, offset=9), watch_row(1, offset=9)]   # the same observation, another ROM offset
        rows += [[999, 1, 0, 4, 0], 'a row', [6, 1, 0, 99, 0]]      # unknown kind, not a list, too long
        outcome = self.fetched(observations=rows)
        self.assertEqual(outcome['accepted'][f'md:{ROM_ID}']['observations'], limit)
        self.counted(outcome, observations_over_limit=3, observations_duplicate=2, observations_invalid=3)

    def test_observations_of_machines_that_share_none_are_not_a_loss(self):
        outcome = self.fetched(observations=[watch_row(1)], system='ng', identity='b' * 64)
        self.counted(outcome)

    def test_the_bank_bound_on_games_is_counted(self):
        records = {'1' * 64: md([0x200]), '2' * 64: md([0x300]), '3' * 64: md([0x300])}
        with patch('retrorecomp.knowledge_exchange.CONSOLE_LIMIT', 1):
            outcome = knowledge_exchange._import_document(document(records))
        self.assertEqual((outcome['new'], outcome['unchanged']), (1, 2))
        self.counted(outcome, games_over_limit=2)

    def test_a_full_bank_is_not_a_loss_when_the_game_brings_nothing_new(self):
        with patch('retrorecomp.knowledge_exchange.CONSOLE_LIMIT', 1):
            knowledge_exchange._import_document(document({'1' * 64: md([0x200])}))
            bundled = {'engine': ENGINE, 'rom_bytes': 0x10000, 'rom_entries': [[0x300]]}
            with patch('retrorecomp.knowledge_exchange._bundled', return_value=bundled):
                outcome = knowledge_exchange._import_document(document({'2' * 64: md([0x300])}))
        self.assertEqual(outcome['unchanged'], 1)
        self.counted(outcome)

    def test_a_union_over_a_fields_bound_is_counted_and_the_bank_keeps_what_it_had(self):
        self.counted(knowledge_exchange._import_document(document({ROM_ID: big(0x200, 40000)})))
        outcome = knowledge_exchange._import_document(document({ROM_ID: big(0x200 + 2 * 50000, 40000)}))
        self.assertEqual(outcome['unchanged'], 1)
        self.counted(outcome, records_over_bounds=1)
        self.assertEqual(len(knowledge.read(self.bank)['consoles']['md'][ROM_ID]['rom_entries']), 40000)

    def test_observations_past_the_banks_bound_for_a_game_are_counted(self):
        limit = knowledge_exchange.OBSERVATION_LIMIT
        first = [watch_row(n) for n in range(limit - 100)]
        self.counted(knowledge_exchange._import_document(document(observations={ROM_ID: first})))
        more = [watch_row(n) for n in range(limit - 100, limit + 50)]
        outcome = knowledge_exchange._import_document(document(observations={ROM_ID: more}))
        self.assertEqual(outcome['enriched'], 1)
        self.counted(outcome, observations_over_limit=50)
        self.assertEqual(len(knowledge.read_observations(knowledge.imported_observations_path())['md'][ROM_ID]), limit)

    def test_the_document_stage_drops_join_the_fetched_ones(self):
        limit = knowledge_exchange.OBSERVATION_LIMIT
        self.fetched(observations=[watch_row(n) for n in range(limit - 10)])
        # Second call: 40 rows already in the bank (not new, so not lost), 40 new ones of which 10 fit,
        # one malformed row. The call's own bound keeps all 80; the bank's bound cuts the 30 beyond it.
        outcome = self.fetched(observations=[watch_row(n) for n in range(limit - 50, limit + 30)] + ['a row'])
        self.counted(outcome, observations_invalid=1, observations_over_limit=30)

    def test_the_sync_summary_carries_the_counts(self):
        from retrorecomp import online
        answer = {'roms': {f'md:{ROM_ID}': {'cursor': 1, 'level': 'standard', 'records': [],
                                            'observations': [watch_row(1), 'a row']}}}
        with patch.object(online, 'account', return_value={'service': 'x', 'email': 'a'}), \
                patch.object(online, 'fetch_knowledge', return_value=answer), \
                patch.object(online, '_shared_state', return_value={}), \
                patch.object(online, '_save_shared_state'):
            summary = online.sync_shared([f'md:{ROM_ID}'])
        self.assertEqual((summary['observations'], summary['dropped']['observations_invalid']), (1, 1))


if __name__ == '__main__':
    unittest.main()


class LeftOutLineTests(unittest.TestCase):
    """The window says what an import or a sync left out, in one line (gui_sharing.SharingMixin.log_left_out)."""

    def make(self):
        import queue
        from retrorecomp.gui_sharing import SharingMixin
        from retrorecomp.i18n import tr
        window = SharingMixin.__new__(SharingMixin)
        window.messages = queue.Queue()
        window.tr = lambda key, **values: tr(key, 'en', **values)
        return window

    def test_every_dropped_counter_is_said_or_deliberately_quiet(self):
        from retrorecomp.gui_sharing import SharingMixin
        from retrorecomp.knowledge_exchange import DROPPED_KEYS
        said = set(SharingMixin.LOST_KEYS) | set(SharingMixin.INVALID_KEYS)
        self.assertEqual(said | {'observations_duplicate'}, set(DROPPED_KEYS))

    def test_losses_and_refusals_are_said_and_duplicates_are_not(self):
        from retrorecomp.knowledge_exchange import new_dropped
        window = self.make()
        dropped = new_dropped()
        dropped['observations_duplicate'] = 40
        window.log_left_out(dropped)
        self.assertTrue(window.messages.empty())
        dropped.update(records_over_bounds=2, observations_over_limit=5, records_invalid=1, observation_rows_unknown=9)
        window.log_left_out(dropped)
        kind, text = window.messages.get_nowait()
        self.assertEqual(kind, 'log')
        self.assertIn('7 rows past a limit', text)
        self.assertIn('1 rows refused as invalid', text)
        window.log_left_out(None)
        self.assertTrue(window.messages.empty())
