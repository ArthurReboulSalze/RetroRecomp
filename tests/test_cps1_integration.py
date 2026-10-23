"""CPS-1 converter integration: profile, controls, routes, packing, host wiring.
Synthetic data and the public catalogue only; no ROM is needed."""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from smsrecomp import cps1_catalogue
from smsrecomp.cps1_build import input_table, pack
from smsrecomp.cps1_conversion import merge, routes

ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_registered_profile_metadata_and_scan_levels(self):
        from smsrecomp.systems import PROFILES, get_profile
        from smsrecomp.metadata import game_metadata
        from smsrecomp.scan_levels import plan_for
        profile = get_profile('cps1')
        self.assertIn(profile, PROFILES)
        self.assertEqual((profile.export_folder, profile.video_modes), ('CPS-1', ('arcade',)))
        self.assertEqual(game_metadata('Demo', False, 'arcade', 'cps1')['Console'], 'Capcom CPS-1')
        self.assertEqual(plan_for('cps1', level='quick').frames, 2400)

    def test_zip_detection_precedes_neo_geo_and_respects_a_chosen_console(self):
        from smsrecomp.systems import profile_for_path
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'demo.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('demo.bin', b'synthetic')
            with patch('smsrecomp.cps1.looks_like_cps1_zip', return_value=True):
                self.assertEqual(profile_for_path(path).id, 'cps1')
            with patch('smsrecomp.cps1.looks_like_cps1_zip', side_effect=AssertionError):
                self.assertEqual(profile_for_path(path, 'cps1').id, 'cps1')

    def test_feedback_kinds_match_the_runtime(self):
        from smsrecomp.feedback import KINDS
        self.assertEqual(KINDS['cps1'], {14, 15, 16})
        header = (ROOT / 'native/runtime_feedback.h').read_text(encoding='utf-8')
        self.assertIn('RR_FB_CPS1_ROM=14, RR_FB_CPS1_RAM=15, RR_FB_CPS1_Z80=16', header)
        self.assertIn('kind>RR_FB_CPS1_Z80', (ROOT / 'native/runtime_feedback.c').read_text(encoding='utf-8'))


class ControlTests(unittest.TestCase):
    def test_final_fight_players_one_and_two(self):
        rows = input_table(cps1_catalogue.by_set()['ffight'])
        self.assertIn((0, 1, 7, 1), rows)       # coin 1 -> player 1 coin
        self.assertIn((0, 32, 6, 2), rows)      # start 2 -> player 2 Start
        self.assertIn((1, 4096, 0, 2), rows)    # player 2 button 1
        self.assertFalse([row for row in rows if row[2] in (3, 4, 5)])

    def test_six_button_games_use_the_extra_port(self):
        rows = input_table(cps1_catalogue.by_set()['sf2'])
        self.assertIn((2, 1, 3, 1), rows)       # IN2 bit 0 -> player 1 button 4
        self.assertIn((2, 64, 5, 2), rows)      # IN2 bit 6 -> player 2 button 6

    def test_third_and_fourth_players_stay_released(self):
        game = cps1_catalogue.by_set()['captcomm']
        self.assertTrue(all(player in (1, 2) for *_, player in input_table(game)))

    def test_host_menu_and_pad_bits_agree(self):
        ui = (ROOT / 'native/console16_host_ui.c').read_text(encoding='utf-8')
        block = ui[ui.index('#elif RR16_CPS1'):ui.index('#elif RR16_MD')]
        self.assertIn('enum { A, B, C, X, Y, Z, START, COIN, UP, DOWN, LEFT, RIGHT, ACTIONS };', block)
        self.assertIn('{1,2,4,8,16,32,64,128,256,512,1024,2048}', block)
        host = (ROOT / 'native/cps1_host.h').read_text(encoding='utf-8')
        self.assertIn('RR_CPS1_START, RR_CPS1_COIN, RR_CPS1_UP, RR_CPS1_DOWN, RR_CPS1_LEFT, RR_CPS1_RIGHT', host)


class RouteTests(unittest.TestCase):
    def test_levels_choose_attract_play_and_long_routes(self):
        identity = 'a' * 64
        self.assertEqual([r[0] for r in routes(identity, frames=3600, level='quick', six_buttons=False)], ['play'])
        self.assertEqual([r[0] for r in routes(identity, frames=3600, level='standard', six_buttons=False)],
                         ['attract', 'play'])
        self.assertEqual([r[0] for r in routes(identity, frames=3600, level='thorough', six_buttons=True)],
                         ['attract', 'play', 'long-1', 'long-2'])

    def test_play_route_inserts_a_coin_then_uses_host_bits(self):
        name, frames, script = routes('b' * 64, frames=3600, level='quick', six_buttons=False)[0]
        rows = [tuple(int(v, 16) if i else int(v) for i, v in enumerate(line.split())) for line in script.splitlines()]
        self.assertEqual(rows[0], (0, 0, 0))
        self.assertEqual(next(row for row in rows if row[1])[1], 0x80)
        self.assertTrue(all(p1 < 0x1000 and p2 < 0x1000 and not p1 & 0x38 for _, p1, p2 in rows))
        self.assertEqual(rows[-1][0], frames - 1)
        self.assertEqual(routes('b' * 64, frames=3600, level='quick', six_buttons=False)[0][2], script)

    def test_observations_merge_without_duplicates(self):
        known = {'m68k_ram': [{'offset': 16, 'words': '4e75'}], 'z80_ram': []}
        self.assertFalse(merge(known, {'m68k_ram': [{'offset': 16, 'words': '4e75'}]}))
        self.assertTrue(merge(known, {'z80_ram': [{'address': 0xd000, 'bytes': 'c9000000'}]}))
        self.assertEqual(len(known['z80_ram']), 1)


class PackTests(unittest.TestCase):
    def test_board_pack_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp)
            (board / 'board.txt').write_bytes(b'cps1-board 1\n')
            (board / 'maincpu.bin').write_bytes(b'\x00\x01' * 8)
            (board / 'oki.bin').write_bytes(b'\x7f')
            data = pack(board)
        self.assertEqual(data[:4], b'CPZ1')
        raw = zlib.decompress(data[8:])
        self.assertEqual(len(raw), int.from_bytes(data[4:8], 'little'))
        self.assertEqual((raw[:8], int.from_bytes(raw[8:12], 'little')), (b'CPS1PACK', 3))
        names = [raw[12 + 20 * n:28 + 20 * n].rstrip(b'\0') for n in range(3)]
        self.assertEqual(names, [b'board.txt', b'maincpu.bin', b'oki.bin'])
        self.assertEqual(len(raw), 12 + 60 + 13 + 16 + 1)

    def test_runtime_reads_the_same_layout(self):
        main = (ROOT / 'native/cps1_main.c').read_text(encoding='utf-8')
        self.assertIn('memcmp(source, "CPZ1", 4)', main)
        self.assertIn('memcmp(raw, "CPS1PACK", 8)', main)
        self.assertRegex(main, re.escape('size_t offset = 12 + (size_t)entries * 20;'))


if __name__ == '__main__':
    unittest.main()
