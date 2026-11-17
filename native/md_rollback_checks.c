/* Multiplayer rollback of the Mega Drive (md_backend.c, rr16_md_snap_*), linked with the objects of an actual game build
 * (tools/megadrive_rollback_selftest.py). Save at a frame end, run frames with changing pads, load, run the same frames:
 * every frame's digest and sound must be identical and the snapshot taken after them byte for byte the same. A save over
 * a buffer of other bytes gives the same bytes; a wrong size, a short buffer or a wrong header is refused.
 *
 * `authored`: an authored program in work RAM (no game code runs) makes frames end inside the cases a quick state refuses:
 * the 68000 suspended in an instruction under a 68000-to-VRAM DMA, the sound CPU suspended in a read of the 68000 bus, a
 * bus request not yet granted. Each kind must be met and pass (busy_frame_end_exact). Negative controls load a snapshot
 * with one of its private parts taken from the later state: the replay must notice.
 * `game`: the build's own game from power-on, frames with changing pads, a check every few frames and at each busy end.
 * A development check, outside the stamps: it is not compiled into a game. */
#include "platform_io.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "genesis_runtime.h"
#include "sim_step.h"
#include "md_prefetch.h"
#include "genesis_machine.c"
#include "rb_state.h"
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
extern size_t rr16_md_snap_bound(void);
extern size_t rr16_md_snap_save(void *buffer, size_t capacity);
extern bool rr16_md_snap_load(const void *buffer, size_t size);
extern uint64_t rr16_md_digest(void);
extern size_t rr16_md_snap_peak_exec, rr16_md_snap_peak_events, rr_md_bus_live_stack_peak;
static unsigned checks;
#define CHECK(ok) do { ++checks; if (!(ok)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #ok); exit(1); } } while (0)

#define RUN 8u                       /* frames run from a snapshot, then again after loading it */
enum { PART_EXEC, PART_CPU, PART_SCHED, PART_RAM, PART_BUS, PART_VDP, PART_FM, PART_PSG, PART_EVQ, PART_INPUT,
       PART_GLUE, PART_INTERP, PART_Z80, PART_YM, PART_GUN, PART_CART, PART_TAP, PARTS };
static const char *const part_names[PARTS] = {"exec", "cpu", "sched", "ram", "bus", "vdp", "fm", "psg", "evq", "input",
                                             "glue", "interp", "z80", "ym", "gun", "cart", "tap"};
static uint8_t *start, *first, *second, *mixed;
static size_t bound;
static uint32_t seed = 0x2468ace1u;
static uint16_t pad_word(void) { seed = seed * 1664525u + 1013904223u; return (uint16_t)(seed >> 16) & 0x0fffu; }
typedef struct { unsigned tested, instruction, sound_cpu, handshake, max_size; size_t largest; } Tally;
static Tally tally;

static int part_span(const uint8_t *b, size_t size, unsigned part, size_t *at, uint32_t *length) {
    size_t p = 8;
    for (unsigned i = 0; i < PARTS; ++i) {
        uint32_t n; if (size - p < 4) return 0;
        memcpy(&n, b + p, 4); p += 4;
        if (i == part) { *at = p; *length = n; return 1; }
        p += n;
    }
    return 0;
}
/* The bytes of a part that must be identical after an exact replay. The two fibers' stack images are left out: below
 * the live frames' values they hold whatever earlier, deeper calls left in padding and unused slots, which differs
 * between a run and its replay without being read. What the stacks decide is compared instead: their length (the saved
 * stack pointer) here, and the game fiber's address-free view (its resume site, PC and tail frames) in `views`. */
static size_t compared_bytes(unsigned part, const uint8_t *p, uint32_t length) {
    if (part == PART_EXEC) return length < 12 ? length : 12;   /* the tail frame head and the image's length */
    if (part == PART_BUS) {
        unsigned points, instructions, undos;
        const size_t fixed = RR_MD_BUS_LIVE(RR_MD_LIVE_SIZE) 0;
        if (length < fixed + 4) return length;
        memcpy(&points, p, sizeof points); memcpy(&instructions, p + sizeof points, sizeof instructions);
        memcpy(&undos, p + sizeof points + sizeof instructions, sizeof undos);
        size_t lazy = points * sizeof *rr_lazy_point + instructions * sizeof *rr_lazy_instruction + undos * sizeof *rr_lazy_undo;
        return fixed + lazy + 4 <= length ? fixed + lazy + 4 : length;   /* up to the stack image's length */
    }
    return length;
}
/* The first part that differs, or -1. */
static int differing_part(const uint8_t *a, size_t an, const uint8_t *b, size_t bn) {
    for (unsigned part = 0; part < PARTS; ++part) {
        size_t ao, bo; uint32_t al, bl;
        if (!part_span(a, an, part, &ao, &al) || !part_span(b, bn, part, &bo, &bl)) return (int)part;
        if (al != bl || memcmp(a + ao, b + bo, compared_bytes(part, a + ao, al))) return (int)part;
    }
    return an == bn ? -1 : PARTS;
}
static uint64_t exec_view(void) { return glue_rb_exec_digest(14695981039346656037ull); }
static void run_frames(const uint16_t *pads, uint64_t *digests, uint64_t *sounds) {
    for (unsigned k = 0; k < RUN; ++k) {
        rr16_frame(pads[2 * k], pads[2 * k + 1]);
        digests[k] = rr16_md_digest(); sounds[k] = rr16_audio_frame_fingerprint();
    }
}
/* Save, run RUN frames, load, run them again: identical. Returns 1. With `swap` (a negative control: the snapshot loaded
 * has that part from the later state) it returns 0 when the replay differs, 2 when the part was the same (no case) and
 * 3 when the load refused it; the machine then goes back to the true later state. Otherwise the state afterwards is the
 * replayed one. */
static int rollback(int swap) {
    uint16_t pads[2 * RUN];
    for (unsigned k = 0; k < 2 * RUN; ++k) pads[k] = pad_word();
    size_t n = rr16_md_snap_save(start, bound);
    CHECK(n && n <= bound);
    if (n > tally.largest) tally.largest = n;
    uint64_t d1[RUN], s1[RUN], d2[RUN], s2[RUN];
    run_frames(pads, d1, s1);
    size_t n1 = rr16_md_snap_save(first, bound);
    uint64_t v1 = exec_view();
    CHECK(n1);
    if (swap >= 0) {
        /* The snapshot with part `swap` from the later state (same length, or the control is skipped). */
        size_t so, fo; uint32_t sl, fl;
        CHECK(part_span(start, n, (unsigned)swap, &so, &sl) && part_span(first, n1, (unsigned)swap, &fo, &fl));
        if (sl != fl || !memcmp(start + so, first + fo, sl)) { CHECK(rr16_md_snap_load(first, n1)); return 2; }
        memcpy(mixed, start, n); memcpy(mixed + so, first + fo, sl);
        if (!rr16_md_snap_load(mixed, n)) { CHECK(rr16_md_snap_load(first, n1)); return 3; }
        run_frames(pads, d2, s2);
        size_t n2 = rr16_md_snap_save(second, bound);
        int same = n2 && !memcmp(d1, d2, sizeof d1) && !memcmp(s1, s2, sizeof s1) && differing_part(first, n1, second, n2) < 0
                   && exec_view() == v1;
        CHECK(rr16_md_snap_load(first, n1));
        return same;
    } else {
        CHECK(rr16_md_snap_load(start, n));
    }
    run_frames(pads, d2, s2);
    size_t n2 = rr16_md_snap_save(second, bound);
    uint64_t v2 = exec_view();
    CHECK(n2);
    int same = !memcmp(d1, d2, sizeof d1) && !memcmp(s1, s2, sizeof s1) && differing_part(first, n1, second, n2) < 0 &&
               v1 == v2;
    if (swap < 0 && !same) {
        unsigned k = 0; while (k < RUN && d1[k] == d2[k] && s1[k] == s2[k]) ++k;
        fprintf(stderr, "replay differs: frame +%u of %u, digest %s, sound %s, game fiber view %s, first part %s\n",
                k + 1, RUN, k < RUN && d1[k] != d2[k] ? "differs" : "same", k < RUN && s1[k] != s2[k] ? "differs" : "same",
                v1 != v2 ? "differs" : "same",
                differing_part(first, n1, second, n2) >= 0 && differing_part(first, n1, second, n2) < PARTS ?
                part_names[differing_part(first, n1, second, n2)] : "framing");
        CHECK(same);
    }
    return same;
}
static void kinds_now(int *instruction, int *sound, int *handshake) {
    *instruction = rr16_md_instruction_busy();
    *sound = rr_z80_busy != 0;
    *handshake = g_machine.bus.z80_busreq && g_machine.bus.z80_reset_off && !rr_local_ack;
}
static void tested_here(void) {
    int i, s, h; kinds_now(&i, &s, &h);
    ++tally.tested; tally.instruction += i; tally.sound_cpu += s; tally.handshake += h;
}
static void buffer_rules(void) {
    /* A save over other bytes gives the same bytes; short buffers and wrong sizes or headers are refused. */
    memset(first, 0xaa, bound); memset(second, 0x55, bound);
    size_t a = rr16_md_snap_save(first, bound), b = rr16_md_snap_save(second, bound);
    CHECK(a && a == b && !memcmp(first, second, a));
    CHECK(!rr16_md_snap_save(first, bound - 1) && !rr16_md_snap_save(NULL, bound));
    CHECK(!rr16_md_snap_load(first, a - 1) && !rr16_md_snap_load(first, a + 1) && !rr16_md_snap_load(NULL, a));
    memcpy(mixed, first, a); mixed[0] ^= 1; CHECK(!rr16_md_snap_load(mixed, a));
    CHECK(rr16_md_snap_load(first, a));
    size_t c = rr16_md_snap_save(second, bound);
    CHECK(c == a && !memcmp(first, second, a));   /* a load then a save gives the bytes back */
}

static void put16(uint32_t address, const uint16_t *words, size_t count) {
    for (size_t i = 0; i < count; ++i) gbus_write16(&g_machine.bus, address + 2u * (uint32_t)i, words[i]);
}
static int authored(void) {
    GenesisMachine *m = &g_machine;
    g_cpu.SR = 0x2700; g_cpu.A[7] = 0xffff00;
    rr_md_portable_restart(1); rr_md_portable_arm(0xff0100); rr_md_cpu_stopped = 0;
    /* The sound CPU reads the 68000's bus through its bank window in a loop: each read waits for the bus. */
    static const uint8_t z80[] = {0x3a, 0x00, 0x80, 0x32, 0x00, 0x10, 0xc3, 0x00, 0x00};
    memset(m->bus.z80_ram, 0, sizeof m->bus.z80_ram); memcpy(m->bus.z80_ram, z80, sizeof z80);
    m->bus.z80_reset_off = 1; m->bus.z80_busreq = m->bus.z80_reset_pending = 0;
    z80_own_reset(&m->z80); m->bus.z80_bank = 0x1c0;
    /* The 68000: a 68000-to-VRAM DMA of 6K words with the display on (it holds the CPU for most of a frame), a long
     * read-modify-write in RAM (a counter), then up to 4096 bus requests, as many as the counter says, each polled until
     * granted and released; again. */
    static const uint16_t code[] = {
        0x41f9, 0x00c0, 0x0004,            /* lea $C00004,a0 */
        0x30bc, 0x8174, 0x30bc, 0x8f02,    /* display and DMA on (VINT masked by SR); auto-increment 2 */
        0x30bc, 0x9300, 0x30bc, 0x9418,    /* length $1800 words */
        0x30bc, 0x9500, 0x30bc, 0x9680, 0x30bc, 0x977f,   /* source $FF0000 */
        0x30bc, 0x4000, 0x30bc, 0x0080,    /* VRAM 0, DMA: the CPU waits in this write */
        0x52b9, 0x00ff, 0xf000,            /* addq.l #1,$FFF000 */
        0x3e39, 0x00ff, 0xf002,            /* move.w $FFF002,d7 */
        0xeb4f, 0x0247, 0x0fff,            /* lsl.w #5,d7; andi.w #$FFF,d7: a count that moves the frame ends */
        0x33fc, 0x0100, 0x00a1, 0x1100,    /* move.w #$100,$A11100: bus request */
        0x0839, 0x0000, 0x00a1, 0x1100,    /* btst #0,$A11100 */
        0x66f6,                            /* bne.s the btst */
        0x33fc, 0x0000, 0x00a1, 0x1100,    /* release */
        0x51cf, 0xffe4,                    /* dbra d7,the request */
        0x60aa,                            /* bra.s the register writes */
    };
    put16(0xff0100, code, sizeof code / sizeof *code);
    /* Each frame end of the first frames: a rollback check where the bus is busy, and every fourth one anyway. */
    for (unsigned frame = 0; frame < 240; ++frame) {
        int i, s, h; kinds_now(&i, &s, &h);
        if (i || s || h || frame % 4 == 0) { tested_here(); rollback(-1); }
        else rr16_frame(pad_word(), pad_word());
    }
    unsigned loops = (unsigned)g_ram[0xf000] << 24 | g_ram[0xf001] << 16 | g_ram[0xf002] << 8 | g_ram[0xf003];
    printf(",\"authored\":{\"tested\":%u,\"instruction_busy\":%u,\"sound_cpu_busy\":%u,\"handshake_pending\":%u,"
           "\"program_loops\":%u,\"pc\":%u}", tally.tested, tally.instruction, tally.sound_cpu, tally.handshake, loops,
           (unsigned)g_cpu.PC);
    CHECK(loops > 8);   /* the program goes round: its frame ends fall at different points */
    CHECK(tally.instruction && tally.sound_cpu && tally.handshake);   /* busy_frame_end_exact: every kind met */
    /* Negative controls at busy frame ends: a part taken from the later state must be noticed by the replay. */
    printf(",\"negative_controls\":{");
    static const unsigned controls[] = {PART_EXEC, PART_BUS, PART_GLUE, PART_INTERP, PART_Z80, PART_CPU, PART_RAM};
    for (size_t c = 0; c < sizeof controls / sizeof *controls; ++c) {
        unsigned seen = 0, tried = 0, refused = 0;
        for (unsigned attempt = 0; attempt < 40 && !seen; ++attempt) {
            int i, s, h; kinds_now(&i, &s, &h);
            if (!(i || s)) { rr16_frame(pad_word(), pad_word()); continue; }
            int r = rollback((int)controls[c]);
            if (r == 0 || r == 1) { ++tried; seen += r == 0; }
            refused += r == 3;
        }
        printf("%s\"%s\":\"%s\"", c ? "," : "", part_names[controls[c]],
               seen ? "noticed" : tried ? "not_noticed" : refused ? "refused_by_load" : "no_case");
    }
    printf("}");
    return 1;
}
static int game(unsigned frames) {
    for (unsigned frame = 0; frame < frames; ++frame) {
        int i, s, h; kinds_now(&i, &s, &h);
        if (((i || s || h) && tally.tested < 400) || frame % 16 == 0) { tested_here(); rollback(-1); }
        else rr16_frame(pad_word(), pad_word());
    }
    printf(",\"game\":{\"frames\":%u,\"tested\":%u,\"instruction_busy\":%u,\"sound_cpu_busy\":%u,\"handshake_pending\":%u}",
           frames, tally.tested, tally.instruction, tally.sound_cpu, tally.handshake);
    return 1;
}
/* The multitaps (retrorecomp/megadrive_multitap.py), driven through the bus as a game drives them, whatever the build's own
 * adapter: the Team Player's sequence, the 4 Way Play's selection and signature, the J-Cart's two pads at both addresses, a
 * plain pad when the game speaks neither, and the adapters' state in the rollback snapshot. */
extern int rr_md_tap_mode;
extern void rr16_md_extra_pads(uint16_t p3, uint16_t p4);
#define PAD_U 0x01
#define PAD_D 0x02
#define PAD_L 0x04
#define PAD_R 0x08
#define PAD_B 0x10
#define PAD_C 0x20
#define PAD_A 0x40
#define PAD_S 0x80
static uint8_t io(uint32_t port_data, uint8_t value) { gbus_write8(&g_machine.bus, port_data, value); return gbus_read8(&g_machine.bus, port_data); }
static void multitap(void) {
    GenesisBus *b = &g_machine.bus;
    const uint16_t pads[4] = {PAD_U | PAD_A, PAD_D | PAD_B, PAD_L | PAD_C, PAD_R | PAD_S};
    b->pad[0] = pads[0]; b->pad[1] = pads[1]; rr16_md_extra_pads(pads[2], pads[3]);
    rr_md_tap_mode = 1;
    /* The Team Player as games identify it, with TH alone as an output ($70 / $30 written, TR left high): 3, then F. */
    gbus_write8(b, 0xa10009, 0x40);
    CHECK(io(0xa10003, 0x70) == 0x73);
    CHECK(io(0xa10003, 0x30) == 0x3f);
    /* Then TH and TR as outputs for the handshake and the data, TL echoing TR. */
    gbus_write8(b, 0xa10009, 0x60);
    CHECK(io(0xa10003, 0x00) == 0x00);                    /* acknowledge 0, TL low */
    CHECK(io(0xa10003, 0x20) == 0x30);
    const uint8_t type = RR_MD_SIX_BUTTONS ? 1 : 0;
    for (int pad = 0; pad < 4; ++pad) CHECK((io(0xa10003, (uint8_t)(pad & 1 ? 0x20 : 0x00)) & 0x0f) == type);
    const unsigned groups = RR_MD_SIX_BUTTONS ? 3 : 2;
    unsigned tr = 0x20;   /* the last type read left TR high */
    for (int pad = 0; pad < 4; ++pad) {
        const uint16_t p = pads[pad];
        const uint8_t want[3] = {
            (uint8_t)(~(((p & PAD_R) ? 8 : 0) | ((p & PAD_L) ? 4 : 0) | ((p & PAD_D) ? 2 : 0) | ((p & PAD_U) ? 1 : 0)) & 15),
            (uint8_t)(~(((p & PAD_S) ? 8 : 0) | ((p & PAD_A) ? 4 : 0) | ((p & PAD_C) ? 2 : 0) | ((p & PAD_B) ? 1 : 0)) & 15),
            0x0f};
        for (unsigned g = 0; g < groups; ++g) { tr ^= 0x20; CHECK((io(0xa10003, (uint8_t)tr) & 0x0f) == want[g]); }
    }
    CHECK(io(0xa10003, 0x60) == 0x73);                    /* TH high starts again */
    /* The 4 Way Play: selection on port B, signature $7C, then each pad through port A with port A's TH. */
    gbus_write8(b, 0xa10009, 0x40); gbus_write8(b, 0xa1000b, 0x7f);
    gbus_write8(b, 0xa10005, 0x7c);
    CHECK(io(0xa10003, 0x40) == 0x7c);
    for (int pad = 0; pad < 4; ++pad) {
        const uint16_t p = pads[pad];
        gbus_write8(b, 0xa10005, (uint8_t)(pad << 4 | 0x0c));
        const uint8_t high = (uint8_t)(0x40 | (~(((p & PAD_C) ? 0x20 : 0) | ((p & PAD_B) ? 0x10 : 0) | ((p & PAD_R) ? 8 : 0) |
                                                 ((p & PAD_L) ? 4 : 0) | ((p & PAD_D) ? 2 : 0) | ((p & PAD_U) ? 1 : 0)) & 0x3f));
        const uint8_t low = (uint8_t)(~(((p & PAD_S) ? 0x20 : 0) | ((p & PAD_A) ? 0x10 : 0) | ((p & PAD_D) ? 2 : 0) |
                                        ((p & PAD_U) ? 1 : 0)) & 0x33);
        CHECK(io(0xa10003, 0x40) == high);
        CHECK(io(0xa10003, 0x00) == low);
    }
    CHECK(gbus_read8(b, 0xa10005) == 0x7f);               /* port B carries no pad of its own */
    /* The adapters' state is part of the rollback snapshot: a selection made after a save is undone by its load. */
    gbus_write8(b, 0xa10005, 0x2c);
    size_t n = rr16_md_snap_save(start, bound);
    CHECK(n);
    gbus_write8(b, 0xa10005, 0x7c);
    CHECK(io(0xa10003, 0x40) == 0x7c);
    CHECK(rr16_md_snap_load(start, n));
    CHECK(io(0xa10003, 0x40) != 0x7c);
    /* The J-Cart: pads 3 and 4 at $38FFFE and $3FFFFE, bit 0 of a write as TH. */
    rr_md_tap_mode = 2;
    for (uint32_t at = 0x38fffe; at <= 0x3ffffe; at += 0x070000) {
        gbus_write16(b, at, 1);
        uint16_t w = gbus_read16(b, at);
        CHECK((w & 0xff) == (0xc0 | (~(PAD_L | PAD_C) & 0x3f)) && (w >> 8) == (0xc0 | (~PAD_R & 0x3f)));
        gbus_write8(b, at + 1, 0);
        w = gbus_read16(b, at);
        CHECK((w & 0xff) == (0x80 | 0x33) && (w >> 8) == (0x80 | (~0x20 & 0x33)));   /* pad 4: Start */
        CHECK(gbus_read8(b, at) == (w >> 8) && gbus_read8(b, at + 1) == (w & 0xff));
    }
    rr_md_tap_mode = 0;
    gbus_write8(b, 0xa10009, 0x40);
    CHECK(io(0xa10003, 0x40) == (0x40 | (~PAD_U & 0x3f)));   /* no adapter: the ordinary pad */
    printf(",\"multitap\":{\"team_player\":true,\"way_play\":true,\"j_cart\":true,\"plain_pad\":true,\"snapshot\":true}");
}
static int checks_main(int argc, wchar_t **argv) {
    CHECK(argc >= 2 && rr16_init(true));
    bound = rr16_md_snap_bound();
    CHECK(bound > 0);
    start = malloc(bound); first = malloc(bound); second = malloc(bound); mixed = malloc(bound);
    CHECK(start && first && second && mixed);
    printf("{\"bound\":%zu", bound);
    buffer_rules();
    if (!wcscmp(argv[1], L"authored")) authored();
    else if (!wcscmp(argv[1], L"multitap")) multitap();
    else game(argc >= 3 ? (unsigned)wcstoul(argv[2], NULL, 10) : 1800u);
    buffer_rules();
    printf(",\"largest_save\":%zu,\"game_stack_peak\":%zu,\"sound_stack_peak\":%zu,\"events_peak\":%zu,\"checks\":%u,"
           "\"passed\":true}\n", tally.largest, rr16_md_snap_peak_exec, rr_md_bus_live_stack_peak,
           rr16_md_snap_peak_events, checks);
    rr16_shutdown();
    return 0;
}
#ifdef _WIN32
int wmain(int argc, wchar_t **argv) { return checks_main(argc, argv); }
#else
int main(int argc, char **argv) {
    wchar_t mode[32], frames[32];
    CHECK(argc >= 2 && rr_from_utf8(argv[1], mode, 32));
    if (argc >= 3) CHECK(rr_from_utf8(argv[2], frames, 32));
    wchar_t *args[] = {L"checks", mode, frames};
    return checks_main(argc, args);
}
#endif
