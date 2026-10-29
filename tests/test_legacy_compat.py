"""Backward compatibility is owed to the previous release only (decision of 28 October 2026).

The tree of 1.6.0 listed nothing for a previous release. The tree of 1.6.1 listed the previous release, 1.6.0, and
only it. The tree of 1.6.2 listed 1.6.1 and only it. The tree of 1.6.3 lists 1.6.2 and only it: its game stamps in
`LEGACY_GAME_STAMPS` (the Master System, Game Gear, Game Boy and NES; the Mega Drive, Neo Geo, CPS-1 and Super Nintendo
have none, because 1.6.3 changes what a game does on their CPUs, the 68000 shifts and the 65816 BRK and COP: the release
procedure of docs/COMPILATION_LIBRARY.md; the X68000 has none because its request carries an `x68_sdk` stamp the
mechanism does not recompute; the 1.6.1 stamps are dropped) and its quick-state keys as `RR16_STATE_COMPAT_ABI` (Mega
Drive, Super Nintendo, Neo Geo and CPS-1, Windows, whether or not the export is upgraded; the 1.6.1 keys are dropped). The values
below are frozen: they were computed from the `v1.6.0`, `v1.6.1` and `v1.6.2` tags (docs/UPGRADES.md, "Exports of 1.6.2
in 1.6.3"; docs/GAME_STATES.md, "States written by release 1.6.2"), the game stamps with Python 3.14.5 (Windows) and
3.13.5 (Linux), the state keys with Python 3.14.5. The release that follows 1.6.3 replaces the game stamps and the state
keys with those of 1.6.3; the mechanisms are driven here with synthetic values as well.
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

# Game stamps of release 1.6.2, from the v1.6.2 tag (archive of the tag, `role_stamps(system)['game']`), equal on every
# console to the stamp the published Windows converter gives with its own `_compilation-inputs`. Four consoles are listed:
# between 1.6.2 and 1.6.3 the Master System and Game Gear change only the "functions" engine (a functions export that
# diverges fails the upgrade recheck and is converted again), the Game Boy and the NES no game behaviour.
GAME_STAMPS_162 = {
    'gb': '831c25068b495316b763e46ee05a62f4ca4b9a1abbb92692c68979c559406b9a',
    'gg': '14ae3fcbdaf43b121500a121128bcae88161279b350a745952ff17e44ae65743',
    'nes': 'fa98f9dd4c480eb16ab7e66c491cb52b02100f88631c5f398112a896e79f5ce4',
    'sms': 'b4e9d8b926b55189f2369ea20e6e99123a2ef3b8bbe12ad9a2455c8a9e35f4b2',
}
# Verified like the others and NOT listed: 1.6.3 changes what a game does on these CPUs (the 68000 shifts for the Mega
# Drive, Neo Geo and CPS-1, the 65816 BRK and COP for the Super Nintendo), so their exports of 1.6.2 are converted in full.
# The release procedure of docs/COMPILATION_LIBRARY.md lists no console whose game the release really changes.
GAME_STAMPS_162_NOT_LISTED = {
    'cps1': 'd4e10fc37d4974cd495d666ac35bb11a29be5a79df2ed3fa8167263f044b54fb',
    'md': 'ad4dee96cbceb46be2c7cdf200d917586451d53c8abbca0d24c4b6e95a500b85',
    'ng': 'aff15893e4d95019cab57539ab28f5438f74613b07e780f2f9412f19b054b838',
    'snes': 'b6a7c7fd16250e9512258d961d7f2069d8bf6f0988a0be611530219577556d18',
}
# The X68000 is not listed either: its request carries an SDK stamp derived from the game stamp that the mechanism does
# not recompute, so its 1.6.2 stamp (below) is recorded and must stay unlisted.
X68_GAME_STAMP_162_NOT_LISTED = '699f09265a9fe722e1cedabd80d711961f8edd8e06385366eb1aa7cc1befab39'
# The same release's Linux converter, built with Python 3.13 (code is fingerprinted as bytecode): the stamps the published
# Linux 1.6.2 converter gives with its own `_compilation-inputs`, equal to the archive of v1.6.2 under Python 3.13.
GAME_STAMPS_162_LINUX = {
    'gb': 'dde2e590f43d5efc0dea2d34ceedee54ee908cdba37d1a1ea6535cde1d6bc1b4',
    'gg': '0d63e09321860ce6e161b49a24535d13ddc10b5e6d281b91b195ad9472710a6d',
    'nes': '6618f7f293fd864e5cc6e3fec4aa89b020e2795593ba924ab30b4e13990b921a',
    'sms': '58d4d6ee6bd59653e4815b303a8c332d593b3755419970732171e914d6b0af73',
}
GAME_STAMPS_162_LINUX_NOT_LISTED = {
    'cps1': '4a0de40695a4b51350cf43eb36450211cdff13f785730f1ead61bffc4ae6ea43',
    'md': '0de9eed2964d4261237a9099334e7bbcad2dead0dab99258674dd0c306b220b0',
    'ng': 'b6d6f5a7ae69485b8b86913241a865b171dcad8cb30ab38ada9dc381b3e62142',
    'snes': 'fa81323602399f6e839ec9a3ee3ba1e0443fe313b5916c46b8a26742bdd55452',
}
X68_GAME_STAMP_162_LINUX_NOT_LISTED = '35980145fc8de1a9afb1b4722831bdbeafb38b097f963532579c412d5f2b2bc2'
# Game stamps of release 1.6.1 (the table of 1.6.2 listed them, Windows converter then Linux converter): owed to nobody
# any more.
GAME_STAMPS_161_REMOVED = {
    'cps1': 'fb7d9315c9637c103aa81f259712524d9bf29b33e6e9d920ce8f4b5ad83f92db',
    'gb': 'e5fc74915974ec27ab05bc9c9ae5ecea03050316ed39d9842b11485d2ffe1e09',
    'gg': 'f860d65789176fa85ad7c7880c766da1754ea98fedac4f50edcf77d664f799cd',
    'md': '2effe9f498891007f54fadc029a8f55f625ed414c73894fe2cbde5684dcfd188',
    'nes': 'a8b871f2ab08ffc44633cc562b942fdac9a3cc4d65a7706030b714abf96fa017',
    'ng': '1d1a5224f6c89a58ff7f1f79d807918a1c4f1295e0ae3543a253a4d884d2959b',
    'sms': 'c4589fe7b51645c8fc779fb2511d3dc9c793fa855b5c910089bbdf0cb3dea68d',
    'snes': '463da5c5cf464363bbc887e524a1933288e9f94c7d748cae624748dc172b6ae4',
}
GAME_STAMPS_161_LINUX_REMOVED = {
    'cps1': '5a47af5e465134ab8fa927cd3389c7bbbcc12d61ec02f18461de63e89ae175fb',
    'gb': 'f194a7e52b26bddadcf02362d4921774ec75f8c65629724286c3ad5c716322d5',
    'gg': '2e805515d5cf5e080ea5f9ac10d97759bcf22b6976b565b2a73d599f2d82d736',
    'md': '47c10b4b7a49bd24c34cee183442cdb5344c578657f5b3ed83106794a9944db9',
    'nes': '480b9aea940b6c5fe11adcf226dcf6fc15fb5df2703080c8c62ef71a4efba5c2',
    'ng': 'cc24dd0a1115f37f2053188a478f8592bb2e42765b6e07aacd8f8d4bf7427e4f',
    'sms': '1a3b71b7a75d91e2ed859656671c7471a31d9ce4527f2f15170146e961a71346',
    'snes': '0a62f3c2061a22948f8442c8b84faee71f0925772536f8a7d30d4ae43bef63d9',
}
X68_GAME_STAMP_161_NOT_LISTED = '428f2fc57bfbd0d11cf3e1bbd7977a967628bc328728746dc784cea0c39241ca'
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
# Game stamps of release 1.5.6 (the table of 1.6.0 listed them): owed to nobody for three releases now.
GAME_STAMPS_156_REMOVED = {
    'cps1': '187c9db92db22e872d352e6c5895640c414849ba6e50b07db0b06c4e703738fb',
    'gb': 'c8a90b01e99b68da0f9796d109d7f161e9c848d2f8100651731c6dfe3f56f806',
    'gg': '08950dbb0d3cce0475b17c309d17f72c0b65ed02e9e99cf1b9a4138afe50747b',
    'md': 'd9bd59e01303a56a92e619aef54f67203fa7d0b3a7cb3211addc0562d6f9aa18',
    'nes': 'c98420ac1dfde068026e7fb72da97844714b6a31e6536cca93ff012add168715',
    'sms': '3897d8b37cffe8a438fd12cb7b522c9fac5222c5b94c9eb045457ef557e2fa7b',
}
# Quick-state keys of release 1.6.2 (Windows), from the v1.6.2 tag; the same code gives the documented 1.5.6 keys from
# the v1.5.6 tag. All four moved in 1.6.3: the Mega Drive and Super Nintendo keys hash the native files the host kit
# replaced, the Neo Geo and CPS-1 ones hash the fingerprints of modules that moved onto the shared conversion helpers
# (and of this rollover's own edit).
MD_STATE_ABI_162 = '7943c469d11b059b7cf2a6ff4597dc2809d25cd5b093752d837c2a4d8c661948'
SNES_STATE_ABI_162 = 'b9fbf76dc2cc49459420ff111d143c64c72cd72b440a1264d91b38be21bcb5c4'
NEO_GEO_STATE_ABI_162 = '0d361a5f02f0f6838bf555dce0b89dd8fa1dce8cd23045fd2811653fec0720df'
CPS1_STATE_ABI_162 = 'b24053cfe60639a1a464f74e63d155dcb351ac0713796e554937edd65821d8e9'
# Keys of release 1.6.1 (the previous release of the tree of 1.6.2): owed to nobody any more.
STATE_ABI_161_REMOVED = {
    'md': 'fb6d191a2b8c3975e4a69560fb204ad1e79c8726bb55f448e15e2d201550c959',
    'snes': '366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1',
    'ng': '5c25722def19e560b4cbce7c7424d3c2f3317a2a91f6d3d3f184f16a46fdc474',
    'cps1': 'f745f993a28521fa17dbe84332964b677a3ab35f5bbb77b7f7c1fcb95cd902ee',
}
# Keys of release 1.6.0: owed to nobody any more. The Super Nintendo one is also its 1.6.1 key.
STATE_ABI_160_REMOVED = {
    'md': '2832912487d66aa2f846a6c48ca7248976adec158ee407b8fcb3a509f514d6c8',
    'snes': '366aa5f94b8c57080255e2540bc513bc8e875e8b03fc8fb02bef344b2c05ddf1',
    'ng': '6e0721d152aa17f6bec321b960177773b7e9eaf06c29cc350b39f3a4b91fc46a',
    'cps1': 'bc842183c642e70f5c9a43570d685ce8ea1efa826c7f21e8268c4a6abfb6fa9d',
}
# Keys of releases before 1.6.0 that earlier trees listed: never listed again.
STATE_ABI_156_REMOVED = ('9866fc8dcb7866bc38e7f3251b2469aa6933a46ae181f3a03ad5fa12ca2a8520',
                         'fa66982c49f9d86ebf38e555714601d7466bf43331de44eaf4093e6d759bea41',
                         'a04dc60ccd2aab4d029fa96fef271d91595396fe3bd97b434f117ca32ff799dd')


class LegacyStampTests(unittest.TestCase):
    def test_the_table_lists_release_1_6_2_and_nothing_older(self):
        self.assertEqual(inputs.LEGACY_GAME_STAMPS, {system: (stamp, GAME_STAMPS_162_LINUX[system])
                                                     for system, stamp in GAME_STAMPS_162.items()})
        for system in sorted(inputs.SYSTEMS):
            expected = (GAME_STAMPS_162[system], GAME_STAMPS_162_LINUX[system]) if system in GAME_STAMPS_162 else ()
            self.assertEqual(inputs.legacy_game_stamps(system), expected, system)
        self.assertEqual(inputs.legacy_game_stamps('unknown'), ())
        listed = {stamp for stamps in inputs.LEGACY_GAME_STAMPS.values() for stamp in stamps}
        self.assertFalse(listed & set(GAME_STAMPS_156_REMOVED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_160_REMOVED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_161_REMOVED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_161_LINUX_REMOVED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_162_NOT_LISTED.values()))
        self.assertFalse(listed & set(GAME_STAMPS_162_LINUX_NOT_LISTED.values()))

    def test_every_listed_stamp_moved_since_1_6_2_and_is_not_the_current_one(self):
        # The stamp of 1.6.3 is another one on every console: a listed stamp is a receipt that is never current.
        for system in sorted(inputs.SYSTEMS):
            self.assertNotIn(inputs.role_stamps(system)['game'], inputs.legacy_game_stamps(system), system)
            self.assertNotEqual(inputs.role_stamps(system)['game'], GAME_STAMPS_162.get(system), system)
            self.assertNotEqual(inputs.role_stamps(system)['game'], GAME_STAMPS_162_LINUX.get(system), system)
            self.assertNotEqual(inputs.role_stamps(system)['game'], GAME_STAMPS_162_NOT_LISTED.get(system), system)

    def test_the_x68000_is_converted_in_full_by_the_next_release(self):
        # Its request holds `x68_sdk`, hash of the game stamp of the tree that wrote it: not covered by the table.
        self.assertEqual(inputs.legacy_game_stamps('x68'), ())
        listed = {stamp for stamps in inputs.LEGACY_GAME_STAMPS.values() for stamp in stamps}
        self.assertNotIn(X68_GAME_STAMP_162_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_162_LINUX_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_161_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_161_LINUX_NOT_LISTED, listed)
        self.assertNotIn(X68_GAME_STAMP_160_NOT_LISTED, listed)

    def test_the_consoles_whose_game_changes_on_their_cpu_have_no_entry(self):
        # The release procedure (docs/COMPILATION_LIBRARY.md): no entry for a console when the release really changes what
        # a game does. 1.6.3 changes the 68000 shifts (Mega Drive, Neo Geo, CPS-1) and the 65816 BRK and COP (Super
        # Nintendo): their exports of 1.6.2 are converted in full, whatever the stamps verified for 1.6.2 are.
        self.assertEqual(sorted(GAME_STAMPS_162_NOT_LISTED), ['cps1', 'md', 'ng', 'snes'])
        self.assertEqual(sorted(GAME_STAMPS_162_LINUX_NOT_LISTED), ['cps1', 'md', 'ng', 'snes'])
        for system in GAME_STAMPS_162_NOT_LISTED:
            self.assertEqual(inputs.legacy_game_stamps(system), (), system)
            self.assertNotIn(system, inputs.LEGACY_GAME_STAMPS)

    def test_the_consoles_that_change_no_game_behaviour_are_upgraded(self):
        # Master System and Game Gear: only the "functions" engine changes (the default banked engine generates the same
        # sources; a functions export that diverges fails the upgrade recheck). Game Boy and NES: nothing a game does.
        self.assertEqual(sorted(GAME_STAMPS_162), ['gb', 'gg', 'nes', 'sms'])
        for system in GAME_STAMPS_162:
            self.assertEqual(inputs.legacy_game_stamps(system), (GAME_STAMPS_162[system], GAME_STAMPS_162_LINUX[system]))


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

    def receipt(self, folder, item, game, release='1.6.2', schema=3):
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
                    self.assertEqual(previous['legacy_release'], '1.6.2')
                    self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.2')
                    # Any other game part (an older release, other code) is converted in full.
                    target, path = self.receipt(folder, item, 'f' * 64)
                    self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_the_game_part_of_a_1_6_2_receipt_is_what_the_table_makes_1_6_3_accept(self):
        # A 1.6.2 receipt carries hash(request with engine = the game stamp of the tag): the request of 1.6.3, asked
        # with that engine, gives the same hash on every listed console, and the table lists exactly that hash.
        from retrorecomp import freshness
        for system in sorted(GAME_STAMPS_162):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                item, parts = self.parts(system)
                # The Windows and the Linux converter of 1.6.2, in the table's order.
                frozen = [self.parts(system, stamps[system])[1] for stamps in (GAME_STAMPS_162, GAME_STAMPS_162_LINUX)]
                self.assertEqual(parts['legacy_games'], [part['game'] for part in frozen])
                for part in frozen:
                    self.assertNotEqual(parts['game'], part['game'])
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        target, path = self.receipt(folder, item, part['game'])
                        self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                        previous = freshness.upgradable(item, target, path, parts, print)
                        self.assertEqual(previous['legacy_release'], '1.6.2')
                        self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.2')

    def test_nothing_is_upgraded_from_a_release_the_table_does_not_list(self):
        # 1.5.6, 1.6.0 and 1.6.1 (listed by the tables of 1.6.0, 1.6.1 and 1.6.2, not by this one) and any other game
        # part: converted in full.
        from retrorecomp import freshness
        for release, removed in (('1.5.6', GAME_STAMPS_156_REMOVED), ('1.6.0', GAME_STAMPS_160_REMOVED),
                                 ('1.6.1', GAME_STAMPS_161_REMOVED), ('1.6.1', GAME_STAMPS_161_LINUX_REMOVED)):
            for system in sorted(removed):
                with self.subTest(release=release, system=system), tempfile.TemporaryDirectory() as folder:
                    item, parts = self.parts(system)
                    # 1.6.2 on Windows and on Linux, for the four consoles that list it
                    self.assertEqual(len(parts['legacy_games']), 2 if system in GAME_STAMPS_162 else 0)
                    old = self.parts(system, removed[system])[1]['game']
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        for game in (old, 'f' * 64):
                            target, path = self.receipt(folder, item, game, release)
                            self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_a_1_6_2_receipt_of_a_console_without_an_entry_is_converted_in_full(self):
        # Mega Drive, Neo Geo, CPS-1 and Super Nintendo: their 1.6.2 game stamp (the one a real 1.6.2 receipt carries) is
        # not listed, so the receipt is not recognised and the export is converted in full.
        from retrorecomp import freshness
        for system in sorted(GAME_STAMPS_162_NOT_LISTED):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                item, parts = self.parts(system)
                self.assertEqual(parts['legacy_games'], [])
                for stamps in (GAME_STAMPS_162_NOT_LISTED, GAME_STAMPS_162_LINUX_NOT_LISTED):
                    game = self.parts(system, stamps[system])[1]['game']
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        target, path = self.receipt(folder, item, game)
                        self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                        self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_without_an_entry_a_1_6_2_receipt_is_converted_in_full(self):
        # What the X68000 gets (its request needs real disks and firmware, so a console with an entry stands for it).
        from retrorecomp import freshness
        nine = {'sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'x68', 'cps1'}
        self.assertEqual(sorted((inputs.SYSTEMS & nine) - set(GAME_STAMPS_162)), ['cps1', 'md', 'ng', 'snes', 'x68'])
        with tempfile.TemporaryDirectory() as folder, patch.dict(inputs.LEGACY_GAME_STAMPS, {}, clear=True):
            item, parts = self.parts('sms')
            self.assertEqual(parts['legacy_games'], [])
            with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                target, path = self.receipt(folder, item, GAME_STAMPS_162['sms'])
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

    def test_the_states_of_release_1_6_2_are_accepted_by_the_four_consoles_whose_key_moved(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        self.assertEqual(console16_state.MD_STATE_ABI_162, MD_STATE_ABI_162)
        self.assertEqual(console16_state.SNES_STATE_ABI_162, SNES_STATE_ABI_162)
        self.assertEqual(neogeo_build.STATE_ABI_162, NEO_GEO_STATE_ABI_162)
        self.assertEqual(cps1_build.LEGACY_STATE_ABI_162, CPS1_STATE_ABI_162)
        texts = self.configs()
        for system, key in (('md', MD_STATE_ABI_162), ('snes', SNES_STATE_ABI_162), ('ng', NEO_GEO_STATE_ABI_162),
                            ('cps1', CPS1_STATE_ABI_162)):
            text = texts[system]
            # Exactly one compatibility line, and it is the key of 1.6.2, which is not the build's own key.
            self.assertEqual(text.count('RR16_STATE_COMPAT_ABI'), 1, system)
            self.assertIn(f'#define RR16_STATE_COMPAT_ABI "{key}"\n', text, system)
            self.assertRegex(text, r'#define RR16_STATE_ABI "[0-9a-f]{64}"', system)
            self.assertNotIn(f'RR16_STATE_ABI "{key}"', text, system)

    def test_the_layout_versions_the_1_6_2_keys_stand_for_did_not_move(self):
        # The keys hash files; what is serialized is fixed by these versions and the state files, none of which changed
        # between the v1.6.2 tag and 1.6.3 (below native/ the files that differ are the host kit shell and adapters,
        # the options menu, the sound output, runtime_catalog.inc, the CMake file and the checks: strings, shell code
        # and build lists, none of it saved in a state; the Neo Geo and CPS-1 state files are byte-identical).
        from retrorecomp import console16_state
        self.assertEqual((console16_state.PORTABLE_STATE_ABI, console16_state.MD_PORTABLE_STATE_ABI), (2, 11))
        for name in StateLayoutGuardTests.FILES:
            path = ASSETS / 'native' / name
            if path.is_file():
                self.assertNotIn('runtime_catalog', path.read_text(encoding='utf-8', errors='replace'), name)

    def test_no_state_key_of_a_release_before_1_6_2_is_accepted(self):
        texts = self.configs()
        for system, text in texts.items():
            for key in STATE_ABI_156_REMOVED:
                self.assertNotIn(key, text, system)
            for removed in (STATE_ABI_160_REMOVED, STATE_ABI_161_REMOVED):
                self.assertNotIn(removed[system], text, system)
            self.assertNotRegex(text, r'RR16_STATE_COMPAT_ABI_\d', system)
        # The 1.6.1 keys are not 1.6.2 keys either, and the Super Nintendo key of 1.6.0 and 1.6.1 was one and the same.
        for system, key in (('md', MD_STATE_ABI_162), ('snes', SNES_STATE_ABI_162), ('ng', NEO_GEO_STATE_ABI_162),
                            ('cps1', CPS1_STATE_ABI_162)):
            self.assertNotEqual(key, STATE_ABI_161_REMOVED[system], system)
        self.assertEqual(STATE_ABI_161_REMOVED['snes'], STATE_ABI_160_REMOVED['snes'])

    def test_the_state_key_constants_are_those_of_1_6_2_only(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        for module in (console16_state, cps1_build, neogeo_build):
            for name in dir(module):
                match = re.search(r'STATE_ABI_(\d+)$', name)
                if match:
                    self.assertEqual(match.group(1), '162', (module.__name__, name))
        for module, name in ((console16_state, 'MD_STATE_ABI_161'), (console16_state, 'SNES_STATE_ABI_161'),
                             (neogeo_build, 'STATE_ABI_161'), (cps1_build, 'LEGACY_STATE_ABI_161'),
                             (console16_state, 'MD_STATE_ABI_160'), (console16_state, 'SNES_STATE_ABI_160'),
                             (neogeo_build, 'STATE_ABI_160'), (cps1_build, 'LEGACY_STATE_ABI_160'),
                             (console16_state, 'MD_STATE_ABI_141'), (console16_state, 'SNES_STATE_ABI_141'),
                             (console16_state, 'MD_STATE_ABI_156'), (neogeo_build, 'STATE_ABI_156'),
                             (cps1_build, 'LEGACY_STATE_ABI_156')):
            self.assertFalse(hasattr(module, name), (module.__name__, name))

    def test_the_shared_16_bit_state_loader_accepts_the_compatibility_key_a_build_defines(self):
        loader = (ASSETS / 'native/console16_state.c').read_text(encoding='utf-8')
        self.assertRegex(loader, r'#ifdef RR16_STATE_COMPAT_ABI\b')


class NeoGeoStateKeyPlatformTests(unittest.TestCase):
    """The key of 1.6.2 is a Windows key: a Linux build writes none (its own key also hashes its target)."""

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
            self.assertEqual(f'#define RR16_STATE_COMPAT_ABI "{NEO_GEO_STATE_ABI_162}"' in text, listed)
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
