"""Offline-first selected-game card. All file/network work stays off Tk."""
from io import BytesIO
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from PIL import Image, ImageTk

from .branding import COLORS
from .game_details import Cards, public_url
from .systems import get_profile


class GameCardView(ttk.Frame):
    def __init__(self, parent, owner):
        super().__init__(parent,padding=(14,4,4,4))
        self.owner, self.tr = owner, owner.tr
        self.cards, self.game, self.token = Cards(), None, 0
        self.events, self.pending = queue.Queue(), False
        self.info_queue, self.info_current, self.info_count = [], None, 0
        self.info_active = False
        self.title = ttk.Label(self,font=(owner.ui_font,12,'bold'),wraplength=285)
        self.title.pack(fill='x',pady=(0,8))
        self.art = tk.Label(self,bg=COLORS['field'],fg=COLORS['disabled'],height=1)
        self.art.pack(fill='x')
        actions=ttk.Frame(self)
        actions.pack(fill='x',pady=(8,6))
        self.choose=ttk.Button(actions,command=self.choose_cover)
        self.choose.pack(side='left')
        self.find=ttk.Button(actions,command=self.search_cover)
        self.find.pack(side='left',padx=(6,0))
        self.fetch=ttk.Button(self,command=self.search_info)
        self.fetch.pack(fill='x',pady=(0,8))
        self.message=tk.StringVar()
        ttk.Label(self,textvariable=self.message,style='Muted.TLabel',wraplength=290).pack(fill='x')
        body=ttk.Frame(self)
        body.pack(fill='both',expand=True,pady=(6,0))
        self.info=tk.Text(body,wrap='word',height=5,width=26,bg=COLORS['field'],
            fg=COLORS['text'],relief='flat',borderwidth=0,padx=10,pady=8,
            font=(owner.ui_font,9),state='disabled',highlightthickness=0)
        bar=ttk.Scrollbar(body,command=self.info.yview)
        self.info.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.info.pack(fill='both',expand=True)
        self.source=ttk.Button(self,command=self.open_source)
        self.source.pack(anchor='w',pady=(6,0))
        self.source_url=''
        self.bind('<Configure>',self.resize)
        self.payload=None
        self.after(80,self.drain)
        self.localize()
        self.select(None)

    def localize(self):
        self.choose.configure(text=self.tr('card_choose_cover'))
        self.find.configure(text=self.tr('card_find_cover'))
        self.fetch.configure(text=self.tr('card_fetch_info'))
        self.source.configure(text=self.tr('card_source'))

    def controls(self):
        state='normal' if self.game and not self.pending else 'disabled'
        for button in (self.choose,self.find,self.fetch):button.configure(state=state)
        if self.info_active:
            self.fetch.configure(text=self.tr('stop'),command=self.stop_info,state='normal')
        else:self.fetch.configure(text=self.tr('card_fetch_info'),command=self.search_info)
        self.source.configure(state='normal' if self.source_url else 'disabled')

    def select(self, game):
        self.game=game
        self.token+=1
        self.localize()
        self.title.configure(text=game.title if game else self.tr('card_select'))
        self.message.set(self.tr('card_loading') if game else '')
        self.payload=None
        self.draw_cover()
        self.show_metadata({})
        self.controls()
        if game:
            language=self.owner.language
            self.run('loaded',game,lambda:(self.cards.cover(game),self.cards.metadata(game,language)),busy=False)

    def run(self, kind, game, callback, *, busy=True):
        if busy:
            self.pending=True
            self.message.set(self.tr('card_searching'))
            self.controls()
        token=self.token
        def worker():
            try:self.events.put((kind,token,game,callback(),busy))
            except Exception:self.events.put(('error',token,game,None,busy))
        threading.Thread(target=worker,daemon=True).start()

    def resize(self, event):
        self.title.configure(wraplength=max(150,event.width-25))
        self.draw_cover()

    def draw_cover(self):
        self.photo=None
        if self.payload:
            try:
                with Image.open(BytesIO(self.payload)) as source:image=source.convert('RGBA')
                image.thumbnail((max(140,min(310,self.winfo_width()-30)),210),Image.Resampling.LANCZOS)
                self.photo=ImageTk.PhotoImage(image)
            except (OSError,ValueError):pass
        self.art.configure(image=self.photo or '',text='' if self.photo else self.tr('card_no_cover'),
                           height=0 if self.photo else 4)

    def show_metadata(self, data):
        lines=[]
        if self.game:lines.append(get_profile(self.game.system).name+'\n')
        for key in ('release','developer','publisher','genre','players'):
            if data.get(key):
                label='card_first_release' if key=='release' and data.get('release_scope')=='general' else 'card_'+key
                lines.append(self.tr(label)+': '+data[key])
        if data.get('description'):lines+=['',data['description']]
        elif data:lines+=['',self.tr('card_no_summary')]
        if data.get('provider'):
            lines+=['',data['provider']+' · '+data.get('language',''),data.get('license','')]
        if not data:lines.append(self.tr('card_info_empty'))
        self.info.configure(state='normal')
        self.info.delete('1.0','end')
        self.info.insert('1.0','\n'.join(lines))
        self.info.configure(state='disabled')
        self.source_url=public_url(data.get('source',''))
        self.controls()

    def open_source(self):
        if self.source_url:webbrowser.open(self.source_url)

    def choose_cover(self):
        if not self.game or self.pending:return
        name=filedialog.askopenfilename(parent=self.owner.app,title=self.tr('pick_cover'),
            filetypes=[(self.tr('images'),'*.png *.jpg *.jpeg *.webp *.bmp *.ico')])
        if not name:return
        game=self.game
        def save():
            from .artwork import _read_image
            payload=_read_image(Path(name))
            self.cards.set_cover(game,payload,override=True)
            return payload
        self.run('cover',game,save)

    def search_cover(self):
        if self.game and not self.pending:
            game=self.game
            self.run('cover',game,lambda:self.cards.online_cover(game))

    def search_info(self):
        if not self.game or self.pending:return
        self.search_games([self.game],refresh=True)

    def search_games(self, games, *, refresh=False):
        if self.pending or not games:return
        self.info_queue=list(games)
        self.info_language=self.owner.language
        self.info_refresh=refresh
        self.info_count=0
        self.info_active=True
        self.next_info()

    def stop_info(self):
        # Let the single in-flight HTTPS request finish, then stop the queue.
        self.info_queue=[]
        self.fetch.configure(state='disabled')

    def next_info(self):
        from .game_metadata import search
        while self.info_queue:
            game=self.info_queue.pop(0)
            language=self.info_language
            if not self.info_refresh and self.cards.metadata(game,language):continue
            self.info_current=game
            self.run('candidates',game,lambda game=game:(language,search(game.title,game.system,language)))
            return
        self.info_active=False
        self.info_current=None
        self.pending=False
        self.owner.compiled_view.status.set(self.tr('card_batch_done',count=self.info_count))
        self.controls()

    def choose_candidate(self, rows):
        if len(rows)==1:return rows[0]
        panel=tk.Toplevel(self.owner.app)
        panel.title(self.tr('card_choose_match'))
        panel.transient(self.owner.app)
        panel.configure(bg=COLORS['background'])
        from .dialogs import center_dialog
        center_dialog(panel,self.owner.app,650,330)
        ttk.Label(panel,text=self.tr('card_choose_match'),padding=12).pack(anchor='w')
        table=ttk.Treeview(panel,columns=('title','date','provider'),show='headings',selectmode='browse',height=5)
        for key,label,width in (('title','game',330),('date','card_release',100),('provider','card_source',150)):
            table.heading(key,text=self.tr(label))
            table.column(key,width=width,minwidth=70)
        for i,row in enumerate(rows):table.insert('','end',iid=str(i),values=(row['title'],row.get('release',''),row['provider']))
        table.pack(fill='both',expand=True,padx=12)
        chosen=[]
        def accept():
            if table.selection():chosen.append(rows[int(table.selection()[0])]);panel.destroy()
        bottom=ttk.Frame(panel,padding=12)
        bottom.pack(fill='x')
        ttk.Button(bottom,text=self.tr('close'),command=panel.destroy).pack(side='right')
        ttk.Button(bottom,text=self.tr('card_use_match'),command=accept).pack(side='right',padx=8)
        table.bind('<Double-1>',lambda e:accept())
        panel.bind('<Escape>',lambda e:panel.destroy())
        panel.grab_set()
        self.wait_window(panel)
        return chosen[0] if chosen else None

    def drain(self):
        try:
            while True:
                kind,token,game,value,busy=self.events.get_nowait()
                if busy:self.pending=False
                current=self.game and (game.system,game.identity)==(self.game.system,self.game.identity)
                if kind=='loaded':
                    if token==self.token:
                        self.payload,metadata=value
                        self.draw_cover();self.show_metadata(metadata);self.message.set('')
                elif kind=='candidates':
                    language,rows=value
                    if not rows:
                        if current:self.message.set(self.tr('card_not_found'))
                        self.next_info()
                    else:
                        row=self.choose_candidate(rows)
                        if row:
                            from .game_metadata import complete
                            self.run('metadata',game,lambda game=game,language=language,row=row:self.cards.save_metadata(game,language,complete(row)))
                        else:
                            self.message.set('')
                            self.next_info()
                elif kind=='metadata':
                    self.info_count+=1
                    if current:
                        self.show_metadata(value)
                        self.message.set(self.tr('card_saved'))
                    self.next_info()
                elif kind=='cover' and current:
                    self.payload=value;self.draw_cover()
                    self.message.set(self.tr('card_cover_saved'))
                elif kind=='error':
                    if current:self.message.set(self.tr('card_failed'))
                    if busy and self.info_active and self.info_current is game:self.next_info()
                self.controls()
        except queue.Empty:pass
        self.after(100,self.drain)
