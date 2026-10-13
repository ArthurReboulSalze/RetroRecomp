/* Original arithmetic and suspended-device-state tests; no firmware data. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "snes/cx4.h"
#include "snes/dsp1.h"
#include "snes/dsp1_hle.h"
#include "snes_dsp1_vectors.h"
#include "snes/saveload.h"
#include "snes/cart.h"
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"line %u: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {SaveLoadInfo stream;unsigned pos;bool load;uint8_t bytes[8192];} Stream;
static void transfer(SaveLoadInfo *s,void *data,size_t n){Stream *p=(Stream*)s;
    CHECK(p->pos+n<=sizeof p->bytes);if(p->load)memcpy(data,p->bytes+p->pos,n);else memcpy(p->bytes+p->pos,data,n);p->pos+=(unsigned)n;}
static void put(Dsp1 *d,uint64_t *clock,uint8_t byte){*clock+=64;dsp1_sync(d,*clock);dsp1_write(d,0,byte);}
static uint8_t get(Dsp1 *d,uint64_t *clock){*clock+=64;dsp1_sync(d,*clock);return dsp1_read(d,0);}
static void horizon(void) {
    for(unsigned n=0;n<sizeof(rr_dsp1_expected)/sizeof(rr_dsp1_expected[0]);n++) {
        Dsp1HleState state;dsp1_hle_state_reset(&state);
        const uint16_t *inputs[]={rr_dsp1_projection[n],rr_dsp1_target[n],rr_dsp1_point[n],rr_dsp1_raster[n]};
        const uint8_t commands[]={2,14,6,10},lengths[]={7,2,3,1};unsigned offset=0;
        for(unsigned c=0;c<4;c++) {
            int16_t input[7]={0},out[4]={0};uint8_t count=0;
            for(unsigned i=0;i<lengths[c];i++)input[i]=(int16_t)inputs[c][i];
            CHECK(dsp1_hle_execute_state(&state,commands[c],input,lengths[c],out,4,&count));
            for(unsigned i=0;i<count*2;i++) {
                uint8_t actual=(uint8_t)((uint16_t)out[i/2]>>(8*(i%2)));
                if(actual!=rr_dsp1_expected[n][offset+i])fprintf(stderr,"horizon %u cmd %02x byte %u\n",n,commands[c],i);
                CHECK(actual==rr_dsp1_expected[n][offset+i]);
            }
            offset+=count*2;
        }
        CHECK(offset==26 && state.projection_valid);
    }
}
static void horizon_resume(void) {
    const unsigned cases[]={2,3,89,110,119,127};
    for(unsigned n=0;n<sizeof(cases)/sizeof(cases[0]);n++) {
        unsigned row=cases[n];Dsp1 *a=dsp1_create(),*b=dsp1_create();
        CHECK(a && b);dsp1_load_firmware(a,NULL);dsp1_load_firmware(b,NULL);
        uint64_t ca=500000,cb;
        put(a,&ca,2);
        for(unsigned i=0;i<7;i++) {
            put(a,&ca,(uint8_t)rr_dsp1_projection[row][i]);
            put(a,&ca,(uint8_t)(rr_dsp1_projection[row][i]>>8));
        }
        ca+=5000;dsp1_sync(a,ca);
        for(unsigned i=0;i<8;i++)CHECK(get(a,&ca)==rr_dsp1_expected[row][i]);
        Stream s={{transfer,NULL},0,false,{0}};dsp1_saveload(a,&s.stream);
        s.pos=0;s.load=true;dsp1_saveload(b,&s.stream);cb=ca;
        const uint16_t *inputs[]={rr_dsp1_target[row],rr_dsp1_point[row],rr_dsp1_raster[row]};
        const unsigned commands[]={14,6,10},lengths[]={2,3,1},bytes[]={4,6,8};
        unsigned offset=8;
        for(unsigned c=0;c<3;c++) {
            put(a,&ca,commands[c]);put(b,&cb,commands[c]);
            for(unsigned i=0;i<lengths[c];i++) {
                put(a,&ca,(uint8_t)inputs[c][i]);put(a,&ca,(uint8_t)(inputs[c][i]>>8));
                put(b,&cb,(uint8_t)inputs[c][i]);put(b,&cb,(uint8_t)(inputs[c][i]>>8));
            }
            ca+=5000;cb+=5000;dsp1_sync(a,ca);dsp1_sync(b,cb);
            for(unsigned i=0;i<bytes[c];i++) {
                uint8_t value=get(a,&ca);CHECK(value==rr_dsp1_expected[row][offset+i]);
                CHECK(get(b,&cb)==value);
            }
            offset+=bytes[c];
        }
        CHECK(!dsp1_hle_failed(a) && !dsp1_hle_failed(b));dsp1_destroy(a);dsp1_destroy(b);
    }
}
static void independent_operations(void) {
    Dsp1HleState state;int16_t out[4];uint8_t count;
    dsp1_hle_state_reset(&state);
    {const int16_t input[]={0,0,0,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,28,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==998);
    CHECK(out[1]==-2000);
    CHECK(out[2]==2998);
    }
    {const int16_t input[]={0,0,0,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,60,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==998);
    CHECK(out[1]==-2000);
    CHECK(out[2]==2998);
    }
    {const int16_t input[]={8192,16384,24576,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,28,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==-2999);
    CHECK(out[1]==999);
    CHECK(out[2]==2001);
    }
    {const int16_t input[]={8192,16384,24576,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,60,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==-2999);
    CHECK(out[1]==999);
    CHECK(out[2]==2001);
    }
    {const int16_t input[]={4660,43981,12609,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,28,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==2621);
    CHECK(out[1]==-2158);
    CHECK(out[2]==1575);
    }
    {const int16_t input[]={4660,43981,12609,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,60,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==2621);
    CHECK(out[1]==-2158);
    CHECK(out[2]==1575);
    }
    {const int16_t input[]={32768,49152,32767,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,28,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==3000);
    CHECK(out[1]==-2000);
    CHECK(out[2]==-999);
    }
    {const int16_t input[]={32768,49152,32767,1000,-2000,3000};
    CHECK(dsp1_hle_execute_state(&state,60,input,6,out,4,&count));CHECK(count==3);
    CHECK(out[0]==3000);
    CHECK(out[1]==-2000);
    CHECK(out[2]==-999);
    }
    {const int16_t input[]={4660,16384};
    CHECK(dsp1_hle_execute_state(&state,0,input,2,out,4,&count));CHECK(count==1);
    CHECK(out[0]==2330);
    }
    {const int16_t input[]={0};
    CHECK(dsp1_hle_execute_state(&state,7,input,1,out,4,&count));CHECK(count==1);
    CHECK(out[0]==0);
    }
    {const int16_t input[]={32767};
    CHECK(dsp1_hle_execute_state(&state,15,input,1,out,4,&count));CHECK(count==1);
    CHECK(out[0]==0);
    }
    {const int16_t input[]={0};
    CHECK(dsp1_hle_execute_state(&state,39,input,1,out,4,&count));CHECK(count==1);
    CHECK(out[0]==256);
    }
    {const int16_t input[]={32767};
    CHECK(dsp1_hle_execute_state(&state,47,input,1,out,4,&count));CHECK(count==1);
    CHECK(out[0]==256);
    }
    {const int16_t input[]={0,0,0,16384};
    CHECK(dsp1_hle_execute_state(&state,56,input,4,out,4,&count));CHECK(count==1);
    CHECK(out[0]==-8191);
    }
}

static void aliases(void) {
    static const uint8_t pairs[][2]={{48,16},{36,4},{44,12},{60,28},{18,2},{34,2},{50,2},{26,10},{42,10},{58,10},{22,6},{38,6},{54,6},{30,14},{46,14},{62,14},{5,1},{53,1},{49,1},{21,17},{37,33},{9,13},{57,13},{61,13},{25,29},{41,45},{51,3},{59,11},{52,20},{7,15},{39,47}};
    for(unsigned i=0;i<sizeof(pairs)/sizeof(pairs[0]);i++)for(unsigned seed=0;seed<32;seed++) {
        uint8_t alias=pairs[i][0],canonical=pairs[i][1],ni,no,ai,ao,ca=0,cb=0;
        CHECK(dsp1_hle_command_shape(alias,&ai,&ao));
        CHECK(dsp1_hle_command_shape(canonical,&ni,&no));CHECK(ai==ni && ao==no);
        Dsp1HleState a,b;dsp1_hle_state_reset(&a);
        int16_t projection[]={128,256,1024,512,1024,0,4096},out[4];uint8_t count;
        CHECK(dsp1_hle_execute_state(&a,2,projection,7,out,4,&count));b=a;
        int16_t input[7]={0},oa[4]={0},ob[4]={0};
        for(unsigned n=0;n<7;n++)input[n]=(int16_t)(seed*179+n*253);
        if(canonical==2)memcpy(input,projection,sizeof projection);
        CHECK(dsp1_hle_execute_state(&a,alias,input,ai,oa,4,&ca));
        CHECK(dsp1_hle_execute_state(&b,canonical,input,ni,ob,4,&cb));
        CHECK(ca==cb && !memcmp(oa,ob,ca*sizeof(int16_t)));
        CHECK(!memcmp(&a,&b,sizeof a));
    }
    for(unsigned seed=0;seed<256;seed++) {
        int16_t input[]={0,0,0,0x4000},out[4];uint8_t count;Dsp1HleState state;
        dsp1_hle_state_reset(&state);
        CHECK(dsp1_hle_execute_state(&state,0x38,input,4,out,4,&count));CHECK(count==1 && out[0]==-8191);
        input[0]=(int16_t)seed;
        CHECK(dsp1_hle_execute_state(&state,0x0f,input,1,out,4,&count));CHECK(out[0]==0);
        CHECK(dsp1_hle_execute_state(&state,0x2f,input,1,out,4,&count));CHECK(out[0]==256);
    }
}

static void dsp(void){
    aliases();
    independent_operations();
    horizon();
    horizon_resume();
    /* Independent Snes9x outputs for eight authored screen/ground cases.
     * These are numeric results, never firmware or original-game data. */
    const uint16_t az[]={0,0,0,0x2000,0x2000,0x4000,0x6000,0x8000};
    const int16_t h[]={16,16,-16,16,-32,0,32,16},v[]={80,80,80,80,64,96,32,64};
    const uint8_t expected[8][12]={
        {0,0,0,0,0,0,0,0,0,0,0,0},
        {0,0,0x57,0xf6,0x80,0,0x59,0xff,0x97,0,0xdc,0xff},
        {0,0,0x57,0xf6,0x80,0,0x59,0xff,0x67,0,0xdc,0xff},
        {0,0,0x57,0xf6,0xaa,1,0xd5,0xff,0x5c,1,0x22,0},
        {0,0,0x57,0xf6,0xaa,1,0xd5,0xff,0x3b,1,0x43,0},
        {0,0,0x57,0xf6,0x26,2,0,1,0x88,1,0,1},
        {0,0,0x57,0xf6,0xaa,1,0x2b,2,0x5f,1,0xe1,1},
        {0,0,0x57,0xf6,0x80,0,0xa7,2,0x68,0,0x3d,2}};
    for(unsigned n=0;n<8;n++){
        Dsp1 *d=dsp1_create();dsp1_load_firmware(d,NULL);uint64_t clock=0;
        if(n){const uint16_t params[]={128,256,1024,512,1024,az[n],4096};put(d,&clock,2);
            for(unsigned p=0;p<7;p++){put(d,&clock,(uint8_t)params[p]);put(d,&clock,(uint8_t)(params[p]>>8));}
            clock+=5000;dsp1_sync(d,clock);
            for(unsigned p=0;p<8;p++){uint8_t out=get(d,&clock);
                if(out!=expected[n][p])fprintf(stderr,"vector %u byte %u got %02x expected %02x\n",n,p,out,expected[n][p]);
                CHECK(out==expected[n][p]);}}
        put(d,&clock,0x0e);put(d,&clock,(uint8_t)h[n]);put(d,&clock,(uint8_t)((uint16_t)h[n]>>8));
        put(d,&clock,(uint8_t)v[n]);put(d,&clock,(uint8_t)((uint16_t)v[n]>>8));
        clock+=5000;dsp1_sync(d,clock);
        for(unsigned p=8;p<12;p++){uint8_t out=get(d,&clock);
            if(out!=expected[n][p])fprintf(stderr,"vector %u byte %u got %02x expected %02x\n",n,p,out,expected[n][p]);
            CHECK(out==expected[n][p]);}
        CHECK(!dsp1_hle_failed(d));dsp1_destroy(d);
    }
    const int16_t rotation[6][6]={{0,0,0,100,100,20},{0x1000,0x1000,0x2000,100,-64,32},
        {0x2000,0x2000,0x4000,-100,96,-48},{0x4000,0x2000,0x6000,32,-32,16},
        {0,0,0,-100,-100,-20},{0x7000,0,(int16_t)0x8000,100,100,0}};
    const uint8_t rotation_expected[6][6]={{0x63,0,0x63,0,0x14,0},{0x7d,0x10,0x18,0x10,0x15,0x20},
        {0x78,0x1f,0x9c,0x1f,0x70,0x3f},{0,0x40,0x2c,0x20,0x3d,0x60},
        {0x9c,0xff,0x9c,0xff,0xec,0xff},{0x9c,0x6f,0x9c,0xff,0,0x80}};
    for(unsigned n=0;n<6;n++){
        Dsp1 *d=dsp1_create();dsp1_load_firmware(d,NULL);uint64_t clock=0;put(d,&clock,0x14);
        for(unsigned p=0;p<6;p++){put(d,&clock,(uint8_t)rotation[n][p]);put(d,&clock,(uint8_t)((uint16_t)rotation[n][p]>>8));}
        clock+=5000;dsp1_sync(d,clock);
        for(unsigned p=0;p<6;p++){uint8_t out=get(d,&clock);
            if(out!=rotation_expected[n][p])fprintf(stderr,"rotation %u byte %u got %02x expected %02x\n",n,p,out,rotation_expected[n][p]);
            CHECK(out==rotation_expected[n][p]);}
        CHECK(!dsp1_hle_failed(d));dsp1_destroy(d);
    }
    const int16_t attitude[6][4]={{0x4000,0,0,0},{0x4000,0x2000,0x1000,0x4000},
        {0x7fff,0x4000,0x2000,0x1000},{0x4000,0x6000,0x1000,0x2000},
        {0x7fff,(int16_t)0x8000,0x1000,0},{0x2000,0x2000,0x6000,0x1000}};
    const uint8_t attitude_expected[6][14]={{0x18,0,0xec,0xff,0x0e,0,0x18,0,0xec,0xff,0x0e,0,0x18,0},
        {0x22,0,0xfd,0xff,2,0,0x14,0,0xfe,0xff,0x1b,0,0x23,0},
        {0x31,0,0x2f,0,0x0b,0,0xe6,0xff,0xf9,0xff,0x40,0,0x31,0},
        {1,0,0x0a,0,0x20,0,0xf2,0xff,0xf7,0xff,0x1f,0,2,0},
        {0xdc,0xff,0x27,0,0x2e,0,0xdc,0xff,0x27,0,0x2e,0,0xdd,0xff},
        {0xf9,0xff,7,0,0xf0,0xff,0xee,0xff,6,0,0,0,0xfa,0xff}};
    for(unsigned n=0;n<6;n++){
        Dsp1 *d=dsp1_create();dsp1_load_firmware(d,NULL);uint64_t clock=0;unsigned bank=n%3;
        put(d,&clock,1+16*bank);
        for(unsigned p=0;p<4;p++){put(d,&clock,(uint8_t)attitude[n][p]);put(d,&clock,(uint8_t)((uint16_t)attitude[n][p]>>8));}
        clock+=5000;dsp1_sync(d,clock);
        const unsigned commands[]={0xd,3,0xb};const int16_t vector[]={100,-80,60};unsigned index=0;
        for(unsigned c=0;c<3;c++){
            put(d,&clock,commands[c]+16*bank);
            for(unsigned p=0;p<3;p++){put(d,&clock,(uint8_t)vector[p]);put(d,&clock,(uint8_t)((uint16_t)vector[p]>>8));}
            clock+=5000;dsp1_sync(d,clock);
            for(unsigned p=0;p<(c==2?2:6);p++){
                uint8_t out=get(d,&clock);
                if(out!=attitude_expected[n][index])fprintf(stderr,"matrix %u byte %u got %02x expected %02x\n",n,index,out,attitude_expected[n][index]);
                CHECK(out==attitude_expected[n][index++]);
            }
        }
        CHECK(!dsp1_hle_failed(d));dsp1_destroy(d);
    }
    for(unsigned n=0;n<1024;n++){
        Dsp1 *d=dsp1_create();CHECK(d!=NULL);dsp1_load_firmware(d,NULL);
        CHECK(!dsp1_firmware_loaded(d) && dsp1_hle_active(d));
        int16_t a=(int16_t)(n*197+0x8000),b=(int16_t)(n*349+0x4000);uint64_t clock=100000;
        put(d,&clock,0);put(d,&clock,(uint8_t)a);put(d,&clock,(uint8_t)((uint16_t)a>>8));
        put(d,&clock,(uint8_t)b);put(d,&clock,(uint8_t)((uint16_t)b>>8));
        uint16_t value=get(d,&clock);value|=(uint16_t)get(d,&clock)<<8;
        CHECK(value==(uint16_t)(((int32_t)a*b)>>15));CHECK(!dsp1_hle_failed(d));dsp1_destroy(d);
    }
    Dsp1 *a=dsp1_create(),*b=dsp1_create();dsp1_load_firmware(a,NULL);dsp1_load_firmware(b,NULL);
    uint64_t c1=500000,c2;put(a,&c1,0);put(a,&c1,0x34); // mid-word host protocol
    Stream s={{transfer,NULL},0,false,{0}};dsp1_saveload(a,&s.stream);s.pos=0;s.load=true;dsp1_saveload(b,&s.stream);c2=c1;
    const uint8_t rest[]={0x12,0x00,0x40};for(unsigned n=0;n<3;n++){put(a,&c1,rest[n]);put(b,&c2,rest[n]);}
    CHECK(get(a,&c1)==get(b,&c2));CHECK(get(a,&c1)==get(b,&c2));
    dsp1_destroy(a);dsp1_destroy(b);
    a=dsp1_create();dsp1_load_firmware(a,NULL);c1=0;put(a,&c1,0x0a);put(a,&c1,0x30);put(a,&c1,0);
    for(unsigned n=0;n<8;n++)CHECK(get(a,&c1)==0);CHECK(!dsp1_hle_failed(a));dsp1_destroy(a);
    a=dsp1_create();dsp1_load_firmware(a,NULL);c1=0;put(a,&c1,0xff);put(a,&c1,0x40);
    CHECK(!dsp1_hle_failed(a));put(a,&c1,0x1f);
    CHECK(dsp1_hle_failed(a) && dsp1_hle_failed_command(a)==0x1f);dsp1_destroy(a);
}
static uint8_t rom[0x8000];
static Cx4 *start_cx4(void){
    Cx4 *c=cx4_create(rom,sizeof rom,NULL,0);CHECK(c!=NULL);CHECK(cx4_load_firmware(c,NULL));
    cx4_write(c,0x7f49,0);cx4_write(c,0x7f4a,0x80);cx4_write(c,0x7f4b,0);cx4_write(c,0x7f4f,0);return c;
}
static void cx(void){
    const uint16_t program[]={0x6403,0x8409,0xe060,0xfc00}; // LD A,3; ADD A,9; ST R0,A; HALT
    for(unsigned n=0;n<4;n++){rom[n*2]=(uint8_t)program[n];rom[n*2+1]=(uint8_t)(program[n]>>8);}
    Cx4 *a=start_cx4();cx4_sync(a,10000);CHECK(cx4_read(a,0x7f80)==12);
    CHECK(cx4_read(a,0x7f81)==0 && cx4_read(a,0x7f82)==0);CHECK(cx4_instructions_executed(a)==4);cx4_destroy(a);
    a=start_cx4();cx4_sync(a,100);CHECK(cx4_instructions_executed(a)<4);
    Stream s={{transfer,NULL},0,false,{0}};cx4_saveload(a,&s.stream);cx4_saveload_clock(a,&s.stream);
    Cx4 *b=cx4_create(rom,sizeof rom,NULL,0);cx4_load_firmware(b,NULL);
    s.pos=0;s.load=true;cx4_saveload(b,&s.stream);cx4_saveload_clock(b,&s.stream);
    cx4_sync(a,10000);cx4_sync(b,10000);
    for(unsigned n=0;n<48;n++)CHECK(cx4_read(a,0x7f80+n)==cx4_read(b,0x7f80+n));
    CHECK(cx4_read(b,0x7f80)==12);CHECK(!cx4_locked(a) && !cx4_locked(b));
    cx4_destroy(a);cx4_destroy(b);
}
static void cx_arithmetic_resume(void) {
    const uint16_t ops[]={0x8062,0x9062,0xa862,0xb062,0xb862,0xa062};
    for(unsigned seed=0;seed<128;seed++)for(unsigned op=0;op<6;op++) {
        uint32_t x=(seed*0x10203u+0x7fffa0u)&0xffffffu;
        uint32_t y=(seed*0x32111u+0x800080u)&0xffffffu;
        uint32_t expected=op==0?x+y:op==1?x-y:op==2?x^y:op==3?x&y:op==4?x|y:~(x^y);
        expected&=0xffffffu;
        uint16_t program[]={0x6061,ops[op],0xe060,0xfc00};
        for(unsigned n=0;n<4;n++){rom[2*n]=(uint8_t)program[n];rom[2*n+1]=(uint8_t)(program[n]>>8);}
        Cx4 *a=cx4_create(rom,sizeof rom,NULL,0);CHECK(a && cx4_load_firmware(a,NULL));
        for(unsigned n=0;n<3;n++){cx4_write(a,0x7f83+n,(uint8_t)(x>>(n*8)));cx4_write(a,0x7f86+n,(uint8_t)(y>>(n*8)));}
        cx4_write(a,0x7f49,0);cx4_write(a,0x7f4a,0x80);cx4_write(a,0x7f4b,0);cx4_write(a,0x7f4f,0);
        uint64_t anchor=100+seed%3*200;cx4_sync(a,anchor);
        Stream stream={{transfer,NULL},0,false,{0}};cx4_saveload(a,&stream.stream);cx4_saveload_clock(a,&stream.stream);
        Cx4 *b=cx4_create(rom,sizeof rom,NULL,0);CHECK(b && cx4_load_firmware(b,NULL));
        stream.pos=0;stream.load=true;cx4_saveload(b,&stream.stream);cx4_saveload_clock(b,&stream.stream);
        cx4_sync(a,10000);cx4_sync(b,10000);
        for(unsigned n=0;n<3;n++){CHECK(cx4_read(a,0x7f80+n)==(uint8_t)(expected>>(n*8)));CHECK(cx4_read(b,0x7f80+n)==cx4_read(a,0x7f80+n));}
        CHECK(cx4_instructions_executed(a)==4);CHECK(!cx4_locked(a) && !cx4_locked(b));
        cx4_destroy(a);cx4_destroy(b);
    }
}

static void maps(void){
    Cart cart={0};cart.type=CART_DSP1;cart.romImageSize=524288;
    for(unsigned bank=0;bank<256;bank++)for(unsigned adr=0;adr<65536;adr+=0x1000){
        bool want=(bank&127)>=32 && (bank&127)<64 && adr>=0x8000;
        CHECK(cart_is_dsp1_window(&cart,bank,adr)==want);
    }
    CHECK(cart_dsp1_register(&cart,0x8000)==0);CHECK(cart_dsp1_register(&cart,0xc000)==1);
    cart.romImageSize=0x200000;
    for(unsigned bank=0;bank<256;bank++)for(unsigned adr=0;adr<65536;adr+=0x1000) {
        CHECK(cart_is_dsp1_window(&cart,bank,adr)==((bank&127)<32 && adr>=0x6000 && adr<0x8000));
    }
    CHECK(cart_dsp1_register(&cart,0x6000)==0 && cart_dsp1_register(&cart,0x7000)==1);
    cart.type=CART_DSP1_HIROM;
    CHECK(cart_is_dsp1_window(&cart,0,0x6000));CHECK(!cart_is_dsp1_window(&cart,0x20,0x6000));
    CHECK(cart_is_dsp1_sram_window(&cart,0x20,0x6000));
}
int main(void){CHECK(rr16_init(true));maps();dsp();cx();cx_arithmetic_resume();rr16_shutdown();printf("{\"checks\":%u,\"passed\":true}\n",checks);return 0;}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main();}
