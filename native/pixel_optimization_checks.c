/* Authored numeric pixels only. No ROM, window, game execution or display. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#include "planar_rows.h"
#include "scale2x.h"
#include "stereo_fir.h"
#include "nes_sprite_shift.h"
#ifdef _WIN32
#include <windows.h>
static double seconds(void) { LARGE_INTEGER a,b;QueryPerformanceCounter(&a);QueryPerformanceFrequency(&b);return (double)a.QuadPart/b.QuadPart; }
#else
static double seconds(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
#endif
static uint32_t seed=0x759ad02b;
static uint32_t value(void) {seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static uint64_t pixel_checks,planar_checks;
static unsigned sprite_checks,sprite_selection_checks;
static unsigned reference_sprite_first(const uint8_t *x,const uint8_t *lo,const uint8_t *hi,bool skipped) {
    for(unsigned i=0;i<8;++i)if((!x[i] || skipped) && ((lo[i]|hi[i])&128u))return i;
    return 8;
}
static void reference_shift(uint8_t x[8],uint8_t low[8],uint8_t high[8],bool skipped,bool render) {
    uint64_t a,b,c;memcpy(&a,x,8);memcpy(&b,low,8);memcpy(&c,high,8);
    if(!(a|b|c))return;
    for(unsigned i=0;i<8;i++) {
        if(x[i] && !skipped)--x[i];
        else if(render){low[i]<<=1;high[i]<<=1;}
    }
}
static volatile unsigned sprite_sink;
static double sprite_old,sprite_new;
static void sprites(void) {
    for(unsigned scene=0;scene<65536;scene++)for(unsigned mode=0;mode<4;mode++) {
        uint8_t a[24],b[24];
        for(unsigned i=0;i<24;i++)a[i]=scene<256?(uint8_t)scene:scene<512?(uint8_t)(i&1?0:scene):(uint8_t)value();
        memcpy(b,a,sizeof a);
        unsigned expected=reference_sprite_first(a,a+8,a+16,mode&1);
        if(rr_nes_sprite_first(b,b+8,b+16,mode&1)!=expected) {
            fprintf(stderr,"NES sprite priority mismatch scene=%u mode=%u\n",scene,mode);exit(1);
        }
        if(memcmp(a,b,sizeof a))abort(); /* selection must not mutate a unit */
        ++sprite_selection_checks;
        reference_shift(a,a+8,a+16,mode&1,mode&2);rr_nes_sprite_shift(b,b+8,b+16,mode&1,mode&2);
        if(memcmp(a,b,sizeof a)){fprintf(stderr,"NES shifter mismatch scene=%u mode=%u\n",scene,mode);exit(1);}
        ++sprite_checks;
    }
    for(unsigned mode=0;mode<2;mode++) {
        uint8_t s[24];for(unsigned i=0;i<24;i++)s[i]=(uint8_t)value();double start=seconds();
        for(unsigned n=0;n<4194304;n++) {
            /* The eight units are loaded during sprite fetches, then clocked
             * unchanged for the next visible span, as in the real PPU. */
            if(!(n&255))for(unsigned i=0;i<24;i++)s[i]=(uint8_t)(n+i*17);
            if(mode)rr_nes_sprite_shift(s,s+8,s+16,false,true);
            else reference_shift(s,s+8,s+16,false,true);
            sprite_sink=s[n&7]+s[8+(n&7)];
        }
        if(mode)sprite_new=seconds()-start;else sprite_old=seconds()-start;
    }
}
static uint64_t fir_checks;
static double fir_old,fir_new;
static void reference_fir(const int16_t *history,unsigned position,const float *coefficients,
        unsigned taps,double *left,double *right) {
    double l=0,r=0;
    for(unsigned tap=0;tap<taps;tap++) {
        unsigned p=(position+256u-tap)%256u; /* original fixed 256-tap ring */
        l+=history[p*2]*coefficients[tap];r+=history[p*2+1]*coefficients[tap];
    }
    *left=l;*right=r;
}
static volatile double sound_sink;
static void sound(void) {
    int16_t history[512];float coefficients[256];
    for(unsigned scene=0;scene<128;scene++) {
        for(unsigned i=0;i<512;i++)history[i]=scene==0?INT16_MIN:scene==1?INT16_MAX:(int16_t)value();
        for(unsigned i=0;i<256;i++)coefficients[i]=(int32_t)(value()%2000001-1000000)/1048576.0f;
        for(unsigned pos=0;pos<256;pos++) {
            double a[2],b[2];
            reference_fir(history,pos,coefficients,256,&a[0],&a[1]);
            rr_stereo_fir(history,pos,coefficients,256,&b[0],&b[1]);
            fir_checks+=2;
            if(memcmp(a,b,sizeof a)) {fprintf(stderr,"FIR differs scene=%u position=%u\n",scene,pos);exit(1);}
        }
    }
    for(unsigned mode=0;mode<2;mode++) {
        double start=seconds();
        for(unsigned n=0;n<262144;n++) {
            double a,b;
            if(mode)rr_stereo_fir(history,n&255,coefficients,256,&a,&b);
            else reference_fir(history,n&255,coefficients,256,&a,&b);
            sound_sink=a+b;
        }
        if(mode)fir_new=seconds()-start;else fir_old=seconds()-start;
    }
}
static void reference_scale(const uint32_t *s,int w,int h,int stride,uint32_t *d,int pitch) {
    for(int y=0;y<h;y++)for(int x=0;x<w;x++) {
        uint32_t e=s[y*stride+x],b=s[(y?y-1:y)*stride+x],z=s[(y+1<h?y+1:y)*stride+x];
        uint32_t l=s[y*stride+(x?x-1:x)],r=s[y*stride+(x+1<w?x+1:x)];
        uint32_t *p=d+y*2*pitch+x*2;
        if(b!=z && l!=r){p[0]=l==b?l:e;p[1]=b==r?r:e;p[pitch]=l==z?l:e;p[pitch+1]=z==r?r:e;}
        else p[0]=p[1]=p[pitch]=p[pitch+1]=e;
    }
}
static void planar(void) {
    for(unsigned n=0;n<65536;n++) {
        uint16_t planes[4]={(uint16_t)n,(uint16_t)value(),(uint16_t)value(),(uint16_t)value()};
        uint64_t row=0;
        for(unsigned pair=0;pair<4;pair++) {
            row|=rr_planar_pair(planes[pair])<<(pair*2);
            for(unsigned bit=0;bit<8;bit++) {
                unsigned expected=0;
                for(unsigned p=0;p<=pair;p++)expected|=(((planes[p]>>bit)&1)|(((planes[p]>>(bit+8))&1)<<1))<<(p*2);
                ++planar_checks;
                if(rr_planar_pixel(row,bit)!=expected)abort();
            }
        }
    }
}
static double scale_old,scale_new;
static void scale(void) {
    static const int sizes[][2]={{1,1},{1,7},{2,3},{3,1},{5,11},{7,5},{15,13},
        {160,144},{248,192},{256,192},{256,240},{256,239},{320,224},{512,478}};
    for(unsigned size=0;size<sizeof sizes/sizeof *sizes;size++)for(unsigned scene=0;scene<8;scene++) {
        int w=sizes[size][0],h=sizes[size][1],stride=w+3,pitch=w*2+5;
        size_t count=(size_t)pitch*(h*2+1)+8;
        uint32_t *source=malloc(((size_t)stride*h+8)*4),*a=malloc(count*4),*b=malloc(count*4);
        if(!source||!a||!b)abort();
        for(int n=0;n<stride*h+8;n++)source[n]=scene==0?0x5a3193u:scene==1?value():value()%16;
        memset(a,0xa5,count*4);memset(b,0xa5,count*4);
        reference_scale(source+1,w,h,stride,a+1,pitch);rr_scale2x(source+1,w,h,stride,b+1,pitch);
        pixel_checks+=(uint64_t)w*h*4;
        if(memcmp(a,b,count*4)){fprintf(stderr,"Scale2x mismatch %dx%d scene %u\n",w,h,scene);exit(1);}
        if(size==12) {
            double start=seconds();for(unsigned rep=0;rep<128;rep++)reference_scale(source+1,w,h,stride,a+1,pitch);
            scale_old+=seconds()-start;
            start=seconds();for(unsigned rep=0;rep<128;rep++)rr_scale2x(source+1,w,h,stride,b+1,pitch);
            scale_new+=seconds()-start;
            if(memcmp(a,b,count*4))abort();
        }
        free(source);free(a);free(b);
    }
}
#define SMS_SCREEN_W 256
#define SMS_SCREEN_H 192
static struct {uint8_t reg[16],vram[16384],cram[64],status;bool is_gg;} g_vdp;
#include "video_mode4.inc"
#include "mode4_reference.inc"
static double sms_old,sms_new;
static void mode4(void) {
    uint32_t a[256],b[256];
    for(unsigned scene=0;scene<128;scene++) {
        for(unsigned i=0;i<sizeof g_vdp.vram;i++)g_vdp.vram[i]=(uint8_t)value();
        for(unsigned i=0;i<sizeof g_vdp.cram;i++)g_vdp.cram[i]=(uint8_t)value();
        for(unsigned i=0;i<16;i++)g_vdp.reg[i]=(uint8_t)value();
        g_vdp.is_gg=!!(scene&1);reduce_sprite_flicker=!!(scene&2);g_vdp_force_display=!!(scene&4);
        sprite_tracking_reset();
        int sat=(g_vdp.reg[5]&0x7e)<<7;
        sprite_stable_reverse=!!(scene&8);sprite_tracking_sat=sat;
        sprite_tracking_mode=(g_vdp.reg[0]&8)|(g_vdp.reg[1]&3)|((g_vdp.reg[6]&4)<<4);
        memcpy(sprite_tracking_attributes,g_vdp.vram+sat,64);
        memcpy(sprite_tracking_attributes+64,g_vdp.vram+sat+128,128);
        for(int y=0;y<192;y++) {
            int hs=value()&255,vs=value()&255;
            for(int status=0;status<2;status++) {
                uint8_t initial=(uint8_t)value();g_vdp.status=initial;
                mode4_line_reference(a,y,hs,vs,status);uint8_t expected=g_vdp.status;
                g_vdp.status=initial;mode4_line(b,y,hs,vs,status);
                pixel_checks+=256;
                if(memcmp(a,b,sizeof a)||expected!=g_vdp.status) {
                    fprintf(stderr,"Mode4 mismatch scene=%u line=%d hs=%d vs=%d status=%d\n",scene,y,hs,vs,status);exit(1);
                }
            }
            /* Each line observes current VRAM and CRAM, without a stale cache. */
            g_vdp.vram[value()&16383]=(uint8_t)value();g_vdp.cram[value()&63]=(uint8_t)value();
        }
    }
    g_vdp.reg[1]=0x40;reduce_sprite_flicker=g_vdp_force_display=0;g_vdp.is_gg=false;
    for(unsigned mode=0;mode<2;mode++) {
        double start=seconds();
        for(unsigned i=0;i<32768;i++) {
            if(mode)mode4_line(b,i%192,i&255,(i>>8)&255,false);
            else mode4_line_reference(a,i%192,i&255,(i>>8)&255,false);
        }
        if(mode)sms_new=seconds()-start;else sms_old=seconds()-start;
    }
    if(memcmp(a,b,sizeof a))abort();
}
int main(void) {
    planar();scale();mode4();sound();sprites();
    printf("{\"passed\":true,\"planar_checks\":%llu,\"pixel_checks\":%llu,\"scale2x_sse2\":%s,"
        "\"scale2x_reference_seconds\":%.9f,\"scale2x_optimized_seconds\":%.9f,"
        "\"mode4_reference_seconds\":%.9f,\"mode4_optimized_seconds\":%.9f,"
        "\"fir_checks\":%llu,\"fir_sse2\":%s,\"fir_reference_seconds\":%.9f,\"fir_optimized_seconds\":%.9f,"
        "\"sprite_checks\":%u,\"sprite_selection_checks\":%u,\"sprite_reference_seconds\":%.9f,\"sprite_optimized_seconds\":%.9f}\n",
        (unsigned long long)planar_checks,(unsigned long long)pixel_checks,RR_SCALE2X_SIMD?"true":"false",
        scale_old,scale_new,sms_old,sms_new,(unsigned long long)fir_checks,RR_STEREO_FIR_SIMD?"true":"false",fir_old,fir_new,
        sprite_checks,sprite_selection_checks,sprite_old,sprite_new);return 0;
}
