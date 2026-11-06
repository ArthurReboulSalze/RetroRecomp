"""Capcom arcade romsets (MAME or FBNeo ZIP), identified against a catalogue. Read-only: nothing is extracted or written.

Shared by the CPS-1 (`cps1.py`) and the CPS-2 (`cps2.py`): a `Family` names the catalogue and the wording of its messages, and the
functions here do the rest. Members are matched by CRC32 and size, then checked against the catalogue's SHA-1 when read, so renamed
members and both romset dialects are accepted. A split clone reads its shared files from the parent ZIP in the same folder. The ZIP
name never creates a match on its own.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable
from zipfile import ZipFile
import zlib

from . import zip_sets

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
# A merged ZIP holds every revision of a game; read members by streaming.
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 1024


@dataclass(frozen=True)
class Family:
    """One board family: its label in messages, its catalogue module (games(), files(game), program_files(game)) and, optionally,
    a sentence added to the "incomplete set" refusal for the missing file names."""
    label: str
    catalogue: object
    missing_hint: Callable[[dict, list], str] | None = None
    # Names of members that a romset dialect stores twice over (FBNeo keeps some 1 MiB ROMs as 2 MiB files whose two halves are the ROM): such a
    # member also counts as the ROM that is its half, when both halves are equal.
    doubled: frozenset = frozenset()


@dataclass(frozen=True)
class CapcomSet:
    path: Path
    title: str
    set_name: str
    parent: str
    members: tuple[dict, ...]
    sha256: str
    support: str
    reason: str
    rotation: int
    board: str
    mapper: str
    alternatives: tuple[str, ...] = ()
    system_id: str = 'cps1'
    tier: str = 'supported'

    @property
    def size(self):
        return sum(item['bytes'] for item in self.members)

    @property
    def supported(self):
        return self.support == 'phase1'

    def metadata(self):
        return {'console': self.system_id, 'title': self.title, 'set': self.set_name,
                'parent': self.parent, 'sha256': self.sha256,
                # the key file of a CPS-2 set is read to decrypt the program and never appears in a report (not even its name or hashes)
                'members': [{k: v for k, v in item.items() if k not in ('archive', 'archive_path')}
                            for item in self.members if item.get('region') != 'key'],
                'support': self.support, 'reason': self.reason, 'rotation': self.rotation,
                'board': self.board, 'mapper': self.mapper, 'alternatives': list(self.alternatives), 'tier': self.tier}


def archive_members(path: Path, family: Family) -> tuple[dict, ...]:
    """Bounds are checked before any decompression."""
    records = []
    with zip_sets.zip_errors(family.label):
        zip_sets.check_size(path, MAX_ARCHIVE_BYTES, label=family.label)
        with ZipFile(path) as archive:
            for entry in zip_sets.bounded_entries(archive, label=family.label,
                                                  max_members=MAX_MEMBERS, max_expanded=MAX_EXPANDED_BYTES):
                if entry.flag_bits & 1:
                    raise ValueError(f'Encrypted {family.label} archive member.')
                if entry.file_size > MAX_MEMBER_BYTES:
                    raise ValueError(f'{family.label} archive member exceeds the size limit.')
                records.append({'name': zip_sets.flat_name(entry.filename),
                                'archive_path': entry.filename, 'bytes': entry.file_size, 'crc32': entry.CRC})
            records += _halves(archive, records, family)
    return tuple(sorted(records, key=lambda item: item['archive_path']))


def _halves(archive: ZipFile, records: list, family: Family) -> list:
    """The ROM that is the half of each doubled member (`Family.doubled`) whose two halves are equal."""
    found = []
    for record in records:
        if record['name'] in family.doubled and record['bytes'] % 2 == 0:
            data = archive.read(record['archive_path'])
            half = len(data) // 2
            if data[:half] == data[half:]:
                found.append({**record, 'bytes': half, 'crc32': zlib.crc32(data[:half]), 'half': True})
    return found


def _keys(records) -> set:
    return {(item['crc32'], item['bytes']) for item in records}


def _parent_path(path: Path, game: dict) -> Path | None:
    if not game['parent']:
        return None
    parent = path.parent / (game['parent'] + '.zip')
    return parent if parent.is_file() and parent.resolve() != path.resolve() else None


def looks_like_zip(family: Family, path: Path, games: list[dict] | None = None) -> bool:
    """At least two program ROMs of one catalogued set must be present."""
    games = family.catalogue.games() if games is None else games
    present = _keys(archive_members(path, family))
    return any(sum((item['crc32'], item['bytes']) in present for item in family.catalogue.program_files(game)) >= 2
               for game in games)


def identify(family: Family, path: Path, games: list[dict] | None = None, set_name: str | None = None) -> tuple[dict, list[dict]]:
    """Return the chosen set and every other complete set in the archive."""
    games = family.catalogue.games() if games is None else games
    catalogue = family.catalogue
    own = _keys(archive_members(path, family))
    parents = {}

    def available(game):
        parent = _parent_path(path, game)
        if parent is None:
            return own
        if parent not in parents:
            parents[parent] = _keys(archive_members(parent, family))
        return own | parents[parent]

    def needed(game):
        return {(item['crc32'], item['bytes']) for item in catalogue.files(game)}

    def programs(game):
        return {(item['crc32'], item['bytes']) for item in catalogue.program_files(game)}

    # A candidate's program must come from this ZIP, at least in part.
    partial = [game for game in games if (set_name is None or game['set'] == set_name) and programs(game) & own]
    if not partial:
        raise ValueError(f'{family.label} program ROMs not recognized. Use a MAME or FBNeo {family.label} romset; '
                         'a renamed set from another board cannot be used.')
    candidates = [game for game in partial if programs(game) <= available(game)] or partial
    complete = [game for game in candidates if needed(game) <= available(game)]
    stem = path.stem.casefold()
    named = [game for game in complete if game['set'].casefold() == stem]
    if len(named) == 1 or len(complete) == 1:
        chosen = (named or complete)[0]
        return chosen, [game for game in complete if game is not chosen]
    # A merged archive from an older romset can lack the current parent
    # revision while holding several complete clones. Stay within the family
    # its name designates: supported boards first, then MAME's driver order.
    family_sets = [game for game in complete if stem in (game['set'].casefold(), game['parent'].casefold())]
    if family_sets:
        order = {game['set']: index for index, game in enumerate(games)}
        chosen = min(family_sets, key=lambda game: (game['support'] != 'phase1', order[game['set']]))
        return chosen, [game for game in complete if game is not chosen]
    if len(complete) > 1:
        raise ValueError(f'Ambiguous {family.label} set: select ' + ', '.join(game['set'] for game in complete))
    best = max(candidates, key=lambda game: len(needed(game) & available(game)))
    missing = sorted(item['name'] for item in catalogue.files(best)
                     if (item['crc32'], item['bytes']) not in available(best))
    hint = f' Place {best["parent"]}.zip beside it.' if best['parent'] and _parent_path(path, best) is None else ''
    extra = (' ' + family.missing_hint(best, missing)) if family.missing_hint and family.missing_hint(best, missing) else ''
    raise ValueError(f'{family.label} set {best["set"]} is incomplete: missing {", ".join(missing)}.{hint}{extra}')


def _read_member(archive: ZipFile, record: dict, family: Family) -> dict:
    if record.get('half'):
        data = archive.read(record['archive_path'])
        half = data[:len(data) // 2]
        if len(half) != record['bytes'] or data[len(half):] != half:
            raise ValueError(f'{family.label} member {record["archive_path"]} changed while it was being read.')
        return {'sha1': hashlib.sha1(half).hexdigest(), 'sha256': hashlib.sha256(half).hexdigest()}
    return zip_sets.read_member_digests(archive, record['archive_path'], record['bytes'],
                                        ('sha1', 'sha256'), label=family.label)


def read_set(family: Family, path: Path, games: list[dict] | None, set_name: str | None, title_of: Callable[[dict], str],
             system_id: str, tier_of: Callable[[dict], str]) -> CapcomSet:
    """Identify, then hash every required file; CRC and SHA-1 must both agree."""
    catalogue = family.catalogue
    game, others = identify(family, path, games, set_name)
    sources = [path] + ([parent] if (parent := _parent_path(path, game)) else [])
    members = []
    for source in sources:
        if len(members) == len(catalogue.files(game)):
            break
        records = archive_members(source, family)
        wanted = [item for item in catalogue.files(game)
                  if item['name'] not in {member['name'] for member in members}]
        with zip_sets.zip_errors(family.label), ZipFile(source) as archive:
            for item in wanted:
                record = next((r for r in records if (r['crc32'], r['bytes']) == (item['crc32'], item['bytes'])), None)
                if record is None:
                    continue
                digests = _read_member(archive, record, family)
                if digests['sha1'] != item['sha1']:
                    raise ValueError(f'{family.label} member {record["archive_path"]} has the CRC of {item["name"]} '
                                     'but different contents.')
                members.append({'name': item['name'], 'region': item['region'], 'bytes': item['bytes'],
                                'crc32': item['crc32'], 'sha256': digests['sha256'],
                                'archive': str(source), 'archive_path': record['archive_path'],
                                **({'half': True} if record.get('half') else {})})
    if len(members) != len(catalogue.files(game)):
        raise ValueError(f'{family.label} set ' + game['set'] + ' changed while it was being read.')
    members.sort(key=lambda item: item['name'])
    # Archive names, dialect and member aliases do not change the board's bytes.
    identity = hashlib.sha256(json.dumps({'set': game['set'], 'files': [
        [item['name'], item['bytes'], item['sha256']] for item in members]}).encode()).hexdigest()
    return CapcomSet(path, title_of(game), game['set'], game['parent'], tuple(members), identity,
                     game['support'], game['reason'], game['rotation'], game['board'], game['mapper'],
                     tuple(other['set'] for other in others), system_id=system_id, tier=tier_of(game))
