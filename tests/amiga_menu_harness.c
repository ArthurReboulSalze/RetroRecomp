/* Original Retro-Recomp, MIT. The Amiga's own part of the player menus on the host kit: the keyboard row of the F2 options
 * ("Keyboard (Ctrl+Alt+K): game controls / computer only", from rrhk_computer.inc) and the Ctrl+Alt+K chord. The player is
 * compiled with stubs for the machine session (no vAmiga needed): only the adapter and the kit run. */
#include <SDL.h>
#define main rr_unused_player_main
#include "../native/amiga_machine/amiga_player.c"
#include "hostkit/hostkit_internal.h"
#undef main

/* The session is not part of this check. */
RrAmigaSession *rr_amiga_open(const RrAmigaGame *game, char *error, size_t error_size) { (void)game; (void)error; (void)error_size; return NULL; }
void rr_amiga_joystick(RrAmigaSession *s, unsigned bits) { (void)s; (void)bits; }
void rr_amiga_mouse(RrAmigaSession *s, int dx, int dy, int left, int right) { (void)s; (void)dx; (void)dy; (void)left; (void)right; }
void rr_amiga_keys(RrAmigaSession *s, const uint8_t held[128]) { (void)s; (void)held; }
int rr_amiga_frame(RrAmigaSession *s) { (void)s; return -1; }
const char *rr_amiga_error(const RrAmigaSession *s) { (void)s; return "stub"; }
const uint32_t *rr_amiga_picture(const RrAmigaSession *s, int *width, int *height) { (void)s; *width = RR_AMIGA_PICTURE_WIDTH; *height = RR_AMIGA_PICTURE_LINES_PAL; return NULL; }
size_t rr_amiga_audio(RrAmigaSession *s, int16_t *pcm, size_t capacity) { (void)s; (void)pcm; (void)capacity; return 0; }
void rr_amiga_frame_info(const RrAmigaSession *s, RrAmigaFrameInfo *info) { (void)s; memset(info, 0, sizeof *info); }
int rr_amiga_set_native(RrAmigaSession *s, int enabled) { (void)s; (void)enabled; return 1; }
void rr_amiga_set_observe(RrAmigaSession *s, int enabled) { (void)s; (void)enabled; }
int rr_amiga_write_observations(const RrAmigaSession *s, const char *path) { (void)s; (void)path; return 1; }
uint64_t rr_amiga_native_count(const RrAmigaSession *s) { (void)s; return 0; }
uint64_t rr_amiga_interpreted_count(const RrAmigaSession *s) { (void)s; return 0; }
long rr_amiga_resload_calls(const RrAmigaSession *s) { (void)s; return 0; }
int rr_amiga_write_resload_log(const RrAmigaSession *s, const char *path) { (void)s; (void)path; return 1; }
int rr_amiga_state_save(RrAmigaSession *s, const char *path, const char *abi) { (void)s; (void)path; (void)abi; return 4; }
int rr_amiga_state_load(RrAmigaSession *s, const char *path, const char *abi) { (void)s; (void)path; (void)abi; return 1; }

static unsigned checks, failures;
static bool harness_running = true;
static void check(int okay, const char *name) { checks++; if (!okay) { failures++; fprintf(stderr, "FAIL: %s\n", name); } }
static bool press(SDL_Scancode scan, SDL_Keymod mod) {
   SDL_Event e;
   memset(&e, 0, sizeof e); e.type = SDL_KEYDOWN; e.key.keysym.scancode = scan; e.key.keysym.sym = SDL_GetKeyFromScancode(scan); e.key.keysym.mod = mod;
   return rrhk_adapter()->event(&e, &harness_running);
}

int main(int argc, char **argv) {
   const RrhkMachine *machine;
   RrhkUi *ui;
   FILE *f;
   (void)argc; (void)argv;
   SDL_SetMainReady(); SDL_setenv("SDL_VIDEODRIVER", "dummy", 1); SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
   if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_GAMECONTROLLER)) return 2;
   machine = rrhk_adapter();
   rrhk_bind(machine); rrhk_load_bindings(); rrhk_options_init(L"Amiga"); rrhk_options_keyboard("Amiga", 10);
   ui = rrhk_ui(); ca.windowed = true;
   snprintf(player_config, sizeof player_config, "%s", "amiga-menu-player.cfg");
   check(machine->option_rows == x_option_rows, "the Amiga table offers the keyboard row of the F2 options");
   check(machine->key_event == x_key_event, "the Amiga table hands the row's key to the computer part");
   x_settings_loaded(ui);
   check(!guest_keyboard, "a game starts with the game controls (the keyboard's owner is per game, never read from the shared ini)");
   check(!machine->key_event(ui, SDL_SCANCODE_K, &harness_running) && !guest_keyboard, "a real K does not toggle the keyboard");
   check(machine->key_event(ui, (SDL_Scancode)RRC_ROW_KEYBOARD, &harness_running) && guest_keyboard, "the F2 row gives the keyboard to the computer");
   check(!x_keyboard_pad(), "with the computer keyboard, the keys bound to the pad stop");
   check(machine->key_event(ui, (SDL_Scancode)RRC_ROW_KEYBOARD, &harness_running) && !guest_keyboard, "the F2 row gives it back to the game controls");
   check(x_keyboard_pad(), "with the game controls, the keyboard plays the pad");
   check(press(SDL_SCANCODE_K, (SDL_Keymod)(KMOD_CTRL | KMOD_ALT)) && guest_keyboard, "Ctrl+Alt+K is the same switch");
   press(SDL_SCANCODE_K, (SDL_Keymod)(KMOD_CTRL | KMOD_ALT));
   check(!guest_keyboard, "Ctrl+Alt+K switches back");
   f = fopen(player_config, "wb");
   if (f) { fputs("fullscreen=0 keyboard=1 autofire=0 width=900 height=675\n", f); fclose(f); }
   player_load(NULL);
   check(guest_keyboard, "the game's own player.cfg gives the keyboard back to the computer");
   remove(player_config);
   printf("%u checks, %u failures\n", checks, failures);
   SDL_Quit();
   return failures ? 1 : 0;
}
