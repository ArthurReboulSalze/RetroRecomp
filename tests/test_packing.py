"""UPX packing of validated games: Windows unchanged, Linux x86-64 packed and tested."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import packing
from retrorecomp.paths import ASSETS

ELF_X86_64 = b'\x7fELF\x02\x01\x01' + bytes(11) + (62).to_bytes(2, 'little')
# What packing.py asks of `os` on a POSIX machine, so compact_executable takes its Linux branch anywhere
# (patching os.name itself would make pathlib build the other platform's paths).
POSIX_OS = SimpleNamespace(name='posix', access=lambda *_: True, close=os.close, X_OK=os.X_OK)
ELF_ARM64 =b'\x7fELF\x02\x01\x01' + bytes(11) + (183).to_bytes(2, 'little')


class BundledPackerTests(unittest.TestCase):
    def test_both_packers_are_the_pinned_official_builds(self):
        windows = ASSETS / 'assets/tools/upx.exe'
        linux = ASSETS / packing.UPX_LINUX
        self.assertEqual(hashlib.sha256(windows.read_bytes()).hexdigest(), packing.UPX_SHA256)
        self.assertEqual(hashlib.sha256(linux.read_bytes()).hexdigest(), packing.UPX_LINUX_SHA256)
        header = linux.read_bytes()[:20]
        self.assertEqual((header[:6], header[18:20]), (ELF_X86_64[:6], ELF_X86_64[18:20]))

    def test_each_converter_bundles_only_its_own_packer(self):
        from tools.prepare_publication import BUNDLED_FILES, PACKER, PACKERS, PUBLIC_FILES
        self.assertTrue(PACKERS <= set(PUBLIC_FILES))
        self.assertEqual(BUNDLED_FILES & PACKERS, {PACKER})
        self.assertEqual(PACKER, 'assets/tools/upx.exe' if os.name == 'nt' else packing.UPX_LINUX)

    def test_only_the_x68000_generators_are_bundled_among_x68000_tools(self):
        from retrorecomp.x68000_conversion import SDK_TOOLS
        from tools.prepare_publication import BUNDLED_FILES, PUBLIC_FILES, X68000_SDK_TOOLS
        self.assertEqual(X68000_SDK_TOOLS, SDK_TOOLS)
        bundled = {name for name in BUNDLED_FILES if name.startswith('tools/x68000_')}
        self.assertEqual(bundled, {'tools/' + name for name in SDK_TOOLS})
        self.assertIn('tools/x68000_fixtures.py', PUBLIC_FILES)


class LinuxPackingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'Game'
        self.game.write_bytes(ELF_X86_64 + bytes(64) + b'native game')
        machine = patch('retrorecomp.packing.platform.machine', return_value='x86_64')
        machine.start()
        self.addCleanup(machine.stop)
        self.addCleanup(packing._UNPACKED_REASONS.clear)

    def run_packer(self, returncode=0, executable=True):
        calls = []
        def run(command, **options):
            calls.append((command, options))
            self.assertTrue(Path(command[0]).is_file())
            return SimpleNamespace(returncode=returncode, stdout='', stderr='upx: Game: CantPackException: test')
        with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                patch('retrorecomp.packing.os.access', return_value=executable):
            packing.compact_linux(self.game)
        return calls

    def test_x86_64_game_is_packed_at_level_9_then_tested(self):
        calls = self.run_packer()
        self.assertEqual([command[1:] for command, _ in calls],
                         [('-9', '-q', str(self.game)), ('-t', '-q', str(self.game))])
        self.assertEqual({Path(command[0]) for command, _ in calls}, {ASSETS / packing.UPX_LINUX})
        self.assertEqual({options['timeout'] for _, options in calls}, {packing.LINUX_TIMEOUT})

    def test_a_packer_without_its_execute_bit_runs_from_a_private_verified_copy(self):
        seen = []
        def run(command, **options):
            seen.append(Path(command[0]))
            self.assertEqual(hashlib.sha256(Path(command[0]).read_bytes()).hexdigest(), packing.UPX_LINUX_SHA256)
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                patch('retrorecomp.packing.os.access', return_value=False):
            packing.compact_linux(self.game)
        self.assertEqual(len(set(seen)), 1)
        self.assertEqual(seen[0].parent.parent, self.root)    # beside the game, never in /tmp
        self.assertFalse(seen[0].parent.exists())             # removed afterwards

    def scripted(self, outcomes, emit=None):
        """Run compact_linux with a fake UPX: `outcomes` maps a command ('pack' or 'test') to a
        (returncode, message) pair. Packing really rewrites the file, as UPX does. With `emit`,
        compact_executable runs as on a Linux machine instead (the log callback is its business)."""
        calls = []
        def run(command, **options):
            args = command[1:]
            kind = 'test' if '-t' in args else 'pack'
            calls.append(args[:-2])
            code, message = outcomes.get(kind, (0, ''))
            if kind == 'pack':
                Path(args[-1]).write_bytes(b'UPX! packed by upx')
            return SimpleNamespace(returncode=code, stdout='', stderr=message)
        with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                patch('retrorecomp.packing.os', POSIX_OS), \
                contextlib.redirect_stderr(io.StringIO()) as printed:
            outcome = packing.compact_linux(self.game) if emit is None else packing.compact_executable(self.game, emit)
        self.printed = printed.getvalue()
        return outcome, calls

    def test_a_game_packed_and_tested_reports_nothing_and_leaves_no_copy(self):
        outcome, calls = self.scripted({})
        self.assertIsNone(outcome)
        self.assertEqual(calls, [('-9',), ('-t',)])
        self.assertEqual(self.game.read_bytes(), b'UPX! packed by upx')
        self.assertEqual(list(self.root.iterdir()), [self.game])

    def test_a_packing_rejected_by_the_upx_test_is_replaced_by_the_game_as_built(self):
        # UPX 5.2.1 rejects valid NRV packings of some large ELFs (upx/upx issue 18937).
        original = self.game.read_bytes()
        message = f'upx-amd64_linux: {self.game}: Exception: compressed data violation'
        outcome, calls = self.scripted({'test': (1, message)})
        self.assertEqual(calls, [('-9',), ('-t',)])
        self.assertIn('could not pack and verify the executable (Exception: compressed data violation; upx/upx issue 18937)',
                      outcome['notice'])
        self.assertIn('published unpacked', outcome['notice'])
        self.assertEqual(self.game.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.game])

    def test_a_packer_that_cannot_pack_leaves_the_game_unpacked_too(self):
        original = self.game.read_bytes()
        outcome, calls = self.scripted({'pack': (2, 'upx: Game: CantPackException: test')})
        self.assertEqual(calls, [('-9',)])
        self.assertIn('CantPackException', outcome['notice'])
        self.assertNotIn('18937', outcome['notice'])
        self.assertEqual(self.game.read_bytes(), original)

    def test_a_timeout_is_a_game_left_unpacked_not_a_failed_conversion(self):
        original = self.game.read_bytes()
        with patch('retrorecomp.packing.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('upx', packing.LINUX_TIMEOUT)), \
                patch('retrorecomp.packing.os.access', return_value=True), \
                contextlib.redirect_stderr(io.StringIO()):
            outcome = packing.compact_linux(self.game)
        self.assertIn('timed out', outcome['notice'])
        self.assertEqual(self.game.read_bytes(), original)

    def test_a_packer_that_cannot_start_is_still_an_error(self):
        with patch('retrorecomp.packing.subprocess.run', side_effect=OSError('exec format error')), \
                patch('retrorecomp.packing.os.access', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'UPX could not compact or verify Game: exec format'):
                packing.compact_linux(self.game)
        self.assertEqual(list(self.root.iterdir()), [self.game])

    def test_the_notice_reaches_the_conversion_log_and_not_stderr(self):
        log = []
        outcome, calls = self.scripted({'test': (1, 'upx: Game: Exception: compressed data violation')}, emit=log.append)
        self.assertEqual(calls, [('-9',), ('-t',)])
        self.assertEqual(log, [outcome['notice']])
        self.assertIn('compressed data violation', log[0])
        self.assertEqual(self.printed, '')    # the command line shows the log line once, not twice

    def test_without_a_log_the_notice_goes_to_stderr_once(self):
        with patch('retrorecomp.packing.subprocess.run',
                   return_value=SimpleNamespace(returncode=1, stdout='', stderr='upx: Game: Exception: test')), \
                patch('retrorecomp.packing.os', POSIX_OS), \
                contextlib.redirect_stderr(io.StringIO()) as printed:
            outcome = packing.compact_executable(self.game)
        self.assertEqual(printed.getvalue(), outcome['notice'] + '\n')

    def test_a_game_packed_and_tested_says_nothing_to_the_log(self):
        log = []
        outcome, _ = self.scripted({}, emit=log.append)
        self.assertIsNone(outcome)
        self.assertEqual((log, self.printed), ([], ''))

    def test_the_report_says_why_a_game_was_published_unpacked(self):
        identity = packing.file_identity(self.game)
        # Packed and tested: the record says nothing more than before.
        self.scripted({})
        packed = packing.packing_record(identity, self.game)
        self.assertNotIn('unpacked_reason', packed)
        self.assertEqual(packed['level'], '-9')
        self.assertEqual(packed['compared_on'], 'unpacked build executable')
        # A conversion that replayed a packed copy (Neo Geo, CPS-1, X68000) says so.
        replayed = packing.packing_record(identity, self.game, packed_replayed=True)
        self.assertIn('packed copy replayed', replayed['compared_on'])
        # Published as built: the same unpacked bytes, with the reason.
        self.game.write_bytes(ELF_X86_64 + bytes(64) + b'native game')
        outcome, _ = self.scripted({'test': (1, 'upx: Game: Exception: compressed data violation')})
        record = packing.packing_record(identity, self.game)
        self.assertEqual((record['packed'], record['unpacked_reason']), (False, outcome['notice']))
        self.assertEqual(record['published']['sha256'], identity['sha256'])
        # Another executable has no reason.
        other = packing.packing_record({'bytes': 1, 'sha256': '0' * 64}, self.game)
        self.assertNotIn('unpacked_reason', other)

    def test_a_modified_packer_is_refused(self):
        with patch.object(packing, 'UPX_LINUX_SHA256', '0' * 64), \
                patch('retrorecomp.packing.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'integrity check'):
                packing.compact_linux(self.game)
        run.assert_not_called()

    def test_x68000_games_are_packed_like_every_console(self):
        # Its disks and firmware are linked into the program, not read from the file.
        self.game.write_bytes(ELF_X86_64 + bytes(1024 * 1024 - 30) + b'system/keropi/iplrom.dat\0' + bytes(16))
        calls = self.run_packer()
        self.assertEqual([command[1:] for command, _ in calls],
                         [('-9', '-q', str(self.game)), ('-t', '-q', str(self.game))])

    def test_other_architectures_stay_as_built(self):
        arm = self.root / 'Arm Game'
        arm.write_bytes(ELF_ARM64 + bytes(64))
        with patch('retrorecomp.packing.subprocess.run') as run:
            before = arm.read_bytes()
            packing.compact_linux(arm)
            self.assertEqual(arm.read_bytes(), before)
            with patch('retrorecomp.packing.platform.machine', return_value='aarch64'):
                packing.compact_linux(self.game)
        run.assert_not_called()

    def test_only_native_elves_are_accepted(self):
        self.game.write_bytes(b'MZ' + bytes(64))
        with self.assertRaisesRegex(RuntimeError, 'ELF'):
            packing.compact_linux(self.game)


@unittest.skipUnless(os.name == 'nt', 'Windows packing')
class WindowsPackingTests(unittest.TestCase):
    def test_windows_games_keep_the_same_upx_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(b'MZ')
            with patch('retrorecomp.packing.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
                packing.compact_executable(game)
        self.assertEqual([call.args[0][1:] for call in run.call_args_list],
                         [('-9', '--compress-resources=0', '--compress-icons=0', str(game)), ('-t', str(game))])
        self.assertEqual({Path(call.args[0][0]) for call in run.call_args_list}, {ASSETS / 'assets/tools/upx.exe'})
        for call in run.call_args_list:
            self.assertEqual((call.kwargs['timeout'], call.kwargs['creationflags']),
                             (packing.LINUX_TIMEOUT, subprocess.CREATE_NO_WINDOW))

    def test_the_limit_grows_with_the_executable(self):
        # A fixed 120 s stopped a large NES game packed while other conversions ran (1.6.5).
        with tempfile.TemporaryDirectory() as folder:
            small, large = Path(folder) / 'small.exe', Path(folder) / 'large.exe'
            small.write_bytes(b'MZ')
            with large.open('wb') as stream:
                stream.truncate(78_000_000)
            self.assertEqual(packing.upx_timeout(small), packing.LINUX_TIMEOUT)
            self.assertEqual(packing.upx_timeout(large), 780)
            self.assertEqual(packing.upx_timeout(Path(folder) / 'missing.exe'), packing.LINUX_TIMEOUT)


@unittest.skipUnless(platform.system() == 'Linux' and platform.machine() == 'x86_64' and shutil.which('cc'),
                     'Linux x86-64 with a C compiler')
class RealLinuxPackingTests(unittest.TestCase):
    def test_a_packed_program_still_runs_and_finds_its_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'game.c').write_text(
                '#include <stdio.h>\n#include <string.h>\n#include <unistd.h>\n'
                'static const char data[1 << 16] = "[Retro-Recomp] payload";\n'
                'int main(void){char b[4096];ssize_t n=readlink("/proc/self/exe",b,sizeof b-1);'
                'if(n<=0)return 3;b[n]=0;printf("%s|%s\\n",b,data);return 0;}\n', encoding='ascii')
            game = root / 'Game'
            subprocess.run(['cc', '-O2', str(root / 'game.c'), '-o', str(game)], check=True)
            raw = game.read_bytes()
            packing.compact_executable(game)
            self.assertLess(game.stat().st_size, len(raw))
            self.assertTrue(os.access(game, os.X_OK))
            output = subprocess.run([str(game)], capture_output=True, text=True, check=True).stdout
            self.assertEqual(output, f'{game}|[Retro-Recomp] payload\n')


if __name__ == '__main__':
    unittest.main()
