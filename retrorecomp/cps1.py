"""Capcom CPS-1 romsets (MAME or FBNeo ZIP). Read-only: nothing is extracted or written.

Members are matched by CRC32 and size, then checked against the catalogue's
SHA-1 when read, so renamed members and both romset dialects are accepted.
A split clone reads its shared files from the parent ZIP in the same folder.
The ZIP name never creates a match on its own.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from . import cps1_catalogue, zip_sets

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
# A merged ZIP holds every revision of a game; read members by streaming.
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 1024


def display_title(title: str) -> str:
    """MAME's title with the subtitle separated as in the other consoles'
    names ("1941 - Counter Attack", not "1941: Counter Attack", which Windows
    filenames would turn into "1941_ Counter Attack")."""
    return title.replace(': ', ' - ')


@dataclass(frozen=True)
class Cps1Set:
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

    @property
    def size(self):
        return sum(item['bytes'] for item in self.members)

    @property
    def supported(self):
        return self.support == 'phase1'

    def metadata(self):
        return {'console': self.system_id, 'title': self.title, 'set': self.set_name,
                'parent': self.parent, 'sha256': self.sha256,
                'members': [{k: v for k, v in item.items() if k not in ('archive', 'archive_path')}
                            for item in self.members],
                'support': self.support, 'reason': self.reason, 'rotation': self.rotation,
                'board': self.board, 'mapper': self.mapper, 'alternatives': list(self.alternatives)}


def archive_members(path: Path) -> tuple[dict, ...]:
    """Bounds are checked before any decompression."""
    records = []
    with zip_sets.zip_errors('CPS-1'):
        zip_sets.check_size(path, MAX_ARCHIVE_BYTES, label='CPS-1')
        with ZipFile(path) as archive:
            for entry in zip_sets.bounded_entries(archive, label='CPS-1',
                                                  max_members=MAX_MEMBERS, max_expanded=MAX_EXPANDED_BYTES):
                if entry.flag_bits & 1:
                    raise ValueError('Encrypted CPS-1 archive member.')
                if entry.file_size > MAX_MEMBER_BYTES:
                    raise ValueError('CPS-1 archive member exceeds the size limit.')
                records.append({'name': zip_sets.flat_name(entry.filename),
                                'archive_path': entry.filename, 'bytes': entry.file_size, 'crc32': entry.CRC})
    return tuple(sorted(records, key=lambda item: item['archive_path']))


def _keys(records) -> set:
    return {(item['crc32'], item['bytes']) for item in records}


def _parent_path(path: Path, game: dict) -> Path | None:
    if not game['parent']:
        return None
    parent = path.parent / (game['parent'] + '.zip')
    return parent if parent.is_file() and parent.resolve() != path.resolve() else None


def looks_like_cps1_zip(path: Path, games: list[dict] | None = None) -> bool:
    """At least two program ROMs of one catalogued set must be present."""
    games = cps1_catalogue.games() if games is None else games
    present = _keys(archive_members(path))
    return any(sum((item['crc32'], item['bytes']) in present for item in cps1_catalogue.program_files(game)) >= 2
               for game in games)


def identify_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> dict:
    return _identify(path, cps1_catalogue.games() if games is None else games, set_name)[0]


def _identify(path: Path, games: list[dict], set_name: str | None) -> tuple[dict, list[dict]]:
    """Return the chosen set and every other complete set in the archive."""
    own = _keys(archive_members(path))
    parents = {}

    def available(game):
        parent = _parent_path(path, game)
        if parent is None:
            return own
        if parent not in parents:
            parents[parent] = _keys(archive_members(parent))
        return own | parents[parent]

    def needed(game):
        return {(item['crc32'], item['bytes']) for item in cps1_catalogue.files(game)}

    def programs(game):
        return {(item['crc32'], item['bytes']) for item in cps1_catalogue.program_files(game)}

    # A candidate's program must come from this ZIP, at least in part.
    partial = [game for game in games if (set_name is None or game['set'] == set_name) and programs(game) & own]
    if not partial:
        raise ValueError('CPS-1 program ROMs not recognized. Use a MAME or FBNeo CPS-1 romset; '
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
    family = [game for game in complete if stem in (game['set'].casefold(), game['parent'].casefold())]
    if family:
        order = {game['set']: index for index, game in enumerate(games)}
        chosen = min(family, key=lambda game: (game['support'] != 'phase1', order[game['set']]))
        return chosen, [game for game in complete if game is not chosen]
    if len(complete) > 1:
        raise ValueError('Ambiguous CPS-1 set: select ' + ', '.join(game['set'] for game in complete))
    best = max(candidates, key=lambda game: len(needed(game) & available(game)))
    missing = sorted(item['name'] for item in cps1_catalogue.files(best)
                     if (item['crc32'], item['bytes']) not in available(best))
    hint = f' Place {best["parent"]}.zip beside it.' if best['parent'] and _parent_path(path, best) is None else ''
    raise ValueError(f'CPS-1 set {best["set"]} is incomplete: missing {", ".join(missing)}.{hint}')


def _read_member(archive: ZipFile, record: dict) -> dict:
    return zip_sets.read_member_digests(archive, record['archive_path'], record['bytes'],
                                        ('sha1', 'sha256'), label='CPS-1')


def read_set(path: Path, games: list[dict] | None = None, *, set_name: str | None = None) -> Cps1Set:
    """Identify, then hash every required file; CRC and SHA-1 must both agree."""
    game, others = _identify(path, cps1_catalogue.games() if games is None else games, set_name)
    sources = [path] + ([parent] if (parent := _parent_path(path, game)) else [])
    members = []
    for source in sources:
        if len(members) == len(cps1_catalogue.files(game)):
            break
        records = archive_members(source)
        wanted = [item for item in cps1_catalogue.files(game)
                  if item['name'] not in {member['name'] for member in members}]
        with zip_sets.zip_errors('CPS-1'), ZipFile(source) as archive:
            for item in wanted:
                record = next((r for r in records if (r['crc32'], r['bytes']) == (item['crc32'], item['bytes'])), None)
                if record is None:
                    continue
                digests = _read_member(archive, record)
                if digests['sha1'] != item['sha1']:
                    raise ValueError(f'CPS-1 member {record["archive_path"]} has the CRC of {item["name"]} '
                                     'but different contents.')
                members.append({'name': item['name'], 'region': item['region'], 'bytes': item['bytes'],
                                'crc32': item['crc32'], 'sha256': digests['sha256'],
                                'archive': str(source), 'archive_path': record['archive_path']})
    if len(members) != len(cps1_catalogue.files(game)):
        raise ValueError('CPS-1 set ' + game['set'] + ' changed while it was being read.')
    members.sort(key=lambda item: item['name'])
    # Archive names, dialect and member aliases do not change the board's bytes.
    identity = hashlib.sha256(json.dumps({'set': game['set'], 'files': [
        [item['name'], item['bytes'], item['sha256']] for item in members]}).encode()).hexdigest()
    return Cps1Set(path, display_title(game['title']), game['set'], game['parent'], tuple(members), identity,
                   game['support'], game['reason'], game['rotation'], game['board'], game['mapper'],
                   tuple(other['set'] for other in others))
