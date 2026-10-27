"""Small local batch checkpoints, recovered explicitly through Convert.

ROMs and executables are never copied here. The definition is written once;
completed row numbers are checkpointed separately. An OS lock distinguishes
an interrupted run from another converter instance still doing useful work.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import uuid

from .library import atomic_json
from .platforms import target_id

MAX_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 8192


def _read(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Batch recovery file exceeds its size limit.')
    return json.loads(raw)


def _lock(path):
    stream = path.open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close();raise
    return stream


class BatchJournal:
    def __init__(self, path, stream, definition, done=None):
        self.path,self.stream,self.definition=path,stream,definition
        self.done=dict(done or {})

    @classmethod
    def create(cls, directory, items, output):
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ValueError('Batch recovery supports 1–8192 rows.')
        directory.mkdir(parents=True,exist_ok=True)
        rows=[]
        for item in items:
            row=asdict(item)
            row.update(path=str(item.path),cover=str(item.cover) if item.cover else None)
            rows.append(row)
        definition={'schema':1,'target':target_id(),'output':str(output.resolve()),'items':rows}
        if len(json.dumps(definition).encode('utf-8')) > MAX_BYTES:
            raise ValueError('Batch recovery file exceeds its size limit.')
        path=directory/(uuid.uuid4().hex+'.json');stream=_lock(path.with_suffix('.lock'))
        try:
            atomic_json(path,definition)
            journal=cls(path,stream,definition);journal.save(False);return journal
        except BaseException:
            stream.close();raise

    @property
    def progress(self):
        return self.path.with_suffix('.progress.json')

    def save(self, finished):
        atomic_json(self.progress,{'schema':1,'finished':bool(finished),'done':self.done})

    def result(self, index, value):
        if type(index) is not int or not 0 <= index < len(self.definition['items']):
            raise ValueError('Invalid batch recovery row.')
        self.done[str(index)]=value['status'];self.save(False)

    def finish(self, record):
        try:self.save(record.get('pending',0)==0)
        finally:self.close()

    def discard(self):
        try:self.save(True)
        finally:self.close()

    def close(self):
        if self.stream is not None:
            self.stream.close();self.stream=None

    def pending_items(self):
        from .batch import BatchItem
        result=[]
        for index,row in enumerate(self.definition['items']):
            if str(index) in self.done:continue
            values={**row,'path':Path(row['path']),'cover':Path(row['cover']) if row['cover'] else None}
            result.append(BatchItem(**values))
        return result


def recover(directory):
    """Reserve the newest interrupted queue; never open or identify a ROM."""
    try:
        candidates=[p for p in directory.glob('*.json') if not p.name.endswith('.progress.json')]
        if not candidates:return None
        candidates.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
    except OSError:
        return None
    for path in candidates:
        journal=_recover_path(path)
        if journal is not None:return journal
    return None


def _recover_path(path):
    stream=None
    try:
        stream=_lock(path.with_suffix('.lock'))
        definition=_read(path);checkpoint=_read(path.with_suffix('.progress.json'))
        if (definition['schema']!=1 or definition['target']!=target_id()
                or checkpoint['schema']!=1 or type(checkpoint['finished']) is not bool
                or checkpoint['finished'] or not Path(definition['output']).is_absolute()
                or not isinstance(definition['items'],list) or not 1<=len(definition['items'])<=MAX_ITEMS
                or not isinstance(checkpoint['done'],dict)):
            stream.close();return None
        from .batch import BatchItem
        from .systems import system_ids
        fields=set(BatchItem.__dataclass_fields__)
        consoles=('',)+system_ids()
        for row in definition['items']:
            if (not isinstance(row,dict) or set(row)!=fields or not isinstance(row['path'],str)
                    or not Path(row['path']).is_absolute()
                    or not isinstance(row['title'],str) or not isinstance(row['system'],str)
                    or row['system'] not in consoles
                    or not isinstance(row['sha256'],str)
                    or row['sha256'] and not re.fullmatch('[0-9a-f]{64}',row['sha256'])
                    or row['cover'] is not None and not isinstance(row['cover'],str)):
                raise ValueError('Invalid batch recovery item.')
        for index,status in checkpoint['done'].items():
            if (not isinstance(index,str) or not index.isdecimal() or not 0<=int(index)<len(definition['items'])
                    or not isinstance(status,str)):
                raise ValueError('Invalid batch recovery checkpoint.')
        journal=BatchJournal(path,stream,definition,checkpoint['done'])
        if not journal.pending_items():journal.close();return None
        return journal
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        if stream is not None:stream.close()
        return None


# ---------------------------------------------------------------------------
# Concurrent conversions per console.
#
# The shared value (Options > General) stays the default and the overall cap;
# a console may lower it. batch.convert_batch takes one number of workers for
# the whole queue and is a game-side module, so a queue that mixes consoles with
# different numbers is cut into groups, each run by one convert_batch with its
# own number. Groups never run more games together than the shared value.
# ---------------------------------------------------------------------------

MAX_JOBS = 8


def normalize_console_jobs(raw):
    """The well-formed entries of the saved per-console numbers: 1-8, known consoles."""
    from .scan_levels import CONSOLES
    if not isinstance(raw, dict):
        return {}
    return {console: value for console, value in raw.items() if console in CONSOLES
            and type(value) is int and 1 <= value <= MAX_JOBS}


def console_jobs(shared, per_console, console):
    """Games of one console converted at once: its own number, never above the shared one."""
    return min(per_console.get(console, shared), shared)


class JobGroup:
    """Rows of the queue converted together, with the workers they get."""

    def __init__(self, console, rows, jobs):
        self.console, self.rows, self.jobs = console, rows, jobs

    @property
    def need(self):
        # Workers that can really be busy at once; what the shared cap counts.
        return min(self.jobs, len(self.rows))


def job_groups(items, shared, per_console):
    """Cut the queue into groups, in the order each first appears.

    A console whose number is below the shared one has a group of its own;
    every other row, whatever its console, stays in one group with the shared
    number: with nothing set, the queue is a single group, as before.
    """
    own = {console for console, value in per_console.items() if min(value, shared) < shared}
    groups = {}
    for index, item in enumerate(items):
        groups.setdefault(item.system if item.system in own else '', []).append(index)
    return [JobGroup(console, rows, console_jobs(shared, per_console, console) if console else shared)
            for console, rows in groups.items()]


class GroupCancel:
    """The queue's cancel event as one group sees it.

    convert_batch clears the process-wide Stop flag when it starts. A group that
    starts just after "Stop now" would clear it for the games already running, so
    a group that sees the cancel raises that flag again when Stop now was chosen.
    """

    def __init__(self, cancel, now=None):
        self.cancel, self.now = cancel, now

    def is_set(self):
        if not self.cancel.is_set():
            return False
        if self.now is not None and self.now.is_set():
            from .core import stop_processes, stop_requested
            if not stop_requested():
                stop_processes()
        return True


def merge_records(items, results, groups, records, shared, elapsed, output):
    """One summary for the queue, from the groups' own summaries and the results by row."""
    from . import __version__
    from datetime import datetime, timezone
    games = [result for result in results if result is not None]
    total = lambda key: sum(record.get(key, 0) for record in records)
    stopped = total('stopped')
    return {"tool": "Retro-Recomp", "version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(), "output": str(output),
            "requested": len(items), "jobs": shared,
            "cancelled": len(records) < len(groups) or any(record.get('cancelled') for record in records),
            # Rows of a group that never started, or killed by Stop, were not converted.
            "pending": len(items) - len(games) + stopped, "stopped": stopped,
            "succeeded": total('succeeded'), "failed": total('failed'),
            "unrecognized": total('unrecognized'), "skipped": total('skipped'),
            "duplicates": total('duplicates'), "games": games,
            "existing": total('existing'), "current": total('current'),
            "pending_installations": total('pending_installations'),
            "elapsed_seconds": round(elapsed, 3)}


def convert_in_groups(items, output, *, jobs, per_console=None, cancel=None, stop_now=None,
                      on_event=lambda kind, index, value: None, emit=print, convert=None, **options):
    """convert_batch for a queue whose consoles may have their own number of workers.

    With no console below the shared value this is one convert_batch call, as
    before. Otherwise each group runs its own, together while their workers fit
    in `jobs` (a group waits for room; the first that fits starts), with events
    by row of the whole queue, one cancel and one summary.
    """
    if convert is None:
        from .batch import convert_batch as convert
    plan = job_groups(items, jobs, per_console or {})
    if len(plan) <= 1:
        return convert(items, output, cancel=cancel, on_event=on_event, emit=emit,
                       jobs=plan[0].jobs if plan else jobs, **options)
    import time
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    from threading import Event, Lock
    started = time.perf_counter()
    cancel = cancel if cancel is not None else Event()
    results, records, lock = [None] * len(items), [], Lock()

    def run(group):
        def forward(kind, local, value):
            # The handler was written for one scheduler thread: one at a time.
            with lock:
                row = group.rows[local]
                if kind == 'result':
                    results[row] = value
                on_event(kind, row, value)
        return convert([items[row] for row in group.rows], output, cancel=GroupCancel(cancel, stop_now),
                       on_event=forward, emit=emit, jobs=group.jobs, **options)

    waiting, running, load, failure = list(plan), {}, 0, None
    with ThreadPoolExecutor(max_workers=len(plan), thread_name_prefix='retro-recomp-group') as pool:
        while waiting or running:
            if failure is None and not cancel.is_set():
                for group in list(waiting):
                    if load + group.need <= jobs:
                        waiting.remove(group)
                        load += group.need
                        running[pool.submit(run, group)] = group
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in sorted(finished, key=lambda value: running[value].rows[0]):
                load -= running.pop(future).need
                try:
                    records.append(future.result())
                except Exception as exc:
                    failure = failure or exc
    if failure is not None:
        raise failure
    record = merge_records(items, results, plan, records, jobs, time.perf_counter() - started,
                           Path(output).resolve())
    directory = Path(output).resolve() / "datas"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "Retro-Recomp-batch.json", record)
    return record


def run_limited(entries, console, jobs, per_console, work, finished):
    """Run work(entry) with at most `jobs` at once and `per_console` of one console.

    Entries start in order, each when its console has a free place. finished(entry,
    future) is called here as each one ends. (Reconvert from the collection.)
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    waiting, running, busy = list(entries), {}, {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while waiting or running:
            for entry in list(waiting):
                if len(running) >= jobs:
                    break
                kind = console(entry)
                if busy.get(kind, 0) < console_jobs(jobs, per_console, kind):
                    waiting.remove(entry)
                    busy[kind] = busy.get(kind, 0) + 1
                    running[pool.submit(work, entry)] = entry
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                entry = running.pop(future)
                busy[console(entry)] -= 1
                finished(entry, future)
