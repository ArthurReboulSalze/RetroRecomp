"""Capcom CPS-2 romsets (MAME or FBNeo ZIP). Read-only: nothing is extracted or written.

The reading is shared with the CPS-1 (capcom_sets.py). A CPS-2 romset carries the game's 20-byte decryption key as one of its files
(`ssf2.key`, MAME's `key` region): the converter reads it from the player's own archive and never supplies, embeds or downloads one.
A set without its key is refused by name.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from . import capcom_sets, cps2_catalogue
from .cps1 import display_title


def _missing_key_hint(game: dict, missing: list) -> str:
    key = cps2_catalogue.key_file(game)['name']
    if key in missing:
        return (f'The key file {key} is not in the archive: the converter needs the romset to carry it (FBNeo romsets and recent MAME '
                'romsets do) and never supplies one.')
    return ''


FAMILY = capcom_sets.Family('CPS-2', cps2_catalogue, _missing_key_hint)


@dataclass(frozen=True)
class Cps2Set(capcom_sets.CapcomSet):
    """A CPS-2 set. Its members include the key file (region `key`)."""
    system_id: str = 'cps2'
    tier: str = 'experimental'

    @property
    def key_member(self) -> dict:
        return next(item for item in self.members if item['region'] == 'key')


def archive_members(path: Path) -> tuple[dict, ...]:
    return capcom_sets.archive_members(path, FAMILY)


def looks_like_cps2_zip(path: Path, games: list[dict] | None = None) -> bool:
    """At least two program ROMs of one catalogued set must be present."""
    return capcom_sets.looks_like_zip(FAMILY, path, games)


def identify_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> dict:
    return capcom_sets.identify(FAMILY, path, games, set_name)[0]


def read_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> Cps2Set:
    """Identify, then hash every required file (the key file included); CRC and SHA-1 must both agree."""
    found = capcom_sets.read_set(FAMILY, path, games, set_name, lambda game: display_title(game['title']), 'cps2',
                                 lambda game: 'experimental')
    return Cps2Set(**{name: getattr(found, name) for name in found.__dataclass_fields__})
