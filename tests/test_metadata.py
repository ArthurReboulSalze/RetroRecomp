from pathlib import Path
import tempfile
import unittest
from smsrecomp import __version__
from smsrecomp.metadata import write_game_metadata, game_metadata


class MetadataTests(unittest.TestCase):
    def test_names_console_controls_and_generator_are_explicit(self):
        for gun in (False, True):
            metadata = game_metadata('Authored Game', gun)
            self.assertEqual(metadata['ProductName'], 'Authored Game')
            self.assertEqual(metadata['Console'], 'Master System')
            self.assertEqual(metadata['FileVersion'], __version__)
            self.assertIn(metadata['Controls'], metadata['FileDescription'])
            self.assertEqual('Light Phaser' in metadata['Controls'], gun)
            self.assertNotIn('copyright', metadata)
            regional = game_metadata('Authored Game', gun, 'pal')
            self.assertEqual(regional['VideoStandard'], 'PAL')
            self.assertIn('Master System PAL', regional['FileDescription'])

    def test_resource_survives_unicode_quotes_and_missing_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            metadata = write_game_metadata(folder, 'Été "test"\\name\nline', 'Authored Game.exe', light_phaser=False, icon=True)
            content = (folder / 'game_resources.rc').read_text(encoding='utf-8')
            self.assertIn('101 ICON "game.ico"', content)
            self.assertIn('Été ""test""\\\\name\\nline', content)
            self.assertEqual(metadata['OriginalFilename'], 'Authored Game.exe')
            write_game_metadata(folder, 'Second', 'Second.exe', light_phaser=True, icon=False)
            content = (folder / 'game_resources.rc').read_text(encoding='utf-8')
            self.assertIn('1 VERSIONINFO', content)
            self.assertNotIn(' ICON ', content)
            self.assertNotIn('Authored Game.exe', content)
