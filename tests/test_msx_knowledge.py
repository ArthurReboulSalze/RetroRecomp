"""The MSX and MSX2 paths of the shared base (retrorecomp/msx_knowledge.py, msx2_knowledge.py): numbers about the player's own cartridge, never
its bytes; a record of another cartridge, machine or size is refused; received windows are used but shared again only once learned. No ROM."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import knowledge, msx2_knowledge, msx_knowledge as k, path_profiles as pp


def cartridge(seed: int = 1, size: int = 0x8000) -> bytes:
    out = bytearray(size)
    value = seed
    for n in range(size):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        out[n] = value >> 16 & 0xFF
    return bytes(out)


BIOS = bytes(0x8000)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.cart = cartridge()
        self.sha = hashlib.sha256(self.cart).hexdigest()
        self.inside = {self.cart[0x100:0x104], self.cart[0x2345:0x2349]}
        self.outside = {b'\xDE\xAD\xBE\xEF'} if b'\xDE\xAD\xBE\xEF' not in self.cart else set()

    def test_a_record_holds_offsets_into_the_cartridge_and_counts_the_rest(self):
        record, counts = k.promote(self.sha, self.cart, BIOS, self.inside | self.outside)
        self.assertEqual(sorted(k.rows(record)), sorted(self.cart.find(word) for word in self.inside))
        self.assertEqual(counts['private_not_in_cartridge'], len(self.outside))
        self.assertEqual(record['game'], f'msx:{self.sha}')
        self.assertEqual(set(record['identity']['sources']), {'rom', 'bios'})
        text = repr(record)
        for word in self.inside:                      # numbers, never the bytes
            self.assertNotIn(word.hex(), text)
        self.assertEqual(k.validate_record(record, self.sha), record)

    def test_received_windows_are_read_from_the_players_own_cartridge(self):
        record, _ = k.promote(self.sha, self.cart, BIOS, self.inside)
        found, info = k.shared_rows(self.sha, self.cart, imported=record)
        self.assertEqual(found, self.inside)
        self.assertEqual(info['imported'], 2)

    def test_what_is_refused(self):
        record, _ = k.promote(self.sha, self.cart, BIOS, self.inside)
        other = hashlib.sha256(b'other').hexdigest()
        with self.assertRaises(ValueError):
            k.validate_record(record, other)                      # another cartridge
        with self.assertRaises(ValueError):
            msx2_knowledge.validate_record(record, self.sha)      # another machine
        found, info = k.shared_rows(self.sha, self.cart[:0x4000], imported=record)
        self.assertEqual(found, set())                            # a cartridge of another size
        self.assertIn('imported', info['ignored'])
        with self.assertRaises(ValueError):                       # past the end of the cartridge it names
            k.make_record(self.sha, self.cart, BIOS, [len(self.cart) - 2])
        stale = dict(record, cpus={'z80': dict(record['cpus']['z80'], core='0' * 40)})
        found, info = k.shared_rows(self.sha, self.cart, qualified=stale)
        self.assertEqual((found, info['ignored'].get('qualified')), (set(), 'another engine revision'))

    def test_record_rules_state_what_validate_record_enforces(self):
        """RECORD_RULES is what the site's builder reads: an interpreter of the rules and `validate_record` accept and refuse the same records."""
        rules = k.RECORD_RULES

        def accepted_by_rules(value) -> bool:
            identity = value['identity']
            sources = identity['sources']
            if list(identity['layout']) != rules['layout'] or set(sources) - set(rules['sources']['only']) \
                    or set(rules['sources']['required']) - set(sources):
                return False
            if rules['sources']['hashed'] and not all('sha256' in source for source in sources.values()):
                return False
            if value['game'] != 'msx:' + sources[rules['sources']['game']]['sha256']:
                return False
            for cpu, section in value['cpus'].items():
                for kind, blocks in section['paths'].items():
                    if kind not in rules['paths'].get(cpu, {}):
                        return False
                    if any(block.get('src') != rules['paths'][cpu][kind]['src'] for block in blocks):
                        return False
            return True

        good, _ = k.promote(self.sha, self.cart, BIOS, self.inside)
        no_bios = dict(good, identity=dict(good['identity'], sources={'rom': good['identity']['sources']['rom']}))
        unhashed = dict(good, identity=dict(good['identity'], sources={**good['identity']['sources'],
                                                                         'bios': {'bytes': len(BIOS)}}))
        other_game = dict(good, game='msx:' + hashlib.sha256(b'x').hexdigest())
        into_bios = dict(good, cpus={'z80': dict(good['cpus']['z80'], paths={'windows': [dict(good['cpus']['z80']['paths']['windows'][0],
                                                                                                 src='bios')]})})
        for number, (value, expected) in enumerate([(good, True), (no_bios, False), (unhashed, False), (other_game, False),
                                                    (into_bios, False)]):
            with self.subTest(case=number):
                try:
                    k.validate_record(value)
                    enforced = True
                except ValueError:
                    enforced = False
                self.assertEqual(enforced, expected)
                self.assertEqual(accepted_by_rules(value), expected)

    def test_union_and_engines(self):
        first, _ = k.promote(self.sha, self.cart, BIOS, {self.cart[0x10:0x14]})
        second, _ = k.promote(self.sha, self.cart, BIOS, {self.cart[0x20:0x24]})
        self.assertEqual(sorted(k.rows(k.merged(self.sha, first, second))), [0x10, 0x20])
        self.assertNotEqual(k.engine('msx'), k.engine('msx2'))
        self.assertEqual(msx2_knowledge.engine(), k.engine('msx2'))


class ConversionUseTests(unittest.TestCase):
    """receive (before learning) and conclude (after every check) on a work folder, with the banks and the library in a temporary folder."""

    def test_received_windows_are_translated_but_shared_only_once_learned(self):
        cart = cartridge(7)
        sha = hashlib.sha256(cart).hexdigest()
        theirs, mine = cart[0x40:0x44], cart[0x80:0x84]
        offered, _ = k.promote(sha, cart, BIOS, {theirs})
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            work, library = root / 'work', root / 'library'
            work.mkdir()
            with mock.patch('retrorecomp.library.library_root', lambda system: library / system), \
                    mock.patch.object(knowledge, 'qualified_game', lambda system, identity: {}), \
                    mock.patch.object(knowledge, 'imported_game', lambda system, identity: offered):
                use = k.receive('msx', sha, cart, work)
                self.assertEqual((use['imported'], use['new_to_this_build']), (1, 1))
                self.assertIn(theirs, k.words((work / k.PATTERNS).read_text()))     # translated from the first pass
                # learning adds this player's own window, as msx_build.learn does
                (work / k.PATTERNS).write_text(k.text_of({theirs, mine}))
                block = k.conclude('msx', sha, cart, BIOS, work, use, 'Test')
                record = k.library_record(sha)
                self.assertEqual(k.rows(record), [0x80])                            # the received window is not shared again
                self.assertEqual(block['record_sha256'], k.record_digest(record))
                self.assertTrue(block['shared'])
                again = k.receive('msx', sha, cart, work)                           # nothing new the second time
                self.assertEqual(again['new_to_this_build'], 0)

    def test_the_switch_withdraws_the_msx(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s not in ('msx', 'msx2'))):
                self.assertEqual(k.receive('msx', '0' * 64, cartridge(), Path(root)), {'shared': False})
                self.assertIsNone(knowledge.schema3_module('msx'))
        self.assertIn('msx', pp.EXPERIMENTAL_SHARED)
        self.assertIn('msx2', pp.EXPERIMENTAL_SHARED)
        self.assertNotIn('msx2plus', pp.SHARED_SYSTEMS)                             # experimental, out of the sharing


if __name__ == '__main__':
    unittest.main()
