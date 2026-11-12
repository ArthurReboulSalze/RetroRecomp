/* The MSX glue of the shared banked Z80 chain, included by the headless check (msx_native_main.c) and by the game
 * (msx_player.c). MIT, Retro-Recomp.
 *
 * It holds what the generated bodies and the step loop (native/banked_runtime.inc rendered for the MSX by
 * retrorecomp.z80_chain: a region map, one wait state per M1 cycle, /INT read at the end of each instruction) need: the bus
 * ABI on the MSX machine of msx_machine.c, the region map, the counted fallback on the corrected reference interpreter
 * (its M1 count gives the wait states), the learning of code run from RAM, and the loop itself. The includer defines
 * SMSRECOMP_BANKED_AOT before including it, supplies msx_main_service() and sets the machine's line hook.
 *
 * Timing contract, the same as msx_reference_main.c so the runs can be compared state for state: an instruction's I/O and
 * its writes to a cartridge device happen at the instruction's start time (a chain of redundant DD/FD prefixes is one
 * instruction); the machine's lines are run at instruction boundaries; /INT is read once the machine has caught up. */
#include "msx_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static MsxMachine machine;
static uint8_t ram[65536];
static uint8_t slot0[0x10000];             /* the BIOS source: main, logo page; on the MSX2 the sub-ROM at C000h */
static uint8_t cart[0x200000];
static MsxV9938 v9938;                      /* the MSX2's VDP (msx_setup_msx2) */
static uint8_t mapper_ram[4u << 20];        /* the MSX2's mapper RAM: up to 256 segments of 16 KB */

/* ---- the names the shared step loop and the generated bodies use ---- */
Z80State g_z80;
uint64_t g_sync_deadline, g_frame_ic;
int g_diff_freeze; uint64_t g_diff_icount;
void sms_diff_abort(void) {}
void sms_sync(void) {}
void sms_halt(void) {}
int sms_slot_bank(uint16_t addr) { (void)addr; return -1; }
static z80 g_hz;
static bool g_hz_init;
static uint64_t g_hybrid_calls, g_hybrid_cyc, g_irq_taken, g_next_line_cyc;
static uint64_t smsrecomp_total_cycles, smsrecomp_measured_guest_cycles;
static int banked_last_interpreted, smsrecomp_interp_depth, smsrecomp_stop_pending;
static uint64_t step_start;                 /* g_z80.cyc when the current instruction began */
uint16_t g_dbg_pc, g_enter_ring[SMS_ENTER_RING_SIZE];
uint32_t g_enter_pos;
int g_diff_active;
void sms_diff_enter(uint16_t addr) { (void)addr; }
/* The step loop calls this at the start of every step (Z80Machine.step_begin). An instruction's I/O happens at its
 * start; a chain of redundant DD/FD prefixes is one instruction for the reference (it discards them inside one step),
 * so inside a chain the start stays the chain's. */
static inline void smsrecomp_step_begin(int prefix_pending) { if (!prefix_pending) step_start = g_z80.cyc; }

extern unsigned long z80_m1_fetches;        /* the reference CPU's M1 count (cpu.prepare_reference, m1_counter) */

/* The including main says what happens at each instruction boundary (stop at a frame limit, present a frame...). */
static void msx_main_service(void);

/* Bring the machine to `cycle`: its lines, frame flag and sound up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        msx_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = machine.next_line;
}

/* The machine catches up at the end of an instruction (the loop never calls this inside a prefix chain). */
static void advance_vdp(uint64_t cycle)
{
    smsrecomp_total_cycles += cycle > smsrecomp_measured_guest_cycles ? cycle - smsrecomp_measured_guest_cycles : 0;
    smsrecomp_measured_guest_cycles = cycle;
    machine_to(cycle);
}

static int vdp_irq_asserted(void) { return msx_irq(&machine); }

uint8_t sms_read8(uint16_t address) { return msx_read(&machine, address); }

void sms_write8(uint16_t address, uint8_t value)
{
    if (!machine.region[address >> 13].write)
        machine_to(step_start);             /* a device (mapper, SCC) sees the write at the instruction's start */
    msx_write(&machine, address, value);
}

uint8_t sms_io_in(uint8_t port) { machine_to(step_start); return msx_in(&machine, port); }
void sms_io_out(uint8_t port, uint8_t value) { machine_to(step_start); msx_out(&machine, port, value); }

/* The reference CPU of the fallback, on the same bus. */
static uint8_t hyb_read(void *user, uint16_t address) { (void)user; return sms_read8(address); }
static void hyb_write(void *user, uint16_t address, uint8_t value) { (void)user; sms_write8(address, value); }
static uint8_t hyb_in(z80 *z, uint8_t port) { (void)z; return sms_io_in(port); }
static void hyb_out(z80 *z, uint8_t port, uint8_t value) { (void)z; sms_io_out(port, value); }

/* Fallback accounting: where the interpreter ran (first addresses, for the report). */
static uint16_t fallback_at[16];
static uint64_t fallback_count[16];
static void smsrecomp_feedback_at(uint16_t address)
{
    for (int i = 0; i < 16; ++i) {
        if (fallback_count[i] && fallback_at[i] == address) { ++fallback_count[i]; return; }
        if (!fallback_count[i]) { fallback_at[i] = address; fallback_count[i] = 1; return; }
    }
}
/* Learning (--learn FILE): the four bytes at each address the interpreter ran, written out at the end; the next
 * generation translates them as byte-guarded native bodies (native.patterns beside game.toml, read by the emitter). */
static const char *learn_out;
static uint32_t learned[4096];
static int learned_count;
static int smsrecomp_learning_enabled(void) { return learn_out != NULL; }
static void smsrecomp_observe_code(const uint8_t *bytes)
{
    uint32_t word = (uint32_t)bytes[0] << 24 | (uint32_t)bytes[1] << 16 | (uint32_t)bytes[2] << 8 | bytes[3];
    for (int i = 0; i < learned_count; ++i)
        if (learned[i] == word) return;
    if (learned_count < 4096) learned[learned_count++] = word;
}
static void smsrecomp_state_service(void);
static void smsrecomp_banked_fallback(uint16_t addr);
void sms_dispatch_miss(uint16_t addr) { smsrecomp_banked_fallback(addr); }
void call_by_address(uint16_t addr) { smsrecomp_banked_fallback(addr); }

/* The region map the step loop reads: which source and bank (8 KB units) each region shows, or RAM (anything the
 * translated sources do not hold: RAM, an empty socket, the SCC window). */
static BankedRegion region_map[8];
static uint32_t smsrecomp_region_generation, map_built = UINT32_MAX;
static const BankedRegion *smsrecomp_region_map(void)
{
    if (map_built != machine.generation) {
        for (int i = 0; i < 8; ++i) {
            const MsxRegion *r = &machine.region[i];
            const MsxDevice *d = &machine.slot[r->primary][r->secondary];
            /* The Konami SCC answers at 9800h-9FFFh in front of the ROM, which still shows at 8000h-97FFh. */
            int scc = d->kind == MSX_DEV_ROM && d->mapper == MSX_MAPPER_KONAMI_SCC && d->scc_on && i == 4;
            int rom = d->kind == MSX_DEV_ROM && (r->read || scc) && d->block[i] >= 0 && d->source != MSX_SOURCE_NONE;
            region_map[i].source = rom ? d->source : 0;
            region_map[i].bank = rom ? (uint8_t)(d->bank_base + d->block[i]) : 0;
            region_map[i].ram = (uint8_t)!rom;
            region_map[i].guard_from = rom && scc ? 0x1800 : 0;
            region_map[i].guard_to = rom && scc ? 0x2000 : 0;
        }
        map_built = machine.generation;
        smsrecomp_region_generation = machine.generation;
    }
    return region_map;
}

#include "msx_banked_loop.inc"

/* Called by the loop once an instruction and the interrupt it may accept are complete. */
static void smsrecomp_state_service(void)
{
    msx_main_service();
}
