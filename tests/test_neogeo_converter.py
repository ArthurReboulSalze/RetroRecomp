"""Converter/BIOs/merged-set regressions using authored bytes only."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import zlib

from retrorecomp.batch import identify,convert_batch
from retrorecomp.core import ConversionError
from retrorecomp.neogeo import read_set,canonical_archive,selected_members,parent_archives
from retrorecomp.neogeo_knowledge import key,validate_record,compact_record,expanded_record
from retrorecomp.neogeo_build import GEOLITH_REV,LITHOGEN_REV


class NeoGeoConverterTests(unittest.TestCase):
    def test_failed_probe_preserves_bounded_runner_diagnostic(self):
        from types import SimpleNamespace
        from retrorecomp.neogeo_build import probe_failure
        result=SimpleNamespace(returncode=3,stderr=b'This title is incompatible with AES systems\n',stdout=b'')
        message=str(probe_failure('aes-attract-reference',result))
        self.assertIn('exit 3',message)
        self.assertIn('incompatible with AES',message)
        result.stderr=b'x'*100000+b'\xff\nImportant final reason'
        message=str(probe_failure('probe',result))
        self.assertLess(len(message),1300)
        self.assertIn('Important final reason',message)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()

    def neo(self):
        lengths=(512,131072,65536,0,0,128);header=bytearray(4096);header[:4]=b'NEO\x01'
        struct.pack_into('<6I',header,4,*lengths);header[44:52]=b'Authored'
        path=self.root/'source.neo';path.write_bytes(header+bytes(sum(lengths)));return path

    def test_machine_capabilities_distinguish_mvs_only_revisions(self):
        from retrorecomp.neogeo_build import aes_compatible,mode_config
        def cartridge(ngh,size=512,markers=()):
            original=self.neo().read_bytes();data=bytearray(original[:4096])+bytearray(size)+original[4096+512:]
            struct.pack_into('<I',data,4,size);struct.pack_into('<I',data,40,ngh)
            for offset,value in markers:data[4096+offset]=value
            path=self.root/'mode.neo';path.write_bytes(data);return path
        for ngh in (0x236,0x275,0x5003):self.assertFalse(aes_compatible(cartridge(ngh)))
        self.assertFalse(aes_compatible(cartridge(0x066)))
        self.assertTrue(aes_compatible(cartridge(0x066,0x100000)))
        for ngh,offset,value,size in ((0x263,0x809,0x0c,0x2000),(0x268,0x26b,0xb9,0x2000),(0x269,0x9e91,0x0f,0xa000)):
            self.assertTrue(aes_compatible(cartridge(ngh,size,[(offset,value)])))
            self.assertFalse(aes_compatible(cartridge(ngh,size,[(offset^1,value)])))
        bios={'sha256':'a'*64,'aes':{'sha256':'b'*64}}
        with patch('retrorecomp.neogeo.validate_bios',return_value=bios):
            config=mode_config(cartridge(0x236),self.root/'bios.zip')
            self.assertIn('#define RR_NG_ARCADE_ONLY 1',config)
            self.assertIn('#define RR_NG_AES_AVAILABLE 0',config)
            config=mode_config(cartridge(0x001),self.root/'bios.zip')
            self.assertIn('#define RR_NG_ARCADE_ONLY 0',config)
            self.assertIn('#define RR_NG_AES_AVAILABLE 1',config)

    def test_unavailable_aes_cannot_be_requested_through_an_extra_route(self):
        from retrorecomp.neogeo_validation import extended_routes
        with self.assertRaisesRegex(ValueError,'unavailable machine'):
            extended_routes('authored',{'authored':{'aes-test':(30,'0 00 00 0 0\n')}},aes=False)

    def test_shared_knowledge_cannot_skip_required_aes_validation(self):
        from tools.build_neogeo_knowledge import qualified_record
        report={'system':{'id':'ng'},'native_validation':{'passed':True,
            'packed_reference_match':True,'reference_before_learning':True},
            'final_checks':[{'reference_match':True,'interpreted_opcodes':0,
                'audio_interpreted_opcodes':0,'native_entries':12,'audio_native_opcodes':34}],
            'game_states':{'validation':{'routes':[{'fresh_process_match':True,
                'replayed_frames':300} for _ in range(3)],'invalid_states_rejected':26,
                'missing_load_is_read_only':True}},
            'ordinary_saves':{'validation':{'idle_launch_creates_nothing':True,
                'native_main_fallback':0,'native_sound_fallback':0,'fresh_process_match':True}},
            'compiler':{'revision':GEOLITH_REV,'loader_revision':LITHOGEN_REV},
            'build_executable':str(self.root/'project/build/Release/game.exe'),
            'runtime_modes':{'aes_available':False}}
        # A build folder removed after publication cannot qualify hints.
        with self.assertRaisesRegex(ValueError,'--keep-build'):
            qualified_record(report)
        (self.root/'project').mkdir(exist_ok=True)
        with patch('retrorecomp.neogeo_build.aes_available',return_value=True) as capability:
            for executable in ('project/build/Release/game.exe','project/build/game'):
                report['build_executable']=str(self.root/executable)
                with self.assertRaisesRegex(ValueError,'verified cartridge/BIOS'):
                    qualified_record(report)
                capability.assert_called_with(self.root/'project')
            report['runtime_modes']['aes_available']=True
            with self.assertRaisesRegex(ValueError,'AES qualification is incomplete'):
                qualified_record(report)

    def test_validation_file_names_the_candidate_that_was_compared(self):
        # A large Linux game UPX cannot pack and test is published unpacked: the file says so (fake UPX).
        from types import SimpleNamespace
        from retrorecomp import packing
        from retrorecomp.neogeo_conversion import record_candidate_validation
        from tests.test_packing import ELF_X86_64, POSIX_OS
        project=self.root/'project';project.mkdir()
        rows=[{'name':'play','frames':300,'native_entries':5,'interpreted_opcodes':0,
               'audio_native_opcodes':7,'audio_interpreted_opcodes':0}]
        def candidate(failure):
            game=project/'packed-game.exe';game.write_bytes(ELF_X86_64+bytes(64)+b'native game')
            (project/'native-validation.json').write_text(json.dumps(
                {'passed':False,'awaiting_packed_validation':True,'routes':[]}),encoding='utf-8')
            log=[]
            def run(command,**options):
                if '-9' in command:Path(command[-1]).write_bytes(b'UPX! packed')
                return SimpleNamespace(returncode=1 if failure and '-t' in command else 0,stdout='',
                                       stderr='upx: packed-game.exe: Exception: compressed data violation')
            with patch('retrorecomp.packing.subprocess.run',side_effect=run),patch('retrorecomp.packing.os',POSIX_OS),\
                    patch('retrorecomp.packing.platform.machine',return_value='x86_64'):
                notice=packing.compact_executable(game,log.append)
            return game,notice,log,record_candidate_validation(project,game,notice,rows)
        game,notice,log,validation=candidate(True)
        self.assertEqual(log,[notice['notice']])
        self.assertEqual(game.read_bytes(),ELF_X86_64+bytes(64)+b'native game')
        self.assertEqual(validation['validated_candidate'],'unpacked')
        self.assertEqual(validation['unpacked_sha256'],hashlib.sha256(game.read_bytes()).hexdigest())
        self.assertEqual(validation['unpacked_reason'],notice['notice'])
        self.assertNotIn('packed_sha256',validation)
        self.assertEqual(json.loads((project/'native-validation.json').read_text(encoding='utf-8')),validation)
        self.assertEqual((validation['passed'],validation['awaiting_packed_validation']),(True,False))
        game,notice,log,validation=candidate(False)
        self.assertEqual((notice,log),(None,[]))
        self.assertEqual(validation['validated_candidate'],'packed')
        self.assertEqual(validation['packed_sha256'],hashlib.sha256(game.read_bytes()).hexdigest())
        self.assertNotIn('unpacked_reason',validation)
        self.assertEqual(validation['routes'],[{'route':'play','frames':300,'passed':True,'main_native':5,
            'main_fallback':0,'sound_native':7,'sound_fallback':0}])

    def test_auto_detection_needs_no_compiler_or_bios(self):
        with patch('retrorecomp.neogeo_build.preparation_tool',side_effect=AssertionError('identification built a tool')):
            item=identify(self.neo())
        self.assertEqual((item.system,item.title,item.video_hint),('ng','Authored','mvs'))
        self.assertFalse(item.error)

    def test_optional_aes_firmware_has_its_own_identity_and_is_verified(self):
        from retrorecomp.neogeo import BIOS_MEMBERS, validate_bios
        from retrorecomp.neogeo_build import aes_identity
        records=[dict(name=name,bytes=size,crc32=crc,sha256=str(i)*64)
                 for i,(name,(size,crc)) in enumerate(BIOS_MEMBERS.items())]
        with patch('retrorecomp.neogeo.archive_members',return_value=records):
            mvs=validate_bios(self.root/'authored.zip')
            self.assertNotIn('aes',mvs)
            records.append(dict(name='neo-epo.bin',bytes=0x20000,crc32=0xd27a71f1,sha256='a'*64))
            dual=validate_bios(self.root/'authored.zip')
            self.assertEqual(mvs['sha256'],dual['sha256']) # original saves remain scoped to the same MVS BIOS
            self.assertNotEqual(key('b'*64,dual['sha256']),aes_identity('b'*64,dual))
            records[-1]['crc32']=0
            with self.assertRaisesRegex(ValueError,'AES export BIOS'):validate_bios(self.root/'authored.zip')

    def test_missing_bios_fails_before_conversion_or_output_creation(self):
        from retrorecomp.neogeo_conversion import convert
        output=self.root/'not-created'
        with patch('retrorecomp.neogeo_conversion.convert_reference') as build:
            with self.assertRaisesRegex(ConversionError,'Select your BIOS'):
                convert(self.neo(),output=output)
        build.assert_not_called();self.assertFalse(output.exists())

    def test_batch_failure_preserves_an_existing_export(self):
        item=identify(self.neo());out=self.root/'Games';folder=out/'Neo Geo';folder.mkdir(parents=True)
        target=folder/'Authored.exe';original=b'MZ unbranded existing file';target.write_bytes(original)
        result=convert_batch([item],out,ng_bios='',emit=lambda _:None)
        self.assertEqual(result['failed'],1);self.assertEqual(target.read_bytes(),original)
        self.assertFalse(list(folder.glob('*.tmp')))

    def merged(self):
        path=self.root/'base.zip'
        raw={'root/001-p1.p1':b'base program','clone/001-p1.p1':b'clone program',
             '001-m1.m1':b'sound','001-c1.c1':b'sprites','clone/extra.p2':b'extra program'}
        with ZipFile(path,'w') as z:
            for name,data in raw.items():z.writestr(name,data)
        def desc(name,programs):
            files=[{'name':'program'+str(n)+'.p1','crc32':zlib.crc32(data),'region':0,'optional':0}
                   for n,data in enumerate(programs)]
            files += [{'name':'sound.m1','crc32':zlib.crc32(b'sound'),'region':2,'optional':0},
                      {'name':'sprites.c1','crc32':zlib.crc32(b'sprites'),'region':6,'optional':0}]
            return {'set':name,'title':'Authored '+name,'parent':'','board':'rom','files':files}
        return path,[desc('base',[b'base program']),desc('clone',[b'clone program',b'extra program'])]

    def test_merged_zip_keeps_its_crc_verified_named_revision(self):
        path,catalogue=self.merged();before=hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(read_set(path,catalogue).set_name,'base')
        output=self.root/'staged.zip';canonical_archive(path,output,catalogue[0])
        with ZipFile(output) as z:
            self.assertEqual(z.read('program0.p1'),b'base program')
            self.assertEqual(len(z.namelist()),3)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        with self.assertRaisesRegex(ValueError,'not replace'):canonical_archive(path,path,catalogue[0])

    def test_merged_renamed_zip_does_not_guess_between_complete_revisions(self):
        path,catalogue=self.merged();other=self.root/'unknown.zip';other.write_bytes(path.read_bytes())
        with self.assertRaisesRegex(ValueError,'Ambiguous'):read_set(other,catalogue)

    def test_crc_collision_is_not_treated_as_identical_content(self):
        records=({'name':'a','bytes':10,'crc32':123,'sha256':'a'*64},
                 {'name':'b','bytes':10,'crc32':123,'sha256':'b'*64})
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            selected_members(records,{'parent':'','files':[{'name':'p1','crc32':123,'optional':0}]})

    def test_complete_clone_named_like_parent_does_not_require_parent_program(self):
        path,catalogue=self.merged();catalogue[1]['parent']='base'
        with ZipFile(path,'w') as archive:
            for name,data in [('p1',b'clone program'),('p2',b'extra program'),
                              ('m1',b'sound'),('c1',b'sprites')]:archive.writestr(name,data)
        game=read_set(path,catalogue)
        self.assertEqual(game.set_name,'clone')
        self.assertEqual(parent_archives(game,catalogue),[])
        staged=self.root/'selected.zip';canonical_archive(path,staged,catalogue[1])
        self.assertEqual(read_set(staged,catalogue).set_name,'clone')

    def test_split_clone_requires_an_independent_crc_matching_parent(self):
        parent,catalogue=self.merged();catalogue[1]['parent']='base'
        child=self.root/'clone.zip'
        with ZipFile(child,'w') as archive:
            archive.writestr('p1',b'clone program');archive.writestr('p2',b'extra program')
        game=read_set(child,catalogue)
        self.assertEqual(parent_archives(game,catalogue)[0][0],parent)
        with ZipFile(parent,'w') as archive:archive.writestr('unrelated',b'not the required data')
        with self.assertRaisesRegex(ValueError,'required cartridge components'):parent_archives(game,catalogue)
        parent.write_bytes(child.read_bytes())
        with self.assertRaisesRegex(ValueError,'separate base.zip'):parent_archives(read_set(parent,catalogue),catalogue)
        parent.unlink()
        with self.assertRaisesRegex(ValueError,'separate base.zip'):parent_archives(game,catalogue)

    def record(self):
        return {'engine':GEOLITH_REV,'loader':LITHOGEN_REV,'cart':'a'*64,'bios':'b'*64,
                'rom_bytes':200000,'p_bytes':512,'bios_bytes':131072,'m1_bytes':65536,'sm1_bytes':131072,
                'rom_entries':[[1,0],[2,2]],'ram_refs':[[0xfc00,1,2,4]],'z80_refs':[[0xfffd,4,10,1]]}

    def test_shared_hints_require_exact_bios_and_bounded_numeric_references(self):
        record=self.record();identity=key(record['cart'],record['bios']);validate_record(identity,record)
        variants=[]
        r=copy.deepcopy(record);r['bios']='c'*64;variants.append(r)
        for name,value in (('words','1234'),('path','somewhere'),('ram_refs',[[65534,1,0,4]]),
                           ('rom_entries',[[True,0]]),('z80_refs',[[65533,4,131070,1]])):
            r=copy.deepcopy(record);r[name]=value;variants.append(r)
        for r in variants:
            with self.subTest(r=r),self.assertRaises(ValueError):validate_record(identity,r)

    def test_refresh_preserves_verified_hints_but_never_mixes_runtime_pins(self):
        from tools.build_neogeo_knowledge import merge_qualified
        old=self.record();identity=key(old['cart'],old['bios']);new=copy.deepcopy(old)
        new['rom_entries']=[[1,6],[2,2]]
        merged=merge_qualified(identity,old,new)
        self.assertEqual(merged['rom_entries'],[[1,0],[1,6],[2,2]])
        self.assertEqual(old['rom_entries'],[[1,0],[2,2]])
        new['engine']='c'*40
        self.assertEqual(merge_qualified(identity,old,new),new)
        old['words']='private dump'
        with self.assertRaises(ValueError):merge_qualified(identity,old,new)

    def test_compact_rom_roots_round_trip_and_merge_without_losing_guards(self):
        from tools.build_neogeo_knowledge import merge_qualified
        record=self.record();identity=key(record['cart'],record['bios'])
        record['rom_entries']=[[1,0],[1,2],[1,6],[1,510],[2,0],[2,131070]]
        packed=compact_record(identity,record)
        self.assertEqual(packed['rom_entries'],[])
        self.assertEqual(expanded_record(identity,packed),record)
        self.assertEqual(record['rom_entries'][0],[1,0])
        new=copy.deepcopy(record);new['rom_entries']=[[1,8],[2,2]]
        merged=merge_qualified(identity,packed,new)
        self.assertEqual(merged['rom_entries'],[[1,0],[1,2],[1,6],[1,8],[1,510],[2,0],[2,2],[2,131070]])
        self.assertEqual(merged['ram_refs'],record['ram_refs'])
        self.assertEqual(merged['z80_refs'],record['z80_refs'])
        self.assertEqual(compact_record(identity,packed),packed)

    def test_compact_rom_roots_reject_invalid_regions_offsets_and_expansion(self):
        record=self.record();identity=key(record['cart'],record['bios'])
        for blocks in ([[1]],[[True,0]],[[1,True]],[[3,0]],[[1,1]],[[1,0,0]],
                       [[1,0,-2]],[[1,0,3]],[[1,510,2]],[[2,131070,2]],[[1,0],[1,2]],
                       [[1,0],[2,0],[1,2]],[[1,'bytes']]):
            bad={**record,'rom_deltas':blocks}
            with self.subTest(blocks=blocks),self.assertRaises(ValueError):validate_record(identity,bad)
        bad={**record,'p_bytes':2<<20,'rom_bytes':3<<20,'rom_entries':[],
             'rom_deltas':[[1,0,*([2]*262144)]]}
        with self.assertRaisesRegex(ValueError,'region/count'):validate_record(identity,bad)
        packed=compact_record(identity,record);packed['raw_rom']=[]
        with self.assertRaises(ValueError):validate_record(identity,packed)

    def test_bios_preferences_are_portable_and_independent_of_cwd(self):
        from retrorecomp.paths import save_preferences,load_preferences,selected_bios_path
        app=self.root/'Portable';bios=app/'Bios/bios.zip'
        with patch('retrorecomp.paths.export_directory',return_value=app):
            self.assertIsNone(selected_bios_path(['malformed']))
            save_preferences({'ng_bios':str(bios)})
            saved=load_preferences()['ng_bios'];self.assertFalse(Path(saved).is_absolute())
            self.assertEqual(selected_bios_path(saved),bios)

    def test_artwork_collapses_same_game_aliases_without_confusing_years(self):
        from retrorecomp.artwork import choose_cover
        names=["The King of Fighters '98 - The Slugfest _ King of Fighters '98 - Dream Match Never Ends (NGM-2420).png",
               "The King of Fighters '99 (NGM-2510).png"]
        self.assertEqual(choose_cover(names,'kof98',"The King of Fighters '98 - The Slugfest"),names[0])
        self.assertEqual(choose_cover(names,'kof99',"The King of Fighters '99"),names[1])


    def test_probe_workers_follow_the_cpu_share_and_never_exceed_the_routes(self):
        """Only the schedule of the validation moves: a conversion alone uses its CPUs (at most eight, one per route), a batch
        keeps its share, a small machine is not oversubscribed (the previous cap was four whatever the machine)."""
        from retrorecomp.neogeo_conversion import cpu_share,validation_workers
        def workers(cpus,budget,routes,games=1):
            with patch('retrorecomp.platforms.available_cpus',return_value=cpus),                 patch('retrorecomp.platforms.game_cpu_share',return_value=budget if budget is not None else cpus):
                return validation_workers(routes,games),cpu_share(games)
        self.assertEqual(workers(24,None,6),(6,8))          # alone on 24 CPUs: one worker per route, checks use eight
        self.assertEqual(workers(24,None,12),(8,8))         # never more than eight
        self.assertEqual(workers(4,None,6),(4,4))           # a 4 CPU machine is as before
        self.assertEqual(workers(2,None,6),(2,2))           # a 2 CPU machine is no longer oversubscribed
        self.assertEqual(workers(24,3,6,8),(3,3))           # eight games at once on 24 CPUs: three each
        self.assertEqual(workers(24,None,6,8),(3,3))        # a caller that set no budget still gets its share
        self.assertEqual(workers(8,1,6,8),(1,1))            # a full batch on 8 CPUs: one each, as before
        self.assertEqual(workers(24,None,1),(1,8))          # a single route is one worker
        self.assertEqual(workers(1,None,5),(1,1))

if __name__=='__main__':unittest.main()
