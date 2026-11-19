"""retrorecomp/netplay/firewall_check.py: the verdict on a record of Windows' firewall (no PowerShell here), and the host's
controller saying a blocked room once (a stand-in check, no worker)."""
import unittest

from retrorecomp.netplay import firewall_check as fw
from retrorecomp.netplay.lobby_client import LobbyController, LobbyModel

PROGRAM = r'C:\RetroRecompTest\Python314\python.exe'


def record(rules=(), category=1, enabled=True, blockall=False, inbound=0):
    return {'current': 2, 'category': category,
            'profiles': [{'bit': bit, 'enabled': enabled, 'blockall': blockall, 'inbound': inbound} for bit in (1, 2, 4)],
            'rules': list(rules)}


def rule(protocol, app=PROGRAM, ports='*', remote='*', profiles=2, action=1):
    return {'app': app, 'action': action, 'protocol': protocol, 'ports': ports, 'remote': remote, 'profiles': profiles}


class VerdictTests(unittest.TestCase):
    def test_no_rule_for_this_program_is_blocked_for_both_protocols(self):
        state, detail = fw.evaluate(record([rule(6, app=r'C:\Other\python.exe'), rule(256, app=None, ports=None)]),
                                    PROGRAM, 24611, False)
        self.assertEqual(state, fw.BLOCKED)
        self.assertIn('tcp', detail)
        self.assertIn('udp', detail)

    def test_windows_prompt_rules_open_the_room(self):
        # The rules Windows' own « allow access? » prompt makes: the program, any port, any remote, one per protocol.
        rules = [rule(6, app=PROGRAM.lower()), rule(17, app=PROGRAM.lower())]
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 24611, True), (fw.OPEN, ''))

    def test_port_rule_without_program_counts_and_ranges_are_read(self):
        rules = [rule(256, app=None, ports='24000-25000')]
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 24611, False), (fw.OPEN, ''))
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 30000, False)[0], fw.BLOCKED)

    def test_a_local_subnet_rule_lets_lan_guests_in_but_not_internet_ones(self):
        rules = [rule(6, ports='24611', remote='LocalSubnet'), rule(17, ports='24611', remote='LocalSubnet')]
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 24611, False), (fw.OPEN, ''))
        state, detail = fw.evaluate(record(rules), PROGRAM, 24611, True)
        self.assertEqual(state, fw.BLOCKED)
        self.assertIn('local network', detail)

    def test_a_rule_of_another_profile_does_not_count(self):
        rules = [rule(6, profiles=4), rule(17, profiles=4)]           # public only; the room's network is private
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 24611, False)[0], fw.BLOCKED)

    def test_firewall_off_or_allowing_by_default_is_open_block_all_is_blocked(self):
        self.assertEqual(fw.evaluate(record(enabled=False), PROGRAM, 24611, True), (fw.OPEN, ''))
        self.assertEqual(fw.evaluate(record(inbound=1), PROGRAM, 24611, True), (fw.OPEN, ''))
        rules = [rule(6), rule(17)]
        state, detail = fw.evaluate(record(rules, blockall=True), PROGRAM, 24611, False)
        self.assertEqual(state, fw.BLOCKED)
        self.assertIn('every incoming', detail)

    def test_a_block_rule_wins(self):
        rules = [rule(6), rule(17), rule(256, action=0)]
        self.assertEqual(fw.evaluate(record(rules), PROGRAM, 24611, False)[0], fw.BLOCKED)

    def test_one_rule_as_an_object_and_a_broken_record(self):
        one = record()
        one['rules'] = rule(256)                 # ConvertTo-Json writes a list of one as the object itself
        self.assertEqual(fw.evaluate(one, PROGRAM, 24611, False), (fw.OPEN, ''))
        self.assertEqual(fw.evaluate({'category': 1, 'profiles': 'x'}, PROGRAM, 24611, False)[0], fw.UNKNOWN)
        self.assertEqual(fw.check(PROGRAM, '192.168.1.20', 24611, False, reader=lambda address: None)[0], fw.UNKNOWN)

    def test_unknown_profile_needs_every_active_profile(self):
        rules = [rule(256, profiles=2)]
        data = record(rules, category=None)
        data['current'] = 6                      # private and public both active, the interface not found
        self.assertEqual(fw.evaluate(data, PROGRAM, 24611, False)[0], fw.BLOCKED)
        data['current'] = 2
        self.assertEqual(fw.evaluate(data, PROGRAM, 24611, False), (fw.OPEN, ''))


class ControllerTests(unittest.TestCase):
    def controller(self, verdict, tests=False):
        controller = LobbyController(library=None, model=LobbyModel())
        asked = []

        def check(program, address, port, internet):
            asked.append((program, address, port, internet))
            return verdict
        controller.firewall = check
        controller.model.secret = bytes(16)
        controller.model.tests = tests
        return controller, asked

    def test_a_blocked_host_room_says_it_once(self):
        controller, asked = self.controller((fw.BLOCKED, 'no rule lets this program receive tcp on port 24611'))
        controller._firewall('192.168.1.20', 24611)
        self.assertEqual(asked[0][1:], ('192.168.1.20', 24611, False))
        self.assertEqual(controller.model.firewall, fw.BLOCKED)
        self.assertEqual([notice['code'] for notice in controller.model.notices], ['firewall_blocked'])

    def test_an_open_room_says_nothing_and_a_failing_check_is_unknown(self):
        controller, _asked = self.controller((fw.OPEN, ''))
        controller._firewall('192.168.1.20', 24611)
        self.assertEqual((controller.model.firewall, list(controller.model.notices)), (fw.OPEN, []))

        def broken(*args):
            raise OSError('no powershell')
        controller.firewall = broken
        controller._firewall('192.168.1.20', 24611)
        self.assertEqual(controller.model.firewall, fw.UNKNOWN)

    def test_room_open_starts_the_check_for_a_host_only_outside_tests(self):
        controller, asked = self.controller((fw.OPEN, ''), tests=True)
        controller.on_event({'event': 'room_open', 'role': 'host', 'address': '127.0.0.1', 'port': 24611})
        self.assertEqual(asked, [])              # a test room never reads the firewall


if __name__ == '__main__':
    unittest.main()
