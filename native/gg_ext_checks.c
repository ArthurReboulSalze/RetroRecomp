/* ROM-free checks of the Game Gear EXT port and the Gear-to-Gear cable (native/gg_ext.h): two contexts, an authored sequence of
 * port accesses at given cycles, and what the other end must see and when. Driven by tools/gg_ext_selftest.py. */
#include <stdio.h>
#include "gg_ext.h"

static int failures, checks;
#define CHECK(cond) do { ++checks; if (!(cond)) { ++failures; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); } } while (0)

typedef struct { GgExt e[2]; GgCable c; } Pair;
static void pair(Pair *p) { gg_ext_reset(&p->e[0]); gg_ext_reset(&p->e[1]); gg_cable_reset(&p->c); }
static uint8_t in(Pair *p, int s, unsigned port, uint64_t cyc) { return gg_ext_in(&p->e[s], &p->c, s, port, cyc); }
static void out(Pair *p, int s, unsigned port, uint8_t v, uint64_t cyc) { gg_ext_out(&p->e[s], &p->c, s, port, v, cyc); }
static bool nmi(Pair *p, int s, uint64_t cyc) { return gg_ext_nmi(&p->e[s], &p->c, s, cyc); }

#define SERIAL 0x30            /* SOUT | SIN, 4800 baud */

int main(void) {
    Pair p;
    /* ---- reset values ---- */
    pair(&p);
    CHECK(in(&p, 0, 2, 0) == 0xFF && in(&p, 0, 3, 0) == 0x00 && in(&p, 0, 4, 0) == 0xFF && in(&p, 0, 5, 0) == 0x00);
    CHECK(gg_bit_cycles(0x00) == 746 && gg_bit_cycles(0x40) == 1492 && gg_bit_cycles(0x80) == 2983 && gg_bit_cycles(0xC0) == 11932);

    /* ---- a byte on the wire: timing of TFUL, RRDY, the NMI ---- */
    pair(&p);
    out(&p, 0, 5, SERIAL | GG_S_RINT, 100); out(&p, 1, 5, SERIAL | GG_S_RINT, 100);
    CHECK((in(&p, 0, 5, 200) & 0xF8) == (SERIAL | GG_S_RINT));       /* only bits 3-7 are stored; bits 0-2 are status */
    out(&p, 0, 3, 0xA5, 1000);
    CHECK(in(&p, 0, 5, 1000) & GG_S_TFUL);                            /* the frame is on the wire */
    CHECK(in(&p, 0, 3, 1001) == 0xA5);                                /* $03 reads back what was written */
    CHECK(!(in(&p, 1, 5, 1000 + 7086) & GG_S_RRDY));                  /* 19 half bits = 7,087 cycles: not yet */
    CHECK(!nmi(&p, 1, 1000 + 7086));
    CHECK((in(&p, 1, 5, 1000 + 7087) & GG_S_RRDY) != 0);              /* at the centre of the stop bit */
    CHECK(nmi(&p, 1, 1000 + 7087));                                    /* RINT: the NMI line rose, one edge */
    CHECK(!nmi(&p, 1, 1000 + 7090));                                   /* held: no second edge */
    CHECK(in(&p, 1, 4, 1000 + 7100) == 0xA5);
    CHECK(!(in(&p, 1, 5, 1000 + 7101) & GG_S_RRDY));                  /* reading $04 clears RRDY... */
    CHECK(!nmi(&p, 1, 1000 + 7102));                                   /* ...and the NMI line */
    CHECK(in(&p, 0, 5, 1000 + 7459) & GG_S_TFUL);                      /* the sender is busy for 10 bit times: 7,460 cycles */
    CHECK(!(in(&p, 0, 5, 1000 + 7460) & GG_S_TFUL));
    CHECK(!nmi(&p, 0, 1000 + 8000));                                   /* nothing was sent to console 1's peer */
    /* a second byte raises a second edge */
    out(&p, 1, 3, 0x5A, 9000);
    CHECK(nmi(&p, 0, 9000 + 7087) && in(&p, 0, 4, 9000 + 7090) == 0x5A);
    CHECK(p.e[0].received == 1 && p.e[1].received == 1 && gg_cable_sent(&p.c, 0) == 1 && gg_cable_sent(&p.c, 1) == 1);

    /* ---- the receive NMI needs RINT ---- */
    pair(&p);
    out(&p, 0, 5, SERIAL, 0); out(&p, 1, 5, SERIAL, 0);
    out(&p, 0, 3, 0x11, 10);
    CHECK((in(&p, 1, 5, 10 + 7087) & GG_S_RRDY) && !nmi(&p, 1, 10 + 7088));

    /* ---- baud rates ---- */
    for (int rate = 0; rate < 4; ++rate) {
        pair(&p);
        const uint8_t control = (uint8_t)(0x30 | (rate << 6));
        const uint64_t bit = gg_bit_cycles(control);
        out(&p, 0, 5, control, 0); out(&p, 1, 5, control, 0);
        out(&p, 0, 3, 0x77, 500);
        CHECK(!(in(&p, 1, 5, 500 + (19 * bit) / 2 - 1) & GG_S_RRDY));
        CHECK(in(&p, 1, 5, 500 + (19 * bit) / 2) & GG_S_RRDY);
        CHECK(in(&p, 0, 5, 500 + 10 * bit - 1) & GG_S_TFUL);
        CHECK(!(in(&p, 0, 5, 500 + 10 * bit) & GG_S_TFUL));
    }

    /* ---- a write while a frame is on the wire is dropped; a transmitter that is off sends nothing; a receiver that is off loses it ---- */
    pair(&p);
    out(&p, 0, 5, SERIAL, 0); out(&p, 1, 5, SERIAL, 0);
    out(&p, 0, 3, 0x01, 100); out(&p, 0, 3, 0x02, 200);
    CHECK(in(&p, 1, 4, 100 + 7087) == 0x01 && p.e[0].dropped == 1 && gg_cable_sent(&p.c, 0) == 1);
    pair(&p);
    out(&p, 0, 5, GG_S_SIN, 0); out(&p, 1, 5, SERIAL, 0);
    out(&p, 0, 3, 0x33, 100);
    CHECK(!(in(&p, 1, 5, 100 + 7087) & GG_S_RRDY));
    pair(&p);
    out(&p, 0, 5, SERIAL, 0); out(&p, 1, 5, GG_S_SOUT, 0);
    out(&p, 0, 3, 0x44, 100);
    CHECK(!(in(&p, 1, 5, 100 + 7087) & GG_S_RRDY) && p.e[1].dropped == 1);
    /* switching the transmitter off aborts the frame on the wire */
    pair(&p);
    out(&p, 0, 5, SERIAL, 0); out(&p, 1, 5, SERIAL, 0);
    out(&p, 0, 3, 0x55, 100); out(&p, 0, 5, GG_S_SIN, 1000);
    CHECK(!(in(&p, 1, 5, 100 + 7087) & GG_S_RRDY) && !(in(&p, 0, 5, 1001) & GG_S_TFUL));

    /* ---- parallel lines: the cable swaps the bits (0<->2, 1<->3, 4<->5, 6 straight), outputs wired-AND ---- */
    pair(&p);
    out(&p, 0, 2, 0x80, 0);
    out(&p, 0, 1, 0x7F & ~0x01, 0);               /* bit 0 low on console 0 */
    CHECK((in(&p, 1, 1, 10) & 0x7F) == (0x7F & ~0x04));
    out(&p, 0, 1, 0x7F & ~0x02, 20);              /* bit 1 low -> bit 3 */
    CHECK((in(&p, 1, 1, 30) & 0x7F) == (0x7F & ~0x08));
    out(&p, 0, 1, 0x7F & ~0x10, 40);              /* bit 4 low -> bit 5 */
    CHECK((in(&p, 1, 1, 50) & 0x7F) == (0x7F & ~0x20));
    out(&p, 0, 1, 0x7F & ~0x40, 60);              /* bit 6 straight */
    CHECK((in(&p, 1, 1, 70) & 0x7F) == (0x7F & ~0x40));
    CHECK((in(&p, 0, 1, 70) & 0x7F) == (0x7F & ~0x40));   /* its own output reads back */
    /* bit 7 of $01 is plain storage */
    out(&p, 0, 1, 0x80, 80);
    CHECK(in(&p, 0, 1, 90) & 0x80);

    /* ---- the PC6 NMI: a falling edge of the other console's PC6, armed by $02 bit 7 = 0 with PC6 an input ---- */
    pair(&p);
    out(&p, 1, 2, 0x7F, 0);                       /* console 1: all inputs, NMI enabled */
    out(&p, 0, 2, 0x80 | 0x3F, 10);               /* console 0 drives PC6 (bit 6 of $02 = 0) */
    out(&p, 0, 1, 0x7F, 20);                      /* PC6 high */
    CHECK(!nmi(&p, 1, 30));
    out(&p, 0, 1, 0x3F, 40);                      /* PC6 falls */
    CHECK(nmi(&p, 1, 50) && !nmi(&p, 1, 60));     /* one edge, and the latch holds the line */
    out(&p, 1, 2, 0xFF, 70);                      /* disabling clears the latch */
    CHECK(!nmi(&p, 1, 80));
    out(&p, 0, 1, 0x7F, 90); out(&p, 0, 1, 0x3F, 100);
    CHECK(!nmi(&p, 1, 110));                      /* disabled: the edge is not latched */
    out(&p, 0, 1, 0x7F, 120);
    out(&p, 1, 2, 0x7F, 130);                     /* re-enabled while PC6 is high */
    out(&p, 0, 1, 0x3F, 140);
    CHECK(nmi(&p, 1, 150));
    /* PC6 as an output of the console itself never interrupts it */
    pair(&p);
    out(&p, 1, 2, 0x3F, 0);
    out(&p, 1, 1, 0x7F, 10); out(&p, 1, 1, 0x3F, 20);
    CHECK(!nmi(&p, 1, 30));

    /* ---- the state, as named bytes, is deterministic and valid ---- */
    Pair a, b;
    pair(&a); pair(&b);
    for (Pair *q = &a; q != NULL; q = (q == &a ? &b : NULL)) {
        out(q, 0, 5, SERIAL | GG_S_RINT, 0); out(q, 1, 5, SERIAL | GG_S_RINT, 0);
        out(q, 0, 3, 0xC3, 1234); out(q, 1, 2, 0x7F, 1300);
        (void)in(q, 1, 5, 2000);
    }
    uint8_t x[GG_EXT_STATE_BYTES], y[GG_EXT_STATE_BYTES], cx[GG_CABLE_STATE_BYTES], cy[GG_CABLE_STATE_BYTES];
    CHECK(gg_ext_state_bytes(&a.e[0], x, sizeof x) == gg_ext_state_bytes(&b.e[0], y, sizeof y) && !memcmp(x, y, GG_EXT_STATE_BYTES - 21));
    CHECK(gg_cable_state_bytes(&a.c, cx, sizeof cx) && gg_cable_state_bytes(&b.c, cy, sizeof cy) && !memcmp(cx, cy, 78));
    CHECK(gg_ext_valid(&a.e[0]) && gg_ext_valid(&a.e[1]) && gg_cable_valid(&a.c));
    CHECK(a.c.count[0] == 1);                     /* the byte of console 0 is still in flight at cycle 2000 */

    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
