from dataclasses import asdict
import hashlib
import json
import os
import shutil
from pathlib import Path
import tempfile
import time
from unittest import TestCase
from unittest.mock import patch
from unittest.mock import Mock
from threading import Event, Lock
from queue import Queue

from retrorecomp.compiled_games import Inventory, Game, game_from_report, refresh, scan
from retrorecomp.feedback import Observation, encode
from retrorecomp.memory_view import summaries


class CompiledGamesTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows CI may expose TEMP through an 8.3 alias; production readers
        # resolve paths. Compare the same canonical spelling in these fixtures.
        self.root = Path(self.temp.name).resolve()
        self.console = self.root/'Games/Master System'
        self.console.mkdir(parents=True)
        self.identity = 'a'*64
        self.exe = self.console/'Example.exe'
        self.exe.write_bytes(b'MZ[Retro-Recomp]\0'+self.identity.encode()+b'\0')
        self.report = self.console/'datas/reports/example/conversion-report.json'
        self.report.parent.mkdir(parents=True)
        self.data = {'tool':'Retro-Recomp','version':'1.1.4','system':{'id':'sms'},
            'rom':{'sha256':self.identity,'name':'Example.sms'},'executable':self.exe.name,
            'runtime_feedback':{'identity':self.identity,'fingerprint':
                hashlib.sha256(encode([],'sms',self.identity)).hexdigest()},
            'export_receipt':{'sha256':hashlib.sha256(self.exe.read_bytes()).hexdigest()},
            'final_checks':[{'interpreter_percent':0}]}
        self.report.write_text(json.dumps(self.data),encoding='utf8')
        self.inventory = Inventory(self.root/'converter/compiled-games.json')
        self.env = patch.dict(os.environ,{'RETRO_RECOMP_LIBRARY_DIR':str(self.root/'knowledge')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_collection_is_restored_without_scanning_or_opening_games(self):
        game = game_from_report(self.report)
        game.source = str(self.root/'original.sms')
        self.inventory.remember(game)
        self.inventory.roots = [str(self.console)]
        self.inventory.save()
        with patch('retrorecomp.compiled_games.scan',side_effect=AssertionError('No startup scan')):
            restored = Inventory(self.inventory.path)
        self.assertEqual([asdict(g) for g in restored.snapshot()],[asdict(game)])
        self.assertEqual(restored.roots,self.inventory.roots)

    def test_cartridge_device_instructions_stay_visible_as_fallback(self):
        # Main CPU clean, device interpreted: the row is still flagged, never silently clean.
        for device, expected in ((40_000_000, True), (0, False)):
            self.data['final_checks'] = [{'interpreter_percent': 0, 'interpreted_opcodes': 0,
                'main_interpreted_opcodes': 0, 'cartridge_chip': 'superfx',
                'coprocessor_instructions': device}]
            self.report.write_text(json.dumps(self.data),encoding='utf8')
            self.assertEqual(game_from_report(self.report).tested_fallback, expected)

    def test_complete_scan_never_runs_executables_and_prunes_deleted_entries(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Never run a scanned binary')):
            count = scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(count,1)
        game = self.inventory.snapshot()[0]
        self.assertEqual(game.status,'no_hints')
        self.exe.unlink()
        scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(game.status,'missing')
        self.assertEqual(Inventory(self.inventory.path).snapshot(),[])

    def test_moving_a_modern_collection_rebases_owned_paths_without_opening_games(self):
        old = self.root/'portable'
        target = old/'Games/Master System/Example.exe'
        target.parent.mkdir(parents=True)
        target.write_bytes(self.exe.read_bytes())
        source = str(self.root/'ROMS/Example.sms')
        inventory = Inventory(old/'datas/compiled-games.json')
        inventory.remember(Game(str(target),'sms',self.identity,'Example',
                                report=str(target.parent/'datas/reports/example/conversion-report.json'),
                                source=source,favorite=True))
        external = self.root/'another-library'
        inventory.roots=[str(old/'Games'),str(external)]
        inventory.save()
        new=self.root/'installed'
        shutil.copytree(old,new)
        with patch('retrorecomp.compiled_games.scan',side_effect=AssertionError('No startup scan')), \
             patch('retrorecomp.batch._embedded_export_identity',side_effect=AssertionError('Do not inspect binaries')):
            restored=Inventory(new/'datas/compiled-games.json')
            restored.relocate()
        game=restored.snapshot()[0]
        self.assertEqual(Path(game.executable),new/'Games/Master System/Example.exe')
        self.assertEqual(Path(game.report),new/'Games/Master System/datas/reports/example/conversion-report.json')
        self.assertEqual(game.source,source)
        self.assertTrue(game.favorite)
        self.assertEqual(restored.roots,[str(new/'Games'),str(external)])
        self.assertTrue((old/'Games/Master System/Example.exe').exists())
        self.assertTrue((new/'datas/compiled-games.before-path-migration.json').is_file())

    def test_legacy_migration_merges_old_and_local_aliases_preserving_favorites(self):
        old = self.root/'old-app'
        new = self.root/'new-app'
        shutil.copytree(self.root/'Games',new/'Games')
        old_game=Game(str(old/'Games/Master System/Example.exe'),'sms',self.identity,'Example',
                      report=str(old/'Games/Master System/datas/reports/example/conversion-report.json'),
                      source=str(self.root/'ROMS/Example.sms'),favorite=True)
        local=game_from_report(new/'Games/Master System/datas/reports/example/conversion-report.json')
        path=new/'datas/compiled-games.json'
        path.parent.mkdir(parents=True)
        original=json.dumps(dict(schema=1,roots=[str(old/'Games')],games=[asdict(old_game),asdict(local)]))
        path.write_text(original,encoding='utf-8')
        inventory=Inventory(path)
        with patch('retrorecomp.batch._embedded_export_identity',side_effect=AssertionError('No binary scan')):
            self.assertEqual(inventory.relocate(),1)
        games=inventory.snapshot()
        self.assertEqual(len(games),1)
        self.assertEqual(games[0].executable,local.executable)
        self.assertEqual(games[0].source,old_game.source)
        self.assertTrue(games[0].favorite)
        self.assertEqual(inventory.roots,[str(new/'Games')])
        self.assertEqual(path.with_name('compiled-games.before-path-migration.json').read_text(encoding='utf-8'),original)
        self.assertFalse(Inventory(path).relocation_pending)
        scan(inventory,[new/'Games'],{})
        scan(inventory,[new/'Games'],{})
        self.assertEqual(len(inventory.snapshot()),1)
        self.assertTrue(inventory.snapshot()[0].favorite)

    def test_legacy_migration_checks_exact_report_identity_not_only_the_name(self):
        new=self.root/'new-app'
        shutil.copytree(self.root/'Games',new/'Games')
        path=new/'datas/compiled-games.json'
        path.parent.mkdir(parents=True)
        old=Game(str(self.root/'old/Games/Master System/Example.exe'),'sms','b'*64,'Example',
                 report=str(self.root/'old/Games/Master System/datas/reports/example/conversion-report.json'))
        path.write_text(json.dumps(dict(schema=1,games=[asdict(old)])),encoding='utf-8')
        inventory=Inventory(path)
        self.assertEqual(inventory.relocate(),0)
        self.assertEqual(inventory.snapshot()[0].executable,old.executable)

    def test_legacy_copy_opens_correctly_before_any_scan_without_reading_executables(self):
        old=self.root/'old-app'
        new=self.root/'installed-app'
        shutil.copytree(self.root/'Games',new/'Games')
        game=Game(str(old/'Games/Master System/Example.exe'),'sms',self.identity,'Example',
                  report=str(old/'Games/Master System/datas/reports/example/conversion-report.json'),favorite=True)
        path=new/'datas/compiled-games.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(schema=1,games=[asdict(game)])),encoding='utf-8')
        inventory=Inventory(path)
        opening=Path.open
        def metadata_only(file,*args,**kwargs):
            if file.suffix.lower()=='.exe':raise AssertionError('Never open games during relocation')
            return opening(file,*args,**kwargs)
        with patch.object(Path,'open',metadata_only),patch('subprocess.Popen',side_effect=AssertionError('Never execute')):
            self.assertEqual(inventory.relocate(),1)
        self.assertEqual(Path(inventory.snapshot()[0].executable),new/'Games/Master System/Example.exe')
        self.assertTrue(inventory.snapshot()[0].favorite)

    def test_temporarily_unavailable_legacy_copy_can_be_relocated_on_a_later_open(self):
        old=self.root/'old-app'
        new=self.root/'installed-app'
        game=Game(str(old/'Games/Master System/Example.exe'),'sms',self.identity,'Example',
                  report=str(old/'Games/Master System/datas/reports/example/conversion-report.json'))
        path=new/'datas/compiled-games.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(schema=1,games=[asdict(game)])),encoding='utf-8')
        inventory=Inventory(path)
        self.assertEqual(inventory.relocate(),0)
        shutil.copytree(self.root/'Games',new/'Games')
        reopened=Inventory(path)
        self.assertTrue(reopened.relocation_pending)
        self.assertEqual(reopened.relocate(),1)
        self.assertEqual(Path(reopened.snapshot()[0].executable),new/'Games/Master System/Example.exe')

    def test_two_existing_copies_remain_distinct_and_missing_external_alias_is_pruned(self):
        scan(self.inventory,[self.root/'Games'],{})
        second=self.root/'another-library'
        second.mkdir()
        other=second/'Example.exe'
        shutil.copy2(self.exe,other)
        original=self.inventory.snapshot()[0]
        original.favorite=True
        scan(self.inventory,[second],{})
        self.assertEqual(len(self.inventory.snapshot()),2)
        other.unlink()
        # Even a scan of the local root checks the formerly saved external path.
        scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(len(self.inventory.snapshot()),1)
        self.assertTrue(self.inventory.snapshot()[0].favorite)

    def test_cancelled_scan_does_not_prune_existing_collection(self):
        scan(self.inventory,[self.root/'Games'],{})
        self.exe.unlink()
        cancel=Event()
        cancel.set()
        scan(self.inventory,[self.root/'Games'],{},cancel=cancel)
        self.assertEqual(len(self.inventory.snapshot()),1)

    def test_unavailable_root_does_not_remove_saved_games(self):
        missing=self.root/'unavailable-drive/Games/Example.exe'
        self.inventory.remember(Game(str(missing),'sms',self.identity,'Offline copy'))
        scan(self.inventory,[self.root/'Games',self.root/'unavailable-drive'],{})
        self.assertEqual(len(self.inventory.snapshot()),2)
        self.assertEqual(next(g for g in self.inventory.snapshot() if Path(g.executable)==missing).status,'missing')

    def test_new_fallback_survives_removing_the_original_file(self):
        game = game_from_report(self.report)
        folder = self.console/'datas/fallbacks'
        folder.mkdir(parents=True)
        payload = encode([Observation(1,123,0,b'abcd')],'sms',self.identity)
        file = folder/f'sms-{self.identity}.rrfb'
        file.write_bytes(payload)
        refresh(game)
        self.assertEqual(game.status,'new_hints')
        self.assertEqual(game.hints,1)
        file.unlink()
        refresh(game)
        self.assertEqual(game.status,'new_hints')
        self.data['runtime_feedback']['fingerprint'] = hashlib.sha256(payload).hexdigest()
        self.report.write_text(json.dumps(self.data))
        refresh(game)
        self.assertEqual(game.status,'covered')

    def test_bad_feedback_and_modified_executables_are_not_reported_as_clean(self):
        game = game_from_report(self.report)
        folder = self.console/'datas/fallbacks'
        folder.mkdir(parents=True)
        (folder/f'sms-{self.identity}.rrfb').write_bytes(b'broken')
        refresh(game)
        self.assertEqual(game.status,'unreadable')
        self.exe.write_bytes(self.exe.read_bytes()+b'changed')
        refresh(game)
        self.assertEqual(game.status,'changed')

    def test_reports_cannot_escape_the_scanned_folder(self):
        for name in ('../another.exe','..\\another.exe','/another.exe','C:\\another.exe'):
            self.data['executable'] = name
            self.report.write_text(json.dumps(self.data))
            with self.assertRaises(ValueError):game_from_report(self.report)

    def test_conflicting_revision_reports_follow_the_real_binary_identity(self):
        other = self.report.parent.parent/'other/conversion-report.json'
        other.parent.mkdir()
        bad = dict(self.data,rom={'sha256':'b'*64})
        other.write_text(json.dumps(bad))
        scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(len(self.inventory.snapshot()),1)
        self.assertEqual(self.inventory.snapshot()[0].identity,self.identity)

    def test_moved_game_with_no_reports_reuses_persistent_identity(self):
        self.inventory.remember(game_from_report(self.report))
        moved = self.root/'moved'
        moved.mkdir()
        (moved/'Example.exe').write_bytes(self.exe.read_bytes())
        scan(self.inventory,[moved],{})
        found = [g for g in self.inventory.snapshot() if Path(g.executable).parent==moved]
        self.assertEqual(len(found),1)
        self.assertEqual(found[0].identity,self.identity)

    def test_game_boy_summary_never_rehashes_the_large_trace(self):
        folder = self.root/'knowledge/gb'/self.identity
        folder.mkdir(parents=True)
        trace = folder/'entries.trace'
        trace.write_bytes(b'a'*200000)
        (folder/'trace.json').write_text(json.dumps({'title':'Example GB'}))
        opened = []
        original = Path.open
        def opening(path,*args,**kwargs):
            opened.append(path)
            if path == trace:raise AssertionError('Viewer must not read the trace')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opening):
            rows,cache = summaries('gb')
            self.assertEqual(rows[0]['bytes'],200000)
            self.assertEqual(rows[0]['system'],'gb')
            again,_ = summaries('gb',cache)
        self.assertEqual(rows,again)
        self.assertEqual(opened.count(folder/'trace.json'),1)

    def test_reconvert_uses_the_exact_source_and_destination_with_normal_conversion(self):
        from retrorecomp.gui import Application
        from retrorecomp.batch import BatchItem
        source = self.root/'original.sms'
        source.write_bytes(b'placeholder')
        game = game_from_report(self.report,source=str(source))
        second=Game(**{**asdict(game),'executable':str(self.root/'another/Example.exe')})
        owner = Application.__new__(Application)
        owner.busy=owner.updating=False
        owner.items={}
        owner.language='en'
        owner.jobs=Mock();owner.jobs.get.return_value=2
        owner.cancel=Event();owner.messages=Queue()
        owner.set_controls=Mock();owner.preferences=Mock(return_value={})
        owner.compiled_inventory=self.inventory
        owner.compiled_view=Mock()
        from retrorecomp.platforms import target_id
        game.target=target_id()
        second.target=target_id()
        item=BatchItem(source,'Example',system='sms',sha256=self.identity)
        active=maximum=0
        lock=Lock()
        def convert(*args):
            nonlocal active,maximum
            with lock:
                active+=1
                maximum=max(active,maximum)
            time.sleep(.03)
            self.assertEqual(args[5],args[7].parent)
            self.assertIn(args[7],(self.exe,Path(second.executable)))
            self.assertTrue(args[-1]['force'])
            folder=args[6]
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/'conversion-report.json'
            path.write_text(json.dumps(self.data))
            args[7].write_bytes(self.exe.read_bytes())
            with lock:active-=1
            return {'status':'success','report':str(path),'executable':str(args[7])}
        with patch('retrorecomp.gui.identify',return_value=item), \
             patch('retrorecomp.batch._convert_in_budget',side_effect=convert) as compiler:
            owner.begin_reconvert([(game,source),(second,source)])
            while True:
                event=owner.messages.get(timeout=10)
                if event[0]=='collection_done':break
            self.assertEqual(event,('collection_done',{'success':2,'failed':0}))
        self.assertEqual(compiler.call_count,2)
        self.assertEqual(maximum,1)
        self.assertEqual(self.inventory.snapshot()[0].source,str(source))


class IncrementalRefreshTests(TestCase):
    """Rows are read again only when their files change; no full scan."""

    def test_only_rows_whose_files_changed_are_read_again(self):
        from retrorecomp.compiled_games import refresh_changed, watch_signature
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            exe = root / 'Game.exe'
            exe.write_bytes(b'MZ game')
            identity = 'a' * 64
            inventory = Inventory(root / 'datas/compiled-games.json')
            inventory.remember(Game(str(exe), 'gb', identity, 'Game'))
            def read(game, preferences=None):
                game.watch = watch_signature(game)
                return game
            with patch('retrorecomp.library.library_root', return_value=root / 'library'), \
                    patch('retrorecomp.compiled_games.refresh', side_effect=read) as reader:
                self.assertEqual(refresh_changed(inventory), 1)
                self.assertEqual(refresh_changed(inventory), 0)
                # A game closed after play: its hints file appears beside it.
                hints = root / 'datas/fallbacks' / f'gb-{identity}.rrfb'
                hints.parent.mkdir(parents=True)
                hints.write_bytes(b'saved on exit')
                self.assertEqual(refresh_changed(inventory), 1)
                self.assertEqual(refresh_changed(inventory), 0)
                self.assertEqual(reader.call_count, 2)
