/* Atari ST adapter for the host kit (docs/HOST_KIT.md, a computer like the X68000 and the Amiga). Original Retro-Recomp code,
 * MIT.
 *
 * Included by native/atarist_machine/atarist_player.c, which owns the Atari ST session (atarist_session.h) and defines the frontend
 * variables that rrhk_computer.inc reads. What the computers share (the guest keyboard and its Ctrl+Alt chords, the captured
 * mouse, the mouse-game profile, the floppy keys, the function keys, the second help page, the window preferences) comes from
 * rrhk_computer.inc, unchanged; what is the ST's stays here: the joysticks of ports 1 and 0, the mouse of port 0, the keys as
 * libretro key codes (Hatari's IKBD maps them to ST scan codes), the floppy changes, the picture and the sound of the session.
 * Guest state is never filtered. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"
#include <math.h>

/* The actions, in menu order; the bit of an action is 1 << its index. Fire is the joystick's button (and the mouse's left
 * button in a mouse game), Button B the mouse's right button in a mouse game (an ST joystick has one button). */
enum { S_UP, S_DOWN, S_LEFT, S_RIGHT, S_FIRE, S_FIRE2, S_START, S_PAUSE, S_ACTIONS };
#define S_NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
static const RrhkAction s_actions[S_ACTIONS] = {
   {"Up", L"Up", 1u << S_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", 1u << S_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", 1u << S_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", 1u << S_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button A", L"Button A", 1u << S_FIRE, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
   {"Button B", L"Button B", 1u << S_FIRE2, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
   {"Start", L"Start", 1u << S_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
   {"Pause", L"Pause", 1u << S_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN}, {S_NO_PAD, S_NO_PAD}}};
#define S_BIT(action) (1u << (action))

#define RRC_UP S_UP
#define RRC_DOWN S_DOWN
#define RRC_LEFT S_LEFT
#define RRC_RIGHT S_RIGHT
#define RRC_BUTTON_A S_FIRE
#define RRC_BUTTON_B S_FIRE2
#define RRC_START S_START
#define RRC_PAUSE S_PAUSE
#define RRC_BIT(action) S_BIT(action)
#define RRC_INI_SECTION L"AtariST"
#define RRC_KEYBOARD_ON "Full guest keyboard: ON (F8/F9 sent to Atari ST)"
#define RRC_GUEST_FKEY_LAST SDL_SCANCODE_F10
#include "hostkit/adapters/rrhk_computer.inc"

/* The libretro key code of an SDL scancode (the code Hatari's frontend maps to an ST scan code), 0: none. Home is ClrHome,
 * End Undo, Page Up Help (as on Hatari's own host); the keypad keeps its keys. */
static unsigned s_retro_key(SDL_Scancode k) {
   static const struct { SDL_Scancode scan; unsigned key; } map[] = {
      {SDL_SCANCODE_ESCAPE, RETROK_ESCAPE}, {SDL_SCANCODE_GRAVE, RETROK_BACKQUOTE}, {SDL_SCANCODE_MINUS, RETROK_MINUS},
      {SDL_SCANCODE_EQUALS, RETROK_EQUALS}, {SDL_SCANCODE_BACKSPACE, RETROK_BACKSPACE}, {SDL_SCANCODE_TAB, RETROK_TAB},
      {SDL_SCANCODE_LEFTBRACKET, RETROK_LEFTBRACKET}, {SDL_SCANCODE_RIGHTBRACKET, RETROK_RIGHTBRACKET},
      {SDL_SCANCODE_RETURN, RETROK_RETURN}, {SDL_SCANCODE_SEMICOLON, RETROK_SEMICOLON}, {SDL_SCANCODE_APOSTROPHE, RETROK_QUOTE},
      {SDL_SCANCODE_BACKSLASH, RETROK_BACKSLASH}, {SDL_SCANCODE_NONUSHASH, RETROK_BACKSLASH}, {SDL_SCANCODE_COMMA, RETROK_COMMA},
      {SDL_SCANCODE_PERIOD, RETROK_PERIOD}, {SDL_SCANCODE_SLASH, RETROK_SLASH}, {SDL_SCANCODE_SPACE, RETROK_SPACE},
      {SDL_SCANCODE_NONUSBACKSLASH, RETROK_LESS}, {SDL_SCANCODE_CAPSLOCK, RETROK_CAPSLOCK},
      {SDL_SCANCODE_LSHIFT, RETROK_LSHIFT}, {SDL_SCANCODE_RSHIFT, RETROK_RSHIFT}, {SDL_SCANCODE_LCTRL, RETROK_LCTRL},
      {SDL_SCANCODE_RCTRL, RETROK_RCTRL}, {SDL_SCANCODE_LALT, RETROK_LALT}, {SDL_SCANCODE_RALT, RETROK_RALT},
      {SDL_SCANCODE_UP, RETROK_UP}, {SDL_SCANCODE_DOWN, RETROK_DOWN}, {SDL_SCANCODE_LEFT, RETROK_LEFT}, {SDL_SCANCODE_RIGHT, RETROK_RIGHT},
      {SDL_SCANCODE_INSERT, RETROK_INSERT}, {SDL_SCANCODE_DELETE, RETROK_DELETE}, {SDL_SCANCODE_HOME, RETROK_HOME},
      {SDL_SCANCODE_END, RETROK_END}, {SDL_SCANCODE_PAGEUP, RETROK_F13},
      {SDL_SCANCODE_KP_0, RETROK_KP0}, {SDL_SCANCODE_KP_1, RETROK_KP1}, {SDL_SCANCODE_KP_2, RETROK_KP2}, {SDL_SCANCODE_KP_3, RETROK_KP3},
      {SDL_SCANCODE_KP_4, RETROK_KP4}, {SDL_SCANCODE_KP_5, RETROK_KP5}, {SDL_SCANCODE_KP_6, RETROK_KP6}, {SDL_SCANCODE_KP_7, RETROK_KP7},
      {SDL_SCANCODE_KP_8, RETROK_KP8}, {SDL_SCANCODE_KP_9, RETROK_KP9}, {SDL_SCANCODE_KP_PERIOD, RETROK_KP_PERIOD},
      {SDL_SCANCODE_KP_DIVIDE, RETROK_KP_DIVIDE}, {SDL_SCANCODE_KP_MULTIPLY, RETROK_KP_MULTIPLY},
      {SDL_SCANCODE_KP_MINUS, RETROK_KP_MINUS}, {SDL_SCANCODE_KP_PLUS, RETROK_KP_PLUS}, {SDL_SCANCODE_KP_ENTER, RETROK_KP_ENTER},
      {SDL_SCANCODE_F1, RETROK_F1}, {SDL_SCANCODE_F2, RETROK_F2}, {SDL_SCANCODE_F3, RETROK_F3}, {SDL_SCANCODE_F4, RETROK_F4},
      {SDL_SCANCODE_F5, RETROK_F5}, {SDL_SCANCODE_F6, RETROK_F6}, {SDL_SCANCODE_F7, RETROK_F7}, {SDL_SCANCODE_F8, RETROK_F8},
      {SDL_SCANCODE_F9, RETROK_F9}, {SDL_SCANCODE_F10, RETROK_F10}};
   unsigned n;
   if (k >= SDL_SCANCODE_A && k <= SDL_SCANCODE_Z) return RETROK_a + (unsigned)(k - SDL_SCANCODE_A);
   if (k >= SDL_SCANCODE_1 && k <= SDL_SCANCODE_9) return RETROK_1 + (unsigned)(k - SDL_SCANCODE_1);
   if (k == SDL_SCANCODE_0) return RETROK_0;
   for (n = 0; n < sizeof map / sizeof map[0]; n++) if (map[n].scan == k) return map[n].key;
   return 0;
}

/* A scancode bound to an action of a player, which the guest does not see while the pad has the keyboard. */
static int s_bound(SDL_Scancode k) {
   const RrhkUi *ui = rrhk_ui();
   int p, a;
   for (p = 0; p < 2; p++) for (a = 0; a < S_ACTIONS; a++) if (ui->keys[p][a] == k && k != SDL_SCANCODE_UNKNOWN) return 1;
   return 0;
}

static struct {
   int16_t audio[2 * 8192];
   size_t audio_count, audio_taken;
   uint8_t held[RETROK_LAST];       /* the keys the guest holds, to send changes only */
} sa;

static unsigned s_joystick_bits(uint16_t pad) {
   unsigned bits = 0;
   if (pad & S_BIT(S_UP)) bits |= RR_ST_JOY_UP;
   if (pad & S_BIT(S_DOWN)) bits |= RR_ST_JOY_DOWN;
   if (pad & S_BIT(S_LEFT)) bits |= RR_ST_JOY_LEFT;
   if (pad & S_BIT(S_RIGHT)) bits |= RR_ST_JOY_RIGHT;
   if (pad & S_BIT(S_FIRE)) bits |= RR_ST_JOY_FIRE;
   return bits;
}

/* The guest's inputs of this frame from the kit's pad words, the keyboard and the mouse: player 1 is the joystick of port 1,
 * player 2 the joystick of port 0 (where the mouse is plugged: a two-player game unplugs it). */
static void s_inputs(void) {
   uint8_t held[RETROK_LAST];
   unsigned bits1 = 0, bits0 = 0, n;
   int left = 0, right = 0, dx = 0, dy = 0, k;
   SDL_Keymod mod = SDL_GetModState();
   memset(held, 0, sizeof held);
   player_poll();
   if (!player_blocked() && input_focus) {
      if (!mouse_game) { bits1 = s_joystick_bits(ca.pad[0]); bits0 = s_joystick_bits(ca.pad[1]); }
      left = player_mouse(RETRO_DEVICE_ID_MOUSE_LEFT, mouse_grab && (mouse_buttons & SDL_BUTTON_LMASK) != 0);
      right = player_mouse(RETRO_DEVICE_ID_MOUSE_RIGHT, mouse_grab && (mouse_buttons & SDL_BUTTON_RMASK) != 0);
      dx = player_mouse(RETRO_DEVICE_ID_MOUSE_X, mouse_dx);
      dy = player_mouse(RETRO_DEVICE_ID_MOUSE_Y, mouse_dy);
      /* The keyboard: every key with full typing, else the keys no binding takes; never a Ctrl+Alt chord, never a function key
       * Retro-Recomp keeps. Start is the guest's Return. */
      if (keys && !((mod & KMOD_CTRL) && (mod & KMOD_ALT))) {
         for (k = 0; k < SDL_NUM_SCANCODES; k++) {
            unsigned code;
            if (!keys[k] || !(code = s_retro_key((SDL_Scancode)k)) || code >= RETROK_LAST) continue;
            if (k >= SDL_SCANCODE_F1 && k <= SDL_SCANCODE_F12 && player_host_fkey(k, mod)) continue;
            if (!guest_keyboard && (s_bound((SDL_Scancode)k) || k == SDL_SCANCODE_ESCAPE)) continue;
            held[code] = 1;
         }
      }
      if (!guest_keyboard && player_start() > 0) held[RETROK_RETURN] = 1;
   }
   rr_st_joystick(session, 1, bits1);
   rr_st_joystick(session, 0, bits0);
   rr_st_mouse(session, dx, dy, left, right);
   for (n = 1; n < RETROK_LAST; n++)
      if (held[n] != sa.held[n]) { rr_st_key(session, n, held[n]); sa.held[n] = held[n]; }
}

/* A floppy change asked by the keys of rrhk_computer.inc (Ctrl+Alt+Page Up/Down): the previous or next disk of the game in
 * drive A. Drive B and eject are not offered (no game of the first scope needs them). */
static void s_disks(void) {
   unsigned count = rr_st_disk_count(session), index;
   char text[96];
   if (want_eject) { want_eject = false; player_notice("Eject is not available on the Atari ST"); }
   if (!want_swap) return;
   want_swap = false;
   if (count < 2 || swap_drive) { player_notice(count < 2 ? "This game has one disk" : "Drive B is not used"); return; }
   index = (rr_st_disk_index(session) + count + (swap_direction < 0 ? count - 1 : 1)) % count;
   if (rr_st_insert_disk(session, index) == 0) {
      snprintf(text, sizeof text, rrhk_tr("Disk %u of %u in drive A", "Disquette %u sur %u dans le lecteur A"), index + 1, count);
      if (ca.windowed) rrhk_notice(text, 3500);
   }
}

/* What the player shows: the whole picture Hatari draws (the ST screen and its borders, where overscan code draws too), never
 * cropped, on a 4:3 screen. */
static const uint32_t *s_pixels(void) {
   int w, h, stride;
   return rr_st_picture(session, &w, &h, &stride);
}
static int s_width(void) { int w, h, stride; rr_st_picture(session, &w, &h, &stride); return w; }
static int s_height(void) { int w, h, stride; rr_st_picture(session, &w, &h, &stride); return h; }

static size_t s_audio(int16_t *pcm, size_t capacity) {
   size_t n = sa.audio_count - sa.audio_taken;
   if (n > capacity) n = capacity;
   if (!n) { sa.audio_count = sa.audio_taken = 0; return 0; }
   memcpy(pcm, sa.audio + sa.audio_taken, n * sizeof(int16_t));
   sa.audio_taken += n;
   return n;
}

static bool s_run_frame(uint16_t p1, uint16_t p2) {
   size_t got;
   int w, h, stride;
   ca.pad[0] = p1; ca.pad[1] = p2;
   fast_forward = x_fast_forward();
   s_inputs();
   s_disks();
   if (rr_st_frame(session) != 0) { fail(rr_st_error(session)); return false; }
   frame_number++;
   rr_st_picture(session, &w, &h, &stride);
   if (w > 0 && h > 0) { width = (unsigned)w; height = (unsigned)h; }
   if (sa.audio_taken) { memmove(sa.audio, sa.audio + sa.audio_taken, (sa.audio_count - sa.audio_taken) * sizeof(int16_t)); sa.audio_count -= sa.audio_taken; sa.audio_taken = 0; }
   got = rr_st_audio(session, sa.audio + sa.audio_count, (sizeof sa.audio / sizeof sa.audio[0] - sa.audio_count) / 2);
   sa.audio_count += got * 2;
   return !quit_requested && (!frame_limit || frame_number < frame_limit);
}
static void s_pause(bool paused) { (void)paused; }
static int s_players(void) { return 2; }
/* A reset boots the machine again: the process restarts itself (the session is one per process). */
static void s_reset(void) { restart_requested = true; quit_requested = true; }
static uint64_t s_zero(void) { return 0; }
static uint64_t s_interpreted(void) { return rr_st_interpreted_count(session); }
static uint64_t s_input_frame(void) { return frame_number; }
static bool s_state_ready(void) { return true; }
static bool s_state_path(wchar_t *path, size_t capacity) { return rr_from_utf8(state_slot, path, capacity) != 0; }
static bool s_state_file(const wchar_t *path, bool load) {
   char utf8[PATH_CAP];
   if (!rr_to_utf8(path, utf8, sizeof utf8)) return false;
   return (load ? state_load(utf8) : state_save(utf8, false)) == 0;
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine machine;
   if (!machine.actions) {
      memset(&machine, 0, sizeof machine);
      machine.ini_section = L"AtariST"; machine.console_name = "Atari ST";
      machine.table_players = 2; machine.players = s_players;
      machine.actions = s_actions; machine.action_count = S_ACTIONS;
      machine.up = S_UP; machine.down = S_DOWN; machine.left = S_LEFT; machine.right = S_RIGHT; machine.start = S_START;
      machine.max_width = RR_ST_PICTURE_MAX_WIDTH; machine.max_height = RR_ST_PICTURE_MAX_HEIGHT;
      machine.frame_seconds = 1.0 / 50.0;
      machine.audio_model = RRHK_AUDIO_QUEUE; machine.audio_rate = 44100; machine.audio_chunked = true;
      machine.video_section = L"AtariST"; machine.autofire_section = L"AtariST"; machine.indexed_bindings = true; machine.bindings_clearable = true;
      machine.machine_fkeys = 10;
      machine.save_failed_en = "Cannot save game state"; machine.save_failed_fr = "Impossible de sauvegarder";
      machine.reset = s_reset; machine.run_frame = s_run_frame; machine.pause = s_pause;
      machine.pixels = s_pixels; machine.visible_width = s_width; machine.visible_height = s_height; machine.raster_height = s_height;
      machine.display_width = s_width;
      machine.audio = s_audio; machine.interpreted = s_interpreted; machine.audio_interpreted = s_zero;
      machine.state_path = s_state_path; machine.state_ready = s_state_ready; machine.state_file = s_state_file; machine.input_frame = s_input_frame;
      machine.settings_loaded = x_settings_loaded; machine.help_lines = x_help_lines; machine.help_controls = x_help_controls;
      machine.option_rows = x_option_rows; machine.key_event = x_key_event;
      machine.frame_start = x_frame_start; machine.finished = x_finished;
      machine.event = x_event; machine.keyboard_pad = x_keyboard_pad; machine.fast_forward = x_fast_forward; machine.game_rect = x_game_rect;
      machine.help_page = x_help_page; machine.action_held = x_action_held;
   }
   return &machine;
}

/* The windowed game: the kit runs the loop and calls s_run_frame for each guest frame. */
static int player_run_windowed(const char *title) {
   RrhkMachine *machine = (RrhkMachine *)rrhk_adapter();
   machine->frame_seconds = 1.0 / (double)(rr_st_refresh_rate(session) > 0 ? rr_st_refresh_rate(session) : 50);
   machine->audio_rate = rr_st_audio_rate(session);
   ca.windowed = true;
   return rrhk_main(machine, title, 2);
}
