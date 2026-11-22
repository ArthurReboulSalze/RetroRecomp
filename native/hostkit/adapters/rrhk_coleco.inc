/* ColecoVision adapter for the host kit (docs/HOST_KIT.md, docs/COLECOVISION.md; a console: two controllers with a stick, two fire buttons and a
 * twelve-key keypad, no Pause button, no keyboard). Original Retro-Recomp code, MIT.
 *
 * Included by native/coleco_machine/coleco_player.c, which owns the machine (coleco_glue.inc: the `machine` variable) and the quick
 * states (coleco_state_file.inc). The guest owns the loop (the translated Z80 code runs until a frame ends): the game opens the window
 * with cv_host_open and calls cv_host_frame at the end of each guest frame (RrhkMachine.driven, as the Master System, the MSX and the SG-1000).
 * Nothing of the computers' adapter (rrhk_computer.inc) is used: every hook that file provides is left NULL, which the kit reads as "none".
 *
 * What is the ColecoVision's, in one 16-bit pad word per player (the kit's contract, so rollback, the digest and a multiplayer session carry
 * everything the game reads): the stick (bits 0-3), the two fire buttons (bits 4-5), the keypad's four lines (bits 6-9: a key is the code of
 * the lines it pulls, two keys held merge as on the real keypad), bit 10 reserved (the console has no Pause button), and bit 11 the flag « the
 * on-screen keypad is open », which the machine reads as « this pad's stick and fire buttons are not the game's ». The twelve keys are ordinary
 * action rows, bindable on the keyboard pages of F2 like any other (the physical top-row digit keys for player 1, the numeric pad's for player 2),
 * and the gamepad's Y opens the host kit's on-screen keypad (rrhk_keypad.inc: the D-pad moves on it, A presses a key, B or Y closes it), drawn
 * over the picture while the game keeps running. The keypad closes on a menu, a restart and a quick-state load.
 *
 * The TMS9928A picture, 256 x 192 colour indices through the chip's sixteen colours with the border of each line around it (the MSX1's and
 * the SG-1000's view and palette: the same chip); the sound, the SN76489A's mono samples doubled into the shared stereo ring of
 * native/audio_output.inc. Quick states (F8/F9) are the game's (coleco_state_file.inc), saved and loaded at once: the kit calls them from
 * the frame's end, which is already the game's service point. Multiplayer: an in-process snapshot and the digest
 * (coleco_state_file.inc: the state's body without the picture), rollback; no cartridge save, so session_save* stay NULL. Nothing here says how long a press takes to reach the picture: that is not measured. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include "hostkit/adapters/rrhk_keypad.inc"

/* The actions, in menu order. The bits are the machine's CV_PAD_*: the stick, the fire buttons, then each keypad key as the lines it pulls
 * (CV_KEY_* in bits 6-9), then the on-screen keypad's flag. Player 1 plays on the arrow keys, D (fire 1, the left button) and S (fire 2, the right
 * button), the digits of the top row and [ ] for * and #; player 2 on I J K L, U and O and the numeric pad's digits, * and /. */
enum { C_UP, C_DOWN, C_LEFT, C_RIGHT, C_FIRE1, C_FIRE2, C_KEY1, C_KEY2, C_KEY3, C_KEY4, C_KEY5, C_KEY6, C_KEY7, C_KEY8, C_KEY9, C_STAR,
       C_KEY0, C_HASH, C_KEYPAD, C_ACTIONS };
#define C_NO_KEY SDL_SCANCODE_UNKNOWN
#define C_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
#define C_ROW(name, ini, bit, group, k1, k2, b1, b2) {name, ini, (uint16_t)(bit), group, 0, {k1, k2}, {b1, b2}}
#define C_KEY(name, ini, code, k1, k2) C_ROW(name, ini, (code) << CV_PAD_KEY_SHIFT, RRHK_SYSTEM, k1, k2, C_NO_PAD, C_NO_PAD)
static const RrhkAction s_actions[C_ACTIONS] = {
   C_ROW("Up", L"Up", CV_PAD_UP, RRHK_DIR, SDL_SCANCODE_UP, SDL_SCANCODE_I, SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP),
   C_ROW("Down", L"Down", CV_PAD_DOWN, RRHK_DIR, SDL_SCANCODE_DOWN, SDL_SCANCODE_K, SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN),
   C_ROW("Left", L"Left", CV_PAD_LEFT, RRHK_DIR, SDL_SCANCODE_LEFT, SDL_SCANCODE_J, SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT),
   C_ROW("Right", L"Right", CV_PAD_RIGHT, RRHK_DIR, SDL_SCANCODE_RIGHT, SDL_SCANCODE_L, SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT),
   C_ROW("Fire 1", L"Fire1", CV_PAD_B1, RRHK_FACE, SDL_SCANCODE_D, SDL_SCANCODE_U, SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A),
   C_ROW("Fire 2", L"Fire2", CV_PAD_B2, RRHK_FACE, SDL_SCANCODE_S, SDL_SCANCODE_O, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B),
   C_KEY("Keypad 1", L"Key1", CV_KEY_1, SDL_SCANCODE_1, SDL_SCANCODE_KP_1), C_KEY("Keypad 2", L"Key2", CV_KEY_2, SDL_SCANCODE_2, SDL_SCANCODE_KP_2),
   C_KEY("Keypad 3", L"Key3", CV_KEY_3, SDL_SCANCODE_3, SDL_SCANCODE_KP_3), C_KEY("Keypad 4", L"Key4", CV_KEY_4, SDL_SCANCODE_4, SDL_SCANCODE_KP_4),
   C_KEY("Keypad 5", L"Key5", CV_KEY_5, SDL_SCANCODE_5, SDL_SCANCODE_KP_5), C_KEY("Keypad 6", L"Key6", CV_KEY_6, SDL_SCANCODE_6, SDL_SCANCODE_KP_6),
   C_KEY("Keypad 7", L"Key7", CV_KEY_7, SDL_SCANCODE_7, SDL_SCANCODE_KP_7), C_KEY("Keypad 8", L"Key8", CV_KEY_8, SDL_SCANCODE_8, SDL_SCANCODE_KP_8),
   C_KEY("Keypad 9", L"Key9", CV_KEY_9, SDL_SCANCODE_9, SDL_SCANCODE_KP_9),
   C_KEY("Keypad *", L"KeyStar", CV_KEY_STAR, SDL_SCANCODE_LEFTBRACKET, SDL_SCANCODE_KP_MULTIPLY),
   C_KEY("Keypad 0", L"Key0", CV_KEY_0, SDL_SCANCODE_0, SDL_SCANCODE_KP_0),
   C_KEY("Keypad #", L"KeyHash", CV_KEY_HASH, SDL_SCANCODE_RIGHTBRACKET, SDL_SCANCODE_KP_DIVIDE),
   /* the open row: gamepad Y on both pads, no key (a keyboard player has the keys themselves); its bit is the flag */
   C_ROW("On-screen keypad", L"Keypad", CV_PAD_KEYPAD_OPEN, RRHK_SYSTEM, C_NO_KEY, C_NO_KEY, SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_Y)};

/* The keypad grid, as printed on the controller: the labels row by row and the action row each cell presses. */
static const char *const s_key_labels[12] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"};
static const int s_key_cells[12] = {C_KEY1, C_KEY2, C_KEY3, C_KEY4, C_KEY5, C_KEY6, C_KEY7, C_KEY8, C_KEY9, C_STAR, C_KEY0, C_HASH};
static const RrhkKeypad s_keypad = {4, 3, s_key_labels, s_key_cells, C_KEYPAD};

/* ---- the picture: the TMS9928A's 256 x 192 with eight border pixels around it (the MSX1's view, the same chip) ---- */
enum { S_VIEW_W = TMS_WIDTH + 16, S_VIEW_H = TMS_HEIGHT + 16 };
static uint32_t s_view[S_VIEW_W * S_VIEW_H];
/* The TMS9918A's sixteen colours (a commonly published approximation of its analogue output; not measured on a set). Index 0 is
 * transparent: the chip puts the backdrop colour there before the picture reaches the host, so it only shows as black when the backdrop
 * is colour 0 itself. The values are the MSX adapter's. */
static const uint32_t s_palette[16] = {
   0xFF000000, 0xFF000000, 0xFF21C842, 0xFF5EDC78, 0xFF5455ED, 0xFF7D76FC, 0xFFD4524D, 0xFF42EBF5,
   0xFFFC5554, 0xFFFF7978, 0xFFD4C154, 0xFFE6CE80, 0xFF21B03B, 0xFFC95BBA, 0xFFCCCCCC, 0xFFFFFFFF};

static void s_picture(const CvMachine *m) {
   for (int y = 0; y < S_VIEW_H; y++) {
      int line = y - 8;
      uint32_t edge = s_palette[m->vdp.border[line < 0 ? 0 : line >= TMS_HEIGHT ? TMS_HEIGHT - 1 : line] & 15];
      uint32_t *out = s_view + y * S_VIEW_W;
      for (int x = 0; x < S_VIEW_W; x++) out[x] = edge;
      if (line >= 0 && line < TMS_HEIGHT)
         for (int x = 0; x < TMS_WIDTH; x++) out[8 + x] = s_palette[m->vdp.frame[line][x] & 15];
   }
}

/* ---- the sound: mono 44.1 kHz from the machine, doubled into the stereo ring (the Master System's and the MSX's output) ---- */
static SDL_AudioDeviceID audio_device;
static void audio_output_clear(void);
#define RR_HOST_AUDIO_FILTER rrhk_options_audio
#define RR_HOST_AUDIO_RESET rrhk_options_audio_reset
#define RR_HOST_AUDIO_DEVICE rrhk_audio_device
#define RR_HOST_AUDIO_HELD rrhk_audio_held
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
#include "audio_output.inc"

static void s_sound(CvMachine *m) {
   static int16_t mono[CV_AUDIO_BUFFER], stereo[2 * CV_AUDIO_BUFFER];
   unsigned n = cv_audio_take(m, mono, CV_AUDIO_BUFFER);
   if (rrhk_session_silent()) return;            /* a frame run again after a multiplayer correction: no sound */
   for (unsigned i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
   host_audio_submit(stereo, n);
}

/* ---- the machine table ---- */
static struct { bool reset; uint64_t frame; uint16_t pad[2]; } sh;

static int s_players(void) { return 2; }
/* The kit hands the pad words of the frame to come; the game takes them at the end of cv_host_frame. */
static bool s_run_frame(uint16_t p1, uint16_t p2) { sh.pad[0] = p1; sh.pad[1] = p2; return true; }
/* The shell calls this at every frame start: only a change empties the ring (the sound held before a pause is not played after it). */
static void s_pause_machine(bool paused) {
   static bool was;
   if (paused == was) return;
   was = paused;
   audio_output_clear();
}
/* The guest owns the loop: a reset is a request the game takes at the end of the frame (cv_host_frame returns 2); the shell keeps running. */
static void s_reset(void) { sh.reset = true; rrhk_keypad_close(); }
static const uint32_t *s_pixels(void) { return s_view; }
static int s_width(void) { return S_VIEW_W; }
static int s_height(void) { return S_VIEW_H; }
/* The TMS9918A's pixel clock (5.37 MHz) gives pixels 8/7 as wide as tall on a 4:3 set, as on the MSX1. */
static int s_display_width(void) { return (S_VIEW_W * 8 + 3) / 7; }
static size_t s_no_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t s_zero(void) { return 0; }
static uint64_t s_interpreted(void) { return banked_fallback_steps; }   /* the counted fallback of the Z80, never hidden */
static uint64_t s_input_frame(void) { return sh.frame; }
static bool s_state_ready(void) { return true; }
static bool s_state_file(const wchar_t *path, bool load) {
   const bool ok = cv_game_state_file(path, load);
   if (ok && load) rrhk_keypad_close();          /* a loaded state starts with the on-screen keypad closed */
   return ok;
}
static bool s_state_path(wchar_t *path, size_t capacity) { return cv_game_state_path(path, capacity); }

/* The keypad's hooks: its own events (Y opens it, the D-pad, A and B while it is open), what it holds in the pad word, its drawing. */
static bool s_event(const SDL_Event *e, bool *running) { (void)running; return rrhk_keypad_event(&s_keypad, e); }
static bool s_action_held(int player, int action) { return rrhk_keypad_held(&s_keypad, player, action); }
static void s_before_present(SDL_Renderer *renderer) { rrhk_keypad_draw(&s_keypad, renderer); }

static void s_help_lines(int slot, const char **lines, int *count) {
   if (slot == 1) lines[(*count)++] = rrhk_tr("Gamepad Y  On-screen keypad", "Manette Y  Pave numerique");
}

static void s_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, rrhk_tr("Arrows: stick; D, S: fire 1, 2; 1-9, 0: keys; [ ]: * #",
                                  "Fleches : manette ; D, S : feu 1, 2 ; 1-9, 0 : touches ; [ ] : * #"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Player 2: I J K L, U O, numeric pad keys. Gamepad Y: keypad",
                                                 "Joueur 2 : I J K L, U O, pave numerique. Manette Y : pave"));
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine adapter;
   if (!adapter.actions) {
      memset(&adapter, 0, sizeof adapter);
      adapter.ini_section = L"ColecoVision"; adapter.console_name = "ColecoVision";
      adapter.table_players = 2; adapter.players = s_players;
      adapter.actions = s_actions; adapter.action_count = C_ACTIONS;
      /* No Pause button: `start` names the first fire button, as the keypad's own check does. */
      adapter.up = C_UP; adapter.down = C_DOWN; adapter.left = C_LEFT; adapter.right = C_RIGHT; adapter.start = C_FIRE1;
      adapter.max_width = S_VIEW_W; adapter.max_height = S_VIEW_H;
      adapter.frame_seconds = (double)CV_CYCLES_PER_LINE * CV_LINES_NTSC / CV_CPU_CLOCK;
      adapter.own_audio = true; adapter.driven = true; adapter.state_deferred = false;
      adapter.reset = s_reset; adapter.run_frame = s_run_frame; adapter.pause = s_pause_machine;
      adapter.pixels = s_pixels; adapter.visible_width = s_width; adapter.visible_height = s_height; adapter.raster_height = s_height;
      adapter.display_width = s_display_width;
      adapter.audio = s_no_audio; adapter.interpreted = s_interpreted; adapter.audio_interpreted = s_zero;
      adapter.audio_reopen = host_audio_reopen; adapter.audio_device_id = host_audio_device_id;
      adapter.audio_ratio = host_audio_ratio;   /* 1.7.7 (HOST_KIT D30): Sync to display */
      adapter.state_ready = s_state_ready; adapter.state_file = s_state_file; adapter.state_path = s_state_path;
      adapter.input_frame = s_input_frame;
      /* Multiplayer (hostkit.h): an in-process snapshot for rollback and the digest (the state's body without the picture, hashed). */
      adapter.snap_bound = cv_snap_bound; adapter.snap_save = cv_snap_save; adapter.snap_load = cv_snap_load; adapter.digest = cv_snap_digest;
      adapter.help_lines = s_help_lines; adapter.help_controls = s_help_controls;
      adapter.event = s_event; adapter.action_held = s_action_held; adapter.before_present = s_before_present;
   }
   return &adapter;
}

/* ---- what the game calls ---- */
static bool cv_host_open(const char *title, int scale, const CvMachine *m) {
   RrhkMachine *adapter = (RrhkMachine *)rrhk_adapter();
   /* The pace of the frames: the board's lines (262 NTSC, 313 PAL). */
   adapter->frame_seconds = (double)CV_CYCLES_PER_LINE * m->lines_per_frame / CV_CPU_CLOCK;
   if (!rrhk_open(adapter, title, scale)) return false;
   rrhk_autofire_reset();
   host_audio_init(CV_AUDIO_RATE);
   rrhk_notice(rrhk_tr("F1: help | Y on a gamepad: keypad", "F1 : aide | Y sur une manette : pave"), 2400);
   return true;
}

/* The end of a guest frame: the picture and the sound out, the window's events and menus, the pads of the next frame in.
 * 0: go on; 1: quit; 2: reset. */
static int cv_host_frame(CvMachine *m) {
   if (!rrhk_session_silent()) s_picture(m);    /* a frame run again after a correction is never shown */
   s_sound(m);
   const bool running = rrhk_frame_done();
   sh.frame++;
   m->pad[0] = (uint16_t)(sh.pad[0] & CV_PAD_MASK);
   m->pad[1] = (uint16_t)(sh.pad[1] & CV_PAD_MASK);
   if (sh.reset) { sh.reset = false; audio_output_clear(); return 2; }
   return running ? 0 : 1;
}

static void cv_host_close(void) {
   host_audio_shutdown();
   rrhk_close();
   SDL_Quit();
}
