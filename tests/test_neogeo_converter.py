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

from smsrecomp.batch import identify,convert_batch
from smsrecomp.core import ConversionError
from smsrecomp.neogeo import read_set,canonical_archive,selected_members,parent_archives
from smsrecomp.neogeo_knowledge import key,validate_record,compact_record,expanded_record
from smsrecomp.neogeo_build import GEOLITH_REV,LITHOGEN_REV


class NeoGeoConverterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()

    def neo(self):
        lengths=(512,131072,65536,0,0,128);header=bytearray(4096);header[:4]=b'NEO\x01'
        struct.pack_into('<6I',header,4,*lengths);header[44:52]=b'Authored'
        path=self.root/'source.neo';path.write_bytes(header+bytes(sum(lengths)));return path

    def test_auto_detection_needs_no_compiler_or_bios(self):
        with patch('smsrecomp.neogeo_build.preparation_tool',side_effect=AssertionError('identification built a tool')):
            item=identify(self.neo())
        self.assertEqual((item.system,item.title,item.video_hint),('ng','Authored','mvs'))
        self.assertFalse(item.error)

    def test_optional_aes_firmware_has_its_own_identity_and_is_verified(self):
        from smsrecomp.neogeo import BIOS_MEMBERS, validate_bios
        from smsrecomp.neogeo_build import aes_identity
        records=[dict(name=name,bytes=size,crc32=crc,sha256=str(i)*64)
                 for i,(name,(size,crc)) in enumerate(BIOS_MEMBERS.items())]
        with patch('smsrecomp.neogeo.archive_members',return_value=records):
            mvs=validate_bios(self.root/'authored.zip')
            self.assertNotIn('aes',mvs)
            records.append(dict(name='neo-epo.bin',bytes=0x20000,crc32=0xd27a71f1,sha256='a'*64))
            dual=validate_bios(self.root/'authored.zip')
            self.assertEqual(mvs['sha256'],dual['sha256']) # original saves remain scoped to the same MVS BIOS
            self.assertNotEqual(key('b'*64,dual['sha256']),aes_identity('b'*64,dual))
            records[-1]['crc32']=0
            with self.assertRaisesRegex(ValueError,'AES export BIOS'):validate_bios(self.root/'authored.zip')

    def test_missing_bios_fails_before_conversion_or_output_creation(self):
        from smsrecomp.neogeo_conversion import convert
        output=self.root/'not-created'
        with patch('smsrecomp.neogeo_conversion.convert_reference') as build:
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
        from smsrecomp.paths import save_preferences,load_preferences,selected_bios_path
        app=self.root/'Portable';bios=app/'Bios/bios.zip'
        with patch('smsrecomp.paths.export_directory',return_value=app):
            self.assertIsNone(selected_bios_path(['malformed']))
            save_preferences({'ng_bios':str(bios)})
            saved=load_preferences()['ng_bios'];self.assertFalse(Path(saved).is_absolute())
            self.assertEqual(selected_bios_path(saved),bios)

    def test_artwork_collapses_same_game_aliases_without_confusing_years(self):
        from smsrecomp.artwork import choose_cover
        names=["The King of Fighters '98 - The Slugfest _ King of Fighters '98 - Dream Match Never Ends (NGM-2420).png",
               "The King of Fighters '99 (NGM-2510).png"]
        self.assertEqual(choose_cover(names,'kof98',"The King of Fighters '98 - The Slugfest"),names[0])
        self.assertEqual(choose_cover(names,'kof99',"The King of Fighters '99"),names[1])


if __name__=='__main__':unittest.main()
