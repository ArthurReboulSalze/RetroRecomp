/* The CPC's PPI 8255 and keyboard: see cpc_ppi.h. MIT, Retro-Recomp. */
#include "cpc_ppi.h"

#include <string.h>

enum { PORT_B_FIXED = 0x7E };   /* links 1-3 (Amstrad), 50 Hz, no expansion, no printer; bit 0 VSYNC, bit 7 tape: see cpc_ppi.h */

void cpc_ppi_reset(CpcPpi *p)
{
    uint8_t keys[CPC_KEY_ROWS], joystick[2];
    memcpy(keys, p->keys, sizeof keys);
    memcpy(joystick, p->joystick, sizeof joystick);
    memset(p, 0, sizeof *p);
    p->control = 0x9B;                                               /* the 8255 resets with every port an input */
    memcpy(p->keys, keys, sizeof keys);
    memcpy(p->joystick, joystick, sizeof joystick);
}

uint8_t cpc_ppi_row(const CpcPpi *p)
{
    unsigned row = p->port_c & 0x0F;
    if (row >= CPC_KEY_ROWS)
        return 0xFF;
    uint8_t down = p->keys[row];
    if (row == 9) down |= p->joystick[0] & 0x3F;
    if (row == 6) down |= p->joystick[1] & 0x3F;
    return (uint8_t)~down;
}

void cpc_ppi_key(CpcPpi *p, unsigned key, int down)
{
    if (key >= CPC_KEY_ROWS * 8)
        return;
    uint8_t bit = (uint8_t)(1u << (key & 7));
    if (down) p->keys[key >> 3] |= bit; else p->keys[key >> 3] &= (uint8_t)~bit;
}

/* Port C's bits 7-6 drive the AY's bus: each change of them, or of port A while they say write or latch, is an AY cycle. */
static void psg_cycle(CpcPpi *p, const CpcPsgBus *psg)
{
    if (!psg)
        return;
    switch (p->port_c >> 6) {
    case 3: if (psg->latch) psg->latch(psg->context, p->port_a); break;
    case 2: if (psg->write) psg->write(psg->context, p->port_a); break;
    case 1: p->psg_data = psg->read ? psg->read(psg->context) : 0xFF; break;
    default: break;
    }
}

uint8_t cpc_ppi_read(CpcPpi *p, unsigned offset, int vsync, const CpcPsgBus *psg)
{
    switch (offset & 3) {
    case 0:
        if (!(p->control & 0x10))
            return p->port_a;                                        /* an output port reads its latch */
        if ((p->port_c >> 6) == 1)
            psg_cycle(p, psg);                                       /* the AY drives the bus while asked to read */
        return (p->port_c >> 6) == 1 ? p->psg_data : 0xFF;
    case 1:
        return (uint8_t)(PORT_B_FIXED | (vsync ? 0x01 : 0x00));
    case 2: {
        uint8_t v = p->port_c;
        if (p->control & 0x08) v |= 0xF0;                            /* inputs read high: nothing drives them */
        if (p->control & 0x01) v |= 0x0F;
        return v;
    }
    default:
        return 0xFF;                                                 /* the control register cannot be read */
    }
}

void cpc_ppi_write(CpcPpi *p, unsigned offset, uint8_t value, const CpcPsgBus *psg)
{
    switch (offset & 3) {
    case 0:
        p->port_a = value;
        if (!(p->control & 0x10))
            psg_cycle(p, psg);
        break;
    case 1:
        break;                                                       /* port B is an input on the CPC */
    case 2:
        p->port_c = value;
        psg_cycle(p, psg);
        break;
    default:
        if (value & 0x80) {                                          /* mode set: the outputs clear */
            p->control = value;
            p->port_a = 0;
            p->port_c = 0;
        } else {                                                     /* one bit of port C */
            uint8_t bit = (uint8_t)(1u << ((value >> 1) & 7));
            if (value & 1) p->port_c |= bit; else p->port_c &= (uint8_t)~bit;
            psg_cycle(p, psg);
        }
        break;
    }
}
