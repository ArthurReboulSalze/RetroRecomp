"""Non-blocking, bounded Tk hover hints; text is resolved when shown."""
import tkinter as tk
from tkinter import ttk
from .branding import COLORS


class Tooltip:
    # The hints waiting to show or showing. A focus-out or an unmap anywhere in a window (the event reaches the
    # toplevel's bindings from every widget below it) dismisses only these: one binding per toplevel instead of
    # two per hint, which made every unmap run every hint's handler (hints x unmapped widgets) and which stayed
    # on the toplevel after the hint's widget was destroyed.
    active = set()

    def __init__(self, widget, text, item=None, place=None):
        """A hint for a widget, or for one canvas item or tag (`item`): then
        only that item shows it, below its own box. `place`, a callable, gives the
        box of the part of the widget it is about ((x, y, width, height) in the
        widget, or None): the hint then shows below that part."""
        self.widget, self.text, self.item, self.place = widget, text, item, place
        self.timer = self.window = None
        self.pinned = False           # opened by a click (toggle): leaving the widget no longer closes it
        top = widget.winfo_toplevel()
        if not getattr(top, '_retro_tooltip_dismiss', False):
            top._retro_tooltip_dismiss = True
            top.bind('<FocusOut>', Tooltip.dismiss_all, add='+')
            top.bind('<Unmap>', Tooltip.dismiss_all, add='+')
            top.bind('<ButtonPress>', Tooltip.click_away, add='+')
        bind = widget.bind if item is None else (lambda event, call, add: widget.tag_bind(item, event, call, add))
        bind('<Enter>', self.schedule, add='+')
        bind('<Leave>', self.leave, add='+')
        for event in ('<ButtonPress>', '<Destroy>', '<Escape>'):
            if item is None or event == '<ButtonPress>':
                bind(event, self.hide, add='+')

    @classmethod
    def dismiss_all(cls, event=None):
        for tip in list(cls.active):
            tip.hide()

    @classmethod
    def close_shown(cls):
        """Closes the hints that show (Esc in a window that has one open): True when there was one, so the key closes
        the hint before the window."""
        shown = [tip for tip in cls.active if tip.window is not None]
        for tip in shown:
            tip.hide()
        return bool(shown)

    @classmethod
    def click_away(cls, event=None):
        """A click anywhere else in the window closes a hint opened by a click (its own widget toggles it)."""
        for tip in list(cls.active):
            if tip.pinned and getattr(event, 'widget', None) is not tip.widget:
                tip.hide()

    def toggle(self, event=None):
        """A click on the widget: the hint opens and stays (until a click on it again, a click elsewhere or Esc), or
        closes when it shows. Bind it to the click of a widget whose hint is worth keeping up (« The rules »)."""
        if self.window is not None:
            self.hide()
        else:
            self.hide()
            self.show()
            self.pinned = self.window is not None
            if self.pinned:
                Tooltip.active.add(self)
        return 'break'

    def leave(self, event=None):
        if not self.pinned:
            self.hide()

    def schedule(self, event=None):
        if self.pinned:
            return                    # back over the widget of an open, clicked hint: it stays as it is
        self.hide()
        self.timer = self.widget.after(450, self.show)
        Tooltip.active.add(self)

    def show(self):
        self.timer = None
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped() or not self.text():
            return
        if self.window is not None:   # never two windows for one hint: the first would stay up for good
            self.window.destroy()
            self.window = None
        self.window = tk.Toplevel(self.widget)
        Tooltip.active.add(self)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(self.widget.winfo_toplevel())
        self.window.attributes('-topmost', True)
        self.window.configure(bg=COLORS['gold'], padx=1, pady=1)
        label = tk.Label(self.window, text=self.text(), bg=COLORS['field'], fg=COLORS['text'],
                         font=ttk.Style(self.widget).lookup('TLabel', 'font'),
                         padx=14, pady=10, justify='left', wraplength=420)
        label.pack()
        label.bind('<ButtonPress>', self.hide)        # a click on the hint itself closes it too
        self.window.update_idletasks()
        if self.window is None:
            return  # Focus/Unmap can dismiss it while idle geometry is processed.
        left, top, height = self.widget.winfo_rootx(), self.widget.winfo_rooty(), self.widget.winfo_height()
        if self.item is not None:
            box = self.widget.bbox(self.item)
            if box:
                left, top, height = left + box[0], top + box[1], box[3] - box[1]
        elif self.place is not None:
            box = self.place()
            if box:
                left, top, height = left + box[0], top + box[1], box[3]
        # Kept inside the work area of the monitor the widget is on (dialogs.work_area): with a second monitor, the
        # primary screen's width pulled every hint back onto the primary monitor, far from its widget.
        from .dialogs import work_area
        try:
            area_left, area_top, area_right, area_bottom = work_area(self.widget)
        except (tk.TclError, TypeError, ValueError):
            area_left, area_top = 0, 0
            area_right, area_bottom = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        width, tall = self.window.winfo_reqwidth(), self.window.winfo_reqheight()
        x = max(area_left, min(left + 12, area_right - width - 8))
        y = top + height + 6
        if y + tall > area_bottom - 8:
            y = top - tall - 6
        y = max(area_top, y)
        self.window.geometry(f'+{x}+{y}')         # '+-1280': a monitor on the left of the primary one
        self.window.deiconify()

    def hide(self, event=None):
        self.pinned = False
        Tooltip.active.discard(self)
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
