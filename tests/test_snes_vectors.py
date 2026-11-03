"""The independent 65816 and SPC700 vector tools: the pins, the digest check on a synthetic archive, the case files."""
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools import fetch_snes_vectors as fetcher
from tools import snes_cpu_vector_selftest as selftest


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, content in files.items():
            raw = content if isinstance(content, bytes) else json.dumps(content).encode('ascii')
            member = tarfile.TarInfo('repo-rev/' + name)
            member.size = len(raw)
            tar.addfile(member, io.BytesIO(raw))
    stream.seek(0)
    return stream


class FetchTests(unittest.TestCase):
    def test_every_corpus_is_pinned_to_a_revision_and_a_digest(self):
        for cpu, corpus in fetcher.CORPORA.items():
            self.assertRegex(corpus['revision'], r'^[0-9a-f]{40}$', cpu)
            self.assertRegex(corpus['manifest_sha256'], r'^[0-9a-f]{64}$', cpu)
            self.assertTrue(corpus['repository'].startswith('SingleStepTests/'))
        self.assertEqual(fetcher.CORPORA['65816']['families'], 512)   # 256 opcodes, emulation and native mode
        self.assertEqual(fetcher.CORPORA['spc700']['families'], 256)

    def test_the_digest_does_not_depend_on_the_order_files_are_listed_in(self):
        self.assertEqual(fetcher.manifest_digest({'a.json': '1', 'b.json': '2'}), fetcher.manifest_digest({'b.json': '2', 'a.json': '1'}))
        self.assertNotEqual(fetcher.manifest_digest({'a.json': '1'}), fetcher.manifest_digest({'a.json': '2'}))

    def corpus(self, digest):
        return {'repository': 'x/y', 'revision': 'a' * 40, 'manifest_sha256': digest, 'families': 2}

    def test_a_sample_is_cached_only_when_the_corpus_matches_its_pinned_digest(self):
        cases = [{'name': f'00 {n}', 'initial': {}, 'final': {}, 'cycles': []} for n in range(10)]
        files = {'v1/00.json': cases, 'v1/01.json': cases[:4], 'LICENSE': b'MIT'}
        digest = fetcher.manifest_digest({name: __import__('hashlib').sha256(json.dumps(files[f'v1/{name}']).encode('ascii')).hexdigest()
                                          for name in ('00.json', '01.json')})
        with tempfile.TemporaryDirectory() as folder, patch.object(fetcher, 'CACHE', Path(folder)):
            with patch.dict(fetcher.CORPORA, {'spc700': self.corpus('0' * 64)}), \
                    patch('urllib.request.urlopen', return_value=archive(files)):
                with self.assertRaises(SystemExit):
                    fetcher.fetch('spc700', 3)
            self.assertEqual(list(Path(folder).iterdir()), [])   # nothing cached for a corpus that does not match
            with patch.dict(fetcher.CORPORA, {'spc700': self.corpus(digest)}), \
                    patch('urllib.request.urlopen', return_value=archive(files)):
                target = fetcher.fetch('spc700', 3)
            data = json.loads(target.read_text())
            self.assertEqual([family['selected'] for family in data['families']], [3, 3])   # min(3, available)
            self.assertEqual(sorted(case['family'] for case in data['cases']).count('00'), 3)
            self.assertEqual(data['manifest_sha256'], digest)
            self.assertTrue((Path(folder) / 'spc700-LICENSE').exists())


class CaseFileTests(unittest.TestCase):
    def test_a_65816_case_is_one_line_the_harness_can_read_back(self):
        case = {'name': 'a9 n 1', 'family': 'a9.n',
                'initial': {'pc': 100, 's': 500, 'p': 3, 'a': 4, 'x': 5, 'y': 6, 'dbr': 7, 'd': 8, 'pbr': 9, 'e': 0, 'ram': [[10, 11], [12, 13]]},
                'final': {'pc': 102, 's': 500, 'p': 3, 'a': 4, 'x': 5, 'y': 6, 'dbr': 7, 'd': 8, 'pbr': 9, 'e': 0, 'ram': [[10, 11]]},
                'cycles': [[10, 11, 'dp-r-mx-'], [12, None, '---r-mx-'], [14, 15, 'd--wemx-']]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cases.txt'
            selftest.write_65816([case], path)
            tokens = path.read_text().split()
        # index e pc s p a x y dbr d pbr nram (addr val)*, final fields, nfram (addr val)*, ncycles (addr val kind)*
        self.assertEqual(tokens[:12], ['0', '0', '100', '500', '3', '4', '5', '6', '7', '8', '9', '2'])
        self.assertEqual(tokens[12:16], ['10', '11', '12', '13'])
        self.assertEqual(tokens[16:27], ['0', '102', '500', '3', '4', '5', '6', '7', '8', '9', '1'])
        self.assertEqual(tokens[27:30], ['10', '11', '3'])
        self.assertEqual(tokens[29:], ['3', '10', '11', '0', '12', '-1', '2', '14', '15', '1'])   # read, internal (no value), write

    def test_a_spc700_case_marks_a_wait_and_a_dummy_read_without_a_value(self):
        case = {'name': '00 0000', 'family': '00',
                'initial': {'pc': 1, 'a': 2, 'x': 3, 'y': 4, 'sp': 5, 'psw': 6, 'ram': [[1, 0]]},
                'final': {'pc': 2, 'a': 2, 'x': 3, 'y': 4, 'sp': 5, 'psw': 6, 'ram': [[1, 0]]},
                'cycles': [[1, 0, 'read'], [2, None, 'read'], [None, None, 'wait'], [9, 7, 'write']]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cases.txt'
            selftest.write_spc700([case], path)
            tokens = path.read_text().split()
        self.assertEqual(tokens[-13:], ['4', '1', '0', '0', '2', '-1', '0', '-1', '-1', '2', '9', '7', '1'])


class HarnessSourceTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_the_harnesses_are_developer_tools_that_no_game_stamp_hashes(self):
        from retrorecomp import stamp_inputs
        for name in ('native/snes_cpu/cpu_vector_checks.c', 'native/snes_cpu/spc_vector_checks.c'):
            self.assertIn(name, stamp_inputs.NOT_INPUTS)
            self.assertTrue((self.ROOT / name).exists())

    def test_no_case_or_vector_file_is_in_the_repository(self):
        tracked = (self.ROOT / 'tools/prepare_publication.py').read_text(encoding='utf-8')
        self.assertNotRegex(tracked, r'snes-vectors|SingleStepTests/65816/')
        gitignore = (self.ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('.deps', gitignore)


if __name__ == '__main__':
    unittest.main()
