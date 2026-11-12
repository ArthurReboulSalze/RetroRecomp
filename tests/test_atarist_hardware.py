"""Atari ST hardware checks (gate G11): the ROM-free, compiler-free parts of tools/atarist_hardware_check.py and its assembler.

The measurements themselves boot authored 68000 programs on the adapted Hatari and take seconds once the core is built:
`python -B tools/atarist_hardware_check.py` (BUILDING.md). The integration test below runs them only when a current build of the
core already exists in the workspace and a compiler is available; otherwise it skips (it never builds Hatari)."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


asm = load('atarist_hardware_asm')
check = load('atarist_hardware_check')


def words(source: str, origin: int = 0x1000) -> str:
    return asm.Assembler(origin).assemble(source).hex()


class AssemblerTests(unittest.TestCase):
    def test_encodings_match_the_programmers_reference_manual(self):
        # (source, bytes): each is the encoding the Motorola M68000 Family Programmer's Reference Manual gives for the form
        known = {
            'move.b #$0a,$ff8001': '13fc000a00ff8001',     # the MMU configuration write of every ST reset
            'bra.s *': '60fe', 'nop': '4e71', 'rte': '4e73', 'rts': '4e75', 'stop #$2700': '4e722700',
            'moveq #0,d0': '7000', 'moveq #-1,d3': '76ff', 'move.w #$2700,sr': '46fc2700', 'move.w sr,d0': '40c0',
            'ori.w #$700,sr': '007c0700', 'andi.w #$f8ff,sr': '027cf8ff',
            'lea $20000,a7': '4ff900020000', 'addq.w #1,d0': '5240', 'subq.l #1,d2': '5382', 'dbra d0,*': '51c8fffe',
            'btst #5,$fffa01': '0839000500fffa01', 'move.l d0,-(sp)': '2f00', 'move.l (sp)+,d0': '201f', 'clr.l $1000.w': '42b81000',
            'cmp.w #$10,d1': '0c410010', 'cmp.w d1,d2': 'b441', 'lsr.w #4,d0': 'e848', 'lsl.l #2,d1': 'e589', 'lsr.l d1,d0': 'e2a8',
            'add.w d0,(a0)': 'd150', 'move.w d1,(a2)+': '34c1', 'move.w 4(a1),d3': '36290004', 'eor.w d1,d2': 'b342',
            'move.b $ff8800,d0': '103900ff8800', 'swap d3': '4843', 'mulu d1,d2': 'c4c1', 'tst.w d4': '4a44', 'neg.w d1': '4441',
            'sub.l d1,d2': '9481', 'move.l #$12345678,$70': '23fc1234567800000070', 'adda.l d0,a0': 'd1c0', 'bne.s *': '66fe',
        }
        for source, expected in known.items():
            with self.subTest(source):
                self.assertEqual(words(source), expected)

    def test_branches_are_relative_to_the_instruction_plus_two(self):
        self.assertEqual(words('x: nop\n bne.s x\n'), '4e7166fc')
        self.assertEqual(words('bra x\nx: nop\n'), '60000002' + '4e71')
        self.assertEqual(words('x: nop\n bsr x\n'), '4e71' + '6100fffc')
        self.assertEqual(words('x: dbra d3,x\n'), '51cbfffe')

    def test_a_form_it_does_not_know_is_refused_not_guessed(self):
        for bad in ('frobnicate d0', 'move.b a0,d0', 'moveq #300,d0', 'addq.w #9,d0', 'bne.s far\n' + 'nop\n' * 200 + 'far: nop', 'add.w d0,a1', 'move.w d0'):
            with self.subTest(bad), self.assertRaises(asm.AssemblyError):
                words(bad)

    def test_labels_data_and_symbols(self):
        program = asm.Assembler(0x2000, {'REG': 0xff8800}).assemble('start: move.b #1,REG\n lea table,a0\ntable: dc.w $1234,5\n dc.b 1,2,3\n even\n dc.l table\n')
        self.assertEqual(program.hex(), '13fc000100ff8800' + '41f9' + '0000200e' + '1234' + '0005' + '010203' + '00' + '0000200e')
        with self.assertRaises(asm.AssemblyError):
            asm.Assembler(0).assemble('a: nop\na: nop\n')
        with self.assertRaises(asm.AssemblyError):
            asm.Assembler(0).assemble('bra nowhere\n')


class ProgramTests(unittest.TestCase):
    def test_every_program_assembles_into_a_tos_shaped_image_without_firmware(self):
        images = {
            'timer': check.timer_program(2, 1, 0, 50, b_data=1), 'picture': check.picture_program(), 'psg': check.psg_program(254),
            'ikbd': check.ikbd_program([0x12, 0x14]), 'wd1772': check.wd_program(),
        }
        for name, image in images.items():
            with self.subTest(name):
                self.assertEqual(len(image), check.TOS_BYTES)
                self.assertEqual(image[:4].hex(), '601e0104')                       # the header the vector harness builds too
                self.assertEqual(image[4:12].hex(), '00fc002000fc0000')              # reset PC and ROM base
                self.assertEqual(image[0x20:0x28].hex(), '13fc000a00ff8001')         # MMU first, or RAM is partly unmapped
                self.assertEqual(image[0x20 + 0x4000:], bytes(check.TOS_BYTES - 0x20 - 0x4000))   # the program is small; the rest of the image is zeros

    def test_the_disk_is_authored_and_has_every_sector_different(self):
        image = check.disk_image()
        self.assertEqual(len(image), 737280)
        sectors = {image[n * 512:(n + 1) * 512] for n in range(1440)}
        self.assertEqual(len(sectors), 1440)
        self.assertEqual(check.lba_of(0, 0, 1), 0)
        self.assertEqual(check.lba_of(79, 1, 9), 1439)
        self.assertEqual(check.lba_of(40, 1, 7), 80 * 9 + 9 + 6)


class ExpectedValueTests(unittest.TestCase):
    """The expected numbers come from the documents, by arithmetic that is checked here against the figures the documents print."""

    def test_the_pal_frame_is_313_lines_of_512_cycles_and_the_cpu_clock_is_the_crystal_over_four(self):
        self.assertEqual(check.FRAME_CYCLES_50, 160256)
        self.assertEqual(check.CPU_HZ, 8021247)
        self.assertAlmostEqual(check.CPU_HZ / check.FRAME_CYCLES_50, 50.0527, places=3)       # the PAL ST's field rate
        self.assertEqual(check.LINE_CYCLES_60, 508)

    def test_the_prescalers_are_the_seven_of_the_mfp(self):
        self.assertEqual(sorted(check.PRESCALERS.values()), [4, 10, 16, 50, 64, 100, 200])
        for code, data in check.PRESCALER_DATA.items():
            self.assertLessEqual(check.PRESCALERS[code] * (data or 256), 12800)

    def test_the_psg_clock_is_the_crystal_over_sixteen_and_the_tone_formula_is_clock_over_sixteen_tp(self):
        self.assertEqual(check.PSG_HZ, 2005311.75)
        self.assertAlmostEqual(2_000_000 / (16 * 284), 440.1, places=1)          # the ST's A440 with TP = 284 (nominal clock)

    def test_the_picture_pattern_gives_the_documented_colour_indices(self):
        indices = check.expected_indices()
        self.assertEqual((len(indices), len(indices[0])), (200, 320))
        self.assertEqual(indices[0][:16], list(range(16)))                      # chunk 0 of line 0: pixel k has index k
        self.assertEqual(indices[1][:16], [k ^ 1 for k in range(16)])
        self.assertEqual(indices[0][16:32], [k ^ 1 for k in range(16)])         # chunk 1 of line 0
        self.assertEqual(len(set(check.PALETTE)), 16)
        for word in check.PALETTE:
            self.assertEqual(word & ~0x777, 0)                                  # 3 bits per component

    def test_the_planes_of_the_pattern_are_the_documented_words(self):
        # pixel k has index k: plane 0 holds the odd pixels, plane 1 the pixels 2,3,6,7.., plane 2 the pixels 4-7 and 12-15, plane 3 the last eight
        words_ = [sum(((k >> plane) & 1) << (15 - k) for k in range(16)) for plane in range(4)]
        self.assertEqual(words_, [0x5555, 0x3333, 0x0F0F, 0x00FF])


class AnalysisTests(unittest.TestCase):
    def test_rising_crossings_are_interpolated_and_need_hysteresis(self):
        square = ([-100] * 10 + [100] * 10) * 5
        crossings = check.rising_crossings(square, 0, 20)
        self.assertEqual(len(crossings), 5)
        self.assertAlmostEqual((crossings[-1] - crossings[0]) / 4, 20, places=6)
        noisy = [-100, 3, -2, 1, 100] * 3 + [-100]
        self.assertEqual(len(check.rising_crossings(noisy, 0, 20)), 3)           # the wobble around zero is not a new cycle
        self.assertAlmostEqual(check.rising_crossings([-10, 30], 10, 5)[0], 0.5)

    def test_timer_ticks_count_reloads_the_pending_reload_and_the_part_of_the_countdown(self):
        row = {'a_ints': 3, 'a_counter': 100, 'a_pending': 0}
        self.assertEqual(check.timer_ticks(row, 0), 3 * 256 + 156)
        self.assertEqual(check.timer_ticks(dict(row, a_pending=1), 0), 4 * 256 + 156)
        self.assertEqual(check.timer_ticks({'a_ints': 0, 'a_counter': 0, 'a_pending': 0}, 0), 0)    # a counter that reads 0 is a fresh 256
        self.assertEqual(check.timer_ticks({'a_ints': 2, 'a_counter': 20, 'a_pending': 0}, 64), 2 * 64 + 44)

    def test_the_ikbd_gaps_are_the_back_to_back_bytes_only(self):
        self.assertEqual(check.packet_gaps([(0, 1), (20, 2), (40, 3), (4000, 4), (4020, 5)]), [20, 20, 20])

    def test_an_unrecorded_difference_fails_and_a_recorded_one_that_vanished_fails(self):
        row = lambda name, verdict: check.finding(name, 'x', 'ym2149', 1, 2, verdict)       # noqa: E731
        self.assertEqual(check.problems([row('a', 'agree'), row('b', 'inconclusive')]), [])
        self.assertTrue(check.problems([row('a', 'differ')]))
        recorded = next(iter(check.RECORDED))
        self.assertEqual(check.problems([row(recorded, 'differ')]), [])
        self.assertTrue(check.problems([row(recorded, 'agree')]))

    def test_the_tolerances_tell_the_nominal_clocks_from_the_documented_ones(self):
        # the check tolerates 0.02 % on the frame: a CPU taken as 8.000 MHz instead of 8.021247 would be 0.26 % away
        self.assertTrue(check.close(160256.0, 160256, 160256 * 0.0002))
        self.assertFalse(check.close(160256 * 8_000_000 / check.CPU_HZ, 160256, 160256 * 0.0002))
        # and the PSG: 2 MHz against crystal / 16
        self.assertFalse(check.close(2_000_000, check.PSG_HZ, check.PSG_HZ * 0.0002))


class TimerDDetectorProgramsTests(unittest.TestCase):
    """The authored programs of the timer D detector's check (mfp-timer-d-signs): they assemble, the code a RAM case copies fits the 64 bytes
    the program copies, and the cases cover each sign, the ROM, a masked interrupt and a game's own order."""
    def test_every_case_assembles_and_a_ram_stub_fits_its_copy(self):
        names = set()
        for name, where, code, expected in check.DETECTOR_CASES:
            with self.subTest(name):
                self.assertEqual(len(check.detector_program(where, code)), check.TOS_BYTES)
                self.assertEqual(len(expected), 4)
                if where == 'ram':
                    self.assertLessEqual(len(asm.Assembler(0x3000).assemble(chr(10).join(code) + chr(10) + 'rts')), 64)
            names.add(name)
        self.assertTrue({'rom', 'tddr-read', 'tcdcr-read', 'start-before-data', 'enable-only', 'enable-masked', 'own-setup'} <= names)
        for letter in range(4):          # each sign is expected at least once, and each case that expects one expects only it
            self.assertTrue(any(expected[letter] for _, _, _, expected in check.DETECTOR_CASES))
        self.assertEqual(check.DETECTOR_CASES[0][3], (0, 0, 0, 0))
        self.assertTrue(set(check.DETECTOR_EXACT) <= names)
        self.assertIn('mfp-timer-d-signs', check.CHECKS)


class FilesTests(unittest.TestCase):
    def test_the_files_are_lf_and_carry_no_firmware_or_game_bytes(self):
        for name in ('tools/atarist_hardware_asm.py', 'tools/atarist_hardware_check.py', 'native/atarist_machine/atarist_hardware_checks.c',
                     'tests/test_atarist_hardware.py'):
            data = (ROOT / name).read_bytes()
            with self.subTest(name):
                self.assertNotIn(b'\r', data)
                self.assertLess(len(data), 120_000)


def _core_is_current():
    """True when the workspace already holds a build of the core for the current adaptation (this test never builds Hatari)."""
    try:
        from retrorecomp import atarist_hatari
        ready = json.loads((check.HATARI / 'ready.json').read_text(encoding='utf-8'))
        return (ready.get('adaptation') == atarist_hatari.adaptation_digest() and (check.HATARI / 'build' / 'src' / 'libretro-hatari.a').exists()
                and (check.HATARI / 'build' / 'src' / 'cpu' / 'cputbl.h').exists())
    except Exception:
        return False


class MachineTests(unittest.TestCase):
    @unittest.skipUnless(_core_is_current(), 'no current build of the adapted Hatari core (python -B tools/atarist_hardware_check.py builds it)')
    def test_the_video_and_ikbd_behaviours_agree_with_the_documents(self):
        try:
            driver = check.build_driver()
        except Exception as error:      # no compiler: not a failure of the repository
            self.skipTest(f'the native driver cannot be built here: {error}')
        found = check.check_video(driver) + check.check_mfp_timer_b(driver)
        self.assertEqual(check.problems(found), [])
        self.assertTrue(any(entry['verdict'] == 'agree' for entry in found))
        self.assertNotIn('differ', {entry['verdict'] for entry in found})


if __name__ == '__main__':
    unittest.main()
