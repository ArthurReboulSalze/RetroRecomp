/* Original Retro-Recomp, MIT. The X68000's own part of the player menus on the host kit: the computer's events
 * (guest keyboard, Ctrl+Alt chords, function keys, pause, help pages) and real software-rendered pages. The kit's
 * pages themselves are proved by the A/B battery (tools/hostkit_ab.py) and the self-tests of the shell. */
#include <SDL.h>
#define main rr_unused_frontend_main
#include "../native/x68000_reference/reference_host.c"
/* The kit functions the harness drives directly (clang refuses implicit declarations). */
#include "hostkit/hostkit_internal.h"
#undef main
static unsigned checks,failures;
static bool harness_running=true;
static void check(int okay,const char *name){checks++;if(!okay){failures++;fprintf(stderr,"FAIL: %s\n",name);}}
static bool press(SDL_Scancode scan,SDL_Keymod mod){
    SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_KEYDOWN;e.key.keysym.scancode=scan;e.key.keysym.sym=SDL_GetKeyFromScancode(scan);e.key.keysym.mod=mod;
    return rrhk_adapter()->event(&e,&harness_running);
}
static void lift(SDL_Scancode scan){
    SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_KEYUP;e.key.keysym.scancode=scan;e.key.keysym.sym=SDL_GetKeyFromScancode(scan);
    rrhk_adapter()->event(&e,&harness_running);
}
#define CHORD (SDL_Keymod)(KMOD_CTRL|KMOD_ALT)
int main(int argc,char **argv){
    int verify=argc>1&&!strcmp(argv[1],"--verify");wchar_t path[4096];RrhkUi *ui;
    SDL_SetMainReady();SDL_setenv("SDL_VIDEODRIVER","dummy",1);SDL_setenv("SDL_AUDIODRIVER","dummy",1);
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_AUDIO|SDL_INIT_EVENTS|SDL_INIT_GAMECONTROLLER))return 2;
    SDL_Window *window=SDL_CreateWindow("X68000 menus",0,0,768,576,SDL_WINDOW_HIDDEN);
    SDL_Renderer *renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);if(!renderer)return 2;
    SDL_FlushEvents(SDL_FIRSTEVENT,SDL_LASTEVENT);
    rr_executable_directory(path,4000);rr_wide_append(path,4096,RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini");
    if(!verify)rr_remove(path);
    rrhk_bind(rrhk_adapter());rrhk_load_bindings();rrhk_options_init(L"X68000");rrhk_options_keyboard("X68000",10);
    ui=rrhk_ui();xa.windowed=true;
    check(rr_menu_init(renderer),"shared font atlas initializes");
    if(verify){
        check(ui->filter==3,"scanlines persist across a fresh process");
        check(ui->fullscreen==1,"pixel display mode persists across a fresh process");
        check(ui->language==1&&rr_language_get()==1,"language persists across a fresh process");
        check(ui->buttons[0][X_PAUSE]==SDL_CONTROLLER_BUTTON_LEFTSTICK,"explicit L3 assignment persists");
        check(ui->keys[0][X_A]==SDL_GetScancodeFromKey(SDLK_z),"explicit fire binding overrides the new W default after restart");
        check(guest_keyboard&&ui->autofire,"the guest keyboard and autofire persist across a fresh process");
    }else{
        /* Pause: F11, or the Pause binding of a player. */
        check(press(SDL_SCANCODE_F11,KMOD_NONE)&&ui->paused,"F11 pauses without consuming a letter key");
        check(player_blocked(),"a paused guest is blocked");
        press(SDL_SCANCODE_F11,KMOD_NONE);check(!player_blocked(),"F11 resumes without consuming a letter key");
        check(!press(SDL_SCANCODE_H,KMOD_NONE)&&!press(SDL_SCANCODE_P,KMOD_NONE)&&!player_blocked(),"H and P remain available to computer games instead of opening help or pause");
        ui->keys[0][X_PAUSE]=SDL_SCANCODE_P;
        check(press(SDL_SCANCODE_P,KMOD_NONE)&&ui->paused,"the Pause binding pauses");
        press(SDL_SCANCODE_P,KMOD_NONE);check(!ui->paused,"the Pause binding resumes");
        ui->menu=1;press(SDL_SCANCODE_P,KMOD_NONE);check(!ui->paused,"a menu ignores the Pause binding");ui->menu=0;
        guest_keyboard=true;check(press(SDL_SCANCODE_P,KMOD_NONE)&&!ui->paused,"full typing leaves P to the guest");guest_keyboard=false;
        ui->keys[0][X_PAUSE]=SDL_SCANCODE_UNKNOWN;
        /* Escape closes a menu entirely before it can do anything else. */
        ui->menu=1;
        check(!press(SDL_SCANCODE_ESCAPE,KMOD_NONE)&&xa.escape_held,"menu Escape starts as the frontend's");
        ui->menu=0;
        check(press(SDL_SCANCODE_ESCAPE,KMOD_NONE),"menu Escape is consumed until release");
        {SDL_Event again;memset(&again,0,sizeof(again));again.type=SDL_KEYDOWN;again.key.repeat=1;again.key.keysym.scancode=SDL_SCANCODE_ESCAPE;
         check(rrhk_adapter()->event(&again,&harness_running)&&harness_running,"held menu Escape cannot become a quit event");}
        static Uint8 *state;state=(Uint8*)SDL_GetKeyboardState(NULL);keys=state;state[SDL_SCANCODE_ESCAPE]=1;guest_keyboard=true;
        check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"menu Escape never leaks into the full guest keyboard");
        lift(SDL_SCANCODE_ESCAPE);
        check(!xa.escape_held&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"release restores ordinary guest Escape handling");
        guest_keyboard=false;state[SDL_SCANCODE_ESCAPE]=0;
        /* Help and its second page. */
        ui->menu=RRHK_MENU_HELP;check(!x_help_page(ui,&(RrhkMenuCtx){renderer,0,0,1}),"the first help page is the kit's");
        press(SDL_SCANCODE_TAB,KMOD_NONE);check(xa.help_page==1,"Tab exposes computer keyboard and disk shortcuts");
        press(SDL_SCANCODE_TAB,KMOD_NONE);check(xa.help_page==0,"Tab returns to the shared page");ui->menu=0;
        press(SDL_SCANCODE_TAB,KMOD_NONE);check(xa.help_page==0,"Tab outside help is the guest's");
        /* Ctrl+Alt chords belong to the computer and always win. */
        check(press(SDL_SCANCODE_H,CHORD)&&ui->menu==RRHK_MENU_HELP,"Ctrl+Alt+H opens help");
        press(SDL_SCANCODE_H,CHORD);check(!ui->menu,"Ctrl+Alt+H closes it");
        press(SDL_SCANCODE_O,CHORD);check(ui->menu==RRHK_MENU_OPTIONS,"Ctrl+Alt+O opens the options");ui->menu=0;
        press(SDL_SCANCODE_K,CHORD);check(guest_keyboard,"Ctrl+Alt+K hands the keyboard to the guest");
        press(SDL_SCANCODE_H,CHORD);check(ui->menu==RRHK_MENU_HELP,"explicit computer chord regains host help in full typing");ui->menu=0;
        press(SDL_SCANCODE_K,CHORD);check(!guest_keyboard,"Ctrl+Alt+K returns to game shortcuts");
        press(SDL_SCANCODE_F,CHORD);check(ui->autofire,"Ctrl+Alt+F is the kit's autofire");press(SDL_SCANCODE_F,CHORD);check(!ui->autofire,"and turns it off again");
        check(harness_running,"nothing quit so far");press(SDL_SCANCODE_Q,CHORD);check(!harness_running,"Ctrl+Alt+Q quits");harness_running=true;
        press(SDL_SCANCODE_PAGEDOWN,CHORD);check(want_swap&&swap_direction==1&&!swap_drive,"Ctrl+Alt+Page Down is the next disk of FDD0");want_swap=false;
        press(SDL_SCANCODE_PAGEUP,(SDL_Keymod)(CHORD|KMOD_SHIFT));check(want_swap&&swap_direction==-1&&swap_drive==1,"Shift selects FDD1");want_swap=false;
        press(SDL_SCANCODE_BACKSPACE,CHORD);check(want_eject,"Ctrl+Alt+Backspace ejects");want_eject=false;
        /* Function keys: Retro-Recomp's by default; F1-F10 are the X68000's when the options hand them over. */
        check(!press(SDL_SCANCODE_F2,KMOD_NONE)&&!press(SDL_SCANCODE_F8,KMOD_NONE),"function keys stay Retro-Recomp's by default");
        {wchar_t on[2]=L"1";rr_ini_set(L"X68000.Options",L"fkeys_machine",on,ui->ini_file);}
        rrhk_options_keyboard("X68000",10);
        check(press(SDL_SCANCODE_F2,KMOD_NONE)&&press(SDL_SCANCODE_F8,KMOD_NONE),"the options row hands F1-F10 to the X68000");
        check(!press(SDL_SCANCODE_F12,KMOD_NONE),"F12, absent from the X68000, stays Retro-Recomp's");
        check(press(SDL_SCANCODE_F11,KMOD_NONE)&&ui->paused,"F11 still pauses");ui->paused=0;
        check(!press(SDL_SCANCODE_F8,KMOD_LCTRL),"Ctrl+F8 stays Retro-Recomp's");
        ui->menu=2;check(!press(SDL_SCANCODE_F2,KMOD_NONE),"inside a menu F2 closes it without Ctrl");ui->menu=0;
        {wchar_t off[2]=L"0";rr_ini_set(L"X68000.Options",L"fkeys_machine",off,ui->ini_file);}
        rrhk_options_keyboard("X68000",10);
        /* Every shared page renders in every game language, on the real renderer. */
        for(int lang=0;lang<RR_LANGUAGE_COUNT;lang++){
            rr_language_set(lang);ui->language=lang;
            ui->menu=RRHK_MENU_HELP;xa.help_page=0;SDL_RenderClear(renderer);rrhk_menu_draw(renderer);
            xa.help_page=1;rrhk_menu_draw(renderer);xa.help_page=0;
            ui->menu=RRHK_MENU_CONTROLS;rrhk_menu_draw(renderer);
            ui->menu=RRHK_MENU_OPTIONS;rrhk_menu_draw(renderer);
            ui->menu=0;ui->paused=1;rrhk_menu_draw(renderer);ui->paused=0;
        }
        check(!core_error,"all menu pages render in every game language");
        rr_language_set(0);ui->language=0;ui->menu=RRHK_MENU_HELP;xa.help_page=1;
        SDL_SetRenderDrawColor(renderer,0,0,0,255);SDL_RenderClear(renderer);rrhk_menu_draw(renderer);
        {
            int w,h;SDL_GetRendererOutputSize(renderer,&w,&h);
            SDL_Surface *preview=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_ARGB8888);
            char *base=SDL_GetBasePath(),name[4096];snprintf(name,sizeof(name),"%smenu-preview.bmp",base?base:"");
            check(preview&&SDL_RenderReadPixels(renderer,NULL,preview->format->format,preview->pixels,preview->pitch)==0&&SDL_SaveBMP(preview,name)==0,"menu preview captured from the actual SDL renderer");
            if(preview)SDL_FreeSurface(preview);SDL_free(base);
        }
        ui->menu=0;xa.help_page=0;
        /* What a fresh process finds: the kit's settings and the legacy layout of the first host. */
        ui->player=0;ui->row=X_A;ui->gamepad_page=0;ui->keys[0][X_A]=SDL_GetScancodeFromKey(SDLK_z);rrhk_store_binding();
        ui->row=X_PAUSE;ui->gamepad_page=1;ui->buttons[0][X_PAUSE]=SDL_CONTROLLER_BUTTON_LEFTSTICK;rrhk_store_binding();ui->gamepad_page=0;
        rr_display_save(ui->ini_file,ui->data_dir,L"X68000",L"filter",3);rr_display_save(ui->ini_file,ui->data_dir,L"X68000",L"display_mode",1);
        {wchar_t one[2]=L"1";rr_ini_set(L"Interface",L"language",rr_language_wide(1),ui->ini_file);rr_ini_set(L"X68000",L"autofire",one,ui->ini_file);}
        guest_keyboard=true;ui->autofire=1;player_store_exit();
        {char text[8192]="";size_t n=0;char narrow[4096];FILE *f;
         rr_to_utf8(ui->ini_file,narrow,sizeof(narrow));
         f=fopen(narrow,"rb");if(f){n=fread(text,1,sizeof(text)-1,f);fclose(f);}text[n]=0;
         check(strstr(text,"p0_key4=")&&strstr(text,"p0_pad7=")&&strstr(text,"[X68000]"),"bindings keep the layout of the first host: [X68000] p<player>_key<n> and p<player>_pad<n>");}
    }
    player_shutdown();rr_menu_shutdown();SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    printf("{\"checks\":%u,\"failures\":%u,\"fresh_process\":%s}\n",checks,failures,verify?"true":"false");
    return failures?1:0;
}
