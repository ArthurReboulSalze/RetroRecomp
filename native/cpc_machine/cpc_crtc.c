/* The CPC's 6845: see cpc_crtc.h. MIT, Retro-Recomp. */
#include "cpc_crtc.h"

#include <string.h>

/* The bits each register keeps (the data sheets' register widths). */
static const uint8_t MASK[18] = { 0xFF, 0xFF, 0xFF, 0xFF, 0x7F, 0x1F, 0x7F, 0x7F, 0xF3, 0x1F, 0x7F, 0x1F, 0x3F, 0xFF, 0x3F, 0xFF,
                                  0x3F, 0xFF };

/* What the CPC firmware programs for its 50 Hz screen (64 x 39 characters of 8 lines, 40 x 25 shown, start C000h). */
static const uint8_t FIRMWARE[18] = { 63, 40, 46, 0x8E, 38, 0, 25, 30, 0, 7, 0, 0, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00 };

void cpc_crtc_reset(CpcCrtc *c, uint8_t type)
{
    memset(c, 0, sizeof *c);
    c->type = type <= CPC_CRTC_TYPE2 ? type : CPC_CRTC_TYPE1;
    memcpy(c->reg, FIRMWARE, sizeof c->reg);
    c->h_display = c->v_display = 1;
    c->ma_row = c->ma_next = c->ma = (uint16_t)((c->reg[12] << 8) | c->reg[13]);
}

void cpc_crtc_select(CpcCrtc *c, uint8_t reg)
{
    c->select = reg & 0x1F;
}

void cpc_crtc_write(CpcCrtc *c, uint8_t value)
{
    if (c->select < 16)                                              /* R16/R17, the light pen, are read only */
        c->reg[c->select] = value & MASK[c->select];
}

uint8_t cpc_crtc_read(const CpcCrtc *c)
{
    uint8_t r = c->select;
    switch (c->type) {
    case CPC_CRTC_TYPE0:
        return r >= 12 && r <= 17 ? c->reg[r] : 0x00;
    case CPC_CRTC_TYPE1:
        if (r == 31)
            return 0xFF;
        return r >= 14 && r <= 17 ? c->reg[r] : 0x00;
    default:
        return r >= 14 && r <= 17 ? c->reg[r] : 0x00;
    }
}

uint8_t cpc_crtc_status(const CpcCrtc *c)
{
    /* Type 1's status register: bit 5 set during the vertical blanking (rows past R6). The other types answer as a read of
     * their data port does on the CPC (the port is not decoded apart). */
    if (c->type != CPC_CRTC_TYPE1)
        return cpc_crtc_read(c);
    return (uint8_t)(c->v_display ? 0x00 : 0x20);
}

CpcCrtcOut cpc_crtc_out(const CpcCrtc *c)
{
    CpcCrtcOut out = { c->ma, c->ra, (uint8_t)(c->h_display && c->v_display), c->hsync, c->vsync };
    return out;
}

static unsigned hsync_width(const CpcCrtc *c)
{
    unsigned w = c->reg[3] & 0x0F;
    if (!w)
        return c->type == CPC_CRTC_TYPE2 ? 16 : 0;
    return w;
}

static unsigned vsync_width(const CpcCrtc *c)
{
    if (c->type != CPC_CRTC_TYPE0)
        return 16;
    unsigned w = c->reg[3] >> 4;
    return w ? w : 16;
}

static uint16_t start_address(const CpcCrtc *c) { return (uint16_t)(((c->reg[12] & 0x3F) << 8) | c->reg[13]); }

static void new_frame(CpcCrtc *c)
{
    c->vcc = 0;
    c->ra = 0;
    c->adjust = 0;
    c->in_adjust = 0;
    c->v_display = 1;
    c->ma_row = c->ma_next = start_address(c);
}

/* The start of a line (character 0): row and frame counting, VSYNC. */
static void new_line(CpcCrtc *c)
{
    if (c->vsync && ++c->vsync_count >= vsync_width(c))
        c->vsync = 0;
    if (c->in_adjust) {
        if (++c->adjust >= c->reg[5])
            new_frame(c);
    } else if (c->ra >= c->reg[9]) {
        c->ra = 0;
        c->ma_row = c->ma_next;
        if (c->vcc >= c->reg[4]) {
            if (c->reg[5]) {
                c->in_adjust = 1;
                c->adjust = 0;
                ++c->vcc;
            } else {
                new_frame(c);
            }
        } else {
            ++c->vcc;
        }
    } else {
        ++c->ra;
    }
    if (c->vcc == c->reg[6] && c->ra == 0 && !c->in_adjust)
        c->v_display = 0;
    if (c->vcc == c->reg[7] && c->ra == 0 && !c->in_adjust && !c->vsync) {
        c->vsync = 1;
        c->vsync_count = 0;
    }
    /* Type 1 takes R12/R13 at the start of every line of the first row; the others at the frame's start only. */
    if (c->type == CPC_CRTC_TYPE1 && c->vcc == 0 && !c->in_adjust)
        c->ma_row = c->ma_next = start_address(c);
}

void cpc_crtc_step(CpcCrtc *c)
{
    if (c->hsync && ++c->hsync_count >= hsync_width(c))
        c->hsync = 0;
    if (c->hcc == c->reg[0]) {
        c->hcc = 0;
        c->h_display = 1;
        new_line(c);
    } else {
        ++c->hcc;
    }
    if (c->hcc == c->reg[1]) {
        c->h_display = 0;
        if (c->ra == c->reg[9])
            c->ma_next = (uint16_t)(c->ma_row + c->reg[1]);
    }
    if (c->hcc == c->reg[2] && !c->hsync && hsync_width(c)) {
        c->hsync = 1;
        c->hsync_count = 0;
    }
    c->ma = (uint16_t)((c->ma_row + c->hcc) & 0x3FFF);
}
