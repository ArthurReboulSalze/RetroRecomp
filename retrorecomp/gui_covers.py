"""The box-art window: one window where the player drops an image (or chooses a file) to give a game its cover.

It opens three ways, and one window holds them all (one row per game):

* « Box art not found » (`missing`): with the option on (`ask_missing_cover`, a preference of the window only, on by
  default; Options turns it off, and so does the window's own « Don't ask again » button), a game of a queue batch that
  ends without box art joins the window: its report says the cover lookup came back empty, or only a title screen or an
  in-game picture stood in for it. The batch never waits for the player: the other conversions go on, the window lists
  each game as it ends, and closing the window skips the games still waiting (and the later ones of the same batch).
* « Choose box art… » of the queue (`queue`): the selected rows, one or several, before they are converted. The image
  becomes the row's chosen box art (the file itself, as before), used by the row's next conversion; nothing is rebuilt.
* « Choose cover… » of a Compiled Games card (`card`): a game already exported.

An image is checked as the converter's box-art reader checks it (the same file types, the same reader). For `missing`
and `card` it is kept as the game's own cover: the game card's override (game_details.Cards), which every later
conversion and Reconvert of that game use. It reaches the exported game through the reconversion of Compiled Games
(begin_reconvert): the game part of the request is unchanged, so only the player shell is rebuilt, with the new icon.
That runs once the window has nothing else to do: at the end of a batch, or at once. A game whose ROM cannot be found
keeps the image for its next Reconvert. Batch and command-line conversions never open this window (this module is the
window's only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from .branding import COLORS
from .dialogs import center_dialog
from .ui_fonts import scaled
from .paths import ROOT, save_preferences
from .systems import get_profile

# The file types of the converter's box-art reader (artwork.FORMATS), the ones the file pickers offered before.
COVER_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.ico')
# The statuses a converted game can end with and still have an export to give a cover to.
EXPORTED = ('success', 'current', 'existing')
THUMBNAIL = 88
APPLY_RETRY_MS = 1500      # an image waits while the window is busy (a send, a search): looked at again after this


class CoverRefused(ValueError):
    """An image the window does not accept; `key` is the message shown on the game's row."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def box_art_missing(report: dict) -> bool:
    """True when a conversion report says the game was given no box art: the lookup came back empty, or a title screen
    or an in-game picture stood in. A cover the player chose, and icons turned off in Options, are never « missing »."""
    art = report.get('artwork') if isinstance(report, dict) else None
    if not isinstance(art, dict):
        return False
    if art.get('source') in ('disabled', 'explicit'):
        return False
    if not art.get('embedded'):
        return art.get('source') == 'missing'
    return art.get('media_style') in ('title', 'snapshot')


def read_cover(path: Path) -> bytes:
    """The image's bytes, read and decoded as the converter's box-art reader reads them; CoverRefused otherwise."""
    from .artwork import ArtworkError, _read_image
    path = Path(path)
    if path.suffix.lower() not in COVER_EXTENSIONS:
        raise CoverRefused('cover_ask_refused_type')
    try:
        return _read_image(path)
    except (ArtworkError, OSError, ValueError):
        raise CoverRefused('cover_ask_refused_image') from None


@dataclass
class CoverRequest:
    """One game of the window. `game` has a title and a system (a Compiled Games entry; for `queue`, the queue's
    BatchItem); `source` is its ROM (None when it cannot be found); `row` its queue row, if any."""
    game: object
    source: Path | None
    row: str | None = None
    kind: str = 'missing'      # missing, queue, card
    state: str = 'waiting'     # waiting, chosen (queue), ready, applying, applied, skipped, failed
    message: str = ''          # a refusal or a failure, shown on the row
    payload: bytes | None = field(default=None, repr=False)     # the image given
    current: bytes | None = field(default=None, repr=False)     # the cover the game has now, when known

    @property
    def key(self):
        if self.kind == 'queue':
            return ('row', self.row)
        return (self.game.system, self.game.identity)


class CoverRequests:
    """The games of the window, in the order they came. No Tk here."""

    def __init__(self):
        self.entries: dict[tuple[str, str], CoverRequest] = {}
        self.declined = False      # the player closed the « not found » games: the rest of this batch is not asked for

    def add(self, game, source, row=None, kind='missing', current=None):
        """List a game; the request already listed for it when it is still open; None for a game without box art
        after the player closed the window during this batch."""
        request = CoverRequest(game, Path(source) if source else None, row, kind, current=current)
        if kind == 'missing' and self.declined:
            return None
        listed = self.entries.get(request.key)
        if listed is not None and listed.state not in ('chosen', 'applied', 'skipped', 'failed'):
            listed.row = row or listed.row
            if kind != 'missing':
                listed.kind, listed.current = kind, current if current is not None else listed.current
                listed.source = listed.source or request.source
            return listed
        self.entries[request.key] = request
        return request

    def give(self, key, payload):
        request = self.entries[key]
        if request.state == 'applying':
            return None            # its cover is being applied: a new image waits for the next round
        request.payload, request.message = payload, ''
        request.state = 'chosen' if request.kind == 'queue' else 'ready'
        return request

    def refuse(self, key, message):
        request = self.entries[key]
        request.message = message
        return request

    def skip(self, key):
        request = self.entries[key]
        if request.state in ('waiting', 'failed'):
            request.state, request.message = 'skipped', ''
        return request

    def close(self):
        """The window is closed. The games without box art still waiting are skipped, and so are the later ones of this
        batch; a game opened to choose its cover leaves the window unchanged. The images already given are applied."""
        if any(request.kind == 'missing' for request in self.entries.values()):
            self.declined = True
        for key, request in list(self.entries.items()):
            if request.state == 'waiting':
                if request.kind == 'missing':
                    request.state = 'skipped'
                else:
                    del self.entries[key]

    def take_ready(self):
        """The games whose image is waiting to be applied and whose ROM is known, now marked as being applied."""
        ready = [request for request in self.entries.values() if request.state == 'ready' and request.source]
        for request in ready:
            request.state = 'applying'
        return ready

    def finished(self, key, succeeded, message=''):
        request = self.entries.get(key)
        if request is None or request.state != 'applying':
            return None
        request.state, request.message = ('applied', '') if succeeded else ('failed', message)
        return request

    def new_batch(self):
        """A new batch asks again; the games already settled leave the window, those still open stay."""
        self.declined = False
        self.entries = {key: request for key, request in self.entries.items()
                        if request.state in ('waiting', 'ready', 'applying')}

    def pending(self):
        return any(request.state in ('ready', 'applying') for request in self.entries.values())

    def open(self):
        return [request for request in self.entries.values() if request.state == 'waiting']


def target_request(requests, keys):
    """The game a drop is for: the row under the pointer (`keys`, from the innermost widget outwards), else the only
    game still waiting. None when it cannot be told."""
    for key in keys:
        if key in requests.entries:
            return requests.entries[key]
    waiting = requests.open()
    return waiting[0] if len(waiting) == 1 else None


def _saved_card_cover(game) -> bytes | None:
    """The image the game card keeps (game_details.Cards), read without any lookup; None when it has none."""
    try:
        from .game_details import Cards
        path = Cards().folder(game) / 'cover.png'
        return path.read_bytes() if path.is_file() else None
    except (OSError, ValueError, KeyError):
        return None


def _image_bytes(path) -> bytes | None:
    try:
        return read_cover(Path(path))
    except (CoverRefused, OSError, TypeError):
        return None


class MissingCoversMixin:
    """The box-art window, its drops and the application of the images to the exported games."""

    def cover_requests(self):
        if getattr(self, '_cover_requests', None) is None:
            self._cover_requests = CoverRequests()
        return self._cover_requests

    # -- the three ways in --------------------------------------------------------------------------------------------
    def check_missing_cover(self, row, result):
        """Called by the batch worker for each result: a game with no box art is sent to the window. Reads the report
        here, off Tk; never raises (the batch must not stop for the window)."""
        if result.get('status') not in EXPORTED or not result.get('report') or not result.get('executable'):
            return
        try:
            from .compiled_games import game_from_report, read_json
            report = Path(result['report'])
            if not box_art_missing(read_json(report)):
                return
            game = game_from_report(report, Path(result['executable']).parent, source=result.get('rom', ''))
        except (OSError, ValueError, TypeError, KeyError):
            return
        self.messages.put(('cover_missing', row, game, Path(result.get('rom', ''))))

    def cover_missing(self, row, game, source):
        request = self.cover_requests().add(game, source, row)
        if request is None or request.kind != 'missing':
            return
        self.messages.put(('log', self.tr('cover_ask_listed', title=game.title)))
        self.show_cover_rows([request])

    def choose_queue_covers(self, rows):
        """« Choose box art… » of the queue: the selected rows in the window, each with the image it has now."""
        requests = []
        for row in rows:
            item = self.items.get(row)
            if item is None:
                continue
            current = _image_bytes(item.cover) if item.cover else None
            requests.append(self.cover_requests().add(item, item.path, row, kind='queue', current=current))
        self.show_cover_rows(requests)

    def choose_card_cover(self, game, current=None):
        """« Choose cover… » of a Compiled Games card: the game in the window, applied to its export once given."""
        self.choose_compiled_covers([game], {(game.system, game.identity): current})

    def choose_compiled_covers(self, games, current=None):
        """The Compiled Games games in the window (the card's button, the list's right-click), each applied to its
        export once given. `current`: the covers already at hand; the others are the game card's saved image, if any."""
        current = current or {}
        requests = []
        for game in games:
            source = Path(game.source) if getattr(game, 'source', '') else None
            if source is None or not source.exists():
                source = next((item.path for item in self.items.values()
                               if item.system == game.system and item.sha256 == game.identity and item.path.exists()),
                              None)
            picture = current.get((game.system, game.identity))
            if picture is None:
                picture = _saved_card_cover(game)
            requests.append(self.cover_requests().add(game, source, kind='card', current=picture))
        if requests:
            self.show_cover_rows(requests)

    # -- the window (Tk thread) ---------------------------------------------------------------------------------------
    def show_cover_rows(self, requests):
        window = getattr(self, 'cover_window', None)
        if window is None or not window.winfo_exists():
            window = self.open_cover_window()
        for request in requests:
            if request.key in self.cover_rows:
                self.cover_refresh(request)
            else:
                self.cover_row(request)
        self.cover_window_header()
        self.cover_window_fit()
        try:
            window.lift()
        except tk.TclError:
            pass

    def open_cover_window(self):
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.configure(bg=background)
        window.transient(self.app)
        self.cover_window, self.cover_rows = window, {}
        body = tk.Frame(window, bg=background, padx=22, pady=18, highlightthickness=1,
                        highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        self.cover_heading = tk.Label(body, bg=background, fg=COLORS['gold'], font=(self.ui_font, 9, 'bold'))
        self.cover_heading.pack(anchor='w')
        self.cover_note = tk.Label(body, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                                   wraplength=600, justify='left')
        self.cover_note.pack(anchor='w', pady=(10, 10))
        footer = tk.Frame(body, bg=background)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        self.cover_status = tk.StringVar(value='')
        tk.Label(footer, textvariable=self.cover_status, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=600, justify='left').pack(anchor='w', pady=(0, 8))
        ttk.Button(footer, text=self.tr('close'), command=self.close_cover_window).pack(side='right')
        self.cover_never = ttk.Button(footer, text=self.tr('cover_ask_never'), command=self.never_ask_cover)
        self.hint(self.cover_never, 'tip_cover_ask_never')
        holder = tk.Frame(body, bg=background)
        holder.pack(fill='both', expand=True)
        canvas = tk.Canvas(holder, bg=background, highlightthickness=0, borderwidth=0, width=600, height=120)
        bar = ttk.Scrollbar(holder, orient='vertical', command=canvas.yview, style='Slim.Vertical.TScrollbar')
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=background)
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        def wheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(-1 if (getattr(event, 'delta', 0) > 0 or getattr(event, 'num', 0) == 4) else 1,
                                    'units')
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            window.bind(sequence, wheel)
        self.cover_canvas, self.cover_list = canvas, inner
        window.protocol('WM_DELETE_WINDOW', self.close_cover_window)
        window.bind('<Escape>', lambda event: self.close_cover_window())
        self.cover_drop = None
        try:
            from .dropfiles import enable_file_drop
            self.cover_drop = enable_file_drop(window, self.cover_dropped,
                                               lambda error: self.messages.put(('cover_drop_error', str(error))))
        except OSError:
            self.cover_status.set(self.tr('cover_ask_no_drop'))
        window.update_idletasks()
        center_dialog(window, self.app, 680, 300)
        window.deiconify()
        return window

    def cover_window_header(self):
        """« Box art not found » while the window holds such a game (with « Don't ask again »), « Choose box art »
        otherwise."""
        entries = self.cover_requests().entries
        missing = any(entries[key].kind == 'missing' for key in self.cover_rows if key in entries)
        title = self.tr('cover_ask_title' if missing else 'cover_pick_title')
        self.cover_window.title(title)
        self.cover_heading.configure(text=title.upper())
        self.cover_note.configure(text=self.tr('cover_ask_note' if missing else 'cover_pick_note'))
        if missing and not self.cover_never.winfo_ismapped():
            self.cover_never.pack(side='right', padx=(0, 8))
        elif not missing:
            self.cover_never.pack_forget()

    def cover_window_fit(self):
        """Grow the list with its games, up to about four rows, then scroll."""
        window = getattr(self, 'cover_window', None)
        if window is None or not window.winfo_exists():
            return
        window.update_idletasks()
        self.cover_canvas.configure(height=min(len(self.cover_rows), 4) * (THUMBNAIL + 18))
        window.update_idletasks()
        center_dialog(window, self.app, max(scaled(window, 680), window.winfo_reqwidth()), window.winfo_reqheight(), measured=True)

    def cover_row(self, request):
        """The row of one game: its drop zone (its picture once known), its title and status, Choose… (and Skip for a
        game without box art)."""
        background = COLORS['panel']
        row = tk.Frame(self.cover_list, bg=background, pady=4)
        row.pack(fill='x', anchor='w', pady=(0, 6))
        zone = tk.Canvas(row, width=THUMBNAIL, height=THUMBNAIL, bg=COLORS['field'], highlightthickness=0,
                         borderwidth=0, cursor='hand2')
        zone.pack(side='left')
        text = tk.Frame(row, bg=background)
        text.pack(side='left', fill='x', expand=True, padx=(14, 8))
        tk.Label(text, text=request.game.title, bg=background, fg=COLORS['text'], font=(self.ui_font, 10, 'bold'),
                 anchor='w', justify='left', wraplength=330).pack(anchor='w')
        try:
            console = get_profile(request.game.system).name
        except (KeyError, ValueError, TypeError):
            console = request.game.system or ''
        tk.Label(text, text=console, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 anchor='w').pack(anchor='w')
        status = tk.Label(text, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9), anchor='w',
                          justify='left', wraplength=330)
        status.pack(anchor='w', pady=(4, 0))
        buttons = tk.Frame(row, bg=background)
        buttons.pack(side='right')
        choose = ttk.Button(buttons, text=self.tr('cover_ask_choose'),
                            command=lambda key=request.key: self.choose_missing_cover(key))
        choose.pack(fill='x')
        skip = ttk.Button(buttons, text=self.tr('cover_ask_skip'),
                          command=lambda key=request.key: self.skip_missing_cover(key))
        zone.bind('<Button-1>', lambda event, key=request.key: self.choose_missing_cover(key))
        widgets = {'row': row, 'zone': zone, 'status': status, 'choose': choose, 'skip': skip, 'photo': None,
                   'shown': None}
        self.cover_rows[request.key] = widgets
        for widget in (row, zone, text, buttons, status, *text.winfo_children()):
            widget._cover_key = request.key
        if getattr(self, 'cover_drop', None) is not None:
            try:
                self.cover_drop.add(row)
            except Exception:
                pass       # this row then takes a chosen file only; the others still take drops
        self.cover_refresh(request)
        return widgets

    def cover_refresh(self, request):
        widgets = getattr(self, 'cover_rows', {}).get(request.key)
        if widgets is None or not widgets['row'].winfo_exists():
            return
        zone = widgets['zone']
        zone.delete('all')
        picture = request.payload if request.payload is not None else request.current
        if picture is not widgets['shown']:
            widgets['shown'], widgets['photo'] = picture, None
            if picture is not None:
                try:
                    from PIL import Image, ImageTk
                    with Image.open(BytesIO(picture)) as image:
                        thumbnail = image.convert('RGBA')
                    thumbnail.thumbnail((THUMBNAIL - 6, THUMBNAIL - 6))
                    widgets['photo'] = ImageTk.PhotoImage(thumbnail, master=zone)
                except Exception:
                    widgets['photo'] = None
        if widgets['photo'] is not None:
            zone.create_image(THUMBNAIL // 2, THUMBNAIL // 2, image=widgets['photo'])
        else:
            zone.create_rectangle(3, 3, THUMBNAIL - 3, THUMBNAIL - 3, outline=COLORS['gold'], dash=(4, 3))
            zone.create_text(THUMBNAIL // 2, THUMBNAIL // 2, text=self.tr('cover_ask_drop_here'), fill=COLORS['muted'],
                             font=(self.ui_font, 8), width=THUMBNAIL - 12, justify='center')
        if request.state == 'waiting':
            key = ('cover_ask_waiting' if request.kind == 'missing' else
                   'cover_pick_current' if request.current is not None else 'cover_pick_waiting')
        elif request.state == 'ready' and not request.source:
            key = 'cover_pick_no_rom'
        else:
            key = {'chosen': 'cover_pick_chosen', 'ready': 'cover_ask_ready_later' if self.busy else 'cover_ask_ready',
                   'applying': 'cover_ask_applying', 'applied': 'cover_ask_applied', 'skipped': 'cover_ask_skipped',
                   'failed': 'cover_ask_failed'}[request.state]
        text = self.tr(key, error=request.message) if request.state == 'failed' else self.tr(key)
        colour = COLORS['muted']
        if request.message and request.state != 'failed':
            text, colour = self.tr(request.message), COLORS['error']
        elif request.state == 'failed':
            colour = COLORS['error']
        elif request.state in ('applied', 'chosen'):
            colour = COLORS['success']
        widgets['status'].configure(text=text, fg=colour)
        widgets['choose'].configure(state='disabled' if request.state == 'applying' else 'normal')
        if request.kind == 'missing':
            if not widgets['skip'].winfo_ismapped():
                widgets['skip'].pack(fill='x', pady=(6, 0))
            widgets['skip'].configure(state='normal' if request.state in ('waiting', 'failed') else 'disabled')
        else:
            widgets['skip'].pack_forget()

    def close_cover_window(self):
        requests = self.cover_requests()
        waiting = [request for request in requests.open() if request.kind == 'missing']
        if waiting:
            self.messages.put(('log', self.tr('cover_ask_closed', count=len(waiting))))
        requests.close()
        window = getattr(self, 'cover_window', None)
        self.cover_window, self.cover_rows, self.cover_drop = None, {}, None
        if window is not None and window.winfo_exists():
            window.destroy()

    def never_ask_cover(self):
        """« Don't ask again »: the option is turned off and saved (Options turns it back on), the window closes. The
        games still waiting keep no box art; the images already given are still applied."""
        self.ask_missing_cover.set(False)
        try:
            save_preferences(self.preferences())
        except (OSError, ValueError, tk.TclError):
            pass       # kept for this session; saved with the next options or batch
        self.messages.put(('log', self.tr('cover_ask_never_log')))
        self.close_cover_window()

    def cover_window_rows(self):
        """Refresh every row (the batch ended, a cover was applied)."""
        for request in self.cover_requests().entries.values():
            self.cover_refresh(request)

    # -- an image for a game -----------------------------------------------------------------------------------------
    def cover_dropped(self, paths):
        """From the native drop: no Tk call here (dropfiles), the window's queue does the rest."""
        self.messages.put(('cover_drop', list(paths)))

    def cover_drop_paths(self, paths):
        """A drop on the window: the game under the pointer, else the only game still waiting."""
        window = getattr(self, 'cover_window', None)
        if window is None or not window.winfo_exists() or not paths:
            return
        keys = []
        try:
            widget = window.winfo_containing(*window.winfo_pointerxy())
        except (tk.TclError, KeyError):
            widget = None
        while widget is not None:
            key = getattr(widget, '_cover_key', None)
            if key is not None:
                keys.append(key)
            widget = getattr(widget, 'master', None)
        request = target_request(self.cover_requests(), keys)
        if request is None:
            self.cover_status.set(self.tr('cover_ask_drop_on_row'))
            return
        self.give_missing_cover(request.key, Path(paths[0]))

    def choose_missing_cover(self, key):
        request = self.cover_requests().entries.get(key)
        if request is None or request.state == 'applying':
            return
        name = filedialog.askopenfilename(parent=getattr(self, 'cover_window', None) or self.app,
                                          title=self.tr('cover_ask_pick', title=request.game.title),
                                          initialdir=ROOT / 'BoxArt',
                                          filetypes=[(self.tr('images'), ' '.join('*' + suffix for suffix in COVER_EXTENSIONS))])
        if name:
            self.give_missing_cover(key, Path(name))

    def give_missing_cover(self, key, path):
        """Check the image, then: a queue row takes it as its chosen box art; an exported game keeps it as its own cover
        and gets it applied once nothing else runs."""
        requests = self.cover_requests()
        request = requests.entries.get(key)
        if request is None or request.state == 'applying':
            return False
        if request.kind == 'queue' and self.busy and request.row in getattr(self, 'active_rows', ()) \
                and self.row_status.get(request.row) in ('waiting', 'converting'):
            self.cover_refresh(requests.refuse(key, 'cover_pick_busy'))     # its conversion already started
            return False
        try:
            payload = read_cover(path)
            cover = Path(path)
            if request.kind != 'queue':
                from .game_details import Cards
                cover = Cards().set_cover(request.game, payload, override=True)
        except CoverRefused as refused:
            self.cover_refresh(requests.refuse(key, refused.key))
            return False
        except (OSError, ValueError) as error:
            request.state = 'failed'
            self.cover_refresh(requests.refuse(key, str(error)))
            return False
        requests.give(key, payload)
        # The queue row takes it as its chosen box art: its next conversion uses it.
        item = self.items.get(request.row) if request.row else None
        if item is not None and (request.kind == 'queue' or (item.system, item.sha256) == request.key):
            item.cover = cover
            try:
                self.table.set(request.row, 'cover', self.tr('chosen'))
            except tk.TclError:
                pass
            if request.kind == 'queue':
                self.use_cover.set(True)
        if request.kind == 'card':
            self.card_cover_shown(request, 'cover_ask_ready' if request.source else 'cover_pick_no_rom')
        self.messages.put(('log', self.tr('cover_ask_given', title=request.game.title, name=Path(path).name)))
        self.cover_refresh(request)
        self.apply_dropped_covers()
        return True

    def card_cover_shown(self, request, message):
        """The Compiled Games card of this game, when it is the one shown: its new picture and where it stands."""
        front_end = getattr(self, 'front_end_view', None)
        if front_end is not None and request.payload is not None:
            front_end.cover_changed(request.game)     # its tile on the front-end's wall too
        card = getattr(getattr(self, 'compiled_view', None), 'card', None)
        game = getattr(card, 'game', None)
        if game is None or (game.system, game.identity) != request.key:
            return
        try:
            if request.payload is not None:
                card.payload = request.payload
                card.draw_cover()
            card.message.set(self.tr(message))
        except (tk.TclError, AttributeError):
            pass

    def skip_missing_cover(self, key):
        request = self.cover_requests().entries.get(key)
        if request is not None:
            self.cover_refresh(self.cover_requests().skip(key))

    # -- applying the images to the exported games -------------------------------------------------------------------
    def apply_dropped_covers(self):
        """Rebuild the player shell of each game given an image (the reconversion of Compiled Games), once the window
        has nothing else running; while it does, look again a moment later."""
        self._cover_retry = None
        requests = self.cover_requests()
        if self.close_when_idle or not any(r.state == 'ready' and r.source for r in requests.entries.values()):
            return
        if self.busy or getattr(self, 'updating', False) or getattr(self, 'importing', False):
            self._cover_retry = self.app.after(APPLY_RETRY_MS, self.apply_dropped_covers)
            self.cover_window_rows()
            return
        ready = requests.take_ready()
        for request in ready:
            self.cover_refresh(request)
            if request.kind == 'card':
                self.card_cover_shown(request, 'cover_ask_applying')
            if request.row and request.row in self.items:
                try:
                    self.table.set(request.row, 'status', self.tr('cover_ask_applying'))
                except tk.TclError:
                    pass
        self.messages.put(('log', self.tr('cover_ask_applying_log', count=len(ready))))
        self.begin_reconvert([(request.game, request.source) for request in ready])

    def cover_reconverted(self, system, identity, status, message=''):
        """A reconversion of Compiled Games ended for one game: when it was applying a given image, say how it went."""
        request = self.cover_requests().finished((system, identity), status in ('success', 'current'), message)
        if request is None:
            return
        if request.row and request.row in self.items:
            try:
                self.table.set(request.row, 'status', self.tr(self.row_status.get(request.row, 'created')))
            except tk.TclError:
                pass
        applied = request.state == 'applied'
        if request.kind == 'card':
            self.card_cover_shown(request, 'cover_ask_applied' if applied else 'card_failed')
        self.messages.put(('log', self.tr('cover_ask_applied_log' if applied else 'cover_ask_failed_log',
                                          title=request.game.title, error=message)))
        self.cover_refresh(request)
