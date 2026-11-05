"""The gauges and the symbol matrix of docs/QUALIFICATION.md are written from the matrix in letters, never by hand."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO))

import qualification_gauges as qg  # noqa: E402
from retrorecomp.systems import ALL_PROFILES  # noqa: E402
from tests.test_machine_registry import _qualification_matrix  # noqa: E402


def _page() -> str:
    return qg.PAGE.read_text(encoding='utf-8')


class GaugeArithmeticTests(unittest.TestCase):
    def test_met_counts_one_partial_a_half_unknown_and_no_zero_and_not_applicable_leaves_the_count(self):
        row = qg.gauge(list('YYPP?N-'))
        self.assertEqual(row['applicable'], 6)
        self.assertEqual(row['percent'], 50)   # (2 + 1) / 6
        self.assertEqual(row['bar'], '█████░░░░░')
        self.assertEqual(qg.gauge(list('YYYY'))['percent'], 100)
        self.assertEqual(qg.gauge(list('YYYY'))['bar'], '██████████')
        self.assertEqual(qg.gauge(list('?N'))['percent'], 0)
        self.assertEqual(qg.gauge(list('---'))['percent'], 0)

    def test_rounding_is_half_up_to_the_unit(self):
        # 5 met and 9 partial of 15 applicable: 63.33 -> 63; 1 met and 1 partial of 4: 37.5 -> 38
        self.assertEqual(qg.gauge(list('YYYYY' + 'P' * 9 + '?' + '-'))['percent'], 63)
        self.assertEqual(qg.gauge(list('YP??'))['percent'], 38)

    def test_the_bar_has_ten_cells(self):
        for letters in ('Y', 'P', 'YP', 'YYP?', '?'):
            self.assertEqual(len(qg.gauge(list(letters))['bar']), qg.CELLS)


class PageTests(unittest.TestCase):
    def test_the_block_agrees_with_the_matrix(self):
        text = _page()
        self.assertEqual(qg.current_block(text), qg.render(text),
                         'run python tools/qualification_gauges.py --write')

    def test_rewriting_changes_nothing_when_the_page_is_in_agreement(self):
        text = _page()
        self.assertEqual(qg.rewritten(text), text)

    def test_the_letters_stay_the_source_the_registry_test_reads(self):
        ids, matrix = qg.read_matrix(_page())
        registry = _qualification_matrix()
        self.assertEqual(ids, list(registry))
        for gate, cells in matrix.items():
            for console in ids:
                self.assertEqual(cells[console], registry[console][gate], (gate, console))

    def test_every_cell_has_a_symbol_and_every_gate_a_short_name(self):
        text = _page()
        _, matrix = qg.read_matrix(text)
        names = qg.read_short_names(text)
        self.assertEqual(list(matrix), list(names))
        self.assertEqual(len(matrix), 16)
        for gate, cells in matrix.items():
            self.assertTrue(names[gate], gate)
            self.assertLessEqual(len(names[gate]), 18, gate)
            for console, cell in cells.items():
                self.assertIn(cell, qg.SYMBOLS, (gate, console))

    def test_the_status_column_is_the_registry_status_and_covers_every_console(self):
        rows = qg.gauges(_page())
        self.assertEqual({row['id'] for row in rows}, {profile.id for profile in ALL_PROFILES})
        for row in rows:
            profile = next(p for p in ALL_PROFILES if p.id == row['id'])
            self.assertEqual((row['name'], row['status']), (profile.name, profile.status))

    def test_the_text_says_what_the_bar_is_not(self):
        block = qg.render(_page())
        self.assertIn('not a quality score', block)
        for measure in ('native code', 'CPU fidelity', 'hardware fidelity', 'gameplay validation', 'physical latency'):
            self.assertIn(measure, block)
        self.assertIn('owner\'s own decision', block)

    def test_the_compact_form_has_one_line_per_console_and_says_what_it_is(self):
        text = qg.short(_page())
        rows = [line for line in text.splitlines() if line.startswith('| ')]
        self.assertEqual(len(rows), 2 + len(ALL_PROFILES))
        self.assertIn('not a quality score', text)
        self.assertIn(qg.ANCHOR, text)


class ReadmeTests(unittest.TestCase):
    def test_the_readme_block_agrees_with_the_matrix(self):
        readme = qg.README.read_text(encoding='utf-8')
        self.assertTrue(qg.readme_in_agreement(readme, _page()), 'run python tools/qualification_gauges.py --write')
        self.assertEqual(qg.rewritten(readme, True, _page()), readme)

    def test_the_readme_names_the_experimental_status_in_clear_and_every_console(self):
        block = qg.current_block(qg.README.read_text(encoding='utf-8'), qg.README_BEGIN, qg.END)
        for profile in ALL_PROFILES:
            line = next(row for row in block.splitlines() if row.startswith('| [' + profile.name + '](docs/'))
            self.assertIn(' ' + profile.status + ' ', line)
        # No machine of the list is experimental since 1.6.9: the status column reads the profile, so a new experimental machine shows up here.
        self.assertEqual(block.count('| experimental |'), sum(profile.status == 'experimental' for profile in ALL_PROFILES))

    def test_every_console_of_the_matrix_has_a_page_that_exists(self):
        page = _page()
        ids, _ = qg.read_matrix(page)
        pages = qg.read_pages(page)
        self.assertEqual(sorted(pages), sorted(ids))
        for name in pages.values():
            self.assertTrue((qg.REPO / 'docs' / name).is_file(), name)

    def test_the_link_of_the_readme_reaches_a_heading_of_the_page(self):
        page = _page()
        self.assertIn('\n### Progress through the qualification list\n', page)
        self.assertTrue(qg.ANCHOR.endswith('#progress-through-the-qualification-list'))

    def test_the_check_command_succeeds_and_fails_on_a_drifted_readme(self):
        self.assertEqual(qg.main(['--check']), 0)
        readme = qg.README.read_text(encoding='utf-8')
        self.assertFalse(qg.readme_in_agreement(readme.replace('63 %', '99 %', 1), _page()))


if __name__ == '__main__':
    unittest.main()
