/* Authored code changes after AOT selection, in actual production fibers.
 * The fixture drives checkpoints and explicitly grants an external request;
 * full arbiter timing is tested separately by md_bus_checks.c. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "genesis_runtime.h"
/* Deliberately expose the zero-clock guard/fetch gap for mutation injection.
 * The real scheduler cannot advance another CPU in that gap. Re-enable the
 * production optimization immediately after injection, before resuming. */
static int expose_fetch_gap;
#define RR_MD_REPEAT_Z80_BOUNDARIES expose_fetch_gap
#define rr_md_z80_step fixture_z80_step
#include "genesis_machine.c"
#undef rr_md_z80_step
void rr_md_z80_step(z80 *z);
static int reference_path;
void fixture_z80_step(z80 *z) {
    if(reference_path)z80_step(z);else rr_md_z80_step(z);
}
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
static unsigned checks,events,reads,writes;
typedef struct { uint16_t address;uint8_t value,write;int64_t stamp; } Event;
static Event trace[32];
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static uint8_t read_byte(void *user,uint16_t address) {
    uint8_t value=gbus_z80_read(user,address);++reads;
    if(events<32)trace[events++]=(Event){address,value,0,rr_z80_time};
    return value;
}
static void write_byte(void *user,uint16_t address,uint8_t value) {
    gbus_z80_write(user,address,value);++writes;
    if(events<32)trace[events++]=(Event){address,value,1,rr_z80_time};
}
static void resume(void) {
    if(rr_z80_blocked) { rr_z80_grant=rr_z80_time+30;rr_z80_granted=1; }
    rr_z80_resume();
}
static void start(const uint8_t code[4],unsigned banked) {
    expose_fetch_gap=1;
    rr16_reset();GenesisMachine *m=&g_machine;
    g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
    m->bus.z80_reset_off=1;m->bus.z80_busreq=m->bus.z80_reset_pending=0;
    rr_md_z80_bus_reset();z80_own_reset(&m->z80);
    m->z80.read_byte=read_byte;m->z80.write_byte=write_byte;
    m->z80.pc=banked?0x8000:0;m->z80.sp=0x1800;m->z80.ix=0x100;m->z80.iy=0x120;
    m->z80.a=0x61;m->z80.r=0xff;m->z80.cyc=0;
    memset(m->bus.z80_ram,0x55,sizeof m->bus.z80_ram);memset(g_ram,0x55,65536);
    memcpy(banked?g_ram:m->bus.z80_ram,code,4);memcpy(g_ram+0x8000,code,4);
    m->bus.z80_bank=0x1c0;g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    events=reads=writes=0;memset(trace,0,sizeof trace);rr_md_z80_reset_evidence();
    rr_z80_start();rr_z80_limit=1;rr_bus_scheduling=1;
}
int main(void) {
    CHECK(rr16_init(true));
    static const struct { uint8_t code[4];unsigned byte,value; } cases[]={
        {{0x3e,0x9a},0,0},{{0xdd,0x21,0x9a},0,0xfd},
        {{0xdd,0x21,0x9a},1,0x3e},{{0xfd,0x21,0x9a},1,0x31},
        {{0xcb,0x46},1,0x86},{{0xed,0x43},1,0x53},
        {{0xdd,0xcb,0xf9,0x46},3,0x86},{{0xdd,0xfd,0x21},2,0x3e},
        {{0xdd,0xed,0x43},2,0x53},{{0x3e,0x9a},1,0x71},
        {{0xdd,0xcb,0xf9,0x46},2,0x01}};
    unsigned comparisons=0;
    for(unsigned i=0;i<sizeof cases/sizeof *cases;++i)for(unsigned banked=0;banked<3;++banked) {
        z80 result={0};uint8_t ram[8192],main_ram[65536];Event native_trace[32];
        unsigned native_events=0,native_reads=0,native_writes=0;
        for(unsigned ref=0;ref<2;++ref) {
            reference_path=ref;
            start(cases[i].code,banked);GenesisMachine *m=&g_machine;
            uint16_t pc=m->z80.pc,target=pc+cases[i].byte;
            unsigned attempts=0;
            do { CHECK(++attempts<64);resume(); }
            while(!(rr_z80_busy && m->z80.pc==target && rr_z80_checkpoint && !rr_z80_retiring));
            CHECK(!rr_md_z80_native_opcodes() && !rr_md_z80_fallback_opcodes());
            if(banked) {
                /* Real banked callback suspends before calculating its map.
                 * Neither the guard peek nor this WAIT returns an opcode. */
                rr_z80_resume();CHECK(rr_z80_blocked && rr_z80_request && m->z80.pc==target);
                if(banked==2) {
                    for(unsigned bit=0;bit<9;++bit)gbus_z80_write(&m->bus,0x6000,(0x1c1u>>bit)&1);
                    CHECK(m->bus.z80_bank==0x1c1);
                }
                gbus_write8(&m->bus,0xe00000+(banked==2?0x8000:0)+cases[i].byte,cases[i].value);
            } else {
                gbus_write8(&m->bus,0xa11100,1);
                rr_bus_slice(m,0,350,0,0);
                CHECK(machine_z80_bus_acknowledged() && rr_z80_busy && m->z80.pc==target);
                size_t n=99;CHECK(!rr16_state_capture(&n) && !n);
                gbus_write8(&m->bus,0xa00000+cases[i].byte,cases[i].value);
                gbus_write8(&m->bus,0xa11100,0);
            }
            expose_fetch_gap=0;
            rr_bus_scheduling=1;rr_z80_limit=1;attempts=0;
            do { CHECK(++attempts<64);resume(); } while(rr_z80_busy);
            rr_bus_scheduling=0;
            CHECK(!rr_md_z80_timing_misses() && !rr_md_bus_busy());
            if(!ref) {
                /* The last two cases change only live operands. */
                unsigned changed=i<9;
                CHECK(rr_md_z80_fallback_opcodes()==changed && rr_md_z80_native_opcodes()==!changed);
                CHECK(rr_md_z80_fallback_cycles()==(changed?m->z80.cyc:0));
                result=m->z80;memcpy(ram,m->bus.z80_ram,sizeof ram);memcpy(main_ram,g_ram,sizeof main_ram);
                memcpy(native_trace,trace,sizeof trace);native_events=events;native_reads=reads;native_writes=writes;
            } else {
                CHECK(!memcmp(&result,&m->z80,sizeof result));CHECK(!memcmp(ram,m->bus.z80_ram,sizeof ram));
                CHECK(!memcmp(main_ram,g_ram,sizeof main_ram));CHECK(events==native_events && reads==native_reads && writes==native_writes);
                for(unsigned e=0;e<events;++e) {
                    Event *a=&native_trace[e],*b=&trace[e];
                    if(a->address!=b->address || a->value!=b->value || a->write!=b->write || a->stamp!=b->stamp)
                        fprintf(stderr,"case %u bank %u event %u: %x/%x %u/%u at %lld/%lld\n",i,banked,e,
                            a->address,b->address,a->value,b->value,(long long)a->stamp,(long long)b->stamp);
                    CHECK(a->address==b->address && a->value==b->value && a->write==b->write && a->stamp==b->stamp);
                }
                ++comparisons;
            }
        }
    }
    rr16_shutdown();
    printf("{\"checks\":%u,\"fiber_comparisons\":%u,\"passed\":true,\"local_BUSACK\":true,\"banked_WAIT_and_map_change\":true,\"pin_timing_measured\":false}\n",checks,comparisons);
    return 0;
}
