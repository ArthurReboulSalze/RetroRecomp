"""Running a conversion batch: preferences, start, stop, the progress drain, play and the results."""
from __future__ import annotations

from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import online
from .batch import convert_batch
from .publishing import is_pending
from .paths import (
    APP_NAME, save_preferences, save_game_language, selected_bios_path, data_directory, console_options,
)
from .i18n import log_text
from .branding import COLORS
from .dialogs import center_dialog
from .platforms import open_local
from .gui_common import INTERFACE_PREFERENCES, SENDING_AVAILABLE, SEND_EVERY


class ConversionMixin:
    """Running a conversion batch: preferences, start, stop, the progress drain, play and the results."""

    def announce_finished(self, record):
        """Make the end of a batch unmistakable: a framed log line with the
        totals and the elapsed time, the system bell and the window title."""
        minutes, seconds = divmod(int(record.get('elapsed_seconds') or 0), 60)
        line = self.tr('batch_finished', total=record.get('requested', 0),
                       succeeded=record.get('succeeded', 0), failed=record.get('failed', 0),
                       minutes=minutes, seconds=seconds)
        for text in ('', '=' * 72, line, '=' * 72):
            self.messages.put(('log', text))
        try:
            self.app.bell()
            self.app.title(APP_NAME + ' - ' + self.tr('finished_title'))
            self.app.after(20000, lambda: self.app.title(APP_NAME))
        except tk.TclError:
            pass

    def preferences(self):
        return dict(language=self.language, coverage_default_revision=2,
            gb_validation_default_revision=1,
            output=self.output.get(), custom_output=self.custom_output.get(),
            system_mode=self.system_mode, platform=self.platform_id,
            backend='banked' if self.extended.get() else 'functions',
            **{key.name: getattr(self, key.name).get() for _, key in console_options('flag') if key.label},
            console_scan=self.console_scan_preferences(),
            passes=self.passes.get(), frames=self.frames.get(), jobs=self.jobs.get(),
            console_jobs=self.console_jobs_preferences(),
            use_cover=self.use_cover.get(),
            online_cover=self.online.get(), icon_tags=self.icon_tags.get(),
            use_shared_base=self.use_shared_base.get(), send_after_batch=self.send_after_batch.get(),
            startup_update_check=self.check_at_startup.get(), last_update_check=self.last_update_check,
            discoveries_waiting=self.discoveries_waiting,
            overwrite=self.overwrite.get(), force=self.force.get(),
            **{key.name: getattr(self, key.name).get() for _, key in console_options('path', 'choice')},
            feedback_paths={system: value.get().strip() for system, value in self.feedback_paths.items() if value.get().strip()},
            rom_paths={system:value.get().strip() for system,value in self.rom_paths.items() if value.get().strip()})

    def console_scan_preferences(self):
        """Per-console scan entries; empty pass/frame fields follow the shared values."""
        settings = {}
        for console, level in self.scan_level.items():
            entry = {}
            if level.get() != 'standard':
                entry['level'] = level.get()
            for key, variables, limit in (('passes', self.scan_passes, 10), ('frames', self.scan_frames, 10000)):
                text = variables[console].get().strip()
                if not text:
                    continue
                try:
                    value = int(text)
                except ValueError:
                    raise ValueError(self.tr('invalid_limits')) from None
                if not 1 <= value <= limit:
                    raise ValueError(self.tr('invalid_limits'))
                entry[key] = value
            if entry:
                settings[console] = entry
        return settings

    def console_jobs_preferences(self):
        """Games converted at once per console; an empty field follows the shared value."""
        settings = {}
        for console, variable in self.scan_jobs.items():
            text = variable.get().strip()
            if not text:
                continue
            try:
                value = int(text)
            except ValueError:
                raise ValueError(self.tr('invalid_limits')) from None
            if not 1 <= value <= 8:
                raise ValueError(self.tr('invalid_limits'))
            settings[console] = value
        return settings

    def start(self, selected=False):
        if self.busy or self.updating or getattr(self, 'importing', False):
            return
        if not self.ensure_build_tools(lambda: self.start(selected)):
            return
        chosen_rows = [row for row in self.table.get_children()
                       if not selected or row in self.table.selection()]
        if not chosen_rows:
            messagebox.showinfo(APP_NAME, self.tr('need_rom'))
            return
        try:
            options = self.preferences()
            if (not 1 <= options['passes'] <= 10 or not 1 <= options['frames'] <= 10000
                    or not 1 <= options['jobs'] <= 8):
                raise ValueError(self.tr('invalid_limits'))
            if not self.output.get().strip():
                raise ValueError(self.tr('need_output'))
            output = Path(options.pop('output')).expanduser().resolve()
            # Games converted at once per console: the queue is cut by it (convert_in_groups).
            per_console, shared_jobs = options.get('console_jobs') or {}, options.pop('jobs')
            for key in INTERFACE_PREFERENCES:
                options.pop(key, None)
            use_shared = options.pop('use_shared_base', False)
            if any(self.items[row].system == 'ng' and not self.items[row].error for row in chosen_rows):
                from .neogeo import validate_bios
                bios = selected_bios_path(options.get('ng_bios'))
                if bios is None:
                    raise ValueError(self.tr('ng_bios_required'))
                try:
                    validate_bios(bios)
                except ValueError as exc:
                    raise ValueError(self.tr('ng_bios_invalid', error=str(exc))) from exc
            for row in chosen_rows:
                if self.items[row].system == 'x68' and not self.items[row].error:
                    from .x68000 import machine
                    machine(self.items[row].path,options.get('x68_ipl'),options.get('x68_cgrom'),options.get('x68_ram',2))
            save_preferences(self.preferences())
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.busy = self.converting = True
        self.cancel.clear()
        self.stop_now.clear()
        self.last_auto_send = time.monotonic()   # the first send of a long batch comes after SEND_EVERY
        self.active_rows = chosen_rows
        self.running_jobs.clear()
        self.completed_jobs = 0
        items = [self.items[row] for row in self.active_rows]
        for row in self.active_rows:
            self.table.set(row, 'status', self.tr('waiting'))
            self.row_status[row] = 'waiting'
        self.progress.configure(value=0, maximum=len(items))
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.set_controls(False)
        self.set_status('starting', count=len(items))
        recovered=self.recovered_batch
        inventory_preferences=self.preferences()
        # A selected-only conversion must leave the other recovered rows
        # recoverable, including after a later window close or crash.
        recovered_indices={}
        if recovered is not None:
            for index,row in enumerate(recovered.definition['items']):
                if str(index) not in recovered.done:
                    recovered_indices.setdefault(row['path'],[]).append(index)
        def worker():
            journal=None
            try:
                from .queue_state import BatchJournal
                try:
                    journal=BatchJournal.create(data_directory()/'pending-batches',items,output)
                except (OSError,ValueError):
                    self.messages.put(('log',self.tr('queue_save_failed')))
                checkpoint_failed=False
                def event(kind,index,value):
                    nonlocal checkpoint_failed
                    if kind=='result' and not checkpoint_failed:
                        try:
                            if journal is not None:journal.result(index,value)
                            if recovered is not None:
                                for saved_index in recovered_indices.get(str(items[index].path),[]):
                                    recovered.result(saved_index,value)
                        except OSError:
                            checkpoint_failed=True
                            self.messages.put(('log',self.tr('queue_save_failed')))
                    if kind=='result':self.remember_export(value,inventory_preferences)
                    self.messages.put((kind,index,value))
                # The shared base's paths for these ROMs join the imported
                # banks first; each conversion checks them again.
                keys = self.shared_rom_keys([(item.system, item.sha256, item.path) for item in items
                                             if item.system and item.sha256 and not item.error], options)
                shared = self.prepare_shared_paths(keys, use_shared)
                self.start_shared_source(use_shared, keys, {item.system for item in items})
                from .queue_state import convert_in_groups
                record = convert_in_groups(items, output, jobs=shared_jobs, per_console=per_console,
                    cancel=self.cancel, stop_now=self.stop_now, convert=convert_batch,
                    **options, shared_paths=shared,
                    emit=lambda text: self.messages.put(('log', text)),
                    on_event=event)
                self.forget_rejected_shared(shared, record['games'])
                if journal is not None:
                    try:journal.finish(record)
                    except OSError:self.messages.put(('log',self.tr('queue_save_failed')))
                if recovered is not None and not recovered.pending_items():
                    try:
                        recovered.discard();self.recovered_batch=None
                    except OSError:self.messages.put(('log',self.tr('queue_save_failed')))
                for folder in {Path(game['executable']).parent for game in record['games']
                               if game['status'] == 'success'}:
                    save_game_language(folder, self.language)
                self.messages.put(('done', record))
            except Exception as exc:
                self.messages.put(('fatal', str(exc)))
            finally:
                self.stop_shared_source()
                if journal is not None:journal.close()
        threading.Thread(target=worker, daemon=True).start()

    def set_controls(self, enabled):
        for control in self.controls:
            control.configure(state='normal' if enabled else 'disabled')
        if self.options_panel is not None and self.options_panel.winfo_exists():
            for control, active_state in self.option_controls:
                control.configure(state=active_state if enabled else 'disabled')
            for system in self.feedback_importing:
                self.feedback_import_buttons[system].configure(state='disabled')
        # The credits stay open to visitors during a batch; the compiled games,
        # the help, the leaderboard and the account are not managed here.
        self.credits_button.configure(state='normal')
        self.start_button.configure(state='normal' if enabled else 'disabled')
        self.stop_button.configure(state='disabled' if enabled else 'normal')
        self.update_retry_button()
        self.language_field.configure(state='readonly' if enabled else 'disabled')
        self.system_field.configure(state='readonly' if enabled else 'disabled')
        self.update_output_controls()
        self.selection_changed()
        self.update_new_paths()
        self.render_disk_space()

    def stop(self):
        """Ask how to stop, then do it. "Stop now": no more games start and the
        build or validation processes of the running conversions are killed;
        nothing is published before a conversion ends, so earlier exports stay
        as they were. "Wait for the running games": no more games start, the
        running ones finish. Closing the dialog changes nothing."""
        if not self.busy or self.cancel.is_set():
            return False
        choice = self.stop_dialog()
        if choice not in ('now', 'wait') or not self.busy:
            return False
        if choice == 'now' and getattr(self, 'stop_now', None) is not None:
            self.stop_now.set()
        self.cancel.set()
        if choice == 'now':
            from .core import stop_processes
            stop_processes()
        self.stop_button.configure(state='disabled')
        self.set_status('stopping' if choice == 'now' else 'stopping_wait')
        return True

    def stop_dialog(self):
        """The two ways to stop: 'now', 'wait', or None when the dialog is
        closed (Escape, the window's close button)."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        chosen = {'value': None}
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('stop_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).pack(anchor='w')
        def answer(value):
            chosen['value'] = value
            window.destroy()
        buttons = []
        for value, label, note in (('now', 'stop_now', 'stop_now_note'), ('wait', 'stop_wait', 'stop_wait_note')):
            option = tk.Frame(body, bg=background)
            option.pack(fill='x', pady=(14, 0))
            button = ttk.Button(option, text=self.tr(label),
                                style='Primary.TButton' if value == 'wait' else 'TButton',
                                command=lambda value=value: answer(value))
            button.pack(fill='x')
            tk.Label(option, text=self.tr(note), bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                     wraplength=420, justify='left').pack(anchor='w', pady=(4, 0))
            buttons.append(button)
        window.bind('<Escape>', lambda event: window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.deiconify()
        window.grab_set()
        buttons[1].focus_set()
        self.app.wait_window(window)
        return chosen['value']

    def drain(self):
        try:
            while True:
                event = self.messages.get_nowait()
                kind = event[0]
                if kind == 'log':
                    getattr(self, 'session_log', []).append(event[1])
                    self.log.configure(state='normal')
                    self.log.insert('end', event[1] + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                    if self.compiled_view is not None:self.compiled_view.show_log(event[1])
                elif kind == 'footer_progress':
                    # Only while the spinner turns (counting or sending).
                    if getattr(self, 'sending_count', 0) > 0:
                        self.footer_label.configure(text=event[1])
                elif kind == 'notice':
                    messagebox.showinfo(APP_NAME, event[1], parent=self.app)
                elif kind == 'drop':
                    self.drop_paths(event[1])
                elif kind == 'drop_blocked':
                    self.messages.put(('log', self.tr('drop_blocked')))
                elif kind == 'raise':
                    # A second start of this installation: show this window.
                    self.app.deiconify()
                    self.app.lift()
                    self.app.focus_force()
                    self.app.attributes('-topmost', True)
                    self.app.after(300, lambda: self.app.attributes('-topmost', False))
                elif kind == 'drop_error':
                    self.messages.put(('log', self.tr('drop_unavailable')))
                elif kind == 'start':
                    row = self.active_rows[event[1]]
                    self.running_jobs.add(event[1])
                    self.table.set(row, 'status', self.tr('converting'))
                    self.row_status[row] = 'converting'
                    self.table.see(row)
                    if not self.cancel.is_set():
                        self.set_status('batch_running', completed=self.completed_jobs,
                                        total=len(self.active_rows), active=len(self.running_jobs))
                elif kind == 'result':
                    row, result = self.active_rows[event[1]], event[2]
                    self.running_jobs.discard(event[1])
                    self.completed_jobs += 1
                    if result['status'] in ('existing', 'current') and self.results.get(row, {}).get('status') == 'success':
                        result = {**self.results[row], **result}
                    self.results[row] = result
                    self.table.set(row, 'video', self.video_display(self.items[row], result))
                    status_key = {'success': 'created', 'error': 'error', 'stopped': 'stopped',
                                  'duplicate': 'duplicate', 'unrecognized': 'unrecognized',
                                  'skipped': 'skipped', 'existing': 'existing', 'current': 'current'}[result['status']]
                    if result['status'] == 'success' and result.get('conversion_stage') == 'experimental':
                        status_key = 'created_experimental'
                    text = (self.same_rom_text(row, result)
                            if result['status'] == 'duplicate' and result.get('duplicate_of')
                            else self.tr(status_key))
                    self.row_status[row] = status_key
                    if result.get('pending_install'):
                        self.row_status[row] = 'pending_install'
                        text = self.tr('pending_install')
                    self.table.set(row, 'status', text)
                    self.table.item(row, tags=('error',) if result['status'] in ('error', 'unrecognized', 'skipped') else (result['status'],))
                    self.progress.configure(value=self.completed_jobs)
                    # A long batch (slow computer, big collection) also sends what it
                    # found so far, every SEND_EVERY seconds, so points do not wait for its end.
                    if result['status'] == 'success' and time.monotonic() - getattr(self, 'last_auto_send', 0) > SEND_EVERY:
                        self.send_new_discoveries()
                    if not self.cancel.is_set():
                        self.set_status('batch_running', completed=self.completed_jobs,
                                        total=len(self.active_rows), active=len(self.running_jobs))
                    self.selection_changed()
                elif kind in ('done', 'fatal'):
                    self.busy = self.converting = False
                    from .core import reset_stop
                    reset_stop()
                    for index in self.running_jobs:
                        row = self.active_rows[index]
                        self.row_status[row] = 'waiting'
                        self.table.set(row, 'status', self.tr('waiting'))
                    self.running_jobs.clear()
                    if self.close_when_idle:
                        self.leave_discoveries_waiting()
                        self.close()
                        return
                    self.set_controls(True)
                    if kind == 'fatal':
                        self.set_status('fatal', error=log_text(event[1], self.language))
                    else:
                        record = event[1]
                        self.set_status('summary', **record)
                        self.announce_finished(record)
                        self.send_discoveries_soon()
                elif kind == 'update_check':
                    if len(event) > 2:
                        self.manual_check_done(event[1], event[2])
                    else:
                        self._offer_update(event[1])
                elif kind == 'update_news':
                    self.apply_update_news(*event[1:])
                elif kind == 'base_updated':
                    self.base_update_done(event[1], event[2])
                elif kind == 'update_ready':
                    self._start_prepared_update(event[1], event[2])
                    return
                elif kind == 'update_error':
                    self._update_error(event[1])
                elif kind == 'feedback_import':
                    system, report, error = event[1:]
                    self.feedback_importing.discard(system)
                    button = self.feedback_import_buttons.get(system)
                    if button is not None and button.winfo_exists():
                        button.configure(state='disabled' if self.busy or self.updating else 'normal')
                    if error:
                        self.feedback_status[system].set(self.tr('feedback_import_error'))
                        self.messages.put(('log', f'Gameplay feedback ({system}): {error}'))
                    else:
                        self.feedback_status[system].set(self.tr('feedback_import_summary',
                            **report, kib=report['bytes']/1024))
                elif kind == 'disk_space_measured':
                    token, projects, error = event[1:]
                    # Only the latest measurement of the open options counts.
                    if token is getattr(self, 'disk_cancel', None) and not token.is_set():
                        self.disk_state = ({'phase': 'error', 'error': error} if error else
                                           {'phase': 'measured', 'projects': projects})
                        self.render_disk_space()
                elif kind == 'disk_space_freed':
                    outcome, error = event[1:]
                    self.busy = False
                    self.set_controls(True)
                    self.disk_state = ({'phase': 'error', 'error': error} if error else
                                       {'phase': 'done', 'outcome': outcome})
                    self.render_disk_space()
                elif kind == 'tools_space_measured':
                    token, folders, error = event[1:]
                    if token is getattr(self, 'tools_cancel', None) and not token.is_set():
                        self.tools_state = ({'phase': 'error', 'error': error} if error else
                                            {'phase': 'measured', 'folders': folders})
                        self.render_disk_space()
                elif kind == 'tools_space_removed':
                    outcome, error = event[1:]
                    self.busy = False
                    self.set_controls(True)
                    self.tools_state = ({'phase': 'error', 'error': error} if error else
                                        {'phase': 'done', 'outcome': outcome})
                    self.render_disk_space()
                    self.measure_disk_space()      # the per-game folders went with .build
                elif kind == 'collection_changed':
                    if self.compiled_view is not None:self.compiled_view.render()
                elif kind == 'knowledge_done':
                    self.knowledge_done(event[1], event[2])
                elif kind == 'player':
                    self.player_read(event[1], event[2])
                elif kind == 'sources_ready':
                    self.finish_source_lookup(*event[1:])
                elif kind == 'rom_folder_searched':
                    self.finish_folder_search(*event[1:])
                elif kind == 'collection_quiet':
                    self.collection_refreshing = False
                    if event[1] and self.compiled_view is not None:self.compiled_view.render()
                    self.update_new_paths()
                elif kind == 'collection_done':
                    self.busy = self.converting = False
                    self.set_controls(True)
                    if self.compiled_view is not None:
                        self.compiled_view.progress.stop()
                        self.compiled_view.render()
                        summary=self.tr('reconvert_summary', **event[1])
                        if event[1].get('detail'):summary+=' · '+event[1]['detail']
                        self.compiled_view.status.set(summary)
                    if self.close_when_idle:
                        self.leave_discoveries_waiting()
                        self.close()
                        return
                    self.send_discoveries_soon()
                elif kind == 'auto_sent':
                    self.auto_sent(event[1], event[2])
                elif kind == 'report_sent':
                    self.report_sent(event[1], event[2])
        except queue.Empty:
            pass
        for row, result in self.results.items():
            if result.get('pending_install') and not is_pending(Path(result['executable'])):
                result['pending_install'] = False
                self.row_status[row] = 'created'
                self.table.set(row, 'status', self.tr('created'))
                self.selection_changed()
        self.app.after(100, self.drain)

    def play(self):
        rows = self.table.selection()
        if self.busy or len(rows) != 1:
            return
        if self.results.get(rows[0], {}).get('pending_install'):
            self.set_status('pending_install')
            return
        executable = self.results.get(rows[0], {}).get('executable')
        if executable:
            path = Path(executable)
            try:
                subprocess.Popen([str(path)], cwd=path.parent)
            except OSError as exc:
                messagebox.showerror(APP_NAME, str(exc))

    def open_output(self):
        path = Path(self.output.get()).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        open_local(path)

    def remember_export(self, result, preferences):
        if result.get('status') not in ('success','current','existing') or not result.get('report'):return
        from .compiled_games import game_from_report, refresh
        # Called by the conversion worker, before its result/done events. A
        # close-after-current-games cannot kill a late inventory writer.
        try:
            game = game_from_report(Path(result['report']),Path(result['executable']).parent,
                                    source=result.get('rom',''))
            self.compiled_inventory.remember(refresh(game,preferences))
            self.compiled_inventory.save()
            self.messages.put(('collection_changed',))
            self.note_conversion(result, game)
        except (OSError,ValueError,TypeError,KeyError):pass

    def note_conversion(self, result, game):
        """A game converted successfully while signed in: the next send tells
        the service (the gift for a game the base already knew, the depth
        coins; online.note_conversion). Skipped games are not conversions.
        What the shared base became for the game travels with the note: the
        conversion that set its paths aside says so (imported_hints_rejected)."""
        if result.get('status') != 'success' or not SENDING_AVAILABLE:
            return
        identity, rejected = game.identity, bool(result.get('imported_hints_rejected'))
        try:
            if game.system == 'ng':
                # The base knows a Neo Geo game by cartridge and BIOS together, and its
                # conversion says itself when it set imported hints aside.
                from .knowledge_exchange import report_game_key
                identity, flagged = report_game_key(result.get('report'))
                if identity is None:
                    return
                rejected = rejected or flagged
            online.note_conversion(game.system, identity, rejected=rejected)
        except Exception:
            pass
