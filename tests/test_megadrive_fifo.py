"""Guard source drift: never silently stage a partially adapted VDP."""
import unittest
from smsrecomp import megadrive_fifo
from smsrecomp.core import ConversionError


class FifoStagingTests(unittest.TestCase):
    def test_missing_or_duplicated_guest_layout_is_rejected(self):
        for source in ('struct Different {};', '} GVDP;\n} GVDP;'):
            with self.assertRaises(ConversionError):
                megadrive_fifo.header(source)

    def test_missing_memory_hook_is_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_fifo.vdp('void gvdp_write_data(void) {}')

    def test_missing_snapshot_guard_is_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_fifo.snapshot('/* An unknown machine layout. */')


if __name__=='__main__':unittest.main()
