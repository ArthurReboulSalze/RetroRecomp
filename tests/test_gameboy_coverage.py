from pathlib import Path
from contextlib import ExitStack
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from smsrecomp.core import ConversionError
from smsrecomp.gameboy import (GameBoyRom, _cpu_compare, _gb_parallelism, _probe, _remember_trace,
                              _verified_trace, convert_game_boy)
from smsrecomp.gameboy_coverage import (branch_entries, cpu_validation_scenarios,
                                      probe_scenarios, read_entries, write_entries)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_short_relays_in_any_bank_and_overlapping_entries(self):
        rom = bytearray([0xFF]) * 65536
        # An indirect caller can arrive at either adjacent one-opcode relay.
        rom[0xFFD0:0xFFD6] = bytes.fromhex('c3 00 60 c3 20 60')
        rom[0x8030:0x8032] = bytes.fromhex('18 fe')  # JR to itself in bank 2.
        rom[0x152:0x156] = bytes.fromhex('c3 c3 01 00')  # Both starts are valid.
        # Do not invent an immediate byte across separately mapped banks.
        rom[0x7FFE:0x8001] = bytes.fromhex('c3 00 40')
        rom[0x8050:0x8053] = bytes.fromhex('c3 00 c0')  # RAM target needs observation.
        original = bytes(rom)
        entries = branch_entries(rom)
        self.assertTrue({(3, 0x7FD0), (3, 0x7FD3), (2, 0x4030),
                         (0, 0x152), (0, 0x153)} <= entries)
        self.assertNotIn((1, 0x7FFE), entries)
        self.assertNotIn((2, 0x4050), entries)
        self.assertEqual(bytes(rom), original)

    def test_trace_merge_filters_ram_and_keeps_physical_bank_identity(self):
        path = self.root / 'observed.trace'
        path.write_text('3:7ff0\n3:7ff0\n0:c000\n3:ff80\n4:4567\n-1:1234\n0:-1\nbad\n2:0130\n0:4000\n')
        entries = read_entries(path, 65536)
        self.assertEqual(entries, {(3, 0x7FF0), (2, 0x130), (0, 0x4000)})
        write_entries(path, entries)
        self.assertEqual(read_entries(path, 65536), entries)
        self.assertEqual(len(path.read_text().splitlines()), 3)

    def test_game_memory_accumulates_and_rejects_tampered_previous_trace(self):
        data = bytes(65536)
        rom = GameBoyRom(self.root / 'authored.gb', data, 0, hashlib.sha256(data).hexdigest(), 'TEST', 0)
        trace = self.root / 'observed.trace'
        with patch('smsrecomp.gameboy.library_root', return_value=self.root / 'library'):
            write_entries(trace, {(1, 0x4000)})
            _remember_trace(rom, trace)
            write_entries(trace, {(3, 0x7000)})
            _remember_trace(rom, trace)
            stored = _verified_trace(rom)
            self.assertEqual(read_entries(stored, len(data)), {(1, 0x4000), (3, 0x7000)})
            stored.write_text('1:4567\n')
            self.assertIsNone(_verified_trace(rom))
            _remember_trace(rom, trace)
            self.assertEqual(read_entries(_verified_trace(rom), len(data)), {(3, 0x7000)})

    def test_cpu_check_requires_the_requested_frames_not_just_matched_steps(self):
        with patch('smsrecomp.gameboy.run', return_value='[DIFF] Matched generated and interpreter execution for 1000000 steps / 29 frames'):
            with self.assertRaises(ConversionError):
                _cpu_compare(self.root / 'game.exe', self.root, 30)

    def test_probe_requires_completion_and_records_banked_fallback(self):
        log = ('[LIMIT] Reached frame limit 1200\n'
               '[INTERP] Fallback inventory: sites=1 dropped=0 complete=yes\n'
               '[INTERP] Fallback site #1 00A:4567 reason=address_not_compiled entries=2 instructions=2 cycles=32\n'
               '[INTERP] Summary: fallbacks=2 interpreter_entries=2 interpreter_instructions=2 interpreter_cycles=32')
        with patch('smsrecomp.gameboy.run', return_value=log):
            result = _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')
        self.assertEqual(result['fallback_details'][0]['bank'], 10)
        self.assertEqual(result['interpreter_cycles'], 32)
        with patch('smsrecomp.gameboy.run', return_value=log.replace('[LIMIT] Reached frame limit 1200', '')):
            with self.assertRaises(ConversionError):
                _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')

    def test_scripts_explore_beyond_start_without_system_actions(self):
        scenarios = probe_scenarios(3600)
        self.assertEqual(len(scenarios), 3)
        for scenario in scenarios[1:]:
            entries = scenario.input_script.split(',')
            self.assertIn('60:S:2', entries)
            self.assertGreater(len(entries), 20)
            for entry in entries:
                frame, buttons, duration = entry.split(':')
                self.assertLess(int(frame), 3600)
                self.assertGreater(int(duration), 0)
                self.assertLessEqual(set(buttons), set('UDLRABS'))
        self.assertEqual(len(probe_scenarios(30)), 1)

    def test_cpu_validation_budgets_leave_coverage_scenarios_unchanged(self):
        def budgets(frames, **options):
            return [(scenario.name, count) for scenario, count in cpu_validation_scenarios(frames, **options)]
        self.assertEqual(budgets(3600), [('boot', 30)])
        self.assertEqual(budgets(3600, deep=True), [('boot', 30), ('play_r', 240), ('play_l', 240)])
        self.assertEqual(budgets(75, deep=True), [('boot', 30), ('play_r', 75), ('play_l', 75)])
        self.assertEqual(budgets(10, deep=True), [('boot', 10)])

    def test_parallelism_respects_batch_cpu_share(self):
        with patch('smsrecomp.gameboy.os.cpu_count', return_value=24):
            self.assertEqual(_gb_parallelism(1), (4, 3))
            self.assertEqual(_gb_parallelism(3), (4, 3))
            self.assertEqual(_gb_parallelism(8), (3, 1))
        with patch('smsrecomp.gameboy.os.cpu_count', return_value=4):
            self.assertEqual(_gb_parallelism(1), (4, 2))
            self.assertEqual(_gb_parallelism(3), (1, 1))

    def test_zero_boot_fallback_does_not_skip_learning_from_play(self):
        rom = bytearray(65536)
        path = self.root / 'fixture.gb'
        path.write_bytes(rom)
        (self.root / 'licenses').mkdir()
        for name in ('LICENSE', 'licenses/gb-recompiled.md', 'licenses/dear-imgui.md', 'licenses/SDL2.md'):
            (self.root / name).write_text('Synthetic license')
        generations = []
        probes = []
        comparisons = []
        prior = self.root / 'prior.trace'
        write_entries(prior, {(1, 0x4000)})

        def fake_command(args, **kwargs):
            if '-o' in args:
                project = args[args.index('-o') + 1]
                generations.append(read_entries(args[args.index('--use-trace') + 1], len(rom)))
                (project / 'build/Release').mkdir(parents=True, exist_ok=True)
                (project / 'build/Release/game.exe').write_bytes(b'MZ')
                (project / 'game_metadata.json').write_text('{"functions": []}')
            return ''

        def fake_probe(exe, build, frames, trace, scenario):
            probes.append((len(generations), scenario.name))
            discovered = {(2, 0x4567)} if scenario.name == 'play_r' else {(0, 0x150)}
            write_entries(trace, discovered)
            cycles = 8 if scenario.name == 'play_r' and len(generations) == 1 else 0
            return dict(scenario=scenario.name, interpreter_cycles=cycles, fallback_sites=int(cycles > 0))

        def fake_compare(exe, build, frames, scenario):
            comparisons.append((scenario.name, frames))
            return 'matched'

        with ExitStack() as stack:
            patches = {'ROOT': self.root, 'prepare_icon': lambda *a, **k: {'embedded': False},
                       '_dependencies': lambda emit: (self.root, self.root/'compiler', self.root, self.root/'cmake', 'generator'),
                       'write_game_metadata': lambda *a, **k: {}, 'adapt_generated_project': lambda *a: None,
                       '_verified_trace': lambda rom: prior, 'run': fake_command, '_probe': fake_probe,
                       '_cpu_compare': fake_compare, '_remember_trace': lambda *a: None}
            for name, value in patches.items():
                stack.enter_context(patch('smsrecomp.gameboy.' + name, value))
            for deep in (False, True):
                with self.subTest(deep=deep):
                    generations.clear()
                    probes.clear()
                    comparisons.clear()
                    messages = []
                    options = {} if deep else {'gb_deep_validation': False}  # Exercise the actual default.
                    convert_game_boy(path, output=self.root/'report', passes=3, frames=360,
                                     emit=messages.append, **options)
                    self.assertEqual(len(generations), 2)
                    self.assertIn((2, 0x4567), generations[1])
                    self.assertIn((1, 0x4000), generations[1])
                    self.assertEqual(probes, [(i, s) for i in (1, 2) for s in ('boot', 'play_r', 'play_l')])
                    self.assertCountEqual(comparisons, [('boot', 30)] + ([('play_r', 240), ('play_l', 240)] if deep else []))
                    self.assertEqual(any('add conversion time' in message for message in messages), deep)
                    report = json.loads((self.root/'report/conversion-report.json').read_text())
                    self.assertEqual(report['native_validation']['mode'], 'deep' if deep else 'standard')
                    self.assertEqual(len(report['final_checks']), 3)
                    self.assertTrue(all(check['interpreter_cycles'] == 0 for check in report['final_checks']))
                    self.assertTrue(all(value >= 0 for value in report['stage_seconds'].values()))


if __name__ == '__main__':
    unittest.main()
