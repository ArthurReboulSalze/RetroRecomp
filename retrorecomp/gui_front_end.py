"""The window's Front-end mode: the compiled games as a wall of box art (front_end_view.py), in place of the queue or
Compiled Games, and back. Also the one launch of a compiled game shared by both views, which remembers when it was
played (front_end.Memory)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class FrontEndMixin:
    """The Front-end switch, its view and the shared launch of a compiled game."""

    def front_end_button_create(self, toolbar):
        button = ttk.Button(toolbar, text=self.tr('front_end'), command=self.toggle_front_end, style='Toolbar.TButton')
        self.decorate_button(button, 'front_end')
        self.hint(button, 'tip_front_end')
        self.front_end_button = button
        return button

    def front_end_start_options(self, parent, checkbox):
        """Options › Common: « Start in Front-end mode », then « …in full screen » below it, greyed while the first
        is off (it only counts with the first)."""
        first = checkbox(parent, 'start_front_end', self.start_front_end, 'tip_start_front_end')
        second = ttk.Checkbutton(parent, text=self.tr('start_front_end_fullscreen'),
                                 variable=self.start_front_end_fullscreen)
        second.pack(anchor='w', padx=(24, 0), pady=(0, 8))
        self.hint(second, 'tip_start_front_end_fullscreen')
        def follow(*unused):
            if second.winfo_exists():
                second.state(['!disabled'] if self.start_front_end.get() else ['disabled'])
        first.configure(command=follow)
        follow()
        self.start_front_end_controls = (first, second)
        return first, second

    def played_memory(self):
        if getattr(self, 'front_end_memory', None) is None:
            from .front_end import Memory
            self.front_end_memory = Memory()
        return self.front_end_memory

    def ensure_compiled_view(self):
        if self.compiled_view is None:
            from .compiled_games_view import CompiledGamesView
            self.compiled_view = CompiledGamesView(self, self.body)
        return self.compiled_view

    def launch_compiled_game(self, game):
        """Play a compiled game (from Compiled Games or the front-end): one game at a time; its date is remembered."""
        if self.ensure_compiled_view().launch(game):
            self.played_memory().mark_played(game)
            return True
        return False

    def toggle_front_end(self):
        if getattr(self, 'front_end_visible', False):
            self.leave_front_end()
        else:
            self.enter_front_end()

    def enter_front_end(self, fullscreen=True):
        if self.options_panel is not None and self.options_panel.winfo_exists():
            self.close_options()
            if self.options_panel is not None:
                return
        # The queue's widgets come back first, so the front-end hides one known layout and restores it on leaving.
        self.front_end_after = 'collection' if self.collection_visible else 'queue'
        if self.collection_visible:
            self.toggle_compiled_games()
        if getattr(self, 'front_end_view', None) is None:
            from .front_end_view import FrontEndView
            self.front_end_view = FrontEndView(self, self.body)
        for widget in self.compiler_widgets:
            widget.grid_remove()
        self.queue_actions.pack_forget()
        self.count_label.pack_forget()
        self.body.rowconfigure(1, weight=1, minsize=100)
        self.body.rowconfigure(7, weight=0, minsize=0)
        self.front_end_view.grid(row=1, column=0, rowspan=7, sticky='nsew')
        self.front_end_visible = True
        self.front_end_button.state(['pressed'])
        self.front_end_view.show()
        # The front-end opens in full screen (Arthur, 16 Nov 2026); Esc / B / F11 bring the window back.
        if fullscreen:
            self.set_front_end_fullscreen(True)
        self.queue_background(self.body)

    def leave_front_end(self, then=None):
        """Back to the view the front-end was opened from (or `then`: 'queue' or 'collection')."""
        if not getattr(self, 'front_end_visible', False):
            return
        if getattr(self, 'front_end_fullscreen', False):
            self.set_front_end_fullscreen(False)
        self.front_end_view.grid_remove()
        self.front_end_view.close_controller()
        self.front_end_visible = False
        self.front_end_button.state(['!pressed'])
        self.body.rowconfigure(1, weight=4, minsize=100)
        self.body.rowconfigure(7, weight=2, minsize=52)
        for widget in self.compiler_widgets:
            widget.grid()
        self.queue_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
        self.count_label.pack(side='right', before=self.credits_button)
        if (then or self.front_end_after) == 'collection':
            self.toggle_compiled_games()
        self.queue_background(self.body)

    def set_front_end_fullscreen(self, on):
        """TV mode: the whole screen for the wall, without the window's header and toolbar (F11 or Back leaves it)."""
        self.front_end_fullscreen = bool(on)
        footer = self.status_dot.master
        if on:
            self.header.pack_forget()
            self.header_stripe.pack_forget()
            self.toolbar.grid_remove()
            footer.grid_remove()
        else:
            self.header.pack(fill='x', before=self.body)
            self.header_stripe.pack(fill='x', before=self.body)
            self.toolbar.grid()
            footer.grid()
        try:
            self.app.attributes('-fullscreen', bool(on))
        except tk.TclError:
            pass
        if getattr(self, 'front_end_view', None) is not None:
            self.front_end_view.apply_scale()
