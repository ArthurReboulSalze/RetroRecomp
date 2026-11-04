"""The colour of the X68000: the intensity bit of GGGGGRRRRRBBBBBI lifts red, green and blue together.

The pinned base kept its frame buffer in RGB565 and put the intensity bit in the lowest unused bit, the low bit of green,
so a pixel with the bit set came out brighter on green only. The machine now keeps the word it was given and widens it
when the picture is presented (native/x68000_machine/colour.h): each primary is (five bits << 1 | I) as a 6-bit DAC level,
extended to 8 bits. tests/x68000_colour_harness.c runs the real masks, the real palette code and that widening on authored
words; the expected values below are written out from the rule, not read from the C. No ROM, disk or firmware is involved.
"""
import re
import unittest
from pathlib import Path

from tests.x68000_base_harness import ROOT, build_and_run


def dac8(level6):
    return (level6 << 2) | (level6 >> 4)


def expected(word):
    intensity = word & 1
    green, red, blue = (word >> 11) & 31, (word >> 6) & 31, (word >> 1) & 31
    return dac8(red << 1 | intensity) << 16 | dac8(green << 1 | intensity) << 8 | dac8(blue << 1 | intensity)


class ColourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build, cls.cases = build_and_run('x68000_colour_harness.c', ['x68k/palette.c'])

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def colour(self, word):
        return int(self.cases[f'c{word:04x}']['v'], 16)

    def test_the_machine_keeps_its_own_colour_word(self):
        layout = self.cases['layout']
        self.assertEqual({key: int(value, 16) for key, value in layout.items()},
                         {'green': 0xf800, 'red': 0x07c0, 'blue': 0x003e, 'ibit': 1, 'halfmask': 0xffff & ~(0x0800 | 0x0040 | 0x0002 | 1), 'ix2': 2})
        self.assertEqual(self.cases['identity'], {'different': '0'})
        written = {key: int(value, 16) for key, value in self.cases['written'].items()}
        self.assertEqual(written, {'graphic0': 0x07c0, 'graphic1': 0xf800, 'graphic2': 0x003e, 'graphic3': 0x0001,
                                   'text3': 0x07c1, 'text4': 0xffff})

    def test_intensity_lifts_the_three_primaries_together(self):
        # Black, then black with the bit: a half step of the 6-bit DAC on each primary (4 of 255), not green alone.
        self.assertEqual(self.colour(0x0000), 0x000000)
        self.assertEqual(self.colour(0x0001), 0x040404)
        # Full red, then with the bit: red goes from 6-bit 62 (251) to 63 (255); green and blue gain the half step.
        self.assertEqual(self.colour(0x07c0), 0xfb0000)
        self.assertEqual(self.colour(0x07c1), 0xff0404)
        self.assertEqual(self.colour(0xf800), 0x00fb00)
        self.assertEqual(self.colour(0xf801), 0x04ff04)
        self.assertEqual(self.colour(0x003e), 0x0000fb)
        self.assertEqual(self.colour(0x003f), 0x0404ff)
        self.assertEqual(self.colour(0xffff), 0xffffff)
        self.assertEqual(self.colour(0xfffe), 0xfbfbfb)
        # The top byte stays zero: a black picture is all zero bytes.
        self.assertTrue(all(self.colour(word) >> 24 == 0 for word in (0, 1, 0xffff)))

    def test_every_word(self):
        wrong = [word for word in range(65536) if self.colour(word) != expected(word)]
        self.assertEqual(wrong[:8], [])

    def test_the_bit_adds_the_same_step_to_every_primary(self):
        for word in range(0, 65536, 2):
            low, high = self.colour(word), self.colour(word | 1)
            for shift in (16, 8, 0):
                self.assertEqual(((high >> shift) & 255) - ((low >> shift) & 255), 4, hex(word))

    def test_contrast(self):
        # Full contrast leaves every word and the intensity bit alone; lower contrast scales the five-bit primaries
        # (the base's rule, kept) and leaves the bit.
        self.assertEqual(self.cases['contrast15'], {'different': '0', 'graphic3': '0001', 'text3': '07c1'})
        half = {key: int(value, 16) for key, value in self.cases['contrast8'].items()}
        self.assertEqual(half['graphic0'], 16 << 6)
        self.assertEqual(half['graphic1'], 16 << 11)
        self.assertEqual(half['graphic2'], 16 << 1)
        self.assertEqual(half['graphic3'], 0x0001)  # no colour: only the bit is left
        self.assertEqual(half['text3'], (16 << 6) | 1)


class PresentationSourceTests(unittest.TestCase):
    def test_the_glue_presents_xrgb8888_through_the_table(self):
        source = Path(ROOT / 'native/x68000_machine/libretro_api.c').read_text(encoding='utf-8')
        self.assertIn('RETRO_PIXEL_FORMAT_XRGB8888', source)
        self.assertNotIn('RETRO_PIXEL_FORMAT_RGB565', source)
        self.assertIn('rr_x68k_colour_table', source)
        self.assertRegex(source, r'convert_frame\(width, height\) : presented_frame, width, height, RR_SCREEN_WIDTH \* sizeof\(uint32_t\)\)')

    def test_the_redraw_after_a_loaded_state_uses_the_same_pictures(self):
        # The host redraws the picture from the machine's framebuffer once a state is loaded: it must be the converted one,
        # at the pitch of the negotiated format (a 16-bit buffer read as 800 x 4 bytes, or the reverse, broke that redraw).
        bridge = Path(ROOT / 'native/x68000_machine/base74/bridge.c').read_text(encoding='utf-8')
        self.assertIn('rr_x68k_framebuffer(void) { return rr_glue_converted_frame(); }', bridge)
        host = Path(ROOT / 'native/x68000_reference/reference_host.c').read_text(encoding='utf-8')
        self.assertIn('video(core.framebuffer(),width,height,800*(pixel_format==RETRO_PIXEL_FORMAT_RGB565?2:4))', host)

    def test_the_picture_is_converted_only_when_the_host_reads_it(self):
        # In 1.6.6 the colour conversion lived in the window kit (player_picture), which a headless run never reaches; moved into the
        # core it ran on every frame, read or not. The core now asks libretro's "video enabled" bit, and the reference host answers
        # from what it does with the picture: a trace or a report hashes it, a capture or the window keeps it.
        glue = Path(ROOT / 'native/x68000_machine/libretro_api.c').read_text(encoding='utf-8')
        self.assertIn('RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE', glue)
        self.assertRegex(glue, r'video_cb\(video_wanted\(\) \? convert_frame\(width, height\) : presented_frame,')
        self.assertIn('return mask & 1;', glue)
        self.assertEqual(glue.count('convert_frame(width, height)'), 1)    # the only conversion of a presented frame
        host = Path(ROOT / 'native/x68000_reference/reference_host.c').read_text(encoding='utf-8')
        self.assertIn('case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE: *(int *)data=2|((hash_video||keep_pixels)?1:0); return true;', host)
        # keep_pixels is true in a window and with a capture, hash_video with a trace or a report: nothing else needs the picture.
        self.assertIn('hash_video=trace_path[0] || report[0]; keep_pixels=hash_video || capture_path[0] || !headless;', host)
        # A state load redraws through the full conversion, whatever the host answered.
        bridge = Path(ROOT / 'native/x68000_machine/base74/bridge.c').read_text(encoding='utf-8')
        self.assertIn('rr_x68k_framebuffer(void) { return rr_glue_converted_frame(); }', bridge)

    def test_the_machine_masks_are_the_colour_word(self):
        source = Path(ROOT / 'native/x68000_machine/base74/host_draw.c').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'WinDraw_Pal16([BRG]) = (0x[0-9a-f]{4})', source),
                         [('B', '0x003e'), ('R', '0x07c0'), ('G', '0xf800')] * 2)


if __name__ == '__main__':
    unittest.main()
