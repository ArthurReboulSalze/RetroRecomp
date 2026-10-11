/* Lazy battery files survive rebuilds; quick states separately pin runtime ABI. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <io.h>
#include "md_battery.h"
#include "retro16_state_config.h"
#define HEADER_BYTES 112
static const uint8_t magic[8]={'R','R','M','D','R','A','1',0};
static uint8_t saved[0x10000], observed[0x10000];
static wchar_t save_path[32768];
static bool active, pending;
static uint64_t last_check, last_changed, retry_at;
static void put32(uint8_t *p, uint32_t n) {
    for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(n>>(i*8));
}
static uint32_t get32(const uint8_t *p) {
    uint32_t n=0; for (unsigned i=0;i<4;++i) n|=(uint32_t)p[i]<<(i*8); return n;
}
static uint64_t hash(const uint8_t *p, size_t n) {
    uint64_t h=14695981039346656037ull;
    for (size_t i=0;i<n;++i) { h^=p[i]; h*=1099511628211ull; } return h;
}
bool rr_md_battery_path(wchar_t *path, size_t capacity) {
    if (capacity<32768) return false;
    DWORD n=GetModuleFileNameW(NULL,path,32700);
    wchar_t *slash=n && n<32700 ? wcsrchr(path,L'\\') : NULL;
    if (!slash) { path[0]=0; return false; }
    slash[1]=0;
    wchar_t name[512],tail[640];
    if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,RR16_STATE_NAME,-1,name,512)) return false;
    swprintf_s(tail,640,L"datas\\saves\\%s-%.12hs.rrsram",name,RR16_STATE_ROM);
    return wcscat_s(path,capacity,tail)==0;
}
bool rr_md_battery_open(GenesisBus *bus, const wchar_t *path) {
    active=pending=false; last_check=last_changed=retry_at=0; save_path[0]=0;
    if (!path || !bus->sram_present || !bus->sram_battery) return true;
    if (!bus->sram_size || bus->sram_size>sizeof saved || !path[0] || wcslen(path)>32000) return false;
    wcscpy_s(save_path,32768,path);
    FILE *file=_wfopen(path,L"rb");
    if (!file && errno!=ENOENT) return false;
    if (file) {
        uint8_t header[HEADER_BYTES];
        uint8_t *payload=malloc(bus->sram_size);
        bool valid=payload && fread(header,1,sizeof header,file)==sizeof header &&
            !memcmp(header,magic,8) && get32(header+8)==1 && get32(header+12)==bus->sram_size &&
            get32(header+16)==bus->sram_base && get32(header+20)==bus->sram_end &&
            get32(header+24)==bus->sram_stride && !memcmp(header+40,RR16_STATE_ROM,64) &&
            fread(payload,1,bus->sram_size,file)==bus->sram_size && fgetc(file)==EOF && !ferror(file);
        if (valid) valid=hash(payload,bus->sram_size)==((uint64_t)get32(header+36)<<32|get32(header+32));
        if (fclose(file)!=0) valid=false;
        if (valid) memcpy(bus->sram,payload,bus->sram_size);
        free(payload);
        /* Never replace a damaged/wrong-cartridge file with blank progress. */
        if (!valid) return false;
    }
    memcpy(saved,bus->sram,bus->sram_size); memcpy(observed,saved,bus->sram_size);
    active=true; return true;
}
static bool write_atomic(const GenesisBus *bus) {
    uint8_t header[HEADER_BYTES]={0};
    memcpy(header,magic,8); put32(header+8,1); put32(header+12,bus->sram_size);
    put32(header+16,bus->sram_base); put32(header+20,bus->sram_end); put32(header+24,bus->sram_stride);
    uint64_t h=hash(bus->sram,bus->sram_size); put32(header+32,(uint32_t)h); put32(header+36,(uint32_t)(h>>32));
    memcpy(header+40,RR16_STATE_ROM,64);
    wchar_t parent[32768],staged[32768]; wcscpy_s(parent,32768,save_path);
    for (wchar_t *p=parent+3;*p;++p) if (*p==L'\\' || *p==L'/') {
        wchar_t separator=*p; *p=0;
        if (!CreateDirectoryW(parent,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS) return false;
        *p=separator;
    }
    swprintf_s(staged,32768,L"%s.%lu.tmp",save_path,GetCurrentProcessId());
    FILE *file=_wfopen(staged,L"wb"); if (!file) return false;
    bool ok=fwrite(header,1,sizeof header,file)==sizeof header && fwrite(bus->sram,1,bus->sram_size,file)==bus->sram_size;
    if (ok) ok=fflush(file)==0 && _commit(_fileno(file))==0;
    if (fclose(file)!=0) ok=false;
    if (ok) ok=MoveFileExW(staged,save_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    if (!ok) DeleteFileW(staged);
    return ok;
}
bool rr_md_battery_flush(const GenesisBus *bus, uint64_t now_ms, bool force) {
    if (!active) return true;
    if (!bus->sram_present || !bus->sram_battery || !bus->sram_size || bus->sram_size>sizeof saved) return false;
    if (!force && (now_ms-last_check<500 || now_ms<retry_at)) return true;
    last_check=now_ms;
    if (memcmp(observed,bus->sram,bus->sram_size)) {
        memcpy(observed,bus->sram,bus->sram_size); last_changed=now_ms;
    }
    pending=memcmp(saved,bus->sram,bus->sram_size)!=0;
    if (!pending || (!force && now_ms-last_changed<2000)) return true;
    if (!write_atomic(bus)) { retry_at=now_ms+10000; return false; }
    memcpy(saved,bus->sram,bus->sram_size); pending=false; retry_at=0; return true;
}
