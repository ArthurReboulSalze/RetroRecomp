"""Backward compatibility is owed to the previous release only (decision of 28 October 2026).

The tree of 1.6.0 listed nothing for a previous release. The tree of 1.6.1 listed the previous release, 1.6.0, and
only it. The tree of 1.6.2 listed 1.6.1 and only it. The tree of 1.6.3 listed 1.6.2 and only it (four consoles). The tree
of 1.6.4 lists NO game stamp of 1.6.3 in `LEGACY_GAME_STAMPS`: 1.6.4 is a structural release with a full reconversion of
every console (decision of the maintainer, 29 October 2026; the release procedure of docs/COMPILATION_LIBRARY.md lists no
console whose game the release really changes), because SDL 2.32.10 is linked into every game, the profile registry moves
every game stamp, and six consoles change in their own way (docs/UPGRADES.md, "Exports of 1.6.3 in 1.6.4"). The 1.6.2
stamps are dropped. The quick-state keys of 1.6.3 are listed where the serialized bytes did not change and the key moved
(Neo Geo only; the Mega Drive and Super Nintendo keys did not move, the CPS-1 and NES states changed: docs/GAME_STATES.md,
"States written by release 1.6.3"). The values below are frozen: they were computed from the `v1.6.0` to `v1.6.3` tags
(docs/UPGRADES.md; docs/GAME_STATES.md), the game, host and build stamps of 1.6.3 with Python 3.14.5 (Windows) and 3.13.5
(Linux), the state keys with Python 3.14.5. The release that follows 1.6.4 replaces them with those of 1.6.4; the
mechanisms are driven here with synthetic values as well.
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

# Game, host and build stamps of release 1.6.3, from the v1.6.3 tag (commit bb2aa95; archive of the tag exported into an
# empty folder, `compilation_inputs.role_stamps(system)`), Windows converter (Python 3.14.5). Evidence only: NONE is listed
# in `LEGACY_GAME_STAMPS`, every console's export of 1.6.3 is converted in full in 1.6.4.
GAME_STAMPS_163 = {
    'cps1': 'cdfe0c2944e41813548f3847e1742d7d9f395463f7966dddd6ea573518628e43',
    'gb': '20d990464af935b2ea058208029ec0a7f0fdadb955e46275f4ad6dcd33749b28',
    'gg': '67487dfd4d724db4f7be9052fd57cafea77f810a9b5a7cf74d7cfdb121b74a4f',
    'md': 'c8c3a33789a92f80d41df0c43e546c581e94884055bb07a31ef04ebae583ba9d',
    'nes': '21c183e6df50d5048ada8f5dfb3596633f4bffcdc6d1fc088d21a5e96a33104c',
    'ng': '4637299cdbf17baea508a7046e4576ca59acc8dd994c2a51c70558adfb76b360',
    'sms': '63e727d52b1b7af0ce1c6544bac62c1362e73132efdad799347c49bf07ed7257',
    'snes': '6825afd89679334b3aee85318a31b1ad2ad381654be1d7d6951552cedb5950ff',
    'x68': 'a58d873ff98ca9a16f973a2621ffa672a1f0dc464f7694ff36f7ebbf4645e84e',
}
HOST_STAMPS_163 = {
    'cps1': '7e3b53b34bd2508f49cde41ad692d743c3d14e5f1c6a47b4c8755466503872d0',
    'gb': '1efc1dbb44cfb596d6fcc823ba67862594dd552e1a8f52d825c9e4b5c26b1f48',
    'gg': '5b99931159ed13039b62ee63a4aa9684eb8998856e8dac85664ef5d74c9c8458',
    'md': 'c398363d34c83ec7821abdafe71f4e3898d09292c6a7c099e0dacfeae0af980e',
    'nes': 'a722d03bfb4d5059045447f7cd27e93782c704bc76f648f3bf74286f2ff1387a',
    'ng': 'd83c902b3ebda289e120f4fcbdb0cfe29f2d6c42a0e394a3ac802797d7c6973c',
    'sms': '53d443aa47fe5fe20d75f37d8bfeb06bc992af3e938555fbb27c0251180d9f0a',
    'snes': '98a5ef5dbefc559d9e1f4df429bde71618db12af86f2644d0a4205f201f85733',
    'x68': 'b1e94a492351899e885aded7e77486a607c8518ed8e1aa86709753f5efbf7640',
}
BUILD_STAMPS_163 = {
    'cps1': '5022eedca09f8a0fffd8cfae1bd0e6c823f277ffe0dd9f3f2f5c27c3e3247a63',
    'gb': 'a95276b71c11e78625c3d29ba0d915c131f6c40e5da9d093093212e6acf21e78',
    'gg': '99adc3982e7e8255bc3ebcb7fad103a94814dd218893a78549f2c5e0a72d5fbb',
    'md': '04d0d103866e5c07fe1867b51182039c13eec54918ad57397effdf9e9cfae061',
    'nes': 'daf686c3aacfb39673019978ab0aac5b00fe46e580b55e532254bb2ddde5cd3d',
    'ng': '6c23ad79d979182db3455217c001ee583fd0a6cb4df5bc52deabb0ac76b9103c',
    'sms': '61b3ff1284fcf75b79309f140d5c68ed04fb0cc038c443a9176606d9bfd96b9e',
    'snes': 'b2fec61a9627103484912da9782e7371ba4987a726b6dcd173da2ceff6fc9f2f',
    'x68': 'e84c6e39d05d7f47ac5e0a51a2b676351cef673e855923b3bbb276597279a255',
}
# The same release's Linux converter, built with Python 3.13 (code is fingerprinted as bytecode): archive of v1.6.3 under
# Python 3.13.5 on the Linux build host.
GAME_STAMPS_163_LINUX = {
    'cps1': '490167ff02e59d7a17f19e863e527589f1d5dbe1a995fb8d016338c1a05148c4',
    'gb': 'e2a69eded159057ecfeade0d66091bb9248e9ba9a3bc63233b5bfcbcfffb344e',
    'gg': 'd5fa178b743638d1e49ed06ad9fbda597dfeb53664decb4f0076acd1a5949561',
    'md': 'd4a0f9676a97e96051cc531e95742e19d4311d137127fda088f9476b5282a3b3',
    'nes': '08df3e3cb280c7728d0a9af21d8c3fdf9b527dd2c5bf3b60e13fd80c4d46d3ff',
    'ng': '107d2a2b96b83614fec0b941555a280036e08edf32d62145b916f0d8331cc0ba',
    'sms': '8efac42db9fee6c3094e9cafc007c87ed7387e736fc4405d7d422e03472a702a',
    'snes': 'd7987cb30048be3cea669466ebfd9f1bbb96cfb8b949afb98fd3c8e78535e586',
    'x68': 'd85456f6c6e16301deb53ab14699812dae766470b4b88d35192f5e05fd5f4524',
}
HOST_STAMPS_163_LINUX = {
    'cps1': '4d5e0e263913a4d6c78ad8b9d191ec4f1f8811ef144bfc2131492a29d2d0c4a3',
    'gb': '56862d16ce57f92894964b8e30ec6b1acd99668b559009bc2df170a78b4ee993',
    'gg': 'a499021dcbad428be4ce18815449a40d782bed6e5fd438dcf79a382d38c094d2',
    'md': '6dff1958e9e78d15f11326c72d339e214d448af4b655dae68dde830e591a0302',
    'nes': '98b830d30a4ee79da2c35f7215346084c140b8dbf8149fe758dc1789736db842',
    'ng': '29890feb1e893aa4cd2b8a36dd967485bd9dc8db8ed0eb0015a7644da04dbeaf',
    'sms': '81b76644c91e662d3e03c98735e8b99942043fd0be6319aec33e3cc52cd5be6e',
    'snes': '26f8011512446037c117b68cb683c60778afd91e358a15f65aa218022afe69a2',
    'x68': 'e4b9192c471a04b521644f79d30a3667b6c00ff379b32016cacce63735d4728c',
}
BUILD_STAMPS_163_LINUX = {
    'cps1': '1710a97d399b07eb651c4982cb4a03ec500d401706920576402ab9b08ff2516e',
    'gb': 'fdf983cbb2cf9f658ca6b4ae0e877ac67fa8b594b8a01141bc40744fbc971b64',
    'gg': '35fd32cf151d92623789c9993895f73d7a6dc706d7a55629abcfe7748750347e',
    'md': 'a2e3f1d84f568da91d943cd6a8c66a847c2eb9196214d0a6374668f8669c5920',
    'nes': '0924450ada99b439fc7bd374df29b679b48366e88234b31b7f02b2d19132de8e',
    'ng': '735812b24a5d4b06f7ca72447e8b7b158a7b83c37a81813d25c8d2b24164e693',
    'sms': '844581a4aee67b01c2b64819e7d4328c6a0eb920ff65fc67f459734df36abf40',
    'snes': 'a801be2aa12c5efc034a1211ed47e81e0d3821a8ec47859e42a7c19ff116e255',
    'x68': '47712564c3a7d72667d0a764f2186a4d23ea492100e73cedd4cc44cc9763c098',
}
# Game stamps of release 1.6.2 (the table of 1.6.3 listed the first four, Windows converter then Linux converter): owed to
# nobody any more.
GAME_STAMPS_162_REMOVED = {
    'cps1': 'd4e10fc37d4974cd495d666ac35bb11a29be5a79df2ed3fa8167263f044b54fb',
    'gb': '831c25068b495316b763e46ee05a62f4ca4b9a1abbb92692c68979c559406b9a',
    'gg': '14ae3fcbdaf43b121500a121128bcae88161279b350a745952ff17e44ae65743',
    'md': 'ad4dee96cbceb46be2c7cdf200d917586451d53c8abbca0d24c4b6e95a500b85',
    'nes': 'fa98f9dd4c480eb16ab7e66c491cb52b02100f88631c5f398112a896e79f5ce4',
    'ng': 'aff15893e4d95019cab57539ab28f5438f74613b07e780f2f9412f19b054b838',
    'sms': 'b4e9d8b926b55189f2369ea20e6e99123a2ef3b8bbe12ad9a2455c8a9e35f4b2',
    'snes': 'b6a7c7fd16250e9512258d961d7f2069d8bf6f0988a0be611530219577556d18',
    'x68': '699f09265a9fe722e1cedabd80d711961f8edd8e06385366eb1aa7cc1befab39',
}
GAME_STAMPS_162_LINUX_REMOVED = {
    'cps1': '4a0de40695a4b51350cf43eb36450211cdff13f785730f1ead61bffc4ae6ea43',
    'gb': 'dde2e590f43d5efc0dea2d34ceedee54ee908cdba37d1a1ea6535cde1d6bc1b4',
    'gg': '0d63e09321860ce6e161b49a24535d13ddc10b5e6d281b91b195ad9472710a6d',
    'md': '0de9eed2964d4261237a9099334e7bbcad2dead0dab99258674dd0c306b220b0',
    'nes': '6618f7f293fd864e5cc6e3fec4aa89b020e2795593ba924ab30b4e13990b921a',
    'ng': 'b6d6f5a7ae69485b8b86913241a865b171dcad8cb30ab38ada9dc381b3e62142',
    'sms': '58d4d6ee6bd59653e4815b303a8c332d593b3755419970732171e914d6b0af73',
    'snes': 'fa81323602399f6e839ec9a3ee3ba1e0443fe313b5916c46b8a26742bdd55452',
    'x68': '35980145fc8de1a9afb1b4722831bdbeafb38b097f963532579c412d5f2b2bc2',
}
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
# Game stamps of release 1.5.6 (the table of 1.6.0 listed them): owed to nobody for four releases now.
GAME_STAMPS_156_REMOVED = {
    'cps1': '187c9db92db22e872d352e6c5895640c414849ba6e50b07db0b06c4e703738fb',
    'gb': 'c8a90b01e99b68da0f9796d109d7f161e9c848d2f8100651731c6dfe3f56f806',
    'gg': '08950dbb0d3cce0475b17c309d17f72c0b65ed02e9e99cf1b9a4138afe50747b',
    'md': 'd9bd59e01303a56a92e619aef54f67203fa7d0b3a7cb3211addc0562d6f9aa18',
    'nes': 'c98420ac1dfde068026e7fb72da97844714b6a31e6536cca93ff012add168715',
    'sms': '3897d8b37cffe8a438fd12cb7b522c9fac5222c5b94c9eb045457ef557e2fa7b',
}
# Quick-state keys of release 1.6.3 (Windows), from the v1.6.3 tag; the same code gives the documented 1.5.6 and 1.6.2
# keys from their tags. The Mega Drive and Super Nintendo keys are ALSO the keys of this tree: nothing they hash moved
# between 1.6.3 and 1.6.4, so the states of 1.6.3 match the build's own key and nothing is listed for them. The Neo Geo
# key moves in this tree only because the rollover edits `neogeo_build` (whose fingerprint it hashes) and its state files
# are byte for byte those of 1.6.3, so it is listed. The CPS-1 key moves with a new state (magic CPS1S002): not listed.
MD_STATE_ABI_163 = '0936bfb95573df62b23bf4da16a1986582f3cc7248c05e35aa61676e282fb35a'
SNES_STATE_ABI_163 = '3cd5b33673547616ed4cf05feddeb7e485137d0f312cb666556e660544f74237'
NEO_GEO_STATE_ABI_163 = 'b04f023a36534c86af7527d56e532b4f4e4a458aa1e5b70fa6656e18ede9ee18'
CPS1_STATE_ABI_163 = '01476848d6aa8b8e27d129550e9658b8174bfb0e9521ae75b5430f28f97e5ad4'
# Keys of release 1.6.2 (the previous release of the tree of 1.6.3): owed to nobody any more.
STATE_ABI_162_REMOVED = {
    'md': '7943c469d11b059b7cf2a6ff4597dc2809d25cd5b093752d837c2a4d8c661948',
    'snes': 'b9fbf76dc2cc49459420ff111d143c64c72cd72b440a1264d91b38be21bcb5c4',
    'ng': '0d361a5f02f0f6838bf555dce0b89dd8fa1dce8cd23045fd2811653fec0720df',
    'cps1': 'b24053cfe60639a1a464f74e63d155dcb351ac0713796e554937edd65821d8e9',
}
# Keys of release 1.6.1: owed to nobody any more.
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
NINE = ('cps1', 'gb', 'gg', 'md', 'nes', 'ng', 'sms', 'snes', 'x68')


class LegacyStampTests(unittest.TestCase):
    def test_the_table_is_empty_in_1_6_4_and_lists_nothing_older(self):
        # 1.6.4 is a structural release with a full reconversion of every console: no stamp of 1.6.3 or of any older
        # release is listed, and no console is upgraded from a previous export.
        self.assertEqual(inputs.LEGACY_GAME_STAMPS, {})
        for system in sorted(inputs.SYSTEMS):
            self.assertEqual(inputs.legacy_game_stamps(system), (), system)
        self.assertEqual(inputs.legacy_game_stamps('unknown'), ())

    def test_the_stamps_of_1_6_3_are_recorded_for_the_nine_consoles_and_none_is_current(self):
        for table in (GAME_STAMPS_163, HOST_STAMPS_163, BUILD_STAMPS_163, GAME_STAMPS_163_LINUX, HOST_STAMPS_163_LINUX,
                      BUILD_STAMPS_163_LINUX):
            self.assertEqual(tuple(sorted(table)), NINE)
            for stamp in table.values():
                self.assertRegex(stamp, r'^[0-9a-f]{64}$')
        # Two converters, two stamps per console: the Python of the Linux converter fingerprints the bytecode differently.
        for system in NINE:
            self.assertNotEqual(GAME_STAMPS_163[system], GAME_STAMPS_163_LINUX[system], system)
        for system in sorted(inputs.SYSTEMS & set(NINE)):
            # The registry refactor and the SDL pin move the game stamp of every console (docs/UPGRADES.md).
            current = inputs.role_stamps(system)['game']
            self.assertNotEqual(current, GAME_STAMPS_163[system], system)
            self.assertNotEqual(current, GAME_STAMPS_163_LINUX[system], system)

    def test_nothing_older_is_listed_either(self):
        listed = {stamp for stamps in inputs.LEGACY_GAME_STAMPS.values() for stamp in stamps}
        self.assertFalse(listed)
        recorded = set()
        for table in (GAME_STAMPS_156_REMOVED, GAME_STAMPS_160_REMOVED, GAME_STAMPS_161_REMOVED,
                      GAME_STAMPS_161_LINUX_REMOVED, GAME_STAMPS_162_REMOVED, GAME_STAMPS_162_LINUX_REMOVED):
            recorded |= set(table.values())
        self.assertEqual(listed & recorded, set())

    def test_the_x68000_has_no_entry_in_any_release(self):
        # Its request holds `x68_sdk`, hash of the game stamp of the tree that wrote it: not covered by the table.
        self.assertEqual(inputs.legacy_game_stamps('x68'), ())
        self.assertNotIn('x68', inputs.LEGACY_GAME_STAMPS)
        for stamp in (GAME_STAMPS_163['x68'], GAME_STAMPS_163_LINUX['x68'], GAME_STAMPS_162_REMOVED['x68'],
                      GAME_STAMPS_162_LINUX_REMOVED['x68'], X68_GAME_STAMP_161_NOT_LISTED,
                      X68_GAME_STAMP_161_LINUX_NOT_LISTED, X68_GAME_STAMP_160_NOT_LISTED):
            self.assertRegex(stamp, r'^[0-9a-f]{64}$')

    def test_entries_of_the_previous_release_are_wellformed_and_never_the_current_stamp(self):
        # What a later release adds: a 64-digit game stamp per listed console, never today's.
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
    whatever today's game stamp is; any other game part is converted in full. The listed stamp here is synthetic, since
    the table of 1.6.4 is empty."""

    def parts(self, system, game_stamp=None):
        from retrorecomp import freshness
        item = SimpleNamespace(system=system, path=Path('game.bin'), sha256='e' * 64, title='Game', cover=None)
        real = inputs.role_stamps
        stamps = (lambda name: {**real(name), 'game': game_stamp}) if game_stamp else real
        with patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}), \
                patch('retrorecomp.paths.selected_bios_path', return_value=Path('neogeo.zip')), \
                patch('retrorecomp.compilation_inputs.role_stamps', side_effect=stamps):
            return item, freshness.request_parts(item, {'use_cover': False})

    def receipt(self, folder, item, game, release='1.6.3', schema=3):
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
                    self.assertEqual(previous['legacy_release'], '1.6.3')
                    self.assertEqual(freshness.upgrade_record(previous)['from_release'], '1.6.3')
                    # Any other game part (an older release, other code) is converted in full.
                    target, path = self.receipt(folder, item, 'f' * 64)
                    self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_a_1_6_3_receipt_of_any_console_is_converted_in_full(self):
        # 1.6.4 lists nothing: the game stamp a real 1.6.3 receipt carries (Windows or Linux converter) is not recognised,
        # whatever the console, so every export of 1.6.3 is converted in full (the base of qualified paths still applies).
        from retrorecomp import freshness
        for system in sorted(inputs.SYSTEMS - {'x68'}):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                item, parts = self.parts(system)
                self.assertEqual(parts['legacy_games'], [])
                for stamps in (GAME_STAMPS_163, GAME_STAMPS_163_LINUX):
                    game = self.parts(system, stamps[system])[1]['game']
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        target, path = self.receipt(folder, item, game)
                        self.assertIsNone(freshness.current(item, target, path, parts['request'], print))
                        self.assertIsNone(freshness.upgradable(item, target, path, parts, print))

    def test_nothing_is_upgraded_from_a_release_the_table_does_not_list(self):
        # 1.5.6, 1.6.0, 1.6.1 and 1.6.2 (listed by the tables of earlier trees, not by this one) and any other game part:
        # converted in full.
        from retrorecomp import freshness
        for release, removed in (('1.5.6', GAME_STAMPS_156_REMOVED), ('1.6.0', GAME_STAMPS_160_REMOVED),
                                 ('1.6.1', GAME_STAMPS_161_REMOVED), ('1.6.1', GAME_STAMPS_161_LINUX_REMOVED),
                                 ('1.6.2', GAME_STAMPS_162_REMOVED), ('1.6.2', GAME_STAMPS_162_LINUX_REMOVED)):
            for system in sorted(removed):
                if system == 'x68':
                    continue
                with self.subTest(release=release, system=system), tempfile.TemporaryDirectory() as folder:
                    item, parts = self.parts(system)
                    self.assertEqual(parts['legacy_games'], [])
                    old = self.parts(system, removed[system])[1]['game']
                    with patch('retrorecomp.freshness._no_new_hints', return_value=True):
                        for game in (old, 'f' * 64):
                            target, path = self.receipt(folder, item, game, release)
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

    @staticmethod
    def own_key(text):
        return re.search(r'#define RR16_STATE_ABI "([0-9a-f]{64})"', text).group(1)

    def test_the_mega_drive_super_nintendo_and_neo_geo_list_no_compatibility_key(self):
        # Decision of 29 October 2026 (from 1.6.5): quick states need not survive an update. 1.6.5 moved
        # native/video_mode4.inc and native/video_checks.c out of the all-consoles group, which changes what these keys
        # hash (the serialized bytes did not change); no compatibility key is listed, so a quick state of an earlier
        # release is refused cleanly (docs/GAME_STATES.md). Cartridge saves are not quick states and are unaffected.
        # The Neo Geo key moved again in 1.6.5 (neogeo_build edited): its 1.6.3 key is no longer listed either.
        texts = self.configs()
        self.assertNotEqual(self.own_key(texts['md']), MD_STATE_ABI_163)
        self.assertNotEqual(self.own_key(texts['ng']), NEO_GEO_STATE_ABI_163)
        for system in ('md', 'snes', 'ng'):
            self.assertNotIn('RR16_STATE_COMPAT_ABI', texts[system], system)

    def test_the_cps1_state_changed_so_the_states_of_1_6_3_are_refused(self):
        # Lot B: magic CPS1S002, every structure of the state written field by field. The key moved with it and no
        # compatibility line is written.
        text = self.configs()['cps1']
        self.assertNotIn('RR16_STATE_COMPAT_ABI', text)
        self.assertNotEqual(self.own_key(text), CPS1_STATE_ABI_163)
        machine = (ASSETS / 'native' / 'cps1_machine.c').read_text(encoding='utf-8')
        self.assertIn('#define STATE_MAGIC "CPS1S002"', machine)
        self.assertNotIn('CPS1S001', machine)

    def test_the_layout_versions_the_1_6_3_keys_stand_for_did_not_move(self):
        # The keys hash files; what is serialized is fixed by these versions and the state files, none of which changed
        # between the v1.6.3 tag and 1.6.4 for the Mega Drive, the Super Nintendo and the Neo Geo.
        from retrorecomp import console16_state
        self.assertEqual((console16_state.PORTABLE_STATE_ABI, console16_state.MD_PORTABLE_STATE_ABI), (2, 11))
        for name in StateLayoutGuardTests.FILES:
            path = ASSETS / 'native' / name
            if path.is_file():
                self.assertNotIn('runtime_catalog', path.read_text(encoding='utf-8', errors='replace'), name)

    def test_no_state_key_of_a_release_before_1_6_3_is_accepted(self):
        texts = self.configs()
        for system, text in texts.items():
            for key in STATE_ABI_156_REMOVED:
                self.assertNotIn(key, text, system)
            for removed in (STATE_ABI_160_REMOVED, STATE_ABI_161_REMOVED, STATE_ABI_162_REMOVED):
                self.assertNotIn(removed[system], text, system)
            self.assertNotRegex(text, r'RR16_STATE_COMPAT_ABI_\d', system)
        # The 1.6.2 keys are not 1.6.3 keys either, and the Super Nintendo key of 1.6.0 and 1.6.1 was one and the same.
        for system, key in (('md', MD_STATE_ABI_163), ('snes', SNES_STATE_ABI_163), ('ng', NEO_GEO_STATE_ABI_163),
                            ('cps1', CPS1_STATE_ABI_163)):
            self.assertNotEqual(key, STATE_ABI_162_REMOVED[system], system)
        self.assertEqual(STATE_ABI_161_REMOVED['snes'], STATE_ABI_160_REMOVED['snes'])

    def test_the_state_key_constants_are_those_of_1_6_3_only(self):
        from retrorecomp import console16_state, cps1_build, neogeo_build
        for module in (console16_state, cps1_build, neogeo_build):
            for name in dir(module):
                match = re.search(r'STATE_ABI_(\d+)$', name)
                if match:
                    self.assertEqual((module, match.group(1)), (neogeo_build, '163'), (module.__name__, name))
        for module, name in ((console16_state, 'MD_STATE_ABI_162'), (console16_state, 'SNES_STATE_ABI_162'),
                             (neogeo_build, 'STATE_ABI_162'), (cps1_build, 'LEGACY_STATE_ABI_162'),
                             (console16_state, 'MD_STATE_ABI_161'), (console16_state, 'SNES_STATE_ABI_161'),
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
    """No compatibility line on either platform from 1.6.5 (it was a Windows-only 1.6.3 key until 1.6.4)."""

    def test_the_neo_geo_writes_no_compatibility_line_on_any_platform(self):
        from retrorecomp import neogeo_build
        real = os

        class FakeOs:
            def __init__(self, name):
                self.name = name

            def __getattr__(self, attribute):
                return getattr(real, attribute)

        for name, listed in (('nt', False), ('posix', False)):
            with self.subTest(name=name), \
                    patch('retrorecomp.neogeo.parse_neo', return_value=SimpleNamespace(sha256='a' * 64)), \
                    patch('retrorecomp.neogeo.validate_bios', return_value={'sha256': 'b' * 64}), \
                    patch('retrorecomp.neogeo_build.os', FakeOs(name)), \
                    patch('retrorecomp.platforms.target_id', return_value='linux-x86_64'):
                text = neogeo_build.state_config(Path('cartridge.neo'), Path('neogeo.zip'), 'Test')
            self.assertEqual(f'#define RR16_STATE_COMPAT_ABI "{NEO_GEO_STATE_ABI_163}"' in text, listed)
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
