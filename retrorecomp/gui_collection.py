"""The collection of converted games: its view, new paths, going deeper and reconverting."""
from __future__ import annotations

from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .batch import identify
from .paths import APP_NAME, save_preferences
from .systems import get_profile
from .gui_common import INTERFACE_PREFERENCES


class CollectionMixin:
    """The collection of converted games: its view, new paths, going deeper and reconverting."""

    def offer_compiled(self, rows):
        """Ask once whether games already compiled in the output folder stay in
        the list for a reconversion; otherwise leave them out, so the user
        need not sort a mixed folder by hand. Nothing is asked before the
        window shows (ROMs given on the command line)."""
        rows = [row for row in rows if self.table.exists(row)]
        if not rows or not self.app.winfo_viewable():
            return
        examples = ', '.join(self.items[row].title for row in rows[:3]) + ('…' if len(rows) > 3 else '')
        if self.confirm_compiled(len(rows), examples):
            return
        for row in rows:
            self.table.delete(row)
            self.items.pop(row, None)
            self.results.pop(row, None)
            self.row_status.pop(row, None)
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))
        self.messages.put(('log', self.tr('already_compiled_left_out', count=len(rows))))
        self.selection_changed()

    def confirm_compiled(self, count, examples):
        return messagebox.askyesno(APP_NAME, self.tr('already_compiled', count=count, examples=examples),
                                   default='no', parent=self.app)

    def new_paths_button(self, parent):
        button = ttk.Button(parent, command=self.recompile_new_paths, style='Toolbar.TButton')
        self.decorate_button(button, 'new_paths')
        self.hint(button, 'tip_recompile_new_paths')
        self.new_paths_buttons.append(button)
        self.update_new_paths()
        return button

    def games_with_new_paths(self, shared_only=False):
        """Games whose saved gameplay hints are newer than their conversion."""
        from .platforms import target_id
        from .knowledge_build import SYSTEMS as SHARED
        return [game for game in self.compiled_inventory.snapshot()
                if game.status == 'new_hints' and game.target in ('', target_id())
                and (not shared_only or game.system in SHARED)]

    def update_new_paths(self):
        count = len(self.games_with_new_paths())
        for button in getattr(self, 'new_paths_buttons', []):
            if button.winfo_exists():
                button.configure(text=self.tr('recompile_new_paths', count=count),
                                 state='normal' if count and not self.busy and not self.updating else 'disabled')

    def quiet_refresh_collection(self, games=None, every=0):
        """Re-read only collection rows whose files changed, in the background;
        Scan games stays available for new folders and moved games."""
        if (self.collection_refreshing or self.busy or self.updating
                or time.monotonic() - self.collection_refreshed_at < every):
            return
        self.collection_refreshing, self.collection_refreshed_at = True, time.monotonic()
        preferences = self.preferences()
        def worker():
            from .compiled_games import refresh_changed
            try:changed = refresh_changed(self.compiled_inventory, preferences, games)
            except Exception:changed = 0
            self.messages.put(('collection_quiet', changed))
        threading.Thread(target=worker, daemon=True).start()

    def recompile_new_paths(self, games=None):
        """Reconvert only the games with new paths (upgrading when nothing else
        changed); games whose ROM cannot be found are left for later."""
        if self.busy or self.updating:return
        games = self.games_with_new_paths() if games is None else games
        if not games:return
        if not self.collection_visible:self.toggle_compiled_games()
        self.reconvert_games(games, skip_missing=True)

    def show_library(self):
        if self.library_view is not None and self.library_view.panel.winfo_exists():
            self.library_view.panel.lift()
            return
        from .memory_view import MemoryView
        self.library_view = MemoryView(self)
        self.library_panels.append(self.library_view.panel)

    def toggle_compiled_games(self):
        if self.options_panel is not None and self.options_panel.winfo_exists():
            self.close_options()
            if self.options_panel is not None:
                return
        if self.compiled_view is None:
            from .compiled_games_view import CompiledGamesView
            self.compiled_view = CompiledGamesView(self, self.body)
        self.collection_visible = not self.collection_visible
        if self.collection_visible:
            for widget in self.compiler_widgets:widget.grid_remove()
            self.queue_actions.pack_forget()
            self.count_label.pack_forget()
            self.collection_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
            self.body.rowconfigure(1, weight=1, minsize=100)
            self.body.rowconfigure(7, weight=0, minsize=0)
            self.compiled_view.grid(row=1,column=0,rowspan=7,sticky='nsew')
            self.compiled_view.render()
            # Games played or converted elsewhere: re-read only what changed.
            self.compiled_view.after_idle(self.compiled_view.quiet_refresh)
        else:
            self.compiled_view.grid_remove()
            self.body.rowconfigure(1, weight=4, minsize=100)
            self.body.rowconfigure(7, weight=2, minsize=52)
            for widget in self.compiler_widgets:widget.grid()
            self.collection_actions.pack_forget()
            self.queue_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
            self.count_label.pack(side='right', before=self.credits_button)
        self.update_compiled_button()
        self.queue_background(self.body)

    def update_compiled_button(self):
        """One width for both captions, so the switch never changes size."""
        captions = (self.tr('compiled_games'), self.tr('conversion_queue'))
        # Width counts average characters ('0'); measure the real text so
        # wide scripts such as Cyrillic are not cut.
        from tkinter import font as tkfont
        measure = tkfont.Font(root=self.app, font=(self.ui_font, 9))
        zero = measure.measure('0') or 7
        widest = max(measure.measure(caption) for caption in captions)
        self.compiled_button.configure(text=captions[1] if self.collection_visible else captions[0],
                                       width=-(-widest // zero) + 1)

    def go_deeper(self, games, level):
        """Compiled Games' "Go further": convert again with a discovery at the
        Extended or Thorough level (a full discovery, not a quick check). The
        level travels with this reconversion only (to begin_reconvert): one that
        stops early never leaves it to the next ordinary reconversion."""
        self.reconvert_games(games, level=level)

    def reconvert_games(self, games, level=None, skip_missing=False):
        """Find the games' ROMs off Tk, then reconvert them (begin_reconvert).
        `level`: "Go further"'s scan level; `skip_missing`: games whose ROM is
        not found wait for later instead of asking for it (new paths)."""
        if self.busy or self.updating or not games:return
        if not self.ensure_build_tools(lambda: self.reconvert_games(games, level, skip_missing)):return
        from .platforms import target_id
        for game in games:
            if game.target and game.target != target_id():
                messagebox.showinfo(APP_NAME,self.tr('game_other_platform'))
                return
        options=self.preferences()
        from .compiled_games import Game
        known=[*self.compiled_inventory.snapshot(),*(Game('',i.system,i.sha256,i.title,source=str(i.path))
               for i in self.items.values() if i.system and i.sha256)]
        self.busy=True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_view.progress.start(15)
        self.compiled_view.status.set(self.tr('rom_searching'))
        def worker():
            from .rom_sources import RomSources
            try:pairs=RomSources().resolve(games,options,known=known,cancel=self.cancel)
            except Exception:pairs=[(game,None) for game in games]
            self.messages.put(('sources_ready',pairs,level,skip_missing))
        threading.Thread(target=worker,daemon=True).start()

    def finish_source_lookup(self, pairs, level=None, skip_missing=False):
        self.busy=False
        self.compiled_view.progress.stop()
        self.set_controls(True)
        if self.close_when_idle and (not self.closing_after_recompile or self.cancel.is_set()):
            self.close()
            return
        if self.cancel.is_set():return
        # While closing, or for new paths, a missing ROM waits for later.
        if any(source is None for _,source in pairs) and (self.closing_after_recompile or skip_missing):
            pairs=[(game,source) for game,source in pairs if source is not None]
        self.locate_missing({'pairs':list(pairs),'level':level,'asked':{}})

    def locate_missing(self, state):
        """ROMs still missing: ask for the folder holding each console's ROMs, search
        it for all of that console's missing games at once, and ask again (another
        folder, or skip them) at most once per console. Cancelling any prompt stops
        the reconversion, as the former ROM picker did; skipped games are logged."""
        pairs,asked=state['pairs'],state['asked']
        missing={}
        for game,source in pairs:
            if source is None:missing.setdefault(game.system,[]).append(game)
        for system,games in missing.items():
            times=asked.get(system,0)
            if times>=2:continue
            name=get_profile(system).name
            if times==1:
                titles='\n'.join(game.title for game in games[:6])+('\n…' if len(games)>6 else '')
                answer=messagebox.askyesnocancel(APP_NAME,
                    self.tr('rom_folder_missing',console=name,count=len(games),titles=titles),parent=self.app)
                if answer is None:return
                if not answer:
                    asked[system]=2
                    return self.locate_missing(state)
            options={'initialdir':self.saved_rom_folder(system)} if self.saved_rom_folder(system) else {}
            folder=filedialog.askdirectory(parent=self.app,mustexist=True,
                title=self.tr('locate_rom_folder',console=name,count=len(games)),**options)
            if not folder:return
            asked[system]=times+1
            return self.search_rom_folder(state,system,games,Path(folder))
        chosen=[(game,source) for game,source in pairs if source is not None]
        for game,source in pairs:
            if source is None:self.messages.put(('log',self.tr('rom_skipped',title=game.title)))
        if chosen:self.begin_reconvert(chosen,state['level'])
        elif self.close_when_idle:self.close()

    def saved_rom_folder(self, system):
        """The ROM folder saved in Options for a console, when it exists."""
        variable=getattr(self,'rom_paths',{}).get(system)
        text=variable.get().strip() if variable is not None else ''
        return text if text and Path(text).expanduser().is_dir() else ''

    def search_rom_folder(self, state, system, games, folder):
        """Search a folder, off Tk, for every missing ROM of one console (the
        exact identity, subfolders and ZIPs included; nothing is written)."""
        self.busy=True
        self.set_controls(False)
        self.compiled_view.progress.start(15)
        self.compiled_view.status.set(self.tr('rom_searching'))
        def worker():
            from .rom_sources import RomSources
            try:found=RomSources().resolve(games,{'rom_paths':{system:str(folder)}},cancel=self.cancel)
            except Exception:found=[(game,None) for game in games]
            self.messages.put(('rom_folder_searched',state,system,folder,found))
        threading.Thread(target=worker,daemon=True).start()

    def finish_folder_search(self, state, system, folder, found):
        self.busy=False
        self.compiled_view.progress.stop()
        self.set_controls(True)
        if self.close_when_idle and (not self.closing_after_recompile or self.cancel.is_set()):
            self.close()
            return
        if self.cancel.is_set():return
        sources={id(game):source for game,source in found if source is not None}
        state['pairs']=[(game,sources.get(id(game),source)) for game,source in state['pairs']]
        if sources:
            # Kept in Options for the next time, and for the other searches of that console.
            variable=getattr(self,'rom_paths',{}).get(system)
            if variable is not None:
                variable.set(str(folder))
                try:save_preferences(self.preferences())
                except (OSError,ValueError,tk.TclError):pass
        text=self.tr('rom_folder_found',console=get_profile(system).name,found=len(sources),
                     total=len(found),folder=str(folder))
        self.messages.put(('log',text))
        self.compiled_view.status.set(text)
        self.locate_missing(state)

    def begin_reconvert(self, chosen, level=None):
        options = self.preferences()
        use_shared = options.pop('use_shared_base', False)
        # Games converted at once per console (run_limited below), as in the queue.
        per_console=options.get('console_jobs') or {}
        for key in (*INTERFACE_PREFERENCES,'output','jobs','overwrite'):
            options.pop(key,None)
        # Always rebuild, but only the player shell when nothing else changed.
        options['force'] = True
        options['rediscover'] = False
        # "Go further": a discovery at the chosen level, whatever the console's setting.
        if level:
            options['scan_level'] = level
            options['rediscover'] = True
        jobs = self.jobs.get()
        self.busy = self.converting = True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_view.progress.start(15)
        self.compiled_view.clear_log()
        self.compiled_view.status.set(self.tr('reconverting_games'))
        def worker():
            from .queue_state import console_jobs, run_limited
            from .batch import _convert_in_budget, _embedded_export_identity, reported_owner
            from .freshness import digest
            from .compiled_games import game_from_report, refresh, read_json
            counts = {'success':0,'failed':0}
            errors, results = [], []
            cartridge_locks={(game.system,game.identity):threading.Lock() for game,_ in chosen}
            # Like a batch from the queue: the shared base's paths first.
            keys = self.shared_rom_keys([(game.system, game.identity, source) for game, source in chosen], options)
            shared = self.prepare_shared_paths(keys, use_shared)
            self.start_shared_source(use_shared, keys, {game.system for game, _ in chosen})
            def convert(pair):
                game,source = pair
                if self.cancel.is_set():return None
                item = identify(source,game.system)
                if item.error or item.sha256 != game.identity:
                    raise ValueError(self.tr('source_mismatch',title=game.title))
                game.source=str(source.resolve())
                self.compiled_inventory.remember(game)
                self.compiled_inventory.save()
                from .game_details import Cards
                item.cover=Cards().override(game)
                target = Path(game.executable)
                report = read_json(game.report) if game.report else {}
                # Old exports carry neither a receipt nor a marker: accept the
                # reports beside them, as a conversion from the queue does.
                if target.is_file() and not (report.get('export_receipt',{}).get('sha256') == digest(target)
                    or _embedded_export_identity(target)==game.identity
                    or reported_owner(target,game.identity)):
                    raise ValueError(self.tr('game_unverified'))
                item.title = game.title
                standard = report.get('video_model',{}).get('standard')
                if standard in get_profile(item.system).video_modes:item.standard_override = standard
                folder = target.parent/'datas/reports'/item.key
                folder.mkdir(parents=True,exist_ok=True)
                games_at_once=console_jobs(jobs,per_console,game.system)
                result = _convert_in_budget(games_at_once,0,item,len(chosen),get_profile(item.system),target.parent,
                    folder,target,[],lambda text:self.messages.put(('log',text)),
                    {**options,'gb_parallel_games':games_at_once,'ng_parallel_games':games_at_once,'shared_paths':shared})
                results.append({**result,'system':item.system,'sha256':item.sha256})
                if result['status'] in ('success','current'):
                    game = game_from_report(Path(result['report']),target.parent,source=str(source))
                    self.compiled_inventory.remember(refresh(game,{}))
                    self.note_conversion(result, game)
                return result
            def guarded(pair):
                game,_=pair
                # Copies in different folders still share compiler work files.
                # Serialize an exact cartridge while unrelated games use the pool.
                with cartridge_locks[(game.system,game.identity)]:return convert(pair)
            def finished(pair,future):
                try:
                    result = future.result()
                    if result is None:return
                    counts['success' if result['status'] in ('success','current') else 'failed'] += 1
                    if result['status']=='error':errors.append(result.get('message',''))
                except Exception as exc:
                    counts['failed'] += 1
                    errors.append(str(exc))
                    self.messages.put(('log',str(exc)))
            try:
                run_limited(chosen,lambda pair:pair[0].system,jobs,per_console,guarded,finished)
                self.compiled_inventory.save()
            except Exception as exc:
                counts['failed'] += 1
                errors.append(str(exc))
                self.messages.put(('log',str(exc)))
            finally:
                self.stop_shared_source()
            self.forget_rejected_shared(shared, results)
            if errors:counts['detail']=' · '.join(errors[:2])
            self.messages.put(('collection_done',counts))
        threading.Thread(target=worker,daemon=True).start()
