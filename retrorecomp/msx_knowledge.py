"""Numeric, ROM-free MSX and MSX2 paths for one exact cartridge: no ROM byte, no RAM byte, no code.

The MSX and the MSX2 share their paths as the experimental tier of the base (like the PC Engine and the CPS-1): a path is qualified only for the
engine revision (`cores`) that validated it, and the whole sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

What is shared. The banked Z80 chain translates every instruction position of the cartridge and of the BIOS ahead of time; what a conversion still
learns is the code the program runs from RAM, as the Master System does: the four bytes at each address the interpreter ran (`msx_build.learn`,
`native.patterns`), which the next generation emits as native bodies guarded by those four bytes. A record holds, for each such window whose
bytes are found in the player's own cartridge, its **offset** in that cartridge (the `window4` shape the Master System already shares as
`pattern_refs`); a player with the same cartridge reads the four bytes back from his own dump. A window runs native only where the bytes at the
program counter equal it, so a received window can never change what a game does: where it does not fit, the interpreter runs, counted.

What stays private, counted and never shared: windows whose bytes are not in the cartridge (code the BIOS or the game builds in RAM), and the
windows received from other players until this player's own conversion learns them (the Master System's rule, `knowledge_build._sega_offered`).
A record is made only from the windows of a conversion that then passed every check (`msx_conversion`), never from the paths it received.

The record names the cartridge and the BIOS it was found with (the profiles hash both); its windows point into the cartridge only, so they are
used under any BIOS. One module serves both machines: every function takes the machine (`system`), and `msx2_knowledge` binds it for the MSX2.
"""
from __future__ import annotations

import hashlib
import json

from . import path_profiles as pp

SYSTEMS = ('msx', 'msx2')
CPU = 'z80'
ROM = 'rom'
BIOS = 'bios'
SHAPE = 'window4'
# A path is qualified for the revision of the engine that consumed it. Raise this when our use of the windows changes in a way a path could notice.
GENERATOR_REVISION = 1
ROW_LIMIT = 4096                  # the windows a game learns at most (msx_glue.inc: `learned[4096]`; the profiles' cap)
PATH_CAPS = {'msx_window': ROW_LIMIT}
WORD = 4

UnknownFormat = pp.UnknownFormat

# What `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`, so that
# `web/lib/paths3.php` follows the converter instead of a copy of its rules; the keys are gba_knowledge's): no layout; the cartridge and the BIOS
# it was found with, both hashed, the game id the cartridge's SHA-256; the windows point into the cartridge only. Their size, four bytes inside
# the cartridge, and the ceiling are the profile's (`window4`).
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [ROM, BIOS], 'required': [ROM, BIOS], 'hashed': True, 'game': ROM},
    'paths': {CPU: {'windows': {'src': ROM}}},
}


def _system(system: str) -> str:
    if system not in SYSTEMS:
        raise ValueError(f'Not an MSX machine: {system!r}.')
    return system


def engine(system: str = 'msx') -> str:
    """The `cores` string of the base for this converter: the Z80 generator's pin and the revision of our use of it, not our game stamp."""
    from .core import ENGINE_REV
    return hashlib.sha1(f'{_system(system)}:{GENERATOR_REVISION}:{ENGINE_REV}'.encode()).hexdigest()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not an MSX record)."""
    try:
        return record['cpus'][CPU]['core']
    except (KeyError, TypeError):
        return ''


def source_facts(cartridge: bytes, bios: bytes) -> dict:
    return {ROM: {'bytes': len(cartridge), 'sha256': hashlib.sha256(cartridge).hexdigest()},
            BIOS: {'bytes': len(bios), 'sha256': hashlib.sha256(bios).hexdigest()}}


def _assemble(system: str, identity: str, sources: dict, offsets, core: str) -> dict:
    offsets = sorted(set(offsets))
    if len(offsets) > ROW_LIMIT:
        raise ValueError('An MSX record holds too many paths.')
    paths = {'windows': [pp._table_block(SHAPE, [[offset] for offset in offsets], 1, ROM)]} if offsets else {}
    return {'schema': pp.SCHEMA, 'game': f'{system}:{identity}', 'identity': {'system': system, 'sources': sources, 'layout': {}},
            'cpus': {CPU: {'map': system, 'core': core, 'paths': paths}}, 'devices': {}}


def make_record(identity: str, cartridge: bytes, bios: bytes, offsets=(), *, system: str = 'msx', core: str | None = None) -> dict:
    """The schema 3 document of a cartridge: the sizes and hashes of the cartridge and the BIOS, the engine, and the offsets."""
    return validate_record(_assemble(_system(system), identity, source_facts(cartridge, bios), offsets, core or engine(system)), identity,
                           system=system)


def rows(record) -> list[int]:
    """The offsets of a validated record."""
    section = record['cpus'][CPU]
    profile = pp.PROFILES[(CPU, section['map'])]
    out = []
    for block in section['paths'].get('windows', ()):
        out += [offset for (offset,) in pp.decode_table(block['table'], 1, profile.caps[SHAPE])]
    return out


def validate_record(record, identity: str | None = None, *, system: str = 'msx') -> dict:
    """Strict numeric allowlist of one MSX record (the schema 3 validator, then what is the MSX's own), or ValueError."""
    _system(system)
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(system + ':'):
            raise ValueError('Not a record of this MSX machine.')
        if identity is not None and record['game'] != f'{system}:{identity}':
            raise ValueError('MSX hints do not match their cartridge.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {} or set(sources) != {ROM, BIOS}:
            raise ValueError('Invalid MSX layout.')
        if record['game'] != f'{system}:{sources[ROM]["sha256"]}':
            raise ValueError('An MSX record is keyed by its cartridge.')
        section = record['cpus'][CPU]
        if set(record['cpus']) != {CPU} or record['devices'] or section['map'] != system or set(section['paths']) - {'windows'}:
            raise ValueError('An MSX record lists its RAM windows only.')
        for block in section['paths'].get('windows', ()):
            if block.get('shape') != SHAPE or block.get('src') != ROM:
                raise ValueError('An MSX window points into the wrong image.')
        if len(rows(record)) > ROW_LIMIT:
            raise ValueError('An MSX record holds too many paths.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid MSX record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players)."""
    if not isinstance(record, dict):
        return set()
    try:
        return {('msx_window', offset) for offset in rows(record)}
    except (KeyError, TypeError, ValueError):
        return set()


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same cartridge (the BIOS they were found with does not change a cartridge window)."""
    return first['game'] == second['game'] and first['identity']['sources'].get(ROM) == second['identity']['sources'].get(ROM)


def rebuild(skeleton: dict, hints, *, system: str = 'msx', core: str | None = None) -> dict:
    """A record of the skeleton's cartridge holding exactly `hints` (as `entry_set` names them)."""
    return validate_record(_assemble(system, skeleton['game'].split(':', 1)[1], skeleton['identity']['sources'],
                                     [offset for name, offset in hints if name == 'msx_window'], core or record_engine(skeleton)),
                           system=system)


def merged(identity: str, first: dict, second: dict, *, system: str = 'msx') -> dict:
    """Union of two records of one cartridge. Records of another engine or another cartridge never mix: the one built by the current engine is
    kept, else the first. ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine(system)
        return second if record_engine(second) == current and record_engine(first) != current else first
    return validate_record(_assemble(system, identity, first['identity']['sources'], {*rows(first), *rows(second)}, record_engine(first)),
                           identity, system=system)


def salvaged_record(identity: str, record, *, system: str = 'msx') -> dict | None:
    """A received record, or None: it is checked as a whole (its rows are numbers about a cartridge whose hash it states)."""
    try:
        return validate_record(record, identity, system=system)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- Windows to paths and back -------------------------------------------------------------------------------

def words(text: str) -> set[bytes]:
    """The windows of a `native.patterns` text (eight hex digits a line); other lines are ignored."""
    out = set()
    for line in text.split():
        if len(line) == 2 * WORD:
            try:
                out.add(bytes.fromhex(line))
            except ValueError:
                continue
    return out


def text_of(found) -> str:
    return ''.join(f'{word.hex().upper()}\n' for word in sorted(found))


def promote(identity: str, cartridge: bytes, bios: bytes, own, *, system: str = 'msx', previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts): the windows this player's own conversions learned (`own`, bytes of four), as offsets of their first place in the
    cartridge, united with the player's previous record of the same cartridge and engine. Windows not in the cartridge stay private, counted."""
    offsets, private = [], 0
    for word in sorted(own):
        at = cartridge.find(word)
        if at < 0:
            private += 1
        else:
            offsets.append(at)
    truncated = max(0, len(set(offsets)) - ROW_LIMIT)
    record = make_record(identity, cartridge, bios, sorted(set(offsets))[:ROW_LIMIT], system=system)
    if previous:
        try:
            record = merged(identity, record, previous, system=system)
        except ValueError:
            pass                                    # the union is over the bound: this conversion's record alone
    return record, {'own_windows': len(own), 'in_cartridge': len(set(offsets)), 'private_not_in_cartridge': private, 'truncated': truncated,
                    'paths': len(rows(record))}


def received_words(record, cartridge: bytes) -> set[bytes]:
    """The windows a record names, read back from this player's own cartridge. ValueError when it points past the cartridge."""
    out = set()
    for offset in rows(record):
        if offset + WORD > len(cartridge):
            raise ValueError('An MSX path points past the cartridge.')
        out.add(bytes(cartridge[offset:offset + WORD]))
    return out


def shared_rows(identity: str, cartridge: bytes, *, system: str = 'msx', qualified=None, imported=None, library=None) -> tuple[set, dict]:
    """(windows, info): the windows of the shared and library records for this cartridge, read from its bytes. Three sources, counted apart:
    the qualified bank (used only for the engine that qualified it), the player's own library record and the imported bank (other players'
    paths). A record of another cartridge, or one that does not validate, is ignored with its reason."""
    found = set()
    info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
    current = engine(system)
    for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
        if not record:
            continue
        try:
            record = validate_record(record, identity, system=system)
            if name == 'qualified' and record_engine(record) != current:
                info['ignored'][name] = 'another engine revision'
                continue
            if record['identity']['sources'][ROM]['bytes'] != len(cartridge):
                raise ValueError('The record names a cartridge of another size.')
            got = received_words(record, cartridge)
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        info[name] = len(got)
        found |= got
    return found, info


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str, *, system: str = 'msx') -> dict | None:
    """This player's own record: the windows that verified conversions learned (`msx_conversion` writes it into the game's summary,
    `<library>/<system>/<game>/compilation.json`), or None."""
    from .library import library_root
    path = library_root(_system(system)) / identity / 'compilation.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            return None
        data = json.loads(raw)
        if data.get('system') != system or data.get('game') != identity or not data.get('fresh_reference_passed'):
            return None
        return validate_record(data['record'], identity, system=system)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


# --- A conversion's use of the sharing (msx_conversion) --------------------------------------------------------

PATTERNS = 'native.patterns'      # every window the next generation translates (msx_build.learn)
RECEIVED = 'native.received'      # the windows of it that came from records, not from this player's own learning


def forget(work) -> None:
    """The work folder's windows are dropped (learned under another mapper): the received ones go with them."""
    for name in (PATTERNS, RECEIVED):
        (work / name).unlink(missing_ok=True)


def receive(system: str, identity: str, cartridge: bytes, work) -> dict:
    """Before learning: the windows of the qualified bank, the player's library record and the imported bank are added to the work
    folder's windows, so the first generation already translates them; the ones new to this build are noted as received. Returns
    what each source gave (the report's `knowledge.use`). A machine out of the sharing receives nothing."""
    if system not in SYSTEMS or system not in pp.SHARED_SYSTEMS:
        return {'shared': False}
    from . import knowledge
    found, info = shared_rows(identity, cartridge, system=system, qualified=knowledge.qualified_game(system, identity),
                              imported=knowledge.imported_game(system, identity), library=library_record(identity, system=system))
    patterns, received = work / PATTERNS, work / RECEIVED
    have = words(patterns.read_text(encoding='utf-8')) if patterns.is_file() else set()
    new = found - have
    if new:
        patterns.write_text(text_of(have | new), encoding='utf-8', newline='\n')
        noted = words(received.read_text(encoding='utf-8')) if received.is_file() else set()
        received.write_text(text_of(noted | new), encoding='utf-8', newline='\n')
    info['new_to_this_build'] = len(new)
    return info


def own_windows(work) -> set[bytes]:
    """The windows this player's own conversions learned in the work folder: all of them but the received ones."""
    patterns, received = work / PATTERNS, work / RECEIVED
    have = words(patterns.read_text(encoding='utf-8')) if patterns.is_file() else set()
    return have - (words(received.read_text(encoding='utf-8')) if received.is_file() else set())


def conclude(system: str, identity: str, cartridge: bytes, bios: bytes, work, use: dict, title: str) -> dict:
    """After every check passed: the record of this conversion's own windows (united with the library's), written into the game's summary
    in the player's library, and the report's `knowledge` section. `shared` says whether the machine is in the sharing at all, not that this
    conversion shared anything."""
    from .systems import get_profile
    block = {'machine_status': get_profile(system).status, 'shared': system in pp.SHARED_SYSTEMS, 'use': dict(use)}
    if system not in SYSTEMS or system not in pp.SHARED_SYSTEMS:
        return block
    from .library import atomic_json, library_root
    record, counts = promote(identity, cartridge, bios, own_windows(work), system=system, previous=library_record(identity, system=system))
    summary = library_root(system) / identity / 'compilation.json'
    summary.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(summary, {'schema': 1, 'title': title, 'system': system, 'game': identity, 'rom_sha256': identity,
                          'private_development_only': True, 'fresh_reference_passed': True, 'record': record, 'cores': engine(system),
                          'record_source': 'the windows this player\'s own conversions learned', 'record_counts': counts})
    return {**block, 'cores': engine(system), 'record_sha256': record_digest(record), 'paths': counts['paths'], 'promotion': counts,
            'source': 'the windows this player\'s own conversions learned, once every check passed',
            'received_are_not_shared_until_learned': True, 'raw_bytes_stored': False, 'fresh_validation_required': True}
