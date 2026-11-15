"""Numeric, ROM-free MSX2+ paths for one exact cartridge or disk set: no ROM byte, no disk byte, no RAM byte, no code.

The MSX2+ shares its paths as the experimental tier of the base (like the PC Engine and the CPS-1): a path is qualified only for the engine
revision (`cores`) that validated it, and the whole sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`). The MSX and
the MSX2 decline it (docs/MSX.md, section 7): their RAM code is BIOS hooks with no source in the cartridge. A disk game is different: it loads
its program from the disks into RAM, so most of what a conversion learns is found in the disks (Quinpl: 540 of 561 windows).

What is shared. The banked Z80 chain translates every instruction position of the cartridge and of the BIOS ahead of time; what a conversion
still learns is the code the program runs from RAM, as the Master System does: the four bytes at each address the interpreter ran
(`msx_build.learn`, `native.patterns`), which the next generation emits as native bodies guarded by those four bytes. A record holds, for each
such window whose bytes are found in the player's own images, its **offset** there: the `window4` shape the Master System shares as
`pattern_refs`, turned into offsets and back by the same helpers (`knowledge_build.window_offsets`, `window_words`).

* A cartridge game: offsets in the cartridge (source `rom`), keyed by its SHA-256.
* A disk game: offsets in one of its disks (sources `disk1` ... `diskN`, the role `disk`, each with its size and SHA-256), rows
  `[disk index, offset]` when there are several. The game key is the set's identity (`msx_disk.read_disks`): the one disk's SHA-256, or the
  SHA-256 of the disks' SHA-256 in order, so a reader checks it from the record alone. The BIOS source states the BIOS image the windows were
  found with; for a disk game it holds the player's disk ROM (at 10000h) and the FM BIOS.

A player with the same images reads the four bytes back from his own copies. A window runs native only where the bytes at the program counter
equal it, so a received window never changes what a game does: where it does not fit, the interpreter runs, counted.

What stays private, counted and never shared: windows whose bytes are not in the images (code the BIOS or the game builds in RAM), and the
windows received from other players until this player's own conversion learns them (the Master System's rule, `knowledge_build._sega_offered`).
A record is made only from the windows of a conversion that then passed every check (`msx_conversion`), never from the paths it received.

Only what is the MSX's is here: the record's identity, the engine pin, the machine's own rules (`RECORD_RULES`, `validate_record`), the
private filter and the use of the windows in a conversion. Comparing, uniting, keeping and gathering records is `path_records`, the one copy
every schema 3 machine can use. `msx2plus_knowledge` binds the MSX2+ (the interface `knowledge.schema3_module` reads).
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import re

from . import path_profiles as pp
from .knowledge_build import window_offsets, window_words
from .msx_disk import DISK_SIZES, MAX_DISKS, disk_set
from .path_records import PathRecords, record_digest

SYSTEMS = ('msx2plus',)
CPU = 'z80'
ROM = 'rom'
BIOS = 'bios'
DISK = 'disk'
SHAPE = 'window4'
KIND = 'msx_window'
# A path is qualified for the revision of the engine that consumed it. Raise this when our use of the windows changes in a way a path could notice.
GENERATOR_REVISION = 2            # 2: the MSX2+ and its disks (1.7.6)
ROW_LIMIT = 4096                  # the windows a game learns at most (msx_glue.inc: `learned[4096]`; the profiles' cap)
PATH_CAPS = {KIND: ROW_LIMIT}
DISK_NAME = re.compile(r'disk([1-9]|10)')

UnknownFormat = pp.UnknownFormat

# What `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`, so that
# `web/lib/paths3.php` follows the converter instead of a copy of its rules; the keys are gba_knowledge's, with `alternatives` for the two
# kinds of record): no layout; either the cartridge or the disks (each 360 or 720 KiB exactly, `sizes`), each hashed, and the BIOS image
# they were found with; the game id the cartridge's SHA-256, or the disk set's identity (`disk_set`); the windows point into the cartridge,
# the one disk (`src`) or every disk in order (`srcs`), nothing else. Their size,
# four bytes inside their source, and the ceiling are the profile's (`window4`).
RECORD_RULES = {
    'layout': [],
    'alternatives': [
        {'sources': {'only': [ROM, BIOS], 'required': [ROM, BIOS], 'hashed': True, 'game': ROM},
         'paths': {CPU: {'windows': {'src': ROM}}}},
        {'sources': {'only': [DISK, BIOS], 'required': [DISK, BIOS], 'hashed': True, 'game': 'disk_set',
                     'numbered': {DISK: [1, MAX_DISKS]}, 'sizes': {DISK: sorted(DISK_SIZES)}},
         'paths': {CPU: {'windows': {'src': DISK}}}},
    ],
    'disk_set': {'one': 'the sha256 of disk1',
                 'several': "sha256('msx-disk-set-v1' NUL disk1.sha256 NUL disk2.sha256 ...), lowercase hex, in disk order"},
}


def _system(system: str) -> str:
    if system not in SYSTEMS:
        raise ValueError(f'Not an MSX machine that shares its paths: {system!r}.')
    return system


def engine(system: str = 'msx2plus') -> str:
    """The `cores` string of the base for this converter: the Z80 generator's pin and the revision of our use of it, not our game stamp."""
    from .core import ENGINE_REV
    return hashlib.sha1(f'{_system(system)}:{GENERATOR_REVISION}:{ENGINE_REV}'.encode()).hexdigest()


def _images(media) -> tuple:
    """A cartridge (bytes) or a disk set (a sequence of images) as a tuple of images; `is_disks` tells which."""
    return (media,) if isinstance(media, (bytes, bytearray)) else tuple(media)


def is_disks(media) -> bool:
    return not isinstance(media, (bytes, bytearray))


def source_facts(media, bios: bytes) -> dict:
    """The sources of a cartridge (`rom`) or of a disk set (`disk1`...), and the BIOS image."""
    fact = lambda data: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    names = [f'{DISK}{n}' for n in range(1, len(_images(media)) + 1)] if is_disks(media) else [ROM]
    return {**{name: fact(data) for name, data in zip(names, _images(media))}, BIOS: fact(bios)}


def disk_names(sources: dict) -> list[str]:
    return sorted((name for name in sources if DISK_NAME.fullmatch(name)), key=lambda name: int(name[len(DISK):]))


def _assemble(system: str, identity: str, sources: dict, hints, core: str) -> dict:
    rows_in = sorted({tuple(row) for name, row in hints if name == KIND})
    if len(rows_in) > ROW_LIMIT:
        raise ValueError('An MSX record holds too many paths.')
    disks = disk_names(sources)
    if not rows_in:
        paths = {}
    elif len(disks) > 1:
        paths = {'windows': [pp._table_block(SHAPE, [list(row) for row in rows_in], 2, sources=disks)]}
    else:
        paths = {'windows': [pp._table_block(SHAPE, [[row[-1]] for row in rows_in], 1, disks[0] if disks else ROM)]}
    return {'schema': pp.SCHEMA, 'game': f'{system}:{identity}', 'identity': {'system': system, 'sources': sources, 'layout': {}},
            'cpus': {CPU: {'map': system, 'core': core, 'paths': paths}}, 'devices': {}}


def rows(record) -> list[tuple]:
    """The windows of a validated record: `(offset,)` in a cartridge, `(disk index, offset)` in a disk set (index 0 for the first disk)."""
    section = record['cpus'][CPU]
    profile = pp.PROFILES[(CPU, section['map'])]
    disks = bool(disk_names(record['identity']['sources']))
    out = []
    for block in section['paths'].get('windows', ()):
        width = 2 if 'srcs' in block else 1
        for row in pp.decode_table(block['table'], width, profile.caps[SHAPE]):
            out.append(tuple(row) if width == 2 else ((0, row[0]) if disks else (row[0],)))
    return out


def _hints(record) -> set:
    return {(KIND, row) for row in rows(record)}


def validate_record(record, identity: str | None = None, *, system: str = 'msx2plus') -> dict:
    """Strict numeric allowlist of one MSX2+ record (the schema 3 validator, then what is the MSX's own), or ValueError."""
    _system(system)
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(system + ':'):
            raise ValueError('Not a record of this MSX machine.')
        if identity is not None and record['game'] != f'{system}:{identity}':
            raise ValueError('MSX hints do not match their game.')
        sources = record['identity']['sources']
        disks = disk_names(sources)
        if record['identity']['layout'] != {} or BIOS not in sources or 'sha256' not in sources[BIOS]:
            raise ValueError('Invalid MSX layout.')
        if disks:
            if set(sources) != {BIOS, *disks} or disks != [f'{DISK}{n}' for n in range(1, len(disks) + 1)]:
                raise ValueError('An MSX disk record names its disks disk1 to diskN.')
            if any('sha256' not in sources[name] for name in disks):
                raise ValueError('An MSX disk record hashes every disk.')
            if any(sources[name]['bytes'] not in DISK_SIZES for name in disks):
                raise ValueError('An MSX disk is 360 or 720 KiB.')
            key = disk_set(sources[name]['sha256'] for name in disks)
        else:
            if set(sources) != {ROM, BIOS} or 'sha256' not in sources[ROM]:
                raise ValueError('Invalid MSX layout.')
            key = sources[ROM]['sha256']
        if record['game'] != f'{system}:{key}':
            raise ValueError('An MSX record is keyed by its cartridge or its disk set.')
        section = record['cpus'][CPU]
        if set(record['cpus']) != {CPU} or record['devices'] or section['map'] != system or set(section['paths']) - {'windows'}:
            raise ValueError('An MSX record lists its RAM windows only.')
        for block in section['paths'].get('windows', ()):
            named = block.get('srcs') or [block.get('src')]
            if block.get('shape') != SHAPE or named != (disks if len(disks) > 1 else disks or [ROM]):
                raise ValueError('An MSX window points into the wrong image.')
        if len(rows(record)) > ROW_LIMIT:
            raise ValueError('An MSX record holds too many paths.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid MSX record.') from error
    return record


def _image_sources(sources: dict) -> dict:
    """What says two records are about the same images: the cartridge or the disks, not the BIOS."""
    return {name: value for name, value in sources.items() if name != BIOS}


@lru_cache(maxsize=None)
def records(system: str = 'msx2plus') -> PathRecords:
    """The machine's records: the common handling (`path_records`) with the MSX's identity, engine, rules and rows."""
    return PathRecords(system=_system(system), cpu=CPU, primary=_image_sources, engine=lambda: engine(system),
                       validate_record=lambda record, identity=None: validate_record(record, identity, system=system),
                       assemble=lambda identity, sources, hints, core: _assemble(system, identity, sources, hints, core), hints=_hints)


def make_record(identity: str, media, bios: bytes, windows=(), *, system: str = 'msx2plus', core: str | None = None) -> dict:
    """The schema 3 document of a cartridge (`media` bytes, `windows` offsets or `(offset,)`) or of a disk set (`media` the images,
    `windows` `(disk index, offset)` pairs): the sizes and hashes of the images and of the BIOS, the engine, and the windows."""
    hints = {(KIND, tuple(row) if isinstance(row, (tuple, list)) else (row,)) for row in windows}
    return validate_record(_assemble(_system(system), identity, source_facts(media, bios), hints, core or engine(system)), identity,
                           system=system)


# The common handling, bound to the machine (the names `knowledge.schema3_module` reads).
def record_engine(record) -> str: return records().record_engine(record)
def entry_set(record) -> set: return records().entry_set(record)
def same_images(first: dict, second: dict) -> bool: return records().same_images(first, second)
def rebuild(skeleton: dict, hints, *, system: str = 'msx2plus', core: str | None = None) -> dict: return records(system).rebuild(skeleton, hints, core=core)
def merged(identity: str, first: dict, second: dict, *, system: str = 'msx2plus') -> dict: return records(system).merged(identity, first, second)
def salvaged_record(identity: str, record, *, system: str = 'msx2plus') -> dict | None: return records(system).salvaged_record(identity, record)
def library_record(identity: str, *, system: str = 'msx2plus') -> dict | None: return records(system).library_record(identity)


# --- Windows to paths and back: the MSX's private filter ------------------------------------------------------------

def words(text: str) -> set[bytes]:
    """The windows of a `native.patterns` text (eight hex digits a line); other lines are ignored."""
    out = set()
    for line in text.split():
        if len(line) == 8:
            try:
                out.add(bytes.fromhex(line))
            except ValueError:
                continue
    return out


def text_of(found) -> str:
    return ''.join(f'{word.hex().upper()}\n' for word in sorted(found))


def media_windows(media, own) -> tuple[list[tuple], int]:
    """The windows `own` as rows of `media`: `(offset,)` of their first place in a cartridge, or `(disk index, offset)` of their first place
    in the first disk holding them; and how many are in none of the images (they stay private)."""
    if not is_disks(media):
        offsets, private = window_offsets(media, own)
        return [(offset,) for offset in offsets], private
    left, out = set(own), set()
    for index, image in enumerate(_images(media)):
        found = {word: image.find(word) for word in left}
        out |= {(index, offset) for offset in found.values() if offset >= 0}
        left = {word for word, offset in found.items() if offset < 0}
    return sorted(out), len(left)


def promote(identity: str, media, bios: bytes, own, *, system: str = 'msx2plus', previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts): the windows this player's own conversions learned (`own`), as rows of the cartridge or the disks, united with the
    player's previous record of the same images and engine. Windows in none of the images stay private, counted."""
    found, private = media_windows(media, own)
    truncated = max(0, len(found) - ROW_LIMIT)
    record = make_record(identity, media, bios, found[:ROW_LIMIT], system=system)
    if previous:
        try:
            record = merged(identity, record, previous, system=system)
        except ValueError:
            pass                                    # the union is over the bound: this conversion's record alone
    return record, {'own_windows': len(set(own)), 'in_images': len(found), 'private_not_in_images': private, 'truncated': truncated,
                    'paths': len(rows(record))}


def shared_rows(identity: str, media, *, system: str = 'msx2plus', qualified=None, imported=None, library=None) -> tuple[set, dict]:
    """(windows, info): the windows of the qualified bank, the player's library record and the imported bank for these images, read from
    their bytes (`path_records.PathRecords.gathered_rows`). A record for images of another size or count is ignored with its reason."""
    images = _images(media)

    def expand(record):
        sources = record['identity']['sources']
        names = disk_names(sources) if is_disks(media) else [ROM]
        if len(names) != len(images) or any(sources.get(name, {}).get('bytes') != len(image) for name, image in zip(names, images)):
            raise ValueError('The record names images of another size.')
        out = set()
        for row in rows(record):
            index, offset = (row if len(row) == 2 else (0, row[0]))
            out |= window_words(images[index], [offset])
        return sorted(out), {}
    found, info = records(system).gathered_rows(identity, expand, qualified=qualified, imported=imported, library=library)
    return set(found), info


# --- A conversion's use of the sharing (msx_conversion) -----------------------------------------------------------

PATTERNS = 'native.patterns'      # every window the next generation translates (msx_build.learn)
RECEIVED = 'native.received'      # the windows of it that came from records, not from this player's own learning


def forget(work) -> None:
    """The work folder's windows are dropped (learned under another mapper): the received ones go with them."""
    for name in (PATTERNS, RECEIVED):
        (work / name).unlink(missing_ok=True)


def receive(system: str, identity: str, media, work) -> dict:
    """Before learning: the windows of the qualified bank, the player's library record and the imported bank are added to the work folder's
    windows, so the first generation already translates them; the ones new to this build are noted as received. Returns what each source
    gave (the report's `knowledge.use`). A machine out of the sharing receives nothing."""
    if system not in SYSTEMS or system not in pp.SHARED_SYSTEMS:
        return {'shared': False}
    from . import knowledge
    found, info = shared_rows(identity, media, system=system, qualified=knowledge.qualified_game(system, identity),
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


def conclude(system: str, identity: str, media, bios: bytes, work, use: dict, title: str) -> dict:
    """After every check passed: the record of this conversion's own windows (united with the library's), written into the game's summary
    in the player's library, and the report's `knowledge` section. `shared` says whether the machine is in the sharing at all, not that this
    conversion shared anything."""
    from .systems import get_profile
    block = {'machine_status': get_profile(system).status, 'shared': system in pp.SHARED_SYSTEMS, 'use': dict(use)}
    if system not in SYSTEMS or system not in pp.SHARED_SYSTEMS:
        return block
    record, counts = promote(identity, media, bios, own_windows(work), system=system, previous=library_record(identity, system=system))
    records(system).write_library_record(identity, record, title=title, record_source="the windows this player's own conversions learned",
                                         record_counts=counts)
    return {**block, 'cores': engine(system), 'record_sha256': record_digest(record), 'paths': counts['paths'], 'promotion': counts,
            'source': "the windows this player's own conversions learned, once every check passed",
            'received_are_not_shared_until_learned': True, 'raw_bytes_stored': False, 'fresh_validation_required': True}
