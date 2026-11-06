"""Native steps of a PlayStation game from the R3000A code its routes ran (Retro-Recomp's own code, MIT; the C it writes expands
Beetle's handler bodies and is GPL-2.0 like them, inside the GPL-2.0 game).

The conversion's observing build (RR_PSX_OBSERVE, native/psx_machine/psx_observe.c) records each (physical address, word) the
interpreter fetched in main RAM or the BIOS, with whether it was ever reached other than from the instruction before it. This
module turns those records into native steps: runs of consecutive instructions, each a C function of cpu.c (`rr_psx_native.inc`,
included by our anchored change) holding, per instruction, the interpreter's own handler body with its word as a constant.

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
    steps: list                     # [(start address, [(address, word), ...])]
    instructions: int               # instructions held by the steps
    variants_left: int              # (address, word) pairs observed at an address whose step holds another word
    observed_runs: int              # executions observed in all
    covered_runs: int               # of them, at an (address, word) a step holds


def plan(pairs: dict[tuple[int, int], Observed], table: Handlers) -> Plan:
    """One word per address (the one run most often), runs of consecutive addresses cut where an address was entered other
    than from the instruction before it (a branch target, a return, a vector) and every MAX_RUN instructions."""
    chosen: dict[int, tuple[int, Observed]] = {}
    entered: set[int] = set()
    for (address, word), seen in pairs.items():
        if not executable(address) or address & 3:
            continue
        if seen.entered:
            entered.add(address)
        if table.name(word) == 'INTERRUPT':
            continue
        best = chosen.get(address)
        if best is None or (seen.count, -word) > (best[1].count, -best[0]):
            chosen[address] = (word, seen)
    steps, current = [], None
    for address in sorted(chosen):
        word = chosen[address][0]
        if current is None or address in entered or address != current[1][-1][0] + 4 or len(current[1]) >= MAX_RUN:
            current = (address, [])
            steps.append(current)
        current[1].append((address, word))
    observed = sum(seen.count for seen in pairs.values())
    covered = sum(chosen[a][1].count for a in chosen)
    return Plan(steps, len(chosen), sum(1 for a, _ in pairs if a in chosen) - len(chosen), observed, covered)


HEADER = """/* Native steps of this PlayStation game, written by Retro-Recomp (retrorecomp/psx_native.py) from the code its conversion
 * routes ran. They expand the handler bodies of Beetle PSX's interpreter (cpu.c) and are GPL-2.0 like them; included by our
 * anchored change of cpu.c when the game is built with RR_PSX_NATIVE. Each instruction keeps the interpreter's timing: the
 * loop head's event check, fetch through the instruction cache and read-absorb tick come before its body. A step is entered at
 * any address of its run, with the word the interpreter has just fetched there. */

/* The core's memory accesses and instruction-cache misses, called rather than expanded in every instruction (the same
 * functions, so the same cycles; only the compiled size changes). A fetch that hits the instruction cache stays inline, as
 * ReadInstruction does it. */
static NO_INLINE uint8_t rr_psx_read_u8(int32_t *t, uint32_t a) { return ReadMemory_u8(t, a); }
static NO_INLINE uint16_t rr_psx_read_u16(int32_t *t, uint32_t a) { return ReadMemory_u16(t, a); }
static NO_INLINE uint32_t rr_psx_read_u32(int32_t *t, uint32_t a, bool ds24, bool lwc) { return ReadMemory_u32(t, a, ds24, lwc); }
static NO_INLINE void rr_psx_write_u8(int32_t *t, uint32_t a, uint32_t v) { WriteMemory_u8(t, a, v); }
static NO_INLINE void rr_psx_write_u16(int32_t *t, uint32_t a, uint32_t v) { WriteMemory_u16(t, a, v); }
static NO_INLINE void rr_psx_write_u32(int32_t *t, uint32_t a, uint32_t v, bool ds24) { WriteMemory_u32(t, a, v, ds24); }
static NO_INLINE uint32_t rr_psx_fetch_missed(int32_t *t, uint32_t a) { return ReadInstruction(t, a); }
#define ReadMemory_u8(t, a) rr_psx_read_u8(t, a)
#define ReadMemory_u16(t, a) rr_psx_read_u16(t, a)
#define ReadMemory_u32(t, a, ds24, lwc) rr_psx_read_u32(t, a, ds24, lwc)
#define WriteMemory_u8(t, a, v) rr_psx_write_u8(t, a, v)
#define WriteMemory_u16(t, a, v) rr_psx_write_u16(t, a, v)
#define WriteMemory_u32(t, a, v, ds24) rr_psx_write_u32(t, a, v, ds24)
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
"""


def _macro(name: str, body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    return f'#define RR_OP_{name} \\\n' + ''.join(f'   {line} \\\n' for line in lines) + '\n'


def _function_name(address: int) -> str:
    return f'rr_psx_step_{address:08x}'


def _step(table: Handlers, start: int, run: list) -> str:
    lines = [f'static int {_function_name(start)}(RrPsxRegs *rr)\n{{\n   RR_IN;\n']
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


def write(cpu_c: Path, pairs: dict, out: Path) -> dict:
    """Write `out` (rr_psx_native.inc) for these observations; returns the summary the report keeps."""
    table = handlers(Path(cpu_c).read_text(encoding='utf-8'))
    p = plan(pairs, table)
    used = sorted({table.name(word) for _, run in p.steps for _, word in run})
    parts = [HEADER, f'/* {len(p.steps)} steps, {p.instructions} instructions; handlers {table.digest[:16]}. */\n\n']
    parts += [_macro(name, table.bodies[name]) for name in used]
    parts += [_step(table, start, run) for start, run in p.steps]
    parts.append('static const struct { uint32_t address, count; RrPsxStep step; } rr_psx_step_table[] = {\n')
    parts += [f'   {{0x{start:08x}u, {len(run)}, {_function_name(start)}}},\n' for start, run in p.steps]
    parts.append('   {0, 0, NULL}\n};\n\n'
                 '__attribute__((constructor)) static void rr_psx_steps_install(void)\n{\n'
                 '   size_t n;\n   uint32_t k;\n'
                 '   for (n = 0; rr_psx_step_table[n].step; n++)\n'
                 '      for (k = 0; k < rr_psx_step_table[n].count; k++)\n      {\n'
                 '         const uint32_t a = rr_psx_step_table[n].address + 4 * k;\n'
                 f'         if (a < 0x{RAM_BYTES:x}u)\n            rr_psx_ram_steps[a >> 2] = rr_psx_step_table[n].step;\n'
                 f'         else\n            rr_psx_bios_steps[(a - 0x{BIOS_BASE:08x}u) >> 2] = rr_psx_step_table[n].step;\n'
                 '      }\n}\n\n'
                 '#undef ReadMemory_u8\n#undef ReadMemory_u16\n#undef ReadMemory_u32\n'
                 '#undef WriteMemory_u8\n#undef WriteMemory_u16\n#undef WriteMemory_u32\n')
    text = ''.join(parts)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.is_file() or out.read_text(encoding='utf-8') != text:
        out.write_text(text, encoding='utf-8', newline='\n')
    return {'format': FORMAT, 'steps': len(p.steps), 'instructions': p.instructions, 'handlers': used,
            'handler_digest': table.digest, 'variants_left_to_interpreter': p.variants_left,
            'observed_executions': p.observed_runs, 'observed_executions_in_steps': p.covered_runs,
            'sha256': hashlib.sha256(text.encode()).hexdigest()}
