import unittest
from smsrecomp import megadrive_read
from smsrecomp.core import ConversionError


class ReadStagingTests(unittest.TestCase):
    def test_unknown_or_ambiguous_header_rejected(self):
        for source in ('struct Unknown {};', '    RrMdVdpIrq rr_irq;\n} GVDP;' * 2):
            with self.assertRaises(ConversionError):
                megadrive_read.header(source)

    def test_unknown_vdp_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_read.vdp('/* unknown */')

    def test_unknown_snapshot_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_read.snapshot('/* unknown */')

    def test_unknown_machine_rejected(self):
        with self.assertRaises(ConversionError):
            megadrive_read.machine('/* unknown */')
