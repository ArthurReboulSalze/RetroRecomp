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
              'eng2:gameb                     Game B: Sub (Windows/English)           C:\\games\\a\\sub\\\n'
              'eng3:gamec                     Game Part V: The End (DOS/French) C:\\games\\c\\\n')

    def test_a_colon_in_the_title_is_not_a_drive(self):
        found = sx.parse_detection(self.OUTPUT, Path('C:/games/c'))
        self.assertEqual([(c.gameid, c.title, c.language) for c in found], [('gamec', 'Game Part V: The End', 'French')])

    def test_candidates_of_the_folder_only(self):
        found = sx.parse_detection(self.OUTPUT, Path('C:/games/a'))
        self.assertEqual([(c.engine, c.gameid, c.language, c.platform) for c in found],
                         [('eng1', 'gamea', 'French', 'CD/DOS'), ('eng1', 'gamea', 'German', 'DOS')])
        self.assertEqual(found[0].title, 'Game A')


class PackedData(unittest.TestCase):
    """Platforms without embedded resources (Linux) carry the engine data and the GUI themes in the pack."""

    def test_collect_data_follows_the_resource_lists_of_the_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, family = Path(tmp) / 'tree', Path(tmp) / 'family'
            (tree / 'gui/themes').mkdir(parents=True)
            (tree / 'dists/engine-data').mkdir(parents=True)
            for name in ('scummremastered.zip', 'gui-icons.dat', 'shaders.dat'):
                (tree / 'gui/themes' / name).write_bytes(b'x')
            (tree / 'dists/engine-data/alpha.dat').write_bytes(b'a')
            (tree / 'dists/engine-data/fonts.dat').write_bytes(b'f')
            (tree / 'dists/engine-data/core.dat').write_bytes(b'c')
            (tree / 'dists/engine-data/beta.dat').write_bytes(b'b')
            (tree / 'dists/engine-data/engine_data_core.mk').write_text(
                'DIST_FILES_LIST += dists/engine-data/core.dat\n', encoding='utf-8')
            (tree / 'dists/engine-data/engine_data.mk').write_text(
                'ifdef ENABLE_ALPHA\nDIST_FILES_LIST += dists/engine-data/alpha.dat\nendif\n'
                'ifdef ENABLE_BETA\nDIST_FILES_LIST += dists/engine-data/beta.dat\nendif\n'
                'ifdef USE_FREETYPE2\nDIST_FILES_LIST += dists/engine-data/fonts.dat\nendif\n'
                'ifdef ENABLE_ALPHA\nDIST_FILES_LIST += dists/engine-data/missing.dat\nendif\n', encoding='utf-8')
            self.assertEqual(scummvm_build.collect_data(tree, family, ('alpha',)),
                             ['alpha.dat', 'core.dat', 'fonts.dat', 'gui-icons.dat', 'scummremastered.zip'])

    def test_a_runtime_with_data_beside_it_packs_it_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'scummvm-runtime'
            runtime.write_bytes(b'ELF')
            self.assertEqual(sx.data_members(runtime), ())
            (Path(tmp) / 'data').mkdir()
            (Path(tmp) / 'data' / 'lure.dat').write_bytes(b'LURE')
            self.assertEqual(sx.data_members(runtime), (('.rr/data/lure.dat', b'LURE'),))
        self.assertNotIn('data=1', sx.manifest_text('t', 'N', 'i'))
        self.assertTrue(sx.manifest_text('t', 'N', 'i', data=True).endswith('data=1\n'))


class SharedPreparation(unittest.TestCase):
    """batch._needs_shared: a batch of emulated games alone does not build the Z80 translator or the shared SDL2."""

    def items(self, *systems, **flags):
        from retrorecomp.batch import BatchItem
        return [BatchItem(Path(f'g{i}'), f'g{i}', system, **flags) for i, system in enumerate(systems)]

    def test_emulated_only_batch_skips_the_preparation(self):
        from retrorecomp.batch import _needs_shared
        items = self.items('scummvm', 'scummvm')
        self.assertFalse(_needs_shared(items, [0, 1]))

    def test_a_mixed_batch_or_an_empty_one_prepares(self):
        from retrorecomp.batch import _needs_shared
        items = self.items('scummvm', 'sms')
        self.assertTrue(_needs_shared(items, [0, 1]))
        self.assertFalse(_needs_shared(items, [0]))
        self.assertTrue(_needs_shared(items, []))            # nothing queued: as before

    def test_skipped_unknown_or_failed_items_do_not_count(self):
        from retrorecomp.batch import BatchItem, _needs_shared
        items = [BatchItem(Path('a'), 'a', 'scummvm'), BatchItem(Path('b'), 'b', 'sms', skipped=True),
                 BatchItem(Path('c'), 'c', 'nes', error='unreadable'), BatchItem(Path('d'), 'd', '', unknown=True)]
        self.assertFalse(_needs_shared(items, [0, 1, 2, 3]))


class RelativeFolder(unittest.TestCase):
    def test_a_relative_folder_matches_the_absolute_path_scummvm_prints(self):
        import os
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            (parent / 'game').mkdir()
            line = f'eng1:gamea                     Game A (DOS/English)                  {parent / "game"}\n'
            before = os.getcwd()
            os.chdir(parent)
            try:
                with mock.patch.object(sx.subprocess, 'run', return_value=mock.Mock(stdout=line)):
                    found = sx.detect(Path('game'), Path('runtime'))
            finally:
                os.chdir(before)
            self.assertEqual([(c.gameid, c.language) for c in found], [('gamea', 'English')])


class Families(unittest.TestCase):
    def test_family_rule_is_generic(self):
        self.assertEqual(scummvm_build.family_for('anyengine'), 'anyengine')
        self.assertEqual(scummvm_build.engines_for('anyengine'), ('anyengine',))
        self.assertIn('scumm_7_8', scummvm_build.engines_for(scummvm_build.family_for('scumm')))
        self.assertTrue(scummvm_build.engines_for(scummvm_build.DETECT_FAMILY))

    def test_fallback_engines_are_read_from_the_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for engine, text in (('alpha', 'ADDetectedGame fallbackDetectExtern(uint md5Bytes) const;'), ('beta', 'nothing')):
                (tree / 'engines' / engine).mkdir(parents=True)
                (tree / 'engines' / engine / 'metaengine.cpp').write_text(text, encoding='utf-8')
            self.assertEqual(scummvm_build.fallback_engines(tree), ('alpha',))

    def test_static_sdl_system_libraries_follow_its_pkg_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            self.assertEqual(scummvm_build.static_system_libraries(prefix), ['m', 'dl', 'pthread'])     # no file: the default
            (prefix / 'lib' / 'pkgconfig').mkdir(parents=True)
            (prefix / 'lib' / 'pkgconfig' / 'sdl2.pc').write_text(
                'Libs: -L${libdir} -lSDL2\nLibs.private: -lm -ldl -lpthread -lrt -lm -Wl,--no-undefined\n', encoding='utf-8')
            self.assertEqual(scummvm_build.static_system_libraries(prefix), ['m', 'dl', 'pthread', 'rt'])

    def test_runtime_identity_names_the_pins(self):
        identity = scummvm_build.runtime_identity('scumm')
        self.assertEqual(identity['scummvm_commit'], scummvm_build.SCUMMVM_REV)
        self.assertEqual(identity['gui_languages'], ['en', 'fr', 'de', 'es', 'it'])
        self.assertRegex(identity['patch_sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
