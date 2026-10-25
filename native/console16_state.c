/* Lazy, atomic quick states bound to the exact cartridge and runtime ABI. */
#include "platform_io.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console16_state.h"
#include "retro16_state_config.h"
#if RR16_NG
#include "neogeo_persistence.h"
#endif
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
static bool compatible_abi(const uint8_t *value) {
    if (!memcmp(value,RR16_STATE_ABI,64)) return true;
#ifdef RR16_STATE_COMPAT_ABI_21
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_21,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_22
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_22,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_23
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_23,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_20
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_20,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI
    if (!memcmp(value,RR16_STATE_COMPAT_ABI,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_2
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_2,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_3
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_3,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_4
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_4,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_5
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_5,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_6
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_6,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_7
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_7,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_8
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_8,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_9
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_9,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_10
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_10,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_11
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_11,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_12
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_12,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_13
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_13,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_14
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_14,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_15
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_15,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_16
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_16,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_17
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_17,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_18
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_18,64)) return true;
#endif
#ifdef RR16_STATE_COMPAT_ABI_19
    if (!memcmp(value,RR16_STATE_COMPAT_ABI_19,64)) return true;
#endif
    return false;
}
bool rr16_state_path(wchar_t *path, size_t capacity) {
    return rr_game_data_file(path,capacity,"states",RR16_STATE_NAME,RR16_STATE_ROM,".rrstate");
}
static bool write_atomic(const wchar_t *path, const uint8_t *payload, size_t size) {
    if (!path[0] || wcslen(path)>32000 || !size || size>MAX_STATE_BYTES) return false;
    uint8_t header[HEADER_BYTES]={0};
    memcpy(header,magic,8); put32(header+8,1); put32(header+12,RR16_STATE_SYSTEM);
    put32(header+16,RR16_STATE_PAL); put32(header+20,(uint32_t)size);
    uint64_t h=hash(payload,size); put32(header+24,(uint32_t)h); put32(header+28,(uint32_t)(h>>32));
    memcpy(header+32,RR16_STATE_ROM,64); memcpy(header+96,RR16_STATE_ABI,64);
    wchar_t parent[32768], staged[32768];
    rr_wide_copy(parent,32768,path);
    for (wchar_t *p=parent+3; *p; ++p) if (*p==L'\\' || *p==L'/') {
        wchar_t separator=*p; *p=0;
        if (!rr_mkdir(parent)) return false;
        *p=separator;
    }
    swprintf(staged,32768,L"%ls.%lu.tmp",path,rr_process_id());
    FILE *file=rr_fopen(staged,L"wb"); if (!file) return false;
    bool ok=fwrite(header,1,sizeof header,file)==sizeof header && fwrite(payload,1,size,file)==size;
    if (ok) ok=rr_flush_file(file);
    if (fclose(file)!=0) ok=false;
    if (ok) ok=rr_replace(staged,path);
    if (!ok) rr_remove(staged); return ok;
}
bool rr16_state_file(const wchar_t *path, bool load) {
    if (!path || !path[0]) return false;
    if (!load) {
        size_t n=0; uint8_t *data=rr16_state_capture(&n);
        bool ok=data && write_atomic(path,data,n); free(data); return ok;
    }
    FILE *file=rr_fopen(path,L"rb"); if (!file) return false;
    uint8_t header[HEADER_BYTES];
    bool valid=fread(header,1,sizeof header,file)==sizeof header &&
        !memcmp(header,magic,8) && get32(header+8)==1 &&
        get32(header+12)==RR16_STATE_SYSTEM && get32(header+16)==RR16_STATE_PAL &&
        !memcmp(header+32,RR16_STATE_ROM,64) && compatible_abi(header+96);
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
    free(data);
#if RR16_NG
    if(ok)rr_ng_persist_after_state();
#endif
    return ok;
}
