"""Check that the desktop form initializes with a ROM without showing a window."""
from pathlib import Path
import json
import os
import sys
import tkinter as tk
from tkinter import ttk
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The check never reaches the online service: the account corner stays signed out.
os.environ['RETRO_RECOMP_SERVICE'] = ''
from retrorecomp.gui import launch, PROFILES
from retrorecomp.library import library_root, list_games
from retrorecomp.gameboy import list_memory
from retrorecomp.nes import list_memory as list_nes_memory
from retrorecomp.neogeo_knowledge import list_memory as list_ng_memory
from retrorecomp.cover_settings import defaults as cover_defaults
from retrorecomp.languages import LANGUAGES, LANGUAGE_NAMES


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
    # A game already compiled in the output folder is offered for removal
    # once the whole addition is in; No leaves it out, Yes keeps it.
    from retrorecomp.batch import identify, system_output
    output = Path(fixtures.name) / 'out'
    compiled = Path(fixtures.name) / 'Synthetic compiled (Europe).sms'
    compiled.write_bytes(bytes([9]) * 8192)
    item = identify(compiled, 'sms')
    folder = system_output(output, item.system)
    (folder / 'datas/reports' / item.key).mkdir(parents=True)
    (folder / 'Synthetic compiled.exe').write_bytes(b'MZ')
    (folder / 'datas/reports' / item.key / 'conversion-report.json').write_text(json.dumps(
        {'executable': 'Synthetic compiled.exe', 'rom': {'sha256': item.sha256}, 'final_checks': [],
         'status': 'converted'}), encoding='utf-8')
    application.output.set(str(output))
    with patch.object(application.app, 'winfo_viewable', return_value=True), \
            patch.object(application, 'confirm_compiled', return_value=False) as asked:
        application.add_paths([compiled])
    assert asked.call_args.args == (1, 'Synthetic compiled'), asked.call_args
    assert compiled.resolve() not in {i.path for i in application.items.values()}
    with patch.object(application.app, 'winfo_viewable', return_value=True), \
            patch.object(application, 'confirm_compiled', return_value=True):
        application.add_paths([compiled])
    kept = [row for row, i in application.items.items() if i.path == compiled.resolve()]
    assert len(kept) == 1 and application.row_status[kept[0]] == 'created', kept
    application.remove_selected()
    # The two disks of one X68000 game make one row, from a playlist written
    # outside the disks' folder.
    if any(profile.id == 'x68' for profile in PROFILES):
        disks = Path(fixtures.name) / 'x68000'
        disks.mkdir()
        for number in (1, 2):
            (disks / f'Synthetic (Disk {number} of 2).dim').write_bytes(
                bytes([0, 1]) + bytes(254) + bytes([number]) * 8192)
        with patch('retrorecomp.rom_sources.data_directory', return_value=Path(fixtures.name) / 'datas'):
            application.add_paths([disks])
        added = [item for item in application.items.values() if item.system == 'x68']
        assert len(added) == 1 and added[0].path.suffix == '.m3u' and added[0].title == 'Synthetic', added
        assert added[0].path.is_relative_to(Path(fixtures.name) / 'datas/x68000-sets')
        assert sorted(p.name for p in disks.iterdir()) == ['Synthetic (Disk 1 of 2).dim', 'Synthetic (Disk 2 of 2).dim']
        before = len(application.items)
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
    # The version and platform sit in the footer; the header's right end is
    # the player's corner, which waits for the online service.
    assert application.version_label.cget('text').endswith(('Windows version', 'Linux version'))
    assert application.version_label.master is application.tagline.master
    assert application.header.itemcget(application.player_name, 'text') == application.tr('account_not_signed')
    assert str(application.sign_in_button.cget('state')) == 'disabled'
    assert application.help_button.winfo_manager() == 'pack'
    application.show_help()
    help_page = [w for w in window.winfo_children() if w.winfo_class() == 'Toplevel'][-1]
    help_page.destroy()
    application.render_player({'account': {'email': 'pat@example.test'}, 'profile': {'pseudonym': 'Pat'},
                               'board': {'you': {'rank': 3, 'total': 42, 'pending': 2}}})
    assert application.header.itemcget(application.player_name, 'text') == 'Pat'
    assert application.header.itemcget(application.player_score, 'text') == (
        application.tr('account_points', points=42, rank=3) + '\n' + application.tr('account_pending', count=2))
    application.render_player(None)
    assert application.header.itemcget(application.player_name, 'text') == application.tr('account_not_signed')
    initial_tags = application.icon_tags.get()
    assert application.preferences()['icon_tags'] == initial_tags
    initial_deep = application.gb_deep_validation.get()
    assert application.preferences()['gb_deep_validation'] == initial_deep
    initial_md_scan = application.scan_level['md'].get()
    assert application.preferences()['console_scan'].get('md', {}).get('level', 'standard') == initial_md_scan
    application.show_options()
    options_panel = application.options_panel
    notebook = next(widget for widget in options_panel.winfo_children() if widget.winfo_class() == 'TNotebook')
    # Nine pages, plus the X68000 and CPS-1 pages when available.
    assert 9 <= len(notebook.tabs()) <= 11
    assert notebook.tab(0, 'text') == application.tr('options_common')
    assert notebook.tab(7, 'text') == application.tr('options_ng')
    assert notebook.tab(len(notebook.tabs()) - 1, 'text') == application.tr('options_boxart')
    assert application.preferences()['ng_bios'] == application.ng_bios.get()
    assert set(application.feedback_paths) >= {'sms','gg','gb','nes','md','snes','ng'}
    before_feedback=application.feedback_paths['sms'].get()
    application.feedback_paths['sms'].set(str(fixtures.name))
    assert application.preferences()['feedback_paths']['sms'] == str(fixtures.name)
    application.feedback_paths['sms'].set(before_feedback)
    assert set(application.feedback_import_buttons) == set(application.feedback_paths)
    report = dict(files=1,games=1,updated_games=1,observations=3,invalid_files=0,bytes=192)
    with patch('retrorecomp.feedback.import_saved_feedback',return_value=report) as recover:
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
    application.scan_level['md'].set('thorough' if initial_md_scan != 'thorough' else 'quick')
    assert application.preferences()['console_scan']['md']['level'] != initial_md_scan
    application.scan_level['md'].set(initial_md_scan)
    assert application.preferences()['console_scan'].get('md', {}).get('level', 'standard') == initial_md_scan
    application.icon_tags_control.invoke()
    assert application.preferences()['icon_tags'] != initial_tags
    application.icon_tags_control.invoke()
    assert application.preferences()['icon_tags'] == initial_tags
    application.set_controls(False)
    assert str(application.gb_deep_control.cget('state')) == 'disabled'
    application.set_controls(True)
    assert str(application.gb_deep_control.cget('state')) == 'normal'
    with patch('retrorecomp.gui.save_preferences'):
        application.close_options()
    assert application.options_panel is None
    assert len(application.tooltips) >= 10
    # The queue/collection switch stays first with one width; each view brings
    # its own buttons, and the knowledge menu stays in both.
    toolbar_slaves = lambda: application.toolbar.pack_slaves()
    switch_width = application.compiled_button.cget('width')
    assert toolbar_slaves()[0] is application.compiled_button
    assert application.queue_actions.winfo_manager() and not application.collection_actions.winfo_manager()
    with patch('retrorecomp.compiled_games_view.CompiledGamesView.scan'):
        application.toggle_compiled_games()
    window.update_idletasks()
    assert toolbar_slaves()[0] is application.compiled_button
    assert application.compiled_button.cget('text') == application.tr('conversion_queue')
    assert application.compiled_button.cget('width') == switch_width
    assert application.collection_actions.winfo_manager() and not application.queue_actions.winfo_manager()
    assert application.knowledge_button in toolbar_slaves()
    application.compiled_view.show_log('first line\nsecond line\nthird line ' + 'x' * 200)
    assert application.compiled_view.log_text.get().splitlines()[0] == 'second line'
    assert len(application.compiled_view.log_text.get().splitlines()[1]) == 150
    application.compiled_view.clear_log()
    assert not application.compiled_view.log_label.winfo_manager()
    application.toggle_compiled_games()
    window.update_idletasks()
    assert toolbar_slaves()[0] is application.compiled_button
    assert application.compiled_button.cget('text') == application.tr('compiled_games')
    assert application.queue_actions.winfo_manager() and not application.collection_actions.winfo_manager()
    assert application.knowledge_button in toolbar_slaves()
    # Discoveries are counted before choosing a file; nothing new means a
    # message only, never a save dialog or an import.
    omitted = dict(already_known=2, missing_rom=0, unqualified=1, ram_without_rom_source=0)
    with patch('retrorecomp.gui.messagebox.showinfo') as info, \
            patch('retrorecomp.gui.filedialog.asksaveasfilename') as save:
        application.knowledge_done(('collect', dict(games=0, consoles={}, discoveries=0, omitted=omitted)), None)
        assert info.called and not save.called
    with patch.object(application, 'achievement', return_value=False) as card, \
            patch('retrorecomp.gui.filedialog.asksaveasfilename') as save:
        application.knowledge_done(('collect', dict(games=2, consoles={'md': 2}, discoveries=9, omitted=omitted)), None)
        assert card.call_args.args[0] == 9 and not save.called
    # The closing card opens, animates and cancels.
    window.after(400, lambda: next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel)).destroy())
    assert application.closing_card(3, 42) is None
    # Closing offers it when games have new paths; the button counts them.
    from retrorecomp.compiled_games import Game
    fresh = [Game(str(Path(fixtures.name) / 'New.exe'), 'gb', 'b' * 64, 'New paths', status='new_hints')]
    with patch.object(application.compiled_inventory, 'snapshot', return_value=fresh), \
            patch('retrorecomp.compiled_games.refresh_changed', return_value=0):
        application.update_new_paths()
        assert application.new_paths_buttons and all(
            str(b.cget('state')) == 'normal' and '(1)' in b.cget('text') for b in application.new_paths_buttons)
        with patch.object(application, 'closing_card', return_value=None):
            assert application.offer_closing_card() is True and not application.closing_checked
        with patch.object(application, 'closing_card', return_value='skip'):
            assert application.offer_closing_card() is False
        with patch.object(application, 'closing_card', return_value='recompile'), \
                patch.object(application, 'reconvert_games') as reconvert:
            assert application.offer_closing_card() is True
            assert reconvert.call_args.args[0] == fresh and application.close_when_idle
        with patch.object(application, 'closing_card', return_value='send'), \
                patch.object(application, 'send_knowledge') as send:
            application.closing_checked = False
            assert application.offer_closing_card() is True and send.call_args.kwargs == {'closing': True}
    # Sending: only games not yet sent with the account, after the card.
    application.closing_send = False
    pending = dict(games=1, consoles={'gb': 1}, discoveries=4, observations={}, titles={}, payload={})
    with patch('retrorecomp.online.pending', return_value=pending), \
            patch.object(application, 'achievement', return_value=True) as card, \
            patch.object(application, 'knowledge_task') as task:
        application.knowledge_done(('send_collect', dict(games=1)), None)
        assert card.call_args.args[0] == 4 and card.call_args.args[2] == application.tr('knowledge_send_action')
        assert task.called
    with patch('retrorecomp.online.pending', return_value=dict(pending, games=0)), \
            patch('retrorecomp.gui.messagebox.showinfo') as info, patch.object(application, 'achievement') as card:
        application.knowledge_done(('send_collect', dict(games=0)), None)
        assert info.call_args.args[1] == application.tr('knowledge_send_none') and not card.called
    with patch('retrorecomp.gui.messagebox.showinfo') as info:
        application.knowledge_done(('sent', {'error': application.tr('online_unreachable')}), None)
        assert info.call_args.args[1] == application.tr('online_unreachable')
    # The sign-in dialog opens on the e-mail step and cancels.
    window.after(400, lambda: next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel)).destroy())
    assert application.sign_in_dialog() is False
    application.closing_checked = application.closing_after_recompile = application.close_when_idle = False
    application.skip_missing_sources = False
    if application.collection_visible:
        application.toggle_compiled_games()
    application.update_new_paths()
    assert all(str(b.cget('state')) == 'disabled' for b in application.new_paths_buttons)
    with patch('retrorecomp.gui.messagebox.showinfo') as info, patch.object(application, 'achievement') as card:
        application.knowledge_done(('preview', (Path('shared.rrknowledge'),
                                                dict(games=0, discoveries=0, consoles={}))), None)
        assert info.called and not card.called
    application.memory_button.invoke()
    panel = next(widget for widget in window.winfo_children() if isinstance(widget, tk.Toplevel))
    panel.withdraw()
    table = next(widget for widget in descendants(panel) if widget.winfo_class() == "Treeview")
    # Game Memory intentionally loads one console asynchronously. Its first
    # page must not parse the entire GB/Neo Geo libraries just to open a dialog.
    from retrorecomp.memory_view import summaries
    expected=len(summaries('sms')[0])
    deadline=time.monotonic()+10
    while len(table.get_children())!=expected and time.monotonic()<deadline:
        window.update();time.sleep(.01)
    assert len(table.get_children())==expected
    old_output = application.output.get()
    with tempfile.TemporaryDirectory() as folder, patch('retrorecomp.gui.save_preferences') as save:
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
        with patch('retrorecomp.gui.convert_batch',side_effect=selected_batch), patch('retrorecomp.gui.save_preferences'):
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
        assert open_notebook.tab(len(open_notebook.tabs()) - 1, 'text') == application.tr('options_boxart')
        assert application.compiled_button.cget('text') == application.tr('compiled_games')
        assert application.knowledge_button.cget('text') == application.tr('knowledge') + ' ▾'
        window.update_idletasks()
        assert (application.frames.get(), application.passes.get()) == initial_tuning
    application.close_options()
    panel.destroy()
    print("PASS: eight languages, platform label, extended default, hover hints, batch queue, banner, duplicates, library; size", window.geometry())
    window.destroy()
    fixtures.cleanup()


tk.Tk.mainloop = smoke
with tempfile.TemporaryDirectory() as queue_folder, \
        patch('retrorecomp.gui.data_directory',return_value=Path(queue_folder)), \
        patch('retrorecomp.compiled_games.data_directory',return_value=Path(queue_folder)), \
        patch('retrorecomp.gui.load_preferences', return_value={'language': 'en', 'system_mode': 'auto'}), \
        patch('retrorecomp.gui.load_cover_settings', side_effect=cover_defaults), \
        patch('retrorecomp.gui.save_cover_settings'), \
        patch('retrorecomp.gui.save_preferences'):
    launch()
