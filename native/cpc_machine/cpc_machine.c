/* The Amstrad CPC 6128 board: see cpc_machine.h. MIT, Retro-Recomp. */
#include "cpc_machine.h"

#include <string.h>

static void remap(CpcMachine *m)
{
    CpcMap map = cpc_memory_map(&m->ga, m->upper_rom);
    if (memcmp(&map, &m->map, sizeof map)) {
        m->map = map;
        ++m->generation;
    }
}

void cpc_reset(CpcMachine *m, uint8_t crtc_type)
{
    memset(m->ram, 0, sizeof m->ram);
    cpc_crtc_reset(&m->crtc, crtc_type);
    m->ga.has_ram_pal = 1;                                           /* the 6128 */
    cpc_ga_reset(&m->ga);
    cpc_ppi_reset(&m->ppi);
    m->fdc.unit_mask = 1;                                            /* US1 is not decoded: drive A and drive B */
    m->fdc.tc_wired = 0;                                             /* nor is the terminal count */
    upd765_reset(&m->fdc);
    for (int d = 0; d < CPC_DRIVES; ++d)
        m->fdc.drive[d].pcn = 0;
    m->upper_rom = 0;
    m->motor = 0;
    m->phase = 0;
    m->frame_ready = 0;
    m->cycles = 0;
    m->frames = 0;
    memset(&m->map, 0xFF, sizeof m->map);                            /* forces the first map, and a new generation */
    remap(m);
}

int cpc_insert_disk(CpcMachine *m, int drive, uint8_t *bytes, uint32_t size, int write_protected)
{
    if (drive < 0 || drive >= CPC_DRIVES)
        return DSK_ERR_GEOMETRY;
    if (!bytes) {
        memset(&m->disk[drive], 0, sizeof m->disk[drive]);
        upd765_insert(&m->fdc, drive, NULL, 0);
        return DSK_OK;
    }
    int why = dsk_parse(&m->disk[drive], bytes, size);
    upd765_insert(&m->fdc, drive, why == DSK_OK ? &m->disk[drive] : NULL, write_protected);
    return why;
}

static const uint8_t *rom_of(const CpcMachine *m, uint8_t source)
{
    switch (source) {
    case CPC_SOURCE_LOWER_ROM: return m->os;
    case CPC_SOURCE_BASIC: return m->basic;
    case CPC_SOURCE_AMSDOS: return m->amsdos;
    default: return NULL;
    }
}

uint8_t cpc_read(const CpcMachine *m, uint16_t address)
{
    unsigned window = address >> 14;
    uint8_t source = m->map.source[window];
    if (source != CPC_SOURCE_RAM) {
        const uint8_t *rom = rom_of(m, source);
        return rom ? rom[address & 0x3FFF] : 0xFF;
    }
    return m->ram[((uint32_t)m->map.ram[window] << 14) | (address & 0x3FFF)];
}

void cpc_write(CpcMachine *m, uint16_t address, uint8_t value)
{
    unsigned window = address >> 14;
    m->ram[((uint32_t)m->map.ram[window] << 14) | (address & 0x3FFF)] = value;   /* a write under a ROM goes to its RAM */
}

uint8_t cpc_in(CpcMachine *m, uint16_t port)
{
    unsigned devices = cpc_io_devices(port);
    uint8_t value = 0xFF;                                            /* nothing drives the bus */
    if (devices & CPC_IO_CRTC) {
        unsigned function = cpc_io_function(port);
        if (function == 3) value &= cpc_crtc_read(&m->crtc);
        else if (function == 2) value &= cpc_crtc_status(&m->crtc);
    }
    if (devices & CPC_IO_PPI)
        value &= cpc_ppi_read(&m->ppi, cpc_io_function(port), cpc_crtc_out(&m->crtc).vsync, &m->psg);
    if (devices & CPC_IO_FDC)
        value &= port & 1 ? upd765_read_data(&m->fdc) : upd765_status(&m->fdc);
    return value;
}

void cpc_out(CpcMachine *m, uint16_t port, uint8_t value)
{
    unsigned devices = cpc_io_devices(port);
    if (devices & CPC_IO_GATE_ARRAY) {
        cpc_ga_write(&m->ga, value);
        remap(m);
    }
    if (devices & CPC_IO_CRTC) {
        unsigned function = cpc_io_function(port);
        if (function == 0) cpc_crtc_select(&m->crtc, value);
        else if (function == 1) cpc_crtc_write(&m->crtc, value);
    }
    if (devices & CPC_IO_ROM_SELECT) {
        m->upper_rom = value;
        remap(m);
    }
    if (devices & CPC_IO_PPI)
        cpc_ppi_write(&m->ppi, cpc_io_function(port), value, &m->psg);
    if (devices & CPC_IO_FDC_MOTOR)
        m->motor = value & 1;
    if ((devices & CPC_IO_FDC) && (port & 1))
        upd765_write_data(&m->fdc, value);                           /* the status register cannot be written */
}

void cpc_advance(CpcMachine *m, uint64_t tstates)
{
    m->cycles += tstates;
    uint64_t total = (uint64_t)m->phase + tstates;
    m->phase = (uint8_t)(total & 3);
    for (uint64_t us = total >> 2; us; --us) {
        cpc_crtc_step(&m->crtc);
        unsigned events = cpc_ga_tick(&m->ga, cpc_crtc_out(&m->crtc), m->ram, m->picture);
        if (events & CPC_GA_FRAME) {
            m->frame_ready = 1;
            ++m->frames;
        }
    }
}

uint64_t cpc_next_event(const CpcMachine *m)
{
    return m->cycles + (4u - m->phase);
}

int cpc_irq(const CpcMachine *m)
{
    return m->ga.interrupt;
}

void cpc_acknowledge(CpcMachine *m)
{
    cpc_ga_acknowledge(&m->ga);
}
