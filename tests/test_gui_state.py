"""The window's state between its tasks: "Go further" and the new-paths
recompile keep their settings to themselves, a send made by hand replaces the
waiting one (closing never sends twice), the account readings follow one
another, the sign-in sends a pseudonym only once edited, and every text button
has its hint in every language. No window is created: the Tk parts are mocks."""
from pathlib import Path
from queue import Queue
import ast
import threading
import time
import unittest
from unittest.mock import Mock, patch

from retrorecomp import gui, online
from retrorecomp.batch import BatchItem
from retrorecomp.compiled_games import Game
from retrorecomp.compiled_games_view import EXTENDED_COINS, THOROUGH_COINS, CompiledGamesView, depth_coins
from retrorecomp.gui import Application, typed_pseudonym
from retrorecomp.i18n import STRINGS, tr
from retrorecomp.languages import LANGUAGES

SHA = 'cd' * 32
SIGNED = {'email': 'p@example.test', 'service': 'https://example.test', 'token': 'rr1_' + 'a' * 43}


def application(**attributes):
    """An Application with the state __init__ declares, without its window."""
    app = Application.__new__(Application)
    app.app = Mock()
    app.app.after.return_value = 'later'
    app.language = 'en'
    app.busy = app.updating = app.converting = False
    app.closing_checked = app.closing_after_recompile = app.closing_send = app.close_when_idle = False
    app.cancel = threading.Event()
    app.messages = Queue()
    app.compiled_view = None
    app.recovered_batch = None
    app.set_controls = Mock()
    app.sending_started, app.sending_finished = Mock(), Mock()
    app.send_after_batch = Mock(get=Mock(return_value=True))
    app.auto_sending = False
    app.last_sent_at = app.deferred_send = app.closing_send_deadline = None
    app.discoveries_waiting = False
    app.manual_sending = False
    app.player = {}
    app.player_checked, app.player_refreshing, app.player_generation = None, False, 0
    app.player_refresh_queued, app.report_queued, app.site_opened = False, None, -1.0
    for name, value in attributes.items():
        setattr(app, name, value)
    return app


class Threads:
    """threading.Thread stand-in: the targets are kept, run when the test says."""

    def __init__(self):
        self.started = []

    def __call__(self, target=None, daemon=None, name=None, args=()):
        thread = Mock()
        thread.start = lambda: self.started.append(target)
        return thread


def logs(app):
    found = []
    while not app.messages.empty():
        event = app.messages.get_nowait()
        if event[0] == 'log':
            found.append(event[1])
    return found


class X68000Summary(unittest.TestCase):
    """The X68000 summary counts interpreted 68000 opcodes, like the other
    opcode consoles, instead of falling back to the cycle sentence."""

    def result_summary(self, result):
        app = application()
        app.table = Mock()
        app.table.selection.return_value = ('row',)
        app.items = {'row': BatchItem(Path('X:/Absent.dim'), 'X68000 game', system='x68')}
        app.results = {'row': result}
        app.selected_button = app.play_button = Mock()
        app.video_field = Mock()
        app.video_name = Mock()
        app.detail = Mock()
        app.selection_changed()
        return app.detail.set.call_args.args[0]

    def test_an_x68_result_shows_the_opcode_sentence(self):
        text = self.result_summary({'status': 'success', 'main_interpreted_opcodes': 1234,
                                    'audio_interpreted_opcodes': 0})
        self.assertIn('Main CPU: 1234 fallback instructions', text)
        self.assertNotIn('interpreter cycles', text)


class ReconversionSettings(unittest.TestCase):
    """Point 1 and 9: the level of "Go further" and the skipped missing ROMs of
    the new-paths recompile belong to one reconversion only."""

    def game(self):
        return Game(str(Path('X:/Games/Mario.exe')), 'gb', SHA, 'Mario')

    def test_a_go_further_that_stops_early_leaves_nothing_for_the_next_reconversion(self):
        game = self.game()
        app = application(begin_reconvert=Mock(), compiled_view=Mock())
        for stop in ('busy', 'tools', 'platform'):
            app.busy = stop == 'busy'
            app.ensure_build_tools = Mock(return_value=stop != 'tools')
            game.target = 'elsewhere' if stop == 'platform' else ''
            with patch('retrorecomp.gui.messagebox.showinfo'):
                app.go_deeper([game], 'thorough')
        app.busy = False
        # The next ordinary reconversion, once its ROM is found: no level.
        app.finish_source_lookup([(game, Path('X:/ROMs/Mario.gb'))])
        self.assertEqual(app.begin_reconvert.call_args.args, ([(game, Path('X:/ROMs/Mario.gb'))], None))
        self.assertFalse(hasattr(app, 'reconvert_level'))

    def test_a_closed_rom_picker_or_a_cancel_drops_the_level(self):
        game = self.game()
        app = application(begin_reconvert=Mock(), compiled_view=Mock())
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=''):
            app.finish_source_lookup([(game, None)], 'thorough')
        app.cancel.set()
        app.finish_source_lookup([(game, Path('X:/ROMs/Mario.gb'))], 'extended')
        app.cancel.clear()
        app.begin_reconvert.assert_not_called()
        app.finish_source_lookup([(game, Path('X:/ROMs/Mario.gb'))])
        self.assertIsNone(app.begin_reconvert.call_args.args[1])

    def test_the_level_and_the_skip_travel_with_the_rom_search(self):
        game = self.game()
        app = application(ensure_build_tools=Mock(return_value=True), compiled_inventory=Mock(snapshot=Mock(return_value=[])),
                          items={}, compiled_view=Mock(), preferences=Mock(return_value={}))
        threads = Threads()
        with patch('retrorecomp.gui.threading.Thread', threads), \
                patch('retrorecomp.rom_sources.RomSources') as sources:
            sources.return_value.resolve.return_value = [(game, None)]
            app.go_deeper([game], 'thorough')
            threads.started.pop()()
            self.assertEqual(app.messages.get_nowait(), ('sources_ready', [(game, None)], 'thorough', False))
            app.busy = False
            app.reconvert_games([game], skip_missing=True)
            threads.started.pop()()
            event = app.messages.get_nowait()
        self.assertEqual(event[2:], (None, True))
        # New paths: a missing ROM waits for later, no file dialog; the next lookup asks again.
        app.busy, app.begin_reconvert = False, Mock()
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value='') as asked:
            app.finish_source_lookup(*event[1:])
            asked.assert_not_called()
            app.finish_source_lookup([(game, None)])
            asked.assert_called_once()
        app.begin_reconvert.assert_not_called()


class SendsByHand(unittest.TestCase):
    """Point 3: a send made by hand is the window's send; closing never sends a second time."""

    def setUp(self):
        self.threads = Threads()
        for patcher in (patch('retrorecomp.gui.SENDING_AVAILABLE', True),
                        patch('retrorecomp.online.account', return_value=SIGNED),
                        patch('retrorecomp.gui.threading.Thread', self.threads),
                        patch('retrorecomp.gui.save_preferences')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def waiting_send(self):
        """A batch ended soon after the last send: its send waits for SEND_EVERY."""
        app = application(preferences=Mock(return_value={}), discoveries_collector=Mock(return_value=lambda: {}),
                          refresh_player=Mock())
        app.last_sent_at = time.monotonic() - 60
        app.send_discoveries_soon()
        self.assertEqual(app.deferred_send, 'later')
        self.assertTrue(app.discoveries_waiting)
        return app

    def test_send_and_close_with_a_waiting_send_closes_after_one_send(self):
        app = self.waiting_send()
        pending = dict(games=1, consoles={'gb': 1}, discoveries=4, observations={}, titles={}, payload={})
        summary = {'games': 1, 'bytes': 2048, 'claims': None}
        # The closing card's "Send and close": counted, sent (the real flow up to online.send).
        app.closing_checked = True
        app.knowledge_task = Mock()
        app.closing_send = True
        with patch('retrorecomp.online.pending', return_value=pending), \
                patch('retrorecomp.online.send', return_value=summary) as upload, \
                patch('retrorecomp.online.send_after_batch') as automatic:
            app.knowledge_done(('send_collect', {'games': 1}), None)
            work = app.knowledge_task.call_args.args[0]
            self.assertTrue(app.manual_sending)
            app.knowledge_done(work(), None)
            upload.assert_called_once_with(pending)
            # The window closed without a second send.
            app.app.destroy.assert_called_once()
            app.app.after_cancel.assert_called_once_with('later')
            self.assertEqual(self.threads.started, [], 'no automatic send started at closing')
            automatic.assert_not_called()
        self.assertIsNone(app.deferred_send)
        self.assertFalse(app.discoveries_waiting, 'nothing left for the next start')
        self.assertLess(time.monotonic() - app.last_sent_at, 5, 'the spacing starts again')
        self.assertFalse(app.manual_sending)

    def test_knowledge_send_replaces_the_waiting_send(self):
        app = self.waiting_send()
        with patch('retrorecomp.gui.messagebox.showinfo'):
            app.knowledge_done(('sent', {'games': 2, 'bytes': 100}), None)
        self.assertIsNone(app.deferred_send)
        self.assertFalse(app.discoveries_waiting)
        # Closing later: nothing waits, nothing is sent.
        self.assertFalse(app.send_before_closing())
        self.assertEqual(self.threads.started, [])

    def test_a_failed_send_by_hand_keeps_the_waiting_send(self):
        app = self.waiting_send()
        with patch('retrorecomp.gui.messagebox.showinfo'):
            app.knowledge_done(('sent', {'error': 'offline'}), None)
        self.assertEqual(app.deferred_send, 'later')
        self.assertTrue(app.discoveries_waiting)

    def test_conversions_alone_are_no_achievement(self):
        app = application(knowledge_task=Mock(), achievement=Mock(return_value=True))
        pending = dict(games=2, consoles={'gb': 2}, discoveries=0, observations={}, titles={}, payload={})
        with patch('retrorecomp.online.pending', return_value=pending), \
                patch('retrorecomp.gui.messagebox.askyesno', return_value=True) as asked:
            app.knowledge_done(('send_collect', {'games': 2}), None)
        app.achievement.assert_not_called()
        self.assertIn(app.tr('knowledge_send_found', games=2, consoles=1), asked.call_args.args[1])
        app.knowledge_task.assert_called_once()


class FileExportMessage(unittest.TestCase):
    """The end of a file export says how many CPS-1 games the version 2 file leaves out, in every language."""

    SUMMARY = {'games': 3, 'consoles': {'md': 3}, 'bytes': 2048, 'version': 2,
               'omitted': {'already_known': 0, 'missing_rom': 0, 'unqualified': 0}}

    def shown(self, language, **changes):
        app = application(language=language)
        with patch('retrorecomp.gui.messagebox.showinfo') as shown:
            app.knowledge_done(('export', {**self.SUMMARY, **changes}), None)
        return shown.call_args.args[1]

    def test_the_count_and_the_online_account_are_named_in_each_language(self):
        self.assertEqual(len(LANGUAGES), 8)
        english = tr('knowledge_export_cps1', 'en', count=7)
        for code in LANGUAGES:
            with self.subTest(code):
                plain = self.shown(code, schema3_only_left_out=0)
                told = self.shown(code, schema3_only_left_out=7)
                self.assertTrue(told.startswith(plain))
                note = told[len(plain):].strip()
                self.assertIn('7', note)
                self.assertIn('CPS-1', note)
                self.assertNotIn('{', note)
                self.assertEqual(note == english, code == 'en', 'translated')

    def test_nothing_is_added_when_no_cps1_game_is_left_out(self):
        for text in (self.shown('en'), self.shown('en', schema3_only_left_out=0)):
            self.assertNotIn('CPS-1', text)


class SendsAndTheWindow(unittest.TestCase):
    """Points 6 and 7, and the option turned off."""

    def test_closing_at_the_end_of_a_batch_leaves_the_send_for_the_next_start(self):
        for kind, event in (('done', ('done', {})), ('collection', ('collection_done', {'success': 1, 'failed': 0}))):
            app = application(close=Mock(), close_when_idle=True, running_jobs=set(), busy=True, converting=True)
            app.messages.put(event)
            with patch('retrorecomp.gui.SENDING_AVAILABLE', True), \
                    patch('retrorecomp.online.account', return_value=SIGNED):
                app.drain()
            app.close.assert_called_once()
            self.assertTrue(app.discoveries_waiting, kind)
            self.assertFalse(app.busy or app.converting, kind)
        # Signed out, or with the option off: nothing waits.
        for account, enabled in ((None, True), (SIGNED, False)):
            app = application(close=Mock(), close_when_idle=True, running_jobs=set())
            app.send_after_batch.get.return_value = enabled
            app.messages.put(('done', {}))
            with patch('retrorecomp.gui.SENDING_AVAILABLE', True), patch('retrorecomp.online.account', return_value=account):
                app.drain()
            self.assertFalse(app.discoveries_waiting)

    def test_turning_the_option_off_forgets_the_waiting_send(self):
        app = application(discoveries_waiting=True)
        app.send_option_changed()
        self.assertTrue(app.discoveries_waiting, 'still on')
        app.send_after_batch.get.return_value = False
        app.send_option_changed()
        self.assertFalse(app.discoveries_waiting)


class AccountReadings(unittest.TestCase):
    """Point 5: one reading at a time; a reading started before a send never
    reports what waits after it."""

    def setUp(self):
        self.threads = Threads()
        self.answers = [{'profile': {'conversions': {'queued': 5, 'queued_days': 2}}},
                        {'profile': {'conversions': {'queued': 7, 'queued_days': 3}}}]
        for patcher in (patch('retrorecomp.gui.SENDING_AVAILABLE', True),
                        patch('retrorecomp.online.account', return_value=SIGNED),
                        patch('retrorecomp.online.cached_player', return_value=None),
                        patch('retrorecomp.online.player', side_effect=self.answers),
                        patch('retrorecomp.gui.threading.Thread', self.threads)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def read(self, app):
        """Run the oldest reading's worker, then hand its answer to Tk."""
        self.threads.started.pop(0)()
        events = []
        while not app.messages.empty():
            events.append(app.messages.get_nowait())
        answers = [event for event in events if event[0] == 'player']
        self.assertEqual(len(answers), 1)
        self.assertTrue(app.player_refreshing, 'the worker never ends the reading itself')
        app.player_read(*answers[0][1:])
        return [event[1] for event in events if event[0] == 'log']

    def test_a_reading_running_during_a_send_does_not_take_its_report(self):
        app = application(render_player=Mock())
        app.refresh_player()
        self.assertEqual((len(self.threads.started), app.player_generation, app.player_refreshing), (1, 1, True))
        # A send's claims arrive while that reading runs: the forced one waits.
        app.auto_sending = True
        app.auto_sent({'games': 1, 'claims': {'converted': 1}}, None)
        self.assertEqual(len(self.threads.started), 1, 'never two readings at once')
        self.assertTrue(app.player_refresh_queued)
        app.refresh_player()   # an ordinary one meanwhile adds nothing
        self.assertEqual(len(self.threads.started), 1)
        logs(app)
        self.read(app)
        self.assertNotIn(True, ['wait for their reward' in text for text in logs(app)])
        self.assertEqual(app.report_queued, 2, 'still waiting for a reading started after the send')
        self.assertEqual((len(self.threads.started), app.player_generation, app.player_refreshing), (1, 2, True))
        self.read(app)
        queued = [text for text in logs(app) if 'wait for their reward' in text]
        wait = app.tr('conversions_wait_days', days='3')
        self.assertEqual(queued, [app.tr('conversions_queued', count='7', wait=wait)])
        self.assertFalse(app.player_refreshing)
        self.assertIsNone(app.report_queued)
        self.assertEqual(app.render_player.call_args.args[0], self.answers[1])

    def test_offline_the_corner_stays_and_the_reading_ends(self):
        app = application(render_player=Mock())
        with patch('retrorecomp.online.player', side_effect=online.ServiceConnectionError()), \
                patch('retrorecomp.online.cached_player', return_value={'profile': {'pseudonym': 'Pat'}}):
            app.refresh_player(force=True)
            self.threads.started.pop()()
        self.assertEqual(app.messages.get_nowait(), ('player', None, 1))
        app.player_read(None, 1)
        self.assertFalse(app.player_refreshing)
        app.render_player.assert_called_once_with({'profile': {'pseudonym': 'Pat'}})


class SignInPseudonym(unittest.TestCase):
    """Point 4: the proposal is sent only once the player edited it."""

    def test_an_untouched_proposal_is_not_sent(self):
        proposed = online.suggested_pseudonym()
        self.assertRegex(proposed, r'^RetroPlayer_\d{6}$')
        self.assertIsNone(typed_pseudonym(proposed, proposed))
        self.assertIsNone(typed_pseudonym(f'  {proposed} ', proposed))
        self.assertIsNone(typed_pseudonym('   ', proposed))
        self.assertEqual(typed_pseudonym(' My   Name ', proposed), 'My Name')
        self.assertEqual(typed_pseudonym(proposed + '7', proposed), proposed + '7')


class ButtonHints(unittest.TestCase):
    """Point 10: the hint key is given with each text button, so it follows
    every interface language."""

    BUTTONS = ('tip_add_roms', 'tip_credits', 'tip_check_updates', 'tip_options', 'tip_choose_cover',
               'tip_auto_cover', 'tip_knowledge')

    def test_each_text_button_names_its_hint(self):
        source = Path(gui.__file__).read_text(encoding='utf-8')
        calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'button'
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == 'self']
        tips = []
        for call in calls:
            self.assertGreaterEqual(len(call.args), 4, ast.unparse(call))
            self.assertIsInstance(call.args[3], ast.Constant, ast.unparse(call))
            tips.append(call.args[3].value)
        self.assertEqual(sorted(tips), sorted(self.BUTTONS))

    def test_the_hints_exist_in_the_eight_languages(self):
        self.assertEqual(len(LANGUAGES), 8)
        for key in self.BUTTONS:
            self.assertIn(key, STRINGS)
            english = tr(key, 'en')
            for code in LANGUAGES:
                text = tr(key, code)
                self.assertTrue(text.strip(), (code, key))
                if code != 'en':
                    self.assertNotEqual(text, english, (code, key))

    def test_a_german_window_gets_the_hint(self):
        app = application(language='de', controls=[], toolbar='.toolbar', tooltips=[], decorate_button=Mock())
        with patch('retrorecomp.gui.ttk.Button'), patch('retrorecomp.gui.Tooltip') as hint:
            app.button('.selection', tr('choose_cover', 'de'), app.choose_cover, 'tip_choose_cover')
        self.assertEqual(hint.call_args.args[1](), tr('tip_choose_cover', 'de'))


class DepthCoins(unittest.TestCase):
    """Point 2: the service adds up the levels a game passes."""

    def test_thorough_from_standard_pays_extended_too(self):
        standard, extended = Game('a.exe', 'gb', SHA, 'A', level='standard'), Game('b.exe', 'gb', SHA, 'B', level='extended')
        unknown = Game('c.exe', 'gb', SHA, 'C')
        self.assertEqual(depth_coins(standard, 'extended', {}), EXTENDED_COINS)
        self.assertEqual(depth_coins(standard, 'thorough', {}), EXTENDED_COINS + THOROUGH_COINS)
        self.assertEqual(depth_coins(unknown, 'thorough', {}), EXTENDED_COINS + THOROUGH_COINS)
        self.assertEqual(depth_coins(extended, 'thorough', {}), THOROUGH_COINS)
        # The server's figures, once read, replace the defaults.
        figures = {'extended': 25, 'thorough': 50}
        self.assertEqual(depth_coins(standard, 'thorough', figures), 75)
        self.assertEqual(depth_coins(extended, 'thorough', figures), 50)


class ExploredGames(unittest.TestCase):
    """The explored games are asked again once their half-hour cache is old."""

    def view(self):
        view = CompiledGamesView.__new__(CompiledGamesView)
        view.events = Queue()
        view.explored, view.explored_at, view.explored_asking = None, 0.0, False
        return view

    def test_asked_once_then_again_after_the_cache(self):
        view = self.view()
        threads = Threads()
        with patch('retrorecomp.compiled_games_view.threading.Thread', threads), \
                patch('retrorecomp.online.sending_available', return_value=False):
            view.ask_explored(now=100.0)
            view.ask_explored(now=101.0)
            self.assertEqual(len(threads.started), 1, 'one question at a time')
            threads.started.pop()()
            view.explored, view.explored_at, view.explored_asking = view.events.get_nowait()[1], 100.0, False
            view.ask_explored(now=100.0 + online.SHOP_REFRESH - 1)
            self.assertEqual(threads.started, [])
            view.ask_explored(now=100.0 + online.SHOP_REFRESH)
            self.assertEqual(len(threads.started), 1)


if __name__ == '__main__':
    unittest.main()


class InterfacePreferences(unittest.TestCase):
    """Every saved preference either reaches the converters or is dropped first.

    The Neo Geo converter takes explicit keywords only: 1.5.4 passed the new
    `discoveries_waiting` preference to it and every Neo Geo conversion failed
    with "unexpected keyword argument"."""

    def preference_keys(self):
        source = Path(gui.__file__).read_text(encoding='utf-8')
        method = next(node for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.FunctionDef) and node.name == 'preferences')
        call = next(node for node in ast.walk(method) if isinstance(node, ast.Call)
                    and getattr(node.func, 'id', '') == 'dict')
        return {keyword.arg for keyword in call.keywords}

    def test_the_neo_geo_converter_accepts_every_preference_that_reaches_it(self):
        import inspect
        from retrorecomp.neogeo_conversion import _convert
        accepted = set(inspect.signature(_convert).parameters)
        # Read by the interface before the batch, or consumed and dropped by
        # batch.convert_batch / _convert_one for a Neo Geo item.
        before_batch = set(gui.INTERFACE_PREFERENCES) | {'output', 'use_shared_base'}
        in_batch = {'jobs', 'overwrite', 'force', 'console_scan', 'gb_deep_validation',
                    'x68_ipl', 'x68_cgrom', 'x68_ram'}
        reaching = self.preference_keys() - before_batch - in_batch
        self.assertEqual(reaching - accepted, set())

    def test_interface_preferences_are_real_preference_keys(self):
        self.assertLessEqual(set(gui.INTERFACE_PREFERENCES), self.preference_keys())

    def test_console_jobs_are_saved_checked_and_dropped_before_any_conversion(self):
        self.assertIn('console_jobs', gui.INTERFACE_PREFERENCES)
        self.assertIn('console_jobs', self.preference_keys())
        app = application(scan_jobs={'sms': Mock(get=Mock(return_value=' 8 ')), 'ng': Mock(get=Mock(return_value='2')),
                                     'x68': Mock(get=Mock(return_value='')), 'gb': Mock(get=Mock(return_value='1'))})
        self.assertEqual(app.console_jobs_preferences(), {'sms': 8, 'ng': 2, 'gb': 1})
        for bad in ('0', '9', 'two', '-1', '2.5'):
            app.scan_jobs['ng'] = Mock(get=Mock(return_value=bad))
            with self.assertRaises(ValueError):
                app.console_jobs_preferences()


class MissingRomFolder(unittest.TestCase):
    """A ROM that Reconvert cannot find is looked for in a folder, for every
    missing game of its console at once; the folder is remembered."""

    def setUp(self):
        import hashlib
        import tempfile
        from retrorecomp.platforms import target_id
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.games, self.payloads = [], {}
        for number in (1, 2, 3):
            payload = bytes([number]) * 16384
            self.payloads[number] = payload
            game = Game(str(self.root / f'Game {number}.exe'), 'sms', hashlib.sha256(payload).hexdigest(),
                        f'Game {number}')
            game.target = target_id()
            self.games.append(game)
        self.library = self.root / 'library' / 'deep'
        self.library.mkdir(parents=True)
        # Names that say nothing about the game; the identity decides.
        (self.library / 'a.sms').write_bytes(self.payloads[1])
        (self.library / 'zzz.sms').write_bytes(self.payloads[2])
        self.elsewhere = self.root / 'other'
        self.elsewhere.mkdir()
        (self.elsewhere / 'third.sms').write_bytes(self.payloads[3])
        self.saved = Mock(get=Mock(return_value=''))
        self.app = application(begin_reconvert=Mock(), compiled_view=Mock(), rom_paths={'sms': self.saved},
                               preferences=Mock(return_value={}))
        self.threads = Threads()
        saving = patch('retrorecomp.gui.save_preferences')
        self.save = saving.start()
        self.addCleanup(saving.stop)
        for patcher in (patch('retrorecomp.gui.threading.Thread', self.threads),
                        patch('retrorecomp.rom_sources.data_directory', return_value=self.root / 'datas')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def settle(self):
        """Run the pending search, then deliver its result to the window."""
        self.threads.started.pop()()
        while True:
            event = self.app.messages.get(timeout=10)
            if event[0] == 'rom_folder_searched':
                break
        self.app.finish_folder_search(*event[1:])

    def test_one_folder_finds_every_missing_rom_of_the_console_and_is_remembered(self):
        missing = [(game, None) for game in self.games[:2]]
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(self.root / 'library')) as asked:
            self.app.finish_source_lookup(missing)
            self.settle()
        asked.assert_called_once()
        self.assertIn('Master System', asked.call_args.kwargs['title'])
        self.assertIn('2 to find', asked.call_args.kwargs['title'])
        chosen, level = self.app.begin_reconvert.call_args.args
        self.assertEqual([(game.title, source.name) for game, source in chosen],
                         [('Game 1', 'a.sms'), ('Game 2', 'zzz.sms')])
        self.assertIsNone(level)
        self.saved.set.assert_called_once_with(str(self.root / 'library'))
        self.save.assert_called_once()
        # The ROMs themselves are untouched.
        self.assertEqual((self.library / 'a.sms').read_bytes(), self.payloads[1])

    def test_a_rom_already_found_is_not_asked_for_and_only_the_missing_ones_count(self):
        pairs = [(self.games[0], self.library / 'a.sms'), (self.games[1], None), (self.games[2], None)]
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(self.root / 'library')) as asked, \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=False) as question:
            self.app.finish_source_lookup(pairs)
            self.assertIn('2 to find', asked.call_args.kwargs['title'])
            self.settle()
            # Game 3 is not in that folder, which the question says.
            self.assertIn('1 Master System ROM(s)', question.call_args.args[1])
        chosen, _ = self.app.begin_reconvert.call_args.args
        self.assertEqual([game.title for game, _ in chosen], ['Game 1', 'Game 2'])

    def test_leftovers_get_one_more_question_and_a_second_folder_then_are_skipped(self):
        pairs = [(game, None) for game in self.games]
        dialogs = []
        with patch('retrorecomp.gui.filedialog.askdirectory',
                   side_effect=lambda **kw: dialogs.append(kw['title']) or str(self.library.parent)) as asked, \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=True) as question:
            self.app.finish_source_lookup(pairs)
            self.settle()                       # finds games 1 and 2; game 3 is missing
            question.assert_called_once()
            self.assertIn('Game 3', question.call_args.args[1])
            self.assertEqual(asked.call_count, 2)
            self.assertIn('1 to find', dialogs[1])
            self.settle()                       # the same folder again: game 3 still missing
            # No third question, no third folder: the game is skipped.
            question.assert_called_once()
            self.assertEqual(asked.call_count, 2)
        chosen, _ = self.app.begin_reconvert.call_args.args
        self.assertEqual([game.title for game, _ in chosen], ['Game 1', 'Game 2'])
        self.assertIn(tr('rom_skipped', 'en', title='Game 3'), logs(self.app))

    def test_a_second_folder_can_complete_the_set(self):
        pairs = [(game, None) for game in self.games]
        folders = iter([str(self.library.parent), str(self.elsewhere)])
        with patch('retrorecomp.gui.filedialog.askdirectory', side_effect=lambda **kw: next(folders)), \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=True):
            self.app.finish_source_lookup(pairs)
            self.settle()
            self.settle()
        chosen, _ = self.app.begin_reconvert.call_args.args
        self.assertEqual([game.title for game, _ in chosen], ['Game 1', 'Game 2', 'Game 3'])
        # The folder that found the last ROM is the one kept.
        self.assertEqual(self.saved.set.call_args_list[-1].args, (str(self.elsewhere),))

    def test_declining_the_second_folder_skips_the_leftovers_and_reconverts_the_rest(self):
        pairs = [(game, None) for game in self.games]
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(self.library.parent)) as asked, \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=False):
            self.app.finish_source_lookup(pairs)
            self.settle()
        asked.assert_called_once()
        chosen, _ = self.app.begin_reconvert.call_args.args
        self.assertEqual([game.title for game, _ in chosen], ['Game 1', 'Game 2'])

    def test_cancelling_the_question_or_a_folder_stops_the_reconversion(self):
        pairs = [(game, None) for game in self.games]
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value='') as asked:
            self.app.finish_source_lookup(pairs)
        asked.assert_called_once()
        self.assertEqual(self.threads.started, [])
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(self.library.parent)), \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=None):
            self.app.finish_source_lookup(pairs)
            self.settle()
        self.app.begin_reconvert.assert_not_called()

    def test_a_folder_that_holds_none_is_not_remembered(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(empty)), \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=False):
            self.app.finish_source_lookup([(self.games[0], None)])
            self.settle()
        self.saved.set.assert_not_called()
        self.app.begin_reconvert.assert_not_called()

    def test_each_console_is_asked_for_once_with_its_own_missing_games(self):
        gb = Game(str(self.root / 'Gb.exe'), 'gb', 'ef' * 32, 'Gb game')
        pairs = [(self.games[0], None), (gb, None), (self.games[1], None)]
        searched = []

        def resolve(self_, games, preferences, **options):
            searched.append(sorted(game.title for game in games))
            return [(game, Path('X:/found/' + game.title) if game.system == 'sms' else None) for game in games]
        asked = []
        with patch('retrorecomp.gui.filedialog.askdirectory',
                   side_effect=lambda **kw: asked.append(kw['title']) or str(self.root / 'roms')), \
                patch('retrorecomp.gui.messagebox.askyesnocancel', return_value=False), \
                patch('retrorecomp.rom_sources.RomSources.resolve', resolve):
            self.app.rom_paths['gb'] = Mock(get=Mock(return_value=''))
            self.app.finish_source_lookup(pairs)
            self.settle()
            self.settle()
        self.assertEqual(len(asked), 2)
        self.assertIn('Master System', asked[0])
        self.assertIn('Game Boy', asked[1])
        self.assertEqual(searched, [['Game 1', 'Game 2'], ['Gb game']])
        chosen, _ = self.app.begin_reconvert.call_args.args
        self.assertEqual([game.title for game, _ in chosen], ['Game 1', 'Game 2'])

    def test_new_paths_and_closing_still_skip_a_missing_rom_without_asking(self):
        with patch('retrorecomp.gui.filedialog.askdirectory') as asked:
            self.app.finish_source_lookup([(self.games[0], None)], skip_missing=True)
            self.app.closing_after_recompile = True
            self.app.finish_source_lookup([(self.games[0], None)])
        asked.assert_not_called()
        self.app.begin_reconvert.assert_not_called()

    def test_stop_while_searching_leaves_the_reconversion_alone(self):
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value=str(self.library.parent)):
            self.app.finish_source_lookup([(self.games[0], None)])
            self.app.cancel.set()
            self.settle()
        self.app.begin_reconvert.assert_not_called()
        self.saved.set.assert_not_called()

    def test_the_saved_folder_opens_the_dialog_when_it_exists(self):
        self.saved.get.return_value = str(self.library)
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value='') as asked:
            self.app.finish_source_lookup([(self.games[0], None)])
        self.assertEqual(asked.call_args.kwargs['initialdir'], str(self.library))
        self.saved.get.return_value = str(self.root / 'gone')
        with patch('retrorecomp.gui.filedialog.askdirectory', return_value='') as asked:
            self.app.finish_source_lookup([(self.games[0], None)])
        self.assertNotIn('initialdir', asked.call_args.kwargs)
