"""retrorecomp/tk_later.py: timers and idle calls on the main window, skipped once their widget is gone, and no raw
`.after(` on anything else in the converter (the Stop dialog's « Stop now » pressed by an orphaned idle script, 21 Nov
2026). A withdrawn root; nothing is shown."""
import re
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from retrorecomp import tk_later
from tests.tk_cleanup import release_tk

SOURCE = Path(__file__).resolve().parents[1] / 'retrorecomp'
# Receivers that are the main window itself (it outlives every other widget): the Application's `app`, the `root` the
# window-wide helpers are given (dialogs.watch_windows, tk_threads.keep_draining).
MAIN_WINDOW = {'app', 'self.app', 'root'}
CALL = re.compile(r'([A-Za-z_][\w.\[\]\'"]*)\.(after|after_idle|after_cancel)\(')


class NoRawTimers(unittest.TestCase):
    def test_every_timer_of_a_widget_that_can_be_destroyed_goes_through_tk_later(self):
        found = []
        for path in sorted(SOURCE.rglob('*.py')):
            if path.name == 'tk_later.py':
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                code = line.split('#', 1)[0]
                for receiver, method in CALL.findall(code):
                    if receiver not in MAIN_WINDOW:
                        found.append(f'{path.relative_to(SOURCE.parent)}:{number}: {receiver}.{method}(')
        self.assertEqual(found, [], 'use tk_later.later / tk_later.cancel (or the main window itself):\n' + '\n'.join(found))


class Later(unittest.TestCase):
    def setUp(self):
        release_tk(self)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def settle(self, seconds=0.15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def test_a_job_runs_for_a_live_widget_with_its_arguments(self):
        calls = []
        widget = tk.Toplevel(self.root)
        tk_later.later(widget, 'idle', calls.append, 'idle')
        tk_later.later(widget, 10, calls.append, 'timer')
        self.settle()
        self.assertEqual(calls, ['idle', 'timer'])

    def test_a_job_of_a_destroyed_widget_does_nothing_and_leaves_no_orphan(self):
        calls, errors = [], []
        self.root.report_callback_exception = lambda *info: errors.append(info)
        widget = tk.Toplevel(self.root)
        tk_later.later(widget, 'idle', calls.append, 'idle')
        tk_later.later(widget, 10, calls.append, 'timer')
        widget.destroy()
        self.settle()
        self.assertEqual((calls, errors), ([], []))
        self.assertEqual(self.root.tk.splitlist(self.root.tk.call('after', 'info')), ())     # all came due and went

    def test_the_command_belongs_to_the_main_window(self):
        widget = tk.Toplevel(self.root)
        job = tk_later.later(widget, 1000, lambda: None)
        script = self.root.tk.splitlist(self.root.tk.call('after', 'info', job))[0]
        self.assertIn(script, self.root._tclCommands)
        self.assertNotIn(script, widget._tclCommands or [])
        widget.destroy()                                                   # the command survives its widget
        self.assertIn(script, self.root.tk.splitlist(self.root.tk.call('info', 'commands', script)))
        tk_later.cancel(widget, job)
        self.assertEqual(self.root.tk.splitlist(self.root.tk.call('after', 'info')), ())

    def test_cancel_stops_a_job_and_ignores_none_and_finished_ones(self):
        calls = []
        widget = tk.Toplevel(self.root)
        job = tk_later.later(widget, 20, calls.append, 'late')
        tk_later.cancel(widget, job)
        tk_later.cancel(widget, None)
        done = tk_later.later(widget, 'idle', calls.append, 'done')
        self.settle()
        tk_later.cancel(widget, done)                                      # already ran: nothing to cancel
        self.assertEqual(calls, ['done'])

    def test_a_closed_dialog_s_job_presses_no_button_of_the_next_dialog(self):
        """The bug of 21 Nov 2026: the first dialog's pending script, orphaned by its destroy, ran the next dialog's button
        command that had taken its freed name. Through tk_later, the script is the main window's and checks its widget."""
        pressed, ran = [], []
        for _ in range(30):
            first = tk.Toplevel(self.root)
            tk_later.later(first, 'idle', lambda: ran.append(1))
            first.destroy()
            second = tk.Toplevel(self.root)
            for value in ('now', 'wait'):
                ttk.Button(second, command=lambda value=value: pressed.append(value)).pack()
            self.root.update_idletasks()
            second.destroy()
        self.assertEqual((pressed, ran), ([], []))


if __name__ == '__main__':
    unittest.main()
