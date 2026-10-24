"""SNES guard compaction changes representation, never guarded code coverage."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp.knowledge import validate_payload
from retrorecomp import snes_knowledge, knowledge, snes_spc, supernintendo


class SpcKnowledgeTests(unittest.TestCase):
    def payload(self, fields):
        return {'schema':1,'consoles':{'snes':{'1'*64:{
            'engine':'a'*40,'rom_bytes':8192,**fields}}}}

    def test_bitmap_preserves_sparse_dense_and_boundary_references(self):
        refs=[[pc,pc%5] for pc in range(65536) if not 0xf0<=pc<=0xff]
        record={'spc_refs':refs,'ram_refs':[[0x7e0000,0,1]]}
        self.assertTrue(snes_knowledge.compact(record))
        self.assertEqual(set(map(tuple,refs)),set(snes_knowledge.references(record)))
        self.assertEqual(record['ram_refs'],[[0x7e0000,0,1]])
        self.assertFalse(snes_knowledge.compact(record))
        validate_payload(self.payload(record))

    def test_overlapping_legacy_encodings_keep_every_reference(self):
        record={'spc_refs':[[31,1],[32,2],[33,1],[0xffff,3]],
                'spc_ranges':[[0x100,0x1ff,1],[0x140,0x180,2]],
                'spc_bitmaps':[[0x200,0x80000001,4]]}
        expected=set(snes_knowledge.references(record))
        snes_knowledge.compact(record)
        self.assertEqual(expected,set(snes_knowledge.references(record)))
        validate_payload(self.payload(record))

    def test_small_records_keep_the_smaller_legacy_representation(self):
        for record in ({'spc_refs':[[0x200,17]]},{'spc_ranges':[[0x100,0xffff,17]]},{}):
            old=copy.deepcopy(record)
            self.assertFalse(snes_knowledge.compact(record));self.assertEqual(record,old)

    def test_invalid_bitmap_alignment_io_bits_and_expansion_budget_are_rejected(self):
        invalid=([1,1,0],[65536,1,0],[0,0,0],[0,1,8192],
                 [0xe0,0x10000,0],[0,1<<32,0],[0,True,0])
        for entry in invalid:
            with self.subTest(entry=entry),self.assertRaises(ValueError):
                validate_payload(self.payload({'spc_bitmaps':[entry]}))
        validate_payload(self.payload({'spc_bitmaps':[[0xe0,0xffff,0],[65504,0xffffffff,0]]}))
        with self.assertRaisesRegex(ValueError,'budget'):
            validate_payload(self.payload({'spc_bitmaps':[[0x100,0xffffffff,0]]*8193}))

    def test_invalid_deltas_and_mixed_representation_budget_are_rejected(self):
        invalid=([8192,[0]],[0,[]],[0,[0,0]],[0,[-1]],[0,[False]],
                 [0,[0xf0]],[0,[65535,1]],[0,[1,65536]],[0,'private bytes'])
        for entry in invalid:
            with self.subTest(entry=entry),self.assertRaises(ValueError):
                validate_payload(self.payload({'spc_deltas':[entry]}))
        validate_payload(self.payload({'spc_deltas':[[0,[0,0xef,17,65535-256]]]}))
        with self.assertRaisesRegex(ValueError,'budget'):
            validate_payload(self.payload({'spc_deltas':[[0,[0x100]+[1]*255]]*1024,
                                          'spc_refs':[[0x200,0]]}))

    def test_real_consumer_reconstructs_the_identical_guard_map(self):
        data=bytes(range(256))*256
        rom=SimpleNamespace(data=data,sha256=hashlib.sha256(data).hexdigest())
        engine=supernintendo.knowledge_engine(rom)
        record={'engine':engine,'rom_bytes':len(data),
                'spc_refs':[[pc,pc%13] for pc in range(65536) if not 0xf0<=pc<=0xff]}
        payload={'schema':1,'consoles':{'snes':{rom.sha256:record}}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/knowledge.RESOURCE;path.parent.mkdir()
            def save():
                path.write_bytes(gzip.compress(json.dumps(payload).encode(),mtime=0))
                knowledge.load.cache_clear()
            with patch('retrorecomp.knowledge.ASSETS',root), \
                    patch('retrorecomp.snes_spc.memory_file',return_value=root/'absent'), \
                    patch('retrorecomp.feedback.records',return_value=[]), \
                    patch.dict('os.environ',{},clear=True):
                save();before=snes_spc.read_masks(rom)
                self.assertTrue(snes_knowledge.compact(record));save()
                self.assertEqual(before,snes_spc.read_masks(rom))
            knowledge.load.cache_clear()


if __name__ == '__main__':unittest.main()
