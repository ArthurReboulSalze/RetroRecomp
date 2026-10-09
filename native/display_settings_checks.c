/* Persistence checks: no SDL video driver or visible window is opened. */
#undef NDEBUG
#include <assert.h>
#include <SDL.h>
#include <windows.h>
#include <stdio.h>
static int fail_transition;
static int window_mode(SDL_Window *window, Uint32 flags) {
    (void)window; assert(flags==0 || flags==SDL_WINDOW_FULLSCREEN_DESKTOP);
    return fail_transition ? -1 : 0;
}
#define SDL_SetWindowFullscreen window_mode
#include "display_settings.h"
#undef SDL_SetWindowFullscreen
int wmain(int argc,wchar_t **argv) {
    assert(argc==2);
    wchar_t path[32768]; swprintf_s(path,32768,L"%s\\Retro-Recomp.ini",argv[1]);
    const wchar_t *sections[]={L"NES.Video",L"MegaDrive.Video",L"SNES.Video"};
    int filter=-1,mode=-1;
    rr_display_load(path,sections[0],&filter,&mode);
    assert(filter==0 && mode==0 && GetFileAttributesW(argv[1])==INVALID_FILE_ATTRIBUTES);
    for (int s=0;s<3;++s) {
        mode=0;
        for (int cycle=0;cycle<6;++cycle) {
            assert(rr_display_cycle(NULL,&mode,path,argv[1],sections[s])==1);
            int stored=-1; rr_display_load(path,sections[s],&filter,&stored);
            assert(stored==mode && stored==(cycle+1)%3);
        }
        for (int f=0;f<4;++f) {
            assert(rr_display_save(path,argv[1],sections[s],L"filter",f));
            rr_display_load(path,sections[s],&filter,&mode); assert(filter==f);
        }
        fail_transition=1; assert(rr_display_cycle(NULL,&mode,path,argv[1],sections[s])==0);
        fail_transition=0; rr_display_load(path,sections[s],&filter,&mode); assert(mode==0);
    }
    assert(rr_display_save(path,argv[1],sections[0],L"display_mode",2));
    rr_display_load(path,sections[1],&filter,&mode); assert(mode==0);
    assert(rr_display_save(path,argv[1],sections[0],L"display_mode",99));
    assert(rr_display_save(path,argv[1],sections[0],L"filter",-1));
    rr_display_load(path,sections[0],&filter,&mode); assert(filter==0 && mode==0);
    puts("PASS: lazy reads; three independent console profiles; F4 cycles survive reload; four filters; failed transitions; invalid values.");
    return 0;
}
