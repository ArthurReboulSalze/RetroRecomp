"""Coverage is distinct from architecture/hardware/output agreement."""
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
from smsrecomp.neogeo_validation import FIELDS,compare
from smsrecomp.megadrive_z80 import opcode_key

class NeoGeoNativeGates(unittest.TestCase):
    def test_shared_68000_forms_keep_distinct_offline_immediates(self):
        from smsrecomp.neogeo_codegen import structural_key,structural_body,canonical_instruction
        ins=dict(addr=0x420,mnemonic=1,size=4,words=[0x203c,0x1122,0x3344,0,0,0,0,0],
                 word_count=3,byte_length=6,src_ea=60,dst_ea=0,reg=0,imm32=0x11223344,
                 target_addr=0,has_target=0,dst_is_ea=1,predec_mem_form=0,mem_shift=0)
        other=dict(ins,addr=0x800,imm32=0x55667788,words=[0x203c,0x5566,0x7788,0,0,0,0,0])
        self.assertEqual(structural_key(ins),structural_key(other))
        self.assertNotEqual(canonical_instruction(ins,'MN_MOVE'),canonical_instruction(other,'MN_MOVE'))
        body=structural_body(ins,'MN_MOVE','g_cpu.D[ins->reg]=ins->imm32; return M68KI_OK;')
        self.assertIn('g_cpu.D[0]=ins->imm32',body)
        self.assertNotIn('m68k_decode',body)
        self.assertNotEqual(structural_key(ins),structural_key(dict(ins,dst_ea=1)))

    def test_shared_relative_targets_rebase_and_absolute_targets_do_not(self):
        from smsrecomp.neogeo_codegen import canonical_instruction
        for name in ('MN_BRA','MN_BSR','MN_Bcc','MN_DBcc'):
            a=canonical_instruction(dict(addr=0x1000,target_addr=0xff0),name)
            b=canonical_instruction(dict(addr=0x2000,target_addr=0x1ff0),name)
            self.assertEqual(a,b)
            self.assertEqual((a['target_addr']+0x3000)&0xffffff,0x2ff0)
        self.assertEqual(canonical_instruction(dict(addr=0x1000,target_addr=0x456),'MN_JMP')['target_addr'],0x456)

    def reports(self):
        native={field:0 for field in FIELDS}
        native.update(native_68000=100,interpreted_68000=0,native_z80=40,interpreted_z80=0)
        reference=dict(native,native_68000=0,interpreted_68000=100,native_z80=0,interpreted_z80=40)
        return native,reference

    def test_same_guest_results_can_have_different_execution_engines(self):
        self.assertEqual(compare(*self.reports()),[])

    def test_missing_native_work_cannot_be_reported_as_zero_fallback_success(self):
        native,reference=self.reports();native['native_68000']=0
        with self.assertRaisesRegex(RuntimeError,'68000_instruction_total'):compare(native,reference)

    def test_fallback_preserves_integrity_but_does_not_pass_native_gate(self):
        native,reference=self.reports();native.update(native_z80=39,interpreted_z80=1)
        self.assertEqual(compare(native,reference,require_native=False),[])
        with self.assertRaisesRegex(RuntimeError,'z80_native_coverage'):compare(native,reference)

    def test_no_guest_result_mismatch_can_be_excused_by_native_coverage(self):
        for field in FIELDS:
            with self.subTest(field=field):
                native,reference=self.reports();native[field]=1
                with self.assertRaisesRegex(RuntimeError,field):compare(native,reference)

    def test_physical_mapping_extended_state_and_retired_clocks_are_qualification_gates(self):
        for field in ('reached_physical','extended_cpu_hash','extended_hardware_hash','cpu_slice_clocks'):
            with self.subTest(field=field):
                native,reference=self.reports();native[field]=reference[field]=0;native[field]=1
                with self.assertRaisesRegex(RuntimeError,field):compare(native,reference)

    def test_mutable_z80_immediates_keep_the_same_compiled_operation(self):
        self.assertEqual(opcode_key(bytes.fromhex('c3fdfff3')),opcode_key(bytes.fromhex('c31280f3')))
        self.assertNotEqual(opcode_key(bytes.fromhex('c3fdfff3')),opcode_key(bytes.fromhex('00fdfff3')))

    def test_displaced_z80_cb_guard_retains_selector_but_reads_displacement_live(self):
        self.assertEqual(opcode_key(bytes.fromhex('ddcb0946')),opcode_key(bytes.fromhex('ddcbf946')))
        self.assertNotEqual(opcode_key(bytes.fromhex('ddcb0946')),opcode_key(bytes.fromhex('ddcb094e')))

    def test_rebuilding_prepared_inputs_never_selects_their_own_staging_folder(self):
        from smsrecomp.neogeo_build import staging_project
        with tempfile.TemporaryDirectory() as temp,patch('smsrecomp.neogeo_build.ROOT',Path(temp)):
            identity='a'*64
            for native in (False,True):
                normal=staging_project(identity,native,[])
                bios=normal/'bios.zip'
                alternate=staging_project(identity,native,[bios])
                self.assertFalse(bios.resolve().is_relative_to(alternate.resolve()))
                self.assertEqual(alternate.parent,normal.parent)

    def test_banked_and_ram_pcs_cannot_create_guessed_cart_roots(self):
        from smsrecomp.neogeo_codegen import code_entries
        self.assertEqual(code_entries(1,0,0x200000,{0x400,0x100400,0x280400}),[0x400])
        self.assertEqual(code_entries(1,0,0x200000,{0x280400},{'p':[0x180400]}),[0x180400])

    def test_same_logical_pc_can_supply_multiple_observed_physical_banks(self):
        from smsrecomp.neogeo_codegen import code_entries
        self.assertEqual(code_entries(1,0,0x400000,{0x200400},{'p':[0x100400,0x300400]}),[0x100400,0x300400])
        self.assertEqual(code_entries(2,0xc00000,0x20000,{0xc40200},{'bios':[0x300]}),[0xc00200,0xc00300])

    def test_physical_root_bounds_and_alignment_are_checked(self):
        from smsrecomp.neogeo_codegen import code_entries
        self.assertEqual(code_entries(1,0,0x200000,set(),{'p':[-2,False,'4',5,0x200000,0x200]}),[0x200])

    def test_private_ram_observations_are_bounded_and_preserve_distinct_variants(self):
        from smsrecomp.neogeo_codegen import ram_observations
        records=[{'offset':0xfc00,'words':words} for words in ('7001','7007','7001')]
        records += [{'offset':-2,'words':'7001'},{'offset':False,'words':'7001'},
                    {'offset':1,'words':'7001'},{'offset':0,'words':'zzzz'},
                    {'offset':0xfffe,'words':'203c11223344'},{'offset':0,'words':'00'*18}]
        self.assertEqual(ram_observations(records),[(0xfc00,bytes.fromhex('7001')),(0xfc00,bytes.fromhex('7007'))])

    def test_qualification_routes_preserve_nam_and_use_only_valid_controller_inputs(self):
        from smsrecomp.neogeo_validation import ROUTES,qualification_routes
        self.assertTrue(all(qualification_routes('nam1975')[name]==route for name,route in ROUTES.items()))
        masks=[int(line.split()[1],16) for line in qualification_routes('authored-new-cart')['actions'][1].splitlines()]
        for button in (16,32,64,128):self.assertTrue(any(mask&button for mask in masks))
        for name in ('mslug','neodrift','pbobblen','samsho2','fatfury2','kof98','kof99','mslug3',
                     'mslugx','mslug5','kof2003','svc','kof2000','garou','authored-new-cart'):
            for frames,script in qualification_routes(name).values():
                previous=-1
                for line in script.splitlines():
                    f,p1,p2,coin,start=line.split();f=int(f)
                    self.assertTrue(previous<f<frames);previous=f
                    self.assertTrue(0<=int(p1,16)<256 and 0<=int(p2,16)<256)
                    self.assertTrue(0<=int(coin,16)<4 and 0<=int(start,16)<16)

    def test_qualification_modes_keep_standard_aes_and_enhanced_separate(self):
        from smsrecomp.neogeo_validation import route_arguments
        self.assertEqual(route_arguments('two-player-explore'),[])
        self.assertEqual(route_arguments('aes-play-reference'),['--aes'])
        self.assertEqual(route_arguments('enhanced-two-player-reference'),['--enhanced'])
        self.assertEqual(route_arguments('aes-enhanced-actions-native'),['--aes','--enhanced'])

    def test_extended_routes_cannot_replace_product_gates_or_inject_invalid_inputs(self):
        from smsrecomp.neogeo_validation import extended_routes,qualification_routes
        standard=qualification_routes('authored')
        plans={'authored':{'sustained':(900,'0 10 00 0 0\n800 00 00 1 1\n')}}
        routes=extended_routes('authored',plans)
        self.assertTrue(all(routes[k]==v for k,v in standard.items()))
        self.assertEqual(routes['sustained'][0],900)
        for bad in ({'play':(900,'0 00 00 0 0\n')},{'long':(1,'0 100 0 0 0\n')},
                    {'long':(900,'0 00 00 0 0\n0 00 00 0 0\n')}):
            with self.assertRaises(ValueError):extended_routes('authored',{'authored':bad})

if __name__=='__main__':unittest.main()
