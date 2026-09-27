from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from smsrecomp.publishing import publish_executable, job_path, is_pending, install_pending
from smsrecomp.publishing import _start_installer, _running


@contextmanager
def locked_file(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'build.exe'
        self.target = self.root / 'Buggy Run.exe'
        self.source.write_bytes(b'new generation')
        self.target.write_bytes(b'previous generation')

    def test_regeneration_replaces_existing_game_without_confirmation(self):
        self.assertFalse(publish_executable(self.source, self.target))
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertFalse(is_pending(self.target))

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock')
    def test_locked_game_queues_and_only_latest_generation_is_installed(self):
        with locked_file(self.target):
            self.assertTrue(publish_executable(self.source, self.target, start_worker=False))
            first = json.loads(job_path(self.target).read_text())
            self.assertEqual(self.target.read_bytes(), b'previous generation')
            self.assertEqual(install_pending(job_path(self.target), first['token'], wait=False), 1)
            self.source.write_bytes(b'latest generation')
            self.assertTrue(publish_executable(self.source, self.target, start_worker=False))
            latest = json.loads(job_path(self.target).read_text())
            self.assertNotEqual(first['token'], latest['token'])
            self.assertFalse(Path(first['staged']).exists())
            self.assertEqual(install_pending(job_path(self.target), first['token'], wait=False), 0)
        self.assertEqual(install_pending(job_path(self.target), latest['token'], wait=False), 0)
        self.assertEqual(self.target.read_bytes(), b'latest generation')
        self.assertFalse(is_pending(self.target))

    @unittest.skipUnless(os.name == 'nt', 'Detached Windows installer')
    def test_background_installer_finishes_after_lock_is_released(self):
        children = []
        def start(marker, token):
            child = _start_installer(marker, token)
            children.append(child)
            return child
        with patch('smsrecomp.publishing._start_installer', side_effect=start):
            with locked_file(self.target):
                self.assertTrue(publish_executable(self.source, self.target))
                self.assertTrue(is_pending(self.target))
        deadline = time.monotonic() + 15
        while is_pending(self.target) and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertFalse(is_pending(self.target))
        self.assertEqual(self.target.read_bytes(), b'new generation')
        self.assertEqual(children[0].wait(timeout=10), 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows process image query')
    def test_running_process_detection_uses_the_full_executable_path(self):
        import sys
        self.assertTrue(_running(Path(sys.executable)))
        self.assertFalse(_running(self.target))

    def test_real_permission_failure_preserves_the_old_game(self):
        error = PermissionError('ACL denied')
        error.winerror = 5
        with patch('smsrecomp.publishing.os.replace', side_effect=error), \
             patch('smsrecomp.publishing._running', return_value=False):
            with self.assertRaises(PermissionError):
                publish_executable(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'previous generation')
        self.assertFalse(is_pending(self.target))
