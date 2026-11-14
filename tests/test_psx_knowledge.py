"""PlayStation shared paths (retrorecomp/psx_knowledge.py): records, their rules, and the private filter on a small authored disc.
No player's disc: the disc is built by tests/test_psx_disc.py's helpers (an ISO 9660 volume with SYSTEM.CNF and a PS-X EXE)."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from retrorecomp import psx, psx_knowledge as k
from retrorecomp.psx_native import Observed
from tests.test_psx_disc import USER, user_sectors


def disc_file(folder: Path) -> Path:
    sectors, exe = user_sectors()
    path = folder / 'game.iso'
    path.write_bytes(b''.join(s.ljust(USER, b'\0') for s in sectors))
    return path


class PsxKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = disc_file(Path(self.folder.name))
        self.item = psx.read_input(self.path)
        self.exe = self.path.read_bytes()[21 * USER:21 * USER + 0x1000]     # the boot file is at sector 21 (SYSTEM.CNF at 20)
        self.bios = bytes(range(256)) * 2048                                   # 512 KiB, an authored stand-in
        data = k.DiscData(self.path, 0)
        self.size = data.size
        data.close()

    def tearDown(self):
        self.folder.cleanup()

    def observed(self):
        """Words the CPU ran: 64 from the executable's text (loaded at 0x10000), 8 the disc does not hold, 2 from the BIOS ROM."""
        pairs = {}
        for n in range(64):
            pairs[(0x10000 + 4 * n, int.from_bytes(self.exe[0x800 + 4 * n:0x804 + 4 * n], 'little'))] = Observed(3, n == 0)
        for n in range(8):
            pairs[(0x180000 + 4 * n, 0xDEAD0000 + n)] = Observed(1, n == 0)
        for n in range(2):
            pairs[(0x1FC00100 + 4 * n, int.from_bytes(self.bios[0x100 + 4 * n:0x104 + 4 * n], 'little'))] = Observed(1, n == 0)
        return pairs

    def test_observed_code_becomes_rows_of_the_disc_and_back(self):
        pairs = self.observed()
        spans, bios_rows, counts = k.translate(self.path, 1, self.bios, pairs)
        self.assertEqual(spans, [(0, 0x10000, 21 * USER + 0x800, 256)])
        self.assertEqual(bios_rows, [(0x1FC00100, 0x100, 4), (0x1FC00104, 0x104, 4)])
        self.assertEqual((counts['in_discs'], counts['in_bios'], counts['private']), (64, 2, 8))
        record = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], self.bios, spans, bios_rows)
        self.assertEqual(record['game'], 'psx:' + self.item.sha256)
        self.assertEqual(record['identity']['sources']['disc1'], {'bytes': self.size, 'sha256': self.item.disc_digests[0]})
        words, left = k.expanded_words(record, self.path, self.bios)
        self.assertEqual(set(words), {pair for pair in pairs if not 0x180000 <= pair[0] < 0x200000})
        self.assertEqual(left, {})
        # another BIOS: its rows are left out with their reason, the disc's are read
        words, left = k.expanded_words(record, self.path, bytes(len(self.bios)))
        self.assertEqual(len(words), 64)
        self.assertEqual(left['bios_rows']['rows'], 2)
        # no BIOS rows: no BIOS source
        plain = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], self.bios, spans, ())
        self.assertNotIn('bios', plain['identity']['sources'])

    def test_the_rules_refuse_what_is_not_a_playstation_record(self):
        spans = [(0, 0x10000, 21 * USER + 0x800, 256)]
        good = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], self.bios, spans, [(0x1FC00100, 0x100, 4)])
        k.validate_record(copy.deepcopy(good), self.item.sha256)

        def refused(change):
            record = copy.deepcopy(good)
            change(record)
            with self.assertRaises(ValueError):
                k.validate_record(record)
        refused(lambda r: r.update(game='psx:' + '0' * 64))                                   # not the key of its discs
        refused(lambda r: r['identity']['sources']['disc1'].pop('sha256'))
        refused(lambda r: r['identity']['sources'].update(disc2=r['identity']['sources'].pop('disc1')))
        refused(lambda r: r['identity']['sources']['bios'].update(bytes=0x40000))
        refused(lambda r: r['identity'].update(layout={'format': 1}))
        refused(lambda r: r['cpus']['r3000a']['paths']['spans'][0].update(src='bios'))
        with self.assertRaises(ValueError):                                                 # a span outside main RAM
            k.make_record(self.item.sha256, self.item.disc_digests, [self.size], None, [(0, 0x1FFFF0, 0, 32)])
        with self.assertRaises(ValueError):                                                 # a BIOS row of two instructions
            k.make_record(self.item.sha256, self.item.disc_digests, [self.size], self.bios, spans, [(0x1FC00100, 0x100, 8)])
        self.assertEqual(set(k.RECORD_RULES), {'layout', 'sources', 'paths', 'disc_set'})
        self.assertEqual(set(k.PATH_CAPS), {name for name, _ in k.entry_set(good)})

    def test_records_of_the_same_disc_unite_and_another_engine_is_kept_apart(self):
        one = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], None, [(0, 0x10000, 21 * USER + 0x800, 128)])
        two = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], None, [(0, 0x10080, 21 * USER + 0x880, 128)])
        both = k.merged(self.item.sha256, one, two)
        self.assertEqual(len(k.rows(both)[0]), 2)
        old = k.make_record(self.item.sha256, self.item.disc_digests, [self.size], None, [(0, 0x10080, 21 * USER + 0x880, 128)],
                            core='0' * 40)
        self.assertEqual(k.merged(self.item.sha256, old, one), one)
        self.assertEqual(k.record_digest(one), hashlib.sha256(
            __import__('json').dumps(one, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest())


if __name__ == '__main__':
    unittest.main()
