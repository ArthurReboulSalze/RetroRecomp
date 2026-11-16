"""Find the firmware the machines need in a folder the player chooses (interface code, MIT).

The Options window's « Find firmware in a folder… » walks one folder and its subfolders once and proposes, option by option,
the files that fill the machines' firmware paths (the profiles' `OptionKey(kind='path')`). It is meant for a frontend's BIOS
folder (Batocera's `bios`) or any pile of loose BIOS files.

* A file is recognised by its content, never by its name: each option names, in `RECOGNISERS`, the check the converter already
  makes (the Neo Geo archive's members, the QSound DSP's CRC and SHA-1, the Game Boy Advance BIOS's SHA-1, the PlayStation table,
  the Kickstart and TOS headers, the MSX ROM signatures). Where the converter only checks a size (the X68000), `KNOWN_DIGESTS`
  holds the public digests of the images (data, one table). A renamed file is found; an unknown or damaged one is left out.
* The registry is keyed by option name and every path option of every profile must appear in it
  (`tests/test_machine_registry.py`); a new machine adds its line here, and the search itself holds no list of machines.
* The walk is bounded: files over `MAX_FILE_BYTES` are not read, links, junctions and other reparse points are never
  followed (nothing outside the chosen folder is read), at most `MAX_FILES` files are looked at, and a cancel event stops it.
* Nothing is written, copied, moved or uploaded here: `search` reads, `review` proposes, `to_apply` returns the paths the
  player ticked, which the window writes to its fields as the Browse buttons do. A path is kept as it is on disk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import stat
from typing import Callable

FORMAT = 1
MAX_FILE_BYTES = 16 * 1024 * 1024     # the largest firmware file a machine reads is a few MiB (an MVS BIOS archive)
MAX_FILES = 100_000                   # files looked at before the walk stops (the window says so)
PROGRESS_EVERY = 200

# Digests of firmware whose converter check is a size only (data, keyed by SHA-1, the identifier the public lists use).
# Source: MAME 0.289, `mame -listxml x68000 x68kxvi` (iplrom.dat, iplromxv.dat, iplromco.dat, cgrom.dat), read on
# 15 Nov 2026 as facts. Rank: the plain X68000's IPL first (the machine the converter models, the file px68k loads); the
# X68030's IPL 1.3 (iplrom30.dat) is left out, as the converter models a 68000 machine.
KNOWN_DIGESTS = {
    '0ed038ed2133b9f78c6e37256807424e0d927560': ('x68_ipl', 'IPL 1.0 (X68000)', 0),
    'e33cdcdb69cd257b0b211ef46e7a8b144637db57': ('x68_ipl', 'IPL 1.1 (X68000 XVI)', 1),
    '77511fc58798404701f66b6bbc9cbde06596eba7': ('x68_ipl', 'IPL 1.2 (X68000 Compact)', 2),
    '8d72c5b4d63bb14c5dbdac495244d659aa1498b6': ('x68_cgrom', 'CGROM (X68000)', 0),
}


@dataclass(frozen=True)
class Hit:
    """One candidate for one option: the path the option would hold (a file, or the folder of a machine that reads a
    folder), a language-free description, the converter's preference (smaller first) and the identity of the content
    (equal digests: the same firmware, so two copies are not a choice to make)."""
    option: str
    path: Path
    role: str
    rank: tuple = ()
    digest: str = ''


@dataclass(frozen=True)
class Check:
    """One way of recognising files: the sizes (and suffix) it reads, and the hits it finds in one file."""
    accepts: Callable[[int, str], bool]
    identify: Callable[[Path], list]


@dataclass(frozen=True)
class Recogniser:
    """How one firmware option is found. `target` 'folder': the machine reads a folder (it picks the image a game needs),
    so the option is given the folder that holds the images. `near`: a check that cannot tell this firmware from other
    files of its size; only files in a folder that holds a recognised `near` firmware are proposed, and never a file
    another option recognised; and only from the folder of the preferred `near` firmware (the home of that machine's
    files), or, when the home holds none, from the other folders holding a `near` firmware. `beside`: a firmware with a real check, preferred in that home folder. `pair`: a sub-ROM checked together with
    the preferred main ROM of (option, generation)."""
    check: Check
    source: str
    target: str = 'file'
    near: str | None = None
    beside: str | None = None
    pair: tuple | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the checks: each calls the converter's own validation ---------------------------------------------------------------

def _neogeo(path: Path) -> list:
    from .neogeo import validate_bios
    info = validate_bios(path)
    aes = 'aes' in info
    digest = info['sha256'] + (f":{info['aes'].get('crc32')}" if aes else '')
    return [('ng_bios', 'MVS BIOS (Europe)' + (' + AES' if aes else ''), (0 if aes else 1,), digest)]


def _qsound(path: Path) -> list:
    from .cps1_qsound import validate_dsp_rom
    info = validate_dsp_rom(path)
    return [('qsound_rom', 'DL-1425 (QSound DSP)', (0,), info['sha256'])]


def _gba(path: Path) -> list:
    from .gba import bios_status
    return [('gba_bios', 'Game Boy Advance BIOS', (0,), _sha256(path))] if bios_status(path) == 'known' else []


def _psx(path: Path) -> list:
    from . import psx_bios
    bios = psx_bios.identify(path)
    if bios.free:
        return []         # OpenBIOS: the converter embeds its own copy
    preferred = psx_bios.PREFERRED.get(bios.region)
    return [('psx_bios', f'{bios.model} {bios.version} ({(bios.region or "").upper()})',
             (0 if bios.model == preferred else 1,), bios.sha256)]


def _kickstart(path: Path) -> list:
    from .amiga_kickstart import scan
    found = []
    for record in scan(path).records:
        version = record.version or {}
        a500 = 0 if version.get('version') == '34.005' else 1 if version else 2
        a1200 = 0 if version.get('version') == '40.068' and version.get('model') == 'A1200' else 1 if version else 2
        found += [('amiga_kickstart', 'Kickstart ' + record.label(), (a500,), record.sha256),
                  ('a1200_kickstart', 'Kickstart ' + record.label(), (a1200,), record.sha256)]
    return found


def _tos(path: Path) -> list:
    from .atarist_tos import identify
    image = identify(path)
    return [('atarist_tos', image.label(), (-image.version,), image.sha256)] if image else []


def _x68000(path: Path) -> list:
    data = path.read_bytes()
    known = KNOWN_DIGESTS.get(hashlib.sha1(data).hexdigest())
    return [(known[0], known[1], (known[2],), hashlib.sha256(data).hexdigest())] if known else []


# C-BIOS, which the converter fetches and pins itself, is never proposed as the player's own BIOS: the images of its pinned
# release by digest, and any other release by the text its main, logo and music ROMs carry.
CBIOS_MARKS = (b'C-BIOS', b'music: INIOPL')


def _is_cbios(data: bytes) -> bool:
    from .msx_cbios import MEMBERS
    return (hashlib.sha256(data).hexdigest() in {digest for _, digest in MEMBERS.values()}
            or any(mark in data for mark in CBIOS_MARKS))


def _msx_main(path: Path) -> list:
    from .msx_conversion import _main_rom
    data = path.read_bytes()
    if _is_cbios(data):
        return []
    digest = hashlib.sha256(data).hexdigest()
    for generation, option, role in ((0, 'msx_bios', 'MSX BIOS'), (1, 'msx2_bios', 'MSX2 BIOS'),
                                     (2, 'msx2plus_bios', 'MSX2+ BIOS')):
        try:
            _main_rom(path, generation)
        except ValueError:
            continue
        return [(option, role, (0,), digest)]
    return []


def _msx_16k(path: Path) -> list:
    """A 16 KiB MSX ROM: the MSX-MUSIC BIOS (signature), else a disk ROM (header only: a weak check), else a sub-ROM
    candidate (verified with its main ROM once the walk is over)."""
    from .msx_conversion import own_diskrom, own_fmbios
    data = path.read_bytes()
    if _is_cbios(data):
        return []
    digest = hashlib.sha256(data).hexdigest()
    for option, role, check in (('msx2plus_fmbios', 'MSX-MUSIC BIOS', own_fmbios), ('msx2plus_diskrom', 'MSX disk ROM', own_diskrom)):
        try:
            check(path)
        except (ValueError, RuntimeError):
            continue
        return [(option, role, (0,), digest)]
    return [('msx2_subrom', 'MSX2 sub-ROM', (0,), digest), ('msx2plus_subrom', 'MSX2+ sub-ROM', (0,), digest)]


def _msx_kanji(path: Path) -> list:
    from .msx_conversion import own_kanji
    own_kanji(path)
    return [('msx2plus_kanji', 'MSX kanji ROM', (0,), _sha256(path))]


def _sizes(*sizes) -> Callable[[int, str], bool]:
    wanted = frozenset(sizes)
    return lambda size, suffix: size in wanted


def _checks() -> dict:
    from . import amiga_kickstart, atarist_tos, cps1_qsound, gba, psx_bios, x68000_media
    return {
        'neogeo': Check(lambda size, suffix: suffix == '.zip', _neogeo),
        'qsound': Check(lambda size, suffix: (suffix == '.zip' and size <= cps1_qsound.MAX_ARCHIVE) or size == cps1_qsound.SIZE,
                        _qsound),
        'gba': Check(_sizes(gba.BIOS_BYTES), _gba),
        'psx': Check(_sizes(psx_bios.BIOS_BYTES), _psx),
        'kickstart': Check(_sizes(*amiga_kickstart.CANDIDATE_SIZES), _kickstart),
        'tos': Check(_sizes(atarist_tos.TOS_SIZE), _tos),
        'x68000': Check(_sizes(x68000_media.IPL_BYTES, x68000_media.CGROM_BYTES), _x68000),
        'msx_main': Check(_sizes(0x8000), _msx_main),
        'msx_16k': Check(_sizes(0x4000), _msx_16k),
        'msx_kanji': Check(_sizes(0x20000, 0x40000), _msx_kanji),
    }


CHECKS = _checks()

# One line per firmware option of the profiles (OptionKey kind 'path'), keyed by its name. A new machine adds its option
# here in the same change: tests/test_machine_registry.py fails for a path option without a recogniser.
RECOGNISERS = {
    'ng_bios': Recogniser(CHECKS['neogeo'], 'neogeo.validate_bios: the MVS BIOS members, by size and CRC'),
    'qsound_rom': Recogniser(CHECKS['qsound'], 'cps1_qsound.validate_dsp_rom: CRC and SHA-1, a file or a ZIP'),
    'gba_bios': Recogniser(CHECKS['gba'], 'gba.bios_status: size and SHA-1 of the supported image'),
    'psx_bios': Recogniser(CHECKS['psx'], 'psx_bios.identify: the SHA-1 table of the retail images', target='folder'),
    'amiga_kickstart': Recogniser(CHECKS['kickstart'], 'amiga_kickstart.scan: the Kickstart header, version by CRC-32',
                                  target='folder'),
    'a1200_kickstart': Recogniser(CHECKS['kickstart'], 'amiga_kickstart.scan: the Kickstart header, version by CRC-32',
                                  target='folder'),
    'atarist_tos': Recogniser(CHECKS['tos'], 'atarist_tos.identify: the TOS 1.0x header', target='folder'),
    'x68_ipl': Recogniser(CHECKS['x68000'], 'KNOWN_DIGESTS (MAME 0.289 SHA-1)'),
    'x68_cgrom': Recogniser(CHECKS['x68000'], 'KNOWN_DIGESTS (MAME 0.289 SHA-1)'),
    'msx_bios': Recogniser(CHECKS['msx_main'], 'msx_conversion._main_rom: DI, JP and the generation byte'),
    'msx2_bios': Recogniser(CHECKS['msx_main'], 'msx_conversion._main_rom: DI, JP and the generation byte'),
    'msx2plus_bios': Recogniser(CHECKS['msx_main'], 'msx_conversion._main_rom: DI, JP and the generation byte'),
    'msx2_subrom': Recogniser(CHECKS['msx_16k'], 'msx_conversion.own_bios2 with the MSX2 main ROM found',
                              near='msx2_bios', pair=('msx2_bios', 1)),
    'msx2plus_subrom': Recogniser(CHECKS['msx_16k'], 'msx_conversion.own_bios2 with the MSX2+ main ROM found',
                                  near='msx2plus_bios', pair=('msx2plus_bios', 2)),
    'msx2plus_diskrom': Recogniser(CHECKS['msx_16k'], 'msx_conversion.own_diskrom: 16 KiB with an "AB" header',
                                   near='msx2plus_bios'),
    'msx2plus_fmbios': Recogniser(CHECKS['msx_16k'], 'msx_conversion.own_fmbios: the "APRLOPLL" signature',
                                  beside='msx2plus_bios'),
    'msx2plus_kanji': Recogniser(CHECKS['msx_kanji'], 'msx_conversion.own_kanji: 128 or 256 KiB of glyphs',
                                 near='msx2plus_bios'),
}


def path_options() -> tuple:
    """The firmware options of the registered profiles, in registration order: (option name, OptionKey, machine names)."""
    from .systems import ALL_PROFILES
    from .paths import console_options
    return tuple((key.name, key, tuple(p.name for p in ALL_PROFILES if key.name in p.option_key_names))
                 for _, key in console_options('path'))


def missing_recognisers() -> list:
    """The firmware options no recogniser covers (empty when every machine joined the registry)."""
    return [name for name, _, _ in path_options() if name not in RECOGNISERS]


# --- the walk ------------------------------------------------------------------------------------------------------------

@dataclass
class Search:
    root: Path
    hits: dict = field(default_factory=dict)     # option -> [Hit], best first
    files: int = 0           # files looked at
    links: int = 0           # links, junctions and reparse points not followed
    large: int = 0           # files over MAX_FILE_BYTES, not read
    unreadable: int = 0      # folders or files that could not be read
    cancelled: bool = False
    limited: bool = False    # MAX_FILES reached


def _reparse(entry) -> bool:
    """A link, a junction or another reparse point (a cloud placeholder): never followed, never read."""
    try:
        if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
            return True
        attributes = getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0)
        return bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
    except OSError:
        return True


def _walk(root: Path, result: Search, cancel, progress):
    """The regular files under root (no link followed), with their size; counts what was skipped."""
    pending = [root]
    while pending:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            return
        folder = pending.pop()
        try:
            with os.scandir(folder) as scanner:
                entries = sorted(scanner, key=lambda e: e.name.casefold())
        except OSError:
            result.unreadable += 1
            continue
        if progress:
            progress(result.files, folder)
        folders = []
        for entry in entries:
            if cancel is not None and cancel.is_set():
                result.cancelled = True
                return
            if _reparse(entry):
                result.links += 1
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    folders.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                result.unreadable += 1
                continue
            if result.files >= MAX_FILES:
                result.limited = True
                return
            result.files += 1
            if progress and result.files % PROGRESS_EVERY == 0:
                progress(result.files, folder)
            if size > MAX_FILE_BYTES:
                result.large += 1
                continue
            yield Path(entry.path), size
        pending.extend(reversed(folders))


def _order(hits: list) -> list:
    return sorted(hits, key=lambda hit: (hit.rank, str(hit.path).casefold()))


def _by_folder(option: str, hits: list) -> list:
    """The folders holding the images of a machine that reads a folder: one hit per folder, described by what it holds."""
    folders: dict = {}
    for hit in hits:
        folders.setdefault(hit.path.parent, []).append(hit)
    grouped = []
    for folder, inside in folders.items():
        inside = _order(inside)
        best = inside[0].rank
        distinct = {hit.digest for hit in inside}
        roles = list(dict.fromkeys(hit.role for hit in inside))
        grouped.append(Hit(option, folder, '; '.join(roles), (best, -len({h.digest for h in inside if h.rank == best}),
                                                              -len(distinct)),
                           hashlib.sha256('\n'.join(sorted(distinct)).encode()).hexdigest()))
    return _order(grouped)


def search(root, cancel=None, progress=None) -> Search:
    """Walk `root` once and return the candidates of every firmware option, best first. `cancel` is a threading.Event,
    `progress(files, folder)` is called from the walking thread. Never raises for a file: one that cannot be read or
    checked is left out."""
    root = Path(root)
    result = Search(root)
    checks = {}
    for name, recogniser in RECOGNISERS.items():
        checks.setdefault(id(recogniser.check), recogniser.check)
    raw: dict = {}
    for path, size in _walk(root, result, cancel, progress):
        suffix = path.suffix.casefold()
        for check in checks.values():
            if not check.accepts(size, suffix):
                continue
            try:
                found = check.identify(path)
            except Exception:       # a damaged or foreign file is left out, whatever its reader raised
                continue
            for option, role, rank, digest in found:
                raw.setdefault(option, []).append(Hit(option, path, role, rank, digest))
    if result.cancelled:
        return result
    strong = {hit.path for option, hits in raw.items() if RECOGNISERS[option].near is None for hit in hits}
    for option, recogniser in RECOGNISERS.items():
        hits = raw.get(option, [])
        anchor = recogniser.near or recogniser.beside
        if anchor is not None:
            mains = _order(raw.get(anchor, []))
            home = mains[0].path.parent if mains else None
            if recogniser.near is not None:
                # The home folder first; when it holds none, any folder that holds one of the machine's main ROMs.
                places = {hit.path.parent for hit in mains}
                hits = [hit for hit in hits if hit.path.parent in places and hit.path not in strong]
                if any(hit.path.parent == home for hit in hits):
                    hits = [hit for hit in hits if hit.path.parent == home]
            if recogniser.pair:
                hits = _paired(hits, mains[0], recogniser.pair[1]) if mains else []
            hits = [Hit(h.option, h.path, h.role, (0 if h.path.parent == home else 1,), h.digest) for h in hits]
        hits = _by_folder(option, hits) if recogniser.target == 'folder' else _order(hits)
        if hits:
            result.hits[option] = hits
    return result


def _paired(hits: list, main: Hit, generation: int) -> list:
    from .msx_conversion import own_bios2
    kept = []
    for hit in hits:
        try:
            own_bios2(main.path, hit.path, generation)
        except (OSError, ValueError, RuntimeError):
            continue
        kept.append(hit)
    return kept


# --- the review and what is applied ----------------------------------------------------------------------------------

@dataclass
class Line:
    option: str
    label: str               # the option's label (an interface key, or the text)
    machines: tuple          # the machines that read the option
    candidates: tuple        # Hit, best first
    current: str             # the value the option holds now ('' when empty)
    same: bool               # the current value already names the best candidate
    ambiguous: bool          # several different firmware with the same preference: the player chooses
    weak: bool               # found by a check that cannot tell it from other files of its size
    ticked: bool             # the default of its checkbox


def _same_path(value: str, path: Path) -> bool:
    from .paths import selected_bios_path
    chosen = selected_bios_path(value)
    if chosen is None:
        return False
    # Both sides resolved: a folder given in its Windows 8.3 short form (RUNNER~1) is the same folder as its long name.
    return os.path.normcase(str(chosen)) == os.path.normcase(str(Path(path).resolve()))


def review(result: Search, current: dict) -> tuple[list, list]:
    """The lines to show, machine by machine and option by option, and the (label, machines) of the options nothing was
    found for. An option the player already set is never ticked by default; an ambiguous one neither."""
    lines, missing = [], []
    for name, key, machines in path_options():
        candidates = tuple(result.hits.get(name, ()))
        if not candidates:
            missing.append((key.label or name, machines))
            continue
        value = str(current.get(name) or '').strip()
        best = candidates[0].rank
        ambiguous = len({hit.digest for hit in candidates if hit.rank == best}) > 1
        weak = RECOGNISERS[name].near is not None and len({hit.digest for hit in candidates}) > 1
        same = bool(value) and _same_path(value, candidates[0].path)
        lines.append(Line(name, key.label or name, machines, candidates, value, same, ambiguous, weak,
                          ticked=not value and not ambiguous and not weak))
    return lines, missing


def to_apply(lines: list, ticked: dict, chosen: dict) -> dict:
    """{option: path} for the ticked lines only, with the candidate the player chose (index into its candidates)."""
    values = {}
    for line in lines:
        if not ticked.get(line.option):
            continue
        index = chosen.get(line.option, 0)
        if not 0 <= index < len(line.candidates):
            index = 0
        values[line.option] = str(line.candidates[index].path)
    return values
