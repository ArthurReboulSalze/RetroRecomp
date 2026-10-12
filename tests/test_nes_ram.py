from pathlib import Path
import tempfile,unittest
from smsrecomp.core import ConversionError
from smsrecomp.nes import read_nes_rom,_seed_sites
from smsrecomp.nes_ram import read_sites,trace_text,write_guards,opcode_sources,shared_sites
from smsrecomp.knowledge import validate_payload
from tools.nes_state_selftest import resume_input

class NesRamTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        header=bytearray(b'NES\x1a'+bytes(12));header[4]=1;header[5]=1
        header[6]=4  # Trainer bytes must never supply a code hint.
        prg=bytearray([0xEA]*16384);prg[10]=0xA9
        path=self.root/'authored.nes';path.write_bytes(header+bytes([0x02]*512)+prg+bytes([0x03]*8192))
        self.rom=read_nes_rom(path)

    def test_state_replay_preserves_two_ports_and_an_event_at_the_load_frame(self):
        source=self.root/'play.input';target=self.root/'resume.input'
        source.write_text('0 2:LEFT\n10 RIGHT+B\n20 A\n25 2:-\n30 -\n')
        resume_input(source,20,target)
        self.assertEqual(target.read_text(),'0 1:RIGHT+B\n0 2:LEFT\n0 1:A\n5 2:-\n10 1:-\n')
        self.assertEqual(source.read_text(),'0 2:LEFT\n10 RIGHT+B\n20 A\n25 2:-\n30 -\n')

    def test_state_replay_rejects_unordered_or_negative_schedules(self):
        source=self.root/'play.input'
        for data in ('5 A\n4 B\n','-1 A\n'):
            source.write_text(data)
            with self.assertRaises(ValueError):resume_input(source,20,self.root/'resume.input')

    def test_trace_preserves_rom_and_multiple_ram_opcodes_but_excludes_mmio(self):
        path=self.root/'entries.trace'
        path.write_text(trace_text({'4K:00:8000'},{(0x300,0xA9),(0x300,0xEA),(0x6000,0xA9)})+
                        '# ram:2000:EA\n# ram:4016:A9\n# ram:FFFF:FF\n# ram:0301:FFFF\n')
        self.assertEqual(_seed_sites(path),{'4k:0:8000'})
        self.assertEqual(read_sites(path),{(0x300,0xA9),(0x300,0xEA),(0x6000,0xA9),(0xFFFF,0xFF)})
        self.assertEqual(read_sites(self.root/'missing.trace'),set())

    def test_shared_references_only_reconstruct_from_prg_not_trainer_or_chr(self):
        sources=opcode_sources(self.rom)
        self.assertEqual(sources[0xA9],16+512+10)
        self.assertNotIn(2,sources);self.assertNotIn(3,sources)
        record={'ram_opcode_refs':[[0x300,sources[0xA9]],[0x6000,sources[0xEA]],
                                   [0x300,16],[0x300,len(self.rom.data)-1]]}
        self.assertEqual(shared_sites(self.rom,record),{(0x300,0xA9),(0x6000,0xEA)})

    def test_guards_reject_unknown_opcode_and_unobserved_pc_without_operand_constants(self):
        path=self.root/'game_cyc.c'
        path.write_text('prefix\n/* RR_NES_RAM_GUARD_BEGIN */\nold\n/* RR_NES_RAM_GUARD_END */\nsuffix\n')
        self.assertEqual(write_guards(path,{(0x300,0xA9),(0x2000,0xEA),(0x300,2)},self.rom),1)
        code=path.read_text();self.assertIn('0x0300A9u',code)
        self.assertNotIn('0x2000EAu',code);self.assertNotIn('0x030002u',code)
        self.assertIn('ram_keys[lo] == key',code)
        before=path.stat().st_mtime_ns;write_guards(path,{(0x300,0xA9)},self.rom)
        self.assertEqual(path.stat().st_mtime_ns,before)
        path.write_text('unknown generator')
        with self.assertRaises(ConversionError):write_guards(path,[],self.rom)

    def test_shared_schema_rejects_register_hints_and_bad_reference_offsets(self):
        for pc,offset in [(0x2000,526),(0x4016,526),(0x10000,526),(0x300,len(self.rom.data))]:
            payload={'schema':1,'consoles':{'nes':{self.rom.sha256:{'engine':'1'*40,
                'rom_bytes':len(self.rom.data),'ram_opcode_refs':[[pc,offset]]}}}}
            with self.subTest(pc=pc,offset=offset),self.assertRaises(ValueError):validate_payload(payload)

    def test_configure_receipt_binds_added_guards_and_legacy_rom_seed_case(self):
        import hashlib,json
        project=self.root/'cycle';generated=project/'generated';generated.mkdir(parents=True)
        umbrella=generated/'game_cyc.c'
        umbrella.write_text('/* RR_NES_RAM_GUARD_BEGIN */\nold\n/* RR_NES_RAM_GUARD_END */\n')
        other=generated/'game_cyc_live.c';other.write_text('authored body\n')
        (project/'complete.json').write_text('{}')
        write_guards(umbrella,{(0x300,0xA9)},self.rom)
        receipt=json.loads((project/'complete.json').read_text())
        self.assertEqual(receipt,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (umbrella,other)})
        trace=self.root/'legacy.trace';trace.write_text('4K:00:8abc 12\n4k:0a:9000\n')
        self.assertEqual(_seed_sites(trace),{'4k:0:8ABC','4k:A:9000'})

    def test_snapshot_does_not_promote_a_trace_changed_after_validation(self):
        from datetime import datetime
        import gzip,json,os
        from types import SimpleNamespace
        from unittest.mock import patch
        from smsrecomp.nes import ENGINE_REV
        from smsrecomp.knowledge import load
        from tools.build_compilation_knowledge import build
        library=self.root/'library';directory=library/self.rom.sha256/ENGINE_REV
        directory.mkdir(parents=True);trace=directory/'cycle-seeds.trace'
        trace.write_text('# ram:0300:A9\n')
        report_path=self.root/'reports/Nintendo NES/datas/reports/authored/conversion-report.json'
        report_path.parent.mkdir(parents=True)
        report={'system':{'id':'nes'},'rom':{'sha256':self.rom.sha256},'compiler':{'revision':ENGINE_REV},
                'native_validation':{'passed':True},'created_utc':'2026-10-12T00:00:00+00:00'}
        report_path.write_text(json.dumps(report));qualified_at=datetime.fromisoformat(report['created_utc']).timestamp()
        item=SimpleNamespace(system='nes',sha256=self.rom.sha256,error=None)
        profile=SimpleNamespace(read_rom=lambda _:self.rom);out=self.root/'snapshot.json.gz'
        with patch('tools.build_compilation_knowledge.identify',return_value=item),\
                patch('tools.build_compilation_knowledge.get_profile',return_value=profile),\
                patch('tools.build_compilation_knowledge.library_root',return_value=library):
            os.utime(trace,(qualified_at+1,qualified_at+1))
            summary=build([self.rom.path],reports=self.root/'reports',output=out)
            self.assertEqual(summary['consoles']['nes']['games'],0)
            os.utime(trace,(qualified_at-1,qualified_at-1))
            build([self.rom.path],reports=self.root/'reports',output=out)
            record=load(out)['consoles']['nes'][self.rom.sha256]
            self.assertEqual(record['ram_opcode_refs'],[[0x300,16+512+10]])
            self.assertNotIn('bytes',record)
            self.assertNotIn(str(self.root),gzip.decompress(out.read_bytes()).decode())

if __name__=='__main__':unittest.main()
