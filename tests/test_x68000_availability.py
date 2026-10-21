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


if __name__ == '__main__':
    unittest.main()
