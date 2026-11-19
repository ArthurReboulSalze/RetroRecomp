"""The welcome of the log panel: Retro-Recomp's logo typed in while nothing has been written to the log yet, then the
developer's message to the players when the site has one (announcement.py).

A small ASCII terminal, in English only whatever the interface language (the owner's decision, 16 November 2026). The
logo is plain ASCII, so every font draws it. It is typed in column by column in the converter's gold, blinks once, then
the version, the platform and the invite fade in under it, and the message is typed in below like on a typewriter
(« Message from the developer: »); without a connection one calm line says so instead (« Not connected to the
Internet. »), never an error. A small cursor runs ahead of the text while it types and is gone once the last character
is out (Arthur, 20 Nov 2026: the blinking square at rest was unpleasant). Every step is a Tk after()
call on the Tk thread (no thread, no busy loop); the picture takes about a second and a half before the message. It
only moves while the log panel is on screen: hidden (window minimised or withdrawn, Compiled Games shown), it jumps to
its last picture and stops.

The first real log line (a conversion, an import, any message of the window) clears the welcome for good, and so does
the start of a batch: the panel then works exactly as before. The welcome never reaches the session log that problem
reports carry. The message is read once, in a worker, when the window opens (launch), and only when the start-up look
for updates is on (Options) and a service is set.
"""
from __future__ import annotations

import math
import threading
import time
import tkinter as tk

from . import __version__, announcement, online
from .branding import COLORS
from .gui_common import PLATFORMS
from .i18n import tr

# Hand-drawn in the figlet style, six rows of equal width, ASCII only.
WELCOME_LOGO = (
    r" ____      _                       ____                                ",
    r"|  _ \ ___| |_ _ __ ___           |  _ \ ___  ___ ___  _ __ ___  _ __  ",
    r"| |_) / _ \ __| '__/ _ \   _____  | |_) / _ \/ __/ _ \| '_ ` _ \| '_ \ ",
    r"|  _ <  __/ |_| | | (_) | |_____| |  _ <  __/ (_| (_) | | | | | | |_) |",
    r"|_| \_\___|\__|_|  \___/          |_| \_\___|\___\___/|_| |_| |_| .__/ ",
    r"                                                                |_|    ",
)
# English only, in every interface language: the terminal is not translated.
MESSAGE_PREFIX = 'Message from the developer:'
OFFLINE_LINE = 'Not connected to the Internet.'
# The typing follows the clock, not the number of steps (a Tk timer can fire later than asked, by up to a system tick).
TYPE_STEP_MS = 20           # the logo: typed in TYPE_SECONDS whatever the steps
TYPE_SECONDS = 0.7
PAUSE_MS = 120
BLINK_MS = (90, 90, 90, 110)    # off, on, off, on
FADE_STEPS = 5              # the subtitle line fades in
FADE_MS = 45
MESSAGE_STEP_MS = 25        # the message: MESSAGE_RATE characters a second (a full 200 in about 1.5 seconds)
MESSAGE_RATE = 140


def _mix(start: str, end: str, share: float) -> str:
    """The colour `share` of the way from `start` to `end` (#rrggbb)."""
    first = [int(start[index:index + 2], 16) for index in (1, 3, 5)]
    last = [int(end[index:index + 2], 16) for index in (1, 3, 5)]
    return '#' + ''.join(f'{round(a + (b - a) * share):02x}' for a, b in zip(first, last))


class WelcomeMixin:
    """The welcome of the log panel and the developer's message."""

    # --- set-up and the message's request ---------------------------------------------------------------------------

    def start_welcome(self):
        """Arm the welcome (end of the window's construction): it plays once the log panel is first on screen."""
        self.welcome = {'state': 'waiting', 'job': None, 'news': None, 'column': 0, 'step': 0, 'pending': [],
                        'typed': 0, 'started': 0.0, 'blinks': 0, 'cursor_on': True}
        self.welcome_styles()
        self.app.bind('<Map>', self.welcome_mapped, add='+')
        self.app.after_idle(self.welcome_mapped)

    def fetch_announcement(self):
        """Read the developer's message in a worker when the window opens; it never delays the start. Only with the
        start-up look of Options on and a service set. The window hears ('message', text) or ('offline', ''); nothing
        when the site has nothing to show."""
        if not self.check_at_startup.get() or not online.service_url():
            return
        def worker():
            kind, text = announcement.read()
            if kind != announcement.NOTHING:
                self.messages.put(('announcement', (kind, text)))
        threading.Thread(target=worker, daemon=True, name='retro-recomp-announcement').start()

    def welcome_styles(self):
        """The tags of the welcome, all in one fixed-width face (the log's own when it is one, else Tk's). Later tags
        win over earlier ones: the hidden columns of the logo over its gold, the typing head over both."""
        log = self.log
        face = log.cget('font')
        try:
            if str(self.app.tk.call('font', 'metrics', face, '-fixed')) != '1':
                face = 'TkFixedFont'
            actual = self.app.tk.call('font', 'actual', face)
            options = dict(zip(actual[::2], actual[1::2]))
            plain = (str(options['-family']), int(options['-size']))
        except (tk.TclError, KeyError, ValueError):
            plain = ('TkFixedFont', 9)
        bold = (*plain, 'bold')
        log.tag_configure('welcome_logo', foreground=COLORS['gold'], font=plain, wrap='none')
        log.tag_configure('welcome_hidden', foreground=COLORS['field'])
        log.tag_configure('welcome_head', background=COLORS['selected'])
        log.tag_configure('welcome_subtitle', foreground=COLORS['muted'], font=plain, spacing1=6)
        log.tag_configure('welcome_line', spacing1=8)
        log.tag_configure('welcome_prefix', foreground=COLORS['gold'], font=bold)
        log.tag_configure('welcome_message', foreground=COLORS['text'], font=plain)
        log.tag_configure('welcome_offline', foreground=COLORS['muted'], font=plain)
        log.tag_configure('welcome_cursor', background=COLORS['gold'], font=plain)
        for name in ('welcome_hidden', 'welcome_head'):
            log.tag_raise(name)

    # --- what is shown ------------------------------------------------------------------------------------------

    def welcome_subtitle(self):
        """The line under the logo: the version and platform (as in the status line) and the invite, in English."""
        return f'v{__version__} · {PLATFORMS[self.platform_id]} — {tr("ready", "en")}'

    def welcome_news(self):
        """The line under the subtitle as (text, tag) pieces: the developer's message, the offline line, or None."""
        news = self.welcome.get('news')
        if not isinstance(news, tuple) or len(news) != 2:
            return None
        kind, text = news
        if kind == announcement.MESSAGE and isinstance(text, str) and text:
            return [(MESSAGE_PREFIX + ' ', 'welcome_prefix'), (text, 'welcome_message')]
        if kind == announcement.OFFLINE:
            return [(OFFLINE_LINE, 'welcome_offline')]
        return None

    def _welcome_visible(self):
        try:
            return bool(self.log.winfo_viewable())
        except tk.TclError:
            return False

    def _welcome_later(self, delay, step):
        self.welcome['job'] = self.log.after(delay, step)

    def _welcome_cancel(self):
        job, self.welcome['job'] = self.welcome['job'], None
        if job is not None:
            try:
                self.log.after_cancel(job)
            except tk.TclError:
                pass

    def _welcome_insert(self, index, text, *tags):
        self.log.configure(state='normal')
        self.log.insert(index, text, ('welcome', *tags))
        self.log.configure(state='disabled')

    def _welcome_write(self, final):
        """Write the welcome again from the start: hidden logo and subtitle to play, or the last picture (the
        message or the offline line too when there is one, the cursor at its end)."""
        log = self.log
        log.configure(state='normal')
        log.delete('1.0', 'end')
        log.configure(state='disabled')
        hidden = () if final else ('welcome_hidden',)
        for row in WELCOME_LOGO:
            self._welcome_insert('end', row + '\n', 'welcome_logo', *hidden)
        self._welcome_insert('end', self.welcome_subtitle(), 'welcome_subtitle')
        log.tag_configure('welcome_logo', foreground=COLORS['gold'])
        log.tag_configure('welcome_subtitle', foreground=COLORS['muted'] if final else COLORS['field'])
        news = self.welcome_news() if final else None
        if news:
            self._welcome_insert('end', '\n')
            for text, tag in news:
                self._welcome_insert('end', text, tag, 'welcome_line')
        if final:
            self._welcome_cursor_at_end()
        log.yview_moveto(0)
        if news:
            log.see('end')

    def _welcome_cursor_at_end(self):
        self.welcome['cursor_on'] = True
        self.log.tag_configure('welcome_cursor', background=COLORS['gold'])
        self._welcome_insert('end', ' ', 'welcome_cursor')

    # --- the steps ----------------------------------------------------------------------------------------------

    def welcome_mapped(self, event=None):
        """Something of the window came on screen: play the welcome the first time the log panel shows."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] not in ('waiting', 'still') or welcome['job'] is not None:
            return
        if not self._welcome_visible():
            return
        if welcome['state'] == 'waiting':
            welcome.update(state='typing', column=0, started=time.monotonic())
            self._welcome_write(final=False)
            self._welcome_later(TYPE_STEP_MS, self._welcome_type)

    def _welcome_step(self, step):
        """Run one step of the animation; hidden, the welcome jumps to its last picture instead."""
        self.welcome['job'] = None
        try:
            if not self._welcome_visible():
                self.welcome_finish()
            else:
                step()
        except tk.TclError:
            pass   # the window is closing

    def _welcome_type(self):
        self._welcome_step(self._welcome_type_columns)

    def _welcome_type_columns(self):
        welcome, log = self.welcome, self.log
        width = len(WELCOME_LOGO[0])
        due = math.ceil(width * (time.monotonic() - welcome['started']) / TYPE_SECONDS)
        start, end = welcome['column'], max(welcome['column'] + 1, min(width, due))
        log.tag_remove('welcome_head', '1.0', 'end')
        for line in range(1, len(WELCOME_LOGO) + 1):
            log.tag_remove('welcome_hidden', f'{line}.{start}', f'{line}.{end}')
            if end < width:
                log.tag_add('welcome_head', f'{line}.{end}')
        welcome['column'] = end
        if end < width:
            self._welcome_later(TYPE_STEP_MS, self._welcome_type)
        else:
            log.tag_remove('welcome_hidden', '1.0', 'end')     # the line ends too
            welcome.update(state='blink', step=0)
            self._welcome_later(PAUSE_MS, self._welcome_blink)

    def _welcome_blink(self):
        self._welcome_step(self._welcome_blink_logo)

    def _welcome_blink_logo(self):
        welcome = self.welcome
        step = welcome['step']
        if step < len(BLINK_MS):
            self.log.tag_configure('welcome_logo', foreground=COLORS['field'] if step % 2 == 0 else COLORS['gold'])
            welcome['step'] = step + 1
            self._welcome_later(BLINK_MS[step], self._welcome_blink)
        else:
            welcome.update(state='subtitle', step=0)
            self._welcome_later(FADE_MS, self._welcome_fade)

    def _welcome_fade(self):
        self._welcome_step(self._welcome_fade_subtitle)

    def _welcome_fade_subtitle(self):
        welcome = self.welcome
        welcome['step'] += 1
        self.log.tag_configure('welcome_subtitle',
                               foreground=_mix(COLORS['field'], COLORS['muted'], welcome['step'] / FADE_STEPS))
        if welcome['step'] < FADE_STEPS:
            self._welcome_later(FADE_MS, self._welcome_fade)
            return
        self._welcome_cursor_at_end()
        self._welcome_type_news_or_rest()

    def _welcome_type_news_or_rest(self):
        """After the subtitle (or when the news arrives later): type the message or the offline line in, or rest."""
        news = self.welcome_news()
        if not news:
            self._welcome_rest()
            return
        self.welcome['pending'] = [(character, tag) for text, tag in news for character in text]
        self.welcome.update(state='message', cursor_on=True, typed=0, started=time.monotonic())
        self.log.tag_configure('welcome_cursor', background=COLORS['gold'])
        self._welcome_insert('welcome_cursor.first', '\n')
        self._welcome_later(MESSAGE_STEP_MS, self._welcome_type_message)

    def _welcome_type_message(self):
        self._welcome_step(self._welcome_type_characters)

    def _welcome_type_characters(self):
        welcome = self.welcome
        pending = welcome['pending']
        count = max(1, math.floor((time.monotonic() - welcome['started']) * MESSAGE_RATE) - welcome['typed'])
        chunk, pending[:count] = pending[:count], []
        welcome['typed'] += len(chunk)
        for character, tag in chunk:
            self._welcome_insert('welcome_cursor.first', character, tag, 'welcome_line')
        self.log.see('welcome_cursor.first')
        if pending:
            self._welcome_later(MESSAGE_STEP_MS, self._welcome_type_message)
        else:
            self._welcome_rest()

    def _welcome_rest(self):
        """The last picture is up: the cursor goes (drawn in the log's own colour; its place stays the anchor where a
        message arriving later is typed in, which lights it again while it types)."""
        self.welcome.update(state='still', pending=[], cursor_on=False)
        try:
            self.log.tag_configure('welcome_cursor', background=COLORS['field'])
        except tk.TclError:
            pass

    # --- what ends or changes it ------------------------------------------------------------------------------

    def welcome_finish(self):
        """Jump to the last picture (hidden panel): no step is left waiting, no cursor."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone':
            return
        self._welcome_cancel()
        self._welcome_write(final=True)
        self._welcome_rest()

    def welcome_announcement(self, news):
        """The site's answer reached the window ('announcement' message, (kind, text)): keep it; typed in at once
        when the welcome already rests, by the animation's own step otherwise; dropped once the panel holds real
        lines."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone' or welcome['news'] is not None:
            return
        welcome['news'] = news
        if welcome['state'] != 'still' or not self.welcome_news():
            return
        self._welcome_cancel()
        if not self._welcome_visible():
            self.welcome_finish()
            return
        try:
            self._welcome_type_news_or_rest()
        except tk.TclError:
            pass

    def end_welcome(self):
        """A real line reaches the log, or a batch starts: the welcome leaves for good and the panel is as before."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone':
            return
        self._welcome_cancel()
        shown = welcome['state'] != 'waiting'
        welcome.update(state='gone', news=None, pending=[])
        if not shown:
            return
        log = self.log
        try:
            ranges = log.tag_ranges('welcome')
            log.configure(state='normal')
            for start, end in reversed(list(zip(ranges[::2], ranges[1::2]))):
                log.delete(start, end)
            log.configure(state='disabled')
        except tk.TclError:
            pass
