/* Nintendo 64 adapter for the host kit (docs/HOST_KIT.md, a console with sticks, rumble and the graphics page of F3, section 2.4
 * and D14). Original Retro-Recomp code, MIT; the game it is linked into is GPL-3.0 as a whole (licenses/mupen64plus-next.md).
 *
 * Included by native/n64_machine/n64_player.c, which owns the session (n64_session.h). Four players with the N64 pad: A, B, Z,
 * Start, L, R, the four C buttons, the d-pad and the control stick. A gamepad's left stick is the control stick and its right stick
 * the C buttons (the core reads both); on the keyboard the four Stick actions push the control stick to its edge (the d-pad has
 * its own keys). The picture is the renderer's image read back after each frame, as large as the internal resolution makes it.
 * The sound is 44.1 kHz stereo through the kit's ring. Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "retro_keyboard.h"
#include "retro_menu.h"

/* The pad word's bits are the session's (RR_N64_PAD_*). The Stick actions are host-side (bit 0): the adapter reads their keys and
 * buttons itself and turns them into the stick (the pad word has sixteen bits and the console's fourteen buttons use them). */
#define N64_PADS(button) {button, button, button, button}
#define N64_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
enum { N_A, N_B, N_Z, N_START, N_L, N_R, N_CUP, N_CDOWN, N_CLEFT, N_CRIGHT, N_UP, N_DOWN, N_LEFT, N_RIGHT,
       N_SUP, N_SDOWN, N_SLEFT, N_SRIGHT, N_ACTIONS };
static const RrhkAction n64_actions[N_ACTIONS] = {
    {"A", L"A", RR_N64_PAD_A, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_2}, N64_PADS(SDL_CONTROLLER_BUTTON_A)},
    {"B", L"B", RR_N64_PAD_B, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_4}, N64_PADS(SDL_CONTROLLER_BUTTON_X)},
    {"Z", L"Z", RR_N64_PAD_Z, RRHK_SYSTEM, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_0}, N64_PADS(RRHK_PAD_LEFT_TRIGGER)},
    {"Start", L"Start", RR_N64_PAD_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, N64_PADS(SDL_CONTROLLER_BUTTON_START)},
    {"L", L"L", RR_N64_PAD_L, RRHK_SYSTEM, SDLK_q, {SDL_SCANCODE_Q, SDL_SCANCODE_KP_7}, N64_PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER)},
    {"R", L"R", RR_N64_PAD_R, RRHK_SYSTEM, SDLK_e, {SDL_SCANCODE_E, SDL_SCANCODE_KP_9}, N64_PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)},
    {"C-Up", L"CUp", RR_N64_PAD_C_UP, RRHK_SYSTEM, 0, {SDL_SCANCODE_I, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_Y)},
    {"C-Down", L"CDown", RR_N64_PAD_C_DOWN, RRHK_SYSTEM, 0, {SDL_SCANCODE_K, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_B)},
    {"C-Left", L"CLeft", RR_N64_PAD_C_LEFT, RRHK_SYSTEM, 0, {SDL_SCANCODE_J, SDL_SCANCODE_UNKNOWN}, N64_PADS(N64_NO_PAD)},
    {"C-Right", L"CRight", RR_N64_PAD_C_RIGHT, RRHK_SYSTEM, 0, {SDL_SCANCODE_L, SDL_SCANCODE_UNKNOWN}, N64_PADS(N64_NO_PAD)},
    {"Up", L"Up", RR_N64_PAD_UP, RRHK_DIR, 0, {SDL_SCANCODE_T, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)},
    {"Down", L"Down", RR_N64_PAD_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_G, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)},
    {"Left", L"Left", RR_N64_PAD_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_F, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)},
    {"Right", L"Right", RR_N64_PAD_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_H, SDL_SCANCODE_UNKNOWN}, N64_PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)},
    {"Stick up", L"StickUp", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_8}, N64_PADS(N64_NO_PAD)},
    {"Stick down", L"StickDown", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_5}, N64_PADS(N64_NO_PAD)},
    {"Stick left", L"StickLeft", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, N64_PADS(N64_NO_PAD)},
    {"Stick right", L"StickRight", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, N64_PADS(N64_NO_PAD)}};

/* ---- the graphics page (D14): what the player sees only; each default is the reference setting every check uses ----
 * Five rows since 1.7.6 (Arthur, 15 November 2026: « Oui, valide »). The renderer's other settings are fixed at the glue's defaults, which
 * are the reference: the super-sampled read-back off, native texture LOD off (it acts only above 1x; F-Zero X's level of detail is the
 * game's own models), Bob deinterlacing (an N64 has no progressive mode for an interlaced picture, and
 * Bob never combs; ParaLLEl keeps Weave for 1x with CRT shaders), the gamma dither on and native texture rectangles on, as the console;
 * the divot filter follows "Edge smoothing", whose notches it removes. A saved value of a removed row is read by no one.
 * Supersampling (Arthur, 15 November 2026: « Ok pour ta proposition d'anti-crénelage. ») draws at twice the internal resolution and
 * ParaLLEl's scanout reduces the picture by two after the VI: the picture keeps the size the resolution row gives, each pixel the
 * mean of four drawn ones, for four times the GPU work. Off, the renderer gets exactly the options it got before the row. 8x, ParaLLEl's
 * largest drawing (Arthur, « Dans la 1.7.6 »), joins the resolution row; at 8x Supersampling has nothing larger to draw and does
 * nothing. */
static const char *const n64_resolutions[] = {"1x (native)", "2x", "4x", "8x"};
static const char *const n64_upscalings[] = {"1x", "2x", "4x", "8x"};
static const char *const n64_off_on[] = {"Off", "On"};
static const char *const n64_false_true[] = {"False", "True"};
static const char *const n64_crops[] = {"Off", "8 pixels", "16 pixels"};
static const char *const n64_crop_values[] = {"0", "8", "16"};
enum { G_RESOLUTION, G_SUPERSAMPLING, G_EDGES, G_SCALING, G_DITHER, G_OVERSCAN, G_COUNT };
static const RrhkGfxOption n64_gfx_options[G_COUNT] = {
    {"Internal resolution", L"resolution", n64_resolutions, 4, 0},
    {"Supersampling", L"supersampling", n64_off_on, 2, 0},
    {"Edge smoothing (console)", L"viaa", n64_off_on, 2, 1},
    {"Smooth scaling (console)", L"vibilinear", n64_off_on, 2, 1},
    {"Dither smoothing", L"ditherfilter", n64_off_on, 2, 1},
    {"Overscan crop", L"overscan", n64_crops, 3, 0}};
/* The rows a core option follows directly; the resolution and supersampling rows set the upscaling and downscaling together. */
static const char *const *const n64_gfx_values[G_COUNT] = {
    NULL, NULL, n64_false_true, n64_false_true, n64_false_true, n64_crop_values};
static const char *const n64_gfx_keys[G_COUNT] = {
    NULL, NULL, "parallel-rdp-vi-aa", "parallel-rdp-vi-bilinear", "parallel-rdp-dither-filter", "parallel-rdp-overscan"};
static int n64_scale = 1;   /* the internal resolution in force: the picture's size against the console's, supersampled or not */
static int n64_resolution = 0, n64_supersampling = 0;

static void n64_gfx_apply(int option, int value) {
    if (option < 0 || option >= G_COUNT || value < 0 || value >= n64_gfx_options[option].count) return;
    if (option == G_RESOLUTION || option == G_SUPERSAMPLING) {
        if (option == G_RESOLUTION) n64_resolution = value;
        else n64_supersampling = value;
        const bool reduce = n64_supersampling && n64_resolution < 3;
        rr_n64_option(session, "parallel-rdp-upscaling", n64_upscalings[n64_resolution + reduce]);
        rr_n64_option(session, "parallel-rdp-downscaling", reduce ? "1/2" : "disable");
        n64_scale = 1 << n64_resolution;
        return;
    }
    rr_n64_option(session, n64_gfx_keys[option], n64_gfx_values[option][value]);
    if (option == G_EDGES) rr_n64_option(session, "parallel-rdp-divot-filter", n64_gfx_values[option][value]);
}

/* Headless runs never open the kit: the defaults (or `--gfx key=index`, for a capture) are applied here. */
static void n64_gfx_defaults(void) { for (int i = 0; i < G_COUNT; ++i) n64_gfx_apply(i, n64_gfx_options[i].def); }
static bool n64_gfx_assign(const char *assignment, bool windowed) {
    const char *equals = strchr(assignment, '=');
    if (windowed) return rrhk_gfx_override(rrhk_adapter(), assignment);
    if (!equals) return false;
    for (int i = 0; i < G_COUNT; ++i) {
        char key[64];
        snprintf(key, sizeof key, "%ls", n64_gfx_options[i].ini_key);
        if (strlen(key) == (size_t)(equals - assignment) && !strncmp(assignment, key, strlen(key))) {
            const int value = atoi(equals + 1);
            if (value < 0 || value >= n64_gfx_options[i].count) return false;
            n64_gfx_apply(i, value);
            return true;
        }
    }
    return false;
}

/* ---- the machine ---- */
static int n64_players(void) { return 4; }
static uint16_t n64_rumbling[4][2];
static void n64_rumble(void) {
    for (int p = 0; p < 4; ++p) {
        uint16_t strong = 0, weak = 0;
        rr_n64_rumble(session, p, &strong, &weak);
        /* A motor the game keeps running is renewed every frame; a stop is sent once. */
        if (strong || weak || n64_rumbling[p][0] || n64_rumbling[p][1]) rrhk_rumble(p, strong, weak, strong || weak ? 100 : 0);
        n64_rumbling[p][0] = strong;
        n64_rumbling[p][1] = weak;
    }
}

static bool n64_run_frame(uint16_t p1, uint16_t p2) {
    const uint64_t frame = frame_number;
    gfx_changes_due(rr_n64_frame_index(session));
    if (event_count) scripted_inputs(rr_n64_frame_index(session));   /* a test run replays its script */
    else for (int p = 0; p < 4; ++p) {
        int16_t axes[RRHK_AXES] = {0, 0, 0, 0};
        const uint16_t word = p == 0 ? p1 : p == 1 ? p2 : rrhk_pad_word(p, frame);
        rrhk_pad_axes(p, frame, axes);
        /* The keyboard's Stick actions: the stick at its edge, as a pad's stick pushed all the way. */
        if (rrhk_action_held(p, N_SLEFT)) axes[RRHK_AXIS_LX] = -32767;
        if (rrhk_action_held(p, N_SRIGHT)) axes[RRHK_AXIS_LX] = 32767;
        if (rrhk_action_held(p, N_SUP)) axes[RRHK_AXIS_LY] = -32767;
        if (rrhk_action_held(p, N_SDOWN)) axes[RRHK_AXIS_LY] = 32767;
        player_inputs(p, word, axes);
    }
    if (!player_frame()) return false;
    n64_rumble();
    return !quit_requested && (!frame_limit || frame_number < frame_limit);
}
/* --frame-times of a windowed run: the kit's cost of each frame (the machine, the sound, the drawing, the present; not the pacing). */
static bool n64_cost_enabled(void) { return frame_log != NULL; }
static void n64_cost(double busy_ms, double present_ms) {
    fprintf(frame_log, "%llu\t%.4f\t%.4f\n", (unsigned long long)rr_n64_frame_index(session), busy_ms, present_ms);
}
static void n64_pause(bool paused) {
    if (paused) for (int p = 0; p < 4; ++p) if (n64_rumbling[p][0] || n64_rumbling[p][1]) { rrhk_rumble(p, 0, 0, 0); n64_rumbling[p][0] = n64_rumbling[p][1] = 0; }
}
static void n64_reset(void) { restart_requested = true; quit_requested = true; }   /* the session is one per process */

/* The picture: rows packed at its width, which grows with the internal resolution. */
static const uint32_t *n64_pixels(void) { return rr_n64_picture(session, NULL, NULL); }
static int n64_pixel_pitch(void) { int w = 0; rr_n64_picture(session, &w, NULL); return w ? w : 320; }
static int n64_visible_width(void) { int w = 0; rr_n64_picture(session, &w, NULL); return w ? w : 320; }
static int n64_visible_height(void) { int h = 0; rr_n64_picture(session, NULL, &h); return h ? h : 240; }
/* The shape the picture is shown at: the console's lines (the picture's divided by the internal resolution) at the core's display
 * aspect (4:3 on a television). */
static int n64_raster_height(void) { const int h = n64_visible_height() / n64_scale; return h > 0 ? h : 240; }
static int n64_display_width(void) { return (int)(rr_n64_aspect(session) * n64_raster_height() + 0.5); }
static size_t n64_audio(int16_t *pcm, size_t capacity) { return player_audio(pcm, capacity); }
static bool n64_audio_enable(unsigned rate) { return rate == rr_n64_audio_rate(session); }
static uint64_t n64_interpreted(void) { return rr_n64_interpreted_count(session); }
static uint64_t n64_zero(void) { return 0; }   /* the RSP's microcode runs on its own recompiler (ParaLLEl-RSP), not counted as VR4300 code */
static uint64_t n64_input_frame(void) { return frame_number; }
static bool n64_state_ready(void) { return true; }
static bool n64_state_path(wchar_t *path, size_t capacity) { return rr_from_utf8(state_slot, path, capacity) != 0; }
static bool n64_state_file(const wchar_t *path, bool load) {
    char utf8[PATH_CAP];
    if (!rr_to_utf8(path, utf8, sizeof utf8)) return false;
    return (load ? state_load(utf8) : state_save(utf8)) == 0;
}

static void n64_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Arrows stick; X A, C B, W Z; Q/E L/R; I/K/J/L C buttons",
                                   "Fleches stick ; X A, C B, W Z ; Q/E L/R ; I/K/J/L boutons C"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter Start; T/F/G/H d-pad", "Entree Start ; T/F/G/H croix"));
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = L"Nintendo64", .console_name = "Nintendo 64",
            .table_players = 4, .players = n64_players,
            .actions = n64_actions, .action_count = N_ACTIONS,
            .up = N_UP, .down = N_DOWN, .left = N_LEFT, .right = N_RIGHT, .start = N_START,
            .max_width = RR_N64_MAX_WIDTH, .max_height = RR_N64_MAX_HEIGHT,
            .frame_seconds = 1.0 / 60.0,
            .audio_model = RRHK_AUDIO_RING, .audio_rate = 44100, .audio_enable = n64_audio_enable, .audio_channels = 2,
            .reset = n64_reset, .run_frame = n64_run_frame, .pause = n64_pause,
            .pixels = n64_pixels, .pixel_pitch = n64_pixel_pitch, .visible_width = n64_visible_width,
            .visible_height = n64_visible_height, .raster_height = n64_raster_height, .display_width = n64_display_width,
            .audio = n64_audio, .interpreted = n64_interpreted, .audio_interpreted = n64_zero,
            .state_path = n64_state_path, .state_ready = n64_state_ready, .state_file = n64_state_file,
            .input_frame = n64_input_frame, .help_controls = n64_help_controls,
            .cost_enabled = n64_cost_enabled, .cost = n64_cost,
            .analog_sticks = 2, .trigger_buttons = true, .rumble = true, .native_caption = RRHK_CORE_CAPTION,
            .gfx_options = n64_gfx_options, .gfx_option_count = G_COUNT, .gfx_apply = n64_gfx_apply,
        };
    }
    return &machine;
}

/* The windowed game: the kit runs the loop and calls n64_run_frame for each frame. */
static int player_run_windowed(const char *title) {
    RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
    machine->frame_seconds = 1.0 / rr_n64_fps(session);
    machine->audio_rate = rr_n64_audio_rate(session);
    return rrhk_main(machine, title, 2);
}
