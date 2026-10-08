"""Peripheral catalogue, identity guard and checked hardware-hook tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from smsrecomp.core import ConversionError
from smsrecomp.guns16 import gun_game, write_header
from smsrecomp.gun16_runtime import replace
from smsrecomp.metadata import game_metadata
from smsrecomp.supernintendo import profile_for, write_profile
from smsrecomp.console16 import reference_differences, MD_AUDIO_FIELDS


class Gun16Tests(unittest.TestCase):
    def test_catalogue_is_console_scoped_and_identity_has_priority(self):
        self.assertEqual(gun_game('md', 0x936B85F7, 'Wrong.zip').device, 'menacer')
        self.assertEqual(gun_game('md', 0, 'Lethal Enforcers II - Gun Fighters (Europe).zip').x_offset, 24)
        self.assertEqual(gun_game('snes', 0, "Yoshi's Safari (USA).sfc").device, 'super_scope')
        self.assertEqual(gun_game('snes', 0, 'Lethal Enforcers (USA).sfc').device, 'justifier')
        self.assertIsNone(gun_game('md', 0xB141EA99, 'Super Scope 6.zip'))
        self.assertIsNone(gun_game('snes', 0, 'Super Mario World.sfc'))

    def test_gun_title_does_not_authorize_a_foreign_cpu_profile(self):
        rom = SimpleNamespace(sha256='0' * 64, path=Path('Super Scope 6.sfc'))
        with self.assertRaises(ConversionError):
            profile_for(rom)

    def test_scope_uses_own_identity_and_no_smw_function_code(self):
        sha = '7a8ffaf8bb549b400ec2f0bda9f3c0dbf5852c38618cdb21cd783c368383e2c7'
        rom = SimpleNamespace(sha256=sha, path=Path('Unknown.sfc'), system_id='snes',
            crc32=0xB141EA99, data=bytes(1048576), mapping='lorom', standard='ntsc')
        with TemporaryDirectory() as temp:
            root = Path(temp)
            write_header(root, rom); write_profile(root, rom, 'Super Scope 6')
            self.assertIn('#define RR16_GUN 3', (root / 'retro_gun_game.h').read_text())
            header = (root / 'retro_snes_game.h').read_text()
            self.assertIn('#define RR_SN_SMW 0', header)
            self.assertIn('1048576', header)
            self.assertEqual([p.name for p in (root / 'generated').iterdir()], ['instruction_program.c'])
            self.assertIn(sha, (root / 'generated/instruction_program.c').read_text())
        rom.standard = 'pal'
        with self.assertRaises(ConversionError):
            profile_for(rom)

    def test_cpu_driven_bus_hook_is_not_guessed_after_dependency_drift(self):
        self.assertEqual(replace('abc', 'b', 'd'), 'adc')
        for text in ('ac', 'abbc'):
            with self.assertRaises(ConversionError):
                replace(text, 'b', 'd')

    def test_explorer_metadata_names_the_actual_gun(self):
        for system, device, label in (('md','menacer','Menacer'), ('md','justifier','Justifier'),
                                      ('snes','super_scope','Super Scope')):
            self.assertIn(label, game_metadata('Game', False, 'ntsc', system, gun_device=device)['Controls'])
        with self.assertRaises(ValueError):
            game_metadata('Game', False, 'ntsc', 'snes', gun_device='menacer')

    def test_reference_gate_detects_missing_or_changed_gun_state(self):
        fields = MD_AUDIO_FIELDS + ('console_version','cpu_sr','cpu_usp','cpu_ssp','cpu_stopped','frame_hash','sequence_hash','cpu_hash','ram_hash','vram_hash','cram_hash',
            'cpu_pc','vsram_hash','vdp_register_hash','gun_kind','gun_light_hits',
            'gun_interrupts','gun_button_reads','gun_latched_hv','gun_buttons_latched',
            'gun_button_packets','gun_trigger_packets','gun_port_control','gun_external_irq_enabled')
        native = dict.fromkeys(fields, 1) | {'native_entries':100, 'interpreted_opcodes':0,
            'audio_native_opcodes':100, 'audio_interpreted_opcodes':0,
            'audio_native_cycles':1000, 'audio_interpreted_cycles':0}
        reference = native | {'native_entries':0, 'interpreted_opcodes':100,
            'audio_native_opcodes':0, 'audio_interpreted_opcodes':100,
            'audio_native_cycles':0, 'audio_interpreted_cycles':1000}
        self.assertEqual(reference_differences('md',native,reference), [])
        self.assertIn('gun_latched_hv', reference_differences('md',native, reference | {'gun_latched_hv':2}))
        reference.pop('gun_light_hits')
        self.assertIn('gun_light_hits',reference_differences('md',native,reference))


if __name__ == '__main__':
    unittest.main()
