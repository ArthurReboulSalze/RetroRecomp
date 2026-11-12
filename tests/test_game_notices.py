"""Each game embeds the notices of the components compiled into it, and each notice file is a stamp input of the machines
that embed it only (retrorecomp/notices.py, `SystemProfile.notice_files`; docs/UPGRADES.md)."""
import unittest
from unittest.mock import patch

from retrorecomp import compilation_inputs as inputs
from retrorecomp import notices, stamp_inputs
from retrorecomp.paths import ASSETS
from retrorecomp.systems import ALL_PROFILES, SHELL_NOTICE_FILES, SystemProfile, get_profile
from retrorecomp.upstreams import MACHINE_UPSTREAMS

# The notice file(s) that carry each upstream's terms in a game. One of the files of an entry must be declared by every
# machine that compiles the upstream; a new upstream is added here with its notice.
UPSTREAM_NOTICES = {
    'smsggrecomp': ('licenses/smsggrecomp.md',),
    'z80-recomp-core': ('licenses/z80-recomp-core.md',),
    'gb-recompiled': ('licenses/gb-recompiled.md',),
    'nesrecomp': ('licenses/nesrecomp.md',),
    'segagenesisrecomp': ('licenses/segagenesisrecomp.md',),
    'm68k-recomp-core': ('licenses/segagenesisrecomp.md',),      # the page holds the submodule's terms too
    'snesrecomp': ('licenses/snesrecomp.md',),
    'pcenginerecomp': ('licenses/pcenginerecomp.md',),
    'beetle-psx-libretro': ('licenses/beetle-psx.md',),
    # Geolith's own BSD terms cover the Neo Geo machine; the CPS family and the X68000 compile only its Musashi copy.
    'geolith-libretro': ('licenses/geolith.md', 'licenses/musashi.md'),
    'lithogen': ('licenses/lithogen.md',),
    'ymfm': ('licenses/cps1-ymfm.md',),
    'mame': ('licenses/cps1-machine.md',),
    'gbarecomp': ('licenses/gbarecomp.md',),
    'arm-recomp-core': ('licenses/gbarecomp.md',),               # the page holds the submodule's MIT terms too
    'px68k': ('licenses/x68000-machine.md',),
    'vamiga': ('licenses/vamiga.md',),
    'hatari': ('licenses/hatari.md',),
    'EmuTOS': ('licenses/emutos.md',),
    'mupen64plus-next': ('licenses/mupen64plus-next.md',),
    'ScummVM': ('licenses/scummvm.md',),
    'FreeType': ('licenses/freetype.md',),
    'C-BIOS': ('licenses/cbios.md',),                          # the MSX and MSX2: optional, in a game that boots it
}
# Upstreams a machine follows without compiling any of their code into its games, each with the reason
# (retrorecomp/upstreams.py says the same in its `compiled` column or beside MACHINE_UPSTREAMS).
NOT_COMPILED = {
    ('md', 'z80-recomp-core'): 'a submodule of the engine; the Mega Drive game builds its own sound-Z80 runtime',
    ('md', 'rbengine'): 'a submodule of the engine that only upstream\'s own tests link',
    ('x68', 'px68k-libretro'): 'the private GPL comparison mode: nothing is compiled or shipped',
    ('atarist', 'segagenesisrecomp'): 'the generator\'s 68000 decoder runs at conversion time; the bodies are Hatari\'s handlers',
    ('atarist', 'm68k-recomp-core'): 'the generator\'s 68000 decoder runs at conversion time; the bodies are Hatari\'s handlers',
}


def embedded(profile: SystemProfile) -> str:
    return notices.notice_text(profile.id, optional=profile.optional_notice_files)


class NoticeTextTests(unittest.TestCase):
    def test_every_game_text_holds_each_declared_notice_and_our_own_licence(self):
        own = (ASSETS / 'LICENSE').read_text(encoding='utf-8').strip()
        for profile in ALL_PROFILES:
            with self.subTest(machine=profile.id):
                text = embedded(profile)
                self.assertTrue(profile.notice_files, 'a machine names the components compiled into its games')
                self.assertIn(own, text)
                for name in profile.declared_notice_files:
                    self.assertIn((ASSETS / name).read_text(encoding='utf-8').strip(), text, name)
                self.assertEqual(text.count('## Retro-Recomp\n'), 1)

    def test_an_optional_notice_is_embedded_only_on_request_and_must_be_declared(self):
        emutos = (ASSETS / 'licenses/emutos.md').read_text(encoding='utf-8').strip()
        self.assertNotIn(emutos, notices.notice_text('atarist'))
        self.assertIn(emutos, notices.notice_text('atarist', optional=('licenses/emutos.md',)))
        self.assertNotIn('licenses/emutos.md', notices.notice_files('atarist'))
        with self.assertRaises(ValueError):
            notices.notice_text('nes', optional=('licenses/emutos.md',))

    def test_a_missing_declared_notice_is_an_error_not_a_silent_gap(self):
        class Broken(type(get_profile('nes'))):
            notice_files = ('licenses/absent-component.md',)
        with patch.object(notices, 'get_profile', lambda system_id: Broken()):
            with self.assertRaises(OSError):
                notices.notice_text('nes')

    def test_engine_texts_are_added_after_the_declared_ones(self):
        text = notices.notice_text('md', extra=[('vendored part', 'Copyright (c) someone\n')])
        self.assertTrue(text.endswith('## vendored part\n\nCopyright (c) someone\n'))

    def test_the_complete_public_list_is_in_no_game(self):
        public = (ASSETS / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
        for profile in ALL_PROFILES:
            self.assertNotIn(public[:400], embedded(profile), profile.id)
            self.assertNotIn('THIRD_PARTY_NOTICES.md', inputs.manifest_names(profile.id))


class CoverageTests(unittest.TestCase):
    def test_the_declared_notices_cover_the_upstreams_of_each_machine(self):
        for profile in ALL_PROFILES:
            declared = set(profile.declared_notice_files)
            for upstream in MACHINE_UPSTREAMS[profile.id]:
                with self.subTest(machine=profile.id, upstream=upstream.key):
                    if (profile.id, upstream.key) in NOT_COMPILED:
                        continue
                    self.assertIn(upstream.key, UPSTREAM_NOTICES, 'name the notice file of this upstream in UPSTREAM_NOTICES')
                    self.assertTrue(declared & set(UPSTREAM_NOTICES[upstream.key]),
                                    f'{profile.id} compiles {upstream.key}: declare its notice on the profile (notice_files)')

    def test_the_exceptions_name_real_upstreams(self):
        for machine, key in NOT_COMPILED:
            self.assertIn(key, {upstream.key for upstream in MACHINE_UPSTREAMS[machine]}, (machine, key))

    def test_the_shell_notices_follow_what_a_game_is_built_with(self):
        self.assertEqual(set(SHELL_NOTICE_FILES), {'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/misc-fixed.md',
                                                   'licenses/llvm-mingw.md', 'licenses/UPX.md'})
        for profile in ALL_PROFILES:
            with self.subTest(machine=profile.id):
                declared = set(profile.declared_notice_files)
                # SDL2 and the compiler's runtime are linked into every executable, the adventure runtime included.
                self.assertLessEqual({'licenses/SDL2.md', 'licenses/llvm-mingw.md'}, declared)
                # The menu fonts, the xBR filter and the packer come with the player shell: a machine on the host kit
                # carries them all. Only a program that is not built on the shell (the adventure runtime) lists its own.
                self.assertEqual(profile.shell_notices, set(SHELL_NOTICE_FILES) <= declared)
                if profile.host_adapter:
                    self.assertTrue(profile.shell_notices)
                if not profile.shell_notices:
                    self.assertEqual(profile.id, 'scummvm')
        # Games hold no Noto glyph (docs/LANGUAGES.md): the interface's font notice is in no game.
        self.assertFalse(any('licenses/Noto.md' in profile.declared_notice_files for profile in ALL_PROFILES))


class OwnershipTests(unittest.TestCase):
    def owners(self, name):
        return {profile.id for profile in ALL_PROFILES if name in inputs.manifest_names(profile.id)}

    def test_a_notice_is_a_host_input_of_exactly_the_machines_that_embed_it(self):
        embedders = {}
        for profile in ALL_PROFILES:
            for name in profile.declared_notice_files:
                embedders.setdefault(name, set()).add(profile.id)
        for name, machines in embedders.items():
            with self.subTest(notice=name):
                self.assertEqual(self.owners(name), machines)
                if name.startswith('licenses/'):
                    self.assertEqual(inputs.role(name), 'host')
        listed = {name for name in inputs.manifest_names() if name.startswith('licenses/')}
        self.assertEqual(listed, {name for name in embedders if name.startswith('licenses/')},
                         'a licence file is a stamp input only through a profile that embeds it')
        self.assertNotIn(stamp_inputs.ALL, [key for key, names in stamp_inputs.INPUTS.items()
                                            if any(name.startswith('licenses/') for name in names)])

    def test_the_builder_is_a_host_module_of_every_machine(self):
        self.assertEqual(inputs.role('retrorecomp.notices'), 'host')
        self.assertIn('retrorecomp.notices', stamp_inputs.INPUTS[stamp_inputs.ALL])

    def test_a_new_machines_notice_moves_no_other_machines_stamp(self):
        """A hypothetical machine that declares one new notice file: the inputs (names and contents) of every existing
        machine stay what they were, so their host, game and build stamps cannot move."""
        before = {profile.id: inputs.input_fingerprints(profile.id) for profile in ALL_PROFILES}
        stamps = {profile.id: inputs.role_stamps(profile.id) for profile in ALL_PROFILES}

        class NewMachine(type(get_profile('nes'))):
            id = 'newmachine'
            notice_files = ('licenses/new-machine-bios.md',)
            host_adapter = None

        profiles = (*ALL_PROFILES, NewMachine())
        raw = {('newmachine',): ('retrorecomp.systems.nes',)}
        with patch.object(stamp_inputs, 'ALL_PROFILES', profiles):
            resolved = stamp_inputs._resolve(raw)
        owners = {name: key for key, names in resolved.items() for name in names}
        self.assertEqual(owners['licenses/new-machine-bios.md'], ('newmachine',))
        # The shell's notices gain an owner; no existing machine gains or loses a name.
        self.assertIn('newmachine', owners['licenses/SDL2.md'])
        for profile in ALL_PROFILES:
            mine = {name for key, names in resolved.items() if profile.id in key for name in names if name.startswith('licenses/')}
            self.assertEqual(mine, {name for name in profile.declared_notice_files if name.startswith('licenses/')}, profile.id)
            self.assertNotIn('licenses/new-machine-bios.md', mine)
        # And with the new file really listed, the fingerprints and stamps of the existing machines are unchanged.
        listed = {**stamp_inputs.INPUTS, ('newmachine',): ('licenses/new-machine-bios.md',)}
        with patch.object(inputs, 'INPUTS', listed):
            for profile in ALL_PROFILES:
                self.assertEqual(inputs.input_fingerprints(profile.id), before[profile.id], profile.id)
                self.assertEqual(inputs.role_stamps(profile.id), stamps[profile.id], profile.id)

    def test_one_machines_notice_moves_only_its_owners_host_stamp(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in inputs.manifest_names():
                if not name.startswith('retrorecomp.'):
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_bytes((ASSETS / name).read_bytes())
            with patch('retrorecomp.paths.ASSETS', root):
                before = {profile.id: inputs.role_stamps(profile.id) for profile in ALL_PROFILES}
                (root / 'licenses/pcenginerecomp.md').write_text('a new notice of the PC Engine engine\n', encoding='utf-8')
                after = {profile.id: inputs.role_stamps(profile.id) for profile in ALL_PROFILES}
        for profile in ALL_PROFILES:
            with self.subTest(machine=profile.id):
                if profile.id == 'pce':
                    self.assertNotEqual(before['pce']['host'], after['pce']['host'])
                    self.assertEqual(before['pce']['game'], after['pce']['game'])
                else:
                    self.assertEqual(before[profile.id], after[profile.id])


if __name__ == '__main__':
    unittest.main()
