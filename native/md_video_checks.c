/* Authored VDP patterns, host geometry and bounds. No cartridge or GUI. */
#include <stdio.h>
#include <stdlib.h>
#include "console16_video.h"
#include "video/genesis_vdp.h"
static unsigned checks, frames, old_dropped;
#define CHECK(ok) do { ++checks; if (!(ok)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#ok); exit(1); } } while (0)
static struct { uint32_t before, image[320*480], after; } target;
static uint8_t indices[GVDP_MAX_WIDTH];
static uint32_t row[GVDP_MAX_WIDTH];
static void render(int h40, int v30, int mode) {
    GVDP v; gvdp_init(&v);
    v.reg[1]=0x40|(v30?8:0); v.reg[12]=(h40?0x81:0)|(mode<<1);
    v.reg[2]=0x38; v.reg[4]=6; v.reg[5]=0x68; v.reg[16]=1;
    int width=h40?320:256, raster=v30?240:224, density=mode==3?2:1;
    CHECK(gvdp_screen_height(&v)==raster && gvdp_output_height(&v)==raster*density);
    /* Tile 1, every row a different nonzero palette index. IM2 cells use
     * sixteen rows and 64 bytes instead of eight rows and 32 bytes. */
    for(int y=0;y<8*density;++y) for(int x=0;x<4;++x)
        v.vram[32*density+y*4+x]=(uint8_t)(((y%15+1)<<4)|(y%15+1));
    for(int x=0;x<64*32;++x) { v.vram[0xe000+x*2+1]=1; v.vram[0xc000+x*2+1]=1; }
    memset(target.image,0,sizeof target.image); target.before=0x12345678; target.after=0x87654321;
    for(int y=0;y<raster*density;++y) {
        int n=gvdp_render_scanline(&v,y,indices); CHECK(n==width);
        for(int x=0;x<n;++x) row[x]=0xff000000u|indices[x];
        CHECK(rr16_video_copy_row(target.image,320,480,y,row,n));
        CHECK(target.image[y*320]==(0xff000000u|(y%(8*density)%15+1)));
        CHECK(target.image[y*320+width-1]==target.image[y*320]);
        if(y>=240) ++old_dropped;
    }
    CHECK(target.before==0x12345678 && target.after==0x87654321);
    CHECK(target.image[(raster*density-1)*320+width-1]!=0);
    if(width==256) CHECK(target.image[319]==0);
    if(raster*density<480) CHECK(target.image[raster*density*320]==0);
    uint64_t h=rr16_video_hash(target.image,320,width,raster*density,raster);
    /* Lower-field differences must contribute to a validation hash. */
    target.image[(raster*density-1)*320]^=0x55;
    CHECK(h!=rr16_video_hash(target.image,320,width,raster*density,raster));
    if(width<320) {
        h=rr16_video_hash(target.image,320,width,raster*density,raster);
        target.image[319]^=0x77;
        CHECK(h==rr16_video_hash(target.image,320,width,raster*density,raster)); }
    ++frames;
}
int main(void) {
    /* Start high, then shrink: no stale rows/columns after a mode switch. */
    for(int mode=3;mode>=0;--mode) for(int v30=1;v30>=0;--v30) for(int h40=1;h40>=0;--h40)
        render(h40,v30,mode);
    uint64_t h=rr16_video_hash(target.image,320,256,224,224);
    target.image[319]=1;target.image[400*320]=1;
    CHECK(h==rr16_video_hash(target.image,320,256,224,224));
    CHECK(h!=rr16_video_hash(target.image,320,256,224,112));
    uint32_t value=1;
    CHECK(!rr16_video_copy_row(target.image,320,480,-1,&value,1));
    CHECK(!rr16_video_copy_row(target.image,320,480,480,&value,1));
    CHECK(!rr16_video_copy_row(target.image,320,480,0,&value,-1));
    CHECK(!rr16_video_copy_row(target.image,320,480,0,row,321));
    CHECK(!rr16_video_copy_row(target.image,320,480,0,NULL,1));
    Rr16Rect r=rr16_video_rect(1920,1080,320,224,2,1);
    CHECK(r.x==320 && r.y==92 && r.w==1280 && r.h==896);
    r=rr16_video_rect(1920,1080,320,224,1,1);
    CHECK(r.x==320 && r.y==92 && r.w==1280 && r.h==896);
    r=rr16_video_rect(1920,1080,320,224,2,0);
    CHECK(r.w==1542 && r.h==1080 && r.x==189 && r.y==0);
    r=rr16_video_rect(1024,768,320,240,2,1);
    CHECK(r.w==640 && r.h==480 && r.x==192 && r.y==144);
    r=rr16_video_rect(320,224,320,224,2,1);
    CHECK(r.w==320 && r.h==224 && r.x==0 && r.y==0);
    r=rr16_video_rect(160,112,320,224,1,1);
    CHECK(r.w==160 && r.h==112);
    r=rr16_video_rect(0,0,320,224,2,1); CHECK(!r.w && !r.h);
    CHECK(old_dropped==896);
    printf("{\"checks\":%u,\"mode_frames\":%u,\"old_host_dropped_rows\":%u,\"passed\":true}\n",checks,frames,old_dropped);
    return 0;
}
