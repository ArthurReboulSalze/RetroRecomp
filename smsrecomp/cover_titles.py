"""Artwork-only title matching, shared by local catalogues and cover services.

ROM identification and duplicate detection must never use these relaxed rules.
Callers restrict the candidates to the requested console before matching.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
import unicodedata


# Verified spelling/long-title aliases; no images or local collection paths.
TITLE_ALIASES = {
    'castleofillusion': 'Castle of Illusion Starring Mickey Mouse',
    'aresshadegyoukoumd': 'A Ressha de Ikou MD',
}
_ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
          'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'xi': '11',
          'xii': '12', 'xiii': '13', 'xiv': '14', 'xv': '15', 'xvi': '16'}
# X is intentionally a letter: Mega Man X and Mega Man 10 are distinct games.
_WORDS = {'brothers': 'bros', 'versus': 'vs', 'junior': 'jr'}
_ARTICLES = frozenset(('a', 'an', 'the', 'and', 'n'))
_SUBTITLE = re.compile(r'\s+[-\u2013\u2014]\s+|:\s*|\s+starring\s+', re.I)
_SPECIAL_EDITIONS = frozenset(('hack', 'redux', 'redesign', 'randomizer', 'remix',
                               'dx', 'deluxe', 'remastered', 'prototype', 'alpha',
                               'beta', 'demo', 'collection', 'trilogy'))


def clean_title(name: str) -> str:
    while re.search(r'\s*(?:\([^)]*\)|\[[^]]*\])\s*$', name):
        name = re.sub(r'\s*(?:\([^)]*\)|\[[^]]*\])\s*$', '', name)
    return re.sub(r'^(.+?),\s*(The|A|An)(?=\s*(?:-|:|\(|\[|$))',
                  r'\2 \1', name, flags=re.I).strip()


def normalized(name: str, *, base: bool = False) -> str:
    if base:
        name = clean_title(name)
    else:
        name = re.sub(r'^(.+?),\s*(The|A|An)(?=\s*(?:-|\(|\[|$))',
                      r'\2 \1', name, flags=re.I)
    name = unicodedata.normalize('NFKD', name).casefold()
    return ''.join(c for c in name if c.isalnum())


def _tokens(name: str) -> tuple[str, ...]:
    text = unicodedata.normalize('NFKD', name).casefold()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"['\u2019](?=[a-z])", '', text)
    words = re.findall(r'[^\W\d_]+|\d+', text)
    # Publisher branding is optional on the box, unlike words such as Super.
    if words and words[0] in ('disney', 'disneys'):
        words = words[1:]
    return tuple(_ROMAN.get(w, _WORDS.get(w, w)) for w in words if w not in _ARTICLES)


@dataclass(frozen=True)
class _Title:
    exact: str
    key: str
    numbers: tuple[str, ...]
    head: str
    subtitle: bool


@lru_cache(maxsize=8192)
def _describe(name: str) -> _Title:
    base = clean_title(name)
    tokens = _tokens(base)
    parts = _SUBTITLE.split(base, maxsplit=1)
    return _Title(normalized(base), ''.join(tokens),
                  tuple(t for t in tokens if t.isdecimal()),
                  ''.join(_tokens(parts[0])), len(parts) > 1)


def _queries(rom_name: str, title: str) -> list[str]:
    names = []
    for name in (rom_name, title):
        base = clean_title(name)
        for variant in (base, *base.split(' ~ '), TITLE_ALIASES.get(normalized(base), '')):
            if variant and variant not in names:
                names.append(variant)
    return names


def sequence_numbers(name: str) -> tuple[str, ...]:
    return _describe(name).numbers


def _editions(name: str) -> frozenset[str]:
    return frozenset(re.findall(r'\b[a-z]+\b', name.casefold())) & _SPECIAL_EDITIONS


def _near(left: str, right: str) -> float:
    """At most one edit, or two on long titles, including adjacent swaps."""
    minimum = min(len(left), len(right))
    limit = 2 if minimum >= 16 else 1
    if minimum < 6 or abs(len(left) - len(right)) > limit:
        return 0
    previous = list(range(len(right) + 1))
    before = previous
    for i, a in enumerate(left, 1):
        row = [i]
        for j, b in enumerate(right, 1):
            distance = min(previous[j] + 1, row[j - 1] + 1,
                           previous[j - 1] + (a != b))
            if i > 1 and j > 1 and a == right[j - 2] and left[i - 2] == b:
                distance = min(distance, before[j - 2] + 1)
            row.append(distance)
        if min(row) > limit:
            return 0
        before, previous = previous, row
    return 1 - previous[-1] / max(len(left), len(right)) if previous[-1] <= limit else 0


def _score(query: _Title, candidate: _Title, *, fuzzy: bool) -> float:
    if query.exact and query.exact == candidate.exact:
        return 1
    if not query.key or query.numbers != candidate.numbers:
        return 0
    if query.key == candidate.key:
        return .99
    if query.subtitle != candidate.subtitle:
        short, long = (candidate, query) if query.subtitle else (query, candidate)
        if short.key == long.head:
            return .96
        if fuzzy:
            similarity = _near(short.key, long.head)
            if similarity:
                return .86 + .01 * similarity
    if not fuzzy:
        return 0
    similarity = _near(query.key, candidate.key)
    return .90 + .01 * similarity if similarity else 0


def matching_indices(names: list[str], rom_name: str, title: str) -> list[int]:
    """Return editions of one sufficiently clear title, otherwise no match."""
    queries = [_describe(q) for q in _queries(rom_name, title)]
    # An abbreviated export label must not remove a sequel number from the ROM.
    authoritative = _describe(rom_name).numbers
    if authoritative:
        queries = [q for q in queries if q.numbers == authoritative]
    candidates = [_describe(name) for name in names]
    requested_editions = _editions(rom_name) | _editions(title)
    # Do not calculate edit distances for ordinary exact/canonical lookups.
    for fuzzy in (False, True):
        groups = {}
        for index, candidate in enumerate(candidates):
            if not _editions(names[index]) <= requested_editions:
                continue
            score = max((_score(q, candidate, fuzzy=fuzzy) for q in queries), default=0)
            if score:
                group = groups.setdefault(candidate.key, [0, []])
                group[0] = max(group[0], score)
                group[1].append(index)
        if groups:
            break
    ranked = sorted(groups.values(), key=lambda group: group[0], reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < .025):
        return []
    return ranked[0][1]


def search_queries(rom_name: str, title: str) -> list[str]:
    """Try at most three search strings, only after an earlier lookup misses."""
    names = _queries(title, rom_name)
    for name in tuple(names):
        head = _SUBTITLE.split(name, maxsplit=1)[0]
        if _describe(head).numbers == _describe(name).numbers and head not in names:
            names.append(head)
        digits = re.sub(r'\b(?:XVI|XV|XIV|XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|V|I)\b',
                        lambda m: _ROMAN[m[0].casefold()], name)
        if digits != name and digits not in names:
            names.append(digits)
    return names[:3]
