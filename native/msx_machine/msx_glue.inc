/* The MSX glue of the shared banked Z80 chain, included by the headless check (msx_native_main.c) and by the game
 * (msx_player.c). MIT, Retro-Recomp.
 *
 * It holds what the generated bodies and the step loop (native/banked_runtime.inc rendered for the MSX by
 * retrorecomp.z80_chain: a region map, one wait state per M1 cycle, /INT read at the end of each instruction) need on this
 * machine: the bus ABI on the MSX machine of msx_machine.c, the region map and the loop itself. What every machine on the
 * chain shares (the names of the bodies, the counted fallback's wrappers and accounting, the learning of code run from RAM)
 * is native/z80_chain_glue.inc, included below, whose header is the contract. The includer defines SMSRECOMP_BANKED_AOT
 * before including this file, supplies msx_main_service() and sets the machine's line hook.
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
static uint8_t slot0[0x18000];             /* the BIOS source: main, logo page; on the MSX2 the sub-ROM at C000h; a disk ROM at 10000h;
                                             * the MSX2+'s MSX-MUSIC BIOS at 14000h */
#ifndef RR_MSX_KANJI
#define RR_MSX_KANJI 0      /* the player's own kanji font: 1 when the game carries it (resource 107) */
#endif
#ifndef RR_MSX_MUSIC
#define RR_MSX_MUSIC 0      /* MSX-MUSIC: 1 in an MSX2+ build (msx_build stages msx_music.c and emu2413 then) */
#endif
#if RR_MSX_MUSIC
#include "msx_music.h"
#endif
static uint8_t cart[0x200000];
static MsxV9938 v9938;                      /* the MSX2's VDP (msx_setup_msx2) */
static uint8_t mapper_ram[4u << 20];        /* the MSX2's mapper RAM: up to 256 segments of 16 KB */

/* The including main says what happens at each instruction boundary (stop at a frame limit, present a frame...). */
static void msx_main_service(void);

static void machine_to(uint64_t cycle);          /* the shared glue (z80_chain_glue.inc) catches the hardware up through it */
#include "z80_chain_glue.inc"

/* Bring the machine to `cycle`: its lines, frame flag and sound up to then. */
static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        msx_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = msx_next_event(&machine);
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
            /* The disk ROM's last region holds the controller's registers at 7FF8h-7FFBh: the ROM still shows below them. */
            int disk = d->kind == MSX_DEV_ROM && d->mapper == MSX_MAPPER_DISK && i == 3;
            int rom = d->kind == MSX_DEV_ROM && (r->read || scc || disk) && d->block[i] >= 0 && d->source != MSX_SOURCE_NONE;
            region_map[i].source = rom ? d->source : 0;
            region_map[i].bank = rom ? (uint8_t)(d->bank_base + d->block[i]) : 0;
            region_map[i].ram = (uint8_t)!rom;
            region_map[i].guard_from = rom && scc ? 0x1800 : rom && disk ? 0x1FF8 : 0;
            region_map[i].guard_to = rom && (scc || disk) ? 0x2000 : 0;
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
