"""CPS-1 route liveness (gate G8): picture and sound activity read from a route's per-frame trace."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import cps1_conversion

BASIS, PRIME, MASK = 14695981039346656037, 1099511628211, (1 << 64) - 1


def sound_hash(samples):
    """native/cps1_main.c: xor the sample as uint16, then multiply, for every sample of the frame."""
    value = BASIS
    for sample in samples:
        value = ((value ^ (sample & 0xffff)) * PRIME) & MASK
    return value


def line(frame, image, samples):
    return f'{frame},{0:016x},{0:016x},{image:016x},{sound_hash(samples):016x},{len(samples)}'


class LivenessTests(unittest.TestCase):
    def liveness(self, lines):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'trace.csv'
            trace.write_text('\n'.join(lines) + '\n', encoding='ascii')
            return cps1_conversion.route_liveness(trace)

    def test_silence_hash_equals_the_hash_of_zero_samples(self):
        for count in (0, 1, 937, 938):
            self.assertEqual(cps1_conversion.silent_sound_hash(count), sound_hash([0] * count))

    def test_a_moving_picture_and_a_late_sound(self):
        silent, loud = [0] * 8, [0, 3, -2, 0, 0, 0, 0, 7]
        result = self.liveness([line(1, 5, silent), line(2, 5, silent), line(3, 6, silent), line(4, 6, loud),
                                line(5, 5, loud), line(6, 5, silent)])
        self.assertEqual(result, {'frames': 6, 'distinct_pictures': 2, 'picture_changes': 2, 'last_picture_change_frame': 5,
                                  'audible_frames': 2, 'last_audible_frame': 5})

    def test_a_frozen_silent_route_has_no_change_and_no_sound(self):
        silent = [0] * 4
        result = self.liveness([line(n, 9, silent) for n in range(1, 11)])
        self.assertEqual((result['picture_changes'], result['audible_frames'], result['distinct_pictures']), (0, 0, 1))

    def test_a_negative_sample_is_audible(self):
        self.assertEqual(self.liveness([line(1, 1, [-1, 0])])['audible_frames'], 1)

    def test_a_malformed_line_is_ignored(self):
        result = self.liveness(['frame,cpu,ram,image,sound,samples', 'garbage', line(1, 1, [0, 0])])
        self.assertEqual(result['frames'], 1)


if __name__ == '__main__':
    unittest.main()
