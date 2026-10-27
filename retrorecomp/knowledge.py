"""Read-only compilation hints, never ROM bytes.

References into the user's exact ROM reconstruct guarded RAM patterns. The
executable carries none: the qualified bank (`qualified_path()`) is written
locally from the shared base before a batch. Local learning stays additive; a
custom library directory opts out of every shared hint. Hints imported from
another user's export are kept in their own bank, merged with the qualified
one at use, and verified by every conversion like the rest.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import zlib
from . import path_profiles
from .paths import ASSETS

# The maintainer campaigns' source file (tools/build_compilation_knowledge.py).
# It stays in the repository but is neither bundled nor read by the converter.
RESOURCE = 'assets/compilation-knowledge.json.gz'
# A bounded decompressed budget, shared by the builder and package audit.
# Growing multi-console observations exceeded the 32 MiB, then the 64 MiB
# cap (Mega Drive collection campaign); the distributed resource remains
# gzip-compressed and strictly numeric.
MAX_BYTES = 128 * 1024 * 1024
# The table of schema 1 fields lives once, in path_profiles (`LEGACY_FIELDS`): this is that
# dictionary. Neo Geo additionally accepts bounded rom_deltas via its dedicated validator.
FIELDS = path_profiles.LEGACY_FIELDS


def validate_payload(value: dict) -> dict:
    """Strict numeric allowlist excludes paths, credentials, images and code. The rules of
    schema 1 live in `path_profiles.validate_legacy_payload`."""
    return path_profiles.validate_legacy_payload(value)


def _document(path: Path):
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Compilation knowledge exceeds its size limit.')
    return json.loads(raw)


def read(path: Path) -> dict:
    """A local bank, validated, as the schema 1 bank {"schema": 1, "consoles": ...} whatever its
    own schema: 1 (what is written today) or 3 (CPU-keyed, `path_profiles`), by its `schema`."""
    return path_profiles.read_bank(_document(path))


def refuse_to_drop_games(path: Path) -> None:
    """ValueError when `path` is a schema 3 bank holding a game that has no schema 1 form (CPS-1,
    X68000, several cores). The writers of this module and of `knowledge_exchange` read a bank
    through the schema 1 view and write {"schema": 1, ...}: they would drop those games, so they
    call this first and write nothing when it refuses. A file that is absent or unreadable is
    treated as empty by the readers and may be written over, as before."""
    try:
        dropped = read_games(path) if path.is_file() else {}
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return
    if dropped:
        raise ValueError(f'{path.name} is a schema 3 bank holding {len(dropped)} game(s) without a schema 1 form '
                         '(' + ', '.join(sorted(dropped)[:3]) + '); a schema 1 writer would drop them.')


def read_games(path: Path) -> dict:
    """{game key: schema 3 record} of a schema 3 bank's games that have no schema 1 form
    (CPS-1, X68000): {} for a schema 1 bank, which cannot hold them."""
    return path_profiles.bank_games(_document(path))


@lru_cache(maxsize=4)
def load(path: Path) -> dict:
    return read(path)


def imported_path() -> Path:
    from .paths import data_directory
    return data_directory() / 'knowledge' / 'imported.json.gz'


@lru_cache(maxsize=2)
def _imported_bank(path: str, size: int, modified: int) -> dict:
    return read(Path(path))['consoles']


def qualified_path() -> Path:
    from .paths import data_directory
    return data_directory() / 'knowledge' / 'qualified.json.gz'


@lru_cache(maxsize=2)
def _qualified_bank(path: str, size: int, modified: int) -> dict:
    return read(Path(path))['consoles']


def qualified_bank() -> dict:
    """The qualified bank's consoles ({} when absent, invalid or disabled);
    a changed file is read again."""
    if disabled():
        return {}
    path = qualified_path()
    try:
        stat = path.stat()
        return _qualified_bank(str(path), stat.st_size, stat.st_mtime_ns)
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return {}


def qualified_record(system: str, identity: str) -> dict:
    """The qualified bank's record for one exact identity, or {}."""
    return qualified_bank().get(system, {}).get(identity, {})


@lru_cache(maxsize=2)
def _qualified_games(path: str, size: int, modified: int) -> dict:
    return read_games(Path(path))


def qualified_game(system: str, identity: str) -> dict:
    """The qualified bank's schema 3 record of a game that schema 1 cannot hold (CPS-1, the
    X68000), or {}: only a schema 3 bank has any."""
    if disabled():
        return {}
    path = qualified_path()
    try:
        stat = path.stat()
        return _qualified_games(str(path), stat.st_size, stat.st_mtime_ns).get(f'{system}:{identity}', {})
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return {}


def bundled_record(system: str, rom, engine: str) -> dict:
    """The qualified bank's record for this exact ROM, built by this compiler revision and
    without the imported hints ({} otherwise). The one reader every console uses."""
    record = qualified_record(system, rom.sha256)
    return (record if record.get('engine') == engine and record.get('rom_bytes') == len(rom.data)
            and hashlib.sha256(rom.data).hexdigest() == rom.sha256 else {})


# Cartridges converting again without their imported hints (see batch).
_SET_ASIDE: set = set()
_SET_ASIDE_LOCK = threading.Lock()


@contextmanager
def imported_set_aside(system: str, identity: str):
    """Ignore one cartridge's imported hints while it converts again."""
    with _SET_ASIDE_LOCK:
        _SET_ASIDE.add((system, identity))
    try:
        yield
    finally:
        with _SET_ASIDE_LOCK:
            _SET_ASIDE.discard((system, identity))


def write_packed(path: Path, document: dict) -> bytes:
    """Atomic, bounded gzip JSON (imported bank and shared files)."""
    raw = json.dumps(document, separators=(',', ':'), sort_keys=True, ensure_ascii=True).encode('ascii')
    if len(raw) > MAX_BYTES:
        raise ValueError('Knowledge size budget exceeded.')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(packed); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return packed


# Raw gameplay observations shared by other players, ROM-free: each row is
# [kind, address, auxiliary, length, rom_offset]; the bytes are read back from
# this player's own ROM at conversion time (feedback.records).
OBSERVATION_LIMIT = 4096
OBSERVATION_OFFSET_LIMIT = 64 * 1024 * 1024


def imported_observations_path() -> Path:
    return imported_path().with_name('imported-observations.json.gz')


def valid_observation_rows(system: str, rows) -> list:
    """Strict numeric rows of one cartridge, or ValueError."""
    from .feedback import KINDS
    if not isinstance(rows, list) or len(rows) > OBSERVATION_LIMIT:
        raise ValueError('Invalid shared observations.')
    clean = []
    for row in rows:
        if (not isinstance(row, list) or len(row) != 5 or any(type(value) is not int for value in row)
                or row[0] not in KINDS[system] or not 0 <= row[1] <= 0xffffffff
                or not 0 <= row[2] <= 0xffffffff or not 1 <= row[3] <= 16
                or not 0 <= row[4] < OBSERVATION_OFFSET_LIMIT):
            raise ValueError('Invalid shared observation.')
        clean.append(list(row))
    return clean


def read_observations(path: Path) -> dict:
    """{system: {sha256: rows}} from a gzip bank, validated."""
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Observation bank exceeds its size limit.')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('consoles'), dict):
        raise ValueError('Invalid observation bank.')
    banks = {}
    for system, games in data['consoles'].items():
        if system not in FIELDS or not isinstance(games, dict):
            raise ValueError('Invalid observation bank console.')
        for identity, rows in games.items():
            if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
                raise ValueError('Invalid observation bank identity.')
            banks.setdefault(system, {})[identity] = valid_observation_rows(system, rows)
    return banks


@lru_cache(maxsize=2)
def _observation_bank(path: str, size: int, modified: int) -> dict:
    return read_observations(Path(path))


def imported_observations(system: str, identity: str) -> list:
    """Imported ROM-free rows of one cartridge (none while set aside)."""
    if (system, identity) in _SET_ASIDE or disabled():
        return []
    path = imported_observations_path()
    try:
        stat = path.stat()
        return _observation_bank(str(path), stat.st_size, stat.st_mtime_ns).get(system, {}).get(identity, [])
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return []


def write_observations(banks: dict) -> None:
    write_packed(imported_observations_path(),
                 {'schema': 1, 'consoles': {system: games for system, games in sorted(banks.items()) if games}})


def discard_imported(system: str, identity: str, reason: str) -> bool:
    """Remove one cartridge's imported hints and observations after they broke
    a conversion that succeeded without them; the rejection is logged."""
    path = imported_path()
    record = observations = None
    try:
        consoles = read(path)['consoles'] if path.is_file() else {}
        record = consoles.get(system, {}).pop(identity, None)
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        consoles = None
    try:
        banks = read_observations(imported_observations_path()) if imported_observations_path().is_file() else {}
        observations = banks.get(system, {}).pop(identity, None)
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        banks = None
    if record is None and observations is None:
        return False
    if record is not None:
        refuse_to_drop_games(path)
        write_packed(path, validate_payload({'schema': 1, 'consoles': {k: v for k, v in consoles.items() if v}}))
    if observations is not None:
        write_observations(banks)
    record = record or {}
    log = path.with_name('imported-rejected.json')
    try:
        entries = json.loads(log.read_text(encoding='utf-8'))
        entries = entries if isinstance(entries, list) else []
    except (OSError, ValueError):
        entries = []
    entries.append({'system': system, 'rom_sha256': identity, 'engine': record.get('engine', ''),
                    'observations': len(observations or []),
                    'reason': str(reason)[:300],
                    'rejected_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    log.write_text(json.dumps(entries[-500:], indent=2) + '\n', encoding='utf-8')
    return True


def imported_record(system: str, identity: str) -> dict:
    """The imported bank's record; a changed file is read again."""
    if (system, identity) in _SET_ASIDE:
        return {}
    path = imported_path()
    try:
        stat = path.stat()
        return _imported_bank(str(path), stat.st_size, stat.st_mtime_ns).get(system, {}).get(identity, {})
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return {}


@lru_cache(maxsize=2)
def _imported_games(path: str, size: int, modified: int) -> dict:
    return read_games(Path(path))


def imported_game(system: str, identity: str) -> dict:
    """`qualified_game` for the imported bank (and set aside like `imported_record`)."""
    if (system, identity) in _SET_ASIDE:
        return {}
    path = imported_path()
    try:
        stat = path.stat()
        return _imported_games(str(path), stat.st_size, stat.st_mtime_ns).get(f'{system}:{identity}', {})
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        return {}


def disabled() -> bool:
    return bool(os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR')
                or os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE') == '0')


def merge_records(system: str, first: dict, second: dict) -> dict:
    """Union of two records of one identity; order is kept."""
    if not second:
        return first
    if not first:
        return second
    from .snes_knowledge import SPC_FIELDS, references
    merged = dict(first)
    for name in FIELDS[system]:
        if name in SPC_FIELDS:
            continue
        values, seen = [], set()
        for entry in (*first.get(name, []), *second.get(name, [])):
            if tuple(entry) not in seen:
                seen.add(tuple(entry)); values.append(list(entry))
        if values:
            merged[name] = values
    if system == 'snes':
        refs = sorted(set(references(first)) | set(references(second)))
        for name in SPC_FIELDS:
            merged.pop(name, None)
        if refs:
            merged['spc_refs'] = [list(entry) for entry in refs]
    return merged


def record_for(system: str, rom, engine: str) -> dict:
    if system=='ng':
        # A cartridge hash alone is insufficient: its selected firmware and
        # prepared multi-region identity must be supplied by the Neo Geo API.
        return {}
    if disabled():
        return {}
    bundled = qualified_record(system, rom.sha256)
    # The qualified bank is qualified for its own compiler. Imported hints
    # count whatever compiler found them: they only guide discovery, and
    # every conversion still checks native code against the reference CPU.
    usable = [record for record in (bundled, imported_record(system, rom.sha256))
              if record and (record is not bundled or record.get('engine') == engine)
              and record.get('rom_bytes') == len(rom.data)]
    if not usable or hashlib.sha256(rom.data).hexdigest() != rom.sha256:
        return {}
    return merge_records(system, *usable) if len(usable) == 2 else usable[0]


def ram_variants(system: str, rom, engine: str, *, field='ram_refs') -> list[dict]:
    return [{'address': address, 'bytes': rom.data[offset:offset+length].hex()}
            for address, offset, length in record_for(system, rom, engine).get(field, [])]
