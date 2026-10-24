import configparser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.linux_desktop import publish_launcher, retire_launcher, _argument


class LinuxDesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.exe = self.root / 'Alex Kidd café 100% $game'
        self.exe.write_bytes(b'\x7fELFtest')
        self.report_path = self.root / 'datas/reports/game/conversion-report.json'
        self.art = self.report_path.parent / 'artwork/cover-icon.png'
        self.art.parent.mkdir(parents=True)
        self.art.write_bytes(b'already validated PNG')
        self.report = {'rom': {'sha256': 'a'*64}, 'artwork': {'embedded': True}}

    @patch('retrorecomp.linux_desktop.platform.system', return_value='Linux')
    def test_cover_launcher_and_non_destructive_hidden_merge(self, _):
        (self.root / '.hidden').write_text('existing user file\n')
        path = publish_launcher(self.exe, self.report_path, self.report)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding='utf-8')
        entry = parser['Desktop Entry']
        self.assertEqual(entry['Name'], self.exe.name)
        self.assertEqual(entry['Exec'], _argument(self.exe.resolve()))
        self.assertEqual(Path(entry['Icon']).read_bytes(), self.art.read_bytes())
        self.assertEqual((self.root / '.hidden').read_text(encoding='utf-8').splitlines(), ['existing user file', self.exe.name])
        before = path.read_bytes()
        self.art.unlink()  # The persistent copy remains independent of reports.
        self.assertTrue(Path(entry['Icon']).is_file())
        self.art.write_bytes(b'replacement cover')
        self.assertEqual(publish_launcher(self.exe, self.report_path, self.report), path)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(Path(entry['Icon']).read_bytes(), b'replacement cover')
        self.assertEqual(self.exe.read_bytes(), b'\x7fELFtest')

    @patch('retrorecomp.linux_desktop.platform.system', return_value='Linux')
    def test_protect_other_launcher_and_reject_unknown_identity(self, _):
        path = self.exe.with_name(self.exe.name + '.desktop')
        path.write_text('[Desktop Entry]\nName=User launcher\n')
        with self.assertRaises(FileExistsError):
            publish_launcher(self.exe, self.report_path, self.report)
        self.assertIn('User launcher', path.read_text())
        with self.assertRaises(ValueError):
            publish_launcher(self.exe, self.report_path, {})

    @patch('retrorecomp.linux_desktop.platform.system', return_value='Windows')
    def test_windows_has_no_launcher_side_effect(self, _):
        self.assertIsNone(publish_launcher(self.exe, self.report_path, self.report))
        self.assertFalse((self.root / '.hidden').exists())
        self.assertFalse((self.root / 'datas/launchers').exists())

    @patch('retrorecomp.linux_desktop.platform.system',return_value='Linux')
    def test_retire_old_title_preserves_new_cover_and_unrelated_starters(self,_):
        old=publish_launcher(self.exe,self.report_path,self.report)
        replacement=self.exe.with_name('New title');replacement.write_bytes(self.exe.read_bytes())
        new=publish_launcher(replacement,self.report_path,self.report)
        self.exe.unlink()
        self.assertTrue(retire_launcher(self.exe,'a'*64))
        self.assertFalse(old.exists());self.assertTrue(new.is_file())
        self.assertEqual((self.root/'.hidden').read_text(encoding='utf-8').splitlines(),['New title'])
        old.write_text('[Desktop Entry]\nName=Personal\n',encoding='utf-8')
        self.assertFalse(retire_launcher(self.exe,'a'*64))
        self.assertTrue(old.is_file())
