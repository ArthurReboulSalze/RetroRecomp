/* Included in the staged hw_mapper.c. Serialize VRC7 without host pointers:
 * the chip field by field (nes_state_vrc7.inc, generated from emu2413.h), then
 * each slot's patch and wave table as an index. */
#include "retro_nes.h"
#include "nes_state_vrc7.inc"
extern unsigned rr_opll_wave_index(const OPLL_SLOT *slot);
extern void rr_opll_restore_wave(OPLL_SLOT *slot, unsigned index);
size_t rr_nes_mapper_audio_size(void) { return hw_cart.mapper == 85 ? rr_size_OPLL() + 36 : 0; }
void rr_nes_mapper_audio_save(uint8_t *buffer) {
    if (hw_cart.mapper != 85) return;
    uint8_t *cursor = rr_ser_OPLL(buffer, vrc7_opll);
    for (int i = 0; i < 18; i++) *cursor++ = (uint8_t)(vrc7_opll->slot[i].patch - vrc7_opll->patch);
    for (int i = 0; i < 18; i++) *cursor++ = (uint8_t)rr_opll_wave_index(&vrc7_opll->slot[i]);
}
bool rr_nes_mapper_audio_check(const uint8_t *buffer) {
    if (hw_cart.mapper != 85) return true;
    if (!vrc7_opll || vrc7_opll->conv) return false;
    OPLL chip;
    memset(&chip, 0, sizeof(chip));
    const uint8_t *cursor = rr_de_OPLL(buffer, &chip);
    if (chip.clk != vrc7_opll->clk || chip.rate != vrc7_opll->rate) return false;
    for (int i = 0; i < 18; i++)
        if (cursor[i] >= 38 || cursor[18 + i] > 1) return false;
    return true;
}
void rr_nes_mapper_audio_load(const uint8_t *buffer) {
    if (hw_cart.mapper != 85) return;
    const uint8_t *cursor = rr_de_OPLL(buffer, vrc7_opll);
    for (int i = 0; i < 18; i++) {
        vrc7_opll->slot[i].patch = &vrc7_opll->patch[cursor[i]];
        rr_opll_restore_wave(&vrc7_opll->slot[i], cursor[18 + i]);
    }
}
