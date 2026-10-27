"""Share compilation discoveries as one ROM-free file.

An export holds, for each exact ROM identity, the numeric hints that the
user's own successful conversions added to the base's qualified paths, and the raw
gameplay observations not yet turned into hints by a conversion, as positions
in the ROM: no ROM byte, path, image or code. An import validates the file like the qualified
bank and adds it to a separate imported bank; every later conversion still
checks native code against the reference CPU, so a wrong hint costs at most
a fallback, never a different game. Paths fetched from the shared base before
a batch (`import_fetched`) join the same banks under the same checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
import zlib

from . import __version__
from .knowledge import (ASSETS, FIELDS, MAX_BYTES, OBSERVATION_LIMIT, RESOURCE, imported_observations_path,
                        imported_path, load, merge_records, read, read_observations, valid_observation_rows,
                        validate_payload, write_observations, write_packed)
from .knowledge_build import SYSTEMS as CARTRIDGE_SYSTEMS, build_record, compact_snes, engines, qualified_reports
from .systems import profile_for_path

# Consoles whose discoveries travel. Neo Geo's are numeric offsets into the
# player's cartridge and BIOS, named by key(cartridge, BIOS) and checked by
# neogeo_knowledge.validate_record; it shares no raw gameplay observations.
SYSTEMS = (*CARTRIDGE_SYSTEMS, 'ng')

FORMAT = 'retro-recomp-knowledge'
# Version 2 adds ROM-free raw observations; version 1 files still import.
VERSION = 2
SUFFIX = '.rrknowledge'
TITLE_LIMIT = 160
CACHE_NAME = 'discoveries-cache.json.gz'
# Games per console in a knowledge payload (validate_payload's bound).
CONSOLE_LIMIT = 4096


def _entries(system: str, record: dict) -> set:
    if system == 'ng':
        from .neogeo_knowledge import entry_set
        return entry_set(record)
    from .snes_knowledge import SPC_FIELDS, references
    if system not in FIELDS:
        return set()   # CPS-1 and X68000 have no shared knowledge (1.5.2 raised KeyError before every Standard batch)
    entries = {(name, tuple(entry)) for name in FIELDS[system] if name not in SPC_FIELDS
               for entry in record.get(name, [])}
    if system == 'snes':
        entries |= {('spc', reference) for reference in references(record)}
    return entries


def _bundled(system: str, identity: str) -> dict:
    from .knowledge import qualified_record
    return qualified_record(system, identity)


def unknown_hints(system: str, record: dict, *known: dict) -> int:
    """How many hints of `record` none of `known` holds for the same ROM."""
    entries = _entries(system, record)
    for other in known:
        if other and other.get('rom_bytes') == record.get('rom_bytes'):
            entries -= _entries(system, other)
    return len(entries)


def adds_to(system: str, record: dict, known: dict) -> bool:
    """True when `record` holds a hint `known` lacks for the same compiler."""
    return unknown_hints(system, record, known) > 0


def _imported_bank() -> dict:
    target = imported_path()
    try:
        return read(target)['consoles'] if target.is_file() else {}
    except (OSError, ValueError, EOFError):
        return {}


def _observation_bank() -> dict:
    target = imported_observations_path()
    try:
        return read_observations(target) if target.is_file() else {}
    except (OSError, ValueError, EOFError):
        return {}


def _merge(system: str, identity: str, first: dict, second: dict):
    """Union of two records of one game; None when a Neo Geo union would
    exceed its bounds (the caller keeps what it had)."""
    if system != 'ng':
        return merge_records(system, first, second)
    from .neogeo_knowledge import merged_record
    try:
        return merged_record(identity, first, second)
    except (ValueError, TypeError, KeyError):
        return None


def _observation_key(row) -> tuple:
    """A shared row's identity: kind, address, auxiliary and length."""
    return tuple(row[:4])


def shareable_observations(system: str, identity: str, rom) -> tuple[list, int]:
    """This player's raw observations as ROM-free numbers: the bytes become
    their position in the player's own ROM. Code found only in RAM (built by
    the game, not copied from its ROM) has no such position and stays local."""
    from .feedback import records
    data = bytes(rom.data)
    rows, ram_only = [], 0
    for row in records(system, identity):
        offset = data.find(row.data)
        if offset < 0:
            ram_only += 1
            continue
        rows.append([row.kind, row.address, row.auxiliary, len(row.data), offset])
    return sorted(rows), ram_only


def _local_keys(system: str, identity: str) -> set:
    from .feedback import records
    return {(row.kind, row.address, row.auxiliary, len(row.data)) for row in records(system, identity)}


# 3 (1.5.6): counts made before held Standard for the Mega Drive, Super
# Nintendo and NES games converted deeper.
CACHE_SCHEMA = 3


def _cache_path() -> Path:
    return imported_path().with_name(CACHE_NAME)


def clear_discoveries_cache() -> bool:
    """Forget every cached count (Options › Disk space); True when there was one.
    Nothing else is touched: the next count reads every game again."""
    try:
        _cache_path().unlink()
        return True
    except FileNotFoundError:
        return False


def _load_cache() -> dict:
    try:
        raw = gzip.decompress(_cache_path().read_bytes())
        data = json.loads(raw) if len(raw) <= MAX_BYTES else {}
        # Schema 2 (1.5.5): no longer tied to the converter's version number, so
        # an update that changes no engine keeps every counted game. Raise
        # CACHE_SCHEMA when the way a contribution is counted changes.
        return data.get('games', {}) if data.get('schema') == CACHE_SCHEMA else {}
    except (OSError, ValueError, EOFError, AttributeError):
        return {}


def _signature(game, engine: str, context: str) -> str:
    """When a game's contribution may have changed: its files (the
    collection's stat signature), its compiler and the ROM search folders.
    Without a file signature nothing is cached."""
    watch = getattr(game, 'watch', '')
    if not watch:
        return ''
    return '|'.join((watch, engine, context, getattr(game, 'status', '')))


def _empty_outcome() -> dict:
    return {'omitted': dict.fromkeys(('unqualified', 'ram_without_rom_source', 'missing_rom',
                                      'already_known', 'ram_only'), 0),
            'record': None, 'found': 0, 'observations': []}


def _current_engines() -> dict:
    """The compiler revision each console's records are built with. Neo Geo's
    is the emulator core and the loader together."""
    from .neogeo_build import GEOLITH_REV, LITHOGEN_REV
    return {**engines(), 'ng': f'{GEOLITH_REV}:{LITHOGEN_REV}'}


def _collect_neo_geo(game, report: dict | None, outcome: dict) -> None:
    """A Neo Geo game's contribution, counted in `outcome`. Its record is
    already numbers (offsets into the cartridge and the BIOS) in the player's
    library, written only from routes a fresh reference run reached, so no ROM
    is read here. It is shared only when the library's record is the one the
    qualified report was built with: same cartridge, BIOS and compiler."""
    from .neogeo_build import GEOLITH_REV, LITHOGEN_REV
    from .neogeo_knowledge import IDENTITY_FIELDS, compact_record, key, library_record
    omitted = outcome['omitted']
    try:
        cart, bios = report['prepared_cartridge']['sha256'], report['bios']['sha256']
        compiler = report['compiler']
        identity = key(cart, bios)
    except (KeyError, TypeError):
        omitted['unqualified'] += 1
        return
    record = library_record(identity)
    if (record is None or compiler.get('revision') != GEOLITH_REV or compiler.get('loader_revision') != LITHOGEN_REV
            or (record['engine'], record['loader'], record['cart'], record['bios']) != (GEOLITH_REV, LITHOGEN_REV, cart, bios)):
        omitted['unqualified'] += 1
        return
    shared = compact_record(identity, record)
    outcome['identity'] = identity
    found = unknown_hints('ng', shared, _bundled('ng', identity))
    if found:
        outcome.update(record=shared, found=found, level=str(report.get('scan_level') or 'standard'))
    else:
        omitted['already_known'] += 1
        from .compiled_games import report_level
        # The record without hints that stands for a conversion with nothing new.
        outcome['converted'] = {'engine': shared['engine'], 'rom_bytes': shared['rom_bytes'],
                                'level': report_level(report),
                                'record': {**{name: shared[name] for name in IDENTITY_FIELDS},
                                           'rom_entries': [], 'ram_refs': [], 'z80_refs': []}}


def collect_knowledge(games, locate=None, context: str = '', progress=None) -> dict:
    """The discoveries of `games` (compiled-games entries), counted, unwritten.

    Qualified hints come from successful conversions; raw observations are
    included for games whose gameplay hints are newer than their last
    conversion (once reconverted, they are shared as qualified hints). Only
    those games need their ROM; `locate(games)` may return
    {(system, identity): path} from the converter's own ROM lookup. Each
    game's result is cached under its file signature, so a later export only
    revisits the games that changed. `progress(stage, done, total)`, when
    given, follows the slow part: 'roms' while the ROMs are looked for, then
    'games' for each game counted again (the cached ones cost nothing).
    """
    current = _current_engines()
    cache, fresh, outcomes, misses, seen = _load_cache(), {}, {}, [], set()
    for game in games:
        key = (game.system, game.identity)
        if game.system not in SYSTEMS or key in seen:
            continue
        seen.add(key)
        signature = _signature(game, current[game.system], context)
        entry = cache.get(f'{game.system}:{game.identity}')
        if signature and isinstance(entry, dict) and entry.get('signature') == signature:
            outcomes[key] = (game, entry['outcome'])
            fresh[f'{game.system}:{game.identity}'] = entry
        else:
            misses.append((game, signature))
    qualified = qualified_reports([game.report for game, _ in misses if game.report])
    wanted = [game for game, _ in misses if game.system != 'ng'
              and ((game.system, game.identity) in qualified or getattr(game, 'status', '') == 'new_hints')]
    if progress and wanted and locate:
        progress('roms', 0, len(wanted))
    sources = locate(wanted) if locate and wanted else {}
    for done, (game, signature) in enumerate(misses):
        if progress:
            progress('games', done, len(misses))
        key = (game.system, game.identity)
        outcome = _empty_outcome()
        raw = getattr(game, 'status', '') == 'new_hints'
        if game.system == 'ng':
            _collect_neo_geo(game, qualified.get(key), outcome)
        elif key not in qualified and not raw:
            outcome['omitted']['unqualified'] += 1
        else:
            path = sources.get(key) or (Path(game.source) if game.source else None)
            try:
                # Same reader as the ROM lookup, ZIPs included.
                rom = profile_for_path(path, game.system).read_rom(path) if path and path.is_file() else None
            except (OSError, ValueError, RuntimeError):
                rom = None
            if rom is None or rom.sha256 != game.identity:
                outcome['omitted']['missing_rom'] += 1
            else:
                if key in qualified:
                    record = build_record(rom, game.system, qualified[key], current[game.system], outcome['omitted'])
                    if record is not None:
                        if game.system == 'snes':
                            compact_snes(record)
                        found = unknown_hints(game.system, record, _bundled(game.system, game.identity))
                        if found:
                            from .compiled_games import report_level
                            outcome.update(record=record, found=found, level=report_level(qualified[key]))
                        else:
                            outcome['omitted']['already_known'] += 1
                            # Converted with nothing new: enough for an account upload to
                            # say so (online.pending; a record without hints), never exported.
                            # Its level: the deepest discovery completed (a quick check counts as standard).
                            from .compiled_games import report_level
                            outcome['converted'] = {'engine': record['engine'], 'rom_bytes': record['rom_bytes'],
                                                    'level': report_level(qualified[key])}
                else:
                    outcome['omitted']['unqualified'] += 1
                if raw:
                    rows, ram_only = shareable_observations(game.system, game.identity, rom)
                    outcome['observations'] = rows
                    outcome['omitted']['ram_only'] += ram_only
        outcomes[key] = (game, outcome)
        if signature:
            fresh[f'{game.system}:{game.identity}'] = {'signature': signature, 'outcome': outcome}
    try:
        write_packed(_cache_path(), {'schema': CACHE_SCHEMA, 'games': fresh})
    except (OSError, ValueError):
        pass
    consoles, observations, titles, levels, discoveries, converted = {}, {}, {}, {}, 0, {}
    omitted = _empty_outcome()['omitted']
    for (system, identity), (game, outcome) in outcomes.items():
        identity = outcome.get('identity', identity)   # Neo Geo: key(cartridge, BIOS), not the file's hash
        for name, value in outcome['omitted'].items():
            omitted[name] = omitted.get(name, 0) + value
        if outcome['record']:
            consoles.setdefault(system, {})[identity] = outcome['record']
            discoveries += outcome['found']
            # The scan level of the qualified conversion; the online board
            # rewards longer scans. Never written into the shared file.
            levels.setdefault(system, {})[identity] = outcome.get('level', 'standard')
        if outcome['observations']:
            observations.setdefault(system, {})[identity] = outcome['observations']
            discoveries += len(outcome['observations'])
        if outcome['record'] or outcome['observations']:
            titles.setdefault(system, {})[identity] = str(game.title)[:TITLE_LIMIT]
        if outcome.get('converted'):
            converted.setdefault(system, {})[identity] = {**outcome['converted'], 'title': str(game.title)[:TITLE_LIMIT]}
    sharing = {system: len(names) for system, names in sorted(titles.items())}
    return {'games': sum(sharing.values()), 'consoles': sharing,
            'discoveries': discoveries, 'omitted': omitted,
            'observations': observations, 'observation_count': sum(
                len(rows) for games in observations.values() for rows in games.values()),
            'payload': validate_payload({'schema': 1, 'consoles': consoles}), 'titles': titles,
            'levels': levels, 'converted': converted}


def write_knowledge(collected: dict, destination: Path, channel: str | None = 'file') -> dict:
    """Write what `collect_knowledge` found to one shared file. With no
    `channel`, nothing is marked as shared: an upload marks it once accepted."""
    document = {'format': FORMAT, 'version': VERSION, 'converter': __version__,
                'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'titles': collected['titles'], 'knowledge': collected['payload'],
                'observations': collected.get('observations', {})}
    packed = write_packed(Path(destination), document)
    if channel:
        mark_shared(channel, collected)
    return {**{key: collected[key] for key in ('games', 'consoles', 'discoveries', 'omitted')},
            'observation_count': collected.get('observation_count', 0), 'bytes': len(packed)}


def export_knowledge(games, destination: Path, locate=None, context: str = '') -> dict:
    """Collect then write the discoveries of `games` to one file."""
    return write_knowledge(collect_knowledge(games, locate, context), destination)


def _shared_path() -> Path:
    return imported_path().with_name('shared.json')


def _contributions(collected: dict) -> dict:
    """One digest per game and kind of discovery, to tell what is new."""
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    result = {}
    for system, records in collected['payload'].get('consoles', {}).items():
        for identity, record in records.items():
            result.setdefault(f'{system}:{identity}', {})['hints'] = digest(record)
    for system, games in collected.get('observations', {}).items():
        for identity, rows in games.items():
            result.setdefault(f'{system}:{identity}', {})['observations'] = digest(rows)
    return result


def pending_since_shared(channel: str, collected: dict) -> list:
    """Games whose discoveries changed since they were last shared on
    `channel` ('file' for exports; a future account upload sends only these)."""
    try:
        shared = json.loads(_shared_path().read_text(encoding='utf-8')).get(channel, {})
    except (OSError, ValueError, AttributeError):
        shared = {}
    return sorted(key for key, parts in _contributions(collected).items()
                  if any(shared.get(key, {}).get(kind) != value for kind, value in parts.items()))


def forget_shared(channel: str, keys) -> None:
    """Forget that the games `keys` ('system:identity') were shared on
    `channel`: their next send or export carries them again."""
    path = _shared_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    entries = data.get(channel) if isinstance(data, dict) else None
    if not isinstance(entries, dict) or not any(key in entries for key in keys):
        return
    for key in keys:
        entries.pop(key, None)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + '\n', encoding='utf-8')


def mark_shared(channel: str, collected: dict) -> None:
    path = _shared_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    entries = data.setdefault(channel, {})
    for key, parts in _contributions(collected).items():
        entries.setdefault(key, {}).update(parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + '\n', encoding='utf-8')


def read_exchange(path: Path) -> dict:
    """Validate a shared file: header, titles, the numeric knowledge and the
    ROM-free observations (version 2)."""
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Knowledge file exceeds its size limit.')
    document = json.loads(raw)
    if (not isinstance(document, dict) or document.get('format') != FORMAT
            or document.get('version') not in (1, 2)
            or not set(document) <= {'format', 'version', 'converter', 'created_utc', 'titles',
                                     'knowledge', 'observations'}
            or (document.get('version') == 1 and 'observations' in document)):
        raise ValueError('Not a Retro-Recomp knowledge file.')
    payload = validate_payload(document.get('knowledge'))
    if not set(payload['consoles']) <= set(SYSTEMS):
        raise ValueError('Unsupported console in knowledge file.')
    observations = document.setdefault('observations', {})
    if not isinstance(observations, dict) or not set(observations) <= set(SYSTEMS):
        raise ValueError('Unsupported console in knowledge file.')
    for system, games in observations.items():
        if not isinstance(games, dict):
            raise ValueError('Invalid shared observations.')
        for identity, rows in games.items():
            if not isinstance(identity, str) or len(identity) != 64 or set(identity) - set('0123456789abcdef'):
                raise ValueError('Invalid shared observations.')
            if system == 'ng' and rows:
                raise ValueError('Neo Geo shares no raw observations.')
            games[identity] = valid_observation_rows(system, rows)
    titles = document.get('titles', {})
    if not isinstance(titles, dict) or any(
            not isinstance(names, dict) or any(
                (identity not in payload['consoles'].get(system, {})
                 and identity not in observations.get(system, {}))
                or not isinstance(title, str) or len(title) > TITLE_LIMIT or not title.isprintable()
                for identity, title in names.items())
            for system, names in titles.items()):
        raise ValueError('Invalid titles in knowledge file.')
    for name in ('converter', 'created_utc'):
        value = document.get(name, '')
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError('Invalid knowledge file header.')
    return document


PATH_LIMIT = 4096


def _path_key(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()[:16]


def discovery_paths(document: dict) -> dict:
    """The discoveries of a validated shared file, as short stable keys per
    game, for the online leaderboard: hints the base's qualified paths lack and
    raw observations (by kind, address, auxiliary and length). `known` tells
    whether the qualified paths already had this ROM. At most PATH_LIMIT
    keys of each kind per game (the smallest ones), so a game converted for
    the first time cannot flood the board."""
    games = {}
    for system, records in document['knowledge']['consoles'].items():
        for identity, record in records.items():
            bundled = _bundled(system, identity)
            known = _entries(system, bundled) if bundled.get('rom_bytes') == record.get('rom_bytes') else set()
            keys = sorted({_path_key([name, list(entry)]) for name, entry in _entries(system, record) - known})
            games[(system, identity)] = {'known': bool(bundled), 'hints': keys[:PATH_LIMIT], 'observations': []}
    for system, rows_by_game in document['observations'].items():
        for identity, rows in rows_by_game.items():
            game = games.setdefault((system, identity), {'known': bool(_bundled(system, identity)), 'hints': [],
                                                         'observations': []})
            game['observations'] = sorted({_path_key(['obs', *row[:4]]) for row in rows})[:PATH_LIMIT]
    return games


def _unknown_observations(system: str, identity: str, rows, imported) -> list:
    known = _local_keys(system, identity) | {_observation_key(row) for row in imported}
    return [row for row in rows if _observation_key(row) not in known]


def preview_import(path: Path) -> dict:
    """Check a shared file before importing it: how many of its hints and
    observations are unknown here (neither bundled, local nor already
    imported), whatever compiler revision found them."""
    document = read_exchange(Path(path))
    bank, observed = _imported_bank(), _observation_bank()
    found = {}
    for system, records in document['knowledge']['consoles'].items():
        for identity, record in records.items():
            count = unknown_hints(system, record, _bundled(system, identity),
                                  bank.get(system, {}).get(identity, {}))
            if count:
                found[(system, identity)] = found.get((system, identity), 0) + count
    for system, games in document['observations'].items():
        for identity, rows in games.items():
            count = len(_unknown_observations(system, identity, rows,
                                              observed.get(system, {}).get(identity, [])))
            if count:
                found[(system, identity)] = found.get((system, identity), 0) + count
    consoles = {}
    for system, _ in found:
        consoles[system] = consoles.get(system, 0) + 1
    return {'games': len(found), 'discoveries': sum(found.values()), 'consoles': consoles,
            'converter': document.get('converter', '')}


def import_knowledge(path: Path) -> dict:
    """Add a shared file to the imported banks; nothing is ever removed.

    Records of every compiler revision are kept and merged: hints only guide
    discovery, and each conversion still validates the native code. Raw
    observations join their own ROM-free bank.
    """
    return _import_document(read_exchange(Path(path)))


def _valid_record(system: str, identity: str, record) -> dict | None:
    """One cartridge record checked like a shared file's, or None."""
    try:
        return validate_payload({'schema': 1, 'consoles': {system: {identity: record}}})['consoles'][system][identity]
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _salvaged_record(system: str, identity: str, record) -> dict | None:
    """A received record without its rows that fail the checks: one malformed
    or incoherent row is left out alone, never the record's other paths."""
    if system == 'ng':
        from .neogeo_knowledge import salvaged_record
        return salvaged_record(identity, record)
    clean = _valid_record(system, identity, record)
    if clean is not None or not isinstance(record, dict):
        return clean
    base = {name: record[name] for name in ('engine', 'rom_bytes') if name in record}
    if _valid_record(system, identity, base) is None:
        return None
    salvaged = dict(base)
    for name, (_, limit) in FIELDS[system].items():
        rows = record.get(name)
        if isinstance(rows, list):
            kept = [row for row in rows if _valid_record(system, identity, {**base, name: [row]}) is not None]
            if kept:
                salvaged[name] = kept[:limit]
    return _valid_record(system, identity, salvaged)


def salvaged_record(system: str, identity: str, record) -> dict | None:
    """`record` as the banks would keep it (its malformed rows left out), or None."""
    return _salvaged_record(system, identity, record)


def import_fetched(roms: dict) -> dict:
    """Add what the shared base served before a batch (`online.fetch_knowledge`:
    {'system:sha256': {'records': [...], 'observations': [...]}}) to the
    imported banks, exactly like an imported file. Each record and row is
    checked like a shared file's; an invalid row is skipped, not its record,
    and an invalid record not the ROM.
    `accepted` counts, per ROM, the valid records and distinct rows received."""
    consoles, observations, accepted = {}, {}, {}
    for key, value in roms.items():
        system, _, identity = key.partition(':') if isinstance(key, str) else ('', '', '')
        if system not in SYSTEMS or len(identity) != 64 or set(identity) - set('0123456789abcdef') \
                or not isinstance(value, dict):
            continue
        record, count = None, 0
        for raw in value.get('records') if isinstance(value.get('records'), list) else ():
            candidate = _salvaged_record(system, identity, raw)
            if candidate is None:
                continue
            count += 1
            merged = _merge(system, identity, record, candidate) if record else candidate
            if system == 'snes' and merged is not candidate:
                compact_snes(merged)
            # Merging never pushes a record past the bank's own limits.
            record = merged if merged is candidate else _valid_record(system, identity, merged) or record
        rows, seen = [], set()
        for row in value.get('observations') if isinstance(value.get('observations'), list) and system != 'ng' else ():
            try:
                clean = valid_observation_rows(system, [row])[0]
            except (ValueError, TypeError, KeyError):
                continue
            if _observation_key(clean) not in seen and len(rows) < OBSERVATION_LIMIT:
                seen.add(_observation_key(clean))
                rows.append(clean)
        if record:
            consoles.setdefault(system, {})[identity] = record
        if rows:
            observations.setdefault(system, {})[identity] = rows
        accepted[key] = {'records': count, 'observations': len(rows)}
    outcome = (_import_document({'knowledge': {'schema': 1, 'consoles': consoles}, 'observations': observations,
                                 'titles': {}, 'converter': ''})
               if consoles or observations else {'games': 0, 'consoles': {}, 'converter': '',
                                                  'new': 0, 'enriched': 0, 'unchanged': 0})
    return {**outcome, 'accepted': accepted}


# --- The shared base's game entries (online.sync_base) ------------------------
#
# An entry is one game as the base holds it, named by the SHA-256 of its
# canonical text: {"format": 2, "system", "identity", "qualified": [{"engine",
# "level", "by", "record"}], "parts": [{"source", "level", "record" | null,
# "observations"}]}. `qualified` holds the paths a successful conversion of
# another player (or a campaign of the maintainer) reached and validated, one
# element per engine revision; `parts` the paths still waiting, one per upload,
# so a revocation or a local rejection can target a part, not the whole game.
# Format 1 (parts only) is still read.

BASE_FORMATS = (1, 2)
BASE_PARTS_LIMIT = 4096
QUALIFIED_BY = ('maintainer', 'players')
ENGINE_LIMIT = 128


def canonical_bytes(value) -> bytes:
    """The canonical text of a JSON value, which the service hashes and signs."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def record_engine(system: str, record) -> str:
    """The engine revision a record was built with, as the base names it: the
    compiler revision of a cartridge console, the emulator core and the loader
    together for the Neo Geo."""
    if not isinstance(record, dict):
        return ''
    if system == 'ng':
        return f"{record.get('engine')}:{record.get('loader')}"
    value = record.get('engine')
    return value if isinstance(value, str) else ''


def current_engines() -> dict:
    """This converter's engine revision for each console the base serves, in
    the form `record_engine` gives (empty when it cannot be told)."""
    try:
        return _current_engines()
    except (ImportError, OSError, KeyError, ValueError):
        return {}


def base_entry(sha: str, value, system: str, identity: str) -> dict | None:
    """The game entry `value` named `sha` for this ROM, with its well-formed
    parts and qualified elements only (a malformed one is skipped, not the
    game, though `sources` still names every part); None when it is not the
    entry asked for: its canonical text must hash to `sha`, be format 1 or 2
    and name this ROM."""
    from .scan_levels import LEVELS
    if not isinstance(value, dict) or type(value.get('format')) is not int or value['format'] not in BASE_FORMATS:
        return None
    if (set(value) != {'format', 'system', 'identity', 'parts', *(('qualified',) if value['format'] >= 2 else ())}
            or value['system'] != system or value['identity'] != identity
            or not isinstance(value['parts'], list)
            or not isinstance(value.get('qualified', []), list)):
        return None
    try:
        if hashlib.sha256(canonical_bytes(value)).hexdigest() != sha:
            return None
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return None
    parts, seen = [], set()
    # Every source the entry names, whether its part is well-formed or not.
    sources = sorted({part['source'] for part in value['parts'][:BASE_PARTS_LIMIT]
                      if isinstance(part, dict) and type(part.get('source')) is int and part['source'] >= 0})
    for part in value['parts'][:BASE_PARTS_LIMIT]:
        if (not isinstance(part, dict) or type(part.get('source')) is not int or part['source'] < 0
                or part['source'] in seen or part.get('level') not in (*LEVELS, None)
                or not (part.get('record') is None or isinstance(part['record'], dict))
                or not isinstance(part.get('observations'), list)):
            continue
        seen.add(part['source'])
        parts.append({name: part[name] for name in ('source', 'level', 'record', 'observations')})
    qualified, engines = [], set()
    for item in value.get('qualified', [])[:BASE_PARTS_LIMIT]:
        if (not isinstance(item, dict) or not isinstance(item.get('engine'), str)
                or not 0 < len(item['engine']) <= ENGINE_LIMIT or item['engine'] in engines
                or item.get('level') not in LEVELS or item.get('by') not in QUALIFIED_BY
                or not isinstance(item.get('record'), dict)):
            continue
        engines.add(item['engine'])
        qualified.append({name: item[name] for name in ('engine', 'level', 'by', 'record')})
    return {'format': value['format'], 'system': system, 'identity': identity, 'parts': parts, 'sources': sources,
            'qualified': qualified}


def split_qualified(system: str, items, engine: str | None) -> tuple:
    """(the element of `items` for this converter's engine revision or None,
    the other elements). An element counts for the engine only when its record
    was really built with it."""
    current, others = None, []
    for item in items:
        if (current is None and engine and item['engine'] == engine
                and record_engine(system, item['record']) == engine):
            current = item
        else:
            others.append(item)
    return current, others


def usable_part(system: str, identity: str, part: dict) -> tuple[bool, int]:
    """(its record is valid, how many of its rows are valid) for one part of a
    base entry: what `import_fetched` will keep of it."""
    record = part.get('record') is not None and _valid_record(system, identity, part['record']) is not None
    rows = 0
    for row in (part.get('observations') or ()) if system != 'ng' else ():
        try:
            valid_observation_rows(system, [row])
            rows += 1
        except (ValueError, TypeError, KeyError):
            pass
    return record, rows


# --- The local base: datas/knowledge/base/ and the installer's copy -------------
#
# One base of paths, kept outside the executable. The installer lays a copy
# beside the program (`Retro-Recomp-base.zip`: manifest.json, index.json and
# entries/<sha>.json); it is only ever read, never unpacked wholesale. Updates
# (online.update_base) keep the newer index in `base/index.json` and, in
# `base/entries/<sha>.json`, only the entries the installer's copy lacks. An
# entry is looked up in the local folder first, then in the copy, and the
# entries no index names any more are removed. `base/state.json` says which
# version is in use and where its index lives (`origin`: "installer" points at
# the copy, without a copy of it; "download" at base/index.json).

INSTALLER_BASE = 'Retro-Recomp-base.zip'
BASE_INDEX_FORMAT = 2
BASE_INDEX_JSON_LIMIT = 64 * 1024 * 1024
BASE_ENTRY_LIMIT = 16 * 1024 * 1024
BASE_MANIFEST_LIMIT = 64 * 1024
BASE_ZIP_MEMBERS = 250000
BASE_UNPACKED_LIMIT = 1024 * 1024 * 1024
BASE_ORIGINS = ('installer', 'download')
_GAME_KEY = re.compile(r'(?:sms|gg|gb|nes|md|snes|ng):[0-9a-f]{64}')
_SHA256 = re.compile(r'[0-9a-f]{64}')
_ENTRY_NAME = re.compile(r'entries/([0-9a-f]{64})\.json')


class BaseArchiveError(ValueError):
    """A base archive that is not what it claims to be (`reason`: 'format',
    'checksum' or 'incomplete')."""

    def __init__(self, reason: str, message: str = ''):
        super().__init__(message or reason)
        self.reason = reason


def installer_base_path() -> Path:
    """The installer's copy of the base: beside the executable, or, from the
    source tree, at the repository root."""
    import sys
    from .paths import ROOT
    folder = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT
    return folder / INSTALLER_BASE


def base_directory() -> Path:
    return imported_path().with_name('base')


def qualified_bank_path() -> Path:
    """The bank of qualified paths for this converter's engines, filled from
    the base before a batch (knowledge.qualified_path() names the same file)."""
    return imported_path().with_name('qualified.json.gz')


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _count(value) -> bool:
    return type(value) is int and value >= 0


def _short(value) -> str | None:
    return value[:64] if isinstance(value, str) else None


def parse_base_index(raw: bytes, version: int | None = None) -> dict | None:
    """{'version', 'built_utc', 'games': {key: {'entry', 'sources'}}} from an
    index file's bytes, or None when it is not a format-2 index (of `version`,
    when given). A malformed game is left out; the file is bounded."""
    if len(raw) > BASE_INDEX_JSON_LIMIT:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if (not isinstance(data, dict) or type(data.get('format')) is not int or data['format'] != BASE_INDEX_FORMAT
            or not _count(data.get('version')) or (version is not None and data['version'] != version)
            or not isinstance(data.get('games'), dict)):
        return None
    games = {}
    for key, value in data['games'].items():
        if (isinstance(key, str) and _GAME_KEY.fullmatch(key) and isinstance(value, dict)
                and isinstance(value.get('entry'), str) and _SHA256.fullmatch(value['entry'])
                and isinstance(value.get('sources'), list)):
            games[key] = {'entry': value['entry'], 'sources': sorted({s for s in value['sources'] if _count(s)})}
    return {'version': data['version'], 'built_utc': _short(data.get('built_utc')), 'games': games}


def _member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes | None:
    """One archive member, read within `limit` bytes (None when absent)."""
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > limit:
        raise BaseArchiveError('format', f'{name} is too large')
    with archive.open(info) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise BaseArchiveError('format', f'{name} is too large')
    return raw


def read_archive_head(archive: zipfile.ZipFile, version: int | None = None) -> dict:
    """The verified manifest and index of a base archive: {'version',
    'built_utc', 'games', 'index_sha256', 'index', 'raw_index'}. Raises
    BaseArchiveError when the archive is not a format-2 base (of `version`,
    when given) or its index is not the one its manifest names."""
    infos = archive.infolist()
    if len(infos) > BASE_ZIP_MEMBERS or sum(info.file_size for info in infos) > BASE_UNPACKED_LIMIT:
        raise BaseArchiveError('format', 'the archive is too large')
    try:
        manifest = json.loads(_member(archive, 'manifest.json', BASE_MANIFEST_LIMIT) or b'')
    except ValueError as error:
        raise BaseArchiveError('format', 'no manifest') from error
    if (not isinstance(manifest, dict) or type(manifest.get('format')) is not int
            or manifest['format'] != BASE_INDEX_FORMAT or not _count(manifest.get('version'))
            or (version is not None and manifest['version'] != version)
            or not isinstance(manifest.get('index_sha256'), str) or not _SHA256.fullmatch(manifest['index_sha256'])):
        raise BaseArchiveError('format', 'unknown manifest')
    raw = _member(archive, 'index.json', BASE_INDEX_JSON_LIMIT)
    if raw is None or hashlib.sha256(raw).hexdigest() != manifest['index_sha256']:
        raise BaseArchiveError('checksum', 'the index is not the one the manifest names')
    index = parse_base_index(raw, manifest['version'])
    if index is None:
        raise BaseArchiveError('format', 'unknown index')
    return {'version': manifest['version'], 'built_utc': _short(manifest.get('built_utc')) or index['built_utc'],
            'games': len(index['games']), 'index_sha256': manifest['index_sha256'], 'index': index,
            'raw_index': raw}


@lru_cache(maxsize=2)
def _installer_head(path: str, size: int, modified: int):
    try:
        with zipfile.ZipFile(path) as archive:
            head = read_archive_head(archive)
            names = frozenset(match.group(1) for match in map(_ENTRY_NAME.fullmatch, archive.namelist()) if match)
    except (OSError, zipfile.BadZipFile, BaseArchiveError, NotImplementedError, RuntimeError):
        return None
    head.pop('raw_index')
    return {**head, 'entries': names}


def installer_base() -> dict | None:
    """The installer's copy as {'version', 'built_utc', 'games',
    'index_sha256', 'index', 'entries' (the entry hashes it holds)}, or None
    when it is absent or not a base. Read again when the file changes."""
    path = installer_base_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    return _installer_head(str(path), stat.st_size, stat.st_mtime_ns)


def _state_path() -> Path:
    return base_directory() / 'state.json'


def read_base_state() -> dict | None:
    """base/state.json as {'version', 'index_sha256', 'origin', 'service',
    'cursor'}, or None when it is absent or malformed."""
    try:
        data = json.loads(_state_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or not _count(data.get('version')) or data.get('origin') not in BASE_ORIGINS
            or not isinstance(data.get('index_sha256'), str) or not _SHA256.fullmatch(data['index_sha256'])):
        return None
    return {'version': data['version'], 'index_sha256': data['index_sha256'], 'origin': data['origin'],
            'service': data['service'] if isinstance(data.get('service'), str) else '',
            'cursor': data['cursor'] if _count(data.get('cursor')) else 0}


def write_base_state(base: dict, service: str = '') -> None:
    state = {'version': base['version'], 'index_sha256': base['index_sha256'], 'origin': base['origin'],
             'service': service, 'cursor': base.get('cursor', 0)}
    _atomic_write(_state_path(), (json.dumps(state, indent=1, sort_keys=True) + '\n').encode('utf-8'))


def _downloaded_base(state: dict | None) -> dict | None:
    if not state or state['origin'] != 'download':
        return None
    try:
        with open(base_directory() / 'index.json', 'rb') as file:
            raw = file.read(BASE_INDEX_JSON_LIMIT + 1)
    except OSError:
        return None
    if hashlib.sha256(raw).hexdigest() != state['index_sha256']:
        return None
    index = parse_base_index(raw, state['version'])
    if index is None:
        return None
    return {'version': state['version'], 'built_utc': index['built_utc'], 'games': len(index['games']),
            'index_sha256': state['index_sha256'], 'index': index, 'origin': 'download', 'cursor': state['cursor']}


def local_base() -> dict | None:
    """The base in use: {'version', 'built_utc', 'games', 'index_sha256',
    'index', 'origin', 'cursor'} or None. The downloaded one, unless the
    installer's copy is newer (a program update brought a later base) or the
    download is damaged; without either, the copy. `cursor` is the highest record id the base is known to hold
    (0 when not known). Reads only."""
    state = read_base_state()
    local = _downloaded_base(state)
    installer = installer_base()
    if installer and (local is None or installer['version'] > local['version']):
        cursor = state['cursor'] if state and state['origin'] == 'installer' \
            and state['index_sha256'] == installer['index_sha256'] else 0
        return {'version': installer['version'], 'built_utc': installer['built_utc'], 'games': installer['games'],
                'index_sha256': installer['index_sha256'], 'index': installer['index'], 'origin': 'installer',
                'cursor': cursor}
    return local


def settle_local_base(service: str = '') -> dict | None:
    """`local_base`, with the store made to say so: the first run on the
    installer's copy points state.json at it (nothing is copied), a newer copy
    replaces the download, and the entries no index names any more are removed."""
    base = local_base()
    if base is None:
        return None
    state = read_base_state()
    if (state is None or state['version'] != base['version'] or state['origin'] != base['origin']
            or state['index_sha256'] != base['index_sha256']):
        if base['origin'] == 'installer':
            try:
                (base_directory() / 'index.json').unlink(missing_ok=True)
            except OSError:
                pass
        write_base_state(base, service)
        prune_entries(base['index'])
    return base


class BaseEntries:
    """Entry texts of the local base: the local folder first, then the
    installer's copy (opened read-only for as long as this object is used)."""

    def __init__(self):
        self.folder = base_directory() / 'entries'
        self.archive = None
        self.held = frozenset()

    def __enter__(self):
        head = installer_base()
        if head:
            try:
                self.archive = zipfile.ZipFile(installer_base_path())
                self.held = head['entries']
            except (OSError, zipfile.BadZipFile):
                self.archive = None
        return self

    def __exit__(self, *exc):
        if self.archive is not None:
            self.archive.close()
            self.archive = None

    def text(self, sha: str) -> bytes | None:
        """The bytes of entry `sha` (their hash is the caller's to check), or
        None when neither the folder nor the copy has it."""
        if not _SHA256.fullmatch(sha):
            return None
        try:
            with open(self.folder / f'{sha}.json', 'rb') as file:
                raw = file.read(BASE_ENTRY_LIMIT + 1)
            if len(raw) <= BASE_ENTRY_LIMIT:
                return raw
        except OSError:
            pass
        if self.archive is not None and sha in self.held:
            try:
                return _member(self.archive, f'entries/{sha}.json', BASE_ENTRY_LIMIT)
            except (OSError, zipfile.BadZipFile, BaseArchiveError, RuntimeError, NotImplementedError):
                return None
        return None


def prune_entries(index: dict) -> int:
    """Remove the local entries no game of `index` names. The count removed."""
    wanted = {game['entry'] for game in index['games'].values()}
    removed = 0
    try:
        names = list((base_directory() / 'entries').iterdir())
    except OSError:
        return 0
    for path in names:
        match = re.fullmatch(r'([0-9a-f]{64})\.json', path.name)
        if match and match.group(1) not in wanted:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def apply_base_archive(path: Path, *, version: int, service: str = '', cursor: int = 0) -> dict:
    """Verify the base archive at `path` (a full base, or a difference whose
    index is the complete index of `version`) and make it the local base:
    every entry it carries is checked against the hash that names it, the
    index against its manifest, and every entry the index names must be held
    by the archive, the local folder or the installer's copy. Nothing changes
    until all of it holds; the state file is written last. Raises
    BaseArchiveError (nothing applied) or OSError (the store may keep entries
    that nothing names, removed by the next pruning). Returns `local_base`."""
    folder = base_directory() / 'entries'
    written = []
    try:
        with zipfile.ZipFile(path) as archive:
            head = read_archive_head(archive, version)
            index = head['index']
            wanted = {game['entry'] for game in index['games'].values()}
            installer = (installer_base() or {}).get('entries', frozenset())
            carried = set()
            for info in archive.infolist():
                match = _ENTRY_NAME.fullmatch(info.filename)
                if not match or match.group(1) not in wanted or info.is_dir():
                    continue
                sha = match.group(1)
                carried.add(sha)
                if sha in installer or (folder / f'{sha}.json').is_file():
                    continue   # content-addressed: what is held under this name is this entry
                raw = _member(archive, info.filename, BASE_ENTRY_LIMIT)
                if raw is None or hashlib.sha256(raw).hexdigest() != sha:
                    raise BaseArchiveError('checksum', f'entry {sha[:12]} is not the one its name says')
                folder.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=sha + '.', suffix='.tmp', dir=folder)
                written.append((temporary, folder / f'{sha}.json'))
                with os.fdopen(fd, 'wb') as file:
                    file.write(raw)
                    file.flush()
                    os.fsync(file.fileno())
            for sha in wanted - carried - set(installer):
                if not (folder / f'{sha}.json').is_file():
                    raise BaseArchiveError('incomplete', f'entry {sha[:12]} is nowhere')
        for temporary, target in written:
            os.replace(temporary, target)
        written = []
        target = base_directory() / 'index.json'
        try:
            earlier = target.read_bytes()
        except OSError:
            earlier = None
        _atomic_write(target, head['raw_index'])
        base = {'version': head['version'], 'built_utc': head['built_utc'], 'games': head['games'],
                'index_sha256': head['index_sha256'], 'index': index, 'origin': 'download', 'cursor': cursor}
        try:
            write_base_state(base, service)
        except BaseException:
            # The state is the commit point: until it is written, the earlier index stays.
            try:
                if earlier is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write(target, earlier)
            except OSError:
                pass
            raise
        prune_entries(index)
        return base
    except zipfile.BadZipFile as error:
        raise BaseArchiveError('format', 'not a zip file') from error
    finally:
        for temporary, _ in written:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def read_qualified_bank() -> dict:
    """{system: {identity: record}} of the qualified bank ({} when absent or
    unreadable)."""
    path = qualified_bank_path()
    try:
        return read(path)['consoles'] if path.is_file() else {}
    except (OSError, ValueError, EOFError, zlib.error):
        return {}


def write_qualified_bank(consoles: dict) -> None:
    write_packed(qualified_bank_path(), validate_payload(
        {'schema': 1, 'consoles': {system: games for system, games in sorted(consoles.items()) if games}}))


def _import_document(document: dict) -> dict:
    """The additive merge behind `import_knowledge` and `import_fetched`."""
    target = imported_path()
    bank, observed = _imported_bank(), _observation_bank()
    outcome = {}
    for system, records in document['knowledge']['consoles'].items():
        games = bank.setdefault(system, {})
        for identity, record in records.items():
            known = games.get(identity, {})
            existed = bool(known) or bool(observed.get(system, {}).get(identity))
            # The bank keeps the bundled catalogue's bound of games per console.
            full = not known and len(games) >= CONSOLE_LIMIT
            if full or not unknown_hints(system, record, _bundled(system, identity), known):
                outcome.setdefault((system, identity), 'unchanged')
                continue
            if known:
                merged = _merge(system, identity, known, record)
                if system == 'snes':
                    compact_snes(merged)
                record = _valid_record(system, identity, merged)
                if record is None:
                    # The union would exceed a field's bound: keep what is there.
                    outcome.setdefault((system, identity), 'unchanged')
                    continue
            games[identity] = record
            outcome[(system, identity)] = 'enriched' if existed else 'new'
    for system, games in document['observations'].items():
        for identity, rows in games.items():
            current = observed.setdefault(system, {}).get(identity, [])
            existed = bool(current) or bool(bank.get(system, {}).get(identity)) or (system, identity) in outcome
            added = _unknown_observations(system, identity, rows, current)
            if not added:
                outcome.setdefault((system, identity), 'unchanged')
                continue
            observed[system][identity] = valid_observation_rows(system, (current + added)[:OBSERVATION_LIMIT])
            if outcome.get((system, identity)) not in ('new', 'enriched'):
                outcome[(system, identity)] = 'enriched' if existed else 'new'
    write_packed(target, validate_payload({'schema': 1, 'consoles': {k: v for k, v in bank.items() if v}}))
    write_observations(observed)
    titles_path = target.with_name('imported-titles.json')
    try:
        names = json.loads(titles_path.read_text(encoding='utf-8'))
        names = names if isinstance(names, dict) else {}
    except (OSError, ValueError):
        names = {}
    for system, values in document.get('titles', {}).items():
        previous = names.get(system) if isinstance(names.get(system), dict) else {}
        names[system] = {**previous, **values}
    titles_path.write_text(json.dumps(names, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    counts = {name: sum(value == name for value in outcome.values()) for name in ('new', 'enriched', 'unchanged')}
    consoles = {}
    for system, _ in outcome:
        consoles[system] = consoles.get(system, 0) + 1
    return {'games': len(outcome), 'consoles': dict(sorted(consoles.items())),
            'converter': document.get('converter', ''), **counts}


def report_game_key(report) -> tuple[str | None, bool]:
    """(the identity the shared base knows a Neo Geo conversion by, whether it
    set imported hints aside) from the conversion's report. The batch names a
    Neo Geo cartridge by its file's hash, the base by cartridge and BIOS
    together, which only the report holds."""
    from .neogeo_knowledge import key
    try:
        data = json.loads(Path(report).read_text(encoding='utf-8'))
        identity = key(data['prepared_cartridge']['sha256'], data['bios']['sha256'])
        rejected = bool((data.get('knowledge') or {}).get('imported_hints_rejected'))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, False
    return identity, rejected
