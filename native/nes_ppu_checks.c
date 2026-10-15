/* Authored bus activity only; compare hidden PPU state as well as video/audio. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "retro_nes.h"
bool cyc_native_has(uint16_t pc){(void)pc;return false;}
void cyc_native_run(void){abort();}
static uint32_t seed;
static uint32_t next_value(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static uint64_t hash_bytes(const void *data,size_t size){
    uint64_t h=14695981039346656037ULL;const unsigned char *p=data;
    while(size--)h=(h^*p++)*1099511628211ULL;return h;
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
            for(unsigned clock=0;clock<128+(value&63);clock++){
                (void)cpu_read(0,0);
                if((clock&31)==17)(void)cpu_read(0x2002,0);
            }
            int16_t pcm[4096];size_t n;uint64_t sound=14695981039346656037ULL;
            while((n=cyc_audio_read(pcm,4096)))sound^=hash_bytes(pcm,n*sizeof(*pcm));
            printf("%u %u %u %llu %016llx %016llx %016llx %016llx %016llx\n",RR_NES_PAL,align,iteration,
                (unsigned long long)cyc_cycle_count(),(unsigned long long)hash_bytes(&ppu,sizeof(ppu)),
                (unsigned long long)hash_bytes(hw_frame_index,sizeof(hw_frame_index)),
                (unsigned long long)cyc_hw_state_hash(),(unsigned long long)cyc_mem_state_hash(),(unsigned long long)sound);
        }
    }
    return 0;
}
