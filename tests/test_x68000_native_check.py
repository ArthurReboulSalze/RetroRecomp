import unittest
from copy import deepcopy
from tools.x68000_native_check import validate_pair


class PairGateTests(unittest.TestCase):
    def pair(self):
        common={'frames':10,'core_error':False,'ram_mib':2,'cpu_mhz':10,'cpu':[0]*18,
                'ram_fnv64':'1'*16,'pcm_fnv64':'2'*16,'final_video_fnv64':'3'*16,
                'native_ram':0,'native_ipl':0,'reference_ram':12,'reference_ipl':8}
        reference={**common,'mode':'interpreted-reference','native_cpu':False}
        native={**common,'mode':'guarded-native-prototype','native_cpu':True,
                'native_ram':12,'native_ipl':8,'reference_ram':0,'reference_ipl':0}
        return reference,native

    def test_independent_counts_and_all_report_fields_agree(self):
        a,b=self.pair();self.assertEqual(validate_pair(a,b,10)['interpreted_instructions'],0)

    def test_no_fallback_or_native_reference_is_waived(self):
        for side,field in ((0,'native_ram'),(1,'reference_ram'),(1,'reference_ipl')):
            a,b=self.pair();(a,b)[side][field]=1
            with self.assertRaises(ValueError):validate_pair(a,b,10)

    def test_changed_pcm_cpu_or_geometry_is_not_masked(self):
        for field,value in (('pcm_fnv64','4'*16),('cpu',[1]*18),('width',512),('cpu_mhz',12)):
            a,b=self.pair();b[field]=value
            with self.assertRaises(ValueError):validate_pair(a,b,10)

    def test_incomplete_execution_or_missing_counter_fails(self):
        for field,value in (('frames',9),('native_cpu',False),('native_ipl',None),('core_error',True)):
            a,b=self.pair();b[field]=value
            with self.assertRaises(ValueError):validate_pair(a,b,10)

if __name__=='__main__':unittest.main()
