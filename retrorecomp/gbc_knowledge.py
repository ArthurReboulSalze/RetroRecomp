"""Numeric, ROM-free Game Boy Color paths for one exact cartridge: no ROM byte, no RAM byte, no code.

The Game Boy Color shares its paths as the experimental tier of the base (like the Game Boy Advance and the PC Engine): a path is qualified only
for the engine revision (`cores`) that validated it, and the whole sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).
The Game Boy's own sharing keeps its first format (schema 1, closed to new machines); the Color's records are schema 3 only.

What is shared (docs/GAME_BOY_COLOR.md, "Paths"): the ROM entries the recompiler was missing, as the Color's library keeps them, `(bank, address)`
of code a conversion's own routes reached in the cartridge. Both shapes already exist in schema 3 (`gb_offsets`, and `gb_rows` when a bank was seen
in the other window), so `path_profiles`, which every console's game stamp hashes, is not edited; `identity.layout` is empty. A record states the
cartridge's SHA-256 and size; the receiver reads the bytes from its own file, and the generated code is compared with the reference as always.

What never travels: code run from work RAM or HRAM, the gameplay records, titles, file names and the save.
"""
from __future__ import annotations

import hashlib
import json

from . import path_profiles as pp

SYSTEM = 'gbc'
ROM = 'rom'
CPU = 'sm83'
MAP = 'gbc'
# Raise this by hand when our use of the engine's entries changes in a way a path could notice.
PATH_REVISION = 1
BANK = 0x4000
_PROFILE = pp.PROFILES[(CPU, MAP)]
ROW_LIMIT = min(_PROFILE.caps['gb_offsets'], _PROFILE.caps['gb_rows'])
# The ceiling of each kind of path, by the name `entry_set` gives it (the form every schema 3 module exposes: the site's base builder reads it).
PATH_CAPS = {'gbc_entry': ROW_LIMIT}
# What this module's `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`).
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [ROM], 'required': [ROM], 'hashed': True, 'game': ROM},
    'paths': {CPU: {'entries': {'src': ROM}}},
}
LIBRARY_FILE = 'compilation.json'
_LIBRARY_BYTES = 4 * 1024 * 1024

UnknownFormat = pp.UnknownFormat


def engine() -> str:
    """The `cores` string of the base for this converter: the engine's pin and the revision of our use of its entries, not our game stamp."""
    from .gameboy import ENGINE_REV
    return hashlib.sha1(f'gbc:{PATH_REVISION}:{ENGINE_REV}'.encode()).hexdigest()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not a Game Boy Color record)."""
    try:
        return record['cpus'][CPU]['core']
    except (KeyError, TypeError):
        return ''


def entry_valid(bank, address, size: int) -> bool:
    return (type(bank) is int and type(address) is int and 0 <= bank < size // BANK and 0 <= address < 0x8000)


def _offset(bank: int, address: int) -> int:
    return bank * BANK + (address & (BANK - 1))


def _switched_window(bank: int, address: int) -> bool:
    """The usual place of a bank: bank 0 below 4000h, every other bank in 4000h-7FFFh. Then the offset says the address."""
    return address < BANK if bank == 0 else address >= BANK


# --- Records (schema 3 documents) ----------------------------------------------------------------------------

def build_record(sha256: str, size: int, core: str, entries) -> dict:
    """The schema 3 document of a cartridge's entries `(bank, address)`, sorted so that equal paths give equal documents."""
    entries = sorted(set(entries))
    if len(entries) > ROW_LIMIT:
        raise ValueError('A Game Boy Color record holds too many paths.')
    if not all(entry_valid(bank, address, size) for bank, address in entries):
        raise ValueError('A Game Boy Color entry is outside its cartridge.')
    paths = {}
    if entries:
        if all(_switched_window(bank, address) for bank, address in entries):
            block = {'shape': 'gb_offsets', 'src': ROM, 'table': pp.encode_table(sorted([_offset(b, a)] for b, a in entries), 1)}
        else:
            block = {'shape': 'gb_rows', 'src': ROM, 'table': pp.encode_table(sorted([_offset(b, a), a] for b, a in entries), 2)}
        paths['entries'] = [block]
    value = {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{sha256}',
             'identity': {'system': SYSTEM, 'sources': {ROM: {'bytes': size, 'sha256': sha256}}, 'layout': {}},
             'cpus': {CPU: {'map': MAP, 'core': core, 'paths': paths}}, 'devices': {}}
    return pp.validate_game(value)


def make_record(identity: str, size: int, entries=(), *, core: str | None = None) -> dict:
    return build_record(identity, size, core or engine(), entries)


def rows(record) -> list[tuple[int, int]]:
    """The entries `(bank, address)` of a record, sorted. ValueError when a row is outside the cartridge."""
    size = record['identity']['sources'][ROM]['bytes']
    out = set()
    for block in record['cpus'][CPU]['paths'].get('entries', ()):
        if block['shape'] == 'gb_offsets':
            for (offset,) in pp.decode_table(block['table'], 1, ROW_LIMIT):
                bank = offset // BANK
                out.add((bank, offset % BANK + (BANK if bank else 0)))
        else:
            for offset, address in pp.decode_table(block['table'], 2, ROW_LIMIT):
                out.add((offset // BANK, address))
    if not all(entry_valid(bank, address, size) for bank, address in out):
        raise ValueError('A Game Boy Color entry is outside its cartridge.')
    return sorted(out)


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one Game Boy Color record (the schema 3 validator, then what is this machine's own), or ValueError."""
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not a Game Boy Color record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('Game Boy Color hints do not match their cartridge.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {} or set(sources) != {ROM} or sources[ROM].get('sha256') != record['game'].split(':', 1)[1]:
            raise ValueError('Invalid Game Boy Color sources.')
        if set(record['cpus']) != {CPU} or record['devices'] or record['cpus'][CPU]['map'] != MAP:
            raise ValueError('A Game Boy Color record lists the SM83 only.')
        paths = record['cpus'][CPU]['paths']
        if set(paths) - {'entries'}:
            raise ValueError('A Game Boy Color record lists ROM entries only.')
        for block in paths.get('entries', ()):
            if block.get('src') != ROM or block['shape'] not in ('gb_offsets', 'gb_rows'):
                raise ValueError('A Game Boy Color block points into the wrong image.')
        rows(record)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid Game Boy Color record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players)."""
    if not isinstance(record, dict):
        return set()
    try:
        return {('gbc_entry', entry) for entry in rows(record)}
    except (KeyError, TypeError, ValueError):
        return set()


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same cartridge."""
    return first['game'] == second['game'] and first['identity']['sources'].get(ROM) == second['identity']['sources'].get(ROM)


def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict:
    """A record of the skeleton's cartridge holding exactly `hints` (as `entry_set` names them)."""
    source = skeleton['identity']['sources'][ROM]
    return validate_record(build_record(source['sha256'], source['bytes'], core or record_engine(skeleton),
                                        [entry for name, entry in hints if name == 'gbc_entry']))


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one cartridge. Records of another engine or another cartridge never mix: the one built by the current engine is
    kept, else the first. ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    source = first['identity']['sources'][ROM]
    return validate_record(build_record(identity, source['bytes'], record_engine(first), {*rows(first), *rows(second)}))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None: it is checked as a whole (its rows are numbers about a cartridge whose hash it states)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- What a conversion reads and writes ----------------------------------------------------------------------

def shared_entries(identity: str, size: int, *, imported: bool = True) -> set[tuple[int, int]]:
    """The entries the banks hold for this exact cartridge: the qualified side bank, only for the engine that qualified it, and, with
    `imported`, other players' paths, whatever engine found them (they only guide discovery). A record of another image is ignored."""
    from .knowledge import imported_game, qualified_game
    found = set()
    records = [qualified_game(SYSTEM, identity)]
    records = [record for record in records if record and record_engine(record) == engine()]
    if imported:
        records.append(imported_game(SYSTEM, identity))
    for record in records:
        record = salvaged_record(identity, record) if record else None
        if record is not None and record['identity']['sources'][ROM]['bytes'] == size:
            found.update(rows(record))
    return found


def remember(identity: str, size: int, entries) -> tuple[dict, bool]:
    """(record, truncated): writes this player's own record, the entries a verified conversion's library holds (never an offered one it did not
    reach). Called only after the comparison with the reference and the replay of the delivered file have passed."""
    from .library import atomic_json, entry_lock, library_root
    kept = sorted(entry for entry in set(entries) if entry_valid(*entry, size))
    record = make_record(identity, size, kept[:ROW_LIMIT])
    folder = library_root(SYSTEM) / identity
    with entry_lock(folder):
        atomic_json(folder / LIBRARY_FILE, {'system': SYSTEM, 'game': identity, 'fresh_reference_passed': True, 'record': record})
    return record, len(kept) > ROW_LIMIT


def knowledge_block(record: dict, truncated: bool, received: int) -> dict:
    """The report's `knowledge` section (what the exchange collector reads: `record_sha256`). `received` counts the entries the banks added to
    what this PC's library already had: they guided the build, and enter the library only once a route of this conversion reached them."""
    from .systems import get_profile
    return {'machine_status': get_profile(SYSTEM).status, 'shared': SYSTEM in pp.SHARED_SYSTEMS, 'cores': engine(),
            'path_revision': PATH_REVISION, 'record_sha256': record_digest(record), 'paths': {'entries': len(rows(record))},
            'truncated': truncated, 'received_entries': received, 'raw_bytes_stored': False, 'fresh_validation_required': True}


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that verified conversions reached (`<library>/gbc/<sha256>/compilation.json`), or None."""
    from .library import library_root
    path = library_root(SYSTEM) / identity / LIBRARY_FILE
    try:
        with path.open('rb') as stream:
            raw = stream.read(_LIBRARY_BYTES + 1)
        if len(raw) > _LIBRARY_BYTES:
            return None
        data = json.loads(raw)
        if data.get('system') != SYSTEM or data.get('game') != identity or not data.get('fresh_reference_passed'):
            return None
        return validate_record(data['record'], identity)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
