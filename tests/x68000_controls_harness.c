/* Original Retro-Recomp SDL input harness, MIT. Includes the actual frontend
 * translation unit so static input callbacks are exercised, never a copy.
 * Virtual gamepads and SDL events are real SDL APIs; keyboard scan-state is
 * injected at the callback boundary (SDL_PushEvent does not change OS keys). */
#include <SDL.h>
static int authored_azerty;
static SDL_Scancode authored_scancode(SDL_Keycode key){
    if(authored_azerty){if(key==SDLK_z)return SDL_SCANCODE_W;if(key==SDLK_w)return SDL_SCANCODE_Z;}
    return SDL_GetScancodeFromKey(key);
}
#define SDL_GetScancodeFromKey authored_scancode
#define main rr_unused_frontend_main
#include "../native/x68000_reference/reference_host.c"
#undef main
#undef SDL_GetScancodeFromKey
static unsigned checks,failures;
static uint8_t authored_keys[SDL_NUM_SCANCODES];
static void check(int okay,const char*name){checks++;if(!okay){failures++;fprintf(stderr,"FAIL: %s\n",name);}}
static void poll_next(void){frame_number++;input_poll();keys=authored_keys;}
static void key_event(SDL_Keycode sym,SDL_Keymod mods){SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_KEYDOWN;e.key.type=SDL_KEYDOWN;e.key.state=SDL_PRESSED;e.key.keysym.sym=sym;e.key.keysym.scancode=SDL_GetScancodeFromKey(sym);e.key.keysym.mod=mods;SDL_PushEvent(&e);poll_next();}
static void focus_event(unsigned kind){SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_WINDOWEVENT;e.window.event=(Uint8)kind;SDL_PushEvent(&e);poll_next();}
static SDL_JoystickID instance(unsigned p){return controllers[p]?SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[p])):-1;}
static int joy(unsigned port,unsigned id){return input_state(port,RETRO_DEVICE_JOYPAD,0,id);}
int main(void){
    int first,second;SDL_Joystick*virtual_pad[2]={0};SDL_JoystickID ids[2];unsigned i;int dx,dy;
    SDL_SetMainReady();SDL_setenv("SDL_VIDEODRIVER","dummy",1);SDL_setenv("SDL_AUDIODRIVER","dummy",1);
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS,"1");
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER|SDL_INIT_JOYSTICK|SDL_INIT_EVENTS)){fprintf(stderr,"SDL: %s\n",SDL_GetError());return 2;}
    window=SDL_CreateWindow("X68000 input test",0,0,64,64,SDL_WINDOW_HIDDEN);
    if(!window){fprintf(stderr,"SDL window: %s\n",SDL_GetError());return 2;}
    /* The developer may have a real pad plugged in. Remove only its initial
     * enumeration events; this isolated test explicitly opens virtual pads. */
    SDL_FlushEvents(SDL_FIRSTEVENT,SDL_LASTEVENT);
    first=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    check(first>=0,"SDL virtual first controller attached");if(first<0)return 2;
    virtual_pad[0]=SDL_JoystickOpen(first);ids[0]=SDL_JoystickInstanceID(virtual_pad[0]);
    add_controller(first);poll_next(); /* Startup scan + queued device-added. */
    check(instance(0)==ids[0]&&instance(1)==-1,"startup enumeration and added event do not duplicate a controller");
    second=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    check(second>=0,"SDL virtual second controller attached");if(second<0)return 2;
    virtual_pad[1]=SDL_JoystickOpen(second);ids[1]=SDL_JoystickInstanceID(virtual_pad[1]);poll_next();
    check(instance(0)==ids[0]&&instance(1)==ids[1]&&ids[0]!=ids[1],"two controller ports have distinct physical identities");
    input_focus=true;
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_A,1);
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_B,1);SDL_JoystickUpdate();poll_next();
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_A),"port one virtual A maps to first game button");
    check(joy(1,RETRO_DEVICE_ID_JOYPAD_A)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_B),"port two virtual B maps to second game button independently");
    for(i=0;i<2;i++){
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_LEFTSTICK,1);
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_RIGHTSTICK,1);
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_BACK,1);
        SDL_JoystickSetVirtualAxis(virtual_pad[i],SDL_CONTROLLER_AXIS_TRIGGERLEFT,32767);
        SDL_JoystickSetVirtualAxis(virtual_pad[i],SDL_CONTROLLER_AXIS_TRIGGERRIGHT,32767);
    }SDL_JoystickUpdate();poll_next();
    for(i=0;i<2;i++)check(!joy(i,RETRO_DEVICE_ID_JOYPAD_L3)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_R3)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_SELECT)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_L2)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_R2),"stick clicks, Select and private menu triggers remain unassigned");
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_A,0);
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_B,0);
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTX,20000);
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTY,-20000);SDL_JoystickUpdate();poll_next();
    check(joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT)&&joy(1,RETRO_DEVICE_ID_JOYPAD_UP)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_RIGHT),"independent directional axes use the selected controller port");
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_GetScancodeFromKey(SDLK_w)]=1;
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_B),"keyboard W is resolved by logical layout and only affects port one");
    check(key_scan(RETROK_z)==(unsigned)SDL_GetScancodeFromKey(SDLK_z),"guest keyboard Z follows SDL logical layout rather than US physical position");
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_GetScancodeFromKey(SDLK_w)]=1;
    check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_w)==1&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_z)==0,"logical W and Z stay distinct for guest keyboard");
    authored_azerty=1;memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_SCANCODE_W]=1;
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_z)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_w),"authored AZERTY layout keeps logical Z distinct from the default W fire button");
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_SCANCODE_Z]=1;
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_w)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_z),"authored AZERTY layout resolves physical Z-position to logical W for keyboard and fire");authored_azerty=0;
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_SCANCODE_F8]=authored_keys[SDL_SCANCODE_F9]=1;
    want_save=want_load=false;guest_keyboard=false;key_event(SDLK_F8,KMOD_NONE);key_event(SDLK_F9,KMOD_NONE);
    check(want_save&&want_load&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F8)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F9),"F8 and F9 are reserved for host save/load by default");
    authored_keys[SDL_SCANCODE_ESCAPE]=1;
    check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"frontend Escape cannot pause a game after a menu closes");
    want_save=want_load=false;key_event(SDLK_k,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));key_event(SDLK_F8,KMOD_NONE);key_event(SDLK_F9,KMOD_NONE);
    check(guest_keyboard&&!want_save&&!want_load&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F8)&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F9),"full guest keyboard toggle forwards F8/F9 and disables host save/load shortcuts");
    check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_ESCAPE),"full computer typing still includes guest Escape");
    authored_keys[SDL_SCANCODE_F12]=1;
    check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F12),"upstream F12 private menu never reaches guest");
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_GetScancodeFromKey(SDLK_w)]=1;
    key_event(SDLK_f,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));input_frame=0;
    check(autofire&&joy(0,RETRO_DEVICE_ID_JOYPAD_B),"rapid fire keeps held first button on even guest frames");input_frame=1;
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B),"rapid fire releases held first button on alternate guest frames");input_frame=2;
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B),"rapid fire repeats at maximum one pulse per two guest frames");
    guest_keyboard=false;input_frame=1;
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_w),"keyboard and joystick both release: games combining them can rapid fire");
    input_frame=2;
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_w),"keyboard and joystick share the rapid fire press phase");
    player_defaults();player_ui.ready=1;player_ui.key[0][X_A]=SDL_SCANCODE_Q;
    memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_SCANCODE_Q]=1;input_frame=1;
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_q),"rebound fire key also releases both input paths");
    guest_keyboard=true;
    check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_q),"full computer typing is never pulsed");
    guest_keyboard=false;authored_keys[SDL_SCANCODE_F5]=1;
    check(player_fast_forward(),"holding F5 accelerates presentation without changing guest controls");
    guest_keyboard=true;check(!player_fast_forward(),"full computer keyboard keeps F5 for the guest");
    guest_keyboard=false;player_ui.menu=1;check(!player_fast_forward(),"menus suppress fast loading");player_ui.menu=0;
    authored_keys[SDL_SCANCODE_F5]=0;
    loading_holdoff=0;RRLoading loading={0};
    check(!rr_loading_update(&loading,1,123)&&!rr_loading_update(&loading,1,123),"one active transfer does not accelerate a changing scene");
    automatic_loading=rr_loading_update(&loading,1,123)!=0;
    check(automatic_loading&&!player_fast_forward(),"waiting image and disk activity never accelerate playback automatically");
    automatic_loading=rr_loading_update(&loading,0,123)!=0;
    check(!automatic_loading&&!player_fast_forward(),"disk inactivity restores normal speed without user intervention");
    automatic_loading=rr_loading_update(&loading,1,456)!=0;
    check(!automatic_loading,"a changing gameplay image suppresses automatic acceleration");
    automatic_loading=true;loading_holdoff=2;
    check(!player_fast_forward(),"interaction can interrupt acceleration without being required to stop it");
    loading_holdoff=0;
    key_event(SDLK_F5,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));
    check(!player_fast_forward(),"the former auto-loading shortcut cannot re-enable automatic acceleration");
    automatic_loading=false;
    mouse_game=true;authored_keys[SDL_SCANCODE_F5]=0;input_frame=1;
    check(!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT),"mouse-controlled first button shares rapid fire release phase");
    input_frame=2;check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT),"mouse-controlled game accepts rebound keyboard fire");
    authored_keys[SDL_SCANCODE_Q]=0;authored_keys[SDL_SCANCODE_RIGHT]=1;
    check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)>0,"mouse-controlled game accepts keyboard directions");
    authored_keys[SDL_SCANCODE_RIGHT]=0;authored_keys[SDL_SCANCODE_LEFT]=1;
    check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)<0,"left mouse emulation preserves signed movement");
    mouse_game=false;
    player_ui.capture=-1;player_ui.menu=1;mouse_grab=false;
    SDL_Event click;SDL_zero(click);click.type=SDL_MOUSEBUTTONDOWN;click.button.button=SDL_BUTTON_LEFT;
    SDL_PushEvent(&click);poll_next();
    check(!mouse_grab,"a frontend menu never captures the pointer");
    player_ui.menu=0;SDL_PushEvent(&click);poll_next();
    check(mouse_grab,"clicking an unknown computer game captures its mouse without a hidden shortcut");
    mouse_grab=false;SDL_SetRelativeMouseMode(SDL_FALSE);
    memset(authored_keys,0,sizeof(authored_keys));
    authored_keys[SDL_SCANCODE_H]=authored_keys[SDL_SCANCODE_P]=1;
    check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_h)&&input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_p),"H and P reach the guest in ordinary shortcut mode");
    guest_keyboard=true;authored_keys[SDL_SCANCODE_F1]=authored_keys[SDL_SCANCODE_F11]=1;
    check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F1)&&!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_F11),"help and pause F keys cannot leak into the guest");
    guest_keyboard=false;
    player_ui.ready=0;guest_keyboard=false;memset(authored_keys,0,sizeof(authored_keys));authored_keys[SDL_GetScancodeFromKey(SDLK_w)]=1;
    SDL_SetModState((SDL_Keymod)(KMOD_CTRL|KMOD_ALT));authored_keys[SDL_SCANCODE_UP]=1;
    authored_keys[SDL_GetScancodeFromKey(SDLK_h)]=1;
    check(!input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_h)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_UP),"Ctrl Alt shortcuts are not forwarded as guest keyboard or keyboard joystick input");
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_START,1);SDL_JoystickUpdate();poll_next();
    check(input_state(0,RETRO_DEVICE_KEYBOARD,0,RETROK_RETURN),"controller Start remains independent from keyboard shortcuts");
    SDL_SetModState(KMOD_NONE);SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_START,0);SDL_JoystickUpdate();
    mouse_grab=true;mouse_dx=12;mouse_dy=-8;mouse_buttons=SDL_BUTTON_LMASK;
    focus_event(SDL_WINDOWEVENT_FOCUS_LOST);
    check(!input_focus&&!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)&&!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT),"focus loss clears mouse input and suppresses physical gamepads");
    focus_event(SDL_WINDOWEVENT_FOCUS_GAINED);check(input_focus,"SDL focus event restores input focus");
    mouse_grab=false;SDL_GetRelativeMouseState(&dx,&dy);poll_next();
    check(!mouse_dx&&!mouse_dy&&!mouse_buttons,"uncaptured mouse motion and buttons are not forwarded");
    check(!joy(2,RETRO_DEVICE_ID_JOYPAD_MASK),"unconfigured third controller port cannot leak inputs");
    /* Actual removal is processed by input_poll, while the host still owns its
     * gamecontroller handle; then a new virtual physical identity fills it. */
    check(SDL_JoystickDetachVirtual(second)==0,"SDL virtual second device detached while host handle is open");poll_next();
    check(instance(0)==ids[0]&&instance(1)==-1,"device-removed event releases only the corresponding controller slot");
    SDL_JoystickClose(virtual_pad[1]);virtual_pad[1]=NULL;
    add_controller(first);add_controller(first);
    check(instance(0)==ids[0]&&instance(1)==-1,"repeated hotplug enumeration does not duplicate the surviving controller");
    second=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    virtual_pad[1]=SDL_JoystickOpen(second);ids[1]=SDL_JoystickInstanceID(virtual_pad[1]);poll_next();
    check(instance(0)==ids[0]&&instance(1)==ids[1]&&ids[0]!=ids[1],"new device-added event fills the free second port without reopening the first");
    for(i=0;i<2;i++)if(controllers[i]){SDL_GameControllerClose(controllers[i]);controllers[i]=NULL;}
    SDL_JoystickClose(virtual_pad[1]);SDL_JoystickDetachVirtual(second);
    SDL_JoystickClose(virtual_pad[0]);SDL_JoystickDetachVirtual(first);
    SDL_DestroyWindow(window);window=NULL;SDL_Quit();
    printf("{\"suite\":\"SDL virtual controller and frontend callbacks\",\"checks\":%u,\"failures\":%u,\"keyboard_boundary_injection\":true}\n",checks,failures);
    return failures?1:0;
}
