"""Corrections of the pinned Musashi 68000 (Geolith's copy of `m68kops.c`), shared by the Neo Geo, the CPS-1 and the X68000.

Each of them is checked against the independent SingleStepTests/m68000 vectors (`tools/neogeo_vector_selftest.py`,
`tools/cps1_vector_selftest.py`, `tools/x68000_vector_selftest.py`): the reference CPU of a conversion, the interpreter that
runs the instructions the native code does not cover, then agrees with the vectors on these points, and with the
translated steps. They are applied to the text at conversion time, like every adaptation of a pinned engine: strict
replacements that refuse a changed pin.
The Mega Drive does not use this copy of Musashi. Its quick-state key does not hash it either.
"""
from __future__ import annotations
from .conversion_common import replace_counted

# The decimal instructions on bytes that are not two decimal digits (the manual leaves the result undefined). Musashi rounds each digit
# on its own; the translated steps and the independent model Moira (MIT) correct the sum as a whole, and so do these helpers (the same
# arithmetic as `megadrive_rules.BCD_HELPERS_C`, proved equal to Moira on every pair of operand bytes and both values of X). They set
# X, C, N, Z and V, as the translated steps do. The twenty handlers (ABCD 5, SBCD 5, NBCD 10) keep their operand access
# and their store, and call the helper for the arithmetic and the flags.
BCD_HELPERS_C = (
    '/* Packed decimal on any bytes, the arithmetic of the translated steps (Retro-Recomp). */\n'
    'static unsigned rr_bcd_flags(unsigned res, unsigned carry, unsigned overflow)\n{\n'
    '\tFLAG_X = FLAG_C = carry << 8;\n'
    '\tFLAG_V = overflow ? VFLAG_SET : VFLAG_CLEAR;\n'
    '\tFLAG_N = NFLAG_8(res);\n'
    '\tFLAG_Z |= res;\n'
    '\treturn res;\n}\n\n'
    'static unsigned rr_bcd_add(unsigned src, unsigned dst)\n{\n'
    '\tunsigned x = XFLAG_AS_1();\n'
    '\tunsigned sum = (dst & 0xff) + (src & 0xff) + x;\n'
    '\tunsigned raw = sum;\n'
    '\tunsigned carry;\n\n'
    '\tif((dst & 0xf) + (src & 0xf) + x > 9)\n'
    '\t\tsum += 6;\n'
    '\tcarry = (sum & 0x3f0) > 0x90;\n'
    '\tif(carry)\n'
    '\t\tsum += 0x60;\n'
    '\treturn rr_bcd_flags(sum & 0xff, carry, !(raw & 0x80) && (sum & 0x80));\n}\n\n'
    'static unsigned rr_bcd_sub(unsigned src, unsigned dst)\n{\n'
    '\tint x = XFLAG_AS_1();\n'
    '\tint d = dst & 0xff;\n'
    '\tint s = src & 0xff;\n'
    '\tint diff = d - s - x;\n'
    '\tint raw = diff;\n'
    '\tunsigned carry;\n\n'
    '\tif((d & 0xf) - (s & 0xf) - x < 0)\n'
    '\t\tdiff -= 6;\n'
    '\tcarry = diff < 0;\n'
    '\tif(d - s - (int)carry < 0)\n'
    '\t\tdiff -= 0x60;\n'
    '\treturn rr_bcd_flags((unsigned)diff & 0xff, carry, (raw & 0x80) && !(diff & 0x80));\n}\n\n\n')
# NBCD: everything from the result to the N flag; the store in the middle is the only part that differs between the handlers.
NBCD_HEAD = (' res = MASK_OUT_ABOVE_8(0x9a - dst - XFLAG_AS_1());\n\n\tif(res != 0x9a)\n\t{\n\t\tFLAG_V = ~res; /* Undefined V behavior */\n\n'
             '\t\tif((res & 0x0f) == 0xa)\n\t\t\tres = (res & 0xf0) + 0x10;\n\n\t\tres = MASK_OUT_ABOVE_8(res);\n\n'
             '\t\tFLAG_V &= res; /* Undefined V behavior part II */\n\n')
NBCD_TAIL = ('\n\t\tFLAG_Z |= res;\n\t\tFLAG_C = CFLAG_SET;\n\t\tFLAG_X = XFLAG_SET;\n\t}\n\telse\n\t{\n\t\tFLAG_V = VFLAG_CLEAR;\n'
             '\t\tFLAG_C = CFLAG_CLEAR;\n\t\tFLAG_X = XFLAG_CLEAR;\n\t}\n\tFLAG_N = NFLAG_8(res);\t/* Undefined N behavior */\n')
NBCD_REGISTER_STORE = '\t\t*r_dst = MASK_OUT_BELOW_8(*r_dst) | res;\n'
NBCD_MEMORY_STORE = '\t\tm68ki_write_8(ea, MASK_OUT_ABOVE_8(res));\n'

# (what, text of the pinned file, replacement, number of occurrences)
MUSASHI_OPS_FIXES = (
    # N and Z are undefined after a divide overflow on the 68000 (the vectors mask them); the values below are the ones the
    # translated steps give, so that the interpreter and the native code leave the same state.
    ('DIVU and DIVS leave N set, Z and C cleared when the quotient overflows (the 16-bit forms)',
     '\t\tFLAG_V = VFLAG_SET;\n\t\treturn;\n\t}\n\t/* On the 68000 the trap costs 38',
     '\t\tFLAG_V = VFLAG_SET;\n\t\tFLAG_N = NFLAG_SET;\n\t\tFLAG_Z = ZFLAG_CLEAR;\n\t\tFLAG_C = CFLAG_CLEAR;\n\t\treturn;\n\t}\n'
     '\t/* On the 68000 the trap costs 38', 22),
    # -0x80000000 / -1 is an overflow like any other quotient that does not fit in 16 bits: the destination is kept.
    ('DIVS of 0x80000000 by -1 overflows (Musashi cleared the destination and the flags)',
     '\t\t\tFLAG_Z = 0;\n\t\t\tFLAG_N = NFLAG_CLEAR;\n\t\t\tFLAG_V = VFLAG_CLEAR;\n\t\t\tFLAG_C = CFLAG_CLEAR;\n\t\t\t*r_dst = 0;\n\t\t\treturn;\n',
     '\t\t\tFLAG_Z = ZFLAG_CLEAR;\n\t\t\tFLAG_N = NFLAG_SET;\n\t\t\tFLAG_V = VFLAG_SET;\n\t\t\tFLAG_C = CFLAG_CLEAR;\n\t\t\treturn;\n', 11),
    # N is undefined after a CHK that does not trap; the vectors, and the translated steps, give 0 (the value is not negative).
    ('CHK within its bounds clears N (the 16-bit forms)',
     '\tif(src >= 0 && src <= bound)\n\t{\n\t\treturn;\n\t}\n',
     '\tif(src >= 0 && src <= bound)\n\t{\n\t\tFLAG_N = NFLAG_CLEAR;\n\t\treturn;\n\t}\n', 11),
    # Read from the vectors (165 CHK vectors, 149 of them traps): 38 plus the operand when the value is above the bound or when the 16-bit
    # subtraction src - bound overflows, 40 plus the operand otherwise (the value is below zero and not above the bound).
    ('the CHK exception takes 2 clocks more below zero when the value is not above the bound and the comparison does not overflow',
     'USE_CYCLES(CYC_INSTRUCTION[REG_IR] - 10);',
     'USE_CYCLES(CYC_INSTRUCTION[REG_IR] - 10 + (src > bound || src - bound < -32768 ? 0 : 2));', 11),
    # The vectors (MAME) push the value A7 had before the decrement, as the translated steps now do (m68000_state_rules).
    # `m68k_op_link_32_a7` has the same line and is left as it is: LINK.L is a 68020 instruction, unreachable on a 68000.
    ('LINK A7 pushes the stack pointer as it was before the decrement (Musashi pushed it after)',
     'static void m68k_op_link_16_a7(void)\n{\n\tREG_A[7] -= 4;\n\tm68ki_write_32(REG_A[7], REG_A[7]);\n',
     'static void m68k_op_link_16_a7(void)\n{\n\tunsigned pushed = REG_A[7];\n\tREG_A[7] -= 4;\n\tm68ki_write_32(REG_A[7], pushed);\n', 1),
    # The decimal instructions: one arithmetic for the result byte and X, C, N, Z (see BCD_HELPERS_C); the helpers go in front of the first handler.
    ('the helpers of the decimal instructions',
     'static void m68k_op_abcd_8_rr(void)\n{\n',
     BCD_HELPERS_C + 'static void m68k_op_abcd_8_rr(void)\n{\n', 1),
    ('ABCD on bytes that are not decimal digits (the register form and the four memory forms)',
     ' res = LOW_NIBBLE(src) + LOW_NIBBLE(dst) + XFLAG_AS_1();\n\n\tFLAG_V = ~res; /* Undefined V behavior */\n\n\tif(res > 9)\n\t\tres += 6;\n'
     '\tres += HIGH_NIBBLE(src) + HIGH_NIBBLE(dst);\n\tFLAG_X = FLAG_C = (res > 0x99) << 8;\n\tif(FLAG_C)\n\t\tres -= 0xa0;\n\n'
     '\tFLAG_V &= res; /* Undefined V behavior part II */\n\tFLAG_N = NFLAG_8(res); /* Undefined N behavior */\n\n\tres = MASK_OUT_ABOVE_8(res);\n\tFLAG_Z |= res;\n',
     ' res = rr_bcd_add(src, dst);\n', 5),
    ('SBCD on bytes that are not decimal digits (the register form and the four memory forms)',
     ' res = LOW_NIBBLE(dst) - LOW_NIBBLE(src) - XFLAG_AS_1();\n\n\tFLAG_V = ~res; /* Undefined V behavior */\n\n\tif(res > 9)\n\t\tres -= 6;\n'
     '\tres += HIGH_NIBBLE(dst) - HIGH_NIBBLE(src);\n\tFLAG_X = FLAG_C = (res > 0x99) << 8;\n\tif(FLAG_C)\n\t\tres += 0xa0;\n\n'
     '\tres = MASK_OUT_ABOVE_8(res);\n\n\tFLAG_V &= res; /* Undefined V behavior part II */\n\tFLAG_N = NFLAG_8(res); /* Undefined N behavior */\n\tFLAG_Z |= res;\n',
     ' res = rr_bcd_sub(src, dst);\n', 5),
    ('NBCD on a data register with a byte that is not a decimal digit pair',
     NBCD_HEAD + NBCD_REGISTER_STORE + NBCD_TAIL,
     ' res = rr_bcd_sub(dst, 0);\n\n' + NBCD_REGISTER_STORE.replace('\t\t', '\t'), 1),
    ('NBCD on a memory byte that is not a decimal digit pair (nine addressing modes); the byte is also written when it is zero',
     NBCD_HEAD + NBCD_MEMORY_STORE + NBCD_TAIL,
     ' res = rr_bcd_sub(dst, 0);\n\n' + NBCD_MEMORY_STORE.replace('\t\t', '\t').replace('MASK_OUT_ABOVE_8(res)', 'res'), 9),
    ('the opcodes F620 to F627 are Line-F exceptions on a 68000, not the 68040 MOVE16',
     'static void m68k_op_move16_32(void)\n{\n',
     'static void m68k_op_move16_32(void)\n{\n'
     '\tif(!CPU_TYPE_IS_040_PLUS(CPU_TYPE))\n\t{\n\t\tm68ki_exception_1111();\n\t\treturn;\n\t}\n', 1),
)


def adapt_musashi_ops(source: str) -> str:
    """`m68kops.c` of the pinned Geolith with `MUSASHI_OPS_FIXES` applied; a text that moved raises `ValueError`.

    The file is CRLF in a Windows checkout and LF in a Linux one: the replacements are made on LF text and the line ends
    the file had are given back.
    """
    crlf = '\r\n' in source
    text = source.replace('\r\n', '\n') if crlf else source
    for what, before, after, count in MUSASHI_OPS_FIXES:
        text = replace_counted(text, before, after, count=count,
                               error=lambda old, what=what: ValueError(f'Pinned Musashi changed ({what}); the correction is refused.'))
    return text.replace('\n', '\r\n') if crlf else text
