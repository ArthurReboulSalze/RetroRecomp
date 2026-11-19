/* Commodore Amiga adapter for the host kit (docs/HOST_KIT.md, a computer like the X68000). Original Retro-Recomp code, MIT.
 *
 * Included by native/amiga_machine/amiga_player.c, which owns the Amiga session (amiga_session.h) and defines the frontend
 * variables that rrhk_computer.inc reads. What the computers share (the guest keyboard and its Ctrl+Alt chords, the captured
 * mouse, the mouse-game profile, the function keys, the second help page, the window preferences) comes from
 * rrhk_computer.inc, unchanged; what is the Amiga's stays here: the joystick of port 2, port 1 (the mouse, or the second player's
 * joystick: a_port1_*), the raw key codes, the picture and the sound of the session. Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "hostkit/hostkit_session.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include <math.h>

/* The libretro numbers rrhk_computer.inc names the mouse inputs with (the Amiga has no libretro core: these are only ids). */
#define RETRO_DEVICE_ID_MOUSE_X 0
#define RETRO_DEVICE_ID_MOUSE_Y 1
#define RETRO_DEVICE_ID_MOUSE_LEFT 2
#define RETRO_DEVICE_ID_MOUSE_RIGHT 3

/* The actions, in menu order; the bit of an action is 1 << its index. Fire is the joystick's button (and the mouse's left
 * button in a mouse game), Button B its second button (the right one). */
enum { A_UP, A_DOWN, A_LEFT, A_RIGHT, A_FIRE, A_FIRE2, A_START, A_PAUSE, A_ACTIONS };
#define A_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction a_actions[A_ACTIONS] = {
   {"Up", L"Up", 1u << A_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << A_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << A_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << A_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button A", L"Button A", 1u << A_FIRE, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_w},
   {"Button B", L"Button B", 1u << A_FIRE2, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_x},
   {"Start", L"Start", 1u << A_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Pause", L"Pause", 1u << A_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {A_NO_PAD, A_NO_PAD}}};
#define A_BIT(action) (1u << (action))

#define RRC_UP A_UP
#define RRC_DOWN A_DOWN
#define RRC_LEFT A_LEFT
#define RRC_RIGHT A_RIGHT
#define RRC_BUTTON_A A_FIRE
#define RRC_BUTTON_B A_FIRE2
#define RRC_START A_START
#define RRC_PAUSE A_PAUSE
#define RRC_BIT(action) A_BIT(action)
#define RRC_INI_SECTION L"Amiga"
#define RRC_KEYBOARD_ON "Full guest keyboard: ON (F8/F9 sent to Amiga)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_F10
#define RRC_HELP_DISKS   /* a WHDLoad install has no disk to change: the keys do nothing here, the help lists none */
#include "hostkit/adapters/rrhk_computer.inc"

/* The Amiga raw key code of an SDL scancode (US layout positions), 0xFF: none. */
static uint8_t a_raw_key(SDL_Scancode k) {
   static const struct { SDL_Scancode scan; uint8_t raw; } map[] = {
      {SDL_SCANCODE_GRAVE, 0x00}, {SDL_SCANCODE_1, 0x01}, {SDL_SCANCODE_2, 0x02}, {SDL_SCANCODE_3, 0x03}, {SDL_SCANCODE_4, 0x04},
      {SDL_SCANCODE_5, 0x05}, {SDL_SCANCODE_6, 0x06}, {SDL_SCANCODE_7, 0x07}, {SDL_SCANCODE_8, 0x08}, {SDL_SCANCODE_9, 0x09},
      {SDL_SCANCODE_0, 0x0A}, {SDL_SCANCODE_MINUS, 0x0B}, {SDL_SCANCODE_EQUALS, 0x0C}, {SDL_SCANCODE_BACKSLASH, 0x0D},
      {SDL_SCANCODE_KP_0, 0x0F}, {SDL_SCANCODE_Q, 0x10}, {SDL_SCANCODE_W, 0x11}, {SDL_SCANCODE_E, 0x12}, {SDL_SCANCODE_R, 0x13},
      {SDL_SCANCODE_T, 0x14}, {SDL_SCANCODE_Y, 0x15}, {SDL_SCANCODE_U, 0x16}, {SDL_SCANCODE_I, 0x17}, {SDL_SCANCODE_O, 0x18},
      {SDL_SCANCODE_P, 0x19}, {SDL_SCANCODE_LEFTBRACKET, 0x1A}, {SDL_SCANCODE_RIGHTBRACKET, 0x1B}, {SDL_SCANCODE_KP_1, 0x1D},
      {SDL_SCANCODE_KP_2, 0x1E}, {SDL_SCANCODE_KP_3, 0x1F}, {SDL_SCANCODE_A, 0x20}, {SDL_SCANCODE_S, 0x21}, {SDL_SCANCODE_D, 0x22},
      {SDL_SCANCODE_F, 0x23}, {SDL_SCANCODE_G, 0x24}, {SDL_SCANCODE_H, 0x25}, {SDL_SCANCODE_J, 0x26}, {SDL_SCANCODE_K, 0x27},
      {SDL_SCANCODE_L, 0x28}, {SDL_SCANCODE_SEMICOLON, 0x29}, {SDL_SCANCODE_APOSTROPHE, 0x2A}, {SDL_SCANCODE_NONUSHASH, 0x2B},
      {SDL_SCANCODE_KP_4, 0x2D}, {SDL_SCANCODE_KP_5, 0x2E}, {SDL_SCANCODE_KP_6, 0x2F}, {SDL_SCANCODE_NONUSBACKSLASH, 0x30},
      {SDL_SCANCODE_Z, 0x31}, {SDL_SCANCODE_X, 0x32}, {SDL_SCANCODE_C, 0x33}, {SDL_SCANCODE_V, 0x34}, {SDL_SCANCODE_B, 0x35},
      {SDL_SCANCODE_N, 0x36}, {SDL_SCANCODE_M, 0x37}, {SDL_SCANCODE_COMMA, 0x38}, {SDL_SCANCODE_PERIOD, 0x39}, {SDL_SCANCODE_SLASH, 0x3A},
      {SDL_SCANCODE_KP_PERIOD, 0x3C}, {SDL_SCANCODE_KP_7, 0x3D}, {SDL_SCANCODE_KP_8, 0x3E}, {SDL_SCANCODE_KP_9, 0x3F},
      {SDL_SCANCODE_SPACE, 0x40}, {SDL_SCANCODE_BACKSPACE, 0x41}, {SDL_SCANCODE_TAB, 0x42}, {SDL_SCANCODE_KP_ENTER, 0x43},
      {SDL_SCANCODE_RETURN, 0x44}, {SDL_SCANCODE_ESCAPE, 0x45}, {SDL_SCANCODE_DELETE, 0x46}, {SDL_SCANCODE_KP_MINUS, 0x4A},
      {SDL_SCANCODE_UP, 0x4C}, {SDL_SCANCODE_DOWN, 0x4D}, {SDL_SCANCODE_RIGHT, 0x4E}, {SDL_SCANCODE_LEFT, 0x4F},
      {SDL_SCANCODE_F1, 0x50}, {SDL_SCANCODE_F2, 0x51}, {SDL_SCANCODE_F3, 0x52}, {SDL_SCANCODE_F4, 0x53}, {SDL_SCANCODE_F5, 0x54},
      {SDL_SCANCODE_F6, 0x55}, {SDL_SCANCODE_F7, 0x56}, {SDL_SCANCODE_F8, 0x57}, {SDL_SCANCODE_F9, 0x58}, {SDL_SCANCODE_F10, 0x59},
      {SDL_SCANCODE_KP_DIVIDE, 0x5C}, {SDL_SCANCODE_KP_MULTIPLY, 0x5D}, {SDL_SCANCODE_KP_PLUS, 0x5E}, {SDL_SCANCODE_INSERT, 0x5F},
      {SDL_SCANCODE_LSHIFT, 0x60}, {SDL_SCANCODE_RSHIFT, 0x61}, {SDL_SCANCODE_CAPSLOCK, 0x62}, {SDL_SCANCODE_LCTRL, 0x63},
      {SDL_SCANCODE_RCTRL, 0x63}, {SDL_SCANCODE_LALT, 0x64}, {SDL_SCANCODE_RALT, 0x65}, {SDL_SCANCODE_LGUI, 0x66},
      {SDL_SCANCODE_RGUI, 0x67}};
   unsigned n;
   for (n = 0; n < sizeof map / sizeof map[0]; n++) if (map[n].scan == k) return map[n].raw;
   return 0xFF;
}

/* A scancode bound to an action of a player, which the guest does not see while the pad has the keyboard. */
static int a_bound(SDL_Scancode k) {
   const RrhkUi *ui = rrhk_ui();
   int p, a;
   for (p = 0; p < 2; p++) for (a = 0; a < A_ACTIONS; a++) if (ui->keys[p][a] == k && k != SDL_SCANCODE_UNKNOWN) return 1;
   return 0;
}

static struct {
   int16_t audio[2 * 4096];
   size_t audio_count, audio_taken;
} aa;

/* ---- port 1: the mouse, or the second player's joystick ------------------------------------------------------------------
 * As on a real Amiga, where the mouse is unplugged from port 1 for a two-player game. By default the port follows the device used
 * last (the session's RR_AMIGA_PORT1_FOLLOW: player 2's pad plugs the joystick, a mouse motion or click plugs the mouse back); the
 * player may keep it on one device. The choice is kept per game in port1.cfg ("port1=N"); a plate says when the device changes.
 * a_port1_mode / a_set_port1_mode / a_port1_device are what the shell's row "Mouse port" on player 2's pad page reads and sets. */
static int a_port1_choice = RR_AMIGA_PORT1_FOLLOW, a_port1_shown;

static int a_port1_mode(void) { return a_port1_choice; }

/* `save`: kept for the next start (a choice made in the window), or this run only (--port1). */
static void a_set_port1_mode(int mode, bool save) {
   FILE *f;
   wchar_t wide[PATH_CAP];
   if (mode < RR_AMIGA_PORT1_FOLLOW || mode > RR_AMIGA_PORT1_JOYSTICK) mode = RR_AMIGA_PORT1_FOLLOW;
   a_port1_choice = mode;
   if (!rrhk_session_active()) rr_amiga_port1_mode(session, mode);    /* a session keeps the joystick in port 1 (a_session_begin) */
   if (!save || !port1_config[0] || !rr_from_utf8(port1_config, wide, PATH_CAP) || !(f = rr_fopen(wide, L"wb"))) return;
   fprintf(f, "port1=%d\n", mode);
   fclose(f);
}

/* The device port 1 holds now: 0 the mouse, 1 the joystick (the row's icon). */
static int a_port1_device(void) { return rr_amiga_port1_device(session); }

static void a_port1_load(void) {
   FILE *f;
   wchar_t wide[PATH_CAP];
   int mode = RR_AMIGA_PORT1_FOLLOW;
   char extra;
   if (port1_option >= 0) { a_set_port1_mode(port1_option, false); return; }
   if (port1_config[0] && rr_from_utf8(port1_config, wide, PATH_CAP) && (f = rr_fopen(wide, L"rb"))) {
      if (fscanf(f, "port1=%d %c", &mode, &extra) != 1) mode = RR_AMIGA_PORT1_FOLLOW;     /* anything else: the default */
      fclose(f);
   }
   a_set_port1_mode(mode, false);
}

/* The plate when port 1 changes device, in the five languages of the games, without accents (as the games write their texts). */
static void a_port1_notice(void) {
   static const char *const text[2][5] = {
      {"Mouse port: mouse", "Port souris : souris", "Mausport: Maus", "Puerto del raton: raton", "Porta del mouse: mouse"},
      {"Mouse port: pad 2", "Port souris : manette 2", "Mausport: Pad 2", "Puerto del raton: mando 2", "Porta del mouse: pad 2"}};
   static const char *const codes[5] = {"en", "fr", "de", "es", "it"};
   const char *code = rr_language_code(rr_language_get());
   int device = a_port1_device(), language = 0, n;
   if (device == a_port1_shown) return;
   a_port1_shown = device;
   for (n = 0; n < 5; n++) if (code && !strcmp(code, codes[n])) language = n;
   if (ca.windowed) rrhk_notice(text[device][language], 3500);
}

/* The row "Mouse port" at the top of player 2's gamepad page (the shell's RrhkPadRow): its value is the player's choice, kept per game; its
 * icon shows the device port 1 holds now (a mouse or a joystick plugged into the port). */
static const char *const a_port1_values[3] = {"Auto (last used)", "Mouse", "Pad 2"};
static void a_pad_port1_set(int value) { a_set_port1_mode(value, true); }
static int a_pad_port1_icon(void) { return a_port1_device() ? RR_ICON_ROW_PORT_JOYSTICK : RR_ICON_ROW_PORT_MOUSE; }
static const RrhkPadRow a_pad_rows[1] = {{2, "Mouse port", 3, a_port1_values, a_port1_mode, a_pad_port1_set, a_pad_port1_icon}};

/* The CPU's speed, the player's option (HOST_KIT D14's one exception, the owner's decision of 15 November 2026): Normal (the model's
 * own clock, the default), x2 or x4, as an accelerator card gave. The row on F2's options page cycles it; the choice is kept per game in
 * cpu.cfg ("cpu=N") and holds across quick states (the session sets it again after a load). --cpu-factor sets it for one run, not saved.
 * A game the conversion lists as needing the normal speed (cpu_stock_only) stays at Normal and says so. Headless runs never read cpu.cfg:
 * the conversion's routes and checks run at Normal. Texts in the five languages of the games, without accents. */
#define A_ROW_CPU (SDL_NUM_SCANCODES + 2)   /* the row's key: past the computers' keyboard row (+1), before the kit's own rows (+16) */
static int a_cpu_choice = 1;

static int a_language(void) {
   static const char *const codes[5] = {"en", "fr", "de", "es", "it"};
   const char *code = rr_language_code(rr_language_get());
   int n;
   for (n = 0; n < 5; n++) if (code && !strcmp(code, codes[n])) return n;
   return 0;
}

/* `save`: kept for the next start (a choice made in the window), or this run only (--cpu-factor). */
static void a_set_cpu(int factor, bool save) {
   FILE *f;
   wchar_t wide[PATH_CAP];
   if (cpu_stock_only || (factor != 2 && factor != 4)) factor = 1;
   a_cpu_choice = factor;
   rr_amiga_cpu_factor(session, factor);
   if (!save || !cpu_config[0] || !rr_from_utf8(cpu_config, wide, PATH_CAP) || !(f = rr_fopen(wide, L"wb"))) return;
   fprintf(f, "cpu=%d\n", factor);
   fclose(f);
}

static void a_cpu_load(void) {
   FILE *f;
   wchar_t wide[PATH_CAP];
   int factor = 1;
   char extra;
   if (cpu_option) { a_set_cpu(cpu_option, false); return; }
   if (cpu_config[0] && rr_from_utf8(cpu_config, wide, PATH_CAP) && (f = rr_fopen(wide, L"rb"))) {
      if (fscanf(f, "cpu=%d %c", &factor, &extra) != 1) factor = 1;     /* anything else: the normal speed */
      fclose(f);
   }
   a_set_cpu(factor, false);
}

/* The row's label (a format with one %s) and its value now, e.g. "CPU speed: x2 (28 MHz)". */
static const char *a_cpu_label(void) {
   static const char *const label[5] = {"CPU speed: %s", "Vitesse du processeur : %s", "CPU-Takt: %s", "Velocidad de la CPU: %s",
                                        "Velocita della CPU: %s"};
   return label[a_language()];
}
static const char *a_cpu_value(void) {
   static const char *const normal[5] = {"Normal", "Normale", "Normal", "Normal", "Normale"};
   static const char *const only[5] = {"Normal (this game)", "Normale (ce jeu)", "Normal (dieses Spiel)", "Normal (este juego)",
                                       "Normale (questo gioco)"};
   static char text[64];
   int language = a_language();
   if (cpu_stock_only) return only[language];
   if (a_cpu_choice == 1) snprintf(text, sizeof text, "%s (%d MHz)", normal[language], cpu_mhz);
   else snprintf(text, sizeof text, "x%d (%d MHz)", a_cpu_choice, cpu_mhz * a_cpu_choice);
   return text;
}

static void a_option_rows(int slot, RrhkOptionRows *rows) {
   x_option_rows(slot, rows);
   if (slot == 1) rrhk_option_row_run(rows, A_ROW_CPU, RR_ICON_ROW_SPEED, a_cpu_label(), a_cpu_value());
}

/* The row cycles Normal, x2, x4; a plate says the new speed (or, for a game listed as needing it, that it stays at Normal). */
static bool a_key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
   char plate[96];
   if ((int)key != A_ROW_CPU) return x_key_event(ui, key, running);
   /* In a session a guest plays the host's speed (the kit fades the row and says so); the host changes it, and the match then
    * starts again for everyone at the new speed (session ABI 9: its session_options changed). */
   if (rrhk_session_guest()) return true;
   if (!cpu_stock_only) a_set_cpu(a_cpu_choice == 1 ? 2 : a_cpu_choice == 2 ? 4 : 1, true);
   snprintf(plate, sizeof plate, a_cpu_label(), a_cpu_value());
   rrhk_notice(plate, 2500);
   return true;
}

/* A pad word's joystick bits. */
static unsigned a_joy_bits(uint16_t pad) {
   unsigned bits = 0;
   if (pad & A_BIT(A_UP)) bits |= RR_AMIGA_JOY_UP;
   if (pad & A_BIT(A_DOWN)) bits |= RR_AMIGA_JOY_DOWN;
   if (pad & A_BIT(A_LEFT)) bits |= RR_AMIGA_JOY_LEFT;
   if (pad & A_BIT(A_RIGHT)) bits |= RR_AMIGA_JOY_RIGHT;
   if (pad & A_BIT(A_FIRE)) bits |= RR_AMIGA_JOY_FIRE;
   if (pad & A_BIT(A_FIRE2)) bits |= RR_AMIGA_JOY_FIRE2;
   return bits;
}

/* The guest's inputs of this frame from the kit's pad words, the keyboard and the mouse. In a multiplayer session, from the frame's
 * words and the host's keys alone, whatever this window's focus or menus (they are the same on every seat): the two joysticks, the
 * keys the host types (session ABI 9), else Start as the guest's Return; the mouse is not carried yet. */
static void a_inputs(void) {
   uint8_t held[128];
   unsigned bits = 0, bits2 = 0;
   uint16_t pad = ca.pad[0], pad2 = ca.pad[1];
   int left = 0, right = 0, dx = 0, dy = 0, k;
   SDL_Keymod mod = SDL_GetModState();
   memset(held, 0, sizeof held);
   player_poll();
   if (rrhk_session_active()) {
      if (guest_keyboard) {
         for (k = 0; k < SDL_NUM_SCANCODES; k++) {
            const uint8_t raw = keys[k] ? a_raw_key((SDL_Scancode)k) : 0xFF;
            if (raw < 128) held[raw] = 1;
         }
      } else held[0x44] = (pad & A_BIT(A_START)) != 0;
      rr_amiga_joystick(session, a_joy_bits(pad));
      rr_amiga_joystick2(session, a_joy_bits(pad2));
      rr_amiga_mouse(session, 0, 0, 0, 0);
      rr_amiga_keys(session, held);
      return;
   }
   if (!player_blocked() && input_focus) {
      if (!mouse_game) bits = a_joy_bits(pad);
      /* Player 2's pad: the joystick of port 1, which takes the port from the mouse when it is used (a_port1_*). */
      bits2 = a_joy_bits(pad2);
      /* The mouse: captured motion and buttons, or (a mouse game) the pad standing for it. */
      left = player_mouse(RETRO_DEVICE_ID_MOUSE_LEFT, mouse_grab && (mouse_buttons & SDL_BUTTON_LMASK) != 0);
      right = player_mouse(RETRO_DEVICE_ID_MOUSE_RIGHT, mouse_grab && (mouse_buttons & SDL_BUTTON_RMASK) != 0);
      dx = player_mouse(RETRO_DEVICE_ID_MOUSE_X, mouse_dx);
      dy = player_mouse(RETRO_DEVICE_ID_MOUSE_Y, mouse_dy);
      /* The keyboard: every key with full typing, else the keys no binding takes; never a Ctrl+Alt chord, never a function key
       * Retro-Recomp keeps. Start is the guest's Return. */
      if (keys && !((mod & KMOD_CTRL) && (mod & KMOD_ALT))) {
         for (k = 0; k < SDL_NUM_SCANCODES; k++) {
            uint8_t raw;
            if (!keys[k]) continue;
            raw = a_raw_key((SDL_Scancode)k);
            if (raw == 0xFF) continue;
            if (k >= SDL_SCANCODE_F1 && k <= SDL_SCANCODE_F12 && player_host_fkey(k, mod)) continue;
            if (!guest_keyboard && (a_bound((SDL_Scancode)k) || k == SDL_SCANCODE_ESCAPE)) continue;
            held[raw] = 1;
         }
      }
      if (!guest_keyboard && player_start() > 0) held[0x44] = 1;
   }
   rr_amiga_joystick(session, bits);
   rr_amiga_joystick2(session, bits2);     /* before the mouse: a mouse used in the same frame keeps the port */
   rr_amiga_mouse(session, dx, dy, left, right);
   rr_amiga_keys(session, held);
   a_port1_notice();
}

/* What the player shows: the display window the game opens (the union of its DIWSTRT/DIWSTOP, measured over the conversion's
 * reference routes and grown by what this run opens), never the overscan border around it, and nothing inside it is cut. The
 * kit's whole-pixel step is the Amiga's lores pixel and line (`width` x `height` for x_game_rect), as the X68000 presents its
 * own resolution: enlarging the window enlarges the picture every 320 x 256 (PAL). The texture keeps hires columns and one
 * row per line (the scanline filter draws one line per row). The window opens at 3x. */
#define A_PAR_PAL (16.0 / 15.0)      /* a PAL lores pixel on a 4:3 screen (320 x 256 fills it) */
#define A_PAR_NTSC (5.0 / 6.0)       /* an NTSC one (320 x 200) */
static struct { int x, y, w, h, ntsc; } av;
static uint32_t av_pixels[RR_AMIGA_PICTURE_WIDTH * RR_AMIGA_PICTURE_MAX_ROWS];
static int av_rows = 1;      /* rows per line of the last picture: 2 while the screen is interlaced (woven fields, amiga_session.h) */

static void a_view_place(int x, int y, int w, int h) {
   int lines = av.ntsc ? RR_AMIGA_PICTURE_LINES_NTSC : RR_AMIGA_PICTURE_LINES_PAL;
   if (x & 1) { x--; w++; }
   w = (w + 1) & ~1;                                 /* whole lores pixels */
   if (x < 0) { w += x; x = 0; }
   if (y < 0) { h += y; y = 0; }
   if (x + w > RR_AMIGA_PICTURE_WIDTH) w = RR_AMIGA_PICTURE_WIDTH - x;
   if (y + h > lines) h = lines - y;
   av.x = x; av.y = y; av.w = w; av.h = h;
   width = (unsigned)(w / 2); height = (unsigned)h;
   aspect_ratio = (av.ntsc ? A_PAR_NTSC : A_PAR_PAL) * (double)width / (double)height;
}

/* The window the conversion measured (w or h 0: none, the standard one: $2C81-$2CC1 PAL, $2C81-$F4C1 NTSC). */
static void a_view_init(int ntsc, int x, int y, int w, int h) {
   av.ntsc = ntsc;
   if (w < 64 || h < 32) { x = 32; w = 640; y = ntsc ? 18 : 12; h = ntsc ? 200 : 256; }
   a_view_place(x, y, w, h);
}

/* A window this run opens beyond the measured one widens what is shown (it never shrinks: the size stays put). */
static void a_view_follow(void) {
   int x, y, w, h, x1, y1;
   if (!rr_amiga_viewport(session, &x, &y, &w, &h)) return;
   x1 = SDL_max(av.x + av.w, x + w); y1 = SDL_max(av.y + av.h, y + h);
   x = SDL_min(av.x, x); y = SDL_min(av.y, y);
   if (x != av.x || y != av.y || x1 - x != av.w || y1 - y != av.h) a_view_place(x, y, x1 - x, y1 - y);
}

static const uint32_t *a_pixels(void) {
   int w, h, row;
   const uint32_t *src = rr_amiga_picture(session, &w, &h);
   for (row = 0; row < av.h * av_rows; row++)
      memcpy(av_pixels + (size_t)row * RR_AMIGA_PICTURE_WIDTH, src + (size_t)(av.y * av_rows + row) * (size_t)w + (size_t)av.x, (size_t)av.w * sizeof(uint32_t));
   return av_pixels;
}
static int a_width(void) { return av.w; }             /* texture columns (hires) */
static int a_display_width(void) { return av.w / 2; } /* lores pixels */
static int a_height(void) { return av.h * av_rows; }  /* lines, one row each (two while interlaced: the same window, twice the rows) */

static size_t a_audio(int16_t *pcm, size_t capacity) {
   size_t n = aa.audio_count - aa.audio_taken;
   if (n > capacity) n = capacity;
   if (!n) { aa.audio_count = aa.audio_taken = 0; return 0; }
   memcpy(pcm, aa.audio + aa.audio_taken, n * sizeof(int16_t));
   aa.audio_taken += n;
   return n;
}

static bool a_run_frame(uint16_t p1, uint16_t p2) {
   size_t got;
   ca.pad[0] = p1; ca.pad[1] = p2;
   fast_forward = x_fast_forward();
   a_inputs();
   if (rr_amiga_frame(session) != 0) { fail(rr_amiga_error(session)); return false; }
   frame_number++;
   a_view_follow();
   {  /* the rows of this frame's picture, known before the kit asks for its height or its pixels */
      int w, h;
      rr_amiga_picture(session, &w, &h);
      av_rows = h > (av.ntsc ? RR_AMIGA_PICTURE_LINES_NTSC : RR_AMIGA_PICTURE_LINES_PAL) ? 2 : 1;
   }
   if (aa.audio_taken) { memmove(aa.audio, aa.audio + aa.audio_taken, (aa.audio_count - aa.audio_taken) * sizeof(int16_t)); aa.audio_count -= aa.audio_taken; aa.audio_taken = 0; }
   got = rr_amiga_audio(session, aa.audio + aa.audio_count, (sizeof aa.audio / sizeof aa.audio[0] - aa.audio_count) / 2);
   aa.audio_count += got * 2;
   return !quit_requested && (!frame_limit || frame_number < frame_limit);
}
static void a_pause(bool paused) { (void)paused; }
/* Two joysticks: port 2 (player 1) and port 1 (player 2's, when it takes the port from the mouse), so F2 offers two players' pages. */
static int a_players(void) { return 2; }
/* ---- multiplayer (hostkit_session.h) ----------------------------------------------------------------------------------------
 * A session (RETRORECOMP_NETPLAY_PIPE at the start: amiga_player.c then opens the machine with
 * RrAmigaGame.session: the install's files and the match's saves, kept in memory) plays from the pad words alone (a_inputs), port 1 holding the
 * joystick, the CPU at the host's speed ("cpu": 1, 2 or 4, pushed to every seat; a game listed as needing the normal speed takes 1
 * only; the export's own speed when none is pushed). The guest keyboard and the mouse are not carried yet (the computers' shared rule, rrhk_computer.inc). */
static int a_session_cpu;            /* the host's "cpu" (a_session_option), 0: the export's own speed */
static uint8_t *a_boot;              /* the machine as the session found it (a_session_begin): the session's restart */
static size_t a_boot_size, a_boot_used;

static size_t a_snap_bound(void) { return rr_amiga_snap_bound(session); }
static size_t a_snap_save(void *buffer, size_t capacity) { return rr_amiga_snap_save(session, buffer, capacity); }
static bool a_snap_load(const void *buffer, size_t size) { return rr_amiga_snap_load(session, buffer, size) != 0; }
static uint64_t a_digest(void) { return rr_amiga_digest(session); }
static void a_side_effects(bool allowed) { rr_amiga_side_effects(session, allowed); }
/* The saves of the match: this player's, for the host's HELLO; the host's, which a guest plays on (in memory, never written). */
static size_t a_session_save(void *out, size_t capacity) { return rr_amiga_session_save(session, out, capacity); }
static bool a_session_save_put(const void *in, size_t size) { return rr_amiga_session_save_put(session, in, size) != 0; }
/* The host at the match's clean end: the match's saves back to its own save folder, the previous files kept in "saves.bak". */
static bool a_session_save_commit(void) { return rr_amiga_session_save_commit(session) != 0; }

static bool a_session_option(const char *key, const char *value) {
   if (strcmp(key, "cpu") || (strcmp(value, "1") && strcmp(value, "2") && strcmp(value, "4"))) return false;
   if (cpu_stock_only && value[0] != '1') return false;
   a_session_cpu = value[0] - '0';
   return true;
}

/* This PC's run-changing options for the host's HELLO: the player's own CPU speed (a game listed as needing the normal speed: 1). The
 * host's value comes back to every seat through a_session_option before the session begins. */
static size_t a_session_options(char *out, size_t capacity) {
   int n = snprintf(out, capacity, "cpu=%d", cpu_stock_only ? 1 : a_cpu_choice);
   return n > 0 && (size_t)n < capacity ? (size_t)n : 0;
}

/* No real-time clock to set: the machine has none fitted, and resload's TIME_GET answers a fixed date. */
static void a_session_begin(uint64_t clock) {
   (void)clock;
   rr_amiga_port1_mode(session, RR_AMIGA_PORT1_JOYSTICK);
   a_set_cpu(a_session_cpu ? a_session_cpu : 1, false);
   if (a_boot_used) return;
   a_boot_size = rr_amiga_snap_bound(session);
   a_boot = (uint8_t *)malloc(a_boot_size);
   a_boot_used = a_boot ? rr_amiga_snap_save(session, a_boot, a_boot_size) : 0;
}

/* A reset starts the install again from ws_GameLoader: the process restarts itself (the session is one per process). In a
 * multiplayer session, at the same frame on every seat, the machine goes back to the session's start instead. */
static void a_reset(void) {
   if (rrhk_session_active()) {
      if (!a_boot_used || !rr_amiga_snap_load(session, a_boot, a_boot_used)) fail("The session's restart failed");
      return;
   }
   restart_requested = true; quit_requested = true;
}
/* The reference CPU runs no hook, so nothing is counted: the run is the interpreter's all the same. */
static uint64_t a_interpreted(void) { return interpreter_only ? 1 : rr_amiga_interpreted_count(session); }
static uint64_t a_zero(void) { return 0; }
static uint64_t a_input_frame(void) { return frame_number; }
static bool a_state_ready(void) { return true; }
static bool a_state_path(wchar_t *path, size_t capacity) { return rr_from_utf8(state_slot, path, capacity) != 0; }
static bool a_state_file(const wchar_t *path, bool load) {
   char utf8[PATH_CAP];
   if (!rr_to_utf8(path, utf8, sizeof utf8)) return false;
   return (load ? rr_amiga_state_load(session, utf8, RR_AMIGA_STATE_ABI, RR_AMIGA_SOURCE_IDENTITY)
                : rr_amiga_state_save(session, utf8, RR_AMIGA_STATE_ABI, RR_AMIGA_SOURCE_IDENTITY)) == 0;
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      memset(&machine, 0, sizeof machine);
      machine.ini_section = L"Amiga"; machine.console_name = "Amiga";
      machine.table_players = 2; machine.players = a_players;
      machine.actions = a_actions; machine.action_count = A_ACTIONS;
      machine.up = A_UP; machine.down = A_DOWN; machine.left = A_LEFT; machine.right = A_RIGHT; machine.start = A_START;
      machine.max_width = RR_AMIGA_PICTURE_WIDTH; machine.max_height = RR_AMIGA_PICTURE_MAX_ROWS;
      machine.frame_seconds = 1.0 / 50.0;
      machine.audio_model = RRHK_AUDIO_QUEUE; machine.audio_rate = RR_AMIGA_AUDIO_RATE; machine.audio_chunked = true;
      machine.video_section = L"Amiga"; machine.autofire_section = L"Amiga"; machine.indexed_bindings = true; machine.bindings_clearable = true;
      machine.machine_fkeys = 10;
      machine.save_failed_en = "Cannot save game state"; machine.save_failed_fr = "Impossible de sauvegarder";
      machine.reset = a_reset; machine.run_frame = a_run_frame; machine.pause = a_pause;
      machine.pixels = a_pixels; machine.visible_width = a_width; machine.visible_height = a_height; machine.raster_height = a_height;
      machine.display_width = a_display_width;
      machine.audio = a_audio; machine.interpreted = a_interpreted; machine.audio_interpreted = a_zero;
      machine.native_caption = RRHK_CORE_CAPTION;
      machine.state_path = a_state_path; machine.state_ready = a_state_ready; machine.state_file = a_state_file; machine.input_frame = a_input_frame;
      machine.settings_loaded = x_settings_loaded; machine.help_lines = x_help_lines; machine.help_controls = x_help_controls;
      /* The F2 row "Keyboard (Ctrl+Alt+K): game controls / computer only" of rrhk_computer.inc, kept per game in player.cfg. */
      machine.option_rows = a_option_rows; machine.key_event = a_key_event;   /* the computers' keyboard row, then the CPU's speed */
      machine.frame_start = x_frame_start; machine.finished = x_finished;
      machine.event = x_event; machine.keyboard_pad = x_keyboard_pad; machine.fast_forward = x_fast_forward; machine.game_rect = x_game_rect;
      machine.help_page = x_help_page; machine.action_held = x_action_held;
      machine.pad_rows = a_pad_rows; machine.pad_row_count = 1;      /* "Mouse port" on player 2's gamepad page */
      machine.snap_bound = a_snap_bound; machine.snap_save = a_snap_save; machine.snap_load = a_snap_load;
      machine.digest = a_digest; machine.side_effects = a_side_effects;
      machine.session_save = a_session_save; machine.session_save_put = a_session_save_put;
      machine.session_save_commit = a_session_save_commit;
      machine.session_option = a_session_option; machine.session_options = a_session_options; machine.session_begin = a_session_begin;
      machine.session_keys = x_session_keys;
   }
   return &machine;
}

/* The windowed game: the kit runs the loop and calls a_run_frame for each guest frame. */
static int player_run_windowed(const char *title, int ntsc) {
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   machine->frame_seconds = ntsc ? 1.0 / 59.94 : 1.0 / 49.92;
   ca.windowed = true;
   a_port1_load();
   a_port1_shown = a_port1_device();
   a_cpu_load();
   return rrhk_main(machine, title, 3);
}
