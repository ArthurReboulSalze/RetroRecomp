"""Live four-channel MOD playback for the converter's credits, not game exports."""
from __future__ import annotations
import ctypes as C
import json
import os
from pathlib import Path
import random
import threading

from .paths import ASSETS, data_directory
from .library import atomic_text

TRACKS = ('night_vector.mod', 'Pixel_Rush.mod', 'pocket_signals_v2.mod')
TITLES = ('Night Vector', 'Pixel Rush', 'Pocket Signals V2')
# Opening another dialog while its predecessor's device is shutting down must
# never play two songs together. Only audio workers wait on this lock.
_device_lock = threading.Lock()


def choose_track(previous=None, rng=None):
    return (rng or random.SystemRandom()).choice([name for name in TRACKS if name != previous])


def library_path():
    name = 'retro_credits.dll' if os.name == 'nt' else 'libretro_credits.so'
    embedded = ASSETS / 'credits-runtime' / name
    return embedded if embedded.is_file() else ASSETS / '.build/credits-audio/runtime' / name


def percussion_map(data):
    """Roles of the supplied ChipLoom samples; melodies are never beat sources.

    Pocket Signals uses catalog names for its three rhythm voices. Combo
    kick/snare + tick samples carry both bits. Values use MOD's 31 sample slots.
    """
    result = []
    for slot in range(31):
        name = data[20+slot*30:42+slot*30].split(b'\0',1)[0].decode('latin1').lower()
        mask = (1 if 'kick' in name else 0) | (2 if 'snare' in name else 0)
        if 'tick' in name: mask |= 4
        mask |= {'tonal hit 78':1, 'fx short 79':2, 'noise hit 77':4}.get(name,0)
        result.append(mask)
    return bytes(result)


class Decoder:
    """Small, deliberately fixed ABI; one owner, no Python audio callbacks."""
    def __init__(self, data, library=None):
        self.lib = C.CDLL(str(library or library_path()))
        for name, result, args in (
            ('open', C.c_void_p, (C.c_void_p, C.c_long)),
            ('start', C.c_int, (C.c_void_p,)),
            ('mute', None, (C.c_void_p, C.c_int)),
            ('info', C.c_int, (C.c_void_p, C.POINTER(C.c_int))),
            ('percussion', C.c_int, (C.c_void_p, C.POINTER(C.c_ubyte))),
            ('beats', None, (C.c_void_p, C.POINTER(C.c_uint32))),
            ('render', C.c_int, (C.c_void_p, C.POINTER(C.c_short), C.c_int)),
            ('close', None, (C.c_void_p,)),
        ):
            function = getattr(self.lib, 'rr_music_' + name)
            function.restype, function.argtypes = result, args
        self.data = C.create_string_buffer(data)
        self.handle = self.lib.rr_music_open(self.data, len(data))
        if not self.handle:
            raise ValueError('Unsupported or damaged four-channel MOD.')
        roles = (C.c_ubyte * 31).from_buffer_copy(percussion_map(data))
        if self.lib.rr_music_percussion(self.handle, roles):
            self.close()
            raise ValueError('Could not configure module percussion.')

    def start(self):
        if self.lib.rr_music_start(self.handle):
            raise OSError('Audio output is unavailable.')

    def mute(self, muted):
        self.lib.rr_music_mute(self.handle, muted)

    def info(self):
        values = (C.c_int * 10)()
        if self.lib.rr_music_info(self.handle, values):
            raise OSError('Module replay stopped.')
        return tuple(values)

    def render(self, frames=960):
        values = (C.c_short * (frames * 2))()
        if self.lib.rr_music_render(self.handle, values, frames):
            raise OSError('Module replay failed.')
        return bytes(values)

    def beats(self):
        values = (C.c_uint32 * 6)()
        self.lib.rr_music_beats(self.handle, values)
        return tuple(values)

    def close(self):
        if self.handle:
            self.lib.rr_music_close(self.handle)
            self.handle = None


class MusicSession:
    """Selection/mute survives reopening; disk writes occur only on user actions."""
    def __init__(self, path=None):
        self.path = path or data_directory() / 'credits-player.json'
        try:
            state = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        self.previous = state.get('last_track')
        self.muted = state.get('muted') is True

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_text(self.path, json.dumps({'last_track': self.previous, 'muted': self.muted})+'\n')
        except OSError:
            pass  # Read-only installations still retain their in-process state.

    def open(self):
        self.previous = choose_track(self.previous)
        self.save()
        return MusicPlayer(self.previous, self.muted)

    def set_muted(self, muted):
        self.muted = bool(muted)
        self.save()


class MusicPlayer:
    def __init__(self, track, muted=False):
        self.track = track
        self.title = TITLES[TRACKS.index(track)]
        self.muted = bool(muted)
        self.status = 'starting'
        self.diagnostic = ''
        self.values = (0,) * 10
        self.beats = (0,) * 6
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name='credits-music', daemon=True)
        self.thread.start()

    def _run(self):
        decoder = None
        acquired = False
        try:
            while not self.stop_event.is_set():
                if _device_lock.acquire(timeout=.05):
                    acquired = True
                    break
            if not acquired or self.stop_event.is_set():
                return
            data = (ASSETS / 'MEDIAS/trackers_chiploom' / self.track).read_bytes()
            decoder = Decoder(data)
            if self.stop_event.is_set():
                return
            decoder.mute(self.muted)
            decoder.start()
            self.status = 'playing'
            while not self.stop_event.wait(.025):
                decoder.mute(self.muted)
                self.values = decoder.info()
                self.beats = decoder.beats()
        except (OSError, ValueError) as exc:
            self.diagnostic = str(exc)
            self.status = 'unavailable'
        finally:
            if decoder is not None:
                decoder.close()
            if acquired:
                _device_lock.release()
            if self.stop_event.is_set():
                self.status = 'closed'

    def close(self):
        self.stop_event.set()
