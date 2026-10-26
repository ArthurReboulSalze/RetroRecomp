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

    def test_each_reader_uses_the_qualified_bank(self):
        engines = self.engines()
        pack(self.path, {system: {self.rom.sha256: self.record(engine)} for system, engine in engines.items()})
        readers = {'gb': gameboy._bundled_record, 'nes': nes._bundled_record,
                   'md': megadrive.bundled_record, 'snes': supernintendo.bundled_record}
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
            for system, reader in {'gb': gameboy._bundled_record, 'nes': nes._bundled_record,
                                   'md': megadrive.bundled_record, 'snes': supernintendo.bundled_record}.items():
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
        readers = {'gb': gameboy._bundled_record, 'nes': nes._bundled_record,
                   'md': megadrive.bundled_record, 'snes': supernintendo.bundled_record}
        for system, reader in readers.items():
            with self.subTest(system):
                self.assertEqual(reader(self.rom), {})
                self.assertEqual(knowledge.record_for(system, self.rom, engines[system]), {})
                # The bank itself returns what it holds; readers filter by engine.
                self.assertEqual(knowledge.qualified_record(system, self.rom.sha256)['engine'], '9' * 40)
        wrong = SimpleNamespace(data=b'x' * len(self.rom.data), sha256=self.rom.sha256)
        pack(self.path, {'gb': {self.rom.sha256: self.record(gameboy.ENGINE_REV)}})
        self.assertEqual(gameboy._bundled_record(wrong), {})
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
                self.assertEqual(gameboy._bundled_record(self.rom), {})
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
