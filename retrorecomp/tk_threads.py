"""Tk objects freed by another thread are released on the Tk thread.

A tkinter Variable or Image tells its Tcl interpreter to forget it in ``__del__``. When the last reference goes away in a
worker thread (a batch, a download), or the cyclic garbage collector happens to run there, that call reaches Tcl from the
wrong thread and the whole process aborts with « Tcl_AsyncDelete: async handler deleted by the wrong thread », no traceback
(seen 16 November 2026 in the test suite, the multiplayer branch's batch worker allocating a little more). The guard below
makes ``__del__`` defer, outside the main thread, to a list the Tk thread empties on a timer: the object is forgotten by Tcl
a moment later, from the right thread. On the main thread nothing changes.
"""
from __future__ import annotations

import threading
import tkinter as tk

DRAIN_MS = 500
_pending: list = []
_lock = threading.Lock()


def _guard(cls) -> None:
    original = cls.__dict__.get('__del__')
    if original is None or getattr(original, '_retro_recomp_guarded', False):
        return

    def __del__(self, _original=original):
        if threading.current_thread() is threading.main_thread():
            _original(self)
        else:
            with _lock:
                _pending.append((_original, self))      # kept alive until the Tk thread runs its finaliser

    __del__._retro_recomp_guarded = True
    cls.__del__ = __del__


def install() -> None:
    """Once, before any Tk object exists: Variable (and its subclasses) and Image (PhotoImage, BitmapImage)."""
    _guard(tk.Variable)
    _guard(tk.Image)


def release_deferred() -> int:
    """Run, on the Tk thread, the finalisers other threads deferred; returns how many."""
    with _lock:
        items = _pending[:]
        _pending.clear()
    for finaliser, obj in items:
        try:
            finaliser(obj)
        except Exception:       # the interpreter may be gone already (the window closed)
            pass
    return len(items)


def pending() -> int:
    with _lock:
        return len(_pending)


def keep_draining(root: tk.Misc) -> None:
    """Empty the deferred list now and every DRAIN_MS while the window lives."""
    def tick():
        release_deferred()
        try:
            root.after(DRAIN_MS, tick)
        except tk.TclError:
            pass
    tick()
