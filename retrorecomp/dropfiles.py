"""Native Explorer / XDND file drops, queued on the converter's UI thread."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from urllib.parse import unquote, urlsplit


class WindowsFileDrop:
    """Own native subclasses on the Tk thread; deliver paths without calling Tk.

    The receiver must enqueue work, rather than identifying ROMs inside a window
    procedure. Register children too so a drop works over the table, its empty
    state, the banner and the log. Dialogs are deliberately separate windows.
    """

    def __init__(self, root, receive, failed):
        self.root = root
        self.receive, self.failed = receive, failed
        self.handles = set()
        self.shell = ctypes.WinDLL('shell32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.controls = ctypes.WinDLL('comctl32', use_last_error=True)
        pointer = ctypes.c_size_t
        self.proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
            wintypes.UINT, pointer, ctypes.c_ssize_t, pointer, pointer)
        self.proc = self.proc_type(self._message)  # Keep alive until every hook is removed.
        self.identity = id(self)
        self.shell.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        self.shell.DragAcceptFiles.restype = None
        self.shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                            wintypes.LPWSTR, wintypes.UINT]
        self.shell.DragQueryFileW.restype = wintypes.UINT
        self.shell.DragFinish.argtypes = [wintypes.HANDLE]
        self.shell.DragFinish.restype = None
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.controls.SetWindowSubclass.argtypes = [wintypes.HWND, self.proc_type, pointer, pointer]
        self.controls.SetWindowSubclass.restype = wintypes.BOOL
        self.controls.RemoveWindowSubclass.argtypes = [wintypes.HWND, self.proc_type, pointer]
        self.controls.RemoveWindowSubclass.restype = wintypes.BOOL
        self.controls.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT,
                                                 pointer, ctypes.c_ssize_t]
        self.controls.DefSubclassProc.restype = ctypes.c_ssize_t
        try:
            self._register(self.user.GetAncestor(root.winfo_id(), 2))  # Tk's WM wrapper.
            self._widgets(root)
        except Exception:
            self.close()
            raise
        root.bind('<Destroy>', self._destroy, add='+')

    def _register(self, handle):
        if not handle or handle in self.handles:
            return
        if not self.controls.SetWindowSubclass(handle, self.proc, self.identity, 0):
            raise OSError('Could not register the ROM drop target')
        self.handles.add(handle)
        self.shell.DragAcceptFiles(handle, True)

    def _widgets(self, widget):
        self._register(widget.winfo_id())
        for child in widget.winfo_children():
            if child.winfo_toplevel() == self.root:
                self._widgets(child)

    def _message(self, handle, message, wparam, lparam, identity, data):
        if message == 0x0233:  # WM_DROPFILES; this window owns the HDROP now.
            try:
                paths = []
                count = self.shell.DragQueryFileW(wparam, 0xffffffff, None, 0)
                for index in range(count):
                    length = self.shell.DragQueryFileW(wparam, index, None, 0)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    self.shell.DragQueryFileW(wparam, index, buffer, length + 1)
                    if buffer.value:
                        paths.append(buffer.value)
            except Exception as error:
                self.failed(error)
            else:
                try:
                    self.receive(paths)
                except Exception as error:
                    self.failed(error)
            finally:
                self.shell.DragFinish(wparam)
            return 0
        if message == 0x0082:  # WM_NCDESTROY: don't retain a recycled HWND.
            self.controls.RemoveWindowSubclass(handle, self.proc, self.identity)
            self.handles.discard(handle)
        return self.controls.DefSubclassProc(handle, message, wparam, lparam)

    def _destroy(self, event):
        if event.widget == self.root:
            self.close()

    def close(self):
        for handle in tuple(self.handles):
            self.shell.DragAcceptFiles(handle, False)
            self.controls.RemoveWindowSubclass(handle, self.proc, self.identity)
            self.handles.discard(handle)


def local_drop_paths(tk, data):
    """Tcl lists preserve spaces, braces and Unicode; never split on whitespace."""
    paths = []
    for value in tk.splitlist(data):
        if value.startswith('file:'):
            url = urlsplit(value)
            if url.netloc not in ('', 'localhost'):
                continue
            value = unquote(url.path)
        if value.startswith('/'):
            paths.append(value)
    return paths


class LinuxFileDrop:
    def __init__(self, root, receive, failed):
        from tkinterdnd2 import TkinterDnD, DND_FILES
        self.root, self.receive, self.failed = root, receive, failed
        self.widgets = []
        try:
            TkinterDnD.require(root)
            def register(widget):
                widget.drop_target_register(DND_FILES)
                self.widgets.append(widget)
                widget.dnd_bind('<<Drop>>', self._drop)
                for child in widget.winfo_children():
                    if child.winfo_toplevel() == root:
                        register(child)
            # Tk itself is not a BaseWidget; tkinterdnd2 extends its children.
            # Our canvases fill the toplevel, including banner, stripe and body.
            for child in root.winfo_children():
                if child.winfo_toplevel() == root:
                    register(child)
        except Exception:
            self.close()
            raise OSError('Could not enable Linux file drops (tkdnd).') from None
        root.bind('<Destroy>', self._destroy, add='+')

    def _drop(self, event):
        try:
            paths = local_drop_paths(self.root.tk, event.data)
            if not paths:
                return 'refuse_drop'
            self.receive(paths)
            return 'copy'
        except Exception as error:
            self.failed(error)
            return 'refuse_drop'

    def _destroy(self, event):
        if event.widget == self.root:
            self.close()

    def close(self):
        for widget in self.widgets:
            try:
                widget.drop_target_unregister()
            except Exception:
                pass  # Tk may already have destroyed this child.
        self.widgets.clear()


def enable_file_drop(root, receive, failed):
    if os.name == 'nt':
        return WindowsFileDrop(root, receive, failed)
    try:
        return LinuxFileDrop(root, receive, failed)
    except ImportError:
        raise OSError('Linux file drops require tkinterdnd2.') from None
