from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from retrorecomp.artwork import prepare_icon
from retrorecomp.batch import identify
from retrorecomp.core import ROOT, patched_generator_source, prepare_runtime, read_game_gear_rom, read_rom
from retrorecomp.systems import profile_for_path


def cartridge(region=7):
    data = bytearray(32768)
    data[0x7ff0:0x7ff8] = b'TMR SEGA'
    data[0x7fff] = region << 4
    return bytes(data)


class GameGearTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_single_rom_zip_is_identified_without_extraction(self):
        source = self.root / 'Sample (Europe).zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('inside/Sample.gg', cartridge())
        before = source.read_bytes()
        self.assertEqual(profile_for_path(source).id, 'gg')
        rom = read_game_gear_rom(source)
        self.assertEqual((rom.system_id, rom.region), ('gg', 7))
        self.assertEqual(identify(source).system, 'gg')
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_ambiguous_zip_does_not_guess_a_console(self):
        source = self.root / 'Mixed.zip'
        with ZipFile(source, 'w') as archive:
            archive.writestr('a.gg', cartridge())
            archive.writestr('b.sms', cartridge(region=4))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            profile_for_path(source)

    def test_game_gear_cover_uses_game_gear_repository(self):
        source = self.root / 'Sample.gg'
        build = self.root / 'build'
        build.mkdir()
        image = Image.new('RGB', (32, 32), 'red')
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        with patch('retrorecomp.artwork._get', return_value=buffer.getvalue()) as get:
            result = prepare_icon(build, source, 'Sample', self.root / 'BoxArt', system_id='gg')
        self.assertTrue(result['embedded'])
        self.assertIn('Sega_-_Game_Gear', get.call_args.args[0])


class Z80GeneratorPatchTests(unittest.TestCase):
    """The patched Z80 generator never emits a direct C call to a paged address."""

    pinned = ROOT / '.deps/smsggrecomp/recompiler/src/code_generator.c'

    @unittest.skipUnless(pinned.is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_direct_calls_are_limited_to_the_fixed_first_kib(self):
        text = patched_generator_source(self.pinned.read_text(encoding='utf-8'))
        guard = 'if (T >= 0x0400) return NULL;'
        self.assertEqual(text.count(guard), 1)
        function = text.index('static const char *name_for_target(uint16_t T){')
        self.assertLess(function, text.index(guard))
        self.assertLess(text.index(guard) - function, 400)
        # The two call sites are the only users of name_for_target.
        self.assertEqual(text.count('name_for_target(T)'), 2)

    @unittest.skipUnless(pinned.is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_halt_pushes_the_next_address_and_ends_the_function_when_the_handler_drops_it(self):
        text = patched_generator_source(self.pinned.read_text(encoding='utf-8'))
        # Only the function emitter's HALT changes; the banked emitter never reaches emit_op for a HALT.
        self.assertNotIn('fprintf(o,"        sms_halt();\\n");', text)
        halt = text.index('static void emit_op(FILE *o, const Z80Insn *in){')
        body = text[halt:text.index('switch (in->prefix){', halt)]
        for needed in ('uint16_t _hsp = s->sp;', 'g_dbg_pc = (uint16_t)(g_dbg_pc + 1);', 'sms_halt();',
                       'if ((int16_t)(s->sp - _hsp) > 0) return;'):
            self.assertEqual(body.count(needed), 1, needed)
        self.assertLess(body.index('_hsp = s->sp'), body.index('sms_halt();'))
        self.assertLess(body.index('sms_halt();'), body.index('(int16_t)(s->sp - _hsp)'))

    @unittest.skipUnless(pinned.is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_a_repeating_block_instruction_leaves_the_repeat_cycle_flags_before_the_interrupt_check(self):
        text = patched_generator_source(self.pinned.read_text(encoding='utf-8'))
        block = text.index('static void emit_block(FILE *o, uint8_t op){')
        body = text[block:text.index('/* ---- ED group ---- */', block)]
        # The address is recorded before the loop (the handler of an accepted interrupt changes g_dbg_pc).
        self.assertEqual(body.count('uint16_t sms_block_pc = g_dbg_pc;'), 1)
        self.assertEqual(body.count('((sms_block_pc >> 8) & 0x28)'), 1)
        # INIR/INDR/OTIR/OTDR also adjust H and P; the load and compare groups do not.
        self.assertEqual(body.count('z80f_set(s, Z80_FLAG_H, (b & 15) == (neg ? 0 : 15))'), 1)
        self.assertIn('if (grp >= 2) fprintf', body)
        # Only while the loop goes on, and before the tick that may accept the interrupt.
        self.assertLess(body.index('sms_block_pc >> 8'), body.index('sms_tick_post'))
        self.assertLess(body.index('emit_block_body(o, op, "            ");'), body.index('sms_block_pc >> 8'))


class FunctionsInterruptContractTests(unittest.TestCase):
    """Only the "functions" runner samples /INT at one boundary and accepts it at the next."""

    engine = ROOT / '.deps/smsggrecomp'

    @unittest.skipUnless((engine / 'runner/glue.c').is_file(), 'pinned smsggrecomp sources are not downloaded')
    def test_the_contract_is_applied_to_the_functions_runner_only(self):
        with tempfile.TemporaryDirectory() as temp:
            glue = {}
            for name, functions in (('banked', False), ('functions', True)):
                game = Path(temp) / name
                game.mkdir()
                path = Path(temp) / f'{name}.sms'
                path.write_bytes(bytes(8192))
                prepare_runtime(game, read_rom(path), 'Authored fixture', self.engine, functions=functions)
                glue[name] = (game / 'runtime_glue.c').read_text(encoding='utf-8')
        self.assertNotIn('g_irq_armed', glue['banked'])
        text = glue['functions']
        self.assertEqual(text.count('static bool g_irq_armed;'), 1)
        self.assertIn('while (g_irq_armed && g_z80.iff1 && !g_z80.ei_block) {', text)
        self.assertEqual(text.count('g_dbg_pc = interrupted;'), 2)
        self.assertIn('g_irq_armed = vdp_irq_asserted() && g_z80.iff1;', text)
        self.assertIn('(vdp_irq_asserted() || g_irq_armed) ? g_z80.cyc + 1', text)
        # The interpreter fallback samples from its own first instruction and the reset clears the flag.
        self.assertEqual(text.count('g_irq_armed = false;'), 3)
        # A RET that unwinds every generated frame continues at the address it popped, with a guard.
        self.assertIn('next = sms_read16((uint16_t)(g_z80.sp - 2));', text)
        self.assertIn('else if (++idle > 100000) break;', text)
        self.assertNotIn('next = sms_read16', glue['banked'])
        # A VDP port access brings the next sync to the next instruction; the banked runner keeps its own port code.
        self.assertEqual(text.count('if (p >= 0x80 && p < 0xC0) sms_io_deadline();'), 2)
        self.assertIn('static uint8_t sms_io_in_body(uint8_t p){', text)
        self.assertIn('static void sms_io_out_body(uint8_t p, uint8_t v){', text)
        self.assertNotIn('_body', glue['banked'])


if __name__ == '__main__':
    unittest.main()
