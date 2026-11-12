"""The banked Z80 chain reads its machine from data (retrorecomp/z80_chain.py); the Sega mapper's text stays what it was."""
import unittest
from pathlib import Path

from retrorecomp import stamp_inputs, z80_chain
from retrorecomp.systems import find_profile
from retrorecomp.z80_chain import SEGA_MAPPER, Z80Machine, Z80RegionMap, Z80Regions

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / 'native/banked_runtime.inc').read_bytes().decode('utf-8')
EMITTER = (ROOT / 'native/banked_emitter.inc').read_bytes().decode('utf-8')
STATE = (ROOT / 'native/banked_reference_state.inc').read_bytes().decode('utf-8')
ENGINE = ROOT / '.deps/smsggrecomp'
# Not real machines. Six 8 KiB slots keyed by registers, without a fixed start, one wait state per M1.
OTHER = Z80Machine('other', Z80Regions(slot_bits=13, slots=6, fixed_bytes=0, ram_from=0xC000, bank_values=256, scope='other'), m1_wait=1)
# Eight 8 KiB regions keyed by a map over two sources, one wait state per M1, /INT read at the end of the instruction.
MAPPED = Z80Machine('mapped', Z80RegionMap(region_bits=13, sources=('rom', 'firmware'), bank_values=256, scope='mapped'),
                    m1_wait=1, irq_sample='instruction_end')
# The same without the Sega runner around the loop: a call at the start of every step and the chain's own state copies.
STANDALONE = Z80Machine('standalone', MAPPED.regions, m1_wait=1, irq_sample='instruction_end', step_begin=True, reference_state=True)


def statements(function: str, text: str) -> set[str]:
    """The statements of one C function of `text`, without blanks or comments."""
    import re
    body = re.search(r'static (?:inline )?[\w ]+\b' + function + r'\([^)]*\)\s*\{(.*?)\n\}', text, re.S).group(1)
    return {part for part in re.sub(r'\s+', '', re.sub(r'/\*.*?\*/', '', body, flags=re.S)).split(';') if part}


class Z80ChainTests(unittest.TestCase):
    def test_the_step_loop_of_the_sega_mapper_is_the_file_itself(self):
        self.assertEqual(z80_chain.runtime_source(SEGA_MAPPER, RUNTIME), RUNTIME)
        self.assertEqual(z80_chain.banked_runtime(SEGA_MAPPER, ROOT), RUNTIME)

    def test_the_master_system_and_the_game_gear_name_the_sega_mapper(self):
        for system in ('sms', 'gg'):
            self.assertIs(find_profile(system).z80_machine, SEGA_MAPPER)
        self.assertEqual(stamp_inputs.sharing('z80_main'), ('sms', 'gg', 'msx', 'msx2'))
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
        # The count is taken back with R where the CPU calls inc_r twice for one M1 cycle (DD/FD before a plain opcode, the
        # interrupt acknowledge).
        self.assertEqual(on.replace('unsigned long z80_m1_fetches;\n', '').replace('\n  ++z80_m1_fetches;', '')
                         .replace(' --z80_m1_fetches;', ''), off)
        self.assertEqual(on.count('z80_m1_fetches'), 4)
        self.assertEqual(on.count('z->r = (z->r & 0x80) | ((z->r - 1) & 0x7f); --z80_m1_fetches;'), 2)

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

    def test_a_mapped_source_never_goes_through_the_sega_cartridge_parser(self):
        # The entry point of the pinned generator, reduced to the two places the front end of a mapped machine edits.
        main = ('int main(void){\n    bool banked_step = false;\n    printf("[SmsRecomp] SMS/GG Z80 static recompiler\\n");\n'
                '    SmsRom rom;\n    if (!rom_parse(rompath, &rom)) return 1;\n    if (banked_step) {}\n}\n')
        self.assertEqual(z80_chain.generator_main(SEGA_MAPPER, main), main)
        self.assertEqual(z80_chain.generator_main(OTHER, main), main)
        mapped = z80_chain.generator_main(MAPPED, main)
        self.assertNotIn('SMS/GG', mapped)
        self.assertLess(mapped.index('return cg_emit_banked_mapped(rompath, &cfg, gendir);'), mapped.index('rom_parse(rompath, &rom)'))
        with self.assertRaises(ValueError):
            z80_chain.generator_main(MAPPED, main.replace('rom_parse(rompath, &rom)', 'rom_parse(rompath, &rom, 0)'))
        # The emitter reads the sources itself: whole, padded with FFh to whole regions, no size test of another machine.
        start = EMITTER.index('static void banked_read_source(')
        front = EMITTER[start:EMITTER.index('    size_t positions = 0, pairs = 0', start)]
        self.assertIn('memset(source->data + size, 0xFF, source->size - (size_t)size);', front)
        self.assertIn('banked_read_source(&sources[0], 0, rom_path, slot_size);', front)
        for sega in ('512', 'TMR', 'rom->', 'rom_parse', 'copier'):
            self.assertNotIn(sega, front)
        self.assertEqual(EMITTER.count('int cg_emit_banked_mapped(const char *rom_path, const GameConfig *cfg, const char *dir) {'), 1)
        self.assertIn('[banked] a machine keyed by a region map is translated by cg_emit_banked_mapped', EMITTER)
        # The same padding for the machine's own tools; a mapper with banks of two regions pads to its bank.
        regions = MAPPED.regions
        self.assertEqual(regions.image(bytes(0x3000)), bytes(0x3000) + b'\xFF' * 0x1000)
        self.assertEqual(regions.image(bytes(0x4200)), bytes(0x4200) + b'\xFF' * 0x1E00)       # 16 KiB + 512: nothing stripped
        self.assertEqual(len(regions.image(bytes(0x6000), 2)), 0x8000)
        self.assertEqual(regions.image(bytes(0x2000)), bytes(0x2000))
        with self.assertRaises(ValueError):
            regions.image(b'')

    def test_a_machine_may_be_called_at_the_start_of_every_step_and_the_sega_loop_has_no_such_call(self):
        self.assertNotIn('smsrecomp_step_begin', RUNTIME)
        self.assertFalse(SEGA_MAPPER.step_begin)
        self.assertNotIn('smsrecomp_step_begin', z80_chain.runtime_source(MAPPED, RUNTIME))
        text = z80_chain.runtime_source(STANDALONE, RUNTIME, STATE)
        self.assertEqual(text.count('        SMS_PC(g_z80.pc);\n        smsrecomp_step_begin(prefix_pending);\n'), 1)
        self.assertEqual(text.count('smsrecomp_step_begin'), 1)
        # Before the step is chosen (halted or not), so a HALT cycle is a step too.
        self.assertLess(text.index('smsrecomp_step_begin(prefix_pending);'), text.index('if (g_z80.halted) {'))

    def test_the_hardware_advances_inside_a_prefix_chain_only_where_the_interrupt_is_latched_at_the_start(self):
        advance = '                prefix_pending = 1;\n                banked_advance_vdp(g_z80.cyc); g_sync_deadline = g_next_line_cyc;\n'
        self.assertTrue(SEGA_MAPPER.advances_in_prefixes and OTHER.advances_in_prefixes)
        self.assertFalse(MAPPED.advances_in_prefixes)
        self.assertEqual(RUNTIME.count(advance), 1)
        self.assertEqual(z80_chain.runtime_source(OTHER, RUNTIME).count(advance), 1)
        text = z80_chain.runtime_source(MAPPED, RUNTIME)
        self.assertNotIn(advance, text)
        self.assertEqual(text.count('                prefix_pending = 1;\n                continue;\n'), 1)
        # Once per completed instruction: the catch-up before /INT is read, and the one every machine has after acceptance
        # (the third occurrence is the helper's own name in its definition).
        loop = text[text.index('static void smsrecomp_banked_run(void)'):]
        self.assertEqual(loop.count('banked_advance_vdp(g_z80.cyc);'), 2)

    def test_the_state_copies_come_with_the_loop_for_a_machine_without_the_sega_runner(self):
        self.assertFalse(SEGA_MAPPER.reference_state)
        for name in ('static void state_to_hz(void)', 'static void state_from_hz(void)'):
            self.assertNotIn(name, RUNTIME)                                   # the Sega glue has the pinned runner's
            self.assertEqual(STATE.count(name), 1)
        text = z80_chain.runtime_source(STANDALONE, RUNTIME, STATE)
        self.assertEqual(text, z80_chain.banked_runtime(STANDALONE, ROOT))
        self.assertEqual(text.count(STATE), 1)
        self.assertLess(text.index('#ifdef SMSRECOMP_BANKED_AOT'), text.index(STATE))
        self.assertLess(text.index(STATE), text.index('static void smsrecomp_banked_fallback('))
        with self.assertRaises(ValueError):
            z80_chain.runtime_source(STANDALONE, RUNTIME)                      # asked for, not given
        self.assertEqual(z80_chain.runtime_source(MAPPED, RUNTIME, STATE), z80_chain.runtime_source(MAPPED, RUNTIME))
        self.assertIn('native/banked_reference_state.inc', stamp_inputs.NOT_INPUTS)

    @unittest.skipUnless((ENGINE / 'runner/glue.c').is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_the_state_copies_are_the_pinned_runners_statement_by_statement(self):
        glue = (ENGINE / 'runner/glue.c').read_text(encoding='utf-8')
        rename = lambda found: {part.replace('banked_pack_f', 'pack_f').replace('banked_unpack_f', 'unpack_f') for part in found}
        # The converter adds the Q and P latches to the runner's pair (core.py) and, for its own I/O timing, a cycle base.
        self.assertEqual(rename(statements('state_to_hz', STATE)),
                         statements('state_to_hz', glue) | {'g_hz.q=g_z80.q', 'g_hz.p=g_z80.p'})
        self.assertEqual(rename(statements('state_from_hz', STATE)),
                         statements('state_from_hz', glue) | {'g_z80.q=g_hz.q', 'g_z80.p=g_hz.p'})
        for ours, theirs in (('banked_pack_f', 'pack_f'), ('banked_unpack_f', 'unpack_f')):
            self.assertEqual(statements(ours, STATE), statements(theirs, glue))
        from retrorecomp import core
        source = Path(core.__file__).read_text(encoding='utf-8')
        self.assertEqual(source.count('    g_hz.q = g_z80.q; g_hz.p = g_z80.p;'), 1)
        self.assertEqual(source.count('    g_z80.q = g_hz.q; g_z80.p = g_hz.p;'), 1)

    def test_a_region_may_guard_one_window_and_keep_the_rest_keyed(self):
        self.assertEqual(EMITTER.count('typedef struct { uint8_t source, bank, ram; uint16_t guard_from, guard_to; } BankedRegion;'), 1)
        # An instruction is at most four bytes: one that starts up to three bytes before the window reads it.
        self.assertEqual(EMITTER.count('if (region->ram || off >= 0x%zX || (off < region->guard_to && off + 3 >= region->guard_from)) '
                                       'return game_banked_guarded_step();'), 1)
        guarded = lambda off, start, end: off < end and off + 3 >= start
        self.assertFalse(any(guarded(off, 0, 0) for off in range(0x2000)))                      # no window: both 0
        hit = [off for off in range(0x2000) if guarded(off, 0x1800, 0x2000)]                    # 9800h-9FFFh of 8000h-9FFFh
        self.assertEqual((hit[0], hit[-1], len(hit)), (0x17FD, 0x1FFF, 0x803))

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
