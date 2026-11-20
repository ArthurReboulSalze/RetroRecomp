"""The Internet room's key and typed code (retrorecomp/netplay/internet_key.py). Pure: no socket, no ROM."""
import random
import unittest

from retrorecomp.netplay import internet_key as key
from retrorecomp.netplay.invitation import DEFAULT_PORT, InvitationError

SECRET = bytes(range(16))


class KeyTests(unittest.TestCase):
    def test_round_trips_with_ipv4_ipv6_and_both(self):
        for v4, v6, length in (('82.65.10.20', None, 42), (None, '2a01:e0a:1:2::5', 61), ('82.65.10.20', '2a01:e0a:1:2::5', 68)):
            text = key.format_key(24611, SECRET, v4, v6)
            self.assertTrue(text.startswith('RR2-'))
            self.assertEqual(len(text.replace('-', '')) - 3, length)
            room = key.parse_key(text)
            self.assertEqual((room.port, room.secret, room.kind), (24611, SECRET, 'net'))
            self.assertEqual(room.addresses, tuple(a for a in (v4, v6) if a))
            self.assertEqual(key.parse_key('  ' + text.lower().replace('-', ' ') + '\n'), room)     # case, spaces, dashes
        self.assertNotIn('82.65', key.format_key(24611, SECRET, '82.65.10.20'))            # not readable at a glance

    def test_a_typing_error_is_caught_before_anything_connects(self):
        text = key.format_key(30000, SECRET, '82.65.10.20')
        rng = random.Random(4)
        caught = 0
        for _ in range(500):
            body = list(text)
            index = rng.choice([i for i, c in enumerate(body) if c not in '-' and i > 3])
            body[index] = rng.choice([c for c in key.ALPHABET if c != body[index]])
            with self.assertRaises(InvitationError) as raised:
                key.parse_key(''.join(body))
            caught += raised.exception.code == 'typo'
        self.assertEqual(caught, 500)
        for bad in (text[:-1], text + 'A', text.replace('-', '')[:-4]):
            with self.assertRaises(InvitationError) as raised:
                key.parse_key(bad)
            self.assertEqual(raised.exception.code, 'typo')

    def test_another_version_and_texts_that_are_no_key(self):
        with self.assertRaises(InvitationError) as raised:
            key.parse_key('RR3-' + key.format_key(30000, SECRET, '82.65.10.20')[4:])
        self.assertEqual(raised.exception.code, 'other_version')
        for bad in ('', 'hello', 'rr1:lan:192.168.1.20:24611:AAAQEAYEAUDAOCAJBIFQYDIOB4', None, 5, b'RR2-AAAAA', 'RR2-' + 'é' * 40,
                    'RR2-' + 'A' * 200):
            with self.assertRaises(InvitationError) as raised:
                key.parse_key(bad)
            self.assertIn(raised.exception.code, ('bad', 'typo', 'other_version'))
            if isinstance(bad, str) and len(bad) > 24:
                self.assertNotIn(bad[4:20] or 'zzz', raised.exception.reason)
        for v4 in ('127.0.0.1', '0.0.0.0', '224.0.0.1', '255.255.255.255', 'example.com'):
            with self.assertRaises(ValueError):
                key.format_key(30000, SECRET, v4)
        with self.assertRaises(ValueError):
            key.format_key(80, SECRET, '82.65.10.20')
        with self.assertRaises(ValueError):
            key.format_key(30000, SECRET)

    def test_the_code_and_the_typed_form(self):
        code = key.format_code(SECRET)
        self.assertEqual([len(group) for group in code.split('-')], [5, 5, 5, 5, 7])
        self.assertEqual(key.parse_code(code), SECRET)
        self.assertEqual(key.parse_code(code.lower().replace('-', '')), SECRET)
        swapped = code.replace('0', 'O').replace('1', 'L')
        self.assertEqual(key.parse_code(swapped), SECRET)                      # Crockford reads O as 0 and I, L as 1
        for index in (0, 7, 13, 25):
            flat = list(code.replace('-', ''))
            flat[index] = '7' if flat[index] != '7' else '8'
            with self.assertRaises(InvitationError) as raised:
                key.parse_code(''.join(flat))
            self.assertEqual(raised.exception.code, 'typo')
        room = key.parse_manual('82.65.10.20', '', code)
        self.assertEqual((room.addresses, room.port, room.secret), (('82.65.10.20',), DEFAULT_PORT, SECRET))
        self.assertEqual(key.parse_manual(' 2a01:e0a::5 ', 30000, code).address, '2a01:e0a::5')
        for address, port in (('example.com', ''), ('127.0.0.1', ''), ('82.65.10.20', '80'), ('82.65.10.20', 'x'), (None, '')):
            with self.assertRaises(InvitationError):
                key.parse_manual(address, port, code)

    def test_the_same_secret_in_both_presentations(self):
        for seed in range(50):
            secret = random.Random(seed).randbytes(16)
            self.assertEqual(key.parse_key(key.format_key(24611, secret, '82.65.10.20')).secret,
                             key.parse_code(key.format_code(secret)))


if __name__ == '__main__':
    unittest.main()
