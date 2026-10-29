"""Data a machine's profile carries so that no registry elsewhere has to list the consoles.

Each class describes what one registry of the converter used to hold for every console: the CPU-keyed path
schema, the shape of the common report, the artwork and metadata catalogues, the library layout the memory
window reads, the pad layout of the random routes, the shared-knowledge group, the host-kit adapter and the
way a file is recognised. A profile fills the ones that apply to it and leaves the others at ``None``: a
machine that declines a registry says so by leaving its field empty (docs/NEW_MACHINE.md).

The values are copied from those registries as they were in 1.6.2 and the tests pin that they are still equal
to them (tests/test_system_profiles.py). Later, the registries read these fields instead of holding a copy.
This module holds data definitions only; it imports nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

# (minimum, maximum) bytes of a standard cartridge image as the paths schema bounds it.
CARTRIDGE_BOUNDS = (8192, 128 * 1024 * 1024 + 528)


@dataclass(frozen=True)
class PathSpec:
    """The CPU-keyed path schema (path_profiles.py) as one machine sees it."""
    # Position of the machine in the schema's own list of consoles (it differs from the documents' order).
    order: int
    # (CPU family, memory map) sections a game record owns, in order.
    sections: tuple[tuple[str, str], ...]
    # (source role, (minimum bytes, maximum bytes)) of every source a record may name.
    source_bounds: tuple[tuple[str, tuple[int, int]], ...]
    # Sources a record must name, and those that must carry a SHA-256 (the identity of its key).
    required_sources: tuple[str, ...] = ()
    hashed_sources: tuple[str, ...] = ()
    # The bounds of each (CPU family, memory map) the machine introduces, as ``(cpu, map, fields)`` where the fields
    # are those of ``path_profiles.Profile`` (roles, caps, windows...). A map two machines share (the Master System
    # and the Game Gear) is declared by one of them, once; ``sections`` says which maps a machine uses.
    shapes: tuple[tuple[str, str, dict], ...] = ()


@dataclass(frozen=True)
class ReportShape:
    """The writer of the machine's conversion report and the top-level key only that writer emits.

    The CPU architectures and counter units of the report come from ``SystemProfile.cpus``."""
    writer: str
    marker: str


@dataclass(frozen=True)
class Catalogues:
    """The public catalogues and local tables that name the machine's games."""
    # libretro-thumbnails repository of box art; ScreenScraper and TheGamesDB platform numbers.
    libretro: str | None = None
    screenscraper: int | None = None
    thegamesdb: int | None = None
    # Wikidata items of the platform (game information searches).
    wikidata: tuple[str, ...] = ()
    # The machine takes part in the reviewed cover references (assets/cover-references.json).
    cover_references: bool = False
    # The machine's own local catalogue under assets/, when it has one.
    local_catalogue: str | None = None


@dataclass(frozen=True)
class LibraryLayout:
    """Where the machine's observations live in the private library and how the memory window reads them."""
    # Folder below the library root; empty for the Master System, whose library predates the namespaces.
    folder: str
    # Glob, from the machine's folder, of the record the window summarises; None when it has no reader.
    summary_glob: str | None = None
    # 'folder_suffix' (the key follows the last hyphen of the record's folder) or 'grandfolder' (the key
    # names the folder above it).
    identity: str = 'folder_suffix'
    # A second file whose size and time enter the summary's cache stamp, beside the record.
    companion: str | None = None


@dataclass(frozen=True)
class InputLayout:
    """The pad of the random routes (random_routes.py) and the format of the script a probe reads."""
    main: tuple[str, ...]
    extra: tuple[str, ...]
    select: str | None
    # Neutral frames before the first press.
    opening: int
    # The pad has a Start button (the Master System has none).
    start: bool = True
    # Which writer formats the script ('md', 'snes', 'nes', 'ng', 'cps1', 'gb', 'sega') and its file suffix.
    script_format: str = ''
    script_suffix: str = '-inputs.txt'


@dataclass(frozen=True)
class SharedKnowledge:
    """How the machine's discoveries travel between players (path_profiles.py)."""
    # 'stable' or 'experimental': an experimental machine travels as schema 3 only and can be withdrawn.
    tier: str
    # The site's builder of the shared base reads the machine's schema 1 records.
    site_builder: bool = False
    # Withdrawing the machine leaves its games out of a file or an upload one by one instead of refusing it whole.
    withdrawable: bool = False


@dataclass(frozen=True)
class Identify:
    """Where the machine takes part in recognising a file (systems.profile_for_path).

    Two stages call a profile's hooks in the order given here. ``path_order`` is the stage that looks at the
    file itself before a ZIP is opened (``SystemProfile.identify_path``); ``content_order`` is the stage that
    sniffs the bytes of a ``.bin`` or ``.rom`` (``SystemProfile.identify_content``). ``None`` leaves a machine
    out of that stage. Orders are unique within a stage."""
    path_order: int | None = None
    content_order: int | None = None
