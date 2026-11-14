"""Numeric, ROM-free shared paths of a 68000 computer: RAM code tied to the player's own media, firmware code tied to the player's own
firmware image. No media byte, no firmware byte, no RAM word, no code.

The common part of the X68000 (disks and IPL), the Amiga (an install's files and the Kickstart) and the Atari ST (disks and TOS): a game loads
its program from the media into RAM and runs it there, and runs some of the firmware. To share what a conversion observed, the bytes are turned
into numbers about the player's own images:

* RAM code that comes from the media: the observed instructions of one run of consecutive addresses are searched, as one string of bytes, at
  an even offset of the media (the machine's own concatenation of its images). A run found there becomes one row `[address, offset, length]`
  of a `span`. Where each instruction of a span starts is not stored: it is decoded from the span's first words by the 68000 word-count
  table (`word_count`), and a span is made only when that decoding gives exactly the observed instructions.
* Firmware code: an observed firmware instruction is a row `[address, offset, length]` of the firmware image, valid only for a firmware with
  the SHA-256 the record states. Which observations are firmware instructions, and where they sit in the image, is the machine's
  (`MediaKnowledge.firmware_rows`).

A player with the same media rebuilds the bytes from the images they supplied and gets the same instructions. What cannot be tied to an image
(code unpacked, relocated or generated at run time) stays private: it is counted, never shared. A record is made only from the fresh reference
runs of a conversion that then passed every check (`promote`): never from feedback rows, never from the hints the conversion was offered.

One `MediaKnowledge` per machine holds what is the machine's: its names (system, memory map, the two source roles, the two path kinds), its
bounds, the words of its refusals, its engine identity and its firmware view. Nothing below names a machine. Cut out of `x68_knowledge` on
14 November 2026 without changing an X68000 outcome (tests/test_m68k_media_knowledge.py pins them).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from typing import Callable
import zlib

from . import path_profiles as pp

LONGEST_INSTRUCTION = 16          # eight words, the bound of the observations
UnknownFormat = pp.UnknownFormat

# The number of words of an instruction from its first word, for the 65,536 first words: the table the Mega Drive recompiler's decoder writes
# (`decode --lengths`, `tools/x68000_native.py`), deflated. The X68000's engine identity names the decoder pin and tests/test_x68_knowledge.py
# compares it, byte for byte, with the table of the decoder when a compiler is present. The 68000's instruction lengths are those of the
# instruction set, the same on every machine that runs one.
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


def instruction(words) -> bytes | None:
    """The bytes of an observed instruction when they are one complete instruction of the word-count table, else None."""
    if not isinstance(words, str) or len(words) % 4 or not 4 <= len(words) <= 2 * LONGEST_INSTRUCTION:
        return None
    try:
        raw = bytes.fromhex(words)
    except ValueError:
        return None
    return raw if len(raw) == 2 * word_count(raw[0] << 8 | raw[1]) else None


def instructions_of_span(data: bytes, address: int) -> list[tuple[int, str]]:
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


def record_digest(record) -> str:
    """SHA-256 of a record's canonical text: how a report names the record a conversion made."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def _find_even(image: bytes, needle: bytes) -> int:
    at = image.find(needle)
    while at != -1 and at & 1:
        at = image.find(needle, at + 1)
    return at


def _slot(window: bytes) -> int:
    return (int.from_bytes(window, 'big') * 2654435761 >> 8) & 0xffffff


class Image:
    """The media and a cheap way to know that a string is NOT in them: an instruction that no even offset of the media begins is private, and
    finding that out by a search of the whole image costs milliseconds each (a game that unpacks its code has tens of thousands). Two tables
    built once: the 16-bit words found at even offsets, and a bit per 4-byte window at even offsets (hashed, so a hit may be a false alarm and is
    then searched; a miss is certain). The answer for one instruction is kept, many addresses carry the same bytes."""

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
        """The first even offset of `raw` in the media, -1 when there is none (the same answer is not searched twice)."""
        if raw not in self.kept:
            self.kept[raw] = _find_even(self.data, raw) if self.may_contain(raw) else -1
        return self.kept[raw]

    def find_run(self, blob: bytes) -> int:
        return _find_even(self.data, blob) if self.may_contain(blob) else -1


def _longest(image: Image, raws: list, start: int) -> tuple[int, int]:
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


@dataclass(frozen=True)
class Words:
    """The words a machine's refusals and notes use (they reach the reports: `shared_rows` names why a record was ignored)."""
    machine: str                 # 'X68000'
    article: str                 # 'an' (an X68000, an Amiga, an Atari ST)
    media_set: str               # 'disk set': the thing a record's game identity names
    media_plural: str            # 'disks': what the media of another player is ('hints are for other disks')
    firmware: str                # 'IPL'
    firmware_article: str        # 'an' (an IPL, a Kickstart, a TOS)
    firmware_size: str           # '128 KiB': what a firmware source must hold

    @property
    def a_machine(self) -> str:
        return f'{self.article} {self.machine}'

    @property
    def an_machine(self) -> str:
        return f'{self.article.capitalize()} {self.machine}'


class MediaKnowledge:
    """The shared paths of one 68000 computer. Every function of an `x68_knowledge`-like module is a method here; the machine's module binds
    them to its names. The bounds are attributes (a test may lower one)."""

    def __init__(self, *, system: str, memory_map: str, media: str, firmware: str, firmware_sizes: tuple, firmware_window: tuple,
                 ram_limit: int, span_limit: int, firmware_limit: int, span_bytes: int, anchor_bytes: int, span_path: str,
                 firmware_path: str, format: int, formats: tuple, words: Words, engine: Callable[[], str],
                 firmware_view: Callable[[bytes | None], bytes | None], firmware_rows: Callable):
        self.system, self.memory_map, self.media, self.firmware = system, memory_map, media, firmware
        self.firmware_sizes, self.firmware_window, self.ram_limit = tuple(firmware_sizes), tuple(firmware_window), ram_limit
        self.span_limit, self.firmware_limit, self.span_bytes, self.anchor_bytes = span_limit, firmware_limit, span_bytes, anchor_bytes
        self.span_path, self.firmware_path, self.format, self.formats = span_path, firmware_path, format, tuple(formats)
        self.words, self._engine, self._firmware_view, self._firmware_rows = words, engine, firmware_view, firmware_rows

    # --- The engine -----------------------------------------------------------------------------------------

    def engine(self) -> str:
        return self._engine()

    def record_engine(self, record) -> str:
        """The `cores` string a record was built with ('' when it is not a record of the machine)."""
        try:
            return record['cpus']['m68k']['core']
        except (KeyError, TypeError):
            return ''

    @property
    def path_caps(self) -> dict:
        """The ceiling of each kind of path, by the name `entry_set` gives it (the form every schema 3 module exposes)."""
        return {self.span_path: self.span_limit, self.firmware_path: self.firmware_limit}

    # --- Images ---------------------------------------------------------------------------------------------

    def source_facts(self, media: bytes, firmware: bytes | None = None) -> dict:
        facts = {self.media: {'bytes': len(media), 'sha256': hashlib.sha256(media).hexdigest()}}
        if firmware is not None:
            facts[self.firmware] = {'bytes': len(firmware), 'sha256': hashlib.sha256(firmware).hexdigest()}
        return facts

    # --- Records (schema 3 documents) -----------------------------------------------------------------------

    def _blocks(self, span_rows, firmware_rows) -> dict:
        paths = {}
        if span_rows:
            paths['spans'] = [pp._table_block('span', span_rows, 3, self.media)]
        if firmware_rows:
            paths['ram_code'] = [pp._table_block('insn', firmware_rows, 3, self.firmware)]
        return paths

    def _assemble(self, identity: str, sources: dict, span_rows, firmware_rows, core: str) -> dict:
        span_rows = sorted({tuple(row) for row in span_rows})
        firmware_rows = sorted({tuple(row) for row in firmware_rows})
        return {'schema': pp.SCHEMA, 'game': f'{self.system}:{identity}',
                'identity': {'system': self.system, 'sources': sources, 'layout': {'format': self.format}},
                'cpus': {'m68k': {'map': self.memory_map, 'core': core, 'paths': self._blocks(span_rows, firmware_rows)}},
                'devices': {}}

    def make_record(self, identity: str, media: bytes, firmware: bytes | None, span_rows=(), firmware_rows=(), *, core: str | None = None) -> dict:
        """The schema 3 document of the media: its sources (sizes and hashes of the media and of the firmware when it holds firmware rows),
        the engine, and the rows. Rows are `[address, offset, length]`; duplicates are removed and the order is the sorted one, so equal
        hints give equal documents."""
        facts = self.source_facts(media, firmware if firmware_rows else None)
        return self._assemble(identity, facts, span_rows, firmware_rows, core or self.engine())

    def validate_record(self, record, identity: str | None = None) -> dict:
        """Strict numeric allowlist of one record (the schema 3 validator, then what is the machine's own), or ValueError (`UnknownFormat`
        for a format this converter cannot read)."""
        w = self.words
        if (isinstance(record, dict) and isinstance(record.get('identity'), dict)
                and isinstance(record['identity'].get('layout'), dict)):
            version = record['identity']['layout'].get('format', 1)
            if type(version) is int and version not in self.formats and 1 <= version <= 255:
                raise UnknownFormat(f'{w.machine} record of an unknown format.')
        try:
            pp.validate_game(record)
            if not isinstance(record, dict) or not record['game'].startswith(self.system + ':'):
                raise ValueError(f'Not {w.a_machine} record.')
            if identity is not None and record['game'] != f'{self.system}:{identity}':
                raise ValueError(f'{w.machine} hints do not match their {w.media_set} identity.')
            sources = record['identity']['sources']
            if record['identity']['layout'] != {'format': self.format} or self.media not in sources or not set(sources) <= {self.media, self.firmware}:
                raise ValueError(f'Invalid {w.machine} layout.')
            if any('sha256' not in source for source in sources.values()):
                raise ValueError(f'{w.an_machine} source states its SHA-256.')
            if self.firmware in sources and sources[self.firmware]['bytes'] not in self.firmware_sizes:
                raise ValueError(f'{w.an_machine} {w.firmware} has {w.firmware_size}.')
            if set(record['cpus']) != {'m68k'} or record['devices']:
                raise ValueError(f'{w.an_machine} record lists its 68000 section.')
            paths = record['cpus']['m68k']['paths']
            if set(paths) - {'spans', 'ram_code'}:
                raise ValueError(f'{w.an_machine} record holds RAM spans and {w.firmware} instructions only.')
            for kind, source in (('spans', self.media), ('ram_code', self.firmware)):
                for block in paths.get(kind, ()):
                    if block.get('src') != source or (source == self.firmware and self.firmware not in sources):
                        raise ValueError(f'{w.an_machine} block points into the wrong image.')
            spans, firmware_rows = self.rows(record)
            # Media code runs in RAM and firmware code in the firmware window, nowhere else (the profile's windows also hold the other).
            if any(address + length > self.ram_limit for address, _, length in spans):
                raise ValueError(f'{w.an_machine} span is outside the RAM.')
            low, end = self.firmware_window
            if any(address < low or address + length > end for address, _, length in firmware_rows):
                raise ValueError(f'{w.an_machine} {w.firmware} row is outside the {w.firmware} window.')
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f'Invalid {w.machine} record.') from error
        return record

    def rows(self, record) -> tuple[list, list]:
        """(span rows, firmware rows) of a validated record."""
        out = {'spans': [], 'ram_code': []}
        section = record['cpus']['m68k']
        profile = pp.PROFILES[('m68k', section['map'])]
        for kind in out:
            for block in section['paths'].get(kind, []):
                width = len(pp.SHAPES[block['shape']][1])
                out[kind] += [tuple(row) for row in pp.decode_table(block['table'], width, profile.caps[block['shape']])]
        return out['spans'], out['ram_code']

    def entry_set(self, record) -> set:
        """Every path of a record as comparable tuples (what the base compares between players)."""
        if not isinstance(record, dict):
            return set()
        try:
            spans, firmware_rows = self.rows(record)
        except (KeyError, TypeError, ValueError):
            return set()
        return {(self.span_path, row) for row in spans} | {(self.firmware_path, row) for row in firmware_rows}

    def same_images(self, first: dict, second: dict) -> bool:
        """Two records point into the very same media (and have the same layout). The firmware is not part of this: a record names its
        firmware only when it holds firmware rows, so two players with the same media and different firmware hold records of the same game."""
        one, two = first['identity'], second['identity']
        return first['game'] == second['game'] and one['layout'] == two['layout'] and one['sources'].get(self.media) == two['sources'].get(self.media)

    def rebuild(self, skeleton: dict, hints, *, core: str | None = None) -> dict:
        """A record of the skeleton's images holding exactly `hints` (as `entry_set` names them)."""
        spans = [row for name, row in hints if name == self.span_path]
        firmware_rows = [row for name, row in hints if name == self.firmware_path]
        sources = skeleton['identity']['sources']
        if not firmware_rows:
            sources = {name: value for name, value in sources.items() if name != self.firmware}
        return self.validate_record(self._assemble(skeleton['game'].split(':', 1)[1], sources, spans, firmware_rows,
                                                   core or self.record_engine(skeleton)))

    def merged(self, identity: str, first: dict, second: dict) -> dict:
        """Union of two records of one media. Records of another engine or other media never mix: the one built by the current engine is
        kept, else the first. The media paths are united; the firmware paths only when both records were made with the same firmware (a record
        keeps the firmware paths it has, the first's when both have some for different firmware). ValueError when the union exceeds a bound."""
        if not second:
            return first
        if not first:
            return second
        if not self.same_images(first, second) or self.record_engine(first) != self.record_engine(second):
            current = self.engine()
            return second if self.record_engine(second) == current and self.record_engine(first) != current else first
        spans = set(self.rows(first)[0]) | set(self.rows(second)[0])
        firmware_first, firmware_second = self.rows(first)[1], self.rows(second)[1]
        facts_first, facts_second = first['identity']['sources'].get(self.firmware), second['identity']['sources'].get(self.firmware)
        if not firmware_first and firmware_second:
            chosen, firmware_rows = facts_second, firmware_second
        elif firmware_first and firmware_second and facts_first == facts_second:
            chosen, firmware_rows = facts_first, set(firmware_first) | set(firmware_second)
        else:
            chosen, firmware_rows = facts_first, firmware_first
        sources = {self.media: first['identity']['sources'][self.media], **({self.firmware: chosen} if firmware_rows and chosen else {})}
        return self.validate_record(self._assemble(identity, sources, spans, firmware_rows if sources.get(self.firmware) else (),
                                                   self.record_engine(first)))

    def salvaged_record(self, identity: str, record) -> dict | None:
        """A received record, or None. A record is all or nothing: it is checked as a whole (its rows are numbers about images whose hashes
        it states, there is no row worth saving from a record that fails)."""
        try:
            return self.validate_record(record, identity)
        except (ValueError, TypeError, KeyError, AttributeError):
            return None

    # --- Observations to paths ------------------------------------------------------------------------------

    def translate(self, media: bytes, firmware: bytes | None, variants, spans) -> tuple[list, list, dict]:
        """Paths for the observations of the fresh reference runs that sit in the player's own images.

        `variants` are the observed `{'pc', 'words'}` rows; `spans` is what the machine's `firmware_rows` reads its firmware observations
        from. Returns the sorted span rows (media), the sorted firmware rows and the counts: observed, tied to an image (a ceiling) and anchored
        (in a long enough span), kept private (and why). Nothing but numbers is returned."""
        ram, other, malformed = {}, 0, 0
        for row in variants:
            pc = row.get('pc') if isinstance(row, dict) else None
            raw = instruction(row.get('words')) if isinstance(row, dict) else None
            if type(pc) is not int or pc & 1 or raw is None:
                malformed += 1
            elif 0 <= pc and pc + len(raw) <= self.ram_limit:
                ram.setdefault(pc, set()).add(raw)
            else:
                other += 1
        # Runs of consecutive addresses: the next instruction starts where the last one ends.
        span_rows, tied, anchored, private, run = [], 0, 0, 0, []
        image = Image(media)

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
                anchored += count if length >= self.anchor_bytes else 0
                start += count
            run.clear()

        for pc, raw in sorted((pc, raw) for pc, raws in ram.items() for raw in raws):
            if run and pc == run[-1][0] + len(run[-1][1]):
                run.append((pc, raw))
            else:
                close()
                run.append((pc, raw))
        close()
        firmware_rows, firmware_seen, firmware_private = self._firmware_rows(firmware, spans)
        span_rows, firmware_rows = sorted(set(span_rows)), sorted(set(firmware_rows))
        # `tied` is a ceiling: an instruction counts when its bytes sit at an even offset of the media, and a short one (two bytes) sits
        # somewhere by chance; `anchored` counts only those in a span of at least `anchor_bytes` bytes, the instructions that really come from
        # the media. Both are shared.
        counts = {'ram': {'observed': sum(len(v) for v in ram.values()), 'tied': tied, 'anchored': anchored, 'private': private, 'spans': len(span_rows)},
                  'other_windows': {'observed': other, 'tied': 0, 'private': other},
                  'malformed': malformed,
                  self.firmware: {'observed': firmware_seen, 'tied': len(firmware_rows), 'private': firmware_private}}
        return span_rows, firmware_rows, counts

    def promote(self, identity: str, media: bytes, firmware: bytes | None, variants, spans, *, previous: dict | None = None) -> tuple[dict, dict]:
        """(record, counts) from the fresh reference runs of a verified conversion. `previous` is the library's record of these very media
        and engine; its media paths are kept (and its firmware paths when the firmware is the same). The record holds no media byte, no
        firmware byte, no RAM word and no code. The limits bound each block (`counts['truncated']`)."""
        span_rows, firmware_rows, counts = self.translate(media, firmware, variants, spans)
        if previous and not isinstance(previous, dict):
            previous = None
        if previous:
            try:
                self.validate_record(previous, identity)
                facts = self.source_facts(media)
                if previous['identity']['sources'][self.media] == facts[self.media] and self.record_engine(previous) == self.engine():
                    held_spans, held_firmware = self.rows(previous)
                    span_rows = sorted(set(span_rows) | set(held_spans))
                    if firmware is not None and previous['identity']['sources'].get(self.firmware) == self.source_facts(media, firmware)[self.firmware]:
                        firmware_rows = sorted(set(firmware_rows) | set(held_firmware))
            except ValueError:
                pass
        covered = 0
        kept = []
        for row in span_rows:
            covered += row[2]
            if covered > self.span_bytes or len(kept) >= self.span_limit:
                break
            kept.append(row)
        counts['truncated'] = len(kept) < len(span_rows) or len(firmware_rows) > self.firmware_limit
        record = self.make_record(identity, media, firmware, kept, firmware_rows[:self.firmware_limit])
        self.validate_record(record, identity)
        counts['paths'] = {'ram_spans': len(self.rows(record)[0]), self.firmware: len(self.rows(record)[1])}
        counts['raw_words_stored'] = False
        return record, counts

    # --- Paths to observations ------------------------------------------------------------------------------

    def expanded_rows(self, record: dict, media: bytes, firmware: bytes | None) -> tuple[list, dict]:
        """Observation rows `(pc, words)` rebuilt from the player's own images, in the form the generator reads, and what was left out.
        ValueError when the record is not for exactly this media. The firmware rows are used only for the very firmware the record states.
        Local build input; it never leaves the process."""
        w = self.words
        self.validate_record(record)
        sources = record['identity']['sources']
        if sources[self.media] != self.source_facts(media)[self.media]:
            raise ValueError(f'{w.machine} hints are for other {w.media_plural}.')
        spans, firmware_rows = self.rows(record)
        out, left = [], {}
        for address, offset, length in spans:
            out += instructions_of_span(media[offset:offset + length], address)
        if firmware_rows:
            view = self._firmware_view(firmware)
            if firmware is None or sources.get(self.firmware) != self.source_facts(media, firmware).get(self.firmware):
                left[self.firmware] = f'another {w.firmware}'
            elif view is None:
                left[self.firmware] = f'{w.firmware_article} {w.firmware} that is not mapped as the file is'
            else:
                out += [(address, bytes(view[offset:offset + length]).hex()) for address, offset, length in firmware_rows]
        return out, left

    def shared_rows(self, identity: str, media: bytes, firmware: bytes | None, *, qualified=None, imported=None, library=None) -> tuple[list, dict]:
        """(rows, info): the guidance of the shared and library records for this media, expanded from its images.

        Three sources, counted apart: the qualified bank (used only for the engine that qualified it), the player's own library record, and
        the imported bank (other players' paths, whatever their engine, which guide discovery and are rechecked like everything else). The
        rows are build input only: they are never added to the private observations a conversion keeps. `info` says what each gave and what
        was ignored and why."""
        rows_out = []
        info = {'qualified': 0, 'library': 0, 'imported': 0, 'ignored': {}}
        current = self.engine()
        for name, record in (('qualified', qualified), ('library', library), ('imported', imported)):
            if not record:
                continue
            try:
                if name == 'qualified' and self.record_engine(record) != current:
                    info['ignored'][name] = 'another engine revision'
                    continue
                expanded, left = self.expanded_rows(record, media, firmware)
            except UnknownFormat:
                info['ignored'][name] = 'unknown record format'
                continue
            except ValueError as error:
                info['ignored'][name] = str(error)[:120]
                continue
            if left:
                info['ignored'][name + '_' + self.firmware] = left[self.firmware]
            info[name] = len(expanded)
            rows_out += expanded
        return rows_out, info

    # --- The player's library -------------------------------------------------------------------------------

    def library_record(self, identity: str) -> dict | None:
        """This player's own record: the paths that fresh, verified conversions reached (the machine's conversion writes it into the game's
        summary, `<library>/<system>/<game>/compilation.json`), or None."""
        from .library import library_root
        path = library_root(self.system) / identity / 'compilation.json'
        try:
            with path.open('rb') as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                return None
            data = json.loads(raw)
            if data.get('system') != self.system or data.get('game') != identity or not data.get('fresh_reference_passed'):
                return None
            return self.validate_record(data['record'], identity)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None
