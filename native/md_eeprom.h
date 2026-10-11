/* Original serial device model, from the Xicor X24C01/X24C02 wire diagrams
 * and ST M24C04 addressing. No emulator implementation is imported.
 * State is pointer-free; storage and the guest master clock are supplied by
 * the caller. Writes become nonvolatile only after STOP and the write cycle. */
#ifndef RR_MD_EEPROM_H
#define RR_MD_EEPROM_H
#include <stdint.h>
#include <string.h>
enum { RR_EE_IDLE, RR_EE_COMMAND, RR_EE_ADDRESS, RR_EE_WRITE,
       RR_EE_ACK, RR_EE_READ, RR_EE_MASTER_ACK };
typedef struct {
    uint64_t last_tick, busy_left;
    uint32_t write_ticks, completed_writes;
    uint16_t address, page_base, pending_mask;
    uint8_t kind, scl, host_sda, release_sda, phase, next_phase;
    uint8_t bits, shift, ack, ack_clock, read_ack, block;
    uint8_t pending[16];
} RrMdEeprom;
static unsigned rr_ee_size(unsigned kind) {
    return kind == 1 ? 128 : kind == 2 ? 256 : kind == 3 ? 512 : 0;
}
static unsigned rr_ee_page(unsigned kind) { return kind == 3 ? 16 : 4; }
static void rr_ee_init(RrMdEeprom *s, unsigned kind, unsigned master_hz) {
    memset(s, 0, sizeof *s); s->kind = (uint8_t)kind;
    s->scl = s->host_sda = s->release_sda = 1;
    /* Deterministic 5 ms software model, not a measured delay of every chip. */
    s->write_ticks = (master_hz + 199u) / 200u;
}
static void rr_ee_advance(RrMdEeprom *s, uint8_t *data, uint64_t now) {
    uint64_t elapsed = now - s->last_tick;
    /* Ignore an earlier interleaved timestamp; preserve modular clock wrap. */
    if ((int64_t)elapsed < 0) return;
    s->last_tick = now;
    if (!s->busy_left) return;
    if (elapsed < s->busy_left) { s->busy_left -= elapsed; return; }
    s->busy_left = 0;
    for (unsigned i = 0; i < rr_ee_page(s->kind); ++i)
        if (s->pending_mask & (1u << i)) data[s->page_base + i] = s->pending[i];
    s->pending_mask = 0; ++s->completed_writes;
}
static unsigned rr_ee_out(const RrMdEeprom *s) {
    return s->host_sda && s->release_sda;
}
static void rr_ee_tx(RrMdEeprom *s, const uint8_t *data) {
    s->phase = RR_EE_READ; s->bits = 0;
    s->shift = data[s->address]; s->release_sda = (s->shift >> 7) & 1;
}
static void rr_ee_received(RrMdEeprom *s) {
    unsigned value = s->shift, phase = s->phase;
    s->ack = 1; s->next_phase = RR_EE_WRITE;
    if (phase == RR_EE_COMMAND) {
        if (s->busy_left) { s->ack = 0; s->next_phase = RR_EE_IDLE; }
        else if (s->kind == 1) {
            s->address = (uint16_t)(value >> 1);
            s->next_phase = value & 1 ? RR_EE_READ : RR_EE_WRITE;
        } else {
            /* Address pins tied low. 24C04 A8 is in command bit 1. */
            unsigned mask = s->kind == 3 ? 0xfc : 0xfe;
            if ((value & mask) != 0xa0) { s->ack = 0; s->next_phase = RR_EE_IDLE; }
            else {
                s->block = (uint8_t)(s->kind == 3 ? value & 2 : 0);
                if (s->kind == 3) s->address = (s->address & 255u) | ((s->block >> 1) << 8);
                s->next_phase = value & 1 ? RR_EE_READ : RR_EE_ADDRESS;
            }
        }
    } else if (phase == RR_EE_ADDRESS) {
        s->address = (uint16_t)(value | ((s->block >> 1) << 8));
    } else {
        unsigned page = rr_ee_page(s->kind), offset = s->address & (page - 1);
        if (!s->pending_mask) s->page_base = s->address & ~(page - 1);
        s->pending[offset] = (uint8_t)value; s->pending_mask |= (uint16_t)(1u << offset);
        s->address = (uint16_t)(s->page_base | ((offset + 1) & (page - 1)));
    }
    s->phase = RR_EE_ACK; s->ack_clock = 0; s->bits = s->shift = 0;
}
static void rr_ee_lines(RrMdEeprom *s, uint8_t *data, uint64_t now,
                        unsigned scl, unsigned sda) {
    if (!s->kind) return;
    rr_ee_advance(s, data, now); scl = !!scl; sda = !!sda;
    unsigned old_scl = s->scl, old_wire = rr_ee_out(s);
    unsigned new_wire = sda && s->release_sda;
    s->scl = (uint8_t)scl; s->host_sda = (uint8_t)sda;
    if (old_scl && scl && old_wire != new_wire) {
        if (!new_wire) { /* START or repeated START; no implicit write. */
            if (!s->busy_left) s->pending_mask = 0;
            s->phase = RR_EE_COMMAND; s->bits = s->shift = 0; s->release_sda = 1;
        } else { /* STOP commits the staged page only after internal programming. */
            if (s->pending_mask && !s->busy_left) s->busy_left = s->write_ticks;
            s->phase = RR_EE_IDLE; s->bits = 0; s->release_sda = 1;
        }
        return;
    }
    if (!old_scl && scl) {
        if (s->phase == RR_EE_COMMAND || s->phase == RR_EE_ADDRESS || s->phase == RR_EE_WRITE) {
            s->shift = (uint8_t)((s->shift << 1) | new_wire);
            if (++s->bits == 8) rr_ee_received(s);
        } else if (s->phase == RR_EE_ACK) s->ack_clock = 1;
        else if (s->phase == RR_EE_READ) ++s->bits;
        else if (s->phase == RR_EE_MASTER_ACK) {
            s->read_ack = !new_wire; s->ack_clock = 1;
        }
    } else if (old_scl && !scl) {
        if (s->phase == RR_EE_ACK) {
            if (!s->ack_clock) s->release_sda = !s->ack;
            else {
                s->release_sda = 1; s->phase = s->next_phase;
                if (s->phase == RR_EE_READ) rr_ee_tx(s, data);
            }
        } else if (s->phase == RR_EE_READ) {
            if (s->bits == 8) {
                s->address = (uint16_t)((s->address + 1) & (rr_ee_size(s->kind) - 1));
                s->phase = RR_EE_MASTER_ACK; s->ack_clock = 0; s->release_sda = 1;
            } else s->release_sda = (s->shift >> (7 - s->bits)) & 1;
        } else if (s->phase == RR_EE_MASTER_ACK && s->ack_clock) {
            if (s->read_ack) rr_ee_tx(s, data);
            else { s->phase = RR_EE_IDLE; s->release_sda = 1; }
        }
    }
}
static int rr_ee_valid(const RrMdEeprom *s, unsigned kind, unsigned master_hz) {
    unsigned size = rr_ee_size(kind), page = rr_ee_page(kind);
    if (s->kind != kind || s->write_ticks != (master_hz + 199u) / 200u ||
        s->busy_left > s->write_ticks || s->scl > 1 || s->host_sda > 1 ||
        s->release_sda > 1 || s->ack > 1 || s->ack_clock > 1 || s->read_ack > 1 ||
        s->phase > RR_EE_MASTER_ACK || s->next_phase > RR_EE_MASTER_ACK ||
        s->bits > 8 || (s->block != 0 && s->block != 2) ||
        s->pending_mask & ~((1u << page) - 1)) return 0;
    if (!kind) return !s->busy_left && !s->pending_mask && !s->address && !s->page_base;
    /* Receive byte 8 has already entered ACK. The eighth read bit exists
     * only while SCL is high, before its falling edge enters master ACK.
     * Reject a forged low-clock READ/8 that could increment to 9 and make
     * the subsequent bit shift undefined. No reachable wire state is lost. */
    if ((s->phase == RR_EE_COMMAND || s->phase == RR_EE_ADDRESS || s->phase == RR_EE_WRITE) && s->bits == 8) return 0;
    if (s->phase == RR_EE_READ && s->bits == 8 && !s->scl) return 0;
    return s->address < size && s->page_base < size && !(s->page_base & (page - 1));
}
#endif
