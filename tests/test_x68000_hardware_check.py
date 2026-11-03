"""Fail-closed hardware evidence checks of the X68000 (tools/x68000_hardware_check.py): authored records only."""
import copy
import unittest
from tools.x68000_hardware_check import check_ledger,check_diagnostics,EXPECTED

class HardwareCheckTests(unittest.TestCase):
    """The fail-closed validators of tools/x68000_hardware_check.py (clock ledger, authored device proofs)."""

    def ledger(self):
        ticks=180312
        row={'guest_frames':1,'cpu_cycles':ticks,'peripheral_ticks':ticks,'lines':567,
             'audio_pairs':ticks*44100//10000000,'samples':ticks*44100//10000000,
             'audio_errors':0,'frame_budget':180310}
        report={'sample_rate':44100.,'audio_samples':row['samples'],'hardware':{
            'frames':1,'cpu_cycles':ticks,'peripheral_ticks':ticks,'lines':567,
            'audio_pairs':row['samples'],'audio_errors':0}}
        return row,report

    def test_clock_fraction_is_retained_not_rounded_per_frame(self):
        row,report=self.ledger()
        self.assertTrue(check_ledger([row],report)['no_audio_invention_or_discard'])
        for extra in (-1,1):
            bad=copy.deepcopy(row);bad['samples']+=extra;bad['audio_pairs']+=extra
            with self.assertRaisesRegex(ValueError,'PCM amount'):check_ledger([bad],report)

    def test_cpu_cycle_debt_cannot_accumulate(self):
        row,report=self.ledger();row['frame_budget']=162707
        with self.assertRaisesRegex(ValueError,'debt'):check_ledger([row],report)

    def test_counters_and_reports_cannot_hide_dropped_audio(self):
        row,report=self.ledger();report['audio_samples']-=1
        with self.assertRaises(ValueError):check_ledger([row],report)
        row['audio_errors']=1
        with self.assertRaises(ValueError):check_ledger([row],report)

    def test_device_proof_rejects_missing_failed_or_unrestored_checks(self):
        for suite,(count,mask) in EXPECTED.items():
            result={'checks':[{'name':str(n),'passed':True} for n in range(count)],
                    'mask':mask,'expected_mask':mask,'state_restored':True}
            self.assertTrue(check_diagnostics(result,suite)['passed'])
            for field,value in (('mask',0),('checks',result['checks'][:-1])):
                bad=copy.deepcopy(result);bad[field]=value
                with self.assertRaises(ValueError):check_diagnostics(bad,suite)
            bad=copy.deepcopy(result);bad['checks'][0]['passed']=False
            with self.assertRaises(ValueError):check_diagnostics(bad,suite)
            if suite!='audio':
                result['state_restored']=False
                with self.assertRaises(ValueError):check_diagnostics(result,suite)

if __name__=='__main__':unittest.main()
