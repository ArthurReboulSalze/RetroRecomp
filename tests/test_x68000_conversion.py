"""Converter boundaries with authored disks/firmware, never commercial bytes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.x68000 import read_input, machine, developer_available, automatic_disk_changes
from retrorecomp.x68000_media import XDF_BYTES, IPL_BYTES, CGROM_BYTES
from retrorecomp import x68000_conversion as conversion
from retrorecomp.x68000_conversion import payload, compact_observations, extend_observations
from retrorecomp.core import ConversionError


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Long form: the Windows runner spells the temporary folder RUNNER~1, the converter resolves it.
        self.root = Path(self.temp.name).resolve()
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

    def test_ipl_observations_become_span_entries_and_progress_counts_them(self):
        ipl=bytes(range(256))*512
        word=ipl[0x100:0x102].hex()
        record={'schema':1,'truncated':False,'source_identity':'a'*64,'variants':[
            {'pc':0xff0100,'words':word,'hits':5},{'pc':0x1000,'words':'303c1234','hits':1}]}
        folded=compact_observations(record,ipl)
        self.assertEqual(folded['schema'],2)
        self.assertEqual([v['pc'] for v in folded['variants']],[0x1000])
        self.assertEqual(folded['spans'][0]['entries'],[[0x10100,1]])
        self.assertEqual(folded['spans'][0]['address'],0xfe0000)
        self.assertEqual(compact_observations(folded),folded)           # spans pass through without an IPL
        self.assertEqual(compact_observations(folded,ipl),folded)       # and folding again changes nothing
        again,progress=extend_observations(folded,record,ipl)
        self.assertFalse(progress)
        new={'schema':1,'truncated':False,'variants':[{'pc':0xff0102,'words':ipl[0x102:0x104].hex(),'hits':1}]}
        again,progress=extend_observations(folded,new,ipl)
        self.assertTrue(progress)
        self.assertEqual(len(again['spans'][0]['entries']),2)
        self.assertEqual(len(record['variants']),2)
        with self.assertRaises(ConversionError):extend_observations(folded,new,b'x'*len(ipl))   # another IPL

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
        # Two identities, each with its job: the game (disk set) names the feedback, the machine the saves.
        self.assertIn('RR_FEEDBACK_IDENTITY "'+source.game_key+'"',(out/'runtime_feedback_config.h').read_text())
        self.assertIn('RR_X68K_SOURCE_IDENTITY "'+m.sha256+'"',header)
        self.assertNotEqual(source.game_key,m.sha256)
        self.assertEqual((out/'export-marker.bin').read_bytes(),b'[Retro-Recomp]\0'+source.sha256.encode()+b'\0')
        for p,data in before.items(): self.assertEqual(p.read_bytes(),data)
        self.assertEqual((out/'blob-300.bin').read_bytes(),before[source.disks[0]])
        self.assertIn('Sharp X68000',(out/'game_metadata.rc').read_text())


    def memory_places(self):
        """A library and a converter folder of their own; returns (library x68 folder, converter folder)."""
        environment = patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(self.root/'library')})
        environment.start(); self.addCleanup(environment.stop)
        folder = self.root/'converter'
        setting = patch('retrorecomp.x68000_conversion.ROOT', folder)
        setting.start(); self.addCleanup(setting.stop)
        return self.root/'library'/'x68', folder

    def legacy_pair(self, folder, manifest, *, sdk='old-sdk', identity=None, content=b'{"observations": 1}\n'):
        """The pair a converter before 1.6.0 left in datas/x68000-development/<machine hash>/."""
        old = folder/conversion.LEGACY_MEMORY/manifest.sha256
        old.mkdir(parents=True)
        (old/'converter-observations.json').write_bytes(content)
        (old/'converter-qualification.json').write_text(json.dumps({
            'schema': 1, 'source_identity': identity or manifest.sha256, 'sdk': sdk,
            'observations_sha256': hashlib.sha256(content).hexdigest()}))
        return old

    def test_observations_live_under_the_game_in_the_library_and_the_old_pair_is_copied_not_moved(self):
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        old = self.legacy_pair(converter, m)
        target = conversion.machine_memory(source, m)
        self.assertEqual(target, library/source.game_key/m.sha256[:16])
        self.assertEqual(conversion.adopt_legacy_memory(source, m, emit=lambda message: None), target)
        for name in conversion.OBSERVATION_FILES:
            self.assertEqual((target/name).read_bytes(), (old/name).read_bytes())
            self.assertTrue((old/name).is_file())
        self.assertEqual(conversion.reusable_observations(target, m), target/'converter-observations.json')
        # The next conversion reads the library copy and leaves a changed old pair alone.
        (old/'converter-observations.json').write_bytes(b'{}')
        self.assertEqual(conversion.adopt_legacy_memory(source, m), target)
        self.assertNotEqual((target/'converter-observations.json').read_bytes(), b'{}')

    def test_old_pair_is_read_in_place_when_the_copy_is_impossible(self):
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        old = self.legacy_pair(converter, m)
        with patch.object(conversion, '_copy_file', side_effect=OSError('read-only')):
            self.assertEqual(conversion.adopt_legacy_memory(source, m), old)
        self.assertEqual(conversion.reusable_observations(old, m), old/'converter-observations.json')
        self.assertTrue((old/'converter-qualification.json').is_file())

    def test_unreadable_observations_stop_with_a_conversion_error_and_stay_unchanged(self):
        from retrorecomp.core import ConversionError
        path = self.root/'converter-observations.json'
        path.write_text('{"schema": 99}')
        class Native:
            @staticmethod
            def observations(paths, ipl):
                raise ValueError('CPU observations are incomplete or unknown.')
        with self.assertRaisesRegex(ConversionError, 'kept unchanged'):
            conversion._read_observations(Native, [path], b'')
        self.assertEqual(path.read_text(), '{"schema": 99}')

    def test_a_legacy_summary_that_is_not_an_object_never_stops_the_conversion(self):
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        legacy = library/m.sha256/'compilation.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('[1, 2]')
        self.assertEqual(conversion.adopt_legacy_summary(source, m), library/source.game_key/'compilation.json')
        self.assertTrue(legacy.is_file())     # not understood, so left as it is

    def test_the_copy_reaches_the_disk_before_its_name_and_waits_for_a_busy_target(self):
        library, converter = self.memory_places()
        source = self.root/'source.json'; source.write_bytes(b'{"observations": 3}\n')
        target = self.root/'copy'/'converter-observations.json'
        busy = PermissionError(13, 'busy'); busy.winerror = 32
        real = os.replace
        calls = []
        def replace(a, b):
            calls.append(b)
            if len(calls) == 1:
                raise busy
            return real(a, b)
        with patch('retrorecomp.x68000_conversion.os.fsync') as fsync, \
                patch('retrorecomp.x68000_conversion.os.replace', side_effect=replace):
            conversion._copy_file(source, target)
        fsync.assert_called_once()
        self.assertEqual(len(calls), 2)
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual([path.name for path in target.parent.iterdir()], [target.name])

    def test_a_receipt_of_another_machine_or_another_file_is_not_reused_but_the_sdk_is_not_compared(self):
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        self.ipl.write_bytes(b'G'*IPL_BYTES)
        _, other = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        self.assertNotEqual(m.sha256, other.sha256)
        old = self.legacy_pair(converter, m, sdk='an-engine-that-no-longer-exists')
        self.assertIsNotNone(conversion.reusable_observations(old, m))     # sdk differs: still reusable
        self.assertIsNone(conversion.reusable_observations(old, other))    # another IPL: a machine of its own
        (old/'converter-observations.json').write_bytes(b'{"observations": 2}\n')
        self.assertIsNone(conversion.reusable_observations(old, m))        # not the file the receipt names
        (old/'converter-qualification.json').write_text('not json')
        self.assertIsNone(conversion.reusable_observations(old, m))

    def test_the_summary_written_under_the_machine_hash_moves_to_the_game(self):
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        legacy = library/m.sha256/'compilation.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text(json.dumps({'schema': 1, 'title': 'Authored', 'mouse_controls': True,
                                      'rom_sha256': source.sha256, 'source_identity': m.sha256}))
        summary = conversion.adopt_legacy_summary(source, m)
        self.assertEqual(summary, library/source.game_key/'compilation.json')
        record = json.loads(summary.read_text())
        self.assertEqual((record['title'], record['mouse_controls'], record['game']), ('Authored', True, source.game_key))
        self.assertFalse(legacy.exists())
        self.assertFalse(legacy.parent.exists())
        # A summary already written for the game wins; only the remembered mouse use is carried over.
        legacy.parent.mkdir()
        legacy.write_text(json.dumps({'schema': 1, 'title': 'Older', 'mouse_controls': True}))
        (legacy.parent/'keep.txt').write_text('another file of the player')
        summary.write_text(json.dumps({'schema': 1, 'title': 'Newer', 'mouse_controls': False, 'game': source.game_key}))
        conversion.adopt_legacy_summary(source, m)
        record = json.loads(summary.read_text())
        self.assertEqual((record['title'], record['mouse_controls']), ('Newer', True))
        self.assertFalse(legacy.exists())
        self.assertEqual((legacy.parent/'keep.txt').read_text(), 'another file of the player')

    def test_the_memory_view_lists_a_game_once_under_its_game_key(self):
        from retrorecomp.memory_view import summaries
        library, converter = self.memory_places()
        source, m = machine(self.playlist('one.xdf\ntwo.xdf'), self.ipl, self.cgrom)
        entry = conversion.game_entry(source)
        entry.mkdir(parents=True)
        (entry/'compilation.json').write_text(json.dumps({'title': 'Authored', 'guarded_variants': 7}))
        (conversion.machine_memory(source, m)).mkdir()
        rows, _ = summaries('x68', titles={source.game_key: 'From the collection'})
        self.assertEqual([(row['identity'], row['title'], row['entries']) for row in rows],
                         [(source.game_key, 'From the collection', 7)])


if __name__=='__main__': unittest.main()
