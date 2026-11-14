"""Numeric, disc-free shared paths of a PlayStation game: no disc byte, no BIOS byte, no RAM word, no code.

The PlayStation shares its paths as the experimental tier of the base (Arthur, 14 November 2026: « Oui, elle partage »): a path is
qualified only for the engine revision (`cores`) that validated it, and the whole sharing can be withdrawn with one line
(`path_profiles.EXPERIMENTAL_SHARED`).

What a conversion learns is the R3000A code its routes ran, as (physical address, word) pairs (`psx_native`). A game loads its code from
its disc into RAM (the boot executable, overlays, code in its own archives), so most of those words are found, as they are, in the
player's own disc: a run of consecutive observed addresses whose words are found as one string of bytes at a 4-aligned place of a disc's
data becomes one row `[address, offset, length]` of a `span`. The offset counts the disc's user data from the start of its ISO 9660
volume (sector times 2,048 plus the place in the sector), so the same row reads the same bytes in every container of the same dump (an
EBOOT, a CUE/BIN): a player rebuilds the words from his own disc. Code that runs from the BIOS ROM, or that the BIOS copies into low RAM
(its kernel), is a row `[address, offset, 4]` of the BIOS image, valid only for a BIOS with the SHA-256 the record states.

The search keeps to what a game reads: the files of the disc's ISO 9660 volume but its movies and CD audio, the boot executable first.
A file is copied into RAM as a whole, so the difference between a RAM address and its disc offset is the same for every run of that file:
a few runs are searched in the files, every other run of the same file is placed by that difference and checked word for word. The
number of searches is bounded; a run neither placed nor found stays private.

What stays private, counted and never shared: words in neither the disc nor the BIOS (code a game decompresses or builds in RAM), runs
the bounded search did not reach, and the words received from other players until this player's own conversion observes them. A record
is made only from the observations of a conversion that then passed every check (`psx_conversion`), never from runtime hints or from
the paths it received. Received words become native steps like observed ones: each step's guard is the word the CPU fetches, so a
received word that does not fit runs on the interpreter, counted, and never changes what the game does.

Only what is the PlayStation's is here: the record's identity, the engine pin, the machine's rules (`RECORD_RULES`, `validate_record`),
the private filter and the use of the paths in a conversion. Comparing, uniting, keeping and gathering records is `path_records`.
"""
from __future__ import annotations

import bisect
from functools import lru_cache
import hashlib
import re

from . import path_profiles as pp
from .path_records import PathRecords, record_digest

SYSTEM = 'psx'
CPU = 'r3000a'
MAP = 'psx'
DISC = 'disc'
BIOS = 'bios'
SPAN_PATH = 'psx_span'
BIOS_PATH = 'psx_bios'
# A path is qualified for the revision of the engine that consumed it. Raise this when our use of the rows changes in a way a path could
# notice. 1: the PlayStation joins the base (14 November 2026).
GENERATOR_REVISION = 1
RAM_LIMIT = 0x200000
BIOS_BASE, BIOS_BYTES = 0x1FC00000, 0x80000
USER = 2048
MAX_DISCS = 8
MAX_VARIANTS = 4                       # the words kept per address (psx_native.MAX_VARIANTS)
# Files never searched: movies (STR), CD-XA and CD audio, which hold no code; and how much of one disc is read for the search.
SKIPPED_EXTENSIONS = ('.STR', '.XA', '.DA', '.MOV', '.PSS', '.AV')
SEARCH_BYTES = 256 << 20
FIND_MIN_WORDS = 4                     # a run searched on its own is at least this long (shorter runs are placed by a known difference)
FIND_BUDGET = 512                      # searches of one disc at most
FIND_MISSES = 64                       # consecutive searches that find nothing end the search of a disc
DISC_NAME = re.compile(r'disc([1-8])')
UnknownFormat = pp.UnknownFormat
_CAPS = pp.PROFILES[(CPU, MAP)].caps
PATH_CAPS = {SPAN_PATH: _CAPS['span'], BIOS_PATH: _CAPS['insn']}

# What `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`):
# no layout; the discs `disc1` to `discN` (N from 1 to 8), each hashed (its digest: psx_disc.Disc.digest, the raw sectors of the dump),
# and the player's BIOS (512 KiB, hashed) only with BIOS rows; the game id is `disc_set` of the discs' digests; spans point into the one
# disc (`src`) or into the discs in order (`srcs`, rows led by the disc's index) and lie in main RAM; BIOS rows are single instructions (4 bytes) in main RAM (the kernel the BIOS copies) or in the BIOS window.
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [DISC, BIOS], 'required': [DISC], 'hashed': True, 'game': 'disc_set',
                'numbered': {DISC: [1, MAX_DISCS]}, 'sizes': {BIOS: [BIOS_BYTES]}},
    'paths': {CPU: {'spans': {'src': DISC, 'window': [0, RAM_LIMIT]},
                    'ram_code': {'src': BIOS, 'windows': [[0, RAM_LIMIT], [BIOS_BASE, BIOS_BASE + BIOS_BYTES]], 'length': 4,
                                 'requires': BIOS}}},
    'disc_set': "sha256('rr-psx-game' NUL disc1.sha256 NUL disc2.sha256 NUL ...), lowercase hex, in disc order, a NUL after each",
}


def engine() -> str:
    """The `cores` string of the base for this converter: the machine's pin and the revision of our use of the paths, not our game stamp."""
    from .psx_beetle import BEETLE_REV
    return hashlib.sha1(f'{SYSTEM}:{GENERATOR_REVISION}:{BEETLE_REV}'.encode()).hexdigest()


def disc_names(sources: dict) -> list[str]:
    return sorted((name for name in sources if DISC_NAME.fullmatch(name)), key=lambda name: int(name[len(DISC):]))


def source_facts(digests, sizes, bios: bytes | None = None) -> dict:
    """The discs (`disc1`...: the user-data bytes of the data track, and the disc's digest) and, with BIOS rows, the BIOS image."""
    facts = {f'{DISC}{n}': {'bytes': size, 'sha256': digest} for n, (digest, size) in enumerate(zip(digests, sizes), start=1)}
    if bios is not None:
        facts[BIOS] = {'bytes': len(bios), 'sha256': hashlib.sha256(bios).hexdigest()}
    return facts


def _assemble(identity: str, sources: dict, hints, core: str) -> dict:
    spans = sorted({tuple(row) for name, row in hints if name == SPAN_PATH})
    bios_rows = sorted({tuple(row) for name, row in hints if name == BIOS_PATH})
    discs = disc_names(sources)
    paths = {}
    if spans and len(discs) > 1:
        paths['spans'] = [pp._table_block('span', [list(row) for row in spans], 4, sources=discs)]
    elif spans:
        paths['spans'] = [pp._table_block('span', [[a, o, n] for _, a, o, n in spans], 3, discs[0])]
    if bios_rows:
        paths['ram_code'] = [pp._table_block('insn', [list(row) for row in bios_rows], 3, BIOS)]
    return {'schema': pp.SCHEMA, 'game': f'{SYSTEM}:{identity}', 'identity': {'system': SYSTEM, 'sources': sources, 'layout': {}},
            'cpus': {CPU: {'map': MAP, 'core': core, 'paths': paths}}, 'devices': {}}


def rows(record) -> tuple[list, list]:
    """(spans `(disc index, address, offset, length)`, BIOS rows `(address, offset, 4)`) of a validated record."""
    section = record['cpus'][CPU]
    discs = disc_names(record['identity']['sources'])
    spans, bios_rows = [], []
    for block in section['paths'].get('spans', ()):
        if 'srcs' in block:
            spans += [tuple(row) for row in pp.decode_table(block['table'], 4, _CAPS['span'])]
        else:
            index = discs.index(block['src'])
            spans += [(index, *row) for row in pp.decode_table(block['table'], 3, _CAPS['span'])]
    for block in section['paths'].get('ram_code', ()):
        bios_rows += [tuple(row) for row in pp.decode_table(block['table'], 3, _CAPS['insn'])]
    return spans, bios_rows


def _hints(record) -> set:
    spans, bios_rows = rows(record)
    return {(SPAN_PATH, row) for row in spans} | {(BIOS_PATH, row) for row in bios_rows}


def validate_record(record, identity: str | None = None) -> dict:
    """Strict numeric allowlist of one PlayStation record (the schema 3 validator, then what is the PlayStation's own), or ValueError."""
    from .psx import game_key
    try:
        pp.validate_game(record)
        if not isinstance(record, dict) or not record['game'].startswith(SYSTEM + ':'):
            raise ValueError('Not a PlayStation record.')
        if identity is not None and record['game'] != f'{SYSTEM}:{identity}':
            raise ValueError('PlayStation hints do not match their game.')
        sources = record['identity']['sources']
        discs = disc_names(sources)
        if record['identity']['layout'] != {} or not discs or set(sources) - {BIOS, *discs}:
            raise ValueError('Invalid PlayStation layout.')
        if discs != [f'{DISC}{n}' for n in range(1, len(discs) + 1)]:
            raise ValueError('A PlayStation record names its discs disc1 to discN.')
        if any('sha256' not in source for source in sources.values()):
            raise ValueError('A PlayStation source states its SHA-256.')
        if BIOS in sources and sources[BIOS]['bytes'] != BIOS_BYTES:
            raise ValueError('A PlayStation BIOS is 512 KiB.')
        if record['game'] != f'{SYSTEM}:{game_key(sources[name]["sha256"] for name in discs)}':
            raise ValueError('A PlayStation record is keyed by its discs.')
        section = record['cpus'][CPU]
        if set(record['cpus']) != {CPU} or record['devices'] or section['map'] != MAP or set(section['paths']) - {'spans', 'ram_code'}:
            raise ValueError('A PlayStation record holds disc spans and BIOS instructions only.')
        for block in section['paths'].get('spans', ()):
            named = block.get('srcs') or [block.get('src')]
            if block.get('shape') != 'span' or named != (discs if len(discs) > 1 else discs[:1]):
                raise ValueError('A PlayStation span points into the wrong image.')
        for block in section['paths'].get('ram_code', ()):
            if block.get('shape') != 'insn' or block.get('src') != BIOS or BIOS not in sources:
                raise ValueError('A PlayStation BIOS row points into the wrong image.')
        spans, bios_rows = rows(record)
        if any(address + length > RAM_LIMIT for _, address, _, length in spans):
            raise ValueError('A PlayStation span is outside main RAM.')
        if any(length != 4 or not (address + 4 <= RAM_LIMIT or BIOS_BASE <= address < BIOS_BASE + BIOS_BYTES)
               for address, _, length in bios_rows):
            raise ValueError('A PlayStation BIOS row is not one instruction of RAM or of the BIOS.')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid PlayStation record.') from error
    return record


def _image_sources(sources: dict) -> dict:
    """What says two records are about the same images: the discs, not the BIOS."""
    return {name: value for name, value in sources.items() if name != BIOS}


@lru_cache(maxsize=None)
def records() -> PathRecords:
    """The machine's records: the common handling (`path_records`) with the PlayStation's identity, engine, rules and rows."""
    return PathRecords(system=SYSTEM, cpu=CPU, primary=_image_sources, engine=engine, validate_record=validate_record,
                       assemble=_assemble, hints=_hints)


def make_record(identity: str, digests, sizes, bios: bytes | None, spans=(), bios_rows=(), *, core: str | None = None) -> dict:
    """The schema 3 document of a game: its discs (and the BIOS when it holds BIOS rows), the engine, and the rows."""
    hints = {(SPAN_PATH, tuple(row)) for row in spans} | {(BIOS_PATH, tuple(row)) for row in bios_rows}
    sources = source_facts(digests, sizes, bios if bios_rows else None)
    return validate_record(_assemble(identity, sources, hints, core or engine()), identity)


# The common handling, bound to the machine (the names `knowledge.schema3_module` reads).
def record_engine(record) -> str: return records().record_engine(record)
def entry_set(record) -> set: return records().entry_set(record)
def same_images(first: dict, second: dict) -> bool: return records().same_images(first, second)
def rebuild(skeleton: dict, hints, *, core: str | None = None) -> dict: return records().rebuild(skeleton, hints, core=core)
def merged(identity: str, first: dict, second: dict) -> dict: return records().merged(identity, first, second)
def salvaged_record(identity: str, record) -> dict | None: return records().salvaged_record(identity, record)
def library_record(identity: str) -> dict | None: return records().library_record(identity)


# --- The player's own disc and BIOS ---------------------------------------------------------------------------------------

class DiscData:
    """One disc's user data as the rows count it (offsets from the start of its ISO 9660 volume), read by sector when asked."""

    def __init__(self, path, index: int):
        from . import psx_disc
        self.disc = psx_disc.open_disc(path, index)
        track = self.disc.data_track()
        self.base, self.size = track.start, track.length * USER
        self._sector, self._data = -1, b''

    def close(self):
        self.disc.close()

    def read(self, offset: int, length: int) -> bytes:
        out = bytearray()
        while length > 0:
            sector, inside = divmod(offset, USER)
            if sector != self._sector:
                self._sector, self._data = sector, self.disc.user(self.base + sector)
            take = min(length, USER - inside)
            out += self._data[inside:inside + take]
            offset += take
            length -= take
        return bytes(out)


class DiscFiles:
    """The files of one disc that the search reads (all but movies and CD audio, the boot executable first, up to SEARCH_BYTES), kept
    in one buffer with where each lies on the disc."""

    def __init__(self, data: DiscData):
        from . import psx_disc
        iso = psx_disc.Iso9660(data.disc)
        boot = None
        try:
            cnf = iso.find('SYSTEM.CNF')
            path = psx_disc.boot_path(psx_disc.parse_system_cnf(iso.read(cnf))) if cnf else None
            boot = iso.find(path.split(':', 1)[-1]) if path else None
        except (psx_disc.DiscError, ValueError):
            boot = None
        files, stack, seen = [], [(iso.root, 0)], set()
        while stack:
            entry, depth = stack.pop()
            try:
                children = iso.listdir(entry)
            except (psx_disc.DiscError, ValueError, IndexError):
                continue
            for child in children:
                if child.lba in seen:
                    continue
                seen.add(child.lba)
                if child.directory:
                    if depth < 8:
                        stack.append((child, depth + 1))
                elif child.size and not child.name.upper().endswith(SKIPPED_EXTENSIONS):
                    files.append(child)
        files.sort(key=lambda e: (boot is None or e.lba != boot.lba, e.lba))
        self.blob = bytearray()
        self.segments = []                      # (disc offset, blob start, length), by disc offset
        for entry in files:
            length = min(entry.size, data.size - entry.lba * USER)
            if length <= 0 or len(self.blob) + length > SEARCH_BYTES:
                continue
            start = len(self.blob)
            self.blob += data.read(entry.lba * USER, length)
            self.blob += bytes(-len(self.blob) % 4)
            self.segments.append((entry.lba * USER, start, length))
        self.segments.sort()
        self._starts = [segment[0] for segment in self.segments]
        self._in_blob = sorted((blob, n) for n, (_, blob, _) in enumerate(self.segments))
        self._blob_starts = [blob for blob, _ in self._in_blob]

    def at(self, offset: int, length: int) -> bytes:
        """The bytes at a disc offset when they lie inside one searched file, else b''."""
        n = bisect.bisect_right(self._starts, offset) - 1
        if n < 0:
            return b''
        start, blob, size = self.segments[n]
        if offset + length > start + size:
            length = start + size - offset
        return bytes(self.blob[blob + offset - start:blob + offset - start + length]) if length > 0 else b''

    def find(self, needle: bytes) -> int:
        """The disc offset of the first 4-aligned place of `needle` in the searched files, -1 when there is none."""
        at = self.blob.find(needle)
        while at != -1:
            start, blob, size = self.segments[self._in_blob[bisect.bisect_right(self._blob_starts, at) - 1][1]]
            if not (at - blob) % 4 and at + len(needle) <= blob + size:
                return start + at - blob
            at = self.blob.find(needle, at + 1)
        return -1


def _ranked(pairs) -> dict:
    """The words kept per executable address, most run first (the native steps' rule, `psx_native.plan`)."""
    found: dict = {}
    for (address, word), seen in pairs.items():
        if not address & 3 and (address < RAM_LIMIT or BIOS_BASE <= address < BIOS_BASE + BIOS_BYTES):
            found.setdefault(address, []).append((-getattr(seen, 'count', 1), word))
    return {address: [word for _, word in sorted(words)[:MAX_VARIANTS]] for address, words in found.items()}


def _runs(ranked: dict) -> list[tuple[int, bytes]]:
    """Runs of consecutive RAM addresses of one rank, as (address, little-endian words), the longest first."""
    out = []
    for rank in range(MAX_VARIANTS):
        current = None
        for address in sorted(a for a, words in ranked.items() if a < RAM_LIMIT and len(words) > rank):
            word = ranked[address][rank].to_bytes(4, 'little')
            if current and address == current[0] + len(current[1]):
                current[1].extend(word)
            else:
                current = [address, bytearray(word)]
                out.append(current)
    return sorted(((a, bytes(b)) for a, b in out), key=lambda run: (-len(run[1]), run[0]))


def _prefix(a: bytes, b: bytes) -> int:
    """Whole words equal at the start of both."""
    n = 0
    while n + 4 <= min(len(a), len(b)) and a[n:n + 4] == b[n:n + 4]:
        n += 4
    return n // 4


def translate(path, discs: int, bios: bytes | None, pairs) -> tuple[list, list, dict]:
    """(spans, BIOS rows, counts): the observed words `pairs` as rows of the player's own discs and BIOS. Words in neither, and runs the
    bounded search does not reach, stay private and are counted."""
    ranked = _ranked(pairs)
    bios_rows, kernel = [], set()
    for address, words in ranked.items():
        if address >= BIOS_BASE and bios is not None:
            offset = address - BIOS_BASE
            bios_rows += [(address, offset, 4) for word in words if bios[offset:offset + 4] == word.to_bytes(4, 'little')]
    pending = _runs(ranked)
    # The BIOS's kernel in low RAM: runs found as they are in the player's BIOS image.
    if bios is not None:
        left = []
        for address, data in pending:
            at = bios.find(data) if address < 0x10000 and len(data) >= 4 * FIND_MIN_WORDS else -1
            while at != -1 and at % 4:
                at = bios.find(data, at + 1)
            if at == -1:
                left.append((address, data))
                continue
            bios_rows += [(address + n, at + n, 4) for n in range(0, len(data), 4)]
            kernel.add(address)
        pending = left
    # The discs: every observed word of main RAM (each of the words kept at an address, overlays included) that a known RAM-to-disc
    # difference places, checked word for word. A difference is found by searching the longest run not placed yet in the disc's files.
    bios_words = {(address, int.from_bytes(bios[offset:offset + 4], 'little')) for address, offset, _ in bios_rows} if bios else set()
    remaining = {(address, word) for address, words in ranked.items() if address < RAM_LIMIT for word in words} - bios_words
    runs = [(address, run) for address, run in pending if len(run) >= 4 * FIND_MIN_WORDS]
    spans, searched, differences = [], 0, 0
    for index in range(discs):
        if not remaining:
            break
        data = DiscData(path, index)
        try:
            files = DiscFiles(data)
            placed: dict = {}
            misses = 0
            for address, run in runs:
                if not remaining or searched >= FIND_BUDGET or misses >= FIND_MISSES:
                    break
                if (address, int.from_bytes(run[:4], 'little')) not in remaining:
                    continue                            # already placed by a difference found before
                searched += 1
                offset = files.find(run[:4 * FIND_MIN_WORDS])
                if offset < 0 or _prefix(files.at(offset, len(run)), run) < FIND_MIN_WORDS:
                    misses += 1
                    continue
                misses, differences = 0, differences + 1
                delta = address - offset
                for pair in list(remaining):
                    if files.at(pair[0] - delta, 4) == pair[1].to_bytes(4, 'little'):
                        placed[pair] = delta
                        remaining.discard(pair)
            # Consecutive addresses placed by one difference make one span.
            current = None
            for (address, _), delta in sorted(placed.items(), key=lambda item: (item[1], item[0][0])):
                if current and current[0] == delta and address == current[1] + current[2]:
                    current[2] += 4
                else:
                    current = [delta, address, 4]
                    spans.append(current)
            spans = [span if isinstance(span, tuple) else (index, span[1], span[1] - span[0], span[2]) for span in spans]
        finally:
            data.close()
    words = sum(len(w) for w in ranked.values())
    in_spans = sum(length for *_, length in spans) // 4
    return sorted(spans), sorted(set(bios_rows)), {
        'observed_words': words, 'in_discs': in_spans, 'in_bios': len(set(bios_rows)),
        'private': len(remaining) + sum(len(w) for a, w in ranked.items() if a >= BIOS_BASE) - sum(1 for a, _, _ in set(bios_rows) if a >= BIOS_BASE),
        'searches': searched, 'differences': differences, 'kernel_runs_in_bios': len(kernel)}


def promote(identity: str, path, digests, sizes, bios: bytes | None, pairs, *, previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts): this player's own observed words as rows of his discs and BIOS, united with his previous record of the same
    discs and engine. Words in neither stay private, counted."""
    spans, bios_rows, counts = translate(path, len(digests), bios, pairs)
    truncated = max(0, len(spans) - PATH_CAPS[SPAN_PATH]) + max(0, len(bios_rows) - PATH_CAPS[BIOS_PATH])
    record = make_record(identity, digests, sizes, bios, spans[:PATH_CAPS[SPAN_PATH]], bios_rows[:PATH_CAPS[BIOS_PATH]])
    if previous:
        try:
            record = merged(identity, record, previous)
        except ValueError:
            pass                                   # the union is over a bound: this conversion's record alone
    spans_now, bios_now = rows(record)
    return record, {**counts, 'truncated': truncated, 'spans': len(spans_now), 'bios_rows': len(bios_now)}


def expanded_words(record: dict, path, bios: bytes | None) -> tuple[list, dict]:
    """The (address, word) pairs of a record, read from the player's own discs and BIOS, and what was left out and why."""
    spans, bios_rows = rows(record)
    sources = record['identity']['sources']
    out, left = [], {}
    by_disc: dict = {}
    for index, address, offset, length in spans:
        by_disc.setdefault(index, []).append((address, offset, length))
    from .psx_disc import DiscError
    for index, items in sorted(by_disc.items()):
        try:
            data = DiscData(path, index)
        except (DiscError, OSError) as error:
            raise ValueError('The record names a disc this game does not have.') from error
        try:
            if data.size != sources[disc_names(sources)[index]]['bytes']:
                raise ValueError('The record names a disc of another size.')
            for address, offset, length in items:
                raw = data.read(offset, length)
                out += [(address + n, int.from_bytes(raw[n:n + 4], 'little')) for n in range(0, len(raw) - 3, 4)]
        except DiscError as error:
            raise ValueError('A span reads outside the data sectors of the disc.') from error
        finally:
            data.close()
    if bios_rows:
        if bios is None or BIOS not in sources or sources[BIOS]['sha256'] != hashlib.sha256(bios).hexdigest():
            left['bios_rows'] = {'rows': len(bios_rows), 'reason': "another BIOS than this player's"}
        else:
            out += [(address, int.from_bytes(bios[offset:offset + 4], 'little')) for address, offset, _ in bios_rows]
    return out, left


def shared_words(identity: str, path, bios: bytes | None, *, qualified=None, imported=None, library=None) -> tuple[set, dict]:
    """(pairs, info): the words of the qualified bank, the player's library record and the imported bank for this game, read from his
    own discs and BIOS (`path_records.PathRecords.gathered_rows`)."""
    found, info = records().gathered_rows(identity, lambda record: expanded_words(record, path, bios),
                                          qualified=qualified, imported=imported, library=library)
    return set(found), info


# --- A conversion's use of the sharing (psx_conversion) ---------------------------------------------------------------------

def receive(identity: str, path, bios: bytes | None, pairs: dict) -> dict:
    """Before the native steps are written: the words of the qualified bank, the player's library record and the imported bank join
    `pairs` (as `psx_native.Observed` of count 1), so the first build already runs them natively. Returns what each source gave (the
    report's `knowledge.use`). A machine out of the sharing receives nothing."""
    if SYSTEM not in pp.SHARED_SYSTEMS:
        return {'shared': False}
    from . import knowledge
    from .psx_native import Observed
    found, info = shared_words(identity, path, bios, qualified=knowledge.qualified_game(SYSTEM, identity),
                               imported=knowledge.imported_game(SYSTEM, identity), library=library_record(identity))
    new = [pair for pair in found if pair not in pairs]
    for pair in new:
        pairs[pair] = Observed(1, False)
    info['new_to_this_build'] = len(new)
    info['received_words'] = len(found)
    return info


def conclude(identity: str, path, digests, bios: bytes | None, own: dict, use: dict, title: str) -> dict:
    """After every check passed: the record of this conversion's own observed words (united with the library's), written into the
    game's summary in the player's library, and the report's `knowledge` section. `shared` says whether the machine is in the sharing
    at all, not that this conversion shared anything."""
    from .systems import get_profile
    block = {'machine_status': get_profile(SYSTEM).status, 'shared': SYSTEM in pp.SHARED_SYSTEMS, 'use': dict(use)}
    if SYSTEM not in pp.SHARED_SYSTEMS:
        return block
    sizes = []
    for index in range(len(digests)):
        data = DiscData(path, index)
        sizes.append(data.size)
        data.close()
    record, counts = promote(identity, path, digests, sizes, bios, own, previous=library_record(identity))
    records().write_library_record(identity, record, title=title,
                                   record_source="the words this player's own conversions observed", record_counts=counts)
    return {**block, 'cores': engine(), 'record_sha256': record_digest(record), 'promotion': counts,
            'source': "the words this player's own conversions observed, once every check passed",
            'received_are_not_shared_until_observed': True, 'raw_bytes_stored': False, 'fresh_validation_required': True}
