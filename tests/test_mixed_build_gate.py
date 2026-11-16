"""The comparison and the input routes of tools/mixed_build_gate.py: no game, no dump, no executable."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mixed_build_gate as gate   # noqa: E402

from retrorecomp.random_routes import script_text, sega_press   # noqa: E402


def rows(count, **changes):
    """`count` frames with a state hash; `changes` maps a 0-based frame to the columns that differ there."""
    out = [{'frame': str(n + 1), 'state': f'{n:04x}', 'native': '10', 'interpreted': '0'} for n in range(count)]
    for index, values in changes.items():
        out[int(index)].update(values)
    return out


class Comparison(unittest.TestCase):
    def test_equal_runs(self):
        self.assertIsNone(gate.first_difference(rows(50), rows(50)))
        result = gate.check('whole', rows(50), rows(50))
        self.assertEqual((result['equal'], result['frames'], result['from_frame']), (True, 50, 1))

    def test_first_differing_frame_and_column(self):
        other = rows(50, **{'20': {'state': 'beef'}, '30': {'state': 'dead'}})
        difference = gate.first_difference(rows(50), other)
        self.assertEqual(difference['frame'], 21)
        self.assertEqual(difference['columns'], ['state'])
        self.assertEqual((difference['first'], difference['second']), ({'state': '0014'}, {'state': 'beef'}))

    def test_counters_are_not_state(self):
        # A build with more native code counts differently: that is the point of the gate, never a difference.
        other = rows(50, **{'5': {'native': '3', 'interpreted': '7'}})
        self.assertIsNone(gate.first_difference(rows(50), other, ignore=('native', 'interpreted')))
        self.assertEqual(gate.first_difference(rows(50), other)['columns'], ['native', 'interpreted'])

    def test_offset_names_the_frame_from_power_on(self):
        resumed = rows(10, **{'3': {'state': 'beef'}})
        self.assertEqual(gate.first_difference(rows(10), resumed, offset=1200)['frame'], 1204)

    def test_a_shorter_run_is_a_difference(self):
        difference = gate.first_difference(rows(50), rows(40))
        self.assertEqual((difference['frame'], difference['columns']), (41, ['length']))
        self.assertEqual(gate.first_difference(rows(5), [])['columns'], ['length'])
        self.assertIsNone(gate.first_difference([], []))

    def test_final_state(self):
        self.assertTrue(gate.final_check('end', {'ram': 'a', 'cpu': 'b'}, {'ram': 'a', 'cpu': 'b'})['equal'])
        result = gate.final_check('end', {'ram': 'a', 'cpu': 'b'}, {'ram': 'a', 'cpu': 'c', 'extra': 1})
        self.assertFalse(result['equal'])
        self.assertEqual(result['first_difference']['columns'], ['cpu', 'extra'])
        self.assertTrue(gate.final_check('end', {'ram': 'a', 'trace': '1'}, {'ram': 'a', 'trace': '2'},
                                         ignore=('trace',))['equal'])


class Verdict(unittest.TestCase):
    def test_all_equal_passes(self):
        self.assertEqual(gate.verdict([gate.check('a', rows(5), rows(5))]), 'passed')

    def test_one_difference_fails(self):
        checks = [gate.check('a', rows(5), rows(5)), gate.check('b', rows(5), rows(5, **{'2': {'state': 'x'}}))]
        self.assertEqual(gate.verdict(checks), 'failed')

    def test_a_refused_state_is_neither(self):
        refusal = gate.refused('state of A in B', 'exit 7')
        self.assertIsNone(refusal['equal'])
        self.assertEqual(gate.verdict([gate.check('a', rows(5), rows(5)), refusal]), 'passed')
        self.assertEqual(gate.verdict([refusal]), 'nothing compared')
        self.assertEqual(gate.verdict([]), 'nothing compared')

    def test_same_split_is_seen(self):
        self.assertFalse(gate.differing_split({'interpreted': 0}, {'interpreted': 0}))
        self.assertTrue(gate.differing_split({'interpreted': 12}, {'interpreted': 0}))


class Routes(unittest.TestCase):
    def test_route_is_reproducible_and_presses_both_pads(self):
        for console in ('nes', 'md', 'sms'):
            route = gate.gate_route(console, 6000)
            self.assertEqual(route, gate.gate_route(console, 6000))
            self.assertEqual(route.steps[0].frame, 0)
            frames = [step.frame for step in route.steps]
            self.assertEqual(frames, sorted(set(frames)))
            self.assertLess(frames[-1], 6000)
            pressed = [set().union(*(getattr(step, pad) for step in route.steps)) for pad in ('p1', 'p2')]
            for buttons in pressed:
                self.assertTrue(buttons & {'left', 'right', 'up', 'down'})
                self.assertTrue(buttons & {'a', 'b', 'c'})
            self.assertEqual(route.steps[-1].p1 | route.steps[-1].p2, frozenset())
        self.assertIn('start', set().union(*(step.p1 for step in gate.gate_route('nes', 6000).steps)))
        self.assertIn('start', set().union(*(step.p2 for step in gate.gate_route('md', 6000).steps)))

    def test_one_player_route_leaves_the_second_pad_alone(self):
        route = gate.gate_route('nes', 3000, players=1)
        self.assertEqual({step.p2 for step in route.steps}, {frozenset()})

    def test_press_limit_of_the_master_system_host(self):
        limit = gate.HOSTS['sms'].limit
        self.assertLessEqual(len(sega_press(gate.gate_route('sms', 6000, limit=limit))), limit)
        self.assertGreater(len(sega_press(gate.gate_route('sms', 6000))), limit)

    def test_too_short_a_route_is_refused(self):
        with self.assertRaises(ValueError):
            gate.gate_route('nes', 700)
        with self.assertRaises(ValueError):
            gate.gate_route('ng-unknown', 6000)

    def test_idle_and_long_routes(self):
        self.assertEqual(script_text(gate.named_route('idle', 'md', 3000)), '0 0 0\n')
        long = gate.named_route('long', 'nes', 3000)
        self.assertEqual(long, gate.named_route('long', 'nes', 3000))
        self.assertGreater(len(long.steps), 10)

    def test_nes_script_names_both_pads(self):
        text = script_text(gate.gate_route('nes', 3000))
        self.assertIn(' 2:', text)
        self.assertIn('START', text)


class NesTrace(unittest.TestCase):
    def test_hash_lines(self):
        text = ('0 trace=0A mem=0B PC=C003 A=00 X=00 Y=00 S=FD P=06 int=00 cycles=27395 hw=0C pic=0D snd=0E aud=1\n'
                '1 trace=1A mem=1B PC=C00B A=80 X=00 Y=00 S=FD P=84 int=00 cycles=57176 hw=1C pic=1D snd=1E aud=0\n')
        parsed = gate.parse_nes_hash(text)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1]['frame'], '1')
        self.assertEqual((parsed[1]['mem'], parsed[1]['cycles'], parsed[1]['snd']), ('1B', '57176', '1E'))
        self.assertEqual(gate.first_difference(parsed, parsed, ignore=gate.HOSTS['nes'].ignore), None)

    def test_resumed_run_ignores_the_cumulative_trace_only(self):
        host = gate.HOSTS['nes']
        self.assertEqual(set(host.resume_ignore) - set(host.ignore), {'trace'})


class Hosts(unittest.TestCase):
    def test_every_host_says_what_it_covers(self):
        for system, host in gate.HOSTS.items():
            self.assertTrue(host.covers, system)
            self.assertEqual(host.console, system)
        self.assertFalse(gate.HOSTS['sms'].states)
        self.assertTrue(gate.HOSTS['nes'].states and gate.HOSTS['md'].states)

    def test_the_tool_holds_no_game_and_is_published(self):
        source = (ROOT / 'tools' / 'mixed_build_gate.py').read_text(encoding='utf-8')
        self.assertNotIn('.zip', source)
        self.assertNotIn('192.168', source)
        publication = (ROOT / 'tools' / 'prepare_publication.py').read_text(encoding='utf-8')
        for name in ('tools/mixed_build_gate.py', 'tests/test_mixed_build_gate.py'):
            self.assertIn(name, publication)


if __name__ == '__main__':
    unittest.main()
