"""UPX packing of validated games: Windows unchanged, Linux x86-64 packed and tested."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import platform
import random
import shutil
import struct
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


def make_pe(code: bytes, size_of_code=None, magic=0x20B) -> bytes:
    """A minimal 64-bit PE: one .text section holding `code` at RVA 0x1000, raw data at 0x400."""
    header = bytearray(0x400)
    header[0:2] = b'MZ'
    struct.pack_into('<I', header, 0x3C, 0x80)
    header[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', header, 0x84, 0x8664, 1)
    struct.pack_into('<H', header, 0x80 + 20, 0xF0)
    optional = 0x80 + 24
    struct.pack_into('<H', header, optional, magic)
    struct.pack_into('<I', header, optional + 4, size_of_code or len(code))
    struct.pack_into('<I', header, optional + 20, 0x1000)
    table = optional + 0xF0
    header[table:table + 8] = b'.text\0\0\0'
    struct.pack_into('<IIII', header, table + 8, len(code), 0x1000, len(code), 0x400)
    return bytes(header) + code


SIZE_OF_CODE_FIELD = 0x80 + 24 + 4


def saturated_code(late_value=7, late_at=4096, size=8192) -> bytes:
    """Code in which every byte value is the first operand byte of an E8 that leaves the code, `late_value` only at `late_at`."""
    code = bytearray(size)
    for value in range(256):
        if value != late_value:
            code[16 * value:16 * value + 5] = bytes((0xE8, value, 0x7F, 0x7F, 0x7F))
    code[late_at:late_at + 5] = bytes((0xE8, late_value, 0x7F, 0x7F, 0x7F))
    return bytes(code)


def spare_values(code: bytes, length: int) -> list[int]:
    """The cto values UPX's call-trick scan (src/filter/ctok.h) leaves free over the first `length` bytes, by brute force."""
    taken = set()
    for position in range(length - 5):
        if code[position] in (0xE8, 0xE9) or (position and code[position - 1] == 0x0F and 0x80 <= code[position] <= 0x8F):
            target = (struct.unpack_from('<I', code, position + 1)[0] + position + 1) & 0xFFFFFFFF
            if target >= length:
                taken.add(code[position + 1])
    return [value for value in range(256) if value not in taken]


class CallFilterModelTests(unittest.TestCase):
    """packing.call_filter_length: the longest part of the code over which UPX's call-trick filter keeps a spare byte."""

    def test_a_value_used_late_frees_the_part_of_the_code_before_it(self):
        code = saturated_code()
        self.assertEqual(spare_values(code, len(code)), [])
        length, value = packing.call_filter_length(make_pe(code))
        self.assertEqual((length, value), (4096 + 5, 7))
        self.assertEqual(spare_values(code, length), [7])
        self.assertEqual(spare_values(code, length + 1), [])

    def test_code_with_a_spare_value_is_left_whole(self):
        code = bytearray(saturated_code())
        code[16 * 9:16 * 9 + 5] = bytes(5)        # nobody uses 9 any more
        length, value = packing.call_filter_length(make_pe(bytes(code)))
        self.assertEqual((length, value), (len(code), 9))
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(make_pe(bytes(code)))
            self.assertIsNone(packing._call_filter_prefix(game))

    def test_a_call_across_the_end_of_the_length_takes_its_value_back(self):
        # An E8 with the late value whose target lies beyond the length takes the value back for every longer length.
        code = bytearray(saturated_code())
        code[4008:4013] = bytes((0xE8, 7, 0x10, 0x00, 0x00))     # target 4008 + 5 + 0x1007 - 4: past the first 4101 bytes
        length, value = packing.call_filter_length(make_pe(bytes(code)))
        self.assertLess(length, 4096 + 5)
        self.assertIn(value, spare_values(bytes(code), length))
        self.assertEqual(spare_values(bytes(code), length + 1), [])

    def test_the_model_matches_a_brute_force_scan_on_random_code(self):
        rng = random.Random(167)
        for _ in range(40):
            size = rng.randrange(600, 2600)
            code = bytes(rng.choice((0xE8, 0xE9, 0x0F, 0x85, 0x00, 0xFF, rng.randrange(256))) if rng.random() < 0.6 else rng.randrange(256)
                         for _ in range(size))
            expected = max((length for length in range(6, size + 1) if spare_values(code, length)), default=0)
            found = packing.call_filter_length(make_pe(code))
            self.assertEqual(found[0] if found else 0, expected)
            if found:
                self.assertIn(found[1], spare_values(code, found[0]))

    def test_the_8x_byte_of_a_conditional_jump_takes_its_value_too(self):
        # 0F 85 rel32 (JNE) is a candidate of filter 0x49 like E8 and E9: its first operand byte is taken.
        code = bytearray(saturated_code())
        code[16 * 9:16 * 9 + 5] = bytes(5)                              # 9 would be spare ...
        code[5000:5006] = bytes((0x0F, 0x85, 9, 0x7F, 0x7F, 0x7F))      # ... but a jump uses it, outside the code
        length, value = packing.call_filter_length(make_pe(bytes(code)))
        self.assertLess(length, len(code))
        self.assertIn(value, spare_values(bytes(code), length))
        self.assertEqual(spare_values(bytes(code), length + 1), [])

    def test_the_header_gives_the_start_and_the_addvalue_of_the_code(self):
        field, size, start, addvalue = packing._pe_code(make_pe(bytes(64)))
        self.assertEqual((field, size, start, addvalue), (SIZE_OF_CODE_FIELD, 64, 0x400, 0))

    def test_only_a_64_bit_pe_is_read(self):
        self.assertIsNone(packing.call_filter_length(b'MZ'))
        self.assertIsNone(packing.call_filter_length(b'\x7fELF' + bytes(100)))
        self.assertIsNone(packing.call_filter_length(make_pe(bytes(64), magic=0x10B)))
        self.assertIsNone(packing.call_filter_length(make_pe(bytes(64), size_of_code=1 << 20)))   # larger than its section
        self.assertIsNone(packing.call_filter_length(make_pe(bytes(64))[:0x300]))

    def test_a_short_filtered_part_is_not_worth_a_new_header(self):
        code = saturated_code(late_at=16 * 256 + 100, size=60000)
        length, _ = packing.call_filter_length(make_pe(code))
        self.assertLess(length * packing.CALL_FILTER_MIN_SHARE, len(code))
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(make_pe(code))
            self.assertIsNone(packing._call_filter_prefix(game))

    def test_size_of_code_is_the_only_header_field_that_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            built = make_pe(saturated_code())
            game.write_bytes(built)
            self.assertEqual(packing._call_filter_prefix(game), 4101)
            packing._set_size_of_code(game, 4101)
            changed = game.read_bytes()
            self.assertEqual(len(changed), len(built))
            self.assertEqual([i for i in range(len(built)) if built[i] != changed[i]],
                             [SIZE_OF_CODE_FIELD, SIZE_OF_CODE_FIELD + 1])
            self.assertEqual(struct.unpack_from('<I', changed, SIZE_OF_CODE_FIELD)[0], 4101)


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

    def test_a_windows_game_upx_cannot_pack_is_published_unpacked_not_failed(self):
        # Windows Defender removed UPX's temporary output (1.6.6): the conversion must not fail.
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(b'MZ validated build')
            def run(command, **options):
                game.write_bytes(b'MZ half-written')   # what UPX leaves behind
                return SimpleNamespace(returncode=1, stdout='',
                                       stderr=f'upx: {game}: IOException: {game}: Invalid argument')
            log = []
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                outcome = packing.compact_executable(game, emit=log.append)
            self.assertEqual(game.read_bytes(), b'MZ validated build')
            self.assertIn('published unpacked', outcome['notice'])
            self.assertIn('antivirus', outcome['notice'])
            self.assertEqual(log, [outcome['notice']])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])

    def test_a_build_that_loses_the_call_filter_is_packed_with_the_longest_filterable_length(self):
        # 1.6.6: the Super Mario Land build used the last spare value, UPX found no filter and the game grew by 24 %.
        built = make_pe(saturated_code())
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(built)
            seen = []
            def run(command, **options):
                seen.append((command[1], struct.unpack_from('<I', Path(command[-1]).read_bytes(), SIZE_OF_CODE_FIELD)[0]))
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                self.assertIsNone(packing.compact_executable(game))
            self.assertEqual(seen, [('-9', 4101), ('-t', 4101)])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])

    def test_when_the_shorter_length_fails_the_build_is_packed_as_before(self):
        built = make_pe(saturated_code())
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(built)
            seen = []
            def run(command, **options):
                seen.append((command[1], struct.unpack_from('<I', Path(command[-1]).read_bytes(), SIZE_OF_CODE_FIELD)[0]))
                failing = len(seen) == 1           # the first pack (shorter length) fails, the next ones succeed
                return SimpleNamespace(returncode=1 if failing else 0, stdout='', stderr='upx: Game.exe: CantPackException: test')
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                self.assertIsNone(packing.compact_executable(game))
            self.assertEqual(seen, [('-9', 4101), ('-9', 8192), ('-t', 8192)])

    def test_when_every_attempt_fails_the_game_is_published_as_built(self):
        built = make_pe(saturated_code())
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(built)
            def run(command, **options):
                Path(command[-1]).write_bytes(b'MZ half-written')
                return SimpleNamespace(returncode=1, stdout='', stderr='upx: Game.exe: CantPackException: test')
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                outcome = packing.compact_executable(game, emit=lambda text: None)
            self.assertIn('published unpacked', outcome['notice'])
            self.assertEqual(game.read_bytes(), built)

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
