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


if __name__ == '__main__':
    unittest.main()
