"""Region qualification tests using authored cartridge headers only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from smsrecomp import supernintendo, snes_timing
from smsrecomp.cartridge16 import read_snes_rom
from smsrecomp.console16 import conversion_rom, reference_differences
from smsrecomp.core import ConversionError
from smsrecomp.systems import profile_for_path


def authored(region, hirom=False):
    data = bytearray(65536)
    offset = 0xffc0 if hirom else 0x7fc0
    data[offset:offset + 21] = b'RR REGION FIXTURE'.ljust(21, b' ')
    data[offset + 21] = 0x21 if hirom else 0x20
    data[offset + 23] = 6
    data[offset + 25] = region
    data[offset + 28:offset + 32] = bytes.fromhex('cbed3412')
    data[offset + 60:offset + 62] = bytes.fromhex('0080')
    return bytes(data)


class SnesTimingTests(unittest.TestCase):
    def test_exact_region_controls_profile_and_generated_timing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for region, standard in ((1, 'ntsc'), (2, 'pal')):
                for mapping in ('lorom', 'hirom'):
                    with self.subTest(standard=standard, mapping=mapping):
                        # The misleading filename must never override the header.
                        path = root / f'Fixture ({"USA" if standard == "pal" else "Europe"}).zip'
                        payload = authored(region, mapping == 'hirom')
                        with ZipFile(path, 'w') as archive:
                            archive.writestr('authored.sfc', payload)
                        original = path.read_bytes()
                        rom = read_snes_rom(path)
                        profile = dict(id='authored', title='Authored', legacy_functions=False,
                                       mapping=mapping, standard=standard)
                        with patch.dict(supernintendo.PROFILES, {rom.sha256: profile}):
                            self.assertEqual(conversion_rom(path, 'snes').standard, standard)
                            self.assertEqual(supernintendo.video_standard(rom, standard), standard)
                            wrong = 'ntsc' if standard == 'pal' else 'pal'
                            with self.assertRaisesRegex(ConversionError, f'requires {standard.upper()} timing'):
                                conversion_rom(path, 'snes', wrong)
                            supernintendo.write_profile(root, rom, 'Authored')
                            header = (root / 'retro_snes_game.h').read_text()
                            self.assertIn(f'#define RR_SN_PAL {int(standard == "pal")}', header)
                            with patch.dict(profile, standard=wrong):
                                with self.assertRaises(ConversionError):
                                    supernintendo.profile_for(rom)
                            with patch.dict(profile, mapping='hirom' if mapping == 'lorom' else 'lorom'):
                                with self.assertRaises(ConversionError):
                                    supernintendo.profile_for(rom)
                        self.assertEqual(path.read_bytes(), original)
                        self.assertEqual(read_snes_rom(path).data, payload)
                        self.assertIn('pal', profile_for_path(path).video_modes)

    def test_pal_timing_diagnostics_must_agree(self):
        # Existing complete validation compares architectural data as well;
        # this test specifically checks that absent region evidence cannot pass.
        fields = ('video_standard', 'field_lines', 'ppu_pal', 'overscan_seen',
                  'interlace_seen', 'hires_seen')
        native = dict(zip(fields, ('pal', 312, 1, 0, 0, 0)))
        for field in fields:
            reference = dict(native)
            reference.pop(field)
            self.assertIn(field, reference_differences('snes', native, reference))

    def test_timing_adapter_rejects_changed_or_ambiguous_hooks(self):
        for adapter in (snes_timing.apu_clock, snes_timing.frame_driver, snes_timing.bus,
                        snes_timing.ppu, snes_timing.bridge, snes_timing.runtime):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaisesRegex(ConversionError, 'Pinned SNES timing hook changed'):
                    adapter('/* unsupported engine revision */')
        with self.assertRaises(ConversionError):
            snes_timing.frame_driver('#define BFD_MASTER_CYCLES_PER_FIELD 357368ull\n' * 2)

    def test_pal_cpu_agreement_does_not_bypass_activity_and_video_gates(self):
        profile = dict(video_scope='progressive_224')
        active = dict(frames=3600, overscan_seen=0, interlace_seen=0, hires_seen=0,
                      visible_frames=3500, pcm_nonzero=10000)
        supernintendo.validate_activity(profile, [active])
        for field in ('overscan_seen', 'interlace_seen', 'hires_seen'):
            with self.subTest(field=field), self.assertRaisesRegex(ConversionError, 'video mode'):
                supernintendo.validate_activity(profile, [dict(active, **{field: 1})])
            missing = dict(active)
            missing.pop(field)
            with self.assertRaises(ConversionError):
                supernintendo.validate_activity(profile, [missing])
        for field in ('visible_frames', 'pcm_nonzero'):
            with self.subTest(field=field), self.assertRaisesRegex(ConversionError, 'remains unqualified'):
                supernintendo.validate_activity(profile, [dict(active, **{field: 0})])
        # A short boot can legitimately precede both the first picture and sound.
        supernintendo.validate_activity(profile, [dict(active, frames=1, visible_frames=0, pcm_nonzero=0)])


if __name__ == '__main__':
    unittest.main()
