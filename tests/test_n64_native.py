"""Nintendo 64 native blocks and the core's adaptation, without a ROM: authored MIPS words, the generator's choices and output."""
import shutil
import tempfile
import unittest
from pathlib import Path

from retrorecomp import n64_core, n64_native
from retrorecomp.core import ConversionError

# Authored VR4300 words (no game byte): ADDIU, SW, LW, JR RA, BEQ, JAL, NOP, ERET, SYSCALL.
ADDIU = 0x24420001      # addiu v0, v0, 1
SW = 0xAFA20010         # sw v0, 16(sp)
LW = 0x8FA20010         # lw v0, 16(sp)
JR_RA = 0x03E00008      # jr ra
BEQ = 0x10400003        # beq v0, zero, +3
JAL = 0x0C000100        # jal 0x400
NOP = 0x00000000
ERET = 0x42000018
SYSCALL = 0x0000000C
BLTZAL = 0x04500002     # bltzal v0, +2


class ClassificationTests(unittest.TestCase):
    def test_flow_and_delay_slots(self):
        for op in (JR_RA, BEQ, JAL, BLTZAL):
            self.assertTrue(n64_native.is_flow(op) and n64_native.has_delay(op), hex(op))
        for op in (ERET, SYSCALL):
            self.assertTrue(n64_native.is_flow(op), hex(op))
            self.assertFalse(n64_native.has_delay(op), hex(op))
        for op in (ADDIU, SW, LW, NOP):
            self.assertFalse(n64_native.is_flow(op), hex(op))
        self.assertTrue(n64_native.is_store(SW))
        self.assertFalse(n64_native.is_store(LW))

    def test_executed_stops_at_the_first_flow_instruction(self):
        self.assertEqual(n64_native.executed((ADDIU, SW, JR_RA, NOP)), 3)
        self.assertEqual(n64_native.executed((ADDIU, LW)), 2)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='n64-native-'))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def write(self, name, lines):
        path = self.folder / name
        path.write_text(''.join(line + '\n' for line in lines), encoding='ascii')
        return path

    def test_reading_sums_counts_and_keeps_variants(self):
        a = self.write('a.txt', [f'80001000 5 4 {ADDIU:08x} {SW:08x} {JR_RA:08x} {NOP:08x}',
                                 f'80001000 2 3 {LW:08x} {BEQ:08x} {NOP:08x}'])
        b = self.write('b.txt', [f'80001000 1 4 {ADDIU:08x} {SW:08x} {JR_RA:08x} {NOP:08x}',
                                 # outside KSEG0 RDRAM: the boot code in the RSP's memory is left to the interpreter
                                 f'a4000040 9 2 {JR_RA:08x} {NOP:08x}'])
        variants = n64_native.read_observations([a, b])
        self.assertEqual(variants[(0x80001000, (ADDIU, SW, JR_RA, NOP))], 6)
        self.assertEqual(variants[(0x80001000, (LW, BEQ, NOP))], 2)
        self.assertEqual(len(variants), 2)

    def test_malformed_lines_are_refused(self):
        for line in ('80001000 1 3 00000000', 'zz 1 1 00000000', '80001001 1 1 00000000', '80001000 0 1 00000000'):
            with self.assertRaises(ConversionError, msg=line):
                n64_native.read_observations([self.write('bad.txt', [line])])

    def test_the_observation_format_round_trips(self):
        variants = {(0x80001000, (ADDIU, JR_RA, NOP)): 3, (0x80002000, (LW, SYSCALL)): 1}
        path = self.folder / 'out.txt'
        n64_native.write_observations(path, variants)
        self.assertEqual(dict(n64_native.read_observations([path])), variants)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='n64-gen-'))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_choice_keeps_the_most_run_and_groups_the_variants(self):
        variants = {(0x80001000, (ADDIU, JR_RA, NOP)): 10, (0x80001000, (LW, JR_RA, NOP)): 30,
                    (0x80003000, (ADDIU, ADDIU, ADDIU, JR_RA, NOP)): 1, (0x80002000, (SW, JR_RA, NOP)): 1}
        chosen = n64_native.choose(variants, coverage=1.0)
        self.assertEqual([(pc, words) for pc, words, _ in chosen],
                         [(0x80001000, (LW, JR_RA, NOP)), (0x80001000, (ADDIU, JR_RA, NOP)), (0x80002000, (SW, JR_RA, NOP)),
                          (0x80003000, (ADDIU, ADDIU, ADDIU, JR_RA, NOP))])
        # 93 % of the weight is in the two variants at 0x80001000 (80 of the 86 instructions run).
        self.assertEqual({pc for pc, _, _ in n64_native.choose(variants, coverage=0.9)}, {0x80001000})

    def test_generated_blocks(self):
        variants = {(0x80001000, (ADDIU, SW, JR_RA, NOP)): 4, (0x80002000, (LW, ADDIU)): 2, (0x80001000, (LW, JR_RA, NOP)): 1}
        result = n64_native.generate(variants, self.folder, coverage=1.0)
        self.assertEqual((result['blocks'], result['addresses'], result['variant_addresses'], result['shards']), (3, 2, 1, 1))
        shard = (self.folder / 'blocks/shard_000.c').read_text(encoding='ascii')
        table = (self.folder / 'blocks/table.c').read_text(encoding='ascii')
        self.assertIn('#include "n64_exec.h"', shard)
        # A store re-checks the block's own words; the jump runs its delay slot and counts as one, as the interpreter does.
        self.assertIn(f' S(0x{SW:x}u, 0x80001008u, 2)', shard)
        self.assertIn(f' execute_op(r4300, 0x{JR_RA:x}u); return 3;', shard)
        # A run with no control flow (the observation's bound) ends after its last word.
        self.assertIn(' return 2;', shard)
        self.assertIn('const uint32_t rr_n64_block_count = 3u;', table)
        rows = [line for line in table.splitlines() if line.startswith(' {0x')]
        self.assertEqual([row.split(',')[0] for row in rows], [' {0x80001000u', ' {0x80001000u', ' {0x80002000u'])
        self.assertIn('rr_n64_b_80001000_0', rows[0])

    def test_no_block_writes_no_file(self):
        result = n64_native.generate({}, self.folder)
        self.assertEqual(result['blocks'], 0)
        self.assertEqual(list((self.folder / 'blocks').glob('*.c')), [])


class RouteTests(unittest.TestCase):
    def test_routes_are_bounded_and_well_formed(self):
        from retrorecomp import n64_conversion as conversion
        routes = [(3600, conversion.main_route(3600)), (3600, conversion.explore_route(3600))]
        routes += [conversion.play_route(code) for code in conversion.PLAY_ROUTES]
        self.assertIsNone(conversion.play_route('NXXE'))
        for frames, events in routes:
            self.assertEqual(events, sorted(events))
            for begin, end, kind, code, value in events:
                self.assertTrue(0 <= begin < end <= frames)
                if kind == 'pad':
                    self.assertTrue(0 <= code < 14 and value == 0)
                else:
                    self.assertEqual(kind, 'stick')
                    self.assertTrue(0 <= code < 16 and -32768 <= value <= 32767)


class AdaptationTests(unittest.TestCase):
    def test_the_digest_follows_the_replacements(self):
        digest = n64_core.adaptation_digest()
        saved = list(n64_core.REPLACEMENTS)
        try:
            n64_core.REPLACEMENTS.append(('x', 'a', 'b'))
            self.assertNotEqual(n64_core.adaptation_digest(), digest)
        finally:
            n64_core.REPLACEMENTS[:] = saved
        self.assertEqual(n64_core.adaptation_digest(), digest)

    def test_nothing_of_angrylion_or_the_gliden64_renderer_is_copied(self):
        for part in n64_core.COPIED:
            self.assertNotIn('angrylion', part.casefold())
            self.assertFalse(part.startswith('GLideN64/') and not (part.startswith('GLideN64/src/osal/') or part == 'GLideN64/LICENSE'), part)
        self.assertIn('custom/GLideN64', n64_core.EXCLUDED)

    def test_the_pinned_checkout_adapts(self):
        checkout = n64_core.ROOT / '.deps' / 'mupen64plus-libretro-nx'
        if not (checkout / 'mupen64plus-core').is_dir():
            self.skipTest('the pinned Mupen64Plus-Next checkout is not in this workspace')
        target = Path(tempfile.mkdtemp(prefix='n64-adapt-'))
        self.addCleanup(shutil.rmtree, target, True)
        tree = n64_core.adapt(checkout, target)
        exec_header = (tree / 'mupen64plus-core/src/device/r4300/n64_exec.h').read_text(encoding='utf-8')
        self.assertIn('always_inline)) void execute_op(struct r4300_core* r4300, uint32_t op)', exec_header)
        interp = (tree / n64_core.INTERP).read_text(encoding='utf-8')
        self.assertIn('rr_n64_run_blocks(r4300)', interp)
        self.assertFalse((tree / 'custom/GLideN64').exists())
        self.assertFalse(any('angrylion' in path.name.casefold() for path in tree.rglob('*')))
        rom = (tree / 'mupen64plus-core/src/main/rom.c').read_text(encoding='utf-8')
        self.assertIn('rr_n64_ini_gets(buffer, 255, &rr_cursor)', rom)
        self.assertNotIn('ConfigGetSharedDataFilepath("mupen64plus.ini")', rom)
        libretro = (tree / 'libretro/libretro.c').read_text(encoding='utf-8')
        self.assertNotIn('copy_file(inifile, "mupen64plus.ini");', libretro)


if __name__ == '__main__':
    unittest.main()
