/* UTF-8 paths at the Windows preparation boundary. Original work: MIT. */
#ifndef RR_NEOGEO_PATH_IO_H
#define RR_NEOGEO_PATH_IO_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
static wchar_t *rr_ng_utf8_wide(const char *text) {
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,NULL,0);if(!n)return NULL;
    wchar_t *wide=malloc((size_t)n*sizeof *wide);if(!wide)return NULL;
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,wide,n)) {free(wide);return NULL;}
    return wide;
}
static FILE *rr_ng_utf8_fopen(const char *path,const char *mode) {
    wchar_t *p=rr_ng_utf8_wide(path),*m=rr_ng_utf8_wide(mode);FILE *file=p && m?_wfopen(p,m):NULL;
    free(p);free(m);return file;
}
static int rr_ng_utf8_remove(const char *path) {
    wchar_t *p=rr_ng_utf8_wide(path);int result=p && DeleteFileW(p)?0:-1;free(p);return result;
}
#endif
