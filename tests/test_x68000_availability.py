"""The X68000 profile is offered only when its converter files are installed."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smsrecomp.x68000 import developer_available

BUNDLED = ('native/x68000_native/CMakeLists.txt', 'native/x68000_reference/CMakeLists.txt',
           'native/x68000_machine/base74/musashi/m68kconf.h', 'tools/x68000_base74.py')


class AvailabilityTests(unittest.TestCase):
    def test_bundled_files_and_importable_generators_are_both_required(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('smsrecomp.x68000.ASSETS', root):
                self.assertFalse(developer_available())
                for name in BUNDLED:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('synthetic SDK marker')
                with patch('smsrecomp.x68000.importlib.util.find_spec', return_value=None):
                    self.assertFalse(developer_available())
                with patch('smsrecomp.x68000.importlib.util.find_spec', return_value=object()):
                    self.assertTrue(developer_available())

    def test_no_libretro_checkout_is_needed(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name in BUNDLED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic SDK marker')
            self.assertFalse((root / '.deps').exists())
            with patch('smsrecomp.x68000.ASSETS', root),                     patch('smsrecomp.x68000.importlib.util.find_spec', return_value=object()):
                self.assertTrue(developer_available())


class PackagedSourceTests(unittest.TestCase):
    """A packaged converter extracts itself to a new folder on every launch."""

    def test_bundled_sources_are_copied_to_a_stable_workspace_folder(self):
        from smsrecomp import x68000_conversion as conversion
        with TemporaryDirectory() as folder:
            assets, root = Path(folder, 'extracted'), Path(folder, 'workspace')
            for name in ('native/x68000_native/CMakeLists.txt', 'tools/x68000_base74.py', 'LICENSE'):
                path = assets / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            (assets / 'tools/unrelated.py').write_text('not copied')
            with patch.object(conversion, 'ASSETS', assets), patch.object(conversion, 'ROOT', root):
                tree = conversion.sdk_tree(root / 'base')
                stamp = (tree / 'LICENSE').stat().st_mtime_ns
                self.assertEqual(conversion.sdk_tree(root / 'base'), tree)
            self.assertTrue(tree.is_relative_to(root))
            self.assertEqual((tree / 'tools/x68000_base74.py').read_text(), 'tools/x68000_base74.py')
            self.assertFalse((tree / 'tools/unrelated.py').exists())
            self.assertEqual((tree / 'LICENSE').stat().st_mtime_ns, stamp)

    def test_cmake_folder_configured_from_another_location_is_reset(self):
        from tools.x68000_native import fresh_cache
        with TemporaryDirectory() as folder:
            build, old, new = Path(folder, 'build'), Path(folder, 'old'), Path(folder, 'new')
            build.mkdir()
            (build / 'CMakeCache.txt').write_text(f'CMAKE_HOME_DIRECTORY:INTERNAL={new.as_posix()}\n')
            fresh_cache(build, new)
            self.assertTrue(build.exists())
            (build / 'CMakeCache.txt').write_text(f'CMAKE_HOME_DIRECTORY:INTERNAL={old.as_posix()}\n')
            fresh_cache(build, new)
            self.assertFalse(build.exists())


if __name__ == '__main__':
    unittest.main()
