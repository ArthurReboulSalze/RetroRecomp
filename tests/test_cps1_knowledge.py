"""CPS-1 in the shared base: numeric records from fresh reference runs, side banks, exchange, base, switch.

CPS-1 is experimental and still being developed, so the paths it shares are tied to the engine revision that
validated them, carry their own format number, and can be withdrawn with one line. Numbers only: no ROM byte,
no RAM word, no code.
"""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import cps1_knowledge, knowledge, knowledge_exchange as kx, online, path_profiles as pp
from tests import test_paths_exchange as paths_exchange
from tests import test_shared_base as shared_base
from tests.test_paths_schema import cps1_document

IDENTITY = '2' * 64
KEY = f'cps1:{IDENTITY}'
MOVE_D0 = bytes.fromhex('303c1234')          # move.w #$1234,d0 (two words)
RTS = bytes.fromhex('4e75')
Z80_OP = bytes.fromhex('3e55')               # ld a,$55 (operand live)


def images():
    """Two small images with known instructions at known places, nothing else recognisable."""
    main = bytearray(b'\x00\x01' * 0x800)     # 4 KiB of filler
    main[0x100:0x104] = MOVE_D0               # even offset: a copy of this instruction
    main[0x201:0x203] = RTS                   # odd offset only: not a place the 68000 can run code from
    audio = bytearray(b'\x00' * 0x8000)
    audio[0x123:0x125] = Z80_OP               # 3e xx at an odd offset: the Z80 has no alignment
    audio[0x124] = 0x99                       # the operand byte in the ROM is another one
    return {'maincpu': bytes(main), 'audiocpu': bytes(audio)}


def lengths(table=None):
    """A stand-in for the generator's decoder: {(offset, data): length}."""
    table = table or {MOVE_D0[:2]: 4, RTS: 2}

    def decode(windows):
        return {(offset, data): table.get(data[:2]) for offset, data in windows}
    return decode


def window(instruction: bytes, tail=b'\xde\xad\xbe\xef', offset=0x40):
    data = instruction + tail
    return {'offset': offset, 'words': data.hex()}


def fresh(m68k=(), z80=()):
    return {'m68k_ram': list(m68k), 'z80_ram': list(z80)}


class TranslationTests(unittest.TestCase):
    def test_an_instruction_in_the_program_rom_becomes_numbers_about_that_rom(self):
        # The window holds the instruction and four bytes of other data after it: only the instruction is tied.
        ram, z80, counts = cps1_knowledge.translate(images(), fresh([window(MOVE_D0)]), lengths())
        self.assertEqual(ram, [(0xff0040, 0x100, 4)])
        self.assertEqual(counts['m68k_ram'], {'observed': 1, 'tied': 1, 'private': 0, 'untranslatable': 0,
                                              'not_in_program_rom': 0})

    def test_what_is_not_in_the_rom_stays_private_and_is_counted(self):
        built = bytes.fromhex('203c0000beef')                 # built by the game: no copy in the ROM
        windows = [window(MOVE_D0), window(built, offset=0x50), window(RTS, offset=0x60),
                   window(b'\xff\xff', offset=0x70)]
        table = {MOVE_D0[:2]: 4, built[:2]: 6, RTS: 2}
        ram, _, counts = cps1_knowledge.translate(images(), fresh(windows), lengths(table))
        # RTS is only at an odd offset of the image: not a place code runs from, so it is not tied.
        self.assertEqual(ram, [(0xff0040, 0x100, 4)])
        self.assertEqual(counts['m68k_ram'], {'observed': 4, 'tied': 1, 'private': 3, 'untranslatable': 1,
                                              'not_in_program_rom': 2})

    def test_malformed_windows_are_ignored(self):
        bad = [{'offset': 0x41, 'words': '4e75'}, {'offset': 0x40, 'words': 'zz'}, {'offset': -2, 'words': '4e75'},
               {'offset': 0xfffe, 'words': '4e754e75'}, {'offset': 0x40, 'words': '4e7'}, 'text', {'offset': 0x40}]
        ram, z80, counts = cps1_knowledge.translate(images(), fresh(bad, [{'address': 0xd000, 'bytes': 'zz'}]), lengths())
        self.assertEqual((ram, z80, counts['m68k_ram']['observed'], counts['z80_ram']['observed']), ([], [], 0, 0))

    def test_a_sound_instruction_is_tied_by_its_structural_bytes_not_its_operand(self):
        observed = {'address': 0xd010, 'bytes': '3e553131'}   # ld a,$55 with the operand the game wrote
        other = {'address': 0xd020, 'bytes': 'edb01234'}      # ldir: not in the ROM
        _, z80, counts = cps1_knowledge.translate(images(), fresh(z80=[observed, other, observed]), lengths())
        self.assertEqual(z80, [(0xd010, 0x123, 4, 1)])
        self.assertEqual(counts['z80_ram'], {'observed': 2, 'tied': 1, 'private': 1, 'untranslatable': 0,
                                             'not_in_sound_rom': 1})
        outside = {'address': 0xc000, 'bytes': '3e553131'}    # not sound RAM
        self.assertEqual(cps1_knowledge.translate(images(), fresh(z80=[outside]), lengths())[1], [])

    def test_code_run_from_graphics_ram_is_not_expressible_and_stays_private(self):
        # Street Fighter II': Champion Edition runs part of its code from graphics RAM. The board reports nothing
        # for it (only work RAM and sound RAM variants exist, native/cps1_machine.c), so there is nothing to tie:
        # the record is valid, holds no path, and the interpreted instructions stay counted by the report.
        record, counts = cps1_knowledge.promote(IDENTITY, images(), fresh(), lengths())
        self.assertEqual(cps1_knowledge.rows(record), ([], []))
        self.assertEqual(counts['paths'], {'m68k_ram': 0, 'z80_ram': 0})
        self.assertFalse(counts['raw_ram_words_stored'])
        cps1_knowledge.validate_record(record, IDENTITY)

    def test_the_paths_rebuild_the_very_instructions_from_the_players_own_images(self):
        from retrorecomp.megadrive_z80 import opcode_key
        record, counts = cps1_knowledge.promote(
            IDENTITY, images(), fresh([window(MOVE_D0)], [{'address': 0xd010, 'bytes': '3e553131'}]), lengths())
        rebuilt = cps1_knowledge.expanded_rows(record, images())
        self.assertEqual(rebuilt['m68k_ram'], [{'offset': 0x40, 'words': MOVE_D0.hex()}])
        key_of = lambda text: opcode_key(bytes.fromhex(text))
        self.assertEqual(key_of(rebuilt['z80_ram'][0]['bytes']), key_of('3e553131'))
        self.assertEqual(rebuilt['z80_ram'][0]['address'], 0xd010)
        # The record holds numbers, hashes of the images and the engine; neither the instruction nor its bytes.
        text = json.dumps(record)
        for secret in (MOVE_D0.hex(), '3e55', 'dead'):
            self.assertNotIn(secret, text)
        self.assertEqual(counts['paths'], {'m68k_ram': 1, 'z80_ram': 1})
        # Other images (another dump, another catalogue layout) never get these paths.
        other = {**images(), 'maincpu': images()['maincpu'][:-2] + b'\xff\xff'}
        with self.assertRaises(ValueError):
            cps1_knowledge.expanded_rows(record, other)

    def test_promotion_keeps_what_the_library_already_held_for_these_images_and_engine(self):
        first, _ = cps1_knowledge.promote(IDENTITY, images(), fresh([window(MOVE_D0)]), lengths())
        second, _ = cps1_knowledge.promote(IDENTITY, images(), fresh(z80=[{'address': 0xd010, 'bytes': '3e553131'}]),
                                           lengths(), previous=first)
        self.assertEqual(cps1_knowledge.entry_set(second), cps1_knowledge.entry_set(first) | {('z80_ram', (0xd010, 0x123, 4, 1))})
        # A record of another engine is not mixed in.
        old = copy.deepcopy(first)
        old['cpus']['m68k']['core'] = '9' * 40
        third, _ = cps1_knowledge.promote(IDENTITY, images(), fresh(), lengths(), previous=old)
        self.assertEqual(cps1_knowledge.rows(third), ([], []))

    def test_the_rows_are_bounded_and_the_cut_is_reported(self):
        many = [window(MOVE_D0, offset=offset) for offset in range(0, 0x2000, 2)]
        with patch.object(cps1_knowledge, 'ROW_LIMIT', 100):
            record, counts = cps1_knowledge.promote(IDENTITY, images(), fresh(many), lengths())
        self.assertTrue(counts['truncated'])
        self.assertEqual(len(cps1_knowledge.rows(record)[0]), 100)


class RecordTests(unittest.TestCase):
    def record(self, **fresh_rows):
        return cps1_knowledge.promote(IDENTITY, images(), fresh([window(MOVE_D0)], [{'address': 0xd010, 'bytes': '3e553131'}]),
                                      lengths())[0]

    def test_a_record_is_a_valid_schema_3_document_with_its_own_format(self):
        record = self.record()
        pp.validate_game(record)
        self.assertEqual(record['identity']['layout']['format'], cps1_knowledge.FORMAT)
        from retrorecomp import cps1_catalogue
        self.assertEqual(record['identity']['layout']['catalogue'], cps1_catalogue.MAME_REVISION)
        self.assertEqual(set(record['identity']['sources']), {'maincpu', 'audiocpu'})
        self.assertEqual(cps1_knowledge.record_engine(record), cps1_knowledge.engine())
        self.assertEqual(cps1_knowledge.validate_record(record, IDENTITY), record)
        with self.assertRaises(ValueError):
            cps1_knowledge.validate_record(record, '3' * 64)

    def test_a_format_this_converter_does_not_know_is_skipped_not_fatal(self):
        newer = self.record()
        newer['identity']['layout']['format'] = 2
        with self.assertRaises(cps1_knowledge.UnknownFormat):
            cps1_knowledge.validate_record(newer, IDENTITY)
        self.assertIsNone(cps1_knowledge.salvaged_record(IDENTITY, newer))
        for broken in (0, 256, True, 'x'):
            bad = self.record()
            bad['identity']['layout']['format'] = broken
            with self.assertRaises(ValueError):
                cps1_knowledge.validate_record(bad, IDENTITY)
        # Another record of the same bank is read as usual: see SideBankTests.

    def test_a_record_that_lies_about_its_sources_or_machine_is_refused(self):
        record = self.record()
        for name, change in {
                'no hash': lambda d: d['identity']['sources']['maincpu'].pop('sha256'),
                'odd program': lambda d: d['identity']['sources']['maincpu'].update(bytes=0x1001),
                'no sound': lambda d: d['cpus'].pop('z80'),
                'a device': lambda d: d.update(devices={'gsu': {'core': 'a' * 40, 'paths': {}}}),
                'ram outside': lambda d: d['cpus']['m68k']['paths']['ram_code'][0].update(
                    table=pp.encode_table([[0xfe0000, 0x100, 4]], 3)),
                'rom outside': lambda d: d['cpus']['m68k']['paths']['ram_code'][0].update(
                    table=pp.encode_table([[0xff0040, 0x100000, 4]], 3)),
                'odd offset': lambda d: d['cpus']['m68k']['paths']['ram_code'][0].update(
                    table=pp.encode_table([[0xff0040, 0x101, 4]], 3)),
                'mask': lambda d: d['cpus']['z80']['paths']['ram_code'][0].update(
                    table=pp.encode_table([[0xd010, 0x123, 4, 2]], 4)),
                'another machine': lambda d: d.update(game='md:' + IDENTITY)}.items():
            damaged = copy.deepcopy(record)
            change(damaged)
            with self.subTest(name), self.assertRaises(ValueError):
                cps1_knowledge.validate_record(damaged, IDENTITY)

    def test_merging_never_mixes_engines_or_images(self):
        record = self.record()
        extra = cps1_knowledge.rebuild(record, cps1_knowledge.entry_set(record) | {('m68k_ram', (0xff0100, 0x10, 2))})
        merged = cps1_knowledge.merged(IDENTITY, record, extra)
        self.assertEqual(cps1_knowledge.entry_set(merged), cps1_knowledge.entry_set(extra))
        other_engine = copy.deepcopy(extra)
        other_engine['cpus']['z80']['core'] = '8' * 40
        self.assertEqual(cps1_knowledge.merged(IDENTITY, record, other_engine), record)
        self.assertEqual(cps1_knowledge.merged(IDENTITY, {}, record), record)


class EngineTests(unittest.TestCase):
    """The engine identity moves when the code that consumes the paths moves."""

    def setUp(self):
        cps1_knowledge.engine_parts.cache_clear()
        self.addCleanup(cps1_knowledge.engine_parts.cache_clear)

    def test_each_input_of_the_engine_moves_the_cores(self):
        base = cps1_knowledge.engine_parts()
        self.assertTrue(all(len(core) == 40 and set(core) <= set('0123456789abcdef') for core in base))
        self.assertEqual(cps1_knowledge.engine(), ':'.join(base))
        cases = {'the generator revision': patch.object(cps1_knowledge, 'GENERATOR_REVISION', 99),
                 'a native file': patch.object(cps1_knowledge, 'text_digest', lambda name, root=None: 'f' * 64),
                 'the Geolith pin': patch('retrorecomp.neogeo_build.GEOLITH_REV', '7' * 40)}
        for name, change in cases.items():
            cps1_knowledge.engine_parts.cache_clear()
            with self.subTest(name), change:
                moved = cps1_knowledge.engine_parts()
                self.assertNotEqual(moved[1], base[1], 'the sound core moves with ' + name)
                self.assertNotEqual(moved[0], base[0], 'the 68000 core moves with ' + name)
        # The 68000 semantics come from the Mega Drive recompiler: its pin moves the 68000 core only.
        from retrorecomp.console16 import REPOSITORIES
        cps1_knowledge.engine_parts.cache_clear()
        pinned = dict(REPOSITORIES, md=(REPOSITORIES['md'][0], '5' * 40))
        with patch('retrorecomp.console16.REPOSITORIES', pinned):
            moved = cps1_knowledge.engine_parts()
        self.assertNotEqual(moved[0], base[0])
        self.assertEqual(moved[1], base[1])

    def test_the_file_the_arithmetic_is_generated_from_moves_the_cores(self):
        # cps1_codegen._semantics cuts cps1_arithmetic.c out of native/md_prefetch.inc.
        self.assertIn('native/md_prefetch.inc', cps1_knowledge.NATIVE_INPUTS)
        import inspect
        from retrorecomp import cps1_codegen
        self.assertIn('md_prefetch.inc', inspect.getsource(cps1_codegen._semantics))
        base = cps1_knowledge.engine_parts()
        real = cps1_knowledge.text_digest
        cps1_knowledge.engine_parts.cache_clear()
        with patch.object(cps1_knowledge, 'text_digest',
                          lambda name, root=None: 'e' * 64 if name == 'native/md_prefetch.inc' else real(name, root)):
            moved = cps1_knowledge.engine_parts()
        self.assertNotEqual(moved[0], base[0], 'the 68000 core moves with the arithmetic source')

    def test_text_is_hashed_without_line_ends_and_the_files_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'a.c').write_bytes(b'one\r\ntwo\r\n')
            (Path(folder) / 'b.c').write_bytes(b'one\ntwo\n')
            self.assertEqual(cps1_knowledge.text_digest('a.c', Path(folder)), cps1_knowledge.text_digest('b.c', Path(folder)))
        for name in cps1_knowledge.NATIVE_INPUTS + cps1_knowledge.GENERATOR_SOURCES:
            self.assertTrue((Path(__file__).resolve().parents[1] / name).is_file(), name)

    # The Python that generates the code a RAM path becomes. Editing one of these files without raising
    # cps1_knowledge.GENERATOR_REVISION would let a path validated by the old code count as qualified for the
    # new one, so this test fails until both are done: raise the revision, then update the digests below.
    PINNED_SOURCES = {
        'retrorecomp/cps1_codegen.py': None, 'retrorecomp/cps1_build.py': None, 'retrorecomp/m68000.py': None,
        'retrorecomp/neogeo_codegen.py': None, 'retrorecomp/neogeo_z80.py': None, 'retrorecomp/megadrive_z80.py': None}
    PINNED_REVISION = 1

    def test_the_generator_sources_are_pinned_to_their_revision(self):
        root = Path(__file__).resolve().parents[1]
        found = {name: cps1_knowledge.text_digest(name, root) for name in cps1_knowledge.GENERATOR_SOURCES}
        self.assertEqual(set(found), set(self.PINNED_SOURCES))
        pins = json.loads((Path(__file__).with_name('cps1_generator_pins.json')).read_text(encoding='utf-8'))
        self.assertEqual(pins['revision'], cps1_knowledge.GENERATOR_REVISION,
                         'GENERATOR_REVISION changed: update tests/cps1_generator_pins.json')
        self.assertEqual(pins['sources'], found,
                         'A CPS-1 generator source changed: raise cps1_knowledge.GENERATOR_REVISION (the CPS-1 paths '
                         'qualified by the old code must be validated again), then update tests/cps1_generator_pins.json')


class Library:
    """A CPS-1 library and side banks in a temporary folder."""

    def start(self, test):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        test.root = Path(temp.name).resolve()
        test.library = test.root / 'library' / 'cps1'
        test.folder = test.root / 'datas' / 'knowledge'
        test.imported = test.folder / 'imported.json.gz'
        test.qualified = test.folder / 'qualified.json.gz'
        environment = {name: value for name, value in os.environ.items()
                       if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.library.library_root', side_effect=lambda system='sms': test.root / 'library' / system),
                     patch('retrorecomp.paths.data_directory', return_value=test.root / 'datas'),
                     patch('retrorecomp.knowledge.imported_path', return_value=test.imported),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=test.imported)):
            item.start()
            test.addCleanup(item.stop)
        for name in ('_imported_bank', '_qualified_bank', '_side_games', '_observation_bank'):
            test.addCleanup(getattr(knowledge, name).cache_clear)

    def keep(self, test, record, **flags):
        directory = test.library / IDENTITY
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'compilation.json').write_text(json.dumps({
            'schema': 1, 'system': 'cps1', 'title': 'Test', 'set': 'testset', 'source_identity': IDENTITY,
            'fresh_reference_passed': True, 'record': record, **flags}), encoding='utf-8')


def a_record(extra=()):
    record, _ = cps1_knowledge.promote(IDENTITY, images(), fresh([window(MOVE_D0)], [{'address': 0xd010, 'bytes': '3e553131'}]),
                                       lengths())
    return cps1_knowledge.rebuild(record, cps1_knowledge.entry_set(record) | set(extra)) if extra else record


class SideBankTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_the_schema_1_banks_never_change_by_a_byte_when_cps1_is_stored(self):
        from tests.test_paths_schema import FIXTURES
        system, identity, record = FIXTURES['md']
        qualified = self.folder / 'qualified.json.gz'
        with patch('retrorecomp.knowledge_exchange.qualified_bank_path', return_value=qualified):
            kx.write_qualified_bank({system: {identity: record}})
            before = qualified.read_bytes()
            kx.write_qualified_bank({system: {identity: record}, 'cps1': {IDENTITY: a_record()}})
            self.assertEqual(qualified.read_bytes(), before, 'qualified.json.gz is what it was without CPS-1')
            self.assertTrue(knowledge.qualified_v3_path().is_file())
            self.assertEqual(kx.read_qualified_bank()['cps1'][IDENTITY], a_record())
            self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), a_record())
            self.assertEqual(knowledge.qualified_record('cps1', IDENTITY), {})
            # Taking the game out removes the side bank and still leaves the schema 1 file as it was.
            kx.write_qualified_bank({system: {identity: record}})
            self.assertFalse(knowledge.qualified_v3_path().exists())
            self.assertEqual(qualified.read_bytes(), before)

    def test_a_damaged_or_unknown_game_is_set_aside_alone(self):
        good, newer, damaged = a_record(), a_record(), a_record()
        newer['game'] = 'cps1:' + '3' * 64
        newer['identity']['layout']['format'] = 2
        damaged['game'] = 'cps1:' + '4' * 64
        damaged['cpus']['z80']['core'] = 'not a core'
        path = knowledge.imported_v3_path()
        knowledge.write_packed(path, {'schema': 3, 'games': {good['game']: good, newer['game']: newer, damaged['game']: damaged}})
        self.assertEqual(set(knowledge.read_side_bank(path)), {good['game']})
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), good)
        self.assertEqual(knowledge.imported_game('cps1', '3' * 64), {})
        with self.assertRaises(ValueError):
            knowledge.write_side_bank(path, {newer['game']: newer})
        path.write_bytes(gzip.compress(b'{"schema": 1, "consoles": {}}'))
        with self.assertRaises(ValueError):
            knowledge.read_side_bank(path)
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})

    def test_a_set_aside_game_and_the_discard_after_a_failure(self):
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record()})
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), a_record())
        with knowledge.imported_set_aside('cps1', IDENTITY):
            self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})
        self.assertTrue(knowledge.discard_imported('cps1', IDENTITY, 'the conversion failed with them'))
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})
        self.assertFalse(knowledge.imported_v3_path().exists())
        log = json.loads(knowledge.imported_v3_path().with_name('imported-rejected.json').read_text(encoding='utf-8'))
        self.assertEqual((log[-1]['system'], log[-1]['rom_sha256']), ('cps1', IDENTITY))
        self.assertFalse(knowledge.discard_imported('cps1', IDENTITY, 'again'))

    def test_withdrawing_cps1_from_the_sharing_reads_nothing_and_breaks_nothing(self):
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record()})
        before = knowledge.imported_v3_path().read_bytes()
        stable = pp.STABLE_SHARED
        with patch.object(pp, 'SHARED_SYSTEMS', stable), patch.object(pp, 'SCHEMA3_ONLY', ()), \
                patch.object(kx, 'SYSTEMS', stable):
            self.assertIsNone(knowledge.schema3_module('cps1'))
            self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})
            self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), {})
            self.assertFalse(knowledge.discard_imported('cps1', IDENTITY, 'x'))
            self.assertNotIn('cps1', kx.read_qualified_bank())
        self.assertEqual(knowledge.imported_v3_path().read_bytes(), before, 'the file was not touched')
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), a_record(), 'it comes back with the name')


class SideBankKeepsWhatItDoesNotReadTests(unittest.TestCase):
    """A rewrite from a partial reading never loses a game: what this converter does not read stays in the file, as
    stored (a machine the switch withdrew or that has no module, a format it does not know, a damaged record, a game
    beyond the room), and the file goes only when no game at all is left."""

    OTHER = '5' * 64

    def setUp(self):
        Library().start(self)
        self.path = knowledge.imported_v3_path()

    def other_record(self, identity, **changes):
        record = a_record()
        record['game'] = 'cps1:' + identity
        for name, value in changes.items():
            if name == 'format':
                record['identity']['layout']['format'] = value
            elif name == 'core':
                record['cpus']['z80']['core'] = value
        return record

    def stored(self, path=None):
        with gzip.open(path or self.path, 'rb') as stream:
            return json.loads(stream.read())['games']

    def put(self, games, path=None):
        knowledge.write_packed(path or self.path, {'schema': 3, 'games': games})
        knowledge._side_games.cache_clear()

    def unread_games(self):
        """Games of a side bank this converter cannot read, each of a different kind."""
        return {'cps1:' + '3' * 64: self.other_record('3' * 64, format=2),          # a newer format
                'cps1:' + '4' * 64: self.other_record('4' * 64, core='not a core'),  # damaged
                'x68:' + '6' * 64: {'game': 'x68:' + '6' * 64, 'anything': [1, 2, 3]}}  # a machine without module

    def assert_kept(self, stored, unread):
        for key, record in unread.items():
            self.assertIn(key, stored)
            self.assertEqual(json.dumps(stored[key], sort_keys=True, separators=(',', ':')),
                             json.dumps(record, sort_keys=True, separators=(',', ':')), key)

    def test_a_write_keeps_the_games_it_cannot_read_as_stored(self):
        unread = self.unread_games()
        self.put({KEY: a_record(), **unread})
        richer = a_record(extra={('m68k_ram', (0xff0100, 0x10, 2))})
        knowledge.write_side_bank(self.path, {KEY: richer})
        stored = self.stored()
        self.assertEqual(stored[KEY], richer)
        self.assert_kept(stored, unread)
        self.assertEqual(set(knowledge.read_side_bank(self.path)), {KEY})
        # Taking the readable game out leaves the others, never an empty file.
        knowledge.write_side_bank(self.path, {})
        self.assertEqual(set(self.stored()), set(unread))
        # And nothing readable or unread: only then the file goes.
        self.put({KEY: a_record()})
        knowledge.write_side_bank(self.path, {})
        self.assertFalse(self.path.exists())

    def test_a_write_that_changes_nothing_does_not_touch_the_file(self):
        self.put({KEY: a_record(), **self.unread_games()})
        before = self.path.read_bytes()
        knowledge.write_side_bank(self.path, knowledge.read_side_bank(self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_game_beyond_the_room_is_kept_and_a_foreign_document_is_never_written_over(self):
        beyond = self.other_record(self.OTHER)
        self.put({KEY: a_record(), beyond['game']: beyond})
        with patch.object(knowledge, 'SIDE_GAMES', 1):
            self.assertEqual(set(knowledge.read_side_bank(self.path)), {KEY})
            knowledge.write_side_bank(self.path, {KEY: a_record(extra={('m68k_ram', (0xff0100, 0x10, 2))})})
        self.assert_kept(self.stored(), {beyond['game']: beyond})
        foreign = gzip.compress(b'{"schema": 1, "consoles": {}}')
        self.path.write_bytes(foreign)
        for write in (lambda: knowledge.write_side_bank(self.path, {KEY: a_record()}),
                      lambda: knowledge.refuse_to_overwrite_side_bank(self.path)):
            with self.assertRaises(ValueError):
                write()
        self.assertEqual(self.path.read_bytes(), foreign)
        # A file that cannot even be decoded holds nothing to keep.
        self.path.write_bytes(b'not a gzip file')
        knowledge.write_side_bank(self.path, {KEY: a_record()})
        self.assertEqual(set(self.stored()), {KEY})

    def test_the_qualified_bank_update_keeps_them_and_a_foreign_file_stops_it_before_any_write(self):
        unread = self.unread_games()
        qualified = knowledge.qualified_v3_path()
        self.put({KEY: a_record(), **unread}, qualified)
        from tests.test_paths_schema import FIXTURES
        system, identity, record = FIXTURES['md']
        legacy = self.folder / 'qualified.json.gz'
        with patch('retrorecomp.knowledge_exchange.qualified_bank_path', return_value=legacy):
            # The bank as a reader sees it: the readable games only.
            consoles = kx.read_qualified_bank()
            consoles.setdefault(system, {})[identity] = record
            kx.write_qualified_bank(consoles)
            self.assert_kept(self.stored(qualified), unread)
            self.assertEqual(self.stored(qualified)[KEY], a_record())
            # The last readable game goes: the unread ones stay.
            del consoles['cps1']
            kx.write_qualified_bank(consoles)
            self.assertEqual(set(self.stored(qualified)), set(unread))
            # A foreign document: nothing is written, the schema 1 bank included.
            qualified.write_bytes(gzip.compress(b'{"schema": 1, "consoles": {}}'))
            legacy.unlink()
            with self.assertRaises(ValueError):
                kx.write_qualified_bank(consoles)
            self.assertFalse(legacy.exists())

    def md_file(self):
        shared = self.root / 'md.rrknowledge'
        kx.write_knowledge(paths_exchange.collected('md'), shared, channel=None)
        return shared

    def test_an_import_keeps_them_and_adds_the_new_game_beside_them(self):
        unread = self.unread_games()
        self.put({KEY: a_record(), **unread})
        shared = self.md_file()
        self.assertEqual(kx.import_knowledge(shared)['new'], 1)
        stored = self.stored()
        self.assert_kept(stored, unread)
        self.assertEqual(stored[KEY], a_record())
        # A CPS-1 file next to them: the new game joins, the unread ones stay.
        newer = self.other_record('7' * 64)
        found = {'games': 1, 'consoles': {'cps1': 1}, 'discoveries': 2, 'omitted': {}, 'observations': {},
                 'observation_count': 0, 'payload': {'schema': 1, 'consoles': {'cps1': {'7' * 64: newer}}},
                 'titles': {'cps1': {'7' * 64: 'Seven'}}, 'levels': {}, 'converted': {}}
        cps = self.root / 'cps.rrknowledge'
        kx.write_knowledge(found, cps, channel=None, version=3)
        self.assertEqual(kx.import_knowledge(cps)['new'], 1)
        stored = self.stored()
        self.assert_kept(stored, unread)
        self.assertEqual(set(stored) - set(unread), {KEY, 'cps1:' + '7' * 64})

    def test_with_the_switch_off_nothing_of_cps1_is_lost_and_it_all_comes_back(self):
        self.put({KEY: a_record(), **self.unread_games()})
        qualified = knowledge.qualified_v3_path()
        self.put({KEY: a_record()}, qualified)
        before = qualified.read_bytes()
        shared = self.md_file()
        from tests.test_paths_schema import FIXTURES
        system, identity, record = FIXTURES['md']
        legacy = self.folder / 'qualified.json.gz'
        stable = pp.STABLE_SHARED
        with patch.object(pp, 'SHARED_SYSTEMS', stable), patch.object(pp, 'SCHEMA3_ONLY', ()), \
                patch.object(kx, 'SYSTEMS', stable), \
                patch('retrorecomp.knowledge_exchange.qualified_bank_path', return_value=legacy):
            # Any import of another console's file ...
            self.assertEqual(kx.import_knowledge(shared)['new'], 1)
            # ... any update of another console's qualified bank ...
            kx.write_qualified_bank({system: {identity: record}})
            # ... and the discard of another console's game.
            self.assertFalse(knowledge.discard_imported('cps1', IDENTITY, 'x'))
        self.assertEqual(qualified.read_bytes(), before, 'the qualified side bank was not touched')
        self.assertEqual(set(self.stored()), {KEY, *self.unread_games()}, 'the imported side bank lost nothing')
        self.assertEqual(self.stored()[KEY], a_record())
        knowledge._side_games.cache_clear()
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), a_record(), 'it comes back with the name')
        self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), a_record())

    def test_discarding_a_readable_game_leaves_the_unreadable_ones(self):
        unread = self.unread_games()
        self.put({KEY: a_record(), **unread})
        self.assertTrue(knowledge.discard_imported('cps1', IDENTITY, 'the conversion failed with them'))
        self.assertTrue(self.path.exists(), 'the file stays while it holds a game')
        self.assertEqual(set(self.stored()), set(unread))
        self.assert_kept(self.stored(), unread)
        knowledge._side_games.cache_clear()
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})
        # The last game of all: the file goes.
        self.put({KEY: a_record()})
        self.assertTrue(knowledge.discard_imported('cps1', IDENTITY, 'again'))
        self.assertFalse(self.path.exists())


def library_report(**changes):
    record = a_record()
    value = {'tool': 'Retro-Recomp', 'created_utc': '2026-10-27T10:00:00+00:00', 'system': {'id': 'cps1'},
             'rom': {'sha256': IDENTITY}, 'native_validation': {'passed': True}, 'scan_level': 'standard',
             'status': 'experimental',
             'knowledge': {'record_sha256': cps1_knowledge.record_digest(record), 'machine_status': 'experimental'}}
    return {**value, **changes}


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)
        self.path = self.root / 'report.json'
        patcher = patch('retrorecomp.knowledge_exchange.engines', side_effect=lambda: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def game(self, **changes):
        self.path.write_text(json.dumps(library_report(**changes)), encoding='utf-8')
        return SimpleNamespace(system='cps1', identity=IDENTITY, title='Test Game', report=str(self.path), source='',
                               watch='', status='current')

    def collect(self, game=None):
        with patch('retrorecomp.knowledge_exchange._current_engines', return_value={'cps1': cps1_knowledge.engine()}):
            return kx.collect_knowledge([game or self.game()])

    def test_the_library_record_of_a_verified_conversion_is_collected_as_numbers(self):
        Library().keep(self, a_record())
        found = self.collect()
        self.assertEqual((found['games'], found['consoles'], found['discoveries']), (1, {'cps1': 1}, 2))
        self.assertEqual(found['payload']['consoles']['cps1'][IDENTITY], a_record())
        self.assertEqual(found['levels'], {'cps1': {IDENTITY: 'standard'}})
        self.assertEqual(found['observations'], {})
        self.assertNotIn('words', json.dumps(found['payload']))
        # Version 3 carries it; read back as the maintainer reads it.
        shared = self.root / 'share.rrknowledge'
        result = kx.write_knowledge(found, shared, channel='file', version=3)
        self.assertEqual(result['version'], 3)
        document = kx.read_exchange(shared)
        self.assertEqual(document['version'], 3)
        self.assertEqual(document['knowledge']['consoles']['cps1'][IDENTITY], a_record())
        paths = kx.discovery_paths(document)
        self.assertEqual((len(paths[('cps1', IDENTITY)]['hints']), paths[('cps1', IDENTITY)]['known']), (2, False))
        self.assertEqual(kx.pending_since_shared('file', found), [])
        self.assertEqual(kx.pending_since_shared('account', found), [KEY])

    def test_a_version_2_file_cannot_carry_it_and_does_not_mark_it_shared(self):
        Library().keep(self, a_record())
        found = self.collect()
        shared = self.root / 'two.rrknowledge'
        result = kx.write_knowledge(found, shared, channel='file', version=2)
        self.assertEqual((result['version'], result['games'], result['schema3_only_left_out']), (2, 0, 1))
        self.assertEqual(kx.read_exchange(shared)['knowledge'], {'schema': 1, 'consoles': {}})
        self.assertEqual(kx.pending_since_shared('file', found), [KEY], 'still to be shared')
        # A file of version 2 that names CPS-1 is refused like an unknown console.
        document = {'format': kx.FORMAT, 'version': 2, 'converter': '1.6.0', 'titles': {},
                    'knowledge': {'schema': 1, 'consoles': {'cps1': {IDENTITY: a_record()}}}}
        shared.write_bytes(gzip.compress(json.dumps(document).encode()))
        with self.assertRaises(ValueError):
            kx.read_exchange(shared)

    def test_a_file_export_is_version_2_by_default_and_counts_the_cps1_games_it_leaves_out(self):
        from tests.test_paths_schema import FIXTURES
        Library().keep(self, a_record())
        found = self.collect()
        md_system, md_identity, md_record = FIXTURES['md']
        found['payload']['consoles'][md_system] = {md_identity: md_record}
        found['titles'][md_system] = {md_identity: 'A Mega Drive game'}
        found.update(games=2, consoles={'cps1': 1, md_system: 1}, discoveries=found['discoveries'] + 3)
        shared = self.root / 'file.rrknowledge'
        result = kx.write_knowledge(found, shared, channel='file')
        self.assertEqual((result['version'], result['games'], result['consoles']), (2, 1, {md_system: 1}))
        self.assertEqual(result['schema3_only_left_out'], 1)
        self.assertEqual(result['discoveries'], 3, 'the CPS-1 discoveries are not counted in a file without them')
        document = kx.read_exchange(shared)
        self.assertEqual((document['version'], set(document['knowledge']['consoles'])), (2, {md_system}))
        self.assertEqual(kx.pending_since_shared('file', found), [KEY], 'the CPS-1 game is still to be shared')
        # Nobody gets a file of a version they cannot read just because a CPS-1 game is in the collection.
        asked = kx.write_knowledge(found, self.root / 'three.rrknowledge', channel=None, version=3)
        self.assertEqual((asked['version'], asked['schema3_only_left_out']), (3, 0))

    def test_what_a_version_2_file_leaves_out_is_what_was_counted_for_it(self):
        # The library holds more paths than the shared base lacks: only the unknown ones were counted.
        richer = a_record(extra={('m68k_ram', (0xff0100, 0x10, 2)), ('m68k_ram', (0xff0200, 0x10, 2))})
        Library().keep(self, richer)
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: a_record()})
        found = self.collect(self.game(knowledge={'record_sha256': cps1_knowledge.record_digest(richer),
                                                  'machine_status': 'experimental'}))
        counted = found['discoveries']
        self.assertEqual(counted, 2)
        self.assertGreater(len(cps1_knowledge.entry_set(richer)), counted)
        self.assertEqual(found['schema3_only_found'], {'cps1': {IDENTITY: counted}})
        left = kx.without_schema3_only(found)
        self.assertEqual((left['discoveries'], left['games']), (0, 0))
        # A collection built by hand, without the counts, never goes below zero.
        by_hand = {key: value for key, value in found.items() if key != 'schema3_only_found'}
        self.assertEqual(kx.without_schema3_only(by_hand)['discoveries'], 2)

    def v3_file(self, games, titles=None):
        from tests.test_paths_schema import FIXTURES
        md_system, md_identity, md_record = FIXTURES['md']
        base = pp.bank_to_v3({'schema': 1, 'consoles': {md_system: {md_identity: md_record}}})
        base['games'].update(games)
        document = {'format': kx.FORMAT, 'version': 3, 'converter': '1.6.0', 'titles': titles or {},
                    'knowledge': base}
        target = self.root / 'mixed.rrknowledge'
        target.write_bytes(gzip.compress(json.dumps(document).encode()))
        return target, f'md:{md_identity}'

    def test_a_game_of_a_format_this_converter_does_not_know_is_left_out_alone(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        target, md_key = self.v3_file({KEY: newer}, titles={'cps1': {IDENTITY: 'Newer'}})
        document = kx.read_exchange(target)
        self.assertEqual(document['unreadable_games'], [KEY])
        self.assertEqual(set(document['knowledge']['consoles']), {'md'})
        self.assertEqual(document['titles'].get('cps1'), {})

    def test_withdrawing_cps1_leaves_the_other_games_of_a_file_readable(self):
        target, md_key = self.v3_file({KEY: a_record()}, titles={'cps1': {IDENTITY: 'Test'}})
        self.assertEqual(set(kx.read_exchange(target)['knowledge']['consoles']), {'md', 'cps1'})
        stable = pp.STABLE_SHARED
        with patch.object(pp, 'SHARED_SYSTEMS', stable), patch.object(pp, 'SCHEMA3_ONLY', ()),                 patch.object(pp, 'WITHDRAWN', ('cps1',)), patch.object(kx, 'SYSTEMS', stable):
            document = kx.read_exchange(target)
        self.assertEqual(document['unreadable_games'], [KEY])
        self.assertEqual(set(document['knowledge']['consoles']), {'md'})
        # A machine that never shared (the X68000) still refuses the file whole.
        from tests.test_paths_schema import x68_document
        other, _ = self.v3_file({x68_document()['game']: x68_document()})
        with self.assertRaises(ValueError):
            kx.read_exchange(other)

    def test_what_is_not_qualified_for_this_romset_and_engine_is_not_shared(self):
        Library().keep(self, a_record())
        cases = {'a conversion that did not pass': library_report(native_validation={'passed': False}),
                 'a record the report does not name': library_report(knowledge={'record_sha256': '0' * 64}),
                 'no knowledge block': {key: value for key, value in library_report().items() if key != 'knowledge'}}
        for name, value in cases.items():
            with self.subTest(name):
                self.path.write_text(json.dumps(value), encoding='utf-8')
                game = SimpleNamespace(system='cps1', identity=IDENTITY, title='T', report=str(self.path), source='',
                                       watch='', status='current')
                found = self.collect(game)
                self.assertEqual((found['games'], found['payload']['consoles']), (0, {}))
        # A record built by another engine revision stays private.
        other = a_record()
        other['cpus']['m68k']['core'] = '9' * 40
        Library().keep(self, other)
        self.assertEqual(self.collect()['games'], 0)
        # So does one that is not marked as made by a passing conversion.
        Library().keep(self, a_record(), fresh_reference_passed=False)
        self.assertEqual(self.collect()['games'], 0)

    def test_a_conversion_with_nothing_new_is_noted_with_a_record_without_paths(self):
        Library().keep(self, a_record())
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: a_record()})
        found = self.collect()
        self.assertEqual((found['games'], found['omitted']['already_known']), (0, 1))
        stub = found['converted']['cps1'][IDENTITY]
        self.assertEqual(stub['level'], 'standard')
        self.assertEqual(cps1_knowledge.rows(stub['record']), ([], []))
        cps1_knowledge.validate_record(stub['record'], IDENTITY)

    def test_import_keeps_the_side_bank_apart_and_adds_only_what_is_new(self):
        shared = self.root / 'share.rrknowledge'
        record = a_record()
        found = {'games': 1, 'consoles': {'cps1': 1}, 'discoveries': 2, 'omitted': {}, 'observations': {},
                 'observation_count': 0, 'payload': {'schema': 1, 'consoles': {'cps1': {IDENTITY: record}}},
                 'titles': {'cps1': {IDENTITY: 'Test Game'}}, 'levels': {}, 'converted': {}}
        kx.write_knowledge(found, shared, channel=None, version=3)
        preview = kx.preview_import(shared)
        self.assertEqual((preview['games'], preview['discoveries'], preview['consoles']), (1, 2, {'cps1': 1}))
        outcome = kx.import_knowledge(shared)
        self.assertEqual((outcome['new'], outcome['consoles']), (1, {'cps1': 1}))
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), record)
        self.assertEqual(knowledge.read(self.imported), {'schema': 1, 'consoles': {}}, 'the schema 1 bank is untouched')
        self.assertEqual(kx.import_knowledge(shared)['unchanged'], 1)
        # More paths for the same romset join the same record.
        richer = a_record(extra={('m68k_ram', (0xff0100, 0x10, 2))})
        found['payload']['consoles']['cps1'][IDENTITY] = richer
        kx.write_knowledge(found, shared, channel=None, version=3)
        self.assertEqual(kx.import_knowledge(shared)['enriched'], 1)
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), richer)
        # A bank that is already known adds nothing.
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: richer})
        self.assertEqual(kx.preview_import(shared)['games'], 0)

    def test_fetched_records_are_checked_like_a_shared_file_and_a_damaged_one_is_skipped(self):
        damaged = a_record()
        damaged['cpus']['z80']['core'] = 'not a core'
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        outcome = kx.import_fetched({KEY: {'records': [damaged, newer, a_record()], 'observations': [[14, 1, 0, 2, 0]]}})
        self.assertEqual(outcome['accepted'][KEY], {'records': 1, 'observations': 0})
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), a_record())

    def test_the_per_account_route_never_asks_for_cps1(self):
        self.assertEqual(online._rom_keys([KEY, 'md:' + 'a' * 64], live=True), ['md:' + 'a' * 64])
        self.assertEqual(online._rom_keys([KEY, 'md:' + 'a' * 64]), sorted([KEY, 'md:' + 'a' * 64]))


class BaseTests(shared_base.BaseHarness):
    """The base carries CPS-1 (format 3 holds it); the converter qualifies what its engine qualified and keeps the rest to check."""

    def setUp(self):
        super().setUp()
        Library().start(self)
        self.addCleanup(knowledge._side_games.cache_clear)
        self.engines['cps1'] = cps1_knowledge.engine()

    def entry(self, *, qualified=(), parts=()):
        value = {'format': 3, 'system': 'cps1', 'identity': IDENTITY,
                 'qualified': sorted(qualified, key=lambda item: item['cores']),
                 'parts': sorted(parts, key=lambda item: item['source'])}
        return hashlib.sha256(kx.canonical_bytes(value)).hexdigest(), value

    def publish3(self, version, sha, sources, value):
        self.publish(version, {KEY: (sha, sources)}, entries=[(sha, value)])

    def test_qualified_for_this_engine_goes_to_the_qualified_side_bank_the_rest_is_to_check(self):
        mine = a_record()
        other = a_record(extra={('m68k_ram', (0xff0200, 0x20, 2))})
        other['cpus']['m68k']['core'] = '9' * 40            # an earlier revision of the engine
        sha, value = self.entry(
            qualified=[{'cores': kx.record_engine('cps1', mine), 'level': 'extended', 'by': 'players', 'record': mine},
                       {'cores': kx.record_engine('cps1', other), 'level': 'standard', 'by': 'maintainer', 'record': other}],
            parts=[{'source': 47, 'level': 'standard', 'record': a_record(extra={('m68k_ram', (0xff0300, 0x30, 2))}),
                    'observations': [[14, 1, 0, 2, 0]]}])
        self.publish3(5, sha, [47], value)
        prepared = online.prepare_batch([KEY])
        self.assertEqual((prepared['base']['version'], prepared['base']['games'], prepared['base']['qualified']), (5, 1, 1))
        self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), mine)
        # The imported side bank holds what is still to check: the other revision's and the waiting part's paths.
        imported = knowledge.imported_game('cps1', IDENTITY)
        self.assertEqual(cps1_knowledge.entry_set(imported) >= cps1_knowledge.entry_set(mine), True)
        self.assertIn(('m68k_ram', (0xff0300, 0x30, 2)), cps1_knowledge.entry_set(imported))
        self.assertEqual(knowledge.imported_observations('cps1', IDENTITY), [], 'no raw rows for CPS-1')
        self.assertEqual(knowledge.read(self.imported), {'schema': 1, 'consoles': {}}, 'schema 1 banks untouched')
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['sources'], use['qualified']['by'], use['qualified']['engine']),
                         ([47], 'players', cps1_knowledge.engine()))
        self.assertEqual(online.shared_paths([KEY])[KEY]['level'], 'extended')

    def test_a_new_engine_revision_makes_every_qualified_path_wait_again(self):
        mine = a_record()
        sha, value = self.entry(qualified=[{'cores': kx.record_engine('cps1', mine), 'level': 'standard',
                                            'by': 'players', 'record': mine}])
        self.publish3(5, sha, [], value)
        online.prepare_batch([KEY])
        self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), mine)
        # The converter's CPS-1 code moves (cores change): the qualified paths leave the qualified bank and
        # come back as paths to check, with their level.
        self.engines['cps1'] = '1' * 40 + ':' + '2' * 40
        online.prepare_batch([KEY], now=self.later())
        self.assertEqual(knowledge.qualified_game('cps1', IDENTITY), {})
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), mine)
        self.assertFalse(knowledge.qualified_v3_path().exists())

    def test_a_revoked_source_withdraws_the_imported_paths(self):
        part = {'source': 47, 'level': 'standard', 'record': a_record(), 'observations': []}
        sha, value = self.entry(parts=[part])
        self.publish3(5, sha, [47], value)
        online.prepare_batch([KEY])
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), a_record())
        self.server.base['manifest']['revoked'] = [47]
        online.prepare_batch([KEY], now=self.later())
        self.assertEqual(knowledge.imported_game('cps1', IDENTITY), {})

    def test_an_entry_of_a_format_this_converter_does_not_know_gives_nothing_and_breaks_nothing(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        sha, value = self.entry(parts=[{'source': 47, 'level': 'standard', 'record': newer, 'observations': []}],
                                qualified=[{'cores': kx.record_engine('cps1', newer), 'level': 'standard',
                                            'by': 'players', 'record': newer}])
        self.publish3(5, sha, [47], value)
        online.prepare_batch([KEY])
        self.assertEqual((knowledge.qualified_game('cps1', IDENTITY), knowledge.imported_game('cps1', IDENTITY)), ({}, {}))


class StampTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_the_knowledge_stamp_follows_the_side_banks(self):
        from retrorecomp.compilation_inputs import knowledge_stamp
        empty = knowledge_stamp('cps1', IDENTITY)
        self.assertEqual(empty, hashlib.sha256(b'{}').hexdigest())
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: a_record()})
        qualified = knowledge_stamp('cps1', IDENTITY)
        self.assertNotEqual(qualified, empty)
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record(extra={('m68k_ram', (0xff0100, 0x10, 2))})})
        self.assertNotEqual(knowledge_stamp('cps1', IDENTITY), qualified)


class ReportTests(unittest.TestCase):
    def test_the_report_says_whether_cps1_is_in_the_sharing_not_always_yes(self):
        from retrorecomp import cps1_conversion
        record = a_record()
        promotion = {'paths': {'m68k_ram': 1, 'z80_ram': 1}, 'm68k_ram': {}, 'm68k_gfx': {}, 'z80_ram': {}, 'truncated': False}
        shared = cps1_conversion.knowledge_block(record, promotion, {})
        self.assertIs(shared['shared'], True)
        self.assertEqual(shared['cores'], cps1_knowledge.engine())
        self.assertEqual(shared['record_sha256'], cps1_knowledge.record_digest(record))
        stable = pp.STABLE_SHARED
        with patch.object(pp, 'SHARED_SYSTEMS', stable):
            self.assertIs(cps1_conversion.knowledge_block(record, promotion, {})['shared'], False)


class LabelTests(unittest.TestCase):
    def test_the_experimental_label_stays_and_does_not_gate_the_sharing(self):
        from retrorecomp.systems.cps1 import CPS1
        self.assertEqual(CPS1.status, 'experimental')
        self.assertIn('cps1', pp.EXPERIMENTAL_SHARED)
        self.assertIn('cps1', pp.SHARED_SYSTEMS)
        # Sharing code reads no status: the label is not an input of the collection or of the promotion.
        import inspect
        for function in (kx._collect_cps1, cps1_knowledge.promote, cps1_knowledge.shared_rows, kx.collect_knowledge):
            text = inspect.getsource(function)
            self.assertNotIn('.status', text.replace("getattr(game, 'status'", ''))
            self.assertNotIn('.experimental', text)

    def test_kind_14_is_not_read_by_the_converter(self):
        from retrorecomp import cps1_conversion
        import inspect
        self.assertEqual(CPS1_KINDS, {14, 15, 16})
        source = inspect.getsource(cps1_conversion.feedback_rows)
        self.assertIn(', 15)', source)
        self.assertIn(', 16)', source)
        self.assertNotIn(', 14)', source)
        # And no shared observation row exists for it: CPS-1 shares none.
        with self.assertRaises(ValueError):
            document = {'format': kx.FORMAT, 'version': 3, 'converter': '1.6.0', 'titles': {},
                        'knowledge': {'schema': 3, 'games': {KEY: a_record()}},
                        'observations': {'cps1': {IDENTITY: [[14, 1, 0, 2, 0]]}}}
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'x.rrknowledge'
                target.write_bytes(gzip.compress(json.dumps(document).encode()))
                kx.read_exchange(target)


from retrorecomp.systems.cps1 import CPS1 as _CPS1  # noqa: E402
CPS1_KINDS = set(_CPS1.feedback_kinds)


if __name__ == '__main__':
    unittest.main()
