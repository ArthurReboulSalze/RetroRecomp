"""The copies of written disks (native/disk_copies.inc): its checks run when a C compiler is available (tools/disk_copies_selftest.py)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('disk_copies_selftest', ROOT / 'tools' / 'disk_copies_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class DiskCopiesTests(unittest.TestCase):
    def test_the_copies_are_read_written_and_committed_as_promised(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0, [line for line in result['lines'] if line.startswith('FAIL')])
        self.assertGreaterEqual(result['passed'], 16)

    def test_nothing_machine_specific_in_the_shared_file(self):
        text = (ROOT / 'native' / 'disk_copies.inc').read_text(encoding='utf-8')
        code = text[text.index('#ifndef RETRO_RECOMP_DISK_COPIES_INC'):].lower()     # the code, after the header's comment
        for word in ('cpc', 'msx', 'upd765', 'fdc', 'machine.'):
            self.assertNotIn(word, code)


if __name__ == '__main__':
    unittest.main()
