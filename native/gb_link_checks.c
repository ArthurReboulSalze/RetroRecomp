/* Authored checks of the Game Boy link cable (native/gb_link.h, native/gb_machine_state.h): two consoles of one process on one cable, run with
 * the interpreter, no original cartridge byte. One small program (32 KiB, no mapper) runs on both consoles; what it does depends on the START button
 * of its console: pressed, it is the master (internal clock): it sends eight bytes 3 n + $11, one transfer each, and logs what it reads; not
 * pressed, it is the slave (external clock): it sends eight bytes n xor $A5, one per transfer, and logs what it reads. Both wait in HALT for the
 * serial interrupt, whose handler (vector $0058) logs SB in work RAM and counts.
 *
 *  1. The exchange: with console 0 the master, the master's log is the slave's eight bytes, the slave's log is the master's eight, the cable counts
 *     eight exchanges, both serial interrupts ran, and the same with console 1 as the master.
 *  2. No cable partner: a master alone (no link) reads $FF each time; a master whose peer never arms reads $FF and nothing is exchanged.
 *  3. Determinism and snapshots: the pair run in frames, a snapshot of both consoles at every frame boundary, the run replayed from any of them gives
 *     the same digests, logs and exchange count; the pair run again in slices of other lengths ends in a state that equals itself when replayed;
 *     a snapshot taken between the two bytes of the exchange (a transfer in flight) is covered (counted in the summary).
 * The summary is one JSON line; any failure stops the program. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbrt.h"
#include "ppu.h"
#include "audio.h"

enum { FRAMES = 30, LOG = 8, SNAP_MAX = 400000 };

static uint8_t rom_image[0x8000];

/* The interpreter runs the one instruction at the address, as the debug step of the runtime does. */
void gb_dispatch(GBContext* ctx, uint16_t addr) {
    const uint8_t saved = ctx->single_step_mode;
    ctx->single_step_mode = 1;
    gb_interpret(ctx, addr);
    ctx->single_step_mode = saved;
}

static void on_audio(GBContext* ctx, int16_t left, int16_t right) { (void)ctx; (void)left; (void)right; }

static size_t put(size_t at, const char* hex) {
    while (*hex) {
        if (*hex == ' ') { ++hex; continue; }
        unsigned value = 0;
        assert(sscanf(hex, "%2x", &value) == 1);
        rom_image[at++] = (uint8_t)value;
        hex += 2;
    }
    return at;
}

static void build_rom(unsigned limit) {            /* the number of transfers each console makes: 8, or 255 for the replay checks (always one in flight) */
    memset(rom_image, 0, sizeof rom_image);
    put(0x58, "C3 20 02");                                   /* serial: JP 0220 */
    put(0x100, "00 C3 50 01");
    rom_image[0x147] = 0x00; rom_image[0x148] = 0x00; rom_image[0x149] = 0x00;
    put(0x150, "F3 31 FE FF AF E0 80 E0 81 E0 82 E0 0F");    /* DI ; SP ; log index, flag, counter, IF = 0 */
    put(0x15D, "3E 08 E0 FF");                                /* IE = serial */
    put(0x161, "3E 10 E0 00 F0 00 CB 5F FB");                /* select the buttons row ; read it ; BIT 3 (START) ; EI */
    put(0x16A, "CA 90 01 C3 C0 01");                          /* START pressed: the master ; else the slave */
    /* master: send 3 n + $11 on the internal clock, wait for the interrupt, n up to 8 */
    put(0x190, "F0 82 47 87 80 C6 11 E0 01 AF E0 81 3E 81 E0 02");
    put(0x1A0, "76 00 F0 81 A7 CA A0 01 F0 82 FE 08 DA 90 01 18 FE");
    /* slave: send n xor $A5 on the external clock, wait for the interrupt */
    put(0x1C0, "F0 82 EE A5 E0 01 AF E0 81 3E 80 E0 02");
    put(0x1CD, "76 00 F0 81 A7 CA CD 01 F0 82 FE 08 DA C0 01 18 FE");
    /* the serial handler: log SB at C000 + index, count, raise the flag */
    rom_image[0x1AB] = rom_image[0x1D8] = (uint8_t)limit;
    put(0x220, "F5 E5 F0 80 6F 26 C0 F0 01 77 2C 7D E0 80 F0 82 3C E0 82 3E 01 E0 81 E1 F1 D9");
}

static GBJoypadState pads[2];

static void init_console(GBContext* ctx) {
    assert(gb_context_load_rom(ctx, rom_image, sizeof rom_image));
    ctx->callbacks.on_audio_sample = on_audio;
    ctx->pc = 0x150; ctx->halted = 0; ctx->ime = 0; ctx->ime_pending = 0;
}

static GBContext* make_console(void) {
    GBConfig config;
    memset(&config, 0, sizeof config);
    config.model = GB_MODEL_DMG;
    config.enable_audio = true; config.enable_serial = true; config.speed_percent = 100;
    config.rtc_unix_time_override_enabled = true; config.rtc_unix_time_override = 1700000000u;
    config.ignore_rtc_persistence = true;
    GBContext* ctx = gb_context_create(&config);
    assert(ctx);
    init_console(ctx);
    return ctx;
}

/* A pair: console 0 is the first, console 1 the satellite the runtime makes with init_console. `master`: the console whose START is pressed (-1: none). */
static GBContext* make_pair(int master, bool linked) {
    pads[0].dpad = pads[0].buttons = pads[1].dpad = pads[1].buttons = 0xFF;
    if (master >= 0) pads[master].buttons = 0xF7;
    GBContext* first = make_console();
    first->joypad = &pads[0];
    if (linked) {
        gb_link_set_init(init_console);
        assert(gb_link_start(first, 2));
        gb_link_context(1)->joypad = &pads[1];
        assert(gb_link_count() == 2);
    }
    return first;
}

static void end_pair(GBContext* first) {
    gb_link_stop();
    gb_context_destroy(first);
}

static void run_frame(GBContext* first) {
    gb_reset_frame(first);
    first->stopped = 0;
    while (!first->frame_done) gb_run_cycles(first, 0xFFFFFFFFu);
}

static unsigned long slices_made;
static void run_frame_sliced(GBContext* first, unsigned salt) {
    gb_reset_frame(first);
    first->stopped = 0;
    unsigned step = 0;
    while (!first->frame_done) {
        const uint32_t budget = 97u + (uint32_t)((salt * 7919u + step * 104729u) % 2300u);
        gb_run_cycles(first, budget);
        ++step; ++slices_made;
    }
}

static uint64_t fnv(uint64_t hash, const void* data, size_t size) {
    const unsigned char* bytes = (const unsigned char*)data;
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

/* The state of the pair that decides the future: both consoles' digests and their pad registers. */
static uint64_t pair_digest(GBContext* first) {
    uint64_t hash = 1469598103934665603ull;
    for (int i = 0; i < gb_link_count(); ++i) {
        const uint64_t part = rr_gb_digest(i == 0 ? first : gb_link_context(i));
        hash = fnv(hash, &part, sizeof part);
        hash = fnv(hash, &pads[i], sizeof pads[i]);
    }
    return hash;                                              /* (the exchange count is a host-side counter, not machine state) */
}

static uint8_t snaps[2][SNAP_MAX];
static size_t snap_size;

static void pair_save(GBContext* first, uint8_t out[2][SNAP_MAX]) {
    snap_size = rr_gb_snap_bound(first);
    assert(snap_size && snap_size <= SNAP_MAX);
    for (int i = 0; i < gb_link_count(); ++i) assert(rr_gb_snap_save(i == 0 ? first : gb_link_context(i), out[i], SNAP_MAX) == snap_size);
}

static void pair_load(GBContext* first, uint8_t in[2][SNAP_MAX]) {
    for (int i = 0; i < gb_link_count(); ++i) assert(rr_gb_snap_load(i == 0 ? first : gb_link_context(i), in[i], snap_size));
}

static void log_of(GBContext* ctx, uint8_t out[LOG]) { memcpy(out, ctx->wram, LOG); }

static const uint8_t from_master[LOG] = {0x11, 0x14, 0x17, 0x1A, 0x1D, 0x20, 0x23, 0x26};          /* 3 n + $11 */
static const uint8_t from_slave[LOG] = {0xA5, 0xA4, 0xA7, 0xA6, 0xA1, 0xA0, 0xA3, 0xA2};          /* n xor $A5 */

static void expect_exchange(int master) {
    GBContext* first = make_pair(master, true);
    for (int i = 0; i < FRAMES; ++i) run_frame(first);
    GBContext* second = gb_link_context(1);
    uint8_t log0[LOG], log1[LOG];
    log_of(first, log0); log_of(second, log1);
    const uint8_t* want0 = master == 0 ? from_slave : from_master;      /* what console 0 reads */
    const uint8_t* want1 = master == 0 ? from_master : from_slave;
    assert(memcmp(log0, want0, LOG) == 0);
    assert(memcmp(log1, want1, LOG) == 0);
    assert(gb_read8(first, 0xFF82) == 8 && gb_read8(second, 0xFF82) == 8);                      /* both handlers ran eight times */
    assert(gb_link_transfers() == 8);
    assert((first->io[0x02] & 0x80) == 0 && (second->io[0x02] & 0x80) == 0);                    /* no transfer left pending */
    end_pair(first);
}

static void expect_no_partner(void) {
    /* A master with no link at all: every read is $FF, as without a cable. */
    GBContext* alone = make_pair(0, false);
    for (int i = 0; i < FRAMES; ++i) run_frame(alone);
    uint8_t log[LOG];
    log_of(alone, log);
    for (int i = 0; i < LOG; ++i) assert(log[i] == 0xFF);
    assert(gb_read8(alone, 0xFF82) == 8);
    end_pair(alone);
    /* A master whose peer never arms (nobody pressed START: both consoles run the slave program, none is a master): nothing is exchanged. */
    GBContext* first = make_pair(-1, true);
    for (int i = 0; i < FRAMES; ++i) run_frame(first);
    assert(gb_link_transfers() == 0);
    assert(gb_read8(first, 0xFF82) == 0 && gb_read8(gb_link_context(1), 0xFF82) == 0);         /* two slaves wait for a clock that never comes */
    end_pair(first);
    /* A master and a peer that is not a slave (both masters): each reads $FF. */
    pads[0].dpad = pads[0].buttons = pads[1].dpad = pads[1].buttons = 0xFF;
    pads[0].buttons = pads[1].buttons = 0xF7;
    GBContext* both = make_console();
    both->joypad = &pads[0];
    gb_link_set_init(init_console);
    assert(gb_link_start(both, 2));
    gb_link_context(1)->joypad = &pads[1];
    for (int i = 0; i < FRAMES; ++i) run_frame(both);
    uint8_t log0[LOG], log1[LOG];
    log_of(both, log0); log_of(gb_link_context(1), log1);
    for (int i = 0; i < LOG; ++i) assert(log0[i] == 0xFF && log1[i] == 0xFF);
    assert(gb_link_transfers() == 0);
    end_pair(both);
}

typedef struct { unsigned in_flight; unsigned frames_replayed; unsigned slices_replayed; } Coverage;

static void expect_replay(Coverage* coverage) {
    /* The pair run in frames, a snapshot of both consoles at every frame boundary. */
    GBContext* first = make_pair(0, true);
    static uint8_t frame_snap[FRAMES + 1][2][SNAP_MAX];
    uint64_t digests[FRAMES + 1];
    uint64_t exchanges[FRAMES + 1];
    pair_save(first, frame_snap[0]); digests[0] = pair_digest(first); exchanges[0] = gb_link_transfers();
    for (int i = 1; i <= FRAMES; ++i) {
        run_frame(first);
        if ((first->serial_transfer.active || gb_link_context(1)->serial_transfer.active)) ++coverage->in_flight;
        pair_save(first, frame_snap[i]);
        digests[i] = pair_digest(first); exchanges[i] = gb_link_transfers();
    }
    const uint64_t final_digest = digests[FRAMES];
    /* Replay from any frame boundary: the same digests after every frame, the same exchange count. */
    for (int from = 0; from < FRAMES; from += 3) {
        pair_load(first, frame_snap[from]);
        assert(pair_digest(first) == digests[from]);
        for (int i = from + 1; i <= FRAMES; ++i) {
            run_frame(first);
            assert(pair_digest(first) == digests[i]);
            ++coverage->frames_replayed;
        }
        assert(pair_digest(first) == final_digest);
    }
    end_pair(first);
    /* The same pair in slices of other lengths: it equals itself when replayed from a snapshot taken at a slice boundary. */
    for (unsigned salt = 1; salt <= 3; ++salt) {
        first = make_pair(salt == 2 ? 1 : 0, true);
        static uint8_t slice_snap[2][SNAP_MAX];
        uint64_t digest_at_snap = 0, digest_after = 0;
        for (int i = 0; i < 9; ++i) run_frame_sliced(first, salt + (unsigned)i);
        /* a snapshot in the middle of a frame: some slices of the next one */
        gb_reset_frame(first);
        first->stopped = 0;
        gb_run_cycles(first, 1500u + salt * 311u);
        pair_save(first, slice_snap);
        digest_at_snap = pair_digest(first);
        const uint32_t pending = (uint32_t)((first->serial_transfer.active ? 1u : 0u) | (gb_link_context(1)->serial_transfer.active ? 2u : 0u));
        if (pending) ++coverage->in_flight;
        for (unsigned k = 0; k < 6; ++k) { gb_run_cycles(first, 700u + k * 53u); ++slices_made; }
        while (!first->frame_done) gb_run_cycles(first, 613u);
        for (int i = 0; i < 6; ++i) run_frame_sliced(first, salt * 13u + (unsigned)i);
        digest_after = pair_digest(first);
        /* load the mid-frame snapshot and play the identical call sequence */
        pair_load(first, slice_snap);
        assert(pair_digest(first) == digest_at_snap);
        for (unsigned k = 0; k < 6; ++k) gb_run_cycles(first, 700u + k * 53u);
        while (!first->frame_done) gb_run_cycles(first, 613u);
        for (int i = 0; i < 6; ++i) run_frame_sliced(first, salt * 13u + (unsigned)i);
        assert(pair_digest(first) == digest_after);
        ++coverage->slices_replayed;
        end_pair(first);
    }
}

/* The cable must not move a console that runs alone: the same program run with no link equals itself run through the link runner when the link
 * has a single console is not offered (gb_link_start refuses less than two); and the digest of a console moves when its peer's byte differs. */
static void expect_digest_moves(void) {
    GBContext* first = make_pair(0, true);
    for (int i = 0; i < 12; ++i) run_frame(first);
    const uint64_t before = pair_digest(first);
    pads[1].buttons = 0xFE;                                    /* another pad register on the second console: another digest */
    assert(pair_digest(first) != before);
    pads[1].buttons = 0xFF;
    gb_link_context(1)->wram[LOG + 3] ^= 0x5A;                 /* a byte of the second console's memory */
    assert(pair_digest(first) != before);
    end_pair(first);
    GBContext* lonely = make_console();
    assert(!gb_link_start(lonely, 1) && gb_link_count() == 0);
    assert(!gb_link_start(lonely, 5) && gb_link_count() == 0);
    gb_context_destroy(lonely);
}

int main(void) {
    build_rom(8);
    expect_exchange(0);
    expect_exchange(1);
    expect_no_partner();
    Coverage coverage = {0, 0, 0};
    build_rom(255);
    expect_replay(&coverage);
    expect_digest_moves();
    printf("{\"link_checks\":\"ok\",\"frames\":%d,\"frames_replayed\":%u,\"slice_replays\":%u,\"snapshots_with_a_transfer_in_flight\":%u,\"slices\":%lu}\n",
           FRAMES, coverage.frames_replayed, coverage.slices_replayed, coverage.in_flight, slices_made);
    return 0;
}
