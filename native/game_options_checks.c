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
    rr_options_event(&e,&menu,false);
}
static void button(int id, int code, int down) {
    SDL_Event e; memset(&e,0,sizeof e);
    e.type=down?SDL_CONTROLLERBUTTONDOWN:SDL_CONTROLLERBUTTONUP;
    e.cbutton.which=id;e.cbutton.button=(Uint8)code;
    rr_options_event(&e,&menu,false);
}
/* F10 is free: Guide opens the options page of F2 from the game. */
static void open_options(void) {
    button(7,SDL_CONTROLLER_BUTTON_GUIDE,1);button(7,SDL_CONTROLLER_BUTTON_GUIDE,0);assert(menu==RR_OPTIONS_MENU);
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
/* Option rows as a host builds them: one function key, then the shared rows. */
static RrOptionRows fixture_rows(void) {
    RrOptionRows d;d.count=0;
    rr_option_row(&d,SDL_SCANCODE_F3,"F3 Filter: %s",rr_option_filter_name(0));
    rr_option_shared_rows(&d);return d;
}
/* The rows are plain data: a copy made before the original is wiped still reads. */
static void rows_survive_copy(void) {
    RrOptionRows a=fixture_rows(),b;
    memcpy(&b,&a,sizeof a);memset(&a,0xA5,sizeof a);
    assert(b.count==5 && !strcmp(b.text[0],"F3 Filter: Sharp pixels") && !strncmp(b.text[1],"Audio filter: ",14) &&
           !strcmp(b.text[2],"Volume: 100%") && !strcmp(b.text[3],"M Sound: ON") && !strncmp(b.text[4],"Output device: ",15));
}
/* A key on the options page, as a host passes it after rr_options_event. */
static int page_key(const RrOptionRows *d, int code) {
    SDL_Event e;memset(&e,0,sizeof e);e.type=SDL_KEYDOWN;e.key.keysym.scancode=(SDL_Scancode)code;
    assert(!rr_options_event(&e,&menu,false));
    int result=rr_option_page_event(&e,d);
    e.type=SDL_KEYUP;rr_options_event(&e,&menu,false);return result;
}
static void chords(void) {
    rr_options_init(L"Fixture");rr_mkdir(rr_options.dir);rr_remove(rr_options.file);
    rr_options_init(L"Fixture");
    assert(rr_options.pad==(int)RR_OPTIONS_QUIT_PAD && rr_options.rpad==(int)RR_OPTIONS_RESTART_PAD &&
           !rr_options.key[0] && !rr_options.rkey[0] && !SDL_AtomicGet(&rr_options.audio_mode));
    rr_ini_set(L"Unrelated",L"keep",L"42",rr_options.file);
    key(SDL_SCANCODE_F10,1);key(SDL_SCANCODE_F10,0);assert(!menu);
    open_options();
    RrOptionRows rows=fixture_rows();
    assert(rows.count==5 && rows.keys[1]==RR_ROW_AUDIO);
    rr_options.row=1;assert(page_key(&rows,SDL_SCANCODE_RETURN)==-1 && SDL_AtomicGet(&rr_options.audio_mode)==1);
    /* Left/Right turn pages: the host receives them; - steps back. */
    SDL_Event turn;memset(&turn,0,sizeof turn);turn.type=SDL_KEYDOWN;turn.key.keysym.scancode=SDL_SCANCODE_RIGHT;
    assert(!rr_options_event(&turn,&menu,false) && !rr_option_page_event(&turn,&rows) && rr_pages_step(&turn)==1);
    turn.type=SDL_KEYUP;rr_options_event(&turn,&menu,false);
    assert(page_key(&rows,SDL_SCANCODE_MINUS)==-1 && SDL_AtomicGet(&rr_options.audio_mode)==0);
    assert(page_key(&rows,SDL_SCANCODE_EQUALS)==-1 && SDL_AtomicGet(&rr_options.audio_mode)==1);
    /* A function-key row runs its shortcut; - leaves it alone. */
    rr_options.row=0;assert(page_key(&rows,SDL_SCANCODE_RETURN)==SDL_SCANCODE_F3 && page_key(&rows,SDL_SCANCODE_MINUS)==-1);
    menu=0; /* hosts close F2 on Escape */
    /* Quit with the keyboard: player 1's keyboard page starts the capture on
     * Enter; the combination is taken once every key is released. */
    key(SDL_SCANCODE_RETURN,1);rr_combo_start(0,false);key(SDL_SCANCODE_RETURN,0);
    assert(rr_options.capture==1 && rr_options.armed);
    key(SDL_SCANCODE_LCTRL,1);key(SDL_SCANCODE_Q,1);
    key(SDL_SCANCODE_Q,0);assert(rr_options.capture);
    key(SDL_SCANCODE_LCTRL,0);assert(!rr_options.capture && rr_options.key[0]==SDL_SCANCODE_LCTRL);
    assert(!rr_options_quit(menu));
    key(SDL_SCANCODE_LCTRL,1);key(SDL_SCANCODE_Q,1);
    now_ms=100;assert(!rr_options_quit(menu));now_ms=1099;assert(!rr_options_quit(menu));
    now_ms=1100;assert(rr_options_quit(menu));
    key(SDL_SCANCODE_Q,0);assert(!rr_options_quit(menu));key(SDL_SCANCODE_LCTRL,0);
    rr_options_init(L"Fixture");
    assert(SDL_AtomicGet(&rr_options.audio_mode)==1 && rr_options.key[1]==SDL_SCANCODE_Q);
    assert(rr_ini_int(L"Unrelated",L"keep",0,rr_options.file)==42);
    /* A binding capture must receive function keys and Guide untouched. */
    SDL_Event e;memset(&e,0,sizeof e);e.type=SDL_KEYDOWN;e.key.keysym.scancode=SDL_SCANCODE_F10;
    assert(!rr_options_event(&e,&menu,true));key(SDL_SCANCODE_F10,0);
    button(8,SDL_CONTROLLER_BUTTON_GUIDE,1);button(8,SDL_CONTROLLER_BUTTON_GUIDE,0);
    assert(menu==RR_OPTIONS_MENU);
    /* Quit with a controller: the gamepad page starts the capture on A. */
    button(8,SDL_CONTROLLER_BUTTON_A,1);rr_combo_start(0,true);button(8,SDL_CONTROLLER_BUTTON_A,0);
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);button(8,SDL_CONTROLLER_BUTTON_START,1);
    button(8,SDL_CONTROLLER_BUTTON_BACK,0);button(8,SDL_CONTROLLER_BUTTON_START,0);
    assert(rr_options.pad==((1<<SDL_CONTROLLER_BUTTON_START)|(1<<SDL_CONTROLLER_BUTTON_BACK)));
    menu=0;assert(!rr_options_quit(menu));
    /* Never combine buttons on different controllers. */
    button(8,SDL_CONTROLLER_BUTTON_START,1);button(9,SDL_CONTROLLER_BUTTON_BACK,1);
    now_ms=2000;assert(!rr_options_quit(menu));now_ms=4000;assert(!rr_options_quit(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);assert(!rr_options_quit(menu));
    now_ms=5000;assert(rr_options_quit(menu));
    memset(&e,0,sizeof e);e.type=SDL_CONTROLLERDEVICEREMOVED;e.cdevice.which=8;
    rr_options_event(&e,&menu,false);assert(!rr_options_quit(menu));
    button(9,SDL_CONTROLLER_BUTTON_BACK,0);
    /* Removing the first pad must not duplicate the second pad's tracking. */
    button(9,SDL_CONTROLLER_BUTTON_START,1);button(9,SDL_CONTROLLER_BUTTON_BACK,1);
    assert(!rr_options_quit(menu));now_ms=6000;assert(rr_options_quit(menu));
    memset(&e,0,sizeof e);e.type=SDL_WINDOWEVENT;e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;
    rr_options_event(&e,&menu,false);assert(!rr_options_quit(menu));
    rr_options_init(L"Fixture");assert(rr_options.pad);
    /* A single key or button is a quit binding too, still held one second. */
    key(SDL_SCANCODE_RETURN,1);rr_combo_start(0,false);key(SDL_SCANCODE_RETURN,0);assert(rr_options.capture);
    key(SDL_SCANCODE_END,1);key(SDL_SCANCODE_END,0);
    assert(!rr_options.capture && rr_options.key[0]==SDL_SCANCODE_END && !rr_options.key[1]);
    button(8,SDL_CONTROLLER_BUTTON_A,1);rr_combo_start(0,true);button(8,SDL_CONTROLLER_BUTTON_A,0);
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);button(8,SDL_CONTROLLER_BUTTON_BACK,0);
    assert(!rr_options.capture && rr_options.pad==(1<<SDL_CONTROLLER_BUTTON_BACK));
    now_ms=7000;assert(!rr_options_quit(menu));
    key(SDL_SCANCODE_END,1);assert(!rr_options_quit(menu));
    now_ms=7999;assert(!rr_options_quit(menu));now_ms=8000;assert(rr_options_quit(menu));
    key(SDL_SCANCODE_END,0);assert(!rr_options_quit(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);now_ms=9000;assert(!rr_options_quit(menu));
    now_ms=10000;assert(rr_options_quit(menu));button(8,SDL_CONTROLLER_BUTTON_BACK,0);
    rr_options_init(L"Fixture");
    assert(rr_options.key[0]==SDL_SCANCODE_END && rr_options.pad==(1<<SDL_CONTROLLER_BUTTON_BACK));
    /* Default restart: Start+Select held one second, once per hold. */
    assert(rr_options.rpad==(int)RR_OPTIONS_RESTART_PAD);
    now_ms=20000;button(8,SDL_CONTROLLER_BUTTON_START,1);assert(!rr_options_restart(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);assert(!rr_options_restart(menu));
    now_ms=20999;assert(!rr_options_restart(menu));now_ms=21000;assert(rr_options_restart(menu));
    now_ms=23000;assert(!rr_options_restart(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,0);assert(!rr_options_restart(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,1);now_ms=23500;assert(!rr_options_restart(menu));
    now_ms=24500;assert(rr_options_restart(menu));
    button(8,SDL_CONTROLLER_BUTTON_BACK,0);button(8,SDL_CONTROLLER_BUTTON_START,0);
    /* Restart rows bind like quit rows: a single key, persisted; X clears. */
    key(SDL_SCANCODE_RETURN,1);rr_combo_start(1,false);key(SDL_SCANCODE_RETURN,0);
    key(SDL_SCANCODE_HOME,1);key(SDL_SCANCODE_HOME,0);assert(rr_options.rkey[0]==SDL_SCANCODE_HOME&&!rr_options.rkey[1]);
    rr_combo_clear(1,true);assert(!rr_options.rpad);
    now_ms=30000;assert(!rr_options_restart(menu));key(SDL_SCANCODE_HOME,1);assert(!rr_options_restart(menu));
    now_ms=31000;assert(rr_options_restart(menu));key(SDL_SCANCODE_HOME,0);
    rr_options_init(L"Fixture");assert(rr_options.rkey[0]==SDL_SCANCODE_HOME&&!rr_options.rpad);
    /* Combination rows show the binding, Unassigned or the capture prompt;
     * Escape cancels a capture. */
    char value[80];
    rr_combo_value(value,sizeof value,1,false);assert(!strcmp(value,rr_keyboard_name(SDL_SCANCODE_HOME)));
    rr_combo_value(value,sizeof value,1,true);assert(!strcmp(value,"Unassigned"));
    rr_combo_start(1,true);rr_combo_value(value,sizeof value,1,true);
    assert(rr_options.capture==4 && !strcmp(value,"Press combo, then release"));
    key(SDL_SCANCODE_ESCAPE,1);key(SDL_SCANCODE_ESCAPE,0);assert(!rr_options.capture);
    rr_remove(rr_options.file);
}
/* The sound controls of every console (decision D12): volume, mute, the speed hold and the output device, all in the one stage that
 * every console's PCM goes through. */
static void sound_controls(void) {
    rr_options_init(L"Fixture");rr_mkdir(rr_options.dir);rr_remove(rr_options.file);rr_options_init(L"Fixture");
    int16_t original[256],pcm[256];
    for(int i=0;i<256;++i)original[i]=(int16_t)((i*389)%30000-15000);
    /* The defaults leave the samples byte for byte, filter or not. */
    memcpy(pcm,original,sizeof pcm);rr_options_audio(pcm,128,2,0,48000);assert(!memcmp(pcm,original,sizeof pcm));
    /* 50% halves, 200% doubles and clamps, 0 is silence. */
    SDL_AtomicSet(&rr_options.volume,50);memcpy(pcm,original,sizeof pcm);rr_options_audio(pcm,128,2,0,48000);
    for(int i=0;i<256;++i)assert(pcm[i]==original[i]*50/100);
    SDL_AtomicSet(&rr_options.volume,200);memcpy(pcm,original,sizeof pcm);rr_options_audio(pcm,128,2,0,48000);
    for(int i=0;i<256;++i){int v=original[i]*2;assert(pcm[i]==(v>32767?32767:v<-32768?-32768:v));}
    SDL_AtomicSet(&rr_options.volume,0);memcpy(pcm,original,sizeof pcm);rr_options_audio(pcm,128,2,0,48000);
    for(int i=0;i<256;++i)assert(!pcm[i]);
    /* Floating point output (the device format F32), mono too. */
    float real[64];for(int i=0;i<64;++i)real[i]=(i&1)?.75f:-.25f;
    SDL_AtomicSet(&rr_options.volume,200);rr_options_audio(real,64,1,1,48000);
    for(int i=0;i<64;++i)assert(real[i]==((i&1)?1.0f:-.5f));
    /* Mute and the hold are silence, whatever the volume; only the samples asked for are written. */
    SDL_AtomicSet(&rr_options.volume,100);
    memcpy(pcm,original,sizeof pcm);assert(rr_sound_toggle_mute() && rr_sound_muted());rr_options_audio(pcm,100,2,0,48000);
    for(int i=0;i<200;++i)assert(!pcm[i]);
    assert(pcm[200]==original[200]);
    assert(!rr_sound_toggle_mute());memcpy(pcm,original,sizeof pcm);rr_options_audio(pcm,128,2,0,48000);assert(!memcmp(pcm,original,sizeof pcm));
    SDL_AtomicSet(&rr_options.speed_held,1);rr_options_audio(pcm,128,2,0,48000);
    for(int i=0;i<256;++i)assert(!pcm[i]);
    SDL_AtomicSet(&rr_options.speed_held,0);
    /* Volume and mute are kept in [Fixture.Options], 0..200. */
    rr_sound_set_volume(80);assert(rr_ini_int(rr_options.section,L"audio_volume",-1,rr_options.file)==80);
    rr_sound_set_volume(500);assert(rr_sound_volume()==200);
    rr_sound_toggle_mute();assert(rr_ini_int(rr_options.section,L"audio_muted",-1,rr_options.file)==1);
    rr_sound_load(130,1,"Some Speakers");
    assert(rr_sound_volume()==130 && rr_sound_muted() && !strcmp(rr_sound_device(),"Some Speakers"));
    rr_sound_load(-5,0,NULL);assert(!rr_sound_volume() && !rr_sound_muted() && !rr_sound_device()[0]);
    rr_sound_load(100,0,"");
    /* The options rows: Volume steps by ten and wraps, M is a key row, the device row reports its name. */
    RrOptionRows d=fixture_rows();
    assert(d.keys[2]==RR_ROW_VOLUME && d.keys[3]==SDL_SCANCODE_M && d.keys[4]==RR_ROW_DEVICE);
    rr_options.row=2;rr_sound_set_volume(100);
    assert(page_key(&d,SDL_SCANCODE_RETURN)==-1 && rr_sound_volume()==110);
    assert(page_key(&d,SDL_SCANCODE_MINUS)==-1 && page_key(&d,SDL_SCANCODE_MINUS)==-1 && rr_sound_volume()==90);
    rr_sound_set_volume(200);assert(page_key(&d,SDL_SCANCODE_RETURN)==-1 && !rr_sound_volume());
    assert(page_key(&d,SDL_SCANCODE_MINUS)==-1 && rr_sound_volume()==200);
    rr_sound_set_volume(100);
    rr_options.row=3;assert(page_key(&d,SDL_SCANCODE_RETURN)==SDL_SCANCODE_M && page_key(&d,SDL_SCANCODE_MINUS)==-1);
    /* The device: without the audio subsystem the cycle has only the system default; a stored name shows (ASCII only). */
    unsigned serial=rr_sound_device_serial();
    rr_sound_set_device("Speakers \xc3\xa9");assert(rr_sound_device_serial()==serial+1);
    char label[100];rr_sound_device_label(label,sizeof label);assert(!strcmp(label,"Speakers \xc3\xa9"));
    rr_options.row=4;assert(page_key(&d,SDL_SCANCODE_RETURN)==-1 && !rr_sound_device()[0]);
    rr_sound_device_label(label,sizeof label);assert(!strcmp(label,"System default"));
    rr_sound_set_device("Kept");rr_sound_set_volume(200);rr_options_init(L"Fixture");rr_sound_load(100,0,"");
    assert(rr_ini_int(rr_options.section,L"audio_volume",-1,rr_options.file)==200);
    wchar_t stored[300];rr_ini_get(rr_options.section,L"audio_device",L"?",stored,300,rr_options.file);assert(!wcscmp(stored,L"Kept"));
    rr_remove(rr_options.file);
    /* A preferences file that cannot be written (a read-only install) never blocks a choice: it applies, and the page says so. */
    rr_options.file[0]=0;
    serial=rr_sound_device_serial();
    rr_sound_set_device("Elsewhere");
    assert(!strcmp(rr_sound_device(),"Elsewhere") && rr_sound_device_serial()==serial+1 && !strcmp(rr_options.status,rr_tr("Config unavailable")));
    rr_options.status[0]=0;rr_sound_set_volume(40);
    assert(rr_sound_volume()==40 && !strcmp(rr_options.status,rr_tr("Config unavailable")));
    assert(rr_sound_toggle_mute() && rr_sound_muted());
}
/* F2 pages: control pages, an optional gun page, then the options. */
static void pages(void) {
    RrPages gun={4,1},plain={2,0};int control=-1;
    assert(rr_pages_count(gun)==6 && rr_pages_count(plain)==3);
    assert(rr_pages_index(gun,RR_CONTROLS_MENU,3)==3 && rr_pages_index(gun,RR_GUN_MENU,0)==4 &&
           rr_pages_index(gun,RR_OPTIONS_MENU,0)==5 && rr_pages_index(plain,RR_OPTIONS_MENU,0)==2);
    assert(rr_pages_goto(gun,2,&control)==RR_CONTROLS_MENU && control==2);
    assert(rr_pages_goto(gun,4,&control)==RR_GUN_MENU && !control);
    assert(rr_pages_goto(gun,6,&control)==RR_CONTROLS_MENU && !control);
    assert(rr_pages_goto(gun,-1,&control)==RR_OPTIONS_MENU && rr_pages_goto(plain,-1,&control)==RR_OPTIONS_MENU);
    assert(rr_pages_goto(plain,2,&control)==RR_OPTIONS_MENU && rr_pages_goto(plain,1,&control)==RR_CONTROLS_MENU && control==1);
    SDL_Event e;memset(&e,0,sizeof e);e.type=SDL_KEYDOWN;
    e.key.keysym.scancode=SDL_SCANCODE_TAB;assert(rr_pages_step(&e)==1);
    e.key.keysym.mod=KMOD_LSHIFT;assert(rr_pages_step(&e)==-1);
    e.key.keysym.mod=0;e.key.keysym.scancode=SDL_SCANCODE_LEFT;assert(rr_pages_step(&e)==-1);
    e.key.repeat=1;assert(!rr_pages_step(&e));
    memset(&e,0,sizeof e);e.type=SDL_CONTROLLERBUTTONDOWN;e.cbutton.button=SDL_CONTROLLER_BUTTON_RIGHTSHOULDER;
    assert(rr_pages_step(&e)==1);e.cbutton.button=SDL_CONTROLLER_BUTTON_DPAD_LEFT;assert(rr_pages_step(&e)==-1);
    e.cbutton.button=SDL_CONTROLLER_BUTTON_A;assert(!rr_pages_step(&e));
    /* Function-key rows return their key; Up/Down only move the selection. */
    RrOptionRows d;d.count=0;
    rr_option_row(&d,SDL_SCANCODE_F3,"F3 Filter: %s",rr_option_filter_name(3));
    rr_option_row(&d,SDL_SCANCODE_F12,"%s","F12 Record fallback hints: ON");
    rr_option_shared_rows(&d);
    assert(d.count==6 && !strcmp(d.text[0],"F3 Filter: Scanlines") && d.keys[2]==RR_ROW_AUDIO &&
           !strncmp(d.text[2],"Audio filter: ",14));
    rr_options.row=0;memset(&e,0,sizeof e);e.type=SDL_KEYDOWN;
    e.key.keysym.scancode=SDL_SCANCODE_DOWN;assert(rr_option_page_event(&e,&d)==-1 && rr_options.row==1);
    e.key.keysym.scancode=SDL_SCANCODE_RETURN;assert(rr_option_page_event(&e,&d)==SDL_SCANCODE_F12);
    e.key.keysym.scancode=SDL_SCANCODE_RIGHT;assert(!rr_option_page_event(&e,&d));
    memset(&e,0,sizeof e);e.type=SDL_CONTROLLERBUTTONDOWN;e.cbutton.button=SDL_CONTROLLER_BUTTON_DPAD_UP;
    assert(rr_option_page_event(&e,&d)==-1 && !rr_options.row);
    e.cbutton.button=SDL_CONTROLLER_BUTTON_A;assert(rr_option_page_event(&e,&d)==SDL_SCANCODE_F3);
}
/* Computers: F1-F10 can go to the guest, Ctrl+F1-F12 stay Retro-Recomp's. */
static void computer_keys(void) {
    rr_options_init(L"Fixture");rr_remove(rr_options.file);rr_options_init(L"Fixture");
    RrOptionRows d=fixture_rows();
    assert(d.count==5 && rr_options_host_fkey(SDL_SCANCODE_F3,KMOD_NONE,false));
    rr_options_keyboard("X68000",10);d=fixture_rows();
    assert(d.count==6 && d.keys[5]==RR_ROW_FKEYS && !strcmp(d.text[5],"F1-F10 keys: Retro-Recomp") && !rr_options.fkeys_machine);
    for(int k=SDL_SCANCODE_F1;k<=SDL_SCANCODE_F12;++k)assert(rr_options_host_fkey(k,KMOD_NONE,false));
    assert(!rr_options_host_fkey(SDL_SCANCODE_A,KMOD_LCTRL,false));
    open_options();rr_options.row=5;assert(page_key(&d,SDL_SCANCODE_RETURN)==-1);
    assert(rr_options.fkeys_machine && menu==RR_OPTIONS_MENU);
    d=fixture_rows();assert(!strcmp(d.text[5],"F1-F10 keys: X68000"));
    for(int k=SDL_SCANCODE_F1;k<=SDL_SCANCODE_F10;++k) {
        assert(!rr_options_host_fkey(k,KMOD_NONE,false) && rr_options_host_fkey(k,KMOD_LCTRL,false));
        assert(rr_options_host_fkey(k,KMOD_NONE,true) && !rr_options_host_fkey(k,(SDL_Keymod)(KMOD_LCTRL|KMOD_LALT),false));
    }
    assert(rr_options_host_fkey(SDL_SCANCODE_F11,KMOD_NONE,false) && rr_options_host_fkey(SDL_SCANCODE_F12,KMOD_NONE,false));
    menu=0;
    rr_options_init(L"Fixture");assert(!rr_options.fkeys && rr_options_host_fkey(SDL_SCANCODE_F2,KMOD_NONE,false));
    rr_options_keyboard("X68000",10);assert(rr_options.fkeys_machine && !rr_options_host_fkey(SDL_SCANCODE_F2,KMOD_NONE,false));
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
    sound();sound_controls();chords();pages();rows_survive_copy();computer_keys();
    SDL_Window *win=SDL_CreateWindow("Options fixture",0,0,768,576,SDL_WINDOW_HIDDEN);assert(win);
    SDL_Renderer *ren=SDL_CreateRenderer(win,-1,SDL_RENDERER_SOFTWARE);assert(ren);assert(rr_menu_init(ren));
    SDL_Surface *image=SDL_CreateRGBSurfaceWithFormat(0,768,576,32,SDL_PIXELFORMAT_ARGB8888);assert(image);
    RrOptionRows d;d.count=0;
    rr_option_row(&d,SDL_SCANCODE_F3,"F3 Filter: %s",rr_option_filter_name(1));
    rr_option_row(&d,SDL_SCANCODE_F4,"F4 Display: %s",rr_option_mode_name(2));
    rr_option_shared_rows(&d);
    rr_option_page_draw(ren,&d,5,6);SDL_RenderPresent(ren);
    assert(SDL_RenderReadPixels(ren,NULL,image->format->format,image->pixels,image->pitch)==0);
    assert(SDL_SaveBMP(image,"options.bmp")==0);
    /* Squares at x = 243 - 9 * count + 9 * page, y = 14, six units wide:
     * the current page is the brightest, earlier ones filled, later outlined. */
    Uint32 *pixel=(Uint32*)image->pixels;int stride=image->pitch/4;
#define RR_SQUARE(page,dx,dy) (pixel[(14*3+(dy))*stride+(189+9*(page))*3+(dx)]&0xffffff)
    assert(RR_SQUARE(5,9,9)==0xffde80 && RR_SQUARE(0,9,9)==0xc4a048);
    rr_option_page_draw(ren,&d,4,6);SDL_RenderPresent(ren);
    assert(SDL_RenderReadPixels(ren,NULL,image->format->format,image->pixels,image->pitch)==0);
    assert(RR_SQUARE(4,9,9)==0xffde80 && RR_SQUARE(5,1,1)==0xc4a048 && RR_SQUARE(5,9,9)!=0xc4a048);
#undef RR_SQUARE
    SDL_FreeSurface(image);
    rr_menu_shutdown();SDL_DestroyRenderer(ren);SDL_DestroyWindow(win);SDL_Quit();
    puts("PASS: byte-exact audio bypass, optional tone filters, persistent single keys/buttons and chords, focus/disconnect and virtual controller.");return 0;
}
