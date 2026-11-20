/* The Game Gear's EXT port, its serial link and the Gear-to-Gear cable between two consoles (Game Gear only).
 *
 * Pure C, no globals, no host: a console has one GgExt, a pair of consoles has one GgCable, and every call gives the cycle of the
 * Z80 that makes it (the console's own cycle counter). The two consoles run in lockstep slices (native/gg_link.inc) shorter than
 * the 9.5 bit times a byte needs to arrive, so a byte sent by one is never due before the slice of the other that follows: the
 * serial model is exact in time; the parallel lines and the PC6 line are seen by the other console one slice late at most.
 *
 * Registers (docs/GAME_GEAR.md, section "Gear-to-Gear cable"; facts read from MAME's gamegear_io_port_device (BSD-3-Clause), the
 * SMS Power wiki and Charles MacDonald's notes; no GPL or non-commercial code is used; what is unverified is listed on that page):
 *   $01 EXT data: the seven pins PC0-PC6 (bit 7 is plain storage)
 *   $02 direction (bit = 1: input) of those pins; bit 7 = 0 enables the PC6 NMI
 *   $03 serial transmit data     $04 serial receive data (reading it clears RRDY and RERR)
 *   $05 serial control / status: bit 0 TFUL (transmit busy), 1 RRDY, 2 RERR, 3 RINT (receive NMI enable), 4 SOUT (transmitter on),
 *       5 SIN (receiver on), 7:6 baud (4800 / 2400 / 1200 / 300). Only bits 3-7 are written.
 * Both interrupt sources (a received byte, a falling edge of PC6) go to the Z80 NMI, never to /INT.
 * Cable: serial null-modem (TXD PC4 to RXD PC5), PC6 straight, the other parallel lines swapped in pairs. Original code, MIT. */
#ifndef GG_EXT_H
#define GG_EXT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum {
    GG_S_TFUL = 0x01, GG_S_RRDY = 0x02, GG_S_RERR = 0x04, GG_S_RINT = 0x08, GG_S_SOUT = 0x10, GG_S_SIN = 0x20,
    GG_S_BAUD_SHIFT = 6, GG_S_WRITE_MASK = 0xF8,
    GG_PIN_TXD = 0x10, GG_PIN_RXD = 0x20, GG_PIN_NMI = 0x40, GG_PINS = 0x7F
};
#define GG_Z80_HZ 3579545ull
#define GG_QUEUE 4                                   /* bytes in flight per direction (at most two can be, at 4800 baud) */

typedef struct { uint64_t due; uint8_t value; } GgWireByte;

typedef struct {
    uint8_t p01, p02, p03, p04, p05;                 /* what was written (p05: bits 3-7), the last byte received */
    uint8_t tx_busy; uint64_t tx_done;               /* a frame is on the wire until tx_done */
    uint8_t rx_ready, rx_error;                      /* RRDY, RERR */
    uint8_t pc6_latch, nmi_line, pc6_level;          /* the PC6 falling-edge latch, the NMI line as last seen, the PC6 level as last seen */
    uint64_t sent, received, dropped;                /* telemetry, part of the state so that a replay agrees */
} GgExt;

typedef struct {
    GgWireByte wire[2][GG_QUEUE];                    /* wire[s]: sent by console s, on its way to the other console */
    uint8_t count[2];
    uint8_t drive[2], level[2];                      /* the pins each console drives (mask) and the level of the driven ones */
    uint32_t total[2];
} GgCable;

#define GG_EXT_STATE_BYTES 64
#define GG_CABLE_STATE_BYTES (2 * (3 + GG_QUEUE * 9) + 8)

/* One bit time in Z80 cycles, rounded up (746, 1492, 2983, 11932: the values of the one cycle-based model read). */
static inline uint64_t gg_bit_cycles(uint8_t control) {
    static const unsigned baud[4] = {4800, 2400, 1200, 300};
    const unsigned b = baud[(control >> GG_S_BAUD_SHIFT) & 3];
    return (GG_Z80_HZ + b - 1) / b;
}

static inline void gg_cable_reset(GgCable *c) { memset(c, 0, sizeof *c); c->drive[0] = c->drive[1] = 0; c->level[0] = c->level[1] = GG_PINS; }
static inline void gg_ext_reset(GgExt *e) {
    memset(e, 0, sizeof *e);
    e->p01 = 0x7F; e->p02 = 0xFF; e->p04 = 0xFF; e->pc6_level = 1;
}

/* The pins this console drives: the outputs of $02, PC4 by the transmitter when it is on, PC5 never when the receiver is. */
static inline void gg_ext_drive(const GgExt *e, uint8_t *drive, uint8_t *level) {
    uint8_t d = (uint8_t)(~e->p02 & GG_PINS), l = e->p01 & GG_PINS;
    if (e->p05 & GG_S_SOUT) { d |= GG_PIN_TXD; l |= GG_PIN_TXD; }       /* TXD idles high; the bytes go through the wire queue */
    if (e->p05 & GG_S_SIN) d &= (uint8_t)~GG_PIN_RXD;
    *drive = d; *level = l;
}
static inline void gg_cable_publish(GgCable *c, int side, const GgExt *e) { gg_ext_drive(e, &c->drive[side], &c->level[side]); }

/* The other console's pins as this console reads them through the cable: bit 0<->2, 1<->3, 4<->5, 6 straight, 7 not connected. */
static inline uint8_t gg_cable_swap(uint8_t v) {
    return (uint8_t)(((v & 3) << 2) | ((v & 0x0C) >> 2) | ((v & 0x10) << 1) | ((v & 0x20) >> 1) | (v & 0x40));
}
/* The level of every pin of console `side`: wired-AND of what both ends drive; an undriven pin reads 1 (pull-up). */
static inline uint8_t gg_cable_pins(const GgCable *c, int side) {
    const int other = side ^ 1;
    const uint8_t mine = (uint8_t)(c->level[side] | ~c->drive[side]);
    const uint8_t theirs = gg_cable_swap((uint8_t)((c->level[other] | ~c->drive[other]) & GG_PINS));
    return (uint8_t)(mine & theirs & GG_PINS);
}

static inline void gg_ext_nmi_sample(GgExt *e, const GgCable *c, int side) {
    const uint8_t pc6 = (gg_cable_pins(c, side) & GG_PIN_NMI) ? 1 : 0;
    /* PC6 is an input of this console (bit 6 of $02 is 1) and the NMI is enabled ($02 bit 7 is 0): a falling edge latches. */
    if (e->pc6_level && !pc6 && (e->p02 & 0x40) && !(e->p02 & 0x80)) e->pc6_latch = 1;
    e->pc6_level = pc6;
}

/* Bring this console's serial machine and its lines up to its cycle. */
static inline void gg_ext_advance(GgExt *e, GgCable *c, int side, uint64_t cyc) {
    if (e->tx_busy && cyc >= e->tx_done) e->tx_busy = 0;
    const int from = side ^ 1;
    while (c->count[from] && c->wire[from][0].due <= cyc) {
        if (e->p05 & GG_S_SIN) {
            if (e->rx_ready) e->dropped++;           /* not read in time: the new byte replaces it (no error flag: unverified on hardware) */
            e->p04 = c->wire[from][0].value; e->rx_ready = 1; e->received++;
        } else e->dropped++;                          /* the receiver is off: the byte is lost */
        for (int i = 1; i < c->count[from]; ++i) c->wire[from][i - 1] = c->wire[from][i];
        c->count[from]--;
    }
    gg_ext_nmi_sample(e, c, side);
}

static inline uint8_t gg_ext_in(GgExt *e, GgCable *c, int side, unsigned port, uint64_t cyc) {
    gg_ext_advance(e, c, side, cyc);
    switch (port) {
    case 1: return (uint8_t)((gg_cable_pins(c, side) & GG_PINS) | (e->p01 & 0x80));
    case 2: return e->p02;
    case 3: return e->p03;
    case 4: e->rx_ready = 0; e->rx_error = 0; return e->p04;
    case 5: return (uint8_t)((e->p05 & GG_S_WRITE_MASK) | (e->rx_error ? GG_S_RERR : 0) | (e->rx_ready ? GG_S_RRDY : 0) | (e->tx_busy ? GG_S_TFUL : 0));
    default: return 0xFF;
    }
}

static inline void gg_ext_out(GgExt *e, GgCable *c, int side, unsigned port, uint8_t value, uint64_t cyc) {
    gg_ext_advance(e, c, side, cyc);
    switch (port) {
    case 1: e->p01 = value; break;
    case 2:
        e->p02 = value;
        if (value & 0x80) e->pc6_latch = 0;          /* disabling the PC6 NMI clears its latch */
        break;
    case 3:
        e->p03 = value;
        if ((e->p05 & GG_S_SOUT) && !e->tx_busy) {   /* a byte written while a frame is on the wire is dropped (one buffer: unverified) */
            const uint64_t bit = gg_bit_cycles(e->p05);
            e->tx_busy = 1; e->tx_done = cyc + 10 * bit; e->sent++;
            if (c->count[side] < GG_QUEUE) {          /* it reaches the other console at the centre of the stop bit */
                c->wire[side][c->count[side]].due = cyc + (19 * bit) / 2; c->wire[side][c->count[side]].value = value;
                c->count[side]++; c->total[side]++;
            }
        } else if (e->p05 & GG_S_SOUT) e->dropped++;
        break;
    case 5: {
        const uint8_t old = e->p05;
        e->p05 = value & GG_S_WRITE_MASK;
        if ((old & GG_S_SOUT) && !(e->p05 & GG_S_SOUT)) {      /* the transmitter switched off: the frame on the wire is lost */
            if (e->tx_busy && c->count[side]) c->count[side]--;
            e->tx_busy = 0;
        }
        if ((old & GG_S_SIN) && !(e->p05 & GG_S_SIN)) { e->rx_ready = 0; e->rx_error = 0; }
        break;
    }
    default: break;
    }
    gg_cable_publish(c, side, e);
    gg_ext_nmi_sample(e, c, side);
}

/* The NMI line is the receive condition or the PC6 latch; the Z80 takes its rising edge. */
static inline bool gg_ext_nmi(GgExt *e, GgCable *c, int side, uint64_t cyc) {
    gg_ext_advance(e, c, side, cyc);
    const uint8_t line = ((e->p05 & GG_S_RINT) && (e->rx_ready || e->rx_error)) || e->pc6_latch;
    const bool edge = line && !e->nmi_line;
    e->nmi_line = line;
    return edge;
}
/* The EXT port never raises /INT. */
static inline bool gg_ext_irq(GgExt *e, GgCable *c, int side, uint64_t cyc) { (void)e; (void)c; (void)side; (void)cyc; return false; }

static inline bool gg_ext_valid(const GgExt *e) {
    return e->tx_busy <= 1 && e->rx_ready <= 1 && e->rx_error <= 1 && e->pc6_latch <= 1 && e->nmi_line <= 1 && e->pc6_level <= 1;
}
static inline bool gg_cable_valid(const GgCable *c) { return c->count[0] <= GG_QUEUE && c->count[1] <= GG_QUEUE; }

static inline const char *gg_ext_summary(const GgExt *e) {
    static char text[4][160];
    static int next;
    char *out = text[next++ & 3];
    snprintf(out, 160, "ext sent=%llu received=%llu dropped=%llu rx=%02X ctl=%02X", (unsigned long long)e->sent,
        (unsigned long long)e->received, (unsigned long long)e->dropped, e->p04, e->p05);
    return out;
}
static inline uint32_t gg_cable_sent(const GgCable *c, int side) { return c->total[side]; }

/* The state as named fields in a fixed byte order, for the digest (never a raw struct). */
static inline size_t gg_ext_state_bytes(const GgExt *e, uint8_t *out, size_t capacity) {
    if (capacity < GG_EXT_STATE_BYTES) return 0;
    size_t n = 0;
    out[n++] = e->p01; out[n++] = e->p02; out[n++] = e->p03; out[n++] = e->p04; out[n++] = e->p05; out[n++] = e->tx_busy;
    out[n++] = e->rx_ready; out[n++] = e->rx_error; out[n++] = e->pc6_latch; out[n++] = e->nmi_line; out[n++] = e->pc6_level;
    const uint64_t words[4] = {e->tx_done, e->sent, e->received, e->dropped};
    for (int w = 0; w < 4; ++w) for (int b = 0; b < 8; ++b) out[n++] = (uint8_t)(words[w] >> (8 * b));
    return n;
}
static inline size_t gg_cable_state_bytes(const GgCable *c, uint8_t *out, size_t capacity) {
    if (capacity < GG_CABLE_STATE_BYTES) return 0;
    size_t n = 0;
    for (int s = 0; s < 2; ++s) {
        out[n++] = c->count[s]; out[n++] = c->drive[s]; out[n++] = c->level[s];
        for (int i = 0; i < GG_QUEUE; ++i) {
            const uint64_t due = i < c->count[s] ? c->wire[s][i].due : 0;
            for (int b = 0; b < 8; ++b) out[n++] = (uint8_t)(due >> (8 * b));
            out[n++] = i < c->count[s] ? c->wire[s][i].value : 0;
        }
    }
    return n;
}

#endif
