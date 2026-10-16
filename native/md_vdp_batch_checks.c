/* ROM-free differential corpus for scalar/tile-span production renderers. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "video/genesis_vdp.h"
extern int gvdp_render_scanline_latched(GVDP *,int,uint8_t *,uint16_t,uint16_t);
unsigned machine_vdp_phase(void) { return 0; }
static uint32_t random_state=0x4d445650;
static uint32_t next(void) {
    random_state^=random_state<<13;random_state^=random_state>>17;
    random_state^=random_state<<5;return random_state;
}
static uint64_t hash=UINT64_C(14695981039346656037),pixels;
static unsigned checks,rows;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static void digest(const void *data,size_t count) {
    const uint8_t *p=data;while(count--){hash^=*p++;hash*=UINT64_C(1099511628211);}
}
static void word(GVDP *v,unsigned address,unsigned value) {
    v->vram[(uint16_t)address]=(uint8_t)(value>>8);
    v->vram[(uint16_t)(address+1)]=(uint8_t)value;
}
static int benchmark(void) {
    GVDP v;gvdp_init(&v);
    for(unsigned i=0;i<sizeof v.vram;++i)v.vram[i]=(uint8_t)next();
    for(unsigned i=0;i<GVDP_VSRAM_ENTRIES;++i)v.vsram[i]=(uint16_t)next();
    v.reg[1]=0x40;v.reg[12]=0x81;v.reg[2]=0x38;v.reg[3]=0x30;
    v.reg[4]=6;v.reg[5]=0x50;v.reg[13]=0x2c;v.reg[16]=0x11;
    for(unsigned i=0;i<80;++i) {
        word(&v,0xa000+i*8,128+next()%224);
        word(&v,0xa002+i*8,((next()&15)<<8)|((i+1)%80));
        word(&v,0xa004+i*8,next());word(&v,0xa006+i*8,128+next()%320);
    }
    gvdp_set_ws_extra(0);gvdp_set_ws_canvas(0);gvdp_set_bgdiag(0);
    uint8_t out[GVDP_MAX_WIDTH];uint64_t sample=0;
    clock_t begin=clock();
    const unsigned count=65536;
    for(unsigned i=0;i<count;++i) {
        v.reg[12]=(i&2048)?0x89:0x81;v.reg[11]=(i>>12)&7;
        v.reg[17]=(i&4096)?0x8a:0;v.reg[18]=0;
        int n=gvdp_render_scanline_latched(&v,i%224,out,0,0);
        sample=sample*UINT64_C(1099511628211)+out[(i*13u)%(unsigned)n];
    }
    double seconds=(double)(clock()-begin)/CLOCKS_PER_SEC;
    digest(out,320);sample^=hash;sample^=(unsigned)v.sprite_collision<<16;
    sample^=(unsigned)v.sprite_overflow<<24;
    printf("{\"passed\":true,\"authored_rows\":%u,\"cpu_seconds\":%.6f,\"sample\":\"%016llx\"}\n",
        count,seconds,(unsigned long long)sample);return 0;
}
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--benchmark"))return benchmark();
    clock_t begin=clock();
    for(unsigned mode=0;mode<512;++mode) {
        GVDP v;gvdp_init(&v);
        for(unsigned i=0;i<sizeof v.vram;++i)v.vram[i]=(uint8_t)next();
        for(unsigned i=0;i<GVDP_VSRAM_ENTRIES;++i)v.vsram[i]=(uint16_t)next();
        for(unsigned i=0;i<sizeof v.reg;++i)v.reg[i]=(uint8_t)next();
        unsigned h40=mode&1,im2=(mode>>1)&1;
        v.reg[1]=(mode%29?0x40:0)|((mode&4)?8:0);
        v.reg[12]=(h40?0x81:0)|(im2?6:0)|((mode&8)?8:0);
        v.reg[11]=(uint8_t)((mode>>4)&7);
        v.reg[16]=(uint8_t)((mode&3)|(((mode>>2)&3)<<4));
        v.reg[2]=0x38;v.reg[3]=0x30;v.reg[4]=6;v.reg[5]=0x50;
        v.reg[13]=0x2c;
        v.reg[17]=(uint8_t)((next()&31)|((mode&32)?0x80:0));
        v.reg[18]=(uint8_t)((next()&31)|((mode&64)?0x80:0));
        unsigned sprite_base=0xa000,origin=im2?256:128;
        for(unsigned i=0;i<(h40?80u:64u);++i) {
            word(&v,sprite_base+i*8,origin+(next()%(im2?480:240)));
            word(&v,sprite_base+i*8+2,((next()&15)<<8)|((i+1)%(h40?80:64)));
            word(&v,sprite_base+i*8+4,next());
            word(&v,sprite_base+i*8+6,i%17==0?0:80+(next()%400));
        }
        gvdp_set_unlimited_sprites((mode>>7)&1);
        gvdp_set_ws_extra(mode%3==0?64:0);
        gvdp_set_ws_canvas(mode%5==0?512:0);
        gvdp_set_ws_bar_black(mode&1);gvdp_set_bgdiag(mode%11==0);
        for(unsigned sample=0;sample<64;++sample) {
            struct {uint8_t guard0[16],out[GVDP_MAX_WIDTH],guard1[16];} result;
            memset(&result,0xa5,sizeof result);
            unsigned line=next()%(im2?480:240);
            GVDP before=v;
            uint16_t vs_a=(uint16_t)next(),vs_b=(uint16_t)next();
            int n=gvdp_render_scanline_latched(&v,line,result.out,vs_a,vs_b);
            CHECK(n>0 && n<=GVDP_MAX_WIDTH);
            for(unsigned k=0;k<16;++k)CHECK(result.guard0[k]==0xa5 && result.guard1[k]==0xa5);
            for(int k=n;k<GVDP_MAX_WIDTH;++k)CHECK(result.out[k]==0xa5);
            digest(&n,sizeof n);digest(result.out,(size_t)n);
            uint8_t flags[2]={v.sprite_overflow,v.sprite_collision};digest(flags,sizeof flags);
            v.sprite_overflow=before.sprite_overflow;v.sprite_collision=before.sprite_collision;
            CHECK(!memcmp(&before,&v,sizeof v));
            ++rows;pixels+=(unsigned)n;
        }
    }
    printf("{\"passed\":true,\"checks\":%u,\"rows\":%u,\"pixels\":%llu,\"hash\":\"%016llx\",\"cpu_seconds\":%.6f}\n",
        checks,rows,(unsigned long long)pixels,(unsigned long long)hash,
        (double)(clock()-begin)/CLOCKS_PER_SEC);
    return 0;
}
