/* Compare old/reduced scheduling with authored RAM programs. No game frames. */
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
static unsigned switches;
static void counted_switch(fiber_t target) {++switches;fiber_switch(target);}
#define fiber_switch counted_switch
#define RR_MD_REPEAT_Z80_BOUNDARIES repeat_boundaries
#define RR_MD_HOST_ONLY_Z80_BOUNDARIES host_only_boundaries
#include "genesis_machine.c"
#undef fiber_switch
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
static unsigned checks,events;
static uint64_t trace;
static uint64_t work_ticks;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
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
static void stamp(unsigned address,unsigned value,unsigned write) {
    uint64_t v[4]={address,value,write,(uint64_t)rr_z80_time};
    for(unsigned i=0;i<4;++i){trace^=v[i];trace*=UINT64_C(1099511628211);}++events;
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
}
typedef struct {
    z80 cpu;M68KState main_cpu;uint8_t ram[8192],main_ram[65536];uint32_t clocks;
    int64_t time;uint64_t trace;unsigned events;
} Result;
static Result run(unsigned test,int mode) {
    repeat_boundaries=mode==1;host_only_boundaries=mode==2;rr16_reset();GenesisMachine *m=&g_machine;
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
    m->bus.z80_ram[0x38]=0xed;m->bus.z80_ram[0x39]=0x4d; /* RETI */
    m->bus.z80_bank=0x1c0;g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    switches=events=0;trace=UINT64_C(14695981039346656037);g_mem_write_trace_fn=main_write;
    unsigned step=test%12<6?97:7;
    uint64_t started=SDL_GetPerformanceCounter();
    for(unsigned begin=0;begin<3420;) {
        unsigned end=begin+step;if(end>3420)end=3420;
        rr_bus_slice(m,begin,end,0,0);
        if(begin>=600 && begin<600+step)gbus_write8(&m->bus,0xa11100,1);
        if(begin>=750 && begin<750+step)gbus_write8(&m->bus,0xa11100,0);
        if(begin>=1200 && begin<1200+step)z80_gen_int(&m->z80,0xff);
        begin=end;
    }
    work_ticks=SDL_GetPerformanceCounter()-started;
    g_mem_write_trace_fn=NULL;
    Result r={0};r.cpu=m->z80;r.main_cpu=g_cpu;memcpy(r.ram,m->bus.z80_ram,sizeof r.ram);
    memcpy(r.main_ram,g_ram,sizeof r.main_ram);r.clocks=g_audio_cycle_counter;
    r.time=rr_z80_time;r.trace=trace;r.events=events;return r;
}
int main(int argc,char **argv) {
    CHECK(rr16_init(true));nested_fibers();unsigned original_switches=0,reduced_switches=0;
    unsigned iterations=argc>1 && !strcmp(argv[1],"--benchmark")?16u:1u;
    uint64_t original_ticks=0,previous_ticks=0,reduced_ticks=0;unsigned previous_switches=0;
    for(unsigned iteration=0;iteration<iterations;++iteration)for(unsigned test=0;test<72;++test) {
        Result original=run(test,1);original_switches+=switches;original_ticks+=work_ticks;
        Result previous=run(test,2);previous_switches+=switches;previous_ticks+=work_ticks;
        Result reduced=run(test,0);reduced_switches+=switches;reduced_ticks+=work_ticks;
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
    printf("{\"passed\":true,\"checks\":%u,\"program_pairs\":%u,\"traces_and_clocks_equal\":true,\"original_switches\":%u,\"previous_switches\":%u,\"reduced_switches\":%u,\"original_work_seconds\":%.9f,\"previous_work_seconds\":%.9f,\"reduced_work_seconds\":%.9f}\n",
        checks,72u*iterations,original_switches,previous_switches,reduced_switches,
        (double)original_ticks/SDL_GetPerformanceFrequency(),(double)previous_ticks/SDL_GetPerformanceFrequency(),(double)reduced_ticks/SDL_GetPerformanceFrequency());return 0;
}
