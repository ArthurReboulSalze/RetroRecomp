"""The engine sources and SDL of core.dependencies() follow their pins (1.6.8).

A library whose .deps an earlier release made holds a checkout of the former pin (SDL 2.32.8 before 1.6.4). A clean
checkout moves to the pin; a checkout with edits, a folder that is not a checkout and an offline fetch stop the
conversion with the reason, and leave the folder as it was. The repositories are local: no network."""
import inspect
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import core, gui_updates, i18n

GIT_ENVIRONMENT = {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
                   'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
                   # A submodule cloned from a local path needs the file protocol (git 2.38.1 and later).
                   'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'protocol.file.allow', 'GIT_CONFIG_VALUE_0': 'always'}


def git(*arguments, cwd=None) -> str:
    return subprocess.run(['git', *map(str, arguments)], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class DependencyPinTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, GIT_ENVIRONMENT)
        environment.start()
        self.addCleanup(environment.stop)
        core.reset_stop()
        self.source = self.root / 'upstream'
        self.old = self.commit(self.source, 'release 2.32.8\n', init=True)
        self.url = self.root / 'SDL.git'
        git('clone', '--quiet', '--bare', self.source, self.url)
        self.checkout = self.root / '.deps' / 'SDL'
        git('clone', '--quiet', self.url, self.checkout)
        git('-C', self.checkout, 'checkout', '--quiet', '--detach', self.old)
        # The new pin reaches the upstream after the old library was cloned.
        self.new = self.commit(self.source, 'release 2.32.10\n')
        git('-C', self.source, 'push', '--quiet', self.url, 'HEAD:refs/heads/main')
        self.log = self.root / '.deps' / 'setup.log'
        self.messages = []

    def commit(self, repository: Path, text: str, *, init: bool = False) -> str:
        if init:
            git('init', '--quiet', '-b', 'main', repository)
        (repository / 'VERSION.txt').write_text(text, encoding='utf-8')
        git('-C', repository, 'add', 'VERSION.txt')
        git('-C', repository, 'commit', '--quiet', '-m', text.strip())
        return git('-C', repository, 'rev-parse', 'HEAD')

    def follow(self, url=None, revision=None, checkout=None):
        core.follow_pin(checkout or self.checkout, str(url or self.url), revision or self.new, self.log,
                        self.messages.append)

    def head(self, checkout=None) -> str:
        return git('-C', checkout or self.checkout, 'rev-parse', 'HEAD')

    def test_a_clean_checkout_of_the_former_pin_moves_to_the_pin(self):
        build = self.checkout / 'build-llvm-0123abcd'          # the SDL build and install folders are untracked
        build.mkdir()
        (build / 'CMakeCache.txt').write_text('cache', encoding='utf-8')
        self.follow()
        self.assertEqual(self.head(), self.new)
        self.assertEqual((self.checkout / 'VERSION.txt').read_text(encoding='utf-8').strip(), 'release 2.32.10')
        self.assertTrue((build / 'CMakeCache.txt').is_file())
        self.assertEqual(self.messages, ['Mise à jour de SDL vers la version épinglée…'])
        self.assertIn('fetch', self.log.read_text(encoding='utf-8'))

    def test_a_revision_already_in_the_checkout_needs_no_connection(self):
        git('-C', self.checkout, 'fetch', '--quiet', self.url, self.new)
        self.follow(url=self.root / 'offline.git')
        self.assertEqual(self.head(), self.new)

    def test_the_pinned_revision_changes_nothing(self):
        self.follow(revision=self.old, url=self.root / 'offline.git')
        self.assertEqual(self.head(), self.old)
        self.assertEqual(self.messages, [])
        self.assertFalse(self.log.exists())

    def test_local_changes_stop_the_conversion_and_are_kept(self):
        (self.checkout / 'VERSION.txt').write_text('edited\n', encoding='utf-8')
        with self.assertRaises(core.ConversionError) as caught:
            self.follow()
        self.assertIn('modifications locales', str(caught.exception))
        self.assertEqual(self.head(), self.old)
        self.assertEqual((self.checkout / 'VERSION.txt').read_text(encoding='utf-8'), 'edited\n')

    def test_an_offline_fetch_stops_the_conversion_and_keeps_the_checkout(self):
        with self.assertRaises(core.ConversionError) as caught:
            self.follow(url=self.root / 'offline.git')
        self.assertIn('Impossible de récupérer la version épinglée de SDL (' + self.new[:7] + ')', str(caught.exception))
        self.assertNotIsInstance(caught.exception, core.StopRequested)
        self.assertEqual(self.head(), self.old)

    def test_a_folder_that_is_not_a_checkout_is_neither_used_nor_replaced(self):
        folder = self.root / '.deps' / 'smsggrecomp'
        folder.mkdir()
        (folder / 'notes.txt').write_text('mine', encoding='utf-8')
        with self.assertRaises(core.ConversionError) as caught:
            self.follow(checkout=folder)
        self.assertIn('n’est pas un dépôt git', str(caught.exception))
        self.assertEqual([item.name for item in folder.iterdir()], ['notes.txt'])

    def test_a_missing_or_empty_folder_is_cloned_at_the_pin(self):
        for name in ('missing', 'empty'):
            folder = self.root / '.deps' / name
            if name == 'empty':
                folder.mkdir()
            self.follow(checkout=folder)
            self.assertEqual(self.head(folder), self.new)
        self.assertEqual(self.messages, ['Téléchargement de missing…', 'Téléchargement de empty…'])

    def test_the_submodules_follow_the_moved_engine(self):
        library = self.root / 'core'
        first = self.commit(library, 'core 1\n', init=True)
        engine = self.root / 'engine'
        git('init', '--quiet', '-b', 'main', engine)
        git('-C', engine, 'submodule', 'add', '--quiet', library, 'external/core')
        git('-C', engine, 'commit', '--quiet', '-m', 'core 1')
        old = git('-C', engine, 'rev-parse', 'HEAD')
        clone = self.root / '.deps' / 'smsggrecomp'
        git('clone', '--quiet', '--recurse-submodules', engine, clone)
        git('-C', clone, 'checkout', '--quiet', '--detach', old)
        second = self.commit(library, 'core 2\n')
        git('-C', engine / 'external/core', 'fetch', '--quiet')
        git('-C', engine / 'external/core', 'checkout', '--quiet', second)
        git('-C', engine, 'commit', '--quiet', '-am', 'core 2')
        new = git('-C', engine, 'rev-parse', 'HEAD')
        self.assertNotEqual(first, second)
        self.follow(url=engine, revision=new, checkout=clone)
        self.assertEqual(self.head(clone), new)
        self.assertEqual(self.head(clone / 'external/core'), second)
        self.assertEqual(git('-C', clone, 'status', '--porcelain', '--untracked-files=no'), '')


class DependencyPinMessageTests(unittest.TestCase):
    def test_dependencies_brings_both_pins_through_the_one_helper(self):
        source = inspect.getsource(core.dependencies)
        self.assertEqual(source.count('follow_pin('), 1)
        self.assertNotIn('rev-parse', source)
        self.assertIn('pinned_checkout(', inspect.getsource(core.follow_pin))

    def test_the_messages_are_translated_for_the_log(self):
        path = 'C:\\Retro\\.deps\\SDL'
        for french, english in (
                ('Mise à jour de SDL vers la version épinglée…', 'Updating SDL to the pinned revision…'),
                ('Impossible de récupérer la version épinglée de SDL (5d24957) depuis https://github.com/libsdl-org/SDL.git'
                 ' : vérifie la connexion, puis relance la conversion (détails dans C:\\Retro\\.deps\\setup.log).',
                 'Cannot fetch the pinned revision of SDL (5d24957) from https://github.com/libsdl-org/SDL.git: check the'
                 ' connection, then convert again (details in C:\\Retro\\.deps\\setup.log).'),
                (f'Le dossier {path} n’est pas un dépôt git : il n’est ni utilisé ni remplacé. Supprime-le pour qu’il'
                 ' soit téléchargé à nouveau.',
                 f'The folder {path} is not a git checkout: it is neither used nor replaced. Delete it so that it is'
                 ' downloaded again.'),
                (f'Le dossier {path} contient des modifications locales : il n’est ni utilisé ni remplacé. Annule-les,'
                 ' ou supprime le dossier pour qu’il soit téléchargé à nouveau.',
                 f'The folder {path} has local changes: it is neither used nor replaced. Undo them, or delete the folder'
                 ' so that it is downloaded again.'),
                ('Version inattendue de SDL : abc. Attendu : def.', 'Unexpected revision of SDL: abc. Expected: def.')):
            self.assertEqual(i18n.log_text(french), english)
            self.assertEqual(i18n.log_text(french, 'fr'), french)

    def test_the_window_names_the_update_steps_in_every_language(self):
        source = inspect.getsource(gui_updates)
        for name, key in (('smsggrecomp', 'deps_step_engine_update'), ('SDL', 'deps_step_sdl_update')):
            self.assertIn(f"'Mise à jour de {name} vers la version épinglée…': '{key}'", source)
            self.assertTrue(i18n.STRINGS[key][0] and i18n.STRINGS[key][1])
            for code in ('it', 'es', 'de', 'zh', 'ja', 'ru'):
                self.assertTrue(i18n.catalog(code)['ui'][key])


if __name__ == '__main__':
    unittest.main()
