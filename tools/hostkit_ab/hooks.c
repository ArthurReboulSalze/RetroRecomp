/* Deterministic host harness for A/B runs of the windowed shell (tools/hostkit_ab.py).
 *
 * Built into a game next to its host sources, which are compiled with the SDL
 * calls below renamed to rrab_* (see hostkit_ab.py). The harness replaces, for the
 * host only:
 *   - the clock (a virtual one: SDL_Delay advances it, every read adds a
 *     microsecond), so pacing, notices and the audio reserve are repeatable;
 *   - the audio device (a model that drains the queue in whole periods of the
 *     virtual clock, or, for a device opened with a callback, runs that callback on the
 *     calling thread at every period boundary), logging every push, pause and clear with
 *     a hash of the PCM;
 *   - the keyboard, the mouse and the window focus (scripted);
 *   - the event stream (the script pushes real SDL events and drives virtual
 *     game controllers);
 *   - the end of every frame (SDL_RenderPresent): the picture the window would
 *     show is read back, hashed and, on request, saved.
 * Nothing here ships in a game; both sides of a comparison are built the same way.
 *
 * Environment: RRAB_SCRIPT (script), RRAB_OUT (output directory).
 * Script: one command per line, `<host loop iteration> <command> [arguments]`.
 *   press <KeyName> [shift|ctrlalt]   key down then up (names as SDL_GetScancodeFromName), with Shift or Ctrl+Alt held
 *   hold <KeyName> | release <KeyName>   scripted keyboard state and the events
 *   attach <p> | detach <p>   virtual game controller of player p (slot p of the harness, not a player)
 *   attachx <p> <vendor> <product> <name>   the same with its own identity, so its own GUID and name
 *   button <p> <Name> <0|1>   | axis <p> <Name> <value>
 *   mouse <x> <y> <mask>      window coordinates, SDL button mask; click: a left button press event
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
#ifdef RRAB_X68
static uint64_t call_hash = 14695981039346656037ull;   /* every answer to the core within one iteration, zeros too */
static unsigned calls;
#endif
static uint64_t audio_stream = 14695981039346656037ull;     /* every byte ever queued, hashed in order */
static unsigned long long audio_bytes;
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
static SDL_AudioCallback audio_callback;      /* a callback device (the NES ring): no queue */
static void *audio_userdata;
static int cursor_shown = 1;

static uint64_t fnv(uint64_t h, const void *data, size_t size) {
    const unsigned char *p = data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

static uint64_t fnv(uint64_t h, const void *data, size_t size);
static void finish(void) {
    if (events_log) fprintf(events_log, "A total %llu %016llx\n", audio_bytes, (unsigned long long)audio_stream);
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
    char name[128]; int p, value, consumed = 0; unsigned x, y, mask;
    if (sscanf(command, "press %127s", name) == 1) {
        Uint16 mod = (strstr(command, " shift") ? KMOD_LSHIFT : 0) | (strstr(command, " ctrlalt") ? KMOD_LCTRL | KMOD_LALT : 0);
        if (mod & KMOD_LSHIFT) push_key(SDL_SCANCODE_LSHIFT, 1, 0);
        if (mod & KMOD_LCTRL) { push_key(SDL_SCANCODE_LCTRL, 1, 0); push_key(SDL_SCANCODE_LALT, 1, 0); }
        push_key(scancode(name), 1, mod); push_key(scancode(name), 0, mod);
        if (mod & KMOD_LCTRL) { push_key(SDL_SCANCODE_LALT, 0, 0); push_key(SDL_SCANCODE_LCTRL, 0, 0); }
        if (mod & KMOD_LSHIFT) push_key(SDL_SCANCODE_LSHIFT, 0, 0);
    } else if (sscanf(command, "hold %127s", name) == 1) { held[scancode(name)] = 1; push_key(scancode(name), 1, 0); }
    else if (sscanf(command, "release %127s", name) == 1) { held[scancode(name)] = 0; push_key(scancode(name), 0, 0); }
    else if (sscanf(command, "attachx %d %u %u %n", &p, &x, &y, &consumed) >= 3 && consumed && p >= 0 && p < 4 && !joysticks[p]) {
        /* a controller with its own identity (USB vendor and product, name), hence its own GUID */
        static char names[4][64];
        snprintf(names[p], sizeof names[p], "%s", command + consumed);
        SDL_VirtualJoystickDesc desc; SDL_zero(desc);
        desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION; desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
        desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
        desc.vendor_id = (Uint16)x; desc.product_id = (Uint16)y; desc.name = names[p];
        int index = SDL_JoystickAttachVirtualEx(&desc);
        if (index < 0 || !(joysticks[p] = SDL_JoystickOpen(index))) exit(5);
    }
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
    else if (!strcmp(command, "click")) {      /* the left button of the mouse goes down, as an event (the mask stays the script's) */
        SDL_Event e; memset(&e, 0, sizeof e);
        e.type = SDL_MOUSEBUTTONDOWN; e.button.state = SDL_PRESSED; e.button.button = SDL_BUTTON_LEFT; e.button.clicks = 1;
        e.button.x = mouse_x; e.button.y = mouse_y; SDL_PushEvent(&e);
    }
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
Uint32 rrab_GetTicks(void) { return (Uint32)(virtual_us / 1000); }
void rrab_Delay(Uint32 ms) {
    init();
    if (events_log) fprintf(events_log, "D %u %u\n", iteration, ms);
    virtual_us += (Uint64)ms * 1000;
}

/* audio device model: whole periods leave the queue at the period boundaries of the virtual clock */
static void audio_advance(void) {
    if (!audio_playing || !audio_period_us) return;
    while (virtual_us >= audio_next_period) {
        if (audio_callback) {
            static Uint8 block[65536];
            audio_next_period += audio_period_us;
            audio_callback(audio_userdata, block, (int)audio_period_bytes);
            fprintf(events_log, "A b %u %016llx\n", iteration, (unsigned long long)fnv(14695981039346656037ull, block, audio_period_bytes));
            continue;
        }
        Uint32 take = audio_queue < audio_period_bytes ? audio_queue : audio_period_bytes;
        audio_queue -= take;
        audio_next_period += audio_period_us;
    }
}
SDL_AudioDeviceID rrab_OpenAudioDevice(const char *name, int capture, const SDL_AudioSpec *want, SDL_AudioSpec *have, int allowed) {
    (void)name; (void)capture; (void)allowed; init();
    *have = *want;
    audio_callback = want->callback; audio_userdata = want->userdata;
    audio_open_flag = 1;
    audio_period_bytes = (Uint32)want->samples * want->channels * 2;
    audio_period_us = (Uint64)want->samples * 1000000u / (Uint64)want->freq;
    fprintf(events_log, "A o %u %d %d %d\n", iteration, want->freq, want->channels, want->samples);
    return 2;
}
int rrab_QueueAudio(SDL_AudioDeviceID dev, const void *data, Uint32 size) {
    (void)dev; audio_advance();
    fprintf(events_log, "A q %u %u %016llx\n", iteration, size, (unsigned long long)fnv(14695981039346656037ull, data, size));
    audio_stream = fnv(audio_stream, data, size); audio_bytes += size;
    audio_queue += size; return 0;
}
Uint32 rrab_GetQueuedAudioSize(SDL_AudioDeviceID dev) { (void)dev; audio_advance(); return audio_queue; }
void rrab_LockAudioDevice(SDL_AudioDeviceID dev) { (void)dev; audio_advance(); }
void rrab_UnlockAudioDevice(SDL_AudioDeviceID dev) { (void)dev; }
void rrab_PauseAudioDevice(SDL_AudioDeviceID dev, int pause) {
    (void)dev; audio_advance();
    if (!pause && !audio_playing) audio_next_period = virtual_us + audio_period_us;
    audio_playing = !pause;
    fprintf(events_log, "A p %u %d queue %u\n", iteration, pause, audio_queue);
}
void rrab_ClearQueuedAudio(SDL_AudioDeviceID dev) { (void)dev; audio_queue = 0; fprintf(events_log, "A c %u\n", iteration); }
void rrab_CloseAudioDevice(SDL_AudioDeviceID dev) { (void)dev; audio_open_flag = 0; fprintf(events_log, "A x %u\n", iteration); }

/* The usable area of the display is the one of a desktop of 1920 x 1080 with a task bar (RRAB_DISPLAY=WxH overrides it): the
 * offscreen driver's own display is not a measure of anything, and the opening size of a window depends on it. */
int rrab_GetDisplayUsableBounds(int index, SDL_Rect *rect) {
    (void)index;
    const char *text = getenv("RRAB_DISPLAY");
    int w = 1920, h = 1040;
    if (text) sscanf(text, "%dx%d", &w, &h);
    rect->x = 0; rect->y = 0; rect->w = w; rect->h = h;
    return 0;
}

/* A title equal to the current one changes nothing and is not logged. */
void rrab_SetWindowTitle(SDL_Window *window, const char *title) {
    init();
    if (strcmp(SDL_GetWindowTitle(window), title)) fprintf(events_log, "T %u %s\n", iteration, title);
    SDL_SetWindowTitle(window, title);
}
/* Only a change of the pointer's visibility is logged. */
int rrab_ShowCursor(int toggle) {
    init();
    if (toggle >= 0 && (toggle != 0) != cursor_shown) { cursor_shown = toggle != 0; fprintf(events_log, "C %u %d\n", iteration, cursor_shown); }
    return SDL_ShowCursor(toggle);
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
#ifdef RRAB_X68
    fprintf(events_log, "H %u %u %016llx\n", iteration, calls, (unsigned long long)call_hash);   /* every answer to the core, zeros too */
    calls = 0; call_hash = 14695981039346656037ull;
#endif
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
#if defined(RRAB_X68)
/* The X68000 (a libretro frontend): every answer to the core that is not zero, as
 * `G iteration port device id value`; the mouse in relative mode and its capture. */
#include <libretro.h>
extern void retro_set_input_state(retro_input_state_t callback);
static retro_input_state_t real_input_state;
static int16_t logged_input_state(unsigned port, unsigned device, unsigned index, unsigned id) {
    int16_t value = real_input_state(port, device, index, id);
    unsigned long long record[4] = {port, device, id, (unsigned short)value};
    call_hash = fnv(call_hash, record, sizeof record); ++calls;
    if (value) { init(); fprintf(events_log, "G %u %u %u %u %d\n", iteration, port, device, id, value); }
    return value;
}
void rrab_set_input_state(retro_input_state_t callback) { real_input_state = callback; retro_set_input_state(logged_input_state); }
static int relative_x, relative_y;
Uint32 rrab_GetRelativeMouseState(int *x, int *y) {
    if (x) *x = mouse_x - relative_x;
    if (y) *y = mouse_y - relative_y;
    relative_x = mouse_x; relative_y = mouse_y; return mouse_mask;
}
int rrab_SetRelativeMouseMode(SDL_bool enabled) {
    init(); fprintf(events_log, "R %u %d\n", iteration, enabled == SDL_TRUE);
    return 0;
}
#elif defined(RRAB_SMS)
/* The Master System and Game Gear: the guest owns the loop. What the host hands to the machine is the pad byte of each player,
 * through glue_set_pad1/2 (the runner's frame callback and the host's refresh in the middle of a frame call them): logged
 * when it changes. The window is the only one the process has. */
#include "glue.h"
static unsigned pad_state[2];
static void log_pad(int which, uint8_t value, void (*real)(uint8_t)) {
    init();
    if (pad_state[which] != value) { pad_state[which] = value; fprintf(events_log, "G %u %d %02x\n", iteration, which + 1, value); }
    real(value);
}
void rrab_set_pad1(uint8_t value) { log_pad(0, value, glue_set_pad1); }
void rrab_set_pad2(uint8_t value) { log_pad(1, value, glue_set_pad2); }
SDL_Window *rrab_GetKeyboardFocus(void) { return SDL_GetWindowFromID(1); }
SDL_Window *rrab_GetMouseFocus(void) { return SDL_GetWindowFromID(1); }
/* A menu that waits for an event: the script of this iteration runs, then one event or sixteen virtual milliseconds. */
int rrab_WaitEventTimeout(SDL_Event *event, int timeout) {
    if (rrab_PollEvent(event)) return 1;
    rrab_Delay((Uint32)timeout);
    return 0;
}
/* The Light Phaser: the position and the trigger the host hands to the machine. */
void lightphaser_pointer(int x, int y, bool trigger);
void rrab_phaser(int x, int y, bool trigger) {
    init(); fprintf(events_log, "X %u %d %d %d\n", iteration, x, y, trigger);
    lightphaser_pointer(x, y, trigger);
}
#elif !defined(RRAB_NES)
extern bool rr16_frame(uint16_t p1, uint16_t p2);
bool rrab_frame(uint16_t p1, uint16_t p2) {
    init(); fprintf(events_log, "G %u %04x %04x\n", iteration, p1, p2);
    return rr16_frame(p1, p2);
}
#else
/* The NES: the two controller words and the Zapper, as the host hands them to the machine. */
extern void cyc_set_controller(int port, uint8_t buttons);
void rrab_set_controller(int port, uint8_t buttons) {
    init(); fprintf(events_log, "G %u %d %02x\n", iteration, port, buttons);
    cyc_set_controller(port, buttons);
}
extern void rr_nes_zapper_aim(int x, int y, bool trigger, bool offscreen);
void rrab_zapper_aim(int x, int y, bool trigger, bool offscreen) {
    init(); fprintf(events_log, "X %u %d %d %d%d\n", iteration, x, y, trigger, offscreen);
    rr_nes_zapper_aim(x, y, trigger, offscreen);
}
#endif
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
