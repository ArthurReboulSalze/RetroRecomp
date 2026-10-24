"""Export receipts are content based, never filename/size based."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from retrorecomp import __version__
from retrorecomp.batch import identify, convert_batch
from retrorecomp.feedback import ingest, encode, Observation


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.output=self.root/'Games'
        rom=self.root/'Authored.sms';rom.write_bytes(bytes(8192));self.item=identify(rom)
        for name,value in [('retrorecomp.publishing.compact_executable',None),
                           ('retrorecomp.paths.load_preferences',{}),
                           ('retrorecomp.cover_settings.load_settings',{}),
                           ('retrorecomp.library.library_root',self.root/'bank')]:
            mocked=patch(name,return_value=value);mocked.start();self.addCleanup(mocked.stop)
        mocked=patch('retrorecomp.systems.master_system.MasterSystemProfile.convert',side_effect=self.compiler)
        self.compiler_mock=mocked.start();self.addCleanup(mocked.stop)

    def compiler(self,path,*,output,title,**options):
        output.mkdir(parents=True,exist_ok=True);exe=output/'build.exe';exe.write_bytes(b'authored executable')
        report={'version':__version__,'rom':{'name':path.name},'executable':exe.name,
            'runtime_feedback':ingest(self.item.system,self.item.sha256,output),
            'final_checks':[{'interpreter_percent':0}]}
        (output/'conversion-report.json').write_text(json.dumps(report));return exe

    def run_batch(self,**options):
        return convert_batch([self.item],self.output,emit=lambda _:None,**options)['games'][0]

    def test_unchanged_export_is_skipped_but_force_and_options_invalidate(self):
        self.assertEqual(self.run_batch()['status'],'success')
        self.assertEqual(self.run_batch()['status'],'current')
        self.assertEqual(self.compiler_mock.call_count,1)
        self.assertEqual(self.run_batch(force=True)['status'],'success')
        self.assertEqual(self.run_batch(frames=7200)['status'],'success')

    def test_new_hints_trigger_once_even_if_old_file_remains(self):
        self.run_batch();folder=self.output/'Master System/datas/fallbacks';folder.mkdir(parents=True)
        file=folder/f'sms-{self.item.sha256}.rrfb'
        file.write_bytes(encode([Observation(1,0x1234,0,b'\x01')],'sms',self.item.sha256))
        self.assertEqual(self.run_batch()['status'],'success')
        self.assertEqual(self.run_batch()['status'],'current')
        file.unlink()
        self.assertEqual(self.run_batch()['status'],'current') # converter retains it

    def test_modified_missing_or_older_binary_receipt_never_skips(self):
        result=self.run_batch();target=Path(result['executable']);target.write_bytes(b'changed')
        self.assertEqual(self.run_batch()['status'],'success')
        target.unlink();self.assertEqual(self.run_batch()['status'],'success')
        report_path=Path(result['report']);report=json.loads(report_path.read_text());report['export_receipt']['schema']=0
        report_path.write_text(json.dumps(report));self.assertEqual(self.run_batch()['status'],'success')

    def test_ui_only_release_keeps_matching_console_receipts(self):
        result=self.run_batch();report_path=Path(result['report'])
        report=json.loads(report_path.read_text());self.assertEqual(report['export_receipt']['schema'],3)
        report['version']='1.1.0';report_path.write_text(json.dumps(report))
        self.assertEqual(self.run_batch()['status'],'current')
        # Old version-based receipts have no independently verified console stamp.
        report['export_receipt']['schema']=1;report_path.write_text(json.dumps(report))
        self.assertEqual(self.run_batch()['status'],'success')

    def test_gameboy_uses_console_scoped_receipts_too(self):
        rom=self.root/'Authored.gb';rom.write_bytes(bytes(32768));self.item=identify(rom)
        with patch('retrorecomp.systems.game_boy.GameBoyProfile.convert',side_effect=self.compiler) as compiler:
            result=self.run_batch();self.assertEqual(result['status'],'success')
            path=Path(result['report']);report=json.loads(path.read_text());report['version']='1.1.0'
            self.assertEqual(report['export_receipt']['schema'],3);path.write_text(json.dumps(report))
            self.assertEqual(self.run_batch()['status'],'current');self.assertEqual(compiler.call_count,1)
            with patch('retrorecomp.compilation_inputs.role_stamps',return_value={'game':'new-sm83-compiler','host':'h'}):
                self.assertEqual(self.run_batch()['status'],'success')

    def test_host_only_change_upgrades_without_rediscovery(self):
        stamps={'game':'same-game','host':'menus-v1'}
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)):
            self.assertFalse(self.run_batch()['upgraded'])
            stamps['host']='menus-v2'
            result=self.run_batch();self.assertTrue(result['upgraded'])
            options=self.compiler_mock.call_args.kwargs
            self.assertEqual((options['scan_level'],options['passes']),('quick',1))
            report=json.loads(Path(result['report']).read_text())
            self.assertEqual(report['upgrade']['discovery']['scan_level'],'standard')
            self.assertEqual(report['upgrade']['check_level'],'quick')
            self.assertEqual(self.run_batch()['status'],'current')
            # The original discovery is kept across successive upgrades.
            stamps['host']='menus-v3'
            again=json.loads(Path(self.run_batch()['report']).read_text())
            self.assertEqual(again['upgrade']['discovery'],report['upgrade']['discovery'])
            # Game-side inputs changed: full conversion with the chosen level.
            stamps.update(game='new-translator',host='menus-v4')
            self.assertFalse(self.run_batch()['upgraded'])
            self.assertNotIn('scan_level',self.compiler_mock.call_args.kwargs)
            # Forcing from the queue rediscovers; Reconvert (rediscover off) upgrades.
            stamps['host']='menus-v5';self.assertFalse(self.run_batch(force=True)['upgraded'])
            stamps['host']='menus-v6';self.assertTrue(self.run_batch(force=True,rediscover=False)['upgraded'])

    def test_build_only_change_upgrades_without_rediscovery(self):
        stamps={'game':'same-game','host':'menus-v1','build':'tools-v1'}
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)):
            self.assertFalse(self.run_batch()['upgraded'])
            self.assertEqual(self.run_batch()['status'],'current')
            stamps['build']='tools-v2'
            result=self.run_batch();self.assertTrue(result['upgraded'])
            self.assertEqual(self.compiler_mock.call_args.kwargs['scan_level'],'quick')
            self.assertNotIn('from_release',json.loads(Path(result['report']).read_text())['upgrade'])

    def test_build_inputs_are_a_third_role_beside_game_and_host(self):
        from retrorecomp import compilation_inputs as inputs
        self.assertEqual(inputs.role('retrorecomp.toolchain'),'build')
        self.assertEqual(inputs.role('retrorecomp.platforms'),'game')
        self.assertEqual(inputs.role('retrorecomp.metadata'),'host')
        self.assertEqual(set(inputs.role_stamps('sms')),{'game','host','build'})

    def legacy_setup(self):
        """An export written by an earlier release, whose game stamp is now listed as equivalent."""
        stamps={'game':'release-1.4.1-game','host':'shell','build':'visual-studio'}
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)):
            first=self.run_batch()
        self.assertEqual(first['status'],'success')
        stamps.update(game='release-1.5.0-game',build='portable-tools')
        return stamps,first

    def test_listed_legacy_game_stamp_is_always_rebuilt_never_current(self):
        stamps,first=self.legacy_setup()
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)), \
                patch.dict('retrorecomp.compilation_inputs.LEGACY_GAME_STAMPS',{'sms':('release-1.4.1-game',)}):
            result=self.run_batch()
            self.assertEqual((result['status'],result['upgraded']),('success',True))
            options=self.compiler_mock.call_args.kwargs
            self.assertEqual((options['scan_level'],options['passes']),('quick',1))
            upgrade=json.loads(Path(result['report']).read_text())['upgrade']
            self.assertEqual(upgrade['from_release'],__version__)
            self.assertIn('listed as equivalent',upgrade['reason'])
            self.assertEqual(self.run_batch()['status'],'current')   # now written by this release

    def test_unlisted_game_stamp_still_means_a_full_conversion(self):
        stamps,first=self.legacy_setup()
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)), \
                patch.dict('retrorecomp.compilation_inputs.LEGACY_GAME_STAMPS',{'sms':('another-release',),'gb':('release-1.4.1-game',)}):
            result=self.run_batch()
            self.assertEqual((result['status'],result['upgraded']),('success',False))
            self.assertNotIn('scan_level',self.compiler_mock.call_args.kwargs)

    def test_legacy_upgrade_that_does_not_pass_falls_back_to_a_full_conversion(self):
        from retrorecomp.core import ConversionError
        stamps,first=self.legacy_setup()
        messages=[];calls=[];real=self.compiler
        def convert(path,**options):
            calls.append(dict(options))
            if options.get('scan_level')=='quick':
                raise ConversionError('Native and reference CPU diverged after 12 frames.\nmore detail')
            return real(path,**options)
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)), \
                patch.dict('retrorecomp.compilation_inputs.LEGACY_GAME_STAMPS',{'sms':('release-1.4.1-game',)}), \
                patch('retrorecomp.systems.master_system.MasterSystemProfile.convert',side_effect=convert):
            result=convert_batch([self.item],self.output,emit=messages.append)['games'][0]
        self.assertEqual((result['status'],result['upgraded']),('success',False))
        self.assertEqual([call.get('scan_level') for call in calls],['quick',None])
        text='\n'.join(messages)
        self.assertIn('did not pass its checks',text);self.assertIn('Native and reference CPU diverged after 12 frames.',text)
        self.assertIn('converting the game in full instead',text);self.assertNotIn('more detail',text)
        report=json.loads(Path(result['report']).read_text())
        self.assertNotIn('upgrade',report)                       # a full conversion, not an inherited one
        self.assertEqual(Path(result['executable']).read_bytes(),b'authored executable')

    def test_failed_legacy_upgrade_and_failed_full_conversion_keep_the_earlier_export(self):
        from retrorecomp.core import ConversionError
        stamps,first=self.legacy_setup()
        target=Path(first['executable']);target.write_bytes(b'working 1.4.1 export')
        # The receipt hashes the executable: write it back so the export is still its own.
        report_path=Path(first['report']);report=json.loads(report_path.read_text())
        from retrorecomp.freshness import digest
        report['export_receipt']['sha256']=digest(target);report_path.write_text(json.dumps(report))
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)), \
                patch.dict('retrorecomp.compilation_inputs.LEGACY_GAME_STAMPS',{'sms':('release-1.4.1-game',)}), \
                patch('retrorecomp.systems.master_system.MasterSystemProfile.convert',
                      side_effect=ConversionError('compiler stopped')):
            result=convert_batch([self.item],self.output,emit=lambda _:None)['games'][0]
        self.assertEqual(result['status'],'error')
        self.assertEqual(target.read_bytes(),b'working 1.4.1 export')

    def test_new_hints_or_other_settings_never_upgrade(self):
        stamps={'game':'same-game','host':'menus-v1'}
        with patch('retrorecomp.compilation_inputs.role_stamps',side_effect=lambda system:dict(stamps)):
            self.run_batch();stamps['host']='menus-v2'
            folder=self.output/'Master System/datas/fallbacks';folder.mkdir(parents=True)
            (folder/f'sms-{self.item.sha256}.rrfb').write_bytes(
                encode([Observation(1,0x1234,0,b'\x01')],'sms',self.item.sha256))
            self.assertFalse(self.run_batch()['upgraded'])
            stamps['host']='menus-v3'
            self.assertFalse(self.run_batch(frames=7200)['upgraded'])

    def test_upgraded_export_still_reports_inherited_fallback(self):
        from retrorecomp.compiled_games import game_from_report
        folder=self.root/'Console/datas/reports/game';folder.mkdir(parents=True)
        report={'tool':'Retro-Recomp','system':{'id':'sms'},'rom':{'sha256':self.item.sha256},
                'executable':'Game.exe','final_checks':[{'interpreter_percent':0}],
                'upgrade':{'discovery':{'final_checks':[{'interpreter_cycles':42}]}}}
        (folder/'conversion-report.json').write_text(json.dumps(report))
        self.assertTrue(game_from_report(folder/'conversion-report.json').tested_fallback)

    def test_overwrite_off_still_protects_stale_exports(self):
        result=self.run_batch();Path(result['executable']).write_bytes(b'old kept')
        self.assertEqual(self.run_batch(overwrite=False,force=True)['status'],'existing')
        self.assertEqual(Path(result['executable']).read_bytes(),b'old kept')

    def test_corrected_cover_reference_invalidates_only_automatic_artwork(self):
        with patch('retrorecomp.cover_references.find',return_value=None) as reference:
            self.run_batch()
            self.assertEqual(self.run_batch()['status'],'current')
            reference.return_value={'revision':'reviewed-front-v1'}
            self.assertEqual(self.run_batch()['status'],'success')
            self.assertEqual(self.run_batch()['status'],'current')
            reference.return_value={'revision':'reviewed-front-v2'}
            self.assertEqual(self.run_batch()['status'],'success')
            self.item.cover=self.root/'selected.png';self.item.cover.write_bytes(b'explicit cover')
            self.run_batch()
            reference.return_value={'revision':'reviewed-front-v3'}
            self.assertEqual(self.run_batch()['status'],'current')


if __name__=='__main__':unittest.main()
