/* Authored Super FX (GSU) checks.
 *
 * Every program and every expected value comes from tools/snes_superfx_model.py, an
 * independent model written from nocash's fullsnes GSU chapter (see that file for what is
 * documented and what rests on ares semantics). The tables are generated into
 * snes_superfx_cases.h; nothing here is derived from running superfx.c.
 *
 * Each case is driven the way the S-CPU does it: cartridge registers at $3000-$303F, the
 * program in a synthetic Game Pak ROM, start by writing the high byte of R15, then the
 * shared master clock is advanced with superfx_sync(). */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "snes/superfx.h"
#include "snes/saveload.h"

#define RR_GSU_ROM_SIZE 0x20000u
#define RR_GSU_RAM_SIZE 0x20000u
typedef struct {uint32_t index,len;const uint8_t *data;} RrGsuPatch;
typedef struct {uint16_t mask;uint16_t r[16];} RrGsuJob;
typedef struct {
    const char *name;
    uint8_t mode,clsr,cfgr,scmr,scbr,pbr,sfr_init,timed,finding,ares,njobs;
    const RrGsuJob *jobs;
    uint16_t nrom;const RrGsuPatch *rom;
    uint16_t nram;const RrGsuPatch *ram;
    const uint8_t *cache;
    uint16_t nresume;const uint32_t *resume;
    uint16_t r[16],sfr,sfr_mask;
    uint8_t rombr,rambr,exp_pbr;
    uint16_t cbr;
    uint32_t ram_crc;
    uint16_t nexp;const RrGsuPatch *exp;
    uint16_t ncache;const RrGsuPatch *cc;
    uint32_t hits,direct,fills,extra;
    int32_t base;uint16_t cyc_lo,cyc_hi;uint8_t no_ram;
} RrGsuCase;
#include "snes_superfx_cases.h"

typedef struct {SaveLoadInfo stream;unsigned pos;bool load;uint8_t bytes[2048];} Stream;
static void transfer(SaveLoadInfo *s,void *data,size_t n){Stream *p=(Stream*)s;
    if(p->pos+n>sizeof p->bytes){fprintf(stderr,"state stream too small\n");exit(1);}
    if(p->load)memcpy(data,p->bytes+p->pos,n);else memcpy(p->bytes+p->pos,data,n);p->pos+=(unsigned)n;}

static uint8_t rom_image[RR_GSU_ROM_SIZE],ram_image[RR_GSU_RAM_SIZE],ram_second[RR_GSU_RAM_SIZE];
static unsigned long self_timed_checks,range_checks,total_checks,total_bad,total_cases,ares_checks,timed_checks,resume_runs;
static unsigned long finding_cases[16],finding_diff_cases[16],finding_diffs[16],finding_checks[16];
static unsigned printed;
static uint32_t durations[sizeof rr_gsu_cases/sizeof rr_gsu_cases[0]];

typedef struct {const RrGsuCase *c;unsigned diffs;} Ctx;
static void expect(Ctx *x,const char *label,uint32_t got,uint32_t want){
    total_checks++;
    if(x->c->ares&&!strcmp(label,"SFR"))ares_checks++;
    if(x->c->finding)finding_checks[x->c->finding]++;
    if(got==want)return;
    x->diffs++;
    if(x->c->finding){
        finding_diffs[x->c->finding]++;
        if(printed<3000){printed++;printf("FINDING %u %s %s got %x expected %x\n",x->c->finding,x->c->name,label,got,want);}
    } else {
        total_bad++;
        if(printed<3000){printed++;printf("MISMATCH %s %s got %x expected %x\n",x->c->name,label,got,want);}
    }
}

static void expect_strict(Ctx *x,const char *label,uint32_t got,uint32_t want){
    total_checks++;
    if(got==want)return;
    x->diffs++;total_bad++;
    if(printed<3000){printed++;printf("MISMATCH %s %s got %x expected %x\n",x->c->name,label,got,want);}
}

static uint32_t crc32_of(const uint8_t *p,size_t n){
    static uint32_t table[256];static bool ready;
    if(!ready){for(uint32_t i=0;i<256;i++){uint32_t c=i;for(int k=0;k<8;k++)c=c&1?0xEDB88320u^(c>>1):c>>1;table[i]=c;}ready=true;}
    uint32_t c=0xFFFFFFFFu;while(n--)c=table[(c^*p++)&255]^(c>>8);return c^0xFFFFFFFFu;
}

static void write_reg(SuperFx *f,unsigned n,uint16_t v){
    superfx_cpu_write_io(f,(uint16_t)(0x3000+2*n),(uint8_t)v);
    if(n!=15)superfx_cpu_write_io(f,(uint16_t)(0x3001+2*n),(uint8_t)(v>>8));
}
static uint16_t read_reg(SuperFx *f,unsigned n){
    return (uint16_t)(superfx_cpu_read_io(f,(uint16_t)(0x3000+2*n))|(superfx_cpu_read_io(f,(uint16_t)(0x3001+2*n))<<8));
}
static void apply(uint8_t *dst,uint32_t size,const RrGsuPatch *p,unsigned n){
    for(unsigned i=0;i<n;i++){if(p[i].index+p[i].len>size){fprintf(stderr,"patch out of range\n");exit(1);}
        memcpy(dst+p[i].index,p[i].data,p[i].len);}
}

typedef struct {SuperFx *fx;uint8_t *ram;uint64_t clock;} Run;

static void configure(const RrGsuCase *c,Run *r){
    SuperFx *f=r->fx;
    superfx_sync(f,r->clock);
    superfx_cpu_write_io(f,0x3037,c->cfgr);superfx_cpu_write_io(f,0x3039,c->clsr);
    superfx_cpu_write_io(f,0x303a,c->scmr);superfx_cpu_write_io(f,0x3038,c->scbr);
    superfx_cpu_write_io(f,0x3034,c->pbr);                       /* flushes the cache */
    superfx_cpu_write_io(f,0x3030,c->sfr_init);                  /* flags only, GO stays 0 */
    if(c->mode==1&&c->cache)for(unsigned i=0;i<512;i++)superfx_cpu_write_io(f,(uint16_t)(0x3100+i),c->cache[i]);
}
static void start_job(const RrGsuCase *c,const RrGsuJob *j,Run *r){
    SuperFx *f=r->fx;
    for(unsigned n=0;n<15;n++)if(j->mask&(1u<<n))write_reg(f,n,j->r[n]);
    if(j->mask&0x8000u){superfx_cpu_write_io(f,0x301e,(uint8_t)j->r[15]);superfx_cpu_write_io(f,0x301f,(uint8_t)(j->r[15]>>8));}
    else superfx_cpu_write_io(f,0x301f,superfx_cpu_read_io(f,0x301f));
    (void)c;
}
static bool finish_job(Run *r){
    for(unsigned step=0;step<400;step++){
        if(!superfx_is_running(r->fx))break;
        r->clock+=19998;superfx_sync(r->fx,r->clock);
    }
    bool stopped=!superfx_is_running(r->fx);
    r->clock+=198;superfx_sync(r->fx,r->clock);          /* let a queued RAM store and the ROM buffer settle */
    return stopped;
}

static void check_state(Ctx *x,Run *r,const SuperFxJob *job,bool timing){
    const RrGsuCase *c=x->c;SuperFx *f=r->fx;char label[48];
    expect(x,"stopped",!superfx_is_running(f),1);
    for(unsigned n=0;n<16;n++){snprintf(label,sizeof label,"R%u",n);expect(x,label,read_reg(f,n),c->r[n]);}
    expect_strict(x,"irq line (CFGR mask)",f->irq_pending,!(c->cfgr&0x80));
    uint16_t sfr=(uint16_t)(superfx_cpu_read_io(f,0x3030)|(superfx_cpu_read_io(f,0x3031)<<8));
    expect(x,"SFR",sfr&c->sfr_mask,c->sfr);
    expect(x,"SFR high read clears IRQ",(superfx_cpu_read_io(f,0x3031)>>7)&1,0);
    expect_strict(x,"irq line after SFR read",f->irq_pending,0);
    expect(x,"PBR",superfx_cpu_read_io(f,0x3034),c->exp_pbr);
    expect(x,"ROMBR",superfx_cpu_read_io(f,0x3036),c->rombr);
    expect(x,"RAMBR",superfx_cpu_read_io(f,0x303c),c->rambr);
    expect(x,"CBR",(uint16_t)(superfx_cpu_read_io(f,0x303e)|(superfx_cpu_read_io(f,0x303f)<<8)),c->cbr);
    for(unsigned i=0;i<c->nexp;i++)for(uint32_t k=0;k<c->exp[i].len;k++){
        snprintf(label,sizeof label,"RAM[%05x]",(unsigned)(c->exp[i].index+k));
        expect(x,label,superfx_cpu_read_ram(f,c->exp[i].index+k,0xEE),c->exp[i].data[k]);
    }
    if(!c->no_ram)expect(x,"RAM checksum",crc32_of(r->ram,RR_GSU_RAM_SIZE),c->ram_crc);
    for(unsigned i=0;i<c->ncache;i++)for(uint32_t k=0;k<c->cc[i].len;k++){
        snprintf(label,sizeof label,"cache[%03x]",(unsigned)(c->cc[i].index+k));
        expect(x,label,superfx_cpu_read_io(f,(uint16_t)(0x3100+c->cc[i].index+k)),c->cc[i].data[k]);
    }
    if(timing&&c->timed&&job){
        /* a cache hit costs one GSU clock, any other opcode byte one ROM read (3 clocks at
         * 10.7 MHz, 5 at 21.4 MHz), a cold cache line sixteen ROM reads; one master clock each */
        uint64_t unit=c->clsr?1:2,rom=c->clsr?5:6;
        uint64_t want=c->hits*unit+((uint64_t)c->direct+16u*c->fills)*rom+(uint64_t)c->extra*unit;
        expect(x,c->timed==1?"job duration, documented prices (master clocks)":"job duration, self-consistent (master clocks)",
               (uint32_t)(job->stop_master-job->start_master),(uint32_t)want);
        if(c->timed==1)timed_checks++;else self_timed_checks++;
    }
    if(timing&&c->base>=0&&job){
        /* documented cycle range for one opcode: this program minus the same program without it */
        uint32_t unit=c->clsr?1:2,dur=(uint32_t)(job->stop_master-job->start_master),d=dur-durations[c->base];
        char text[64];snprintf(text,sizeof text,"cycles %u.%u (documented %u-%u)",d/unit,(d%unit)*10/unit,c->cyc_lo,c->cyc_hi);
        /* the lower bounds are 21 MHz figures: at 10.7 MHz only the upper bound is asserted */
        expect(x,text,d%unit==0&&d/unit<=c->cyc_hi&&(c->clsr==0||d/unit>=c->cyc_lo),1);
        range_checks++;
    }
}

static void new_machine(const RrGsuCase *c,Run *r,SuperFx **fx,uint8_t *ram){
    memset(rom_image,0,sizeof rom_image);memset(ram,0,RR_GSU_RAM_SIZE);
    apply(rom_image,sizeof rom_image,c->rom,c->nrom);apply(ram,RR_GSU_RAM_SIZE,c->ram,c->nram);
    *fx=superfx_create(rom_image,RR_GSU_ROM_SIZE,ram,RR_GSU_RAM_SIZE);
    if(!*fx){fprintf(stderr,"superfx_create failed\n");exit(1);}
    r->fx=*fx;r->ram=ram;r->clock=1002;
}

static void run_case(const RrGsuCase *c,unsigned index){
    Run r;SuperFx *fx;Ctx x={c,0};SuperFxJob job={0};
    new_machine(c,&r,&fx,ram_image);configure(c,&r);
    bool all_stopped=true;
    for(unsigned j=0;j<c->njobs;j++){
        r.clock+=66;superfx_sync(fx,r.clock);start_job(c,&c->jobs[j],&r);
        all_stopped&=finish_job(&r);
    }
    SuperFxJob log[8];int n=superfx_job_log(log,8);if(n>0)job=log[n-1];
    if(!all_stopped)expect(&x,"program stopped",0,1);
    check_state(&x,&r,&job,true);
    durations[index]=(uint32_t)(job.stop_master-job.start_master);
    total_cases++;
    if(c->finding){finding_cases[c->finding]++;if(x.diffs)finding_diff_cases[c->finding]++;}
    superfx_destroy(fx);
}

/* Save mid-job, load into a second core with a copy of Game Pak RAM, then advance both in
 * lock step: they must agree on every step, stop together and end in the documented state. */
static void resume_case(const RrGsuCase *c,uint32_t after){
    Run a,b;SuperFx *fa,*fb;Ctx x={c,0};char label[40];
    new_machine(c,&a,&fa,ram_image);configure(c,&a);
    a.clock+=66;superfx_sync(fa,a.clock);start_job(c,&c->jobs[0],&a);
    a.clock+=after-after%6;superfx_sync(fa,a.clock);
    Stream s={{transfer,NULL},0,false,{0}};
    superfx_saveload(fa,&s.stream);
    memcpy(ram_second,ram_image,sizeof ram_second);
    fb=superfx_create(rom_image,RR_GSU_ROM_SIZE,ram_second,RR_GSU_RAM_SIZE);
    s.pos=0;s.load=true;superfx_saveload(fb,&s.stream);
    b.fx=fb;b.ram=ram_second;b.clock=a.clock;
    expect(&x,"resumed running flag",superfx_is_running(fb),superfx_is_running(fa));
    for(unsigned step=0;step<20000&&(superfx_is_running(fa)||superfx_is_running(fb));step++){
        a.clock+=48;b.clock=a.clock;superfx_sync(fa,a.clock);superfx_sync(fb,b.clock);
        if(superfx_is_running(fa)!=superfx_is_running(fb)||superfx_reg(fa,15)!=superfx_reg(fb,15)){
            snprintf(label,sizeof label,"lock step @%u",(unsigned)step);
            expect(&x,label,superfx_reg(fb,15)|(superfx_is_running(fb)<<16),superfx_reg(fa,15)|(superfx_is_running(fa)<<16));
            break;
        }
    }
    expect(&x,"lock step: original stopped",!superfx_is_running(fa),1);
    expect(&x,"lock step: resumed stopped",!superfx_is_running(fb),1);
    a.clock+=198;superfx_sync(fa,a.clock);b.clock=a.clock;superfx_sync(fb,b.clock);
    SuperFxJob log[8];int n=superfx_job_log(log,8);SuperFxJob job=n>0?log[n-1]:(SuperFxJob){0};
    check_state(&x,&a,&job,true);
    check_state(&x,&b,&job,false);
    resume_runs++;
    superfx_destroy(fa);superfx_destroy(fb);
}

/* The catch-up call must not depend on how the master clock is sliced: the 65816 side makes it
 * after almost every bus cycle (a few clocks apart), the checks above make it every 19,998
 * clocks. Run the same job on two cores, one synced in large steps and one in pseudo-random
 * steps of 1 to 97 clocks (many under six, so the credit is banked and the stopped core takes the
 * idle shortcut), reach the same final clock, then require byte-identical architectural state
 * (the 696-byte state stream), Game Pak RAM and job-log times. */
static unsigned long invariance_runs;
static uint32_t invariance_seed=0x2545f491u;
static unsigned invariance_random(unsigned limit){
    invariance_seed^=invariance_seed<<13;invariance_seed^=invariance_seed>>17;invariance_seed^=invariance_seed<<5;
    return invariance_seed%limit;
}
static void invariance_case(const RrGsuCase *c){
    Run a,b;SuperFx *fa,*fb;Ctx x={c,0};
    new_machine(c,&a,&fa,ram_image);configure(c,&a);
    new_machine(c,&b,&fb,ram_second);configure(c,&b);
    a.clock+=66;superfx_sync(fa,a.clock);b.clock+=66;superfx_sync(fb,b.clock);
    start_job(c,&c->jobs[0],&a);start_job(c,&c->jobs[0],&b);
    for(unsigned step=0;step<400;step++){a.clock+=19998;superfx_sync(fa,a.clock);if(!superfx_is_running(fa))break;}
    a.clock+=198;superfx_sync(fa,a.clock);
    a.clock+=7*6+3;superfx_sync(fa,a.clock);                       /* idle tail, not a multiple of six */
    while(b.clock<a.clock){
        uint64_t step=1+invariance_random(97);
        if(b.clock+step>a.clock)step=a.clock-b.clock;
        b.clock+=step;superfx_sync(fb,b.clock);
    }
    Stream sa={{transfer,NULL},0,false,{0}},sb={{transfer,NULL},0,false,{0}};
    superfx_saveload(fa,&sa.stream);superfx_saveload(fb,&sb.stream);
    expect_strict(&x,"sliced sync: state stream length",sb.pos,sa.pos);
    expect_strict(&x,"sliced sync: state stream",memcmp(sa.bytes,sb.bytes,sa.pos)==0,1);
    expect_strict(&x,"sliced sync: Game Pak RAM",memcmp(ram_image,ram_second,sizeof ram_image)==0,1);
    expect_strict(&x,"sliced sync: master clock",fb->master_clock,fa->master_clock);
    expect_strict(&x,"sliced sync: credit",(uint32_t)fb->clock_credit,(uint32_t)fa->clock_credit);
    expect_strict(&x,"sliced sync: instructions",(uint32_t)fb->instruction_count,(uint32_t)fa->instruction_count);
    invariance_runs++;
    superfx_destroy(fa);superfx_destroy(fb);
}

/* Hand-driven checks of the S-CPU side: register file, SFR flag bits, and aborting a running
 * job by writing GO=0 (fullsnes: the write can abort the program, sets CBR=0000h and empties
 * the cache). */
static void cpu_side_checks(void){
    static const RrGsuCase manual={.name="cpu-side"};
    Ctx x={&manual,0};Run r;SuperFx *fx;char label[48];
    memset(rom_image,0,sizeof rom_image);memset(ram_image,0,sizeof ram_image);
    /* CACHE; loop: BRA loop; NOP -- at 0123 so CBR becomes 0120 */
    rom_image[0x123]=0x02;rom_image[0x124]=0x05;rom_image[0x125]=0xFE;rom_image[0x126]=0x01;
    fx=superfx_create(rom_image,RR_GSU_ROM_SIZE,ram_image,RR_GSU_RAM_SIZE);
    r.fx=fx;r.ram=ram_image;r.clock=1002;superfx_sync(fx,r.clock);
    superfx_cpu_write_io(fx,0x303a,0x18);                        /* GSU owns ROM and RAM, as a game sets it before GO */
    for(unsigned n=0;n<15;n++)write_reg(fx,n,(uint16_t)(0x1111*(n+1)^0x0A5A));
    for(unsigned n=0;n<15;n++){snprintf(label,sizeof label,"register file R%u reads back",n);
        expect_strict(&x,label,read_reg(fx,n),(uint16_t)(0x1111*(n+1)^0x0A5A));}
    superfx_cpu_write_io(fx,0x301e,0x23);
    expect_strict(&x,"R15 low byte reads back",superfx_cpu_read_io(fx,0x301e),0x23);
    superfx_cpu_write_io(fx,0x3030,0x1e);
    expect_strict(&x,"SFR flag bits 1-4 are writable",superfx_cpu_read_io(fx,0x3030),0x1e);
    superfx_cpu_write_io(fx,0x3030,0x00);
    superfx_cpu_write_io(fx,0x301f,0x01);                        /* R15 = 0123, GO */
    expect_strict(&x,"GO set by the R15 high byte write",(superfx_cpu_read_io(fx,0x3030)>>5)&1,1);
    r.clock+=1200;superfx_sync(fx,r.clock);
    expect_strict(&x,"infinite loop still running",superfx_is_running(fx),1);
    expect_strict(&x,"CBR set by CACHE while running",(uint16_t)(superfx_cpu_read_io(fx,0x303e)|(superfx_cpu_read_io(fx,0x303f)<<8)),0x0120);
    superfx_cpu_write_io(fx,0x3030,0x00);                        /* GO=0 */
    expect_strict(&x,"GO=0 write aborts the job",superfx_is_running(fx),0);
    expect_strict(&x,"GO=0 write clears CBR",(uint16_t)(superfx_cpu_read_io(fx,0x303e)|(superfx_cpu_read_io(fx,0x303f)<<8)),0);
    uint16_t pc=read_reg(fx,15);r.clock+=1200;superfx_sync(fx,r.clock);
    expect_strict(&x,"aborted job does not advance",read_reg(fx,15),pc);
    total_cases++;superfx_destroy(fx);
}

/* Game Pak bus ownership (fullsnes, SCMR $303A: RON/RAN 0 = the S-CPU owns the ROM/RAM bus, 1 = the
 * GSU; "the GSU enters WAIT status (if it accesses ROM or RAM)" and goes on when the bit is set
 * again). Expected values follow from that rule alone:
 *  1. mailbox: the GSU polls RAM[0010h] with LDB. With RAN=0 it must not read, so a byte the S-CPU
 *     writes meanwhile is not seen and the job does not finish; with RAN=1 again it is read at once.
 *     This is the Dirt Racer display-list hand-off (the S-CPU fills the list with RAN=0).
 *  2. fetch: code outside the 512-byte cache window is read from ROM; with RON=0 it stops. */
static unsigned long counter_of(SuperFx *f){return (unsigned long)f->instruction_count;}
static void bus_ownership_checks(void){
    static const RrGsuCase manual={.name="bus-ownership"};
    Ctx x={&manual,0};Run r;SuperFx *fx;
    /* 0000: IWT R10,#0010; 0003: ALT1 LDB (R10); WITH R0; MOVES R0; BEQ 0003; NOP; STOP; NOP */
    static const uint8_t mailbox[]={0xfa,0x10,0x00,0x3d,0x4a,0x20,0xb0,0x09,0xfa,0x01,0x00,0x01};
    /* 0400: INC R1; BRA 0400; NOP */
    static const uint8_t fetch[]={0xd1,0x05,0xfd,0x01};
    memset(rom_image,0,sizeof rom_image);memset(ram_image,0,sizeof ram_image);
    memcpy(rom_image,mailbox,sizeof mailbox);memcpy(rom_image+0x400,fetch,sizeof fetch);
    fx=superfx_create(rom_image,RR_GSU_ROM_SIZE,ram_image,RR_GSU_RAM_SIZE);
    r.fx=fx;r.ram=ram_image;r.clock=1002;superfx_sync(fx,r.clock);
    superfx_cpu_write_io(fx,0x3037,0);superfx_cpu_write_io(fx,0x3039,0);superfx_cpu_write_io(fx,0x3038,0);
    superfx_cpu_write_io(fx,0x3034,0);
    superfx_cpu_write_io(fx,0x303a,0x18);                        /* GSU owns ROM and RAM */
    superfx_cpu_write_io(fx,0x301e,0x00);superfx_cpu_write_io(fx,0x301f,0x00);
    r.clock+=3000;superfx_sync(fx,r.clock);
    expect_strict(&x,"mailbox poll runs while the GSU owns RAM",superfx_is_running(fx),1);
    unsigned long polled=counter_of(fx);
    expect_strict(&x,"mailbox poll executes instructions",polled>100,1);
    superfx_cpu_write_io(fx,0x303a,0x10);                        /* RAN=0: the S-CPU owns Game Pak RAM */
    r.clock+=600;superfx_sync(fx,r.clock);                       /* the GSU reaches its next RAM access and waits */
    unsigned long parked=counter_of(fx);
    superfx_cpu_write_ram(fx,0x10,0x5a);                         /* the S-CPU writes the mailbox */
    r.clock+=6000;superfx_sync(fx,r.clock);
    expect_strict(&x,"GSU waits while the S-CPU owns RAM (no progress)",counter_of(fx),parked);
    expect_strict(&x,"GSU still running (WAIT, not stopped)",superfx_is_running(fx),1);
    expect_strict(&x,"mailbox byte is not read during the wait",read_reg(fx,0)==0x5a,0);
    superfx_cpu_write_io(fx,0x303a,0x18);                        /* RAN=1: hand RAM back */
    r.clock+=3000;superfx_sync(fx,r.clock);
    expect_strict(&x,"GSU goes on when RAN is set again and reads the mailbox",read_reg(fx,0),0x5a);
    expect_strict(&x,"job finishes after the hand-off",superfx_is_running(fx),0);

    write_reg(fx,1,0);
    superfx_cpu_write_io(fx,0x301e,0x00);superfx_cpu_write_io(fx,0x301f,0x04);   /* R15 = 0400, GO */
    r.clock+=3000;superfx_sync(fx,r.clock);
    unsigned fetched=read_reg(fx,1);
    expect_strict(&x,"uncached ROM code runs while the GSU owns ROM",fetched>50,1);
    superfx_cpu_write_io(fx,0x303a,0x08);                        /* RON=0: the S-CPU owns Game Pak ROM */
    r.clock+=600;superfx_sync(fx,r.clock);
    unsigned parked_r1=read_reg(fx,1);
    r.clock+=6000;superfx_sync(fx,r.clock);
    expect_strict(&x,"GSU waits for ROM while the S-CPU owns it",read_reg(fx,1),parked_r1);
    expect_strict(&x,"ROM wait is not a stop",superfx_is_running(fx),1);
    superfx_cpu_write_io(fx,0x303a,0x18);
    r.clock+=3000;superfx_sync(fx,r.clock);
    expect_strict(&x,"GSU goes on when RON is set again",read_reg(fx,1)>parked_r1+50u,1);
    total_cases++;superfx_destroy(fx);
}

int main(void){
    if(!rr16_init(true))return 2;
    cpu_side_checks();
    bus_ownership_checks();
    for(unsigned i=0;i<sizeof rr_gsu_cases/sizeof rr_gsu_cases[0];i++){
        const RrGsuCase *c=&rr_gsu_cases[i];
        run_case(c,i);
        for(unsigned k=0;k<c->nresume;k++)resume_case(c,c->resume[k]);
        invariance_case(c);
    }
    rr16_shutdown();
    printf("{\"cases\":%lu,\"resume_runs\":%lu,\"invariance_runs\":%lu,\"checks\":%lu,\"mismatches\":%lu,\"ares_checks\":%lu,\"timed_checks\":%lu,\"self_timed_checks\":%lu,\"range_checks\":%lu,\"findings\":{",
           total_cases,resume_runs,invariance_runs,total_checks,total_bad,ares_checks,timed_checks,self_timed_checks,range_checks);
    bool first=true;
    for(unsigned id=1;id<16;id++)if(finding_cases[id]){
        printf("%s\"%u\":{\"cases\":%lu,\"cases_differing\":%lu,\"differing_assertions\":%lu,\"assertions\":%lu}",
               first?"":",",id,finding_cases[id],finding_diff_cases[id],finding_diffs[id],finding_checks[id]);first=false;
    }
    printf("},\"passed\":%s}\n",total_bad?"false":"true");
    return 0;
}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){(void)a;(void)b;(void)c;(void)d;return main();}
