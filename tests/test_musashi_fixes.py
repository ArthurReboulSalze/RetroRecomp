"""The corrections of the pinned Musashi 68000 shared by the Neo Geo, the CPS-1 and the X68000."""
import unittest
from pathlib import Path

from retrorecomp import musashi_fixes
from retrorecomp.paths import ROOT

PIN = ROOT / '.deps/geolith-libretro/src/m68k/m68kops.c'
DIVIDE = '\t\tFLAG_V = VFLAG_SET;\n\t\treturn;\n\t}\n\t/* On the 68000 the trap costs 38 cycles plus the operand fetch */\n'
CHECK = '\tif(src >= 0 && src <= bound)\n\t{\n\t\treturn;\n\t}\n\t\tUSE_CYCLES(CYC_INSTRUCTION[REG_IR] - 10);\n'
DIVS_MIN = '\t\t\tFLAG_Z = 0;\n\t\t\tFLAG_N = NFLAG_CLEAR;\n\t\t\tFLAG_V = VFLAG_CLEAR;\n\t\t\tFLAG_C = CFLAG_CLEAR;\n\t\t\t*r_dst = 0;\n\t\t\treturn;\n'
LINK = 'static void m68k_op_link_16_a7(void)\n{\n\tREG_A[7] -= 4;\n\tm68ki_write_32(REG_A[7], REG_A[7]);\n'
MOVE16 = 'static void m68k_op_move16_32(void)\n{\n\tuint16_t w2 = OPER_I_16();\n'


ABCD_HEAD = 'static void m68k_op_abcd_8_rr(void)\n{\n'
ABCD = musashi_fixes.MUSASHI_OPS_FIXES[6][1]
SBCD = musashi_fixes.MUSASHI_OPS_FIXES[7][1]
NBCD_REGISTER = musashi_fixes.MUSASHI_OPS_FIXES[8][1]
NBCD_MEMORY = musashi_fixes.MUSASHI_OPS_FIXES[9][1]


def sample(divides=22, checks=11, mins=11, abcd=5, sbcd=5, nbcd_register=1, nbcd_memory=9):
    return (DIVIDE * divides + CHECK * checks + DIVS_MIN * mins + LINK + MOVE16 + ABCD_HEAD
            + ABCD * abcd + SBCD * sbcd + NBCD_REGISTER * nbcd_register + NBCD_MEMORY * nbcd_memory)


class MusashiFixesTests(unittest.TestCase):
    def test_each_site_is_corrected(self):
        fixed = musashi_fixes.adapt_musashi_ops(sample())
        flags = '\t\tFLAG_V = VFLAG_SET;\n\t\tFLAG_N = NFLAG_SET;\n\t\tFLAG_Z = ZFLAG_CLEAR;\n\t\tFLAG_C = CFLAG_CLEAR;\n\t\treturn;'
        self.assertEqual(fixed.count(flags), 22)
        self.assertEqual((fixed.count('- 10 + (src > bound || src - bound < -32768 ? 0 : 2));'), fixed.count('- 10);')), (11, 0))
        self.assertIn('{\n\tunsigned pushed = REG_A[7];\n\tREG_A[7] -= 4;\n\tm68ki_write_32(REG_A[7], pushed);\n', fixed)
        self.assertNotIn('m68ki_write_32(REG_A[7], REG_A[7])', fixed)
        self.assertIn('{\n\tif(!CPU_TYPE_IS_040_PLUS(CPU_TYPE))\n\t{\n\t\tm68ki_exception_1111();\n\t\treturn;\n\t}\n\tuint16_t w2', fixed)

    def test_the_decimal_instructions_call_the_helpers(self):
        fixed = musashi_fixes.adapt_musashi_ops(sample())
        self.assertEqual((fixed.count(' res = rr_bcd_add(src, dst);'), fixed.count(' res = rr_bcd_sub(src, dst);')), (5, 5))
        self.assertEqual(fixed.count(' res = rr_bcd_sub(dst, 0);'), 10)
        self.assertEqual(fixed.count('static unsigned rr_bcd_'), 3)
        for old in ('0x9a - dst', 'Undefined V behavior', 'HIGH_NIBBLE', 'res -= 0xa0', 'res += 0xa0'):
            self.assertNotIn(old, fixed)
        self.assertEqual(fixed.count('m68ki_write_8(ea, res);'), 9)                # the byte is written whatever its value

    def test_the_line_ends_of_the_file_are_kept(self):
        crlf = sample().replace('\n', '\r\n')
        fixed = musashi_fixes.adapt_musashi_ops(crlf)
        self.assertEqual(fixed.count('\n'), fixed.count('\r\n'))
        self.assertEqual(fixed.replace('\r\n', '\n'), musashi_fixes.adapt_musashi_ops(sample()))

    def test_a_moved_pin_is_refused(self):
        for text in (sample(divides=21), sample(checks=10), sample(mins=10), sample() + MOVE16, sample().replace('move16_32', 'move16_33'), sample().replace('link_16_a7', 'link_16_b7'), sample() + LINK,
                     sample(abcd=4), sample(sbcd=6), sample(nbcd_register=0), sample(nbcd_memory=8), sample() + ABCD_HEAD):
            with self.assertRaises(ValueError):
                musashi_fixes.adapt_musashi_ops(text)

    @unittest.skipUnless(PIN.is_file(), 'the pinned Geolith checkout is not present')
    def test_the_pinned_file_takes_the_corrections(self):
        source = PIN.read_text(encoding='utf-8')
        fixed = musashi_fixes.adapt_musashi_ops(source)
        grown = sum(count * (after.count('\n') - before.count('\n')) for _, before, after, count in musashi_fixes.MUSASHI_OPS_FIXES)
        self.assertEqual(len(fixed.splitlines()), len(source.splitlines()) + grown)
        self.assertEqual(fixed.count('rr_bcd_sub(') + fixed.count('rr_bcd_add('), 20 + 2)            # 20 handlers and the 2 definitions
        self.assertEqual(musashi_fixes.adapt_musashi_ops(PIN.read_bytes().decode('utf-8')).replace('\r\n', '\n'), fixed)


if __name__ == '__main__':
    unittest.main()
