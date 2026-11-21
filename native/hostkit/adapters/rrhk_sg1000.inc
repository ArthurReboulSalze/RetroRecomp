/* SG-1000 adapter for the host kit (docs/HOST_KIT.md, docs/SG1000.md; a console: two pads, the Pause button, no keyboard). Original
 * Retro-Recomp code, MIT.
 *
 * Included by native/sg1000_machine/sg1000_player.c, which owns the machine (sg1000_glue.inc: the `machine` variable) and the quick
 * states (sg1000_state_file.inc). The guest owns the loop (the translated Z80 code runs until a frame ends): the game opens the window
 * with sg_host_open and calls sg_host_frame at the end of each guest frame (RrhkMachine.driven, as the Master System and the MSX).
 * Nothing of the computers' adapter (rrhk_computer.inc: the guest keyboard, the function keys handed to the guest, the captured
 * mouse) is used: the machine has two pads and a Pause button, and every hook that file provides is left NULL, which the kit reads as
 * "none" (as the Master System's adapter leaves them).
 *
 * What is the SG-1000's: the two pads (the D-pad and buttons 1 and 2, the bits of the machine's `pad[]`); Pause, bit 6 of each
 * seat's word (an ordinary action row, so a match carries it): the machine raises /NMI once on the press edge, from the word it kept last frame
 * (sg_pad_word), as the console's button does, and the kit pauses nothing itself (RrhkMachine.host_pause stays 0: the game's own pause runs);
 * the TMS9918A picture, 256 x 192 colour indices through the chip's sixteen colours with the border of each line around it (the
 * MSX1's view and palette: the same chip); the sound, the SN76489A's mono samples doubled into the shared stereo ring of
 * native/audio_output.inc. Quick states (F8/F9) are the game's (sg1000_state_file.inc), saved and loaded at once: the kit calls them
 * from the frame's end, which is already the game's service point. Multiplayer: an in-process snapshot and the digest
 * (sg1000_state_file.inc: the state's body without the picture), rollback; no cartridge save, so session_save* stay NULL. Nothing here says how long a press takes to reach the picture: that is not measured. */
#include "hostkit/hostkit.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "display_settings.h"

/* The actions, in menu order. The bits of the first six are the machine's SG_PAD_* (the order of the enum is the order of the bits);
 * Pause is the host's own (bit 0): the machine never sees it in a pad word. Player 1 plays on the arrows, S (button 1) and D (button 2),
 * player 2 on the numeric keypad, as on the Master System; Enter pauses. */
enum { S_UP, S_DOWN, S_LEFT, S_RIGHT, S_B1, S_B2, S_PAUSE, S_ACTIONS };
static const RrhkAction s_actions[S_ACTIONS] = {
   {"Up", L"Up", SG_PAD_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
   {"Down", L"Down", SG_PAD_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
   {"Left", L"Left", SG_PAD_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
   {"Right", L"Right", SG_PAD_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
   {"Button 1", L"Button1", SG_PAD_B1, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
   {"Button 2", L"Button2", SG_PAD_B2, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
   {"Pause", L"Pause", SG_PAD_PAUSE, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}}};

/* ---- the picture: the TMS9918A's 256 x 192 with eight border pixels around it (the MSX1's view, the same chip) ---- */
enum { S_VIEW_W = TMS_WIDTH + 16, S_VIEW_H = TMS_HEIGHT + 16 };
static uint32_t s_view[S_VIEW_W * S_VIEW_H];
/* The TMS9918A's sixteen colours (a commonly published approximation of its analogue output; not measured on a set). Index 0 is
 * transparent: the chip puts the backdrop colour there before the picture reaches the host, so it only shows as black when the backdrop
 * is colour 0 itself. The values are the MSX adapter's. */
static const uint32_t s_palette[16] = {
   0xFF000000, 0xFF000000, 0xFF21C842, 0xFF5EDC78, 0xFF5455ED, 0xFF7D76FC, 0xFFD4524D, 0xFF42EBF5,
   0xFFFC5554, 0xFFFF7978, 0xFFD4C154, 0xFFE6CE80, 0xFF21B03B, 0xFFC95BBA, 0xFFCCCCCC, 0xFFFFFFFF};

static void s_picture(const SgMachine *m) {
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

static void s_sound(SgMachine *m) {
   static int16_t mono[SG_AUDIO_BUFFER], stereo[2 * SG_AUDIO_BUFFER];
   unsigned n = sg_audio_take(m, mono, SG_AUDIO_BUFFER);
   if (rrhk_session_silent()) return;            /* a frame run again after a multiplayer correction: no sound */
   for (unsigned i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
   host_audio_submit(stereo, n);
}

/* ---- the machine table ---- */
static struct { bool reset; uint64_t frame; uint16_t pad[2]; } sh;

static int s_players(void) { return 2; }
/* The kit hands the pad words of the frame to come; the game takes them at the end of sg_host_frame. */
static bool s_run_frame(uint16_t p1, uint16_t p2) { sh.pad[0] = p1; sh.pad[1] = p2; return true; }
/* The shell calls this at every frame start: only a change empties the ring (the sound held before a pause is not played after it). */
static void s_pause_machine(bool paused) {
   static bool was;
   if (paused == was) return;
   was = paused;
   audio_output_clear();
}
/* The guest owns the loop: a reset is a request the game takes at the end of the frame (sg_host_frame returns 2); the shell keeps running. */
static void s_reset(void) { sh.reset = true; }
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
static bool s_state_file(const wchar_t *path, bool load) { return sg_game_state_file(path, load); }
static bool s_state_path(wchar_t *path, size_t capacity) { return sg_game_state_path(path, capacity); }

static void s_help_lines(int slot, const char **lines, int *count) {
   if (slot == 1) lines[(*count)++] = rrhk_tr("Enter  Pause", "Entree  Pause");
}

static void s_help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
   (void)ui;
   rrhk_menu_line(ctx, y, rrhk_tr("Arrows: pad 1; S: button 1, D: button 2; Enter: Pause",
                                  "Fleches : manette 1 ; S : bouton 1, D : bouton 2 ; Entree : Pause"));
   rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Player 2: numeric keypad (8, 9: buttons; 7: Pause)",
                                                 "Joueur 2 : pave numerique (8, 9 : boutons ; 7 : Pause)"));
}

const RrhkMachine *rrhk_adapter(void) {
   static RrhkMachine adapter;
   if (!adapter.actions) {
      memset(&adapter, 0, sizeof adapter);
      adapter.ini_section = L"SG1000"; adapter.console_name = "SG-1000";
      adapter.table_players = 2; adapter.players = s_players;
      adapter.actions = s_actions; adapter.action_count = S_ACTIONS;
      adapter.up = S_UP; adapter.down = S_DOWN; adapter.left = S_LEFT; adapter.right = S_RIGHT; adapter.start = S_PAUSE;
      adapter.max_width = S_VIEW_W; adapter.max_height = S_VIEW_H;
      adapter.frame_seconds = (double)SG_CYCLES_PER_LINE * SG_LINES_NTSC / SG_CPU_CLOCK;
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
      adapter.snap_bound = sg_snap_bound; adapter.snap_save = sg_snap_save; adapter.snap_load = sg_snap_load; adapter.digest = sg_snap_digest;
      adapter.help_lines = s_help_lines; adapter.help_controls = s_help_controls;
   }
   return &adapter;
}

/* ---- what the game calls ---- */
static bool sg_host_open(const char *title, int scale, const SgMachine *m) {
   RrhkMachine *adapter = (RrhkMachine *)rrhk_adapter();
   /* The pace of the frames: the board's lines (262 NTSC, 313 PAL). */
   adapter->frame_seconds = (double)SG_CYCLES_PER_LINE * m->lines_per_frame / SG_CPU_CLOCK;
   if (!rrhk_open(adapter, title, scale)) return false;
   rrhk_autofire_reset();
   host_audio_init(SG_AUDIO_RATE);
   rrhk_notice(rrhk_tr("F1: help | Enter: pause", "F1 : aide | Entree : pause"), 2400);
   return true;
}

/* The end of a guest frame: the picture and the sound out, the window's events and menus, the pads of the next frame in.
 * 0: go on; 1: quit; 2: reset. */
static int sg_host_frame(SgMachine *m) {
   if (!rrhk_session_silent()) s_picture(m);    /* a frame run again after a correction is never shown */
   s_sound(m);
   const bool running = rrhk_frame_done();
   sh.frame++;
   sg_pad_word(m, 0, (uint16_t)(sh.pad[0] & SG_PAD_MASK));   /* a press of Pause is one /NMI, from the word kept in the machine */
   sg_pad_word(m, 1, (uint16_t)(sh.pad[1] & SG_PAD_MASK));
   if (sh.reset) { sh.reset = false; audio_output_clear(); return 2; }
   return running ? 0 : 1;
}

static void sg_host_close(void) {
   host_audio_shutdown();
   rrhk_close();
   SDL_Quit();
}
