"""Share compilation discoveries as one ROM-free file.

An export holds, for each exact ROM identity, the numeric hints that the
user's own successful conversions added to the bundled knowledge, and the raw
gameplay observations not yet turned into hints by a conversion, as positions
in the ROM: no ROM byte, path, image or code. An import validates the file like the bundled
bank and adds it to a separate imported bank; every later conversion still
checks native code against the reference CPU, so a wrong hint costs at most
a fallback, never a different game. Paths fetched from the shared base before
a batch (`import_fetched`) join the same banks under the same checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from . import __version__
from .knowledge import (ASSETS, FIELDS, MAX_BYTES, OBSERVATION_LIMIT, RESOURCE, imported_observations_path,
                        imported_path, load, merge_records, read, read_observations, valid_observation_rows,
                        validate_payload, write_observations, write_packed)
from .knowledge_build import SYSTEMS, build_record, compact_snes, engines, qualified_reports
from .systems import profile_for_path

FORMAT = 'retro-recomp-knowledge'
# Version 2 adds ROM-free raw observations; version 1 files still import.
VERSION = 2
SUFFIX = '.rrknowledge'
TITLE_LIMIT = 160
CACHE_NAME = 'discoveries-cache.json.gz'
# Games per console in a knowledge payload (validate_payload's bound).
CONSOLE_LIMIT = 4096


def _entries(system: str, record: dict) -> set:
    from .snes_knowledge import SPC_FIELDS, references
    if system not in FIELDS:
        return set()   # CPS-1 and X68000 have no shared knowledge (1.5.2 raised KeyError before every Standard batch)
    entries = {(name, tuple(entry)) for name in FIELDS[system] if name not in SPC_FIELDS
               for entry in record.get(name, [])}
    if system == 'snes':
        entries |= {('spc', reference) for reference in references(record)}
    return entries


def _bundled(system: str, identity: str) -> dict:
    try:
        return load(ASSETS / RESOURCE)['consoles'].get(system, {}).get(identity, {})
    except (OSError, ValueError, TypeError, KeyError, EOFError):
        return {}


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


def _cache_path() -> Path:
    return imported_path().with_name(CACHE_NAME)


def _load_cache() -> dict:
    try:
        raw = gzip.decompress(_cache_path().read_bytes())
        data = json.loads(raw) if len(raw) <= MAX_BYTES else {}
        return data.get('games', {}) if data.get('schema') == 1 and data.get('converter') == __version__ else {}
    except (OSError, ValueError, EOFError, AttributeError):
        return {}


def _signature(game, engine: str, context: str) -> str:
    """When a game's contribution may have changed: its files (the
    collection's stat signature), its compiler and the ROM search folders.
    Without a file signature nothing is cached."""
    watch = getattr(game, 'watch', '')
    if not watch:
        return ''
    return '|'.join((watch, engine, __version__, context, getattr(game, 'status', '')))


def _empty_outcome() -> dict:
    return {'omitted': dict.fromkeys(('unqualified', 'ram_without_rom_source', 'missing_rom',
                                      'already_known', 'ram_only'), 0),
            'record': None, 'found': 0, 'observations': []}


def collect_knowledge(games, locate=None, context: str = '') -> dict:
    """The discoveries of `games` (compiled-games entries), counted, unwritten.

    Qualified hints come from successful conversions; raw observations are
    included for games whose gameplay hints are newer than their last
    conversion (once reconverted, they are shared as qualified hints). Only
    those games need their ROM; `locate(games)` may return
    {(system, identity): path} from the converter's own ROM lookup. Each
    game's result is cached under its file signature, so a later export only
    revisits the games that changed.
    """
    current = engines()
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
    wanted = [game for game, _ in misses
              if (game.system, game.identity) in qualified or getattr(game, 'status', '') == 'new_hints']
    sources = locate(wanted) if locate and wanted else {}
    for game, signature in misses:
        key = (game.system, game.identity)
        outcome = _empty_outcome()
        raw = getattr(game, 'status', '') == 'new_hints'
        if key not in qualified and not raw:
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
                            outcome.update(record=record, found=found,
                                           level=str(qualified[key].get('scan_level') or 'standard'))
                        else:
                            outcome['omitted']['already_known'] += 1
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
        write_packed(_cache_path(), {'schema': 1, 'converter': __version__, 'games': fresh})
    except (OSError, ValueError):
        pass
    consoles, observations, titles, levels, discoveries = {}, {}, {}, {}, 0
    omitted = _empty_outcome()['omitted']
    for (system, identity), (game, outcome) in outcomes.items():
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
    sharing = {system: len(names) for system, names in sorted(titles.items())}
    return {'games': sum(sharing.values()), 'consoles': sharing,
            'discoveries': discoveries, 'omitted': omitted,
            'observations': observations, 'observation_count': sum(
                len(rows) for games in observations.values() for rows in games.values()),
            'payload': validate_payload({'schema': 1, 'consoles': consoles}), 'titles': titles,
            'levels': levels}


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
    game, for the online leaderboard: hints the bundled snapshot lacks and
    raw observations (by kind, address, auxiliary and length). `known` tells
    whether the bundled snapshot already had this ROM. At most PATH_LIMIT
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


def import_fetched(roms: dict) -> dict:
    """Add what the shared base served before a batch (`online.fetch_knowledge`:
    {'system:sha256': {'records': [...], 'observations': [...]}}) to the
    imported banks, exactly like an imported file. Each record and row is
    checked like a shared file's; an invalid one is skipped, not the ROM.
    `accepted` counts, per ROM, the valid records and distinct rows received."""
    consoles, observations, accepted = {}, {}, {}
    for key, value in roms.items():
        system, _, identity = key.partition(':') if isinstance(key, str) else ('', '', '')
        if system not in SYSTEMS or len(identity) != 64 or set(identity) - set('0123456789abcdef') \
                or not isinstance(value, dict):
            continue
        record, count = None, 0
        for raw in value.get('records') if isinstance(value.get('records'), list) else ():
            candidate = _valid_record(system, identity, raw)
            if candidate is None:
                continue
            count += 1
            merged = merge_records(system, record, candidate) if record else candidate
            if system == 'snes' and merged is not candidate:
                compact_snes(merged)
            # Merging never pushes a record past the bank's own limits.
            record = merged if merged is candidate else _valid_record(system, identity, merged) or record
        rows, seen = [], set()
        for row in value.get('observations') if isinstance(value.get('observations'), list) else ():
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
                merged = merge_records(system, known, record)
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
