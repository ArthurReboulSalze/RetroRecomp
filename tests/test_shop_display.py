"""The RR coin shop in the converter (display only; buying happens on the
site): the catalog and frame pictures cached beside the player corner, the
framed portrait (the portrait on top, the frame larger), name styles, pins,
badges, header themes, and nothing drawn without a catalog."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from retrorecomp import online
from retrorecomp import gui
from retrorecomp.gui import (Application, PORTRAIT_SIZE, PIN_SIZE, draw_styled_text, frame_side, header_theme,
                             name_colours, sparkle_frame, _portrait_picture)
from tools.gui_patching import patch_gui

TOKEN = 'rr1_' + 'c' * 43
FRAME_URL = '/media/frames/frame_diamond.webp'
CATALOG = [
    {'id': 'explorer', 'slot': 'title', 'price': 50, 'name': {'en': 'Explorer', 'fr': 'Explorateur'}, 'data': {}},
    {'id': 'name_gold', 'slot': 'name_style', 'price': 150, 'name': {'en': 'Gold name'},
     'data': {'style': 'gold', 'colors': ['#ffd24a']}},
    {'id': 'name_gradient', 'slot': 'name_style', 'price': 400, 'name': {'en': 'Gold to amber'},
     'data': {'style': 'gradient', 'colors': ['#ffd24a', '#ff9a1f']}},
    {'id': 'name_sparkle', 'slot': 'name_style', 'price': 900, 'name': {'en': 'Sparkling gold'},
     'data': {'style': 'sparkle', 'colors': ['#ffd24a', '#fff4c2']}},
    {'id': 'badge_sms', 'slot': 'badge', 'price': 60, 'name': {'en': 'Master System badge'},
     'data': {'console': 'sms', 'label': 'SMS', 'color': '#2f6fd6'}},
    {'id': 'badge_md', 'slot': 'badge', 'price': 100, 'name': {'en': 'Mega Drive badge'},
     'data': {'console': 'md', 'label': 'MD', 'color': '#1f2937'}},
    {'id': 'badge_x68', 'slot': 'badge', 'price': 150, 'name': {'en': 'X68000 badge'},
     'data': {'console': 'x68', 'label': 'X68K', 'color': '#5b7083'}},
    {'id': 'badge_ng', 'slot': 'badge', 'price': 150, 'name': {'en': 'Neo Geo badge'},
     'data': {'console': 'ng', 'label': 'NEO', 'color': '#c9961a'}},
    {'id': 'header_classic', 'slot': 'header_theme', 'price': 0, 'name': {'en': 'Classic header'},
     'data': {'theme': 'classic', 'colors': None}},
    {'id': 'header_neon', 'slot': 'header_theme', 'price': 250, 'name': {'en': 'Neon header'},
     'data': {'theme': 'neon', 'colors': ['#1a0b33', '#3a0f5c', '#ff3fd2']}},
    {'id': 'pin_gold', 'slot': 'pin', 'price': 800, 'name': {'en': 'Gold pin'},
     'data': {'tier': 'gold', 'color': '#ffd24a'}},
    {'id': 'frame_diamond', 'slot': 'frame', 'price': 3000, 'name': {'en': 'Iridescent gem frame'},
     'data': {'image': FRAME_URL, 'hole': 0.537}},
    {'id': 'broken', 'slot': 7},
]
EQUIPPED = {'title': 'explorer', 'name_style': 'name_gradient', 'badges': ['badge_sms', 'badge_md'],
            'background': None, 'hover': None, 'header_theme': 'header_neon', 'pin': 'pin_gold',
            'frame': 'frame_diamond'}


def frame_image(colour=(40, 90, 230, 255)):
    """A 256 px frame: a coloured ring and, inside the hole, a red disc the
    portrait must cover."""
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, 255, 255), fill=colour)
    draw.ellipse((60, 60, 195, 195), fill=(255, 0, 0, 255))
    data = io.BytesIO()
    image.save(data, 'WEBP', lossless=True)
    return data.getvalue()


def portrait_bytes(colour=(0, 200, 0)):
    data = io.BytesIO()
    Image.new('RGB', (256, 256), colour).save(data, 'WEBP', lossless=True)
    return data.getvalue()


class FakeShopService(BaseHTTPRequestHandler):
    """The account view with items and equipped slots, the board, `GET shop`
    and the frame picture; `server.shop` = 'ok' or 'missing' (older server)."""
    def log_message(self, *args):
        pass

    def answer(self, status, payload=None, raw=None, kind='application/json'):
        data = raw if raw is not None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.calls.append(self.path)
        if self.path == '/api/v1/account':
            self.answer(200, {'email': 'p@example.test', 'pseudonym': 'Aurore', 'coins': {'balance': 120},
                              'title': {'id': 'explorer', 'name': {'en': 'Explorer'}}, 'titles': ['explorer'],
                              'items': ['explorer', 'name_gradient', 'badge_sms', 'badge_md', 'header_neon',
                                        'pin_gold', 'frame_diamond', 'header_classic'],
                              'equipped': EQUIPPED, 'avatar': {'url': None}})
        elif self.path.startswith('/api/v1/board'):
            self.answer(200, {'you': {'rank': 2, 'total': 4200}, 'entries': []})
        elif self.path == '/api/v1/shop':
            if self.server.shop == 'missing':
                self.answer(404, {'error': 'not_found'})
            else:
                self.answer(200, {'items': CATALOG})
        elif self.path == FRAME_URL:
            self.answer(200, raw=self.server.frame, kind=self.server.frame_type)
        else:
            self.answer(404, {'error': 'not_found'})


class ShopService(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / 'datas'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeShopService)
        self.server.calls, self.server.shop = [], 'ok'
        self.server.frame, self.server.frame_type = frame_image(), 'image/webp'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.patches = [patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                        patch('retrorecomp.paths.data_directory', return_value=self.data),
                        patch.object(online, '_owner_only')]
        for item in self.patches:
            item.start()
        online._save_account({'service': self.url, 'token': TOKEN, 'email': 'p@example.test', 'pseudonym': 'Aurore'})

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def calls(self, path):
        return sum(1 for call in self.server.calls if call == path)

    def test_the_player_corner_brings_the_catalog_and_the_equipped_frame_once(self):
        first = online.player(now=1000)
        self.assertEqual(online.owned(first['profile'])[:2], ['explorer', 'name_gradient'])
        self.assertEqual(online.equipped(first['profile'])['frame'], 'frame_diamond')
        self.assertIn('frame_diamond', first['shop'])
        self.assertNotIn('broken', first['shop'], 'a malformed catalog entry is left out')
        self.assertEqual(first['frame'], self.server.frame)
        self.assertEqual((self.calls('/api/v1/shop'), self.calls(FRAME_URL)), (1, 1))
        # Within PLAYER_REFRESH: nothing goes to the network, everything comes from datas/.
        again = online.player(now=1000 + 60)
        self.assertEqual(again['frame'], self.server.frame)
        self.assertEqual(online.cached_player()['shop'].keys(), first['shop'].keys())
        self.assertEqual(len(self.server.calls), 4)
        # The player stale, the catalog not yet: only the account and the board are read again.
        online.player(now=1000 + online.PLAYER_REFRESH + 1)
        self.assertEqual((self.calls('/api/v1/shop'), self.calls(FRAME_URL)), (1, 1))
        # The catalog stale too: fetched again, the frame picture is not.
        online.player(now=1000 + online.SHOP_REFRESH + 1)
        self.assertEqual((self.calls('/api/v1/shop'), self.calls(FRAME_URL)), (2, 1))
        self.assertTrue(any(path.name.startswith(online.FRAME_PREFIX) for path in self.data.iterdir()))
        # Signing out forgets the player, not the public catalog.
        online._save_account(None)
        self.assertIsNone(online.cached_player())

    def test_the_catalog_alone_refreshes_at_most_every_thirty_minutes(self):
        self.assertIn('pin_gold', online.shop(now=50))
        self.assertIn('pin_gold', online.shop(now=50 + online.SHOP_REFRESH - 1))
        self.assertEqual(self.calls('/api/v1/shop'), 1)
        online.shop(now=50 + online.SHOP_REFRESH + 1)
        self.assertEqual(self.calls('/api/v1/shop'), 2)

    def test_an_older_server_without_the_shop_draws_nothing_and_raises_nothing(self):
        self.server.shop = 'missing'
        data = online.player(now=1000)
        self.assertEqual(data['shop'], {})
        self.assertIsNone(data['frame'])
        looks = online.looks(data['shop'], online.equipped(data['profile']))
        self.assertTrue(all(value is None for slot, value in looks.items() if slot != 'badges'))
        self.assertEqual(looks['badges'], [])

    def test_offline_the_last_catalog_stays_and_without_one_nothing_is_drawn(self):
        self.assertEqual(online.cached_shop(), {})
        online.shop(now=10)
        with patch.object(online, '_call', side_effect=online.ServiceConnectionError()):
            self.assertIn('frame_diamond', online.shop(now=10 + online.SHOP_REFRESH + 5))
            (self.data / online.SHOP_NAME).unlink()
            self.assertEqual(online.shop(force=True), {})
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertEqual(online.shop(force=True), {}, 'service turned off')

    def test_a_frame_picture_comes_only_from_the_service_as_an_image(self):
        frame = {'id': 'frame_x', 'slot': 'frame', 'data': {'image': FRAME_URL, 'hole': 0.6}}
        for bad in ('https://elsewhere.example/frame.webp', '//elsewhere.example/frame.webp',
                    '/media/../account.json', 'media/frame.webp', '/media/frame.webp?x=1', None, 7):
            self.assertIsNone(online._media_url(bad), bad)
        self.assertEqual(online._media_url(self.url + FRAME_URL), self.url + FRAME_URL)
        self.assertIsNone(online.frame_picture({**frame, 'slot': 'pin'}))
        self.server.frame_type = 'text/html'
        self.assertIsNone(online.frame_picture(frame))
        self.assertIsNone(online.frame_picture(frame, download=False), 'nothing cached from a refused answer')
        self.server.frame_type = 'image/webp'
        self.assertEqual(online.frame_picture(frame), self.server.frame)
        self.assertEqual(online.frame_picture(frame, download=False), self.server.frame)

    def test_looks_keep_each_item_in_its_own_slot(self):
        catalog = online._catalog(CATALOG)
        view = online.equipped({'equipped': {'name_style': 'pin_gold', 'pin': 'pin_gold', 'frame': 'unknown',
                                             'badges': ['badge_sms', 'name_gold', 'badge_md', 'badge_x68',
                                                        'badge_ng'], 'header_theme': 5}})
        self.assertEqual(online.SHOP_BADGES, 1, "the site's RR_SHOP_BADGES")
        self.assertEqual(view['badges'], ['badge_sms'], 'one badge shown')
        looks = online.looks(catalog, view)
        self.assertIsNone(looks['name_style'])
        self.assertEqual(looks['pin']['id'], 'pin_gold')
        self.assertIsNone(looks['frame'])
        self.assertIsNone(looks['header_theme'])
        self.assertEqual([badge['id'] for badge in looks['badges']], ['badge_sms'])
        # An id of another slot is never drawn as a badge.
        self.assertEqual([badge['id'] for badge in online.looks(catalog, {'badges': ['name_gold', 'badge_md']})['badges']],
                         ['badge_md'])
        self.assertEqual(online.looks({}, view)['badges'], [])
        self.assertEqual(online.equipped(None)['badges'], [])


class FramedPortrait(unittest.TestCase):
    def test_the_portrait_keeps_44_px_on_top_and_the_frame_is_drawn_larger(self):
        picture = _portrait_picture(portrait_bytes(), 'A', (frame_image(), 0.537))
        side = frame_side(0.537)
        self.assertEqual(side, 78)
        self.assertEqual(picture.size, (side, side))
        centre = picture.getpixel((side // 2, side // 2))
        self.assertEqual(centre[:3], (0, 200, 0), 'the portrait covers the frame hole')
        # Just outside the portrait's 44 px disc, the frame's ring shows.
        ring = picture.getpixel((side // 2, (side - PORTRAIT_SIZE) // 2 - 3))
        self.assertGreater(ring[2], 150)
        self.assertLess(ring[0], 120)
        # The portrait spans exactly 44 px: green inside, ring outside.
        inside = picture.getpixel((side // 2, (side - PORTRAIT_SIZE) // 2 + 3))
        self.assertGreater(inside[1], 150)
        for hole, expected in ((0.646, 64), (0.609, 68)):
            self.assertEqual(frame_side(hole), expected)
            self.assertEqual((frame_side(hole) - PORTRAIT_SIZE) % 2, 0)

    def test_without_a_usable_frame_the_plain_ringed_portrait_stays(self):
        for frame in (None, (b'not an image', 0.6), (frame_image(), 'x'), (frame_image(), 5)):
            self.assertEqual(_portrait_picture(portrait_bytes(), 'A', frame).size, (PORTRAIT_SIZE, PORTRAIT_SIZE))


class NameStyles(unittest.TestCase):
    STYLES = {item['id']: item for item in CATALOG}

    def test_gold_gradient_and_plain(self):
        self.assertEqual(name_colours(self.STYLES['name_gold'], 4), ['#ffd24a'] * 4)
        gradient = name_colours(self.STYLES['name_gradient'], 5)
        self.assertEqual((gradient[0], gradient[-1]), ('#ffd24a', '#ff9a1f'))
        self.assertEqual(len(set(gradient)), 5)
        self.assertIsNone(name_colours(None, 4))
        self.assertIsNone(name_colours({'data': {'style': 'rainbow'}}, 4))
        self.assertIsNone(name_colours(self.STYLES['name_gold'], 0))
        self.assertEqual(name_colours({'data': {'style': 'gold', 'colors': ['red']}}, 1), ['#ffd24a'])

    def test_sparkle_is_gold_with_a_slow_light_band(self):
        style = self.STYLES['name_sparkle']
        self.assertEqual(name_colours(style, 6), ['#ffd24a'] * 6)
        frames = [tuple(name_colours(style, 6, phase)) for phase in (0.1, 0.25, 0.4, 0.9)]
        self.assertGreater(len(set(frames)), 2, 'the band moves')
        self.assertEqual(frames[-1], ('#ffd24a',) * 6, 'then the name rests in gold')
        self.assertLessEqual(gui.SPARKLE_FRAME, 250)
        self.assertGreaterEqual(gui.SPARKLE_FRAME, 100, 'a few frames a second, no more')

    def test_header_themes(self):
        styles = self.STYLES
        self.assertIsNone(header_theme(styles['header_classic']))
        self.assertIsNone(header_theme(None))
        self.assertEqual(header_theme(styles['header_neon']), ('neon', '#1a0b33', '#3a0f5c', '#ff3fd2'))
        self.assertEqual(header_theme({'data': {'theme': 'night'}})[0], 'night')
        self.assertIsNone(header_theme({'data': {'theme': 'unknown'}}))


class Drawing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # a CI runner without a display
            raise unittest.SkipTest(str(error))
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.canvas = tk.Canvas(self.root, width=760, height=300)
        self.catalog = online._catalog(CATALOG)

    def tearDown(self):
        self.canvas.destroy()

    def test_a_styled_name_draws_one_item_per_letter_and_a_plain_one_a_single_item(self):
        items, width = draw_styled_text(self.canvas, 10, 10, 'Aurore', ('TkDefaultFont', 10, 'bold'),
                                        self.catalog['name_gradient'])
        self.assertEqual(len(items), 6)
        self.assertGreater(width, 20)
        self.assertEqual(self.canvas.itemcget(items[0], 'fill'), '#ffd24a')
        self.assertEqual(self.canvas.itemcget(items[-1], 'fill'), '#ff9a1f')
        plain, _ = draw_styled_text(self.canvas, 10, 40, 'Aurore', ('TkDefaultFont', 10, 'bold'), None)
        self.assertEqual(len(plain), 1)
        # Centred and right-aligned names keep their place.
        for anchor, expected in (('center', lambda box: (box[0] + box[2]) / 2), ('ne', lambda box: box[2]),
                                 ('e', lambda box: box[2]), ('w', lambda box: box[0])):
            self.canvas.delete('all')
            items, _ = draw_styled_text(self.canvas, 300, 100, 'Aurore', ('TkDefaultFont', 10, 'bold'),
                                        self.catalog['name_gold'], anchor=anchor, tags=('name',))
            self.assertAlmostEqual(expected(self.canvas.bbox('name')), 300, delta=3, msg=anchor)
            box = self.canvas.bbox('name')
            if anchor in ('center', 'e', 'w'):
                self.assertAlmostEqual((box[1] + box[3]) / 2, 100, delta=3, msg=anchor)
            else:
                self.assertAlmostEqual(box[1], 100, delta=3, msg=anchor)

    def test_the_sparkle_stops_while_the_window_is_hidden(self):
        items, _ = draw_styled_text(self.canvas, 10, 10, 'Aurore', ('TkDefaultFont', 10, 'bold'),
                                    self.catalog['name_sparkle'])
        self.assertEqual(len(self.canvas._sparkle), 6)
        self.assertFalse(sparkle_frame(self.canvas, now=0.8), 'withdrawn window: no animation')
        with patch.object(self.canvas, 'winfo_viewable', return_value=True):
            self.assertTrue(sparkle_frame(self.canvas, now=gui.SPARKLE_PERIOD * 0.25))
            first = [self.canvas.itemcget(item, 'fill') for item in items]
            sparkle_frame(self.canvas, now=gui.SPARKLE_PERIOD * 0.4)
            second = [self.canvas.itemcget(item, 'fill') for item in items]
        self.assertNotEqual(first, second)
        self.canvas.delete('all')
        with patch.object(self.canvas, 'winfo_viewable', return_value=True):
            self.assertFalse(sparkle_frame(self.canvas), 'nothing left to animate')

    def board_application(self):
        app = Application.__new__(Application)
        app.language, app.ui_font = 'fr', 'TkDefaultFont'
        return app

    def test_the_board_draws_styles_badges_pins_and_titles_with_a_catalog(self):
        entry = {'rank': 1, 'pseudonym': 'Aurore', 'games': 12, 'total': 4200,
                 'title': {'id': 'explorer', 'name': {'en': 'Explorer', 'fr': 'Explorateur'}},
                 'equipped': {'name_style': 'name_sparkle', 'badges': ['badge_sms', 'badge_md', 'badge_x68'],
                              'pin': 'pin_gold', 'frame': 'frame_diamond', 'hover': None}}
        other = {'rank': 2, 'pseudonym': 'Basile', 'games': 3, 'total': 90}
        app = self.board_application()
        app.draw_board_rows(self.canvas, [(entry, {'gold': 2}), (other, {})], 760, 'Basile', self.catalog)
        texts = [self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag('board_badge')
                 if self.canvas.type(item) == 'text']
        self.assertEqual(texts, ['SMS'], 'the badge shown, without a first-place mark')
        self.assertTrue(self.canvas.find_withtag('board_pin'))
        self.assertEqual([self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag('board_title')],
                         ['Explorateur'])
        self.assertEqual(len(self.canvas.find_withtag('board_name')), len('Aurore') + 1)
        self.assertEqual(len(self.canvas._sparkle), len('Aurore'))
        # Without the shop's catalog: the names, titles and numbers only.
        app.draw_board_rows(self.canvas, [(entry, {'gold': 2})], 760, None, {})
        self.assertFalse(self.canvas.find_withtag('board_badge'))
        self.assertFalse(self.canvas.find_withtag('board_pin'))
        self.assertEqual(len(self.canvas.find_withtag('board_name')), 1)
        self.assertTrue(self.canvas.find_withtag('board_title'))

    def test_a_first_place_badge_has_its_mark_on_the_board_as_in_the_header(self):
        entry = {'rank': 1, 'pseudonym': 'Aurore', 'total': 4200, 'equipped': {'badges': ['badge_sms']},
                 'top_badges': ['badge_sms']}
        other = {'rank': 2, 'pseudonym': 'Basile', 'total': 90, 'equipped': {'badges': ['badge_md']},
                 'top_badges': ['badge_sms']}   # first on another console than the one shown
        app = self.board_application()
        for row, expected in ((entry, ['SMS', '1']), (other, ['MD'])):
            app.draw_board_rows(self.canvas, [(row, {})], 760, None, self.catalog)
            texts = [self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag('board_badge')
                     if self.canvas.type(item) == 'text']
            self.assertEqual(texts, expected)
        # The podium draws its badge with the same function and mark.
        self.canvas.delete('all')
        gui.draw_badges(self.canvas, 10, 20, online.looks(self.catalog, online.equipped(entry))['badges'],
                        ('TkDefaultFont', 7, 'bold'), tags=('podium_badge',), top=online.top_badges(entry))
        self.assertIn('1', [self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag('podium_badge')
                            if self.canvas.type(item) == 'text'])

    def test_the_pin_glyph_has_the_tiers_colour(self):
        gui.draw_pin(self.canvas, 0, 0, self.catalog['pin_gold'], tags=('pin',))
        colours = {self.canvas.itemcget(item, 'fill') for item in self.canvas.find_withtag('pin')}
        self.assertEqual(colours, {'#ffd24a'})
        box = self.canvas.bbox('pin')
        self.assertLessEqual(box[2] - box[0], PIN_SIZE + 2)


class ShopButton(unittest.TestCase):
    def test_options_open_the_shop_of_the_account_page(self):
        app = Application.__new__(Application)
        with patch_gui('SENDING_AVAILABLE', True), \
                patch('retrorecomp.online.service_url', return_value='https://retro-recomp.com'), \
                patch('webbrowser.open_new_tab') as opened:
            app.open_account_shop()
        opened.assert_called_once_with('https://retro-recomp.com/account#shop')
        with patch_gui('SENDING_AVAILABLE', False), \
                patch('webbrowser.open_new_tab') as opened:
            app.open_account_shop()
        opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
