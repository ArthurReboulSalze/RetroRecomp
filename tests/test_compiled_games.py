from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from unittest import TestCase
from unittest.mock import patch
from unittest.mock import Mock
from threading import Event, Lock
from queue import Queue

from smsrecomp.compiled_games import Inventory, Game, game_from_report, refresh, scan
from smsrecomp.feedback import Observation, encode
from smsrecomp.memory_view import summaries


class CompiledGamesTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
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
        with patch('smsrecomp.compiled_games.scan',side_effect=AssertionError('No startup scan')):
            restored = Inventory(self.inventory.path)
        self.assertEqual([asdict(g) for g in restored.snapshot()],[asdict(game)])
        self.assertEqual(restored.roots,self.inventory.roots)

    def test_scan_never_runs_executables_and_keeps_missing_entries(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Never run a scanned binary')):
            count = scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(count,1)
        game = self.inventory.snapshot()[0]
        self.assertEqual(game.status,'no_hints')
        self.exe.unlink()
        scan(self.inventory,[self.root/'Games'],{})
        self.assertEqual(game.status,'missing')
        self.assertEqual(Inventory(self.inventory.path).snapshot()[0].status,'missing')

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
        from smsrecomp.gui import Application
        from smsrecomp.batch import BatchItem
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
        from smsrecomp.platforms import target_id
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
        with patch('smsrecomp.gui.identify',return_value=item), \
             patch('smsrecomp.batch._convert_in_budget',side_effect=convert) as compiler:
            owner.begin_reconvert([(game,source),(second,source)])
            while True:
                event=owner.messages.get(timeout=10)
                if event[0]=='collection_done':break
            self.assertEqual(event,('collection_done',{'success':2,'failed':0}))
        self.assertEqual(compiler.call_count,2)
        self.assertEqual(maximum,1)
        self.assertEqual(self.inventory.snapshot()[0].source,str(source))
