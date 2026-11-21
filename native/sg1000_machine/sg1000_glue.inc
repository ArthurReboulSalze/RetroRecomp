/* The SG-1000 glue of the shared banked Z80 chain, included by the headless check (sg1000_native_main.c) and by the game
 * (sg1000_player.c). MIT, Retro-Recomp.
 *
 * What every machine on the chain shares is native/z80_chain_glue.inc, included below; its header is the contract. This file is what
 * the SG-1000 owes it: the machine of sg1000_machine.c, the Z80 bus on it, the region map (the cartridge in the first six 8 KiB
 * regions, mirrored by bank, the 1 KiB of RAM in the last two), the Pause button as /NMI, and the loop's include (the step loop
 * rendered for the machine by retrorecomp/z80_chain.py: eight 8 KiB regions, no wait state, /INT and /NMI read at the end of each
 * instruction). The includer defines SMSRECOMP_BANKED_AOT before including it and supplies sg_main_service(). */
#include "sg1000_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static SgMachine machine;
static uint8_t cart[0xC000];                /* the cartridge, padded with FFh to whole 8 KiB regions (the chain pads its source the same) */

/* The including main says what happens at each instruction boundary (stop at a frame limit, present a frame...). */
static void sg_main_service(void);

static void machine_to(uint64_t cycle);          /* the shared glue (z80_chain_glue.inc) catches the hardware up through it */
#include "z80_chain_glue.inc"

/* Bring the machine to `cycle`: its lines, frame flag and sound up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        sg_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = sg_next_event(&machine);
}

static int vdp_irq_asserted(void) { return sg_irq(&machine); }
static int banked_nmi_edge(void) { return sg_nmi_edge(&machine); }

uint8_t sms_read8(uint16_t address) { return sg_read(&machine, address); }
void sms_write8(uint16_t address, uint8_t value) { sg_write(&machine, address, value); }
uint8_t sms_io_in(uint8_t port) { machine_to(step_start); return sg_in(&machine, port); }
void sms_io_out(uint8_t port, uint8_t value) { machine_to(step_start); sg_out(&machine, port, value); }

/* The region map the step loop reads: which bank (8 KiB units) of the cartridge each region shows, or RAM. The layout never changes. */
static BankedRegion region_map[SG_REGIONS];
static uint32_t smsrecomp_region_generation, map_built = UINT32_MAX;
static const BankedRegion *smsrecomp_region_map(void)
{
    if (map_built != machine.generation) {
        unsigned banks = machine.rom_size >> SG_REGION_BITS;
        for (unsigned i = 0; i < SG_REGIONS; ++i) {
            int rom = i < 6 && banks;
            region_map[i].source = 0;
            region_map[i].bank = rom ? (uint8_t)(i % banks) : 0;
            region_map[i].ram = (uint8_t)!rom;
            region_map[i].guard_from = 0;
            region_map[i].guard_to = 0;
        }
        map_built = machine.generation;
        smsrecomp_region_generation = machine.generation;
    }
    return region_map;
}

#include "sg1000_banked_loop.inc"

/* Called by the loop once an instruction and the interrupt it may accept are complete. */
static void smsrecomp_state_service(void)
{
    sg_main_service();
}
