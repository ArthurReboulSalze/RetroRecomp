/* The ZX Spectrum's glue on the shared banked Z80 chain, included by the native check (zxs_native_main.c) and by the game.
 * MIT, Retro-Recomp.
 *
 * What the generated bodies and the step loop (native/banked_runtime.inc rendered for the Spectrum by retrorecomp/z80_chain.py:
 * a region map of four 16 KiB regions, the ROM as its one translated source, /INT read at the end of each instruction, 16-bit
 * ports) need on this machine: the machine of zxs_machine.c, its bus, the region map and the loop. What every machine on the chain
 * shares is native/z80_chain_glue.inc, whose header is the contract. The includer defines SMSRECOMP_BANKED_AOT and supplies
 * zxs_main_service().
 *
 * Timing contract, the same as zxs_reference_main.c so the runs can be compared state for state: an instruction's I/O happens at
 * its start time (the machine caught up to it first); the machine's lines run at instruction boundaries; /INT is read once the
 * machine has caught up with the instruction. Memory is plain RAM and ROM (the 128K pages through a port), so a write needs no
 * catching up. The ULA's contention is not modelled. */
#include "zxs_machine.h"
#include "game_banked.h"
#include "runtime_reference.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static ZxsMachine machine;
static uint8_t rom[0x8000];                 /* the ROM source: 16 KiB (48K) or 32 KiB (128K, the editor ROM then the BASIC ROM) */

static void zxs_main_service(void);
static void machine_to(uint64_t cycle);     /* the shared glue (z80_chain_glue.inc) catches the hardware up through it */
#include "z80_chain_glue.inc"

static void machine_to(uint64_t cycle)
{
    if (cycle > machine.cycles)
        zxs_advance(&machine, cycle - machine.cycles);
    g_next_line_cyc = zxs_next_event(&machine);
}

static int vdp_irq_asserted(void) { return zxs_irq(&machine); }

uint8_t sms_read8(uint16_t address) { return zxs_read(&machine, address); }
void sms_write8(uint16_t address, uint8_t value) { zxs_write(&machine, address, value); }
uint8_t sms_io_in16(uint16_t port) { machine_to(step_start); return zxs_in(&machine, port); }
void sms_io_out16(uint16_t port, uint8_t value) { machine_to(step_start); zxs_out(&machine, port, value); }

/* The region map the step loop reads: the ROM (source 0, the bank the 128K pages in) at 0000h, RAM above. */
static BankedRegion region_map[4];
static uint32_t smsrecomp_region_generation;
static const BankedRegion *smsrecomp_region_map(void)
{
    uint32_t generation = (uint32_t)zxs_rom_bank(&machine) + 1;
    if (generation != smsrecomp_region_generation) {
        memset(region_map, 0, sizeof region_map);
        region_map[0].source = 0;
        region_map[0].bank = (uint8_t)zxs_rom_bank(&machine);
        for (int i = 1; i < 4; ++i)
            region_map[i].ram = 1;
        smsrecomp_region_generation = generation;
    }
    return region_map;
}

#include "zxs_banked_loop.inc"

/* Called by the loop once an instruction and the interrupt it may accept are complete. */
static void smsrecomp_state_service(void)
{
    zxs_main_service();
}

#include "zxs_cpu_start.inc"
