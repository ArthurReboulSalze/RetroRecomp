import hashlib
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smsrecomp import feedback


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
            setting = patch('smsrecomp.paths.'+name, return_value=value)
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
        with patch('smsrecomp.paths.load_preferences',return_value=settings):
            self.assertEqual(feedback.ingest('sms',self.identity,self.root/'new output')['unique_candidates'],1)
            self.assertEqual(feedback.ingest('gg',self.identity,self.root/'new output')['unique_candidates'],0)
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in (self.root/'moved').rglob('*')})

    def test_feedback_search_preferences_support_relative_paths_and_ignore_invalid_fields(self):
        from smsrecomp.paths import feedback_search_paths
        with patch('smsrecomp.paths.export_directory',return_value=self.root):
            self.assertEqual(feedback_search_paths({'feedback_paths':{'sms':'Moved/SMS','gb':23,'unknown':'no'}}),
                             {'sms':(self.root/'Moved/SMS').resolve()})
        self.assertEqual(feedback_search_paths({'feedback_paths':[]}),{})

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
        from smsrecomp.nes import read_nes_rom
        path=self.root/'fixture.nes';path.write_bytes(fixture(0));rom=read_nes_rom(path)
        pc=0x8000;opcode=rom.data[16:17]
        self.save('nes',[feedback.Observation(3,pc,0,opcode),feedback.Observation(4,0x6000,0,b'\x60'),
                         feedback.Observation(3,pc,99999,opcode)],rom.sha256)
        feedback.ingest('nes',rom.sha256,self.root/'games')
        self.assertEqual(feedback.nes_sites(rom),({'4k:0:8000'},{(0x6000,0x60)}))

    def test_16bit_readers_keep_existing_bounds(self):
        from smsrecomp import megadrive,megadrive_z80,supernintendo,snes_spc
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
        from smsrecomp import neogeo_knowledge
        identity = neogeo_knowledge.key('a'*64,'b'*64)
        sources={1:bytes.fromhex('4e714e75'),2:bytes.fromhex('4e73'),3:b'\0'*65536,4:b'\0'*131072}
        self.save('ng',[feedback.Observation(10,0,1,bytes.fromhex('4e71')),
                        feedback.Observation(10,2,1,bytes.fromhex('dead')),
                        feedback.Observation(11,0x100,0,bytes.fromhex('70014e75')),
                        feedback.Observation(12,0xf800,0,bytes.fromhex('3e017600'))],identity)
        feedback.ingest('ng',identity,self.root/'games')
        with patch.object(neogeo_knowledge,'context',return_value=(identity,{},sources)):
            with patch('smsrecomp.neogeo_knowledge.validate_bios', return_value={}):
                physical,ram,z80,_=neogeo_knowledge.hints(self.root)
        self.assertEqual(physical,{'p':{0},'bios':set()})
        self.assertEqual(ram,[{'offset':0x100,'words':'70014e75'}])
        self.assertEqual(z80,[{'address':0xf800,'bytes':'3e017600'}])
        self.assertFalse(feedback.records('ng',neogeo_knowledge.key('a'*64,'c'*64)))


if __name__=='__main__':unittest.main()
