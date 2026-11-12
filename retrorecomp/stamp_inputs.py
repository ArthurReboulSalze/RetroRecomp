"""The inputs of the stamps, as data (docs/STANDARDS.md rules 4 and 5).

This module holds tables and no logic (but for the derivation of one CPU family's
owners from the profiles). `compilation_inputs` reads it to compute
the stamps (game, host and build) of each console's exported games.

* `INPUTS` is the explicit, reviewed manifest: every converter module and every
  file that may enter a stamp, grouped by the consoles that own it. Nothing is
  discovered on disk. It is the only place an owner is stated (there is no
  default scope by file name); the consoles of a CPU family come from the
  profiles. A file or module that is not listed here is ignored by the stamps,
  and a listed one that is missing is an error. A new file is therefore added
  here, with its owners, when it is created;
  `tests/test_stamp_inputs.py` fails when a tracked file is neither listed nor
  declared out of the stamps, and when a listed file is not bundled in the
  executable.
* `INTERFACE_MODULES` are modules no stamp ever hashes. This module and
  `compilation_inputs` are among them: they define how a stamp is computed and
  what it covers, and that is already visible in the stamps, which hash the
  names and contents of the inputs actually listed. Hashing them as game code
  moved every console's stamp whenever a console's file list, the interface
  list or `LEGACY_GAME_STAMPS` was edited. A change of the algorithm itself
  must bump the label in `compilation_inputs` (`STAMP_LABEL`); a test pins the
  output of the algorithm on a fixed synthetic input. `systems/registry.py`, the
  registration list of the machines, is one too: registering a machine moves no
  other console's stamp.
* The role tables (`HOST_*`, `BUILD_MODULES`) say which stamp a listed input
  feeds. See docs/UPGRADES.md.
* `LEGACY_GAME_STAMPS` lists the game stamps of the previous release only, whose
  exports stay upgradable. Editing it never changes a stamp.
"""

from .systems import ALL_PROFILES

# Owner of an input that every console uses (including a console added later).
ALL = '*'

# The consoles that own the files of one CPU family: those whose profile declares the CPU. A machine with that CPU
# joins the family by being registered (systems/registry.py), not by an edit here.
M68000_FAMILY = tuple(profile.id for profile in ALL_PROFILES if any(cpu.arch == 'm68000' for cpu in profile.cpus))
# The machines on the 16-bit host family (quick-state ABI 'rr16') and those on the host kit (they name an adapter).
RR16_FAMILY = tuple(profile.id for profile in ALL_PROFILES if profile.quick_state_family == 'rr16')
HOST_KIT_FAMILY = tuple(profile.id for profile in ALL_PROFILES if profile.host_adapter)


def sharing(group: str) -> tuple:
    """The machines whose profile reuses one shared group of files (`SystemProfile.stamp_groups`)."""
    return tuple(profile.id for profile in ALL_PROFILES if group in profile.stamp_groups)


INTERFACE_MODULES = frozenset(('__init__', 'gui', 'i18n', 'ui_fonts', 'tooltips',
                               # The window, split by responsibility (gui.py assembles the Application).
                               'gui_common', 'gui_drawing', 'gui_window', 'gui_queue', 'gui_conversion',
                               'gui_collection', 'gui_updates', 'gui_options', 'gui_sharing', 'gui_reports',
                               'gui_account', 'gui_leaderboard',
                               'dropfiles', 'updater', 'linux_desktop', 'queue_state',
                               'credits_demo', 'credits_music', 'dialogs',
                               'compiled_games', 'compiled_games_view', 'memory_view',
                               'report_schema',
                               # Declares the pinned upstreams per machine (docs/UPSTREAMS.md); a conversion never reads it.
                               'upstreams',
                               # Measures the time of each phase of a conversion; changes nothing a game is or does.
                               'timings',
                               'game_details','game_metadata','game_card_view','rom_sources',
                               # Sharing discoveries never runs during a conversion.
                               'knowledge_build','knowledge_exchange','online','shared_batch',
                               # Removes build folders once a game is published;
                               # it never changes what a game is or does.
                               'build_cleanup',
                               # The registration list of the machines: a new machine adds one line there and
                               # no other console's stamp moves (docs/NEW_MACHINE.md).
                               'registry',
                               # The definition of the stamps: see the docstring above.
                               'compilation_inputs', 'stamp_inputs'))

# Build (how a game is compiled) versus game: see docs/COMPILATION_LIBRARY.md.
# A build input chooses and drives the C toolchain (portable llvm-mingw or Visual
# Studio), or packs the finished executable (packing: UPX, which restores the
# same program in memory before it starts). It never decides which guest code a
# game runs. A change limited to build inputs rebuilds an export from the paths
# already learned, like a host change, because the executable is recompiled and
# rechecked on the quick routes.
BUILD_MODULES = frozenset(('toolchain', 'packing', 'scummvm_build'))

# Game stamps of the PREVIOUS release only, whose exports stay upgradable: the code that
# differed from today's was only how the game is built, and the exports were
# rebuilt and compared frame by frame with the new build before being listed
# (docs/COMPILATION_LIBRARY.md). A receipt with one of these stamps is never
# current: it is always rebuilt and rechecked, or converted in full.
# Backward compatibility is owed to the previous release only (decision of
# 28 October 2026): the table never holds an entry for a release older than
# that one, and a console whose previous-release game code really differs from
# today's has no entry either. A player coming from an older release reconverts.
# Release procedure: replace the entries with those of the release being left
# (one real receipt per console, proved build-only); never add them to the
# older ones. The table was empty in the tree of 1.6.0; the tree of 1.6.1 listed the stamps of 1.6.0; the tree of 1.6.2
# listed those of 1.6.1; the tree of 1.6.3 listed those of 1.6.2 (Master System, Game Gear, Game Boy and NES).
# The tree of 1.6.4 lists NONE (decision of the maintainer, 29 October 2026): 1.6.4 is a structural release, a full
# reconversion of every console. SDL 2.32.10 is linked into every game (`core.SDL_REV`) and the registry refactor moves
# every game stamp; on top of that six consoles change in their own way (the NES and CPS-1 quick-state bytes, the CPS-1
# graphics-RAM code, the Master System and Game Gear "functions" engine, the Game Boy writable-memory executor and
# counting, the X68000 payload paths), and the release procedure lists no console in that case. The game stamps of
# release 1.6.3 (tag v1.6.3, commit bb2aa95; Windows with Python 3.14.5, Linux with Python 3.13.5), computed for all nine
# consoles, are kept as evidence in docs/COMPILATION_LIBRARY.md ("Release 1.6.3 entries") and tests/test_legacy_compat.py,
# unlisted. Evidence and limits: docs/UPGRADES_HISTORY.md, "Exports of 1.6.3 in 1.6.4". The X68000 would have no entry in any
# case: its request carries an SDK stamp (`x68_sdk`) derived from the game stamp, which this mechanism does not recompute.
LEGACY_GAME_STAMPS: dict[str, tuple[str, ...]] = {}

# Host (the player shell) versus game: see docs/UPGRADES.md. Host inputs draw
# the window, menus, options, bindings, on-screen text, fonts, filters, icons
# and notices, play sound out, and save preferences. The headless runs that
# discover and validate a game's code never use them; those go through each
# console's entry (launcher, main, runner), which stays on the game side. A
# change limited to host inputs upgrades an export without rediscovery.
# Everything not listed is game-side, so an unclassified input fails closed.
HOST_MODULES = frozenset((
    # Embedded artwork, box icons and Windows executable information.
    'artwork', 'cover_keyring', 'cover_references', 'cover_settings', 'cover_sources',
    'cover_titles', 'metadata', 'languages',
    # Placing the finished EXE beside the others.
    'publishing', 'windows',
    # Converter-only shells.
    'branding', 'player_gamepad',
    # Player shells written as patches: the Game Boy platform layer on the host kit (1.6.3);
    # Mega Drive sound delivery.
    'gameboy_host', 'megadrive_audio',
    # The host kit's file list and its copy into a game project.
    'hostkit'))
HOST_NATIVE = frozenset((
    # Paths below native/. Shared menu core, identical on every machine.
    'retro_menu.c', 'retro_menu.h', 'game_options.h', 'game_options_checks.c',
    'autofire.h', 'retro_keyboard.h',
    # On-screen text and fonts.
    'runtime_catalog.inc', 'runtime_i18n.h', 'language_checks.c', 'font6x10.h', 'font10x20.h',
    # Presentation filters, display settings and the window icon.
    'scale2x.h', 'scanlines.h', 'scanline_sdl.h', 'xbr_filter.h', 'xbr_sdl.h', 'xbr_checks.c',
    'display_settings.h', 'display_settings_checks.c', 'icon.c', 'icon.h', 'icon_checks.c',
    # Sound output after each machine's emulated mixer.
    'audio_filter.h', 'audio_cushion.h', 'audio_output.inc', 'audio_checks.c',
    'nes_audio_checks.c',
    'md_audio_loop.inc', 'md_audio_resample.inc',
    # Converter-only controller bridge (never linked into games).
    'player_gamepad.c',
    'neogeo_ui_test.c',
    # The host kit (docs/HOST_KIT.md): the shell shared by every console, and the adapter of each. Every file
    # below native/hostkit is host-side.
    'hostkit/hostkit.h', 'hostkit/hostkit_internal.h',
    'hostkit/shell/rrhk_audio.c', 'hostkit/shell/rrhk_events.c', 'hostkit/shell/rrhk_input.c',
    'hostkit/shell/rrhk_main.c', 'hostkit/shell/rrhk_menu.c', 'hostkit/shell/rrhk_options.c',
    'hostkit/shell/rrhk_pointer.c', 'hostkit/shell/rrhk_ring.c', 'hostkit/shell/rrhk_timing.c',
    'hostkit/shell/rrhk_video.c',
    # (the adapters of the machines on the kit are added from their profiles below)
    'hostkit/adapters/rrhk_x68k.inc', 'hostkit/adapters/rrhk_computer.inc', 'hostkit/adapters/rrhk_amiga.inc',
    'hostkit/adapters/rrhk_atarist.inc', 'hostkit/adapters/rrhk_n64.inc')) | frozenset('hostkit/' + profile.host_adapter for profile in ALL_PROFILES
                                                    if profile.host_adapter)
HOST_FILES = frozenset(('THIRD_PARTY_NOTICES.md',))
HOST_PREFIXES = ('licenses/', 'assets/Retro-Recomp-icon-', 'assets/Retro-Recomp.ico',
                 'assets/tag-shooting.png')


# How a listed file is hashed. Text is hashed with its line ends normalised
# (CRLF becomes LF), so a Windows working tree, `git archive` and Linux agree;
# `.gitattributes` also pins LF for these types. Binary files are hashed as is.
# A listed file whose type is in neither set is an error: classify it here.
TEXT_SUFFIXES = frozenset(('.c', '.cmake', '.cpp', '.def', '.h', '.hpp', '.inc', '.json', '.md', '.py', '.rc', '.toml', '.txt'))
BINARY_SUFFIXES = frozenset(('.gz', '.ico', '.otf', '.png', '.xz'))
# Text files whose exact bytes are pinned by a checksum (-text in .gitattributes).
RAW_FILES = frozenset(('assets/neogeo-catalogue.json', 'assets/cps1-catalogue.json', 'assets/cps2-catalogue.json',
                       # The ScummVM patch is applied byte for byte (-text) and the GPL text is pinned LF (.gitattributes).
                       'native/scummvm/patches/0001-retrorecomp-pack-launch-nodialog.patch',
                       'native/scummvm/patches/0002-retrorecomp-options-page.patch', 'native/scummvm/patches/0003-retrorecomp-theme-colours.patch', 'native/scummvm/LICENSE'))

# Tracked files below native/, assets/, profiles/ and licenses/ that are deliberately not
# inputs of any stamp (exact paths, or prefixes ending in '/' or '-'): interface pictures
# and fonts, the converter-only leaderboard pictures, the locales and the credits, the
# knowledge snapshot and the cover and font tables, the UPX tools and their source archive.
# tests/test_stamp_inputs.py fails for a tracked file in those folders that is neither
# listed in INPUTS nor declared here.
NOT_INPUTS = (
    'assets/Retro-Recomp-banner.png', 'assets/Retro-Recomp-consoles.png',
    'assets/RetroRecomp-UI-JP.otf', 'assets/RetroRecomp-UI-SC.otf', 'assets/board-',
    'assets/compilation-knowledge.json.gz', 'assets/cover-references.json', 'assets/font-coverage.json',
    'assets/credits/', 'assets/locales/', 'assets/tools/',
    'licenses/upx-5.3.0-src.tar.xz',
    # The SM83 vectors are fetched for development tests and never shipped: their licence and their line in the upstream table move no stamp.
    'licenses/SingleStepTests-sm83.md', 'licenses/SingleStepTests-huc6280.md',
    # Developer harnesses (tools/cps1_vector_selftest.py, tools/cps1_z80_vector_selftest.py, tools/neogeo_vector_selftest.py,
    # tools/neogeo_z80_vector_selftest.py, tools/cps1_kabuki_selftest.py, tools/cps1_eeprom_selftest.py, tools/cps1_qsound_selftest.py,
    # tools/cps1_persistence_selftest.py, tools/x68000_vector_selftest.py, tools/gameboy_sm83_vector_selftest.py, tools/pce_huc6280_vector_selftest.py, tools/pce_huc6280_native_vector_selftest.py): never built
    # into a game, so they move no stamp.
    'native/cps1_vector_checks.c', 'native/cps1_z80_vector_checks.c', 'native/neogeo_vector_checks.c',
    'native/neogeo_z80_vector_checks.c', 'native/cps1_kabuki_checks.c',
    'native/cps1_eeprom_checks.c', 'native/cps1_qsound_checks.c', 'native/cps1_persistence_checks.c',
    'native/x68000_vector_checks.c', 'native/gb_sm83_vector_checks.c', 'native/pce_huc6280_vector_checks.cpp',
    'native/pce_huc6280_native_checks.cpp',
    # tools/amiga_vector_selftest.py (Moira and a native step against an independent corpus): built against the adapted vAmiga for a check,
    # never into a game (the folder's CMakeLists.txt does not build it).
    'native/amiga_machine/amiga_vector_checks.cpp',
    # tools/amiga_blitter_selftest.py (the Blitter's specialised routines against vAmiga's microprogram): the same, a check, never in a game.
    'native/amiga_machine/amiga_blit_checks.cpp',
    # tools/amiga_display_selftest.py (Agnus and Denise recorded instruction by instruction and frame by frame, for the fast paths to come): the same, a check, never in a game.
    'native/amiga_machine/amiga_display_checks.cpp',
    # Stage 7's bus model in shadow (after 1.7.3): compiled into the display self-test and, on request (RR_AMIGA_SHADOW, off by default),
    # into a private reference player; never into a game while it controls nothing. It joins the Amiga's game files when it takes control.
    'native/amiga_machine/amiga_bus.h', 'native/amiga_machine/amiga_bus.cpp',
    # tools/atarist_vector_selftest.py (the ST's cycle-exact 68000 against an independent corpus): built against the adapted Hatari for a
    # check, never into a game (the folder's CMakeLists.txt does not build it).
    'native/atarist_machine/atarist_vector_checks.c',
    # tools/atarist_hardware_check.py (authored 68000 programs measured against the hardware's documentation): built for a check only.
    'native/atarist_machine/atarist_hardware_checks.c',
    # tools/snes_cpu_vector_selftest.py (65816 and SPC700 against an independent corpus): never built into a game.
    'native/snes_cpu/cpu_vector_checks.c', 'native/snes_cpu/spc_vector_checks.c',
    # tools/gba_vector_selftest.py (the engine's ARM interpreter and generated code against an independent corpus): built against the
    # staged engine for a check, never into a game.
    'native/gba_vector_checks/',
    # tools/psx_vector_selftest.py (Beetle's R3000A interpreter, the native steps and its GTE against independent corpora): compiled with
    # Beetle's cpu.c for a check, never into a game.
    'native/psx_vector_checks/')

# The manifest: module names ('retrorecomp.x') and file paths below the bundle root,
# with the consoles that own each. A key is ALL, a tuple of console ids, or a name resolved from the profiles:
# 'family:rr16', 'family:host_kit', 'family:m68000' (what the profiles declare: quick-state family, host-kit adapter,
# CPUs) and 'shares:<group>' (the machines whose profile lists the group in `stamp_groups`). A machine joins a
# shared group by saying so in its profile, not by an edit here; its own files are one more tuple key.
_FAMILIES = {'family:rr16': RR16_FAMILY, 'family:host_kit': HOST_KIT_FAMILY, 'family:m68000': M68000_FAMILY}
# The names of the shared groups the manifest defines (a profile's `stamp_groups` must name some of them).
SHARED_GROUPS = set()


def _resolve(entries: dict) -> dict:
    """The manifest with every key an owner tuple. Groups with the same owners are merged, and what the profiles
    state alone is added: each machine's host-kit adapter file and (unless listed) its profile module."""
    resolved: dict = {}

    def add(owners, names):
        if owners:
            resolved[owners] = tuple(sorted({*resolved.get(owners, ()), *names}))

    for key, names in entries.items():
        if key == ALL or isinstance(key, tuple):
            owners = key
        elif key in _FAMILIES:
            owners = _FAMILIES[key]
        elif key.startswith('shares:'):
            SHARED_GROUPS.add(key.partition(':')[2])
            owners = sharing(key.partition(':')[2])
        else:
            raise ValueError('Unknown manifest key: ' + repr(key))
        resolved[owners] = tuple(sorted({*resolved.get(owners, ()), *names}))
    listed = {name for names in resolved.values() for name in names}
    adapters: dict = {}
    modules: dict = {}
    for profile in ALL_PROFILES:
        if profile.host_adapter:
            adapters.setdefault('native/hostkit/' + profile.host_adapter, []).append(profile.id)
        module = type(profile).__module__
        if module.startswith('retrorecomp.') and module not in listed:
            modules.setdefault(module, []).append(profile.id)
    for name, owners in (*adapters.items(), *modules.items()):
        if name not in listed:
            add(tuple(owners), (name,))
    return resolved



INPUTS = _resolve({
    ALL: (
        'THIRD_PARTY_NOTICES.md',
        'assets/Retro-Recomp-icon-128.png',
        'assets/Retro-Recomp-icon-16.png',
        'assets/Retro-Recomp-icon-20.png',
        'assets/Retro-Recomp-icon-24.png',
        'assets/Retro-Recomp-icon-256.png',
        'assets/Retro-Recomp-icon-32.png',
        'assets/Retro-Recomp-icon-40.png',
        'assets/Retro-Recomp-icon-48.png',
        'assets/Retro-Recomp-icon-64.png',
        'assets/Retro-Recomp.ico',
        'assets/tag-shooting.png',
        'licenses/Linux-desktop.md',
        'licenses/Noto.md',
        'licenses/OpenSSL.md',
        'licenses/Pillow.md',
        'licenses/PyInstaller-hooks.md',
        'licenses/PyInstaller.md',
        'licenses/Python.md',
        'licenses/SDL2.md',
        'licenses/SingleStepTests-m68000.md',
        'licenses/SingleStepTests-z80.md',
        'licenses/Tcl-Tk.md',
        'licenses/UPX.md',
        'licenses/dear-imgui.md',
        'licenses/emu2413.md',
        'licenses/fmgen.md',
        'licenses/gb-recompiled.md',
        'licenses/geolith.md',
        'licenses/lithogen.md',
        'licenses/llvm-mingw.md',
        'licenses/musashi.md',
        'licenses/nesrecomp.md',
        'licenses/segagenesisrecomp.md',
        'licenses/snesrecomp.md',
        'licenses/superzazu-z80.md',
        'licenses/x68000-machine.md',
        'licenses/xbr.md',
        'licenses/z80-recomp-core.md',
        'licenses/zlib-ng.md',
        'licenses/zlib.md',
        'native/CMakeLists.txt',
        'native/console16_video.h',
        'native/hostkit/hostkit.h',
        'native/hostkit/hostkit_internal.h',
        'native/hostkit/shell/rrhk_audio.c',
        'native/hostkit/shell/rrhk_events.c',
        'native/hostkit/shell/rrhk_input.c',
        'native/hostkit/shell/rrhk_main.c',
        'native/hostkit/shell/rrhk_menu.c',
        'native/hostkit/shell/rrhk_options.c',
        'native/hostkit/shell/rrhk_pointer.c',
        'native/hostkit/shell/rrhk_ring.c',
        'native/hostkit/shell/rrhk_timing.c',
        'native/hostkit/shell/rrhk_video.c',
        'native/audio_checks.c',
        'native/audio_cushion.h',
        'native/audio_filter.h',
        'native/audio_output.inc',
        'native/autofire.h',
        'native/banked_cpu_checks.c',
        'native/banked_dispatch.c',
        'native/banked_emitter.inc',
        'native/banked_runtime.inc',
        'native/banked_vectors.c',
        'native/display_settings.h',
        'native/display_settings_checks.c',
        'native/embedded_resources.h',
        'native/font10x20.h',
        'native/font6x10.h',
        'native/frame_stop_checks.c',
        'native/game_options.h',
        'native/game_options_checks.c',
        'native/gamestate.h',
        'native/gamestate.inc',
        'native/gamestate_checks.c',
        'native/host_checks.c',
        'native/host_control.h',
        'native/icon.c',
        'native/icon.h',
        'native/icon_checks.c',
        'native/input_checks.c',
        'native/language_checks.c',
        'native/launcher.c',
        'native/lazy_data_checks.c',
        'native/learning.c',
        'native/learning.h',
        'native/learning_posix.c',
        'native/lightphaser.c',
        'native/lightphaser.h',
        'native/lightphaser_checks.c',
        'native/manifest.inc',
        'native/paths.c',
        'native/paths.h',
        'native/paths_posix.inc',
        'native/pixel_optimization_checks.c',
        'native/planar_rows.h',
        'native/platform_io.c',
        'native/platform_io.h',
        'native/platform_posix_checks.c',
        'native/player_gamepad.c',
        'native/presentation_checks.c',
        'native/psg_runs.inc',
        'native/psg_state.inc',
        'native/retro_keyboard.h',
        'native/retro_menu.c',
        'native/retro_menu.h',
        'native/runtime_catalog.inc',
        'native/runtime_feedback.c',
        'native/runtime_feedback.h',
        'native/runtime_feedback_checks.c',
        'native/runtime_feedback_sdl.h',
        'native/runtime_i18n.h',
        'native/scale2x.h',
        'native/scanline_sdl.h',
        'native/scanlines.h',
        'native/sms_sprite_probe.c',
        'native/state_io.h',
        'native/stereo_fir.h',
        'native/video_frame.h',
        'native/video_probe.c',
        'native/xbr_checks.c',
        'native/xbr_filter.h',
        'native/xbr_sdl.h',
        'retrorecomp.artwork',
        'retrorecomp.batch',
        'retrorecomp.branding',
        'retrorecomp.cartridge16',
        'retrorecomp.conversion_common',
        'retrorecomp.core',
        'retrorecomp.cover_keyring',
        'retrorecomp.cover_references',
        'retrorecomp.cover_settings',
        'retrorecomp.cover_sources',
        'retrorecomp.cover_titles',
        'retrorecomp.feedback',
        'retrorecomp.freshness',
        'retrorecomp.knowledge',
        'retrorecomp.languages',
        'retrorecomp.library',
        'retrorecomp.metadata',
        'retrorecomp.packing',
        'retrorecomp.path_profiles',
        'retrorecomp.paths',
        'retrorecomp.peripherals',
        'retrorecomp.platforms',
        'retrorecomp.player_gamepad',
        'retrorecomp.publishing',
        'retrorecomp.random_routes',
        'retrorecomp.resources',
        'retrorecomp.scan_levels',
        'retrorecomp.systems',
        'retrorecomp.systems.specs',
        'retrorecomp.toolchain',
        'retrorecomp.windows',
    ),
    ('gb',): (
        'native/gb_audio_checks.c',
        'native/gb_boundary_checks.c',
        'native/gb_latency_checks.cpp',
        'native/gb_ram_checks.c',
        'native/gb_ram_helpers.h',
        'native/gb_frame_trace.h',
        'native/gb_tick_checks.c',
        'native/gb_halt_checks.c',
        'native/gb_state_compare.h',
        'native/gb_wisdom_checks.c',
        'native/gb_tick_fast.h',
        'retrorecomp.gameboy',
        'retrorecomp.gameboy_boundary',
        'retrorecomp.gameboy_build',
        'retrorecomp.gameboy_coverage',
        'retrorecomp.gameboy_cartridge',
        'retrorecomp.gameboy_delivery',
        'retrorecomp.gameboy_hardware',
        'retrorecomp.gameboy_host',
        'retrorecomp.gameboy_runtime',
    ),
    ('nes',): (
        'native/nes_audio_checks.c',
        'native/nes_dense_checks.c',
        'native/nes_dense_codegen.inc',
        'native/nes_guarded_checks.c',
        'native/nes_live_codegen.inc',
        'native/nes_machine_checks.c',
        'native/nes_machine_state.inc',
        'native/nes_mmc1_checks.c',
        'native/nes_mapper_state.inc',
        'native/nes_ppu_checks.c',
        'native/nes_ppu_fast.inc',
        'native/nes_ppu_lazy.inc',
        'native/nes_ram.inc',
        'native/nes_ram_sweep_checks.c',
        'native/nes_sprite_extra.inc',
        'native/nes_sprite_shift.h',
        'native/nes_state.c',
        'native/nes_windows_checks.c',
        'native/retro_nes.h',
        'retrorecomp.nes',
        'retrorecomp.nes_build',
        'retrorecomp.nes_catalog',
        'retrorecomp.nes_checks',
        'retrorecomp.nes_codegen',
        'retrorecomp.nes_machine',
        'retrorecomp.nes_optimization',
        'retrorecomp.nes_ram',
        'retrorecomp.nes_runtime',
        'retrorecomp.nes_state_layout',
    ),
    ('md',): (
        'native/md_audio_bridge_checks.c',
        'native/md_audio_loop.inc',
        'native/md_audio_mix.h',
        'native/md_audio_mix_checks.c',
        'native/md_audio_resample.inc',
        'native/md_backend.c',
        'native/md_battery.c',
        'native/md_battery.h',
        'native/md_boundary_checks.c',
        'native/md_bus_checks.c',
        'native/md_bus_scheduler.h',
        'native/md_cart.h',
        'native/md_cart.inc',
        'native/md_cart_checks.c',
        'native/md_cycle_checks.c',
        'native/md_decode_dump.c',
        'native/md_dma_checks.c',
        'native/md_eeprom.h',
        'native/md_eeprom_checks.c',
        'native/md_exception_checks.c',
        'native/md_fifo_checks.c',
        'native/md_mapper_checks.c',
        'native/md_native_checks.c',
        'native/md_native_steps.h',
        'native/md_portable_state.inc',
        'native/md_prefetch.h',
        'native/md_prefetch_checks.c',
        'native/md_prefetch_plan_checks.c',
        'native/md_raster_checks.c',
        'native/md_read_checks.c',
        'native/md_sram_checks.c',
        'native/md_step_dispatch.c',
        'native/md_timing.h',
        'native/md_timing_checks.c',
        'native/md_vdp_batch_checks.c',
        'native/md_vdp_dma.h',
        'native/md_vdp_dma.inc',
        'native/md_vdp_fifo.h',
        'native/md_vdp_fifo.inc',
        'native/md_vdp_pixels.inc',
        'native/md_vdp_read.h',
        'native/md_vdp_read.inc',
        'native/md_video_checks.c',
        'native/md_ym_timers.h',
        'native/md_z80_bus.inc',
        'native/md_z80_checks.c',
        'native/md_z80_native.h',
        'native/md_z80_resume_checks.c',
        'native/md_z80_runtime.c',
        'retrorecomp.megadrive',
        'retrorecomp.megadrive_audio',
        'retrorecomp.megadrive_bus',
        'retrorecomp.megadrive_bus_rules',
        'retrorecomp.megadrive_cart',
        'retrorecomp.megadrive_dma',
        'retrorecomp.megadrive_evidence',
        'retrorecomp.megadrive_fifo',
        'retrorecomp.megadrive_hardware',
        'retrorecomp.megadrive_memory',
        'retrorecomp.megadrive_read',
        'retrorecomp.megadrive_runtime',
        'retrorecomp.megadrive_sram',
        'retrorecomp.megadrive_video',
        'retrorecomp.megadrive_z80_timing',
    ),
    ('snes',): (
        'native/snes_backend.c',
        # Below native/ in a folder of its own: the save-state key hashes the files directly below native/.
        'native/snes_cpu/interrupt_checks.c',
        'native/snes_battery.c',
        'native/snes_battery.h',
        'native/snes_bus.h',
        'native/snes_bus.inc',
        'native/snes_bus_checks.c',
        'native/snes_cart.h',
        'native/snes_cart_checks.c',
        'native/snes_chip_checks.c',
        'native/snes_dma.h',
        'native/snes_dma_checks.c',
        'native/snes_dsp1_projection.inc',
        'native/snes_dsp1_vectors.h',
        'native/snes_hdma.inc',
        'native/snes_native_checks.c',
        'native/snes_native_steps.h',
        'native/snes_ppu_bus.inc',
        'native/snes_ppu_bus_checks.c',
        'native/snes_ppu_cache.inc',
        'native/snes_ppu_cache_checks.c',
        'native/snes_spc_checks.c',
        'native/snes_spc_native.h',
        'native/snes_spc_runtime.c',
        'native/snes_superfx_checks.c',
        'native/snes_timing.h',
        'native/snes_timing_checks.c',
        'native/snes_video_checks.c',
        'retrorecomp.snes_bus',
        'retrorecomp.snes_cart',
        'retrorecomp.snes_chips',
        'retrorecomp.snes_codegen',
        'retrorecomp.snes_dma',
        'retrorecomp.snes_evidence',
        'retrorecomp.snes_gsu',
        'retrorecomp.snes_knowledge',
        'retrorecomp.snes_ppu_bus',
        'retrorecomp.snes_routes',
        'retrorecomp.snes_spc',
        'retrorecomp.snes_timing',
        'retrorecomp.snes_video',
        'retrorecomp.supernintendo',
    ),
    ('ng',): (
        'assets/neogeo-catalogue.json',
        'native/neogeo_board_checks.c',
        'native/neogeo_code_view.inc',
        'native/neogeo_controls_checks.c',
        'native/neogeo_decode.c',
        'native/neogeo_fixmask.h',
        'native/neogeo_fixmask_checks.c',
        'native/neogeo_host.c',
        'native/neogeo_host.h',
        'native/neogeo_input.h',
        'native/neogeo_lithogen.c',
        'native/neogeo_lspc_checks.c',
        'native/neogeo_lspc_state.inc',
        'native/neogeo_m68000_checks.c',
        'native/neogeo_main.c',
        'native/neogeo_path_io.h',
        'native/neogeo_persistence.c',
        'native/neogeo_persistence.h',
        'native/neogeo_persistence_checks.c',
        'native/neogeo_reference.c',
        'native/neogeo_reference.h',
        'native/neogeo_sound_checks.c',
        'native/neogeo_sprite_decode.h',
        'native/neogeo_state.c',
        'native/neogeo_state_validate.c',
        'native/neogeo_timer_checks.c',
        'native/neogeo_ui_test.c',
        'native/neogeo_ym_checks.c',
        'native/neogeo_ym_state.inc',
        'native/neogeo_z80_checks.c',
        'native/neogeo_z80_native.h',
        'retrorecomp.neogeo',
        'retrorecomp.neogeo_catalogue',
        'retrorecomp.neogeo_conversion',
        'retrorecomp.neogeo_knowledge',
        'retrorecomp.neogeo_optimization',
        'retrorecomp.neogeo_persistence_checks',
        'retrorecomp.neogeo_state_checks',
        'retrorecomp.neogeo_validation',
    ),
    # The Commodore Amiga (experimental since 1.7.0): its converter modules, the WHDLoad resload layer
    # (MIT, our own), the vAmiga machine session (MPL-2.0 engine, patched at build time by amiga_vamiga) and its host-kit
    # adapter (host role: it is in HOST_NATIVE above). The profile module comes from the profile; the CPU chain, the
    # observed-code generator and the computer adapters it shares are named by its stamp_groups. The licence of the engine
    # is listed here, not under every console (that would move every host stamp).
    ('amiga',): (
        'licenses/vamiga.md',
        'native/amiga_machine/CMakeLists.txt',
        'native/amiga_machine/amiga_player.c',
        'native/amiga_machine/amiga_savefile.h',
        'native/amiga_machine/amiga_session.cpp',
        'native/amiga_machine/amiga_session.h',
        'native/amiga_machine/moira_map.cpp',
        'native/amiga_whdload/rr_decrunch.c',
        'native/amiga_whdload/rr_decrunch.h',
        'native/amiga_whdload/rr_resload.c',
        'native/amiga_whdload/rr_resload.h',
        'native/hostkit/adapters/rrhk_amiga.inc',
        'retrorecomp.amiga',
        'retrorecomp.amiga_codegen',
        'retrorecomp.amiga_translate',
        'retrorecomp.computer_routes',
        'retrorecomp.amiga_conversion',
        'retrorecomp.amiga_kickstart',
        'retrorecomp.amiga_lha',
        'retrorecomp.amiga_vamiga',
        'retrorecomp.amiga_whdload',
    ),
    # The Atari ST (experimental from 1.7.1): its converter modules, the machine session on Hatari (GPL-2.0 engine, patched at
    # build time by atarist_hatari), the libretro API header (MIT, vendored) and its host-kit adapter (host role: in HOST_NATIVE
    # above). The profile module comes from the profile; the computer adapter and the gates it shares come from stamp_groups.
    ('atarist',): (
        'licenses/emutos.md',
        'licenses/hatari.md',
        'native/atarist_machine/CMakeLists.txt',
        'native/atarist_machine/atarist_player.c',
        'native/atarist_machine/atarist_session.c',
        'native/atarist_machine/atarist_session.h',
        'native/atarist_machine/libretro/libretro.h',
        'native/hostkit/adapters/rrhk_atarist.inc',
        'retrorecomp.atarist',
        'retrorecomp.atarist_codegen',
        'retrorecomp.atarist_conversion',
        'retrorecomp.atarist_disk',
        'retrorecomp.atarist_emutos',
        'retrorecomp.atarist_hatari',
        'retrorecomp.atarist_tos',
    ),
    # The Nintendo 64 (experimental): its converter modules, the machine on Mupen64Plus-Next (GPL-2.0-or-later core, MIT ParaLLEl,
    # adapted at build time by n64_core), our MIT glue in place of the unmarked upstream files, the VR4300 hooks, the session and
    # the player, and its host-kit adapter (host role: in HOST_NATIVE above).
    ('n64',): (
        'licenses/mupen64plus-next.md',
        'native/hostkit/adapters/rrhk_n64.inc',
        'native/n64_machine/CMakeLists.txt',
        'native/n64_machine/glue/GLideN64_libretro.h',
        'native/n64_machine/glue/libretro_memory.h',
        'native/n64_machine/glue/libretro_private.h',
        'native/n64_machine/glue/osal_export.h',
        'native/n64_machine/glue/parallel.h',
        'native/n64_machine/glue/parallel_glue.cpp',
        'native/n64_machine/n64_cpu.c',
        'native/n64_machine/n64_cpu.h',
        'native/n64_machine/n64_player.c',
        'native/n64_machine/n64_session.cpp',
        'native/n64_machine/n64_session.h',
        'native/n64_machine/n64_stubs.c',
        'retrorecomp.n64',
        'retrorecomp.n64_conversion',
        'retrorecomp.n64_core',
        'retrorecomp.n64_native',
    ),
    ('x68',): (
        'native/hostkit/adapters/rrhk_x68k.inc',
        'native/x68000_machine/PROVENANCE.md',
        'native/x68000_machine/base74/alias/libretro/dswin.h',
        'native/x68000_machine/base74/alias/libretro/joystick.h',
        'native/x68000_machine/base74/alias/libretro/keyboard.h',
        'native/x68000_machine/base74/alias/libretro/mouse.h',
        'native/x68000_machine/base74/alias/m68000/musashi/m68k.h',
        'native/x68000_machine/base74/alias/x68k/x68kmemory.h',
        'native/x68000_machine/base74/alias/x68kmemory.h',
        'native/x68000_machine/base74/audio_mix.c',
        'native/x68000_machine/base74/bridge.c',
        'native/x68000_machine/base74/config.c',
        'native/x68000_machine/base74/cpu_bus.c',
        'native/x68000_machine/base74/fileio.c',
        'native/x68000_machine/base74/host_draw.c',
        'native/x68000_machine/base74/m68000/m68000.h',
        'native/x68000_machine/base74/mercury_absent.c',
        'native/x68000_machine/base74/musashi/m68kconf.h',
        'native/x68000_machine/base74/x11/common.h',
        'native/x68000_machine/base74/x11/dosio.h',
        'native/x68000_machine/base74/x11/dswin.h',
        'native/x68000_machine/base74/x11/fileio.h',
        'native/x68000_machine/base74/x11/joystick.h',
        'native/x68000_machine/base74/x11/juliet.h',
        'native/x68000_machine/base74/x11/keyboard.h',
        'native/x68000_machine/base74/x11/mmsystem.h',
        'native/x68000_machine/base74/x11/mouse.h',
        'native/x68000_machine/base74/x11/prop.h',
        'native/x68000_machine/base74/x11/status.h',
        'native/x68000_machine/base74/x11/timer.h',
        'native/x68000_machine/base74/x11/windows.h',
        'native/x68000_machine/base74/x11/windraw.h',
        'native/x68000_machine/base74/x11/winui.h',
        'native/x68000_machine/base74/x11/winx68k.h',
        'native/x68000_machine/colour.h',
        'native/x68000_machine/glue.h',
        'native/x68000_machine/glue_line.h',
        'native/x68000_machine/input.c',
        'native/x68000_machine/libretro_api.c',
        'native/x68000_machine/machine.c',
        'native/x68000_machine/provenance.json',
        'native/x68000_machine/state/legacy_stub.c',
        'native/x68000_machine/state/rr_state.c',
        'native/x68000_machine/state/rr_state.h',
        'native/x68000_machine/state/snapshot.c',
        'native/x68000_native/CMakeLists.txt',
        'native/x68000_native/decode.c',
        'native/x68000_native/guard_checks.c',
        'native/x68000_native/observe.c',
        'native/x68000_native/observe.h',
        'native/x68000_reference/CMakeLists.txt',
        'native/x68000_reference/audio_checks.c',
        'native/x68000_reference/audio_checks.h',
        'native/x68000_reference/check_compat.h',
        'native/x68000_reference/disk_checks.c',
        'native/x68000_reference/disk_checks.h',
        'native/x68000_reference/hardware_clock.c',
        'native/x68000_reference/hardware_clock.h',
        'native/x68000_reference/loading.h',
        'native/x68000_reference/media_session.c',
        'native/x68000_reference/media_session.h',
        'native/x68000_reference/mouse_games.json',
        'native/x68000_reference/payload.c',
        'native/x68000_reference/payload.h',
        'native/x68000_reference/probe.c',
        'native/x68000_reference/probe.h',
        'native/x68000_reference/reference_host.c',
        'native/x68000_reference/rtc_clock_shim.h',
        'native/x68000_reference/session_checks.c',
        'native/x68000_reference/session_checks.h',
        'native/x68000_reference/state_store.c',
        'native/x68000_reference/state_store.h',
        'native/x68000_reference/state_store_test.c',
        'native/x68000_reference/timing_checks.c',
        'native/x68000_reference/timing_checks.h',
        'native/x68000_reference/video_checks.c',
        'native/x68000_reference/video_checks.h',
        'retrorecomp.x68000',
        'retrorecomp.x68000_conversion',
        'retrorecomp.x68000_media',
        'retrorecomp.x68000_program',
        'retrorecomp.x68000_scan',
        'retrorecomp.x68_knowledge',
        'tools/x68000_base74.py',
        'tools/x68000_native.py',
        'tools/x68000_reference.py',
        'tools/x68000_reference_check.py',
        'tools/x68000_state_hardware.py',
    ),
    ('gba',): (
        'licenses/gbarecomp.md',
        'native/gba_driver.h',
        'native/gba_machine.cpp',
        'native/gba_machine.h',
        'retrorecomp.gba',
        'retrorecomp.gba_analysis',
        'retrorecomp.gba_build',
        'retrorecomp.gba_conversion',
        'retrorecomp.gba_engine',
        'retrorecomp.gba_patches',
        'retrorecomp.gba_player',
    ),
    # The walk of a player's own record, shared by the two 68000 computers that keep one.
    ('amiga', 'atarist'): (
        'retrorecomp.m68k_record_walk',
    ),
    # The CPS-1 family: the CPS-2 is built from the same board model, host and pipeline, so both own these files.
    ('cps1', 'cps2'): (
        'assets/cps1-catalogue.json',
        'licenses/cps1-machine.md',
        'licenses/cps1-ymfm.md',
        'native/cps1_cps2_board.inc',
        'native/cps1_eeprom.c',
        'native/cps1_eeprom.h',
        'native/cps1_host.c',
        'native/cps1_host.h',
        'native/cps1_m68kconf.h',
        'native/cps1_machine.c',
        'native/cps1_machine.h',
        'native/cps1_main.c',
        'native/cps1_native.c',
        'native/cps1_native.h',
        'native/cps1_oki.c',
        'native/cps1_oki.h',
        'native/cps1_opm.cpp',
        'native/cps1_opm.h',
        'native/cps1_persistence.c',
        'native/cps1_persistence.h',
        'native/cps1_probe.c',
        'native/cps1_qsound.c',
        'native/cps1_qsound.h',
        'native/cps1_z80_native.h',
        'retrorecomp.capcom_catalogue',
        'retrorecomp.capcom_sets',
        'retrorecomp.cps1',
        'retrorecomp.cps1_board',
        'retrorecomp.cps1_build',
        'retrorecomp.cps1_catalogue',
        'retrorecomp.cps1_codegen',
        'retrorecomp.cps1_conversion',
        'retrorecomp.cps1_kabuki',
        'retrorecomp.cps1_knowledge',
        'retrorecomp.cps1_qsound',
    ),
    # What only the CPS-2 adds: its catalogue, its romset reader and the key decryption of its program.
    ('cps2',): (
        'assets/cps2-catalogue.json',
        'retrorecomp.cps2',
        'retrorecomp.cps2_catalogue',
        'retrorecomp.cps2_crypt',
        'retrorecomp.cps2_knowledge',
        'retrorecomp.cps2_tables',
    ),
    # The PC Engine (experimental, docs/PC_ENGINE.md): its reader, its report writer and the engine's notices.
    # Adventure (ScummVM): the GPL patch of the runtime and its notices are the game side of its exes (the runtime is the
    # machine, like native/x68000_machine); scummvm_build decides the runtime (build role, BUILD_MODULES).
    ('scummvm',): (
        'licenses/freetype.md',
        'licenses/scummvm.md',
        'native/scummvm/LICENSE',
        'native/scummvm/README.md',
        'native/scummvm/patches/0001-retrorecomp-pack-launch-nodialog.patch',
        'native/scummvm/patches/0002-retrorecomp-options-page.patch', 'native/scummvm/patches/0003-retrorecomp-theme-colours.patch',
        'retrorecomp.scummvm_build',
        'retrorecomp.scummvm_export',
    ),
    ('pce',): (
        'licenses/pcenginerecomp.md',
        'native/pce_backup.c',
        'native/pce_backup.h',
        'native/pce_machine.cpp',
        'native/pce_machine.h',
        'native/pce_main.c',
        'retrorecomp.pce_build',
        'retrorecomp.pce_conversion',
        'retrorecomp.pce_knowledge',
        'retrorecomp.pce_rom',
    ),
    # The Sony PlayStation (experimental, docs/PLAYSTATION.md): its disc and BIOS readers, its input module, the pack of the disc,
    # the preparation of the pinned Beetle PSX machine, the session that drives it and the machine's notices.
    ('psx',): (
        'licenses/beetle-psx.md',
        'native/psx_machine/CMakeLists.txt',
        'native/psx_machine/psx_main.c',
        'native/psx_machine/psx_observe.c',
        'native/psx_machine/psx_reference.c',
        'native/psx_machine/psx_session.c',
        'native/psx_machine/psx_session.h',
        'retrorecomp.psx',
        'retrorecomp.psx_beetle',
        'retrorecomp.psx_bios',
        'retrorecomp.psx_build',
        'retrorecomp.psx_conversion',
        'retrorecomp.psx_disc',
        'retrorecomp.psx_native',
        'retrorecomp.psx_pack',
    ),
    # The text of the three state rules of the MC68000 steps (LINK A7, UNLK A7, NEGX) is the Mega Drive's own: it is an input of the four
    # machines that apply it. It is listed with owners by id because the Mega Drive cannot join a shared group without editing its
    # profile, which would move its stamp; the three others take the module that applies it through `shares:m68000_state_rules`.
    ('cps1', 'md', 'ng', 'x68'): (
        'retrorecomp.megadrive_rules',
    ),
    ('sms', 'gg'): (
        'native/video_checks.c',
        'native/video_mode4.inc',
        'profiles/example.sms.toml',
        'retrorecomp.sega_evidence',
        'retrorecomp.systems.game_gear',
        'retrorecomp.systems.master_system',
        'retrorecomp.validation',
    ),
    # The shell every converter shares (conversion_common) is under ALL above, with the host kit's shell (every console
    # links it; console16_video.h is included by the kit's video shell). Game role.
    'shares:guns16': (
        'retrorecomp.guns16',
    ),
    'shares:md_prefetch': (
        'native/md_prefetch.inc',
    ),
    'shares:megadrive_z80': (
        'retrorecomp.megadrive_z80',
    ),
    'shares:neogeo_native': (
        'native/neogeo_native.c',
        'native/neogeo_native.h',
    ),
    'shares:neogeo_build': (
        'retrorecomp.neogeo_build',
        'retrorecomp.neogeo_z80',
        'retrorecomp.zip_sets',
    ),
    'shares:megadrive_codegen': (
        'retrorecomp.megadrive_codegen',
    ),
    # The corrections of Geolith's Musashi 68000 (m68kops.c) that the Neo Geo, the CPS-1 and the X68000 build from; the Mega Drive
    # does not use this copy. Game role.
    'shares:musashi_fixes': (
        'retrorecomp.musashi_fixes',
    ),
    # The gates and the evidence about the delivered file (liveness, packed replay) that the converters share;
    # delivery_evidence calls the gates, so a machine that uses it joins this group.
    'shares:conversion_gates': (
        'retrorecomp.conversion_gates',
        'retrorecomp.delivery_evidence',
    ),
    # The module that applies the Mega Drive's state rules to the translated steps of the Neo Geo, the CPS-1 and the X68000 (the text it
    # reads, `megadrive_rules`, is listed under the four machines). Game role.
    'shares:m68000_state_rules': (
        'retrorecomp.m68000_state_rules',
    ),
    'shares:neogeo_codegen': (
        'retrorecomp.neogeo_codegen',
    ),
    # What the host kit's adapters of the disk computers share (the guest keyboard, the captured mouse, the floppy drives...), included by each adapter. Host role.
    'shares:hostkit_computer': (
        'native/hostkit/adapters/rrhk_computer.inc',
    ),
    # The generator of guarded native code for the instructions a computer runs from RAM (the X68000 now, the Amiga when it joins). Game role.
    'shares:m68k_observed': (
        'retrorecomp.m68k_observed',
    ),
    # The banked Z80 chain of a machine whose main CPU is a Z80 (the Master System and the Game Gear now): what a machine declares
    # (its regions, its RAM cut, its M1 wait states) and the corrections of the Z80 state and of the reference CPU. Game role.
    # The emitter and the step loop it parametrises (native/banked_*) are under ALL above.
    'shares:z80_main': (
        'retrorecomp.cpu',
        'retrorecomp.z80_chain',
    ),
    'family:rr16': (
        'native/console16_main.c',
        'native/console16_state.c',
        'native/console16_state.h',
        'native/gun16.c',
        'native/gun16.h',
        'native/gun16_checks.c',
        'native/retro_console16.h',
        'retrorecomp.console16',
        'retrorecomp.console16_optimization',
        'retrorecomp.console16_state',
        'retrorecomp.gun16_runtime',
        'retrorecomp.systems.console16',
    ),
    # Its staging module: the machines on the kit get a copy of it in their project (the X68000 compiles it from the tree).
    # The Master System and the Game Gear get it beside the common runtime (prepare_native_source); the Game Boy gets it
    # in the runtime folder of its project (gameboy_host).
    'family:host_kit': (
        'retrorecomp.hostkit',
    ),
    'family:m68000': (
        'native/m68000_backend.c',
        'native/m68000_backend.h',
        'native/m68000_backend_checks.c',
        'native/m68000_decode_rules_checks.c',
        'native/m68000_state_helpers.h',
        'native/md_exception_decode.h',
        'retrorecomp.m68000',
    ),
})
