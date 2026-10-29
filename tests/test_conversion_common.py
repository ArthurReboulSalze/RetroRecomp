"""The shared conversion helpers give the results the per-console copies gave (docs/STANDARDS.md rule 7).

`GOLDEN` was recorded on the tree before the helpers existed (v1.6.2 plus main, commit acf3d0e), by running the
`collect_*` functions below through the entry points that stay in place (`core.probe`, `gameboy._probe`,
`nes._run_probe`, `core.convert`, `convert_game_boy`, `convert_nes`, `core.replace_once`, ...) with a fake process
and a fake `convert_batch`. The same functions run on the new tree and must record the same values: argv, working
folder, environment changes, timeout, window flag, phase order, the keyword arguments handed to `convert_batch`,
exception types and messages (the French message of `core.py` included). No ROM and no executable is needed.
Regenerate the values only on a tree known to be unchanged: `python tests/test_conversion_common.py --record`.
"""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrorecomp import core, gameboy, nes, nes_codegen, timings  # noqa: E402
from retrorecomp.artwork import ArtworkError  # noqa: E402
from retrorecomp.systems import MASTER_SYSTEM  # noqa: E402

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
GOLDEN_FILE = Path(__file__).with_name('conversion_common_golden.json')


def plain(value, root):
    """JSON-friendly, with the temporary folder replaced and paths in forward slashes."""
    if isinstance(value, dict):
        return {str(key): plain(item, root) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item, root) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        for base, token in ((root, '<T>'), (ROOT, '<R>')):
            for form in (str(base), str(base).replace('\\', '/'), str(base.resolve()), str(base.resolve()).replace('\\', '/')):
                value = value.replace(form, token)
        return value.replace('\\', '/')
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return value


def flags(value):
    return 'no_window_if_windows' if (value == NO_WINDOW and (value or os.name != 'nt')) else value


def outcome(call):
    try:
        return {'returned': call()}
    except Exception as error:  # noqa: BLE001 - the type and the text are what is recorded
        return {'raised': type(error).__name__, 'message': str(error)}


# ---------------------------------------------------------------- the spawn layer of the probes

class FakeProcess:
    """Stands in for subprocess.Popen: records what is started, answers like a finished game."""
    calls: list = []
    events: list = []
    returncode_value = 0

    def __init__(self, args, **kwargs):
        self.args = args
        self.returncode = type(self).returncode_value
        environment = kwargs.get('env')
        changed, removed = {}, []
        if environment is not None:
            changed = {key: value for key, value in environment.items() if os.environ.get(key) != value}
            removed = sorted(key for key in os.environ if key not in environment)
        self.record = {'args': [str(a) for a in args], 'cwd': kwargs.get('cwd'),
                       'cwd_existed': Path(kwargs['cwd']).is_dir() if kwargs.get('cwd') else None,
                       'stdout': kwargs.get('stdout'), 'stderr': kwargs.get('stderr'),
                       'creationflags': flags(kwargs.get('creationflags', 0)),
                       'env_changed': changed, 'env_removed': removed,
                       'other': sorted(set(kwargs) - {'cwd', 'stdout', 'stderr', 'creationflags', 'env'})}
        type(self).calls.append(self.record)
        type(self).events.append('popen')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, input=None, timeout=None):
        self.record['timeout'] = timeout
        self.record['input'] = input
        argv = [str(a) for a in self.args]
        if '--log' in argv:
            Path(argv[argv.index('--log') + 1]).write_text(
                'stopped after 120 frames; dispatch misses: 2\n7.5% interp / 92.5% static\n', encoding='utf-8')
        return b'', b''

    def poll(self):
        return self.returncode

    def kill(self):
        pass

    def wait(self, timeout=None):
        return self.returncode


def fake_phase_factory(events):
    @contextlib.contextmanager
    def phase(name):
        events.append('enter ' + str(name))
        try:
            yield
        finally:
            events.append('exit ' + str(name))
    return phase


def collect_sms_probe(root):
    result = {}
    with patch.dict(os.environ, {'SMSRECOMP_STRICT': '1'}):
        for label, options in (('plain', {}),
                               ('full', dict(strict=True, press=['A', 'START'], reference=True))):
            FakeProcess.calls, FakeProcess.events = [], []
            directory = root / ('probe-' + label)
            with patch('subprocess.Popen', FakeProcess), patch.object(timings, 'phase', fake_phase_factory(FakeProcess.events)):
                report = core.probe(root / 'game.exe', directory, 600, **options)
            report.pop('wall_seconds')
            result[label] = {'calls': FakeProcess.calls, 'events': FakeProcess.events, 'report': report,
                             'result_json': {key: value for key, value in json.loads((directory / 'result.json').read_text(encoding='utf-8')).items()
                                             if key != 'wall_seconds'},
                             'directory_exists': directory.is_dir()}
    return plain(result, root)


class FakeRun:
    """Stands in for core.run_process (what core.run calls), for the Game Boy and NES probes."""

    def __init__(self, stdout='', returncode=0):
        self.stdout, self.returncode, self.calls = stdout, returncode, []

    def __call__(self, args, **kwargs):
        command = [str(a) for a in args]
        self.calls.append({'args': command, 'cwd': kwargs.get('cwd'), 'timeout': kwargs.get('timeout'),
                           'stdout': kwargs.get('stdout'), 'stderr': kwargs.get('stderr'),
                           'creationflags': flags(kwargs.get('creationflags', 0)),
                           'other': sorted(set(kwargs) - {'cwd', 'timeout', 'stdout', 'stderr', 'creationflags'}),
                           'executable_existed': Path(command[0]).is_file()})
        if '--hash-out' in command:
            Path(command[command.index('--hash-out') + 1]).write_text('0\n' * 30, encoding='ascii')
        if '--wav-out' in command:
            with wave.open(str(command[command.index('--wav-out') + 1]), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b'\x01\x00' * 64)
        return subprocess.CompletedProcess(command, self.returncode, self.stdout)


def collect_run_probes(root):
    result = {}
    work = root / 'work'
    work.mkdir()
    exe = root / 'game.exe'
    exe.write_bytes(b'authored')
    trace = work / 'entries.trace'
    gb_output = ('[LIMIT] Reached frame limit 30\n'
                 '[RR-RAM] ram_stub_instructions=0 ram_stub_cycles=0 ram_single_step_instructions=0 ram_single_step_cycles=0 '
                 'highmem_stub_instructions=0 highmem_stub_cycles=0\n'
                 '[INTERP] Fallback inventory: sites=0 dropped=0 complete=yes\n'
                 '[INTERP] No interpreter fallback recorded.\n')
    runner = FakeRun(gb_output)
    with patch('retrorecomp.core.run_process', runner):
        result['gb_probe'] = {'report': gameboy._probe(exe, work, 30, trace), 'calls': runner.calls}
    runner = FakeRun(gb_output)
    script = ProbeScript('play_r', root / 'play.inputs')
    with patch('retrorecomp.core.run_process', runner):
        result['gb_probe_script'] = {'report': gameboy._probe(exe, work, 30, trace, script), 'calls': runner.calls}
    runner = FakeRun('[DIFF] Matched generated and interpreter execution for 30 steps / 30 frames\n')
    with patch('retrorecomp.core.run_process', runner):
        result['gb_cpu_compare'] = {'returned': gameboy._cpu_compare(exe, work, 30, script), 'calls': runner.calls}
    runner = FakeRun('anything', returncode=3)
    with patch('retrorecomp.core.run_process', runner):
        result['gb_probe_exit'] = {'outcome': outcome(lambda: gameboy._probe(exe, work, 30, trace)), 'calls': runner.calls}
    result['gb_validation_log'] = (work / 'validation.log').read_text(encoding='utf-8')
    nes_output = 'mode=native frames=30 cycles=1000 native_cycles=900\ninterpreted: ROM 50 and RAM 20\n$2000-$7FFF 10\n'
    for label, differential in (('nes_probe', False), ('nes_probe_differential', True)):
        runner = FakeRun(nes_output)
        with patch('retrorecomp.core.run_process', runner):
            report = nes._probe(exe, work, 'boot', 30, work / 'seed.trace', root / 'play.inputs', differential=differential)
        result[label] = {'report': report, 'calls': runner.calls}
    runner = FakeRun(nes_output)
    with patch('retrorecomp.core.run_process', runner):
        result['nes_run_probe'] = {'returned': nes._run_probe([exe, '--frames', '30'], work), 'calls': runner.calls}
    runner = FakeRun('x', returncode=5)
    with patch('retrorecomp.core.run_process', runner):
        result['nes_run_probe_exit'] = {'outcome': outcome(lambda: nes._run_probe([exe, '--frames', '30'], work)),
                                        'calls': runner.calls}
    result['nes_validation_log'] = (work / 'validation.log').read_text(encoding='utf-8')
    text = json.dumps(plain(result, root))
    # The private copy of the executable lives in a random folder.
    import re
    text = re.sub(r'nes-probe-[A-Za-z0-9_]+', 'nes-probe-X', text)
    return json.loads(text)


class ProbeScript:
    def __init__(self, name, input_script):
        self.name, self.input_script = name, input_script


# ---------------------------------------------------------------- single-ROM delegation, checks, messages

SENTINEL = object()


def collect_single_rom(root):
    from retrorecomp import batch
    from retrorecomp.paths import games_root
    result = {}

    def emit(text):
        pass

    def make(status, seen):
        def identify(path, *rest):
            item = SimpleNamespace(path=path, title='Identified', cover=SENTINEL, system='x')
            seen['identify'] = {'path': path, 'rest': list(rest)}
            return item

        def convert_batch(items, output, **kwargs):
            seen['batch'] = {'items': [{'title': i.title, 'cover': i.cover} for i in items],
                             'root_is_games_root': output == games_root(),
                             'emit_passed': kwargs.get('emit') is emit,
                             'kwargs': {k: v for k, v in kwargs.items() if k != 'emit'}}
            return {'failed': int(status == 'error'),
                    'games': [{'status': status, 'message': 'the message', 'executable': 'Game.exe'}]}
        return identify, convert_batch

    common = dict(passes=2, frames=5, backend='banked', language='fr', cover=Path('cover.png'),
                  boxart_dir=Path('art'), online_cover=False, use_cover=False, icon_tags=False)
    consoles = {
        'sms': (lambda **kw: core.convert(Path('Game.sms'), **kw), dict(standard_override='ntsc', scan_level='extended')),
        'sms_default_level': (lambda **kw: core.convert(Path('Game.sms'), **kw), dict(standard_override=None)),
        'gb': (lambda **kw: gameboy.convert_game_boy(Path('Game.gb'), **kw),
               dict(standard_override='dmg', scan_level='extended', gb_deep_validation=False)),
        'nes': (lambda **kw: nes.convert_nes(Path('Game.nes'), **kw),
                dict(standard_override='pal', scan_level='thorough')),
    }
    for name, (call, extra) in consoles.items():
        for status in ('success', 'current', 'existing', 'error', 'stopped'):
            for title in ('Custom title', None):
                seen = {}
                identify, convert_batch = make(status, seen)
                with patch('retrorecomp.batch.identify', identify), patch('retrorecomp.batch.convert_batch', convert_batch), \
                     patch('retrorecomp.core.profile_for_path', lambda path, selected=None: MASTER_SYSTEM):
                    arguments = {**common, **extra, 'title': title, 'emit': emit}
                    answer = outcome(lambda: str(call(**arguments)))
                result[f'{name}/{status}/{title}'] = plain({'outcome': answer, **seen}, root)
    return result


def collect_checks(root):
    """Order and text of the scan-level, backend and passes/frames checks (no ROM is read before them)."""
    result = {}
    output = root / 'out'
    cases = {'bad_level': dict(scan_level='bogus'), 'bad_passes': dict(passes=0), 'bad_passes_high': dict(passes=11),
             'bad_frames': dict(frames=0), 'bad_frames_high': dict(frames=10001),
             'level_and_passes': dict(scan_level='bogus', passes=0), 'good_edge': dict(passes=10, frames=10000)}
    runners = {'sms': lambda **kw: core.convert(root / 'Game.sms', **kw),
               'gb': lambda **kw: gameboy.convert_game_boy(root / 'Game.gb', **kw),
               'nes': lambda **kw: nes.convert_nes(root / 'Game.nes', **kw)}
    with patch('retrorecomp.core.profile_for_path', lambda path, selected=None: MASTER_SYSTEM):
        for name, run_it in runners.items():
            for case, options in cases.items():
                for destination in (None, output):
                    seen = []
                    def convert_batch(items, directory, **kwargs):
                        seen.append(kwargs.get('scan_level'))
                        return {'failed': 1, 'games': [{'status': 'error', 'message': 'delegated'}]}
                    with patch('retrorecomp.batch.identify', lambda path, *rest: SimpleNamespace(title='t', cover=None)), \
                         patch('retrorecomp.batch.convert_batch', convert_batch):
                        # A good case stops at the missing ROM: the point is that the checks let it through.
                        answer = outcome(lambda: str(run_it(output=destination, **options)))
                    if case == 'good_edge':
                        answer.pop('message', None)  # the text of a missing-file error names the temporary folder
                    result[f'{name}/{case}/{"delegated" if destination is None else "direct"}'] = plain(
                        {'outcome': answer, 'delegated_level': seen}, root)
        with patch('retrorecomp.batch.identify', lambda path, *rest: SimpleNamespace(title='t', cover=None)):
            result['sms/bad_backend'] = plain(outcome(lambda: str(core.convert(root / 'Game.sms', output=output, backend='nope'))), root)
    return result


def collect_icon_calls(root):
    """What each converter hands to prepare_icon, and how its failures surface."""
    sms = root / 'Game.sms'
    sms.write_bytes(b'\0' * 0x8000)
    gb = root / 'Game.gb'
    gb.write_bytes(b'\0' * 0x8000)
    nes_rom = root / 'Game.nes'
    nes_rom.write_bytes(b'NES\x1a\x01\x01' + b'\0' * 10 + b'\0' * 16384 + b'\0' * 8192)
    try:
        from retrorecomp import conversion_common
        icon_owner = lambda module: 'retrorecomp.conversion_common' if hasattr(conversion_common, 'prepare_icon') else module
    except ImportError:
        icon_owner = lambda module: module
    result = {}
    for name, module, call in (
            ('sms', 'retrorecomp.core', lambda **kw: core.convert(sms, **kw)),
            ('gb', 'retrorecomp.gameboy', lambda **kw: gameboy.convert_game_boy(gb, **kw)),
            ('nes', 'retrorecomp.nes', lambda **kw: nes.convert_nes(nes_rom, **kw))):
        for label, error in (('artwork_error', ArtworkError('no art')), ('os_error', OSError('disk full')),
                             ('other_error', ValueError('not converted'))):
            seen = []

            def fake(*args, **kwargs):
                seen.append({'args': list(args), 'kwargs': kwargs})
                raise error
            workspace = root / f'build-{name}-{label}'
            workspace.mkdir()
            with patch(icon_owner(module) + '.prepare_icon', fake), patch(module + '.ROOT', workspace), \
                 patch('retrorecomp.core.profile_for_path', lambda path, selected=None: MASTER_SYSTEM), \
                 patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(workspace / 'library')}):
                answer = outcome(lambda: str(call(output=workspace / 'out', title='Icon game', cover=Path('c.png'),
                                                  boxart_dir=workspace / 'art', online_cover=False,
                                                  use_cover=True, icon_tags=True, emit=lambda text: None)))
            for call_seen in seen:
                for key in ('emit',):
                    call_seen['kwargs'][key] = 'callable' if callable(call_seen['kwargs'].get(key)) else None
                call_seen['args'][1] = Path(call_seen['args'][1]).name
            result[f'{name}/{label}'] = plain({'outcome': answer, 'calls': seen}, root)
    return result


# ---------------------------------------------------------------- replacement and file helpers

def collect_replacements(root):
    result = {}
    cases = [('abc', 'b', 'X'), ('abcb', 'b', 'X'), ('abc', 'z', 'X'), ('a' * 200, 'a' * 150, 'Y')]
    result['core.replace_once'] = [outcome(lambda: core.replace_once(*case)) for case in cases]
    result['nes_codegen._replace_count'] = [outcome(lambda: nes_codegen._replace_count(*case, count))
                                            for case in cases for count in (1, 2)]
    return result


def collect_files(root):
    """write-if-changed and the restoration of unchanged timestamps, through whatever the tree calls them."""
    from retrorecomp import gameboy_build, nes_build
    try:
        from retrorecomp.conversion_common import write_if_changed as write
    except ImportError:
        write = nes_build.write_changed
    result = {}
    target = root / 'new' / 'dir' / 'file.bin'
    first = write(target, b'one')
    old = 1_000_000_000_000_000_000
    os.utime(target, ns=(old, old))
    same = write(target, b'one')
    unchanged_stamp = target.stat().st_mtime_ns
    different = write(target, b'two')
    result['write'] = {'first': first, 'same': same, 'different': different, 'data': target.read_bytes().decode(),
                       'stamp_kept_when_same': unchanged_stamp == old, 'stamp_moved_when_changed': target.stat().st_mtime_ns != old}
    for label, preserve, names in (('nes', nes_build.preserve_inputs, ('host.c', 'host.h', 'CMakeLists.txt', 'rom.nes', 'skip.txt', 'a.inc', 'b.bin')),
                                   ('gb', gameboy_build.preserve_unchanged_sources, ('host.c', 'host.h', 'CMakeLists.txt', 'rom.gb', 'skip.txt', 'a.rc', 'b.md'))):
        project = root / ('project-' + label)
        project.mkdir()
        (project / 'runtime').mkdir()
        (project / 'runtime' / 'inner.h').write_bytes(b'inner')
        for name in names:
            (project / name).write_bytes(b'original ' + name.encode())
            os.utime(project / name, ns=(old, old))
        os.utime(project / 'runtime' / 'inner.h', ns=(old, old))
        with preserve(project):
            time.sleep(0.01)
            for name in names:
                if name in ('host.h', 'rom.gb', 'rom.nes'):
                    (project / name).write_bytes(b'CHANGED ' + name.encode())
                else:
                    (project / name).write_bytes(b'original ' + name.encode())  # rewritten with the same content
            (project / 'runtime' / 'inner.h').write_bytes(b'inner')
            (project / 'created.c').write_bytes(b'new')
        result['preserve_' + label] = {name: (project / name).stat().st_mtime_ns == old
                                       for name in (*names, 'created.c') if (project / name).exists()}
        result['preserve_' + label]['runtime/inner.h'] = (project / 'runtime' / 'inner.h').stat().st_mtime_ns == old
    return result


COLLECTORS = {'sms_probe': collect_sms_probe, 'run_probes': collect_run_probes, 'single_rom': collect_single_rom,
              'checks': collect_checks, 'icon_calls': collect_icon_calls, 'replacements': collect_replacements,
              'files': collect_files}


def collect_all():
    result = {}
    for name, collector in COLLECTORS.items():
        with tempfile.TemporaryDirectory() as directory:
            result[name] = collector(Path(directory).resolve())
    return result


class RecordedBehaviourTests(unittest.TestCase):
    """The converters behave as they did before the shared helpers (values in conversion_common_golden.json)."""

    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN_FILE.read_text(encoding='utf-8'))

    def same_as_recorded(self, name):
        with tempfile.TemporaryDirectory() as directory:
            actual = COLLECTORS[name](Path(directory).resolve())
        self.assertEqual(json.loads(json.dumps(actual)), self.golden[name])

    def test_the_master_system_probe_spawns_the_same_process(self):
        self.same_as_recorded('sms_probe')

    def test_the_game_boy_and_nes_probes_spawn_the_same_processes(self):
        self.same_as_recorded('run_probes')

    def test_single_rom_conversions_hand_convert_batch_the_same_arguments_and_judge_the_same_rows(self):
        self.same_as_recorded('single_rom')

    def test_scan_level_and_passes_and_frames_checks_keep_their_order_and_text(self):
        self.same_as_recorded('checks')

    def test_the_icon_preparation_gets_the_same_arguments_and_failures_surface_the_same_way(self):
        self.same_as_recorded('icon_calls')

    def test_pinned_source_replacements_accept_and_refuse_the_same_texts(self):
        self.same_as_recorded('replacements')

    def test_file_writes_and_timestamp_restoration_behave_the_same(self):
        self.same_as_recorded('files')

    def test_the_french_message_of_the_master_system_converter_is_kept(self):
        self.assertEqual(self.golden['checks']['sms/bad_passes/direct']['outcome']['message'],
                         'Choisis 1 à 10 passes et 1 à 10000 images par test.')
        self.assertEqual(self.golden['checks']['gb/bad_frames/direct']['outcome']['message'],
                         'Choose 1–10 passes and 1–10000 frames per test.')


class HelperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def test_replace_counted_counts_exactly_or_at_least_once_and_names_the_text_it_missed(self):
        from retrorecomp.conversion_common import replace_counted
        errors = []

        def error(old):
            errors.append(old)
            return KeyError(old)
        self.assertEqual(replace_counted('abcb', 'b', 'X', count=2, error=error), 'aXcX')
        self.assertEqual(replace_counted('abc', 'b', 'X', error=error), 'aXc')
        self.assertEqual(replace_counted('abcbb', 'b', 'X', count=None, error=error), 'aXcXX')
        for source, count in (('abcb', 1), ('abc', 2), ('ac', None), ('ac', 1)):
            with self.assertRaises(KeyError):
                replace_counted(source, 'b', 'X', count=count, error=error)
        self.assertEqual(errors, ['b'] * 4)

    def test_write_if_changed_keeps_the_timestamp_of_an_identical_file(self):
        from retrorecomp.conversion_common import write_if_changed
        path = self.root / 'a' / 'b.bin'
        self.assertTrue(write_if_changed(path, b'one'))
        os.utime(path, ns=(10**18, 10**18))
        self.assertFalse(write_if_changed(path, b'one'))
        self.assertEqual(path.stat().st_mtime_ns, 10**18)
        self.assertTrue(write_if_changed(path, b'two'))
        self.assertEqual(path.read_bytes(), b'two')

    def test_preserve_unchanged_restores_only_the_timestamps_of_unchanged_files(self):
        from retrorecomp.conversion_common import preserve_unchanged
        same, different = self.root / 'same.c', self.root / 'different.c'
        for path in (same, different):
            path.write_bytes(b'x')
            os.utime(path, ns=(10**18, 10**18))
        with preserve_unchanged(lambda: [same, different]):
            same.write_bytes(b'x')
            different.write_bytes(b'y')
        self.assertEqual(same.stat().st_mtime_ns, 10**18)
        self.assertNotEqual(different.stat().st_mtime_ns, 10**18)

    def test_scan_level_defaults_and_refuses_unknown_names(self):
        from retrorecomp.conversion_common import resolve_scan_level
        from retrorecomp.core import ConversionError
        self.assertEqual(resolve_scan_level(None), 'standard')
        self.assertEqual(resolve_scan_level(None, 'extended'), 'extended')
        self.assertEqual(resolve_scan_level('quick', 'extended'), 'quick')
        with self.assertRaises(ConversionError) as caught:
            resolve_scan_level('bogus')
        self.assertEqual(str(caught.exception), "Unknown scan level: 'bogus'.")

    def test_the_run_budget_accepts_its_edges_and_raises_the_given_text(self):
        from retrorecomp.conversion_common import check_run_budget
        from retrorecomp.core import ConversionError
        check_run_budget(1, 1, 'x')
        check_run_budget(10, 10000, 'x')
        check_run_budget(5, 20000, 'x', max_frames=30000)
        for passes, frames in ((0, 5), (11, 5), (3, 0), (3, 10001)):
            with self.assertRaises(ConversionError) as caught:
                check_run_budget(passes, frames, 'the text')
            self.assertEqual(str(caught.exception), 'the text')

    def test_spawn_runs_in_a_created_folder_with_the_given_environment_and_a_phase(self):
        from retrorecomp.conversion_common import check_exit, probe_environment, spawn
        folder = self.root / 'made' / 'here'
        environment = probe_environment(('PATH_NOT_SET_ANYWHERE',), RR_PROBE_TEST='1')
        events = []
        with patch.object(timings, 'phase', fake_phase_factory(events)):
            result = spawn([sys.executable, '-c', 'import os; print(os.getcwd(), os.environ["RR_PROBE_TEST"])'],
                           cwd=folder, env=environment, timeout=60, phase='native_runs',
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.stdout.split(), [str(folder), '1'])
        self.assertEqual(events, ['enter native_runs', 'exit native_runs'])
        check_exit(result, RuntimeError)
        failing = spawn([sys.executable, '-c', 'raise SystemExit(3)'], cwd=folder, timeout=60, capture_output=True)
        with self.assertRaises(RuntimeError) as caught:
            check_exit(failing, lambda done: RuntimeError(f'exit {done.returncode}'))
        self.assertEqual(str(caught.exception), 'exit 3')

    def test_probe_environment_removes_then_sets(self):
        from retrorecomp.conversion_common import probe_environment
        with patch.dict(os.environ, {'RR_A': '1', 'RR_B': '2'}):
            environment = probe_environment(('RR_A',), RR_B='3', RR_C='4')
        self.assertNotIn('RR_A', environment)
        self.assertEqual((environment['RR_B'], environment['RR_C']), ('3', '4'))
        self.assertEqual(os.environ.get('RR_B'), None)

    def test_the_window_flag_is_the_no_window_flag_on_windows_only(self):
        from retrorecomp.conversion_common import no_window
        self.assertEqual(no_window(), NO_WINDOW)

    def test_the_icon_helper_resolves_the_folder_and_turns_artwork_and_os_errors_into_conversion_errors(self):
        from retrorecomp.conversion_common import prepare_game_icon
        from retrorecomp.core import ConversionError
        seen = []
        with patch('retrorecomp.conversion_common.prepare_icon', lambda *a, **k: seen.append((a, k)) or {'embedded': True}):
            self.assertEqual(prepare_game_icon(self.root, self.root / 'r.nes', 'T', Path('art'), system_id='nes'),
                             {'embedded': True})
        self.assertEqual(seen[0][0][3], Path('art').resolve())
        for error in (ArtworkError('a'), OSError('b')):
            with patch('retrorecomp.conversion_common.prepare_icon', side_effect=error):
                with self.assertRaises(ConversionError) as caught:
                    prepare_game_icon(self.root, self.root / 'r.nes', 'T', Path('art'))
            self.assertEqual(str(caught.exception), str(error))

    def test_the_ab_tool_ignores_what_differs_by_construction_and_sees_a_real_difference(self):
        from tools import ab_conversion as ab
        first = ab.Normaliser({self.root / 'tree-a': '<TREE>'})
        second = ab.Normaliser({self.root / 'tree-b': '<TREE>'})
        report = lambda tree, stamp: {'version': stamp, 'created_utc': stamp, 'timings': {'total': stamp},
                                      'rom': {'sha256': 'r'}, 'packed': {'sha256': stamp, 'bytes': 1},
                                      'path': str(self.root / tree / 'x.c'), 'wall_seconds': stamp,
                                      'native_percent': 99.5}
        self.assertEqual(first.json(report('tree-a', '1')), second.json(report('tree-b', '2')))
        self.assertEqual(first.json(report('tree-a', '1'))['rom'], {'sha256': 'r'})
        changed = report('tree-b', '2')
        changed['native_percent'] = 99.4
        self.assertNotEqual(first.json(report('tree-a', '1')), second.json(changed))
        one = {'projects': {'game': {'generated/a.c': 'x', 'rom.nes': 'y'}}, 'reports': {'r.json': {'a': 1}}}
        two = {'projects': {'game': {'generated/a.c': 'x', 'rom.nes': 'y'}}, 'reports': {'r.json': {'a': 1}}}
        self.assertEqual(ab.compare(one, two), [])
        two['projects']['game']['generated/a.c'] = 'z'
        two['reports']['r.json']['a'] = 2
        self.assertEqual(len(ab.compare(one, two)), 2)

    def test_the_converters_adopted_the_helpers_instead_of_keeping_copies(self):
        """No console keeps its own copy: the sources name the helper, and the old names are gone."""
        for module, names in (('core', ('convert_single(', 'check_run_budget(', 'resolve_scan_level(', 'prepare_game_icon(',
                                        'replace_counted(', 'spawn(')),
                              ('gameboy', ('convert_single(', 'check_run_budget(', 'resolve_scan_level(', 'prepare_game_icon(')),
                              ('nes', ('convert_single(', 'check_run_budget(', 'resolve_scan_level(', 'prepare_game_icon(',
                                       'write_if_changed(')),
                              ('gameboy_build', ('preserve_unchanged(',)), ('nes_build', ('preserve_unchanged(',
                                                                                         'write_if_changed(')),
                              ('nes_codegen', ('replace_counted(',))):
            text = (ROOT / 'retrorecomp' / (module + '.py')).read_text(encoding='utf-8')
            for name in names:
                self.assertIn(name, text, f'{module} should call {name}')
            self.assertNotIn('write_changed(', text)
            self.assertNotIn('except (ArtworkError, OSError)', text)
            self.assertNotIn('Unknown scan level', text)


if __name__ == '__main__' and '--record' in sys.argv:
    GOLDEN_FILE.write_text(json.dumps(collect_all(), indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    raise SystemExit(0)
if __name__ == '__main__':
    unittest.main()
