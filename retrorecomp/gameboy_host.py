"""Game Boy player shell: the pinned runtime's SDL platform layer on the host kit.

Host only: nothing here changes the generated game, the SM83 runtime or its
validation, so a change here can upgrade exports without rediscovery (see
docs/UPGRADES.md). Machine-side adaptations stay in gameboy_runtime.py.

Since 1.6.3 (host kit phase 5, docs/HOST_KIT.md) the window, the menus, the
bindings, the controllers, the sound device and the pacing are the shell of
native/hostkit, like every other console's. The runtime's own loop stays: the
generated main calls the platform functions of platform_sdl.h, and the patched
platform_sdl.cpp keeps what is upstream's and the player does not see (input
scripts and recording, screenshots, battery, clock and state files, the display
palette) and hands the rest to the adapter native/hostkit/adapters/rrhk_gb.inc,
which includes the entry points the main calls. Every cut below names its
markers in the pinned file and fails if upstream moved them.
"""
from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

from . import hostkit
from .core import replace_once
from .paths import ASSETS

ADAPTER = 'hostkit/adapters/rrhk_gb.inc'

# What the platform layer keeps of its own state: the persistence settings, the display palettes and the pictures it
# remembers. Everything else it used to hold (window, texture, controllers, bindings, menus, sound ring) is the kit's.
STATE = '''/* ============================================================================
 * Platform state. The window, the controls, the menus and the sound belong to the
 * host kit (hostkit/adapters/rrhk_gb.inc); what stays here is the runtime's own.
 * ========================================================================== */

static GBPlatformTimingInfo g_last_timing = {};
static int g_palette_idx = 1;   /* DMG monochrome is the RetroRecomp default; 0 is the classic green */
static bool g_smooth_lcd_transitions = true;
static bool g_launcher_return_enabled = false;
static bool g_benchmark_mode = false;
static std::string g_persistence_dir;
static GBPersistenceTestFault g_persistence_test_fault =
    GB_PERSISTENCE_TEST_FAULT_NONE;
static GBPersistenceTestTarget g_persistence_test_target =
    GB_PERSISTENCE_TEST_TARGET_BATTERY;
static GBPlatformExitAction g_exit_action = GB_PLATFORM_EXIT_QUIT;
static constexpr int GB_SAVESTATE_SLOT_COUNT = 10;
static std::string g_savestate_status;
static const uint32_t g_palettes[][4] = {
    { 0xFFE0F8D0, 0xFF88C070, 0xFF346856, 0xFF081820 }, // Original
    { 0xFFFFFFFF, 0xFFAAAAAA, 0xFF555555, 0xFF000000 }, // B&W
    { 0xFFFFB000, 0xFFCB4F0E, 0xFF800000, 0xFF330000 }  // Amber
};
static uint32_t g_lcd_off_framebuffer[GB_FRAMEBUFFER_SIZE];
static uint32_t g_last_guest_framebuffer[GB_FRAMEBUFFER_SIZE];
static bool g_lcd_off_framebuffer_initialized = false;
static bool g_last_guest_framebuffer_valid = false;
static uint64_t g_present_count = 0;
static GBContext* g_registered_ctx = NULL;
static GBPortFrame g_port_frame = {};
static bool g_port_frame_valid = false;

static bool has_interpreter_activity(const GBContext* ctx) {
    return ctx != NULL &&
           (ctx->total_dispatch_fallbacks > 0 ||
            ctx->total_interpreter_entries > 0 ||
            ctx->has_unimplemented_interpreter_opcode);
}

static bool save_savestate_slot(GBContext* ctx, int slot);
static bool load_savestate_slot(GBContext* ctx, int slot);

'''

# The effective joypad: what the player holds (the kit's pad word) and what an input script holds, together.
JOYPAD = '''static void update_effective_joypad_state(void) {
    g_joypad_dpad = g_manual_joypad_dpad & g_script_joypad_dpad;
    g_joypad_buttons = g_manual_joypad_buttons & g_script_joypad_buttons;
}

'''


def cut(source: str, start: str, end: str, new: str = '') -> str:
    """Replace [start, end) of the pinned platform file; both markers must be there exactly once, in this order."""
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f'Game Boy platform markers changed upstream: {start[:60]!r} .. {end[:60]!r}')
    first, last = source.index(start), source.index(end)
    if last <= first:
        raise ValueError(f'Game Boy platform markers out of order: {start[:60]!r} .. {end[:60]!r}')
    return source[:first] + new + source[last:]


def block_start(source: str, title: str) -> str:
    """The comment frame that opens a section of the pinned file ('/* ===...\\n * <title>')."""
    index = source.find(f' * {title}\n')
    if index < 0 or source.count(f' * {title}\n') != 1:
        raise ValueError(f'Game Boy platform section changed upstream: {title}')
    return source[source.rindex('/*', 0, index):index + len(f' * {title}\n')]


def kit_platform(source: str, title: str) -> str:
    """The pinned runtime/src/platform_sdl.cpp with its shell removed and the kit adapter included."""
    for line in ('#include "imgui.h"\n', '#include "backends/imgui_impl_sdl2.h"\n', '#include "backends/imgui_impl_sdlrenderer2.h"\n'):
        source = replace_once(source, line, '')
    source = replace_once(source, '#include <vector>\n', '#include <algorithm>\n#include <vector>\n')
    # The state: lines of the window, the controllers and the sound go; the persistence and the pictures stay.
    source = cut(source, block_start(source, 'SDL State'), '/* Joypad state - exported for gbrt.c to access */', STATE)
    # The rest of the file, in order. Controllers, labels and the menu helpers.
    source = cut(source, 'static bool platform_default_fullscreen(void) {', 'static bool platform_uses_app_storage_for_relative_paths(void) {')
    source = cut(source, 'static const char* overlay_menu_hint_text(void) {', 'static bool ensure_parent_directory(const fs::path& path) {')
    # Bindings, their defaults and the runtime preferences file.
    source = cut(source, 'static GBInputBinding make_binding(GBInputBindingKind kind, int code) {',
                 'static void set_savestate_status(const char* action, int slot, bool success, const char* detail) {')
    source = replace_once(source, 'static bool recreate_streaming_texture(void);\nstatic void set_app_suspended(bool suspended);\n\n', '')
    # Which actions are held: the kit's pad word replaces the binding tables.
    source = cut(source, 'static bool input_action_is_pressed(GBInputAction action) {',
                 'static void request_joypad_interrupt(GBContext* ctx) {', JOYPAD)
    # Window geometry, filters, textures, fullscreen, the controller axes and the settings panel.
    source = cut(source, 'static double sdl_now_ms(void) {', 'static void ensure_lcd_off_framebuffer(void) {')
    source = replace_once(source, 'palette_idx < IM_ARRAYSIZE(g_palettes)', 'palette_idx < (int)(sizeof(g_palettes) / sizeof(g_palettes[0]))')
    # Presentation, window, sound, events and pacing: the adapter holds the entry points.
    source = cut(source, 'static void render_frame_internal(const uint32_t* framebuffer, bool count_guest_frame) {',
                 block_start(source, 'Save Data'),
                 f'static const char* g_rr_game_title = {json.dumps(title, ensure_ascii=False)};\n#include "{ADAPTER}"\n\n')
    # The slot helpers of the settings panel (the kit's F8 and F9 use slot 1 only).
    source = cut(source, 'static bool savestate_slot_exists(const GBContext* ctx, int slot, std::string* out_path) {',
                 'static bool save_savestate_slot(GBContext* ctx, int slot) {')
    source = cut(source, 'static bool delete_savestate_slot(GBContext* ctx, int slot) {', 'static const char* persistence_kind_name(')
    # A missing data folder is allowed (created only on an actual save), so that reading and an unchanged launch leave no files.
    source = replace_once(source, '''    if (error || !fs::is_directory(resolved, error) || error) {
        return false;
    }
    g_persistence_dir = resolved.string();''',
        '''    if (error || (fs::exists(resolved, error) && !fs::is_directory(resolved, error)) || error) {
        return false;
    }
    /* A missing directory is allowed. It is created only on an actual save. */
    g_persistence_dir = resolved.string();''')
    source = replace_once(source, '''    FILE* file = fopen(staged.string().c_str(), "wb");''',
        '''    if (!ensure_parent_directory(destination)) return false;
    FILE* file = fopen(staged.string().c_str(), "wb");''')
    source = replace_once(source, '''    const bool success = gb_context_save_state_file(ctx, filename);''',
        '''    const bool success = ensure_parent_directory(fs::path(filename)) &&
        gb_context_save_state_file(ctx, filename);''')
    # A loaded state starts the sound and the pictures afresh (the kit clears its ring).
    source = replace_once(source, '''        reset_audio_output_buffer(true);
        g_last_guest_framebuffer_valid = false;
        g_present_count = ctx->completed_frames;
        g_last_frame_time = SDL_GetTicks();''', '''        g_last_guest_framebuffer_valid = false;
        g_present_count = ctx->completed_frames;''')
    source = replace_once(source, '''        .on_audio_sample = on_audio_sample,
        .load_battery_ram = sdl_load_battery_ram,
        .save_battery_ram = sdl_save_battery_ram,
        .load_rtc_data = sdl_load_rtc_data,
        .save_rtc_data = sdl_save_rtc_data
    };''', '''        .on_audio_sample = on_audio_sample,
        .load_battery_ram = sdl_load_battery_ram,
        .save_battery_ram = sdl_save_battery_ram,
        .load_rtc_data = sdl_load_rtc_data,
        .save_rtc_data = sdl_save_rtc_data,
        .refresh_input = rr_gb_refresh_joyp   /* a JOYP read with no scripted pad asks the host for fresh input */
    };''')
    return source


def adapt_shell(project: Path, title: str) -> None:
    """Stage the kit and its headers, and rebuild the platform file of the private project on them."""
    # Keep the compiler checkout pristine. Each generated game carries the shell sources of the other consoles and
    # the Game Boy adapter the patched platform includes.
    for source_name, destination in (
        ('retro_menu.h', project / 'runtime/include/retro_menu.h'),
        ('autofire.h', project / 'runtime/include/autofire.h'),
        ('game_options.h', project / 'runtime/include/game_options.h'),
        ('audio_filter.h', project / 'runtime/include/audio_filter.h'),
        ('audio_cushion.h', project / 'runtime/include/audio_cushion.h'),
        ('retro_keyboard.h', project / 'runtime/include/retro_keyboard.h'),
        ('retro_menu.c', project / 'runtime/src/retro_menu.c'),
        ('font6x10.h', project / 'runtime/src/font6x10.h'),
        ('font10x20.h', project / 'runtime/src/font10x20.h'),
        ('runtime_i18n.h', project / 'runtime/include/runtime_i18n.h'),
        ('platform_io.h', project / 'runtime/include/platform_io.h'),
        ('platform_io.c', project / 'runtime/src/platform_io.c'),
        ('runtime_catalog.inc', project / 'runtime/src/runtime_catalog.inc'),
        ('scanlines.h', project / 'runtime/include/scanlines.h'),
        ('scanline_sdl.h', project / 'runtime/include/scanline_sdl.h'),
        ('xbr_filter.h', project / 'runtime/include/xbr_filter.h'),
        ('scale2x.h', project / 'runtime/include/scale2x.h'),
        ('xbr_sdl.h', project / 'runtime/include/xbr_sdl.h'),
        ('display_settings.h', project / 'runtime/include/display_settings.h'),
        ('console16_video.h', project / 'runtime/include/console16_video.h'),
    ):
        copyfile(ASSETS / 'native' / source_name, destination)
    hostkit.stage(project, 'gb')
    runtime = project / 'runtime/src/platform_sdl.cpp'
    runtime.write_text(kit_platform(runtime.read_text(encoding='utf-8'), title), encoding='utf-8')

    platform_header = project / 'runtime/include/platform_sdl.h'
    source = platform_header.read_text(encoding='utf-8')
    source = replace_once(source, 'bool gb_platform_poll_events(GBContext* ctx);',
        'bool gb_platform_poll_events(GBContext* ctx);\n'
        'bool gb_platform_wait_while_menu(GBContext* ctx);')
    platform_header.write_text(source, encoding='utf-8')


def kit_cmake(source: str) -> str:
    """The kit's shell files, compiled into the runtime library the platform layer lives in."""
    kit = ' '.join(f'${{CMAKE_CURRENT_SOURCE_DIR}}/{name}' for name in hostkit.sources('gb'))
    return source + f'\ntarget_sources(gbrt PRIVATE {kit})\n'
