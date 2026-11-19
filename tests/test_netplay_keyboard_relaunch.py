"""Session ABI 9 (Arthur, 19 Nov 2026): the host types on a computer (its keys travel in LOCAL, in its input records and in the RUN
of every seat; a guest's are never typed) and the host changes a run-changing option in a match (RELAUNCH: the match ends for
everyone and starts again with the new options). The pipe, the wire, the mapper and the driver, without a game."""
from pathlib import Path
import struct
import unittest

from retrorecomp.netplay import control, input_records as wire, lobby, seat_map, session_pipe as pipe

ROOT = Path(__file__).resolve().parents[1]
KEYS = bytes([0b00000001]) + bytes(pipe.KEY_BYTES - 1)          # the A key (scancode 4: bit 0)


class PipeTests(unittest.TestCase):
    def test_the_header_says_the_same(self):
        header = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
        self.assertIn(f'RRHK_SESSION_ABI {pipe.ABI}', header)
        self.assertEqual(pipe.ABI, 9)
        self.assertIn(f'#define RRHK_KEY_BYTES {pipe.KEY_BYTES}', header)
        hostkit = (ROOT / 'native/hostkit/hostkit.h').read_text(encoding='utf-8')
        self.assertIn(f'#define RRHK_SESSION_KEY_BYTES {pipe.KEY_BYTES}', hostkit)

    def test_a_local_carries_the_keys_after_the_sticks(self):
        self.assertEqual(pipe.parse_local(struct.pack('<IHH', 3, 1, pipe.SYS_KEYBOARD) + KEYS), (3, 1, pipe.SYS_KEYBOARD, None, KEYS))
        both = pipe.parse_local(struct.pack('<IHH4b', 3, 1, 0, 1, 2, 3, 4) + KEYS)
        self.assertEqual(both, (3, 1, 0, (1, 2, 3, 4), KEYS))
        for size in (9, 8 + pipe.KEY_BYTES - 1, 8 + pipe.AXES + pipe.KEY_BYTES + 1):
            with self.assertRaises(pipe.Broken):
                pipe.parse_local(bytes(size))

    def test_a_run_carries_the_hosts_keys_with_their_flag(self):
        payload = pipe.run(7, (1, 2), keys=KEYS)[4:]
        self.assertEqual(payload[4], pipe.RUN_KEYS)
        self.assertEqual(payload[-pipe.KEY_BYTES:], KEYS)
        both = pipe.run(7, (1, 2), axes=((0, 0, 0, 0), (1, 1, 1, 1)), keys=KEYS)[4:]
        self.assertEqual(both[4], pipe.RUN_AXES | pipe.RUN_KEYS)
        self.assertEqual(len(both), 6 + 2 * 2 + pipe.AXES * 2 + pipe.KEY_BYTES)
        with self.assertRaises(ValueError):
            pipe.run(7, (1,), keys=b'short')

    def test_a_relaunch_carries_plain_options_only(self):
        text = 'clock=enhanced\nsystem=aes'
        self.assertEqual(pipe.parse_relaunch(struct.pack('<H', len(text)) + text.encode('ascii')), text)
        for bad in (b'', struct.pack('<H', 3) + b'ab', struct.pack('<H', 2) + b'a\x01'):
            with self.assertRaises(pipe.Broken):
                pipe.parse_relaunch(bad)


class WireTests(unittest.TestCase):
    def test_records_with_keys_round_trip_and_fit(self):
        records = [(1, seat_map.SYS_KEYBOARD, None, KEYS), (2, 0, None, pipe.NO_KEYS)]
        packet = wire.decode(wire.encode_input(0, 9, [], [(0, 4, records)]), 2)
        self.assertEqual(packet.sections[0].records, tuple(records))
        self.assertLess(wire.records_that_fit(2, False, True), wire.records_that_fit(2, False))
        full = [(0, 0, None, KEYS)] * wire.records_that_fit(2, False, True)
        wire.encode_input(0, 0, [], [(0, 0, full), (1, 0, full)])          # stays within the packet's limit

    def test_every_full_input_packet_fits_a_sealed_datagram_and_carries_its_flags(self):
        # The first real 2-seat run found both: the datagram refused FLAG_KEYS, and a full packet of records with keys was larger
        # than a sealed datagram's body (every packet was then dropped as « bad_outgoing »).
        from retrorecomp.netplay import datagram
        for sections in (1, 2, 3, 4):
            for sticks in (False, True):
                for typed in (False, True):
                    record = (1, 0, (1, 1, 1, 1) if sticks else None, KEYS) if typed else \
                        ((1, 0, (1, 1, 1, 1)) if sticks else (1, 0))
                    count = wire.records_that_fit(sections, sticks, typed)
                    packet = wire.encode_input(0, 0, [], [(seat, 0, [record] * count) for seat in range(sections)])
                    self.assertLessEqual(len(packet) - 8, datagram.MAX_BODY, (sections, sticks, typed))
                    kind, body, flags = datagram.split_inner(packet, 0)
                    self.assertEqual(datagram.join_inner(kind, 0, body, flags), packet)

    def test_a_relaunch_bye_is_known_on_both_links(self):
        bye = wire.decode(wire.encode_bye(0, wire.BYE_RELAUNCH, 5), 2)
        self.assertEqual(bye.reason, wire.BYE_RELAUNCH)
        self.assertIn(wire.BYE_RELAUNCH, control.BYE_REASONS_WIRE)
        self.assertEqual(lobby.BACK_NAMES[12], 'relaunch')
        self.assertIn(12, control.BACK_REASONS)


class MapperTests(unittest.TestCase):
    def test_only_the_hosts_keys_are_typed_and_only_when_it_types(self):
        guest_typing = (0, seat_map.SYS_KEYBOARD, None, KEYS)
        self.assertIsNone(seat_map.keys([(0, 0, None, KEYS), guest_typing]))       # the host does not type
        self.assertEqual(seat_map.keys([(0, seat_map.SYS_KEYBOARD, None, KEYS), (0, 0, None, pipe.NO_KEYS)]), KEYS)
        self.assertIsNone(seat_map.keys([(0, 0), (0, 0)]))
        self.assertEqual(seat_map.SYS_KEYBOARD & (seat_map.SYS_GAME_MASK | seat_map.SYS_CONTROL_MASK | seat_map.SYS_RESTART |
                                                  seat_map.SYS_STATE_SAVE | seat_map.SYS_STATE_LOAD), 0)

    def test_a_guess_keeps_the_keys_held(self):
        from retrorecomp.netplay.rollback import predicted
        self.assertEqual(predicted([(5, seat_map.SYS_KEYBOARD | seat_map.SYS_RESTART, None, KEYS)]),
                         (5, seat_map.SYS_KEYBOARD, None, KEYS))



class GuestModelTests(unittest.TestCase):
    def test_a_guests_model_knows_the_seats_names_from_its_launch_request(self):
        from retrorecomp.netplay.lobby_client import LobbyModel
        model = LobbyModel()
        model.apply({'event': 'launch_request', 'match_id': 3, 'seats': 2, 'names': ['Arthur', 'Nadia'], 'tier': 'rollback',
                     'prediction': 5})
        self.assertEqual(model.last_launch['names'], ['Arthur', 'Nadia'])
        self.assertEqual(model.last_launch['match_id'], 3)

if __name__ == '__main__':
    unittest.main()
