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


if __name__ == '__main__':
    unittest.main()
