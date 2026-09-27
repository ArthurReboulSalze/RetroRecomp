"""Windows shell identity and icon refresh after replacing a generated EXE."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


def set_converter_identity() -> None:
    if os.name != 'nt':
        return
    try:
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID('RetroRecomp.Converter')
    except OSError:
        pass


def refresh_executable_icon(target: Path) -> None:
    """Notify the Shell that this EXE changed, without restarting Explorer.

    This is best effort: an unavailable shell must not fail an installation
    that has already succeeded. Call only once the new file is in place.
    """
    if os.name != 'nt':
        return
    try:
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.SHChangeNotify.argtypes = [wintypes.LONG, wintypes.UINT,
                                        ctypes.c_void_p, ctypes.c_void_p]
        shell.SHChangeNotify.restype = None
        path = ctypes.c_wchar_p(str(target.resolve()))
        # SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT.
        shell.SHChangeNotify(0x2000, 0x3005, ctypes.cast(path, ctypes.c_void_p), None)
    except OSError:
        pass
