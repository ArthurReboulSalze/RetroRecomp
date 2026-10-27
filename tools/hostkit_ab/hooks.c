/* Deterministic host harness for A/B runs of the windowed shell (tools/hostkit_ab.py).
 *
 * Built into a game next to its host sources, which are compiled with the SDL
 * calls below renamed to rrab_* (see hostkit_ab.py). The harness replaces, for the
 * host only:
 *   - the clock (a virtual one: SDL_Delay advances it, every read adds a
 *     microsecond), so pacing, notices and the audio reserve are repeatable;
 *   - the audio device (a model that drains the queue in whole periods of the
 *     virtual clock), logging every push, pause and clear with a hash of the PCM;
 *   - the keyboard, the mouse and the window focus (scripted);
 *   - the event stream (the script pushes real SDL events and drives virtual
 *     game controllers);
 *   - the end of every frame (SDL_RenderPresent): the picture the window would
 *     show is read back, hashed and, on request, saved.
 * Nothing here ships in a game; both sides of a comparison are built the same way.
 *
 * Environment: RRAB_SCRIPT (script), RRAB_OUT (output directory).
 * Script: one command per line, `<host loop iteration> <command> [arguments]`.
 *   press <KeyName> [shift]   key down then up (names as SDL_GetScancodeFromName)
 *   hold <KeyName> | release <KeyName>   scripted keyboard state and the events
 *   attach <p> | detach <p>   virtual game controller of player p
 *   button <p> <Name> <0|1>   | axis <p> <Name> <value>
 *   mouse <x> <y> <mask>      window coordinates, SDL button mask
 *   capture <file.bmp>        save the next presented picture
 *   quit                      push SDL_QUIT
 */
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *script, *frames_log, *events_log;
static char pending_line[1024];
static unsigned pending_due, iteration;
static int has_line, initialized, iteration_started;
static Uint64 virtual_us;
static Uint8 held[SDL_NUM_SCANCODES];
static int mouse_x, mouse_y;
static Uint32 mouse_mask;
static SDL_Joystick *joysticks[4];
static char capture_path[1024];

/* audio model */
static int audio_open_flag, audio_playing;
static Uint32 audio_queue, audio_period_bytes;
static Uint64 audio_next_period;
static Uint64 audio_period_us;

static uint64_t fnv(uint64_t h, const void *data, size_t size) {
    const unsigned char *p = data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

static void finish(void) {
    if (frames_log) fclose(frames_log);
    if (events_log) fclose(events_log);
    frames_log = events_log = NULL;
}

static void next_line(void);
static void init(void) {
    if (initialized) return;
    initialized = 1;
    const char *path = getenv("RRAB_SCRIPT"), *out = getenv("RRAB_OUT");
    if (!path || !out) { fprintf(stderr, "rrab: RRAB_SCRIPT and RRAB_OUT are required\n"); exit(5); }
    char name[1200];
    snprintf(name, sizeof name, "%s/frames.log", out); frames_log = fopen(name, "wb");
    snprintf(name, sizeof name, "%s/events.log", out); events_log = fopen(name, "wb");
    script = fopen(path, "rb");
    if (!script || !frames_log || !events_log) { fprintf(stderr, "rrab: cannot open script or output\n"); exit(5); }
    atexit(finish);
    next_line();
}

static void next_line(void) {
    char line[1100];
    has_line = 0;
    while (fgets(line, sizeof line, script)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (sscanf(line, "%u %1000[^\r\n]", &pending_due, pending_line) != 2) { fprintf(stderr, "rrab: bad line %s", line); exit(5); }
        has_line = 1; return;
    }
}

static void push_key(SDL_Scancode code, int down, Uint16 mod) {
    SDL_Event e; memset(&e, 0, sizeof e);
    e.type = down ? SDL_KEYDOWN : SDL_KEYUP;
    e.key.state = down ? SDL_PRESSED : SDL_RELEASED;
    e.key.keysym.scancode = code;
    e.key.keysym.sym = SDL_GetKeyFromScancode(code);
    e.key.keysym.mod = mod;
    SDL_PushEvent(&e);
}

static SDL_Scancode scancode(const char *name) {
    char spelled[128];
    snprintf(spelled, sizeof spelled, "%s", name);
    for (char *c = spelled; *c; ++c) if (*c == '_') *c = ' ';   /* Left_Shift, Keypad_8 */
    SDL_Scancode code = SDL_GetScancodeFromName(spelled);
    if (!code) { fprintf(stderr, "rrab: unknown key %s\n", name); exit(5); }
    return code;
}

static void run_command(const char *command) {
    char name[128]; int p, value; unsigned x, y, mask;
    if (sscanf(command, "press %127s", name) == 1) {
        Uint16 mod = strstr(command, " shift") ? KMOD_LSHIFT : 0;
        if (mod) push_key(SDL_SCANCODE_LSHIFT, 1, 0);
        push_key(scancode(name), 1, mod); push_key(scancode(name), 0, mod);
        if (mod) push_key(SDL_SCANCODE_LSHIFT, 0, 0);
    } else if (sscanf(command, "hold %127s", name) == 1) { held[scancode(name)] = 1; push_key(scancode(name), 1, 0); }
    else if (sscanf(command, "release %127s", name) == 1) { held[scancode(name)] = 0; push_key(scancode(name), 0, 0); }
    else if (sscanf(command, "attach %d", &p) == 1 && p >= 0 && p < 4 && !joysticks[p]) {
        int index = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        if (index < 0 || !(joysticks[p] = SDL_JoystickOpen(index))) exit(5);
    } else if (sscanf(command, "detach %d", &p) == 1 && p >= 0 && p < 4 && joysticks[p]) {
        SDL_JoystickID id = SDL_JoystickInstanceID(joysticks[p]); SDL_JoystickClose(joysticks[p]); joysticks[p] = NULL;
        for (int i = 0; i < SDL_NumJoysticks(); ++i) if (SDL_JoystickGetDeviceInstanceID(i) == id) SDL_JoystickDetachVirtual(i);
    } else if (sscanf(command, "button %d %127s %d", &p, name, &value) == 3 && p >= 0 && p < 4 && joysticks[p]) {
        SDL_GameControllerButton b = SDL_GameControllerGetButtonFromString(name);
        if (b == SDL_CONTROLLER_BUTTON_INVALID || SDL_JoystickSetVirtualButton(joysticks[p], b, (Uint8)value)) exit(5);
        SDL_JoystickUpdate();
    } else if (sscanf(command, "axis %d %127s %d", &p, name, &value) == 3 && p >= 0 && p < 4 && joysticks[p]) {
        SDL_GameControllerAxis a = SDL_GameControllerGetAxisFromString(name);
        if (a == SDL_CONTROLLER_AXIS_INVALID || SDL_JoystickSetVirtualAxis(joysticks[p], a, (Sint16)value)) exit(5);
        SDL_JoystickUpdate();
    } else if (sscanf(command, "mouse %u %u %u", &x, &y, &mask) == 3) { mouse_x = (int)x; mouse_y = (int)y; mouse_mask = mask; }
    else if (sscanf(command, "capture %127s", name) == 1) snprintf(capture_path, sizeof capture_path, "%s/%s", getenv("RRAB_OUT"), name);
    else if (!strcmp(command, "quit")) { SDL_Event e; memset(&e, 0, sizeof e); e.type = SDL_QUIT; SDL_PushEvent(&e); }
    else { fprintf(stderr, "rrab: unknown command %s\n", command); exit(5); }
}

/* The script of one host loop iteration runs when the loop first polls events. */
int rrab_PollEvent(SDL_Event *event) {
    init();
    if (!iteration_started) {
        iteration_started = 1;
        while (has_line && pending_due <= iteration) {
            if (pending_due < iteration) { fprintf(stderr, "rrab: late command %s\n", pending_line); exit(5); }
            run_command(pending_line); next_line();
        }
    }
    return SDL_PollEvent(event);
}
const Uint8 *rrab_GetKeyboardState(int *count) { if (count) *count = SDL_NUM_SCANCODES; return held; }
Uint32 rrab_GetMouseState(int *x, int *y) { if (x) *x = mouse_x; if (y) *y = mouse_y; return mouse_mask; }
Uint32 rrab_GetWindowFlags(SDL_Window *window) { return SDL_GetWindowFlags(window) | SDL_WINDOW_INPUT_FOCUS | SDL_WINDOW_MOUSE_FOCUS; }

/* virtual clock: microseconds */
Uint64 rrab_GetPerformanceFrequency(void) { return 1000000; }
Uint64 rrab_GetPerformanceCounter(void) { return virtual_us++; }
Uint64 rrab_GetTicks64(void) { return virtual_us / 1000; }
void rrab_Delay(Uint32 ms) {
    init();
    if (events_log) fprintf(events_log, "D %u %u\n", iteration, ms);
    virtual_us += (Uint64)ms * 1000;
}

/* audio device model: whole periods leave the queue at the period boundaries of the virtual clock */
static void audio_advance(void) {
    if (!audio_playing || !audio_period_us) return;
    while (virtual_us >= audio_next_period) {
        Uint32 take = audio_queue < audio_period_bytes ? audio_queue : audio_period_bytes;
        audio_queue -= take;
        audio_next_period += audio_period_us;
    }
}
SDL_AudioDeviceID rrab_OpenAudioDevice(const char *name, int capture, const SDL_AudioSpec *want, SDL_AudioSpec *have, int allowed) {
    (void)name; (void)capture; (void)allowed; init();
    *have = *want;
    audio_open_flag = 1;
    audio_period_bytes = (Uint32)want->samples * want->channels * 2;
    audio_period_us = (Uint64)want->samples * 1000000u / (Uint64)want->freq;
    fprintf(events_log, "A o %u %d %d %d\n", iteration, want->freq, want->channels, want->samples);
    return 2;
}
int rrab_QueueAudio(SDL_AudioDeviceID dev, const void *data, Uint32 size) {
    (void)dev; audio_advance();
    fprintf(events_log, "A q %u %u %016llx\n", iteration, size, (unsigned long long)fnv(14695981039346656037ull, data, size));
    audio_queue += size; return 0;
}
Uint32 rrab_GetQueuedAudioSize(SDL_AudioDeviceID dev) { (void)dev; audio_advance(); return audio_queue; }
void rrab_PauseAudioDevice(SDL_AudioDeviceID dev, int pause) {
    (void)dev; audio_advance();
    if (!pause && !audio_playing) audio_next_period = virtual_us + audio_period_us;
    audio_playing = !pause;
    fprintf(events_log, "A p %u %d queue %u\n", iteration, pause, audio_queue);
}
void rrab_ClearQueuedAudio(SDL_AudioDeviceID dev) { (void)dev; audio_queue = 0; fprintf(events_log, "A c %u\n", iteration); }
void rrab_CloseAudioDevice(SDL_AudioDeviceID dev) { (void)dev; audio_open_flag = 0; fprintf(events_log, "A x %u\n", iteration); }

void rrab_SetWindowTitle(SDL_Window *window, const char *title) {
    init(); fprintf(events_log, "T %u %s\n", iteration, title); SDL_SetWindowTitle(window, title);
}
int rrab_SetWindowFullscreen(SDL_Window *window, Uint32 flags) {
    init(); int r = SDL_SetWindowFullscreen(window, flags); fprintf(events_log, "F %u %u -> %d\n", iteration, flags, r); return r;
}

/* the end of an iteration: read back what the window shows */
void rrab_RenderPresent(SDL_Renderer *renderer) {
    init();
    int w = 0, h = 0; SDL_GetRendererOutputSize(renderer, &w, &h);
    SDL_Surface *image = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!image || SDL_RenderReadPixels(renderer, NULL, SDL_PIXELFORMAT_ARGB8888, image->pixels, image->pitch)) { fprintf(stderr, "rrab: readback failed: %s\n", SDL_GetError()); exit(5); }
    uint64_t h64 = 14695981039346656037ull;
    for (int y = 0; y < h; ++y) h64 = fnv(h64, (const char *)image->pixels + (size_t)y * image->pitch, (size_t)w * 4);
    fprintf(frames_log, "P %u %016llx %dx%d\n", iteration, (unsigned long long)h64, w, h);
    if (capture_path[0]) {
        if (SDL_SaveBMP(image, capture_path)) { fprintf(stderr, "rrab: cannot save %s\n", capture_path); exit(5); }
        capture_path[0] = 0;
    }
    SDL_FreeSurface(image);
    SDL_RenderPresent(renderer);
    ++iteration; iteration_started = 0;
}

/* What the host hands to the machine, logged and passed on: the pad words, the extra
 * CPS-1 pads and the pointer. */
extern bool rr16_frame(uint16_t p1, uint16_t p2);
bool rrab_frame(uint16_t p1, uint16_t p2) {
    init(); fprintf(events_log, "G %u %04x %04x\n", iteration, p1, p2);
    return rr16_frame(p1, p2);
}
#ifdef RRAB_CPS1
extern void rr_cps1_set_extra_pads(uint16_t p3, uint16_t p4);
void rrab_extra_pads(uint16_t p3, uint16_t p4) {
    init(); fprintf(events_log, "E %u %04x %04x\n", iteration, p3, p4);
    rr_cps1_set_extra_pads(p3, p4);
}
#endif
#ifdef RRAB_GUN
#include "gun16.h"
void rrab_gun_input(Rr16GunInput in) {
    init();
    fprintf(events_log, "X %u %d %d %d%d%d%d%d%d%d\n", iteration, in.x, in.y, in.fire, in.aux, in.secondary,
            in.start, in.turbo, in.pause, in.offscreen);
    rr16_gun_input(in);
}
#endif
