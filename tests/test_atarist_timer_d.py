"""Atari ST timer D, chosen per game (docs/ATARI_ST.md, known limits): the ROM-free parts. The rule that reads the detector's signs, the
report's fields, the run's check of the mode it ran, the payload constant, the option of the profile and the replacements that add the
detector to Hatari's MFP. The detector itself runs in the adapted Hatari: `python -B tools/atarist_hardware_check.py` measures it with
authored programs."""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from retrorecomp import atarist_conversion as conversion, atarist_hatari
from retrorecomp.core import ConversionError
from retrorecomp.systems import get_profile


def signs(**seen):
    """A run report's `timer_d_signs`: letter -> (count, frame, pc)."""
    return {letter: {'count': c, 'frame': f, 'pc': pc} for letter, (c, f, pc) in seen.items()}


class DecisionTests(unittest.TestCase):
    def test_the_choices_are_the_options(self):
        self.assertEqual(conversion.TIMER_D_CHOICES, ('auto', 'patched', 'exact'))
        option = next(key for key in get_profile('atarist').option_keys if key.name == 'atarist_timer_d')
        self.assertEqual((option.kind, option.choices, option.default, option.signature), ('choice', conversion.TIMER_D_CHOICES, 'auto', True))

    def test_a_report_without_signs_reads_as_zeros(self):
        table = conversion.timer_d_signs({'main': {}, 'explore': {'timer_d_signs': signs(A=(2, 778, 0x106f8))}})
        self.assertEqual(table['main']['A'], {'count': 0, 'frame': 0, 'pc': '0x000000'})
        self.assertEqual(table['explore']['A'], {'count': 2, 'frame': 778, 'pc': '0x0106f8'})
        self.assertEqual(set(table['main']), {'A', 'B', 'C', 'D'})

    def test_auto_keeps_the_patch_without_a_deciding_sign(self):
        for reports in ({'main': {}}, {'main': {'timer_d_signs': signs(D=(40, 100, 0x2000))}}):
            mode, reason = conversion.timer_d_decision('auto', conversion.timer_d_signs(reports))
            self.assertEqual(mode, 'patched')
            self.assertIn('not looked at', reason)

    def test_each_deciding_sign_drops_the_patch_and_the_earliest_is_named(self):
        for letter in conversion.TIMER_D_DECIDING_SIGNS:
            table = conversion.timer_d_signs({'main': {'timer_d_signs': signs(**{letter: (1, 500, 0x1234)})}})
            mode, reason = conversion.timer_d_decision('auto', table)
            self.assertEqual(mode, 'exact', letter)
            self.assertIn(f'sign {letter}', reason)
        table = conversion.timer_d_signs({'main': {'timer_d_signs': signs(A=(1, 778, 0x106f8))},
                                          'explore': {'timer_d_signs': signs(C=(3, 90, 0x4000), D=(9, 5, 0x10))}})
        mode, reason = conversion.timer_d_decision('auto', table)
        self.assertEqual(mode, 'exact')
        self.assertIn('sign C', reason)
        self.assertIn('frame 90', reason)
        self.assertIn('pc 0x004000', reason)
        self.assertIn('route explore', reason)

    def test_asked_modes_are_kept_whatever_the_signs(self):
        table = conversion.timer_d_signs({'main': {'timer_d_signs': signs(A=(1, 10, 0x100))}})
        self.assertEqual(conversion.timer_d_decision('patched', table)[0], 'patched')
        self.assertEqual(conversion.timer_d_decision('exact', {})[0], 'exact')
        self.assertEqual(conversion.timer_d_decision('exact', {})[1], 'chosen in Options')

    def test_the_report_names_the_mode_the_reason_and_the_signs(self):
        table = conversion.timer_d_signs({'main': {'timer_d_signs': signs(A=(1, 778, 0x106f8))}})
        mode, reason = conversion.timer_d_decision('auto', table)
        final = conversion.timer_d_signs({'main': {}})
        field = conversion.timer_d_report('auto', mode, reason, 'patched', table, final)
        self.assertEqual((field['mode'], field['patched'], field['choice'], field['hatari_option']), ('exact', False, 'auto', 'hatari_timerd'))
        self.assertEqual(field['signs']['measured_on'], 'patched')
        self.assertEqual(field['signs']['routes']['main']['A']['frame'], 778)
        self.assertIn('signs_on_final_machine', field)
        self.assertIn('not looked at', field['limit'])
        kept = conversion.timer_d_report('auto', 'patched', 'none', 'patched', table, None)
        self.assertTrue(kept['patched'])
        self.assertNotIn('signs_on_final_machine', kept)
        json.dumps(field)


class RunTests(unittest.TestCase):
    def run_replay(self, report, timer_d, tos=True):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        arguments = []

        def spawn(args, **options):
            arguments.extend(args)
            (folder / 'result.json').write_text(json.dumps({'frames': 5, 'stopped': False, **report}), encoding='utf-8')
            return mock.Mock(returncode=0)
        with mock.patch.object(conversion, 'spawn', spawn):
            result = conversion.replay(Path('player.exe'), folder, 5, folder / 'e.txt', tos=folder / 'tos.img' if tos else None, timer_d=timer_d)
        return result, arguments

    def test_the_reference_player_is_told_the_mode_and_its_report_must_say_it(self):
        _, arguments = self.run_replay({'timer_d_patch': False}, 'exact')
        self.assertEqual(arguments[arguments.index('--timer-d') + 1], 'exact')
        _, arguments = self.run_replay({'timer_d_patch': True}, 'patched')
        self.assertEqual(arguments[arguments.index('--timer-d') + 1], 'patched')
        for report, mode in (({'timer_d_patch': True}, 'exact'), ({'timer_d_patch': False}, 'patched'), ({}, 'patched')):
            with self.subTest(mode=mode, report=report), self.assertRaises(ConversionError):
                self.run_replay(report, mode)

    def test_a_game_binary_takes_no_mode_argument(self):
        result, arguments = self.run_replay({'timer_d_patch': False}, 'exact', tos=False)
        self.assertNotIn('--timer-d', arguments)
        self.assertEqual(result['frames'], 5)
        with self.assertRaises(ConversionError):
            self.run_replay({'timer_d_patch': True}, 'exact', tos=False)

    def test_the_payload_carries_the_mode(self):
        header = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(header, ignore_errors=True))
        source = mock.Mock(sha256='ab' * 32)
        disk = header / 'd.st'
        disk.write_bytes(b'\0' * 16)
        tos = header / 't.img'
        tos.write_bytes(b'\0' * 16)
        with mock.patch('retrorecomp.metadata.write_game_metadata', return_value={}), mock.patch('retrorecomp.resources.embed_resources'), \
                mock.patch.object(conversion.shutil, 'copy2'):
            for mode, value in (('exact', 1), ('patched', 0)):
                (header / 'game_resources.rc').write_text('', encoding='utf-8')
                conversion.payload(header, source, [disk], tos, 'T', False, timer_d=mode)
                text = (header / 'atarist_payload.h').read_text(encoding='utf-8')
                self.assertIn(f'#define RR_ST_TIMER_D_EXACT {value}', text, mode)


class DetectorTests(unittest.TestCase):
    """The replacements that add the detector to Hatari's MFP: each old text is found exactly once in a text that has them (the
    adaptation itself refuses anything else), and the new text calls the detector only from outside the TOS."""
    def test_every_hook_is_a_replacement_of_the_mfp(self):
        hooks = [new for rel, old, new in atarist_hatari.REPLACEMENTS if rel == 'src/mfp.c' and 'rr_timer_d_note' in new]
        self.assertEqual(len(hooks), 7)      # the detector's own block and six registers
        kinds = re.findall(r'rr_timer_d_note \( (RR_TD_\w+)', ''.join(hooks))
        self.assertEqual(sorted(kinds), sorted(['RR_TD_TDDR_READ', 'RR_TD_TCDCR_READ', 'RR_TD_TDDR_WRITE', 'RR_TD_TCDCR_WRITE',
                                                'RR_TD_ENABLE_WRITE', 'RR_TD_ENABLE_WRITE']))

    def test_the_detector_ignores_the_tos_and_the_second_mfp_and_changes_nothing(self):
        code = atarist_hatari.TIMER_D_DETECTOR
        self.assertIn('pc >= TosAddress && pc <= TosAddress + TosSize', code)
        self.assertIn('IoAccessCurrentAddress >= 0xfffa80', code)
        # observation only: it writes nothing of the machine (no register, no IoMem, no configuration)
        for name in ('IoMem[', 'ConfigureParams', 'pMFP_Main->IERB =', 'pMFP_Main->TDDR', 'M68000_WaitState'):
            self.assertNotIn(name, code)
        # sign D never chooses; A, B and C are the three counters the conversion reads
        self.assertEqual(conversion.TIMER_D_DECIDING_SIGNS, ('A', 'B', 'C'))


if __name__ == '__main__':
    unittest.main()
