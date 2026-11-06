"""Native steps of a PlayStation game from the R3000A code its routes ran (Retro-Recomp's own code, MIT; the C it writes expands
Beetle's handler bodies and is GPL-2.0 like them, inside the GPL-2.0 game).

The conversion's observing build (RR_PSX_OBSERVE, native/psx_machine/psx_observe.c) records each (physical address, word) the
interpreter fetched in main RAM or the BIOS, with whether it was ever reached other than from the instruction before it. This
module turns those records into native steps: runs of consecutive instructions, each a C function holding, per instruction,
the interpreter's own handler body with its word as a constant. The steps are written in slices compiled side by side; each
slice compiles the head of cpu.c (our anchored change: its declarations with the CPU state shared) and calls cpu.c's memory
accessors, exception entry and instruction-cache miss through functions cpu.c exports.

Each step keeps the interpreter's timing and order to the instruction. Between two instructions it does what the interpreter's
loop head does (the event check, r0 pinned, the instruction fetch through the core's instruction cache with its cycles, the
read-absorb tick) and checks, as its guard, that the fetched word is the word it was generated for and that no interrupt is
pending; otherwise it hands the fetched instruction to the interpreter, which runs and counts it. Code that changes (overlays,
code loaded from the disc later, a different disc) therefore never runs a stale step: the guard compares what the CPU really
fetched. A step also leaves as soon as the address is not the next one of its run (a taken branch).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

FORMAT = 1
OBSERVE_MAGIC = 'RRPSX-OBSERVE 1'
MAX_RUN = 256                       # instructions in one step at most (a long straight run becomes several steps)
MAX_VARIANTS = 4                    # words kept per address (the most run); further words stay with the interpreter
RAM_BYTES, BIOS_BASE, BIOS_BYTES = 0x200000, 0x1FC00000, 0x80000


class NativeError(RuntimeError):
    pass


@dataclass
class Observed:
    count: int = 0
    entered: bool = False


def read_observations(paths) -> tuple[dict[tuple[int, int], Observed], bool]:
    """Every (address, word) of the observation files, their counts summed; True when a file's table overflowed."""
    pairs: dict[tuple[int, int], Observed] = {}
    overflow = False
    for path in paths:
        lines = Path(path).read_text(encoding='ascii').splitlines()
        if not lines or lines[0] != OBSERVE_MAGIC:
            raise NativeError(f'{Path(path).name}: not a PlayStation observation file.')
        for line in lines[1:]:
            if line == 'overflow':
                overflow = True
                continue
            pc, word, count, entered = line.split()
            item = pairs.setdefault((int(pc, 16), int(word, 16)), Observed())
            item.count += int(count)
            item.entered |= entered != '0'
    return pairs, overflow


HINT_KIND = 23                      # the PlayStation's runtime hints (systems/psx.py feedback_kinds; psx_main.c RR_FB_PSX)


def add_hints(pairs: dict[tuple[int, int], Observed], rows) -> int:
    """The runtime hints of the player's games (retrorecomp/feedback.py records of HINT_KIND: a 16-byte block of main RAM or
    the BIOS where the interpreter ran instructions the steps did not hold, its physical address, a mask of the words run and
    the four words) join the observations; returns how many (address, word) pairs were new. They are checked like the
    observed code: a step holds the core's own handler body, and the word the CPU fetches is its guard."""
    added = 0
    for row in rows:
        if row.kind != HINT_KIND or len(row.data) != 16 or row.address & 15 or not executable(row.address):
            continue
        for index in range(4):
            if not (row.auxiliary >> index) & 1:
                continue
            key = (row.address + 4 * index, int.from_bytes(row.data[4 * index:4 * index + 4], 'little'))
            if key not in pairs:
                pairs[key] = Observed(1, False)
                added += 1
    return added


# ------------------------------------------------------------------ Beetle's handlers

def _run_real(cpu: str) -> str:
    start = cpu.find('static int32_t CPU_RunReal(')
    end = cpu.find('int32_t CPU_Run(PS_CPU *self, int32_t timestamp_in)', start)
    if start < 0 or end < 0:
        raise NativeError('Beetle PSX cpu.c: CPU_RunReal was not found.')
    return cpu[start:end]


def _strip_comments(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


@dataclass(frozen=True)
class Handlers:
    table: tuple[str, ...]          # handler name of each opf value without a pending interrupt (128 entries)
    bodies: dict                    # name -> body text, comments removed
    digest: str

    def name(self, word: int) -> str:
        return self.table[opf(word)]


def handlers(cpu_text: str) -> Handlers:
    """The dispatch table and the handler bodies of the prepared cpu.c (exactly as the interpreter runs them)."""
    real = _run_real(cpu_text)
    begin = real.find('\n   CGBEGIN\n')
    end = real.find('\n   CGEND\n', begin)
    if begin < 0 or end < 0:
        raise NativeError('Beetle PSX cpu.c: the dispatch table was not found.')
    table = tuple(re.findall(r'CGE\(op_(\w+)\)', real[begin:end]))
    if len(table) != 256:
        raise NativeError('Beetle PSX cpu.c: the dispatch table does not have 256 entries.')
    bodies = {}
    for match in re.finditer(r'BEGIN_OPF\((\w+)\);(.*?)END_OPF;', real, flags=re.S):
        name = match.group(1)
        if name in bodies:
            raise NativeError(f'Beetle PSX cpu.c: two handlers named {name}.')
        bodies[name] = _strip_comments(match.group(2))
    missing = set(table[:128]) - set(bodies)
    if missing:
        raise NativeError('Beetle PSX cpu.c: no body for ' + ', '.join(sorted(missing)) + '.')
    for name in set(table[:128]):
        if re.search(r'\bgoto\b|\breturn\b|\bopf\b|\bself\b', bodies[name]):
            raise NativeError(f'Beetle PSX cpu.c: the {name} handler leaves its body; it cannot be a native step.')
    digest = hashlib.sha256('\0'.join(f'{n}\0{bodies[n]}' for n in sorted(bodies)).encode()
                            + '\0'.join(table).encode()).hexdigest()
    return Handlers(table[:128], bodies, digest)


def opf(word: int) -> int:
    """The interpreter's decode (cpu.c: opf before the interrupt bit is added)."""
    value = word & 0x3F
    if word & (0x3F << 26):
        value = 0x40 | (word >> 26)
    return value


# ------------------------------------------------------------------ steps

def executable(address: int) -> bool:
    return address < RAM_BYTES or BIOS_BASE <= address < BIOS_BASE + BIOS_BYTES


@dataclass
class Plan:
    steps: list                     # [(start address, rank, [(address, word), ...])]
    instructions: int               # (address, word) pairs held by the steps
    addresses: int                  # addresses with at least one step
    variants_left: int              # pairs observed beyond MAX_VARIANTS words at their address (left to the interpreter)
    observed_runs: int              # executions observed in all
    covered_runs: int               # of them, at an (address, word) a step holds


def plan(pairs: dict[tuple[int, int], Observed], table: Handlers) -> Plan:
    """The words seen at each address, most run first (code loaded over other code: overlays, a later disc), up to
    MAX_VARIANTS. The words of one rank form runs of consecutive addresses, cut where an address was entered other than from
    the instruction before it (a branch target, a return, a vector) and every MAX_RUN instructions."""
    variants: dict[int, list] = {}
    entered: set[int] = set()
    for (address, word), seen in pairs.items():
        if not executable(address) or address & 3:
            continue
        if seen.entered:
            entered.add(address)
        if table.name(word) != 'INTERRUPT':
            variants.setdefault(address, []).append((-seen.count, word, seen))
    for found in variants.values():
        found.sort(key=lambda v: (v[0], v[1]))
    steps = []
    for rank in range(MAX_VARIANTS):
        current = None
        for address in sorted(a for a, found in variants.items() if len(found) > rank):
            word = variants[address][rank][1]
            if current is None or address in entered or address != current[2][-1][0] + 4 or len(current[2]) >= MAX_RUN:
                current = (address, rank, [])
                steps.append(current)
            current[2].append((address, word))
    kept = [v for found in variants.values() for v in found[:MAX_VARIANTS]]
    observed = sum(seen.count for seen in pairs.values())
    covered = sum(seen.count for _, _, seen in kept)
    left = sum(max(0, len(found) - MAX_VARIANTS) for found in variants.values())
    return Plan(steps, len(kept), len(variants), left, observed, covered)


SHARD_HEADER = """/* What a slice of this PlayStation game's native steps needs of Beetle PSX's cpu.c, written by Retro-Recomp
 * (retrorecomp/psx_native.py). A slice compiles the head of cpu.c (RR_PSX_SHARD: its declarations, aliases and
 * constants, with the CPU state shared), which includes this file; the handler macros below are copied from the
 * interpreter (GPL-2.0, like it). Each instruction keeps the interpreter's timing: the loop head's event check, fetch
 * through the instruction cache and read-absorb tick come before its body. A step is entered at any address of its
 * run, with the word the interpreter has just fetched there. */
#ifndef RR_PSX_SHARD_H
#define RR_PSX_SHARD_H

extern uint64_t rr_psx_fetched_count, rr_psx_native_count;
/* cpu.c's own accessors, exception entry and instruction-cache miss (our anchored change exports them). */
uint8_t rr_psx_read_u8(int32_t *t, uint32_t a);
uint16_t rr_psx_read_u16(int32_t *t, uint32_t a);
uint32_t rr_psx_read_u32(int32_t *t, uint32_t a, bool ds24, bool lwc);
void rr_psx_write_u8(int32_t *t, uint32_t a, uint32_t v);
void rr_psx_write_u16(int32_t *t, uint32_t a, uint32_t v);
void rr_psx_write_u32(int32_t *t, uint32_t a, uint32_t v, bool ds24);
uint32_t rr_psx_fetch_missed(int32_t *t, uint32_t a);
uint32_t rr_psx_exception(uint32_t code, uint32_t pc, uint32_t np, uint32_t instr);
void rr_psx_recalc_ipcache(void);
#define ReadMemory_u8 rr_psx_read_u8
#define ReadMemory_u16 rr_psx_read_u16
#define ReadMemory_u32 rr_psx_read_u32
#define WriteMemory_u8 rr_psx_write_u8
#define WriteMemory_u16 rr_psx_write_u16
#define WriteMemory_u32 rr_psx_write_u32
#define CPU_Exception rr_psx_exception
#define CPU_RecalcIPCache rr_psx_recalc_ipcache

/* The interpreter's handler macros (cpu.c). */
%s
/* The loop head of the interpreter, per instruction of a step. */
#define RR_READ_INSTRUCTION \\
   (ICache[(PC & 0xFFC) >> 2].TV == PC ? (++rr_psx_fetched_count, ICache[(PC & 0xFFC) >> 2].Data) \\
                                      : rr_psx_fetch_missed(&timestamp, PC))
#define RR_IN \\
   int32_t timestamp = rr->timestamp; \\
   uint32_t PC = rr->PC, new_PC = rr->new_PC, LDWhich = rr->LDWhich, LDValue = rr->LDValue, rr_word = rr->instr
#define RR_OUT \\
   rr->timestamp = timestamp; rr->PC = PC; rr->new_PC = new_PC; rr->LDWhich = LDWhich; rr->LDValue = LDValue
#define RR_FETCH(physical) \\
   if (timestamp >= next_event_ts) goto rr_out; \\
   cpu_last_check_ts = timestamp; \\
   GPR[0] = 0; \\
   if ((PC & 0x1FFFFFFF) != (physical)) goto rr_out; \\
   rr_word = RR_READ_INSTRUCTION;
#define RR_GUARD(word) if (rr_word != (word) || IPCache) goto rr_fetched;
#define RR_TICK \\
   if (ReadAbsorb[ReadAbsorbWhich]) ReadAbsorb[ReadAbsorbWhich]--; else timestamp++; \\
   ++rr_psx_native_count;
#define RR_NEXT PC = new_PC; new_PC = new_PC + 4; BDBT = 0;
#define RR_END \\
   rr_out: RR_OUT; return 0; \\
   rr_fetched: RR_OUT; rr->instr = rr_word; return 1;

#endif
"""

# The macros of cpu.c the handler bodies use, copied into the slices' header (each defined exactly once in cpu.c).
HANDLER_MACROS = ('GPR_DEPRES_BEGIN', 'GPR_DEP', 'GPR_RES', 'GPR_DEPRES_END', 'DO_LDS', 'DO_BRANCH', 'ITYPE', 'ITYPE_ZE',
                  'JTYPE', 'RTYPE')
SLICE_PRELUDE = ('/* Native steps of this PlayStation game (slice %d), written by Retro-Recomp (retrorecomp/psx_native.py)\n'
                 ' * from the code its conversion routes ran: the handler bodies of Beetle PSX\'s interpreter with each\n'
                 ' * instruction word constant (GPL-2.0, like them). */\n'
                 '#define RR_PSX_SHARD 1\n#include "mednafen/psx/cpu.c"\n\n')
SLICE_INSTRUCTIONS = 6000           # instructions per slice (the slices compile side by side)


def handler_macros(cpu_text: str) -> str:
    """The text of the HANDLER_MACROS definitions of cpu.c, continuation lines included."""
    lines = cpu_text.splitlines()
    out = []
    for name in HANDLER_MACROS:
        found = [n for n, line in enumerate(lines) if re.match(rf'\s*#\s*define\s+{name}\b(?!\w)', line)]
        if len(found) != 1:
            raise NativeError(f'Beetle PSX cpu.c: the {name} macro is not defined exactly once.')
        n = found[0]
        out.append(lines[n].strip())
        while lines[n].rstrip().endswith('\\'):
            n += 1
            out.append(lines[n].rstrip())
    return '\n'.join(out) + '\n'


def _macro(name: str, body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    return f'#define RR_OP_{name} \\\n' + ''.join(f'   {line} \\\n' for line in lines) + '\n'


def _function_name(address: int, rank: int = 0) -> str:
    return f'rr_psx_step_{address:08x}' + (f'_{rank}' if rank else '')


def _step(table: Handlers, start: int, rank: int, run: list) -> str:
    lines = [f'int {_function_name(start, rank)}(RrPsxRegs *rr)\n{{\n   RR_IN;\n']
    if len(run) > 1:
        lines.append(f'   switch (((PC & 0x1FFFFFFF) - 0x{start:08x}u) >> 2)\n   {{\n'
                     + ''.join(f'      case {n}: goto rr_e{n};\n' for n in range(len(run)))
                     + '      default: return 1;\n   }\n')
    for index, (address, word) in enumerate(run):
        name = table.name(word)
        lines.append(f'   /* {address:08x}: {word:08x} {name} */\n')
        if index:
            lines.append(f'   RR_FETCH(0x{address:08x}u)\n')
        lines.append(f'   rr_e{index}: RR_GUARD(0x{word:08x}u)\n' if len(run) > 1 else f'   RR_GUARD(0x{word:08x}u)\n')
        branch = 'DO_BRANCH(' in table.bodies[name]
        if branch:
            lines.append(f'#undef BRANCH_DISPATCH\n#define BRANCH_DISPATCH goto rr_b{index};\n')
        lines.append(f'   RR_TICK\n   {{ const uint32_t instr = 0x{word:08x}u; RR_OP_{name} }}\n   RR_NEXT\n')
        if branch:
            lines.append(f'   rr_b{index}: ;\n')
    lines.append('   goto rr_out;\n   RR_END\n}\n\n')
    return ''.join(lines)


TABLE = """/* The native step table of this PlayStation game, written by Retro-Recomp (retrorecomp/psx_native.py): which step
 * runs each address of main RAM and the BIOS, installed at start-up. */
#define RR_PSX_SHARD 1
#include "mednafen/psx/cpu.c"

extern RrPsxStep rr_psx_ram_steps[0x%x >> 2];
extern RrPsxStep rr_psx_bios_steps[0x%x >> 2];
%s
static const struct { uint32_t address, count; RrPsxStep step; } rr_psx_step_table[] = {
%s   {0, 0, NULL}
};

/* Addresses where several words were seen: the step is chosen by the word the interpreter has just fetched (sorted by
 * address, then word). */
static const struct { uint32_t address, word; RrPsxStep step; } rr_psx_variant_table[] = {
%s   {0xFFFFFFFFu, 0, NULL}
};

static int rr_psx_variant_step(RrPsxRegs *rr)
{
   const uint32_t address = rr->PC & 0x1FFFFFFF;
   size_t low = 0, high = sizeof rr_psx_variant_table / sizeof rr_psx_variant_table[0] - 1;
   while (low < high)
   {
      const size_t middle = (low + high) / 2;
      if (rr_psx_variant_table[middle].address < address
          || (rr_psx_variant_table[middle].address == address && rr_psx_variant_table[middle].word < rr->instr))
         low = middle + 1;
      else
         high = middle;
   }
   if (rr_psx_variant_table[low].address == address && rr_psx_variant_table[low].word == rr->instr)
      return rr_psx_variant_table[low].step(rr);
   return 1;
}

static void rr_psx_install(uint32_t a, RrPsxStep step)
{
   if (a < 0x%xu)
      rr_psx_ram_steps[a >> 2] = step;
   else
      rr_psx_bios_steps[(a - 0x%08xu) >> 2] = step;
}

__attribute__((constructor)) static void rr_psx_steps_install(void)
{
   size_t n;
   uint32_t k;
   for (n = 0; rr_psx_step_table[n].step; n++)
      for (k = 0; k < rr_psx_step_table[n].count; k++)
         rr_psx_install(rr_psx_step_table[n].address + 4 * k, rr_psx_step_table[n].step);
   for (n = 0; rr_psx_variant_table[n].step; n++)
      rr_psx_install(rr_psx_variant_table[n].address, rr_psx_variant_step);
}
"""


def _slices(steps: list) -> list[list]:
    out, size = [[]], 0
    for step in steps:
        if size >= SLICE_INSTRUCTIONS:
            out.append([])
            size = 0
        out[-1].append(step)
        size += len(step[2])
    return out


def _write_text(path: Path, text: str) -> None:
    if not path.is_file() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8', newline='\n')


def write(cpu_c: Path, pairs: dict, folder: Path) -> dict:
    """Write the native steps of these observations into `folder` (the slices `rr_psx_steps_NN.c`, their header and the
    table); returns the summary the report keeps, with the C files to compile (`sources`)."""
    cpu_text = Path(cpu_c).read_text(encoding='utf-8')
    table = handlers(cpu_text)
    p = plan(pairs, table)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    header = SHARD_HEADER % handler_macros(cpu_text)
    _write_text(folder / 'rr_psx_shard.h', header)
    digest.update(header.encode())
    sources = []
    used = set()
    for number, steps in enumerate(_slices(p.steps)):
        names = sorted({table.name(word) for _, _, run in steps for _, word in run})
        used.update(names)
        text = (SLICE_PRELUDE % number + ''.join(_macro(name, table.bodies[name]) for name in names)
                + ''.join(_step(table, start, rank, run) for start, rank, run in steps))
        sources.append(f'rr_psx_steps_{number:02d}.c')
        _write_text(folder / sources[-1], text)
        digest.update(text.encode())
    for stale in folder.glob('rr_psx_steps_*.c'):
        if stale.name not in sources:
            stale.unlink()
    words: dict[int, list] = {}
    for start, rank, run in p.steps:
        for address, word in run:
            words.setdefault(address, []).append((word, _function_name(start, rank)))
    shared = {a: sorted(found) for a, found in words.items() if len(found) > 1}
    prototypes = ''.join(f'int {_function_name(start, rank)}(RrPsxRegs *rr);\n' for start, rank, _ in p.steps)
    steps = ''.join(f'   {{0x{start:08x}u, {len(run)}, {_function_name(start, rank)}}},\n' for start, rank, run in p.steps)
    variants = ''.join(f'   {{0x{a:08x}u, 0x{word:08x}u, {name}}},\n' for a in sorted(shared) for word, name in shared[a])
    text = TABLE % (RAM_BYTES, BIOS_BYTES, prototypes, steps, variants, RAM_BYTES, BIOS_BASE)
    sources.append('rr_psx_native_table.c')
    _write_text(folder / sources[-1], text)
    digest.update(text.encode())
    return {'format': FORMAT, 'steps': len(p.steps), 'instructions': p.instructions, 'addresses': p.addresses,
            'addresses_with_variants': len(shared), 'handlers': sorted(used), 'handler_digest': table.digest,
            'variants_left_to_interpreter': p.variants_left, 'observed_executions': p.observed_runs,
            'observed_executions_in_steps': p.covered_runs, 'sources': sources, 'sha256': digest.hexdigest()}
