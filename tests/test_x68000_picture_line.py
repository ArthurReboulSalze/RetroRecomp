"""The X68000 frame loop never draws the "no line" marker: it indexed the line tables 4 GiB out and crashed the reference.

Found on three sets of the test collection (Tetris v5, TF4G v0.3A09 and a later start of the same family): a game that
reprograms the CRTC during a machine line makes a line visible that had been chosen as "not in the picture", and the line
drawing then received the marker. tests/x68000_picture_line_harness.c runs the rule of native/x68000_machine/glue_line.h;
the source test below checks that machine.c uses it. No ROM, disk or firmware is involved.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse(output):
    cases = {}
    for line in output.splitlines():
        name, *fields = line.split()
        cases[name] = {key: value for key, value in (field.split('=') for field in fields)}
    return cases


class PictureLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from retrorecomp.core import toolchain, ConversionError
        from retrorecomp.platforms import build_executable, cmake_target_args
        try:
            cmake, generator = toolchain()
        except ConversionError as exc:
            raise unittest.SkipTest(str(exc))
        cls.build_temp = tempfile.TemporaryDirectory(prefix='rr-x68000-line-')
        project = Path(cls.build_temp.name)
        (project / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(PictureLine LANGUAGES C)\n'
            f'add_executable(line-test "{ROOT.as_posix()}/tests/x68000_picture_line_harness.c")\n'
            f'target_include_directories(line-test PRIVATE "{ROOT.as_posix()}/native/x68000_machine")\n', encoding='utf-8')
        for command in (
            [str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator, *cmake_target_args()],
            [str(cmake), '--build', str(project / 'build'), '--config', 'Release'],
        ):
            compiled = subprocess.run(command, capture_output=True, text=True)
            if compiled.returncode:
                cls.build_temp.cleanup()
                raise RuntimeError(compiled.stdout + compiled.stderr)
        binary = build_executable(project / 'build', 'line-test')
        cls.cases = parse(subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout)

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def test_a_line_that_became_visible_during_its_machine_line_gets_the_line_the_crtc_gives_now(self):
        self.assertEqual(self.cases['marker']['value'], '4294967295')
        self.assertEqual(self.cases['marker_replaced']['line'], '16')
        self.assertEqual(self.cases['marker_replaced_step_four']['line'], '8')
        self.assertEqual(self.cases['steps'], {'one': '16', 'two': '32', 'four': '64'})

    def test_a_line_chosen_when_the_machine_line_began_is_never_changed(self):
        self.assertEqual(self.cases['chosen_kept']['line'], '5')
        self.assertEqual(self.cases['first_line_kept']['line'], '0')


class FrameLoopUsesItTests(unittest.TestCase):
    def test_the_frame_loop_takes_every_picture_line_through_the_helpers(self):
        source = (ROOT / 'native/x68000_machine/machine.c').read_text(encoding='utf-8')
        self.assertIn('VLINE = rr_glue_line_to_draw(VLINE, vline, CRTC_VSTART, CRTC_VStep);', source)
        self.assertIn('VLINE = rr_glue_picture_line(vline, CRTC_VSTART, CRTC_VStep);', source)
        self.assertIn('VLINE = RR_GLUE_NO_LINE;', source)
        self.assertIsNone(re.search(r'0xffffffffu', source), 'the marker is spelled once, in glue_line.h')


if __name__ == '__main__':
    unittest.main()
