"""The disk rewrite tool changes the container of a standard 2HD disk and nothing else (authored bytes only)."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp.x68000_media import identify_disk
from tests.test_x68000_media_formats import d88_disk as reference_d88, dim_disk, raw_disk
from tools import x68000_disk_rewrite as rewrite


class DiskRewriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.raw = raw_disk(11)

    def source(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_the_d88_is_the_layout_the_reader_documents(self):
        self.assertEqual(rewrite.d88_disk(self.raw, name=b'AUTHORED'), reference_d88(self.raw))

    def test_every_container_gives_the_same_disk(self):
        for name, data in (('a.dim', dim_disk(self.raw)), ('b.dim', dim_disk(self.raw, signature=False)),
                           ('c.xdf', self.raw), ('d.d88', reference_d88(self.raw))):
            for target in ('d88', 'xdf'):
                with self.subTest(source=name, target=target):
                    output = self.root / f'out-{name}.{target}'
                    rewrite.main([str(self.source(name, data)), '--format', target, str(output)])
                    self.assertEqual(identify_disk(output).content(), self.raw if target == 'xdf' else rewrite.raw_disk(output))
                    self.assertEqual(rewrite.raw_disk(output), self.raw)

    def test_nothing_is_overwritten_and_other_disks_are_refused(self):
        existing = self.source('there.xdf', b'kept')
        with self.assertRaises(SystemExit):
            rewrite.main([str(self.source('a.xdf', self.raw)), '--format', 'd88', str(existing)])
        self.assertEqual(existing.read_bytes(), b'kept')
        partial = bytearray(dim_disk(self.raw))
        partial[1 + 5] = 0
        partial = bytes(partial[:256]) + self.raw[:5 * 8192] + self.raw[6 * 8192:]
        with self.assertRaises(ValueError):
            rewrite.raw_disk(self.source('partial.dim', partial))


if __name__ == '__main__':
    unittest.main()
