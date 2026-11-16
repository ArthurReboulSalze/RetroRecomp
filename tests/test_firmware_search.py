"""Find firmware in a folder (retrorecomp/firmware_search.py, retrorecomp/gui_firmware.py).

Every file here is synthetic: a few authored bytes that pass the converter's own structural checks (a Kickstart header, a TOS
header, MSX ROM signatures), or, for the checks that rest on the digests of real images, a recogniser patched to accept a
marker. No firmware byte is in the repository."""
import hashlib
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from retrorecomp import firmware_search as fs
from retrorecomp.systems import get_profile


def kickstart(size=256 * 1024, fill=0):
    return bytes([0x11, 0x14, 0x4E, 0xF9]) + bytes([fill]) * (size - 4)


def tos(version=0x0104, country=3):
    blob = bytearray(192 * 1024)
    blob[0] = 0x60
    blob[2:4] = version.to_bytes(2, 'big')
    blob[8:12] = (0xFC0000).to_bytes(4, 'big')
    blob[0x1D] = country << 1
    return bytes(blob)


def msx_main(generation, fill=0):
    blob = bytearray([fill]) * 0x8000
    blob[0], blob[1], blob[0x2D] = 0xF3, 0xC3, generation
    return bytes(blob)


def sixteen(head, fill=0, signature=b''):
    blob = bytearray([fill]) * 0x4000
    blob[:len(head)] = head
    if signature:
        blob[0x18:0x18 + len(signature)] = signature
    return bytes(blob)


class Folder:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def close(self):
        self.temp.cleanup()


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.folder = Folder()
        self.addCleanup(self.folder.close)

    def test_renamed_files_in_nested_folders_are_found_by_content_and_junk_is_ignored(self):
        f = self.folder
        f.write('deep/er/whatever.dat', kickstart())
        f.write('st/tos-uk.img', tos(0x0104, 3))
        f.write('st/tos-de.img', tos(0x0102, 1))
        f.write('msx/a.rom', msx_main(0))
        f.write('msx/b.bin', msx_main(2))
        f.write('msx/c.bin', sixteen(b'AB', signature=b'APRLOPLL'))
        f.write('junk/kick34005.A500', bytes(256 * 1024))          # the right name and size, not a Kickstart
        f.write('junk/scph5501.bin', bytes(512 * 1024))             # the right name and size, not a PlayStation BIOS
        f.write('junk/notes.txt', b'hello')
        result = fs.search(f.root)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.files, 9)
        self.assertEqual([h.path for h in result.hits['amiga_kickstart']], [f.root / 'deep/er'])   # a folder: the machine reads it
        self.assertEqual([h.path for h in result.hits['atarist_tos']], [f.root / 'st'])
        self.assertIn('TOS 1.04 (United Kingdom)', result.hits['atarist_tos'][0].role)
        self.assertEqual(result.hits['msx_bios'][0].path, f.root / 'msx/a.rom')
        self.assertEqual(result.hits['msx2plus_bios'][0].path, f.root / 'msx/b.bin')
        self.assertEqual(result.hits['msx2plus_fmbios'][0].path, f.root / 'msx/c.bin')
        for option in ('psx_bios', 'gba_bios', 'ng_bios', 'qsound_rom', 'x68_ipl', 'msx2_bios'):
            self.assertNotIn(option, result.hits)

    def test_a_digest_table_entry_and_a_patched_recogniser_find_their_files(self):
        f = self.folder
        ipl = f.write('keropi/anything.bin', b'\x01' * (128 * 1024))
        with patch.dict(fs.KNOWN_DIGESTS, {hashlib.sha1(ipl.read_bytes()).hexdigest(): ('x68_ipl', 'IPL test', 0)}):
            result = fs.search(f.root)
        self.assertEqual([(h.path, h.role) for h in result.hits['x68_ipl']], [(ipl, 'IPL test')])
        self.assertNotIn('x68_cgrom', result.hits)
        f.write('gba/agb.rom', b'\x02' * (16 * 1024))
        with patch('retrorecomp.gba.bios_status', side_effect=lambda path: 'known' if path.name == 'agb.rom' else 'unknown'):
            self.assertEqual(fs.search(f.root).hits['gba_bios'][0].path, f.root / 'gba/agb.rom')

    def test_the_converter_preference_comes_first_and_equal_choices_are_ambiguous(self):
        f = self.folder
        f.write('a/x.rom', kickstart(fill=1))
        f.write('b/y.rom', kickstart(fill=2))
        f.write('b/z.rom', kickstart(fill=3))
        hits = fs.search(f.root).hits['amiga_kickstart']
        self.assertEqual([h.path for h in hits], [f.root / 'b', f.root / 'a'])     # the folder with more images first
        f.write('m/one.rom', msx_main(1, fill=1))
        f.write('n/two.rom', msx_main(1, fill=2))
        f.write('n/copy.rom', msx_main(1, fill=2))
        result = fs.search(f.root)
        lines, _ = fs.review(result, {})
        line = next(line for line in lines if line.option == 'msx2_bios')
        self.assertTrue(line.ambiguous)
        self.assertFalse(line.ticked)            # the player chooses: nothing is ticked for him

    def test_c_bios_is_not_proposed(self):
        from retrorecomp.msx_cbios import MEMBERS
        blob = msx_main(0, fill=7)
        with patch.dict(MEMBERS, {'cbios_main_msx1.rom': (len(blob), hashlib.sha256(blob).hexdigest())}):
            self.folder.write('cbios_main_msx1.rom', blob)
            self.assertNotIn('msx_bios', fs.search(self.folder.root).hits)
        other = bytearray(msx_main(1, fill=9))           # another C-BIOS release: its own name in its text
        other[0x1000:0x1006] = b'C-BIOS'
        self.folder.write('renamed/msx2.rom', bytes(other))
        self.assertNotIn('msx2_bios', fs.search(self.folder.root).hits)

    def test_the_music_bios_beside_the_msx2_plus_bios_is_preferred(self):
        f = self.folder
        f.write('home/main.rom', msx_main(2))
        f.write('home/fm.rom', sixteen(b'AB', fill=1, signature=b'APRLOPLL'))
        f.write('other/fm.rom', sixteen(b'AB', fill=2, signature=b'APRLOPLL'))
        lines, _ = fs.review(fs.search(f.root), {})
        line = next(line for line in lines if line.option == 'msx2plus_fmbios')
        self.assertEqual([h.path for h in line.candidates], [f.root / 'home/fm.rom', f.root / 'other/fm.rom'])
        self.assertFalse(line.ambiguous)
        self.assertTrue(line.ticked)

    def test_the_msx2_plus_extras_are_proposed_only_beside_its_bios_and_the_sub_rom_with_its_main_rom(self):
        f = self.folder
        f.write('plus/main.rom', msx_main(2))
        f.write('plus/sub.rom', sixteen(b'CD'))
        f.write('plus/disk.rom', sixteen(b'AB', fill=1))
        f.write('elsewhere/disk.rom', sixteen(b'AB', fill=2))       # an "AB" ROM far from any MSX BIOS: not proposed
        result = fs.search(f.root)
        self.assertEqual([h.path for h in result.hits['msx2plus_subrom']], [f.root / 'plus/sub.rom'])
        self.assertEqual([h.path for h in result.hits['msx2plus_diskrom']], [f.root / 'plus/disk.rom'])
        self.assertNotIn('msx2_subrom', result.hits)                # no MSX2 main ROM: no MSX2 pair to check
        f.write('shared/main2.rom', msx_main(2, fill=3))             # a second MSX2+ BIOS, its sub-ROM beside it
        f.write('shared/sub2.rom', sixteen(b'CD', fill=3))
        f.write('shared/disk2.rom', sixteen(b'AB', fill=3))
        result = fs.search(f.root)
        self.assertEqual([h.path for h in result.hits['msx2plus_diskrom']], [f.root / 'plus/disk.rom'])   # the home only
        (f.root / 'plus/sub.rom').unlink()
        result = fs.search(f.root)                                  # no sub-ROM at home: the other MSX2+ folder
        self.assertEqual([h.path for h in result.hits['msx2plus_subrom']], [f.root / 'shared/sub2.rom'])
        self.assertEqual(result.hits['msx2plus_subrom'][0].rank, (1,))

    @unittest.skipUnless(hasattr(os, 'symlink'), 'no symbolic links here')
    def test_a_link_is_not_followed(self):
        outside = Folder()
        self.addCleanup(outside.close)
        outside.write('kick.rom', kickstart())
        try:
            os.symlink(outside.root, self.folder.root / 'link', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links need a privilege here')
        result = fs.search(self.folder.root)
        self.assertEqual(result.links, 1)
        self.assertNotIn('amiga_kickstart', result.hits)

    @unittest.skipUnless(os.name == 'nt', 'junctions are a Windows feature')
    def test_a_real_junction_is_not_followed(self):
        import _winapi
        outside = Folder()
        self.addCleanup(outside.close)
        outside.write('kick.rom', kickstart())
        junction = self.folder.root / 'junction'
        _winapi.CreateJunction(str(outside.root), str(junction))
        self.addCleanup(lambda: junction.exists() and os.rmdir(junction))   # the link only, before the folders go
        result = fs.search(self.folder.root)
        self.assertEqual(result.links, 1)
        self.assertNotIn('amiga_kickstart', result.hits)

    def test_a_junction_or_reparse_point_is_not_followed(self):
        entry = Mock(is_symlink=Mock(return_value=False), is_junction=Mock(return_value=True))
        self.assertTrue(fs._reparse(entry))
        entry = Mock(is_symlink=Mock(return_value=False), is_junction=Mock(return_value=False))
        entry.stat.return_value = Mock(st_file_attributes=0x400)
        self.assertTrue(fs._reparse(entry))
        entry.stat.return_value = Mock(st_file_attributes=0x10)
        self.assertFalse(fs._reparse(entry))

    def test_files_over_the_size_bound_are_not_read(self):
        self.folder.write('big.rom', kickstart())
        with patch.object(fs, 'MAX_FILE_BYTES', 1024), patch('retrorecomp.amiga_kickstart.scan') as scan:
            result = fs.search(self.folder.root)
        scan.assert_not_called()
        self.assertEqual(result.large, 1)
        self.assertEqual(result.hits, {})

    def test_the_file_count_bound_stops_the_walk(self):
        for number in range(5):
            self.folder.write(f'f{number}.txt', b'x')
        with patch.object(fs, 'MAX_FILES', 3):
            result = fs.search(self.folder.root)
        self.assertTrue(result.limited)
        self.assertEqual(result.files, 3)

    def test_cancel_stops_the_search(self):
        self.folder.write('a/kick.rom', kickstart())
        cancel = threading.Event()
        cancel.set()
        result = fs.search(self.folder.root, cancel=cancel)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.hits, {})
        seen = []
        cancel.clear()
        fs.search(self.folder.root, cancel=cancel, progress=lambda files, folder: (seen.append(folder), cancel.set()))
        self.assertEqual(len(seen), 1)

    def test_nothing_is_written_in_the_searched_folder(self):
        self.folder.write('a/kick.rom', kickstart())
        before = sorted((p, p.stat().st_mtime_ns) for p in self.folder.root.rglob('*'))
        fs.search(self.folder.root)
        self.assertEqual(sorted((p, p.stat().st_mtime_ns) for p in self.folder.root.rglob('*')), before)

    def test_every_firmware_option_of_the_profiles_has_a_recogniser(self):
        self.assertEqual(fs.missing_recognisers(), [])
        self.assertEqual(set(fs.RECOGNISERS), {name for name, _, _ in fs.path_options()})


class ReviewTests(unittest.TestCase):
    def result(self, **hits):
        return fs.Search(Path('.'), hits={option: [fs.Hit(option, Path(path), 'role', (rank,), digest)
                                                   for path, rank, digest in values] for option, values in hits.items()})

    def test_an_option_already_set_is_not_ticked_and_says_its_value(self):
        result = self.result(gba_bios=[('found/gba.bin', 0, 'a')], psx_bios=[('found', 0, 'b')])
        lines, missing = fs.review(result, {'gba_bios': 'mine/gba.bin', 'psx_bios': ''})
        by_option = {line.option: line for line in lines}
        self.assertFalse(by_option['gba_bios'].ticked)
        self.assertEqual(by_option['gba_bios'].current, 'mine/gba.bin')
        self.assertTrue(by_option['psx_bios'].ticked)
        self.assertNotIn('gba_bios', [line.option for line in lines if line.ticked])
        self.assertIn('ng_bios_label', [label for label, _ in missing])
        self.assertEqual(by_option['gba_bios'].machines, (get_profile('gba').name,))

    def test_the_same_path_is_recognised_as_already_set(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'gba.bin'  # as given: a runner's temp folder can be an 8.3 short name, and both sides are resolved
            lines, _ = fs.review(self.result(gba_bios=[(str(path), 0, 'a')]), {'gba_bios': str(path)})
        self.assertTrue(lines[0].same)
        self.assertFalse(lines[0].ticked)

    def test_an_option_two_machines_read_names_both(self):
        lines, _ = fs.review(self.result(qsound_rom=[('q.zip', 0, 'a')]), {})
        self.assertEqual(len(lines[0].machines), 2)

    def test_only_the_ticked_options_are_applied_with_the_chosen_candidate(self):
        result = self.result(gba_bios=[('g1', 0, 'a')], psx_bios=[('p1', 0, 'b'), ('p2', 0, 'c')], ng_bios=[('n', 0, 'd')])
        lines, _ = fs.review(result, {})
        values = fs.to_apply(lines, {'gba_bios': True, 'psx_bios': True, 'ng_bios': False}, {'psx_bios': 1})
        self.assertEqual(values, {'gba_bios': 'g1', 'psx_bios': 'p2'})
        self.assertEqual(fs.to_apply(lines, {'psx_bios': True}, {'psx_bios': 9}), {'psx_bios': 'p1'})


class WindowTests(unittest.TestCase):
    def test_apply_writes_only_the_ticked_fields_and_checks_a_verifiable_one(self):
        from retrorecomp.gui_firmware import FirmwareSearchMixin
        app = Mock()
        lines = [fs.Line('ng_bios', 'ng_bios_label', ('Neo Geo',), (fs.Hit('ng_bios', Path('n.zip'), 'r'),), '', False, False,
                         False, True),
                 fs.Line('gba_bios', 'gba_bios', ('GBA',), (fs.Hit('gba_bios', Path('a'), 'r'), fs.Hit('gba_bios', Path('b'), 'r')),
                         'set', False, False, False, False),
                 fs.Line('psx_bios', 'psx_bios', ('PS',), (fs.Hit('psx_bios', Path('p1'), 'r'), fs.Hit('psx_bios', Path('p2'), 'r')),
                         '', False, True, False, False)]
        controls = {'ng_bios': (Mock(get=Mock(return_value=True)), None),
                    'gba_bios': (Mock(get=Mock(return_value=False)), Mock(current=Mock(return_value=1))),
                    'psx_bios': (Mock(get=Mock(return_value=True)), Mock(current=Mock(return_value=1)))}
        values = FirmwareSearchMixin.apply_firmware_choices(app, lines, controls)
        self.assertEqual(values, {'ng_bios': 'n.zip', 'psx_bios': 'p2'})
        app.ng_bios.set.assert_called_once_with('n.zip')
        app.psx_bios.set.assert_called_once_with('p2')
        app.gba_bios.set.assert_not_called()
        app.check_firmware.assert_called_once_with('ng_bios')       # the Neo Geo row has a Check button

    def test_the_review_is_built_with_one_checkbox_per_line_in_a_hidden_window(self):
        import tkinter as tk
        from retrorecomp.gui_firmware import FirmwareSearchMixin
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()                     # never shown
        self.addCleanup(root.destroy)
        app = Mock(ui_font='TkDefaultFont')
        app.tr = lambda key, **values: key
        app.option_text = lambda label: label
        result = fs.Search(Path('.'), files=12)
        lines, missing = fs.review(fs.Search(Path('.'), hits={
            'gba_bios': [fs.Hit('gba_bios', Path('g'), 'GBA BIOS', (0,), 'a')],
            'psx_bios': [fs.Hit('psx_bios', Path('p1'), 'SCPH', (0,), 'b'), fs.Hit('psx_bios', Path('p2'), 'SCPH', (0,), 'c')]}),
            {'gba_bios': 'already/here.bin'})
        body = tk.Frame(root)
        controls = FirmwareSearchMixin.build_firmware_review(app, body, result, lines, missing, close=lambda: None)
        self.assertEqual(set(controls), {'gba_bios', 'psx_bios'})
        self.assertFalse(controls['gba_bios'][0].get())       # already set: not ticked
        self.assertFalse(controls['psx_bios'][0].get())       # two different images, same preference: the player chooses
        self.assertEqual(controls['psx_bios'][1].current(), 0)
        self.assertIsNone(controls['gba_bios'][1])


if __name__ == '__main__':
    unittest.main()
