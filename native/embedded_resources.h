#ifndef RR_EMBEDDED_RESOURCES_H
#define RR_EMBEDDED_RESOURCES_H
#include <stddef.h>
#include <SDL.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef _WIN32
#include <windows.h>
static inline const void *rr_resource(unsigned id,size_t *size) {
    HRSRC r=FindResourceW(NULL,MAKEINTRESOURCEW(id),MAKEINTRESOURCEW(10));
    if(!r){*size=0;return NULL;}
    *size=SizeofResource(NULL,r);HGLOBAL loaded=LoadResource(NULL,r);
    return loaded?LockResource(loaded):NULL;
}
#else
const void *rr_resource(unsigned id,size_t *size);
#endif
static inline void rr_set_window_icon(SDL_Window *window) {
#ifndef _WIN32
    size_t size;const void *data=rr_resource(101,&size);
    if(!window || !data || !size || size>0x7fffffff)return;
    SDL_RWops *rw=SDL_RWFromConstMem(data,(int)size);
    SDL_Surface *icon=rw?SDL_LoadBMP_RW(rw,1):NULL;
    if(icon){SDL_SetWindowIcon(window,icon);SDL_FreeSurface(icon);}
#else
    (void)window;
#endif
}
#ifdef __cplusplus
}
#endif
#endif
