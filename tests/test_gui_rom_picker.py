"""The ROM picker of the window offers every machine's own extension (1.7.0 shipped without the Amiga's .lha)."""
import unittest

from retrorecomp.gui_common import PROFILES
from retrorecomp.gui_queue import GENERIC_ROM_EXTENSIONS, rom_patterns


class RomPickerTests(unittest.TestCase):
    def test_every_profile_extension_and_the_generic_shapes_are_offered(self):
        offered = rom_patterns().split()
        for profile in PROFILES:
            for extension in getattr(profile, 'extensions', ()) or ():
                self.assertIn('*' + extension, offered, profile.id)
        for extension in GENERIC_ROM_EXTENSIONS:
            self.assertIn('*' + extension, offered)
        self.assertIn('*.lha', offered)
        self.assertEqual(len(offered), len(set(offered)))


if __name__ == '__main__':
    unittest.main()
