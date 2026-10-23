"""ROM-free knowledge export/import: format, additive merge and use."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smsrecomp import knowledge, knowledge_exchange

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
        self.patches = [patch('smsrecomp.knowledge.imported_path', return_value=self.bank),
                        patch('smsrecomp.knowledge_exchange.imported_path', return_value=self.bank),
                        patch('smsrecomp.knowledge_exchange.engines', side_effect=lambda: self.engine)]
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
        with patch('smsrecomp.knowledge.load', return_value=bundled):
            self.assertEqual(knowledge.record_for('md', rom, ENGINE)['rom_entries'], [[0x200]])
            knowledge_exchange.import_knowledge(self.write('share.rrknowledge', self.document(
                {'md': {rom.sha256: md([0x300])}})))
            self.assertEqual(knowledge.record_for('md', rom, ENGINE)['rom_entries'], [[0x200], [0x300]])
            # The bundled snapshot is bound to its compiler; imported hints are not.
            self.assertEqual(knowledge.record_for('md', rom, OTHER)['rom_entries'], [[0x300]])

    def test_failed_conversion_retries_without_imported_hints_and_sets_them_aside(self):
        from smsrecomp import batch
        sha = hashlib.sha256(b'cartridge').hexdigest()
        knowledge_exchange.import_knowledge(self.write('share.rrknowledge', self.document(
            {'md': {sha: md([0x200])}})))
        item = SimpleNamespace(system='md', sha256=sha, title='Shared')
        seen, messages = [], []

        def convert(*args):
            hints = knowledge.imported_record('md', sha)
            seen.append(bool(hints))
            return {'status': 'error', 'message': 'reference mismatch'} if hints else {'status': 'success'}

        with patch('smsrecomp.batch._convert_one', side_effect=convert):
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
        with patch('smsrecomp.batch._convert_one', return_value={'status': 'error', 'message': 'no'}):
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
                 SimpleNamespace(system='x68', identity='1' * 64, title='Computer', source=str(source), report='')]
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
            with patch('smsrecomp.knowledge_exchange.load', return_value=bundled), \
                    patch('smsrecomp.knowledge_exchange.profile_for_path', return_value=profile), \
                    patch('smsrecomp.knowledge_exchange.qualified_reports', return_value=qualified), \
                    patch('smsrecomp.knowledge_exchange.engines', return_value={'md': ENGINE}), \
                    patch('smsrecomp.knowledge_exchange.build_record', return_value=record):
                return knowledge_exchange.export_knowledge(games, destination, locate)

        summary = export(md([0x200]))
        self.assertEqual(located, [['Fixture', 'Missing']])
        self.assertEqual({k: summary['omitted'][k] for k in ('already_known', 'missing_rom', 'unqualified')},
                         {'already_known': 1, 'missing_rom': 1, 'unqualified': 1})
        self.assertEqual(summary['games'], 0)
        summary = export(md([0x200, 0x300]))
        self.assertEqual(summary['consoles'], {'md': 1})
        document = knowledge_exchange.read_exchange(destination)
        self.assertEqual(document['titles'], {'md': {rom.sha256: 'Fixture'}})
        self.assertEqual(document['knowledge']['consoles']['md'][rom.sha256]['rom_entries'], [[0x200], [0x300]])
        text = gzip.decompress(destination.read_bytes()).decode('ascii')
        self.assertNotIn('ROMS', text)
        self.assertNotIn(str(self.root).replace('\\', '/'), text.replace('\\\\', '/'))


class RawObservationTests(unittest.TestCase):
    """Raw gameplay observations travel as ROM positions, never ROM bytes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bank = self.root / 'datas/knowledge/imported.json.gz'
        self.library = self.root / 'library'
        self.patches = [patch('smsrecomp.knowledge.imported_path', return_value=self.bank),
                        patch('smsrecomp.knowledge_exchange.imported_path', return_value=self.bank),
                        patch('smsrecomp.library.library_root', side_effect=lambda system: self.library / system),
                        patch('smsrecomp.knowledge_exchange.engines', return_value={'md': ENGINE})]
        for item in self.patches:
            item.start()
        data = b''.join(hashlib.sha256(n.to_bytes(4, 'little')).digest() for n in range(2048))
        self.rom = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.source = self.root / 'Game.md'
        self.source.write_bytes(data)
        from smsrecomp.feedback import Observation, encode, private_file
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
        with patch('smsrecomp.knowledge_exchange.profile_for_path', return_value=profile), \
                patch('smsrecomp.knowledge_exchange.load', return_value={'schema': 1, 'consoles': {}}):
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
        from smsrecomp.feedback import records, private_file
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
        from smsrecomp.compilation_inputs import knowledge_stamp
        before = knowledge_stamp('md', self.rom.sha256)
        self.assertTrue(knowledge.discard_imported('md', self.rom.sha256, 'failed'))
        self.assertEqual(records('md', self.rom.sha256, 6, self.rom), [])
        self.assertNotEqual(knowledge_stamp('md', self.rom.sha256), before)

    def test_reconverted_games_share_hints_not_raw_observations(self):
        game = self.game(status='covered')                    # feedback consumed by a conversion
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('smsrecomp.knowledge_exchange.profile_for_path', return_value=profile):
            summary = knowledge_exchange.collect_knowledge([game])
        self.assertEqual((summary['observation_count'], summary['omitted']['unqualified']), (0, 1))

    def test_unchanged_games_come_from_the_cache_and_sharing_is_tracked(self):
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('smsrecomp.knowledge_exchange.profile_for_path', return_value=profile) as reader:
            first = knowledge_exchange.collect_knowledge([self.game(watch='files-v1')])
            again = knowledge_exchange.collect_knowledge([self.game(watch='files-v1')])
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(again['observations'], first['observations'])
            knowledge_exchange.collect_knowledge([self.game(watch='files-v2')])
            self.assertEqual(reader.call_count, 2)
        key = f'md:{self.rom.sha256}'
        self.assertEqual(knowledge_exchange.pending_since_shared('account', first), [key])
        knowledge_exchange.mark_shared('account', first)
        self.assertEqual(knowledge_exchange.pending_since_shared('account', first), [])
        self.assertEqual(knowledge_exchange.pending_since_shared('file', first), [key])


if __name__ == '__main__':
    unittest.main()
