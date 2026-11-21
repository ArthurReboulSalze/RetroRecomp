/* The Amstrad CPC's I/O decoding and memory map, as data the machine and the Z80 chain read. MIT, Retro-Recomp.
 *
 * I/O: the CPC decodes a port from single address lines, so one OUT may reach several devices (a program never relies on it,
 * but a careless address does it). Gate Array: A15 = 0, A14 = 1 (7Fxxh), written only. CRTC: A14 = 0, A9-A8 the function
 * (BCxxh select, BDxxh write, BExxh status, BFxxh read). Upper ROM select: A13 = 0 (DFxxh), written. Printer: A12 = 0 (EFxxh).
 * PPI: A11 = 0, A9-A8 the port (F4xxh A, F5xxh B, F6xxh C, F7xxh control). Floppy (the 6128's, the 664's or a DDI-1): A10 = 0
 * and A7 = 0; A8 = 0 the motor (FA7Eh), A8 = 1 the controller, A0 its register (FB7Eh status, FB7Fh data).
 *
 * Memory: four 16 KiB windows. Reads: 0000h-3FFFh the lower ROM (the OS) unless the Gate Array turned it off, C000h-FFFFh the
 * upper ROM selected at DFxxh (BASIC for any number but 7, AMSDOS for 7) unless turned off, RAM elsewhere through the 6128's
 * configuration. Writes always go to RAM. The screen is read from the base 64 KiB, whatever the configuration. */
#ifndef RR_CPC_BUS_H
#define RR_CPC_BUS_H
#include <stdint.h>

#include "cpc_gate_array.h"

enum {
    CPC_IO_GATE_ARRAY = 0x001, CPC_IO_CRTC = 0x002, CPC_IO_ROM_SELECT = 0x004, CPC_IO_PRINTER = 0x008, CPC_IO_PPI = 0x010,
    CPC_IO_FDC_MOTOR = 0x020, CPC_IO_FDC = 0x040,
};

/* The devices an I/O address reaches (CPC_IO_* bits). */
static inline unsigned cpc_io_devices(uint16_t port)
{
    unsigned d = 0;
    if ((port & 0xC000) == 0x4000) d |= CPC_IO_GATE_ARRAY;
    if (!(port & 0x4000)) d |= CPC_IO_CRTC;
    if (!(port & 0x2000)) d |= CPC_IO_ROM_SELECT;
    if (!(port & 0x1000)) d |= CPC_IO_PRINTER;
    if (!(port & 0x0800)) d |= CPC_IO_PPI;
    if (!(port & 0x0400) && !(port & 0x0080)) d |= port & 0x0100 ? CPC_IO_FDC : CPC_IO_FDC_MOTOR;
    return d;
}

/* The function of the CRTC or the port of the PPI: A9-A8. */
static inline unsigned cpc_io_function(uint16_t port) { return (port >> 8) & 3; }

enum { CPC_SOURCE_RAM = 0, CPC_SOURCE_LOWER_ROM = 1, CPC_SOURCE_BASIC = 2, CPC_SOURCE_AMSDOS = 3 };

typedef struct {
    uint8_t source[4];      /* what each window reads: CPC_SOURCE_* */
    uint8_t ram[4];         /* the 16 KiB RAM bank each window writes (and reads when its source is RAM): 0-7 */
} CpcMap;

/* The map for the Gate Array's ROM enables and RAM configuration and the upper ROM number selected. */
static inline CpcMap cpc_memory_map(const CpcGateArray *g, uint8_t upper_rom)
{
    CpcMap m;
    cpc_ram_banks(g->has_ram_pal ? g->ram_config : 0, m.ram);
    m.source[0] = g->rom_config & 0x04 ? CPC_SOURCE_RAM : CPC_SOURCE_LOWER_ROM;
    m.source[1] = m.source[2] = CPC_SOURCE_RAM;
    m.source[3] = g->rom_config & 0x08 ? CPC_SOURCE_RAM : upper_rom == 7 ? CPC_SOURCE_AMSDOS : CPC_SOURCE_BASIC;
    return m;
}
#endif
