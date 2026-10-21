/* Board-level readiness for the private frontend. Original code, MIT. */
#include "x68k/fdd.h"
#include "x68k/fdc.h"
extern unsigned RR_FDD_MediaMask(void);
extern unsigned RR_FDD_BlinkMask(void);
unsigned rr_x68000_media_ready(void) {
    /* Physical presence is distinct from the three-frame ready delay. */
    return RR_FDD_MediaMask() | (RR_FDD_BlinkMask()<<8);
}
unsigned rr_x68000_media_activity(void) {
    return (FDD_IsReading?1u:0u)|(FDC_IsDataReady()?2u:0u);
}
