/* Lazy MVS NVRAM/card persistence. Fixed data layout, no CPU/ROM/BIOS bytes.
 * Identity includes exact prepared cartridge, selected BIOS and system/region.
 * Deliberately independent of the quick-state runtime ABI. Original work: MIT. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <io.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "geo.h"
#include "retro16_state_config.h"
#include "neogeo_persistence.h"
enum { HEADER=128, NVRAM_BYTES=65536, CARD_BYTES=2048, PAYLOAD=NVRAM_BYTES+CARD_BYTES };
static uint8_t baseline[PAYLOAD];
static bool enabled,armed,loaded,saved,blocked,has_file;
static uint64_t disk_hash;
static uint64_t initial_nvram_hash,initial_card_hash;
static wchar_t save_path[32768];
static const uint8_t magic[8]={'R','R','N','V','S','0','0','1'};
static void put32(uint8_t *p,uint32_t v) {for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(8*n));}
static uint32_t get32(const uint8_t *p) {uint32_t v=0;for(unsigned n=0;n<4;++n)v|=(uint32_t)p[n]<<(8*n);return v;}
static uint64_t hash(const uint8_t *p,size_t n) {
    uint64_t h=14695981039346656037ull;for(size_t i=0;i<n;++i)h=(h^p[i])*1099511628211ull;return h;
}
static void capture(uint8_t *data) {memcpy(data,ngsys.nvram,NVRAM_BYTES);memcpy(data+NVRAM_BYTES,ngsys.memcard,CARD_BYTES);}
bool rr_ng_persist_path(wchar_t *path,size_t capacity) {
    if(!path || capacity<32768)return false;
    DWORD n=GetModuleFileNameW(NULL,path,32700);
    wchar_t *slash=n && n<32700?wcsrchr(path,L'\\'):NULL;if(!slash)return false;
    slash[1]=0;wchar_t tail[128];swprintf_s(tail,128,L"datas\\saves\\NeoGeo-%.64hs.rrsave",RR16_STATE_ROM);
    return wcscat_s(path,capacity,tail)==0;
}
/* 1 valid, 0 missing, -1 malformed/unreadable. Never mutate machine on failure. */
static int read_saved(uint8_t *data,uint64_t *checksum) {
    FILE *file=_wfopen(save_path,L"rb");
    if(!file) {DWORD attr=GetFileAttributesW(save_path);return attr==INVALID_FILE_ATTRIBUTES &&
        (GetLastError()==ERROR_FILE_NOT_FOUND || GetLastError()==ERROR_PATH_NOT_FOUND)?0:-1;}
    uint8_t header[HEADER];bool valid=fread(header,1,HEADER,file)==HEADER;
    if(valid)valid=!memcmp(header,magic,8) && get32(header+8)==1 && get32(header+12)==3 &&
        get32(header+16)==PAYLOAD && !get32(header+20) && !memcmp(header+32,RR16_STATE_ROM,64) &&
        get32(header+96)==NVRAM_BYTES && get32(header+100)==CARD_BYTES;
    if(valid)for(unsigned n=104;n<HEADER;++n)if(header[n])valid=false;
    if(valid)valid=fread(data,1,PAYLOAD,file)==PAYLOAD && fgetc(file)==EOF && !ferror(file);
    fclose(file);
    if(valid) {
        *checksum=hash(data,PAYLOAD);
        valid=*checksum==((uint64_t)get32(header+28)<<32|get32(header+24));
    }
    return valid?1:-1;
}
static HANDLE lock_save(void) {
    wchar_t name[128];swprintf_s(name,128,L"Local\\Retro-Recomp-NeoGeo-%.64hs",RR16_STATE_ROM);
    HANDLE mutex=CreateMutexW(NULL,FALSE,name);if(!mutex)return NULL;
    DWORD wait=WaitForSingleObject(mutex,5000);
    if(wait!=WAIT_OBJECT_0 && wait!=WAIT_ABANDONED) {CloseHandle(mutex);return NULL;}
    return mutex;
}
static void unlock_save(HANDLE mutex) {ReleaseMutex(mutex);CloseHandle(mutex);}
bool rr_ng_persist_begin(bool use) {
    enabled=use;armed=loaded=saved=blocked=has_file=false;disk_hash=0;capture(baseline);
    initial_nvram_hash=hash(ngsys.nvram,NVRAM_BYTES);initial_card_hash=hash(ngsys.memcard,CARD_BYTES);
    if(!enabled)return true;
    if(!rr_ng_persist_path(save_path,32768)) {blocked=true;return false;}
    HANDLE mutex=lock_save();if(!mutex) {blocked=true;return false;}
    uint8_t *data=malloc(PAYLOAD);uint64_t checksum=0;
    int result=data?read_saved(data,&checksum):-1;
    if(result==1) {
        memcpy(ngsys.nvram,data,NVRAM_BYTES);memcpy(ngsys.memcard,data+NVRAM_BYTES,CARD_BYTES);
        memcpy(baseline,data,PAYLOAD);disk_hash=checksum;loaded=has_file=true;
        initial_nvram_hash=hash(ngsys.nvram,NVRAM_BYTES);initial_card_hash=hash(ngsys.memcard,CARD_BYTES);
    }
    free(data);unlock_save(mutex);blocked=result<0;return !blocked;
}
void rr_ng_persist_activity(bool active) {
    if(!enabled || blocked || armed)return;
    if(active) {if(!loaded)capture(baseline);armed=true;}
    else if(!loaded)capture(baseline); /* Ignore first-boot initialization until actual game input. */
}
void rr_ng_persist_after_state(void) {if(enabled && !blocked)armed=true;}
static bool write_atomic(const uint8_t *data) {
    uint8_t header[HEADER]={0};memcpy(header,magic,8);put32(header+8,1);put32(header+12,3);
    put32(header+16,PAYLOAD);uint64_t checksum=hash(data,PAYLOAD);
    put32(header+24,(uint32_t)checksum);put32(header+28,(uint32_t)(checksum>>32));
    memcpy(header+32,RR16_STATE_ROM,64);put32(header+96,NVRAM_BYTES);put32(header+100,CARD_BYTES);
    wchar_t parent[32768],temporary[32768];wcscpy_s(parent,32768,save_path);
    for(wchar_t *p=parent+3;*p;++p)if(*p==L'\\' || *p==L'/') {
        wchar_t separator=*p;*p=0;
        if(!CreateDirectoryW(parent,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return false;
        *p=separator;
    }
    swprintf_s(temporary,32768,L"%s.%lu.tmp",save_path,GetCurrentProcessId());
    FILE *file=_wfopen(temporary,L"wb");if(!file)return false;
    bool okay=fwrite(header,1,HEADER,file)==HEADER && fwrite(data,1,PAYLOAD,file)==PAYLOAD;
    if(okay)okay=fflush(file)==0 && _commit(_fileno(file))==0;
    if(fclose(file))okay=false;
    if(okay)okay=MoveFileExW(temporary,save_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    if(!okay)DeleteFileW(temporary);return okay;
}
bool rr_ng_persist_close(void) {
    if(!enabled)return true;
    if(blocked)return false;
    if(!armed || (!memcmp(baseline,ngsys.nvram,NVRAM_BYTES) &&
                  !memcmp(baseline+NVRAM_BYTES,ngsys.memcard,CARD_BYTES)))return true;
    HANDLE mutex=lock_save();if(!mutex)return false;
    uint8_t *current=malloc(PAYLOAD),*previous=malloc(PAYLOAD);uint64_t checksum=0;
    int result=previous?read_saved(previous,&checksum):-1;
    /* A second running copy must not silently overwrite another session's save. */
    bool okay=current && ((has_file && result==1 && checksum==disk_hash) || (!has_file && result==0));
    if(okay) {capture(current);okay=write_atomic(current);}
    if(okay) {saved=has_file=true;disk_hash=hash(current,PAYLOAD);memcpy(baseline,current,PAYLOAD);}
    free(current);free(previous);unlock_save(mutex);return okay;
}
void rr_ng_persist_report(FILE *file) {
    fprintf(file,",\"persistent_memory\":{\"enabled\":%s,\"loaded\":%s,\"saved\":%s,\"blocked\":%s,"
        "\"nvram_hash\":\"%016llx\",\"card_hash\":\"%016llx\","
        "\"initial_nvram_hash\":\"%016llx\",\"initial_card_hash\":\"%016llx\",\"file_bytes\":%u}",
        enabled?"true":"false",loaded?"true":"false",saved?"true":"false",blocked?"true":"false",
        hash(ngsys.nvram,NVRAM_BYTES),hash(ngsys.memcard,CARD_BYTES),initial_nvram_hash,initial_card_hash,HEADER+PAYLOAD);
}
