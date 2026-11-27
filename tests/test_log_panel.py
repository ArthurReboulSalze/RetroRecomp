"""The log panel during a batch (gui_conversion.drain and write_log, 27 November 2026): the lines one turn reads are written
at once, the panel keeps the last LOG_KEEP lines while the session keeps them all, and a turn hands the window back after
DRAIN_BUDGET seconds. Before, every line was its own insert and scroll, and 3,000 lines held the window over a second."""
import collections
import queue
import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

from retrorecomp import gui_conversion
from retrorecomp.gui_conversion import ConversionMixin
from tests.tk_cleanup import release_tk


class Panel(ConversionMixin):
    def __init__(self, root):
        self.app = MagicMock()
        self.messages = queue.Queue()
        self.log = tk.Text(root)
        self.log.configure(state='disabled')
        self.session_log = collections.deque(maxlen=20000)
        self.compiled_view = None
        self.results = {}
        self.ended = 0

    def end_welcome(self):
        self.ended += 1


class LogPanel(unittest.TestCase):
    def setUp(self):
        release_tk(self)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.panel = Panel(self.root)

    def lines(self):
        return self.panel.log.get('1.0', 'end-1c').split('\n')

    def test_one_turn_writes_every_line_at_once(self):
        for number in range(3000):
            self.panel.messages.put(('log', f'line {number}'))
        inserts = []
        original = tk.Text.insert
        with patch.object(tk.Text, 'insert', lambda widget, *a, **k: (inserts.append(a), original(widget, *a, **k))[1]):
            self.panel.drain()
        self.assertTrue(self.panel.messages.empty())
        self.assertEqual(len(inserts), 1)
        self.assertEqual(self.lines()[:2], ['line 0', 'line 1'])
        self.assertEqual(self.lines()[-2:], ['line 2999', ''])
        self.assertEqual(len(self.panel.session_log), 3000)
        self.assertEqual(str(self.panel.log.cget('state')), 'disabled')
        self.panel.app.after.assert_called_with(100, self.panel.drain)

    def test_the_panel_keeps_the_last_lines_and_the_session_all_of_them(self):
        total = gui_conversion.LOG_KEEP * 2
        for start in range(0, total, 1000):
            self.panel.write_log([f'line {number}' for number in range(start, start + 1000)])
        shown = self.lines()
        self.assertLessEqual(len(shown) - 1, gui_conversion.LOG_KEEP + gui_conversion.LOG_KEEP // 10)
        self.assertGreaterEqual(len(shown) - 1, gui_conversion.LOG_KEEP)
        self.assertEqual(shown[-2], f'line {total - 1}')
        self.assertEqual(len(self.panel.session_log), total)
        self.assertEqual(self.panel.session_log[0], 'line 0')

    def test_a_turn_over_its_budget_hands_the_window_back(self):
        for number in range(10):
            self.panel.messages.put(('log', f'line {number}'))
        with patch.object(gui_conversion, 'DRAIN_BUDGET', -1):
            self.panel.drain()
        self.assertEqual(self.panel.messages.qsize(), 10)              # nothing read this turn
        self.panel.app.after.assert_called_with(1, self.panel.drain)   # the next turn comes at once
        self.panel.drain()
        self.assertTrue(self.panel.messages.empty())

    def test_lines_keep_their_place_around_other_events(self):
        self.panel.messages.put(('log', 'before'))
        self.panel.messages.put(('footer_progress', 'ignored'))
        self.panel.messages.put(('log', 'after'))
        self.panel.drain()
        self.assertEqual(self.lines(), ['before', 'after', ''])
        self.assertEqual(self.panel.ended, 2)                            # once per block of lines


if __name__ == '__main__':
    unittest.main()
