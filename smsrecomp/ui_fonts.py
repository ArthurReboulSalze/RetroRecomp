"""Process-local, OFL font subsets; no installation or system font changes."""
from __future__ import annotations
import ctypes
import ctypes.util
import os
from .paths import ASSETS

_loaded = False


def load_fonts():
    global _loaded
    if _loaded:
        return
    paths = [ASSETS/'assets'/f'RetroRecomp-UI-{face}.otf' for face in ('JP','SC')]
    if not all(path.is_file() for path in paths):
        raise RuntimeError('Retro-Recomp interface font subsets are missing.')
    if os.name == 'nt':
        add = ctypes.WinDLL('gdi32', use_last_error=True).AddFontResourceExW
        add.argtypes = (ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_void_p)
        add.restype = ctypes.c_int
        for path in paths:
            if not add(str(path),0x10,None):
                raise OSError('Unable to load the Retro-Recomp interface font.')
    else:
        library = ctypes.util.find_library('fontconfig')
        if not library:
            raise OSError('Fontconfig is required for the multilingual interface.')
        fc = ctypes.CDLL(library)
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddFile.argtypes = (ctypes.c_void_p,ctypes.c_char_p)
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        config = fc.FcConfigGetCurrent()
        for path in paths:
            if not fc.FcConfigAppFontAddFile(config,os.fsencode(path)):
                raise OSError('Unable to load the Retro-Recomp interface font.')
    _loaded = True


def family(language):
    # Keep the original Windows UI face for Latin and Cyrillic. The CJK subset
    # is needed for Chinese/Japanese, not for every translated interface.
    if os.name == 'nt' and language not in ('zh', 'ja'):
        return 'Segoe UI'
    return 'RetroRecomp UI SC' if language == 'zh' else 'RetroRecomp UI JP'
