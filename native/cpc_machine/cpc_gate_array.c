/* The CPC's Gate Array and the 6128's RAM PAL: see cpc_gate_array.h. MIT, Retro-Recomp. */
#include "cpc_gate_array.h"

#include <string.h>

enum { WINDOW_X = 14, WINDOW_Y = 36, FREE_LINE = 64, FREE_FRAME = 320 };

/* The 32 hardware colours, red, green and blue each 0, 1 (50 %) or 2 (100 %): the CPC's documented table (27 distinct). */
static const uint8_t LEVELS[32][3] = {
    {1, 1, 1}, {1, 1, 1}, {0, 2, 1}, {2, 2, 1}, {0, 0, 1}, {2, 0, 1}, {0, 1, 1}, {2, 1, 1},
    {2, 0, 1}, {2, 2, 1}, {2, 2, 0}, {2, 2, 2}, {2, 0, 0}, {2, 0, 2}, {2, 1, 0}, {2, 1, 2},
    {0, 0, 1}, {0, 2, 1}, {0, 2, 0}, {0, 2, 2}, {0, 0, 0}, {0, 0, 2}, {0, 1, 0}, {0, 1, 2},
    {1, 0, 1}, {1, 2, 1}, {1, 2, 0}, {1, 2, 2}, {1, 0, 0}, {1, 0, 2}, {1, 1, 0}, {1, 1, 2},
};

uint32_t cpc_colour(uint8_t hardware)
{
    static const uint8_t gun[3] = { 0x00, 0x80, 0xFF };
    const uint8_t *l = LEVELS[hardware & 31];
    return (uint32_t)gun[l[0]] << 16 | (uint32_t)gun[l[1]] << 8 | gun[l[2]];
}

void cpc_ram_banks(uint8_t ram_config, uint8_t banks[4])
{
    static const uint8_t CONFIG[8][4] = {
        {0, 1, 2, 3}, {0, 1, 2, 7}, {4, 5, 6, 7}, {0, 3, 2, 7}, {0, 4, 2, 3}, {0, 5, 2, 3}, {0, 6, 2, 3}, {0, 7, 2, 3},
    };
    memcpy(banks, CONFIG[ram_config & 7], 4);
}

unsigned cpc_byte_pens(uint8_t mode, uint8_t b, uint8_t pens[8])
{
    switch (mode & 3) {
    case 2:
        for (unsigned i = 0; i < 8; ++i)
            pens[i] = (uint8_t)((b >> (7 - i)) & 1);
        return 8;
    case 1:
        for (unsigned i = 0; i < 4; ++i)
            pens[i] = (uint8_t)(((b >> (7 - i)) & 1) | (((b >> (3 - i)) & 1) << 1));
        return 4;
    default: {                                                       /* mode 0; mode 3 keeps its two low bits */
        for (unsigned i = 0; i < 2; ++i) {
            uint8_t p = (uint8_t)(((b >> (7 - i)) & 1) | (((b >> (3 - i)) & 1) << 1)
                                  | (((b >> (5 - i)) & 1) << 2) | (((b >> (1 - i)) & 1) << 3));
            pens[i] = (mode & 3) == 3 ? (uint8_t)(p & 3) : p;
        }
        return 2;
    }
    }
}

/* What draw() reads for each pixel, built once from cpc_byte_pens and cpc_colour (the same values, looked up): the pen of each
 * of the eight pixels a screen byte gives in each mode (a mode 1 pen twice, a mode 0 pen four times), and each hardware
 * colour as 0x00RRGGBB. */
static uint8_t PIXEL_PEN[4][256][8];
static uint32_t COLOUR[32];
static int tables_built;

static void build_tables(void)
{
    for (unsigned mode = 0; mode < 4; ++mode)
        for (unsigned b = 0; b < 256; ++b) {
            uint8_t pens[8];
            unsigned count = cpc_byte_pens((uint8_t)mode, (uint8_t)b, pens), width = 8 / count;
            for (unsigned x = 0; x < 8; ++x)
                PIXEL_PEN[mode][b][x] = pens[x / width];
        }
    for (unsigned c = 0; c < 32; ++c)
        COLOUR[c] = cpc_colour((uint8_t)c);
    tables_built = 1;
}

void cpc_ga_reset(CpcGateArray *g)
{
    uint8_t pal = g->has_ram_pal;
    memset(g, 0, sizeof *g);
    g->has_ram_pal = pal;
    g->mode = g->mode_next = 1;
    for (unsigned i = 0; i < 17; ++i)
        g->ink[i] = 0x14;                                            /* black until the firmware sets its inks */
}

void cpc_ga_write(CpcGateArray *g, uint8_t value)
{
    switch (value >> 6) {
    case 0:
        g->pen = value & 0x10 ? CPC_BORDER_PEN : (uint8_t)(value & 0x0F);
        break;
    case 1:
        g->ink[g->pen] = value & 0x1F;
        break;
    case 2:
        g->mode_next = value & 3;
        g->rom_config = value & 0x0C;
        if (value & 0x10) {
            g->counter = 0;
            g->interrupt = 0;
        }
        break;
    default:
        if (g->has_ram_pal)
            g->ram_config = value & 0x3F;
        break;
    }
}

void cpc_ga_acknowledge(CpcGateArray *g)
{
    g->counter &= 0x1F;
    g->interrupt = 0;
}

static void draw(const CpcGateArray *g, CpcCrtcOut crtc, const uint8_t *ram, uint32_t *picture)
{
    if (g->beam_x < WINDOW_X || g->beam_x >= WINDOW_X + CPC_SCREEN_WIDTH / 16
        || g->beam_y < WINDOW_Y || g->beam_y >= WINDOW_Y + CPC_SCREEN_HEIGHT)
        return;
    if (!tables_built)
        build_tables();
    uint32_t *out = picture + (g->beam_y - WINDOW_Y) * CPC_SCREEN_WIDTH + (g->beam_x - WINDOW_X) * 16;
    if (crtc.hsync || crtc.vsync) {
        for (unsigned i = 0; i < 16; ++i) out[i] = 0;
        return;
    }
    if (!crtc.display) {
        uint32_t border = COLOUR[g->ink[CPC_BORDER_PEN] & 31];
        for (unsigned i = 0; i < 16; ++i) out[i] = border;
        return;
    }
    for (unsigned byte = 0; byte < 2; ++byte) {
        const uint8_t *pens = PIXEL_PEN[g->mode & 3][ram[cpc_crtc_address(crtc.ma, crtc.ra, byte)]];
        for (unsigned x = 0; x < 8; ++x)
            *out++ = COLOUR[g->ink[pens[x]] & 31];
    }
}

unsigned cpc_ga_tick(CpcGateArray *g, CpcCrtcOut crtc, const uint8_t *ram, uint32_t *picture)
{
    unsigned events = 0;
    if (crtc.hsync && !g->hsync) {                                   /* HSYNC starts: the mode is taken, the beam returns */
        g->mode = g->mode_next;
        g->beam_x = 0;
        ++g->beam_y;
    } else if (++g->beam_x >= FREE_LINE) {
        g->beam_x = 0;
        ++g->beam_y;
    }
    if (!crtc.hsync && g->hsync) {                                   /* HSYNC ends: the interrupt counter steps */
        ++g->counter;
        if (g->vsync_delay && --g->vsync_delay == 0) {
            if (g->counter >= 32) {
                g->interrupt = 1;
                events |= CPC_GA_INTERRUPT;
            }
            g->counter = 0;
        }
        if (g->counter >= 52) {
            g->counter = 0;
            g->interrupt = 1;
            events |= CPC_GA_INTERRUPT;
        }
    }
    if (crtc.vsync && !g->vsync) {                                   /* VSYNC starts: a frame is complete */
        g->vsync_delay = 2;
        g->beam_y = 0;
        events |= CPC_GA_FRAME;
    } else if (g->beam_y >= FREE_FRAME) {
        g->beam_y = 0;
        events |= CPC_GA_FRAME;
    }
    g->hsync = crtc.hsync;
    g->vsync = crtc.vsync;
    if (picture && ram)
        draw(g, crtc, ram, picture);
    return events;
}
