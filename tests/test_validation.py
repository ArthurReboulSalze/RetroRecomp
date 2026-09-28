import copy
from pathlib import Path
import tempfile
import unittest

from smsrecomp.validation import compare_execution


class NativeValidationTests(unittest.TestCase):
    def test_rejects_cpu_ram_image_trace_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            native, reference = Path(tmp) / 'native', Path(tmp) / 'reference'
            for directory in (native, reference):
                directory.mkdir()
                (directory / 'frame.png').write_bytes(b'image')
                (directory / 'frame.png.ram').write_bytes(b'ram')
                (directory / 'vdp.csv').write_text('frame,cols\n1,2,3,4,5,6,7,8,9\n')
            state = dict(passed=True, completed_frames=1, requested_frames=1, final_cpu={'pc': 123, 'wz': 456})
            self.assertTrue(compare_execution(state, state, native, reference)['passed'])
            changed = copy.deepcopy(state)
            changed['final_cpu']['wz'] += 1
            self.assertFalse(compare_execution(state, changed, native, reference)['checks']['final_cpu'])
            for key, filename in (('final_ram', 'frame.png.ram'), ('final_image', 'frame.png'), ('vdp_trace', 'vdp.csv')):
                with self.subTest(key=key):
                    original = (reference / filename).read_bytes()
                    (reference / filename).write_bytes(b'different' if key != 'vdp_trace' else b'header\n9,2,3,4,5,6,7,8,9\n')
                    self.assertFalse(compare_execution(state, state, native, reference)['checks'][key])
                    (reference / filename).unlink()
                    self.assertFalse(compare_execution(state, state, native, reference)['passed'])
                    (reference / filename).write_bytes(original)
            changed = dict(state, passed=False)
            self.assertFalse(compare_execution(state, changed, native, reference)['passed'])

    def test_rejects_raster_differences_with_identical_final_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            native, reference = Path(tmp) / 'native', Path(tmp) / 'reference'
            header = 'frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h\n'
            for directory in (native, reference):
                directory.mkdir()
                (directory / 'frame.png').write_bytes(b'image')
                (directory / 'frame.png.ram').write_bytes(b'ram')
                (directory / 'vdp.csv').write_text(header + '1,2,3,4,5,6,7,8,9,10,abcd\n')
            state = dict(passed=True, completed_frames=1, requested_frames=1, final_cpu={'pc': 123})
            self.assertTrue(compare_execution(state, state, native, reference)['passed'])
            for row in ('1,2,3,4,5,6,7,8,9,10,dcba\n', '1,2,3,4,5,6,7,8,9,10\n'):
                (reference / 'vdp.csv').write_text(header + row)
                result = compare_execution(state, state, native, reference)
                self.assertFalse(result['checks']['vdp_trace'])
                self.assertFalse(result['passed'])
