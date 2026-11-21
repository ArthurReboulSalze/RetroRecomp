"""The glue every machine on the banked Z80 chain shares: native/z80_chain_glue.inc (its header is the includer's contract) and
retrorecomp/z80_chain_build.py. The MSX family is the first includer and builder; the checks keep the contract and the text the
rendered loop needs from drifting apart."""
import re
import tempfile
import unittest
from pathlib import Path

from retrorecomp import stamp_inputs, z80_chain, z80_chain_build
from retrorecomp.systems import find_profile

ROOT = Path(__file__).resolve().parents[1]
GLUE = (ROOT / 'native/z80_chain_glue.inc').read_bytes().decode('utf-8')
MSX_GLUE = (ROOT / 'native/msx_machine/msx_glue.inc').read_bytes().decode('utf-8')
RUNTIME = (ROOT / 'native/banked_runtime.inc').read_bytes().decode('utf-8')
STATE = (ROOT / 'native/banked_reference_state.inc').read_bytes().decode('utf-8')
HEADER = GLUE[:GLUE.index('#include <stdio.h>')]


class GlueContractTests(unittest.TestCase):
    def test_the_header_names_everything_the_includer_owes(self):
        for name in ('machine_to', 'sms_read8', 'sms_write8', 'sms_io_in', 'sms_io_out', 'vdp_irq_asserted', 'smsrecomp_region_map',
                     'smsrecomp_region_generation', 'smsrecomp_state_service', 'banked_nmi_edge', 'machine_instruction_cost',
                     'game_banked.h', 'runtime_reference.h', 'SMSRECOMP_BANKED_AOT', '_banked_loop.inc'):
            self.assertIn(name, HEADER, name)
        self.assertIn('RESERVED, not implemented', HEADER)       # the cost hook is named, not written
        # A 16-bit machine's pair (Z80Machine.port_bits): the header names it and the define that selects it.
        for name in ('sms_io_in16', 'sms_io_out16', 'SMSRECOMP_PORT16', 'exactly one pair'):
            self.assertIn(name, HEADER, name)

    def test_the_msx_glue_supplies_what_the_header_asks_for(self):
        self.assertIn('static void machine_to(uint64_t cycle);', MSX_GLUE)          # the prototype, before the include
        self.assertLess(MSX_GLUE.index('static void machine_to(uint64_t cycle);'), MSX_GLUE.index('#include "z80_chain_glue.inc"'))
        after = MSX_GLUE[MSX_GLUE.index('#include "z80_chain_glue.inc"'):]
        for definition in ('static void machine_to(uint64_t cycle)\n{', 'uint8_t sms_read8(uint16_t address)', 'void sms_write8(uint16_t address',
                           'uint8_t sms_io_in(uint8_t port)', 'void sms_io_out(uint8_t port', 'static int vdp_irq_asserted(void)',
                           'smsrecomp_region_map(void)', 'smsrecomp_region_generation', 'static void smsrecomp_state_service(void)',
                           '#include "msx_banked_loop.inc"'):
            self.assertIn(definition, after, definition)

    def test_the_shared_glue_does_not_define_what_is_the_machines(self):
        for name in ('MsxMachine', 'msx_', 'machine.', 'region_map[', 'slot0', 'cart['):
            self.assertNotIn(name, GLUE[GLUE.index('#include <stdio.h>'):], name)

    def test_the_names_the_rendered_loop_uses_are_defined_by_the_glue_or_promised_by_it(self):
        for machine, state in ((find_profile('msx').z80_machine, STATE),
                               (z80_chain.Z80Machine('nmi-machine', find_profile('msx').z80_machine.regions, irq_sample='instruction_end',
                                                     step_begin=True, reference_state=True, nmi=True), STATE)):
            loop = z80_chain.runtime_source(machine, RUNTIME, state)
            owed = set(re.findall(r'\b(g_sync_deadline|g_frame_ic|g_next_line_cyc|smsrecomp_total_cycles|smsrecomp_measured_guest_cycles|'
                                  r'banked_last_interpreted|smsrecomp_interp_depth|smsrecomp_stop_pending|g_hz_init|g_hybrid_calls|'
                                  r'g_hybrid_cyc|g_irq_taken|smsrecomp_feedback_at|smsrecomp_learning_enabled|smsrecomp_observe_code|'
                                  r'hyb_read|hyb_write|hyb_in|hyb_out|advance_vdp)\b', loop))
            self.assertTrue(owed)
            for name in owed:
                self.assertRegex(GLUE, r'\b' + name + r'\b', name)
            for name in ('vdp_irq_asserted', 'smsrecomp_state_service', 'smsrecomp_region_map') + (('banked_nmi_edge',) if machine.nmi else ()):
                if name in loop:
                    self.assertIn(name, HEADER, name)

    def test_the_msx_build_stages_the_shared_glue_beside_the_machine_glue_that_includes_it(self):
        # A conversion builds in a flat work folder: the included file must be copied there (a build, not the tests, caught it once).
        from retrorecomp import msx_build
        self.assertIn('z80_chain_glue.inc', msx_build.CHAIN_FILES)
        self.assertIn('#include "z80_chain_glue.inc"', MSX_GLUE)
        with tempfile.TemporaryDirectory() as work:
            msx_build.stage_sources(Path(work))
            self.assertTrue((Path(work) / 'z80_chain_glue.inc').is_file())
            self.assertTrue((Path(work) / 'msx_glue.inc').is_file())

    def test_the_msx_family_shares_the_glue_group(self):
        self.assertEqual(stamp_inputs.sharing('z80_chain_glue'), ('msx', 'msx2', 'msx2plus', 'zxs', 'sg1000', 'coleco', 'cpc'))
        group = stamp_inputs.INPUTS[stamp_inputs.sharing('z80_chain_glue')]
        self.assertIn('native/z80_chain_glue.inc', group)
        self.assertIn('retrorecomp.z80_chain_build', group)


class ChainBuildTests(unittest.TestCase):
    def test_a_file_is_written_only_when_it_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a' / 'b.txt'
            z80_chain_build.write_if_changed(path, b'one')
            stamp = path.stat().st_mtime_ns
            z80_chain_build.write_if_changed(path, b'one')
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            z80_chain_build.write_if_changed(path, b'two')
            self.assertEqual(path.read_bytes(), b'two')

    def test_files_of_several_folders_are_staged_flat_and_nested_names_keep_their_folder(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two, tempfile.TemporaryDirectory() as work:
            (Path(one) / 'a.c').write_bytes(b'a')
            (Path(two) / 'sub').mkdir()
            (Path(two) / 'sub' / 'b.h').write_bytes(b'b')
            z80_chain_build.stage_files(Path(work), ((Path(one), ('a.c',)), (Path(two), ('sub/b.h',))))
            self.assertEqual((Path(work) / 'a.c').read_bytes(), b'a')
            self.assertEqual((Path(work) / 'sub' / 'b.h').read_bytes(), b'b')

    def test_the_reference_copy_exports_its_acceptance_once_and_refuses_a_copy_that_lost_the_m1_take_back(self):
        from retrorecomp.cpu import prepare_reference
        machine = find_profile('msx').z80_machine
        engine = ROOT / '.deps/smsggrecomp'
        with tempfile.TemporaryDirectory() as work:
            prepare_reference(Path(work), engine, m1_counter=machine.counts_m1)
            path = Path(work) / 'runtime_reference.c'
            z80_chain_build.instrument_reference(path, 'x_accept', machine)
            z80_chain_build.instrument_reference(path, 'x_accept', machine)
            text = path.read_text(encoding='utf-8')
            self.assertEqual(text.count('void x_accept(z80* const z) { process_interrupts(z); }'), 1)
            broken = Path(work) / 'broken.c'
            broken.write_text(text.replace(' --z80_m1_fetches;', ''), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                z80_chain_build.instrument_reference(broken, 'y_accept', machine)


if __name__ == '__main__':
    unittest.main()
