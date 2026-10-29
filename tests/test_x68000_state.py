"""Compile the actual C envelope; run save/load in distinct fresh processes."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StateStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        cls.build_temp = tempfile.TemporaryDirectory(prefix='rr-x68000-state-')
        cls.project = Path(cls.build_temp.name)
        source = (ROOT / 'native/x68000_reference').as_posix()
        (cls.project / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(StateStoreFixtures LANGUAGES C)\n'
            'set(CMAKE_C_STANDARD 11)\n'
            f'add_executable(state-test "{source}/state_store.c" '
            f'"{source}/state_store_test.c")\n'
            'if(MSVC)\n'
            'target_compile_options(state-test PRIVATE /W4 /WX /utf-8)\n'
            'target_compile_definitions(state-test PRIVATE _CRT_SECURE_NO_WARNINGS)\n'
            'else()\n'
            'target_compile_options(state-test PRIVATE -Wall -Wextra -Werror)\n'
            'endif()\n'
            # The fixture's Windows entry point is wmain: MinGW (the portable llvm-mingw) links it with -municode.
            'if(MINGW)\n'
            'target_link_options(state-test PRIVATE -municode)\n'
            'endif()\n', encoding='utf-8')
        cmake, generator = toolchain()
        for command in (
            [str(cmake), '-S', str(cls.project), '-B', str(cls.project / 'build'),
             '-G', generator, *cmake_target_args()],
            [str(cmake), '--build', str(cls.project / 'build'), '--config', 'Release'],
        ):
            compiled = subprocess.run(command, capture_output=True, text=True)
            if compiled.returncode:
                cls.build_temp.cleanup()
                raise RuntimeError(compiled.stdout + compiled.stderr)
        cls.binary = build_executable(cls.project / 'build', 'state-test')

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def setUp(self):
        self.case_temp = tempfile.TemporaryDirectory(prefix='rr-state-case-')
        self.directory = Path(self.case_temp.name)
        self.path = self.directory / 'slot.rrstate'

    def tearDown(self):
        self.case_temp.cleanup()

    def call(self, action, mode='normal', path=None):
        output = subprocess.check_output(
            [str(self.binary), action, str(path or self.path), mode], text=True)
        return json.loads(output)

    def saved(self):
        self.assertEqual(self.call('write')['status'], 0)
        return self.path.read_bytes()

    def assert_rejected_without_mutation(self, expected=None, mode='normal'):
        outcome = self.call('load', mode)
        self.assertNotEqual(outcome['status'], 0)
        if expected is not None:
            self.assertEqual(outcome['status'], expected)
        self.assertEqual((outcome['core'], outcome['auxiliary']), (77, 66))
        self.assertEqual((outcome['loads'], outcome['applies'], outcome['captures']), (0, 0, 0))

    def test_fresh_process_restores_core_and_opaque_host_state(self):
        data = self.saved()
        self.assertEqual(data[:8], b'RRX68KS1')
        outcome = self.call('load')
        self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (0, 42, 12))
        self.assertEqual((outcome['loads'], outcome['applies'], outcome['captures']), (1, 1, 1))

    def test_corrupt_payload_and_header_are_rejected_before_callbacks(self):
        data = self.saved()
        for offset in (0, 8, 12, 16, 24, 32, 96, 160, 168, len(data)-1):
            with self.subTest(offset=offset):
                changed = bytearray(data)
                changed[offset] ^= 1
                self.path.write_bytes(changed)
                self.assert_rejected_without_mutation()

    def test_truncation_and_trailing_bytes_are_rejected(self):
        data = self.saved()
        for size in (0, 7, 167, 168, len(data)-1):
            with self.subTest(size=size):
                self.path.write_bytes(data[:size])
                self.assert_rejected_without_mutation(2)
        self.path.write_bytes(data + b'extra')
        self.assert_rejected_without_mutation(2)

    def test_other_cartridge_firmware_or_ram_and_other_build_are_refused(self):
        self.saved()
        for mode, expected in (('identity', 3), ('compatibility', 4)):
            with self.subTest(mode=mode):
                self.assert_rejected_without_mutation(expected, mode)

    def test_dynamic_saved_core_and_media_sizes_load_in_fresh_process(self):
        for mode, sizes in (('expanded', (48, 24)), ('compact', (16, 8))):
            with self.subTest(mode=mode):
                self.assertEqual(self.call('write', mode)['status'], 0)
                outcome = self.call('load')
                self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (0, 42, 12))
                self.assertEqual((outcome['core_size'], outcome['auxiliary_size']), sizes)

    def test_dynamic_target_failure_restores_original_sizes_and_bytes(self):
        self.assertEqual(self.call('write', 'expanded')['status'], 0)
        for mode in ('core-fail', 'aux-fail'):
            with self.subTest(mode=mode):
                outcome = self.call('load', mode)
                self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (5, 77, 66))
                self.assertEqual((outcome['core_size'], outcome['auxiliary_size']), (32, 16))

    def test_oversized_saved_lengths_are_rejected_before_allocation_or_callbacks(self):
        data = self.saved()
        for offset, size in ((16, 0), (16, 64*1024*1024+1),
                             (24, 32*1024*1024+1), (16, 2**64-1)):
            with self.subTest(offset=offset, size=size):
                changed = bytearray(data)
                changed[offset:offset+8] = size.to_bytes(8, 'little')
                self.path.write_bytes(changed)
                self.assert_rejected_without_mutation(2)

    def test_invalid_sizes_and_digests_are_rejected_before_allocation(self):
        self.saved()
        self.assert_rejected_without_mutation(2, 'oversize')
        self.assert_rejected_without_mutation(2, 'malformed-digest')

    def test_host_preflight_rejects_media_before_capture_or_mutation(self):
        self.saved()
        self.assert_rejected_without_mutation(2, 'aux-reject')

    def test_failing_core_loader_rolls_back_partially_changed_core_and_host(self):
        self.saved()
        outcome = self.call('load', 'core-fail')
        self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (5, 77, 66))
        self.assertEqual((outcome['loads'], outcome['applies']), (2, 2))

    def test_failing_media_apply_rolls_back_before_core_load(self):
        self.saved()
        outcome = self.call('load', 'aux-fail')
        self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (5, 77, 66))
        self.assertEqual((outcome['loads'], outcome['applies']), (1, 2))

    def test_failed_rollback_is_reported_as_fatal(self):
        self.saved()
        self.assertEqual(self.call('load', 'rollback-fail')['status'], 6)

    def test_capture_failure_preserves_previous_save_and_live_game(self):
        before = self.saved()
        self.assertEqual(self.call('write', 'capture-fail')['status'], 5)
        self.assertEqual(self.path.read_bytes(), before)
        outcome = self.call('load', 'capture-fail')
        self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (5, 77, 66))
        self.assertEqual((outcome['loads'], outcome['applies']), (0, 0))
        self.assertEqual(list(self.directory.glob('*.tmp.*')), [])

    def test_unicode_path_and_atomic_replace(self):
        path = self.directory / 'sauvegarde été 日本語.rrstate'
        self.assertEqual(self.call('write', path=path)['status'], 0)
        self.assertEqual(self.call('write', path=path)['status'], 0)
        self.assertEqual(self.call('load', path=path)['status'], 0)
        self.assertEqual(list(self.directory.glob('*.tmp.*')), [])

    def test_missing_parent_does_not_create_files_or_destroy_other_saves(self):
        before = self.saved()
        missing = self.directory / 'missing' / 'slot.rrstate'
        self.assertEqual(self.call('write', path=missing)['status'], 1)
        self.assertFalse(missing.parent.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_absent_auxiliary_works_without_auxiliary_callbacks(self):
        self.assertEqual(self.call('write', 'noaux')['status'], 0)
        outcome = self.call('load', 'noaux')
        self.assertEqual((outcome['status'], outcome['core'], outcome['auxiliary']), (0, 42, 66))


class ChipStorageTests(unittest.TestCase):
    """The quick state saves fmgen's members, some of which its constructors and Reset never write (1.6.3)."""

    SOURCE = (b'#include <stdio.h>\n\nextern "C" {\n\n#include "common.h"\n};\n\n'
              b'class MyOPM : public FM::OPM\n{\npublic:\n\tMyOPM();\n\tvirtual ~MyOPM() {}\nprivate:\n'
              b'\tvirtual void Intr(bool);\n\tint CurReg;\n\tDWORD CurCount;\n};\n\n'
              b'MyOPM::MyOPM()\n{\n\tCurReg = 0;\n}\n\n'
              b'void OPM_Reset(void)\n{\n\tif ( opm ) opm->Reset();\n}\n\n'
              b'// ----------------------------------------------------------\n'
              b'// ---------------------------- YMF288\n')

    def test_the_chip_is_allocated_zeroed_so_that_no_heap_content_reaches_a_state(self):
        from tools.x68000_base74 import adapt_fmg_wrap
        text = adapt_fmg_wrap(self.SOURCE).decode('ascii')
        self.assertIn('static void *operator new(size_t size) { void *p = ::operator new(size); memset(p, 0, size); return p; }', text)
        self.assertIn('static void operator delete(void *p) { ::operator delete(p); }', text)
        # The class-specific functions need their declarations before the class, and sit inside it.
        self.assertLess(text.index('#include <new>'), text.index('extern "C" {'))
        self.assertLess(text.index('#include <string.h>'), text.index('class MyOPM'))
        self.assertLess(text.index('class MyOPM'), text.index('operator new'))
        self.assertLess(text.index('operator new'), text.index('MyOPM();'))


if __name__ == '__main__':
    unittest.main()
