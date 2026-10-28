"""Backward compatibility is owed to the previous release only (decision of 28 October 2026).

In the tree of 1.6.0 nothing is listed for a previous release: `LEGACY_GAME_STAMPS` is empty and no build writes a
`RR16_STATE_COMPAT_ABI` key. The mechanisms stay, and the tests below drive them with synthetic values: the release that
follows 1.6.0 adds the entries of 1.6.0 (and only those) and replaces them at each release after.
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


class LegacyStampTests(unittest.TestCase):
    def test_the_table_lists_no_release_in_the_tree_of_1_6_0(self):
        self.assertEqual(inputs.LEGACY_GAME_STAMPS, {})
        for system in sorted(inputs.SYSTEMS):
            self.assertEqual(inputs.legacy_game_stamps(system), (), system)
        self.assertEqual(inputs.legacy_game_stamps('unknown'), ())

    def test_entries_of_the_previous_release_are_wellformed_and_never_the_current_stamp(self):
        # What a release adds: a 64-digit game stamp per listed console, never today's.
        for system in sorted(inputs.SYSTEMS):
            with patch.dict(inputs.LEGACY_GAME_STAMPS, {system: ('1' * 64,)}):
                stamps = inputs.legacy_game_stamps(system)
            self.assertEqual(stamps, ('1' * 64,))
            self.assertRegex(stamps[0], r'^[0-9a-f]{64}$')
            self.assertNotEqual(stamps[0], inputs.role_stamps(system)['game'])

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
    """The mechanism for the previous release: a receipt whose game part is listed stays upgradable on that console,
    whatever today's game stamp is; any other game part is converted in full. The listed stamp here is synthetic."""

    def parts(self, system, game_stamp=None):
        from retrorecomp import freshness
        item = SimpleNamespace(system=system, path=Path('game.bin'), sha256='e' * 64, title='Game', cover=None)
        real = inputs.role_stamps
        stamps = (lambda name: {**real(name), 'game': game_stamp}) if game_stamp else real
        with patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}), \
                patch('retrorecomp.paths.selected_bios_path', return_value=Path('neogeo.zip')), \
                patch('retrorecomp.compilation_inputs.role_stamps', side_effect=stamps):
            return item, freshness.request_parts(item, {'use_cover': False})

    def receipt(self, folder, item, game, release='1.6.0', schema=3):
        from retrorecomp.freshness import digest
        target = Path(folder) / 'Game'
        target.write_bytes(f'export written by {release}'.encode())
        report = {'version': release, 'rom': {'sha256': item.sha256}, 'executable': target.name,
                  'native_validation': {'passed': True},
                  'export_receipt': {'schema': schema, 'request': f'request-{release}', 'game': game,
                                     'host': f'host-{release}', 'sha256': digest(target)}}
        path = Path(folder) / 'conversion-report.json'
        path.write_text(json.dumps(report), encoding='utf-8')
        return target, path

    def test_a_listed_game_part_is_upgraded_not_reconverted_and_an_unlisted_one_is_converted_in_full(self):
        from retrorecomp import freshness
        # The X68000 request needs real disks and firmware: its mechanism is the same one.
        for system in sorted(inputs.SYSTEMS - {'x68'}):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder, \
                    patch.dict(inputs.LEGACY_GAME_STAMPS, {system: ('synthetic-previous-release-' + system,)}):
                item, parts = self.parts(system)
                self.assertEqual(len(parts['legacy_games']), 1)
                self.assertNotIn(parts['game'], parts['legacy_games'])
                # Independent of today's game stamp: the listed stamp is the frozen one.
                self.assertEqual(self.parts(system, 'game-stamp-of-another-day')[1]['legacy_games'],
                                 parts['legacy_games'])
                with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                    target, path = self.receipt(folder, item, parts['legacy_games'][0])
                    self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                    previous = freshness.upgradable(item, target, path, parts, print)
                    self.assertEqual(previous['legacy_release'], '1.6.0')
                    self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.0')
                    # Any other game part (an older release, other code) is converted in full.
                    target, path = self.receipt(folder, item, 'f' * 64)
                    self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_nothing_is_upgraded_from_a_release_the_table_does_not_list(self):
        from retrorecomp import freshness
        with tempfile.TemporaryDirectory() as folder:
            item, parts = self.parts('sms')
            self.assertEqual(parts['legacy_games'], [])
            with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                target, path = self.receipt(folder, item, 'f' * 64, '1.5.6')
                self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_only_the_receipt_this_release_writes_is_current(self):
        # Receipts of schema 1 and 2 (releases before 1.6.0) are never current, even for the very same request.
        from retrorecomp import freshness
        with tempfile.TemporaryDirectory() as folder, patch('retrorecomp.freshness._no_new_hints', return_value=True):
            item, parts = self.parts('sms')
            for schema, expected in ((3, True), (2, False), (1, False)):
                target, path = self.receipt(folder, item, parts['game'], schema=schema)
                report = json.loads(path.read_text(encoding='utf-8'))
                report['export_receipt']['request'] = parts['request']
                path.write_text(json.dumps(report), encoding='utf-8')
                found = freshness.current(item, target, path, parts['request'], print)
                self.assertEqual(found is not None, expected, schema)


@unittest.skipUnless(os.name == 'nt', 'Windows state compatibility lines')
class StateCompatibilityTests(unittest.TestCase):
    def sixteen_bit_config(self, system):
        import importlib
        from retrorecomp import console16_state
        from retrorecomp.console16 import REPOSITORIES
        for module in ('snes_timing', 'snes_video', 'snes_cart', 'snes_dma', 'snes_bus', 'snes_ppu_bus', 'snes_chips'):
            importlib.import_module('retrorecomp.' + module)
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / ('retro_md_game.h' if system == 'md' else 'retro_snes_game.h')).write_text('#define X 1' + chr(10))
            console16_state.write_config(project, SimpleNamespace(sha256='d' * 64), system, 'Test', REPOSITORIES)
            return (project / 'retro16_state_config.h').read_text(encoding='ascii')

    def test_no_state_key_of_an_earlier_release_is_accepted_by_any_console(self):
        from retrorecomp import cps1_build, neogeo_build
        with patch('retrorecomp.neogeo.parse_neo', return_value=SimpleNamespace(sha256='a' * 64)), \
                patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}):
            texts = {'ng': neogeo_build.state_config(Path('cartridge.neo'), Path('neogeo.zip'), 'Test')}
        texts['cps1'] = cps1_build.state_config(SimpleNamespace(sha256='c' * 64), 'Test')
        texts['md'] = self.sixteen_bit_config('md')
        texts['snes'] = self.sixteen_bit_config('snes')
        for system, text in texts.items():
            self.assertNotIn('RR16_STATE_COMPAT_ABI', text, system)
            self.assertRegex(text, r'#define RR16_STATE_ABI "[0-9a-f]{64}"', system)

    def test_the_state_key_constants_of_earlier_releases_are_gone(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        for module in (console16_state, cps1_build, neogeo_build):
            for name in dir(module):
                self.assertNotRegex(name, r'STATE_ABI_\d', (module.__name__, name))

    def test_the_shared_16_bit_state_loader_accepts_the_compatibility_key_a_build_defines(self):
        loader = (ASSETS / 'native/console16_state.c').read_text(encoding='utf-8')
        self.assertRegex(loader, r'#ifdef RR16_STATE_COMPAT_ABI\b')


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
