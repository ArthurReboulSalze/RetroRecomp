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


def observations_from_misses(misses, rom: bytes, iwram: bytes | None) -> tuple[Observations, list[Miss]]:
    """Turn a run's misses into paths. Returns (what was learned, the misses that stay on the interpreter)."""
    learned, unresolved = Observations(), []
    for miss in misses:
        flag = THUMB if miss.thumb else 0
        address = miss.address & ~1
        if ROM_BASE <= address < ROM_BASE + min(len(rom), ROM_MAX):
            learned.roots.add((address - ROM_BASE) | flag)
        elif in_window(address, IWRAM) and iwram:
            where = find_source(rom, iwram, IWRAM[0], address - IWRAM[0])
            if where is None or where[2] < 4:
                unresolved.append(miss)
                continue
            ram_offset, rom_offset, length = where
            entry = address - IWRAM[0]
            learned.spans.add((address | flag, rom_offset + (entry - ram_offset), length - (entry - ram_offset)))
        else:
            unresolved.append(miss)
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


def config_text(name: str, sha1: str, size: int, observations: Observations) -> str:
    """The engine's per-binary TOML: the identity of the cartridge, our roots and our code copies. The finder keeps
    discovering what it can; nothing here removes code."""
    lines = ['[program]', f'name = "{name}"', 'id = "game"', f'load_address = 0x{ROM_BASE:08X}', f'size = 0x{size:08X}',
             f'entry_pc = 0x{ROM_BASE:08X}', '', '[identity]', f'sha1 = "{sha1}"', '']
    for address, offset, size_ in _copies(observations.spans):
        lines += ['[[code_copy]]', f'runtime_start = 0x{address:08X}', f'source_start = 0x{ROM_BASE + offset:08X}',
                  f'size = 0x{size_:X}', 'note = "observed by Retro-Recomp"', '']
    for entry in sorted(observations.roots):
        lines += ['[[extra_func]]', f'addr = 0x{ROM_BASE + (entry & ~1):08X}',
                  f'mode = "{"thumb" if entry & THUMB else "arm"}"', 'note = "observed by Retro-Recomp"', '']
    for address, offset, _length in sorted(observations.spans):
        lines += ['[[extra_func]]', f'addr = 0x{address & ~1:08X}', f'source_addr = 0x{ROM_BASE + offset:08X}',
                  f'mode = "{"thumb" if address & THUMB else "arm"}"', 'note = "observed by Retro-Recomp"', '']
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
