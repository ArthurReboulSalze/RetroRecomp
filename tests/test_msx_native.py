"""The MSX on the banked Z80 chain (systems/msx.py, retrorecomp/msx_build.py, tools/msx_native.py): the machine it declares and the step loop rendered for it.
No ROM, no compiler: the native runs themselves are checked by the tool against the reference."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tool():
    sys.path.insert(0, str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location('msx_native', ROOT / 'tools' / 'msx_native.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['msx_native'] = module
    spec.loader.exec_module(module)
    return module


class MachineTests(unittest.TestCase):
    def setUp(self):
        self.tool = tool()
        self.machine = self.tool.MSX_MACHINE

    def test_the_msx_is_a_region_map_of_eight_8k_regions_with_the_cartridge_then_the_bios(self):
        self.assertTrue(self.machine.mapped)
        self.assertEqual(self.machine.regions.region_bits, 13)
        self.assertEqual(self.machine.regions.regions, 8)
        self.assertEqual(self.machine.regions.sources, ('cartridge', 'bios'))

    def test_one_wait_state_per_m1_and_int_read_at_the_end_of_the_instruction(self):
        self.assertEqual(self.machine.m1_wait, 1)
        self.assertTrue(self.machine.counts_m1)
        self.assertEqual(self.machine.irq_sample, 'instruction_end')

    def test_the_generator_lives_in_its_own_folders(self):
        self.assertEqual(self.machine.generator_source, 'recompiler-src-msx')
        self.assertEqual(self.machine.generator_build, 'recompiler-build-msx')

    def test_the_step_loop_rendered_for_the_msx(self):
        from retrorecomp.paths import ASSETS
        from retrorecomp.z80_chain import banked_runtime
        loop = banked_runtime(self.machine, ASSETS)
        self.assertIn('smsrecomp_region_map()', loop)
        self.assertIn('game_banked_step(map)', loop)
        self.assertIn('g_hz.cyc += 1 * (z80_m1_fetches - m1_before)', loop)       # the fallback's wait states
        self.assertIn('g_z80.cyc += 5; banked_halt_steps++', loop)               # a HALT cycle with its wait
        self.assertIn('pending_irq = vdp_irq_asserted();\n        banked_after_step(pending_irq);', loop)
        self.assertNotIn('g_bank[', loop)
        # L1b: the start-of-step call, the state copies shipped with the loop, no hardware advance inside a prefix chain.
        self.assertIn('        SMS_PC(g_z80.pc);\n        smsrecomp_step_begin(prefix_pending);\n', loop)
        self.assertIn('static void state_to_hz(void)', loop)
        self.assertIn('static void state_from_hz(void)', loop)
        self.assertIn('                prefix_pending = 1;\n                continue;\n', loop)
        glue = (ROOT / 'native' / 'msx_machine' / 'msx_glue.inc').read_text(encoding='utf-8')
        for gone in ('#undef SMS_PC', 'fragments_at_step', 'static void state_to_hz'):
            self.assertNotIn(gone, glue)

    def test_the_generator_gets_the_image_the_machine_sees(self):
        image = bytes(range(256)) * 48                                         # 12 KB, plain
        padded = self.tool.padded(image)
        self.assertEqual(len(padded), 0x4000)
        self.assertEqual(padded[:len(image)], image)
        self.assertEqual(set(padded[len(image):]), {0xFF})
        self.assertEqual(self.tool.padded(b'\0' * 0x4000), b'\0' * 0x4000)

    def test_the_comparison_covers_the_whole_state_and_every_frame(self):
        for field in ('af2', 'bc2', 'de2', 'hl2', 'i', 'r', 'im', 'iff2', 'wz', 'frame_trace', 'psg', 'blocks', 'ram_fnv',
                      'vram_fnv', 'audio_fnv', 'cycles', 'interrupts'):
            self.assertIn(field, self.tool.COMPARED)

    def test_the_timing_regression_cartridges(self):
        prefix = self.tool.cartridge_prefix_io()
        self.assertEqual(prefix[0x10:0x12], bytes([0x0E, 0x99]))
        self.assertEqual(prefix[0x14:0x17], bytes([0xDD, 0xED, 0x79]))        # OUT (C),A behind a redundant DD
        self.assertEqual(prefix[0x26:0x28], bytes([0x18, 0xEA]))
        self.assertEqual(0x4028 + (0xEA - 256), 0x4012)
        self.assertEqual(self.tool.cartridge_ei_ex()[0x10:0x15], bytes([0xFB, 0xDD, 0xE3, 0x18, 0xFB]))

    def test_the_glue_defines_what_the_loop_needs(self):
        glue = (ROOT / 'native' / 'msx_machine' / 'msx_glue.inc').read_text(encoding='utf-8')
        for name in ('smsrecomp_region_map', 'smsrecomp_region_generation', 'smsrecomp_step_begin',
                     'hyb_read', 'advance_vdp', 'vdp_irq_asserted', 'sms_dispatch_miss', 'smsrecomp_feedback_at',
                     'smsrecomp_learning_enabled', 'smsrecomp_observe_code', 'smsrecomp_state_service',
                     '#include "msx_banked_loop.inc"'):
            self.assertIn(name, glue)


class RouteTests(unittest.TestCase):
    """msx_routes: the PC Engine's route names and lengths, the default mapping's inputs, a walk that starts quiet."""
    IDENTITY = '0123abcd' * 8

    def test_the_levels_play_the_pc_engines_routes(self):
        from retrorecomp import msx_routes
        names = {level: [(name, frames) for name, frames, _ in msx_routes.routes(self.IDENTITY, frames=3600, level=level)]
                 for level in ('quick', 'standard', 'extended', 'thorough')}
        self.assertEqual(names['quick'], [('play', 3600)])
        self.assertEqual(names['standard'], [('attract', 3600), ('play', 3600)])
        self.assertEqual(names['extended'], [('attract', 3600), ('play', 3600), ('long-1', 18000)])
        self.assertEqual(names['thorough'][-1], ('long-2', 18000))
        self.assertEqual(msx_routes.routes(self.IDENTITY, frames=600, level='standard')[1][1], msx_routes.PLAY_FRAMES)
        self.assertEqual(msx_routes.routes(self.IDENTITY, frames=3600, level='standard')[0][2], '')

    def test_a_script_is_what_the_route_include_reads_in_frame_order(self):
        import re
        from retrorecomp import msx_routes
        text = msx_routes.routes(self.IDENTITY, frames=3600, level='extended', variant=(2, 'RETURN'))[2][2]
        frames = []
        for line in text.splitlines():
            match = re.fullmatch(r'(\d+) key (\d) (\d) ([01])|(\d+) joy 0 ([0-3][0-9A-F])', line)
            self.assertIsNotNone(match, line)
            frames.append(int(match.group(1) or match.group(5)))
        self.assertEqual(frames, sorted(frames))
        self.assertLess(frames[-1], 18000)
        self.assertEqual(text, msx_routes.routes(self.IDENTITY, frames=3600, level='extended', variant=(2, 'RETURN'))[2][2])

    def test_the_start_presses_fire_then_return_and_the_walk_starts_with_directions_only(self):
        from retrorecomp import msx_routes
        events = msx_routes.events(3600, msx_routes.route_seed(self.IDENTITY, 'play'), (2, 'RETURN'))
        self.assertEqual(events[:6], [('key', 480, 8, 0, 1), ('joy', 480, 0, 0x2F), ('key', 486, 8, 0, 0), ('joy', 486, 0, 0x3F),
                                      ('key', 540, 7, 7, 1), ('key', 546, 7, 7, 0)])
        start = msx_routes.walk_start(2)
        quiet = [event for event in events if start <= event[1] < start + msx_routes.QUIET_WALK]
        self.assertTrue(quiet)
        for event in quiet:
            if event[0] == 'joy':
                self.assertEqual(event[3] & 0x10, 0x10, event)      # trigger A stays up
            else:
                self.assertEqual(event[2], 8, event)                 # only the cursor keys
                self.assertNotEqual(event[3], 0, event)              # never SPACE
        self.assertEqual(msx_routes.candidates(3600), [1, 2, 3, 4, 6, (1, 'RETURN'), (2, 'RETURN'), (3, 'RETURN')])
        self.assertEqual(sorted(msx_routes.candidates(3600), key=msx_routes.variant_order)[:2], [1, (1, 'RETURN')])

    def test_a_multi_disk_game_gets_its_next_disks_on_the_long_routes(self):
        from retrorecomp import msx_routes
        self.assertEqual(msx_routes.disk_changes(18000, 1), [])
        self.assertEqual(msx_routes.disk_changes(18000, 3), [('disk', 6000, 1), ('disk', 9000, 2)])
        rows = msx_routes.routes(self.IDENTITY, frames=3600, level='extended', disks=3)
        self.assertNotIn(' disk ', rows[1][2])                       # play: never a disk change
        long_route = rows[2][2].splitlines()
        self.assertIn('6000 disk 1', long_route)
        self.assertIn('9000 disk 2', long_route)
        frames = [int(line.split()[0]) for line in long_route]
        self.assertEqual(frames, sorted(frames))



class QuickStateTests(unittest.TestCase):
    """The MSX's quick states: the shared envelope, the build binding, the damaged copies the conversion feeds the game."""

    def test_the_state_file_uses_the_shared_envelope_with_the_msx_magic(self):
        text = (ROOT / 'native/msx_machine/msx_state_file.inc').read_text(encoding='utf-8')
        self.assertIn('#include "state_envelope.h"', text)
        self.assertIn('"RRMSXST\\0"', text)
        self.assertNotIn('0xEDB88320', text)          # the CRC is the envelope's, not a copy

    def test_the_binding_changes_with_everything_a_state_depends_on(self):
        from types import SimpleNamespace
        from retrorecomp.msx_conversion import state_binding
        guess = SimpleNamespace(mapper='konami', base=0x4000, mirrored=False)
        base = state_binding(b'bios', guess, 'ntsc', 'msx1', 0)
        self.assertEqual(len(base), 32)
        others = [state_binding(b'other', guess, 'ntsc', 'msx1', 0),
                  state_binding(b'bios', SimpleNamespace(mapper='ascii8', base=0x4000, mirrored=False), 'ntsc', 'msx1', 0),
                  state_binding(b'bios', SimpleNamespace(mapper='konami', base=0x8000, mirrored=False), 'ntsc', 'msx1', 0),
                  state_binding(b'bios', SimpleNamespace(mapper='konami', base=0x4000, mirrored=True), 'ntsc', 'msx1', 0),
                  state_binding(b'bios', guess, 'pal', 'msx1', 0), state_binding(b'bios', guess, 'ntsc', 'msx2', 0),
                  state_binding(b'bios', guess, 'ntsc', 'msx2', 512)]
        self.assertEqual(len({base, *others}), len(others) + 1)

    def test_every_field_of_the_header_and_the_binding_is_damaged_once(self):
        from retrorecomp.msx_conversion import damaged_states
        state = bytes(range(256)) * 4
        damaged = damaged_states(state)
        for label, offset in (('magic', 0), ('schema', 8), ('machine', 12), ('identity', 16), ('length', 80), ('crc', 84),
                              ('binding', 88), ('payload', len(state) - 1)):
            changed = [i for i, (a, b) in enumerate(zip(state, damaged[label])) if a != b]
            self.assertEqual(changed, [offset], label)
        self.assertEqual(damaged['empty'], b'')
        self.assertEqual(len(damaged['one-byte-short']), len(state) - 1)


class VectorTests(unittest.TestCase):
    """Gate G10: the independent Z80 vectors through the MSX's own generator expect one wait state per M1 cycle."""

    def test_m1_cycles_by_prefix(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        spec = importlib.util.spec_from_file_location('banked_vector_selftest', ROOT / 'tools' / 'banked_vector_selftest.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = {(0x00, 0x00): 1, (0x3E, 0x12): 1, (0xCB, 0x11): 2, (0xED, 0xB0): 2, (0xDD, 0x21): 2, (0xFD, 0xCB): 2,
                 (0xDD, 0xC9): 2, (0xDD, 0xDD): 1, (0xFD, 0xED): 1}
        for (opcode, following), expected in cases.items():
            self.assertEqual(module.m1_cycles(opcode, following), expected, (hex(opcode), hex(following)))


class SramTests(unittest.TestCase):
    """Gate G7: an ASCII cartridge's battery SRAM, found from the bank values the game writes, kept in a cart_save.c file."""

    def test_the_bit_is_the_lowest_set_one_above_the_bank_number(self):
        from retrorecomp.msx_rom import sram_bit
        self.assertEqual(sram_bit('ascii8', 0x20000, 0x20), 5)          # Xanadu: 16 banks of 8 KiB, bit 5
        self.assertEqual(sram_bit('ascii8', 0x100000, 0x80), 7)         # Royal Blood: bit 7
        self.assertEqual(sram_bit('ascii16', 0x20000, 0x10), 4)         # Hydlide 2: 8 banks of 16 KiB, bit 4
        self.assertEqual(sram_bit('ascii8', 0x20000, 0x30), 4)
        self.assertIsNone(sram_bit('ascii8', 0x20000, 0))
        self.assertIsNone(sram_bit('konami', 0x20000, 0x20))
        self.assertIsNone(sram_bit('ascii8', 0x200000, 0x01))           # no bit at or above 256 banks

    def test_the_runners_take_the_bit_and_the_state_binding_changes_with_it(self):
        from types import SimpleNamespace
        from retrorecomp.msx_conversion import cartridge_bank_high, state_binding
        from retrorecomp.msx_rom import Guess
        self.assertEqual(Guess('ascii8', sram=5).arguments(), ['--mapper', 'ascii8', '--sram-bit', '5'])
        self.assertEqual(Guess('ascii8').arguments(), ['--mapper', 'ascii8'])
        plain = SimpleNamespace(mapper='ascii8', base=0x4000, mirrored=False, sram=None)
        with_sram = SimpleNamespace(mapper='ascii8', base=0x4000, mirrored=False, sram=5)
        self.assertNotEqual(state_binding(b'b', plain, 'ntsc', 'msx1', 0), state_binding(b'b', with_sram, 'ntsc', 'msx1', 0))
        entry = [1, 0, *range(8), 0, 0, 0, 15, 32, 12345, 0x20]
        self.assertEqual(cartridge_bank_high({'blocks': [[0, 0, *range(8), 0, 0, 0, 15, 0, 0, 0], entry]}), 0x20)
        self.assertEqual(cartridge_bank_high({'blocks': []}), 0)

    def test_the_cartridge_writes_sram_only_in_page_2(self):
        text = (ROOT / 'native/msx_machine/msx_cart.c').read_text(encoding='utf-8')
        self.assertEqual(text.count('if (address >= 0x8000 && address < 0xC000 && d->block[address >> 13] == MSX_BLOCK_SRAM)'), 2)
        player = (ROOT / 'native/msx_machine/msx_player.c').read_text(encoding='utf-8')
        self.assertIn('atexit(sram_at_exit)', player)
        self.assertIn('"--sram"', player)


class Msx2OrMsx2PlusTests(unittest.TestCase):
    """Arthur's rule of 13 November 2026 between the MSX2 and the MSX2+, on authored cartridges (no ROM): the folder or the menu
    decides; a file known to be at least MSX2 with nothing saying which goes to the MSX2+; a plain .rom with no hint stays where
    it went before; the hint that decided is kept for the log."""

    @staticmethod
    def cartridge() -> bytes:
        return bytes((0x41, 0x42, 0x10, 0x40)) + bytes(12) + bytes((0xC9,)) + bytes(0x4000 - 17)   # AB, INIT at 4010h: RET

    def place(self, root, folder: str, name: str) -> Path:
        import zipfile
        where = Path(root) / folder if folder else Path(root)
        where.mkdir(parents=True, exist_ok=True)
        path = where / name
        if name.endswith('.zip'):
            with zipfile.ZipFile(path, 'w') as bundle:
                bundle.writestr(Path(name).stem + '.mx2', self.cartridge())
        else:
            path.write_bytes(self.cartridge())
        return path

    def test_each_case(self):
        import tempfile
        from retrorecomp.batch import identify
        from retrorecomp.systems.msx import decided
        cases = (('msx2+', 'game.rom', None, 'msx2plus', 'msx2+ folder'),
                 ('msx2plus', 'game.rom', None, 'msx2plus', 'msx2+ folder'),
                 ('msx2', 'game.rom', None, 'msx2', 'msx2 folder'),
                 ('msx2', 'game.mx2', None, 'msx2', 'msx2 folder'),
                 ('msx2+', 'game.mx2', None, 'msx2plus', 'msx2+ folder'),
                 ('', 'game.mx2', None, 'msx2plus', 'in doubt between MSX2 and MSX2+: MSX2+'),
                 ('', 'game.zip', None, 'msx2plus', 'in doubt between MSX2 and MSX2+: MSX2+'),
                 ('', 'game.mx2', 'msx2', 'msx2', 'chosen in the menu'),
                 ('', 'game.rom', 'msx2plus', 'msx2plus', 'chosen in the menu'),
                 ('msx2', 'game.mx2', 'msx2plus', 'msx2plus', 'chosen in the menu'),
                 ('', 'game.rom', None, 'msx', None))                         # a plain .rom with no hint: the MSX1's, as before
        for folder, name, selected, system, hint in cases:
            with self.subTest(folder=folder, name=name, selected=selected), tempfile.TemporaryDirectory() as root:
                path = self.place(root, folder, name)
                item = identify(path, selected)
                self.assertEqual(item.system, system, item.error)
                self.assertEqual(decided(path), hint)


class Msx2PlusDiskInputTests(unittest.TestCase):
    """MSX2+ disks as the converter reads them (msx_disk.py) and identifies them: a .dsk, a set grouped by
    rom_sources.disk_sets into an M3U marked with the machine, sizes checked, an identity for the set."""

    def test_a_disk_a_set_and_what_is_refused(self):
        import tempfile
        from retrorecomp.batch import identify
        from retrorecomp.msx_disk import read_disks
        from retrorecomp.rom_sources import disk_sets
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            one = root / 'Game (Disk 1 of 2).dsk'
            two = root / 'Game (Disk 2 of 2).dsk'
            one.write_bytes(bytes(737280))
            two.write_bytes(bytes([1]) * 368640)
            single = read_disks(one)
            self.assertEqual((single.size, len(single.disks)), (737280, 1))
            sets = disk_sets([two, one], root / 'sets')
            self.assertEqual(sets.grouped, 1)
            playlist = sets.paths[0]
            self.assertIn('# Retro-Recomp system: msx2plus', playlist.read_text(encoding='utf-8'))
            both = read_disks(playlist)
            self.assertEqual([p.name for p in both.disks], [one.name, two.name])
            self.assertNotEqual(both.sha256, single.sha256)
            self.assertEqual(identify(playlist).system, 'msx2plus')
            self.assertEqual(identify(one).system, 'msx2plus')
            bad = root / 'bad.dsk'
            bad.write_bytes(bytes(1000))
            with self.assertRaises(ValueError):
                read_disks(bad)

    def test_the_authored_write_disk_is_a_disk_the_converter_reads(self):
        """tools/msx_write_disk.py, the disk that proves the write path (no game data): 720 KiB, an MSX-DOS boot sector with
        its BPB, a boot program that hooks H.STKE and calls PHYDIO with the carry set, the two FATs marked F9h."""
        import tempfile
        from retrorecomp.msx_disk import read_disks
        spec = importlib.util.spec_from_file_location('msx_write_disk', ROOT / 'tools' / 'msx_write_disk.py')
        writer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(writer)
        disk = writer.image()
        self.assertEqual(len(disk), 737280)
        self.assertEqual(disk[0], 0xEB)
        self.assertEqual(int.from_bytes(disk[11:13], 'little'), 512)
        self.assertEqual(int.from_bytes(disk[19:21], 'little'), 1440)
        self.assertEqual(disk[21], 0xF9)
        code = writer.boot_code()
        self.assertEqual(disk[0x1E:0x1E + len(code)], code)
        self.assertIn(bytes((0x22, 0xDB, 0xFE)), code)                 # the hook's address into H.STKE
        self.assertIn(bytes((0x37, 0xCD, 0x44, 0x01)), code)           # SCF / CALL PHYDIO: a write
        for fat in (1, 4):
            self.assertEqual(disk[fat * 512:fat * 512 + 3], bytes((0xF9, 0xFF, 0xFF)))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'write.dsk'
            path.write_bytes(disk)
            self.assertEqual(read_disks(path).images, (disk,))


class ReportTests(unittest.TestCase):
    """Gate G2: the MSX's rows give the common report v2 its counts, its devices and its route warnings."""

    def test_a_final_row_gives_the_main_cpu_its_counts(self):
        from retrorecomp import report_schema
        row = {'name': 'play', 'scenario': 'play', 'frames': 3600, 'native_steps': 1000, 'interpreted_steps': 7,
               'native_entries': 1000, 'interpreted_opcodes': 7, 'interpreter_cycles': 40, 'interpreter_percent': 0.7}
        scenario = report_schema._main_scenario('msx', row)
        self.assertEqual((scenario['name'], scenario['native'], scenario['interpreted']), ('play', 1000, 7))
        self.assertEqual(scenario['cycles']['interpreted'], 40)
        self.assertTrue(report_schema._fallback_state([scenario]))

    def test_the_writer_names_its_counts_as_the_reader_reads_them(self):
        text = (ROOT / 'retrorecomp' / 'msx_conversion.py').read_text(encoding='utf-8')
        self.assertIn("'native_entries': native['native_steps'], 'interpreted_opcodes': native['fallback_steps']", text)
        self.assertIn("'hardware_devices': hardware_devices(guess, msx2, plus, len(disks.disks) if disks is not None else 0)", text)

    def test_the_devices_are_c_models_with_no_counter(self):
        from types import SimpleNamespace
        from retrorecomp import report_schema
        from retrorecomp.msx_conversion import hardware_devices
        units = hardware_devices(SimpleNamespace(mapper='konami-scc', base=0x4000, mirrored=False, reason='probe'), True)
        self.assertEqual([(u['id'], u['kind']) for u in units],
                         [('konami-scc', 'cartridge_mapper'), ('v9938', 'video_unit'), ('ay-3-8910', 'audio_unit'), ('scc', 'audio_unit')])
        self.assertEqual(len(report_schema._hardware_devices({'hardware_devices': units})), 4)
        plain = hardware_devices(SimpleNamespace(mapper='plain', base=0x4000, mirrored=True, reason='size'), False)
        self.assertEqual([u['id'] for u in plain], ['plain', 'tms9918a', 'ay-3-8910'])
        disk = hardware_devices(SimpleNamespace(mapper='plain', base=0x4000, mirrored=False, reason='no cartridge: a disk game'),
                                True, True, 2)
        self.assertEqual([(u['id'], u['kind']) for u in disk],
                         [('disk-interface', 'cartridge_mapper'), ('v9958', 'video_unit'), ('ay-3-8910', 'audio_unit')])
        self.assertEqual(disk[0]['details']['disks'], 2)
        self.assertEqual(len(report_schema._hardware_devices({'hardware_devices': disk})), 3)
        for unit in units + plain + disk:
            self.assertFalse(unit['details']['hardware_fidelity_validated'])

    def test_a_route_that_stops_early_is_named(self):
        from retrorecomp.msx_conversion import route_warnings
        rows = [{'scenario': 'play', 'liveness': {'frames': 3600, 'last_picture_change_frame': 100}},
                {'scenario': 'long-1', 'liveness': {'frames': 18000, 'last_picture_change_frame': 17999}}]
        self.assertEqual(route_warnings(rows), ['play: the picture stopped changing at frame 100 of 3600'])


if __name__ == '__main__':
    unittest.main()
