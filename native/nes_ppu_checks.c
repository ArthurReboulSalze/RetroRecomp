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
#if RR_NES_FAST_PPU
    if(argc>2&&!strcmp(argv[2],"extra"))return extra_sprites_check();
#endif
    uint8_t *audio_state=malloc(rr_nes_apu_size());if(!audio_state)return 4;
    static const uint16_t audio_regs[]={
        0x4000,0x4001,0x4002,0x4003,0x4004,0x4005,0x4006,0x4007,
        0x4008,0x400a,0x400b,0x400c,0x400e,0x400f,0x4010,0x4011,0x4012,0x4013,0x4015,0x4017};
    for(unsigned align=0;align<4;align++){
        cyc_power_on((uint8_t)align);cyc_run_power_on();cyc_audio_enable(48000);seed=1+align;
        for(unsigned i=0;i<256;i++)ppu.oam[i]=(uint8_t)(i*19);
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
            printf("%u %u %u %llu %016llx %016llx %016llx %016llx %016llx %016llx\n",RR_NES_PAL,align,iteration,
                (unsigned long long)cyc_cycle_count(),(unsigned long long)hash_bytes(&ppu,sizeof(ppu)),
                (unsigned long long)hash_bytes(hw_frame_index,sizeof(hw_frame_index)),
                (unsigned long long)hw_hash,(unsigned long long)cyc_mem_state_hash(),(unsigned long long)sound,
                (unsigned long long)hash_bytes(audio_state,rr_nes_apu_size()));
        }
    }
    free(audio_state);return 0;
}
