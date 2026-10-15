/* xBR-lv2 contour reconstruction, CPU adaptation of Hyllian's MIT shader.
 * Copyright (C) 2011-2016 Hyllian - sergiogdb@gmail.com
 * Incorporates ideas from SABR by Joshua Street.
 * RetroRecomp adaptation: fixed 4x coverage, integer RGB mixing, shared SDL host.
 * Full permission and warranty notice: licenses/xbr.md.
 * Pinned upstream: libretro/glsl-shaders 235448f244bf676d135f7b25ea6b8e1eae41c4e4
 * xbr/shaders/xbr-lv2.glsl (CORNER_C, SMOOTH_TIPS, default detail rules).
 */
#ifndef RR_XBR_FILTER_H
#define RR_XBR_FILTER_H
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#define RR_XBR_SCALE 4

static float rr_xbr_luma(uint32_t p) {
    return (14.352f * ((p >> 16) & 255) + 28.176f * ((p >> 8) & 255) + 5.472f * (p & 255)) / 255.0f;
}
static uint32_t rr_xbr_mix(uint32_t a, uint32_t b, unsigned weight) {
    if (!weight || a==b) return a;
    if (weight==256) return b;
    unsigned inv = 256 - weight;
    uint32_t rb=(((a&0x00ff00ff)*inv+(b&0x00ff00ff)*weight+0x00800080)>>8)&0x00ff00ff;
    uint32_t ag=(((a>>8)&0x00ff00ff)*inv+((b>>8)&0x00ff00ff)*weight+0x00800080)&0xff00ff00;
    return rb|ag;
}
static int rr_xbr_rgb_distance(uint32_t a, uint32_t b) {
    int sum = 0;
    for (unsigned shift = 0; shift < 24; shift += 8) {
        int d = (int)((a >> shift) & 255) - (int)((b >> shift) & 255);
        sum += d < 0 ? -d : d;
    }
    return sum;
}
static float rr_xbr_wd(float a,float b,float c,float d,float e,float f,float g,float h) {
    return fabsf(a-b)+fabsf(a-c)+fabsf(d-e)+fabsf(d-f)+4.0f*fabsf(g-h);
}

/* Coverage for four rotations, sixteen edge-flag combinations, sixteen
 * subpixels. Prepared once per host; never touched by audio/guest threads. */
typedef struct { uint16_t weights[4][16][16]; int ready; } RrXbrWeights;
static void rr_xbr_weights(RrXbrWeights *table) {
    static const float a[4]={1,-1,-1,1}, b[4]={1,1,-1,-1}, c[4]={1.5f,.5f,-.5f,.5f};
    static const float bx[4]={.5f,2,-.5f,-2}, cx[4]={1,1,-.5f,0};
    static const float by[4]={2,.5f,-2,-.5f}, cy[4]={2,0,-1,.5f};
    if (table->ready) return;
    for (int r=0;r<4;r++) for (int flags=0;flags<16;flags++)
        for (int y=0;y<4;y++) for (int x=0;x<4;x++) {
            float px=(x+.5f)/4, py=(y+.5f)/4, dl=(r&1)? .25f:.125f, du=(r&1)? .125f:.25f;
            float values[4]={
                (a[r]*py+b[r]*px+.25f-c[r]-.25f)/.5f,
                (a[r]*py+b[r]*px+.25f-c[r])/.5f,
                (a[r]*py+bx[r]*px+dl-cx[r])/(2*dl),
                (a[r]*py+by[r]*px+du-cy[r])/(2*du)};
            float weight=0;
            for (int k=0;k<4;k++) if ((flags & (1<<k)) && values[k]>weight) weight=values[k];
            table->weights[r][flags][y*4+x]=(uint16_t)(weight>=1 ? 256 : weight*256);
        }
    table->ready=1;
}

/* An output block depends only on its clamped 5x5 source neighbourhood.
 * Dilate exact pixel differences by two in each axis. Cached output is reused
 * only when every contributing source pixel is unchanged (no temporal blend). */
static unsigned rr_xbr_dirty(const uint32_t *src,int w,int h,int stride,
    uint32_t *previous,uint8_t *dirty,uint8_t *scratch,int valid) {
    unsigned count=0;
    for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
        int i=y*w+x;uint32_t value=src[y*stride+x];
        dirty[i]=(uint8_t)(!valid || value!=previous[i]);previous[i]=value;
    }
    for(int y=0;y<h;++y) {
        unsigned sum=0;
        for(int x=0;x<w && x<2;++x)sum+=dirty[y*w+x];
        for(int x=0;x<w;++x) {
            if(x+2<w)sum+=dirty[y*w+x+2];
            scratch[y*w+x]=(uint8_t)(sum!=0);
            if(x>=2)sum-=dirty[y*w+x-2];
        }
    }
    for(int x=0;x<w;++x) {
        unsigned sum=0;
        for(int y=0;y<h && y<2;++y)sum+=scratch[y*w+x];
        for(int y=0;y<h;++y) {
            if(y+2<h)sum+=scratch[(y+2)*w+x];
            dirty[y*w+x]=(uint8_t)(sum!=0);count+=sum!=0;
            if(y>=2)sum-=scratch[(y-2)*w+x];
        }
    }
    return count;
}

static void rr_xbr4_masked(const uint32_t *src,int w,int h,int stride,uint32_t *dst,RrXbrWeights *table,const uint8_t *dirty) {
    /* Five rolling metric rows: each source pixel is converted once. No
     * allocation, state from older frames, or repeated 5x5 RGB conversions. */
    float rows[5][1028];
    if(w<1 || w>1024 || h<1 || stride<w) return;
    rr_xbr_weights(table);
    for(int j=0;j<4;j++) {
        int sy=j-2; if(sy<0)sy=0;if(sy>=h)sy=h-1;
        for(int x=0;x<w;x++) rows[j][x+2]=rr_xbr_luma(src[sy*stride+x]);
        rows[j][0]=rows[j][1]=rows[j][2];rows[j][w+2]=rows[j][w+3]=rows[j][w+1];
    }
    for (int y=0;y<h;y++) {
      float *last=rows[(y+4)%5];int sy=y+2<h?y+2:h-1;
      for(int x=0;x<w;x++) last[x+2]=rr_xbr_luma(src[sy*stride+x]);
      last[0]=last[1]=last[2];last[w+2]=last[w+3]=last[w+1];
      const float *row[5];for(int j=0;j<5;j++)row[j]=rows[(y+j)%5];
      for (int x=0;x<w;x++) {
        if(dirty && !dirty[y*w+x])continue;
        uint32_t center=src[y*stride+x];
        uint32_t *out=dst+y*4*w*4+x*4;
        /* Flat interiors require no neighbourhood metric or interpolation. */
        uint32_t north=src[(y?y-1:y)*stride+x], south=src[(y+1<h?y+1:y)*stride+x];
        uint32_t west=src[y*stride+(x?x-1:x)], east=src[y*stride+(x+1<w?x+1:x)];
        if (center==north && center==south && center==west && center==east) {
            for(int j=0;j<4;j++) for(int i=0;i<4;i++) out[j*w*4+i]=center;
            continue;
        }
        float luma[25];
        for(int j=0;j<5;j++) for(int i=0;i<5;i++) luma[j*5+i]=row[j][x+i];
        /* Shader vector swizzles expressed as four clockwise neighbourhoods. */
        static const int bi[4]={7,11,17,13}, ci[4]={8,6,16,18};
        static const int i4i[4]={19,3,5,21}, i5i[4]={23,9,1,15}, h5i[4]={22,14,2,10};
        uint32_t cardinal[4]={east,north,west,south}, secondary[4]={south,east,north,west}, color[4];
        const uint16_t *weight[4];
        for(int r=0;r<4;r++) {
            float e=luma[12],b=luma[bi[r]],c=luma[ci[r]],d=luma[bi[(r+1)%4]],f=luma[bi[(r+3)%4]];
            float g=luma[ci[(r+2)%4]],h0=luma[bi[(r+2)%4]],i=luma[ci[(r+3)%4]];
            float i4=luma[i4i[r]],i5=luma[i5i[r]],h5=luma[h5i[r]],f4=luma[h5i[(r+1)%4]];
#define RR_XEQ(a,b) (fabsf((a)-(b))<=15.0f)
            int edge0=e!=f && e!=h0;
            int edge1=edge0 && ((!RR_XEQ(f,b) && !RR_XEQ(f,c)) || (!RR_XEQ(h0,d) && !RR_XEQ(h0,g)) ||
                (RR_XEQ(e,i) && ((!RR_XEQ(f,f4) && !RR_XEQ(f,i4)) || (!RR_XEQ(h0,h5) && !RR_XEQ(h0,i5)))) || RR_XEQ(e,g) || RR_XEQ(e,c));
            float wd1=rr_xbr_wd(e,c,g,i,h5,f4,h0,f),wd2=rr_xbr_wd(h0,d,i5,f,i4,b,e,i);
            int tip=edge0 && wd1<=wd2, edge=edge1 && wd1+.1f<=wd2;
            int shallow=edge && e!=g && d!=g && 2*fabsf(f-g)<=fabsf(h0-c);
            int steep=edge && e!=c && b!=c && 2*fabsf(h0-c)<=fabsf(f-g);
            weight[r]=table->weights[r][tip | (edge<<1) | (shallow<<2) | (steep<<3)];
            color[r]=fabsf(e-f)<=fabsf(e-h0) ? cardinal[r] : secondary[r];
#undef RR_XEQ
        }
        for(int j=0;j<4;j++) for(int i=0;i<4;i++) {
            int p=j*4+i;
            uint32_t a=rr_xbr_mix(rr_xbr_mix(center,color[0],weight[0][p]),color[2],weight[2][p]);
            uint32_t b=rr_xbr_mix(rr_xbr_mix(center,color[1],weight[1][p]),color[3],weight[3][p]);
            out[j*w*4+i]=a==b ? a : rr_xbr_rgb_distance(center,a)<=rr_xbr_rgb_distance(center,b) ? b : a;
        }
      }
    }
}
static void rr_xbr4(const uint32_t *src,int w,int h,int stride,uint32_t *dst,RrXbrWeights *table) {
    rr_xbr4_masked(src,w,h,stride,dst,table,NULL);
}
#endif
