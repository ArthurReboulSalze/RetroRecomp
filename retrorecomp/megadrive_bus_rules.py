"""Bus layout rules of the Mega Drive's 68000 that the pinned interpreter gets wrong, found by independent vectors (1.6.8).

The 452 vectors of `tests/fixtures/m68k-groups` that differed from the pinned interpreter only by the layout of their bus
transactions (the total of clocks was right) are corrected in two places: the prefetch model (`native/md_prefetch.inc`, with its
static plan in `retrorecomp/megadrive_codegen.py`) and, here, the order in which the executor writes the two words of a long.
The rules are strict one-time replacements of pinned lines, as those of `megadrive_rules.py`, and are applied by the Mega Drive
only; they live in a module of their own because `megadrive_rules.py` is an input of the Neo Geo, CPS-1 and X68000 stamps (they
read its state rules) and none of their behaviour changes here.

* A long that reads its operand first (`ADD`, `SUB`, `AND`, `OR`, `EOR`, `NEG`, `NEGX`, `NOT`, `CLR`, the other read-modify-write
  forms) is written low word first.
* `ADDX.L` and `SUBX.L` on two predecrement operands read each long from its low word, and write the low word, then the next
  prefetch, then the high word.
"""
from __future__ import annotations

from .megadrive_rules import replace

# The order of the two words of a long write that reads the operand first (the arithmetic and logic read-modify-write forms,
# NEG, NEGX, NOT and CLR, which the shared text reads first as the 68000 does): the low word goes first.
BUS_ORDER_RULES = (
    ('static void mem_write(M68KSize sz, uint32_t a, uint32_t v) {\n'
     '    switch (sz) { case M68K_SIZE_B: m68k_write8(a, (uint8_t)v); break;\n'
     '                  case M68K_SIZE_L: m68k_write32(a, v);        break;\n',
     'static int s_low_first;     /* a long read-modify-write writes its low word first */\n'
     'static void mem_write(M68KSize sz, uint32_t a, uint32_t v) {\n'
     '    switch (sz) { case M68K_SIZE_B: m68k_write8(a, (uint8_t)v); break;\n'
     '                  case M68K_SIZE_L: if (s_low_first) { m68k_write16(a + 2u, (uint16_t)v); m68k_write16(a, (uint16_t)(v >> 16)); }\n'
     '                                    else m68k_write32(a, v);   break;\n'),
    ('static void write_ea_ex(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, uint32_t val, int rmw) {\n',
     'static void write_ea_body(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, uint32_t val, int rmw) {\n'),
    ('static void write_ea(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, uint32_t val) {\n',
     'static void write_ea_ex(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, uint32_t val, int rmw) {\n'
     '    s_low_first = rmw && sz == M68K_SIZE_L;\n'
     '    write_ea_body(ins, ea, sz, er, val, rmw);\n'
     '    s_low_first = 0;\n'
     '}\n'
     'static void write_ea(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, uint32_t val) {\n'),
    # ADDX.L and SUBX.L on two predecrement operands: each long is read from its low word, and the result is written low word,
    # next prefetch, high word.
    ('static uint32_t read_ea_ex(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, int rmw) {\n',
     'static uint32_t mem_read_low_first(M68KSize sz, uint32_t a) {\n'
     '    if (sz != M68K_SIZE_L) return mem_read(sz, a);\n'
     '    uint32_t lo = m68k_read16(a + 2u);\n'
     '    return ((uint32_t)m68k_read16(a) << 16) | lo;\n'
     '}\n'
     'static void mem_write_split(uint32_t a, uint32_t v) {\n'
     '    rr_md_prefetch_hold();\n'
     '    m68k_write16(a + 2u, (uint16_t)v);\n'
     '    rr_md_prefetch_release();\n'
     '    m68k_write16(a, (uint16_t)(v >> 16));\n'
     '}\n'
     'static uint32_t read_ea_ex(const M68KInstr *ins, int ea, M68KSize sz, ExtR *er, int rmw) {\n'),
    ('        g_cpu.A[src] -= ay_dec; b = mem_read(sz, g_cpu.A[src]) & m;\n'
     '        g_cpu.A[dst] -= ax_dec; a = mem_read(sz, g_cpu.A[dst]) & m;\n',
     '        g_cpu.A[src] -= ay_dec; b = mem_read_low_first(sz, g_cpu.A[src]) & m;\n'
     '        g_cpu.A[dst] -= ax_dec; a = mem_read_low_first(sz, g_cpu.A[dst]) & m;\n'),
    ('    if (ins->predec_mem_form) mem_write(sz, g_cpu.A[dst], r);\n',
     '    if (ins->predec_mem_form) { if (sz == M68K_SIZE_L) mem_write_split(g_cpu.A[dst], r); else mem_write(sz, g_cpu.A[dst], r); }\n'),
)


def adapt_bus_order_rules(source: str) -> str:
    """The interpreter text (after `megadrive_rules.adapt_instruction_rules`) with the write order of the long operations."""
    for old, new in BUS_ORDER_RULES:
        source = replace(source, old, new)
    return source
