"""The Game Boy Color's own fixes of the pinned runtime (retrorecomp/gameboy_color_hardware.py): each one applies to the pinned engine when the checkout is
present, a moved upstream marker is refused, and the original Game Boy's sources never receive any of them. The behaviour itself is measured by the
public test ROMs in the Color build (tools/gameboy_testroms.py --model cgb); nothing here needs a ROM."""
import shutil
import tempfile
import unittest
from pathlib import Path

from retrorecomp import gameboy_color_hardware as color
from retrorecomp import gameboy_hardware as hardware
from retrorecomp.core import ConversionError

PINNED = Path(__file__).resolve().parents[1] / '.deps' / 'gb-recompiled' / 'runtime' / 'src'
PRESENT = all((PINNED / name).exists() for name in ('audio.c', 'ppu.c', 'gbrt.c'))


@unittest.skipUnless(PRESENT, 'the engine checkout is not present')
class OnThePinnedEngine(unittest.TestCase):
    def patched(self, model: str) -> dict:
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / 'runtime' / 'src').mkdir(parents=True)
            for name in ('audio.c', 'ppu.c', 'gbrt.c'):
                shutil.copyfile(PINNED / name, project / 'runtime' / 'src' / name)
            # The unused-bits patch of the runtime module comes first in a real conversion; the Color's register fix anchors on its text.
            from retrorecomp import gameboy_runtime
            gbrt = project / 'runtime' / 'src' / 'gbrt.c'
            gbrt.write_text(gameboy_runtime.adapt_unused_io_bits(gbrt.read_text(encoding='utf-8')), encoding='utf-8')
            hardware.adapt_hardware(project, model)
            return {name: (project / 'runtime' / 'src' / name).read_text(encoding='utf-8') for name in ('audio.c', 'ppu.c', 'gbrt.c')}

    def test_the_color_receives_every_fix(self):
        files = self.patched('cgb')
        self.assertIn('<< 3) | (', files['ppu.c'])                                   # 5 to 8 bits as the test references do
        self.assertNotIn('* 255 / 31', files['ppu.c'].split('rgb555_to_rgba', 1)[1][:400])
        self.assertIn('return true;     /* OAM and the unusable area conflict with the transfer */', files['gbrt.c'])
        self.assertIn('cgb_disable_edge = false &&', files['gbrt.c'])
        self.assertIn('ctx->io[0x00] = 0xFF; /* JOYP: the selection lines start high */', files['gbrt.c'])
        self.assertIn('return addr == 0xFF68 ? 0xC8 : addr == 0xFF6A ? 0xD0 : 0xFF;', files['gbrt.c'])
        self.assertIn('if (false) {', files['audio.c'])                              # no length write while the unit is off
        self.assertNotIn('kept_length[0];', files['audio.c'])
        self.assertIn('the byte being played', files['audio.c'])
        self.assertIn('the first sample comes 6 clocks late', files['audio.c'])

    def test_the_original_game_boy_receives_none_of_them(self):
        files = self.patched('dmg')
        for marker in ('<< 3) | (', 'return true;     /* OAM', 'cgb_disable_edge = false', 'selection lines start high', '0xC8 : addr == 0xFF6A',
                       'the byte being played', 'comes 6 clocks late', 'if (false) {'):
            for name, text in files.items():
                self.assertNotIn(marker, text, (marker, name))
        self.assertIn('kept_length[0];', files['audio.c'])

    def test_the_default_model_is_the_original_game_boy(self):
        self.assertEqual(self.patched('dmg'), self.patched_default())

    def patched_default(self) -> dict:
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / 'runtime' / 'src').mkdir(parents=True)
            for name in ('audio.c', 'ppu.c', 'gbrt.c'):
                shutil.copyfile(PINNED / name, project / 'runtime' / 'src' / name)
            from retrorecomp import gameboy_runtime
            gbrt = project / 'runtime' / 'src' / 'gbrt.c'
            gbrt.write_text(gameboy_runtime.adapt_unused_io_bits(gbrt.read_text(encoding='utf-8')), encoding='utf-8')
            hardware.adapt_hardware(project)
            return {name: (project / 'runtime' / 'src' / name).read_text(encoding='utf-8') for name in ('audio.c', 'ppu.c', 'gbrt.c')}


class MovedMarkers(unittest.TestCase):
    def test_a_fix_refuses_a_source_whose_marker_moved(self):
        for fix in (color.adapt_color_expansion, color.adapt_color_oam_dma, color.adapt_color_timer, color.adapt_color_registers,
                    color.adapt_color_power_off, color.adapt_color_wave_write, color.adapt_color_wave_timer):
            with self.subTest(fix.__name__), self.assertRaises(ConversionError):
                fix('nothing of the pinned runtime')


if __name__ == '__main__':
    unittest.main()
