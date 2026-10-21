/* Original Retro-Recomp private session state bridge, MIT. */
#include "probe.h"
#include "common.h"
#include "hardware_clock.h"
#include "winx68k.h"
#include <libretro.h>
#include <stdint.h>
#include <string.h>
#ifdef RR_X68000_EXTENDED_CPU_STATE
#include "m68kcpu.h"
#endif
extern uint16_t *videoBuffer;
RR_X68K_EXPORT const char *rr_x68k_state_compatibility(void) { return RR_X68K_STATE_ABI; }
RR_X68K_EXPORT const void *rr_x68k_framebuffer(void) { return videoBuffer; }
int RR_HostClock_StateAction(StateMem *sm,int load,int data_only)
{
    uint64_t ticks[8];
    int ret;
    SFORMAT fields[] = {SFARRAY64(ticks,8),SFARRAY16(videoBuffer,800*600),
#ifdef RR_X68000_EXTENDED_CPU_STATE
        /* A fresh process still has its power-on reset penalty. Retaining it
         * after F9 changes CPU slice boundaries and advances an active floppy
         * DMA by a byte, even when frame-end CPU registers look identical. */
        SFVAR(m68ki_cpu.reset_cycles),
        SFVAR(m68ki_cpu.ppc),SFVAR(m68ki_cpu.ir),
        SFVAR(m68ki_cpu.pref_addr),SFVAR(m68ki_cpu.pref_data),
        SFVAR(m68ki_cpu.instr_mode),SFVAR(m68ki_cpu.run_mode),
        SFVAR(m68ki_cpu.virq_state),SFVAR(m68ki_cpu.nmi_pending),
#endif
        SFEND};
    rr_x68k_hardware_snapshot(ticks);
    ret=PX68KSS_StateAction(sm,load,data_only,fields,"RR_HOST_CLOCK_VIDEO",false);
    if(ret && load) rr_x68k_hardware_restore(ticks);
    return ret;
}
