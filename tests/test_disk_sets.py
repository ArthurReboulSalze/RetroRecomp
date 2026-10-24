"""Multi-disk X68000 games are queued once, as the equivalent ordered M3U."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from retrorecomp.batch import identify
from retrorecomp.rom_sources import RomSources, disk_sets, disk_tag
from retrorecomp.x68000 import read_input


def synthetic_dim(path, fill):
    """One stored 2HD track: the smallest DIM the console reader accepts."""
    header = bytearray(256)
    header[1] = 1
    path.write_bytes(bytes(header) + bytes([fill]) * 8 * 1024)
    return path


class DiskSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.roms = self.root / 'roms'
        self.roms.mkdir()
        self.sets = self.root / 'datas/x68000-sets'

    def tearDown(self):
        self.temp.cleanup()

    def disk(self, name, fill):
        return synthetic_dim(self.roms / name, fill)

    def test_names_of_set_members(self):
        self.assertEqual(disk_tag('Game (1990)(Pub)(Disk 2 of 3)(User).dim'), ('Game (1990)(Pub)', '', 2, 3))
        self.assertEqual(disk_tag('Game (Fix) (Disk 1) (System).dim'), ('Game (Fix)', '', 1, None))
        self.assertEqual(disk_tag('Game (Disk B).dim'), ('Game', '', 2, None))
        self.assertEqual(disk_tag('Game (Disk 1 of 2)(System)[a2].dim'), ('Game', '[a2]', 1, 2))
        self.assertIsNone(disk_tag('Game (Disk 3 of 2).dim'))
        self.assertIsNone(disk_tag('Diskette Game (Disked).dim'))

    def test_named_disks_become_the_equivalent_ordered_playlist(self):
        second = self.disk('Game (1990)(Pub)(Disk 2 of 2)(User).dim', 2)
        other = self.disk('Other (Pub).dim', 9)
        first = self.disk('Game (1990)(Pub)(Disk 1 of 2)(System).dim', 1)
        before = sorted(self.roms.iterdir())
        sets = disk_sets([second, other, first], self.sets)
        self.assertEqual(sets.grouped, 1)
        self.assertEqual(sets.incomplete, [])
        playlist, rest = sets.paths
        self.assertEqual(rest, other)
        self.assertTrue(playlist.is_relative_to(self.sets))
        self.assertEqual(playlist.name, 'Game (1990)(Pub).m3u')
        # Nothing is written beside the player's disks.
        self.assertEqual(sorted(self.roms.iterdir()), before)
        handwritten = self.root / 'Game.m3u'
        handwritten.write_text(f'{first}\n{second}\n', encoding='utf-8')
        self.assertEqual(read_input(playlist).disks, (first.resolve(), second.resolve()))
        self.assertEqual(read_input(playlist).sha256, read_input(handwritten).sha256)
        item = identify(playlist)
        self.assertEqual((item.system, item.title, item.error), ('x68', 'Game', ''))

    def test_one_disk_brings_the_rest_of_its_set_and_rewrites_nothing(self):
        first = self.disk('Game (Disk A).dim', 1)
        self.disk('Game (Disk B).dim', 2)
        self.disk('Game (Disk C).dim', 3)
        playlist = disk_sets([first], self.sets).paths[0]
        self.assertEqual(len(read_input(playlist).disks), 3)
        stamp = playlist.stat().st_mtime_ns
        self.assertEqual(disk_sets([first], self.sets).paths, [playlist])
        self.assertEqual(playlist.stat().st_mtime_ns, stamp)

    def test_alternate_dumps_stay_apart_and_gaps_are_reported(self):
        primary = [self.disk('Game (Disk 1 of 2).dim', 1), self.disk('Game (Disk 2 of 2).dim', 2)]
        alternate = self.disk('Game (Disk 1 of 2)[a].dim', 3)
        sets = disk_sets([*primary, alternate], self.sets)
        self.assertEqual(sets.grouped, 1)
        self.assertEqual(sets.paths[1], alternate)
        self.assertEqual(sets.incomplete, [('Game[a]', [2], 2)])
        gap = disk_sets([self.disk('Saga (Disk 1).dim', 4), self.disk('Saga (Disk 3).dim', 5)], self.sets)
        self.assertEqual(gap.incomplete, [('Saga', [2], 3)])
        self.assertEqual(len(read_input(gap.paths[0]).disks), 2)

    def test_a_players_own_playlist_keeps_its_disks(self):
        disks = [self.disk('Game (Disk 1 of 2).dim', 1), self.disk('Game (Disk 2 of 2).dim', 2)]
        own = self.roms / 'Game.m3u'
        own.write_text('Game (Disk 1 of 2).dim\nGame (Disk 2 of 2).dim\n', encoding='utf-8')
        sets = disk_sets([*disks, own], self.sets)
        self.assertEqual((sets.paths, sets.grouped), ([own], 0))
        self.assertFalse(self.sets.exists())

    def test_ambiguous_names_stay_separate(self):
        game = self.disk('Game (Disk 1 of 2)(Game).dim', 1)
        demo = self.disk('Game (Disk 1 of 2)(Demo).dim', 2)
        sets = disk_sets([game, demo], self.sets)
        self.assertEqual((sets.paths, sets.grouped), ([game, demo], 0))
        mixed = [self.disk('Mix (Disk 1 of 2).dim', 3), self.disk('Mix (Disk 2 of 3).dim', 4)]
        self.assertEqual(disk_sets(mixed, self.sets).paths, mixed)

    def test_source_lookup_finds_a_set_by_its_own_identity(self):
        disks = [self.disk('Game (Disk 1 of 2).dim', 1), self.disk('Game (Disk 2 of 2).dim', 2)]
        handwritten = self.root / 'Game.m3u'
        handwritten.write_text('\n'.join(map(str, disks)) + '\n', encoding='utf-8')
        game = SimpleNamespace(system='x68', identity=read_input(handwritten).sha256, title='Game',
                               source='', report=str(self.root / 'missing.json'))
        sources = RomSources(self.root / 'datas')
        (_, found), = sources.resolve([game], {'rom_paths': {'x68': str(self.roms)}})
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).is_relative_to(self.root / 'datas/x68000-sets'))
        self.assertEqual(read_input(found).sha256, game.identity)


if __name__ == '__main__':
    unittest.main()
