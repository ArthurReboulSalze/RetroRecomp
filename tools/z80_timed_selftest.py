"""The rendered contention evaluator (retrorecomp/z80_timed.render_c) against its Python walk (z80_timed.delay), ROM-free.

    python -B tools/z80_timed_selftest.py [--samples N]

Every encoding of the seven groups and the acceptances (IM1, IM2, NMI, HALT, a redundant prefix), from seeded random registers
and T-states, taken and not taken, through a rule shaped like the Spectrum's (a delay on 4000h-7FFFh that depends on the T-state)
and an I/O rule that depends on the port; the C program and the Python walk must give the same delay every time. The positive
control renders the same text with one source wrong (HL read as BC) and must differ. Needs a C compiler (the portable llvm-mingw,
else clang, gcc or cc on the PATH).
"""
import argparse
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import z80_timed  # noqa: E402
from retrorecomp.z80_chain import COST_GROUPS  # noqa: E402
from retrorecomp.z80_timing import cycles, length  # noqa: E402

PATTERN = (6, 5, 4, 3, 2, 1, 0, 0)


def peek(address: int) -> int:
    return (address * 7 + 3) & 0xFF


def memory_rule(t: int, address: int) -> int:
    if (address & 0xC000) != 0x4000:
        return 0
    line = t % 224
    return PATTERN[line & 7] if line < 128 else 0


def io_rule(t: int, port: int) -> int:
    if not port & 1:
        return 1 + (t & 3)
    return 2 if (port & 0xC000) == 0x4000 else 0


HARNESS = r'''
#include <stdio.h>
#include <stdint.h>
static uint8_t rr_peek(uint16_t a) { return (uint8_t)(a * 7u + 3u); }
static unsigned rr_memory(uint64_t t, uint16_t a)
{
    static const unsigned pattern[8] = {6, 5, 4, 3, 2, 1, 0, 0};
    if ((a & 0xC000) != 0x4000) return 0;
    unsigned line = (unsigned)(t % 224);
    return line < 128 ? pattern[line & 7] : 0;
}
static unsigned rr_io(uint64_t t, uint16_t port)
{
    if (!(port & 1)) return 1 + (unsigned)(t & 3);
    return (port & 0xC000) == 0x4000 ? 2 : 0;
}
#define RR_TIMED_PEEK(a) rr_peek(a)
#define RR_TIMED_MEMORY(t, a) rr_memory(t, a)
#define RR_TIMED_IO(t, p) rr_io(t, p)
#include "timed.inc"
int main(int argc, char **argv)
{
    FILE *in = fopen(argv[1], "r");
    int g, op, taken;
    unsigned pc, sp, bc, de, hl, ix, iy, vec, a, i, r, base_length;
    unsigned long long t;
    if (!in || argc < 2) return 2;
    while (fscanf(in, "%d %d %d %u %u %u %u %u %u %u %u %u %u %u %u %llu", &g, &op, &taken, &pc, &sp, &bc, &de, &hl, &ix, &iy,
                  &vec, &a, &i, &r, &base_length, &t) == 16) {
        RrTimedStart st = {(uint16_t)pc, (uint16_t)sp, (uint16_t)bc, (uint16_t)de, (uint16_t)hl, (uint16_t)ix, (uint16_t)iy,
                           (uint16_t)vec, (uint8_t)a, (uint8_t)i, (uint8_t)r};
        uint32_t d;
        if (g < 0) d = rr_timed_special_delay(op, &st, t);
        else {
            d = rr_timed_base(g, (unsigned)op, &st, t);
            if (taken) d += rr_timed_extra(g, (unsigned)op, &st, t + base_length + d);
        }
        printf("%u\n", (unsigned)d);
    }
    fclose(in);
    return 0;
}
'''


def find_compiler():
    try:
        from retrorecomp import toolchain
        candidate = toolchain.tools_directory() / 'llvm-mingw' / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    for name in ('clang', 'gcc', 'cc'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _cases(samples: int):
    rng = random.Random(20261122)
    out = []
    specials = list(z80_timed.SPECIALS)
    for index, group in enumerate(list(COST_GROUPS) + [None]):
        for opcode in (range(256) if group is not None else range(len(specials))):
            for sample in range(samples):
                state = {name: rng.randrange(256) for name in ('a', 'b', 'c', 'd', 'e', 'h', 'l', 'i', 'r')}
                state.update({'pc': rng.choice((0x4000, 0x8000, 0x7FFE)) + rng.randrange(64), 'sp': rng.choice((0x5F00, 0xFF00)),
                              'ix': rng.randrange(0x10000), 'iy': rng.randrange(0x10000), 'vec': rng.randrange(0x10000)})
                if sample % 2:
                    state.update({'h': rng.choice((0x40, 0x5A, 0x7F)), 'd': rng.choice((0x40, 0x6C)), 'b': 0x41})
                t = rng.randrange(14000, 70000)
                taken = sample % 3 != 0
                out.append((index if group is not None else -1, opcode, taken, state, t))
    return out


def _expected(group_index: int, opcode: int, taken: bool, state: dict, t: int) -> int:
    if group_index < 0:
        name = list(z80_timed.SPECIALS)[opcode]
        return z80_timed.walk('', z80_timed.SPECIALS[name], state, peek, t, memory_rule, io_rule)
    return z80_timed.delay(COST_GROUPS[group_index], opcode, state, peek, t, memory_rule, io_rule, taken=taken)


def _build(compiler: str, folder: Path, text: str, name: str) -> Path:
    (folder / 'timed.inc').write_text(text, encoding='utf-8', newline='\n')
    (folder / 'main.c').write_text(HARNESS, encoding='utf-8', newline='\n')
    exe = folder / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run([compiler, '-O1', '-std=c11', '-Wall', '-Werror', '-Wno-unused-function', '-o', str(exe), str(folder / 'main.c')],
                   check=True, capture_output=True, text=True)
    return exe


def run(compiler: str, samples: int = 8) -> dict:
    cases = _cases(samples)
    lines = []
    for group_index, opcode, taken, state, t in cases:
        base_length = length(cycles(COST_GROUPS[group_index], opcode)[0]) if group_index >= 0 else 0
        bc, de, hl = state['b'] << 8 | state['c'], state['d'] << 8 | state['e'], state['h'] << 8 | state['l']
        lines.append(f"{group_index} {opcode} {int(taken)} {state['pc']} {state['sp']} {bc} {de} {hl} {state['ix']} {state['iy']} "
                     f"{state['vec']} {state['a']} {state['i']} {state['r']} {base_length} {t}")
    expected = [_expected(*case) for case in cases]
    text = z80_timed.render_c()
    folder = Path(tempfile.mkdtemp(prefix='z80-timed-'))
    try:
        (folder / 'cases.txt').write_text('\n'.join(lines) + '\n', encoding='ascii')
        results = {}
        for name, source in (('timed', text), ('control', text.replace('case 4: return st->hl;', 'case 4: return st->bc;'))):
            exe = _build(compiler, folder, source, name)
            output = subprocess.run([str(exe), str(folder / 'cases.txt')], check=True, capture_output=True, text=True).stdout
            results[name] = [int(value) for value in output.split()]
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if len(results['timed']) != len(cases):
        raise RuntimeError('the C program did not answer every case')
    mismatches = [(cases[k][0], cases[k][1], expected[k], results['timed'][k]) for k in range(len(cases))
                  if expected[k] != results['timed'][k]]
    control = sum(expected[k] != results['control'][k] for k in range(len(cases)))
    return {'compared': len(cases), 'mismatches': mismatches[:12], 'mismatch_count': len(mismatches),
            'nonzero': sum(1 for value in expected if value), 'control_differs': control > 0, 'control_mismatches': control}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--samples', type=int, default=8)
    args = parser.parse_args()
    compiler = find_compiler()
    if compiler is None:
        print('No C compiler found.')
        return 2
    result = run(compiler, args.samples)
    print(f"{result['compared']} cases, {result['nonzero']} with a delay, {result['mismatch_count']} differ "
          f"{result['mismatches']}; control (HL read as BC) differs on {result['control_mismatches']}")
    return 0 if not result['mismatch_count'] and result['control_differs'] else 1


if __name__ == '__main__':
    sys.exit(main())
