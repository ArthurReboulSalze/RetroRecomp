"""A busy window stops its queue and closes after the active work finishes."""
from queue import Queue
from threading import Event
import unittest
from unittest.mock import Mock, patch

from retrorecomp.gui import Application
from tools.gui_patching import patch_gui


class ShutdownTests(unittest.TestCase):
    def application(self):
        application = Application.__new__(Application)
        application.updating = False
        application.busy = True
        application.close_when_idle = False
        application.recovered_batch = None
        application.cancel = Event()
        application.app = Mock()
        application.stop_button = Mock()
        application.set_status = Mock()
        application.set_controls = Mock()
        application.preferences = Mock(return_value={})
        application.messages = Queue()
        application.running_jobs = {0}
        application.active_rows = ['row']
        application.row_status = {'row': 'converting'}
        application.table = Mock()
        application.language = 'en'
        # The closing card has its own tests (tools/gui_smoke.py).
        application.closing_checked = application.closing_after_recompile = False
        application.offer_closing_card = Mock(return_value=False)
        # Closing at the end of a batch leaves its send for the next start (here: the option off).
        application.send_after_batch = Mock(get=Mock(return_value=False))
        return application

    def test_recompile_chosen_on_the_closing_card_is_not_interrupted(self):
        application = self.application()
        application.closing_after_recompile = True
        application.close()
        self.assertTrue(application.close_when_idle)
        self.assertFalse(application.cancel.is_set())
        application.app.destroy.assert_not_called()

    def test_close_stops_queue_and_exits_after_success_or_failure(self):
        for event in (('done', {}), ('fatal', 'Authored failure')):
            with self.subTest(event=event[0]):
                application = self.application()
                with patch('tkinter.messagebox.showinfo') as info, \
                        patch.object(Application, 'stop_dialog', return_value='now') as ask, \
                        patch('retrorecomp.core.stop_processes') as kill, \
                        patch_gui('save_preferences') as save:
                    application.close()
                    # Closing a busy window offers the same two ways to stop;
                    # "stop now" kills the running conversions.
                    ask.assert_called_once()
                    kill.assert_called_once()
                    application.set_status.assert_called_with('stopping')
                    self.assertTrue(application.cancel.is_set())
                    self.assertTrue(application.close_when_idle)
                    application.app.destroy.assert_not_called()
                    info.assert_not_called()
                    application.messages.put(event)
                    application.drain()
                    application.app.destroy.assert_called_once()
                    self.assertFalse(application.running_jobs)
                    save.assert_called_once_with({})
                    application.app.after.assert_not_called()

    def test_waiting_for_the_running_games_does_not_kill_them(self):
        application = self.application()
        with patch.object(Application, 'stop_dialog', return_value='wait') as ask,                 patch('retrorecomp.core.stop_processes') as kill:
            self.assertTrue(application.stop())
        ask.assert_called_once()
        kill.assert_not_called()
        # No new game starts; the running ones finish.
        self.assertTrue(application.cancel.is_set())
        application.set_status.assert_called_with('stopping_wait')
        application.stop_button.configure.assert_called_with(state='disabled')

    def test_closing_the_stop_dialog_changes_nothing(self):
        application = self.application()
        with patch.object(Application, 'stop_dialog', return_value=None),                 patch('retrorecomp.core.stop_processes') as kill:
            self.assertFalse(application.stop())
        kill.assert_not_called()
        self.assertFalse(application.cancel.is_set())
        application.set_status.assert_not_called()

    def test_closing_the_window_after_choosing_to_wait_just_waits(self):
        application = self.application()
        with patch.object(Application, 'stop_dialog', return_value='wait'),                 patch('retrorecomp.core.stop_processes') as kill,                 patch_gui('save_preferences'):
            application.close()
            # A second close asks nothing more: the games are already finishing.
            with patch.object(Application, 'stop_dialog') as again:
                application.close()
                again.assert_not_called()
        kill.assert_not_called()
        self.assertTrue(application.close_when_idle)
        application.app.destroy.assert_not_called()
        application.messages.put(('done', {}))
        application.drain()
        application.app.destroy.assert_called_once()

    def test_close_of_idle_application_remains_immediate(self):
        application = self.application()
        application.busy = False
        with patch_gui('save_preferences'):
            application.close()
        application.app.destroy.assert_called_once()

    def test_close_releases_reserved_recovery_queue(self):
        application=self.application();application.busy=False
        application.recovered_batch=Mock()
        with patch_gui('save_preferences'):
            application.close()
        application.recovered_batch.close.assert_called_once()
        application.app.destroy.assert_called_once()


if __name__ == '__main__':
    unittest.main()
