import hashlib
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR':str(self.root/'bank'),
                                                   'RETRO_RECOMP_BUNDLED_KNOWLEDGE':'0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name, value in (('games_directory', self.root/'default games'),
                            ('preferred_games_root', (self.root/'configured games', False)),
                            ('load_preferences', {})):
            setting = patch('retrorecomp.paths.'+name, return_value=value)
            setting.start()
            self.addCleanup(setting.stop)
        self.identity = 'a'*64

    def save(self, system, rows, identity=None):
        identity = identity or self.identity
        path = self.root/'games/datas/fallbacks'/f'{system}-{identity}.rrfb'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(feedback.encode(rows,system,identity))
        return path

    def test_all_consoles_import_separate_exact_identities(self):
        for system, kinds in feedback.KINDS.items():
            rows = [feedback.Observation(kind, 0x100, 0, b'\x76') for kind in kinds]
            path = self.save(system, rows)
            report = feedback.ingest(system,self.identity,self.root/'games')
            self.assertEqual(report['unique_candidates'],len(kinds))
            self.assertEqual(set(feedback.records(system,self.identity)),set(rows))
            self.assertEqual(feedback.records(system,'b'*64),[])
            # Removing an exported file must not lose imported private hints.
            path.unlink()
            self.assertEqual(set(feedback.records(system,self.identity)),set(rows))

    def test_corrupt_wrong_system_and_oversize_rejected(self):
        row = feedback.Observation(1,0x100,0,b'\x76')
        data = feedback.encode([row],'sms',self.identity)
        for invalid in (data[:-1], data+b'\0',data[:100]+b'\xff'+data[101:], b'0'*(feedback.MAX_BYTES+1)):
            with self.assertRaises(ValueError):feedback.decode(invalid,'sms',self.identity)
        with self.assertRaises(ValueError):feedback.decode(data,'gg',self.identity)
        with self.assertRaises(ValueError):feedback.decode(data,'sms','b'*64)

    def test_relocated_game_search_is_recursive_read_only_and_console_scoped(self):
        moved=self.root/'moved/collection/renamed game/datas/fallbacks'
        moved.mkdir(parents=True)
        file=moved/f'sms-{self.identity}.rrfb'
        row=feedback.Observation(1,0x100,0,b'\x76')
        file.write_bytes(feedback.encode([row],'sms',self.identity))
        before={p:p.stat().st_mtime_ns for p in (self.root/'moved').rglob('*')}
        settings={'feedback_paths':{'sms':str(self.root/'moved')}}
        with patch('retrorecomp.paths.load_preferences',return_value=settings):
            # A conversion with its own library (this test's) reads no folder of the player's.
            self.assertEqual(feedback.ingest('sms',self.identity,self.root/'new output')['unique_candidates'],0)
            with patch('retrorecomp.feedback._isolated',return_value=False):
                self.assertEqual(feedback.ingest('sms',self.identity,self.root/'new output')['unique_candidates'],1)
                self.assertEqual(feedback.ingest('gg',self.identity,self.root/'new output')['unique_candidates'],0)
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in (self.root/'moved').rglob('*')})

    def test_feedback_search_preferences_support_relative_paths_and_ignore_invalid_fields(self):
        from retrorecomp.paths import feedback_search_paths
        with patch('retrorecomp.paths.export_directory',return_value=self.root):
            self.assertEqual(feedback_search_paths({'feedback_paths':{'sms':'Moved/SMS','gb':23,'unknown':'no'}}),
                             {'sms':(self.root/'Moved/SMS').resolve()})
        self.assertEqual(feedback_search_paths({'feedback_paths':[]}),{})

    def test_x68000_feedback_folder_is_kept(self):
        from retrorecomp.paths import feedback_search_paths
        folder=self.root/'x68 games'
        self.assertEqual(feedback_search_paths({'feedback_paths':{'x68':str(folder)}}),{'x68':folder.resolve()})

    def test_saturated_import_keeps_newer_high_address_observations(self):
        old=[feedback.Observation(1,n,0,b'\x76') for n in range(feedback.LIMIT)]
        path=self.save('sms',old)
        feedback.ingest('sms',self.identity,self.root/'games')
        path.unlink()
        new=feedback.Observation(1,0xffff,0,b'\x76')
        self.save('sms',[new])
        feedback.ingest('sms',self.identity,self.root/'games')
        records=feedback.records('sms',self.identity)
        self.assertEqual(len(records),feedback.LIMIT)
        self.assertIn(new,records)

    def test_bulk_import_needs_no_rom_and_survives_source_deletion_and_path_change(self):
        first = feedback.Observation(1,0x100,0,b'\x76')
        second = feedback.Observation(1,0x200,0,b'\xc9')
        a = self.save('sms',[first])
        b = self.save('sms',[second],'b'*64)
        settings = {'feedback_paths':{'sms':str(self.root/'games')}}
        before = {p:p.stat().st_mtime_ns for p in (self.root/'games').rglob('*')}
        report = feedback.import_saved_feedback('sms',settings)
        self.assertEqual((report['games'],report['observations'],report['updated_games']),(2,2,2))
        self.assertEqual(report['bytes'],2*(feedback.HEADER.size+feedback.RECORD.size))
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in (self.root/'games').rglob('*')})
        saved = feedback.private_file('sms',self.identity)
        stamp = saved.stat().st_mtime_ns
        self.assertEqual(feedback.import_saved_feedback('sms',settings)['updated_games'],0)
        self.assertEqual(saved.stat().st_mtime_ns,stamp)
        a.unlink(); b.unlink()
        settings['feedback_paths']['sms'] = str(self.root/'new empty games')
        self.assertEqual(feedback.import_saved_feedback('sms',settings)['files'],0)
        self.assertEqual(feedback.records('sms',self.identity),[first])
        self.assertEqual(feedback.records('sms','b'*64),[second])
        self.assertEqual(feedback.ingest('sms',self.identity,None)['unique_candidates'],1)
        # Retaining a raw candidate must never manufacture a qualification.
        self.assertFalse(list((self.root/'bank').rglob('*.json')))

    def test_bulk_import_rejects_corruption_wrong_console_and_skips_states(self):
        row = feedback.Observation(1,0x100,0,b'\x76')
        self.save('sms',[row])
        self.save('gg',[row])
        corrupt = self.save('sms',[row],'b'*64)
        corrupt.write_bytes(b'corrupt')
        impostor = self.save('sms',[row],'c'*64)
        impostor.write_bytes(feedback.encode([row],'sms','d'*64))
        hidden = self.root/'games/datas/states'/f'sms-{"e"*64}.rrfb'
        hidden.parent.mkdir(parents=True)
        hidden.write_bytes(feedback.encode([row],'sms','e'*64))
        report = feedback.import_saved_feedback('sms',{'feedback_paths':{'sms':str(self.root/'games')}})
        self.assertEqual((report['files'],report['games'],report['invalid_files']),(1,1,2))
        self.assertEqual(feedback.records('sms','e'*64),[])
        self.assertEqual(feedback.records('gg',self.identity),[])

    def test_bulk_import_newer_files_win_at_size_limit(self):
        old = [feedback.Observation(1,n,0,b'\x76') for n in range(feedback.LIMIT)]
        a = self.save('sms',old)
        newer = self.root/'games/renamed/datas/fallbacks'/a.name
        newer.parent.mkdir(parents=True)
        row = feedback.Observation(1,0xffff,0,b'\xc9')
        newer.write_bytes(feedback.encode([row],'sms',self.identity))
        os.utime(a,ns=(1000000000,1000000000))
        os.utime(newer,ns=(2000000000,2000000000))
        report = feedback.import_saved_feedback('sms',{'feedback_paths':{'sms':str(self.root/'games')}})
        self.assertEqual(report['observations'],feedback.LIMIT)
        self.assertIn(row,feedback.records('sms',self.identity))
        archive = feedback.private_file('sms',self.identity)
        stamp = archive.stat().st_mtime_ns
        report = feedback.import_saved_feedback('sms',{'feedback_paths':{'sms':str(self.root/'games')}})
        self.assertEqual(report['updated_games'],0)
        self.assertEqual(archive.stat().st_mtime_ns,stamp)

    def test_no_file_for_empty_or_wrong_rom(self):
        self.save('sms',[feedback.Observation(1,0,0,b'\x76')],'b'*64)
        report=feedback.ingest('sms',self.identity,self.root/'games')
        self.assertEqual(report['unique_candidates'],0)
        self.assertFalse((self.root/'bank').exists())

    def test_size_dedup_and_bound(self):
        rows=[feedback.Observation(1,n,0,b'\x76') for n in range(9000)]
        data=feedback.encode(rows+rows,'sms',self.identity)
        self.assertEqual(len(data),131168)
        self.assertEqual(len(feedback.decode(data,'sms',self.identity)[0]),4096)
        self.assertEqual(len(feedback.encode(rows[:100],'sms',self.identity)),3296)

    def test_gb_checks_live_rom_bytes_and_excludes_ram(self):
        data=bytearray(32768);data[0x100:0x104]=b'\x3e\xa5\x76\0'
        rom=SimpleNamespace(data=bytes(data),sha256=self.identity)
        self.save('gb',[feedback.Observation(2,0x100,0,bytes(data[0x100:0x104])),
                        feedback.Observation(2,0x200,0,b'bad!'),
                        feedback.Observation(2,0xc000,0,b'ram!')])
        feedback.ingest('gb',self.identity,self.root/'games')
        self.assertEqual(feedback.gb_entries(rom),{(0,0x100)})

    def test_sms_and_gg_mapping_and_ram_guards(self):
        for system in ('sms','gg'):
            data=bytes(range(256))*128
            rom=SimpleNamespace(system_id=system,data=data,sha256=self.identity)
            self.save(system,[feedback.Observation(1,0x100,0x020100,data[0x100:0x104]),
                              feedback.Observation(1,0xc000,0,b'\x3e\x01\x76\0')])
            feedback.ingest(system,self.identity,self.root/'games')
            seeds,patterns=feedback.sega_candidates(rom)
            self.assertEqual(len(seeds),1)
            self.assertIn(b'\x3e\x01\x76\0',patterns)

    def test_nes_opcode_sites_and_mapped_rom(self):
        from tools.nes_native_selftest import fixture
        from retrorecomp.nes import read_nes_rom
        path=self.root/'fixture.nes';path.write_bytes(fixture(0));rom=read_nes_rom(path)
        pc=0x8000;opcode=rom.data[16:17]
        self.save('nes',[feedback.Observation(3,pc,0,opcode),feedback.Observation(4,0x6000,0,b'\x60'),
                         feedback.Observation(3,pc,99999,opcode)],rom.sha256)
        feedback.ingest('nes',rom.sha256,self.root/'games')
        self.assertEqual(feedback.nes_sites(rom),({'4k:0:8000'},{(0x6000,0x60)}))

    def test_16bit_readers_keep_existing_bounds(self):
        from retrorecomp import megadrive,megadrive_z80,supernintendo,snes_spc
        rom=SimpleNamespace(data=b'\0'*32768,sha256=self.identity,path=Path('fixture.bin'),mapping='lorom')
        self.save('md',[feedback.Observation(5,0x200,0,b'\0'*8),
                        feedback.Observation(6,0xff0010,0,b'\x4e\x75'),
                        feedback.Observation(6,0x100,0,b'\x4e\x75'),
                        feedback.Observation(7,0x100,1,b'\x3e\0\0\0')])
        feedback.ingest('md',rom.sha256,self.root/'games')
        self.assertIn(0x200,megadrive.read_entries(rom))
        self.assertEqual(megadrive.read_ram_variants(rom),[{'address':0xff0010,'bytes':'4e75'}])
        self.assertTrue(megadrive_z80.read_variants(rom))
        self.save('snes',[feedback.Observation(8,0x7e1000,0,b'\xe6\x10\x6b\xea'),
                          feedback.Observation(8,0x002100,0,b'\xe6\x10\x6b\xea'),
                          feedback.Observation(9,0x300,0,b'\x6f')])
        feedback.ingest('snes',rom.sha256,self.root/'games')
        self.assertEqual(len(supernintendo.read_ram_variants(rom)),1)
        self.assertTrue(snes_spc.read_masks(rom)[0x300*32+0x6f//8] & (1<<(0x6f&7)))

    def test_neogeo_keeps_cart_and_bios_identity_and_live_guards(self):
        from retrorecomp import neogeo_knowledge
        identity = neogeo_knowledge.key('a'*64,'b'*64)
        sources={1:bytes.fromhex('4e714e75'),2:bytes.fromhex('4e73'),3:b'\0'*65536,4:b'\0'*131072}
        self.save('ng',[feedback.Observation(10,0,1,bytes.fromhex('4e71')),
                        feedback.Observation(10,2,1,bytes.fromhex('dead')),
                        feedback.Observation(11,0x100,0,bytes.fromhex('70014e75')),
                        feedback.Observation(12,0xf800,0,bytes.fromhex('3e017600'))],identity)
        feedback.ingest('ng',identity,self.root/'games')
        with patch.object(neogeo_knowledge,'context',return_value=(identity,{},sources)):
            with patch('retrorecomp.neogeo_knowledge.validate_bios', return_value={}):
                physical,ram,z80,_=neogeo_knowledge.hints(self.root)
        self.assertEqual(physical,{'p':{0},'bios':set()})
        self.assertEqual(ram,[{'offset':0x100,'words':'70014e75'}])
        self.assertEqual(z80,[{'address':0xf800,'bytes':'3e017600'}])
        self.assertFalse(feedback.records('ng',neogeo_knowledge.key('a'*64,'c'*64)))

    # Version 1 up to 4,096 records; version 2 up to 65,536 where the profile's bound allows (Mega Drive).

    def test_version_1_bytes_are_those_of_release_1_7_2(self):
        sms = feedback.encode([feedback.Observation(1,n,0,b'\x76') for n in range(100)],'sms','a'*64)
        self.assertEqual((len(sms),hashlib.sha256(sms).hexdigest()),
                         (3296,'2cc5a387257a33af0aa55e78c05de5972dddfaed7e3a168757055b3f1c1aec59'))
        md = feedback.encode([feedback.Observation(5,0x200+2*n,0x200+2*n,bytes([n&255,n>>8,1,2,3,4,5,6]))
                              for n in range(4096)],'md','a'*64)
        self.assertEqual((len(md),hashlib.sha256(md).hexdigest()),
                         (131168,'b4cb8a0d8dbfcf0f5bc232ff4fc4038bd06ba7e239733759d06034bdf5ef367e'))
        self.assertEqual((version_of(sms),version_of(md)),(1,1))

    def test_mega_drive_keeps_65536_records_in_version_2(self):
        rows = [md_row(n) for n in range(70000)]
        data = feedback.encode(rows,'md',self.identity)
        self.assertEqual((len(data),version_of(data)),(2097248,2))
        self.assertEqual(len(data),feedback.FORMAT_MAX_BYTES)
        self.assertEqual(feedback.decode(data,'md',self.identity),(rows[:65536],4464))
        data = feedback.encode(rows[:9000],'md',self.identity)
        self.assertEqual((len(data),version_of(data)),(288096,2))
        self.assertEqual(feedback.decode(data,'md',self.identity),(rows[:9000],0))
        self.assertEqual(feedback.limit('md'),65536)
        self.assertEqual(feedback.max_bytes('md'),feedback.FORMAT_MAX_BYTES)

    def test_version_and_count_have_one_canonical_form(self):
        feedback.decode(raw_file(1,4096),'md',self.identity)
        feedback.decode(raw_file(2,4097),'md',self.identity)
        feedback.decode(raw_file(2,65536),'md',self.identity)
        for invalid in (raw_file(2,10), raw_file(2,4096), raw_file(1,5000), raw_file(1,65536),
                        raw_file(2,65537), raw_file(3,10), raw_file(0,10)):
            with self.assertRaises(ValueError):feedback.decode(invalid,'md',self.identity)

    def test_a_version_2_file_is_longer_than_max_bytes_and_carries_version_2(self):
        data = feedback.encode([md_row(n) for n in range(5000)],'md',self.identity)
        # The two conditions the 1.7.2 decode tests (a 1.7.2 reader is not run here): the length and the version number.
        self.assertGreater(len(data),feedback.MAX_BYTES)
        self.assertEqual(version_of(data),2)

    def test_every_other_machine_keeps_4096_records_in_version_1(self):
        self.assertEqual({system for system,bound in feedback.LIMITS.items() if bound != 4096},{'md'})
        for system,kinds in feedback.KINDS.items():
            if system == 'md' or not kinds:
                continue
            rows = [feedback.Observation(min(kinds),n,0,b'\x76') for n in range(9000)]
            data = feedback.encode(rows,system,self.identity)
            self.assertEqual((len(data),version_of(data)),(131168,1),system)
            self.assertEqual(feedback.decode(data,system,self.identity)[1],4904,system)
            self.assertEqual(feedback.max_bytes(system),131168,system)

    def test_old_version_1_file_loads_and_its_call_count_is_not_a_refused_count(self):
        path = self.root/'games/datas/fallbacks'/f'md-{self.identity}.rrfb'
        path.parent.mkdir(parents=True)
        path.write_bytes(feedback.encode([md_row(n) for n in range(4096)],'md',self.identity,3000000))
        self.assertEqual(feedback.decode(path.read_bytes(),'md',self.identity)[1],3000000)
        report = feedback.ingest('md',self.identity,self.root/'games')
        self.assertEqual((report['unique_candidates'],report['limit_reached'],report['refused_records']),(4096,False,0))
        self.assertEqual(version_of(feedback.private_file('md',self.identity).read_bytes()),1)
        # The same file for a machine whose bound is 4,096: the number is only a flag, as before.
        sms = self.root/'games/datas/fallbacks'/f'sms-{self.identity}.rrfb'
        sms.write_bytes(feedback.encode([feedback.Observation(1,n,0,b'\x76') for n in range(4096)],'sms',self.identity,3000000))
        report = feedback.ingest('sms',self.identity,self.root/'games')
        self.assertEqual((report['limit_reached'],report['refused_records']),(True,None))
        # A newer file of other rows: the record grows past 4,096 and becomes version 2.
        path.write_bytes(feedback.encode([md_row(n) for n in range(10000,15000)],'md',self.identity))
        report = feedback.ingest('md',self.identity,self.root/'games')
        self.assertEqual((report['unique_candidates'],report['limit_reached'],report['refused_records']),(9096,False,0))
        private = feedback.private_file('md',self.identity).read_bytes()
        self.assertEqual((version_of(private),len(private)),(2,feedback.HEADER.size+9096*feedback.RECORD.size))

    def test_ingest_counts_the_distinct_records_the_full_record_refused(self):
        full = self.root/'games/datas/fallbacks'/f'md-{self.identity}.rrfb'
        other = self.root/'games/sub/datas/fallbacks'/full.name
        with patch.dict(feedback.LIMITS,{'md':8192}):
            full.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            full.write_bytes(feedback.encode([md_row(n) for n in range(8192)],'md',self.identity))
            other.write_bytes(feedback.encode([md_row(n) for n in range(8192,9192)],'md',self.identity))
            os.utime(full,ns=(2000000000,2000000000))
            os.utime(other,ns=(1000000000,1000000000))
            messages = []
            report = feedback.ingest('md',self.identity,self.root/'games/sub',emit=messages.append)
            self.assertEqual((report['unique_candidates'],report['limit'],report['limit_reached'],
                              report['refused_records']),(8192,8192,True,1000))
            self.assertEqual(report['max_bytes_per_game'],feedback.HEADER.size+8192*feedback.RECORD.size)
            self.assertEqual(set(feedback.records('md',self.identity)),{md_row(n) for n in range(8192)})
            self.assertEqual(len(messages),1)
            self.assertTrue(messages[0].endswith('; at least 1000 more were refused: the record is full at 8192.'),messages)

    def test_a_version_2_header_number_is_reported_as_it_is(self):
        path = self.root/'games/datas/fallbacks'/f'md-{self.identity}.rrfb'
        path.parent.mkdir(parents=True)
        path.write_bytes(feedback.encode([md_row(n) for n in range(5000)],'md',self.identity,777))
        messages = []
        report = feedback.ingest('md',self.identity,self.root/'games',emit=messages.append)
        self.assertEqual((report['unique_candidates'],report['limit_reached'],report['refused_records']),(5000,True,777))
        # 5,000 rows are far from the bound of 65,536: the line says what was refused, never "full".
        self.assertTrue(messages[0].endswith('; at least 777 more were refused.'),messages)
        self.assertNotIn('full at',messages[0])

    def test_the_real_bound_at_65536(self):
        path = self.root/'games/datas/fallbacks'/f'md-{self.identity}.rrfb'
        path.parent.mkdir(parents=True)
        path.write_bytes(feedback.encode([md_row(n) for n in range(70000)],'md',self.identity))
        messages = []
        report = feedback.ingest('md',self.identity,self.root/'games',emit=messages.append)
        self.assertEqual((report['unique_candidates'],report['limit'],report['refused_records'],report['bytes']),
                         (65536,65536,4464,2097248))
        self.assertIn('at least 4464 more were refused',messages[0])
        self.assertEqual(len(feedback.records('md',self.identity)),65536)

    def test_a_full_record_of_a_4096_machine_logs_a_flag_only(self):
        path = self.root/'games/datas/fallbacks'/f'sms-{self.identity}.rrfb'
        path.parent.mkdir(parents=True)
        path.write_bytes(feedback.encode([feedback.Observation(1,n,0,b'\x76') for n in range(5000)],'sms',self.identity))
        messages = []
        report = feedback.ingest('sms',self.identity,self.root/'games',emit=messages.append)
        self.assertEqual((report['limit'],report['limit_reached'],report['refused_records']),(4096,True,None))
        self.assertTrue(messages[0].endswith('; more were refused: the record is full at 4096.'),messages)

    def test_fingerprints_of_up_to_4096_rows_are_those_of_release_1_7_2(self):
        self.save('sms',[feedback.Observation(1,n,0,b'\x76') for n in range(100)])
        report = feedback.ingest('sms',self.identity,self.root/'games')
        self.assertEqual(report['fingerprint'],'2cc5a387257a33af0aa55e78c05de5972dddfaed7e3a168757055b3f1c1aec59')
        self.assertEqual((report['limit'],report['refused_records'],report['max_bytes_per_game']),(4096,None,131168))
        self.save('md',[feedback.Observation(5,0x200+2*n,0x200+2*n,bytes([n&255,n>>8,1,2,3,4,5,6])) for n in range(4096)])
        report = feedback.ingest('md',self.identity,self.root/'games')
        self.assertEqual(report['fingerprint'],'b4cb8a0d8dbfcf0f5bc232ff4fc4038bd06ba7e239733759d06034bdf5ef367e')
        self.assertEqual((report['limit'],report['refused_records'],report['max_bytes_per_game'],report['limit_reached']),
                         (65536,0,2097248,False))

    def test_bulk_import_counts_the_left_out_records_for_the_mega_drive_only(self):
        with patch.dict(feedback.LIMITS,{'md':8192}):
            first = self.save('md',[md_row(n) for n in range(8192)])
            newer = self.root/'games/renamed/datas/fallbacks'/first.name
            newer.parent.mkdir(parents=True)
            newer.write_bytes(feedback.encode([md_row(n) for n in range(8192,9192)],'md',self.identity))
            os.utime(first,ns=(1000000000,1000000000))
            os.utime(newer,ns=(2000000000,2000000000))
            report = feedback.import_saved_feedback('md',{'feedback_paths':{'md':str(self.root/'games')}})
            self.assertEqual((report['observations'],report['refused_records']),(8192,1000))
        self.save('sms',[feedback.Observation(1,0x100,0,b'\x76')])
        report = feedback.import_saved_feedback('sms',{'feedback_paths':{'sms':str(self.root/'games')}})
        self.assertIsNone(report['refused_records'])

    def test_stage_writes_the_bound_only_above_4096(self):
        for system,expected in (('md','#define RR_FEEDBACK_LIMIT 65536u\n'),('sms',''),('snes','')):
            project = self.root/('project '+system)
            project.mkdir()
            feedback.stage(project,system,self.identity,cmake=False)
            self.assertEqual((project/'runtime_feedback_config.h').read_text(encoding='ascii'),
                             f'#define RR_FEEDBACK_SYSTEM "{system}"\n#define RR_FEEDBACK_IDENTITY "{self.identity}"\n'+expected)

    def test_the_c_default_is_4096_and_no_converter_module_names_the_macro(self):
        root = Path(__file__).resolve().parents[1]
        text = (root/'native/runtime_feedback.c').read_text(encoding='utf-8')
        self.assertIn('#ifndef RR_FEEDBACK_LIMIT\n#define RR_FEEDBACK_LIMIT 4096u',text)
        for path in sorted((root/'retrorecomp').glob('*.py')):
            if path.name != 'feedback.py':
                self.assertNotIn('RR_FEEDBACK_LIMIT',path.read_text(encoding='utf-8'),path.name)


def md_row(n):
    """An authored Mega Drive row: numbers and four bytes, nothing from a ROM."""
    return feedback.Observation(5, 0x200 + 2*n, 0, n.to_bytes(4, 'little') + b'abcd')


def raw_file(version, count, system='md', identity='a'*64, dropped=0):
    """A hand-built file with a valid digest, to test what a reader accepts."""
    rows = b''.join(feedback.RECORD.pack(5, 8, 0, 0x200 + 2*n, 0, (n.to_bytes(4, 'little') + b'abcd').ljust(16, b'\0'), 0)
                    for n in range(count))
    return feedback.HEADER.pack(b'RRFB001\0', version, count, dropped, system.encode().ljust(8, b'\0'),
                                identity.encode(), feedback.checksum(rows)) + rows


def version_of(data):
    return struct.unpack_from('<I', data, 8)[0]


if __name__=='__main__':unittest.main()
