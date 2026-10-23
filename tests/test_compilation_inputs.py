"""Export invalidation follows real console inputs, including frozen code."""
import gzip
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import os
import unittest
from unittest.mock import patch

from smsrecomp import compilation_inputs as inputs


class CompilationInputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.revisions = {}
        for target, value in (
                ('smsrecomp.paths.ASSETS', self.root),
                ('smsrecomp.compilation_inputs._code_digest', self.code_digest)):
            mocked = patch(target, **({'side_effect':value} if callable(value) else {'new':value}))
            mocked.start(); self.addCleanup(mocked.stop)

    def code_digest(self, name, *metadata):
        return self.revisions.get(name, 'unchanged')

    def write(self, name, value):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def stamps(self):
        return {s:inputs.engine_stamp(s) for s in ('sms','gg','gb','nes','md','snes','ng')}

    def test_interface_and_unrelated_backend_changes_keep_exports(self):
        before = self.stamps()
        for name in ('gui','i18n','updater','ui_fonts','linux_desktop','queue_state'):
            self.revisions['smsrecomp.' + name] = 'ui-release'
        self.assertEqual(before, self.stamps())
        self.revisions['smsrecomp.megadrive_bus'] = 'new-bus'
        after = self.stamps()
        self.assertNotEqual(before['md'], after['md'])
        for system in ('sms','gg','gb','nes','snes','ng'):
            self.assertEqual(before[system], after[system])

    def test_native_shared_unknown_and_scoped_dependencies(self):
        before = self.stamps()
        self.write('native/md_prefetch.inc','new pipeline')
        after = self.stamps()
        self.assertNotEqual(before['md'],after['md'])
        self.assertEqual(before['snes'],after['snes'])
        self.assertEqual(before['sms'],after['sms'])
        self.write('native/new_unclassified_helper.h','new shared helper')
        self.assertTrue(all(after[s] != self.stamps()[s] for s in after))
        before = self.stamps()
        self.write('native/m68000_state_helpers.h','new CPU helper')
        after = self.stamps()
        self.assertNotEqual(before['md'],after['md']);self.assertNotEqual(before['ng'],after['ng'])
        self.assertEqual(before['snes'],after['snes'])

    def test_cps1_files_do_not_age_existing_exports(self):
        before = self.stamps()
        self.revisions['smsrecomp.cps1'] = 'new romsets'
        self.revisions['smsrecomp.cps1_catalogue'] = 'new catalogue'
        self.write('native/cps1_machine.c', 'new board')
        self.write('assets/cps1-catalogue.json', '{}')
        self.write('licenses/cps1-machine.md', 'new notice')
        self.assertEqual(before, self.stamps())

    def test_relative_names_and_notices_are_part_of_the_signature(self):
        path=self.write('native/md_one.h','same contents'); before=inputs.engine_stamp('md')
        path.rename(path.with_name('md_two.h'))
        self.assertNotEqual(before, inputs.engine_stamp('md'))
        before=self.stamps();self.write('licenses/SDL2.md','new embedded notice')
        self.assertTrue(all(before[s] != self.stamps()[s] for s in before))

    def test_ui_assets_do_not_invalidate_games_but_game_icons_do(self):
        before=self.stamps()
        self.write('assets/Retro-Recomp-banner.png','header')
        self.write('assets/RetroRecomp-UI-JP.otf','interface font')
        self.assertEqual(before,self.stamps())
        self.write('assets/Retro-Recomp-icon-256.png','export icon')
        self.assertTrue(all(before[s] != self.stamps()[s] for s in before))

    def test_frozen_code_paths_do_not_change_a_code_fingerprint(self):
        source='def outer():\n    return lambda x: x + 1\n'
        first=compile(source,'C:/temporary/_MEI111/code.py','exec')
        second=compile(source,'/tmp/_MEI222/code.py','exec')
        import marshal
        self.assertEqual(marshal.dumps(inputs._portable_code(first)),
                         marshal.dumps(inputs._portable_code(second)))
        self.assertEqual(inputs.code_fingerprint(first),inputs.code_fingerprint(second))

    def test_constants_are_stable_across_hash_seeds_and_marshal_roundtrip(self):
        source="def f(x):\n return x in {'alpha','beta','gamma','delta','epsilon','zeta','eta','theta'}\n"
        import marshal
        code=compile(source,'temporary.py','exec')
        expected=inputs.code_fingerprint(code)
        self.assertEqual(expected,inputs.code_fingerprint(marshal.loads(marshal.dumps(code))))
        script='from smsrecomp.compilation_inputs import code_fingerprint;print(code_fingerprint(compile('+repr(source)+',"different.py","exec")))'
        for seed in ('1','2','17','random'):
            value=subprocess.check_output([sys.executable,'-c',script],env={**os.environ,'PYTHONHASHSEED':seed},text=True).strip()
            self.assertEqual(value,expected)
        self.assertNotEqual(expected,inputs.code_fingerprint(compile(source.replace('theta','omega'),'temporary.py','exec')))

    def test_knowledge_is_scoped_to_the_exact_cartridge(self):
        sha, other='1'*64,'2'*64
        record={'engine':'a'*40,'rom_bytes':8192,'rom_entries':[[0,0x8000]]}
        payload={'schema':1,'consoles':{'nes':{sha:record,other:record}}}
        path=self.root/'assets/compilation-knowledge.json.gz';path.parent.mkdir()
        def save():
            with gzip.open(path,'wt',encoding='utf-8') as stream:json.dump(payload,stream)
        save()
        with patch.dict('os.environ', {'RETRO_RECOMP_BUNDLED_KNOWLEDGE':'1'}, clear=True):
            before=inputs.knowledge_stamp('nes',sha)
            payload['consoles']['nes'][other]={**record,'rom_entries':[[0,0x8001]]};save()
            self.assertEqual(before,inputs.knowledge_stamp('nes',sha))
            payload['consoles']['nes'][sha]={**record,'rom_entries':[[0,0x8002]]};save()
            self.assertNotEqual(before,inputs.knowledge_stamp('nes',sha))


if __name__ == '__main__':unittest.main()
