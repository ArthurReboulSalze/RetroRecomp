"""Numeric, ROM-free Atari ST paths for one exact game: no disk byte, no TOS byte, no RAM word, no code.

The Atari ST shares its paths as the experimental tier of the base (like the X68000, the CPS-1 and the PC Engine): a path is qualified only for the
engine revision (`cores`) that validated it, the record carries its own format number, and the whole sharing can be withdrawn with one line
(`path_profiles.EXPERIMENTAL_SHARED`).

What is shared. A game loads its program from the floppy into RAM and runs it there, and every game runs the TOS from its ROM, so the instructions
a conversion observes sit in the player's own images. They are turned into numbers about those images:

* TOS code: an instruction at `address` of the 192 KiB TOS (`tos`, at 0xFC0000) is a row `[address, offset, length]` of that image, valid only for a TOS with the
  SHA-256 the record states (EmuTOS 1.4 or the player's own TOS 1.0x).
* RAM code that comes from the disks: the observed instructions of one run of consecutive addresses are searched, as one string of bytes, at an even offset of
  the logical content of the disks (`disk`: the standard-format sectors of every image, in (cylinder, side, sector) order, one disk after the other:
  `atarist_disk.logical_content`). A run found there becomes one row `[address, offset, length]` of a `span`; where each instruction of a span starts is
  decoded from its first words by the 68000 word-count table, and a span is made only when that decoding gives exactly the observed instructions.

A player with the same disks and TOS rebuilds the bytes from the images they supplied and gets the same instructions. What cannot be tied to an image stays
**private**: code a loader relocates or unpacks, a track in a custom format (the sectors of those tracks are not in the content), an STX image (not read), the
cartridge area (Hatari's own code for the GEMDOS hook of the desktop). It is counted, never shared. A record is made only from the fresh reference runs of a
conversion that then passed every check (`promote`, `atarist_conversion`): never from received paths, never from the player's own record of a real session.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import path_profiles as pp
# The tie helpers of the X68000's record (the same 68000, the same search of an instruction string in an image): a second user of them, not a copy.
# They move to a shared module the next time the X68000's module moves.
from .x68_knowledge import _Image, _instruction, _longest, text_digest, word_count

SYSTEM = 'atarist'
# Version of the record. `path_profiles`, which every console's game stamp hashes, is not edited for it (as for the PC Engine and the CPS-2): `identity.layout` is empty and the
# version travels with the engine revision (`cores`), which GENERATOR_REVISION raises whenever the shape changes; a record of a shape this reader does not know fails its
# validation and is set aside by the bank, never the rest of the bank.
FORMAT = 1
DISK, TOS = 'disk', 'tos'
TOS_BASE = 0xFC0000
TOS_BYTES = 192 * 1024
RAM_LIMIT = 0x400000              # the ST's RAM (up to 4 MiB): where disk code runs
LONGEST_INSTRUCTION = 16          # eight words, the bound of the observations
SPAN_LIMIT = 16384                # rows of the span block (the profile's cap)
TOS_LIMIT = 65536                 # rows of the TOS block (the profile's cap)
SPAN_BYTES = 4 << 20              # bytes the spans of a record may cover (`path_profiles.SPAN_BYTES`)
ANCHOR_BYTES = 8                  # a span of at least this many bytes is a place of the disks; a shorter one may be a coincidence of the data
# The ceiling of each kind of path, by the name `entry_set` gives it (the form every schema 3 module exposes: the site's base builder reads it).
PATH_CAPS = {'atarist_span': SPAN_LIMIT, 'atarist_tos': TOS_LIMIT}

# --- The engine identity (`cores`) ---------------------------------------------------------------------------
#
# A path is qualified for the revision of the engine that consumed it: the pin of Hatari (whose handlers every native step calls), the text of the native files
# that guard and run the steps (hashed here, line ends normalised) and GENERATOR_REVISION, for the Python that generates them. Python sources cannot be hashed as
# text in a packaged executable, so GENERATOR_SOURCES are pinned by tests/test_atarist_knowledge.py: editing one without raising the revision fails the test.
# Raise GENERATOR_REVISION whenever the generator, the guards or the handlers change in a way a path could notice; every qualified path is then "waiting" again.
# 1: first revision (14 November 2026, the Atari ST joins the base).
GENERATOR_REVISION = 1
NATIVE_INPUTS = ('native/atarist_machine/CMakeLists.txt', 'native/atarist_machine/atarist_player.c', 'native/atarist_machine/atarist_session.c',
                 'native/atarist_machine/atarist_session.h')
GENERATOR_SOURCES = ('retrorecomp/atarist_codegen.py', 'retrorecomp/atarist_hatari.py')

UnknownFormat = pp.UnknownFormat


def engine_core() -> str:
    from .atarist_hatari import HATARI_REV
    native = hashlib.sha256(''.join(name + text_digest(name) for name in NATIVE_INPUTS).encode()).hexdigest()
    return hashlib.sha1(f'atarist-m68k:{GENERATOR_REVISION}:{HATARI_REV}:{native}'.encode()).hexdigest()


def engine() -> str:
    """The `cores` string of the base for this converter."""
    return engine_core()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not an Atari ST record)."""
    try:
        return record['cpus']['m68k']['core']
    except (KeyError, TypeError):
        return ''


# --- Images --------------------------------------------------------------------------------------------------

def disk_content(blobs) -> bytes:
    """The ordered disks' standard sectors, one disk after the other (`atarist_disk.logical_content`). `blobs` are (extension, bytes) pairs."""
    from .atarist_disk import logical_content
    return b''.join(logical_content(data, extension) for extension, data in blobs)


def source_facts(disk: bytes | None, tos: bytes | None) -> dict:
    facts = {}
    if disk:
        facts[DISK] = {'bytes': len(disk), 'sha256': hashlib.sha256(disk).hexdigest()}
    if tos:
        facts[TOS] = {'bytes': len(tos), 'sha256': hashlib.sha256(tos).hexdigest()}
    return facts


# --- Records (schema 3 documents) ----------------------------------------------------------------------------

def _blocks(span_rows, tos_rows) -> dict:
    paths = {}
    if span_rows:
        paths['spans'] = [pp._table_block('span', span_rows, 3, DISK)]
    if tos_rows:
        paths['ram_code'] = [pp._table_block('insn', tos_rows, 3, TOS)]
    return paths


def _assemble(identity: str, sources: dict, span_rows, tos_rows, core: str) -> dict:
    span_rows = sorted({tuple(row) for row in span_rows})
    tos_rows = sorted({tuple(row) for row in tos_rows})
    return {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{identity}',
            'identity': {'system': SYSTEM, 'sources': sources, 'layout': {}},
            'cpus': {'m68k': {'map': SYSTEM, 'core': core, 'paths': _blocks(span_rows, tos_rows)}},
            'devices': {}}


def make_record(identity: str, disk: bytes | None, tos: bytes | None, span_rows=(), tos_rows=(), *, core: str | None = None) -> dict:
    """The schema 3 document of a game: its sources (the size and hash of the disks' content when it holds spans, of the TOS when it holds TOS rows), the engine and
    the rows `[address, offset, length]`. Duplicates are removed and the order is the sorted one, so equal hints give equal documents."""
    facts = source_facts(disk if span_rows else None, tos if tos_rows else None)
    return _assemble(identity, facts, span_rows, tos_rows, core or engine())


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one Atari ST record (the schema 3 validator, then what is the ST's own), or ValueError."""
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not an Atari ST record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('Atari ST hints do not match their game identity.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {} or not sources or not set(sources) <= {DISK, TOS}:
            raise ValueError('Invalid Atari ST layout.')
        if any('sha256' not in source for source in sources.values()):
            raise ValueError('An Atari ST source states its SHA-256.')
        if TOS in sources and sources[TOS]['bytes'] != TOS_BYTES:
            raise ValueError('An Atari ST TOS image has 192 KiB.')
        if set(record['cpus']) != {'m68k'} or record['devices']:
            raise ValueError('An Atari ST record lists its 68000 section.')
        paths = record['cpus']['m68k']['paths']
        if set(paths) - {'spans', 'ram_code'}:
            raise ValueError('An Atari ST record holds disk spans and TOS instructions only.')
        for kind, source in (('spans', DISK), ('ram_code', TOS)):
            for block in paths.get(kind, ()):
                if block.get('src') != source or source not in sources:
                    raise ValueError('An Atari ST block points into the wrong image.')
        spans, tos_rows = rows(record)
        if any(address + length > RAM_LIMIT for address, _, length in spans):
            raise ValueError('An Atari ST span is outside the RAM.')
        if any(address < TOS_BASE or address + length > TOS_BASE + TOS_BYTES or offset != address - TOS_BASE for address, offset, length in tos_rows):
            raise ValueError('An Atari ST TOS row is not at its place of the TOS.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid Atari ST record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def rows(record) -> tuple[list, list]:
    """(span rows, TOS rows) of a validated record."""
    out = {'spans': [], 'ram_code': []}
    section = record['cpus']['m68k']
    profile = pp.PROFILES[('m68k', section['map'])]
    for kind in out:
        for block in section['paths'].get(kind, []):
            width = len(pp.SHAPES[block['shape']][1])
            out[kind] += [tuple(row) for row in pp.decode_table(block['table'], width, profile.caps[block['shape']])]
    return out['spans'], out['ram_code']


def entry_set(record) -> set:
    """Every path of a record as comparable tuples (what the base compares between players)."""
    if not isinstance(record, dict):
        return set()
    try:
        spans, tos_rows = rows(record)
    except (KeyError, TypeError, ValueError):
        return set()
    return {('atarist_span', row) for row in spans} | {('atarist_tos', row) for row in tos_rows}


def same_images(first: dict, second: dict) -> bool:
    """Two records of one game whose disk spans point into the very same content (and that have the same layout). The TOS is not part of this: a record names its TOS only
    when it holds TOS rows, so two players with the same disks and other TOSes hold records of the same game."""
    one, two = first['identity'], second['identity']
    return first['game'] == second['game'] and one['layout'] == two['layout'] and one['sources'].get(DISK) == two['sources'].get(DISK)


def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict:
    """A record of the skeleton's images holding exactly `hints` (as `entry_set` names them)."""
    spans = [row for name, row in hints if name == 'atarist_span']
    tos_rows = [row for name, row in hints if name == 'atarist_tos']
    sources = {name: value for name, value in skeleton['identity']['sources'].items() if (name == DISK and spans) or (name == TOS and tos_rows)}
    return validate_record(_assemble(skeleton['game'].split(':', 1)[1], sources, spans, tos_rows, core or record_engine(skeleton)))


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one game. Records of other disks or another engine never mix: the one built by the current engine is kept, else the first. The disk spans
    are united (when both name the same content); the TOS rows only when both were made with the same TOS (a record keeps the TOS rows it has, the first's when both
    have some for different TOSes). ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    spans_first, tos_first = rows(first)
    spans_second, tos_second = rows(second)
    disk_first, disk_second = first['identity']['sources'].get(DISK), second['identity']['sources'].get(DISK)
    if spans_first and spans_second and disk_first != disk_second:
        return first
    spans = set(spans_first) | set(spans_second)
    disk = disk_first or disk_second
    tos_facts_first, tos_facts_second = first['identity']['sources'].get(TOS), second['identity']['sources'].get(TOS)
    if not tos_first and tos_second:
        tos_facts, tos_rows = tos_facts_second, tos_second
    elif tos_first and tos_second and tos_facts_first == tos_facts_second:
        tos_facts, tos_rows = tos_facts_first, set(tos_first) | set(tos_second)
    else:
        tos_facts, tos_rows = tos_facts_first, tos_first
    sources = {**({DISK: disk} if spans and disk else {}), **({TOS: tos_facts} if tos_rows and tos_facts else {})}
    return validate_record(_assemble(identity, sources, spans if sources.get(DISK) else (), tos_rows if sources.get(TOS) else (), record_engine(first)))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None. A record is all or nothing: it is checked as a whole (its rows are numbers about images whose hashes it states, there is no row worth
    saving from a record that fails)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- Observations to paths -----------------------------------------------------------------------------------

def translate(disk: bytes, tos: bytes, variants) -> tuple[list, list, dict]:
    """Paths for the observations of the fresh reference runs that sit in the player's own images.

    `variants` are the observed `(pc, words)` rows (`words` a hex string). Returns the sorted span rows (disk), the sorted TOS rows and the counts: observed, tied to an
    image (a ceiling) and anchored (in a long enough span), kept private (and why). Nothing but numbers is returned."""
    ram, tos_seen, tos_rows, tos_private, cartridge, malformed = {}, 0, [], 0, 0, 0
    for pc, words in variants:
        raw = _instruction(words)
        if type(pc) is not int or pc & 1 or raw is None:
            malformed += 1
        elif pc + len(raw) <= RAM_LIMIT:
            ram.setdefault(pc, set()).add(raw)
        elif pc >= TOS_BASE:
            tos_seen += 1
            offset = pc - TOS_BASE
            if tos and pc + len(raw) <= TOS_BASE + len(tos) and tos[offset:offset + len(raw)] == raw:
                tos_rows.append((pc, offset, len(raw)))
            else:
                tos_private += 1
        else:
            cartridge += 1
    span_rows, tied, anchored, private, run = [], 0, 0, 0, []
    image = _Image(disk)

    def close():
        nonlocal tied, anchored, private
        raws = [raw for _, raw in run]
        start = 0
        while start < len(run):
            count, at = _longest(image, raws, start)
            if not count:
                private += 1
                start += 1
                continue
            length = sum(len(raw) for raw in raws[start:start + count])
            span_rows.append((run[start][0], at, length))
            tied += count
            anchored += count if length >= ANCHOR_BYTES else 0
            start += count
        run.clear()

    for pc, raw in sorted((pc, raw) for pc, raws in ram.items() for raw in raws):
        if run and pc == run[-1][0] + len(run[-1][1]):
            run.append((pc, raw))
        else:
            close()
            run.append((pc, raw))
    close()
    span_rows, tos_rows = sorted(set(span_rows)), sorted(set(tos_rows))
    # `tied` is a ceiling: an instruction counts when its bytes sit at an even offset of the disks, and a short one (two bytes) sits somewhere by chance; `anchored`
    # counts only those in a span of at least ANCHOR_BYTES bytes, the instructions that really come from the disks. Both are shared.
    counts = {'ram': {'observed': sum(len(v) for v in ram.values()), 'tied': tied, 'anchored': anchored, 'private': private, 'spans': len(span_rows)},
              'tos': {'observed': tos_seen, 'tied': len(tos_rows), 'private': tos_private},
              'cartridge_area': {'observed': cartridge, 'tied': 0, 'private': cartridge},
              'malformed': malformed}
    return span_rows, tos_rows, counts


def promote(identity: str, disk: bytes, tos: bytes, variants, *, previous: dict | None = None) -> tuple[dict | None, dict]:
    """(record, counts) from the fresh reference runs of a verified conversion; the record is None when nothing at all is tied. `previous` is the library's record of this game
    and engine; its disk spans are kept when the content is the same (and its TOS rows when the TOS is the same). The record holds no disk byte, no TOS byte, no RAM word and
    no code. The limits bound each block (`counts['truncated']`)."""
    span_rows, tos_rows, counts = translate(disk, tos, variants)
    if previous and isinstance(previous, dict):
        try:
            validate_record(previous, identity)
            facts = source_facts(disk, tos)
            if record_engine(previous) == engine():
                held_spans, held_tos = rows(previous)
                held = previous['identity']['sources']
                if held.get(DISK) == facts.get(DISK):
                    span_rows = sorted(set(span_rows) | set(held_spans))
                if held.get(TOS) == facts.get(TOS):
                    tos_rows = sorted(set(tos_rows) | set(held_tos))
        except ValueError:
            pass
    covered, kept = 0, []
    for row in span_rows:
        covered += row[2]
        if covered > SPAN_BYTES or len(kept) >= SPAN_LIMIT:
            break
        kept.append(row)
    counts['truncated'] = len(kept) < len(span_rows) or len(tos_rows) > TOS_LIMIT
    if not kept and not tos_rows:
        counts['paths'] = {'disk_spans': 0, 'tos': 0}
        counts['raw_words_stored'] = False
        return None, counts
    record = make_record(identity, disk, tos, kept, tos_rows[:TOS_LIMIT])
    validate_record(record, identity)
    counts['paths'] = {'disk_spans': len(rows(record)[0]), 'tos': len(rows(record)[1])}
    counts['raw_words_stored'] = False
    return record, counts


# --- Paths to observations -----------------------------------------------------------------------------------

def _instructions_of_span(data: bytes, address: int) -> list[tuple[int, str]]:
    """The (pc, words) of the instructions of a span's bytes, decoded from its first word; ValueError when the last one overruns."""
    out, position = [], 0
    while position < len(data):
        if position + 2 > len(data):
            raise ValueError('A span ends inside an instruction.')
        size = 2 * word_count(data[position] << 8 | data[position + 1])
        if size > LONGEST_INSTRUCTION or position + size > len(data):
            raise ValueError('A span ends inside an instruction.')
        out.append((address + position, data[position:position + size].hex()))
        position += size
    return out


def expanded_rows(record: dict, disk: bytes | None, tos: bytes | None) -> tuple[list, dict]:
    """Instruction rows `(pc, words)` rebuilt from the player's own images, in the form the generator reads, and what was left out. ValueError when the record's disk spans
    are for other disks. The TOS rows are used only for the very TOS the record states. Local build input; it never leaves the process."""
    validate_record(record)
    sources = record['identity']['sources']
    spans, tos_rows = rows(record)
    out, left = [], {}
    if spans:
        if not disk or sources[DISK] != source_facts(disk, None)[DISK]:
            raise ValueError('Atari ST hints are for other disks.')
        for address, offset, length in spans:
            out += _instructions_of_span(disk[offset:offset + length], address)
    if tos_rows:
        if not tos or sources.get(TOS) != source_facts(None, tos).get(TOS):
            left['tos'] = 'another TOS'
        else:
            out += [(address, tos[offset:offset + length].hex()) for address, offset, length in tos_rows]
    return out, left


def shared_rows(disk: bytes | None, tos: bytes, *, qualified=None, imported=None, library=None) -> tuple[list, dict]:
    """(rows, info): the guidance of the shared and library records for this game, expanded from its images.

    Three sources, counted apart: the qualified bank (used only for the engine that qualified it), the player's own library record, and the imported bank (other
    players' paths, whatever their engine, which guide the generation and are rechecked like everything else: a native step is guarded by the opcode the CPU has
    latched). The rows are build input only: they are never added to the private observations a conversion keeps. `info` says what each gave and what was ignored
    and why."""
    rows_out = []
    info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
    current = engine()
    for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
        if not record:
            continue
        try:
            if name == 'qualified' and record_engine(record) != current:
                info['ignored'][name] = 'another engine revision'
                continue
            expanded, left = expanded_rows(record, disk, tos)
        except UnknownFormat:
            info['ignored'][name] = 'unknown record format'
            continue
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        if left:
            info['ignored'][name + '_tos'] = left['tos']
        info[name] = len(expanded)
        rows_out += expanded
    return rows_out, info


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record of a game: the paths that fresh, verified conversions reached (`atarist_conversion` writes it into the summary of the game's TOS folder,
    `<library>/atarist/<game>/tos-<key>/compilation.json`), the records of the TOS folders united, or None."""
    from .library import library_root
    folder = library_root(SYSTEM) / identity
    found = None
    try:
        summaries = sorted(folder.glob('tos-*/compilation.json'))
    except OSError:
        return None
    for path in summaries:
        try:
            with path.open('rb') as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                continue
            data = json.loads(raw)
            if data.get('system') != SYSTEM or data.get('game') != identity or not data.get('fresh_reference_passed') or 'record' not in data:
                continue
            record = validate_record(data['record'], identity)
            found = merged(identity, found, record) if found else record
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return found
