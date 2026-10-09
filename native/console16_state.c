/* Lazy, atomic quick states bound to the exact cartridge and runtime ABI. */
#include <windows.h>
#include <io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console16_state.h"
#include "retro16_state_config.h"
#define HEADER_BYTES 160
#define MAX_STATE_BYTES (32u * 1024u * 1024u)
static const uint8_t magic[8] = {'R','R','1','6','S','T','1',0};
static void put32(uint8_t *p, uint32_t n) {
    for (int i=0; i<4; ++i) p[i]=(uint8_t)(n>>(8*i));
}
static uint32_t get32(const uint8_t *p) {
    uint32_t n=0; for (int i=0; i<4; ++i) n|=(uint32_t)p[i]<<(8*i); return n;
}
static uint64_t hash(const uint8_t *p, size_t n) {
    uint64_t h=14695981039346656037ull;
    for (size_t i=0; i<n; ++i) { h^=p[i]; h*=1099511628211ull; } return h;
}
bool rr16_state_path(wchar_t *path, size_t capacity) {
    if (capacity < 32768) return false;
    DWORD n=GetModuleFileNameW(NULL,path,32700);
    wchar_t *slash=n && n<32700 ? wcsrchr(path,L'\\') : NULL;
    if (!slash) { path[0]=0; return false; }
    slash[1]=0;
    wchar_t name[512];
    if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,RR16_STATE_NAME,-1,name,512)) return false;
    wchar_t tail[640];
    swprintf_s(tail,640,L"datas\\states\\%s-%.12hs.rrstate",name,RR16_STATE_ROM);
    return wcscat_s(path,capacity,tail)==0;
}
static bool write_atomic(const wchar_t *path, const uint8_t *payload, size_t size) {
    if (!path[0] || wcslen(path)>32000 || !size || size>MAX_STATE_BYTES) return false;
    uint8_t header[HEADER_BYTES]={0};
    memcpy(header,magic,8); put32(header+8,1); put32(header+12,RR16_STATE_SYSTEM);
    put32(header+16,RR16_STATE_PAL); put32(header+20,(uint32_t)size);
    uint64_t h=hash(payload,size); put32(header+24,(uint32_t)h); put32(header+28,(uint32_t)(h>>32));
    memcpy(header+32,RR16_STATE_ROM,64); memcpy(header+96,RR16_STATE_ABI,64);
    wchar_t parent[32768], staged[32768];
    wcscpy_s(parent,32768,path);
    for (wchar_t *p=parent+3; *p; ++p) if (*p==L'\\' || *p==L'/') {
        wchar_t separator=*p; *p=0;
        if (!CreateDirectoryW(parent,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS) return false;
        *p=separator;
    }
    swprintf_s(staged,32768,L"%s.%lu.tmp",path,GetCurrentProcessId());
    FILE *file=_wfopen(staged,L"wb"); if (!file) return false;
    bool ok=fwrite(header,1,sizeof header,file)==sizeof header && fwrite(payload,1,size,file)==size;
    if (ok) ok=fflush(file)==0 && _commit(_fileno(file))==0;
    if (fclose(file)!=0) ok=false;
    if (ok) ok=MoveFileExW(staged,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    if (!ok) DeleteFileW(staged); return ok;
}
bool rr16_state_file(const wchar_t *path, bool load) {
    if (!path || !path[0]) return false;
    if (!load) {
        size_t n=0; uint8_t *data=rr16_state_capture(&n);
        bool ok=data && write_atomic(path,data,n); free(data); return ok;
    }
    FILE *file=_wfopen(path,L"rb"); if (!file) return false;
    uint8_t header[HEADER_BYTES];
    bool valid=fread(header,1,sizeof header,file)==sizeof header &&
        !memcmp(header,magic,8) && get32(header+8)==1 &&
        get32(header+12)==RR16_STATE_SYSTEM && get32(header+16)==RR16_STATE_PAL &&
        !memcmp(header+32,RR16_STATE_ROM,64) && !memcmp(header+96,RR16_STATE_ABI,64);
    size_t n=valid ? get32(header+20) : 0;
    uint8_t *data=n && n<=MAX_STATE_BYTES ? (uint8_t *)malloc(n) : NULL;
    valid=data && fread(data,1,n,file)==n && fgetc(file)==EOF && !ferror(file);
    fclose(file);
    if (valid) valid=hash(data,n)==((uint64_t)get32(header+28)<<32 | get32(header+24));
    bool ok=false;
    if (valid) {
        size_t backup_size=0; uint8_t *backup=rr16_state_capture(&backup_size);
        if (backup) {
            ok=rr16_state_restore(data,n);
            if (!ok) rr16_state_restore(backup,backup_size);
        }
        free(backup);
    }
    free(data); return ok;
}
