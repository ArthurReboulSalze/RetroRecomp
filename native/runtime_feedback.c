/* Small private recompilation hints, never a gameplay log or a memory dump.
 * All disk I/O, allocation, locking and merging happen at normal process exit.
 * The wire layout is fixed little-endian and independently validated in Python. */
#include "runtime_feedback.h"
#include "runtime_feedback_config.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <limits.h>

#define LIMIT 4096u
#define HEADER 96u
#define RECORD 32u
static uint8_t records[LIMIT][RECORD];
static uint16_t slots[LIMIT*2];
static unsigned count, dropped;
static int enabled, initial_enabled, started, finished, active;

static void put32(uint8_t *b, uint32_t v) {
    for(unsigned n=0;n<4;++n)b[n]=(uint8_t)(v>>(n*8));
}
static uint32_t get32(const uint8_t *b) {
    return (uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;
}
static uint32_t hash(const uint8_t *b, size_t z) {
    uint32_t h=2166136261u;
    for(size_t n=0;n<z;++n)h=(h^b[n])*16777619u;
    return h;
}
static int add(const uint8_t *r) {
    unsigned slot=hash(r,RECORD)&(LIMIT*2-1);
    while(slots[slot]) {
        if(!memcmp(records[slots[slot]-1],r,RECORD))return 0;
        slot=(slot+1)&(LIMIT*2-1);
    }
    if(count==LIMIT) { if(dropped<UINT_MAX)++dropped;return 0; }
    memcpy(records[count],r,RECORD);slots[slot]=(uint16_t)++count;return 1;
}
int rr_feedback_enabled(void) { return enabled; }
int rr_feedback_toggle(void) { if(active && !finished)enabled=!enabled;return enabled; }
const char *rr_feedback_label(void) { return enabled?"F12 Fallback recording: ON":"F12 Fallback recording: OFF"; }
int rr_feedback_pending(void) { return enabled && count!=0; }
void rr_feedback_note(unsigned kind,uint32_t pc,uint32_t aux,const uint8_t *b,unsigned z) {
    if(!enabled || !kind || kind>RR_FB_NG_Z80 || !b || !z || z>16)return;
    uint8_t r[RECORD]={0};r[0]=(uint8_t)kind;r[1]=(uint8_t)z;
    put32(r+4,pc);put32(r+8,aux);memcpy(r+12,b,z);add(r);
}
static int base_directory(wchar_t *path) {
    /* Read-only resolution, including Unicode and long renamed-game paths. */
    DWORD n=GetModuleFileNameW(NULL,path,32768);
    if(!n || n>=32000)return 0;
    wchar_t *slash=wcsrchr(path,L'\\');if(!slash)return 0;*slash=0;
    if(wcsncmp(path,L"\\\\?\\",4)) {
        size_t length=wcslen(path);
        if(path[0]==L'\\' && path[1]==L'\\') {
            memmove(path+8,path+2,(length-1)*sizeof(wchar_t));wmemcpy(path,L"\\\\?\\UNC\\",8);
        } else {
            memmove(path+4,path,(length+1)*sizeof(wchar_t));wmemcpy(path,L"\\\\?\\",4);
        }
    }
    wcscat(path,L"\\datas");
    return 1;
}
static int directory(wchar_t *path) {
    if(!base_directory(path))return 0;
    if(!CreateDirectoryW(path,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return 0;
    wcscat(path,L"\\fallbacks");
    return CreateDirectoryW(path,NULL) || GetLastError()==ERROR_ALREADY_EXISTS;
}
static void preference_key(wchar_t *key) {
    char raw[80];snprintf(raw,sizeof raw,"%s.%s",RR_FEEDBACK_SYSTEM,RR_FEEDBACK_IDENTITY);
    MultiByteToWideChar(CP_UTF8,0,raw,-1,key,80);
}
static void flush(void) {
    if(!enabled || !count)return; /* No fallback: no file, directory or lock. */
    wchar_t root[32768],path[32768],temporary[32768],mutex_name[128],suffix[100];
    if(!directory(root))return;
    char name[100];snprintf(name,sizeof name,"%s-%s.rrfb",RR_FEEDBACK_SYSTEM,RR_FEEDBACK_IDENTITY);
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name,-1,suffix,100))return;
    swprintf(path,32768,L"%ls\\%ls",root,suffix);
    swprintf(mutex_name,128,L"Local\\RetroRecompFeedback-%08x-%ls",hash((const uint8_t*)path,wcslen(path)*sizeof(wchar_t)),suffix);
    HANDLE mutex=CreateMutexW(NULL,FALSE,mutex_name);if(!mutex)return;
    DWORD wait=WaitForSingleObject(mutex,5000);
    if(wait!=WAIT_OBJECT_0 && wait!=WAIT_ABANDONED) { CloseHandle(mutex);return; }
    /* Incoming session first: even a saturated previous file can receive new
     * useful hints. Never let accumulated sessions exceed LIMIT records. */
    unsigned incoming=count;int changed=1;
    FILE *file=_wfopen(path,L"rb");
    if(file) {
        uint8_t header[HEADER];
        if(fread(header,1,HEADER,file)==HEADER && !memcmp(header,"RRFB001\0",8) &&
           get32(header+8)==1 && get32(header+12)<=LIMIT &&
           !memcmp(header+20,RR_FEEDBACK_SYSTEM,sizeof(RR_FEEDBACK_SYSTEM)) &&
           !memcmp(header+28,RR_FEEDBACK_IDENTITY,64)) {
            unsigned old_count=get32(header+12);size_t size=old_count*RECORD;
            uint8_t *old=(uint8_t*)malloc(size?size:1);
            if(old && fread(old,1,size,file)==size && fgetc(file)==EOF && hash(old,size)==get32(header+92)) {
                unsigned newly_added=0,matched=0;uint8_t matched_rows[LIMIT]={0};
                for(unsigned i=0;i<old_count;++i) {
                    const uint8_t *r=old+i*RECORD;
                    unsigned slot=hash(r,RECORD)&(LIMIT*2-1);
                    while(slots[slot]) {
                        unsigned index=slots[slot]-1;
                        if(!memcmp(records[index],r,RECORD)) {
                            if(index<incoming && !matched_rows[index]) {matched_rows[index]=1;++matched;}
                            break;
                        }
                        slot=(slot+1)&(LIMIT*2-1);
                    }
                }
                for(unsigned i=0;i<old_count;++i) newly_added+=(unsigned)add(old+i*RECORD);
                /* Do not rewrite an identical deduplicated set each session. */
                changed=(matched!=incoming) || incoming+newly_added!=old_count || dropped>get32(header+16);
                if(get32(header+16)>dropped)dropped=get32(header+16);
            }
            free(old);
        }
        fclose(file);
    }
    if(changed) {
        uint8_t header[HEADER]={0};memcpy(header,"RRFB001\0",8);put32(header+8,1);
        put32(header+12,count);put32(header+16,dropped);
        memcpy(header+20,RR_FEEDBACK_SYSTEM,sizeof(RR_FEEDBACK_SYSTEM));
        memcpy(header+28,RR_FEEDBACK_IDENTITY,64);put32(header+92,hash(&records[0][0],count*RECORD));
        swprintf(temporary,32768,L"%ls.%lu.tmp",path,GetCurrentProcessId());
        file=_wfopen(temporary,L"wb");int okay=0;
        if(file) {
            okay=fwrite(header,1,HEADER,file)==HEADER && fwrite(records,RECORD,count,file)==count;
            if(fflush(file))okay=0;
            if(fclose(file))okay=0;
        }
        if(okay)okay=MoveFileExW(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
        if(!okay)DeleteFileW(temporary);
    }
    ReleaseMutex(mutex);CloseHandle(mutex);
}
void rr_feedback_finish(void) {
    if(!active || finished)return;
    flush();
    /* F12 is an explicit preference change, saved only on shutdown too. A
     * read or an unchanged launch still creates no settings file/directory. */
    if(enabled!=initial_enabled) {
        wchar_t path[32768],key[80];
        if(base_directory(path) && (CreateDirectoryW(path,NULL) || GetLastError()==ERROR_ALREADY_EXISTS)) {
            wcscat(path,L"\\Retro-Recomp.ini");
            preference_key(key);
            WritePrivateProfileStringW(L"FallbackRecording",key,enabled?L"1":L"0",path);
        }
    }
    finished=1;enabled=0;
}
void rr_feedback_start(int gameplay) {
    if(started)return;started=1;
    const char *setting=getenv("RETRO_RECOMP_FEEDBACK");
    enabled=setting ? !strcmp(setting,"1") : gameplay!=0;
    active=gameplay || enabled;
    if(active && !setting) {
        wchar_t path[32768],key[80];
        if(base_directory(path)) {
            wcscat(path,L"\\Retro-Recomp.ini");
            preference_key(key);
            enabled=GetPrivateProfileIntW(L"FallbackRecording",key,1,path)!=0;
        }
    }
    initial_enabled=enabled;
    if(active && atexit(rr_feedback_finish)) {enabled=0;active=0;}
}
