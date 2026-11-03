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


def make_pe(code: bytes, size_of_code=None, magic=0x20B, virtual_size=None) -> bytes:
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
    struct.pack_into('<IIII', header, table + 8, virtual_size or len(code), 0x1000, len(code), 0x400)
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
        located = packing._pe_code(make_pe(bytes(64)))
        self.assertEqual(located, (SIZE_OF_CODE_FIELD, 64, 0x400, 0, 64))
        # UPX reads min(SizeOfRawData, VirtualSize) bytes of a section (pefile.cpp).
        self.assertEqual(packing._pe_code(make_pe(bytes(64), virtual_size=40))[4], 40)

    def test_what_is_past_the_virtual_size_is_zeros_for_upx(self):
        # The raw tail of a section past its VirtualSize is not read by UPX (zero fill): a call there takes no value.
        code = saturated_code(late_at=7000, size=8192)
        self.assertEqual(spare_values(code, len(code)), [])
        length, value = packing.call_filter_length(make_pe(code, virtual_size=6500))
        self.assertEqual((length, value), (len(code), 7))
        length, _ = packing.call_filter_length(make_pe(code))
        self.assertEqual(length, 7000 + 5)

    def test_the_length_is_capped_by_addvalue_and_by_the_largest_buffer_of_the_filter(self):
        # Targets inside the filtered part must stay under 2**24 with addvalue (ctok.h), and UPX does not filter a
        # buffer over max_buf_len 0x00ffffff (filter_impl.cpp).
        code = saturated_code()
        field = SIZE_OF_CODE_FIELD
        with patch.object(packing, '_pe_code', return_value=(field, len(code), 0x400, (1 << 24) - 4100, len(code))):
            self.assertEqual(packing.call_filter_length(make_pe(code)), (4100, 7))      # the late value, free below 4102
        with patch.object(packing, '_pe_code', return_value=(field, 1 << 24, 0x400, 0, 1 << 24)):
            self.assertEqual(packing.call_filter_length(bytes(0x400 + (1 << 24))), (0xFFFFFF, 0))


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

    def test_the_linux_method_is_one_constant_and_changes_nothing_while_it_is_nrv(self):
        self.assertEqual((packing.LINUX_METHOD, packing.WINDOWS_METHOD), ('nrv', 'lzma'))
        self.assertEqual(packing.METHOD_FLAGS, {'nrv': (), 'lzma': ('--lzma',)})
        with patch.object(packing, 'LINUX_METHOD', 'lzma'):
            calls = self.run_packer()
        self.assertEqual([command[1:] for command, _ in calls],
                         [('-9', '--lzma', '-q', str(self.game)), ('-t', '-q', str(self.game))])
        with patch('retrorecomp.packing.os', POSIX_OS):
            self.assertEqual(packing.packing_method(), 'nrv')
        self.game.write_bytes(b'UPX! packed')
        with patch('retrorecomp.packing.os', POSIX_OS):
            self.assertEqual(packing.packing_record({'bytes': 1, 'sha256': '0' * 64}, self.game)['method'], 'nrv')

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
    def setUp(self):
        self.addCleanup(packing._CALL_FILTER_USED.clear)

    def test_windows_games_are_packed_with_lzma_and_the_same_other_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(b'MZ')
            with patch('retrorecomp.packing.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
                packing.compact_executable(game)
        self.assertEqual([call.args[0][1:] for call in run.call_args_list],
                         [('-9', '--lzma', '--compress-resources=0', '--compress-icons=0', str(game)), ('-t', str(game))])
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
            with patch('retrorecomp.packing.subprocess.run', side_effect=run) as runner, \
                    patch('retrorecomp.packing.time.sleep') as sleep:
                outcome = packing.compact_executable(game, emit=log.append)
            self.assertEqual(runner.call_count, 2)      # the identical pack, once more after the wait (1.6.7)
            sleep.assert_called_once_with(packing.DEFENDER_RETRY_WAIT)
            self.assertEqual(game.read_bytes(), b'MZ validated build')
            self.assertIn('published unpacked', outcome['notice'])
            self.assertIn('antivirus', outcome['notice'])
            self.assertEqual(log, [outcome['notice']])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])

    def script_defender(self, game, blocked):
        """A fake UPX for the plain build: pack number n (1-based) fails like a Defender removal when n is in `blocked`.
        Returns (the commands run with the SizeOfCode and the bytes the file had when each started, the run function)."""
        started = []
        def run(command, **options):
            data = Path(command[-1]).read_bytes()
            started.append((command[1:], struct.unpack_from('<I', data, SIZE_OF_CODE_FIELD)[0], data[:2] == b'MZ'))
            if command[1] == '--fileinfo':
                return SimpleNamespace(returncode=0, stderr='', stdout='x [amd64-win64.pe, win64/pe]\n  1 bytes, filter 0x49/0x57\n')
            if command[1] == '-9':
                if len([call for call in started if call[0][0] == '-9']) in blocked:
                    Path(command[-1]).write_bytes(b'MZ half-written')
                    return SimpleNamespace(returncode=1, stdout='', stderr=f'upx: {game}: IOException: {game}: Invalid argument')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        return started, run

    def test_an_antivirus_removal_is_retried_once_with_the_identical_command(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            built = make_pe(bytes(64))                 # nothing for the call filter: the plain attempt only
            game.write_bytes(built)
            started, run = self.script_defender(game, blocked={1})
            with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                    patch('retrorecomp.packing.time.sleep') as sleep:
                self.assertIsNone(packing.compact_executable(game, emit=lambda text: self.fail(text)))
            commands = [call[0] for call in started]
            self.assertEqual(commands, [('-9', '--lzma', '--compress-resources=0', '--compress-icons=0', str(game)),
                                        ('-9', '--lzma', '--compress-resources=0', '--compress-icons=0', str(game)),
                                        ('-t', str(game))])
            self.assertEqual(started[1][1:], (len(bytes(64)), True))      # the validated build was put back first
            sleep.assert_called_once_with(packing.DEFENDER_RETRY_WAIT)
            self.assertEqual(game.read_bytes(), built)                     # the fake UPX left the build as it got it
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])

    def test_a_second_removal_leaves_the_game_as_built_after_one_retry_only(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            built = make_pe(bytes(64))
            game.write_bytes(built)
            started, run = self.script_defender(game, blocked={1, 2, 3})
            with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                    patch('retrorecomp.packing.time.sleep') as sleep:
                outcome = packing.compact_executable(game, emit=lambda text: None)
            self.assertEqual(len(started), 2)                  # one attempt and one retry, never a third
            self.assertEqual(started[0][0], started[1][0])     # the same command, no other option
            self.assertEqual(sleep.call_count, 1)
            self.assertIn('antivirus', outcome['notice'])
            self.assertEqual(game.read_bytes(), built)

    def test_another_failure_is_not_retried_and_nothing_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(make_pe(bytes(64)))
            def run(command, **options):
                return SimpleNamespace(returncode=1, stdout='', stderr='upx: Game.exe: CantPackException: test')
            with patch('retrorecomp.packing.subprocess.run', side_effect=run) as runner, \
                    patch('retrorecomp.packing.time.sleep') as sleep:
                packing.compact_executable(game, emit=lambda text: None)
            self.assertEqual(runner.call_count, 1)
            sleep.assert_not_called()

    def test_the_retry_of_the_call_filter_attempt_repeats_its_header_and_a_second_removal_stops_there(self):
        # The antivirus removed the output of the shortened-SizeOfCode attempt twice: the plain form of the same
        # build is not tried to get past it.
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            built = game.read_bytes()
            started, run = self.script_defender(game, blocked={1, 2})
            with patch('retrorecomp.packing.subprocess.run', side_effect=run), \
                    patch('retrorecomp.packing.time.sleep') as sleep:
                outcome = packing.compact_executable(game, emit=lambda text: None)
            self.assertEqual([call[1] for call in started], [4101, 4101])     # both with the prefix, no plain attempt
            self.assertEqual(sleep.call_count, 1)
            self.assertIn('antivirus', outcome['notice'])
            self.assertEqual(game.read_bytes(), built)
            self.assertNotIn(hashlib.sha256(built).hexdigest(), packing._CALL_FILTER_USED)

    def test_the_retry_of_the_call_filter_attempt_can_succeed(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            started, run = self.script_defender(game, blocked={1})
            with patch('retrorecomp.packing.subprocess.run', side_effect=run), patch('retrorecomp.packing.time.sleep'):
                self.assertIsNone(packing.compact_executable(game, emit=lambda text: None))
            self.assertEqual([(call[0][0], call[1]) for call in started],
                             [('-9', 4101), ('-9', 4101), ('-t', 4101), ('--fileinfo', 4101)])
            self.assertIn(hashlib.sha256(make_pe(saturated_code())).hexdigest(), packing._CALL_FILTER_USED)

    def test_the_report_names_the_method_of_a_packed_game(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Game.exe'
            game.write_bytes(b'MZ UPX! packed')
            identity = {'bytes': 100, 'sha256': '0' * 64}
            self.assertEqual(packing.packing_record(identity, game)['method'], 'lzma')
            game.write_bytes(b'MZ as built')
            self.assertIsNone(packing.packing_record(identity, game)['method'])      # not packed: no method

    # The suite does not run UPX itself here: subprocess.run is replaced by a script that plays UPX (pack, test and
    # --fileinfo) and records what the game's SizeOfCode was at each call. The real UPX was run on real builds by hand.
    def play_upx(self, game, filters=('0x49',), pack_fails=False):
        """A fake UPX: (the list of (argument, SizeOfCode seen) calls, the run function). The n-th --fileinfo says filters[n]."""
        seen = []
        def run(command, **options):
            argument = command[1]
            seen.append((argument, struct.unpack_from('<I', Path(command[-1]).read_bytes(), SIZE_OF_CODE_FIELD)[0]))
            if argument == '--fileinfo':
                said = filters[len([call for call in seen if call[0] == '--fileinfo']) - 1]
                return SimpleNamespace(returncode=0, stderr='', stdout=(
                    'game.exe [amd64-win64.pe, win64/pe]' + chr(10) + '   1328128 bytes, compressed by UPX 13, method 8, level 9, '
                    f'filter {said}/0x57' + chr(10)))
            failing = pack_fails and argument == '-9' and len([call for call in seen if call[0] == '-9']) == 1
            return SimpleNamespace(returncode=1 if failing else 0, stdout='',
                                   stderr='upx: Game.exe: CantPackException: test' if failing else '')
        return seen, run

    def staged(self, folder):
        game = Path(folder) / 'Game.exe'
        game.write_bytes(make_pe(saturated_code()))
        return game

    def test_a_build_that_loses_the_call_filter_is_packed_with_the_longest_filterable_length(self):
        # 1.6.6: the Super Mario Land build used the last spare value, UPX found no filter and the game grew by 24 %.
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            seen, run = self.play_upx(game)
            log = []
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                self.assertIsNone(packing.compact_executable(game, emit=log.append))
            self.assertEqual(seen, [('-9', 4101), ('-t', 4101), ('--fileinfo', 4101)])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])
            self.assertEqual(len(log), 1)
            self.assertIn('call filter kept over 50 % of the code (4101 of 8192 bytes)', log[0])
            # The report says it: only for a packed game, and only for the build that used it.
            build = make_pe(saturated_code())
            identity = {'bytes': len(build), 'sha256': hashlib.sha256(build).hexdigest()}
            game.write_bytes(b'MZ UPX! the packed game')      # what the fake UPX did not write
            record = packing.packing_record(identity, game)
            self.assertEqual(record['call_filter'], {'filter': '0x49', 'code_bytes': 8192, 'filtered_bytes': 4101})
            self.assertNotIn('call_filter', packing.packing_record({'bytes': 1, 'sha256': '0' * 64}, game))

    def test_a_packed_file_without_the_call_filter_is_replaced_by_the_plain_attempt(self):
        # Seen for real: UPX returned 0, `upx -t` passed and the file had filter 0x00 and was 7 % larger.
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            seen, run = self.play_upx(game, filters=('0x00', '0x49'))
            log = []
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                self.assertIsNone(packing.compact_executable(game, emit=log.append))
            self.assertEqual(seen, [('-9', 4101), ('-t', 4101), ('--fileinfo', 4101), ('-9', 8192), ('-t', 8192)])
            self.assertEqual(log, [])
            self.assertNotIn(hashlib.sha256(make_pe(saturated_code())).hexdigest(), packing._CALL_FILTER_USED)

    def test_the_note_of_an_earlier_packing_is_not_kept_when_the_next_one_falls_back(self):
        # The conversion and the publication pack the same build in one process: the report must say what the last one did.
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            build = game.read_bytes()
            seen, run = self.play_upx(game)
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                packing.compact_executable(game)
            self.assertIn(hashlib.sha256(build).hexdigest(), packing._CALL_FILTER_USED)
            game.write_bytes(build)
            seen, run = self.play_upx(game, filters=('0x00',))
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                packing.compact_executable(game)
            self.assertNotIn(hashlib.sha256(build).hexdigest(), packing._CALL_FILTER_USED)

    def test_when_the_shorter_length_fails_the_build_is_packed_as_before(self):
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            seen, run = self.play_upx(game, pack_fails=True)
            with patch('retrorecomp.packing.subprocess.run', side_effect=run):
                self.assertIsNone(packing.compact_executable(game))
            self.assertEqual(seen, [('-9', 4101), ('-9', 8192), ('-t', 8192)])

    def test_a_staged_copy_that_cannot_be_patched_is_packed_as_before(self):
        # The antivirus may remove or lock the staged copy: the conversion must not fail on the header write.
        with tempfile.TemporaryDirectory() as folder:
            game = self.staged(folder)
            seen, run = self.play_upx(game)
            with patch('retrorecomp.packing.subprocess.run', side_effect=run),                     patch('retrorecomp.packing._set_size_of_code', side_effect=PermissionError('locked')):
                self.assertIsNone(packing.compact_executable(game))
            self.assertEqual(seen, [('-9', 8192), ('-t', 8192)])
            self.assertEqual([path.name for path in Path(folder).iterdir()], ['Game.exe'])

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
