"""Converter boundaries with authored disks/firmware, never commercial bytes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.x68000 import read_input, machine, developer_available, automatic_disk_changes
from retrorecomp.x68000_media import XDF_BYTES, IPL_BYTES, CGROM_BYTES
from retrorecomp.x68000_conversion import payload, compact_observations, extend_observations
from retrorecomp.core import ConversionError


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, size, byte in [('one.xdf', XDF_BYTES, 1), ('two.xdf', XDF_BYTES, 2),
                                 ('iplrom.dat', IPL_BYTES, 3), ('cgrom.dat', CGROM_BYTES, 4)]:
            (self.root/name).write_bytes(bytes([byte])*size)
        self.ipl = self.root/'iplrom.dat'
        self.cgrom = self.root/'cgrom.dat'

    def playlist(self, text):
        p = self.root/'game.m3u'; p.write_text(text, encoding='utf-8-sig'); return p

    def test_playlist_single_disk_and_direct_disk_identify_same_source(self):
        self.assertEqual(read_input(self.root/'one.xdf').sha256,
                         read_input(self.playlist('#EXTM3U\none.xdf\n')).sha256)

    def test_ordered_set_and_firmware_and_ram_are_separate_exact_identities(self):
        a = read_input(self.playlist('one.xdf\ntwo.xdf\n')).sha256
        self.assertNotEqual(a, read_input(self.playlist('two.xdf\none.xdf\n')).sha256)
        _, m2 = machine(self.root/'one.xdf', self.ipl, self.cgrom, 2)
        _, m4 = machine(self.root/'one.xdf', self.ipl, self.cgrom, 4)
        self.assertNotEqual(m2.sha256, m4.sha256)
        self.ipl.write_bytes(b'F'*IPL_BYTES)
        self.assertNotEqual(m2.sha256, machine(self.root/'one.xdf', self.ipl, self.cgrom, 2)[1].sha256)

    def test_duplicate_disks_and_network_urls_and_commands_are_rejected(self):
        for text in ('one.xdf\none.xdf', 'https://example.org/game.xdf', 'one.xdf\0'):
            with self.assertRaises(ValueError): read_input(self.playlist(text))
        p=self.root/'launch.cmd';p.write_text('not executed')
        with self.assertRaises(ValueError): read_input(p)

    def test_missing_firmware_and_unsupported_ram_fail_before_build(self):
        with self.assertRaisesRegex(ValueError, 'IPL'): machine(self.root/'one.xdf', None, None)
        with self.assertRaisesRegex(ValueError, 'RAM'): machine(self.root/'one.xdf', self.ipl, self.cgrom, 8)

    def test_missing_converter_files_hide_the_profile(self):
        with patch('retrorecomp.x68000.ASSETS', self.root): self.assertFalse(developer_available())

    def test_regeneration_compacts_only_identical_observed_encodings(self):
        record={'schema':1,'truncated':False,'source_identity':'a'*64,'variants':[
            {'pc':0x1000,'words':'303c1234','hits':7},{'pc':0x1000,'words':'303c1234','hits':1},
            {'pc':0x1000,'words':'303c5678','hits':2}]}
        result=compact_observations(record)
        self.assertEqual(result['source_identity'],record['source_identity'])
        self.assertEqual(len(result['variants']),2)
        self.assertEqual(result['variants'][0]['hits'],7)
        self.assertEqual(len(record['variants']),3)
        with self.assertRaises(ConversionError):compact_observations({**record,'truncated':True})

    def test_automatic_disk_requests_cover_every_multi_disk_set(self):
        from dataclasses import replace
        source=read_input(self.root/'one.xdf')
        self.assertFalse(automatic_disk_changes(source))
        # No exact-set gate: any ordered set of two or more disks, whatever
        # its identity, answers the guest's own requests.
        pair=replace(source,disks=(source.path,source.path.with_name('two.xdf')),sha256='a'*64)
        self.assertTrue(automatic_disk_changes(pair))

    def test_generation_progress_requires_a_new_pc_or_encoding_not_more_hits(self):
        record={'schema':1,'truncated':False,'source_identity':'a'*64,'variants':[
            {'pc':0x1000,'words':'303c1234','hits':7}]}
        extra={'schema':1,'truncated':False,'variants':[
            {'pc':0x1000,'words':'303c1234','hits':900}]}
        merged,progress=extend_observations(record,extra)
        self.assertFalse(progress)
        self.assertEqual(merged['variants'][0]['hits'],900)
        extra['variants'].append({'pc':0x1000,'words':'303c5678','hits':1})
        merged,progress=extend_observations(record,extra)
        self.assertTrue(progress)
        self.assertEqual(len(merged['variants']),2)
        self.assertEqual(merged['source_identity'],record['source_identity'])
        self.assertEqual(len(record['variants']),1)

    def test_mouse_controls_follow_the_payload_decision_not_an_exact_set(self):
        from dataclasses import replace
        source=read_input(self.root/'one.xdf')
        _,manifest=machine(self.root/'one.xdf',self.ipl,self.cgrom,2)
        power=replace(source,sha256='06ae8a805f2826bf049febf54aa2734760ac893f95620ee30dcb6c7a60271215')
        for game,expected in ((source,1),(power,0)):
            project=self.root/f'payload-{expected}'
            payload(project,game,manifest,'Game',{},bool(expected))
            self.assertIn(f'#define RR_X68K_MOUSE_GAME {expected}\n',(project/'x68000_payload.h').read_text())

    def test_computer_exploration_clicks_both_mouse_buttons_and_leaves_guest_menus(self):
        from retrorecomp.x68000_scan import exploration_routes
        routes=exploration_routes(8000)
        self.assertEqual(routes,exploration_routes(8000))
        self.assertEqual(len({r.events for r in routes}),2)
        for route in routes:
            self.assertLessEqual(route.frames,6000)
            self.assertLessEqual(len(route.events),4096)
            self.assertTrue(all(0<=e[0]<e[1]<=route.frames for e in route.events))
            self.assertFalse(any(e[2]=='key' and e[3]>=282 for e in route.events))
        mouse=next(r for r in routes if r.name=='mouse')
        self.assertTrue({2,3}<={e[3] for e in mouse.events if e[2]=='mouse'})
        self.assertTrue(any(e[2]=='mouse' and e[3] in (0,1) and e[4]<0 for e in mouse.events))
        keyboard=next(r for r in routes if r.name=='keyboard')
        self.assertTrue({13,27,32}<={e[3] for e in keyboard.events if e[2]=='key'})
        extended=exploration_routes(8000,mouse_controls=True)
        self.assertEqual(extended[0].frames,10000)
        self.assertTrue(any(e[0]>9000 for e in extended[0].events))

    def test_saturated_or_wrong_identity_additional_capture_cannot_be_qualified(self):
        record={'schema':1,'truncated':False,'source_identity':'a'*64,'variants':[]}
        for extra in ({**record,'truncated':True}, {**record,'source_identity':'b'*64}):
            with self.assertRaises(ConversionError):extend_observations(record,extra)

    def test_memory_view_reads_small_summary_without_instruction_data(self):
        from retrorecomp.memory_view import summaries
        p=self.root/('a'*64)/'compilation.json';p.parent.mkdir()
        p.write_text(json.dumps({'title':'Authored X68000','guarded_variants':42}))
        with patch('retrorecomp.memory_view.library_root',return_value=self.root):
            rows,cache=summaries('x68')
        self.assertEqual(rows[0]['entries'],42)
        self.assertEqual(rows[0]['title'],'Authored X68000')

    def test_payload_does_not_modify_inputs_and_preserves_exact_resource_identity(self):
        source,m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl,self.cgrom)
        before={p:p.read_bytes() for p in (*source.disks,self.ipl,self.cgrom)}
        out=self.root/'payload'
        payload(out,source,m,'Authored "X68000" game',{})
        header=(out/'x68000_payload.h').read_text()
        self.assertIn(m.sha256,header)
        self.assertIn('media/disk-01.xdf',header)
        self.assertIn('media/disk-02.xdf',header)
        self.assertIn('"x68"',(out/'runtime_feedback_config.h').read_text())
        self.assertEqual((out/'export-marker.bin').read_bytes(),b'[Retro-Recomp]\0'+source.sha256.encode()+b'\0')
        for p,data in before.items(): self.assertEqual(p.read_bytes(),data)
        self.assertEqual((out/'blob-300.bin').read_bytes(),before[source.disks[0]])
        self.assertIn('Sharp X68000',(out/'game_metadata.rc').read_text())


if __name__=='__main__': unittest.main()
