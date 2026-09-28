"""Replace generated games, or install them when Windows releases the old EXE."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .library import atomic_json
from .packing import compact_executable
from .windows import refresh_executable_icon


def job_path(target: Path) -> Path:
    key = hashlib.sha256(str(target.resolve()).casefold().encode('utf-8')).hexdigest()[:20]
    return target.parent / 'datas/pending' / (key + '.json')


@contextmanager
def publication_lock(target: Path):
    # A converter and its detached installer must never publish out of order.
    if os.name != 'nt':
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    key = hashlib.sha256(str(target.resolve()).casefold().encode('utf-8')).hexdigest()
    handle = kernel.CreateMutexW(None, False, 'Local\\Retro-Recomp-Publish-' + key)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        result = kernel.WaitForSingleObject(handle, 30000)
        if result not in (0, 0x80):
            raise OSError('Another conversion is still publishing this game.')
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _running(target: Path) -> bool:
    if os.name != 'nt':
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    ids = (ctypes.c_uint32 * 16384)()
    used = ctypes.c_uint32()
    psapi.EnumProcesses.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    if not psapi.EnumProcesses(ids, ctypes.sizeof(ids), ctypes.byref(used)):
        return False
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    expected = str(target.resolve()).casefold()
    for pid in ids[:used.value // 4]:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            name = ctypes.create_unicode_buffer(32768)
            length = ctypes.c_uint32(len(name))
            if kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
                if str(Path(name.value).resolve()).casefold() == expected:
                    return True
        finally:
            kernel.CloseHandle(handle)
    return False


def _delete_sharing_lock(target: Path) -> bool:
    if os.name != 'nt':
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # Query DELETE access; do not delete, write, or mark the file for removal.
    handle = kernel.CreateFileW(str(target), 0x10000, 7, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        return ctypes.get_last_error() in (32, 33)
    kernel.CloseHandle(handle)
    return False


def _in_use(error: PermissionError, target: Path) -> bool:
    return target.is_file() and (getattr(error, 'winerror', None) in (32, 33) or
        (getattr(error, 'winerror', None) == 5 and (_delete_sharing_lock(target) or _running(target))))


def is_pending(target: Path) -> bool:
    return job_path(target).is_file()


def _start_installer(marker: Path, token: str):
    environment = os.environ.copy()
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '_install-pending', str(marker), token]
        # Unpack separately so the parent can clean up its temporary DLLs
        # while this installer waits for the game to close.
        environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    else:
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'RetroRecomp.py'),
                   '_install-pending', str(marker), token]
    with marker.with_suffix('.log').open('ab') as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 env=environment,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    # Keep the process object alive and reap it without blocking conversion.
    threading.Thread(target=child.wait, daemon=True).start()
    return child


def publish_executable(source: Path, target: Path, *, start_worker=True,
                       compact=False) -> bool:
    """Return True when installation is waiting for a running/locked game.

    Copies are staged on the destination volume. Ordinary reconversion silently
    replaces the EXE; sharing violations keep the old game playable and queue
    the latest build. Real permission/disk errors remain conversion failures.
    """
    source, target = source.resolve(), target.resolve()
    marker = job_path(target)
    marker.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staged = marker.parent / (token + '.exe')
    shutil.copy2(source, staged)
    pending = False
    try:
        if compact:
            compact_executable(staged)
        with publication_lock(target):
            previous = None
            try:
                previous = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
            try:
                os.replace(staged, target)
            except PermissionError as error:
                if not _in_use(error, target):
                    raise
                atomic_json(marker, {'token': token, 'target': str(target), 'staged': str(staged),
                    'sha256': hashlib.sha256(staged.read_bytes()).hexdigest()})
                pending = True
            if not pending:
                marker.unlink(missing_ok=True)
                refresh_executable_icon(target)
            if previous:
                old = Path(previous.get('staged', ''))
                if old.parent.resolve() == marker.parent.resolve() and old != staged and old.suffix == '.exe':
                    old.unlink(missing_ok=True)
    finally:
        if not pending:
            staged.unlink(missing_ok=True)
    if pending and start_worker:
        _start_installer(marker, token)
    return pending


def install_pending(marker: Path, token: str, *, wait=True) -> int:
    """A newer conversion supersedes this job; do not interrupt any game."""
    verified = False
    while True:
        try:
            job = json.loads(marker.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return 0
        if job.get('token') != token:
            return 0
        target = Path(job['target'])
        if job_path(target).resolve() != marker.resolve():
            raise ValueError('Invalid pending installation location')
        with publication_lock(target):
            # Re-read after acquiring the same lock used by every conversion.
            try:
                job = json.loads(marker.read_text(encoding='utf-8'))
            except FileNotFoundError:
                return 0
            if job.get('token') != token:
                return 0
            staged = Path(job['staged'])
            if staged.parent.resolve() != marker.parent.resolve() or staged.name != token + '.exe':
                raise ValueError('Invalid staged executable')
            if not verified:
                if hashlib.sha256(staged.read_bytes()).hexdigest() != job['sha256']:
                    raise ValueError('Pending executable changed since compilation')
                verified = True
            try:
                os.replace(staged, target)
            except PermissionError as error:
                if not _in_use(error, target):
                    raise
            else:
                marker.unlink()
                refresh_executable_icon(target)
                return 0
        if not wait:
            return 1
        time.sleep(1)
