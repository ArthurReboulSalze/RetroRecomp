"""Problem reports sent from the window."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import online
from .batch import system_output
from .paths import APP_NAME
from .systems import get_profile
from .branding import COLORS
from .dialogs import center_dialog
from .gui_common import SENDING_AVAILABLE


class ReportsMixin:
    """Problem reports sent from the window."""

    # --- Problem reports -------------------------------------------------------

    def report_available(self):
        return SENDING_AVAILABLE and not getattr(self, 'reporting', False)

    def session_log_for(self, title):
        """The conversion log lines of this session that name the game (else
        the last lines), as one text."""
        lines = list(getattr(self, 'session_log', ()))
        relevant = [line for line in lines if title and title in line]
        return '\n'.join(relevant or lines[-100:])

    @staticmethod
    def read_report_file(path):
        """A game's conversion-report.json, or None."""
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def report_roots(self, rom=None, games=None):
        """Folders whose names must not leave the computer: the games folder,
        the folder of the game's ROM, and the ROM folders of the options."""
        roots = [('<games>', games or self.output.get())]
        if rom:
            roots.append(('<rom>', str(Path(rom).parent)))
        roots += [('<rom>', value.get().strip()) for value in self.rom_paths.values() if value.get().strip()]
        return roots

    def queue_report_context(self, row):
        """What a failed (or wrong) queue row lets the report carry."""
        item, result = self.items.get(row), self.results.get(row, {})
        if item is None:
            return {}
        report = result.get('report')
        if not report and item.system and item.sha256:
            report = system_output(Path(self.output.get()).expanduser(), item.system) \
                / 'datas/reports' / item.key / 'conversion-report.json'
        games = system_output(Path(self.output.get()).expanduser(), item.system) if item.system else None
        return {'game': {'system': item.system, 'identity': item.sha256, 'title': item.title},
                'error': result.get('message') or item.error or None,
                'log': self.session_log_for(item.title),
                'report': self.read_report_file(report) if report else None,
                'roots': self.report_roots(item.path, str(games) if games else None)}

    def same_rom_text(self, row, result):
        """'Same ROM as …' naming the other file: two dumps of one ROM often share a display title."""
        item = self.items.get(row)
        name = result['duplicate_of']
        if item is not None and item.title.casefold() == str(name).casefold():
            for other, candidate in self.items.items():
                if (other != row and candidate.sha256 == item.sha256 and candidate.system == item.system
                        and self.row_status.get(other) != 'duplicate'):
                    name = candidate.path.name
                    break
        return self.tr('same_rom', title=name)

    def report_row_problem(self):
        rows = self.table.selection()
        if len(rows) == 1:
            self.report_problem('conversion', self.queue_report_context(rows[0]))

    def report_game_problem(self, game):
        """A compiled game that was created but is wrong."""
        executable = Path(game.executable)
        self.report_problem('conversion', {
            'game': {'system': game.system, 'identity': game.identity, 'title': game.title},
            'error': None, 'log': self.session_log_for(game.title),
            'report': self.read_report_file(game.report) if game.report else None,
            'roots': self.report_roots(game.source, str(executable.parent.parent))})

    def report_problem(self, kind='manual', context=None):
        """Offer to send a problem report. It needs a signed-in account (the
        sign-in is offered); the dialog shows what will be sent."""
        if not self.report_available():
            return
        if not online.account() and not self.sign_in_dialog():
            return
        context = context or {}
        message = self.report_dialog(kind, context)
        if message is None:
            return
        self.reporting = True
        self.sending_started('sending_report')
        language = self.language
        def worker():
            try:
                identifier = online.send_report(kind, game=context.get('game'), error=context.get('error'),
                                                log=context.get('log'), report=context.get('report'),
                                                message=message, language=language, roots=context.get('roots', ()))
            except Exception as error:
                self.messages.put(('report_sent', None, error))
                return
            self.messages.put(('report_sent', identifier, None))
        threading.Thread(target=worker, daemon=True, name='retro-recomp-report').start()

    def report_sent(self, identifier, error):
        self.reporting = False
        self.sending_finished()
        if error is None:
            self.messages.put(('log', self.tr('report_sent', id=identifier)))
            messagebox.showinfo(APP_NAME, self.tr('report_sent', id=identifier), parent=self.app)
            return
        if isinstance(error, online.ServiceError) and error.status == 401:
            self.refresh_player()   # the token was revoked: the corner shows signed out
        messagebox.showerror(APP_NAME, self.tr('report_failed', error=self.service_problem(error)), parent=self.app)

    def report_preview(self, kind, context):
        """(body, text): what would be sent, without the player's message, and
        the same as readable text for the dialog."""
        body = online.build_report(kind, game=context.get('game'), error=context.get('error'),
                                   log=context.get('log'), report=context.get('report'), language=self.language,
                                   roots=context.get('roots', ())) if kind != 'manual' else {}
        parts = []
        if body.get('game'):
            parts.append('game: ' + json.dumps(body['game'], ensure_ascii=False))
        if body.get('error'):
            parts.append('error:\n' + body['error'])
        if body.get('report'):
            parts.append('report:\n' + json.dumps(body['report'], ensure_ascii=False, indent=1))
        if body.get('log'):
            parts.append('log:\n' + body['log'])
        return body, '\n\n'.join(parts)

    def report_dialog(self, kind, context):
        """The report as it will leave, plus a box for the player's message.
        The message text, or None when cancelled."""
        body, preview = self.report_preview(kind, context)
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('report_title')}")
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        chosen = {'message': None}
        shell = tk.Frame(window, bg=background, padx=22, pady=18,
                         highlightthickness=1, highlightbackground=COLORS['gold'])
        shell.pack(fill='both', expand=True)
        def label(text, colour='text', size=9, bold=False, pad=(0, 0), wrap=520, font=None):
            tk.Label(shell, text=text, bg=background, fg=COLORS[colour], justify='left', wraplength=wrap,
                     font=font or (self.ui_font, size, 'bold' if bold else 'normal')).pack(anchor='w', pady=pad)
        label(self.tr('report_title').upper(), 'gold', bold=True)
        label(self.tr('report_intro' if kind == 'conversion' else 'report_intro_manual'), pad=(8, 10))
        if kind == 'conversion':
            game = context.get('game') or {}
            profile = get_profile(game['system']).name if game.get('system') else self.tr('unknown_console')
            label(self.tr('report_game', title=game.get('title', '?'), console=profile), bold=True)
            if body.get('error'):
                lines = body['error'].splitlines()
                shown = '\n'.join(lines[:4]) + ('\n…' if len(lines) > 4 else '')
                label(self.tr('report_error') + '\n' + shown[:600], 'muted', pad=(4, 0), font=('Consolas', 9))
            else:
                label(self.tr('report_no_error'), 'muted', pad=(4, 0))
            label(self.tr('report_log', kib=f"{len(body['log'].encode('utf-8')) / 1024:.1f}") if body.get('log')
                  else self.tr('report_no_log'), 'muted', pad=(4, 0))
            if body.get('report'):
                label(self.tr('report_details', count=len(body['report'])), 'muted')
        show = tk.BooleanVar(value=False)
        view = tk.Frame(shell, bg=background)
        text = tk.Text(view, width=70, height=9, wrap='none', bg=COLORS['field'], fg=COLORS['text'],
                       font=('Consolas', 8), relief='flat', padx=8, pady=6,
                       highlightthickness=1, highlightbackground=COLORS['border'])
        scroll = ttk.Scrollbar(view, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert('1.0', preview or self.tr('report_nothing_else'))
        text.configure(state='disabled')
        text.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        toggle = ttk.Button(shell)
        def flip():
            show.set(not show.get())
            toggle.configure(text=self.tr('report_hide' if show.get() else 'report_show'))
            if show.get():
                view.pack(fill='x', pady=(4, 0), after=toggle)
            else:
                view.pack_forget()
            window.update_idletasks()
            center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        toggle.configure(text=self.tr('report_show'), command=flip)
        if preview:
            toggle.pack(anchor='w', pady=(8, 0))
        required = kind == 'manual' or not body.get('error')
        label(self.tr('report_message_required' if required else 'report_message_optional'), 'muted', pad=(12, 2))
        entry = tk.Text(shell, width=70, height=5, wrap='word', bg=COLORS['field'], fg=COLORS['text'],
                        insertbackground=COLORS['text'], font=(self.ui_font, 9), relief='flat', padx=8, pady=6,
                        highlightthickness=1, highlightbackground=COLORS['border'])
        entry.pack(fill='x')
        label(self.tr('report_privacy'), 'muted', size=8, pad=(8, 0))
        buttons = tk.Frame(shell, bg=background)
        buttons.pack(fill='x', pady=(14, 0))
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='right')
        send = ttk.Button(buttons, text=self.tr('report_send'), style='Primary.TButton')
        send.pack(side='right', padx=(0, 8))
        def typed():
            return entry.get('1.0', 'end').strip()
        def sync(event=None):
            send.state(['!disabled' if typed() or not required else 'disabled'])
        def confirm():
            if required and not typed():
                return
            chosen['message'] = typed()
            window.destroy()
        send.configure(command=confirm)
        # Typing, pasting or cutting: the Send button follows the message.
        entry.bind('<<Modified>>', lambda event: (entry.edit_modified(False), sync()))
        sync()
        window.bind('<Escape>', lambda event: window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.deiconify()
        window.grab_set()
        entry.focus_set()
        self.app.wait_window(window)
        return chosen['message']
