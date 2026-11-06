"""LHA reader of the Amiga WHDLoad installs, on archives written by the test itself (no game, no ROM)."""
import struct
import unittest

from retrorecomp import amiga_lha


class _BitWriter:
    def __init__(self):
        self.out, self.acc, self.n = bytearray(), 0, 0

    def put(self, value, bits):
        for k in range(bits - 1, -1, -1):
            self.acc = (self.acc << 1) | ((value >> k) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc, self.n = 0, 0

    def bytes(self):
        if self.n:
            self.out.append(self.acc << (8 - self.n))
        return bytes(self.out)


def lh5_stream(symbols, distance_symbol=5):
    """One lh5 block: every literal/length symbol coded on 9 bits (sent through a constant code-length table) and a
    constant distance symbol. `symbols` holds byte values and ('match', length, extra) tuples."""
    w = _BitWriter()
    w.put(len(symbols), 16)
    w.put(0, 5)
    w.put(9 + 2, 5)            # code-length table: one symbol (length 9), zero-bit codes
    w.put(510, 9)              # 510 literal/length lengths follow, each costs zero bits
    w.put(0, 4)
    w.put(distance_symbol, 4)  # distance table: one symbol
    for s in symbols:
        if isinstance(s, tuple):
            _, length, extra = s
            w.put(256 + length - 3, 9)
            w.put(extra, distance_symbol - 1)
        else:
            w.put(s, 9)
    return w.bytes()


def expand(symbols, distance_symbol=5):
    out = bytearray()
    for s in symbols:
        if isinstance(s, tuple):
            _, length, extra = s
            src = len(out) - ((1 << (distance_symbol - 1)) + extra) - 1
            for k in range(length):
                out.append(out[src + k])
        else:
            out.append(s)
    return bytes(out)


def level1(name, data, method='-lh0-', packed=None, comment=b'', directory=None, crc=None):
    packed = data if packed is None else packed
    stored = name.encode('latin-1') + (b'\x00' + comment if comment else b'')
    ext = b''
    if directory is not None:
        # one extended header: type 2 (directory), then the size of the next one (0: last)
        ext = b'\x02' + directory.encode('latin-1').replace(b'/', b'\xff') + struct.pack('<H', 0)
        first = len(ext)
    else:
        first = 0
    base = (method.encode() + struct.pack('<II', len(packed) + len(ext), len(data)) + b'\0\0\0\0' + b'\x20\x01'
            + bytes([len(stored)]) + stored + struct.pack('<H', amiga_lha.crc16(data) if crc is None else crc)
            + b'A' + struct.pack('<H', first))
    header = bytes([len(base), 0]) + base
    return header + ext + packed


def level0(name, data):
    stored = name.encode('latin-1')
    base = (b'-lh0-' + struct.pack('<II', len(data), len(data)) + b'\0\0\0\0' + b'\x20\x00' + bytes([len(stored)])
            + stored + struct.pack('<H', amiga_lha.crc16(data)))
    return bytes([len(base), 0]) + base + data


def level2(name, data, directory):
    exts = []
    for kind, value in ((0x01, name.encode()), (0x02, directory.encode().replace(b'/', b'\xff'))):
        exts.append(bytes([kind]) + value)
    chain = b''
    sizes = [len(e) + 2 for e in exts]
    for k, e in enumerate(exts):
        chain += e + struct.pack('<H', sizes[k + 1] if k + 1 < len(exts) else 0)
    fixed = (b'-lh0-' + struct.pack('<II', len(data), len(data)) + b'\0\0\0\0' + b'\x00\x02'
             + struct.pack('<H', amiga_lha.crc16(data)) + b'A' + struct.pack('<H', sizes[0]))
    total = 2 + len(fixed) + len(chain)
    return struct.pack('<H', total) + fixed + chain + data


class LhaTest(unittest.TestCase):
    def test_crc16_is_the_arc_variant(self):
        self.assertEqual(amiga_lha.crc16(b'123456789'), 0xBB3D)

    def test_level1_stored_member_with_directory_and_comment(self):
        data = b'hello amiga' * 7
        blob = level1('Game.Slave', data, comment=b'v1.2 (2020)', directory='Game/') + b'\x00'
        (m,) = amiga_lha.members(blob)
        self.assertEqual((m.name, m.comment, m.size, m.level), ('Game/Game.Slave', 'v1.2 (2020)', len(data), 1))
        self.assertEqual(amiga_lha.extract(blob, m), data)

    def test_levels_0_and_2_and_several_members(self):
        blob = level0('Readme', b'text') + level2('Disk.1', b'\x11' * 300, 'Game/') + level1('x.info', b'i') + b'\x00'
        names = [m.name for m in amiga_lha.members(blob)]
        self.assertEqual(names, ['Readme', 'Game/Disk.1', 'x.info'])
        disk = amiga_lha.members(blob)[1]
        self.assertEqual(amiga_lha.extract(blob, disk), b'\x11' * 300)

    def test_lh5_literals_and_matches(self):
        symbols = [*b'WHDLoad slave data ', *b'0123456789abcdefghij', ('match', 12, 3), ('match', 40, 15), *b'end']
        data = expand(symbols)
        packed = lh5_stream(symbols)
        blob = level1('d', data, method='-lh5-', packed=packed) + b'\x00'
        (m,) = amiga_lha.members(blob)
        self.assertEqual(amiga_lha.extract(blob, m), data)

    def test_a_wrong_crc_is_refused(self):
        blob = level1('f', b'abc', crc=0x1234) + b'\x00'
        with self.assertRaisesRegex(amiga_lha.LhaError, 'CRC'):
            amiga_lha.extract(blob, amiga_lha.members(blob)[0])

    def test_unknown_methods_and_levels_are_refused_with_their_name(self):
        blob = level1('f', b'abc', method='-lzs-') + b'\x00'
        with self.assertRaisesRegex(amiga_lha.LhaError, '-lzs-'):
            amiga_lha.extract(blob, amiga_lha.members(blob)[0])
        bad = bytearray(level1('f', b'abc'))
        bad[20] = 3                    # the header level byte
        with self.assertRaisesRegex(amiga_lha.LhaError, 'level 3'):
            amiga_lha.members(bytes(bad) + b'\x00')

    def test_a_payload_beyond_the_file_is_refused(self):
        blob = level1('f', b'abcdef')[:-3]
        with self.assertRaises(amiga_lha.LhaError):
            amiga_lha.members(blob)


if __name__ == '__main__':
    unittest.main()
