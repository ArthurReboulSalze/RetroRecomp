"""The leaderboard « Marches » (Arthur's pick, 20 Nov 2026): the player's row pinned at the foot while out of view, and how far
the next place is (none, first, behind); the podium's real portraits and the rows without any (Arthur, 21 Nov 2026).
Made-up rows and pictures; a withdrawn window, nothing shown, no network (the opener is a stand-in)."""
import io
import os
import tempfile
import tkinter as tk
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from retrorecomp import online
from retrorecomp.gui import Application
from retrorecomp.gui_leaderboard import board_messages, next_place, podium_paths
from tests.tk_cleanup import release_tk


def rows(*totals):
    return [({'rank': index, 'pseudonym': f'P{index}', 'total': total, 'games': 3, 'avatar': f'/avatars/p{index}.webp'},
             {'gold': 1}) for index, total in enumerate(totals, 1)]


def picture(colour=(40, 160, 220)):
    """A small made-up portrait, as PNG bytes."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (64, 64), colour).save(buffer, 'PNG')
    return buffer.getvalue()


class Response:
    """A stand-in for the opener's answer."""
    def __init__(self, body, kind='image/webp'):
        self.body, self.kind = body, kind
        self.headers = self

    def get_content_type(self):
        return self.kind

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class BoardPortraits(unittest.TestCase):
    """online.board_portrait: a board entry's public portrait, downloaded once into datas/ under its public file name."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        for patcher in (patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': 'https://retro-recomp.com'}),
                        patch('retrorecomp.online._account_path', return_value=self.folder / 'account.json')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def opener(self, *answers):
        opened = patch.object(online._OPENER, 'open', side_effect=list(answers))
        self.addCleanup(opened.stop)
        return opened.start()

    def test_only_a_file_of_the_site_s_avatars_is_fetched(self):
        opened = self.opener()
        for value in (None, '', 42, '/shop/frame.webp', '/avatars/', '/avatars/a/b.webp', '/avatars/../account.json',
                      'https://elsewhere.example/avatars/a.webp', '//elsewhere.example/avatars/a.webp'):
            self.assertIsNone(online.board_portrait(value), value)
        opened.assert_not_called()

    def test_a_portrait_is_downloaded_once_with_a_small_timeout_then_read_from_datas(self):
        body = picture()
        opened = self.opener(Response(body))
        self.assertIsNone(online.board_portrait('/avatars/p1.webp', download=False))     # not cached: no request
        opened.assert_not_called()
        self.assertEqual(online.board_portrait('/avatars/p1.webp'), body)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, 'https://retro-recomp.com/avatars/p1.webp')
        self.assertNotIn('Authorization', request.headers)                               # a public file
        self.assertEqual(opened.call_args.kwargs['timeout'], online.BOARD_PORTRAIT_TIMEOUT)
        self.assertLessEqual(online.BOARD_PORTRAIT_TIMEOUT, 10)
        self.assertEqual((self.folder / 'board-portrait-p1.webp').read_bytes(), body)
        self.assertEqual(online.board_portrait('/avatars/p1.webp', download=False), body)
        self.assertEqual(online.board_portrait('https://retro-recomp.com/avatars/p1.webp'), body)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['board-portrait-p1.webp'])

    def test_a_failure_or_something_else_than_a_picture_gives_none_and_writes_nothing(self):
        self.opener(Response(b'<html>', 'text/html'), Response(b''),
                    urllib.error.HTTPError('u', 404, 'gone', {}, io.BytesIO()), OSError('offline'),
                    Response(b'x' * (online.BOARD_PORTRAIT_LIMIT + 1)))
        for _ in range(5):
            self.assertIsNone(online.board_portrait('/avatars/p1.webp'))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_only_the_most_recently_used_portraits_are_kept(self):
        self.opener(*[Response(picture()) for _ in range(online.BOARD_PORTRAIT_KEEP + 3)])
        for index in range(online.BOARD_PORTRAIT_KEEP + 3):
            online.board_portrait(f'/avatars/p{index}.webp')
            os.utime(self.folder / f'board-portrait-p{index}.webp', (1_000_000 + index, 1_000_000 + index))
        online._prune_board_portraits()
        kept = sorted(int(p.stem[len('board-portrait-p'):]) for p in self.folder.glob('board-portrait-*'))
        self.assertEqual(kept, list(range(3, online.BOARD_PORTRAIT_KEEP + 3)))


class LoadingTheBoard(unittest.TestCase):
    """board_messages: the board first (with the cached podium portraits), the downloads after, the first three only."""

    def entries(self, count=5):
        return [entry for entry, _ in rows(*range(900, 900 - 100 * count, -100))]

    def run_loader(self, cached=(), downloaded=None, board=None):
        calls = []
        def portrait(path, download=True):
            calls.append((path, download))
            if path in cached:
                return b'cached:' + path.encode()
            return (downloaded or {}).get(path) if download else None
        answer = board if board is not None else {'entries': self.entries()}
        with patch('retrorecomp.online.board', return_value=answer), patch('retrorecomp.online.shop', return_value={}), \
                patch('retrorecomp.online.board_portrait', side_effect=portrait):
            return list(board_messages('all', str)), calls

    def test_only_the_podium_s_three_portraits_are_asked_for(self):
        self.assertEqual(podium_paths(self.entries()), ['/avatars/p1.webp', '/avatars/p2.webp', '/avatars/p3.webp'])
        self.assertEqual(podium_paths([{'avatar': None}, {}, {'avatar': '/avatars/p3.webp'}, {'avatar': '/avatars/x'}]),
                         ['/avatars/p3.webp'])
        _messages, calls = self.run_loader(downloaded={'/avatars/p2.webp': b'two'})
        self.assertEqual({path for path, _ in calls}, {'/avatars/p1.webp', '/avatars/p2.webp', '/avatars/p3.webp'})

    def test_the_board_comes_first_and_the_downloads_after_it(self):
        messages, calls = self.run_loader(cached={'/avatars/p1.webp'}, downloaded={'/avatars/p2.webp': b'two'})
        self.assertEqual([m[0] for m in messages], ['board', 'portraits'])
        self.assertEqual(messages[0][2], {'/avatars/p1.webp': b'cached:/avatars/p1.webp'})
        self.assertEqual(messages[1][1], {'/avatars/p2.webp': b'two'})                 # p3 failed: the fallback stays
        self.assertEqual(calls[:3], [(f'/avatars/p{i}.webp', False) for i in (1, 2, 3)])
        self.assertEqual(calls[3:], [('/avatars/p2.webp', True), ('/avatars/p3.webp', True)])

    def test_all_cached_means_no_download_and_a_board_without_portraits_means_none(self):
        messages, calls = self.run_loader(cached={f'/avatars/p{i}.webp' for i in (1, 2, 3)})
        self.assertEqual([m[0] for m in messages], ['board'])
        self.assertFalse([call for call in calls if call[1]])
        bare = {'entries': [{'rank': 1, 'pseudonym': 'A', 'total': 9}]}               # a site without the field
        messages, calls = self.run_loader(board=bare)
        self.assertEqual((len(messages), messages[0][2], calls), (1, {}, []))

    def test_a_portrait_that_raises_is_only_a_missing_one(self):
        with patch('retrorecomp.online.board', return_value={'entries': self.entries(1)}), \
                patch('retrorecomp.online.shop', return_value={}), \
                patch('retrorecomp.online.board_portrait', side_effect=RuntimeError('broken')):
            messages = list(board_messages('all', str))
        self.assertEqual([m[0] for m in messages], ['board', 'portraits'])
        self.assertEqual(messages[1][1], {})

    def test_an_unreachable_board_says_so_and_fetches_no_portrait(self):
        with patch('retrorecomp.online.board', side_effect=online.ServiceConnectionError()), \
                patch('retrorecomp.online.board_portrait') as portrait:
            messages = list(board_messages('all', lambda exc: 'offline'))
        self.assertEqual(messages, [('board', (None, 'offline', {}), {})])
        portrait.assert_not_called()


class NextPlace(unittest.TestCase):
    def test_a_player_not_in_the_rows_gets_nothing(self):
        self.assertIsNone(next_place(rows(900, 800), 'Someone'))
        self.assertIsNone(next_place(rows(900, 800), None))

    def test_the_first_player_leads(self):
        self.assertEqual(next_place(rows(900, 800), 'P1')['state'], 'first')

    def test_a_player_in_the_middle_is_told_the_points_to_pass_the_one_above(self):
        place = next_place(rows(900, 800, 700), 'P2')
        self.assertEqual((place['state'], place['gap'], place['above']['pseudonym']), ('behind', 101, 'P1'))
        self.assertAlmostEqual(place['share'], (800 - 700) / (900 - 700))

    def test_the_last_one_measures_from_zero(self):
        place = next_place(rows(900, 300), 'P2')
        self.assertEqual(place['gap'], 601)
        self.assertAlmostEqual(place['share'], 300 / 900)


class OnACanvas(unittest.TestCase):
    """A withdrawn root, a canvas and an Application without its window."""

    def setUp(self):
        release_tk(self)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.canvas = tk.Canvas(self.root, width=760, height=80)
        self.app = Application.__new__(Application)
        self.app.language, self.app.ui_font = 'fr', 'TkDefaultFont'

    def texts(self, tag):
        return [self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag(tag)
                if self.canvas.type(item) == 'text']


class PinnedFoot(OnACanvas):
    def test_out_of_view_the_player_s_row_is_pinned_with_the_way_to_the_next_place(self):
        board = rows(900, 800, 700)
        place = self.app.draw_board_pinned(self.canvas, board, 760, 'P3', {}, visible=False)
        self.assertEqual(place['state'], 'behind')
        self.assertIn('P3', ''.join(self.texts('pinned_row')))
        self.assertEqual(self.texts('next_place_text'),
                         [self.app.tr('leaderboard_next', points=self.app.count_text(101), name='P2', rank=2)])
        self.assertIn('101', self.texts('next_place_text')[0])

    def test_in_view_only_the_way_to_the_next_place_is_shown(self):
        self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'P2', {}, visible=True)
        self.assertFalse(self.canvas.find_withtag('pinned_row'))
        self.assertTrue(self.texts('next_place_text'))

    def test_the_first_player_is_told_they_lead(self):
        self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'P1', {}, visible=False)
        self.assertEqual(self.texts('next_place_text'), [self.app.tr('leaderboard_first')])

    def test_a_player_outside_the_rows_gets_no_foot(self):
        self.assertIsNone(self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'Someone', {}, visible=False))
        self.assertFalse(self.canvas.find_all())

    def test_the_player_s_own_row_is_gold_rimmed_in_the_list(self):
        self.app.draw_board_rows(self.canvas, rows(900, 800, 700), 760, 'P2', {})
        outlines = {self.canvas.itemcget(item, 'outline') for item in self.canvas.find_all()
                    if self.canvas.type(item) == 'polygon'}
        self.assertIn('#d4a737', outlines)


class RowsWithoutPortraits(OnACanvas):
    """The ranking rows and the pinned row: the rank chip, then the name; no avatar circle, letter or picture."""

    def test_a_row_has_no_avatar_circle_letter_or_picture(self):
        self.app.draw_board_rows(self.canvas, rows(900, 800, 700, 600), 760, 'P2', {})
        kinds = {self.canvas.type(item) for item in self.canvas.find_all()}
        self.assertNotIn('oval', kinds)
        self.assertNotIn('image', kinds)                     # no gem pictures given here: none at all
        self.assertFalse([text for text in self.texts('all') if len(text) == 1 and text.isalpha()])

    def test_the_name_starts_under_the_column_caption(self):
        self.app.draw_board_rows(self.canvas, rows(900), 760, None, {})
        name = self.canvas.find_withtag('board_name')[0]
        player_left = self.app.board_columns(760)['player'][0]
        self.assertEqual(self.canvas.coords(name)[0], player_left + 10)
        chip_right = self.app.board_columns(760)['rank'][0] + 8 + 34
        self.assertGreaterEqual(self.canvas.coords(name)[0] - chip_right, 12)       # a clear step after the chip

    def test_the_pinned_row_has_no_avatar_either_and_its_bar_lines_up_with_the_names(self):
        self.app.draw_board_pinned(self.canvas, rows(900, 800, 700), 760, 'P3', {}, visible=False)
        self.assertNotIn('oval', {self.canvas.type(item) for item in self.canvas.find_withtag('pinned_row')})
        bar = min(self.canvas.bbox(item)[0] for item in self.canvas.find_withtag('next_place')
                  if self.canvas.type(item) == 'polygon')
        self.assertLessEqual(abs(bar - (self.app.board_columns(760)['player'][0] + 10)), 2)


class PodiumPortrait(OnACanvas):
    """The podium's portrait: the player's picture, or the quiet fallback; one picture kept per player, place and size."""

    def test_a_portrait_and_the_fallback_are_drawn_as_pictures(self):
        drawn = self.app.podium_portrait(self.canvas, 100, 40, 20, 1, picture(), key='/avatars/p1.webp')
        fallback = self.app.podium_portrait(self.canvas, 200, 40, 20, 2, None, key='/avatars/p2.webp')
        self.assertEqual({self.canvas.type(drawn), self.canvas.type(fallback)}, {'image'})
        self.assertEqual(self.canvas.find_withtag('podium_portrait'), (drawn, fallback))
        self.assertEqual(len(self.canvas._portraits), 2)

    def test_the_animation_s_redraws_reuse_the_picture(self):
        raw = picture()
        first = self.app.podium_portrait(self.canvas, 100, 40, 20, 1, raw, key='/avatars/p1.webp')
        again = self.app.podium_portrait(self.canvas, 100, 30, 20, 1, raw, key='/avatars/p1.webp')
        self.assertEqual(self.canvas.itemcget(first, 'image'), self.canvas.itemcget(again, 'image'))
        self.assertEqual(len(self.canvas._portraits), 1)

    def test_an_unreadable_portrait_falls_back_quietly(self):
        from retrorecomp.gui_drawing import _podium_picture
        broken = _podium_picture(b'not a picture', 40, '#d4a737', '#333333', '#777777')
        fallback = _podium_picture(None, 40, '#d4a737', '#333333', '#777777')
        self.assertEqual(broken.size, (40, 40))
        self.assertEqual(broken.tobytes(), fallback.tobytes())
        real = _podium_picture(picture((200, 30, 30)), 40, '#d4a737', '#333333', '#777777')
        self.assertEqual(real.getpixel((20, 20))[:3], (200, 30, 30))               # the player's own picture
        self.assertEqual(real.getpixel((0, 0))[3], 0)                              # round: the corners are clear


if __name__ == '__main__':
    unittest.main()
