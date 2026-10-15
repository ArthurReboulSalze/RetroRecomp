/* UTF-8 paths at the Windows preparation boundary. Original work: MIT. */
#ifndef RR_NEOGEO_PATH_IO_H
#define RR_NEOGEO_PATH_IO_H
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static wchar_t *rr_ng_utf8_wide(const char *text) {
    size_t n=strlen(text)+1;
    wchar_t *wide=malloc((size_t)n*sizeof *wide);if(!wide)return NULL;
    if(!rr_from_utf8(text,wide,n)) {free(wide);return NULL;}
    return wide;
}
static FILE *rr_ng_utf8_fopen(const char *path,const char *mode) {
    wchar_t *p=rr_ng_utf8_wide(path),*m=rr_ng_utf8_wide(mode);FILE *file=p && m?rr_fopen(p,m):NULL;
    free(p);free(m);return file;
}
static int rr_ng_utf8_remove(const char *path) {
    wchar_t *p=rr_ng_utf8_wide(path);int result=p && rr_exists(p)?(rr_remove(p),rr_exists(p)?-1:0):-1;free(p);return result;
}
#endif
