import unittest
from smsrecomp.peripherals import LIGHT_PHASER_GAMES, light_phaser_game, game_tags


class PeripheralTests(unittest.TestCase):
    def test_cartridge_catalogue_survives_renaming(self):
        for game in LIGHT_PHASER_GAMES:
            for crc in game.crcs:
                self.assertEqual(light_phaser_game(crc, "renamed.sms"), game)

    def test_assault_city_editions_do_not_conflict(self):
        self.assertIsNone(light_phaser_game(0x0BD8DA96, "Assault City (Light Phaser).sms"))
        self.assertIsNone(light_phaser_game(0, "Assault City (Europe).sms"))
        self.assertIsNotNone(light_phaser_game(0, "Assault City (Europe) (Light Phaser).sms"))
        self.assertIsNotNone(light_phaser_game(0x861B6E79, "Assault City.sms"))

    def test_filename_fallback_requires_full_title(self):
        self.assertIsNotNone(light_phaser_game(0, "Wanted! (USA, Europe).sms"))
        self.assertIsNotNone(light_phaser_game(0, "Hang On - Safari Hunt (USA).sms"))
        self.assertIsNotNone(light_phaser_game(0, "Rambo 3.sms"))
        self.assertIsNone(light_phaser_game(0, "Aerial Assault (USA).sms"))
        self.assertIsNone(light_phaser_game(0, "Safari Hunting.sms"))
        self.assertIsNone(light_phaser_game(0, "Not Wanted.sms"))

    def test_optional_gun_mode_is_explicit(self):
        self.assertTrue(light_phaser_game(0x0CA95637, "Laser Ghost.sms").trigger_on_p2)
        self.assertFalse(light_phaser_game(0x5FC74D2A, "Gangster Town.sms").trigger_on_p2)

    def test_known_overdump_retains_gun_support_after_rename(self):
        game = light_phaser_game(0xC5083000, 'renamed.sms')
        self.assertEqual(game.title, 'Hang-On & Safari Hunt')

    def test_t2_sms_and_other_pad_shooters_are_not_gun_games(self):
        for crc, name in [(0x93CA8152, 'T2 - The Arcade Game (Europe).sms'),
                          (0xAC56104F, 'Terminator 2 - Judgment Day (Europe).sms'),
                          (0x0BD8DA96, 'Assault City (Light Phaser).sms')]:
            with self.subTest(name=name):
                self.assertIsNone(light_phaser_game(crc, name))
                self.assertEqual(game_tags(crc, name), ())

    def test_documented_homebrew_and_diagnostics_do_not_tag_old_versions(self):
        for name in ('Porkpolis.sms', 'Shootagem.sms', 'Shooting Stars.sms',
                     'Die Hard 2.sms', 'SMS-A-Sketch (v1.2).sms'):
            with self.subTest(name=name):
                self.assertIsNotNone(light_phaser_game(0, name))
        self.assertEqual(light_phaser_game(0x7253C3EC, 'renamed.sms').title, 'Color & Switch Test')
        for name in ('SMS-A-Sketch.sms', 'SMS-A-Sketch (v1.1).sms', 'Shootagem 2.sms'):
            self.assertIsNone(light_phaser_game(0, name))

    def test_tags_identify_gun_support_not_shooter_genre_or_cover_title(self):
        self.assertEqual(game_tags(0x5FC74D2A, "renamed.sms"), ("shooting",))
        self.assertEqual(game_tags(0, "Wanted (Europe).sms"), ("shooting",))
        self.assertEqual(game_tags(0, "Bomber Raid.sms"), ())
        self.assertEqual(game_tags(0x0BD8DA96, "Assault City (Light Phaser).sms"), ())


if __name__ == "__main__":
    unittest.main()
