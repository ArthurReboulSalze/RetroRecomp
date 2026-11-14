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

from functools import lru_cache
import hashlib
from pathlib import Path

from . import m68k_media_knowledge as media
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
# 2: ABCD, SBCD and NBCD on bytes that are not two decimal digits (13 November 2026): the translated steps take the three new state rules of
# `m68000_state_rules` (shared with the Mega Drive, Neo Geo and CPS-1) and Musashi's twenty decimal handlers take the same arithmetic
# (`musashi_fixes`), so the two paths agree and the 22 decimal vectors of m68k-groups pass. The generated code changes only for those three
# instructions; V follows Moira too (the five flags). Valid decimal operands give the same result as before.
GENERATOR_REVISION = 2
NATIVE_INPUTS = ('native/x68000_native/CMakeLists.txt', 'native/x68000_native/decode.c', 'native/x68000_native/guard_checks.c',
                 'native/x68000_native/observe.c', 'native/x68000_native/observe.h')
GENERATOR_SOURCES = ('tools/x68000_native.py', 'tools/x68000_base74.py', 'retrorecomp/m68k_observed.py', 'retrorecomp/m68000.py', 'retrorecomp/m68000_state_rules.py',
                     'retrorecomp/megadrive_rules.py', 'retrorecomp/musashi_fixes.py', 'retrorecomp/neogeo_codegen.py')

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


UnknownFormat = pp.UnknownFormat


# --- Images --------------------------------------------------------------------------------------------------

def disk_content(disks) -> bytes:
    """The ordered disks as the machine stores them, one after the other (`DiskImage.content`)."""
    from .x68000_media import identify_disk
    return b''.join(identify_disk(path).content() for path in disks)


def _ipl_mapped(ipl: bytes | None) -> bytes | None:
    """The IPL as the machine maps it, or None when this IPL is not mapped as the file is (a SCSI boot marker)."""
    if ipl is None:
        return None
    from tools.x68000_native import ipl_view
    return ipl_view(ipl)


def _ipl_rows(ipl: bytes | None, spans) -> tuple[list, int, int]:
    """The IPL rows of the observation file's IPL spans (`schema` 2): (rows, IPL instructions observed, kept private). A row is valid only for
    the very IPL it was observed with, mapped as the file is, inside the IPL's code."""
    from tools.x68000_native import IPL_CODE_END, IPL_SPANS
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
    return ipl_rows, ipl_seen, ipl_private


# --- The common part (retrorecomp/m68k_media_knowledge.py), bound to the X68000's names --------------------------------------
#
# Cut out of this module on 14 November 2026 (the Amiga and the Atari ST share it); every outcome is the one before the cut
# (tests/test_m68k_media_knowledge.py). The engine and the IPL view are read through this module's names when they are called, so a
# test that patches them here is seen.
KNOWLEDGE = media.MediaKnowledge(
    system=SYSTEM, memory_map='x68', media=DISK, firmware=IPL, firmware_sizes=(IPL_BYTES,), firmware_window=(0xfc0000, 0xfffffe),
    ram_limit=RAM_LIMIT, span_limit=SPAN_LIMIT, firmware_limit=IPL_LIMIT, span_bytes=SPAN_BYTES, anchor_bytes=ANCHOR_BYTES,
    span_path='x68_span', firmware_path='x68_ipl', format=FORMAT, formats=FORMATS,
    words=media.Words(machine='X68000', article='an', media_set='disk set', media_plural='disks', firmware='IPL', firmware_article='an',
                      firmware_size='128 KiB'),
    engine=lambda: engine(), firmware_view=lambda ipl: _ipl_mapped(ipl), firmware_rows=lambda ipl, spans: _ipl_rows(ipl, spans))

word_counts, word_count, record_digest = media.word_counts, media.word_count, media.record_digest
_Image = media.Image
record_engine, source_facts = KNOWLEDGE.record_engine, KNOWLEDGE.source_facts
make_record, validate_record, rows, entry_set = KNOWLEDGE.make_record, KNOWLEDGE.validate_record, KNOWLEDGE.rows, KNOWLEDGE.entry_set
same_images, rebuild, merged, salvaged_record = KNOWLEDGE.same_images, KNOWLEDGE.rebuild, KNOWLEDGE.merged, KNOWLEDGE.salvaged_record
translate, promote, expanded_rows, shared_rows = KNOWLEDGE.translate, KNOWLEDGE.promote, KNOWLEDGE.expanded_rows, KNOWLEDGE.shared_rows
library_record = KNOWLEDGE.library_record
