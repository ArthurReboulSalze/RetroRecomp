/* Real disk layer tests with authored memory bytes, never a game or BIOS. MIT. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "geo.h"
#include "neogeo_persistence.h"
static unsigned checks;
static void require(int okay,const char *name) {++checks;if(!okay) {fprintf(stderr,"NG saves: %s\n",name);exit(2);}}
static uint64_t hash(const uint8_t *p,size_t n) {uint64_t h=14695981039346656037ull;for(size_t i=0;i<n;++i)h=(h^p[i])*1099511628211ull;return h;}
static void put32(uint8_t *p,uint32_t v) {for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(8*n));}
int main(int argc,char **argv) {
    if(argc!=2)return 2;memset(ngsys.nvram,0,sizeof ngsys.nvram);memset(ngsys.memcard,0xa5,sizeof ngsys.memcard);
    wchar_t path[32768];require(rr_ng_persist_path(path,32768),"portable save path");
    if(!strcmp(argv[1],"invalid")) {
        require(!rr_ng_persist_begin(true),"bad file rejected");
        int intact=1;for(unsigned n=0;n<sizeof ngsys.nvram;++n)if(ngsys.nvram[n])intact=0;
        require(intact,"bad save cannot mutate NVRAM");
        intact=1;for(unsigned n=0;n<sizeof ngsys.memcard;++n)if(ngsys.memcard[n]!=0xa5)intact=0;
        require(intact,"bad save cannot mutate card");
        rr_ng_persist_activity(true);ngsys.nvram[512]=77;
        require(!rr_ng_persist_close(),"bad existing file not overwritten");
    } else {
        bool off=!strcmp(argv[1],"disabled");require(rr_ng_persist_begin(!off),"begin");
        if(!strcmp(argv[1],"idle") || off) {
            ngsys.nvram[3]=7;rr_ng_persist_activity(false);require(rr_ng_persist_close(),"idle initialization ignored");
            require(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES,"idle creates no save");
        } else if(!strcmp(argv[1],"save")) {
            ngsys.nvram[3]=7;rr_ng_persist_activity(false);rr_ng_persist_activity(true);
            ngsys.nvram[512]=125;ngsys.memcard[69]=55;require(rr_ng_persist_close(),"changed memories saved");
            require(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES,"save exists");
        } else {
            require(ngsys.nvram[3]==7 && ngsys.memcard[69]==55,"fresh process card and NVRAM restored");
            require(ngsys.nvram[512]==125 || ngsys.nvram[512]==99,"fresh process score restored");
            if(!strcmp(argv[1],"state")) {
                ngsys.nvram[512]=99;rr_ng_persist_after_state();require(rr_ng_persist_close(),"explicit state becomes ordinary save");
            } else if(!strcmp(argv[1],"conflict")) {
                rr_ng_persist_activity(true);ngsys.nvram[512]=42;
                FILE *file=_wfopen(path,L"rb");require(file!=NULL,"read concurrent fixture");
                uint8_t *bytes=malloc(67712);require(bytes && fread(bytes,1,67712,file)==67712,"read complete fixture");fclose(file);
                bytes[128+512]=88;uint64_t sum=hash(bytes+128,67584);put32(bytes+24,(uint32_t)sum);put32(bytes+28,(uint32_t)(sum>>32));
                file=_wfopen(path,L"wb");require(file && fwrite(bytes,1,67712,file)==67712,"other session writes valid save");fclose(file);free(bytes);
                require(!rr_ng_persist_close(),"concurrent update cannot be silently lost");
            } else {
                if(!strcmp(argv[1],"unchanged"))rr_ng_persist_activity(true);
                else {ngsys.nvram[10]=123;rr_ng_persist_activity(false);}
                require(rr_ng_persist_close(),"unchanged or idle session does not rewrite");
            }
        }
    }
    printf("{\"passed\":true,\"checks\":%u,\"synthetic_only\":true}\n",checks);return 0;
}
