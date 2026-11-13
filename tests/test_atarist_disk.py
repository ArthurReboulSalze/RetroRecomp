"""The desktop autostart picks the program of disk 1 from its root directory, and the disks of a set are put in the order their
names mean, on authored disk images written by the test (a boot sector, two FATs and a root directory of a few entries: no game, no
disk of anyone, no TOS) and on made-up disk names."""
import struct
import unittest

from retrorecomp import atarist_disk


def entry(name: str, ext: str, attr: int = 0, size: int = 1000) -> bytes:
    return name.ljust(8).encode() + ext.ljust(3).encode() + bytes([attr]) + bytes(14) + struct.pack('<HI', 2, size)


def st_image(entries: list[bytes], spt: int = 9, heads: int = 2, declared_fats: int = 2) -> bytes:
    """An 80-track ST image whose boot sector has a BPB (512-byte sectors, 2 per cluster, 1 reserved, `declared_fats` FATs of 5 sectors,
    112 root entries) and whose root directory holds the given entries, after two FATs as the TOS reads it."""
    boot = bytearray(512)
    boot[11:19] = struct.pack('<HBHBH', 512, 2, 1, declared_fats, 112)
    boot[19:21] = struct.pack('<H', 80 * spt * heads)
    boot[22:28] = struct.pack('<HHH', 5, spt, heads)
    disk = bytearray(80 * spt * heads * 512)
    disk[:512] = boot
    root = (1 + 2 * 5) * 512
    for n, e in enumerate(entries):
        disk[root + 32 * n:root + 32 * (n + 1)] = e
    return bytes(disk)


def msa_image(st: bytes, spt: int = 9, heads: int = 2) -> bytes:
    """The same disk as an MSA image, every track run-length encoded when it saves room."""
    out = bytearray(b'\x0e\x0f' + struct.pack('>HHHH', spt, heads - 1, 0, 79))
    size = spt * 512
    for t in range(80 * heads):
        track = st[t * size:(t + 1) * size]
        if track == bytes(size):
            packed = b'\xe5\x00' + struct.pack('>H', size)
        else:
            packed = track
        out += struct.pack('>H', len(packed)) + packed
    return bytes(out)


class AutostartTests(unittest.TestCase):
    def test_the_only_program_is_started(self):
        disk = st_image([entry('GAME', 'DAT'), entry('PLAY', 'PRG'), entry('DESKTOP', 'INF')])
        self.assertEqual(atarist_disk.autostart_program(disk, '.st')[0], 'A:\\PLAY.PRG')
        self.assertEqual(atarist_disk.autostart_program(msa_image(disk), 'msa')[0], 'A:\\PLAY.PRG')

    def test_installers_hidden_files_and_deleted_entries_are_not_programs_to_open(self):
        deleted = b'\xe5' + entry('OLD', 'PRG')[1:]
        disk = st_image([entry('INSTALL', 'PRG'), entry('SECRET', 'PRG', attr=0x02), deleted, entry('GAME', 'APP')])
        self.assertEqual(atarist_disk.autostart_program(disk, 'st')[0], 'A:\\GAME.APP')

    def test_two_programs_an_auto_folder_or_no_file_system_mean_no_autostart(self):
        two = st_image([entry('ONE', 'PRG'), entry('TWO', 'TOS')])
        program, reason = atarist_disk.autostart_program(two, 'st')
        self.assertIsNone(program)
        self.assertIn('2 programs (ONE.PRG, TWO.TOS) and no rule picks one', reason)
        auto = st_image([entry('AUTO', '', attr=0x10), entry('GAME', 'PRG')])
        self.assertIsNone(atarist_disk.autostart_program(auto, 'st')[0])
        self.assertIn('AUTO folder', atarist_disk.autostart_program(auto, 'st')[1])
        self.assertIsNone(atarist_disk.autostart_program(bytes(737280), 'st')[0])
        self.assertIsNone(atarist_disk.autostart_program(b'not a disk', 'ipf')[0])
        self.assertIn('STX', atarist_disk.autostart_program(bytes(1000), 'stx')[1])

    def test_the_root_is_read_after_two_fats_whatever_the_bpb_declares(self):
        # Battle Probe, Pharaoh III and Trailblazer declare one FAT and the TOS lists their programs after two: the converter reads where the TOS does.
        disk = st_image([entry('PROBE', 'PRG'), entry('DESKTOP', 'INF')], spt=10, heads=1, declared_fats=1)
        self.assertEqual(atarist_disk.autostart_program(disk, 'st')[0], 'A:\\PROBE.PRG')
        names = [f"{e['name']}.{e['ext']}" for e in atarist_disk.root_entries(atarist_disk.read_sectors(disk, 'st'))]
        self.assertEqual(names, ['PROBE.PRG', 'DESKTOP.INF'])
        # a field that is neither one nor two is no DOS file system, as before
        bad = bytearray(disk)
        bad[16] = 3
        self.assertIn('no DOS file system', atarist_disk.autostart_program(bytes(bad), 'st')[1])

    def test_a_one_sided_disk_is_read_by_its_own_geometry(self):
        disk = st_image([entry('PLAY', 'PRG')], spt=10, heads=1)
        self.assertEqual(atarist_disk.autostart_program(disk, 'st')[0], 'A:\\PLAY.PRG')


class SeveralProgramsTests(unittest.TestCase):
    def decide(self, names, title, attr=0):
        entries = [entry(n.split('.')[0], n.split('.')[1], attr) for n in names]
        return atarist_disk.autostart_decision(st_image(entries), 'st', title)

    def test_the_program_named_like_a_word_of_the_title_is_started(self):
        decision = self.decide(['CRICKET.PRG', 'PUTSCR.TOS'], 'Championship Cricket')
        self.assertEqual((decision['program'], decision['rule']), ('A:\\CRICKET.PRG', 'title-word'))
        self.assertEqual(decision['candidates'], ['CRICKET.PRG', 'PUTSCR.TOS'])
        # a trailing underscore, a short name that is not a word of the title, a Roman numeral
        self.assertEqual(self.decide(['OUTCAST_.PRG', 'RENMUSIC.PRG'], 'Outcast')['program'], 'A:\\OUTCAST_.PRG')
        self.assertEqual(self.decide(['AAA.PRG', 'RODY.PRG'], 'Rody et Mastico III')['program'], 'A:\\RODY.PRG')
        self.assertIsNone(self.decide(['X.PRG', 'III.PRG'], 'Game X III')['program'])

    def test_two_names_that_fit_or_none_leave_the_choice_to_the_player(self):
        both = self.decide(['ESCAPE.TOS', 'SECOND.TOS'], 'Mercenary - Escape from Targ & The Second City')
        self.assertIsNone(both['program'])
        self.assertIn('2 are named like a word of the title', both['reason'])
        none = self.decide(['ARCH.PRG', 'GOLF.PRG'], 'Mean 18')
        self.assertIsNone(none['program'])
        self.assertIsNone(none['rule'])
        self.assertEqual(none['candidates'], ['ARCH.PRG', 'GOLF.PRG'])
        self.assertIn('no rule picks one', none['reason'])
        self.assertIsNone(self.decide(['BG.PRG', 'BG_ENG.PRG', 'BG_FRE.PRG'], 'Backgammon Royale')['program'])

    def test_the_only_program_that_is_not_a_utility_is_started(self):
        decision = self.decide(['PLAY.PRG', 'SETUP.PRG', 'README.TOS'], 'A Game')
        self.assertEqual((decision['program'], decision['rule']), ('A:\\PLAY.PRG', 'only-non-utility'))
        self.assertIsNone(self.decide(['PLAY.PRG', 'MAIN.PRG', 'COPY.TOS'], 'A Game')['program'])
        self.assertIsNone(self.decide(['SETUP.PRG', 'FORMAT.TOS'], 'A Game')['program'])
        self.assertEqual(self.decide(['DOCTOR.PRG', 'SETUP.PRG'], 'A Game')['program'], 'A:\\DOCTOR.PRG')
        # a name list, by exact word: the music program and the level editor are not the game (Conquests of Camelot, Trailblazer), a name that only contains them is
        sierra = self.decide(['MUSIC.PRG', 'SIERRA.PRG'], 'Conquests of Camelot - The Search for the Grail')
        self.assertEqual((sierra['program'], sierra['rule']), ('A:\\SIERRA.PRG', 'only-non-utility'))
        trail = self.decide(['EDITOR.PRG', 'TRAIL.PRG'], 'Trailblazer')
        self.assertEqual((trail['program'], trail['rule']), ('A:\\TRAIL.PRG', 'only-non-utility'))
        self.assertIsNone(self.decide(['MUSIC2.PRG', 'PLAY.PRG'], 'A Game')['program'])
        self.assertIsNone(self.decide(['EDITOR.PRG', 'MUSIC.PRG'], 'A Game')['program'])

    def test_a_lone_program_is_still_started_whatever_its_name(self):
        decision = self.decide(['BACKUP.TOS'], 'Some Game')
        self.assertEqual((decision['program'], decision['rule']), ('A:\\BACKUP.TOS', 'only-program'))

    def test_the_title_words_leave_out_short_words_numerals_and_articles(self):
        self.assertEqual(atarist_disk.title_words('The Lurking Horror II'), {'LURKING', 'HORROR'})

    def test_no_program_and_an_auto_folder_say_so(self):
        self.assertEqual(self.decide([], 'A Game')['candidates'], [])
        self.assertIn('no program', self.decide([], 'A Game')['reason'])
        auto = atarist_disk.autostart_decision(st_image([entry('AUTO', '', attr=0x10), entry('GAME', 'PRG')]), 'st', 'Game')
        self.assertIsNone(auto['program'])


class DiskOrderTests(unittest.TestCase):
    def order(self, *names):
        return atarist_disk.order_disks(list(names))

    def test_numbered_lettered_and_reel_disks_follow_their_number(self):
        for label in ('Disk {}', 'Side {}', 'Reel {}'):
            names = [f'Game (Europe) ({label.format(n)}).ipf' for n in (3, 1, 2)]
            self.assertEqual(self.order(*names), sorted(names))
        names = [f'Game (Europe) (Disk {n}).ipf' for n in (10, 2, 9, 1)]
        self.assertEqual(self.order(*names), [names[3], names[1], names[2], names[0]])
        letters = ['Game (Disk B).ipf', 'Game (Disk C).ipf', 'Game (Disk A).ipf']
        self.assertEqual(self.order(*letters), ['Game (Disk A).ipf', 'Game (Disk B).ipf', 'Game (Disk C).ipf'])

    def test_the_boot_disk_comes_first_whatever_its_name(self):
        self.assertEqual(self.order('Battle Chess (Europe) (Animation Disk).ipf', 'Battle Chess (Europe) (StartUp Disk).ipf'),
                         ['Battle Chess (Europe) (StartUp Disk).ipf', 'Battle Chess (Europe) (Animation Disk).ipf'])
        self.assertEqual(self.order('G (Disk A).ipf', 'G (Disk C).ipf', 'G (Boot Disk).ipf', 'G (Disk B).ipf'),
                         ['G (Boot Disk).ipf', 'G (Disk A).ipf', 'G (Disk B).ipf', 'G (Disk C).ipf'])
        self.assertEqual(self.order('G (Play Disk).ipf', 'G (Boot Disk).ipf'), ['G (Boot Disk).ipf', 'G (Play Disk).ipf'])
        self.assertEqual(self.order('G (Games Disk B).ipf', 'G (Boot Disk A).ipf'), ['G (Boot Disk A).ipf', 'G (Games Disk B).ipf'])

    def test_a_disk_without_a_label_comes_before_the_named_ones(self):
        self.assertEqual(self.order('Chessmaster (Europe) (Games Disk).ipf', 'Chessmaster (Europe).ipf'),
                         ['Chessmaster (Europe).ipf', 'Chessmaster (Europe) (Games Disk).ipf'])
        self.assertEqual(self.order('G (Disk 2).ipf', 'G.ipf'), ['G.ipf', 'G (Disk 2).ipf'])

    def test_a_program_disk_precedes_its_volumes(self):
        names = ['Mean (Famous Courses Disk - Volume II).ipf', 'Mean (Program Disk).ipf', 'Mean (Famous Courses Disk - Volume I).ipf']
        self.assertEqual(self.order(*names), [names[1], names[2], names[0]])

    def test_tags_that_are_not_labels_are_ignored(self):
        names = ['Game (Europe) (v1.1) (Dual Sided) (Disk 2).ipf', 'Game (Europe) (v1.1) (Dual Sided) (Disk 1).ipf']
        self.assertEqual(self.order(*names), [names[1], names[0]])
        names = ['Game (Compilation - Magnum 4) (Disk 2).ipf', 'Game (Compilation - Magnum 4) (Disk 1).ipf']
        self.assertEqual(self.order(*names), [names[1], names[0]])

    def test_names_without_tags_are_read_from_their_end(self):
        self.assertEqual(self.order('game2.st', 'game1.st'), ['game1.st', 'game2.st'])
        self.assertEqual(self.order('game_b.st', 'game_a.st', 'game_c.msa'), ['game_a.st', 'game_b.st', 'game_c.msa'])
        self.assertEqual(self.order('game disk 2.st', 'game disk 1.st'), ['game disk 1.st', 'game disk 2.st'])
        self.assertEqual(self.order('b.st', 'a.st'), ['a.st', 'b.st'])

    def test_unlabelled_names_keep_the_alphabetical_order(self):
        self.assertEqual(self.order('beta.ipf', 'Alpha.ipf', 'gamma.ipf'), ['Alpha.ipf', 'beta.ipf', 'gamma.ipf'])


if __name__ == '__main__':
    unittest.main()
