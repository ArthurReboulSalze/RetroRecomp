"""The queue of ROMs: restoring it, dropping and importing paths, the list and its menu."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from .batch import BatchItem, identify, system_output
from .publishing import is_pending
from .report_schema import fallback_summary
from .paths import ROOT, APP_NAME, games_root, data_directory
from .i18n import log_text
from .dropfiles import enable_file_drop
from .systems import discover_roms, find_profile, get_profile
from .branding import COLORS
from .platforms import open_local
from .gui_common import PROFILES


class QueueMixin:
    """The queue of ROMs: restoring it, dropping and importing paths, the list and its menu."""

    def restore_queue(self):
        from .queue_state import recover
        journal=recover(data_directory()/'pending-batches')
        if journal is None:return False
        self.recovered_batch=journal
        self.output.set(journal.definition['output']);self.custom_output.set(True)
        self.custom_output_path=Path(journal.definition['output'])
        for item in journal.pending_items():
            status='invalid' if item.error else 'waiting'
            row=self.table.insert('','end',values=(item.title,
                get_profile(item.system).name if item.system else self.tr('unknown_console'),
                self.video_display(item),self.tr('size',value=item.size//1024) if item.size else '-',
                self.tr('auto'),self.tr(status)))
            self.items[row]=item;self.row_status[row]=status
        self.count.set(f'{len(self.items)} ROM'+('s' if len(self.items)!=1 else ''))
        self.update_empty_state();self.update_output_controls()
        self.set_status('queue_restored',count=len(self.items))
        return True

    def enable_drops(self):
        try:
            self.file_drop = enable_file_drop(self.app, self.queue_drop,
                lambda error: self.messages.put(('drop_error', str(error))))
        except OSError as error:
            self.messages.put(('drop_error', str(error)))

    def queue_drop(self, paths):
        # No Tk calls or ROM reads inside the native window procedure.
        kind = 'drop_blocked' if self.busy or self.updating else 'drop'
        self.messages.put((kind, paths))

    def drop_paths(self, paths):
        if self.busy or self.updating or getattr(self, 'importing', False):
            self.messages.put(('log', self.tr('drop_blocked')))
            return
        try:
            self.import_paths(paths)
        except OSError:
            self.messages.put(('log', self.tr('drop_unreadable')))

    def system_choices(self):
        return (self.tr('automatic'), *(profile.name for profile in PROFILES))

    def system_display(self):
        return self.tr('automatic') if self.system_mode == 'auto' else get_profile(self.system_mode).name

    def change_system(self, event=None):
        if self.busy:
            return
        selected = self.system_name.get()
        self.system_mode = next((profile.id for profile in PROFILES if profile.name == selected), 'auto')
        self.reload_queue()

    def update_output_controls(self):
        if self.output_field is None or not self.output_field.winfo_exists():
            return
        state = 'normal' if self.custom_output.get() and not self.busy else 'disabled'
        self.output_field.configure(state=state)
        self.output_browse.configure(state=state)

    def change_output_mode(self):
        if self.busy:
            return
        if self.custom_output.get():
            self.output.set(str(self.custom_output_path or games_root()))
        else:
            self.custom_output_path = Path(self.output.get()).expanduser()
            self.output.set(str(games_root()))
        self.update_output_controls()
        self.reload_queue()

    def reload_queue(self):
        if self.busy or not self.items:
            return
        previous = [(item.path, item.cover, item.standard_override, item.system)
                    for item in self.items.values()]
        selected = {self.items[row].path for row in self.table.selection()}
        self.table.delete(*self.table.get_children())
        self.items.clear(); self.results.clear(); self.row_status.clear()
        self.add_paths(path for path, _, _, _ in previous)
        remembered = {path: (cover, override, system) for path, cover, override, system in previous}
        for row, item in self.items.items():
            cover, override, system = remembered[item.path]
            item.cover = cover
            if not item.error and item.system == system:
                item.standard_override = override
            self.table.set(row, 'cover', self.tr('chosen' if cover else 'auto'))
            self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
            if item.path in selected:
                self.table.selection_add(row)
        self.selection_changed()

    def video_display(self, item: BatchItem, result: dict | None = None) -> str:
        if item.error or not item.video_hint:
            return '-'
        if item.system == 'cps1':
            return 'Arcade 59.64 Hz'
        if item.system == 'ng':
            return 'MVS · Europe'
        if item.standard_override:
            return self.tr('video_selected', standard=item.standard_override.upper())
        if result and result.get('video_standard'):
            return result['video_standard'].upper()
        return self.tr('video_guess', standard=item.video_hint.upper())

    def change_video(self, event=None):
        rows = self.table.selection()
        if self.busy or len(rows) != 1:
            return
        row = rows[0]
        item = self.items[row]
        selected = self.video_name.get().lower()
        item.standard_override = selected if selected in get_profile(item.system).video_modes else None
        result = self.results.get(row)
        if result and item.standard_override and result.get('video_standard') != item.standard_override:
            self.results.pop(row)
            self.row_status[row] = 'waiting'
            self.table.set(row, 'status', self.tr('waiting'))
            self.table.item(row, tags=())
        self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
        self.selection_changed()

    def add_paths(self, paths):
        """Add ROMs, folders or disk sets to the queue. Once the whole addition
        is in, games that already have an export are offered for removal."""
        outer = not getattr(self, 'adding_depth', 0)
        if outer:
            self.compiled_added = []
        self.adding_depth = getattr(self, 'adding_depth', 0) + 1
        try:
            self._add_paths(paths)
        finally:
            self.adding_depth -= 1
        if outer:
            self.offer_compiled(self.compiled_added)

    def _expand_paths(self, paths, found=lambda count: None, cancel=None):
        """Files to queue from files, folders and disk sets, without Tk calls.
        A multi-disk X68000 game is one entry: its disks become one playlist."""
        from .rom_sources import disk_sets
        files, logs = [], []
        def walk(entries):
            sets = disk_sets(entries)
            if sets.grouped:
                logs.append(self.tr('x68_sets_grouped', count=sets.grouped))
            for title, missing, total in sets.incomplete:
                logs.append(self.tr('x68_set_incomplete', title=title,
                                    missing=', '.join(map(str, missing)), total=total))
            for path in sets.paths:
                if cancel is not None and cancel.is_set():
                    return
                path = Path(path)
                if path.is_dir():
                    try:
                        walk(discover_roms(path))
                    except OSError:
                        logs.append(self.tr('drop_unreadable'))
                    continue
                files.append(path)
                found(len(files))
        walk(list(paths))
        return files, logs

    def _prepare_path(self, path, mode, output):
        """Identify one ROM and read its existing export, without Tk calls."""
        item = identify(path, None if mode == 'auto' else mode)
        status = ('skipped' if item.skipped else 'unrecognized' if item.unknown
                  else 'invalid' if item.error else 'waiting')
        prepared = {'item': item, 'status': status, 'result': None}
        if item.error:
            return prepared
        folder = system_output(output, item.system)
        report_path = folder / 'datas/reports' / item.key / 'conversion-report.json'
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            filename = report['executable']
            if Path(filename).name != filename:
                raise ValueError('Invalid executable filename in report')
            target = folder / filename
            if target.is_file() and report.get('rom', {}).get('sha256') == item.sha256:
                pending = is_pending(target)
                summary = fallback_summary(report, lenient=True)
                summary['video_standard'] = summary['video_standard'] or item.video_hint
                prepared['result'] = dict(status='success', executable=str(target.resolve()), report=str(report_path),
                    pending_install=pending, **summary)
                prepared['status'] = ('pending_install' if pending else
                                      'created_experimental' if report.get('status') == 'experimental' else 'created')
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return prepared

    def _insert_prepared(self, prepared):
        item, status, result = prepared['item'], prepared['status'], prepared['result']
        row = self.table.insert('', 'end', values=(item.title,
            get_profile(item.system).name if item.system else self.tr('unknown_console'),
            self.video_display(item, result),
            self.tr('size', value=item.size//1024) if item.size else '-',
            self.tr('auto'), self.tr(status)),
            tags=('error',) if item.error else ('success',) if result else ())
        self.items[row] = item
        self.row_status[row] = status
        if result:
            self.results[row] = result
            self.compiled_added.append(row)
        return row

    def _finish_adding(self):
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))
        self.update_empty_state()
        self.app.after_idle(self.fit_minimum_width)

    def _add_paths(self, paths):
        files, logs = self._expand_paths(paths)
        for line in logs:
            self.messages.put(('log', line))
        existing = {item.path for item in self.items.values()}
        output = Path(self.output.get()).expanduser()
        for path in files:
            if path.resolve() in existing:
                continue
            prepared = self._prepare_path(path, self.system_mode, output)
            self._insert_prepared(prepared)
            existing.add(prepared['item'].path)
        self._finish_adding()

    def import_paths(self, paths):
        """Add files or folders from the window: folders are walked and ROMs
        read in a worker, with a progress bar, so a slow computer never looks
        frozen. A few plain files are added at once."""
        paths = [Path(path) for path in paths]
        if not paths:
            return
        if len(paths) <= 8 and not any(path.is_dir() for path in paths):
            before = len(self.items)
            self.add_paths(paths)
            self.set_status('drop_added', count=len(self.items) - before)
            return
        self.importing = True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_added = []
        before = len(self.items)
        mode, output = self.system_mode, Path(self.output.get()).expanduser()
        existing = {item.path for item in self.items.values()}
        state = {'found': 0, 'total': 0, 'done': 0, 'ready': [], 'logs': [], 'finished': False}
        self.progress.configure(mode='indeterminate', value=0)
        self.progress.start(12)
        self.set_status('import_scanning', count=0)

        def worker():
            try:
                files, logs = self._expand_paths(paths, lambda count: state.update(found=count), self.cancel)
                state['logs'] = logs
                state['total'] = len(files)
                for path in files:
                    if self.cancel.is_set():
                        break
                    try:
                        if path.resolve() not in existing:
                            prepared = self._prepare_path(path, mode, output)
                            existing.add(prepared['item'].path)
                            state['ready'].append(prepared)
                    except OSError:
                        pass
                    state['done'] += 1
            finally:
                state['finished'] = True

        def poll():
            ready, state['ready'] = state['ready'], []
            for prepared in ready:
                self._insert_prepared(prepared)
            if state['total']:
                if str(self.progress.cget('mode')) != 'determinate':
                    self.progress.stop()
                    self.progress.configure(mode='determinate', maximum=state['total'])
                self.progress.configure(value=state['done'])
                self.set_status('import_reading', done=state['done'], total=state['total'])
            else:
                self.set_status('import_scanning', count=state['found'])
            if ready:
                self._finish_adding()
            if not state['finished'] or state['ready']:
                self.app.after(80, poll)
                return
            self.progress.stop()
            self.progress.configure(mode='determinate', value=0)
            for line in state['logs']:
                self.messages.put(('log', line))
            self._finish_adding()
            self.importing = False
            self.set_controls(True)
            self.set_status('drop_added', count=len(self.items) - before)
            self.offer_compiled(self.compiled_added)

        threading.Thread(target=worker, daemon=True).start()
        poll()

    def choose_roms(self):
        paths = filedialog.askopenfilenames(title=self.tr('pick_roms'), initialdir=ROOT / 'ROMS',
            filetypes=[('ROM files', '*.sms *.gg *.gb *.zip *.bin *.rom *.gbc *.gba *.nes *.sfc *.smc *.md *.gen *.pce *.dim *.xdf *.m3u'),
                       ('All files', '*.*')])
        self.import_paths(paths)

    def choose_directory(self):
        path = filedialog.askdirectory(title=self.tr('pick_folder'), initialdir=ROOT / 'ROMS')
        if path:
            self.import_paths([Path(path)])

    def select_all_rows(self):
        self.table.selection_set(self.table.get_children())

    def queue_menu(self, event):
        """Right-click on the queue: the row's actions, then list housekeeping.
        Removing rows never touches the ROM files, and the label says so."""
        row = self.table.identify_row(event.y)
        if row and row not in self.table.selection():
            self.table.selection_set(row)
            self.table.focus(row)
        rows = self.table.selection()
        if not rows:
            return
        one = len(rows) == 1
        item = self.items.get(rows[0]) if one else None
        result = self.results.get(rows[0], {}) if one else {}
        free = not self.busy and not self.updating
        def state(enabled):
            return 'normal' if enabled else 'disabled'
        colors = dict(bg=COLORS['button'], fg=COLORS['text'], activebackground=COLORS['selected'],
                      activeforeground=COLORS['gold_hover'])
        menu = tk.Menu(self.app, tearoff=False, **colors)
        playable = (one and free and result.get('status') in ('success', 'existing', 'current')
                    and not result.get('pending_install'))
        menu.add_command(label=self.tr('play'), command=self.play, state=state(playable))
        menu.add_command(label=self.tr('start_selected'), command=lambda: self.start(selected=True), state=state(free))
        if any(self.row_status.get(row) in ('error', 'stopped') for row in rows):
            menu.add_command(label=self.tr('retry'), command=self.retry_failed, state=state(free))
        # A failed row, or a game that was created but is wrong, can be reported (an identical
        # ROM skipped is not a problem: its first copy was converted).
        menu.add_command(label=self.tr('report_problem'), command=self.report_row_problem,
                         state=state(one and self.report_available()
                                     and self.row_status.get(rows[0]) not in ('waiting', 'converting', 'duplicate', None)))
        menu.add_separator()
        menu.add_command(label=self.tr('choose_cover'), command=self.choose_cover, state=state(one and free))
        menu.add_command(label=self.tr('auto_cover'), command=self.automatic_cover, state=state(free))
        if item is not None and not item.error:
            video = tk.Menu(menu, tearoff=False, **colors)
            for label in (self.tr('auto'), *(mode.upper() for mode in get_profile(item.system).video_modes)):
                video.add_radiobutton(label=label, variable=self.video_name, value=label, command=self.change_video)
            menu.add_cascade(label=self.tr('video_timing'), menu=video, state=state(free))
        menu.add_separator()
        menu.add_command(label=self.tr('open_rom_folder'), state=state(item is not None),
                         command=lambda: item and open_local(item.path.parent))
        executable = result.get('executable')
        menu.add_command(label=self.tr('open_game_folder'), state=state(bool(executable)),
                         command=lambda: executable and open_local(Path(executable).parent))
        menu.add_separator()
        menu.add_command(label=self.tr('remove_from_list', count=len(rows)), command=self.remove_selected,
                         state=state(free))
        menu.add_command(label=self.tr('clear'), command=self.clear, state=state(free))
        menu.add_command(label=self.tr('select_all'), command=self.select_all_rows)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def remove_selected(self):
        if self.busy:
            return
        for row in self.table.selection():
            if self.recovered_batch is not None:
                journal=self.recovered_batch
                for index,saved in enumerate(journal.definition['items']):
                    if saved['path']==str(self.items[row].path):
                        try:journal.result(index,{'status':'removed'})
                        except OSError:pass
            self.table.delete(row)
            self.items.pop(row, None)
            self.results.pop(row, None)
            self.row_status.pop(row, None)
        self.add_paths([])
        self.selection_changed()

    def clear(self):
        self.table.selection_set(self.table.get_children())
        self.remove_selected()

    def choose_output(self):
        path = filedialog.askdirectory(title=self.tr('pick_output'), initialdir=self.output.get())
        if path:
            self.output.set(path)
            self.custom_output_path = Path(path)
            self.reload_queue()

    def choose_cover(self):
        rows = self.table.selection()
        if len(rows) != 1:
            messagebox.showinfo(APP_NAME, self.tr('one_cover'))
            return
        path = filedialog.askopenfilename(title=self.tr('pick_cover'), initialdir=ROOT / 'BoxArt', filetypes=[(self.tr('images'), '*.png *.jpg *.jpeg *.webp *.bmp *.ico')])
        if path:
            self.items[rows[0]].cover = Path(path)
            self.table.set(rows[0], 'cover', self.tr('chosen'))
            self.use_cover.set(True)
            self.selection_changed()

    def automatic_cover(self):
        for row in self.table.selection():
            self.items[row].cover = None
            self.table.set(row, 'cover', self.tr('auto'))
        self.selection_changed()

    def selection_changed(self):
        rows = self.table.selection()
        self.selected_button.configure(state='normal' if rows and not self.busy and not self.updating else 'disabled')
        result = self.results.get(rows[0], {}) if len(rows) == 1 else {}
        self.play_button.configure(state='normal' if not self.busy and result.get('status') in ('success', 'existing', 'current') and not result.get('pending_install') else 'disabled')
        item = self.items[rows[0]] if len(rows) == 1 else None
        if item and not item.error:
            self.video_field.configure(values=(self.tr('auto'),
                *(mode.upper() for mode in get_profile(item.system).video_modes)))
        self.video_name.set((item.standard_override.upper() if item and item.standard_override
                             else self.tr('auto')))
        self.video_field.configure(state='readonly' if item and not item.error and not self.busy else 'disabled')
        if len(rows) == 1:
            text = log_text(item.error or result.get('message') or str(item.path), self.language)
            if result.get('status') == 'duplicate' and result.get('duplicate_of'):
                text = self.same_rom_text(rows[0], result)
            elif result.get('status') == 'existing':
                text = self.tr('existing')
            if item.cover:
                text += f" · {self.tr('cover')}: {item.cover.name}"
            if result.get('status') == 'success':
                comparison = result.get('reference_vdp_trace_match')
                if getattr(find_profile(item.system), 'fallback_display', 'cycles') == 'opcodes':
                    text = self.tr('fallback16', opcodes=result.get('main_interpreted_opcodes', 0),
                        audio_opcodes=result.get('audio_interpreted_opcodes', 0))
                    device = result.get('device')
                    if device and (device.get('instructions') or device.get('mode') == 'interpreted'):
                        text += ' · ' + self.tr('fallback_device', chip=str(device['chip']).upper(),
                            instructions=device['instructions'], per_frame=device['per_frame'])
                elif result.get('interpreter_percent') is None or comparison is None:
                    text = self.tr('fallback_cycles', cycles=result.get('interpreter_cycles', 0))
                else:
                    text = self.tr('fallback', percent=result['interpreter_percent'],
                                   comparison=self.tr('vdp_equal' if comparison else 'vdp_different'))
            text += ' · ' + self.video_display(item, result)
            self.detail.set(text)
        else:
            self.detail.set(self.tr('shared'))

    def failed_rows(self):
        return [row for row in self.table.get_children() if self.row_status.get(row) in ('error', 'stopped')]

    def update_retry_button(self):
        self.retry_button.configure(state='normal' if self.failed_rows() and not self.busy and not self.updating
                                    else 'disabled')

    def retry_failed(self):
        rows = self.failed_rows()
        if not rows or self.busy:
            return
        self.table.selection_set(rows)
        self.start(selected=True)
