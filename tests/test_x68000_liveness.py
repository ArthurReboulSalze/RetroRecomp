"""The liveness record of an X68000 route is read from its trace: distinct pictures, audio blocks, RAM states, counters.

The trace is authored (made-up hashes and registers, no game): three frames, two pictures, one repeated audio block.
"""
import tempfile
import unittest
from pathlib import Path

from retrorecomp.x68000_conversion import route_liveness
from tools.x68000_reference_check import TRACE_COLUMNS


def row(frame, video, pcm, ram, pc):
    registers = ['00000000'] * 18
    registers[0] = pc
    return '\t'.join([str(frame), video * 16, pcm * 16, ram * 16, '735', '768', '512', *registers])


class RouteLivenessTests(unittest.TestCase):
    def test_distinct_pictures_audio_blocks_ram_states_and_counters_are_counted_from_the_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'trace.tsv'
            lines = ['\t'.join(TRACE_COLUMNS),
                     row(0, 'a', '1', '1', '00000010'),
                     row(1, 'b', '1', '2', '00000020'),
                     row(2, 'b', '1', '3', '00000020')]
            trace.write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
            result = route_liveness(Path(folder), 3, {'nonblack_frames': 2, 'nonzero_samples': 99})
        self.assertEqual(result, {'frames': 3, 'distinct_pictures': 2, 'distinct_audio_blocks': 1,
                                  'distinct_ram_states': 3, 'distinct_program_counters': 2,
                                  'nonblack_frames': 2, 'nonzero_samples': 99})


if __name__ == '__main__':
    unittest.main()
