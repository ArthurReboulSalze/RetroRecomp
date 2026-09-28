from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from smsrecomp.batch import identify
from smsrecomp.core import ConversionError
from smsrecomp.nes import _probe, read_nes_rom
from smsrecomp.systems import profile_for_path


def cartridge(*, nes2=False, timing=0, battery=False):
    header = bytearray(16)
    header[:4] = b'NES\x1a'
    header[4] = 2
    header[5] = 1
    if nes2:
        header[7] = 0x08
        header[12] = timing
    if battery:
        header[6] |= 0x02
    return bytes(header) + bytes(2 * 16384 + 8192)


class NesProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_nes_zip_detected_without_writing_beside_source(self):
        source = self.root / 'Sample.zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('Sample.nes', cartridge())
        before = source.read_bytes()
        self.assertEqual(profile_for_path(source).id, 'nes')
        self.assertEqual(identify(source).system, 'nes')
        self.assertEqual(read_nes_rom(source).mapper, 0)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_headered_bin_and_nes2_timing_are_separate_from_game_boy(self):
        source = self.root / 'Sample.bin'
        source.write_bytes(cartridge(nes2=True, timing=1))
        self.assertEqual(profile_for_path(source).id, 'nes')
        self.assertEqual(identify(source).video_hint, 'pal')
        self.assertEqual(read_nes_rom(source).video_standard, 'pal')

    def test_size_mismatch_is_rejected_before_compilation(self):
        source = self.root / 'Broken.nes'
        source.write_bytes(cartridge()[:-1])
        with self.assertRaisesRegex(ConversionError, 'declares'):
            read_nes_rom(source)

    def test_probe_accepts_zero_fallback_and_counts_other_interpretation(self):
        executable = self.root / 'game.exe'
        seed = self.root / 'seeds.trace'
        with patch('smsrecomp.nes.run', return_value='mode=native frames=1 cycles=100 native_cycles=100 (100.0%)'):
            self.assertEqual(_probe(executable, self.root, 'boot', 1, seed)['interpreter_cycles'], 0)
        output = ('mode=native frames=1 cycles=100 native_cycles=90 (90.0%)\n'
                  '  interpreted: ROM 2 (2.0%)  RAM 3 (3.0%)  $2000-$7FFF 4 (4.0%)\n')
        with patch('smsrecomp.nes.run', return_value=output):
            self.assertEqual(_probe(executable, self.root, 'boot', 1, seed)['interpreter_cycles'], 9)


if __name__ == '__main__':
    unittest.main()
