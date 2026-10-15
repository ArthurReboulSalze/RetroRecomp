/* Lazy MVS NVRAM/card persistence. Fixed data layout, no CPU/ROM/BIOS bytes.
 * Identity includes exact prepared cartridge, selected BIOS and system/region.
 * Deliberately independent of the quick-state runtime ABI. Original work: MIT. */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#ifndef _WIN32
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#endif
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
    char tail[128];wchar_t wide_tail[128];
    snprintf(tail,sizeof(tail),RR_SLASH "datas" RR_SLASH "saves" RR_SLASH "NeoGeo-%.64s.rrsave",RR16_STATE_ROM);
    return rr_executable_directory(path,capacity) && rr_from_utf8(tail,wide_tail,128) && rr_wide_append(path,capacity,wide_tail)==0;
}
/* 1 valid, 0 missing, -1 malformed/unreadable. Never mutate machine on failure. */
static int read_saved(uint8_t *data,uint64_t *checksum) {
    FILE *file=rr_fopen(save_path,L"rb");
    if(!file)return errno==ENOENT?0:-1;
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
#ifdef _WIN32
typedef HANDLE RRSaveLock;
static RRSaveLock lock_save(void) {
    wchar_t name[128];swprintf(name,128,L"Local\\Retro-Recomp-NeoGeo-%.64hs",RR16_STATE_ROM);
    RRSaveLock mutex=CreateMutexW(NULL,FALSE,name);if(!mutex)return NULL;
    DWORD wait=WaitForSingleObject(mutex,5000);
    if(wait!=WAIT_OBJECT_0 && wait!=WAIT_ABANDONED) {CloseHandle(mutex);return NULL;}
    return mutex;
}
static void unlock_save(RRSaveLock mutex) {ReleaseMutex(mutex);CloseHandle(mutex);}
#else

typedef int RRSaveLock;
static RRSaveLock lock_save(void) {
    char name[256];snprintf(name,sizeof(name),"/tmp/retro-recomp-ng-%lu-%.64s.lock",(unsigned long)getuid(),RR16_STATE_ROM);
    int fd=open(name,O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return 0;
    struct stat st;if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=getuid() || st.st_nlink!=1){close(fd);return 0;}
    struct timespec delay={0,10000000};
    for(unsigned retry=0;retry<500;++retry) {
        if(!flock(fd,LOCK_EX|LOCK_NB))return fd+1;
        if(errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)break;
        nanosleep(&delay,NULL);
    }
    close(fd);return 0;
}
static void unlock_save(RRSaveLock lock){int fd=lock-1;flock(fd,LOCK_UN);close(fd);}
#endif

bool rr_ng_persist_begin(bool use) {
    enabled=use;armed=loaded=saved=blocked=has_file=false;disk_hash=0;capture(baseline);
    initial_nvram_hash=hash(ngsys.nvram,NVRAM_BYTES);initial_card_hash=hash(ngsys.memcard,CARD_BYTES);
    if(!enabled)return true;
    if(!rr_ng_persist_path(save_path,32768)) {blocked=true;return false;}
    RRSaveLock mutex=lock_save();if(!mutex) {blocked=true;return false;}
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
    wchar_t parent[32768],temporary[32768];rr_wide_copy(parent,32768,save_path);
    for(wchar_t *p=parent+3;*p;++p)if(*p==L'\\' || *p==L'/') {
        wchar_t separator=*p;*p=0;
        if(!rr_mkdir(parent))return false;
        *p=separator;
    }
    swprintf(temporary,32768,L"%ls.%lu.tmp",save_path,rr_process_id());
    FILE *file=rr_fopen(temporary,L"wb");if(!file)return false;
    bool okay=fwrite(header,1,HEADER,file)==HEADER && fwrite(data,1,PAYLOAD,file)==PAYLOAD;
    if(okay)okay=rr_flush_file(file);
    if(fclose(file))okay=false;
    if(okay)okay=rr_replace(temporary,save_path);
    if(!okay)rr_remove(temporary);return okay;
}
bool rr_ng_persist_close(void) {
    if(!enabled)return true;
    if(blocked)return false;
    if(!armed || (!memcmp(baseline,ngsys.nvram,NVRAM_BYTES) &&
                  !memcmp(baseline+NVRAM_BYTES,ngsys.memcard,CARD_BYTES)))return true;
    RRSaveLock mutex=lock_save();if(!mutex)return false;
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
