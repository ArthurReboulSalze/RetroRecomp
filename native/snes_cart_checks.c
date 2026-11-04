/* Original cartridge decoding and lazy/transactional battery assertions. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "snes/snes.h"
#include "snes_native_steps.h"
#include "snes_battery.h"
#include "common_rtl.h"
#include "cpu_state.h"
extern Snes *g_snes;
extern uint8_t g_ram[0x20000];
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)){fprintf(stderr,"check failed: %s at %d\n",#x,__LINE__);exit(1);} } while(0)
static uint8_t ram[0x20000];
static int expected(unsigned type,unsigned romsize,unsigned ramsize,unsigned bank,unsigned adr) {
    if(bank==126 || bank==127) return -1;
    if(type==CART_LOROM && ((bank>=112 && bank<=125) || bank>=240) &&
            (adr<32768 || (romsize<=2097152 && ramsize<=32768)))
        return ((bank%16)*32768 + adr%32768)%ramsize;
    if(type==CART_HIROM && ((bank>=32 && bank<=63) || (bank>=160 && bank<=191)) && adr>=24576 && adr<32768)
        return ((bank%32)*8192 + adr%8192)%ramsize;
    return -1;
}
static void mapping(Cart *cart) {
    const unsigned addresses[]={0,0x1fff,0x2000,0x5fff,0x6000,0x7ffc,0x7fff,0x8000,0xfffc,0xffff};
    const unsigned sizes[]={2048,32768,131072};
    for(unsigned map=1;map<=2;map++)for(unsigned large=0;large<2;large++)for(unsigned size=0;size<3;size++){
        cart->type=map;cart->romImageSize=large?4194304:1048576;cart->ramSize=sizes[size];
        for(unsigned bank=0;bank<256;bank++)for(unsigned a=0;a<10;a++) {
            unsigned adr=addresses[a];int off=expected(map,cart->romImageSize,cart->ramSize,bank,adr);
            memset(ram,0x39,sizeof ram);
            cart_write(cart,(uint8_t)bank,(uint16_t)adr,0xa6);
            if(off>=0){
                CHECK(ram[off]==0xa6);CHECK(cart_read(cart,bank,adr)==0xa6);
                cpu_write8(&g_cpu,bank,adr,0x75);CHECK(ram[off]==0x75);
                CHECK(cpu_read8(&g_cpu,bank,adr)==0x75);
            }
            else {for(unsigned i=0;i<cart->ramSize;i++)if(ram[i]!=0x39){CHECK(false);}}
            uint8_t code[4];bool wanted=true;
            for(unsigned n=0;n<4;n++)if(expected(map,cart->romImageSize,cart->ramSize,bank,(adr+n)&0xffff)<0 &&
                    !(bank==126 || bank==127 || ((bank&127)<64 && ((adr+n)&0xffff)<8192)))wanted=false;
            CHECK(rr_snes_read_ram_code((bank<<16)|adr,code)==wanted);
        }
    }
}
/* The ROM pointer of every bank and address in the LoROM and HiROM views, for sizes the remainder is a mask for (powers of two)
 * and for sizes it is not (3 MiB, 5 MiB): the pointer is the one the plain remainder gives. */
static void rom_pointer(Cart *cart) {
    const unsigned sizes[]={65536,262144,1048576,3145728,4194304,5242880,8388608};
    const unsigned addresses[]={0,1,0x1fff,0x5fff,0x6000,0x7fff,0x8000,0x8001,0xbfff,0xc000,0xfffe,0xffff};
    unsigned old_size=cart->romSize,old_ram=cart->ramSize;
    uintptr_t base=(uintptr_t)cart->rom;
    cart->ramSize=0;
    for(unsigned map=1;map<=2;map++)for(unsigned s=0;s<sizeof sizes/sizeof *sizes;s++){
        cart->type=map;cart->romSize=sizes[s];cart->romImageSize=sizes[s]>4194304?sizes[s]:4194304;
        for(unsigned bank=0;bank<256;bank++)for(unsigned a=0;a<sizeof addresses/sizeof *addresses;a++){
            unsigned adr=addresses[a],canonical=bank&0x7f;uint8_t *got=cart_getRomPtr(cart,(uint8_t)bank,(uint16_t)adr);
            if(bank==126||bank==127||(adr<0x8000&&canonical<0x40)){CHECK(got==NULL);continue;}
            unsigned off=map==1?((canonical<<15)|(adr&0x7fff)):(((canonical&0x3f)<<16)|adr);
            if(map==2&&sizes[s]>4194304&&!(bank&0x80))off+=0x400000;
            CHECK((uintptr_t)got==base+off%sizes[s]);
        }
    }
    cart->romSize=old_size;cart->ramSize=old_ram;
}
static unsigned file_read(const wchar_t *path,uint8_t *out,unsigned capacity) {
    FILE *f=_wfopen(path,L"rb");CHECK(f!=NULL);unsigned n=(unsigned)fread(out,1,capacity,f);CHECK(!ferror(f));CHECK(!fclose(f));return n;
}
static void file_write(const wchar_t *path,const uint8_t *data,unsigned n) {
    FILE *f=_wfopen(path,L"wb");CHECK(f!=NULL);CHECK(fwrite(data,1,n,f)==n);CHECK(!fclose(f));
}
static void battery(Cart *cart,const wchar_t *root) {
    wchar_t path[32768],bad[32768];swprintf_s(path,32768,L"%s\\sauvegarde élève\\progress.rrsram",root);
    swprintf_s(bad,32768,L"%s\\bad.rrsram",root);
    cart->type=CART_LOROM;cart->ramSize=8192;memset(ram,0,8192);
    CHECK(rr_snes_battery_open(cart,true,path));CHECK(rr_snes_battery_flush(cart,0,true));
    CHECK(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES);
    ram[8191]=0x7b;
    CHECK(rr_snes_battery_flush(cart,500,false));CHECK(rr_snes_battery_flush(cart,2499,false));
    CHECK(GetFileAttributesW(path)==INVALID_FILE_ATTRIBUTES);
    CHECK(rr_snes_battery_flush(cart,3000,false));CHECK(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES);
    uint8_t original[8400],changed[8400],again[8400];unsigned n=file_read(path,original,sizeof original);
    CHECK(n==112+8192);memset(ram,0,8192);CHECK(rr_snes_battery_open(cart,true,path));CHECK(ram[8191]==0x7b);
    /* A damaged file never blocks the game and is never lost: it is set aside byte for byte and a new save starts beside it. */
    wchar_t aside[32768+16];swprintf_s(aside,32768+16,L"%s.unusable-1",bad);
    for(unsigned off=0;off<n;off+=97){
        DeleteFileW(bad);DeleteFileW(aside);
        memcpy(changed,original,n);changed[off]^=0x40;file_write(bad,changed,n);memset(ram,0x5a,8192);
        CHECK(rr_snes_battery_open(cart,true,bad));CHECK(rr_snes_battery_notice()==1);CHECK(ram[0]==0x5a && ram[8191]==0x5a);
        CHECK(GetFileAttributesW(bad)==INVALID_FILE_ATTRIBUTES);
        CHECK(file_read(aside,again,sizeof again)==n);CHECK(!memcmp(changed,again,n));
        ram[0]=0xaa;CHECK(rr_snes_battery_flush(cart,9000,true));
        CHECK(file_read(bad,again,sizeof again)==n);CHECK(again[112]==0xaa);
        CHECK(file_read(aside,again,sizeof again)==n);CHECK(!memcmp(changed,again,n));
    }
    DeleteFileW(bad);DeleteFileW(aside);
    file_write(bad,original,n-1);CHECK(rr_snes_battery_open(cart,true,bad));CHECK(rr_snes_battery_notice()==1);
    memcpy(changed,original,n);changed[n]=1;file_write(bad,changed,n+1);CHECK(rr_snes_battery_open(cart,true,bad));CHECK(rr_snes_battery_notice()==1);
    /* All 99 names taken: nothing is replaced, the file stays where it is, nothing is saved this session (notice 2). */
    DeleteFileW(bad);
    for(unsigned k=1;k<=99;k++){
        wchar_t taken[32768+16];swprintf_s(taken,32768+16,L"%s.unusable-%u",bad,k);
        uint8_t mark[1]={(uint8_t)k};file_write(taken,mark,1);
    }
    memcpy(changed,original,n);changed[0]^=0x40;file_write(bad,changed,n);
    CHECK(!rr_snes_battery_open(cart,true,bad));CHECK(rr_snes_battery_notice()==2);
    CHECK(file_read(bad,again,sizeof again)==n);CHECK(!memcmp(changed,again,n));
    for(unsigned k=1;k<=99;k++){
        wchar_t taken[32768+16];swprintf_s(taken,32768+16,L"%s.unusable-%u",bad,k);
        CHECK(file_read(taken,again,sizeof again)==1);CHECK(again[0]==(uint8_t)k);DeleteFileW(taken);
    }
    DeleteFileW(bad);
    /* A good save of another mapping is a foreign file: set aside too (a copy here, the real save stays for the next check). */
    file_write(bad,original,n);cart->type=CART_HIROM;
    CHECK(rr_snes_battery_open(cart,true,bad));CHECK(rr_snes_battery_notice()==1);cart->type=CART_LOROM;
    CHECK(file_read(aside,again,sizeof again)==n);CHECK(!memcmp(original,again,n));
    DeleteFileW(bad);DeleteFileW(aside);
    CHECK(rr_snes_battery_open(cart,true,path));ram[0]=3;CHECK(rr_snes_battery_flush(cart,9000,true));
    CHECK(rr_snes_battery_open(cart,true,path));CHECK(ram[0]==3 && ram[8191]==0x7b);
    /* No battery means no output, even when RAM changes. */
    wchar_t volatile_path[32768];swprintf_s(volatile_path,32768,L"%s\\volatile\\never.rrsram",root);
    CHECK(rr_snes_battery_open(cart,false,volatile_path));ram[0]^=1;CHECK(rr_snes_battery_flush(cart,10000,true));
    CHECK(GetFileAttributesW(volatile_path)==INVALID_FILE_ATTRIBUTES);
    CHECK(rr_snes_battery_open(cart,true,NULL));
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    wchar_t folder[32768];CHECK(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,argv[1],-1,folder,32768));
    CHECK(rr16_init(true));Cart *cart=g_snes->cart;
    uint8_t *old_ram=cart->ram;unsigned old_size=cart->ramSize,old_type=cart->type,old_image=cart->romImageSize;
    uint8_t *old_sram=g_sram;int old_sram_size=g_sram_size;g_sram=ram;g_sram_size=sizeof ram;
    cart->ram=ram;mapping(cart);battery(cart,folder);
    rom_pointer(cart);
    g_sram=old_sram;g_sram_size=old_sram_size;
    cart->ram=old_ram;cart->ramSize=old_size;cart->type=old_type;cart->romImageSize=old_image;
    for(unsigned n=0;n<RR_SN_RAM_VARIANT_LIMIT;n++) {
        unsigned pc=n*4;memcpy(g_ram+pc,"\xa9\x34\x12\xea",4);
        rr16_snes_observe_fallback(0x7e0000+pc);
        rr16_snes_observe_fallback(0x7e0000+pc); /* duplicates must consume no slot */
    }
    memcpy(g_ram+0x10000,"\xa9\x34\x12\xea",4);
    rr16_snes_observe_fallback(0x7f0000);rr16_snes_observe_fallback(0x7f0000);
    wchar_t report_path[32768];swprintf_s(report_path,32768,L"%s\\observations.json",folder);
    FILE *report=_wfopen(report_path,L"wb");CHECK(report!=NULL);fputs("{\"checks\":0",report);
    rr16_report_details(report);fputs("}",report);CHECK(!fclose(report));
    rr16_shutdown();printf("{\"checks\":%u,\"passed\":true}\n",checks);return 0;
}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main(__argc,__argv);}
