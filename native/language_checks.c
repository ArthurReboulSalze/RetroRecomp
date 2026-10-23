#define SDL_MAIN_HANDLED
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <SDL.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "retro_menu.h"
int main(int argc,char **argv) {
    const char *codes[]={"en","fr","it","es","de"};
    assert(rr_language_from_code("fr-CA")==1);
    assert(rr_language_from_code("ja_JP")==0); /* converter-only languages fall back to English */
    assert(rr_language_from_code("french")==0);
    assert(rr_menu_text_width("ABC")==15); /* five-unit cells */
    assert(rr_menu_text_width("\344\270\255\346\226\207")==10); /* no CJK/Cyrillic glyphs: one cell each */
    assert(rr_menu_text_width("\320\257")==5);
    assert(rr_menu_text_width("\303\251")==5);
    assert(rr_menu_text_width("\342")==5);
    SDL_SetMainReady();assert(SDL_Init(SDL_INIT_VIDEO)==0);
    SDL_Surface *surface=SDL_CreateRGBSurfaceWithFormat(0,1024,384,32,SDL_PIXELFORMAT_ARGB8888);
    assert(surface);
    SDL_Renderer *renderer=SDL_CreateSoftwareRenderer(surface);assert(renderer);
    assert(rr_menu_init(renderer));
    SDL_SetRenderDrawColor(renderer,20,20,20,255); SDL_RenderClear(renderer);
    for(int id=0;id<RR_LANGUAGE_COUNT;++id) {
        assert(!strcmp(rr_language_code(id),codes[id]));
        assert(rr_language_from_code(codes[id])==id);
        assert(rr_language_from_wide(rr_language_wide(id))==id);
        assert(rr_language_next(id)==(id+1)%RR_LANGUAGE_COUNT);
        rr_language_set(id);
        assert(rr_language_get()==id);
        assert(id==0 || strcmp(rr_tr("Game paused"),"Game paused"));
        int x=(id%4)*256,y=(id/4)*192;
        rr_menu_box(renderer,x,y,1,4,4,248,184,7,23,50,255);
        rr_menu_text(renderer,x,y,1,14,15,rr_language_name(id),38,215,255);
        const char *lines[]={"F1  Help | Shift+F1 Restart","F2  Controls","F3  Next filter","F4  Window / Pixel / Fit","F7  Next language","F8  Save game state","Game paused","Gamepad","Keyboard","Saving fallback hints..."};
        for(int row=0;row<10;++row)rr_menu_text(renderer,x,y,1,14,34+row*14,lines[row],233,239,247);
    }
    SDL_RenderPresent(renderer);
    if(argc>1)assert(SDL_SaveBMP(surface,argv[1])==0);
    rr_menu_shutdown();SDL_DestroyRenderer(renderer);SDL_FreeSurface(surface);

    /* At scale 3 the 10x20 font is rebuilt for 15x30 cells: solid strokes with
     * blended edges, and accented Latin-1 falls back to the same ASCII cell. */
    SDL_Surface *large=SDL_CreateRGBSurfaceWithFormat(0,768,576,32,SDL_PIXELFORMAT_ARGB8888);assert(large);
    SDL_Renderer *scaled=SDL_CreateSoftwareRenderer(large);assert(scaled);
    assert(rr_menu_init(scaled));
    int ox,oy,unit;rr_menu_layout(scaled,&ox,&oy,&unit);assert(unit==3 && !ox && !oy);
    rr_language_set(0);
    SDL_SetRenderDrawColor(scaled,0,0,0,255);SDL_RenderClear(scaled);
    rr_menu_text(scaled,ox,oy,unit,20,20,"E",255,255,255);
    rr_menu_text(scaled,ox,oy,unit,40,20,"\303\211",255,255,255);
    SDL_RenderPresent(scaled);
    const uint32_t *pixels=large->pixels;int pitch=large->pitch/4,solid=0,edge=0;
    for(int y=60;y<90;++y)for(int x=0;x<15;++x) {
        uint32_t plain=pixels[y*pitch+60+x]&0xffffff,accent=pixels[y*pitch+120+x]&0xffffff;
        assert(plain==accent);
        solid+=plain==0xffffff;edge+=plain && plain!=0xffffff;
    }
    assert(solid>=40 && edge>=10);
    rr_menu_shutdown();SDL_DestroyRenderer(scaled);SDL_FreeSurface(large);SDL_Quit();
    puts("PASS: five ASCII menus, stable IDs, cycle, printf catalogue and fine 10x20 text at scale 3");return 0;
}
