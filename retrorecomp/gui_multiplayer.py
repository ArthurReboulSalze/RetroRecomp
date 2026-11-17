"""The window's Multiplayer button and its window (multiplayer_view.py): host or join a room on the local network. One window
at a time; closing the converter with a room open asks first, as closing that window does."""
from __future__ import annotations


class MultiplayerMixin:
    """The toolbar button, the window's one instance, and the converter's closing."""

    multiplayer_window = None

    def multiplayer_button_create(self, toolbar):
        button = self.icon_button(toolbar, 'mp_title', 'tip_multiplayer', self.show_multiplayer, 'players', managed=False)
        self.multiplayer_button = button
        return button

    def multiplayer_name(self):
        """The nickname a room starts with: the retro-recomp.com pseudonym when signed in, else empty."""
        player = getattr(self, 'player', None) or {}
        profile = player.get('profile') or {}
        account = player.get('account') or {}
        return str(profile.get('pseudonym') or account.get('pseudonym') or '')[:16]

    def show_multiplayer(self, pick=None):
        """Open the window (or bring it forward). `pick`: a compiled game chosen before, from Compiled Games."""
        window = self.multiplayer_window
        if window is not None and not window.closing and window.window.winfo_exists():
            window.window.deiconify()
            window.window.lift()
            window.window.focus_set()
            return window
        from .multiplayer_view import MultiplayerWindow
        from .netplay.lobby_check import LocalLibrary
        self.multiplayer_window = MultiplayerWindow(self, LocalLibrary(self.compiled_inventory),
                                                    name=self.multiplayer_name(), pick=pick)
        return self.multiplayer_window

    def multiplayer_may_close(self):
        """The converter is closing: a room open asks first (leaving ends a match for this player). False: stay open."""
        window = self.multiplayer_window
        if window is None or window.closing:
            return True
        try:
            if not window.window.winfo_exists():
                return True
        except Exception:
            return True
        return window.ask_close()
