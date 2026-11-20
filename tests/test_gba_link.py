"""The Game Boy Advance link cable's reviewed data (retrorecomp/gba_link.py): no ROM needed."""
from __future__ import annotations

import unittest

from retrorecomp import gba_link


class SeedTests(unittest.TestCase):
    def test_every_seed_is_a_plain_row(self):
        for sha256, seed in gba_link.SEEDS.items():
            self.assertRegex(sha256, r'^[0-9a-f]{64}$')
            self.assertTrue(seed.roots)
            self.assertEqual(list(seed.roots), sorted(set(seed.roots)))
            for root in seed.roots:
                self.assertTrue(root & gba_link.THUMB, 'a link root is a Thumb entry here')
                self.assertLess(root & ~1, 32 * 1024 * 1024)
                self.assertEqual(root & 1, 1)
            self.assertGreaterEqual(seed.seats_tested, 2)
            self.assertLessEqual(seed.seats_tested, 4)
            self.assertEqual(seed.interpreted, 0, 'a row is accepted only from a run with no interpreted instruction')
            self.assertGreater(seed.frames, 0)
            self.assertGreater(seed.cycles, 0)

    def test_a_cartridge_without_a_row_is_not_ready(self):
        other = '0' * 64
        self.assertEqual(gba_link.roots(other), set())
        self.assertEqual(gba_link.seats(other), 0)
        report = gba_link.report(other)
        self.assertEqual(report['status'], 'not qualified')
        self.assertIn('input sharing', report['reason'])

    def test_a_ready_cartridge_reports_the_five_measures_apart(self):
        sha256 = next(iter(gba_link.SEEDS))
        report = gba_link.report(sha256)
        self.assertEqual(report['status'], 'ready')
        for key in ('native_code', 'cpu_fidelity', 'hardware_fidelity', 'gameplay_validation', 'physical_latency'):
            self.assertIn(key, report)
        self.assertNotIn('zero latency', str(report).lower())
        self.assertEqual(report['seats'], gba_link.seats(sha256))
        self.assertEqual(len(gba_link.roots(sha256)), report['roots_added'])


class ProfileTests(unittest.TestCase):
    def test_the_profile_offers_the_cable_to_two_consoles_and_a_game_needs_its_row(self):
        from retrorecomp.systems import get_profile
        self.assertEqual(get_profile('gba').netplay_link_seats, 2)
        self.assertLessEqual(max(seed.seats_tested for seed in gba_link.SEEDS.values()), get_profile('gba').netplay_link_seats)

    def test_the_player_learns_the_cable_from_the_workers_environment_and_refuses_a_game_without_a_row(self):
        from retrorecomp.paths import ROOT
        source = (ROOT / 'native' / 'gba_machine.cpp').read_text(encoding='utf-8')
        adapter = (ROOT / 'native' / 'hostkit' / 'adapters' / 'rrhk_gba.c').read_text(encoding='utf-8')
        self.assertIn('getenv("RETRORECOMP_NETPLAY_LINK")', source)
        self.assertIn('RR_GBA_LINK_SEATS', source)
        self.assertIn('the link cable is refused', source)
        self.assertIn('.link_consoles = (int)rrgba_link_seats()', adapter)


if __name__ == '__main__':
    unittest.main()
