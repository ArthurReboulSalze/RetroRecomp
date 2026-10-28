"""Game Boy player shell: shared menus, options, fonts, text and filters, and
the SDL platform patches (window, menus, presentation, sound output, input).

Host only: nothing here changes the generated game, the SM83 runtime or its
validation, so a change here can upgrade exports without rediscovery (see
docs/UPGRADES.md). Machine-side adaptations stay in gameboy_runtime.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

from .core import replace_once
from .paths import ASSETS


def disable_imgui_layout_persistence(source: str) -> str:
    """ImGui debug layout is unused; only RetroRecomp preferences are saved."""
    return replace_once(source, '    ImGuiIO& io = ImGui::GetIO(); (void)io;',
                        '''    ImGuiIO& io = ImGui::GetIO(); (void)io;
    /* RetroRecomp uses its own menu and datas preferences. ImGui's unused
       debug-window layout must never create imgui.ini in the launch folder. */
    io.IniFilename = nullptr;''')


def adapt_shell(project: Path, title: str) -> None:
    # Keep the compiler checkout pristine. Each generated game carries the same
    # menu drawing code as the Sega runtimes and a small Game Boy action bridge.
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
        ('gb_menu.inc', project / 'runtime/src/gb_menu.inc'),
        ('scanlines.h', project / 'runtime/include/scanlines.h'),
        ('scanline_sdl.h', project / 'runtime/include/scanline_sdl.h'),
        ('xbr_filter.h', project / 'runtime/include/xbr_filter.h'),
        ('scale2x.h', project / 'runtime/include/scale2x.h'),
        ('xbr_sdl.h', project / 'runtime/include/xbr_sdl.h'),
    ):
        copyfile(ASSETS / 'native' / source_name, destination)
    runtime = project / "runtime/src/platform_sdl.cpp"
    source = runtime.read_text(encoding="utf-8")
    source = replace_once(source, '#include "platform_sdl.h"',
                          '#include "platform_sdl.h"\n#include "runtime_feedback_sdl.h"\n#include "retro_menu.h"\n#include "autofire.h"\n#include "platform_io.h"\n#include "scanline_sdl.h"\n#include "xbr_sdl.h"')
    source = '#include "embedded_resources.h"\n#include "game_options.h"\n' + source
    source = replace_once(source, '    g_renderer = SDL_CreateRenderer(g_window, -1, SDL_RENDERER_ACCELERATED);',
                          '    rr_set_window_icon(g_window);\n#ifndef _WIN32\n    SDL_SetHintWithPriority(SDL_HINT_RENDER_VSYNC,"1",SDL_HINT_DEFAULT);\n#endif\n    g_renderer = SDL_CreateRenderer(g_window, -1, SDL_RENDERER_ACCELERATED);')
    source = replace_once(source, 'static SDL_Texture* g_texture = NULL;',
                          '''static SDL_Texture* g_texture = NULL;
static SDL_Texture* g_rr_scale2x_texture = NULL;
static RrScanlineMask g_rr_scanlines = {};
static RrXbr g_rr_xbr = {};
static uint32_t g_rr_scale2x_pixels[GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT * 4];''')
    source = replace_once(source, 'static bool g_show_menu = false;',
                          '''static bool g_show_menu = false;
static int g_rr_menu_kind = 0;
static int g_rr_menu_row = 0;
static bool g_rr_bind_gamepad = false;
static int g_rr_language = 0;
static bool g_rr_autofire = false;
static RrAutofire g_rr_fire[2] = {};
static uint64_t g_rr_input_frame = 0;
static void rr_gb_toggle_menu(int kind);''')
    source = replace_once(source, 'static int g_palette_idx = 0;', 'static int g_palette_idx = 1;')
    source = replace_once(source, '''typedef enum GBRenderFilterMode {
    GB_RENDER_FILTER_NEAREST = 0,
    GB_RENDER_FILTER_LINEAR = 1,
} GBRenderFilterMode;''', '''typedef enum GBRenderFilterMode {
    GB_RENDER_FILTER_NEAREST = 0,
    GB_RENDER_FILTER_LINEAR = 1,
    GB_RENDER_FILTER_SCALE2X = 2,
    GB_RENDER_FILTER_SCANLINES = 3,
} GBRenderFilterMode;''')
    source = replace_once(source, '''static const char* g_render_filter_names[] = {
    "Nearest",
    "Linear",
};''', '''static const char* g_render_filter_names[] = {
    "Sharp pixels", "xBR smooth", "Scale2x", "Scanlines",
};''')
    source = replace_once(source, 'static bool g_show_overlay = false;',
                          f'static bool g_show_overlay = false;\nstatic const char* g_rr_game_title = {json.dumps(title, ensure_ascii=False)};')
    source = replace_once(source, '"GameBoy Recompiled",\n        SDL_WINDOWPOS_CENTERED,',
                          'g_rr_game_title,\n        SDL_WINDOWPOS_CENTERED,')
    source = replace_once(source, 'char title[64];\n        snprintf(title, sizeof(title), "GameBoy Recompiled - Frame %d", g_frame_count);',
                          'char title[512];\n        snprintf(title, sizeof(title), "%s | %s", g_rr_game_title,\n                 has_interpreter_activity(g_registered_ctx) ? "Interpreter fallback" : "Native code");')
    source = replace_once(source, 'char title[96];\n        if (g_frame_count == 0) {\n            snprintf(title, sizeof(title), "GameBoy Recompiled - Starting... (%llu)",\n                     (unsigned long long)(g_present_count / 30));\n        } else {\n            snprintf(title, sizeof(title), "GameBoy Recompiled - Frame %d (Working...)",\n                     g_frame_count);\n        }',
                          'char title[512];\n        snprintf(title, sizeof(title), "%s | %s", g_rr_game_title,\n                 has_interpreter_activity(g_registered_ctx) ? "Interpreter fallback" : "Native code");')
    source = replace_once(source, '} else if (g_show_overlay) {',
                          '} else if (g_show_overlay && !g_fullscreen) {')
    source = replace_once(source, '''static std::string runtime_preferences_path(void) {
    const std::string pref_dir = make_pref_storage_dir("runtime");
    if (!pref_dir.empty()) {
        fs::path resolved = fs::path(pref_dir) / "runtime_prefs.ini";
        ensure_parent_directory(resolved);
        return resolved.lexically_normal().string();
    }
    return fs::path("runtime_prefs.ini").lexically_normal().string();
}''', '''static std::string runtime_preferences_path(void) {
    /* Shared by Game Boy exports; reading settings never creates a folder. */
    char* base = SDL_GetBasePath();
    if (!base) return std::string("datas/Retro-Recomp-GameBoy.ini");
    const fs::path resolved = fs::path(base) / "datas" / "Retro-Recomp-GameBoy.ini";
    SDL_free(base);
    return resolved.lexically_normal().string();
}
static void rr_gb_shared_language(bool save) {
    char* base=SDL_GetBasePath(); if(!base)return;
    const std::string path=(fs::path(base)/"datas"/"Retro-Recomp.ini").string();
    SDL_free(base);
    wchar_t wide[32768],value[16];
    if(!rr_from_utf8(path.c_str(),wide,32768))return;
    if(save) rr_ini_set(L"Interface",L"language",rr_language_wide(g_rr_language),wide);
    else if(rr_ini_get(L"Interface",L"language",L"",value,16,wide)>0) {
        g_rr_language=rr_language_from_wide(value); rr_language_set(g_rr_language);
    }
}''')
    source = replace_once(source, '''    FILE* file = fopen(path.c_str(), "w");
    if (!file) {
        fprintf(stderr, "[SDL] Failed to save runtime prefs to %s\\n", path.c_str());''',
        '''    if (!ensure_parent_directory(fs::path(path))) {
        fprintf(stderr, "[SDL] Failed to create runtime prefs directory\\n");
        return;
    }
    FILE* file = fopen(path.c_str(), "w");
    if (!file) {
        fprintf(stderr, "[SDL] Failed to save runtime prefs to %s\\n", path.c_str());''')
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
    # SDL scancodes identify physical positions. Resolve W/X from the active
    # keyboard layout so an AZERTY keyboard still uses its labelled W/X keys.
    source = replace_once(source, 'static void set_default_input_bindings(void) {', '''static SDL_Scancode rr_letter_key(SDL_Keycode key, SDL_Scancode fallback) {
    const SDL_Scancode mapped = SDL_GetScancodeFromKey(key);
    return mapped == SDL_SCANCODE_UNKNOWN ? fallback : mapped;
}

static void set_default_input_bindings(void) {''')
    for old, new in (
        ('GB_INPUT_ACTION_UP][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_W)', 'GB_INPUT_ACTION_UP][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_DOWN][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_S)', 'GB_INPUT_ACTION_DOWN][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_LEFT][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_A)', 'GB_INPUT_ACTION_LEFT][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_RIGHT][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_D)', 'GB_INPUT_ACTION_RIGHT][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_A][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_Z)', 'GB_INPUT_ACTION_A][0] = make_binding(GB_INPUT_BINDING_KEY, rr_letter_key(SDLK_w, SDL_SCANCODE_W))'),
        ('GB_INPUT_ACTION_A][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_J)', 'GB_INPUT_ACTION_A][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_B][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_X)', 'GB_INPUT_ACTION_B][0] = make_binding(GB_INPUT_BINDING_KEY, rr_letter_key(SDLK_x, SDL_SCANCODE_X))'),
        ('GB_INPUT_ACTION_B][1] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_K)', 'GB_INPUT_ACTION_B][1] = make_binding(GB_INPUT_BINDING_NONE, 0)'),
        ('GB_INPUT_ACTION_SELECT][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_BACKSPACE)', 'GB_INPUT_ACTION_SELECT][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_LSHIFT)'),
    ):
        source = replace_once(source, 'g_keyboard_bindings[' + old + ';', 'g_keyboard_bindings[' + new + ';')
    source = replace_once(source, '''    g_savestate_slot = 0;
    g_savestate_status.clear();''', '''    g_savestate_slot = 0;
    g_palette_idx = 1; /* DMG monochrome is the RetroRecomp default. */
    g_render_filter_mode = GB_RENDER_FILTER_NEAREST;
    g_fullscreen = false;
    g_render_scaling_mode = GB_RENDER_SCALING_PIXEL_PERFECT;
    g_rr_language = 0; rr_language_set(0);
    g_rr_autofire = false;
    g_savestate_status.clear();''')
    source = replace_once(source, '''                if (strcmp(key, "audio.enabled") == 0) {''', '''                if (strcmp(key, "video.display_mode") == 0) {
                    long parsed = strtol(value, NULL, 10);
                    if (parsed >= 0 && parsed < 3) {
                        g_fullscreen = parsed != 0;
                        g_render_scaling_mode = parsed == 2 ? GB_RENDER_SCALING_ASPECT_FIT : GB_RENDER_SCALING_PIXEL_PERFECT;
                    }
                    continue;
                }
                if (strcmp(key, "video.filter") == 0) {
                    long parsed = strtol(value, NULL, 10);
                    if (parsed >= 0 && parsed <= GB_RENDER_FILTER_SCANLINES)
                        g_render_filter_mode = (GBRenderFilterMode)parsed;
                    continue;
                }
                if (strcmp(key, "video.palette") == 0) {
                    g_palette_idx = strcmp(value, "green") == 0 ? 0 : 1;
                    continue;
                }
                if (strcmp(key, "ui.language") == 0) {
                    g_rr_language = rr_language_from_code(value); rr_language_set(g_rr_language);
                    continue;
                }
                if (strcmp(key, "input.autofire") == 0) {
                    g_rr_autofire = strcmp(value, "1") == 0;
                    continue;
                }
                if (strcmp(key, "audio.enabled") == 0) {''')
    source = replace_once(source, '''    fprintf(file, "audio.enabled=%d\\n", g_audio_output_enabled ? 1 : 0);''',
        '''    fprintf(file, "video.filter=%d\\n", (int)g_render_filter_mode);
    fprintf(file, "video.display_mode=%d\\n", g_fullscreen ? (g_render_scaling_mode == GB_RENDER_SCALING_PIXEL_PERFECT ? 1 : 2) : 0);
    fprintf(file, "video.palette=%s\\n", g_palette_idx == 1 ? "mono" : "green");
    fprintf(file, "ui.language=%s\\n", rr_language_code(g_rr_language));
    fprintf(file, "input.autofire=%d\\n", g_rr_autofire ? 1 : 0);
    fprintf(file, "audio.enabled=%d\\n", g_audio_output_enabled ? 1 : 0);''')
    source = replace_once(source, '''            const char* name = SDL_GetScancodeName((SDL_Scancode)binding.code);
            return (name && name[0]) ? std::string(name) : ("Scancode " + std::to_string((int)binding.code));''', '''            const SDL_Scancode scan = (SDL_Scancode)binding.code;
            const char* name = SDL_GetKeyName(SDL_GetKeyFromScancode(scan));
            if (!name || !name[0]) name = SDL_GetScancodeName(scan);
            return (name && name[0]) ? std::string(name) : ("Scancode " + std::to_string((int)binding.code));''')
    # Keep the upstream input storage and state implementation, but replace
    # its visible settings panel with the shared RetroRecomp game menu.
    for before, after in (
        ("g_keyboard_bindings[GB_INPUT_ACTION_SAVE_STATE][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F5);",
         "g_keyboard_bindings[GB_INPUT_ACTION_SAVE_STATE][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F8);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_LOAD_STATE][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F8);",
         "g_keyboard_bindings[GB_INPUT_ACTION_LOAD_STATE][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F9);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_PREVIOUS_STATE_SLOT][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F6);",
         "g_keyboard_bindings[GB_INPUT_ACTION_PREVIOUS_STATE_SLOT][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_NEXT_STATE_SLOT][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F7);",
         "g_keyboard_bindings[GB_INPUT_ACTION_NEXT_STATE_SLOT][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_OVERLAY][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F1);",
         "g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_OVERLAY][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_MENU][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F10);",
         "g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_MENU][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_P);"),
        ("g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_PORT_UI][0] = make_binding(GB_INPUT_BINDING_KEY, SDL_SCANCODE_F2);",
         "g_keyboard_bindings[GB_INPUT_ACTION_TOGGLE_PORT_UI][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_controller_bindings[GB_INPUT_ACTION_SAVE_STATE][0] = make_binding(GB_INPUT_BINDING_CONTROLLER_BUTTON, SDL_CONTROLLER_BUTTON_X);",
         "g_controller_bindings[GB_INPUT_ACTION_SAVE_STATE][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_controller_bindings[GB_INPUT_ACTION_LOAD_STATE][0] = make_binding(GB_INPUT_BINDING_CONTROLLER_BUTTON, SDL_CONTROLLER_BUTTON_Y);",
         "g_controller_bindings[GB_INPUT_ACTION_LOAD_STATE][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
        ("g_controller_bindings[GB_INPUT_ACTION_TOGGLE_PORT_UI][0] = make_binding(GB_INPUT_BINDING_CONTROLLER_BUTTON, SDL_CONTROLLER_BUTTON_RIGHTSTICK);",
         "g_controller_bindings[GB_INPUT_ACTION_TOGGLE_PORT_UI][0] = make_binding(GB_INPUT_BINDING_NONE, 0);"),
    ):
        source = replace_once(source, before, after)
    source = replace_once(source, '''                case SDL_SCANCODE_F2:
                    if (ctx && pressed && event->key.repeat == 0) {
                        const GBPortInputEvent port_event = {
                            GB_PORT_INPUT_TOGGLE_UI, true};
                        gbrt_port_input(ctx, &port_event);
                    }
                    return true;

                case SDL_SCANCODE_F3:
                    if (ctx && pressed && event->key.repeat == 0) {
                        const GBPortInputEvent port_event = {
                            GB_PORT_INPUT_TOGGLE_ENCOUNTERS, true};
                        gbrt_port_input(ctx, &port_event);
                    }
                    return true;''', '''                case SDL_SCANCODE_F1:
                    /* F1 opens help; Shift+F1 restarts at once. */
                    if (pressed && event->key.repeat == 0 && !(event->key.keysym.mod & KMOD_SHIFT))
                        g_show_menu = !g_show_menu;
                    else if (ctx && pressed && event->key.repeat == 0) {
                        gb_context_reset(ctx, true);
                        reset_audio_output_buffer(true);
                    }
                    return true;

                case SDL_SCANCODE_F2:
                    if (pressed && event->key.repeat == 0) g_show_menu = !g_show_menu;
                    return true;

                case SDL_SCANCODE_F3:
                    if (pressed && event->key.repeat == 0) {
                        g_render_filter_mode = g_render_filter_mode == GB_RENDER_FILTER_NEAREST
                            ? GB_RENDER_FILTER_LINEAR : GB_RENDER_FILTER_NEAREST;
                        update_render_filter();
                    }
                    return true;

                case SDL_SCANCODE_F4:
                    if (pressed && event->key.repeat == 0) {
                        if (!g_fullscreen) {
                            g_render_scaling_mode = GB_RENDER_SCALING_PIXEL_PERFECT;
                            set_fullscreen_enabled(true);
                        } else if (g_render_scaling_mode == GB_RENDER_SCALING_PIXEL_PERFECT) {
                            g_render_scaling_mode = GB_RENDER_SCALING_ASPECT_FIT;
                            update_game_viewport();
                        } else {
                            set_fullscreen_enabled(false);
                        }
                    }
                    return true;''')
    source = replace_once(source, '''                case GB_INPUT_ACTION_TOGGLE_MENU:
                    g_show_menu = !g_show_menu;
                    break;''', '''                case GB_INPUT_ACTION_TOGGLE_MENU:
                    rr_gb_toggle_menu(3);
                    break;''')
    source = replace_once(source, '''    g_palette_idx = 0;
    g_smooth_lcd_transitions = true;''',
        '''    g_palette_idx = 1;
    g_smooth_lcd_transitions = true;''')
    source = replace_once(source, '''            if (integer_scale < 1) {
                integer_scale = 1;
            }
            viewport_w = GB_SCREEN_WIDTH * integer_scale;''',
        '''            if (integer_scale < 1) integer_scale = 1;
            if (g_render_filter_mode == GB_RENDER_FILTER_SCALE2X && integer_scale >= 2)
                integer_scale -= integer_scale % 2;
            viewport_w = GB_SCREEN_WIDTH * integer_scale;''')
    source = replace_once(source, 'static void render_frame_internal(const uint32_t* framebuffer, bool count_guest_frame) {',
        '#include "gb_menu.inc"\n\nstatic void render_frame_internal(const uint32_t* framebuffer, bool count_guest_frame) {')
    source = replace_once(source, '''    if (g_texture) {
        SDL_SetTextureScaleMode(g_texture,
                                g_render_filter_mode == GB_RENDER_FILTER_LINEAR
                                    ? SDL_ScaleModeLinear
                                    : SDL_ScaleModeNearest);
    }''', '''    if (g_texture) {
        SDL_SetTextureScaleMode(g_texture,
            SDL_ScaleModeNearest);
    }
    if (g_rr_scale2x_texture) SDL_SetTextureScaleMode(g_rr_scale2x_texture, SDL_ScaleModeNearest);''')
    source = replace_once(source, '''    if (g_texture) {
        SDL_DestroyTexture(g_texture);
        g_texture = NULL;
    }

    g_texture = SDL_CreateTexture(''', '''    if (g_texture) {
        SDL_DestroyTexture(g_texture);
        g_texture = NULL;
    }
    rr_xbr_destroy(&g_rr_xbr);
    rr_scanlines_destroy(&g_rr_scanlines);
    if (g_rr_scale2x_texture) {
        SDL_DestroyTexture(g_rr_scale2x_texture);
        g_rr_scale2x_texture = NULL;
    }

    g_texture = SDL_CreateTexture(''')
    source = replace_once(source, '''    update_render_filter();
    g_renderer_reset_pending = false;
    return true;
}''', '''    g_rr_scale2x_texture = SDL_CreateTexture(g_renderer, SDL_PIXELFORMAT_ARGB8888,
        SDL_TEXTUREACCESS_STATIC, GB_SCREEN_WIDTH * 2, GB_SCREEN_HEIGHT * 2);
    if (!g_rr_scale2x_texture) {
        fprintf(stderr, "[SDL] Failed to create Scale2x texture: %s\\n", SDL_GetError());
        return false;
    }
    update_render_filter();
    g_renderer_reset_pending = false;
    return true;
}''')
    source = replace_once(source, '''    copy_display_frame(pixels, pitch, framebuffer, g_palette_idx, g_registered_ctx);

    SDL_UnlockTexture(g_texture);''', '''    copy_display_frame(pixels, pitch, framebuffer, g_palette_idx, g_registered_ctx);
    /* Mode 1 retains its stored ID; reconstruct contours with xBR at 4x. */
    SDL_Texture *rr_xbr_texture = g_render_filter_mode == GB_RENDER_FILTER_LINEAR ?
        rr_xbr_update(g_renderer, &g_rr_xbr, (const uint32_t*)pixels, GB_SCREEN_WIDTH, GB_SCREEN_HEIGHT, pitch / 4) : NULL;
    const bool rr_scale2x_active = g_render_filter_mode == GB_RENDER_FILTER_SCALE2X &&
        g_game_viewport.w >= GB_SCREEN_WIDTH * 2 && g_game_viewport.h >= GB_SCREEN_HEIGHT * 2;
    if (rr_scale2x_active)
        rr_gb_scale2x((const uint32_t*)pixels, pitch / (int)sizeof(uint32_t), g_rr_scale2x_pixels);
    SDL_UnlockTexture(g_texture);
    if (rr_scale2x_active)
        SDL_UpdateTexture(g_rr_scale2x_texture, NULL, g_rr_scale2x_pixels, GB_SCREEN_WIDTH * 2 * 4);''')
    source = replace_once(source, '''    SDL_RenderCopy(g_renderer, g_texture, NULL, &g_game_viewport);

    ImGui_ImplSDLRenderer2_NewFrame();''', '''    SDL_RenderCopy(g_renderer,
        rr_xbr_texture ? rr_xbr_texture : rr_scale2x_active ? g_rr_scale2x_texture : g_texture,
        NULL, &g_game_viewport);
    if (g_render_filter_mode == GB_RENDER_FILTER_SCANLINES)
        rr_scanlines_draw(g_renderer, &g_rr_scanlines, &g_game_viewport, GB_SCREEN_HEIGHT);

    ImGui_ImplSDLRenderer2_NewFrame();''')
    menu_start = '    if (g_show_menu) {\n        const float ui_scale = imgui_io.FontGlobalScale;'
    menu_end = '    } else if (g_show_overlay && !g_fullscreen) {'
    if source.count(menu_start) != 1 or source.count(menu_end) != 1:
        raise ValueError('Game Boy settings panel markers changed upstream')
    start, end = source.index(menu_start), source.index(menu_end)
    source = source[:start] + '    if (g_show_menu) {\n        /* RetroRecomp draws its shared SDL menu after ImGui. */\n' + source[end:]
    source = replace_once(source, '''    ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData());
    g_last_timing.compose_ms''',
        '''    ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData());
    rr_gb_draw_menu();
    if (!g_show_menu) rr_gb_draw_status();
    g_last_timing.compose_ms''')
    source = replace_once(source, '''    update_render_filter();

    // Setup Dear ImGui context''', '''    if (!rr_menu_init(g_renderer)) {
        fprintf(stderr, "[SDL] Failed to initialize RetroRecomp menu\\n");
        SDL_DestroyRenderer(g_renderer);
        SDL_DestroyWindow(g_window);
        SDL_Quit();
        return false;
    }
    update_render_filter();

    // Setup Dear ImGui context''')
    source = disable_imgui_layout_persistence(source)
    source = replace_once(source, '''    if (g_texture) {
        SDL_DestroyTexture(g_texture);
        g_texture = NULL;
    }
    if (g_renderer) {''', '''    rr_feedback_close_screen(g_renderer);
    rr_menu_shutdown();
    if (g_texture) {
        SDL_DestroyTexture(g_texture);
        g_texture = NULL;
    }
    rr_xbr_destroy(&g_rr_xbr);
    rr_scanlines_destroy(&g_rr_scanlines);
    if (g_rr_scale2x_texture) {
        SDL_DestroyTexture(g_rr_scale2x_texture);
        g_rr_scale2x_texture = NULL;
    }
    if (g_renderer) {''')
    source = replace_once(source, '''        case SDL_RENDER_TARGETS_RESET:
        case SDL_RENDER_DEVICE_RESET:
            g_renderer_reset_pending = true;
            recreate_streaming_texture();
            break;''', '''        case SDL_RENDER_TARGETS_RESET:
        case SDL_RENDER_DEVICE_RESET:
            g_renderer_reset_pending = true;
            rr_menu_shutdown();
            rr_menu_init(g_renderer);
            recreate_streaming_texture();
            break;''')
    source = replace_once(source, '''    if (handle_binding_capture_event(event)) {
        return true;
    }

    switch (event->type) {''', '''    rr_options_observe(event);
    if (handle_binding_capture_event(event)) {
        return true;
    }
    if (rr_gb_handle_menu_event(event, ctx)) return true;

    switch (event->type) {''')
    source = replace_once(source, '''            if (event->key.keysym.scancode == SDL_SCANCODE_ESCAPE ||
                event->key.keysym.scancode == SDL_SCANCODE_AC_BACK) {
                cancel_binding_capture();
                return true;
            }
            commit_binding_capture''', '''            const SDL_Scancode key = event->key.keysym.scancode;
            if (key == SDL_SCANCODE_ESCAPE || key == SDL_SCANCODE_AC_BACK ||
                key == SDL_SCANCODE_F1 || key == SDL_SCANCODE_F2) {
                cancel_binding_capture();
                return true;
            }
            if (key == SDL_SCANCODE_P || key == SDL_SCANCODE_RETURN ||
                key == SDL_SCANCODE_KP_ENTER || (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12))
                return true;
            commit_binding_capture''')
    source = replace_once(source, '''    switch (event->type) {
        case SDL_KEYDOWN:
            if (g_binding_capture_device''', '''    switch (event->type) {
        case SDL_KEYDOWN: {
            if (g_binding_capture_device''')
    source = replace_once(source, '''            commit_binding_capture(make_binding(GB_INPUT_BINDING_KEY, event->key.keysym.scancode));
            return true;

        case SDL_CONTROLLERBUTTONDOWN:''', '''            commit_binding_capture(make_binding(GB_INPUT_BINDING_KEY, event->key.keysym.scancode));
            return true;
        }

        case SDL_CONTROLLERBUTTONDOWN:''')
    source = replace_once(source, '''    record_manual_input_state(current_cycles);

    return true;
}

void gb_platform_submit_port_frame(void* user, const GBPortFrame* frame) {''',
        '''    record_manual_input_state(current_cycles);

    return true;
}

bool gb_platform_wait_while_menu(GBContext* ctx) {
    while (g_show_menu && !g_benchmark_mode) {
        if (!gb_platform_poll_events(ctx)) return false;
        const uint32_t* frame = g_last_guest_framebuffer_valid ? g_last_guest_framebuffer :
            (ctx ? gb_get_framebuffer(ctx) : NULL);
        if (frame) gb_platform_present_framebuffer(frame);
        if (g_show_menu) SDL_Delay(16);
    }
    return true;
}

void gb_platform_submit_port_frame(void* user, const GBPortFrame* frame) {''')
    source = replace_once(source, '''    if (input_action_is_pressed(GB_INPUT_ACTION_START)) g_manual_joypad_buttons &= (uint8_t)~0x08;
}''', '''    if (input_action_is_pressed(GB_INPUT_ACTION_START)) g_manual_joypad_buttons &= (uint8_t)~0x08;
    for (int i = 0; i < 2; ++i) {
        const bool down = (g_manual_joypad_buttons & (1u << i)) == 0;
        if (!rr_autofire(&g_rr_fire[i], down, g_rr_autofire, g_rr_input_frame))
            g_manual_joypad_buttons |= (uint8_t)(1u << i);
    }
}''')
    source = replace_once(source, '    uint64_t current_cycles = ctx ? ctx->total_cycles : 0;',
        '    uint64_t current_cycles = ctx ? ctx->total_cycles : 0;\n    g_rr_input_frame = current_cycles / 70224ULL;')
    source = replace_once(source, '''    update_effective_joypad_state();
    record_manual_input_state(current_cycles);''', '''    const uint8_t previous_dpad = g_joypad_dpad;
    const uint8_t previous_buttons = g_joypad_buttons;
    update_effective_joypad_state();
    if (ctx && input_transition_creates_press(previous_dpad, previous_buttons,
                                              g_joypad_dpad, g_joypad_buttons,
                                              dpad_selected, buttons_selected))
        request_joypad_interrupt(ctx);
    record_manual_input_state(current_cycles);''')
    source = source.replace('    load_runtime_preferences();', '    load_runtime_preferences();\n    rr_options_init(L"GameBoy");\n    rr_gb_shared_language(false);')
    source = replace_once(source, '    record_manual_input_state(current_cycles);',
        '    if (rr_options_quit(g_show_menu ? g_rr_menu_kind : 0)) return false;\n'
        '    if (rr_options_restart(g_show_menu ? g_rr_menu_kind : 0) && ctx) {\n'
        '        gb_context_reset(ctx, true); reset_audio_output_buffer(true);\n'
        '        g_show_menu = false; g_rr_menu_kind = 0;\n'
        '    }\n'
        '    record_manual_input_state(current_cycles);')
    runtime.write_text(source, encoding="utf-8")

    platform_header = project / 'runtime/include/platform_sdl.h'
    source = platform_header.read_text(encoding='utf-8')
    source = replace_once(source, 'bool gb_platform_poll_events(GBContext* ctx);',
        'bool gb_platform_poll_events(GBContext* ctx);\n'
        'bool gb_platform_wait_while_menu(GBContext* ctx);')
    platform_header.write_text(source, encoding='utf-8')
