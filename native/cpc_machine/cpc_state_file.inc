/* Quick states and multiplayer snapshots of the Amstrad CPC game (MIT, Retro-Recomp), included by cpc_player.c after its disks.
 *
 * The body, the same in a quick state's file and in a snapshot: the CPU (native/z80_chain_state.inc: 43 bytes, every field within
 * its bounds), drive A's disk when the game has written it in this run (a flag, then the image's bytes: the board's state holds the
 * drive's heads, never the image), then the board (cpc_state.c: RAM, CRTC, Gate Array, PPI with the keyboard and joystick lines,
 * uPD765, AY, sound stream, time and frame count, the boot key sequence's clock). A quick state is that body in the shared envelope
 * (native/state_file.h: magic RRCPCST, schema 1, machine 1 the CPC 6128, the first disk's SHA-256, then the build binding
 * RR_CPC_STATE_ABI: the state's layout, the ROMs, the CRTC and the disks, written by the converter in cpc_game.h). A snapshot is
 * the body after a magic word, in memory only, with no envelope and no allocation per call. Both are checked whole on scratch
 * copies (the CPU and the board) before anything is applied, at the service point (an instruction and the interrupt it may accept
 * complete), where the loop's own locals hold nothing a state would need; the machine's consistency check (the board's time
 * within one line of the CPU's) refuses a state whose fields are each in bounds but do not fit together. */
#include "cpc_state.h"
#include "z80_chain_state.inc"
#include "state_file.h"

#define CPC_STATE_SCHEMA 1u
#define CPC_STATE_CAPACITY ((size_t)RR_STATE_ENVELOPE_HEADER + 32u + RR_Z80_CPU_STATE_BYTES + 1u + RR_CPC_DISK_MAX + CPC_RAM_BYTES + 4096u)
#define CPC_SNAP_MAGIC 0x31504E5343504352ull       /* "RCPCSNP1" read little-endian */
#define CPC_STATE_LINE_T 256u                      /* one 64 us line in T-states */

static const uint8_t cpc_state_binding[32] = RR_CPC_STATE_ABI;
static Z80State cpc_cpu_candidate;
static CpcMachine cpc_board_candidate;
static uint8_t disk_ever;                          /* drive A's disk was written in this run: its bytes travel with every state */

static void cpc_state_body(RetroStateIO *io)
{
    Z80State cpu = g_z80;
    rr_z80_cpu_state(io, &cpu);
    if (io->mode == RR_STATE_WRITE) disk_ever |= machine.fdc.drive[0].written;
    const uint8_t ever = (uint8_t)rr_state_word(io, disk_ever, 1, 1);
    if (ever) rr_state_bytes(io, disk_data[0], disk_sizes[0]);   /* copied in APPLY only */
    else if (io->mode == RR_STATE_APPLY && io->ok && disk_ever)  /* a state from before the game wrote: the disk as it came */
        memcpy(disk_data[0], disk_original[0], disk_sizes[0]);
    if (io->mode == RR_STATE_CHECK) {
        cpc_cpu_candidate = cpu;
        memcpy(&cpc_board_candidate, &machine, sizeof machine);
        cpc_machine_state(&cpc_board_candidate, io);
        return;
    }
    cpc_machine_state(&machine, io);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        disk_ever = ever;
        g_z80 = cpu;
        cpc_rebuild(&machine);
        map_built = UINT32_MAX;                    /* the loop's region map is rebuilt before the next step */
        g_next_line_cyc = cpc_next_event(&machine);
        smsrecomp_measured_guest_cycles = g_z80.cyc;
        step_start = g_z80.cyc;
        smsrecomp_interp_depth = 0;                /* the fallback CPU is refilled from g_z80 at each use */
        /* Execution, fallback and learning counters stay cumulative across a load, as on the other machines. */
    }
}

/* The board's time follows the CPU's at the service point: at most one line behind it, never ahead. */
static bool cpc_state_consistent(void)
{
    return cpc_board_candidate.cycles <= cpc_cpu_candidate.cyc && cpc_cpu_candidate.cyc - cpc_board_candidate.cycles <= CPC_STATE_LINE_T;
}

static RetroStateFile cpc_state_file(void)
{
    RetroStateFile f = { { "RRCPCST\0", CPC_STATE_SCHEMA, 1, RR_CPC_IDENTITY, cpc_state_body }, cpc_state_binding,
                         sizeof cpc_state_binding, cpc_state_consistent, CPC_STATE_CAPACITY };
    return f;
}

static int cpc_quick_save(const wchar_t *path) { RetroStateFile f = cpc_state_file(); return rr_state_file_save(&f, path); }
static int cpc_quick_load(const wchar_t *path) { RetroStateFile f = cpc_state_file(); return rr_state_file_load(&f, path); }

/* ---- the multiplayer snapshots (hostkit.h, "Multiplayer") ---- */
static void cpc_snap_body(RetroStateIO *io)
{
    if (rr_state_word(io, CPC_SNAP_MAGIC, 8, UINT64_MAX) != CPC_SNAP_MAGIC) io->ok = false;
    cpc_state_body(io);
}

static size_t cpc_snap_bound(void) { return CPC_STATE_CAPACITY; }

static size_t cpc_snap_save(void *buffer, size_t capacity)
{
    RetroStateIO io = { (uint8_t *)buffer, capacity, 0, RR_STATE_WRITE, true };
    cpc_snap_body(&io);
    return io.ok ? io.pos : 0;
}

static bool cpc_snap_load(const void *buffer, size_t size)
{
    RetroStateIO check = { (uint8_t *)buffer, size, 0, RR_STATE_CHECK, true };
    cpc_snap_body(&check);
    if (!check.ok || check.pos != size || !cpc_state_consistent()) return false;
    RetroStateIO apply = { (uint8_t *)buffer, size, 0, RR_STATE_APPLY, true };
    cpc_snap_body(&apply);
    return apply.ok;
}

/* The FNV-64 of the snapshot's bytes: the CPU, a written disk, the board with its frame count. */
static uint64_t cpc_snap_digest(void)
{
    static uint8_t scratch[CPC_STATE_CAPACITY];
    size_t n = cpc_snap_save(scratch, sizeof scratch);
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) { h ^= scratch[i]; h *= 1099511628211ull; }
    return n ? h : 0;
}
