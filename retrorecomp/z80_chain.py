"""What a machine declares to use the banked Z80 chain (the Master System and the Game Gear today).

The chain is the banked emitter appended to the pinned Z80 generator (`native/banked_emitter.inc`) and the step loop of the
generated game (`native/banked_runtime.inc`). Both used to carry the Sega mapper as constants: three 16 KiB slots with a bank
register each (the bank key `b0, b1, b2`), a first KiB that never pages, code from RAM at `pc >= $C000`, the plain Z80 cycle
table and /INT sampled at the start of a step. They are data here, one `Z80Machine` per machine, named by its profile
(`z80_machine`); this module turns it into the text the two files need. A second Z80 machine declares its own value and
reuses the files (docs/STANDARDS.md rule 1).

Two ways to key the translated code:

* `Z80Regions`: by bank registers. The slots are fixed, each has one register, RAM starts where they end. The Sega mapper.
* `Z80RegionMap`: by a region map the machine's bus keeps. Every region shows a bank of one of several sources (cartridge,
  firmware) or RAM, and the map changes at run time; a position is keyed by (source, bank, offset). No machine uses it yet.

Game role, group `shares:z80_main` (retrorecomp/stamp_inputs.py): an edit moves the game stamp of the machines on the chain.
It imports no module of the converter.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Z80Regions:
    """An address space keyed by bank registers: the slots whose code is translated ahead of time and the RAM cut."""
    # log2 of the size of one switchable slot (14: 16 KiB).
    slot_bits: int
    # Slots from address 0, each with one bank register: the arity of the bank key of `game_banked_step`.
    slots: int
    # Bytes at the start of slot 0 that the mapper never pages (0: none).
    fixed_bytes: int
    # First PC that only runs through the byte guards (code in RAM): the end of the last slot, stated and checked.
    ram_from: int
    # How many values a bank register takes (the mirror period of the ROM must fit).
    bank_values: int
    # The scope the coverage report names (`support_scope` of banked-coverage.json).
    scope: str

    def __post_init__(self):
        if not (8 <= self.slot_bits <= 15 and 1 <= self.slots <= 8 and self.slots << self.slot_bits <= 0x10000):
            raise ValueError('Z80 regions: 1 to 8 slots of 256 bytes to 32 KiB inside 64 KiB.')
        if self.ram_from != self.slots << self.slot_bits:
            raise ValueError('Z80 regions: the RAM cut is the end of the last slot.')
        if self.fixed_bytes and not 4 <= self.fixed_bytes < 1 << self.slot_bits:
            raise ValueError('Z80 regions: the fixed start is none or 4 bytes to less than one slot.')
        if not 1 <= self.bank_values <= 256:
            raise ValueError('Z80 regions: a bank register is one byte.')

    def initialiser(self) -> str:
        return (f'.mapped = 0, .slot_bits = {self.slot_bits}, .slots = {self.slots}, .fixed_bytes = 0x{self.fixed_bytes:X}, '
                f'.ram_from = 0x{self.ram_from:X}, .sources = 1, .bank_values = {self.bank_values}')


@dataclass(frozen=True)
class Z80RegionMap:
    """An address space keyed by a region map: 64 KiB cut in equal regions, each showing at run time a bank of one source or RAM.

    The machine's bus keeps the map and gives it to the step loop (`smsrecomp_region_map()`), with a counter it raises each
    time the map changes (`smsrecomp_region_generation`). RAM is wherever the map says, and an instruction that reaches the
    next region is checked against the bytes it reads there."""
    # log2 of the size of one region (13: eight regions of 8 KiB).
    region_bits: int
    # The sources a region can show, in the order of the map's `source` numbers. The first is the cartridge of game.toml;
    # the generator reads the others from the files `banked.sources` names beside it, one per line, in this order.
    sources: tuple[str, ...]
    bank_values: int
    scope: str

    def __post_init__(self):
        if not 10 <= self.region_bits <= 15:
            raise ValueError('Z80 region map: regions of 1 KiB to 32 KiB.')
        if not 1 <= len(self.sources) <= 16 or len(set(self.sources)) != len(self.sources):
            raise ValueError('Z80 region map: 1 to 16 sources, each named once.')
        if not 1 <= self.bank_values <= 256:
            raise ValueError('Z80 region map: a bank number is one byte.')

    @property
    def regions(self) -> int:
        return 0x10000 >> self.region_bits

    def initialiser(self) -> str:
        return (f'.mapped = 1, .slot_bits = {self.region_bits}, .slots = {self.regions}, .fixed_bytes = 0x0, '
                f'.ram_from = 0x10000, .sources = {len(self.sources)}, .bank_values = {self.bank_values}')


# When the step loop reads the /INT level of an instruction it will accept the interrupt after.
IRQ_SAMPLES = ('step_start', 'instruction_end')


@dataclass(frozen=True)
class Z80Machine:
    """One machine on the banked Z80 chain."""
    # Names the machine in the generator's source; never a console id.
    key: str
    regions: Z80Regions | Z80RegionMap
    # Wait states the machine adds to every M1 (opcode fetch) cycle: T-states per fetch, on top of the Z80's own. They are
    # added per M1 of an instruction (one, two behind a prefix), per iteration of a repeating block instruction and per
    # HALT cycle; the acceptance of an interrupt keeps the Z80's own count.
    m1_wait: int = 0
    # 'step_start': the level is latched before the instruction runs (the Sega runner's contract, shared with its reference
    # CPU). 'instruction_end': it is read after the instruction, once the hardware has caught up with it.
    irq_sample: str = 'step_start'
    # Suffix of the folders where the machine's own build of the generator lives (.deps/recompiler-src<tag>,
    # .deps/recompiler-build<tag>...). Empty for the Sega mapper, whose folders predate it; another machine names its own, so
    # that two machines never rebuild each other's generator.
    generator_tag: str = ''

    def __post_init__(self):
        if not 0 <= self.m1_wait <= 3:
            raise ValueError('Z80 machine: 0 to 3 wait states per M1 cycle.')
        if self.irq_sample not in IRQ_SAMPLES:
            raise ValueError('Z80 machine: /INT is sampled at step_start or at instruction_end.')
        if self.generator_tag and not (self.generator_tag.startswith('-') and self.generator_tag[1:].isalnum()):
            raise ValueError('Z80 machine: the generator tag is empty or a hyphen and letters or digits.')

    @property
    def mapped(self) -> bool:
        return isinstance(self.regions, Z80RegionMap)

    @property
    def generator_source(self) -> str:
        """Folder, below .deps, of the patched generator sources of this machine."""
        return 'recompiler-src' + self.generator_tag

    @property
    def generator_build(self) -> str:
        """Folder, below .deps, where they are built (the toolchain's suffix follows it)."""
        return 'recompiler-build' + self.generator_tag

    @property
    def counts_m1(self) -> bool:
        """The reference CPU must count its M1 cycles (cpu.prepare_reference): the fallback adds the wait states from them."""
        return self.m1_wait > 0


def emitter_source(machine: Z80Machine, emitter: str) -> str:
    """The banked emitter for one machine: its description as a C initialiser, then the emitter that reads it."""
    return (f'/* The machine this generator is built for (retrorecomp/z80_chain.py, {machine.key}). */\n'
            f'#define BANKED_MACHINE {{ {machine.regions.initialiser()}, .m1_wait = {machine.m1_wait}, '
            f'.scope = "{machine.regions.scope}" }}\n' + emitter)


def _once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f'The banked runtime changed; the Z80 chain must follow: {old[:90]!r}')
    return source.replace(old, new, 1)


def _runtime_parts(machine: Z80Machine) -> tuple[str, ...]:
    """The lines of the step loop that depend on the machine, in the order they appear in native/banked_runtime.inc."""
    regions = machine.regions
    count = regions.regions if machine.mapped else regions.slots
    if machine.mapped:
        seen = '    uint32_t seen_generation = UINT32_MAX;\n'
        mark = ('        const BankedRegion *map = smsrecomp_region_map();\n'
                '        if (smsrecomp_region_generation != seen_generation) {\n'
                f'            for (int region = 0; region < {count}; ++region) if (!map[region].ram) banked_seen[region][map[region].bank] = 1;\n'
                '            seen_generation = smsrecomp_region_generation;\n'
                '        }\n')
        key = 'map'
    else:
        word = 'uint32_t' if count <= 4 else 'uint64_t'
        terms = [f'({word})(uint8_t)g_bank[{slot}]' + (f' << {8 * slot}' if slot else '') for slot in range(count)]
        packed = (' |\n' + ' ' * 25).join(' | '.join(terms[first:first + 2]) for first in range(0, count, 2))
        seen = f'    {word} seen_banks = {word[:-2].upper()}_MAX;\n'
        mark = (f'        {word} banks = {packed};\n'
                '        if (banks != seen_banks) {\n'
                f'            for (int slot = 0; slot < {count}; ++slot) banked_seen[slot][(uint8_t)g_bank[slot]] = 1;\n'
                '            seen_banks = banks;\n'
                '        }\n')
        key = ', '.join(f'(uint8_t)g_bank[{slot}]' for slot in range(count))
    at_start = machine.irq_sample == 'step_start'
    return (
        f'static uint8_t banked_seen[{count}][256];\n',
        # The counted fallback: one instruction on the reference CPU, which knows no wait state. It counts its M1 cycles
        # (cpu.prepare_reference, `m1_counter`) and the machine's wait states are added from that count.
        ('    z80_step(&g_hz);\n' if not machine.m1_wait else
         '    extern unsigned long z80_m1_fetches;\n    unsigned long m1_before = z80_m1_fetches;\n    z80_step(&g_hz);\n'
         f'    g_hz.cyc += {machine.m1_wait} * (z80_m1_fetches - m1_before);   /* the machine\'s wait states, per M1 cycle */\n')
        + '    state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = base + g_hz.cyc;\n',
        seen,
        '        if (!prefix_pending) pending_irq = vdp_irq_asserted();\n' if at_start else '',
        mark,
        f'            g_z80.cyc += {4 + machine.m1_wait}; banked_halt_steps++;\n',
        f'            int step = game_banked_step({key});\n',
        '        prefix_pending = 0; g_frame_ic++;\n' + ('' if at_start else
            '        banked_advance_vdp(g_z80.cyc);   /* the hardware catches up, then /INT is read at the end of the instruction */\n'
            '        pending_irq = vdp_irq_asserted();\n')
        + '        banked_after_step(pending_irq);\n',
        f'    unsigned counts[{count}] = {{0}};\n'
        f'    for (int s = 0; s < {count}; ++s) for (int b = 0; b < 256; ++b) counts[s] += banked_seen[s][b];\n'
        '    fprintf(stderr, "[banked] native_steps=%llu halt_steps=%llu fallback_steps=%llu banks_seen='
        + '/'.join(['%u'] * count) + '\\n",\n'
        '        (unsigned long long)banked_native_steps, (unsigned long long)banked_halt_steps,\n'
        '        (unsigned long long)banked_fallback_steps, '
        + ', '.join(f'counts[{slot}]' for slot in range(count)) + ');\n',
    )


# The Sega mapper of the Master System and the Game Gear: three 16 KiB slots (registers $FFFD-$FFFF), a first KiB that
# never pages, RAM from $C000, no wait state, /INT latched at the start of a step. native/banked_runtime.inc is written
# with these values; the two profiles name this machine (`z80_machine`).
SEGA_MAPPER = Z80Machine('sega', Z80Regions(slot_bits=14, slots=3, fixed_bytes=0x400, ram_from=0xC000, bank_values=256,
                                            scope='master-system-sega-mapper'))


def runtime_source(machine: Z80Machine, runtime: str) -> str:
    """The step loop for one machine.

    `runtime` is the text of native/banked_runtime.inc, written with the values of `SEGA_MAPPER`. Each line that depends on
    the machine is found in it as the Sega mapper renders it, exactly once, and replaced by this machine's: for the Sega
    mapper the result is the file itself, byte for byte, and a line edited in the file without this module following
    raises instead of being left as it is."""
    for old, new in zip(_runtime_parts(SEGA_MAPPER), _runtime_parts(machine)):
        runtime = _once(runtime, old, new)
    return runtime


def banked_emitter(machine: Z80Machine, assets: Path) -> str:
    """native/banked_emitter.inc for one machine (`assets` is the bundle root, retrorecomp.paths.ASSETS)."""
    return emitter_source(machine, (assets / 'native/banked_emitter.inc').read_text(encoding='utf-8'))


def banked_runtime(machine: Z80Machine, assets: Path) -> str:
    """native/banked_runtime.inc for one machine."""
    return runtime_source(machine, (assets / 'native/banked_runtime.inc').read_text(encoding='utf-8'))
