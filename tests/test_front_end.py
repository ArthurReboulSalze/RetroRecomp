"""The front-end (retrorecomp/front_end.py, front_end_view.py): its consoles, order, grid, gamepad, memory, search and
favourites, and the view's behaviour in a hidden window (no ROM, no game, nothing written outside a temporary folder)."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from tests.tk_cleanup import release_tk
from unittest.mock import Mock

from retrorecomp import front_end as fe
from retrorecomp.compiled_games import Game
from retrorecomp.systems import available_profiles


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def game(title, system='sms', *, favorite=False, status='no_hints', modified=0):
    return Game(f'C:/games/{system}/{title}.exe', system, sha(system + title), title, status=status,
                favorite=favorite, modified=modified)


def mask(*names):
    value = 0
    for name in names:
        value |= 1 << fe.BUTTONS[name]
    return value


class Shelves(unittest.TestCase):
    def test_consoles_in_registry_order_and_missing_games_left_out(self):
        profiles = available_profiles()
        games = [game('Sonic', 'md'), game('Alex Kidd', 'sms'), game('Gone', 'sms', status='missing')]
        result = fe.shelves(games, profiles)
        ids = [profile.id for profile, _ in result]
        order = [profile.id for profile in profiles]
        self.assertEqual(ids, sorted(ids, key=order.index))
        self.assertEqual({profile.id: [g.title for g in found] for profile, found in result},
                         {'sms': ['Alex Kidd'], 'md': ['Sonic']})

    def test_orders(self):
        a, b, c = game('beta', modified=3), game('Alpha', modified=1), game('gamma', modified=2)
        played = {fe.game_key(c): 100.0, fe.game_key(a): 50.0}
        self.assertEqual([g.title for g in fe.sort_games([a, b, c], 'title', {})], ['Alpha', 'beta', 'gamma'])
        self.assertEqual([g.title for g in fe.sort_games([a, b, c], 'converted', {})], ['beta', 'gamma', 'Alpha'])
        # Last played first, then the never played ones by title.
        self.assertEqual([g.title for g in fe.sort_games([a, b, c], 'last_played', played)],
                         ['gamma', 'beta', 'Alpha'])

    def test_search_over_every_console_ignores_case_and_accents_and_needs_every_word(self):
        games = [game('Super Mario Land', 'gb'), game('Super Mario Bros', 'nes'), game('Pokémon Rouge', 'gb'),
                 game('Mario Kart', 'snes')]
        self.assertEqual([g.title for g in fe.search(games, 'MARIO')],
                         ['Super Mario Land', 'Super Mario Bros', 'Mario Kart'])
        self.assertEqual([g.title for g in fe.search(games, 'super  mario bros')], ['Super Mario Bros'])
        self.assertEqual([g.title for g in fe.search(games, 'pokemon')], ['Pokémon Rouge'])
        self.assertEqual(fe.search(games, '   '), [])

    def test_favorites(self):
        games = [game('A', favorite=True), game('B'), game('C', 'md', favorite=True)]
        self.assertEqual([g.title for g in fe.favorites(games)], ['A', 'C'])


class Geometry(unittest.TestCase):
    def test_cell_aspect_is_the_clamped_median(self):
        self.assertEqual(fe.cell_aspect([]), fe.DEFAULT_ASPECT)
        self.assertAlmostEqual(fe.cell_aspect([0.7, 0.71, 3.0]), 0.71)
        self.assertEqual(fe.cell_aspect([5.0, 4.0]), fe.ASPECT_RANGE[1])
        self.assertEqual(fe.cell_aspect([0.1, float('nan')]), fe.ASPECT_RANGE[0])

    def test_fit_never_distorts(self):
        self.assertEqual(fe.fit((400, 300), (200, 200)), (200, 150))
        self.assertEqual(fe.fit((300, 400), (200, 200)), (150, 200))
        self.assertEqual(fe.fit((0, 0), (20, 30)), (20, 30))

    def test_grid_columns_are_kept_between_the_bounds_and_titles_follow_the_cover_width(self):
        self.assertEqual(fe.grid(1100, 0.7, columns=2).columns, fe.MIN_COLUMNS)
        self.assertEqual(fe.grid(1100, 0.7, columns=40).columns, fe.MAX_COLUMNS)
        self.assertEqual(fe.MIN_COLUMNS, 4)
        wide = fe.grid(1100, 0.7, columns=4)
        narrow = fe.grid(1100, 0.7, columns=12)
        self.assertEqual(wide.title_lines, 2)
        self.assertLess(narrow.title_lines, 2)
        auto = fe.grid(1100, 0.7)
        self.assertTrue(fe.MIN_COLUMNS <= auto.columns <= fe.MAX_COLUMNS)
        # Room above the first row for the chosen cover's growth.
        self.assertGreaterEqual(auto.top, auto.margin + auto.cover_height * (fe.FOCUS_GROWTH - 1))

    def test_origin_visible_and_hit_agree(self):
        layout = fe.grid(1000, 0.7, columns=5)
        count = 23
        for index in (0, 4, 5, 22):
            x, y = layout.origin(index)
            self.assertEqual(layout.at(x + 5, y + 5, count), index)
            self.assertIn(index, layout.visible(y - 10, 50, count))
        self.assertIsNone(layout.at(0, 0, count))
        self.assertEqual(layout.rows(count), 5)

    def test_moves(self):
        # 10 games, 4 per row: rows 0-3, 4-7, 8-9.
        self.assertEqual(fe.move(3, 10, 4, dx=1), 4)            # right goes on to the next row
        self.assertEqual(fe.move(0, 10, 4, dx=-1), 0)
        self.assertEqual(fe.move(1, 10, 4, dy=-1), 1)           # nothing above the first row
        self.assertEqual(fe.move(6, 10, 4, dy=1), 9)            # the last row is short: its last game
        self.assertEqual(fe.move(9, 10, 4, dy=1), 9)
        self.assertEqual(fe.move(5, 10, 4, dy=-1), 1)
        self.assertEqual(fe.move(0, 0, 4, dx=1), 0)

    def test_step_columns(self):
        self.assertEqual(fe.step_columns(4, -1), 4)
        self.assertEqual(fe.step_columns(12, 1), 12)
        self.assertEqual(fe.step_columns(6, 1), 7)

    def test_carousel_shows_every_other_entry_once_around_the_chosen_one(self):
        for count in range(1, 16):
            for chosen in range(count):
                left, right = fe.carousel(count, chosen)
                self.assertNotIn(chosen, left + right)
                self.assertEqual(sorted(left + right), sorted(set(range(count)) - {chosen}))
                self.assertLessEqual(abs(len(right) - len(left)), 1)
        self.assertEqual(fe.carousel(5, 0), ([4, 3], [1, 2]))


class Keyboard(unittest.TestCase):
    def test_moves_wrap_and_wide_keys_are_one_stop(self):
        space = fe.KEYBOARD[3].index('space')
        self.assertEqual(fe.keyboard_move(3, space - 1, 1, 0), (3, space))
        self.assertEqual(fe.keyboard_move(3, space, 1, 0), (3, space + 2))      # past both cells of the space
        self.assertEqual(fe.keyboard_move(3, space + 2, -1, 0), (3, space + 1))
        self.assertEqual(fe.keyboard_move(0, 0, -1, 0), (0, len(fe.KEYBOARD[0]) - 1))
        self.assertEqual(fe.keyboard_move(0, 3, 0, -1), (len(fe.KEYBOARD) - 1, 3))

    def test_typing(self):
        self.assertEqual(fe.type_key('', 'space'), '')                          # no leading space
        self.assertEqual(fe.type_key('ma', 'R'), 'mar')
        self.assertEqual(fe.type_key('mar', 'delete'), 'ma')
        self.assertEqual(fe.type_key('', 'delete'), '')
        self.assertEqual(fe.type_key('x' * fe.MAX_QUERY, 'a'), 'x' * fe.MAX_QUERY)
        self.assertEqual(fe.type_key('a', 'done'), 'a')


class Gamepad(unittest.TestCase):
    def test_waits_for_rest_then_one_event_per_press(self):
        pad = fe.GridPad()
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.0), [])             # held when the view opened
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.1), [])
        self.assertEqual(pad.update([(0, 0, 0)], 0.2), [])                      # at rest: armed
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.3), ['a'])
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.4), [])             # held: once
        self.assertEqual(pad.update([(mask('b', 'l2'), 0, 0)], 0.5), ['b', 'l2'])
        self.assertEqual(pad.update([(mask('r2'), 0, 0), (mask('lb'), 0, 0)], 0.6), ['lb', 'r2'])

    def test_triggers_are_the_bridge_bits_above_every_sdl_button(self):
        source = (Path(__file__).resolve().parents[1] / 'native/player_gamepad.c').read_text(encoding='utf-8')
        self.assertIn('RR_PAD_LEFT_TRIGGER (1u << %d)' % fe.BUTTONS['l2'], source)
        self.assertIn('RR_PAD_RIGHT_TRIGGER (1u << %d)' % fe.BUTTONS['r2'], source)
        self.assertGreater(fe.BUTTONS['l2'], 21)

    def test_directions_repeat_faster_when_held_and_disabling_disarms(self):
        pad = fe.GridPad()
        pad.update([(0, 0, 0)], 0.0)
        self.assertEqual(pad.update([(0, 0, 30000)], 0.0), [('move', 0, 1)])
        self.assertEqual(pad.update([(0, 0, 30000)], 0.2), [])
        self.assertEqual(pad.update([(0, 0, 30000)], 0.36), [('move', 0, 1)])
        self.assertEqual(pad.update([(mask('left'), 0, 0)], 0.4), [('move', -1, 0)])
        self.assertEqual(pad.update([(0, 30000, 20000)], 0.5), [('move', 1, 0)])   # the axis pushed further wins
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.6, enabled=False), [])
        self.assertEqual(pad.update([(mask('a'), 0, 0)], 0.7), [])                # not armed again until at rest


class MemoryFile(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / 'front-end.json'

    def test_round_trip(self):
        memory = fe.Memory(self.path)
        memory.console, memory.order, memory.columns = 'md', 'title', {'md': 7, 'favorites': 5}
        memory.mark_played(game('Sonic', 'md'), now=1234.0)
        again = fe.Memory(self.path)
        self.assertEqual((again.console, again.order, again.columns), ('md', 'title', {'md': 7, 'favorites': 5}))
        self.assertEqual(again.played, {fe.game_key(game('Sonic', 'md')): 1234.0})

    def test_bad_entries_are_left_out(self):
        good = fe.game_key(game('Ok'))
        self.path.write_text(json.dumps({'schema': 1, 'console': '../x', 'order': 'random',
                                         'columns': {'sms': 3, 'md': 6, 'gb': 'many', 'BAD!': 5},
                                         'played': {good: 10, 'sms:nothex': 5, 'md:' + 'a' * 64: -1}}),
                             encoding='utf-8')
        memory = fe.Memory(self.path)
        self.assertEqual((memory.console, memory.order), ('', fe.ORDERS[0]))
        self.assertEqual(memory.columns, {'md': 6})
        self.assertEqual(memory.played, {good: 10.0})

    def test_other_schema_and_broken_file_start_empty(self):
        for text in ('{"schema": 2, "console": "md"}', '{broken', '[]'):
            self.path.write_text(text, encoding='utf-8')
            memory = fe.Memory(self.path)
            self.assertEqual((memory.console, memory.columns, memory.played), ('', {}, {}))

    def test_played_is_bounded(self):
        memory = fe.Memory(self.path)
        memory.played = {f'sms:{sha(str(i))}': float(i + 1) for i in range(fe.MAX_PLAYED)}
        memory.mark_played(game('Newest'), now=10.0 ** 9)
        self.assertEqual(len(memory.played), fe.MAX_PLAYED)
        self.assertNotIn(f'sms:{sha("0")}', memory.played)          # the oldest went


class SavedCovers(unittest.TestCase):
    def test_cached_cover_reads_only_what_is_saved_never_the_executable(self):
        from unittest.mock import patch
        from PIL import Image
        from retrorecomp.game_details import Cards
        folder = Path(tempfile.mkdtemp())
        cards = Cards(folder)
        bare, boxed = game('No cover'), game('Boxed')
        with patch('retrorecomp.game_details.pe_icon', side_effect=AssertionError('executable read')),              patch('retrorecomp.game_details.elf_icon', side_effect=AssertionError('executable read')),              patch('retrorecomp.game_details.boxart_cache_directory', return_value=folder / 'BoxArt'):
            self.assertIsNone(cards.cached_cover(bare))
            picture = folder / 'box.png'
            Image.new('RGB', (30, 40), 'red').save(picture)
            cards.set_cover(boxed, picture.read_bytes(), override=True)
            self.assertTrue(cards.cached_cover(boxed).startswith(b'\x89PNG'))


class Inventory:
    def __init__(self, games):
        self.games = games

    def snapshot(self):
        return list(self.games)

    def set_favorite(self, target, value):
        for entry in self.games:
            if (entry.system, entry.identity) == (target.system, target.identity):
                entry.favorite = value


class HiddenView(unittest.TestCase):
    """The view in a withdrawn window: never shown, no gamepad, covers from a stand-in."""

    def setUp(self):
        release_tk(self)                      # first: its cleanup runs after root.destroy (tests/tk_cleanup.py)
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        from retrorecomp import front_end_view
        self.games = ([game(f'Master {i:02d}', 'sms') for i in range(9)]
                      + [game('Super Mario Land', 'gb', favorite=True), game('Tetris', 'gb'),
                         game('Sonic', 'md', favorite=True)])
        self.owner = Mock(tr=lambda key, **values: key + (repr(sorted(values.items())) if values else ''),
                          ui_font='TkDefaultFont', language='en', busy=False, updating=False, compiled_view=None,
                          front_end_fullscreen=False, app=self.root, compiled_inventory=Inventory(self.games))
        cards = Mock()
        cards.cached_cover.return_value = None
        cards.metadata.return_value = {}
        self.folder = Path(tempfile.mkdtemp())
        original = front_end_view.FrontEndView.start_controller
        front_end_view.FrontEndView.start_controller = lambda view: None      # no gamepad bridge in the suite
        self.addCleanup(setattr, front_end_view.FrontEndView, 'start_controller', original)
        self.view = front_end_view.FrontEndView(self.owner, self.root, memory=fe.Memory(self.folder / 'fe.json'),
                                                cards=cards)
        self.addCleanup(self.view.loader.close)                      # its cover thread stops with the test
        self.view.pack(fill='both', expand=True)
        # A withdrawn window is never mapped, so it has no size of its own: give the wall the size of a window.
        self.view.wall.winfo_width = lambda: 1000
        self.view.wall.winfo_height = lambda: 600
        self.view.tabs.winfo_width = lambda: 1000
        self.view.show()
        self.root.update()

    def test_strip_has_the_favourites_then_the_consoles_and_opens_on_a_console(self):
        ids = [entry.id for entry, _ in self.view.shelves]
        self.assertEqual(ids[0], 'favorites')
        self.assertEqual(set(ids[1:]), {'sms', 'gb', 'md'})
        self.assertNotIn(self.view.shelf_id(), ('favorites', 'search'))

    def test_covers_per_row_are_remembered_per_console(self):
        self.view.select_shelf(self.view.index_of('sms'), slide=False)
        start = self.view.layout.columns
        self.view.change_columns(1)
        self.assertEqual(self.view.memory.columns['sms'], start + 1)
        for _ in range(20):
            self.view.change_columns(-1)
        self.assertEqual(self.view.layout.columns, fe.MIN_COLUMNS)
        self.view.select_shelf(self.view.index_of('gb'), slide=False)
        self.assertNotIn('gb', self.view.memory.columns)
        self.assertEqual(json.loads((self.folder / 'fe.json').read_text(encoding='utf-8'))['columns'],
                         {'sms': fe.MIN_COLUMNS})

    def lb_rb(self, start, event):
        """Where LB / RB lead from entry `start`: the reference the wheel and Ctrl+arrows follow."""
        self.view.select_shelf(start, slide=False)
        self.view.pad_event(event)
        return self.view.shelf

    def wheel(self, delta=0, num=0):
        """A wheel event over the strip, as Tk gives it (a withdrawn window gets no generated events)."""
        return self.view.strip_wheel(SimpleNamespace(delta=delta, num=num))

    def test_the_strip_s_wheel_and_ctrl_arrows_are_bound(self):
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.assertIn('strip_wheel', self.view.tabs.bind(sequence), sequence)
        for widget in (self.view.wall, self.view.tabs, self.view.details):     # from anywhere in the front-end
            self.assertIn('previous_console', widget.bind('<Control-Left>'))
            self.assertIn('next_console', widget.bind('<Control-Right>'))
        # The covers keep their own wheel (scrolling) and Ctrl+wheel (covers per row); the plain arrows move between
        # covers; Ctrl+F still searches; none of them is one of the strip's.
        self.assertIn('wheel', self.view.wall.bind('<MouseWheel>'))
        self.assertNotIn('strip_wheel', self.view.wall.bind('<MouseWheel>'))
        self.assertIn('zoom_wheel', self.view.wall.bind('<Control-MouseWheel>'))
        for sequence in ('<Left>', '<Right>', '<Control-f>'):
            self.assertNotIn('console', self.view.wall.bind(sequence), sequence)
        self.assertEqual(self.view.tabs.bind('<Control-MouseWheel>'), '')

    def test_the_wheel_over_the_strip_changes_console_one_notch_for_one_like_lb_rb(self):
        count = len(self.view.shelves)
        for start in (0, count - 1):                                       # round at both ends, as LB / RB are
            for delta, event in ((-120, 'rb'), (120, 'lb')):               # down: the next; up: the previous
                expected = self.lb_rb(start, event)
                self.view.select_shelf(start, slide=False)
                self.assertEqual(self.wheel(delta), 'break')
                self.assertEqual(self.view.shelf, expected, (start, delta))
        self.view.select_shelf(0, slide=False)
        self.wheel(-240)                                                   # two notches in one event: two consoles
        self.assertEqual(self.view.shelf, 2 % count)
        for _ in range(3):                                                 # a fine wheel: a console per 120
            self.wheel(-40)
        self.assertEqual(self.view.shelf, 3 % count)
        self.wheel(num=5)                                                  # X11's wheel: down is the next
        self.assertEqual(self.view.shelf, 4 % count)
        self.wheel(num=4)
        self.assertEqual(self.view.shelf, 3 % count)

    def test_ctrl_left_and_right_change_console_like_lb_and_rb(self):
        count = len(self.view.shelves)
        for method, event in ((self.view.next_console, 'rb'), (self.view.previous_console, 'lb')):
            for start in (0, count - 1):
                expected = self.lb_rb(start, event)
                self.view.select_shelf(start, slide=False)
                self.assertEqual(method(SimpleNamespace()), 'break')
                self.assertEqual(self.view.shelf, expected, (event, start))

    def test_the_wheel_and_ctrl_arrows_leave_the_typed_search_and_the_menu_alone(self):
        self.view.open_search()
        for key in 'MA':
            self.view.type(key)
        self.view.next_console()
        self.wheel(-120)
        self.assertEqual(self.view.shelf_id(), 'search')
        self.assertTrue(self.view.editing)
        self.view.type('done')
        self.view.back()
        self.view.select_shelf(self.view.index_of('sms'), slide=False)
        self.view.open_menu()
        self.assertIsNotNone(self.view.menu_items)
        self.view.previous_console()
        self.wheel(120)
        self.assertEqual(self.view.shelf_id(), 'sms')

    def test_favourites_and_back_to_the_console(self):
        self.view.select_shelf(self.view.index_of('sms'), slide=False)
        self.view.toggle_favorites()
        self.assertEqual(self.view.shelf_id(), 'favorites')
        self.assertEqual({g.title for g in self.view.games}, {'Super Mario Land', 'Sonic'})
        self.view.toggle_favorites()
        self.assertEqual(self.view.shelf_id(), 'sms')

    def test_search_typed_on_the_keyboard_then_closed_by_back(self):
        self.view.select_shelf(self.view.index_of('md'), slide=False)
        self.view.open_search()
        self.assertTrue(self.view.editing)
        for key in 'MARIO':
            self.view.type(key)
        self.assertEqual(self.view.shelf_id(), 'search')
        self.assertEqual([g.title for g in self.view.games], ['Super Mario Land'])
        self.view.type('done')
        self.assertFalse(self.view.editing)
        self.assertTrue(self.view.search_open)
        self.view.back()                                    # Back leaves the search first
        self.assertFalse(self.view.search_open)
        self.assertEqual(self.view.shelf_id(), 'md')
        self.view.open_search()
        self.view.type('done')                               # an empty search closes at once
        self.assertFalse(self.view.search_open)

    def test_back_asks_before_leaving_and_no_keeps_the_front_end(self):
        self.view.back()
        self.assertEqual(self.view.menu_heading, 'front_end_leave_question')
        self.assertEqual([key for key, _, _ in self.view.menu_items], ['front_end_yes', 'front_end_no'])
        self.view.step(1, 0)
        self.view.accept()                                  # No
        self.owner.toggle_front_end.assert_not_called()
        self.view.back()
        self.view.accept()                                  # Yes is chosen first
        self.owner.toggle_front_end.assert_called_once()

    def test_control_and_shift_clicks_choose_several_games_and_the_menu_acts_on_all(self):
        self.view.select_shelf(self.view.index_of('sms'), slide=False)
        layout = self.view.layout

        def click(index, state=0):
            x, y = layout.origin(index)
            event = Mock(x=x + 10, y=y + 10 - self.view.wall.canvasy(0), state=state)
            self.view.clicked(event)

        click(0)
        click(2, 0x4)
        click(4, 0x1)
        self.assertEqual(len(self.view.selected), 4)                        # 0, then 2 to 4
        keys = [key for key, _, _ in self.view.actions()]
        self.assertIn('front_end_find_covers', keys)
        self.assertIn('front_end_choose_covers', keys)
        dict((key, action) for key, action, _ in self.view.actions())['front_end_choose_covers']()
        chosen = self.owner.choose_compiled_covers.call_args[0][0]
        self.assertEqual(len(chosen), 4)
        self.view.back()                                                    # Back clears the selection first
        self.assertEqual(self.view.selected, set())
        self.assertIsNone(self.view.menu_items)

    def test_games_without_a_saved_cover_are_offered_an_online_search_for_the_front_end(self):
        self.view.select_shelf(self.view.index_of('gb'), slide=False)
        deadline = time.monotonic() + 5                      # the loader finds no saved cover for either game
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
            if all(fe.game_key(g) in self.view.no_cover for g in self.view.games):
                break
        items = {key: (action, enabled) for key, action, enabled in self.view.actions()}
        self.assertTrue(items['front_end_find_missing'][1])
        self.assertEqual(self.view.menu_label('front_end_find_missing'), "front_end_find_missing[('count', 2)]")
        self.view.cards.online_cover.return_value = None
        items['front_end_find_missing'][0]()
        self.assertEqual(self.view.searching, (0, 2, 0))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
            if self.view.searching is None:
                break
        self.assertEqual(self.view.cards.online_cover.call_count, 2)
        self.assertEqual(self.view.search_result, (2, 2, 0))

    def wait(self, condition, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not condition():
            self.root.update()
            time.sleep(0.01)

    def test_a_sharper_thumbnail_is_drawn_never_the_picture_of_the_old_one(self):
        """The blurred covers (20 Nov 2026): a thumbnail read again for a larger box must not be shown through the
        picture made, at the same size, from the smaller one."""
        from PIL import Image
        self.view.select_shelf(self.view.index_of('gb'), slide=False)
        self.root.update()
        target = self.view.games[0]
        key = fe.game_key(target)
        small = Image.new('RGB', (12, 16), 'red')
        self.view.events.put(('cover', self.view.loader.generation, key, small, 0.75))
        self.wait(lambda: key in self.view.thumbnails)
        self.view.draw_wall()
        old = {name: self.view.photos[name] for name in self.view.photos if name[0] == key}
        self.assertTrue(old)                                   # the small one, stretched to the tile
        sharp = Image.new('RGB', (300, 400), 'blue')
        self.view.events.put(('cover', self.view.loader.generation, key, sharp, 0.75))
        self.wait(lambda: self.view.thumbnails.get(key) is sharp)
        drawn = {self.view.wall.itemcget(item, 'image') for item in self.view.wall.find_withtag('tile')
                 if self.view.wall.type(item) == 'image'}
        self.assertTrue(drawn)
        self.assertFalse(drawn & {str(photo) for photo in old.values()})      # the old pictures are not reused

    def test_refresh_reads_the_cover_again_and_searches_it_online_only_when_missing_and_allowed(self):
        self.view.select_shelf(self.view.index_of('gb'), slide=False)
        self.wait(lambda: all(fe.game_key(g) in self.view.no_cover for g in self.view.games))
        target = self.view.games[0]
        items = {key: (action, enabled) for key, action, enabled in self.view.actions()}
        self.assertIn('front_end_refresh_cover', items)
        calls = self.view.cards.cached_cover.call_count
        self.owner.online.get.return_value = False                # online covers off: read again, nothing searched
        items['front_end_refresh_cover'][0]()
        self.wait(lambda: self.view.cards.cached_cover.call_count == calls + 1 and not self.view.refreshing)
        self.assertEqual(self.view.cards.cached_cover.call_count, calls + 1)
        self.view.cards.online_cover.assert_not_called()
        self.owner.online.get.return_value = True                 # on: still missing, so searched online
        self.view.cards.online_cover.return_value = None
        self.view.refresh_covers([target])
        self.wait(lambda: self.view.cards.online_cover.call_count == 1 and self.view.searching is None)
        self.view.cards.online_cover.assert_called_once_with(target)

    def test_the_round_scan_button_runs_the_compiled_games_scan_and_reads_every_cover_again(self):
        compiled = Mock(running=False)
        self.owner.ensure_compiled_view.return_value = compiled
        self.owner.compiled_view = compiled
        self.view.draw_tabs()
        box = next((x0, x1) for x0, x1, name in self.view.tool_boxes if name == 'scan')
        self.view.tab_clicked(Mock(x=(box[0] + box[1]) // 2))
        compiled.scan.assert_called_once_with()
        self.view.no_cover.add('x')
        calls = self.view.cards.cached_cover.call_count
        self.view.library_refreshed()
        self.assertNotIn('x', self.view.no_cover)
        self.wait(lambda: self.view.cards.cached_cover.call_count > calls)
        self.assertGreater(self.view.cards.cached_cover.call_count, calls)

    def test_the_cover_actions_open_the_box_art_window_of_gui_covers(self):
        self.view.select_shelf(self.view.index_of('sms'), slide=False)
        actions = {key: action for key, action, _ in self.view.actions()}
        actions['card_choose_cover']()
        self.owner.choose_compiled_covers.assert_called_once_with([self.view.focused()])

    def test_the_gamepad_does_nothing_while_a_game_runs(self):
        running = Mock()
        running.poll.return_value = None
        self.owner.compiled_view = Mock(game_process=running)
        pad = Mock()
        pad.poll.return_value = [(mask('r2'), 0, 0)] + [(0, 0, 0)] * 3
        self.view.controller = pad
        self.view.pad = fe.GridPad()
        self.view.pad.armed, self.view.pad.buttons = True, 0
        columns = self.view.layout.columns
        self.view.poll_controller()
        self.assertEqual(self.view.layout.columns, columns)
        self.view.controller = None


class FakeView:
    """Stands for FrontEndView in the mixin's tests: a frame that records what the window asks of it."""
    def __init__(self, owner, parent):
        import tkinter as tk
        self.frame = tk.Frame(parent)
        self.calls = []

    def __getattr__(self, name):
        if name in ('grid', 'grid_remove', 'winfo_manager'):
            return getattr(self.frame, name)
        return lambda *args, **kwargs: self.calls.append(name)


class Window(unittest.TestCase):
    """gui_front_end.FrontEndMixin on a stand-in window: entering and leaving, full screen, the start options."""

    def setUp(self):
        release_tk(self)                      # first: its cleanup runs after root.destroy
        import tkinter as tk
        from tkinter import ttk
        from unittest.mock import patch
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        from retrorecomp.gui_front_end import FrontEndMixin

        class Owner(FrontEndMixin):
            pass

        owner = self.owner = Owner()
        root = owner.app = self.root
        owner.tr = lambda key, **values: key
        owner.hint = Mock()
        owner.decorate_button = Mock()
        owner.queue_background = Mock()
        owner.toggle_compiled_games = Mock()
        owner.close_options = Mock()
        owner.options_panel = None
        owner.collection_visible = False
        owner.front_end_visible = owner.front_end_fullscreen = False
        owner.front_end_view = None
        owner.header = tk.Frame(root, height=10)
        owner.header.pack(fill='x')
        owner.header_stripe = tk.Frame(root, height=2)
        owner.header_stripe.pack(fill='x')
        owner.body = tk.Frame(root)
        owner.body.pack(fill='both', expand=True)
        owner.toolbar = tk.Frame(owner.body)
        owner.toolbar.grid(row=0, column=0)
        owner.compiled_button = ttk.Button(owner.toolbar)
        owner.compiled_button.pack(side='left')
        owner.queue_actions = tk.Frame(owner.toolbar)
        owner.queue_actions.pack(side='left')
        owner.credits_button = ttk.Button(owner.toolbar)
        owner.credits_button.pack(side='right')
        owner.count_label = ttk.Label(owner.toolbar)
        owner.count_label.pack(side='right')
        owner.report_button = ttk.Button(owner.toolbar)
        owner.report_button.pack(side='right')
        owner.knowledge_button = ttk.Button(owner.toolbar)
        owner.knowledge_button.pack(side='right')
        owner.place_count_label = lambda: owner.count_label.pack(side='right', before=owner.report_button)
        # The pair of buttons stands in its own frame, in the middle of the bar.
        owner.toolbar_centre = tk.Frame(owner.toolbar)
        owner.toolbar_centre.pack(side='left', expand=True)
        owner.front_end_button_create(owner.toolbar_centre, owner.toolbar).pack(side='right')
        owner.compiler_widgets = [tk.Frame(owner.body) for _ in range(2)]
        for row, widget in enumerate(owner.compiler_widgets, 1):
            widget.grid(row=row, column=0)
        footer = tk.Frame(owner.body)
        footer.grid(row=8, column=0)
        owner.status_dot = tk.Canvas(footer)
        self.fullscreen = []
        original = root.attributes

        def attributes(*args):
            if args and args[0] == '-fullscreen':
                self.fullscreen.append(args)          # never a real full screen in the suite
                return None
            return original(*args)

        root.attributes = attributes
        patcher = patch('retrorecomp.front_end_view.FrontEndView', FakeView)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_button_opens_in_the_window_and_full_screen_has_its_own_button(self):
        owner = self.owner
        self.assertEqual(owner.front_end_screen_button.winfo_manager(), '')     # hidden outside the front-end
        owner.front_end_button.invoke()
        # Arthur, 17 Nov 2026: the Front-end button stays in the window; Full screen appears left of it.
        self.assertTrue(owner.front_end_visible)
        self.assertFalse(owner.front_end_fullscreen)
        self.assertEqual(self.fullscreen, [])
        self.assertEqual(owner.front_end_screen_button.winfo_manager(), 'pack')
        # Left of Knowledge in the toolbar (packed right after it), no longer beside the Front-end button.
        order = owner.toolbar.pack_slaves()
        self.assertEqual(order.index(owner.front_end_screen_button), order.index(owner.knowledge_button) + 1)
        self.assertNotIn(owner.front_end_screen_button, owner.toolbar_centre.pack_slaves())
        self.assertEqual(owner.front_end_button.master, owner.toolbar_centre)
        # Arrows out to the corners; arrows in once the front-end fills the screen.
        self.assertEqual(owner.decorate_button.call_args_list[-1].args[1:], ('fullscreen_enter',))
        self.assertEqual((owner.header.winfo_manager(), owner.toolbar.winfo_manager()), ('pack', 'grid'))
        owner.front_end_screen_button.invoke()
        self.assertTrue(owner.front_end_visible and owner.front_end_fullscreen)
        self.assertEqual(self.fullscreen[-1], ('-fullscreen', True))
        self.assertEqual(owner.decorate_button.call_args_list[-1].args[1:], ('fullscreen_exit',))
        self.assertEqual(owner.front_end_screen_button.cget('text'), 'front_end_window')
        self.assertEqual(owner.header.winfo_manager(), '')
        self.assertEqual(owner.toolbar.winfo_manager(), '')
        self.assertEqual(owner.status_dot.master.winfo_manager(), '')
        self.assertTrue(all(w.winfo_manager() == '' for w in owner.compiler_widgets))
        self.assertIn('show', owner.front_end_view.calls)
        # X / F11: back to the window, still in the front-end.
        owner.set_front_end_fullscreen(False)
        self.assertEqual(owner.decorate_button.call_args_list[-1].args[1:], ('fullscreen_enter',))
        self.assertEqual(self.fullscreen[-1], ('-fullscreen', False))
        self.assertTrue(owner.front_end_visible)
        self.assertEqual((owner.header.winfo_manager(), owner.toolbar.winfo_manager()), ('pack', 'grid'))
        owner.set_front_end_fullscreen(True)
        # Leaving (from full screen): the window and the queue come back.
        owner.toggle_front_end()
        self.assertFalse(owner.front_end_visible or owner.front_end_fullscreen)
        self.assertEqual(self.fullscreen[-1], ('-fullscreen', False))
        self.assertEqual((owner.header.winfo_manager(), owner.toolbar.winfo_manager()), ('pack', 'grid'))
        self.assertTrue(all(w.winfo_manager() == 'grid' for w in owner.compiler_widgets))
        self.assertEqual(owner.queue_actions.winfo_manager(), 'pack')
        self.assertEqual(owner.front_end_screen_button.winfo_manager(), '')
        self.assertIn('close_controller', owner.front_end_view.calls)
        owner.toggle_compiled_games.assert_not_called()

    def test_opened_from_compiled_games_it_goes_back_there_and_can_open_in_a_window(self):
        owner = self.owner
        owner.collection_visible = True
        owner.toggle_compiled_games.side_effect = lambda: setattr(owner, 'collection_visible',
                                                                  not owner.collection_visible)
        owner.enter_front_end(fullscreen=False)
        self.assertFalse(owner.front_end_fullscreen)
        self.assertEqual(self.fullscreen, [])
        self.assertEqual(owner.header.winfo_manager(), 'pack')
        owner.leave_front_end()
        self.assertTrue(owner.collection_visible)
        self.assertEqual(owner.toggle_compiled_games.call_count, 2)

    def test_the_second_start_option_is_greyed_until_the_first_is_ticked(self):
        import tkinter as tk
        from tkinter import ttk
        owner = self.owner
        owner.start_front_end = tk.BooleanVar(master=self.root, value=False)
        owner.start_front_end_fullscreen = tk.BooleanVar(master=self.root, value=True)
        page = tk.Frame(self.root)

        def checkbox(parent, key, variable, hint):
            control = ttk.Checkbutton(parent, text=key, variable=variable)
            control.pack()
            return control

        first, second = owner.front_end_start_options(page, checkbox)
        self.assertTrue(second.instate(['disabled']))
        first.invoke()                                       # ticked: the second can be chosen
        self.assertTrue(owner.start_front_end.get())
        self.assertFalse(second.instate(['disabled']))
        first.invoke()                                       # unticked again: greyed
        self.assertTrue(second.instate(['disabled']))

    def test_the_start_options_are_window_preferences_never_given_to_a_converter(self):
        from retrorecomp.gui_common import INTERFACE_PREFERENCES
        self.assertIn('start_front_end', INTERFACE_PREFERENCES)
        self.assertIn('start_front_end_fullscreen', INTERFACE_PREFERENCES)


class CoverActions(unittest.TestCase):
    """A cover given in the box-art window (gui_covers) reaches the front-end's wall."""

    def test_a_cover_given_in_the_box_art_window_is_shown_on_the_wall(self):
        from retrorecomp.gui_covers import MissingCoversMixin
        owner = Mock(compiled_view=None)
        request = Mock(payload=b'png', game=game('Sonic', 'md'), key=('md', sha('mdSonic')))
        MissingCoversMixin.card_cover_shown(owner, request, 'cover_ask_ready')
        owner.front_end_view.cover_changed.assert_called_once_with(request.game)


if __name__ == '__main__':
    unittest.main()
