/* Request-driven main-bus arbitration. Both continuations yield to the host
 * thread; neither C stack belongs in a portable state. The main CPU yields
 * between nominal transactions and DMA waits. Prefetch/internal placement
 * and BR/BG/BGACK synchronizers are not a pin-accurate board model. */
#include "fiber_compat.h"
#include "md_bus_scheduler.h"
static fiber_t rr_z80_main, rr_z80_fiber;
static int rr_z80_busy, rr_z80_blocked, rr_z80_request, rr_z80_granted, rr_bus_scheduling;
static int rr_bus_main_split;
static int rr_z80_checkpoint,rr_z80_retiring,rr_local_ack,rr_local_request,rr_local_reset,rr_bus_control_event;
static int64_t rr_local_request_time,rr_local_ack_time;
bool machine_main_bus_split(void) { return rr_bus_main_split!=0; }
/* Line-relative signed clocks retain an old request across line/frame edges
 * without inheriting the legacy machine counter's 32-bit wrap. */
static int64_t rr_z80_time, rr_z80_limit, rr_z80_grant;
static uint64_t rr_bus_requests, rr_bus_wait_ticks, rr_bus_stolen_cycles;
bool rr_md_bus_busy(void) {
    return rr16_md_instruction_busy() || rr_z80_busy ||
        (g_machine.bus.z80_busreq && g_machine.bus.z80_reset_off && !rr_local_ack);
}
void rr_md_z80_bus_reset(void) {
    if(rr_z80_fiber)fiber_destroy(rr_z80_fiber);
    rr_z80_fiber=rr_z80_main=NULL;
    rr_z80_busy=rr_z80_blocked=rr_z80_request=rr_z80_granted=rr_bus_scheduling=0;
    rr_z80_time=rr_z80_limit=rr_z80_grant=0;
    rr_bus_main_split=0;
    rr_z80_checkpoint=rr_z80_retiring=rr_bus_control_event=0;
    /* Portable capture excludes a pending handshake/live continuation. A
     * stored BUSREQ therefore represents stable ownership on pointer rewire. */
    rr_local_request=rr_local_ack=g_machine.bus.z80_busreq;
    rr_local_reset=g_machine.bus.z80_reset_off;
    rr_local_request_time=rr_local_ack_time=0;
}
static int64_t rr_bus_align(int64_t time,unsigned divisor) {
    int64_t remainder=time%(int64_t)divisor;
    return remainder>0?time+divisor-remainder:time-remainder;
}
bool machine_z80_bus_acknowledged(void) {
    return g_machine.bus.z80_busreq && rr_local_ack &&
        rr_local_ack_time<=(int64_t)machine_vdp_phase();
}
void machine_z80_bus_control(void) {
    int request=g_machine.bus.z80_busreq,reset=g_machine.bus.z80_reset_off;
    if(request!=rr_local_request) {
        rr_local_request_time=machine_vdp_phase();rr_local_ack=0;
    }
    /* Held RESET has no live machine cycle to complete. Its stable ownership
     * is reconstructed after load; running-clock ACK uses the boundary path. */
    if(request && !reset) { rr_local_ack=1;rr_local_ack_time=machine_vdp_phase(); }
    if(!request)rr_local_ack=0;
    rr_local_request=request;rr_local_reset=reset;
    if(rr_bus_scheduling) { rr_bus_control_event=1;rr_md_cpu_control_yield(); }
}
void machine_z80_boundary(void) {
    if(!rr_bus_scheduling || !rr_z80_fiber || fiber_current()!=rr_z80_fiber)return;
    rr_z80_checkpoint=1;fiber_switch(rr_z80_main);rr_z80_checkpoint=0;
}
void machine_z80_instruction_boundary(void) {
    rr_z80_retiring=1;machine_z80_boundary();rr_z80_retiring=0;
}
void machine_z80_bus_released(void) {
    /* BUSREQ/reset can hold a live, already granted transaction for several
     * slices or frames. Its continuation must resume on a current Z80 edge,
     * never replay the elapsed pause as instructions/audio events in the past.
     * Nominal instruction cycles remain untouched; this is wall time only. */
    if(!rr_local_ack && rr_local_reset)return; /* Unacknowledged pulse. */
    int64_t release=rr_bus_align(machine_vdp_phase(),MASTER_PER_Z80);
    if(rr_z80_time<release)rr_z80_time=release;
    if(rr_z80_granted && rr_z80_grant<release)rr_z80_grant=release;
}
void machine_z80_bus_barrier(void) {
    /* A native guard is a peek, not an extra bus transaction. */
    if(!rr_z80_fiber || fiber_current()!=rr_z80_fiber)return;
    int waited=0;
    while(gvdp_dma_blocks_cpu(&g_machine.vdp)) {
        waited=1;
        rr_z80_blocked=1;fiber_switch(rr_z80_main);rr_z80_blocked=0;
    }
    if(waited && rr_z80_grant>rr_z80_time) {
        rr_bus_wait_ticks+=rr_z80_grant-rr_z80_time;rr_z80_time=rr_z80_grant;
        s_z80_off=(uint32_t)rr_z80_time;
    }
    if(waited)rr_z80_granted=0;
}
void machine_z80_bus_wait(void) {
    if(!rr_z80_fiber || fiber_current()!=rr_z80_fiber)return;
    /* A previous VDP wait in this same live instruction has already advanced
     * its stamp; consume that debt before timestamping another transaction. */
    rr_z80_time+=(uint64_t)rr_vdp_z80_wait*MASTER_PER_Z80;rr_vdp_z80_wait=0;
    ++rr_bus_requests;rr_z80_request=1;
    if(rr_bus_scheduling) {
        rr_z80_blocked=1;fiber_switch(rr_z80_main);rr_z80_blocked=0;
    } else {
        /* Isolated fixture/legacy slice: no running main-CPU scheduler. */
        machine_z80_bus_barrier();
        int64_t now=g_machine.vdp.rr_fifo.clock;
        if(now<rr_z80_time)now=rr_z80_time;
        rr_z80_grant=rr_bus_align(rr_bus_align(now,7)+28,15);
        glue_charge_68k_stall(4);rr_bus_stolen_cycles+=4;
    }
    rr_z80_request=rr_z80_granted=0;
    if(rr_z80_grant>rr_z80_time) {
        rr_bus_wait_ticks+=rr_z80_grant-rr_z80_time;
        rr_z80_time=rr_z80_grant;
        s_z80_off=(uint32_t)rr_z80_time;
    }
}
void machine_z80_cycles(unsigned cycles) {
    if(!rr_z80_fiber || fiber_current()!=rr_z80_fiber)return;
    /* Nominal cycles are now placed inside the instruction. Bus/VDP waits
     * remain additional wall time and must not be charged again at retirement. */
    rr_z80_time+=((uint64_t)cycles+rr_vdp_z80_wait)*MASTER_PER_Z80;
    rr_vdp_z80_wait=0;s_z80_off=(uint32_t)rr_z80_time;
}
static void rr_z80_run(void *unused) {
    (void)unused;
    for(;;) {
        if(rr_z80_time>=rr_z80_limit) { fiber_switch(rr_z80_main);continue; }
        machine_z80_boundary(); /* Before native guards and interrupt/fetch. */
        rr_vdp_z80_wait=0;
        s_z80_off=(uint32_t)rr_z80_time;
        rr_z80_busy=1;
        rr_md_z80_step(&g_machine.z80);
        rr_z80_busy=0;
    }
}
static void rr_z80_start(void) {
    if(rr_z80_fiber)return;
    rr_z80_main=fiber_convert_thread();
    rr_z80_fiber=fiber_create(256u*1024u,256u*1024u,rr_z80_run,NULL);
    if(!rr_z80_main || !rr_z80_fiber)abort();
}
static int rr_z80_prepare(GenesisMachine *m) {
    rr_vdp_z80_active=0;
    if(m->bus.z80_busreq!=rr_local_request || m->bus.z80_reset_off!=rr_local_reset)
        machine_z80_bus_control(); /* Isolated fixtures can change the pins. */
    if(!m->bus.z80_reset_off || (m->bus.z80_busreq && rr_local_ack))return 0;
    if(m->bus.z80_reset_pending) {
        int64_t release=rr_z80_time;
        rr_md_z80_bus_reset();z80_own_reset(&m->z80);
        rr_bus_scheduling=1;
        rr_z80_time=release;
        rr_md_z80_capture_driver();m->bus.z80_reset_pending=0;
    }
    rr_z80_start();rr_vdp_z80_active=1;return 1;
}
static void rr_z80_resume(void) {
    rr_vdp_z80_active=1;fiber_switch(rr_z80_fiber);rr_vdp_z80_active=0;
}
static void rr_bus_cpu_until(GenesisMachine *m,unsigned target,uint32_t before,
                             unsigned end_master,unsigned fraction) {
    /* Interior slices can pause a transaction. With no earlier bus request,
     * the final line budget lets the current instruction retire; its overrun
     * is carried into the next frame, preserving portable state boundaries.
     * A source DMA remains a hard ownership barrier even at frame end. */
    rr_bus_main_split=end_master<MASTER_PER_LINE;
    unsigned elapsed=g_audio_cycle_counter-before;
    while(elapsed<target) {
        if(gvdp_dma_blocks_cpu(&m->vdp)) {
            unsigned release=gvdp_dma_wait_until(&m->vdp,end_master);
            unsigned wait=gvdp_dma_blocks_cpu(&m->vdp)?target:(release+fraction+6)/7;
            if(wait>target)wait=target;
            if(wait>elapsed)glue_charge_68k_stall(wait-elapsed);
            elapsed=g_audio_cycle_counter-before;
            if(gvdp_dma_blocks_cpu(&m->vdp) || elapsed>=target)break;
            glue_own_vint_service_latched(&m->vdp);
            elapsed=g_audio_cycle_counter-before;
            if(elapsed>=target)break;
        }
        unsigned prior=elapsed;glue_run_game_chunk(target-elapsed);
        elapsed=g_audio_cycle_counter-before;
        if(rr_bus_control_event)break;
        if(elapsed==prior && !gvdp_dma_blocks_cpu(&m->vdp))break;
    }
}
static void rr_bus_slice(GenesisMachine *m,unsigned begin,unsigned end,
                          uint32_t before,unsigned fraction) {
    const int64_t base=0;
    unsigned target=(end+fraction)/7, start=(begin+fraction)/7;
    unsigned elapsed=g_audio_cycle_counter-before;
    if(elapsed<start)glue_charge_68k_stall(start-elapsed);
    gvdp_fifo_advance(&m->vdp,begin);
    rr_bus_scheduling=1;rr_z80_limit=base+end;
    int enabled=rr_z80_prepare(m);rr_vdp_z80_active=0;
    if(enabled && !rr_z80_busy && rr_z80_time<base+begin)rr_z80_time=rr_bus_align(base+begin,15);
rendezvous:
    for(;;) {
        rr_bus_control_event=0;
        /* A reset cancels its old C continuation on the host, never on the
         * sound fiber. Reinitialization is deferred until reset is released. */
        enabled=rr_z80_prepare(m);rr_vdp_z80_active=0;
        rr_z80_limit=base+end;
        if(!enabled) {
            rr_bus_cpu_until(m,target,before,end,fraction);
            if(rr_bus_control_event)continue;
            break;
        }
        if(rr_z80_checkpoint) {
            int64_t boundary=rr_z80_time;
            unsigned phase=boundary>(int64_t)begin?(unsigned)boundary:begin;
            unsigned deadline=(phase+fraction+6)/7;
            if(deadline>target)deadline=target;
            rr_bus_cpu_until(m,deadline,before,phase<end?phase:end,fraction);
            if(!m->bus.z80_reset_off || m->bus.z80_reset_pending)continue;
            if(m->bus.z80_busreq && rr_local_request_time<=boundary) {
                /* Request sampled at the completed machine cycle; ACK is
                 * visible on this nominal Z80 rising edge, not at the write. */
                rr_local_ack=1;rr_local_ack_time=boundary;
                continue;
            }
            if(boundary>=(int64_t)end && !rr_z80_retiring &&
               !(end==MASTER_PER_LINE && rr_z80_busy))break;
            rr_z80_resume();continue;
        }
        if(rr_z80_blocked) {
            if(rr_z80_granted) {
                if(rr_z80_grant>(int64_t)end)break;
                rr_z80_resume();continue;
            }
            int64_t request=rr_z80_time;
            if(request>=(int64_t)end)break;
            unsigned phase=request>(int64_t)begin?(unsigned)request:begin;
            unsigned deadline=(phase+fraction+6)/7;
            if(deadline>target)deadline=target;
            rr_bus_cpu_until(m,deadline,before,phase,fraction);
            if(!m->bus.z80_reset_off || m->bus.z80_reset_pending)continue;
            if(rr_bus_control_event)continue;
            if(gvdp_dma_blocks_cpu(&m->vdp)) {
                unsigned release=gvdp_dma_wait_until(&m->vdp,end);
                if(gvdp_dma_blocks_cpu(&m->vdp))break;
                phase=release; /* Last source fetch, not destination tail. */
            }
            unsigned cpu_phase=machine_vdp_phase();
            if(phase<cpu_phase)phase=cpu_phase;
            if(phase<m->vdp.rr_fifo.clock)phase=m->vdp.rr_fifo.clock;
            int64_t grant=rr_bus_align(phase+fraction,7)-fraction;
            int64_t release=rr_z80_request?rr_bus_align(grant+28,15):rr_bus_align(grant,15);
            unsigned cpu_release=(unsigned)((release+fraction+6)/7);
            elapsed=g_audio_cycle_counter-before;
            if(cpu_release>elapsed)glue_charge_68k_stall(cpu_release-elapsed);
            if(rr_z80_request)rr_bus_stolen_cycles+=4;
            rr_z80_grant=release;rr_z80_granted=1;
            if(release>(int64_t)end)break;
            /* BUSREQ cannot cut a WAIT-extended machine cycle in half. */
            rr_z80_resume();continue;
        }
        if(rr_z80_time<(int64_t)end) { rr_z80_resume();continue; }
        rr_bus_cpu_until(m,target,before,end,fraction);
        if(rr_bus_control_event)continue;
        break;
    }
    rr_vdp_z80_active=0;
    rr_bus_cpu_until(m,target,before,end,fraction);
    if(rr_bus_control_event)goto rendezvous;
    gvdp_fifo_advance(&m->vdp,end);
    if(rr16_md_gun_pending())glue_own_interrupt(2,&m->vdp);
    glue_own_vint_service_latched(&m->vdp);
    rr_bus_scheduling=0;
    m->z80_cycle_debt=rr_z80_time>base+end?(uint32_t)((rr_z80_time-base-end+14)/15):0;
}
