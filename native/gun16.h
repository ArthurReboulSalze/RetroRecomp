/* Original peripheral protocols. See docs/GUNS_16BIT.md for references. */
#ifndef RETRO_GUN16_H
#define RETRO_GUN16_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

enum { RR_GUN_NONE, RR_GUN_MENACER, RR_GUN_JUSTIFIER, RR_GUN_SCOPE };
typedef struct Rr16GunInput {
    int x, y;
    bool fire, aux, secondary, start, turbo, pause, offscreen;
} Rr16GunInput;

static uint8_t rr_menacer_buttons(const Rr16GunInput *in) {
    return (uint8_t)((in->aux ? 1 : 0) | (in->fire ? 2 : 0) |
                    (in->secondary ? 4 : 0) | (in->start ? 8 : 0));
}
typedef struct RrMenacer {
    uint8_t buttons;
    bool main_reset;
} RrMenacer;
static void rr_menacer_write(RrMenacer *gun, const Rr16GunInput *in,
                             uint8_t data, uint8_t control) {
    /* PD4/PD5 must be outputs. A long receiver reset (PD4 high, PD5 low)
     * acquires a button packet. TH-only device identification does not acquire
     * buttons, and a short counter reset retains the previous packet. */
    bool reset = (control & 0x30) == 0x30 && (data & 0x30) == 0x10;
    if (reset && !gun->main_reset) gun->buttons = rr_menacer_buttons(in);
    gun->main_reset = reset;
}

/* MD data-port pins, before merging CPU-driven outputs. A second Justifier
 * is unplugged: its buttons are released and it never produces a light hit. */
static uint8_t rr_md_gun_port(int kind, const Rr16GunInput *in, uint8_t data,
                             uint8_t control, bool light_low) {
    uint8_t pins;
    if (kind == RR_GUN_MENACER) {
        pins = (uint8_t)(0x40 | rr_menacer_buttons(in));
    } else {
        bool second = (data & control & 0x20) != 0;
        pins = (data & control & 0x40) ? 0x30 :
            (uint8_t)(0x70 | (in->fire && !second ? 0 : 1) |
                            (in->start && !second ? 0 : 2));
    }
    if (light_low) pins &= (uint8_t)~0x40;
    control &= 0x7f;
    return (uint8_t)((pins & ~control) | (data & control));
}

/* Documented discontinuous counter ranges, expressed arithmetically. */
static uint8_t rr_md_gun_hcounter(int x, int width, int offset, bool menacer) {
    if (menacer) x = x * 289 / 320;
    int index = (x / 2 + offset) % (width == 320 ? 210 : 171);
    if (index < 0) index += width == 320 ? 210 : 171;
    return (uint8_t)(index < (width == 320 ? 183 : 148) ? index :
                     index + (width == 320 ? 46 : 85));
}

typedef struct RrScope {
    Rr16GunInput input;
    bool pending_fire, pending_pause, previous_fire, previous_pause, strobe;
    bool reported_turbo;
    bool reported_offscreen;
    uint16_t packet;
    unsigned index;
} RrScope;
static void rr_scope_input(RrScope *scope, Rr16GunInput input) {
    if (input.fire && (!scope->previous_fire || (input.turbo && !scope->input.turbo)))
        scope->pending_fire = true;
    if (input.pause && !scope->previous_pause) scope->pending_pause = true;
    scope->previous_fire = input.fire;
    scope->previous_pause = input.pause;
    scope->input = input;
}
static uint16_t rr_scope_latch(RrScope *scope) {
    bool fire = scope->pending_fire || (scope->input.turbo && scope->input.fire);
    if (fire) scope->reported_turbo = scope->input.turbo;
    if (fire || scope->input.aux) scope->reported_offscreen = scope->input.offscreen;
    scope->packet = (uint16_t)(0x00ff | (fire ? 0x8000 : 0) |
        (scope->input.aux ? 0x4000 : 0) | (scope->reported_turbo ? 0x2000 : 0) |
        (scope->pending_pause && !fire && !scope->input.aux ? 0x1000 : 0) |
        (scope->reported_offscreen ? 0x0200 : 0));
    scope->pending_fire = scope->pending_pause = false;
    scope->index = 0;
    return scope->packet;
}
static void rr_scope_strobe(RrScope *scope, unsigned value) {
    bool next = (value & 1) != 0;
    if (scope->strobe && !next) rr_scope_latch(scope);
    scope->strobe = next;
}
static uint8_t rr_scope_serial(RrScope *scope) {
    if (scope->strobe) return scope->input.fire ? 1 : 0;
    if (scope->index >= 16) return 1;
    return (uint8_t)((scope->packet >> (15 - scope->index++)) & 1);
}

void rr16_gun_input(Rr16GunInput input);
void rr16_gun_reset(void);
void rr16_gun_report(FILE *file);
void rr16_md_gun_line(int line);
bool rr16_md_gun_pending(void);
void rr16_md_gun_irq_begin(void);
void rr16_md_gun_irq_end(void);
void rr16_md_instruction(bool active);
bool rr16_md_instruction_busy(void);
uint8_t rr16_md_gun_read(uint8_t data, uint8_t control);
void rr16_md_gun_io_write(uint8_t data, uint8_t control);
uint16_t rr16_md_gun_hv(uint16_t fallback);
void rr16_scope_write_strobe(unsigned value);
uint8_t rr16_scope_read(void);
void rr16_scope_auto(void);
uint8_t rr16_scope_auto_reg(unsigned reg);
uint8_t rr16_scope_iobit(uint8_t fallback);
void rr16_scope_beam(unsigned h, unsigned v, unsigned span);
#endif
