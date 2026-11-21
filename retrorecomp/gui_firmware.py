"""Find firmware in a folder: the Options button, its search dialog and its review (the search is firmware_search.py).

The dialog walks the chosen folder in a thread (a progress line and a Cancel button), then lists what it found machine by
machine and option by option, each with a checkbox, before anything changes. Use writes the ticked paths to the firmware
fields of Options, as the Browse buttons do (they are saved with the other options); the player's files are only read."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .branding import COLORS
from .dialogs import center_dialog
from .ui_fonts import scaled
from .gui_options import FIRMWARE_ROWS
from .paths import APP_NAME
from . import tk_later

ROLE_CHARACTERS = 160     # a folder of many images is described by its first ones


def _shorten(text: str, limit: int = ROLE_CHARACTERS) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip('; ') + '…'


class FirmwareSearchMixin:
    """The « Find firmware in a folder… » button of Options (Common page) and its dialog."""

    def build_firmware_search_button(self, parent):
        """The button, made in `parent` and not placed (Options › Common puts it in its BIOS and firmware section)."""
        button = ttk.Button(parent, text=self.tr('firmware_search'), command=self.find_firmware)
        self.option_controls.append((button, 'normal'))
        self.hint(button, 'tip_firmware_search')
        self.firmware_search_button = button
        return button

    def find_firmware(self):
        if self.busy or getattr(self, 'firmware_dialog', None) is not None:
            return
        folder = filedialog.askdirectory(parent=self.options_panel, title=self.tr('firmware_search_choose'))
        if folder:
            self.open_firmware_dialog(Path(folder))

    def open_firmware_dialog(self, folder: Path):
        """The modal dialog: the search runs in a thread, then the review replaces the progress line."""
        from . import firmware_search
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.transient(self.app)
        self.firmware_dialog = window
        body = tk.Frame(window, bg=background, padx=22, pady=18, highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('firmware_search_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).pack(anchor='w')
        progress = tk.StringVar(value=self.tr('firmware_search_progress', files=0))
        tk.Label(body, textvariable=progress, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=640, justify='left').pack(anchor='w', pady=(12, 12))
        cancel = threading.Event()
        state = {'files': 0, 'result': None}

        def close():
            cancel.set()
            self.firmware_dialog = None
            if window.winfo_exists():
                window.destroy()
        stop = ttk.Button(body, text=self.tr('knowledge_cancel'), command=close)
        stop.pack(anchor='e')
        window.protocol('WM_DELETE_WINDOW', close)
        window.bind('<Escape>', lambda event: close())

        def worker():
            def seen(files, _folder):
                state['files'] = files
            try:
                state['result'] = firmware_search.search(folder, cancel=cancel, progress=seen)
            except OSError:
                state['result'] = firmware_search.Search(folder, unreadable=1)

        def poll():
            if not window.winfo_exists():
                return
            if state['result'] is None:
                progress.set(self.tr('firmware_search_progress', files=state['files']))
                tk_later.later(window, 100, poll)
                return
            if cancel.is_set() or state['result'].cancelled:
                close()
                return
            for child in body.winfo_children()[1:]:
                child.destroy()
            current = {name: getattr(self, name).get() for name, _, _ in firmware_search.path_options()}
            lines, missing = firmware_search.review(state['result'], current)
            self.build_firmware_review(body, state['result'], lines, missing, close)
            window.update_idletasks()
            center_dialog(window, self.app, max(window.winfo_reqwidth(), scaled(window, 760)), min(window.winfo_reqheight(), scaled(window, 640)), measured=True)

        threading.Thread(target=worker, daemon=True).start()
        window.update_idletasks()
        center_dialog(window, self.app, scaled(window, 560), window.winfo_reqheight(), measured=True)
        window.deiconify()
        window.grab_set()
        tk_later.later(window, 100, poll)

    def build_firmware_review(self, body, result, lines, missing, close):
        """The review inside `body`: one line per option found, its checkbox, its candidates, then Use and Cancel.
        Returns {option: (BooleanVar, chooser or None)} for the window's own checks."""
        background = COLORS['panel']
        muted = {'bg': background, 'fg': COLORS['muted'], 'font': (self.ui_font, 9), 'justify': 'left'}
        tk.Label(body, text=self.tr('firmware_search_note'), wraplength=700, **muted).pack(anchor='w', pady=(10, 8))
        footer = tk.Frame(body, bg=background)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        holder = tk.Frame(body, bg=background)
        holder.pack(fill='both', expand=True)
        canvas = tk.Canvas(holder, bg=background, highlightthickness=0, borderwidth=0, height=360, width=720)
        bar = ttk.Scrollbar(holder, orient='vertical', command=canvas.yview, style='Slim.Vertical.TScrollbar')
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=background)
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        controls = {}
        for line in lines:
            row = tk.Frame(inner, bg=background)
            row.pack(fill='x', anchor='w', pady=(0, 10))
            ticked = tk.BooleanVar(value=line.ticked)
            title = ' / '.join(line.machines) + ' · ' + self.option_text(line.label)
            ttk.Checkbutton(row, text=title, variable=ticked).pack(anchor='w')
            chooser = None
            texts = [f'{hit.path}  ·  {_shorten(hit.role)}' for hit in line.candidates]
            if len(texts) > 1:
                chooser = ttk.Combobox(row, state='readonly', values=texts, width=96)
                chooser.current(0)
                chooser.pack(anchor='w', padx=(24, 0), pady=(2, 0))
            else:
                tk.Label(row, text=texts[0], wraplength=680, **muted).pack(anchor='w', padx=(24, 0))
            notes = []
            if line.same:
                notes.append(self.tr('firmware_search_same'))
            elif line.current:
                notes.append(self.tr('firmware_search_already', path=line.current))
            if line.ambiguous or line.weak:
                notes.append(self.tr('firmware_search_several', count=len(line.candidates)))
            for note in notes:
                tk.Label(row, text=note, wraplength=680, **muted).pack(anchor='w', padx=(24, 0))
            controls[line.option] = (ticked, chooser)
        if not lines:
            tk.Label(inner, text=self.tr('firmware_search_none'), wraplength=680, **muted).pack(anchor='w')
        summary = [self.tr('firmware_search_summary', files=result.files, links=result.links, large=result.large)]
        if result.limited:
            summary.append(self.tr('firmware_search_limit', files=result.files))
        if missing:
            names = '; '.join(' / '.join(machines) + ' · ' + self.option_text(label) for label, machines in missing)
            summary.append(self.tr('firmware_search_missing', names=names))
        tk.Label(footer, text='\n'.join(summary), wraplength=700, **muted).pack(anchor='w', pady=(0, 10))

        def use():
            self.apply_firmware_choices(lines, controls)
            close()
        buttons = tk.Frame(footer, bg=background)
        buttons.pack(fill='x')
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=close).pack(side='right')
        ttk.Button(buttons, text=self.tr('firmware_search_apply'), style='Primary.TButton', command=use,
                   state='normal' if lines else 'disabled').pack(side='right', padx=(0, 8))
        return controls

    def apply_firmware_choices(self, lines, controls):
        """Write the ticked paths to their Options fields (saved with the options, as Browse does); a firmware the window
        can verify is checked at once. Returns {option: path} written."""
        from .firmware_search import to_apply
        ticked = {option: variable.get() for option, (variable, _) in controls.items()}
        chosen = {option: chooser.current() for option, (_, chooser) in controls.items() if chooser is not None}
        values = to_apply(lines, ticked, chosen)
        for option, path in values.items():
            getattr(self, option).set(path)
            if FIRMWARE_ROWS.get(option, {}).get('check'):
                self.check_firmware(option)
        return values
