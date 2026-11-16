"""The developer's message to every player: one short English text the site may publish, read once when the window opens.

`GET {service}/api/v1/announcement` (online.announcement): no query, no account, nothing about the player; like every
request of the converter it carries only the converter's version in its User-Agent. The answer agreed with the site is

    {"active": true | false, "message": "...", "updated_utc": "ISO-8601"}

The welcome of the log panel is in English only (the owner's decision, 16 November 2026), so is the message. It is shown
as plain text only: line breaks and tabs become spaces, control and format characters are left out (no markup, link or
escape is ever interpreted: the text goes to a Tk Text widget as characters), so are characters outside the Basic
Multilingual Plane (Tk 8.6 cannot draw all of them), and the text is cut at LIMIT characters.

Three outcomes, never an error: the message; 'offline' when the site cannot be reached (no network, no name resolution,
a timeout), which the window says in one calm line; nothing when the site answered without a message to show (inactive,
empty, 204, 404, an invalid answer) or when no service is set.
"""
from __future__ import annotations

import re
import time
import unicodedata

from . import online

LIMIT = 200
TIMEOUT = 5
MESSAGE, OFFLINE, NOTHING = 'message', 'offline', 'nothing'
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


def pick(answer) -> str:
    """The message of an answer ('' when it is inactive, empty or not an answer of the agreed shape)."""
    if not isinstance(answer, dict) or answer.get('active') is not True:
        return ''
    return clean(answer.get('message'))


def read(timeout: float = TIMEOUT) -> tuple[str, str]:
    """Ask the site now: (MESSAGE, text), (OFFLINE, '') or (NOTHING, ''). Never raises: the window calls it from a
    worker. `timeout` bounds the whole request, not only each socket wait: an answer that trickles in later than that
    (or after a slow name lookup) counts as a timeout."""
    started = time.monotonic()
    try:
        if not online.service_url():
            return NOTHING, ''
        answer = online.announcement(timeout=timeout)
    except online.ServiceConnectionError:
        return OFFLINE, ''
    except Exception:
        return NOTHING, ''
    if time.monotonic() - started > timeout:
        return OFFLINE, ''
    text = pick(answer)
    return (MESSAGE, text) if text else (NOTHING, '')
