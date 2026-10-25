"""UPX packing of validated games: Windows unchanged, Linux x86-64 packed and tested."""
import hashlib
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
ELF_ARM64 = b'\x7fELF\x02\x01\x01' + bytes(11) + (183).to_bytes(2, 'little')


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

    def test_upx_failure_stops_publication(self):
        with self.assertRaisesRegex(RuntimeError, 'UPX could not compact or verify Game: .*CantPackException'):
            self.run_packer(returncode=2)

    def test_a_modified_packer_is_refused(self):
        with patch.object(packing, 'UPX_LINUX_SHA256', '0' * 64), \
                patch('retrorecomp.packing.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'integrity check'):
                packing.compact_linux(self.game)
        run.assert_not_called()

    def test_x68000_and_other_architectures_stay_as_built(self):
        x68000 = self.root / 'X68000 Game'
        # The payload table may straddle a read boundary.
        x68000.write_bytes(ELF_X86_64 + bytes(1024 * 1024 - 30) + b'system/keropi/iplrom.dat\0' + bytes(16))
        arm = self.root / 'Arm Game'
        arm.write_bytes(ELF_ARM64 + bytes(64))
        with patch('retrorecomp.packing.subprocess.run') as run:
            for path in (x68000, arm):
                before = path.read_bytes()
                packing.compact_linux(path)
                self.assertEqual(path.read_bytes(), before)
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
            self.assertEqual((call.kwargs['timeout'], call.kwargs['creationflags']), (120, subprocess.CREATE_NO_WINDOW))


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
