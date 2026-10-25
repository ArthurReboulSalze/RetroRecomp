"""The start-up picture: sharp transparency on Windows, a card on Linux, the
segments of the current step."""
import unittest

from retrorecomp.gui import SPLASH_STEPS, startup_picture


class StartupPictureTests(unittest.TestCase):
    def test_transparent_picture_has_only_shown_or_keyed_pixels(self):
        picture = startup_picture(2, 'Starting…', '9.9.9', True)
        self.assertEqual(picture.size, (300, 290))
        self.assertEqual(set(picture.getchannel('A').getdata()), {0, 255})
        self.assertEqual(picture.getpixel((2, 2))[3], 0)   # a corner outside the logo is keyed out

    def test_card_picture_fills_its_rounded_card(self):
        picture = startup_picture(1, '', '9.9.9', False)
        self.assertEqual(picture.getpixel((150, 280))[3], 255)

    def test_segments_light_up_with_the_step(self):
        def gold_pixels(step):
            picture = startup_picture(step, '', '9.9.9', True)
            return sum(1 for x in range(60, 240) if picture.getpixel((x, 228))[:3] == (212, 167, 55))
        counts = [gold_pixels(step) for step in range(1, SPLASH_STEPS + 1)]
        self.assertEqual(counts, sorted(counts))
        self.assertGreater(counts[0], 0)
        self.assertGreater(counts[-1], counts[0] * 3)


if __name__ == '__main__':
    unittest.main()
