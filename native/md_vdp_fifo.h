#ifndef RR_MD_VDP_FIFO_H
#define RR_MD_VDP_FIFO_H
#include <stdint.h>
#include "md_timing.h"
/* Pointer-free guest state. Entries retain the command/address at acceptance;
 * VRAM low byte is committed first and survives a snapshot between slots. */
typedef struct RrMdVdpWrite {
    uint16_t address, value;
    uint8_t code, reserved[3];
} RrMdVdpWrite;
typedef struct RrMdVdpFifo {
    RrMdVdpWrite entries[4];
    uint32_t clock, head, count, half;
} RrMdVdpFifo;
/* Active-scan access facts: three tile slots then refresh in each group,
 * plus the sprite-gap and adjacent end-of-line slots. The phase origin is
 * the same V-counter edge as md_timing.h. No emulator implementation/table
 * is bundled. Blanked slots use nominal distributed bandwidth (167/205);
 * precise refresh/HSYNC phases in blanking still need qualification. */
static inline unsigned rr_md_fifo_next_slot(unsigned after, int h40, int blanked) {
    unsigned line=after/RR_MD_MASTER_PER_LINE, phase=after%RR_MD_MASTER_PER_LINE;
    unsigned best=RR_MD_MASTER_PER_LINE;
    if (blanked) {
        unsigned slots=h40?205u:167u;
        unsigned index=(uint64_t)phase*slots/RR_MD_MASTER_PER_LINE;
        do { best=(uint64_t)(++index)*RR_MD_MASTER_PER_LINE/slots; } while (best<=phase);
    } else {
        unsigned first=h40?352u:230u, second=h40?820u:510u;
        if (first>phase) best=first;
        if (second>phase && second<best) best=second;
        unsigned groups=h40?5u:4u;
        for (unsigned group=0; group<groups; ++group)
            for (unsigned slot=0; slot<3; ++slot) {
                unsigned at=(h40?820u:810u)+group*(h40?512u:640u)+slot*(h40?128u:160u);
                if (at>phase && at<best) best=at;
            }
        unsigned end=h40?3364u:3350u, last=h40?3380u:3370u;
        if(end>phase && end<best) best=end;
        if(last>phase && last<best) best=last;
        if(best==RR_MD_MASTER_PER_LINE) return (line+1)*RR_MD_MASTER_PER_LINE+first;
    }
    return line*RR_MD_MASTER_PER_LINE+best;
}
#endif
