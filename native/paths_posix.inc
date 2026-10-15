#include "paths.h"
#include "embedded_rom.h"
#include "platform_io.h"
#include <string.h>

int retro_make_directories(wchar_t *p) {
    if(!p[0])return 0;
    for(size_t i=1;p[i];++i)if(p[i]==L'/') {
        p[i]=0;int ok=rr_mkdir(p);p[i]=L'/';if(!ok)return 0;
    }
    return rr_mkdir(p);
}
int retro_executable_directory(wchar_t *out) { return rr_executable_directory(out,RETRO_PATH_CAP); }
int retro_data_directory(wchar_t *out) {
    if(!retro_executable_directory(out) || wcslen(out)>RETRO_PATH_CAP-512)return 0;
    wcscat(out,L"/datas");return 1;
}
int retro_game_directory(wchar_t *out) {
    wchar_t root[RETRO_PATH_CAP],label[128],sha[65];
    if(!retro_data_directory(root)||!rr_from_utf8(sms_game_slug,label,128)||!rr_from_utf8(sms_rom_sha256,sha,65))return 0;
    return swprintf(out,RETRO_PATH_CAP,L"%ls/games/%ls-%.12ls",root,label,sha)>0;
}
static int file_path(wchar_t *out,const wchar_t *suffix) {
    wchar_t dir[RETRO_PATH_CAP],label[128];
    if(!retro_game_directory(dir)||!rr_from_utf8(sms_game_slug,label,128))return 0;
    return swprintf(out,RETRO_PATH_CAP,L"%ls/%ls%ls",dir,label,suffix)>0;
}
FILE *retro_game_file(const wchar_t *suffix,const wchar_t *mode) {
    wchar_t p[RETRO_PATH_CAP],dir[RETRO_PATH_CAP];if(!file_path(p,suffix))return NULL;
    if((mode[0]==L'w'||mode[0]==L'a')&&(!retro_game_directory(dir)||!retro_make_directories(dir)))return NULL;
    return rr_fopen(p,mode);
}
void retro_game_file_reset(const wchar_t *suffix) {wchar_t p[RETRO_PATH_CAP];if(file_path(p,suffix))rr_remove(p);}
int retro_game_file_replace(const wchar_t *a,const wchar_t *b) {wchar_t x[RETRO_PATH_CAP],y[RETRO_PATH_CAP];return file_path(x,a)&&file_path(y,b)&&rr_replace(x,y);}
