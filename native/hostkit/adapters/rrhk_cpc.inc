/* Amstrad CPC adapter for the host kit (docs/HOST_KIT.md; a computer, like the MSX, the X68000, the Amiga and the Atari ST).
 * Original Retro-Recomp code, MIT.
 *
 * Included by native/cpc_machine/cpc_player.c, which owns the board (cpc_glue.inc), the boot key sequence (generated/boot_keys.h,
 * `rr_boot_keys`) and the frontend variables rrhk_computer.inc reads. The guest owns the loop: the game opens the window with
 * cpc_host_open and calls cpc_host_frame at the end of each guest frame (RrhkMachine.driven, as the MSX). What the computers
 * share comes from rrhk_computer.inc, its text unchanged; what is the CPC's stays here (rules reviewed by the lead, 21 Nov 2026):
 *
 * - joystick 1 on keyboard row 9 from player 1's pad, joystick 2 on row 6 from player 2's (shared with the keys 6 5 R T G F, as
 *   on the machine: with no second pad nothing presses row 6); Fire 1 is the stick's fire 1 and SPACE, Start is SPACE, Select
 *   RETURN, the directions the CPC's cursor keys too (the pad's keyboard aliases);
 * - the keyboard at its positions on the host's (rrhk_cpc_keys.h): alone, every key the pad table does not bind, never a
 *   Ctrl+Alt chord, a function key Retro-Recomp keeps or Escape (two ESC break a BASIC program); with full typing (Ctrl+Alt+K)
 *   every key, Escape included; in a session the host's keys when it types, else the pad's aliases;
 * - the boot key sequence: while it runs (rrhk_boot_keys_frame at the board's emulated frame), the matrix is exactly its keys of
 *   the frame and every keyboard-derived input is ignored (the player's keys, the host's typing, the pad's aliases): only the
 *   joystick lines of rows 9 and 6 stay live.
 *
 * The picture is the board's 768 x 272 (48 characters of 16 mode-2 pixels), shown at the width of 384 mode-1 pixels; the sound
 * is the board's 44,100 Hz into the shared ring of native/audio_output.inc, mono as the built-in speaker by default, the headphone
 * jack's stereo as a row of F2's options page (c_sound). Quick states (F8/F9) are the game's,
 * saved and loaded at the frame's end, its service point. In a session the player gives the snapshots, the digest, the frame's
 * effects and the disk's save (cpc_session_save, _save_put, _begin, _save_commit). */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include "rrhk_boot_keys.h"
#include "rrhk_cpc_keys.h"
#include "hostkit/adapters/rrhk_text.h"
#include <math.h>

/* The four libretro mouse ids rrhk_computer.inc names (no mouse on these games: they only keep its code compiling). */
#ifndef RETRO_DEVICE_ID_MOUSE_X
#define RETRO_DEVICE_ID_MOUSE_X 0
#define RETRO_DEVICE_ID_MOUSE_Y 1
#define RETRO_DEVICE_ID_MOUSE_LEFT 2
#define RETRO_DEVICE_ID_MOUSE_RIGHT 3
#endif

/* The actions, in menu order; the bit of an action is 1 << its index. */
enum { C_UP, C_DOWN, C_LEFT, C_RIGHT, C_FIRE1, C_FIRE2, C_START, C_SELECT, C_PAUSE, C_ACTIONS };
#define C_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction c_actions[C_ACTIONS] = {
   {"Up", L"Up", 1u << C_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << C_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << C_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << C_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button 1", L"Fire 1", 1u << C_FIRE1, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_x},
   {"Button 2", L"Fire 2", 1u << C_FIRE2, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_w},
   {"Start (SPACE)", L"Start", 1u << C_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Select (RETURN)", L"Select", 1u << C_SELECT, RRHK_SYSTEM, 0, {SDL_SCANCODE_RSHIFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
   {"Pause", L"Pause", 1u << C_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {C_NO_PAD, C_NO_PAD}}};
#define C_BIT(action) (1u << (action))

#define RRC_UP C_UP
#define RRC_DOWN C_DOWN
#define RRC_LEFT C_LEFT
#define RRC_RIGHT C_RIGHT
#define RRC_BUTTON_A C_FIRE1
#define RRC_BUTTON_B C_FIRE2
#define RRC_START C_START
#define RRC_PAUSE C_PAUSE
#define RRC_BIT(action) C_BIT(action)
#define RRC_INI_SECTION L"CPC"
#define RRC_KEYBOARD_ON "Full CPC keyboard: ON (ESC sent to the CPC)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_UNKNOWN      /* the CPC's f0-f9 are the keypad's: F1-F12 stay Retro-Recomp's */
#define RRC_HELP_DISKS                                /* one disk a game for now: no disk key to list */
#include "hostkit/adapters/rrhk_computer.inc"

/* ---- the keyboard: a host key to the CPC key at its position (rrhk_cpc_keys.h), 0xFF for none ---- */
static uint8_t c_keymap[SDL_NUM_SCANCODES];
static bool c_keymap_ready;
static void c_keymap_build(void) {
   memset(c_keymap, 0xFF, sizeof c_keymap);
   for (unsigned i = 0; i < sizeof RRHK_CPC_KEYS / sizeof RRHK_CPC_KEYS[0]; i++)
      c_keymap[RRHK_CPC_KEYS[i].scancode] = RRHK_CPC_KEYS[i].cpc_key;
   c_keymap_ready = true;
}

static void c_press(uint8_t held[CPC_KEY_ROWS], unsigned key) {
   if (key < CPC_KEY_ROWS * 8) held[key >> 3] |= (uint8_t)(1u << (key & 7));
}

/* A scancode bound to an action of a player, which the guest does not see while the pad has the keyboard. */
static int c_bound(SDL_Scancode k) {
   const RrhkUi *ui = rrhk_ui();
   for (int p = 0; p < 2; p++) for (int a = 0; a < C_ACTIONS; a++) if (ui->keys[p][a] == k && k != SDL_SCANCODE_UNKNOWN) return 1;
   return 0;
}

/* The joystick lines of a pad word (CPC_JOY_* bits, a bit set: pressed). */
static uint8_t c_joystick(uint16_t pad) {
   return (uint8_t)(((pad & C_BIT(C_UP)) ? CPC_JOY_UP : 0) | ((pad & C_BIT(C_DOWN)) ? CPC_JOY_DOWN : 0) |
                    ((pad & C_BIT(C_LEFT)) ? CPC_JOY_LEFT : 0) | ((pad & C_BIT(C_RIGHT)) ? CPC_JOY_RIGHT : 0) |
                    ((pad & C_BIT(C_FIRE1)) ? CPC_JOY_FIRE1 : 0) | ((pad & C_BIT(C_FIRE2)) ? CPC_JOY_FIRE2 : 0));
}

/* The pad's keyboard aliases of player 1: the cursor keys, SPACE (Fire 1, Start), RETURN (Select). */
static void c_pad_keys(uint8_t held[CPC_KEY_ROWS], uint16_t pad) {
   if (pad & C_BIT(C_UP)) c_press(held, CPC_KEY_UP);
   if (pad & C_BIT(C_DOWN)) c_press(held, CPC_KEY_DOWN);
   if (pad & C_BIT(C_LEFT)) c_press(held, CPC_KEY_LEFT);
   if (pad & C_BIT(C_RIGHT)) c_press(held, CPC_KEY_RIGHT);
   if (pad & (C_BIT(C_FIRE1) | C_BIT(C_START))) c_press(held, CPC_KEY_SPACE);
   if (pad & C_BIT(C_SELECT)) c_press(held, CPC_KEY_RETURN);
}

/* Every key of a keyboard state through the positional table (the boot sequence, the host's typing, full typing). */
static void c_all_keys(uint8_t held[CPC_KEY_ROWS], const Uint8 *state) {
   for (int k = 0; k < SDL_NUM_SCANCODES; k++)
      if (state[k] && c_keymap[k] != 0xFF) c_press(held, c_keymap[k]);
}

/* The inputs of the frame to come, written on the board's PPI lines. */
static void c_inputs(CpcMachine *m) {
   static Uint8 boot_state[SDL_NUM_SCANCODES];
   uint8_t held[CPC_KEY_ROWS], joy1 = 0, joy2 = 0;
   SDL_Keymod mod = SDL_GetModState();
   memset(held, 0, sizeof held);
   if (!c_keymap_ready) c_keymap_build();
   player_poll();
   const int live = rrc_session() || (!player_blocked() && input_focus);
   if (live) {
      joy1 = c_joystick(ca.pad[0]);
      joy2 = c_joystick(ca.pad[1]);
   }
   if (rrhk_boot_keys_frame(&rr_boot_keys, (uint32_t)m->frames, boot_state)) {
      /* The boot key sequence owns the keyboard: its keys only, nothing keyboard-derived of the player's or the host's. */
      c_all_keys(held, boot_state);
   } else if (rrc_session()) {
      /* A match: the frame's words and the host's keys only, the same on every seat (session ABI 9). */
      if (guest_keyboard) c_all_keys(held, keys);
      else c_pad_keys(held, ca.pad[0]);
   } else if (live) {
      if (keys && !((mod & KMOD_CTRL) && (mod & KMOD_ALT))) {
         for (int k = 0; k < SDL_NUM_SCANCODES; k++) {
            if (!keys[k] || c_keymap[k] == 0xFF) continue;
            if (k >= SDL_SCANCODE_F1 && k <= SDL_SCANCODE_F12 && player_host_fkey(k, mod)) continue;
            if (!guest_keyboard && (c_bound((SDL_Scancode)k) || k == SDL_SCANCODE_ESCAPE)) continue;
            c_press(held, c_keymap[k]);
         }
      }
      if (!guest_keyboard) c_pad_keys(held, ca.pad[0]);
   }
   memcpy(m->ppi.keys, held, sizeof held);
   m->ppi.joystick[0] = joy1;
   m->ppi.joystick[1] = joy2;
}

/* ---- the picture: the board's 768 x 272, opaque ---- */
static uint32_t c_view[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static void c_picture(const uint32_t *picture) {
   for (unsigned i = 0; i < CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT; i++) c_view[i] = 0xFF000000u | picture[i];
}

/* ---- the sound: the board's stereo 44.1 kHz into the shared ring ---- */
static SDL_AudioDeviceID audio_device;
static void audio_output_clear(void);
#define RR_HOST_AUDIO_FILTER rrhk_options_audio
#define RR_HOST_AUDIO_RESET rrhk_options_audio_reset
#define RR_HOST_AUDIO_DEVICE rrhk_audio_device
#define RR_HOST_AUDIO_HELD rrhk_audio_held
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
#include "audio_output.inc"

/* ---- the sound's output: the built-in speaker (mono, the default) or the headphone jack (stereo), the player's choice ----
 * The board gives the jack's stereo (A left, C right, B half on each side). Most CPC games were written for the built-in speaker,
 * which plays the three voices together: the default is that mono, (left + right) / 2 = (A + B + C) / 2 on both sides; the
 * stereo of the jack is a row on F2's options page, kept per game in sound.cfg beside player.cfg (« output=stereo »). Only what this
 * PC hears changes: the board, its states and the multiplayer digest are the same either way. */
#define C_ROW_SOUND (SDL_NUM_SCANCODES + 2)     /* the row's key: past the computers' keyboard row (+1), before the kit's own (+16) */
static bool c_stereo;

/* The adapter's texts in the five game languages (rrhk_text.h: en, fr, it, es, de; ASCII, as the games write them). */
static const RrhkText c_sound_row = {"Sound: %s", "Son : %s", "Audio: %s", "Sonido: %s", "Ton: %s"};
static const RrhkText c_sound_mono = {"mono (built-in speaker)", "mono (haut-parleur)", "mono (altoparlante)", "mono (altavoz)",
                                      "Mono (Lautsprecher)"};
static const RrhkText c_sound_stereo = {"stereo (headphone jack)", "stereo (prise casque)", "stereo (cuffie)", "estereo (auriculares)",
                                        "Stereo (Kopfhoerer)"};
static const char *c_sound_value(void) { return rrhk_text(c_stereo ? &c_sound_stereo : &c_sound_mono); }

/* sound.cfg beside player.cfg (its folder: player_config without "player.cfg"). */
static bool c_sound_path(wchar_t *wide, size_t capacity) {
   char path[1100];
   const char *slash = strrchr(player_config, '/');
   const size_t folder = slash ? (size_t)(slash - player_config) + 1 : 0;
   if (folder + 10 >= sizeof path) return false;
   memcpy(path, player_config, folder);
   strcpy(path + folder, "sound.cfg");
   return rr_from_utf8(path, wide, capacity) != 0;
}
static void c_sound_load(void) {
   wchar_t wide[1100];
   char line[32] = "";
   FILE *f;
   c_stereo = false;
   if (!c_sound_path(wide, 1100) || !(f = rr_fopen(wide, L"rb"))) return;
   if (fgets(line, sizeof line, f)) c_stereo = !strncmp(line, "output=stereo", 13);
   fclose(f);
}
static void c_sound_save(void) {
   wchar_t wide[1100];
   FILE *f;
   if (!c_sound_path(wide, 1100) || !(f = rr_fopen(wide, L"wb"))) return;
   fputs(c_stereo ? "output=stereo\n" : "output=mono\n", f);
   fclose(f);
}

static void c_sound(CpcMachine *m) {
   static int16_t stereo[2 * CPC_AUDIO_BUFFER];
   uint32_t n = cpc_audio_take(m, stereo, CPC_AUDIO_BUFFER);
   if (fast_forward) return;                     /* frames faster than the sound: the samples are dropped, not queued */
   if (rrhk_session_silent()) return;           /* a frame run again after a multiplayer correction: no sound */
   if (!c_stereo)
      for (uint32_t i = 0; i < n; ++i) {
         const int16_t mono = (int16_t)(((int32_t)stereo[2 * i] + stereo[2 * i + 1]) / 2);
         stereo[2 * i] = stereo[2 * i + 1] = mono;
      }
   host_audio_submit(stereo, n);
}

static void c_option_rows(int slot, RrhkOptionRows *rows) {
   x_option_rows(slot, rows);
   if (slot == 1) rrhk_option_row_icon(rows, C_ROW_SOUND, RR_ICON_ROW_HEADPHONES, rrhk_text(&c_sound_row), c_sound_value());
}
static bool c_key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
   char plate[96];
   if ((int)key != C_ROW_SOUND) return x_key_event(ui, key, running);
   c_stereo = !c_stereo;
   c_sound_save();
   snprintf(plate, sizeof plate, rrhk_text(&c_sound_row), c_sound_value());
   rrhk_notice(plate, 2500);
   return true;
}

/* ---- the machine table ---- */
static struct { bool reset; uint64_t frame; } ch;

static int c_players(void) { return 2; }
static bool c_run_frame(uint16_t p1, uint16_t p2) { ca.pad[0] = p1; ca.pad[1] = p2; fast_forward = x_fast_forward(); return true; }
static void c_pause(bool paused) {
   static bool was;
   if (paused == was) return;
   was = paused;
   audio_output_clear();
}
static void c_reset(void) { ch.reset = true; }
static const uint32_t *c_pixels(void) { return c_view; }
static int c_width(void) { return CPC_SCREEN_WIDTH; }
static int c_height(void) { return CPC_SCREEN_HEIGHT; }
/* Mode-1 pixels are about square on a CPC monitor: the 768 mode-2 points are shown 384 wide. */
static int c_display_width(void) { return CPC_SCREEN_WIDTH / 2; }
static size_t c_no_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t c_zero(void) { return 0; }
static uint64_t c_interpreted(void) { return banked_fallback_steps; }
static uint64_t c_input_frame(void) { return ch.frame; }
static bool c_state_ready(void) { return true; }
static bool c_state_file(const wchar_t *path, bool load) { return cpc_game_state_file(path, load); }
static bool c_state_path(wchar_t *path, size_t capacity) { return cpc_game_state_path(path, capacity); }

static void c_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, rrhk_tr("Arrows: joystick 1; D: fire 1 (and SPACE), S: fire 2; player 2's pad: keys 6 5 R T G F",
                                  "Fleches : manette 1 ; D : tir 1 (et ESPACE), S : tir 2 ; manette 2 : touches 6 5 R T G F"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter: SPACE; right Shift: RETURN; Ctrl+Alt+K: the CPC keyboard (and ESC)",
                                                 "Entree : ESPACE ; Maj droite : RETURN ; Ctrl+Alt+K : le clavier CPC (et ESC)"));
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine_table;
   if (!machine_table.actions) {
      RrhkMachine *t = &machine_table;
      memset(t, 0, sizeof *t);
      t->ini_section = L"CPC"; t->console_name = "Amstrad CPC";
      t->table_players = 2; t->players = c_players;
      t->actions = c_actions; t->action_count = C_ACTIONS;
      t->up = C_UP; t->down = C_DOWN; t->left = C_LEFT; t->right = C_RIGHT; t->start = C_START;
      t->max_width = CPC_SCREEN_WIDTH; t->max_height = CPC_SCREEN_HEIGHT;
      t->frame_seconds = 64.0 * 312.0 / 1000000.0;              /* the firmware's screen: 312 lines of 64 us */
      t->own_audio = true; t->driven = true; t->state_deferred = false;
      t->video_section = L"CPC"; t->autofire_section = L"CPC"; t->indexed_bindings = true; t->bindings_clearable = true;
      t->machine_fkeys = 0;
      t->reset = c_reset; t->run_frame = c_run_frame; t->pause = c_pause;
      t->pixels = c_pixels; t->visible_width = c_width; t->visible_height = c_height; t->raster_height = c_height;
      t->display_width = c_display_width;
      t->audio = c_no_audio; t->interpreted = c_interpreted; t->audio_interpreted = c_zero;
      t->audio_reopen = host_audio_reopen; t->audio_device_id = host_audio_device_id;
      t->audio_ratio = host_audio_ratio;
      t->state_ready = c_state_ready; t->state_file = c_state_file; t->state_path = c_state_path;
      /* Multiplayer: the game's in-process snapshots, its digest (the board's, with the boot sequence's frame), its effects. */
      t->snap_bound = cpc_snap_bound; t->snap_save = cpc_snap_save; t->snap_load = cpc_snap_load;
      t->digest = cpc_snap_digest; t->side_effects = cpc_side_effects;
      /* The disk's save in a match: the host's disk A travels to every seat, played in memory, written back at a clean end. */
      t->session_save = cpc_session_save; t->session_save_put = cpc_session_save_put;
      t->session_begin = cpc_session_begin; t->session_save_commit = cpc_session_save_commit;
      t->session_keys = x_session_keys;
      t->input_frame = c_input_frame;
      t->settings_loaded = x_settings_loaded; t->help_lines = x_help_lines; t->help_controls = c_help_controls;
      t->option_rows = c_option_rows; t->key_event = c_key_event;   /* the computers' keyboard row, then the sound's output */
      t->frame_start = x_frame_start; t->finished = x_finished;
      t->event = x_event; t->keyboard_pad = x_keyboard_pad; t->fast_forward = x_fast_forward; t->game_rect = x_game_rect;
      t->help_page = x_help_page; t->action_held = x_action_held;
   }
   return &machine_table;
}

/* ---- what the game calls ---- */
static bool cpc_host_open(const char *title, int scale) {
   RrhkMachine *table = (RrhkMachine *)rrhk_adapter();
   /* The window's whole-pixel scale counts mode-1 pixels, as the MSX2's counts its half-pixels in pairs. */
   width = CPC_SCREEN_WIDTH / 2; height = CPC_SCREEN_HEIGHT;
   ca.windowed = true;
   if (!rrhk_open(table, title, scale)) return false;
   rrhk_autofire_reset();
   host_audio_init(CPC_AUDIO_RATE);
   c_sound_load();                              /* the player's sound output for this game: mono unless sound.cfg says stereo */
   rrhk_notice(rrhk_tr("F1: help | Ctrl+Alt+K: CPC keyboard", "F1 : aide | Ctrl+Alt+K : clavier CPC"), 2400);
   return true;
}

/* The end of a guest frame: the picture and the sound out, the window's events and menus, the inputs of the next frame in.
 * 0: go on; 1: quit; 2: reset. */
static int cpc_host_frame(CpcMachine *m) {
   if (!rrhk_session_silent()) c_picture(m->picture);
   c_sound(m);
   const bool running = rrhk_frame_done();
   ch.frame++;
   c_inputs(m);
   if (ch.reset) { ch.reset = false; audio_output_clear(); return 2; }
   return running ? 0 : 1;
}

static void cpc_host_close(void) {
   host_audio_shutdown();
   rrhk_close();
   SDL_Quit();
}
