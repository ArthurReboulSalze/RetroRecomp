/* Compare old/reduced/deferred scheduling with authored RAM programs. No
 * game frames. A deferred sound CPU runs ahead, so its cycles interleave
 * differently with 68000 writes: that mode is compared per CPU (each in its
 * own order, with clocks), plus every final state. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include "retro_console16.h"
#include "genesis_runtime.h"
#include "fiber_compat.h"
static int repeat_boundaries;
static int host_only_boundaries;
static int lazy_boundaries;
static unsigned switches;
static void counted_switch(fiber_t target) {++switches;fiber_switch(target);}
#define fiber_switch counted_switch
#define RR_MD_REPEAT_Z80_BOUNDARIES repeat_boundaries
#define RR_MD_HOST_ONLY_Z80_BOUNDARIES host_only_boundaries
#define RR_MD_LAZY_Z80 lazy_boundaries
/* The sweep programs run through the reference core directly: authored code
 * has no converter-generated native body, and the interpreter-miss path
 * (machine_z80_fallback) deliberately ends every deferred instruction. */
static int direct_step;
#define rr_md_z80_step fixture_z80_step
#include "genesis_machine.c"
#undef rr_md_z80_step
#undef fiber_switch
void rr_md_z80_step(z80 *z);
void fixture_z80_step(z80 *z) {
    if(direct_step)z80_step(z);else rr_md_z80_step(z);
}
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
static unsigned checks,events,current_test;
static uint64_t trace;
static uint64_t work_ticks;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s (program %u)\n",__LINE__,#ok,current_test);exit(1);}}while(0)
static fiber_t nested_host,nested_parent,nested_child,nested_return;
static unsigned nested_visits,nested_local;
static void child_entry(void *unused) {
    (void)unused;unsigned local=0;
    for(;;) {
        CHECK(fiber_current()==nested_child);nested_local=++local;++nested_visits;
        fiber_switch(nested_return);
    }
}
static void parent_entry(void *unused) {
    (void)unused;
    for(;;) {
        CHECK(fiber_current()==nested_parent);nested_return=nested_parent;
        fiber_switch(nested_child);CHECK(fiber_current()==nested_parent);
        fiber_switch(nested_host);
    }
}
static void nested_fibers(void) {
    nested_host=fiber_current();
    nested_child=fiber_create(65536,65536,child_entry,NULL);
    nested_parent=fiber_create(65536,65536,parent_entry,NULL);
    CHECK(nested_child && nested_parent);
    fiber_switch(nested_parent);CHECK(nested_visits==1 && nested_local==1 && fiber_current()==nested_host);
    size_t n=fiber_snapshot_bound(nested_child);void *saved=malloc(n);CHECK(n && saved);
    CHECK(fiber_snapshot_save(nested_child,saved,n)==n);
    /* Reset/destruction may cancel the old parent while the child is suspended.
     * Its next resume must return to its current caller, not a dead stack. */
    fiber_destroy(nested_parent);nested_parent=NULL;nested_return=nested_host;
    fiber_switch(nested_child);CHECK(nested_visits==2 && nested_local==2);
    CHECK(fiber_snapshot_load(nested_child,saved,n)==0);
    fiber_switch(nested_child);CHECK(nested_visits==3 && nested_local==2);
    nested_parent=fiber_create(65536,65536,parent_entry,NULL);CHECK(nested_parent);
    fiber_switch(nested_parent);CHECK(nested_visits==4 && nested_local==3);
    CHECK(fiber_reset(nested_child,child_entry,NULL)==0);
    nested_return=nested_host;fiber_switch(nested_child);CHECK(nested_visits==5 && nested_local==1);
    free(saved);fiber_destroy(nested_child);fiber_destroy(nested_parent);
    CHECK(fiber_current()==nested_host);
}
typedef struct { uint32_t address, value, kind; int64_t time; } Event;
static Event z80_events[65536],main_events[65536];
static unsigned z80_count,main_count;
static void stamp(unsigned address,unsigned value,unsigned write) {
    uint64_t v[4]={address,value,write,(uint64_t)rr_z80_time};
    for(unsigned i=0;i<4;++i){trace^=v[i];trace*=UINT64_C(1099511628211);}++events;
    CHECK(z80_count<65536);z80_events[z80_count++]=(Event){address,value,write,rr_z80_time};
}
static void rollback(int64_t time) {
    /* The deferred scheduler will replay these sound-CPU cycles. */
    while(z80_count && z80_events[z80_count-1].time>=time)--z80_count;
}
static uint64_t events_hash(const Event *e,unsigned n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(unsigned i=0;i<n;++i) {
        uint64_t v[4]={e[i].address,e[i].value,e[i].kind,(uint64_t)e[i].time};
        for(unsigned k=0;k<4;++k){h^=v[k];h*=UINT64_C(1099511628211);}
    }
    return h;
}
static uint8_t read_byte(void *bus,uint16_t address) {
    uint8_t value=gbus_z80_read(bus,address);stamp(address,value,0);return value;
}
static void write_byte(void *bus,uint16_t address,uint8_t value) {
    gbus_z80_write(bus,address,value);stamp(address,value,1);
}
extern void (*g_mem_write_trace_fn)(uint32_t,uint8_t,uint32_t);
static void main_write(uint32_t address,uint8_t value,uint32_t cycle) {
    uint64_t v[4]={address,value,2,cycle};
    for(unsigned i=0;i<4;++i){trace^=v[i];trace*=UINT64_C(1099511628211);}++events;
    CHECK(main_count<65536);main_events[main_count++]=(Event){address,value,2,cycle};
}
/* Sweep (programs SWEEP_FIRST and up): authored sound programs with private
 * RAM work and shared cycles (YM status/write, banked read) against a 68000
 * that requests the bus and polls for the grant, over every slice length from
 * 5 to 259 master clocks (0: the host's sixteen slices per line) and sixteen
 * 68000 delays. A BUSREQ write that ends the merged final catch-up of a
 * deferred payment must be answered at once, as in the immediate schedule: if
 * the host checkpoint runs the 68000 once more first, the poll count (D1) and
 * the clocks differ. The programs that exposed it before the correction were
 * 24622 and 12 others (INC (IX+0) with delay loops of 13). */
#define SWEEP_FIRST 72u
#define SWEEP_Z80 8u
#define SWEEP_PAD 16u
#define SWEEP_STEPS 256u
#define TESTS (SWEEP_FIRST+SWEEP_Z80*SWEEP_PAD*SWEEP_STEPS)
static const uint8_t sweep_z80[SWEEP_Z80][16]={
    {0x21,0,0x10,0x34,0x34,0x3a,0,0x40,0xc3,0,0},          /* INC (HL) x2; LD A,($4000) */
    {0x21,0,0x10,0x34,0x3a,0,0x80,0x34,0xc3,0,0},          /* INC (HL); LD A,($8000); INC (HL) */
    {0x21,0,0x10,0x35,0x35,0x35,0x32,0,0x40,0xc3,0,0},     /* DEC (HL) x3; LD ($4000),A */
    {0x21,0,0x10,0x7e,0x3c,0x77,0x34,0x32,0x01,0x40,0xc3,3,0}, /* LD A,(HL); INC A; LD (HL),A; INC (HL); LD ($4001),A */
    {0xe3,0xe3,0xc3,0,0},                                    /* EX (SP),HL: a long gap between accesses */
    {0xcd,6,0,0xc3,0,0,0xc9},                                /* CALL 6; JP 0 / RET */
    {0xdd,0x34,0,0x3a,0,0x40,0xc3,0,0},                      /* INC (IX+0); LD A,($4000) */
    {0x21,0,0x10,0x36,0x55,0x3a,0,0x80,0xc3,0,0},            /* LD (HL),n; LD A,($8000) */
};
typedef struct {
    z80 cpu;M68KState main_cpu;uint8_t ram[8192],main_ram[65536];uint32_t clocks;
    int64_t time;uint64_t trace;unsigned events;
    uint64_t z80_trace,main_trace;unsigned z80_events,main_events;
} Result;
static Result run(unsigned test,int mode) {
    repeat_boundaries=mode==1;host_only_boundaries=mode==2;lazy_boundaries=mode==3;
    rr16_reset();GenesisMachine *m=&g_machine;
    g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
    m->bus.z80_reset_off=1;m->bus.z80_busreq=m->bus.z80_reset_pending=0;
    rr_md_z80_bus_reset();z80_own_reset(&m->z80);
    m->z80.read_byte=read_byte;m->z80.write_byte=write_byte;
    m->z80.sp=0x1ff0;m->z80.ix=0x1100;m->z80.iy=0x1200;
    memset(m->bus.z80_ram,0,sizeof m->bus.z80_ram);memset(g_ram,0,sizeof g_ram);
    static const uint8_t code[][16]={
        {0x04,0xc3,0,0}, /* INC B; JP 0: adjacent retirement/guard/fetch */
        {0x21,0,0x10,0x34,0x7e,0x32,1,0x10,0xc3,3,0},
        {0xdd,0x34,0,0xdd,0xcb,0,6,0xc3,0,0},
        {0x3a,0,0x80,0x3c,0x32,1,0x80,0xc3,0,0}, /* banked main-bus WAIT */
        {0xc5,0x04,0xd1,0xc3,0,0},
        {0xfb,0x00,0x76,0xc3,1,0}, /* HALT/interrupt boundaries */
    };
    memcpy(m->bus.z80_ram,code[test%6],16);
    if(test>=SWEEP_FIRST)memcpy(m->bus.z80_ram,sweep_z80[(test-SWEEP_FIRST)%SWEEP_Z80],16);
    if(test>=12) {
        /* ADDQ.W #1,$ff2000; BRA.S -8: a running 68000 shares the RAM bus. */
        const uint16_t main_code[]={0x5279,0x00ff,0x2000,0x60f8};
        for(unsigned i=0;i<4;++i)gbus_write16(&m->bus,0xff0100+i*2,main_code[i]);
        rr_md_cpu_stopped=0;
    }
    if(test>=24) {
        static const uint16_t programs[][24]={
            /* Shared sound RAM writes, a bus-ownership handshake, reset of a
             * running sound continuation, and YM status reads. All authored. */
            {0x13c0,0x00a0,0x1000,0x5200,0x60f6},
            {0x13fc,1,0x00a1,0x1100,0x13c0,0x00a0,0x1000,0x13fc,0,0x00a1,0x1100,0x60e8},
            {0x13fc,0,0x00a1,0x1200,0x13fc,1,0x00a1,0x1200,0x60ee},
            {0x1039,0x00a0,0x4000,0x13c0,0x00ff,0x2000,0x60f2},
        };
        unsigned which=(test-24)/12;
        for(unsigned i=0;i<24;++i)gbus_write16(&m->bus,0xff0100+i*2,programs[which][i]);
    }
    if(test>=SWEEP_FIRST) {
        /* A running 68000 requests the bus and polls for the grant, as game
         * drivers do before touching sound RAM or the YM: the number of polls
         * it needs is the observable. Padding moves its write against the
         * sound CPU's slice ends. All authored. */
        unsigned pad=((test-SWEEP_FIRST)/SWEEP_Z80)%SWEEP_PAD;
        uint16_t program[24]={0x41f9,0x00a1,0x1100,      /* LEA $a11100,A0 */
            0x30bc,0x0100,                               /* MOVE.W #$100,(A0): request the bus */
            0x5241,                                      /* poll: ADDQ.W #1,D1 */
            0x4a50,0x66fa,                               /* TST.W (A0); BNE.S poll */
            0x30bc,0x0000,                               /* MOVE.W #0,(A0): release it */
            0x303c,0,0x51c8,0xfffe};                     /* MOVE.W #n,D0; DBRA D0,* (the sound CPU runs meanwhile) */
        program[11]=(uint16_t)(1u+pad/4u*4u);
        unsigned n=14;for(unsigned i=0;i<pad%4u;++i)program[n++]=0x4e71;
        unsigned displacement=0x100u-(n*2u+2u);
        program[n]=(uint16_t)(0x6000u|(displacement&0xffu));   /* BRA.S to the start */
        for(unsigned i=0;i<24;++i)gbus_write16(&m->bus,0xff0100+i*2,program[i]);
        rr_md_cpu_stopped=0;
    }
    m->bus.z80_ram[0x38]=0xed;m->bus.z80_ram[0x39]=0x4d; /* RETI */
    m->bus.z80_bank=0x1c0;g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    switches=events=z80_count=main_count=0;trace=UINT64_C(14695981039346656037);g_mem_write_trace_fn=main_write;
    rr_md_lazy_rollback_trace=rollback;
    unsigned step=test%12<6?97:7;
    unsigned parts=0; /* 0: fixed step; 1: the host's own sixteenth-of-a-line slices */
    if(test>=SWEEP_FIRST) {
        static unsigned steps[SWEEP_STEPS];for(unsigned i=1;i<SWEEP_STEPS;++i)steps[i]=4u+i;
        unsigned which=(test-SWEEP_FIRST)/(SWEEP_Z80*SWEEP_PAD);
        step=steps[which%SWEEP_STEPS];parts=!step;if(parts)step=1;
    }
    direct_step=test>=SWEEP_FIRST;
    uint64_t started=SDL_GetPerformanceCounter();
    for(unsigned begin=0,part=0;begin<3420;++part) {
        unsigned end=parts?(part+1u)*3420u/16u:begin+step;if(end>3420)end=3420;
        rr_bus_slice(m,begin,end,0,0);
        if(test<SWEEP_FIRST) {
            if(begin>=600 && begin<600+step)gbus_write8(&m->bus,0xa11100,1);
            if(begin>=750 && begin<750+step)gbus_write8(&m->bus,0xa11100,0);
            if(begin>=1200 && begin<1200+step)z80_gen_int(&m->z80,0xff);
        }
        begin=end;
    }
    work_ticks=SDL_GetPerformanceCounter()-started;
    g_mem_write_trace_fn=NULL;
    Result r={0};r.cpu=m->z80;r.main_cpu=g_cpu;memcpy(r.ram,m->bus.z80_ram,sizeof r.ram);
    memcpy(r.main_ram,g_ram,sizeof r.main_ram);r.clocks=g_audio_cycle_counter;
    r.time=rr_z80_time;r.trace=trace;r.events=events;
    r.z80_trace=events_hash(z80_events,z80_count);r.main_trace=events_hash(main_events,main_count);
    r.z80_events=z80_count;r.main_events=main_count;return r;
}
int main(int argc,char **argv) {
    CHECK(rr16_init(true));nested_fibers();unsigned original_switches=0,reduced_switches=0;
    unsigned iterations=argc>1 && !strcmp(argv[1],"--benchmark")?16u:1u;
    uint64_t original_ticks=0,previous_ticks=0,reduced_ticks=0,deferred_ticks=0;
    unsigned previous_switches=0,deferred_switches=0;uint64_t rollbacks=rr_md_lazy_rollbacks;
    /* The timing benchmark keeps its original programs; the sweep is a check. */
    const unsigned tests=iterations>1?SWEEP_FIRST:TESTS;
    for(unsigned iteration=0;iteration<iterations;++iteration)for(unsigned test=0;test<tests;++test) {
        current_test=test;
        Result original=run(test,1);original_switches+=switches;original_ticks+=work_ticks;
        Result previous=run(test,2);previous_switches+=switches;previous_ticks+=work_ticks;
        Result reduced=run(test,0);reduced_switches+=switches;reduced_ticks+=work_ticks;
        Result deferred=run(test,3);deferred_switches+=switches;deferred_ticks+=work_ticks;
        CHECK(!memcmp(&original.cpu,&deferred.cpu,sizeof original.cpu));
        CHECK(!memcmp(&original.main_cpu,&deferred.main_cpu,sizeof original.main_cpu));
        CHECK(!memcmp(original.ram,deferred.ram,sizeof original.ram));
        CHECK(!memcmp(original.main_ram,deferred.main_ram,sizeof original.main_ram));
        CHECK(original.clocks==deferred.clocks && original.time==deferred.time);
        CHECK(original.z80_trace==deferred.z80_trace && original.z80_events==deferred.z80_events);
        CHECK(original.main_trace==deferred.main_trace && original.main_events==deferred.main_events);
        CHECK(!memcmp(&original.cpu,&reduced.cpu,sizeof original.cpu));
        CHECK(!memcmp(&original.main_cpu,&reduced.main_cpu,sizeof original.main_cpu));
        CHECK(!memcmp(original.ram,reduced.ram,sizeof original.ram));
        CHECK(!memcmp(original.main_ram,reduced.main_ram,sizeof original.main_ram));
        CHECK(original.clocks==reduced.clocks && original.time==reduced.time);
        CHECK(original.trace==reduced.trace && original.events==reduced.events);
        CHECK(!memcmp(&original.cpu,&previous.cpu,sizeof original.cpu));
        CHECK(!memcmp(&original.main_cpu,&previous.main_cpu,sizeof original.main_cpu));
        CHECK(!memcmp(original.ram,previous.ram,sizeof original.ram));
        CHECK(!memcmp(original.main_ram,previous.main_ram,sizeof original.main_ram));
        CHECK(original.clocks==previous.clocks && original.time==previous.time);
        CHECK(original.trace==previous.trace && original.events==previous.events);
    }
    CHECK(reduced_switches<original_switches);rr16_shutdown();
    rollbacks=rr_md_lazy_rollbacks-rollbacks;
    printf("{\"passed\":true,\"checks\":%u,\"program_pairs\":%u,\"traces_and_clocks_equal\":true,\"original_switches\":%u,\"previous_switches\":%u,\"reduced_switches\":%u,\"deferred_switches\":%u,\"deferred_rollbacks\":%llu,\"original_work_seconds\":%.9f,\"previous_work_seconds\":%.9f,\"reduced_work_seconds\":%.9f,\"deferred_work_seconds\":%.9f}\n",
        checks,tests*iterations,original_switches,previous_switches,reduced_switches,deferred_switches,(unsigned long long)rollbacks,
        (double)original_ticks/SDL_GetPerformanceFrequency(),(double)previous_ticks/SDL_GetPerformanceFrequency(),(double)reduced_ticks/SDL_GetPerformanceFrequency(),
        (double)deferred_ticks/SDL_GetPerformanceFrequency());return 0;
}
