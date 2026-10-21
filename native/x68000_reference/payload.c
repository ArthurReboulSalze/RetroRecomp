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
static int safe_path(const wchar_t *path) {
#ifdef _WIN32
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
    char name[8192];struct stat st;if(!rr_to_utf8(path,name,sizeof(name)))return 0;
    if(lstat(name,&st))return errno==ENOENT;
    return S_ISDIR(st.st_mode)||(S_ISREG(st.st_mode)&&st.st_nlink==1);
#endif
}
static int directories(wchar_t *path) {
    for(wchar_t *p=path;*p;p++)if(*p=='/'||*p=='\\'){
        wchar_t old=*p;if(p==path||(p==path+2&&path[1]==':'))continue;
        *p=0;int ok=safe_path(path);*p=old;if(!ok)return 0;
    }
    return safe_path(path)&&rr_mkdir(path);
}
int rr_x68k_payload_prepare(const char *base,char *directory,size_t capacity) {
    char value[4096];wchar_t root[4096],file[4096],lock[4096];
    if(snprintf(value,sizeof(value),"%sdatas",base)>=(int)sizeof(value)||!rr_from_utf8(value,root,4096)||!directories(root))return 0;
    rr_wide_append(root,4096,RR_SLASH_W L"games");if(!directories(root))return 0;
    snprintf(value,sizeof(value),"%sx68-%s",RR_SLASH,RR_X68K_SOURCE_IDENTITY);
    if(!rr_from_utf8(value,file,4096)||rr_wide_append(root,4096,file)||!directories(root)||!rr_to_utf8(root,directory,capacity))return 0;
    rr_wide_copy(lock,4096,root);rr_wide_append(lock,4096,RR_SLASH_W L"session.lock");if(!safe_path(lock))return 0;
#ifdef _WIN32
    game_lock=CreateFileW(lock,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
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
        FILE *f=rr_fopen(file,L"rb");
        if(f){
            if(item->writable){fclose(f);continue;}
            size_t at=0;unsigned char chunk[65536];int ok=1;
            while(at<size){size_t n=size-at;if(n>sizeof(chunk))n=sizeof(chunk);if(fread(chunk,1,n,f)!=n||memcmp(chunk,bytes+at,n)){ok=0;break;}at+=n;}
            if(fgetc(f)!=EOF||ferror(f))ok=0;fclose(f);if(!ok)return 0;continue;
        }
        wchar_t temporary[4096];rr_wide_copy(temporary,4096,file);rr_wide_append(temporary,4096,L".new");
        if(!safe_path(temporary))return 0;
        f=rr_fopen(temporary,L"wb");if(!f)return 0;
        int ok=fwrite(bytes,1,size,f)==size&&rr_flush_file(f);if(fclose(f))ok=0;
        if(!ok||!rr_replace(temporary,file)){rr_remove(temporary);return 0;}
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
