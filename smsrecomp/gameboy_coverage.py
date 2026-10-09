"""Extra ROM discovery and reproducible probes for the pinned SM83 compiler.

Static candidates are compilation hints, not proof that a byte is code.
Observed ROM entries are kept separately and never include writable RAM.
"""
from dataclasses import dataclass
from pathlib import Path


Entry = tuple[int, int]
TRACE_LIMIT = 8 * 1024 * 1024


def read_entries(path: Path | None, rom_size: int) -> set[Entry]:
    entries: set[Entry] = set()
    if path is None or not path.is_file():
        return entries
    # Runtime traces can repeat the same entry on every frame; stream them.
    with path.open(encoding='ascii', errors='replace') as stream:
        for line in stream:
            try:
                bank_text, address_text = line.strip().split(':')
                bank, address = int(bank_text, 10), int(address_text, 16)
            except ValueError:
                continue
            if 0 <= bank < rom_size // 0x4000 and 0 <= address < 0x8000:
                entries.add((bank, address))
    return entries


def write_entries(path: Path, entries: set[Entry]) -> None:
    text = ''.join(f'{bank}:{address:04x}\n' for bank, address in sorted(entries))
    if len(text) > TRACE_LIMIT:
        raise ValueError('Game Boy entry library exceeds its size limit.')
    path.write_text(text, encoding='ascii')


def branch_entries(rom: bytes) -> set[Entry]:
    """Seed short JP/JR relays that the upstream multi-opcode heuristic skips.

    Inspect each byte independently, including overlapping candidates. Only
    operands wholly inside one physical bank qualify. No ROM is patched and
    no dynamic target or RAM contents are assumed to be constant.
    """
    entries: set[Entry] = set()
    for bank in range(len(rom) // 0x4000):
        base = bank * 0x4000
        window = 0 if bank == 0 else 0x4000
        for offset in range(0x4000):
            if bank == 0 and 0x104 <= offset < 0x150:
                continue  # Cartridge header/logo, not a discovery hint.
            opcode = rom[base + offset]
            address = window + offset
            if opcode == 0xC3 and offset <= 0x3FFD:
                target = rom[base + offset + 1] | rom[base + offset + 2] << 8
            elif opcode == 0x18 and offset <= 0x3FFE:
                displacement = rom[base + offset + 1]
                if displacement >= 128:
                    displacement -= 256
                target = (address + 2 + displacement) & 0xFFFF
            else:
                continue
            if target < 0x8000:
                entries.add((bank, address))
    return entries


@dataclass(frozen=True)
class ProbeScenario:
    name: str
    input_script: str = ''


def varied_scenario(frames: int) -> ProbeScenario:
    """Explore menu choices and released/reversed controls as well as movement."""
    actions = [(180, 'S', 4), (450, 'S', 4), (600, 'S', 4), (750, 'A', 8),
               (1000, 'D', 20), (1050, 'A', 8), (1200, 'S', 4),
               (1500, 'R', 800), (2300, 'L', 700), (3200, 'R', 1000),
               (4300, 'L', 800), (5250, 'R', 700)]
    actions += [(i, 'A', 8) for i in range(1600, frames, 73)]
    actions += [(i, 'B', 10) for i in range(1650, frames, 131)]
    script = ','.join(f'{start}:{buttons}:{min(duration, frames-start)}'
                      for start, buttons, duration in actions if start < frames)
    return ProbeScenario('varied', script)


def probe_scenarios(frames: int) -> tuple[ProbeScenario, ...]:
    scenarios = [ProbeScenario('boot')]
    for direction in ('R', 'L'):
        actions = ['60:S:2'] if frames > 60 else []
        if frames > 150:
            actions.append(f'150:{direction}:{frames - 150}')
        actions.extend(f'{frame}:A:8' for frame in range(200, frames, 60))
        if direction == 'L':
            actions.extend(f'{frame}:B:8' for frame in range(230, frames, 120))
        if actions:
            scenarios.append(ProbeScenario(f'play_{direction.lower()}', ','.join(actions)))
    if frames >= 750:
        scenarios.append(varied_scenario(frames))
    return tuple(scenarios)


def cpu_validation_scenarios(frames: int, *, deep: bool = False) -> tuple[tuple[ProbeScenario, int], ...]:
    """Keep discovery independent of the costly per-instruction CPU checks."""
    return tuple((scenario, min(frames, 30 if scenario.name == 'boot' else 240))
                 for scenario in probe_scenarios(frames)
                 if deep or scenario.name == 'boot')
