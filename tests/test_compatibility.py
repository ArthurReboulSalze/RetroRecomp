"""The newest converter version an export is compatible with (retrorecomp/compatibility.py, Arthur, 20 Nov 2026): from the
role stamps only, stored in the library's row, shown in Compiled games with « Converted with … · compatible … ». No ROM,
no export; the library is a temporary file."""
import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import compatibility
from retrorecomp.compiled_games import Game, Inventory

STAMPS = {'md': ('g' * 64, 'h' * 64, 'b' * 64), 'gb': ('G' * 64, 'H' * 64, 'B' * 64)}
TABLE = {'1.9.0': {'md': dict(zip(compatibility.ROLES, STAMPS['md'])), 'gb': dict(zip(compatibility.ROLES, STAMPS['gb']))}}


def running(system):
    return STAMPS[system]


def game(title, system='md', version='1.9.0', status='no_hints', index=1):
    base = 'C:/games' if os.name == 'nt' else '/games'               # absolute on its platform (C:/ is not on Linux)
    return Game(f'{base}/{system}/{title}.exe', system, f'{index:02x}' * 32, title, version=version, status=status)


def check(version='1.9.0', system='md', table=TABLE, now=running):
    return compatibility.compatible_version(version, system, table, now, running='1.9.1')


class FromTheStampsOnly(unittest.TestCase):
    def test_the_same_stamps_stamp_the_running_version(self):
        self.assertEqual(check(), '1.9.1')

    def test_a_different_host_stamp_stamps_nothing(self):
        moved = lambda system: (STAMPS[system][0], 'x' * 64, STAMPS[system][2])
        self.assertEqual(check(now=moved), '')

    def test_a_different_game_stamp_stamps_nothing(self):
        moved = lambda system: ('x' * 64,) + STAMPS[system][1:]
        self.assertEqual(check(now=moved), '')

    def test_a_different_build_stamp_stamps_nothing(self):
        moved = lambda system: STAMPS[system][:2] + ('x' * 64,)
        self.assertEqual(check(now=moved), '')

    def test_an_unrecorded_release_or_console_and_the_running_version_stamp_nothing(self):
        self.assertEqual(check(version='1.8.0'), '')
        self.assertEqual(check(system='nes', now=lambda system: ('n' * 64,) * 3), '')
        self.assertEqual(check(version='1.9.1'), '')                 # made by the running version: nothing to add
        self.assertEqual(check(version=''), '')

    def test_the_shipped_table_is_read_and_an_unknown_file_counts_as_empty(self):
        self.assertIsInstance(compatibility.load(), dict)
        folder = Path(tempfile.mkdtemp())
        (folder / 'other.json').write_text(json.dumps({'schema': 2, 'releases': TABLE}), encoding='utf-8')
        self.assertEqual(compatibility.load(folder / 'other.json'), {})
        self.assertEqual(compatibility.load(folder / 'missing.json'), {})

    def test_a_release_adds_its_own_entry_and_the_oldest_are_dropped(self):
        folder = Path(tempfile.mkdtemp())
        path = folder / 'release-stamps.json'
        for index in range(compatibility.KEEP_RELEASES + 3):
            path.write_text(json.dumps(compatibility.record(path, f'1.{index}.0', {'md': {}})), encoding='utf-8')
        releases = compatibility.load(path)
        self.assertEqual(len(releases), compatibility.KEEP_RELEASES)
        self.assertIn(f'1.{compatibility.KEEP_RELEASES + 2}.0', releases)
        self.assertNotIn('1.0.0', releases)


class InTheLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.inventory = Inventory(self.folder / 'compiled-games.json')
        self.rows = [game('Sonic', index=1), game('Tetris', 'gb', index=2), game('Gone', status='missing', index=3),
                     game('Old', version='1.8.0', index=4), game('Edited', status='changed', index=5)]
        for row in self.rows:
            self.inventory.remember(row)

    def update(self, now=running):
        return compatibility.update(self.inventory, TABLE, now, running='1.9.1')

    def test_rows_are_stamped_kept_apart_from_their_version_and_saved(self):
        self.assertEqual(self.update(), 2)
        values = {g.title: (g.version, g.compatible) for g in self.inventory.snapshot()}
        self.assertEqual(values, {'Sonic': ('1.9.0', '1.9.1'), 'Tetris': ('1.9.0', '1.9.1'), 'Gone': ('1.9.0', ''),
                                  'Old': ('1.8.0', ''), 'Edited': ('1.9.0', '')})
        self.inventory.save()
        again = {g.title: (g.version, g.compatible) for g in Inventory(self.folder / 'compiled-games.json').snapshot()}
        self.assertEqual(again, values)
        self.assertEqual(self.update(), 0)                            # nothing new: nothing changed

    def test_a_stamp_that_moves_later_clears_the_row(self):
        self.update()
        moved = lambda system: ('x' * 64,) + STAMPS[system][1:] if system == 'md' else STAMPS[system]
        self.assertEqual(self.update(moved), 1)
        self.assertEqual({g.title: g.compatible for g in self.inventory.snapshot() if g.compatible}, {'Tetris': '1.9.1'})

    def test_a_refresh_of_the_collection_stamps_the_rows(self):
        with patch('retrorecomp.compatibility.update', return_value=1) as update, \
                patch('retrorecomp.compiled_games.watch_signature', side_effect=lambda g: g.watch):
            for row in self.inventory.snapshot():
                row.level = 'standard'
            from retrorecomp.compiled_games import refresh_changed
            self.assertEqual(refresh_changed(self.inventory), 1)
        update.assert_called_once_with(self.inventory)


class InTheList(unittest.TestCase):
    """Compiled games shows the compatible version; its hint names both."""

    def setUp(self):
        from retrorecomp.gui import Application
        from tools.gui_patching import keep_window_data_in, patch_gui
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        keep_window_data_in(self, folder / 'datas')
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        # The window's quiet refresh of the collection (1.5 s after it opens, and on focus) restamps every row with the
        # real shipped table and the running stamps, which clears this test's made-up compatible version: on a loaded
        # PC the test outlasts 1.5 s and failed once in a full suite (20 Nov 2026). The rows here are set by hand.
        quiet = patch.object(Application, 'quiet_refresh_collection')
        quiet.start()
        self.addCleanup(quiet.stop)
        with patch_gui('load_preferences', return_value={'language': 'fr'}), \
                patch_gui('preferred_games_root', return_value=(folder / 'exports', False)):
            self.app = Application(self.root)

    def test_the_version_column_shows_the_compatible_version_and_the_hint_names_both(self):
        app = self.app
        sonic, old = game('Sonic', index=1), game('Old', version='1.8.0', index=2)
        sonic.compatible = '1.9.1'
        for row in (sonic, old):
            app.compiled_inventory.remember(row)
        with patch('retrorecomp.compiled_games_view.CompiledGamesView.scan'):
            app.toggle_compiled_games()
        view = app.compiled_view
        view.render()
        self.root.update()
        shown = {view.rows[row].title: view.table.set(row, 'version') for row in view.rows}
        self.assertEqual(shown, {'Sonic': '1.9.1', 'Old': '1.8.0'})
        row = next(row for row in view.rows if view.rows[row] is sonic)
        with patch.object(view, 'hovered_version', return_value=(row, sonic)):
            self.assertEqual(view.version_hint(), 'Converti avec 1.9.0 · compatible 1.9.1')
        with patch.object(view, 'hovered_version', return_value=(None, None)):
            self.assertEqual(view.version_hint(), '')


if __name__ == '__main__':
    unittest.main()
