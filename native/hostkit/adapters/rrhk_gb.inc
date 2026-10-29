/* Game Boy adapter: the machine contract of the host kit over the platform layer of the pinned gb-recompiled runtime.
 * Original RetroRecomp code: MIT, like the runtime it is built into (arcanite24/gb-recompiled, MIT). This file is included
 * by the patched runtime/src/platform_sdl.cpp (retrorecomp/gameboy_host.py), after the pieces of the upstream platform that
 * stay (input scripts and recording, screenshots, persistence, display palette): its window, menus, bindings, controller
 * handling, sound device and pacing are the kit's. The loop belongs to the generated main: it calls gb_platform_poll_events
 * once per slice, gb_platform_render_frame (or the partial-slice presents) and gb_platform_vsync once per frame. The kit's
 * frame function is called from gb_platform_vsync (driven mode, docs/HOST_KIT.md): it presents the picture, plays the
 * sound of the frame, handles the events, the menus and the quick states, and paces. A menu is a loop inside that call, so
 * the guest does not run meanwhile. Not a general kit file: it sees the runtime's statics and types. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include "platform_io.h"
#include "embedded_resources.h"

/* ---- the controls ---- */
/* The pad word given to the machine: the JOYP direction nibble (right, left, up, down) then the button nibble (A, B,
 * Select, Start), in positive logic; the runtime's registers are active low. */
enum { RR_GB_UP, RR_GB_DOWN, RR_GB_LEFT, RR_GB_RIGHT, RR_GB_A, RR_GB_B, RR_GB_START, RR_GB_SELECT, RR_GB_PAUSE, RR_GB_ACTIONS };
static const RrhkAction rr_gb_actions[RR_GB_ACTIONS] = {
    {"Up", L"Up", 0x04, RRHK_DIR, 0, {SDL_SCANCODE_UP}, {SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", 0x08, RRHK_DIR, 0, {SDL_SCANCODE_DOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", 0x02, RRHK_DIR, 0, {SDL_SCANCODE_LEFT}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", 0x01, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
    /* W and X follow the keyboard layout; the controller's east and south buttons are A and B, as on the console. */
    {"Button A", L"A", 0x10, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W}, {SDL_CONTROLLER_BUTTON_B}},
    {"Button B", L"B", 0x20, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X}, {SDL_CONTROLLER_BUTTON_A}},
    {"Start", L"Start", 0x80, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN}, {SDL_CONTROLLER_BUTTON_START}},
    {"Select", L"Select", 0x40, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT}, {SDL_CONTROLLER_BUTTON_BACK}},
    /* The Pause menu is the host's own row: it has no bit, the cartridge never sees it. */
    {"Pause/Menu", L"Pause", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_P}, {SDL_CONTROLLER_BUTTON_GUIDE}},
};

/* ---- the machine's state ---- */
static RrhkMachine rr_gb_machine;
static uint32_t g_rr_view[GB_SCREEN_WIDTH * GB_SCREEN_HEIGHT];   /* the picture of the last frame, at the origin of the kit's texture */
static bool g_rr_stop;                  /* the kit asked to stop (quit): the next poll of events says so */
static uint64_t g_rr_sample_time;       /* last mid-frame sample of the pads */
static std::vector<int16_t> g_rr_pcm;   /* interleaved stereo produced since the kit last took the sound */
enum { RR_GB_PCM_LIMIT_FRAMES = 16384 };

/* ---- the former preferences (datas/Retro-Recomp-GameBoy.ini of 1.6.2 and before), read where the kit's keys are absent ---- */
static const char *const rr_gb_old_names[RR_GB_ACTIONS] = {"up", "down", "left", "right", "a", "b", "start", "select", nullptr};

static std::string rr_gb_old_file(const RrhkUi *ui) {
    static wchar_t wide[32768];
    char narrow[32768 * 2];
    rr_wide_copy(wide, 32768, ui->data_dir);
    rr_wide_append(wide, 32768, RR_SLASH_W L"Retro-Recomp-GameBoy.ini");
    return rr_to_utf8(wide, narrow, sizeof narrow) ? std::string(narrow) : std::string();
}

static void rr_gb_read_old(RrhkUi *ui, int *palette) {
    const std::string path = rr_gb_old_file(ui);
    FILE *file = path.empty() ? NULL : fopen(path.c_str(), "r");
    if (!file) return;
    char line[256];
    while (fgets(line, sizeof line, file)) {
        char *text = trim_ascii(line);
        char *equals = text ? strchr(text, '=') : NULL;
        if (!equals || text[0] == '#') continue;
        *equals = '\0';
        const char *key = trim_ascii(text), *value = trim_ascii(equals + 1);
        if (!strcmp(key, "video.filter")) { int v = atoi(value); if (v >= 0 && v < 4) ui->filter = v; }
        else if (!strcmp(key, "video.display_mode")) { int v = atoi(value); if (v >= 0 && v < 3) ui->fullscreen = v; }
        else if (!strcmp(key, "video.palette")) *palette = !strcmp(value, "green") ? 0 : 1;
        else if (!strcmp(key, "ui.language")) { ui->language = rr_language_from_code(value); }
        else if (!strcmp(key, "input.autofire")) ui->autofire = !strcmp(value, "1");
        else if (!strncmp(key, "keyboard.", 9) || !strncmp(key, "controller.", 11)) {
            /* keyboard.<action>.<slot>=key:<scancode> | controller.<action>.<slot>=button:<button>; the first slot only */
            const bool pad = key[0] == 'c';
            const char *name = key + (pad ? 11 : 9), *dot = strrchr(name, '.');
            if (!dot || strcmp(dot, ".0")) continue;
            for (int a = 0; a < RR_GB_PAUSE; ++a) {
                if (strlen(rr_gb_old_names[a]) != (size_t)(dot - name) || strncmp(name, rr_gb_old_names[a], (size_t)(dot - name))) continue;
                if (!strcmp(value, "none")) { if (pad) ui->buttons[0][a] = (SDL_GameControllerButton)-1; else ui->keys[0][a] = SDL_SCANCODE_UNKNOWN; }
                else if (!pad && !strncmp(value, "key:", 4)) {
                    long code = strtol(value + 4, NULL, 10);
                    if (code > SDL_SCANCODE_UNKNOWN && code < SDL_NUM_SCANCODES) ui->keys[0][a] = (SDL_Scancode)code;
                } else if (pad && !strncmp(value, "button:", 7)) {
                    long code = strtol(value + 7, NULL, 10);
                    if (code >= 0 && code < SDL_CONTROLLER_BUTTON_MAX) ui->buttons[0][a] = (SDL_GameControllerButton)code;
                }
            }
        }
    }
    fclose(file);
}

static void rr_gb_settings_loaded(RrhkUi *ui) {
    int palette = 1;                    /* DMG monochrome is the RetroRecomp default */
    rr_gb_read_old(ui, &palette);
    /* The kit read its own display keys before this call: the former file only replaces what the kit's file lacks. */
    int filter = rr_ini_int(ui->video_section, L"filter", ui->filter, ui->read_file);
    int mode = rr_ini_int(ui->video_section, L"display_mode", ui->fullscreen, ui->read_file);
    ui->filter = filter >= 0 && filter < 4 ? filter : 0;
    ui->fullscreen = mode >= 0 && mode < 3 ? mode : 0;
    g_palette_idx = (int)rr_ini_int(L"GameBoy.Video", L"palette", palette, ui->read_file) == 0 ? 0 : 1;
}

/* ---- the pads: the kit's pad word, then the runtime's active-low registers ---- */
static bool rr_gb_press_created(uint8_t previous_dpad, uint8_t previous_buttons, uint8_t next_dpad, uint8_t next_buttons,
                                bool dpad_selected, bool buttons_selected) {
    return (dpad_selected && (previous_dpad & ~next_dpad)) || (buttons_selected && (previous_buttons & ~next_buttons));
}

static void rr_gb_apply_pad(GBContext *ctx, uint16_t word) {
    g_manual_joypad_dpad = (uint8_t)(0xFF & ~(word & 0x0F));
    g_manual_joypad_buttons = (uint8_t)(0xFF & ~((word >> 4) & 0x0F));
    const uint8_t previous_dpad = g_joypad_dpad, previous_buttons = g_joypad_buttons;
    update_effective_joypad_state();
    const uint8_t joyp = ctx ? ctx->io[0x00] : 0xFF;
    if (ctx && rr_gb_press_created(previous_dpad, previous_buttons, g_joypad_dpad, g_joypad_buttons, !(joyp & 0x10), !(joyp & 0x20)))
        request_joypad_interrupt(ctx);
    record_manual_input_state(ctx ? ctx->total_cycles : 0);
}

static uint64_t rr_gb_input_frame(void) { return g_registered_ctx ? g_registered_ctx->total_cycles / 70224ULL : 0; }

/* Live input, on the CPU/main thread only: after every slice and when a cartridge reads JOYP, at most once a millisecond. System
 * actions stay in the frame's event loop: a JOYP read must never reset or load the machine in the middle of an opcode. */
static void rr_gb_sample_input(GBContext *ctx, bool force) {
    if (g_benchmark_mode || g_script_count || !rrhk_window() || rrhk_ui()->menu || rrhk_ui()->paused) return;
    const uint64_t now = SDL_GetPerformanceCounter(), frequency = SDL_GetPerformanceFrequency();
    const uint64_t interval = frequency / 1000u ? frequency / 1000u : 1u;
    if (!force && g_rr_sample_time && now - g_rr_sample_time < interval) return;
    SDL_PumpEvents();
    g_rr_sample_time = now;
    rr_gb_apply_pad(ctx, rrhk_pad_word(0, rr_gb_input_frame()));
}

static void rr_gb_refresh_joyp(GBContext *ctx) { rr_gb_sample_input(ctx, false); }

/* ---- the machine ---- */
static int rr_gb_players(void) { return 1; }
static const uint32_t *rr_gb_pixels(void) { return g_rr_view; }
static int rr_gb_width(void) { return GB_SCREEN_WIDTH; }
static int rr_gb_height(void) { return GB_SCREEN_HEIGHT; }

/* One frame of the machine is the guest running after the call returns: the kit only hands the pad over. */
static bool rr_gb_run_frame(uint16_t p1, uint16_t p2) {
    (void)p2;
    rr_gb_apply_pad(g_registered_ctx, p1);
    g_rr_sample_time = SDL_GetPerformanceCounter();
    return true;
}

static void rr_gb_reset(void) {
    if (g_registered_ctx) gb_context_reset(g_registered_ctx, true);
    g_rr_pcm.clear();
}
static void rr_gb_pause(bool paused) { (void)paused; }

/* The sound of the frame: the samples the APU produced, 44.1 kHz stereo; `capacity` counts int16 values, the result frames. */
static size_t rr_gb_audio(int16_t *pcm, size_t capacity) {
    size_t frames = g_rr_pcm.size() / 2;
    if (frames > capacity / 2) frames = capacity / 2;
    memcpy(pcm, g_rr_pcm.data(), frames * 2 * sizeof(int16_t));
    g_rr_pcm.erase(g_rr_pcm.begin(), g_rr_pcm.begin() + (ptrdiff_t)(frames * 2));
    return frames;
}
static bool rr_gb_audio_enable(unsigned rate) { (void)rate; return true; }

static uint64_t rr_gb_interpreted(void) { return has_interpreter_activity(g_registered_ctx) ? 1 : 0; }
static uint64_t rr_gb_no_count(void) { return 0; }

/* A quick state is taken between two frames (decision D6): the frame function of the kit runs after a completed frame. The
 * state is the runtime's own file of slot 1, under the game's folder of datas, as before the kit. */
static bool rr_gb_state_ready(void) { return g_registered_ctx && g_registered_ctx->frame_done; }
static bool rr_gb_state_file(const wchar_t *path, bool load) {
    (void)path;
    const bool done = load ? load_savestate_slot(g_registered_ctx, 0) : save_savestate_slot(g_registered_ctx, 0);
    if (done && load) { g_rr_pcm.clear(); rrhk_autofire_reset(); }
    return done;
}

/* ---- the palette (F5): the Game Boy's own option ---- */
static bool rr_gb_color_game(void) { return g_registered_ctx && g_registered_ctx->config.model == GB_MODEL_CGB; }

static bool rr_gb_key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    (void)running;
    if (key != SDL_SCANCODE_F5) return false;
    if (rr_gb_color_game()) { rrhk_notice(rrhk_tr("Game Boy Color: game palette", "Game Boy Color : couleurs du jeu"), 1800); return true; }
    const int next = g_palette_idx == 1 ? 0 : 1;
    if (rrhk_write_ready() && rr_display_save(ui->ini_file, ui->data_dir, L"GameBoy.Video", L"palette", next)) {
        g_palette_idx = next;
        rrhk_notice(next == 1 ? rrhk_tr("Display: monochrome", "Affichage : monochrome") :
                                rrhk_tr("Display: classic green", "Affichage : vert classique"), 1800);
    } else rrhk_notice(rrhk_tr("Config unavailable", "Config inaccessible"), 1800);
    return true;
}

static void rr_gb_option_rows(int slot, RrhkOptionRows *rows) {
    if (slot == 0 && !rr_gb_color_game())
        rrhk_option_row(rows, SDL_SCANCODE_F5, "F5 Palette: %s", rr_tr(g_palette_idx == 1 ? "Monochrome" : "Classic green"));
}

static void rr_gb_help_lines(int slot, const char **lines, int *count) {
    if (slot == 0) lines[(*count)++] = rrhk_tr("F5  Monochrome / classic green", "F5  Monochrome / vert classique");
    else lines[(*count)++] = rrhk_tr("P  Pause | Enter  Start", "P  Pause | Entree  Start");
}

static void rr_gb_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Gamepad menu: Guide button", "Menu manette : bouton Guide"));
}

static void rr_gb_pause_page(RrhkUi *ui, const RrhkMenuCtx *ctx) {
    (void)ui;
    const int ox = ctx->ox, oy = ctx->oy, unit = ctx->unit;
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 62, rrhk_tr("Game paused", "Jeu en pause"), RR_MENU_GOLD);
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 90, rrhk_tr("P: resume", "P : reprendre"), RR_MENU_GOLD);
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 118, rrhk_tr("Shift+F1: restart", "Maj+F1 : redemarrer"), RR_MENU_HINT);
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 140, rrhk_tr("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), RR_MENU_HINT);
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 152, has_interpreter_activity(g_registered_ctx) ?
        rrhk_tr("Interpreter fallback used", "Secours interprete utilise") : rrhk_tr("Native code", "Code natif"), RR_MENU_ACCENT);
    rr_menu_text(ctx->renderer, ox, oy, unit, 14, 164, rrhk_tr("F1: help | F2: controls & options", "F1 : aide | F2 : commandes et options"), RR_MENU_HINT);
}

static const RrhkMachine *rr_gb_adapter(void) {
    if (!rr_gb_machine.actions) {
        rr_gb_machine.ini_section = L"GameBoy";
        rr_gb_machine.console_name = "Game Boy";
        rr_gb_machine.table_players = 1;
        rr_gb_machine.players = rr_gb_players;
        rr_gb_machine.actions = rr_gb_actions;
        rr_gb_machine.action_count = RR_GB_ACTIONS;
        rr_gb_machine.up = RR_GB_UP; rr_gb_machine.down = RR_GB_DOWN; rr_gb_machine.left = RR_GB_LEFT; rr_gb_machine.right = RR_GB_RIGHT;
        rr_gb_machine.start = RR_GB_START;
        rr_gb_machine.max_width = GB_SCREEN_WIDTH; rr_gb_machine.max_height = GB_SCREEN_HEIGHT;
        rr_gb_machine.frame_seconds = 70224.0 / 4194304.0;
        rr_gb_machine.audio_model = RRHK_AUDIO_RING;
        rr_gb_machine.audio_rate = 44100u; rr_gb_machine.audio_channels = 2; rr_gb_machine.audio_margin_ms = 10;
        rr_gb_machine.audio_enable = rr_gb_audio_enable;
        rr_gb_machine.save_failed_en = "Unable to save quick state"; rr_gb_machine.save_failed_fr = "Impossible de sauvegarder";
        rr_gb_machine.driven = true;
        rr_gb_machine.host_pause = RR_GB_PAUSE + 1;
        rr_gb_machine.minimum_window = true;
        rr_gb_machine.even_scale2x = true;
        rr_gb_machine.reset = rr_gb_reset;
        rr_gb_machine.run_frame = rr_gb_run_frame;
        rr_gb_machine.pause = rr_gb_pause;
        rr_gb_machine.pixels = rr_gb_pixels;
        rr_gb_machine.visible_width = rr_gb_width; rr_gb_machine.visible_height = rr_gb_height;
        rr_gb_machine.raster_height = rr_gb_height; rr_gb_machine.display_width = rr_gb_width;
        rr_gb_machine.audio = rr_gb_audio;
        rr_gb_machine.interpreted = rr_gb_interpreted; rr_gb_machine.audio_interpreted = rr_gb_no_count;
        rr_gb_machine.state_ready = rr_gb_state_ready; rr_gb_machine.state_file = rr_gb_state_file;
        rr_gb_machine.input_frame = rr_gb_input_frame;
        rr_gb_machine.settings_loaded = rr_gb_settings_loaded;
        rr_gb_machine.option_rows = rr_gb_option_rows; rr_gb_machine.help_lines = rr_gb_help_lines;
        rr_gb_machine.help_controls = rr_gb_help_controls; rr_gb_machine.key_event = rr_gb_key_event;
        rr_gb_machine.pause_page = rr_gb_pause_page;
    }
    return &rr_gb_machine;
}
const RrhkMachine *rrhk_adapter(void) { return rr_gb_adapter(); }

/* The sound the APU produces goes to the kit while a window is open (never in the headless runs). */
static void on_audio_sample(GBContext *ctx, int16_t left, int16_t right) {
    (void)ctx;
    if (g_benchmark_mode || !rrhk_window() || g_rr_pcm.size() >= (size_t)RR_GB_PCM_LIMIT_FRAMES * 2) return;
    g_rr_pcm.push_back(left);
    g_rr_pcm.push_back(right);
}

/* ---- the entry points of the generated main (platform_sdl.h) ---- */
static void render_frame_internal(const uint32_t* framebuffer, bool count_guest_frame) {
    if (!framebuffer) return;
    g_present_count++;
    if (count_guest_frame) {
        g_frame_count++;
        memcpy(g_last_guest_framebuffer, framebuffer, sizeof(g_last_guest_framebuffer));
        g_last_guest_framebuffer_valid = true;
        /* Screenshots of the selected guest frames. */
        if (frame_is_selected_for_dump(g_dump_frames, g_dump_count, (uint32_t)g_frame_count)) {
            char suffix[32];
            snprintf(suffix, sizeof(suffix), "_%05d.ppm", g_frame_count);
            const std::string filename = g_screenshot_prefix + suffix;
            save_ppm(filename.c_str(), framebuffer, GB_SCREEN_WIDTH, GB_SCREEN_HEIGHT, g_frame_count);
        }
    }
    if (frame_is_selected_for_dump(g_dump_present_frames, g_dump_present_count, (uint32_t)g_frame_count)) {
        char suffix[80];
        snprintf(suffix, sizeof(suffix), "_guest_%05d_present_%06llu.ppm", g_frame_count, (unsigned long long)g_present_count);
        const std::string filename = g_screenshot_prefix + suffix;
        save_ppm(filename.c_str(), framebuffer, GB_SCREEN_WIDTH, GB_SCREEN_HEIGHT, g_frame_count);
    }
    g_last_timing.upload_ms = g_last_timing.compose_ms = g_last_timing.present_ms = g_last_timing.total_render_ms = 0.0;
    /* The kit presents the picture, with its filter, at the end of the frame (gb_platform_vsync). */
    if (g_benchmark_mode || !rrhk_window()) return;
    copy_display_frame(g_rr_view, GB_SCREEN_WIDTH * (int)sizeof(uint32_t), framebuffer, g_palette_idx, g_registered_ctx);
}

bool gb_platform_init(int scale) {
    g_benchmark_mode = g_benchmark_mode || env_flag_enabled("GBRECOMP_BENCHMARK");
    g_exit_action = GB_PLATFORM_EXIT_QUIT;
    g_frame_count = 0;
    g_manual_joypad_buttons = 0xFF;
    g_manual_joypad_dpad = 0xFF;
    g_script_joypad_buttons = 0xFF;
    g_script_joypad_dpad = 0xFF;
    update_effective_joypad_state();
    g_last_guest_framebuffer_valid = false;
    g_present_count = 0;
    g_last_timing = {};
    g_rr_stop = false;
    g_rr_sample_time = 0;
    g_rr_pcm.clear();
    if (g_benchmark_mode) {
        if (!SDL_getenv("SDL_VIDEODRIVER")) SDL_setenv("SDL_VIDEODRIVER", "dummy", 0);
        if (!SDL_getenv("SDL_AUDIODRIVER")) SDL_setenv("SDL_AUDIODRIVER", "dummy", 0);
        if (SDL_Init(SDL_INIT_TIMER) < 0) {
            fprintf(stderr, "[SDL] SDL_Init failed in benchmark mode: %s\n", SDL_GetError());
            return false;
        }
        return true;
    }
    return rrhk_open(rr_gb_adapter(), g_rr_game_title, scale);
}

void gb_platform_shutdown(void) {
    close_input_record_file();
    rrhk_close();
    g_rr_pcm.clear();
    g_port_frame = {};
    g_port_frame_valid = false;
    g_registered_ctx = NULL;
    SDL_Quit();
}

void gb_platform_set_benchmark_mode(bool enabled) { g_benchmark_mode = enabled; }
void gb_platform_set_launcher_return_enabled(bool enabled) { g_launcher_return_enabled = enabled; }
GBPlatformExitAction gb_platform_get_exit_action(void) { return g_exit_action; }

/* Events belong to the kit: it reads them between two frames, in gb_platform_vsync. What is read here is the scripted input
 * (headless probes and replays) and the live pads, once per slice. A quit the kit saw at the last frame ends the loop. */
bool gb_platform_poll_events(GBContext* ctx) {
    if (g_rr_stop) return false;

    /* Handle Automation Inputs */
    uint8_t previous_script_dpad = g_script_joypad_dpad;
    uint8_t previous_script_buttons = g_script_joypad_buttons;
    g_script_joypad_dpad = 0xFF;
    g_script_joypad_buttons = 0xFF;

    uint64_t current_cycles = ctx ? ctx->total_cycles : 0;
    for (int i = 0; i < g_script_count; i++) {
        ScriptEntry* e = &g_input_script[i];
        bool active = false;
        if (e->anchor == SCRIPT_ANCHOR_CYCLE) {
            if (e->period > 0) {
                active = current_cycles >= e->start &&
                         current_cycles < (e->end + e->duration) &&
                         ((current_cycles - e->start) % e->period) < e->duration;
            } else {
                active = current_cycles >= e->start &&
                         current_cycles < (e->start + e->duration);
            }
        } else {
            uint64_t current_frame = (uint64_t)g_frame_count;
            active = current_frame >= e->start &&
                     current_frame < (e->start + e->duration);
        }
        if (active) {
            g_script_joypad_dpad &= e->dpad;
            g_script_joypad_buttons &= e->buttons;
        }
    }

    uint8_t new_script_dpad = (uint8_t)(previous_script_dpad & (uint8_t)(~g_script_joypad_dpad) & 0x0F);
    uint8_t new_script_buttons = (uint8_t)(previous_script_buttons & (uint8_t)(~g_script_joypad_buttons) & 0x0F);
    uint8_t joyp = ctx ? ctx->io[0x00] : 0xFF;
    bool dpad_selected = !(joyp & 0x10);
    bool buttons_selected = !(joyp & 0x20);
    if (ctx && ((new_script_dpad && dpad_selected) || (new_script_buttons && buttons_selected))) {
        request_joypad_interrupt(ctx);
    }

    rr_gb_sample_input(ctx, true);
    update_effective_joypad_state();
    record_manual_input_state(current_cycles);

    return true;
}

/* Called before every slice of the generated loop: the kit already decided at the last frame whether the game goes on. */
bool gb_platform_wait_while_menu(GBContext* ctx) {
    (void)ctx;
    return !g_rr_stop;
}

void gb_platform_submit_port_frame(void* user, const GBPortFrame* frame) {
    (void)user;
    if (frame == NULL || frame->abi_version != GB_PORT_ABI_VERSION ||
        frame->command_count > GB_PORT_MAX_DRAW_COMMANDS) {
        g_port_frame = {};
        g_port_frame_valid = false;
        return;
    }
    g_port_frame = *frame;
    g_port_frame_valid = true;
}

void gb_platform_render_frame(const uint32_t* framebuffer) {
    render_frame_internal(framebuffer, true);
}

void gb_platform_present_framebuffer(const uint32_t* framebuffer) {
    const uint32_t* stable_framebuffer = g_last_guest_framebuffer_valid ? g_last_guest_framebuffer : framebuffer;
    render_frame_internal(stable_framebuffer, false);
}

void gb_platform_render_lcd_off_frame(void) {
    ensure_lcd_off_framebuffer();
    const uint32_t* stable_framebuffer = g_last_guest_framebuffer_valid ? g_last_guest_framebuffer : g_lcd_off_framebuffer;
    render_frame_internal(stable_framebuffer, false);
}

void gb_platform_get_timing_info(GBPlatformTimingInfo* out) {
    if (!out) return;
    *out = g_last_timing;
}

uint8_t gb_platform_get_joypad(void) {
    /* Return combined state based on P1 register selection */
    /* Caller should AND with the appropriate selection bits */
    return g_joypad_buttons & g_joypad_dpad;
}

/* The end of a frame, or of a slice of the frame the generated loop presented: the kit shows the picture, plays the sound,
 * reads the events and the menus and waits for the deadline of the cycles that were just run. */
void gb_platform_vsync(uint32_t frame_cycles) {
    const uint32_t cycles = frame_cycles > 0 ? frame_cycles : 70224u;
    g_last_timing.pacing_cycles = cycles;
    g_last_timing.pacing_ms = 0.0;
    if (g_benchmark_mode || !rrhk_window()) return;
    rr_gb_machine.frame_seconds = (double)cycles / 4194304.0;
    if (!rrhk_frame_done()) g_rr_stop = true;
}

bool gb_platform_get_smooth_lcd_transitions(void) { return g_smooth_lcd_transitions; }
void gb_platform_set_smooth_lcd_transitions(bool enabled) { g_smooth_lcd_transitions = enabled; }

void gb_platform_set_title(const char* title) {
    if (rrhk_window() && !g_benchmark_mode) SDL_SetWindowTitle(rrhk_window(), title);
}
