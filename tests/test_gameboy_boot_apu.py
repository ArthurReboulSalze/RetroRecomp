"""The 1.6.8 boot state, serial phase and sound-unit patches of the Game Boy runtime (retrorecomp/gameboy_runtime.py, gameboy_hardware.py).
The synthetic sources pin the text each patch writes and that a moved upstream marker is refused; the pinned audio.c is also patched
when the engine checkout is present. The behaviour itself is proved by the test ROMs (tools/gameboy_testroms.py)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from retrorecomp import gameboy_hardware as hardware
from retrorecomp import gameboy_runtime as runtime
from retrorecomp.core import ConversionError

PINNED_AUDIO = Path(__file__).resolve().parents[1] / '.deps' / 'gb-recompiled' / 'runtime' / 'src' / 'audio.c'
RESET = '    if (ctx->ppu) {\n        ppu_reset((GBPPU*)ctx->ppu, ctx);\n    }\n}'
SERIAL = '                ctx->serial_transfer.cycles_remaining =\n                    ctx->serial_transfer.fast_clock ? 128u : 4096u;\n'


class BootStateTests(unittest.TestCase):
    def test_the_ppu_is_stepped_to_the_line_the_console_has_after_the_boot_rom_only_on_a_dmg_without_boot_rom(self):
        source = runtime.adapt_boot_ppu_phase('x\n' + RESET)
        self.assertIn('if (skip_bootrom && !gb_is_cgb_mode(ctx) && !gb_is_cgb_compat_mode(ctx))', source)
        self.assertIn('ppu_tick((GBPPU*)ctx->ppu, ctx, 4104u);', source)
        with self.assertRaises(ConversionError):
            runtime.adapt_boot_ppu_phase('x\n' + RESET.replace('ppu_reset', 'ppu_reset2'))

    def test_the_serial_transfer_ends_on_the_phase_of_the_divider(self):
        source = runtime.adapt_serial_phase(SERIAL)
        self.assertIn('4096u - (uint32_t)(ctx->div_counter & 0x1FFu)', source)
        self.assertIn('fast_clock ? 128u :', source)
        with self.assertRaises(ConversionError):
            runtime.adapt_serial_phase('nothing')


@unittest.skipUnless(PINNED_AUDIO.exists(), 'the engine checkout is not present')
class SoundUnitTests(unittest.TestCase):
    def patched(self) -> str:
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / 'runtime' / 'src').mkdir(parents=True)
            shutil.copyfile(PINNED_AUDIO, project / 'runtime' / 'src' / 'audio.c')
            hardware.adapt_hardware(project)
            return (project / 'runtime' / 'src' / 'audio.c').read_text(encoding='utf-8')

    def test_channel_one_is_on_after_the_boot_rom(self):
        source = self.patched()
        self.assertIn('apu->ch1.enabled = true;\n    apu->ch1.volume = 0;', source)

    def test_the_power_switch_keeps_the_wave_ram_and_the_length_counters(self):
        source = self.patched()
        self.assertIn('memcpy(apu->ch3.wave_ram, kept_wave, sizeof(kept_wave));', source)
        self.assertIn('apu->ch4.length_counter = kept_length[3];', source)
        self.assertIn('else if (addr == 0xFF20) apu->ch4.length_counter = 64 - (value & 0x3F);', source)

    def test_enabling_a_length_clocks_it_in_the_first_half_of_the_period_on_the_four_channels(self):
        source = self.patched()
        self.assertEqual(source.count('!audio_next_step_clocks_length(apu)'), 8)   # four enables and four reloads

    def test_the_sweep_calculates_with_a_shift_of_zero_and_negate_is_remembered_in_the_unused_field(self):
        source = self.patched()
        self.assertIn('uint16_t delta = new_freq >> shift;', source)
        self.assertIn('if (sub) ch->freq = 1;', source)
        self.assertIn('apu->ch1.freq = 0;', source)
        self.assertNotIn('ch1.freq', PINNED_AUDIO.read_text(encoding='utf-8'))      # the field is unused upstream: the state keeps its size


if __name__ == '__main__':
    unittest.main()
