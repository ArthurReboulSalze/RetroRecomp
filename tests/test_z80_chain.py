"""The banked Z80 chain reads its machine from data (retrorecomp/z80_chain.py); the Sega mapper's text stays what it was."""
import unittest
from pathlib import Path

from retrorecomp import stamp_inputs, z80_chain
from retrorecomp.systems import find_profile
from retrorecomp.z80_chain import SEGA_MAPPER, Z80Machine, Z80RegionMap, Z80Regions

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / 'native/banked_runtime.inc').read_bytes().decode('utf-8')
EMITTER = (ROOT / 'native/banked_emitter.inc').read_bytes().decode('utf-8')
# Not real machines. Six 8 KiB slots keyed by registers, without a fixed start, one wait state per M1.
OTHER = Z80Machine('other', Z80Regions(slot_bits=13, slots=6, fixed_bytes=0, ram_from=0xC000, bank_values=256, scope='other'), m1_wait=1)
# Eight 8 KiB regions keyed by a map over two sources, one wait state per M1, /INT read at the end of the instruction.
MAPPED = Z80Machine('mapped', Z80RegionMap(region_bits=13, sources=('rom', 'firmware'), bank_values=256, scope='mapped'),
                    m1_wait=1, irq_sample='instruction_end')


class Z80ChainTests(unittest.TestCase):
    def test_the_step_loop_of_the_sega_mapper_is_the_file_itself(self):
        self.assertEqual(z80_chain.runtime_source(SEGA_MAPPER, RUNTIME), RUNTIME)
        self.assertEqual(z80_chain.banked_runtime(SEGA_MAPPER, ROOT), RUNTIME)

    def test_the_master_system_and_the_game_gear_name_the_sega_mapper(self):
        for system in ('sms', 'gg'):
            self.assertIs(find_profile(system).z80_machine, SEGA_MAPPER)
        self.assertEqual(stamp_inputs.sharing('z80_main'), ('sms', 'gg'))
        regions = SEGA_MAPPER.regions
        self.assertEqual((regions.slot_bits, regions.slots, regions.fixed_bytes, regions.ram_from, regions.bank_values,
                          SEGA_MAPPER.m1_wait, SEGA_MAPPER.irq_sample, SEGA_MAPPER.mapped),
                         (14, 3, 0x400, 0xC000, 256, 0, 'step_start', False))

    def test_the_emitter_gets_the_machine_as_one_initialiser_and_names_no_mapper_itself(self):
        text = z80_chain.emitter_source(SEGA_MAPPER, EMITTER)
        self.assertTrue(text.endswith(EMITTER))
        self.assertEqual(text.count('#define BANKED_MACHINE { .mapped = 0, .slot_bits = 14, .slots = 3, .fixed_bytes = 0x400, '
                                    '.ram_from = 0xC000, .sources = 1, .bank_values = 256, .m1_wait = 0, '
                                    '.scope = "master-system-sega-mapper" }\n'), 1)
        self.assertEqual(EMITTER.count('static const BankedMachine banked_machine = BANKED_MACHINE;'), 1)
        for constant in ('0xC000', '0x4000', '0x3FFD', '0x3FD', '0x400', 'uint8_t b0', 'sega', 'Sega'):
            self.assertNotIn(constant, EMITTER)
        self.assertIn('.m1_wait = 1', z80_chain.emitter_source(OTHER, EMITTER))
        self.assertIn('{ .mapped = 1, .slot_bits = 13, .slots = 8, .fixed_bytes = 0x0, .ram_from = 0x10000, .sources = 2, '
                      '.bank_values = 256, .m1_wait = 1, .scope = "mapped" }', z80_chain.emitter_source(MAPPED, EMITTER))

    def test_another_machine_renders_its_own_bank_key_and_halt_cost(self):
        text = z80_chain.runtime_source(OTHER, RUNTIME)
        key = ', '.join(f'(uint8_t)g_bank[{slot}]' for slot in range(6))
        for line in ('static uint8_t banked_seen[6][256];\n', '    uint64_t seen_banks = UINT64_MAX;\n',
                     f'            int step = game_banked_step({key});\n',
                     '            g_z80.cyc += 5; banked_halt_steps++;\n',
                     '(uint64_t)(uint8_t)g_bank[5] << 40;\n', 'banks_seen=%u/%u/%u/%u/%u/%u\\n",\n',
                     # /INT stays where the Sega runner samples it
                     '        if (!prefix_pending) pending_irq = vdp_irq_asserted();\n'):
            self.assertEqual(text.count(line), 1, line)
        self.assertNotIn('g_bank[2]);', text)
        # The counted fallback adds the wait states from the reference CPU's count of M1 cycles.
        self.assertEqual(text.count('    extern unsigned long z80_m1_fetches;\n    unsigned long m1_before = z80_m1_fetches;\n'
                                    '    z80_step(&g_hz);\n    g_hz.cyc += 1 * (z80_m1_fetches - m1_before);'), 1)
        # Everything else is the shared text: the same lines but for one the wider bank word adds and three of the fallback.
        self.assertEqual(len(text.splitlines()), len(RUNTIME.splitlines()) + 4)

    def test_the_generator_of_another_machine_lives_in_its_own_folders_and_only_a_waiting_machine_counts_m1(self):
        self.assertEqual((SEGA_MAPPER.generator_source, SEGA_MAPPER.generator_build, SEGA_MAPPER.counts_m1),
                         ('recompiler-src', 'recompiler-build', False))
        tagged = Z80Machine('other', OTHER.regions, m1_wait=1, generator_tag='-other')
        self.assertEqual((tagged.generator_source, tagged.generator_build, tagged.counts_m1),
                         ('recompiler-src-other', 'recompiler-build-other', True))
        self.assertNotIn('z80_m1_fetches', RUNTIME)
        with self.assertRaises(ValueError):
            Z80Machine('other', OTHER.regions, generator_tag='../elsewhere')

    @unittest.skipUnless((ROOT / '.deps/smsggrecomp/runner/external/superzazu/z80.c').is_file(),
                         'pinned smsggrecomp sources are not downloaded')
    def test_the_reference_cpu_counts_m1_cycles_only_when_asked(self):
        import tempfile
        from retrorecomp.cpu import prepare_reference
        with tempfile.TemporaryDirectory() as plain, tempfile.TemporaryDirectory() as counted:
            prepare_reference(Path(plain), ROOT / '.deps/smsggrecomp')
            prepare_reference(Path(counted), ROOT / '.deps/smsggrecomp', m1_counter=True)
            off = (Path(plain) / 'runtime_reference.c').read_text(encoding='utf-8')
            on = (Path(counted) / 'runtime_reference.c').read_text(encoding='utf-8')
            self.assertEqual((Path(plain) / 'runtime_reference.h').read_bytes(), (Path(counted) / 'runtime_reference.h').read_bytes())
        self.assertNotIn('z80_m1_fetches', off)
        # The count is the only difference: no cycle addition of the CPU is edited.
        self.assertEqual(on.replace('unsigned long z80_m1_fetches;\n', '').replace('\n  ++z80_m1_fetches;', ''), off)
        self.assertEqual(on.count('z80_m1_fetches'), 2)

    def test_a_mapped_machine_reads_its_region_map_and_samples_the_interrupt_where_it_says(self):
        text = z80_chain.runtime_source(MAPPED, RUNTIME)
        for line in ('static uint8_t banked_seen[8][256];\n', '    uint32_t seen_generation = UINT32_MAX;\n',
                     '        const BankedRegion *map = smsrecomp_region_map();\n',
                     '        if (smsrecomp_region_generation != seen_generation) {\n',
                     '            int step = game_banked_step(map);\n',
                     '            g_z80.cyc += 5; banked_halt_steps++;\n'):
            self.assertEqual(text.count(line), 1, line)
        self.assertNotIn('g_bank', text)
        self.assertNotIn('if (!prefix_pending) pending_irq', text)
        end = text.index('        prefix_pending = 0; g_frame_ic++;\n')
        self.assertTrue(text[end:].startswith(
            '        prefix_pending = 0; g_frame_ic++;\n        banked_advance_vdp(g_z80.cyc);   /* the hardware catches up, '
            'then /INT is read at the end of the instruction */\n        pending_irq = vdp_irq_asserted();\n'
            '        banked_after_step(pending_irq);\n'))
        # The acceptance of an interrupt keeps the Z80's own count on every machine.
        self.assertEqual(text.count('g_z80.cyc += g_z80.im == 2 ? 19 : 13;'), 1)

    def test_a_line_of_the_step_loop_that_moved_is_refused(self):
        with self.assertRaises(ValueError):
            z80_chain.runtime_source(SEGA_MAPPER, RUNTIME.replace('g_z80.cyc += 4; banked_halt_steps++;', 'g_z80.cyc += 4;'))

    def test_impossible_machines_are_refused(self):
        good = dict(slot_bits=14, slots=3, fixed_bytes=0x400, ram_from=0xC000, bank_values=256, scope='x')
        for change in (dict(slots=5), dict(slots=0), dict(ram_from=0xC001), dict(ram_from=0x8000), dict(fixed_bytes=2),
                       dict(fixed_bytes=0x4000), dict(bank_values=257), dict(slot_bits=16)):
            with self.assertRaises(ValueError, msg=change):
                Z80Regions(**{**good, **change})
        for change in (dict(region_bits=9), dict(sources=()), dict(sources=('rom', 'rom')), dict(bank_values=0)):
            with self.assertRaises(ValueError, msg=change):
                Z80RegionMap(**{**dict(region_bits=13, sources=('rom',), bank_values=256, scope='x'), **change})
        for change in (dict(m1_wait=4), dict(irq_sample='never')):
            with self.assertRaises(ValueError, msg=change):
                Z80Machine('x', Z80Regions(**good), **change)


if __name__ == '__main__':
    unittest.main()
