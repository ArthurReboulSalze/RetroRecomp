"""Numeric, ROM-free PC Engine paths for one exact HuCard: no ROM byte, no RAM byte, no code.

The PC Engine shares its paths as the experimental tier of the base (like the CPS-1, the CPS-2 and the X68000): a path is qualified only for the engine
revision (`cores`) that validated it, and the whole sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

What is shared. The engine knows an instruction by its logical PC, all eight bank registers (MPRs) and its bytes. A conversion's captures hold those; a
record holds numbers about the player's own decoded ROM instead:

* `insn` rows `[context << 16 | pc, offset, length]`: the instruction's bytes are `length` bytes at `offset` of the ROM. For code that runs from the card, that is
  where it sits. For code that runs from work RAM, it is a place of the ROM that holds the same bytes.
* `opcode_ptr` rows `[context * 8 + register, value]`: the table of MPR contexts the `insn` rows name, eight rows a context. These two shapes already exist, so
  `path_profiles`, which every console's game stamp hashes, is not edited: the profile only declares them for its map. `identity.layout` is empty, as for the CPS-2.

A player with the same card rebuilds the instructions from their own ROM (`expanded_rows`). What cannot be tied to the ROM (code generated at run time, code
run from the Backup RAM) **stays private**: it is counted, never shared. A record is made only from the captures of a conversion that then passed every check
(`promote`, `pce_conversion`), never from the paths it received. The Street Fighter II board shares nothing: its mapper's latch is not part of the engine's
identity, so a position cannot be told from a logical address, and its module is already at the engine's bound.
"""
from __future__ import annotations

import hashlib
import json

from . import path_profiles as pp

SYSTEM = 'pce'
ROM = 'rom'
CPU = 'huc6280'
MAP = 'pce'
# A path is qualified for the revision of the engine that consumed it. Raise this when our use of the engine's identities changes in a way a path could notice.
GENERATOR_REVISION = 1
ROW_LIMIT = 65536                 # the engine's bound on identities (rows of the `insn` block, the profile's cap)
CONTEXT_LIMIT = 4096              # MPR contexts of a record; the Street Fighter II board, the largest, has 466
ADDRESS_LIMIT = CONTEXT_LIMIT << 16
BANK = 0x2000
ROM_BANKS = 0x80                  # physical banks below this one are the card's
SHARED_BOARD = 'base'
# The ceiling of each kind of path, by the name `entry_set` gives it (the form every schema 3 module exposes: the site's base builder reads it).
PATH_CAPS = {'pce_insn': ROW_LIMIT}

UnknownFormat = pp.UnknownFormat


def engine() -> str:
    """The `cores` string of the base for this converter: the engine's pin and the revision of our use of it, not our game stamp."""
    from .pce_conversion import ENGINE_REV
    return hashlib.sha1(f'pce:{GENERATOR_REVISION}:{ENGINE_REV}'.encode()).hexdigest()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not a PC Engine record)."""
    try:
        return record['cpus'][CPU]['core']
    except (KeyError, TypeError):
        return ''


def source_facts(rom: bytes) -> dict:
    return {ROM: {'bytes': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}}


def bank_map(size: int) -> list[int]:
    """The ROM bank behind each of the 128 physical banks of the standard board, as the pinned engine maps them (`hucard_bank_map`), mirrors included."""
    banks = size // BANK
    if not banks or size % BANK:
        raise ValueError('A HuCard holds whole banks.')
    if banks == 48:
        return [bank & 31 if bank < 0x40 else 0x20 + (bank & 15) for bank in range(ROM_BANKS)]
    if banks == 64:
        return [bank & 63 if bank < 0x40 else 0x20 + (bank & 31) for bank in range(ROM_BANKS)]
    if banks == 96:
        return [bank & 63 if bank < 0x40 else 0x40 + (bank & 31) for bank in range(ROM_BANKS)]
    return [bank % banks for bank in range(ROM_BANKS)]


def physical_of(pc: int, mpr, length: int) -> list[int]:
    """The physical address of each byte of an instruction, as the engine's decoder derives them."""
    return [mpr[((pc + index) & 0xffff) >> 13] << 13 | ((pc + index) & 0x1fff) for index in range(length)]


# --- Records (schema 3 documents) ----------------------------------------------------------------------------

def _assemble(identity: str, sources: dict, entries, core: str) -> dict:
    """The document of the rows `(mpr, pc, offset, length)`, sorted, with the contexts numbered in their sorted order: equal paths give equal documents."""
    entries = sorted({(tuple(mpr), pc, offset, length) for mpr, pc, offset, length in entries})
    contexts = {mpr: index for index, mpr in enumerate(sorted({entry[0] for entry in entries}))}
    if len(contexts) > CONTEXT_LIMIT or len(entries) > ROW_LIMIT:
        raise ValueError('A PC Engine record holds too many paths.')
    paths = {}
    if entries:
        paths['ram_code'] = [pp._table_block('insn', [[contexts[mpr] << 16 | pc, offset, length] for mpr, pc, offset, length in entries], 3, ROM),
                             pp._table_block('opcode_ptr', [[index * 8 + slot, value] for mpr, index in contexts.items() for slot, value in enumerate(mpr)], 2, ROM)]
    return {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{identity}', 'identity': {'system': SYSTEM, 'sources': sources, 'layout': {}},
            'cpus': {CPU: {'map': MAP, 'core': core, 'paths': paths}}, 'devices': {}}


def make_record(identity: str, rom: bytes, entries=(), *, core: str | None = None) -> dict:
    """The schema 3 document of a card: the size and hash of its decoded ROM, the engine, and the rows."""
    return _assemble(identity, source_facts(rom), entries, core or engine())


def rows(record) -> list[tuple]:
    """The rows `(mpr, pc, offset, length)` of a validated record. ValueError when a row names a context the table does not hold."""
    section = record['cpus'][CPU]
    profile = pp.PROFILES[(CPU, section['map'])]
    blocks = {block['shape']: block for block in section['paths'].get('ram_code', [])}
    if not blocks:
        return []
    if set(blocks) != {'insn', 'opcode_ptr'}:
        raise ValueError('A PC Engine record holds instructions and their contexts.')
    table = dict()
    for slot, value in pp.decode_table(blocks['opcode_ptr']['table'], 2, profile.caps['opcode_ptr']):
        if slot in table or value > 255:
            raise ValueError('Invalid PC Engine context table.')
        table[slot] = value
    count = len(table) // 8
    if len(table) % 8 or sorted(table) != list(range(count * 8)):
        raise ValueError('Invalid PC Engine context table.')
    out = []
    for address, offset, length in pp.decode_table(blocks['insn']['table'], 3, profile.caps['insn']):
        context, pc = address >> 16, address & 0xffff
        if context >= count:
            raise ValueError('A PC Engine path names an unknown context.')
        out.append((tuple(table[context * 8 + slot] for slot in range(8)), pc, offset, length))
    return out


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one PC Engine record (the schema 3 validator, then what is the PC Engine's own), or ValueError."""
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not a PC Engine record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('PC Engine hints do not match their card.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {} or set(sources) != {ROM} or 'sha256' not in sources[ROM]:
            raise ValueError('Invalid PC Engine layout.')
        if set(record['cpus']) != {CPU} or record['devices'] or set(record['cpus'][CPU]['paths']) - {'ram_code'}:
            raise ValueError('A PC Engine record lists its instructions only.')
        for block in record['cpus'][CPU]['paths'].get('ram_code', ()):
            if block.get('src') != ROM:
                raise ValueError('A PC Engine block points into the wrong image.')
        rows(record)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid PC Engine record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players); the contexts are named by their values, not their numbers."""
    if not isinstance(record, dict):
        return set()
    try:
        return {('pce_insn', row) for row in rows(record)}
    except (KeyError, TypeError, ValueError):
        return set()


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same ROM."""
    return first['game'] == second['game'] and first['identity']['sources'].get(ROM) == second['identity']['sources'].get(ROM)


def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict:
    """A record of the skeleton's card holding exactly `hints` (as `entry_set` names them)."""
    return validate_record(_assemble(skeleton['game'].split(':', 1)[1], skeleton['identity']['sources'], [row for name, row in hints if name == 'pce_insn'],
                                     core or record_engine(skeleton)))


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one card. Records of another engine or another ROM never mix: the one built by the current engine is kept, else the first.
    ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    return validate_record(_assemble(identity, first['identity']['sources'], {*rows(first), *rows(second)}, record_engine(first)))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None: it is checked as a whole (its rows are numbers about a ROM whose hash it states)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- Observations to paths -----------------------------------------------------------------------------------

def translate(rom: bytes, board: str, observations) -> tuple[list, dict]:
    """Paths for the observations `{'pc', 'mpr', 'data', 'physical'}` of a conversion's captures that sit in the player's own ROM. Returns the rows and the
    counts; nothing but numbers. A place in the card is where the instruction runs from; for anything else, the first place in the ROM with the same bytes."""
    seen, out = set(), []
    counts = {'observed': 0, 'card': 0, 'ram_tied': 0, 'private': 0, 'board': board}
    if board != SHARED_BOARD:
        counts['private'] = sum(1 for _ in observations)
        counts['observed'] = counts['private']
        return [], counts
    banks, found = bank_map(len(rom)), {}
    for item in observations:
        pc, mpr, data = item['pc'], tuple(item['mpr']), bytes(item['data'])
        if (mpr, pc, data) in seen:
            continue
        seen.add((mpr, pc, data))
        counts['observed'] += 1
        first = item['physical'][0]
        if first >> 13 < ROM_BANKS:
            offset = banks[first >> 13] * BANK + (first & (BANK - 1))
            if rom[offset:offset + len(data)] == data:
                out.append((mpr, pc, offset, len(data)))
                counts['card'] += 1
                continue
        if data not in found:
            found[data] = rom.find(data)
        if found[data] < 0:
            counts['private'] += 1
        else:
            out.append((mpr, pc, found[data], len(data)))
            counts['ram_tied'] += 1
    return sorted(set(out)), counts


def read_captures(paths) -> list:
    """The observations of the engine's capture files of this conversion (private files: they hold the game's bytes)."""
    observations = []
    for path in paths:
        with open(path, encoding='utf-8') as stream:
            observations += json.load(stream).get('observations', ())
    return observations


def promote(identity: str, rom: bytes, board: str, observations, *, previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts) from the captures of a verified conversion. `previous` is the library's record of this very ROM and engine; its paths are kept.
    The record holds no ROM byte, no RAM byte and no code. The limits bound the rows (`counts['truncated']`)."""
    entries, counts = translate(rom, board, observations)
    entries = set(entries)
    if previous and isinstance(previous, dict):
        try:
            validate_record(previous, identity)
            if previous['identity']['sources'][ROM] == source_facts(rom)[ROM] and record_engine(previous) == engine():
                entries |= set(rows(previous))
        except ValueError:
            pass
    kept, contexts = [], set()
    for entry in sorted(entries):
        if len(kept) >= ROW_LIMIT or (entry[0] not in contexts and len(contexts) >= CONTEXT_LIMIT):
            continue
        contexts.add(entry[0])
        kept.append(entry)
    counts['truncated'] = len(kept) < len(entries)
    record = make_record(identity, rom, kept)
    validate_record(record, identity)
    counts['paths'] = {'instructions': len(kept), 'contexts': len(contexts)}
    counts['raw_bytes_stored'] = False
    return record, counts


# --- Paths to observations -----------------------------------------------------------------------------------

def expanded_rows(record: dict, rom: bytes) -> list[dict]:
    """The instructions of a record rebuilt from the player's own ROM, as a capture's observations. ValueError when the record is not for exactly this ROM.
    Local build input; it never leaves the process's work folder."""
    validate_record(record)
    if record['identity']['sources'][ROM] != source_facts(rom)[ROM]:
        raise ValueError('PC Engine hints are for another ROM.')
    out = {}
    for mpr, pc, offset, length in rows(record):
        data = rom[offset:offset + length]
        out[(mpr, pc, data)] = {'pc': pc, 'mpr': list(mpr), 'physical': physical_of(pc, mpr, length), 'data': list(data), 'native_hits': 0, 'interpreted_hits': 1}
    return list(out.values())


def received_capture(rows_in, known, *, runtime_abi: int, capacity: int) -> tuple[dict | None, int]:
    """(capture document, rows left out): what the received rows add to the identities `known` (this conversion's own), within the engine's bound. It is a local
    input of the module, in the engine's capture format: one hit a row stands for "received", no run; the report says so (`knowledge.use`)."""
    fresh = [row for row in rows_in if (tuple(row['mpr']), row['pc'], tuple(row['data'])) not in known]
    room = max(0, capacity - len(known))
    kept = fresh[:room]
    if not kept:
        return None, len(fresh)
    return ({'schema': 1, 'runtime_abi': runtime_abi, 'capacity': capacity, 'dropped_instructions': 0, 'unreadable_instructions': 0,
             'retired_instructions': len(kept), 'complete': True, 'observations': kept}, len(fresh) - len(kept))


def shared_rows(identity: str, rom: bytes, *, qualified=None, imported=None, library=None) -> tuple[list, dict]:
    """(rows, info): the guidance of the shared and library records for this card, expanded from its ROM. Three sources, counted apart: the qualified bank (used
    only for the engine that qualified it), the player's own library record, and the imported bank (other players' paths, which guide discovery and are rechecked
    like everything else). The rows are build input only: never added to what the conversion keeps. `info` says what each gave and what was ignored and why."""
    rows_out, seen = [], set()
    info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
    current = engine()
    for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
        if not record:
            continue
        try:
            if name == 'qualified' and record_engine(record) != current:
                info['ignored'][name] = 'another engine revision'
                continue
            expanded = expanded_rows(record, rom)
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        info[name] = len(expanded)
        for row in expanded:
            key = (tuple(row['mpr']), row['pc'], tuple(row['data']))
            if key not in seen:
                seen.add(key)
                rows_out.append(row)
    return rows_out, info


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that verified conversions reached (`pce_conversion` writes it into the game's summary,
    `<library>/pce/<game>/compilation.json`), or None."""
    from .library import library_root
    path = library_root(SYSTEM) / identity / 'compilation.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            return None
        data = json.loads(raw)
        if data.get('system') != SYSTEM or data.get('game') != identity or not data.get('fresh_reference_passed'):
            return None
        return validate_record(data['record'], identity)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
