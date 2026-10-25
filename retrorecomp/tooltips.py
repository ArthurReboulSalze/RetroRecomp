"""Non-blocking, bounded Tk hover hints; text is resolved when shown."""
import tkinter as tk
from tkinter import ttk
from .branding import COLORS


class Tooltip:
    def __init__(self, widget, text, item=None):
        """A hint for a widget, or for one canvas item or tag (`item`): then
        only that item shows it, below its own box."""
        self.widget, self.text, self.item = widget, text, item
        self.timer = self.window = None
        widget.winfo_toplevel().bind('<FocusOut>', self.hide, add='+')
        widget.winfo_toplevel().bind('<Unmap>', self.hide, add='+')
        bind = widget.bind if item is None else (lambda event, call, add: widget.tag_bind(item, event, call, add))
        bind('<Enter>', self.schedule, add='+')
        for event in ('<Leave>', '<ButtonPress>', '<Destroy>', '<Escape>'):
            if item is None or event in ('<Leave>', '<ButtonPress>'):
                bind(event, self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.timer = self.widget.after(450, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped() or not self.text():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(self.widget.winfo_toplevel())
        self.window.attributes('-topmost', True)
        self.window.configure(bg=COLORS['gold'], padx=1, pady=1)
        tk.Label(self.window, text=self.text(), bg=COLORS['field'], fg=COLORS['text'],
                 font=ttk.Style(self.widget).lookup('TLabel', 'font'),
                 padx=14, pady=10, justify='left', wraplength=420).pack()
        self.window.update_idletasks()
        if self.window is None:
            return  # Focus/Unmap can dismiss it while idle geometry is processed.
        left, top, height = self.widget.winfo_rootx(), self.widget.winfo_rooty(), self.widget.winfo_height()
        if self.item is not None:
            box = self.widget.bbox(self.item)
            if box:
                left, top, height = left + box[0], top + box[1], box[3] - box[1]
        x = min(left + 12, self.window.winfo_screenwidth() - self.window.winfo_reqwidth() - 8)
        y = top + height + 6
        if y + self.window.winfo_reqheight() > self.window.winfo_screenheight() - 8:
            y = top - self.window.winfo_reqheight() - 6
        self.window.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.window.deiconify()

    def hide(self, event=None):
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
