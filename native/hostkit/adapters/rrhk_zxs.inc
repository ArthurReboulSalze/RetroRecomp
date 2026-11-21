/* ZX Spectrum adapter for the host kit (docs/HOST_KIT.md; a computer, like the MSX). Original Retro-Recomp code, MIT.
 *
 * Included by native/zxs_machine/zxs_player.c, which owns the machine (zxs_glue.inc) and defines the frontend variables that
 * rrhk_computer.inc reads. The guest owns the loop (the translated Z80 code runs until a frame ends): the game opens the window
 * with zxs_host_open and calls zxs_host_frame at the end of each guest frame (RrhkMachine.driven, as the MSX). What the computers
 * share (the guest keyboard with Ctrl+Alt+K and its chords, the function keys, the second help page, the window preferences)
 * comes from rrhk_computer.inc, unchanged; what is the Spectrum's stays here: the 40-key keyboard by half-rows, the pads on the
 * joystick interface the snapshot was saved for, the 320 x 240 picture of colour indices with the Spectrum's sixteen colours,
 * the sound (beeper and, on the 128K, the AY) through the shared stereo ring of native/audio_output.inc. Quick states (F8/F9)
 * are the game's (zxs_player.c), saved and loaded at once: the kit calls them from the frame's end, which is already the game's
 * service point. Guest state is never filtered. Multiplayer (snapshots, digest, session saves) is not offered yet: step 3. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
/* The shared headers and the computers' part hold helpers a computer may not need (the Spectrum has no mouse, no drive): their
 * unused static functions are not this adapter's warnings. */
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "display_settings.h"
#include <math.h>

/* The four libretro mouse ids rrhk_computer.inc names (a Spectrum game here has no mouse: they only keep its code compiling). */
#ifndef RETRO_DEVICE_ID_MOUSE_X
#define RETRO_DEVICE_ID_MOUSE_X 0
#define RETRO_DEVICE_ID_MOUSE_Y 1
#define RETRO_DEVICE_ID_MOUSE_LEFT 2
#define RETRO_DEVICE_ID_MOUSE_RIGHT 3
#endif

/* The actions, in menu order; the bit of an action is 1 << its index. A Spectrum joystick has one fire button: Fire 2 is the
 * same button (a second pad button, its own autofire). Start is the Spectrum's ENTER, Select its SPACE. */
enum { Z_UP, Z_DOWN, Z_LEFT, Z_RIGHT, Z_FIRE, Z_FIRE2, Z_START, Z_SELECT, Z_PAUSE, Z_ACTIONS };
#define Z_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction z_actions[Z_ACTIONS] = {
   {"Up", L"Up", 1u << Z_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << Z_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << Z_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << Z_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Fire", L"Fire", 1u << Z_FIRE, RRHK_FACE, 0, {SDL_SCANCODE_RCTRL, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_x},
   {"Fire 2", L"Fire 2", 1u << Z_FIRE2, RRHK_FACE, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_w},
   {"Start (ENTER)", L"Start", 1u << Z_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Select (SPACE)", L"Select", 1u << Z_SELECT, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
   {"Pause", L"Pause", 1u << Z_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {Z_NO_PAD, Z_NO_PAD}}};
#define Z_BIT(action) (1u << (action))

#define RRC_UP Z_UP
#define RRC_DOWN Z_DOWN
#define RRC_LEFT Z_LEFT
#define RRC_RIGHT Z_RIGHT
#define RRC_BUTTON_A Z_FIRE
#define RRC_BUTTON_B Z_FIRE2
#define RRC_START Z_START
#define RRC_PAUSE Z_PAUSE
#define RRC_BIT(action) Z_BIT(action)
#define RRC_INI_SECTION L"ZXSpectrum"
#define RRC_KEYBOARD_ON "Full Spectrum keyboard: ON"
#define RRC_GUEST_FKEY_LAST ((int)SDL_SCANCODE_F1 - 1)   /* the Spectrum has no function key: they all stay Retro-Recomp's */
#define RRC_HELP_DISKS
#include "hostkit/adapters/rrhk_computer.inc"
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic pop
#endif

/* ---- the keyboard: the eight half-rows (zxs_machine.h keys[]), bit 0 the outer key of each row ----
 *   0 FEFE: CAPS SHIFT Z X C V      1 FDFE: A S D F G       2 FBFE: Q W E R T        3 F7FE: 1 2 3 4 5
 *   4 EFFE: 0 9 8 7 6               5 DFFE: P O I U Y       6 BFFE: ENTER L K J H    7 7FFE: SPACE SYMBOL-SHIFT M N B */
#define Z_KEY(row, bit) ((uint8_t)((row) << 3 | (bit)))
enum { Z_CAPS = Z_KEY(0, 0), Z_SYMBOL = Z_KEY(7, 1), Z_ENTER = Z_KEY(6, 0), Z_SPACE = Z_KEY(7, 0), Z_NONE = 0xFF };

/* The Spectrum keys of an SDL scancode, at most two (a host key that stands for a shifted Spectrum key): Shift is CAPS SHIFT,
 * Ctrl is SYMBOL SHIFT, Backspace is CAPS SHIFT + 0 (DELETE) and the arrows CAPS SHIFT + 5 6 7 8, as the Spectrum's own
 * cursor keys. 0 when the key is not the Spectrum's. */
static int z_keys_of(SDL_Scancode k, uint8_t out[2]) {
   static const struct { SDL_Scancode scan; uint8_t a, b; } map[] = {
      {SDL_SCANCODE_LSHIFT, Z_CAPS, Z_NONE}, {SDL_SCANCODE_RSHIFT, Z_CAPS, Z_NONE},
      {SDL_SCANCODE_LCTRL, Z_SYMBOL, Z_NONE}, {SDL_SCANCODE_RCTRL, Z_SYMBOL, Z_NONE},
      {SDL_SCANCODE_RETURN, Z_ENTER, Z_NONE}, {SDL_SCANCODE_KP_ENTER, Z_ENTER, Z_NONE}, {SDL_SCANCODE_SPACE, Z_SPACE, Z_NONE},
      {SDL_SCANCODE_BACKSPACE, Z_CAPS, Z_KEY(4, 0)},
      {SDL_SCANCODE_LEFT, Z_CAPS, Z_KEY(3, 4)}, {SDL_SCANCODE_DOWN, Z_CAPS, Z_KEY(4, 4)},
      {SDL_SCANCODE_UP, Z_CAPS, Z_KEY(4, 3)}, {SDL_SCANCODE_RIGHT, Z_CAPS, Z_KEY(4, 2)}};
   /* The letters by their row and place (A..Z), the digits 1-5 and 6-0. */
   static const uint8_t letters[26] = {
      Z_KEY(1, 0), Z_KEY(7, 4), Z_KEY(0, 3), Z_KEY(1, 2), Z_KEY(2, 2), Z_KEY(1, 3), Z_KEY(1, 4), Z_KEY(6, 4), Z_KEY(5, 2),
      Z_KEY(6, 3), Z_KEY(6, 2), Z_KEY(6, 1), Z_KEY(7, 2), Z_KEY(7, 3), Z_KEY(5, 1), Z_KEY(5, 0), Z_KEY(2, 0), Z_KEY(2, 3),
      Z_KEY(1, 1), Z_KEY(2, 4), Z_KEY(5, 3), Z_KEY(0, 4), Z_KEY(2, 1), Z_KEY(0, 2), Z_KEY(5, 4), Z_KEY(0, 1)};
   out[1] = Z_NONE;
   if (k >= SDL_SCANCODE_A && k <= SDL_SCANCODE_Z) { out[0] = letters[k - SDL_SCANCODE_A]; return 1; }
   if (k >= SDL_SCANCODE_1 && k <= SDL_SCANCODE_5) { out[0] = Z_KEY(3, k - SDL_SCANCODE_1); return 1; }
   if (k >= SDL_SCANCODE_6 && k <= SDL_SCANCODE_9) { out[0] = Z_KEY(4, 4 - (k - SDL_SCANCODE_6)); return 1; }
   if (k == SDL_SCANCODE_0) { out[0] = Z_KEY(4, 0); return 1; }
   for (unsigned n = 0; n < sizeof map / sizeof map[0]; n++)
      if (map[n].scan == k) { out[0] = map[n].a; out[1] = map[n].b; return 1; }
   return 0;
}

static void z_press(uint8_t held[8], uint8_t key) { if (key != Z_NONE) held[key >> 3] |= (uint8_t)(1u << (key & 7)); }

/* ---- the pads: player 1 on the joystick interface the snapshot was saved for (its joystick byte, image byte 6), player 2 on the
 * Interface 2 keys player 1 does not use. THE ONE TABLE of this mapping: retrorecomp/zxs_routes.py (PAD_KEYS, KEMPSTON_BIT)
 * drives the conversion's routes through exactly these keys, so a change here is a change there. ---- */
enum { Z_PAD_CURSOR, Z_PAD_KEMPSTON, Z_PAD_SINCLAIR_LEFT, Z_PAD_SINCLAIR_RIGHT };
/* The keys of a key-based interface: left, right, down, up, fire. */
static const uint8_t z_pad_keys[4][5] = {
   [Z_PAD_CURSOR] = {Z_KEY(3, 4), Z_KEY(4, 2), Z_KEY(4, 4), Z_KEY(4, 3), Z_KEY(4, 0)},            /* 5 8 6 7 and 0 */
   [Z_PAD_SINCLAIR_LEFT] = {Z_KEY(3, 0), Z_KEY(3, 1), Z_KEY(3, 2), Z_KEY(3, 3), Z_KEY(3, 4)},     /* 1 2 3 4 5 */
   [Z_PAD_SINCLAIR_RIGHT] = {Z_KEY(4, 4), Z_KEY(4, 3), Z_KEY(4, 2), Z_KEY(4, 1), Z_KEY(4, 0)}};   /* 6 7 8 9 0 */
/* The Kempston port's bits (active high): right, left, down, up, fire. */
enum { Z_KEMPSTON_RIGHT = 0x01, Z_KEMPSTON_LEFT = 0x02, Z_KEMPSTON_DOWN = 0x04, Z_KEMPSTON_UP = 0x08, Z_KEMPSTON_FIRE = 0x10 };
static int z_pad1 = Z_PAD_CURSOR, z_pad2 = Z_PAD_SINCLAIR_RIGHT;

/* The interfaces from the image's joystick byte (0 cursor, 1 Kempston, 2 Sinclair 2 left, 3 Sinclair 2 right; FFh, a .sna that
 * does not say: cursor). Player 2 is on the Interface 2 keys player 1 shares least: 6-0, or 1-5 when player 1 is on 6-0 or on the
 * cursor keys (5-8 and 0, which share 6, 7, 8 and 0 with 6-0 but only 5 with 1-5). */
static void z_pads_from_image(uint8_t joystick) {
   z_pad1 = joystick <= Z_PAD_SINCLAIR_RIGHT ? joystick : Z_PAD_CURSOR;
   z_pad2 = z_pad1 == Z_PAD_SINCLAIR_RIGHT || z_pad1 == Z_PAD_CURSOR ? Z_PAD_SINCLAIR_LEFT : Z_PAD_SINCLAIR_RIGHT;
}

static uint8_t z_kempston(uint16_t pad) {
   return (uint8_t)(((pad & Z_BIT(Z_RIGHT)) ? Z_KEMPSTON_RIGHT : 0) | ((pad & Z_BIT(Z_LEFT)) ? Z_KEMPSTON_LEFT : 0) |
                    ((pad & Z_BIT(Z_DOWN)) ? Z_KEMPSTON_DOWN : 0) | ((pad & Z_BIT(Z_UP)) ? Z_KEMPSTON_UP : 0) |
                    ((pad & (Z_BIT(Z_FIRE) | Z_BIT(Z_FIRE2))) ? Z_KEMPSTON_FIRE : 0));
}

/* A pad word on a key-based interface, and its Start (ENTER) and Select (SPACE). */
static void z_pad_on_keys(uint8_t held[8], int kind, uint16_t pad) {
   const uint8_t *k = z_pad_keys[kind];
   if (pad & Z_BIT(Z_LEFT)) z_press(held, k[0]);
   if (pad & Z_BIT(Z_RIGHT)) z_press(held, k[1]);
   if (pad & Z_BIT(Z_DOWN)) z_press(held, k[2]);
   if (pad & Z_BIT(Z_UP)) z_press(held, k[3]);
   if (pad & (Z_BIT(Z_FIRE) | Z_BIT(Z_FIRE2))) z_press(held, k[4]);
}
static void z_pad_system(uint8_t held[8], uint16_t pad) {
   if (pad & Z_BIT(Z_START)) z_press(held, Z_ENTER);
   if (pad & Z_BIT(Z_SELECT)) z_press(held, Z_SPACE);
}

/* A scancode bound to an action of a player, which the guest does not see while the pad has the keyboard. */
static int z_bound(SDL_Scancode k) {
   const RrhkUi *ui = rrhk_ui();
   for (int p = 0; p < 2; p++) for (int a = 0; a < Z_ACTIONS; a++) if (ui->keys[p][a] == k && k != SDL_SCANCODE_UNKNOWN) return 1;
   return 0;
}

/* The inputs of the frame to come: the pads from the kit's pad words, the keyboard (every key with full typing, else the keys
 * no binding takes; never a Ctrl+Alt chord, never a function key, never Escape). */
static void z_inputs(ZxsMachine *m) {
   uint8_t held[8];
   uint8_t kempston = 0;
   SDL_Keymod mod = SDL_GetModState();
   memset(held, 0, sizeof held);
   player_poll();
   const bool session = rrc_session();
   if (session || (!player_blocked() && input_focus)) {
      const uint16_t pad1 = ca.pad[0], pad2 = ca.pad[1];
      if (z_pad1 == Z_PAD_KEMPSTON) kempston = z_kempston(pad1);
      else z_pad_on_keys(held, z_pad1, pad1);
      z_pad_on_keys(held, z_pad2, pad2);
      z_pad_system(held, pad1);
      z_pad_system(held, pad2);
      if (keys && (session ? guest_keyboard : !((mod & KMOD_CTRL) && (mod & KMOD_ALT)))) {
         for (int k = 0; k < SDL_NUM_SCANCODES; k++) {
            uint8_t spectrum[2];
            if (!keys[k] || !z_keys_of((SDL_Scancode)k, spectrum)) continue;
            if (!session && !guest_keyboard && z_bound((SDL_Scancode)k)) continue;
            z_press(held, spectrum[0]);
            z_press(held, spectrum[1]);
         }
      }
   }
   for (int row = 0; row < 8; row++) m->keys[row] = (uint8_t)(0xFF & ~held[row]);
   m->kempston = kempston;
}

/* ---- the picture: the machine's 320 x 240 colour indices (the 256 x 192 paper and its border) ---- */
static uint32_t z_view[ZXS_HEIGHT * ZXS_WIDTH];
/* The sixteen colours: index bit 0 blue, bit 1 red, bit 2 green, bit 3 bright; a component is D7h, FFh when bright (the levels
 * commonly published for the ULA's output; not measured on a set). Bright black is black. */
static uint32_t z_palette[16];
static void z_palette_fill(void) {
   for (unsigned c = 0; c < 16; c++) {
      const uint32_t level = (c & 8) ? 0xFF : 0xD7;
      z_palette[c] = 0xFF000000u | ((c & 2) ? level << 16 : 0) | ((c & 4) ? level << 8 : 0) | ((c & 1) ? level : 0);
   }
}

static void z_picture(const ZxsMachine *m) {
   const uint8_t *in = &m->picture[0][0];
   for (unsigned i = 0; i < ZXS_WIDTH * ZXS_HEIGHT; i++) z_view[i] = z_palette[in[i] & 15];
}

/* ---- the sound: mono 44.1 kHz from the machine, doubled into the stereo ring (the MSX's output) ---- */
static SDL_AudioDeviceID audio_device;
static void audio_output_clear(void);
#define RR_HOST_AUDIO_FILTER rrhk_options_audio
#define RR_HOST_AUDIO_RESET rrhk_options_audio_reset
#define RR_HOST_AUDIO_DEVICE rrhk_audio_device
#define RR_HOST_AUDIO_HELD rrhk_audio_held
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
#include "audio_output.inc"

static void z_sound(ZxsMachine *m) {
   static int16_t mono[ZXS_AUDIO_BUFFER], stereo[2 * ZXS_AUDIO_BUFFER];
   unsigned n = zxs_audio_take(m, mono, ZXS_AUDIO_BUFFER);
   if (fast_forward) return;                     /* frames faster than the sound: the samples are dropped, not queued */
   for (unsigned i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
   host_audio_submit(stereo, n);
}

/* ---- the machine table ---- */
static struct { bool reset; uint64_t frame; } zh;

static int z_players(void) { return 2; }
static bool z_run_frame(uint16_t p1, uint16_t p2) { ca.pad[0] = p1; ca.pad[1] = p2; fast_forward = x_fast_forward(); return true; }
/* The shell calls this at every frame start: only a change empties the ring (the sound held before a pause is not played after
 * it). */
static void z_pause(bool paused) {
   static bool was;
   if (paused == was) return;
   was = paused;
   audio_output_clear();
}
/* The guest owns the loop: a reset is a request the game takes at the end of the frame (zxs_host_frame returns 2). */
static void z_reset(void) { zh.reset = true; }
static const uint32_t *z_pixels(void) { return z_view; }
static int z_width(void) { return ZXS_WIDTH; }
static int z_height(void) { return ZXS_HEIGHT; }
/* 320 x 240 shown at 4:3: square pixels. */
static int z_display_width(void) { return ZXS_WIDTH; }
static size_t z_no_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t z_zero(void) { return 0; }
static uint64_t z_interpreted(void) { return banked_fallback_steps; }
static uint64_t z_input_frame(void) { return zh.frame; }
static bool z_state_ready(void) { return true; }
static bool z_state_file(const wchar_t *path, bool load) { return zxs_game_state_file(path, load); }
static bool z_state_path(wchar_t *path, size_t capacity) { return zxs_game_state_path(path, capacity); }

static void z_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, z_pad1 == Z_PAD_KEMPSTON
                  ? rrhk_tr("Arrows: Kempston joystick; right Ctrl: fire", "Fleches : manette Kempston ; Ctrl droit : tir")
                  : z_pad1 == Z_PAD_CURSOR
                  ? rrhk_tr("Arrows: cursor joystick (5 6 7 8, 0 fire); right Ctrl: fire",
                            "Fleches : manette curseur (5 6 7 8, 0 tir) ; Ctrl droit : tir")
                  : rrhk_tr("Arrows: Interface 2 joystick; right Ctrl: fire", "Fleches : manette Interface 2 ; Ctrl droit : tir"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter: ENTER; Shift: CAPS SHIFT; Ctrl: SYMBOL SHIFT; Ctrl+Alt+K: the keyboard",
                                                 "Entree : ENTER ; Maj : CAPS SHIFT ; Ctrl : SYMBOL SHIFT ; Ctrl+Alt+K : le clavier"));
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      memset(&machine, 0, sizeof machine);
      machine.ini_section = L"ZXSpectrum"; machine.console_name = "ZX Spectrum";
      machine.table_players = 2; machine.players = z_players;
      machine.actions = z_actions; machine.action_count = Z_ACTIONS;
      machine.up = Z_UP; machine.down = Z_DOWN; machine.left = Z_LEFT; machine.right = Z_RIGHT; machine.start = Z_START;
      machine.max_width = ZXS_WIDTH; machine.max_height = ZXS_HEIGHT;
      machine.frame_seconds = 69888.0 / 3500000.0;            /* the 48K's frame; zxs_host_open sets the model's */
      machine.own_audio = true; machine.driven = true; machine.state_deferred = false;
      machine.video_section = L"ZXSpectrum"; machine.autofire_section = L"ZXSpectrum"; machine.indexed_bindings = true;
      machine.bindings_clearable = true;
      machine.machine_fkeys = 0;
      machine.reset = z_reset; machine.run_frame = z_run_frame; machine.pause = z_pause;
      machine.pixels = z_pixels; machine.visible_width = z_width; machine.visible_height = z_height; machine.raster_height = z_height;
      machine.display_width = z_display_width;
      machine.audio = z_no_audio; machine.interpreted = z_interpreted; machine.audio_interpreted = z_zero;
      machine.audio_reopen = host_audio_reopen; machine.audio_device_id = host_audio_device_id;
      machine.audio_ratio = host_audio_ratio;
      machine.state_ready = z_state_ready; machine.state_file = z_state_file; machine.state_path = z_state_path;
      /* Multiplayer (snap_bound / snap_save / snap_load, digest, side_effects, session_*): left NULL until step 3; without a
       * digest the game is not offered in multiplayer. */
      machine.input_frame = z_input_frame;
      machine.settings_loaded = x_settings_loaded; machine.help_lines = x_help_lines; machine.help_controls = z_help_controls;
      machine.option_rows = x_option_rows; machine.key_event = x_key_event;
      machine.frame_start = x_frame_start; machine.finished = x_finished;
      machine.event = x_event; machine.keyboard_pad = x_keyboard_pad; machine.fast_forward = x_fast_forward; machine.game_rect = x_game_rect;
      machine.help_page = x_help_page; machine.action_held = x_action_held;
   }
   return &machine;
}

/* ---- what the game calls ---- */
static bool zxs_host_open(const char *title, int scale, const ZxsMachine *m, uint8_t joystick) {
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   machine->frame_seconds = (double)m->t_frame / m->clock_hz;   /* 69,888 T at 3.5 MHz (48K), 70,908 at 3.5469 MHz (128K) */
   z_pads_from_image(joystick);
   z_palette_fill();
   width = ZXS_WIDTH; height = ZXS_HEIGHT;
   ca.windowed = true;
   if (!rrhk_open(machine, title, scale)) return false;
   rrhk_autofire_reset();
   host_audio_init(ZXS_AUDIO_RATE);
   rrhk_notice(rrhk_tr("F1: help | Ctrl+Alt+K: Spectrum keyboard", "F1 : aide | Ctrl+Alt+K : clavier Spectrum"), 2400);
   return true;
}

/* The end of a guest frame: the picture and the sound out, the window's events and menus, the inputs of the next frame in.
 * 0: go on; 1: quit; 2: reset. */
static int zxs_host_frame(ZxsMachine *m) {
   z_picture(m);
   z_sound(m);
   const bool running = rrhk_frame_done();
   zh.frame++;
   z_inputs(m);
   if (want_swap || want_eject) want_swap = want_eject = false;   /* no drives: the computers' disk keys do nothing */
   if (zh.reset) { zh.reset = false; audio_output_clear(); return 2; }
   return running ? 0 : 1;
}

static void zxs_host_close(void) {
   host_audio_shutdown();
   rrhk_close();
   SDL_Quit();
}
