"""Numeric, ROM-free CPS-1 paths for one exact romset: no ROM byte, no RAM word, no code.

CPS-1 is an experimental machine in development, and its paths are shared as such: a path is qualified only for
the engine revision (`cores`) that validated it, the record carries its own format number, and the whole
sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

What is shared. The 68000 program ROM and the Z80 sound ROM are translated whole, so the only paths a CPS-1
game has are the instructions it ran from RAM (68000 work RAM at 0xFF0000, Z80 sound RAM at 0xD000): code the
game copied there, or code it built. The reference runs of a conversion see all of it. To share one, its
bytes are turned into numbers about the player's own ROM images, exactly as Neo Geo does
(`neogeo_codegen.generate`, `neogeo_knowledge.numeric_record`):

* 68000: the bytes of the instruction alone (its length comes from the generator's own decoder, so the
  neighbouring words of the observed window, which are other data, are left out) are searched at an even offset of
  the assembled program image: row `[address, offset, length]`.
* Z80: the instruction's structural bytes (`megadrive_z80.opcode_key`: opcodes and prefixes, never operands) are
  searched at any offset of the assembled sound image: row `[address, offset, 4, mask]`.

A player with the same romset rebuilds the bytes from the ROMs they supplied and gets the same instructions.
An observation whose bytes are not in those images (code unpacked or generated at run time, or run from
graphics RAM as Street Fighter II' Champion Edition does, which the translator does not cover yet) cannot be tied
to a ROM and **stays private**: it is counted, never shared.

Promotion. A record is made only from the fresh reference runs of a conversion that then passed every check
(`promote`, `cps1_conversion`): never from feedback rows, never from the hints the conversion was offered.

Feedback kind 14 (a ROM instruction the native code did not cover) is recorded by the game and read by nobody
on purpose: the program ROM is swept whole, so a ROM position that is interpreted is one the decoder rejects,
and no path can change that. It is diagnostic only; it is never shared or promoted. Kinds 15 and 16 (work-RAM and
sound-RAM code met while playing) are the player's private build hints; they are not persisted.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from . import path_profiles as pp
from .paths import ASSETS

SYSTEM = 'cps1'
# Version of the record. It is `layout.format` of the schema 3 document. A reader skips (never refuses) a
# record of a format it does not know; a format that changes keeps a function here that reads the old one.
FORMAT = 1
FORMATS = (1,)
RAM_BASE = 0xff0000
RAM_BYTES = 0x10000
Z80_RAM = (0xd000, 0xd800)
ROW_LIMIT = 4096                  # the profiles' cap, and the generator's own bound on observed RAM variants
LONGEST_INSTRUCTION = 10          # 68000: five words

# --- The engine identity (`cores`) ---------------------------------------------------------------------------
#
# A path is qualified for the revision of the engine that consumed it. The two section cores below are
# 40-digit digests that move whenever anything that decides what a RAM path becomes moves:
#   * the pins of the code the translation is built from (the Mega Drive recompiler's semantics and decoder,
#     the Geolith 68000 and Z80 cores);
#   * the text of the native files that guard and run it (hashed here, line ends normalised);
#   * GENERATOR_REVISION, for the Python that generates it. Python sources cannot be hashed as text in a packaged
#     executable (and a bytecode hash differs between Python versions, which would split the players), so
#     GENERATOR_SOURCES are pinned by tests/test_cps1_knowledge.py: editing one without raising the revision
#     fails the test. Raise GENERATOR_REVISION whenever the generator, the guards or the semantics change in a
#     way a RAM path could notice. A new revision makes every qualified path "waiting" again for it.
GENERATOR_REVISION = 1
# native/md_prefetch.inc is the source of the generated cps1_arithmetic.c (cps1_codegen._semantics cuts the
# multiply/divide timing out of it), so it decides what a RAM path becomes like the CPS-1 files do.
NATIVE_INPUTS = ('native/cps1_native.c', 'native/cps1_native.h', 'native/cps1_z80_native.h',
                 'native/cps1_machine.c', 'native/cps1_machine.h', 'native/md_prefetch.inc')
GENERATOR_SOURCES = ('retrorecomp/cps1_codegen.py', 'retrorecomp/cps1_build.py', 'retrorecomp/m68000.py',
                     'retrorecomp/neogeo_codegen.py', 'retrorecomp/neogeo_z80.py', 'retrorecomp/megadrive_z80.py')


def text_digest(name: str, root: Path | None = None) -> str:
    """SHA-256 of a text file with CR LF read as LF (the checkout and the package differ only there)."""
    data = ((root or ASSETS) / name).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def engine_parts() -> tuple[str, str]:
    """(68000 section core, Z80 section core)."""
    from .console16 import REPOSITORIES
    from .neogeo_build import GEOLITH_REV
    native = hashlib.sha256(''.join(name + text_digest(name) for name in NATIVE_INPUTS).encode()).hexdigest()
    return (hashlib.sha1(f'cps1-m68k:{GENERATOR_REVISION}:{REPOSITORIES["md"][1]}:{GEOLITH_REV}:{native}'.encode()).hexdigest(),
            hashlib.sha1(f'cps1-z80:{GENERATOR_REVISION}:{GEOLITH_REV}:{native}'.encode()).hexdigest())


def engine() -> str:
    """The `cores` string of the base for this converter: both section cores, joined."""
    return ':'.join(engine_parts())


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not a CPS-1 record)."""
    try:
        cpus = record['cpus']
        return f"{cpus['m68k']['core']}:{cpus['z80']['core']}"
    except (KeyError, TypeError):
        return ''


UnknownFormat = pp.UnknownFormat


# --- Images --------------------------------------------------------------------------------------------------

def images_from_board(board: Path, game: dict) -> dict:
    """The program and sound images of an assembled board folder (`cps1_board.write_board`)."""
    from .cps1_codegen import program_size
    return {'maincpu': (Path(board) / 'maincpu.bin').read_bytes()[:program_size(game)],
            'audiocpu': (Path(board) / 'audiocpu.bin').read_bytes()}


def source_facts(images: dict) -> dict:
    return {name: {'bytes': len(images[name]), 'sha256': hashlib.sha256(images[name]).hexdigest()}
            for name in ('maincpu', 'audiocpu')}


# --- Records (schema 3 documents) ----------------------------------------------------------------------------

def _catalogue_revision() -> str:
    from . import cps1_catalogue
    return cps1_catalogue.MAME_REVISION


def make_record(identity: str, images: dict, ram_rows=(), z80_rows=(), *, cores: tuple | None = None) -> dict:
    """The schema 3 document of a romset: its sources (sizes and hashes of the two images), the engine, and the
    rows. Rows are `[address, offset, length]` (68000) and `[address, offset, 4, mask]` (Z80); duplicates are
    removed and the order is the sorted one, so equal hints give equal documents."""
    m68k_core, z80_core = cores or engine_parts()
    ram_rows = sorted({tuple(row) for row in ram_rows})
    z80_rows = sorted({tuple(row) for row in z80_rows})
    m68k_paths, z80_paths = {}, {}
    if ram_rows:
        m68k_paths['ram_code'] = [pp._table_block('insn', ram_rows, 3, 'maincpu')]
    if z80_rows:
        z80_paths['ram_code'] = [pp._table_block('insn_masked', z80_rows, 4, 'audiocpu')]
    return {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{identity}',
            'identity': {'system': SYSTEM, 'sources': source_facts(images),
                         'layout': {'catalogue': _catalogue_revision(), 'format': FORMAT}},
            'cpus': {'m68k': {'map': 'cps1', 'core': m68k_core, 'paths': m68k_paths},
                     'z80': {'map': 'cps1-sound', 'core': z80_core, 'paths': z80_paths}},
            'devices': {}}


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one CPS-1 record (the schema 3 validator, then what is CPS-1's own), or
    ValueError (`UnknownFormat` for a format this converter cannot read)."""
    if (isinstance(record, dict) and isinstance(record.get('identity'), dict)
            and isinstance(record['identity'].get('layout'), dict)):
        version = record['identity']['layout'].get('format', 1)
        if type(version) is int and version not in FORMATS and 1 <= version <= 255:
            raise UnknownFormat('CPS-1 record of an unknown format.')
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not a CPS-1 record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('CPS-1 hints do not match their romset identity.')
        layout = record['identity']['layout']
        if set(layout) != {'catalogue', 'format'} or layout['format'] not in FORMATS:
            raise ValueError('Invalid CPS-1 layout.')
        if set(record['cpus']) != {'m68k', 'z80'} or record['devices']:
            raise ValueError('A CPS-1 record lists its 68000 and Z80 sections.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid CPS-1 record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def rows(record) -> tuple[list, list]:
    """(68000 rows, Z80 rows) of a validated record."""
    out = {'m68k': [], 'z80': []}
    for cpu, section in record['cpus'].items():
        profile = pp.PROFILES[(cpu, section['map'])]
        for block in section['paths'].get('ram_code', []):
            width = len(pp.SHAPES[block['shape']][1])
            out[cpu] += [tuple(row) for row in pp.decode_table(block['table'], width, profile.caps[block['shape']])]
    return out['m68k'], out['z80']


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players)."""
    if not isinstance(record, dict):
        return set()
    try:
        ram, z80 = rows(record)
    except (KeyError, TypeError, ValueError):
        return set()
    return {('m68k_ram', row) for row in ram} | {('z80_ram', row) for row in z80}


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same images: same sources, same layout, same machine."""
    return (first['game'] == second['game'] and first['identity'] == second['identity'])


def rebuild(skeleton: dict, hints, *, cores: tuple | None = None) -> dict:
    """A record of the skeleton's images holding exactly `hints` (as `entry_set` names them)."""
    ram = [row for name, row in hints if name == 'm68k_ram']
    z80 = [row for name, row in hints if name == 'z80_ram']
    out = {**skeleton, 'cpus': {cpu: dict(section, paths={}) for cpu, section in skeleton['cpus'].items()}}
    if ram:
        out['cpus']['m68k']['paths'] = {'ram_code': [pp._table_block('insn', sorted(ram), 3, 'maincpu')]}
    if z80:
        out['cpus']['z80']['paths'] = {'ram_code': [pp._table_block('insn_masked', sorted(z80), 4, 'audiocpu')]}
    return validate_record(out)


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one romset. Records of another engine or other images never mix: the one built
    by the current engine is kept, else the first. ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    return rebuild(first, entry_set(first) | entry_set(second))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None. A record is all or nothing: it is checked as a whole (its rows are numbers
    about images whose hashes it states, there is no row worth saving from a record that fails)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- Observations to paths -----------------------------------------------------------------------------------

def _ram_window(row):
    if not isinstance(row, dict):
        return None
    offset, words = row.get('offset'), row.get('words')
    if (type(offset) is not int or not 0 <= offset < RAM_BYTES or offset & 1 or not isinstance(words, str)
            or len(words) % 4 or not re.fullmatch(r'[0-9a-fA-F]{4,32}', words)):
        return None
    data = bytes.fromhex(words)
    return (offset, data) if offset + len(data) <= RAM_BYTES else None


def _find_even(image: bytes, needle: bytes) -> int:
    position = image.find(needle)
    while position >= 0 and position & 1:
        position = image.find(needle, position + 1)
    return position


def _z80_pattern(mask: int, normal: bytes) -> re.Pattern:
    return re.compile(b''.join(re.escape(normal[n:n + 1]) if mask >> n & 1 else b'.' for n in range(4)), re.DOTALL)


def translate(images: dict, fresh: dict, lengths) -> tuple[list, list, dict]:
    """Paths for the observations of the fresh reference runs that sit in the game's own images.

    `fresh` holds {'m68k_ram': [{'offset', 'words'}], 'z80_ram': [{'address', 'bytes'}]}. `lengths(windows)`
    answers {(offset, data): byte length of the first instruction or None} (the generator's decoder:
    `cps1_codegen.ram_instruction_lengths`). Returns the sorted 68000 and Z80 rows and the counts: observed (valid
    shape, duplicates removed), tied to a ROM offset, kept private (and why). Nothing but numbers is returned."""
    from .megadrive_z80 import opcode_key
    windows = []
    for row in fresh.get('m68k_ram', ()):
        item = _ram_window(row)
        if item is not None and item not in windows:
            windows.append(item)
    sizes = lengths(windows) if windows else {}
    ram_rows, untranslatable, not_in_rom = set(), 0, 0
    for offset, data in windows:
        length = sizes.get((offset, data))
        if not length or length & 1 or not 2 <= length <= 16 or offset + length > RAM_BYTES:
            untranslatable += 1
            continue
        position = _find_even(images['maincpu'], data[:length])
        if position < 0:
            not_in_rom += 1
            continue
        ram_rows.add((RAM_BASE + offset, position, length))
    z80_rows, z80_seen, z80_untied, z80_odd = set(), set(), 0, 0
    for row in fresh.get('z80_ram', ()):
        address, raw = (row.get('address'), row.get('bytes')) if isinstance(row, dict) else (None, None)
        if (type(address) is not int or not Z80_RAM[0] <= address < Z80_RAM[1] or not isinstance(raw, str)
                or not re.fullmatch('[0-9a-fA-F]{8}', raw)):
            continue
        item = (address, bytes.fromhex(raw))
        if item in z80_seen:
            continue
        z80_seen.add(item)
        key = opcode_key(item[1])
        if key is None:
            z80_odd += 1
            continue
        match = _z80_pattern(*key).search(images['audiocpu'])
        if match is None:
            z80_untied += 1
            continue
        z80_rows.add((address, match.start(), 4, key[0]))
    counts = {'m68k_ram': {'observed': len(windows), 'tied': len(ram_rows),
                           'private': untranslatable + not_in_rom,
                           'untranslatable': untranslatable, 'not_in_program_rom': not_in_rom},
              'z80_ram': {'observed': len(z80_seen), 'tied': len(z80_rows), 'private': z80_odd + z80_untied,
                          'untranslatable': z80_odd, 'not_in_sound_rom': z80_untied}}
    return sorted(ram_rows), sorted(z80_rows), counts


def promote(identity: str, images: dict, fresh: dict, lengths, *, previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts) from the fresh reference runs of a verified conversion. `previous` is the library's
    record of these very images and engine; its paths are kept. The record holds no ROM byte, no RAM word and
    no code. ROW_LIMIT bounds each CPU (`counts['truncated']`)."""
    ram, z80, counts = translate(images, fresh, lengths)
    if previous and not isinstance(previous, dict):
        previous = None
    base = make_record(identity, images)
    if previous:
        try:
            validate_record(previous, identity)
            if same_images(previous, base) and record_engine(previous) == engine():
                held_ram, held_z80 = rows(previous)
                ram, z80 = sorted(set(ram) | set(held_ram)), sorted(set(z80) | set(held_z80))
        except ValueError:
            pass
    counts['truncated'] = len(ram) > ROW_LIMIT or len(z80) > ROW_LIMIT
    record = make_record(identity, images, ram[:ROW_LIMIT], z80[:ROW_LIMIT])
    validate_record(record, identity)
    counts['paths'] = {'m68k_ram': len(rows(record)[0]), 'z80_ram': len(rows(record)[1])}
    counts['raw_ram_words_stored'] = False
    return record, counts


# --- Paths to observations -----------------------------------------------------------------------------------

def expanded_rows(record: dict, images: dict) -> dict:
    """Observation rows rebuilt from the player's own images, in the form `cps1_codegen` reads. ValueError when
    the record is not for exactly these images. Local build input; it never leaves the process."""
    validate_record(record)
    if record['identity']['sources'] != source_facts(images):
        raise ValueError('CPS-1 hints are for other images.')
    ram, z80 = rows(record)
    return {'m68k_ram': [{'offset': address - RAM_BASE, 'words': images['maincpu'][offset:offset + length].hex()}
                         for address, offset, length in ram],
            'z80_ram': [{'address': address, 'bytes': images['audiocpu'][offset:offset + 4].hex()}
                        for address, offset, _, _ in z80]}


def shared_rows(identity: str, images: dict, *, qualified=None, imported=None, library=None) -> tuple[dict, dict]:
    """(rows, info): the guidance of the shared and library records for this romset, expanded from its images.

    Three sources, counted apart: the qualified bank (used only for the engine that qualified it), the player's
    own library record, and the imported bank (other players' paths, whatever their engine, which guide discovery
    and are rechecked like everything else). The rows are build input only: they are never added to the
    private observations a conversion keeps. `info` says what each gave and what was ignored and why."""
    rows_out = {'m68k_ram': [], 'z80_ram': []}
    info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
    current = engine()
    for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
        if not record:
            continue
        try:
            if name == 'qualified' and record_engine(record) != current:
                info['ignored'][name] = 'another engine revision'
                continue
            expanded = expanded_rows(record, images)
        except UnknownFormat:
            info['ignored'][name] = 'unknown record format'
            continue
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        info[name] = len(expanded['m68k_ram']) + len(expanded['z80_ram'])
        for key in rows_out:
            rows_out[key] += expanded[key]
    return rows_out, info


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that fresh, verified conversions reached (`cps1_conversion` writes
    it into the library's compilation.json), or None."""
    from .library import library_root
    path = library_root(SYSTEM) / identity / 'compilation.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            return None
        data = json.loads(raw)
        if data.get('system') != SYSTEM or data.get('source_identity') != identity or not data.get('fresh_reference_passed'):
            return None
        return validate_record(data['record'], identity)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
