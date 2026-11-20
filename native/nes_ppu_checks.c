/* Authored bus activity only; compare hidden PPU state as well as video/audio. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "retro_nes.h"
extern size_t rr_nes_apu_size(void);
extern void rr_nes_apu_save(uint8_t *);
extern void rr_nes_apu_load(const uint8_t *);
bool cyc_native_has(uint16_t pc){(void)pc;return false;}
void cyc_native_run(void){abort();}
static uint32_t seed;
static uint32_t next_value(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static uint64_t hash_bytes(const void *data,size_t size){
    uint64_t h=14695981039346656037ULL;const unsigned char *p=data;
    while(size--)h=(h^*p++)*1099511628211ULL;return h;
}
#if RR_NES_FAST_PPU
void rr_nes_extra_sprites(bool enabled);
/* Twelve 8x8 objects on one line: the original units show the first eight;
 * the host option adds the others only on screen. Hidden PPU state, the
 * overflow flag and every bus fetch are the same with and without it. */
static int extra_sprites_check(void){
    uint64_t state[2];uint16_t line[2][256];
    for(int on=0;on<2;on++){
        cyc_power_on(0);cyc_run_power_on();rr_nes_extra_sprites(on!=0);
        if(!hw_cart.chr||hw_cart.chr_len<0x20)return 5;
        memset(hw_cart.chr,0,hw_cart.chr_len);memset(hw_cart.chr+0x10,0xff,8);
        memset(ppu.ciram,0,sizeof(ppu.ciram));memset(ppu.palette,0,sizeof(ppu.palette));
        ppu.palette[0]=0x0f;ppu.palette[0x11]=0x16;
        memset(ppu.oam,0xf8,sizeof(ppu.oam));
        for(unsigned n=0;n<12;n++){ppu.oam[n*4]=49;ppu.oam[n*4+1]=1;ppu.oam[n*4+2]=0;ppu.oam[n*4+3]=(uint8_t)(n*16);}
        for(unsigned k=0;k<2*29781;k++)(void)cpu_read(0,0); /* power-up register warm-up */
        cpu_write(0x2000,0,0);cpu_write(0x2001,0x1e,0);
        for(unsigned k=0;k<3*29781;k++)(void)cpu_read(0,0);
        state[on]=cyc_hw_state_hash()^hash_bytes(&ppu,sizeof(ppu));
        for(unsigned x=0;x<256;x++)line[on][x]=hw_frame_index[52*256+x];
    }
    rr_nes_extra_sprites(false);
    for(unsigned x=0;x<256;x++){
        bool object=(x&15)<8; /* eight-pixel objects every sixteen pixels */
        uint16_t original=object&&x<128?0x16:0x0f,extra=object&&x<192?0x16:0x0f;
        if(line[0][x]!=original||line[1][x]!=extra){
            fprintf(stderr,"x=%u off=%02x on=%02x\n",x,line[0][x],line[1][x]);return 6;
        }
    }
    if(state[0]!=state[1])return 7;
    puts("PASS: objects 9-12 shown only with the option; hidden PPU state, overflow and fetches unchanged.");
    return 0;
}
#endif
/* The APU alone, over long runs (the deferred cycles of nes_apu_batch.inc): channel and frame counter settings written at
 * random, runs of 1 to 40,000 cycles, the interrupt lines and the cycle count hashed on every cycle (a DMA stall or an IRQ
 * one cycle late shows at once), and the whole APU state, the sound and the machine hashed at the end of each run. */
static int apu_checks(unsigned mapper){
    static const uint16_t regs[]={
        0x4000,0x4001,0x4002,0x4003,0x4004,0x4005,0x4006,0x4007,0x4008,0x400a,0x400b,0x400c,0x400e,0x400f,
        0x4010,0x4011,0x4012,0x4013,0x4015,0x4017,0x4015,0x4017,0x4003,0x4007,0x400b,0x400f};
    uint8_t *state=malloc(rr_nes_apu_size());if(!state)return 4;
    for(unsigned scenario=0;scenario<28;scenario++){
        cyc_power_on((uint8_t)(scenario&3));cyc_run_power_on();
        if(scenario%3!=2)cyc_audio_enable(scenario&1?44100:48000);
        seed=0x9e3779b9u+scenario*7919u;cpu.i=0;
        for(unsigned segment=0;segment<14;segment++){
            unsigned changes=next_value()%7;
            if(segment==0)changes+=6;
            for(unsigned c=0;c<changes;c++){
                uint16_t reg=regs[next_value()%(sizeof(regs)/sizeof(regs[0]))];
                uint8_t value=(uint8_t)(next_value()>>8);
                if(reg==0x4015&&(next_value()&3))value|=0x0f;       /* mostly enabled */
                if(reg==0x4017&&(next_value()&1))value&=0xc0;
                if(reg==0x4010&&(next_value()&1))value&=0xcf;       /* no loop, a slow rate */
                cpu_write(reg,value,0);
            }
            unsigned kind=segment%4;
            unsigned length=1+next_value()%(kind==0?40000u:kind==1?3000u:kind==2?400u:40u);
            uint64_t trace=14695981039346656037ULL;
            cpu.do_irq=0;
            for(unsigned cycle=0;cycle<length;cycle++){
                uint32_t r=next_value();
                if((r&1023)==0){
                    switch((r>>10)%6){
                    case 0:(void)cpu_read(0x4015,0);break;
                    case 1:(void)cpu_read(0x4016,0);break;
                    case 2:(void)cpu_read(0x4017,0);break;
                    case 3:(void)cyc_hw_state_hash();break;
                    case 4:cpu_write(0x4014,(uint8_t)(r>>16),0);break;
                    default:cpu_write(0x4016,(uint8_t)((r>>16)&1),0);break;
                    }
                }else (void)cpu_read(0,(r&15)==0?CYC_POLL:0);
                if((r&0xfff)==7)cpu.do_irq=0;
                trace=(trace^(hw.irq_line|cpu.do_irq<<1|cpu.do_nmi<<2|(unsigned)(cyc_cycle_count()<<3)))*1099511628211ULL;
            }
            int16_t pcm[4096];size_t n;uint64_t sound=14695981039346656037ULL;
            while((n=cyc_audio_read(pcm,4096)))sound^=hash_bytes(pcm,n*sizeof(*pcm));
            rr_nes_apu_save(state);
            printf("A %u %u %u %llu %016llx %016llx %016llx %016llx %016llx\n",mapper,scenario,segment,
                (unsigned long long)cyc_cycle_count(),(unsigned long long)trace,(unsigned long long)hash_bytes(&cpu,sizeof(cpu)),
                (unsigned long long)sound,(unsigned long long)hash_bytes(state,rr_nes_apu_size()),
                (unsigned long long)cyc_hw_state_hash());
        }
    }
    free(state);return 0;
}
int main(int argc,char **argv){
    unsigned mapper=argc>1?(unsigned)atoi(argv[1]):0;
    size_t prg=mapper==0?32768:mapper==153?524288:65536,size=16+prg;
    uint8_t *rom=calloc(1,size);if(!rom)return 2;memcpy(rom,"NES\032",4);
    rom[4]=(uint8_t)(prg/16384);rom[6]=(uint8_t)(mapper<<4);rom[7]=(uint8_t)(mapper&0xf0);
    if(mapper==153){rom[7]|=8;rom[10]=0x70;rom[11]=7;}
    memset(rom+16,0xea,prg);
    for(size_t pos=16;pos<size;pos+=4096){
        rom[pos+4090]=rom[pos+4092]=rom[pos+4094]=0;
        rom[pos+4091]=rom[pos+4093]=rom[pos+4095]=0x80;
    }
    if(!cyc_load_ines(rom,size))return 3;free(rom);cyc_run_native=false;
    if(argc>2&&!strcmp(argv[2],"apu"))return apu_checks(mapper);
#if RR_NES_FAST_PPU
    if(argc>2&&!strcmp(argv[2],"extra"))return extra_sprites_check();
    if(argc>2&&!strcmp(argv[2],"engaged")){ /* whether this board runs the deferred clock, and does defer edges */
        extern bool rr_ppu_lazy;extern unsigned rr_ppu_room;
        cyc_power_on(0);cyc_run_power_on();
        bool lazy=rr_ppu_lazy&&rr_ppu_room>1;
        for(unsigned k=0;k<2000;k++)(void)cpu_read(0,0);
        puts(lazy&&rr_ppu_lazy?"deferred":"eager");return 0;
    }
#endif
    uint8_t *audio_state=malloc(rr_nes_apu_size());if(!audio_state)return 4;
    static const uint16_t audio_regs[]={
        0x4000,0x4001,0x4002,0x4003,0x4004,0x4005,0x4006,0x4007,
        0x4008,0x400a,0x400b,0x400c,0x400e,0x400f,0x4010,0x4011,0x4012,0x4013,0x4015,0x4017};
    for(unsigned align=0;align<4;align++){
        cyc_power_on((uint8_t)align);cyc_run_power_on();cyc_audio_enable(48000);seed=1+align;
        for(unsigned i=0;i<256;i++)ppu.oam[i]=(uint8_t)(i*19);
        /* Pattern data that differs from byte to byte, so that tiles and sprites (flipped ones too) fetch something. */
        if(hw_cart.chr&&hw_cart.chr_len)for(size_t i=0;i<hw_cart.chr_len;i++)hw_cart.chr[i]=(uint8_t)(next_value()>>11);
        for(unsigned i=0;i<sizeof(ppu.ciram);i++)ppu.ciram[i]=(uint8_t)(i*23);
        for(unsigned i=0;i<32;i++)ppu.palette[i]=(uint8_t)(i*3);
        for(unsigned iteration=0;iteration<700;iteration++){
            uint32_t value=next_value();
            cpu_write(0x2000,(uint8_t)(value>>8),0);
            cpu_write(0x2001,(iteration%23)==0?0:(uint8_t)(value|0x18),0);
            if(iteration%2==0)cpu_write((uint16_t)(0x2000+(value&7)),(uint8_t)(value>>16),0);
            if(iteration%3==0)(void)cpu_read((uint16_t)(0x2000+((value>>4)&7)),0);
            if(iteration%17==0)cpu_write(0x4014,(uint8_t)(value&7),0);
            if(iteration%11==0)cpu_write((uint16_t)(0x8000+(value&0x7001)),(uint8_t)(value>>24),0);
            cpu_write(audio_regs[iteration%20],(uint8_t)(value>>16),0);
            if(iteration%19==0)cpu_write(0x4015,31,0);
            if(iteration%29==0)apu_debug_set_noise((uint16_t)(value&0x7fff),(uint16_t)(value&0xff));
            if(iteration%37==0){
                rr_nes_apu_save(audio_state);
                cpu_write(0x4011,(uint8_t)value,0);
                for(unsigned k=0;k<23;k++)(void)cpu_read(0,0);
                rr_nes_apu_load(audio_state);
            }
            if(iteration%103==0){apu_audio_enable(false,0);cyc_audio_enable((iteration&1)?44100:48000);}
            for(unsigned clock=0;clock<128+(value&63);clock++){
                (void)cpu_read(0,0);
                if((clock&31)==17)(void)cpu_read(0x2002,0);
            }
            int16_t pcm[4096];size_t n;uint64_t sound=14695981039346656037ULL;
            while((n=cyc_audio_read(pcm,4096)))sound^=hash_bytes(pcm,n*sizeof(*pcm));
            rr_nes_apu_save(audio_state);
            /* Observing the machine first runs any deferred PPU edges. */
            uint64_t hw_hash=cyc_hw_state_hash();
            {   /* Diagnostic: RR_PPU_DUMP=align:iteration writes the whole PPU of that checkpoint to stderr, to compare two builds. */
                const char *dump=getenv("RR_PPU_DUMP");unsigned da,di;
                if(dump&&sscanf(dump,"%u:%u",&da,&di)==2&&da==align&&di==iteration){
                    const unsigned char *p=(const unsigned char *)&ppu;
                    for(size_t k=0;k<sizeof(ppu);k++)fprintf(stderr,"%02x%s",p[k],(k&31)==31?"\n":"");
                    fprintf(stderr,"\n");
                }
            }
            /* The CPU's interrupt inputs and edges show when /NMI and /IRQ were sampled. */
            printf("%u %u %u %llu %016llx %016llx %016llx %016llx %016llx %016llx %016llx\n",RR_NES_PAL,align,iteration,
                (unsigned long long)cyc_cycle_count(),(unsigned long long)hash_bytes(&cpu,sizeof(cpu)),
                (unsigned long long)hash_bytes(&ppu,sizeof(ppu)),
                (unsigned long long)hash_bytes(hw_frame_index,sizeof(hw_frame_index)),
                (unsigned long long)hw_hash,(unsigned long long)cyc_mem_state_hash(),(unsigned long long)sound,
                (unsigned long long)hash_bytes(audio_state,rr_nes_apu_size()));
        }
    }
    /* /NMI is sampled at one tick of each CPU cycle and the PPU sets vblank at one dot. Where that dot falls in the
     * cycle depends on the clock alignment and on the frame (the frame is not a whole number of CPU cycles), so
     * this follows four vblanks from each alignment and prints the CPU and PPU state of the cycles around each, to
     * hold a deferred clock to the tick by tick one where /NMI is sampled just before or just after the dot. */
    {
        const unsigned frame=(RR_PRERENDER+1u)*341u;
        for(unsigned align=0;align<4;align++){
            cyc_power_on((uint8_t)align);cyc_run_power_on();
            cpu_write(0x2001,0,0);cpu_write(0x2000,0x80,0);
            for(unsigned vblank=0;vblank<4;vblank++){
                rr_ppu_sync();
                unsigned position=ppu.scanline*341u+ppu.dot;
                unsigned dots=(241u*341u+1u+frame-position)%frame;
                unsigned cycles=(unsigned)((unsigned long long)dots*RR_PPU_DIV/RR_CPU_DIV);
                for(unsigned k=0;k+8<cycles;k++)(void)cpu_read(0,0);
                for(unsigned k=0;k<24;k++){
                    (void)cpu_read(0,0);rr_ppu_sync();
                    printf("N %u %u %u %016llx %016llx\n",align,vblank,k,(unsigned long long)hash_bytes(&cpu,sizeof(cpu)),
                        (unsigned long long)hash_bytes(&ppu,sizeof(ppu)));
                }
                cpu_read(0x2002,0); /* clear the flag: the next vblank is a new edge */
            }
        }
    }
    free(audio_state);return 0;
}
