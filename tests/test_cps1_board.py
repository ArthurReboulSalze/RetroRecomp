"""CPS-1 region assembly and board description. Synthetic data only."""
import math
from pathlib import Path
import re
import unittest

from smsrecomp import cps1_board, cps1_catalogue

ROOT = Path(__file__).resolve().parents[1]


def region(tag, size, loads, erase=None):
    return {'tag': tag, 'bytes': size, 'erase': erase, 'loads': loads}


def load(op, name, offset, size):
    return {'op': op, 'name': name, 'offset': offset, 'bytes': size, 'crc32': 0, 'sha1': '0' * 40}


class AssemblyTests(unittest.TestCase):
    def test_mame_load_layouts(self):
        files = {'even': b'\x01\x02', 'odd': b'\x03\x04', 'swap': b'\x10\x11\x12\x13',
                 'w0': b'\xa0\xa1\xa2\xa3', 'w1': b'\xb0\xb1\xb2\xb3', 'byte': b'\xc0\xc1'}
        game = {'regions': [
            region('maincpu', 8, [load('load16_byte', 'even', 0, 2), load('load16_byte', 'odd', 1, 2),
                                  load('load16_word_swap', 'swap', 4, 4)]),
            region('gfx', 16, [load('load64_word', 'w0', 0, 4), load('load64_word', 'w1', 2, 4),
                               load('load64_byte', 'byte', 5, 2)], erase=0xff)]}
        regions = cps1_board.assemble(game, files)
        self.assertEqual(bytes(regions['maincpu']), bytes([1, 3, 2, 4, 0x11, 0x10, 0x13, 0x12]))
        self.assertEqual(bytes(regions['gfx']), bytes([0xa0, 0xa1, 0xb0, 0xb1, 0xff, 0xc0, 0xff, 0xff,
                                                       0xa2, 0xa3, 0xb2, 0xb3, 0xff, 0xc1, 0xff, 0xff]))

    def test_continue_reload_ignore_fill_and_copy(self):
        files = {'sound': bytes(range(8))}
        game = {'regions': [
            region('audiocpu', 16, [load('load', 'sound', 0, 2), {'op': 'ignore', 'bytes': 2},
                                    {'op': 'continue', 'offset': 8, 'bytes': 2},
                                    {'op': 'reload', 'offset': 12, 'bytes': 2},
                                    {'op': 'fill', 'offset': 4, 'bytes': 2, 'value': 0x7f}]),
            region('stars', 4, [{'op': 'copy', 'source': 'audiocpu', 'source_offset': 8, 'offset': 0, 'bytes': 4}])]}
        regions = cps1_board.assemble(game, files)
        self.assertEqual(bytes(regions['audiocpu']),
                         bytes([0, 1, 0, 0, 0x7f, 0x7f, 0, 0, 4, 5, 0, 0, 0, 1, 0, 0]))
        self.assertEqual(bytes(regions['stars']), bytes([4, 5, 0, 0]))

    def test_layout_outside_its_region_is_refused(self):
        game = {'regions': [region('oki', 2, [load('load16_byte', 'big', 0, 2)])]}
        with self.assertRaisesRegex(ValueError, 'does not fit'):
            cps1_board.assemble(game, {'big': b'\x01\x02'})


class DescriptionTests(unittest.TestCase):
    def test_final_fight_board_text(self):
        text = cps1_board.descriptor(cps1_catalogue.by_set()['ffight']).splitlines()
        for line in ('cps1-board 1', 'set ffight', 'cpu_clock 10000000', 'id 32 4', 'layer_control 46',
                     'priority 38 48 40 50', 'bank_sizes 32768 0 0 0', 'input DSWC 159', 'rotation 0'):
            self.assertIn(line, text)
        self.assertEqual(sum(line.startswith('range ') for line in text), 4)

    def test_twelve_megahertz_and_extra_ports(self):
        text = cps1_board.descriptor(cps1_catalogue.by_set()['sf2ce']).splitlines()
        self.assertIn('cpu_clock 12000000', text)
        self.assertIn('ports 54 0 0', text)
        self.assertIn('input IN2 255', text)


class OkiTableTests(unittest.TestCase):
    def test_step_sizes_match_mame_formula(self):
        source = (ROOT / 'native/cps1_oki.c').read_text(encoding='utf-8')
        table = re.search(r'step_size\[49\] = \{([^}]*)\}', source).group(1)
        values = [int(value) for value in table.replace('\n', ' ').split(',') if value.strip()]
        self.assertEqual(values, [math.floor(16.0 * math.pow(11.0 / 10.0, step)) for step in range(49)])


if __name__ == '__main__':
    unittest.main()
