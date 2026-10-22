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
static int rr_z80_checkpoint_advanced;
static int rr_bus_nested_active; /* only rr_bus_slice owns a main-CPU budget */
static int64_t rr_local_request_time,rr_local_ack_time;
bool machine_main_bus_split(void) { return rr_bus_main_split!=0; }
/* Line-relative signed clocks retain an old request across line/frame edges
 * without inheriting the legacy machine counter's 32-bit wrap. */
static int64_t rr_z80_time, rr_z80_limit, rr_z80_grant;
static uint32_t rr_bus_main_origin;
static unsigned rr_bus_begin,rr_bus_fraction;
/* A retirement, the next instruction guard and its first fetch can visit the
 * very same boundary. Once the scheduler has returned, repeating that visit
 * cannot advance either CPU. Invalidate on every actual resume/reset; never
 * reuse a checkpoint across a raster slice, bus grant, or local bus control. */
static int rr_z80_boundary_reusable;
static int64_t rr_z80_boundary_time;
#ifndef RR_MD_REPEAT_Z80_BOUNDARIES
#define RR_MD_REPEAT_Z80_BOUNDARIES 0
#endif
#ifndef RR_MD_HOST_ONLY_Z80_BOUNDARIES
#define RR_MD_HOST_ONLY_Z80_BOUNDARIES 0
#endif
static uint64_t rr_bus_requests, rr_bus_wait_ticks, rr_bus_stolen_cycles;
static void rr_bus_cpu_until(GenesisMachine *,unsigned,uint32_t,unsigned,unsigned);

/* Deferred private rendezvous (Retro-Recomp, MIT). A Z80 cycle on its own
 * RAM cannot observe the 68000, and the 68000 cannot observe it, unless the
 * 68000 touches Z80 RAM or bus/reset control. Such a rendezvous is queued with
 * its clock instead of running the 68000 at once. Before any shared cycle (YM,
 * bank, VDP/PSG, I/O), unnamed cycle, interpreter miss or host checkpoint, the
 * host pays the queued points in order: each keeps the arbiter's own deadline
 * and early-return test, in one 68000 run when no host event intervenes. If the
 * 68000 touches Z80 RAM or bus control while the Z80 is ahead, the Z80 is put
 * back on the exact point (instruction snapshot, RAM undo, replay) first. */
#ifndef RR_MD_LAZY_Z80
#define RR_MD_LAZY_Z80 1
#endif
#define RR_LAZY_POINTS 256u
#define RR_LAZY_UNDO 1024u
typedef struct { int64_t time; unsigned instruction, call; } RrLazyPoint;
typedef struct {
    z80 cpu; int64_t time; uint32_t z80_off, vdp_wait;
    int64_t boundary_time; int boundary_reusable;
    unsigned undo, point; RrMdZ80Evidence evidence;
} RrLazyInstruction;
static RrLazyPoint rr_lazy_point[RR_LAZY_POINTS];
static RrLazyInstruction rr_lazy_instruction[RR_LAZY_POINTS];
static struct { uint16_t offset; uint8_t value; } rr_lazy_undo[RR_LAZY_UNDO];
static unsigned rr_lazy_points, rr_lazy_instructions, rr_lazy_undos, rr_lazy_cursor;
static unsigned rr_lazy_calls;       /* rendezvous so far in the open instruction */
static int rr_lazy_open;             /* this Z80 instruction may still queue points */
static int rr_lazy_flush_wanted;     /* the sound CPU waits for the host to pay */
static int rr_lazy_flushing, rr_lazy_restored, rr_lazy_replaying;
static unsigned rr_lazy_replay_left;
static int64_t rr_lazy_restored_time, rr_lazy_after_time;
static fiber_t rr_lazy_return;
/* A restore replays on a fresh continuation: the previous one may be the
 * live caller of the 68000 run. It is recycled once it has handed back. */
static fiber_t rr_z80_spare, rr_lazy_retired;
/* A cycle past the slice end with points queued: the arbiter can only take
 * its host checkpoint there, whose catch-up the host merges with the points.
 * A retirement past the end may instead return, depending on where the points
 * leave the 68000: it pays them under the sound CPU and asks the arbiter. */
static int rr_lazy_beyond_pending, rr_lazy_beyond_return;
static void rr_lazy_flush(GenesisMachine *m,unsigned final_target);
uint64_t rr_md_lazy_points, rr_md_lazy_flushes, rr_md_lazy_rollbacks;
/* Diagnostics only: a fixture drops Z80 cycles a replay will redo. */
void (*rr_md_lazy_rollback_trace)(int64_t time);
extern uint32_t rr_md_cpu_transaction;
int rr_md_cpu_lazy_safe(void);
void rr_md_cpu_budget_until(uint32_t counter);
static void rr_z80_run(void *unused);
static void rr_z80_rendezvous(void);
static int rr_lazy_eligible(void) {
    return RR_MD_LAZY_Z80 && !RR_MD_REPEAT_Z80_BOUNDARIES && !RR_MD_HOST_ONLY_Z80_BOUNDARIES &&
        rr_bus_scheduling && rr_bus_nested_active && rr_z80_time<rr_z80_limit &&
        g_machine.bus.z80_reset_off && !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending;
}
static unsigned rr_lazy_deadline(int64_t time,unsigned *phase_out) {
    /* The nested arbiter's phase and deadline for a checkpoint at this clock. */
    unsigned phase=time>(int64_t)rr_bus_begin?(unsigned)time:rr_bus_begin;
    unsigned deadline=(phase+rr_bus_fraction+6u)/7u;
    unsigned target=((unsigned)rr_z80_limit+rr_bus_fraction)/7u;
    if(deadline>target)deadline=target;
    if(phase_out)*phase_out=phase;
    return deadline;
}
static void rr_lazy_close(void) {
    /* No later restore may enter this instruction (a shared cycle happened,
     * or the host changed the Z80, its clock or its bus ownership). */
    if(rr_lazy_points)return;
    rr_lazy_undos=rr_lazy_instructions=0;rr_lazy_open=0;
}
static void rr_lazy_count(void) {
    if(rr_lazy_instructions || rr_lazy_replaying)++rr_lazy_calls;
}
static void rr_lazy_settle(void) {
    /* Pay every queued point before a cycle the 68000 can observe. Like the
     * nested arbiter, the 68000 runs under this sound continuation. */
    if(rr_lazy_points) {
        ++rr_md_lazy_flushes;
        rr_lazy_flush(&g_machine,0);
        if(rr_lazy_retired==fiber_current()) {
            /* A 68000 contact put the Z80 on a replayed continuation. */
            for(;;)fiber_switch(rr_z80_main);
        }
        /* Paid without a 68000 contact: the arbiter last returned here. */
        rr_z80_boundary_time=rr_lazy_after_time;rr_z80_boundary_reusable=1;
    }
    rr_lazy_points=rr_lazy_undos=rr_lazy_instructions=0;rr_lazy_open=0;
}
static void rr_lazy_begin_instruction(void) {
    rr_lazy_open=0;
    if(!rr_lazy_replaying && !rr_lazy_eligible())return;
    if(rr_lazy_instructions==RR_LAZY_POINTS || rr_lazy_undos+64u>RR_LAZY_UNDO)rr_lazy_settle();
    /* Without queued points, earlier instructions are committed. */
    if(!rr_lazy_points)rr_lazy_undos=rr_lazy_instructions=0;
    rr_lazy_calls=0;
    RrLazyInstruction *s=&rr_lazy_instruction[rr_lazy_instructions++];
    s->cpu=g_machine.z80;s->time=rr_z80_time;s->z80_off=s_z80_off;s->vdp_wait=rr_vdp_z80_wait;
    s->boundary_time=rr_z80_boundary_time;s->boundary_reusable=rr_z80_boundary_reusable;
    s->undo=rr_lazy_undos;s->point=rr_lazy_points;rr_md_z80_evidence_save(&s->evidence);
    rr_lazy_open=1;
}
static int rr_lazy_private(void) {
    /* Returns 1 when this rendezvous needs no 68000 run now. */
    if(rr_lazy_replaying) {
        if(rr_lazy_replay_left) {
            --rr_lazy_replay_left;rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;return 1;
        }
        /* The restored point: the 68000 is inside its catch-up for it. */
        rr_lazy_replaying=0;rr_lazy_open=0;
        fiber_switch(rr_lazy_return);
        /* The host resumes us after that catch-up: the nested arbiter's checks. */
        rr_vdp_z80_active=1;
        if(g_machine.bus.z80_reset_off && !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending) {
            rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;return 1;
        }
        rr_z80_checkpoint_advanced=1;
        rr_z80_checkpoint=1;fiber_switch(rr_z80_main);rr_z80_checkpoint=0;
        rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;
        return 1;
    }
    if(!rr_lazy_open || !rr_lazy_eligible())return 0;
    if(rr_z80_boundary_reusable && rr_z80_time==rr_z80_boundary_time)return 1;
    if(rr_lazy_points==RR_LAZY_POINTS)return 0;
    RrLazyPoint *point=&rr_lazy_point[rr_lazy_points++];
    point->time=rr_z80_time;point->instruction=rr_lazy_instructions-1u;point->call=rr_lazy_calls-1u;
    ++rr_md_lazy_points;
    rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;
    return 1;
}
static void rr_lazy_restore(unsigned index) {
    /* Put the Z80 exactly on queued point `index`, inside its rendezvous. */
    const RrLazyPoint *point=&rr_lazy_point[index];
    const RrLazyInstruction *s=&rr_lazy_instruction[point->instruction];
    unsigned skip=point->call;
    ++rr_md_lazy_rollbacks;
    while(rr_lazy_undos>s->undo) {
        --rr_lazy_undos;g_machine.bus.z80_ram[rr_lazy_undo[rr_lazy_undos].offset]=rr_lazy_undo[rr_lazy_undos].value;
    }
    if(rr_md_lazy_rollback_trace)rr_md_lazy_rollback_trace(s->time);
    g_machine.z80=s->cpu;rr_z80_time=s->time;s_z80_off=s->z80_off;rr_vdp_z80_wait=s->vdp_wait;
    rr_z80_boundary_time=s->boundary_time;rr_z80_boundary_reusable=s->boundary_reusable;
    rr_md_z80_evidence_load(&s->evidence);
    rr_z80_busy=rr_z80_retiring=rr_z80_checkpoint=rr_z80_checkpoint_advanced=0;
    rr_lazy_restored_time=point->time;rr_lazy_restored=1;
    rr_lazy_points=rr_lazy_undos=rr_lazy_instructions=0;
    rr_lazy_replaying=1;rr_lazy_replay_left=skip;rr_lazy_calls=0;rr_lazy_return=fiber_current();
    /* The previous continuation belongs to the abandoned future. */
    fiber_t next=rr_z80_spare;rr_z80_spare=NULL;
    if(next) { if(fiber_reset(next,rr_z80_run,NULL)!=0)abort(); }
    else next=fiber_create(256u*1024u,256u*1024u,rr_z80_run,NULL);
    if(!next)abort();
    rr_lazy_retired=rr_z80_fiber;rr_z80_fiber=next;
    rr_vdp_z80_active=1;fiber_switch(rr_z80_fiber);rr_vdp_z80_active=0;
    rr_md_cpu_budget_until(rr_bus_main_origin+rr_lazy_deadline(rr_lazy_restored_time,NULL));
}
static int rr_lazy_beyond(void) {
    /* Returns 1 when the host served this rendezvous past the slice end. */
    if(!rr_lazy_points || rr_z80_retiring || !rr_bus_nested_active || rr_z80_time<rr_z80_limit ||
       !g_machine.bus.z80_reset_off || g_machine.bus.z80_busreq || g_machine.bus.z80_reset_pending)return 0;
    rr_lazy_beyond_pending=1;fiber_switch(rr_z80_main);
    /* Paid by the host; this instruction stays restorable unless closed. */
    rr_lazy_points=0;
    if(rr_lazy_beyond_return)return 1;
    /* Resumed after the host served it as the arbiter's checkpoint. */
    rr_z80_checkpoint=0;rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;
    return 1;
}
static int rr_lazy_arbiter_returns(void) {
    /* The arbiter's early return for the current point (no nested run past
     * the slice end): an exact revisit, or the 68000 already there. */
    if(!((rr_z80_time<rr_z80_limit || rr_z80_retiring) && g_machine.bus.z80_reset_off &&
         !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending))return 0;
    if(rr_z80_boundary_reusable && rr_z80_time==rr_z80_boundary_time)return 1;
    int64_t phase=rr_z80_time>(int64_t)rr_bus_begin?rr_z80_time:rr_bus_begin;
    if(rr_z80_retiring && phase>rr_z80_limit)phase=rr_z80_limit;
    uint32_t elapsed=g_audio_cycle_counter-rr_bus_main_origin;
    return (uint64_t)elapsed*7u>=(uint64_t)(phase+rr_bus_fraction);
}
void machine_z80_irq_change(void) {
    /* The VDP's Z80 interrupt line: a 68000-clocked event during a payment
     * puts the Z80 on its point first; elsewhere it ends restorability. */
    if(rr_lazy_flushing)machine_z80_main_access();
    else rr_lazy_close();
}
void machine_z80_main_access(void) {
    /* The 68000 is about to touch Z80 RAM or bus/reset control. */
    if(!rr_lazy_flushing || rr_lazy_restored)return;
    uint32_t elapsed=rr_md_cpu_transaction-rr_bus_main_origin;
    unsigned index=rr_lazy_cursor;
    while(index<rr_lazy_points && rr_lazy_deadline(rr_lazy_point[index].time,NULL)<=elapsed)++index;
    if(index<rr_lazy_points)rr_lazy_restore(index);
}
static void rr_lazy_flush(GenesisMachine *m,unsigned final_target) {
    /* The nested arbiter's catch-up for each queued point, in order. At the
     * slice end the host's own final catch-up (same bus split) may follow in
     * the same run; nonzero final_target is that deadline. */
    rr_lazy_flushing=1;rr_lazy_restored=0;rr_lazy_cursor=0;
    rr_lazy_after_time=rr_lazy_point[rr_lazy_points-1u].time;
    while(!rr_lazy_restored) {
        uint32_t elapsed=g_audio_cycle_counter-rr_bus_main_origin;
        unsigned phase=0,deadline=0;
        while(rr_lazy_cursor<rr_lazy_points) {
            deadline=rr_lazy_deadline(rr_lazy_point[rr_lazy_cursor].time,&phase);
            if((uint64_t)elapsed*7u<(uint64_t)(phase+rr_bus_fraction))break;
            ++rr_lazy_cursor; /* The 68000 is already there. */
        }
        if(rr_lazy_cursor==rr_lazy_points)break;
        rr_bus_control_event=0;rr_vdp_z80_active=0;
        if(elapsed>=deadline) {
            /* Deadline capped at the slice: that call runs nothing. */
            rr_bus_main_split=phase<MASTER_PER_LINE;++rr_lazy_cursor;
        } else if(rr_md_cpu_lazy_safe() && !gvdp_dma_blocks_cpu(&m->vdp)) {
            /* No host event between the queued points: one run to the last.
             * A DMA wait, a 68000 contact or a stall returns here first. */
            unsigned last=final_target?final_target:rr_lazy_deadline(rr_lazy_point[rr_lazy_points-1u].time,NULL);
            rr_bus_main_split=phase<MASTER_PER_LINE;
            glue_run_game_chunk(last-elapsed);
            if(!rr_lazy_restored && g_audio_cycle_counter-rr_bus_main_origin==elapsed &&
               !gvdp_dma_blocks_cpu(&m->vdp))rr_lazy_cursor=rr_lazy_points; /* parked: no call can run it */
        } else {
            rr_bus_cpu_until(m,deadline,rr_bus_main_origin,phase,rr_bus_fraction);
        }
        rr_vdp_z80_active=1;
    }
    if(rr_lazy_restored && !rr_bus_control_event) {
        /* Finish the restored point's catch-up as the arbiter's loop would. */
        unsigned phase;unsigned deadline=rr_lazy_deadline(rr_lazy_restored_time,&phase);
        if(g_audio_cycle_counter-rr_bus_main_origin<deadline) {
            rr_vdp_z80_active=0;
            rr_bus_cpu_until(m,deadline,rr_bus_main_origin,phase,rr_bus_fraction);
            rr_vdp_z80_active=1;
        }
    }
    if(!rr_lazy_restored)rr_lazy_points=0;
    rr_lazy_flushing=0;
}
bool rr_md_bus_busy(void) {
    return rr16_md_instruction_busy() || rr_z80_busy ||
        (g_machine.bus.z80_busreq && g_machine.bus.z80_reset_off && !rr_local_ack);
}
void rr_md_z80_bus_reset(void) {
    if(rr_z80_fiber)fiber_destroy(rr_z80_fiber);
    rr_z80_fiber=rr_z80_main=NULL;
    rr_z80_busy=rr_z80_blocked=rr_z80_request=rr_z80_granted=rr_bus_scheduling=0;
    rr_z80_time=rr_z80_limit=rr_z80_grant=0;
    rr_bus_main_origin=rr_bus_begin=rr_bus_fraction=0;
    rr_z80_boundary_reusable=0;
    rr_bus_main_split=0;
    rr_z80_checkpoint=rr_z80_retiring=rr_bus_control_event=0;
    rr_z80_checkpoint_advanced=0;
    rr_bus_nested_active=0;
    rr_lazy_points=rr_lazy_undos=rr_lazy_instructions=rr_lazy_cursor=0;
    rr_lazy_open=rr_lazy_flush_wanted=rr_lazy_flushing=rr_lazy_restored=rr_lazy_replaying=0;
    if(rr_z80_spare)fiber_destroy(rr_z80_spare);
    if(rr_lazy_retired)fiber_destroy(rr_lazy_retired);
    rr_z80_spare=rr_lazy_retired=NULL;
    rr_lazy_beyond_pending=rr_lazy_beyond_return=0;rr_lazy_calls=0;
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
    machine_z80_main_access();rr_lazy_close();
    rr_z80_boundary_reusable=0;
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
static void rr_z80_rendezvous(void) {
    if(!rr_bus_scheduling || !rr_z80_fiber || fiber_current()!=rr_z80_fiber)return;
    if(!RR_MD_REPEAT_Z80_BOUNDARIES && (rr_z80_time<rr_z80_limit || rr_z80_retiring) &&
       g_machine.bus.z80_reset_off && !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending) {
        if(rr_z80_boundary_reusable && rr_z80_time==rr_z80_boundary_time)return;
        /* A completed, indivisible 68000 transaction can already be beyond
         * this Z80 checkpoint. The host would run no CPU work before resuming
         * us. Keep all real transactions and WAIT/control/end-slice yields. */
        int64_t phase=rr_z80_time>(int64_t)rr_bus_begin?rr_z80_time:rr_bus_begin;
        /* Retirement beyond the slice is resumed immediately by the host
         * once the main CPU has paid that slice. The next instruction still
         * hits rr_z80_run's limit and returns to the host. Do not apply this
         * to a fetch/WAIT boundary, where the suspended access must stay live. */
        if(rr_z80_retiring && phase>rr_z80_limit)phase=rr_z80_limit;
        uint32_t elapsed=g_audio_cycle_counter-rr_bus_main_origin;
        if((uint64_t)elapsed*7u>=(uint64_t)(phase+rr_bus_fraction))return;
    }
    if(!RR_MD_REPEAT_Z80_BOUNDARIES && !RR_MD_HOST_ONLY_Z80_BOUNDARIES && rr_bus_nested_active && rr_z80_time<rr_z80_limit &&
       g_machine.bus.z80_reset_off && !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending) {
        /* The host checkpoint would run this very same 68000 budget and
         * immediately resume us. Call it on the current continuation instead:
         * minicoro can return the main CPU to its live Z80 caller. No clocks,
         * transactions, interrupt polls or WAIT phases are batched away. */
        unsigned phase=rr_z80_time>(int64_t)rr_bus_begin?(unsigned)rr_z80_time:rr_bus_begin;
        unsigned deadline=(phase+rr_bus_fraction+6u)/7u;
        unsigned target=((unsigned)rr_z80_limit+rr_bus_fraction)/7u;
        if(deadline>target)deadline=target;
        rr_bus_control_event=0;rr_vdp_z80_active=0;
        rr_bus_cpu_until(&g_machine,deadline,rr_bus_main_origin,phase,rr_bus_fraction);
        rr_vdp_z80_active=1;
        if(g_machine.bus.z80_reset_off && !g_machine.bus.z80_busreq && !g_machine.bus.z80_reset_pending) {
            rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;return;
        }
        /* A control change still returns to the host, which owns reset,
         * destruction and ACK. It must not execute this budget a second time. */
        rr_z80_checkpoint_advanced=1;
    }
    rr_z80_checkpoint=1;fiber_switch(rr_z80_main);rr_z80_checkpoint=0;
    rr_z80_boundary_time=rr_z80_time;rr_z80_boundary_reusable=1;
}
static int rr_z80_on_fiber(void) {
    return rr_bus_scheduling && rr_z80_fiber && fiber_current()==rr_z80_fiber;
}
void machine_z80_boundary(void) {
    /* I/O and other cycles without a Z80 RAM address. */
    if(!rr_z80_on_fiber())return;
    rr_lazy_count();
    if(!rr_lazy_beyond()) { rr_lazy_settle();rr_z80_rendezvous(); }
    rr_lazy_close();
}
void machine_z80_access(uint16_t address) {
    if(!rr_z80_on_fiber())return;
    rr_lazy_count();
    if(address<0x4000u) {
        if(rr_lazy_private() || rr_lazy_beyond())return;
        rr_lazy_settle();rr_z80_rendezvous();return;
    }
    if(!rr_lazy_beyond()) { rr_lazy_settle();rr_z80_rendezvous(); }
    rr_lazy_close();
}
void machine_z80_write(uint16_t address) {
    machine_z80_access(address);
    if(address>=0x4000u || !rr_lazy_instructions || !rr_z80_on_fiber())return;
    if(rr_lazy_undos==RR_LAZY_UNDO) { rr_lazy_settle();return; }
    unsigned offset=address&0x1fffu;
    rr_lazy_undo[rr_lazy_undos].offset=(uint16_t)offset;
    rr_lazy_undo[rr_lazy_undos++].value=g_machine.bus.z80_ram[offset];
}
void machine_z80_fallback(void) {
    /* Learning an interpreter miss is not replayable. */
    if(rr_z80_on_fiber())rr_lazy_settle();
}
void machine_z80_instruction_boundary(void) {
    rr_z80_retiring=1;
    if(rr_z80_on_fiber()) {
        rr_lazy_count();
        if(!rr_lazy_private()) { rr_lazy_settle();rr_z80_rendezvous(); }
    }
    rr_z80_retiring=0;
}
void machine_z80_bus_released(void) {
    machine_z80_main_access();rr_lazy_close();
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
    if(rr_bus_scheduling)rr_lazy_settle();
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
    if(rr_bus_scheduling)rr_lazy_settle();
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
        /* Points still queued here are paid by the host (rr_z80_resume). */
        if(rr_z80_time>=rr_z80_limit) { rr_lazy_open=0;fiber_switch(rr_z80_main);continue; }
        /* Before native guards and interrupt/fetch. */
        if(rr_z80_on_fiber()) {
            rr_lazy_begin_instruction();rr_lazy_count();
            if(!rr_lazy_private()) { rr_lazy_settle();rr_z80_rendezvous(); }
        }
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
static void rr_lazy_recycle(void) {
    if(!rr_lazy_retired)return;
    if(rr_z80_spare)fiber_destroy(rr_z80_spare);
    rr_z80_spare=rr_lazy_retired;rr_lazy_retired=NULL;
}
static void rr_z80_resume(void) {
    for(;;) {
        rr_z80_boundary_reusable=0;
        rr_vdp_z80_active=1;fiber_switch(rr_z80_fiber);rr_vdp_z80_active=0;
        if(rr_lazy_retired) { rr_lazy_recycle();continue; }
        if(rr_lazy_beyond_pending) {
            rr_lazy_beyond_pending=0;
            unsigned final_target=rr_z80_limit<MASTER_PER_LINE?((unsigned)rr_z80_limit+rr_bus_fraction)/7u:0u;
            ++rr_md_lazy_flushes;rr_lazy_flush(&g_machine,final_target);
            if(rr_lazy_restored) { rr_lazy_recycle();continue; }
            rr_lazy_beyond_return=rr_lazy_arbiter_returns();
            if(rr_lazy_beyond_return)continue;
            /* The arbiter's host checkpoint; rr_bus_slice serves it next. */
            rr_z80_checkpoint=1;break;
        }
        if(!rr_lazy_points)break;
        /* The sound CPU stopped at the slice end with points still queued. */
        unsigned final_target=0;
        if(rr_z80_time>=rr_z80_limit && !rr_z80_checkpoint && !rr_z80_blocked &&
           rr_z80_limit<MASTER_PER_LINE)
            final_target=((unsigned)rr_z80_limit+rr_bus_fraction)/7u;
        ++rr_md_lazy_flushes;rr_lazy_flush(&g_machine,final_target);
        if(!rr_lazy_restored)break;
        rr_lazy_recycle();
    }
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
    rr_bus_main_origin=before;rr_bus_begin=begin;rr_bus_fraction=fraction;
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
        rr_bus_nested_active=1;
        rr_bus_main_origin=before;rr_bus_begin=begin;rr_bus_fraction=fraction;
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
            if(!rr_z80_checkpoint_advanced)
                rr_bus_cpu_until(m,deadline,before,phase<end?phase:end,fraction);
            rr_z80_checkpoint_advanced=0;
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
    rr_bus_nested_active=0;
    m->z80_cycle_debt=rr_z80_time>base+end?(uint32_t)((rr_z80_time-base-end+14)/15):0;
}
