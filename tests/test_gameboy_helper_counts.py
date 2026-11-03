"""The guarded helpers are counted (1.6.7, gate G3): the line the runtime prints, how the probe reads it, and the schema-2 scenario that carries it."""
import unittest

from retrorecomp import gameboy
from retrorecomp.report_schema import read_report
from tests.test_report_schema import gb_report

LINE = ('[RR-HELPERS] store_entries=1 store_cycles=8 copy_entries=3 copy_cycles=250 dma_page_entries=0 dma_page_cycles=0 '
        'interrupt_dma_entries=2 interrupt_dma_cycles=8')


class ParsingTests(unittest.TestCase):
    def test_the_line_gives_four_kinds_with_entries_and_cycles(self):
        counts = list(map(int, gameboy.HELPERS.search('noise\n' + LINE + '\nmore').groups()))
        self.assertEqual(counts, [1, 8, 3, 250, 0, 0, 2, 8])
        self.assertEqual(gameboy.HELPER_KINDS, ('store', 'copy', 'dma_page', 'interrupt_dma'))

    def test_a_line_that_lacks_a_kind_is_not_read(self):
        self.assertIsNone(gameboy.HELPERS.search(LINE.replace(' interrupt_dma_entries=2 interrupt_dma_cycles=8', '')))


class SchemaTests(unittest.TestCase):
    def test_the_counts_ride_in_the_scenario_of_the_main_cpu_beside_the_one_at_a_time_counts(self):
        report = gb_report()
        for row in report['final_checks']:
            row['ram_stub_instructions'] = row['ram_single_step_instructions'] = row['highmem_stub_instructions'] = 0
            row['ram_stub_cycles'] = row['ram_single_step_cycles'] = row['highmem_stub_cycles'] = 0
            row['guarded_helpers'] = {'store': {'entries': 1, 'cycles': 8}, 'copy': {'entries': 3, 'cycles': 250},
                                      'dma_page': {'entries': 0, 'cycles': 0}, 'interrupt_dma': {'entries': 2, 'cycles': 8}}
        scenario = read_report(report)['cpus'][0]['scenarios'][0]
        self.assertEqual(scenario['guarded_helpers']['copy'], {'entries': 3, 'cycles': 250})
        self.assertEqual(scenario['ram_single_step']['stub_instructions'], 0)         # a separate field
        self.assertEqual(scenario['interpreted'], 0)                                  # never added to the interpreter

    def test_a_row_without_the_counts_has_none_and_they_are_never_invented(self):
        scenario = read_report(gb_report())['cpus'][0]['scenarios'][0]
        self.assertNotIn('guarded_helpers', scenario)


if __name__ == '__main__':
    unittest.main()
