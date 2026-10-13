/* Authored protected-RAM/lower-ROM tests, no commercial program or assets. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "hw_internal.h"
#include "retro_nes.h"
#include "game_cyc.c"

typedef struct { Cpu6502 processor; uint64_t cycles,bus,memory,hardware; } Result;
static unsigned cases,rejected,rom_cases,dmc_cases,changed_rom_cases;
static bool taito(void) { return hw_cart.mapper==80 || hw_cart.mapper==207 || hw_cart.mapper==82 || hw_cart.mapper==552; }
static uint16_t control(void) {
    unsigned m=hw_cart.mapper,s=hw_cart.info.submapper;
    return m==21 ? (s==2 ? 0x9080 : 0x9004) : m==23 ? (s==2 ? 0x9008 : 0x9002) : (s==2 ? 0x9004 : 0x9001);
}
static void unlock(void) {
    if(hw_cart.mapper==69) { cpu_write(0x8000,8,0);cpu_write(0xA000,0xC0,0); }
    if(hw_cart.mapper==21 || hw_cart.mapper==23 || hw_cart.mapper==25) cpu_write(control(),1,0);
    if(taito()) {
        if(hw_cart.mapper==80 || hw_cart.mapper==207) cpu_write(0x7EF8,0xA3,0);
        else { cpu_write(0x7EF7,0xCA,0);cpu_write(0x7EF8,0x69,0);cpu_write(0x7EF9,0x84,0); }
    }
}
static void setup(uint16_t pc,unsigned op,unsigned variant,unsigned interrupt,bool rom,unsigned page) {
    if(hw_cart.chr_ram_len) memset(hw_cart.chr+hw_cart.chr_ram_base,0x55,hw_cart.chr_ram_len);
    cyc_power_on(variant&3);cyc_trace_enabled=false;unlock();
    for(unsigned i=0;i<0x800;i++) hw.ram[i]=(uint8_t)(i*17+variant*31);
    memset(hw_cart.wram,0x55,sizeof(hw_cart.wram));
    if(rom && hw_cart.mapper==69) { cpu_write(0x8000,8,0);cpu_write(0xA000,(uint8_t)(page|((variant&1)?0x80:0)),0); }
    if(!rom) {
        uint8_t bytes[3]={(uint8_t)op,(uint8_t)((variant&1)?0xFF:0x01),0x01};
        for(unsigned i=0;i<3;i++) { uint8_t value;uint16_t addr=(uint16_t)(pc+i);
            if(rr_nes_ram_peek(addr,&value))cpu_write(addr,bytes[i],0); }
    }
    if(variant>=4) {
        cpu_write(0x4010,0x8F,0);cpu_write(0x4012,0xFF,0);cpu_write(0x4013,0,0);cpu_write(0x4015,0x10,0);
        ApuDmcView d;
        for(unsigned n=0;n<16;n++) { apu_debug_dmc(&d);if(d.dma)break;cpu_write(0,0,0); }
        apu_debug_dmc(&d);if(!d.dma || !d.playing || d.bytes!=1)abort();
    }
    if(variant>=8 || (variant<4 && (variant&2)))cpu_write(0x4014,2,0);
    memset(&cpu,0,sizeof(cpu));cpu.pc=pc;cpu.a=(uint8_t)(0x13+variant*43);cpu.x=(uint8_t)(variant*85);
    cpu.y=(uint8_t)(255-cpu.x);cpu.s=(uint8_t)(0xFF-variant);cpu_set_p((uint8_t)(variant*0x55));
    cpu.do_nmi=interrupt&1;cpu.do_irq=(interrupt>>1)&1;cpu.do_reset=(interrupt>>2)&1;
    cyc_trace_hash=0;cyc_trace_cycle=0;cyc_trace_enabled=true;
    cyc_run_interp_rom_cycles=cyc_run_interp_ram_cycles=cyc_run_interp_other_cycles=0;
}
static Result snapshot(void) {
    Result r={0};r.processor=cpu;r.cycles=cyc_cycle_count();r.bus=cyc_trace_hash;
    r.memory=cyc_mem_state_hash();r.hardware=cyc_hw_state_hash();return r;
}
static void compare(uint16_t pc,unsigned op,unsigned variant,unsigned irq,bool rom,unsigned bank) {
    setup(pc,op,variant,irq,rom,bank);Result initial=snapshot();
    if(!cyc_native_has(pc)) { fprintf(stderr,"Missing %d/%u RAM=%u PC=%04X\n",hw_cart.mapper,hw_cart.info.submapper,hw_cart.wram_len,pc);exit(2); }
    if(rom) {
        if(!dense_has(pc))abort();
        /* JMP on these fixture pages leaves code coverage immediately. Test
         * the complete dispatch loop without using upper hot blocks compiled
         * for the base mapper on another board. */
        if(op==0x4C && variant==0 && irq==0 && (bank==0 || bank==3) && pc==0x6230)
            cyc_native_run();
        else dense_step(pc);
        rom_cases++;
    }
    else live_step(pc);
    Result native=snapshot();
    if(cyc_run_interp_rom_cycles || cyc_run_interp_ram_cycles || cyc_run_interp_other_cycles)abort();
    if(variant>=4) { ApuDmcView d;apu_debug_dmc(&d);if(d.dma || d.bytes)abort();dmc_cases++; }
    setup(pc,op,variant,irq,rom,bank);Result initial_reference=snapshot();
    if(memcmp(&initial,&initial_reference,sizeof(initial))) { fprintf(stderr,"Initial states differ\n");exit(2); }
    cpu_interp_step();Result reference=snapshot();
    if(memcmp(&native,&reference,sizeof(native))) {
        fprintf(stderr,"Window divergence mapper=%d sub=%u pc=%04X op=%02X variant=%u irq=%u bank=%u bus=%llx/%llx\n",
            hw_cart.mapper,hw_cart.info.submapper,pc,op,variant,irq,bank,(unsigned long long)native.bus,(unsigned long long)reference.bus);exit(2);
    }
    cases++;
}
static void rejected_fetch(uint16_t pc) {
    uint64_t before=cyc_cycle_count(),trace_cycle=cyc_trace_cycle;Result initial=snapshot();
    if(cyc_native_has(pc)) { fprintf(stderr,"Protected/register window accepted %04X\n",pc);exit(2); }
    /* Snapshot and restore the whole machine to compare a fetched fallback
     * without resetting the protection register changed by this test. */
    size_t n=rr_nes_state_size();uint8_t *saved=malloc(n);if(!saved || !rr_nes_state_save(saved,n))abort();
    live_step(pc);Result native=snapshot();
    if(cyc_run_interp_rom_cycles+cyc_run_interp_ram_cycles+cyc_run_interp_other_cycles!=cyc_cycle_count()-before)abort();
    if(!rr_nes_state_load(saved,n))abort();free(saved);
    /* Trace accounting is intentionally not part of a quick state. */
    cyc_trace_hash=initial.bus;cyc_trace_cycle=trace_cycle;cpu_interp_step();Result reference=snapshot();
    if(memcmp(&native,&reference,sizeof(native))) { fprintf(stderr,"Rejected fetch differs %04X\n",pc);exit(2); }
    rejected++;
}
static void protections(void) {
    uint8_t value;unsigned bank;
    if(hw_cart.mapper==40)return;
    if(hw_cart.mapper==69) {
        for(unsigned mode=0;mode<2;mode++) { setup(0x6000,0xA9,0,0,false,0);
            cpu_write(0x8000,8,0);cpu_write(0xA000,(uint8_t)(0x40|(mode?0x80:0)),0);
            if(!mode) { if(rr_nes_ram_peek(0x6000,&value)||rr_nes_rom_bank4(0x6000,&bank))abort(); }
            else if(!rr_nes_ram_peek(0x6000,&value)||rr_nes_rom_bank4(0x6000,&bank))abort();
        }
    } else if(taito()) {
        const uint16_t ports[]={0x7EF0,0x7EF6,0x7EF7,0x7EF8,0x7EF9,0x7EFA,0x7EFF};
        for(unsigned i=0;i<7;i++) { setup(ports[i],0xA9,0,0,false,0);if(rr_nes_ram_peek(ports[i],&value))abort();rejected_fetch(ports[i]); }
        uint16_t pc=hw_cart.mapper==80 || hw_cart.mapper==207 ? 0x7F00 : 0x6000;
        setup(pc,0xA9,0,0,false,0);cpu_write(pc==0x7F00?0x7EF8:0x7EF7,0,0);
        if(rr_nes_ram_peek(pc,&value))abort();rejected_fetch(pc);
        if(pc==0x6000) {
            setup(0x6800,0xA9,0,0,false,0);cpu_write(0x7EF8,0,0);rejected_fetch(0x6800);
            setup(0x7000,0xA9,0,0,false,0);cpu_write(0x7EF9,0,0);rejected_fetch(0x7000);
            setup(0x7400,0xA9,0,0,false,0);rejected_fetch(0x7400);
        }
    } else {
        if(hw_cart.has_wram && hw_cart.mapper!=22 && hw_cart.info.submapper!=3) {
            setup(0x6000,0xA9,0,0,false,0);cpu_write(control(),0,0);rejected_fetch(0x6000);
        }
        if(!hw_cart.has_wram || (hw_cart.wram_len==2048 && hw_cart.mapper!=22 && hw_cart.info.submapper!=3)) {
            setup(0x7000,0xA9,0,0,false,0);rejected_fetch(0x7000);
            if(!hw_cart.has_wram) { setup(0x6000,0xA9,0,0,false,0);rejected_fetch(0x6000); }
        }
    }
}
static void changed_lower_rom(void) {
    /* An unexpected fetched byte must continue in the visible interpreter
     * without turning a $6000/$7000 alias into a bogus $E000/$F000 seed. */
    const uint16_t pcs[]={0x6100,0x7FFF};
    for(unsigned p=0;p<2;p++)for(unsigned variant=0;variant<=8;variant+=4) {
        uint16_t pc=pcs[p];unsigned bank;
        setup(pc,0,variant,0,true,3);
        if(!rr_nes_rom_bank4(pc,&bank))abort();
        unsigned physical=bank*4096+(pc&0xFFF);uint8_t original=hw_cart.prg[physical];
        hw_cart.prg[physical]=original^0x80;
        size_t slots=cyc_run_miss_slots();cyc_run_miss=calloc(slots,sizeof(*cyc_run_miss));if(!cyc_run_miss)abort();
        uint64_t before=cyc_cycle_count();live_step(pc);Result native=snapshot();
        if(cyc_run_interp_rom_cycles!=cyc_cycle_count()-before || !cyc_run_interp_rom_cycles)abort();
        for(size_t n=0;n<slots;n++)if(cyc_run_miss[n]) { fprintf(stderr,"Lower alias polluted ROM seed journal\n");exit(2); }
        free(cyc_run_miss);cyc_run_miss=NULL;
        setup(pc,0,variant,0,true,3);cpu_interp_step();Result reference=snapshot();
        if(memcmp(&native,&reference,sizeof(native))) { fprintf(stderr,"Changed lower ROM fallback differs\n");exit(2); }
        hw_cart.prg[physical]=original;changed_rom_cases++;
    }
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    fseek(f,0,SEEK_END);size_t n=ftell(f);rewind(f);uint8_t *rom=malloc(n);
    if(!rom||fread(rom,1,n,f)!=n)return 2;fclose(f);if(!cyc_load_ines(rom,n))return 2;free(rom);
    if(hw_cart.mapper==40 || hw_cart.mapper==69) {
        for(unsigned page=0;page<(hw_cart.mapper==69?8u:1u);page++)
            for(unsigned op=0;op<256;op++)for(unsigned v=0;v<4;v++)for(unsigned irq=0;irq<8;irq++)
                compare((uint16_t)(0x6100+op*4),op,v,irq,true,page);
        const uint16_t edges[]={0x6FFE,0x6FFF,0x7FFE,0x7FFF};
        for(unsigned i=0;i<4;i++)for(unsigned v=4;v<12;v++)for(unsigned irq=0;irq<8;irq++)compare(edges[i],0,v,irq,true,3);
    }
    if(hw_cart.mapper!=40 && hw_cart.has_wram) {
        const uint16_t pcs[]={0x6000,0x67FE,0x6800,0x6FFE,0x7000,0x73FE,0x73FF,0x7F00,0x7F7E,0x7F80,0x7FFE};
        for(unsigned p=0;p<11;p++) {
            setup(pcs[p],0xA9,0,0,false,0);uint8_t value;if(!rr_nes_ram_peek(pcs[p],&value))continue;
            for(unsigned op=0;op<256;op++)for(unsigned v=0;v<4;v++)for(unsigned irq=0;irq<8;irq++)compare(pcs[p],op,v,irq,false,0);
            for(unsigned op=0;op<256;op++)for(unsigned v=4;v<12;v++)compare(pcs[p],op,v,0,false,0);
        }
    }
    if(hw_cart.mapper!=40 && hw_cart.has_wram && cases==rom_cases) {
        fprintf(stderr,"Expected unlocked RAM was not exercised\n");return 2;
    }
    protections();
    if(hw_cart.mapper==40 || hw_cart.mapper==69)changed_lower_rom();
    printf("{\"passed\":true,\"mapper\":%d,\"submapper\":%u,\"instruction_cases\":%u,\"rom_alias_cases\":%u,\"dmc_cases\":%u,\"rejected_windows\":%u,\"changed_rom_cases\":%u}\n",
        hw_cart.mapper,hw_cart.info.submapper,cases,rom_cases,dmc_cases,rejected,changed_rom_cases);return 0;
}
