"""Super FX (GSU) instruction decoder and static code traversal.

Groundwork for "option B" of docs/SNES_SUPERFX.md (static recompilation of GSU
code). Nothing here is used by the conversion path yet: it decodes bytes the way
the chip does and walks GSU programs from known entry points so that coverage,
indirect control flow and prefix-state variety can be measured.

Instruction semantics follow the public documentation of the chip (nocash
fullsnes, "SNES Cart GSU"). The few points the documentation leaves open (ALT3
forms, the value a read of R15 yields, how the delay slot and the pipeline
interact, what STOP leaves behind) were taken from the behaviour of the pinned
engine's GSU core (`superfx.c`, adapted from the ISC-licensed ares) and checked
against dumps of every instruction that core executed in the eight local Super
FX cartridges (tools/snes_gsu_survey.py). No GPL code was read or copied.

What the decoder models
-----------------------
* Prefix state.  ALT1/ALT2/ALT3 set the two ALT bits and clear B; WITH Rn sets B
  and both register selectors; TO/FROM set only the destination/source selector
  unless B is set (then they are MOVE/MOVES and consume the prefix).  Every other
  instruction except the relative branches consumes (clears) the whole state.  A
  decoded instruction is therefore keyed by (PC, state) with state =
  (alt, b, sreg, dreg), not by PC alone.
* Operand lengths: IBT/LMS/SMS and branches take one byte, IWT/LM/SM two.
* Delay slot: after every branch, JMP, LJMP, LOOP and every instruction that
  writes R15 the next instruction in memory still executes before the transfer.
  When that instruction has operand bytes the pipeline takes them from the path
  actually followed (the target if the transfer is taken), so `BEQ x ; IWT R15,#a`
  is a two-way dispatch; the traversal models this, including a transfer inside
  the slot of another transfer.
* STOP: the byte after it is consumed by the pipeline, so when the S-CPU sets
  SFR.G again (without writing R15) the chip resumes two bytes after the STOP.
  The engine's job log does not record such resumes; `traverse` can follow them.
* Indirect control flow: JMP/LJMP/LOOP read registers, and any instruction whose
  destination is R15 (IWT R15, MOVE R15, ALU with a R15 destination...) jumps.
  A small constant propagation over IBT/IWT/MOVE/LINK/INC/DEC/ADD#/SUB# resolves
  the usual idioms (JMP after IWT, LOOP after MOVE R13,R15, return through R11
  set by LINK); the rest is reported as unresolved so that observed targets
  can be added.
* Code addresses: the chip fetches banks $00-$3F through the LoROM view (bit 15
  ignored), banks $40-$5F linearly, and $70-$71 from Game Pak RAM, which static
  code analysis cannot see.
"""
from collections import deque
from dataclasses import dataclass, field

CLEAR = (0, 0, 0, 0)  # (alt, b, sreg, dreg)

BRANCH_NAMES = {0x05: 'BRA', 0x06: 'BGE', 0x07: 'BLT', 0x08: 'BNE', 0x09: 'BEQ',
                0x0a: 'BPL', 0x0b: 'BMI', 0x0c: 'BCC', 0x0d: 'BCS', 0x0e: 'BVC',
                0x0f: 'BVS'}

# Instruction categories used by the measurements.
CATEGORIES = ('plot', 'rpix', 'mult', 'getb', 'load', 'store', 'alu', 'move',
              'prefix', 'branch', 'jump', 'loop', 'misc')

# Tags name the engine services a compiled instruction would still have to call
# so that master-clock totals stay exact (see docs/SNES_SUPERFX.md).
TAG_ROM_BUFFER = 'rom_buffer'    # GETB/GETC and R14 writes (buffer reload, 5/6 clocks)
TAG_ROM_BANK = 'rom_bank'        # ROMB
TAG_RAM_BUFFER = 'ram_buffer'    # loads/stores through the RAM buffer
TAG_RAM_BANK = 'ram_bank'        # RAMB
TAG_PIXEL = 'pixel'              # pixel caches (PLOT, RPIX)
TAG_MULT = 'mult'                # multiplier timing (CFGR MS0, CLSR)
TAG_CACHE = 'cache'              # CBR changes (CACHE, LJMP)

ROM_NOT_FETCHABLE = None


def sext8(value):
    return value - 256 if value & 0x80 else value


def region(pbr):
    """Memory the GSU executes from for a program bank register value."""
    pbr &= 0x7f
    if pbr < 0x40:
        return 'rom-lorom'
    if pbr < 0x60:
        return 'rom-linear'
    if pbr in (0x70, 0x71):
        return 'ram'
    return 'void'


class GsuRom:
    """Cartridge ROM as the GSU's own bus sees it (read-only)."""

    def __init__(self, data):
        self.data = bytes(data)
        size = 1
        while size < max(len(self.data), 1):
            size <<= 1
        self.mask = size - 1

    def read(self, pbr, address):
        """Byte at PBR:address, or None when that is not ROM."""
        pbr &= 0x7f
        address &= 0xffff
        if pbr < 0x40:
            offset = ((pbr << 15) | (address & 0x7fff)) & self.mask
        elif pbr < 0x60:
            offset = ((pbr << 16) | address) & self.mask
        else:
            return ROM_NOT_FETCHABLE
        return self.data[offset] if offset < len(self.data) else ROM_NOT_FETCHABLE


def _next_state(op, state):
    alt, b, sreg, dreg = state
    if op == 0x3d:
        return (alt | 1, 0, sreg, dreg)
    if op == 0x3e:
        return (alt | 2, 0, sreg, dreg)
    if op == 0x3f:
        return (3, 0, sreg, dreg)
    if 0x10 <= op <= 0x1f:
        return (alt, b, sreg, op & 15) if not b else CLEAR
    if 0x20 <= op <= 0x2f:
        return (alt, 1, op & 15, op & 15)
    if 0xb0 <= op <= 0xbf:
        return (alt, b, op & 15, dreg) if not b else CLEAR
    if 0x05 <= op <= 0x0f:
        return state
    return CLEAR


@dataclass(frozen=True)
class Instr:
    pbr: int
    pc: int
    op: int
    state: tuple
    length: int
    mnemonic: str
    operand: object
    flow: str            # seq stop branch jmp ljmp loop r15
    category: str
    reads: tuple
    writes: tuple
    tags: frozenset
    next_state: tuple
    r15_imm: object = None   # target when the R15 write comes from an immediate
    raw: tuple = ()          # operand bytes as decoded

    @property
    def address(self):
        return (self.pbr << 16) | self.pc

    @property
    def conditional(self):
        return (self.flow == 'branch' and self.op != 0x05) or self.flow == 'loop'

    @property
    def transfers(self):
        return self.flow not in ('seq', 'stop')


def _spec(op, alt, b, sreg, dreg):
    """(mnemonic template, operand bytes, category, reads, writes, tags, flow).

    `reads`/`writes` are register numbers; R15 appears in `writes` only when the
    instruction transfers control through it.
    """
    n = op & 15
    a1, a2 = bool(alt & 1), bool(alt & 2)
    ALU = 'alu'
    if op == 0x00:
        return 'STOP', 0, 'misc', (), (), (), 'stop'
    if op == 0x01:
        return 'NOP', 0, 'misc', (), (), (), 'seq'
    if op == 0x02:
        return 'CACHE', 0, 'misc', (), (), (TAG_CACHE,), 'seq'
    if op == 0x03:
        return 'LSR', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op == 0x04:
        return 'ROL', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op in BRANCH_NAMES:
        return BRANCH_NAMES[op] + ' ${t:04X}', 1, 'branch', (), (), (), 'branch'
    if 0x10 <= op <= 0x1f:
        if b:
            return f'MOVE R{n},R{sreg}', 0, 'move', (sreg,), (n,), (), 'seq'
        return f'TO R{n}', 0, 'prefix', (), (), (), 'seq'
    if 0x20 <= op <= 0x2f:
        return f'WITH R{n}', 0, 'prefix', (), (), (), 'seq'
    if 0x30 <= op <= 0x3b:
        name = 'STB' if a1 else 'STW'
        return f'{name} (R{n})', 0, 'store', (n, sreg), (), (TAG_RAM_BUFFER,), 'seq'
    if op == 0x3c:
        return 'LOOP', 0, 'loop', (12, 13), (12, 15), (), 'loop'
    if op in (0x3d, 0x3e, 0x3f):
        return f'ALT{op - 0x3c}', 0, 'prefix', (), (), (), 'seq'
    if 0x40 <= op <= 0x4b:
        name = 'LDB' if a1 else 'LDW'
        return f'{name} (R{n})', 0, 'load', (n,), (dreg,), (TAG_RAM_BUFFER,), 'seq'
    if op == 0x4c:
        if a1:
            return 'RPIX', 0, 'rpix', (1, 2), (dreg,), (TAG_PIXEL,), 'seq'
        return 'PLOT', 0, 'plot', (1, 2), (1,), (TAG_PIXEL,), 'seq'
    if op == 0x4d:
        return 'SWAP', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op == 0x4e:
        return ('CMODE' if a1 else 'COLOR'), 0, 'misc', (sreg,), (), (), 'seq'
    if op == 0x4f:
        return 'NOT', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if 0x50 <= op <= 0x5f:
        name = ('ADD', 'ADC', 'ADD', 'ADC')[alt]
        if a2:
            return f'{name} #{n}', 0, ALU, (sreg,), (dreg,), (), 'seq'
        return f'{name} R{n}', 0, ALU, (sreg, n), (dreg,), (), 'seq'
    if 0x60 <= op <= 0x6f:
        if alt == 2:
            return f'SUB #{n}', 0, ALU, (sreg,), (dreg,), (), 'seq'
        if alt == 3:
            return f'CMP R{n}', 0, ALU, (sreg, n), (), (), 'seq'
        return f'{"SBC" if alt == 1 else "SUB"} R{n}', 0, ALU, (sreg, n), (dreg,), (), 'seq'
    if op == 0x70:
        return 'MERGE', 0, ALU, (7, 8), (dreg,), (), 'seq'
    if 0x71 <= op <= 0x7f:
        name = 'BIC' if a1 else 'AND'
        if a2:
            return f'{name} #{n}', 0, ALU, (sreg,), (dreg,), (), 'seq'
        return f'{name} R{n}', 0, ALU, (sreg, n), (dreg,), (), 'seq'
    if 0x80 <= op <= 0x8f:
        name = 'UMULT' if a1 else 'MULT'
        if a2:
            return f'{name} #{n}', 0, 'mult', (sreg,), (dreg,), (TAG_MULT,), 'seq'
        return f'{name} R{n}', 0, 'mult', (sreg, n), (dreg,), (TAG_MULT,), 'seq'
    if op == 0x90:
        return 'SBK', 0, 'store', (sreg,), (), (TAG_RAM_BUFFER,), 'seq'
    if 0x91 <= op <= 0x94:
        return f'LINK #{n}', 0, 'move', (), (11,), (), 'seq'
    if op == 0x95:
        return 'SEX', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op == 0x96:
        return ('DIV2' if a1 else 'ASR'), 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op == 0x97:
        return 'ROR', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if 0x98 <= op <= 0x9d:
        if a1:
            return f'LJMP R{n}', 0, 'jump', (n, sreg), (15,), (TAG_CACHE,), 'ljmp'
        return f'JMP R{n}', 0, 'jump', (n,), (15,), (), 'jmp'
    if op == 0x9e:
        return 'LOB', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if op == 0x9f:
        if a1:
            return 'LMULT', 0, 'mult', (sreg, 6), (dreg, 4), (TAG_MULT,), 'seq'
        return 'FMULT', 0, 'mult', (sreg, 6), (dreg,), (TAG_MULT,), 'seq'
    if 0xa0 <= op <= 0xaf:
        if a1:
            return f'LMS R{n},(${{m:03X}})', 1, 'load', (), (n,), (TAG_RAM_BUFFER,), 'seq'
        if a2:
            return f'SMS (${{m:03X}}),R{n}', 1, 'store', (n,), (), (TAG_RAM_BUFFER,), 'seq'
        return f'IBT R{n},#{{i}}', 1, 'move', (), (n,), (), 'seq'
    if 0xb0 <= op <= 0xbf:
        if b:
            return f'MOVES R{dreg},R{n}', 0, 'move', (n,), (dreg,), (), 'seq'
        return f'FROM R{n}', 0, 'prefix', (), (), (), 'seq'
    if op == 0xc0:
        return 'HIB', 0, ALU, (sreg,), (dreg,), (), 'seq'
    if 0xc1 <= op <= 0xcf:
        name = 'XOR' if a1 else 'OR'
        if a2:
            return f'{name} #{n}', 0, ALU, (sreg,), (dreg,), (), 'seq'
        return f'{name} R{n}', 0, ALU, (sreg, n), (dreg,), (), 'seq'
    if 0xd0 <= op <= 0xde:
        return f'INC R{n}', 0, ALU, (n,), (n,), (), 'seq'
    if op == 0xdf:
        if alt == 2:
            return 'RAMB', 0, 'misc', (sreg,), (), (TAG_RAM_BANK,), 'seq'
        if alt == 3:
            return 'ROMB', 0, 'misc', (sreg,), (), (TAG_ROM_BANK,), 'seq'
        return 'GETC', 0, 'getb', (), (), (TAG_ROM_BUFFER,), 'seq'
    if 0xe0 <= op <= 0xee:
        return f'DEC R{n}', 0, ALU, (n,), (n,), (), 'seq'
    if op == 0xef:
        name = ('GETB', 'GETBH', 'GETBL', 'GETBS')[alt]
        reads = (sreg,) if alt in (1, 2) else ()
        return name, 0, 'getb', reads, (dreg,), (TAG_ROM_BUFFER,), 'seq'
    # 0xf0-0xff
    if a1:
        return f'LM R{n},(${{a:04X}})', 2, 'load', (), (n,), (TAG_RAM_BUFFER,), 'seq'
    if a2:
        return f'SM (${{a:04X}}),R{n}', 2, 'store', (n,), (), (TAG_RAM_BUFFER,), 'seq'
    return f'IWT R{n},#${{i:04X}}', 2, 'move', (), (n,), (), 'seq'


def decode_bytes(op, operands, pbr, pc, state=CLEAR):
    """Decode opcode `op` with `operands` (bytes that follow it) at PBR:PC.

    `operands` may be longer than needed; missing bytes read as zero.
    """
    alt, b, sreg, dreg = state
    template, nbytes, category, reads, writes, tags, flow = _spec(op, alt, b, sreg, dreg)
    raw = list(operands[:nbytes]) + [0] * (nbytes - len(operands))
    operand = None
    r15_imm = None
    text = template
    if 0x05 <= op <= 0x0f:
        disp = sext8(raw[0])
        operand = (pc + 2 + disp) & 0xffff      # target, relative to the delay slot
        text = template.format(t=operand)
    elif 0xa0 <= op <= 0xaf:
        n = op & 15
        if alt & 1 or alt & 2:
            operand = raw[0] << 1
            text = template.format(m=operand)
        else:
            operand = sext8(raw[0]) & 0xffff
            text = template.format(i=f'${operand:04X}' if operand >= 0x8000 else f'{operand}')
            if n == 15:
                r15_imm = operand
    elif op >= 0xf0:
        operand = raw[0] | (raw[1] << 8)
        text = template.format(a=operand, i=operand)
        if not (alt & 3) and (op & 15) == 15:
            r15_imm = operand
    # Any instruction whose destination is R15 transfers control through it.
    if flow == 'seq' and 15 in writes:
        flow = 'r15'
    # Writing R14 (directly or as a destination) reloads the ROM buffer.
    if 14 in writes and TAG_ROM_BUFFER not in tags:
        tags = tuple(tags) + (TAG_ROM_BUFFER,)
    return Instr(pbr & 0x7f, pc & 0xffff, op, state, 1 + nbytes, text, operand, flow,
                 category, tuple(reads), tuple(writes), frozenset(tags),
                 _next_state(op, state), r15_imm, tuple(raw))


def decode(rom, pbr, pc, state=CLEAR):
    """Decode the instruction at PBR:PC, or None when that byte is not ROM."""
    op = rom.read(pbr, pc)
    if op is None:
        return None
    operands = []
    for k in (1, 2):
        value = rom.read(pbr, pc + k)
        operands.append(0 if value is None else value)
    return decode_bytes(op, operands, pbr, pc, state)


# --- static traversal --------------------------------------------------------

MAX_CONSTANTS = 6
# A node whose constants keep changing after this many visits is widened to "nothing known".
MAX_VISITS = 6


def _merge(a, b):
    """Join two constant maps (register -> frozenset of values)."""
    out = {}
    for reg, values in a.items():
        other = b.get(reg)
        if other is None:
            continue
        joined = values | other
        if len(joined) <= MAX_CONSTANTS:
            out[reg] = joined
    return out


def _transfer(instr, consts):
    """Constant map after `instr` (a fresh dict)."""
    out = dict(consts)
    op, n = instr.op, instr.op & 15
    state = instr.state
    sreg, dreg = state[2], state[3]
    alt = state[0]
    value = None   # frozenset when the instruction yields a known destination

    def source(reg):
        if reg == 15:
            return frozenset({(instr.pc + 1) & 0xffff})
        return consts.get(reg)

    dest = None
    if 0xa0 <= op <= 0xaf and not alt and instr.operand is not None:
        dest, value = n, frozenset({instr.operand})
    elif op >= 0xf0 and not alt:
        dest, value = n, frozenset({instr.operand})
    elif 0x10 <= op <= 0x1f and state[1]:
        dest, value = n, source(sreg)
    elif 0xb0 <= op <= 0xbf and state[1]:
        dest, value = dreg, source(n)
    elif 0x91 <= op <= 0x94:
        dest, value = 11, frozenset({(instr.pc + 1 + n) & 0xffff})
    elif 0xd0 <= op <= 0xde:
        cur = consts.get(n)
        dest, value = n, (frozenset((v + 1) & 0xffff for v in cur) if cur else None)
    elif 0xe0 <= op <= 0xee:
        cur = consts.get(n)
        dest, value = n, (frozenset((v - 1) & 0xffff for v in cur) if cur else None)
    elif 0x50 <= op <= 0x5f and alt == 2:
        cur = source(sreg)
        dest, value = dreg, (frozenset((v + n) & 0xffff for v in cur) if cur else None)
    elif 0x60 <= op <= 0x6f and alt == 2:
        cur = source(sreg)
        dest, value = dreg, (frozenset((v - n) & 0xffff for v in cur) if cur else None)
    if dest is not None:
        for reg in instr.writes:
            if reg != dest:
                out.pop(reg, None)
        if value and dest != 15:
            out[dest] = value
        else:
            out.pop(dest, None)
        return out
    for reg in instr.writes:
        out.pop(reg, None)
    return out


@dataclass
class IndirectSite:
    pbr: int
    pc: int
    kind: str                     # jmp ljmp loop r15
    static_targets: set = field(default_factory=set)    # {(pbr, pc)}
    observed_targets: set = field(default_factory=set)

    @property
    def resolved(self):
        return bool(self.static_targets)


@dataclass
class Traversal:
    nodes: dict = field(default_factory=dict)       # (pbr, pc, state) -> Instr
    slots: set = field(default_factory=set)         # node keys reached as delay slots
    entries: list = field(default_factory=list)
    indirect: dict = field(default_factory=dict)    # (pbr, pc) -> IndirectSite
    anomalies: list = field(default_factory=list)   # (pbr, pc, text)
    not_rom: dict = field(default_factory=dict)     # (pbr, pc) -> region name
    slot_operand_sites: set = field(default_factory=set)  # delay slots holding multi-byte instructions
    edges: set = field(default_factory=set)         # ((pbr, pc), (pbr, pc)) between executed instructions
    resume_points: set = field(default_factory=set)  # (pbr, pc) two bytes after each STOP reached
    truncated: bool = False

    def addresses(self):
        return {(k[0], k[1]) for k in self.nodes}

    def prefix_states_per_address(self):
        table = {}
        for pbr, pc, state in self.nodes:
            table.setdefault((pbr, pc), set()).add(state)
        return table

    def unresolved(self):
        return [site for site in self.indirect.values() if not site.resolved]


MAX_SLOT_DEPTH = 3


def traverse(rom, entries, observed=None, max_nodes=2_000_000, resume_after_stop=False):
    """Walk GSU code from `entries` (iterable of (pbr, r15) or (pbr, r15, state)).

    `observed` maps (pbr, pc of an indirect control instruction) to the targets
    seen when it ran, as (pbr, pc) pairs; they are followed like static targets
    but kept apart in `IndirectSite.observed_targets`.

    With `resume_after_stop`, execution continues two bytes after every `STOP ; NOP`:
    the S-CPU can set SFR.G again without writing R15, and the chip then resumes at
    R15, which already points past the byte that follows the STOP.

    Delay slots follow the chip's pipeline: the instruction after a transfer
    always runs, and when it has operand bytes they are the first bytes of the
    path taken (the target if the transfer is taken, the next bytes otherwise).
    `BEQ x ; IWT R15,#a` is therefore a two-way dispatch: not taken, the IWT jumps
    to `a`; taken, the IWT takes its address from the bytes at the branch target.
    """
    observed = observed or {}
    result = Traversal()
    consts_at = {}
    visits = {}
    queue = deque()

    def push(key, consts):
        old = consts_at.get(key)
        if old is None:
            consts_at[key] = consts
            queue.append(key)
            return
        merged = _merge(old, consts)
        if merged != old:
            visits[key] = visits.get(key, 0) + 1
            if visits[key] > MAX_VISITS:
                merged = {}
            if merged != old:
                consts_at[key] = merged
                queue.append(key)

    for entry in entries:
        pbr, pc = entry[0] & 0x7f, entry[1] & 0xffff
        state = entry[2] if len(entry) > 2 else CLEAR
        result.entries.append((pbr, pc))
        push((pbr, pc, state), {})

    def node(pbr, pc, state):
        key = (pbr, pc, state)
        found = result.nodes.get(key)
        if found is None:
            found = decode(rom, pbr, pc, state)
            if found is None:
                result.not_rom[(pbr, pc)] = region(pbr)
                return None
            result.nodes[key] = found
        return found

    def site(instr, kind, pc):
        found = result.indirect.get((instr.pbr, pc))
        if found is None:
            found = result.indirect[(instr.pbr, pc)] = IndirectSite(instr.pbr, pc, kind)
        return found

    def targets_of(instr, consts, pc, after_operands):
        """Targets of a transfer executed at `pc` whose delay slot is at `after_operands`."""
        pbr, state = instr.pbr, instr.state
        flow = instr.flow
        if flow == 'branch':
            return [(pbr, (after_operands + sext8(instr.raw[0] if instr.raw else 0)) & 0xffff)]
        record = site(instr, flow, pc)
        found = []
        if flow == 'jmp':
            found = [(pbr, v) for v in consts.get(instr.op & 15, ())]
        elif flow == 'ljmp':
            banks, values = consts.get(instr.op & 15), consts.get(state[2])
            if banks and values:
                found = [(b & 0x7f, v) for b in banks for v in values]
        elif flow == 'loop':
            found = [(pbr, v) for v in consts.get(13, ())]
        elif instr.r15_imm is not None:
            found = [(pbr, instr.r15_imm)]
        else:
            sources = None
            if 0x10 <= instr.op <= 0x1f and state[1]:
                sources = consts.get(state[2]) if state[2] != 15 else None
            elif 0xb0 <= instr.op <= 0xbf and state[1]:
                sources = consts.get(instr.op & 15)
            found = [(pbr, v) for v in sources or ()]
        record.static_targets.update(found)
        extra = observed.get((pbr, pc), ())
        record.observed_targets.update(extra)
        return found + list(extra)

    def follow(instr, pc, after_operands, consts, depth):
        """Successors of `instr` (running at `pc`, next stream byte `after_operands`)."""
        after = _transfer(instr, consts)
        flow = instr.flow
        if flow == 'stop':
            if resume_after_stop and not depth and rom.read(instr.pbr, pc + 1) == 0x01:
                resume = (instr.pbr, (pc + 2) & 0xffff)
                result.resume_points.add(resume)
                result.edges.add(((instr.pbr, pc), resume))
                push((resume[0], resume[1], CLEAR), {})
            return
        if flow == 'seq':
            result.edges.add(((instr.pbr, pc), (instr.pbr, after_operands)))
            push((instr.pbr, after_operands, instr.next_state), after)
            return
        if depth >= MAX_SLOT_DEPTH:
            result.anomalies.append((instr.pbr, pc, 'transfer nested too deep in delay slots'))
            return
        slot_pc = after_operands
        slot = node(instr.pbr, slot_pc, instr.next_state)
        if slot is None:
            return
        result.slots.add((instr.pbr, slot_pc, instr.next_state))
        result.edges.add(((instr.pbr, pc), (instr.pbr, slot_pc)))
        paths = [(target, True) for target in set(targets_of(instr, consts, pc, after_operands))]
        if instr.conditional:
            paths.append(((instr.pbr, (slot_pc + 1) & 0xffff), False))
        for (tpbr, position), taken in paths:
            tpbr &= 0x7f
            virtual = slot
            if slot.length > 1:
                result.slot_operand_sites.add((slot.pbr, slot.pc))
                if taken:
                    operands = [rom.read(tpbr, position + k) or 0 for k in range(slot.length - 1)]
                    virtual = decode_bytes(slot.op, operands, slot.pbr, slot.pc, slot.state)
            nxt = (position + slot.length - 1) & 0xffff
            if virtual.flow == 'stop':
                continue
            if virtual.flow == 'seq':
                result.edges.add(((instr.pbr, slot_pc), (tpbr, nxt)))
                push((tpbr, nxt, virtual.next_state), _transfer(virtual, after))
                continue
            # A transfer in the delay slot of a transfer: its own slot is the byte at `nxt`.
            if tpbr != instr.pbr:
                inner = decode_bytes(virtual.op, virtual.raw, tpbr, virtual.pc, virtual.state)
            else:
                inner = virtual
            follow(inner, slot_pc, nxt, after, depth + 1)

    while queue:
        if len(result.nodes) > max_nodes:
            result.truncated = True
            break
        key = queue.popleft()
        consts = consts_at[key]
        pbr, pc, state = key
        instr = node(pbr, pc, state)
        if instr is None:
            continue
        follow(instr, pc, (pc + instr.length) & 0xffff, consts, 0)
    return result


def covered_counts(traversal, executed):
    """Split dynamic counts into covered/uncovered by a traversal.

    `executed` yields (pbr, pc, state, count).  Returns a dict with the counts
    of instructions and of distinct (pc, state) pairs covered at the address
    level, at the (address, state) level, and not at all.
    """
    addresses = traversal.addresses()
    out = {'instr_total': 0, 'instr_address': 0, 'instr_state': 0,
           'keys_total': 0, 'keys_address': 0, 'keys_state': 0}
    for pbr, pc, state, count in executed:
        out['instr_total'] += count
        out['keys_total'] += 1
        if (pbr, pc) in addresses:
            out['instr_address'] += count
            out['keys_address'] += 1
        if (pbr, pc, tuple(state)) in traversal.nodes:
            out['instr_state'] += count
            out['keys_state'] += 1
    return out
