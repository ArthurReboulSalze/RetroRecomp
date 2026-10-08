/* Authored hardware/quick-state regression fixtures; no commercial game data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "retro_nes.h"

bool cyc_native_has(uint16_t pc) { (void)pc; return false; }
void cyc_native_run(void) { abort(); }
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static void ticks(unsigned n) { while(n--) cpu_read(0,0); }
static void boot(void) { cyc_power_on(0); cyc_run_power_on(); }
static void drain(void) { int16_t b[4096]; while(cyc_audio_read(b,4096)) {} }
static uint64_t audio_hash(void) {
    int16_t b[4096]; size_t n; uint64_t h=0xcbf29ce484222325ULL;
    while((n=cyc_audio_read(b,4096))) for(size_t i=0;i<n;i++) h=(h^(uint16_t)b[i])*0x100000001b3ULL;
    return h;
}
static void frame_clock(void) {
    for(int rendering=0;rendering<2;rendering++) {
        boot(); cpu_write(0x2001,rendering ? 0x18 : 0,0);
        /* Let the pipeline settle; then measure six complete frames. */
        for(int f=0;f<2;f++) { hw_frame_done=false; while(!hw_frame_done) ticks(1); }
        uint64_t start=hw.cycles;
        for(int f=0;f<6;f++) { hw_frame_done=false; while(!hw_frame_done) ticks(1); }
        uint64_t expected=RR_NES_PAL ? 199485 : rendering ? 178683 : 178684;
        CHECK(hw.cycles-start==expected);
    }
    boot(); unsigned dot=ppu.dot; ticks(5);
    CHECK(ppu.dot-dot==(RR_NES_PAL ? 16 : 15));
    /* Register accesses clock a partial CPU cycle before its cycle count is
     * committed. The rational PAL divider must not slip at that boundary. */
    const uint16_t regs[]={0x2002,0x2004,0x2007};
    for(unsigned r=0;r<3;r++) for(unsigned align=0;align<4;align++) {
        cyc_power_on((uint8_t)align); unsigned start=ppu.dot;
        for(int n=0;n<25;n++) cpu_read(regs[r],0);
        ticks(5); /* Finish at the same tick within the CPU cycle. */
        CHECK(ppu.dot-start==(RR_NES_PAL ? 96 : 90));
    }
    for(unsigned align=0;align<4;align++) {
        cyc_power_on((uint8_t)align); unsigned start=ppu.dot;
        for(int n=0;n<25;n++) cpu_write(0x2000,0,0);
        ticks(5); CHECK(ppu.dot-start==(RR_NES_PAL ? 96 : 90));
        cyc_power_on((uint8_t)align); start=ppu.dot;
        cpu_write(0x4014,0,0); ticks(5);
        unsigned position=ppu.scanline*341+ppu.dot;
        CHECK(position-start==(unsigned)((hw.cycles*RR_CPU_DIV+align)/RR_PPU_DIV));
    }
    boot(); cyc_audio_enable(48000); ticks(100000);
    int16_t b[8192]; size_t n=cyc_audio_read(b,8192);
    double expected=100000.0*48000/RR_CPU_HZ;
    CHECK((double)n > expected-2 && (double)n < expected+2);
    boot(); unsigned irq=0; while(!apu_irq_output() && irq<40000) { ticks(1); irq++; }
    CHECK(irq >= (RR_NES_PAL ? 33250u : 29826u) && irq <= (RR_NES_PAL ? 33255u : 29831u));
    boot(); cpu_write(0x4010,15,0); apu_debug_set_dmc_timer(2); ticks(2);
    ApuDmcView d; apu_debug_dmc(&d); CHECK(d.timer==(RR_NES_PAL ? 50 : 54));
    if(RR_NES_PAL) {
        boot(); ppu.scanline=264; ppu.dot=1; ppu.oam_addr=0;
        cpu_write(0x2004,0x51,0); CHECK(ppu.oam[0]==0x51);
        ppu.scanline=265; ppu.dot=1; ppu.oam_addr=0;
        cpu_write(0x2004,0x62,0); CHECK(ppu.oam[0]==0x51);
    }
}
static void gun_checks(void) {
    boot(); CHECK((cpu_read(0x4017,0)&24)==8); CHECK((cpu_read(0x4016,0)&24)==0);
    rr_nes_zapper_aim(100,100,true,false);
    CHECK((cpu_read(0x4017,0)&24)==24);
    rr_nes_zapper_pixel(100,100,0x0F); CHECK((rr_nes_zapper_read(1)&8)!=0);
    rr_nes_zapper_pixel(150,100,0x30); CHECK((rr_nes_zapper_read(1)&8)!=0);
    rr_nes_zapper_pixel(100,100,0x30); CHECK((cpu_read(0x4017,0)&24)==16);
    ticks(3000); CHECK((rr_nes_zapper_read(1)&8)!=0);
    rr_nes_zapper_pixel(100,100,0x30); rr_nes_zapper_aim(-1,-1,true,true);
    CHECK((cpu_read(0x4017,0)&24)==24);
    /* Real PPU output, not a direct sensor call: old framebuffer pixels must
     * not be seen before the beam reaches the aim. Forced blank emits $3F00. */
    boot(); memset(hw_frame_index,0x30,256*240*sizeof(uint16_t));
    ppu.palette[0]=0x30; rr_nes_zapper_aim(100,100,false,false);
    CHECK((rr_nes_zapper_read(1)&8)!=0);
    for(unsigned n=0; n<40000 && (rr_nes_zapper_read(1)&8); n++) ticks(1);
    CHECK((rr_nes_zapper_read(1)&8)==0);
    ppu.palette[0]=0x0F; ticks(3500); CHECK((rr_nes_zapper_read(1)&8)!=0);
}
static void state_checks(void) {
    boot(); cyc_audio_enable(48000);
    cpu_write(0x4015,1,0); cpu_write(0x4000,0xBF,0);
    cpu_write(0x4002,0x40,0); cpu_write(0x4003,0x08,0);
    if(hw_cart.mapper==85) {
        cpu_write(0x9010,0x30,0); cpu_write(0x9030,0x10,0);
        cpu_write(0x9010,0x10,0); cpu_write(0x9030,0x80,0);
        cpu_write(0x9010,0x20,0); cpu_write(0x9030,0x15,0);
    }
    for(int i=0;i<3;i++) { cyc_run_frame(); drain(); }
    if(hw_cart.chr_ram_len) hw_cart.chr[hw_cart.chr_ram_base+15]=0x63;
    hw_cart.wram[7]=0xAB;
    rr_nes_zapper_aim(150,120,true,false); rr_nes_zapper_pixel(150,120,0x30);
    size_t size=rr_nes_state_size(); uint8_t *saved=malloc(size), *bad=malloc(size);
    CHECK(saved && bad); CHECK(rr_nes_state_save(saved,size));
    uint64_t before=cyc_hw_state_hash(), mem=cyc_mem_state_hash(); Cpu6502 c=cpu;
    uint8_t gun=rr_nes_zapper_read(1);
    cyc_run_frame(); uint64_t after=cyc_hw_state_hash(), mem_after=cyc_mem_state_hash(), pcm=audio_hash();
    Cpu6502 final_cpu=cpu;
    uint64_t interpreted=cyc_run_interp_rom_cycles;
    CHECK(rr_nes_state_load(saved,size));
    CHECK(cyc_run_interp_rom_cycles==interpreted);
    CHECK(cyc_hw_state_hash()==before && cyc_mem_state_hash()==mem && !memcmp(&c,&cpu,sizeof(c)));
    CHECK(rr_nes_zapper_read(1)==gun);
    cyc_run_frame(); CHECK(cyc_hw_state_hash()==after && cyc_mem_state_hash()==mem_after);
    CHECK(!memcmp(&final_cpu,&cpu,sizeof(cpu))); CHECK(audio_hash()==pcm);
    /* Both header mismatch and accidental corruption must reject atomically. */
    const size_t offsets[]={0,8,73,150,size-1,size/2};
    for(unsigned i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++) {
        memcpy(bad,saved,size); bad[offsets[i]]^=0xA5;
        CHECK(!rr_nes_state_load(bad,size));
        CHECK(cyc_hw_state_hash()==after && cyc_mem_state_hash()==mem_after);
    }
    CHECK(!rr_nes_state_load(saved,size-1));
    free(saved);free(bad);
}
int main(int argc,char **argv) {
    int mapper=argc>1 ? atoi(argv[1]) : 0;
    size_t prg=mapper==0 ? 32768 : 65536, size=16+prg;
    uint8_t *rom=calloc(1,size); memcpy(rom,"NES\032",4);
    rom[4]=(uint8_t)(prg/16384); rom[6]=(uint8_t)(mapper<<4); rom[7]=(uint8_t)(mapper&0xF0);
    for(size_t pos=16;pos<size;pos+=4096) {
        rom[pos]=0xE6;rom[pos+1]=0;rom[pos+2]=0x4C;rom[pos+3]=0;rom[pos+4]=0x80;
        rom[pos+4090]=rom[pos+4092]=rom[pos+4094]=0;
        rom[pos+4091]=rom[pos+4093]=rom[pos+4095]=0x80;
    }
    CHECK(cyc_load_ines(rom,size)); free(rom); cyc_run_native=false;
    frame_clock(); gun_checks(); state_checks();
    printf("{\"mapper\":%d,\"pal\":%d,\"checks\":%u,\"state_bytes\":%zu}\n",mapper,RR_NES_PAL,checks,rr_nes_state_size());
    return 0;
}
