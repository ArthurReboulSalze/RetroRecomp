/* The computer's side of a host kit adapter (docs/HOST_KIT.md, section 5). Original Retro-Recomp code, MIT.
 *
 * What every computer that boots from disks and is played with a pad shares, written once: the guest keyboard and its Ctrl+Alt chords, the captured mouse
 * and the mouse-game profile, the floppy drives (swap, eject), the fast-loading key, the function keys the computer keeps, the second help page, the
 * window preferences, the pad that stands for the mouse. The Sharp X68000 includes it from rrhk_x68k.inc; the Amiga includes it from its own adapter.
 *
 * The including adapter defines, before the #include:
 *   the actions of its pad table and their bit:      RRC_UP RRC_DOWN RRC_LEFT RRC_RIGHT RRC_BUTTON_A RRC_BUTTON_B RRC_START RRC_PAUSE   RRC_BIT(action)
 *   its section of the settings file:                RRC_INI_SECTION
 *   the notice of the full guest keyboard (a translated text, it names the machine): RRC_KEYBOARD_ON
 *   the last function key the guest owns with full typing: RRC_GUEST_FKEY_LAST
 *   the disk keys its help page lists, each followed by a comma: RRC_HELP_DISKS (only those the computer answers)
 * and its frontend (the file that includes the adapter) defines these variables, which the libretro callbacks and the kit's loop share:
 *   guest_keyboard mouse_grab mouse_game input_focus fast_forward loading_holdoff want_swap swap_drive swap_direction want_eject
 *   keys mouse_dx mouse_dy mouse_buttons width height aspect_ratio player_config
 * What the computer does not decide stays in the adapter: the actions themselves, the picture, the sound, the state, the machine table.
 * The machine table wires the computer's hooks: settings_loaded, option_rows, key_event, help_lines, help_controls, frame_start,
 * finished, event, keyboard_pad, fast_forward, game_rect, help_page and action_held (the x_ functions below). */

/* The state of the windowed player that the computer's functions keep. */
static struct {
   bool windowed;                 /* the kit runs the loop */
   uint16_t pad[2];               /* the kit's pad word of each player for this frame */
   int help_page, escape_held;
   bool started, relative;
} ca;

/* The F2 options row that hands the whole keyboard to the computer, as Ctrl+Alt+K does: a pseudo-key past every scancode,
 * which no keyboard sends, so only the row reaches the machine's key hook (decision of 5 November 2026: a keyboard game
 * keeps its keys, the pad keys bound on the keyboard stop, and only a real gamepad plays the joystick). */
#define RRC_ROW_KEYBOARD (SDL_NUM_SCANCODES + 1)

static int player_blocked(void) { const RrhkUi *ui = rrhk_ui(); return ca.windowed && (ui->menu || ui->paused); }
static int player_escape_held(void) { return ca.windowed && ca.escape_held; }

static void player_notice(const char *message) { if (ca.windowed) rrhk_notice(rr_tr(message), 3500); }

/* Function keys are Retro-Recomp shortcuts unless the options hand F1-F10 to the guest, or full typing keeps F1-F10
 * for it (Pinball Dreams picks its table with F1-F4). Ctrl+F1-F12 (not Ctrl+Alt) and any function key inside a menu stay
 * with Retro-Recomp, so the help stays at Ctrl+F1 and Ctrl+Alt+H. */
static int player_host_fkey(int key, SDL_Keymod mod) {
   if (key < SDL_SCANCODE_F1 || key > SDL_SCANCODE_F12) return 0;
   if ((ca.windowed && rrhk_ui()->menu) || ((mod & KMOD_CTRL) && !(mod & KMOD_ALT))) return 1;
   if (guest_keyboard && key <= RRC_GUEST_FKEY_LAST) return 0;
   return rrhk_options_host_fkey(key, mod, false);
}

/* The Return key of the guest: Start of the first player (any binding), or -1 without the kit. */
static int player_start(void) {
   if (!ca.windowed) return -1;
   if (player_blocked() || !input_focus) return 0;
   return (ca.pad[0] & RRC_BIT(RRC_START)) != 0;
}
static int player_pad_start(void) {
   SDL_GameController *pad = ca.windowed ? rrhk_ui()->pads[0] : NULL;
   return pad && SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_START);
}

/* A key bound to a button of player 1 is that button (decision of 28 October 2026, "same rules on every machine"): while
 * autofire releases the button, the key the guest reads is released too. -1: not such a key. */
static int player_face_alias(unsigned scan) {
   unsigned action;
   if (!ca.windowed || guest_keyboard || !scan) return -1;
   for (action = RRC_BUTTON_A; action <= RRC_BUTTON_B; action++)
      if ((unsigned)rrhk_ui()->keys[0][action] == scan) return !player_blocked() && input_focus && (ca.pad[0] & RRC_BIT(action)) != 0;
   return -1;
}

/* The mouse of a mouse game: the buttons are Button A and Button B (with their autofire), the directions of the first
 * player and the stick move the pointer. */
static int player_mouse(unsigned id, int value) {
   if (!mouse_game || !ca.windowed || !input_focus || player_blocked()) return value;
   if (id == RETRO_DEVICE_ID_MOUSE_LEFT) return (ca.pad[0] & RRC_BIT(RRC_BUTTON_A)) != 0;
   if (id == RETRO_DEVICE_ID_MOUSE_RIGHT) return (ca.pad[0] & RRC_BIT(RRC_BUTTON_B)) != 0;
   if (id == RETRO_DEVICE_ID_MOUSE_X || id == RETRO_DEVICE_ID_MOUSE_Y) {
      int horizontal = id == RETRO_DEVICE_ID_MOUSE_X;
      SDL_GameController *pad = rrhk_ui()->pads[0];
      int step = ((ca.pad[0] & RRC_BIT(horizontal ? RRC_RIGHT : RRC_DOWN)) != 0) - ((ca.pad[0] & RRC_BIT(horizontal ? RRC_LEFT : RRC_UP)) != 0);
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

/* The picture keeps the aspect ratio of the machine. In the window and in Pixel mode it is the largest whole multiple of the
 * picture's own pixel grid, centred (the common integer rule, HOST_KIT.md divergence 9, applied to the window in phase 4: the
 * window used to stretch to the aspect-correct fit); only Fit mode fills the output. */
static bool x_game_rect(int rw, int rh, int mode, SDL_Rect *rect) {
   SDL_Rect dst;
   if (!width || !height) return false;
   dst.x = 0; dst.y = 0; dst.w = rw; dst.h = (int)round(rw / aspect_ratio);
   if (dst.h > rh) { dst.h = rh; dst.w = (int)round(rh * aspect_ratio); }
   if (mode != 2) {
      int scale = SDL_min(rw / (int)width, rh / (int)height);
      if (scale >= 1) { dst.w = (int)width * scale; dst.h = (int)height * scale; }
   }
   dst.x = (rw - dst.w) / 2; dst.y = (rh - dst.h) / 2;
   *rect = dst;
   return true;
}

/* ---- the machine ---- */
static bool x_fast_forward(void) {
   const Uint8 *state = SDL_GetKeyboardState(NULL);
   return input_focus && !player_blocked() && state && state[SDL_SCANCODE_F5] && player_host_fkey(SDL_SCANCODE_F5, SDL_GetModState());
}

static bool x_keyboard_pad(void) {
   SDL_Keymod mod = SDL_GetModState();
   return !guest_keyboard && !((mod & KMOD_CTRL) && (mod & KMOD_ALT));
}

/* The pointer's buttons are Button A and Button B of the first player while a mouse game holds the mouse. */
static bool x_action_held(int player, int action) {
   Uint32 buttons;
   if (player || !mouse_game || !mouse_grab || !input_focus || rrhk_ui()->menu || rrhk_ui()->paused) return false;
   buttons = SDL_GetMouseState(NULL, NULL);
   return action == RRC_BUTTON_A ? (buttons & SDL_BUTTON_LMASK) != 0 : action == RRC_BUTTON_B && (buttons & SDL_BUTTON_RMASK) != 0;
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
/* The keyboard's owner is kept per game, in the game's own player.cfg (player_load at the first frame): a game never
 * inherits it from the last game played. Each game starts with the game controls until the player chooses. */
static void x_settings_loaded(RrhkUi *ui) {
   (void)ui;
   guest_keyboard = false;
}

/* Ctrl+Alt+K and the F2 row: the keyboard goes to the computer (the keys bound to the pad stop, a real gamepad still plays)
 * or back to the game controls. The choice is written at once, so a game closed any way keeps it. */
/* Its texts are English and French through rrhk_tr, like the other computer notices: the five-language catalogue
 * (native/runtime_catalog.inc) is left untouched in 1.6.9 because the Mega Drive and Super Nintendo quick-state keys hash it. */
static void x_toggle_keyboard(void) {
   guest_keyboard = !guest_keyboard;
   if (guest_keyboard && !rrhk_ui()->pads[0])
      player_notice(rrhk_tr("Computer keyboard: no gamepad connected", "Clavier de l'ordinateur : aucune manette connectee"));
   else player_notice(guest_keyboard ? RRC_KEYBOARD_ON : "Game shortcuts: ON (F8/F9 save and load)");
   player_save();
}
static void x_option_rows(int slot, RrhkOptionRows *rows) {
   if (slot == 1)
      rrhk_option_row(rows, RRC_ROW_KEYBOARD, rrhk_tr("Keyboard (Ctrl+Alt+K): %s", "Clavier (Ctrl+Alt+K) : %s"),
                      guest_keyboard ? rrhk_tr("computer only", "ordinateur seul") : rrhk_tr("game controls", "commandes du jeu"));
}
static bool x_key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
   (void)ui; (void)running;
   if ((int)key != RRC_ROW_KEYBOARD) return false;
   x_toggle_keyboard();
   return true;
}

/* What a capture notice says: Ctrl+Alt+M or a press of the middle button (the wheel) releases the mouse; neither
 * computer's mouse had a middle button, so the guest never needs it. */
#define RRC_MOUSE_CAPTURED rrhk_tr("Mouse captured (Ctrl+Alt+M or middle click releases it)", \
                                   "Souris capturee (Ctrl+Alt+M ou clic du milieu pour la liberer)")

/* The mouse is captured (relative) only while the game runs in a focused window. */
static void x_sync_mouse(void) {
   bool wanted = mouse_grab && input_focus && !player_blocked();
   if (wanted != ca.relative) { SDL_SetRelativeMouseMode(wanted ? SDL_TRUE : SDL_FALSE); ca.relative = wanted; }
   if (player_blocked()) SDL_GetRelativeMouseState(NULL, NULL);   /* motion during a menu is not the guest's */
}
static void x_frame_start(void *window, void *renderer) {
   (void)renderer;
   if (!ca.started) {
      ca.started = true;
      SDL_SetWindowMinimumSize((SDL_Window *)window, 400, 340);
      player_load((SDL_Window *)window);
      if (mouse_game) { mouse_grab = true; player_notice(RRC_MOUSE_CAPTURED); }
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
   /* A function key handed to the guest never reaches the frontend. */
   if (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12 && !player_host_fkey(key, mod)) { rrhk_options_observe(e); return true; }
   /* A menu's Escape belongs entirely to the frontend until key release: it must not pause the guest or quit twice. */
   if (e->type == SDL_KEYUP && e->key.keysym.scancode == SDL_SCANCODE_ESCAPE) ca.escape_held = 0;
   if (e->type == SDL_KEYDOWN && e->key.keysym.scancode == SDL_SCANCODE_ESCAPE && ca.escape_held) { rrhk_options_observe(e); return true; }
   if (key == SDL_SCANCODE_ESCAPE && ui->menu) ca.escape_held = 1;
   if (ui->capturing) return false;
   /* A press of the middle button (the wheel) releases a captured mouse and never reaches the guest. */
   if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_MIDDLE && mouse_grab) {
      mouse_grab = false; player_notice(rrhk_tr("Mouse released", "Souris liberee")); return true;
   }
   if (e->type == SDL_MOUSEBUTTONUP && e->button.button == SDL_BUTTON_MIDDLE) return true;
   /* A click on an unknown computer game captures its mouse; menus and an unfocused window never do. */
   if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_LEFT && input_focus && !player_blocked() && !mouse_grab) {
      mouse_grab = true; player_notice(RRC_MOUSE_CAPTURED);
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
      else if (sym == SDLK_k) x_toggle_keyboard();
      else if (sym == SDLK_f) rrhk_toggle_autofire();
      else if (sym == SDLK_m) { mouse_grab = !mouse_grab; player_notice(mouse_grab ? RRC_MOUSE_CAPTURED : rrhk_tr("Mouse released", "Souris liberee")); }
      else if (sym == SDLK_PAGEUP || sym == SDLK_PAGEDOWN) { want_swap = true; swap_drive = (mod & KMOD_SHIFT) ? 1 : 0; swap_direction = sym == SDLK_PAGEUP ? -1 : 1; }
      else if (sym == SDLK_BACKSPACE) { want_eject = true; swap_drive = (mod & KMOD_SHIFT) ? 1 : 0; }
      return true;
   }
   if (key == SDL_SCANCODE_F11) { ui->paused = !ui->paused; return true; }
   if (key == SDL_SCANCODE_TAB && ui->menu == RRHK_MENU_HELP) { ca.help_page ^= 1; return true; }
   /* The Pause binding of either player, when no menu is open and the guest does not have the keyboard. */
   if (!ui->menu && !guest_keyboard && (key || button >= 0)) {
      unsigned p;
      for (p = 0; p < 2; p++) {
         int match = key ? ui->keys[p][RRC_PAUSE] == key : ui->buttons[p][RRC_PAUSE] == button;
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
   rrhk_menu_line(ctx, y, rr_tr("Tab: game / computer shortcuts"));
}
static bool x_help_page(RrhkUi *ui, const RrhkMenuCtx *ctx) {
   const char *const lines[] = {"Ctrl+Alt+K: full guest keyboard", rrhk_tr("Ctrl+Alt+M / middle click: mouse", "Ctrl+Alt+M / clic milieu : souris"), "Ctrl+Alt+F: rapid fire",
      RRC_HELP_DISKS "Ctrl+Alt+H: help", "Ctrl+Alt+O: options",
      "Ctrl+Alt+Enter: display mode", "Ctrl+Alt+Q: quit", "Ctrl+F1-F12: Retro-Recomp shortcuts"};
   unsigned n;
   (void)ui;
   if (!ca.help_page) return false;
   for (n = 0; n < sizeof lines / sizeof lines[0]; n++) rrhk_menu_line(ctx, RR_MENU_FIRST_LINE + (int)n * RR_MENU_LINE, rr_tr(lines[n]));
   rrhk_menu_line(ctx, RR_MENU_LAST_LINE, rr_tr("Tab: game / computer shortcuts"));
   return true;
}

/* Preferences written when the game closes, as the former host did (the keyboard's owner is the game's own, in player.cfg). */
static void player_store_exit(void) {
   const RrhkUi *ui = rrhk_ui();
   if (!ca.windowed || !ui->ini_file[0]) return;
   rr_display_save(ui->ini_file, ui->data_dir, RRC_INI_SECTION, L"autofire", ui->autofire != 0);
}
