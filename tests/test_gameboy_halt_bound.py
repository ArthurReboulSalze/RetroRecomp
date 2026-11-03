"""The mode 3 bound of the halted fast-forward (retrorecomp/gameboy_runtime.py: adapt_halt_mode3), on synthetic sources: no ROM, no compiler.
The behaviour itself is checked by tools/gameboy_halt_selftest.py (the runtime built with and without the bound, whole state compared
after every slice) and by the per-frame traces of the A/B of 1.6.7."""
import inspect
import unittest

from retrorecomp import gameboy_runtime as runtime

OLD = ('        /* Mode 3 ends on a dynamic FIFO event; advance only one CPU M-cycle. */\n'
       '        case PPU_MODE_DRAW: target = ppu->mode_cycles + 4u; break;\n')
SOURCE = ('    switch (ppu->mode) {\n        case PPU_MODE_OAM: target = CYCLES_OAM_SCAN; break;\n' + OLD +
          '        case PPU_MODE_HBLANK: target = ppu->hblank_length; break;\n    }\n')


class HaltBoundPatchTests(unittest.TestCase):
    def test_the_one_machine_cycle_step_of_mode_3_is_replaced_and_nothing_else(self):
        out = runtime.adapt_halt_mode3(SOURCE)
        self.assertNotIn('target = ppu->mode_cycles + 4u; break;', out)
        self.assertIn('case PPU_MODE_OAM: target = CYCLES_OAM_SCAN; break;', out)
        self.assertIn('case PPU_MODE_HBLANK: target = ppu->hblank_length; break;', out)

    def test_the_step_stops_one_dot_before_the_earliest_end_of_the_transfer(self):
        out = runtime.adapt_halt_mode3(SOURCE)
        self.assertIn('pixels_left > 4u ? pixels_left - 1u : 4u', out)       # never reaches the dot where the mode ends
        self.assertIn('ppu->visible_mode == PPU_MODE_DRAW', out)             # not before the mode is published as 3
        self.assertIn('GB_SCREEN_WIDTH - ppu->draw_x', out)

    def test_a_changed_upstream_is_refused(self):
        with self.assertRaises(Exception):
            runtime.adapt_halt_mode3(SOURCE.replace('4u; break;', '8u; break;'))
        with self.assertRaises(Exception):
            runtime.adapt_halt_mode3(runtime.adapt_halt_mode3(SOURCE))       # a second application does not find its marker

    def test_the_comparison_build_can_leave_the_bound_out(self):
        parameters = inspect.signature(runtime.adapt_generated_project).parameters
        self.assertIs(parameters['halt_mode3_bound'].default, True)           # a conversion always applies it


class StepArithmeticTests(unittest.TestCase):
    """The rule of the C text, on its own: a step of 4 * floor((pixels_left - 1) / 4) cycles never reaches the earliest end."""

    @staticmethod
    def step(pixels_left):
        target = pixels_left - 1 if pixels_left > 4 else 4
        return max(4, target & ~3)

    def test_no_step_reaches_the_earliest_end_and_wake_up_stays_on_the_four_cycle_grid(self):
        for pixels_left in range(1, 161):
            cycles = self.step(pixels_left)
            self.assertEqual(cycles % 4, 0)
            self.assertGreaterEqual(cycles, 4)
            if pixels_left > 4:
                self.assertLess(cycles, pixels_left)       # the dot where the mode can end is still ahead

    def test_the_whole_line_takes_few_steps(self):
        position, steps = 0, 0
        while position < 160 - 4:
            position += self.step(160 - position)
            steps += 1
        self.assertLessEqual(steps, 10)


if __name__ == '__main__':
    unittest.main()
