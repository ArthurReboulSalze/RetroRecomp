import json
from pathlib import Path
import tempfile
import unittest
import hashlib
from tools.x68000_native import observations,private_path,source_receipts,fold_ipl,ipl_view,IPL_BYTES


class NativeObservationTests(unittest.TestCase):
    def read(self,value):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'observations.json';p.write_text(json.dumps(value),encoding='utf-8')
            return observations([p])

    def test_different_code_versions_at_same_pc_are_preserved(self):
        variants=[{'pc':0x123456,'words':'303c1234'},{'pc':0x123456,'words':'303c5678'},
                  {'pc':0x123456,'words':'303c1234'}]
        self.assertEqual(self.read({'schema':1,'truncated':False,'variants':variants}),
                         [(0x123456,'303c1234'),(0x123456,'303c5678')])

    def test_truncated_discovery_never_silently_qualifies(self):
        for value in ({'schema':1,'truncated':True,'variants':[]},{'schema':3,'truncated':False},{'schema':1,'truncated':False,'spans':[]}):
            with self.assertRaises(ValueError):self.read(value)

    def test_unmapped_unaligned_and_cross_boundary_samples_are_refused(self):
        for pc,words in ((0xe80000,'4e71'),(1,'4e71'),(0xbffffe,'303c1234'),(0xfffffe,'303c1234'),(False,'4e71')):
            with self.assertRaises(ValueError):self.read({'schema':1,'truncated':False,'variants':[{'pc':pc,'words':words}]})

    def test_text_vram_code_is_guarded_but_io_apertures_are_not_probed(self):
        self.assertEqual(self.read({'schema':1,'truncated':False,'variants':[{'pc':0xe7ffc0,'words':'303c1234'}]}),[(0xe7ffc0,'303c1234')])
        for pc in (0xe7fffe,0xe80000,0xc00000):
            with self.assertRaises(ValueError):self.read({'schema':1,'truncated':False,'variants':[{'pc':pc,'words':'303c1234'}]})

    def test_scsi_rom_code_is_accepted_only_inside_its_fetch_aperture(self):
        for pc,words in ((0xea0036,'303c1234'),(0xea1ffe,'4e71')):
            self.assertEqual(self.read({'schema':1,'truncated':False,'variants':[{'pc':pc,'words':words}]}),[(pc,words)])
        for pc,words in ((0xea1fff,'4e71'),(0xea2000,'4e71'),(0xea1ffe,'303c1234'),(0xe9fffe,'4e71')):
            with self.assertRaises(ValueError):
                self.read({'schema':1,'truncated':False,'variants':[{'pc':pc,'words':words}]})

    def test_malformed_samples_are_not_decoder_inputs(self):
        for words in ('abcd00','ABCD','gggg','0000'*9,''):
            with self.assertRaises(ValueError):self.read({'schema':1,'truncated':False,'variants':[{'pc':0x1000,'words':words}]})

    def test_private_generated_data_cannot_escape_build_folder(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):private_path(Path(d)/'generated')

    def test_identity_is_required_for_build_and_cannot_disagree_with_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'cpu.json'
            path.write_text(json.dumps({'schema':1,'truncated':False,'variants':[]}))
            with self.assertRaises(ValueError):source_receipts([path])
            path.write_text(json.dumps({'source_identity':'a'*64}))
            self.assertEqual(source_receipts([path])[0]['identity'],'a'*64)
            (root/'datas').mkdir();(root/'datas/source-manifest.json').write_text(json.dumps({'sha256':'b'*64}))
            with self.assertRaises(ValueError):source_receipts([path])

    def ipl(self):
        # A synthetic 128 KiB image: words 0..65535 repeated, so every address has distinct bytes.
        return b''.join(((n*7919)&0xffff).to_bytes(2,'big') for n in range(IPL_BYTES//2))

    def variant(self,ipl,pc,count,base=0xfc0000):
        offset=(pc-base)%IPL_BYTES
        return {'pc':pc,'words':bytes(ipl[(offset+n)%IPL_BYTES] for n in range(count*2)).hex(),'hits':3}

    def test_ipl_variants_fold_into_spans_and_expand_back_without_stored_words(self):
        ipl=self.ipl()
        rows=[self.variant(ipl,0xff0100,2),self.variant(ipl,0xff0100,1),self.variant(ipl,0xfc0040,3),
              self.variant(ipl,0xfdfffe,3),                      # runs from the first mapping into the second
              {'pc':0xff0200,'words':'4e71','hits':1},           # not what the IPL holds here: stays a variant
              {'pc':0x1000,'words':'303c1234','hits':1},{'pc':0xea0040,'words':'74ff','hits':1}]
        rest,spans=fold_ipl(rows,ipl)
        self.assertEqual([r['pc'] for r in rest],[0xff0200,0x1000,0xea0040])
        self.assertEqual([(s['address'],s['entries']) for s in spans],
                         [(0xfc0000,[[0x40,3],[0x1fffe,3]]),(0xfe0000,[[0x10100,1],[0x10100,2]])])
        for span in spans:
            self.assertEqual(span['sha256'],hashlib.sha256(ipl).hexdigest())
        record={'schema':2,'truncated':False,'variants':rest,'spans':spans}
        self.assertNotIn(self.variant(ipl,0xff0100,2)['words'],json.dumps(record))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'o.json';p.write_text(json.dumps(record))
            expected=sorted({(r['pc'],r['words']) for r in rows})
            self.assertEqual(observations([p],ipl),expected)
            with self.assertRaises(ValueError):observations([p])                   # spans need their IPL
            with self.assertRaises(ValueError):observations([p],ipl[:-2]+b'ab')    # another IPL

    def test_an_ipl_that_the_machine_replaces_is_never_folded(self):
        ipl=bytearray(self.ipl());ipl[0x10600:0x10604]=bytes([0x00,0xfc,0x00,0x00])
        self.assertIsNone(ipl_view(bytes(ipl)))
        row=self.variant(bytes(ipl),0xff0100,2)
        self.assertEqual(fold_ipl([row],bytes(ipl)),([row],[]))
        self.assertIsNone(ipl_view(bytes(100)))

    def test_malformed_span_entries_are_refused(self):
        ipl=self.ipl();digest=hashlib.sha256(ipl).hexdigest()
        for entry in ([1,2],[0,0],[0,9],[0x20000,1],[0x1fffc,3],[-2,1],['a',1],[0],[0,1,2]):
            span={'source':'ipl','sha256':digest,'address':0xfe0000,'offset':0,'length':IPL_BYTES,'entries':[entry]}
            with self.assertRaises(ValueError):
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'o.json';p.write_text(json.dumps({'schema':2,'truncated':False,'variants':[],'spans':[span]}))
                    observations([p],ipl)
        for span in ({'source':'disk','address':0xfe0000,'offset':0,'length':IPL_BYTES,'entries':[]},
                     {'source':'ipl','sha256':digest,'address':0xfe0000,'offset':2,'length':IPL_BYTES,'entries':[]}):
            with self.assertRaises(ValueError):
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'o.json';p.write_text(json.dumps({'schema':2,'truncated':False,'variants':[],'spans':[span]}))
                    observations([p],ipl)

if __name__=='__main__':unittest.main()
