from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch
from unittest.mock import Mock
from threading import Event
from queue import Queue
from zipfile import ZipFile

from PIL import Image

from retrorecomp.compiled_games import Game, Inventory
from retrorecomp.game_details import Cards, synopsis, pe_icon
from retrorecomp.rom_sources import RomSources, rom_folders
from retrorecomp import game_metadata as metadata


class CardTests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.payload=b'\0'*16384
        self.game=Game(str(self.root/'Game.exe'),'sms',hashlib.sha256(self.payload).hexdigest(),'Example 2')
        self.cards=Cards(self.root/'converter')

    def test_sources_find_renamed_exact_zip_not_a_similarly_named_revision(self):
        root=self.root/'roms/subfolder'
        root.mkdir(parents=True)
        wrong=root/'Example 2.sms'
        wrong.write_bytes(b'\x01'*8192)
        correct=root/'unrelated filename.zip'
        with ZipFile(correct,'w') as archive:archive.writestr('exact.sms',b'X'*512+self.payload)
        before={p:p.read_bytes() for p in (wrong,correct)}
        resolver=RomSources(self.root/'converter')
        with patch('subprocess.Popen',side_effect=AssertionError('Never launch a ROM')):
            pairs=resolver.resolve([self.game],{'rom_paths':{'sms':str(root.parent)}})
        self.assertEqual(pairs[0][1],correct)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        # Same-sized replacement invalidates the cached content identity.
        correct.write_bytes(b'not a zip')
        self.assertFalse(RomSources(self.root/'converter').matches(correct,self.game))

    def test_sources_reuse_another_exports_exact_origin_and_portable_roots(self):
        source=self.root/'original.sms'
        source.write_bytes(self.payload)
        other=Game('',self.game.system,self.game.identity,'Other name',source=str(source))
        resolver=RomSources(self.root/'converter')
        pairs=resolver.resolve([self.game],{},known=[other])
        self.assertEqual(pairs[0][1],source)
        with patch('retrorecomp.rom_sources.export_directory',return_value=self.root):
            self.assertEqual(rom_folders({'rom_paths':{'sms':'roms','unknown':'x'}}),{'sms':self.root/'roms'})

    def test_source_report_path_is_durable_and_reused_after_index_reload(self):
        from retrorecomp.compiled_games import game_from_report
        report=self.root/'conversion-report.json'
        source=self.root/'source.sms'
        report.write_text(json.dumps(dict(tool='Retro-Recomp',system={'id':'sms'},
            rom={'sha256':self.game.identity},executable='Game.exe',source_rom=str(source))))
        inventory=Inventory(self.root/'inventory.json')
        inventory.remember(game_from_report(report,self.root))
        inventory.save()
        self.assertEqual(Inventory(inventory.path).snapshot()[0].source,str(source))

    def test_card_persists_offline_per_console_revision_and_language(self):
        record=dict(title='Example',description='<p>Existing source summary.</p>',provider='Example DB',
                    source='https://example.org/game/2',language='en')
        self.cards.save_metadata(self.game,'fr',record)
        loaded=Cards(self.root/'converter')
        with patch('retrorecomp.cover_sources.request',side_effect=AssertionError('No network for saved cards')):
            self.assertEqual(loaded.metadata(self.game,'fr')['description'],'Existing source summary.')
            self.assertEqual(loaded.metadata(self.game,'fr')['language'],'en')
            self.assertEqual(loaded.metadata(self.game,'en'),{})
            other=Game('','gg',self.game.identity,self.game.title)
            self.assertEqual(loaded.metadata(other,'fr'),{})
        text=synopsis('This is an existing source sentence. '*200)
        self.assertLessEqual(len(text),850)
        self.assertTrue(text.endswith('…'))

    def test_manual_cover_is_copied_and_available_without_original_file(self):
        raw=BytesIO();Image.new('RGB',(100,150),'red').save(raw,format='PNG')
        path=self.cards.set_cover(self.game,raw.getvalue(),override=True)
        self.assertEqual(self.cards.override(self.game),path)
        with patch('retrorecomp.game_details.pe_icon',side_effect=AssertionError('Cache comes first')):
            self.assertEqual(self.cards.cover(self.game),path.read_bytes())
        self.cards.save_metadata(self.game,'en',{'description':'Summary'})
        self.assertEqual(self.cards.override(self.game),path)

    def test_offline_cover_prefers_report_cache_to_executable_reads(self):
        image=self.root/'cached.png'
        Image.new('RGB',(100,150),'green').save(image)
        report=self.root/'report.json'
        report.write_text(json.dumps({'artwork':{'image':str(image)}}))
        self.game.report=str(report)
        with (patch('retrorecomp.cover_sources.request',side_effect=AssertionError('Offline')),
              patch('retrorecomp.game_details.pe_icon',side_effect=AssertionError('Cache comes first'))):
            self.assertEqual(self.cards.cover(self.game),image.read_bytes())

    def test_regeneration_refreshes_automatic_card_cover_and_preserves_manual_choice(self):
        from retrorecomp.game_details import read_json
        old=self.root/'old.png';front=self.root/'corrected-front.png'
        Image.new('RGB',(32,48),'green').save(old)
        Image.new('RGB',(32,48),'red').save(front)
        report=self.root/'report.json';self.game.report=str(report)
        report.write_text(json.dumps({'artwork':{'image':str(old)}}))
        # Older card caches have no report fingerprint and must migrate offline.
        self.cards.set_cover(self.game,old.read_bytes())
        self.cards.save_metadata(self.game,'en',{'description':'Saved summary'})
        with (patch('retrorecomp.cover_sources.request',side_effect=AssertionError('Offline')),
              patch('retrorecomp.game_details.pe_icon',side_effect=AssertionError('Prefer cached image'))):
            self.cards.cover(self.game)
            report.write_text(json.dumps({'artwork':{'image':str(front)}}))
            refreshed=self.cards.cover(self.game)
            self.assertEqual(Image.open(BytesIO(refreshed)).getpixel((0,0))[:3],(255,0,0))
            self.assertEqual(self.cards.metadata(self.game,'en')['description'],'Saved summary')
            def cached_json(path,*args,**kwargs):
                self.assertNotEqual(Path(path),report,'Unchanged cover must avoid parsing the report again')
                return read_json(path,*args,**kwargs)
            with patch('retrorecomp.game_details.read_json',side_effect=cached_json):
                self.cards.cover(self.game)
            manual=BytesIO();Image.new('RGB',(32,48),'gold').save(manual,format='PNG')
            chosen=self.cards.set_cover(self.game,manual.getvalue(),override=True)
            report.write_text(json.dumps({'artwork':{'image':str(old)}}))
            self.assertEqual(self.cards.cover(self.game),chosen.read_bytes())

    def test_non_pe_extraction_never_executes_binary(self):
        path=self.root/'Game'
        path.write_bytes(b'\x7fELFdata')
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):
            self.assertIsNone(pe_icon(path))

    def test_pe_icon_recovery_reads_a_bounded_resource_on_both_platforms(self):
        import struct
        raw=BytesIO();Image.new('RGB',(128,128),'gold').save(raw,format='PNG')
        image=raw.getvalue()
        data=bytearray(4096)
        data[:2]=b'MZ'
        def h(p,v):struct.pack_into('<H',data,p,v)
        def i(p,v):struct.pack_into('<I',data,p,v)
        i(60,64);data[64:68]=b'PE\0\0';h(70,1);h(84,240);h(88,0x20b)
        i(88+112+16,0x1000)
        section=88+240
        for offset,value in ((8,2048),(12,0x1000),(16,2048),(20,512)):i(section+offset,value)
        for relative,kind,next_offset in ((0,3,0x80000018),(24,1,0x80000030),(48,1033,72)):
            h(512+relative+14,1);i(512+relative+16,kind);i(512+relative+20,next_offset)
        i(512+72,0x1000+88);i(512+76,len(image));data[600:600+len(image)]=image
        path=self.root/'Game.exe';path.write_bytes(data)
        self.assertEqual(pe_icon(path),image)

    def test_favorites_survive_rescans_and_apply_to_copies_of_the_same_game(self):
        inventory=Inventory(self.root/'compiled.json')
        inventory.remember(self.game)
        inventory.set_favorite(self.game,True)
        fresh=Game(self.game.executable,'sms',self.game.identity,'Example 2')
        inventory.remember(fresh)
        other=Game(str(self.root/'copy.exe'),'sms',self.game.identity,'Example 2')
        inventory.remember(other)
        inventory.save()
        self.assertTrue(all(g.favorite for g in Inventory(inventory.path).snapshot()))
        inventory.set_favorite(other,False)
        self.assertFalse(any(g.favorite for g in Inventory(inventory.path).snapshot()))

    def test_elf_icon_recovery_is_portable_without_loading_binary(self):
        import struct
        from retrorecomp.game_details import elf_icon
        raw=BytesIO();Image.new('RGBA',(256,256),'blue').save(raw,format='BMP')
        image=raw.getvalue()
        data=bytearray(256+len(image))
        data[:6]=b'\x7fELF\x02\x01'
        struct.pack_into('<Q',data,40,64)
        struct.pack_into('<HH',data,58,64,1)
        struct.pack_into('<I',data,68,1)
        struct.pack_into('<Q',data,72,2)
        struct.pack_into('<QQ',data,88,256,len(image))
        data[256:]=image
        path=self.root/'Game';path.write_bytes(data)
        self.assertEqual(elf_icon(path),image)

    def test_gui_source_lookup_delivers_exact_path_before_requesting_manual_input(self):
        from retrorecomp.gui import Application
        from retrorecomp.platforms import target_id
        source=self.root/'roms/renamed.sms';source.parent.mkdir()
        source.write_bytes(self.payload)
        self.game.target=target_id()
        owner=Application.__new__(Application)
        owner.busy=owner.updating=owner.close_when_idle=False
        owner.compiled_inventory=Inventory(self.root/'compiled.json');owner.compiled_inventory.remember(self.game)
        owner.items={};owner.cancel=Event();owner.messages=Queue();owner.set_controls=Mock()
        owner.compiled_view=Mock();owner.language='en';owner.begin_reconvert=Mock()
        owner.preferences=Mock(return_value={'rom_paths':{'sms':str(source.parent)}})
        with patch('retrorecomp.gui.filedialog.askopenfilename',side_effect=AssertionError('Should find exact source')):
            with patch('retrorecomp.rom_sources.data_directory',return_value=self.root/'converter'):
                owner.reconvert_games([self.game])
                kind,pairs=owner.messages.get(timeout=10)
            self.assertEqual(kind,'sources_ready')
            owner.finish_source_lookup(pairs)
            owner.begin_reconvert.assert_called_once_with([(self.game,source)])

    def test_bulk_metadata_is_explicit_and_skips_already_saved_cards(self):
        from retrorecomp.game_card_view import GameCardView
        view=GameCardView.__new__(GameCardView)
        view.cards=self.cards;view.owner=Mock();view.owner.language='en'
        view.tr=lambda key,**kwargs:key
        view.pending=False;view.controls=Mock();view.run=Mock()
        self.cards.save_metadata(self.game,'en',{'description':'Already saved'})
        view.search_games([self.game])
        view.run.assert_not_called()
        view.search_games([self.game],refresh=True)
        self.assertEqual(view.run.call_args.args[0],'candidates')

    def test_automatic_card_selection_never_starts_online_search(self):
        from retrorecomp.game_card_view import GameCardView
        view=GameCardView.__new__(GameCardView)
        view.owner=Mock();view.owner.language='fr';view.tr=lambda key:key
        view.token=0;view.title=Mock();view.message=Mock();view.draw_cover=Mock()
        view.show_metadata=Mock();view.controls=Mock();view.localize=Mock();view.run=Mock()
        view.cards=self.cards
        with patch.object(metadata,'search',side_effect=AssertionError('Manual only')):
            view.select(self.game)
            self.assertEqual(view.run.call_args.args[0],'loaded')
            # The selection callback reads the local card only.
            self.assertEqual(view.run.call_args.kwargs,{'busy':False})

    def test_wikidata_filters_wrong_console_and_sequel_and_marks_general_dates(self):
        def entity(title,platform):
            return dict(id='Q123',labels={'en':{'value':title}},claims={
                'P400':[{'mainsnak':{'datavalue':{'value':{'id':platform}}}}],
                'P577':[{'mainsnak':{'datavalue':{'value':{'time':'+1992-01-01T00:00:00Z','precision':9}}}}]})
        for title,system,expected in (('Example 2','Q209868',1),('Example 1','Q209868',0),('Example 2','Q172742',0)):
            replies=[{'search':[{'id':'Q123'}]},{'entities':{'Q123':entity(title,system)}}]
            with patch.object(metadata,'_wiki',side_effect=replies):
                rows=metadata.wikidata('Example 2','sms','fr')
            self.assertEqual(len(rows),expected)
            if rows:self.assertEqual((rows[0]['release'],rows[0]['release_scope']),('1992','general'))

    def test_metadata_keeps_old_card_after_network_failure_and_rejects_secret_urls(self):
        self.cards.save_metadata(self.game,'en',{'description':'Old summary','source':'https://site.test/?apikey=secret'})
        with patch.object(metadata,'_wiki',side_effect=ValueError('Offline')):
            with self.assertRaises(ValueError):metadata.search('Example','sms','en',settings={'accounts':{}})
        self.assertEqual(self.cards.metadata(self.game,'en')['description'],'Old summary')
        self.assertEqual(self.cards.metadata(self.game,'en')['source'],'')

    def test_native_cards_do_not_change_other_console_knowledge(self):
        from retrorecomp.compilation_inputs import INTERFACE_MODULES
        self.assertTrue({'game_details','game_metadata','rom_sources','game_card_view'}<=INTERFACE_MODULES)
