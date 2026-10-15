/* Authored pixel patterns only: no game data, window or visual capture. */
#undef NDEBUG
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "xbr_filter.h"
static RrXbrWeights weights;
int main(void) {
    uint32_t seed=7;
    for(int n=0;n<2000;n++) {
        seed=seed*1664525u+1013904223u;uint32_t a=seed;
        seed=seed*1664525u+1013904223u;uint32_t b=seed;
        for(unsigned weight=0;weight<=256;weight++) {
            uint32_t expected=0;
            for(unsigned shift=0;shift<=24;shift+=8)
                expected|=(((((a>>shift)&255)*(256-weight)+((b>>shift)&255)*weight+128)>>8)<<shift);
            assert(rr_xbr_mix(a,b,weight)==expected);
        }
    }
    uint32_t source[11*9], before[11*9], out[9*9*16+2];
    for(int pattern=0;pattern<6;pattern++) {
        for(int y=0;y<9;y++) for(int x=0;x<11;x++) {
            int white=pattern==0 ? 1 : pattern==1 ? x>=4 : pattern==2 ? y>=4 :
                pattern==3 ? x>=y : pattern==4 ? 2*x>=y+4 : ((x+y)&1);
            source[y*11+x]=white ? 0xffeeeeee : 0xff222222;
        }
        memcpy(before,source,sizeof source);
        out[0]=out[9*9*16+1]=0x13579bdf;
        rr_xbr4(source,9,9,11,out+1,&weights);
        assert(out[0]==0x13579bdf && out[9*9*16+1]==0x13579bdf);
        assert(!memcmp(source,before,sizeof source));
        int mixed=0;
        for(int y=0;y<36;y++) for(int x=0;x<36;x++) {
            uint32_t pixel=out[1+y*36+x];
            assert((pixel>>24)==255 && (pixel&255)>=0x22 && (pixel&255)<=0xee);
            mixed+=pixel!=0xffeeeeee && pixel!=0xff222222;
            if(pattern<3) assert(pixel==source[(y/4)*11+x/4]);
        }
        if(pattern==3 || pattern==4) assert(mixed>16);
        printf("PASS authored pattern %d: %d blended contour subpixels\n",pattern,mixed);
    }
    uint32_t single=0xffb79425, tiny[16];
    rr_xbr4(&single,1,1,1,tiny,&weights);
    for(int i=0;i<16;i++) assert(tiny[i]==single);
    uint32_t diagonal[81],turned[81],first[1296],rotated[1296];
    for(int y=0;y<9;y++) for(int x=0;x<9;x++) {
        diagonal[y*9+x]=x*2>=y+3 ? 0xffe3b329 : 0xff203143;
        turned[x*9+8-y]=diagonal[y*9+x];
    }
    rr_xbr4(diagonal,9,9,9,first,&weights);
    rr_xbr4(turned,9,9,9,rotated,&weights);
    for(int y=0;y<36;y++) for(int x=0;x<36;x++)
        assert(rr_xbr_rgb_distance(first[y*36+x],rotated[x*36+35-y])<=3);
    puts("PASS: packed blend matches scalar RGBA; rotated shallow contours agree within byte rounding.");
    /* Exact cache equivalence for stationary images, changing edge pixels,
     * alpha, scrolling/full redraws, padded rows and a reset/resolution change. */
    /* Tiny edge cases plus GB/GG, SMS, NES, MD/Neo Geo and SNES
     * high-resolution/interlaced presentation sizes, all with padded rows. */
    const int cache_sizes[][2]={{1,1},{3,2},{17,13},{160,144},{256,192},
        {256,224},{256,240},{320,224},{320,240},{320,480},{512,448},{512,478}};
    for(unsigned mode=0;mode<sizeof cache_sizes/sizeof cache_sizes[0];++mode) {
        int w=cache_sizes[mode][0],h=cache_sizes[mode][1],stride=w+3;
        uint32_t *src=calloc((size_t)stride*h,4),*previous=malloc((size_t)w*h*4);
        uint32_t *full=malloc((size_t)w*h*64),*cached=malloc((size_t)w*h*64);
        uint8_t *dirty=malloc((size_t)w*h),*scratch=malloc((size_t)w*h);
        assert(src && previous && full && cached && dirty && scratch);
        for(int frame=0;frame<30;++frame) {
            if(frame%7==0)for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
                seed=seed*1664525u+1013904223u;src[y*stride+x]=seed;
            }
            else if(frame%3) {
                int x=frame%2?w-1:0,y=frame%4?h-1:0;
                src[y*stride+x]^=0x80810201u;
            }
            rr_xbr4(src,w,h,stride,full,&weights);
            unsigned changed=rr_xbr_dirty(src,w,h,stride,previous,dirty,scratch,frame!=0 && frame!=17);
            if(changed)rr_xbr4_masked(src,w,h,stride,cached,&weights,dirty);
            assert(!memcmp(full,cached,(size_t)w*h*64));
            assert(!rr_xbr_dirty(src,w,h,stride,previous,dirty,scratch,1));
        }
        free(src);free(previous);free(full);free(cached);free(dirty);free(scratch);
    }
    puts("PASS: 360 cached frames byte-identical to full xBR across console resolutions, borders, alpha and cache reset.");
    /* Representative sparse edges, full-detail worst case, and largest 16-bit
     * frame. Measurement is CPU filter time, not physical input latency. */
    const int widths[]={256,256,320}, heights[]={240,240,480};
    LARGE_INTEGER frequency,start,end;QueryPerformanceFrequency(&frequency);
    for(int mode=0;mode<3;mode++) {
        int w=widths[mode],h=heights[mode],frames=80;
        uint32_t *src=malloc(w*h*4),*dst=malloc(w*h*16*4);assert(src && dst);
        for(int y=0;y<h;y++) for(int x=0;x<w;x++) {
            int bright=mode==1 ? ((x+y)&1) : (x/32+y/24)%3==0 ? ((x+y)%31<16) : 1;
            src[y*w+x]=bright ? 0xffea9b20 : 0xff1b4733;
        }
        rr_xbr4(src,w,h,w,dst,&weights);
        QueryPerformanceCounter(&start);
        for(int i=0;i<frames;i++) rr_xbr4(src,w,h,w,dst,&weights);
        QueryPerformanceCounter(&end);
        printf("CPU filter %dx%d pattern=%d: %.3f ms/frame\n",w,h,mode,1000.0*(end.QuadPart-start.QuadPart)/frequency.QuadPart/frames);
        free(src);free(dst);
    }
    return 0;
}
