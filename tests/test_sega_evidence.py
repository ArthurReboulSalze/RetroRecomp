"""The Master System / Game Gear liveness (gate G8) and packed replay (gate G5) adapters: synthetic traces, no ROM, no process."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import core, sega_evidence
from retrorecomp.core import ConversionError
from retrorecomp.delivery_evidence import DeliveredFile

HEADER = 'frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h,psg_h,psg_nz'
OLD_HEADER = 'frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h'


def trace(directory: Path, name: str, frames, header=HEADER) -> Path:
    """`frames`: (picture, ram, sound hash, non-zero samples) per frame, written in the runner's format."""
    path = directory / name
    lines = [header]
    for number, (picture, ram, sound, nonzero) in enumerate(frames, 1):
        line = f'{number},v,c,r,{ram},00,00,00,00,C07F,{picture}'
        lines.append(line + (f',{sound},{nonzero}' if header == HEADER else ''))
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')
    return path


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_the_trace_gives_picture_sound_ram_and_no_program_counter(self):
        path = trace(self.directory, 'play.csv', [('a', '1', 's0', 0), ('b', '2', 's1', 12), ('b', '2', 's1', 3), ('c', '3', 's2', 0)])
        result = sega_evidence.route_liveness(path)
        self.assertEqual(result, {'frames': 4, 'distinct_pictures': 3, 'picture_changes': 2, 'last_picture_change_frame': 4,
                                  'audible_frames': 2, 'last_audible_frame': 3, 'distinct_sound_blocks': 3,
                                  'distinct_ram_states': 3})
        self.assertNotIn('distinct_program_counters', result)

    def test_a_trace_without_the_sound_columns_gives_none_not_zero(self):
        path = trace(self.directory, 'old.csv', [('a', '1', '', 0), ('b', '2', '', 0)], header=OLD_HEADER)
        result = sega_evidence.route_liveness(path)
        self.assertIsNone(result['audible_frames'])
        self.assertIsNone(result['last_audible_frame'])
        self.assertIsNone(result['distinct_sound_blocks'])
        self.assertEqual((result['frames'], result['distinct_pictures']), (2, 2))

    def test_a_silent_route_is_reported_with_zero_audible_frames(self):
        path = trace(self.directory, 'silent.csv', [('a', '1', 's', 0), ('b', '2', 's', 0)])
        result = sega_evidence.route_liveness(path)
        self.assertEqual((result['audible_frames'], result['last_audible_frame']), (0, 0))

    def test_a_trace_without_the_picture_column_is_refused(self):
        path = self.directory / 'bad.csv'
        path.write_text('frame,ram_h\n1,2\n', encoding='ascii')
        with self.assertRaises(ConversionError):
            sega_evidence.route_liveness(path)

    def test_only_the_play_route_must_show_a_moving_picture(self):
        frozen = sega_evidence.route_liveness(trace(self.directory, 'frozen.csv', [('a', '1', 's', 0)] * 5))
        moving = sega_evidence.route_liveness(trace(self.directory, 'moving.csv', [('a', '1', 's', 0), ('b', '1', 's', 0)]))
        sega_evidence.require_main_route_moving('demo', frozen, self.directory)       # a title waiting for a button is allowed
        sega_evidence.require_main_route_moving('play', moving, self.directory)
        with self.assertRaises(ConversionError) as raised:
            sega_evidence.require_main_route_moving('play', frozen, self.directory)
        self.assertIn('picture never changed', str(raised.exception))

    def test_a_silent_play_route_is_not_refused(self):
        silent = sega_evidence.route_liveness(trace(self.directory, 'silent.csv', [('a', '1', 's', 0), ('b', '1', 's', 0)]))
        sega_evidence.require_main_route_moving('play', silent, self.directory)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.executable = self.directory / 'game.exe'
        self.executable.write_bytes(b'built')
        self.checks = [{'scenario': 'demo', 'press': [], 'frames': 3}, {'scenario': 'play', 'press': ['60:S'], 'frames': 3}]
        self.references = {check['scenario']: {'scenario': check['scenario']} for check in self.checks}

    def delivered(self):
        copied = {}

        def fake_deliver(executable, packed, label, emit):
            packed.write_bytes(executable.read_bytes() + b'+packed')
            copied['label'] = label
            return DeliveredFile(packed, None, 'abc123')

        return fake_deliver, copied

    def replay(self, pictures):
        def replay(candidate, directory, check):
            directory.mkdir(parents=True, exist_ok=True)
            trace(directory, 'vdp.csv', pictures[check['scenario']])
            return {'scenario': check['scenario']}
        return replay

    def test_a_replayed_copy_that_matches_may_claim_it_and_carries_its_liveness(self):
        deliver, copied = self.delivered()
        moving = [('a', '1', 's0', 0), ('b', '2', 's1', 5)]
        with patch.object(sega_evidence, 'deliver_packed', deliver):
            delivered, results = sega_evidence.replay_delivered(
                self.executable, self.directory / 'packed-game.exe', self.directory / 'packed', self.checks, self.references,
                self.replay({'demo': moving, 'play': moving}), lambda result, reference: [], lambda text: None)
        self.assertEqual(copied['label'], 'Master System / Game Gear')
        self.assertEqual(delivered.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(delivered.report_fields(), {'packed_candidate_sha256': 'abc123'})
        self.assertEqual(results['play']['liveness']['audible_frames'], 1)
        self.assertEqual(sorted(results), ['demo', 'play'])

    def test_a_difference_from_the_reference_is_refused_and_nothing_is_claimed(self):
        deliver, _ = self.delivered()
        moving = [('a', '1', 's0', 0), ('b', '2', 's1', 5)]
        with patch.object(sega_evidence, 'deliver_packed', deliver):
            with self.assertRaises(ConversionError) as raised:
                sega_evidence.replay_delivered(
                    self.executable, self.directory / 'packed-game.exe', self.directory / 'packed', self.checks, self.references,
                    self.replay({'demo': moving, 'play': moving}),
                    lambda result, reference: ['ram'] if result['scenario'] == 'play' else [], lambda text: None)
        self.assertIn('play', str(raised.exception))
        self.assertIn('ram', str(raised.exception))

    def test_a_frozen_play_route_of_the_delivered_file_is_refused(self):
        deliver, _ = self.delivered()
        with patch.object(sega_evidence, 'deliver_packed', deliver):
            with self.assertRaises(ConversionError) as raised:
                sega_evidence.replay_delivered(
                    self.executable, self.directory / 'packed-game.exe', self.directory / 'packed', self.checks, self.references,
                    self.replay({'demo': [('a', '1', 's', 0)] * 3, 'play': [('a', '1', 's', 0)] * 3}),
                    lambda result, reference: [], lambda text: None)
        self.assertIn('picture never changed', str(raised.exception))


class ConvertWiringTests(unittest.TestCase):
    """The conversion reads the delivered-file evidence through the adapter; both engines replay the delivered copy."""

    def test_convert_uses_the_adapter_for_liveness_and_the_banked_replay(self):
        import inspect
        text = inspect.getsource(core.convert)
        self.assertIn('route_liveness(trace / "vdp.csv")', text)
        self.assertIn('require_main_route_moving(scenario, check["liveness"], trace)', text)
        self.assertIn('# The file the player receives is a compressed copy of this build: replay it on every route', text)
        self.assertIn('engine has no per-route reference, so the copy is compared with the final pass of this same build', text)
        self.assertIn("checks.pop('final_cpu')", text)
        self.assertIn('replay_delivered(executable, packed', text)
        self.assertIn('**(delivered.report_fields() if delivered else {})', text)

    def test_the_runner_trace_carries_the_sound_columns(self):
        from retrorecomp.core import prepare_runtime
        engine = core.ROOT / '.deps/smsggrecomp'
        if not (engine / 'runner/glue.c').is_file():
            self.skipTest('pinned smsggrecomp sources are not downloaded')
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            path = game / 'rom.sms'
            path.write_bytes(bytes(8192))
            prepare_runtime(game, core.read_rom(path), 'Fixture', engine)
            text = (game / 'runtime_glue.c').read_text(encoding='utf-8')
        self.assertIn('pixels_h,psg_h,psg_nz\\n', text)
        self.assertIn('(g_audio_sink || g_vdp_trace) && cyc > g_psg_cyc', text)
        self.assertIn('(g_audio_sink || g_vdp_trace) && smsrecomp_measured_guest_cycles > g_psg_cyc', text)
        self.assertIn('if (g_vdp_trace) for (size_t i = 0; i < n * 2; ++i){', text)


class ReportDeviceTests(unittest.TestCase):
    """Gate G2: the devices and the instruction counts the report gains (retrorecomp/sega_evidence.py)."""

    @staticmethod
    def codemasters_rom():
        rom = bytearray(0x40000)
        rom[0x7FE6:0x7FEA] = bytes([0xB4, 0xB5, 0x4C, 0x4A])
        return bytes(rom)

    def test_the_codemasters_header_is_the_checksum_pair_and_nothing_else(self):
        self.assertTrue(sega_evidence.codemasters_header(self.codemasters_rom()))
        self.assertFalse(sega_evidence.codemasters_header(bytes(0x40000)))                       # all zero: no header
        blank = bytearray([0xff]) * 0x8000
        self.assertFalse(sega_evidence.codemasters_header(bytes(blank)))                          # erased flash is not a header
        self.assertFalse(sega_evidence.codemasters_header(bytes(0x4000)))                         # too small to hold one

    def test_the_devices_run_no_program_and_claim_no_hardware_fidelity(self):
        devices = sega_evidence.hardware_devices('sms', bytes(0x20000))
        self.assertEqual([(d['id'], d['kind']) for d in devices],
                         [('sega', 'cartridge_mapper'), ('vdp_mode4', 'video_unit'), ('sn76489', 'audio_unit')])
        for device in devices:
            self.assertIs(device['details']['hardware_fidelity_validated'], False)
            self.assertIs(device['details']['translated_from_rom'], False)
        self.assertEqual(devices[0]['details']['rom_banks_16k'], 8)
        game_gear = sega_evidence.hardware_devices('gg', bytes(0x20000))
        self.assertEqual(game_gear[1]['details']['visible_pixels'], [160, 144])
        self.assertIs(game_gear[2]['details']['stereo_ports'], True)
        self.assertIs(devices[2]['details']['stereo_ports'], False)

    def test_a_codemasters_cartridge_is_reported_as_a_mapper_the_runtime_does_not_model(self):
        mapper = sega_evidence.hardware_devices('sms', self.codemasters_rom())[0]
        self.assertEqual((mapper['id'], mapper['mode']), ('codemasters', 'not_modelled'))
        self.assertIs(mapper['details']['codemasters_registers_modelled'], False)

    def test_step_counters_are_read_from_the_banked_log_and_never_invented(self):
        log = '[banked] native_steps=27098091 halt_steps=12 fallback_steps=3 banks_seen=1/1/1\n[banked-guards] native_steps=400\n'
        self.assertEqual(sega_evidence.step_counters(log),
                         {'native_instructions': 27098091, 'halted_steps': 12, 'guarded_native_instructions': 400})
        self.assertEqual(sega_evidence.step_counters('[exec] hybrid(interp): 0 calls'), {})
        self.assertEqual(sega_evidence.step_counters(''), {})

    def test_the_enriched_report_reads_back_with_devices_and_native_counts(self):
        import json
        from retrorecomp.report_schema import read_report
        from tests.test_report_schema import sms_report
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp) / 'build'
            report = sms_report()
            report['build_directory'] = str(build)
            for scenario in ('demo', 'play'):
                folder = build / 'checks' / f'pass1_{scenario}'
                folder.mkdir(parents=True)
                (folder / 'runtime.log').write_text('[banked] native_steps=1000 halt_steps=5 fallback_steps=0 banks_seen=1/1/1\n',
                                                    encoding='utf-8')
            report['history'] = report['final_checks']          # one pass: the final pass is pass 1
            path = Path(temp) / 'conversion-report.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            sega_evidence.enrich_report(path, 'sms', bytes(0x20000))
            read = read_report(json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual([d['id'] for d in read['devices']], ['sega', 'vdp_mode4', 'sn76489'])
        self.assertTrue(all(d['fallback_present'] is None for d in read['devices']))
        scenario = read['cpus'][0]['scenarios'][0]
        self.assertEqual((scenario['native'], scenario['interpreted'], scenario['halted_steps']), (1000, None, 5))


if __name__ == '__main__':
    unittest.main()
