"""The player corner: account menu, sign-in, pseudonym and the header player."""
from __future__ import annotations

import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__, online
from .paths import APP_NAME
from .branding import COLORS
from .gui_common import SENDING_AVAILABLE, typed_pseudonym
from .gui_drawing import compact_number, _portrait_photo


class AccountMixin:
    """The player corner: account menu, sign-in, pseudonym and the header player."""

    def sign_out(self):
        if self.busy or self.updating:return
        signed = online.account() or {}
        if not messagebox.askyesno(APP_NAME, self.tr('account_sign_out_confirm', email=signed.get('email', '')),
                                   icon='question', default='no', parent=self.app):
            return
        self.knowledge_task(lambda:(online.sign_out(), ('signed_out', None))[1], 'knowledge_working')

    # --- The player's corner of the header ---------------------------------

    def count_text(self, value):
        return compact_number(value, self.language)

    def open_site_page(self, page):
        """A page of the site in the web browser; coming back to the window
        then reads the account again soon (focus_player)."""
        if SENDING_AVAILABLE:
            self.site_opened = time.monotonic()
            webbrowser.open_new_tab(online.service_url() + page)

    def open_account_site(self):
        """The player's account page on the site, in the web browser."""
        self.open_site_page('/account')

    def open_account_shop(self):
        """The shop section of the account page (its anchor on the site)."""
        self.open_site_page('/account#shop')

    def open_account_items(self):
        """"Manage my items": the account page's My items (buy, equip, remove)."""
        self.open_site_page('/account#items')

    def account_menu(self, event):
        """Right-click on the account corner: the site's pages and the pseudonym."""
        if not SENDING_AVAILABLE or not online.account():
            return
        menu = tk.Menu(self.app, tearoff=False, bg=COLORS['button'], fg=COLORS['text'],
                       activebackground=COLORS['selected'], activeforeground=COLORS['gold_hover'])
        menu.add_command(label=self.tr('account_items_site'), command=self.open_account_items)
        menu.add_command(label=self.tr('account_open_site'), command=self.open_account_site)
        menu.add_command(label=self.tr('account_pseudonym_change'), command=self.pseudonym_dialog,
                         state='disabled' if self.busy or self.updating else 'normal')
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def pseudonym_clicked(self):
        """The name in the header: while the pseudonym is a generated one, choose one."""
        profile = (self.player or {}).get('profile') or {}
        if SENDING_AVAILABLE and online.account() and not online.pseudonym_chosen(profile) and not (self.busy or self.updating):
            self.pseudonym_dialog()

    def focus_player(self, now=None):
        """The window is in front again: the player's corner is read again when
        its last reading is PLAYER_REFRESH old, or 15 s after a page of the site
        was opened from here (a purchase, an item equipped, a new portrait);
        never more often, and never two readings at once. `now`: the
        time.monotonic() to use (the checks pass their own clock)."""
        if not SENDING_AVAILABLE or self.player_refreshing or not online.account():
            return
        now = time.monotonic() if now is None else now
        last = self.player_checked
        if last is None:
            return   # the start-up reading has not run yet
        wait = 15 if self.site_opened > last else online.PLAYER_REFRESH
        if now - last >= wait:
            self.refresh_player(force=True)

    def portrait_clicked(self):
        """Signed in: the account page on the site; signed out: the sign-in."""
        if not SENDING_AVAILABLE:
            return
        if online.account():
            self.open_account_site()
        elif not (self.busy or self.updating):
            self.sign_in_dialog()

    def sign_in_from_header(self):
        """The header's second button: sign in, or sign out once signed in."""
        if self.busy or self.updating or not SENDING_AVAILABLE:return
        if online.account():
            self.sign_out()
        else:
            self.sign_in_dialog()

    def refresh_player(self, force=False):
        """Show the player's corner from the local cache at once, then, off Tk,
        refresh it from the site only when it is older than PLAYER_REFRESH (2
        minutes), or at once with `force` (a sign-in, a send, back from the
        site). Without an account, nothing is fetched. One reading at a time:
        a forced one asked for while another runs starts once it ends (its
        answer may predate a send); an ordinary one is then not needed."""
        if not SENDING_AVAILABLE or not online.account():
            self.render_player(None)
            return
        cached = online.cached_player()
        if cached:
            self.render_player(cached)
        if self.player_refreshing:
            self.player_refresh_queued = self.player_refresh_queued or force
            return
        self.player_checked = time.monotonic()
        self.player_refreshing = True
        self.player_generation += 1
        generation = self.player_generation
        def worker():
            try:
                data = online.player(force=force) or {'account': online.account()}
            except (online.ServiceError, online.ServiceConnectionError) as error:
                # Offline: the last known corner stays as it is.
                data = None if cached else {'account': online.account(), 'error': self.online_message(error)}
            except Exception:
                data = None
            self.messages.put(('player', data, generation))
        threading.Thread(target=worker, daemon=True).start()

    def player_read(self, data, generation):
        """A reading of the account ended (on Tk): draw it (None keeps the
        corner), log what waits after a send, then start a forced reading
        asked for meanwhile."""
        if generation == self.player_generation:
            self.player_refreshing = False
        if data is not None:
            self.render_player(data)
            self.log_queued(data, generation)
        if not self.player_refreshing and self.player_refresh_queued:
            self.player_refresh_queued = False
            self.refresh_player(force=True)

    def title_name(self, title):
        """A title from the site ({'id', 'name': {language: text}}) in the
        interface language, else English, else any; '' without one."""
        names = title.get('name') if isinstance(title, dict) else None
        if not isinstance(names, dict):
            return ''
        for code in (self.language, 'en', *sorted(names)):
            if isinstance(names.get(code), str) and names[code].strip():
                return names[code].strip()[:48]
        return ''

    @staticmethod
    def coin_balance(profile):
        """The RR coins balance of `GET account`, or None before the site says."""
        coins = profile.get('coins') if isinstance(profile, dict) else None
        balance = coins.get('balance') if isinstance(coins, dict) else None
        return balance if type(balance) is int else None

    def render_player(self, data=...):
        """Draw the account corner from the last answer: a portrait, the
        pseudonym (or the e-mail's user name), points and rank; or the
        invitation to sign in, disabled until the online service opens."""
        if data is not ...:
            self.player = data or {}
        self.update_account_options()
        player = self.player
        account = player.get('account') or (online.account() if SENDING_AVAILABLE else None)
        header = self.header
        for child in self.player_actions.winfo_children():
            child.pack_forget()
        # The shop items the account equips, drawn when the catalog knows them.
        profile = player.get('profile') or {}
        self.looks = online.looks(player.get('shop') or {}, online.equipped(profile) if account else {})
        if not account:
            self.portrait = _portrait_photo(self.app)
            header.itemconfigure(self.portrait_item, image=self.portrait)
            header.itemconfigure(self.player_name, text=self.tr('account_not_signed'))
            header.itemconfigure(self.player_title, text='')
            header.itemconfigure(self.player_score,
                                 text=self.tr('account_invite') if SENDING_AVAILABLE else self.tr('account_coming'))
            self.board_button.configure(state='normal' if SENDING_AVAILABLE else 'disabled')
            self.sign_in_button.configure(text=self.tr('account_sign_in'),
                                          state='normal' if SENDING_AVAILABLE else 'disabled')
            self.board_button.pack(side='top', fill='x')
            self.sign_in_button.pack(side='top', fill='x', pady=(4, 0))
            self.app.after_idle(self.layout_header)
            return
        name = profile.get('pseudonym') or account.get('pseudonym') or str(account.get('email', '')).split('@')[0]
        frame = self.looks.get('frame')
        frame = (player['frame'], frame['data'].get('hole')) if frame and player.get('frame') else None
        self.portrait = _portrait_photo(self.app, player.get('avatar'), name[:1], frame)
        header.itemconfigure(self.portrait_item, image=self.portrait)
        header.itemconfigure(self.player_name, text=name)
        header.itemconfigure(self.player_title, text=self.title_name(profile.get('title')))
        you = (player.get('board') or {}).get('you') or {}
        if player.get('error'):
            score = player['error']
        elif (player.get('board') or {}).get('demo'):
            score = self.tr('account_board_soon')
        elif you.get('rank'):
            score = self.tr('account_points', points=self.count_text(you.get('total', 0)), rank=you['rank'])
        else:
            score = self.tr('account_unranked', points=self.count_text(you.get('total', 0)))
        coins = self.coin_balance(profile)
        if coins is not None and not player.get('error'):
            score += ' · ' + self.tr('account_coins', coins=self.count_text(coins))
        if you.get('pending'):
            score += '\n' + self.tr('account_pending', count=self.count_text(you['pending']))
        if not online.pseudonym_chosen(profile) and not player.get('error'):
            score += '\n' + self.tr('account_pseudonym_hint')
        header.itemconfigure(self.player_score, text=score)
        self.board_button.configure(state='normal')
        self.sign_in_button.configure(text=self.tr('account_sign_out'), state='normal')
        self.board_button.pack(side='top', fill='x')
        self.sign_in_button.pack(side='top', fill='x', pady=(4, 0))
        self.app.after_idle(self.layout_header)

    def sign_in_dialog(self):
        """E-mail, then the e-mailed code; True once this converter has a token."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('signin_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        tk.Label(body, text=self.tr('signin_intro'), bg=background, fg=COLORS['text'], font=(self.ui_font, 9),
                 wraplength=400, justify='left').grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 12))
        tk.Label(body, text=self.tr('signin_email'), bg=background, fg=COLORS['muted'],
                 font=(self.ui_font, 9)).grid(row=2, column=0, columnspan=2, sticky='w')
        email = tk.StringVar(value=(online.account() or {}).get('email', ''))
        email_field = ttk.Entry(body, textvariable=email, width=44)
        email_field.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(2, 8))
        terms = tk.BooleanVar(value=False)
        consent = tk.Frame(body, bg=background)
        consent.grid(row=4, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(consent, text=self.tr('signin_terms'), variable=terms).pack(side='left')
        privacy = tk.Label(consent, text=self.tr('signin_privacy'), bg=background, fg=COLORS['gold_hover'],
                           font=(self.ui_font, 9, 'underline'), cursor='hand2')
        privacy.pack(side='left', padx=(8, 0))
        privacy.bind('<Button-1>', lambda event:webbrowser.open_new_tab(online.service_url() + '/privacy'))
        code_label = tk.Label(body, text=self.tr('signin_code'), bg=background, fg=COLORS['muted'],
                              font=(self.ui_font, 9))
        code = tk.StringVar()
        code_field = ttk.Entry(body, textvariable=code, width=12)
        # With the code: the pseudonym of a new account (or of one without any), proposed and editable.
        pseudonym_label = tk.Label(body, text=self.tr('signin_pseudonym'), bg=background, fg=COLORS['muted'],
                                   font=(self.ui_font, 9))
        proposed = online.suggested_pseudonym()
        pseudonym = tk.StringVar(value=proposed)
        pseudonym_field = ttk.Entry(body, textvariable=pseudonym, width=26)
        self.hint(pseudonym_field, 'tip_signin_pseudonym')
        message = tk.StringVar()
        tk.Label(body, textvariable=message, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=400, justify='left').grid(row=7, column=0, columnspan=2, sticky='w', pady=(10, 0))
        buttons = tk.Frame(body, bg=background)
        buttons.grid(row=8, column=0, columnspan=2, sticky='e', pady=(14, 0))
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text=self.tr('signin_send_code'), style='Primary.TButton')
        go.pack(side='right', padx=(0, 8))
        state = {'stage': 'email', 'signed': False}
        def run(call, done):
            # The network call runs off Tk; the dialog polls for its answer.
            go.state(['disabled'])
            answer = {}
            def worker():
                try:answer['value'] = call()
                except Exception as error:answer['error'] = error
            threading.Thread(target=worker, daemon=True).start()
            def wait():
                if not window.winfo_exists():return
                if not answer:
                    window.after(100, wait)
                    return
                go.state(['!disabled'])
                if 'error' in answer:message.set(self.online_message(answer['error']))
                else:done(answer['value'])
            wait()
        def code_sent(_):
            state['stage'] = 'code'
            message.set(self.tr('signin_code_sent', email=email.get().strip()))
            code_label.grid(row=5, column=0, sticky='w', pady=(10, 0))
            code_field.grid(row=6, column=0, sticky='w', pady=(2, 0))
            pseudonym_label.grid(row=5, column=1, sticky='w', padx=(16, 0), pady=(10, 0))
            pseudonym_field.grid(row=6, column=1, sticky='w', padx=(16, 0), pady=(2, 0))
            go.configure(text=self.tr('signin_submit'))
            code_field.focus_set()
        def signed_in(data):
            state['signed'] = True
            self.messages.put(('log', self.tr('signin_done', email=data['email'])))
            window.destroy()
            self.refresh_player(force=True)
            # No pseudonym given and none on the account: it was generated; ask once now.
            if data.get('pseudonym_chosen') is False:
                self.app.after_idle(self.pseudonym_dialog)
        def submit():
            address = email.get().strip()
            if state['stage'] == 'email' or not code.get().strip():
                if not terms.get():
                    message.set(self.tr('online_terms_needed'))
                    return
                run(lambda:online.request_code(address, self.language), code_sent)
            else:
                from .platforms import target_id
                name = typed_pseudonym(pseudonym.get(), proposed)
                if name and not online.valid_pseudonym(name):
                    message.set(self.tr('online_pseudonym_invalid'))
                    return
                run(lambda:online.sign_in(address, code.get().strip(), f'Retro-Recomp {__version__} ({target_id()})',
                                          pseudonym=name),
                    signed_in)
        go.configure(command=submit)
        window.bind('<Escape>', lambda event:window.destroy())
        window.bind('<Return>', lambda event:go.invoke())
        window.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - window.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        window.grab_set()
        email_field.focus_set()
        self.app.wait_window(window)
        return state['signed']

    def pseudonym_dialog(self):
        """Choose the public pseudonym (PATCH account): proposed with the
        current one; while it is a generated one, keeping it also counts as a
        choice. True once saved."""
        current = online.account()
        if not SENDING_AVAILABLE or not current:
            return False
        profile = (self.player or {}).get('profile') or {}
        name_now = str(profile.get('pseudonym') or current.get('pseudonym') or '')
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('pseudonym_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).pack(anchor='w')
        generated = not online.pseudonym_chosen(profile)
        tk.Label(body, text=self.tr('pseudonym_intro_generated' if generated else 'pseudonym_intro', name=name_now),
                 bg=background, fg=COLORS['text'], font=(self.ui_font, 9), wraplength=400,
                 justify='left').pack(anchor='w', pady=(8, 10))
        name = tk.StringVar(value=name_now)
        field = ttk.Entry(body, textvariable=name, width=36)
        field.pack(anchor='w')
        tk.Label(body, text=self.tr('pseudonym_rules'), bg=background, fg=COLORS['muted'], font=(self.ui_font, 8),
                 wraplength=400, justify='left').pack(anchor='w', pady=(4, 0))
        message = tk.StringVar()
        tk.Label(body, textvariable=message, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=400, justify='left').pack(anchor='w', pady=(8, 0))
        buttons = tk.Frame(body, bg=background)
        buttons.pack(anchor='e', pady=(12, 0))
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text=self.tr('pseudonym_save'), style='Primary.TButton')
        go.pack(side='right', padx=(0, 8))
        state = {'saved': False}
        def save():
            chosen = ' '.join(name.get().split())
            if not online.valid_pseudonym(chosen):
                message.set(self.tr('online_pseudonym_invalid'))
                return
            go.state(['disabled'])
            answer = {}
            def worker():
                try:answer['value'] = online.set_pseudonym(chosen)
                except Exception as error:answer['error'] = error
            threading.Thread(target=worker, daemon=True).start()
            def wait():
                if not window.winfo_exists():return
                if not answer:
                    window.after(100, wait)
                    return
                go.state(['!disabled'])
                if 'error' in answer:
                    message.set(self.online_message(answer['error']))
                    return
                state['saved'] = True
                self.messages.put(('log', self.tr('pseudonym_saved', name=chosen)))
                window.destroy()
                self.refresh_player(force=True)
            wait()
        go.configure(command=save)
        window.bind('<Escape>', lambda event:window.destroy())
        window.bind('<Return>', lambda event:go.invoke())
        window.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - window.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        window.grab_set()
        field.focus_set()
        field.select_range(0, 'end')
        self.app.wait_window(window)
        return state['saved']
