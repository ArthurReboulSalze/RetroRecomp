"""Neo Geo: the code a reference run observed and could not keep is counted and reported, never silent (1.7.3)."""
import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import neogeo_conversion

NATIVE = Path(__file__).resolve().parents[1] / 'native'


def write_project(folder, **routes):
    discovery = Path(folder) / 'native-discovery'
    discovery.mkdir()
    for name, report in routes.items():
        (discovery / f'{name}-reference.json').write_text(json.dumps(report), encoding='utf-8')
    return Path(folder)


def clean(**extra):
    return {'variant_cap': 4096, 'm68k_ram_variants': [{'offset': 2, 'words': '4e71'}], 'z80_variants': [],
            'm68k_ram_observations_truncated': False, 'm68k_ram_variants_dropped': 0, 'z80_variants_dropped': 0, **extra}


class DiscoveryLimitsTests(unittest.TestCase):
    def limits(self, **routes):
        notes = []
        with tempfile.TemporaryDirectory() as folder:
            result = neogeo_conversion.discovery_limits(write_project(folder, **routes), notes.append)
        return result, notes

    def test_nothing_dropped_says_nothing(self):
        result, notes = self.limits(attract=clean(), play=clean())
        self.assertFalse(result['observed_code_dropped'])
        self.assertEqual((result['m68k_ram_variants_dropped'], result['z80_variants_dropped']), (0, 0))
        self.assertIs(result['m68k_ram_observations_truncated'], False)
        self.assertEqual(notes, [])
        self.assertEqual(result['routes']['attract']['m68k_ram_variants'], 1)

    def test_dropped_z80_variants_are_reported_and_announced(self):
        result, notes = self.limits(attract=clean(), play=clean(z80_variants_dropped=7))
        self.assertTrue(result['observed_code_dropped'])
        self.assertEqual(result['z80_variants_dropped'], 7)
        self.assertEqual(result['routes']['play']['z80_variants_dropped'], 7)
        self.assertEqual(result['routes']['attract']['z80_variants_dropped'], 0)
        self.assertEqual(len(notes), 1)
        self.assertIn('counted interpreter fallback', notes[0])

    def test_the_m68k_flag_is_read_and_the_figure_is_a_maximum_not_a_sum(self):
        result, notes = self.limits(a=clean(m68k_ram_observations_truncated=True, m68k_ram_variants_dropped=5),
                                    b=clean(m68k_ram_observations_truncated=True, m68k_ram_variants_dropped=9), c=clean())
        self.assertIs(result['m68k_ram_observations_truncated'], True)
        self.assertEqual(result['m68k_ram_variants_dropped'], 9)
        self.assertTrue(result['observed_code_dropped'])
        self.assertEqual(len(notes), 1)

    def test_a_flag_without_a_count_still_counts_as_dropped(self):
        report = clean(m68k_ram_observations_truncated=True)
        del report['m68k_ram_variants_dropped']
        result, notes = self.limits(a=report)
        self.assertTrue(result['observed_code_dropped'])
        self.assertIsNone(result['m68k_ram_variants_dropped'])

    def test_a_report_without_the_fields_reads_none_never_zero(self):
        result, notes = self.limits(a={'m68k_ram_variants': [], 'z80_variants': []})
        self.assertIsNone(result['m68k_ram_variants_dropped'])
        self.assertIsNone(result['z80_variants_dropped'])
        self.assertIsNone(result['m68k_ram_observations_truncated'])
        self.assertFalse(result['observed_code_dropped'])
        self.assertEqual(result['variant_cap'], neogeo_conversion.VARIANT_CAP)

    def test_the_cap_is_the_one_the_executable_wrote(self):
        result, _ = self.limits(a=clean(variant_cap=8))
        self.assertEqual(result['variant_cap'], 8)


class NativeSourceTests(unittest.TestCase):
    """The executable's side, read from the source (a conversion shows the figures end to end)."""

    def test_every_drop_is_counted_and_written(self):
        reference = (NATIVE / 'neogeo_reference.c').read_text(encoding='utf-8')
        main = (NATIVE / 'neogeo_main.c').read_text(encoding='utf-8')
        self.assertIn('else ++rr_ng_z80_variants_dropped;', reference)
        self.assertIn('rr_ng_ram_observations_truncated=1;++rr_ng_ram_variants_dropped;', reference)
        for key in ('variant_cap', 'm68k_ram_observations_truncated', 'm68k_ram_variants_dropped', 'z80_variants_dropped'):
            self.assertIn(f'\\"{key}\\"', main)

    def test_the_cap_is_one_macro_and_the_arrays_are_not_smaller_than_it(self):
        header = (NATIVE / 'neogeo_reference.h').read_text(encoding='utf-8')
        self.assertIn('#define RR_NG_VARIANT_CAP 4096', header)
        self.assertIn('RrNgZ80Variant rr_ng_z80_variants[4096]', header)
        self.assertIn('RrNgRamVariant rr_ng_ram_variants[4096]', header)
        reference = (NATIVE / 'neogeo_reference.c').read_text(encoding='utf-8')
        self.assertNotIn('<4096', reference.replace('rr_ng_z80_variants[4096]', ''))


if __name__ == '__main__':
    unittest.main()
