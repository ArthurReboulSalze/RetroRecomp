/* The Amstrad CPC glue of the shared banked Z80 chain, included by the game (and the headless check to come). MIT, Retro-Recomp.
 *
 * What the generated bodies and the step loop (native/banked_runtime.inc rendered for the CPC by retrorecomp.z80_chain: a region
 * map of four 16 KiB regions, no M1 wait state, the CPC's instruction costs in whole microseconds, /INT read at the end of each
 * instruction, the full 16-bit port) need on this machine: the bus on the board of cpc_machine.c, the region map, the
 * acknowledge of the Gate Array's interrupt and the loop itself. What every machine on the chain shares is
 * native/z80_chain_glue.inc, whose header is the contract. The includer defines SMSRECOMP_BANKED_AOT before including this
 * file, supplies cpc_main_service() and fills `machine` (its ROMs, its disks, its picture) before the loop starts.
 *
 * The port: the CPC decodes its devices from the high byte of the address (cpc_bus.h), so the chain gives the whole address
 * (Z80Machine port_bits 16: (A << 8) | n for IN A,(n) and OUT (n),A, BC for the (C) and block forms, B after its decrement for
 * OUTI and its kind): sms_io_in16 / sms_io_out16, declared by game_banked.h (SMSRECOMP_PORT16).
 *
 * Timing: an instruction's I/O happens at the instruction's start time (`step_start`, the chain's contract); so does a write to
 * the 16 KiB page the CRTC shows, so that the picture is drawn up to that time before the byte changes. The Gate Array's
 * interrupt is a level the Z80 drops by accepting it: once the loop has accepted one (its count `g_irq_taken` moved), the Gate
 * Array is acknowledged before the next instruction. */
#include "cpc_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static CpcMachine machine;

/* The including main says what happens at each instruction boundary (stop at a frame limit, present a frame...). */
static void cpc_main_service(void);

static void machine_to(uint64_t cycle);          /* the shared glue (z80_chain_glue.inc) catches the hardware up through it */
#include "z80_chain_glue.inc"

/* Bring the machine to `cycle`: its video, interrupt and frame flag up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        cpc_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = cpc_next_event(&machine);
}

static int vdp_irq_asserted(void) { return cpc_irq(&machine); }

uint8_t sms_read8(uint16_t address) { return cpc_read(&machine, address); }

void sms_write8(uint16_t address, uint8_t value)
{
    /* The screen is the base 64 KiB page R12 bits 5-4 name: draw up to the instruction's start before a byte of it changes. */
    if (machine.map.ram[address >> 14] == ((machine.crtc.reg[12] >> 4) & 3))
        machine_to(step_start);
    cpc_write(&machine, address, value);
}

uint8_t sms_io_in16(uint16_t port) { machine_to(step_start); return cpc_in(&machine, port); }
void sms_io_out16(uint16_t port, uint8_t value) { machine_to(step_start); cpc_out(&machine, port, value); }

/* The region map the step loop reads, in the order of the machine's sources (retrorecomp/systems/amstrad_cpc.py): source 0 the
 * system ROM, bank 0 the OS, bank 1 BASIC; source 1 AMSDOS. RAM wherever the Gate Array turned a ROM off. */
static BankedRegion region_map[4];
static uint32_t smsrecomp_region_generation, map_built = UINT32_MAX;
static const BankedRegion *smsrecomp_region_map(void)
{
    if (map_built != machine.generation) {
        for (int i = 0; i < 4; ++i) {
            uint8_t source = machine.map.source[i];
            int rom = (source == CPC_SOURCE_LOWER_ROM && machine.os) || (source == CPC_SOURCE_BASIC && machine.basic)
                      || (source == CPC_SOURCE_AMSDOS && machine.amsdos);
            region_map[i].source = rom && source == CPC_SOURCE_AMSDOS ? 1 : 0;
            region_map[i].bank = rom && source == CPC_SOURCE_BASIC ? 1 : 0;
            region_map[i].ram = (uint8_t)!rom;
            region_map[i].guard_from = 0;
            region_map[i].guard_to = 0;
        }
        map_built = machine.generation;
        smsrecomp_region_generation = machine.generation;
    }
    return region_map;
}

#include "cpc_banked_loop.inc"

/* Called by the loop once an instruction and the interrupt it may accept are complete. */
static void smsrecomp_state_service(void)
{
    static uint64_t acknowledged;
    if (g_irq_taken != acknowledged) {
        acknowledged = g_irq_taken;
        cpc_acknowledge(&machine);
    }
    cpc_main_service();
}
