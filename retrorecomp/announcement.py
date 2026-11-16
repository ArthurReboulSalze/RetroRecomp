"""Arthur's message to every player: one short text the site may publish, read once when the window opens.

`GET {service}/api/v1/announcement` (online.announcement): no query, no account, nothing about the player; like every
request of the converter it carries only the converter's version in its User-Agent. The answer agreed with the site is

    {"active": true | false, "messages": {"fr": "...", "en": "..."}, "updated_utc": "..."}

The window shows the player's language when the site wrote it, otherwise English, as plain text only: line breaks and
tabs become spaces, control and format characters are left out (no markup, link or escape is ever interpreted: the text
goes to a Tk Text widget as characters), so are characters outside the Basic Multilingual Plane (Tk 8.6 cannot draw all
of them), and the text is cut at LIMIT characters. Anything else (inactive, an empty message, 204 or 404, a timeout, no
network, no service, an invalid answer) shows nothing, silently.
"""
from __future__ import annotations

import re
import time
import unicodedata

from . import online
from .languages import language_code

LIMIT = 200
TIMEOUT = 5
_SPACES = re.compile('[\t\n\r\x0b\x0c\x85   ]+')
# Unicode categories never shown: controls, format characters (bidirectional overrides, zero-width marks),
# surrogates, private use and unassigned code points.
_LEFT_OUT = frozenset(('Cc', 'Cf', 'Cs', 'Co', 'Cn'))


def clean(text) -> str:
    """`text` as one line of plain text the window can draw, at most LIMIT characters ('' for anything not a string)."""
    if not isinstance(text, str):
        return ''
    text = _SPACES.sub(' ', text)
    kept = ''.join(character for character in text
                   if ord(character) <= 0xFFFF and unicodedata.category(character) not in _LEFT_OUT)
    return _SPACES.sub(' ', kept).strip()[:LIMIT].rstrip()


def pick(answer, language: str = 'en') -> str:
    """The message of an answer for a player of `language`: theirs, else English, else ''."""
    if not isinstance(answer, dict) or answer.get('active') is not True:
        return ''
    messages = answer.get('messages')
    if not isinstance(messages, dict):
        return ''
    for code in dict.fromkeys((language_code(language), 'en')):
        text = clean(messages.get(code))
        if text:
            return text
    return ''


def fetch_answer(timeout: float = TIMEOUT) -> dict | None:
    """The site's answer now, or None (no service, offline, an error, an invalid answer). Never raises: the window
    calls it from a worker and says nothing when it fails. `timeout` bounds the whole request, not only each socket
    wait: an answer that trickles in later than that (or after a slow name lookup) is left out too. The window keeps
    the answer and picks the player's language with `pick`, again if the language changes."""
    started = time.monotonic()
    try:
        if not online.service_url():
            return None
        answer = online.announcement(timeout=timeout)
    except Exception:
        return None
    if not isinstance(answer, dict) or time.monotonic() - started > timeout:
        return None
    return answer


def fetch(language: str = 'en', timeout: float = TIMEOUT) -> str:
    """The message for a player of `language` now ('' when there is none or it cannot be read)."""
    return pick(fetch_answer(timeout), language)
