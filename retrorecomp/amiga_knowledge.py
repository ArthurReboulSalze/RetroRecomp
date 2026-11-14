"""Numeric, ROM-free Amiga paths for one exact WHDLoad install: no install byte, no Kickstart byte, no RAM word, no code.

The Amiga shares its paths as the experimental tier of the shared base, like the X68000: a path is qualified only for the engine revision
(`cores`) that validated it, the record carries its own format number, and the whole sharing can be withdrawn with one line
(`path_profiles.EXPERIMENTAL_SHARED`). The common part is `m68k_media_knowledge`; what is the Amiga's is here.

What is shared. An install's slave loads the game's files into RAM and runs them there, and the installs that ask for one run some of the
player's Kickstart. To share what a conversion observed, the bytes are turned into numbers about the player's own images:

* RAM code that comes from the install: runs of observed instructions found, as they are, in the install's media (`install_content`: the
  slave, then the files the slave may load in the order of their names, each padded to an even length) become rows `[address, offset,
  length]` of a span. Code a game unpacks (RNC, its own packer), relocates or builds at run time is not in the files: it stays private and is
  counted. How much is found differs by install (13 November 2026, the panel's observations: Lotus 2 90 %, Blood Money 96 %, Another World
  67 %, Lemmings 35 %, Monkey Island 2 0 %, its files packed).
* Kickstart code: an observed Kickstart instruction whose words are the image's at its place is a row `[address, offset, length]` of the
  Kickstart, valid only for a Kickstart with the SHA-256 the record states (the image as the conversion maps it, 256 KiB at $FC0000). One that
  a slave patched in its writable copy differs from the image: private.

A player with the same install rebuilds the bytes from the archive they supplied and gets the same instructions. A record is made only from
the fresh reference runs of a conversion that then passed every check: never from the player's own record (F12), never from the remembered
observations of earlier conversions, never from the paths the conversion was offered.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path

from . import m68k_media_knowledge as media
from . import path_profiles as pp
from .paths import ASSETS

SYSTEM = 'amiga'
# The record carries no format number: its layout is empty, as the Game Boy Advance's (a format of its own would be a layout key that
# `path_profiles` reads for every machine, and so a game stamp of every machine). A later record format adds that key there.
FORMAT = None
FORMATS = ()
INSTALL, KICKSTART = 'install', 'kickstart'
KICKSTART_BYTES = 0x40000                 # Kickstart 1.x, the only one the profile runs
KICKSTART_WINDOW = (0xFC0000, 0x1000000)  # where it runs (the writable-ROM alias); the authored boot ROM below is not the Kickstart
RAM_LIMIT = 0xDC0000                      # the end of slow RAM: chip, fast and slow RAM are below (the profile's apertures)
SPAN_LIMIT = 16384                        # rows of the span block (the profile's cap)
KICKSTART_LIMIT = 65536                   # rows of the Kickstart block (the profile's cap)
SPAN_BYTES = pp.SPAN_BYTES                # bytes the spans of a record may cover
ANCHOR_BYTES = 8                          # a span of at least this many bytes is a place of the install; a shorter one may be a coincidence
PATH_CAPS = {'amiga_span': SPAN_LIMIT, 'amiga_kick': KICKSTART_LIMIT}

# What `validate_record` enforces on top of the schema 3 check, as data (the form the site's builder reads, `tools/build_web_limits.py`, as for the
# Game Boy Advance). Keys: `layout` (the exact keys of the layout); `sources` (`only`, `required`: the names; `hashed`: each one states its SHA-256;
# `game`: the name of the source whose SHA-256 the game id is, None here: the id is the SHA-256 of the player's archive, which no source of the record
# is); `paths` ({cpu: {kind: {`src`: the one image its blocks point into, `window`: [lowest address, first address after] every row of the kind lies in,
# `requires`: the source a block of the kind needs in the record}}}). The sizes of the sources (an even install, a 256 KiB Kickstart), the profile's
# windows, the lengths and alignments, the ceilings and the format are `path_profiles`', read by the builder from the converter.
RECORD_RULES = {
    'layout': [],
    'sources': {'only': [INSTALL, KICKSTART], 'required': [INSTALL], 'hashed': True, 'game': None},
    'paths': {'m68k': {'spans': {'src': INSTALL, 'window': [0, RAM_LIMIT], 'requires': INSTALL},
                       'ram_code': {'src': KICKSTART, 'window': list(KICKSTART_WINDOW), 'requires': KICKSTART}}},
}

# --- The engine identity (`cores`) ---------------------------------------------------------------------------
#
# A path is qualified for the revision of the engine that consumed it. The core moves whenever anything that decides what a RAM path becomes
# moves: the vAmiga pin (Moira, the 68000 whose handlers the native steps specialise), the text of the native files that run the steps, and
# GENERATOR_REVISION for the Python that generates them. Python sources cannot be hashed as text in a packaged executable, so GENERATOR_SOURCES
# are pinned by tests/test_amiga_knowledge.py (tests/amiga_generator_pins.json): editing one without raising the revision fails the test. Raise
# it whenever the generator, the guards or the semantics change in a way a RAM path could notice; every qualified path then waits again.
# 1: first revision (14 November 2026, the Amiga joins the base).
GENERATOR_REVISION = 1
NATIVE_INPUTS = ('native/amiga_machine/amiga_bus.cpp', 'native/amiga_machine/amiga_bus.h', 'native/amiga_machine/moira_map.cpp')
GENERATOR_SOURCES = ('retrorecomp/amiga_codegen.py', 'retrorecomp/amiga_translate.py', 'retrorecomp/amiga_vamiga.py', 'retrorecomp/m68k_observed.py')


def text_digest(name: str, root: Path | None = None) -> str:
    """SHA-256 of a text file with CR LF read as LF (the checkout and the package differ only there)."""
    data = ((root or ASSETS) / name).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def engine_core() -> str:
    from .amiga_vamiga import VAMIGA_REV
    native = hashlib.sha256(''.join(name + text_digest(name) for name in NATIVE_INPUTS).encode()).hexdigest()
    return hashlib.sha1(f'amiga-m68k:{GENERATOR_REVISION}:{VAMIGA_REV}:{native}'.encode()).hexdigest()


def engine() -> str:
    """The `cores` string of the base for this converter."""
    return engine_core()


UnknownFormat = pp.UnknownFormat


# --- Images --------------------------------------------------------------------------------------------------

def install_content(blob: bytes) -> bytes:
    """The install as the paths count it: the slave, then every file the slave may load in the order of their names, each padded to an even
    length (a file may start at any byte of the archive; the 68000's code starts at even addresses). The same archive gives the same bytes."""
    from . import amiga_lha, amiga_whdload
    install = amiga_whdload.install(blob)
    members = {member.name: member for member in amiga_lha.members(blob)}
    parts = [amiga_lha.extract(blob, members[install.slave_path])]
    parts += [amiga_lha.extract(blob, member) for _, member in sorted(install.files.items())]
    return b''.join(part + b'\0' * (len(part) & 1) for part in parts)


def _kickstart_view(kickstart: bytes | None) -> bytes | None:
    """The Kickstart as the machine maps it (the image itself, 256 KiB at $FC0000), or None for another size."""
    return kickstart if kickstart is not None and len(kickstart) == KICKSTART_BYTES else None


def _kickstart_rows(kickstart: bytes | None, observed) -> tuple[list, int, int]:
    """The Kickstart rows of the observed Kickstart instructions `(pc, words)`: (rows, observed, kept private). A row is an instruction of the
    word-count table inside the Kickstart window whose words are the image's at its place."""
    view = _kickstart_view(kickstart)
    rows, seen, private = [], 0, 0
    low, end = KICKSTART_WINDOW
    for row in observed or ():
        seen += 1
        pc, words = row if isinstance(row, (tuple, list)) and len(row) == 2 else (None, None)
        raw = media.instruction(words)
        if view is None or type(pc) is not int or pc & 1 or raw is None or not low <= pc or pc + len(raw) > end:
            private += 1
            continue
        offset = pc - low
        if view[offset:offset + len(raw)] != raw:
            private += 1            # a slave's patch in its writable copy, or another image
            continue
        rows.append((pc, offset, len(raw)))
    return rows, seen, private


# --- The common part, bound to the Amiga's names ---------------------------------------------------------------
KNOWLEDGE = media.MediaKnowledge(
    system=SYSTEM, memory_map='amiga', media=INSTALL, firmware=KICKSTART, firmware_sizes=(KICKSTART_BYTES,),
    firmware_window=KICKSTART_WINDOW, ram_limit=RAM_LIMIT, span_limit=SPAN_LIMIT, firmware_limit=KICKSTART_LIMIT,
    span_bytes=SPAN_BYTES, anchor_bytes=ANCHOR_BYTES, span_path='amiga_span', firmware_path='amiga_kick', format=FORMAT, formats=FORMATS,
    words=media.Words(machine='Amiga', article='an', media_set='install', media_plural='install files', firmware='Kickstart',
                      firmware_article='a', firmware_size='256 KiB'),
    engine=lambda: engine(), firmware_view=lambda kickstart: _kickstart_view(kickstart),
    firmware_rows=lambda kickstart, observed: _kickstart_rows(kickstart, observed))

record_digest = media.record_digest
record_engine, source_facts = KNOWLEDGE.record_engine, KNOWLEDGE.source_facts
make_record, validate_record, rows, entry_set = KNOWLEDGE.make_record, KNOWLEDGE.validate_record, KNOWLEDGE.rows, KNOWLEDGE.entry_set
same_images, rebuild, merged, salvaged_record = KNOWLEDGE.same_images, KNOWLEDGE.rebuild, KNOWLEDGE.merged, KNOWLEDGE.salvaged_record
translate, promote, expanded_rows, shared_rows = KNOWLEDGE.translate, KNOWLEDGE.promote, KNOWLEDGE.expanded_rows, KNOWLEDGE.shared_rows


# The player's own record of an install, beside its private memory: one per install whatever the Kickstart (that memory is per Kickstart, in
# `kick-<sha>` folders), so the conversion merges each run's paths into it (the install's are one; the Kickstart rows stay those of one image).
RECORD_FILE = 'paths-record.json'


def library_record(identity: str) -> dict | None:
    """This player's own record: the paths that fresh, verified conversions of the install reached (`<library>/amiga/<game>/paths-record.json`), or None."""
    return KNOWLEDGE.library_record(identity, RECORD_FILE)
