"""Checks of the register routing added to the private copy of the pinned SNES engine."""
from pathlib import Path
import unittest

from retrorecomp import snes_bus
from retrorecomp.core import ConversionError

ROOT = Path(__file__).resolve().parents[1]
PINNED_RTL = ROOT / '.deps/snesrecomp/runner/src/common_rtl.c'
STROBE = 'snes_writeReg(g_snes, reg, value);'


class SnesBusRoutingTests(unittest.TestCase):
    def test_manual_joypad_strobe_reaches_the_controller_ports(self):
        # The pinned WriteReg forwards only $4200-$421F, so a guest's $4016
        # strobe was dropped; Star Fox 2 (Japan prototype) then read its pad
        # packet one bit late and stopped on the "controller only" notice.
        if not PINNED_RTL.exists():
            self.skipTest('the pinned SNES engine is not set up')
        source = PINNED_RTL.read_text(encoding='utf-8')
        self.assertNotIn('else if (reg == 0x4016) {', source)
        adapted = snes_bus.runtime(source)
        route = adapted.index('} else if (reg == 0x4016) {')
        internal = adapted.index('} else if (reg >= 0x4200 && reg < 0x4220) {\n    if (reg == 0x420C) {')
        self.assertLess(route, internal)
        self.assertIn(STROBE, adapted[route:internal])
        # Only the write dispatch changes: reads keep their existing route.
        self.assertEqual(adapted.count('reg == 0x4016'), source.count('reg == 0x4016') + 1)

    def test_strobe_adapter_refuses_a_changed_or_ambiguous_dispatch(self):
        with self.assertRaisesRegex(ConversionError, 'Pinned SNES timing hook changed'):
            snes_bus.runtime('/* unsupported engine revision */')
        hook = '  } else if (reg >= 0x4200 && reg < 0x4220) {\n    if (reg == 0x420C) {'
        with self.assertRaises(ConversionError):
            snes_bus.runtime(hook + '\n' + hook)


if __name__ == '__main__':
    unittest.main()
