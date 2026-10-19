"""The converter's persistent collection view, shared by Windows and Linux."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .branding import COLORS
from .compiled_games import Game, default_roots, scan, refresh
from .paths import APP_NAME
from .platforms import open_local, target_id
from .systems import PROFILES, get_profile
import subprocess

ATTENTION = {'new_hints', 'fallback', 'changed', 'unreadable'}


class CompiledGamesView(ttk.Frame):
    def __init__(self, owner, parent):
        super().__init__(parent, padding=(24, 8, 24, 0))
        self.owner, self.tr, self.inventory = owner, owner.tr, owner.compiled_inventory
        self.events, self.running = queue.Queue(), False
        self.render_token = 0
        self.sort_key, self.reverse = 'title', False
        self.rows = {}
        top = ttk.Frame(self)
        top.pack(fill='x', pady=(0,12))
        mark = tk.Canvas(top, width=42, height=40, bg=COLORS['background'], highlightthickness=0)
        mark.pack(side='left',padx=(0,10))
        mark.create_rectangle(1,3,38,36,outline=COLORS['gold'],width=1)
        mark.create_line(9,11,30,11,30,25,9,25,9,11,fill=COLORS['muted'])
        mark.create_line(20,25,20,30,14,30,26,30,fill=COLORS['gold'])
        title = ttk.Frame(top)
        title.pack(side='left')
        ttk.Label(title,text=self.tr('compiled_games'),font=(owner.ui_font,14,'bold')).pack(anchor='w')
        ttk.Label(title,text=self.tr('compiled_intro'),style='Muted.TLabel').pack(anchor='w')
        self.scan_button = ttk.Button(top,text=self.tr('scan_games'),command=self.scan,style='Primary.TButton')
        owner.decorate_button(self.scan_button,'refresh',True)
        self.scan_button.pack(side='right')
        self.stop_button = ttk.Button(top,text=self.tr('stop'),command=owner.stop)
        self.add_button = ttk.Button(top,text=self.tr('scan_folder'),command=self.add_folder)
        self.add_button.pack(side='right',padx=8)
        self.summary = tk.StringVar()
        strip = tk.Frame(self,bg=COLORS['panel'],padx=12,pady=10)
        strip.pack(fill='x',pady=(0,12))
        tk.Label(strip,textvariable=self.summary,bg=COLORS['panel'],fg=COLORS['gold'],
                 font=(owner.ui_font,10)).pack(anchor='w')
        filters = ttk.Frame(self)
        filters.pack(fill='x',pady=(0,10))
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
        self.states.bind('<<ComboboxSelected>>',lambda e:self.render())
        panes = ttk.Panedwindow(self,orient='horizontal')
        panes.pack(fill='both',expand=True)
        frame = ttk.Frame(panes)
        panes.add(frame,weight=3)
        from .game_card_view import GameCardView
        self.card = GameCardView(panes,owner)
        panes.add(self.card,weight=1)
        self.after_idle(lambda:panes.sashpos(0,max(460,self.winfo_width()-340)))
        self.columns = ('favorite','title','system','version','hints','status')
        self.table = ttk.Treeview(frame,columns=self.columns,show='headings',selectmode='extended')
        for key,width in zip(self.columns,(36,200,115,95,75,200)):
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
        self.progress.pack(fill='x',pady=(7,6))
        self.detail = tk.StringVar(value=self.tr('compiled_hint'))
        ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1000).pack(anchor='w')
        self.localize()
        self.render()
        self.after(80,self.drain)

    def localize(self):
        self.card.localize()
        self.favorite_filter.configure(text=self.tr('favorites_only'))
        self.consoles.configure(values=[self.tr('all_consoles'),*[p.name for p in PROFILES]])
        self.consoles.current(0)
        self.states.configure(values=[self.tr(k) for k in ('all_games','needs_attention','with_hints','missing_games')])
        self.states.current(0)
        for key,label in zip(self.columns,('favorite_star','game','console','build_version','saved_hints','conversion')):
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
        system = self.consoles.current()-1
        state = self.states.current()
        text = self.search.get().casefold().strip()
        games = [g for g in all_games if (system<0 or g.system==PROFILES[system].id)
            and (not self.favorites.get() or g.favorite)
            and (state!=1 or g.status in ATTENTION) and (state!=2 or g.hints)
            and (state!=3 or g.status=='missing') and (not text or text in
                (g.title+' '+get_profile(g.system).name+' '+g.identity).casefold())]
        key = lambda g:((not g.favorite,g.title.casefold()) if self.sort_key=='favorite' else get_profile(g.system).name if self.sort_key=='system' else
                       self.tr('game_'+g.status) if self.sort_key=='status' else getattr(g,self.sort_key))
        games.sort(key=key,reverse=self.reverse)
        def insert(start=0):
            if token != self.render_token or not self.winfo_exists():return
            for index,g in enumerate(games[start:start+60],start):
                row = self.table.insert('','end',values=('★' if g.favorite else '☆',g.title,get_profile(g.system).name,
                    g.version or '—',g.hints,self.tr('game_'+g.status)),tags=('odd',g.status) if index%2 else (g.status,))
                self.rows[row] = g
                if g.key in selected:self.table.selection_add(row)
            if start+60<len(games):self.after(1,lambda:insert(start+60))
        insert()
        self.status.set(self.tr('games_count',count=len(games)) if games else self.tr('compiled_empty'))
        labels = ('favorite_star','game','console','build_version','saved_hints','conversion')
        for key,label in zip(self.columns,labels):
            self.table.heading(key,text=self.tr(label)+('  ▼' if self.reverse else '  ▲') if key==self.sort_key else self.tr(label))

    def star_clicked(self,event):
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
        menu.add_command(label=self.tr('open_folder'),command=lambda:open_local(Path(self.chosen()[0].executable).parent))
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()

    def play(self):
        games = self.chosen()
        if len(games)!=1:return
        game = games[0]
        if game.target != target_id():
            messagebox.showinfo(APP_NAME,self.tr('game_other_platform'),parent=self.owner.app)
            return
        try:
            path = Path(game.executable)
            subprocess.Popen([str(path)],cwd=path.parent)
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
        try:
            while True:
                kind,value = self.events.get_nowait()
                if kind=='progress':self.status.set(self.tr('scanned_games',count=value))
                else:
                    self.running = False
                    self.progress.stop()
                    self.scan_button.configure(state='normal')
                    self.add_button.configure(state='normal')
                    self.render()
                    if kind=='error':self.status.set(self.tr('scan_failed'))
        except queue.Empty:pass
        self.after(100,self.drain)

    def conversion_state(self):
        if self.owner.busy:
            if not self.stop_button.winfo_manager():self.stop_button.pack(side='right',padx=8)
        else:self.stop_button.pack_forget()
        state='disabled' if self.running or self.owner.busy or self.owner.updating else 'normal'
        self.scan_button.configure(state=state)
        self.add_button.configure(state=state)
