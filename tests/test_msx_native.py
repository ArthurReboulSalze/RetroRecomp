"""The MSX on the banked Z80 chain (systems/msx.py, retrorecomp/msx_build.py, tools/msx_native.py): the machine it declares and the step loop rendered for it.
No ROM, no compiler: the native runs themselves are checked by the tool against the reference."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tool():
    sys.path.insert(0, str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location('msx_native', ROOT / 'tools' / 'msx_native.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['msx_native'] = module
    spec.loader.exec_module(module)
    return module


class MachineTests(unittest.TestCase):
    def setUp(self):
        self.tool = tool()
        self.machine = self.tool.MSX_MACHINE

    def test_the_msx_is_a_region_map_of_eight_8k_regions_with_the_cartridge_then_the_bios(self):
        self.assertTrue(self.machine.mapped)
        self.assertEqual(self.machine.regions.region_bits, 13)
        self.assertEqual(self.machine.regions.regions, 8)
        self.assertEqual(self.machine.regions.sources, ('cartridge', 'bios'))

    def test_one_wait_state_per_m1_and_int_read_at_the_end_of_the_instruction(self):
        self.assertEqual(self.machine.m1_wait, 1)
        self.assertTrue(self.machine.counts_m1)
        self.assertEqual(self.machine.irq_sample, 'instruction_end')

    def test_the_generator_lives_in_its_own_folders(self):
        self.assertEqual(self.machine.generator_source, 'recompiler-src-msx')
        self.assertEqual(self.machine.generator_build, 'recompiler-build-msx')

    def test_the_step_loop_rendered_for_the_msx(self):
        from retrorecomp.paths import ASSETS
        from retrorecomp.z80_chain import banked_runtime
        loop = banked_runtime(self.machine, ASSETS)
        self.assertIn('smsrecomp_region_map()', loop)
        self.assertIn('game_banked_step(map)', loop)
        self.assertIn('g_hz.cyc += 1 * (z80_m1_fetches - m1_before)', loop)       # the fallback's wait states
        self.assertIn('g_z80.cyc += 5; banked_halt_steps++', loop)               # a HALT cycle with its wait
        self.assertIn('pending_irq = vdp_irq_asserted();\n        banked_after_step(pending_irq);', loop)
        self.assertNotIn('g_bank[', loop)

    def test_the_generator_gets_the_image_the_machine_sees(self):
        image = bytes(range(256)) * 48                                         # 12 KB, plain
        padded = self.tool.padded(image)
        self.assertEqual(len(padded), 0x4000)
        self.assertEqual(padded[:len(image)], image)
        self.assertEqual(set(padded[len(image):]), {0xFF})
        self.assertEqual(self.tool.padded(b'\0' * 0x4000), b'\0' * 0x4000)

    def test_the_comparison_covers_the_whole_state_and_every_frame(self):
        for field in ('af2', 'bc2', 'de2', 'hl2', 'i', 'r', 'im', 'iff2', 'wz', 'frame_trace', 'psg', 'blocks', 'ram_fnv',
                      'vram_fnv', 'audio_fnv', 'cycles', 'interrupts'):
            self.assertIn(field, self.tool.COMPARED)

    def test_the_timing_regression_cartridges(self):
        prefix = self.tool.cartridge_prefix_io()
        self.assertEqual(prefix[0x10:0x12], bytes([0x0E, 0x99]))
        self.assertEqual(prefix[0x14:0x17], bytes([0xDD, 0xED, 0x79]))        # OUT (C),A behind a redundant DD
        self.assertEqual(prefix[0x26:0x28], bytes([0x18, 0xEA]))
        self.assertEqual(0x4028 + (0xEA - 256), 0x4012)
        self.assertEqual(self.tool.cartridge_ei_ex()[0x10:0x15], bytes([0xFB, 0xDD, 0xE3, 0x18, 0xFB]))

    def test_the_glue_defines_what_the_loop_needs(self):
        glue = (ROOT / 'native' / 'msx_machine' / 'msx_glue.inc').read_text(encoding='utf-8')
        for name in ('smsrecomp_region_map', 'smsrecomp_region_generation', 'state_to_hz', 'state_from_hz',
                     'hyb_read', 'advance_vdp', 'vdp_irq_asserted', 'sms_dispatch_miss', 'smsrecomp_feedback_at',
                     'smsrecomp_learning_enabled', 'smsrecomp_observe_code', 'smsrecomp_state_service',
                     '#include "msx_banked_loop.inc"'):
            self.assertIn(name, glue)


if __name__ == '__main__':
    unittest.main()
