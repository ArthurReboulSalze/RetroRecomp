"""Numeric, ROM-free X68000 paths for one exact ordered disk set: no disk byte, no IPL byte, no RAM word, no code.

The X68000 is supported since 1.6.9 and shares its paths as the experimental tier of the base (like the CPS-1): a path is
qualified only for the engine revision (`cores`) that validated it, the record carries its own format number, and the whole
sharing can be withdrawn with one line (`path_profiles.EXPERIMENTAL_SHARED`).

What is shared. A game loads its program from the floppy into RAM and runs it there, so the instructions a conversion
observes are in RAM (and in the IPL ROM, which every game runs to boot). To share them, the bytes are turned into numbers
about the player's own images:

* RAM code that comes from the disks: the observed instructions of one run of consecutive addresses are searched, as one
  string of bytes, at an even offset of the ordered disk images (`disk`: the contents of the disks, one after the other).
  A run found there becomes one row `[address, offset, length]` of a `span`. Where each instruction of a span starts is not
  stored: it is decoded from the span's first words by the 68000 word-count table (`word_count`), and a span is made only
  when that decoding gives exactly the observed instructions.
* IPL code: the player's IPL (`ipl`, 128 KiB) is the same bytes whatever the game; an observed instruction there is a row
  `[address, offset, length]` of the IPL, valid only for an IPL with the SHA-256 the record states.

A player with the same disks rebuilds the bytes from the images they supplied and gets the same instructions. What cannot be
tied to an image (code unpacked, relocated or generated at run time, text VRAM, the SCSI ROM stub) **stays private**: it
is counted, never shared. A record is made only from the fresh reference runs of a conversion that then passed every check
(`promote`, `x68000_conversion`): never from feedback rows, never from the hints the conversion was offered.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import zlib

from . import path_profiles as pp
from .paths import ASSETS

SYSTEM = 'x68'
# Version of the record. It is `layout.format` of the schema 3 document. A reader skips (never refuses) a record of a format
# it does not know; a format that changes keeps a function here that reads the old one.
FORMAT = 1
FORMATS = (1,)
RAM_LIMIT = 0xc00000              # the 68000 address space below the text VRAM: RAM (up to 12 MiB), where disk code runs
IPL_BYTES = 128 * 1024
LONGEST_INSTRUCTION = 16          # eight words, the bound of `native.observations`
SPAN_LIMIT = 16384                # rows of the span block (the profile's cap)
IPL_LIMIT = 65536                 # rows of the IPL block (the profile's cap)
SPAN_BYTES = 4 << 20              # bytes the spans of a record may cover (`path_profiles.SPAN_BYTES`)
ANCHOR_BYTES = 8                  # a span of at least this many bytes is a place of the disks; a shorter one may be a coincidence of the data
DISK, IPL = 'disk', 'ipl'
# The ceiling of each kind of path, by the name `entry_set` gives it (the one form every schema 3 module exposes: the site's base builder reads it).
# The first counts span rows (their bytes are bounded too, SPAN_BYTES), the second IPL instruction rows.
PATH_CAPS = {'x68_span': SPAN_LIMIT, 'x68_ipl': IPL_LIMIT}

# --- The engine identity (`cores`) ---------------------------------------------------------------------------
#
# A path is qualified for the revision of the engine that consumed it. The core below is a 40-digit digest that moves
# whenever anything that decides what a RAM path becomes moves:
#   * the pins of the code the translation is built from (the Mega Drive recompiler's decoder and semantics, the Geolith
#     Musashi, the px68k base the machine is built on);
#   * the text of the native files that guard and run it (hashed here, line ends normalised);
#   * GENERATOR_REVISION, for the Python that generates it. Python sources cannot be hashed as text in a packaged executable
#     (and a bytecode hash differs between Python versions, which would split the players), so GENERATOR_SOURCES are pinned by
#     tests/test_x68_knowledge.py: editing one without raising the revision fails the test. Raise GENERATOR_REVISION whenever
#     the generator, the guards or the semantics change in a way a RAM path could notice. A new revision makes every qualified
#     path "waiting" again for it.
# 1: first revision (5 November 2026, the X68000 joins the base). The generator moved from tools/x68000_native.py into retrorecomp/m68k_observed.py on
# 5 November 2026 without changing a byte of what it writes (A/B of UPGRADES.md): the revision stays 1, the pins follow.
GENERATOR_REVISION = 1
NATIVE_INPUTS = ('native/x68000_native/CMakeLists.txt', 'native/x68000_native/decode.c', 'native/x68000_native/guard_checks.c',
                 'native/x68000_native/observe.c', 'native/x68000_native/observe.h')
GENERATOR_SOURCES = ('tools/x68000_native.py', 'tools/x68000_base74.py', 'retrorecomp/m68k_observed.py', 'retrorecomp/m68000.py', 'retrorecomp/m68000_state_rules.py',
                     'retrorecomp/megadrive_rules.py', 'retrorecomp/musashi_fixes.py', 'retrorecomp/neogeo_codegen.py')

# The number of words of an instruction from its first word, for the 65,536 first words: the table the pinned recompiler's decoder
# writes (`decode --lengths`, `tools/x68000_native.py`), deflated. It follows the pin of the decoder (the engine identity names
# it) and tests/test_x68_knowledge.py compares it, byte for byte, with the table of the decoder when a compiler is present.
_WORD_COUNTS = (
    'eNrt3duuwiAUANFsdv3/X/YSX6waW6lBYE18MRF1nNCjWI6lbCPXLJllB+/G50aWNafLJfc9h1fEnfX1Nc9CjzfudXzRX/8v'
    '+2Vl/9Rff/2n7t96vP7+/uvv+K+//jP234rxY75/0r/v/jXHz+td6G/+66+//vrr319//fTXT/8W/ml8Vf+lsv8R4/Xvu3/t'
    '+qn+5r/++uvv+K9/f/31018//Vv4W/+x/q+/7//1N//1119//fXXT3/99df/388/2PP4rfnF6xf666+//vrr3/jxj9q//6vv'
    'T/Qfbf5HV4ze3/wfo3/5sA/9cou4fW7OiNbP3/wf5/hfJvz/B/z58+fPnz9//vz58+fPn//m8xdibvjz58+fP3/+/Pnz58+f'
    'P38AAAAAAICZmH3/J3/+/Pnz58+fP3/+/Pnz58+f/4y/v6i//vrrr7/++uuvv/7666//eP0BAAAAAEA4/z+s/1j/019//fXX'
    'X3/99ddff/31119//fnz58+fP3/+/Pnz58+fP3/+/K3/6K+//vrrr7/++uuvv/7662//fzTdv8CfP3/+/Pnz58+fP3/+/Pnz'
    'BwAAAAAA/8wZzfxZkA=='
)


@lru_cache(maxsize=1)
def word_counts() -> bytes:
    data = zlib.decompress(base64.b64decode(''.join(_WORD_COUNTS)))
    if len(data) != 65536 or not all(1 <= n <= 8 for n in data):
        raise ValueError('Invalid MC68000 word-count table.')
    return data


def word_count(first_word: int) -> int:
    return word_counts()[first_word]


def text_digest(name: str, root: Path | None = None) -> str:
    """SHA-256 of a text file with CR LF read as LF (the checkout and the package differ only there)."""
    data = ((root or ASSETS) / name).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def engine_core() -> str:
    from .console16 import REPOSITORIES
    from .neogeo_build import GEOLITH_REV
    from tools.x68000_base74 import COMMIT
    native = hashlib.sha256(''.join(name + text_digest(name) for name in NATIVE_INPUTS).encode()).hexdigest()
    return hashlib.sha1(f'x68-m68k:{GENERATOR_REVISION}:{REPOSITORIES["md"][1]}:{GEOLITH_REV}:{COMMIT}:{native}'.encode()).hexdigest()


def engine() -> str:
    """The `cores` string of the base for this converter."""
    return engine_core()


def record_engine(record) -> str:
    """The `cores` string a record was built with ('' when it is not an X68000 record)."""
    try:
        return record['cpus']['m68k']['core']
    except (KeyError, TypeError):
        return ''


UnknownFormat = pp.UnknownFormat


# --- Images --------------------------------------------------------------------------------------------------

def disk_content(disks) -> bytes:
    """The ordered disks as the machine stores them, one after the other (`DiskImage.content`)."""
    from .x68000_media import identify_disk
    return b''.join(identify_disk(path).content() for path in disks)


def source_facts(disk: bytes, ipl: bytes | None = None) -> dict:
    facts = {DISK: {'bytes': len(disk), 'sha256': hashlib.sha256(disk).hexdigest()}}
    if ipl is not None:
        facts[IPL] = {'bytes': len(ipl), 'sha256': hashlib.sha256(ipl).hexdigest()}
    return facts


def _ipl_mapped(ipl: bytes | None) -> bytes | None:
    """The IPL as the machine maps it, or None when this IPL is not mapped as the file is (a SCSI boot marker)."""
    if ipl is None:
        return None
    from tools.x68000_native import ipl_view
    return ipl_view(ipl)


# --- Records (schema 3 documents) ----------------------------------------------------------------------------

def _blocks(span_rows, ipl_rows) -> dict:
    paths = {}
    if span_rows:
        paths['spans'] = [pp._table_block('span', span_rows, 3, DISK)]
    if ipl_rows:
        paths['ram_code'] = [pp._table_block('insn', ipl_rows, 3, IPL)]
    return paths


def _assemble(identity: str, sources: dict, span_rows, ipl_rows, core: str) -> dict:
    span_rows = sorted({tuple(row) for row in span_rows})
    ipl_rows = sorted({tuple(row) for row in ipl_rows})
    return {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{identity}',
            'identity': {'system': SYSTEM, 'sources': sources, 'layout': {'format': FORMAT}},
            'cpus': {'m68k': {'map': 'x68', 'core': core, 'paths': _blocks(span_rows, ipl_rows)}},
            'devices': {}}


def make_record(identity: str, disk: bytes, ipl: bytes | None, span_rows=(), ipl_rows=(), *, core: str | None = None) -> dict:
    """The schema 3 document of a disk set: its sources (sizes and hashes of the disks and of the IPL when it holds IPL rows),
    the engine, and the rows. Rows are `[address, offset, length]`; duplicates are removed and the order is the sorted one, so
    equal hints give equal documents."""
    facts = source_facts(disk, ipl if ipl_rows else None)
    return _assemble(identity, facts, span_rows, ipl_rows, core or engine())


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one X68000 record (the schema 3 validator, then what is the X68000's own), or ValueError
    (`UnknownFormat` for a format this converter cannot read)."""
    if (isinstance(record, dict) and isinstance(record.get('identity'), dict)
            and isinstance(record['identity'].get('layout'), dict)):
        version = record['identity']['layout'].get('format', 1)
        if type(version) is int and version not in FORMATS and 1 <= version <= 255:
            raise UnknownFormat('X68000 record of an unknown format.')
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not an X68000 record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('X68000 hints do not match their disk set identity.')
        sources = record['identity']['sources']
        if record['identity']['layout'] != {'format': FORMAT} or DISK not in sources or not set(sources) <= {DISK, IPL}:
            raise ValueError('Invalid X68000 layout.')
        if any('sha256' not in source for source in sources.values()):
            raise ValueError('An X68000 source states its SHA-256.')
        if IPL in sources and sources[IPL]['bytes'] != IPL_BYTES:
            raise ValueError('An X68000 IPL has 128 KiB.')
        if set(record['cpus']) != {'m68k'} or record['devices']:
            raise ValueError('An X68000 record lists its 68000 section.')
        paths = record['cpus']['m68k']['paths']
        if set(paths) - {'spans', 'ram_code'}:
            raise ValueError('An X68000 record holds RAM spans and IPL instructions only.')
        for kind, source in (('spans', DISK), ('ram_code', IPL)):
            for block in paths.get(kind, ()):
                if block.get('src') != source or (source == IPL and IPL not in sources):
                    raise ValueError('An X68000 block points into the wrong image.')
        spans, ipl_rows = rows(record)
        # Disk code runs in RAM and IPL code in the IPL window, nowhere else (the profile's windows also hold the other).
        if any(address + length > RAM_LIMIT for address, _, length in spans):
            raise ValueError('An X68000 span is outside the RAM.')
        if any(address < 0xfc0000 or address + length > 0xfffffe for address, _, length in ipl_rows):
            raise ValueError('An X68000 IPL row is outside the IPL window.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid X68000 record.') from error
    return record


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def rows(record) -> tuple[list, list]:
    """(span rows, IPL rows) of a validated record."""
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
        spans, ipl = rows(record)
    except (KeyError, TypeError, ValueError):
        return set()
    return {('x68_span', row) for row in spans} | {('x68_ipl', row) for row in ipl}


def same_images(first: dict, second: dict) -> bool:
    """Two records point into the very same disks (and have the same layout). The IPL is not part of this: a record names its IPL only when it holds IPL
    rows, so two players with the same disks and different IPLs hold records of the same game."""
    one, two = first['identity'], second['identity']
    return first['game'] == second['game'] and one['layout'] == two['layout'] and one['sources'].get(DISK) == two['sources'].get(DISK)


def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict:
    """A record of the skeleton's images holding exactly `hints` (as `entry_set` names them)."""
    spans = [row for name, row in hints if name == 'x68_span']
    ipl = [row for name, row in hints if name == 'x68_ipl']
    sources = skeleton['identity']['sources']
    if not ipl:
        sources = {name: value for name, value in sources.items() if name != IPL}
    return validate_record(_assemble(skeleton['game'].split(':', 1)[1], sources, spans, ipl,
                                     core or record_engine(skeleton)))


def merged(identity: str, first: dict, second: dict) -> dict:
    """Union of two records of one disk set. Records of another engine or other disks never mix: the one built by the current engine is
    kept, else the first. The disk paths are united; the IPL paths only when both records were made with the same IPL (a record keeps the IPL
    paths it has, the first's when both have some for different IPLs). ValueError when the union exceeds a bound."""
    if not second:
        return first
    if not first:
        return second
    if not same_images(first, second) or record_engine(first) != record_engine(second):
        current = engine()
        return second if record_engine(second) == current and record_engine(first) != current else first
    spans = set(rows(first)[0]) | set(rows(second)[0])
    ipl_first, ipl_second = rows(first)[1], rows(second)[1]
    facts_first, facts_second = first['identity']['sources'].get(IPL), second['identity']['sources'].get(IPL)
    if not ipl_first and ipl_second:
        chosen, ipl_rows = facts_second, ipl_second
    elif ipl_first and ipl_second and facts_first == facts_second:
        chosen, ipl_rows = facts_first, set(ipl_first) | set(ipl_second)
    else:
        chosen, ipl_rows = facts_first, ipl_first
    sources = {DISK: first['identity']['sources'][DISK], **({IPL: chosen} if ipl_rows and chosen else {})}
    return validate_record(_assemble(identity, sources, spans, ipl_rows if sources.get(IPL) else (), record_engine(first)))


def salvaged_record(identity: str, record) -> dict | None:
    """A received record, or None. A record is all or nothing: it is checked as a whole (its rows are numbers about images whose
    hashes it states, there is no row worth saving from a record that fails)."""
    try:
        return validate_record(record, identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# --- Observations to paths -----------------------------------------------------------------------------------

def _find_even(image: bytes, needle: bytes) -> int:
    at = image.find(needle)
    while at != -1 and at & 1:
        at = image.find(needle, at + 1)
    return at


def _instruction(words) -> bytes | None:
    """The bytes of an observed instruction when they are one complete instruction of the word-count table, else None."""
    if not isinstance(words, str) or len(words) % 4 or not 4 <= len(words) <= 2 * LONGEST_INSTRUCTION:
        return None
    try:
        raw = bytes.fromhex(words)
    except ValueError:
        return None
    return raw if len(raw) == 2 * word_count(raw[0] << 8 | raw[1]) else None


def _slot(window: bytes) -> int:
    return (int.from_bytes(window, 'big') * 2654435761 >> 8) & 0xffffff


class _Image:
    """The ordered disks and a cheap way to know that a string is NOT in them: an instruction that no even offset of the disks begins is private,
    and finding that out by a search of the whole image costs milliseconds each (a game that unpacks its code has tens of thousands). Two tables
    built once: the 16-bit words found at even offsets, and a bit per 4-byte window at even offsets (hashed, so a hit may be a false alarm and is then
    searched; a miss is certain). The answer for one instruction is kept, many addresses carry the same bytes."""

    def __init__(self, data: bytes):
        self.data = data
        self.words = words = bytearray(65536)
        self.quads = quads = bytearray(1 << 24)
        for at in range(0, len(data) - 1, 2):
            words[data[at] << 8 | data[at + 1]] = 1
        for at in range(0, len(data) - 3, 2):
            quads[_slot(data[at:at + 4])] = 1
        self.kept: dict = {}

    def may_contain(self, raw: bytes) -> bool:
        if not self.words[raw[0] << 8 | raw[1]]:
            return False
        return len(raw) < 4 or bool(self.quads[_slot(raw[:4])])

    def find(self, raw: bytes) -> int:
        """The first even offset of `raw` in the disks, -1 when there is none (the same answer is not searched twice)."""
        if raw not in self.kept:
            self.kept[raw] = _find_even(self.data, raw) if self.may_contain(raw) else -1
        return self.kept[raw]

    def find_run(self, blob: bytes) -> int:
        return _find_even(self.data, blob) if self.may_contain(blob) else -1


def _longest(image: _Image, raws: list, start: int) -> tuple[int, int]:
    """(how many instructions from `start` on begin a string found in the image, where), (0, -1) when not even the first does."""
    if image.find(raws[start]) < 0:
        return 0, -1
    count = len(raws) - start
    at = image.find_run(b''.join(raws[start:]))
    if at >= 0:
        return count, at
    low, high, best = 1, count - 1, (1, image.find(raws[start]))
    while low <= high:
        middle = (low + high) // 2
        at = image.find_run(b''.join(raws[start:start + middle]))
        if at >= 0:
            best, low = (middle, at), middle + 1
        else:
            high = middle - 1
    return best


def translate(disk: bytes, ipl: bytes | None, variants, spans) -> tuple[list, list, dict]:
    """Paths for the observations of the fresh reference runs that sit in the player's own images.

    `variants` are the observed `{'pc', 'words'}` rows and `spans` the IPL spans of the observation file (`schema` 2). Returns the
    sorted span rows (disk), the sorted IPL rows and the counts: observed, tied to an image (a ceiling) and anchored (in a long enough span), kept
    private (and why). Nothing but numbers is returned."""
    from tools.x68000_native import IPL_CODE_END, IPL_SPANS
    ram, other, malformed = {}, 0, 0
    for row in variants:
        pc = row.get('pc') if isinstance(row, dict) else None
        raw = _instruction(row.get('words')) if isinstance(row, dict) else None
        if type(pc) is not int or pc & 1 or raw is None:
            malformed += 1
        elif 0 <= pc and pc + len(raw) <= RAM_LIMIT:
            ram.setdefault(pc, set()).add(raw)
        else:
            other += 1
    # Runs of consecutive addresses: the next instruction starts where the last one ends.
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
    ipl_rows, ipl_seen, ipl_private = [], 0, 0
    view = _ipl_mapped(ipl)
    for span in spans or ():
        if not isinstance(span, dict) or span.get('source') != IPL:
            continue
        address, offset, length = span.get('address'), span.get('offset'), span.get('length')
        for entry in span.get('entries', ()):
            ipl_seen += 1
            position, words = entry
            size = words * 2
            if (view is None or (address, offset, length) not in IPL_SPANS or span.get('sha256') != hashlib.sha256(ipl).hexdigest()
                    or address + position + size > IPL_CODE_END or (offset + position) % IPL_BYTES + size > IPL_BYTES):
                ipl_private += 1
                continue
            ipl_rows.append((address + position, (offset + position) % IPL_BYTES, size))
    span_rows, ipl_rows = sorted(set(span_rows)), sorted(set(ipl_rows))
    # `tied` is a ceiling: an instruction counts when its bytes sit at an even offset of the disks, and a short one (two bytes) sits somewhere by chance;
    # `anchored` counts only those in a span of at least ANCHOR_BYTES bytes, the instructions that really come from the disks. Both are shared.
    counts = {'ram': {'observed': sum(len(v) for v in ram.values()), 'tied': tied, 'anchored': anchored, 'private': private, 'spans': len(span_rows)},
              'other_windows': {'observed': other, 'tied': 0, 'private': other},
              'malformed': malformed,
              'ipl': {'observed': ipl_seen, 'tied': len(ipl_rows), 'private': ipl_private}}
    return span_rows, ipl_rows, counts


def promote(identity: str, disk: bytes, ipl: bytes | None, variants, spans, *, previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts) from the fresh reference runs of a verified conversion. `previous` is the library's record of these very
    disks and engine; its disk paths are kept (and its IPL paths when the IPL is the same). The record holds no disk byte, no
    IPL byte, no RAM word and no code. The limits bound each block (`counts['truncated']`)."""
    span_rows, ipl_rows, counts = translate(disk, ipl, variants, spans)
    if previous and not isinstance(previous, dict):
        previous = None
    base = make_record(identity, disk, ipl, span_rows, ipl_rows)
    if previous:
        try:
            validate_record(previous, identity)
            facts = source_facts(disk)
            if previous['identity']['sources'][DISK] == facts[DISK] and record_engine(previous) == engine():
                held_spans, held_ipl = rows(previous)
                span_rows = sorted(set(span_rows) | set(held_spans))
                if ipl is not None and previous['identity']['sources'].get(IPL) == source_facts(disk, ipl)[IPL]:
                    ipl_rows = sorted(set(ipl_rows) | set(held_ipl))
        except ValueError:
            pass
    covered = 0
    kept = []
    for row in span_rows:
        covered += row[2]
        if covered > SPAN_BYTES or len(kept) >= SPAN_LIMIT:
            break
        kept.append(row)
    counts['truncated'] = len(kept) < len(span_rows) or len(ipl_rows) > IPL_LIMIT
    record = make_record(identity, disk, ipl, kept, ipl_rows[:IPL_LIMIT])
    validate_record(record, identity)
    counts['paths'] = {'ram_spans': len(rows(record)[0]), 'ipl': len(rows(record)[1])}
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


def expanded_rows(record: dict, disk: bytes, ipl: bytes | None) -> tuple[list, dict]:
    """Observation rows `(pc, words)` rebuilt from the player's own images, in the form the generator reads, and what was left out.
    ValueError when the record is not for exactly these disks. The IPL rows are used only for the very IPL the record states.
    Local build input; it never leaves the process."""
    validate_record(record)
    sources = record['identity']['sources']
    if sources[DISK] != source_facts(disk)[DISK]:
        raise ValueError('X68000 hints are for other disks.')
    spans, ipl_rows = rows(record)
    out, left = [], {}
    for address, offset, length in spans:
        out += _instructions_of_span(disk[offset:offset + length], address)
    if ipl_rows:
        view = _ipl_mapped(ipl)
        if ipl is None or sources.get(IPL) != source_facts(disk, ipl).get(IPL):
            left['ipl'] = 'another IPL'
        elif view is None:
            left['ipl'] = 'an IPL that is not mapped as the file is'
        else:
            out += [(address, bytes(view[offset:offset + length]).hex()) for address, offset, length in ipl_rows]
    return out, left


def shared_rows(identity: str, disk: bytes, ipl: bytes | None, *, qualified=None, imported=None, library=None) -> tuple[list, dict]:
    """(rows, info): the guidance of the shared and library records for this disk set, expanded from its images.

    Three sources, counted apart: the qualified bank (used only for the engine that qualified it), the player's own library
    record, and the imported bank (other players' paths, whatever their engine, which guide discovery and are rechecked like
    everything else). The rows are build input only: they are never added to the private observations a conversion keeps.
    `info` says what each gave and what was ignored and why."""
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
            expanded, left = expanded_rows(record, disk, ipl)
        except UnknownFormat:
            info['ignored'][name] = 'unknown record format'
            continue
        except ValueError as error:
            info['ignored'][name] = str(error)[:120]
            continue
        if left:
            info['ignored'][name + '_ipl'] = left['ipl']
        info[name] = len(expanded)
        rows_out += expanded
    return rows_out, info


# --- The player's library ------------------------------------------------------------------------------------

def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that fresh, verified conversions reached (`x68000_conversion` writes it into the
    game's summary, `<library>/x68/<game>/compilation.json`), or None."""
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
