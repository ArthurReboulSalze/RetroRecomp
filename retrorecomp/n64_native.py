"""Nintendo 64 native blocks: C generated from the VR4300 code a game is seen running (MIT).

An observation (native/n64_machine/n64_cpu.c, mode 1) lists, once per (address, code identity), the straight run that starts at a
leader (a jump target, a branch not taken, an exception vector) up to and including its first control-flow instruction and that
instruction's delay slot, with how often it ran. Several variants of one address are kept (overlays load different code at one
place); the game picks at run time the variant whose words are the live ones (the guard), else the core's interpreter runs it,
counted.

Each block calls the core's own instruction function for each of its words, with the opcode a constant (`execute_op(r4300, op)`
of n64_exec.h, always inlined: the switch on the opcode folds away, there is no fetch and no decode). It stops as soon as the PC
is not where a straight run puts it (an exception, an interrupt check that moved it) and, after every store, compares the rest of
its own words with the live ones (code that writes itself). A block that ends on a jump or a branch runs it, its delay slot
included (the core's jump functions run the delay slot themselves), and the next block follows without going back to the loop.

Only KSEG0 addresses of RDRAM are kept (TLB-mapped code, the boot code in the RSP's memory and the cartridge's own addresses run
on the interpreter). Nothing else is claimed: the blocks are the core's own semantics, and a fresh reference run of the same game
on the interpreter checks every frame.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path

from .core import ConversionError

FORMAT = 1
RUN_MAX = 130                  # the observation's bound (128 words) plus a delay slot
KSEG0 = (0x80000000, 0x80800000)
MAX_VARIANTS = 1 << 21
PER_SHARD = 1500


def is_flow(op: int) -> bool:
    """A control-flow instruction: jumps, branches, traps and syscalls, COP0 (ERET, TLB, a write that may raise an interrupt),
    CACHE, BC1x. A block never runs past one."""
    major, funct, rs = op >> 26, op & 0x3F, (op >> 21) & 0x1F
    if major == 0:
        return funct in (8, 9, 12, 13, 15) or 48 <= funct <= 54
    return major in (1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23, 16, 47) or (major == 17 and rs == 8)


def has_delay(op: int) -> bool:
    major, funct, rs, rt = op >> 26, op & 0x3F, (op >> 21) & 0x1F, (op >> 16) & 0x1F
    if major == 0:
        return funct in (8, 9)
    if major == 1:
        return rt in (0, 1, 2, 3, 16, 17, 18, 19)
    return major in (2, 3, 4, 5, 6, 7, 20, 21, 22, 23) or (major == 17 and rs == 8)


def is_store(op: int) -> bool:
    return (op >> 26) in (40, 41, 42, 43, 44, 45, 46, 56, 57, 60, 61, 63)


def read_observations(paths, variants: dict | None = None) -> dict:
    """(pc, words) -> times run, summed over observation files; every line is checked (KSEG0, length, flow at its end)."""
    variants = defaultdict(int) if variants is None else variants
    for path in paths:
        for number, line in enumerate(Path(path).read_text(encoding='ascii').splitlines(), 1):
            fields = line.split()
            try:
                pc, count, length = int(fields[0], 16), int(fields[1]), int(fields[2])
                words = tuple(int(x, 16) for x in fields[3:])
            except (IndexError, ValueError):
                raise ConversionError(f'Nintendo 64 observation {Path(path).name}:{number} is malformed.') from None
            if length != len(words) or not 1 <= length <= RUN_MAX or count < 1 or pc % 4 or any(w >> 32 for w in words):
                raise ConversionError(f'Nintendo 64 observation {Path(path).name}:{number} is invalid.')
            if not KSEG0[0] <= pc < KSEG0[1] or pc + 4 * length > KSEG0[1]:
                continue
            variants[(pc, words)] += count
            if len(variants) > MAX_VARIANTS:
                raise ConversionError('Nintendo 64 observation bound exceeded.')
    return variants


def write_observations(path: Path, variants: dict) -> None:
    """The observation format again (the private memory of a game keeps the union of its conversions' observations)."""
    lines = [f'{pc:08x} {count} {len(words)} ' + ' '.join(f'{w:08x}' for w in words)
             for (pc, words), count in sorted(variants.items())]
    path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='ascii')


def executed(words) -> int:
    """The instructions a block runs at most before its delay slot: up to its first control-flow instruction."""
    for i, op in enumerate(words):
        if is_flow(op):
            return i + 1
    return len(words)


def choose(variants: dict, coverage: float = 0.995) -> list[tuple[int, tuple, int]]:
    """The blocks kept: the most run first (by instructions run) until `coverage` of the observed instructions; then by address,
    the variants of one address together, the most run first (the run time table points at the first)."""
    weighted = sorted(((count * executed(words), pc, words, count) for (pc, words), count in variants.items()),
                      key=lambda item: (-item[0], item[1], item[2]))
    total = sum(item[0] for item in weighted)
    chosen, covered = [], 0
    for weight, pc, words, count in weighted:
        if total and covered >= coverage * total:
            break
        chosen.append((pc, words, count))
        covered += weight
    # Every observed version of a kept address is kept too: overlays load other code at a place the game runs often, and a
    # version left out is a guard miss each time it runs (Ocarina of Time's play route: 25,793 of them before this).
    kept = {pc for pc, _, _ in chosen}
    have = {(pc, words) for pc, words, _ in chosen}
    chosen += [(pc, words, count) for _, pc, words, count in weighted if pc in kept and (pc, words) not in have]
    chosen.sort(key=lambda item: (item[0], -item[2], item[1]))
    return chosen


def block_lines(name: str, pc: int, words: tuple) -> list[str]:
    lines = [f'const uint32_t rr_n64_w_{name}[{len(words)}] = {{' + ','.join(f'0x{w:x}u' for w in words) + '};',
             f'int rr_n64_b_{name}(struct r4300_core *r4300, const uint32_t *live) {{ const uint32_t *W = rr_n64_w_{name}; '
             f'const uint32_t LEN = {len(words)}u; (void)W; (void)LEN; (void)live;']
    run = executed(words)
    for k in range(run):
        op, following = words[k], (pc + 4 * (k + 1)) & 0xFFFFFFFF
        if k == run - 1 and is_flow(op):
            # The jump runs its delay slot itself; counted as one, as the interpreter's loop counts it.
            lines.append(f' execute_op(r4300, 0x{op:x}u); return {k + 1};')
            break
        lines.append(f' {"S" if is_store(op) else "E"}(0x{op:x}u, 0x{following:x}u, {k + 1})')
    else:
        lines.append(f' return {run};')
    lines.append('}')
    return lines


def generate(variants: dict, folder: Path, coverage: float = 0.995) -> dict:
    """blocks/shard_NNN.c and blocks/table.c in `folder` (rewritten); an empty selection writes no block (the game then runs the
    cached interpreter). Returns what was written."""
    blocks = folder / 'blocks'
    blocks.mkdir(parents=True, exist_ok=True)
    for old in blocks.glob('*.c'):
        old.unlink()
    chosen = choose(variants, coverage)
    if not chosen:
        return {'format': FORMAT, 'blocks': 0, 'instructions': 0, 'addresses': 0, 'shards': 0, 'table_sha256': None}
    names, seen = [], defaultdict(int)
    for pc, _, _ in chosen:
        names.append(f'{pc:08x}_{seen[pc]}')
        seen[pc] += 1
    head = ['/* Generated by Retro-Recomp (retrorecomp/n64_native.py): native blocks over the core\'s own instruction functions. */',
            '#include "n64_exec.h"', '#include "n64_cpu.h"', '#include <string.h>',
            '#define E(op, nx, k) execute_op(r4300, op); if (r4300->interp_PC.addr != (nx)) return (k);',
            '#define S(op, nx, k) E(op, nx, k) if (memcmp(live + (k), W + (k), (LEN - (k)) * 4)) return (k);']
    shards = 0
    for start in range(0, len(chosen), PER_SHARD):
        lines = list(head)
        for j in range(start, min(start + PER_SHARD, len(chosen))):
            pc, words, _ = chosen[j]
            lines += block_lines(names[j], pc, words)
        (blocks / f'shard_{shards:03d}.c').write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
        shards += 1
    # The table: one array in address order, the variants of an address together (the run time table points at the first).
    table = ['/* Generated by Retro-Recomp (retrorecomp/n64_native.py). */', '#include "n64_cpu.h"']
    table += [f'extern const uint32_t rr_n64_w_{n}[]; int rr_n64_b_{n}(struct r4300_core *, const uint32_t *);' for n in names]
    table.append(f'const uint32_t rr_n64_block_count = {len(chosen)}u;')
    table.append('const RrN64Block rr_n64_blocks[] = {')
    table += [f' {{0x{pc:08x}u, {len(words)}u, rr_n64_b_{n}, rr_n64_w_{n}}},' for (pc, words, _), n in zip(chosen, names)]
    table.append('};')
    text = '\n'.join(table) + '\n'
    (blocks / 'table.c').write_text(text, encoding='ascii', newline='\n')
    return {'format': FORMAT, 'blocks': len(chosen), 'instructions': sum(executed(w) for _, w, _ in chosen),
            'addresses': len(seen), 'variant_addresses': sum(1 for v in seen.values() if v > 1), 'shards': shards,
            'observed_variants': len(variants), 'table_sha256': hashlib.sha256(text.encode('ascii')).hexdigest()}
