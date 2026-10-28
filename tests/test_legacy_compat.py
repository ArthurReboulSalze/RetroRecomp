"""Backward compatibility is owed to the previous release only (decision of 28 October 2026).

The tree of 1.6.0 listed nothing for a previous release. The tree of 1.6.1 listed the previous release, 1.6.0, and
only it. The tree of 1.6.2 lists 1.6.1 and only it: its game stamps in `LEGACY_GAME_STAMPS` (the eight consoles but the
X68000; the 1.6.0 stamps are dropped) and its quick-state keys as `RR16_STATE_COMPAT_ABI` (Mega Drive, Super Nintendo,
Neo Geo and CPS-1, Windows; the 1.6.0 keys are dropped). The values below are frozen: they were computed from the
`v1.6.0` and `v1.6.1` tags with Python 3.14.5 (docs/UPGRADES.md, "Exports of 1.6.1 in 1.6.2"; docs/GAME_STATES.md,
"States written by release 1.6.0" and "States written by release 1.6.1"). The release that follows 1.6.2 replaces the
game stamps and the state keys with those of 1.6.2; the mechanisms are driven here with synthetic values as well.
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

# Game stamps of release 1.6.1, from the v1.6.1 tag (`git archive`, `role_stamps(system)['game']`; the same method
# gives the 1.6.0 stamps again, byte for byte). Between 1.6.1 and 1.6.2 no listed input changed what a conversion
# generates (docs/UPGRADES.md). The X68000 is not listed: its request carries an SDK stamp derived from the game stamp
# that the mechanism does not recompute, so its 1.6.1 stamp (below) is recorded and must stay unlisted.
GAME_STAMPS_161 = {
    'cps1': 'fb7d9315c9637c103aa81f259712524d9bf29b33e6e9d920ce8f4b5ad83f92db',
    'gb': 'e5fc74915974ec27ab05bc9c9ae5ecea03050316ed39d9842b11485d2ffe1e09',
    'gg': 'f860d65789176fa85ad7c7880c766da1754ea98fedac4f50edcf77d664f799cd',
    'md': '2effe9f498891007f54fadc029a8f55f625ed414c73894fe2cbde5684dcfd188',
    'nes': 'a8b871f2ab08ffc44633cc562b942fdac9a3cc4d65a7706030b714abf96fa017',
    'ng': '1d1a5224f6c89a58ff7f1f79d807918a1c4f1295e0ae3543a253a4d884d2959b',
    'sms': 'c4589fe7b51645c8fc779fb2511d3dc9c793fa855b5c910089bbdf0cb3dea68d',
    'snes': '463da5c5cf464363bbc887e524a1933288e9f94c7d748cae624748dc172b6ae4',
}
X68_GAME_STAMP_161_NOT_LISTED = '428f2fc57bfbd0d11cf3e1bbd7977a967628bc328728746dc784cea0c39241ca'
# The same release's Linux converter, built with Python 3.13 (code is fingerprinted as bytecode): the stamps the published
# Linux 1.6.1 converter gives with its own `_compilation-inputs`, equal to git archive v1.6.1 under Python 3.13.
GAME_STAMPS_161_LINUX = {
    'cps1': '5a47af5e465134ab8fa927cd3389c7bbbcc12d61ec02f18461de63e89ae175fb',
    'gb': 'f194a7e52b26bddadcf02362d4921774ec75f8c65629724286c3ad5c716322d5',
    'gg': '2e805515d5cf5e080ea5f9ac10d97759bcf22b6976b565b2a73d599f2d82d736',
    'md': '47c10b4b7a49bd24c34cee183442cdb5344c578657f5b3ed83106794a9944db9',
    'nes': '480b9aea940b6c5fe11adcf226dcf6fc15fb5df2703080c8c62ef71a4efba5c2',
    'ng': 'cc24dd0a1115f37f2053188a478f8592bb2e42765b6e07aacd8f8d4bf7427e4f',
    'sms': '1a3b71b7a75d91e2ed859656671c7471a31d9ce4527f2f15170146e961a71346',
    'snes': '0a62f3c2061a22948f8442c8b84faee71f0925772536f8a7d30d4ae43bef63d9',
}
X68_GAME_STAMP_161_LINUX_NOT_LISTED = '0aea38e48dea2196c46904a2f9a2bbb8c9cf565ad455cf59969e7c0e7b8d3f71'
# Game stamps of release 1.6.0 (the table of 1.6.1 listed them): owed to nobody any more.
GAME_STAMPS_160_REMOVED = {
    'cps1': '699f824303f77ebbf4583bd7c9cc1ee1aa7c167391e247e0010f7fbc72ec5b95',
    'gb': 'c36134ebfc832440005280367b64225bc09b486c3fff560d0f8a1376110712da',
    'gg': '47c60b9a2034948c0f2c31e8e3a209a368f8ef45490cc6047f73cfb882c637be',
    'md': '4db8a6f2397ab51d383166778c227e45cadcd3806bd7bf5aaf7e965267744b75',
    'nes': '511451fc62f41db3f8dee6f57e1d2b2d2623cf8a0171482bd73bcb2bb595432b',
    'ng': '41577b77c4e78dd15d8644092591e5852efc1c96e9fe5be1dde2bbca8b1fcb61',
    'sms': '19b8bd2a33d49f8b2d08e2335e7ee5d96178347c941d3da73800b0bb61551732',
    'snes': 'cccb132e2e23df78340770cd1c0c562d32645d732e97aa15c4e853e66c06af36',
}
X68_GAME_STAMP_160_NOT_LISTED = '7de0d3b5731e81f2df6a705a502e165d07349423641dcc2454ce1de9392a6f36'
# Game stamps of release 1.5.6 (the table of 1.6.0 listed them): owed to nobody for two releases now.
GAME_STAMPS_156_REMOVED = {
    'cps1': '187c9db92db22e872d352e6c5895640c414849ba6e50b07db0b06c4e703738fb',
    'gb': 'c8a90b01e99b68da0f9796d109d7f161e9c848d2f8100651731c6dfe3f56f806',
    'gg': '08950dbb0d3cce0475b17c309d17f72c0b65ed02e9e99cf1b9a4138afe50747b',
    'md': 'd9bd59e01303a56a92e619aef54f67203fa7d0b3a7cb3211addc0562d6f9aa18',
    'nes': 'c98420ac1dfde068026e7fb72da97844714b6a31e6536cca93ff012add168715',
    'sms': '3897d8b37cffe8a438fd12cb7b522c9fac5222c5b94c9eb045457ef557e2fa7b',
}
# Quick-state keys of release 1.6.1 (Windows), from the v1.6.1 tag; the same code gives the documented 1.5.6 keys from
# the v1.5.6 tag. The Super Nintendo key is the same in 1.6.0 and 1.6.1 (SNES_STATE_ABI_160 below): 1.6.1 needed no line
# for it, 1.6.2 lists it for the first time because the runtime catalogue moved the key.
MD_STATE_ABI_161 = 'fb6d191a2b8c3975e4a69560fb204ad1e79c8726bb55f448e15e2d201550c959'
SNES_STATE_ABI_161 = '366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1'
NEO_GEO_STATE_ABI_161 = '5c25722def19e560b4cbce7c7424d3c2f3317a2a91f6d3d3f184f16a46fdc474'
CPS1_STATE_ABI_161 = 'f745f993a28521fa17dbe84332964b677a3ab35f5bbb77b7f7c1fcb95cd902ee'
# Keys of release 1.6.0 (the previous release of the tree of 1.6.1): owed to nobody any more. The Super Nintendo one is
# also its 1.6.1 key (the key did not move), so it stays accepted and is not in this tuple.
SNES_STATE_ABI_160 = '366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1'
STATE_ABI_160_REMOVED = {
    'md': '2832912487d66aa2f846a6c48ca7248976adec158ee407b8fcb3a509f514d6c8',
    'ng': '6e0721d152aa17f6bec321b960177773b7e9eaf06c29cc350b39f3a4b91fc46a',
    'cps1': 'bc842183c642e70f5c9a43570d685ce8ea1efa826c7f21e8268c4a6abfb6fa9d',
}
# Keys of releases before 1.6.0 that earlier trees listed: never listed again.
STATE_ABI_156_REMOVED = ('9866fc8dcb7866bc38e7f3251b2469aa6933a46ae181f3a03ad5fa12ca2a8520',
                         'fa66982c49f9d86ebf38e555714601d7466bf43331de44eaf4093e6d759bea41',
                         'a04dc60ccd2aab4d029fa96fef271d91595396fe3bd97b434f117ca32ff799dd')


class LegacyStampTests(unittest.TestCase):
    def test_the_table_lists_release_1_6_1_and_nothing_older(self):
        self.assertEqual(inputs.LEGACY_GAME_STAMPS, {system: (stamp, GAME_STAMPS_161_LINUX[system])
                                                     for system, stamp in GAME_STAMPS_161.items()})
        for system in sorted(inputs.SYSTEMS):
            expected = (GAME_STAMPS_161[system], GAME_STAMPS_161_LINUX[system]) if system in GAME_STAMPS_161 else ()
            self.assertEqual(inputs.legacy_game_stamps(system), expected, system)
        self.assertEqual(inputs.legacy_game_stamps('unknown'), ())
        listed = {stamp for stamps in inputs.LEGACY_GAME_STAMPS.values() for stamp in stamps}
        self.assertFalse(listed & set(GAME_STAMPS_156_REMOVED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_160_REMOVED.values()))

    def test_every_listed_stamp_moved_since_1_6_1_and_is_not_the_current_one(self):
        # The stamp of 1.6.2 is another one on every console: a listed stamp is a receipt that is never current.
        for system in sorted(inputs.SYSTEMS):
            self.assertNotIn(inputs.role_stamps(system)['game'], inputs.legacy_game_stamps(system), system)
            self.assertNotEqual(inputs.role_stamps(system)['game'], GAME_STAMPS_161.get(system), system)
            self.assertNotEqual(inputs.role_stamps(system)['game'], GAME_STAMPS_161_LINUX.get(system), system)

    def test_the_x68000_is_converted_in_full_by_the_next_release(self):
        # Its request holds `x68_sdk`, hash of the game stamp of the tree that wrote it: not covered by the table.
        self.assertEqual(inputs.legacy_game_stamps('x68'), ())
        listed = {stamp for stamps in inputs.LEGACY_GAME_STAMPS.values() for stamp in stamps}
        self.assertNotIn(X68_GAME_STAMP_161_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_161_LINUX_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_160_NOT_LISTED, listed)

    def test_super_nintendo_exports_of_1_6_1_are_upgraded(self):
        # Nothing Super Nintendo specific changed between 1.6.1 and 1.6.2 (docs/UPGRADES.md): the entry is listed.
        self.assertEqual(inputs.legacy_game_stamps('snes'), (GAME_STAMPS_161['snes'], GAME_STAMPS_161_LINUX['snes']))


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

    def receipt(self, folder, item, game, release='1.6.1', schema=3):
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
                    self.assertEqual(previous['legacy_release'], '1.6.1')
                    self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.1')
                    # Any other game part (an older release, other code) is converted in full.
                    target, path = self.receipt(folder, item, 'f' * 64)
                    self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_the_game_part_of_a_1_6_1_receipt_is_what_the_table_makes_1_6_2_accept(self):
        # A 1.6.1 receipt carries hash(request with engine = the game stamp of the tag): the request of 1.6.2, asked
        # with that engine, gives the same hash on every listed console, and the table lists exactly that hash.
        from retrorecomp import freshness
        for system in sorted(GAME_STAMPS_161):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                item, parts = self.parts(system)
                # The Windows and the Linux converter of 1.6.1, in the table's order.
                frozen = [self.parts(system, stamps[system])[1] for stamps in (GAME_STAMPS_161, GAME_STAMPS_161_LINUX)]
                self.assertEqual(parts['legacy_games'], [part['game'] for part in frozen])
                for part in frozen:
                    self.assertNotEqual(parts['game'], part['game'])
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        target, path = self.receipt(folder, item, part['game'])
                        self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                        previous = freshness.upgradable(item, target, path, parts, print)
                        self.assertEqual(previous['legacy_release'], '1.6.1')
                        self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.1')

    def test_nothing_is_upgraded_from_a_release_the_table_does_not_list(self):
        # 1.5.6 and 1.6.0 (listed by the tables of 1.6.0 and 1.6.1, not by this one) and any other game part:
        # converted in full.
        from retrorecomp import freshness
        for release, removed in (('1.5.6', GAME_STAMPS_156_REMOVED), ('1.6.0', GAME_STAMPS_160_REMOVED)):
            for system in sorted(removed):
                with self.subTest(release=release, system=system), tempfile.TemporaryDirectory() as folder:
                    item, parts = self.parts(system)
                    self.assertEqual(len(parts['legacy_games']), 2)     # 1.6.1 on Windows and on Linux
                    old = self.parts(system, removed[system])[1]['game']
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        for game in (old, 'f' * 64):
                            target, path = self.receipt(folder, item, game, release)
                            self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_without_an_entry_a_1_6_1_receipt_is_converted_in_full(self):
        # What the X68000 gets (its request needs real disks and firmware, so a console with an entry stands for it).
        from retrorecomp import freshness
        self.assertEqual(sorted(inputs.SYSTEMS - set(GAME_STAMPS_161)), ['x68'])
        with tempfile.TemporaryDirectory() as folder, patch.dict(inputs.LEGACY_GAME_STAMPS, {}, clear=True):
            item, parts = self.parts('sms')
            self.assertEqual(parts['legacy_games'], [])
            with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                target, path = self.receipt(folder, item, GAME_STAMPS_161['sms'])
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

    def configs(self):
        from retrorecomp import cps1_build, neogeo_build
        with patch('retrorecomp.neogeo.parse_neo', return_value=SimpleNamespace(sha256='a' * 64)), \
                patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}):
            texts = {'ng': neogeo_build.state_config(Path('cartridge.neo'), Path('neogeo.zip'), 'Test')}
        texts['cps1'] = cps1_build.state_config(SimpleNamespace(sha256='c' * 64), 'Test')
        texts['md'] = self.sixteen_bit_config('md')
        texts['snes'] = self.sixteen_bit_config('snes')
        return texts

    def test_the_states_of_release_1_6_1_are_accepted_by_the_four_consoles_whose_key_moved(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        self.assertEqual(console16_state.MD_STATE_ABI_161, MD_STATE_ABI_161)
        self.assertEqual(console16_state.SNES_STATE_ABI_161, SNES_STATE_ABI_161)
        self.assertEqual(neogeo_build.STATE_ABI_161, NEO_GEO_STATE_ABI_161)
        self.assertEqual(cps1_build.LEGACY_STATE_ABI_161, CPS1_STATE_ABI_161)
        texts = self.configs()
        for system, key in (('md', MD_STATE_ABI_161), ('snes', SNES_STATE_ABI_161), ('ng', NEO_GEO_STATE_ABI_161),
                            ('cps1', CPS1_STATE_ABI_161)):
            text = texts[system]
            # Exactly one compatibility line, and it is the key of 1.6.1, which is not the build's own key.
            self.assertEqual(text.count('RR16_STATE_COMPAT_ABI'), 1, system)
            self.assertIn(f'#define RR16_STATE_COMPAT_ABI "{key}"\n', text, system)
            self.assertRegex(text, r'#define RR16_STATE_ABI "[0-9a-f]{64}"', system)
            self.assertNotIn(f'RR16_STATE_ABI "{key}"', text, system)

    def test_the_layout_versions_the_1_6_1_keys_stand_for_did_not_move(self):
        # The keys hash files; what is serialized is fixed by these versions and the state files, none of which changed
        # between the v1.6.1 tag and 1.6.2 (below native/ only the host kit shell, the NES host files and
        # runtime_catalog.inc differ: strings and shell code, none of it saved in a state).
        from retrorecomp import console16_state
        self.assertEqual((console16_state.PORTABLE_STATE_ABI, console16_state.MD_PORTABLE_STATE_ABI), (2, 11))
        for name in StateLayoutGuardTests.FILES:
            path = ASSETS / 'native' / name
            if path.is_file():
                self.assertNotIn('runtime_catalog', path.read_text(encoding='utf-8', errors='replace'), name)

    def test_the_super_nintendo_key_of_1_6_1_is_the_one_of_1_6_0_and_is_no_longer_the_build_key(self):
        # 1.6.1 needed no line: its key was 1.6.0's. The runtime catalogue moved it in 1.6.2, which lists it now.
        self.assertEqual(SNES_STATE_ABI_161, SNES_STATE_ABI_160)
        text = self.configs()['snes']
        self.assertIn(f'#define RR16_STATE_COMPAT_ABI "{SNES_STATE_ABI_161}"', text)
        self.assertNotIn(f'#define RR16_STATE_ABI "{SNES_STATE_ABI_161}"', text)

    def test_no_state_key_of_a_release_before_1_6_1_is_accepted(self):
        texts = self.configs()
        for system, text in texts.items():
            for key in STATE_ABI_156_REMOVED:
                self.assertNotIn(key, text, system)
            if system in STATE_ABI_160_REMOVED:
                self.assertNotIn(STATE_ABI_160_REMOVED[system], text, system)
            self.assertNotRegex(text, r'RR16_STATE_COMPAT_ABI_\d', system)
        # The 1.6.0 keys of the three consoles whose key changed in 1.6.1 are not 1.6.1 keys either.
        for system, key in (('md', MD_STATE_ABI_161), ('ng', NEO_GEO_STATE_ABI_161), ('cps1', CPS1_STATE_ABI_161)):
            self.assertNotEqual(key, STATE_ABI_160_REMOVED[system], system)

    def test_the_state_key_constants_are_those_of_1_6_1_only(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        for module in (console16_state, cps1_build, neogeo_build):
            for name in dir(module):
                match = re.search(r'STATE_ABI_(\d+)$', name)
                if match:
                    self.assertEqual(match.group(1), '161', (module.__name__, name))
        for module, name in ((console16_state, 'MD_STATE_ABI_160'), (console16_state, 'SNES_STATE_ABI_160'),
                             (neogeo_build, 'STATE_ABI_160'), (cps1_build, 'LEGACY_STATE_ABI_160'),
                             (console16_state, 'MD_STATE_ABI_141'), (console16_state, 'SNES_STATE_ABI_141'),
                             (console16_state, 'MD_STATE_ABI_156'), (neogeo_build, 'STATE_ABI_156'),
                             (cps1_build, 'LEGACY_STATE_ABI_156')):
            self.assertFalse(hasattr(module, name), (module.__name__, name))

    def test_the_shared_16_bit_state_loader_accepts_the_compatibility_key_a_build_defines(self):
        loader = (ASSETS / 'native/console16_state.c').read_text(encoding='utf-8')
        self.assertRegex(loader, r'#ifdef RR16_STATE_COMPAT_ABI\b')


class NeoGeoStateKeyPlatformTests(unittest.TestCase):
    """The key of 1.6.1 is a Windows key: a Linux build writes none (its own key also hashes its target)."""

    def test_the_neo_geo_compatibility_line_is_written_on_windows_only(self):
        from retrorecomp import neogeo_build
        real = os

        class FakeOs:
            def __init__(self, name):
                self.name = name

            def __getattr__(self, attribute):
                return getattr(real, attribute)

        for name, listed in (('nt', True), ('posix', False)):
            with self.subTest(name=name), \
                    patch('retrorecomp.neogeo.parse_neo', return_value=SimpleNamespace(sha256='a' * 64)), \
                    patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}), \
                    patch('retrorecomp.neogeo_build.os', FakeOs(name)), \
                    patch('retrorecomp.platforms.target_id', return_value='linux-x86_64'):
                text = neogeo_build.state_config(Path('cartridge.neo'), Path('neogeo.zip'), 'Test')
            self.assertEqual(f'#define RR16_STATE_COMPAT_ABI "{NEO_GEO_STATE_ABI_161}"' in text, listed)
            self.assertEqual(text.count('RR16_STATE_COMPAT_ABI'), int(listed))


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
