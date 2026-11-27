"""« Delete game… » of Compiled Games (retrorecomp/game_removal.py, the owner's request of 27 November 2026), in scratch folders
only: what goes (the exe and its report folder), what stays (the saves unless asked, the ROM, other games), what is refused
(files the converter cannot show are its own, files outside the output folders), and the list that follows at once."""
import hashlib
import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import game_removal
from retrorecomp.compiled_games import Inventory, scan
from retrorecomp.feedback import encode


def export(console: Path, name: str, identity: str):
    """A converted game as the converter writes it: the exe carries the ROM identity, the report names both."""
    exe = console / f'{name}.exe'
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b'MZ[Retro-Recomp]\0' + identity.encode() + b'\0')
    report = console / f'datas/reports/{name}/conversion-report.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'tool': 'Retro-Recomp', 'version': '1.1.4', 'system': {'id': 'sms'},
        'rom': {'sha256': identity, 'name': name + '.sms'}, 'executable': exe.name,
        'runtime_feedback': {'identity': identity, 'fingerprint': hashlib.sha256(encode([], 'sms', identity)).hexdigest()},
        'export_receipt': {'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}, 'final_checks': [{'interpreter_percent': 0}]}),
        encoding='utf-8')
    return exe, report


class Scratch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.games = self.root / 'Games'
        self.console = self.games / 'Master System'
        environment = patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(self.root / 'knowledge')})
        environment.start()
        self.addCleanup(environment.stop)
        self.alpha_exe, self.alpha_report = export(self.console, 'Alpha', 'a' * 64)
        self.beta_exe, self.beta_report = export(self.console, 'Beta', 'b' * 64)
        saves = self.console / 'datas' / 'games'
        (saves / f'Alpha-{"a" * 12}').mkdir(parents=True)
        (saves / f'Alpha-{"a" * 12}' / 'Alpha-quicksave.state').write_bytes(b'state')
        (saves / f'Alpha-{"a" * 12}.sav').write_bytes(b'battery')
        (saves / f'Beta-{"b" * 12}').mkdir()
        self.rom = self.root / 'roms' / 'Alpha.sms'
        self.rom.parent.mkdir()
        self.rom.write_bytes(b'rom')
        self.inventory = Inventory(self.root / 'converter' / 'compiled-games.json')
        scan(self.inventory, [self.games])
        self.alpha = next(g for g in self.inventory.snapshot() if g.title == 'Alpha')
        self.alpha.source = str(self.rom)


class Plans(Scratch):
    def test_the_exe_and_its_report_go_and_only_this_game_s_saves_are_offered(self):
        plan = game_removal.plan(self.alpha, [self.games])
        self.assertEqual(plan.files, [self.alpha_exe, self.alpha_report.parent])
        self.assertEqual([p.name for p in plan.saves], [f'Alpha-{"a" * 12}', f'Alpha-{"a" * 12}.sav'])

    def test_saves_kept_unless_asked(self):
        plan = game_removal.plan(self.alpha, [self.games])
        plan.trash = False                         # never the real Recycle Bin from a test
        game_removal.delete(plan, with_saves=False)
        self.assertFalse(self.alpha_exe.exists())
        self.assertFalse(self.alpha_report.parent.exists())
        self.assertTrue((self.console / 'datas/games' / f'Alpha-{"a" * 12}' / 'Alpha-quicksave.state').exists())
        self.assertTrue((self.console / 'datas/games' / f'Alpha-{"a" * 12}.sav').exists())
        self.assertTrue(self.beta_exe.exists() and self.beta_report.exists())       # the other game is untouched
        self.assertTrue(self.rom.exists())                                           # the ROM is never touched

    def test_saves_go_when_asked(self):
        plan = game_removal.plan(self.alpha, [self.games])
        plan.trash = False
        game_removal.delete(plan, with_saves=True)
        self.assertEqual(sorted(p.name for p in (self.console / 'datas/games').iterdir()), [f'Beta-{"b" * 12}'])

    def test_the_recycle_bin_gets_the_same_list(self):
        plan = game_removal.plan(self.alpha, [self.games])
        plan.trash = True
        with patch.object(game_removal, 'to_trash') as trash:
            game_removal.delete(plan, with_saves=False)
        trash.assert_called_once_with([self.alpha_exe, self.alpha_report.parent])
        self.assertTrue(self.alpha_exe.exists())                                     # the bin was not really called

    def test_refused_when_the_exe_is_not_this_game(self):
        self.alpha_exe.write_bytes(b'MZ another program with the same name')
        with self.assertRaises(game_removal.Refused):
            game_removal.plan(self.alpha, [self.games])

    def test_refused_when_the_report_names_another_game(self):
        data = json.loads(self.alpha_report.read_text(encoding='utf-8'))
        data['executable'] = 'Other.exe'
        self.alpha_report.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(game_removal.Refused):
            game_removal.plan(self.alpha, [self.games])

    def test_refused_outside_the_output_folders(self):
        with self.assertRaises(game_removal.Refused):
            game_removal.plan(self.alpha, [self.root / 'elsewhere'])


class FromTheCollection(Scratch):
    """The collection's « Delete game… » and its Delete key: the dialog, then the game leaves the list at once."""
    def setUp(self):
        super().setUp()
        from tools.gui_patching import keep_window_data_in, patch_gui
        from tests.tk_cleanup import release_tk
        release_tk(self)
        keep_window_data_in(self, self.root / 'datas')
        try:
            self.tk = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.tk.withdraw()
        self.addCleanup(self.tk.destroy)
        from retrorecomp.gui import Application
        with patch_gui('load_preferences', return_value={'language': 'en'}), \
                patch_gui('preferred_games_root', return_value=(self.games, False)):
            self.app = Application(self.tk)
        self.app.compiled_inventory = self.inventory
        self.app.toggle_compiled_games()
        self.tk.update()
        self.view = self.app.compiled_view
        self.view.inventory = self.inventory
        self.view.render()
        self.tk.update()
        for patcher in (patch('retrorecomp.compiled_games_view.default_roots', return_value=[self.games]),
                        patch.object(game_removal, 'trash_available', return_value=False)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def select(self, title):
        row = next(r for r, g in self.view.rows.items() if g.title == title)
        self.view.table.selection_set(row)
        self.view.table.focus(row)

    def titles(self):
        return sorted(g.title for g in self.view.rows.values())

    def test_the_delete_key_deletes_after_the_dialog_and_the_list_follows(self):
        self.select('Alpha')
        with patch.object(type(self.view), 'delete_dialog', return_value=False) as dialog:
            # The table's own <Delete> binding, run as Tk runs it (a withdrawn window gets no keyboard focus to generate it)
            import re
            script = str(self.view.table.bind('<Delete>'))
            self.assertTrue(script)
            self.tk.eval('foreach _ {1} {' + re.sub(r'%[A-Za-z#]', '0', script) + '}')   # its « break » ends the loop
            self.tk.update()
        dialog.assert_called_once()
        self.assertFalse(self.alpha_exe.exists())
        self.assertEqual(self.titles(), ['Beta'])
        self.assertEqual([g.title for g in Inventory(self.inventory.path).snapshot()], ['Beta'])
        self.assertTrue((self.console / 'datas/games' / f'Alpha-{"a" * 12}.sav').exists())

    def test_cancel_deletes_nothing(self):
        self.select('Alpha')
        with patch.object(type(self.view), 'delete_dialog', return_value=None):
            self.view.delete_games()
        self.assertTrue(self.alpha_exe.exists())
        self.assertEqual(self.titles(), ['Alpha', 'Beta'])

    def test_refused_while_a_conversion_runs(self):
        self.select('Alpha')
        self.app.busy = True
        try:
            with patch('retrorecomp.compiled_games_view.messagebox.showinfo') as told, \
                    patch.object(type(self.view), 'delete_dialog') as dialog:
                self.view.delete_games()
        finally:
            self.app.busy = False
        told.assert_called_once()
        dialog.assert_not_called()
        self.assertTrue(self.alpha_exe.exists())

    def test_the_dialog_names_the_files_and_keeps_the_saves_unticked(self):
        self.select('Alpha')
        plan = game_removal.plan(self.alpha, [self.games])
        shown = {}
        def look(window):
            self.tk.update()
            texts = [w for w in all_widgets(window) if w.winfo_class() == 'Text']
            shown['listing'] = texts[0].get('1.0', 'end-1c')
            box = next(w for w in all_widgets(window) if w.winfo_class() == 'TCheckbutton')
            shown['saves'] = (box.cget('text'), box.instate(['selected']))
            window.destroy()
        with patch.object(self.tk, 'wait_window', side_effect=look):
            self.assertIsNone(self.view.delete_dialog([plan]))
        self.assertIn('Alpha', shown['listing'])
        self.assertIn(str(self.alpha_exe), shown['listing'])
        self.assertIn(str(self.alpha_report.parent), shown['listing'])
        self.assertEqual(shown['saves'], (self.app.tr('delete_game_saves', count=2), False))


def all_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from all_widgets(child)


class NotInTheFrontEnd(unittest.TestCase):
    def test_the_front_end_offers_no_delete(self):
        source = (Path(__file__).resolve().parents[1] / 'retrorecomp' / 'front_end_view.py').read_text(encoding='utf-8')
        self.assertNotIn('delete_game', source)
        self.assertNotIn('game_removal', source)


if __name__ == '__main__':
    unittest.main()
