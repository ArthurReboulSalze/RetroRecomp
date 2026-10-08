/* RetroRecomp's 16-bit mouse peripherals. No external emulator code copied. */
#include <string.h>
#include "retro_console16.h"
#if RR16_MD
#include "genesis_runtime.h"
#include "video/genesis_machine.h"
#else
#include "snes/snes.h"
#include "snes/ppu.h"
extern Snes *g_snes;
extern Ppu *g_ppu;
#endif

static Rr16GunInput input = {.x = -1, .y = -1, .offscreen = true};
static uint64_t light_hits, interrupt_count, button_reads;
#if RR16_MD
static bool hv_valid, pending_irq, irq_active, instruction_active;
static uint16_t latched_hv;
static RrMenacer menacer;
static uint64_t button_packets, trigger_packets;
#else
static RrScope scope;
static unsigned last_h, last_v;
#endif
void rr16_gun_input(Rr16GunInput value) {
    input = value;
    if (value.x < 0 || value.y < 0 || value.x >= rr16_visible_width() || value.y >= RR16_HEIGHT)
        input.offscreen = true;
#if !RR16_MD
    rr_scope_input(&scope, input);
#endif
}
void rr16_gun_reset(void) {
    light_hits = interrupt_count = button_reads = 0;
    input = (Rr16GunInput){.x = -1, .y = -1, .offscreen = true};
#if RR16_MD
    hv_valid = pending_irq = irq_active = instruction_active = false; latched_hv = 0;
    memset(&menacer, 0, sizeof menacer);
    button_packets = trigger_packets = 0;
#else
    memset(&scope, 0, sizeof scope); scope.input = input;
    scope.packet = 0x02ff; last_h = last_v = 0;
    scope.reported_offscreen = true;
#endif
}
void rr16_gun_report(FILE *file) {
    fprintf(file, ",\"gun_kind\":%d,\"gun_light_hits\":%llu,\"gun_interrupts\":%llu,\"gun_button_reads\":%llu",
        RR16_GUN, (unsigned long long)light_hits, (unsigned long long)interrupt_count,
        (unsigned long long)button_reads);
#if RR16_MD
    fprintf(file, ",\"gun_latched_hv\":%u,\"gun_buttons_latched\":%u,\"gun_port_control\":%u,\"gun_external_irq_enabled\":%s", latched_hv, menacer.buttons,
        g_machine.bus.io_ctrl[1], (g_machine.vdp.reg[11] & 8) ? "true" : "false");
    fprintf(file, ",\"gun_button_packets\":%llu,\"gun_trigger_packets\":%llu",
        (unsigned long long)button_packets, (unsigned long long)trigger_packets);
#else
    fprintf(file, ",\"gun_packet\":%u,\"gun_latched_h\":%u,\"gun_latched_v\":%u,\"gun_latch_enabled\":%s", scope.packet, last_h, last_v, g_snes->ppuLatch ? "true" : "false");
#endif
}
#if RR16_MD
void rr16_md_gun_io_write(uint8_t data, uint8_t control) {
    if (RR16_GUN == RR_GUN_MENACER) {
        bool previous = menacer.main_reset;
        rr_menacer_write(&menacer, &input, data, control);
        if (menacer.main_reset && !previous) {
            ++button_packets;
            if (menacer.buttons & 2) ++trigger_packets;
        }
    }
}
uint8_t rr16_md_gun_read(uint8_t data, uint8_t control) {
    ++button_reads;
    int y = input.y + RR16_GUN_Y_OFFSET;
    bool light = !input.offscreen && g_machine.vdp.scanline == y &&
        (RR16_GUN != RR_GUN_JUSTIFIER || !(data & control & 0x30));
    Rr16GunInput pins = input;
    if (RR16_GUN == RR_GUN_MENACER) {
        pins.aux = (menacer.buttons & 1) != 0; pins.fire = (menacer.buttons & 2) != 0;
        pins.secondary = (menacer.buttons & 4) != 0; pins.start = (menacer.buttons & 8) != 0;
    }
    return rr_md_gun_port(RR16_GUN, &pins, data, control, light);
}
void rr16_md_gun_line(int line) {
    if (!RR16_GUN || input.offscreen || line != input.y + RR16_GUN_Y_OFFSET || line >= RR16_HEIGHT) return;
    GenesisBus *bus = &g_machine.bus;
    if (!(bus->io_ctrl[1] & 0x80) || (bus->io_ctrl[1] & 0x40)) return;
    if (RR16_GUN == RR_GUN_JUSTIFIER && (bus->io_data[1] & bus->io_ctrl[1] & 0x30)) return;
    ++light_hits;
    latched_hv = (uint16_t)((line << 8) | rr_md_gun_hcounter(input.x,
        rr16_visible_width(), RR16_GUN_X_OFFSET, RR16_GUN == RR_GUN_MENACER));
    hv_valid = true;
    if (g_machine.vdp.reg[11] & 8) pending_irq = true;
}
bool rr16_md_gun_pending(void) { return RR16_GUN && pending_irq; }
void rr16_md_gun_irq_begin(void) { pending_irq = false; irq_active = true; ++interrupt_count; }
void rr16_md_gun_irq_end(void) { irq_active = false; }
void rr16_md_gun_instruction(bool active) { instruction_active = RR16_GUN && active; }
bool rr16_md_gun_instruction_busy(void) { return instruction_active; }
uint16_t rr16_md_gun_hv(uint16_t fallback) {
    /* The engine schedules whole scanlines. Non-latching games receive the
     * sensor estimate during their level-2 handler only, not a frozen clock. */
    return RR16_GUN && hv_valid && ((g_machine.vdp.reg[0] & 2) || irq_active) ? latched_hv : fallback;
}
#else
void rr16_scope_write_strobe(unsigned value) { if (RR16_GUN == RR_GUN_SCOPE) rr_scope_strobe(&scope, value); }
uint8_t rr16_scope_read(void) { ++button_reads; return rr_scope_serial(&scope); }
void rr16_scope_auto(void) { rr_scope_latch(&scope); scope.index = 16; ++button_reads; }
uint8_t rr16_scope_auto_reg(unsigned reg) { ++button_reads; return (uint8_t)(scope.packet >> ((reg & 1) ? 8 : 0)); }
uint8_t rr16_scope_iobit(uint8_t fallback) {
    if (RR16_GUN != RR_GUN_SCOPE || input.offscreen || !(input.fire || input.aux)) return fallback;
    unsigned target = (unsigned)(input.x + 10) * 4;
    unsigned y = input.y >= 3 ? (unsigned)input.y - 3 : 0;
    return g_snes->vPos == y && g_snes->hPos >= target && g_snes->hPos < target + 4 ?
        (uint8_t)(fallback & ~0x80) : fallback;
}
void rr16_scope_beam(unsigned h, unsigned v, unsigned span) {
    if (RR16_GUN != RR_GUN_SCOPE || input.offscreen || !(input.fire || input.aux) || !g_snes->ppuLatch) return;
    unsigned x = (unsigned)(input.x + 10);
    unsigned y = input.y >= 3 ? (unsigned)input.y - 3 : 0;
    if (v != y || x * 4 < h || x * 4 >= h + span) return;
    g_ppu->hCount = (uint16_t)x; g_ppu->vCount = (uint16_t)y;
    g_ppu->countersLatched = true;
    last_h = x; last_v = y; ++light_hits;
}
#endif
