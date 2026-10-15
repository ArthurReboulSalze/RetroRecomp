"""Export receipts are content based, never filename/size based."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from smsrecomp import __version__
from smsrecomp.batch import identify, convert_batch
from smsrecomp.feedback import ingest, encode, Observation


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.output=self.root/'Games'
        rom=self.root/'Authored.sms';rom.write_bytes(bytes(8192));self.item=identify(rom)
        for name,value in [('smsrecomp.publishing.compact_executable',None),
                           ('smsrecomp.paths.load_preferences',{}),
                           ('smsrecomp.cover_settings.load_settings',{}),
                           ('smsrecomp.library.library_root',self.root/'bank')]:
            mocked=patch(name,return_value=value);mocked.start();self.addCleanup(mocked.stop)
        mocked=patch('smsrecomp.systems.master_system.MasterSystemProfile.convert',side_effect=self.compiler)
        self.compiler_mock=mocked.start();self.addCleanup(mocked.stop)

    def compiler(self,path,*,output,title,**options):
        output.mkdir(parents=True,exist_ok=True);exe=output/'build.exe';exe.write_bytes(b'authored executable')
        report={'version':__version__,'rom':{'name':path.name},'executable':exe.name,
            'runtime_feedback':ingest('sms',self.item.sha256,output),
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
        report_path=Path(result['report']);report=json.loads(report_path.read_text());report['version']='0.0.0'
        report_path.write_text(json.dumps(report));self.assertEqual(self.run_batch()['status'],'success')

    def test_overwrite_off_still_protects_stale_exports(self):
        result=self.run_batch();Path(result['executable']).write_bytes(b'old kept')
        self.assertEqual(self.run_batch(overwrite=False,force=True)['status'],'existing')
        self.assertEqual(Path(result['executable']).read_bytes(),b'old kept')


if __name__=='__main__':unittest.main()
