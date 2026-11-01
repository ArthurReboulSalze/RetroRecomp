"""What the header of a Game Boy cartridge says about its hardware, for the report (gate G2).

The pinned runtime models the mapper in C (`gbrt.c`, with the Wisdom Tree addition of `gameboy_runtime.py`); nothing of it is translated
from the ROM and nothing of it falls back to the interpreter. This module only names it: the header type, the mapper family, the sizes,
whether a battery file and a real-time clock are kept, and whether the runtime models this mapper at all. The battery and clock lists
and the banked ranges below are the runtime's own (`gb_cart_type_has_battery`, `gb_cart_type_has_rtc` and the mapper ranges of
`gb_context_get_rom_bank`); `tests/test_gameboy_cartridge.py` pins them. The record holds numbers and names read from the header, never
bytes of the ROM.
"""
from __future__ import annotations

# header type: (name, mapper family, rumble motor)
TYPES = {
    0x00: ('ROM ONLY', 'none', False), 0x01: ('MBC1', 'MBC1', False), 0x02: ('MBC1+RAM', 'MBC1', False),
    0x03: ('MBC1+RAM+BATTERY', 'MBC1', False), 0x05: ('MBC2', 'MBC2', False), 0x06: ('MBC2+BATTERY', 'MBC2', False),
    0x08: ('ROM+RAM', 'none', False), 0x09: ('ROM+RAM+BATTERY', 'none', False), 0x0B: ('MMM01', 'MMM01', False),
    0x0C: ('MMM01+RAM', 'MMM01', False), 0x0D: ('MMM01+RAM+BATTERY', 'MMM01', False),
    0x0F: ('MBC3+TIMER+BATTERY', 'MBC3', False), 0x10: ('MBC3+TIMER+RAM+BATTERY', 'MBC3', False), 0x11: ('MBC3', 'MBC3', False),
    0x12: ('MBC3+RAM', 'MBC3', False), 0x13: ('MBC3+RAM+BATTERY', 'MBC3', False), 0x19: ('MBC5', 'MBC5', False),
    0x1A: ('MBC5+RAM', 'MBC5', False), 0x1B: ('MBC5+RAM+BATTERY', 'MBC5', False), 0x1C: ('MBC5+RUMBLE', 'MBC5', True),
    0x1D: ('MBC5+RUMBLE+RAM', 'MBC5', True), 0x1E: ('MBC5+RUMBLE+RAM+BATTERY', 'MBC5', True), 0x20: ('MBC6', 'MBC6', False),
    0x22: ('MBC7+SENSOR+RUMBLE+RAM+BATTERY', 'MBC7', True), 0xFC: ('POCKET CAMERA', 'camera', False),
    0xFD: ('BANDAI TAMA5', 'TAMA5', False), 0xFE: ('HuC3', 'HuC3', False), 0xFF: ('HuC1+RAM+BATTERY', 'HuC1', False)}

# The runtime's own lists.
BATTERY = frozenset((0x03, 0x06, 0x09, 0x0D, 0x0F, 0x10, 0x13, 0x1B, 0x1E, 0x22, 0xFF))
CLOCK = frozenset((0x0F, 0x10))
BANKED = frozenset((*range(0x01, 0x04), 0x05, 0x06, *range(0x0F, 0x14), *range(0x19, 0x1F)))     # MBC1, MBC2, MBC3, MBC5
UNBANKED = frozenset((0x00, 0x08, 0x09))                                                          # ROM only, with or without RAM

# Header byte 0149: the RAM size code. MBC2 has its own 512 cells of four bits whatever the code says.
RAM_BYTES = {0x00: 0, 0x01: 0, 0x02: 0x2000, 0x03: 0x8000, 0x04: 0x20000, 0x05: 0x10000}
MBC2_BYTES = 512


def is_wisdom_tree(data: bytes) -> bool:
    """The runtime's rule (`rr_gb_detect_wisdom_tree`): header type 00, whole 32 KiB banks, more than 32 KiB, and both words in the ROM."""
    return (len(data) > 0x8000 and len(data) % 0x8000 == 0 and len(data) > 0x147 and data[0x147] == 0x00
            and b'WISDOM' in data and b'TREE' in data)


def cartridge_record(data: bytes) -> dict:
    """The cartridge as the header and the runtime's lists describe it."""
    code = data[0x147]
    name, family, rumble = TYPES.get(code, (f'unknown type {code:02X}', 'unknown', False))
    wisdom = is_wisdom_tree(data)
    if wisdom:
        name, family = 'Wisdom Tree (header says ROM ONLY)', 'Wisdom Tree'
    modelled = wisdom or code in BANKED or code in UNBANKED
    ram = MBC2_BYTES if family == 'MBC2' else RAM_BYTES.get(data[0x149], 0)
    return {'header_type': f'{code:02X}', 'header_name': name, 'mapper': family, 'mapper_modelled_by_runtime': modelled,
            'rom_bytes': len(data), 'rom_banks_16k': len(data) // 0x4000, 'ram_bytes': ram,
            'ram_cell_bits': 4 if family == 'MBC2' else 8,
            'battery': code in BATTERY, 'real_time_clock': code in CLOCK, 'rumble': rumble}


def device_entries(cartridge: dict) -> list[dict]:
    """The `hardware_devices` the report stores: the cartridge's mapper and the sound unit, neither of them a CPU and neither counted."""
    return [
        {'id': cartridge['mapper'], 'kind': 'cartridge_mapper', 'mode': 'c_model' if cartridge['mapper_modelled_by_runtime'] else 'not_modelled',
         'details': {**cartridge, 'translated_from_rom': False,
                     'interpreter': 'none: the mapper is C code in the runtime, driven by the writes the translated program makes',
                     'hardware_fidelity_validated': False}},
        {'id': 'apu', 'kind': 'audio_unit', 'mode': 'c_model',
         'details': {'channels': 4, 'sample_rate': 44100, 'translated_from_rom': False,
                     'interpreter': 'none: the sound unit is C code in the runtime, not a CPU with a program',
                     'corrections': ['live_envelope_mix', 'pulse_retrigger_duty_phase', 'noise_shift_14_15_clock_stop'],
                     'hardware_fidelity_validated': False}}]


def cartridge_memory(cartridge: dict) -> dict:
    """The memory layout for `saves.cartridge_memory`: what the cartridge keeps and under which names the delivered file writes it."""
    battery_ram = cartridge['battery'] and cartridge['ram_bytes'] > 0
    files = ['<title>-<ROM sha256 prefix>.sav'] if battery_ram else []
    if cartridge['real_time_clock']:
        files.append('<title>-<ROM sha256 prefix>.rtc')
    return {'battery_ram': battery_ram, 'ram_bytes': cartridge['ram_bytes'],
            'real_time_clock': cartridge['real_time_clock'], 'files': files,
            'folder': 'datas/games/<title>-<ROM sha256 prefix>/', 'written': 'only when the RAM or the clock changed',
            'validated_by': 'tools/gameboy_saves_check.py on authored cartridges (MBC1, MBC2, MBC3 with clock, MBC5), not per conversion'}
