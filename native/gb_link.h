/* The Game Boy link cable: two (later more) consoles of one process on one cable. Included at the END of the runtime's gbrt.c
 * (retrorecomp/gameboy_runtime.py), after the machine state, because it uses the static serial tick of the runtime. Original RetroRecomp
 * code: MIT.
 *
 * The model (docs/GAME_BOY.md, "Link cable"): every PC of a multiplayer match runs ALL the linked consoles in one deterministic process. The
 * first console (index 0) is the guest's own context, driven by the generated main; the others are satellites, created here from the same
 * generated init function, and run from inside the first one's gb_run_cycles in fixed chunks, in a fixed order: after each chunk of the
 * first console, every satellite is run up to the same total cycle count. The schedule depends on the consoles' states only, so every PC
 * and every replay after a rollback sees the same interleave.
 *
 * The cable is a byte swap at the end of a master transfer (SC = $81, the internal clock): when the master's eight bits are done, if the
 * other console is armed as a slave (SC bit 7 set, bit 0 clear: the external clock) the two SB registers are exchanged, the slave's SC bit 7
 * is cleared and its serial interrupt is requested; if it is not armed the master reads $FF, as with no cable. Not modelled: the bits
 * shifting in one by one (a read of SB during a transfer sees the old byte), two masters on one cable (each reads $FF), the four-player
 * adapter. A console alone, or in a match without a link, is not changed in any way. */
#ifndef RR_GB_LINK_H
#define RR_GB_LINK_H

#define RR_GB_LINK_MAX 4
#define RR_GB_LINK_CHUNK 256u          /* cycles: a quarter of a transfer, 1/274 of a frame */

static GBContext* g_rr_link_ctx[RR_GB_LINK_MAX];
static int g_rr_link_count;
static void (*g_rr_link_init)(GBContext*);
static uint64_t g_rr_link_transfers;   /* completed exchanges since the link started (host-only, for the self-test and the logs) */

void gb_link_set_init(void (*init)(GBContext*)) { g_rr_link_init = init; }
int gb_link_count(void) { return g_rr_link_count; }
GBContext* gb_link_context(int index) { return index >= 0 && index < g_rr_link_count ? g_rr_link_ctx[index] : NULL; }
uint64_t gb_link_transfers(void) { return g_rr_link_transfers; }

/* Ends the link: the satellites are destroyed, the first console runs alone again. */
void gb_link_stop(void) {
    for (int i = 1; i < g_rr_link_count; ++i) gb_context_destroy(g_rr_link_ctx[i]);
    memset(g_rr_link_ctx, 0, sizeof g_rr_link_ctx);
    g_rr_link_count = 0;
    g_rr_link_transfers = 0;
}

/* Starts a link of `consoles` consoles (2 to RR_GB_LINK_MAX) around `primary`, the guest's own context. The satellites are made from the
 * same generated init (cartridge, mapper, power-on state, native guards), with the primary's configuration and callbacks, never a save id:
 * a satellite reads and writes no file. Returns false (and no link) when the init function is not known or an allocation fails. */
bool gb_link_start(GBContext* primary, int consoles) {
    gb_link_stop();
    if (!primary || consoles < 2 || consoles > RR_GB_LINK_MAX || !g_rr_link_init) return false;
    g_rr_link_ctx[0] = primary;
    g_rr_link_count = 1;
    for (int i = 1; i < consoles; ++i) {
        GBConfig config = primary->config;
        config.ignore_rtc_persistence = true;
        GBContext* satellite = gb_context_create(&config);
        if (!satellite) { gb_link_stop(); return false; }
        g_rr_link_init(satellite);
        satellite->callbacks = primary->callbacks;
        g_rr_link_ctx[g_rr_link_count++] = satellite;
    }
    return true;
}

static bool rr_gb_link_runs(GBContext* ctx) { return g_rr_link_count > 1 && ctx == g_rr_link_ctx[0]; }

/* The master's transfer has ended: the byte the master reads. */
static uint8_t rr_gb_link_exchange(GBContext* ctx, uint8_t outgoing) {
    if (g_rr_link_count != 2) return 0xFF;                 /* more than two consoles need the four-player adapter: not modelled */
    GBContext* peer = ctx == g_rr_link_ctx[0] ? g_rr_link_ctx[1] : ctx == g_rr_link_ctx[1] ? g_rr_link_ctx[0] : NULL;
    if (!peer || (peer->io[0x02] & 0x81) != 0x80) return 0xFF;
    const uint8_t incoming = peer->io[0x01];
    peer->io[0x01] = outgoing;
    peer->io[0x02] &= (uint8_t)~0x80;
    peer->io[0x0F] |= 0x08;
    ++g_rr_link_transfers;
    return incoming;
}

/* Runs a satellite up to the total cycle count `target` (a console that finished its frame waits for the next one). */
static void rr_gb_link_catch_up(GBContext* satellite, uint64_t target) {
    while (!satellite->frame_done && satellite->total_cycles < target) {
        uint64_t behind = target - satellite->total_cycles;
        rr_gb_run_cycles_one(satellite, behind > RR_GB_LINK_CHUNK ? RR_GB_LINK_CHUNK : (uint32_t)behind);
    }
}

/* gb_run_cycles of the first console, with the satellites interleaved: same contract (returns the cycles the first console ran). */
static uint32_t rr_gb_link_run(GBContext* primary, uint32_t max_cycles) {
    const uint32_t start = primary->cycles;
    const bool bounded = max_cycles > 0 && max_cycles != UINT32_MAX;
    if (!primary->frame_done && primary->frame_cycles == 0)
        for (int i = 1; i < g_rr_link_count; ++i)
            if (g_rr_link_ctx[i]->frame_done) gb_reset_frame(g_rr_link_ctx[i]);       /* a new frame of the pair */
    while (!primary->frame_done) {
        uint32_t chunk = RR_GB_LINK_CHUNK;
        if (bounded) {
            const uint32_t ran = primary->cycles - start;
            if (ran >= max_cycles) break;
            if (chunk > max_cycles - ran) chunk = max_cycles - ran;
        }
        rr_gb_run_cycles_one(primary, chunk);
        for (int i = 1; i < g_rr_link_count; ++i) rr_gb_link_catch_up(g_rr_link_ctx[i], primary->total_cycles);
    }
    if (primary->frame_done)                                    /* the pair's frame ends when every console's has */
        for (int i = 1; i < g_rr_link_count; ++i)
            for (unsigned guard = 0; !g_rr_link_ctx[i]->frame_done && guard < 70224u; ++guard)
                rr_gb_run_cycles_one(g_rr_link_ctx[i], 4);
    return primary->cycles - start;
}

#endif
