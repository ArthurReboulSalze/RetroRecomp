"""The contention evaluator of the Z80 chain (retrorecomp/z80_timed.py): the walk in Python, the non-pure addresses one by one, the C
text it renders, and (when a C compiler is installed) the rendered C against the Python walk: tools/z80_timed_selftest.py. No ROM."""
import importlib.util
from pathlib import Path
import shutil
import unittest

from retrorecomp import z80_timed
from retrorecomp.z80_chain import COST_GROUPS
from retrorecomp.z80_timing import cycles, length

ROOT = Path(__file__).resolve().parents[1]
STATE = {'pc': 0x8000, 'sp': 0x6000, 'a': 0x12, 'b': 0x34, 'c': 0x56, 'd': 0x78, 'e': 0x9A, 'h': 0x4B, 'l': 0xCD, 'i': 0x3B,
         'r': 0x7E, 'ix': 0x5000, 'iy': 0x7000, 'vec': 0x3BFF}


def peek(address):
    return (address * 7 + 3) & 0xFF


class Recorder:
    """A memory and an I/O rule that note each call (T-state, address) and answer a fixed delay."""

    def __init__(self, memory=0, io=0):
        self.calls, self.wait_memory, self.wait_io = [], memory, io

    def memory(self, t, address):
        self.calls.append(('mem', t, address))
        return self.wait_memory

    def io(self, t, port):
        self.calls.append(('io', t, port))
        return self.wait_io


class WalkTests(unittest.TestCase):
    def test_without_a_delay_the_walk_adds_nothing_and_asks_once_per_contended_t_state(self):
        for group in COST_GROUPS:
            for opcode in range(256):
                base, extra = cycles(group, opcode)
                rules = Recorder()
                self.assertEqual(z80_timed.delay(group, opcode, STATE, peek, 1000, rules.memory, rules.io, taken=True), 0)
                asked = sum(count if kind == 'int' else 1 for kind, _, count in base + extra)
                self.assertEqual(len(rules.calls), asked, (group, hex(opcode)))
                # Without a delay every call comes at the T-state the plain cycle list gives it.
                t, expected = 1000, []
                for kind, _, count in base + extra:
                    if kind == 'int':
                        expected += [t + k for k in range(count)]
                    else:
                        expected.append(t)
                    t += {'m1': 4, 'rd': 3, 'wr': 3, 'in': 4, 'out': 4}.get(kind, count)
                self.assertEqual([call[1] for call in rules.calls], expected, (group, hex(opcode)))

    def test_a_delay_moves_every_later_cycle(self):
        # INC (HL): M1 on PC, read HL, one internal T on HL, write HL; each call waits 2, so each later one starts 2 later.
        rules = Recorder(memory=2)
        self.assertEqual(z80_timed.delay('', 0x34, STATE, peek, 0, rules.memory, rules.io), 8)
        self.assertEqual(rules.calls, [('mem', 0, 0x8000), ('mem', 6, 0x4BCD), ('mem', 11, 0x4BCD), ('mem', 14, 0x4BCD)])

    def test_the_extra_cycles_start_where_the_base_ends(self):
        # DJNZ taken: M1, an internal T on IR, the displacement read; then five internal T on PC+1.
        rules = Recorder(memory=1)
        self.assertEqual(z80_timed.delay('', 0x10, STATE, peek, 100, rules.memory, rules.io, taken=True), 8)
        times = [call[1] for call in rules.calls]
        base_end = 100 + length(cycles('', 0x10)[0]) + 3
        self.assertEqual(times[3:], [base_end + 2 * k for k in range(5)])
        self.assertEqual(z80_timed.delay('', 0x10, STATE, peek, 100, Recorder(1).memory, Recorder(1).io), 3)


class NonPureAddressTests(unittest.TestCase):
    """The addresses the table header names as not plain registers, each seen through the rules."""

    def addresses(self, group, opcode, state=STATE, taken=False):
        rules = Recorder()
        z80_timed.delay(group, opcode, state, peek, 0, rules.memory, rules.io, taken=taken)
        return [(kind, address) for kind, _, address in rules.calls]

    def special(self, name, state=STATE):
        rules = Recorder()
        z80_timed.walk('', z80_timed.SPECIALS[name], state, peek, 0, rules.memory, rules.io)
        return [(kind, address) for kind, _, address in rules.calls]

    def test_the_im2_vector_is_i_and_the_bus_byte(self):
        self.assertEqual(self.special('im2'), [('mem', 0x5FFF), ('mem', 0x5FFE), ('mem', 0x3BFF), ('mem', 0x3C00)])
        self.assertEqual(z80_timed.cycle_length(z80_timed.SPECIALS['im2']), 19)
        self.assertEqual(self.special('im1'), [('mem', 0x5FFF), ('mem', 0x5FFE)])
        self.assertEqual(z80_timed.cycle_length(z80_timed.SPECIALS['im1']), 13)
        self.assertEqual(z80_timed.cycle_length(z80_timed.SPECIALS['nmi']), 11)
        self.assertEqual(self.special('halt'), [('mem', 0x8000)])

    def test_ex_sp_hl_reads_and_writes_both_stack_bytes(self):
        self.assertEqual(self.addresses('', 0xE3), [('mem', 0x8000), ('mem', 0x6000), ('mem', 0x6001), ('mem', 0x6001),
                                                    ('mem', 0x6001), ('mem', 0x6000), ('mem', 0x6000), ('mem', 0x6000)])

    def test_a_block_repeat_waits_on_the_registers_before_the_instruction(self):
        ldir = self.addresses('ed', 0xB0, taken=True)
        self.assertEqual(ldir[-5:], [('mem', 0x789A)] * 5)                 # DE as it was
        cpir = self.addresses('ed', 0xB1, taken=True)
        self.assertEqual(cpir[-5:], [('mem', 0x4BCD)] * 5)                 # HL as it was
        otir = self.addresses('ed', 0xB3, taken=True)
        self.assertEqual(otir[-6:], [('io', 0x3356)] + [('mem', 0x3356)] * 5)    # B less one : C

    def test_in_and_out_go_to_the_io_rule_with_the_whole_port(self):
        self.assertEqual(self.addresses('', 0xDB), [('mem', 0x8000), ('mem', 0x8001), ('io', 0x1200 | peek(0x8001))])
        self.assertEqual(self.addresses('ed', 0x78), [('mem', 0x8000), ('mem', 0x8001), ('io', 0x3456)])
        self.assertEqual(self.addresses('ed', 0xA3)[-1], ('io', 0x3356))

    def test_indexed_and_operand_addresses(self):
        displacement = peek(0x8002)
        signed = displacement - 256 if displacement > 127 else displacement
        self.assertIn(('mem', (0x5000 + signed) & 0xFFFF), self.addresses('dd', 0x34))
        self.assertIn(('mem', (0x7000 + signed) & 0xFFFF), self.addresses('fdcb', 0x06))
        word = peek(0x8001) | peek(0x8002) << 8
        self.assertEqual(self.addresses('', 0x22)[-2:], [('mem', word), ('mem', (word + 1) & 0xFFFF)])


class ChainTests(unittest.TestCase):
    """Z80Machine.contention in the chain's texts: rendered only where asked, refused where it cannot hold."""

    def test_contention_needs_the_z80s_own_counts(self):
        from retrorecomp.z80_chain import SEGA_MAPPER, Z80Costs, Z80Machine
        for bad in (dict(m1_wait=1), dict(costs=Z80Costs(irq=15))):
            with self.subTest(bad), self.assertRaises(ValueError):
                Z80Machine('x', SEGA_MAPPER.regions, contention=True, **bad)

    def test_only_a_machine_with_contention_renders_the_evaluator(self):
        import dataclasses
        from retrorecomp import z80_chain
        from retrorecomp.systems import find_profile
        for system in ('sms', 'gg', 'msx', 'msx2', 'msx2plus', 'sg1000', 'coleco', 'zxs'):
            machine = find_profile(system).z80_machine
            self.assertFalse(machine.contention, system)
            for text in (z80_chain.banked_runtime(machine, ROOT), z80_chain.banked_emitter(machine, ROOT)):
                self.assertNotIn('rr_timed', text, system)
        timed = dataclasses.replace(find_profile('zxs').z80_machine, contention=True)
        loop = z80_chain.banked_runtime(timed, ROOT)
        for needle in ('rr_timed_epoch = base;', 'RR_TIMED_HALT', 'RR_TIMED_IM2 : RR_TIMED_IM1'):
            self.assertIn(needle, loop)
        emitter = z80_chain.banked_emitter(timed, ROOT)
        self.assertEqual(emitter.count('rr_timed_extra(rr_g, rr_op, &rr_ts, s->cyc)'), 5)    # RET, DJNZ, JR, CALL, repeat
        self.assertEqual(emitter.count('rr_timed_base(rr_g, rr_op, &rr_ts, rr_t0)'), 2)      # a block, any other
        self.assertIn('RR_TIMED_FRAGMENT', emitter)
        self.assertIn('#include \\"banked_timed.h\\"', emitter)
        with_nmi = dataclasses.replace(find_profile('sg1000').z80_machine, contention=True)      # a machine with the /NMI pin
        self.assertIn('RR_TIMED_NMI', z80_chain.banked_runtime(with_nmi, ROOT))

    @unittest.skipUnless((ROOT / '.deps/smsggrecomp/runner/external/superzazu/z80.c').is_file(),
                         'pinned smsggrecomp sources are not downloaded')
    def test_the_reference_takes_the_delays_only_when_asked(self):
        import tempfile
        from retrorecomp.cpu import prepare_reference
        texts = {}
        for timed in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                prepare_reference(Path(folder), ROOT / '.deps/smsggrecomp', contention=timed, port16=True)
                texts[timed] = (Path(folder) / 'runtime_reference.c').read_text(encoding='utf-8')
        self.assertNotIn('rr_timed', texts[False])
        for needle in ('uint64_t rr_timed_epoch;', 'RR_TIMED_FRAGMENT', 'RR_TIMED_HALT', 'RR_TIMED_NMI', 'RR_TIMED_IM2',
                       'rr_timed_plain[rr_tg][decoded]'):
            self.assertIn(needle, texts[True])
        self.assertEqual(texts[True].count('RR_TIMED_IM1'), 2)                  # modes 0 and 1
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as folder:
                prepare_reference(Path(folder), ROOT / '.deps/smsggrecomp', contention=True, m1_counter=True)


class RenderTests(unittest.TestCase):
    def test_the_c_text_holds_every_encoding_and_is_stable(self):
        text = z80_timed.render_c()
        self.assertEqual(text, z80_timed.render_c())
        self.assertIn('static const uint16_t rr_timed_index[7][256]', text)
        self.assertIn('RR_TIMED_IM2', text)
        for name in ('rr_timed_base', 'rr_timed_extra', 'rr_timed_special_delay'):
            self.assertIn(f'RR_TIMED_API uint32_t {name}(', text)
            self.assertIn(f'RR_TIMED_API uint32_t {name}(', z80_timed.render_header())
        self.assertNotIn('\r', text)

    def test_the_rendered_c_walks_as_the_python_model(self):
        spec = importlib.util.spec_from_file_location('z80_timed_selftest', ROOT / 'tools' / 'z80_timed_selftest.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        compiler = module.find_compiler()
        if compiler is None:
            self.skipTest('no C compiler found (tools/z80_timed_selftest.py)')
        result = module.run(compiler, samples=6)
        self.assertEqual(result['mismatches'], [], result)
        self.assertGreater(result['compared'], 7 * 256 * 6)
        self.assertTrue(result['control_differs'])


if __name__ == '__main__':
    unittest.main()
