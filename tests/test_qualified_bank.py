"""The qualified bank replaces the embedded snapshot for every hint reader.

Synthetic data only: no ROM, no network, no real data directory.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import gzip
import hashlib
import json
import os
import re
import tempfile
import unittest

from retrorecomp import compilation_inputs as inputs
from retrorecomp import gameboy, knowledge, knowledge_exchange, megadrive, nes, supernintendo
from retrorecomp.console16 import REPOSITORIES

DISABLING = ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')


def pack(path, consoles):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps({'schema': 1, 'consoles': consoles}).encode(), mtime=0))


class QualifiedBankTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'datas' / 'knowledge' / 'qualified.json.gz'
        self.imported = self.root / 'datas' / 'knowledge' / 'imported.json.gz'
        environment = {name: value for name, value in os.environ.items() if name not in DISABLING}
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.knowledge.qualified_path', return_value=self.path),
                     patch('retrorecomp.knowledge.imported_path', return_value=self.imported)):
            item.start()
            self.addCleanup(item.stop)
        for cache in (knowledge._qualified_bank, knowledge._imported_bank):
            cache.cache_clear()
            self.addCleanup(cache.cache_clear)
        data = bytes(range(256)) * 256
        self.rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest())
        self.other = '2' * 64

    def record(self, engine, **fields):
        return {'engine': engine, 'rom_bytes': len(self.rom.data), **fields}

    def engines(self):
        return {'gb': gameboy.ENGINE_REV, 'nes': nes.ENGINE_REV, 'md': REPOSITORIES['md'][1],
                'snes': supernintendo.knowledge_engine(self.rom)}

    def readers(self):
        """Every console reads its bundled record through knowledge.bundled_record; md and snes only
        bind their engine in a one-line wrapper."""
        engines = self.engines()
        return {'gb': lambda rom: knowledge.bundled_record('gb', rom, engines['gb']),
                'nes': lambda rom: knowledge.bundled_record('nes', rom, engines['nes']),
                'md': megadrive.bundled_record, 'snes': supernintendo.bundled_record}

    def test_there_is_one_bundled_record_reader(self):
        for module in (gameboy, nes):
            self.assertFalse(hasattr(module, '_bundled_record'), module.__name__)

    def test_each_reader_uses_the_qualified_bank(self):
        engines = self.engines()
        pack(self.path, {system: {self.rom.sha256: self.record(engine)} for system, engine in engines.items()})
        readers = self.readers()
        for system, reader in readers.items():
            with self.subTest(system):
                self.assertEqual(reader(self.rom)['engine'], engines[system])
                self.assertEqual(knowledge.record_for(system, self.rom, engines[system])['engine'], engines[system])
                self.assertEqual(knowledge_exchange._bundled(system, self.rom.sha256)['engine'], engines[system])
                self.assertEqual(knowledge.qualified_record(system, self.rom.sha256)['engine'], engines[system])

    def test_the_embedded_snapshot_is_not_read_any_more(self):
        engines = self.engines()
        assets = self.root / 'assets'
        pack(assets / 'compilation-knowledge.json.gz',
             {system: {self.rom.sha256: self.record(engine)} for system, engine in engines.items()})
        with patch('retrorecomp.knowledge.ASSETS', assets), patch('retrorecomp.paths.ASSETS', assets), \
                patch('retrorecomp.gameboy.ASSETS', assets), patch('retrorecomp.nes.ASSETS', assets):
            for system, reader in self.readers().items():
                with self.subTest(system):
                    self.assertEqual(reader(self.rom), {})
                    self.assertEqual(knowledge.record_for(system, self.rom, engines[system]), {})
                    self.assertEqual(knowledge_exchange._bundled(system, self.rom.sha256), {})
        # No code path loads the snapshot through the packaged resource directory.
        pattern = re.compile(r'load\(\s*ASSETS\s*/\s*RESOURCE')
        source = Path(knowledge.__file__).parent
        self.assertEqual([path.name for path in source.glob('*.py')
                          if pattern.search(path.read_text(encoding='utf-8'))], [])
        self.assertEqual(knowledge.RESOURCE, 'assets/compilation-knowledge.json.gz')   # maintainers' source

    def test_the_engine_filter_is_unchanged(self):
        engines = self.engines()
        pack(self.path, {system: {self.rom.sha256: self.record('9' * 40)} for system in engines})
        readers = self.readers()
        for system, reader in readers.items():
            with self.subTest(system):
                self.assertEqual(reader(self.rom), {})
                self.assertEqual(knowledge.record_for(system, self.rom, engines[system]), {})
                # The bank itself returns what it holds; readers filter by engine.
                self.assertEqual(knowledge.qualified_record(system, self.rom.sha256)['engine'], '9' * 40)
        wrong = SimpleNamespace(data=b'x' * len(self.rom.data), sha256=self.rom.sha256)
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV)}})
        self.assertEqual(knowledge.bundled_record('gb', wrong, gameboy.ENGINE_REV), {})
        self.assertEqual(knowledge.record_for('gb', wrong, gameboy.ENGINE_REV), {})

    def test_qualified_hints_merge_with_imported_ones_whatever_their_compiler(self):
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567]])}})
        pack(self.imported, {'gb': {self.rom.sha256: self.record('8' * 40, rom_entries=[[2, 0x6000]])}})
        merged = knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV)
        self.assertEqual(merged['rom_entries'], [[1, 0x4567], [2, 0x6000]])
        # Another compiler: only the imported record guides the conversion.
        self.assertEqual(knowledge.record_for('gb', self.rom, '7' * 40)['rom_entries'], [[2, 0x6000]])

    def test_disabled_modes_know_nothing(self):
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567]])}})
        self.assertTrue(knowledge.qualified_record('gb', self.rom.sha256))
        for variable in DISABLING:
            with self.subTest(variable), patch.dict(os.environ, {variable: '0'}):
                self.assertEqual(knowledge.qualified_bank(), {})
                self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256), {})
                self.assertEqual(knowledge.bundled_record('gb', self.rom, gameboy.ENGINE_REV), {})
                self.assertEqual(knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV), {})
                self.assertEqual(inputs.knowledge_stamp('gb', self.rom.sha256), 'disabled')

    def test_a_missing_or_invalid_bank_knows_nothing(self):
        self.assertEqual(knowledge.qualified_bank(), {})
        self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256), {})
        self.assertEqual(knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV), {})
        self.path.parent.mkdir(parents=True)
        invalid = {
            'not gzip': b'plain text',
            'broken block': bytes.fromhex('1f8b080000000000000307') + bytes(16),
            'not json': gzip.compress(b'{'),
            'wrong schema': gzip.compress(json.dumps({'schema': 2, 'consoles': {}}).encode()),
            'unknown console': gzip.compress(json.dumps({'schema': 1, 'consoles': {'zx': {}}}).encode()),
            'private path': gzip.compress(json.dumps({'schema': 1, 'consoles': {'gb': {self.rom.sha256: {
                **self.record(gameboy.ENGINE_REV), 'private_path': 'K:/private'}}}}).encode()),
            'empty': b'',
        }
        for name, content in invalid.items():
            with self.subTest(name):
                self.path.write_bytes(content)
                self.assertEqual(knowledge.qualified_bank(), {})
                self.assertEqual(knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV), {})
                self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256), {})

    def test_an_oversized_bank_is_refused(self):
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567]])}})
        with patch('retrorecomp.knowledge.MAX_BYTES', 32):
            self.assertEqual(knowledge.qualified_bank(), {})

    def test_a_replaced_bank_is_read_again(self):
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567]])}})
        self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256)['rom_entries'], [[1, 0x4567]])
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567], [3, 0x7000]])}})
        self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256)['rom_entries'], [[1, 0x4567], [3, 0x7000]])
        self.path.unlink()
        self.assertEqual(knowledge.qualified_record('gb', self.rom.sha256), {})

    def test_the_stamp_follows_the_games_qualified_and_imported_hints(self):
        sha = self.rom.sha256
        engine = gameboy.ENGINE_REV
        empty = inputs.knowledge_stamp('gb', sha)
        pack(self.path, {'gb': {self.other: self.record(engine, rom_entries=[[1, 0x4567]])}})
        self.assertEqual(inputs.knowledge_stamp('gb', sha), empty, 'another game leaves this stamp')
        pack(self.path, {'gb': {sha: self.record(engine, rom_entries=[[1, 0x4567]]),
                                self.other: self.record(engine)}})
        first = inputs.knowledge_stamp('gb', sha)
        self.assertNotEqual(first, empty)
        pack(self.path, {'gb': {sha: self.record(engine, rom_entries=[[1, 0x4567]]),
                                self.other: self.record(engine, rom_entries=[[1, 0x4568]])}})
        self.assertEqual(inputs.knowledge_stamp('gb', sha), first)
        pack(self.path, {'gb': {sha: self.record(engine, rom_entries=[[1, 0x4567], [2, 0x6000]])}})
        second = inputs.knowledge_stamp('gb', sha)
        self.assertNotEqual(second, first)
        pack(self.imported, {'gb': {sha: self.record('8' * 40, rom_entries=[[3, 0x7000]])}})
        self.assertNotEqual(inputs.knowledge_stamp('gb', sha), second)
        self.path.unlink()
        self.imported.unlink()
        self.assertEqual(inputs.knowledge_stamp('gb', sha), empty, 'a missing bank is the same as an empty one')

    def test_the_stamp_reads_the_qualified_bank_only(self):
        assets = self.root / 'assets'
        pack(assets / 'compilation-knowledge.json.gz',
             {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV, rom_entries=[[1, 0x4567]])}})
        before = inputs.knowledge_stamp('gb', self.rom.sha256)
        with patch('retrorecomp.paths.ASSETS', assets), patch('retrorecomp.knowledge.ASSETS', assets):
            self.assertEqual(inputs.knowledge_stamp('gb', self.rom.sha256), before)


class GameStampTests(unittest.TestCase):
    """`knowledge_stamp` hashes the game's own record (stage B3 of the paths): in the schema 1 form,
    whatever schema the bank file is in; for Neo Geo and the machines without a schema 1 form, theirs."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'datas' / 'knowledge' / 'qualified.json.gz'
        self.imported = self.root / 'datas' / 'knowledge' / 'imported.json.gz'
        environment = {name: value for name, value in os.environ.items() if name not in DISABLING}
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.knowledge.qualified_path', return_value=self.path),
                     patch('retrorecomp.knowledge.imported_path', return_value=self.imported)):
            item.start()
            self.addCleanup(item.stop)
        self.side = self.root / 'datas' / 'knowledge' / 'qualified-v3.json.gz'
        for item in (patch('retrorecomp.knowledge.qualified_v3_path', return_value=self.side),
                     patch('retrorecomp.knowledge.imported_v3_path',
                           return_value=self.root / 'datas' / 'knowledge' / 'imported-v3.json.gz')):
            item.start()
            self.addCleanup(item.stop)
        self.caches = (knowledge._qualified_bank, knowledge._imported_bank, knowledge._side_games)
        for cache in self.caches:
            cache.cache_clear()
            self.addCleanup(cache.cache_clear)

    def write(self, path, document):
        knowledge.write_packed(path, document)
        for cache in self.caches:
            cache.cache_clear()

    def empty(self):
        return hashlib.sha256(b'{}').hexdigest()

    def test_a_record_has_the_same_stamp_in_a_schema_1_and_a_schema_3_bank(self):
        from tests.test_paths_schema import FIXTURES
        from retrorecomp import path_profiles
        for name in ('sms', 'gb', 'nes', 'md', 'snes'):
            system, _, record = FIXTURES[name]
            sha = hashlib.sha256(name.encode()).hexdigest()
            payload = {'schema': 1, 'consoles': {system: {sha: record}}}
            self.write(self.path, payload)
            first = inputs.knowledge_stamp(system, sha)
            self.assertNotEqual(first, self.empty(), name)
            self.write(self.path, path_profiles.bank_to_v3(payload))
            self.assertEqual(knowledge.qualified_record(system, sha), record, name)
            self.assertEqual(inputs.knowledge_stamp(system, sha), first, name)
            # The stamp is the hash of the record itself, as it was before the schemas.
            self.assertEqual(first, hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_neo_geo_hashes_the_games_record_not_the_whole_bank(self):
        from tests.test_paths_schema import ng_record
        from retrorecomp import neogeo_knowledge
        first, second = ng_record(), ng_record(cart='c' * 64)
        one, two = (neogeo_knowledge.key(r['cart'], r['bios']) for r in (first, second))
        self.write(self.path, {'schema': 1, 'consoles': {'ng': {one: first}}})
        stamp = inputs.knowledge_stamp('ng', one)
        self.assertNotEqual(stamp, self.empty())
        self.assertEqual(inputs.knowledge_stamp('ng', two), self.empty(), 'a game without a record')
        self.write(self.path, {'schema': 1, 'consoles': {'ng': {one: first, two: second}}})
        self.assertEqual(inputs.knowledge_stamp('ng', one), stamp, 'another game of the bank leaves it alone')
        self.assertNotEqual(inputs.knowledge_stamp('ng', two), stamp)
        self.write(self.imported, {'schema': 1, 'consoles': {'ng': {one: ng_record(rom_entries=[[1, 0]])}}})
        self.assertNotEqual(inputs.knowledge_stamp('ng', one), stamp, 'imported Neo Geo hints count')
        self.assertEqual(inputs.knowledge_stamp('ng', two), inputs.knowledge_stamp('ng', two))

    def test_cps1_hashes_its_schema_3_record_from_the_side_bank_and_the_x68000_has_none(self):
        # CPS-1 has no schema 1 form: its record lives in the schema 3 side bank (`qualified-v3.json.gz`), never in
        # the schema 1 file. The X68000 shares nothing: its stamp stays the constant.
        from tests.test_cps1_knowledge import a_record, IDENTITY
        document = a_record()
        identity, other = IDENTITY, '9' * 64
        self.assertEqual(inputs.knowledge_stamp('cps1', identity), self.empty())
        self.write(self.side, {'schema': 3, 'games': {document['game']: document}})
        stamp = inputs.knowledge_stamp('cps1', identity)
        self.assertNotEqual(stamp, self.empty())
        self.assertEqual(inputs.knowledge_stamp('cps1', other), self.empty(), 'another game')
        self.assertEqual(stamp, hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        # Any change of its paths moves it.
        from retrorecomp import cps1_knowledge
        changed = cps1_knowledge.rebuild(document, cps1_knowledge.entry_set(document) | {('m68k_ram', (0xff0100, 0x10, 2))})
        self.write(self.side, {'schema': 3, 'games': {changed['game']: changed}})
        self.assertNotEqual(inputs.knowledge_stamp('cps1', identity), stamp)
        # A schema 3 file at the schema 1 path is not where a CPS-1 record is looked for.
        self.side.unlink()
        self.write(self.path, {'schema': 3, 'games': {document['game']: document}})
        self.assertEqual(inputs.knowledge_stamp('cps1', identity), self.empty())
        self.assertEqual(inputs.knowledge_stamp('x68', identity), self.empty())
        self.path.unlink()
        for cache in self.caches:
            cache.cache_clear()

    def test_the_game_key_comes_from_the_profile(self):
        from types import SimpleNamespace
        from retrorecomp.systems import get_profile
        item = SimpleNamespace(path=Path('game.neo'), sha256='1' * 64)
        for system in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'cps1', 'x68'):
            self.assertEqual(get_profile(system).knowledge_identity(item, {}), item.sha256, system)
        ng = get_profile('ng')
        self.assertEqual(ng.knowledge_identity(item, {'bios': {'sha256': '2' * 64}}),
                         __import__('retrorecomp.neogeo_knowledge', fromlist=['key']).key('1' * 64, '2' * 64))
        # No verified firmware, or a set not prepared yet: no key, so no record.
        self.assertEqual(ng.knowledge_identity(item, {'bios': 'stand-in'}), item.sha256)
        with patch('retrorecomp.neogeo_knowledge.shared_identity', return_value=None):
            self.assertEqual(ng.knowledge_identity(item, {'bios': {'sha256': '2' * 64}}), item.sha256)


class QualifiedPathTests(unittest.TestCase):
    def test_the_path_sits_beside_the_imported_bank(self):
        root = Path(tempfile.gettempdir()) / 'synthetic-datas'
        with patch('retrorecomp.paths.data_directory', return_value=root):
            self.assertEqual(knowledge.qualified_path(), root / 'knowledge' / 'qualified.json.gz')
            self.assertEqual(knowledge.qualified_path().parent, knowledge.imported_path().parent)
            self.assertNotEqual(knowledge.qualified_path(), knowledge.imported_path())


class PackagedResourceTests(unittest.TestCase):
    def test_the_snapshot_is_public_but_not_bundled(self):
        from tools.prepare_publication import BUNDLED_FILES, PUBLIC_FILES, UNBUNDLED_FILES
        snapshot = 'assets/compilation-knowledge.json.gz'
        self.assertIn(snapshot, PUBLIC_FILES)
        self.assertNotIn(snapshot, BUNDLED_FILES)
        self.assertEqual(UNBUNDLED_FILES, {snapshot})
        self.assertIn('tests/test_qualified_bank.py', PUBLIC_FILES)
        # The other resources keep travelling in the executable.
        self.assertIn('assets/cover-references.json', BUNDLED_FILES)
        self.assertIn('assets/neogeo-catalogue.json', BUNDLED_FILES)

    def test_both_packagers_follow_the_bundled_list(self):
        tools = Path(__file__).resolve().parents[1] / 'tools'
        self.assertIn('BUNDLED_FILES', (tools / 'package.ps1').read_text(encoding='utf-8'))
        self.assertIn('BUNDLED_FILES', (tools / 'package_linux.py').read_text(encoding='utf-8'))
        for name in ('package.ps1', 'package_linux.py', 'package_installers.py'):
            self.assertNotIn('compilation-knowledge', (tools / name).read_text(encoding='utf-8'))

    def test_an_executable_carrying_the_snapshot_is_refused(self):
        # audit_executable accepts only names in BUNDLED_FILES under assets/.
        source = Path(__file__).resolve().parents[1] / 'tools' / 'prepare_publication.py'
        text = source.read_text(encoding='utf-8')
        self.assertIn('if name not in BUNDLED_FILES:\n                raise ValueError(f"Unexpected executable payload', text)

    def test_the_repository_audit_still_validates_the_snapshot(self):
        from tools.prepare_publication import check_public_file
        snapshot = 'assets/compilation-knowledge.json.gz'
        good = gzip.compress(json.dumps({'schema': 1, 'consoles': {}}).encode())
        check_public_file(snapshot, good)
        with self.assertRaises(ValueError):
            check_public_file(snapshot, gzip.compress(json.dumps({'schema': 2, 'consoles': {}}).encode()))


if __name__ == '__main__':
    unittest.main()
