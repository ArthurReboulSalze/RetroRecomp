"""Numeric, ROM-free Atari ST paths for one exact game: no disk byte, no TOS byte, no RAM word, no code.

The Atari ST shares its paths as the experimental tier of the base (like the X68000, the Amiga, the CPS-1 and the PC Engine): a path is qualified only for the
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

The common part (records, merging, promotion, expansion, the three banks' guidance) is `m68k_media_knowledge`, shared with the X68000 and the Amiga; this module is what is
the Atari ST's: its engine identity, the logical content of its disks, its TOS view and the TOS rows, and its library of one summary per TOS.

A player with the same disks and TOS rebuilds the bytes from the images they supplied and gets the same instructions. What cannot be tied to an image stays
**private**: code a loader relocates or unpacks, a track in a custom format (the sectors of those tracks are not in the content), an STX image (not read), the
cartridge area (Hatari's own code for the GEMDOS hook of the desktop). It is counted, never shared. A record is made only from the fresh reference runs of a
conversion that then passed every check (`promote`, `atarist_conversion`): never from received paths, never from the player's own record of a real session.
"""
from __future__ import annotations

import hashlib
import json

from . import m68k_media_knowledge as media
from . import path_profiles as pp
from .x68_knowledge import text_digest

SYSTEM = 'atarist'
# The record carries no format number: its layout is empty, as the Amiga's and the Game Boy Advance's (a format of its own would be a layout key that `path_profiles` reads for every
# machine, and so a game stamp of every machine). A later record format adds that key there.
FORMAT = None
FORMATS = ()
DISK, TOS = 'disk', 'tos'
TOS_BASE = 0xFC0000
TOS_BYTES = 192 * 1024
RAM_LIMIT = 0x400000              # the ST's RAM (up to 4 MiB): where disk code runs
SPAN_LIMIT = 16384                # rows of the span block (the profile's cap)
TOS_LIMIT = 65536                 # rows of the TOS block (the profile's cap)
SPAN_BYTES = 4 << 20              # bytes the spans of a record may cover (`path_profiles.SPAN_BYTES`)
ANCHOR_BYTES = 8                  # a span of at least this many bytes is a place of the disks; a shorter one may be a coincidence of the data
# What `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, as for the Amiga and the Game Boy Advance): the exact keys of the
# layout, the names of the sources, and for each kind of path the one image its blocks point into and the window every row lies in.
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [DISK, TOS], 'required': [DISK], 'hashed': True, 'game': None},
    'paths': {'m68k': {'spans': {'src': DISK, 'window': [0, RAM_LIMIT], 'requires': DISK},
                       'ram_code': {'src': TOS, 'window': [TOS_BASE, TOS_BASE + TOS_BYTES], 'requires': TOS}}},
}
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


# --- Images --------------------------------------------------------------------------------------------------

def disk_content(blobs) -> bytes:
    """The ordered disks' standard sectors, one disk after the other (`atarist_disk.logical_content`). `blobs` are (extension, bytes) pairs. A game whose disks hold no
    standard sector at all (every track in a custom format, or images this module does not read) has the images themselves as its content: nothing is tied to it, but the
    record can still carry the TOS rows, and a record needs a source for its media."""
    from .atarist_disk import logical_content
    content = b''.join(logical_content(data, extension) for extension, data in blobs)
    content = content or b''.join(data for _, data in blobs)
    return content + b'\0' * (len(content) & 1)          # the common part refuses media of an odd size


def _tos_rows(tos: bytes | None, observed) -> tuple[list, int, int]:
    """The TOS rows of the observations above the RAM (`observed`: (pc, words) pairs): (rows, observed, kept private). A row is an instruction at its own place of the TOS
    image (`address - TOS_BASE`), valid only for a TOS with the SHA-256 the record states. What is above the RAM and not in the TOS ROM (Hatari's own code in the cartridge
    area, for the GEMDOS hook of the desktop) is private."""
    rows, seen, private = [], 0, 0
    for pc, words in observed or ():
        seen += 1
        raw = media.instruction(words)
        offset = pc - TOS_BASE
        if tos and raw is not None and type(pc) is int and 0 <= offset and offset + len(raw) <= len(tos) and not pc & 1 and tos[offset:offset + len(raw)] == raw:
            rows.append((pc, offset, len(raw)))
        else:
            private += 1
    return rows, seen, private


KNOWLEDGE = media.MediaKnowledge(
    system=SYSTEM, memory_map=SYSTEM, media=DISK, firmware=TOS, firmware_sizes=(TOS_BYTES,), firmware_window=(TOS_BASE, TOS_BASE + TOS_BYTES),
    ram_limit=RAM_LIMIT, span_limit=SPAN_LIMIT, firmware_limit=TOS_LIMIT, span_bytes=SPAN_BYTES, anchor_bytes=ANCHOR_BYTES,
    span_path='atarist_span', firmware_path='atarist_tos', format=FORMAT, formats=FORMATS,
    words=media.Words(machine='Atari ST', article='an', media_set='game', media_plural='disks', firmware='TOS', firmware_article='a', firmware_size='192 KiB'),
    engine=lambda: engine(), firmware_view=lambda tos: tos, firmware_rows=_tos_rows)

word_counts, word_count, record_digest = media.word_counts, media.word_count, media.record_digest
record_engine, source_facts = KNOWLEDGE.record_engine, KNOWLEDGE.source_facts
make_record, validate_record, rows, entry_set = KNOWLEDGE.make_record, KNOWLEDGE.validate_record, KNOWLEDGE.rows, KNOWLEDGE.entry_set
same_images, rebuild, merged, salvaged_record = KNOWLEDGE.same_images, KNOWLEDGE.rebuild, KNOWLEDGE.merged, KNOWLEDGE.salvaged_record
translate, expanded_rows, shared_rows = KNOWLEDGE.translate, KNOWLEDGE.expanded_rows, KNOWLEDGE.shared_rows


def promote(identity: str, disk: bytes, tos: bytes, observed, *, previous: dict | None = None) -> tuple[dict, dict]:
    """(record, counts) from the fresh reference runs of a verified conversion: `observed` are their (pc, words) pairs. The instructions in the RAM are tied to the disks, those above
    it to the TOS; the common `promote` then keeps the previous record's paths for the same images."""
    variants = [{'pc': pc, 'words': words} for pc, words in observed if pc < RAM_LIMIT]
    above = [(pc, words) for pc, words in observed if pc >= RAM_LIMIT]
    return KNOWLEDGE.promote(identity, disk, tos, variants, above, previous=previous)


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
