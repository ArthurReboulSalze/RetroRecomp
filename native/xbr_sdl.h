#ifndef RR_XBR_SDL_H
#define RR_XBR_SDL_H
#include <SDL.h>
#include "xbr_filter.h"
typedef struct {
    SDL_Texture *texture;
    uint32_t *pixels;
    int width,height;
    RrXbrWeights weights;
} RrXbr;
static void rr_xbr_destroy(RrXbr *state) {
    if(state->texture) SDL_DestroyTexture(state->texture);
    SDL_free(state->pixels); state->texture=NULL;state->pixels=NULL;state->width=state->height=0;
}
/* Work only on the completed presentation frame; no previous-frame history.
 * Allocation is limited to first use or visible-resolution changes. */
static SDL_Texture *rr_xbr_update(SDL_Renderer *renderer,RrXbr *state,const uint32_t *src,int w,int h,int stride) {
    if(w<1 || h<1 || w>1024 || h>1024 || stride<w) return NULL;
    if(!state->texture || w!=state->width || h!=state->height) {
        rr_xbr_destroy(state);
        state->pixels=(uint32_t *)SDL_malloc((size_t)w*h*16*sizeof(uint32_t));
        state->texture=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_ARGB8888,SDL_TEXTUREACCESS_STREAMING,w*4,h*4);
        if(!state->pixels || !state->texture) { rr_xbr_destroy(state);return NULL; }
        SDL_SetTextureScaleMode(state->texture,SDL_ScaleModeLinear);
        state->width=w;state->height=h;
    }
    rr_xbr4(src,w,h,stride,state->pixels,&state->weights);
    if(SDL_UpdateTexture(state->texture,NULL,state->pixels,w*16)!=0) return NULL;
    return state->texture;
}
#endif
