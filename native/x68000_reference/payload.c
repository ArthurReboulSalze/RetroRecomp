/* Original Retro-Recomp, MIT. Embedded originals are only copied to owned data. */
#include "payload.h"
#include "platform_io.h"
#include "embedded_resources.h"
#include "x68000_payload.h"
#include <stdint.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
static HANDLE game_lock=INVALID_HANDLE_VALUE;
#else
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
static int game_lock=-1;
#endif
#ifdef _WIN32
/* Wide Win32 calls stop at MAX_PATH (260 characters, 248 for a folder) unless the path carries the extended-length
 * prefix, so a game placed deep in a folder tree could not prepare its private data. Only the operating-system calls
 * see the prefixed copy; every path kept or returned stays as given, and a short path is used as it is. */
#define OS_PATH_LONG 240
#define OS_PATH_CAPACITY 4112
/* The path is made absolute and normalised by GetFullPathNameW first (".", "..", "/", trailing dots and spaces), as the
 * short form is normalised by Win32 itself: the prefixed form skips that step, and a short relative path can grow past
 * MAX_PATH once made absolute. */
static const wchar_t *os_path(const wchar_t *path,wchar_t *out) {
    wchar_t full[4096];size_t at=0;
    if(!wcsncmp(path,L"\\\\?\\",4)||!wcsncmp(path,L"\\\\.\\",4))return path;
    DWORD n=GetFullPathNameW(path,4096,full,NULL);if(!n||n>=4096)return NULL;
    if(n<OS_PATH_LONG)return path;
    if(full[0]==L'\\'&&full[1]==L'\\'){wmemcpy(out,L"\\\\?\\UNC\\",8);at=8;}
    else{wmemcpy(out,L"\\\\?\\",4);at=4;}
    wmemcpy(out+at,full+(at==8?2:0),n-(at==8?2:0)+1);
    return out;
}
static FILE *os_fopen(const wchar_t *path,const wchar_t *mode) {
    wchar_t long_path[OS_PATH_CAPACITY];const wchar_t *p=os_path(path,long_path);return p?rr_fopen(p,mode):NULL;
}
static int os_mkdir(const wchar_t *path) {
    wchar_t long_path[OS_PATH_CAPACITY];const wchar_t *p=os_path(path,long_path);return p&&rr_mkdir(p);
}
static int os_replace(const wchar_t *from,const wchar_t *to) {
    wchar_t long_from[OS_PATH_CAPACITY],long_to[OS_PATH_CAPACITY];
    const wchar_t *a=os_path(from,long_from),*b=os_path(to,long_to);return a&&b&&rr_replace(a,b);
}
static void os_remove(const wchar_t *path) {
    wchar_t long_path[OS_PATH_CAPACITY];const wchar_t *p=os_path(path,long_path);if(p)rr_remove(p);
}
#else
#define os_fopen rr_fopen
#define os_mkdir rr_mkdir
#define os_replace rr_replace
#define os_remove rr_remove
#endif
static int safe_path(const wchar_t *given) {
#ifdef _WIN32
    wchar_t long_path[OS_PATH_CAPACITY];const wchar_t *path=os_path(given,long_path);
    if(!path)return 0;
    DWORD attr=GetFileAttributesW(path);
    if(attr==INVALID_FILE_ATTRIBUTES)return GetLastError()==ERROR_FILE_NOT_FOUND||GetLastError()==ERROR_PATH_NOT_FOUND;
    if(attr&FILE_ATTRIBUTE_REPARSE_POINT)return 0;
    if(!(attr&FILE_ATTRIBUTE_DIRECTORY)){
        BY_HANDLE_FILE_INFORMATION info;HANDLE h=CreateFileW(path,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
        if(h==INVALID_HANDLE_VALUE)return 0;
        int ok=GetFileInformationByHandle(h,&info)&&info.nNumberOfLinks==1;CloseHandle(h);return ok;
    }
    return 1;
#else
    const wchar_t *path=given;
    char name[8192];struct stat st;if(!rr_to_utf8(path,name,sizeof(name)))return 0;
    if(lstat(name,&st))return errno==ENOENT;
    return S_ISDIR(st.st_mode)||(S_ISREG(st.st_mode)&&st.st_nlink==1);
#endif
}
/* Something is there (a file, a folder, anything) that fopen could not open for reading. */
static int path_exists(const wchar_t *given) {
#ifdef _WIN32
    wchar_t long_path[OS_PATH_CAPACITY];const wchar_t *path=os_path(given,long_path);
    return path&&GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES;
#else
    char name[8192];struct stat st;
    return rr_to_utf8(given,name,sizeof(name))&&!lstat(name,&st);
#endif
}
static int directories(wchar_t *path) {
    for(wchar_t *p=path;*p;p++)if(*p=='/'||*p=='\\'){
        wchar_t old=*p;if(p==path||(p==path+2&&path[1]==':'))continue;
        *p=0;int ok=safe_path(path);*p=old;if(!ok)return 0;
    }
    return safe_path(path)&&os_mkdir(path);
}
/* Moves an unusable file to "<file>.unusable-N" (the first N from 1 to 99 that is free; the last one is replaced when all
 * are taken). Returns 0 only when the file cannot be moved. */
static int set_aside(const wchar_t *file) {
    wchar_t aside[4096];
    for(unsigned n=1;n<=99;n++){
        wchar_t suffix[16]=L".unusable-";size_t at=wcslen(suffix);
        if(n>=10)suffix[at++]=(wchar_t)(L'0'+n/10);
        suffix[at++]=(wchar_t)(L'0'+n%10);suffix[at]=0;
        rr_wide_copy(aside,4096,file);if(rr_wide_append(aside,4096,suffix))return 0;
        if(!safe_path(aside))return 0;
        FILE *taken=os_fopen(aside,L"rb");
        if(taken){fclose(taken);if(n<99)continue;}
        return os_replace(file,aside);
    }
    return 0;
}
int rr_x68k_payload_prepare(const char *base,char *directory,size_t capacity) {
    char value[4096];wchar_t root[4096],file[4096],lock[4096];
    if(snprintf(value,sizeof(value),"%sdatas",base)>=(int)sizeof(value)||!rr_from_utf8(value,root,4096)||!directories(root))return 0;
    rr_wide_append(root,4096,RR_SLASH_W L"games");if(!directories(root))return 0;
    snprintf(value,sizeof(value),"%sx68-%s",RR_SLASH,RR_X68K_SOURCE_IDENTITY);
    if(!rr_from_utf8(value,file,4096)||rr_wide_append(root,4096,file)||!directories(root)||!rr_to_utf8(root,directory,capacity))return 0;
    rr_wide_copy(lock,4096,root);rr_wide_append(lock,4096,RR_SLASH_W L"session.lock");if(!safe_path(lock))return 0;
#ifdef _WIN32
    {wchar_t long_lock[OS_PATH_CAPACITY];const wchar_t *lock_path=os_path(lock,long_lock);
    game_lock=lock_path?CreateFileW(lock_path,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL):INVALID_HANDLE_VALUE;}
    if(game_lock==INVALID_HANDLE_VALUE)return 0;
#else
    if(!rr_to_utf8(lock,value,sizeof(value)))return 0;
    game_lock=open(value,O_CREAT|O_RDWR|O_NOFOLLOW,0600);
    if(game_lock<0||flock(game_lock,LOCK_EX|LOCK_NB))return 0;
#endif
    const wchar_t *folders[]={L"media",L"system",L"system" RR_SLASH_W L"keropi",L"saves"};
    for(unsigned i=0;i<4;i++){
        rr_wide_copy(file,4096,root);rr_wide_append(file,4096,RR_SLASH_W);rr_wide_append(file,4096,folders[i]);
        if(!directories(file))return 0;
    }
    for(unsigned i=0;i<RR_X68K_FILE_COUNT;i++){
        const RrX68kPayloadFile *item=&rr_x68k_files[i];size_t size=0;
        const unsigned char *bytes=rr_resource(item->resource,&size);wchar_t tail[256];
        if(!bytes||!size||!rr_from_utf8(item->path,tail,256))return 0;
        rr_wide_copy(file,4096,root);rr_wide_append(file,4096,RR_SLASH_W);rr_wide_append(file,4096,tail);
        if(!safe_path(file))return 0;
        FILE *f=os_fopen(file,L"rb");
        if(f){
            int ok=1;
            if(item->writable){
                /* A floppy image keeps its size whatever the game writes: any other size is not this disk. */
                ok=!fseek(f,0,SEEK_END)&&(size_t)ftell(f)==size;
            }else{
                size_t at=0;unsigned char chunk[65536];
                while(at<size){size_t n=size-at;if(n>sizeof(chunk))n=sizeof(chunk);if(fread(chunk,1,n,f)!=n||memcmp(chunk,bytes+at,n)){ok=0;break;}at+=n;}
                if(ok&&(fgetc(f)!=EOF||ferror(f)))ok=0;
            }
            fclose(f);
            if(ok)continue;
            /* An unusable copy never blocks the game and is never deleted: it is kept under another name and the
             * original embedded in the executable is written again. */
            if(!set_aside(file))return 0;
        }else if(path_exists(file)&&!set_aside(file))return 0;
        wchar_t temporary[4096];rr_wide_copy(temporary,4096,file);rr_wide_append(temporary,4096,L".new");
        if(!safe_path(temporary))return 0;
        f=os_fopen(temporary,L"wb");if(!f)return 0;
        int ok=fwrite(bytes,1,size,f)==size&&rr_flush_file(f);if(fclose(f))ok=0;
        if(!ok||!os_replace(temporary,file)){os_remove(temporary);return 0;}
    }
    return 1;
}
void rr_x68k_payload_release(void) {
#ifdef _WIN32
    if(game_lock!=INVALID_HANDLE_VALUE)CloseHandle(game_lock);game_lock=INVALID_HANDLE_VALUE;
#else
    if(game_lock>=0)close(game_lock);game_lock=-1;
#endif
}
