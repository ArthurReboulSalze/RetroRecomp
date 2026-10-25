"""Compile the real seven console input readers against authored SDL inputs.

No cartridge, firmware, window, sound or gameplay measurement is involved.
The fixture substitutes keyboard state; gamepads are real SDL virtual devices.
"""
from pathlib import Path
import argparse
import ast
import json
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrorecomp.platforms import sdl_install
from retrorecomp.paths import ROOT, ASSETS
from retrorecomp.core import toolchain, run
from retrorecomp.platforms import cmake_target_args, build_executable


def function(source, name):
    start=source.index(name+'(')
    start=source.rfind('\n',0,start)+1
    opened=source.index('{',start);depth=1;end=opened+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


PREAMBLE='''#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include "autofire.h"
#include "retro_keyboard.h"
static Uint8 held_keys[SDL_NUM_SCANCODES];
static uint64_t fixture_frame;
static const Uint8 *fixture_keyboard(int *n) {(void)n;return held_keys;}
#define SDL_GetKeyboardState fixture_keyboard
'''

TEST='''
int main(void) {
    SDL_SetMainReady();assert(SDL_Init(SDL_INIT_GAMECONTROLLER)==0);
    SDL_Joystick *stick[2]={0};
    setup();
    for(int p=0;p<PLAYERS;++p) {
        int index=SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER,SDL_CONTROLLER_AXIS_MAX,SDL_CONTROLLER_BUTTON_MAX,0);
        assert(index>=0);pads[p]=SDL_GameControllerOpen(index);assert(pads[p]);
        stick[p]=SDL_GameControllerGetJoystick(pads[p]);
        for(int a=0;a<ACTIONS;++a)assert(binding(p,a)!=SDL_CONTROLLER_BUTTON_LEFTSTICK && binding(p,a)!=SDL_CONTROLLER_BUTTON_RIGHTSTICK);
    }
    for(int device=0;device<2;++device) {
        clear_fire();autofire=1;
        for(int p=0;p<PLAYERS;++p)for(int a=0;a<ACTIONS;++a) {
            if(device)assert(SDL_JoystickSetVirtualButton(stick[p],binding(p,a),1)==0);
            else keyboard(p,a,1);
        }
        SDL_GameControllerUpdate();
        for(uint64_t f=100;f<220;++f)for(int p=0;p<PLAYERS;++p) {
            uint16_t value=sample(p,f);
            assert((value&FIRE_MASK)==(!(f&1)?FIRE_MASK:0));
            for(int repeat=0;repeat<5;++repeat)assert(sample(p,f)==value);
        }
        /* Paused guest, then a rewind within an already held press. */
        assert(!(sample(0,219)&FIRE_MASK));
        assert((sample(0,150)&FIRE_MASK)==FIRE_MASK);
        autofire=0;
        for(int p=0;p<PLAYERS;++p)assert((sample(p,151)&FIRE_MASK)==FIRE_MASK);
        for(int p=0;p<PLAYERS;++p)for(int a=0;a<ACTIONS;++a) {
            if(device)assert(SDL_JoystickSetVirtualButton(stick[p],binding(p,a),0)==0);
            else keyboard(p,a,0);
        }
        SDL_GameControllerUpdate();
        for(int p=0;p<PLAYERS;++p)assert(!(sample(p,152)&FIRE_MASK));
    }
    /* Stick clicks have no default assignment, but explicit bindings work. */
    for(int button=SDL_CONTROLLER_BUTTON_LEFTSTICK;button<=SDL_CONTROLLER_BUTTON_RIGHTSTICK;++button) {
        remap(0,FIRST_FIRE,button);autofire=0;
        assert(SDL_JoystickSetVirtualButton(stick[0],button,1)==0);SDL_GameControllerUpdate();
        assert(sample(0,300)&FIRST_MASK);
        autofire=1;clear_fire();assert(sample(0,301)&FIRST_MASK);
        assert(!(sample(0,302)&FIRST_MASK));
        assert(SDL_JoystickSetVirtualButton(stick[0],button,0)==0);SDL_GameControllerUpdate();
        assert(!(sample(0,303)&FIRST_MASK));
    }
    SDL_Quit();puts("PASS keyboard/gamepad rapid fire, both players, stable reads, pause, rewind, off/release, assignable L3/R3 without defaults");return 0;
}
'''


def source(system, test=TEST):
    """The fixture's C source: the console's real declarations and reader, then `test`."""
    if system in ('ng','cps1','md','snes','nes'):
        path='nes_host_ui.c' if system=='nes' else 'console16_host_ui.c'
        text=(ASSETS/'native'/path).read_text()
        first=text.index('enum { A, B, SELECT') if system=='nes' else text.index('#if RR16_NG\nenum')
        declarations=text[first:text.index('static wchar_t ini_file',first)]
        reader=function(text,'controller_input')
        definitions=(f'#define RR16_NG {int(system=="ng")}\n#define RR16_CPS1 {int(system=="cps1")}\n#define RR16_MD {int(system=="md")}\n'
                     f'#define RR16_PLAYERS {4 if system=="cps1" else 2}\n#define rr16_players() RR16_PLAYERS\n#define RR_MD_SIX_BUTTONS 1\n')
        setup='''
static int autofire;
#define PLAYERS 2
#define FIRST_FIRE A
#define FIRST_MASK bits[A]
#define FIRE_MASK fire_mask()
static uint16_t fire_mask(void) {uint16_t n=0;for(int a=A;a<=LAST_FIRE;++a)n|=bits[a];return n;}
static void setup(void) {}
static void clear_fire(void) {memset(fire_state,0,sizeof fire_state);}
static int binding(int p,int a) {return buttons[p][a];}
static void remap(int p,int a,int b) {buttons[p][a]=(SDL_GameControllerButton)b;}
static void keyboard(int p,int a,int down) {held_keys[keys[p][a]]=(Uint8)down;}
static uint16_t sample(int p,uint64_t frame) {return controller_input(p,frame);}
'''.replace('LAST_FIRE','B' if system=='nes' else 'FACE_LAST')
        return PREAMBLE+definitions+declarations+'\nstatic int autofire;\n'+reader+setup+test
    if system in ('sms','gg'):
        text=(ASSETS/'native/controls.c').read_text()
        declarations=text[text.index('static SDL_Scancode default_keys'):text.index('const char *controls_text')]
        setup='''
static SDL_GameController *pads[2];
#define PLAYERS 2
#define FIRST_FIRE 4
#define FIRST_MASK SMS_PAD_B1
#define FIRE_MASK (SMS_PAD_B1|SMS_PAD_B2)
#define ACTIONS 6
#define autofire controls.autofire
uint64_t glue_frame_count(void) {return fixture_frame;}
static void setup(void) {memcpy(controls.keys,default_keys,sizeof default_keys);memcpy(controls.buttons,default_buttons,sizeof default_buttons);}
static void clear_fire(void) {controls_reset_autofire();}
static int binding(int p,int a) {return controls.buttons[p][a];}
static void remap(int p,int a,int b) {controls.buttons[p][a]=(SDL_GameControllerButton)b;}
static void keyboard(int p,int a,int down) {held_keys[controls.keys[p][a]]=(Uint8)down;}
static uint16_t sample(int p,uint64_t frame) {fixture_frame=frame;return read_controls(p,pads[p],true,held_keys);}
'''
        return PREAMBLE+('#define RETRO_GAME_GEAR 1\n' if system=='gg' else '')+'''#include "controls.h"
enum {SMS_PAD_UP=1,SMS_PAD_DOWN=2,SMS_PAD_LEFT=4,SMS_PAD_RIGHT=8,SMS_PAD_B1=16,SMS_PAD_B2=32,SMS_PAD_START=64};
Controls controls;
uint64_t glue_frame_count(void);
'''+declarations+function(text,'read_controls')+setup+test
    # Exercise the exact checked replacement emitted into the GB SDL runtime.
    code=(ROOT/'retrorecomp/gameboy_host.py').read_text()
    tree=ast.parse(code)
    replacements=[node.args[2].value for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='replace_once' and len(node.args)>2
        and isinstance(node.args[1],ast.Constant) and isinstance(node.args[1].value,str)
        and node.args[1].value.startswith('    if (input_action_is_pressed(GB_INPUT_ACTION_START))')]
    assert len(replacements)==1
    upstream=(ROOT/'.deps/gb-recompiled/runtime/src/platform_sdl.cpp').read_text()
    reader=function(upstream,'rebuild_manual_joypad_state_from_bindings')
    marker='    if (input_action_is_pressed(GB_INPUT_ACTION_START)) g_manual_joypad_buttons &= (uint8_t)~0x08;\n}'
    assert reader.count(marker)==1
    reader=reader.replace(marker,replacements[0])
    return PREAMBLE+'''
enum {GB_INPUT_ACTION_A,GB_INPUT_ACTION_B,GB_INPUT_ACTION_SELECT,GB_INPUT_ACTION_START,GB_INPUT_ACTION_UP,GB_INPUT_ACTION_DOWN,GB_INPUT_ACTION_LEFT,GB_INPUT_ACTION_RIGHT};
typedef int GBInputAction;
static SDL_GameController *pads[2];
static SDL_GameControllerButton buttons[8]={SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_BACK,SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT};
static bool g_keyboard_binding_pressed[8][2],g_controller_button_binding_pressed[8][2],g_controller_axis_binding_pressed[8][2];
static uint8_t g_manual_joypad_dpad,g_manual_joypad_buttons;
static RrAutofire g_rr_fire[2];static uint64_t g_rr_input_frame;static bool g_rr_autofire;
'''+function(upstream,'input_action_is_pressed')+reader+'''
#define PLAYERS 1
#define ACTIONS 8
#define FIRST_FIRE 0
#define FIRST_MASK 1
#define FIRE_MASK 3
#define autofire g_rr_autofire
static void setup(void) {}
static void clear_fire(void) {memset(g_rr_fire,0,sizeof g_rr_fire);}
static int binding(int p,int a) {(void)p;return buttons[a];}
static void remap(int p,int a,int b) {(void)p;buttons[a]=(SDL_GameControllerButton)b;}
static void keyboard(int p,int a,int down) {(void)p;g_keyboard_binding_pressed[a][0]=down!=0;}
static uint16_t sample(int p,uint64_t frame) {
    g_rr_input_frame=frame;
    for(int a=0;a<8;++a)g_controller_button_binding_pressed[a][0]=SDL_GameControllerGetButton(pads[p],buttons[a])!=0;
    rebuild_manual_joypad_state_from_bindings();return (uint8_t)~g_manual_joypad_buttons;
}
'''+test


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'.build/autofire-selftest')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    systems=('sms','gg','gb','nes','md','snes','ng','cps1')
    for system in systems:(out/(system+'.c')).write_text(source(system),encoding='utf-8')
    cmake,generator=toolchain();sdl=sdl_install()
    targets='\n'.join(f'add_executable({s} {s}.c)\ntarget_include_directories({s} PRIVATE "{(ASSETS/"native").as_posix()}")\ntarget_link_libraries({s} PRIVATE SDL2::SDL2-static)' for s in systems)
    (out/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(AutofireChecks C)\nfind_package(SDL2 REQUIRED CONFIG)\n'+targets+'\n')
    log=out/'build.log'
    run([cmake,'-S',out,'-B',out/'build','-G',generator,*cmake_target_args(),f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],log=log)
    run([cmake,'--build',out/'build','--config','Release','--parallel','4'],log=log)
    results={}
    env=dict(os.environ,SDL_AUDIODRIVER='dummy',SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS='1')
    for system in systems:
        result=subprocess.run([str(build_executable(out/'build',system))],env=env,capture_output=True,text=True,timeout=30)
        results[system]={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        print(system,result.returncode,result.stdout.strip(),result.stderr,flush=True)
    (out/'results.json').write_text(json.dumps(results,indent=2))
    assert all(row['exit_code']==0 for row in results.values()),results

if __name__=='__main__':main()
