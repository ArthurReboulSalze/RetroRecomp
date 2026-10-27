import struct
import unittest
from retrorecomp.x68000_program import parse_x,RAM_LIMIT
from tools.x68000_fixtures import human68k_hello,_x_file


class ProgramTests(unittest.TestCase):
    def test_real_authored_relocation_at_two_load_addresses(self):
        source=human68k_hello(relocated=True);p=parse_x(source)
        self.assertEqual(p.relocations,((2,4),))
        for base in (0x10000,0x123456):
            image=p.load_image(base)
            self.assertEqual(int.from_bytes(image[2:6],'big'),base+18)
            self.assertEqual(image[6:],source[70:64+len(p.text)+len(p.data)])
        self.assertEqual(source,human68k_hello(relocated=True))

    def test_pc_relative_program_is_independent_of_load_base(self):
        p=parse_x(human68k_hello())
        self.assertEqual(p.load_image(0x20000),p.load_image(0x40000))

    def test_extended_and_word_relocations_and_bss(self):
        text=bytearray(65544)
        text[65536:65540]=(8).to_bytes(4,'big');text[65540:65542]=(12).to_bytes(2,'big')
        content=bytearray(_x_file(bytes(text),b'',bytes.fromhex('0001 00010000 0005')))
        struct.pack_into('>I',content,20,16)
        p=parse_x(bytes(content));image=p.load_image(0x10000,include_bss=True)
        self.assertEqual(int.from_bytes(image[65536:65540],'big'),0x10008)
        self.assertEqual(int.from_bytes(image[65540:65542],'big'),12)
        self.assertEqual(image[-16:],bytes(16))

    def test_relocation_bounds_and_partial_escape_are_rejected(self):
        for reloc in (bytes.fromhex('0001'),bytes.fromhex('0008'),bytes.fromhex('0002 0002')):
            with self.assertRaises(ValueError):parse_x(_x_file(bytes(8),b'',reloc))

    def test_invalid_entry_sections_bound_modules(self):
        for offset,value in ((8,0xffffffff),(12,RAM_LIMIT),(60,64),(44,1)):
            source=bytearray(human68k_hello());struct.pack_into('>I',source,offset,value)
            with self.assertRaises(ValueError):parse_x(bytes(source))
        with self.assertRaises(ValueError):parse_x(human68k_hello()+b'X')

    def test_load_limits_do_not_allocate_unbounded_bss(self):
        p=parse_x(human68k_hello())
        for address in (-2,1,RAM_LIMIT,True):
            with self.assertRaises(ValueError):p.load_image(address,include_bss=True)

if __name__=='__main__':unittest.main()
