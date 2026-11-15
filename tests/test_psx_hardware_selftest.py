"""tools/psx_hardware_selftest.py without the suite or a BIOS: the disc it builds boots like a game's (a licensed volume, SYSTEM.CNF,
the program), and the log comparison starts at the test's own first line, after what the BIOS prints."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import psx_hardware_selftest as hardware          # noqa: E402
from retrorecomp import psx_disc                  # noqa: E402
from tests.test_psx_disc import psexe             # noqa: E402


class HardwareSelftestTests(unittest.TestCase):
    def test_the_disc_boots_the_program_as_a_game(self):
        with tempfile.TemporaryDirectory() as folder:
            program = psexe(size=0x1000)
            cue = hardware.disc_for(program, Path(folder))
            identity = psx_disc.describe(cue)[0]
            disc = psx_disc.open_disc(cue)
            raw = disc.raw(20)
            disc.close()
        self.assertEqual((identity.boot, identity.serial, identity.region), ('SLUS_999.99', 'SLUS-99999', 'ntsc-u'))
        self.assertEqual(identity.exe.pc, 0x80010000)
        # Mode 2 Form 1 with its EDC: the CRC of the subheader and the data, stored after them (what Beetle checks)
        edc = 0
        for value in raw[16:16 + 8 + 2048]:
            edc = hardware.EDC_TABLE[(edc ^ value) & 0xFF] ^ (edc >> 8)
        self.assertEqual(raw[15], 2)
        self.assertEqual(int.from_bytes(raw[2072:2076], 'little'), edc)
        self.assertNotEqual(raw[2076:2352], bytes(276))

    def test_the_log_comparison_starts_at_the_test(self):
        printed = 'PS-X Realtime Kernel\nKERNEL SETUP!\ntimers test\nA: 1\nB: 2\n'
        found = hardware.log_match(printed, 'timers test\nA: 1\nB: 3\n')
        self.assertEqual((found['lines_expected'], found['equal']), (3, 2))
        self.assertEqual(found['first_difference'], {'line': 3, 'expected': 'B: 3', 'printed': 'B: 2'})


if __name__ == '__main__':
    unittest.main()
