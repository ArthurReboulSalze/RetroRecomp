"""The build, run and learn helpers every machine on the banked Z80 chain shares (retrorecomp/z80_chain_build.py): the CMake text of a machine's
project, one headless run and its report, the comparison of two reports, the rows of a route, and the learning loop. The machines' own builders
(msx_build, sg1000_build, the CPC's, the ZX's) call them; the generator, the bodies and the staging are tested in test_z80_chain_glue.py."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from retrorecomp import z80_chain_build as chain
from retrorecomp.z80_chain import Z80Costs, Z80Machine, Z80RegionMap


class ProjectCmakeTests(unittest.TestCase):
    MACHINE = ('sg1000_machine.c', 'tms9918.c', 'sn76489.c')

    def text(self, **options):
        return chain.chain_project_cmake('sg1000', 'RetroSg1000', reference_main='sg1000_reference_main.c', native_main='sg1000_native_main.c',
                                         machine_sources=self.MACHINE, **options)

    def test_the_reference_runner_is_always_there_and_the_bodies_and_the_check_come_with_bodies(self):
        text = self.text()
        self.assertIn('add_executable(sg1000_reference sg1000_reference_main.c sg1000_machine.c tms9918.c sn76489.c runtime_reference.c)', text)
        self.assertIn('add_library(sg1000_bodies OBJECT generated/game_banked_index.c ${bodies})', text)
        self.assertIn('add_executable(sg1000_check sg1000_native_main.c sg1000_machine.c tms9918.c sn76489.c runtime_reference.c '
                      '$<TARGET_OBJECTS:sg1000_bodies>)', text)
        self.assertIn('foreach(target sg1000_reference sg1000_check)', text)
        alone = self.text(bodies=False)
        self.assertIn('foreach(target sg1000_reference)', alone)
        self.assertNotIn('sg1000_bodies', alone)
        self.assertNotIn('sg1000_check', alone)

    def test_a_machines_own_switches_and_its_player_lines_are_added_and_nothing_else_changes(self):
        plain = self.text()
        extra = self.text(definitions=('RR_X=1', 'RR_Y=2'), game_lines=('add_executable(game player.c)',))
        self.assertIn('target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS RR_X=1 RR_Y=2)', extra)
        self.assertTrue(extra.endswith('add_executable(game player.c)\n'))
        self.assertEqual(extra.replace(' RR_X=1 RR_Y=2', '').replace('add_executable(game player.c)\n', ''), plain)

    def test_each_target_is_defined_once_and_the_text_ends_with_a_newline(self):
        text = self.text()
        for target in ('sg1000_reference', 'sg1000_check'):
            self.assertEqual(text.count(f'add_executable({target} '), 1)
        self.assertEqual(text.count('add_library(sg1000_bodies '), 1)
        self.assertTrue(text.endswith('\n') and '\r' not in text)


class RunAndCompareTests(unittest.TestCase):
    def test_one_run_gives_the_json_the_program_printed_and_a_failed_run_raises_the_builders_error(self):
        class Mine(RuntimeError):
            pass
        report = chain.run_program(Path(sys.executable), ['-c', 'print(\'{"frames": 3, "pc": 7}\')'], error=Mine)
        self.assertEqual(report, {'frames': 3, 'pc': 7})
        with self.assertRaises(Mine):
            chain.run_program(Path(sys.executable), ['-c', 'import sys; sys.exit(3)'], error=Mine)

    def test_the_cartridge_reaches_the_program_on_its_standard_input(self):
        code = 'import sys, json; print(json.dumps({"n": len(sys.stdin.buffer.read()), "cart": sys.argv[1:]}))'
        report = chain.run_program(Path(sys.executable), ['-c', code], image=b'\x01\x02\x03')
        self.assertEqual(report['n'], 3)
        self.assertEqual(report['cart'], ['--cart', '-'])

    def test_a_field_missing_on_either_side_differs(self):
        compared = ('frames', 'pc', 'ram_fnv')
        self.assertEqual(chain.differences({'frames': 1, 'pc': 2, 'ram_fnv': 3}, {'frames': 1, 'pc': 2, 'ram_fnv': 3}, compared), {})
        self.assertEqual(chain.differences({'frames': 1, 'pc': 2}, {'frames': 1, 'pc': 5, 'ram_fnv': 3}, compared),
                         {'pc': (2, 5), 'ram_fnv': (None, 3)})
        self.assertEqual(chain.differences({'frames': 1, 'pc': 2, 'extra': 9}, {'frames': 1, 'pc': 2, 'extra': 8}, ('frames', 'pc')), {})

    def test_the_rows_of_a_route_are_read_as_frame_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = Path(folder) / 'rows.csv'
            rows.write_text('frame,cpu,ram,picture,sound,samples,audible,pc\n1,aa,bb,cc,dd,735,1,0100\n2,aa,bb,ce,dd,735,0,0101\n', encoding='ascii')
            read = chain.frame_rows(rows)
        self.assertEqual([row.frame for row in read], [1, 2])
        self.assertEqual([row.picture for row in read], ['cc', 'ce'])
        self.assertEqual([row.audible for row in read], [True, False])


class LearnTests(unittest.TestCase):
    def run_learning(self, work, found, steps, *, passes=3):
        """`found[pass][route]`: what each route learns in each pass; `steps[pass][route]`: its fallback steps."""
        calls = {'generate': 0, 'build': 0, 'pass': -1}

        def generate():
            calls['generate'] += 1

        def build_check():
            calls['build'] += 1
            calls['pass'] += 1
            return Path('check.exe')

        def run_check(check, args, learned):
            route = int(args[0])
            patterns = found[calls['pass']][route] if calls['pass'] < len(found) else []
            if patterns:
                learned.write_text(''.join(f'{p}\n' for p in patterns), encoding='utf-8')
            return steps[calls['pass']][route] if calls['pass'] < len(steps) else 0
        check, counts = chain.learn_passes(work, [['0'], ['1']], generate=generate, build_check=build_check, run_check=run_check, passes=passes)
        return check, counts, calls

    def test_it_stops_when_nothing_fell_back(self):
        with tempfile.TemporaryDirectory() as folder:
            check, counts, calls = self.run_learning(Path(folder), found=[[[], []]], steps=[[0, 0]])
            self.assertEqual(counts, [0])
            self.assertEqual((calls['generate'], calls['build']), (1, 1))
            self.assertFalse((Path(folder) / 'native.patterns').exists())

    def test_what_the_routes_learn_is_united_and_the_next_pass_generates_again(self):
        with tempfile.TemporaryDirectory() as folder:
            check, counts, calls = self.run_learning(Path(folder), found=[[['0000AA01', '0000BB02'], ['0000BB02', '0000CC03']], [[], []]],
                                                     steps=[[5, 7], [0, 0]])
            self.assertEqual(counts, [12, 0])
            self.assertEqual((calls['generate'], calls['build']), (2, 2))
            self.assertEqual((Path(folder) / 'native.patterns').read_text(encoding='utf-8').split(), ['0000AA01', '0000BB02', '0000CC03'])

    def test_it_stops_when_a_pass_learns_nothing_new(self):
        with tempfile.TemporaryDirectory() as folder:
            same = [['0000AA01'], []]
            check, counts, calls = self.run_learning(Path(folder), found=[same, same, same], steps=[[3, 0], [3, 0], [3, 0]])
            self.assertEqual(counts, [3, 3])
            self.assertEqual(calls['build'], 2)

    def test_when_every_pass_still_learns_the_last_bodies_are_generated_once_more(self):
        with tempfile.TemporaryDirectory() as folder:
            found = [[[f'0000{n:04X}'], []] for n in range(3)]
            check, counts, calls = self.run_learning(Path(folder), found=found, steps=[[1, 0]] * 3, passes=3)
            self.assertEqual(counts, [1, 1, 1])
            self.assertEqual((calls['generate'], calls['build']), (4, 4))        # three passes, then the bodies with every pattern
            self.assertEqual(len((Path(folder) / 'native.patterns').read_text(encoding='utf-8').split()), 3)


class ReferenceCopyTests(unittest.TestCase):
    """The bodies' generation and the reference runner built alone prepare the reference interpreter's copy with the same arguments."""
    MACHINE = Z80Machine('refcopy', Z80RegionMap(region_bits=13, sources=('rom',), bank_values=256, scope='refcopy'), m1_wait=1,
                         irq_sample='instruction_end', nmi=True, port_bits=16,
                         costs=Z80Costs(base=(('', 0x00, 8),), irq=15, irq_im2=22, nmi=14))

    def calls(self):
        recorded = []
        engine = Path('engine')
        with tempfile.TemporaryDirectory() as folder,                 mock.patch('retrorecomp.cpu.prepare_reference', lambda *a, **k: recorded.append((a[2:], k))),                 mock.patch('retrorecomp.cpu.prepare_cpu_headers', lambda *a, **k: None),                 mock.patch.object(chain, 'generator', lambda machine, emit=print: (Path('tool'), engine)),                 mock.patch.object(chain, 'instrument_reference', lambda *a, **k: None),                 mock.patch.object(chain.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0)):
            work = Path(folder)
            chain.generate_bodies(work, self.MACHINE, bytes(8192), (), 'game', loop_name='loop.inc', accept='accept')
            chain.build_reference_runner(work / 'alone', self.MACHINE, accept='accept', stage=lambda w: None,
                                         build=lambda w, targets, emit: {targets[0]: Path('ref.exe')}, target='ref')
        return recorded

    def test_the_two_call_sites_pass_the_same_arguments_for_a_machine_with_costs_and_16_bit_ports(self):
        generated, alone = self.calls()
        self.assertEqual(generated, alone)
        self.assertEqual(generated[1], dict(m1_counter=True, nmi=True, costs=self.MACHINE.costs, port16=True))

    def test_the_arguments_come_from_one_function(self):
        recorded = []
        with mock.patch('retrorecomp.cpu.prepare_reference', lambda *a, **k: recorded.append((a, k))):
            chain.prepare_machine_reference(Path('w'), Path('e'), self.MACHINE)
        self.assertEqual(recorded, [((Path('w'), Path('e')), dict(m1_counter=True, nmi=True, costs=self.MACHINE.costs, port16=True))])


if __name__ == '__main__':
    unittest.main()
