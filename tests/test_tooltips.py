"""Hover hints: one dismiss binding per window, whatever the number of hints (the Linux slowness of 1.7.4)."""

import tkinter as tk
import unittest

from retrorecomp.tooltips import Tooltip


def _unmap_handlers(top) -> int:
    script = top.bind('<Unmap>') or ''
    return sum(1 for line in script.splitlines() if line.strip())


class OneBindingPerWindow(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'no display: {error}')
        self.root.withdraw()

    def tearDown(self):
        Tooltip.active.clear()
        self.root.destroy()

    def test_hints_add_no_window_binding_after_the_first(self):
        # 1.7.4 bound <Unmap> and <FocusOut> on the window once per hint and never removed them: the options panel
        # added 105 handlers at each opening, and each unmapped widget ran all of them (several seconds on Linux).
        first = tk.Label(self.root, text='first')
        Tooltip(first, lambda: 'hint')
        once = _unmap_handlers(self.root)
        for opening in range(3):
            frame = tk.Frame(self.root)
            for index in range(50):
                Tooltip(tk.Label(frame, text=str(index)), lambda: 'hint')
            frame.destroy()
        self.assertEqual(_unmap_handlers(self.root), once)
        self.assertEqual(once, 1)

    def test_an_unmap_hides_only_the_waiting_and_shown_hints(self):
        labels = [tk.Label(self.root, text=str(index)) for index in range(3)]
        tips = [Tooltip(label, lambda: 'hint') for label in labels]
        tips[1].schedule()
        self.assertEqual(Tooltip.active, {tips[1]})
        self.assertIsNotNone(tips[1].timer)
        Tooltip.dismiss_all()
        self.assertEqual(Tooltip.active, set())
        self.assertIsNone(tips[1].timer)

    def test_a_hidden_hint_leaves_the_active_set(self):
        tip = Tooltip(tk.Label(self.root, text='x'), lambda: 'hint')
        tip.schedule()
        tip.hide()
        self.assertNotIn(tip, Tooltip.active)


if __name__ == '__main__':
    unittest.main()
