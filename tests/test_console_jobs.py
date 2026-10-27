"""Games converted at once per console: the shared value stays the default and the cap."""
from pathlib import Path
from threading import Event, Lock
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from retrorecomp.batch import BatchItem
from retrorecomp.queue_state import (GroupCancel, convert_in_groups, console_jobs, job_groups,
                                     normalize_console_jobs, run_limited)


def items(*systems):
    return [BatchItem(Path(f'{n}.rom'), f'Game {n}', system=system, sha256=f'{n:064x}')
            for n, system in enumerate(systems)]


class Settings(unittest.TestCase):
    def test_only_well_formed_numbers_of_known_consoles_are_kept(self):
        self.assertEqual(normalize_console_jobs({'sms': 8, 'ng': 2, 'x68': 1, 'cps1': 3, 'xx': 2,
                                                 'gb': 0, 'nes': 9, 'md': '2', 'snes': True, 'gg': 2.0}),
                         {'sms': 8, 'ng': 2, 'x68': 1, 'cps1': 3})
        self.assertEqual(normalize_console_jobs(None), {})
        self.assertEqual(normalize_console_jobs([]), {})

    def test_a_console_follows_the_shared_value_and_never_exceeds_it(self):
        self.assertEqual(console_jobs(3, {}, 'ng'), 3)
        self.assertEqual(console_jobs(3, {'ng': 2}, 'ng'), 2)
        self.assertEqual(console_jobs(3, {'ng': 8}, 'ng'), 3)
        self.assertEqual(console_jobs(3, {'ng': 2}, 'sms'), 3)


class Groups(unittest.TestCase):
    def test_a_queue_with_nothing_set_is_one_group_as_before(self):
        queue = items('sms', 'ng', 'x68', 'gb', '')
        for per_console in ({}, {'ng': 3}, {'ng': 8}):
            groups = job_groups(queue, 3, per_console)
            self.assertEqual([(g.console, g.rows, g.jobs) for g in groups], [('', [0, 1, 2, 3, 4], 3)])

    def test_a_console_below_the_shared_value_has_its_own_group_in_queue_order(self):
        queue = items('sms', 'ng', 'x68', 'sms', 'ng', 'gb', '')
        groups = job_groups(queue, 8, {'ng': 2, 'x68': 1, 'sms': 8})
        self.assertEqual([(g.console, g.rows, g.jobs) for g in groups],
                         [('', [0, 3, 5, 6], 8), ('ng', [1, 4], 2), ('x68', [2], 1)])
        self.assertEqual([g.need for g in groups], [4, 2, 1])

    def test_a_setting_for_a_console_not_in_the_queue_changes_nothing(self):
        self.assertEqual(len(job_groups(items('sms', 'gb'), 8, {'ng': 1})), 1)


class Fake:
    """A stand-in for convert_batch: `jobs` workers, one result per row."""

    def __init__(self, delay=0.05, fail=None):
        self.calls, self.lock, self.delay, self.fail = [], Lock(), delay, fail
        self.active = self.peak = 0
        self.by_console, self.peak_by_console = {}, {}

    def __call__(self, queue, output, *, cancel=None, on_event=None, emit=print, jobs=1, **options):
        if self.fail and queue[0].system == self.fail:
            raise OSError('disk full')
        self.calls.append(([item.system for item in queue], jobs, options, cancel))
        workers = min(jobs, len(queue))
        results = [None] * len(queue)
        with self.lock:
            self.active += workers
            self.peak = max(self.peak, self.active)
            console = queue[0].system
            self.by_console[console] = self.by_console.get(console, 0) + workers
            self.peak_by_console[console] = max(self.peak_by_console.get(console, 0), self.by_console[console])
        done = 0
        for index, item in enumerate(queue):
            if cancel is not None and cancel.is_set():
                break
            on_event('start', index, item.title)
            time.sleep(self.delay)
            results[index] = {'status': 'success', 'title': item.title, 'system': item.system}
            on_event('result', index, results[index])
            done += 1
        with self.lock:
            self.active -= workers
            self.by_console[console] -= workers
        games = [r for r in results if r is not None]
        return {'requested': len(queue), 'succeeded': len(games), 'failed': 0, 'unrecognized': 0,
                'skipped': 0, 'duplicates': 0, 'existing': 0, 'current': 0, 'stopped': 0,
                'pending_installations': 0, 'pending': len(queue) - len(games),
                'cancelled': len(games) < len(queue), 'games': games}


class Conversion(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name).resolve()

    def test_nothing_set_is_the_former_single_call_with_the_shared_value(self):
        fake, events = Fake(), []
        record = convert_in_groups(items('sms', 'ng', 'x68'), self.output, jobs=3, per_console={'ng': 3},
                                   on_event=lambda *event: events.append(event), convert=fake, force=True)
        self.assertEqual(len(fake.calls), 1)
        systems, jobs, options, _ = fake.calls[0]
        self.assertEqual((systems, jobs, options), (['sms', 'ng', 'x68'], 3, {'force': True}))
        self.assertEqual(record['succeeded'], 3)

    def test_each_group_gets_its_number_and_events_carry_the_rows_of_the_whole_queue(self):
        fake, events = Fake(), []
        queue = items('sms', 'ng', 'sms', 'x68', 'ng')
        record = convert_in_groups(queue, self.output, jobs=8, per_console={'ng': 2, 'x68': 1},
                                   on_event=lambda *event: events.append(event), convert=fake, shared_paths={})
        self.assertEqual(sorted((systems[0], jobs) for systems, jobs, _, _ in fake.calls),
                         [('ng', 2), ('sms', 8), ('x68', 1)])
        self.assertTrue(all(options == {'shared_paths': {}} for *_, options, _ in fake.calls))
        starts = sorted(index for kind, index, _ in events if kind == 'start')
        results = sorted(index for kind, index, _ in events if kind == 'result')
        self.assertEqual((starts, results), ([0, 1, 2, 3, 4], [0, 1, 2, 3, 4]))
        for kind, index, value in events:
            if kind == 'result':
                self.assertEqual(value['system'], queue[index].system)
        # One summary, games in queue order, one batch record on disk.
        self.assertEqual([g['title'] for g in record['games']], [f'Game {n}' for n in range(5)])
        self.assertEqual((record['requested'], record['succeeded'], record['pending'], record['cancelled'],
                          record['jobs']), (5, 5, 0, False, 8))
        saved = json.loads((self.output / 'datas/Retro-Recomp-batch.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['succeeded'], 5)
        self.assertEqual(len(saved['games']), 5)

    def test_groups_never_run_more_games_together_than_the_shared_value(self):
        fake = Fake(delay=0.08)
        # 4 sms (needs 4 of 5), 3 ng at 2, 3 x68 at 1: 4 + 2 > 5, so ng waits for room.
        queue = items('sms', 'sms', 'sms', 'sms', 'ng', 'ng', 'ng', 'x68', 'x68', 'x68')
        convert_in_groups(queue, self.output, jobs=5, per_console={'ng': 2, 'x68': 1}, convert=fake)
        self.assertLessEqual(fake.peak, 5)
        self.assertLessEqual(fake.peak_by_console['ng'], 2)
        self.assertLessEqual(fake.peak_by_console['x68'], 1)
        self.assertLessEqual(fake.peak_by_console['sms'], 5)
        # The x68 group fits next to the four sms workers: they overlapped.
        self.assertEqual(fake.peak, 5)

    def test_a_console_set_to_one_runs_its_games_one_after_the_other_beside_the_others(self):
        fake = Fake(delay=0.05)
        queue = items('sms', 'sms', 'x68', 'x68')
        convert_in_groups(queue, self.output, jobs=4, per_console={'x68': 1}, convert=fake)
        self.assertEqual(fake.peak_by_console['x68'], 1)
        self.assertEqual(fake.peak, 3)

    def test_stop_leaves_the_groups_still_waiting_pending_and_cancelled(self):
        cancel, fake = Event(), Fake()
        def event(kind, index, value):
            if kind == 'start':
                cancel.set()
        queue = items('sms', 'sms', 'ng', 'ng', 'x68')
        record = convert_in_groups(queue, self.output, jobs=2, per_console={'ng': 1, 'x68': 1},
                                   cancel=cancel, on_event=event, convert=fake)
        # jobs=2: the sms group (2 workers) fills the cap and the others never start.
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(record['cancelled'])
        self.assertEqual(record['pending'], 5 - record['succeeded'])
        self.assertGreaterEqual(record['pending'], 3)

    def test_stop_before_anything_starts_converts_nothing(self):
        cancel, fake = Event(), Fake()
        cancel.set()
        record = convert_in_groups(items('sms', 'ng'), self.output, jobs=2, per_console={'ng': 1},
                                   cancel=cancel, convert=fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual((record['cancelled'], record['pending'], record['games']), (True, 2, []))

    def test_a_group_that_raises_is_reported_after_the_running_ones_end(self):
        fake = Fake(fail='ng')
        with self.assertRaises(OSError):
            convert_in_groups(items('sms', 'ng', 'sms'), self.output, jobs=8, per_console={'ng': 1}, convert=fake)

    def test_events_reach_the_handler_one_at_a_time(self):
        fake, inside, overlaps = Fake(delay=0.01), [], []
        def event(kind, index, value):
            inside.append(1)
            overlaps.append(len(inside))
            time.sleep(0.002)
            inside.pop()
        convert_in_groups(items(*['sms', 'ng', 'x68'] * 4), self.output, jobs=8,
                          per_console={'ng': 2, 'x68': 1}, on_event=event, convert=fake)
        self.assertEqual(max(overlaps), 1)


class StopNow(unittest.TestCase):
    def test_a_group_started_after_stop_now_raises_the_stop_flag_again(self):
        cancel, now = Event(), Event()
        group = GroupCancel(cancel, now)
        with patch('retrorecomp.core.stop_processes') as kill, patch('retrorecomp.core.stop_requested', return_value=False):
            self.assertFalse(group.is_set())
            kill.assert_not_called()
            cancel.set()
            self.assertTrue(group.is_set())
            kill.assert_not_called()   # "wait for the running games": nothing is killed
            now.set()
            self.assertTrue(group.is_set())
            kill.assert_called_once()

    def test_the_flag_is_not_raised_twice(self):
        cancel, now = Event(), Event()
        cancel.set(), now.set()
        with patch('retrorecomp.core.stop_processes') as kill, patch('retrorecomp.core.stop_requested', return_value=True):
            self.assertTrue(GroupCancel(cancel, now).is_set())
            kill.assert_not_called()


class Reconvert(unittest.TestCase):
    def run_games(self, systems, jobs, per_console, delay=0.04):
        lock, active, peak, by_console, peak_by = Lock(), [0], [0], {}, {}
        finished_order = []

        def work(entry):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                by_console[entry[0]] = by_console.get(entry[0], 0) + 1
                peak_by[entry[0]] = max(peak_by.get(entry[0], 0), by_console[entry[0]])
            time.sleep(delay)
            with lock:
                active[0] -= 1
                by_console[entry[0]] -= 1
            if entry[1] == 'bad':
                raise ValueError('bad')
            return entry

        run_limited([(system, str(n)) for n, system in enumerate(systems)], lambda entry: entry[0], jobs,
                    per_console, work, lambda entry, future: finished_order.append((entry, future)))
        return peak[0], peak_by, finished_order

    def test_a_console_limit_holds_while_other_consoles_use_the_free_places(self):
        peak, by_console, finished = self.run_games(['x68'] * 3 + ['sms'] * 4 + ['ng'] * 2, 4, {'x68': 1, 'ng': 1})
        self.assertEqual(by_console['x68'], 1)
        self.assertEqual(by_console['ng'], 1)
        self.assertLessEqual(peak, 4)
        self.assertEqual(len(finished), 9)

    def test_a_game_of_a_limited_console_does_not_hold_back_the_others(self):
        # x68 first, limit 1: the sms games behind it still use the three other places.
        peak, by_console, _ = self.run_games(['x68'] * 4 + ['sms'] * 3, 4, {'x68': 1})
        self.assertEqual(peak, 4)
        self.assertEqual(by_console['x68'], 1)

    def test_nothing_set_runs_up_to_the_shared_value(self):
        peak, _, finished = self.run_games(['gb'] * 6, 3, {})
        self.assertEqual(peak, 3)
        self.assertEqual(len(finished), 6)

    def test_failures_reach_the_callback_of_their_own_game(self):
        calls = []

        def work(entry):
            if entry[1] == 'bad':
                raise ValueError('x')
            return entry
        run_limited([('gb', 'ok'), ('gb', 'bad')], lambda e: e[0], 2, {}, work,
                    lambda e, future: calls.append((e, future.exception() is not None)))
        self.assertEqual(sorted(calls), [(('gb', 'bad'), True), (('gb', 'ok'), False)])


if __name__ == '__main__':
    unittest.main()
