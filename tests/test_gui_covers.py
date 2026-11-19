"""The box-art window (retrorecomp/gui_covers.py): which games are listed, what an image does, where it is applied.

Three ways in: a game a batch left without box art, the queue's « Choose box art… », a Compiled Games card."""
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from tests.tk_cleanup import release_tk
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image

from retrorecomp import gui_covers as gc
from retrorecomp.compiled_games import Game
from retrorecomp.gui_common import INTERFACE_PREFERENCES

SHA_A, SHA_B = 'a' * 64, 'b' * 64


def game(identity=SHA_A, title='Synthetic Game', system='sms'):
    return Game(f'C:/Games/{title}.exe', system, identity, title, report=f'C:/Games/{title}.json')


def png(path, size=(40, 56), colour=(200, 40, 40, 255)):
    Image.new('RGBA', size, colour).save(path)
    return path


class Window(gc.MissingCoversMixin):
    """The mixin on a stand-in for the Application: no Tk unless a test builds one."""

    def __init__(self):
        self.messages = queue.Queue()
        self.busy = self.close_when_idle = False
        self.items, self.row_status = {}, {}
        self.table = Mock()
        self.app = Mock()
        self.begin_reconvert = Mock()
        self.ui_font = 'TkDefaultFont'
        self.ask_missing_cover = Mock()
        self.preferences = Mock(return_value={})
        self.hint = Mock()
        self.use_cover = Mock()
        self.active_rows = []

    def tr(self, key, **values):
        return key

    def drained(self):
        events = []
        while True:
            try:
                events.append(self.messages.get_nowait())
            except queue.Empty:
                return events


class MissingBoxArt(unittest.TestCase):
    def test_an_empty_lookup_and_a_title_screen_stand_in_are_missing_box_art(self):
        self.assertTrue(gc.box_art_missing({'artwork': {'embedded': False, 'source': 'missing'}}))
        self.assertTrue(gc.box_art_missing({'artwork': {'embedded': True, 'source': 'libretro', 'media_style': 'title'}}))
        self.assertTrue(gc.box_art_missing({'artwork': {'embedded': True, 'source': 'local', 'media_style': 'snapshot'}}))

    def test_a_cover_found_chosen_or_turned_off_is_not_missing(self):
        self.assertFalse(gc.box_art_missing({'artwork': {'embedded': True, 'source': 'libretro', 'media_style': 'boxart'}}))
        self.assertFalse(gc.box_art_missing({'artwork': {'embedded': True, 'source': 'explicit'}}))
        self.assertFalse(gc.box_art_missing({'artwork': {'embedded': False, 'source': 'disabled'}}))
        self.assertFalse(gc.box_art_missing({'artwork': {'embedded': False, 'source': 'explicit'}}))
        self.assertFalse(gc.box_art_missing({}))                  # a report without artwork says nothing
        self.assertFalse(gc.box_art_missing({'artwork': 'odd'}))
        self.assertFalse(gc.box_art_missing(None))

    def test_the_option_never_reaches_a_converter(self):
        self.assertIn('ask_missing_cover', INTERFACE_PREFERENCES)


class Images(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_the_manual_box_art_file_types_are_the_ones_accepted(self):
        from retrorecomp.artwork import FORMATS
        self.assertEqual(set(gc.COVER_EXTENSIONS), FORMATS)

    def test_a_real_image_is_read_and_other_files_are_refused_with_their_reason(self):
        self.assertTrue(gc.read_cover(png(self.folder / 'Box.PNG')).startswith(b'\x89PNG'))
        text = self.folder / 'notes.txt'
        text.write_text('not an image', encoding='utf-8')
        with self.assertRaises(gc.CoverRefused) as refused:
            gc.read_cover(text)
        self.assertEqual(refused.exception.key, 'cover_ask_refused_type')
        broken = self.folder / 'broken.jpg'
        broken.write_bytes(b'\xff\xd8 not really a jpeg')
        with self.assertRaises(gc.CoverRefused) as refused:
            gc.read_cover(broken)
        self.assertEqual(refused.exception.key, 'cover_ask_refused_image')
        clear = png(self.folder / 'clear.png', colour=(0, 0, 0, 0))
        with self.assertRaises(gc.CoverRefused):
            gc.read_cover(clear)                                  # fully transparent: the manual path refuses it too
        with self.assertRaises(gc.CoverRefused):
            gc.read_cover(self.folder / 'gone.png')


class Requests(unittest.TestCase):
    def test_each_exact_game_is_listed_once_in_the_order_it_ended(self):
        requests = gc.CoverRequests()
        self.assertIsNotNone(requests.add(game(SHA_B, 'Second'), 'b.sms', 'row2'))
        self.assertIsNotNone(requests.add(game(SHA_A, 'First'), 'a.sms', 'row1'))
        first = requests.entries[('sms', SHA_A)]
        self.assertIs(requests.add(game(SHA_A, 'First'), 'a.sms', 'row1'), first)     # still open: the same row
        self.assertIsNotNone(requests.add(game(SHA_A, 'Same dump, other console', 'gg'), 'a.gg'))
        self.assertEqual([request.game.title for request in requests.open()], ['Second', 'First', 'Same dump, other console'])

    def test_closing_skips_the_waiting_games_and_the_rest_of_the_batch_but_keeps_the_images_given(self):
        requests = gc.CoverRequests()
        requests.add(game(SHA_A), 'a.sms')
        requests.add(game(SHA_B), 'b.sms')
        requests.give(('sms', SHA_A), b'image')
        requests.close()
        self.assertEqual(requests.entries[('sms', SHA_B)].state, 'skipped')
        self.assertEqual(requests.entries[('sms', SHA_A)].state, 'ready')
        self.assertIsNone(requests.add(game('c' * 64), 'c.sms'))      # a later game of the same batch is not asked for
        requests.new_batch()                                            # the next batch asks again
        self.assertEqual(list(requests.entries), [('sms', SHA_A)])
        self.assertIsNotNone(requests.add(game('c' * 64), 'c.sms'))

    def test_ready_images_are_taken_once_and_their_outcome_settles_the_row(self):
        requests = gc.CoverRequests()
        requests.add(game(SHA_A), 'a.sms')
        requests.add(game(SHA_B), 'b.sms')
        requests.give(('sms', SHA_A), b'image')
        taken = requests.take_ready()
        self.assertEqual([request.key for request in taken], [('sms', SHA_A)])
        self.assertEqual(requests.take_ready(), [])
        self.assertIsNone(requests.give(('sms', SHA_A), b'other'))     # being applied: not replaced under it
        self.assertTrue(requests.pending())
        self.assertIsNone(requests.finished(('sms', SHA_B), True))     # never asked to apply
        self.assertEqual(requests.finished(('sms', SHA_A), True).state, 'applied')
        self.assertFalse(requests.pending())
        requests.give(('sms', SHA_B), b'image')
        requests.take_ready()
        failed = requests.finished(('sms', SHA_B), False, 'compiler stopped')
        self.assertEqual((failed.state, failed.message), ('failed', 'compiler stopped'))
        self.assertEqual(requests.give(('sms', SHA_B), b'again').state, 'ready')   # a failed row can be given again

    def test_a_drop_goes_to_the_row_under_the_pointer_else_to_the_only_game_waiting(self):
        requests = gc.CoverRequests()
        requests.add(game(SHA_A), 'a.sms')
        self.assertEqual(gc.target_request(requests, []).key, ('sms', SHA_A))
        requests.add(game(SHA_B), 'b.sms')
        self.assertIsNone(gc.target_request(requests, []))
        self.assertEqual(gc.target_request(requests, [('sms', SHA_B)]).key, ('sms', SHA_B))
        self.assertIsNone(gc.target_request(requests, [('sms', 'f' * 64)]))


class Flow(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        # The game card's own cover is written beside the test, never in the player's Export/datas.
        patcher = patch('retrorecomp.game_details.data_directory', return_value=self.folder / 'datas')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = Window()
        self.window.cover_refresh = Mock()

    def report(self, artwork):
        import json
        path = self.folder / 'report.json'
        path.write_text(json.dumps({'tool': 'Retro-Recomp', 'system': 'sms', 'title': 'Synthetic Game',
                                    'executable': 'Synthetic Game.exe', 'rom': {'sha256': SHA_A},
                                    'artwork': artwork}), encoding='utf-8')
        return path

    def test_only_an_exported_game_without_box_art_is_sent_to_the_window(self):
        found = Game('x', 'sms', SHA_A, 'Synthetic Game')
        with patch('retrorecomp.compiled_games.game_from_report', return_value=found):
            missing = self.report({'embedded': False, 'source': 'missing'})
            result = {'status': 'success', 'report': str(missing), 'executable': str(self.folder / 'g.exe'),
                      'rom': 'C:/roms/Synthetic Game.sms'}
            self.window.check_missing_cover('row1', result)
            for status in ('error', 'stopped', 'duplicate'):
                self.window.check_missing_cover('row1', {**result, 'status': status})
            self.window.check_missing_cover('row1', {**result, 'report': ''})
            covered = self.report({'embedded': True, 'source': 'libretro', 'media_style': 'boxart'})
            self.window.check_missing_cover('row1', {**result, 'report': str(covered)})
            self.window.check_missing_cover('row1', {**result, 'report': str(self.folder / 'gone.json')})
        events = self.window.drained()
        self.assertEqual(events, [('cover_missing', 'row1', found, Path('C:/roms/Synthetic Game.sms'))])

    def test_an_image_becomes_the_games_own_cover_and_the_rows_chosen_box_art(self):
        from retrorecomp.game_details import Cards
        window = self.window
        window.busy = True                                               # the batch still runs
        window.items['row1'] = item = Mock(system='sms', sha256=SHA_A, cover=None)
        window.cover_requests().add(game(), 'a.sms', 'row1')
        self.assertTrue(window.give_missing_cover(('sms', SHA_A), png(self.folder / 'cover.png')))
        override = Cards().override(game())
        self.assertIsNotNone(override)                                   # what Reconvert and later conversions use
        self.assertEqual(item.cover, override)
        window.table.set.assert_called_with('row1', 'cover', 'chosen')
        self.assertEqual(window.cover_requests().entries[('sms', SHA_A)].state, 'ready')
        window.begin_reconvert.assert_not_called()                       # never during the batch
        window.app.after.assert_called_once()

    def test_a_refused_file_keeps_the_game_waiting_with_its_reason(self):
        window = self.window
        window.cover_requests().add(game(), 'a.sms')
        text = self.folder / 'cover.gif'
        text.write_bytes(b'GIF89a')
        self.assertFalse(window.give_missing_cover(('sms', SHA_A), text))
        request = window.cover_requests().entries[('sms', SHA_A)]
        self.assertEqual((request.state, request.message), ('waiting', 'cover_ask_refused_type'))
        window.begin_reconvert.assert_not_called()

    def test_once_idle_the_images_are_applied_by_the_reconversion_and_the_outcome_is_shown(self):
        window = self.window
        window.items['row1'] = Mock(system='sms', sha256=SHA_A, cover=None)
        window.row_status['row1'] = 'created'
        window.cover_requests().add(game(), Path('a.sms'), 'row1')
        window.cover_requests().add(game(SHA_B), Path('b.sms'), 'row2')
        window.give_missing_cover(('sms', SHA_A), png(self.folder / 'cover.png'))
        window.begin_reconvert.assert_called_once()
        (pairs,), _ = window.begin_reconvert.call_args
        self.assertEqual([(g.identity, source) for g, source in pairs], [(SHA_A, Path('a.sms'))])
        window.table.set.assert_called_with('row1', 'status', 'cover_ask_applying')
        window.cover_reconverted('sms', SHA_A, 'success')
        self.assertEqual(window.cover_requests().entries[('sms', SHA_A)].state, 'applied')
        window.table.set.assert_called_with('row1', 'status', 'created')
        window.cover_reconverted('sms', SHA_B, 'success')                # not applying: nothing changes
        self.assertEqual(window.cover_requests().entries[('sms', SHA_B)].state, 'waiting')

    def test_nothing_is_applied_while_the_window_closes(self):
        window = self.window
        window.close_when_idle = True
        window.cover_requests().add(game(), 'a.sms')
        window.cover_requests().give(('sms', SHA_A), b'image')
        window.apply_dropped_covers()
        window.begin_reconvert.assert_not_called()

    def test_dont_ask_again_turns_the_option_off_saves_it_and_closes_the_window(self):
        window = self.window
        window.close_cover_window = Mock()
        with patch.object(gc, 'save_preferences') as save:
            window.never_ask_cover()
        window.ask_missing_cover.set.assert_called_once_with(False)
        save.assert_called_once()
        window.close_cover_window.assert_called_once()


class ChooseBoxArt(unittest.TestCase):
    """« Choose box art… » of the queue and « Choose cover… » of a Compiled Games card open the same window."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = patch('retrorecomp.game_details.data_directory', return_value=self.folder / 'datas')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = Window()
        self.window.show_cover_rows = Mock()
        self.window.cover_refresh = Mock()

    def queue_row(self, row='row1', cover=None):
        rom = self.folder / f'{row}.sms'
        rom.write_bytes(b'\x00' * 64)
        self.window.items[row] = item = Mock(system='sms', sha256=SHA_A, cover=cover, path=rom, title='Queued')
        return item

    def test_a_queue_row_takes_the_file_itself_as_its_chosen_box_art_and_nothing_is_rebuilt(self):
        from retrorecomp.game_details import Cards
        old = png(self.folder / 'old.png', colour=(0, 200, 0, 255))
        item = self.queue_row(cover=old)
        self.queue_row('row2')
        self.window.choose_queue_covers(['row1', 'row2', 'gone'])
        (shown,), _ = self.window.show_cover_rows.call_args
        self.assertEqual([request.key for request in shown], [('row', 'row1'), ('row', 'row2')])
        self.assertEqual(shown[0].current, old.read_bytes())                 # its box art now, as the thumbnail
        self.assertIsNone(shown[1].current)
        new = png(self.folder / 'new.png')
        self.assertTrue(self.window.give_missing_cover(('row', 'row1'), new))
        self.assertEqual(item.cover, new)
        self.assertEqual(shown[0].state, 'chosen')
        self.window.table.set.assert_called_with('row1', 'cover', 'chosen')
        self.window.use_cover.set.assert_called_once_with(True)
        self.assertIsNone(Cards().override(game()))                          # the game card is not touched
        self.window.begin_reconvert.assert_not_called()
        self.window.app.after.assert_not_called()

    def test_a_queue_row_already_converting_is_not_changed_under_its_conversion(self):
        item = self.queue_row()
        self.window.busy, self.window.active_rows = True, ['row1']
        self.window.row_status['row1'] = 'converting'
        self.window.choose_queue_covers(['row1'])
        self.assertFalse(self.window.give_missing_cover(('row', 'row1'), png(self.folder / 'new.png')))
        self.assertIsNone(item.cover)
        self.assertEqual(self.window.cover_requests().entries[('row', 'row1')].message, 'cover_pick_busy')

    def test_a_card_image_becomes_the_override_and_is_applied_to_the_export(self):
        from retrorecomp.game_details import Cards
        rom = self.folder / 'game.sms'
        rom.write_bytes(b'\x00' * 64)
        exported = Game('x', 'sms', SHA_A, 'Exported', source=str(rom))
        self.window.choose_card_cover(exported, current=b'old picture')
        request = self.window.cover_requests().entries[('sms', SHA_A)]
        self.assertEqual((request.kind, request.source, request.current), ('card', rom, b'old picture'))
        self.window.give_missing_cover(('sms', SHA_A), png(self.folder / 'new.png'))
        self.assertIsNotNone(Cards().override(exported))
        (pairs,), _ = self.window.begin_reconvert.call_args
        self.assertEqual([(g.identity, source) for g, source in pairs], [(SHA_A, rom)])
        self.window.cover_reconverted('sms', SHA_A, 'success')
        self.assertEqual(request.state, 'applied')

    def test_a_card_whose_rom_is_gone_keeps_the_image_for_its_next_reconvert(self):
        from retrorecomp.game_details import Cards
        exported = Game('x', 'sms', SHA_A, 'Exported', source=str(self.folder / 'moved.sms'))
        self.window.choose_card_cover(exported)
        self.assertIsNone(self.window.cover_requests().entries[('sms', SHA_A)].source)
        self.window.give_missing_cover(('sms', SHA_A), png(self.folder / 'new.png'))
        self.assertIsNotNone(Cards().override(exported))
        self.assertEqual(self.window.cover_requests().entries[('sms', SHA_A)].state, 'ready')
        self.window.apply_dropped_covers()
        self.window.begin_reconvert.assert_not_called()
        self.window.app.after.assert_not_called()                            # nothing to wait for either

    def test_a_card_finds_its_rom_in_the_queue_when_its_own_source_is_gone(self):
        item = self.queue_row()
        self.window.choose_card_cover(Game('x', 'sms', SHA_A, 'Exported', source=''))
        self.assertEqual(self.window.cover_requests().entries[('sms', SHA_A)].source, item.path)

    def test_the_list_right_click_opens_one_row_per_game_with_the_card_image_it_keeps(self):
        from retrorecomp.game_details import Cards
        kept, plain = Game('x', 'sms', SHA_A, 'Kept'), Game('x', 'md', SHA_B, 'Plain')
        Cards().set_cover(kept, png(self.folder / 'kept.png').read_bytes(), override=True)
        self.window.choose_compiled_covers([kept, plain])
        (shown,), _ = self.window.show_cover_rows.call_args
        self.assertEqual([(r.key, r.kind) for r in shown], [(('sms', SHA_A), 'card'), (('md', SHA_B), 'card')])
        self.assertEqual(shown[0].current[1:4], b'PNG')                       # the card's saved image
        self.assertIsNone(shown[1].current)

    def test_closing_forgets_the_rows_opened_to_choose_and_never_blocks_the_batch_window(self):
        requests = gc.CoverRequests()
        requests.add(Mock(system='sms', title='Queued'), 'q.sms', 'row1', kind='queue')
        requests.add(game(SHA_B), 'b.sms', kind='card')
        requests.close()
        self.assertEqual(requests.entries, {})
        self.assertFalse(requests.declined)
        self.assertIsNotNone(requests.add(game(SHA_A), 'a.sms'))


class HiddenWindow(unittest.TestCase):
    def test_one_window_for_the_batch_one_row_per_game_and_a_drop_on_the_only_waiting_game(self):
        release_tk(self)                      # first: its cleanup runs after root.destroy (tests/tk_cleanup.py)
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        self.addCleanup(root.destroy)
        folder = Path(tempfile.mkdtemp())
        window = Window()
        window.app = root
        with patch('retrorecomp.game_details.data_directory', return_value=folder / 'datas'), \
             patch('retrorecomp.dropfiles.enable_file_drop', return_value=Mock()), \
             patch.object(tk.Toplevel, 'deiconify'):                    # never shown on the desktop
            window.cover_missing('row1', game(SHA_A, 'First'), Path('a.sms'))
            first = window.cover_window
            window.cover_missing('row2', game(SHA_B, 'Second'), Path('b.sms'))
            self.assertIs(window.cover_window, first)                   # one shared window
            self.assertEqual(len(window.cover_rows), 2)
            window.skip_missing_cover(('sms', SHA_B))
            window.cover_drop_paths([str(png(folder / 'box.png'))])     # only First still waits
            self.assertEqual(window.cover_requests().entries[('sms', SHA_A)].state, 'applying')
            window.begin_reconvert.assert_called_once()
            self.assertEqual(first.title(), 'cover_ask_title')
            self.assertTrue(window.cover_never.winfo_manager())                # « Don't ask again » for these games
            window.close_cover_window()
            # « Choose box art… » of the queue: the same window, its own title, no « Don't ask again ».
            window.items['q'] = Mock(system='sms', sha256=SHA_A, cover=None, path=folder / 'q.sms', title='Queued')
            window.cover_requests().new_batch()
            window.choose_queue_covers(['q'])
            self.assertEqual(window.cover_window.title(), 'cover_pick_title')
            self.assertFalse(window.cover_never.winfo_manager())
            self.assertFalse(window.cover_rows[('row', 'q')]['skip'].winfo_manager())
            window.close_cover_window()
        self.assertIsNone(window.cover_window)
        self.assertFalse(first.winfo_exists())


if __name__ == '__main__':
    unittest.main()
