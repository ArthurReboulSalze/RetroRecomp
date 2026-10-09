"""Non-blocking, bounded Tk hover hints; text is resolved when shown."""
import tkinter as tk
from .branding import COLORS


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.timer = self.window = None
        widget.winfo_toplevel().bind('<FocusOut>', self.hide, add='+')
        widget.winfo_toplevel().bind('<Unmap>', self.hide, add='+')
        widget.bind('<Enter>', self.schedule, add='+')
        for event in ('<Leave>', '<ButtonPress>', '<Destroy>', '<Escape>'):
            widget.bind(event, self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.timer = self.widget.after(450, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(self.widget.winfo_toplevel())
        self.window.attributes('-topmost', True)
        self.window.configure(bg=COLORS['gold'], padx=1, pady=1)
        tk.Label(self.window, text=self.text(), bg=COLORS['field'], fg=COLORS['text'], font=('Segoe UI', 10),
                 padx=14, pady=10, justify='left', wraplength=420).pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx() + 12, self.window.winfo_screenwidth() - self.window.winfo_reqwidth() - 8)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        if y + self.window.winfo_reqheight() > self.window.winfo_screenheight() - 8:
            y = self.widget.winfo_rooty() - self.window.winfo_reqheight() - 6
        self.window.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.window.deiconify()

    def hide(self, event=None):
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
