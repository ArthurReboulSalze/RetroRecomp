/* The glue every machine on the banked Z80 chain shares (the MSX family, the SG-1000, the ColecoVision and the machines after them),
 * included by the machine's own glue. MIT, Retro-Recomp. Game role, group `shares:z80_chain_glue` (retrorecomp/stamp_inputs.py); the Python side
 * of the same split is retrorecomp/z80_chain_build.py.
 *
 * It holds what the generated bodies and the step loop (native/banked_runtime.inc rendered for the machine by retrorecomp/z80_chain.py)
 * need whatever the machine is: the names the bodies link to, the register of the instruction's start time, the wrappers that put the
 * reference interpreter (the counted fallback) on the machine's bus, the accounting of the fallback and the learning of code run from RAM
 * (`--learn FILE`), the dispatch miss, and the catching up of the hardware at the end of an instruction.
 *
 * THE INCLUDER'S CONTRACT (the machine's glue, e.g. native/msx_machine/msx_glue.inc).
 *
 * Before the include, in this order:
 *   - the headers `game_banked.h` and `runtime_reference.h` (the machine's own struct and the rest of its headers too);
 *   - `#define SMSRECOMP_BANKED_AOT` (the build does), the machine's state variables;
 *   - the prototype `static void machine_to(uint64_t cycle);`.
 * After the include (the order does not matter among these, they only have to exist before the loop):
 *   - `static void machine_to(uint64_t cycle)`: bring the machine's hardware (its video lines, its frame flag, its sound) up to `cycle` and
 *     set `g_next_line_cyc` to the cycle of its next event. `advance_vdp` (here) calls it once the instruction is done; the bus calls it at the
 *     instruction's start time (`step_start`) before an I/O access or a write a device must see in time;
 *   - the Z80 bus: `uint8_t sms_read8(uint16_t)`, `void sms_write8(uint16_t, uint8_t)`, `uint8_t sms_io_in(uint8_t)`,
 *     `void sms_io_out(uint8_t, uint8_t)`. The reference interpreter goes through the same four (the `hyb_*` wrappers below);
 *   - `static int vdp_irq_asserted(void)`: the level of /INT (the name the rendered loop uses, whatever chip raises it);
 *   - `static const BankedRegion *smsrecomp_region_map(void)` and `smsrecomp_region_generation` (a machine keyed by a region map);
 *   - the rendered loop itself, `#include "<machine>_banked_loop.inc"` (written by `z80_chain_build.generate_bodies`);
 *   - `static void smsrecomp_state_service(void)`: called by the loop once an instruction and the interrupt it may accept are complete.
 * Optional hooks, only for the machines that ask for them:
 *   - `static int banked_nmi_edge(void)`, when `Z80Machine.nmi` is set: nonzero once per falling edge of /NMI seen since the last call
 *     (the machine makes the edge, the chain's `banked_accept_nmi` takes it). Called after `machine_to` has caught the hardware up;
 *   - RESERVED, not implemented here: a hook for the cost of an instruction (a table of cycles per opcode, the contention of a machine
 *     whose video steals bus cycles). Its name, `machine_instruction_cost`, is kept free; its shape is the first machine that needs it.
 *
 * Timing contract, the same as the machine's reference runner so the runs can be compared state for state: an instruction's I/O and its
 * writes to a cartridge device happen at the instruction's start time (a chain of redundant DD/FD prefixes is one instruction); the machine's
 * lines are run at instruction boundaries; /INT is read once the machine has caught up. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

/* Bring the machine's hardware up to the end of an instruction (the loop never calls this inside a prefix chain), counting the guest cycles. */
static void advance_vdp(uint64_t cycle)
{
    smsrecomp_total_cycles += cycle > smsrecomp_measured_guest_cycles ? cycle - smsrecomp_measured_guest_cycles : 0;
    smsrecomp_measured_guest_cycles = cycle;
    machine_to(cycle);
}


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

