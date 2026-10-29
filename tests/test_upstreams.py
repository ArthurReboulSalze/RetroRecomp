"""The upstream registry, the pins in the code and docs/UPSTREAMS.md must agree (no network, no ROM).

Every machine declares its upstreams in `retrorecomp/upstreams.py`; every declared pin must be readable from the
place the code holds it; and the page `docs/UPSTREAMS.md` must carry a row and the revision of each of them, so a
bump or a new machine that forgets the page fails here.
"""
import re
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from retrorecomp import upstreams  # noqa: E402
from retrorecomp.systems import ALL_PROFILES  # noqa: E402
import check_upstreams  # noqa: E402

DOC = (ROOT / 'docs/UPSTREAMS.md').read_text(encoding='utf-8')
COMMIT = re.compile(r'^[0-9a-f]{40}$')
# The upstreams the project is known to pin; a reader that finds fewer has lost some.
KNOWN = {'smsggrecomp', 'z80-recomp-core', 'gb-recompiled', 'nesrecomp', 'segagenesisrecomp', 'm68k-recomp-core',
         'snesrecomp', 'geolith-libretro', 'lithogen', 'ymfm', 'mame', 'px68k', 'px68k-libretro', 'SDL',
         'llvm-mingw', 'CMake', 'Ninja', 'UPX', 'SingleStepTests/z80', 'SingleStepTests/m68000'}


def declaration_problems(machine_ids, table, reasons):
    """Sentences for the machines that declare nothing (an empty tuple needs a reason)."""
    problems = []
    for machine in machine_ids:
        if machine in table and table[machine]:
            continue
        if machine in table or machine in reasons:
            if not reasons.get(machine):
                problems.append(f'{machine} declares no upstream and gives no reason in NO_UPSTREAM')
        else:
            problems.append(f'{machine} has no entry in MACHINE_UPSTREAMS')
    for machine in set(table) | set(reasons):
        if machine not in machine_ids:
            problems.append(f'{machine} is declared but is not a machine of retrorecomp.systems')
    return problems


def rows_of(repo):
    return [line for line in DOC.splitlines() if line.startswith(f'| [{repo}](')]


class RegistryTests(unittest.TestCase):
    def test_every_machine_declares_its_upstreams(self):
        ids = [profile.id for profile in ALL_PROFILES]
        self.assertEqual([], declaration_problems(ids, upstreams.MACHINE_UPSTREAMS, upstreams.NO_UPSTREAM))

    def test_a_missing_declaration_is_found(self):
        table = {'a': (upstreams.SDL,), 'b': ()}
        found = declaration_problems(['a', 'b', 'c'], table, {})
        self.assertEqual(2, len(found))
        self.assertEqual([], declaration_problems(['a', 'b'], table, {'b': 'uses no third-party code'}))
        self.assertTrue(declaration_problems(['a'], {'a': (), 'zz': ()}, {'a': 'x'}))

    def test_the_reader_finds_the_known_upstreams(self):
        keys = {item.key for item in upstreams.all_upstreams()}
        self.assertFalse(KNOWN - keys, f'the registry lost: {sorted(KNOWN - keys)}')
        self.assertEqual(len(keys), len(upstreams.all_upstreams()), 'an upstream is listed twice')

    def test_every_pin_is_read_from_the_code(self):
        for item in upstreams.all_upstreams():
            with self.subTest(item.key):
                pin = upstreams.pin_of(item)
                if item.pin.kind == 'submodule':
                    self.assertIsNotNone(item.parent, 'a submodule names its parent')
                    self.assertIn(item.parent.key, {u.key for u in upstreams.all_upstreams()})
                    if pin is not None:                       # only when .deps has the pinned checkout
                        self.assertRegex(pin, COMMIT)
                    continue
                self.assertIsNotNone(pin, f'{item.pin.where} cannot be read')
                if item.is_version:
                    self.assertRegex(pin, r'^\d[\w.]*$')
                else:
                    self.assertRegex(pin, COMMIT)

    def test_duplicate_pins_agree(self):
        for item in upstreams.all_upstreams():
            for other in item.also:
                with self.subTest(item.key, other=other.where):
                    self.assertEqual(upstreams.pin_of(item), upstreams.read_pin(other))

    def test_every_machine_upstream_has_consoles(self):
        for item in upstreams.all_upstreams():
            self.assertTrue(upstreams.consoles_of(item), item.key)

    def test_the_branch_and_licence_are_declared(self):
        for item in upstreams.all_upstreams():
            for field in ('repo', 'branch', 'role', 'licence', 'compiled'):
                self.assertTrue(getattr(item, field), f'{item.key}.{field}')
            self.assertRegex(item.repo, r'^[\w.-]+/[\w.-]+$')


class DocumentTests(unittest.TestCase):
    def test_every_upstream_has_a_row_in_both_tables(self):
        for item in upstreams.all_upstreams():
            with self.subTest(item.key):
                self.assertGreaterEqual(len(rows_of(item.repo)), 2, f'docs/UPSTREAMS.md needs a row of {item.repo} in the '
                                        'pins table and in the role table')

    def test_every_pin_is_in_the_document(self):
        for item in upstreams.all_upstreams():
            pin = upstreams.pin_of(item)
            first = (rows_of(item.repo) or [''])[0]
            with self.subTest(item.key):
                if pin is not None:
                    self.assertIn(pin, first, f'the full pin of {item.key} is not in its row')
                    self.assertIn(pin[:7] if not item.is_version else pin, first)
                if item.pin.kind == 'submodule':
                    self.assertIn(item.pin.path, first)
                elif item.pin.kind == 'json':
                    self.assertIn(item.pin.file, first)
                else:
                    stem = item.pin.where
                    self.assertIn(stem, first, f'{stem} is not named in the row of {item.key}')
                for other in item.also:
                    self.assertIn(other.file if other.kind == 'json' else other.where, first)
                for machine in upstreams.consoles_of(item):
                    if '*' not in item.shared_by:
                        self.assertIn(machine, first, f'{machine} is not named in the row of {item.key}')
                if '*' in item.shared_by:
                    self.assertIn('all', first)

    def test_the_review_date_is_stated(self):
        self.assertRegex(DOC, r'Last full review: \*\*\d{1,2} [A-Z][a-z]+ 20\d\d\*\*')

    def test_the_sections_exist(self):
        for heading in ('## The pins', '## How to check an upstream', '## Decision rule', '## Licence rule',
                        '## The anchor method', '## Deferred', '## How to record a review'):
            self.assertIn(heading, DOC)
        self.assertIn('carried as our own patches in 1.6.3', DOC)


class ToolTests(unittest.TestCase):
    def test_list_runs_offline(self):
        done = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_upstreams.py'), '--list'],
                              capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual(0, done.returncode, done.stderr)
        for key in KNOWN:
            self.assertIn(key, done.stdout)
        self.assertNotIn('MISMATCH', done.stdout)
        self.assertNotIn('NOT READABLE', done.stdout)

    def test_pins_never_touch_the_network(self):
        def refuse(*args, **kwargs):
            raise AssertionError('the offline reader opened a connection')
        with patch.object(socket.socket, 'connect', refuse), patch.object(check_upstreams, 'api', refuse):
            rows = check_upstreams.pins()
        self.assertTrue(all(row['pin'] or row['where'].startswith('submodule') for row in rows))

    def test_a_network_failure_is_reported_on_its_row(self):
        def fail(path, params=None):
            raise check_upstreams.ApiError('HTTP 503 offline test')
        item = upstreams.SMSGGRECOMP
        base = next(row for row in check_upstreams.pins() if row['key'] == item.key)
        with patch.object(check_upstreams, 'api', fail):
            row = check_upstreams.check(item, base)
            rows = check_upstreams.run_online({'SDL', 'UPX'})
        self.assertIn('503', row['error'])
        self.assertEqual({'SDL', 'UPX'}, {r['key'] for r in rows})
        self.assertTrue(all(r['error'] for r in rows))

    def test_the_tool_never_writes_into_deps(self):
        source = (ROOT / 'tools/check_upstreams.py').read_text(encoding='utf-8')
        for forbidden in ('write_text', 'write_bytes', 'rmtree', 'unlink', "'clone'", "'fetch'", "'checkout'"):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
