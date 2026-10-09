"""Read-only compilation hints shipped with the converter, never ROM bytes.

References into the user's exact ROM reconstruct guarded RAM patterns. Local
learning stays additive; a custom library directory opts out of bundled hints.
"""
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import zlib
from .paths import ASSETS

RESOURCE = 'assets/compilation-knowledge.json.gz'
MAX_BYTES = 32 * 1024 * 1024
FIELDS = {
    'sms': {'rom_entries': (5, 65536), 'pattern_refs': (1, 4096)},
    'gg': {'rom_entries': (5, 65536), 'pattern_refs': (1, 4096)},
    'gb': {'rom_entries': (2, 65536)},
    'nes': {'rom_entries': (2, 65536)},
    'md': {'rom_entries': (1, 65536), 'ram_refs': (3, 2048), 'z80_refs': (3, 32768)},
    'snes': {'ram_refs': (3, 2048), 'spc_refs': (2, 262144)},
}


def validate_payload(value: dict) -> dict:
    """Strict numeric allowlist excludes paths, credentials, images and code."""
    if (not isinstance(value, dict) or set(value) != {'schema', 'consoles'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['consoles'], dict)
            or not set(value['consoles']) <= FIELDS.keys()):
        raise ValueError('Invalid compilation knowledge schema.')
    for system, games in value['consoles'].items():
        if not isinstance(games, dict) or len(games) > 4096:
            raise ValueError('Invalid compilation knowledge catalogue.')
        for sha, record in games.items():
            if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
                    or not isinstance(record, dict)
                    or not {'engine', 'rom_bytes'} <= record.keys()
                    or not set(record) <= {'engine', 'rom_bytes', *FIELDS[system]}
                    or not isinstance(record['engine'], str)
                    or not re.fullmatch('[0-9a-f]{40}', record['engine'])
                    or type(record['rom_bytes']) is not int
                    or not 8192 <= record['rom_bytes'] <= 128 * 1024 * 1024 + 528):
                raise ValueError('Invalid compilation knowledge identity.')
            for name, (width, limit) in FIELDS[system].items():
                entries = record.get(name, [])
                if (not isinstance(entries, list) or len(entries) > limit
                        or any(not isinstance(e, list) or len(e) != width
                               or any(type(n) is not int or not 0 <= n <= 0xffffffff for n in e)
                               for e in entries)):
                    raise ValueError('Invalid compilation knowledge entries.')
                for entry in entries:
                    if name == 'rom_entries':
                        valid = True
                        if system in ('sms', 'gg'):
                            valid = entry[0] < 0xbf01 and all(b <= 255 for b in entry[1:4])
                        elif system == 'gb':
                            valid = entry[0] < record['rom_bytes'] // 0x4000 and entry[1] < 0x8000
                        elif system == 'nes':
                            valid = entry[0] < record['rom_bytes'] // 4096 and 0x8000 <= entry[1] <= 0xffff
                        elif system == 'md':
                            valid = 0x200 <= entry[0] <= record['rom_bytes'] - 8 and not entry[0] & 1
                        if not valid:
                            raise ValueError('Invalid ROM compilation entry.')
                    if name == 'pattern_refs' and entry[0] + 4 > record['rom_bytes']:
                        raise ValueError('Compilation pattern outside ROM.')
                    if name == 'spc_refs' and (entry[0] > 65535 or 0xf0 <= entry[0] <= 0xff
                                               or entry[1] >= record['rom_bytes']):
                        raise ValueError('Invalid SPC700 compilation reference.')
                    if name in ('ram_refs', 'z80_refs'):
                        if not 1 <= entry[2] <= 16 or entry[1] + entry[2] > record['rom_bytes']:
                            raise ValueError('Compilation reference outside ROM.')
    return value


@lru_cache(maxsize=4)
def load(path: Path) -> dict:
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Compilation knowledge exceeds its size limit.')
    return validate_payload(json.loads(raw))


def record_for(system: str, rom, engine: str) -> dict:
    if (os.environ.get('RETRO_RECOMP_LIBRARY_DIR') or os.environ.get('SMSRECOMP_LIBRARY_DIR')
            or os.environ.get('RETRO_RECOMP_BUNDLED_KNOWLEDGE') == '0'):
        return {}
    try:
        record = load(ASSETS / RESOURCE)['consoles'].get(system, {}).get(rom.sha256, {})
        if (record.get('engine') == engine and record.get('rom_bytes') == len(rom.data)
                and hashlib.sha256(rom.data).hexdigest() == rom.sha256):
            return record
    except (OSError, ValueError, TypeError, KeyError, EOFError, zlib.error):
        pass
    return {}


def ram_variants(system: str, rom, engine: str, *, field='ram_refs') -> list[dict]:
    return [{'address': address, 'bytes': rom.data[offset:offset+length].hex()}
            for address, offset, length in record_for(system, rom, engine).get(field, [])]
