"""The X68000 generator adapts the shared 68000 forms by an exact prologue.

A change to the shared Neo Geo form (retrorecomp.neogeo_codegen) must fail here,
not only when an X68000 conversion generates its CPU.
"""
import unittest

from retrorecomp.neogeo_codegen import structural_body
from tools.x68000_native import FORM_COPY


class NativeFormTests(unittest.TestCase):
    def test_the_shared_form_still_starts_with_the_pinned_copy(self):
        ins = {'words': [0x4E71], 'byte_length': 2, 'size': 0}
        body = structural_body(ins, 'nop', '').replace('rr_ng_', 'rr_x68k_')
        self.assertEqual(body.count(FORM_COPY), 1)


if __name__ == '__main__':
    unittest.main()
