/* The Nintendo 64's gamepad through the host kit's real loop, with no game (tools/n64_sticks_selftest.py).
 *
 * The kit's shell and the N64 adapter (native/hostkit/adapters/rrhk_n64.inc, included as n64_player.c includes it) are compiled as
 * an export compiles them, around a stub session that records what the adapter hands the core each frame (rr_n64_pad). One virtual
 * game controller is attached before the window opens (dummy video and audio drivers, a hidden window). It checks that
 *   - the left stick reaches the core as the kit reads it (rrhk_pad_axes, the player's dead zone, 0 % by default: the raw values),
 *     at several positions, with no button bit: the control stick's path is the one it was before 1.7.6;
 *   - the right stick's axes no longer reach the core (0 and 0), and past the kit's stick threshold each of its four directions
 *     presses its C button in the pad word (the default bindings RRHK_PAD_RSTICK_*), and nothing under the threshold;
 *   - Y and B, the former C-Up and C-Down, press nothing now; the four Stick rows show "Left stick" on the gamepad page;
 *   - the machine declares the 16:9 screen format (widescreen) and one stick.
 * No ROM, no visible window, no sound device; a few seconds of run time. Original RetroRecomp code: MIT. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "n64_machine/n64_session.h"
#include "platform_io.h"

static int failures;
#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

/* ---- what n64_player.c defines before it includes the adapter ---- */
#define PATH_CAP 2048
static RrN64Session *session;
static unsigned frame_limit, frame_number;
static bool quit_requested, restart_requested;
static unsigned event_count;
static FILE *frame_log;
static char state_slot[PATH_CAP];
static unsigned recorded_bits;
static int16_t recorded[4];
static int recorded_calls;
static bool player_frame(void);
static void player_inputs(int player, uint16_t word, const int16_t axes[4]) {
    if (player != 0) return;
    recorded_bits = word;
    memcpy(recorded, axes, sizeof recorded);
    ++recorded_calls;
}
static size_t player_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static void scripted_inputs(uint64_t frame) { (void)frame; }
static void gfx_changes_due(uint64_t frame) { (void)frame; }
static int state_save(const char *slot) { (void)slot; return 1; }
static int state_load(const char *slot) { (void)slot; return 1; }
static bool saves_allowed = true;
static bool saves_commit(void) { return false; }

/* ---- the stub session: what the adapter calls ---- */
static uint32_t pixels[320 * 240];
uint64_t rr_n64_frame_index(const RrN64Session *s) { (void)s; return frame_number; }
const uint32_t *rr_n64_picture(const RrN64Session *s, int *width, int *height) {
    (void)s;
    if (width) *width = 320;
    if (height) *height = 240;
    return pixels;
}
double rr_n64_aspect(const RrN64Session *s) { (void)s; return 4.0 / 3.0; }
void rr_n64_picture_frame(const RrN64Session *s, int *width, int *height) { (void)s; *width = 320; *height = 240; }
unsigned rr_n64_audio_rate(const RrN64Session *s) { (void)s; return 44100; }
double rr_n64_fps(const RrN64Session *s) { (void)s; return 60.0; }
int rr_n64_rumble(const RrN64Session *s, int player, uint16_t *strong, uint16_t *weak) {
    (void)s; (void)player; *strong = *weak = 0; return 0;
}
int rr_n64_option(RrN64Session *s, const char *key, const char *value) { (void)s; (void)key; (void)value; return 1; }
uint64_t rr_n64_interpreted_count(const RrN64Session *s) { (void)s; return 0; }
uint64_t rr_n64_digest(RrN64Session *s) { (void)s; return 0; }
static uint8_t save_memory[16];
uint8_t *rr_n64_save_memory(RrN64Session *s, size_t *size) { (void)s; *size = sizeof save_memory; return save_memory; }
void rr_n64_session_clock(RrN64Session *s, uint64_t clock) { (void)s; (void)clock; }
/* The fallback recording of an export is not part of the kit. */
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "F12 Record fallback hints: OFF"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#ifndef _WIN32
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

#include "hostkit/adapters/rrhk_n64.inc"

static SDL_Joystick *pad;
static void axis(SDL_GameControllerAxis which, int16_t value) { CHECK(SDL_JoystickSetVirtualAxis(pad, which, value) == 0); }
static void button(SDL_GameControllerButton which, bool down) { CHECK(SDL_JoystickSetVirtualButton(pad, which, down ? 1 : 0) == 0); }

/* The script: each step sets the pad, waits a few frames for SDL's events, then checks what the core was handed. */
typedef struct { int16_t lx, ly, rx, ry; bool y, b; unsigned bits; bool left_stick_through; } Step;
#define C_ALL (RR_N64_PAD_C_UP | RR_N64_PAD_C_DOWN | RR_N64_PAD_C_LEFT | RR_N64_PAD_C_RIGHT)
static const Step steps[] = {
    {0, 0, 0, 0, false, false, 0, true},                                  /* at rest */
    {12000, -20000, 0, 0, false, false, 0, true},                          /* the control stick, part way */
    {-32768, 32767, 0, 0, false, false, 0, true},                          /* the control stick at its corner */
    {-5000, 700, 0, 0, false, false, 0, true},                             /* a small push */
    {0, 0, 32767, 0, false, false, RR_N64_PAD_C_RIGHT, true},              /* the right stick: one C button per direction */
    {0, 0, -32768, 0, false, false, RR_N64_PAD_C_LEFT, true},
    {0, 0, 0, -32768, false, false, RR_N64_PAD_C_UP, true},
    {0, 0, 0, 32767, false, false, RR_N64_PAD_C_DOWN, true},
    {9000, 9000, 6000, -6000, false, false, 0, true},                      /* under the stick threshold: no C button */
    {20000, 0, 32767, 32767, false, false, RR_N64_PAD_C_RIGHT | RR_N64_PAD_C_DOWN, true},   /* both sticks at once */
    {0, 0, 0, 0, true, true, 0, true},                                     /* Y and B, the former C-Up and C-Down: nothing */
};
static unsigned step, step_frame;

static bool player_frame(void) {
    ++frame_number;
    if (step >= sizeof steps / sizeof steps[0]) { quit_requested = true; return true; }
    const Step *s = &steps[step];
    if (step_frame == 0) {
        axis(SDL_CONTROLLER_AXIS_LEFTX, s->lx); axis(SDL_CONTROLLER_AXIS_LEFTY, s->ly);
        axis(SDL_CONTROLLER_AXIS_RIGHTX, s->rx); axis(SDL_CONTROLLER_AXIS_RIGHTY, s->ry);
        button(SDL_CONTROLLER_BUTTON_Y, s->y); button(SDL_CONTROLLER_BUTTON_B, s->b);
    }
    if (++step_frame < 4) return true;
    /* What the kit reads of the left stick is what the core gets: the path before 1.7.6 handed rrhk_pad_axes' LX and LY on. */
    int16_t kit[RRHK_AXES] = {0, 0, 0, 0};
    CHECK(rrhk_pad_axes(0, frame_number, kit));
    /* 1.7.6 (HOST_KIT D29): the kit gives SDL's -32768 as -32767, the sticks symmetric for the core. */
    CHECK(kit[RRHK_AXIS_LX] == (s->lx < -32767 ? -32767 : s->lx) && kit[RRHK_AXIS_LY] == (s->ly < -32767 ? -32767 : s->ly));
    if (s->left_stick_through) CHECK(recorded[RRHK_AXIS_LX] == kit[RRHK_AXIS_LX] && recorded[RRHK_AXIS_LY] == kit[RRHK_AXIS_LY]);
    CHECK(recorded[RRHK_AXIS_RX] == 0 && recorded[RRHK_AXIS_RY] == 0);
    CHECK((recorded_bits & C_ALL) == s->bits);
    CHECK((recorded_bits & ~C_ALL) == 0);   /* the left stick drives no d-pad bit (one stick read as a stick) */
    if (failures) fprintf(stderr, "  step %u: bits %04x axes %d %d %d %d\n", step, recorded_bits, recorded[0], recorded[1], recorded[2],
                          recorded[3]);
    ++step;
    step_frame = 0;
    return true;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_GAMECONTROLLER) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }
    const int index = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
    CHECK(index >= 0);
    pad = index >= 0 ? SDL_JoystickOpen(index) : NULL;
    CHECK(pad != NULL);
    if (!pad) return 2;
    axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT, -32768); axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, -32768);
    const RrhkMachine *machine = rrhk_adapter();
    CHECK(machine->widescreen);
    CHECK(machine->analog_sticks == 1);
    for (int a = N_SUP; a <= N_SRIGHT; ++a) CHECK(n64_actions[a].pad_label && !strcmp(n64_actions[a].pad_label, "Left stick"));
    static const SDL_GameControllerButton c_rows[4] = {RRHK_PAD_RSTICK_UP, RRHK_PAD_RSTICK_DOWN, RRHK_PAD_RSTICK_LEFT, RRHK_PAD_RSTICK_RIGHT};
    for (int a = 0; a < 4; ++a) CHECK(n64_actions[N_CUP + a].pad[0] == c_rows[a]);
    const int status = player_run_windowed("N64 sticks");
    CHECK(status == 0);
    CHECK(step == sizeof steps / sizeof steps[0]);
    /* The kit's columns, as it left them: the C rows on the right stick for every player. */
    const RrhkUi *ui = rrhk_ui();
    for (int p = 0; p < 4; ++p) for (int a = 0; a < 4; ++a) CHECK(ui->buttons[p][N_CUP + a] == c_rows[a]);
    SDL_JoystickClose(pad);
    SDL_Quit();
    printf("%s: %u steps, %u frames, %d calls, %d failure(s)\n", failures ? "FAIL" : "PASS", step, frame_number, recorded_calls, failures);
    return failures ? 1 : 0;
}
