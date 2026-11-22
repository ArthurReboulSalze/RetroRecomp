"""Tk objects freed by another thread are released on the Tk thread.

A tkinter Variable or Image tells its Tcl interpreter to forget it in ``__del__``. When the last reference goes away in a
worker thread (a batch, a download), or the cyclic garbage collector happens to run there, that call reaches Tcl from the
wrong thread and the whole process aborts with « Tcl_AsyncDelete: async handler deleted by the wrong thread », no traceback
(seen 16 November 2026 in the test suite, the multiplayer branch's batch worker allocating a little more). The guard below
makes ``__del__`` defer, outside the main thread, to a list the Tk thread empties on a timer: the object is forgotten by Tcl
a moment later, from the right thread. On the main thread nothing changes.

A root (``tk.Tk``) is the same danger in a larger form: its interpreter (the ``tkapp`` object every widget, image, font and
variable of the root holds as ``.tk``) is deleted by Tcl when its last reference goes away, and from another thread that is
the same abort. A destroyed root that sits in a reference cycle (a window and the object that owns it, a test and its stand-ins)
is freed by the cycle collector, which runs in whichever thread happens to allocate: twice in the full test suite on 22 November
2026, during the interface tests. So a root's ``__del__`` parks its interpreter here, whatever the thread, and the main thread
frees it later, once nothing else holds it: when the next root is created, on the app's drain timer, or at exit.

A destroyed root must also become garbage at all. tkinter deletes the callbacks a widget registered when the widget is destroyed,
but not the ones a Variable registered for its traces (``trace_add``): they live until the Variable itself is freed, and each
holds the callback, so the window object that owns the Variable, so the root. That cycle passes through Tcl, where the collector
cannot see it, and the root, its interpreter and its pictures stayed for the life of the process (124 roots and half the
Windows GDI limit over one pass of the interface tests, 22 Nov 2026). So once a root is destroyed, the variable traces that call
Python are removed and every Python callback still standing in its interpreter is deleted; a Variable freed later finds its
commands gone, which it ignores.
"""
from __future__ import annotations

import re
import sys
import threading
import tkinter as tk
from tkinter import font as tk_font

DRAIN_MS = 500
_pending: list = []
_parked: list = []          # the interpreters of dead roots, freed on the main thread only (release_deferred)
_lock = threading.Lock()


def _count(items: list, index: int) -> int:
    return sys.getrefcount(items[index])


_ALONE = _count([object()], 0)   # an object only a list holds, counted the same way (the interpreter's own borrowed references)


def _guard(cls) -> None:
    original = cls.__dict__.get('__del__')
    if original is None or getattr(original, '_retro_recomp_guarded', False):
        return

    def __del__(self, _original=original):
        if threading.current_thread() is threading.main_thread():
            try:
                _original(self)
            except tk.TclError:     # its commands were deleted with its root (_forget_callbacks)
                pass
        else:
            with _lock:
                _pending.append((_original, self))      # kept alive until the Tk thread runs its finaliser

    __del__._retro_recomp_guarded = True
    cls.__del__ = __del__


# tkinter names every Python callback it registers in Tcl repr(id(function)) followed by the function's name; no Tcl or Tk
# command starts with a digit.
_PYTHON_COMMAND = re.compile(r'^[0-9]')


def _forget_callbacks(interpreter) -> int:
    """After its root is destroyed: remove the variable traces that call Python, then delete every Python callback still
    defined in the interpreter. Returns how many callbacks were deleted."""
    deleted = 0
    try:
        split = interpreter.splitlist
        for variable in split(interpreter.call('info', 'globals')):
            try:
                traces = split(interpreter.call('trace', 'info', 'variable', variable))
            except tk.TclError:
                continue
            for trace in traces:
                operations, command = split(trace)
                if _PYTHON_COMMAND.match(str(command)):
                    interpreter.call('trace', 'remove', 'variable', variable, operations, command)
        for name in split(interpreter.call('info', 'commands')):
            if _PYTHON_COMMAND.match(str(name)):
                interpreter.deletecommand(str(name))
                deleted += 1
    except tk.TclError:         # the interpreter is being deleted already
        pass
    return deleted


def _guard_root() -> None:
    if getattr(tk.Tk, '_retro_recomp_guarded', False):
        return
    original_init = tk.Tk.__init__

    def __init__(self, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            release_deferred()                          # the interpreters of the roots that died since the last one
        original_init(self, *args, **kwargs)

    def __del__(self):
        interpreter = self.__dict__.get('tk')           # absent when Tk() itself failed (no display)
        if interpreter is not None:
            with _lock:
                _parked.append(interpreter)

    original_destroy = tk.Tk.destroy

    def destroy(self):
        original_destroy(self)
        interpreter = self.__dict__.get('tk')
        if interpreter is not None:
            _forget_callbacks(interpreter)              # nothing in Tcl holds this root's Python objects any more

    tk.Tk.__init__ = __init__
    tk.Tk.__del__ = __del__
    tk.Tk.destroy = destroy
    tk.Tk._retro_recomp_guarded = True


def install() -> None:
    """Once, before any Tk object is freed (tk_later installs it when it is imported, so before any window exists): Variable
    (and its subclasses), Image (PhotoImage, BitmapImage), Font, Pillow's ImageTk pictures, and the root's interpreter."""
    _guard(tk.Variable)
    _guard(tk.Image)
    _guard(tk_font.Font)
    try:
        # Pillow's pictures delete their Tk image in __del__ through Tcl: from another thread that call waits for the main
        # thread and can wait for ever (the stress loop's collector thread, 22 Nov 2026, once closed windows became garbage).
        from PIL import ImageTk
    except ImportError:
        pass
    else:
        _guard(ImageTk.PhotoImage)
        _guard(ImageTk.BitmapImage)
    _guard_root()


def release_deferred() -> int:
    """Run, on the Tk thread, the finalisers other threads deferred, and free the parked interpreters nothing else holds any
    more; returns how many finalisers ran and interpreters were freed. Outside the main thread it does nothing."""
    if threading.current_thread() is not threading.main_thread():
        return 0
    with _lock:
        items = _pending[:]
        _pending.clear()
        parked = _parked.copy()
        _parked.clear()
    for finaliser, obj in items:
        try:
            finaliser(obj)
        except Exception:       # the interpreter may be gone already (the window closed)
            pass
    held = [_count(parked, index) > _ALONE for index in range(len(parked))]
    kept = [interpreter for interpreter, busy in zip(parked, held) if busy]
    freed = len(parked) - len(kept)
    parked.clear()              # the others are deleted here, on this thread
    if kept:
        with _lock:
            _parked.extend(kept)
    return len(items) + freed


def pending() -> int:
    with _lock:
        return len(_pending)


def parked() -> int:
    """How many interpreters of dead roots wait for the main thread."""
    with _lock:
        return len(_parked)


def keep_draining(root: tk.Misc) -> None:
    """Empty the deferred list now and every DRAIN_MS while the window lives."""
    def tick():
        release_deferred()
        try:
            root.after(DRAIN_MS, tick)
        except tk.TclError:
            pass
    tick()
