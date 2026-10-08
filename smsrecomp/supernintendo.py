"""ROM-scoped RAM instruction observations owned by the SNES converter."""
from __future__ import annotations
from pathlib import Path
import json
import re
from .library import atomic_json, entry_lock, library_root

RAM_VARIANT_LIMIT = 2048
PROFILES = {
    '0838e531fe22c077528febe14cb3ff7c492f1f5fa8de354192bdff7137c27f5b':
        {'id': 'smw', 'title': 'Super Mario World', 'legacy_functions': True},
    '7a8ffaf8bb549b400ec2f0bda9f3c0dbf5852c38618cdb21cd783c368383e2c7':
        {'id': 'super-scope-6', 'title': 'Super Scope 6', 'legacy_functions': False},
    '66871d66be19ad2c34c927d6b14cd8eb6fc3181965b6e517cb361f7316009cfb':
        {'id': 'zelda-alttp', 'title': 'The Legend of Zelda - A Link to the Past',
         'legacy_functions': False},
    '12b77c4bc9c1832cee8881244659065ee1d84c70c3d29e6eaf92e6798cc2ca72':
        {'id': 'super-metroid', 'title': 'Super Metroid', 'legacy_functions': False},
    '628147468c3539283197f58f03b94df49758a332831857481ea9cc31645f0527':
        {'id': 'donkey-kong-country', 'title': 'Donkey Kong Country',
         'legacy_functions': False, 'mapping': 'hirom'},
    '0ef6f4cce5a2273fa49fe1ce724e0048a8e39c91da6b00dbb693fe1ba909177d':
        {'id': 'super-castlevania-iv', 'title': 'Super Castlevania IV', 'legacy_functions': False},
}


def profile_for(rom):
    from .core import ConversionError
    profile = PROFILES.get(rom.sha256)
    if profile is None:
        raise ConversionError('SNES integration is experimental. This cartridge was '
            'identified, but will not be compiled with another game\'s profile. '
            'Qualified titles: ' + ', '.join(p['title'] for p in PROFILES.values()) + '.')
    mapping = profile.get('mapping', 'lorom')
    if rom.mapping != mapping or rom.standard != 'ntsc':
        raise ConversionError(f'This qualified SNES profile requires its NTSC {mapping} cartridge.')
    return profile


def write_profile(project: Path, rom, title: str) -> None:
    """Identity for a per-instruction program; no foreign game's function tree."""
    profile = profile_for(rom)
    (project / 'retro_snes_game.h').write_text(
        f'#define RR_SN_TITLE {json.dumps(title, ensure_ascii=True)}\n'
        f'#define RR_SN_ROM_BYTES {len(rom.data)}u\n'
        f'#define RR_SN_SMW {int(profile["legacy_functions"])}\n', encoding='ascii')
    if profile['legacy_functions']:
        return
    generated = project / 'generated'
    generated.mkdir(exist_ok=True)
    digest = ','.join(str(byte) for byte in bytes.fromhex(rom.sha256))
    # The operation map is generated separately for every ROM byte. The old
    # function-level dispatcher is unused, with its bridge disabled on both
    # paths. Empty metadata here never replaces any guest instruction body.
    (generated / 'instruction_program.c').write_text(f'''/* Original program identity. Guest operations are in snes_native_ops.inc. */
#include "cpu_state.h"
#include "program_module.h"
const DispatchEntry g_dispatch_table[] = {{{{0xffffffffu, {{NULL,NULL,NULL,NULL}}, 0}}}};
const unsigned g_dispatch_table_count = 0;
const RamRoutineGuard g_ram_routine_guards[] = {{{{0xffffffffu, 0, 0}}}};
const unsigned g_ram_routine_guard_count = 0;
static SnesProgramModule rr_program = {{
    .id = "main", .symbol_prefix = "", .dispatch = g_dispatch_table,
    .dispatch_count = 0, .guards = g_ram_routine_guards, .guard_count = 0,
    .rom_size = {len(rom.data)}u, .rom_sha256 = {{{digest}}},
    .program_digest = "{rom.sha256}", .build_digest = "rr-instruction-map-v1"
}};
SNES_PROGRAM_MODULE_CONSTRUCTOR(rr_register_instruction_program) {{
    snes_program_module_register(&rr_program);
}}
''', encoding='ascii')


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
