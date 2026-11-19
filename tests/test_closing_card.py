"""The closing card (retrorecomp/closing_card_view.py, reached through gui_leaderboard.closing_card and
offer_closing_card): its four choices and what each returns, the shared « New paths » list behind « Recompile », the greyed
Send button, the keys and the two-second animation. The real window is built withdrawn, its data in a temporary folder; the
list is patched in (no real modal), and no ROM or game is involved."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from retrorecomp import closing_card_view as view
from retrorecomp.closing_card_view import ClosingCard
from retrorecomp.compiled_games import Game
from retrorecomp.gui import Application
from tools.gui_patching import keep_window_data_in, patch_gui


def game(title, system='gb', index=0, hints=2):
    return Game(f'C:/games/{system}/{title}.exe', system, f'{index:02x}' * 32, title, status='new_hints', hints=hints)


GAMES = [game('Sonic 2', 'md', 1, 5), game('Super Mario Land', 'gb', 2, 4), game('Contra', 'nes', 3, 2),
         game('Alex Kidd', 'sms', 4, 1)]


def all_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from all_widgets(child)


def pressed(window, text):
    button = next(w for w in all_widgets(window) if w.winfo_class() == 'TButton' and w.cget('text') == text)
    button.invoke()


class CardWindow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        keep_window_data_in(self, folder / 'datas')       # never the player's real Export/datas
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        with patch_gui('load_preferences', return_value={'language': 'en'}), \
                patch_gui('preferred_games_root', return_value=(folder / 'exports', False)):
            self.app = Application(self.root)
        self.root.update_idletasks()
        self.addCleanup(self.close_window)

    def close_window(self):
        owners = {name: widget for widget in all_widgets(self.root) for name in (widget._tclCommands or [])}
        for job in self.root.tk.call('after', 'info'):
            command = self.root.tk.call('after', 'info', job)[0]
            owners.get(command, self.root).after_cancel(job)
        self.root.destroy()

    def card(self, games=GAMES, **options):
        card = ClosingCard(self.app, games, **options)
        self.addCleanup(card.pick, None)
        self.root.update()
        return card

    def shown(self, act, sending=True, games=GAMES):
        """Open the card as the converter does (`closing_card`); `act(window)` plays the player's part, closing the card as a
        button does. Returns what the card returned."""
        def wait(window):
            self.root.update()
            act(window)
        with patch.object(self.root, 'wait_window', side_effect=wait), \
                patch('retrorecomp.gui_leaderboard.SENDING_AVAILABLE', sending):
            return self.app.closing_card(games)


class Choices(CardWindow):
    def test_each_of_the_four_choices_returns_what_it_returned_before(self):
        for text, expected in (('Recompile 4 games, then close', 'recompile'), ('Send and close', 'send'),
                               ('Close without sending', 'skip'), ('Cancel', None)):
            with self.subTest(choice=text), patch.object(self.app, 'new_paths_dialog', return_value=list(GAMES)):
                self.assertEqual(self.shown(lambda window: pressed(window, text)), expected)

    def test_the_card_names_the_two_routes_and_the_two_ways_of_sending(self):
        card = self.card()
        texts = [w.cget('text') for w in all_widgets(card.win) if w.winfo_class() == 'Label']
        tr = self.app.tr
        for key in ('closing_card_recompile', 'closing_card_send'):
            self.assertIn(tr(key), texts)
        canvas_texts = [card.art.itemcget(item, 'text') for item in card.art.find_all() if card.art.type(item) == 'text']
        for key in ('closing_route_pc', 'closing_route_base', 'closing_count'):
            self.assertIn(tr(key), canvas_texts)

    def test_one_game_says_discovery_in_the_singular(self):
        card = self.card([game('Sonic 2', 'md', 1, 1)])
        canvas_texts = [card.art.itemcget(item, 'text') for item in card.art.find_all() if card.art.type(item) == 'text']
        self.assertIn(self.app.tr('closing_count_one'), canvas_texts)

    def test_the_tab_order_is_recompile_send_skip_cancel(self):
        self.assertEqual(self.card().focus_order(), ['Recompile 4 games, then close', 'Send and close',
                                                     'Close without sending', 'Cancel'])


class Recompile(CardWindow):
    def test_recompile_opens_the_shared_list_with_the_cards_games_and_keeps_the_ticked_ones(self):
        with patch.object(self.app, 'new_paths_dialog', return_value=GAMES[:2]) as listing:
            self.assertEqual(self.shown(lambda window: pressed(window, 'Recompile 4 games, then close')), 'recompile')
        listing.assert_called_once_with(GAMES)
        self.assertEqual(self.app.closing_selection, GAMES[:2])

    def test_closing_recompiles_only_the_games_ticked_in_the_list(self):
        self.app.closing_checked = False
        with patch.object(self.app, 'games_with_new_paths', return_value=GAMES), \
                patch('retrorecomp.compiled_games.refresh_changed', return_value=0), \
                patch.object(self.app, 'new_paths_dialog', return_value=[GAMES[0], GAMES[2]]), \
                patch.object(self.app, 'reconvert_games') as reconvert, patch.object(self.app, 'toggle_compiled_games'), \
                patch.object(self.root, 'wait_window', side_effect=lambda window: pressed(window, 'Recompile 4 games, then close')):
            self.assertTrue(self.app.offer_closing_card())
        self.assertEqual([g.title for g in reconvert.call_args.args[0]], ['Sonic 2', 'Contra'])
        self.assertTrue(self.app.close_when_idle and self.app.closing_after_recompile)

    def test_cancelling_the_list_brings_back_the_card_and_runs_nothing(self):
        card = self.card()
        with patch.object(self.app, 'new_paths_dialog', return_value=[]) as listing, \
                patch.object(self.app, 'reconvert_games') as reconvert:
            card.go.invoke()
        listing.assert_called_once()
        reconvert.assert_not_called()
        self.assertTrue(card.win.winfo_exists())
        self.assertFalse(card.destroyed)
        self.assertIsNone(card.choice)
        card.pick(None)                                           # the card still answers: Cancel
        self.assertTrue(card.destroyed)

    def test_a_list_with_nothing_ticked_does_not_close_the_card(self):
        card = ClosingCard(self.app, GAMES, checklist=lambda games: [])
        self.addCleanup(card.pick, None)
        card.go.invoke()
        self.assertFalse(card.destroyed)


class SendGreyedOut(CardWindow):
    def test_send_is_greyed_while_sending_is_not_available_and_the_texts_say_so(self):
        card = self.card(sending=False)
        tr = self.app.tr
        self.assertTrue(card.send.instate(['disabled']))
        card.send.invoke()
        self.assertFalse(card.destroyed)
        texts = [w.cget('text') for w in all_widgets(card.win) if w.winfo_class() == 'Label']
        self.assertIn(tr('closing_body_soon', games=4), texts)
        self.assertIn(tr('closing_recompile_note_soon'), texts)
        self.assertIn(tr('tip_closing_send'), texts)
        self.assertNotIn(tr('closing_card_send'), texts)
        self.assertEqual(card.focus_order(), ['Recompile 4 games, then close', 'Close without sending', 'Cancel'])

    def test_send_is_available_when_sending_is(self):
        card = self.card(sending=True)
        self.assertFalse(card.send.instate(['disabled']))
        self.assertIn(self.app.tr('closing_body', games=4), [w.cget('text') for w in all_widgets(card.win)
                                                             if w.winfo_class() == 'Label'])

    def test_the_converter_applies_its_own_rule(self):
        def act(window):
            send = next(w for w in all_widgets(window) if w.winfo_class() == 'TButton' and w.cget('text') == 'Send and close')
            self.assertTrue(send.instate(['disabled']))
            pressed(window, 'Cancel')
        self.assertIsNone(self.shown(act, sending=False))


class Keys(CardWindow):
    def test_return_presses_the_focused_button(self):
        for name, expected in (('skip', 'skip'), ('send', 'send'), ('cancel', None)):
            with self.subTest(button=name):
                card = ClosingCard(self.app, GAMES, checklist=lambda games: list(games))
                self.addCleanup(card.pick, None)
                with patch.object(card.win, 'focus_get', return_value=getattr(card, name)):
                    card.on_return()
                self.assertEqual((card.destroyed, card.choice), (True, expected))

    def test_return_elsewhere_or_on_a_greyed_button_runs_the_recommended_choice(self):
        for focused in (None, 'send'):
            with self.subTest(focused=focused):
                card = ClosingCard(self.app, GAMES, sending=False, checklist=lambda games: list(games))
                self.addCleanup(card.pick, None)
                with patch.object(card.win, 'focus_get', return_value=getattr(card, focused) if focused else None):
                    card.on_return()
                self.assertEqual(card.choice, 'recompile')

    def test_the_keys_are_bound_on_the_window(self):
        card = self.card()
        for key in ('<Return>', '<KP_Enter>', '<Escape>'):
            self.assertTrue(card.win.bind(key), key)

    def test_escape_and_the_window_close_cancel(self):
        for how in ('escape', 'close'):
            with self.subTest(how=how):
                card = ClosingCard(self.app, GAMES)
                self.root.update()
                if how == 'escape':
                    card.on_escape()                      # what the window's Escape binding runs
                else:
                    self.root.tk.call(card.win.protocol('WM_DELETE_WINDOW'))
                self.root.update()
                self.assertEqual((card.destroyed, card.choice), (True, None))


class Animation(CardWindow):
    def test_the_route_lasts_about_two_seconds_then_the_counter_shows_every_discovery(self):
        card = self.card()
        self.assertEqual(card.art.itemcget(card.number, 'text'), '0')
        clock = iter(i * 0.4 for i in range(1000))            # 0.4 s per reading: the card ends after five steps
        seen = []
        with patch.object(view, 'time', Mock(monotonic=lambda: next(clock))):
            card.play()
            for _ in range(300):
                self.root.update()
                seen.append(int(card.art.itemcget(card.number, 'text')))
                if card.done:
                    break
                self.root.after(5)
        self.assertTrue(card.done)
        self.assertEqual(seen, sorted(seen))                    # the counter only goes up
        self.assertEqual(card.art.itemcget(card.number, 'text'), str(sum(g.hints for g in GAMES)))
        self.assertIsNone(card.job)                             # still afterwards: no step pending
        self.assertEqual(view.DURATION, 2.0)

    def test_closing_mid_animation_cancels_the_pending_step(self):
        card = ClosingCard(self.app, GAMES)
        card.play()
        job = card.job
        self.assertIsNotNone(job)
        self.assertIn(job, self.root.tk.call('after', 'info'))
        card.pick(None)
        self.assertIsNone(card.job)
        self.assertNotIn(job, self.root.tk.call('after', 'info'))
        with patch.object(card, 'frame') as frame:
            card.tick()                                          # a late step does nothing
        frame.assert_not_called()

    def test_the_window_closed_from_outside_stops_the_animation_too(self):
        card = ClosingCard(self.app, GAMES)
        card.play()
        job = card.job
        card.win.destroy()
        self.assertTrue(card.destroyed)
        self.assertNotIn(job, self.root.tk.call('after', 'info'))

    def test_one_pulse_per_game_the_fifth_carrying_the_rest(self):
        games = [game(f'Game {i}', 'nes', i, hints=i + 1) for i in range(7)]
        plan = view.flights(games)
        self.assertEqual(len(plan), 5)
        self.assertEqual(sum(h for _d, _l, h in plan), sum(g.hints for g in games))
        self.assertEqual(view.counter_value(plan, 0.0, 28), 0)
        self.assertEqual(view.counter_value(plan, view.DURATION, 28), 28)
        departures = [d for d, _l, _h in plan]
        self.assertEqual(departures, sorted(departures))
        self.assertLessEqual(max(land for _d, land, _h in plan) + view.COUNT_ROLL, view.DURATION + 1e-9)

    def test_a_card_without_games_still_builds_and_shows_zero(self):
        card = self.card([])
        card.frame(view.DURATION)
        self.assertEqual(card.art.itemcget(card.number, 'text'), '0')


class RoundedFocus(CardWindow):
    def test_a_ring_replaces_the_dotted_focus_line_in_the_pill_button_layout(self):
        styles = view.styles_for(self.app)
        layout = str(styles.look.style.layout('CcGoldCard.TButton'))
        self.assertNotIn('Button.focus', layout)
        plain = styles.look.pill_button('CcPlainTest', '#d4a737', '#efc64f', '#191919', '#232323')
        self.assertIn('Button.focus', str(styles.look.style.layout(plain)))


if __name__ == '__main__':
    unittest.main()
