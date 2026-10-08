"""Check that the desktop form initializes with a ROM without showing a window."""
from pathlib import Path
import sys
import tkinter as tk
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.gui import launch
from smsrecomp.library import library_root, list_games
from smsrecomp.gameboy import list_memory
from smsrecomp.nes import list_memory as list_nes_memory
from smsrecomp.cover_settings import defaults as cover_defaults


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
    assert application.language in ('en', 'fr') and application.extended.get()
    initial_tags = application.icon_tags.get()
    assert application.preferences()['icon_tags'] == initial_tags
    initial_deep = application.gb_deep_validation.get()
    assert application.preferences()['gb_deep_validation'] == initial_deep
    initial_md_scan = application.md_advanced_scan.get()
    assert application.preferences()['md_advanced_scan'] == initial_md_scan
    application.show_options()
    options_panel = application.options_panel
    notebook = next(widget for widget in options_panel.winfo_children() if widget.winfo_class() == 'TNotebook')
    assert len(notebook.tabs()) == 8
    assert notebook.tab(0, 'text') == application.tr('options_common')
    assert notebook.tab(7, 'text') == application.tr('options_boxart')
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
                                         + len(list_memory()) + len(list_nes_memory()))
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
    for language in ('fr', 'en'):
        application.language = language
        application.refresh_language()
        assert application.start_button.cget('text') == application.tr('start')
        assert len(application.items) == before
        assert application.options_button.cget('text') == application.tr('options')
        window.update_idletasks()
        assert (application.frames.get(), application.passes.get()) == initial_tuning
    panel.destroy()
    print("PASS: English/French, extended default, hover hints, batch queue, left-aligned banner, duplicates, library; size", window.geometry())
    window.destroy()
    fixtures.cleanup()


tk.Tk.mainloop = smoke
with patch('smsrecomp.gui.load_preferences', return_value={'language': 'en', 'system_mode': 'auto'}), \
        patch('smsrecomp.gui.load_cover_settings', side_effect=cover_defaults), \
        patch('smsrecomp.gui.save_cover_settings'), \
        patch('smsrecomp.gui.save_preferences'):
    launch()
