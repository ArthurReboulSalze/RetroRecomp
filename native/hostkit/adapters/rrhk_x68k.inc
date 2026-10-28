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

/* The largest picture the machine renders (800 x 600) and the one the window starts with. */
#define X_MAX_WIDTH 800
#define X_MAX_HEIGHT 600

static struct {
   bool windowed;                 /* the kit runs the loop */
   uint16_t pad[2];               /* the kit's pad word of each player for this frame */
   int help_page, escape_held;
   bool started, relative;
   uint32_t *argb;                /* the last picture, 0xAARRGGBB, X_MAX_WIDTH per row */
   int16_t *audio;                /* the sound of this frame (stereo int16), not yet taken by the kit */
   size_t audio_count, audio_capacity, audio_taken;
} xa;

static int player_blocked(void) { const RrhkUi *ui = rrhk_ui(); return xa.windowed && (ui->menu || ui->paused); }
static int player_escape_held(void) { return xa.windowed && xa.escape_held; }

static void player_notice(const char *message) { if (xa.windowed) rrhk_notice(rr_tr(message), 3500); }

/* Function keys are Retro-Recomp shortcuts unless the options hand F1-F10 to the X68000, or full typing keeps F2-F10
 * for it. Ctrl+F1-F12 (not Ctrl+Alt) and any function key inside a menu stay with Retro-Recomp. */
static int player_host_fkey(int key, SDL_Keymod mod) {
   if (key < SDL_SCANCODE_F1 || key > SDL_SCANCODE_F12) return 0;
   if ((xa.windowed && rrhk_ui()->menu) || ((mod & KMOD_CTRL) && !(mod & KMOD_ALT))) return 1;
   if (guest_keyboard && key >= SDL_SCANCODE_F2 && key <= SDL_SCANCODE_F10) return 0;
   return rrhk_options_host_fkey(key, mod, false);
}

/* The libretro joypad of a port from the kit's pad word (keyboard, controller, stick, autofire, opposite directions). */
static int player_joy(unsigned port) {
   static const struct { unsigned action, id; } map[] = { {X_UP, RETRO_DEVICE_ID_JOYPAD_UP}, {X_DOWN, RETRO_DEVICE_ID_JOYPAD_DOWN},
      {X_LEFT, RETRO_DEVICE_ID_JOYPAD_LEFT}, {X_RIGHT, RETRO_DEVICE_ID_JOYPAD_RIGHT}, {X_A, RETRO_DEVICE_ID_JOYPAD_B}, {X_B, RETRO_DEVICE_ID_JOYPAD_A} };
   unsigned mask = 0, n;
   if (!xa.windowed || port > 1) return -1;
   if (player_blocked() || !input_focus) return 0;
   for (n = 0; n < sizeof map / sizeof map[0]; n++) if (xa.pad[port] & X_BIT(map[n].action)) mask |= 1u << map[n].id;
   return (int)mask;
}
/* The Return key of the guest: Start of the first player (any binding), or -1 without the kit. */
static int player_start(void) {
   if (!xa.windowed) return -1;
   if (player_blocked() || !input_focus) return 0;
   return (xa.pad[0] & X_BIT(X_ENTER)) != 0;
}
static int player_pad_start(void) {
   SDL_GameController *pad = xa.windowed ? rrhk_ui()->pads[0] : NULL;
   return pad && SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_START);
}
/* A key bound to a button of player 1 is that button (decision of 28 October 2026, "same rules on every machine"): while
 * autofire releases the button, the key the guest reads is released too. -1: not such a key. */
static int player_face_alias(unsigned scan) {
   unsigned action;
   if (!xa.windowed || guest_keyboard || !scan) return -1;
   for (action = X_A; action <= X_B; action++)
      if ((unsigned)rrhk_ui()->keys[0][action] == scan) return !player_blocked() && input_focus && (xa.pad[0] & X_BIT(action)) != 0;
   return -1;
}
/* The mouse of a mouse game: the buttons are Button A and Button B (with their autofire), the directions of the first
 * player and the stick move the pointer. */
static int player_mouse(unsigned id, int value) {
   if (!mouse_game || !xa.windowed || !input_focus || player_blocked()) return value;
   if (id == RETRO_DEVICE_ID_MOUSE_LEFT) return (xa.pad[0] & X_BIT(X_A)) != 0;
   if (id == RETRO_DEVICE_ID_MOUSE_RIGHT) return (xa.pad[0] & X_BIT(X_B)) != 0;
   if (id == RETRO_DEVICE_ID_MOUSE_X || id == RETRO_DEVICE_ID_MOUSE_Y) {
      int horizontal = id == RETRO_DEVICE_ID_MOUSE_X;
      SDL_GameController *pad = rrhk_ui()->pads[0];
      int step = ((xa.pad[0] & X_BIT(horizontal ? X_RIGHT : X_DOWN)) != 0) - ((xa.pad[0] & X_BIT(horizontal ? X_LEFT : X_UP)) != 0);
      int axis = pad ? SDL_GameControllerGetAxis(pad, horizontal ? SDL_CONTROLLER_AXIS_LEFTX : SDL_CONTROLLER_AXIS_LEFTY) : 0;
      int delta = step * 6;
      /* The stick of the kit's pad word has one dead zone for every console (decision D1, 28 October 2026). */
      if (axis > 16000 || axis < -16000) delta = axis / 5500;
      return (horizontal ? mouse_dx : mouse_dy) + delta;
   }
   return value;
}
/* Keyboard and mouse of this frame. */
static void player_poll(void) {
   keys = SDL_GetKeyboardState(NULL);
   mouse_buttons = SDL_GetRelativeMouseState(&mouse_dx, &mouse_dy);
   if (!mouse_grab || !input_focus) { mouse_dx = mouse_dy = 0; mouse_buttons = 0; }
}

/* ---- the picture ---- */
static void player_picture(const void *data, unsigned w, unsigned h, size_t pitch) {
   unsigned x, y;
   if (!xa.windowed || !data || !xa.argb) return;
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

/* The picture keeps the aspect ratio of the machine; Pixel mode is the largest whole multiple of the picture's own
 * pixel grid (the rule of the former X68000 host, not yet the common integer rule: HOST_KIT.md divergence 9). */
static bool x_game_rect(int rw, int rh, int mode, SDL_Rect *rect) {
   SDL_Rect dst;
   if (!width || !height) return false;
   dst.x = 0; dst.y = 0; dst.w = rw; dst.h = (int)round(rw / aspect_ratio);
   if (dst.h > rh) { dst.h = rh; dst.w = (int)round(rh * aspect_ratio); }
   if (mode == 1) {
      int scale = SDL_min(rw / (int)width, rh / (int)height);
      if (scale >= 1) { dst.w = (int)width * scale; dst.h = (int)height * scale; }
   }
   dst.x = (rw - dst.w) / 2; dst.y = (rh - dst.h) / 2;
   *rect = dst;
   return true;
}

/* ---- the sound: the frame's PCM waits here until the kit takes it ---- */
static int player_queue_audio(const int16_t *samples, size_t count) {
   if (!xa.windowed) return 1;
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

/* ---- the machine ---- */
static bool x_fast_forward(void) {
   const Uint8 *state = SDL_GetKeyboardState(NULL);
   return input_focus && !player_blocked() && state && state[SDL_SCANCODE_F5] && player_host_fkey(SDL_SCANCODE_F5, SDL_GetModState());
}
static bool x_run_frame(uint16_t p1, uint16_t p2) {
   xa.pad[0] = p1; xa.pad[1] = p2;
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
static bool x_keyboard_pad(void) {
   SDL_Keymod mod = SDL_GetModState();
   return !guest_keyboard && !((mod & KMOD_CTRL) && (mod & KMOD_ALT));
}
/* The pointer's buttons are Button A and Button B of the first player while a mouse game holds the mouse. */
static bool x_action_held(int player, int action) {
   Uint32 buttons;
   if (player || !mouse_game || !mouse_grab || !input_focus || rrhk_ui()->menu || rrhk_ui()->paused) return false;
   buttons = SDL_GetMouseState(NULL, NULL);
   return action == X_A ? (buttons & SDL_BUTTON_LMASK) != 0 : action == X_B && (buttons & SDL_BUTTON_RMASK) != 0;
}

/* ---- window state kept in datas/player.cfg since the first player (width and height are all that is read back) ---- */
static void player_load(SDL_Window *window) {
   FILE *f = fopen(player_config, "rb"); unsigned full = 0, keyboard = 0, fire = 0, w = 0, h = 0; char extra;
   if (f) {
      int n = fscanf(f, "fullscreen=%u keyboard=%u autofire=%u width=%u height=%u %c", &full, &keyboard, &fire, &w, &h, &extra);
      fclose(f);
      if (n == 5 && full < 2 && keyboard < 2 && fire < 2 && w >= 400 && w <= 8192 && h >= 300 && h <= 8192) {
         guest_keyboard = keyboard != 0;
         if (window && !(SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN_DESKTOP)) SDL_SetWindowSize(window, (int)w, (int)h);
      }
   }
}
static void player_save(void) {
   FILE *f; int w = 900, h = 675; SDL_Window *window = rrhk_window();
   if (!window) return;
   SDL_GetWindowSize(window, &w, &h);
   f = fopen(player_config, "wb");
   if (f) { fprintf(f, "fullscreen=%u keyboard=%u autofire=%u width=%d height=%d\n",
      (SDL_GetWindowFlags(window) & SDL_WINDOW_FULLSCREEN_DESKTOP) != 0, guest_keyboard, rrhk_ui()->autofire != 0, w, h); fclose(f); }
}
static void x_finished(double elapsed) { (void)elapsed; player_save(); }
static void x_settings_loaded(RrhkUi *ui) {
   guest_keyboard = rr_ini_int(L"X68000", L"guest_keyboard", 0, ui->ini_file) != 0;
}

/* The mouse is captured (relative) only while the game runs in a focused window. */
static void x_sync_mouse(void) {
   bool wanted = mouse_grab && input_focus && !player_blocked();
   if (wanted != xa.relative) { SDL_SetRelativeMouseMode(wanted ? SDL_TRUE : SDL_FALSE); xa.relative = wanted; }
   if (player_blocked()) SDL_GetRelativeMouseState(NULL, NULL);   /* motion during a menu is not the guest's */
}
static void x_frame_start(void *window, void *renderer) {
   (void)renderer;
   if (!xa.started) {
      xa.started = true;
      SDL_SetWindowMinimumSize((SDL_Window *)window, 400, 340);
      player_load((SDL_Window *)window);
      if (mouse_game) { mouse_grab = true; player_notice("Mouse controls: Ctrl+Alt+M releases the mouse"); }
   }
   x_sync_mouse();
}

/* The computer's own events, before the kit sees them: the guest keyboard, Ctrl+Alt chords, focus, mouse capture,
 * pause (F11 or the Pause binding), the second help page. true: consumed. */
static bool x_event(const SDL_Event *e, bool *running) {
   RrhkUi *ui = rrhk_ui();
   int key = e->type == SDL_KEYDOWN && !e->key.repeat ? e->key.keysym.scancode : 0;
   int button = e->type == SDL_CONTROLLERBUTTONDOWN ? e->cbutton.button : -1;
   SDL_Keymod mod = key ? (SDL_Keymod)e->key.keysym.mod : KMOD_NONE;
   /* Any input interrupts an automatic fast loading. */
   if ((e->type == SDL_KEYDOWN && !e->key.repeat && e->key.keysym.sym != SDLK_F5) || e->type == SDL_MOUSEBUTTONDOWN ||
       e->type == SDL_CONTROLLERBUTTONDOWN || (e->type == SDL_MOUSEMOTION && (e->motion.xrel || e->motion.yrel)) ||
       (e->type == SDL_CONTROLLERAXISMOTION && (e->caxis.value > 12000 || e->caxis.value < -12000)))
      loading_holdoff = 16;
   if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_LOST) input_focus = false;
   if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_GAINED) input_focus = true;
   if (e->type == SDL_QUIT) return false;
   /* A function key handed to the X68000 never reaches the frontend. */
   if (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12 && !player_host_fkey(key, mod)) { rrhk_options_observe(e); return true; }
   /* A menu's Escape belongs entirely to the frontend until key release: it must not pause the guest or quit twice. */
   if (e->type == SDL_KEYUP && e->key.keysym.scancode == SDL_SCANCODE_ESCAPE) xa.escape_held = 0;
   if (e->type == SDL_KEYDOWN && e->key.keysym.scancode == SDL_SCANCODE_ESCAPE && xa.escape_held) { rrhk_options_observe(e); return true; }
   if (key == SDL_SCANCODE_ESCAPE && ui->menu) xa.escape_held = 1;
   if (ui->capturing) return false;
   /* A click on an unknown computer game captures its mouse; menus and an unfocused window never do. */
   if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_LEFT && input_focus && !player_blocked() && !mouse_grab) {
      mouse_grab = true; player_notice("Mouse captured (Ctrl+Alt+M to release)");
   }
   /* Full computer typing reserves the ordinary keys for the guest. Guide and explicit Ctrl+Alt shortcuts remain. */
   if (guest_keyboard && !ui->menu && (e->type == SDL_KEYDOWN || e->type == SDL_KEYUP) &&
       !(key && (mod & KMOD_CTRL) && (mod & KMOD_ALT)) && !(key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12)) {
      rrhk_options_observe(e); return true;
   }
   if (key && (mod & KMOD_CTRL) && (mod & KMOD_ALT)) {
      SDL_Keycode sym = e->key.keysym.sym;
      rrhk_options_observe(e);
      if (sym == SDLK_h) ui->menu = ui->menu ? 0 : RRHK_MENU_HELP;
      else if (sym == SDLK_o) ui->menu = RRHK_MENU_OPTIONS;
      else if (sym == SDLK_RETURN) rrhk_cycle_display();
      else if (sym == SDLK_q) *running = false;
      else if (sym == SDLK_k) {
         guest_keyboard = !guest_keyboard;
         player_notice(guest_keyboard ? "Full guest keyboard: ON (F8/F9 sent to X68000)" : "Game shortcuts: ON (F8/F9 save and load)");
      } else if (sym == SDLK_f) rrhk_toggle_autofire();
      else if (sym == SDLK_m) { mouse_grab = !mouse_grab; player_notice(mouse_grab ? "Mouse captured (Ctrl+Alt+M to release)" : "Mouse released"); }
      else if (sym == SDLK_PAGEUP || sym == SDLK_PAGEDOWN) { want_swap = true; swap_drive = (mod & KMOD_SHIFT) ? 1 : 0; swap_direction = sym == SDLK_PAGEUP ? -1 : 1; }
      else if (sym == SDLK_BACKSPACE) { want_eject = true; swap_drive = (mod & KMOD_SHIFT) ? 1 : 0; }
      return true;
   }
   if (key == SDL_SCANCODE_F11) { ui->paused = !ui->paused; return true; }
   if (key == SDL_SCANCODE_TAB && ui->menu == RRHK_MENU_HELP) { xa.help_page ^= 1; return true; }
   /* The Pause binding of either player, when no menu is open and the guest does not have the keyboard. */
   if (!ui->menu && !guest_keyboard && (key || button >= 0)) {
      unsigned p;
      for (p = 0; p < 2; p++) {
         int match = key ? ui->keys[p][X_PAUSE] == key : ui->buttons[p][X_PAUSE] == button;
         if (button >= 0 && (!ui->pads[p] || SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(ui->pads[p])) != e->cbutton.which)) continue;
         if (match) { ui->paused = !ui->paused; return true; }
      }
   }
   return false;
}

/* ---- help (F1) ---- */
static void x_help_lines(int slot, const char **lines, int *count) {
   if (slot == 0) lines[(*count)++] = rr_tr("F5  Fast loading (hold)");
   else lines[(*count)++] = rr_tr("F11 Pause");
}
static void x_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, rr_tr("Arrows + W/X; Enter: Start"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rr_tr("Tab: game / computer shortcuts"));
}
static bool x_help_page(RrhkUi *ui, const RrhkMenuCtx *ctx) {
   static const char *const lines[] = {"Ctrl+Alt+K: full guest keyboard", "Ctrl+Alt+M: mouse capture", "Ctrl+Alt+F: rapid fire",
      "Ctrl+Alt+Page Up/Down: FDD0", "Add Shift: FDD1", "Ctrl+Alt+Backspace: eject disk", "Ctrl+Alt+H: help", "Ctrl+Alt+O: options",
      "Ctrl+Alt+Enter: display mode", "Ctrl+Alt+Q: quit", "Ctrl+F1-F12: Retro-Recomp shortcuts"};
   unsigned n;
   (void)ui;
   if (!xa.help_page) return false;
   for (n = 0; n < sizeof lines / sizeof lines[0]; n++) rrhk_menu_line(ctx, RR_MENU_FIRST_LINE + (int)n * RR_MENU_LINE, rr_tr(lines[n]));
   rrhk_menu_line(ctx, RR_MENU_LAST_LINE, rr_tr("Tab: game / computer shortcuts"));
   return true;
}

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
   xa.windowed = true;
   xa.argb = (uint32_t *)calloc((size_t)X_MAX_WIDTH * X_MAX_HEIGHT, sizeof(uint32_t));
   if (!xa.argb) { fail("Presentation allocation failed"); return 1; }
   status = rrhk_main(machine, title, 1);
   return status;
}
/* Preferences written when the game closes, as the former host did. */
static void player_store_exit(void) {
   const RrhkUi *ui = rrhk_ui();
   if (!xa.windowed || !ui->ini_file[0]) return;
   rr_display_save(ui->ini_file, ui->data_dir, L"X68000", L"guest_keyboard", guest_keyboard);
   rr_display_save(ui->ini_file, ui->data_dir, L"X68000", L"autofire", ui->autofire != 0);
}
static void player_shutdown(void) { free(xa.argb); free(xa.audio); xa.argb = NULL; xa.audio = NULL; }
