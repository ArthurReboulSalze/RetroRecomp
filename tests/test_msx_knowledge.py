"""The MSX2+ paths of the shared base (retrorecomp/msx_knowledge.py, msx2plus_knowledge.py): numbers about the player's own cartridge or disks,
never their bytes; a record of other images, another machine or another size is refused; received windows are used but shared again only once
learned. The MSX and the MSX2 decline the sharing. No ROM, no disk image."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import knowledge, msx2plus_knowledge as m, msx_knowledge as k, path_profiles as pp
from retrorecomp.msx_disk import disk_set


def cartridge(seed: int = 1, size: int = 0x8000) -> bytes:
    out = bytearray(size)
    value = seed
    for n in range(size):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        out[n] = value >> 16 & 0xFF
    return bytes(out)


def disks(count: int, seed: int = 11) -> tuple:
    return tuple(cartridge(seed + n, 368640) for n in range(count))


BIOS = bytes(0x18000)


class CartridgeRecordTests(unittest.TestCase):
    def setUp(self):
        self.cart = cartridge()
        self.sha = hashlib.sha256(self.cart).hexdigest()
        self.inside = {self.cart[0x100:0x104], self.cart[0x2345:0x2349]}
        self.outside = {b'\xDE\xAD\xBE\xEF'} if b'\xDE\xAD\xBE\xEF' not in self.cart else set()

    def test_a_record_holds_offsets_into_the_cartridge_and_counts_the_rest(self):
        record, counts = m.promote(self.sha, self.cart, BIOS, self.inside | self.outside)
        self.assertEqual(sorted(k.rows(record)), sorted((self.cart.find(word),) for word in self.inside))
        self.assertEqual(counts['private_not_in_images'], len(self.outside))
        self.assertEqual(record['game'], f'msx2plus:{self.sha}')
        self.assertEqual(set(record['identity']['sources']), {'rom', 'bios'})
        text = repr(record)
        for word in self.inside:                      # numbers, never the bytes
            self.assertNotIn(word.hex(), text)
        self.assertEqual(m.validate_record(record, self.sha), record)

    def test_received_windows_are_read_from_the_players_own_cartridge(self):
        record, _ = m.promote(self.sha, self.cart, BIOS, self.inside)
        found, info = m.shared_rows(self.sha, self.cart, imported=record)
        self.assertEqual(found, self.inside)
        self.assertEqual(info['imported'], 2)

    def test_what_is_refused(self):
        record, _ = m.promote(self.sha, self.cart, BIOS, self.inside)
        with self.assertRaises(ValueError):
            m.validate_record(record, hashlib.sha256(b'other').hexdigest())      # another cartridge
        with self.assertRaises(ValueError):
            k.validate_record(record, self.sha, system='msx2')                     # a machine that declines the sharing
        found, info = m.shared_rows(self.sha, self.cart[:0x4000], imported=record)
        self.assertEqual(found, set())                                            # a cartridge of another size
        self.assertIn('imported', info['ignored'])
        with self.assertRaises(ValueError):                                       # past the end of the cartridge it names
            m.make_record(self.sha, self.cart, BIOS, [len(self.cart) - 2])
        stale = dict(record, cpus={'z80': dict(record['cpus']['z80'], core='0' * 40)})
        found, info = m.shared_rows(self.sha, self.cart, qualified=stale)
        self.assertEqual((found, info['ignored'].get('qualified')), (set(), 'another engine revision'))

    def test_union_and_engine(self):
        first, _ = m.promote(self.sha, self.cart, BIOS, {self.cart[0x10:0x14]})
        second, _ = m.promote(self.sha, self.cart, BIOS, {self.cart[0x20:0x24]})
        self.assertEqual(sorted(k.rows(m.merged(self.sha, first, second))), [(0x10,), (0x20,)])
        self.assertEqual(m.engine(), k.engine('msx2plus'))
        with self.assertRaises(ValueError):
            k.engine('msx2')


class DiskRecordTests(unittest.TestCase):
    def setUp(self):
        self.images = disks(3)
        self.key = disk_set(hashlib.sha256(image).hexdigest() for image in self.images)
        # Two windows in disk 1, one in disk 3, one built in RAM.
        self.inside = {self.images[0][0x200:0x204], self.images[0][0x5000:0x5004], self.images[2][0x1234:0x1238]}
        self.outside = {b'\xC3\x00\xC0\xC9'} if not any(b'\xC3\x00\xC0\xC9' in image for image in self.images) else set()

    def test_a_disk_record_holds_disk_and_offset_and_is_keyed_by_the_set(self):
        record, counts = m.promote(self.key, self.images, BIOS, self.inside | self.outside)
        self.assertEqual(record['game'], f'msx2plus:{self.key}')
        self.assertEqual(set(record['identity']['sources']), {'disk1', 'disk2', 'disk3', 'bios'})
        self.assertEqual(sorted(k.rows(record)), [(0, 0x200), (0, 0x5000), (2, 0x1234)])
        self.assertEqual(counts['private_not_in_images'], len(self.outside))
        block = record['cpus']['z80']['paths']['windows'][0]
        self.assertEqual(block['srcs'], ['disk1', 'disk2', 'disk3'])
        found, info = m.shared_rows(self.key, self.images, imported=record)
        self.assertEqual(found, self.inside)
        text = repr(record)
        for word in self.inside:
            self.assertNotIn(word.hex(), text)

    def test_one_disk_is_keyed_by_its_own_hash(self):
        image = self.images[0]
        key = hashlib.sha256(image).hexdigest()
        self.assertEqual(disk_set([key]), key)
        record, _ = m.promote(key, (image,), BIOS, {image[0x200:0x204]})
        self.assertEqual(record['cpus']['z80']['paths']['windows'][0]['src'], 'disk1')
        self.assertEqual(k.rows(record), [(0, 0x200)])
        self.assertEqual(m.shared_rows(key, (image,), library=record)[0], {image[0x200:0x204]})

    def test_what_is_refused_for_disks(self):
        record, _ = m.promote(self.key, self.images, BIOS, self.inside)
        sources = record['identity']['sources']
        swapped = dict(record, identity=dict(record['identity'], sources={**sources, 'disk1': sources['disk2'], 'disk2': sources['disk1']}))
        gap = dict(record, identity=dict(record['identity'], sources={n: v for n, v in sources.items() if n != 'disk2'}))
        with_rom = dict(record, identity=dict(record['identity'], sources={**sources, 'rom': {'bytes': 0x8000, 'sha256': '0' * 64}}))
        for bad in (swapped, gap, with_rom):
            with self.assertRaises(ValueError):
                m.validate_record(bad)
        found, info = m.shared_rows(self.key, self.images[:2], imported=record)    # another number of disks
        self.assertEqual(found, set())
        self.assertIn('imported', info['ignored'])
        with self.assertRaises(ValueError):                                         # past the end of the disk it names
            m.make_record(self.key, self.images, BIOS, [(1, 368640 - 2)])

    def test_record_rules_state_what_validate_record_enforces(self):
        """RECORD_RULES is what the site's builder reads: an interpreter of the rules and `validate_record` accept and refuse the same records."""
        rules = m.RECORD_RULES

        def key_of(sources, how):
            if how == 'disk_set':
                names = sorted((n for n in sources if n.startswith('disk')), key=lambda n: int(n[4:]))
                return disk_set(sources[n]['sha256'] for n in names)
            return sources[how]['sha256']

        def accepted_by_rules(value) -> bool:
            identity = value['identity']
            sources = identity['sources']
            if list(identity['layout']) != rules['layout']:
                return False
            for alternative in rules['alternatives']:
                rule = alternative['sources']
                numbered = rule.get('numbered', {})
                roles = {}
                ok = True
                for name in sources:
                    role = next((r for r in numbered if name.startswith(r) and name[len(r):].isdigit()), name)
                    if role in numbered:
                        low, high = numbered[role]
                        ok &= low <= int(name[len(role):]) <= high
                    roles.setdefault(role, []).append(name)
                for role, (low, high) in numbered.items():
                    got = sorted(int(n[len(role):]) for n in roles.get(role, []))
                    ok &= got == list(range(1, len(got) + 1))
                if not ok or set(roles) - set(rule['only']) or set(rule['required']) - set(roles):
                    continue
                if rule['hashed'] and not all('sha256' in source for source in sources.values()):
                    continue
                if value['game'] != 'msx2plus:' + key_of(sources, rule['game']):
                    continue
                allowed = alternative['paths']
                good = True
                for cpu, section in value['cpus'].items():
                    for kind, blocks in section['paths'].items():
                        if kind not in allowed.get(cpu, {}):
                            good = False
                            continue
                        for block in blocks:
                            names = block.get('srcs') or [block.get('src')]
                            good &= all(roles.get(allowed[cpu][kind]['src']) and name in roles[allowed[cpu][kind]['src']]
                                        for name in names)
                if good:
                    return True
            return False

        cart = cartridge()
        cart_key = hashlib.sha256(cart).hexdigest()
        cart_record, _ = m.promote(cart_key, cart, BIOS, {cart[0x100:0x104]})
        disk_record, _ = m.promote(self.key, self.images, BIOS, self.inside)
        sources = disk_record['identity']['sources']
        cases = [
            (cart_record, True), (disk_record, True),
            (dict(cart_record, identity=dict(cart_record['identity'], sources={'rom': cart_record['identity']['sources']['rom']})), False),
            (dict(disk_record, identity=dict(disk_record['identity'], sources={**sources, 'bios': {'bytes': len(BIOS)}})), False),
            (dict(disk_record, game='msx2plus:' + hashlib.sha256(b'x').hexdigest()), False),
            (dict(disk_record, identity=dict(disk_record['identity'], sources={**sources, 'disk1': sources['disk2'],
                                                                                'disk2': sources['disk1']})), False),
            (dict(cart_record, cpus={'z80': dict(cart_record['cpus']['z80'], paths={'windows': [
                dict(cart_record['cpus']['z80']['paths']['windows'][0], src='bios')]})}), False),
        ]
        for number, (value, expected) in enumerate(cases):
            with self.subTest(case=number):
                try:
                    m.validate_record(value)
                    enforced = True
                except ValueError:
                    enforced = False
                self.assertEqual(enforced, expected)
                self.assertEqual(accepted_by_rules(value), expected)


class CommonHandlingTests(unittest.TestCase):
    """path_records (the one copy of the schema 3 handling) and the window helpers of knowledge_build, which the Master System's records use
    too: the helpers give what the Master System's code computed inline before (14 November 2026)."""

    def test_the_window_helpers_give_the_master_systems_old_results(self):
        from retrorecomp.knowledge_build import window_offsets, window_words
        data = cartridge(3, 0x4000)
        windows = {data[n:n + 4] for n in (0, 7, 0x1234, 0x3FFC)} | {b'\x00\x01\x02\x03', b'\xFF\xFE\xFD\xFC'}
        old = [data.find(raw) for raw in windows]                                   # knowledge_build.build_record before
        offsets, missing = window_offsets(data, windows)
        self.assertEqual(offsets, [offset for offset in sorted(set(old)) if offset >= 0])
        self.assertEqual(missing, sum(offset < 0 for offset in old))
        refs = [[offset] for offset in offsets]
        self.assertEqual(window_words(data, (offset for (offset,) in refs)), {data[offset:offset + 4] for (offset,) in refs})

    def test_the_common_handling_names_no_machine(self):
        text = (Path(__file__).resolve().parents[1] / 'retrorecomp' / 'path_records.py').read_text(encoding='utf-8')
        for name in ('msx', 'MSX', 'sms', 'pce', 'x68', 'gba', 'cps'):
            self.assertNotIn(name, text)

    def test_merging_keeps_the_current_engine_and_shared_rows_counts_each_source(self):
        cart = cartridge(5)
        sha = hashlib.sha256(cart).hexdigest()
        records = m.records()
        one, _ = m.promote(sha, cart, BIOS, {cart[0x10:0x14]})
        old = m.make_record(sha, cart, BIOS, [0x20], core='1' * 40)
        self.assertEqual(records.merged(sha, old, one), one)                        # another engine: the current one is kept
        self.assertEqual(records.merged(sha, one, old), one)
        self.assertIsNone(records.salvaged_record(sha, dict(one, game='msx2plus:' + '0' * 64)))
        found, info = records.gathered_rows(sha, lambda record: ([('row', n) for n in k.rows(record)], {}), library=one, imported=one,
                                            qualified=old)
        self.assertEqual(found, [('row', (0x10,))])                                 # each row once
        self.assertEqual((info['library'], info['imported'], info['ignored'].get('qualified')), (1, 1, 'another engine revision'))

    def test_same_images_compares_the_images_not_the_bios(self):
        images = disks(2)
        key = disk_set(hashlib.sha256(image).hexdigest() for image in images)
        one, _ = m.promote(key, images, BIOS, {images[0][0x10:0x14]})
        other_bios, _ = m.promote(key, images, bytes(0x14000), {images[1][0x10:0x14]})
        self.assertTrue(m.same_images(one, other_bios))
        self.assertEqual(sorted(k.rows(m.merged(key, one, other_bios))), [(0, 0x10), (1, 0x10)])


class ConversionUseTests(unittest.TestCase):
    """receive (before learning) and conclude (after every check) on a work folder, with the banks and the library in a temporary folder."""

    def _round_trip(self, identity, media, theirs, mine):
        offered, _ = m.promote(identity, media, BIOS, {theirs})
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            work, library = root / 'work', root / 'library'
            work.mkdir()
            with mock.patch('retrorecomp.library.library_root', lambda system: library / system), \
                    mock.patch.object(knowledge, 'qualified_game', lambda system, identity: {}), \
                    mock.patch.object(knowledge, 'imported_game', lambda system, identity: offered):
                use = k.receive('msx2plus', identity, media, work)
                self.assertEqual((use['imported'], use['new_to_this_build']), (1, 1))
                self.assertIn(theirs, k.words((work / k.PATTERNS).read_text()))     # translated from the first pass
                (work / k.PATTERNS).write_text(k.text_of({theirs, mine}))          # learning adds this player's own window
                block = k.conclude('msx2plus', identity, media, BIOS, work, use, 'Test')
                record = m.library_record(identity)
                self.assertEqual(block['record_sha256'], k.record_digest(record))
                self.assertTrue(block['shared'])
                self.assertEqual(k.receive('msx2plus', identity, media, work)['new_to_this_build'], 0)
                return record

    def test_received_windows_are_translated_but_shared_only_once_learned(self):
        cart = cartridge(7)
        record = self._round_trip(hashlib.sha256(cart).hexdigest(), cart, cart[0x40:0x44], cart[0x80:0x84])
        self.assertEqual(k.rows(record), [(0x80,)])                                 # the received window is not shared again

    def test_a_disk_game_round_trip(self):
        images = disks(2, seed=21)
        key = disk_set(hashlib.sha256(image).hexdigest() for image in images)
        record = self._round_trip(key, images, images[0][0x40:0x44], images[1][0x80:0x84])
        self.assertEqual(k.rows(record), [(1, 0x80)])

    def test_the_switch_withdraws_the_msx2plus_and_the_msx_and_msx2_decline(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s != 'msx2plus')):
                self.assertEqual(k.receive('msx2plus', '0' * 64, cartridge(), Path(root)), {'shared': False})
                self.assertIsNone(knowledge.schema3_module('msx2plus'))
            self.assertEqual(k.receive('msx2', '0' * 64, cartridge(), Path(root)), {'shared': False})
        self.assertIn('msx2plus', pp.EXPERIMENTAL_SHARED)
        self.assertNotIn('msx', pp.SHARED_SYSTEMS)
        self.assertNotIn('msx2', pp.SHARED_SYSTEMS)
        self.assertIs(knowledge.schema3_module('msx2plus'), m)


if __name__ == '__main__':
    unittest.main()
