/* Authored virtual Light Phaser. TL is the trigger, TH is a raster pulse,
 * and the H counter stays latched between falling edges. The sensor is an
 * idealized finite spot, not a simulation of CRT brightness or gun optics.
 * See the Sega I/O documentation linked in docs/LIGHT_PHASER.md. */
#include "lightphaser.h"
#include "glue.h"
#include "sms_clocks.h"
#include <limits.h>

static bool enabled, trigger;
static int aim_x, aim_y, horizontal_offset;
static uint8_t control, h_latch;
static uint64_t previous_cycles;
static uint64_t sensor_low_reads, horizontal_reads;

void lightphaser_reset(bool active, int offset) {
    enabled = active; horizontal_offset = offset;
    aim_x = aim_y = -1; trigger = false;
    control = 0xFF; h_latch = 0; previous_cycles = 0;
    sensor_low_reads = horizontal_reads = 0;
}
bool lightphaser_enabled(void) { return enabled; }
void lightphaser_pointer(int x, int y, bool pressed) {
    aim_x = x; aim_y = y; trigger = pressed;
}
void lightphaser_position(int *x, int *y, bool *pressed) {
    *x = aim_x; *y = aim_y; *pressed = trigger;
}
static bool on_screen(void) { return aim_x >= 0 && aim_x < 256 && aim_y >= 0 && aim_y < 192; }

/* Follow the generated console clock and frame length, including PAL.
 * A 72-cycle low pulse is about 20 microseconds. It spans seven scanlines.
 * Events latch even if software skips reading DD at the leading edge. */
static bool sync_sensor(uint64_t cycles) {
    const uint64_t frame_cycles = SMS_CYC_PER_FRAME;
    bool low = false;
    if (enabled && (control & 2) && on_screen()) {
        uint64_t frame = cycles / frame_cycles;
        int first = aim_x * 2 / 3;
        uint64_t latest = 0;
        bool event = false;
        for (int y = aim_y - 3; y <= aim_y + 3; ++y) {
            if (y < 0 || y >= 192) continue;
            uint64_t edge = frame * frame_cycles + (uint64_t)y * 228u + first;
            if (edge <= cycles) {
                if (edge >= previous_cycles && (!event || edge > latest)) { latest = edge; event = true; }
                if (cycles - edge < 72 && cycles / 228u == edge / 228u) low = true;
            } else if (frame) {
                edge -= frame_cycles;
                if (edge >= previous_cycles && (!event || edge > latest)) { latest = edge; event = true; }
            }
        }
        if (event) h_latch = (uint8_t)(horizontal_offset + aim_x / 2);
    }
    previous_cycles = cycles == UINT64_MAX ? cycles : cycles + 1;
    return low;
}

uint8_t lightphaser_dc(uint8_t pad1, uint8_t pad2) {
    uint8_t value = (uint8_t)(0xFF ^ ((pad2 & 3) << 6));
    if (trigger || (pad1 & SMS_PAD_B1)) value &= (uint8_t)~0x10;
    if (!(control & 1)) value = (uint8_t)((value & ~0x20) | ((control & 0x10) << 1));
    return value;
}
uint8_t lightphaser_dd(uint8_t pad2, uint64_t cycles) {
    uint8_t value = (uint8_t)(0xFF ^ ((pad2 >> 2) & 15));
    if (sync_sensor(cycles)) { value &= (uint8_t)~0x40; ++sensor_low_reads; }
    if (!(control & 2)) value = (uint8_t)((value & ~0x40) | ((control & 0x20) << 1));
    if (!(control & 4)) value = (uint8_t)((value & ~8) | ((control & 0x40) >> 3));
    if (!(control & 8)) value = (uint8_t)((value & ~0x80) | (control & 0x80));
    return value;
}
uint8_t lightphaser_hcounter(uint64_t cycles) { ++horizontal_reads; sync_sensor(cycles); return h_latch; }
void lightphaser_observations(uint64_t *low_reads, uint64_t *counter_reads) {
    *low_reads = sensor_low_reads; *counter_reads = horizontal_reads;
}
void lightphaser_control(uint8_t value, uint64_t cycles, uint8_t free_hcounter) {
    bool sensor_low = sync_sensor(cycles);
    bool old_th1 = control & 2 ? !sensor_low : (control & 0x20) != 0;
    bool old_th2 = control & 8 ? true : (control & 0x80) != 0;
    control = value;
    bool new_th1 = control & 2 ? !sensor_low : (control & 0x20) != 0;
    bool new_th2 = control & 8 ? true : (control & 0x80) != 0;
    if ((old_th1 && !new_th1) || (old_th2 && !new_th2)) h_latch = free_hcounter;
}

#include "state_io.h"
void lightphaser_state(RetroStateIO *io) {
    uint8_t c = (uint8_t)rr_state_word(io, control, 1, 255);
    uint8_t h = (uint8_t)rr_state_word(io, h_latch, 1, 255);
    uint64_t previous = rr_state_word(io, previous_cycles, 8, UINT64_MAX);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        control = c; h_latch = h; previous_cycles = previous;
        /* Host aim/trigger and diagnostic counters belong to the live session. */
    }
}
