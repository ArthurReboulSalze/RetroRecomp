"""Converter memory and cartridge isolation checks with authored data."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import megadrive, m68000, megadrive_codegen
from retrorecomp.megadrive_codegen import translated_body, operation_name, jump_table_entries
from retrorecomp.core import ConversionError


class MegaDriveMemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        env = patch.dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(self.root / 'library'))
        env.start(); self.addCleanup(env.stop)
        data = bytearray(range(256)) * 16
        for offset, value in ((0, 0xffc000), (4, 0x200), (0x70, 0x220), (0x78, 0x240)):
            data[offset:offset + 4] = value.to_bytes(4, 'big')
        self.rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest())
        profiles = patch.dict(megadrive.PROFILES, {self.rom.sha256:
            {'id': 'authored', 'title': 'Authored test', 'prefix': 'game', 'sonic': False}})
        profiles.start(); self.addCleanup(profiles.stop)

    def test_library_filters_misaligned_outside_and_stale_rom_entries(self):
        check = {'rom_entries': [0x200, 0x220, 0x221, 0xff0000, len(self.rom.data)]}
        self.assertEqual(megadrive.learn_entries(self.rom, [check]), 2)
        self.assertEqual(megadrive.read_entries(self.rom), {0x200, 0x220})
        self.rom.data[0x220] ^= 1
        self.assertEqual(megadrive.read_entries(self.rom), {0x200})

    def test_library_isolated_by_exact_rom_hash(self):
        megadrive.learn_entries(self.rom, [{'rom_entries': [0x200]}])
        record = megadrive.memory_file(self.rom)
        data = json.loads(record.read_text()); data['rom_sha256'] = '0' * 64
        record.write_text(json.dumps(data))
        self.assertEqual(megadrive.read_entries(self.rom), set())

    def test_ram_variants_merge_without_losing_previous_rom_observations(self):
        megadrive.learn_entries(self.rom, [{'rom_entries': [0x200]}])
        first = {'address': 0xff8000, 'bytes': '7001'}
        second = {'address': 0xff8000, 'bytes': '70ff'}
        invalid = [{'address': 0x200, 'bytes': '7001'}, {'address': 0xff8001, 'bytes': '7001'},
                   {'address': 0xff8000, 'bytes': 'zzzz'}, {'address': 0xff8000, 'bytes': '700'}]
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': [first, *invalid]}]), 1)
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': [first, second]}]), 1)
        self.assertEqual(megadrive.read_ram_variants(self.rom), [first, second])
        self.assertEqual(megadrive.read_entries(self.rom), {0x200})

    def test_observed_interior_pcs_are_not_made_function_entries(self):
        megadrive.write_profile(self.root, self.root, self.rom, {0x208, 0x20a, 0x20c})
        import tomllib
        profile = tomllib.loads((self.root / 'game.toml').read_text())
        self.assertNotIn(0x208, profile['functions']['extra'])
        self.assertEqual(profile['ram_layout']['initial_ssp'], 0xffc000)

    def test_ram_instruction_extent_includes_final_words_without_bus_wrap(self):
        variants = [{'address': 0xfffff4, 'bytes': '4ef900000800'},
                    {'address': 0xfffffa, 'bytes': '4ef900000800'},
                    {'address': 0xfffffe, 'bytes': '4e71'}]
        rejected = [{'address': 0xfffffc, 'bytes': '4ef900000800'},
                    {'address': 0xfffffe, 'bytes': '4e710000'},
                    {'address': 0xffffff, 'bytes': '4e71'},
                    {'address': 0x1000000, 'bytes': '4e71'}]
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': variants + rejected}]), 3)
        self.assertEqual(megadrive.read_ram_variants(self.rom), variants)

    def test_other_cartridge_is_not_compiled_as_a_known_title(self):
        self.rom.sha256 = '0' * 64
        self.rom.title = 'Another cartridge'
        profile = megadrive.profile_for(self.rom)
        self.assertEqual(profile['title'], self.rom.title)
        self.assertEqual(profile['source'], 'cartridge')
        self.assertFalse(profile['sonic'])
        megadrive.write_profile(self.root, self.root, self.rom, set())
        self.assertIn('output_prefix="game"', (self.root / 'game.toml').read_text())

    def test_invalid_stack_and_odd_interrupt_vectors_rejected(self):
        self.rom.data[0:4] = (0x80000).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_known_eeprom_board_support_without_save_header_or_known_rom(self):
        self.rom.data[0x180:0x18e] = b'GM T-81406 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = b' ' * 12
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])
        self.assertTrue(megadrive.eeprom_device(self.rom)['implemented'])
        self.assertEqual(megadrive.eeprom_device(self.rom)['chip'], '24C04')

    def test_large_rom_requires_explicit_mapper_identity_and_mapped_vectors(self):
        self.rom.data=bytearray(b'\xff'*0x500000)
        for offset,value in ((0,0xffc000),(4,0x200),(0x70,0x220),(0x78,0x240)):
            self.rom.data[offset:offset+4]=value.to_bytes(4,'big')
        self.rom.data[0x100:0x110]=b'SEGA MEGA DRIVE '.ljust(16,b' ')
        with self.assertRaises(ConversionError):megadrive.validate_cartridge(self.rom)
        self.rom.data[0x180:0x18e]=b'GM MK-12056-00'
        megadrive.validate_cartridge(self.rom)
        self.assertEqual(megadrive.bank_mapper(self.rom)['kind'],'sega_512k')
        self.rom.data[4:8]=(0x400200).to_bytes(4,'big')
        with self.assertRaises(ConversionError):megadrive.vectors(self.rom)
        self.rom.data[0x180:0x18e]=b' '*14
        self.rom.data[0x100:0x110]=b'SEGA SSF'.ljust(16,b' ')
        megadrive.validate_cartridge(self.rom)
        self.rom.data.extend(b'\xff'*0x400000)
        with self.assertRaises(ConversionError):megadrive.validate_cartridge(self.rom)
        self.rom.sha256 = '0' * 64
        self.rom.title = 'Renamed cartridge'
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])

    def test_parallel_sram_patch_overrides_original_sega_eeprom_identity(self):
        self.rom.data[0x180:0x18e] = b'GM T-12053 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241f8200020000100203fff')
        self.assertIsNone(megadrive.eeprom_device(self.rom))
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241e8400020000100200001')
        self.assertEqual(megadrive.eeprom_device(self.rom)['chip'], 'X24C01')

    def test_unlisted_declared_eeprom_keeps_limitation_without_guessing_circuit(self):
        self.rom.data[0x180:0x18e] = b'GM T-99999 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241e8400020000100200001')
        device = megadrive.eeprom_device(self.rom)
        self.assertIsNone(device['chip'])
        self.assertIsNone(device['wiring'])
        self.assertFalse(device['implemented'])
        self.assertIn('EEPROM', megadrive.profile_for(self.rom)['limitations'][0])
        self.rom.data[0:4] = (0xffc000).to_bytes(4, 'big')
        self.rom.data[0x78:0x7c] = (0x241).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_all_work_ram_aliases_accept_stack_irq_and_guarded_observations(self):
        for base in range(0xe00000, 0x1000000, 0x10000):
            with self.subTest(base=base):
                self.rom.data[:4] = (0xff000000 | base | 0xc000).to_bytes(4, 'big')
                self.rom.data[0x78:0x7c] = (base | 0x8000).to_bytes(4, 'big')
                values = megadrive.vectors(self.rom)
                self.assertEqual(values['ssp'], 0xff000000 | base | 0xc000)
                self.assertEqual(values['vblank'], base | 0x8000)
                self.assertTrue(megadrive.valid_ram_variant({'address': base | 0x8000, 'bytes': '4e71'}))
        self.assertFalse(megadrive.valid_ram_variant({'address': 0xdffffe, 'bytes': '4e71'}))

    def test_svp_hardware_marker_rejects_without_relying_on_title(self):
        self.rom.data[0x1c8:0x1ca] = b'SV'
        self.rom.title = 'Renamed cartridge'
        with self.assertRaisesRegex(ConversionError, 'SVP coprocessor'):
            megadrive.validate_cartridge(self.rom)
        self.rom.data[0x1c8:0x1ca] = b'  '
        self.rom.title = 'Virtua Racing'
        megadrive.validate_cartridge(self.rom)

    def test_empty_stack_at_bus_wrap_preserves_full_address_register(self):
        for stack in (0, 0x1000000, 0xffff0000, 0xfffffffe):
            with self.subTest(stack=stack):
                self.rom.data[:4] = stack.to_bytes(4, 'big')
                self.assertEqual(megadrive.vectors(self.rom)['ssp'], stack)
        for stack in (1, 2, 0x1000001, 0xffff0001):
            with self.subTest(invalid_stack=stack):
                self.rom.data[:4] = stack.to_bytes(4, 'big')
                with self.assertRaises(ConversionError):
                    megadrive.vectors(self.rom)

    def test_unused_horizontal_interrupt_vector_is_preserved_without_becoming_code(self):
        self.rom.crc32 = 0x12345678
        for vector in (0, 0xffffffff):
            with self.subTest(vector=vector):
                self.rom.data[0x70:0x74] = vector.to_bytes(4, 'big')
                vectors = megadrive.vectors(self.rom)
                self.assertEqual(vectors['hblank'], vector & 0xffffff)
                self.assertNotIn(vectors['hblank'], vectors['roots'])
                megadrive.write_spec(self.root, self.rom, 'Authored test')
                self.assertIn(f'#define RR_MD_HBLANK 0x{vector & 0xffffff:06x}u',
                              (self.root / 'retro_md_game.h').read_text())
        # The required vertical interrupt keeps its normal validity checks.
        self.rom.data[0x78:0x7c] = (0xffffffff).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_console_region_uses_header_and_not_game_title(self):
        self.rom.crc32 = 0x12345678
        for header, overseas in ((b'J', 0), (b'U', 1), (b'JUE', 1), (b'1', 0),
                                  (b'4', 1), (b'9', 0), (b'F', 1)):
            with self.subTest(header=header):
                self.rom.data[0x1f0:0x200] = header.ljust(16, b' ')
                megadrive.write_spec(self.root, self.rom, 'Unrelated title')
                spec = (self.root / 'retro_md_game.h').read_text()
                self.assertIn(f'#define RR_MD_OVERSEAS {overseas}\n', spec)

    def test_native_body_contains_selected_operation_and_literal_operands(self):
        instruction = {'addr': 0xff8000, 'mnemonic': 2, 'size': 2,
            'words': [0x7001] + [0] * 7, 'word_count': 1, 'byte_length': 2, 'src_ea': -1,
            'dst_ea': -1, 'reg': 0, 'imm32': 1, 'target_addr': 0, 'has_target': 0,
            'dst_is_ea': 0, 'predec_mem_form': 0, 'mem_shift': 0}
        body = translated_body(instruction, 'MN_MOVEQ', 'g_cpu.D[ins->reg] = ins->imm32; return M68KI_OK;')
        self.assertIn('g_cpu.D[(0)] = (1)', body)
        self.assertNotIn('m68k_decode(', body)
        self.assertNotIn('exec_one(', body)
        self.assertEqual(operation_name(instruction), 'rr_md_op_ff8000_7001')
        instruction['words'][0] = 0x70ff
        self.assertEqual(operation_name(instruction), 'rr_md_op_ff8000_70ff')


class JumpTableDiscoveryTests(unittest.TestCase):
    def test_reached_slot_expands_siblings_but_arbitrary_pointers_do_not(self):
        data = bytearray(b'\xff' * 4096)
        for pc, target in ((0x400, 0x500), (0x404, 0x510), (0x408, 0x520)):
            data[pc:pc+4] = b'\x4e\xfa' + (target - pc - 2).to_bytes(2, 'big', signed=True)
        self.assertEqual(jump_table_entries(data, {0x404}), {0x400, 0x404, 0x408})
        self.assertEqual(jump_table_entries(data, set()), set())
        self.assertEqual(jump_table_entries(data, {0x403, 0x1000, 0xff0000}), set())
        for pc, target in ((0x600, 0x500), (0x604, 0x510), (0x608, 0x520)):
            data[pc:pc+4] = target.to_bytes(4, 'big')
        self.assertEqual(jump_table_entries(data, {0x604}), set())

    def test_short_invalid_truncated_and_negative_displacement_runs(self):
        data = bytearray(b'\xff' * 4096)
        for pc, target in ((0x600, 0x200), (0x604, 0x210), (0x608, 0x220)):
            data[pc:pc+4] = b'\x60\x00' + (target - pc - 2).to_bytes(2, 'big', signed=True)
        self.assertEqual(jump_table_entries(data, {0x604}), {0x600, 0x604, 0x608})
        data[0x608:0x60c] = b'\xff' * 4
        self.assertEqual(jump_table_entries(data, {0x604}), set())
        for target in (0x201, 0x1000, 0):
            data[0x608:0x60c] = b'\x60\x00' + (target - 0x60a).to_bytes(2, 'big', signed=True)
            self.assertEqual(jump_table_entries(data, {0x604}), set())
        data[0xffc:0x1000] = bytes.fromhex('4ef90000')
        self.assertEqual(jump_table_entries(data, {0xffc}), set())


ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/segagenesisrecomp/runner/m68k_interp.c'
ANCHOR = '        int reg_count = (ins->src_ea >= 0);\n'
HOOK = 'rr_md_arithmetic_phase((sz == M68K_SIZE_L ? 8u : 6u) + 2u * (g_cpu.D[ins->src_ea] & 63u), 0, 1);'


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class ShiftTimingAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = m68000.adapt_semantics(PINNED.read_text(encoding='utf-8'))

    def test_the_hook_is_added_once_before_the_shift_and_only_for_a_register_count(self):
        adapted = megadrive_codegen.adapt_shift_timing(self.source)
        self.assertEqual(adapted.count(HOOK), 1)
        start = adapted.index(ANCHOR)
        self.assertLess(start, adapted.index(HOOK))
        self.assertLess(adapted.index(HOOK), adapted.index('do_shift(ins->mnemonic', start))
        self.assertIn('if (reg_count)\n            ' + HOOK, adapted)

    def test_the_other_machines_text_is_untouched(self):
        for prefix in ('rr_ng', 'rr_cps1', 'rr_x68k'):
            self.assertNotIn('2u * (g_cpu.D[ins->src_ea] & 63u)',
                             m68000.adapt_semantics(PINNED.read_text(encoding='utf-8'), hook_prefix=prefix))

    def test_reset_is_executed_for_the_mega_drive_only(self):
        # Supervisor RESET changes nothing but the PC and the clocks; user mode keeps the privilege violation.
        raw = PINNED.read_text(encoding='utf-8')
        halt = 'g_m68ki_bad_pc = ins->addr; g_m68ki_bad_op = ins->words[0];\n        return M68KI_HALT_UNIMPL;'
        shared = m68000.adapt_semantics(raw)
        start = shared.index('    case MN_RESET:')
        self.assertIn(halt, shared[start:start + 400])
        adapted = megadrive_codegen.adapt_reset(shared)
        body = adapted[adapted.index('    case MN_RESET:'):][:500]
        self.assertIn('rr_md_instruction_exception(next_pc, 8, ins->addr, 34)', body)
        self.assertNotIn('HALT_UNIMPL', body)
        self.assertIn('return M68KI_OK;', body)
        for prefix in ('rr_ng', 'rr_cps1', 'rr_x68k'):
            other = m68000.adapt_semantics(raw, hook_prefix=prefix)
            self.assertIn(halt, other[other.index('    case MN_RESET:'):][:500], prefix)
        with self.assertRaises(ConversionError):
            megadrive_codegen.adapt_reset(adapted)

    def test_the_neogeo_cps1_and_x68000_generators_never_get_the_hook(self):
        # Their stamp groups include megadrive_codegen, but they only import write_changed / the decoder tool: the hook is
        # applied by megadrive_codegen's generate_steps and adapt_interpreter alone.
        hook = 'rr_md_arithmetic_phase((sz == M68K_SIZE_L'
        for name in ('retrorecomp/neogeo_codegen.py', 'retrorecomp/cps1_codegen.py', 'tools/x68000_native.py'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn('adapt_shift_timing', text, name)
            self.assertNotIn(hook, text, name)
        for prefix in ('rr_ng', 'rr_cps1', 'rr_x68k'):
            self.assertNotIn(hook, m68000.adapt_semantics(PINNED.read_text(encoding='utf-8'), hook_prefix=prefix), prefix)
        self.assertIn(hook, megadrive_codegen.adapt_shift_timing(self.source))

    def test_a_changed_upstream_fails_loudly(self):
        with self.assertRaises(ConversionError):
            megadrive_codegen.adapt_shift_timing(self.source.replace(ANCHOR, ANCHOR.replace('>= 0', '> 0'), 1))


class ShiftFixtureClockTests(unittest.TestCase):
    def test_every_register_count_vector_is_replayed_with_its_clocks(self):
        fixture = json.loads((ROOT / 'tests/fixtures/m68k-shifts/cases.json').read_text(encoding='utf-8'))
        self.assertFalse([t['name'] for t in fixture['tests'] if 'timing_unchecked' in t])
        counted = 0
        for test in fixture['tests']:
            opcode = int(test['name'].split()[-1], 16)
            if not opcode & 0x20:
                continue
            count = test['initial'][f'd{(opcode >> 9) & 7}'] & 63
            expected = (8 if test['group'].endswith('.l') else 6) + 2 * count
            self.assertEqual(test['length'], expected, test['name'])
            counted += 1
        self.assertGreater(counted, 400)


class PinnedSoundCpuRecompilerIsNotBuiltTests(unittest.TestCase):
    """The pinned z80-recomp-core header reads a 16-bit value with two reads in one C expression (sms_read16, used by the
    engine's runner/z80_recomp.c for the IM 2 vector). The Mega Drive sound CPU never builds that code: its Z80 is the
    private SuperZazu copy, whose 16-bit accesses are already two ordered reads. If the build ever compiles
    z80_recomp.c or defines GENESIS_Z80_RECOMP, the two reads must be ordered like the Master System's first."""

    def test_the_mega_drive_build_does_not_compile_the_pinned_z80_recompiler(self):
        root = Path(__file__).resolve().parents[1] / 'retrorecomp'
        for name in ('console16.py', 'console16_optimization.py', 'megadrive.py', 'megadrive_codegen.py', 'megadrive_runtime.py',
                     'megadrive_z80.py', 'megadrive_z80_timing.py', 'megadrive_bus.py', 'systems/console16.py'):
            text = (root / name).read_text(encoding='utf-8')
            self.assertNotIn('z80_recomp.c', text, name)
            self.assertNotIn('sms_runtime', text, name)
            self.assertNotIn('-DGENESIS_Z80_RECOMP', text, name)
            self.assertNotIn('GENESIS_Z80_RECOMP=', text, name)

    def test_the_private_z80_reads_16_bits_as_two_ordered_reads(self):
        from retrorecomp import megadrive_z80_timing
        text = (Path(__file__).resolve().parents[1] / 'retrorecomp/megadrive_z80_timing.py').read_text(encoding='utf-8')
        import re
        self.assertRegex(text, r'uint8_t lo = rb\(z, addr\);\s+uint8_t hi = rb\(z, \(uint16_t\)\(addr \+ 1\)\);')
        self.assertIn('uint8_t lo = nextb(z), hi = nextb(z);', text)
        self.assertRegex(text, r'uint8_t lo = rb\(z, z->sp\+\+\);\s+uint8_t hi = rb\(z, z->sp\+\+\);')
        self.assertTrue(callable(megadrive_z80_timing.adapt))


class DeliveredFileEvidenceTests(unittest.TestCase):
    """Liveness (G8) and the packed replay (G5) of the Mega Drive, on synthetic traces and a fake delivered file."""
    HEADER = 'frame,frame_hash,native,interpreted,audio_hash,pc,sr,sp,z80_pc,busreq,reset_off,fm_nonzero,psg_nonzero'

    def trace(self, rows, header=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'play.trace.csv'
        path.write_text(chr(10).join([header or self.HEADER] + rows) + chr(10), encoding='ascii')
        return path

    def line(self, frame, picture, sound='aa', pc='000200', fm=0, psg=0):
        return f'{frame},{picture},10,0,{sound},{pc},2700,fffffff0,0000,0,1,{fm},{psg}'

    def test_a_moving_route_has_its_record(self):
        from retrorecomp import megadrive_evidence as evidence
        record = evidence.route_liveness(self.trace([
            self.line(1, 'p1', 's1', '000200', 0, 0), self.line(2, 'p1', 's1', '000204', 5, 0),
            self.line(3, 'p2', 's2', '000208', 0, 7), self.line(4, 'p2', 's2', '000208', 0, 0)]))
        self.assertEqual(record, {'frames': 4, 'distinct_pictures': 2, 'picture_changes': 1, 'last_picture_change_frame': 3,
                                  'audible_frames': 2, 'last_audible_frame': 3, 'distinct_sound_blocks': 2,
                                  'distinct_program_counters': 3})

    def test_a_column_the_trace_lacks_is_none_not_zero(self):
        from retrorecomp import megadrive_evidence as evidence
        record = evidence.route_liveness(self.trace(['1,pa', '2,pb', '3,pb'], header='frame,frame_hash'))
        self.assertEqual((record['distinct_pictures'], record['picture_changes']), (2, 1))
        self.assertIsNone(record['audible_frames'])
        self.assertIsNone(record['last_audible_frame'])
        self.assertIsNone(record['distinct_sound_blocks'])
        self.assertIsNone(record['distinct_program_counters'])

    def test_only_a_frozen_play_route_is_refused(self):
        from retrorecomp import megadrive_evidence as evidence
        frozen = evidence.route_liveness(self.trace([self.line(n, 'same', fm=1) for n in range(1, 6)]))
        moving = evidence.route_liveness(self.trace([self.line(1, 'a'), self.line(2, 'b')]))
        folder = Path('checks/packed')
        evidence.require_main_route_moving('play', moving, folder)
        for scenario in ('demo', 'advanced', 'early-start', 'menu-confirm', 'pseudo-random-1'):
            evidence.require_main_route_moving(scenario, frozen, folder)   # a still title, a menu: accepted
        with self.assertRaises(ConversionError) as error:
            evidence.require_main_route_moving('play', frozen, folder)
        self.assertIn('never changed', str(error.exception))

    def delivered(self, differences):
        """replay_delivered with the compression replaced by a fake delivered file and the replay by a synthetic trace."""
        from retrorecomp import megadrive_evidence as evidence
        from retrorecomp.delivery_evidence import DeliveredFile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        fake = DeliveredFile(root / 'packed-game.exe', None, 'f' * 64)
        checks = [{'scenario': 'demo', 'frames': 3}, {'scenario': 'play', 'frames': 3}]
        references = {check['scenario']: {'scenario': check['scenario']} for check in checks}
        runs = []

        def replay(candidate, directory, check):
            runs.append((candidate, check['scenario']))
            (directory / f"{check['scenario']}.trace.csv").write_text(
                chr(10).join([self.HEADER] + [self.line(n, f"p{n}", fm=1) for n in (1, 2, 3)]) + chr(10), encoding='ascii')
            return {'scenario': check['scenario']}

        with patch.object(evidence, 'deliver_packed', return_value=fake):
            outcome = evidence.replay_delivered(root / 'game.exe', root / 'packed-game.exe', root / 'packed', checks,
                                                references, replay, lambda result, reference: differences(result), print)
        return fake, outcome, runs

    def test_the_delivered_file_matches_on_every_route(self):
        fake, (delivered, results), runs = self.delivered(lambda result: [])
        self.assertIs(delivered, fake)
        self.assertEqual([scenario for _, scenario in runs], ['demo', 'play'])
        self.assertEqual(fake.validation_fields(), {'packed_reference_match': True})
        self.assertEqual(fake.report_fields(), {'packed_candidate_sha256': 'f' * 64})
        self.assertEqual(results['play']['liveness']['picture_changes'], 2)

    def test_a_difference_refuses_the_delivered_file(self):
        from retrorecomp.delivery_evidence import DeliveredFile
        with self.assertRaises(ConversionError) as error:
            self.delivered(lambda result: ['frame_hash'] if result['scenario'] == 'play' else [])
        self.assertIn('differs from the fresh reference', str(error.exception))
        self.assertIn('frame_hash', str(error.exception))
        fresh = DeliveredFile(Path('x.exe'), None, '0' * 64)
        with self.assertRaises(ValueError):
            fresh.validation_fields()   # a file nobody replayed cannot claim the match


class LearnedCodeLimitsAreCountedTests(unittest.TestCase):
    """What the limits of the learned code cut is counted for the report (nothing is silent); no ROM, no compiler."""

    def test_the_ram_variant_library_counts_what_the_limit_cuts(self):
        limit = megadrive.RAM_VARIANT_LIMIT
        pairs = [(0xe00000 + 2 * n, '4e71') for n in range(limit + 50)]
        observed = [{'address': 0xf00000 + 2 * n, 'bytes': '4e71'} for n in range(10)]
        rom = SimpleNamespace(data=b'', sha256='0' * 64)
        with patch.object(megadrive, '_ram_variant_pairs', lambda rom, imported: pairs):
            self.assertEqual(len(megadrive.read_ram_variants(rom)), limit)       # the lowest addresses are still kept
            self.assertEqual(megadrive.ram_variant_overflow(rom), {'limit': limit, 'known': limit + 50, 'dropped': 50})
            self.assertEqual(megadrive.ram_variant_overflow(rom, [{'ram_variants': observed}])['dropped'], 60)
        with patch.object(megadrive, '_ram_variant_pairs', lambda rom, imported: pairs[:limit]):
            self.assertEqual(megadrive.ram_variant_overflow(rom)['dropped'], 0)

    def test_the_z80_library_counts_variants_and_driver_images_past_their_limits(self):
        from retrorecomp import megadrive_z80
        rom = SimpleNamespace(data=b'', sha256='0' * 64)
        # 40,960 distinct positions (8,192 below $4000 once mirrored, 32,768 from $8000), all the same opcode.
        items = [{'address': pc, 'bytes': '00000000'} for pc in (*range(0x2000), *range(0x8000, 0x10000))]
        images = [f'{n:02x}' * 8192 for n in range(1, 7)]
        with patch.object(megadrive_z80, '_library_items', lambda rom, imported: items):
            self.assertEqual(len(megadrive_z80.read_variants(rom)), megadrive_z80.LIMIT)
            report = megadrive_z80.variant_overflow(rom, [{'z80_driver_images': images}])
        self.assertEqual((report['limit'], report['image_limit']), (32768, 4))
        self.assertEqual(report['images_dropped'], 2)
        self.assertEqual(report['dropped'], report['known'] - 32768)
        self.assertGreater(report['dropped'], 8000)
        with patch.object(megadrive_z80, '_library_items', lambda rom, imported: items[:100]):
            small = megadrive_z80.variant_overflow(rom, [])
        self.assertEqual((small['dropped'], small['images_dropped']), (0, 0))

    def test_the_driver_images_learned_are_the_first_four_of_each_run(self):
        from retrorecomp import megadrive_z80
        images = [f'{n:02x}' * 8192 for n in range(1, 7)]
        found, cut = megadrive_z80._observed([{'z80_driver_images': images}])
        self.assertEqual((len(found), cut), (4 * 8192, 2))
        found, cut = megadrive_z80._observed([{'z80_driver_images': images[:4]}, {'z80_driver_images': images[:4]}])
        self.assertEqual(cut, 0)

    def test_the_report_block_says_what_was_cut_and_what_the_game_could_not_record(self):
        from retrorecomp import megadrive_evidence
        rom = SimpleNamespace(data=b'', sha256='0' * 64)
        checks = [{'ram_variants': [], 'ram_observation_overflows': 7, 'ram_variants_dropped': 5, 'ram_variants_dropped_exact': True,
                   'z80_dropped_variants': 0},
                  {'ram_variants': [], 'ram_observation_overflows': 9, 'ram_variants_dropped': 4, 'ram_variants_dropped_exact': False,
                   'z80_dropped_variants': 3}]
        with patch.object(megadrive, '_ram_variant_pairs', lambda rom, imported: []),              patch('retrorecomp.megadrive_z80._library_items', lambda rom, imported: []):
            block = megadrive_evidence.learning_limits(rom, checks)
        self.assertEqual(block['ram_variants']['native_observations_dropped'], 9)
        self.assertEqual(block['ram_variants']['native_variants_dropped'], 5)
        self.assertFalse(block['ram_variants']['native_variants_dropped_exact'])     # a table that saturated says so
        self.assertEqual(block['z80_variants']['native_variants_dropped'], 3)
        self.assertTrue(block['anything_cut'])
        with patch.object(megadrive, '_ram_variant_pairs', lambda rom, imported: []),              patch('retrorecomp.megadrive_z80._library_items', lambda rom, imported: []):
            quiet = megadrive_evidence.learning_limits(rom, [{'ram_variants': []}])
        self.assertFalse(quiet['anything_cut'])


if __name__ == '__main__':
    unittest.main()
