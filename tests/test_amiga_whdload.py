"""WHDLoad slave and install reader, on a synthetic slave written by the test (authored words, no game, no ROM)."""
import struct
import unittest

from retrorecomp import amiga_whdload as W
from tests.test_amiga_lha import level1


def slave_code(version=17, flags=0x1002, base=0x80000, exp=0x1000, kick=None, current='data/'):
    """A slave's first hunk: the ws_ header, its strings, a two-instruction game loader."""
    strings = bytearray()
    out = {}

    def text(key, value):
        out[key] = 0x60 + len(strings)
        strings.extend(value + b'\x00')
    text('dir', current.encode())
    text('name', b'Synthetic Game')
    text('copy', b'2026 Retro-Recomp tests')
    text('info', b'installed by\xffthe test')
    kick_ptr = kick_size = kick_crc = 0
    if kick:
        kick_size = 0x40000
        if len(kick) == 1:
            text('kick', kick[0].encode())
            kick_ptr, kick_crc = out['kick'], 0x1234
        else:
            for k, name in enumerate(kick):
                text('k%d' % k, name.encode())
            out['list'] = 0x60 + len(strings) + (-(0x60 + len(strings)) % 2)
            strings.extend(b'\x00' * (out['list'] - 0x60 - len(strings)))
            for k, _ in enumerate(kick):
                strings.extend(struct.pack('>HH', 0x1111 * (k + 1), out['k%d' % k]))
            strings.extend(b'\x00\x00')
            kick_ptr, kick_crc = out['list'], 0xFFFF
    header = bytearray(0x60)
    header[0:4] = bytes.fromhex('70ff4e75')            # moveq #-1,d0 / rts
    header[4:12] = b'WHDLOADS'
    struct.pack_into('>HHIIHHH', header, 12, version, flags, base, 0, 0x58, out['dir'], 0)
    header[30], header[31] = 0x5f, 0x59
    struct.pack_into('>iHHHHIHH', header, 32, exp, out['name'], out['copy'], out['info'], kick_ptr, kick_size, kick_crc, 0)
    header[0x58:0x5c] = bytes.fromhex('41fa0000')      # lea (pc),a0 (game loader, never run here)
    header[0x5c:0x60] = bytes.fromhex('4e754e71')
    code = bytes(header) + bytes(strings)
    return code + b'\x00' * (-len(code) % 4)


def hunk_file(code, data=b'\x00\x00\x00\x08\x00\x00\x00\x00', bss_longs=4):
    longs = lambda b: len(b) // 4
    out = struct.pack('>IIIII', 0x3F3, 0, 3, 0, 2)
    out += struct.pack('>III', longs(code), longs(data) | W.MEM_CHIP, bss_longs)
    out += struct.pack('>II', 0x3E9, longs(code)) + code
    out += struct.pack('>IIII', 0x3EC, 1, 1, 0x5c) + struct.pack('>I', 0)          # pointer at 0x5c of code -> data hunk
    out += struct.pack('>II', 0x3F0, 1) + b'main' + struct.pack('>II', 0x58, 0)     # one symbol
    out += struct.pack('>I', 0x3F2)
    out += struct.pack('>II', 0x3EA, longs(data)) + data
    short = struct.pack('>HHH', 1, 0, 0) + struct.pack('>H', 0)                     # data offset 0 -> code hunk
    out += struct.pack('>I', 0x3FC) + short + b'\x00' * (-len(short) % 4)
    out += struct.pack('>I', 0x3F2)
    out += struct.pack('>II', 0x3EB, bss_longs) + struct.pack('>I', 0x3F2)
    return out


class SlaveTest(unittest.TestCase):
    def test_hunks_relocations_and_bss(self):
        loaded = W.hunks(hunk_file(slave_code()))
        self.assertEqual([h.kind for h in loaded], ['code', 'data', 'bss'])
        self.assertEqual(loaded[1].memory, 'chip')
        self.assertEqual(loaded[0].relocs, {1: [0x5c]})
        self.assertEqual(loaded[1].relocs, {0: [0]})
        self.assertEqual(loaded[2].size, 16)
        images = W.relocate(loaded, [0x1000, 0x20000, 0x30000])
        self.assertEqual(images[0][0x5c:0x60], struct.pack('>I', (0x4e754e71 + 0x20000) & 0xFFFFFFFF))
        self.assertEqual(images[1][0:4], struct.pack('>I', 8 + 0x1000))
        self.assertEqual(images[2], bytes(16))

    def test_header_fields_by_version(self):
        s = W.slave_header(W.hunks(hunk_file(slave_code())))
        self.assertEqual((s.version, s.base_mem, s.exp_mem, s.game_loader), (17, 0x80000, 0x1000, 0x58))
        self.assertEqual(s.flag_names, ('NoError', 'ClearMem'))
        self.assertEqual((s.current_dir, s.name, s.info), ('data/', 'Synthetic Game', 'installed by\nthe test'))
        self.assertEqual((s.key_debug, s.key_exit), (0x5f, 0x59))
        self.assertFalse(s.kickemu)
        old = W.slave_header(W.hunks(hunk_file(slave_code(version=7))))
        self.assertEqual((old.exp_mem, old.name, old.kick_names), (0, '', ()))   # fields a v7 slave does not define

    def test_kickemu_names_single_and_list(self):
        one = W.slave_header(W.hunks(hunk_file(slave_code(kick=['34005.a500']))))
        self.assertEqual((one.kick_names, one.kick_size, one.kickemu), (('34005.a500',), 0x40000, True))
        many = W.slave_header(W.hunks(hunk_file(slave_code(kick=['40068.a1200', '40068.a4000']))))
        self.assertEqual(many.kick_names, ('40068.a1200', '40068.a4000'))

    def test_not_a_slave(self):
        code = bytearray(slave_code())
        code[4:12] = b'NOTASLAV'
        with self.assertRaisesRegex(W.InstallError, 'WHDLOADS'):
            W.slave_header(W.hunks(hunk_file(bytes(code))))
        with self.assertRaisesRegex(W.InstallError, 'not an AmigaDOS'):
            W.hunks(b'\x00' * 32)

    def test_a_relocation_outside_its_hunk_is_refused(self):
        blob = bytearray(hunk_file(slave_code()))
        at = blob.find(struct.pack('>IIII', 0x3EC, 1, 1, 0x5c))
        struct.pack_into('>I', blob, at + 12, 0x10000)
        with self.assertRaisesRegex(W.InstallError, 'relocation outside'):
            W.hunks(bytes(blob))


class InstallTest(unittest.TestCase):
    def archive(self, slaves=('Game/Game.Slave',)):
        blob = b''
        for name in slaves:
            blob += level1(name, hunk_file(slave_code()))
        for name, data in (('Game.info', b'icon'), ('Game/ReadMe', b'r'), ('Game/data/Disk.1', b'\x01' * 64),
                           ('Game/data/disk.2', b'\x02' * 64), ('Game/data/levels/l1', b'L'), ('Game/data/x.info', b'i')):
            blob += level1(name, data)
        return blob + b'\x00'

    def test_the_slave_icon_gives_custom1_to_5(self):
        def tool(text):                 # a DiskObject string: its 32-bit length, then the bytes with the NUL
            raw = text.encode('latin-1') + b'\x00'
            return struct.pack('>I', len(raw)) + raw
        icon = (b'\xe3\x10\x00\x01' + b'\x00' * 74 + tool('WHDLoad') + struct.pack('>I', 20) +
                tool('SLAVE=Game.Slave') + tool('CUSTOM1=2') + tool('CUSTOM3=$10') + tool('(CUSTOM2=7)') + tool('CUSTOM5=0x20'))
        blob = level1('Game/Game.Slave', hunk_file(slave_code())) + level1('Game/Game.info', icon) + level1('Game/data/f', b'x') + b'\x00'
        install = W.install(blob)
        self.assertEqual(W.custom_options(blob, install), (2, 0, 16, 0, 32))   # a ToolType in parentheses is switched off
        self.assertEqual(W.icon_strings(icon)[:2], ['WHDLoad', 'SLAVE=Game.Slave'])
        bare = level1('Game/Game.Slave', hunk_file(slave_code())) + level1('Game/data/f', b'x') + b'\x00'
        self.assertEqual(W.custom_options(bare, W.install(bare)), (0, 0, 0, 0, 0))   # no icon: all 0, as WHDLoad without ToolTypes

    def test_data_folder_disks_and_files(self):
        i = W.install(self.archive())
        self.assertEqual((i.slave_path, i.data_dir), ('Game/Game.Slave', 'Game/data'))
        self.assertEqual(sorted(i.disks), [1, 2])
        self.assertEqual(sorted(i.files), ['Disk.1', 'disk.2', 'levels/l1'])   # icons beside the data are not data

    def test_the_data_folder_is_found_whatever_its_case(self):
        blob = level1('Game/Game.Slave', hunk_file(slave_code(current='DATA/'))) + level1('Game/data/Disk.1', b'x') + b'\x00'
        i = W.install(blob)
        self.assertEqual((i.data_dir, sorted(i.disks)), ('Game/data', [1]))

    def test_a_slave_kept_inside_its_data_folder(self):
        blob = level1('Game/data/Game.slave', hunk_file(slave_code(current='data'))) + level1('Game/data/Disk.1', b'x')
        self.assertEqual(W.install(blob + b'\x00').data_dir, 'Game/data')

    def test_an_absolute_developer_path_falls_back_to_its_last_part(self):
        code = slave_code(current='SOURCES:WHD_Slaves/Game/data')
        blob = level1('Game/Game.Slave', hunk_file(code)) + level1('Game/data/main', b'x') + b'\x00'
        self.assertEqual(sorted(W.install(blob).files), ['main'])

    def test_a_collection_of_slaves_needs_a_choice(self):
        blob = self.archive(('Games/Disk1.Slave', 'Games/Disk2.Slave'))
        with self.assertRaisesRegex(W.InstallError, 'choose one slave'):
            W.install(blob)
        chosen = W.install(blob, 'Games/Disk2.Slave')
        self.assertEqual(chosen.other_slaves, ('Games/Disk1.Slave',))

    def test_the_slave_named_as_its_folder_is_the_game(self):
        blob = self.archive(('Game/GameIntro.Slave', 'Game/Game.Slave'))
        chosen = W.install(blob)
        self.assertEqual((chosen.slave_path, chosen.other_slaves), ('Game/Game.Slave', ('Game/GameIntro.Slave',)))
        two = self.archive(('Game/Game.Slave', 'Game/more/Game.Slave'))           # two of that name: refused, never guessed
        with self.assertRaisesRegex(W.InstallError, 'choose one slave'):
            W.install(two)

    def test_no_slave(self):
        with self.assertRaisesRegex(W.InstallError, 'no WHDLoad slave'):
            W.install(level1('Game/ReadMe', b'r') + b'\x00')


if __name__ == '__main__':
    unittest.main()
