"""Instruction rules of the Mega Drive's 68000 that the pinned interpreter gets wrong, found by independent vectors.

The pinned `m68k_interp.c` is the text both the translated steps and the reference path are built from. The vectors of
`tests/fixtures/m68k-groups` (MIT, made with MAME, `tools/megadrive_groups_selftest.py`) differ from it in a few instructions;
this module corrects the ones the Motorola manual defines (and, for LINK A7 and UNLK A7, the vectors alone). Each rule is a
strict one-time replacement of a pinned line: a changed upstream fails loudly instead of being half applied. They are applied
by the Mega Drive only (the other 68000 machines run Musashi or their own text), so only the Mega Drive game stamp moves.

State (the final registers and memory):
* `RTR` loads the five condition code bits only (the status register's bits 5 to 7 of the low byte do not exist);
* `LINK A7` pushes the value A7 had before the decrement, and `UNLK A7` ends with the long it popped (the increment of the
  stack pointer is overwritten by that load); these two follow the vectors (MAME), a literal reading of the manual gives the
  old behaviour;
* `NEGX` leaves Z alone when the result is zero (Z is cleared by a non-zero result only);
* `ABCD`, `SBCD` and `NBCD` on bytes that are not two decimal digits (the manual leaves the result undefined) give the result byte and
  the five flags (X, C, N, Z and V, which the manual also leaves undefined) of the independent model Moira (MIT), which also
  reproduces the 22 vectors the pinned text missed (the shared helpers `bcd_add_byte` and `bcd_sub_byte`, `BCD_HELPERS_C`).

Clocks (the total of an instruction, as the manual's tables give it):
* the long forms of `ADD`, `SUB`, `AND`, `OR`, `EOR`, `ADDA` and `SUBA` take two clocks more when the source is a data or
  address register or an immediate (`ADD.L D0,D1` is 8, not 6; `CMP` and `CMPA` do not);
* `CMPA.W` is `6 + ea`, not the `8 + ea` of `ADDA.W`/`SUBA.W`;
* `BTST Dn,#imm` is two clocks more; `BCHG`, `BCLR` and `BSET` on a data register by bit number take two clocks less when the
  bit number is below 16; `Scc Dn` takes 4 clocks, not 6, when the condition is false. These three depend on the data, so they
  charge their time at execution, through the hook `rr_md_arithmetic_phase` that `MULU` and the register shifts already use.
The other undefined results (the flags the manual leaves undefined) are not modelled.
"""
from __future__ import annotations

from .core import ConversionError
from .gun16_runtime import replace as strict_replace


def replace(source: str, old: str, new: str) -> str:
    # The shared strict one-time replacement; only the message is ours (gun16_runtime is in the stamps of every 16-bit machine).
    try:
        return strict_replace(source, old, new)
    except ConversionError:
        raise ConversionError('Pinned 68000 interpreter changed; the Mega Drive instruction rules are refused (' + old.strip().splitlines()[0][:60] + ').') from None


# The static lines of the cycle estimate (after m68000.adapt_cycle_estimates) and what the manual gives.
ESTIMATE_RULES = (
    ('        if (dst_is_reg) return (is_long ? 6 : 4) + ea_src;\n'
     '        else            return (is_long ? 12 : 8) + ea_src + ea_dst;',
     '        if (dst_is_reg) return (is_long ? 6 : 4) + ea_src +\n'
     '            (is_long && instr->mnemonic != MN_CMP && (ea_src == 0 || instr->src_ea == 0x3c) ? 2 : 0);\n'
     '        else            return (is_long ? 12 : 8) + ea_src + ea_dst;'),
    ('    case MN_ADDA: case MN_SUBA: case MN_CMPA:\n'
     '        return (is_long ? 6 : 8) + ea_src;',
     '    case MN_ADDA: case MN_SUBA: case MN_CMPA:\n'
     '        return (instr->mnemonic == MN_CMPA || is_long ? 6 : 8) + ea_src +\n'
     '            (is_long && instr->mnemonic != MN_CMPA && (ea_src == 0 || instr->src_ea == 0x3c) ? 2 : 0);'),
    ('        return (instr->reg<0?4:0) + (dst_is_reg?6:4+interp_ea_read_cost(instr->src_ea,M68K_SIZE_B));',
     '        return (instr->reg<0?4:0) + (dst_is_reg?6:4+interp_ea_read_cost(instr->src_ea,M68K_SIZE_B)) +\n'
     '            (instr->reg>=0 && instr->src_ea == 0x3c ? 2 : 0);'),
)

# The result byte and the flags of ABCD, SBCD and NBCD on any two bytes, decimal digits or not (the manual leaves the result of the
# others, and V of all of them, undefined). Written from the behaviour of the 68000 as the independent model Moira (MIT) shows it, and
# proved equal to it on every operand pair and both values of X (`tools/megadrive_moira_vectors.py`, `native/md_bcd_checks.c`): the
# result byte and the five flags agree everywhere. Both functions return the result in bits 0 to 7, the decimal carry, which is X and C,
# in bit 8 and V in bit 9: V is set when bit 7 changes between the sum before the corrections and the sum after them (0 to 1 for an
# addition, 1 to 0 for a subtraction).
BCD_HELPERS_C = (
    '/* Packed decimal on any bytes. The low digit is corrected when its sum passes 9, the high part when the sum passes 0x90\n'
    ' * (bits 4 to 9 of the corrected sum); a subtraction borrows 6 for the low digit and 0x60 for the high part, and the decision\n'
    ' * on the high part uses the borrow already found. ABCD: bcd_add_byte(dst, src, x); SBCD: bcd_sub_byte(dst, src, x);\n'
    ' * NBCD: bcd_sub_byte(0, operand, x). */\n'
    'static unsigned bcd_add_byte(unsigned dst, unsigned src, unsigned x) {\n'
    '    unsigned digits = (dst & 0xFu) + (src & 0xFu) + x;\n'
    '    unsigned sum = (dst & 0xFFu) + (src & 0xFFu) + x, raw = sum;\n'
    '    if (digits > 9u) sum += 6u;\n'
    '    unsigned carry = (sum & 0x3F0u) > 0x90u;\n'
    '    if (carry) sum += 0x60u;\n'
    '    unsigned overflow = !(raw & 0x80u) && (sum & 0x80u);\n'
    '    return (sum & 0xFFu) | (carry << 8) | (overflow << 9);\n'
    '}\n'
    'static unsigned bcd_sub_byte(unsigned dst, unsigned src, unsigned x) {\n'
    '    int d = (int)(dst & 0xFFu), s = (int)(src & 0xFFu), borrowed = (int)x;\n'
    '    int diff = d - s - borrowed, raw = diff;\n'
    '    if ((d & 0xF) - (s & 0xF) - borrowed < 0) diff -= 6;\n'
    '    unsigned carry = diff < 0;\n'
    '    if (d - s - (int)carry < 0) diff -= 0x60;\n'
    '    unsigned overflow = (raw & 0x80) && !(diff & 0x80);\n'
    '    return ((unsigned)diff & 0xFFu) | (carry << 8) | (overflow << 9);\n'
    '}\n\n')

# The corrected lines of the executor, and their live clocks.
STATE_RULES = (
    ('        g_cpu.SR = (uint16_t)((g_cpu.SR & 0xFF00u) | (ccr & 0xFFu));\n',
     '        g_cpu.SR = (uint16_t)((g_cpu.SR & 0xFF00u) | (ccr & 0x1Fu));\n'),
    ('        g_cpu.A[7] -= 4; m68k_write32(g_cpu.A[7], g_cpu.A[ar]);\n'
     '        g_cpu.A[ar] = g_cpu.A[7];\n',
     '        uint32_t pushed = g_cpu.A[ar];\n'
     '        g_cpu.A[7] -= 4; m68k_write32(g_cpu.A[7], pushed);\n'
     '        g_cpu.A[ar] = g_cpu.A[7];\n'),
    ('        g_cpu.A[7] = g_cpu.A[ar];\n'
     '        g_cpu.A[ar] = m68k_read32(g_cpu.A[7]);\n'
     '        g_cpu.A[7] += 4;\n',
     '        uint32_t frame = g_cpu.A[ar];\n'
     '        uint32_t popped = m68k_read32(frame);\n'
     '        g_cpu.A[7] = frame + 4;\n'
     '        g_cpu.A[ar] = popped;\n'),
    ('            r = (0u - a - x) & m;\n'
     '            flags_sub(0u, a, r, sz);\n',
     '            r = (0u - a - x) & m;\n'
     '            uint16_t kept_z = (uint16_t)(g_cpu.SR & SR_Z);\n'
     '            flags_sub(0u, a, r, sz);\n'
     '            if (ins->mnemonic == MN_NEGX && !r) g_cpu.SR = (uint16_t)((g_cpu.SR & ~SR_Z) | kept_z);\n'),
    # 4 to 8: the decimal instructions, V included (BCD_HELPERS_C above): the helpers and the flag `overflow` they report, the three call
    # sites, and the line that clears V. They are appended, never inserted: the Neo Geo, CPS-1 and X68000 rules module reads this tuple
    # by position.
    ('static void do_bcd(const M68KInstr *ins, int op) {\n'
     '    int x = (g_cpu.SR >> 4) & 1;\n'
     '    uint8_t a, b = 0, r; int carry; uint32_t a_addr = 0; int to_mem = 0;\n',
     BCD_HELPERS_C + 'static void do_bcd(const M68KInstr *ins, int op) {\n'
     '    int x = (g_cpu.SR >> 4) & 1;\n'
     '    uint8_t a, b = 0, r; int carry; uint32_t a_addr = 0; int to_mem = 0; int overflow = 0;\n'),
    ('        unsigned lo = (a & 0xF) + (b & 0xF) + x;\n'
     '        unsigned adj_lo = (lo > 9) ? 6 : 0;\n'
     '        unsigned hi = (a >> 4) + (b >> 4) + ((lo + adj_lo) >> 4);\n'
     '        unsigned adj_hi = (hi > 9) ? 6 : 0;\n'
     '        unsigned full = (hi << 4) + adj_hi * 16 + ((lo + adj_lo) & 0xF);\n'
     '        r = (uint8_t)full; carry = (full & 0x100) != 0;\n',
     '        unsigned full = bcd_add_byte(a, b, (unsigned)x);\n'
     '        r = (uint8_t)full; carry = (full & 0x100) != 0; overflow = (full & 0x200) != 0;\n'),
    ('        int lo = (int)(a & 0xF) - (int)(b & 0xF) - x;\n'
     '        int adj_lo = (lo < 0) ? 6 : 0;\n'
     '        int hi = (int)(a >> 4) - (int)(b >> 4) - (lo < 0 ? 1 : 0);\n'
     '        int adj_hi = (hi < 0) ? 6 : 0;\n'
     '        int full = (hi & 0xFF) * 16 - adj_hi * 16 + ((lo - adj_lo) & 0xF);\n'
     '        r = (uint8_t)full; carry = (hi < 0);\n',
     '        unsigned full = bcd_sub_byte(a, b, (unsigned)x);\n'
     '        r = (uint8_t)full; carry = (full & 0x100) != 0; overflow = (full & 0x200) != 0;\n'),
    ('        int lo = -(int)(a & 0xF) - x;\n'
     '        int adj_lo = (lo < 0) ? 6 : 0;\n'
     '        int hi = -(int)(a >> 4) - (lo < 0 ? 1 : 0);\n'
     '        int adj_hi = (hi < 0) ? 6 : 0;\n'
     '        int full = (hi & 0xFF) * 16 - adj_hi * 16 + ((lo - adj_lo) & 0xF);\n'
     '        r = (uint8_t)full; carry = (hi < 0);\n',
     '        unsigned full = bcd_sub_byte(0u, a, (unsigned)x);\n'
     '        r = (uint8_t)full; carry = (full & 0x100) != 0; overflow = (full & 0x200) != 0;\n'),
    ('        g_cpu.SR &= ~SR_V;\n'
     '        if (r) g_cpu.SR &= ~SR_Z; else if (zold) g_cpu.SR |= SR_Z;\n',
     '        g_cpu.SR &= ~SR_V;\n'
     '        if (overflow) g_cpu.SR |= SR_V;\n'
     '        if (r) g_cpu.SR &= ~SR_Z; else if (zold) g_cpu.SR |= SR_Z;\n'),
)
CLOCK_RULES = (
    ('        uint8_t val = eval_cond(cc) ? 0xFFu : 0x00u;\n',
     '        uint8_t val = eval_cond(cc) ? 0xFFu : 0x00u;\n'
     '        if (!val && ((ins->src_ea >> 3) & 7) == 0) rr_md_arithmetic_phase(4, 0, 1);\n'),
    ('        ExtR save = er;                                  /* BCHG/BCLR/BSET: RMW */\n',
     '        if (ea_mode == 0 && !is_imm && bn < 16)         /* a bit number below 16 saves two clocks */\n'
     '            rr_md_arithmetic_phase(ins->mnemonic == MN_BCLR ? 8u : 6u, 0, 1);\n'
     '        ExtR save = er;                                  /* BCHG/BCLR/BSET: RMW */\n'),
)


def adapt_estimate_rules(source: str) -> str:
    """The static clock rules, for every text that holds the cycle estimate (the steps' table, the reference path, the decoder)."""
    for old, new in ESTIMATE_RULES:
        source = replace(source, old, new)
    return source


def adapt_instruction_rules(source: str) -> str:
    """The estimate rules, the state rules and the data-dependent clocks, for the interpreter text of the Mega Drive."""
    source = adapt_estimate_rules(source)
    for old, new in STATE_RULES + CLOCK_RULES:
        source = replace(source, old, new)
    return source
