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
  firmware) or RAM, and the map changes at run time; a position is keyed by (source, bank, offset). No machine of the
  converter uses it yet. Such a machine has its own front end in the generator (`generator_main`):
  its sources are read as they are and padded to whole regions, never through the Sega cartridge parser.

What a machine without the Sega runner asks of the step loop is data too: a call at the start of every step
(`step_begin`), the hardware left alone inside a chain of redundant prefixes (`irq_sample='instruction_end'`) and the
copies between the translated register file and the reference CPU of the fallback (`reference_state`,
native/banked_reference_state.inc). The Sega mapper asks for none: its loop is native/banked_runtime.inc itself.
A machine with a /NMI pin (`nmi`) gets the check of an edge at the end of every instruction and the chain's one `banked_accept_nmi`.

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
    next region is checked against the bytes it reads there. A region that shows a source may also name one window of
    offsets, `guard_from` to `guard_to` (excluded), where something else answers (a sound chip in front of the ROM): only
    the instructions that read a byte of the window run through the byte guards, the rest of the region stays keyed."""
    # log2 of the size of one region (13: eight regions of 8 KiB).
    region_bits: int
    # The sources a region can show, in the order of the map's `source` numbers. The first is the cartridge of game.toml;
    # the generator reads the others from the files `banked.sources` names beside it, one per line, in this order.
    # Every source is read whole, nothing stripped, and padded with FFh to whole regions (`image`).
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

    def image(self, data: bytes, regions_per_bank: int = 1) -> bytes:
        """A source as the generator translates it: the bytes as they are, padded with FFh to whole regions. A mapper
        whose banks span several regions (16 KiB banks over 8 KiB regions: 2) pads to its own bank, and gives the
        generator that image, so that both take the same mirror of a short image."""
        if not data or regions_per_bank < 1:
            raise ValueError('Z80 region map: a source has at least one byte, a bank at least one region.')
        return data + b'\xFF' * (-len(data) % (regions_per_bank << self.region_bits))

    def initialiser(self) -> str:
        return (f'.mapped = 1, .slot_bits = {self.region_bits}, .slots = {self.regions}, .fixed_bytes = 0x0, '
                f'.ram_from = 0x10000, .sources = {len(self.sources)}, .bank_values = {self.bank_values}')


# When the step loop reads the /INT level of an instruction it will accept the interrupt after.
IRQ_SAMPLES = ('step_start', 'instruction_end')

# The encoding groups of the Z80, as `Z80Costs.base` names them: no prefix, CB, DD, FD, ED, DD CB d and FD CB d (the opcode of
# the last two is the byte after the displacement).
COST_GROUPS = ('', 'cb', 'dd', 'fd', 'ed', 'ddcb', 'fdcb')


@dataclass(frozen=True)
class Z80Costs:
    """The T-states of each instruction on a machine whose bus stretches the Z80's own, as a static table.

    The Amstrad CPC is the case: its gate array lets the CPU touch the bus only once per microsecond (4 T-states), so every
    instruction takes a whole number of microseconds, which a table per encoding states. Every value is in T-states, before the
    machine's M1 wait states (`Z80Machine.m1_wait`), and the defaults are the Z80's own: `Z80Costs()` changes nothing.

    `base` replaces the Z80's own count of some encodings: (group of COST_GROUPS, opcode, T-states). A conditional branch keeps
    its base when it is not taken and adds its `*_taken` extra when it is (JR cc and DJNZ, RET cc, CALL cc; JP cc has none,
    and the same with a DD or FD prefix before them); a repeating block instruction (LDIR, CPIR, INIR, OTIR and their
    decrementing forms) adds `repeat` each time it goes round again, CPIR and CPDR `repeat_compare` (the CPC counts 8 T there and 4 T
    for the others; None: the same as `repeat`). `irq` and `irq_im2` are the acceptance of /INT (modes 0 and
    1, mode 2), `nmi` the acceptance of /NMI, `halt` one cycle of a HALT, `fragment` a redundant DD or FD prefix. The emitter
    (`emitter_source`), the step loop (`runtime_source`) and the reference CPU of the counted fallback
    (`cpu.prepare_reference(costs=...)`) all read the same values; tools/z80_costs_selftest.py checks that they agree."""
    base: tuple[tuple[str, int, int], ...] = ()
    jr_taken: int = 5
    djnz_taken: int = 5
    ret_taken: int = 6
    call_taken: int = 7
    repeat: int = 5
    repeat_compare: int | None = None
    irq: int = 13
    irq_im2: int = 19
    nmi: int = 11
    halt: int = 4
    fragment: int = 4

    def __post_init__(self):
        seen = set()
        for entry in self.base:
            if not isinstance(entry, tuple) or len(entry) != 3:
                raise ValueError('Z80 costs: a base entry is (group, opcode, T-states).')
            group, opcode, states = entry
            if group not in COST_GROUPS or not (isinstance(opcode, int) and 0 <= opcode <= 255):
                raise ValueError(f'Z80 costs: unknown encoding {entry!r}.')
            if not (isinstance(states, int) and 1 <= states <= 255):
                raise ValueError(f'Z80 costs: {entry!r} must cost 1 to 255 T-states.')
            if (group, opcode) in seen:
                raise ValueError(f'Z80 costs: {group or "unprefixed"} {opcode:02X}h is given twice.')
            seen.add((group, opcode))
        for name in ('jr_taken', 'djnz_taken', 'ret_taken', 'call_taken', 'repeat', 'irq_im2', 'nmi', 'halt', 'fragment'):
            value = getattr(self, name)
            if not (isinstance(value, int) and 0 <= value <= 255):
                raise ValueError(f'Z80 costs: {name} is 0 to 255 T-states.')
        if self.repeat_compare is not None and not (isinstance(self.repeat_compare, int) and 0 <= self.repeat_compare <= 255):
            raise ValueError('Z80 costs: repeat_compare is None or 0 to 255 T-states.')
        # Mode 0 runs the RST 38h the floating bus gives: the reference CPU adds the RST's own 11 T-states to the acceptance.
        if not (isinstance(self.irq, int) and 11 <= self.irq <= 255):
            raise ValueError('Z80 costs: irq is 11 to 255 T-states (mode 0 runs RST 38h, 11 of them).')

    @property
    def compare_repeat(self) -> int:
        """What a repeating CPIR or CPDR adds each time it goes round again."""
        return self.repeat if self.repeat_compare is None else self.repeat_compare

    @property
    def table(self) -> list[list[int]]:
        """The base costs as seven rows of 256 (COST_GROUPS order), 0 where the Z80's own count stands."""
        rows = [[0] * 256 for _ in COST_GROUPS]
        for group, opcode, states in self.base:
            rows[COST_GROUPS.index(group)][opcode] = states
        return rows

    def c_table(self, name: str) -> str:
        """The base costs as a C array of that shape, for the emitter and the reference CPU alike."""
        rows = ['    {' + ','.join(str(value) for value in row) + '}' for row in self.table]
        return f'static const unsigned char {name}[7][256] = {{\n' + ',\n'.join(rows) + '\n};\n'


# The Z80's own counts: what a machine without a table of its own runs on.
Z80_COSTS = Z80Costs()


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
    # CPU). 'instruction_end': it is read after the instruction, once the hardware has caught up with it; the hardware
    # then follows whole instructions, so a redundant prefix (a fragment of the instruction it precedes) does not advance
    # it, where the Sega runner advances it on every fragment (`advances_in_prefixes`).
    irq_sample: str = 'step_start'
    # The loop calls `smsrecomp_step_begin(prefix_pending)` at the start of every step, HALT cycles included, after
    # SMS_PC: 0 when an instruction starts, 1 when the step goes on inside a chain of redundant prefixes. The machine's
    # glue defines it (a function or a macro) before the loop. Off: no call is written at all.
    step_begin: bool = False
    # The loop comes with `state_to_hz` / `state_from_hz` (native/banked_reference_state.inc), the copies between the
    # translated register file and the reference CPU of the counted fallback. Off for the Sega mapper, whose pinned
    # runner defines its own pair in the glue the loop is appended to.
    reference_state: bool = False
    # Suffix of the folders where the machine's own build of the generator lives (.deps/recompiler-src<tag>,
    # .deps/recompiler-build<tag>...). Empty for the Sega mapper, whose folders predate it; another machine names its own, so
    # that two machines never rebuild each other's generator.
    generator_tag: str = ''
    # The machine has a /NMI input (the ColecoVision's VDP, the SG-1000's pause button). The loop then asks the machine's glue,
    # at the end of every instruction once the hardware has caught up, whether a falling edge of /NMI is waiting
    # (`banked_nmi_edge()`: nonzero once per edge, consuming it) and, if so, accepts it (`banked_accept_nmi`) instead of /INT:
    # the NMI is never masked, not even by EI's one-instruction delay, and has priority. Off: no byte of the text changes.
    nmi: bool = False
    # The T-states of each instruction when the machine's bus stretches the Z80's own (Z80Costs: the Amstrad CPC's whole
    # microseconds). None: the Z80's own counts, and no byte of the text changes.
    costs: Z80Costs | None = None
    # The width of a port on the machine's bus: 8 (the Master System, the Game Gear, the MSX: the low byte decodes everything) or 16
    # (the ZX Spectrum and the Amstrad CPC decode the high byte too). 16: the bodies and the reference CPU pass the whole address the
    # Z80 puts on the bus, and the glue's bus is `sms_io_in16` / `sms_io_out16`. 8: no byte of the text changes.
    port_bits: int = 8
    # The loop starts from the Z80's documented reset values of AF and SP (FFFFh), as a machine that boots from its ROM does.
    # False for a machine whose program starts from a saved state (a ZX Spectrum snapshot): its glue sets every register before
    # the loop, and the loop keeps them. True: no byte of the text changes.
    reset_registers: bool = True

    def __post_init__(self):
        if not 0 <= self.m1_wait <= 3:
            raise ValueError('Z80 machine: 0 to 3 wait states per M1 cycle.')
        if self.irq_sample not in IRQ_SAMPLES:
            raise ValueError('Z80 machine: /INT is sampled at step_start or at instruction_end.')
        if self.nmi and self.irq_sample != 'instruction_end':
            raise ValueError('Z80 machine: /NMI is read at the end of an instruction, once the hardware has caught up (instruction_end).')
        if self.generator_tag and not (self.generator_tag.startswith('-') and self.generator_tag[1:].isalnum()):
            raise ValueError('Z80 machine: the generator tag is empty or a hyphen and letters or digits.')
        if self.port_bits not in (8, 16):
            raise ValueError('Z80 machine: ports are 8 or 16 bits wide.')
        if self.costs is not None and not isinstance(self.costs, Z80Costs):
            raise ValueError('Z80 machine: costs is a Z80Costs or None.')

    @property
    def cost(self) -> Z80Costs:
        """The machine's instruction costs, the Z80's own when it states none."""
        return self.costs or Z80_COSTS

    @property
    def mapped(self) -> bool:
        return isinstance(self.regions, Z80RegionMap)

    @property
    def advances_in_prefixes(self) -> bool:
        """The hardware advances on every redundant prefix of a chain (the Sega runner's contract)."""
        return self.irq_sample == 'step_start'

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


def _emitter_cost_lines(costs: Z80Costs) -> tuple[str, ...]:
    """The lines of native/banked_emitter.inc that write a fixed cost (a redundant prefix, the taken branches, a block
    instruction going round again), as `costs` renders them. With the Z80's own counts they are the file's lines byte for byte."""
    return (
        f'        fprintf(o, "    s->pc++; s->r = (s->r & 0x80) | ((s->r + 1) & 0x7F); s->cyc += %d;\\n}}\\n", {costs.fragment} + banked_machine.m1_wait);\n',
        f'        fprintf(o, "    if (%s) {{ s->cyc += {costs.ret_taken}; s->pc = sms_read16(s->sp); s->wz = s->pc; s->sp = (uint16_t)(s->sp + 2); }}\\n", cond((in->opcode >> 3) & 7));\n',
        f'            fprintf(o, "    s->b = (uint8_t)(s->b - 1);\\n    if (s->b) {{ s->cyc += {costs.djnz_taken}; s->pc = %s; s->wz = s->pc; }}\\n", target);\n',
        f'            fprintf(o, "    if (%s) {{ s->cyc += {costs.jr_taken}; s->pc = %s; s->wz = s->pc; }}\\n", cond((in->opcode >> 3) & 3), target);\n',
        f'        fprintf(o, "    s->wz = %s; if (%s) {{ s->cyc += {costs.call_taken}; s->sp = (uint16_t)(s->sp - 2); sms_write16(s->sp, s->pc); s->pc = %s; }}\\n", target, cond((in->opcode >> 3) & 7), target);\n',
        # A repeating CPIR or CPDR (opcode & 3 == 1) adds its own count when the machine gives it one.
        (f'        fprintf(o, "    if (%s) {{ s->cyc += {costs.repeat}; s->pc = (uint16_t)(s->pc - 2);", more);\n'
         if costs.compare_repeat == costs.repeat else
         f'        fprintf(o, "    if (%s) {{ s->cyc += %d; s->pc = (uint16_t)(s->pc - 2);", more, '
         f'(in->opcode & 3) == 1 ? {costs.compare_repeat} : {costs.repeat});\n'),
    )


# The two lines that write an instruction's base count (a block instruction, any other), and the place of the table and its
# lookup in a machine that has one.
_EMITTER_BASE = ('        fprintf(o, "    s->cyc += %d;\\n", 16 + m1 * banked_machine.m1_wait);\n',
                 '        fprintf(o, "    s->cyc += %d;\\n", cyc_base(in) + m1 * banked_machine.m1_wait);\n')
_EMITTER_MACHINE = 'static const BankedMachine banked_machine = BANKED_MACHINE;\n'
_COST_LOOKUP = '''/* The machine's own T-states for some encodings (retrorecomp/z80_chain.py, Z80Costs.base): 0 keeps the Z80's count. The rows
 * are no prefix, CB, DD, FD, ED, DD CB and FD CB, as in cpu.prepare_reference's copy of the same table. */
static int banked_cost(const Z80Insn *in, int own) {
    int row = in->prefix == Z80_PFX_CB ? 1 : in->prefix == Z80_PFX_DD ? 2 : in->prefix == Z80_PFX_FD ? 3 :
        in->prefix == Z80_PFX_ED ? 4 : in->prefix == Z80_PFX_DDCB ? 5 : in->prefix == Z80_PFX_FDCB ? 6 : 0;
    return banked_cost_table[row][in->opcode & 0xFF] ? banked_cost_table[row][in->opcode & 0xFF] : own;
}
'''


def _emitter_costs(machine: Z80Machine, emitter: str) -> str:
    """The emitter with the machine's instruction costs; the text itself, byte for byte, for the Z80's own counts."""
    costs = machine.cost
    for old, new in zip(_emitter_cost_lines(Z80_COSTS), _emitter_cost_lines(costs)):
        emitter = _once(emitter, old, new)
    if costs.base:
        emitter = _once(emitter, _EMITTER_BASE[0], _EMITTER_BASE[0].replace('16 + m1', 'banked_cost(in, 16) + m1'))
        emitter = _once(emitter, _EMITTER_BASE[1], _EMITTER_BASE[1].replace('cyc_base(in) + m1', 'banked_cost(in, cyc_base(in)) + m1'))
        emitter = _once(emitter, _EMITTER_MACHINE, _EMITTER_MACHINE + costs.c_table('banked_cost_table') + _COST_LOOKUP)
    return emitter

# ---- 16-bit ports (Z80Machine.port_bits) ------------------------------------------------------------------------------------
# The pinned emitter names the low byte of a port only: `sms_io_in(0xNN)` and `sms_io_out(0xNN, s->a)` for IN A,(n) and
# OUT (n),A, `sms_io_in(s->c)` and `sms_io_out(s->c, v)` for the (C) and block forms. On the Z80 the address bus carries the whole
# port: A then n for the immediate forms (A as it was before the instruction: the call is made before IN writes A), BC for the
# others (B before its decrement for INI and IND, after it for OUTI and OUTD, which the emitter's order already gives). A machine
# that decodes the high byte (the ZX Spectrum, the Amstrad CPC) asks for 16-bit ports: its generator re-spells each of those four
# shapes in the files of bodies it has just written, and refuses any other spelling of an I/O call, so an emitter change cannot
# slip through. Its bodies call `sms_io_in16` / `sms_io_out16`, which game_banked.h declares (with SMSRECOMP_PORT16) for the
# machine's glue (native/z80_chain_glue.inc) to define. An 8-bit machine renders none of this.
_IO16_REWRITE = r'''/* 16-bit ports (retrorecomp/z80_chain.py, Z80Machine.port_bits): the I/O calls of a file of bodies re-spelled with the whole
 * address on the bus (A and n for IN A,(n) / OUT (n),A, BC for the others); any other spelling is refused. */
static int banked_hex2(const char *p, unsigned *value) {
    unsigned v = 0;
    for (int i = 0; i < 2; ++i) {
        char c = p[i];
        unsigned d = c >= '0' && c <= '9' ? (unsigned)(c - '0') : c >= 'A' && c <= 'F' ? (unsigned)(c - 'A' + 10) : 16;
        if (d > 15) return 0;
        v = v << 4 | d;
    }
    *value = v;
    return 1;
}
static void banked_io16_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "[banked] cannot read %s\n", path); exit(1); }
    fseek(f, 0, SEEK_END); long size = ftell(f); fseek(f, 0, SEEK_SET);
    char *text = (char *)malloc((size_t)size + 1), *out = (char *)malloc((size_t)size * 2 + 64);
    if (!text || !out) exit(1);
    size_t got = fread(text, 1, (size_t)size, f); fclose(f); text[got] = 0;
    char *w = out; const char *r = text;
    while (*r) {
        const char *in = strstr(r, "sms_io_in("), *ot = strstr(r, "sms_io_out(");
        const char *at = in && (!ot || in < ot) ? in : ot;
        if (!at) { size_t n = strlen(r); memcpy(w, r, n); w += n; break; }
        memcpy(w, r, (size_t)(at - r)); w += at - r;
        unsigned port;
        if (at == in && !strncmp(at, "sms_io_in(0x", 12) && banked_hex2(at + 12, &port) && at[14] == ')') {
            w += sprintf(w, "sms_io_in16((uint16_t)(s->a << 8 | 0x%02X))", port); r = at + 15;
        } else if (at == in && !strncmp(at, "sms_io_in(s->c)", 15)) {
            w += sprintf(w, "sms_io_in16(z80_bc(s))"); r = at + 15;
        } else if (at == ot && !strncmp(at, "sms_io_out(0x", 13) && banked_hex2(at + 13, &port) && !strncmp(at + 15, ", ", 2)) {
            w += sprintf(w, "sms_io_out16((uint16_t)(s->a << 8 | 0x%02X), ", port); r = at + 17;
        } else if (at == ot && !strncmp(at, "sms_io_out(s->c, ", 17)) {
            w += sprintf(w, "sms_io_out16(z80_bc(s), "); r = at + 17;
        } else {
            fprintf(stderr, "[banked] an I/O call the 16-bit ports do not know in %s: %.40s\n", path, at); exit(1);
        }
    }
    f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "[banked] cannot write %s\n", path); exit(1); }
    fwrite(out, 1, (size_t)(w - out), f); fclose(f);
    free(text); free(out);
}

'''
_IO16_HEADER = r'''    fprintf(h, "/* 16-bit ports (Z80Machine.port_bits): the machine's glue defines these two, not sms_io_in / sms_io_out. */\n"
        "#define SMSRECOMP_PORT16 1\nuint8_t sms_io_in16(uint16_t port);\nvoid sms_io_out16(uint16_t port, uint8_t value);\n");
'''
_BODIES_HEADER = '    fprintf(h, "#pragma once\\n#include <stddef.h>\\n#include \\"sms_runtime.h\\"\\n#include \\"z80_ops.h\\"\\n");\n'
_BODIES_CLOSE = ('        for (uint32_t id = first; id <= pool->count && id < first+256; ++id) banked_body(o, &pool->ops[id], id);\n'
                 '        fclose(o);\n')
_BODIES_WRITER = '/* game_layout.c, game_banked.h and the native bodies. */\n'


def _emitter_ports(machine: Z80Machine, emitter: str) -> str:
    """The emitter for a machine with 16-bit ports; the text itself, byte for byte, for an 8-bit one."""
    if machine.port_bits == 8:
        return emitter
    emitter = _once(emitter, _BODIES_WRITER, _IO16_REWRITE + _BODIES_WRITER)
    emitter = _once(emitter, _BODIES_HEADER, _BODIES_HEADER + _IO16_HEADER)
    return _once(emitter, _BODIES_CLOSE, _BODIES_CLOSE + '        banked_io16_file(path);\n')


def emitter_source(machine: Z80Machine, emitter: str) -> str:
    """The banked emitter for one machine: its description as a C initialiser, then the emitter that reads it, with the
    machine's own instruction costs (`Z80Machine.costs`) when it states some and its 16-bit ports (`Z80Machine.port_bits`)."""
    return (f'/* The machine this generator is built for (retrorecomp/z80_chain.py, {machine.key}). */\n'
            f'#define BANKED_MACHINE {{ {machine.regions.initialiser()}, .m1_wait = {machine.m1_wait}, '
            f'.scope = "{machine.regions.scope}" }}\n' + _emitter_ports(machine, _emitter_costs(machine, emitter)))


def _once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f'The banked runtime changed; the Z80 chain must follow: {old[:90]!r}')
    return source.replace(old, new, 1)


# The Z80's non-maskable interrupt, written once for every machine that has the pin (`Z80Machine.nmi`). The return address is
# pushed and execution goes on at $0066 (11 T-states, one refresh); IFF1 is cleared and IFF2 keeps what it was, so that RETN
# restores it. EI's pending delay does not hold it back (it only holds back /INT) and it ends a HALT, the PC being the
# instruction after the HALT as for /INT. The Q and P latches are cleared; the parity flag of LD A,I / LD A,R is an /INT
# artefact and is left alone. cpu.prepare_reference(nmi=True) gives the reference CPU the same acceptance.
_NMI_ACCEPT = '''/* The Z80 NMI (retrorecomp/z80_chain.py): the return address is pushed and execution goes on at $0066; IFF1 is cleared, IFF2
 * keeps its value, a HALT ends, and EI's delay does not hold it back. banked_nmi_edge() is the machine's: nonzero once per
 * falling edge of /NMI. */
static void banked_accept_nmi(void) {
    g_z80.p = g_z80.q = 0; g_z80.ei_block = 0;
    g_z80.iff1 = false; g_z80.halted = false;
    g_z80.r = (uint8_t)((g_z80.r & 0x80) | ((g_z80.r + 1) & 0x7F));
    g_z80.cyc += 11;
    g_z80.sp = (uint16_t)(g_z80.sp - 2); sms_write16(g_z80.sp, g_z80.pc);
    g_z80.pc = 0x0066; g_z80.wz = g_z80.pc;
}

'''

def _nmi_accept(costs: Z80Costs) -> str:
    """The chain's NMI acceptance with the machine's count of it (`Z80Costs.nmi`)."""
    return _NMI_ACCEPT.replace('    g_z80.cyc += 11;\n', f'    g_z80.cyc += {costs.nmi};\n', 1)


_AFTER_STEP = 'static inline void banked_after_step(int pending_irq) {'
_RESET_REGISTERS = '    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;\n'
_TAKE_AFTER_STEP = '        banked_after_step(pending_irq);\n'


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
        '        SMS_PC(g_z80.pc);\n' + ('        smsrecomp_step_begin(prefix_pending);\n' if machine.step_begin else ''),
        # A redundant prefix: the Sega runner moves the hardware on every fragment; a machine whose hardware follows
        # whole instructions leaves it where the chain began.
        ("                /* A redundant prefix never completes EI's delay and never\n"
         '                 * accepts an interrupt. Keep hardware time moving even in an\n'
         '                 * endless prefix stream; no host recursion is involved. */\n'
         '                prefix_pending = 1;\n'
         '                banked_advance_vdp(g_z80.cyc); g_sync_deadline = g_next_line_cyc;\n' if machine.advances_in_prefixes else
         "                /* A redundant prefix never completes EI's delay and never accepts an interrupt. The hardware does\n"
         '                 * not move inside the chain: it catches up at the end of the instruction the prefixes precede. */\n'
         '                prefix_pending = 1;\n'),
        # The counted fallback: one instruction on the reference CPU, which knows no wait state. It counts its M1 cycles
        # (cpu.prepare_reference, `m1_counter`) and the machine's wait states are added from that count.
        ('    z80_step(&g_hz);\n' if not machine.m1_wait else
         '    extern unsigned long z80_m1_fetches;\n    unsigned long m1_before = z80_m1_fetches;\n    z80_step(&g_hz);\n'
         f'    g_hz.cyc += {machine.m1_wait} * (z80_m1_fetches - m1_before);   /* the machine\'s wait states, per M1 cycle */\n')
        + '    state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = base + g_hz.cyc;\n',
        seen,
        '        if (!prefix_pending) pending_irq = vdp_irq_asserted();\n' if at_start else '',
        mark,
        f'            g_z80.cyc += {machine.cost.halt + machine.m1_wait}; banked_halt_steps++;\n',
        f'            int step = game_banked_step({key});\n',
        '        prefix_pending = 0; g_frame_ic++;\n' + ('' if at_start else
            '        banked_advance_vdp(g_z80.cyc);   /* the hardware catches up, then /INT is read at the end of the instruction */\n'
            '        pending_irq = vdp_irq_asserted();\n')
        + ('        if (banked_nmi_edge()) banked_accept_nmi(); else banked_after_step(pending_irq);\n' if machine.nmi
           else _TAKE_AFTER_STEP),
        _nmi_accept(machine.cost) + _AFTER_STEP if machine.nmi else _AFTER_STEP,
        # The acceptance of /INT: the machine's counts of modes 0 and 1, and of mode 2.
        f'    g_z80.cyc += g_z80.im == 2 ? {machine.cost.irq_im2} : {machine.cost.irq};\n',
        # The registers the loop starts from: the reset values, or the ones the machine's glue gave (a saved state).
        _RESET_REGISTERS if machine.reset_registers else
        '    /* The machine\'s glue set every register (a saved state, Z80Machine.reset_registers False): kept as they are. */\n',
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


def runtime_source(machine: Z80Machine, runtime: str, reference_state: str = '') -> str:
    """The step loop for one machine.

    `runtime` is the text of native/banked_runtime.inc, written with the values of `SEGA_MAPPER`. Each line that depends on
    the machine is found in it as the Sega mapper renders it, exactly once, and replaced by this machine's: for the Sega
    mapper the result is the file itself, byte for byte, and a line edited in the file without this module following
    raises instead of being left as it is.

    `reference_state` is the text of native/banked_reference_state.inc; a machine that asks for it (`reference_state`)
    gets it ahead of the loop's first function, inside the same `#ifdef`."""
    for old, new in zip(_runtime_parts(SEGA_MAPPER), _runtime_parts(machine)):
        runtime = _once(runtime, old, new)
    if machine.reference_state:
        if 'static void state_to_hz(void)' not in reference_state or 'static void state_from_hz(void)' not in reference_state:
            raise ValueError('The Z80 chain needs native/banked_reference_state.inc for this machine.')
        include = '#include "game_banked.h"\n'
        runtime = _once(runtime, include, include + reference_state)
    return runtime


# The entry point of the pinned generator (main_sms.c) once the converter added `--banked-step` to it (core.dependencies).
_MAIN_BANNER = '    printf("[SmsRecomp] SMS/GG Z80 static recompiler\\n");\n'
_MAIN_PARSE = '    SmsRom rom;\n    if (!rom_parse(rompath, &rom)) return 1;\n'


def generator_main(machine: Z80Machine, main_source: str) -> str:
    """The generator's entry point for one machine.

    The Sega mapper keeps the pinned front end: the result is `main_source` itself. A machine keyed by a region map gets
    its own: with `--banked-step` the cartridge named by game.toml is never given to the Sega parser (which strips 512
    bytes from a file whose size is 512 above a multiple of 16 KiB, looks for the TMR SEGA header and names a Sega
    region and mapper); `cg_emit_banked_mapped` (native/banked_emitter.inc) reads every source itself."""
    if not machine.mapped:
        return main_source
    main_source = _once(main_source, _MAIN_BANNER, '    printf("[banked] Z80 translator of a region-map machine\\n");\n')
    return _once(main_source, _MAIN_PARSE, '''    if (banked_step) {
        /* A machine keyed by a region map (retrorecomp/z80_chain.py) reads its sources itself: whole regions, nothing
         * stripped, no header of another machine looked for. */
        extern int cg_emit_banked_mapped(const char *, const GameConfig *, const char *);
        char dir[260]; dirname_of(game_toml, dir, sizeof(dir));
        char gendir[300]; snprintf(gendir, sizeof(gendir), "%sgenerated", dir);
        return cg_emit_banked_mapped(rompath, &cfg, gendir);
    }
''' + _MAIN_PARSE)


def banked_emitter(machine: Z80Machine, assets: Path) -> str:
    """native/banked_emitter.inc for one machine (`assets` is the bundle root, retrorecomp.paths.ASSETS)."""
    return emitter_source(machine, (assets / 'native/banked_emitter.inc').read_text(encoding='utf-8'))


def banked_runtime(machine: Z80Machine, assets: Path) -> str:
    """native/banked_runtime.inc for one machine (with native/banked_reference_state.inc when the machine asks for it)."""
    state = (assets / 'native/banked_reference_state.inc').read_text(encoding='utf-8') if machine.reference_state else ''
    return runtime_source(machine, (assets / 'native/banked_runtime.inc').read_text(encoding='utf-8'), state)
