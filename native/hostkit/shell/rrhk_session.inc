/* Multiplayer session of the host kit (hostkit_session.h; multiplayer stage 0, .build/multiplayer/HOOKS.md). Included at the
 * end of rrhk_main.c (never compiled by itself), so that no machine's build list changes.
 *
 * Nothing here runs unless the converter's netplay worker started the game with RETRORECOMP_NETPLAY_PIPE: rrhk_session_on stays
 * false and the game plays alone exactly as before. In a session the game is a commanded stepper: once per frame it reports its
 * local pad, then executes the worker's commands in order (silent frames, snapshots of its own ring, digests, pause, notices)
 * until the live frame's RUN, which the loop then runs with the session's port words. The game never blocks on the pipe: it
 * waits at most part of a frame, then shows the last picture and asks again; a closed pipe ends the session.
 *
 * Original Retro-Recomp code, MIT. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hostkit/hostkit_internal.h"
#include "hostkit/hostkit_session.h"
#include "runtime_i18n.h"
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
typedef HANDLE RrhkPipe;
#define RRHK_NO_PIPE NULL
#else
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
typedef int RrhkPipe;
#define RRHK_NO_PIPE (-1)
#endif

bool rrhk_session_on;

static struct {
    RrhkPipe in, out;
    uint8_t rx[2 * (4 + RRHK_SESSION_MAX_PAYLOAD)];
    size_t rx_len;
    bool broken;                    /* the pipe closed, or a message broke the rules */
    uint16_t ports[RRHK_MAX_PLAYERS];
    bool silent;                    /* a re-simulated frame is running */
    int setup_ports;                /* the ports SETUP gave (rrhk_session_ports) */
    bool driven_silent;             /* a driven machine's guest runs a silent frame: done when it calls rrhk_frame_done */
    bool guest;
    bool paused;
    bool restart_pending;           /* the host asked to restart: reported in the LOCALs of one frame */
    bool restarting;                /* a driven machine restarts for everyone: its shell closes and opens again, the session
                                     * stays (pipes, frame count, setup) */
    uint8_t state_pending;          /* the host asked to save (1) or load (2) the match's state: in the LOCALs of one frame */
    uint8_t *state;                 /* the match's state (the host's F8 / F9 for everyone): one slot of snap_bound bytes, in
                                     * memory only, freed with the session; NULL on a machine without snapshots */
    size_t state_size, state_len;
    bool state_used;
    uint8_t *save_in;               /* the host's save image handed before SETUP (SAVE_IN), kept for a restart's put */
    size_t save_total, save_got;
    uint8_t options[RRHK_SESSION_MAX_PAYLOAD];      /* the host's run-changing options of SETUP, applied again then */
    uint16_t options_length;
    char paused_by[24];
    bool setup;                     /* SETUP received and applied: frames may run */
    Uint64 setup_until;             /* SETUP must come before this (SDL ticks) */
    uint32_t live;                  /* the frame the next live RUN must name */
    uint32_t last_run;              /* the last frame run, live or silent */
    bool local_sent;                /* LOCAL already reported for `live` */
    uint16_t word_sent, system_sent;   /* what that LOCAL said: a change of the system bits before the RUN is reported again */
    int8_t axes_sent[RRHK_AXES];    /* and this PC's sticks (a machine with sticks) */
    int8_t axes[RRHK_MAX_PLAYERS][RRHK_AXES];   /* every port's sticks of the frame being run (RRHK_RUN_AXES) */
    Uint64 ending_until;            /* the session ended: the message stays on screen until then, then the game closes */
    uint16_t exit_reason;           /* what EXIT says then (RRHK_EXIT_*): stopped by Retro-Recomp, lost, refused */
    int32_t ppm;                    /* time sync: added to the frame period */
    uint8_t *ring;                  /* depth slots of slot_size bytes */
    size_t slot_size;
    unsigned depth;
    uint32_t slot_frame[RRHK_SESSION_MAX_RING];
    size_t slot_len[RRHK_SESSION_MAX_RING];
    bool slot_used[RRHK_SESSION_MAX_RING];
} s = {RRHK_NO_PIPE, RRHK_NO_PIPE};

bool rrhk_session_active(void) { return rrhk_session_on; }
bool rrhk_session_silent(void) { return s.silent; }
int rrhk_session_ports(void) { return rrhk_session_on && s.setup_ports ? s.setup_ports : 0; }
bool rrhk_session_paused(void) { return rrhk_session_on && s.paused; }
uint16_t rrhk_session_port(int port) { return port >= 0 && port < RRHK_MAX_PLAYERS ? s.ports[port] : 0; }
bool rrhk_session_guest(void) { return rrhk_session_on && s.guest; }
bool rrhk_session_restart(void) {
    if (!rrhk_session_on) return false;
    if (s.guest) { rrhk_notice(rr_tr("Only the host can restart"), 1800); return false; }
    s.restart_pending = true;
    return true;
}
/* F8 / F9 (or the pad's Quick save / Quick load) in a session: the host's request goes to every seat at the same frame. The
 * match's state lives in memory for this match only; a player's own quick states are never read or written here. */
bool rrhk_session_states(void) { return rrhk_session_on && s.state && !s.guest; }
void rrhk_session_state(bool load) {
    if (!rrhk_session_on) return;
    if (!s.state) { rrhk_notice(rr_tr("Quick states are off in multiplayer"), 1800); return; }
    if (s.guest) { rrhk_notice(rr_tr("Only the host saves and loads"), 1800); return; }
    if (load && !s.state_used && s.state_pending != 1) { rrhk_notice(rr_tr("No state saved in this match"), 1800); return; }
    s.state_pending = load ? 2 : 1;
}
Uint64 rrhk_session_period(Uint64 period) {
    return s.ppm ? (Uint64)((double)period * (1.0 + (double)s.ppm / 1e6)) : period;
}
/* The sound's factor while the worker stretches the frame period by ppm (time sync): the frames come 1 + ppm slower, so the
 * machine's sound is stretched by as much (the same hook as Sync to display, rrhk_audio_set_base). */
double rrhk_session_audio_base(void) { return 1.0 + (double)s.ppm / 1e6; }

/* ---- the pipe ---- */

static bool pipe_from(const char *text, RrhkPipe *pipe) {
    char *end = NULL;
    const unsigned long long value = strtoull(text, &end, 10);
    if (end == text) return false;
#ifdef _WIN32
    *pipe = (HANDLE)(uintptr_t)value;
    return *pipe != NULL && *pipe != INVALID_HANDLE_VALUE;
#else
    if (value > 65535) return false;
    *pipe = (int)value;
    return fcntl(*pipe, F_GETFD) != -1;
#endif
}

static bool send_message(uint16_t type, const void *payload, size_t length) {
    if (s.broken || length > RRHK_SESSION_MAX_PAYLOAD) return false;
    uint8_t buffer[4 + RRHK_SESSION_MAX_PAYLOAD];
    buffer[0] = (uint8_t)type; buffer[1] = (uint8_t)(type >> 8);
    buffer[2] = (uint8_t)length; buffer[3] = (uint8_t)(length >> 8);
    if (length) memcpy(buffer + 4, payload, length);
    size_t done = 0, total = 4 + length;
    while (done < total) {
#ifdef _WIN32
        DWORD wrote = 0;
        if (!WriteFile(s.out, buffer + done, (DWORD)(total - done), &wrote, NULL) || !wrote) { s.broken = true; return false; }
#else
        const ssize_t wrote = write(s.out, buffer + done, total - done);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) { s.broken = true; return false; }
#endif
        done += (size_t)wrote;
    }
    return true;
}

/* What the pipe holds now, appended to rx; never waits. */
static void pump(void) {
    if (s.broken || s.rx_len >= sizeof s.rx) return;
#ifdef _WIN32
    DWORD available = 0;
    if (!PeekNamedPipe(s.in, NULL, 0, NULL, &available, NULL)) { s.broken = true; return; }
    if (!available) return;
    DWORD room = (DWORD)(sizeof s.rx - s.rx_len), got = 0;
    if (!ReadFile(s.in, s.rx + s.rx_len, available < room ? available : room, &got, NULL)) { s.broken = true; return; }
    s.rx_len += got;
#else
    const ssize_t got = read(s.in, s.rx + s.rx_len, sizeof s.rx - s.rx_len);
    if (got > 0) s.rx_len += (size_t)got;
    else if (got == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) s.broken = true;
#endif
}

/* Waits until the pipe has bytes or `milliseconds` passed (no busy loop). */
static void wait_input(unsigned milliseconds) {
#ifdef _WIN32
    const Uint64 until = SDL_GetTicks64() + milliseconds;
    for (;;) {
        DWORD available = 0;
        if (!PeekNamedPipe(s.in, NULL, 0, NULL, &available, NULL)) { s.broken = true; return; }
        if (available || SDL_GetTicks64() >= until) return;
        SDL_Delay(1);
    }
#else
    struct pollfd fd = {s.in, POLLIN, 0};
    while (poll(&fd, 1, (int)milliseconds) < 0 && errno == EINTR) {}
#endif
}

/* The next whole message in rx, removed from it: its type, its payload copied to `payload`. 0: none yet. */
static uint16_t take(uint8_t *payload, uint16_t *length) {
    if (s.rx_len < 4) return 0;
    const uint16_t type = (uint16_t)(s.rx[0] | s.rx[1] << 8), size = (uint16_t)(s.rx[2] | s.rx[3] << 8);
    if (size > RRHK_SESSION_MAX_PAYLOAD || !type) { s.broken = true; return 0; }
    if (s.rx_len < 4u + size) return 0;
    memcpy(payload, s.rx + 4, size);
    memmove(s.rx, s.rx + 4 + size, s.rx_len - 4 - size);
    s.rx_len -= 4u + size;
    *length = size;
    return type;
}

static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> 8 * i); }

static void refuse(uint16_t code, const char *text) {
    uint8_t payload[3 + 255];
    const size_t n = text ? strlen(text) : 0, kept = n > 255 ? 255 : n;
    put16(payload, code); payload[2] = (uint8_t)kept;
    if (kept) memcpy(payload + 3, text, kept);
    send_message(RRHK_MSG_REFUSED, payload, 3 + kept);
}

/* A name from the worker (already cleaned there), kept printable here too. */
/* A player's name in a notice: games draw ASCII only, so anything else becomes '?', and at most 16 characters are kept (the
 * worker transliterates accents before sending). */
static void copy_name(char *out, size_t cap, const uint8_t *text, size_t length) {
    size_t n = length < 16 ? length : 16;
    if (n > cap - 1) n = cap - 1;
    for (size_t i = 0; i < n; ++i) out[i] = text[i] >= 32 && text[i] < 127 ? (char)text[i] : '?';
    out[n] = 0;
}

/* ---- opening ---- */

static bool apply_options(const RrhkMachine *m, const uint8_t *text, size_t length) {
    size_t start = 0;
    while (start < length) {
        size_t end = start;
        while (end < length && text[end] != '\n') ++end;
        char line[256];
        const size_t n = end - start;
        if (n) {
            if (n >= sizeof line) { refuse(RRHK_REFUSED_OPTION, "(too long)"); return false; }
            memcpy(line, text + start, n); line[n] = 0;
            char *equal = strchr(line, '=');
            if (!equal) { refuse(RRHK_REFUSED_OPTION, line); return false; }
            *equal = 0;
            if (!m->session_option || !m->session_option(line, equal + 1)) { refuse(RRHK_REFUSED_OPTION, line); return false; }
        }
        start = end + 1;
    }
    return true;
}

bool rrhk_session_open(RrhkRun *run) {
    if (rrhk_session_on) {
        /* A driven machine restarted for everyone (RRHK_RUN_RESET): the session goes on from the next frame, with the host's
         * options and a guest's side effects set again on the new run. */
        const RrhkMachine *m = run->machine;
        if (s.setup && !apply_options(m, s.options, s.options_length)) return false;
        if (s.guest && m->side_effects) m->side_effects(false);
        if (s.setup && s.save_in && m->session_save_put) m->session_save_put(s.save_in, s.save_total);
        if (s.setup && m->session_begin) m->session_begin(RRHK_SESSION_CLOCK);
        return true;
    }
    const char *value = getenv(RRHK_SESSION_ENV);
    if (!value || !*value) return true;                 /* alone: nothing changes */
    if (run->test_frames) return true;                  /* a hidden-window test run (the conversion's checks) is never a session */
    const RrhkMachine *m = run->machine;
    char in_text[32] = {0};
    const char *comma = strchr(value, ',');
    if (!comma || (size_t)(comma - value) >= sizeof in_text || !pipe_from(comma + 1, &s.out)) {
        fprintf(stderr, "[session] %s is not two pipe handles\n", RRHK_SESSION_ENV);
        return false;
    }
    memcpy(in_text, value, (size_t)(comma - value));
    if (!pipe_from(in_text, &s.in)) { fprintf(stderr, "[session] the input pipe is not valid\n"); return false; }
#ifndef _WIN32
    fcntl(s.in, F_SETFL, fcntl(s.in, F_GETFL) | O_NONBLOCK);
#endif
    s.broken = false; s.rx_len = 0;
    /* HELLO: what this game can do in a session; the worker decides the tier (delay, rollback) or refuses the machine. */
    uint8_t hello[16 + 64 + 2 + RRHK_SESSION_MAX_OPTIONS + 4];
    const size_t bound = m->snap_bound && m->snap_save && m->snap_load ? m->snap_bound() : 0;
    const uint8_t caps = (uint8_t)((bound ? RRHK_CAP_SNAPSHOT : 0) | (m->digest ? RRHK_CAP_DIGEST : 0) |
                                   (m->pointer ? RRHK_CAP_POINTER : 0) | (m->analog_sticks ? RRHK_CAP_AXES : 0) |
                                   (m->driven ? RRHK_CAP_DRIVEN : 0));
    char name[64];
    size_t name_length = 0;
    /* The machine's name as players read it (a CPS-2 board says CPS-2; ini_section stays the preferences' key). */
    if (m->console_name) {
        for (const char *c = m->console_name; *c && name_length < sizeof name - 1; ++c)
            name[name_length++] = (unsigned char)*c >= 32 && (unsigned char)*c < 127 ? *c : '?';
    } else {
        for (const wchar_t *w = m->ini_section; w && *w && name_length < sizeof name - 1; ++w)
            name[name_length++] = *w >= 32 && *w < 127 ? (char)*w : '?';
    }
    put16(hello, RRHK_SESSION_ABI);
    hello[2] = (uint8_t)m->players();
    hello[3] = caps;
    put32(hello + 4, (uint32_t)(bound > 0xffffffffu ? 0 : bound));
    put32(hello + 8, m->frame_seconds > 0.0 ? (uint32_t)(1000.0 / m->frame_seconds + 0.5) : 0);
    hello[12] = (uint8_t)name_length;
    memcpy(hello + 13, name, name_length);
    /* This PC's run-changing options: the host's are what every seat plays with (they come back in SETUP). */
    size_t options = m->session_options ? m->session_options((char *)hello + 15 + name_length, RRHK_SESSION_MAX_OPTIONS) : 0;
    if (options > RRHK_SESSION_MAX_OPTIONS) options = 0;
    for (size_t i = 0; i < options; ++i) {
        const uint8_t c = hello[15 + name_length + i];
        if (c != '\n' && (c < 32 || c > 126)) { options = 0; break; }      /* never a byte the worker would refuse */
    }
    put16(hello + 13 + name_length, (uint16_t)options);
    /* This game's save image (session ABI 8): its size in HELLO, then the bytes in SAVE_OUT (the host's travel to every seat). */
    size_t save_size = m->session_save ? m->session_save(NULL, 0) : 0;
    uint8_t *save = save_size && save_size <= RRHK_SESSION_MAX_SAVE ? (uint8_t *)malloc(save_size) : NULL;
    if (!save || m->session_save(save, save_size) != save_size) { free(save); save = NULL; save_size = 0; }
    put32(hello + 15 + name_length + options, (uint32_t)save_size);
    if (!send_message(RRHK_MSG_HELLO, hello, 19 + name_length + options)) { free(save); fprintf(stderr, "[session] the pipe is closed\n"); return false; }
    for (size_t at = 0; at < save_size; at += RRHK_SESSION_SAVE_CHUNK) {
        uint8_t chunk[4 + RRHK_SESSION_SAVE_CHUNK];
        const size_t n = save_size - at < RRHK_SESSION_SAVE_CHUNK ? save_size - at : RRHK_SESSION_SAVE_CHUNK;
        put32(chunk, (uint32_t)at);
        memcpy(chunk + 4, save + at, n);
        if (!send_message(RRHK_MSG_SAVE_OUT, chunk, 4 + n)) { free(save); return false; }
    }
    free(save);
    /* A gun or pointer (the local mouse) lives outside the pad words: such a game is not offered until LOCAL carries it. The
     * sticks travel since session ABI 7. A computer's keyboard bindings (keyboard_pad) feed the pad words like any other: in a
     * session the computer adapter gives its guest no key of this PC (rrhk_computer.inc), so only the joysticks reach the
     * machine (RRHK_CAP_KEYBOARD stays for a game that will read the guest keyboard once LOCAL carries it). */
    if (m->pointer) {
        refuse(RRHK_REFUSED_COMMAND, "pointer");
        fprintf(stderr, "[session] this game's controls cannot be shared yet\n");
        return false;
    }
    memset(s.ports, 0, sizeof s.ports);
    memset(s.axes, 0, sizeof s.axes);
    memset(s.slot_used, 0, sizeof s.slot_used);
    s.live = s.last_run = 0; s.local_sent = false; s.paused = false; s.restart_pending = false; s.ppm = 0; s.ending_until = 0; s.system_sent = 0; s.exit_reason = 0;
    s.state_pending = 0; s.state_used = false; s.state_len = 0;
    s.setup = false; s.setup_until = SDL_GetTicks64() + 15000;
    rrhk_session_on = true;           /* from here the frames wait for SETUP inside the loop (events and pictures go on) */
    /* The worker started this game from a window in the background: without the focus, the keyboard reaches nothing and the
     * pads are ignored (or read twice through two of Windows' paths, seen on a ThinkPad on 17 Nov 2026). The game asks for it
     * once, as a game opened by the player has it. */
    if (run->win) {
        SDL_SetHint(SDL_HINT_FORCE_RAISEWINDOW, "1");
        SDL_RaiseWindow(run->win);
    }
    return true;
}

/* SETUP: the seat, the ports, the snapshot ring and the host's run-changing options, applied before frame 0. */
static bool setup(const RrhkMachine *m, const uint8_t *payload, uint16_t length) {
    if (length < 6) { refuse(RRHK_REFUSED_COMMAND, "setup"); return false; }
    const unsigned seat = payload[0], ports = payload[1], depth = payload[2];
    const uint16_t options = (uint16_t)(payload[4] | payload[5] << 8);
    if (seat >= RRHK_MAX_PLAYERS || ports > RRHK_MAX_PLAYERS || depth > RRHK_SESSION_MAX_RING || 6u + options != length) {
        refuse(RRHK_REFUSED_COMMAND, "setup");
        return false;
    }
    s.guest = (payload[3] & RRHK_SETUP_GUEST) != 0;
    s.setup_ports = (int)ports;
    if (!apply_options(m, payload + 6, options)) return false;
    memcpy(s.options, payload + 6, options); s.options_length = options;
    const size_t bound = m->snap_bound && m->snap_save && m->snap_load ? m->snap_bound() : 0;
    if (depth && bound) {
        s.ring = (uint8_t *)malloc(bound * depth);
        if (!s.ring) { refuse(RRHK_REFUSED_SNAPSHOT, "memory"); return false; }
        s.slot_size = bound; s.depth = depth;
    } else if (depth) { refuse(RRHK_REFUSED_SNAPSHOT, "none"); return false; }
    /* The match's state (the host's F8 / F9 for everyone), on any tier, for a machine whose snapshot is a whole state. */
    if (bound && !s.state) {
        s.state = (uint8_t *)malloc(bound);
        if (!s.state) { refuse(RRHK_REFUSED_SNAPSHOT, "memory"); return false; }
        s.state_size = bound;
    }
    if (s.guest && m->side_effects) m->side_effects(false);
    /* The host's save, in memory for this match (it came before SETUP, whole). */
    if (s.save_got != s.save_total) { refuse(RRHK_REFUSED_COMMAND, "save"); return false; }
    if (s.save_in && (!m->session_save_put || !m->session_save_put(s.save_in, s.save_total))) {
        refuse(RRHK_REFUSED_COMMAND, "save");
        return false;
    }
    if (m->session_begin) m->session_begin(RRHK_SESSION_CLOCK);
    s.setup = true;
    fprintf(stderr, "[session] started: seat %u, %u ports, ring %u, %s; physical latency unmeasured\n",
            seat + 1, ports, depth, s.guest ? "guest" : "host");
    return true;
}

/* ---- one iteration ---- */

static void effects(const RrhkMachine *m, bool allowed) {
    if (m->side_effects) m->side_effects(allowed && !s.guest);
}

/* A word from the network is cleaned as the local path cleans its own (rrhk_local_pad_word): only the machine's action bits
 * are kept, and opposite directions held together cancel. A peer can then never hand the machine a word no pad could make
 * (security review K1). */
static uint16_t clean_word(const RrhkMachine *m, uint16_t word) {
    uint16_t valid = 0;
    for (int a = 0; a < m->action_count; ++a) valid |= m->actions[a].bit;
    word &= valid;
    const uint16_t left = m->actions[m->left].bit, right = m->actions[m->right].bit;
    const uint16_t up = m->actions[m->up].bit, down = m->actions[m->down].bit;
    if ((word & (left | right)) == (left | right)) word &= (uint16_t)~(left | right);
    if ((word & (up | down)) == (up | down)) word &= (uint16_t)~(up | down);
    return word;
}

static bool set_ports(const RrhkMachine *m, const uint8_t *payload, uint16_t length) {
    const unsigned count = payload[5];
    const bool sticks = (payload[4] & RRHK_RUN_AXES) != 0;
    if (count > RRHK_MAX_PLAYERS || length != 6u + 2u * count + (sticks ? RRHK_AXES * count : 0u)) return false;
    memset(s.ports, 0, sizeof s.ports);
    memset(s.axes, 0, sizeof s.axes);
    for (unsigned p = 0; p < count; ++p)
        s.ports[p] = clean_word(m, (uint16_t)(payload[6 + 2 * p] | payload[7 + 2 * p] << 8));
    if (sticks && m->analog_sticks)      /* a machine without sticks ignores them (its words are all it reads) */
        for (unsigned p = 0; p < count; ++p)
            for (int a = 0; a < RRHK_AXES; ++a) {
                const int8_t value = (int8_t)payload[6 + 2 * count + RRHK_AXES * p + a];
                s.axes[p][a] = value < -127 ? -127 : value;     /* symmetric, as the kit's own sticks */
            }
    return true;
}

/* A port's sticks as the machine reads them (-32766..32766: 258 per step of the int8 the session carries). */
void rrhk_session_axes(int port, int16_t axes[RRHK_AXES]) {
    for (int a = 0; a < RRHK_AXES; ++a)
        axes[a] = port >= 0 && port < RRHK_MAX_PLAYERS ? (int16_t)(s.axes[port][a] * 258) : 0;
}

/* This PC's sticks for LOCAL: the gamepad's (after its dead zone), with the machine's stick-from-key actions folded in, as
 * int8 (the original pads' precision: a DualShock and an N64 stick are 8-bit). */
static void local_axes(const RrhkMachine *m, uint64_t input_frame, int8_t out[RRHK_AXES]) {
    int16_t axes[RRHK_AXES];
    rrhk_local_pad_axes(0, input_frame, axes);
    if (m->stick_actions) {
        static const int axis[4] = {RRHK_AXIS_LX, RRHK_AXIS_LX, RRHK_AXIS_LY, RRHK_AXIS_LY};
        static const int16_t edge[4] = {-32767, 32767, -32767, 32767};
        for (int i = 0; i < 4; ++i)
            if (m->stick_actions[i] >= 0 && m->stick_actions[i] < m->action_count && rrhk_action_held(0, m->stick_actions[i]))
                axes[axis[i]] = edge[i];
    }
    for (int a = 0; a < RRHK_AXES; ++a) {
        const int value = axes[a] >= 0 ? (axes[a] + 129) / 258 : -((-axes[a] + 129) / 258);
        out[a] = (int8_t)(value > 127 ? 127 : value < -127 ? -127 : value);
    }
}

/* The session is over (lost, refused, stopped): the reason stays on screen about 3.5 s (events polled, pictures presented, no
 * frame run), then the game closes. Never a window that simply vanishes. */
#define RRHK_SESSION_ENDING_MS 3500
/* The in-game chat (rrhk_chat.inc, included at the end of this file). */
static bool chat_show(const uint8_t *payload, uint16_t length);
static void chat_turn(int turn, const char *name);
static void chat_slow(void);
static void chat_reset(void);

/* RUN_STATE_SAVE / RUN_STATE_LOAD, before the frame runs (live, or again in a silent frame after a correction). */
static bool match_state(const RrhkMachine *m, uint8_t flags, bool live) {
    if (flags & RRHK_RUN_STATE_SAVE) {
        const size_t n = s.state ? m->snap_save(s.state, s.state_size) : 0;
        if (!n) return false;
        s.state_len = n; s.state_used = true;
        if (live) rrhk_notice(rr_tr("State saved by the host"), 1800);
    } else if (flags & RRHK_RUN_STATE_LOAD) {
        if (!s.state || !s.state_used || !m->snap_load(s.state, s.state_len)) return false;
        if (live) rrhk_notice(rr_tr("State loaded by the host"), 1800);
    }
    return true;
}

static int ending(const char *message, uint16_t reason) {
    if (!s.ending_until) {
        s.exit_reason = reason;
        rrhk_notice(message, RRHK_SESSION_ENDING_MS + 500);
        s.ending_until = SDL_GetTicks64() + RRHK_SESSION_ENDING_MS;    /* nothing more is read; EXIT is sent at close */
    }
    return 0;
}
static int lost(RrhkRun *run, const char *why) {
    (void)run;
    fprintf(stderr, "[session] %s\n", why);
    return ending(rr_tr("Connection to Retro-Recomp lost"), RRHK_EXIT_LOST);
}

int rrhk_session_frame(RrhkRun *run, uint64_t input_frame) {
    const RrhkMachine *m = run->machine;
    uint8_t payload[RRHK_SESSION_MAX_PAYLOAD];
    if (s.ending_until) return SDL_GetTicks64() >= s.ending_until ? -1 : 0;
    if (!s.setup) {
        /* No frame before SETUP; the loop keeps polling events and presenting meanwhile. */
        pump();
        if (s.broken) return lost(run, "the pipe is closed");
        uint16_t length = 0;
        const uint16_t type = take(payload, &length);
        if (s.broken) return lost(run, "a message broke the rules");
        if (type == RRHK_MSG_SETUP) {
            if (setup(m, payload, length)) return 0;
            fprintf(stderr, "[session] the setup was refused\n");
            return ending(rr_tr("Connection to Retro-Recomp lost"), RRHK_EXIT_FAILED);
        }
        if (type == RRHK_MSG_SAVE_IN) {
            /* The host's save image, in order, before SETUP (a guest). */
            if (length < 8) return lost(run, "a SAVE_IN broke the rules");
            const uint32_t total = u32(payload), offset = u32(payload + 4), n = length - 8u;
            if (total > RRHK_SESSION_MAX_SAVE || n > RRHK_SESSION_SAVE_CHUNK || offset != s.save_got || offset + n > total ||
                (s.save_in && total != s.save_total) || (!total && n))
                return lost(run, "a SAVE_IN broke the rules");
            if (!s.save_in && total) {
                s.save_in = (uint8_t *)malloc(total);
                if (!s.save_in) return lost(run, "no memory for the host's save");
                s.save_total = total;
            }
            if (n) memcpy(s.save_in + offset, payload + 8, n);
            s.save_got += n;
            return 0;
        }
        if (type) return lost(run, "a message before the setup");
        if (SDL_GetTicks64() >= s.setup_until) return lost(run, "no setup from Retro-Recomp");
        wait_input(4);
        return 0;
    }
    /* The system bits are read every iteration: a menu opened asks everyone to pause, and closing it (while the session is
     * paused, so no RUN comes) is reported again for the same frame, with the same word; the worker takes the latest. */
    const uint16_t system = (uint16_t)((rrhk.menu || rrhk.paused ? RRHK_SYS_PAUSE : 0) |
                                       (s.restart_pending ? RRHK_SYS_RESTART : 0) |
                                       (s.state_pending == 1 ? RRHK_SYS_STATE_SAVE : s.state_pending == 2 ? RRHK_SYS_STATE_LOAD : 0));
    if (!s.local_sent || system != s.system_sent) {
        /* A menu's keys and buttons never reach the game: while one is open (or a binding is being captured), this PC
         * sends the neutral word. */
        if (!s.local_sent) {
            const bool neutral = rrhk.menu || rrhk.capturing || rrhk_chat_holds_word();
            s.word_sent = neutral ? 0 : rrhk_local_pad_word(0, input_frame);
            memset(s.axes_sent, 0, sizeof s.axes_sent);
            if (m->analog_sticks && !neutral) local_axes(m, input_frame, s.axes_sent);
        }
        uint8_t local[8 + RRHK_AXES];
        put32(local, s.live);
        put16(local + 4, s.word_sent);
        put16(local + 6, system);
        memcpy(local + 8, s.axes_sent, RRHK_AXES);
        if (!send_message(RRHK_MSG_LOCAL, local, m->analog_sticks ? sizeof local : 8u)) return lost(run, "the pipe is closed");
        s.local_sent = true; s.system_sent = system;
    }
    /* Wait for the live frame at most three quarters of a frame, then show the last picture and come back. */
    const unsigned budget = m->frame_seconds > 0.0 ? (unsigned)(m->frame_seconds * 750.0) : 12;
    const Uint64 until = SDL_GetTicks64() + budget;
    for (;;) {
        pump();
        if (s.broken) return lost(run, "the pipe is closed");
        uint16_t length = 0;
        const uint16_t type = take(payload, &length);
        if (s.broken) return lost(run, "a message broke the rules");
        if (!type) {
            if (s.paused) {
                char text[96];
                snprintf(text, sizeof text, rr_tr("Paused by %s"), s.paused_by);
                rrhk_notice(text, 500);
                return 0;
            }
            const Uint64 now = SDL_GetTicks64();
            if (now >= until) return 0;
            wait_input((unsigned)(until - now));
            continue;
        }
        switch (type) {
        case RRHK_MSG_RUN: {
            if (length < 6 || !set_ports(m, payload, length)) return lost(run, "a RUN broke the rules");
            const uint32_t frame = u32(payload);
            if (payload[4] & ~(RRHK_RUN_SILENT | RRHK_RUN_RESET | RRHK_RUN_STATE_SAVE | RRHK_RUN_STATE_LOAD | RRHK_RUN_AXES))
                return lost(run, "a RUN with unknown flags");
            if (payload[4] & RRHK_RUN_SILENT) {
                /* Re-simulation after a LOAD: frames in order, up to the one before the live frame. */
                if (!s.ring) { refuse(RRHK_REFUSED_COMMAND, "silent"); return lost(run, "a silent frame without snapshots"); }
                if (frame != s.live) return lost(run, "a silent RUN out of order");
                s.silent = true; effects(m, false);
                if (payload[4] & RRHK_RUN_RESET) {                 /* the host's restart, run again after a correction */
                    m->reset();
                    if (m->driven) s.restarting = true;    /* its shell closes after this frame and opens again: not the end */
                }
                if (!match_state(m, payload[4], false)) {           /* the host's F8 / F9, run again after a correction */
                    s.silent = false; effects(m, true);
                    refuse(RRHK_REFUSED_SNAPSHOT, "state");
                    return lost(run, "the match's state could not be saved or loaded");
                }
                if (m->driven) {
                    /* A driven machine: its guest runs the frame when rrhk_frame_done returns, and calls it again at the
                     * frame's end, where rrhk_session_silent_done ends it (no picture, no pacing, its sound dropped:
                     * own_audio machines push nothing while rrhk_session_silent() is true). */
                    s.driven_silent = true;
                    s.last_run = frame;
                    s.live = frame + 1;
                    return 2;
                }
                const bool ok = m->run_frame(s.ports[0], s.ports[1]);
                rrhk_audio_discard(run);
                s.silent = false; effects(m, true);
                if (!ok) return lost(run, "the machine stopped");
                s.last_run = frame;
                s.live = frame + 1;
                break;
            }
            if (frame != s.live) return lost(run, "a RUN for another frame");
            if (payload[4] & RRHK_RUN_RESET) {
                /* The host's restart, at the same frame on every seat: the machine restarts, then this frame runs (a driven
                 * machine unwinds after it, as Shift+F1 does alone). */
                m->reset(); rrhk_audio_pause_output(run);
                rrhk_notice(rr_tr("Restarted by the host"), 1800);
                if (m->driven) s.restarting = true;    /* its shell closes after this frame and opens again: not the end */
            }
            if (!match_state(m, payload[4], true)) {
                refuse(RRHK_REFUSED_SNAPSHOT, "state");
                return lost(run, "the match's state could not be saved or loaded");
            }
            if (payload[4] & RRHK_RUN_STATE_LOAD) rrhk_audio_pause_output(run);
            s.last_run = frame;
            return 1;
        }
        case RRHK_MSG_SAVE: case RRHK_MSG_LOAD: {
            if (length != 4 || !s.ring) { refuse(RRHK_REFUSED_SNAPSHOT, "ring"); return lost(run, "a snapshot without a ring"); }
            const uint32_t frame = u32(payload);
            const unsigned slot = frame % s.depth;
            uint8_t *data = s.ring + (size_t)slot * s.slot_size;
            if (type == RRHK_MSG_SAVE) {
                const size_t n = m->snap_save(data, s.slot_size);
                if (!n) { refuse(RRHK_REFUSED_SNAPSHOT, "save"); return lost(run, "a snapshot could not be taken"); }
                s.slot_frame[slot] = frame; s.slot_len[slot] = n; s.slot_used[slot] = true;
            } else {
                if (!s.slot_used[slot] || s.slot_frame[slot] != frame || !m->snap_load(data, s.slot_len[slot])) {
                    refuse(RRHK_REFUSED_SNAPSHOT, "load");
                    return lost(run, "a snapshot could not be loaded");
                }
                /* The frames after it are run again (silent, then live) before the next live frame. */
                s.live = frame;
            }
            break;
        }
        case RRHK_MSG_DIGEST: {
            uint8_t out[12];
            const uint64_t digest = m->digest ? m->digest() : 0;
            put32(out, s.last_run);
            put32(out + 4, (uint32_t)digest); put32(out + 8, (uint32_t)(digest >> 32));
            send_message(RRHK_MSG_DIGEST_OF, out, sizeof out);
            break;
        }
        case RRHK_MSG_PAUSE:
            if (length < 2 || length != 2u + payload[1]) return lost(run, "a PAUSE broke the rules");
            s.paused = payload[0] != 0;
            copy_name(s.paused_by, sizeof s.paused_by, payload + 2, payload[1]);
            if (!s.paused) rrhk_notice(rr_tr("Resumed"), 1200);
            break;
        case RRHK_MSG_NOTICE: {
            if (length < 3 || length != 3u + payload[2]) return lost(run, "a NOTICE broke the rules");
            char name[24], text[128];
            copy_name(name, sizeof name, payload + 3, payload[2]);
            const uint16_t code = (uint16_t)(payload[0] | payload[1] << 8);
            /* The code chooses a catalogue string; only the name comes from the pipe. */
            if (code == RRHK_NOTICE_TURN || code == RRHK_NOTICE_YOUR_TURN) { chat_turn(code == RRHK_NOTICE_YOUR_TURN ? 2 : 1, name); break; }
            if (code == RRHK_NOTICE_CHAT_SLOW) { chat_slow(); break; }
            if (code == RRHK_NOTICE_WAITING) snprintf(text, sizeof text, rr_tr("Waiting for %s"), name);
            else if (code == RRHK_NOTICE_LEFT) snprintf(text, sizeof text, rr_tr("%s left the game"), name);
            else snprintf(text, sizeof text, "%s", rr_tr("Resumed"));
            rrhk_notice(text, 1800);
            break;
        }
        case RRHK_MSG_CHAT_SHOW:
            if (!chat_show(payload, length)) return lost(run, "a CHAT_SHOW broke the rules");
            break;
        case RRHK_MSG_PACE: {
            if (length != 4) return lost(run, "a PACE broke the rules");
            const int32_t ppm = (int32_t)u32(payload);
            s.ppm = ppm > 20000 ? 20000 : ppm < -20000 ? -20000 : ppm;
            break;
        }
        case RRHK_MSG_STOP: {
            const uint16_t reason = length >= 2 ? (uint16_t)(payload[0] | payload[1] << 8) : 0;
            fprintf(stderr, "[session] stopped by Retro-Recomp (%u)\n", (unsigned)reason);
            return ending(reason == RRHK_STOP_DESYNC ? rr_tr("The games went out of step: the match stops") :
                          reason == RRHK_STOP_BOOT_MISMATCH ? rr_tr("Your game differs from the host's") :
                          rr_tr("The match is over"), RRHK_EXIT_STOPPED);
        }
        default:
            refuse(RRHK_REFUSED_COMMAND, "unknown");
            return lost(run, "an unknown message");
        }
    }
}

/* The end of a driven machine's silent frame (its guest called rrhk_frame_done): true when one had run, and the kit then
 * neither presents nor paces it. */
bool rrhk_session_silent_done(RrhkRun *run) {
    if (!s.driven_silent) return false;
    s.driven_silent = false;
    s.silent = false;
    effects(run->machine, true);
    rrhk_audio_discard(run);
    return true;
}

void rrhk_session_frame_done(RrhkRun *run, Uint64 cost_ticks) {
    uint8_t done[8];
    put32(done, s.live);
    put32(done + 4, (uint32_t)(run->frequency ? cost_ticks * 1000000u / run->frequency : 0));
    send_message(RRHK_MSG_DONE, done, sizeof done);
    ++s.live;
    if (s.system_sent & RRHK_SYS_RESTART) s.restart_pending = false;     /* the worker saw it in this frame's LOCAL */
    if (s.system_sent & (RRHK_SYS_STATE_SAVE | RRHK_SYS_STATE_LOAD)) s.state_pending = 0;
    s.local_sent = false;
}

void rrhk_session_close(RrhkRun *run, int reason) {
    (void)run;
    if (!rrhk_session_on) return;
    if (s.restarting && !s.ending_until) { s.restarting = false; return; }      /* the shell opens again at once */
    uint8_t out[2];
    /* The reason the session recorded when it ended (stopped, lost, refused) wins over the window's own (closed, failed). */
    put16(out, s.exit_reason ? s.exit_reason : (uint16_t)reason);
    send_message(RRHK_MSG_EXIT, out, sizeof out);
#ifdef _WIN32
    CloseHandle(s.in); CloseHandle(s.out);
#else
    close(s.in); close(s.out);
#endif
    s.in = s.out = RRHK_NO_PIPE;
    free(s.ring); s.ring = NULL; s.depth = 0;
    free(s.state); s.state = NULL; s.state_size = s.state_len = 0; s.state_used = false;     /* the match's state ends here */
    free(s.save_in); s.save_in = NULL; s.save_total = s.save_got = 0;                          /* and the host's save */
    chat_reset();
    rrhk_session_on = false;
}

#include "rrhk_chat.inc"
