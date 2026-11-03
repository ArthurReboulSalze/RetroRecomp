from pathlib import Path
import tempfile
import unittest
from retrorecomp import __version__
from retrorecomp.metadata import MANIFEST_XML, write_game_metadata, game_metadata


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


class ManifestTests(unittest.TestCase):
    """The application manifest of every game (1.6.7): inline in the resource script, standard, no behaviour change."""

    def manifest_of(self, **options):
        import re
        import xml.etree.ElementTree as ElementTree
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_game_metadata(folder, 'Authored Game', 'Authored Game.exe', light_phaser=False, icon=False, **options)
            content = (folder / 'game_resources.rc').read_text(encoding='utf-8').replace(chr(13) + chr(10), chr(10))
        block = re.search(r'^1 24\nBEGIN\n(.*?)\nEND$', content, re.S | re.M)
        self.assertIsNotNone(block, 'resource 1 of type RT_MANIFEST (24)')
        pieces = re.findall(r'^  "(.*)\\n",?$', block.group(1), re.M)
        xml = '\n'.join(pieces) + '\n'
        self.assertEqual(xml, MANIFEST_XML)
        return content, ElementTree.fromstring(xml.encode('utf-8'))

    def test_every_console_gets_the_manifest_once(self):
        from retrorecomp.systems import system_ids
        for system in system_ids():
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                write_game_metadata(folder, 'Game', 'Game.exe', light_phaser=False, icon=True, system_id=system)
                content = (folder / 'game_resources.rc').read_text(encoding='utf-8').replace(chr(13) + chr(10), chr(10))
            self.assertEqual(content.count('\n1 24\n'), 1, system)
            self.assertEqual(content.count('1 VERSIONINFO'), 1, system)

    def test_it_runs_as_the_invoker_and_names_the_windows_versions(self):
        _, root = self.manifest_of()
        ns = {'a': 'urn:schemas-microsoft-com:asm.v1', 'v3': 'urn:schemas-microsoft-com:asm.v3',
              'c': 'urn:schemas-microsoft-com:compatibility.v1'}
        level = root.find('.//v3:requestedExecutionLevel', ns)
        self.assertEqual((level.get('level'), level.get('uiAccess')), ('asInvoker', 'false'))
        self.assertEqual({e.get('Id') for e in root.findall('.//c:supportedOS', ns)},
                         {'{35138b9a-5d96-4fbd-8e2d-a2440225f93a}', '{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}',
                          '{1f676c76-80e1-4239-95bb-83d0f6d0da78}', '{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}'})

    def test_its_dpi_awareness_is_the_one_the_host_asks_sdl_for(self):
        _, root = self.manifest_of()
        settings = root.find('.//{urn:schemas-microsoft-com:asm.v3}windowsSettings')
        names = {child.tag.split('}')[1]: child.text for child in settings}
        self.assertEqual(names, {'dpiAware': 'true/pm', 'dpiAwareness': 'PerMonitorV2,PerMonitor'})
        # Nothing else that changes how a game behaves: no code page, long paths or common controls.
        for forbidden in ('activeCodePage', 'longPathAware', 'Microsoft.Windows.Common-Controls', 'gdiScaling'):
            self.assertNotIn(forbidden, MANIFEST_XML)
        host = (Path(__file__).resolve().parents[1] / 'native/hostkit/shell/rrhk_main.c').read_text(encoding='utf-8')
        self.assertIn('SDL_HINT_WINDOWS_DPI_AWARENESS, "permonitorv2"', host)

    def test_it_is_the_same_for_every_game(self):
        # The same bytes for every title, console and version of a game (a reproducible build).
        first, _ = self.manifest_of()
        second, _ = self.manifest_of(system_id='gb')
        self.assertEqual(first[first.index('1 24'):first.index('1 VERSIONINFO')],
                         second[second.index('1 24'):second.index('1 VERSIONINFO')])
