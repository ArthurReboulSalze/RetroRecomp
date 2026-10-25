from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import gzip
import hashlib
import json
import os
import tempfile
import unittest
from retrorecomp import knowledge, gameboy, core
from retrorecomp.library import GameMemory, write_manifest
from retrorecomp import snes_spc, supernintendo


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        data = bytes(range(256)) * 256
        self.rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest(),
                                   path=self.root/'authored.gb', system_id='gb')
        self.addCleanup(knowledge.load.cache_clear)

    def install(self, system, fields, engine):
        payload = {'schema':1,'consoles':{system:{self.rom.sha256:{
            'engine':engine,'rom_bytes':len(self.rom.data),**fields}}}}
        path = self.root/knowledge.RESOURCE;path.parent.mkdir(exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(payload).encode(),mtime=0))
        self.addCleanup(patch.stopall)
        patch('retrorecomp.knowledge.ASSETS',self.root).start()
        return payload

    def test_read_only_hints_bound_to_console_engine_size_and_rom(self):
        self.install('gb',{'rom_entries':[[1,0x4567]]},gameboy.ENGINE_REV)
        before = sorted(p.relative_to(self.root) for p in self.root.rglob('*'))
        self.assertEqual(knowledge.record_for('gb',self.rom,gameboy.ENGINE_REV)['rom_entries'],[[1,0x4567]])
        self.assertFalse(knowledge.record_for('nes',self.rom,gameboy.ENGINE_REV))
        self.assertFalse(knowledge.record_for('gb',self.rom,'0'*40))
        wrong = SimpleNamespace(data=b'x'*len(self.rom.data),sha256=self.rom.sha256)
        self.assertFalse(knowledge.record_for('gb',wrong,gameboy.ENGINE_REV))
        self.assertEqual(before,sorted(p.relative_to(self.root) for p in self.root.rglob('*')))

    def test_bundled_and_local_gb_entries_merge_custom_library_can_start_empty(self):
        self.install('gb',{'rom_entries':[[1,0x4567]]},gameboy.ENGINE_REV)
        trace = self.root/'local.trace';trace.write_text('2:6000\n')
        with patch('retrorecomp.gameboy._verified_trace',return_value=trace):
            self.assertEqual(gameboy._known_entries(self.rom),{(1,0x4567),(2,0x6000)})
            for variable in ('RETRO_RECOMP_LIBRARY_DIR','SMSRECOMP_LIBRARY_DIR','RETRO_RECOMP_BUNDLED_KNOWLEDGE'):
                with patch.dict(os.environ,{variable:'0'}):
                    self.assertEqual(gameboy._known_entries(self.rom),{(2,0x6000)})

    def test_references_reconstruct_from_supplied_rom_without_embedded_bytes(self):
        payload=self.install('md',{'ram_refs':[[0xff0010,10,4]]},'1'*40)
        self.assertEqual(knowledge.ram_variants('md',self.rom,'1'*40),
                         [{'address':0xff0010,'bytes':self.rom.data[10:14].hex()}])
        payload['consoles']['md'][self.rom.sha256]['private_path']='K:/private'
        with self.assertRaises(ValueError):knowledge.validate_payload(payload)

    def test_rejects_ram_as_gb_rom_hint_and_out_of_bounds_references(self):
        for fields in ({'rom_entries':[[1,0xc000]]},{'rom_entries':[[50,0x4567]]},
                       {'rom_entries':[['1',0x4567]]}):
            payload={'schema':1,'consoles':{'gb':{self.rom.sha256:{
                'engine':gameboy.ENGINE_REV,'rom_bytes':len(self.rom.data),**fields}}}}
            with self.assertRaises(ValueError):knowledge.validate_payload(payload)
        payload=self.install('md',{'ram_refs':[[0xff0010,len(self.rom.data)-2,4]]},'1'*40)
        with self.assertRaises(ValueError):knowledge.validate_payload(payload)
        self.assertFalse(knowledge.record_for('md',self.rom,'1'*40))

    def test_corrupt_snapshot_leaves_normal_discovery_available(self):
        self.install('gb', {'rom_entries': [[1, 0x4567]]}, gameboy.ENGINE_REV)
        path = self.root / knowledge.RESOURCE
        # Valid gzip header, invalid compressed block.
        path.write_bytes(bytes.fromhex('1f8b080000000000000307') + bytes(16))
        self.assertEqual(knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV), {})

    def test_snes_extended_ram_references_keep_per_console_and_size_limits(self):
        def payload(system,count):
            return {'schema':1,'consoles':{system:{self.rom.sha256:{
                'engine':'1'*40,'rom_bytes':len(self.rom.data),
                'ram_refs':[[0x7e0000+4*n,n%8192,4] for n in range(count)]}}}}
        self.assertEqual(knowledge.validate_payload(payload('snes',4096))['schema'],1)
        with self.assertRaises(ValueError):knowledge.validate_payload(payload('snes',16385))
        with self.assertRaises(ValueError):knowledge.validate_payload(payload('md',2049))

    def test_snes_opcode_hints_reconstruct_only_the_guard_and_preserve_local_data(self):
        engine=supernintendo.knowledge_engine(self.rom)
        payload=self.install('snes',{'ram_opcode_refs':[[0x7e0100,0xa9]]},engine)
        journal=self.root/'absent'/'native-ram.json'
        with patch('retrorecomp.supernintendo.memory_file',return_value=journal):
            self.assertEqual(supernintendo.read_ram_opcodes(self.rom),[(0x7e0100,0xa9)])
            self.assertFalse(journal.parent.exists())
            wrong=SimpleNamespace(data=b'x'*len(self.rom.data),sha256=self.rom.sha256)
            self.assertEqual(supernintendo.read_ram_opcodes(wrong),[])
        record=payload['consoles']['snes'][self.rom.sha256]
        for entry in ([0x1000000,0xa9],[0x7e0100,len(self.rom.data)],[0x7e0100,-1]):
            record['ram_opcode_refs']=[entry]
            with self.assertRaises(ValueError):knowledge.validate_payload(payload)

    def test_snes_ranges_preserve_all_guarded_opcodes_and_exclude_io(self):
        from tools.build_compilation_knowledge import compact_spc_refs
        refs = [[pc,op] for pc in range(65536) if not 0xf0 <= pc <= 0xff
                for op in (0,pc % 7,255)]
        ranges = compact_spc_refs(refs)
        expanded = {(pc,offset) for first,last,offset in ranges for pc in range(first,last+1)}
        self.assertEqual(expanded,{tuple(e) for e in refs})
        engine = supernintendo.knowledge_engine(self.rom)
        self.install('snes',{'spc_refs':refs},engine)
        with patch('retrorecomp.snes_spc.memory_file',return_value=self.root/'absent'):
            legacy = snes_spc.read_masks(self.rom)
        payload = self.install('snes',{'spc_ranges':ranges},engine)
        knowledge.load.cache_clear()
        with patch('retrorecomp.snes_spc.memory_file',return_value=self.root/'absent'):
            self.assertEqual(snes_spc.read_masks(self.rom),legacy)
        record=payload['consoles']['snes'][self.rom.sha256]
        for invalid in ([9,8,0],[0,65536,0],[0xef,0x100,0],[0x100,0x100,len(self.rom.data)]):
            record['spc_ranges']=[invalid]
            with self.assertRaises(ValueError):knowledge.validate_payload(payload)
        record['spc_ranges']=[[0x100,65535,0]]*5
        with self.assertRaises(ValueError):knowledge.validate_payload(payload)

    def test_bounded_loader_rejects_oversized_snapshot(self):
        self.install('gb', {'rom_entries': [[1, 0x4567]]}, gameboy.ENGINE_REV)
        with patch('retrorecomp.knowledge.MAX_BYTES', 32):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                knowledge.load(self.root / knowledge.RESOURCE)
            self.assertEqual(knowledge.record_for('gb', self.rom, gameboy.ENGINE_REV), {})

    def test_oversized_refresh_preserves_existing_snapshot(self):
        from tools.build_compilation_knowledge import build
        self.install('gb', {'rom_entries': [[1, 0x4567]]}, gameboy.ENGINE_REV)
        output = self.root / knowledge.RESOURCE
        before = output.read_bytes()
        with patch('tools.build_compilation_knowledge.MAX_BYTES', 32):
            with self.assertRaisesRegex(ValueError, 'size budget'):
                build([], reports=self.root, output=output, base=output)
        self.assertEqual(output.read_bytes(), before)

    def test_sega_hints_recheck_live_rom_window_and_preserve_local_priority(self):
        self.rom.system_id='sms'
        address=0x150;fnv=2166136261
        for value in self.rom.data[address:address+256]:fnv=((fnv^value)*16777619)&0xffffffff
        entry=[address,0,1,0,fnv]
        self.install('sms',{'rom_entries':[entry],'pattern_refs':[[10]]},core.ENGINE_REV)
        with patch('retrorecomp.library.library_root',return_value=self.root/'local'):
            memory=GameMemory(self.rom)
        self.assertEqual(memory.seeds(),{tuple(entry)})

        self.assertIn(self.rom.data[10:14],memory.code_patterns())
        self.assertFalse(memory.directory.exists())
        memory.directory.mkdir(parents=True)
        bad=entry.copy();bad[-1]^=1
        write_manifest(memory.journal,{tuple(bad)})
        self.assertEqual(memory.seeds(),{tuple(entry)})

    def test_spc_masks_merge_local_and_rom_derived_opcodes_without_writes(self):
        import base64, zlib
        engine = supernintendo.knowledge_engine(self.rom)
        self.install('snes', {'spc_refs': [[0x200, 17]]}, engine)
        path = self.root / 'spc-native.json'
        masks = bytearray(snes_spc.MASK_BYTES)
        masks[0x200 * 32 + 5 // 8] = 1 << (5 & 7)
        record = {'schema': 1, 'rom_sha256': self.rom.sha256,
                  'opcode_masks': base64.b64encode(zlib.compress(masks)).decode()}
        path.write_text(json.dumps(record), encoding='utf-8')
        before = path.read_bytes()
        with patch('retrorecomp.snes_spc.memory_file', return_value=path):
            merged = snes_spc.read_masks(self.rom)
            self.assertEqual(merged[0x200 * 32], 1 << 5)
            self.assertEqual(merged[0x200 * 32 + 2], 1 << 1)
            self.assertEqual(path.read_bytes(), before)
            path.unlink()
            shared = snes_spc.read_masks(self.rom)
            self.assertEqual(shared[0x200 * 32], 0)
            self.assertEqual(shared[0x200 * 32 + 2], 1 << 1)
            self.assertFalse(path.exists())

    def test_builder_exports_only_qualified_numeric_hints(self):
        from tools.build_compilation_knowledge import build
        engine = supernintendo.knowledge_engine(self.rom)
        reports = self.root / 'reports'
        path = reports / 'Super Nintendo/datas/reports/fixture/conversion-report.json'
        path.parent.mkdir(parents=True)
        item = SimpleNamespace(system='snes', sha256=self.rom.sha256, error=None)
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        masks = bytearray(snes_spc.MASK_BYTES)
        masks[0x200 * 32 + 2] = 2
        destination = self.root / 'snapshot.json.gz'
        with patch('tools.build_compilation_knowledge.identify', return_value=item), \
                patch('tools.build_compilation_knowledge.get_profile', return_value=profile), \
                patch('retrorecomp.supernintendo.read_ram_variants', return_value=[
                    {'address': 0x7e0100, 'bytes': self.rom.data[10:14].hex()},
                    {'address': 0x7e0200, 'bytes': 'ffffeeee'}]), \
                patch('retrorecomp.snes_spc.read_masks', return_value=bytes(masks)):
            summary = build([self.rom.path], reports=reports, output=destination)
            self.assertEqual(summary['consoles']['snes']['games'], 0)
            report = {'system': {'id': 'snes'}, 'rom': {'sha256': self.rom.sha256},
                      'created_utc': '2099-01-01T00:00:00+00:00',
                      'native_validation': {'passed': True}, 'compiler': {'revision': engine}}
            path.write_text(json.dumps(report), encoding='utf-8')
            summary = build([self.rom.path], reports=reports, output=destination)
        record = knowledge.load(destination)['consoles']['snes'][self.rom.sha256]
        self.assertEqual(record['ram_refs'], [[0x7e0100, 10, 4]])
        self.assertEqual(record['ram_opcode_refs'],[[0x7e0100,10],[0x7e0200,255]])
        self.assertEqual(record['spc_refs'], [[0x200, 17]])
        self.assertEqual(summary['omitted']['ram_without_rom_source'], 0)
        self.assertEqual(summary['qualification'], {'standard': 1})
        self.assertNotIn('bytes', record)
        self.assertNotIn(str(self.root), gzip.decompress(destination.read_bytes()).decode())

    def test_builder_counts_quick_checks_from_shared_paths_apart(self):
        from tools.build_compilation_knowledge import qualification_origin
        self.assertEqual(qualification_origin({}), 'standard')
        self.assertEqual(qualification_origin({'scan_level': 'extended'}), 'extended')
        self.assertEqual(qualification_origin({'scan_level': 'quick', 'shared_paths': {
            'level': 'standard', 'records': 1, 'quick': True}}), 'quick_shared_paths')
        self.assertEqual(qualification_origin({'scan_level': 'quick', 'bundled_paths': {
            'level': 'standard', 'quick': True}}), 'quick_bundled_paths')
        self.assertEqual(qualification_origin({'scan_level': 'quick', 'upgrade': {}}), 'quick')
        self.assertEqual(qualification_origin({'upgrade': {'from': '1.5.0'}}), 'quick_upgrade')
        # A console whose report has no scan_level: the batch's record decides.
        self.assertEqual(qualification_origin({'shared_paths': {'level': 'standard', 'quick': True}}),
                         'quick_shared_paths')
        self.assertEqual(qualification_origin({'shared_paths': {'level': 'standard', 'quick': False}}), 'standard')

    def test_snes_refresh_keeps_qualified_record_when_either_cpu_journal_is_newer(self):
        from datetime import datetime
        from tools.build_compilation_knowledge import build
        engine=supernintendo.knowledge_engine(self.rom)
        reports=self.root/'reports'
        path=reports/'Super Nintendo/datas/reports/fixture/conversion-report.json'
        path.parent.mkdir(parents=True)
        report={'system':{'id':'snes'},'rom':{'sha256':self.rom.sha256},
                'created_utc':'2026-10-12T10:00:00+00:00','native_validation':{'passed':True},
                'compiler':{'revision':engine}}
        path.write_text(json.dumps(report));when=datetime.fromisoformat(report['created_utc']).timestamp()
        main,sound=self.root/'main.json',self.root/'sound.json'
        for p in (main,sound):p.write_text('{}');os.utime(p,(when-1,when-1))
        old={'engine':engine,'rom_bytes':len(self.rom.data),'ram_refs':[[0x7e0100,10,4]]}
        base=self.root/'base.json.gz';base.write_bytes(gzip.compress(json.dumps({'schema':1,'consoles':{'snes':{self.rom.sha256:old}}}).encode()))
        output=self.root/'updated.json.gz'
        with patch('tools.build_compilation_knowledge.identify',return_value=SimpleNamespace(system='snes',sha256=self.rom.sha256,error=None)), \
             patch('tools.build_compilation_knowledge.get_profile',return_value=SimpleNamespace(read_rom=lambda _:self.rom)), \
             patch('retrorecomp.supernintendo.memory_file',return_value=main), \
             patch('retrorecomp.snes_spc.memory_file',return_value=sound), \
             patch('retrorecomp.supernintendo.read_ram_variants',return_value=[]), \
             patch('retrorecomp.snes_spc.read_masks',return_value=bytes(snes_spc.MASK_BYTES)):
            for p in (main,sound):
                os.utime(p,(when+1,when+1))
                summary=build([self.rom.path],reports=reports,output=output,base=base)
                self.assertEqual(summary['omitted']['unqualified'],1)
                self.assertEqual(knowledge.load(output)['consoles']['snes'][self.rom.sha256],old)
                os.utime(p,(when-1,when-1))
            self.assertEqual(build([self.rom.path],reports=reports,output=output,base=base)['refresh']['snes']['requalified'],1)
            del report['created_utc'];path.write_text(json.dumps(report))
            self.assertEqual(build([self.rom.path],reports=reports,output=output,base=base)['omitted']['unqualified'],1)

    def test_md_refresh_does_not_promote_observations_after_qualification(self):
        from datetime import datetime
        from tools.build_compilation_knowledge import build
        from retrorecomp.console16 import REPOSITORIES
        engine = REPOSITORIES['md'][1]
        reports = self.root / 'reports'
        report_path = reports / 'Mega Drive/datas/reports/fixture/conversion-report.json'
        report_path.parent.mkdir(parents=True)
        report = {'system': {'id': 'md'}, 'rom': {'sha256': self.rom.sha256},
            'created_utc': '2026-10-11T10:00:00+00:00',
            'native_validation': {'passed': True}, 'compiler': {'revision': engine}}
        qualified_at = datetime.fromisoformat(report['created_utc']).timestamp()
        main, sound = self.root / 'main.json', self.root / 'sound.json'
        for path in (main, sound):
            path.write_text('{}', encoding='ascii')
            os.utime(path, (qualified_at - 1, qualified_at - 1))
        retained = {'engine': engine, 'rom_bytes': len(self.rom.data), 'rom_entries': [[0x200]]}
        base = self.root / 'base.json.gz'
        base.write_bytes(gzip.compress(json.dumps({'schema': 1, 'consoles': {
            'md': {self.rom.sha256: retained}}}).encode(), mtime=0))
        before = base.read_bytes()
        output = self.root / 'snapshot.json.gz'
        item = SimpleNamespace(system='md', sha256=self.rom.sha256, error=None)
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('tools.build_compilation_knowledge.identify', return_value=item), \
                patch('tools.build_compilation_knowledge.get_profile', return_value=profile), \
                patch('retrorecomp.megadrive.memory_file', return_value=main), \
                patch('retrorecomp.megadrive_z80.memory_file', return_value=sound), \
                patch('retrorecomp.megadrive.read_entries', return_value={0x200, 0x210}), \
                patch('retrorecomp.megadrive.read_ram_variants', return_value=[]), \
                patch('retrorecomp.megadrive_z80.read_variants', return_value=[]):
            report_path.write_text(json.dumps(report), encoding='utf-8')
            for modified in (main, sound):
                with self.subTest(cpu=modified.name):
                    os.utime(modified, (qualified_at + 1, qualified_at + 1))
                    summary = build([self.rom.path], reports=reports, output=output, base=base)
                    self.assertEqual(summary['omitted']['unqualified'], 1)
                    self.assertEqual(knowledge.load(output)['consoles']['md'][self.rom.sha256], retained)
                    self.assertEqual(summary['refresh']['md']['requalified'], 0)
                    os.utime(modified, (qualified_at - 1, qualified_at - 1))
            summary = build([self.rom.path], reports=reports, output=output, base=base)
            self.assertEqual(summary['refresh']['md']['requalified'], 1)
            self.assertEqual(knowledge.load(output)['consoles']['md'][self.rom.sha256]['rom_entries'],
                             [[0x200], [0x210]])
            del report['created_utc']
            report_path.write_text(json.dumps(report), encoding='utf-8')
            summary = build([self.rom.path], reports=reports, output=output, base=base)
            self.assertEqual(summary['omitted']['unqualified'], 1)
            self.assertEqual(knowledge.load(output)['consoles']['md'][self.rom.sha256], retained)
        self.assertEqual(base.read_bytes(), before)

    def test_partial_refresh_keeps_other_consoles_and_requires_new_validation(self):
        from tools.build_compilation_knowledge import build
        record = {'engine': gameboy.ENGINE_REV, 'rom_bytes': len(self.rom.data),
                  'rom_entries': [[1, 0x4567]]}
        other_sha = 'a' * 64
        other_record = {'engine': '1' * 40, 'rom_bytes': len(self.rom.data),
                        'rom_entries': [[0, 0x8000]]}
        base = self.root / 'base.json.gz'
        base.write_bytes(gzip.compress(json.dumps({'schema': 1, 'consoles': {
            'gb': {self.rom.sha256: record}, 'nes': {other_sha: other_record}}}).encode(), mtime=0))
        before = base.read_bytes()
        output = self.root / 'refresh.json.gz'
        reports = self.root / 'reports'
        report_path = reports / 'Game Boy/datas/reports/fixture/conversion-report.json'
        report_path.parent.mkdir(parents=True)
        report = {'system': {'id': 'gb'}, 'rom': {'sha256': self.rom.sha256},
                  'native_validation': {'passed': False},
                  'compiler': {'revision': gameboy.ENGINE_REV}}
        report_path.write_text(json.dumps(report), encoding='utf-8')
        trace = self.root / 'entries.trace'
        trace.write_text('2:6000\n', encoding='ascii')
        item = SimpleNamespace(system='gb', sha256=self.rom.sha256, error=None)
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        with patch('tools.build_compilation_knowledge.identify', return_value=item), \
                patch('tools.build_compilation_knowledge.get_profile', return_value=profile), \
                patch('retrorecomp.gameboy._verified_trace', return_value=trace):
            summary = build([self.rom.path], reports=reports, output=output, base=base)
            self.assertEqual(knowledge.load(output)['consoles']['gb'][self.rom.sha256], record)
            self.assertEqual(summary['refresh']['gb'], {'retained': 1, 'requalified': 0, 'added': 0})
            self.assertEqual(summary['omitted']['unqualified'], 1)
            report['native_validation']['passed'] = True
            report_path.write_text(json.dumps(report), encoding='utf-8')
            summary = build([self.rom.path], reports=reports, output=output, base=base)
        payload = knowledge.load(output)
        self.assertEqual(payload['consoles']['gb'][self.rom.sha256]['rom_entries'], [[2, 0x6000]])
        self.assertEqual(payload['consoles']['nes'][other_sha], other_record)
        self.assertEqual(summary['refresh']['gb'], {'retained': 0, 'requalified': 1, 'added': 0})
        self.assertEqual(summary['refresh']['nes']['retained'], 1)
        self.assertEqual(base.read_bytes(), before)

    def test_partial_refresh_rejects_private_base_before_replacing_output(self):
        from tools.build_compilation_knowledge import build
        base = self.root / 'private.json.gz'
        base.write_bytes(gzip.compress(json.dumps({'schema': 1, 'consoles': {
            'gb': {self.rom.sha256: {'engine': gameboy.ENGINE_REV,
                'rom_bytes': len(self.rom.data), 'private_path': 'K:/private'}}}}).encode(), mtime=0))
        output = self.root / 'unchanged.json.gz'
        output.write_bytes(b'previous resource')
        with self.assertRaises(ValueError):
            build([], reports=self.root/'reports', output=output, base=base)
        self.assertEqual(output.read_bytes(), b'previous resource')

    def test_sega_builder_requires_matching_native_report_and_nonempty_checks(self):
        from tools.build_compilation_knowledge import build
        reports = self.root / 'reports'
        report_path = reports / 'Master System/datas/reports/fixture/conversion-report.json'
        report_path.parent.mkdir(parents=True)
        report = {'system': {'id': 'sms'}, 'rom': {'sha256': self.rom.sha256},
            'created_utc': '2026-10-09T00:00:00+00:00', 'backend': 'banked',
            'native_validation': {'passed': False}, 'engine_revision': core.ENGINE_REV}
        generation = {'created_utc': report['created_utc'], 'engine_revision': core.ENGINE_REV,
            'reference_vdp_trace_match': True, 'checks': [{'passed': True}]}
        memory = SimpleNamespace(metadata=lambda: {'generations': [generation]},
            seeds=lambda: set(), journal=self.root/'observations.log',
            code_journal=self.root/'patterns',
            code_patterns=lambda: {self.rom.data[10:14], b'\xff' * 4})
        item = SimpleNamespace(system='sms', sha256=self.rom.sha256, error=None)
        profile = SimpleNamespace(read_rom=lambda path: self.rom)
        output = self.root / 'snapshot.json.gz'
        with patch('tools.build_compilation_knowledge.identify', return_value=item), \
                patch('tools.build_compilation_knowledge.get_profile', return_value=profile), \
                patch('retrorecomp.knowledge_build.GameMemory', return_value=memory):
            report_path.write_text(json.dumps(report), encoding='utf-8')
            self.assertEqual(build([self.rom.path], reports=reports, output=output)['consoles']['sms']['games'], 0)
            report['native_validation']['passed'] = True
            report_path.write_text(json.dumps(report), encoding='utf-8')
            summary = build([self.rom.path], reports=reports, output=output)
            self.assertEqual(summary['consoles']['sms']['games'], 1)
            # Include qualified shared windows even when no local journal was
            # needed; dynamic patterns without ROM bytes stay private.
            record = knowledge.load(output)['consoles']['sms'][self.rom.sha256]
            self.assertEqual(record['pattern_refs'], [[10]])
            self.assertEqual(summary['omitted']['ram_without_rom_source'], 1)
            generation['created_utc'] = 'old qualification'
            self.assertEqual(build([self.rom.path], reports=reports, output=output)['consoles']['sms']['games'], 0)
            generation['created_utc'] = report['created_utc']
            generation['checks'] = []
            self.assertEqual(build([self.rom.path], reports=reports, output=output)['consoles']['sms']['games'], 0)
            generation['checks'] = [{'passed': True}]
            # A failed later attempt leaves the old successful report intact,
            # but may have appended new observations to the local journal.
            memory.code_journal.write_text('01020304\n', encoding='ascii')
            from datetime import datetime
            qualified_at = datetime.fromisoformat(report['created_utc']).timestamp()
            os.utime(memory.code_journal, (qualified_at - 1, qualified_at - 1))
            self.assertEqual(build([self.rom.path], reports=reports, output=output)['consoles']['sms']['games'], 1)
            os.utime(memory.code_journal, (qualified_at + 1, qualified_at + 1))
            self.assertEqual(build([self.rom.path], reports=reports, output=output)['consoles']['sms']['games'], 0)


if __name__=='__main__':unittest.main()
