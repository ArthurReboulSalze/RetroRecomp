"""Corrections of the pinned Musashi 68000 (Geolith's copy of `m68kops.c`), shared by the Neo Geo, the CPS-1 and the X68000.

Each of them is checked against the independent SingleStepTests/m68000 vectors (`tools/neogeo_vector_selftest.py`,
`tools/cps1_vector_selftest.py`, `tools/x68000_vector_selftest.py`): the reference CPU of a conversion, the interpreter that
runs the instructions the native code does not cover, then agrees with the vectors on these three points, and with the
translated steps. They are applied to the text at conversion time, like every adaptation of a pinned engine: strict
replacements that refuse a changed pin.
The Mega Drive does not use this copy of Musashi. Its quick-state key does not hash it either.
"""
from __future__ import annotations
from .conversion_common import replace_counted

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
