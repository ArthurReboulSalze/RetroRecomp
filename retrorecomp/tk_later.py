"""Timers and idle calls of the converter's windows, always scheduled on the main window.

tkinter's ``widget.after(ms, func)`` and ``widget.after_idle(func)`` register ``func`` as a Tcl command named after the
Python function's id (``1977300563776<lambda>``) and owned by ``widget``: destroying the widget deletes the command,
but the timer or idle script stays queued under that name. When it comes due it either fails (« invalid command
name ») or, when CPython has meanwhile given a new callback the same freed id, so the same name, runs THAT one: the
Stop dialog answered « Stop now » by itself (gui_smoke, 21 Nov 2026, the window placement check of a closed dialog).

``later`` schedules on the main window, which outlives every window, dialog, canvas and view, and skips the call when
the widget it is for no longer exists; ``cancel`` cancels such a job. Every timer and idle call of a widget that can be
destroyed before it is due goes through here: tests/test_tk_later.py refuses a raw ``.after(`` or ``.after_idle(``
anywhere in retrorecomp/ except on the main window itself.
"""
from __future__ import annotations

import tkinter as tk

from . import tk_threads

# Every window module schedules through here, so importing it is the moment before any window exists: the Tk objects (variables,
# images, fonts, a root's interpreter) freed in another thread are released on the main thread instead (tk_threads), in the
# converter, the game collection and the test suite alike.
tk_threads.install()


def later(widget: tk.Misc, delay, func, *args):
    """Call ``func(*args)`` after ``delay`` milliseconds, or when Tk is next idle (``delay='idle'``), for ``widget``:
    nothing happens when ``widget`` was destroyed first. Returns the job for ``cancel`` (None when the main window is
    gone already, as when the app is closing)."""
    root = widget._root()

    def run():
        try:
            alive = widget.winfo_exists()
        except tk.TclError:
            return
        if alive:
            func(*args)

    run.__name__ = getattr(func, '__name__', 'later')      # the Tcl command's name stays readable in a trace
    try:
        return root.after_idle(run) if delay == 'idle' else root.after(delay, run)
    except (tk.TclError, RuntimeError):
        return None


def cancel(widget: tk.Misc, job) -> None:
    """Cancel a job of ``later`` (None does nothing). Through the main window, which owns its command."""
    if not job:
        return
    try:
        widget._root().after_cancel(job)
    except (tk.TclError, ValueError, RuntimeError):
        pass
