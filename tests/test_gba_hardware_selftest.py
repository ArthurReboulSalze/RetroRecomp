"""The pure parts of the Game Boy Advance hardware self-test (tools/gba_hardware_selftest.py), without a ROM, a BIOS or a compiler.

The cartridges are zero-filled files and the pictures are drawn here with Pillow; nothing is converted or run.
"""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SPEC = importlib.util.spec_from_file_location('gba_hardware_selftest', Path(__file__).resolve().parents[1] / 'tools' / 'gba_hardware_selftest.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def make_tree(root: Path) -> None:
    for relative in (*tool.JUDGED, 'ppu/hello.gba', 'ppu/shades.gba', 'nes/nes.gba', 'unsafe/unsafe.gba'):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(256))
    (root / 'README.md').write_text('not a cartridge', encoding='utf-8')


def draw(path: Path, color: tuple[int, int, int], mode: str = 'RGB') -> str:
    """A 240x160 picture of one colour; returns the SHA-256 of its RGB pixel data."""
    image = Image.new('RGB', (240, 160), color)
    image.save(path, format='PNG')
    return hashlib.sha256(image.tobytes()).hexdigest()


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        make_tree(self.root)
        self.tests = tool.discover(self.root)

    def tearDown(self):
        self.folder.cleanup()

    def test_every_cartridge_is_listed_and_other_files_are_not(self):
        self.assertEqual(len(self.tests), len(tool.JUDGED) + 4)
        self.assertNotIn('README.md', [test['name'] for test in self.tests])

    def test_the_eight_suites_are_judged(self):
        judged = {test['name'] for test in self.tests if test['judged']}
        self.assertEqual(judged, set(tool.JUDGED))
        self.assertEqual(len(judged), 8)

    def test_visual_and_other_roms_are_not_judged_with_a_reason(self):
        reasons = {test['name']: test['not_judged'] for test in self.tests if not test['judged']}
        self.assertEqual(set(reasons), {'ppu/hello.gba', 'ppu/shades.gba', 'nes/nes.gba', 'unsafe/unsafe.gba'})
        self.assertIn('visual', reasons['ppu/hello.gba'])
        self.assertTrue(all(reasons.values()))

    def test_ids_are_flat_and_the_rom_hash_is_a_hash_of_its_bytes(self):
        ids = [test['id'] for test in self.tests]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('save-flash64', ids)
        self.assertTrue(all('/' not in item for item in ids))
        self.assertTrue(all(test['sha256'] == hashlib.sha256(bytes(256)).hexdigest() for test in self.tests))

    def test_only_keeps_the_matching_ids(self):
        self.assertEqual([test['id'] for test in tool.select(self.tests, ['thumb'])], ['thumb-thumb'])
        self.assertEqual(len(tool.select(self.tests, None)), len(self.tests))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.saved = tool.EXPECTED_PASS_PICTURE, dict(tool.EXPECTED_BY_SUITE)
        self.addCleanup(self.restore)

    def restore(self):
        tool.EXPECTED_PASS_PICTURE = self.saved[0]
        tool.EXPECTED_BY_SUITE.clear()
        tool.EXPECTED_BY_SUITE.update(self.saved[1])

    def test_the_picture_hash_is_of_the_pixels_not_of_the_file(self):
        expected = draw(self.root / 'a.png', (10, 20, 30))
        self.assertEqual(tool.picture_hash(self.root / 'a.png'), expected)
        image = Image.open(self.root / 'a.png')
        image.save(self.root / 'b.png', format='PNG', optimize=True, compress_level=0)
        self.assertEqual(tool.picture_hash(self.root / 'b.png'), expected)

    def test_a_matching_picture_passes(self):
        tool.EXPECTED_PASS_PICTURE = draw(self.root / 'pass.png', (0, 0, 0))
        verdict, reason = tool.judge('arm/arm.gba', tool.picture_hash(self.root / 'pass.png'))
        self.assertEqual(verdict, 'pass')
        self.assertTrue(reason)

    def test_a_different_picture_fails(self):
        tool.EXPECTED_PASS_PICTURE = draw(self.root / 'pass.png', (0, 0, 0))
        draw(self.root / 'other.png', (200, 0, 0))
        self.assertEqual(tool.judge('arm/arm.gba', tool.picture_hash(self.root / 'other.png'))[0], 'fail')

    def test_no_picture_or_a_stopped_host_fails(self):
        tool.EXPECTED_PASS_PICTURE = draw(self.root / 'pass.png', (0, 0, 0))
        self.assertEqual(tool.judge('arm/arm.gba', None)[0], 'fail')
        same = tool.picture_hash(self.root / 'pass.png')
        verdict, reason = tool.judge('arm/arm.gba', same, exit_code=3, aborted='FATAL: overflow')
        self.assertEqual(verdict, 'fail')
        self.assertIn('FATAL', reason)

    def test_a_per_suite_hash_overrides_the_common_one(self):
        common = draw(self.root / 'common.png', (0, 0, 0))
        special = draw(self.root / 'special.png', (9, 9, 9))
        tool.EXPECTED_PASS_PICTURE = common
        tool.EXPECTED_BY_SUITE['bios/bios.gba'] = special
        self.assertEqual(tool.judge('bios/bios.gba', special)[0], 'pass')
        self.assertEqual(tool.judge('bios/bios.gba', common)[0], 'fail')
        self.assertEqual(tool.judge('arm/arm.gba', common)[0], 'pass')


class ReportTests(unittest.TestCase):
    def rows(self, *verdicts):
        return [{'id': f'r{index}', 'name': f'r{index}.gba', 'verdict': verdict} for index, verdict in enumerate(verdicts)]

    def test_all_judged_passing_exits_zero_whatever_is_not_judged(self):
        rows = self.rows('pass', 'pass', 'not judged', 'not applicable')
        self.assertEqual(tool.exit_code(rows), 0)
        self.assertEqual(tool.aggregate(rows)['counts'], {'pass': 2, 'not judged': 1, 'not applicable': 1})
        self.assertEqual(tool.aggregate(rows)['judged'], 2)

    def test_one_failure_or_one_missing_run_exits_one(self):
        self.assertEqual(tool.exit_code(self.rows('pass', 'fail')), 1)
        self.assertEqual(tool.exit_code(self.rows('pass', 'not run')), 1)

    def test_nothing_judged_is_not_a_proof(self):
        self.assertEqual(tool.exit_code(self.rows('not judged', 'not applicable')), 1)
        self.assertEqual(tool.exit_code([]), 1)

    def test_a_visual_test_is_never_counted_as_passed(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        make_tree(root)
        rows = [tool.row_of(test) for test in tool.discover(root)]
        visual = [row for row in rows if row['name'].startswith('ppu/')]
        self.assertTrue(visual)
        self.assertTrue(all(row['verdict'] == 'not judged' and row['reason'] for row in visual))
        self.assertEqual(sum(row['verdict'] == 'not run' for row in rows), 8)

    def test_the_report_round_trips_and_keeps_finished_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root, work = Path(folder) / 'roms', Path(folder) / 'work'
            make_tree(root)
            tests = tool.discover(root)
            rows = tool.merge_rows(tests, [])
            rows[0] = dict(rows[0], verdict='pass', reason='ok', picture_sha256='ab' * 32, interpreted_instructions=0)
            tool.write_report(work, rows)
            stored = tool.load_rows(work)
            self.assertEqual(stored[0]['verdict'], 'pass')
            merged = tool.merge_rows(tests, stored)
            self.assertEqual(merged[0]['verdict'], 'pass')
            self.assertEqual(sum(row['verdict'] == 'not run' for row in merged), 7)
            # a ROM whose bytes changed loses its stored verdict
            changed = [dict(test, sha256='0' * 64) if test is tests[0] else test for test in tests]
            self.assertEqual(tool.merge_rows(changed, stored)[0]['verdict'], tool.row_of(changed[0])['verdict'])
            self.assertIn('physical_latency', (work / tool.REPORT_NAME).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
