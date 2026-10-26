"""The converter's persistent collection view, shared by Windows and Linux."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .branding import COLORS
from .compiled_games import LEVEL_STARS, Game, default_roots, scan, refresh
from .paths import APP_NAME
from .platforms import open_local, target_id
from .systems import available_profiles, get_profile
PROFILES = available_profiles()
import subprocess

ATTENTION = {'new_hints', 'fallback', 'changed', 'unreadable'}
# The consoles whose games the online service takes (conversion rewards).
SHARED_CONSOLES = ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng')


def base_key(game) -> str:
    """How the shared base names this game: 'system:identity', except Neo Geo,
    named by cartridge and BIOS together, which only its report holds."""
    if game.system == 'ng' and game.report:
        from .knowledge_exchange import report_game_key
        identity = report_game_key(game.report)[0]
        if identity:
            return f'ng:{identity}'
    return f'{game.system}:{game.identity}'


# The states filter: its last entry lists the games nobody finished at the Thorough level yet.
STATES = ('all_games', 'needs_attention', 'with_hints', 'missing_games', 'games_to_explore')
EXPLORE = STATES.index('games_to_explore')


def stars(level):
    """Three small stars, lit for Standard, Extended and Thorough ('' while unknown)."""
    lit = LEVEL_STARS.get(level, 0)
    return '★' * lit + '☆' * (3 - lit) if lit else ''


class CompiledGamesView(ttk.Frame):
    def __init__(self, owner, parent):
        super().__init__(parent, padding=(24, 0, 24, 0))
        self.owner, self.tr, self.inventory = owner, owner.tr, owner.compiled_inventory
        self.events, self.running = queue.Queue(), False
        self.relocation_attempted = False
        self.render_token = 0
        self.sort_key, self.reverse = 'title', False
        self.rows = {}
        self.game_process = None
        self.controller = None
        from .player_gamepad import Navigation
        self.navigation = Navigation()
        # The collection's actions share the main toolbar, right after the
        # queue/collection switch, instead of a second row of buttons.
        bar = owner.collection_actions
        self.play_button = ttk.Button(bar,text=self.tr('play'),command=self.play,style='Toolbar.Primary.TButton')
        owner.decorate_button(self.play_button,'play',True)
        self.play_button.pack(side='left')
        # Pictures only, named by their hints; the view enables them itself.
        self.scan_button = owner.icon_button(bar,'scan_games','tip_scan_games',self.scan,'refresh',managed=False)
        self.scan_button.pack(side='left',padx=(8,0))
        self.add_button = owner.icon_button(bar,'scan_folder','tip_scan_folder',self.add_folder,'add_exe_folder',managed=False)
        self.add_button.pack(side='left',padx=(6,0))
        self.stop_button = owner.icon_button(bar,'stop','tip_stop',owner.stop,'stop',managed=False)
        self.summary = tk.StringVar()
        filters = ttk.Frame(self)
        filters.pack(fill='x',pady=(0,8))
        ttk.Label(filters,textvariable=self.summary,style='Muted.TLabel').pack(side='right',padx=(12,0))
        self.console, self.state, self.search = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.consoles = ttk.Combobox(filters,textvariable=self.console,state='readonly',width=22)
        self.consoles.pack(side='left')
        self.states = ttk.Combobox(filters,textvariable=self.state,state='readonly',width=27)
        self.states.pack(side='left',padx=8)
        self.favorites = tk.BooleanVar(value=False)
        self.favorite_filter = ttk.Checkbutton(filters,text=self.tr('favorites_only'),variable=self.favorites,command=self.render)
        self.favorite_filter.pack(side='left',padx=(0,8))
        ttk.Label(filters,text=self.tr('search')).pack(side='left',padx=(8,6))
        search = ttk.Entry(filters,textvariable=self.search)
        search.pack(side='left',fill='x',expand=True)
        self.search_after = None
        self.search.trace_add('write',self.search_changed)
        self.consoles.bind('<<ComboboxSelected>>',lambda e:self.render())
        self.states.bind('<<ComboboxSelected>>',lambda e:self.states_changed())
        panes = ttk.Panedwindow(self,orient='horizontal')
        panes.pack(fill='both',expand=True)
        frame = ttk.Frame(panes)
        panes.add(frame,weight=3)
        from .game_card_view import GameCardView
        self.card = GameCardView(panes,owner)
        panes.add(self.card,weight=1)
        self.after_idle(lambda:panes.sashpos(0,max(460,self.winfo_width()-340)))
        self.columns = ('favorite','title','system','level','version','hints','status')
        # The games someone already finished at the Thorough level (online.explored), once asked.
        self.explored = None
        self.table = ttk.Treeview(frame,columns=self.columns,show='headings',selectmode='extended')
        for key,width in zip(self.columns,(36,200,115,62,95,75,200)):
            self.table.column(key,width=width,minwidth=32 if key=='favorite' else 65,stretch=key in ('title','status'),anchor='center' if key=='favorite' else 'w')
            self.table.heading(key,command=lambda k=key:self.sort(k))
        bar = ttk.Scrollbar(frame,command=self.table.yview)
        self.table.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.table.pack(fill='both',expand=True)
        for tag,background,color in (('new_hints','#382e1d',COLORS['gold_hover']),
                ('fallback','#332724',COLORS['error']),('missing',COLORS['field'],COLORS['disabled']),
                ('changed','#332724',COLORS['error']),('unreadable','#332724',COLORS['error']),
                ('covered','#202b23',COLORS['success'])):
            self.table.tag_configure(tag,background=background,foreground=color)
        self.table.tag_configure('odd',background='#1e1e1e')
        self.table.bind('<Button-3>',self.context_menu)
        self.table.bind('<Button-1>',self.star_clicked)
        self.table.bind('<Double-1>',lambda e:self.play())
        self.table.bind('<<TreeviewSelect>>',self.selection)
        self.table.bind('<Return>',lambda e:self.play())
        bottom = ttk.Frame(self)
        bottom.pack(fill='x',pady=(10,0))
        self.status = tk.StringVar()
        ttk.Label(bottom,textvariable=self.status,style='Muted.TLabel',wraplength=820).pack(side='left')
        self.progress = ttk.Progressbar(self,mode='indeterminate')
        self.progress.pack(fill='x',pady=(7,4))
        # The last one or two converter lines, quiet and unframed.
        self.log_lines = deque(maxlen=2)
        self.log_text = tk.StringVar()
        self.log_label = ttk.Label(self,textvariable=self.log_text,style='Muted.TLabel',
                                   font=('Consolas',8),justify='left')
        self.detail = tk.StringVar(value=self.tr('compiled_hint'))
        self.detail_label = ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1000)
        self.detail_label.pack(anchor='w')
        self.localize()
        self.render()
        self.after(80,self.drain)
        self.played = None
        self.after(1000,self.watch_played)
        self.after_idle(self.relocate)
        self.after_idle(self.start_controller)
        self.bind('<Destroy>',self.close_controller,add=True)

    def start_controller(self):
        try:
            from .player_gamepad import Controller
            self.controller = Controller()
        except (OSError, AttributeError):
            # Mouse and keyboard remain available on hosts with no controller
            # backend. A packaged app supplies the small native SDL bridge.
            return
        self.after(40,self.poll_controller)

    def close_controller(self,event=None):
        if event is not None and event.widget is not self:return
        if self.controller:
            self.controller.close()
            self.controller = None

    def poll_controller(self):
        if not self.winfo_exists() or not self.controller:return
        active = self.game_process is not None and self.game_process.poll() is None
        if self.game_process is not None and not active:
            self.game_process = None
        focus = self.focus_displayof()
        enabled = (self.winfo_viewable() and not active and not self.running
            and not self.owner.busy and not self.owner.updating and focus is not None
            and focus.winfo_toplevel() is self.owner.app and self.grab_current() is None)
        try:
            action = self.navigation.update(self.controller.poll(),time.monotonic(),enabled)
        except OSError:
            self.close_controller(); return
        if action == 'play':self.play()
        elif action in (-1,1):
            rows = self.table.get_children()
            if rows:
                current = self.table.focus()
                index = rows.index(current) if current in rows else (-1 if action==1 else len(rows))
                row = rows[max(0,min(len(rows)-1,index+action))]
                self.table.selection_set(row)
                self.table.focus(row)
                self.table.see(row)
        self.after(40,self.poll_controller)

    def quiet_refresh(self, games=None, every=0):
        """Re-read only rows whose files changed (see the application)."""
        if not self.running:
            self.owner.quiet_refresh_collection(games, every)

    def watch_played(self):
        """A game launched from Play wrote its discoveries on exit: show them."""
        if not self.winfo_exists():return
        process = self.game_process
        if self.played is not None and (process is None or process.poll() is not None):
            played, self.played = self.played, None
            self.quiet_refresh([played])
        self.after(1000,self.watch_played)

    def relocate(self):
        if (self.inventory.relocation_pending and not self.relocation_attempted
                and not self.running and not self.owner.busy and not self.owner.updating):
            self.relocation_attempted = True
            self.work(self.inventory.relocate)

    def localize(self):
        self.play_button.configure(text=self.tr('play'))
        self.scan_button.configure(text=self.tr('scan_games'))
        self.add_button.configure(text=self.tr('scan_folder'))
        self.stop_button.configure(text=self.tr('stop'))
        self.card.localize()
        self.favorite_filter.configure(text=self.tr('favorites_only'))
        self.consoles.configure(values=[self.tr('all_consoles'),*[p.name for p in PROFILES]])
        self.consoles.current(0)
        self.states.configure(values=[self.tr(k) for k in STATES])
        self.states.current(0)
        for key,label in zip(self.columns,('favorite_star','game','console','scan_stars','build_version','saved_hints','conversion')):
            self.table.heading(key,text=self.tr(label))

    def sort(self,key):
        self.reverse = not self.reverse if key == self.sort_key else False
        self.sort_key = key
        self.render()

    def search_changed(self,*args):
        if self.search_after: self.after_cancel(self.search_after)
        self.search_after = self.after(160,self.render)

    def render(self):
        self.search_after = None
        self.conversion_state()
        self.render_token += 1
        token = self.render_token
        selected = {self.rows[r].key for r in self.table.selection() if r in self.rows}
        self.rows = {}
        self.table.delete(*self.table.get_children())
        all_games = self.inventory.snapshot()
        self.summary.set(self.tr('compiled_summary',count=len(all_games),
            attention=sum(g.status in ATTENTION for g in all_games),
            hints=sum(g.hints for g in all_games)))
        self.owner.update_new_paths()
        system = self.consoles.current()-1
        state = self.states.current()
        text = self.search.get().casefold().strip()
        explored = (self.explored or {}).get('games') or {}
        games = [g for g in all_games if (system<0 or g.system==PROFILES[system].id)
            and (not self.favorites.get() or g.favorite)
            and (state!=1 or g.status in ATTENTION) and (state!=2 or g.hints)
            and (state!=3 or g.status=='missing')
            and (state!=EXPLORE or self.to_explore(g, explored)) and (not text or text in
                (g.title+' '+get_profile(g.system).name+' '+g.identity).casefold())]
        key = lambda g:((not g.favorite,g.title.casefold()) if self.sort_key=='favorite' else get_profile(g.system).name if self.sort_key=='system' else
                       self.tr('game_'+g.status) if self.sort_key=='status' else LEVEL_STARS.get(g.level,0) if self.sort_key=='level'
                       else getattr(g,self.sort_key))
        games.sort(key=key,reverse=self.reverse)
        def insert(start=0):
            if token != self.render_token or not self.winfo_exists():return
            for index,g in enumerate(games[start:start+60],start):
                row = self.table.insert('','end',values=('★' if g.favorite else '☆',g.title,get_profile(g.system).name,
                    stars(g.level),g.version or '—',g.hints,self.tr('game_'+g.status)),tags=('odd',g.status) if index%2 else (g.status,))
                self.rows[row] = g
                if g.key in selected:self.table.selection_add(row)
            if start+60<len(games):self.after(1,lambda:insert(start+60))
        insert()
        self.status.set(self.tr('games_count',count=len(games)) if games else self.tr('compiled_empty'))
        if state==EXPLORE:
            # What the first one to finish a game at the Thorough level earns (the server's figure).
            bonus = (self.explored or {}).get('explorer')
            self.status.set(self.tr('explore_status',count=len(games),coins=bonus if bonus is not None else '—')
                            if self.explored is not None else self.tr('explore_loading'))
        labels = ('favorite_star','game','console','scan_stars','build_version','saved_hints','conversion')
        for key,label in zip(self.columns,labels):
            self.table.heading(key,text=self.tr(label)+('  ▼' if self.reverse else '  ▲') if key==self.sort_key else self.tr(label))

    @staticmethod
    def to_explore(game, explored):
        """A game of a console the service takes that nobody has finished at the
        Thorough level yet (this player included)."""
        return (game.system in SHARED_CONSOLES and game.level != 'thorough'
                and base_key(game) not in explored)

    def states_changed(self):
        """The states filter; "Games to explore" asks the service once (cached half an hour)."""
        if self.states.current()==EXPLORE and self.explored is None:
            from . import online
            def worker():
                try:
                    found = online.explored() if online.sending_available() else {'games': {}, 'explorer': None}
                except Exception:
                    found = {'games': {}, 'explorer': None}
                self.events.put(('explored', found))
            threading.Thread(target=worker,daemon=True).start()
        self.render()

    def star_clicked(self,event):
        if self.running:return 'break'
        row=self.table.identify_row(event.y)
        if row in self.rows and self.table.identify_column(event.x)=='#1':
            game=self.rows[row]
            self.inventory.set_favorite(game,not game.favorite)
            self.render()
            return 'break'

    def toggle_favorites(self):
        games=self.chosen()
        value=not all(g.favorite for g in games)
        for game in games:self.inventory.set_favorite(game,value)
        self.render()

    def selection(self,event=None):
        games = self.chosen()
        if len(games)==1:
            g = games[0]
            self.detail.set(f'{g.executable}  ·  {g.target or "—"}')
        else:self.detail.set(self.tr('compiled_hint'))
        self.card.select(games[0] if len(games)==1 else None)

    def chosen(self):
        return [self.rows[r] for r in self.table.selection() if r in self.rows]

    def context_menu(self,event):
        row = self.table.identify_row(event.y)
        if not row:return
        if row not in self.table.selection():self.table.selection_set(row)
        menu = tk.Menu(self,tearoff=False,bg=COLORS['button'],fg=COLORS['text'],
                       activebackground=COLORS['selected'],activeforeground=COLORS['gold_hover'])
        menu.add_command(label=self.tr('play'),command=self.play)
        menu.add_command(label=self.tr('favorite_remove' if all(g.favorite for g in self.chosen()) else 'favorite_add'),command=self.toggle_favorites)
        menu.add_command(label=self.tr('card_fetch_info'),command=lambda:self.card.search_games(self.chosen()),
                         state='disabled' if self.card.pending else 'normal')
        menu.add_separator()
        menu.add_command(label=self.tr('reconvert'),command=lambda:self.owner.reconvert_games(self.chosen()),
                         state='disabled' if self.running or self.owner.busy or self.owner.updating else 'normal')
        menu.add_command(label=self.tr('rescan'),command=self.rescan,
                         state='disabled' if self.running else 'normal')
        # Go further: a discovery at the Extended or Thorough level, with the coins it may bring.
        chosen = self.chosen()
        idle = not (self.running or self.owner.busy or self.owner.updating)
        depth = ((self.explored or {}).get('depth') or {})
        for level,coins in (('extended',depth.get('extended',20)),('thorough',depth.get('thorough',40))):
            deeper = [g for g in chosen if LEVEL_STARS.get(g.level,1) < LEVEL_STARS[level]]
            if deeper:
                shared = all(g.system in SHARED_CONSOLES for g in deeper)
                menu.add_command(label=self.tr('go_further_'+level+('_coins' if shared else ''),coins=coins),
                                 command=lambda games=deeper,level=level:self.owner.go_deeper(games,level),
                                 state='normal' if idle else 'disabled')
        menu.add_command(label=self.tr('open_folder'),command=lambda:open_local(Path(self.chosen()[0].executable).parent))
        menu.add_separator()
        # A game that was created but is wrong: the report carries its conversion report.
        menu.add_command(label=self.tr('report_problem'),command=lambda:self.owner.report_game_problem(self.chosen()[0]),
                         state='normal' if len(self.chosen())==1 and self.owner.report_available() else 'disabled')
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def play(self):
        if self.running:return
        if self.game_process is not None and self.game_process.poll() is None:return
        games = self.chosen()
        if len(games)!=1:return
        game = games[0]
        if game.target != target_id():
            messagebox.showinfo(APP_NAME,self.tr('game_other_platform'),parent=self.owner.app)
            return
        try:
            path = Path(game.executable)
            self.game_process = subprocess.Popen([str(path)],cwd=path.parent)
            self.played = game
        except OSError:
            messagebox.showerror(APP_NAME,self.tr('game_launch_failed'),parent=self.owner.app)

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self.owner.app,title=self.tr('scan_folder'))
        if folder:
            path = str(Path(folder).resolve())
            if path not in self.inventory.roots:self.inventory.roots.append(path)
            self.scan()

    def scan(self):
        preferences = self.owner.preferences()
        roots = [*default_roots(preferences),*map(Path,self.inventory.roots)]
        self.work(lambda:scan(self.inventory,roots,preferences,
            progress=lambda n:self.events.put(('progress',n))))

    def rescan(self):
        games, preferences = self.chosen(), self.owner.preferences()
        def worker():
            for game in games:
                self.inventory.remember(refresh(Game(**asdict(game)),preferences,verify_binary=True))
            self.inventory.save()
            return len(games)
        if games:self.work(worker)

    def work(self,callback):
        if self.running or self.owner.busy or self.owner.updating:return
        self.running = True
        self.scan_button.configure(state='disabled')
        self.add_button.configure(state='disabled')
        self.progress.start(15)
        self.status.set(self.tr('scanning_games'))
        def worker():
            try:self.events.put(('done',callback()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def drain(self):
        self.conversion_state()
        self.relocate()
        try:
            while True:
                kind,value = self.events.get_nowait()
                if kind=='progress':self.status.set(self.tr('scanned_games',count=value))
                elif kind=='explored':
                    self.explored = value
                    self.render()
                else:
                    self.running = False
                    self.progress.stop()
                    self.scan_button.configure(state='normal')
                    self.add_button.configure(state='normal')
                    self.render()
                    if kind=='error':self.status.set(self.tr('scan_failed'))
        except queue.Empty:pass
        self.after(100,self.drain)

    def show_log(self, text):
        """Keep the latest converter lines, one screen line each."""
        for line in str(text).splitlines() or ['']:
            line = line.strip()
            if line:self.log_lines.append(line if len(line) <= 150 else line[:149] + '\u2026')
        self.log_text.set('\n'.join(self.log_lines))
        if self.log_lines and not self.log_label.winfo_manager():
            self.log_label.pack(anchor='w',pady=(0,4),before=self.detail_label)

    def clear_log(self):
        self.log_lines.clear()
        self.log_text.set('')
        self.log_label.pack_forget()

    def conversion_state(self):
        if self.owner.busy:
            if not self.stop_button.winfo_manager():self.stop_button.pack(side='left',padx=(6,0))
        else:self.stop_button.pack_forget()
        state='disabled' if self.running or self.owner.busy or self.owner.updating else 'normal'
        self.scan_button.configure(state=state)
        self.add_button.configure(state=state)
