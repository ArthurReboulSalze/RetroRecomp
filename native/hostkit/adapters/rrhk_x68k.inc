/* Sharp X68000 adapter for the host kit (docs/HOST_KIT.md, phase 3). Original Retro-Recomp code, MIT.
 *
 * Included by native/x68000_reference/reference_host.c, the one translation unit that owns the libretro core, the disks
 * and the quick-state envelope: the kit's loop calls the machine through the RrhkMachine table below, the frontend's
 * input callbacks read the pad words and the few host facts (guest keyboard, mouse capture, fast loading) kept here.
 * What stays the computer's own, as listed in HOST_KIT.md section 5: the guest keyboard and its Ctrl+Alt chords, the
 * captured mouse and the mouse-game profile, the floppy drives, the fast-loading key, the variable picture size.
 * Everything else (window, picture, F1/F2/F3/F4/F6/F7/F8/F9/F12, pads, pad slots, quit and restart combinations,
 * sound output) is the kit's. Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#ifdef RR_X68000_LINKED
#include "runtime_feedback_sdl.h"
#else
/* The reference prototype has no embedded resources and no fallback hints: the kit's two calls into them are empty. */
void rr_feedback_start(int gameplay) { (void)gameplay; }
int rr_feedback_enabled(void) { return 0; }
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "Fallback hints unavailable"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif
#endif

/* The actions, in menu order; the bit of an action is 1 << its index. Button A is the first button of the game
 * (libretro B), Button B the second. Both are face buttons, so autofire applies to them as on every console. */
enum { X_UP, X_DOWN, X_LEFT, X_RIGHT, X_A, X_B, X_ENTER, X_PAUSE, X_ACTIONS };
#define X_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction x_actions[X_ACTIONS] = {
   {"Up", L"Up", 1u << X_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << X_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << X_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << X_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button A", L"Button A", 1u << X_A, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
   {"Button B", L"Button B", 1u << X_B, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
   {"Start", L"Start", 1u << X_ENTER, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Pause", L"Pause", 1u << X_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {X_NO_PAD, X_NO_PAD}}};
#define X_BIT(action) (1u << (action))

/* What the computer shares with the other disk computers (rrhk_computer.inc) is told which of these actions is which. */
#define RRC_UP X_UP
#define RRC_DOWN X_DOWN
#define RRC_LEFT X_LEFT
#define RRC_RIGHT X_RIGHT
#define RRC_BUTTON_A X_A
#define RRC_BUTTON_B X_B
#define RRC_START X_ENTER
#define RRC_PAUSE X_PAUSE
#define RRC_BIT(action) X_BIT(action)
#define RRC_INI_SECTION L"X68000"
#define RRC_KEYBOARD_ON "Full guest keyboard: ON (F8/F9 sent to X68000)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_F10

/* The largest picture the machine renders (800 x 600) and the one the window starts with. */
#define X_MAX_WIDTH 800
#define X_MAX_HEIGHT 600
#include "hostkit/adapters/rrhk_computer.inc"

static struct {
   uint32_t *argb;                /* the last picture, 0xAARRGGBB, X_MAX_WIDTH per row */
   int16_t *audio;                /* the sound of this frame (stereo int16), not yet taken by the kit */
   size_t audio_count, audio_capacity, audio_taken;
} xa;



/* The libretro joypad of a port from the kit's pad word (keyboard, controller, stick, autofire, opposite directions). */
static int player_joy(unsigned port) {
   static const struct { unsigned action, id; } map[] = { {X_UP, RETRO_DEVICE_ID_JOYPAD_UP}, {X_DOWN, RETRO_DEVICE_ID_JOYPAD_DOWN},
      {X_LEFT, RETRO_DEVICE_ID_JOYPAD_LEFT}, {X_RIGHT, RETRO_DEVICE_ID_JOYPAD_RIGHT}, {X_A, RETRO_DEVICE_ID_JOYPAD_B}, {X_B, RETRO_DEVICE_ID_JOYPAD_A} };
   unsigned mask = 0, n;
   if (!ca.windowed || port > 1) return -1;
   if (player_blocked() || !input_focus) return 0;
   for (n = 0; n < sizeof map / sizeof map[0]; n++) if (ca.pad[port] & X_BIT(map[n].action)) mask |= 1u << map[n].id;
   return (int)mask;
}

/* ---- the picture ---- */
static void player_picture(const void *data, unsigned w, unsigned h, size_t pitch) {
   unsigned x, y;
   if (!ca.windowed || !data || !xa.argb) return;
   if (w > X_MAX_WIDTH || h > X_MAX_HEIGHT) { fail("Video geometry beyond the machine's largest picture"); return; }
   for (y = 0; y < h; y++) {
      uint32_t *out = xa.argb + (size_t)y * X_MAX_WIDTH;
      const uint8_t *row = (const uint8_t *)data + y * pitch;
      if (pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
         for (x = 0; x < w; x++) {
            uint16_t v; unsigned r, g, b;
            memcpy(&v, row + x * 2, 2);
            r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31;
            out[x] = 0xff000000u | ((r * 255 / 31) << 16) | ((g * 255 / 63) << 8) | (b * 255 / 31);
         }
      } else for (x = 0; x < w; x++) { uint32_t c; memcpy(&c, row + x * 4, 4); out[x] = c | 0xff000000u; }
   }
}
static const uint32_t *x_pixels(void) { return xa.argb; }
static int x_width(void) { return width ? (int)width : 768; }
static int x_height(void) { return height ? (int)height : 576; }


/* ---- the sound: the frame's PCM waits here until the kit takes it ---- */
static int player_queue_audio(const int16_t *samples, size_t count) {
   if (!ca.windowed) return 1;
   if (xa.audio_count + count * 2 > xa.audio_capacity) {
      size_t capacity = (xa.audio_count + count * 2) * 2;
      void *grown = realloc(xa.audio, capacity * sizeof(int16_t));
      if (!grown) return 0;
      xa.audio = (int16_t *)grown; xa.audio_capacity = capacity;
   }
   memcpy(xa.audio + xa.audio_count, samples, count * 2 * sizeof(int16_t));
   xa.audio_count += count * 2;
   return 1;
}
static size_t x_audio(int16_t *pcm, size_t capacity) {
   size_t n = xa.audio_count - xa.audio_taken;
   if (n > capacity) n = capacity;
   if (!n) { xa.audio_count = xa.audio_taken = 0; return 0; }
   memcpy(pcm, xa.audio + xa.audio_taken, n * sizeof(int16_t));
   xa.audio_taken += n;
   return n;
}

static bool x_run_frame(uint16_t p1, uint16_t p2) {
   ca.pad[0] = p1; ca.pad[1] = p2;
   fast_forward = x_fast_forward();
   input_poll();
   if (!host_frame() || quit_requested || core_error) return false;
   return !frame_limit || frame_number < frame_limit;
}
static void x_pause(bool paused) { (void)paused; }
static int x_players(void) { return 2; }
static void x_reset(void) {
   core.reset();
   if (media_opened && !rr_media_boot(&media)) fail(rr_media_error(&media));
   automatic_loading = false; memset(&loading_detector, 0, sizeof(loading_detector));
}
static uint64_t x_interpreted(void) {
#ifdef RR_X68000_DEVCPU
   return cpu_stats[2] + cpu_stats[3];
#else
   return 1;   /* the reference prototype runs the whole MC68000 on its interpreter */
#endif
}
static uint64_t x_zero(void) { return 0; }
static uint64_t x_input_frame(void) { return input_frame; }
static bool x_state_ready(void) { return true; }
static bool x_state_path(wchar_t *path, size_t capacity) { return rr_from_utf8(state_slot, path, capacity) != 0; }
static bool x_state_file(const wchar_t *path, bool load) { (void)path; return snapshot(load) == RR_STATE_OK; }





const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      machine = (RrhkMachine){
         .ini_section = L"X68000", .console_name = "X68000",
         .table_players = 2, .players = x_players,
         .actions = x_actions, .action_count = X_ACTIONS,
         .up = X_UP, .down = X_DOWN, .left = X_LEFT, .right = X_RIGHT, .start = X_ENTER,
         .max_width = X_MAX_WIDTH, .max_height = X_MAX_HEIGHT, .frame_seconds = 1.0 / 61.46,
         .own_audio = false, .audio_model = RRHK_AUDIO_QUEUE, .audio_rate = 44100u, .audio_chunked = true,
         .video_section = L"X68000", .autofire_section = L"X68000", .indexed_bindings = true, .bindings_clearable = true,
         .machine_fkeys = 10,
         .save_failed_en = "Cannot save game state", .save_failed_fr = "Impossible de sauvegarder",
         .reset = x_reset, .run_frame = x_run_frame, .pause = x_pause,
         .pixels = x_pixels, .visible_width = x_width, .visible_height = x_height, .raster_height = x_height, .display_width = x_width,
         .audio = x_audio, .interpreted = x_interpreted, .audio_interpreted = x_zero,
         .state_path = x_state_path, .state_ready = x_state_ready, .state_file = x_state_file, .input_frame = x_input_frame,
         .settings_loaded = x_settings_loaded, .help_lines = x_help_lines, .help_controls = x_help_controls,
         .frame_start = x_frame_start, .finished = x_finished,
         .event = x_event, .keyboard_pad = x_keyboard_pad, .fast_forward = x_fast_forward, .game_rect = x_game_rect,
         .help_page = x_help_page, .action_held = x_action_held,
      };
   }
   return &machine;
}

/* The windowed game: the kit runs the loop and calls x_run_frame for each guest frame. */
static int player_run_windowed(const char *title) {
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   int status;
   machine->frame_seconds = 1.0 / fps;
   machine->own_audio = mute;
   ca.windowed = true;
   xa.argb = (uint32_t *)calloc((size_t)X_MAX_WIDTH * X_MAX_HEIGHT, sizeof(uint32_t));
   if (!xa.argb) { fail("Presentation allocation failed"); return 1; }
   status = rrhk_main(machine, title, 1);
   return status;
}
static void player_shutdown(void) { free(xa.argb); free(xa.audio); xa.argb = NULL; xa.audio = NULL; }
