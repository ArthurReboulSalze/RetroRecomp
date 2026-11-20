/* The Game Gear link (the Gear-to-Gear cable): two Game Gears in one process, for the Game Gear only (stamp group 'gg').
 * Included in the glue after gamestate.inc, before the banked loop, which calls rrl_start, rrl_irq, rrl_nmi and rrl_after_step.
 *
 * Every PC runs BOTH consoles; only the pads travel in a match (Option A of .build/gg-link-cable-study.md). The consoles share
 * the one set of globals of the runtime: the console that is running owns them, the other one is kept as a whole snapshot (the
 * rollback snapshot of gamestate.inc: CPU, banks, RAM, VDP, raster, PSG, counters of the timeline) and the two are swapped at
 * every slice, 24 video lines (5,472 Z80 cycles, less than the 7,087 cycles one byte takes to arrive at 4800 baud, 9.5 bit
 * times, so a byte sent in a slice is never due before the next slice of the other console). Console 0 runs its slice, then
 * console 1; a frame is delivered to the host kit after BOTH have finished it, at a round end, whichever console this PC shows,
 * so that every PC takes its digest and its snapshots at the same place of the two timelines.
 *
 * Nothing here changes a game that does not run linked: rrl_on is false and every hook is a test of it.
 * What is not modelled is listed in docs/GAME_GEAR.md (power-on phase of the two consoles fixed at zero, parallel lines seen
 * by the other console at the next slice). */
#include "gg_ext.h"

typedef struct { void (*present)(const uint32_t *fb, int w, int h); bool (*frame_done)(void); } RrlHost;

static bool rrl_request;                 /* asked for: the environment, or the multiplayer session */
static int rrl_seat;                     /* the console this PC shows (0 or 1) */
static RrlHost rrl_host;
static int rrl_cur;                      /* the console whose state is in the globals */
static int rrl_chunk;                    /* the slice (line / 24) the console now running is in */
static GgExt rrl_ext[2];
static GgCable rrl_cable;
static uint8_t *rrl_snap[2];
static size_t rrl_snap_size;
static uint8_t rrl_pad[2];
static uint64_t rrl_script_frame[2][16];
static uint8_t rrl_script_mask[2][16];
static int rrl_script_count[2];
static uint64_t rrl_delivered, rrl_limit, rrl_rounds, rrl_swaps;
static void (*rrl_real_sink)(const int16_t *, size_t);
static void rrl_selftest(void);

#define RRL_SLICE_LINES 24               /* 5,472 Z80 cycles: below the 7,087 a byte takes to arrive at 4800 baud (9.5 bit times) */
#define RRL_MAGIC 0x314B4E4Cu            /* "LNK1" */

static bool rrl_pending;                 /* asked for after the run began (a session opens one frame in): begin at the next instruction boundary */
static uint8_t *rrl_poweron;             /* the power-on state of the console, taken when the run begins */
void smsrecomp_link_request(bool on) { rrl_request = on; if (on && !rrl_on && rrl_poweron) rrl_pending = true; }
void smsrecomp_link_set_seat(int seat) { rrl_seat = seat ? 1 : 0; }
void smsrecomp_link_set_host(void (*present)(const uint32_t *, int, int), bool (*frame_done)(void)) {
    rrl_host.present = present; rrl_host.frame_done = frame_done;
}
int smsrecomp_link_seat(void) { return rrl_seat; }
bool smsrecomp_link_active(void) { return rrl_on; }

/* Linked play needs the banked engine (the only one with a snapshot), a Game Gear, and no reference run. */
static bool rrl_capable(void) {
#ifdef SMSRECOMP_BANKED_AOT
    return g_is_gg && !getenv("SMSRECOMP_REFERENCE");
#else
    return false;
#endif
}
bool smsrecomp_link_enabled(void) {
    static int probed;
    if (!probed) {
        probed = 1;
        const char *logfile = getenv("RETRO_RECOMP_GG_LINK_LOGFILE");     /* a developer's log of a run whose stderr nobody keeps */
        if (logfile && logfile[0]) freopen(logfile, "a", stderr);
        const char *value = getenv("RETRO_RECOMP_GG_LINK");
        if (value && value[0] >= '1' && value[0] <= '2') { rrl_request = true; rrl_seat = value[0] - '1'; }
    }
#ifdef SMSRECOMP_BANKED_AOT
    return rrl_request && g_is_gg && !getenv("SMSRECOMP_REFERENCE");
#else
    return false;
#endif
}

/* ---- the scripted pads of a headless run: RETRO_RECOMP_GG_LINK_PRESS0 / 1 = "frame:keys;frame:keys" (U D L R A B S) ---- */
static uint8_t rrl_keys(const char *s) {
    uint8_t mask = 0;
    for (; *s && *s != ';'; ++s) switch (*s) {
        case 'U': mask |= SMS_PAD_UP; break;    case 'D': mask |= SMS_PAD_DOWN; break;
        case 'L': mask |= SMS_PAD_LEFT; break;  case 'R': mask |= SMS_PAD_RIGHT; break;
        case 'A': mask |= SMS_PAD_B1; break;    case 'B': mask |= SMS_PAD_B2; break;
        case 'S': mask |= SMS_PAD_START; break; default: break;
    }
    return mask;
}
static void rrl_parse_script(int console) {
    char name[40];
    snprintf(name, sizeof name, "RETRO_RECOMP_GG_LINK_PRESS%d", console);
    const char *text = getenv(name);
    rrl_script_count[console] = 0;
    while (text && *text && rrl_script_count[console] < 16) {
        char *end;
        const uint64_t frame = strtoull(text, &end, 0);
        const char *colon = *end == ':' ? end + 1 : end;
        const int n = rrl_script_count[console]++;
        rrl_script_frame[console][n] = frame; rrl_script_mask[console][n] = rrl_keys(colon);
        const char *next = strchr(colon, ';');
        text = next ? next + 1 : NULL;
    }
}
static uint8_t rrl_scripted(int console, uint64_t frame, uint8_t current) {
    bool found = false; uint64_t best = 0; uint8_t mask = current;
    for (int i = 0; i < rrl_script_count[console]; ++i)
        if (rrl_script_frame[console][i] <= frame && (!found || rrl_script_frame[console][i] >= best)) {
            found = true; best = rrl_script_frame[console][i]; mask = rrl_script_mask[console][i];
        }
    return found ? mask : current;
}

/* The pads the host kit delivers for the frame (the adapter's pads[0], pads[1]): one per console. */
void smsrecomp_link_set_pads(uint8_t first, uint8_t second) {
    rrl_pad[0] = first; rrl_pad[1] = second;
    if (rrl_on) { g_pad1 = rrl_pad[rrl_cur]; g_pad2 = 0; }
}

/* ---- the two consoles, one snapshot each ---- */
static bool rrl_save_live(void) {
    return smsrecomp_snap_save(rrl_snap[rrl_cur], rrl_snap_size) == rrl_snap_size;
}
static bool rrl_load(int console) {
    if (!smsrecomp_snap_load(rrl_snap[console], rrl_snap_size)) return false;
    rrl_cur = console; rrl_chunk = g_vdp.line / RRL_SLICE_LINES;
    rrl_pad[console] = rrl_scripted(console, g_frame, rrl_pad[console]);
    g_pad1 = rrl_pad[console]; g_pad2 = 0;
    return true;
}
static void rrl_fail(const char *what) {
    fprintf(stderr, "[link] fatal: %s (console %d, frame %llu)\n", what, rrl_cur, (unsigned long long)g_frame);
    exit(4);
}

/* The sound of the console that is not shown is advanced, never played: the PSG must run the same on every PC. */
static void rrl_sink(const int16_t *frames, size_t count) {
    if (rrl_cur == rrl_seat && rrl_real_sink) rrl_real_sink(frames, count);
}
static int rrl_frame_cb(const uint32_t *fb, int width, int height) {
    if (rrl_cur == rrl_seat && rrl_host.present) rrl_host.present(fb, width, height);
    return 0;
}

static void rrl_report(void) {
    if (!rrl_on) return;
    const char *prefix = getenv("RETRO_RECOMP_GG_LINK_DUMP");
    if (!rrl_save_live()) return;
    const int live = rrl_cur;
    for (int c = 0; c < 2; ++c) {
        if (!rrl_load(c)) break;
        fprintf(stderr, "[link] console %d: frame=%llu cycles=%llu ram=%016llx vdp=%016llx pc=%04X sp=%04X %s\n", c + 1,
            (unsigned long long)g_frame, (unsigned long long)g_z80.cyc, (unsigned long long)fnv1a64(g_ram, sizeof g_ram),
            (unsigned long long)fnv1a64(&g_vdp, sizeof g_vdp), g_z80.pc, g_z80.sp, gg_ext_summary(&rrl_ext[c]));
        if (prefix && prefix[0]) {
            char path[512];
            snprintf(path, sizeof path, "%s.%d.ram", prefix, c + 1);
            FILE *f = fopen(path, "wb");
            if (f) { fwrite(g_ram, 1, sizeof g_ram, f); fclose(f); }
        }
    }
    fprintf(stderr, "[link] rounds=%llu swaps=%llu cable bytes %u/%u\n", (unsigned long long)rrl_rounds,
        (unsigned long long)rrl_swaps, gg_cable_sent(&rrl_cable, 0), gg_cable_sent(&rrl_cable, 1));
    rrl_load(live);
}

/* Start of a run (and of every reset): both consoles from the same power-on state, the cable empty. */
static void rrl_begin(void) {
    if (!smsrecomp_link_enabled()) { if (rrl_request) fprintf(stderr, "[link] asked for but not available (not a Game Gear banked build)\n"); return; }
    rrl_snap_size = smsrecomp_snap_bound();
    if (!rrl_snap_size) return;
    for (int c = 0; c < 2; ++c) {
        if (!rrl_snap[c]) rrl_snap[c] = (uint8_t *)malloc(rrl_snap_size);
        if (!rrl_snap[c]) rrl_fail("no memory for the second console");
    }
    gg_cable_reset(&rrl_cable);
    gg_ext_reset(&rrl_ext[0]); gg_ext_reset(&rrl_ext[1]);
    rrl_cur = 0; rrl_delivered = 0; rrl_rounds = rrl_swaps = 0;
    if (g_frame_limit) rrl_limit = g_frame_limit;
    g_frame_limit = 0;                  /* the limit is applied at a round end, to both consoles */
    rrl_parse_script(0); rrl_parse_script(1);
    g_input_cb = NULL;
    if (g_audio_sink != rrl_sink) rrl_real_sink = g_audio_sink;
    g_audio_sink = rrl_sink;
    g_frame_cb = rrl_frame_cb;
    memcpy(rrl_snap[0], rrl_poweron, rrl_snap_size); memcpy(rrl_snap[1], rrl_poweron, rrl_snap_size);
    rrl_pending = false;
    if (!smsrecomp_snap_load(rrl_snap[0], rrl_snap_size)) rrl_fail("power-on state");     /* console 0 is the power-on state again */
    rrl_on = true;
    rrl_cur = 0; rrl_chunk = g_vdp.line / RRL_SLICE_LINES;
    g_pad1 = rrl_pad[0]; g_pad2 = 0;
    fprintf(stderr, "[link] Gear-to-Gear cable: two Game Gears in one process, this PC shows console %d, slice %d lines\n",
        rrl_seat + 1, RRL_SLICE_LINES);
}

/* Start of a run (and of every reset): the power-on state is kept; the pair begins now when it was asked for (the environment), or at the
 * next instruction boundary once a session asks (smsrecomp_link_request). */
static void rrl_start(void) {
    rrl_on = false; rrl_pending = false;
    if (!rrl_capable()) return;
    rrl_snap_size = smsrecomp_snap_bound();
    if (!rrl_snap_size) return;
    if (!rrl_poweron) rrl_poweron = (uint8_t *)malloc(rrl_snap_size);
    if (!rrl_poweron || smsrecomp_snap_save(rrl_poweron, rrl_snap_size) != rrl_snap_size) rrl_fail("power-on snapshot");
    if (smsrecomp_link_enabled()) rrl_begin();
}

/* The hooks of the banked loop. */
/* RETRO_RECOMP_GG_LINK_TRACE=<lines>: the first accesses to the EXT ports and NMIs, with console, frame, cycle and pc (a developer's trace). */
static long rrl_trace_left = -1;
static void rrl_trace(const char *what, unsigned port, unsigned value) {
    if (rrl_trace_left < 0) { const char *t = getenv("RETRO_RECOMP_GG_LINK_TRACE"); rrl_trace_left = t ? atol(t) : 0; }
    if (rrl_trace_left == 0) return;
    static long from = -1;
    if (from < 0) { const char *f = getenv("RETRO_RECOMP_GG_LINK_TRACE_FROM"); from = f ? atol(f) : 0; }
    if ((long)g_frame < from) return;
    static int last[2][8] = {{-1, -1, -1, -1, -1, -1, -1, -1}, {-1, -1, -1, -1, -1, -1, -1, -1}};
    if (what[0] == 'I' && port < 8 && !getenv("RETRO_RECOMP_GG_LINK_TRACE_ALL")) {        /* a poll that reads the same value again says nothing */
        if (last[rrl_cur][port] == (int)value) return;
        last[rrl_cur][port] = (int)value;
    }
    --rrl_trace_left;
    fprintf(stderr, "[link-trace] c%d f%llu cyc=%llu pc=%04X %s $%02X %02X\n", rrl_cur + 1, (unsigned long long)g_frame,
        (unsigned long long)g_z80.cyc, g_z80.pc, what, port, value);
}
static inline bool rrl_irq(void) { return gg_ext_irq(&rrl_ext[rrl_cur], &rrl_cable, rrl_cur, g_z80.cyc); }
static inline bool rrl_nmi(void) {
    const bool edge = gg_ext_nmi(&rrl_ext[rrl_cur], &rrl_cable, rrl_cur, g_z80.cyc);
    if (edge) rrl_trace("NMI", 0, 0);
    return edge;
}
static uint8_t rrl_port_in(uint8_t port) {
    const uint8_t value = gg_ext_in(&rrl_ext[rrl_cur], &rrl_cable, rrl_cur, port, g_z80.cyc);
    rrl_trace("IN ", port, value);
    return value;
}
static void rrl_port_out(uint8_t port, uint8_t value) {
    rrl_trace("OUT", port, value);
    gg_ext_out(&rrl_ext[rrl_cur], &rrl_cable, rrl_cur, port, value, g_z80.cyc);
}

/* The Z80 NMI: the return address is pushed, execution goes on at $0066, IFF1 is cleared and IFF2 keeps the previous state. */
static void banked_accept_nmi(void) {
    if (g_z80.p) g_z80.f &= (uint8_t)~Z80_FLAG_P;
    g_z80.p = g_z80.q = 0; g_z80.ei_block = 0;
    g_z80.iff1 = false; g_z80.halted = false;
    g_z80.r = (uint8_t)((g_z80.r & 0x80) | ((g_z80.r + 1) & 0x7F));
    g_z80.cyc += 11;
    g_z80.sp = (uint16_t)(g_z80.sp - 2); sms_write16(g_z80.sp, g_z80.pc);
    g_z80.pc = 0x0066; g_z80.wz = g_z80.pc;
}

/* A picture of each console at the end of the frames named by RETRO_RECOMP_GG_LINK_PNG_FRAMES ("300,600"), written as
 * <RETRO_RECOMP_GG_LINK_PNG>.f<frame>.<console>.png: a developer's way to see both screens of a headless run. */
static void rrl_dump_pictures(void) {
    static const char *prefix; static const char *frames; static int probed;
    if (!probed) { probed = 1; prefix = getenv("RETRO_RECOMP_GG_LINK_PNG"); frames = getenv("RETRO_RECOMP_GG_LINK_PNG_FRAMES"); }
    if (!prefix || !frames) return;
    bool wanted = false;
    for (const char *p = frames; *p; ) {
        char *end; const unsigned long long frame = strtoull(p, &end, 10);
        if (end == p) break;
        if (frame == g_frame) wanted = true;
        p = *end == ',' ? end + 1 : end;
    }
    if (!wanted) return;
    const int live = rrl_cur;
    for (int c = 0; c < 2; ++c) {
        if (!rrl_load(c)) return;
        smsrecomp_video_present(g_fb);
        char path[512];
        snprintf(path, sizeof path, "%s.f%llu.%d.png", prefix, (unsigned long long)g_frame, c + 1);
        png_write_argb(path, g_fb, SMS_SCREEN_W, SMS_SCREEN_H, SMS_SCREEN_W);
    }
    rrl_load(live);
}

/* Both consoles finished a slice, console 1 last: a frame the two have finished goes to the host kit, then the next round. */
static void rrl_round_end(void) {
    ++rrl_rounds;
    if (g_frame != rrl_delivered) {
        rrl_delivered = g_frame;
        rrl_dump_pictures();
        rrl_selftest();
        if (rrl_host.frame_done && !rrl_host.frame_done()) { rrl_report(); if (g_running) longjmp(g_quit_env, 1); }
    }
    if (rrl_limit && g_frame >= rrl_limit) { rrl_report(); if (g_running) longjmp(g_quit_env, 1); }
}

/* After a completed instruction: the slice ends when the line crosses a multiple of 32 (or the frame wraps). */
static void rrl_after_step(void) {
    if (!rrl_on) { rrl_pending = false; if (rrl_poweron) rrl_begin(); return; }
    if ((g_vdp.line / RRL_SLICE_LINES) == rrl_chunk) return;
    if (!rrl_save_live()) rrl_fail("save");
    ++rrl_swaps;
    if (rrl_cur == 1) rrl_round_end();
    if (!rrl_load(rrl_cur ^ 1)) rrl_fail("load");
}

/* ---- the host kit's view: one machine made of the two consoles, in seat order ---- */
typedef struct { uint32_t magic, size; uint64_t delivered; uint32_t current, pad[2]; } RrlHead;
size_t smsrecomp_link_snap_bound(void) {
    const size_t one = smsrecomp_snap_bound();
    return one ? sizeof(RrlHead) + 2 * (one + sizeof(GgExt)) + sizeof(GgCable) : 0;
}
size_t smsrecomp_link_snap_save(void *buffer, size_t capacity) {
    const size_t size = smsrecomp_link_snap_bound();
    /* A session that has asked and whose pair has not begun yet (it begins at the next instruction boundary, from the power-on state): the
     * snapshot is the pair as it will begin, so that a load of it later puts the pair back at its start. */
    const bool coming = !rrl_on && rrl_pending && rrl_poweron;
    if (!size || !buffer || capacity < size || (!rrl_on && !coming) || (rrl_on && !rrl_save_live())) return 0;
    uint8_t *out = (uint8_t *)buffer;
    RrlHead head; memset(&head, 0, sizeof head);
    head.magic = RRL_MAGIC; head.size = (uint32_t)rrl_snap_size;
    head.delivered = coming ? 0 : rrl_delivered; head.current = coming ? 1u : (uint32_t)rrl_cur;
    head.pad[0] = coming ? 0 : rrl_pad[0]; head.pad[1] = coming ? 0 : rrl_pad[1];
    memcpy(out, &head, sizeof head); out += sizeof head;
    GgExt fresh; gg_ext_reset(&fresh);
    GgCable cable = rrl_cable; if (coming) gg_cable_reset(&cable);
    for (int c = 0; c < 2; ++c) {
        memcpy(out, coming ? rrl_poweron : rrl_snap[c], rrl_snap_size); out += rrl_snap_size;
        memcpy(out, coming ? &fresh : &rrl_ext[c], sizeof(GgExt)); out += sizeof(GgExt);
    }
    memcpy(out, &cable, sizeof cable);
    return size;
}
bool smsrecomp_link_snap_load(const void *buffer, size_t size) {
    if (!rrl_on || !buffer || size != smsrecomp_link_snap_bound()) return false;
    const uint8_t *in = (const uint8_t *)buffer;
    RrlHead head; memcpy(&head, in, sizeof head); in += sizeof head;
    if (head.magic != RRL_MAGIC || head.size != rrl_snap_size || head.current > 1) return false;
    GgExt ext[2]; GgCable cable;
    const uint8_t *snap[2];
    for (int c = 0; c < 2; ++c) {
        snap[c] = in; in += rrl_snap_size;
        memcpy(&ext[c], in, sizeof(GgExt)); in += sizeof(GgExt);
    }
    memcpy(&cable, in, sizeof cable);
    if (!gg_ext_valid(&ext[0]) || !gg_ext_valid(&ext[1]) || !gg_cable_valid(&cable)) return false;
    /* Each console's snapshot checks itself when it is loaded: a buffer that is the kit's own never fails here. */
    const int live = rrl_cur;
    for (int c = 0; c < 2; ++c) {
        if (!smsrecomp_snap_load(snap[c], rrl_snap_size)) { rrl_load(live); return false; }
    }
    for (int c = 0; c < 2; ++c) memcpy(rrl_snap[c], snap[c], rrl_snap_size);
    rrl_ext[0] = ext[0]; rrl_ext[1] = ext[1]; rrl_cable = cable; rrl_delivered = head.delivered;
    rrl_cur = (int)head.current;
    return rrl_load(rrl_cur);
}

/* The digest: both consoles in seat order, then the cable, as named fields (never a raw struct). */
uint64_t smsrecomp_link_digest(void) {
    if (!rrl_on) return smsrecomp_digest();      /* a session about to link: the one console, the same on every seat */
    if (!rrl_save_live()) return 0;
    const int live = rrl_cur;
    uint64_t hash = 14695981039346656037ull;
    for (int c = 0; c < 2; ++c) {
        if (!rrl_load(c)) return 0;
        const uint64_t d = smsrecomp_digest();
        for (int i = 0; i < 8; ++i) { hash ^= (uint8_t)(d >> (8 * i)); hash *= 1099511628211ull; }
        uint8_t bytes[GG_EXT_STATE_BYTES];
        const size_t n = gg_ext_state_bytes(&rrl_ext[c], bytes, sizeof bytes);
        for (size_t i = 0; i < n; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    }
    uint8_t bytes[GG_CABLE_STATE_BYTES];
    const size_t n = gg_cable_state_bytes(&rrl_cable, bytes, sizeof bytes);
    for (size_t i = 0; i < n; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    rrl_load(live);
    return hash;
}

/* RETRO_RECOMP_GG_LINK_SELFTEST=<frame>: the rollback of the pair, checked inside the game. At that frame the two consoles are
 * saved; 40 frames on the digest is taken, the snapshot is loaded (the digest must be the saved one at once) and the same 40
 * frames are run again: the digest must be the same as the first time. Prints "[link] rollback check PASS" or FAIL. */
static void rrl_selftest(void) {
    static int mode = -1, phase;
    static uint64_t first, later; static uint8_t *buffer; static size_t size; static uint64_t at, until;
    if (mode < 0) {
        const char *value = getenv("RETRO_RECOMP_GG_LINK_SELFTEST");
        mode = value ? 1 : 0; at = value ? strtoull(value, NULL, 0) : 0; until = at + 40;
    }
    if (!mode) return;
    if (phase == 0 && g_frame == at) {
        size = smsrecomp_link_snap_bound();
        buffer = (uint8_t *)malloc(size);
        if (!buffer || smsrecomp_link_snap_save(buffer, size) != size) { fprintf(stderr, "[link] rollback check FAIL: save\n"); phase = 9; return; }
        first = smsrecomp_link_digest(); phase = 1;
        fprintf(stderr, "[link] rollback check: saved at frame %llu, digest %016llx, %zu bytes\n", (unsigned long long)g_frame, (unsigned long long)first, size);
    } else if (phase == 1 && g_frame == until) {
        later = smsrecomp_link_digest();
        const bool changed = later != first;
        const bool loaded = smsrecomp_link_snap_load(buffer, size);
        const uint64_t again = loaded ? smsrecomp_link_digest() : 0;
        fprintf(stderr, "[link] rollback check: at frame %llu digest %016llx (differs from the saved: %s); loaded %s, digest after the load %016llx (%s the saved)\n",
            (unsigned long long)until, (unsigned long long)later, changed ? "yes" : "NO", loaded ? "yes" : "NO", (unsigned long long)again, again == first ? "equals" : "DIFFERS FROM");
        phase = (loaded && again == first && changed) ? 2 : 9;
        if (phase == 9) fprintf(stderr, "[link] rollback check FAIL: the load\n");
    } else if (phase == 2 && g_frame == until) {
        const uint64_t replay = smsrecomp_link_digest();
        fprintf(stderr, "[link] rollback check %s: the same %llu frames run again give digest %016llx (first time %016llx)\n",
            replay == later ? "PASS" : "FAIL", (unsigned long long)(until - at), (unsigned long long)replay, (unsigned long long)later);
        phase = 3;
    }
}
