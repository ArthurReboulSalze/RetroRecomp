#ifndef RR_RUNTIME_FEEDBACK_SDL_H
#define RR_RUNTIME_FEEDBACK_SDL_H
#include "runtime_feedback.h"
#include "retro_menu.h"
/* A closing status in the existing game window, only when hints exist. No
 * modal window, artificial delay, or UI added while the game is running. */
static void rr_feedback_close_screen(SDL_Renderer *renderer) {
    if(!rr_feedback_pending())return;
    if(renderer) {
        int x,y,unit;rr_menu_layout(renderer,&x,&y,&unit);
        SDL_RenderSetViewport(renderer,NULL);
        SDL_SetRenderDrawBlendMode(renderer,SDL_BLENDMODE_BLEND);
        rr_menu_box(renderer,x,y,unit,4,144,248,40,20,20,20,245);
        rr_menu_text(renderer,x,y,unit,12,153,"Saving fallback hints",245,245,245);
        rr_menu_text(renderer,x,y,unit,12,168,"for the next recompilation...",210,210,210);
        rr_menu_end(renderer);SDL_RenderPresent(renderer);
    }
    rr_feedback_finish();
}
#endif
