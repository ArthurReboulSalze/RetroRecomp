/* Authored hardware/quick-state regression fixtures; no commercial game data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "cpu6502.h"
#include "hw_internal.h"
#include "retro_nes.h"
/* Multiplayer rollback (native/hostkit/hostkit_session.h), defined in nes_machine_state.inc. */
size_t rr_nes_snap_bound(void);
size_t rr_nes_snap_save(void *buffer, size_t capacity);
bool rr_nes_snap_load(const void *buffer, size_t size);
uint64_t rr_nes_digest(void);

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
/* The Four Score: $4016 gives players 1 and 3 and then the signature 00010000, $4017 players 2 and 4 and 00100000, most
 * significant bit first, 24 reads after a strobe. Without it (RR_NES_FOUR_SCORE 0) the extra pads are not wired: eight bits,
 * then ones, as before. */
static uint32_t port_bits(int port, unsigned count) {
    uint32_t value=0;
    for(unsigned i=0;i<count;i++) { value=value<<1|(cpu_read((uint16_t)(0x4016+port),0)&1u); ticks(8); }
    return value;
}
static void strobe(void) { cpu_write(0x4016,1,0); ticks(6); cpu_write(0x4016,0,0); ticks(6); }
static void four_score_checks(void) {
    boot();
    cyc_set_controller(0,0xA5); cyc_set_controller(1,0x3C); cyc_set_controller(2,0x81); cyc_set_controller(3,0xC3);
    strobe();
    if(RR_NES_FOUR_SCORE) {
        CHECK(port_bits(0,24)==0xA58110u); CHECK(port_bits(1,24)==0x3CC320u);
        CHECK(port_bits(0,8)==0xFF); CHECK(port_bits(1,8)==0xFF);
    } else {
        CHECK(port_bits(0,24)==0xA5FFFFu); CHECK(port_bits(1,24)==0x3CFFFFu);
    }
    /* A strobe starts the register again, and the pads read are the ones set before it. */
    cyc_set_controller(0,0x5A); cyc_set_controller(2,0x18); strobe();
    CHECK(port_bits(0,16)==(RR_NES_FOUR_SCORE ? 0x5A18u : 0x5AFFu));
    /* A read cut in the middle, then the machine saved: the rest of the register comes out the same after a load of the quick
     * state and of the in-process snapshot, the third and fourth pads and the signature included. */
    cyc_set_controller(0,0xC9); cyc_set_controller(1,0x6E); cyc_set_controller(2,0x27); cyc_set_controller(3,0xB1); strobe();
    CHECK(port_bits(0,11)==(RR_NES_FOUR_SCORE ? 0x649u : 0x64Fu));
    size_t size=rr_nes_state_size(), raw_size=rr_nes_snap_bound();
    uint8_t *file=malloc(size), *raw=malloc(raw_size); CHECK(file && raw);
    CHECK(rr_nes_state_save(file,size)); CHECK(rr_nes_snap_save(raw,raw_size)==raw_size);
    uint64_t digest=rr_nes_digest();
    CHECK(port_bits(0,13)==(RR_NES_FOUR_SCORE ? 0x710u : 0x1FFFu)); CHECK(port_bits(1,24)==(RR_NES_FOUR_SCORE ? 0x6EB120u : 0x6EFFFFu));
    CHECK(rr_nes_state_load(file,size)); CHECK(rr_nes_digest()==digest);
    CHECK(port_bits(0,13)==(RR_NES_FOUR_SCORE ? 0x710u : 0x1FFFu)); CHECK(port_bits(1,24)==(RR_NES_FOUR_SCORE ? 0x6EB120u : 0x6EFFFFu));
    CHECK(rr_nes_snap_load(raw,raw_size)); CHECK(rr_nes_digest()==digest);
    CHECK(port_bits(0,13)==(RR_NES_FOUR_SCORE ? 0x710u : 0x1FFFu)); CHECK(port_bits(1,24)==(RR_NES_FOUR_SCORE ? 0x6EB120u : 0x6EFFFFu));
    free(file); free(raw);
    if(RR_NES_FOUR_SCORE) {
        /* Another word for player 3 or 4 is another machine: the digest sees it. */
        boot(); cyc_set_controller(2,0x01); strobe(); uint64_t one=rr_nes_digest();
        boot(); cyc_set_controller(3,0x01); strobe(); uint64_t other=rr_nes_digest();
        CHECK(one!=other);
    }
}
static void frame_pads(int f) {
    cyc_set_controller(0,(uint8_t)(f*37)); cyc_set_controller(1,(uint8_t)(f*11));
    if(RR_NES_FOUR_SCORE) { cyc_set_controller(2,(uint8_t)(f*5+1)); cyc_set_controller(3,(uint8_t)(f*13+2)); }
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
    /* Every byte of a state is written by a field serialiser (no padding, no zero fill first):
     * a save over a buffer of other bytes is identical to the first, and so is a save made
     * after loading it back. */
    memset(bad,0xA5,size); CHECK(rr_nes_state_save(bad,size)); CHECK(!memcmp(saved,bad,size));
    memset(bad,0x5A,size); CHECK(rr_nes_state_save(bad,size)); CHECK(!memcmp(saved,bad,size));
    CHECK(!memcmp(saved,"RRNESST2",8));
    uint64_t before=cyc_hw_state_hash(), mem=cyc_mem_state_hash(); Cpu6502 c=cpu;
    uint8_t gun=rr_nes_zapper_read(1);
    cyc_run_frame(); uint64_t after=cyc_hw_state_hash(), mem_after=cyc_mem_state_hash(), pcm=audio_hash();
    Cpu6502 final_cpu=cpu;
    uint64_t interpreted=cyc_run_interp_rom_cycles;
    CHECK(rr_nes_state_load(saved,size));
    memset(bad,0xA5,size); CHECK(rr_nes_state_save(bad,size)); CHECK(!memcmp(saved,bad,size));
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
    /* Multiplayer rollback: the raw snapshot of this process, eight frames with changing pads, back to it, the same pads
     * again: the same machine and sound, the same digest at every frame; a digest taken every frame (as a session asks)
     * changes nothing against a run that takes none; a write made after the snapshot is undone by loading it. */
    size_t raw_size=rr_nes_snap_bound(); uint8_t *raw=malloc(raw_size); CHECK(raw);
    CHECK(rr_nes_snap_save(raw,raw_size)==raw_size); CHECK(rr_nes_snap_save(raw,raw_size-1)==0);
    uint64_t start_hw=cyc_hw_state_hash(), start_mem=cyc_mem_state_hash(), digests[8];
    for(int f=0;f<8;f++) {
        frame_pads(f);
        cyc_run_frame(); digests[f]=rr_nes_digest(); CHECK(digests[f]!=0);
    }
    uint64_t end_hw=cyc_hw_state_hash(), end_mem=cyc_mem_state_hash(), end_pcm=audio_hash();
    hw_cart.wram[7]^=0xFF;
    CHECK(rr_nes_snap_load(raw,raw_size)); CHECK(!rr_nes_snap_load(raw,raw_size-1));
    CHECK(cyc_hw_state_hash()==start_hw && cyc_mem_state_hash()==start_mem);
    for(int f=0;f<8;f++) {
        frame_pads(f);
        cyc_run_frame(); CHECK(rr_nes_digest()==digests[f]);
    }
    CHECK(cyc_hw_state_hash()==end_hw && cyc_mem_state_hash()==end_mem && audio_hash()==end_pcm);
    CHECK(rr_nes_snap_load(raw,raw_size));
    for(int f=0;f<8;f++) { frame_pads(f); cyc_run_frame(); }
    CHECK(cyc_hw_state_hash()==end_hw && cyc_mem_state_hash()==end_mem && rr_nes_digest()==digests[7]);
    free(raw);
}
static void pending_state_checks(void) {
    /* Save at a legal CPU boundary with transfers/interrupts still pending.
     * The next fetch must resume the same arbitration, not restart a DMA. */
    for (unsigned mode = 1; mode < 4; mode++) for (unsigned phase = 0; phase < 4; phase++)
        for (unsigned interrupt = 0; interrupt < 8; interrupt++) {
        cyc_power_on((uint8_t)phase); cyc_run_power_on(); cyc_audio_enable(48000);
        if (hw_cart.mapper == 69) {
            cpu_write(0x8000,8,0); cpu_write(0xA000,0xC1,0);
        }
        if (hw_cart.mapper == 153) cpu_write(0x800D,0x20,0);
        for (unsigned i=0;i<0x800;i++) hw.ram[i]=(uint8_t)(i*17+phase);
        if (hw_cart.has_wram) hw_cart.wram[13]=0x79;
        if (mode & 2) {
            cpu_write(0x4010,0x8F,0); cpu_write(0x4012,0xFF,0);
            cpu_write(0x4013,0,0); cpu_write(0x4015,0x10,0);
            ApuDmcView d;
            for (unsigned n=0;n<16;n++) { apu_debug_dmc(&d); if(d.dma) break; cpu_write(0,0,0); }
            apu_debug_dmc(&d); CHECK(d.dma && d.playing && d.bytes==1);
        }
        if (mode & 1) cpu_write(0x4014,2,0);
        cpu.do_nmi=interrupt&1; cpu.do_irq=(interrupt>>1)&1; cpu.do_reset=(interrupt>>2)&1;
        drain();
        size_t size=rr_nes_state_size(); uint8_t *saved=malloc(size); CHECK(saved);
        CHECK(rr_nes_state_save(saved,size));
        Cpu6502 before_cpu=cpu; uint64_t before_hw=cyc_hw_state_hash(), before_mem=cyc_mem_state_hash();
        cpu_interp_step(); ticks(64);
        Cpu6502 after_cpu=cpu; uint64_t after_hw=cyc_hw_state_hash(), after_mem=cyc_mem_state_hash(), pcm=audio_hash();
        CHECK(rr_nes_state_load(saved,size));
        CHECK(!memcmp(&before_cpu,&cpu,sizeof(cpu)) && before_hw==cyc_hw_state_hash() && before_mem==cyc_mem_state_hash());
        cpu_interp_step(); ticks(64);
        CHECK(!memcmp(&after_cpu,&cpu,sizeof(cpu)) && after_hw==cyc_hw_state_hash() && after_mem==cyc_mem_state_hash());
        CHECK(audio_hash()==pcm); free(saved);
    }
}
/* The host's save in a session (session ABI 8): one image of the cartridge's nonvolatile memory that another machine plays on,
 * a wrong image refused, and a guest's save file never written. A battery cartridge of its own (MMC1), loaded after the others. */
static void session_save_checks(void) {
    const size_t prg=65536, size=16+prg+8192;
    uint8_t *rom=calloc(1,size); CHECK(rom); memcpy(rom,"NES\032",4);
    rom[4]=(uint8_t)(prg/16384); rom[5]=1; rom[6]=(uint8_t)(1<<4|2);
    for(size_t pos=16;pos<16+prg;pos+=4096) {
        rom[pos]=0xE6;rom[pos+1]=0;rom[pos+2]=0x4C;rom[pos+3]=0;rom[pos+4]=0x80;
        rom[pos+4090]=rom[pos+4092]=rom[pos+4094]=0; rom[pos+4091]=rom[pos+4093]=rom[pos+4095]=0x80;
    }
    CHECK(cyc_load_ines(rom,size)); free(rom); cyc_run_native=false;
    boot(); const size_t nv=cyc_nvram_size(0); CHECK(nv>0 && cyc_nvram_size(1)==0);
    for(size_t i=0;i<nv;i++) hw_cart.wram[i]=(uint8_t)(i*7+3);
    const size_t image_size=rr_nes_session_save(NULL,0); CHECK(image_size==12+nv);
    uint8_t *image=malloc(image_size), *again=malloc(image_size); CHECK(image && again);
    CHECK(rr_nes_session_save(image,image_size)==image_size); CHECK(rr_nes_session_save(image,image_size-1)==0);
    memset(again,0xA5,image_size); CHECK(rr_nes_session_save(again,image_size)==image_size); CHECK(!memcmp(image,again,image_size));
    /* Another PC: a blank save, then the host's image: the same bytes, the same digest of the machine. */
    boot(); for(size_t i=0;i<nv;i++) hw_cart.wram[i]=0xFF;
    uint64_t blank=rr_nes_digest();
    CHECK(rr_nes_session_save_put(image,image_size));
    for(size_t i=0;i<nv;i++) CHECK(hw_cart.wram[i]==(uint8_t)(i*7+3));
    CHECK(rr_nes_digest()!=blank);
    CHECK(rr_nes_session_save(again,image_size)==image_size && !memcmp(image,again,image_size));
    /* The host loaded its save file before the power-on; a guest takes the image after it. Both must be the same machine. */
    cyc_power_on(0); CHECK(cyc_nvram_import(0,image+12,nv)); cyc_power_on(0); cyc_run_power_on();
    uint64_t host_boot=rr_nes_digest(), host_hw=cyc_hw_state_hash(), host_mem=cyc_mem_state_hash();
    boot(); for(size_t i=0;i<nv;i++) hw_cart.wram[i]=0xFF;
    CHECK(rr_nes_session_save_put(image,image_size));
    /* The machine is the same: the CPU, the hardware and the memories (the digest also names the sound mixer's leftovers of this
     * process's earlier boots, which two fresh processes do not have). */
    CHECK(cyc_hw_state_hash()==host_hw && cyc_mem_state_hash()==host_mem);
    (void)host_boot;
    /* A wrong image changes nothing. */
    memcpy(again,image,image_size); again[0]^=1; CHECK(!rr_nes_session_save_put(again,image_size));
    memcpy(again,image,image_size); again[4]^=1; CHECK(!rr_nes_session_save_put(again,image_size));
    CHECK(!rr_nes_session_save_put(image,image_size-1)); CHECK(!rr_nes_session_save_put(NULL,image_size));
    CHECK(rr_nes_session_save(again,image_size)==image_size && !memcmp(image,again,image_size));
    /* The guest's ban on writing its own save file. */
    CHECK(!rr_nes_saves_blocked()); rr_nes_saves_allowed(false); CHECK(rr_nes_saves_blocked()); rr_nes_saves_allowed(true); CHECK(!rr_nes_saves_blocked());
    free(image); free(again);
}
int main(int argc,char **argv) {
    int mapper=argc>1 ? atoi(argv[1]) : 0;
    size_t prg=mapper==0 ? 32768 : mapper==153 ? 524288 : 65536, size=16+prg;
    uint8_t *rom=calloc(1,size); memcpy(rom,"NES\032",4);
    rom[4]=(uint8_t)(prg/16384); rom[6]=(uint8_t)(mapper<<4); rom[7]=(uint8_t)(mapper&0xF0);
    if(mapper==153) { rom[7]|=8; rom[10]=0x70; rom[11]=7; }
    for(size_t pos=16;pos<size;pos+=4096) {
        rom[pos]=0xE6;rom[pos+1]=0;rom[pos+2]=0x4C;rom[pos+3]=0;rom[pos+4]=0x80;
        rom[pos+4090]=rom[pos+4092]=rom[pos+4094]=0;
        rom[pos+4091]=rom[pos+4093]=rom[pos+4095]=0x80;
    }
    CHECK(cyc_load_ines(rom,size)); free(rom); cyc_run_native=false;
    frame_clock(); if(RR_NES_ZAPPER) gun_checks(); four_score_checks(); state_checks(); pending_state_checks(); session_save_checks();
    printf("{\"mapper\":%d,\"pal\":%d,\"four_score\":%d,\"checks\":%u,\"state_bytes\":%zu}\n",mapper,RR_NES_PAL,RR_NES_FOUR_SCORE,checks,rr_nes_state_size());
    return 0;
}
