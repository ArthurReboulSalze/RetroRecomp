"""CPS-1 comparison with MAME (tools/cps1_mame_compare.py): the parts that need neither MAME nor a ROM."""
import importlib.util
from pathlib import Path
import unittest

from PIL import Image

from retrorecomp import cps1_catalogue

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_mame_compare', ROOT / 'tools' / 'cps1_mame_compare.py')
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


class PortValueTests(unittest.TestCase):
    def test_coin_and_start_clear_their_active_low_bits_in_in0(self):
        game = cps1_catalogue.by_set()['1941']
        rows = compare.port_values(game, '0 000 000\n802 080 000\n810 000 000\n916 040 000\n920 001 000\n')
        self.assertEqual(rows[0], (0, 255, 65535, 65535, 65535))
        self.assertEqual(rows[1][:2], (802, 254))          # coin 1: bit 0 of IN0 low
        self.assertEqual(rows[2][:2], (810, 255))          # released
        self.assertEqual(rows[3][:2], (916, 239))          # start 1: bit 4 of IN0 low
        self.assertEqual(rows[4][2], 65519)                # button 1 of player 1 clears bit 4 of IN1
        self.assertEqual(rows[4][3:], (65535, 65535))

    def test_a_three_player_board_has_its_third_port(self):
        game = cps1_catalogue.by_set()['captcomm']
        rows = compare.port_values(game, '0 000 000\n')
        self.assertEqual(rows[0], (0, 255, 65535, 255, 255))


class UnrotateTests(unittest.TestCase):
    def test_unrotate_inverts_the_rotation_the_game_applies_to_vertical_boards(self):
        width, height = 6, 4
        source = Image.new('RGB', (width, height))
        source.putdata([(x * 20, y * 40, (x + y) * 10) for y in range(height) for x in range(width)])
        # native/cps1_host.c: pixels[(width - 1 - x) * stride + y] = src[y * width + x]
        rotated = Image.new('RGB', (height, width))
        for y in range(height):
            for x in range(width):
                rotated.putpixel((y, width - 1 - x), source.getpixel((x, y)))
        self.assertEqual(list(compare.unrotate(rotated).getdata()), list(source.getdata()))


class SoundTests(unittest.TestCase):
    RATE = compare.AUDIO_RATE

    def files(self, mame, ours, rate=None):
        import tempfile
        import wave
        import numpy
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        wav, pcm = Path(folder.name) / 'mame.wav', Path(folder.name) / 'game.pcm'
        with wave.open(str(wav), 'wb') as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(rate or self.RATE)
            stream.writeframes(numpy.repeat(mame.astype('<i2'), 2).tobytes())
        pcm.write_bytes(ours.astype('<i2').tobytes())
        return wav, pcm

    def tone(self, seconds, frequency=440.0, level=8000, shift=0):
        import numpy
        t = numpy.arange(seconds * self.RATE + shift) / self.RATE
        return (level * numpy.sin(2 * numpy.pi * frequency * t) + 300 * numpy.sin(2 * numpy.pi * 3100 * t))

    def test_the_same_sound_agrees_exactly(self):
        signal = self.tone(8)
        result = compare.compare_sound(*self.files(signal, signal))
        self.assertTrue(result['compared'])
        self.assertAlmostEqual(result['level_difference_db_max'], 0.0, places=6)
        self.assertGreater(result['averaged_spectrum_cosine'], 0.999999)
        self.assertEqual(result['lag_samples'], 0)

    def test_a_louder_game_shows_its_level_difference_and_a_small_lag_is_found(self):
        signal = self.tone(8)
        louder = self.tone(8, level=16000)
        result = compare.compare_sound(*self.files(signal, louder))
        self.assertAlmostEqual(result['level_difference_db_median'], 6.0, delta=0.2)
        import numpy
        delayed = compare.compare_sound(*self.files(signal, numpy.concatenate([numpy.zeros(200), signal])))
        self.assertEqual(abs(delayed['lag_samples']), 200)
        self.assertGreater(delayed['averaged_spectrum_cosine'], 0.999)

    def test_a_silent_side_and_a_wrong_rate_are_reported_not_compared(self):
        import numpy
        silent = numpy.zeros(8 * self.RATE)
        self.assertFalse(compare.compare_sound(*self.files(self.tone(8), silent))['compared'])
        self.assertFalse(compare.compare_sound(*self.files(self.tone(8), self.tone(8), rate=48000))['compared'])


if __name__ == '__main__':
    unittest.main()
