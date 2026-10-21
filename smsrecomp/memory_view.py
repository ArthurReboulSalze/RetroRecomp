"""Lazy console-by-console browsing; display summaries never enter a compiler."""
from __future__ import annotations

from pathlib import Path
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk

from .branding import COLORS
from .compiled_games import read_json
from .dialogs import center_dialog
from .library import library_root, atomic_json
from .paths import APP_NAME, data_directory
from .platforms import open_local
from .systems import available_profiles, get_profile
PROFILES = available_profiles()


def summaries(system, cache=None, titles=None):
    """Read changed metadata only. GB traces are stat'ed, never rehashed here."""
    root = library_root(system)
    titles, cache, result, updated = titles or {}, cache or {}, [], {}
    patterns = {'sms': '*/compilation.json', 'gg': '*/compilation.json', 'gb': '*/trace.json',
                'nes': '*/*/cycle-seeds.trace', 'md': '*/native-entries.json',
                'snes': '*/native-ram.json', 'ng': '*/compilation.json', 'x68': '*/compilation.json'}
    seen = set()
    for path in root.glob(patterns[system]):
        identity = path.parent.parent.name if system == 'nes' else path.parent.name.rsplit('-', 1)[-1]
        if not re.fullmatch('[0-9a-f]{64}', identity) or identity in seen:
            continue
        seen.add(identity)
        try:
            stat = path.stat()
            stamp = [stat.st_mtime_ns, stat.st_size]
            extra = path.parent / ('entries.trace' if system == 'gb' else 'observations.log')
            if system in ('gb', 'sms', 'gg') and extra.is_file():
                details = extra.stat()
                stamp += [details.st_mtime_ns, details.st_size]
            old = cache.get(str(path), {})
            if old.get('stamp') == stamp:
                row = dict(old['row'])
            else:
                row = {'identity': identity, 'title': titles.get(identity, identity[:12]),
                       'entries': 0, 'bytes': stat.st_size, 'system': system}
                if system == 'nes':
                    with path.open('rb') as stream:
                        row['entries'] = sum(1 for line in stream if line.strip())
                else:
                    value = read_json(path, 64 * 1024 * 1024)
                    row['title'] = value.get('title') or row['title']
                    if system in ('sms', 'gg'):
                        observations = path.parent / 'observations.log'
                        row['entries'] = (value.get('generations') or [{}])[-1].get('learning', {}).get('observations', 0)
                        # Small line journal, once per changed record; no opcode/ROM validation in a viewer.
                        if observations.is_file():
                            with observations.open('rb') as stream:
                                row['entries'] = sum(1 for line in stream if line.strip())
                    elif system == 'gb':
                        trace = path.parent / 'entries.trace'
                        row['bytes'] = trace.stat().st_size if trace.is_file() else 0
                        row['entries'] = None
                    elif system == 'md':
                        row['entries'] = len(value.get('entries', [])) + len(value.get('ram_variants', []))
                    elif system == 'snes':
                        row['entries'] = len(value.get('ram_variants', []))
                    elif system == 'x68':
                        row['entries'] = value.get('guarded_variants', 0)
                    else:
                        record = value.get('record', {})
                        row['entries'] = sum(len(v) for v in record.values() if isinstance(v, list))
            row['title'] = titles.get(identity, row['title'])
            updated[str(path)] = {'stamp': stamp, 'row': row}
            result.append(row)
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            continue
    return sorted(result, key=lambda r:r['title'].casefold()), updated


class MemoryView:
    def __init__(self, owner):
        self.owner, self.tr = owner, owner.tr
        self.queue, self.generation = queue.Queue(), 0
        self.panel = panel = tk.Toplevel(owner.app)
        panel.title(APP_NAME + ' — ' + self.tr('memory'))
        panel.configure(bg=COLORS['background'])
        panel.transient(owner.app)
        center_dialog(panel, owner.app, 860, 510)
        panel.minsize(680, 350)
        body = ttk.Frame(panel, padding=16)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=self.tr('memory_intro'), wraplength=800).pack(anchor='w', pady=(0,10))
        controls = ttk.Frame(body)
        controls.pack(fill='x', pady=(0,10))
        self.system = tk.StringVar(value=PROFILES[0].name)
        self.selector = ttk.Combobox(controls, textvariable=self.system,
            values=[p.name for p in PROFILES], state='readonly', width=22)
        self.selector.pack(side='left')
        self.selector.bind('<<ComboboxSelected>>', self.load)
        ttk.Button(controls, text=self.tr('rescan'), command=self.load).pack(side='left', padx=8)
        self.status = tk.StringVar()
        ttk.Label(controls, textvariable=self.status, style='Muted.TLabel').pack(side='right')
        row = ttk.Frame(body)
        row.pack(fill='both', expand=True)
        self.table = ttk.Treeview(row, columns=('console','game','identity','entries'), show='headings')
        for key, caption, width in (('console','console',130),('game','game',290),
                                    ('identity','identity',120),('entries','observations',145)):
            self.table.heading(key, text=self.tr(caption))
            self.table.column(key, width=width, minwidth=80, stretch=key=='game')
        bar = ttk.Scrollbar(row, command=self.table.yview)
        self.table.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.table.pack(fill='both', expand=True)
        bottom = ttk.Frame(body)
        bottom.pack(fill='x', pady=(10,0))
        ttk.Button(bottom, text=self.tr('open_memory'), command=self.open_folder).pack(side='left')
        ttk.Button(bottom, text=self.tr('close'), command=panel.destroy).pack(side='right')
        panel.bind('<Escape>', lambda e:panel.destroy())
        panel.after(20, self.load)
        panel.after(50, self.drain)

    def selected(self):
        return next(p.id for p in PROFILES if p.name == self.system.get())

    def open_folder(self):
        path = library_root(self.selected())
        path.mkdir(parents=True, exist_ok=True)
        open_local(path)

    def load(self, event=None):
        self.generation += 1
        token, system = self.generation, self.selected()
        self.status.set(self.tr('memory_loading'))
        self.table.delete(*self.table.get_children())
        titles = {g.identity:g.title for g in self.owner.compiled_inventory.snapshot() if g.system==system}
        titles.update({i.sha256:i.title for i in self.owner.items.values() if i.system==system})
        def worker():
            try:
                file = data_directory() / 'memory-index' / (system + '.json')
                try: cache = read_json(file).get('entries', {})
                except (OSError, ValueError): cache = {}
                rows, cache = summaries(system, cache, titles)
                file.parent.mkdir(parents=True,exist_ok=True)
                atomic_json(file, {'schema':1,'entries':cache})
                self.queue.put((token, rows, ''))
            except Exception as exc:
                self.queue.put((token, [], str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        if not self.panel.winfo_exists(): return
        try:
            while True:
                token, rows, error = self.queue.get_nowait()
                if token != self.generation: continue
                self.status.set(self.tr('memory_failed') if error else self.tr('games_count', count=len(rows)))
                # Chunk insertions keep a large console responsive to close/resize.
                self.insert(rows, token)
        except queue.Empty: pass
        self.panel.after(80, self.drain)

    def insert(self, rows, token):
        if token != self.generation or not self.panel.winfo_exists(): return
        for row in rows[:60]:
            count = self.tr('trace_size', kib=row['bytes']/1024) if row['entries'] is None else row['entries']
            self.table.insert('', 'end', values=(get_profile(row['system']).name, row['title'],
                               row['identity'][:12], count))
        if len(rows)>60:
            self.panel.after(1, lambda:self.insert(rows[60:], token))
