/* Small file/settings boundary shared by Windows and POSIX hosts. */
#ifndef RR_PLATFORM_IO_H
#define RR_PLATFORM_IO_H
#include <stdio.h>
#include <wchar.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define RR_SLASH_W L"\\"
#define RR_SLASH "\\"
static inline int rr_from_utf8(const char *s,wchar_t *out,size_t cap) { return MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,out,(int)cap)!=0; }
static inline int rr_to_utf8(const wchar_t *s,char *out,size_t cap) { return WideCharToMultiByte(CP_UTF8,0,s,-1,out,(int)cap,NULL,NULL)!=0; }
static inline int rr_exists(const wchar_t *p) { return GetFileAttributesW(p)!=INVALID_FILE_ATTRIBUTES; }
static inline int rr_mkdir(const wchar_t *p) { return CreateDirectoryW(p,NULL)||GetLastError()==ERROR_ALREADY_EXISTS; }
static inline FILE *rr_fopen(const wchar_t *p,const wchar_t *m) { return _wfopen(p,m); }
static inline int rr_replace(const wchar_t *a,const wchar_t *b) { return MoveFileExW(a,b,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0; }
static inline void rr_remove(const wchar_t *p) { _wremove(p); }
static inline int rr_copy_new(const wchar_t *a,const wchar_t *b) { return CopyFileW(a,b,TRUE)!=0; }
static inline int rr_ini_get(const wchar_t *s,const wchar_t *k,const wchar_t *d,wchar_t *out,unsigned cap,const wchar_t *p) { return (int)GetPrivateProfileStringW(s,k,d,out,cap,p); }
static inline int rr_ini_int(const wchar_t *s,const wchar_t *k,int d,const wchar_t *p) { return (int)GetPrivateProfileIntW(s,k,d,p); }
static inline int rr_ini_set(const wchar_t *s,const wchar_t *k,const wchar_t *v,const wchar_t *p) { return WritePrivateProfileStringW(s,k,v,p)!=0; }
static inline unsigned long rr_process_id(void) { return GetCurrentProcessId(); }
static inline int rr_flush_file(FILE *f) { return fflush(f)==0 && _commit(_fileno(f))==0; }
static inline int rr_executable_directory(wchar_t *out,size_t cap) {
    DWORD n=GetModuleFileNameW(NULL,out,(DWORD)cap);
    if(!n || n>=cap)return 0;
    wchar_t *slash=wcsrchr(out,L'\\'); if(!slash)return 0; *slash=0;return 1;
}
#else
#define RR_SLASH_W L"/"
#define RR_SLASH "/"
int rr_from_utf8(const char *,wchar_t *,size_t);
int rr_to_utf8(const wchar_t *,char *,size_t);
int rr_exists(const wchar_t *);
int rr_mkdir(const wchar_t *);
FILE *rr_fopen(const wchar_t *,const wchar_t *);
int rr_replace(const wchar_t *,const wchar_t *);
void rr_remove(const wchar_t *);
int rr_copy_new(const wchar_t *,const wchar_t *);
int rr_ini_get(const wchar_t *,const wchar_t *,const wchar_t *,wchar_t *,unsigned,const wchar_t *);
int rr_ini_int(const wchar_t *,const wchar_t *,int,const wchar_t *);
int rr_ini_set(const wchar_t *,const wchar_t *,const wchar_t *,const wchar_t *);
int rr_executable_directory(wchar_t *out,size_t cap);
unsigned long rr_process_id(void);
int rr_flush_file(FILE *);
#endif
static inline int rr_wide_copy(wchar_t *out,size_t cap,const wchar_t *source) {
    size_t n=wcslen(source);if(n>=cap){if(cap)out[0]=0;return ERANGE;}
    memmove(out,source,(n+1)*sizeof(wchar_t));return 0;
}
static inline int rr_wide_append(wchar_t *out,size_t cap,const wchar_t *source) {
    size_t n=wcslen(out);return n<cap?rr_wide_copy(out+n,cap-n,source):ERANGE;
}
static inline int rr_game_data_file(wchar_t *out,size_t cap,const char *subdir,
                                   const char *name,const char *sha,const char *suffix) {
    char tail[2048];wchar_t wide[2048];
    int n=snprintf(tail,sizeof(tail),RR_SLASH "datas" RR_SLASH "%s" RR_SLASH "%s-%.12s%s",subdir,name,sha,suffix);
    return n>0 && n<(int)sizeof(tail) && rr_executable_directory(out,cap) &&
        rr_from_utf8(tail,wide,2048) && rr_wide_append(out,cap,wide)==0;
}
#ifdef __cplusplus
}
#endif
#endif
