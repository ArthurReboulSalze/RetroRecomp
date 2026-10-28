"""Updates of the converter and of the shared base, and the build tools installation."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import online
from .paths import APP_NAME, save_preferences
from .i18n import STRINGS, log_text
from .branding import COLORS
from .dialogs import center_dialog
from .gui_common import UPDATE_CHECK_EVERY, base_is_newer, update_error_text
from .gui_drawing import badged_icon


class UpdatesMixin:
    """Updates of the converter and of the shared base, and the build tools installation."""

    def check_updates(self):
        """The update button. With something known to be new it offers exactly
        that (the software, the base, or both); otherwise it looks, software
        and base, and says what it found. Only a click or the start-up look
        (when the option is on) asks the network."""
        if self.busy or self.updating:
            return
        software, base = self.update_news.get('software'), self.update_news.get('base')
        if software or base:
            self.offer_news(software, base)
            return
        self.updating = True
        self.update_button.configure(state='disabled')
        self.set_status('checking_updates')
        def worker():
            try:
                from .updater import check_for_update
                update = check_for_update()
            except Exception as exc:
                self.messages.put(('update_error', exc))
                return
            self.messages.put(('update_check', update, self.look_at_base(force=True)))
        threading.Thread(target=worker, daemon=True).start()

    def look_at_base(self, force=False):
        """The base check (the site's manifest only), None when it cannot be
        made: offline, no service, or a build without the base."""
        check = getattr(online, 'check_base', None)
        if check is None:
            return None
        try:
            info = check(force=True) if force else check()
        except Exception:
            return None
        return info if isinstance(info, dict) and not info.get('error') else None

    def startup_update_due(self, now=None):
        """The option is on and the last look is older than UPDATE_CHECK_EVERY."""
        if not self.check_at_startup.get():
            return False
        now = time.time() if now is None else now
        last = self.last_update_check
        return not isinstance(last, (int, float)) or last > now or now - last >= UPDATE_CHECK_EVERY

    def startup_update_check(self):
        """When the window has opened: look for a new version of the software
        and of the base in a worker, silently (nothing is said offline), and
        send what was found back through the message queue. Nothing is
        downloaded."""
        if not self.startup_update_due():
            return
        def worker():
            software = None
            software_known = False
            try:
                from .updater import check_for_update
                software, software_known = check_for_update(), True
            except Exception:
                pass
            base = self.look_at_base()
            self.messages.put(('update_news', software_known, software, base is not None, base))
        threading.Thread(target=worker, daemon=True).start()

    def apply_update_news(self, software_known, software, base_known, base):
        """Remember what a look found (a side that could not be reached keeps
        what it showed), space the next look, and redraw the dot."""
        if software_known:
            self.update_news['software'] = software
        if base_known:
            self.update_news['base'] = base if base_is_newer(base) else None
        if software_known or base_known:
            self.last_update_check = time.time()
        self.refresh_update_badge()

    def update_news_lines(self):
        lines = []
        software, base = self.update_news.get('software'), self.update_news.get('base')
        if software:
            lines.append(self.tr('update_news_software', version=software.version))
        if base:
            lines.append(self.tr('update_news_base', version=base['latest']))
        return lines

    def update_tip(self):
        lines = self.update_news_lines()
        tip = self.tr('tip_check_updates')
        return '\n'.join(lines) + '\n\n' + tip if lines else tip

    def refresh_update_badge(self):
        """A dot on the update button while the software or the base has something new."""
        badge = bool(self.update_news.get('software') or self.update_news.get('base'))
        try:
            if badge:
                if ('download', 'badge') not in self.button_images:
                    self.button_images[('download', 'badge')] = (
                        badged_icon(self.app, 'download', COLORS['text']),
                        badged_icon(self.app, 'download', COLORS['disabled']))
            normal, disabled = self.button_images[('download', 'badge' if badge else False)]
            self.update_button.configure(image=(normal, 'disabled', disabled))
        except (KeyError, tk.TclError):
            pass

    def manual_check_done(self, update, base):
        """The result of a click on the button with nothing known: what was found
        is remembered, then offered, or "up to date"."""
        self.updating = False
        self.update_button.configure(state='normal')
        self.set_status('ready')
        self.apply_update_news(True, update, base is not None, base)
        software, news_base = self.update_news.get('software'), self.update_news.get('base')
        if software or news_base:
            self.offer_news(software, news_base)
        else:
            self._offer_update(None)

    def offer_news(self, software, base):
        """Offer what is new: the software alone goes straight to its own
        question (with the release notes); with a new base, the three choices."""
        if software and not base:
            self._offer_update(software)
            return
        choice = self.update_choice_dialog(software, base)
        if choice == 'base':
            self.update_base_now()
        elif choice == 'software' and software:
            self._offer_update(software)
        elif choice == 'both' and software:
            self.update_base_now(then=software)

    def update_choice_dialog(self, software, base):
        """What is new and what to update: 'software', 'base', 'both', or None
        (later, or the window closed). Only the choices that exist are shown."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.transient(self.app)
        chosen = tk.StringVar(value='')
        body = tk.Frame(window, bg=background, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('update_choice_question'), bg=background, fg=COLORS['text'],
                 font=(self.ui_font, 10), wraplength=480, justify='left').pack(anchor='w')
        tk.Label(body, text='\n'.join('\u2022 ' + line for line in self.update_news_lines()),
                 bg=background, fg=COLORS['gold'], font=(self.ui_font, 10, 'bold'),
                 justify='left').pack(anchor='w', pady=(10, 0))
        buttons = tk.Frame(body, bg=background)
        buttons.pack(fill='x', pady=(16, 0))
        def pick(value):
            chosen.set(value)
            window.destroy()
        ttk.Button(buttons, text=self.tr('update_choice_later'), command=window.destroy).pack(side='right')
        primary = None
        for value, key in (('both', 'update_choice_both'), ('base', 'update_choice_base'),
                           ('software', 'update_choice_software')):
            if (value == 'both' and not (software and base)) or (value == 'base' and not base) \
                    or (value == 'software' and not software):
                continue
            button = ttk.Button(buttons, text=self.tr(key), command=lambda value=value: pick(value),
                                style='Primary.TButton' if primary is None else 'TButton')
            button.pack(side='right', padx=(0, 8))
            primary = primary or button
        window.bind('<Escape>', lambda event: window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.deiconify()
        window.grab_set()
        if primary is not None:
            primary.focus_set()
        self.app.wait_window(window)
        return chosen.get() or None

    def update_base_now(self, then=None):
        """Bring the base up to date in a worker (online.update_base). `then` is
        the software Update to install straight after, when both were chosen."""
        self.updating = True
        self.update_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.set_status('updating_base')
        def worker():
            update = getattr(online, 'update_base', None)
            try:
                result = update() if update else {'error': self.tr('online_unreachable')}
            except Exception as exc:
                result = {'error': str(exc) or type(exc).__name__}
            self.messages.put(('base_updated', result, then))
        threading.Thread(target=worker, daemon=True).start()

    def base_update_done(self, result, then=None):
        self.updating = False
        self.update_button.configure(state='normal')
        self.start_button.configure(state='normal')
        self.set_status('ready')
        error = result.get('error') if isinstance(result, dict) else self.tr('online_unreachable')
        if error or not isinstance(result, dict):
            messagebox.showerror(APP_NAME, self.tr('base_update_error', error=error or ''))
            return
        self.update_news['base'] = None
        self.refresh_update_badge()
        if then is not None:
            # Both were chosen: the software follows, with no second question.
            if getattr(sys, 'frozen', False):
                self.download_update(then)
            else:
                messagebox.showinfo(APP_NAME, self.tr('update_source', version=then.version, page=then.page))
            return
        version = result.get('version')
        key = 'base_current' if result.get('previous') == version and not result.get('downloaded_bytes') \
            else 'base_update_finished'
        messagebox.showinfo(APP_NAME, self.tr(key, version=version))

    def _offer_update(self, update):
        self.updating = False
        self.update_button.configure(state='normal')
        self.set_status('ready')
        if update is None:
            self.update_news['software'] = None
            self.refresh_update_badge()
            messagebox.showinfo(APP_NAME, self.tr('update_current'))
            return
        if not getattr(sys, 'frozen', False):
            messagebox.showinfo(APP_NAME, self.tr('update_source', version=update.version,
                                                 page=update.page))
            return
        question = self.tr('update_available', version=update.version,
                           megabytes=round(update.size / 1048576, 1))
        accepted = (self.update_dialog(update, question) if update.notes
                    else messagebox.askyesno(APP_NAME, question))
        if not accepted:
            return
        self.download_update(update)

    def download_update(self, update):
        """Download the software update (and the base copy of its release) in a worker."""
        self.updating = True
        self.update_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.set_status('downloading_update', version=update.version)
        def worker():
            try:
                from .updater import prepare_update
                self.messages.put(('update_ready', *prepare_update(update, Path(sys.executable))))
            except Exception as exc:
                self.messages.put(('update_error', exc))
        threading.Thread(target=worker, daemon=True).start()

    def update_dialog(self, update, question):
        """The update question with what changed since the installed version.
        The notes are the published release notes, in English only; the two
        buttons answer the localized question. True when the download is chosen."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.transient(self.app)
        chosen = tk.BooleanVar(value=False)
        body = tk.Frame(window, bg=background, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=question, bg=background, fg=COLORS['text'], font=(self.ui_font, 10),
                 wraplength=560, justify='left').pack(anchor='w')
        tk.Label(body, text="What's new", bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).pack(anchor='w', pady=(12, 4))
        frame = tk.Frame(body, bg=background)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, width=72, height=18, wrap='word', bg=COLORS['field'], fg=COLORS['text'],
                       font=(self.ui_font, 9), relief='flat', padx=10, pady=8,
                       highlightthickness=1, highlightbackground=COLORS['border'])
        bar = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=bar.set)
        text.insert('1.0', update.notes)
        text.configure(state='disabled')
        text.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        buttons = tk.Frame(body, bg=background)
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Later', command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text='Download and restart', style='Primary.TButton',
                        command=lambda: (chosen.set(True), window.destroy()))
        go.pack(side='right', padx=(0, 8))
        window.bind('<Escape>', lambda event: window.destroy())
        window.bind('<Return>', lambda event: go.invoke())
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.minsize(520, 360)
        window.deiconify()
        window.grab_set()
        go.focus_set()
        self.app.wait_window(window)
        return chosen.get()

    def _start_prepared_update(self, job_dir: Path, token: str):
        from .updater import discard_update, start_update_helper
        try:
            start_update_helper(job_dir, token)
        except Exception as exc:
            try:
                discard_update(job_dir, Path(sys.executable))
            except OSError:
                pass
            self._update_error(str(exc))
            return
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        if self.recovered_batch is not None:self.recovered_batch.close()
        self.app.destroy()

    def _update_error(self, error: Exception | str):
        self.updating = False
        self.update_button.configure(state='normal')
        self.start_button.configure(state='normal')
        self.set_status('ready')
        messagebox.showerror(APP_NAME, update_error_text(error, self.language))

    # --- Build tools ---------------------------------------------------------

    def ensure_build_tools(self, retry):
        """True when a conversion can start; otherwise offer to install what is
        missing and run `retry` once it is installed."""
        from .updater import missing_build_tools
        try:
            missing = missing_build_tools()
        except Exception:
            return True   # the conversion reports its own precise error
        from .core import dependencies_ready
        if not missing:
            if dependencies_ready():
                return True
            # Tools present, shared pieces not built yet: prepare them now,
            # behind the progress window, rather than inside the first game.
            if messagebox.askyesno(APP_NAME, self.tr('deps_intro') + '\n\n' + self.tr('deps_question'), parent=self.app):
                self.install_build_tools({}, retry)
            return False
        if os.name == 'nt':
            items = [self.tr(f'tools_item_{key}') for key in ('git', 'compiler') if missing.get(key)]
            text = self.tr('tools_intro', items='\n• ' + '\n• '.join(items))
        elif missing.get('packages'):
            text = self.tr('tools_intro_linux', count=len(missing['packages']),
                           packages=' '.join(missing['packages']))
        else:
            messagebox.showwarning(APP_NAME, self.tr('tools_manual_linux', commands=', '.join(missing['commands'])),
                                   parent=self.app)
            return False
        text += '\n\n' + self.tr('tools_deps_note')
        if messagebox.askyesno(APP_NAME, text + '\n\n' + self.tr('tools_question'), parent=self.app):
            self.install_build_tools(missing, retry)
        return False

    def install_build_tools(self, missing, retry):
        """Install in a worker; a small window follows the downloads and steps."""
        from . import updater
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('tools_title')}")
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        window.protocol('WM_DELETE_WINDOW', lambda: None)   # the installer cannot be interrupted midway
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('tools_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 10, 'bold')).pack(anchor='w')
        step = tk.Label(body, text=self.tr('tools_preparing'), bg=background, fg=COLORS['text'],
                        font=(self.ui_font, 9), wraplength=440, justify='left')
        step.pack(anchor='w', pady=(10, 6))
        bar = ttk.Progressbar(body, length=440, mode='determinate')
        bar.pack(fill='x')
        detail = tk.Label(body, text='', bg=background, fg=COLORS['muted'], font=(self.ui_font, 8),
                          wraplength=440, justify='left')
        detail.pack(anchor='w', pady=(6, 0))
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.deiconify()
        state = {'label': '', 'done': 0, 'total': 0, 'step': '', 'result': None}
        self.updating = True
        self.set_controls(False)
        # The shared pieces (engine sources, Z80 → C translator, static SDL2)
        # follow the tools, so the first conversion starts at once.
        steps = {'Téléchargement de smsggrecomp…': 'deps_step_engine', 'Téléchargement de SDL…': 'deps_step_sdl_fetch',
                 'Compilation du traducteur Z80 → C…': 'deps_step_translator',
                 'Compilation de SDL2 statique (première utilisation)…': 'deps_step_sdl'}

        def progress(label, done, total):
            state.update(label=label, done=done, total=total)

        def worker():
            try:
                if os.name == 'nt':
                    if missing.get('git'):
                        updater.install_git(progress)
                    if missing.get('compiler'):
                        updater.install_toolchain(progress)
                elif missing.get('packages'):
                    updater.install_linux_packages(missing['packages'], progress)
                from .core import dependencies, dependencies_ready, reset_stop
                if not dependencies_ready():
                    reset_stop()
                    state.update(label='', total=0, step='deps_step_start')
                    dependencies(emit=lambda text: state.update(step=steps.get(text, text)))
                state['result'] = ('ok', None)
            except updater.ToolInstallError as error:
                state['result'] = ('failed', str(error))
            except Exception as error:
                state['result'] = ('failed', str(error) or type(error).__name__)

        def poll():
            if not window.winfo_exists():
                return
            label, done, total = state['label'], state['done'], state['total']
            if label and total:
                if str(bar.cget('mode')) != 'determinate':
                    bar.stop()
                    bar.configure(mode='determinate')
                bar.configure(maximum=total, value=done)
                if label in ('Download', 'Install'):
                    step.configure(text=self.tr('tools_step_packages' if label == 'Install' else 'tools_step_fetch'))
                    detail.configure(text=f'{done * 100 // max(total, 1)} %')
                else:
                    step.configure(text=self.tr('tools_step_download', name=label))
                    detail.configure(text=f'{done / 1048576:.1f} / {total / 1048576:.1f} MB')
            elif state['step']:
                if str(bar.cget('mode')) != 'indeterminate':
                    bar.configure(mode='indeterminate')
                    bar.start(12)
                key = state['step']
                step.configure(text=self.tr(key) if key in STRINGS else log_text(key, self.language))
                detail.configure(text=self.tr('deps_step_hint'))
            if state['result'] is None:
                window.after(150, poll)
                return
            bar.stop()
            window.destroy()
            self.updating = False
            self.set_controls(True)
            outcome, error = state['result']
            if outcome == 'ok':
                self.messages.put(('log', self.tr('tools_done')))
                messagebox.showinfo(APP_NAME, self.tr('tools_done'), parent=self.app)
                retry()
            else:
                manual = (self.tr('tools_manual_windows') if os.name == 'nt' else
                          'sudo ' + ' '.join(updater.linux_install_command(missing.get('packages', ()))))
                messagebox.showerror(APP_NAME, self.tr('tools_failed', error=error) + '\n\n' + manual,
                                     parent=self.app)

        threading.Thread(target=worker, daemon=True).start()
        poll()
