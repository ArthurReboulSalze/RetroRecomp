"""The suite leaves the player's real Neo Geo cache of prepared cartridges alone (tests/test_legacy_compat.py once wrote it).

`unittest discover` imports every module before it runs one, and runs the modules in name order: the snapshot below is taken before any
other test, and this module is last (hence `zz`). A test that reaches `neogeo_knowledge` must patch `library_root` (or the Neo Geo
functions) as `LegacyReceiptTests` does. Run alone, the test only checks that the file did not change since this module was imported."""
import unittest

from retrorecomp import neogeo_knowledge
from retrorecomp.library import library_root


def snapshot():
    path = library_root('ng') / neogeo_knowledge.CACHE_NAME
    try:
        stat = path.stat()
    except OSError:
        return path, None
    return path, (stat.st_size, stat.st_mtime_ns)


REAL_PATH, BEFORE = snapshot()


class RealDataGuardTests(unittest.TestCase):
    def test_the_prepared_cartridge_cache_of_the_real_library_is_untouched(self):
        path, now = snapshot()
        self.assertEqual(path, REAL_PATH)
        self.assertEqual(now, BEFORE, f'a test wrote {path}: keep its library in a scratch folder (patch library_root)')


if __name__ == '__main__':
    unittest.main()
