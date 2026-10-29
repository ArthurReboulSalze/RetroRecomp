"""The 16-bit, Neo Geo and CPS-1 converters give the results they gave before they adopted the shared helpers
(docs/STANDARDS.md rule 7), and the gates they share (`retrorecomp/conversion_gates.py`) decide as they did.

`GOLDEN` (conversion_gates_golden.json) was recorded on the tree before the copies were removed (1.6.3 after P5a, commit
f81a873), by running the `collect_*` functions below through the entry points that stay in place (`console16.probe16`,
`neogeo_state_checks.probe/check`, `neogeo_conversion.check_routes`, `neogeo_persistence_checks.check`,
`cps1_conversion.run/check_states`, `neogeo_build.pinned_dependency/_replace/probe_failure`,
`console16.dependencies16`, `cps1_build._write/_replace_once`) with a fake process, a fake game that answers from the
command line and a fake `git`. The same functions run on the new tree and must record the same values: argv, timeout,
capture options, environment changes, the order of the git commands, the files written, the gate decisions on synthetic
traces and states, exception types and messages. No ROM and no executable is needed.

What the move changes on purpose is not in the golden but asserted on its own: the Neo Geo and CPS-1 probes now run in
the folder they write their evidence to and with no console window on Windows (`ProcessContextTests`).
Regenerate the values only on a tree known to be unchanged: `python tests/test_conversion_gates.py --record`.
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

from retrorecomp.core import ConversionError  # noqa: E402
from retrorecomp import (console16, cps1_build, cps1_conversion, neogeo_build, neogeo_conversion,  # noqa: E402
                         neogeo_persistence_checks, neogeo_state_checks, timings)
from test_conversion_common import fake_phase_factory, flags, outcome, plain  # noqa: E402

GOLDEN_FILE = Path(__file__).with_name('conversion_gates_golden.json')


def scrub(value):
    """Temporary folder names made by `tempfile` differ from run to run."""
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'game-[a-z0-9_]{8}', 'game-<X>', value)
    return value


def option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


class Recorder:
    """Stands in for `core.run_process`: records what is started, answers through `behave(argv, record)`.

    `context=False` leaves out the working folder and the window flag (the Neo Geo and CPS-1 probes gain them on
    purpose; see `ProcessContextTests`)."""

    def __init__(self, behave, context=True):
        self.behave, self.context, self.calls, self.raw = behave, context, [], []

    def __call__(self, args, **kwargs):
        argv = [str(a) for a in args]
        environment = kwargs.get('env')
        changed, removed = {}, []
        if environment is not None:
            changed = {key: value for key, value in environment.items() if os.environ.get(key) != value}
            removed = sorted(key for key in os.environ if key not in environment)
        record = {'args': argv, 'timeout': kwargs.get('timeout'), 'capture_output': kwargs.get('capture_output'),
                  'text': kwargs.get('text'), 'env_changed': changed, 'env_removed': removed,
                  'other': sorted(set(kwargs) - {'cwd', 'timeout', 'capture_output', 'text', 'creationflags', 'env'})}
        self.raw.append({'cwd': kwargs.get('cwd'), 'cwd_existed': Path(kwargs['cwd']).is_dir() if kwargs.get('cwd') else None,
                         'creationflags': flags(kwargs.get('creationflags', 0))})
        if self.context:
            record.update(cwd=kwargs.get('cwd'), cwd_existed=self.raw[-1]['cwd_existed'],
                          creationflags=self.raw[-1]['creationflags'])
        self.calls.append(record)
        return self.behave(argv, record)


class SerialPool:
    """A pool that runs each job when its result is asked for: a failing job stops the later ones, always."""

    def __init__(self, max_workers=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def map(self, function, *iterables):
        return map(function, *iterables)


@contextlib.contextmanager
def fake_process(recorder):
    """`core.run_process` replaced by `recorder`, also in the converters that imported the name before the move,
    and the thread pools replaced by `SerialPool` (the order of the probes is then the order of the code)."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch('retrorecomp.core.run_process', recorder))
        stack.enter_context(patch('concurrent.futures.ThreadPoolExecutor', SerialPool))
        for module in (neogeo_conversion, neogeo_persistence_checks, cps1_conversion):
            if hasattr(module, 'run_process'):
                stack.enter_context(patch.object(module, 'run_process', recorder))
        yield


def csv_rows(path, rows):
    Path(path).write_text('frame,hash\n' + ''.join(f'{i},{value}\n' for i, value in rows), encoding='ascii', newline='')


def timeline(i):
    return (i * 37 + 11) % 251


# ---------------------------------------------------------------- the 16-bit probe

def collect_probe16(root):
    result = {}
    directory = root / 'probe'
    directory.mkdir()
    exe = root / 'game.exe'
    exe.write_bytes(b'authored')
    script, state = root / 'route.txt', root / 'previous.rrstate'
    script.write_text('0 0 0\n', encoding='ascii')
    state.write_bytes(b'state')

    def scenario(label, options, code=0, report=None, frames=None, stale=None, set_env=None):
        def behave(argv, record):
            path = Path(option(argv, '--report'))
            if stale is not None:
                path.write_text(json.dumps(stale), encoding='utf-8')
            elif report is not False:
                path.write_text(json.dumps(report if report is not None else
                                           {'frames': int(option(argv, '--frames')) if frames is None else frames,
                                            'gun_light_hits': 3, 'gun_interrupts': 4, 'gun_trigger_packets': 5}),
                                encoding='utf-8')
            return subprocess.CompletedProcess(argv, code, f'out-{label}\n', f'err-{label}\n')
        recorder, events = Recorder(behave), []
        with patch('retrorecomp.core.run_process', recorder), patch.object(timings, 'phase', fake_phase_factory(events)), \
                patch.dict(os.environ, set_env or {}):
            call = outcome(lambda: console16.probe16(exe, directory, options.pop('frames', 120), **options))
        logs = {path.name: path.read_text(encoding='utf-8') for path in sorted(directory.glob('*.log'))}
        result[label] = {'calls': recorder.calls, 'events': events, 'outcome': call, 'logs': logs}
        for path in directory.glob('*'):
            path.unlink()

    interpreter = {'GENESIS_FORCE_INTERP': '0', 'SNESRECOMP_LLE_BOUNCE': '1', 'RR_SNES_FORCE_INTERP': '0', 'KEEP_ME': 'x'}
    scenario('demo', {}, set_env=interpreter)
    scenario('reference', dict(reference=True), set_env={'KEEP_ME': 'x'})
    scenario('play_script_states', dict(play=True, input_script=script, save_state=root / 'next.rrstate',
                                        load_state=state, scenario='second'), set_env=interpreter)
    scenario('gun_ok', dict(play=True, gun_menu='t2', frames=3000), set_env=interpreter)
    scenario('gun_no_aim', dict(play=True, gun_menu='t2', frames=3000), frames=3000,
             report={'frames': 3000, 'gun_light_hits': 0, 'gun_interrupts': 4, 'gun_trigger_packets': 5})
    scenario('gun_short', dict(play=True, gun_menu='t2', frames=2999),
             report={'frames': 2999, 'gun_light_hits': 0})
    scenario('frames_short', {}, report={'frames': 5})
    scenario('failed', {}, code=3, set_env=interpreter)
    scenario('failed_unreadable_report', {}, code=1, stale=None, report=False)
    scenario('failed_load', dict(load_state=state), code=7)
    scenario('failed_load_without_state', {}, code=7)
    scenario('failed_save', dict(save_state=root / 'next.rrstate'), code=8)
    scenario('failed_other_code_with_save', dict(save_state=root / 'next.rrstate', load_state=state), code=9)
    scenario('coprocessor', {}, code=2, stale={'coprocessor_failed': True, 'cartridge_chip': 'sa1',
                                               'coprocessor_failed_command': 5})
    scenario('coprocessor_defaults', {}, code=2, stale={'coprocessor_failed': True})
    scenario('failed_with_clean_report', {}, code=2, stale={'frames': 1})
    scenario('failed_with_broken_report', {}, code=2, stale=None, report=False)
    (directory / 'play.json').write_text('{broken', encoding='utf-8')

    def broken(argv, record):
        return subprocess.CompletedProcess(argv, 4, 'o', 'e')
    with patch('retrorecomp.core.run_process', Recorder(broken)):
        result['failed_broken_report'] = outcome(lambda: console16.probe16(exe, directory, 120, play=True))
    return plain(result, root)


def collect_console16_checks(root):
    """The budget and scan-level checks of convert16, in their order, and the arguments handed to the batch."""
    from retrorecomp import guns16, megadrive, supernintendo
    result = {}
    rom = SimpleNamespace(crc32=0, path=Path('x.bin'), sha256='0' * 64)
    batch_calls, rows = [], {}

    def convert_batch(items, directory, **kwargs):
        batch_calls.append({'title': items[0].title, 'cover': items[0].cover,
                            'kwargs': {key: value for key, value in kwargs.items() if key != 'emit'},
                            'emit_given': callable(kwargs.get('emit')),
                            'directory': directory})
        row = {'status': 'success', 'executable': str(root / 'game.exe'), 'message': 'ok'}
        row.update(rows.get('row', {}))
        return {'failed': int(row['status'] == 'error'), 'games': [row]}

    def reached(label, row=None, **options):
        batch_calls.clear()
        rows['row'] = row or {}
        arguments = dict(system_id='md', passes=3, frames=3600)
        arguments.update(options)
        with patch.object(console16, 'conversion_rom', lambda *a, **k: rom), \
                patch.object(megadrive, 'profile_for', lambda r: {'title': 'T'}), \
                patch.object(megadrive, 'video_standard', lambda *a: 'ntsc'), \
                patch.object(supernintendo, 'profile_for', lambda r: {'title': 'S'}), \
                patch.object(supernintendo, 'video_standard', lambda *a: 'ntsc'), \
                patch.object(guns16, 'gun_game', lambda *a: None), \
                patch('retrorecomp.batch.convert_batch', convert_batch), \
                patch('retrorecomp.batch.identify', lambda path, system: SimpleNamespace(title=None, cover=None)), \
                patch('retrorecomp.paths.games_root', lambda: root / 'games'):
            result[label] = {'outcome': outcome(lambda: console16.convert16(root / 'x.bin', emit=lambda text: None,
                                                                            **arguments)),
                             'batch': list(batch_calls)}
    for label, options in (('plain', {}), ('no_frames', dict(frames=0)), ('too_many_frames', dict(frames=10001)),
                           ('edge_frames', dict(frames=10000)), ('no_passes', dict(passes=0)),
                           ('too_many_passes', dict(passes=11)), ('edge_passes', dict(passes=10)),
                           ('unknown_level', dict(scan_level='bogus')), ('level', dict(scan_level='extended')),
                           ('legacy_switch', dict(md_advanced_scan=True)), ('snes_legacy_switch',
                                                                            dict(system_id='snes', md_advanced_scan=True)),
                           ('level_beats_switch', dict(scan_level='quick', md_advanced_scan=True)),
                           ('budget_before_level', dict(scan_level='bogus', frames=0)),
                           ('batch_error', dict(row={'status': 'error', 'message': 'Compiler stopped.'})),
                           ('batch_current', dict(row={'status': 'current'})),
                           ('batch_other_status', dict(row={'status': 'skipped', 'message': 'x'})),
                           ('titled', dict(title='My title')), ('covered', dict(cover=root / 'cover.png'))):
        reached(label, **options)
    return plain(result, root)


# ---------------------------------------------------------------- pinned git checkouts

class FakeGit:
    """Stands in for `core.run` on git (and cmake): a few folders that behave like checkouts, every command recorded."""

    def __init__(self, root, **state):
        self.root, self.calls, self.state, self.heads = root, [], state, {}

    def __call__(self, args, *, cwd=None, timeout='default', **kwargs):
        argv = [str(a) for a in args]
        self.calls.append({'args': argv, 'cwd': cwd, 'timeout': timeout, 'other': sorted(kwargs)})
        if argv[0] != 'git':
            return ''
        words, where = argv[1:], cwd
        if words[:1] == ['-C']:
            where, words = words[1], words[2:]
        where = Path(where) if where is not None else None
        verb = words[0]
        if verb == 'clone':
            target = Path(words[-1])
            (target / '.git').mkdir(parents=True)
            if '--no-checkout' not in words:
                (target / 'file.txt').write_text('x', encoding='utf-8')
            self.heads[target] = 'cloned'
        elif verb == 'checkout':
            if not self.state.get('stuck'):
                self.heads[where] = words[-1]
            (where / 'file.txt').write_text('x', encoding='utf-8')
        elif verb == 'status':
            return ' M changed.c\n' if self.state.get('dirty') else ''
        elif verb == 'rev-parse':
            return self.heads.get(where, 'unknown') + '\n'
        return ''


def checkout(root, name, head, populated=True):
    folder = root / '.deps' / name
    (folder / '.git').mkdir(parents=True)
    if populated:
        (folder / 'file.txt').write_text('x', encoding='utf-8')
    return folder


def collect_pinned_dependency(root):
    result = {}
    revision = 'a' * 40
    for label, setup in (('fresh', dict(clone=True)), ('fresh_from_research', dict(clone=True, research=True)),
                         ('at_revision', dict(head=revision)), ('moved', dict(head='b' * 40)),
                         ('dirty', dict(head=revision, dirty=True)), ('moved_and_dirty', dict(head='b' * 40, dirty=True)),
                         ('checkout_does_not_land', dict(clone=True, stuck=True)),
                         ('moved_and_stuck', dict(head='b' * 40, stuck=True))):
        folder = root / label
        (folder / '.deps').mkdir(parents=True)
        fake = FakeGit(folder, dirty=setup.get('dirty', False), stuck=setup.get('stuck', False))
        if setup.get('research'):
            (folder / '.build/neogeo-research-20261013/geolith').mkdir(parents=True)
        if 'head' in setup:
            fake.heads[checkout(folder, 'geolith', setup['head'])] = setup['head']
        with patch('retrorecomp.core.run', fake), patch.object(neogeo_build, 'ROOT', folder):
            call = outcome(lambda: neogeo_build.pinned_dependency('geolith', 'https://example.invalid/geolith.git', revision))
        result[label] = {'outcome': call, 'commands': fake.calls}
    return plain(result, root)


def collect_dependencies16(root):
    result = {}
    revisions = {key: value[1] for key, value in console16.REPOSITORIES.items()}
    for system in ('md', 'snes'):
        directory = console16.REPOSITORIES[system][2]
        for label, setup in (('fresh', {}), ('at_revision', dict(head=revisions[system])),
                             ('moved', dict(head='b' * 40)), ('dirty', dict(head=revisions[system], dirty=True)),
                             ('moved_and_dirty', dict(head='b' * 40, dirty=True)),
                             ('moved_and_stuck', dict(head='b' * 40, stuck=True)),
                             ('empty_clone', dict(head='b' * 40, empty=True)),
                             ('empty_clone_dirty', dict(head=revisions[system], empty=True, dirty=True))):
            folder = root / f'{system}-{label}'
            (folder / 'sdl').mkdir(parents=True)
            (folder / 'sdl' / 'sdl.lib').write_bytes(b'x')
            fake = FakeGit(folder, dirty=setup.get('dirty', False), stuck=setup.get('stuck', False))
            if 'head' in setup:
                fake.heads[checkout(folder, directory, setup['head'], populated=not setup.get('empty'))] = setup['head']
            with patch('retrorecomp.console16.run', fake), patch.object(console16, 'ROOT', folder), \
                    patch('retrorecomp.platforms.require_backend', lambda system_id: None), \
                    patch.object(console16, 'toolchain', lambda: (Path('cmake'), 'Ninja')), \
                    patch.object(console16, 'sdl_install', lambda: folder / 'sdl'), \
                    patch.object(console16, 'sdl_library', lambda: 'sdl.lib'), \
                    patch.object(console16, 'build_executable', lambda build, name: build / (name + '.exe')), \
                    patch.object(console16, 'cmake_target_args', lambda: ['-DTARGET=1']), \
                    patch.object(console16, 'build_jobs', lambda: '4'):
                call = outcome(lambda: tuple(str(part) for part in console16.dependencies16(system, lambda text: None)))
            result[f'{system}-{label}'] = {'outcome': call, 'commands': fake.calls}
    return plain(result, root)


# ---------------------------------------------------------------- Neo Geo

class FakeNeoGeo:
    """A fake Neo Geo executable that answers from its command line like a deterministic machine.

    Flaws (keyword arguments) switch one wrong behaviour on: `diverge` (the restored run differs from the continuous
    one from that frame), `not_loaded`, `accept` (names of the invalid states it accepts), `changes` (a rejection that
    alters the machine), `creates` (a missing-state load that makes the folder), `fail` (report names that exit 3),
    `native_only_fail` (interpreted opcodes in the report)."""

    def __init__(self, **flaws):
        self.flaws, self.states = flaws, {}

    @staticmethod
    def state(frame):
        size = 160 + 153700
        data = bytearray(size)
        data[0:4] = frame.to_bytes(4, 'little')
        data[172:176] = (100000).to_bytes(4, 'little')
        data[180:184] = (2700).to_bytes(4, 'little')
        return bytes(data)

    def __call__(self, argv, record):
        report, trace = Path(option(argv, '--report')), option(argv, '--trace')
        frames, loaded, rejected, offset = int(option(argv, '--frames')), False, False, 0
        stem = report.stem
        if stem in self.flaws.get('fail', ()):
            return subprocess.CompletedProcess(argv, 3, b'', b'boom ' + stem.encode())
        index = 0
        while index < len(argv):
            if argv[index] == '--checkpoint':
                frame, path = int(argv[index + 1]), Path(argv[index + 2])
                path.write_bytes(self.state(frame))
                index += 3
            else:
                index += 1
        source = option(argv, '--load-state')
        if source is not None:
            path = Path(source)
            data = path.read_bytes() if path.is_file() else None
            if data is not None and data == self.state(int.from_bytes(data[:4], 'little')) and path.stem.startswith('frame-'):
                loaded, offset = True, int.from_bytes(data[:4], 'little')
            elif path.stem in self.flaws.get('accept', ()):
                loaded = True
            else:
                rejected = True
                if self.flaws.get('creates') and not path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
        if self.flaws.get('not_loaded') and loaded:
            loaded = False
        interpreted = 5 if self.flaws.get('interpreted') else 0
        body = {'frames': frames, 'state_loaded': loaded, 'load_rejected': rejected,
                'interpreted_68000': interpreted, 'interpreted_z80': 0}
        if trace:
            rows = []
            for i in range(frames):
                value = timeline(offset + i)
                if loaded and offset and 'diverge' in self.flaws and i >= self.flaws['diverge']:
                    value += 1
                if rejected and self.flaws.get('changes') and i == 3:
                    value += 1
                rows.append((offset + i, value))
            csv_rows(trace, rows)
        report.write_text(json.dumps(body), encoding='utf-8')
        return subprocess.CompletedProcess(argv, 0, b'', b'')


def quick_reframe(original, payload):
    """`neogeo_state_checks.reframe` without its byte-by-byte hash (a rewrite of 150 KB per variant is slow)."""
    import zlib
    head = bytearray(original[:160])
    head[20:24] = len(payload).to_bytes(4, 'little')
    head[24:32] = zlib.crc32(payload).to_bytes(8, 'little')
    return head + payload


def collect_ng_state_probe(root):
    result = {}
    output = root / 'state-checks'
    output.mkdir()
    exe = root / 'packed-game.exe'
    script = root / 'play.inputs'
    script.write_text('0 00 00 0 0\n', encoding='ascii')

    def scenario(label, call, **flaws):
        game = FakeNeoGeo(**flaws)
        recorder = Recorder(game, context=False)
        with fake_process(recorder), patch.object(neogeo_state_checks, 'reframe', quick_reframe):
            answer = outcome(lambda: call(exe, output))
        files = sorted(path.name for path in output.rglob('*') if path.is_file())
        details = {}
        for name in ('divergence.json', 'result.json'):
            if (output / name).is_file():
                details[name] = json.loads((output / name).read_text(encoding='utf-8'))
        result[label] = {'calls': recorder.calls, 'outcome': answer, 'files': files, 'details': details}
        for path in sorted(output.rglob('*'), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()

    scenario('probe', lambda e, o: neogeo_state_checks.probe(e, o, 'continuous', 90, script, '--checkpoint', 30,
                                                            o / 'frame-30.rrstate', mode='aes'))
    scenario('probe_plain', lambda e, o: neogeo_state_checks.probe(e, o, 'cold', 60))
    scenario('probe_failure', lambda e, o: neogeo_state_checks.probe(e, o, 'cold', 60), fail=('cold',))
    check = lambda e, o: neogeo_state_checks.check(e, o, warmups=(30, 45), replay=20, input_script=script, workers=1)
    scenario('check', check)
    scenario('check_aes', lambda e, o: neogeo_state_checks.check(e, o, warmups=(30, 45), replay=20, input_script=script,
                                                                workers=1, mode='aes'))
    scenario('check_default_script', lambda e, o: neogeo_state_checks.check(e, o, warmups=(30, 45), replay=20, workers=1))
    scenario('check_diverges', check, diverge=5)
    scenario('check_not_loaded', check, not_loaded=True)
    scenario('check_strict_fallback', lambda e, o: neogeo_state_checks.check(e, o, warmups=(30, 45), replay=20,
                                                                            input_script=script, require_native=True,
                                                                            workers=1), interpreted=True)
    scenario('check_accepts_truncated', check, accept=('truncated',))
    scenario('check_accepts_inner', check, accept=('inner-truncated', 'inner-magic'))
    scenario('check_rejection_changes_machine', check, changes=True)
    scenario('check_missing_state_creates_folder', check, creates=True)
    scenario('check_failing_probe', check, fail=('restored-30',))
    return plain(scrub(result), root)


def route_report(frames, **changes):
    body = {'frames': frames, 'native_68000': 900, 'interpreted_68000': 12, 'native_z80': 400, 'interpreted_z80': 3,
            'nonzero_samples': 700, 'nonuniform_frames': frames, 'cpu_hash': 'c', 'ram_hash': 'r',
            'extended_hardware_hash': 'h', 'z80_hash': 'z', 'image_hash': 'i', 'pcm_hash': 'p'}
    from retrorecomp.neogeo_validation import FIELDS
    for field in FIELDS:
        body.setdefault(field, f'v-{field}')
    body.update(changes)
    return body


def collect_ng_check_routes(root):
    result = {}
    for label, native, reference, code in (
            ('good', {}, {}, 0), ('reference_differs', {}, {'cpu_hash': 'other'}, 0),
            ('no_image', {'nonuniform_frames': 3}, {'nonuniform_frames': 3}, 0),
            ('no_audio', {'nonzero_samples': 0}, {'nonzero_samples': 0}, 0),
            ('total_differs', {'native_68000': 5}, {}, 0), ('exit', {}, {}, 3)):
        folder = root / label
        project = folder / 'project'
        (project / 'native-discovery').mkdir(parents=True)
        exe = folder / 'packed-game.exe'
        exe.write_bytes(b'x')
        from retrorecomp.neogeo_validation import extended_routes
        routes = extended_routes('gururin', None)
        for name, (frames, _) in routes.items():
            (project / 'native-discovery' / (name + '-reference.json')).write_text(
                json.dumps(route_report(frames, **reference)), encoding='utf-8')

        def behave(argv, record, native=native, code=code):
            if code:
                return subprocess.CompletedProcess(argv, code, b'', b'  engine\n stopped  ' + b'x' * 1500)
            frames = int(option(argv, '--frames'))
            Path(option(argv, '--report')).write_text(json.dumps(route_report(frames, **native)), encoding='utf-8')
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        recorder = Recorder(behave, context=False)
        with fake_process(recorder), patch.object(neogeo_conversion, 'aes_available', lambda p: False):
            answer = outcome(lambda: neogeo_conversion.check_routes(exe, project, 'gururin', None, workers=1))
        result[label] = {'calls': recorder.calls, 'outcome': answer,
                         'reports': sorted(path.name for path in (project / 'packed-checks').glob('*.json'))}
    return plain(result, root)


def collect_ng_persistence(root):
    result = {}

    def scenario(label, **flaws):
        folder = root / label
        project = folder / 'project'
        (project / 'native-discovery').mkdir(parents=True)
        (project / 'native-discovery' / 'play.inputs').write_text('0 00 00 0 0\n', encoding='ascii')
        exe = folder / 'packed-game.exe'
        exe.write_bytes(b'exe')
        state = {'saved': flaws.get('saved', True), 'calls': 0}

        def behave(argv, record):
            report, binary = Path(option(argv, '--report')), Path(argv[0])
            label_ = report.stem
            if label_ in flaws.get('fail', ()):
                return subprocess.CompletedProcess(argv, 5, b'', b'')
            memory = {'blocked': flaws.get('blocked', False), 'saved': False, 'loaded': False,
                      'nvram_hash': 'n', 'card_hash': 'c', 'initial_nvram_hash': 'n', 'initial_card_hash': 'c0'}
            body = {'interpreted_68000': 0, 'interpreted_z80': 2, 'persistent_memory': memory}
            if label_ == 'idle' and flaws.get('idle_creates'):
                (binary.parent / 'datas').mkdir()
            if label_ == 'played':
                memory['saved'] = state['saved']
                if state['saved'] or flaws.get('stray'):
                    saves = binary.parent / 'datas/saves'
                    saves.mkdir(parents=True)
                    (saves / 'NeoGeo-key.rrsave').write_bytes(b'\0' * flaws.get('size', 67712))
                    if flaws.get('two'):
                        (saves / 'second.rrsave').write_bytes(b'\0' * 67712)
            if label_ == 'reopened':
                memory['loaded'] = not flaws.get('not_loaded')
                memory['initial_nvram_hash'] = 'n' if not flaws.get('other_hash') else 'zz'
                memory['initial_card_hash'] = 'c'
                if flaws.get('rewrites'):
                    for file in (binary.parent / 'datas/saves').glob('*.rrsave'):
                        file.write_bytes(b'\1' * 67712)
            report.write_text(json.dumps(body), encoding='utf-8')
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        recorder = Recorder(behave, context=False)
        with fake_process(recorder):
            answer = outcome(lambda: neogeo_persistence_checks.check(exe, project, frames=500, mode=flaws.get('mode')))
        files = sorted(path.name for path in (project / ('aes-ordinary-save-checks' if flaws.get('mode') == 'aes'
                                                         else 'ordinary-save-checks')).glob('*.json'))
        result[label] = {'calls': recorder.calls, 'outcome': answer, 'reports': files}
    scenario('saved')
    scenario('saved_aes', mode='aes')
    scenario('nothing_to_save', saved=False)
    scenario('blocked', blocked=True)
    scenario('idle_creates', idle_creates=True)
    scenario('wrong_size', size=100)
    scenario('two_files', two=True)
    scenario('not_reopened', not_loaded=True)
    scenario('other_hash', other_hash=True)
    scenario('rewritten', rewrites=True)
    scenario('unexpected_file', saved=False, stray=True)
    scenario('failed_idle', fail=('idle',))
    scenario('failed_played', fail=('played',))
    return plain(scrub(result), root)


def collect_ng_build_helpers(root):
    result = {}

    class Output:
        def __init__(self, stdout=b'', stderr=b'', returncode=1):
            self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
    for label, answer in (('stderr_bytes', Output(stderr=b'bad  thing\nhappened')), ('stdout_bytes', Output(stdout=b'only out')),
                          ('str', Output(stderr='texte accentué')), ('empty', Output()), ('none', Output(None, None)),
                          ('long', Output(stderr=b'x' * 3000)), ('undecodable', Output(stderr=b'\xff\xfe ok'))):
        error = neogeo_build.probe_failure('packed attract', answer)
        result['failure_' + label] = {'type': type(error).__name__, 'message': str(error)}
    source = 'one two one\nthree'
    for label, call in (('missing', lambda: neogeo_build._replace(source, 'absent', 'x')),
                        ('several_any', lambda: neogeo_build._replace(source, 'one', 'ONE')),
                        ('single_any', lambda: neogeo_build._replace(source, 'three', 'THREE')),
                        ('count_two', lambda: neogeo_build._replace(source, 'one', 'ONE', count=2)),
                        ('count_one_but_two', lambda: neogeo_build._replace(source, 'one', 'ONE', count=1)),
                        ('count_one_but_none', lambda: neogeo_build._replace(source, 'absent', 'x', count=1)),
                        ('long_text', lambda: neogeo_build._replace(source, 'z' * 100, 'x'))):
        result['replace_' + label] = outcome(call)
    return plain(result, root)


# ---------------------------------------------------------------- CPS-1

class FakeCps1:
    """A fake CPS-1 executable: a timeline of rows, quick states, an exit code 4 for a state it cannot load."""

    def __init__(self, **flaws):
        self.flaws = flaws

    def __call__(self, argv, record):
        report, trace = Path(option(argv, '--report', 'none.json')), option(argv, '--trace')
        frames = int(option(argv, '--frames'))
        stem = report.stem
        if stem in self.flaws.get('fail', ()):
            return subprocess.CompletedProcess(argv, 2, self.flaws.get('stdout', ''), self.flaws.get('stderr', ''))
        offset, state = 0, option(argv, '--load-state')
        if state is not None:
            path = Path(state)
            good = path.name == 'quick.rrstate'
            if not good:
                return subprocess.CompletedProcess(argv, 0 if self.flaws.get('accepts') else 4, '', '')
            offset = int.from_bytes(path.read_bytes()[5:9], 'little')
        save = option(argv, '--save-state')
        if save is not None:
            at = int(option(argv, '--save-at'))
            Path(save).write_bytes(b'STATE' + at.to_bytes(4, 'little') + b'\0' * 300)
        if trace:
            rows = []
            for i in range(frames):
                value = timeline(offset + i) + (1 if self.flaws.get('diverge') and state is not None and i == 7 else 0)
                rows.append((offset + i, value))
            csv_rows(trace, rows)
        body = {'frames': self.flaws.get('frames', offset + frames), 'save_failed': bool(self.flaws.get('save_failed'))}
        report.write_text(json.dumps(body), encoding='utf-8')
        return subprocess.CompletedProcess(argv, 0, '', '')


def collect_cps1_runs(root):
    result = {}
    script = root / 'play.inputs'
    script.write_text('0 000 000\n', encoding='ascii')
    exe = root / 'game.exe'

    def scenario(label, call, **flaws):
        folder = root / label
        recorder = Recorder(FakeCps1(**flaws), context=False)
        with fake_process(recorder):
            answer = outcome(lambda: call(folder))
        result[label] = {'calls': recorder.calls, 'outcome': answer,
                         'files': sorted(path.name for path in folder.rglob('*') if path.is_file()) if folder.is_dir() else None}
    run = lambda folder: cps1_conversion.run(exe, folder, 'play', 90, script)
    scenario('run', run)
    scenario('run_extra_and_end', lambda folder: cps1_conversion.run(exe, folder / 'deeper', 'reference', 100, script,
                                                                    '--reference', ends_at=100))
    scenario('run_exit_stderr', run, fail=('play',), stderr='first\nlast line\n')
    scenario('run_exit_stdout', run, fail=('play',), stdout='from stdout\n')
    scenario('run_exit_silent', run, fail=('play',))
    scenario('run_ended_early', run, frames=10)
    scenario('run_end_override_early', lambda folder: cps1_conversion.run(exe, folder, 'load', 90, script, ends_at=50))
    scenario('run_save_failed', run, save_failed=True)

    def states(folder, frames=1800, name='play'):
        folder.mkdir(parents=True, exist_ok=True)
        expected = folder.parent / (folder.name + '-expected.csv')
        csv_rows(expected, [(i, timeline(i)) for i in range(frames)])
        return cps1_conversion.check_states(exe, folder, name, frames, script, expected)
    scenario('states', states)
    scenario('states_short_route', lambda folder: states(folder, 700))
    scenario('states_diverge', states, diverge=True)
    scenario('states_accepts_truncated', states, accepts=True)
    scenario('states_save_fails', states, fail=('save',), stderr='no save')
    scenario('states_load_fails', states, fail=('load',), stdout='no load')
    scenario('states_save_flag', states, save_failed=True)
    return plain(result, root)


def collect_cps1_helpers(root):
    result = {}
    text = 'abc abc def'
    for label, args in (('missing', ('zzz', 'x', 'thing')), ('twice', ('abc', 'x', 'thing')), ('once', ('def', 'x', 'thing'))):
        result['replace_once_' + label] = outcome(lambda args=args: cps1_build._replace_once(text, *args))
    target = root / 'a' / 'b' / 'file.c'
    stages = {}
    cps1_build._write(target, 'int a;\nint b;\n')
    raw = target.read_bytes()
    stages['created'] = {'text': raw.replace(b'\r\n', b'\n').decode(), 'native_newlines': raw == 'int a;\nint b;\n'.replace('\n', os.linesep).encode()}
    os.utime(target, ns=(1_000_000_000, 1_000_000_000))
    cps1_build._write(target, 'int a;\nint b;\n')
    stages['same_text_keeps_time'] = target.stat().st_mtime_ns == 1_000_000_000
    cps1_build._write(target, 'int a;\nint c;\n')
    stages['changed_rewrites'] = {'text': target.read_bytes().replace(b'\r\n', b'\n').decode(),
                                  'time_moved': target.stat().st_mtime_ns != 1_000_000_000}
    cps1_build._write(target, 'café →\n')
    stages['utf8'] = target.read_bytes().replace(b'\r\n', b'\n').decode('utf-8')
    cps1_build._write(root / 'empty.c', '')
    stages['empty_text'] = (root / 'empty.c').read_bytes().decode()
    result['write'] = stages
    return plain(result, root)


# ---------------------------------------------------------------- all of it

COLLECTORS = {'probe16': collect_probe16, 'console16_checks': collect_console16_checks,
              'pinned_dependency': collect_pinned_dependency, 'dependencies16': collect_dependencies16,
              'ng_state_probe': collect_ng_state_probe, 'ng_check_routes': collect_ng_check_routes,
              'ng_persistence': collect_ng_persistence, 'ng_build_helpers': collect_ng_build_helpers,
              'cps1_runs': collect_cps1_runs, 'cps1_helpers': collect_cps1_helpers}


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

    def test_the_16_bit_probe_spawns_and_judges_as_before(self):
        self.check('probe16')

    def test_the_16_bit_budget_and_scan_level_checks_keep_their_order_and_text(self):
        self.check('console16_checks')

    def test_the_pinned_checkout_of_neo_geo_runs_the_same_git_commands(self):
        self.check('pinned_dependency')

    def test_the_pinned_checkout_of_the_16_bit_engines_runs_the_same_git_commands(self):
        self.check('dependencies16')

    def test_the_neo_geo_state_checks_spawn_and_decide_as_before(self):
        self.check('ng_state_probe')

    def test_the_neo_geo_packed_replays_spawn_and_decide_as_before(self):
        self.check('ng_check_routes')

    def test_the_neo_geo_ordinary_save_checks_spawn_and_decide_as_before(self):
        self.check('ng_persistence')

    def test_the_neo_geo_build_helpers_give_the_same_texts(self):
        self.check('ng_build_helpers')

    def test_the_cps1_runs_and_state_checks_spawn_and_decide_as_before(self):
        self.check('cps1_runs')

    def test_the_cps1_build_helpers_give_the_same_results(self):
        self.check('cps1_helpers')


class GateTests(unittest.TestCase):
    """The shared gates on synthetic values (no recording: they are new)."""

    def test_the_gates_raise_the_error_they_are_given_and_only_then(self):
        from retrorecomp import conversion_gates as gates
        gates.require(True, lambda: self.fail('built an error for a passing gate'))
        gates.require_equal([1, 2], [1, 2], lambda: self.fail('built an error for equal rows'))
        with self.assertRaisesRegex(ValueError, 'differ'):
            gates.require_equal([1, 2], [1, 3], lambda: ValueError('differ'))
        with self.assertRaises(ConversionError):
            gates.require(False, lambda: ConversionError('stop'))

    def test_trace_files_are_equal_when_their_bytes_are(self):
        from retrorecomp import conversion_gates as gates
        with tempfile.TemporaryDirectory() as folder:
            one, two, three = (Path(folder) / name for name in ('one.csv', 'two.csv', 'three.csv'))
            one.write_bytes(b'frame,hash\n0,1\n')
            two.write_bytes(b'frame,hash\n0,1\n')
            three.write_bytes(b'frame,hash\n0,2\n')
            gates.require_same_file(one, two, lambda: self.fail('equal files refused'))
            with self.assertRaisesRegex(RuntimeError, 'trace'):
                gates.require_same_file(one, three, lambda: RuntimeError('trace differs'))

    def test_the_first_difference_is_found_where_the_rows_part_or_one_ends(self):
        from retrorecomp.conversion_gates import continuation_difference, first_difference
        self.assertIsNone(first_difference([], []))
        self.assertIsNone(first_difference(['a', 'b'], ['a', 'b']))
        self.assertEqual(first_difference(['a', 'b', 'c'], ['a', 'x', 'c']), 1)
        self.assertEqual(first_difference(['a', 'b'], ['a', 'b', 'c']), 2)
        self.assertEqual(first_difference(['a'], ['b']), 0)
        timeline = [str(i) for i in range(100)]
        self.assertIsNone(continuation_difference(timeline, timeline[40:60], 40, 20))
        self.assertEqual(continuation_difference(timeline, timeline[40:55] + ['x'] + timeline[56:60], 40, 20), 15)
        self.assertEqual(continuation_difference(timeline, timeline[40:59], 40, 20), 19)
        self.assertEqual(continuation_difference(timeline, timeline[40:61], 40, 20), 20)
        self.assertEqual(continuation_difference(timeline, [], 40, 20), 0)

    def test_the_comparison_notice_names_the_delivered_file(self):
        from retrorecomp.conversion_gates import comparison_notice
        self.assertEqual(comparison_notice('Neo Geo', None),
                         'Neo Geo: comparing the compressed executable with the fresh reference.')
        self.assertEqual(comparison_notice('CPS-1', {'notice': 'too big'}),
                         'CPS-1: comparing the unpacked executable with the fresh reference.')

    def test_the_candidate_is_a_copy_that_is_packed_and_the_notice_comes_back(self):
        from retrorecomp import conversion_gates as gates
        for notice in (None, {'notice': 'left as built'}):
            with tempfile.TemporaryDirectory() as folder:
                built, packed = Path(folder) / 'game.exe', Path(folder) / 'packed' / 'candidate.exe'
                packed.parent.mkdir()
                built.write_bytes(b'built')
                seen = []
                said = []

                def compact(path, emit=None):
                    seen.append((path, path.read_bytes(), emit))
                    path.write_bytes(b'packed')
                    return notice
                with patch('retrorecomp.packing.compact_executable', compact):
                    self.assertEqual(gates.pack_candidate(built, packed, said.append), notice)
                self.assertEqual(seen, [(packed, b'built', said.append)])
                self.assertEqual(built.read_bytes(), b'built')
                self.assertEqual(packed.read_bytes(), b'packed')


class PinnedCheckoutTests(unittest.TestCase):
    """The skeleton of the pinned checkouts, with the commands recorded (the consoles' own are in the golden)."""

    def run_case(self, *, present=True, empty=False, head='pin', dirty=False, dirty_first=False, fill=True, refuse=False):
        from retrorecomp.conversion_common import pinned_checkout
        log = []
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder) / 'engine'
            (checkout / '.git').mkdir(parents=True)
            if not empty:
                (checkout / 'file.c').write_text('x', encoding='utf-8')

            def checkout_command(*arguments, **options):
                log.append(arguments[0])
                return {'status': ' M a.c\n' if dirty else '', 'rev-parse': head + '\n'}.get(arguments[0], '')

            def moved(found):
                log.append('moved')
                if refuse:
                    raise ValueError('moved')
            try:
                pinned_checkout(checkout, 'pin', checkout_command, present=present, clone=lambda: log.append('clone'),
                                fill=(lambda: log.append('fill')) if fill else None, moved=moved,
                                dirty=lambda: RuntimeError('edited'), dirty_first=dirty_first)
                result = 'ok'
            except Exception as error:  # noqa: BLE001
                result = type(error).__name__
        return result, log

    def test_a_missing_checkout_is_cloned_first_and_an_empty_one_is_filled(self):
        self.assertEqual(self.run_case(present=False), ('ok', ['clone', 'rev-parse', 'status']))
        self.assertEqual(self.run_case(empty=True), ('ok', ['fill', 'rev-parse', 'status']))
        self.assertEqual(self.run_case(empty=True, fill=False), ('ok', ['rev-parse', 'status']))
        self.assertEqual(self.run_case(), ('ok', ['rev-parse', 'status']))

    def test_the_order_of_the_two_verifications_is_the_one_asked_for(self):
        self.assertEqual(self.run_case(dirty_first=True), ('ok', ['status', 'rev-parse']))
        self.assertEqual(self.run_case(head='other', dirty=True, dirty_first=True), ('RuntimeError', ['status']))
        self.assertEqual(self.run_case(head='other', dirty=True), ('RuntimeError', ['rev-parse', 'moved', 'status']))

    def test_a_checkout_at_another_revision_is_handed_to_the_caller(self):
        self.assertEqual(self.run_case(head='other'), ('ok', ['rev-parse', 'moved', 'status']))
        self.assertEqual(self.run_case(head='other', refuse=True), ('ValueError', ['rev-parse', 'moved']))


class ProcessContextTests(unittest.TestCase):
    """What the move changes on purpose: the probes of Neo Geo and CPS-1 run in the folder they write their evidence to,
    with no console window on Windows (the other values of the call are in the golden)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def test_the_neo_geo_state_probe_runs_in_its_output_folder_without_a_window(self):
        output = self.root / 'state-checks'
        output.mkdir()
        recorder = Recorder(FakeNeoGeo(), context=False)
        with fake_process(recorder):
            neogeo_state_checks.probe(self.root / 'game.exe', output, 'cold', 30)
        self.assertEqual(recorder.raw, [{'cwd': output, 'cwd_existed': True, 'creationflags': 'no_window_if_windows'}])

    def test_the_cps1_runs_run_in_their_folder_without_a_window_and_make_it(self):
        folder = self.root / 'checks' / 'native'
        script = self.root / 'play.inputs'
        script.write_text('0 000 000\n', encoding='ascii')
        recorder = Recorder(FakeCps1(), context=False)
        with fake_process(recorder):
            cps1_conversion.run(self.root / 'game.exe', folder, 'play', 30, script)
        self.assertEqual(recorder.raw, [{'cwd': folder, 'cwd_existed': True, 'creationflags': 'no_window_if_windows'}])

    def test_the_neo_geo_packed_replays_run_in_their_folder_without_a_window(self):
        project = self.root / 'project'
        (project / 'native-discovery').mkdir(parents=True)
        from retrorecomp.neogeo_validation import extended_routes
        for name, (frames, _) in extended_routes('gururin', None).items():
            (project / 'native-discovery' / (name + '-reference.json')).write_text(json.dumps(route_report(frames)),
                                                                                   encoding='utf-8')

        def behave(argv, record):
            Path(option(argv, '--report')).write_text(json.dumps(route_report(int(option(argv, '--frames')))),
                                                      encoding='utf-8')
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        recorder = Recorder(behave, context=False)
        with fake_process(recorder), patch.object(neogeo_conversion, 'aes_available', lambda p: False):
            neogeo_conversion.check_routes(self.root / 'game.exe', project, 'gururin', None, workers=1)
        self.assertEqual({(call['cwd'], call['creationflags']) for call in recorder.raw},
                         {(project / 'packed-checks', 'no_window_if_windows')})
        self.assertEqual(len(recorder.raw), 3)


class AdoptionTests(unittest.TestCase):
    """No console keeps its own copy: the sources name the helper, and the old forms are gone."""

    def source(self, name):
        return (ROOT / 'retrorecomp' / (name + '.py')).read_text(encoding='utf-8')

    def test_the_converters_call_the_shared_helpers(self):
        for module, names in (('console16', ('spawn(', 'check_exit(', 'probe_environment(', 'check_run_budget(',
                                              'resolve_scan_level(', 'convert_single(', 'pinned_checkout(')),
                              ('neogeo_conversion', ('spawn(', 'check_exit(', 'resolve_scan_level(', 'pack_candidate(',
                                                     'comparison_notice(')),
                              ('neogeo_state_checks', ('spawn(', 'check_exit(', 'continuation_difference(', 'require(',
                                                       'require_equal(')),
                              ('neogeo_persistence_checks', ('spawn(', 'check_exit(')),
                              ('neogeo_build', ('spawn(', 'check_exit(', 'pinned_checkout(', 'replace_counted(',
                                                'pack_candidate(')),
                              ('cps1_conversion', ('spawn(', 'check_exit(', 'resolve_scan_level(', 'pack_candidate(',
                                                   'comparison_notice(', 'require_same_file(', 'continuation_difference(')),
                              ('cps1_build', ('replace_counted(', 'write_if_changed('))):
            text = self.source(module)
            for name in names:
                self.assertIn(name, text, f'{module} should call {name}')

    def test_the_old_copies_are_gone(self):
        for module in ('console16', 'neogeo_conversion', 'neogeo_state_checks', 'neogeo_persistence_checks', 'cps1_conversion'):
            text = self.source(module)
            self.assertNotIn('run_process', text, module)
            self.assertNotIn('Unknown scan level', text, module)
        self.assertNotIn('os.environ.copy', self.source('console16'))
        for module in ('neogeo_conversion', 'cps1_conversion', 'neogeo_build'):
            self.assertNotIn('compact_executable', self.source(module))
        self.assertNotIn('write_changed', self.source('cps1_build'))
        self.assertNotIn('text.count(old)', self.source('cps1_build'))
        self.assertNotIn('source.count(old)', self.source('neogeo_build'))
        self.assertNotIn('.read_bytes() !=', self.source('cps1_conversion'))

    def test_the_shared_module_is_owned_by_exactly_the_consoles_that_import_it(self):
        from retrorecomp import compilation_inputs as inputs
        importers = [path.stem for path in (ROOT / 'retrorecomp').glob('*.py')
                     if path.stem != 'conversion_gates' and re.search(r'conversion_gates import|import conversion_gates',
                                                                      path.read_text(encoding='utf-8'))]
        self.assertTrue(importers)
        expected = {system for system in inputs.SYSTEMS for name in importers
                    if 'retrorecomp.' + name in inputs.manifest_names(system)}
        owners = {system for system in inputs.SYSTEMS if 'retrorecomp.conversion_gates' in inputs.manifest_names(system)}
        self.assertEqual(owners, expected, importers)
        self.assertEqual(owners, {'ng', 'cps1', 'x68'})
        common = {system for system in inputs.SYSTEMS
                  if 'retrorecomp.conversion_common' in inputs.manifest_names(system)}
        self.assertEqual(common, {'sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68'})


class AbToolTests(unittest.TestCase):
    """`tools/ab_conversion.py` reads the layouts of the 16-bit, Neo Geo and CPS-1 builds and leaves out what differs
    by construction there (the key of a quick state, the digest of an executable)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def test_the_kept_builds_of_every_console_layout_are_found(self):
        from tools import ab_conversion as ab
        for name in ('sms_game_AAAAAAAA_0123456789ab', 'md-rom-' + 'a' * 64, 'snes-rom-' + 'b' * 16, 'ng-' + 'c' * 20 + '-native',
                     'cps1/1941-0123456789ab', 'megadrive-compiler', 'megadrive-step-decoder', 'cps1-reference'):
            folder = self.root / '.build' / name
            folder.mkdir(parents=True)
            if name.startswith('sms_'):
                (folder / 'rom.sms').write_bytes(b'x')
        found = [path.relative_to(self.root / '.build').as_posix() for path in ab.kept_builds(self.root)]
        self.assertEqual(sorted(found), sorted(['sms_game_AAAAAAAA_0123456789ab', 'md-rom-' + 'a' * 64, 'snes-rom-' + 'b' * 16,
                                                'ng-' + 'c' * 20 + '-native', 'cps1/1941-0123456789ab']))

    def test_a_state_is_compared_without_the_key_of_the_code_that_wrote_it(self):
        from tools import ab_conversion as ab
        normaliser = ab.Normaliser({})
        header = bytes(range(96))
        one, two, three = (self.root / name for name in ('one.rrstate', 'two.rrstate', 'three.rrstate'))
        one.write_bytes(header + b'a' * 64 + b'payload')
        two.write_bytes(header + b'b' * 64 + b'payload')
        three.write_bytes(header + b'a' * 64 + b'payloae')
        self.assertEqual(ab.fingerprint(one, normaliser), ab.fingerprint(two, normaliser))
        self.assertNotEqual(ab.fingerprint(one, normaliser), ab.fingerprint(three, normaliser))

    def test_the_digests_of_executables_a_report_carries_do_not_count(self):
        from tools import ab_conversion as ab
        normaliser = ab.Normaliser({})
        report = lambda stamp: {'packed_candidate_sha256': stamp, 'packed': {'replay': {'candidate_sha256': stamp, 'frames': 3}},
                                'cpu_hash': 'same'}
        self.assertEqual(normaliser.json(report('1')), normaliser.json(report('2')))
        changed = report('1')
        changed['cpu_hash'] = 'other'
        self.assertNotEqual(normaliser.json(report('1')), normaliser.json(changed))
        for name, key in (('native-validation.json', 'native_sha256'), ('native-validation.json', 'packed_sha256')):
            one, two = self.root / 'one' / name, self.root / 'two' / name
            for path, value in ((one, '1'), (two, '2')):
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps({key: value, 'passed': True}), encoding='utf-8')
            self.assertEqual(ab.fingerprint(one, normaliser), ab.fingerprint(two, normaliser))


if __name__ == '__main__':
    unittest.main()
