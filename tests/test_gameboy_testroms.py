"""The verdict rules and the applicability of tools/gameboy_testroms.py, on synthetic data: no ROM, no build."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gameboy_testroms as testroms  # noqa: E402


def registers(*values):
    return dict(zip('bcdehl', values))


class MooneyeVerdictTests(unittest.TestCase):
    def test_the_fibonacci_registers_pass(self):
        self.assertEqual(testroms.judge('mooneye', b'', registers(3, 5, 8, 13, 21, 34))[0], 'passed')

    def test_the_fibonacci_serial_bytes_pass(self):
        self.assertEqual(testroms.judge('mooneye', b'x\x03\x05\x08\x0d\x15\x22', None)[0], 'passed')

    def test_forty_two_six_times_fails(self):
        self.assertEqual(testroms.judge('mooneye', b'', registers(*(0x42,) * 6))[0], 'failed')
        self.assertEqual(testroms.judge('mooneye', b'\x42' * 6, None)[0], 'failed')

    def test_anything_else_is_incomplete_never_a_pass(self):
        self.assertEqual(testroms.judge('mooneye', b'', registers(0, 0, 0, 0, 0, 0))[0], 'incomplete')
        self.assertEqual(testroms.judge('mooneye', b'', None)[0], 'incomplete')


class BlarggVerdictTests(unittest.TestCase):
    def test_passed_and_failed_are_read_from_the_serial_text(self):
        self.assertEqual(testroms.judge('blargg', b'01-special\n\n\nPassed\n', None)[0], 'passed')
        self.assertEqual(testroms.judge('blargg', b'01-special\n\nE5 3D\nFailed #3\n', None)[0], 'failed')

    def test_the_runtime_lines_are_not_the_serial_text(self):
        raw = b'[GBRT] Passed through\nFrame limit: 10\n'
        self.assertEqual(testroms.judge('blargg', raw, None)[0], 'incomplete')

    def test_oam_bug_reads_the_memory_verdict(self):
        state = {'eram_a000_a0ff': [0, 0xDE, 0xB0, 0x61]}
        self.assertEqual(testroms.judge('oam_bug', b'', state)[0], 'passed')
        self.assertEqual(testroms.judge('oam_bug', b'', {'eram_a000_a0ff': [1, 0xDE, 0xB0, 0x61]})[0], 'failed')
        self.assertEqual(testroms.judge('oam_bug', b'', {'eram_a000_a0ff': [0x80, 0xDE, 0xB0, 0x61]})[0], 'incomplete')
        self.assertEqual(testroms.judge('oam_bug', b'', {'eram_a000_a0ff': [0, 0, 0, 0]})[0], 'incomplete')


class ApplicabilityTests(unittest.TestCase):
    def test_models_other_than_the_original_game_boy_are_set_aside_with_a_reason(self):
        for name in ('acceptance/boot_regs-sgb.gb', 'acceptance/boot_div-S.gb', 'acceptance/boot_regs-dmg0.gb',
                     'acceptance/boot_regs-mgb.gb', 'misc/boot_regs-cgb.gb', 'utils/bootrom_dumper.gb',
                     'manual-only/sprite_priority.gb'):
            self.assertTrue(testroms.mooneye_applicability(name), name)

    def test_the_tests_of_the_original_game_boy_apply(self):
        for name in ('acceptance/timer/tim00.gb', 'acceptance/oam_dma/sources-GS.gb', 'acceptance/boot_regs-dmgABC.gb',
                     'acceptance/boot_div-dmgABCmgb.gb', 'emulator-only/mbc1/rom_1Mb.gb'):
            self.assertIsNone(testroms.mooneye_applicability(name), name)


class DiscoveryTests(unittest.TestCase):
    def test_the_combined_rom_is_set_aside_and_the_single_ones_run(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'blargg-archive-org' / 'cpu_instrs' / 'x' / 'cpu_instrs'
            (archive / 'individual').mkdir(parents=True)
            (archive / 'cpu_instrs.gb').write_bytes(b'combined')
            (archive / 'individual' / '01-special.gb').write_bytes(b'single')
            tests = {test['name']: test for test in testroms.discover(Path(folder))}
            self.assertTrue(tests['cpu_instrs/cpu_instrs.gb']['not_applicable'])
            self.assertIsNone(tests['cpu_instrs/individual/01-special.gb']['not_applicable'])
            self.assertEqual([test['id'] for test in testroms.select(list(tests.values()), None)],
                             ['blargg-cpu_instrs-individual_01_special'])


if __name__ == '__main__':
    unittest.main()
