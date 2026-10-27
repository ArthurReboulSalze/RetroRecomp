"""Interrupted conversion recovery does not read ROMs or repeat finished rows."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from retrorecomp.batch import BatchItem
from retrorecomp.queue_state import BatchJournal,recover


class QueueRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.folder=self.root/'queue'
        self.items=[BatchItem(self.root/f'Absent {n}.sms',f'Authored {n}',system='sms',sha256=str(n)*64)
                    for n in range(3)]

    def create(self):
        journal=BatchJournal.create(self.folder,self.items,self.root/'Games')
        self.addCleanup(journal.close);return journal

    def test_active_queue_cannot_be_recovered_by_a_second_instance(self):
        journal=self.create();self.assertIsNone(recover(self.folder))
        journal.close();restored=recover(self.folder);self.assertIsNotNone(restored);restored.close()

    def test_completed_rows_are_skipped_and_active_rows_resume_after_restart(self):
        journal=self.create();journal.result(0,{'status':'success'});journal.result(2,{'status':'error'})
        journal.close()
        # No source ROM exists; restoration must not contact its disk or share.
        with patch.object(Path,'read_bytes',side_effect=AssertionError('ROM opened')):
            restored=recover(self.folder)
            self.assertEqual(restored.pending_items(),[self.items[1]])
            self.assertEqual(restored.definition['output'],str(self.root/'Games'))
            restored.close()

    def test_clean_finish_and_explicit_discard_are_not_restored(self):
        journal=self.create();journal.finish({'pending':0});self.assertIsNone(recover(self.folder))
        journal=self.create();journal.discard();self.assertIsNone(recover(self.folder))

    def test_x68_and_cps1_rows_recover_and_unknown_consoles_stay_refused(self):
        items=[BatchItem(self.root/'Absent.dim','X68000 game',system='x68',sha256=str(7)*64),
               BatchItem(self.root/'Absent.zip','CPS-1 game',system='cps1',sha256=str(8)*64)]
        journal=BatchJournal.create(self.folder,items,self.root/'Games');journal.close()
        restored=recover(self.folder);self.assertEqual(restored.pending_items(),items);restored.close()
        definition=json.loads(journal.path.read_text());definition['items'][0]['system']='gamecube'
        journal.path.write_text(json.dumps(definition))
        self.assertIsNone(recover(self.folder))

    def test_completed_or_active_newer_batch_does_not_hide_older_unfinished_rows(self):
        old=self.create();old.result(0,{'status':'success'});old.close()
        newer=self.create()
        for finished in (False,True):
            if finished:newer.finish({'pending':0})
            restored=recover(self.folder);self.assertEqual(restored.path,old.path)
            self.assertEqual(restored.pending_items(),self.items[1:]);restored.close()

    def test_stop_after_active_tasks_keeps_only_unfinished_rows(self):
        journal=self.create();journal.result(0,{'status':'success'});journal.finish({'pending':2})
        restored=recover(self.folder);self.assertEqual(restored.pending_items(),self.items[1:]);restored.close()

    def test_corrupt_foreign_and_oversized_files_are_ignored(self):
        journal=self.create();journal.close()
        definition=json.loads(journal.path.read_text());definition['target']='foreign-architecture'
        journal.path.write_text(json.dumps(definition));self.assertIsNone(recover(self.folder))
        journal.path.write_text('{broken');self.assertIsNone(recover(self.folder))
        with patch('retrorecomp.queue_state.MAX_BYTES',4):self.assertIsNone(recover(self.folder))

    def test_definition_is_unchanged_while_small_checkpoints_advance(self):
        journal=self.create();before=journal.path.read_bytes()
        journal.result(1,{'status':'current','private_metadata':'not persisted'})
        self.assertEqual(before,journal.path.read_bytes())
        self.assertEqual(json.loads(journal.progress.read_text())['done'],{'1':'current'})


if __name__=='__main__':unittest.main()
