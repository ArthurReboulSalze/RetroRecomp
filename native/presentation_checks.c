/* Numeric/input checks only: no video driver, window, rendering or capture. */
#undef NDEBUG
#include <assert.h>
#include "host_control.h"
#include "scanlines.h"
#include "include/sms_runtime.h"
static uint64_t test_time_us;
#define smsrecomp_input_time_us() test_time_us
#include "controls.c"

static int fake_x = 30, fake_y = 40, fake_w = 800, fake_h = 600;
static int fullscreen_calls, fail_fullscreen;
static void test_position(SDL_Window *w, int *x, int *y) { (void)w; *x=fake_x; *y=fake_y; }
static void test_size(SDL_Window *w, int *x, int *y) { (void)w; *x=fake_w; *y=fake_h; }
static void set_position(SDL_Window *w, int x, int y) { (void)w; fake_x=x; fake_y=y; }
static void set_size(SDL_Window *w, int x, int y) { (void)w; fake_w=x; fake_h=y; }
static int set_fullscreen(SDL_Window *w, uint32_t flags) {
    (void)w; fullscreen_calls++;
    if (fail_fullscreen) return -1;
    if (flags) { assert(flags == SDL_WINDOW_FULLSCREEN_DESKTOP); fake_x=fake_y=0; fake_w=1920; fake_h=1080; }
    return 0;
}
#define SDL_GetWindowPosition test_position
#define SDL_GetWindowSize test_size
#define SDL_SetWindowPosition set_position
#define SDL_SetWindowSize set_size
#define SDL_SetWindowFullscreen set_fullscreen
#include "host.c"
#undef SDL_GetWindowPosition
#undef SDL_GetWindowSize
#undef SDL_SetWindowPosition
#undef SDL_SetWindowSize
#undef SDL_SetWindowFullscreen
#undef smsrecomp_input_time_us

static void key(SDL_Scancode key, int repeat) {
    SDL_Event event; SDL_zero(event); event.type=SDL_KEYDOWN;
    event.key.keysym.scancode=key; event.key.repeat=(uint8_t)repeat;
    assert(handle_event(&event));
}
static void sizes(void) {
    const int outputs[][2] = {{1920,1080},{2560,1440},{3440,1440},{720,1280},{800,600},{503,389},{319,201},{200,130}};
    full_crop = crop = (SDL_Rect){0,0,256,192};
    int k; SDL_Rect r = game_rect(1920,1080,&k);
    assert(r.w==1280 && r.h==960 && k==5);
    key(SDL_SCANCODE_F4,0); assert(fullscreen && !fullscreen_fit && fullscreen_calls==1);
    key(SDL_SCANCODE_F4,1); assert(fullscreen && !fullscreen_fit && fullscreen_calls==1);
    key(SDL_SCANCODE_F4,0); assert(fullscreen && fullscreen_fit && fullscreen_calls==1);
    r=game_rect(1920,1080,&k); assert(r.w==1440 && r.h==1080 && r.x==240 && r.y==0);
    for (int border=0; border<=8; border+=8) for (unsigned i=0; i<sizeof(outputs)/sizeof(outputs[0]); ++i) {
        crop=(SDL_Rect){border,0,256-border,192};
        int ow=outputs[i][0], oh=outputs[i][1], gx, gy;
        for (int filter=0; filter<FILTER_COUNT; ++filter) {
            controls.filter=filter; r=game_rect(ow,oh,&k);
            assert(r.w<=ow && r.h<=oh && (r.w==ow || r.h==oh));
            assert(abs(r.w*crop.h-r.h*crop.w)<256);
            assert(r.x==(ow-r.w)/2 && r.y==(oh-r.h)/2);
            assert(gun_coordinates(r.x,r.y,ow,oh,ow,oh,&gx,&gy) && gx==border && gy==0);
            assert(!gun_coordinates(r.x-1,r.y,ow,oh,ow,oh,&gx,&gy));
            assert(!gun_coordinates(r.x+r.w,r.y,ow,oh,ow,oh,&gx,&gy));
            assert(!gun_coordinates(r.x,r.y+r.h,ow,oh,ow,oh,&gx,&gy));
            assert(gun_coordinates(r.x+r.w-1,r.y+r.h-1,ow,oh,ow,oh,&gx,&gy));
            assert(gx==border+(r.w-1)*crop.w/r.w && gy==(r.h-1)*crop.h/r.h);
        }
    }
    crop=full_crop; controls.filter=FILTER_NEAREST;
    int gx,gy; assert(gun_coordinates(480,270,960,540,1920,1080,&gx,&gy) && gx==128 && gy==96);
    fail_fullscreen=1; key(SDL_SCANCODE_F4,0); assert(fullscreen && fullscreen_fit);
    fail_fullscreen=0; key(SDL_SCANCODE_F4,0); assert(!fullscreen && !fullscreen_fit);
    assert(fake_x==30 && fake_y==40 && fake_w==800 && fake_h==600);
    puts("PASS: F4 window/integer/fit cycle, repeated keys, failed transition, restored window, four filters/eight display sizes, aspect and HiDPI/cropped gun coordinates.");
}
static void scanlines(void) {
    const int rows[] = {192, 224, 240, 448};
    for (unsigned n = 0; n < sizeof(rows) / sizeof(rows[0]); ++n) {
        int source = rows[n];
        /* Native display stays untouched. A 3x pixel is two bright output
         * rows and one translucent gap, rather than a discarded game row. */
        unsigned bands = 0;
        for (int y = 0; y < source * 3; ++y) {
            assert(rr_scanline_alpha(y, source * 3, source) == (y % 3 == 2 ? 85 : 0));
            if (rr_scanline_alpha(y, source * 3, source)) ++bands;
        }
        assert(bands == (unsigned)source);
        for (int y = 0; y < source; ++y) assert(!rr_scanline_alpha(y, source, source));
    }
    const int heights[] = {448, 672, 720, 896, 1008, 1080, 1440, 2160};
    for (unsigned n = 0; n < sizeof(heights) / sizeof(heights[0]); ++n) {
        unsigned total = 0;
        for (int y = 0; y < heights[n]; ++y) {
            unsigned alpha = rr_scanline_alpha(y, heights[n], 224);
            assert(alpha <= 85); total += alpha;
        }
        /* Fractional zoom retains the same average brightness within the
         * half-alpha rounding allowance of each physical output pixel. */
        assert(abs((int)(total * 3) - heights[n] * 85) <= heights[n] * 3 / 2);
    }
    assert(!rr_scanline_alpha(0, 0, 224));
    assert(!rr_scanline_alpha(-1, 672, 224));
    assert(!rr_scanline_alpha(672, 672, 224));
    assert(!rr_scanline_alpha(0, 672, 0));
    puts("PASS: CRT gaps follow each guest row; native image intact, 3x detail preserved, fractional/fullscreen zoom brightness stable.");
}
static void autofire(void) {
    SDL_VirtualJoystickDesc desc; SDL_zero(desc);
    desc.version=SDL_VIRTUAL_JOYSTICK_DESC_VERSION; desc.type=SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    desc.naxes=SDL_CONTROLLER_AXIS_MAX; desc.nbuttons=SDL_CONTROLLER_BUTTON_MAX;
    desc.axis_mask=(1u<<SDL_CONTROLLER_AXIS_MAX)-1; desc.button_mask=(1u<<SDL_CONTROLLER_BUTTON_MAX)-1;
    desc.name="Authored virtual gamepad";
    int devices[2]; SDL_GameController *pads_test[2]; SDL_Joystick *sticks[2];
    for (int p=0;p<2;++p) {
        devices[p]=SDL_JoystickAttachVirtualEx(&desc); assert(devices[p]>=0);
        pads_test[p]=SDL_GameControllerOpen(devices[p]); assert(pads_test[p]);
        sticks[p]=SDL_GameControllerGetJoystick(pads_test[p]);
        assert(SDL_JoystickSetVirtualButton(sticks[p],SDL_CONTROLLER_BUTTON_A,1)==0);
        assert(SDL_JoystickSetVirtualButton(sticks[p],SDL_CONTROLLER_BUTTON_B,1)==0);
        assert(SDL_JoystickSetVirtualButton(sticks[p],SDL_CONTROLLER_BUTTON_DPAD_RIGHT,1)==0);
    }
    SDL_GameControllerUpdate(); uint8_t keys[SDL_NUM_SCANCODES]={0};
    assert(!controls.autofire && controls.language==0);
    key(SDL_SCANCODE_F6,0); assert(controls.autofire && controls.language==0);
    key(SDL_SCANCODE_F6,1); assert(controls.autofire);
    controls_load(); assert(controls.autofire);
    unsigned pressed[2]={0}, pulses[2]={0}; bool was_pressed[2]={false};
    /* Half-millisecond samples include the exact 12.5 ms release boundary. */
    for (test_time_us=0;test_time_us<1000000;test_time_us+=500) for(int p=0;p<2;++p) {
        uint8_t value=read_controls(p,pads_test[p],true,keys);
        assert((value&SMS_PAD_RIGHT) && !(value&(SMS_PAD_UP|SMS_PAD_DOWN|SMS_PAD_LEFT)));
        assert((value&(SMS_PAD_B1|SMS_PAD_B2))==(test_time_us%25000<12500 ? SMS_PAD_B1|SMS_PAD_B2 : 0));
        bool down=(value&SMS_PAD_B1)!=0;
        if(down) { pressed[p]++; if(!was_pressed[p]) pulses[p]++; }
        was_pressed[p]=down;
    }
    assert(pressed[0]==1000 && pressed[1]==1000);
    assert(pulses[0]==40 && pulses[1]==40);
    test_time_us=1012500; keys[controls.keys[0][4]]=1;
    assert((read_controls(0,pads_test[0],true,keys)&(SMS_PAD_B1|SMS_PAD_B2))==SMS_PAD_B1);
    memset(keys,0,sizeof(keys)); assert(!read_controls(0,pads_test[0],false,keys));
    assert((read_controls(0,pads_test[0],true,keys)&(SMS_PAD_B1|SMS_PAD_B2))==(SMS_PAD_B1|SMS_PAD_B2));
    test_time_us=1013000;
    assert(SDL_JoystickSetVirtualButton(sticks[1],SDL_CONTROLLER_BUTTON_A,0)==0); SDL_GameControllerUpdate();
    assert(!(read_controls(1,pads_test[1],true,keys)&SMS_PAD_B1));
    assert(SDL_JoystickSetVirtualButton(sticks[1],SDL_CONTROLLER_BUTTON_A,1)==0); SDL_GameControllerUpdate();
    assert(read_controls(1,pads_test[1],true,keys)&SMS_PAD_B1); /* new press immediate, other button remains off */
    assert(!(read_controls(1,pads_test[1],true,keys)&SMS_PAD_B2));
    assert(controls_bind(0,4,true,SDL_CONTROLLER_BUTTON_X));
    assert(SDL_JoystickSetVirtualButton(sticks[0],SDL_CONTROLLER_BUTTON_X,1)==0); SDL_GameControllerUpdate();
    controls_reset_autofire(); assert(read_controls(0,pads_test[0],true,keys)&SMS_PAD_B1);
    test_time_us+=12500; assert(!(read_controls(0,pads_test[0],true,keys)&SMS_PAD_B1));
    /* Time is frozen in a pause; repeated samples cannot accelerate pulses. */
    for(int i=0;i<100;++i) assert(!(read_controls(0,pads_test[0],true,keys)&SMS_PAD_B1));
    /* A guest rewind must not underflow the held-button phase. */
    test_time_us=0; assert(read_controls(0,pads_test[0],true,keys)&SMS_PAD_B1);
    key(SDL_SCANCODE_F6,0); assert(!controls.autofire && controls.language==0);
    assert((read_controls(0,pads_test[0],true,keys)&(SMS_PAD_B1|SMS_PAD_B2))==(SMS_PAD_B1|SMS_PAD_B2));
    key(SDL_SCANCODE_F7,0); assert(controls.language==1 && !controls.autofire);
    key(SDL_SCANCODE_F7,0); assert(controls.language==0);
    for(int p=1;p>=0;--p) { SDL_GameControllerClose(pads_test[p]); assert(SDL_JoystickDetachVirtual(devices[p])==0); }
    puts("PASS: F6 autofire/F7 language, both players/buttons, forty pulses per simulated second, balanced 12.5 ms phases, immediate/released presses, remapping, keyboard/focus and shared INI; frozen pause and safe rewind.");
}
int main(int argc,char **argv) {
    assert(argc==2 && SDL_Init(SDL_INIT_GAMECONTROLLER|SDL_INIT_TIMER)==0);
    assert(MultiByteToWideChar(CP_UTF8,0,argv[1],-1,config_path,RETRO_PATH_CAP));
    controls_load(); window=(SDL_Window*)(uintptr_t)1;
    sizes(); scanlines(); autofire(); window=NULL;
    menu=3; parent_menu=1; capturing=true;
    key(SDL_SCANCODE_F8,0); assert(menu==0 && parent_menu==0 && !capturing);
    menu=3; key(SDL_SCANCODE_F9,1); assert(menu==3);
    key(SDL_SCANCODE_F9,0); assert(menu==0);
    _putenv_s("SMSRECOMP_REFERENCE","1"); menu=3;
    key(SDL_SCANCODE_F8,0); assert(menu==3); _putenv_s("SMSRECOMP_REFERENCE","");
    deadline=123; input_sample_counter=456; previous_interpreter_state=2;
    state_completed(RR_QUICKLOAD,RR_STATE_OK);
    assert(!deadline && !input_sample_counter && previous_interpreter_state==-1);
    puts("PASS: F8/F9 keyboard requests, repeat suppression, pause exit, unsupported reference mode and load pacing reset; no video initialized.");
    g_z80.cyc=3579545ULL; assert(smsrecomp_input_time_us()==1000000);
    g_z80.cyc=3579545ULL*1000000000ULL; assert(smsrecomp_input_time_us()==1000000000000000ULL);
    g_z80.cyc=(3579545ULL+79)/80; assert(smsrecomp_input_time_us()==12500);
    g_z80.cyc--; assert(smsrecomp_input_time_us()==12499);
    SDL_Quit(); return 0;
}
