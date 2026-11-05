"""CPS-2 catalogue and romset identification. Synthetic ZIPs only; no ROMs and no keys needed."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from retrorecomp import cps1, cps1_catalogue, cps2, cps2_catalogue
from tools import build_cps2_catalogue as builder

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.deps' / ('mame-cps1-' + builder.MAME_REVISION[:7])


def blob(seed, size):
    return hashlib.sha256(seed.encode()).digest() * (size // 32) + hashlib.sha256(seed.encode()).digest()[:size % 32]


def load(op, name, offset, data):
    return {'op': op, 'name': name, 'offset': offset, 'bytes': len(data), 'crc32': zlib.crc32(data),
            'sha1': hashlib.sha1(data).hexdigest()}


class BundledCatalogueTests(unittest.TestCase):
    def test_integrity_scope_and_references(self):
        data = cps2_catalogue.catalogue()
        games = data['games']
        self.assertEqual(data['source']['revision'], builder.MAME_REVISION)
        self.assertEqual(len(games), 324)
        phase1 = [game for game in games if cps2_catalogue.supported(game)]
        self.assertEqual(len(phase1), 258)
        reasons = {}
        for game in games:
            if not cps2_catalogue.supported(game):
                reasons[game['reason']] = reasons.get(game['reason'], 0) + 1
        self.assertEqual(reasons, {'bootleg_or_hack': 47, 'special_init': 10, 'network_adapter': 7, 'dead_board': 2})
        # the board and the graphics mapper are the CPS-1 catalogue's own
        boards, mappers = cps1_catalogue.catalogue()['boards'], cps1_catalogue.catalogue()['mappers']
        for game in games:
            self.assertIn(game['board'], boards)
            self.assertIn(game['mapper'], mappers)
            self.assertTrue(cps2_catalogue.program_files(game), game['set'])
        sets = cps2_catalogue.by_set()
        self.assertEqual((sets['ssf2']['board'], sets['ssf2']['mapper'], sets['ssf2']['machine']), ('CPS_B_21_DEF', 'cps2', 'cps2'))
        self.assertEqual(sets['19xx']['rotation'], 270)
        self.assertEqual(sets['ecofghtr']['reason'], 'special_init')
        self.assertEqual(sets['ssf2tb']['reason'], 'network_adapter')
        self.assertEqual(sets['ssf2us2']['reason'], 'bootleg_or_hack')

    def test_every_set_names_its_key_and_the_catalogue_holds_no_key(self):
        for game in cps2_catalogue.games():
            if game['machine'] == 'gigaman2':
                continue
            key = cps2_catalogue.key_file(game)
            self.assertEqual(key['bytes'], 20)
            self.assertEqual(len(key['sha1']), 40)
        raw = (ROOT / 'assets' / 'cps2-catalogue.json').read_bytes()
        # the key regions carry a name and hashes only: no load of the catalogue is a 20-byte literal
        self.assertNotIn(b'"data"', raw)
        self.assertNotIn(b'"bytes_hex"', raw)

    def test_the_ports_of_the_standard_blocks(self):
        sets = cps2_catalogue.by_set()
        self.assertEqual(sets['ssf2']['input'], 'cps2_2p6b')
        players = {entry[2] for port in sets['ddtod']['inputs'].values() for entry in port['inputs']}
        self.assertEqual(players, {1, 2, 3, 4})

    @unittest.skipUnless((CACHE / 'cps2.cpp').is_file() and (CACHE / 'cps1_v.cpp').is_file() and (CACHE / 'ioport.cpp').is_file(),
                         'pinned MAME sources are not cached')
    def test_catalogue_rebuilds_byte_for_byte(self):
        data = builder.encode(builder.build(CACHE, offline=True))
        self.assertEqual(hashlib.sha256(data).hexdigest(), cps2_catalogue.SHA256)


class IdentificationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.data = {name: blob(name, 64) for name in ('d.03', 'd.04', 'd.05', 'g.1', 'q.1', 'z.1', 'e.key', 'c.03', 'c.key')}
        self.data['z.1'] = blob('z.1', 32)       # 16 bytes loaded, 16 continued: the member is 32 bytes
        self.data['e.key'] = blob('e.key', 20)
        self.data['c.key'] = blob('c.key', 20)

        def regions(program, key):
            return [{'tag': 'maincpu', 'bytes': 256, 'erase': None,
                     'loads': [load('load16_word_swap', program, 0, self.data[program]),
                               load('load16_word_swap', 'd.04', 0x40, self.data['d.04']),
                               load('load16_word_swap', 'd.05', 0x80, self.data['d.05'])]},
                    {'tag': 'gfx', 'bytes': 512, 'erase': None, 'loads': [load('load64_word', 'g.1', 0, self.data['g.1'])]},
                    {'tag': 'audiocpu', 'bytes': 64, 'erase': None,
                     'loads': [dict(load('load', 'z.1', 0, self.data['z.1']), bytes=16), {'op': 'continue', 'offset': 32, 'bytes': 16}]},
                    {'tag': 'qsound', 'bytes': 64, 'erase': None, 'loads': [load('load', 'q.1', 0, self.data['q.1'])]},
                    {'tag': 'key', 'bytes': 32, 'erase': None, 'loads': [load('load', key, 0, self.data[key])]}]

        def game(name, parent, program, key):
            return {'set': name, 'parent': parent, 'title': name.title() + ': Test', 'support': 'phase1', 'reason': '',
                    'rotation': 0, 'board': 'CPS_B_21_DEF', 'mapper': 'cps2', 'machine': 'cps2',
                    'regions': regions(program, key)}
        self.games = [game('demo', '', 'd.03', 'e.key'), game('democ', 'demo', 'c.03', 'c.key')]

    def archive(self, name, members):
        path = self.folder / name
        with zipfile.ZipFile(path, 'w') as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        return path

    def parent_members(self):
        return {name: self.data[name] for name in ('d.03', 'd.04', 'd.05', 'g.1', 'q.1', 'z.1', 'e.key')}

    def test_complete_set_with_its_key_is_read_and_the_key_is_a_member(self):
        game = cps2.read_set(self.archive('demo.zip', self.parent_members()), self.games)
        self.assertEqual((game.set_name, game.system_id, game.tier, game.supported, len(game.members)), ('demo', 'cps2', 'experimental', True, 7))
        self.assertEqual(game.key_member['name'], 'e.key')
        self.assertEqual(game.title, 'Demo - Test')
        # the identity hashes the key file too: another key is another set of bytes
        other = dict(self.parent_members(), **{'e.key': blob('other', 20)})
        self.games[0]['regions'][4]['loads'][0] = load('load', 'e.key', 0, other['e.key'])
        self.assertNotEqual(cps2.read_set(self.archive('o.zip', other), self.games).sha256, game.sha256)

    def test_a_romset_without_its_key_is_refused_by_name(self):
        members = self.parent_members()
        del members['e.key']
        with self.assertRaisesRegex(ValueError, r'missing e\.key.*key file e\.key is not in the archive.*never supplies one'):
            cps2.read_set(self.archive('demo.zip', members), self.games)

    def test_a_key_with_the_right_size_but_other_contents_is_refused(self):
        members = self.parent_members()
        members['e.key'] = bytes(20)
        with self.assertRaisesRegex(ValueError, 'missing e.key'):
            cps2.read_set(self.archive('demo.zip', members), self.games)

    def test_split_clone_reads_its_parent_beside_it(self):
        clone = self.archive('democ.zip', {'c.03': self.data['c.03'], 'c.key': self.data['c.key']})
        with self.assertRaisesRegex(ValueError, 'Place demo.zip beside it'):
            cps2.read_set(clone, self.games)
        self.archive('demo.zip', self.parent_members())
        game = cps2.read_set(clone, self.games)
        self.assertEqual(game.set_name, 'democ')
        self.assertEqual(game.key_member['name'], 'c.key')

    def test_the_two_families_do_not_read_each_others_archives(self):
        path = self.archive('demo.zip', self.parent_members())
        self.assertTrue(cps2.looks_like_cps2_zip(path, self.games))
        self.assertFalse(cps1.looks_like_cps1_zip(path))                  # against the real CPS-1 catalogue
        with self.assertRaisesRegex(ValueError, 'CPS-2 program ROMs not recognized'):
            cps2.identify_set(self.archive('other.zip', {'x.bin': b'unrelated'}), self.games)
        with self.assertRaisesRegex(ValueError, 'CPS-1 program ROMs not recognized'):
            cps1.identify_set(path)



class BoardTests(unittest.TestCase):
    def test_the_board_description_of_a_cps2_set(self):
        from retrorecomp import cps1_board
        lines = cps1_board.descriptor(cps2_catalogue.by_set()['ssf2']).splitlines()
        self.assertIn('machine cps2', lines)
        self.assertIn('z80_clock 8000000', lines)
        # 16 MHz x 0.7375, MAME's compensation for the waitstates it does not emulate (docs/CPS2.md)
        self.assertIn('cpu_clock 11800000', lines)
        self.assertIn('kludge 0', lines)
        self.assertTrue(any(line.startswith('input IN2 ') for line in lines))
        self.assertFalse(any(line.startswith('input DSW') for line in lines))      # a production CPS-2 board has no switches

    @unittest.skipUnless((ROOT / '.deps' / 'segagenesisrecomp' / 'runner' / 'm68k_interp.c').is_file(), 'the MC68000 translation engine is not checked out')
    def test_translated_pc_relative_reads_use_the_decrypted_view_only_on_a_cps2_board(self):
        from retrorecomp import cps1_codegen
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            cps1_codegen._semantics(project)
            plain = (project / 'cps1_step_semantics.h').read_text(encoding='utf-8')
            (project / 'board').mkdir()
            (project / 'board' / 'maincpu-op.bin').write_bytes(b'00')
            cps1_codegen._semantics(project)
            decrypted = (project / 'cps1_step_semantics.h').read_text(encoding='utf-8')
        self.assertNotIn('mem_read_pc', plain)
        self.assertEqual(decrypted.count('return mem_read_pc(sz,'), 2)       # (d16,PC) and (d8,PC,Xn) operands
        self.assertEqual(decrypted.count('movem_pc ? mem_read_pc('), 2)       # MOVEM from a PC-relative address, long and word
        self.assertIn('m68k_read_pcrelative_32', decrypted)


if __name__ == '__main__':
    unittest.main()
