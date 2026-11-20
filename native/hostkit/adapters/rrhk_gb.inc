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
    {"Button A", L"A", 0x10, RRHK_FACE, 0, {SDL_SCANCODE_S}, {SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_w},
    {"Button B", L"B", 0x20, RRHK_FACE, 0, {SDL_SCANCODE_D}, {SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_x},
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
static std::vector<uint8_t> g_rr_pristine;       /* the state at the first slice of the game, taken in a session only: a session starts every seat from it */
static bool g_rr_pristine_tried;
static std::vector<uint8_t> g_rr_session_image;  /* the match's cartridge RAM: the host's own (session_save), or the host's given to a guest (session_save_put) */
static bool g_rr_effects = true;        /* false: nothing is written outside the machine (a guest's session, a silent frame): the cartridge RAM and the clock stay in memory */
/* The link cable (native/gb_link.h in the runtime): the consoles of a match, all run by this PC. Console 0 is the guest's own context (the kit's registered
 * one, its pads are the globals of the platform); the satellites 1.. read the registers below through their `joypad` pointer. */
enum { RR_GB_LINK_SLOTS = 4 };
static GBJoypadState g_rr_link_pad[RR_GB_LINK_SLOTS];    /* the satellites' pad registers (active low), from the seats' pad words */
static int g_rr_link_view;                               /* the console this PC shows and hears: its own seat's */
static std::vector<ScriptEntry> g_rr_link_script;        /* headless tests only: the second console's input script (RETRO_RECOMP_GB_LINK_SCRIPT) */
static bool g_rr_link_headless_tried;
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
        /* The upstream shell's sound settings, which the kit offers to every console (decision D12): the volume (0..200),
         * the mute and the output device by name. */
        else if (!strcmp(key, "audio.muted")) ui->audio_muted = strcmp(value, "0") != 0;
        else if (!strcmp(key, "audio.volume_percent")) { long v = strtol(value, NULL, 10); if (v >= 0 && v <= 200) ui->audio_volume = (int)v; }
        else if (!strcmp(key, "audio.device_name")) snprintf(ui->audio_device, sizeof ui->audio_device, "%s", value);
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
static void rr_gb_link_apply_pad(int index, uint16_t word);
static bool rr_gb_run_frame(uint16_t p1, uint16_t p2) {
    rr_gb_apply_pad(g_registered_ctx, p1);
    if (gb_link_count() > 1) rr_gb_link_apply_pad(1, p2);        /* seat 1's pad drives the second console of a link */
    g_rr_sample_time = SDL_GetPerformanceCounter();
    return true;
}

static void rr_gb_reset(void) {
    if (g_registered_ctx) gb_context_reset(g_registered_ctx, true);
    for (int i = 1; i < gb_link_count(); ++i) gb_context_reset(gb_link_context(i), true);
    g_rr_pcm.clear();
    rrhk_autofire_reset();
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

/* ---- multiplayer (hostkit_session.h): the machine's snapshot and digest ----
 * The runtime part (native/gb_machine_state.h, in gbrt.c) holds the context, the memory blocks and the video and sound units. What lives in
 * the platform layer and decides the next frames is added here: the pad registers the cartridge reads through JOYP (the manual and the
 * effective ones, and the scripted ones, which stay released in a session). The runtime's last_joypad is in its own part. Host-only things
 * (the window, the sound ring, the filters, the palette, the timers of the shell) are not in it. */
typedef struct RrGbPadState {
    uint8_t manual_dpad, manual_buttons, script_dpad, script_buttons, dpad, buttons;
    uint8_t reserved[10];
} RrGbPadState;

/* One console's snapshot: the runtime's part, then its pad registers. Console 0 keeps its registers in the platform's globals, a satellite in its own. */
static GBContext *rr_gb_console(int index) { return index == 0 ? g_registered_ctx : gb_link_context(index); }

static size_t rr_gb_one_bound(void) {
    const size_t machine = rr_gb_snap_bound(g_registered_ctx);
    return machine ? machine + sizeof(RrGbPadState) : 0;
}

static size_t rr_gb_one_save(int index, void *buffer, size_t capacity) {
    const size_t bound = rr_gb_one_bound();
    GBContext *ctx = rr_gb_console(index);
    if (!bound || !ctx || !buffer || capacity < bound) return 0;
    const size_t machine = rr_gb_snap_save(ctx, buffer, bound - sizeof(RrGbPadState));
    if (!machine || machine + sizeof(RrGbPadState) != bound) return 0;
    RrGbPadState pads;
    memset(&pads, 0, sizeof pads);
    if (index == 0) {
        pads.manual_dpad = g_manual_joypad_dpad; pads.manual_buttons = g_manual_joypad_buttons;
        pads.script_dpad = g_script_joypad_dpad; pads.script_buttons = g_script_joypad_buttons;
        pads.dpad = g_joypad_dpad; pads.buttons = g_joypad_buttons;
    } else {
        pads.manual_dpad = pads.dpad = g_rr_link_pad[index].dpad; pads.manual_buttons = pads.buttons = g_rr_link_pad[index].buttons;
        pads.script_dpad = pads.script_buttons = 0xFF;
    }
    memcpy((uint8_t *)buffer + machine, &pads, sizeof pads);
    return bound;
}

static bool rr_gb_one_load(int index, const void *buffer, size_t size) {
    const size_t bound = rr_gb_one_bound();
    GBContext *ctx = rr_gb_console(index);
    if (!bound || !ctx || !buffer || size != bound) return false;
    if (!rr_gb_snap_load(ctx, buffer, bound - sizeof(RrGbPadState))) return false;
    RrGbPadState pads;
    memcpy(&pads, (const uint8_t *)buffer + (bound - sizeof(RrGbPadState)), sizeof pads);
    if (index == 0) {
        g_manual_joypad_dpad = pads.manual_dpad; g_manual_joypad_buttons = pads.manual_buttons;
        g_script_joypad_dpad = pads.script_dpad; g_script_joypad_buttons = pads.script_buttons;
        g_joypad_dpad = pads.dpad; g_joypad_buttons = pads.buttons;
    } else {
        g_rr_link_pad[index].dpad = pads.dpad; g_rr_link_pad[index].buttons = pads.buttons;
    }
    return true;
}

/* The match's snapshot: every console's, in seat order (console 0 first), each at the size of one. The consoles of a match are known at SETUP
 * (rrhk_session_ports, or the link of a headless test); until then, and for a match with no link, it is the size of one console. */
static int rr_gb_link_consoles_planned(void);
static size_t rr_gb_snap_bound_adapter(void) {
    const size_t one = rr_gb_one_bound();
    return one ? one * (size_t)rr_gb_link_consoles_planned() : 0;
}

static size_t rr_gb_snap_save_adapter(void *buffer, size_t capacity) {
    const size_t one = rr_gb_one_bound(), bound = rr_gb_snap_bound_adapter();
    if (!bound || !buffer || capacity < bound) return 0;
    for (size_t i = 0; i < bound / one; ++i)
        if (rr_gb_one_save((int)i, (uint8_t *)buffer + i * one, one) != one) return 0;
    return bound;
}

static bool rr_gb_snap_load_adapter(const void *buffer, size_t size) {
    const size_t one = rr_gb_one_bound(), bound = rr_gb_snap_bound_adapter();
    if (!bound || !buffer || size != bound) return false;
    for (size_t i = 0; i < bound / one; ++i)
        if (!rr_gb_one_load((int)i, (const uint8_t *)buffer + i * one, one)) return false;
    g_rr_pcm.clear();            /* the sound of the frames that are run again is discarded */
    return true;
}

/* ---- the link cable: this PC runs every console of the match ----
 * A match whose seats each have their own port (rrhk_session_ports() of 2 or more, which the lobby gives a Game Boy game on the link cable) is two
 * consoles on one cable, run here by the runtime's gb_link (native/gb_link.h): console i is driven by seat i's pad word, and this PC shows and plays its own
 * seat's console. A headless run can start a link on its own for the tests: RETRO_RECOMP_GB_LINK=2 (consoles), RETRO_RECOMP_GB_LINK_VIEW=n (the console shown),
 * RETRO_RECOMP_GB_LINK_SCRIPT=<input script of the second console, the format of --input-script>. Never read by a window that is open. */
static bool rr_gb_link_headless(void) { return g_benchmark_mode || !rrhk_window(); }

static int rr_gb_link_consoles_wanted(void) {
    if (rrhk_session_active()) {
        const int ports = rrhk_session_ports();
        return ports >= 2 ? 2 : 0;                  /* two consoles at most: the four-player adapter is not modelled */
    }
    if (rr_gb_link_headless()) {
        const char *value = SDL_getenv("RETRO_RECOMP_GB_LINK");
        const int consoles = value ? atoi(value) : 0;
        return consoles >= 2 ? 2 : 0;
    }
    return 0;
}

static int rr_gb_link_consoles_planned(void) {
    const int started = gb_link_count();
    if (started > 1) return started;
    const int wanted = rr_gb_link_consoles_wanted();
    return wanted > 1 ? wanted : 1;
}

/* Joypad of a satellite: the seat's pad word (the direction nibble, then the buttons), the same way as the guest console's. */
static void rr_gb_link_apply_pad(int index, uint16_t word) {
    GBContext *console = gb_link_context(index);
    if (!console || index <= 0 || index >= RR_GB_LINK_SLOTS) return;
    const GBJoypadState previous = g_rr_link_pad[index];
    GBJoypadState next;
    next.dpad = (uint8_t)(0xFF & ~(word & 0x0F));
    next.buttons = (uint8_t)(0xFF & ~((word >> 4) & 0x0F));
    g_rr_link_pad[index] = next;
    const uint8_t joyp = console->io[0x00];
    if (rr_gb_press_created(previous.dpad, previous.buttons, next.dpad, next.buttons, !(joyp & 0x10), !(joyp & 0x20)))
        request_joypad_interrupt(console);
}

/* Starts (or keeps) the link the match wants, around the guest's context. false: this match has no link. */
static bool rr_gb_link_begin(void) {
    const int wanted = rr_gb_link_consoles_wanted();
    if (wanted < 2 || !g_registered_ctx) { if (gb_link_count() > 1) gb_link_stop(); return false; }
    if (gb_link_count() != wanted && !gb_link_start(g_registered_ctx, wanted)) {
        fprintf(stderr, "[link] the second console could not be made: no link\n");
        return false;
    }
    for (int i = 1; i < wanted; ++i) {
        g_rr_link_pad[i].dpad = g_rr_link_pad[i].buttons = 0xFF;
        gb_link_context(i)->joypad = &g_rr_link_pad[i];
    }
    int view = 0;
    if (rrhk_session_active()) view = rrhk_session_seat();
    else if (const char *text = SDL_getenv("RETRO_RECOMP_GB_LINK_VIEW")) view = atoi(text);
    g_rr_link_view = view >= 0 && view < wanted ? view : 0;
    fprintf(stderr, "[link] %d consoles on the cable, this PC shows console %d\n", wanted, g_rr_link_view);
    return true;
}

/* The second console's input script of a headless test (the format of --input-script), then its pad word at a frame. */
static void rr_gb_link_script_parse(const char *text) {
    g_rr_link_script.clear();
    if (!text || !*text) return;
    char *copy = strdup(text);
    if (!copy) return;
    for (char *token = strtok(copy, ","); token; token = strtok(NULL, ",")) {
        char button_text[16] = {0};
        ScriptEntry entry = {};
        if (!parse_script_token(token, &entry, button_text, sizeof button_text) || !parse_buttons(button_text, &entry.dpad, &entry.buttons)) {
            fprintf(stderr, "[link] invalid input token '%s'\n", token);
            g_rr_link_script.clear();
            break;
        }
        g_rr_link_script.push_back(entry);
    }
    free(copy);
}

static uint16_t rr_gb_link_script_word(const GBContext *console) {
    uint8_t dpad = 0xFF, buttons = 0xFF;
    const uint64_t cycles = console ? console->total_cycles : 0, frame = (uint64_t)g_frame_count;
    for (const ScriptEntry &e : g_rr_link_script) {
        bool active;
        if (e.anchor == SCRIPT_ANCHOR_CYCLE) {
            if (e.period > 0) active = cycles >= e.start && cycles < (e.end + e.duration) && ((cycles - e.start) % e.period) < e.duration;
            else active = cycles >= e.start && cycles < (e.start + e.duration);
        } else active = frame >= e.start && frame < (e.start + e.duration);
        if (active) { dpad &= e.dpad; buttons &= e.buttons; }
    }
    return (uint16_t)((~dpad & 0x0F) | ((~buttons & 0x0F) << 4));
}

/* The console `ctx` belongs to this PC's view: its sound is played and its picture shown; the others advance silently. */
static bool rr_gb_link_shown(const GBContext *ctx) {
    return gb_link_count() < 2 || ctx == gb_link_context(g_rr_link_view);
}

/* A session starts (and again at every restart of it): the cartridge's clock runs on the session's clock, the same on every seat, never on this PC's.
 * The registers become the date of `clock` (seconds since 1970; days counted in the nine bits of the cartridge's counter), the second's
 * cycle counter restarts, and the runtime's own source of time is the same value (the clock file's time stamp is never read in a session). */
static void rr_gb_session_begin_console(GBContext *ctx, uint64_t clock) {
    if (!ctx) return;
    if (ctx->eram && ctx->eram_size) {
        if (g_rr_session_image.size() == ctx->eram_size) memcpy(ctx->eram, g_rr_session_image.data(), ctx->eram_size);
        else memset(ctx->eram, 0, ctx->eram_size);        /* no save of the host's (or one this cartridge does not read): every seat starts blank */
    }
    ctx->config.rtc_unix_time_override_enabled = true;
    ctx->config.rtc_unix_time_override = clock;
    const uint64_t days = clock / 86400u;
    ctx->rtc.s = (uint8_t)(clock % 60u); ctx->rtc.m = (uint8_t)((clock / 60u) % 60u); ctx->rtc.h = (uint8_t)((clock / 3600u) % 24u);
    ctx->rtc.dl = (uint8_t)(days & 0xFFu); ctx->rtc.dh = (uint8_t)((days >> 8) & 0x01u);
    ctx->rtc.latched_s = ctx->rtc.s; ctx->rtc.latched_m = ctx->rtc.m; ctx->rtc.latched_h = ctx->rtc.h;
    ctx->rtc.latched_dl = ctx->rtc.dl; ctx->rtc.latched_dh = ctx->rtc.dh;
    ctx->rtc.latch_state = 0; ctx->rtc.last_time = 0; ctx->rtc.active = true;
}

static void rr_gb_session_begin(uint64_t clock) {
    if (!g_registered_ctx) return;
    const bool linked = rr_gb_link_begin();
    const int consoles = linked ? gb_link_count() : 1;
    /* The game ran one frame before the session's SETUP (the guest's loop runs first, the kit's frame function is called at its end),
     * on this seat's own save, clock and boot: every console starts again from the state the game began in, then takes the match's save
     * (the host's, on every console for now) and the session's clock. */
    for (int i = 0; i < consoles; ++i) {
        if (!g_rr_pristine.empty()) rr_gb_one_load(i, g_rr_pristine.data(), g_rr_pristine.size());
        rr_gb_session_begin_console(rr_gb_console(i), clock);
    }
    g_rr_pcm.clear();
}

/* The match's cartridge RAM (session ABI 8): what the game would read at power-on. The host's is its save file, read here because the kit asks
 * before the game has loaded anything (the cartridge RAM has no size yet): the sizes a cartridge has, and a file of another size is what the
 * game itself rejects, so then the match has no save and every seat starts blank. A guest never reads or writes its own file in a session. */
static bool rr_gb_save_size_valid(size_t size) {
    return size == 512 || size == 2048 || size == 8192 || size == 32768 || size == 65536 || size == 131072;
}

static size_t rr_gb_session_save(void *out, size_t capacity) {
    if (g_persistence_dir.empty()) return 0;
    const fs::path directory(g_persistence_dir);
    FILE *file = fopen((directory / (directory.filename().string() + ".sav")).string().c_str(), "rb");
    if (!file) return 0;
    std::vector<uint8_t> bytes(131073);
    const size_t size = fread(bytes.data(), 1, bytes.size(), file);
    fclose(file);
    if (!rr_gb_save_size_valid(size)) return 0;
    bytes.resize(size);
    g_rr_session_image = bytes;               /* held, so that a restart gives the host its own save back */
    if (!out) return size;
    if (capacity < size) return 0;
    memcpy(out, bytes.data(), size);
    return size;
}

static bool rr_gb_session_save_put(const void *in, size_t size) {
    if (!in || !rr_gb_save_size_valid(size)) return false;
    g_rr_session_image.assign((const uint8_t *)in, (const uint8_t *)in + size);
    return true;
}

/* At a clean end of a match the host writes the match's cartridge RAM (the in-memory one) to its own save file, once: the previous file stays as
 * `.bak` (a copy made first; no copy, no write), the new one goes through the runtime's atomic transaction (a staged file, then a replace). The
 * kit holds the side effects off from SETUP to the end, so the gate of that transaction is opened for this one write. The clock is the session's
 * and is not written. */
static bool write_persistence_transaction(const char* filename, const void* data, size_t size, GBPersistenceTestTarget target);
static bool rr_gb_session_save_commit(void) {
    GBContext *ctx = g_registered_ctx;
    if (!ctx || !ctx->eram || !rr_gb_save_size_valid(ctx->eram_size) || g_persistence_dir.empty()) return false;
    const fs::path directory(g_persistence_dir);
    const fs::path file = directory / (directory.filename().string() + ".sav");
    std::error_code error;
    if (fs::exists(file, error) && !error) {
        fs::copy_file(file, fs::path(file.string() + ".bak"), fs::copy_options::overwrite_existing, error);
        if (error) { fprintf(stderr, "[session] the previous save could not be kept as .bak: the save is not rewritten\n"); return false; }
    }
    if (!ensure_parent_directory(file)) return false;
    const bool before = g_rr_effects;
    g_rr_effects = true;
    const bool written = write_persistence_transaction(file.string().c_str(), ctx->eram, ctx->eram_size, GB_PERSISTENCE_TEST_TARGET_BATTERY);
    g_rr_effects = before;
    if (written) ctx->eram_dirty = false;
    uint64_t hash = 0xcbf29ce484222325ull;                          /* FNV-1a of the image written: the file can be checked against it */
    for (size_t i = 0; i < ctx->eram_size; ++i) hash = (hash ^ ctx->eram[i]) * 0x100000001b3ull;
    fprintf(stderr, "[session] the host's save %s (%zu bytes, fnv1a %016llx)\n", written ? "written" : "not written", ctx->eram_size,
            (unsigned long long)hash);
    return written;
}

/* What a frame may do outside the machine: off for the silent frames of a session and for a guest's whole session. The cartridge RAM and
 * the clock files are the only writes of a Game Boy game (write_persistence_transaction, patched in gameboy_host.py, honours this). */
static void rr_gb_side_effects(bool allowed) { g_rr_effects = allowed; }

/* The machine's digest, then the pad registers one by one (a byte each, in this order). */
static uint64_t rr_gb_digest_adapter(void) {
    uint64_t hash = rr_gb_digest(g_registered_ctx);
    const uint8_t pads[] = {g_manual_joypad_dpad, g_manual_joypad_buttons, g_script_joypad_dpad, g_script_joypad_buttons, g_joypad_dpad, g_joypad_buttons};
    for (size_t i = 0; i < sizeof pads; ++i) hash = (hash ^ pads[i]) * 0x100000001b3ull;
    /* A link: the other consoles' digests follow in seat order, each with its pad registers, folded into the same hash. */
    for (int index = 1; index < gb_link_count(); ++index) {
        uint64_t part = rr_gb_digest(gb_link_context(index));
        part = (part ^ g_rr_link_pad[index].dpad) * 0x100000001b3ull;
        part = (part ^ g_rr_link_pad[index].buttons) * 0x100000001b3ull;
        for (int byte = 0; byte < 8; ++byte) hash = (hash ^ ((part >> (byte * 8)) & 0xFF)) * 0x100000001b3ull;
    }
    return hash;
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
        rrhk_option_row_icon(rows, SDL_SCANCODE_F5, RR_ICON_ROW_PALETTE, "F5 Palette: %s",
                             rr_tr(g_palette_idx == 1 ? "Monochrome" : "Classic green"));
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
        rr_gb_machine.snap_bound = rr_gb_snap_bound_adapter; rr_gb_machine.snap_save = rr_gb_snap_save_adapter;
        rr_gb_machine.snap_load = rr_gb_snap_load_adapter; rr_gb_machine.digest = rr_gb_digest_adapter;
        rr_gb_machine.side_effects = rr_gb_side_effects; rr_gb_machine.session_begin = rr_gb_session_begin;
        rr_gb_machine.session_save = rr_gb_session_save; rr_gb_machine.session_save_put = rr_gb_session_save_put;
        rr_gb_machine.session_save_commit = rr_gb_session_save_commit;
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
    if (!rr_gb_link_shown(ctx)) return;                   /* a link: only the console of this PC's seat is heard */
    if (g_benchmark_mode || !rrhk_window() || rrhk_session_silent() || g_rr_pcm.size() >= (size_t)RR_GB_PCM_LIMIT_FRAMES * 2) return;
    g_rr_pcm.push_back(left);
    g_rr_pcm.push_back(right);
}

/* ---- the entry points of the generated main (platform_sdl.h) ---- */
static void render_frame_internal(const uint32_t* framebuffer, bool count_guest_frame) {
    if (!framebuffer) return;
    /* A link: the picture is the console of this PC's seat (console 0's is what the generated main hands over). */
    if (gb_link_count() > 1 && g_rr_link_view > 0) {
        const uint32_t* shown = gb_get_framebuffer(gb_link_context(g_rr_link_view));
        if (shown) framebuffer = shown;
    }
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
    /* The kit presents the picture, with its filter, at the end of the frame (gb_platform_vsync). A silent frame of a session has none. */
    if (g_benchmark_mode || !rrhk_window() || rrhk_session_silent()) return;
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
    gb_link_stop();
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

    /* A headless link: the second console's pad is its own script (a window that is open takes the seats' words in rr_gb_run_frame). */
    if (gb_link_count() > 1 && rr_gb_link_headless() && !rrhk_session_active())
        rr_gb_link_apply_pad(1, rr_gb_link_script_word(gb_link_context(1)));

    return true;
}

/* Called before every slice of the generated loop: the kit already decided at the last frame whether the game goes on. */
bool gb_platform_wait_while_menu(GBContext* ctx) {
    /* In a session, the state the game begins in (before its first cycle) is kept: SETUP, which comes after the first frame, starts every seat from it. */
    if (ctx && !g_rr_pristine_tried && rrhk_session_active()) {
        g_rr_pristine_tried = true;
        g_rr_pristine.resize(rr_gb_one_bound());                      /* one console's: every console of a link starts from it */
        if (g_rr_pristine.empty() || rr_gb_one_save(0, g_rr_pristine.data(), g_rr_pristine.size()) != g_rr_pristine.size()) g_rr_pristine.clear();
    }
    /* A headless run can start a link of its own (the tests, rr_gb_link_headless): the second console is made before the first cycle. */
    if (ctx && !g_rr_link_headless_tried && rr_gb_link_headless() && !rrhk_session_active()) {
        g_rr_link_headless_tried = true;
        if (rr_gb_link_begin()) rr_gb_link_script_parse(SDL_getenv("RETRO_RECOMP_GB_LINK_SCRIPT"));
    }
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
    /* A headless link says where it stands (the tests compare these lines between two processes): every 60 frames, the digest of the pair. */
    if (gb_link_count() > 1 && rr_gb_link_headless() && g_frame_count % 60 == 0 && SDL_getenv("RETRO_RECOMP_GB_LINK_LOG"))
        fprintf(stderr, "[link] frame %d digest %016llx exchanges %llu\n", g_frame_count, (unsigned long long)rr_gb_digest_adapter(),
                (unsigned long long)gb_link_transfers());
    if (g_benchmark_mode || !rrhk_window()) return;
    rr_gb_machine.frame_seconds = (double)cycles / 4194304.0;
    if (!rrhk_frame_done()) g_rr_stop = true;
}

/* In a session a frame is one whole machine frame, ended by exactly one rrhk_frame_done: the generated loop presents no slice of it. */
bool gb_platform_get_smooth_lcd_transitions(void) { return g_smooth_lcd_transitions && !rrhk_session_active(); }
void gb_platform_set_smooth_lcd_transitions(bool enabled) { g_smooth_lcd_transitions = enabled; }

void gb_platform_set_title(const char* title) {
    if (rrhk_window() && !g_benchmark_mode) SDL_SetWindowTitle(rrhk_window(), title);
}
