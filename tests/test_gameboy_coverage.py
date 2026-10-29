from pathlib import Path
from contextlib import ExitStack
import os
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.core import ConversionError
from retrorecomp.platforms import build_executable
from retrorecomp.gameboy import (GameBoyRom, _cpu_compare, _gb_parallelism, _probe, _remember_trace,
                              _verified_trace, convert_game_boy)
from retrorecomp.gameboy_coverage import (branch_entries, cpu_validation_scenarios,
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
        with patch('retrorecomp.gameboy.library_root', return_value=self.root / 'library'):
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
        with patch('retrorecomp.gameboy.run', return_value='[DIFF] Matched generated and interpreter execution for 1000000 steps / 29 frames'):
            with self.assertRaises(ConversionError):
                _cpu_compare(self.root / 'game.exe', self.root, 30)

    def test_probe_requires_completion_and_records_banked_fallback(self):
        log = ('[LIMIT] Reached frame limit 1200\n'
               '[RR-RAM] ram_stub_instructions=3 ram_stub_cycles=24 ram_single_step_instructions=5 ram_single_step_cycles=44 '
               'highmem_stub_instructions=2 highmem_stub_cycles=9\n'
               '[INTERP] Fallback inventory: sites=1 dropped=0 complete=yes\n'
               '[INTERP] Fallback site #1 00A:4567 reason=address_not_compiled entries=2 instructions=2 cycles=32\n'
               '[INTERP] Summary: fallbacks=2 interpreter_entries=2 interpreter_instructions=2 interpreter_cycles=32')
        with patch('retrorecomp.gameboy.run', return_value=log):
            result = _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')
        self.assertEqual(result['fallback_details'][0]['bank'], 10)
        self.assertEqual(result['interpreter_cycles'], 32)
        # WRAM/HRAM code run one instruction at a time is counted apart from the interpreter, and required.
        self.assertEqual((result['ram_stub_instructions'], result['ram_stub_cycles'],
                          result['ram_single_step_instructions'], result['ram_single_step_cycles'],
                          result['highmem_stub_instructions'], result['highmem_stub_cycles']), (3, 24, 5, 44, 2, 9))
        # A runtime line without the high-memory figures (an export of the same lot before it) is not accepted.
        with patch('retrorecomp.gameboy.run', return_value=log.replace(' highmem_stub_instructions=2 highmem_stub_cycles=9', '')):
            with self.assertRaises(ConversionError):
                _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')
        with patch('retrorecomp.gameboy.run', return_value=log.replace('[RR-RAM]', '[RR-OTHER]')):
            with self.assertRaises(ConversionError):
                _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')
        with patch('retrorecomp.gameboy.run', return_value=log.replace('[LIMIT] Reached frame limit 1200', '')):
            with self.assertRaises(ConversionError):
                _probe(self.root / 'game.exe', self.root, 1200, self.root / 'trace')

    def test_scripts_explore_beyond_start_without_system_actions(self):
        scenarios = probe_scenarios(3600)
        self.assertEqual(len(scenarios), 4)
        for scenario in scenarios[1:3]:
            entries = scenario.input_script.split(',')
            self.assertIn('60:S:2', entries)
            self.assertGreater(len(entries), 20)
        varied = scenarios[-1].input_script.split(',')
        self.assertIn('180:S:4', varied)
        self.assertIn('1000:D:20', varied)
        self.assertIn('2300:L:700', varied)
        for scenario in scenarios[1:]:
            entries = scenario.input_script.split(',')
            for entry in entries:
                frame, buttons, duration = entry.split(':')
                self.assertLess(int(frame), 3600)
                self.assertGreater(int(duration), 0)
                self.assertLessEqual(set(buttons), set('UDLRABS'))
                self.assertLessEqual(int(frame) + int(duration), 3600)
        self.assertEqual(len(probe_scenarios(30)), 1)

    def test_cpu_validation_budgets_leave_coverage_scenarios_unchanged(self):
        def budgets(frames, **options):
            return [(scenario.name, count) for scenario, count in cpu_validation_scenarios(frames, **options)]
        self.assertEqual(budgets(3600), [('boot', 30)])
        self.assertEqual(budgets(3600, deep=True), [('boot', 30), ('play_r', 240), ('play_l', 240), ('varied', 240)])
        self.assertEqual(budgets(75, deep=True), [('boot', 30), ('play_r', 75), ('play_l', 75)])
        self.assertEqual(budgets(10, deep=True), [('boot', 10)])

    def test_parallelism_respects_batch_cpu_share(self):
        from retrorecomp.platforms import build_jobs
        limit=int(build_jobs())
        with patch('retrorecomp.gameboy.available_cpus', return_value=24):
            self.assertEqual(_gb_parallelism(1), (min(24,limit), 3))
            self.assertEqual(_gb_parallelism(3), (min(8,limit), 3))
            self.assertEqual(_gb_parallelism(8), (min(3,limit), 1))
        with patch('retrorecomp.gameboy.available_cpus', return_value=4):
            self.assertEqual(_gb_parallelism(1), (min(4,limit), 2))
            self.assertEqual(_gb_parallelism(3), (1, 1))

    def test_parallelism_honors_explicit_limit_and_process_cpu_budget(self):
        from retrorecomp.platforms import compilation_budget
        with patch('retrorecomp.platforms.available_cpus',return_value=4), \
                patch('retrorecomp.gameboy.available_cpus',return_value=4), \
                patch.dict('os.environ',{'RETRO_RECOMP_BUILD_JOBS':'1'}):
            self.assertEqual(_gb_parallelism(1),(1,2))
            with compilation_budget(6):self.assertEqual(_gb_parallelism(6),(1,1))

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
                candidate=build_executable(project/'build','game')
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(b'MZ')
                (project / 'game_metadata.json').write_text('{"functions": []}')
            return ''

        def fake_probe(exe, build, frames, trace, scenario):
            probes.append((len(generations), scenario.name))
            discovered = {(2, 0x4567)} if scenario.name == 'play_r' else {(0, 0x150)}
            write_entries(trace, discovered)
            cycles = 8 if scenario.name == 'play_r' and len(generations) == 1 else 0
            return dict(scenario=scenario.name, interpreter_cycles=cycles, fallback_sites=int(cycles > 0),
                        ram_stub_instructions=0, ram_stub_cycles=0, ram_single_step_instructions=0,
                        ram_single_step_cycles=0, highmem_stub_instructions=0, highmem_stub_cycles=0)

        def fake_compare(exe, build, frames, scenario):
            comparisons.append((scenario.name, frames))
            return 'matched'

        with ExitStack() as stack:
            patches = {'ROOT': self.root,
                       '_dependencies': lambda emit: (self.root, self.root/'compiler', self.root, self.root/'cmake', 'generator'),
                       'write_game_metadata': lambda *a, **k: {}, 'adapt_generated_project': lambda *a: None,
                       '_verified_trace': lambda rom: prior, 'run': fake_command, '_probe': fake_probe,
                       '_cpu_compare': fake_compare, '_remember_trace': lambda *a: None}
            for name, value in patches.items():
                stack.enter_context(patch('retrorecomp.gameboy.' + name, value))
            # The icon preparation lives in the shared conversion helpers.
            stack.enter_context(patch('retrorecomp.conversion_common.prepare_icon', lambda *a, **k: {'embedded': False}))
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
                    # Written in schema 2 beside the old keys, with the time and target Game Boy lacked.
                    from retrorecomp.report_schema import read_report
                    document = read_report(report)
                    self.assertEqual(report['schema']['version'], 2)
                    self.assertIn('created_utc', report)
                    self.assertIn('target', report)
                    self.assertEqual(document['scan']['level'], report['scan_level'])
                    self.assertEqual(document['cpus'][0]['arch'], 'sm83')


class WritableCodeHookTests(unittest.TestCase):
    """The single-instruction executor of writable code (1.6.4) is wired once, in the right order."""

    def test_hook_and_executor_are_present_exactly_once(self):
        from retrorecomp import gameboy_runtime
        from retrorecomp.paths import ASSETS
        runtime = Path(gameboy_runtime.__file__).read_text(encoding='utf-8')
        header = (ASSETS / 'native/gb_ram_helpers.h').read_text(encoding='utf-8')
        # The counted dispatch entry (helpers, then the stub, then the single instruction) is the only hook.
        self.assertEqual(runtime.count('rr_gb_try_ram_dispatch(ctx, addr)'), 1)
        self.assertNotIn('rr_gb_try_ram_instruction(ctx, addr)', runtime)
        # The generated dispatch's call of the upstream 0xFF00-0xFF7F stub is replaced by the counted one, once;
        # the HRAM stub (signature-matched OAM-DMA wait routine) and the interpreter's own calls stay untouched.
        self.assertEqual(runtime.count("'if (rr_gb_try_highmem_dispatch(ctx, addr)) {'"), 1)
        self.assertEqual(runtime.count("'if (gbrt_try_execute_highmem_stub(ctx, addr)) {'"), 1)
        self.assertNotIn('gbrt_try_execute_hram_stub(', runtime)
        self.assertLess(header.index('rr_gb_try_store_helper(ctx, addr)) return 1;'),
                        header.index('gbrt_try_execute_ram_stub(ctx, addr)) {'))
        self.assertLess(header.index('gbrt_try_execute_ram_stub(ctx, addr)) {'),
                        header.index('rr_gb_try_ram_instruction(ctx, addr)) {'))
        for field in ('rr_ram_stub_instructions', 'rr_ram_stub_cycles', 'rr_ram_single_step_instructions',
                      'rr_ram_single_step_cycles', 'rr_highmem_stub_instructions', 'rr_highmem_stub_cycles'):
            self.assertEqual(runtime.count(f'uint64_t {field};'), 1, field)
            self.assertEqual(header.count(f'ctx->{field}'), 1, field)
        self.assertIn('[RR-RAM] ram_stub_instructions', runtime)
        self.assertIn('highmem_stub_instructions=%llu highmem_stub_cycles=%llu', runtime)
        self.assertEqual(header.count('static inline uint8_t rr_gb_try_highmem_dispatch('), 1)
        self.assertEqual(header.count('static inline uint8_t rr_gb_try_ram_instruction('), 1)
        self.assertEqual(header.count('static inline unsigned rr_gb_ram_length('), 1)
        # What the executor declines (prefix, HALT, STOP, RST, branches) stays with the reference.
        self.assertIn('HALT,\n * STOP, the CB prefix, RST and the illegal opcodes stay with the reference', header)


if __name__ == '__main__':
    unittest.main()
