"""The X68000 converter gives the results it gave before it adopted the shared helpers (docs/STANDARDS.md rule 7).

`GOLDEN` (x68000_common_golden.json) was recorded on the tree before the copies were removed (1.6.3 after P5b, commit
85e21e8), by running the `collect_*` functions below through the entry points that stay in place
(`x68000_conversion.replay`, `run_routes`, `sdk_tree` and `convert`) with a fake process, a fake game that answers from
the command line, and, for `convert`, fake discovery, build and replay steps that write the traces the gates compare.
The same functions run on the new tree and must record the same values: argv, timeout, window flag, files given to the
process, the order of the replays and of the timing phases, the files written, the messages of the conversion, the
decisions of the gates on synthetic traces, exception types and messages. No ROM, no firmware and no executable is needed.

What the move changes on purpose is not in the golden but asserted on its own: the replays now run in the folder they
write their evidence to (`ProcessContextTests`).
Regenerate the values only on a tree known to be unchanged: `python tests/test_x68000_common.py --record`.
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from retrorecomp import timings, x68000_conversion as conversion  # noqa: E402
from test_conversion_common import fake_phase_factory, flags, outcome, plain  # noqa: E402
from tools import x68000_native, x68000_reference  # noqa: E402
from tools.x68000_reference_check import HARDWARE_COLUMNS, TRACE_COLUMNS  # noqa: E402

GOLDEN_FILE = Path(__file__).with_name('x68000_common_golden.json')


def scrub(value):
    """Temporary folder names made by `tempfile` differ from run to run."""
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r'(qa|reference)-[a-z0-9_]{8}', r'\1-<X>', value)
        value = re.sub(r"No such file or directory: '.*'", "No such file or directory: '<path>'", value)
        return re.sub(r'/x68/(win|linux)(-llvm)?/', '/x68/<os>/', value)
    return value


def option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def hex_row(index, value):
    wide = lambda salt: format((value * 2654435761 + salt) % 2 ** 64, '016x')
    narrow = lambda salt: format((value * 40503 + salt) % 2 ** 32, '08x')
    return '\t'.join([str(index), wide(1), wide(2), wide(3), '10', '320', '240',
                      *[narrow(k) for k in range(len(TRACE_COLUMNS) - 7)]])


def valid_trace(frames, flaw=None):
    """A trace `validate_trace` accepts (hardware columns left out), or one flawed on purpose."""
    header = list(TRACE_COLUMNS + (HARDWARE_COLUMNS if flaw == 'hardware_header' else ()))
    if flaw == 'bad_header':
        header[3] = 'other'
    rows = [hex_row(index, (index * 37 + 11) % 251) for index in range(frames)]
    if flaw == 'short':
        rows = rows[:-1]
    if flaw == 'skipped_frame':
        rows[2] = 'x' + rows[2]
    if flaw == 'bad_hash':
        rows[1] = rows[1].replace(rows[1].split('\t')[1], 'zz')
    return '\t'.join(header) + '\n' + ''.join(row + '\n' for row in rows)


class FakeGame:
    """Stands in for `core.run_process`: records what is started, answers like a replay of the X68000 player."""

    def __init__(self, **flaws):
        self.flaws, self.calls, self.raw = flaws, [], []

    def __call__(self, args, **kwargs):
        argv = [str(a) for a in args]
        environment = kwargs.get('env')
        files = {name: getattr(kwargs.get(name), 'name', None) for name in ('stdout', 'stderr')}
        self.calls.append({'args': argv, 'timeout': kwargs.get('timeout'), 'creationflags': flags(kwargs.get('creationflags', 0)),
                           'env_given': environment is not None, 'files': files, 'stdin': kwargs.get('stdin'),
                           'other': sorted(set(kwargs) - {'cwd', 'timeout', 'creationflags', 'env', 'stdout', 'stderr'})})
        self.raw.append({'cwd': kwargs.get('cwd'), 'cwd_existed': Path(kwargs['cwd']).is_dir() if kwargs.get('cwd') else None})
        frames = int(option(argv, '--frames'))
        if self.flaws.get('code'):
            kwargs['stderr'].write(self.flaws.get('stderr', b'engine stopped'))
            return subprocess.CompletedProcess(argv, self.flaws['code'], None, None)
        kwargs['stdout'].write(b'fine\n')
        report = {'frames': frames, 'hardware': {'audio_errors': 0}}
        if self.flaws.get('report') != 'none':
            report.update(self.flaws.get('report', {}))
            Path(option(argv, '--report')).write_text(json.dumps(report), encoding='utf-8')
        Path(option(argv, '--trace')).write_text(valid_trace(frames, self.flaws.get('trace')), encoding='ascii', newline='')
        return subprocess.CompletedProcess(argv, 0, None, None)


class EagerPool:
    """A pool that runs each job when it is submitted and keeps the failure for `result()`: every job runs, in order."""

    def __init__(self, max_workers=None, thread_name_prefix=''):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, function, *args, **kwargs):
        try:
            value, error = function(*args, **kwargs), None
        except Exception as raised:  # noqa: BLE001
            value, error = None, raised

        def result():
            if error is not None:
                raise error
            return value
        return SimpleNamespace(result=result)


@contextlib.contextmanager
def fake_process(game):
    """`core.run_process` replaced by `game`, also in the converter when it still imported the name."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch('retrorecomp.core.run_process', game))
        stack.enter_context(patch('concurrent.futures.ThreadPoolExecutor', EagerPool))
        if hasattr(conversion, 'run_process'):
            stack.enter_context(patch.object(conversion, 'run_process', game))
        yield


# ---------------------------------------------------------------- replay and run_routes

def collect_replay(root):
    result = {}
    binary, events = root / 'player.exe', root / 'inputs.tsv'
    binary.write_bytes(b'authored')
    events.write_text('0 1 key 13 1\n', encoding='ascii')

    def scenario(label, frames=4000, name='run', **options):
        flaws = options.pop('flaws', {})
        game, log = FakeGame(**flaws), []
        folder = root / name
        with fake_process(game), patch.object(timings, 'phase', fake_phase_factory(log)):
            call = outcome(lambda: conversion.replay(binary, folder, frames, events, **options))
        files = {path.name: path.read_text(encoding='utf-8', errors='replace')[:200]
                 for path in sorted(folder.glob('*.log'))}
        result[label] = {'calls': game.calls, 'phases': log, 'outcome': call, 'logs': files,
                         'folder_made': folder.is_dir(), 'written': sorted(path.name for path in folder.iterdir())}
        for path in folder.glob('*'):
            path.unlink()

    scenario('plain')
    scenario('reference_observe', reference=True, observe=True, extra=['--auto-disk'])
    scenario('state_arguments', extra=('--state-save-at', 3200, '--state-load-start', '--state-slot', root / 'quick.rrstate'))
    scenario('short_run_timeout', frames=300)
    scenario('long_run_timeout', frames=36000)
    scenario('nested_folder', name='deep/er/run')
    scenario('failed_process', flaws=dict(code=3, stderr=b'x' * 2500 + b'tail \xff end'))
    scenario('failed_process_without_output', flaws=dict(code=1, stderr=b''))
    scenario('core_error', flaws=dict(report={'core_error': 'boom'}))
    scenario('frames_differ', flaws=dict(report={'frames': 12}))
    scenario('audio_errors', flaws=dict(report={'hardware': {'audio_errors': 2}}))
    scenario('missing_hardware', flaws=dict(report={'hardware': None}))
    scenario('no_report', flaws=dict(report='none'))
    for flaw in ('bad_header', 'hardware_header', 'short', 'skipped_frame', 'bad_hash'):
        scenario('trace_' + flaw, flaws=dict(trace=flaw))
    return plain(scrub(result), root)


def collect_run_routes(root):
    result = {}
    binary, events = root / 'player.exe', root / 'inputs.tsv'
    binary.write_bytes(b'authored')
    events.write_text('0 1 key 13 1\n', encoding='ascii')

    def jobs(*specs):
        return [(binary, root / name, frames, events, options) for name, frames, options in specs]

    def scenario(label, specs, workers, **flaws):
        game, log = FakeGame(**flaws), []
        with fake_process(game), patch.object(timings, 'phase', fake_phase_factory(log)):
            call = outcome(lambda: [item['frames'] for item in conversion.run_routes(jobs(*specs), workers)])
        result[label] = {'calls': [call_['args'][call_['args'].index('--report') + 1] for call_ in game.calls],
                         'frames': [call_['args'][call_['args'].index('--frames') + 1] for call_ in game.calls],
                         'timeouts': [call_['timeout'] for call_ in game.calls],
                         'phases': log, 'outcome': call}

    native = lambda name, frames: (name, frames, dict(observe=True))
    reference = lambda name, frames: (name, frames, dict(reference=True, observe=True, extra=['--auto-disk']))
    scenario('serial_native', [native('a', 4000), native('b', 1000), native('c', 300)], 1)
    scenario('serial_reference', [reference('a', 4000), native('b', 1000)], 1)
    scenario('one_job_many_workers', [native('a', 1000)], 4)
    scenario('parallel_native', [native('a', 4000), native('b', 1000), native('c', 300)], 3)
    scenario('parallel_reference', [native('a', 4000), reference('b', 1000)], 2)
    scenario('no_job', [], 3)
    scenario('failure_stops_the_serial_loop', [native('a', 4000), native('b', 1000), native('c', 300)], 1, code=2)
    scenario('failure_after_all_parallel_jobs_ran', [native('a', 4000), native('b', 1000)], 2, code=2)
    return plain(scrub(result), root)


# ---------------------------------------------------------------- sdk_tree

def collect_sdk_tree(root):
    result = {}
    assets = root / 'assets-root'
    for name, data in (('native/a.c', b'int a;\n'), ('native/deep/b.h', b'#define B 1\n'), ('tools/x68000_one.py', b'ONE = 1\n'),
                       ('tools/other.py', b'OTHER = 1\n'), ('licenses/x.md', b'# licence\n'), ('licenses/y.txt', b'text'),
                       ('LICENSE', b'MIT\n')):
        path = assets / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (assets / 'native/emptydir').mkdir()
    base = root / 'base'

    def listing(folder):
        return {path.relative_to(folder).as_posix(): path.read_bytes().decode('latin-1')
                for path in sorted(folder.rglob('*')) if path.is_file()}

    def tree():
        with patch.object(conversion, 'ASSETS', assets):
            return conversion.sdk_tree(base)

    first = tree()
    result['first'] = {'returned_name': first.name, 'files': listing(first)}
    old = 1_000_000_000
    for path in first.rglob('*'):
        if path.is_file():
            os.utime(path, (old, old))
    tree()
    result['second_leaves_every_file_alone'] = sorted(path.relative_to(first).as_posix() for path in first.rglob('*')
                                                      if path.is_file() and int(path.stat().st_mtime) != old)
    (assets / 'native/a.c').write_bytes(b'int a2;\n')
    (assets / 'tools/x68000_two.py').write_bytes(b'TWO = 2\n')
    tree()
    result['third_rewrites_only_what_changed'] = {
        'rewritten': sorted(path.relative_to(first).as_posix() for path in first.rglob('*')
                            if path.is_file() and int(path.stat().st_mtime) != old),
        'files': listing(first)}
    # A tree that is the checkout itself is used as it is.
    with patch.object(conversion, 'ASSETS', conversion.ROOT):
        result['checkout_is_used_as_is'] = conversion.sdk_tree(base) == conversion.ROOT
    return plain(result, root)


# ---------------------------------------------------------------- convert (checks, gates, order of the work)

def tl(frame):
    return (frame * 37 + 11) % 251


def fake_trace(frames, offset=0, flaws=()):
    """The rows of a fake trace: a header and one row per frame, the value of a frame following the timeline."""
    rows = ['frame\tvalue\tother']
    for frame in range(frames):
        value = tl(offset + frame)
        if frame in dict(flaws):
            value = dict(flaws)[frame]
        rows.append(f'{frame}\t{value}\t{value * 3}')
    return '\n'.join(rows) + '\n'


class Scenario:
    """Everything `convert` needs from the outside, faked; the knobs choose what the fake player does."""

    def __init__(self, root, **knobs):
        self.root, self.knobs, self.log, self.passes, self.builds = root, knobs, [], 0, 0
        self.work_ipl = root / 'iplrom.dat'
        self.work_ipl.write_bytes(bytes(range(256)) * 4)
        self.cgrom = root / 'cgrom.dat'
        self.cgrom.write_bytes(b'font')
        self.disk = root / 'game.dim'
        self.disk.write_bytes(b'disk')
        self.source = SimpleNamespace(title='Fake Game', game_key='k' * 32, sha256='s' * 64, path=self.disk, disks=[self.disk],
                                      metadata=lambda: {'sha256': 's' * 64})
        self.manifest = SimpleNamespace(
            sha256='m' * 64, media=[], firmware=SimpleNamespace(ipl=SimpleNamespace(path=self.work_ipl),
                                                               cgrom=SimpleNamespace(path=self.cgrom)),
            config=SimpleNamespace(ram_bytes=2 * 1024 * 1024), local_record=lambda: {'machine': 'fake'},
            verify_sources=lambda: self.log.append('verify_sources'))
        self.reports, self.saved = [], {}

    # -- the fake replay: writes what the real one writes (trace, observations, state), answers with a report
    def replay(self, binary, folder, frames, events, *, reference=False, observe=False, extra=()):
        extra = [str(item) for item in extra]
        shown = [Path(item).relative_to(self.root).as_posix() if item.startswith(str(self.root)) else item for item in extra]
        folder.mkdir(parents=True, exist_ok=True)
        relative = folder.relative_to(self.root).as_posix()
        kind = 'reference' if reference else 'native'
        self.log.append(f'replay {kind} {relative} frames={frames} events={Path(events).name} observe={observe} '
                        f'extra={shown} binary={Path(binary).name}')
        k = self.knobs
        loading = '--state-load-start' in extra
        saving = option(extra, '--state-save-at')
        name = folder.name
        if saving is not None:
            self.saved['boot' if name == 'boot' else 'main'] = int(saving)
        flaws = ()
        offset = 0
        if loading:
            offset = self.saved['main' if name == 'restart' else 'boot']
            if name == 'restart' and k.get('f9_diverge') is not None:
                flaws = ((k['f9_diverge'], 999),)
            if name == 'boot-restart' and k.get('boot_f9_diverge') is not None:
                flaws = ((k['boot_f9_diverge'], 999),)
        elif not reference and name.startswith('native-') and k.get('native_diverge'):
            flaws = ((7, 999),)
        elif not reference and folder.parent.name.startswith('native-') and k.get('route_diverge'):
            flaws = ((9, 999),)
        elif name == 'boot' and k.get('boot_diverge'):
            flaws = ((5, 999),)
        (folder / 'trace.tsv').write_text(fake_trace(frames, offset, flaws), encoding='ascii', newline='')
        if saving is not None:
            slot = folder / 'datas/games' / ('x68-fake' if name != 'boot' else 'boot-game') / 'quick.rrstate'
            slot.parent.mkdir(parents=True, exist_ok=True)
            slot.write_bytes(b'state')
        report = {'frames': frames, 'hardware': {'audio_errors': 0}, 'nonzero_samples': 0 if k.get('silent') else 5,
                  'nonblack_frames': 3, 'reference_ram': 0, 'reference_ipl': 0, 'native_ram': 100, 'native_ipl': 20,
                  'fps': 55.46, 'automatic_disk_changes': 0, 'media_events': []}
        if not reference and name.startswith('native-'):
            self.passes += 1
            if int(name.split('-')[1]) <= k.get('fallback_passes', 0):
                report.update(reference_ram=4, reference_ipl=1)
        if not reference and folder.parent.name.startswith('native-'):
            report.update(reference_ram=k.get('route_fallback', 0), reference_ipl=0)
        if observe:
            # The reference knows one encoding; a native run brings a new one each time unless it learns nothing.
            pc = 0x2000 if reference or k.get('no_progress') else 0x3000 + 2 * len(self.log)
            variants = [{'pc': pc, 'words': '4e71', 'hits': 1}]
            (folder / 'observations.json').write_text(json.dumps({'schema': 1, 'truncated': False, 'variants': variants}),
                                                      encoding='utf-8')
        return report

    def build_player(self, work, payload_dir, *, emit, machine=(), sdk=None):
        self.builds += 1
        self.log.append(f'build_player {Path(work).name} machine={list(machine)}')
        work.mkdir(parents=True, exist_ok=True)
        exe = work / 'player.exe'
        exe.write_bytes(b'player %d' % self.builds)
        return exe

    def prepare_bundle(self, folder, disks, ipl, cgrom, generic, *, title, ram_mib):
        self.log.append(f'prepare_bundle {Path(folder).name} title={title} ram={ram_mib}')
        folder.mkdir(parents=True, exist_ok=True)
        exe = folder / 'reference.exe'
        exe.write_bytes(b'reference')
        return exe

    def generate(self, folder, rows, deps, receipts=None):
        self.log.append(f'generate {Path(folder).name} rows={len(rows)} receipts={receipts!r}')
        Path(folder).mkdir(parents=True, exist_ok=True)
        return {'files': 3}

    def build(self, folder, deps, sdl, jobs, extra=()):
        self.log.append(f'native.build {Path(folder).name} extra={list(extra)}')
        exe = Path(folder) / 'generic.exe'
        exe.write_bytes(b'generic')
        return exe

    def observations(self, paths, ipl=None):
        count = 0
        for path in paths:
            count += len(json.loads(Path(path).read_text(encoding='utf-8'))['variants'])
        return [(0x2000 + 2 * index, '4e71') for index in range(count)]

    def run(self, **arguments):
        self.emitted = []
        options = dict(x68_ipl=self.work_ipl, x68_cgrom=self.cgrom, x68_ram=2, output=self.root / 'out', scan_level='quick',
                       emit=self.emitted.append)
        options.update(arguments)
        library = self.root / 'library'
        patches = [
            patch.object(conversion, 'ROOT', self.root / 'tree'), patch.object(conversion, 'developer_available',
                                                                               lambda: self.knobs.get('available', True)),
            patch.object(conversion, 'machine', lambda *a, **k: (self.source, self.manifest)),
            patch.object(conversion, 'sdk_stamp', lambda part=None: 'a' * 64),
            patch.object(conversion, 'sdk_tree', lambda base: self.root / 'tree'),
            patch.object(conversion, 'machine_sources', lambda base, emit: ('-DFAKE',)),
            patch.object(conversion, 'payload', lambda *a, **k: {}),
            patch.object(conversion, 'build_player', self.build_player),
            patch.object(conversion, 'replay', self.replay),
            patch.object(conversion, 'write_report', lambda path, report: self.reports.append(report)),
            patch.object(conversion, 'toolchain_description', lambda: {'kind': 'fake'}),
            patch.object(conversion, 'toolchain_suffix', lambda: ''),
            patch.object(conversion, 'target_id', lambda: 'fake-target'),
            patch.object(conversion, 'route_workers', lambda count: self.knobs.get('workers', 1)),
            patch.object(x68000_native, 'generate', self.generate), patch.object(x68000_native, 'build', self.build),
            patch.object(x68000_native, 'observations', self.observations),
            patch.object(x68000_native, 'source_receipts', lambda paths: 'receipt'),
            patch.object(x68000_native, 'ROOT', None), patch.object(x68000_reference, 'ROOT', None),
            patch.object(x68000_native, 'SDK', None, create=True),
            patch.object(x68000_reference, 'prepare_bundle', self.prepare_bundle),
            patch('retrorecomp.feedback.ingest', lambda *a, **k: {'ingested': 0}),
            patch('retrorecomp.feedback.records', lambda *a, **k: []),
            patch('retrorecomp.artwork.prepare_icon', lambda *a, **k: {'embedded': False}),
            patch('concurrent.futures.ThreadPoolExecutor', EagerPool),
            patch.object(timings, 'phase', fake_phase_factory(self.log)),
            patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(library)}),
        ]
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            return outcome(lambda: str(conversion.convert(self.disk, **options)))


def collect_convert(root):
    result = {}
    count = [0]

    def scenario(label, knobs=None, **arguments):
        count[0] += 1
        folder = root / f's{count[0]}'
        folder.mkdir()
        game = Scenario(folder, **(knobs or {}))
        answer = game.run(**arguments)
        report = game.reports[0] if game.reports else None
        library = {path.relative_to(folder / 'library').as_posix(): json.loads(path.read_text(encoding='utf-8'))
                   for path in sorted((folder / 'library').rglob('*.json'))}
        result[label] = {
            'outcome': answer, 'emitted': game.emitted, 'log': game.log, 'builds': game.builds,
            'report': None if report is None else {key: report[key] for key in (
                'scan_level', 'final_checks', 'exploration_checks', 'mouse_controls', 'status', 'system', 'executable',
                'automatic_disk_requests', 'qualification_inputs_sha256', 'native_validation', 'game_states', 'video_model')
                if key in report},
            'library': library}

    scenario('quick_clean')
    scenario('standard_clean_serial', dict(), scan_level='standard')
    scenario('standard_clean_parallel', dict(workers=2), scan_level='standard')
    scenario('default_scan_level', dict(), scan_level=None)
    scenario('extended_clean', dict(), scan_level='extended')
    scenario('thorough_clean', dict(), scan_level='thorough')
    scenario('fallback_then_clean', dict(fallback_passes=1))
    scenario('fallback_twice_then_clean', dict(fallback_passes=2), passes=3)
    scenario('fallback_without_progress', dict(fallback_passes=5, no_progress=True))
    scenario('route_fallback_counts', dict(route_fallback=3), scan_level='standard')
    scenario('passes_zero_is_one', dict(fallback_passes=9, always_new=True), passes=0)
    scenario('passes_many_is_ten', dict(fallback_passes=99, always_new=True), passes=99)
    scenario('passes_as_text', dict(fallback_passes=99, always_new=True), passes='2')
    scenario('frames_small_is_4000', dict(), frames=100)
    scenario('frames_large_is_10000', dict(), frames=99999)
    scenario('frames_as_text', dict(), frames='5000')
    scenario('native_trace_diverges', dict(native_diverge=True))
    scenario('route_trace_diverges', dict(route_diverge=True), scan_level='standard')
    scenario('silent_player', dict(silent=True))
    scenario('f9_continuation_diverges', dict(f9_diverge=17))
    scenario('f9_frame_zero_is_not_compared', dict(f9_diverge=0))
    scenario('f9_first_compared_row_diverges', dict(f9_diverge=1))
    scenario('f9_last_compared_row_diverges', dict(f9_diverge=399))
    scenario('boot_diverges', dict(boot_diverge=True))
    scenario('boot_f9_diverges', dict(boot_f9_diverge=30))
    scenario('boot_f9_frame_zero_is_not_compared', dict(boot_f9_diverge=0))
    scenario('boot_f9_first_compared_row_diverges', dict(boot_f9_diverge=1))
    scenario('boot_f9_last_compared_row_diverges', dict(boot_f9_diverge=39))
    scenario('unknown_scan_level', dict(), scan_level='insane')
    scenario('empty_scan_level_is_standard', dict(), scan_level='')
    scenario('standard_override_refused', dict(), standard_override='pal')
    scenario('standard_override_native_ok', dict(), standard_override='native')
    scenario('scan_level_error_comes_first', dict(), scan_level='insane', standard_override='pal')
    scenario('converter_files_missing', dict(available=False), scan_level='insane')
    scenario('title_with_control_character', dict(), title='bad\ttitle')
    scenario('title_too_long', dict(), title='t' * 161)
    scenario('title_given', dict(), title='Given title')
    scenario('invalid_qualification_inputs', dict(), qualification_events=[(0, 1, 'key', 13, 2)])
    scenario('qualification_inputs_out_of_range', dict(), qualification_events=[(0, 9999, 'key', 13, 1)])
    scenario('qualification_inputs_custom', dict(), qualification_events=[(0, 10, 'key', 13, 1)])
    return plain(scrub(result), root)


COLLECTORS = {name[len('collect_'):]: function for name, function in list(globals().items())
              if name.startswith('collect_') and name != 'collect_all' and callable(function)}


def collect(name):
    with tempfile.TemporaryDirectory() as folder:
        return COLLECTORS[name](Path(folder).resolve())


def collect_all():
    return {name: collect(name) for name in COLLECTORS}


if __name__ == '__main__' and '--record' in sys.argv:
    GOLDEN_FILE.write_text(json.dumps(collect_all(), indent=1, sort_keys=True, ensure_ascii=False) + '\n',
                           encoding='utf-8', newline='\n')
    raise SystemExit(0)


GOLDEN = json.loads(GOLDEN_FILE.read_text(encoding='utf-8')) if GOLDEN_FILE.is_file() else {}


class RecordedBehaviourTests(unittest.TestCase):
    maxDiff = None

    def check(self, name):
        self.assertEqual(collect(name), GOLDEN[name])

    def test_a_replay_spawns_and_judges_as_before(self):
        self.check('replay')

    def test_the_routes_replay_in_the_same_order_and_phases(self):
        self.check('run_routes')

    def test_the_sdk_tree_is_written_and_left_alone_as_before(self):
        self.check('sdk_tree')

    def test_a_conversion_checks_gates_and_works_in_the_same_order(self):
        self.check('convert')


class ProcessContextTests(unittest.TestCase):
    """What the move changes on purpose: a replay runs in the folder it writes its evidence to."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        (self.root / 'player.exe').write_bytes(b'authored')
        (self.root / 'inputs.tsv').write_text('0 1 key 13 1\n', encoding='ascii')

    def test_a_replay_runs_in_its_own_folder_with_no_window(self):
        game = FakeGame()
        folder = self.root / 'one' / 'run'
        with fake_process(game):
            conversion.replay(self.root / 'player.exe', folder, 4000, self.root / 'inputs.tsv')
        self.assertEqual(game.raw, [{'cwd': folder, 'cwd_existed': True}])
        self.assertEqual(game.calls[0]['creationflags'], 'no_window_if_windows')

    def test_every_route_runs_in_its_own_folder(self):
        game = FakeGame()
        names = ('a', 'b', 'c')
        jobs = [(self.root / 'player.exe', self.root / name, 300, self.root / 'inputs.tsv', {}) for name in names]
        with fake_process(game):
            conversion.run_routes(jobs, 3)
        self.assertEqual(sorted(call['cwd'] for call in game.raw), sorted(self.root / name for name in names))


class AdoptionTests(unittest.TestCase):
    """The converter keeps no copy of what the shared helpers do: the sources name the helper, the old forms are gone."""

    def source(self, name):
        return (ROOT / 'retrorecomp' / (name + '.py')).read_text(encoding='utf-8')

    def test_the_converter_calls_the_shared_helpers(self):
        text = self.source('x68000_conversion')
        for name in ('spawn(', 'check_exit(', 'resolve_scan_level(', 'write_if_changed(', 'require_same_file(',
                     'require_equal(', 'require(', 'continuation_difference('):
            self.assertIn(name, text, name)

    def test_the_old_copies_are_gone(self):
        text = self.source('x68000_conversion')
        self.assertNotIn('run_process', text)
        self.assertNotIn('CREATE_NO_WINDOW', text)
        self.assertNotIn('Unknown scan level', text)
        self.assertNotIn('LEVELS', text)
        self.assertNotIn('.read_bytes()!=', text)
        self.assertNotIn("a.split('\t')", text)

    def test_the_budget_stays_a_clamp_not_a_refusal(self):
        # check_run_budget refuses a number out of range; the X68000 has always brought it back into range.
        text = self.source('x68000_conversion')
        self.assertNotIn('check_run_budget', text)
        self.assertIn('max(1,min(int(passes),10))', text)
        self.assertIn('max(4000,min(int(frames),10000))', text)

    def test_the_shared_modules_are_owned_by_the_x68000_too(self):
        from retrorecomp import compilation_inputs as inputs
        for module in ('conversion_common', 'conversion_gates'):
            self.assertIn('retrorecomp.' + module, inputs.manifest_names('x68'))


class ContinuationTests(unittest.TestCase):
    """`continues` on the lines of two traces: the frame number is left out, frame 0 of the resumed run is the load."""

    def lines(self, values, first=0):
        return ['header'] + [f'{first + index}\t{value}\tx' for index, value in enumerate(values)]

    def test_a_resumed_run_that_follows_the_timeline_continues_it(self):
        timeline = self.lines(range(100))
        resumed = self.lines([50, 51, 52, 53, 54])
        self.assertTrue(conversion.continues(timeline, resumed, 50, 5))

    def test_the_first_and_the_last_compared_frames_count_but_the_load_frame_does_not(self):
        timeline = self.lines(range(100))
        for position, expected in ((0, True), (1, False), (4, False)):
            values = [50, 51, 52, 53, 54]
            values[position] = 99
            self.assertEqual(conversion.continues(timeline, self.lines(values), 50, 5), expected, position)

    def test_the_frame_numbers_are_not_compared(self):
        self.assertTrue(conversion.continues(self.lines(range(100)), self.lines([50, 51, 52], first=7), 50, 3))


class AbToolTests(unittest.TestCase):
    """`tools/ab_conversion.py` reads an X68000 workspace and lines up what the stamp and `mkdtemp` name differently."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def workspace(self, tree, stamp, qa):
        base = tree / '.build/x68/win' / stamp
        for relative, text in ((f'{"m" * 16}/qa-{qa}/reference/result.json', '{"frames": 4000}'),
                               (f'{"m" * 16}/native/generated.h', f'/* {tree.as_posix()}/.build/x68/win/{stamp}/qa-{qa} */'),
                               ('discovery/ready.json', '{"sdk": "x"}')):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        (base / 'discovery/build').mkdir()
        (base / 'discovery/build/cache.txt').write_text('skipped', encoding='utf-8')
        return base

    def test_two_workspaces_that_differ_only_by_stamp_folder_and_random_names_are_identical(self):
        from tools import ab_conversion as ab
        one, two = self.root / 'a', self.root / 'b'
        self.workspace(one, '0123456789ab', 'abcd1234')
        self.workspace(two, 'ba9876543210', 'wxyz_987')
        self.assertEqual([path.name for path in ab.kept_builds(one)], ['0123456789ab'])
        side = self.root / 'side'
        side.mkdir()
        gathered = [ab.gather(tree, side, self.root / 'out') for tree in (one, two)]
        self.assertEqual(ab.compare(*gathered), [])
        names = sorted(gathered[0]['projects'])
        self.assertEqual(names, ['x68/win/<stamp>'])
        self.assertIn('discovery/ready.json', gathered[0]['projects'][names[0]])
        self.assertNotIn('discovery/build/cache.txt', gathered[0]['projects'][names[0]])
        self.assertIn(f'{"m" * 16}/qa-<X>/reference/result.json', gathered[0]['projects'][names[0]])

    def test_an_x68000_state_is_compared_without_its_checksum_and_nothing_else_of_the_payload(self):
        from tools import ab_conversion as ab
        normaliser = ab.Normaliser({})
        size = 17186640 + 4096
        base = bytearray(b'RRX68KS1' + bytes(size - 8))
        paths = []
        # The window of the OPM section that carried heap garbage before 1.6.3 is compared like the rest of the payload.
        for name, changes in (('one', {}), ('two', {164: 9}), ('other', {17184896 + 100: 7}), ('key', {100: 5})):
            data = bytearray(base)
            for position, value in changes.items():
                data[position] = value
            path = self.root / (name + '.rrstate')
            path.write_bytes(bytes(data))
            paths.append(ab.fingerprint(path, normaliser))
        one, two, other, key = paths
        self.assertEqual(one, two)
        self.assertNotEqual(one, other)
        self.assertEqual(one, key)   # bytes 96 to 160 are the key of the code that wrote it: masked as for every console

    def test_the_digest_of_a_reference_module_and_the_sdk_stamp_of_a_discovery_build_do_not_count(self):
        from tools import ab_conversion as ab
        normaliser = ab.Normaliser({})
        prints = []
        for name, key, value in (('reference-build.json', 'module_sha256', '1'), ('reference-build.json', 'module_sha256', '2'),
                                 ('ready.json', 'sdk', '1'), ('ready.json', 'sdk', '2'),
                                 ('reference-build.json', 'source_identity', '1'), ('reference-build.json', 'source_identity', '2')):
            path = self.root / (key + value) / name
            path.parent.mkdir()
            path.write_text(json.dumps({key: value, 'stage': 'x'}), encoding='utf-8')
            prints.append(ab.fingerprint(path, normaliser))
        self.assertEqual(prints[0], prints[1])
        self.assertEqual(prints[2], prints[3])
        self.assertNotEqual(prints[4], prints[5])

    def test_a_real_difference_in_a_file_is_still_found(self):
        from tools import ab_conversion as ab
        one, two = self.root / 'a', self.root / 'b'
        self.workspace(one, '0123456789ab', 'abcd1234')
        base_two = self.workspace(two, 'ba9876543210', 'wxyz_987')
        (base_two / 'discovery/ready.json').write_text('{"executable": "y"}', encoding='utf-8')
        side = self.root / 'side'
        side.mkdir()
        problems = ab.compare(*(ab.gather(tree, side, self.root / 'out') for tree in (one, two)))
        self.assertEqual(problems, ['x68/win/<stamp>: differs: discovery/ready.json'])


if __name__ == '__main__':
    unittest.main()
