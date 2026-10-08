"""ROM-scoped RAM instruction observations owned by the SNES converter."""
from __future__ import annotations
from pathlib import Path
import json
import re
from .library import atomic_json, entry_lock, library_root

RAM_VARIANT_LIMIT = 2048


def wram_offset(address: int) -> int | None:
    if not isinstance(address, int) or not 0 <= address <= 0xffffff:
        return None
    bank, offset = address >> 16, address & 0xffff
    if bank in (0x7e, 0x7f):
        return address & 0x1ffff
    if bank & 0x7f < 0x40 and offset < 0x2000:
        return offset
    return None


def valid_ram_variant(item) -> bool:
    if not isinstance(item, dict):
        return False
    address, raw = item.get('address'), item.get('bytes')
    return (isinstance(address, int) and isinstance(raw, str)
            and re.fullmatch('[0-9a-fA-F]{8}', raw) is not None
            and all(wram_offset((address & 0xff0000) | ((address + n) & 0xffff)) is not None
                    for n in range(4)) and 0 <= address <= 0xffffff)


def memory_file(rom) -> Path:
    return library_root('snes') / rom.sha256 / 'native-ram.json'


def read_ram_variants(rom) -> list[dict]:
    try:
        record = json.loads(memory_file(rom).read_text(encoding='utf-8'))
        if record.get('schema') != 1 or record.get('rom_sha256') != rom.sha256:
            return []
        return [item for item in record.get('ram_variants', []) if valid_ram_variant(item)][:RAM_VARIANT_LIMIT]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def learn_ram_variants(rom, checks) -> int:
    additions = {(item['address'], item['bytes'].lower()) for check in checks
                 for item in check.get('ram_variants', []) if valid_ram_variant(item)}
    if not additions:
        return 0
    path = memory_file(rom)
    with entry_lock(path.parent):
        previous = {(item['address'], item['bytes'].lower()) for item in read_ram_variants(rom)}
        merged = set(sorted(previous | additions)[:RAM_VARIANT_LIMIT])
        if previous != merged:
            atomic_json(path, {'schema': 1, 'rom_sha256': rom.sha256, 'ram_variants':
                [{'address': address, 'bytes': raw} for address, raw in sorted(merged)]})
    return len(merged - previous)
