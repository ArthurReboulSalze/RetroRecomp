import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SetupLockTests(unittest.TestCase):
    def test_independent_processes_and_nested_setup_share_one_gate(self):
        worker = r'''
import json,sys,time
from pathlib import Path
from retrorecomp import core
core.ROOT=Path(sys.argv[1])
counter=core.ROOT/'counter.json'
@core.serialized_setup
def inner():
    value=json.loads(counter.read_text()) if counter.exists() else 0
    time.sleep(.03)
    counter.write_text(json.dumps(value+1))
@core.serialized_setup
def outer():
    inner()
    inner()
for _ in range(3):outer()
'''
        with tempfile.TemporaryDirectory(prefix='rr-setup-lock-') as temp:
            root = Path(temp)
            processes = [subprocess.Popen([sys.executable, '-c', worker, temp],
                cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True) for _ in range(6)]
            outputs = [p.communicate(timeout=60) for p in processes]
            for p, (stdout, stderr) in zip(processes, outputs):
                self.assertEqual(p.returncode, 0, stdout + stderr)
            self.assertEqual(json.loads((root / 'counter.json').read_text()), 36)

    def test_exception_releases_nested_gate(self):
        from unittest.mock import patch
        from retrorecomp import core
        with tempfile.TemporaryDirectory(prefix='rr-setup-error-') as temp:
            @core.serialized_setup
            def fail():
                raise ValueError('fixture')
            @core.serialized_setup
            def next_setup():
                return 'ready'
            with patch.object(core, 'ROOT', Path(temp)):
                with self.assertRaisesRegex(ValueError, 'fixture'):
                    fail()
                self.assertEqual(next_setup(), 'ready')


class EngineSetupTests(unittest.TestCase):
    """Every function that clones or pins an engine under .deps runs under the shared setup gate (core.serialized_setup):
    a batch converts several games at once, and on a fresh install the first one clones while the others look for HEAD.
    The PC Engine missed it until 9 November 2026 (13 of 14 cards failed on an empty .deps with two jobs). A function that
    clones without the decorator is listed here with the guard that covers it, so a new machine cannot miss it silently."""

    GUARDED_ELSEWHERE = {
        'core.follow_pin': 'the helper of core.dependencies and pce_build.ensure_engine, both serialized',
        'amiga_vamiga.source': "called under entry_lock('vamiga-lock') in amiga_conversion.machine_core",
        'atarist_hatari.source': "called under entry_lock('hatari-lock') in atarist_conversion.machine_core",
        'n64_core.source': "called under entry_lock('core-lock') in n64_conversion.machine_core",
        'psx_beetle.source': "called under psx_conversion's entry_lock of the game's own folder only (raised with the "
                             'PlayStation specialist on 9 November 2026)',
        'scummvm_build._checkout': 'called by prepare_sources from _build_runtime, which runs through serialized_setup',
        'scummvm_build._ensure_sdl': 'called by _build_runtime, which runs through serialized_setup',
    }

    @staticmethod
    def engine_setups() -> dict[str, bool]:
        """{'module.function': serialized} for each top-level function that clones a git repository or calls
        pinned_checkout / follow_pin, nested helpers included."""
        import ast

        def name(node):
            return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None

        def setup(call):
            if name(call.func) in ('pinned_checkout', 'follow_pin'):
                return True
            words = [e.value for e in call.args[0].elts if isinstance(e, ast.Constant)] \
                if call.args and isinstance(call.args[0], ast.List) else []
            return 'git' in words and 'clone' in words
        package = Path(__file__).resolve().parents[1] / 'retrorecomp'
        found = {}
        for path in sorted(package.rglob('*.py')):
            module = path.relative_to(package).with_suffix('').as_posix().replace('/', '.')
            for top in ast.parse(path.read_text(encoding='utf-8')).body:
                if isinstance(top, ast.FunctionDef) and any(isinstance(n, ast.Call) and setup(n) for n in ast.walk(top)):
                    found[f'{module}.{top.name}'] = any(name(d) == 'serialized_setup' for d in top.decorator_list)
        return found

    def test_every_engine_setup_is_serialized_or_names_its_guard(self):
        setups = self.engine_setups()
        self.assertIn('pce_build.ensure_engine', setups)
        unguarded = sorted(name for name, serialized in setups.items() if not serialized)
        self.assertEqual(unguarded, sorted(self.GUARDED_ELSEWHERE))
        self.assertGreaterEqual(sum(setups.values()), 7)              # the scan still finds the serialized ones

    def test_the_pc_engine_engine_is_fetched_under_the_gate(self):
        from unittest.mock import patch
        from retrorecomp import core, pce_build
        depth = []
        with tempfile.TemporaryDirectory(prefix='rr-pce-setup-') as temp, patch.object(core, 'ROOT', Path(temp)), \
                patch.object(core, 'follow_pin', side_effect=lambda *_, **__: depth.append(core._SHARED_SETUP_DEPTH)):
            pce_build.ensure_engine(lambda text: None)
        self.assertEqual(depth, [1])


if __name__ == '__main__':
    unittest.main()
