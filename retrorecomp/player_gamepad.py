"""Controller navigation for Compiled Games; no global keyboard/input hooks."""
import ctypes as C
import os
from .paths import ASSETS


class Controller:
    def __init__(self, library=None):
        name = 'retro_gamepad.dll' if os.name == 'nt' else 'libretro_gamepad.so'
        path = ASSETS/'player-runtime'/name
        if not path.is_file(): path = ASSETS/'.build/player-gamepad/runtime'/name
        self.lib = C.CDLL(str(library or path))
        self.lib.rr_player_pads_open.restype = C.c_void_p
        self.lib.rr_player_pads_open.argtypes = []
        self.lib.rr_player_pads_poll.restype = C.c_int
        self.lib.rr_player_pads_poll.argtypes = [C.c_void_p,C.POINTER(C.c_int32)]
        self.lib.rr_player_pads_close.argtypes = [C.c_void_p]
        self.lib.rr_player_pads_close.restype = None
        self.handle = self.lib.rr_player_pads_open()
        if not self.handle: raise OSError('Controller initialization failed.')

    def poll(self):
        values = (C.c_int32*12)()
        if self.lib.rr_player_pads_poll(self.handle,values)<0: raise OSError('Controller polling failed.')
        return [tuple(values[i:i+3]) for i in range(0,12,3)]

    def close(self):
        if self.handle:
            self.lib.rr_player_pads_close(self.handle)
            self.handle = None


class Navigation:
    """Neutral-to-arm, edge-triggered launch and paced directional repeats."""
    def __init__(self):
        self.armed = False
        self.buttons = self.direction = 0
        self.repeat_at = 0.

    def update(self, pads, now, enabled=True):
        buttons = 0
        direction = 0
        for mask, x, y in pads:
            buttons |= mask
            d = -1 if mask & (1<<11) or y < -16000 else 1 if mask & (1<<12) or y > 16000 else 0
            if d: direction = d
        if not enabled:
            self.armed = False
        if not self.armed:
            self.buttons = buttons
            self.direction = direction
            self.armed = enabled and not buttons and not direction
            return None
        launch = bool(buttons & 1 and not self.buttons & 1)
        self.buttons = buttons
        move = direction and (direction != self.direction or now >= self.repeat_at)
        if move: self.repeat_at = now + (.35 if direction != self.direction else .10)
        self.direction = direction
        if launch: return 'play'
        if move: return direction
        return None
