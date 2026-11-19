"""The window's Front-end mode: the compiled games as a wall of box art (front_end_view.py), in place of the queue or
Compiled Games, and back. Also the one launch of a compiled game shared by both views, which remembers when it was
played (front_end.Memory)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class FrontEndMixin:
    """The Front-end switch, its view and the shared launch of a compiled game."""

    def front_end_button_create(self, centre, toolbar=None):
        """The Front-end button, in `centre` (the middle of the bar), and the Full screen one, made in `toolbar` and
        placed by enter_front_end left of Knowledge. Both show only their picture (their hints carry the names) in the
        accent style."""
        button = ttk.Button(centre, text=self.tr('front_end'), command=self.toggle_front_end,
                            style='Feature.Toolbar.TButton')
        self.decorate_button(button, 'front_end', accent=True)
        button.configure(compound='image')
        self.hint(button, 'tip_front_end', 'front_end')
        self.front_end_button = button
        # Full screen: shown while the front-end is open (Arthur, 17 Nov 2026: the Front-end button opens it in the
        # window, this button goes full screen), left of Knowledge (19 Nov). Its picture is arrows out to the corners,
        # and arrows in while the front-end already fills the screen.
        screen = ttk.Button(toolbar if toolbar is not None else centre, text=self.tr('front_end_fullscreen'),
                            style='Feature.Toolbar.TButton',
                            command=lambda: self.set_front_end_fullscreen(not self.front_end_fullscreen))
        self.front_end_screen_button = screen
        self.front_end_screen_picture()
        self.hint(screen, 'tip_front_end_fullscreen',
                  lambda: 'front_end_window' if self.front_end_fullscreen else 'front_end_fullscreen')
        return button

    def front_end_screen_picture(self):
        """The Full screen button's picture, text and (through its hint) name for the state it is in."""
        screen = self.front_end_screen_button
        out = not getattr(self, 'front_end_fullscreen', False)
        self.decorate_button(screen, 'fullscreen_enter' if out else 'fullscreen_exit', accent=True)
        screen.configure(compound='image', text=self.tr('front_end_fullscreen' if out else 'front_end_window'))

    def front_end_localize(self):
        """A new interface language: the button, and the front-end's fonts (Chinese and Japanese have their own) and
        texts when it exists."""
        self.front_end_button.configure(text=self.tr('front_end'))
        self.front_end_screen_picture()
        view = getattr(self, 'front_end_view', None)
        if view is not None:
            view.relocalize()

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

    def enter_front_end(self, fullscreen=False):
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
        self.front_end_screen_button.pack(side='right', padx=(0, 8), after=self.knowledge_button)
        self.front_end_view.show()
        self.app.after(60, self.front_end_view.take_focus)
        # The Front-end button opens it in the window; the Full screen button, X or F11 go full screen, and the start-up
        # option can open it there directly (Arthur, 17 Nov 2026).
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
        self.front_end_screen_button.pack_forget()
        self.body.rowconfigure(1, weight=4, minsize=100)
        self.body.rowconfigure(7, weight=2, minsize=52)
        for widget in self.compiler_widgets:
            widget.grid()
        self.queue_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
        self.place_count_label()
        if (then or self.front_end_after) == 'collection':
            self.toggle_compiled_games()
        self.queue_background(self.body)

    def set_front_end_fullscreen(self, on):
        """Full screen: the whole screen for the wall, without the window's header, toolbar and status line (X, F11
        or the strip's corner button go back to the window; leaving the front-end leaves it too)."""
        self.front_end_fullscreen = bool(on)
        self.front_end_screen_picture()
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
            # Twice: Windows settles the full-screen switch a moment later and may move the focus again.
            for delay in (60, 400):
                self.app.after(delay, self.front_end_view.take_focus)
