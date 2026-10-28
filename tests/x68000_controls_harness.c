/* Original Retro-Recomp SDL input harness, MIT. Includes the actual frontend
 * translation unit (and with it the host kit's adapter) so the static input
 * callbacks are exercised, never a copy; the kit's shell is linked beside it.
 * Virtual gamepads and SDL events are real SDL APIs; the keyboard state is
 * written into SDL's own array (SDL_PushEvent does not change OS keys). */
#include <SDL.h>
#define main rr_unused_frontend_main
#include "../native/x68000_reference/reference_host.c"
/* The kit functions the harness drives directly (clang refuses implicit declarations). */
#include "hostkit/hostkit_internal.h"
#undef main
static unsigned checks,failures;
static bool harness_running=true;
static void check(int okay,const char*name){checks++;if(!okay){failures++;fprintf(stderr,"FAIL: %s\n",name);}}
static Uint8 *held(void){return (Uint8*)SDL_GetKeyboardState(NULL);}
static void release_all(void){memset(held(),0,SDL_NUM_SCANCODES);}
/* What the kit does at the top of a loop iteration: events first (the machine's hook, then hot-plug), then the pad words. */
static void drain(void){
    SDL_Event e;
    while(SDL_PollEvent(&e)){
        if(rrhk_adapter()->event(&e,&harness_running))continue;
        if(e.type==SDL_CONTROLLERDEVICEADDED||e.type==SDL_CONTROLLERDEVICEREMOVED)rrhk_open_pads();
    }
}
static void sample(void){
    xa.pad[0]=input_focus?rrhk_pad_word(0,input_frame):0;xa.pad[1]=input_focus?rrhk_pad_word(1,input_frame):0;
    fast_forward=rrhk_adapter()->fast_forward();
    frame_number++;input_poll();
}
static void next(void){drain();sample();}
static void key_event(SDL_Keycode sym,SDL_Keymod mods){SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_KEYDOWN;e.key.type=SDL_KEYDOWN;e.key.state=SDL_PRESSED;e.key.keysym.sym=sym;e.key.keysym.scancode=SDL_GetScancodeFromKey(sym);e.key.keysym.mod=mods;SDL_PushEvent(&e);next();}
static void focus_event(unsigned kind){SDL_Event e;memset(&e,0,sizeof(e));e.type=SDL_WINDOWEVENT;e.window.event=(Uint8)kind;SDL_PushEvent(&e);next();}
static SDL_JoystickID instance(unsigned p){return rrhk_ui()->pads[p]?SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk_ui()->pads[p])):-1;}
static int joy(unsigned port,unsigned id){return input_state(port,RETRO_DEVICE_JOYPAD,0,id);}
static int guest_key(unsigned id){return input_state(0,RETRO_DEVICE_KEYBOARD,0,id);}
int main(void){
    int first,second;SDL_Joystick*virtual_pad[2]={0};SDL_JoystickID ids[2];unsigned i;
    SDL_SetMainReady();SDL_setenv("SDL_VIDEODRIVER","dummy",1);SDL_setenv("SDL_AUDIODRIVER","dummy",1);
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS,"1");
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER|SDL_INIT_JOYSTICK|SDL_INIT_EVENTS)){fprintf(stderr,"SDL: %s\n",SDL_GetError());return 2;}
    SDL_Window *probe=SDL_CreateWindow("X68000 input test",0,0,64,64,SDL_WINDOW_HIDDEN);
    if(!probe){fprintf(stderr,"SDL window: %s\n",SDL_GetError());return 2;}
    /* The developer may have a real pad plugged in. Remove only its initial
     * enumeration events; this isolated test explicitly opens virtual pads. */
    SDL_FlushEvents(SDL_FIRSTEVENT,SDL_LASTEVENT);
    {wchar_t ini[4096];rr_executable_directory(ini,4000);rr_wide_append(ini,4096,RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini");rr_remove(ini);}
    rrhk_bind(rrhk_adapter());rrhk_load_bindings();rrhk_options_init(L"X68000");rrhk_options_keyboard("X68000",10);
    xa.windowed=true;input_focus=true;release_all();
    check(rrhk_ui()->keys[0][X_A]==SDL_GetScancodeFromKey(SDLK_w)&&rrhk_ui()->keys[0][X_B]==SDL_GetScancodeFromKey(SDLK_x),"unsaved defaults use logical W and X");
    check(rrhk_ui()->buttons[0][X_PAUSE]==X_NO_PAD&&rrhk_ui()->keys[0][X_PAUSE]==SDL_SCANCODE_UNKNOWN&&X_ACTIONS==X_PAUSE+1,"no pause binding by default and no restart row");
    first=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    check(first>=0,"SDL virtual first controller attached");if(first<0)return 2;
    virtual_pad[0]=SDL_JoystickOpen(first);ids[0]=SDL_JoystickInstanceID(virtual_pad[0]);
    rrhk_open_pads();next(); /* Startup scan + queued device-added. */
    check(instance(0)==ids[0]&&instance(1)==-1,"startup enumeration and added event do not duplicate a controller");
    second=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    check(second>=0,"SDL virtual second controller attached");if(second<0)return 2;
    virtual_pad[1]=SDL_JoystickOpen(second);ids[1]=SDL_JoystickInstanceID(virtual_pad[1]);next();
    check(instance(0)==ids[0]&&instance(1)==ids[1]&&ids[0]!=ids[1],"two controller ports have distinct physical identities, dealt in plug order");
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_A,1);
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_B,1);SDL_JoystickUpdate();next();
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_A),"port one virtual A maps to first game button");
    check(joy(1,RETRO_DEVICE_ID_JOYPAD_A)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_B),"port two virtual B maps to second game button independently");
    for(i=0;i<2;i++){
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_LEFTSTICK,1);
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_RIGHTSTICK,1);
        SDL_JoystickSetVirtualButton(virtual_pad[i],SDL_CONTROLLER_BUTTON_BACK,1);
        SDL_JoystickSetVirtualAxis(virtual_pad[i],SDL_CONTROLLER_AXIS_TRIGGERLEFT,32767);
        SDL_JoystickSetVirtualAxis(virtual_pad[i],SDL_CONTROLLER_AXIS_TRIGGERRIGHT,32767);
    }SDL_JoystickUpdate();next();
    for(i=0;i<2;i++)check(!joy(i,RETRO_DEVICE_ID_JOYPAD_L3)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_R3)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_SELECT)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_L2)&&!joy(i,RETRO_DEVICE_ID_JOYPAD_R2),"stick clicks, Select and private menu triggers remain unassigned");
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_A,0);
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_B,0);
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_LEFTSTICK,0);SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_LEFTSTICK,0);
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTX,20000);
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTY,-20000);SDL_JoystickUpdate();next();
    check(joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT)&&joy(1,RETRO_DEVICE_ID_JOYPAD_UP)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_RIGHT),"independent directional axes use the selected controller port");
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTX,15000);SDL_JoystickUpdate();next();
    check(!joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT),"the stick dead zone is the common 16000, not the former 12000");
    SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTX,0);SDL_JoystickSetVirtualAxis(virtual_pad[1],SDL_CONTROLLER_AXIS_LEFTY,0);SDL_JoystickUpdate();
    held()[SDL_SCANCODE_LEFT]=held()[SDL_SCANCODE_RIGHT]=1;next();
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_LEFT)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_RIGHT),"opposite directions cancel, as on every console");
    release_all();held()[SDL_GetScancodeFromKey(SDLK_w)]=1;next();
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_B),"keyboard W is resolved by logical layout and only affects port one");
    check(key_scan(RETROK_z)==(unsigned)SDL_GetScancodeFromKey(SDLK_z),"guest keyboard Z follows SDL logical layout rather than US physical position");
    check(guest_key(RETROK_w)==1&&guest_key(RETROK_z)==0,"logical W and Z stay distinct for guest keyboard");
    /* F8 and F9 belong to the kit unless full typing hands them to the guest. */
    release_all();held()[SDL_SCANCODE_F8]=held()[SDL_SCANCODE_F9]=1;guest_keyboard=false;key_event(SDLK_F8,KMOD_NONE);key_event(SDLK_F9,KMOD_NONE);
    check(!guest_key(RETROK_F8)&&!guest_key(RETROK_F9),"F8 and F9 are reserved for the host's save/load by default");
    held()[SDL_SCANCODE_ESCAPE]=1;
    check(!guest_key(RETROK_ESCAPE),"frontend Escape cannot pause a game after a menu closes");
    key_event(SDLK_k,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));
    check(guest_keyboard&&guest_key(RETROK_F8)&&guest_key(RETROK_F9),"full guest keyboard toggle forwards F8/F9");
    check(guest_key(RETROK_ESCAPE),"full computer typing still includes guest Escape");
    held()[SDL_SCANCODE_F12]=1;
    check(!guest_key(RETROK_F12),"upstream F12 private menu never reaches guest");
    {SDL_Event typed;memset(&typed,0,sizeof(typed));typed.type=SDL_KEYDOWN;typed.key.keysym.scancode=SDL_SCANCODE_ESCAPE;typed.key.keysym.sym=SDLK_ESCAPE;
     check(rrhk_adapter()->event(&typed,&harness_running)&&harness_running,"in full typing a key press belongs to the guest and cannot quit");
     typed.key.keysym.scancode=SDL_SCANCODE_F2;typed.key.keysym.sym=SDLK_F2;
     check(rrhk_adapter()->event(&typed,&harness_running),"in full typing F2 belongs to the guest");
     typed.key.keysym.scancode=SDL_SCANCODE_F1;typed.key.keysym.sym=SDLK_F1;
     check(!rrhk_adapter()->event(&typed,&harness_running),"in full typing F1 still reaches the kit's help");}
    key_event(SDLK_k,(SDL_Keymod)(KMOD_CTRL|KMOD_ALT));
    check(!guest_keyboard,"the same chord returns to game shortcuts");
    release_all();
    /* Autofire: the common rule (decision D4, 28 October 2026): each new press starts on, per button, guest frames. */
    held()[SDL_GetScancodeFromKey(SDLK_w)]=1;rrhk_ui()->autofire=1;input_frame=0;
    xa.pad[0]=rrhk_pad_word(0,input_frame);check(joy(0,RETRO_DEVICE_ID_JOYPAD_B),"autofire: a new press starts on");
    input_frame=1;xa.pad[0]=rrhk_pad_word(0,input_frame);check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B),"autofire: the next guest frame releases");
    input_frame=2;xa.pad[0]=rrhk_pad_word(0,input_frame);check(joy(0,RETRO_DEVICE_ID_JOYPAD_B),"autofire: one pulse per two guest frames");
    input_frame=3;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!guest_key(RETROK_w),"the key bound to the button is the button: both release on the same guest frame");
    input_frame=4;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&guest_key(RETROK_w),"keyboard and joystick share the autofire press phase");
    held()[SDL_GetScancodeFromKey(SDLK_x)]=1;input_frame=5;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_A)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_B),"autofire is per button: a second button pressed later starts on its own");
    release_all();input_frame=7;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_A),"released buttons stay released");
    rrhk_ui()->keys[0][X_A]=SDL_SCANCODE_Q;held()[SDL_SCANCODE_Q]=1;input_frame=1;rrhk_autofire_reset();xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&guest_key(RETROK_q),"a rebound fire key starts on at its own press, whatever the frame parity");
    input_frame=2;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!guest_key(RETROK_q),"rebound fire key also releases both input paths");
    guest_keyboard=true;
    check(guest_key(RETROK_q),"full computer typing is never pulsed");
    guest_keyboard=false;rrhk_ui()->keys[0][X_A]=SDL_GetScancodeFromKey(SDLK_w);release_all();rrhk_ui()->autofire=0;rrhk_autofire_reset();
    /* F5 held accelerates presentation. */
    held()[SDL_SCANCODE_F5]=1;
    check(x_fast_forward(),"holding F5 accelerates presentation without changing guest controls");
    guest_keyboard=true;check(!x_fast_forward(),"full computer keyboard keeps F5 for the guest");
    guest_keyboard=false;rrhk_ui()->menu=1;check(!x_fast_forward(),"menus suppress fast loading");rrhk_ui()->menu=0;
    held()[SDL_SCANCODE_F5]=0;
    loading_holdoff=0;RRLoading loading={0};
    check(!rr_loading_update(&loading,1,123)&&!rr_loading_update(&loading,1,123),"one active transfer does not accelerate a changing scene");
    automatic_loading=rr_loading_update(&loading,1,123)!=0;
    check(automatic_loading&&!x_fast_forward(),"waiting image and disk activity never accelerate playback automatically");
    automatic_loading=rr_loading_update(&loading,0,123)!=0;
    check(!automatic_loading&&!x_fast_forward(),"disk inactivity restores normal speed without user intervention");
    automatic_loading=rr_loading_update(&loading,1,456)!=0;
    check(!automatic_loading,"a changing gameplay image suppresses automatic acceleration");
    automatic_loading=false;
    /* Mouse games: the buttons are the first two buttons, the directions and the stick move the pointer. */
    mouse_game=true;input_frame=1;release_all();rrhk_ui()->autofire=1;rrhk_autofire_reset();
    held()[SDL_GetScancodeFromKey(SDLK_w)]=1;input_frame=0;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT),"mouse-controlled game accepts the bound fire key as the left button");
    input_frame=1;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT),"mouse-controlled first button shares the autofire release phase");
    rrhk_ui()->autofire=0;release_all();held()[SDL_SCANCODE_RIGHT]=1;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)>0,"mouse-controlled game accepts keyboard directions");
    release_all();held()[SDL_SCANCODE_LEFT]=1;xa.pad[0]=rrhk_pad_word(0,input_frame);
    check(input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)<0,"left mouse emulation preserves signed movement");
    mouse_game=false;release_all();xa.pad[0]=0;
    /* The mouse is captured by a click on an unknown computer game, never from a menu. */
    rrhk_ui()->menu=1;mouse_grab=false;
    SDL_Event click;SDL_zero(click);click.type=SDL_MOUSEBUTTONDOWN;click.button.button=SDL_BUTTON_LEFT;
    SDL_PushEvent(&click);next();
    check(!mouse_grab,"a frontend menu never captures the pointer");
    rrhk_ui()->menu=0;SDL_PushEvent(&click);next();
    check(mouse_grab,"clicking an unknown computer game captures its mouse without a hidden shortcut");
    mouse_grab=false;SDL_SetRelativeMouseMode(SDL_FALSE);
    release_all();held()[SDL_SCANCODE_H]=held()[SDL_SCANCODE_P]=1;
    check(guest_key(RETROK_h)&&guest_key(RETROK_p),"H and P reach the guest in ordinary shortcut mode");
    guest_keyboard=true;held()[SDL_SCANCODE_F1]=held()[SDL_SCANCODE_F11]=1;
    check(!guest_key(RETROK_F1)&&!guest_key(RETROK_F11),"help and pause F keys cannot leak into the guest");
    guest_keyboard=false;
    release_all();held()[SDL_GetScancodeFromKey(SDLK_w)]=1;
    SDL_SetModState((SDL_Keymod)(KMOD_CTRL|KMOD_ALT));held()[SDL_SCANCODE_UP]=1;held()[SDL_GetScancodeFromKey(SDLK_h)]=1;next();
    check(!guest_key(RETROK_h)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_B)&&!joy(0,RETRO_DEVICE_ID_JOYPAD_UP),"Ctrl Alt shortcuts are not forwarded as guest keyboard or keyboard joystick input");
    SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_START,1);SDL_JoystickUpdate();next();
    check(guest_key(RETROK_RETURN),"controller Start remains independent from keyboard shortcuts");
    SDL_SetModState(KMOD_NONE);SDL_JoystickSetVirtualButton(virtual_pad[0],SDL_CONTROLLER_BUTTON_START,0);SDL_JoystickUpdate();release_all();
    mouse_grab=true;mouse_dx=12;mouse_dy=-8;mouse_buttons=SDL_BUTTON_LMASK;
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_DPAD_RIGHT,1);SDL_JoystickUpdate();
    focus_event(SDL_WINDOWEVENT_FOCUS_LOST);
    check(!input_focus&&!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_X)&&!input_state(0,RETRO_DEVICE_MOUSE,0,RETRO_DEVICE_ID_MOUSE_LEFT)&&!joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT),"focus loss clears mouse input and suppresses physical gamepads");
    focus_event(SDL_WINDOWEVENT_FOCUS_GAINED);check(input_focus&&joy(1,RETRO_DEVICE_ID_JOYPAD_RIGHT),"SDL focus event restores input focus");
    SDL_JoystickSetVirtualButton(virtual_pad[1],SDL_CONTROLLER_BUTTON_DPAD_RIGHT,0);SDL_JoystickUpdate();
    mouse_grab=false;SDL_GetRelativeMouseState(NULL,NULL);next();
    check(!mouse_dx&&!mouse_dy&&!mouse_buttons,"uncaptured mouse motion and buttons are not forwarded");
    check(!joy(2,RETRO_DEVICE_ID_JOYPAD_MASK),"unconfigured third controller port cannot leak inputs");
    /* Actual removal is processed with the kit's hot-plug, while the host still owns its gamecontroller handle. */
    check(SDL_JoystickDetachVirtual(second)==0,"SDL virtual second device detached while host handle is open");next();
    check(instance(0)==ids[0]&&instance(1)==-1,"device-removed event releases only the corresponding controller slot");
    SDL_JoystickClose(virtual_pad[1]);virtual_pad[1]=NULL;
    rrhk_open_pads();rrhk_open_pads();
    check(instance(0)==ids[0]&&instance(1)==-1,"repeated hotplug enumeration does not duplicate the surviving controller");
    second=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
    virtual_pad[1]=SDL_JoystickOpen(second);ids[1]=SDL_JoystickInstanceID(virtual_pad[1]);next();
    check(instance(0)==ids[0]&&instance(1)==ids[1]&&ids[0]!=ids[1],"new device-added event fills the free second port without reopening the first");
    rrhk_close_pads();
    SDL_JoystickClose(virtual_pad[1]);SDL_JoystickDetachVirtual(second);
    SDL_JoystickClose(virtual_pad[0]);SDL_JoystickDetachVirtual(first);
    SDL_DestroyWindow(probe);SDL_Quit();
    printf("{\"suite\":\"SDL virtual controller and frontend callbacks\",\"checks\":%u,\"failures\":%u,\"keyboard_boundary_injection\":true}\n",checks,failures);
    return failures?1:0;
}
