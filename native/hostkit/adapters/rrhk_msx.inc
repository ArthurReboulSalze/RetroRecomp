/* MSX adapter for the host kit (docs/HOST_KIT.md; a computer, like the X68000, the Amiga and the Atari ST). Original
 * Retro-Recomp code, MIT.
 *
 * Included by native/msx_machine/msx_player.c, which owns the machine (msx_glue.inc) and defines the frontend variables that
 * rrhk_computer.inc reads. The guest owns the loop (the translated Z80 code runs until a frame ends): the game opens the window
 * with msx_host_open and calls msx_host_frame at the end of each guest frame (RrhkMachine.driven, as the Master System). What
 * the computers share (the guest keyboard with Ctrl+Alt+K and its chords, the function keys, the second help page, the window
 * preferences) comes from rrhk_computer.inc, unchanged; what is the MSX's stays here: joystick 1 and 2 through the PSG, the
 * keyboard matrix, the TMS9918A or V9938 picture with its border (the machine says which chip it has), the sound (PSG, key click, SCC) through the shared stereo ring of
 * native/audio_output.inc. Quick states (F8/F9) are the game's (msx_state_file.inc), saved and loaded at once: the kit calls
 * them from the frame's end, which is already the game's service point. Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include <math.h>

/* The four libretro mouse ids rrhk_computer.inc names (an MSX game here has no mouse: they only keep its code compiling). */
#ifndef RETRO_DEVICE_ID_MOUSE_X
#define RETRO_DEVICE_ID_MOUSE_X 0
#define RETRO_DEVICE_ID_MOUSE_Y 1
#define RETRO_DEVICE_ID_MOUSE_LEFT 2
#define RETRO_DEVICE_ID_MOUSE_RIGHT 3
#endif

/* The actions, in menu order; the bit of an action is 1 << its index. The directions are joystick 1's and press the MSX cursor
 * keys too; trigger A also presses SPACE (the fire key of most keyboard games); Start is the MSX SPACE key, Select its F1. */
enum { M_UP, M_DOWN, M_LEFT, M_RIGHT, M_A, M_B, M_START, M_SELECT, M_PAUSE, M_ACTIONS };
#define M_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction m_actions[M_ACTIONS] = {
   {"Up", L"Up", 1u << M_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << M_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << M_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << M_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Trigger A", L"Trigger A", 1u << M_A, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
   {"Trigger B", L"Trigger B", 1u << M_B, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
   {"Start (SPACE)", L"Start", 1u << M_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Select (F1)", L"Select", 1u << M_SELECT, RRHK_SYSTEM, 0, {SDL_SCANCODE_RSHIFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
   {"Pause", L"Pause", 1u << M_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {M_NO_PAD, M_NO_PAD}}};
#define M_BIT(action) (1u << (action))

#define RRC_UP M_UP
#define RRC_DOWN M_DOWN
#define RRC_LEFT M_LEFT
#define RRC_RIGHT M_RIGHT
#define RRC_BUTTON_A M_A
#define RRC_BUTTON_B M_B
#define RRC_START M_START
#define RRC_PAUSE M_PAUSE
#define RRC_BIT(action) M_BIT(action)
#define RRC_INI_SECTION L"MSX"
#define RRC_KEYBOARD_ON "Full MSX keyboard: ON (F1-F5 sent to the MSX)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_F5
#define RRC_HELP_DISKS
#include "hostkit/adapters/rrhk_computer.inc"

/* ---- the keyboard matrix (international layout, as C-BIOS's): row and bit of an SDL scancode, -1 for none ---- */
static int m_matrix(SDL_Scancode k, int *row, int *bit) {
   static const struct { SDL_Scancode scan; signed char row, bit; } map[] = {
      {SDL_SCANCODE_MINUS, 1, 2}, {SDL_SCANCODE_EQUALS, 1, 3}, {SDL_SCANCODE_BACKSLASH, 1, 4}, {SDL_SCANCODE_LEFTBRACKET, 1, 5},
      {SDL_SCANCODE_RIGHTBRACKET, 1, 6}, {SDL_SCANCODE_SEMICOLON, 1, 7}, {SDL_SCANCODE_APOSTROPHE, 2, 0},
      {SDL_SCANCODE_GRAVE, 2, 1}, {SDL_SCANCODE_COMMA, 2, 2}, {SDL_SCANCODE_PERIOD, 2, 3}, {SDL_SCANCODE_SLASH, 2, 4},
      {SDL_SCANCODE_LSHIFT, 6, 0}, {SDL_SCANCODE_RSHIFT, 6, 0}, {SDL_SCANCODE_LCTRL, 6, 1}, {SDL_SCANCODE_RCTRL, 6, 1},
      {SDL_SCANCODE_LALT, 6, 2}, {SDL_SCANCODE_CAPSLOCK, 6, 3}, {SDL_SCANCODE_RALT, 6, 4},
      {SDL_SCANCODE_F1, 6, 5}, {SDL_SCANCODE_F2, 6, 6}, {SDL_SCANCODE_F3, 6, 7}, {SDL_SCANCODE_F4, 7, 0}, {SDL_SCANCODE_F5, 7, 1},
      {SDL_SCANCODE_ESCAPE, 7, 2}, {SDL_SCANCODE_TAB, 7, 3}, {SDL_SCANCODE_PAUSE, 7, 4}, {SDL_SCANCODE_BACKSPACE, 7, 5},
      {SDL_SCANCODE_END, 7, 6}, {SDL_SCANCODE_RETURN, 7, 7}, {SDL_SCANCODE_SPACE, 8, 0}, {SDL_SCANCODE_HOME, 8, 1},
      {SDL_SCANCODE_INSERT, 8, 2}, {SDL_SCANCODE_DELETE, 8, 3}, {SDL_SCANCODE_LEFT, 8, 4}, {SDL_SCANCODE_UP, 8, 5},
      {SDL_SCANCODE_DOWN, 8, 6}, {SDL_SCANCODE_RIGHT, 8, 7}};
   if (k >= SDL_SCANCODE_1 && k <= SDL_SCANCODE_9) { int digit = 1 + (int)(k - SDL_SCANCODE_1); *row = digit >> 3; *bit = digit & 7; return 1; }
   if (k == SDL_SCANCODE_0) { *row = 0; *bit = 0; return 1; }
   if (k >= SDL_SCANCODE_A && k <= SDL_SCANCODE_Z) { int letter = 6 + (int)(k - SDL_SCANCODE_A); *row = 2 + letter / 8; *bit = letter % 8; return 1; }
   for (unsigned n = 0; n < sizeof map / sizeof map[0]; n++)
      if (map[n].scan == k) { *row = map[n].row; *bit = map[n].bit; return 1; }
   return 0;
}

/* A scancode bound to an action of a player, which the guest does not see while the pad has the keyboard. */
static int m_bound(SDL_Scancode k) {
   const RrhkUi *ui = rrhk_ui();
   for (int p = 0; p < 2; p++) for (int a = 0; a < M_ACTIONS; a++) if (ui->keys[p][a] == k && k != SDL_SCANCODE_UNKNOWN) return 1;
   return 0;
}

/* The joystick bits of a pad word, active low (0 up, 1 down, 2 left, 3 right, 4 trigger A, 5 trigger B). */
static uint8_t m_joystick(uint16_t pad) {
   uint8_t pressed = (uint8_t)(((pad & M_BIT(M_UP)) ? 0x01 : 0) | ((pad & M_BIT(M_DOWN)) ? 0x02 : 0) | ((pad & M_BIT(M_LEFT)) ? 0x04 : 0) |
                               ((pad & M_BIT(M_RIGHT)) ? 0x08 : 0) | ((pad & M_BIT(M_A)) ? 0x10 : 0) | ((pad & M_BIT(M_B)) ? 0x20 : 0));
   return (uint8_t)(0x3F & ~pressed);
}

/* The inputs of the frame to come: the joysticks from the kit's pad words, the matrix from the keyboard (every key with full
 * typing, else the keys no binding takes; never a Ctrl+Alt chord, never a function key Retro-Recomp keeps) and from the pad
 * (directions on the cursor keys, trigger A and Start on SPACE, Select on F1). */
static void m_inputs(MsxMachine *m) {
   uint8_t held[MSX_KEY_ROWS];
   SDL_Keymod mod = SDL_GetModState();
   memset(held, 0, sizeof held);
   uint8_t joy1 = 0x3F, joy2 = 0x3F;
   player_poll();
   if (!player_blocked() && input_focus) {
      joy1 = m_joystick(ca.pad[0]);
      joy2 = m_joystick(ca.pad[1]);
      if (keys && !((mod & KMOD_CTRL) && (mod & KMOD_ALT))) {
         for (int k = 0; k < SDL_NUM_SCANCODES; k++) {
            int row, bit;
            if (!keys[k] || !m_matrix((SDL_Scancode)k, &row, &bit)) continue;
            if (k >= SDL_SCANCODE_F1 && k <= SDL_SCANCODE_F12 && player_host_fkey(k, mod)) continue;
            if (!guest_keyboard && (m_bound((SDL_Scancode)k) || k == SDL_SCANCODE_ESCAPE)) continue;
            held[row] |= (uint8_t)(1u << bit);
         }
      }
      if (!guest_keyboard) {
         const uint16_t pad = ca.pad[0];
         if (pad & M_BIT(M_UP)) held[8] |= 0x20;
         if (pad & M_BIT(M_DOWN)) held[8] |= 0x40;
         if (pad & M_BIT(M_LEFT)) held[8] |= 0x10;
         if (pad & M_BIT(M_RIGHT)) held[8] |= 0x80;
         if (pad & (M_BIT(M_A) | M_BIT(M_START))) held[8] |= 0x01;
         if (pad & M_BIT(M_SELECT)) held[6] |= 0x20;
      }
   }
   for (int row = 0; row < MSX_KEY_ROWS; row++) m->keys[row] = (uint8_t)~held[row];
   msx_joystick(m, 0, joy1);
   msx_joystick(m, 1, joy2);
}

/* ---- the picture: the TMS9918A's 256 x 192 with eight border pixels around it; the V9938's 512 half-pixels x 212 lines
 * with 16 half-pixels and 8 lines of border (a 256-pixel mode doubled, a 192-line picture centred, R#18 moving the picture
 * inside the border). The view size is the chip's, fixed for the whole game. ---- */
enum { M_VIEW_W = MSX_WIDTH + 16, M_VIEW_H = MSX_HEIGHT + 16, M_VIEW2_W = MSX2_WIDTH + 32, M_VIEW2_H = MSX2_LINES + 16 };
static uint32_t m_view[M_VIEW2_H * M_VIEW2_W];
static bool m_v9938;                        /* set by msx_host_open from the machine */
static int m_view_w = M_VIEW_W, m_view_h = M_VIEW_H;
/* The TMS9918A's sixteen colours (a commonly published approximation of its analogue output; not measured on a set). */
static const uint32_t m_palette[16] = {
   0xFF000000, 0xFF000000, 0xFF21C842, 0xFF5EDC78, 0xFF5455ED, 0xFF7D76FC, 0xFFD4524D, 0xFF42EBF5,
   0xFFFC5554, 0xFFFF7978, 0xFFD4C154, 0xFFE6CE80, 0xFF21B03B, 0xFFC95BBA, 0xFFCCCCCC, 0xFFFFFFFF};

/* A V9938 colour (0GGG0RRR0BBB) as ARGB: each three-bit component scaled to 0-255. */
static uint32_t m_rgb9(uint16_t c) {
   if (c & MSX_COLOUR15) {                   /* a V9958 YJK point: 5 bits a channel */
      unsigned g15 = (c >> 10) & 31, r15 = (c >> 5) & 31, b15 = c & 31;
      return 0xFF000000u | ((uint32_t)((r15 << 3) | (r15 >> 2)) << 16) | ((uint32_t)((g15 << 3) | (g15 >> 2)) << 8)
             | (uint32_t)((b15 << 3) | (b15 >> 2));
   }
   unsigned g = (c >> 8) & 7, r = (c >> 4) & 7, b = c & 7;
   return 0xFF000000u | (r * 255 / 7) << 16 | (g * 255 / 7) << 8 | (b * 255 / 7);
}

static void m_picture2(const MsxMachine *m) {
   const MsxV9938 *v = m->v9938;
   /* R#18: the vertical adjust moves the whole picture (taken at frame start); the horizontal one each line as it was drawn
    * (a game that changes it at a line interrupt, Space Manbow's playfield under its status bar, scrolls those lines only). */
   int lines = v->lines_latched, top = 8 + (MSX2_LINES - lines) / 2 + v->adjust_v;
   for (int y = 0; y < M_VIEW2_H; y++) {
      int line = y - top;
      int edge_line = line < 0 ? 0 : line >= lines ? lines - 1 : line;
      uint32_t edge_even = m_rgb9(v->border[edge_line][0]), edge_odd = m_rgb9(v->border[edge_line][1]);
      uint32_t *out = m_view + y * M_VIEW2_W;
      for (int x = 0; x < M_VIEW2_W; x++) out[x] = (x & 1) ? edge_odd : edge_even;
      if (line >= 0 && line < lines) {
         const int left = 16 + 2 * v->line_adjust[line];      /* 2 to 32: the 512 half-pixels always fit in 544 */
         for (int x = 0; x < MSX2_WIDTH; x++)
            if (left + x >= 0 && left + x < M_VIEW2_W) out[left + x] = m_rgb9(v->frame[line][x]);
      }
   }
}

static void m_picture(const MsxMachine *m) {
   if (m_v9938) { m_picture2(m); return; }
   for (int y = 0; y < M_VIEW_H; y++) {
      int line = y - 8;
      uint32_t edge = m_palette[m->vdp.border[line < 0 ? 0 : line >= MSX_HEIGHT ? MSX_HEIGHT - 1 : line] & 15];
      uint32_t *out = m_view + y * M_VIEW_W;
      for (int x = 0; x < M_VIEW_W; x++) out[x] = edge;
      if (line >= 0 && line < MSX_HEIGHT)
         for (int x = 0; x < MSX_WIDTH; x++) out[8 + x] = m_palette[m->vdp.frame[line][x] & 15];
   }
}

/* ---- the sound: mono 44.1 kHz from the machine, doubled into the stereo ring (the Master System's output) ---- */
static SDL_AudioDeviceID audio_device;
static void audio_output_clear(void);
#define RR_HOST_AUDIO_FILTER rrhk_options_audio
#define RR_HOST_AUDIO_RESET rrhk_options_audio_reset
#define RR_HOST_AUDIO_DEVICE rrhk_audio_device
#define RR_HOST_AUDIO_HELD rrhk_audio_held
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
#include "audio_output.inc"

static void m_sound(MsxMachine *m) {
   static int16_t mono[MSX_AUDIO_BUFFER], stereo[2 * MSX_AUDIO_BUFFER];
   unsigned n = msx_audio_take(m, mono, MSX_AUDIO_BUFFER);
   if (fast_forward) return;                     /* frames faster than the sound: the samples are dropped, not queued */
   for (unsigned i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
   host_audio_submit(stereo, n);
}

/* ---- the machine table ---- */
static struct { bool reset; bool quit; uint64_t frame; } mh;

static int m_players(void) { return 2; }
static bool m_run_frame(uint16_t p1, uint16_t p2) { ca.pad[0] = p1; ca.pad[1] = p2; fast_forward = x_fast_forward(); return true; }
/* The shell calls this at every frame start: only a change empties the ring (the sound held before a pause is not played
 * after it). */
static void m_pause(bool paused) {
   static bool was;
   if (paused == was) return;
   was = paused;
   audio_output_clear();
}
/* The guest owns the loop: a reset is a request the game takes at the end of the frame (msx_host_frame returns 2); the
 * shell keeps running. */
static void m_reset(void) { mh.reset = true; }
static const uint32_t *m_pixels(void) { return m_view; }
static int m_width(void) { return m_view_w; }
static int m_height(void) { return m_view_h; }
/* The TMS9918A's pixel clock (5.37 MHz, as the PC Engine's lowest) gives pixels 8/7 as wide as tall on a 4:3 set; the
 * V9938's half-pixels are half as wide. */
static int m_display_width(void) { return m_v9938 ? (m_view_w * 4 + 3) / 7 : (m_view_w * 8 + 3) / 7; }
static size_t m_no_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t m_zero(void) { return 0; }
static uint64_t m_interpreted(void) { return banked_fallback_steps; }
static uint64_t m_input_frame(void) { return mh.frame; }
static bool m_state_ready(void) { return true; }
static bool m_state_file(const wchar_t *path, bool load) { return msx_game_state_file(path, load); }
static bool m_state_path(wchar_t *path, size_t capacity) { return msx_game_state_path(path, capacity); }

static void m_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, rrhk_tr("Arrows: joystick 1; X: trigger A (and SPACE), W: trigger B",
                                  "Fleches : manette 1 ; X : bouton A (et ESPACE), W : bouton B"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter: SPACE; right Shift: F1; Ctrl+Alt+K: the MSX keyboard",
                                                 "Entree : ESPACE ; Maj droite : F1 ; Ctrl+Alt+K : le clavier MSX"));
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      memset(&machine, 0, sizeof machine);
      machine.ini_section = L"MSX"; machine.console_name = "MSX";
      machine.table_players = 2; machine.players = m_players;
      machine.actions = m_actions; machine.action_count = M_ACTIONS;
      machine.up = M_UP; machine.down = M_DOWN; machine.left = M_LEFT; machine.right = M_RIGHT; machine.start = M_START;
      machine.max_width = m_view_w; machine.max_height = m_view_h;
      machine.frame_seconds = (double)MSX_CYCLES_PER_LINE * MSX_LINES_NTSC / MSX_CPU_CLOCK;
      machine.own_audio = true; machine.driven = true; machine.state_deferred = false;
      machine.video_section = L"MSX"; machine.autofire_section = L"MSX"; machine.indexed_bindings = true; machine.bindings_clearable = true;
      machine.machine_fkeys = 5;
      machine.reset = m_reset; machine.run_frame = m_run_frame; machine.pause = m_pause;
      machine.pixels = m_pixels; machine.visible_width = m_width; machine.visible_height = m_height; machine.raster_height = m_height;
      machine.display_width = m_display_width;
      machine.audio = m_no_audio; machine.interpreted = m_interpreted; machine.audio_interpreted = m_zero;
      machine.audio_reopen = host_audio_reopen; machine.audio_device_id = host_audio_device_id;
      machine.state_ready = m_state_ready; machine.state_file = m_state_file; machine.state_path = m_state_path;
      machine.input_frame = m_input_frame;
      machine.settings_loaded = x_settings_loaded; machine.help_lines = x_help_lines; machine.help_controls = m_help_controls;
      machine.option_rows = x_option_rows; machine.key_event = x_key_event;
      machine.frame_start = x_frame_start; machine.finished = x_finished;
      machine.event = x_event; machine.keyboard_pad = x_keyboard_pad; machine.fast_forward = x_fast_forward; machine.game_rect = x_game_rect;
      machine.help_page = x_help_page; machine.action_held = x_action_held;
   }
   return &machine;
}

/* ---- what the game calls ---- */
static bool msx_host_open(const char *title, int scale, const MsxMachine *m) {
   m_v9938 = m->video == MSX_VIDEO_V9938;
   if (m_v9938) { m_view_w = M_VIEW2_W; m_view_h = M_VIEW2_H; }
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   /* The pace of the frames: the board's lines. An MSX2's software may switch 50/60 Hz later (R#9): the kit keeps this
    * pace until it can follow (lead request L3). */
   machine->frame_seconds = (double)MSX_CYCLES_PER_LINE * m->lines_per_frame / MSX_CPU_CLOCK;
   /* The window's whole-pixel scale (rrhk_computer.inc x_game_rect) counts the TMS9918A's pixels, as the Amiga counts lores
    * pixels: the V9938's store holds two half-pixels per pixel, so its picture is 272 pixels wide like the MSX1's, not 544
    * (a 544 x 228 picture at 1:1 opened flat and wide). */
   width = (unsigned)(m_v9938 ? m_view_w / 2 : m_view_w); height = (unsigned)m_view_h;
   ca.windowed = true;
   if (!rrhk_open(machine, title, scale)) return false;
   rrhk_autofire_reset();
   host_audio_init(MSX_AUDIO_RATE);
   rrhk_notice(rrhk_tr("F1: help | Ctrl+Alt+K: MSX keyboard", "F1 : aide | Ctrl+Alt+K : clavier MSX"), 2400);
   return true;
}

/* The end of a guest frame: the picture and the sound out, the window's events and menus, the inputs of the next frame in.
 * 0: go on; 1: quit; 2: reset. */
static int msx_host_frame(MsxMachine *m) {
   /* The pace follows the machine's lines: an MSX2's software switches 50/60 Hz with R#9 (taken at each frame start). The
    * kit reads frame_seconds at every frame (rrhk_main.c), so nothing else is needed. */
   ((RrhkMachine *)rrhk_adapter())->frame_seconds = (double)MSX_CYCLES_PER_LINE * m->lines_per_frame / MSX_CPU_CLOCK;
   m_picture(m);
   m_sound(m);
   const bool running = rrhk_frame_done();
   mh.frame++;
   m_inputs(m);
   if (mh.reset) { mh.reset = false; audio_output_clear(); return 2; }
   return running ? 0 : 1;
}

static void msx_host_close(void) {
   host_audio_shutdown();
   rrhk_close();
   SDL_Quit();
}
