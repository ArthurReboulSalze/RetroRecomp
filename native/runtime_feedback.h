#ifndef RR_RUNTIME_FEEDBACK_H
#define RR_RUNTIME_FEEDBACK_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Host-only, bounded, deduplicated observations. Neither function below does
 * filesystem I/O. The one registered exit handler merges/writes on normal exit.
 * reset and quick-state loading must not clear this session's observations. */
enum {
    RR_FB_SEGA_Z80=1, RR_FB_GB=2, RR_FB_NES_ROM=3, RR_FB_NES_RAM=4,
    RR_FB_MD_ROM=5, RR_FB_MD_RAM=6, RR_FB_MD_Z80=7,
    RR_FB_SNES_RAM=8, RR_FB_SNES_SPC=9,
    RR_FB_NG_ROM=10, RR_FB_NG_RAM=11, RR_FB_NG_Z80=12, RR_FB_X68000=13,
    RR_FB_CPS1_ROM=14, RR_FB_CPS1_RAM=15, RR_FB_CPS1_Z80=16
};
void rr_feedback_start(int gameplay);
int rr_feedback_enabled(void);
int rr_feedback_toggle(void);
const char *rr_feedback_label(void);
int rr_feedback_pending(void);
void rr_feedback_finish(void);
void rr_feedback_note(unsigned kind, uint32_t address, uint32_t auxiliary,
                      const uint8_t *bytes, unsigned length);
#ifdef __cplusplus
}
#endif
#endif
