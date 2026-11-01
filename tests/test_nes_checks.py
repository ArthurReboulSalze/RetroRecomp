"""NES liveness from the per-frame trace, the state schedule, and what the report says of saves (no ROM needed)."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import nes, nes_checks
from retrorecomp.core import ConversionError
from retrorecomp.delivery_evidence import frozen_route, require_moving_picture


def line(frame, picture, sound='0000000000000000', audible=0, memory='AAAA', pc='8000'):
    return (f'{frame} trace=0000000000000000 mem={memory} PC={pc} A=00 X=00 Y=00 S=FD P=24 int=00 cycles={frame * 29780} '
            f'hw=1111111111111111 pic={picture} snd={sound} aud={audible}')


class LivenessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def trace(self, *lines):
        path = self.folder / 'route.hash'
        path.write_text('\n'.join(lines) + '\n', encoding='ascii')
        return path

    def test_a_route_that_moves_and_sounds_is_counted(self):
        record = nes_checks.route_liveness(self.trace(
            line(0, 'A1'), line(1, 'A2', 'B1', 1, 'AB', '8010'), line(2, 'A2', 'B1', 1), line(3, 'A3', 'B2', 0, 'AC', '8010')))
        self.assertEqual(record, {'frames': 4, 'distinct_pictures': 3, 'picture_changes': 2, 'last_picture_change_frame': 3,
                                  'audible_frames': 2, 'last_audible_frame': 2, 'distinct_sound_blocks': 3,
                                  'distinct_ram_states': 3, 'distinct_program_counters': 2})

    def test_a_frozen_route_is_refused_and_a_moving_one_is_not(self):
        frozen = nes_checks.route_liveness(self.trace(*(line(frame, 'A1') for frame in range(30))))
        self.assertTrue(frozen_route(frozen))
        with self.assertRaises(ConversionError):
            require_moving_picture(frozen, lambda: ConversionError('stuck'))
        moving = nes_checks.route_liveness(self.trace(line(0, 'A1'), line(1, 'A2')))
        require_moving_picture(moving, lambda: ConversionError('stuck'))

    def test_a_silent_route_says_zero_audible_frames_and_a_trace_without_sound_says_none(self):
        silent = nes_checks.route_liveness(self.trace(line(0, 'A1'), line(1, 'A2')))
        self.assertEqual((silent['audible_frames'], silent['last_audible_frame']), (0, 0))
        old = self.trace('0 trace=0 mem=AAAA PC=8000 A=00 X=00 Y=00 S=FD P=24 int=00 cycles=1 hw=1111111111111111')
        record = nes_checks.route_liveness(old)
        self.assertEqual(record['frames'], 0)
        self.assertIsNone(record['audible_frames'])
        self.assertIsNone(record['distinct_sound_blocks'])

    def test_the_resume_schedule_keeps_the_keys_held_at_the_save_and_the_later_events(self):
        source = self.folder / 'in.input'
        source.write_text('# comment\n0 1:RIGHT\n10 1:RIGHT+A\n50 1:-\n60 2:LEFT\n', encoding='ascii')
        target = nes_checks.resume_input(source, 30, self.folder / 'out.input')
        self.assertEqual(target.read_text(encoding='ascii').splitlines(), ['0 1:RIGHT+A', '0 2:-', '20 1:-', '30 2:LEFT'])


class SavesTests(unittest.TestCase):
    def rom(self, flags6):
        header = bytes([0x4E, 0x45, 0x53, 0x1A, 2, 1, flags6, 0]) + bytes(8)
        return type('Rom', (), {'data': header + bytes(0x8000 + 0x2000), 'sha256': 'ab' * 32})()

    def test_a_battery_cartridge_names_its_save_file_and_says_where_it_is_checked(self):
        record = nes._ordinary_saves(self.rom(0x12), 'Some Game')
        self.assertTrue(record['supported'])
        self.assertEqual(record['path'], 'datas/games/Some_Game-abababababab.sav')
        self.assertIn('tools/nes_saves_check.py', record['validation']['method'])
        self.assertIn('not run during conversion', record['validation']['method'])

    def test_a_cartridge_without_a_battery_says_so(self):
        record = nes._ordinary_saves(self.rom(0x10), 'Some Game')
        self.assertFalse(record['supported'])
        self.assertNotIn('path', record)


class HostSourceTests(unittest.TestCase):
    def test_the_headless_trace_carries_the_picture_the_sound_and_the_audible_flag(self):
        from retrorecomp import nes_runtime
        from retrorecomp.paths import ROOT
        engine = ROOT / '.deps' / 'nesrecomp'
        if not (engine / 'runner/cyc/cyc_host.c').is_file():
            self.skipTest('the pinned NES engine is not checked out')
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'p'
            nes_runtime.prepare_host(project, engine, '0' * 64, 'T', mapper=0)
            host = (project / 'cyc_host.c').read_text(encoding='utf-8')
        self.assertIn('pic=%016llX snd=%016llX aud=%u', host)
        self.assertIn('if (wav_out || hash_out)', host)
        self.assertIn('if (hash_f || wav_f)', host)


if __name__ == '__main__':
    unittest.main()
