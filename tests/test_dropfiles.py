"""Real Windows HDROP delivery and reuse of the mixed-console ROM queue."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import queue
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from retrorecomp.dropfiles import enable_file_drop, local_drop_paths
from retrorecomp.gui import Application
from retrorecomp.i18n import tr
from tools.gui_patching import patch_gui


class DropQueueTests(unittest.TestCase):
    def test_drop_does_not_change_an_active_batch_or_update(self):
        for busy, updating in ((True, False), (False, True)):
            app = Application.__new__(Application)
            app.busy, app.updating = busy, updating
            app.messages = queue.Queue()
            app.language = 'en'
            app.add_paths = Mock()
            app.queue_drop(['a.sms'])
            self.assertEqual(app.messages.get_nowait()[0], 'drop_blocked')
            # Also guard a drop received just before the batch starts.
            app.drop_paths(['a.sms'])
            app.add_paths.assert_not_called()
            self.assertEqual(app.messages.get_nowait(), ('log', tr('drop_blocked', 'en')))

    def test_linux_tcl_paths_and_local_uris(self):
        interp = tk.Tcl()
        self.assertEqual(local_drop_paths(interp,
            '{/tmp/ROMs été/Game {1}.nes} file:///tmp/Jeu%20de%20test.gb '
            'https://example.org/game.zip file://server/private.gb'),
            ['/tmp/ROMs été/Game {1}.nes', '/tmp/Jeu de test.gb'])


@unittest.skipUnless(os.name == 'nt', 'Windows Explorer/Tk integration')
class WindowsDropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve() / 'ROMs été avec espaces'
        self.folder.mkdir()
        self.root = tk.Tk()
        self.root.withdraw()
        with patch_gui('load_preferences', return_value={}), \
                patch_gui('preferred_games_root', return_value=(self.folder / 'exports', False)):
            self.app = Application(self.root)
        self.root.update_idletasks()
        self.assertIsNotNone(self.app.file_drop)
        self.addCleanup(self.cleanup_window)

    def settle(self):
        """Folders are read in a worker; wait for the import to finish."""
        import time
        deadline = time.monotonic() + 20
        while getattr(self.app, 'importing', False) and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.app.drain()   # the log lines of the import
        self.assertFalse(getattr(self.app, 'importing', False))

    def cleanup_window(self):
        def widgets(parent):
            yield parent
            for child in parent.winfo_children():
                yield from widgets(child)
        owners = {name: widget for widget in widgets(self.root)
                  for name in (widget._tclCommands or [])}
        for job in self.root.tk.call('after', 'info'):
            command = self.root.tk.call('after', 'info', job)[0]
            owners.get(command, self.root).after_cancel(job)
        self.root.destroy()
        self.assertFalse(self.app.file_drop.handles)

    def send_drop(self, widget, paths, *, wrapper=False, drain=True):
        """Supply the same Unicode HGLOBAL format Explorer sends; ownership transfers."""
        class DropFiles(ctypes.Structure):
            _fields_ = [('offset', wintypes.DWORD), ('point', wintypes.POINT),
                        ('nonclient', wintypes.BOOL), ('wide', wintypes.BOOL)]
        payload = ('\0'.join(map(str, paths)) + '\0\0').encode('utf-16-le')
        header = DropFiles(ctypes.sizeof(DropFiles), wintypes.POINT(0, 0), False, True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel.GlobalLock.restype = ctypes.c_void_p
        kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel.GlobalUnlock.restype = wintypes.BOOL
        kernel.GlobalFlags.argtypes = [wintypes.HGLOBAL]
        kernel.GlobalFlags.restype = wintypes.UINT
        user = self.app.file_drop.user
        user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        user.SendMessageW.restype = ctypes.c_ssize_t
        handle = kernel.GlobalAlloc(0x42, ctypes.sizeof(header) + len(payload))
        self.assertTrue(handle)
        address = kernel.GlobalLock(handle)
        self.assertTrue(address)
        ctypes.memmove(address, ctypes.byref(header), ctypes.sizeof(header))
        ctypes.memmove(address + ctypes.sizeof(header), payload, len(payload))
        kernel.GlobalUnlock(handle)
        hwnd = widget.winfo_id()
        if wrapper:
            hwnd = user.GetAncestor(hwnd, 2)
        self.assertIn(hwnd, self.app.file_drop.handles)
        self.assertEqual(user.SendMessageW(hwnd, 0x233, handle, 0), 0)
        self.assertEqual(kernel.GlobalFlags(handle), 0x8000, 'HDROP must be freed exactly once')
        if drain:
            self.app.drain()

    def fixture(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_native_drop_on_all_main_surfaces_and_duplicate_path(self):
        path = self.fixture('Cartouche été 日本.sms', bytes(8192))
        for widget, wrapper in ((self.root, True), (self.root, False),
                                (self.app.header, False), (self.app.table, False),
                                (self.app.empty_state, False), (self.app.empty_art, False),
                                (self.app.log, False)):
            with self.subTest(widget=widget, wrapper=wrapper):
                self.send_drop(widget, [path])
                self.assertEqual(len(self.app.items), 1)
        item = next(iter(self.app.items.values()))
        self.assertEqual((item.path, item.system, item.error), (path, 'sms', ''))
        self.assertEqual(self.app.status_key, 'drop_added')

    def test_mixed_folder_zip_unknown_and_all_six_consoles(self):
        from tools.snes_scheduler_selftest import cartridge
        sms = bytearray(32768)
        sms[0x7ff0:0x7ff8] = b'TMR SEGA'
        sms[0x7fff] = 0x4c
        gg = bytearray(sms)
        gg[0x7fff] = 0x6c
        gb = bytearray(32768)
        gb[0x134:0x138] = b'TEST'
        nes = b'NES\x1a' + bytes((1, 0)) + bytes(10) + bytes(16384)
        md = bytearray(32768)
        md[0x100:0x104] = b'SEGA'
        md[0x1f0:0x1f3] = b'JUE'
        files = [self.fixture(name, data) for name, data in
                 (('a.sms', sms), ('b.gg', gg), ('c.gb', gb), ('d.nes', nes),
                  ('e.md', md), ('f.sfc', cartridge(bytes.fromhex('40'))),
                  ('inconnue.gba', b'unsupported'), ('notes.txt', b'not a ROM'))]
        nested = self.folder / 'sous dossier'
        nested.mkdir()
        archive = nested / 'Jeu ZIP.zip'
        with ZipFile(archive, 'w') as target:
            target.writestr('a.sms', sms)
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in (*files, archive)}
        self.send_drop(self.app.table, [self.folder, files[0]])
        self.settle()
        self.assertEqual(len(self.app.items), 8)  # Six consoles + ZIP + unsupported ROM.
        valid = [item for item in self.app.items.values() if not item.error]
        self.assertEqual({item.system for item in valid}, {'sms', 'gg', 'gb', 'nes', 'md', 'snes'})
        self.assertEqual(len(valid), 7)
        self.assertTrue(any(item.unknown for item in self.app.items.values()))
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).digest() for p in before})
        self.assertFalse((self.folder / 'exports').exists())

    def test_manual_console_choice_still_rejects_mismatched_roms(self):
        self.app.system_mode = 'gb'
        path = self.fixture('Wrong console.sms', bytes(8192))
        self.send_drop(self.app.table, [path])
        item = next(iter(self.app.items.values()))
        self.assertTrue(item.skipped)
        self.assertEqual(item.system, 'sms')

    def test_busy_drop_is_consumed_without_mutating_batch(self):
        path = self.fixture('a.sms', bytes(8192))
        self.app.busy = True
        self.send_drop(self.app.table, [path], drain=False)
        self.app.busy = False  # Finishing a batch must not replay a rejected drop.
        self.app.drain()
        self.assertFalse(self.app.items)
        self.assertIn(tr('drop_blocked', 'en'), self.app.log.get('1.0', 'end'))

    def test_inaccessible_folder_does_not_discard_other_dropped_files(self):
        path = self.fixture('a.sms', bytes(8192))
        with patch_gui('discover_roms', side_effect=PermissionError('denied')):
            self.send_drop(self.app.table, [self.folder, path])
            self.settle()
        self.assertEqual(len(self.app.items), 1)
        self.assertIn(tr('drop_unreadable', 'en'), self.app.log.get('1.0', 'end'))


if __name__ == '__main__':
    unittest.main()
