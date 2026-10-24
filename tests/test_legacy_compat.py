"""Exports of release 1.4.1 stay upgradable, and their quick states stay readable.

The 1.4.1 values below were computed from the v1.4.1 tag and found, byte for
byte, in executables and receipts written by the released Retro-Recomp.exe.
"""
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import compilation_inputs as inputs
from retrorecomp.paths import ASSETS

NEO_GEO_ABI_141 = 'b3305fddf7b7c0b961d6abb04f401e0a7ca8d55974dd13c8b05f2fda60df7e5e'
CPS1_ABI_141 = 'd92d265ba352da2602ee7a74492a02f6397477a131b79afab1ef42fa66f1d557'


class LegacyStampTests(unittest.TestCase):
    def test_listed_stamps_are_wellformed_and_never_the_current_one(self):
        self.assertTrue(inputs.LEGACY_GAME_STAMPS)
        for system, stamps in inputs.LEGACY_GAME_STAMPS.items():
            self.assertIn(system, inputs.SYSTEMS)
            for stamp in stamps:
                self.assertRegex(stamp, r'^[0-9a-f]{64}$')
                self.assertNotEqual(stamp, inputs.role_stamps(system)['game'],
                                    'a stale list must not shadow the current game part')
        # Only consoles whose 1.4.1 game part was reproduced from a real receipt are listed.
        self.assertEqual(sorted(inputs.LEGACY_GAME_STAMPS), ['cps1', 'gb', 'gg', 'md', 'nes', 'ng', 'sms', 'snes'])
        self.assertEqual(inputs.legacy_game_stamps('x68'), ())
        self.assertEqual(inputs.legacy_game_stamps('unknown'), ())

    def test_toolchain_choice_is_a_build_input_and_changes_no_game_or_host_stamp(self):
        self.assertEqual(inputs.role('retrorecomp.toolchain'), 'build')
        with patch.object(inputs, '_code_digest', side_effect=lambda name, *a: 'tools-v1'):
            before = inputs.role_stamps('sms')
        with patch.object(inputs, '_code_digest', side_effect=lambda name, *a: 'tools-v2' if name == 'retrorecomp.toolchain' else 'tools-v1'):
            after = inputs.role_stamps('sms')
        self.assertNotEqual(before['build'], after['build'])
        self.assertEqual((before['game'], before['host']), (after['game'], after['host']))


@unittest.skipUnless(os.name == 'nt', 'Windows state compatibility lines')
class StateCompatibilityTests(unittest.TestCase):
    def test_neo_geo_states_of_release_141_are_accepted(self):
        from retrorecomp import neogeo_build
        cartridge = SimpleNamespace(sha256='a' * 64)
        firmware = {'sha256': 'b' * 64}
        with patch('retrorecomp.neogeo.parse_neo', return_value=cartridge), \
                patch('retrorecomp.neogeo.validate_bios', return_value=firmware):
            text = neogeo_build.state_config(Path('cartridge.neo'), Path('neogeo.zip'), 'Test')
        self.assertIn(f'#define RR16_STATE_COMPAT_ABI_3 "{NEO_GEO_ABI_141}"', text)
        current = re.search(r'#define RR16_STATE_ABI "([0-9a-f]{64})"', text).group(1)
        self.assertNotEqual(current, NEO_GEO_ABI_141)

    def test_cps1_states_of_release_141_are_accepted(self):
        from retrorecomp import cps1_build
        text = cps1_build.state_config(SimpleNamespace(sha256='c' * 64), 'Test')
        self.assertIn(f'#define RR16_STATE_COMPAT_ABI "{CPS1_ABI_141}"', text)
        current = re.search(r'#define RR16_STATE_ABI "([0-9a-f]{64})"', text).group(1)
        self.assertNotEqual(current, CPS1_ABI_141)

    def test_the_shared_16_bit_state_loader_knows_the_compatibility_macros_used(self):
        loader = (ASSETS / 'native/console16_state.c').read_text(encoding='utf-8')
        for macro in ('RR16_STATE_COMPAT_ABI', 'RR16_STATE_COMPAT_ABI_3'):
            self.assertRegex(loader, rf'#ifdef {macro}\b')


class StateLayoutGuardTests(unittest.TestCase):
    """States are written field by field. The same field must have the same size
    with Visual Studio and with clang (MinGW-w64): long double is 8 bytes with
    the first and 16 with the second, so no saved state may use it. The state
    files of both builds were also compared byte for byte in size and replayed
    across builds (tools/neogeo_state_cross.py, state16_cross.py, nes_state_cross.py)."""
    FILES = ('neogeo_state.c', 'neogeo_state_validate.c', 'neogeo_lspc_state.inc', 'neogeo_ym_state.inc',
             'cps1_machine.c', 'cps1_oki.c', 'cps1_opm.cpp', 'console16_state.c', 'console16_state.h',
             'nes_state.c', 'nes_machine_state.inc', 'nes_mapper_state.inc', 'md_portable_state.inc')

    def test_no_saved_state_uses_a_type_whose_size_depends_on_the_compiler(self):
        for name in self.FILES:
            path = ASSETS / 'native' / name
            if not path.is_file():
                continue
            text = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(encoding='utf-8', errors='replace'), flags=re.S)
            self.assertNotRegex(text, r'\blong\s+double\b', name)


if __name__ == '__main__':
    unittest.main()
