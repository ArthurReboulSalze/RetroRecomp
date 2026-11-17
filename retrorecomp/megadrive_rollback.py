"""Multiplayer rollback for the Mega Drive: the in-process snapshot of the rollback tier and of the host's F8 / F9.

The snapshot (`rr16_md_snap_*`, the contract in `native/hostkit/hostkit.h`) lives in memory, in one process: it is taken
after a frame, loaded on a correction and never written to a file or sent. A frame can end with the 68000 suspended inside
an instruction (a bus or DMA wait), with the sound CPU suspended inside one of its own, or with a bus request not yet
granted: a quick state refuses those frame ends, a rollback cannot. So the snapshot keeps the two live continuations (the
fibers' stacks, raw) and every static a suspended instruction reads when it resumes, raw too: host pointers stay valid
because nothing they point to moves in a process (the fibers are kept for its whole life, below).

Everything is added to the private copies of the runtime a game build compiles, by this module alone: the files that fix
the Mega Drive quick-state key (`console16_state.state_layout_files`) are not touched, and a quick state keeps its
portable form (`native/md_portable_state.inc`). Diagnostic counters and host-side state (window, sound device, filters)
are left out. The determinism probe is `native/md_rollback_checks.c` (`tools/megadrive_rollback_selftest.py`).
"""
from .core import ConversionError


def _replace(source: str, old: str, new: str, what: str) -> str:
    if source.count(old) != 1:
        raise ConversionError(f'Pinned {what} changed; Mega Drive rollback adaptation refused.')
    return source.replace(old, new)


# The glue's own statics outside the upstream sections (megadrive_bus.glue and console16_state.md_glue add most; the
# scheduler's host fiber is upstream's and may be the sound CPU's while a nested 68000 run is suspended), then the
# snapshot itself, assembled here because the glue sees the game fiber and the upstream sections.
GLUE_LIVE = r'''
#if RR_MD_STEP_AOT
/* Multiplayer rollback (retrorecomp/megadrive_rollback.py): the in-process snapshot of hostkit.h's snap_*. */
#include "md_prefetch.h"
#include "md_ym_timers.h"
#include "md_cart.h"
#include "md_z80_native.h"
#include "sim_step.h"
#define RR_MD_GLUE_LIVE(X) X(rr_step_running) X(rr_portable_resume) X(rr_deferred_yield) X(rr_cpu_bus_cycles) \
    X(rr_cpu_bus_locked) X(rr_cpu_bus_pc) X(rr_md_cpu_transaction) X(s_main_fiber)
#define RR_MD_GLUE_SIZE(name) sizeof(name) +
extern RrMdPrefetch rr_md_prefetch;
extern uint32_t rr_md_cpu_stopped;
extern size_t rr_md_interp_live_size(void);
extern size_t rr_md_interp_live_save(void *data, size_t capacity);
extern int rr_md_interp_live_load(const void *data, size_t size);
extern size_t rr_md_bus_live_bound(void);
extern size_t rr_md_bus_live_save(void *data, size_t capacity);
extern int rr_md_bus_live_load(const void *data, size_t size);
extern size_t rr_md_fm_snap_bound(void);
extern size_t rr_md_fm_snap_save(void *dst, size_t cap);
extern int rr_md_fm_snap_load(const void *src, size_t len);
extern size_t psg_rb_save(void *dst, size_t cap);
extern int psg_rb_load(const void *src, size_t len);
extern size_t audio_event_rb_save(void *dst, size_t cap);
extern int audio_event_rb_load(const void *src, size_t len);
extern size_t rr16_gun_state_save(void *data, size_t capacity);
extern bool rr16_gun_state_load(const void *data, size_t size);
extern void rr16_md_instruction(bool active);
extern bool rr16_md_instruction_busy(void);
/* The game fiber's live stack (its header and registers included), the PSG's undrained samples and the queued sound
 * events are bounded: a frame ends far below these (the probe reports the largest seen), and a frame that does not fails
 * its save, which the session reports, instead of writing past its slot. */
#define RR_MD_SNAP_GAME_STACK (64u * 1024u)
#define RR_MD_SNAP_PSG (20u * 1024u)
#define RR_MD_SNAP_EVENTS 4096u
enum { RR_MD_SNAP_EXEC, RR_MD_SNAP_CPU, RR_MD_SNAP_SCHED, RR_MD_SNAP_RAM, RR_MD_SNAP_BUS, RR_MD_SNAP_VDP,
       RR_MD_SNAP_FM, RR_MD_SNAP_PSG_PART, RR_MD_SNAP_EVQ, RR_MD_SNAP_INPUT, RR_MD_SNAP_GLUE, RR_MD_SNAP_INTERP,
       RR_MD_SNAP_Z80, RR_MD_SNAP_YM, RR_MD_SNAP_GUN, RR_MD_SNAP_CART, RR_MD_SNAP_PARTS };
typedef struct { M68KState cpu; uint32_t stopped; RrMdPrefetch prefetch; } RrMdSnapCpu;
typedef struct { uint32_t pending_stall; int32_t unlimited_sprites; } RrMdSnapVdp;
typedef struct { GenesisSimInput in; uint32_t ticks; } RrMdSnapInput;
size_t rr16_md_snap_peak_exec, rr16_md_snap_peak_events;   /* the largest parts seen, for the probe's report */
static size_t rr_md_glue_live_size(void) { return RR_MD_GLUE_LIVE(RR_MD_GLUE_SIZE) 0; }
static size_t rr_md_snap_part_bound(unsigned part) {
    switch (part) {
    case RR_MD_SNAP_EXEC: return 12u + RR_MD_SNAP_GAME_STACK;
    case RR_MD_SNAP_CPU: return sizeof(RrMdSnapCpu);
    case RR_MD_SNAP_SCHED: return glue_rb_sched_save(NULL, 0);
    case RR_MD_SNAP_RAM: return sizeof g_ram;
    case RR_MD_SNAP_BUS: return rr_md_bus_live_bound();
    case RR_MD_SNAP_VDP: return sizeof(RrMdSnapVdp);
    case RR_MD_SNAP_FM: return rr_md_fm_snap_bound();
    case RR_MD_SNAP_PSG_PART: return RR_MD_SNAP_PSG;
    case RR_MD_SNAP_EVQ: return 4u + (size_t)RR_MD_SNAP_EVENTS * 8u;
    case RR_MD_SNAP_INPUT: return sizeof(RrMdSnapInput);
    case RR_MD_SNAP_GLUE: return rr_md_glue_live_size();
    case RR_MD_SNAP_INTERP: return rr_md_interp_live_size();
    case RR_MD_SNAP_Z80: return sizeof(RrMdZ80Evidence);
    case RR_MD_SNAP_YM: return sizeof(RrMdYmTimers);
    case RR_MD_SNAP_GUN: return rr16_gun_state_save(NULL, 0) + 1u;
    case RR_MD_SNAP_CART: return sizeof(RrMdCartState);
    }
    return 0;
}
size_t rr16_md_snap_bound(void) {
    static size_t bound;
    if (!bound) {
        size_t n = 8;
        for (unsigned part = 0; part < RR_MD_SNAP_PARTS; ++part) n += 4 + rr_md_snap_part_bound(part);
        bound = n;
    }
    return bound;
}
static size_t rr_md_snap_part_save(unsigned part, uint8_t *o, size_t cap) {
    switch (part) {
    case RR_MD_SNAP_EXEC: {
        size_t n = glue_rb_exec_save(NULL, 0);
        if (n > cap) return 0;
        if (n > rr16_md_snap_peak_exec) rr16_md_snap_peak_exec = n;
        return glue_rb_exec_save(o, n) == n ? n : 0;
    }
    case RR_MD_SNAP_CPU: {
        RrMdSnapCpu c; memset(&c, 0, sizeof c);
        c.cpu = g_cpu; c.stopped = rr_md_cpu_stopped; c.prefetch = rr_md_prefetch;
        memcpy(o, &c, sizeof c); return sizeof c;
    }
    case RR_MD_SNAP_SCHED: return glue_rb_sched_save(o, cap);
    case RR_MD_SNAP_RAM: memcpy(o, g_ram, sizeof g_ram); return sizeof g_ram;
    case RR_MD_SNAP_BUS: return rr_md_bus_live_save(o, cap);
    case RR_MD_SNAP_VDP: {
        RrMdSnapVdp v; memset(&v, 0, sizeof v);
        v.pending_stall = gvdp_rb_pending_stall(); v.unlimited_sprites = gvdp_unlimited_sprites();
        memcpy(o, &v, sizeof v); return sizeof v;
    }
    case RR_MD_SNAP_FM: return rr_md_fm_snap_save(o, cap);
    case RR_MD_SNAP_PSG_PART: { size_t n = psg_rb_save(NULL, 0); return n <= cap ? psg_rb_save(o, n) : 0; }
    case RR_MD_SNAP_EVQ: {
        size_t n = audio_event_rb_save(NULL, 0);
        if (n > cap) return 0;
        if (n > rr16_md_snap_peak_events) rr16_md_snap_peak_events = n;
        return audio_event_rb_save(o, n);
    }
    case RR_MD_SNAP_INPUT: {
        RrMdSnapInput in; memset(&in, 0, sizeof in);
        in.in = *genesis_sim_input(); in.ticks = genesis_sim_tick_count();
        memcpy(o, &in, sizeof in); return sizeof in;
    }
    case RR_MD_SNAP_GLUE: {
#define RR_MD_GLUE_PUT(name) memcpy(o, &(name), sizeof(name)); o += sizeof(name);
        RR_MD_GLUE_LIVE(RR_MD_GLUE_PUT)
        return rr_md_glue_live_size();
    }
    case RR_MD_SNAP_INTERP: return rr_md_interp_live_save(o, cap);
    case RR_MD_SNAP_Z80: {
        /* The phase of a sound-CPU instruction suspended on the bus (its counters ride along); its path flags only count. */
        RrMdZ80Evidence e; memset(&e, 0, sizeof e); rr_md_z80_evidence_save(&e);
        memcpy(o, &e, sizeof e); return sizeof e;
    }
    case RR_MD_SNAP_YM: memcpy(o, rr16_md_ym_state(), sizeof(RrMdYmTimers)); return sizeof(RrMdYmTimers);
    case RR_MD_SNAP_GUN: {
        size_t n = rr16_gun_state_save(o, cap - 1);
        if (!n) return 0;
        o[n] = rr16_md_instruction_busy() ? 1 : 0;   /* the gun state's load clears it: a suspended instruction keeps it */
        return n + 1;
    }
    case RR_MD_SNAP_CART: memcpy(o, rr_md_cart_state(), sizeof(RrMdCartState)); return sizeof(RrMdCartState);
    }
    return 0;
}
/* "MDS1", the part count, then each part as u32 length + bytes, in the order of the enum above. */
size_t rr16_md_snap_save(void *buffer, size_t capacity) {
    if (!buffer || capacity < rr16_md_snap_bound() || !s_game_fiber) return 0;
    uint8_t *o = (uint8_t *)buffer;
    const uint32_t parts = RR_MD_SNAP_PARTS;
    memcpy(o, "MDS1", 4); memcpy(o + 4, &parts, 4); o += 8;
    for (unsigned part = 0; part < RR_MD_SNAP_PARTS; ++part) {
        size_t n = rr_md_snap_part_save(part, o + 4, rr_md_snap_part_bound(part));
        if (!n) return 0;
        uint32_t length = (uint32_t)n; memcpy(o, &length, 4); o += 4 + n;
    }
    return (size_t)(o - (uint8_t *)buffer);
}
bool rr16_md_snap_load(const void *buffer, size_t size) {
    const uint8_t *b = (const uint8_t *)buffer, *at[RR_MD_SNAP_PARTS];
    uint32_t length[RR_MD_SNAP_PARTS], parts;
    if (!buffer || size < 8 || size > rr16_md_snap_bound() || memcmp(b, "MDS1", 4) || !s_game_fiber) return false;
    memcpy(&parts, b + 4, 4);
    if (parts != RR_MD_SNAP_PARTS) return false;
    size_t p = 8;
    for (unsigned part = 0; part < RR_MD_SNAP_PARTS; ++part) {
        if (size - p < 4) return false;
        memcpy(&length[part], b + p, 4); p += 4;
        if (length[part] > size - p || length[part] > rr_md_snap_part_bound(part)) return false;
        at[part] = b + p; p += length[part];
    }
    if (p != size) return false;
    /* The fixed parts must have their size, and the cartridge chips a valid state, before anything changes. */
    static const unsigned fixed[] = {RR_MD_SNAP_CPU, RR_MD_SNAP_RAM, RR_MD_SNAP_VDP, RR_MD_SNAP_INPUT, RR_MD_SNAP_GLUE,
                                     RR_MD_SNAP_INTERP, RR_MD_SNAP_Z80, RR_MD_SNAP_YM, RR_MD_SNAP_GUN, RR_MD_SNAP_CART};
    for (size_t i = 0; i < sizeof fixed / sizeof *fixed; ++i)
        if (length[fixed[i]] != rr_md_snap_part_bound(fixed[i])) return false;
    RrMdCartState cart; memcpy(&cart, at[RR_MD_SNAP_CART], sizeof cart);
    if (!rr_md_cart_valid(&cart)) return false;
    /* The game fiber first: the one load that needs the fiber as it is (suspended, the same stack); then the bus
     * scheduler, which checks its own image (and the sound CPU's fiber) before it changes anything. */
    if (!glue_rb_exec_load(at[RR_MD_SNAP_EXEC], length[RR_MD_SNAP_EXEC])) return false;
    if (!rr_md_bus_live_load(at[RR_MD_SNAP_BUS], length[RR_MD_SNAP_BUS])) return false;
    RrMdSnapCpu c; memcpy(&c, at[RR_MD_SNAP_CPU], sizeof c);
    g_cpu = c.cpu; rr_md_cpu_stopped = c.stopped; rr_md_prefetch = c.prefetch;
    if (!glue_rb_sched_load(at[RR_MD_SNAP_SCHED], length[RR_MD_SNAP_SCHED])) return false;
    memcpy(g_ram, at[RR_MD_SNAP_RAM], sizeof g_ram);
    RrMdSnapVdp v; memcpy(&v, at[RR_MD_SNAP_VDP], sizeof v);
    gvdp_rb_set_pending_stall(v.pending_stall); gvdp_set_unlimited_sprites(v.unlimited_sprites);
    if (!rr_md_fm_snap_load(at[RR_MD_SNAP_FM], length[RR_MD_SNAP_FM]) ||
        !psg_rb_load(at[RR_MD_SNAP_PSG_PART], length[RR_MD_SNAP_PSG_PART]) ||
        !audio_event_rb_load(at[RR_MD_SNAP_EVQ], length[RR_MD_SNAP_EVQ])) return false;
    RrMdSnapInput in; memcpy(&in, at[RR_MD_SNAP_INPUT], sizeof in);
    genesis_sim_input_restore(&in.in); genesis_sim_set_tick_count(in.ticks);
    const uint8_t *g = at[RR_MD_SNAP_GLUE];
#define RR_MD_GLUE_GET(name) memcpy(&(name), g, sizeof(name)); g += sizeof(name);
    RR_MD_GLUE_LIVE(RR_MD_GLUE_GET)
    if (!rr_md_interp_live_load(at[RR_MD_SNAP_INTERP], length[RR_MD_SNAP_INTERP])) return false;
    RrMdZ80Evidence e; memcpy(&e, at[RR_MD_SNAP_Z80], sizeof e); rr_md_z80_evidence_load(&e);
    RrMdYmTimers timers; memcpy(&timers, at[RR_MD_SNAP_YM], sizeof timers); rr16_md_ym_restore(&timers);
    size_t gun = length[RR_MD_SNAP_GUN] - 1;
    if (!rr16_gun_state_load(at[RR_MD_SNAP_GUN], gun)) return false;
    rr16_md_instruction(at[RR_MD_SNAP_GUN][gun] != 0);
    return rr_md_cart_restore(&cart) != 0;
}
#else
size_t rr16_md_snap_bound(void) { return 0; }   /* a build without step code plays on the delay tier */
size_t rr16_md_snap_save(void *buffer, size_t capacity) { (void)buffer; (void)capacity; return 0; }
bool rr16_md_snap_load(const void *buffer, size_t size) { (void)buffer; (void)size; return false; }
#endif
'''

# The bus arbiter and the sound CPU's scheduler (native/md_z80_bus.inc, included in the machine copy) and the machine
# copy's own line clocks, with the whole machine (its host pointers are the same objects in this process), the palette
# made from its CRAM, the YM timer clock and the sound CPU's live continuation.
MACHINE_LIVE = r'''
#if RR_MD_STEP_AOT
/* Multiplayer rollback (retrorecomp/megadrive_rollback.py): raw, in this process only; diagnostic counters left out, the
 * lazy queue's used entries only. */
#define RR_MD_SNAP_Z80_STACK (16u*1024u)
#define RR_MD_BUS_LIVE(X) X(rr_lazy_points) X(rr_lazy_instructions) X(rr_lazy_undos) X(rr_z80_fiber) X(rr_z80_spare) \
    X(rr_lazy_retired) X(rr_z80_main) X(rr_z80_busy) X(rr_z80_blocked) X(rr_z80_request) X(rr_z80_granted) \
    X(rr_bus_scheduling) X(rr_bus_main_split) X(rr_z80_checkpoint) X(rr_z80_retiring) X(rr_local_ack) X(rr_local_request) \
    X(rr_local_reset) X(rr_bus_control_event) X(rr_z80_checkpoint_advanced) X(rr_bus_nested_active) \
    X(rr_local_request_time) X(rr_local_ack_time) X(rr_z80_time) X(rr_z80_limit) X(rr_z80_grant) X(rr_bus_main_origin) \
    X(rr_bus_begin) X(rr_bus_fraction) X(rr_z80_boundary_reusable) X(rr_z80_boundary_time) X(rr_z80_cycle_end) \
    X(rr_z80_cycle_head) X(rr_z80_cycle_count) X(rr_lazy_cursor) X(rr_lazy_calls) X(rr_lazy_open) \
    X(rr_lazy_flush_wanted) X(rr_lazy_flushing) X(rr_lazy_restored) X(rr_lazy_replaying) X(rr_lazy_replay_left) \
    X(rr_lazy_restored_time) X(rr_lazy_after_time) X(rr_lazy_return) X(rr_lazy_beyond_pending) \
    X(rr_lazy_beyond_return) X(rr_main_fraction) X(rr_main_debt) X(s_line_base) X(rr_gun_slice_base) \
    X(rr_vdp_cpu_origin) X(rr_vdp_z80_active) X(rr_vdp_z80_wait) X(s_z80_off) X(g_machine) X(s_cram_argb) \
    X(g_snd_frame) X(g_snd_line)
#define RR_MD_LIVE_SIZE(name) sizeof(name) +
int rr_md_fiber_kept(fiber_t fiber);
void rr_md_fiber_park_others(const fiber_t *live, unsigned count);
extern fiber_t glue_rb_game_fiber(void);
size_t rr_md_bus_live_stack_peak;   /* the largest sound-CPU stack image taken, for the probe's report */
size_t rr_md_bus_live_bound(void) {
    return RR_MD_BUS_LIVE(RR_MD_LIVE_SIZE) sizeof rr_lazy_point+sizeof rr_lazy_instruction+sizeof rr_lazy_undo+
        4+RR_MD_SNAP_Z80_STACK;
}
size_t rr_md_bus_live_save(void *data,size_t capacity) {
    if(rr_lazy_points>RR_LAZY_POINTS || rr_lazy_instructions>RR_LAZY_POINTS || rr_lazy_undos>RR_LAZY_UNDO)return 0;
    if(!rr_md_fiber_kept(rr_z80_fiber) || !rr_md_fiber_kept(rr_z80_spare) || !rr_md_fiber_kept(rr_lazy_retired))return 0;
    size_t stack=rr_z80_fiber?fiber_snapshot_bound(rr_z80_fiber):0;
    size_t need=RR_MD_BUS_LIVE(RR_MD_LIVE_SIZE) rr_lazy_points*sizeof *rr_lazy_point+
        rr_lazy_instructions*sizeof *rr_lazy_instruction+rr_lazy_undos*sizeof *rr_lazy_undo+4+stack;
    if(!data || capacity<need || stack>RR_MD_SNAP_Z80_STACK || (rr_z80_fiber && !stack))return 0;
    if(stack>rr_md_bus_live_stack_peak)rr_md_bus_live_stack_peak=stack;
    uint8_t *o=(uint8_t *)data;
#define RR_MD_LIVE_PUT(name) memcpy(o,&(name),sizeof(name));o+=sizeof(name);
    RR_MD_BUS_LIVE(RR_MD_LIVE_PUT)
    memcpy(o,rr_lazy_point,rr_lazy_points*sizeof *rr_lazy_point);o+=rr_lazy_points*sizeof *rr_lazy_point;
    memcpy(o,rr_lazy_instruction,rr_lazy_instructions*sizeof *rr_lazy_instruction);
    o+=rr_lazy_instructions*sizeof *rr_lazy_instruction;
    memcpy(o,rr_lazy_undo,rr_lazy_undos*sizeof *rr_lazy_undo);o+=rr_lazy_undos*sizeof *rr_lazy_undo;
    uint32_t length=(uint32_t)stack;memcpy(o,&length,4);o+=4;
    if(stack && fiber_snapshot_save(rr_z80_fiber,o,stack)!=stack)return 0;
    return need;
}
int rr_md_bus_live_load(const void *data,size_t size) {
    const size_t fixed=RR_MD_BUS_LIVE(RR_MD_LIVE_SIZE) 0;
    const uint8_t *i=(const uint8_t *)data;
    if(!data || size<fixed+4)return 0;
    /* The image begins with the three counts and the three fibers (the order of RR_MD_BUS_LIVE): check them, and that
     * the whole image fits, before anything changes. */
    unsigned points,instructions,undos;fiber_t fiber,spare,retired;
    size_t at=0;
    memcpy(&points,i+at,sizeof points);at+=sizeof rr_lazy_points;
    memcpy(&instructions,i+at,sizeof instructions);at+=sizeof rr_lazy_instructions;
    memcpy(&undos,i+at,sizeof undos);at+=sizeof rr_lazy_undos;
    memcpy(&fiber,i+at,sizeof fiber);at+=sizeof rr_z80_fiber;
    memcpy(&spare,i+at,sizeof spare);at+=sizeof rr_z80_spare;
    memcpy(&retired,i+at,sizeof retired);
    if(points>RR_LAZY_POINTS || instructions>RR_LAZY_POINTS || undos>RR_LAZY_UNDO ||
       !rr_md_fiber_kept(fiber) || !rr_md_fiber_kept(spare) || !rr_md_fiber_kept(retired))return 0;
    size_t lazy=points*sizeof *rr_lazy_point+instructions*sizeof *rr_lazy_instruction+undos*sizeof *rr_lazy_undo;
    if(size<fixed+lazy+4)return 0;
    uint32_t stack;memcpy(&stack,i+fixed+lazy,4);
    if(size!=fixed+lazy+4+stack || (fiber && !stack) || (!fiber && stack))return 0;
    if(stack && fiber_snapshot_load(fiber,i+fixed+lazy+4,stack)!=0)return 0;
#define RR_MD_LIVE_GET(name) memcpy(&(name),i,sizeof(name));i+=sizeof(name);
    RR_MD_BUS_LIVE(RR_MD_LIVE_GET)
    memcpy(rr_lazy_point,i,points*sizeof *rr_lazy_point);i+=points*sizeof *rr_lazy_point;
    memcpy(rr_lazy_instruction,i,instructions*sizeof *rr_lazy_instruction);i+=instructions*sizeof *rr_lazy_instruction;
    memcpy(rr_lazy_undo,i,undos*sizeof *rr_lazy_undo);
    /* The fibers this state does not use are free again, as they were when it was taken. */
    const fiber_t live[]={rr_z80_fiber,rr_z80_spare,rr_lazy_retired,glue_rb_game_fiber()};
    rr_md_fiber_park_others(live,sizeof live/sizeof *live);
    return 1;
}
#endif
'''

# The interpreter's instruction-local statics (the prefetch planner of md_prefetch.inc, the prepared native step, the
# order of a long read-modify-write, the exception and trace residues): a suspended instruction reads them when it
# resumes. Only step builds include md_prefetch.inc.
INTERPRETER_LIVE = r'''
#if RR_MD_STEP_AOT
/* Multiplayer rollback (retrorecomp/megadrive_rollback.py): an instruction suspended on the bus, raw, in this process. */
#define RR_MD_INTERP_LIVE(X) X(rr_pf_image_pc) X(rr_pf_image_count) X(rr_pf_pending) X(rr_pf_before_write) \
    X(rr_pf_control) X(rr_pf_control_cycles) X(rr_pf_condition) X(rr_pf_image_valid) X(rr_pf_move) \
    X(rr_pf_dst_advance) X(rr_pf_dst_idle) X(rr_pf_image) X(rr_prepared_native) X(s_low_first) X(rr_md_illegal_ea) \
    X(rr_md_exception_cycles) X(rr_md_trace_suppressed)
#define RR_MD_INTERP_SIZE(name) sizeof(name) +
size_t rr_md_interp_live_size(void) { return RR_MD_INTERP_LIVE(RR_MD_INTERP_SIZE) 0; }
size_t rr_md_interp_live_save(void *data, size_t capacity) {
    uint8_t *o = (uint8_t *)data;
    if (!data || capacity < rr_md_interp_live_size()) return 0;
#define RR_MD_INTERP_PUT(name) memcpy(o, &(name), sizeof(name)); o += sizeof(name);
    RR_MD_INTERP_LIVE(RR_MD_INTERP_PUT)
    return rr_md_interp_live_size();
}
int rr_md_interp_live_load(const void *data, size_t size) {
    const uint8_t *i = (const uint8_t *)data;
    if (!data || size != rr_md_interp_live_size()) return 0;
#define RR_MD_INTERP_GET(name) memcpy(&(name), i, sizeof(name)); i += sizeof(name);
    RR_MD_INTERP_LIVE(RR_MD_INTERP_GET)
    return 1;
}
#endif
'''

# The YM2612 in the upstream format of ym2612_rb_save, with reusable buffers: the upstream save and load build a
# std::vector on every call, and the rollback tier saves once per frame.
FM_LIVE = r'''
/* Multiplayer rollback (retrorecomp/megadrive_rollback.py): ym2612_rb_save's bytes, without an allocation once the two
 * buffers exist. */
static std::vector<uint8_t> s_rr_snap_chip, s_rr_load_chip;
static void rr_md_fm_chip_image(void) {
    if (!s_inited) ym2612_init();
    if (s_rr_snap_chip.capacity() < 4096) s_rr_snap_chip.reserve(4096);
    ymfm::ymfm_saved_state st(s_rr_snap_chip, true);
    s_chip->save_restore(st);
}
extern "C" size_t rr_md_fm_snap_bound(void) {
    rr_md_fm_chip_image();
    return 4 + s_rr_snap_chip.size() + sizeof s_master_accum + sizeof s_fm_lpf_prev + sizeof s_fm_lpf_out + 4 +
           (size_t)FM_SCRATCH_STEREO_SAMPLES * 2u * sizeof(int16_t);
}
extern "C" size_t rr_md_fm_snap_save(void *dst, size_t cap) {
    rr_md_fm_chip_image();
    uint32_t n = (uint32_t)s_rr_snap_chip.size();
    uint32_t pend = (uint32_t)(s_scratch_write - s_scratch_read);
    size_t need = sizeof n + n + sizeof s_master_accum + sizeof s_fm_lpf_prev +
                  sizeof s_fm_lpf_out + sizeof pend + (size_t)pend * 2u * sizeof(int16_t);
    if (!dst || cap < need) return 0;
    uint8_t *o = (uint8_t *)dst;
    std::memcpy(o, &n, sizeof n); o += sizeof n;
    if (n) { std::memcpy(o, s_rr_snap_chip.data(), n); o += n; }
    std::memcpy(o, &s_master_accum, sizeof s_master_accum); o += sizeof s_master_accum;
    std::memcpy(o, s_fm_lpf_prev, sizeof s_fm_lpf_prev); o += sizeof s_fm_lpf_prev;
    std::memcpy(o, s_fm_lpf_out, sizeof s_fm_lpf_out); o += sizeof s_fm_lpf_out;
    std::memcpy(o, &pend, sizeof pend); o += sizeof pend;
    std::memcpy(o, &s_scratch[s_scratch_read * 2], (size_t)pend * 2u * sizeof(int16_t));
    return need;
}
extern "C" int rr_md_fm_snap_load(const void *src, size_t len) {
    if (!s_inited) ym2612_init();
    const uint8_t *i = (const uint8_t *)src;
    uint32_t n = 0, pend = 0;
    if (!src || len < sizeof n) return 0;
    std::memcpy(&n, i, sizeof n); i += sizeof n;
    size_t fixed = sizeof s_master_accum + sizeof s_fm_lpf_prev + sizeof s_fm_lpf_out + sizeof pend;
    if (n > (1u << 20) || len - sizeof n < (size_t)n + fixed) return 0;
    std::memcpy(&pend, i + n + fixed - sizeof pend, sizeof pend);
    if (pend > FM_SCRATCH_STEREO_SAMPLES ||
        len - sizeof n != (size_t)n + fixed + (size_t)pend * 2u * sizeof(int16_t)) return 0;
    s_rr_load_chip.assign(i, i + n); i += n;
    ymfm::ymfm_saved_state st(s_rr_load_chip, false);
    s_chip->save_restore(st);
    std::memcpy(&s_master_accum, i, sizeof s_master_accum); i += sizeof s_master_accum;
    std::memcpy(s_fm_lpf_prev, i, sizeof s_fm_lpf_prev); i += sizeof s_fm_lpf_prev;
    std::memcpy(s_fm_lpf_out, i, sizeof s_fm_lpf_out); i += sizeof s_fm_lpf_out;
    i += sizeof pend;
    std::memcpy(s_scratch, i, (size_t)pend * 2u * sizeof(int16_t));
    s_scratch_read = 0;
    s_scratch_write = pend;
    return 1;
}
'''

# Fibers kept for the process's life: fiber_destroy parks a fiber, fiber_create resets a parked one of the same sizes.
# The sound CPU's continuations are created and destroyed as the lazy rendezvous replays (md_z80_bus.inc); a snapshot
# holds one of them by address with its stack image, which loads only into the stack it was taken from.
FIBER_KEEP = r'''
/* Multiplayer rollback (retrorecomp/megadrive_rollback.py): a fiber is never freed while the game runs. */
#define RR_FIBERS_KEPT 8u
static fiber_impl *rr_fiber_kept[RR_FIBERS_KEPT];
static size_t rr_fiber_kept_commit[RR_FIBERS_KEPT], rr_fiber_kept_reserve[RR_FIBERS_KEPT];
static unsigned rr_fiber_kept_count, rr_fiber_parked;
fiber_t fiber_create(size_t commit, size_t reserve, fiber_entry_fn entry, void *arg)
{
    for (unsigned i = 0; i < rr_fiber_kept_count; ++i)
        if ((rr_fiber_parked & 1u << i) && rr_fiber_kept_commit[i] == commit && rr_fiber_kept_reserve[i] == reserve) {
            if (fiber_reset((fiber_t)rr_fiber_kept[i], entry, arg) != 0) return NULL;
            rr_fiber_parked &= ~(1u << i);
            return (fiber_t)rr_fiber_kept[i];
        }
    fiber_t fiber = rr_fiber_create_new(commit, reserve, entry, arg);
    if (fiber && rr_fiber_kept_count < RR_FIBERS_KEPT) {
        rr_fiber_kept[rr_fiber_kept_count] = (fiber_impl *)fiber;
        rr_fiber_kept_commit[rr_fiber_kept_count] = commit; rr_fiber_kept_reserve[rr_fiber_kept_count] = reserve;
        ++rr_fiber_kept_count;
    }
    return fiber;
}
void fiber_destroy(fiber_t fiber)
{
    for (unsigned i = 0; i < rr_fiber_kept_count; ++i)
        if (rr_fiber_kept[i] == (fiber_impl *)fiber) { rr_fiber_parked |= 1u << i; return; }
    rr_fiber_destroy_now(fiber);
}
/* A snapshot may name a fiber only if it is kept (NULL is fine). */
int rr_md_fiber_kept(fiber_t fiber)
{
    if (!fiber) return 1;
    for (unsigned i = 0; i < rr_fiber_kept_count; ++i) if (rr_fiber_kept[i] == (fiber_impl *)fiber) return 1;
    return 0;
}
/* After a load: every kept fiber the loaded state does not use is parked, as it was when the state was taken. */
void rr_md_fiber_park_others(const fiber_t *live, unsigned count)
{
    unsigned parked = 0;
    for (unsigned i = 0; i < rr_fiber_kept_count; ++i) {
        int used = 0;
        for (unsigned k = 0; k < count; ++k) used |= live[k] == (fiber_t)rr_fiber_kept[i];
        if (!used) parked |= 1u << i;
    }
    rr_fiber_parked = parked;
}
'''

# A session's silent frame (a rollback running again frames already heard) gives the sound device nothing: its clock,
# its ring and the bridge stay where the live frames left them.
AUDIO_SILENT = (
    '''    if (s_dev == 0 || psg_buf == NULL || psg_frames == 0)
        return;''',
    '''    if (s_dev == 0 || psg_buf == NULL || psg_frames == 0 || rrhk_session_silent())
        return;''')


def glue(source: str) -> str:
    source = _replace(source, 'size_t glue_rb_exec_save(void *dst, size_t cap)\n{',
                      'fiber_t glue_rb_game_fiber(void) { return s_game_fiber; }\n'
                      'size_t glue_rb_exec_save(void *dst, size_t cap)\n{', 'Mega Drive glue exec section')
    return source + GLUE_LIVE


def machine(source: str) -> str:
    return source + MACHINE_LIVE


def interpreter(source: str) -> str:
    return source + INTERPRETER_LIVE


def fm(source: str) -> str:
    if 'extern "C" size_t ym2612_rb_save(' not in source or 'FM_SCRATCH_STEREO_SAMPLES' not in source:
        raise ConversionError('Pinned YM2612 snapshot changed; Mega Drive rollback adaptation refused.')
    return source + FM_LIVE


def fiber(source: str) -> str:
    source = _replace(source, 'fiber_t fiber_create(size_t commit, size_t reserve, fiber_entry_fn entry, void *arg)\n{',
                      'static fiber_t rr_fiber_create_new(size_t commit, size_t reserve, fiber_entry_fn entry, void *arg)\n{',
                      'fiber creation')
    source = _replace(source, 'void fiber_destroy(fiber_t fiber)\n{', 'static void rr_fiber_destroy_now(fiber_t fiber)\n{',
                      'fiber destruction')
    return source + FIBER_KEEP


def audio(source: str) -> str:
    source = _replace(source, *AUDIO_SILENT, 'Mega Drive audio flush')
    return 'extern _Bool rrhk_session_silent(void);\n' + source
