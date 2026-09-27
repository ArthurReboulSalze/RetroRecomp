from pathlib import Path
import configparser
import tempfile
import unittest
from smsrecomp.i18n import tr, extended_default, log_text
from smsrecomp.paths import save_game_language
from smsrecomp.paths import games_directory, ROOT, save_preferences, export_directory, workspace_directory, data_directory
import json
from unittest.mock import patch


class LanguageTests(unittest.TestCase):
    def test_portable_default_groups_games_by_system(self):
        with patch('smsrecomp.paths.sys.frozen', True, create=True), \
                patch('smsrecomp.paths.sys.executable', str(ROOT / 'Export/Retro-Recomp.exe')):
            self.assertEqual(games_directory(), ROOT / 'Export/Games/Master System')
            self.assertEqual(games_directory('.'), ROOT / 'Export')
            self.assertEqual(games_directory('Jeux'), ROOT / 'Export/Jeux')
        self.assertEqual(games_directory(), ROOT / 'Export/Games/Master System')

    def test_packaged_export_keeps_the_project_workspace_and_shared_data(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder).resolve()
            (project / 'smsrecomp').mkdir()
            (project / 'RetroRecomp.py').write_text('')
            (project / 'smsrecomp/core.py').write_text('')
            application = project / 'Export'
            with patch('smsrecomp.paths.sys.frozen', True, create=True), \
                    patch('smsrecomp.paths.sys.executable', str(application / 'Retro-Recomp.exe')):
                self.assertEqual(workspace_directory(), project)
                self.assertEqual(export_directory(), application)
                self.assertEqual(data_directory(), application / 'datas')
                self.assertEqual(games_directory('Games/Master System'), application / 'Games/Master System')

    def test_moved_standalone_converter_does_not_add_a_second_export_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            application = Path(folder).resolve() / 'Portable'
            with patch('smsrecomp.paths.sys.frozen', True, create=True), \
                    patch('smsrecomp.paths.sys.executable', str(application / 'Retro-Recomp.exe')):
                self.assertEqual(workspace_directory(), application)
                self.assertEqual(games_directory(), application / 'Games/Master System')
                self.assertEqual(data_directory(), application / 'datas')

    def test_saving_preferences_keeps_local_output_relative(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            with patch('smsrecomp.paths.ROOT', directory):
                save_preferences({'output': str(directory / 'Export'), 'language': 'fr'})
                saved = json.loads((directory / 'Export/datas/Retro-Recomp.json').read_text())
                self.assertEqual(saved['output'], '.')
                self.assertEqual(games_directory(saved['output']), directory / 'Export')
    def test_old_default_is_upgraded_but_later_explicit_opt_out_is_preserved(self):
        self.assertTrue(extended_default({}))
        self.assertTrue(extended_default({'backend': 'functions'}))
        self.assertFalse(extended_default({'backend': 'functions', 'coverage_default_revision': 2}))
        self.assertTrue(extended_default({'backend': 'banked', 'coverage_default_revision': 2}))

    def test_user_messages_keep_variables_and_switch_language(self):
        for lang in ('en', 'fr'):
            value = tr('fallback', lang, percent=12.5, comparison='VDP')
            self.assertIn('12.5', value)
            self.assertIn('VDP', value)
        self.assertEqual(tr('start'), 'Convert / regenerate')
        self.assertEqual(tr('start', 'fr'), 'Convertir / régénérer')

    def test_conversion_log_translates_values_without_modifying_paths(self):
        path = 'C:/Jeux français/mon-jeu.exe'
        self.assertEqual(log_text('Exécutable créé : ' + path), 'Executable created: ' + path)
        self.assertEqual(log_text('demo : 100.0 % natif, 0.0 % interprété.'), 'demo: 100.0% native, 0.0% interpreted.')
        self.assertEqual(log_text('Vérification du mode strict…', 'fr'), 'Vérification du mode strict…')

    def test_shared_ini_language_update_preserves_keyboard_and_filter(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / 'jeux partagés'; data = root / 'datas'; data.mkdir(parents=True)
            ini = data / 'Retro-Recomp.ini'
            ini.write_text('[Clavier]\nbouton1=C\n[ClavierJ2]\nbouton1=V\n[Video]\nfiltre=3\n', encoding='ascii')
            for lang in ('fr', 'en'):
                save_game_language(root, lang)
                config = configparser.ConfigParser(); config.read(ini, encoding='ascii')
                self.assertEqual(config['Interface']['language'], lang)
                self.assertEqual(config['Clavier']['bouton1'], 'C')
                self.assertEqual(config['ClavierJ2']['bouton1'], 'V')
                self.assertEqual(config['Video']['filtre'], '3')
