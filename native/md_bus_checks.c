/* Authored bus ownership fixtures, linked with the actual generated backend.
 * This includes its private machine copy to drive individual Z80 slices. */
#include "platform_io.h"
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "genesis_runtime.h"
#include "sim_step.h"
#include "md_prefetch.h"
#include "genesis_machine.c"
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
static unsigned checks;
static unsigned pause_reads;
static int64_t pause_read_stamp;
static int64_t pause_resume_stamp;
static uint8_t pause_read(void *user,uint16_t address) {
    uint8_t value=gbus_z80_read((GenesisBus *)user,address);
    if(address==0x8000) { ++pause_reads;pause_read_stamp=rr_z80_time; }
    if(address==3)pause_resume_stamp=rr_z80_time;
    return value;
}
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static void dma(unsigned length,int display) {
    GVDP *v=&g_machine.vdp;
    gvdp_reset(v);v->reg[1]=0x10|(display?0x40:0);v->reg[12]=0x81;v->reg[15]=2;
    v->reg[19]=(uint8_t)length;v->reg[20]=(uint8_t)(length>>8);
    v->reg[21]=v->reg[22]=0;v->reg[23]=0x70;
    gvdp_write_control(v,0x4000);gvdp_write_control(v,0x0080);
}
static void z80_program(const uint8_t *code,size_t size) {
    rr_md_z80_bus_reset();
    GenesisMachine *m=&g_machine;
    memset(m->bus.z80_ram,0,sizeof m->bus.z80_ram);memcpy(m->bus.z80_ram,code,size);
    m->bus.z80_reset_off=1;m->bus.z80_busreq=m->bus.z80_reset_pending=0;
    z80_own_reset(&m->z80);m->z80.b=0;m->z80.cyc=m->z80_cycle_debt=0;
    m->bus.z80_bank=0x1c0; /* main RAM mirror at E00000 */
    rr_gun_slice_base=0;
}
static void gate_state(const wchar_t *path) {
    size_t size=123;CHECK(!rr16_state_ready());
    CHECK(!rr16_state_capture(&size) && !size);
    CHECK(!rr16_state_file(path,false));
    CHECK(!rr_exists(path));
}
static void prime_z80_absolute_request(int64_t request) {
    /* LD A,(nn)/LD (nn),A consume 4+3+3 T before the data cycle. These
     * 68000 arbitration fixtures need a request at a chosen clock, so start
     * the instruction in the preceding slice (possibly the preceding line).
     * Execute the real fetch/operand cycles; never bypass their timing. */
    rr_z80_start();rr_z80_time=request-150;rr_z80_limit=request+1;
    rr_bus_scheduling=1;
    do { rr_z80_resume(); } while(rr_z80_checkpoint);
    rr_bus_scheduling=0;
    CHECK(rr_z80_busy && rr_z80_blocked && rr_z80_request && rr_z80_time==request);
}
static void local_bus_cases(void) {
    GenesisMachine *m=&g_machine;
    /* Literal Zilog machine-cycle boundaries. No value is computed by the
     * implementation under test. Indexed address calculation extends the
     * displacement cycle; PUSH extends M1, and JR extends its operand cycle. */
    static const struct { uint8_t code[6];unsigned request,ack; } cases[]={
        {{0x3a,0,0x20,0x76},7,60},{{0x3a,0,0x20,0x76},70,105},
        {{0x3a,0,0x20,0x76},112,150},{{0x3a,0,0x20,0x76},161,195},
        {{0xdd,0x7e,0,0x76},7,60},{{0xdd,0x7e,0,0x76},70,120},
        {{0xdd,0x7e,0,0x76},133,240},{{0xdd,0x7e,0,0x76},252,285},
        {{0xe5,0x76},7,75},{{0xe5,0x76},84,120},{{0xe5,0x76},133,165},
        {{0x18,0,0x76},7,60},{{0x18,0,0x76},70,180},
        {{0x76},7,60},{{0x76},70,120}};
    for(unsigned i=0;i<sizeof cases/sizeof cases[0];++i)
    for(unsigned byte=0;byte<2;++byte)for(unsigned partition=0;partition<2;++partition) {
        rr16_reset();g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
        z80_program(cases[i].code,sizeof cases[i].code);m->z80.ix=0x2000;m->z80.sp=0x1800;
        g_audio_cycle_counter=rr_vdp_cpu_origin=0;rr_main_fraction=0;
        rr_bus_slice(m,0,cases[i].request,0,0);
        if(byte)gbus_write8(&m->bus,0xa11100,1);else gbus_write16(&m->bus,0xa11100,0x100);
        CHECK(!machine_z80_bus_acknowledged());
        CHECK(gbus_read16(&m->bus,0xa11100)==0x100 && gbus_peek16(&m->bus,0xa11100)==0x100);
        unsigned step=partition?7:350;
        for(unsigned begin=cases[i].request;begin<350;) {
            unsigned end=begin+step;if(end>350)end=350;
            rr_bus_slice(m,begin,end,0,0);begin=end;
        }
        if(rr_local_ack_time!=cases[i].ack)fprintf(stderr,"local case=%u ACK=%lld expected=%u\n",i,(long long)rr_local_ack_time,cases[i].ack);
        CHECK(rr_local_ack_time==cases[i].ack && machine_z80_bus_acknowledged());
        CHECK(gbus_read8(&m->bus,0xa11100)==0 && gbus_peek16(&m->bus,0xa11100)==0);
        unsigned long nominal=m->z80.cyc;int64_t paused=rr_z80_time;
        rr_bus_slice(m,350,700,0,0);
        CHECK(m->z80.cyc==nominal && rr_z80_time==paused);
        gbus_write8(&m->bus,0xa11100,0);
        CHECK(!machine_z80_bus_acknowledged() && rr_z80_time==705);
        rr_bus_slice(m,700,1400,0,0);CHECK(m->z80.cyc>nominal);
    }
    /* A pulse which ends before the next cycle does not grant ownership or
     * insert a pause. HALT still reaches M1 boundaries, and an IRQ arriving
     * while ACK is held is accepted only after the bus is released. */
    rr16_reset();g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
    const uint8_t halt[]={0x76};z80_program(halt,sizeof halt);
    g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    rr_bus_slice(m,0,7,0,0);gbus_write8(&m->bus,0xa11100,1);
    g_audio_cycle_counter=2;gbus_write8(&m->bus,0xa11100,0);
    CHECK(!rr_local_ack && rr_z80_time==60);
    rr_bus_slice(m,14,70,0,0);gbus_write8(&m->bus,0xa11100,1);
    rr_bus_slice(m,70,210,0,0);CHECK(rr_local_ack_time==120 && m->z80.halted);
    m->z80.iff1=m->z80.iff2=1;m->z80.interrupt_mode=1;z80_gen_int(&m->z80,0xff);
    rr_bus_slice(m,210,420,0,0);CHECK(m->z80.halted && m->z80.pc==1);
    gbus_write8(&m->bus,0xa11100,0);rr_bus_slice(m,420,900,0,0);
    CHECK(!m->z80.halted && m->z80.pc>=0x38);
    /* Real 68000 code writes BUSREQ, polls its high status byte, releases it,
     * then STOPs. The local Z80 keeps running before and after the handshake. */
    rr16_reset();g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    const uint16_t control[]={0x13fc,1,0x00a1,0x1100,0x1039,0x00a1,0x1100,
        0x66f8,0x13fc,0,0x00a1,0x1100,0x4e72,0x2700};
    for(unsigned i=0;i<sizeof control/sizeof control[0];++i)gbus_write16(&m->bus,0xff0100+2*i,control[i]);
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
    const uint8_t loop[]={0x04,0xc3,0,0};z80_program(loop,sizeof loop);
    machine_run_frame(NULL,NULL);
    CHECK(rr_md_cpu_stopped && g_cpu.PC==0xff011c && (g_cpu.D[0]&0xff)==0);
    CHECK(!m->bus.z80_busreq && m->z80.b && rr16_state_ready());
}
static int checks_main(int argc,wchar_t **argv) {
    CHECK(argc==2 && rr16_init(true));rr_remove(argv[1]);
    GenesisMachine *m=&g_machine;GVDP *v=&m->vdp;
    /* BUSREQ is a request, not an instantaneous BUSACK. The running Z80 must
     * reach a machine-cycle boundary before ownership is acknowledged. */
    rr16_reset();m->bus.z80_reset_off=1;
    g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    gbus_write8(&m->bus,0xa11100,1);
    CHECK(gbus_read16(&m->bus,0xa11100)==0x100);
    local_bus_cases();
    /* First word completes a DMA command; the second changes autoincrement.
     * A 65536-word active transfer crosses a whole host frame. */
    for(int h40=0;h40<2;++h40) {
        rr16_reset();
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;g_cpu.A[0]=0xc00004;g_cpu.D[0]=0x00808f06;
        uint16_t code[]={0x2080,0x4e72,0x2700}; /* MOVE.L D0,(A0); STOP */
        for(unsigned i=0;i<3;++i)gbus_write16(&m->bus,0xff0100+2*i,code[i]);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        const uint8_t sound[]={0x3e,0x27,0x32,0x00,0x40,0x3e,0x05,0x32,0x01,0x40,0x04,0xc3,0x0a,0};
        z80_program(sound,sizeof sound);
        dma(0,1);v->rr_dma.mode=v->rr_dma.remaining=0;v->dma_active=0;
        v->reg[12]=h40?0x81:0;
        gvdp_write_control(v,0x4000); /* leave the first command half latched */
        machine_run_frame(NULL,NULL);
        CHECK(gvdp_dma_blocks_cpu(v) && rr16_md_instruction_busy());
        CHECK(v->reg[15]==2 && g_cpu.PC==0xff0100);
        CHECK(m->z80.b!=0 && m->bus.ym_addr[0]==0x27 && m->bus.ym_mode==5);
        gate_state(argv[1]);
        unsigned frames=1;
        /* Maximum-length active H32 DMA exceeds twelve NTSC frames. This is
         * a bounded liveness test, not a claim of a measured DMA duration. */
        while(rr_md_bus_busy() && frames++<32)machine_run_frame(NULL,NULL);
        CHECK(frames<32 && rr16_state_ready());
        CHECK(v->reg[15]==6 && !gvdp_dma_blocks_cpu(v));
        CHECK(g_cpu.PC==0xff0106 && g_cpu.A[0]==0xc00004);
        CHECK(rr16_state_file(argv[1],false));
        CHECK(rr16_state_file(argv[1],true));rr_remove(argv[1]);
    }
    /* Main CPU opcode is RAM-authored, hence intentionally uses the decoded
     * reference path above; native ROM dispatch is covered by game probes. */
    rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    const uint8_t push[]={0xe5,0x76}; /* PUSH HL then HALT */
    z80_program(push,sizeof push);m->z80.sp=0x8002;m->z80.h=0x12;m->z80.l=0x34;
    g_ram[0]=0xaa;g_ram[1]=0xbb;dma(4,1);
    step_z80(m,14);
    CHECK(rr_z80_busy && rr_z80_blocked && m->z80.sp==0x8001);
    CHECK(g_ram[0]==0xaa && g_ram[1]==0xbb);gate_state(argv[1]);
    CHECK(m->z80_cycle_debt==0);
    /* BUSREQ pauses this already pending instruction too. */
    m->bus.z80_busreq=1;gvdp_dma_wait_until(v,3420);
    CHECK(!gvdp_dma_blocks_cpu(v));step_z80(m,14);
    CHECK(m->z80.sp==0x8001 && g_ram[1]==0xbb);
    m->bus.z80_busreq=0;step_z80(m,14);
    CHECK(!rr_z80_busy && !rr_z80_blocked && rr16_state_ready());
    CHECK(m->z80.sp==0x8000 && g_ram[0]==0x34 && g_ram[1]==0x12);
    CHECK(rr16_state_file(argv[1],false));
    CHECK(rr16_state_file(argv[1],true));rr_remove(argv[1]);
    /* Banked data read uses the post-DMA value, not a speculative early read. */
    const uint8_t read[]={0x3a,0x00,0x80,0x76};
    z80_program(read,sizeof read);m->z80.a=0x55;g_ram[0]=0x11;dma(4,1);step_z80(m,14);
    CHECK(rr_z80_blocked && m->z80.a==0x55);
    g_ram[0]=0x22;gvdp_dma_wait_until(v,3420);step_z80(m,14);
    CHECK(!rr_z80_busy && m->z80.a==0x22);
    /* Banked opcode fetch cannot advance PC during DMA either. */
    z80_program(read,sizeof read);m->z80.pc=0x8000;g_ram[0]=0x04;g_ram[1]=0x76;
    dma(4,1);step_z80(m,14);CHECK(rr_z80_blocked && m->z80.pc==0x8000 && !m->z80.b);
    gvdp_dma_wait_until(v,3420);step_z80(m,14);
    CHECK(!rr_z80_busy && m->z80.b==1);
    /* Reset discards a live C continuation rather than resuming it in new RAM. */
    z80_program(push,sizeof push);m->z80.sp=0x8002;dma(4,1);step_z80(m,14);
    CHECK(rr_z80_blocked);rr16_reset();CHECK(rr16_state_ready() && !rr_z80_fiber);
    /* Internal fill/copy do not own the external bus. */
    for(unsigned mode=2;mode<=3;++mode) {
        z80_program(read,sizeof read);gvdp_reset(v);g_ram[0]=0x37;
        v->reg[1]=0x50;v->reg[12]=0x81;v->reg[15]=2;
        v->rr_dma.mode=mode;v->rr_dma.remaining=1024;v->rr_dma.code=1;v->rr_dma.increment=2;v->dma_active=1;
        step_z80(m,14);CHECK(!rr_z80_busy && m->z80.a==0x37);
    }
    /* Clocked requests, through the same arbiter as machine_run_frame. The
     * source release precedes the first active-display destination slot. */
    for(int h40=0;h40<2;++h40) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
        uint16_t stop[]={0x4e72,0x2700};
        for(unsigned i=0;i<2;++i)gbus_write16(&m->bus,0xff0100+2*i,stop[i]);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        z80_program(read,sizeof read);m->z80.a=0x55;g_ram[0]=0x39;
        dma(2,1);v->reg[12]=h40?0x81:0;
        unsigned release=gvdp_dma_wait_until(v,213);
        CHECK(!gvdp_dma_blocks_cpu(v) && v->rr_fifo.count==2);
        CHECK(release==(h40?33:40));
        dma(2,1);v->reg[12]=h40?0x81:0;
        prime_z80_absolute_request(0);
        uint64_t requests=rr_bus_requests,stolen=rr_bus_stolen_cycles;
        rr_bus_slice(m,0,213,0,0);
        CHECK(m->z80.a==0x39 && !rr_z80_blocked);
        CHECK(rr_z80_grant==75);
        CHECK(rr_z80_grant<213 && v->rr_fifo.count==2);
        CHECK(rr_bus_requests==requests && rr_bus_stolen_cycles==stolen+4);
        CHECK(g_audio_cycle_counter>=213/7);
    }
    /* Same instruction under different host partitioning: an unfinished
     * transfer retains its timestamp and side effects exactly once. */
    for(int split=0;split<2;++split) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
        gbus_write16(&m->bus,0xff0100,0x4e72);gbus_write16(&m->bus,0xff0102,0x2700);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        z80_program(read,sizeof read);g_ram[0]=0x41;
        prime_z80_absolute_request(0);
        uint64_t requests=rr_bus_requests;
        if(split) {
            rr_bus_slice(m,0,20,0,0);
            CHECK(rr_z80_blocked && rr_z80_request && m->z80.a!=0x41);
            gate_state(argv[1]);
        }
        rr_bus_slice(m,split?20:0,213,0,0);
        CHECK(m->z80.a==0x41 && !rr_z80_busy);
        CHECK(rr_bus_requests==requests);
        /* The 10T before this request happened in the previous slice. */
        CHECK(rr_z80_grant==30 && rr_z80_time==255);
    }
    /* Unprimed instructions request the shared bus after their real local
     * fetch/operand phases. DIVU keeps the main bus free during this window.
     * Literal grants include the /7 and /15 clock edges, not board pins. */
    static const uint8_t phase_code[3][6]={{0x3a,0,0x80,0x76},
        {0xdd,0x3a,0,0x80,0x76},{0xdd,0xcb,0,0x06,0x76}};
    static const unsigned grants[3][7]={{195,195,180,180,180,195,195},
        {240,255,255,255,255,240,240},{390,390,390,375,360,360,390}};
    for(unsigned kind=0;kind<3;++kind)for(unsigned fraction=0;fraction<7;++fraction)
    for(unsigned partition=0;partition<3;++partition) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;rr_main_fraction=fraction;
        g_cpu.SR=0x2700;g_cpu.D[0]=0;g_cpu.D[1]=1;g_cpu.A[7]=0xffff00;
        gbus_write16(&m->bus,0xff0100,0x80c1);gbus_write16(&m->bus,0xff0102,0x4e72);
        gbus_write16(&m->bus,0xff0104,0x2700);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        rr_md_prefetch=(RrMdPrefetch){0xff0100,2,{0x80c1,0x4e72}};
        z80_program(phase_code[kind],sizeof phase_code[0]);m->z80.ix=0x8000;g_ram[0]=0x11;
        uint64_t requests=rr_bus_requests,misses=rr_md_z80_timing_misses();
        unsigned step=partition==1?7:partition==2?31:700;
        for(unsigned begin=0;begin<700;) {
            unsigned end=begin+step;if(end>700)end=700;
            rr_bus_slice(m,begin,end,0,fraction);begin=end;
        }
        if(rr_z80_grant!=grants[kind][fraction])fprintf(stderr,"phase kind=%u fraction=%u part=%u grant=%lld expected=%u\n",
            kind,fraction,partition,(long long)rr_z80_grant,grants[kind][fraction]);
        CHECK(rr_z80_grant==grants[kind][fraction]);
        CHECK(rr_bus_requests==requests+(kind==2?2:1));
        CHECK(kind==2?g_ram[0]==0x22:m->z80.a==0x11);
        CHECK(rr_md_z80_timing_misses()==misses && !rr_z80_busy);
    }
    /* Start with an already filled instruction queue. MOVE.L's first operand
     * word completes at tick 28, so a request at tick 21 waits for that cycle.
     * The nominal reservation ends at 56, rounded to the Z80 edge at 60. The
     * low operand word then sees the Z80 write. No fictitious opcode read is
     * charged ahead of the operand, and neither word is replayed. */
    for(int split=0;split<2;++split) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;g_cpu.A[0]=0xff0200;
        gbus_write16(&m->bus,0xff0100,0x2010);
        gbus_write16(&m->bus,0xff0102,0x4e72);gbus_write16(&m->bus,0xff0104,0x2700);
        gbus_write16(&m->bus,0xff0200,0x1122);gbus_write16(&m->bus,0xff0202,0x3344);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        rr_md_prefetch=(RrMdPrefetch){0xff0100,2,{0x2010,0x4e72}};
        const uint8_t writer[]={0x32,0x02,0x82,0x76};
        z80_program(writer,sizeof writer);m->z80.a=0x99;prime_z80_absolute_request(21);
        if(split) {
            rr_bus_slice(m,0,30,0,0);
            CHECK(rr16_md_instruction_busy() && rr_z80_granted);
            CHECK(g_cpu.PC==0xff0100 && g_ram[0x202]==0x33);
            gate_state(argv[1]);
        }
        rr_bus_slice(m,split?30:0,213,0,0);
        CHECK(g_cpu.D[0]==0x11229944 && g_cpu.PC==0xff0106);
        CHECK(g_ram[0x202]==0x99 && rr_z80_grant==60);
        CHECK(!rr16_md_instruction_busy());
    }
    /* Operand-dependent internal loops retain different stream phases.
     * The Z80 changes STOP's immediate after MUL's early read, but before
     * DIV's late read. Neither unfinished instruction may become an F8 state. */
    for(int divide=0;divide<2;++divide)for(int split=0;split<2;++split) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;g_cpu.D[0]=0;g_cpu.D[1]=1;
        unsigned op=divide?0x80c1:0xc0c1;
        gbus_write16(&m->bus,0xff0100,(uint16_t)op);
        gbus_write16(&m->bus,0xff0102,0x4e72);gbus_write16(&m->bus,0xff0104,0x2700);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        rr_md_prefetch=(RrMdPrefetch){0xff0100,2,{(uint16_t)op,0x4e72}};
        const uint8_t writer[]={0x32,0x05,0x81,0x76};
        z80_program(writer,sizeof writer);m->z80.a=0x15;prime_z80_absolute_request(35);
        if(split) {
            rr_bus_slice(m,0,21,0,0);
            /* Both internal loops must yield before retiring: an internal
             * operation is not a reservation of the external main bus. */
            CHECK(rr16_md_instruction_busy());gate_state(argv[1]);
        }
        rr_bus_slice(m,split?21:0,1500,0,0);
        CHECK(g_ram[0x105]==0x15 && rr_md_cpu_stopped && g_cpu.PC==0xff0106);
        CHECK(g_cpu.SR==(divide?0x2715:0x2700) && g_cpu.D[0]==0);
        CHECK(!rr16_md_instruction_busy() && rr16_state_ready());
        CHECK(rr_z80_grant==75); /* Request at 35, four nominal clocks, Z80 edge. */
    }
    /* Internal work overlaps an external reservation rather than being
     * charged twice. Test host partitions, divider fractions and 32-bit
     * counter wrap against literal MULU/DIVU costs (0 by 1: 40/136 clocks). */
    for(int divide=0;divide<2;++divide)for(unsigned fraction=0;fraction<7;++fraction)
    for(unsigned partition=0;partition<3;++partition)for(unsigned wrap=0;wrap<2;++wrap) {
        rr16_reset();
        uint32_t origin=wrap?0xfffffff0u:0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;g_cpu.D[0]=0;g_cpu.D[1]=1;
        unsigned op=divide?0x80c1:0xc0c1,clocks=divide?136:40;
        gbus_write16(&m->bus,0xff0100,(uint16_t)op);
        gbus_write16(&m->bus,0xff0102,0x4e72);gbus_write16(&m->bus,0xff0104,0x2700);
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        rr_md_prefetch=(RrMdPrefetch){0xff0100,2,{(uint16_t)op,0x4e72}};
        z80_program(read,sizeof read);g_ram[0]=0x69;prime_z80_absolute_request(35);
        g_audio_cycle_counter=rr_vdp_cpu_origin=origin;rr_main_fraction=fraction;
        uint64_t misses=rr_md_bus_budget_misses,requests=rr_bus_requests;
        unsigned end=clocks*7-fraction,step=partition==1?7:partition==2?23:end;
        for(unsigned begin=0;begin<end;) {
            unsigned cut=begin+step;if(cut>end)cut=end;
            rr_bus_slice(m,begin,cut,origin,fraction);begin=cut;
        }
        if(g_cpu.PC!=0xff0102 || rr16_md_instruction_busy())
            fprintf(stderr,"idle divide=%d fraction=%u partition=%u wrap=%u pc=%x cycles=%u busy=%d grant=%lld\n",
                divide,fraction,partition,wrap,g_cpu.PC,g_audio_cycle_counter-origin,
                rr16_md_instruction_busy(),(long long)rr_z80_grant);
        CHECK(g_cpu.PC==0xff0102 && !rr16_md_instruction_busy());
        CHECK(g_cpu.D[0]==0 && g_audio_cycle_counter-origin==clocks);
        CHECK(g_cycle_accumulator==clocks);
        CHECK(m->z80.a==0x69 && rr_z80_grant==75);
        CHECK(rr_bus_requests==requests && rr_md_bus_budget_misses==misses);
        CHECK(rr16_state_ready());
    }
    /* V-int enters on the main fiber. A Z80 reservation can suspend its
     * stack writes; pending IRQ/partial frame never becomes a disk state. */
    uint8_t saved_vector[4];memcpy(saved_vector,g_rom+0x78,4);
    for(int split=0;split<3;++split) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.PC=0xff0100;g_cpu.SR=0x2015;g_cpu.A[7]=0xfff000;
        gbus_write16(&m->bus,0xff0100,0x4e71);
        gbus_write16(&m->bus,0xff0300,0x4e72);gbus_write16(&m->bus,0xff0302,0x2700);
        g_rom[0x78]=0;g_rom[0x79]=0xff;g_rom[0x7a]=3;g_rom[0x7b]=0;
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
        z80_program(read,sizeof read);g_ram[0]=0x41;
        gvdp_reset(v);v->reg[1]=0x20;v->vint_pending=1;
        prime_z80_absolute_request(0);
        unsigned cut=split==1?80:120;
        if(split) {
            rr_bus_slice(m,0,cut,0,0);
            CHECK(rr16_md_instruction_busy());
            CHECK(v->vint_pending==(split==1));
            gate_state(argv[1]);
        }
        rr_bus_slice(m,split?cut:0,700,0,0);
        CHECK(g_cpu.PC==0xff0304 && rr_md_cpu_stopped && g_cpu.A[7]==0xffeffa);
        CHECK(gbus_peek16(&m->bus,0xffeffa)==0x2015);
        CHECK(gbus_peek16(&m->bus,0xffeffc)==0xff && gbus_peek16(&m->bus,0xffeffe)==0x0100);
        CHECK(!v->vint_pending && !rr16_md_instruction_busy() && rr16_state_ready());
    }
    memcpy(g_rom+0x78,saved_vector,4);
    /* RAM can differ from words already fetched. F9 must retain that queue,
     * rather than reconstruct it from the modified RAM. */
    rr16_reset();g_cpu.PC=0xff0100;g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
    gbus_write16(&m->bus,0xff0100,0x7022);gbus_write16(&m->bus,0xff0102,0x4e71);
    gbus_write16(&m->bus,0xff0104,0x4e72);gbus_write16(&m->bus,0xff0106,0x2700);
    rr_md_prefetch=(RrMdPrefetch){0xff0100,2,{0x7011,0x4e71}};
    genesis_sim_set_tick_count(1); /* A live pipeline is not an unstarted boot state. */
    size_t queue_size;uint8_t *queue_state=rr16_state_capture(&queue_size);
    CHECK(queue_state && queue_size && rr16_state_ready());
    rr_md_prefetch.words[0]=0x7033;g_ram[0x101]=0x44;
    CHECK(rr16_state_restore(queue_state,queue_size));free(queue_state);
    CHECK(rr_md_prefetch.pc==0xff0100 && rr_md_prefetch.valid==2 && rr_md_prefetch.words[0]==0x7011);
    CHECK(g_ram[0x101]==0x22);
    machine_run_frame(NULL,NULL);
    CHECK(g_cpu.D[0]==0x11 && g_cpu.PC==0xff0108 && rr_md_cpu_stopped);
    CHECK(rr16_state_file(argv[1],false) && rr16_state_file(argv[1],true));rr_remove(argv[1]);
    /* STOP does no bus work. An unprimed Z80 data request at 10T=150 master
     * clocks must not wait for an invented four-cycle idle instruction. */
    static const unsigned stop_grants[7]={195,195,180,180,180,195,195};
    for(unsigned fraction=0;fraction<7;++fraction)
    for(unsigned partition=0;partition<3;++partition)for(unsigned wrap=0;wrap<2;++wrap) {
        rr16_reset();
        uint32_t origin=wrap?0xfffffff0u:0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
        z80_program(read,sizeof read);g_ram[0]=0x72;
        g_audio_cycle_counter=rr_vdp_cpu_origin=origin;rr_main_fraction=fraction;
        unsigned step=partition==1?7:partition==2?31:700;
        for(unsigned begin=0;begin<700;) {
            unsigned end=begin+step;if(end>700)end=700;
            rr_bus_slice(m,begin,end,origin,fraction);begin=end;
        }
        if(rr_z80_grant!=stop_grants[fraction])fprintf(stderr,
            "STOP fraction=%u partition=%u wrap=%u grant=%lld expected=%u\n",
            fraction,partition,wrap,(long long)rr_z80_grant,stop_grants[fraction]);
        CHECK(rr_z80_grant==stop_grants[fraction]);
        CHECK(g_audio_cycle_counter-origin==(700+fraction)/7);
        CHECK(g_cpu.PC==0xff0100 && rr_md_cpu_stopped && m->z80.a==0x72);
        CHECK(!rr_md_bus_busy() && rr16_state_ready());
    }
    /* A BUSREQ arriving during a WAIT-extended read cannot revoke that read.
     * It finishes once at 30; the next cycle is held, resuming at release. */
    rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
    const uint8_t twice[]={0x3a,0,0x80,0x3a,0,0x80,0x76};
    z80_program(twice,sizeof twice);g_ram[0]=0x58;
    m->z80.read_byte=pause_read;pause_reads=0;
    prime_z80_absolute_request(0);
    uint64_t paused_stolen=rr_bus_stolen_cycles;
    rr_bus_slice(m,0,20,0,0);CHECK(rr_z80_granted && !pause_reads);
    gbus_write16(&m->bus,0xa11100,0x100);
    rr_bus_slice(m,20,420,0,0);CHECK(pause_reads==1 && pause_read_stamp==30 && rr_z80_busy);
    CHECK(machine_z80_bus_acknowledged() && rr_local_ack_time==75);
    gate_state(argv[1]);
    gbus_write16(&m->bus,0xa11100,0);
    rr_bus_slice(m,420,630,0,0);
    CHECK(pause_resume_stamp==420 && pause_reads==2 && m->z80.a==0x58);
    CHECK(rr_bus_stolen_cycles==paused_stolen+8 && !rr_z80_busy);
    /* Word/byte release edges, a pause across an entire raster frame, and a
     * reset pulse which discards the old expression before restarting PC=0. */
    static const unsigned resume_edges[5]={420,435,435,450,450};
    for(unsigned reset=0;reset<2;++reset)for(unsigned frame_pause=0;frame_pause<2;++frame_pause)
    for(unsigned edge=0;edge<5;++edge) {
        rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
        g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
        rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
        z80_program(twice,sizeof twice);g_ram[0]=0x58;m->z80.a=0x19;
        m->z80.read_byte=pause_read;pause_reads=0;
        prime_z80_absolute_request(0);rr_bus_slice(m,0,20,0,0);
        gbus_write8(&m->bus,0xa11100,1);
        /* First read must finish before BUSACK; reset can then cancel the
         * remaining expression without allowing the following read. */
        rr_bus_slice(m,20,210,0,0);
        CHECK(pause_reads==1 && pause_read_stamp==30 && m->z80.a==0x58);
        if(reset)gbus_write8(&m->bus,0xa11200,0);
        if(frame_pause) {
            machine_run_frame(NULL,NULL);
            CHECK(pause_reads==1 && rr_z80_busy && m->z80.a==0x58);
            /* Start a fresh line with explicit divider phase for the authored
             * edge assertion. The live pending request retains its old time. */
            g_audio_cycle_counter=rr_vdp_cpu_origin=0;rr_main_fraction=0;
            gvdp_reset(v);
        }
        unsigned release=(60+edge)*7;
        rr_bus_slice(m,frame_pause?0:210,release,0,0);
        CHECK(pause_reads==1 && m->z80.a==0x58);
        unsigned long nominal=m->z80.cyc;
        if(reset) {
            /* Releasing reset while BUSREQ is held must not run the CPU. */
            gbus_write16(&m->bus,0xa11200,0x100);
            CHECK(pause_reads==1 && m->bus.z80_reset_pending);
        }
        gbus_write8(&m->bus,0xa11100,0);
        CHECK(rr_z80_time==resume_edges[edge] && m->z80.cyc==nominal);
        if(reset) {
            /* New program has no banked access: an obsolete read must never
             * commit after reset, even when its grant had already completed. */
            m->bus.z80_ram[0]=0x04;m->bus.z80_ram[1]=0x76; /* INC B; HALT */
        }
        rr_bus_slice(m,release,900,0,0);
        if(reset)CHECK(pause_reads==1 && m->z80.b==1 && m->z80.halted && !m->bus.z80_reset_pending);
        else CHECK(pause_reads==2 && pause_resume_stamp==resume_edges[edge] && m->z80.a==0x58);
        CHECK(!rr_md_bus_busy() && rr16_state_ready());
        /* Redundant deassertions must not move the running clock backwards. */
        int64_t now=rr_z80_time;gbus_write16(&m->bus,0xa11100,0);CHECK(rr_z80_time==now);
    }
    /* Carry the divider remainder between frames. Repeated floor(frame/7)
     * would lose real master-clock time in PAL and NTSC alike. */
    rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    gbus_write16(&m->bus,0xff0100,0x4e72);gbus_write16(&m->bus,0xff0102,0x2700);
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
    m->bus.z80_reset_off=0;
    for(unsigned frame=0;frame<11;++frame) {
        uint32_t before_cpu=g_audio_cycle_counter;
        uint32_t clocks=(rr_main_fraction+RR_MD_LINES*3420u)/7u;
        unsigned debt=rr_main_debt;
        machine_run_frame(NULL,NULL);
        /* No pseudo-instruction debt remains once STOP has been entered. */
        CHECK(g_audio_cycle_counter-before_cpu+debt==clocks+rr_main_debt);
        CHECK(rr_main_debt==0);
        CHECK(!rr_md_bus_busy());
    }
    /* Persist the phase/debt in the old tail padding, including counter wrap.
     * Eleven frames must follow floor(total master/7), with one final residue. */
    CHECK(g_audio_cycle_counter==(11u*RR_MD_LINES*3420u)/7u+rr_main_debt);
    unsigned phase=rr_main_fraction,debt=rr_main_debt;
    size_t n=machine_rb_save(NULL,0);void *clock_state=malloc(n);
    CHECK(clock_state && machine_rb_save(clock_state,n)==n);
    machine_run_frame(NULL,NULL);CHECK(machine_rb_load(clock_state,n));
    CHECK(rr_main_fraction==phase && rr_main_debt==debt);
    uint32_t bad_clock=0x80000007u;
    memcpy((uint8_t *)clock_state+sizeof(GenesisMachine)+20,&bad_clock,4);
    CHECK(!machine_rb_load(clock_state,n));
    CHECK(rr_main_fraction==phase && rr_main_debt==debt);free(clock_state);
    /* A banked pending instruction also crosses the old 32-bit machine-clock
     * wrap. It must resume rather than compare a future epoch with zero. */
    rr16_reset();g_audio_cycle_counter=rr_vdp_cpu_origin=0;
    g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
    gbus_write16(&m->bus,0xff0100,0x4e72);gbus_write16(&m->bus,0xff0102,0x2700);
    rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);
    z80_program(read,sizeof read);g_ram[0]=0x63;dma(1024,1);
    m->master_cycle=0xfffff800u;
    rr_main_fraction=6;
    machine_run_frame(NULL,NULL);
    CHECK(m->master_cycle<0xfffff800u && m->z80.a==0x63);
    CHECK(!rr_z80_busy && rr16_state_ready());
    CHECK(rr_main_fraction==(6u+RR_MD_LINES*3420u)%7u);
    CHECK(rr16_state_file(argv[1],false));CHECK(rr16_state_file(argv[1],true));rr_remove(argv[1]);
    rr16_shutdown();
    printf("{\"checks\":%u,\"passed\":true,\"actual_backend\":true,\"authored_fixtures\":true,\"pin_timing_measured\":false}\n",checks);
    return 0;
}

#ifdef _WIN32
int wmain(int argc,wchar_t **argv) { return checks_main(argc,argv); }
#else
int main(int argc,char **argv) {
    wchar_t path[4096];
    CHECK(argc==2 && rr_from_utf8(argv[1],path,sizeof path/sizeof *path));
    wchar_t *args[]={L"checks",path};return checks_main(argc,args);
}
#endif
