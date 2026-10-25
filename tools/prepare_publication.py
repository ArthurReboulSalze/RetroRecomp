"""Prepare and audit public sources and converter releases; never upload them."""
from __future__ import annotations

import argparse
import hashlib
import json
import marshal
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import __version__ as VERSION
PUBLIC_FILES = tuple("""
retrorecomp/x68000.py retrorecomp/x68000_media.py retrorecomp/x68000_conversion.py
retrorecomp/systems/x68000.py docs/X68000.md
tests/test_x68000_availability.py tests/test_x68000_mouse.py tests/test_x68000_native_forms.py
native/x68000_machine/base74/alias/libretro/dswin.h
native/x68000_machine/base74/alias/libretro/joystick.h
native/x68000_machine/base74/alias/libretro/keyboard.h
native/x68000_machine/base74/alias/libretro/mouse.h
native/x68000_machine/base74/alias/m68000/musashi/m68k.h
native/x68000_machine/base74/alias/x68k/x68kmemory.h native/x68000_machine/base74/alias/x68kmemory.h
native/x68000_machine/base74/audio_mix.c native/x68000_machine/base74/bridge.c
native/x68000_machine/base74/config.c native/x68000_machine/base74/cpu_bus.c
native/x68000_machine/base74/fileio.c native/x68000_machine/base74/host_draw.c
native/x68000_machine/base74/m68000/m68000.h native/x68000_machine/base74/mercury_absent.c
native/x68000_machine/base74/musashi/m68kconf.h native/x68000_machine/base74/x11/common.h
native/x68000_machine/base74/x11/dosio.h native/x68000_machine/base74/x11/dswin.h
native/x68000_machine/base74/x11/fileio.h native/x68000_machine/base74/x11/joystick.h
native/x68000_machine/base74/x11/juliet.h native/x68000_machine/base74/x11/keyboard.h
native/x68000_machine/base74/x11/mmsystem.h native/x68000_machine/base74/x11/mouse.h
native/x68000_machine/base74/x11/prop.h native/x68000_machine/base74/x11/status.h
native/x68000_machine/base74/x11/timer.h native/x68000_machine/base74/x11/windows.h
native/x68000_machine/base74/x11/windraw.h native/x68000_machine/base74/x11/winui.h
native/x68000_machine/base74/x11/winx68k.h native/x68000_machine/glue.h
native/x68000_machine/input.c native/x68000_machine/libretro_api.c native/x68000_machine/machine.c
native/x68000_machine/provenance.json native/x68000_machine/PROVENANCE.md
native/x68000_machine/state/legacy_stub.c native/x68000_machine/state/rr_state.c
native/x68000_machine/state/rr_state.h native/x68000_machine/state/snapshot.c
native/x68000_reference/audio_checks.c native/x68000_reference/audio_checks.h
native/x68000_reference/check_compat.h native/x68000_reference/CMakeLists.txt
native/x68000_reference/disk_checks.c native/x68000_reference/disk_checks.h
native/x68000_reference/hardware_clock.c native/x68000_reference/hardware_clock.h
native/x68000_reference/loading.h native/x68000_reference/media_probe.c
native/x68000_reference/media_session.c native/x68000_reference/media_session.h native/x68000_reference/mouse_games.json
native/x68000_reference/payload.c native/x68000_reference/payload.h
native/x68000_reference/player_ui.inc native/x68000_reference/probe.c
native/x68000_reference/probe.h native/x68000_reference/reference_host.c
native/x68000_reference/rtc_clock_shim.h native/x68000_reference/session_bridge.c
native/x68000_reference/session_checks.c native/x68000_reference/session_checks.h
native/x68000_reference/state_store.c native/x68000_reference/state_store.h
native/x68000_reference/state_store_test.c native/x68000_reference/timing_checks.c
native/x68000_reference/timing_checks.h native/x68000_reference/video_checks.c
native/x68000_reference/video_checks.h native/x68000_native/CMakeLists.txt
native/x68000_native/decode.c native/x68000_native/guard_checks.c native/x68000_native/observe.c
native/x68000_native/observe.h tools/x68000_native.py tools/x68000_reference.py
tools/x68000_reference_check.py tools/x68000_base74.py tools/x68000_state_hardware.py
retrorecomp/x68000_scan.py
native/autofire.h tools/autofire_selftest.py tests/test_autofire.py tools/start_select_selftest.py
native/game_options.h native/audio_filter.h native/audio_cushion.h
native/player_gamepad.c retrorecomp/player_gamepad.py tools/build_player_gamepad.py tools/build_splash.py
tools/player_gamepad/CMakeLists.txt
native/game_options_checks.c tools/game_options_selftest.py tests/test_player_gamepad.py
tools/package_installers.py tools/installers/windows.iss tools/installers/deb_launcher.sh
tools/installers/linux_install.sh tools/installers/linux_uninstall.sh
tests/test_installers.py docs/INSTALLING.md
retrorecomp/compiled_games.py retrorecomp/compiled_games_view.py retrorecomp/memory_view.py
retrorecomp/game_details.py retrorecomp/game_metadata.py retrorecomp/game_card_view.py retrorecomp/rom_sources.py
tests/test_game_cards.py tests/test_disk_sets.py
docs/COMPILED_GAMES.md docs/UPGRADES.md
MEDIAS/RetroRecomp_UI_1.1.5.jpg
tests/test_compiled_games.py
retrorecomp/credits_demo.py retrorecomp/credits_music.py retrorecomp/dialogs.py
tools/credits_audio/CMakeLists.txt tools/credits_audio/player.c tools/build_credits_audio.py
tests/test_credits.py tools/credits_selftest.py
assets/credits/NOTICE.md docs/CREDITS.md
MEDIAS/trackers_chiploom/night_vector.mod
MEDIAS/trackers_chiploom/Pixel_Rush.mod
MEDIAS/trackers_chiploom/pocket_signals_v2.mod
retrorecomp/platforms.py retrorecomp/toolchain.py native/platform_io.h native/platform_io.c
retrorecomp/linux_desktop.py tests/test_linux_desktop.py
retrorecomp/languages.py
retrorecomp/ui_fonts.py tools/build_languages.py tests/test_languages.py
retrorecomp/resources.py native/embedded_resources.h
docs/LANGUAGES.md
docs/QUALITY_REVIEW.md
native/language_checks.c tools/language_selftest.py
native/runtime_i18n.h native/runtime_catalog.inc
assets/locales/fr.json assets/locales/it.json assets/locales/es.json assets/locales/de.json
assets/locales/zh.json assets/locales/ja.json assets/locales/ru.json
assets/board-trophy.png assets/board-gem-gold.png assets/board-gem-platinum.png assets/board-gem-diamond.png
assets/RetroRecomp-UI-JP.otf assets/RetroRecomp-UI-SC.otf assets/font-coverage.json licenses/Noto.md
native/paths_posix.inc native/learning_posix.c native/font6x10.h native/font10x20.h
native/platform_posix_checks.c tools/linux_sms_selftest.py
retrorecomp/freshness.py retrorecomp/compilation_inputs.py tests/test_compilation_inputs.py
retrorecomp/snes_knowledge.py tests/test_snes_knowledge.py
tests/test_build_budget.py
tests/test_compiler_durability.py
retrorecomp/queue_state.py tests/test_queue_state.py
tools/queue_recovery_selftest.py
tests/test_freshness.py
tests/test_gui_shutdown.py
tests/test_stop_now.py
tests/test_startup_splash.py
retrorecomp/feedback.py native/runtime_feedback.c native/runtime_feedback.h native/runtime_feedback_sdl.h
tools/runtime_feedback_selftest.py native/runtime_feedback_checks.c tests/test_feedback.py
tools/gameplay_feedback_selftest.py
.gitattributes .gitignore .github/workflows/checks.yml
tools/build_site.py tests/test_site.py
site/index.html site/styles.css site/404.html
README.md LICENSE CONTRIBUTING.md THIRD_PARTY_NOTICES.md
RetroRecomp.py requirements.txt
docs/ARCHITECTURE.md docs/BUILDING.md docs/COMPATIBILITY.md docs/BOXART.md docs/AUDIO.md
docs/RUNTIME_FEEDBACK.md
docs/INDEX.md tools/check_doc_links.py tests/test_doc_links.py
docs/CONTROLS.md docs/ROADMAP.md docs/RELEASE_NOTES.md docs/SYSTEM_PROFILES.md docs/GAME_GEAR.md docs/GAME_BOY.md docs/NES.md
MEDIAS/RetroRecomp_logo.png MEDIAS/RetroRecomp_ban.png
MEDIAS/RetroRecomp_logo_outlined.png MEDIAS/RetroRecomp_consoles.png
MEDIAS/RetroRecomp_UI_1.1.3.png
MEDIAS/RetroRecomp_Master_System_Collection.png
MEDIAS/RetroRecomp_Compiled_Games.png MEDIAS/RetroRecomp_Credits.png
MEDIAS/RetroRecomp_Queue_en.png MEDIAS/RetroRecomp_Collection_fr.png MEDIAS/RetroRecomp_Options_de.png
MEDIAS/RetroRecomp_Credits_ja.png MEDIAS/RetroRecomp_Closing_it.gif
MEDIAS/RetroRecomp_Help_fr.png MEDIAS/RetroRecomp_Leaderboard_fr.png
MEDIAS/RetroRecomp_learning_cycle.png
MEDIAS/RetroRecomp_Native_Games_web.mp4
MEDIAS/RetroRecomp_Native_Games_poster.jpg
MEDIAS/TAG_SHOOTING.png assets/tag-shooting.png
profiles/example.sms.toml
assets/Retro-Recomp-banner.png assets/Retro-Recomp.ico
assets/Retro-Recomp-consoles.png
assets/Retro-Recomp-icon-16.png assets/Retro-Recomp-icon-20.png
assets/Retro-Recomp-icon-24.png assets/Retro-Recomp-icon-32.png
assets/Retro-Recomp-icon-40.png assets/Retro-Recomp-icon-48.png
assets/Retro-Recomp-icon-64.png assets/Retro-Recomp-icon-128.png
assets/Retro-Recomp-icon-256.png
assets/tools/upx.exe assets/tools/upx-amd64_linux
licenses/z80-recomp-core.md licenses/superzazu-z80.md licenses/SDL2.md licenses/xbr.md
licenses/gb-recompiled.md licenses/dear-imgui.md licenses/nesrecomp.md licenses/emu2413.md
licenses/UPX.md licenses/llvm-mingw.md
licenses/segagenesisrecomp.md licenses/snesrecomp.md
licenses/geolith.md licenses/lithogen.md licenses/musashi.md
licenses/x68000-machine.md licenses/fmgen.md
licenses/upx-5.2.1-src.tar.xz
licenses/SingleStepTests-z80.md licenses/SingleStepTests-m68000.md licenses/Python.md licenses/Tcl-Tk.md
licenses/Pillow.md licenses/PyInstaller.md licenses/PyInstaller-hooks.md
licenses/OpenSSL.md licenses/zlib.md licenses/zlib-ng.md
retrorecomp/__init__.py retrorecomp/artwork.py retrorecomp/batch.py
retrorecomp/build_cleanup.py tests/test_build_cleanup.py
retrorecomp/cover_settings.py retrorecomp/cover_sources.py tests/test_cover_sources.py
retrorecomp/cover_titles.py tests/test_cover_titles.py
retrorecomp/cover_references.py assets/cover-references.json tests/test_cover_references.py
retrorecomp/core.py retrorecomp/cpu.py retrorecomp/gui.py retrorecomp/branding.py retrorecomp/i18n.py retrorecomp/updater.py
retrorecomp/nes_build.py tests/test_nes_build.py
retrorecomp/library.py retrorecomp/knowledge.py retrorecomp/paths.py retrorecomp/publishing.py retrorecomp/packing.py tests/test_packing.py
assets/compilation-knowledge.json.gz tools/build_compilation_knowledge.py tests/test_knowledge.py docs/COMPILATION_LIBRARY.md
retrorecomp/knowledge_build.py retrorecomp/knowledge_exchange.py tests/test_knowledge_exchange.py
retrorecomp/online.py tests/test_online.py tests/test_shared_sync.py
retrorecomp/gameboy_host.py
retrorecomp/tooltips.py retrorecomp/validation.py retrorecomp/windows.py
retrorecomp/dropfiles.py tests/test_dropfiles.py
native/snes_dsp1_projection.inc
native/snes_dsp1_vectors.h
tools/snes_hdma_selftest.py
retrorecomp/peripherals.py
retrorecomp/metadata.py tests/test_metadata.py
retrorecomp/systems/__init__.py retrorecomp/systems/master_system.py
retrorecomp/systems/game_gear.py retrorecomp/systems/game_boy.py
retrorecomp/gameboy.py retrorecomp/gameboy_runtime.py
retrorecomp/gameboy_build.py retrorecomp/gameboy_boundary.py tests/test_gameboy_build.py
native/gb_boundary_checks.c tools/gameboy_boundary_selftest.py
retrorecomp/gameboy_timing.py retrorecomp/gameboy_hardware.py
native/gb_audio_checks.c tools/gameboy_hardware_selftest.py
retrorecomp/gameboy_coverage.py tests/test_gameboy_coverage.py
retrorecomp/nes.py retrorecomp/nes_codegen.py retrorecomp/nes_runtime.py retrorecomp/nes_ram.py retrorecomp/systems/nes.py tests/test_nes.py
tests/test_nes_ram.py
native/CMakeLists.txt native/banked_cpu_checks.c native/banked_dispatch.c
native/banked_emitter.inc native/banked_runtime.inc native/banked_vectors.c
native/controls.c native/controls.h native/host.c native/host_checks.c
native/host_control.h native/icon.c native/icon.h native/icon_checks.c
native/input_checks.c native/launcher.c native/learning.c native/learning.h
native/manifest.inc native/paths.c native/paths.h native/ui.c native/ui.h
native/xbr_filter.h native/xbr_sdl.h native/xbr_checks.c tools/xbr_selftest.py
native/scale2x.h native/planar_rows.h native/stereo_fir.h
native/nes_sprite_shift.h native/nes_sprite_extra.inc
native/pixel_optimization_checks.c tools/pixel_optimization_selftest.py
tests/fixtures/presentation/mode4_reference.inc
docs/RUNTIME_PERFORMANCE.md
native/retro_menu.c native/retro_menu.h native/retro_keyboard.h native/gb_menu.inc
native/gb_ram_helpers.h native/gb_ram_checks.c tools/gameboy_ram_selftest.py
native/nes_host_ui.c native/nes_dense_codegen.inc native/nes_live_codegen.inc native/nes_ram.inc
native/nes_audio_output.inc native/nes_audio_checks.c tools/nes_audio_selftest.py
native/nes_dense_checks.c tools/nes_native_selftest.py
native/nes_guarded_checks.c tools/nes_guarded_selftest.py
native/nes_windows_checks.c tools/nes_windows_selftest.py
native/retro_nes.h native/nes_machine_state.inc native/nes_mapper_state.inc native/nes_state.c
native/nes_machine_checks.c tools/nes_machine_selftest.py
native/nes_ppu_fast.inc native/nes_ppu_lazy.inc native/nes_ppu_checks.c tools/nes_ppu_selftest.py
tools/nes_state_selftest.py
retrorecomp/nes_machine.py retrorecomp/nes_catalog.py retrorecomp/nes_optimization.py
retrorecomp/cartridge16.py retrorecomp/console16.py retrorecomp/megadrive.py retrorecomp/megadrive_codegen.py retrorecomp/systems/console16.py
retrorecomp/m68000.py native/m68000_state_helpers.h native/m68000_backend.h native/m68000_backend.c
native/m68000_backend_checks.c tools/m68000_backend_selftest.py
retrorecomp/neogeo.py retrorecomp/neogeo_build.py retrorecomp/systems/neogeo.py
retrorecomp/neogeo_catalogue.py retrorecomp/neogeo_conversion.py
retrorecomp/neogeo_state_checks.py retrorecomp/neogeo_knowledge.py
retrorecomp/neogeo_persistence_checks.py
tests/test_neogeo_converter.py tools/build_neogeo_knowledge.py
assets/neogeo-catalogue.json
native/neogeo_input.h native/neogeo_lithogen.c native/neogeo_main.c native/neogeo_reference.h native/neogeo_reference.c
tools/neogeo_prototype.py tools/neogeo_qualification.py tests/test_neogeo.py docs/NEOGEO.md
retrorecomp/neogeo_codegen.py retrorecomp/neogeo_z80.py retrorecomp/neogeo_validation.py
native/neogeo_native.c native/neogeo_native.h native/neogeo_z80_native.h native/neogeo_decode.c
native/neogeo_code_view.inc native/neogeo_board_checks.c tools/neogeo_board_selftest.py
native/neogeo_lspc_state.inc native/neogeo_sprite_decode.h
native/neogeo_lspc_checks.c
native/neogeo_timer_checks.c native/neogeo_sound_checks.c native/neogeo_ym_checks.c
tools/neogeo_campaign.py
tools/neogeo_campaign_review.py
native/neogeo_m68000_checks.c native/neogeo_z80_checks.c
native/neogeo_host.c native/neogeo_host.h native/neogeo_state.c native/neogeo_state_validate.c native/neogeo_ym_state.inc
native/neogeo_ui_test.c native/neogeo_controls_checks.c
native/neogeo_persistence.c native/neogeo_persistence.h native/neogeo_persistence_checks.c
native/neogeo_path_io.h
tools/neogeo_persistence_selftest.py
tools/neogeo_state_selftest.py tools/neogeo_host_selftest.py tools/neogeo_controls_selftest.py
tools/neogeo_m68000_selftest.py tools/neogeo_z80_selftest.py tests/test_neogeo_native.py
retrorecomp/cps1.py retrorecomp/cps1_catalogue.py assets/cps1-catalogue.json
tools/build_cps1_catalogue.py licenses/cps1-machine.md tests/test_cps1.py
retrorecomp/cps1_board.py retrorecomp/cps1_build.py tests/test_cps1_board.py licenses/cps1-ymfm.md
native/cps1_machine.c native/cps1_machine.h native/cps1_oki.c native/cps1_oki.h
native/cps1_opm.cpp native/cps1_opm.h native/cps1_m68kconf.h native/cps1_probe.c
native/cps1_native.c native/cps1_native.h native/cps1_z80_native.h
retrorecomp/cps1_codegen.py tests/test_cps1_codegen.py
native/cps1_host.c native/cps1_host.h native/cps1_main.c retrorecomp/cps1_conversion.py
retrorecomp/systems/cps1.py tests/test_cps1_integration.py docs/CPS1.md
native/retro_console16.h native/console16_main.c native/console16_host_ui.c native/scanlines.h
native/scanline_sdl.h native/display_settings.h
native/display_settings_checks.c tools/display_settings_selftest.py
tools/gameboy_display_selftest.py
native/console16_state.c native/console16_state.h native/md_portable_state.inc
retrorecomp/console16_state.py tools/console16_state_selftest.py
native/md_backend.c native/md_decode_dump.c native/md_native_steps.h native/md_exception_decode.h native/md_step_dispatch.c
native/md_battery.c native/md_battery.h retrorecomp/megadrive_sram.py retrorecomp/megadrive_memory.py
native/md_cart.h native/md_cart.inc native/md_eeprom.h native/md_eeprom_checks.c
native/md_cart_checks.c native/md_mapper_checks.c
retrorecomp/megadrive_cart.py tools/megadrive_eeprom_selftest.py tools/megadrive_mapper_selftest.py
tools/megadrive_eeprom_state_selftest.py tools/megadrive_irq_collision_selftest.py tests/test_setup_lock.py
native/md_sram_checks.c tools/megadrive_sram_selftest.py tests/test_megadrive_sram.py
tools/megadrive_save_selftest.py
native/md_native_checks.c tools/megadrive_native_selftest.py tests/test_megadrive.py
native/md_cycle_checks.c tools/megadrive_cycles_selftest.py
native/md_exception_checks.c tools/megadrive_exception_selftest.py
tests/fixtures/md-exceptions/cases.json tests/fixtures/md-exceptions/LICENSE
docs/MEGADRIVE_CPU_EXCEPTIONS.md
native/snes_backend.c native/snes_native_steps.h native/snes_native_checks.c
retrorecomp/snes_codegen.py retrorecomp/supernintendo.py
retrorecomp/snes_timing.py native/snes_timing.h
retrorecomp/snes_video.py
retrorecomp/snes_dma.py native/snes_dma.h native/snes_hdma.inc
retrorecomp/snes_bus.py native/snes_bus.h native/snes_bus.inc
retrorecomp/snes_ppu_bus.py native/snes_ppu_bus.inc
native/snes_ppu_cache.inc native/snes_ppu_cache_checks.c tools/snes_ppu_cache_selftest.py
retrorecomp/console16_optimization.py tests/test_console16_optimization.py
retrorecomp/megadrive_audio.py native/md_audio_loop.inc native/md_audio_bridge_checks.c
native/md_audio_resample.inc native/md_audio_mix.h native/md_audio_mix_checks.c
tools/megadrive_audio_bridge_selftest.py
native/snes_ppu_bus_checks.c tools/snes_ppu_bus_selftest.py
native/snes_bus_checks.c tools/snes_bus_selftest.py
retrorecomp/snes_chips.py
native/snes_dma_checks.c tools/snes_dma_selftest.py tests/test_snes_chips.py
native/snes_chip_checks.c tools/snes_chip_selftest.py
retrorecomp/snes_cart.py native/snes_cart.h native/snes_battery.c native/snes_battery.h
native/snes_cart_checks.c tools/snes_cart_selftest.py tests/test_snes_cart.py
tools/snes_ram_selftest.py
native/snes_video_checks.c tools/snes_video_selftest.py tools/snes_object_selftest.py
tests/test_snes_video.py
docs/SNES.md
native/snes_timing_checks.c tools/snes_timing_selftest.py tests/test_snes_timing.py
retrorecomp/snes_spc.py native/snes_spc_native.h native/snes_spc_runtime.c
native/snes_spc_checks.c tools/snes_spc_selftest.py tests/test_snes_spc.py
retrorecomp/guns16.py retrorecomp/gun16_runtime.py
retrorecomp/megadrive_runtime.py native/md_ym_timers.h native/md_timing.h tools/megadrive_audio_selftest.py
native/md_timing_checks.c tools/megadrive_timing_selftest.py
native/console16_video.h native/md_video_checks.c tools/megadrive_video_selftest.py
native/md_raster_checks.c tools/megadrive_raster_selftest.py
docs/MEGADRIVE_VIDEO.md
retrorecomp/megadrive_fifo.py native/md_vdp_fifo.h native/md_vdp_fifo.inc
native/md_fifo_checks.c tools/megadrive_fifo_selftest.py tests/test_megadrive_fifo.py
retrorecomp/megadrive_dma.py native/md_vdp_dma.h native/md_vdp_dma.inc
retrorecomp/megadrive_read.py native/md_vdp_read.h native/md_vdp_read.inc
retrorecomp/megadrive_bus.py native/md_bus_scheduler.h native/md_z80_bus.inc
native/md_prefetch.h native/md_prefetch.inc native/md_prefetch_checks.c
native/md_prefetch_plan_checks.c tools/megadrive_prefetch_plan_selftest.py
tools/megadrive_prefetch_selftest.py tests/fixtures/md-prefetch/cases.json tests/fixtures/md-prefetch/authored.json tests/fixtures/md-prefetch/LICENSE
docs/MEGADRIVE_PREFETCH.md
native/md_bus_checks.c tools/megadrive_bus_selftest.py
native/md_boundary_checks.c tools/megadrive_boundary_selftest.py
native/md_vdp_batch_checks.c tools/megadrive_vdp_batch_selftest.py
native/md_vdp_pixels.inc retrorecomp/megadrive_video.py
native/md_read_checks.c tools/megadrive_read_selftest.py tests/test_megadrive_read.py
native/md_dma_checks.c tools/megadrive_dma_selftest.py tests/test_megadrive_dma.py
retrorecomp/megadrive_z80.py native/md_z80_native.h native/md_z80_runtime.c
retrorecomp/megadrive_z80_timing.py tests/fixtures/z80_phases.json docs/MEGADRIVE_Z80_TIMING.md
native/md_z80_checks.c tools/megadrive_z80_selftest.py tests/test_megadrive_z80.py
native/md_z80_resume_checks.c tools/megadrive_z80_resume_selftest.py tools/megadrive_interrupt_selftest.py
retrorecomp/megadrive_hardware.py tools/megadrive_progression_selftest.py tests/test_megadrive_progression.py docs/MEGADRIVE_EEPROM.md docs/MEGADRIVE_MAPPERS.md
native/gun16.h native/gun16.c native/gun16_checks.c
tools/gun16_selftest.py tests/test_guns16.py docs/GUNS_16BIT.md
  tools/snes_native_selftest.py tools/snes_scheduler_selftest.py tests/test_snes.py tests/test_console16.py docs/CONSOLES_16BIT.md retrorecomp/random_routes.py tests/test_random_routes.py retrorecomp/scan_levels.py tests/test_scan_levels.py
native/gb_input_refresh.inc native/gb_audio_output.inc
native/gb_latency_checks.cpp tools/gameboy_latency_selftest.py
native/video_frame.h native/video_mode4.inc native/video_checks.c native/video_probe.c
native/lightphaser.c native/lightphaser.h native/lightphaser_checks.c
native/frame_stop_checks.c
native/gamestate.h native/gamestate.inc native/state_io.h native/psg_state.inc native/psg_runs.inc
native/gamestate_checks.c tools/gamestate_selftest.py docs/GAME_STATES.md
native/lazy_data_checks.c tools/lazy_data_selftest.py
native/presentation_checks.c tools/presentation_selftest.py
native/audio_output.inc native/audio_checks.c tools/audio_selftest.py
tests/test_artwork.py tests/test_batch.py tests/test_i18n.py
tests/test_library.py tests/test_publishing.py tests/test_updater.py tests/test_rom.py
tests/test_toolchain.py tests/test_legacy_compat.py tools/toolchain_compare.py tools/nes_state_cross.py
tools/state16_cross.py tools/neogeo_state_cross.py tools/x68000_cross.py
tests/test_validation.py tests/test_publication.py
tests/test_peripherals.py
tools/banked_cpu_selftest.py tools/banked_selftest.py
tools/banked_vector_selftest.py tools/banked_verify.py tools/cpu_selftest.py
tools/data_selftest.py tools/fetch_z80_vectors.py tools/gui_smoke.py
tools/host_selftest.py tools/icon_selftest.py tools/install_converter.py
tools/learning_selftest.py tools/package.ps1 tools/player2_selftest.py
tools/prepare_logo.py tools/publishing_selftest.py tools/prepare_publication.py
tools/lightphaser_selftest.py tools/video_selftest.py docs/LIGHT_PHASER.md docs/VIDEO.md
native/sms_sprite_probe.c tools/sms_sprite_selftest.py
tools/frame_stop_selftest.py
tests/test_game_gear.py tests/test_game_boy.py
retrorecomp/cover_keyring.py tests/test_cover_keyring.py
tools/package_linux.py docs/LINUX.md licenses/Linux-desktop.md
""".split())
PUBLIC_SET = frozenset(PUBLIC_FILES)
# Every public converter module is frozen into the executable, including ones
# no application path imports yet (profiles in development): packaging passes
# these as hidden imports and audit_executable checks each against its source.
PUBLIC_MODULES = tuple(sorted(name[:-3].replace("/", ".").removesuffix(".__init__")
                              for name in PUBLIC_FILES if name.startswith("retrorecomp/") and name.endswith(".py")))


# Third-party modules the interface needs that PyInstaller's analysis can miss.
# PIL._tkinter_finder registers Pillow's Tk image bridge (ImageTk): without it
# the Linux converter stopped at its first header picture ("PyImagingPhoto").
RUNTIME_MODULES = ("PIL._tkinter_finder", "PIL.ImageTk")


def write_module_hook(directory: Path) -> Path:
    """PyInstaller hook listing PUBLIC_MODULES (a command line would be too long on Windows)."""
    directory.mkdir(parents=True, exist_ok=True)
    hook = directory / "hook-retrorecomp.py"
    hook.write_text("hiddenimports = " + repr(list(PUBLIC_MODULES) + list(RUNTIME_MODULES)) + "\n", encoding="utf-8")
    return hook
# Each converter carries only the UPX build that packs its own games
# (retrorecomp/packing.py): the Windows one, or the Linux x86-64 one.
PACKERS = frozenset(("assets/tools/upx.exe", "assets/tools/upx-amd64_linux"))
PACKER = "assets/tools/upx.exe" if os.name == "nt" else "assets/tools/upx-amd64_linux"
BUNDLED_FILES = frozenset(p for p in PUBLIC_FILES
                          if (p.startswith(("native/", "assets/", "profiles/", "MEDIAS/trackers_chiploom/"))
                          or (p.startswith("licenses/") and p.endswith(".md"))
                          or p in {"LICENSE", "THIRD_PARTY_NOTICES.md"}
                          # X68000 generators: hashed into the SDK stamp, read as files by CMake.
                          or p.startswith("tools/x68000_"))
                          and (p not in PACKERS or p == PACKER))
TEXT_EXTENSIONS = {".py", ".md", ".c", ".cpp", ".h", ".inc", ".ps1", ".toml", ".yml", ".json", ".html", ".css"}
SENSITIVE = {
    "private drive path": re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Projects)[\\/]"),
    "private network path": re.compile(r"\\\\(?:\d{1,3}\.){3}\d{1,3}\\"),
    "GitHub credential": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained credential": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    "API credential": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "AWS credential": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "literal password": re.compile(r"(?i)\b(?:password|api_key|access_token)\s*=\s*['\"][^'\"]{8,}['\"]"),
}


def check_public_file(name: str, data: bytes) -> None:
    """Fail with the rule name only, without printing sensitive contents."""
    if name not in PUBLIC_SET:
        raise ValueError(f"Not on the public allowlist: {name}")
    if name == 'assets/cover-references.json':
        from retrorecomp.cover_references import MAX_BYTES, validate_payload
        if len(data) > MAX_BYTES:
            raise ValueError('Cover references exceed their size limit.')
        validate_payload(json.loads(data))
    if name == 'assets/neogeo-catalogue.json':
        from retrorecomp.neogeo_catalogue import SHA256
        if hashlib.sha256(data).hexdigest()!=SHA256:
            raise ValueError('Neo Geo catalogue failed its integrity check.')
    if name == 'assets/cps1-catalogue.json':
        from retrorecomp.cps1_catalogue import SHA256
        if hashlib.sha256(data).hexdigest()!=SHA256:
            raise ValueError('CPS-1 catalogue failed its integrity check.')
    if name == 'assets/compilation-knowledge.json.gz':
        import gzip, io
        from retrorecomp.knowledge import MAX_BYTES, validate_payload
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Compilation knowledge exceeds its size limit.')
        validate_payload(json.loads(raw))
    if Path(name).suffix.lower() in TEXT_EXTENSIONS or name == "LICENSE":
        content = data.decode("utf-8-sig")
        for label, pattern in SENSITIVE.items():
            if pattern.search(content):
                raise ValueError(f"{name}: {label}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_sources(root: Path) -> dict:
    entries = []
    for name in PUBLIC_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symbolic-link public file: {name}")
        data = path.read_bytes()
        check_public_file(name, data)
        entries.append({"path": name, "bytes": len(data), "sha256": digest(data)})
    return {"files": entries, "count": len(entries)}


def stage_sources(root: Path, target: Path) -> dict:
    report = audit_sources(root)
    if target == root or root.is_relative_to(target):
        raise ValueError("The public snapshot must be separate from the source root.")
    target.mkdir(parents=True, exist_ok=True)
    # Repeated preparation overwrites only approved files; never delete user data.
    for name in PUBLIC_FILES:
        dest = target / name
        if dest.is_symlink() or not dest.resolve().is_relative_to(target.resolve()):
            raise ValueError(f"Unsafe snapshot path: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
    audit_sources(target)
    extras = [p.relative_to(target).as_posix() for p in target.rglob("*")
              if p.is_file() and p.relative_to(target).as_posix() not in PUBLIC_SET
              and not any(part in {".git", ".build", "Export", "__pycache__"}
                          for part in p.relative_to(target).parts)]
    if extras:
        raise ValueError(f"Unexpected snapshot files: {extras}")
    return report


def audit_staged(root: Path) -> dict:
    names = subprocess.check_output(["git", "diff", "--cached", "--name-only",
                                     "--diff-filter=ACMR", "-z"], cwd=root)
    paths = [p.decode("utf-8") for p in names.split(b"\0") if p]
    for name in paths:
        data = subprocess.check_output(["git", "show", f":{name}"], cwd=root)
        check_public_file(name, data)
    return {"staged_count": len(paths), "staged_files": paths}


def audit_tracked(root: Path) -> dict:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    paths = [p.decode("utf-8") for p in names.split(b"\0") if p]
    for name in paths:
        if name not in PUBLIC_SET:
            raise ValueError(f"Not on the public allowlist: {name}")
        check_public_file(name, (root / name).read_bytes())
    return {"tracked_count": len(paths), "tracked_files": paths}


def audit_executable(executable: Path, source: Path) -> dict:
    """Inspect decompressed PyInstaller assets and our compiled Python modules."""
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    bundled = {}
    audio = []
    gamepads = []
    for original in archive.toc:
        name = original.replace("\\", "/")
        if name.startswith('player-runtime/'):
            leaf = Path(name).name
            if leaf not in ('retro_gamepad.dll', 'libretro_gamepad.so'):
                raise ValueError('Unexpected controller library: ' + name)
            built = source / '.build/player-gamepad/runtime' / leaf
            if not built.is_file() or archive.extract(original) != built.read_bytes():
                raise ValueError('Controller library differs from native build: ' + name)
            gamepads.append(name)
        if name.startswith('credits-runtime/'):
            leaf = Path(name).name
            if leaf not in ('retro_credits.dll', 'libretro_credits.so'):
                raise ValueError('Unexpected credits audio library: ' + name)
            built = source / '.build/credits-audio/runtime' / leaf
            if not built.is_file() or archive.extract(original) != built.read_bytes():
                raise ValueError('Credits audio differs from the native build: ' + name)
            audio.append(name)
        if name.startswith(("native/", "assets/", "profiles/", "licenses/", "MEDIAS/trackers_chiploom/",
                            "tools/x68000_")) or name in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
            if name not in BUNDLED_FILES:
                raise ValueError(f"Unexpected executable payload: {name}")
            data = archive.extract(original)
            if data != (source / name).read_bytes():
                raise ValueError(f"Executable payload differs from public source: {name}")
            if name in ('assets/compilation-knowledge.json.gz', 'assets/cover-references.json'):
                check_public_file(name, data)
            bundled[name] = digest(data)
        if name.lower().endswith((".sms", ".gg", ".gb", ".nes", ".fds", ".rom", ".bin",
                                  ".sfc", ".smc", ".gen", ".smd", ".neo", ".rrfb",
                                  ".rrstate", ".rrsave", ".manifest", ".patterns", "bios.zip")):
            raise ValueError(f"Game data in executable: {name}")
    if set(bundled) != BUNDLED_FILES:
        raise ValueError("The executable is missing public resources.")
    if len(audio) != 1:
        raise ValueError('The executable needs exactly one native credits player.')
    if len(gamepads) != 1:
        raise ValueError('The executable needs exactly one controller bridge.')
    pyz = archive.open_embedded_archive("PYZ.pyz")
    modules = []
    for module in PUBLIC_MODULES:
        name = module.replace(".", "/") + ("/__init__.py" if (source / module.replace(".", "/")).is_dir() else ".py")
        actual = pyz.extract(module)
        expected = compile((source / name).read_text(encoding="utf-8-sig"),
                           actual.co_filename, "exec", dont_inherit=True, optimize=0)
        if actual != expected:
            raise ValueError(f"Frozen Python differs from public source: {module}")
        modules.append(module)
    for module in RUNTIME_MODULES:
        try:
            pyz.extract(module)
        except Exception as error:
            raise ValueError(f"The executable lacks a module its interface needs: {module}") from error
    entry = marshal.loads(archive.extract("RetroRecomp"))
    expected = compile((source / "RetroRecomp.py").read_text(encoding="utf-8-sig"),
                       entry.co_filename, "exec", dont_inherit=True, optimize=0)
    if entry != expected:
        raise ValueError("Frozen entrypoint differs from public source.")
    return {"archive_entries": len(archive.toc), "resources": bundled,
            "modules": modules, "sha256": digest(executable.read_bytes())}


def make_standalone(source: Path, executable: Path, target: Path) -> dict:
    """Publish the converter as a single EXE with linked source and bundled notices."""
    proof = audit_executable(executable, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.exe.pending')
    shutil.copyfile(executable, temporary)
    temporary.replace(target)
    sha = digest(target.read_bytes())
    return {"exe": str(target), "sha256": sha, "bytes": target.stat().st_size,
            "executable": proof}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--stage", type=Path, help="Create an allowlisted public source snapshot.")
    parser.add_argument("--staged", action="store_true", help="Audit outgoing Git index files.")
    parser.add_argument("--tracked", action="store_true", help="Audit all tracked public files (CI).")
    parser.add_argument("--exe", type=Path, help="Clean converter to inspect for --standalone.")
    parser.add_argument("--standalone", type=Path, help="Write a single-file converter.")
    parser.add_argument("--report", type=Path, help="Write a local JSON audit (never bundled).")
    args = parser.parse_args()
    root = args.source.resolve()
    report = {"version": VERSION, "source": audit_sources(root)}
    if args.staged:
        report["git"] = audit_staged(root)
    if args.tracked:
        report["tracked"] = audit_tracked(root)
    if args.stage:
        report["snapshot"] = stage_sources(root, args.stage.resolve())
    if args.standalone:
        if not args.exe:
            parser.error("--standalone requires --exe")
        report["standalone"] = make_standalone(root, args.exe.resolve(), args.standalone.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"public_files": report["source"]["count"],
                      "snapshot": str(args.stage) if args.stage else None,
                      "staged_files": report.get("git", {}).get("staged_count"),
                      "standalone": report.get("standalone", {}).get("exe"),
                      "sha256": report.get("standalone", {}).get("sha256")}, indent=2))


if __name__ == "__main__":
    main()
