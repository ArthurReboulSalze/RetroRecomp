"""Parallel games share compiler capacity without global environment changes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch
from retrorecomp.platforms import compilation_budget, build_jobs


class CompilerBudgetTests(unittest.TestCase):
    def test_parallel_games_are_capped_to_available_host_cpus(self):
        with patch('retrorecomp.platforms.available_cpus', return_value=8), \
                patch.dict('os.environ',{'RETRO_RECOMP_BUILD_JOBS':'4'}):
            self.assertEqual(build_jobs(),'4')
            with compilation_budget(8):self.assertEqual(build_jobs(),'1')
            with compilation_budget(4):self.assertEqual(build_jobs(),'2')
            self.assertEqual(build_jobs(),'4')

    def test_nested_budget_is_restored_even_after_failure(self):
        with patch('retrorecomp.platforms.available_cpus',return_value=16), \
                patch.dict('os.environ',{'RETRO_RECOMP_BUILD_JOBS':'8'}):
            with compilation_budget(4):
                self.assertEqual(build_jobs(),'4')
                with self.assertRaises(RuntimeError):
                    with compilation_budget(8):
                        self.assertEqual(build_jobs(),'2');raise RuntimeError('authored failure')
                self.assertEqual(build_jobs(),'4')
            self.assertEqual(build_jobs(),'8')

    def test_a_game_converted_alone_on_windows_uses_its_cpu_share_up_to_eight_jobs(self):
        import os
        environment = {key: value for key, value in os.environ.items() if key != 'RETRO_RECOMP_BUILD_JOBS'}
        with patch('retrorecomp.platforms.os.name', 'nt'), patch.dict('os.environ', environment, clear=True):
            for cpus, alone in ((24, '8'), (6, '6'), (1, '1')):
                with self.subTest(cpus=cpus), patch('retrorecomp.platforms.available_cpus', return_value=cpus):
                    self.assertEqual(build_jobs(), alone)
            with patch('retrorecomp.platforms.available_cpus', return_value=24), compilation_budget(8):
                self.assertEqual(build_jobs(), '3')

    def test_simultaneous_workers_do_not_change_each_others_budget(self):
        barrier=Barrier(2)
        def work(games):
            with compilation_budget(games):
                barrier.wait(timeout=5);return build_jobs()
        with patch('retrorecomp.platforms.available_cpus',return_value=8), \
                patch.dict('os.environ',{'RETRO_RECOMP_BUILD_JOBS':'8'}), \
                ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(work,(2,8))),['4','1'])
            self.assertEqual(build_jobs(),'8')


if __name__ == '__main__':unittest.main()
