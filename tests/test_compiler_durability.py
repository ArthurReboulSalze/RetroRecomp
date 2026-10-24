"""ROM-free regression cases for shared caches, filenames and learning writes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Barrier
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp.core import executable_name, module_fingerprint
from retrorecomp.library import atomic_text, entry_lock


class CompilerDurabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_source_and_loaded_code_share_the_same_identity(self):
        source = "def f(x):\n return x in {'alpha', 'beta', 'gamma'}\n"
        path = self.root / 'adapter.py'
        path.write_text(source)
        code = compile(source, 'temporary-bundle/adapter.py', 'exec')
        module = SimpleNamespace(__file__=str(path),
                                 __loader__=SimpleNamespace(get_code=lambda name: code))
        with patch.dict(sys.modules, {'authored_adapter': module}):
            original = module_fingerprint('authored_adapter')
            path.unlink()
            self.assertEqual(module_fingerprint('authored_adapter'), original)
            code = compile(source.replace('gamma', 'delta'), 'temporary-bundle/adapter.py', 'exec')
            self.assertNotEqual(module_fingerprint('authored_adapter'), original)

    def test_loader_constant_aliases_do_not_invalidate_identical_code(self):
        code = compile('def f():\n return 42\n', '', 'exec')
        text = 'constant with spaces ' * 8
        alias = text.encode().decode()
        self.assertIsNot(text, alias)
        code = code.replace(co_consts=code.co_consts + (text, text))
        module = SimpleNamespace(__file__='',
                                 __loader__=SimpleNamespace(get_code=lambda name: code))
        with patch.dict(sys.modules, {'authored_adapter': module}):
            original = module_fingerprint('authored_adapter')
            code = code.replace(co_consts=code.co_consts[:-1] + (alias,))
            self.assertEqual(module_fingerprint('authored_adapter'), original)

    def test_long_titles_reserve_a_distinct_suffix_on_both_hosts(self):
        for host in ('nt', 'posix'):
            with self.subTest(host=host), patch('retrorecomp.core.os.name', host):
                title = 'Very long title ' * 30
                names = [executable_name(title, suffix=f' ({n})') for n in range(2, 10)]
                self.assertEqual(len(set(names)), 8)
                self.assertTrue(all(len(name) <= 154 for name in names))
                unicode_name = executable_name('日本語游戏🎮' * 40, suffix=' (2)')
                self.assertTrue(unicode_name.endswith(' (2).exe' if host == 'nt' else ' (2)'))
                if host != 'nt':
                    self.assertLessEqual(len(unicode_name.encode('utf-8')), 240)
                else:
                    self.assertLessEqual(len(executable_name('🎮' * 150, suffix=' (2)').encode('utf-16-le')), 308)

    def test_name_reservation_terminates_and_preserves_existing_files(self):
        from retrorecomp.batch import BatchItem, _OutputNames, export_target
        title = 'Long name ' * 35
        item = BatchItem(self.root / 'authored.sms', title, 'sms', 'a' * 64)
        old = self.root / executable_name(title)
        old.write_bytes(b'unrelated user file')
        names = _OutputNames(self.root)
        target, retired = names.reserve(item)
        self.assertEqual(target.name, executable_name(title, suffix=' (2)'))
        self.assertEqual(retired, [])
        self.assertEqual(export_target(item, self.root), target)
        other, _ = names.reserve(BatchItem(item.path, title, 'sms', 'b' * 64))
        self.assertEqual(other.name, executable_name(title, suffix=' (3)'))
        self.assertEqual(old.read_bytes(), b'unrelated user file')

    def test_streamed_export_identity_matches_the_complete_file_rules(self):
        from retrorecomp.batch import _embedded_export_identity
        def original(data):
            if not data.startswith((b'MZ', b'\x7fELF')) or b'[Retro-Recomp]' not in data:
                return None
            marked = set(re.findall(rb'\[Retro-Recomp\]\x00([0-9a-f]{64})\x00', data))
            if marked:
                return next(iter(marked)).decode() if len(marked) == 1 else None
            legacy = set(re.findall(rb'(?<![0-9a-f])([0-9a-f]{64})\x00', data))
            return next(iter(legacy)).decode() if len(legacy) == 1 else None
        path = self.root / 'authored-binary'
        mark = b'[Retro-Recomp]\0' + b'a' * 64 + b'\0'
        for header in (b'MZ\0\0', b'\x7fELF'):
            for offset in (-95, -79, -65, -15, -1, 0, 1, 15):
                for tail in (mark, mark + b'b' * 64 + b'\0',
                             mark + mark.replace(b'a', b'b'),
                             b'[Retro-Recomp]padding!' + b'a' * 64 + b'\0',
                             b'[Retro-Recomp]!' + b'a' * 160 + b'\0'):
                    data = header + b'\xff' * (1024 * 1024 + offset) + tail
                    path.write_bytes(data)
                    with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded binary read')):
                        self.assertEqual(_embedded_export_identity(path), original(data))

    def test_lock_timeout_and_release_across_real_processes(self):
        script = ('import sys\nfrom pathlib import Path\nfrom retrorecomp.library import entry_lock\n'
                  'with entry_lock(Path(sys.argv[1])):\n print("locked",flush=True)\n sys.stdin.read()\n')
        child = subprocess.Popen([sys.executable, '-c', script, str(self.root)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'locked')
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                with entry_lock(self.root, timeout=.08):
                    self.fail('Acquired a lock held by another process')
            self.assertLess(time.monotonic() - start, 3)
        finally:
            child.communicate('', timeout=5)
        self.assertEqual(child.returncode, 0)
        with entry_lock(self.root, timeout=0):
            pass

    def test_atomic_trace_failure_keeps_previous_observations(self):
        path = self.root / 'entries.trace'
        atomic_text(path, 'old entries\n')
        with patch('retrorecomp.library.os.replace', side_effect=OSError('authored disk failure')):
            with self.assertRaises(OSError):
                atomic_text(path, 'new entries\n')
        self.assertEqual(path.read_text(), 'old entries\n')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_gameboy_concurrent_memory_merges_do_not_lose_entries(self):
        from retrorecomp.gameboy import GameBoyRom, _remember_trace, _verified_trace
        from retrorecomp.gameboy_coverage import read_entries, write_entries
        data = bytes(65536)
        rom = GameBoyRom(self.root / 'authored.gb', data, 0, hashlib.sha256(data).hexdigest(), 'TEST', 0)
        traces = []
        for i in range(8):
            path = self.root / f'{i}.trace'
            write_entries(path, {(1, 0x4000 + i)})
            traces.append(path)
        barrier = Barrier(8)
        def work(path):
            barrier.wait(timeout=5)
            _remember_trace(rom, path)
        with patch('retrorecomp.gameboy.library_root', return_value=self.root / 'library'):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(work, traces))
            stored = _verified_trace(rom)
            self.assertEqual(read_entries(stored, len(data)), {(1, 0x4000 + i) for i in range(8)})
            stamp = stored.stat().st_mtime_ns
            _remember_trace(rom, traces[0])
            self.assertEqual(stored.stat().st_mtime_ns, stamp)

    def test_gameboy_interrupted_manifest_commit_preserves_verified_memory(self):
        from retrorecomp.gameboy import GameBoyRom, _remember_trace, _verified_trace, list_memory
        from retrorecomp.gameboy_coverage import read_entries, write_entries
        data = bytes(65536)
        rom = GameBoyRom(self.root / 'authored.gb', data, 0, hashlib.sha256(data).hexdigest(), 'TEST', 0)
        trace = self.root / 'observed.trace'
        with patch('retrorecomp.gameboy.library_root', return_value=self.root / 'library'):
            write_entries(trace, {(1, 0x4000)})
            _remember_trace(rom, trace)
            write_entries(trace, {(2, 0x5000)})
            with patch('retrorecomp.gameboy.atomic_json', side_effect=OSError('interrupted manifest commit')):
                with self.assertRaises(OSError):
                    _remember_trace(rom, trace)
            recovered = _verified_trace(rom)
            self.assertEqual(recovered.name, 'entries.trace.previous')
            self.assertEqual(read_entries(recovered, len(data)), {(1, 0x4000)})
            self.assertEqual(len(list_memory()), 1)
            _remember_trace(rom, trace)
            self.assertEqual(read_entries(_verified_trace(rom), len(data)), {(1, 0x4000), (2, 0x5000)})
            self.assertFalse(recovered.exists())

    def test_nes_keeps_late_discoveries_and_ram_guards_from_other_conversions(self):
        from retrorecomp.nes import _remember_seed, _seed_sites
        from retrorecomp.nes_ram import read_sites, trace_text
        traces = []
        target = self.root / 'library/rom/revision/cycle-seeds.trace'
        target.parent.mkdir(parents=True)
        target.write_text('4k:1:8123\n# ram:0300:EA\n')
        for i in range(8):
            path = self.root / f'{i}.trace'
            path.write_text(trace_text({f'4k:0:{0x8100+i:04X}'}, {(0x400+i, 0xA9)}))
            traces.append(path)
        barrier = Barrier(8)
        def work(path):
            barrier.wait(timeout=5)
            _remember_seed(path, target)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, traces))
        self.assertEqual(_seed_sites(target), {'4k:1:8123'} | {f'4k:0:{0x8100+i:04X}' for i in range(8)})
        self.assertEqual(read_sites(target), {(0x300, 0xEA)} | {(0x400+i, 0xA9) for i in range(8)})


if __name__ == '__main__':
    unittest.main()
