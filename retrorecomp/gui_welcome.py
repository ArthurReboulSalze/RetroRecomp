"""The welcome of the log panel: Retro-Recomp's logo typed in while nothing has been written to the log yet, then
Arthur's message to the players when the site has one (announcement.py).

The logo is plain ASCII, so every font and every interface language draws it. It is typed in column by column in
the converter's gold, blinks once, then the version, the platform and the invite fade in under it, and the message is
typed in below like on a typewriter; a small cursor then blinks for about a minute and stays lit. Every
step is a Tk after() call on the Tk thread (no thread, no busy loop), and the whole picture takes about two seconds
before the message. It only moves while the log panel is on screen: hidden (window minimised or withdrawn, Compiled
Games shown), it jumps to its last picture and stops, and the cursor blinks again once the panel is back.

The first real log line (a conversion, an import, any message of the window) clears the welcome for good, and so does
the start of a batch: the panel then works exactly as before. The welcome never reaches the session log that problem
reports carry. The message is read once, in a worker, when the window opens (launch), and only when the start-up look
for updates is on (Options) and a service is set; it is shown as plain text, in the player's language or else English.
"""
from __future__ import annotations

import math
import threading
import time
import tkinter as tk

from . import __version__, announcement, online
from .branding import COLORS
from .gui_common import PLATFORMS

# Hand-drawn in the figlet style, six rows of equal width, ASCII only.
WELCOME_LOGO = (
    r" ____      _                       ____                                ",
    r"|  _ \ ___| |_ _ __ ___           |  _ \ ___  ___ ___  _ __ ___  _ __  ",
    r"| |_) / _ \ __| '__/ _ \   _____  | |_) / _ \/ __/ _ \| '_ ` _ \| '_ \ ",
    r"|  _ <  __/ |_| | | (_) | |_____| |  _ <  __/ (_| (_) | | | | | | |_) |",
    r"|_| \_\___|\__|_|  \___/          |_| \_\___|\___\___/|_| |_| |_| .__/ ",
    r"                                                                |_|    ",
)
# The typing follows the clock, not the number of steps (a Tk timer can fire later than asked, by up to a system tick).
TYPE_STEP_MS = 20           # the logo: typed in TYPE_SECONDS whatever the steps
TYPE_SECONDS = 0.7
PAUSE_MS = 120
BLINK_MS = (90, 90, 90, 110)    # off, on, off, on
FADE_STEPS = 5              # the subtitle line fades in
FADE_MS = 45
MESSAGE_STEP_MS = 25        # the message: MESSAGE_RATE characters a second (a full 200 in about three seconds)
MESSAGE_RATE = 70
CURSOR_MS = 530
CURSOR_BLINKS = 120         # about a minute of blinking each time the panel is shown, then the cursor stays lit


def _mix(start: str, end: str, share: float) -> str:
    """The colour `share` of the way from `start` to `end` (#rrggbb)."""
    first = [int(start[index:index + 2], 16) for index in (1, 3, 5)]
    last = [int(end[index:index + 2], 16) for index in (1, 3, 5)]
    return '#' + ''.join(f'{round(a + (b - a) * share):02x}' for a, b in zip(first, last))


class WelcomeMixin:
    """The welcome of the log panel and Arthur's message."""

    # --- set-up and the message's request ---------------------------------------------------------------------------

    def start_welcome(self):
        """Arm the welcome (end of the window's construction): it plays once the log panel is first on screen."""
        self.welcome = {'state': 'waiting', 'job': None, 'answer': None, 'column': 0, 'step': 0, 'pending': [],
                        'typed': 0, 'started': 0.0, 'blinks': 0, 'cursor_on': True}
        self.welcome_styles()
        self.app.bind('<Map>', self.welcome_mapped, add='+')
        self.app.after_idle(self.welcome_mapped)

    def fetch_announcement(self):
        """Read Arthur's message in a worker when the window opens; it never delays the start. Only with the start-up
        look of Options on and a service set; nothing is said when it cannot be read."""
        if not self.check_at_startup.get() or not online.service_url():
            return
        def worker():
            answer = announcement.fetch_answer()
            if answer is not None:
                self.messages.put(('announcement', answer))
        threading.Thread(target=worker, daemon=True, name='retro-recomp-announcement').start()

    def welcome_styles(self):
        """The tags of the welcome (again when the language changes the interface face). Later tags win over earlier
        ones: the hidden columns of the logo over its gold, the typing head over both."""
        log = self.log
        try:
            fixed = self.app.tk.call('font', 'metrics', log.cget('font'), '-fixed')
        except tk.TclError:
            fixed = 0
        logo_font = log.cget('font') if str(fixed) == '1' else 'TkFixedFont'
        log.tag_configure('welcome_logo', foreground=COLORS['gold'], font=logo_font, wrap='none')
        log.tag_configure('welcome_hidden', foreground=COLORS['field'])
        log.tag_configure('welcome_head', background=COLORS['selected'])
        log.tag_configure('welcome_subtitle', foreground=COLORS['muted'], font=(self.ui_font, 9), spacing1=6)
        log.tag_configure('welcome_line', spacing1=8)
        log.tag_configure('welcome_prefix', foreground=COLORS['gold'], font=(self.ui_font, 9, 'bold'))
        log.tag_configure('welcome_message', foreground=COLORS['text'], font=(self.ui_font, 9))
        log.tag_configure('welcome_cursor', background=COLORS['gold'], font=(self.ui_font, 9))
        for name in ('welcome_hidden', 'welcome_head'):
            log.tag_raise(name)

    # --- what is shown ------------------------------------------------------------------------------------------

    def welcome_subtitle(self):
        """The line under the logo: the version and platform (as in the status line) and the invite."""
        return f'v{__version__} · {PLATFORMS[self.platform_id]} — {self.tr("ready")}'

    def welcome_message(self):
        """(prefix, text) of Arthur's message for the player's language, or None."""
        text = announcement.pick(self.welcome.get('answer'), self.language)
        return (self.tr('welcome_from_arthur'), text) if text else None

    def welcome_shown(self):
        """Whether the welcome is in the panel (playing or still)."""
        welcome = getattr(self, 'welcome', None)
        return bool(welcome) and welcome['state'] not in ('waiting', 'gone')

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
        message too when there is one, the cursor at its end)."""
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
        message = self.welcome_message() if final else None
        if message:
            self._welcome_insert('end', '\n')
            self._welcome_insert('end', message[0] + ' ', 'welcome_prefix', 'welcome_line')
            self._welcome_insert('end', message[1], 'welcome_message', 'welcome_line')
        if final:
            self._welcome_cursor_at_end()
        log.yview_moveto(0)
        if message:
            log.see('end')

    def _welcome_cursor_at_end(self):
        self.welcome['cursor_on'] = True
        self.log.tag_configure('welcome_cursor', background=COLORS['gold'])
        self._welcome_insert('end', ' ', 'welcome_cursor')

    # --- the steps ----------------------------------------------------------------------------------------------

    def welcome_mapped(self, event=None):
        """Something of the window came on screen: play the welcome the first time the log panel shows, and let the
        cursor blink again when the panel comes back."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] not in ('waiting', 'still') or welcome['job'] is not None:
            return
        if not self._welcome_visible():
            return
        if welcome['state'] == 'waiting':
            welcome.update(state='typing', column=0, started=time.monotonic())
            self._welcome_write(final=False)
            self._welcome_later(TYPE_STEP_MS, self._welcome_type)
        else:
            welcome['blinks'] = 0
            self._welcome_later(CURSOR_MS, self._welcome_blink_cursor)

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
        self._welcome_type_message_or_rest()

    def _welcome_type_message_or_rest(self):
        """After the subtitle (or when the message arrives later): type the message in, or rest with the cursor."""
        message = self.welcome_message()
        if not message:
            self._welcome_rest()
            return
        prefix, text = message
        self.welcome['pending'] = ([(character, 'welcome_prefix') for character in prefix + ' ']
                                   + [(character, 'welcome_message') for character in text])
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
        for character, kind in chunk:
            self._welcome_insert('welcome_cursor.first', character, kind, 'welcome_line')
        self.log.see('welcome_cursor.first')
        if pending:
            self._welcome_later(MESSAGE_STEP_MS, self._welcome_type_message)
        else:
            self._welcome_rest()

    def _welcome_rest(self):
        """The last picture is up: the cursor blinks while the panel is on screen."""
        self.welcome.update(state='still', blinks=0, pending=[])
        if self._welcome_visible():
            self._welcome_later(CURSOR_MS, self._welcome_blink_cursor)

    def _welcome_blink_cursor(self):
        welcome = self.welcome
        welcome['job'] = None
        try:
            if welcome['state'] != 'still':
                return
            if not self._welcome_visible():
                # Hidden: the cursor stays lit, and blinks again once the panel is back (welcome_mapped).
                welcome['cursor_on'] = True
                self.log.tag_configure('welcome_cursor', background=COLORS['gold'])
                return
            welcome['cursor_on'] = not welcome['cursor_on']
            self.log.tag_configure('welcome_cursor',
                                   background=COLORS['gold'] if welcome['cursor_on'] else COLORS['field'])
            welcome['blinks'] += 1
            if welcome['blinks'] < CURSOR_BLINKS or not welcome['cursor_on']:
                self._welcome_later(CURSOR_MS, self._welcome_blink_cursor)
        except tk.TclError:
            pass

    # --- what ends or changes it ------------------------------------------------------------------------------

    def welcome_finish(self):
        """Jump to the last picture (hidden panel, language change): no step is left waiting; the cursor blinks
        again while the panel is on screen."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone':
            return
        self._welcome_cancel()
        self._welcome_write(final=True)
        self._welcome_rest()

    def welcome_announcement(self, answer):
        """The site's answer reached the window ('announcement' message): keep it; typed in at once when the welcome
        already rests, by the animation's own step otherwise; dropped once the panel holds real lines."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone':
            return
        welcome['answer'] = answer
        if welcome['state'] != 'still' or not self.welcome_message():
            return
        self._welcome_cancel()
        if not self._welcome_visible():
            self.welcome_finish()
            return
        try:
            self._welcome_type_message_or_rest()
        except tk.TclError:
            pass

    def welcome_language(self):
        """The language changed: the welcome is written again in it, at once (refresh_language)."""
        if self.welcome_shown():
            self.welcome_styles()
            self.welcome_finish()
        elif getattr(self, 'welcome', None):
            self.welcome_styles()

    def end_welcome(self):
        """A real line reaches the log, or a batch starts: the welcome leaves for good and the panel is as before."""
        welcome = getattr(self, 'welcome', None)
        if not welcome or welcome['state'] == 'gone':
            return
        self._welcome_cancel()
        shown = welcome['state'] != 'waiting'
        welcome.update(state='gone', answer=None, pending=[])
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
