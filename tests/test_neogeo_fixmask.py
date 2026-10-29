"""The Neo Geo fix-layer edge-mask detector (native/neogeo_fixmask.h), without any ROM.

native/neogeo_fixmask_checks.c runs the real detector and latch on synthetic fix tiles, palettes and pictures: a coloured
mask is painted black after 30 matching frames, a black mask, a picture, a flash and a partly filled column are never
touched, a latched band is released after 120 frames that do not match, and the frame the validation hashes read is never
written. The test builds and runs it through tools/neogeo_fixmask_selftest.py.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FixMaskDetectorTests(unittest.TestCase):
    def test_detector_and_latch_on_synthetic_data(self):
        done = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/neogeo_fixmask_selftest.py')],
                              capture_output=True, text=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1]), {'neogeo_fixmask': 'ok'})

    def test_the_view_is_the_only_consumer_of_the_detector(self):
        # The pixels the validation hashes, the reference runs and the image dump read stay rr16_pixels(): only the
        # host kit's adapter shows the painted view.
        adapter = (ROOT / 'native/hostkit/adapters/rrhk_ng.c').read_text(encoding='utf-8')
        self.assertIn('.pixels = view_pixels', adapter)
        host = (ROOT / 'native/neogeo_host.c').read_text(encoding='utf-8')
        self.assertNotIn('fixmask', host)
        main = (ROOT / 'native/console16_main.c').read_text(encoding='utf-8')
        self.assertNotIn('fixmask', main)


if __name__ == '__main__':
    unittest.main()
