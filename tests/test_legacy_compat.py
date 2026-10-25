"""Exports of release 1.4.1 stay upgradable, and their quick states stay readable.

The 1.4.1 values below were computed from the v1.4.1 tag and found, byte for
byte, in executables and receipts written by the released Retro-Recomp.exe.
"""
import json
import os
import re
import tempfile
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


class PackingBuildRoleTests(unittest.TestCase):
    """Packing (UPX) is how a game is built: changing it, as Linux compression did
    in release 1.5.0, rebuilds exports from the paths already learned."""

    def test_packing_is_a_build_input_of_every_console(self):
        self.assertEqual(inputs.role('retrorecomp.packing'), 'build')
        self.assertEqual(inputs.BUILD_MODULES, frozenset(('toolchain', 'packing')))
        for system in sorted(inputs.SYSTEMS):
            self.assertIn('retrorecomp.packing', dict(inputs.input_fingerprints(system)), system)

    def test_a_packing_change_changes_no_game_or_host_stamp_on_any_console(self):
        for system in sorted(inputs.SYSTEMS):
            with patch.object(inputs, '_code_digest', side_effect=lambda name, *a: 'pack-v1'):
                before = inputs.role_stamps(system)
            with patch.object(inputs, '_code_digest',
                              side_effect=lambda name, *a: 'pack-v2' if name == 'retrorecomp.packing' else 'pack-v1'):
                after = inputs.role_stamps(system)
            self.assertNotEqual(before['build'], after['build'], system)
            self.assertEqual((before['game'], before['host']), (after['game'], after['host']), system)


class LegacyReceiptTests(unittest.TestCase):
    """A receipt written by release 1.4.1 stays upgradable on each listed console,
    whatever today's game stamp is (it changed when packing became a build input)."""

    def parts(self, system, game_stamp=None):
        from retrorecomp import freshness
        item = SimpleNamespace(system=system, path=Path('game.bin'), sha256='e' * 64, title='Game', cover=None)
        real = inputs.role_stamps
        stamps = (lambda name: {**real(name), 'game': game_stamp}) if game_stamp else real
        with patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}),                 patch('retrorecomp.paths.selected_bios_path', return_value=Path('neogeo.zip')),                 patch('retrorecomp.compilation_inputs.role_stamps', side_effect=stamps):
            return item, freshness.request_parts(item, {'use_cover': False})

    def receipt(self, folder, item, game):
        from retrorecomp.freshness import digest
        target = Path(folder) / 'Game'
        target.write_bytes(b'export written by 1.4.1')
        report = {'version': '1.4.1', 'rom': {'sha256': item.sha256}, 'executable': target.name,
                  'native_validation': {'passed': True},
                  'export_receipt': {'schema': 3, 'request': 'request-1.4.1', 'game': game,
                                     'host': 'host-1.4.1', 'sha256': digest(target)}}
        path = Path(folder) / 'conversion-report.json'
        path.write_text(json.dumps(report), encoding='utf-8')
        return target, path

    def test_exports_of_release_141_are_upgraded_not_reconverted_on_each_listed_console(self):
        from retrorecomp import freshness
        for system, stamps in sorted(inputs.LEGACY_GAME_STAMPS.items()):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                item, parts = self.parts(system)
                self.assertEqual(len(parts['legacy_games']), len(stamps))
                self.assertNotIn(parts['game'], parts['legacy_games'])
                # Independent of today's game stamp: the frozen 1.4.1 stamp is used.
                self.assertEqual(self.parts(system, 'game-stamp-before-packing-moved')[1]['legacy_games'],
                                 parts['legacy_games'])
                with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                    target, path = self.receipt(folder, item, parts['legacy_games'][0])
                    self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                    previous = freshness.upgradable(item, target, path, parts, print)
                    self.assertEqual(previous['legacy_release'], '1.4.1')
                    self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.4.1')
                    # Any other game part (another release, other code) is converted in full.
                    target, path = self.receipt(folder, item, 'f' * 64)
                    self.assertIsNone(freshness.upgradable(item, target, path, parts, print))


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

    def sixteen_bit_config(self, system):
        import importlib
        import tempfile
        from retrorecomp import console16_state
        from retrorecomp.console16 import REPOSITORIES
        for module in ('snes_timing', 'snes_video', 'snes_cart', 'snes_dma', 'snes_bus', 'snes_ppu_bus', 'snes_chips'):
            importlib.import_module('retrorecomp.' + module)
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / ('retro_md_game.h' if system == 'md' else 'retro_snes_game.h')).write_text('#define X 1' + chr(10))
            console16_state.write_config(project, SimpleNamespace(sha256='d' * 64), system, 'Test', REPOSITORIES)
            return (project / 'retro16_state_config.h').read_text(encoding='ascii')

    def test_mega_drive_states_of_release_141_are_accepted(self):
        from retrorecomp.console16_state import MD_STATE_ABI_141
        text = self.sixteen_bit_config('md')
        self.assertIn(f'#define RR16_STATE_COMPAT_ABI_23 "{MD_STATE_ABI_141}"', text)
        self.assertEqual(MD_STATE_ABI_141, '58e2c720c4d5988484fb970ca2a0d0b9b722a5023d5806cd58da56d67ea96164')
        self.assertNotIn(f'RR16_STATE_ABI "{MD_STATE_ABI_141}"', text)

    def test_super_nintendo_states_of_release_141_are_accepted(self):
        from retrorecomp.console16_state import SNES_STATE_ABI_141
        text = self.sixteen_bit_config('snes')
        self.assertIn(f'#define RR16_STATE_COMPAT_ABI "{SNES_STATE_ABI_141}"', text)
        self.assertEqual(SNES_STATE_ABI_141, '396976503cf0a7478e85bd818d8ec5a1ccf5dab95d306550b1fd5c73ebbd0d1b')

    def test_the_shared_16_bit_state_loader_knows_the_compatibility_macros_used(self):
        loader = (ASSETS / 'native/console16_state.c').read_text(encoding='utf-8')
        for macro in ('RR16_STATE_COMPAT_ABI', 'RR16_STATE_COMPAT_ABI_3', 'RR16_STATE_COMPAT_ABI_23'):
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
