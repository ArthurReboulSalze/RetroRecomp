"""Close/reopen the real hidden converter around an interrupted authored queue."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from queue import Empty
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.batch import BatchItem
from smsrecomp.gui import Application
from smsrecomp.queue_state import BatchJournal


def main():
    with tempfile.TemporaryDirectory(prefix='rr-queue-ui-') as temporary:
        root=Path(temporary).resolve();data=root/'datas'
        items=[BatchItem(root/f'Authored {i}.sms',f'Authored {i}',system='sms',sha256=str(i)*64,size=8192)
               for i in range(2)]
        journal=BatchJournal.create(data/'pending-batches',items,root/'Games')
        journal.result(0,{'status':'success'});journal.close() # model process exit without finish
        with patch('smsrecomp.gui.data_directory',return_value=data), \
                patch('smsrecomp.gui.load_preferences',return_value={}), \
                patch('smsrecomp.gui.save_preferences'):
            for reopening in range(3):
                window=tk.Tk();window.withdraw();application=Application(window)
                try:
                    restored=application.restore_queue()
                    if reopening<2:
                        assert restored and list(application.items.values())==[items[1]],reopening
                        assert application.output.get()==str(root/'Games')
                        assert not application.busy and not application.running_jobs
                        window.update_idletasks()
                        if reopening==1:
                            application.table.selection_set(application.table.get_children())
                            application.remove_selected();assert not application.items
                    else:assert not restored and not application.items
                finally:application.close()
        assert not any(root.glob('*.sms')), 'Recovery must not create or read a source ROM'
        journal=BatchJournal.create(data/'pending-batches',items,root/'Games');journal.close()
        with patch('smsrecomp.gui.data_directory',return_value=data), \
                patch('smsrecomp.gui.load_preferences',return_value={}), \
                patch('smsrecomp.gui.save_preferences'):
            window=tk.Tk();window.withdraw();application=Application(window)
            try:
                assert application.restore_queue()
                application.table.selection_set(application.table.get_children()[0])
                def convert(selected,*args,on_event,**kwargs):
                    assert selected==[items[0]]
                    on_event('result',0,{'status':'current'})
                    return {'pending':0,'games':[]}
                with patch('smsrecomp.gui.convert_batch',side_effect=convert):
                    application.start(selected=True)
                    deadline=time.monotonic()+10
                    while True:
                        try:event=application.messages.get(timeout=0.2)
                        except Empty:
                            if time.monotonic()>deadline:raise AssertionError('Selected recovery worker did not finish')
                            continue
                        assert event[0]!='fatal',event
                        if event[0]=='done':break
                assert application.recovered_batch.pending_items()==[items[1]]
                application.busy=False
            finally:application.close()
            window=tk.Tk();window.withdraw();application=Application(window)
            try:
                assert application.restore_queue() and list(application.items.values())==[items[1]]
                application.clear()
            finally:application.close()
            window=tk.Tk();window.withdraw();application=Application(window)
            try:assert not application.restore_queue()
            finally:application.close()
    print('PASS: interrupted rows survive fresh Tk windows; selected-only resume retains other rows; remove/clear stay retired; no real conversion starts.')


if __name__=='__main__':main()
