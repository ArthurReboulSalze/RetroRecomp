"""Capcom CPS-1 romsets (MAME or FBNeo ZIP). Read-only: nothing is extracted or written.

The reading itself is shared with the CPS-2 (capcom_sets.py). Members are matched by CRC32 and size, then checked against the catalogue's
SHA-1 when read, so renamed members and both romset dialects are accepted.
A split clone reads its shared files from the parent ZIP in the same folder.
The ZIP name never creates a match on its own.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from . import capcom_sets, cps1_catalogue

MAX_ARCHIVE_BYTES = capcom_sets.MAX_ARCHIVE_BYTES
MAX_EXPANDED_BYTES = capcom_sets.MAX_EXPANDED_BYTES
MAX_MEMBER_BYTES = capcom_sets.MAX_MEMBER_BYTES
MAX_MEMBERS = capcom_sets.MAX_MEMBERS
FAMILY = capcom_sets.Family('CPS-1', cps1_catalogue)


def display_title(title: str) -> str:
    """MAME's title with the subtitle separated as in the other consoles'
    names ("1941 - Counter Attack", not "1941: Counter Attack", which Windows
    filenames would turn into "1941_ Counter Attack")."""
    return title.replace(': ', ' - ')


def cover_titles(path: Path) -> tuple[str, ...]:
    return capcom_sets.cover_titles(FAMILY, path, display_title)


@dataclass(frozen=True)
class Cps1Set(capcom_sets.CapcomSet):
    """A CPS-1 or CPS-1.5 set; `tier` is the catalogue column ('experimental' for the QSound boards)."""


def archive_members(path: Path) -> tuple[dict, ...]:
    return capcom_sets.archive_members(path, FAMILY)


def looks_like_cps1_zip(path: Path, games: list[dict] | None = None) -> bool:
    """At least two program ROMs of one catalogued set must be present."""
    return capcom_sets.looks_like_zip(FAMILY, path, games)


def identify_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> dict:
    return _identify(path, cps1_catalogue.games() if games is None else games, set_name)[0]


def _identify(path: Path, games: list[dict], set_name: str | None) -> tuple[dict, list[dict]]:
    """Return the chosen set and every other complete set in the archive."""
    return capcom_sets.identify(FAMILY, path, games, set_name)


def read_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> Cps1Set:
    """Identify, then hash every required file; CRC and SHA-1 must both agree."""
    found = capcom_sets.read_set(FAMILY, path, games, set_name, lambda game: display_title(game['title']), 'cps1',
                                 cps1_catalogue.tier)
    return Cps1Set(**{name: getattr(found, name) for name in found.__dataclass_fields__})
