"""Share qualified compilation discoveries as one ROM-free file.

An export holds, for each exact ROM identity, the numeric hints that the
user's own successful conversions added to the bundled knowledge: no ROM
byte, path, image or code. An import validates the file like the bundled
bank and adds it to a separate imported bank; every later conversion still
checks native code against the reference CPU, so a wrong hint costs at most
a fallback, never a different game.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import tempfile

from . import __version__
from .knowledge import (ASSETS, FIELDS, MAX_BYTES, RESOURCE, imported_path, load, merge_records,
                        read, validate_payload)
from .knowledge_build import SYSTEMS, build_record, compact_snes, engines, qualified_reports
from .systems import profile_for_path

FORMAT = 'retro-recomp-knowledge'
VERSION = 1
SUFFIX = '.rrknowledge'
TITLE_LIMIT = 160


def _entries(system: str, record: dict) -> set:
    from .snes_knowledge import SPC_FIELDS, references
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


def adds_to(system: str, record: dict, known: dict) -> bool:
    """True when `record` holds a hint `known` lacks for the same compiler."""
    if not known or known.get('engine') != record.get('engine') or known.get('rom_bytes') != record.get('rom_bytes'):
        return bool(_entries(system, record))
    return bool(_entries(system, record) - _entries(system, known))


def _write(path: Path, document: dict) -> bytes:
    raw = json.dumps(document, separators=(',', ':'), sort_keys=True, ensure_ascii=True).encode('ascii')
    if len(raw) > MAX_BYTES:
        raise ValueError('Knowledge size budget exceeded.')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(packed); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return packed


def export_knowledge(games, destination: Path, locate=None) -> dict:
    """Write the discoveries of `games` (compiled-games entries) to one file.

    Only qualified games need their ROM; `locate(games)` may return
    {(system, identity): path} from the converter's own ROM lookup.
    """
    current = engines()
    games = [game for game in games if game.system in SYSTEMS]
    qualified = qualified_reports([game.report for game in games if game.report])
    consoles, titles, seen, pending = {}, {}, set(), []
    omitted = {'unqualified': 0, 'ram_without_rom_source': 0, 'missing_rom': 0, 'already_known': 0}
    for game in games:
        key = (game.system, game.identity)
        if key in seen:
            continue
        seen.add(key)
        if key in qualified:
            pending.append(game)
        else:
            omitted['unqualified'] += 1
    sources = locate(pending) if locate and pending else {}
    for game in pending:
        key = (game.system, game.identity)
        path = sources.get(key) or (Path(game.source) if game.source else None)
        try:
            # Same reader as the ROM lookup, ZIPs included.
            rom = profile_for_path(path, game.system).read_rom(path) if path and path.is_file() else None
        except (OSError, ValueError, RuntimeError):
            rom = None
        if rom is None or rom.sha256 != game.identity:
            omitted['missing_rom'] += 1
            continue
        record = build_record(rom, game.system, qualified.get(key), current[game.system], omitted)
        if record is None:
            continue
        if game.system == 'snes':
            compact_snes(record)
        if not adds_to(game.system, record, _bundled(game.system, game.identity)):
            omitted['already_known'] += 1
            continue
        consoles.setdefault(game.system, {})[game.identity] = record
        titles.setdefault(game.system, {})[game.identity] = str(game.title)[:TITLE_LIMIT]
    payload = validate_payload({'schema': 1, 'consoles': consoles})
    document = {'format': FORMAT, 'version': VERSION, 'converter': __version__,
                'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'titles': titles, 'knowledge': payload}
    packed = _write(Path(destination), document)
    return {'games': sum(len(records) for records in consoles.values()),
            'consoles': {system: len(records) for system, records in sorted(consoles.items())},
            'bytes': len(packed), 'omitted': omitted}


def read_exchange(path: Path) -> dict:
    """Validate a shared file: header, titles and the numeric knowledge."""
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Knowledge file exceeds its size limit.')
    document = json.loads(raw)
    if (not isinstance(document, dict) or document.get('format') != FORMAT
            or document.get('version') != VERSION
            or not set(document) <= {'format', 'version', 'converter', 'created_utc', 'titles', 'knowledge'}):
        raise ValueError('Not a Retro-Recomp knowledge file.')
    payload = validate_payload(document.get('knowledge'))
    if not set(payload['consoles']) <= set(SYSTEMS):
        raise ValueError('Unsupported console in knowledge file.')
    titles = document.get('titles', {})
    if not isinstance(titles, dict) or any(
            system not in payload['consoles'] or not isinstance(names, dict) or any(
                identity not in payload['consoles'][system] or not isinstance(title, str)
                or len(title) > TITLE_LIMIT or not title.isprintable() for identity, title in names.items())
            for system, names in titles.items()):
        raise ValueError('Invalid titles in knowledge file.')
    for name in ('converter', 'created_utc'):
        value = document.get(name, '')
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError('Invalid knowledge file header.')
    return document


def import_knowledge(path: Path) -> dict:
    """Add a shared file to the imported bank; nothing is ever removed."""
    document = read_exchange(Path(path))
    target = imported_path()
    try:
        bank = read(target)['consoles'] if target.is_file() else {}
    except (OSError, ValueError, EOFError):
        bank = {}
    counts = {'new': 0, 'enriched': 0, 'unchanged': 0, 'replaced': 0}
    for system, records in document['knowledge']['consoles'].items():
        games = bank.setdefault(system, {})
        for identity, record in records.items():
            known = games.get(identity)
            if not known:
                games[identity] = record; counts['new'] += 1
            elif known.get('engine') == record.get('engine') and known.get('rom_bytes') == record.get('rom_bytes'):
                if adds_to(system, record, known):
                    merged = merge_records(system, known, record)
                    if system == 'snes':
                        compact_snes(merged)
                    games[identity] = merged; counts['enriched'] += 1
                else:
                    counts['unchanged'] += 1
            else:
                # Another compiler revision: the most recent import is kept.
                games[identity] = record; counts['replaced'] += 1
    _write(target, validate_payload({'schema': 1, 'consoles': {k: v for k, v in bank.items() if v}}))
    titles_path = target.with_name('imported-titles.json')
    try:
        names = json.loads(titles_path.read_text(encoding='utf-8'))
        names = names if isinstance(names, dict) else {}
    except (OSError, ValueError):
        names = {}
    for system, values in document.get('titles', {}).items():
        current = names.get(system) if isinstance(names.get(system), dict) else {}
        names[system] = {**current, **values}
    titles_path.write_text(json.dumps(names, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'games': sum(len(records) for records in document['knowledge']['consoles'].values()),
            'consoles': {system: len(records) for system, records in sorted(document['knowledge']['consoles'].items())},
            'converter': document.get('converter', ''), **counts}
