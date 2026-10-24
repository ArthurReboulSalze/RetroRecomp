"""Reject drift before any ambiguous DMA, IRQ or old-state adaptation."""
import unittest
from retrorecomp import megadrive_dma
from retrorecomp.core import ConversionError


class DmaStagingTests(unittest.TestCase):
    def test_unknown_or_ambiguous_vdp_layout_rejected(self):
        for source in ('struct Different {};', '    RrMdVdpFifo rr_fifo;\n} GVDP;\n' * 2):
            with self.assertRaises(ConversionError):
                megadrive_dma.header(source)

    def test_unknown_snapshot_layout_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_dma.snapshot('/* Unexpected snapshot */')

    def test_unknown_machine_migration_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_dma.machine('/* Missing qualified layout */')


if __name__ == '__main__':
    unittest.main()
