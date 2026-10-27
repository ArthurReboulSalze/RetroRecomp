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

from retrorecomp import compilation_inputs as inputs


class CompilationInputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.revisions = {}
        # Every listed file exists, so a stamp can be computed; each test then changes what it needs.
        for name in inputs.manifest_names():
            if not name.startswith('retrorecomp.'):
                self.write(name, ('initial contents of ' + name + ' ') * 4)
        for target, value in (
                ('retrorecomp.paths.ASSETS', self.root),
                ('retrorecomp.compilation_inputs._code_digest', self.code_digest)):
            mocked = patch(target, **({'side_effect':value} if callable(value) else {'new':value}))
            mocked.start(); self.addCleanup(mocked.stop)

    def code_digest(self, name, *metadata):
        return self.revisions.get(name, 'unchanged')

    def write(self, name, value):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def stamps(self):
        return {s:inputs.engine_stamp(s) for s in ('sms','gg','gb','nes','md','snes','ng','x68','cps1')}

    def test_interface_and_unrelated_backend_changes_keep_exports(self):
        before = self.stamps()
        for name in ('gui','i18n','updater','ui_fonts','linux_desktop','queue_state'):
            self.revisions['retrorecomp.' + name] = 'ui-release'
        self.assertEqual(before, self.stamps())
        self.revisions['retrorecomp.megadrive_bus'] = 'new-bus'
        after = self.stamps()
        self.assertNotEqual(before['md'], after['md'])
        for system in ('sms','gg','gb','nes','snes','ng','x68'):
            self.assertEqual(before[system], after[system])

    def test_native_shared_unknown_and_scoped_dependencies(self):
        before = self.stamps()
        self.write('native/md_prefetch.inc','new pipeline')
        after = self.stamps()
        self.assertNotEqual(before['md'],after['md'])
        self.assertEqual(before['snes'],after['snes'])
        self.assertEqual(before['sms'],after['sms'])
        # A file on disk that the manifest does not list is ignored; listing it makes it a shared input.
        self.write('native/new_unclassified_helper.h','new shared helper')
        self.assertEqual(after, self.stamps())
        listed = {**inputs.INPUTS, inputs.ALL: (*inputs.INPUTS[inputs.ALL], 'native/new_unclassified_helper.h')}
        with patch.object(inputs, 'INPUTS', listed):
            self.assertTrue(all(after[s] != self.stamps()[s] for s in after))
        before = self.stamps()
        self.write('native/m68000_state_helpers.h','new CPU helper')
        after = self.stamps()
        self.assertNotEqual(before['md'],after['md']);self.assertNotEqual(before['ng'],after['ng'])
        self.assertNotEqual(before['x68'],after['x68']);self.assertNotEqual(before['cps1'],after['cps1'])
        self.assertEqual(before['snes'],after['snes'])

    def test_cps1_files_do_not_age_existing_exports(self):
        before = self.stamps()
        self.revisions['retrorecomp.cps1'] = 'new romsets'
        self.revisions['retrorecomp.cps1_catalogue'] = 'new catalogue'
        self.write('native/cps1_machine.c', 'new board')
        self.write('assets/cps1-catalogue.json', '{}')
        self.write('licenses/cps1-machine.md', 'new notice')
        after = self.stamps()
        self.assertNotEqual(before['cps1'], after['cps1'])
        del before['cps1'], after['cps1']
        self.assertEqual(before, after)

    def test_cps1_follows_the_modules_and_host_it_reuses(self):
        before = self.stamps()
        self.revisions['retrorecomp.neogeo_codegen'] = 'new semantics'
        after = self.stamps()
        self.assertNotEqual(before['cps1'], after['cps1']); self.assertNotEqual(before['ng'], after['ng'])
        self.assertEqual(before['md'], after['md'])
        before = after
        self.write('native/console16_host_ui.c', 'new shared menus')
        after = self.stamps()
        for system in ('md', 'snes', 'ng', 'cps1'):
            self.assertNotEqual(before[system], after[system])
        self.assertEqual(before['nes'], after['nes'])

    def test_relative_names_and_notices_are_part_of_the_signature(self):
        def listed(name):
            self.write(name, 'same contents')
            return {**inputs.INPUTS, ('md',): (name,)}
        with patch.object(inputs, 'INPUTS', listed('native/md_one.h')):
            before = inputs.engine_stamp('md')
        with patch.object(inputs, 'INPUTS', listed('native/md_two.h')):
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
        script='from retrorecomp.compilation_inputs import code_fingerprint;print(code_fingerprint(compile('+repr(source)+',"different.py","exec")))'
        for seed in ('1','2','17','random'):
            value=subprocess.check_output([sys.executable,'-c',script],env={**os.environ,'PYTHONHASHSEED':seed},text=True).strip()
            self.assertEqual(value,expected)
        self.assertNotEqual(expected,inputs.code_fingerprint(compile(source.replace('theta','omega'),'temporary.py','exec')))

    def test_knowledge_is_scoped_to_the_exact_cartridge(self):
        sha, other='1'*64,'2'*64
        record={'engine':'a'*40,'rom_bytes':8192,'rom_entries':[[0,0x8000]]}
        payload={'schema':1,'consoles':{'nes':{sha:record,other:record}}}
        path=self.root/'knowledge/qualified.json.gz';path.parent.mkdir()
        def save():
            with gzip.open(path,'wt',encoding='utf-8') as stream:json.dump(payload,stream)
        save()
        from retrorecomp import knowledge
        self.addCleanup(knowledge._qualified_bank.cache_clear)
        with patch.dict('os.environ', {'RETRO_RECOMP_BUNDLED_KNOWLEDGE':'1'}, clear=True), \
                patch('retrorecomp.knowledge.qualified_path', return_value=path):
            before=inputs.knowledge_stamp('nes',sha)
            payload['consoles']['nes'][other]={**record,'rom_entries':[[0,0x8001]]};save()
            self.assertEqual(before,inputs.knowledge_stamp('nes',sha))
            payload['consoles']['nes'][sha]={**record,'rom_entries':[[0,0x8002]]};save()
            self.assertNotEqual(before,inputs.knowledge_stamp('nes',sha))



class InputRoleTests(unittest.TestCase):
    """The player shell is classified the same way on every machine."""

    def test_every_machine_shell_is_host_and_every_entry_is_game(self):
        shells = ('native/retro_menu.c', 'native/game_options.h', 'native/runtime_catalog.inc',
                  'native/host.c', 'native/controls.c', 'native/ui.c',          # Master System / Game Gear
                  'native/gb_menu.inc', 'retrorecomp.gameboy_host',                 # Game Boy
                  'native/nes_host_ui.c',                                         # NES
                  'native/console16_host_ui.c',                                   # Mega Drive, SNES, Neo Geo, CPS-1
                  'native/x68000_reference/player_ui.inc',                        # X68000
                  'licenses/SDL2.md', 'THIRD_PARTY_NOTICES.md', 'retrorecomp.metadata')
        for name in shells:
            with self.subTest(name=name):
                self.assertEqual(inputs.role(name), 'host')
        # Headless discovery and validation run through these: always game-side.
        entries = ('native/launcher.c', 'native/console16_main.c', 'native/cps1_main.c',
                   'native/neogeo_main.c', 'native/x68000_reference/reference_host.c',
                   'native/x68000_reference/audio_checks.c', 'native/platform_io.c',
                   'native/embedded_resources.h', 'retrorecomp.gameboy_runtime', 'retrorecomp.nes_runtime',
                   'retrorecomp.core', 'retrorecomp.knowledge', 'profiles/example.sms.toml',
                   'assets/neogeo-catalogue.json', 'native/a_new_file.c', 'retrorecomp.a_new_module')
        for name in entries:
            with self.subTest(name=name):
                self.assertEqual(inputs.role(name), 'game')

    def test_listed_host_inputs_exist(self):
        import importlib.util
        from retrorecomp.paths import ASSETS
        self.assertEqual([n for n in inputs.HOST_NATIVE if not (ASSETS / 'native' / n).is_file()], [])
        self.assertEqual([m for m in inputs.HOST_MODULES
                          if importlib.util.find_spec('retrorecomp.' + m) is None], [])

    def test_role_stamps_move_independently(self):
        names = [('native/retro_menu.c', 'a'), ('native/launcher.c', 'b')]
        with patch('retrorecomp.compilation_inputs.input_fingerprints', side_effect=lambda system: list(names)):
            before = inputs.role_stamps('sms')
            names[0] = ('native/retro_menu.c', 'changed menu')
            menu = inputs.role_stamps('sms')
            names[1] = ('native/launcher.c', 'changed entry')
            entry = inputs.role_stamps('sms')
        self.assertEqual((menu['game'], menu['host'] != before['host']), (before['game'], True))
        self.assertEqual((entry['host'], entry['game'] != menu['game']), (menu['host'], True))


if __name__ == '__main__':unittest.main()
