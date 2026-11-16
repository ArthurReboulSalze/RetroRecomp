"""Conversion time estimates in the window: the queue, the scan level in the Options, a running batch and the first use.

The figures and their rules live in time_estimates.py (the reviewed table assets/conversion-times.json); this mixin only
says them, always as an estimate on the reference PC. The batch clock is a Tk timer that ticks once a second while a
batch runs: it waits on nothing and stops with the batch.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk

from . import time_estimates

TICK_MS = 1000


class EstimatesMixin:
    """Conversion time estimates in the window."""

    # --- what this PC already has (first use) ---------------------------------------------------------------------

    def refresh_first_use(self):
        """Look, in a worker, at what a first conversion would still have to download or build; the queue line is
        written again when the answer comes ('first_use' message)."""
        def worker():
            state = {'tools_missing': False, 'shared_missing': False}
            try:
                from .updater import missing_build_tools
                state['tools_missing'] = bool(missing_build_tools())
            except Exception:
                pass
            try:
                from .core import dependencies_ready
                state['shared_missing'] = not dependencies_ready()
            except Exception:
                pass
            self.messages.put(('first_use', state))
        threading.Thread(target=worker, daemon=True).start()

    def first_use_ready(self, state):
        self.first_use_state = state
        self.selection_changed()

    def converted_machines(self):
        """The machines this PC has converted a game of (the compiled games); their engines were downloaded already."""
        try:
            return {game.system for game in self.compiled_inventory.snapshot()}
        except Exception:
            return None

    # --- the queue ------------------------------------------------------------------------------------------------

    def row_level(self, system):
        variable = getattr(self, 'scan_level', {}).get(system)
        try:
            return variable.get() if variable is not None else 'standard'
        except tk.TclError:
            return 'standard'

    def rows_estimate(self, rows, *, first_use=True):
        entries = [(self.items[row].system, self.row_level(self.items[row].system)) for row in rows
                   if row in self.items and self.items[row].system and not self.items[row].error]
        if not entries:
            return None
        try:
            jobs = int(self.jobs.get())
            per_console = self.console_jobs_preferences()
        except (ValueError, tk.TclError):
            jobs, per_console = 1, {}
        state = getattr(self, 'first_use_state', None) if first_use else None
        return time_estimates.queue_estimate(
            entries, jobs=jobs, per_console=per_console,
            tools_missing=bool(state and state.get('tools_missing')),
            shared_missing=bool(state and state.get('shared_missing')),
            converted_machines=self.converted_machines() if state is not None else None)

    def duration(self, seconds, *, up=False):
        return time_estimates.duration_text(seconds, self.tr, up=up)

    def estimate_lines(self, estimate):
        """The queue's estimate in sentences: the time, what is not counted, the first use."""
        if estimate is None or not time_estimates.table():
            return []
        lines = []
        if estimate.games:
            lines.append(self.tr('estimate_queue', typical=self.duration(estimate.typical),
                                 high=self.duration(estimate.high, up=True), reference=time_estimates.reference_label()))
        if estimate.unknown:
            lines.append(self.tr('estimate_unknown', count=estimate.unknown))
        if estimate.first_build:
            lines.append(self.tr('estimate_first_build', time=self.duration(estimate.first_build, up=True)))
        elif estimate.first_download:
            lines.append(self.tr('estimate_first_download'))
        return lines

    def queue_estimate_text(self):
        """The line under the queue when no single game is selected: the estimate of the whole queue."""
        if getattr(self, 'busy', False):
            return ''
        return ' '.join(self.estimate_lines(self.rows_estimate(self.table.get_children())))

    # --- the Options: one game at a level -----------------------------------------------------------------------

    def render_level_estimates(self):
        for console, variable in getattr(self, 'level_timings', {}).items():
            try:
                variable.set(self.level_estimate_text(console))
            except tk.TclError:
                pass

    def level_estimate_text(self, console):
        found = time_estimates.game_time(console, self.row_level(console))
        if found is None:
            return ''
        values = dict(low=self.duration(found.low), high=self.duration(found.high, up=True),
                      longest=self.duration(found.longest, up=True), reference=time_estimates.reference_label())
        return self.tr('estimate_level' if found.measured else 'estimate_level_derived', **values)

    # --- a running batch ------------------------------------------------------------------------------------------

    def start_estimate_clock(self, rows):
        """Called when a batch starts: the estimate goes to the log and the clock starts."""
        self.batch_started = time.monotonic()
        self.job_started = {}
        self.batch_estimate = self.rows_estimate(rows, first_use=False)
        estimate = self.batch_estimate
        if estimate is not None and estimate.games and time_estimates.table():
            self.messages.put(('log', self.tr('estimate_log', typical=self.duration(estimate.typical),
                                             high=self.duration(estimate.high, up=True),
                                             reference=time_estimates.reference_label())))
        self.estimate_clock = getattr(self, 'estimate_clock', 0) + 1
        self.tick_estimate(self.estimate_clock)

    def job_began(self, index):
        self.job_started[index] = time.monotonic()

    def running_line(self):
        """The line under the batch status: elapsed time against the usual time on the reference PC."""
        started = getattr(self, 'batch_started', None)
        if started is None:
            return ''
        elapsed = time.monotonic() - started
        estimate = getattr(self, 'batch_estimate', None)
        clock = time_estimates.elapsed_text(elapsed)
        if estimate is None or not estimate.games:
            return self.tr('estimate_elapsed', elapsed=clock)
        if elapsed > estimate.high:
            return self.tr('estimate_running_over', elapsed=clock, high=self.duration(estimate.high, up=True),
                           longest=self.duration(estimate.longest, up=True))
        return self.tr('estimate_running', elapsed=clock, typical=self.duration(estimate.typical),
                       high=self.duration(estimate.high, up=True))

    def row_running_text(self, index):
        """A running game's status cell: its own clock and its usual time."""
        row = self.active_rows[index]
        item = self.items.get(row)
        began = getattr(self, 'job_started', {}).get(index)
        if item is None or began is None:
            return self.tr('converting')
        clock = time_estimates.elapsed_text(time.monotonic() - began)
        found = time_estimates.game_time(item.system, self.row_level(item.system))
        if found is None:
            return self.tr('converting_clock', elapsed=clock)
        return self.tr('converting_elapsed', elapsed=clock, typical=self.duration(found.typical))

    def tick_estimate(self, clock=None):
        """Once a second while the batch runs: the status line and the clocks of the running games. A tick of an
        earlier batch's clock (one that ended less than a second before this one started) stops by itself."""
        clock = getattr(self, 'estimate_clock', 0) if clock is None else clock
        if clock != getattr(self, 'estimate_clock', 0):
            return
        if not getattr(self, 'converting', False) or getattr(self, 'batch_started', None) is None:
            self.batch_started = None
            return
        try:
            for index in list(self.running_jobs):
                row = self.active_rows[index]
                if self.row_status.get(row) == 'converting':
                    self.table.set(row, 'status', self.row_running_text(index))
            self.render_status()
            self.app.after(TICK_MS, lambda: self.tick_estimate(clock))
        except tk.TclError:
            self.batch_started = None

    def render_status(self):
        """The status line, with the batch clock under it while a batch runs."""
        text = self.tr(self.status_key, **self.status_values)
        line = self.running_line() if getattr(self, 'batch_started', None) is not None else ''
        self.status.set(text + ('\n' + line if line else ''))

    def stop_estimate_text(self):
        """For the Stop dialog (also reached by closing the window): how long the batch has run and usually runs."""
        started, estimate = getattr(self, 'batch_started', None), getattr(self, 'batch_estimate', None)
        if started is None or estimate is None or not estimate.games:
            return ''
        return self.tr('stop_elapsed', elapsed=time_estimates.elapsed_text(time.monotonic() - started),
                       typical=self.duration(estimate.typical), high=self.duration(estimate.high, up=True),
                       longest=self.duration(estimate.longest, up=True), reference=time_estimates.reference_label())

    # --- the tools window ------------------------------------------------------------------------------------------

    def first_use_note(self):
        """Said where the build tools and shared pieces are offered: the first conversion takes longer, and why."""
        data = time_estimates.table()
        if not data:
            return ''
        seconds, _ = time_estimates.first_use(shared_missing=True, data=data)
        return self.tr('first_use_note', time=self.duration(seconds, up=True), reference=time_estimates.reference_label())
