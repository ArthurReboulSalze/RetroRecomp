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


INTERFACE_MODULES = frozenset(('__init__', 'gui', 'i18n', 'ui_fonts', 'tooltips',
                               # The window, split by responsibility (gui.py assembles the Application).
                               'gui_common', 'gui_drawing', 'gui_window', 'gui_queue', 'gui_conversion',
                               'gui_collection', 'gui_updates', 'gui_options', 'gui_sharing', 'gui_reports',
                               'gui_account', 'gui_leaderboard',
                               'dropfiles', 'updater', 'linux_desktop', 'queue_state',
                               'credits_demo', 'credits_music', 'dialogs',
                               'compiled_games', 'compiled_games_view', 'memory_view',
                               'report_schema',
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
BUILD_MODULES = frozenset(('toolchain', 'packing'))

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
# older ones. The table was empty in the tree of 1.6.0; the tree of 1.6.1 listed the stamps of 1.6.0; the entries of
# 1.6.1 are the ones below.
# Release 1.6.1 (tag v1.6.1, commit 48b1fac, Python 3.14.5, the Python of the packaged converter), declared on
# 28 October 2026 for the Master System, Game Gear, Game Boy, NES, Mega Drive, Super Nintendo, Neo Geo and CPS-1.
# Each value is the game stamp computed from the tag (`git archive`, then `compilation_inputs.role_stamps`; the same
# method gives the 1.6.0 entries of the tree of 1.6.1 again, byte for byte). Between the tag and 1.6.2 no listed input
# changed what a conversion generates: the report gained its `timings`, the batch applies the shared base, the NES
# player shell moved onto the host kit (the generated sources and the learned paths are the same), and the packer is
# UPX 5.3.0 (a build input). Evidence and limits: docs/UPGRADES.md, "Exports of 1.6.1 in 1.6.2". The X68000 has no
# entry: its request carries an SDK stamp (`x68_sdk`) derived from the game stamp, which this mechanism does not
# recompute.
LEGACY_GAME_STAMPS = {
    # (the Windows converter's stamp, built with Python 3.14; the Linux converter's, built with Python 3.13: code is
    # fingerprinted as bytecode, so the two published 1.6.1 converters stamp differently; both checked with their own
    # `_compilation-inputs` against this table)
    'cps1': ('fb7d9315c9637c103aa81f259712524d9bf29b33e6e9d920ce8f4b5ad83f92db',
        '5a47af5e465134ab8fa927cd3389c7bbbcc12d61ec02f18461de63e89ae175fb'),
    'gb': ('e5fc74915974ec27ab05bc9c9ae5ecea03050316ed39d9842b11485d2ffe1e09',
        'f194a7e52b26bddadcf02362d4921774ec75f8c65629724286c3ad5c716322d5'),
    'gg': ('f860d65789176fa85ad7c7880c766da1754ea98fedac4f50edcf77d664f799cd',
        '2e805515d5cf5e080ea5f9ac10d97759bcf22b6976b565b2a73d599f2d82d736'),
    'md': ('2effe9f498891007f54fadc029a8f55f625ed414c73894fe2cbde5684dcfd188',
        '47c10b4b7a49bd24c34cee183442cdb5344c578657f5b3ed83106794a9944db9'),
    'nes': ('a8b871f2ab08ffc44633cc562b942fdac9a3cc4d65a7706030b714abf96fa017',
        '480b9aea940b6c5fe11adcf226dcf6fc15fb5df2703080c8c62ef71a4efba5c2'),
    'ng': ('1d1a5224f6c89a58ff7f1f79d807918a1c4f1295e0ae3543a253a4d884d2959b',
        'cc24dd0a1115f37f2053188a478f8592bb2e42765b6e07aacd8f8d4bf7427e4f'),
    'sms': ('c4589fe7b51645c8fc779fb2511d3dc9c793fa855b5c910089bbdf0cb3dea68d',
        '1a3b71b7a75d91e2ed859656671c7471a31d9ce4527f2f15170146e961a71346'),
    'snes': ('463da5c5cf464363bbc887e524a1933288e9f94c7d748cae624748dc172b6ae4',
        '0a62f3c2061a22948f8442c8b84faee71f0925772536f8a7d30d4ae43bef63d9'),
}

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
    # Player shells written as patches: Game Boy platform window, menus,
    # sound output and input; Mega Drive sound delivery.
    'gameboy_host', 'gameboy_timing', 'megadrive_audio',
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
    'gb_audio_output.inc', 'nes_audio_checks.c',
    'md_audio_loop.inc', 'md_audio_resample.inc',
    # Converter-only controller bridge (never linked into games).
    'player_gamepad.c',
    # Each machine family's shell: Master System / Game Gear and Game Boy (the 16-bit consoles, the NES
    # and the X68000 are on the host kit below).
    'host.c', 'ui.c', 'ui.h', 'controls.c', 'controls.h',
    'gb_menu.inc', 'gb_input_refresh.inc',
    'neogeo_ui_test.c',
    # The host kit (docs/HOST_KIT.md): the shell shared by Mega Drive, SNES, Neo Geo, CPS-1 and
    # the NES, and the adapter of each. Every file below native/hostkit is host-side.
    'hostkit/hostkit.h', 'hostkit/hostkit_internal.h',
    'hostkit/shell/rrhk_audio.c', 'hostkit/shell/rrhk_events.c', 'hostkit/shell/rrhk_input.c',
    'hostkit/shell/rrhk_main.c', 'hostkit/shell/rrhk_menu.c', 'hostkit/shell/rrhk_options.c',
    'hostkit/shell/rrhk_pointer.c', 'hostkit/shell/rrhk_ring.c', 'hostkit/shell/rrhk_timing.c',
    'hostkit/shell/rrhk_video.c',
    'hostkit/adapters/rrhk_md.c', 'hostkit/adapters/rrhk_snes.c', 'hostkit/adapters/rrhk_ng.c',
    'hostkit/adapters/rrhk_cps1.c', 'hostkit/adapters/rrhk_nes.c', 'hostkit/adapters/rrhk_x68k.inc'))
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
RAW_FILES = frozenset(('assets/neogeo-catalogue.json', 'assets/cps1-catalogue.json'))

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
    'licenses/upx-5.3.0-src.tar.xz')

# The manifest: module names ('retrorecomp.x') and file paths below the bundle root,
# with the consoles that own each.

INPUTS = {
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
        'native/controls.c',
        'native/controls.h',
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
        'native/host.c',
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
        'native/ui.c',
        'native/ui.h',
        'native/video_checks.c',
        'native/video_frame.h',
        'native/video_mode4.inc',
        'native/video_probe.c',
        'native/xbr_checks.c',
        'native/xbr_filter.h',
        'native/xbr_sdl.h',
        'retrorecomp.artwork',
        'retrorecomp.batch',
        'retrorecomp.branding',
        'retrorecomp.cartridge16',
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
        'native/gb_audio_output.inc',
        'native/gb_boundary_checks.c',
        'native/gb_input_refresh.inc',
        'native/gb_latency_checks.cpp',
        'native/gb_menu.inc',
        'native/gb_ram_checks.c',
        'native/gb_ram_helpers.h',
        'retrorecomp.gameboy',
        'retrorecomp.gameboy_boundary',
        'retrorecomp.gameboy_build',
        'retrorecomp.gameboy_coverage',
        'retrorecomp.gameboy_hardware',
        'retrorecomp.gameboy_host',
        'retrorecomp.gameboy_runtime',
        'retrorecomp.gameboy_timing',
        'retrorecomp.systems.game_boy',
    ),
    ('nes',): (
        'native/hostkit/adapters/rrhk_nes.c',
        'native/nes_audio_checks.c',
        'native/nes_dense_checks.c',
        'native/nes_dense_codegen.inc',
        'native/nes_guarded_checks.c',
        'native/nes_live_codegen.inc',
        'native/nes_machine_checks.c',
        'native/nes_machine_state.inc',
        'native/nes_mapper_state.inc',
        'native/nes_ppu_checks.c',
        'native/nes_ppu_fast.inc',
        'native/nes_ppu_lazy.inc',
        'native/nes_ram.inc',
        'native/nes_sprite_extra.inc',
        'native/nes_sprite_shift.h',
        'native/nes_state.c',
        'native/nes_windows_checks.c',
        'native/retro_nes.h',
        'retrorecomp.nes',
        'retrorecomp.nes_build',
        'retrorecomp.nes_catalog',
        'retrorecomp.nes_codegen',
        'retrorecomp.nes_machine',
        'retrorecomp.nes_optimization',
        'retrorecomp.nes_ram',
        'retrorecomp.nes_runtime',
        'retrorecomp.systems.nes',
    ),
    ('md',): (
        'native/md_audio_bridge_checks.c',
        'native/hostkit/adapters/rrhk_md.c',
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
        'native/md_exception_decode.h',
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
        'retrorecomp.megadrive_cart',
        'retrorecomp.megadrive_dma',
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
        'native/hostkit/adapters/rrhk_snes.c',
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
        'native/hostkit/adapters/rrhk_ng.c',
        'native/neogeo_board_checks.c',
        'native/neogeo_code_view.inc',
        'native/neogeo_controls_checks.c',
        'native/neogeo_decode.c',
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
        'retrorecomp.neogeo_persistence_checks',
        'retrorecomp.neogeo_state_checks',
        'retrorecomp.neogeo_validation',
        'retrorecomp.systems.neogeo',
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
        'native/x68000_machine/glue.h',
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
        'native/x68000_reference/media_probe.c',
        'native/x68000_reference/media_session.c',
        'native/x68000_reference/media_session.h',
        'native/x68000_reference/mouse_games.json',
        'native/x68000_reference/payload.c',
        'native/x68000_reference/payload.h',
        'native/x68000_reference/probe.c',
        'native/x68000_reference/probe.h',
        'native/x68000_reference/reference_host.c',
        'native/x68000_reference/rtc_clock_shim.h',
        'native/x68000_reference/session_bridge.c',
        'native/x68000_reference/session_checks.c',
        'native/x68000_reference/session_checks.h',
        'native/x68000_reference/state_store.c',
        'native/x68000_reference/state_store.h',
        'native/x68000_reference/state_store_test.c',
        'native/x68000_reference/timing_checks.c',
        'native/x68000_reference/timing_checks.h',
        'native/x68000_reference/video_checks.c',
        'native/x68000_reference/video_checks.h',
        'retrorecomp.systems.x68000',
        'retrorecomp.x68000',
        'retrorecomp.x68000_conversion',
        'retrorecomp.x68000_media',
        'retrorecomp.x68000_program',
        'retrorecomp.x68000_scan',
        'tools/x68000_base74.py',
        'tools/x68000_native.py',
        'tools/x68000_reference.py',
        'tools/x68000_reference_check.py',
        'tools/x68000_state_hardware.py',
    ),
    ('cps1',): (
        'assets/cps1-catalogue.json',
        'native/hostkit/adapters/rrhk_cps1.c',
        'licenses/cps1-machine.md',
        'licenses/cps1-ymfm.md',
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
        'native/cps1_probe.c',
        'native/cps1_z80_native.h',
        'retrorecomp.cps1',
        'retrorecomp.cps1_board',
        'retrorecomp.cps1_build',
        'retrorecomp.cps1_catalogue',
        'retrorecomp.cps1_codegen',
        'retrorecomp.cps1_conversion',
        'retrorecomp.cps1_knowledge',
        'retrorecomp.systems.cps1',
    ),
    ('sms', 'gg'): (
        'profiles/example.sms.toml',
        'retrorecomp.cpu',
        'retrorecomp.systems.game_gear',
        'retrorecomp.systems.master_system',
        'retrorecomp.validation',
    ),
    # The shell every converter of these consoles shares: single-ROM path, checks, spawn layer of the probes, pinned
    # source patching and file writes. Game role. P5b (the other families) extends the owners when they adopt it.
    ('sms', 'gg', 'gb', 'nes'): (
        'retrorecomp.conversion_common',
    ),
    ('md', 'snes'): (
        'retrorecomp.guns16',
    ),
    ('md', 'x68'): (
        'native/md_prefetch.inc',
    ),
    ('md', 'cps1'): (
        'retrorecomp.megadrive_z80',
    ),
    ('ng', 'x68'): (
        'native/neogeo_native.c',
        'native/neogeo_native.h',
    ),
    ('ng', 'cps1'): (
        'retrorecomp.neogeo_build',
        'retrorecomp.neogeo_z80',
        'retrorecomp.zip_sets',
    ),
    ('md', 'x68', 'cps1'): (
        'retrorecomp.megadrive_codegen',
    ),
    ('ng', 'x68', 'cps1'): (
        'retrorecomp.neogeo_codegen',
    ),
    ('md', 'snes', 'ng', 'cps1'): (
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
    # The host kit's shell: every console that links it (phases 1 to 3). console16_video.h (rr16_video_rect) is
    # included by the kit's video shell, so NES and X68000 exports compile it too; game role.
    ('md', 'snes', 'ng', 'cps1', 'nes', 'x68'): (
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
    ),
    # Its staging module: the consoles whose projects get a copy of the kit (the X68000 compiles it from the tree).
    ('md', 'snes', 'ng', 'cps1', 'nes'): (
        'retrorecomp.hostkit',
    ),
    M68000_FAMILY: (
        'native/m68000_backend.c',
        'native/m68000_backend.h',
        'native/m68000_backend_checks.c',
        'native/m68000_state_helpers.h',
        'retrorecomp.m68000',
    ),
}
