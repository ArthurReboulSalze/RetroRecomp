"""Check that the desktop form initializes with a ROM without showing a window."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.gui import launch
from smsrecomp.library import library_root, list_games
from smsrecomp.gameboy import list_memory
from smsrecomp.nes import list_memory as list_nes_memory
from smsrecomp.neogeo_knowledge import list_memory as list_ng_memory
from smsrecomp.cover_settings import defaults as cover_defaults
from smsrecomp.languages import LANGUAGES, LANGUAGE_NAMES


def smoke(window):
    window.withdraw()
    window.update_idletasks()
    assert window.title() == "Retro-Recomp"
    application = window._retro_application
    # The check must not depend on a user's local ROM collection or queue.
    fixtures = tempfile.TemporaryDirectory()
    for number in range(5):
        path = Path(fixtures.name) / f'Synthetic {number} (Europe).sms'
        path.write_bytes(bytes([number + 1]) * 8192)
    application.add_paths(Path(fixtures.name).glob('*.sms'))
    assert len(application.items) == len(list(application.table.get_children())) >= 5
    assert 'system' in application.table['columns'] and 'video' in application.table['columns']
    assert application.body.grid_rowconfigure(1)['weight'] == 4
    assert application.body.grid_rowconfigure(7)['weight'] == 2
    assert application.banner is not None
    assert application.banner.width() <= 600 and application.banner.height() < 175
    banner_items = application.header.find_withtag('banner')
    assert len(banner_items) == 1
    assert application.header.coords(banner_items[0]) == [24.0, 0.0]
    assert application.tagline.master is application.footer_label.master
    initial_tuning = application.frames.get(), application.passes.get()
    before = len(application.items)
    application.add_paths([item.path for item in application.items.values()])
    assert len(application.items) == before
    row = application.table.get_children()[0]
    application.table.selection_set(row)
    application.selection_changed()
    assert str(application.video_field.cget('state')) == 'readonly'
    application.video_name.set('PAL')
    application.change_video()
    assert application.items[row].standard_override == 'pal'
    assert 'PAL' in application.table.set(row, 'video')
    application.video_name.set(application.tr('auto'))
    application.change_video()
    assert application.items[row].standard_override is None
    content = window
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    assert application.language in LANGUAGES and application.extended.get()
    assert application.header.itemcget(application.platform_text,'text') in ('Windows version','Linux version')
    initial_tags = application.icon_tags.get()
    assert application.preferences()['icon_tags'] == initial_tags
    initial_deep = application.gb_deep_validation.get()
    assert application.preferences()['gb_deep_validation'] == initial_deep
    initial_md_scan = application.md_advanced_scan.get()
    assert application.preferences()['md_advanced_scan'] == initial_md_scan
    application.show_options()
    options_panel = application.options_panel
    notebook = next(widget for widget in options_panel.winfo_children() if widget.winfo_class() == 'TNotebook')
    assert len(notebook.tabs()) == 9
    assert notebook.tab(0, 'text') == application.tr('options_common')
    assert notebook.tab(7, 'text') == application.tr('options_ng')
    assert notebook.tab(8, 'text') == application.tr('options_boxart')
    assert application.preferences()['ng_bios'] == application.ng_bios.get()
    assert set(application.feedback_paths) == {'sms','gg','gb','nes','md','snes','ng'}
    before_feedback=application.feedback_paths['sms'].get()
    application.feedback_paths['sms'].set(str(fixtures.name))
    assert application.preferences()['feedback_paths']['sms'] == str(fixtures.name)
    application.feedback_paths['sms'].set(before_feedback)
    assert set(application.feedback_import_buttons) == set(application.feedback_paths)
    report = dict(files=1,games=1,updated_games=1,observations=3,invalid_files=0,bytes=192)
    with patch('smsrecomp.feedback.import_saved_feedback',return_value=report) as recover:
        application.feedback_import_buttons['sms'].invoke()
        deadline = time.monotonic()+5
        while application.feedback_importing and time.monotonic()<deadline:
            window.update()
            time.sleep(.01)
        assert not application.feedback_importing
        assert recover.call_args.args[0] == 'sms'
        assert application.feedback_status['sms'].get() == application.tr('feedback_import_summary',**report,kib=192/1024)
        assert str(application.feedback_import_buttons['sms'].cget('state')) == 'normal'
    assert set(application.cover_accounts) == {'screenscraper', 'thegamesdb', 'igdb', 'arcadeitalia'}
    assert not application.cover_3d.get()
    application.gb_deep_control.invoke()
    assert application.preferences()['gb_deep_validation'] != initial_deep
    application.gb_deep_control.invoke()
    assert application.preferences()['gb_deep_validation'] == initial_deep
    application.md_scan_control.invoke()
    assert application.preferences()['md_advanced_scan'] != initial_md_scan
    application.md_scan_control.invoke()
    assert application.preferences()['md_advanced_scan'] == initial_md_scan
    application.icon_tags_control.invoke()
    assert application.preferences()['icon_tags'] != initial_tags
    application.icon_tags_control.invoke()
    assert application.preferences()['icon_tags'] == initial_tags
    application.set_controls(False)
    assert str(application.gb_deep_control.cget('state')) == 'disabled'
    assert str(application.md_scan_control.cget('state')) == 'disabled'
    application.set_controls(True)
    assert str(application.gb_deep_control.cget('state')) == 'normal'
    assert str(application.md_scan_control.cget('state')) == 'normal'
    with patch('smsrecomp.gui.save_preferences'):
        application.close_options()
    assert application.options_panel is None
    assert len(application.tooltips) >= 10
    application.memory_button.invoke()
    panel = next(widget for widget in window.winfo_children() if isinstance(widget, tk.Toplevel))
    panel.withdraw()
    table = next(widget for widget in descendants(panel) if widget.winfo_class() == "Treeview")
    assert len(table.get_children()) == (len(list_games()) + len(list_games(library_root('gg')))
                                         + len(list_memory()) + len(list_nes_memory())
                                         + len(list_ng_memory()))
    old_output = application.output.get()
    with tempfile.TemporaryDirectory() as folder, patch('smsrecomp.gui.save_preferences') as save:
        application.output.set(folder)
        application.language_name.set('Français')
        application.change_language()
        assert save.call_args.args[0]['language'] == 'fr'
        assert not (Path(folder)/'datas').exists()
        assert application.table.heading('title', 'text') == application.tr('game')
        application.language_name.set('English')
        application.change_language()
        assert save.call_args.args[0]['language'] == 'en'
    application.output.set(old_output)
    # Exercise the real selection-to-worker mapping without building fixtures.
    for count in (1, 2):
        selected=list(application.table.get_children())[:count]
        application.table.selection_set(selected);application.selection_changed()
        assert str(application.selected_button.cget('state'))=='normal'
        expected=[application.items[row].path for row in selected]
        def selected_batch(items, output, *, on_event, **kwargs):
            assert [item.path for item in items]==expected
            games=[]
            for index,item in enumerate(items):
                on_event('start',index,item.title)
                result={'status':'current','title':item.title,'executable':str(Path(fixtures.name)/'not-run.exe')}
                games.append(result);on_event('result',index,result)
            return dict(games=games,succeeded=0,current=len(items),existing=0,unrecognized=0,
                        skipped=0,failed=0,duplicates=0,pending=0)
        with patch('smsrecomp.gui.convert_batch',side_effect=selected_batch), patch('smsrecomp.gui.save_preferences'):
            application.selected_button.invoke()
            deadline=time.monotonic()+5
            while application.busy and time.monotonic()<deadline:
                window.update();time.sleep(.01)
            assert not application.busy
            assert application.active_rows==selected
            assert all(application.row_status[row]=='current' for row in selected)
    application.show_options()
    open_notebook = next(widget for widget in application.options_panel.winfo_children()
                         if isinstance(widget, ttk.Notebook))
    for language in (*LANGUAGES[1:], 'en'):
        application.language = language
        application.refresh_language()
        assert application.start_button.cget('text') == application.tr('start')
        assert application.selected_button.cget('text') == application.tr('start_selected')
        assert len(application.items) == before
        assert application.options_button.cget('text') == application.tr('options')
        assert open_notebook.tab(0, 'text') == application.tr('options_common')
        assert open_notebook.tab(8, 'text') == application.tr('options_boxart')
        assert application.options_panel.title() == 'Retro-Recomp - ' + application.tr('options')
        window.update_idletasks()
        assert (application.frames.get(), application.passes.get()) == initial_tuning
    application.close_options()
    panel.destroy()
    print("PASS: eight languages, platform label, extended default, hover hints, batch queue, banner, duplicates, library; size", window.geometry())
    window.destroy()
    fixtures.cleanup()


tk.Tk.mainloop = smoke
with tempfile.TemporaryDirectory() as queue_folder, \
        patch('smsrecomp.gui.data_directory',return_value=Path(queue_folder)), \
        patch('smsrecomp.gui.load_preferences', return_value={'language': 'en', 'system_mode': 'auto'}), \
        patch('smsrecomp.gui.load_cover_settings', side_effect=cover_defaults), \
        patch('smsrecomp.gui.save_cover_settings'), \
        patch('smsrecomp.gui.save_preferences'):
    launch()
