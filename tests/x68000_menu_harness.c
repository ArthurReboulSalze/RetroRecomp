/* Original Retro-Recomp, MIT. Real SDL/software-rendered common player menus. */
#define main rr_unused_frontend_main
#include "../native/x68000_reference/reference_host.c"
#undef main
static unsigned checks,failures;
static void check(int okay,const char *name){checks++;if(!okay){failures++;fprintf(stderr,"FAIL: %s\n",name);}}
static int option_row(int key){RrOptionRows d=player_option_rows();for(int i=0;i<d.count;i++)if(d.keys[i]==key)return i;return -1;}
static void send_key(SDL_Keycode key,SDL_Keymod mod){
    SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_KEYDOWN;e.key.keysym.sym=key;
    e.key.keysym.scancode=SDL_GetScancodeFromKey(key);e.key.keysym.mod=mod;
    frame_number++;SDL_PushEvent(&e);input_poll();
    e.type=SDL_KEYUP;frame_number++;SDL_PushEvent(&e);input_poll();
}
/* Closing a menu re-primes output: the device plays once a start reserve of
 * guest PCM is queued again, never on an empty queue. */
static int resumes_after_priming(void){
    static int16_t pcm[800*2];
    int paused_first=SDL_GetAudioDeviceStatus(audio_device)==SDL_AUDIO_PAUSED;
    for(int n=0;n<8&&SDL_GetAudioDeviceStatus(audio_device)!=SDL_AUDIO_PLAYING;n++)player_queue_audio(pcm,800);
    return paused_first&&SDL_GetAudioDeviceStatus(audio_device)==SDL_AUDIO_PLAYING;
}
int main(int argc,char **argv){
    int verify=argc>1&&!strcmp(argv[1],"--verify");wchar_t path[4096];
    SDL_SetMainReady();SDL_setenv("SDL_VIDEODRIVER","dummy",1);SDL_setenv("SDL_AUDIODRIVER","dummy",1);
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_AUDIO|SDL_INIT_EVENTS|SDL_INIT_GAMECONTROLLER))return 2;
    window=SDL_CreateWindow("X68000 menus",0,0,768,576,SDL_WINDOW_HIDDEN);
    renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);if(!renderer)return 2;
    SDL_FlushEvents(SDL_FIRSTEVENT,SDL_LASTEVENT);
    rr_executable_directory(path,4000);rr_wide_append(path,4096,RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini");
    if(!verify)rr_remove(path);
    check(player_init(),"shared font atlas and options initialize");
    SDL_AudioSpec spec;SDL_zero(spec);spec.freq=44100;spec.format=AUDIO_S16SYS;spec.channels=2;spec.samples=512;
    audio_device=SDL_OpenAudioDevice(NULL,0,&spec,NULL,0);
    check(audio_device!=0,"queued audio device opens for menu pause and resume checks");
    SDL_PauseAudioDevice(audio_device,0);
    if(verify){
        check(player_ui.filter==3,"scanlines persist across a fresh process");
        check(player_ui.display==1,"pixel display mode persists across a fresh process");
        check(rr_language_get()==1,"language persists across a fresh process");
        check(player_ui.pad[0][X_PAUSE]==SDL_CONTROLLER_BUTTON_LEFTSTICK,"explicit L3 assignment persists");
        check(SDL_AtomicGet(&rr_options.audio_mode)==1,"optional audio filter persists");
        check(player_ui.key[0][X_A]==SDL_GetScancodeFromKey(SDLK_z),"explicit fire binding overrides the new W default after restart");
    }else{
        check(player_ui.pad[0][X_PAUSE]<0&&X_ACTIONS==X_PAUSE+1,"no pause on stick clicks by default and no restart row");
        check(player_ui.key[0][X_A]==SDL_GetScancodeFromKey(SDLK_w)&&player_ui.key[0][X_B]==SDL_GetScancodeFromKey(SDLK_x),"unsaved defaults use logical W and X");
        send_key(SDLK_h,KMOD_NONE);send_key(SDLK_p,KMOD_NONE);
        check(!player_blocked(),"H and P remain available to computer games instead of opening help or pause");
        send_key(SDLK_F11,KMOD_NONE);check(player_ui.paused&&player_blocked(),"F11 pauses without consuming a letter key");
        send_key(SDLK_F11,KMOD_NONE);check(!player_blocked(),"F11 resumes without requiring a letter key");
        send_key(SDLK_F1,KMOD_NONE);check(player_ui.menu==1&&player_blocked(),"F1 opens help and pauses guest execution");
        check(SDL_GetAudioDeviceStatus(audio_device)==SDL_AUDIO_PAUSED,"help pauses the audio device");
        send_key(SDLK_F1,KMOD_NONE);
        check(!player_blocked()&&!quit_requested&&resumes_after_priming(),"F1 closes help and resumes the guest; audio plays once re-primed");
        send_key(SDLK_F1,KMOD_NONE);
        send_key(SDLK_TAB,KMOD_NONE);check(player_ui.help_page==1,"Tab exposes computer keyboard and disk shortcuts");
        send_key(SDLK_ESCAPE,KMOD_NONE);check(!player_blocked()&&!quit_requested,"Escape closes help without quitting");
        check(resumes_after_priming(),"Escape resumes the audio device once re-primed");
        send_key(SDLK_F1,KMOD_NONE);
        SDL_Event esc;SDL_zero(esc);esc.type=SDL_KEYDOWN;esc.key.keysym.scancode=SDL_SCANCODE_ESCAPE;esc.key.keysym.sym=SDLK_ESCAPE;
        player_event(&esc);
        check(!player_blocked()&&player_ui.escape_held&&!quit_requested,"menu Escape is consumed until release");
        player_event(&esc);esc.key.repeat=1;player_event(&esc);
        check(!quit_requested,"held menu Escape cannot become a quit event");
        static Uint8 held_keys[SDL_NUM_SCANCODES];held_keys[SDL_SCANCODE_ESCAPE]=1;keys=held_keys;
        guest_keyboard=true;
        check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"menu Escape never leaks into the full guest keyboard");
        esc.type=SDL_KEYUP;player_event(&esc);
        check(!player_ui.escape_held&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"release restores ordinary guest Escape handling");
        guest_keyboard=false;keys=SDL_GetKeyboardState(NULL);
        send_key(SDLK_F2,KMOD_NONE);check(player_ui.menu==2,"F2 opens actual controls menu");
        player_ui.row=X_A;send_key(SDLK_RETURN,KMOD_NONE);send_key(SDLK_z,KMOD_NONE);
        check(player_ui.key[0][X_A]==SDL_GetScancodeFromKey(SDLK_z),"F2 can still assign Z explicitly instead of default W");
        send_key(SDLK_F2,KMOD_NONE);
        check(!player_blocked()&&resumes_after_priming(),"F2 closes controls and resumes the guest; audio plays once re-primed");
        send_key(SDLK_F1,KMOD_NONE);send_key(SDLK_F2,KMOD_NONE);
        check(player_ui.menu==2,"F2 switches directly from help to controls");
        send_key(SDLK_F1,KMOD_NONE);check(player_ui.menu==1,"F1 switches directly from controls to help");
        send_key(SDLK_F2,KMOD_NONE);
        send_key(SDLK_TAB,KMOD_NONE);check(player_ui.menu==2&&player_ui.player==1,"the next F2 page is the independent second player");
        send_key(SDLK_LEFT,KMOD_NONE);check(player_ui.menu==2&&player_ui.player==0,"Left returns to the first player page");
        player_ui.row=X_PAUSE;send_key(SDLK_RETURN,KMOD_NONE);
        SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_CONTROLLERBUTTONDOWN;e.cbutton.button=SDL_CONTROLLER_BUTTON_LEFTSTICK;
        check(player_event(&e)&&player_ui.pad[0][X_PAUSE]==SDL_CONTROLLER_BUTTON_LEFTSTICK,"L3 can be explicitly captured as pause");
        e.type=SDL_CONTROLLERBUTTONUP;player_event(&e);
        send_key(SDLK_ESCAPE,KMOD_NONE);
        send_key(SDLK_F3,KMOD_NONE);check(player_ui.filter==2,"first filter after pixels is Scale2x");
        send_key(SDLK_F3,KMOD_NONE);check(player_ui.filter==3,"next filter is proportional scanlines");
        send_key(SDLK_F3,KMOD_NONE);check(player_ui.filter==1,"xBR is last in the filter cycle");
        send_key(SDLK_F3,KMOD_NONE);check(player_ui.filter==0,"filter cycle returns to clean pixels");
        send_key(SDLK_F4,KMOD_NONE);check(player_ui.display==1,"F4 chooses pixel perfect fullscreen");
        send_key(SDLK_F7,KMOD_NONE);check(rr_language_get()==1,"F7 cycles language");
        for(int i=1;i<RR_LANGUAGE_COUNT;i++)send_key(SDLK_F7,KMOD_NONE);
        check(rr_language_get()==0,"every game language cycles back to English");
        send_key(SDLK_F10,KMOD_NONE);check(!player_ui.menu,"F10 is free");
        send_key(SDLK_F2,KMOD_NONE);send_key(SDLK_LEFT,KMOD_NONE);
        check(player_ui.menu==RR_OPTIONS_MENU&&player_page()==2,"the options are the last F2 page");
        rr_options.row=option_row(RR_ROW_AUDIO);send_key(SDLK_RETURN,KMOD_NONE);
        check(SDL_AtomicGet(&rr_options.audio_mode)==1,"audio filtering is optional and selectable on the options page");
        rr_options.row=0;send_key(SDLK_RETURN,KMOD_NONE);check(player_ui.filter==2&&player_ui.menu==RR_OPTIONS_MENU,"an option row runs its function key");
        for(int i=0;i<3;i++)send_key(SDLK_RETURN,KMOD_NONE);
        check(player_ui.filter==0,"the filter row cycles back to clean pixels");
        send_key(SDLK_ESCAPE,KMOD_NONE);check(!player_ui.menu,"options close without quitting");
        /* Quit and restart combinations close player 1's page. */
        send_key(SDLK_F2,KMOD_NONE);send_key(SDLK_UP,KMOD_NONE);check(player_ui.row==X_ACTIONS+1,"restart is the last row of player 1");
        send_key(SDLK_UP,KMOD_NONE);send_key(SDLK_RETURN,KMOD_NONE);
        check(rr_options.capture==1&&rr_options.armed,"Enter captures the keyboard quit combination");
        send_key(SDLK_END,KMOD_NONE);check(!rr_options.capture&&rr_options.key[0]==SDL_SCANCODE_END,"the keyboard quit combination is stored");
        send_key(SDLK_DELETE,KMOD_NONE);check(!rr_options.key[0],"Delete clears it");
        send_key(SDLK_RIGHT,KMOD_NONE);check(player_ui.player==1&&player_ui.row==X_ACTIONS-1,"player 2's page has no combination rows");
        send_key(SDLK_ESCAPE,KMOD_NONE);
        /* Option: F1-F10 to the X68000; Ctrl+F1-F12 stay Retro-Recomp's. */
        check(rr_options.fkeys==10&&!rr_options.fkeys_machine,"function keys stay Retro-Recomp's by default");
        send_key(SDLK_F2,KMOD_NONE);send_key(SDLK_LEFT,KMOD_NONE);rr_options.row=option_row(RR_ROW_FKEYS);send_key(SDLK_RETURN,KMOD_NONE);
        check(rr_options.fkeys_machine,"the options row hands F1-F10 to the X68000");
        send_key(SDLK_ESCAPE,KMOD_NONE);
        {
            static Uint8 fkey_state[SDL_NUM_SCANCODES];fkey_state[SDL_SCANCODE_F2]=1;keys=fkey_state;
            check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F2)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F12),
                "F2 reaches the X68000, which has no F12");
            keys=SDL_GetKeyboardState(NULL);
        }
        send_key(SDLK_F2,KMOD_NONE);check(!player_ui.menu,"plain F2 stays with the X68000");
        want_save=false;send_key(SDLK_F8,KMOD_NONE);check(!want_save,"plain F8 stays with the X68000");
        send_key(SDLK_F8,KMOD_LCTRL);check(want_save,"Ctrl+F8 saves the game state");want_save=false;
        send_key(SDLK_F2,KMOD_LCTRL);check(player_ui.menu==2,"Ctrl+F2 opens the F2 pages");
        send_key(SDLK_F2,KMOD_NONE);check(!player_ui.menu,"inside a menu F2 closes it without Ctrl");
        send_key(SDLK_F11,KMOD_NONE);check(player_ui.paused,"F11, absent from the X68000, still pauses");
        send_key(SDLK_F11,KMOD_NONE);
        send_key(SDLK_F2,KMOD_LCTRL);send_key(SDLK_LEFT,KMOD_NONE);rr_options.row=option_row(RR_ROW_FKEYS);send_key(SDLK_RETURN,KMOD_NONE);
        check(!rr_options.fkeys_machine,"the row returns F1-F10 to Retro-Recomp");
        send_key(SDLK_ESCAPE,KMOD_NONE);
        send_key(SDLK_F1,KMOD_SHIFT);check(player_ui.want_reset&&!player_ui.menu,"Shift F1 queues a restart between guest frames at once");
        player_ui.want_reset=0;
        send_key(SDLK_k,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));want_save=false;send_key(SDLK_F8,KMOD_NONE);
        check(guest_keyboard&&!want_save,"computer typing keeps guest F8 independent from snapshots");
        send_key(SDLK_h,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));check(player_ui.menu==1,"explicit computer chord regains host help");
        send_key(SDLK_ESCAPE,KMOD_NONE);send_key(SDLK_k,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));
        send_key(SDLK_F8,KMOD_NONE);send_key(SDLK_F9,KMOD_NONE);check(want_save&&want_load,"game mode restores F8/F9 snapshot requests");
        static uint16_t pixels[256*192];for(int i=0;i<256*192;i++)pixels[i]=(uint16_t)i;
        for(int lang=0;lang<RR_LANGUAGE_COUNT;lang++){
            rr_language_set(lang);player_ui.menu=1;player_present(pixels,256,192,512);
            player_ui.menu=2;player_present(pixels,256,192,512);
            player_ui.menu=RR_OPTIONS_MENU;player_present(pixels,256,192,512);
        }
        check(!core_error,"all shared menu pages render in every game language");
        rr_language_set(0);player_ui.menu=2;player_present(pixels,256,192,512);
        {
            int w,h;SDL_GetRendererOutputSize(renderer,&w,&h);
            SDL_Surface *preview=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_ARGB8888);
            char *base=SDL_GetBasePath(),name[4096];snprintf(name,sizeof(name),"%smenu-preview.bmp",base?base:"");
            check(preview&&SDL_RenderReadPixels(renderer,NULL,preview->format->format,preview->pixels,preview->pitch)==0&&SDL_SaveBMP(preview,name)==0,"menu preview captured from the actual SDL renderer");
            if(preview)SDL_FreeSurface(preview);SDL_free(base);
        }
        player_ui.menu=0;player_ui.filter=3;player_store(L"filter",3);rr_language_set(0);player_language();
        rr_options.key[0]=SDL_SCANCODE_Q;rr_options.key[1]=rr_options.key[2]=0;
        rr_options.down[SDL_SCANCODE_Q]=1;rr_options.focused=1;rr_options.suppressed=0;
        (void)player_ui_quit();rr_options.hold=SDL_GetTicks64()-1100;
        check(player_ui_quit(),"held quit chord triggers without waiting for another SDL event");
    }
    player_shutdown();SDL_CloseAudioDevice(audio_device);SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
    printf("{\"checks\":%u,\"failures\":%u,\"fresh_process\":%s}\n",checks,failures,verify?"true":"false");
    return failures?1:0;
}
