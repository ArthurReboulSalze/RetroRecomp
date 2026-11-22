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

A variable's trace is the same kind of callback with a longer life: ``variable.trace_add`` registers it on the variable, not on
a widget, so destroying the window that uses it leaves it in Tcl, holding the callback and through it the window's object, its
pictures and their GDI handles, for as long as the session lasts (the multiplayer window: one more per opening, 22 Nov 2026).
``follow`` adds the trace for a widget's lifetime and removes it when that widget is destroyed; tests/test_tk_later.py refuses a
raw ``.trace_add(`` in retrorecomp/.
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


def follow(widget: tk.Misc, variable: tk.Variable, callback, mode='write') -> str:
    """``variable.trace_add(mode, callback)`` while ``widget`` exists: the trace (and its Tcl command) goes when ``widget`` is
    destroyed. Returns the trace's name, as trace_add does."""
    name = variable.trace_add(mode, callback)
    path = str(widget)

    def forget(event):
        if str(getattr(event, 'widget', '')) != path:   # a child's <Destroy> reaches a toplevel's binding too
            return
        try:
            variable.trace_remove(mode, name)
        except (tk.TclError, ValueError):
            pass

    widget.bind('<Destroy>', forget, add='+')
    return name


def cancel(widget: tk.Misc, job) -> None:
    """Cancel a job of ``later`` (None does nothing). Through the main window, which owns its command."""
    if not job:
        return
    try:
        widget._root().after_cancel(job)
    except (tk.TclError, ValueError, RuntimeError):
        pass
