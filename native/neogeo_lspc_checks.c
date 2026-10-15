/* Authored, ROM-free regression for the two-line sprite pipeline in states. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine/geo_lspc.c"
#include "sprite_scalar_reference.inc"
static unsigned checks;
static void require(int okay,const char *name) {
    ++checks;if(!okay) {fprintf(stderr,"Neo Geo LSPC check: %s\n",name);exit(2);}
}
static void packed_sprite_rows(void) {
    for(unsigned x=0;x<1024;++x)for(unsigned shrink=0;shrink<16;++shrink) {
        unsigned visible=0,pos=0;
        for(unsigned p=0;p<16;++p)if(lut_hshrink[shrink][p]) {
            visible+=((x+pos)&511u)<LSPC_WIDTH;++pos;
        }
        require(pos==shrink+1,"horizontal shrink output length");
        require(rr_ng_sprite_offscreen(x,shrink)==!visible,"offscreen reject preserves 512-pixel wrap");
    }
    static uint8_t bytes[128];romdata_t temporary={0};
    romdata_t *old_rom=romdata;unsigned old_cd=ngsys.cdmode;
    temporary.c=bytes;temporary.csz=sizeof bytes;romdata=&temporary;
    uint32_t seed=0x12345678;
    for(unsigned sample=0;sample<256;++sample) {
        for(unsigned n=0;n<sizeof bytes;++n) {
            seed=seed*1664525u+1013904223u;bytes[n]=(uint8_t)(seed>>24);
        }
        for(unsigned cd=0;cd<2;++cd) {
            ngsys.cdmode=cd;
            for(unsigned y=0;y<16;++y) {
                uint32_t rows[2]={rr_ng_sprite_row(bytes+y*4,cd),rr_ng_sprite_row(bytes+64+y*4,cd)};
                for(unsigned flip=0;flip<2;++flip)for(unsigned shrink=0;shrink<16;++shrink)
                    for(unsigned p=0;p<16;++p)if(lut_hshrink[shrink][p]) {
                        unsigned half=((p&8)^(flip?0:8))>>3,x=(p&7)^(flip?7:0);
                        require(((rows[half]>>(x*4))&15)==geo_lspc_tpix(half*64,x,y),
                            "packed sprite row equals scalar planar decoder, flip and shrink");
                    }
            }
        }
    }
    romdata=old_rom;ngsys.cdmode=old_cd;
}
static void whole_sprite_lines(void) {
    static uint8_t tiles[4096],zoom[65536];
    romdata_t fake={0};romdata_t *old_rom=romdata;
    unsigned old_cd=ngsys.cdmode,old_limit=sprlimit;
    fake.c=tiles;fake.csz=sizeof tiles;fake.l0=zoom;fake.l0sz=sizeof zoom;
    romdata=&fake;ngsys.cdmode=0;sprlimit=96;
    uint32_t seed=0x9b126f7d;unsigned expected[2][LSPC_WIDTH];
    for(unsigned n=0;n<sizeof tiles;++n){seed=seed*1664525u+1013904223u;tiles[n]=(uint8_t)(seed>>24);}
    for(unsigned n=0;n<sizeof zoom;++n)zoom[n]=(uint8_t)(n^(n>>8));
    for(unsigned scene=0;scene<128;++scene) {
        sprlimit=(scene&2)?381:96;
        for(unsigned n=0;n<0x8800;++n){seed=seed*1664525u+1013904223u;lspc.vram[n]=(uint16_t)(seed>>16);}
        for(unsigned i=1;i<382;++i) {
            /* Alternating maximal load and mixed shrink/chain/wrap scenes.
             * Invisible entries must still consume the 96-sprite budget. */
            if(!(scene&1)) {
                lspc.vram[0x8200+i]=32;
                lspc.vram[0x8400+i]=(uint16_t)(((i*13+scene*5)&511)<<7);
                lspc.vram[0x8000+i]=0x0fff;
            }
        }
        lspc.scanline=LSPC_LINE_BUFSTART+(scene*7)%264;lspc.aa_counter=scene&7;lspc.aa_disable=scene&8;
        lbactive=scene&1;memset(linebuf,0,sizeof linebuf);
        rr_ng_scalar_sprcalc();memcpy(expected,linebuf,sizeof expected);unsigned selector=lbactive;
        lbactive=scene&1;memset(linebuf,0,sizeof linebuf);geo_lspc_sprcalc();
        require(selector==lbactive && !memcmp(expected,linebuf,sizeof expected),
            "complete sprite line matches pinned scalar renderer under load");
    }
    romdata=old_rom;ngsys.cdmode=old_cd;sprlimit=old_limit;
}
static void specification(void) {
    require(LSPC_PIXELS==384 && LSPC_SCANLINES==264 && LSPC_WIDTH==320,"documented MVS raster geometry");
    geo_lspc_vramaddr_wr(0x7fff);geo_lspc_vrammod_wr(1);geo_lspc_vram_wr(0xabcd);
    require(lspc.vram[0x7fff]==0xabcd && lspc.vramaddr==0,"lower VRAM wraps within bank");
    geo_lspc_vramaddr_wr(0x8000);geo_lspc_vrammod_wr(-1);geo_lspc_vram_wr(0x1234);
    require(lspc.vram[0x8000]==0x1234 && lspc.vramaddr==0xffff,"signed modulo preserves upper VRAM bank");
    geo_lspc_vramaddr_wr(0x8000);require(geo_lspc_vram_rd()==0x1234 && lspc.vramaddr==0x8000,"read does not auto increment");
    lspc.aa_timer=0;lspc.aa_counter=7;geo_lspc_mode_wr(0x0200);geo_lspc_aa();
    require(lspc.aa_counter==0 && lspc.aa_timer==2,"animation wraps and reloads speed");
    geo_lspc_aa();geo_lspc_aa();require(!lspc.aa_counter,"animation waits reload+1 frames");
    geo_lspc_aa();require(lspc.aa_counter==1,"animation advances after reload+1 frames");
    static uint8_t tiles[256],shrink[65536];
    memset(tiles,0,sizeof tiles);
    for(unsigned row=0;row<16;++row) {
        tiles[row*4]=tiles[row*4+64]=0xff; // solid colour index 1
        tiles[128+row*4+2]=tiles[128+row*4+64+2]=0xff; // solid index 2
    }
    for(unsigned x=0;x<65536;++x)shrink[x]=(uint8_t)x;
    romdata->c=tiles;romdata->csz=sizeof tiles;romdata->l0=shrink;romdata->l0sz=sizeof shrink;
    crommask=1;ngsys.cdmode=0;memset(lspc.vram,0,sizeof lspc.vram);
    lspc.scanline=LSPC_LINE_BUFSTART;lspc.aa_disable=1;lspc.palbank=0;
    for(unsigned i=1;i<=97;++i) {
        lspc.vram[0x8000+i]=0x0fff;lspc.vram[0x8200+i]=1;
        lspc.vram[i*64]=i==97?1:0;
    }
    memset(linebuf,0,sizeof linebuf);lbactive=0;sprlimit=96;
    geo_lspc_sprcalc();require(linebuf[0][0]==1,"97th sprite excluded at real 96 sprite cap");
    memset(linebuf,0,sizeof linebuf);lbactive=0;sprlimit=381;
    geo_lspc_sprcalc();require(linebuf[0][0]==2,"enhanced rendering includes the otherwise clipped 97th column");
    sprlimit=96;
    lspc.vram[0x8200+3]=0; // leave only sprites 1 and 2 for priority/shrink tests
    for(unsigned i=3;i<=97;++i)lspc.vram[0x8200+i]=0;
    lspc.vram[128]=1;memset(linebuf,0,sizeof linebuf);lbactive=0;
    geo_lspc_sprcalc();require(linebuf[0][0]==2 && linebuf[0][15]==2 && !linebuf[0][16],"higher sprite number draws in front");
    lspc.vram[0x8202]=0;
    for(unsigned size=0;size<16;++size) {
        memset(linebuf,0,sizeof linebuf);lbactive=0;lspc.vram[0x8001]=(size<<8)|0xff;
        geo_lspc_sprcalc();unsigned count=0;
        for(unsigned x=0;x<320;++x)if(linebuf[0][x])++count;
        require(count==size+1,"horizontal shrink produces documented 1..16 pixels");
    }
    reg_disblspr=reg_disblfix=1;
    lspc.scanline=247;lspc.cyc=573;ngsys.irq2_ctrl=0x40;ngsys.irq2_reload=767;ngsys.irq2_counter=123;
    geo_lspc_run(196);require(lspc.scanline==248,"scanline wraps at 384 pixel clocks");
    geo_lspc_run(574);require(ngsys.irq2_counter==768,"vblank reload includes zero pixel");
    lspc.scanline=263;lspc.cyc=712;geo_lspc_run(1);require(!lspc.scanline,"264th scanline wraps raster");
}
int main(void) {
    static uint32_t pixels[LSPC_WIDTH*264];
    uint8_t saved[RR_NG_LSPC_EXTRA_BYTES],again[RR_NG_LSPC_EXTRA_BYTES];
    packed_sprite_rows();whole_sprite_lines();unsigned decode_checks=checks;checks=0;
    geo_lspc_init();geo_lspc_set_buffer(pixels);specification();
    unsigned spec_checks=checks;checks=0;
    for(unsigned n=0;n<SIZE_8K;++n)palette_normal[n]=0xff000000|n;
    lspc.palbank=0;lspc.scanline=1;
    for(unsigned active=0;active<2;++active) {
        for(unsigned row=0;row<2;++row)for(unsigned x=0;x<LSPC_WIDTH;++x)
            linebuf[row][x]=1+(row*LSPC_WIDTH+x)%8191;
        lbactive=active;reg_disblspr=0x1234;reg_disblfix=0x5678;reg_envideo=1;
        require(rr_ng_lspc_extra_save(saved,sizeof saved)==sizeof saved,"capture both line buffers");
        memset(linebuf,0,sizeof linebuf);lbactive^=1;reg_disblspr=reg_disblfix=reg_envideo=0;
        require(rr_ng_lspc_extra_restore(saved,sizeof saved),"restore sprite pipeline");
        rr_ng_lspc_extra_save(again,sizeof again);
        require(!memcmp(saved,again,sizeof saved),"restore indices, selector and render registers");
        geo_lspc_bdsprline();
        for(unsigned x=0;x<LSPC_WIDTH;++x) {
            if(pixels[LSPC_WIDTH+x]!=(0xff000000|1+(active*LSPC_WIDTH+x)%8191) ||
               linebuf[active][x] || !linebuf[active^1][x])
                require(0,"first resumed line uses and consumes only the saved active buffer");
        }
        require(1,"first resumed scanline matches captured palette indices");
        require(rr_ng_lspc_extra_restore(saved,sizeof saved),"restore before invalid-state tests");
        const unsigned offsets[]={0,4,20,35};
        for(unsigned n=0;n<sizeof offsets/sizeof *offsets;++n) {
            uint8_t bad[RR_NG_LSPC_EXTRA_BYTES];memcpy(bad,saved,sizeof bad);bad[offsets[n]]=255;
            require(!rr_ng_lspc_extra_restore(bad,sizeof bad),"invalid pipeline rejected");
            rr_ng_lspc_extra_save(again,sizeof again);
            require(!memcmp(saved,again,sizeof saved),"invalid pipeline did not mutate state");
        }
        require(!rr_ng_lspc_extra_restore(saved,sizeof saved-1),"truncated pipeline rejected");
        require(!rr_ng_lspc_extra_restore(saved,sizeof saved+1),"trailing pipeline rejected");
    }
    printf("{\"passed\":true,\"sprite_pipeline_checks\":%u,\"video_spec_checks\":%u,\"sprite_decode_checks\":%u,\"synthetic_inputs_only\":true}\n",checks,spec_checks,decode_checks);
    return 0;
}
