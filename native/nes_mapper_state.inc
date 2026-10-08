/* Included in the staged hw_mapper.c. Serialize VRC7 without host pointers. */
#include "retro_nes.h"
extern unsigned rr_opll_wave_index(const OPLL_SLOT *slot);
extern void rr_opll_restore_wave(OPLL_SLOT *slot, unsigned index);
typedef struct {
    OPLL chip;
    uint8_t patch[18], wave[18];
} RrVrc7State;
size_t rr_nes_mapper_audio_size(void) { return hw_cart.mapper == 85 ? sizeof(RrVrc7State) : 0; }
void rr_nes_mapper_audio_save(uint8_t *buffer) {
    if (hw_cart.mapper != 85) return;
    RrVrc7State s = {0};
    s.chip = *vrc7_opll;
    s.chip.conv = NULL; /* The fixed-rate VRC7 core does not use a converter. */
    for (int i = 0; i < 18; i++) {
        s.patch[i] = (uint8_t)(vrc7_opll->slot[i].patch - vrc7_opll->patch);
        s.wave[i] = (uint8_t)rr_opll_wave_index(&vrc7_opll->slot[i]);
        s.chip.slot[i].patch = NULL;
        s.chip.slot[i].wave_table = NULL;
    }
    memcpy(buffer, &s, sizeof(s));
}
bool rr_nes_mapper_audio_check(const uint8_t *buffer) {
    if (hw_cart.mapper != 85) return true;
    if (!vrc7_opll || vrc7_opll->conv) return false;
    RrVrc7State s;
    memcpy(&s, buffer, sizeof(s));
    if (s.chip.conv || s.chip.clk != vrc7_opll->clk || s.chip.rate != vrc7_opll->rate) return false;
    for (int i = 0; i < 18; i++)
        if (s.patch[i] >= 38 || s.wave[i] > 1 || s.chip.slot[i].patch || s.chip.slot[i].wave_table) return false;
    return true;
}
void rr_nes_mapper_audio_load(const uint8_t *buffer) {
    if (hw_cart.mapper != 85) return;
    RrVrc7State s;
    memcpy(&s, buffer, sizeof(s));
    *vrc7_opll = s.chip;
    for (int i = 0; i < 18; i++) {
        vrc7_opll->slot[i].patch = &vrc7_opll->patch[s.patch[i]];
        rr_opll_restore_wave(&vrc7_opll->slot[i], s.wave[i]);
    }
}
