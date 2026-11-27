"""A test run never writes the player's real Export/datas (account-player.json, shop-catalog.json, BoxArt/<system>/).

The resolver (paths.data_directory) gives a test process a scratch folder of its own; these tests call the real
writers with no patch at all and check where the files land. The positive control shows the check itself trips
when the resolver is made to hand out the real folder."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import online, paths


def inside(path: Path, folder: Path) -> bool:
    return Path(path).resolve().is_relative_to(Path(folder).resolve())


def reaches_real_data(path: Path) -> bool:
    """The guard: True when `path` is in the player's real datas folder."""
    return inside(path, paths.real_data_directory())


class DataDirectoryGuard(unittest.TestCase):
    def test_this_run_is_a_test_run_with_a_scratch_folder(self):
        self.assertTrue(paths.running_tests())
        self.assertFalse(reaches_real_data(paths.data_directory()))
        self.assertTrue(paths.data_directory().is_dir())

    def test_environment_variable_wins(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {paths.DATA_DIRECTORY_VARIABLE: folder}):
            self.assertEqual(paths.data_directory(), Path(folder))
            self.assertEqual(paths.boxart_cache_directory('cpc'), Path(folder) / 'BoxArt' / 'cpc')

    def test_explicit_root_is_kept(self):
        self.assertEqual(paths.data_directory(Path('x')), Path('x') / 'datas')

    def test_account_caches_land_in_scratch(self):
        for path in (online._account_path(), online._player_path(), online._shop_path(), online._avatar_path()):
            self.assertFalse(reaches_real_data(path), path)
        online._write_bytes(online._player_path(), b'{}')
        online._write_bytes(online._shop_path(), b'{}')
        try:
            self.assertTrue(online._player_path().is_file())
            self.assertTrue(inside(online._shop_path(), paths.data_directory()))
        finally:
            online._player_path().unlink(missing_ok=True)
            online._shop_path().unlink(missing_ok=True)

    def test_cover_cache_lands_in_scratch_for_every_console(self):
        from retrorecomp.systems import ALL_PROFILES
        for profile in ALL_PROFILES:
            self.assertFalse(reaches_real_data(paths.boxart_cache_directory(profile.id)), profile.id)

    def test_cover_cache_write_follows_the_redirect(self):
        cache = paths.boxart_cache_directory('zxs')
        self.assertTrue(inside(cache, paths.data_directory()))
        self.assertFalse(reaches_real_data(cache))

    def test_positive_control_the_guard_catches_the_real_folder(self):
        """With the redirect off (not a test run, no variable) the resolver gives the real folder and the guard trips."""
        environment = {k: v for k, v in os.environ.items() if k != paths.DATA_DIRECTORY_VARIABLE}
        with patch.dict(os.environ, environment, clear=True), patch.object(paths, 'running_tests', return_value=False):
            self.assertTrue(reaches_real_data(online._player_path()))
            self.assertTrue(reaches_real_data(online._shop_path()))
            self.assertTrue(reaches_real_data(paths.boxart_cache_directory('coleco')))
        # and the check is not fooled by a scratch path beside it
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(reaches_real_data(Path(folder) / 'datas' / 'shop-catalog.json'))


if __name__ == '__main__':
    unittest.main()
