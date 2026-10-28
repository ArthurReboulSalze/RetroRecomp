"""Sharing discoveries: knowledge export and import, the shared base and sending."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import online
from .paths import APP_NAME, selected_bios_path
from .branding import COLORS
from .gui_common import BUSY_SEND_RETRY, SENDING_AVAILABLE, SEND_EVERY


class SharingMixin:
    """Sharing discoveries: knowledge export and import, the shared base and sending."""

    def knowledge_menu(self):
        menu = tk.Menu(self.app, tearoff=False, bg=COLORS['button'], fg=COLORS['text'],
                       activebackground=COLORS['selected'], activeforeground=COLORS['gold_hover'])
        menu.add_command(label=self.tr('knowledge_import'), command=self.import_knowledge)
        menu.add_command(label=self.tr('knowledge_export'), command=self.export_knowledge)
        menu.add_separator()
        if not SENDING_AVAILABLE:
            # Sending arrives with the web service.
            menu.add_command(label=self.tr('knowledge_export_web'), state='disabled')
        else:
            # One entry both ways: the local base first, then this account's discoveries.
            menu.add_command(label=self.tr('knowledge_sync'), command=self.sync_shared_base)
            # Signing out lives in the header (and Options); signing in stays
            # here too, next to the send that needs it.
            if not online.account():
                menu.add_command(label=self.tr('knowledge_sign_in'), command=self.sign_in_dialog)
        button = self.knowledge_button
        try:menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:menu.grab_release()

    def knowledge_task(self, callback, status='knowledge_working'):
        """File work runs off Tk; the result comes back as one message."""
        self.busy = True
        self.set_controls(False)
        self.messages.put(('log', self.tr(status)))
        if self.compiled_view is not None:
            self.compiled_view.progress.start(15)
            self.compiled_view.status.set(self.tr(status))
        def worker():
            try:
                # An automatic send after a batch finishes first.
                with self.knowledge_lock:
                    outcome = callback()
                self.messages.put(('knowledge_done', outcome, None))
            except Exception as exc:self.messages.put(('knowledge_done', None, str(exc) or type(exc).__name__))
        threading.Thread(target=worker, daemon=True).start()

    def export_knowledge(self):
        """Count the discoveries first; ask where to save only if there are some."""
        if self.busy or self.updating:return
        self.collect_discoveries('collect')

    def collect_discoveries(self, kind):
        """Collect the shareable discoveries off Tk; `kind` tells knowledge_done
        whether they go to a file ('collect') or to the shared base ('send_collect')."""
        games = self.compiled_inventory.snapshot()
        if not games:
            messagebox.showinfo(APP_NAME, self.tr('knowledge_export_empty'), parent=self.app)
            if self.closing_send:self.close()
            return
        self.cancel.clear()
        collect = self.discoveries_collector(self.cancel)
        # The gold spinner turns while counting; its line follows the progress.
        self.counting = True
        self.sending_started('knowledge_counting')
        self.knowledge_task(lambda: (kind, collect()), 'knowledge_counting')

    def discoveries_collector(self, cancel):
        """A function collecting the shareable discoveries off Tk; the Tk
        values it needs are read now, on the Tk thread."""
        from .knowledge_exchange import collect_knowledge
        # Qualified games whose source moved are found like for Reconvert.
        options = self.preferences()
        from .compiled_games import Game
        known = [*self.compiled_inventory.snapshot(), *(Game('', i.system, i.sha256, i.title, source=str(i.path))
                                                        for i in self.items.values() if i.system and i.sha256)]
        def locate(pending):
            from .rom_sources import RomSources
            pairs = RomSources().resolve(pending, options, known=known, cancel=cancel)
            return {(game.system, game.identity): source for game, source in pairs if source}
        last = [0.0]
        def progress(stage, done, total):
            now = time.monotonic()
            if stage == 'games' and done and now - last[0] < 0.2:
                return
            last[0] = now
            key = 'counting_roms' if stage == 'roms' else 'counting_games'
            self.messages.put(('footer_progress', self.tr(key, done=done, total=total)))
        def collect():
            # Discoveries saved since the last look count without a full scan.
            from .compiled_games import refresh_changed
            refresh_changed(self.compiled_inventory, options)
            # Cached results stay valid while the ROM folders stay the same.
            context = json.dumps(options.get('rom_paths', {}), sort_keys=True)
            return collect_knowledge(self.compiled_inventory.snapshot(), locate, context, progress)
        return collect

    def send_knowledge(self, closing=False):
        """Send the discoveries the shared base has not received from this
        account yet; with `closing`, the window closes once it is done."""
        if self.busy or self.updating:return
        self.closing_send = closing
        if not online.account() and not self.sign_in_dialog():
            if closing:self.close()
            return
        self.collect_discoveries('send_collect')

    def online_message(self, error):
        if isinstance(error, online.ServiceConnectionError):
            return self.tr('online_unreachable')
        known = {'invalid_code': 'online_invalid_code', 'invalid_email': 'online_invalid_email',
                 'rate_limited': 'online_rate_limited', 'quota': 'online_rate_limited',
                 'terms_required': 'online_terms_needed', 'too_large': 'online_report_too_large',
                 'invalid_report': 'online_report_invalid', 'unauthorized': 'online_signed_out',
                 'pseudonym_taken': 'online_pseudonym_taken', 'invalid_pseudonym': 'online_pseudonym_invalid',
                 'verify': 'base_error_verify', 'no_path': 'base_error_nopath', 'no_base': 'base_error_nobase',
                 'unavailable': 'base_error_unavailable', 'format': 'base_error_format'}
        reason = getattr(error, 'reason', '') or type(error).__name__
        if reason == 'converter_outdated':
            # The service names the oldest version it accepts uploads from.
            minimum = online.minimum_converter(error, ask=False)
            return self.tr('online_outdated_min', minimum=minimum) if minimum else self.tr('online_outdated')
        return self.tr(known[reason]) if reason in known else self.tr('online_refused', reason=reason)

    def upload_discoveries(self, pending):
        """Worker side of a send: a summary, or {'error': text} to report."""
        try:
            return online.send(pending)
        except (online.ServiceError, online.ServiceConnectionError) as error:
            return {'error': self.online_message(error)}

    def service_problem(self, error):
        """A service or file error in one short, translated phrase."""
        if isinstance(error, (online.ServiceError, online.ServiceConnectionError)):
            return self.online_message(error)
        return str(error) or type(error).__name__

    # --- The shared base around each batch -----------------------------------

    def prepare_shared_paths(self, keys, enabled, quiet=False):
        """Worker side, before a batch: the shared base for these ROMs
        ('system:identity'). The local base applies whatever the option says
        (its qualified paths replace what the executable used to embed); with
        the option on it is first brought up to date, at most once a day, and
        a signed-in player also fetches the paths found since. Said in a few
        log lines. A failure leaves the conversions as they would be offline.
        `quiet` leaves out the lines that say nothing came."""
        try:
            outcome = online.prepare_batch(keys, bool(enabled))
        except Exception as exc:   # the batch goes on whatever happens here
            outcome = {'paths': {}, 'summary': None, 'error': exc, 'base': None}
        summary, error = outcome['summary'], outcome['error']
        self.log_published_base(outcome.get('base'), summary, error, quiet)
        if error is not None:
            self.messages.put(('log', self.tr('shared_unavailable', error=self.service_problem(error))))
        elif summary and summary['roms']:
            self.messages.put(('log', self.tr('shared_received', games=summary['roms'], records=summary['records'],
                                              observations=summary['observations'])))
        elif summary and summary['asked'] and not quiet:
            self.messages.put(('log', self.tr('shared_nothing')))
        return outcome['paths']

    def shared_rom_keys(self, entries, options):
        """The shared base's names ('system:identity') for the ROMs of a batch,
        from (system, sha256, path) triples. A cartridge console is named by
        its ROM's hash. A Neo Geo game by its prepared cartridge and the BIOS
        its conversion will use (neogeo_knowledge.key); one whose cartridge is
        not prepared yet is not asked for here: its conversion asks once it is
        (start_shared_source)."""
        keys, bios_sha, checked = [], None, False
        for system, sha256, path in entries:
            if system != 'ng':
                keys.append(f'{system}:{sha256}')
                continue
            if not checked:
                checked = True
                try:
                    from .neogeo import validate_bios
                    firmware = selected_bios_path((options or {}).get('ng_bios'))
                    bios_sha = validate_bios(firmware)['sha256'] if firmware else None
                except (ValueError, OSError):
                    bios_sha = None
            try:
                from .neogeo_knowledge import shared_identity
                identity = shared_identity(Path(path), sha256, bios_sha)
            except (OSError, ValueError, TypeError):
                identity = None
            if identity:
                keys.append(f'ng:{identity}')
        return keys

    def start_shared_source(self, enabled, keys, systems):
        """For the length of a batch with Neo Geo games: a conversion that has
        just prepared its cartridge asks the shared base for it, once, unless
        `keys` (the batch's first request) already covered it."""
        if 'ng' not in systems:
            return
        from . import neogeo_knowledge
        asked, lock = set(keys), threading.Lock()
        def source(identity):
            key = f'ng:{identity}'
            with lock:   # one request at a time: they all write the same files
                if key in asked:
                    return
                asked.add(key)
                self.prepare_shared_paths([key], enabled, quiet=True)
        neogeo_knowledge.SHARED_SOURCE = source

    def stop_shared_source(self):
        module = sys.modules.get(__package__ + '.neogeo_knowledge')
        if module is not None:
            module.SHARED_SOURCE = None

    def log_published_base(self, base, summary, error, quiet=False):
        """The shared base's outcome for this batch in log lines: an update
        that came in, no base and no connection (also as a notice, once per
        session: every game is discovered in full), the local base used because
        there was no connection, its number and the games received, nothing
        new (left to the signed-in sync's own line when there is one), a format
        this version cannot read, and the problem that stopped it, if any.
        Nothing when there is no base and nothing was asked of it."""
        if not base:
            return
        update = base.get('update') or {}
        if update.get('source'):
            self.messages.put(('log', self.tr('base_updated', version=update['version'],
                                              size=self.byte_size(update.get('downloaded_bytes', 0)))))
        if base.get('offline') and not quiet:
            if base.get('version') is None:
                self.messages.put(('log', self.tr('base_none')))
                if not getattr(self, 'base_notice_given', False):
                    self.base_notice_given = True
                    self.messages.put(('notice', self.tr('base_none')))
            else:
                self.messages.put(('log', self.tr('base_local_offline', version=base['version'])))
        if base.get('note') == 'format':
            self.messages.put(('log', self.tr('shared_base_format', format=base.get('format'))))
        elif base.get('version') is not None and base.get('games'):
            self.messages.put(('log', self.tr('shared_base_received', version=base['version'], games=base['games'])))
        elif (base.get('version') is not None and base.get('error') is None and summary is None and base.get('asked')
                and not quiet):
            self.messages.put(('log', self.tr('shared_base_nothing', version=base['version'])))
        if base.get('error') is not None and not (base.get('offline') or base.get('note') == 'format'):
            problem = self.service_problem(base['error'])
            # Offline, the signed-in sync reports the same problem right after.
            if error is None or problem != self.service_problem(error):
                self.messages.put(('log', self.tr('shared_base_unavailable', error=problem)))

    @staticmethod
    def byte_size(count):
        """A download size in words: '312 KiB', '4.7 MiB'."""
        return f'{count / 1048576:.1f} MiB' if count >= 1048576 else f'{max(1, round(count / 1024))} KiB'

    # --- The shared base on demand ---------------------------------------------

    def sync_shared_base(self):
        """Knowledge › Sync: bring the local base up to the service's latest
        version (off Tk), then, once signed in, send this account's new
        discoveries (knowledge_done chains the send). Signed out, only the
        base is updated; the result says how to send too."""
        if self.busy or self.updating:
            return
        self.syncing, self.sync_line = True, ''
        self.knowledge_task(lambda: ('base_updated', online.update_base()), 'base_update_working')

    def base_update_line(self, result):
        """The short result line of `update_base`."""
        if result.get('error'):
            reason = {'offline': 'online_unreachable', 'unavailable': 'base_error_unavailable',
                      'no_base': 'base_error_nobase', 'no_path': 'base_error_nopath', 'format': 'base_error_format',
                      'verify': 'base_error_verify', 'disk': 'base_error_disk'}.get(result['error'], 'online_refused')
            problem = self.tr(reason, reason=result['error']) if reason == 'online_refused' else self.tr(reason)
            return self.tr('base_update_failed', error=problem)
        if result.get('source'):
            return self.tr('base_updated', version=result['version'],
                           size=self.byte_size(result.get('downloaded_bytes', 0)))
        return self.tr('base_up_to_date', version=result['version'])

    def forget_rejected_shared(self, shared, results):
        """Shared paths a batch set aside after they broke a conversion no
        longer allow a quick check for that ROM."""
        rejected = [f"{result.get('system')}:{result.get('sha256')}" for result in results
                    if result.get('imported_hints_rejected')]
        keys = [key for key in rejected if key in shared]
        for result in results:
            if result.get('system') == 'ng' and result.get('report'):
                # Neo Geo says it in its own report, under the cartridge and BIOS identity (a
                # game asked for once its cartridge was prepared is not in `shared`).
                from .knowledge_exchange import report_game_key
                identity, flagged = report_game_key(result['report'])
                if identity and flagged:
                    keys.append(f'ng:{identity}')
        if keys:
            try:
                online.forget_shared(keys)
            except OSError:
                pass

    def sending_started(self, key='sending_discoveries'):
        """While discoveries (or a report) travel to the server, the status
        line's green dot becomes a small turning gold circle and the line says so."""
        self.sending_count = getattr(self, 'sending_count', 0) + 1
        if self.sending_count > 1 or not hasattr(self, 'status_dot'):
            return
        self.footer_label.configure(text=self.tr(key))
        def turn(angle=0):
            if self.sending_count <= 0:
                return
            dot = self.status_dot
            dot.delete('spinner')
            dot.itemconfigure('dot', state='hidden')
            dot.create_arc(1, 1, 11, 11, start=angle, extent=270, style='arc', outline=COLORS['gold'],
                           width=2, tags='spinner')
            self.spin_after = dot.after(60, turn, (angle - 30) % 360)
        turn()

    def sending_finished(self):
        self.sending_count = max(0, getattr(self, 'sending_count', 0) - 1)
        if self.sending_count or not hasattr(self, 'status_dot'):
            return
        try:
            self.status_dot.after_cancel(self.spin_after)
        except (AttributeError, tk.TclError, ValueError):
            pass
        self.status_dot.delete('spinner')
        self.status_dot.itemconfigure('dot', state='normal')
        self.footer_label.configure(text=self.tr('footer'))

    def send_new_discoveries(self):
        """After a batch, signed in with the option on: send the discoveries the
        shared base has not received from this account, then their claims, in
        a worker. Failures only reach the log; the games stay pending for the
        next batch. Never during an update; the window stays usable."""
        if (not SENDING_AVAILABLE or getattr(self, 'updating', False) or getattr(self, 'auto_sending', True)
                or not self.send_after_batch.get() or not online.account()):
            return
        collect = self.discoveries_collector(threading.Event())
        self.auto_sending = True
        self.last_auto_send = self.last_sent_at = time.monotonic()
        self.sending_started()
        def worker():
            try:
                with self.knowledge_lock:
                    summary = online.send_after_batch(collect)
                self.messages.put(('auto_sent', summary, None))
            except Exception as exc:
                self.messages.put(('auto_sent', None, exc))
        threading.Thread(target=worker, daemon=True, name='retro-recomp-send').start()

    def send_discoveries_soon(self):
        """After a batch: send now, or, when the last send is under SEND_EVERY
        old, once that much time has passed. Many short batches in a row then
        make one send every SEND_EVERY, not one each."""
        last = getattr(self, 'last_sent_at', None)
        wait = 0 if last is None else SEND_EVERY - (time.monotonic() - last)
        if wait <= 0:
            self.send_new_discoveries()
        elif getattr(self, 'deferred_send', None) is None:
            self.discoveries_waiting = True
            self.deferred_send = self.app.after(int(wait * 1000) + 1000, self.deferred_send_due)

    def deferred_send_due(self):
        self.deferred_send = None
        if self.converting:
            return   # a running batch sends what it finds itself (every SEND_EVERY and at its end)
        if self.busy:
            # An import, an export, a send by hand or a ROM search: the send waits for it.
            self.deferred_send = self.app.after(BUSY_SEND_RETRY * 1000, self.deferred_send_due)
            return
        self.send_new_discoveries()

    def manual_send_done(self):
        """Knowledge › Send (or the closing card's "Send and close") went
        through: it was this window's send. The send waiting for SEND_EVERY is
        dropped, the spacing starts again and nothing waits for the next start,
        so closing never sends a second time."""
        if self.deferred_send is not None:
            try:
                self.app.after_cancel(self.deferred_send)
            except (tk.TclError, ValueError):
                pass
            self.deferred_send = None
        self.last_sent_at = time.monotonic()
        self.discoveries_waiting = False

    def leave_discoveries_waiting(self):
        """The window closes at the end of a batch, before the batch's own
        send: with the option on and an account, the next start sends."""
        if SENDING_AVAILABLE and self.send_after_batch.get() and online.account():
            self.discoveries_waiting = True

    def send_option_changed(self, *_):
        """The send option turned off: nothing waits for the next start."""
        try:
            enabled = self.send_after_batch.get()
        except tk.TclError:
            return
        if not enabled:
            self.discoveries_waiting = False

    def auto_sent(self, summary, error):
        self.auto_sending = False
        self.sending_finished()
        if error is None:
            self.discoveries_waiting = False
        if error is not None:
            self.messages.put(('log', self.tr('auto_send_failed', error=self.service_problem(error))))
            return
        claims = (summary or {}).get('claims') or {}
        if (summary or {}).get('games'):
            text = self.tr('auto_send_done', games=summary['games'])
            if claims.get('new'):
                text += ' ' + self.tr('knowledge_send_new', count=claims['new'])
            if claims.get('converted'):
                text += ' ' + self.tr('knowledge_send_converted', count=claims['converted'])
            self.messages.put(('log', text))
        if (summary or {}).get('claims_refused'):
            self.messages.put(('log', self.tr('claims_refused', reason=', '.join(summary['claims_refused']))))
        if (summary or {}).get('games') or claims:
            self.read_after_send()

    def read_after_send(self):
        """A send's claims were taken: new points (and coins) at once, and the
        first reading started from now on (not one already running, which
        predates the claims) says how many games wait for their reward."""
        self.report_queued = self.player_generation + 1
        self.refresh_player(force=True)

    def log_queued(self, data, generation):
        """After a send, once the account was read by a reading started after
        it: how many converted games wait for their reward (beyond the
        service's games per day), credited on the following days. Nothing from
        an older service or with none waiting."""
        wanted = self.report_queued
        if wanted is None or generation < wanted:
            return
        self.report_queued = None
        count, days = online.queued_conversions((data or {}).get('profile'))
        if count:
            days = max(1, days)
            text = self.tr('conversions_queued' if count > 1 else 'conversions_queued_one', count=self.count_text(count),
                           wait=self.tr('conversions_wait_days' if days > 1 else 'conversions_wait_day',
                                        days=self.count_text(days)))
            self.messages.put(('log', text))

    def import_knowledge(self):
        """Check the chosen file first; import only unknown discoveries."""
        if self.busy or self.updating:return
        from .knowledge_exchange import SUFFIX, preview_import
        name = filedialog.askopenfilename(parent=self.app, title=self.tr('knowledge_import'),
            filetypes=[(self.tr('knowledge_file'), '*' + SUFFIX)])
        if name:self.knowledge_task(lambda:('preview', (Path(name), preview_import(Path(name)))),
                                    'knowledge_checking')

    def knowledge_done(self, outcome, error):
        self.busy = False
        self.set_controls(True)
        if getattr(self, 'counting', False):
            self.counting = False
            self.sending_finished()
        if self.manual_sending:
            self.manual_sending = False
            self.sending_finished()
        if self.compiled_view is not None:self.compiled_view.progress.stop()
        if error:
            text = self.tr('knowledge_failed', error=error)
            self.messages.put(('log', text))
            if self.compiled_view is not None:self.compiled_view.status.set(text)
            messagebox.showerror(APP_NAME, text, parent=self.app)
            self.syncing, self.sync_line = False, ''
            if self.closing_send:self.close()
            return
        kind, summary = outcome
        if kind == 'base_updated':
            line, syncing = self.base_update_line(summary), getattr(self, 'syncing', False)
            self.syncing = False
            if not syncing or summary.get('error') == 'offline':
                self.knowledge_report(line)   # offline, the send would fail the same way
            elif not online.account():
                self.knowledge_report(line + '\n\n' + self.tr('knowledge_sync_signin'))
            else:
                self.messages.put(('log', line))
                self.sync_line = line
                self.closing_send = False
                self.collect_discoveries('send_collect')
            return
        # A sync shows its base line once, with the send's question or result.
        sync_line, self.sync_line = getattr(self, 'sync_line', ''), ''
        base_line = sync_line + '\n\n' if sync_line else ''
        if kind == 'send_collect':
            pending = online.pending(summary)
            if not pending['games']:
                if self.closing_send:self.close()
                else:self.knowledge_report(base_line + self.tr('knowledge_send_none'))
                return
            detail = (base_line + self.tr('knowledge_send_found', games=pending['games'],
                                          consoles=len(pending['consoles']))
                      + '\n\n' + self.tr('knowledge_scope'))
            # On the closing card the player already chose to send. Conversions
            # alone (no new path) are no achievement: a plain question then.
            if (self.closing_send
                    or (self.achievement(pending['discoveries'], detail, self.tr('knowledge_send_action'))
                        if pending['discoveries'] else
                        messagebox.askyesno(APP_NAME, detail, icon='question', parent=self.app))):
                self.sending_started()
                self.manual_sending = True
                self.knowledge_task(lambda:('sent', self.upload_discoveries(pending)), 'knowledge_sending')
            return
        if kind in ('sent', 'signed_out'):
            if kind == 'signed_out':
                text = self.tr('signed_out')
                self.render_player(None)
            elif 'error' in summary:
                text = summary['error']
            else:
                self.manual_send_done()
                text = self.tr('knowledge_send_done', games=summary['games'], kib=summary.get('bytes', 0) / 1024)
                if (summary.get('claims') or {}).get('new'):
                    text += ' ' + self.tr('knowledge_send_new', count=summary['claims']['new'])
                if (summary.get('claims') or {}).get('converted'):
                    text += ' ' + self.tr('knowledge_send_converted', count=summary['claims']['converted'])
                if summary.get('claims'):
                    self.read_after_send()
                if summary.get('claims_refused'):
                    # Quietly, in the log only: the file itself was received.
                    self.messages.put(('log', self.tr('claims_refused', reason=', '.join(summary['claims_refused']))))
            self.messages.put(('log', text))
            if self.compiled_view is not None:self.compiled_view.status.set(text)
            if self.closing_send:
                if 'error' in (summary or {}):messagebox.showwarning(APP_NAME, text, parent=self.app)
                self.close()
            else:
                messagebox.showinfo(APP_NAME, text, parent=self.app)
            return
        if kind == 'collect':
            omitted = summary['omitted']
            if not summary['games']:
                text = self.tr('knowledge_export_none', known=omitted['already_known'],
                               missing=omitted['missing_rom'], unqualified=omitted['unqualified'])
                if omitted['missing_rom']:
                    text += ' ' + self.tr('knowledge_missing_hint')
                self.knowledge_report(text)
                return
            detail = (self.tr('knowledge_export_found', games=summary['games'], consoles=len(summary['consoles']))
                      + '\n\n' + self.tr('knowledge_scope'))
            if not self.achievement(summary['discoveries'], detail, self.tr('knowledge_export_action')):
                return
            from datetime import date
            from .knowledge_exchange import SUFFIX, write_knowledge
            name = filedialog.asksaveasfilename(parent=self.app, title=self.tr('knowledge_export'),
                defaultextension=SUFFIX, initialfile=f'Retro-Recomp-knowledge-{date.today():%Y-%m-%d}{SUFFIX}',
                filetypes=[(self.tr('knowledge_file'), '*' + SUFFIX)])
            if name:self.knowledge_task(lambda:('export', write_knowledge(summary, Path(name))))
            return
        if kind == 'preview':
            source, preview = summary
            if not preview['discoveries']:
                self.knowledge_report(self.tr('knowledge_import_nothing'))
                return
            detail = self.tr('knowledge_import_found', games=preview['games'], consoles=len(preview['consoles']))
            if self.achievement(preview['discoveries'], detail, self.tr('knowledge_import_action')):
                from .knowledge_exchange import import_knowledge
                self.knowledge_task(lambda:('import', import_knowledge(source)))
            return
        if kind == 'export':
            omitted = summary['omitted']
            text = self.tr('knowledge_export_done', games=summary['games'], consoles=len(summary['consoles']),
                           kib=summary['bytes'] / 1024, known=omitted['already_known'],
                           missing=omitted['missing_rom'], unqualified=omitted['unqualified'])
            if omitted['missing_rom']:
                text += ' ' + self.tr('knowledge_missing_hint')
            if summary.get('schema3_only_left_out'):
                text += ' ' + self.tr('knowledge_export_cps1', count=summary['schema3_only_left_out'])
        else:
            text = self.tr('knowledge_import_done', games=summary['new'] + summary['enriched'],
                           new=summary['new'], enriched=summary['enriched'], unchanged=summary['unchanged'])
        self.knowledge_report(text)

    def knowledge_report(self, text):
        self.messages.put(('log', text))
        if self.compiled_view is not None:self.compiled_view.status.set(text)
        messagebox.showinfo(APP_NAME, text, parent=self.app)
