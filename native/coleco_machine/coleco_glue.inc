/* The ColecoVision glue of the shared banked Z80 chain, included by the headless check (coleco_native_main.c) and by the game
 * (coleco_player.c). MIT, Retro-Recomp.
 *
 * What every machine on the chain shares is native/z80_chain_glue.inc, included below; its header is the contract. This file is what
 * the ColecoVision owes it: the machine of coleco_machine.c, the Z80 bus on it, the region map (the BIOS in the first 8 KiB region, nothing in
 * the next two, the console's RAM in the fourth, the cartridge in the last four, mirrored by bank), the VDP's interrupt as /NMI, and the
 * loop's include (the step loop rendered for the machine by retrorecomp/z80_chain.py: eight 8 KiB regions, no wait state, /NMI read at the end
 * of each instruction). The includer defines SMSRECOMP_BANKED_AOT before including it and supplies cv_main_service(). */
#include "coleco_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static CvMachine machine;
static uint8_t bios[CV_BIOS_SIZE];          /* the player's BIOS: the second source of the chain (the generator translates it beside the cartridge) */
static uint8_t cart[0x8000];                /* the cartridge, padded with FFh to whole 8 KiB regions (the chain pads its source the same) */

/* The including main says what happens at each instruction boundary (stop at a frame limit, present a frame...). */
static void cv_main_service(void);

static void machine_to(uint64_t cycle);          /* the shared glue (z80_chain_glue.inc) catches the hardware up through it */
#include "z80_chain_glue.inc"

/* Bring the machine to `cycle`: its lines, frame flag and sound up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        cv_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = cv_next_event(&machine);
}

static int vdp_irq_asserted(void) { return cv_irq(&machine); }      /* /INT is not wired: the VDP's interrupt is /NMI */
static int banked_nmi_edge(void) { return cv_nmi_edge(&machine); }

uint8_t sms_read8(uint16_t address) { return cv_read(&machine, address); }
void sms_write8(uint16_t address, uint8_t value) { cv_write(&machine, address, value); }
uint8_t sms_io_in(uint8_t port) { machine_to(step_start); return cv_in(&machine, port); }
void sms_io_out(uint8_t port, uint8_t value) { machine_to(step_start); cv_out(&machine, port, value); }

/* The region map the step loop reads, which never changes: region 0 the BIOS (source 1), regions 1 and 2 the expansion port (RAM in the
 * chain's sense: nothing is translated there, the machine's bus answers FFh), region 3 the console's RAM, regions 4 to 7 the cartridge
 * (source 0), bank (region - 4) mod the cartridge's 8 KiB banks. */
static BankedRegion region_map[CV_REGIONS];
static uint32_t smsrecomp_region_generation, map_built = UINT32_MAX;
static const BankedRegion *smsrecomp_region_map(void)
{
    if (map_built != machine.generation) {
        unsigned banks = machine.rom_size >> CV_REGION_BITS;
        for (unsigned i = 0; i < CV_REGIONS; ++i) {
            int rom = i >= 4 && banks;
            int firmware = i == 0;
            region_map[i].source = (uint8_t)(firmware ? 1 : 0);
            region_map[i].bank = rom ? (uint8_t)((i - 4) % banks) : 0;
            region_map[i].ram = (uint8_t)!(rom || firmware);
            region_map[i].guard_from = 0;
            region_map[i].guard_to = 0;
        }
        map_built = machine.generation;
        smsrecomp_region_generation = machine.generation;
    }
    return region_map;
}

#include "coleco_banked_loop.inc"

/* Called by the loop once an instruction and the interrupt it may accept are complete. */
static void smsrecomp_state_service(void)
{
    cv_main_service();
}
