import json
from pathlib import Path
import tempfile
import unittest
from tools.x68000_native import observations,private_path,source_receipts


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
        for value in ({'schema':1,'truncated':True,'variants':[]},{'schema':2,'truncated':False}):
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

if __name__=='__main__':unittest.main()
