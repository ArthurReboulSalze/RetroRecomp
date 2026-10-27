"""Synthetic multi-region archives and identity/bounds; no retail ROM needed."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import zlib

from retrorecomp.neogeo import (archive_members, identify_set, read_set, parse_neo,
    looks_like_neogeo_zip, validate_bios, combined_identity, BIOS_MEMBERS)
from retrorecomp.systems import profile_for_path, NEOGEO, PROFILES, UnsupportedConsoleError


class NeoGeoInputsTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.path=self.root/'renamed collection.zip'
        self.program=b'authored program'
        self.entries={'001-p1.p1':self.program,'001-m1.m1':b'sound','001-c1.c1':b'sprites'}
        self.write_zip()
        self.descriptor={'set':'authored','title':'Authored cartridge','parent':'','board':'standard',
                         'files':[{'name':'original.p1','crc32':zlib.crc32(self.program),
                                   'region':0,'optional':0}]}
        self.catalogue=[self.descriptor]

    def write_zip(self, entries=None):
        with ZipFile(self.path,'w',compression=ZIP_STORED) as archive:
            for name,data in (entries or self.entries).items():archive.writestr(name,data)

    def neo(self, lengths=(512,131072,65536,0,0,128), *, trailing=b''):
        header=bytearray(4096);header[:4]=b'NEO\x01'
        struct.pack_into('<6I',header,4,*lengths)
        header[44:52]=b'Authored'
        target=self.root/'authored.neo'
        target.write_bytes(header+b'\0'*sum(lengths)+trailing)
        return target

    def test_program_crc_identifies_a_renamed_zip(self):
        self.assertEqual(identify_set(self.path,self.catalogue)['set'],'authored')

    def test_filename_cannot_override_wrong_program_bytes(self):
        self.entries['001-p1.p1']=b'different program';self.write_zip()
        with self.assertRaisesRegex(ValueError,'revision/layout'):
            identify_set(self.path,self.catalogue,set_name='authored')

    def test_ambiguous_contents_require_explicit_selection(self):
        other=dict(self.descriptor,set='another')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            identify_set(self.path,[self.descriptor,other])
        self.assertEqual(identify_set(self.path,[self.descriptor,other],set_name='another')['set'],'another')

    def test_unknown_layout_is_not_compiled_with_another_game(self):
        with self.assertRaisesRegex(ValueError,'another game profile'):
            identify_set(self.path,[])

    def test_multi_file_detection_precedes_single_cartridge_zip(self):
        self.assertTrue(looks_like_neogeo_zip(self.path))
        self.assertIs(profile_for_path(self.path),NEOGEO)
        self.assertIs(profile_for_path(self.path),NEOGEO)
        self.assertIs(profile_for_path(self.path,'ng'),NEOGEO)
        self.assertIn(NEOGEO,PROFILES)

    def test_regular_console_archives_still_use_original_reader(self):
        self.write_zip({'game.gb':b'\0'*32768})
        self.assertEqual(profile_for_path(self.path).id,'gb')

    def test_eprom_program_member_is_detected_automatically(self):
        self.write_zip({'cart.ep1':b'authored program','cart.m1':b'sound','cart.c1':b'sprites'})
        self.assertTrue(looks_like_neogeo_zip(self.path))

    def test_merged_archive_has_its_own_bounded_streaming_budget(self):
        # Only central-directory metadata is authored; no large allocation.
        entries=[]
        for n in range(9):
            item=ZipInfo(f'component-{n}.bin');item.file_size=128*1024*1024;item.CRC=0
            entries.append(item)
        with patch('retrorecomp.neogeo.ZipFile') as archive:
            archive.return_value.__enter__.return_value.infolist.return_value=entries[:8]
            self.assertEqual(len(archive_members(self.path)),8)
            archive.return_value.__enter__.return_value.infolist.return_value=entries
            with self.assertRaisesRegex(ValueError,'expanded size'):archive_members(self.path)

    def test_content_identity_survives_member_renaming(self):
        first=read_set(self.path,self.catalogue)
        self.write_zip({'other-'+name:data for name,data in self.entries.items()})
        self.assertEqual(first.sha256,read_set(self.path,self.catalogue).sha256)
        self.assertIs(profile_for_path(self.path,'ng'),NEOGEO)

    def test_content_identity_changes_with_sound_revision(self):
        first=read_set(self.path,self.catalogue)
        self.entries['001-m1.m1']=b'another driver';self.write_zip()
        self.assertNotEqual(first.sha256,read_set(self.path,self.catalogue).sha256)

    def test_archive_crc_is_checked_from_real_bytes(self):
        data=self.path.read_bytes();offset=data.index(self.program)
        data=data[:offset]+bytes([data[offset]^1])+data[offset+1:];self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'CRC'):
            archive_members(self.path,hash_contents=True)

    def test_duplicate_basenames_are_rejected(self):
        self.write_zip({'first/001-p1.p1':b'a','second/001-p1.p1':b'b'})
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            archive_members(self.path)

    def test_valid_neo_has_independent_region_identity(self):
        rom=parse_neo(self.neo())
        self.assertEqual(rom.title,'Authored')
        self.assertEqual(len(rom.members),6)
        self.assertEqual(rom.members[2]['offset'],4096+512+131072)
        self.assertEqual(rom.members[2]['sha256'],hashlib.sha256(b'\0'*65536).hexdigest())

    def test_neo_header_size_cannot_read_outside_container(self):
        target=self.neo();data=bytearray(target.read_bytes());struct.pack_into('<I',data,4,16<<20);target.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'sizes'):
            parse_neo(target)

    def test_neo_rejects_trailing_data(self):
        with self.assertRaisesRegex(ValueError,'sizes'):
            parse_neo(self.neo(trailing=b'junk'))

    def test_neo_rejects_wrong_format_version(self):
        target=self.neo();data=bytearray(target.read_bytes());data[3]=2;target.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'signature/version'):
            parse_neo(target)

    def test_neo_board_header_participates_in_identity(self):
        target=self.neo();first=parse_neo(target)
        data=bytearray(target.read_bytes());struct.pack_into('<I',data,40,0x047);target.write_bytes(data)
        self.assertNotEqual(first.sha256,parse_neo(target).sha256)

    def test_neo_rejects_incomplete_fix_sound_and_sprites(self):
        for lengths in ((512,32,65536,0,0,128),(512,131072,65535,0,0,128),
                        (512,131072,65536,0,0,127)):
            with self.subTest(lengths=lengths),self.assertRaises(ValueError):parse_neo(self.neo(lengths))

    def test_neo_is_available_in_automatic_converter_detection(self):
        target=self.neo()
        self.assertIs(profile_for_path(target),NEOGEO)
        self.assertIs(profile_for_path(target),NEOGEO)

    def test_bios_needs_all_selected_members_and_correct_revision(self):
        records=[{'name':name,'bytes':size,'crc32':crc,'sha256':'a'*64}
                 for name,(size,crc) in BIOS_MEMBERS.items()]
        with patch('retrorecomp.neogeo.archive_members',return_value=records):
            self.assertEqual(validate_bios(self.path)['system'],'mvs')
        with patch('retrorecomp.neogeo.archive_members',return_value=records[1:]):
            with self.assertRaisesRegex(ValueError,'requires'):validate_bios(self.path)
        records[0]['crc32']^=1
        with patch('retrorecomp.neogeo.archive_members',return_value=records):
            with self.assertRaisesRegex(ValueError,'Incorrect BIOS'):validate_bios(self.path)

    def test_compilation_identity_includes_bios_and_tool_revisions(self):
        game=read_set(self.path,self.catalogue)
        bios={'sha256':'a'*64,'system':'mvs','region':'eu'}
        original=combined_identity(game,bios,engine_revision='a',loader_revision='b')
        changed=combined_identity(game,dict(bios,sha256='b'*64),engine_revision='a',loader_revision='b')
        self.assertNotEqual(original,changed)
        self.assertNotEqual(original,combined_identity(game,bios,engine_revision='c',loader_revision='b'))

    def authored_bios(self,changed=False,extra=False):
        data={name:('authored-'+name).encode() for name in BIOS_MEMBERS}
        if changed:data['sm1.sm1']+=b' changed'
        target=self.root/'bios.zip'
        with ZipFile(target,'w') as archive:
            for name,content in data.items():archive.writestr(name,content)
            if extra:archive.writestr('unused.txt',b'not selected')
        return target,{name:(len(content),zlib.crc32(content)) for name,content in data.items()}

    def test_state_identity_is_independent_of_title_and_unselected_bios_files(self):
        from retrorecomp.neogeo_build import state_config
        target=self.neo();bios,records=self.authored_bios()
        with patch('retrorecomp.neogeo.BIOS_MEMBERS',records):first=state_config(target,bios,'Authored')
        data=bytearray(target.read_bytes());data[44:52]=b'Renamed!';target.write_bytes(data)
        bios,records=self.authored_bios(extra=True)
        with patch('retrorecomp.neogeo.BIOS_MEMBERS',records):second=state_config(target,bios,'Renamed')
        def identity(header):return next(line for line in header.splitlines() if line.startswith('#define RR16_STATE_ROM '))
        self.assertEqual(identity(first),identity(second))
        self.assertNotEqual(first,second)  # Display/file names are still allowed to differ.

    def test_state_identity_changes_for_cart_or_selected_bios_content(self):
        from retrorecomp.neogeo_build import state_config
        target=self.neo();bios,records=self.authored_bios()
        with patch('retrorecomp.neogeo.BIOS_MEMBERS',records):first=state_config(target,bios,'Authored')
        data=bytearray(target.read_bytes());data[4096]^=1;target.write_bytes(data)
        with patch('retrorecomp.neogeo.BIOS_MEMBERS',records):cart_changed=state_config(target,bios,'Authored')
        bios,records=self.authored_bios(changed=True)
        with patch('retrorecomp.neogeo.BIOS_MEMBERS',records):bios_changed=state_config(target,bios,'Authored')
        self.assertNotEqual(first,cart_changed);self.assertNotEqual(cart_changed,bios_changed)

    def test_state_abi_can_use_frozen_modules_without_python_asset_files(self):
        import importlib
        from retrorecomp.neogeo_build import state_config
        from retrorecomp.paths import ASSETS
        from contextlib import ExitStack
        target=self.neo();bios,records=self.authored_bios()
        only_assets=self.root/'frozen-assets'
        for name in ('neogeo_state.c','neogeo_state_validate.c','neogeo_reference.c',
                     'neogeo_ym_state.inc','neogeo_native.c','neogeo_z80_native.h','neogeo_code_view.inc','neogeo_lspc_state.inc'):
            destination=only_assets/'native'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes((ASSETS/'native'/name).read_bytes())
        class FrozenLoader:
            def get_code(self,name):return compile('authored_compiler = 1','random-extraction/module.py','exec')
        with ExitStack() as stack:
            stack.enter_context(patch('retrorecomp.neogeo_build.ASSETS',only_assets))
            stack.enter_context(patch('retrorecomp.neogeo.BIOS_MEMBERS',records))
            for name in ('retrorecomp.neogeo_build','retrorecomp.neogeo_codegen','retrorecomp.neogeo_z80'):
                module=importlib.import_module(name)
                stack.enter_context(patch.object(module,'__file__',str(only_assets/'absent.py')))
                stack.enter_context(patch.object(module,'__loader__',FrozenLoader()))
            header=state_config(target,bios,'Authored')
        self.assertIn('#define RR16_STATE_ABI ',header)


if __name__=='__main__':unittest.main()
