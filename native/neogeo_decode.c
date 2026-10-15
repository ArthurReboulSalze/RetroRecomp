/* Offline MC68000 frontend: bounded region bytes, no console ROM header. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68k_decoder.h"
#include "m68k_validator.h"
#include "rom_parser.h"
#include "md_cycle_estimate.h"
#include "md_exception_decode.h"
typedef struct { unsigned base,size;uint8_t *bytes; } Region;
static uint8_t fetch(uint32_t pc,void *ctx) {
    Region *r=ctx;return pc>=r->base && pc-r->base<r->size?r->bytes[pc-r->base]:0xff;
}
static Region region;
static unsigned *queue,tail;static uint8_t *seen;
static void enqueue(unsigned pc) {
    if((pc&1u) || pc<region.base || pc-region.base>=region.size)return;
    unsigned index=(pc-region.base)>>1;if(seen[index])return;
    seen[index]=1;queue[tail++]=pc;
}
int main(int argc,char **argv) {
    if(argc!=5 && argc!=6)return 2;
    region.base=(unsigned)strtoul(argv[2],NULL,16);
    FILE *input=fopen(argv[1],"rb");if(!input)return 3;
    fseek(input,0,SEEK_END);long size=ftell(input);rewind(input);
    if(size<2 || size>0x1000000 || size%2 || region.base>(0x1000000u-(unsigned)size))return 3;
    region.size=(unsigned)size;region.bytes=malloc(size);
    if(!region.bytes || fread(region.bytes,1,size,input)!=(size_t)size)return 3;fclose(input);
    queue=malloc((size/2)*sizeof *queue);seen=calloc(size/2,1);if(!queue||!seen)return 3;
    input=fopen(argv[3],"rb");FILE *output=fopen(argv[4],"wb");if(!input||!output)return 3;
    unsigned pc;while(fscanf(input,"%x",&pc)==1)enqueue(pc);fclose(input);
    /* Immutable apertures can be entered indirectly at any even address.
     * Decode each candidate offline; legality, length and live mapping/word
     * guards still apply. RAM never uses this sweep. */
    if(argc==6) {
        char *end=NULL;unsigned long scan=strtoul(argv[5],&end,16);
        if(!end || *end || scan>region.size || (scan&1u))return 2;
        for(unsigned offset=0;offset<scan;offset+=2)enqueue(region.base+offset);
    }
    GenesisRom view={0};view.rom_size=region.base+region.size;view.read8_override=fetch;view.read8_user=&region;
    M68KValidatorOptions opts={0};int comma=0;fputs("[",output);
    for(unsigned head=0;head<tail;++head) {
        pc=queue[head];M68KInstr ins={0};
        if(!m68k_decode(&view,pc,&ins))continue;rr_md_normalize_exception(&ins);
        if(ins.byte_length>region.size-(pc-region.base) || m68k_validate(&ins,&opts)!=M68K_LEGAL)continue;
        fprintf(output,"%s{\"addr\":%u,\"mnemonic\":%d,\"size\":%d,\"words\":[",comma?",":"",ins.addr,ins.mnemonic,ins.size);
        for(int i=0;i<8;++i)fprintf(output,"%s%u",i?",":"",ins.words[i]);
        fprintf(output,"],\"word_count\":%d,\"byte_length\":%u,\"src_ea\":%d,\"dst_ea\":%d,\"reg\":%d,\"imm32\":%u,\"target_addr\":%u,\"has_target\":%d,\"dst_is_ea\":%d,\"predec_mem_form\":%d,\"mem_shift\":%d,\"cycles\":%d}",
            ins.word_count,ins.byte_length,ins.src_ea,ins.dst_ea,ins.reg,ins.imm32,ins.target_addr,ins.has_target,ins.dst_is_ea,ins.predec_mem_form,ins.mem_shift,interp_estimate_cycles(&ins));comma=1;
        if(ins.has_target)enqueue(ins.target_addr);
        switch(ins.mnemonic) {
        case MN_JMP:case MN_BRA:case MN_RTS:case MN_RTE:case MN_RTR:case MN_ILLEGAL:break;
        default:enqueue(pc+ins.byte_length);break;
        }
    }
    fputs("]\n",output);fclose(output);free(queue);free(seen);free(region.bytes);return 0;
}
