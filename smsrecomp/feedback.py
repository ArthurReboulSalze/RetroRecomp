"""Private, bounded gameplay fallback candidates, saved only on game shutdown.

These files are not qualified knowledge. Each compiler keeps its usual byte
guards and fresh reference checks; no raw feedback is bundled or published.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import struct
import tempfile

from .paths import ASSETS

LIMIT = 4096
HEADER = struct.Struct('<8sIII8s64sI')
RECORD = struct.Struct('<BBHII16sI')
MAX_BYTES = HEADER.size + LIMIT * RECORD.size
SYSTEMS = {'sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1'}
KINDS = {'sms': {1}, 'gg': {1}, 'gb': {2}, 'nes': {3, 4},
         'md': {5, 6, 7}, 'snes': {8, 9}, 'ng': {10, 11, 12}, 'x68': {13},
         'cps1': {14, 15, 16}}


@dataclass(frozen=True, order=True)
class Observation:
    kind: int
    address: int
    auxiliary: int
    data: bytes


def checksum(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def _identity(system: str, identity: str) -> None:
    if system not in SYSTEMS or not re.fullmatch('[0-9a-f]{64}', identity):
        raise ValueError('Invalid runtime feedback identity.')


def decode(data: bytes, system: str, identity: str) -> tuple[list[Observation], int]:
    _identity(system, identity)
    if len(data) < HEADER.size or len(data) > MAX_BYTES:
        raise ValueError('Invalid runtime feedback length.')
    magic, version, count, dropped, console, key, digest = HEADER.unpack_from(data)
    if (magic != b'RRFB001\0' or version != 1 or count > LIMIT or
            len(data) != HEADER.size + count * RECORD.size or
            console != system.encode().ljust(8, b'\0') or key != identity.encode() or
            checksum(data[HEADER.size:]) != digest):
        raise ValueError('Corrupt or mismatched runtime feedback.')
    rows = []
    for offset in range(HEADER.size, len(data), RECORD.size):
        kind, length, flags, pc, aux, raw, reserved = RECORD.unpack_from(data, offset)
        if (kind not in KINDS[system] or not 1 <= length <= 16 or flags or reserved or
                any(raw[length:])):
            raise ValueError('Invalid runtime feedback record.')
        rows.append(Observation(kind, pc, aux, raw[:length]))
    if len(set(rows)) != len(rows):
        raise ValueError('Repeated runtime feedback record.')
    return rows, dropped


def encode(rows: list[Observation], system: str, identity: str, dropped: int = 0) -> bytes:
    _identity(system, identity)
    # Caller orders newest candidates first. Sorting here would silently lose
    # new high-address observations once a prior file is already saturated.
    all_unique = list(dict.fromkeys(rows))
    dropped = max(dropped, len(all_unique) - LIMIT)
    unique = all_unique[:LIMIT]
    raw = b''.join(RECORD.pack(row.kind, len(row.data), 0, row.address,
                              row.auxiliary, row.data.ljust(16, b'\0'), 0) for row in unique)
    data = HEADER.pack(b'RRFB001\0', 1, len(unique), min(dropped, 0xffffffff),
                       system.encode().ljust(8, b'\0'), identity.encode(), checksum(raw)) + raw
    decode(data, system, identity)
    return data


def _load(path: Path, system: str, identity: str) -> tuple[list[Observation], int]:
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    return decode(data, system, identity)


def _read(path: Path, system: str, identity: str) -> tuple[list[Observation], int]:
    try:
        return _load(path, system, identity)
    except (OSError, ValueError, struct.error):
        return [], 0


def private_file(system: str, identity: str) -> Path:
    from .library import library_root
    _identity(system, identity)
    return library_root(system) / '_runtime-feedback' / (identity + '.rrfb')


def records(system: str, identity: str, kind: int | None = None) -> list[Observation]:
    rows, _ = _read(private_file(system, identity), system, identity)
    return [row for row in rows if kind is None or row.kind == kind]


def variants(system: str, identity: str, kind: int) -> list[dict]:
    return [{'address': r.address, 'bytes': r.data.hex()} for r in records(system, identity, kind)]


def sega_candidates(rom) -> tuple[set, set[bytes]]:
    seeds, patterns = set(), set()
    for row in records(rom.system_id, rom.sha256, 1):
        pc, packed = row.address, row.auxiliary
        if pc > 0xffff or packed > 0xffffff or len(row.data) != 4:
            continue
        banks = [(packed >> (8*n)) & 255 for n in range(3)]
        if pc + 255 < 0xc000:
            data = bytes(rom.data[(addr if addr < 0x400 else
                banks[addr >> 14] * 0x4000 + (addr & 0x3fff)) % len(rom.data)]
                for addr in range(pc, pc+256))
            if data[:4] == row.data:
                seeds.add((pc, *banks, checksum(data)))
                patterns.add(row.data)
        # Writable code is a candidate only; the Z80 compiler retains its live
        # four-byte guard. Never grant ROM coverage using a RAM window.
        if pc >= 0xc000:
            patterns.add(row.data)
    return seeds, patterns


def gb_entries(rom) -> set[tuple[int, int]]:
    entries = set()
    for row in records('gb', rom.sha256, 2):
        pc, bank = row.address, row.auxiliary
        offset = bank*0x4000 + (pc & 0x3fff)
        span = min(len(row.data), 0x4000 - (pc & 0x3fff))
        if (pc < 0x8000 and bank < len(rom.data)//0x4000 and
                row.data and rom.data[offset:offset+span] == row.data[:span]):
            entries.add((bank, pc))
    return entries


def nes_sites(rom) -> tuple[set[str], set[tuple[int, int]]]:
    entries, guards = set(), set()
    prg_start = 16 + (512 if rom.data[6] & 4 else 0)
    from .nes import _nes_size
    prg_bytes = _nes_size(rom.data[4], rom.data[9] & 15, 16384) if rom.nes2 else rom.data[4]*16384
    for row in records('nes', rom.sha256):
        pc, bank = row.address, row.auxiliary
        if row.kind == 3 and 0x8000 <= pc <= 0xffff and len(row.data) == 1:
            offset = bank*4096 + (pc & 4095)
            if offset < prg_bytes and prg_start + offset < len(rom.data) and rom.data[prg_start+offset:prg_start+offset+1] == row.data:
                entries.add(f'4k:{bank:X}:{pc:04X}')
        if row.kind == 4 and (pc < 0x2000 or 0x6000 <= pc <= 0xffff) and len(row.data) == 1:
            guards.add((pc, row.data[0]))
    return entries, guards


def _retain(system: str, identity: str, rows: list[Observation], dropped: int = 0):
    """Atomically merge private candidates, never promote them to qualified data."""
    from .library import entry_lock
    target = private_file(system, identity)
    if not rows:
        old, overflow = _read(target, system, identity)
        return old, overflow, False
    with entry_lock(target.parent):
        old, overflow = _read(target, system, identity)
        if set(rows).issubset(old) and dropped <= overflow:
            return old, overflow, False
        payload = encode(rows + old, system, identity, max(dropped, overflow))
        fd, name = tempfile.mkstemp(prefix=identity + '.', suffix='.tmp', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        merged, overflow = decode(payload, system, identity)
        return merged, overflow, True


def _linked(path: Path) -> bool:
    try:
        # FILE_ATTRIBUTE_REPARSE_POINT also covers Windows junctions on Python
        # versions predating Path.is_junction(). Do not traverse source links.
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def _feedback_files(root: Path, system: str, identity: str | None = None, *, emit):
    """Bounded, read-only search of an explicitly chosen games directory."""
    root = Path(root)
    if _linked(root):
        return
    pattern = re.compile(re.escape(system) + '-(' + (identity or '[0-9a-f]{64}') + r')\.rrfb')
    visited = matched = 0
    skipped = {'.git', '.build', 'artwork', 'boxart', 'boxarts', 'states', 'library', 'cache'}
    for base, directories, files in os.walk(root, followlinks=False):
        visited += 1
        if visited > 50000:
            emit('Gameplay feedback: search limit reached; choose a more specific games folder.')
            return
        folder = Path(base)
        if len(folder.relative_to(root).parts) >= 16:
            directories[:] = []
        else:
            directories[:] = [name for name in directories
                if name.casefold() not in skipped and not _linked(folder/name)]
        if folder.name.casefold() == 'datas':
            directories[:] = [name for name in directories if name.casefold() == 'fallbacks']
        for name in files:
            match = pattern.fullmatch(name)
            if match is None or _linked(folder/name):
                continue
            matched += 1
            if matched > 50000:
                emit('Gameplay feedback: file limit reached; choose a more specific games folder.')
                return
            yield folder/name, match[1]


def _export_locations(system: str, preferences: dict) -> list[Path]:
    from .paths import games_directory, preferred_games_root, feedback_search_paths
    from .systems import get_profile
    configured, _ = preferred_games_root(preferences)
    roots = [games_directory(system_id=system), configured/get_profile(system).export_folder]
    extra = feedback_search_paths(preferences).get(system)
    if extra is not None:
        roots.append(extra)
    return list(dict.fromkeys(roots))


def import_saved_feedback(system: str, preferences: dict, *, emit=lambda message: None) -> dict:
    """Recover every game's candidates without ROMs or a conversion queue.

    Source files are read only; the independent converter copy survives moves,
    preference changes and deletion of the game's original datas directory.
    """
    _identity(system, '0'*64)
    files = {}
    for root in _export_locations(system, preferences):
        for path, identity in _feedback_files(root, system, emit=emit):
            try:
                files.setdefault(identity, {})[path] = path.stat().st_mtime_ns
            except OSError:
                pass
    games, updated, invalid, accepted = {}, set(), 0, 0
    # Stream one bounded file at a time, merge once per game. Importing older
    # and newer saturated copies must not repeatedly evict/reinsert records.
    for identity, sources in files.items():
        candidates, dropped = {}, 0
        for path in sorted(sources, key=lambda path: sources[path], reverse=True):
            try:
                rows, overflow = _load(path, system, identity)
            except (OSError, ValueError, struct.error):
                invalid += 1
                continue
            dropped = max(dropped, overflow)
            if rows:
                accepted += 1
            for row in rows:
                if row in candidates:
                    continue
                if len(candidates) < LIMIT:
                    candidates[row] = None
                else:
                    dropped = max(dropped, 1)
        if not candidates:
            continue
        retained, _overflow, changed = _retain(system, identity, list(candidates), dropped)
        games[identity] = len(retained)
        if changed:
            updated.add(identity)
    return {'files': accepted, 'games': len(games), 'updated_games': len(updated),
            'observations': sum(games.values()), 'invalid_files': invalid,
            'bytes': sum(HEADER.size + RECORD.size*count for count in games.values()),
            'fresh_validation_required': True}


def ingest(system: str, identity: str, output: Path | None, *, emit=lambda message: None) -> dict:
    """Import beside the selected exports and retain locally across regenerations.

    Never scan the ROM's source folder/share. Only known local export locations
    and the converter's private bank are considered. Reads create nothing.
    """
    from .paths import load_preferences, feedback_search_paths
    preferences = load_preferences()
    locations = _export_locations(system, preferences)
    if output is not None:
        selected = Path(output).resolve()
        locations += [selected, *selected.parents]
    found: dict[Observation, int] = {}
    dropped = 0
    def accept(path, rows):
        nonlocal dropped
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        for row in rows:
            found[row] = max(stamp, found.get(row, 0))
        if len(found) > LIMIT:
            dropped = max(dropped, len(found)-LIMIT)
            for row in sorted(found, key=lambda row: (-found[row], row))[LIMIT:]:
                del found[row]
    for directory in set(locations):
        path = directory / 'datas/fallbacks' / f'{system}-{identity}.rrfb'
        rows, overflow = _read(path, system, identity)
        accept(path, rows)
        dropped = max(dropped, overflow)
    extra = feedback_search_paths(preferences).get(system)
    if extra is not None:
        for path, _key in _feedback_files(extra, system, identity, emit=emit):
            rows, overflow = _read(path, system, identity)
            accept(path, rows)
            dropped = max(dropped, overflow)
    rows, overflow, _changed = _retain(system, identity,
        sorted(found, key=lambda row: (-found[row], row)), dropped)
    if rows:
        emit(f'Gameplay feedback: {len(rows)} unique fallback candidates ({HEADER.size + RECORD.size * len(rows)} bytes); fresh validation required.')
    import hashlib
    fingerprint = hashlib.sha256(encode(sorted(rows), system, identity)).hexdigest()
    return {'schema': 1, 'identity': identity, 'fingerprint': fingerprint,
            'unique_candidates': len(rows), 'limit_reached': bool(overflow),
            'toggle_key': 'F12', 'recording_default': True,
            'bytes': HEADER.size + RECORD.size * len(rows) if rows else 0,
            'max_bytes_per_game': MAX_BYTES, 'saved_at': 'normal_process_exit',
            'fresh_validation_required': True}


def stage(project: Path, system: str, identity: str, *, target: str = 'game', cmake: bool = True) -> None:
    """Stage common exit-only recorder into a generated project."""
    _identity(system, identity)
    for name in ('runtime_feedback.h', 'runtime_feedback.c', 'runtime_feedback_sdl.h', 'platform_io.h', 'platform_io.c'):
        destination = project / name
        data = (ASSETS / 'native' / name).read_bytes()
        if not destination.is_file() or destination.read_bytes() != data:
            destination.write_bytes(data)
    config = (f'#define RR_FEEDBACK_SYSTEM "{system}"\n'
              f'#define RR_FEEDBACK_IDENTITY "{identity}"\n')
    destination = project / 'runtime_feedback_config.h'
    if not destination.is_file() or destination.read_text(encoding='ascii') != config:
        destination.write_text(config, encoding='ascii')
    if cmake:
        path = project / 'CMakeLists.txt'
        source = path.read_text(encoding='utf-8')
        source += (f'\ntarget_sources({target} PRIVATE runtime_feedback.c)\n'
                   f'if(NOT WIN32)\n  target_sources({target} PRIVATE platform_io.c)\nendif()\n'
                   f'target_include_directories({target} PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}")\n')
        path.write_text(source, encoding='utf-8')
