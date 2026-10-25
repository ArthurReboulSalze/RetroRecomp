"""The converter's player corner and problem reports: big scores, the portrait
link, and the report flow (sign-in first, then what the player confirms)."""
from collections import deque
from pathlib import Path
from queue import Queue
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from retrorecomp import online
from retrorecomp.batch import BatchItem
from retrorecomp.gui import Application, compact_number

SHA = 'ab' * 32


class CompactNumbers(unittest.TestCase):
    def test_below_one_hundred_thousand_the_digits_are_grouped_in_the_languages_way(self):
        self.assertEqual([compact_number(value, 'en') for value in (0, 999, 1234, 99999)],
                         ['0', '999', '1,234', '99,999'])
        self.assertEqual(compact_number(99999, 'fr'), '99\u00a0999')
        self.assertEqual(compact_number(12345, 'de'), '12.345')
        self.assertEqual(compact_number(12345, 'ja'), '12,345')

    def test_thousands_and_millions_have_one_decimal_cut_not_rounded(self):
        self.assertEqual(compact_number(110912, 'en'), '110.9K')
        self.assertEqual(compact_number(110912, 'fr'), '110,9K')
        self.assertEqual(compact_number(100000, 'en'), '100K')
        self.assertEqual(compact_number(999999, 'en'), '999.9K', 'never shown as 1000K')
        self.assertEqual(compact_number(1234567, 'en'), '1.2M')
        self.assertEqual(compact_number(1234567, 'fr'), '1,2M')
        self.assertEqual(compact_number(1000000, 'fr'), '1M')
        self.assertEqual(compact_number(12345678, 'en'), '12.3M')

    def test_odd_values_do_not_break_the_header(self):
        self.assertEqual(compact_number(None), 'None')
        self.assertEqual(compact_number('12', 'en'), '12')
        self.assertEqual(compact_number(-5, 'en'), '-5')
        self.assertEqual(compact_number(1500.9, 'en'), '1,500')
        self.assertEqual(compact_number(5, 'xx'), '5')


def application(**attributes):
    app = Application.__new__(Application)
    app.language = 'en'
    app.app = Mock()
    app.busy = app.updating = app.reporting = False
    app.messages = Queue()
    app.session_log = deque(maxlen=100)
    app.output = Mock(get=Mock(return_value=str(Path('X:/Games'))))
    app.rom_paths = {}
    app.items, app.results, app.row_status = {}, {}, {}
    app.sending_started = Mock()
    app.sending_finished = Mock()
    app.refresh_player = Mock()
    for name, value in attributes.items():
        setattr(app, name, value)
    return app


class Portrait(unittest.TestCase):
    def test_signed_in_the_portrait_opens_the_account_page_of_the_site(self):
        app = application(sign_in_dialog=Mock())
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), \
                patch('retrorecomp.online.account', return_value={'token': 'rr1_x'}), \
                patch('retrorecomp.online.service_url', return_value='https://retro-recomp.com'), \
                patch('retrorecomp.gui.webbrowser.open_new_tab') as opened:
            app.portrait_clicked()
        opened.assert_called_once_with('https://retro-recomp.com/account')
        app.sign_in_dialog.assert_not_called()

    def test_signed_out_it_offers_the_sign_in_and_opens_nothing(self):
        app = application(sign_in_dialog=Mock())
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), patch('retrorecomp.online.account', return_value=None), \
                patch('retrorecomp.gui.webbrowser.open_new_tab') as opened:
            app.portrait_clicked()
            app.busy = True   # not in the middle of a batch
            app.portrait_clicked()
        opened.assert_not_called()
        app.sign_in_dialog.assert_called_once()

    def test_without_the_service_the_portrait_does_nothing(self):
        app = application(sign_in_dialog=Mock())
        with patch('retrorecomp.gui.SENDING_AVAILABLE', False), patch('retrorecomp.gui.webbrowser.open_new_tab') as opened:
            app.portrait_clicked()
        opened.assert_not_called()
        app.sign_in_dialog.assert_not_called()


class ReportFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def failed_row(self):
        rom = self.folder / 'ROMS' / 'Mario (USA).sfc'
        item = BatchItem(rom, 'Mario', 'snes', SHA, 524288)
        reports = self.folder / 'Games' / 'Super Nintendo' / 'datas' / 'reports' / item.key
        reports.mkdir(parents=True)
        (reports / 'conversion-report.json').write_text(json.dumps(
            {'version': '1.5.1', 'status': 'experimental', 'build_executable': 'C:\\private\\g.exe'}), encoding='utf-8')
        app = application(output=Mock(get=Mock(return_value=str(self.folder / 'Games'))))
        app.items['row'], app.row_status['row'] = item, 'error'
        app.results['row'] = {'status': 'error', 'message': 'Compilation failed: undefined symbol'}
        app.session_log.extend(['[1/2 - Mario] scanning', '[2/2 - Zelda] scanning', 'Mario : Compilation failed'])
        return app

    def test_a_failed_row_carries_its_game_error_log_and_report_fields(self):
        app = self.failed_row()
        context = app.queue_report_context('row')
        self.assertEqual(context['game'], {'system': 'snes', 'identity': SHA, 'title': 'Mario'})
        self.assertEqual(context['error'], 'Compilation failed: undefined symbol')
        self.assertEqual(context['log'], '[1/2 - Mario] scanning\nMario : Compilation failed',
                         'only the lines that name the game')
        self.assertEqual(context['report']['status'], 'experimental')
        self.assertIn(('<games>', str(self.folder / 'Games' / 'Super Nintendo')), context['roots'])
        self.assertIn(('<rom>', str(self.folder / 'ROMS')), context['roots'])
        body = online.build_report('conversion', **context)
        self.assertNotIn('build_executable', body['report'])

    def test_a_game_without_lines_of_its_own_gets_the_end_of_the_log(self):
        app = application()
        app.session_log.extend(f'line {number}' for number in range(150))
        self.assertTrue(app.session_log_for('Nobody').endswith('line 149'))
        self.assertEqual(len(app.session_log_for('Nobody').splitlines()), 100)

    def test_signing_in_comes_first_and_cancelling_it_sends_nothing(self):
        app = application(sign_in_dialog=Mock(return_value=False), report_dialog=Mock())
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), patch('retrorecomp.online.account', return_value=None), \
                patch('retrorecomp.online.send_report') as send:
            app.report_problem('manual')
        app.sign_in_dialog.assert_called_once()
        app.report_dialog.assert_not_called()
        send.assert_not_called()

    def test_cancelling_the_dialog_sends_nothing(self):
        app = application(report_dialog=Mock(return_value=None))
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), \
                patch('retrorecomp.online.account', return_value={'token': 'rr1_x'}), \
                patch('retrorecomp.online.send_report') as send:
            app.report_problem('manual')
        send.assert_not_called()
        app.sending_started.assert_not_called()
        self.assertFalse(app.reporting)

    def test_confirming_sends_in_a_worker_with_the_sending_indicator(self):
        app = self.failed_row()
        app.report_dialog = Mock(return_value='It fails at once')
        context = app.queue_report_context('row')
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True), \
                patch('retrorecomp.online.account', return_value={'token': 'rr1_x'}), \
                patch('retrorecomp.online.send_report', return_value=7) as send:
            app.report_problem('conversion', context)
            event = app.messages.get(timeout=5)
        app.sending_started.assert_called_once_with('sending_report')
        self.assertTrue(app.reporting)
        self.assertEqual(event, ('report_sent', 7, None))
        kwargs = send.call_args.kwargs
        self.assertEqual((send.call_args.args, kwargs['message'], kwargs['language']),
                         (('conversion',), 'It fails at once', 'en'))
        self.assertEqual(kwargs['game']['identity'], SHA)
        self.assertEqual(kwargs['error'], 'Compilation failed: undefined symbol')

    def test_the_answer_ends_the_indicator_and_tells_the_player(self):
        app = application()
        app.reporting = True
        with patch('retrorecomp.gui.messagebox.showinfo') as info, patch('retrorecomp.gui.messagebox.showerror') as error:
            app.report_sent(7, None)
            info.assert_called_once()
            self.assertIn('7', info.call_args.args[1])
            error.assert_not_called()
            self.assertFalse(app.reporting)
            app.sending_finished.assert_called_once()
            app.report_sent(None, online.ServiceError(429, 'rate_limited'))
            error.assert_called_once()
            app.report_sent(None, online.ServiceError(401, 'unauthorized'))
        app.refresh_player.assert_called_once()

    def test_one_report_at_a_time_and_none_without_the_service(self):
        app = application()
        with patch('retrorecomp.gui.SENDING_AVAILABLE', True):
            self.assertTrue(app.report_available())
            app.reporting = True
            self.assertFalse(app.report_available())
        with patch('retrorecomp.gui.SENDING_AVAILABLE', False):
            app.reporting = False
            self.assertFalse(app.report_available())

    def test_the_services_new_refusals_have_their_own_sentences(self):
        app = application()
        for reason, key in (('too_large', 'online_report_too_large'), ('invalid_report', 'online_report_invalid'),
                            ('unauthorized', 'online_signed_out')):
            self.assertEqual(app.online_message(online.ServiceError(400, reason)), app.tr(key))


if __name__ == '__main__':
    unittest.main()
