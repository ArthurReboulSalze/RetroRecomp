/* Offline bounded instruction snapshots. Original RetroRecomp, MIT. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68k_decoder.h"
#include "m68k_validator.h"
#include "rom_parser.h"
#include "md_exception_decode.h"
static unsigned base,length;
static unsigned char bytes[16];
static uint8_t fetch(uint32_t pc,void *ctx) {
    (void)ctx;return pc>=base && pc-base<length?bytes[pc-base]:0xff;
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    if(!strcmp(argv[1],"--lengths")){
        FILE*out=fopen(argv[2],"wb");if(!out)return 3;
        for(unsigned op=0;op<65536;op++){
            base=0x8000;length=sizeof(bytes);memset(bytes,0,sizeof(bytes));bytes[0]=(unsigned char)(op>>8);bytes[1]=(unsigned char)op;
            GenesisRom view={0};view.rom_size=base+length;view.read8_override=fetch;
            M68KInstr s={0};unsigned char words=8;
            if(m68k_decode(&view,base,&s)&&s.word_count>0&&s.word_count<=8)words=(unsigned char)s.word_count;
            if(fwrite(&words,1,1,out)!=1){fclose(out);return 3;}
        }
        return fclose(out)?3:0;
    }
    FILE *in=fopen(argv[1],"r"),*out=fopen(argv[2],"w");
    if(!in||!out)return 3;
    char line[128],hex[34];unsigned count=0,comma=0;
    fputs("[",out);
    while(fgets(line,sizeof line,in)) {
        if(++count>262144)return 4;
        char extra;
        if(sscanf(line,"%x %32s %c",&base,hex,&extra)!=2)return 4;
        length=(unsigned)strlen(hex)/2;
        if(base>0xffffffu || (base&1u) || length<2 || length>16 || strlen(hex)!=length*2 || base+length>0x1000000u)return 4;
        for(unsigned i=0;i<length;++i) {
            char part[3]={hex[i*2],hex[i*2+1],0},*end;
            unsigned v=(unsigned)strtoul(part,&end,16);if(*end)return 4;bytes[i]=(uint8_t)v;
        }
        GenesisRom view={0};view.rom_size=base+length;view.read8_override=fetch;
        M68KInstr s={0};M68KValidatorOptions options={0};
        if(!m68k_decode(&view,base,&s))continue;
        rr_md_normalize_exception(&s);
        if(s.byte_length>length || m68k_validate(&s,&options)!=M68K_LEGAL)continue;
        fprintf(out,"%s{\"addr\":%u,\"mnemonic\":%d,\"size\":%d,\"words\":[",comma?",":"",s.addr,s.mnemonic,s.size);
        for(int i=0;i<8;++i)fprintf(out,"%s%u",i?",":"",s.words[i]);
        fprintf(out,"],\"word_count\":%d,\"byte_length\":%u,\"src_ea\":%d,\"dst_ea\":%d,\"reg\":%d,\"imm32\":%u,\"target_addr\":%u,\"has_target\":%d,\"dst_is_ea\":%d,\"predec_mem_form\":%d,\"mem_shift\":%d}",
            s.word_count,s.byte_length,s.src_ea,s.dst_ea,s.reg,s.imm32,s.target_addr,s.has_target,s.dst_is_ea,s.predec_mem_form,s.mem_shift);
        comma=1;
    }
    fputs("]\n",out);fclose(in);return fclose(out)?3:0;
}
