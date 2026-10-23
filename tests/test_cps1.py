"""CPS-1 catalogue and romset identification. Synthetic ZIPs only; no ROMs needed."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from smsrecomp import cps1, cps1_catalogue
from tools import build_cps1_catalogue as builder

ROOT = Path(__file__).resolve().parents[1]


def blob(seed, size):
    return hashlib.sha256(seed.encode()).digest() * (size // 32) + hashlib.sha256(seed.encode()).digest()[:size % 32]


def load(op, name, offset, data):
    return {'op': op, 'name': name, 'offset': offset, 'bytes': len(data), 'crc32': zlib.crc32(data),
            'sha1': hashlib.sha1(data).hexdigest()}


class BundledCatalogueTests(unittest.TestCase):
    def test_integrity_scope_and_board_references(self):
        data = cps1_catalogue.catalogue()
        games = data['games']
        self.assertEqual(data['source']['revision'], builder.MAME_REVISION)
        self.assertEqual(len(games), 233)
        phase1 = [game for game in games if cps1_catalogue.supported(game)]
        self.assertEqual(len(phase1), 129)
        self.assertEqual(len({game['parent'] or game['set'] for game in phase1}), 28)
        self.assertEqual(sum(game['rotation'] == 270 for game in phase1), 13)
        for game in games:
            self.assertIn(game['board'], data['boards'])
            self.assertIn(game['mapper'], data['mappers'])
            self.assertTrue(cps1_catalogue.program_files(game), game['set'])
        sets = cps1_catalogue.by_set()
        self.assertEqual((sets['ffight']['board'], sets['ffight']['mapper']), ('CPS_B_04', 'S224B'))
        self.assertEqual(sets['sf2']['ports'][0], 0x36)
        self.assertEqual((sets['wof']['support'], sets['wof']['reason']), ('excluded', 'qsound'))
        self.assertIn('QSound', cps1_catalogue.unsupported_reason(sets['wof']))
        self.assertEqual(sets['sf2qp1']['reason'], 'bootleg_or_hack')
        self.assertEqual(sets['forgottn']['reason'], 'dial')
        self.assertEqual(sets['1941']['rotation'], 270)

    def test_file_sizes_include_continued_parts(self):
        audio = [item for item in cps1_catalogue.files(cps1_catalogue.by_set()['ffight']) if item['region'] == 'audiocpu']
        self.assertEqual([(item['name'], item['bytes']) for item in audio], [('ff_09.12b', 0x10000)])

    def test_unverified_mappers_and_suspect_dumps_are_not_evidence(self):
        sets = cps1_catalogue.by_set()
        self.assertTrue(cps1_catalogue.qualification_candidate(sets['ffight']))
        for name in ('gulunpa', 'striderua', 'sf2ceec', 'pokonyan'):
            self.assertTrue(cps1_catalogue.supported(sets[name]))
            self.assertFalse(cps1_catalogue.qualification_candidate(sets[name]), name)

    @unittest.skipUnless((ROOT / '.deps' / ('mame-cps1-' + builder.MAME_REVISION[:7])).is_dir(),
                         'pinned MAME sources are not cached')
    def test_catalogue_rebuilds_byte_for_byte(self):
        data = builder.encode(builder.build(ROOT / '.deps' / ('mame-cps1-' + builder.MAME_REVISION[:7]), offline=True))
        self.assertEqual(hashlib.sha256(data).hexdigest(), cps1_catalogue.SHA256)


class BuilderParsingTests(unittest.TestCase):
    SOURCE = '''
#define CODE_SIZE 0x400000
ROM_START( demo ) /* "quoted" // not a comment start */
	ROM_REGION( CODE_SIZE, "maincpu", 0 ) // 68000
	ROM_LOAD16_BYTE( "a.1", 0x00000, 0x20000, CRC(12345678) SHA1(0123456789abcdef0123456789abcdef01234567) )
	ROM_REGION( 0x18000, "audiocpu", 0 )
	ROM_LOAD( "s.1", 0x00000, 0x08000, BAD_DUMP CRC(9abcdef0) SHA1(0123456789abcdef0123456789abcdef01234567) )
	ROM_CONTINUE( 0x10000, 0x08000 )
	ROM_REGION( 0x0200, "bboardplds", 0 )
	ROM_LOAD( "pal.1a", 0x0000, 0x0117, NO_DUMP )
ROM_END
'''

    def test_rom_blocks_comments_macros_and_flags(self):
        text = builder.strip_comments(self.SOURCE)
        sets = builder.rom_sets(text, builder.object_macros(text))
        regions = sets['demo']
        self.assertEqual([region['tag'] for region in regions], ['maincpu', 'audiocpu'])
        self.assertEqual(regions[0]['bytes'], 0x400000)
        self.assertEqual(regions[0]['loads'][0]['crc32'], 0x12345678)
        self.assertEqual(regions[1]['loads'][0]['bad_dump'], 1)
        self.assertEqual(regions[1]['loads'][1], {'op': 'continue', 'offset': 0x10000, 'bytes': 0x8000})

    def test_unknown_rom_macros_stop_the_build(self):
        text = builder.strip_comments(self.SOURCE.replace('ROM_CONTINUE', 'ROM_MYSTERY'))
        with self.assertRaises(SystemExit):
            builder.rom_sets(text, builder.object_macros(text))


class IdentificationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.data = {name: blob(name, 64) for name in ('a.p1', 'a.p2', 'c.p1', 's.a', 'g.1', 'o.1')}
        self.data['s.a'] = blob('s.a', 32)

        def regions(program):
            sound = self.data['s.a']
            return [{'tag': 'maincpu', 'bytes': 256, 'erase': None,
                     'loads': [load('load16_byte', program, 0, self.data[program]),
                               load('load16_byte', 'a.p2', 1, self.data['a.p2'])]},
                    {'tag': 'audiocpu', 'bytes': 64, 'erase': None,
                     'loads': [dict(load('load', 's.a', 0, sound), bytes=16), {'op': 'continue', 'offset': 32, 'bytes': 16}]},
                    {'tag': 'gfx', 'bytes': 512, 'erase': None, 'loads': [load('load64_word', 'g.1', 0, self.data['g.1'])]},
                    {'tag': 'oki', 'bytes': 64, 'erase': None, 'loads': [load('load', 'o.1', 0, self.data['o.1'])]}]

        def game(name, parent, program, support='phase1', reason=''):
            return {'set': name, 'parent': parent, 'title': name.title(), 'support': support, 'reason': reason,
                    'rotation': 0, 'board': 'CPS_B_04', 'mapper': 'S224B', 'mapper_verified': True,
                    'regions': regions(program)}
        self.games = [game('demo', '', 'a.p1'), game('democ', 'demo', 'c.p1'),
                      game('demob', 'demo', 'c.p1', 'excluded', 'bootleg_or_hack')]
        self.games[2]['regions'][2]['loads'][0] = load('load64_word', 'g.2', 0, blob('g.2', 64))

    def archive(self, name, members):
        path = self.folder / name
        with zipfile.ZipFile(path, 'w') as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        return path

    def parent_members(self, rename=False):
        names = ('a.p1', 'a.p2', 's.a', 'g.1', 'o.1')
        return {('fb_' + name if rename else name): self.data[name] for name in names}

    def test_complete_set_with_renamed_members_and_extra_plds(self):
        members = self.parent_members(rename=True) | {'s224b.1a': b'pld'}
        game = cps1.read_set(self.archive('renamed.zip', members), self.games)
        self.assertEqual((game.set_name, game.supported, len(game.members)), ('demo', True, 5))
        same = cps1.read_set(self.archive('demo.zip', self.parent_members()), self.games)
        self.assertEqual(game.sha256, same.sha256)

    def test_split_clone_reads_its_parent_beside_it(self):
        clone = self.archive('democ.zip', {'c.p1': self.data['c.p1']})
        with self.assertRaisesRegex(ValueError, 'Place demo.zip beside it'):
            cps1.read_set(clone, self.games)
        self.archive('demo.zip', self.parent_members())
        game = cps1.read_set(clone, self.games)
        self.assertEqual(game.set_name, 'democ')
        self.assertEqual(sum(member['archive'] != str(clone) for member in game.members), 4)

    def test_merged_archive_without_current_parent_picks_a_supported_clone(self):
        members = {name: self.data[name] for name in ('c.p1', 'a.p2', 's.a', 'g.1', 'o.1')} | {'g.2': blob('g.2', 64)}
        game = cps1.read_set(self.archive('demo.zip', members), self.games)
        self.assertEqual((game.set_name, game.alternatives), ('democ', ('demob',)))
        self.assertEqual(cps1.read_set(self.folder / 'demo.zip', self.games, set_name='demob').set_name, 'demob')

    def test_same_crc_with_other_contents_and_unknown_programs_are_refused(self):
        self.games[0]['regions'][3]['loads'][0]['sha1'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'different contents'):
            cps1.read_set(self.archive('demo.zip', self.parent_members()), self.games)
        with self.assertRaisesRegex(ValueError, 'not recognized'):
            cps1.identify_set(self.archive('other.zip', {'x.bin': b'unrelated'}), self.games)

    def test_quick_detection_needs_two_program_roms(self):
        self.assertTrue(cps1.looks_like_cps1_zip(self.archive('demo.zip', self.parent_members()), self.games))
        self.assertFalse(cps1.looks_like_cps1_zip(self.archive('one.zip', {'a.p1': self.data['a.p1']}), self.games))


if __name__ == '__main__':
    unittest.main()
