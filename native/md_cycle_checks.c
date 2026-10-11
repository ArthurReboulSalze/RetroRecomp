/* Authored timing totals, independent of native/reference shared estimates. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md_native_steps.h"
typedef struct { const char *name; unsigned pc,clocks; uint8_t code[8]; unsigned size; } Case;
#include "cycle_fixture.h"
M68KState g_cpu;
uint8_t g_rom[0x400000],g_ram[0x10000];
static uint8_t flat[0x1000000];
uint64_t g_native_insn_count;
uint32_t g_cycle_accumulator,g_audio_cycle_counter,g_vblank_threshold=0xffffffffu;
uint32_t rr_md_cpu_stopped;
int g_rte_pending;
static int reference;
static unsigned reads,checks;
int genesis_force_interp(void) { return reference; }
void rr16_note_interpreted(void) {}
void rr16_note_rom_fallback(uint32_t pc) { (void)pc; }
uint32_t rr_md_rom_fetch_offset;
uint32_t rr_md_cart_code_offset(uint32_t pc,const uint16_t *words,unsigned count) { (void)words;(void)count;return pc; }
void rr16_note_ram_instruction(const M68KInstr *ins) { (void)ins; }
void glue_check_vblank(void) {}
int game_instruction_hook_site(uint32_t pc) { (void)pc;return 0; }
int genesis_game_instruction_hook(uint32_t pc) { (void)pc;return 0; }
void rr_md_cpu_fetch_cycles(unsigned words,int locked) { (void)words;(void)locked; }
unsigned rr_md_cpu_retire_cycles(unsigned cycles) { return cycles; }
unsigned rr_md_cpu_stop_cycles(void) { return 4; }
/* These suites isolate CPU semantics/totals. Dedicated prefetch tests enable bus phases. */
int rr_md_prefetch_active(void) { return 0; }
void rr_md_cpu_iack(unsigned level) { (void)level; }
void rr_md_cpu_idle(unsigned clocks) { (void)clocks; }
void rr_md_cpu_bus_lock(int locked) { (void)locked; }
uint16_t rr_md_read_instruction_word(uint32_t pc) { return m68k_read16(pc); }
uint8_t m68k_read8(uint32_t a) { if(a>=0xe00000)++reads;return flat[a&0xffffff]; }
uint16_t m68k_read16(uint32_t a) { return (m68k_read8(a)<<8)|m68k_read8(a+1); }
uint32_t m68k_read32(uint32_t a) { return ((uint32_t)m68k_read16(a)<<16)|m68k_read16(a+2); }
void m68k_write8(uint32_t a,uint8_t v) { flat[a&0xffffff]=v; }
void m68k_write16(uint32_t a,uint16_t v) { m68k_write8(a,v>>8);m68k_write8(a+1,v); }
void m68k_write32(uint32_t a,uint32_t v) { m68k_write16(a,v>>16);m68k_write16(a+2,v); }
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAIL %s %s: %s (clocks %u expected %u)\n",t->name,reference?"reference":"native",#x,g_audio_cycle_counter,t->clocks);return 1;}}while(0)
int main(void) {
    for(reference=0;reference<2;++reference)for(unsigned i=0;i<sizeof cases/sizeof *cases;++i) {
        const Case *t=&cases[i];memset(&g_cpu,0,sizeof g_cpu);memset(flat,0,sizeof flat);
        memcpy(flat+t->pc,t->code,t->size);memcpy(g_rom+t->pc,t->code,t->size);
        g_cpu.PC=t->pc;g_cpu.SR=0x2700;g_cpu.A[0]=0xe02000;g_cpu.A[1]=0xe02100;g_cpu.A[7]=0xe0ff00;
        g_cpu.D[0]=1;flat[0xe02000]=0x12;flat[0xe02001]=0x34;
        reads=0;g_audio_cycle_counter=g_cycle_accumulator=rr_md_cpu_stopped=0;
        CHECK(rr_md_native_lookup(t->pc)!=NULL);
        CHECK(m68k_interp_step()==M68KI_OK);
        CHECK(g_audio_cycle_counter==t->clocks && g_cycle_accumulator==t->clocks);
        CHECK(g_cpu.PC==t->pc+t->size);
        if(!strcmp(t->name,"CLR.L (A0)+"))CHECK(reads==4 && g_cpu.A[0]==0xe02004);
        if(!strcmp(t->name,"CLR.L -(A0)"))CHECK(reads==4 && g_cpu.A[0]==0xe01ffc);
        if(!strcmp(t->name,"SNE (A0)+"))CHECK(reads==1 && g_cpu.A[0]==0xe02001);
        if(!strncmp(t->name,"CMPM",4)) {
            unsigned size=strstr(t->name,".L")?4:strstr(t->name,".W")?2:1;
            CHECK(reads==size*2);
            if(strstr(t->name,"(A7)+,(A1)+"))CHECK(g_cpu.A[7]==0xe0ff02 && g_cpu.A[1]==0xe02101);
            else if(strstr(t->name,"(A0)+,(A7)+"))CHECK(g_cpu.A[0]==0xe02001 && g_cpu.A[7]==0xe0ff02);
            else CHECK(g_cpu.A[0]==0xe02000+size && g_cpu.A[1]==0xe02100+size);
        }
        if(strstr(t->name,"-(A0),-(A1)")) {
            unsigned size=strstr(t->name,".L")?4:strstr(t->name,".W")?2:1;
            CHECK(reads==size*2 && g_cpu.A[0]==0xe02000-size && g_cpu.A[1]==0xe02100-size);
        }
    }
    printf("{\"cases\":%u,\"checks\":%u,\"native_and_reference\":true,\"passed\":true}\n",
           (unsigned)(sizeof cases/sizeof *cases),checks);return 0;
}
