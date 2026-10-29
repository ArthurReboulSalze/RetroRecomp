"""A DMA channel start on the X68000 machine base: the adapted x68k/dmac.c against authored bus bytes.

tests/x68000_dmac_harness.c is linked with the real dmac.c produced by tools/x68000_base74.py from the pinned
hissorii/px68k checkout. No ROM, disk or firmware is involved; the bus is a few authored bytes and the device is a flag.
"""
import unittest

from tests.x68000_base_harness import build_and_run


class DmacChannelStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build, cls.cases = build_and_run('x68000_dmac_harness.c', ['x68k/dmac.c'])

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def test_a_start_on_an_active_channel_restarts_it_instead_of_a_timing_error(self):
        armed, restarted = self.cases['armed'], self.cases['restart_on_active_channel']
        self.assertEqual((armed['csr'], armed['cer'], armed['mtc']), ('08', '00', '4'))
        self.assertEqual((restarted['csr'], restarted['cer'], restarted['mtc'], restarted['mar']),
                         ('08', '00', '3', '01001'))

    def test_a_start_clears_a_completion_the_game_did_not_acknowledge(self):
        first = self.cases['first_transfer']
        again = self.cases['start_with_completion_not_acknowledged']
        self.assertEqual((first['csr'], first['cer'], first['mtc']), ('80', '00', '0'))
        self.assertEqual((again['csr'], again['cer'], again['mtc']), ('80', '00', '0'))
        self.assertEqual(again['interrupts'], '2')

    def test_the_other_start_errors_are_unchanged(self):
        zero = self.cases['zero_count']
        self.assertEqual((zero['csr'], zero['cer']), ('90', '0d'))
        abort = self.cases['software_abort']
        self.assertEqual((abort['csr'], abort['cer']), ('90', '11'))


if __name__ == '__main__':
    unittest.main()
