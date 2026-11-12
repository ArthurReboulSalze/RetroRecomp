"""What a Game Boy Advance conversion learns about a cartridge, and the engine configuration it turns into.

A path is a number about a cartridge, never bytes of it (docs/GAME_BOY_ADVANCE.md, "Paths"). Two kinds are kept, both
in the machine's schema 3 section `arm7tdmi` / `gba`:

* a **ROM root**: a function entry the engine's own analysis did not find and a run reached, as a `phys` entry, the
  cartridge offset with the Thumb flag in bit 0;
* a **RAM routine**: code copied from the cartridge into IWRAM at run time, as a `span` row (RAM address with the Thumb
  flag in bit 0, cartridge offset of the same instruction, length of the stretch where the RAM bytes equal the
  cartridge's).

The runs that observe them are the engine's own headless host (`gba_build.py`): a PC that fell to its interpreter is
written in a miss proposal, and the IWRAM image left at the end of the run says which cartridge bytes a RAM PC came
from. The proposal is never trusted blindly: the generated code that uses a RAM routine compares the live bytes with
the cartridge's before entering it, so a wrong stretch costs a counted interpreter step, not a wrong game.

Code the cartridge does not hold at all (a routine the game decompresses or writes into work RAM) is a third case, **RAM code**
(`RamCode`): the bytes the probe found at the address when the game first reached it. Those bytes are derived from the
cartridge, so they are never a path and never reach the paths library: they live in memory for the conversion in progress, are
appended to the image the generator reads (`generator_image`) and end as guarded native code in the converted game, which compares
the live bytes with them before every entry and falls back to the interpreter (counted) when they differ.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import path_profiles

ROM_BASE = 0x08000000
ROM_MAX = 32 * 1024 * 1024
IWRAM = (0x03000000, 0x03008000)
EWRAM = (0x02000000, 0x02040000)
THUMB = 1
# A stretch of live bytes this long that occurs once in the cartridge is taken as copied from it.
MAX_COPIES = 4          # copies of one stretch in a cartridge that are still read as one source (see find_source)
MATCH_WINDOWS = (48, 96, 192, 384)
SECTION = ('arm7tdmi', 'gba')

_MISS = re.compile(r'\[\[extra_func\]\]\s*addr\s*=\s*(0x[0-9A-Fa-f]+)\s*mode\s*=\s*"(arm|thumb)"'
                   r'(?:\s*note\s*=\s*"[^"\n]*?bridged x(\d+)[^"\n]*")?')


@dataclass(frozen=True)
class Miss:
    address: int
    thumb: bool
    count: int = 0


@dataclass
class Observations:
    """The numbers a cartridge has taught the converter. `roots` hold offset | Thumb flag, `spans` hold
    (RAM address | Thumb flag, cartridge offset, length)."""
    roots: set = field(default_factory=set)
    spans: set = field(default_factory=set)

    def size(self) -> int:
        return len(self.roots) + len(self.spans)

    def merge(self, other: 'Observations') -> int:
        """Add what `other` knows; returns how many entries were new."""
        before = self.size()
        self.roots |= other.roots
        self.spans |= other.spans
        return self.size() - before


def parse_misses(text: str) -> list[Miss]:
    """The addresses a run reached with no generated function, from the engine's proposal file."""
    return [Miss(int(match[1], 16), match[2] == 'thumb', int(match[3] or 0)) for match in _MISS.finditer(text)]


def in_window(address: int, window: tuple[int, int]) -> bool:
    return window[0] <= address < window[1]


def _stretch(rom: bytes, live: bytes, offset: int, found: int) -> tuple[int, int]:
    """How far the live bytes keep equal to the cartridge's before and after `offset` (the cartridge's at `found`)."""
    back = 0
    while offset - back > 0 and found - back > 0 and live[offset - back - 1] == rom[found - back - 1]:
        back += 1
    ahead = 0
    while offset + ahead < len(live) and found + ahead < len(rom) and live[offset + ahead] == rom[found + ahead]:
        ahead += 1
    return back, ahead


def find_source(rom: bytes, live: bytes, window_start: int, offset: int):
    """Where the live bytes at `offset` of a RAM image come from in the cartridge, or None.

    Returns (RAM offset of the stretch, cartridge offset of the stretch, length): the stretch around `offset` where the
    two are equal. The live bytes must occur in the cartridge and nowhere else, with one exception: a stretch that
    occurs at several places of the cartridge byte for byte (a library routine a cartridge holds twice) is the same
    code whichever copy the game read, so the longest copy is taken (the lowest address when equal). None is data
    written at run time and is left to the interpreter (counted), as are bytes that differ between their copies."""
    found, candidates = None, []
    for window in MATCH_WINDOWS:
        needle = live[offset:offset + window]
        if len(needle) < window or needle.count(0) == len(needle) or len(set(needle)) < 4:
            continue
        here = []
        position = rom.find(needle)
        while position >= 0 and len(here) <= MAX_COPIES:
            here.append(position)
            position = rom.find(needle, position + 1)
        if not here:                                           # a longer window no longer matches: the shorter ones decide
            if not candidates:
                return None
            break
        candidates = here
        if len(candidates) == 1:
            found = candidates[0]
            break
    if found is None:
        if not 1 < len(candidates) <= MAX_COPIES:
            return None
        found = max(candidates, key=lambda position: (sum(_stretch(rom, live, offset, position)), -position))
    back, ahead = _stretch(rom, live, offset, found)
    start, length = offset - back, back + ahead
    skew = start & 1
    return start + skew, found - back + skew, (length - skew) & ~1


def _ram_image(address: int, iwram: bytes | None, ewram: bytes | None):
    """(window, live bytes) of the work RAM that holds `address`, or (None, None) when the run did not dump it."""
    if in_window(address, IWRAM):
        return IWRAM, iwram
    if in_window(address, EWRAM):
        return EWRAM, ewram
    return None, None


def why_unresolved(miss: Miss, rom: bytes, iwram: bytes | None, ewram: bytes | None, samples=()) -> str:
    """Why a miss cannot become a path, in a word: 'not in the cartridge or work RAM' (an address outside both), 'no dump' (the run did not
    dump that RAM), 'no copy' (the live bytes occur nowhere in the cartridge: code made at run time, a decompressed overlay), 'too short'
    (the equal stretch is shorter than a function), 'zero' (the live bytes are empty or too uniform to be code)."""
    recorded = [live for where, live in samples if where == miss.address & ~1]
    if recorded:
        if _sample_source(rom, miss.address & ~1, samples):
            return 'copy'
        return 'zero' if all(live.count(0) == len(live) or len(set(live[:MATCH_WINDOWS[0]])) < 4 for live in recorded) else 'no copy'
    window, live = _ram_image(miss.address & ~1, iwram, ewram)
    if window is None:
        return 'not in the cartridge or work RAM'
    if not live:
        return 'no dump'
    offset = (miss.address & ~1) - window[0]
    needle = live[offset:offset + MATCH_WINDOWS[0]]
    if len(needle) < MATCH_WINDOWS[0] or needle.count(0) == len(needle) or len(set(needle)) < 4:
        return 'zero'
    where = find_source(rom, live, window[0], offset)
    if where is None:
        return 'no copy'
    return 'too short' if where[2] < 4 else 'copy'


def _sample_source(rom: bytes, address: int, samples):
    """The stretches of the cartridge that the live bytes recorded at `address` come from: [(cartridge offset, length)], longest first."""
    found = []
    for where, live in samples:
        if where != address:
            continue
        source = find_source(rom, live, 0, 0)
        if source is not None and source[2] >= 4:
            found.append((source[1] - source[0], source[2]))        # the sample starts at the address: its offset is 0
    return sorted(set(found), key=lambda item: -item[1])


MAX_VARIANTS = 256              # versions of the bytes at one address a game may have (the probe records as many)
PARAM_MIN_VALUES = 8            # an aligned word with this many different values across the versions of one routine is a parameter, not code
PARAM_NOTE = 'RAM parameter word'
POOL_ALIGN = 16
POOL_GAP = 16                   # zero bytes after each block: no stretch decodes into the next one
REUSE_MIN = 64                  # bytes a recorded stretch must share with a placed block to be read from it
IMAGE_MAX = 32 * 1024 * 1024    # the cartridge window of the bus: the image the generator reads must fit in it


@dataclass
class RamCode:
    """Code found in work RAM that the cartridge does not hold, for the conversion in progress: {(address, thumb flag): [bytes, ...]}, one
    entry per version of the bytes the game had there. Memory only: never written to the library (see the head of this module)."""
    variants: dict = field(default_factory=dict)
    refused: int = 0            # versions MAX_VARIANTS did not keep (the cap is never silent: the report counts them)
    image_overflow: bool = False  # the image the generator would read does not fit the cartridge window: no RAM code was built

    def size(self) -> int:
        return sum(len(items) for items in self.variants.values())

    def has(self, address: int, thumb: bool) -> bool:
        return (address & ~1, THUMB if thumb else 0) in self.variants

    def take(self, miss: Miss, samples) -> int:
        """Keep the versions recorded for a missed RAM address; returns how many were new (0 when there are none or all were known)."""
        if not (in_window(miss.address & ~1, IWRAM) or in_window(miss.address & ~1, EWRAM)):
            return 0
        key = (miss.address & ~1, THUMB if miss.thumb else 0)
        known = self.variants.setdefault(key, [])
        added = 0
        for where, live in samples:
            if where != key[0] or len(live) < 8:
                continue
            head = live[:MATCH_WINDOWS[0]]
            if head.count(0) == len(head) or len(set(head)) < 4 or live in known:
                continue
            if len(known) >= MAX_VARIANTS:
                self.refused += 1
                continue
            known.append(live)
            added += 1
        if not known:
            del self.variants[key]
        return added


@dataclass(frozen=True)
class RamEntry:
    """One RAM entry point of the generator: (RAM address, Thumb flag, address of its bytes in the generator's image)."""
    address: int
    thumb: bool
    source: int


def parameter_words(address: int, versions) -> list[int]:
    """Offsets from `address` of the aligned words that take PARAM_MIN_VALUES or more values across the versions of a routine: arguments the
    caller writes into the routine's own literal pool, read by the routine from the live RAM. Code that is rewritten per call is not one of
    them in practice (a handful of shapes); and if one were, the generator refuses a control flow that enters a declared data range."""
    if len(versions) < PARAM_MIN_VALUES:
        return []
    size = min(len(item) for item in versions)
    return [offset for offset in range((-address) % 4, size - 3, 4)
            if len({item[offset:offset + 4] for item in versions}) >= PARAM_MIN_VALUES]


def shapes(address: int, versions) -> tuple[list[bytes], list[int]]:
    """The versions of a routine reduced to its code shapes: one representative per distinct bytes outside the parameter words, and those words."""
    words = parameter_words(address, versions)
    if not words:
        return list(versions), []
    kept: dict = {}
    for item in versions:
        masked = bytearray(item)
        for offset in words:
            masked[offset:offset + 4] = bytes(4)
        kept.setdefault(bytes(masked), item)
    return list(kept.values()), words


def mirror_address(address: int, number: int) -> int | None:
    """The address the generator knows the `number`-th version of a routine at (a routine in work RAM that the game replaces by another one, from the
    cartridge or made at run time). The generator keeps one function per address, so versions after the first are entered at the mirrors of
    the work RAM (IWRAM repeats every 32 KB up to 0x04000000, EWRAM every 256 KB up to 0x03000000, same low bits): the guard of the generated
    code is position independent (it compares bytes and uses the live address), so the mirror is only a name for the version. None when the
    version no longer fits in the mirrors."""
    if in_window(address, IWRAM):
        size, end = IWRAM[1] - IWRAM[0], 0x04000000
    elif in_window(address, EWRAM):
        size, end = EWRAM[1] - EWRAM[0], 0x03000000
    else:
        return None
    mirrored = address + number * size
    return mirrored if mirrored < end else None


def generator_image(rom: bytes, ram_code: RamCode) -> tuple[bytes, list[RamEntry], list[tuple[int, int]]]:
    """The cartridge followed by the RAM code bytes, and one entry per version.

    The generator decodes a relocated RAM body from the bytes at its source address and embeds them as the guard of the generated code, so
    a routine the cartridge does not hold needs those bytes in the image it reads. They follow the cartridge, each block placed at
    the same offset modulo 4 as its RAM address (literal-pool alignment is kept) and followed by a gap. A stretch that repeats bytes of a block
    already placed (the routines of one decompressed overlay) is read from that block. Without RAM code, or when the image would not fit the
    cartridge window, the cartridge itself is returned and the lists are empty. The third result is the ranges of the image that hold parameter
    words (a version per code shape is placed; the words that change at every call are declared as data and are not compared at run time)."""
    if not ram_code.variants:
        return rom, [], []
    image = bytearray(rom)
    image += bytes((-len(image)) % 4096)
    placed: list[tuple[int, int, bytes]] = []                # (RAM address, offset in the image, bytes)
    entries: list[RamEntry] = []
    ranges: list[tuple[int, int]] = []
    for (address, flag), all_versions in sorted(ram_code.variants.items()):
        versions, words = shapes(address, all_versions)
        for live in versions:
            source = None
            for base, offset, data in placed:
                if base <= address < base + len(data):
                    shared = min(len(live), base + len(data) - address)
                    if shared >= REUSE_MIN and live[:shared] == data[address - base:address - base + shared]:
                        source = offset + address - base
                        break
            if source is None:
                start = (len(image) + POOL_ALIGN - 1) // POOL_ALIGN * POOL_ALIGN + (address & 3)
                image += bytes(start - len(image)) + live + bytes(POOL_GAP)
                placed.append((address, start, live))
                source = start
            entries.append(RamEntry(address, bool(flag), ROM_BASE + source))
            ranges += [(ROM_BASE + source + offset, ROM_BASE + source + offset + 4) for offset in words if offset + 4 <= len(live)]
    ram_code.image_overflow = len(image) > IMAGE_MAX
    if ram_code.image_overflow:
        return rom, [], []
    return bytes(image), entries, sorted(set(ranges))


def observations_from_misses(misses, rom: bytes, iwram: bytes | None, ewram: bytes | None = None,
                             samples=()) -> tuple[Observations, list[Miss]]:
    """Turn a run's misses into paths. Returns (what was learned, the misses that stay on the interpreter)."""
    learned, unresolved = Observations(), []
    for miss in misses:
        flag = THUMB if miss.thumb else 0
        address = miss.address & ~1
        if ROM_BASE <= address < ROM_BASE + min(len(rom), ROM_MAX):
            learned.roots.add((address - ROM_BASE) | flag)
            continue
        recorded = _sample_source(rom, address, samples)
        if recorded:                                # the bytes as they were when the address was first reached
            for rom_offset, length in recorded:
                learned.spans.add((address | flag, rom_offset, length))
            continue
        window, live = _ram_image(address, iwram, ewram)
        if window is None or not live:
            unresolved.append(miss)
            continue
        where = find_source(rom, live, window[0], address - window[0])
        if where is None or where[2] < 4:
            unresolved.append(miss)
            continue
        ram_offset, rom_offset, length = where
        entry = address - window[0]
        learned.spans.add((address | flag, rom_offset + (entry - ram_offset), length - (entry - ram_offset)))
    return learned, unresolved


def _copies(spans) -> list[tuple[int, int, int]]:
    """The code copies the spans imply: (RAM start, cartridge start, size), adjacent ones with the same bias joined."""
    stretches = sorted((address & ~1, offset, length) for address, offset, length in spans)
    joined: list[list[int]] = []
    for address, offset, length in stretches:
        if joined and joined[-1][0] + joined[-1][2] >= address and joined[-1][0] - joined[-1][1] == address - offset:
            joined[-1][2] = max(joined[-1][2], address + length - joined[-1][0])
        else:
            joined.append([address, offset, length])
    return [tuple(item) for item in joined]


def _versions(spans) -> tuple[list[tuple[int, int, int]], dict]:
    """The code copies of the cartridge with the versions of one RAM routine told apart: [(address | Thumb flag, offset, length)] and how many
    versions each (address, flag) has. Copies of one address from different cartridge offsets are versions (an overlay the game swaps in the
    same place); the lowest offset keeps the address and the others are named at its mirrors (`mirror_address`). The same offset seen with
    several lengths is one copy, the longest."""
    longest: dict = {}
    for address, offset, length in spans:
        key = (address & ~1, address & 1, offset)
        longest[key] = max(longest.get(key, 0), length)
    counts: dict = {}
    rows = []
    for (address, flag, offset), length in sorted(longest.items()):
        number = counts.get((address, flag), 0)
        counts[(address, flag)] = number + 1
        mirrored = mirror_address(address, number)
        if mirrored is not None:
            rows.append((mirrored | flag, offset, length))
    return rows, counts


def config_text(name: str, sha1: str, size: int, observations: Observations, ram_entries=(), data_ranges=(), stats: dict | None = None) -> str:
    """The engine's per-binary TOML: the identity of the image the generator reads (the cartridge, followed by the RAM code bytes
    when there are some), our roots, our code copies and our RAM entries. The finder keeps discovering what it can; nothing here
    removes code."""
    lines = ['[program]', f'name = "{name}"', 'id = "game"', f'load_address = 0x{ROM_BASE:08X}', f'size = 0x{size:08X}',
             f'entry_pc = 0x{ROM_BASE:08X}', '', '[identity]', f'sha1 = "{sha1}"', '']
    placed, versions = _versions(observations.spans)
    for address, offset, size_ in _copies(placed):
        lines += ['[[code_copy]]', f'runtime_start = 0x{address:08X}', f'source_start = 0x{ROM_BASE + offset:08X}',
                  f'size = 0x{size_:X}', 'note = "observed by Retro-Recomp"', '']
    for entry in sorted(observations.roots):
        lines += ['[[extra_func]]', f'addr = 0x{ROM_BASE + (entry & ~1):08X}',
                  f'mode = "{"thumb" if entry & THUMB else "arm"}"', 'note = "observed by Retro-Recomp"', '']
    for address, offset, _length in sorted(placed):
        lines += ['[[extra_func]]', f'addr = 0x{address & ~1:08X}', f'source_addr = 0x{ROM_BASE + offset:08X}',
                  f'mode = "{"thumb" if address & THUMB else "arm"}"', 'note = "observed by Retro-Recomp"', '']
    for start, end in data_ranges:
        lines += ['[[data_range]]', f'start = 0x{start:08X}', f'end = 0x{end:08X}', f'note = "{PARAM_NOTE}"', '']
    for entry in ram_entries:
        key = (entry.address, THUMB if entry.thumb else 0)
        number = versions.get(key, 0)
        versions[key] = number + 1
        address = mirror_address(entry.address, number)
        if address is None:
            if stats is not None:
                stats['versions_without_mirror'] = stats.get('versions_without_mirror', 0) + 1
            continue
        lines += ['[[extra_func]]', f'addr = 0x{address:08X}', f'source_addr = 0x{entry.source:08X}',
                  f'mode = "{"thumb" if entry.thumb else "arm"}"', 'note = "RAM code seen by Retro-Recomp"', '']
    return '\n'.join(lines)


def record(sha256: str, size: int, core: str, observations: Observations) -> dict:
    """The schema 3 record of a cartridge's paths (validated: a number that does not fit its bounds is a bug here)."""
    paths = {}
    if observations.roots:
        paths['entries'] = [{'shape': 'phys', 'src': 'rom',
                             'table': path_profiles.encode_table([[entry] for entry in sorted(observations.roots)], 1)}]
    if observations.spans:
        paths['spans'] = [{'shape': 'span', 'src': 'rom',
                           'table': path_profiles.encode_table(sorted(list(row) for row in observations.spans), 3)}]
    value = {'schema': path_profiles.SCHEMA, 'game': 'gba:' + sha256,
             'identity': {'system': 'gba', 'sources': {'rom': {'bytes': size, 'sha256': sha256}}, 'layout': {}},
             'cpus': {SECTION[0]: {'map': SECTION[1], 'core': core, 'paths': paths}}, 'devices': {}}
    return path_profiles.validate_game(value)


def observations_of(document: dict) -> Observations:
    """The paths of a validated record (the reverse of `record`)."""
    paths = path_profiles.validate_game(document)['cpus'].get(SECTION[0], {}).get('paths', {})
    found = Observations()
    for block in paths.get('entries', ()):
        found.roots |= {row[0] for row in path_profiles.decode_table(block['table'], 1, 1 << 20)}
    for block in paths.get('spans', ()):
        found.spans |= {tuple(row) for row in path_profiles.decode_table(block['table'], 3, 1 << 20)}
    return found
