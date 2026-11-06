"""The adventure export (retrorecomp/scummvm_export.py, scummvm_build.py) on authored data only: no game, no ScummVM run."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import scummvm_build, scummvm_export as sx


class PackFormat(unittest.TestCase):
    def test_pack_round_trip_is_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            program = root / 'program.bin'
            program.write_bytes(b'MZ' + bytes(range(256)) * 4)
            game = root / 'game'
            (game / 'sub').mkdir(parents=True)
            (game / 'A.DAT').write_bytes(bytes(range(200)))
            (game / 'sub' / 'b.bin').write_bytes(b'\x00\xff' * 1000)
            (game / 'empty.txt').write_bytes(b'')
            (game / 'stub.scummvm').write_bytes(b'')
            out = root / 'out' / 'Game.exe'
            files, data = sx.write_pack(program, game, out, sx.manifest_text('target', 'Name', '0123456789ab'),
                                        extra=(('.rr/selftest.bin', bytes(range(256))),))
            self.assertEqual((files, data), (3, 200 + 2000))
            blob = out.read_bytes()
            self.assertTrue(blob.startswith(program.read_bytes()))
            index = {name: (start, size) for name, start, size in sx.read_pack_index(out)}
            self.assertEqual(sorted(index), ['.rr/launch.ini', '.rr/selftest.bin', 'A.DAT', 'empty.txt', 'sub/b.bin'])
            for name, path in (('A.DAT', game / 'A.DAT'), ('sub/b.bin', game / 'sub' / 'b.bin')):
                start, size = index[name]
                self.assertEqual(blob[start:start + size], path.read_bytes())
            start, size = index['.rr/launch.ini']
            self.assertIn(b'target=target\nname=Name\nid=0123456789ab\n', blob[start:start + size])
            self.assertFalse(out.with_name('Game.exe.part').exists())

    def test_an_exe_without_pack_has_no_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / 'plain.exe'
            plain.write_bytes(b'MZ' + b'\0' * 100)
            self.assertEqual(sx.read_pack_index(plain), [])


class Names(unittest.TestCase):
    def test_titles_follow_the_export_convention(self):
        self.assertEqual(sx.exe_title('The Example Game'), 'Example Game, The')
        self.assertEqual(sx.exe_title('Example II: The Subtitle'), 'Example II - The Subtitle')
        self.assertEqual(sx.exe_title('Odd <name>?'), 'Odd name')
        self.assertEqual(sx.datas_name("Example's Game: Part 2!"), 'Example_s_Game_Part_2')

    def test_id_depends_on_names_and_sizes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / 'x.dat').write_bytes(b'abc')
            first = sx.folder_id(game)
            (game / 'x.dat').write_bytes(b'xyz')            # same size, other bytes
            self.assertEqual(sx.folder_id(game), first)
            (game / 'x.dat').write_bytes(b'abcd')
            self.assertNotEqual(sx.folder_id(game), first)
            self.assertRegex(first, r'^[0-9a-f]{12}$')


class Detection(unittest.TestCase):
    OUTPUT = ('GameID     Description     Full Path\n'
              '---------- --------------- ---------\n'
              'eng1:gamea                     Game A (CD/DOS/French)                  C:\\games\\a\\\n'
              'eng1:gamea                     Game A (DOS/German)                     C:\\games\\a\\\n'
              'eng2:gameb                     Game B: Sub (Windows/English)           C:\\games\\a\\sub\\\n')

    def test_candidates_of_the_folder_only(self):
        found = sx.parse_detection(self.OUTPUT, Path('C:/games/a'))
        self.assertEqual([(c.engine, c.gameid, c.language, c.platform) for c in found],
                         [('eng1', 'gamea', 'French', 'CD/DOS'), ('eng1', 'gamea', 'German', 'DOS')])
        self.assertEqual(found[0].title, 'Game A')


class Families(unittest.TestCase):
    def test_family_rule_is_generic(self):
        self.assertEqual(scummvm_build.family_for('anyengine'), 'anyengine')
        self.assertEqual(scummvm_build.engines_for('anyengine'), ('anyengine',))
        self.assertIn('scumm_7_8', scummvm_build.engines_for(scummvm_build.family_for('scumm')))
        self.assertEqual(scummvm_build.engines_for(scummvm_build.DETECT_FAMILY), scummvm_build.DETECT_ENGINES)

    def test_runtime_identity_names_the_pins(self):
        identity = scummvm_build.runtime_identity('scumm')
        self.assertEqual(identity['scummvm_commit'], scummvm_build.SCUMMVM_REV)
        self.assertEqual(identity['gui_languages'], ['en', 'fr', 'de', 'es', 'it'])
        self.assertRegex(identity['patch_sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
