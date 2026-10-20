/* Authored checks only: no cartridge, BIOS, gameplay or audible output. */
#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <assert.h>
#include <stdio.h>
#include <math.h>
static Uint64 now_ms;
static Uint64 fixture_ticks(void) {return now_ms;}
#define SDL_GetTicks64 fixture_ticks
#include "game_options.h"
#include "player_gamepad.c"
static int menu;
static void key(int code, int down) {
    SDL_Event e; memset(&e,0,sizeof e);
    e.type = down ? SDL_KEYDOWN : SDL_KEYUP; e.key.keysym.scancode=(SDL_Scancode)code;
    rr_options_event(&e,&menu,false,true);
}
static void button(int id, int code, int down) {
    SDL_Event e; memset(&e,0,sizeof e);
    e.type=down?SDL_CONTROLLERBUTTONDOWN:SDL_CONTROLLERBUTTONUP;
    e.cbutton.which=id;e.cbutton.button=(Uint8)code;
    rr_options_event(&e,&menu,false,true);
}
static double energy(int mode,double frequency,int rate) {
    int16_t pcm[4096];RrAudioFilter s={0};
    for(int i=0;i<4096;++i)pcm[i]=(int16_t)(20000*sin(6.283185307179586*frequency*i/rate));
    rr_audio_filter(pcm,4096,1,0,rate,mode,&s);
    double e=0;for(int i=1024;i<4096;++i)e+=(double)pcm[i]*pcm[i];return e;
}
static void sound(void) {
    int16_t original[2048],whole[2048],chunks[2048];
    for(int i=0;i<2048;++i)original[i]=(int16_t)(i*173+129);
    for(int mode=0;mode<3;++mode) {
        RrAudioFilter a={0},b={0};
        memcpy(whole,original,sizeof whole);memcpy(chunks,original,sizeof chunks);
        rr_audio_filter(whole,1024,2,0,48000,mode,&a);
        for(int i=0;i<1024;i+=32)rr_audio_filter(chunks+i*2,32,2,0,48000,mode,&b);
        assert(!memcmp(whole,chunks,sizeof whole));
        if(!mode)assert(!memcmp(whole,original,sizeof whole));
    }
    for(int rate=44100;rate<=48000;rate+=3900) {
        assert(energy(1,16000,rate)<energy(0,16000,rate)*.6);
        assert(energy(2,16000,rate)<energy(1,16000,rate)*.6);
        assert(energy(2,1000,rate)>energy(0,1000,rate)*.9);
    }
    float pcm[128];RrAudioFilter f={0};
    for(int i=0;i<64;++i){pcm[2*i]=.5f;pcm[2*i+1]=-.25f;}
    rr_audio_filter(pcm,64,2,1,48000,2,&f);
    for(int i=0;i<64;++i){assert(pcm[2*i]==.5f);assert(pcm[2*i+1]==-.25f);}
    assert(f.ready);rr_audio_filter(pcm,64,2,1,48000,0,&f);assert(!f.ready);
    /* Off preserves even floating point payload bits exactly. */
    uint32_t bits[4]={0x80000000u,0x7fc01234u,0x3f800000u,0xbf800000u},copy[4];
    memcpy(copy,bits,sizeof bits);rr_audio_filter(bits,2,2,1,48000,0,&f);assert(!memcmp(copy,bits,sizeof bits));
}
static void chords(void) {
    rr_options_init(L"Fixture");rr_mkdir(rr_options.dir);rr_remove(rr_options.file);
    rr_options_init(L"Fixture");
    assert(!rr_options.pad && !rr_options.key[0] && !SDL_AtomicGet(&rr_options.audio_mode));
    rr_ini_set(L"Unrelated",L"keep",L"42",rr_options.file);
    key(SDL_SCANCODE_F10,1);assert(menu==RR_OPTIONS_MENU);key(SDL_SCANCODE_F10,0);
    key(SDL_SCANCODE_RETURN,1);key(SDL_SCANCODE_RETURN,0);
    assert(SDL_AtomicGet(&rr_options.audio_mode)==1);
    key(SDL_SCANCODE_DOWN,1);key(SDL_SCANCODE_DOWN,0);
    key(SDL_SCANCODE_RETURN,1);key(SDL_SCANCODE_RETURN,0);assert(rr_options.capture && rr_options.armed);
    key(SDL_SCANCODE_LCTRL,1);key(SDL_SCANCODE_Q,1);
    key(SDL_SCANCODE_Q,0);assert(rr_options.capture);
    key(SDL_SCANCODE_LCTRL,0);assert(!rr_options.capture && rr_options.key[0]==SDL_SCANCODE_LCTRL);
    key(SDL_SCANCODE_ESCAPE,1);key(SDL_SCANCODE_ESCAPE,0);assert(!menu);
    assert(!rr_options_quit(menu));
    key(SDL_SCANCODE_LCTRL,1);key(SDL_SCANCODE_Q,1);
    now_ms=100;assert(!rr_options_quit(menu));now_ms=1099;assert(!rr_options_quit(menu));
    now_ms=1100;assert(rr_options_quit(menu));
    key(SDL_SCANCODE_Q,0);assert(!rr_options_quit(menu));key(SDL_SCANCODE_LCTRL,0);
    rr_options_init(L"Fixture");
    assert(SDL_AtomicGet(&rr_options.audio_mode)==1 && rr_options.key[1]==SDL_SCANCODE_Q);
    assert(rr_ini_int(L"Unrelated",L"keep",0,rr_options.file)==42);
    /* A binding capture must receive F10 and Guide untouched. */
    SDL_Event e;memset(&e,0,sizeof e);e.type=SDL_KEYDOWN;e.key.keysym.scancode=SDL_SCANCODE_F10;
    assert(!rr_options_event(&e,&menu,true,true));key(SDL_SCANCODE_F10,0);
    button(8,SDL_CONTROLLER_BUTTON_GUIDE,1);button(8,SDL_CONTROLLER_BUTTON_GUIDE,0);
    assert(menu==RR_OPTIONS_MENU);
    rr_options.row=2;button(8,SDL_CONTROLLER_BUTTON_A,1);button(8,SDL_CONTROLLER_BUTTON_A,0);
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);button(8,SDL_CONTROLLER_BUTTON_START,1);
    button(8,SDL_CONTROLLER_BUTTON_BACK,0);button(8,SDL_CONTROLLER_BUTTON_START,0);
    assert(rr_options.pad==((1<<SDL_CONTROLLER_BUTTON_START)|(1<<SDL_CONTROLLER_BUTTON_BACK)));
    button(8,SDL_CONTROLLER_BUTTON_B,1);button(8,SDL_CONTROLLER_BUTTON_B,0);assert(!rr_options_quit(menu));
    /* Never combine buttons on different controllers. */
    button(8,SDL_CONTROLLER_BUTTON_START,1);button(9,SDL_CONTROLLER_BUTTON_BACK,1);
    now_ms=2000;assert(!rr_options_quit(menu));now_ms=4000;assert(!rr_options_quit(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);assert(!rr_options_quit(menu));
    now_ms=5000;assert(rr_options_quit(menu));
    memset(&e,0,sizeof e);e.type=SDL_CONTROLLERDEVICEREMOVED;e.cdevice.which=8;
    rr_options_event(&e,&menu,false,true);assert(!rr_options_quit(menu));
    button(9,SDL_CONTROLLER_BUTTON_BACK,0);
    /* Removing the first pad must not duplicate the second pad's tracking. */
    button(9,SDL_CONTROLLER_BUTTON_START,1);button(9,SDL_CONTROLLER_BUTTON_BACK,1);
    assert(!rr_options_quit(menu));now_ms=6000;assert(rr_options_quit(menu));
    memset(&e,0,sizeof e);e.type=SDL_WINDOWEVENT;e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;
    rr_options_event(&e,&menu,false,true);assert(!rr_options_quit(menu));
    rr_options_init(L"Fixture");assert(rr_options.pad);
    rr_remove(rr_options.file);
}
static void pads(void) {
    RrPlayerPads *p=rr_player_pads_open();assert(p);
    int32_t values[12];int baseline=rr_player_pads_poll(p,values);
    int i=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    assert(i>=0);SDL_Joystick *j=SDL_JoystickOpen(i);assert(j);
    assert(rr_player_pads_poll(p,values)==baseline+1);
    int slot=-1;
    for(int k=0;k<4;++k)if(p->pad[k] && SDL_GameControllerGetJoystick(p->pad[k])==j)slot=k;
    assert(slot>=0);
    assert(SDL_JoystickSetVirtualButton(j,SDL_CONTROLLER_BUTTON_A,1)==0);
    assert(SDL_JoystickSetVirtualAxis(j,SDL_CONTROLLER_AXIS_LEFTY,-25000)==0);
    assert(rr_player_pads_poll(p,values)==baseline+1);assert(values[slot*3]&1);assert(values[slot*3+2]==-25000);
    SDL_JoystickClose(j);SDL_JoystickDetachVirtual(i);
    assert(rr_player_pads_poll(p,values)==baseline);assert(!values[slot*3] && !values[slot*3+2]);
    rr_player_pads_close(p);
}
int main(void) {
    SDL_SetMainReady();assert(SDL_Init(0)==0);
    pads(); /* Tk has no SDL video window: exercise exactly that lifetime. */
    assert(SDL_InitSubSystem(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER)==0);
    sound();chords();
    SDL_Window *win=SDL_CreateWindow("Options fixture",0,0,768,576,SDL_WINDOW_HIDDEN);assert(win);
    SDL_Renderer *ren=SDL_CreateRenderer(win,-1,SDL_RENDERER_SOFTWARE);assert(ren);assert(rr_menu_init(ren));
    rr_options_draw(ren);SDL_RenderPresent(ren);
    SDL_Surface *image=SDL_CreateRGBSurfaceWithFormat(0,768,576,32,SDL_PIXELFORMAT_ARGB8888);
    assert(image);assert(SDL_RenderReadPixels(ren,NULL,image->format->format,image->pixels,image->pitch)==0);
    assert(SDL_SaveBMP(image,"options.bmp")==0);SDL_FreeSurface(image);
    rr_menu_shutdown();SDL_DestroyRenderer(ren);SDL_DestroyWindow(win);SDL_Quit();
    puts("PASS: byte-exact audio bypass, optional tone filters, persistent chords, focus/disconnect and virtual controller.");return 0;
}
