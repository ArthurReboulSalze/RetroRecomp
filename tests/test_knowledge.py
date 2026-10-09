from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import gzip
import hashlib
import json
import os
import tempfile
import unittest
from smsrecomp import knowledge, gameboy, core
from smsrecomp.library import GameMemory, write_manifest
from smsrecomp import snes_spc, supernintendo


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
        patch('smsrecomp.knowledge.ASSETS',self.root).start()
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
        with patch('smsrecomp.gameboy._verified_trace',return_value=trace):
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

    def test_sega_hints_recheck_live_rom_window_and_preserve_local_priority(self):
        self.rom.system_id='sms'
        address=0x150;fnv=2166136261
        for value in self.rom.data[address:address+256]:fnv=((fnv^value)*16777619)&0xffffffff
        entry=[address,0,1,0,fnv]
        self.install('sms',{'rom_entries':[entry],'pattern_refs':[[10]]},core.ENGINE_REV)
        with patch('smsrecomp.library.library_root',return_value=self.root/'local'):
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
        with patch('smsrecomp.snes_spc.memory_file', return_value=path):
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
                patch('smsrecomp.supernintendo.read_ram_variants', return_value=[
                    {'address': 0x7e0100, 'bytes': self.rom.data[10:14].hex()},
                    {'address': 0x7e0200, 'bytes': 'ffffeeee'}]), \
                patch('smsrecomp.snes_spc.read_masks', return_value=bytes(masks)):
            summary = build([self.rom.path], reports=reports, output=destination)
            self.assertEqual(summary['consoles']['snes']['games'], 0)
            report = {'system': {'id': 'snes'}, 'rom': {'sha256': self.rom.sha256},
                      'native_validation': {'passed': True}, 'compiler': {'revision': engine}}
            path.write_text(json.dumps(report), encoding='utf-8')
            summary = build([self.rom.path], reports=reports, output=destination)
        record = knowledge.load(destination)['consoles']['snes'][self.rom.sha256]
        self.assertEqual(record['ram_refs'], [[0x7e0100, 10, 4]])
        self.assertEqual(record['spc_refs'], [[0x200, 17]])
        self.assertEqual(summary['omitted']['ram_without_rom_source'], 1)
        self.assertNotIn('bytes', record)
        self.assertNotIn(str(self.root), gzip.decompress(destination.read_bytes()).decode())

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
                patch('smsrecomp.gameboy._verified_trace', return_value=trace):
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
                patch('tools.build_compilation_knowledge.GameMemory', return_value=memory):
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
