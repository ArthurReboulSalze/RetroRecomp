"""The resload services a WHDLoad slave calls (native/amiga_whdload/rr_resload.c and rr_decrunch.c), checked by an
authored C harness.

The harness runs every provided service on a flat guest memory with authored files: loads, disk images, saves,
CRC-16, Control tags, the whole patch-list language including IF blocks and PL_NEXT, PatchSeg, Relocate (over itself,
into a CHIP area, as a LoadSeg list), RNC1 unpacking (a file packed here by an encoder written from the format, with
literal runs and matches over two sub-chunks), the Kickstart load (resload_LoadKick, and the image a v16+ slave header
asks for, one name or a table of CRC-16 and name pairs, with an authored fake image), Examine, ExNext and ListFiles over
an authored file list, and the refusals of what is not provided. No game, slave, ROM or Kickstart is involved.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class RncWriter:
    """RNC method 1 stream: bits least significant first in 16-bit little-endian words; a literal run is stored right
    after the last word that holds bits, and the next bits go on filling that word."""

    def __init__(self):
        self.out = bytearray()
        self.slot = None      # byte position of the word being filled
        self.bits = 0
        self.acc = 0

    def bit(self, b):
        if self.slot is None:
            self.slot = len(self.out)
            self.out += b'\0\0'
            self.bits = self.acc = 0
        self.acc |= (b & 1) << self.bits
        self.bits += 1
        struct.pack_into("<H", self.out, self.slot, self.acc)
        if self.bits == 16:
            self.slot = None

    def number(self, value, n):            # n bits, least significant first
        for k in range(n):
            self.bit(value >> k)

    def code(self, symbol):                # 16 symbols of 4 bits each: canonical code = symbol, sent MSB first
        for k in range(3, -1, -1):
            self.bit(symbol >> k)

    def value(self, x):                    # n < 2 is itself; else 2^(n-1) and n-1 more bits
        if x < 2:
            self.code(x)
        else:
            n = x.bit_length()
            self.code(n)
            self.number(x - (1 << (n - 1)), n - 1)

    def literals(self, data):
        self.out += data


def rnc1(chunks):
    """chunks: a list of sub-chunks (literal bytes, then (distance, length) or None for the last). Returns
    (packed file, unpacked bytes)."""
    w, plain = RncWriter(), bytearray()
    w.number(0, 2)                          # lock and key bits
    for _ in range(3):                      # literal, distance and length tables: 16 codes of 4 bits
        w.number(16, 5)
        for _ in range(16):
            w.number(4, 4)
    w.number(len(chunks), 16)
    for literal, match in chunks:
        w.value(len(literal))
        if literal:
            w.literals(literal)
            plain += literal
        if match:
            distance, length = match
            w.value(distance - 1)
            w.value(length - 2)
            for _ in range(length):
                plain.append(plain[-distance])
    body = bytes(w.out)
    header = b'RNC\x01' + struct.pack('>IIHHBB', len(plain), len(body), crc16(plain), crc16(body), 0, 1)
    return header + body, bytes(plain)


class ResloadHarnessTest(unittest.TestCase):
    def test_the_authored_harness_passes(self):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        with tempfile.TemporaryDirectory(prefix='rr-amiga-resload-') as temp:
            project = Path(temp)
            native = (ROOT / 'native/amiga_whdload').as_posix()
            (project / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                'project(ResloadChecks LANGUAGES C)\n'
                'set(CMAKE_C_STANDARD 11)\n'
                f'add_executable(resload-checks "{ROOT.as_posix()}/tests/amiga_resload_harness.c" "{native}/rr_resload.c"'
                f' "{native}/rr_decrunch.c")\n'
                f'target_include_directories(resload-checks PRIVATE "{native}")\n'
                'if(MSVC)\n'
                'target_compile_options(resload-checks PRIVATE /W4 /WX /utf-8)\n'
                'target_compile_definitions(resload-checks PRIVATE _CRT_SECURE_NO_WARNINGS)\n'
                'else()\n'
                'target_compile_options(resload-checks PRIVATE -Wall -Wextra -Werror)\n'
                'endif()\n', encoding='utf-8')
            packed, plain = rnc1([(b'WHDLoad install data, ', (22, 40)), (b'0123456789', (3, 9)),
                                  (bytes(range(200)), (200, 300)), (b'end of file', None)])
            (project / 'packed.rnc').write_bytes(packed)
            (project / 'plain.bin').write_bytes(plain)
            cmake, generator = toolchain()
            for command in ([str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator,
                             *cmake_target_args()],
                            [str(cmake), '--build', str(project / 'build'), '--config', 'Release']):
                built = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(build_executable(project / 'build', 'resload-checks')),
                                     str(project / 'packed.rnc'), str(project / 'plain.bin')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('OK (0 failures)', result.stdout)

    def test_the_rnc1_writer_packs_what_it_says(self):
        packed, plain = rnc1([(b'abc', (3, 6)), (b'', None)])
        self.assertEqual(plain, b'abcabcabc')
        self.assertEqual(packed[:4], b'RNC\x01')
        self.assertEqual(struct.unpack('>I', packed[4:8])[0], 9)


if __name__ == '__main__':
    unittest.main()
