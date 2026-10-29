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


SIXTEEN_BIT_SETUP='''
#include "hostkit/hostkit.h"
@TABLE@
static int players(void) {return @PLAYERS@;}
static RrhkMachine machine;
const char *rr_translate(int language,const char *english,const char *french) {(void)language;(void)french;return english;}
const char *rr_tr(const char *english) {return english;}
int rr_language_from_wide(const wchar_t *code) {(void)code;return 0;}
const wchar_t *rr_language_wide(int language) {(void)language;return L"en";}
void rr_language_set(int language) {(void)language;}
#include "platform_io.c"
#include "hostkit/shell/rrhk_input.c"
#define keys rrhk.keys
#define buttons rrhk.buttons
#define pads rrhk.pads
#define autofire rrhk.autofire
#ifndef PLAYERS
#define PLAYERS 2
#endif
#define FIRST_FIRE @FIRST@
#define FIRST_MASK bits[@FIRST@]
#define FIRE_MASK fire_mask()
static uint16_t bits[ACTIONS];
static uint16_t fire_mask(void) {uint16_t n=0;for(int a=0;a<ACTIONS;++a)if(actions[a].group==RRHK_FACE)n|=bits[a];return n;}
static void setup(void) {
    machine=(RrhkMachine){.ini_section=L"Fixture",.table_players=@PLAYERS@,.players=players,.actions=actions,.action_count=ACTIONS};
    for(int a=0;a<ACTIONS;++a) {
        bits[a]=actions[a].bit;
        if(!strcmp(actions[a].name,"Up"))machine.up=a;
        if(!strcmp(actions[a].name,"Down"))machine.down=a;
        if(!strcmp(actions[a].name,"Left"))machine.left=a;
        if(!strcmp(actions[a].name,"Right"))machine.right=a;
        if(!strcmp(actions[a].name,"Start"))machine.start=a;
    }
    rrhk_bind(&machine);
}
static void clear_fire(void) {rrhk_autofire_reset();}
static int binding(int p,int a) {return buttons[p][a];}
static void remap(int p,int a,int b) {buttons[p][a]=(SDL_GameControllerButton)b;}
static void keyboard(int p,int a,int down) {held_keys[keys[p][a]]=(Uint8)down;}
static uint16_t sample(int p,uint64_t frame) {return rrhk_pad_word(p,frame);}
'''


def sixteen_bit(system, test):
    """The host kit's own input module and the machine's own action table (the 16-bit consoles and the NES), against a mock keyboard.

    The table is cut from the adapter's source (the Mega Drive one in its six-button form) and the kit's
    rrhk_input.c is compiled as it is; the names keep the vocabulary of the other fixtures."""
    adapter='rrhk_gb.inc' if system=='gb' else f'rrhk_{"sms" if system=="gg" else system}.c'
    text=(ASSETS/'native/hostkit/adapters'/adapter).read_text()
    first={'md':'#define DIRECTIONS','cps1':'#define PADS','sms':'#ifdef RETRO_GAME_GEAR\nenum','gg':'#ifdef RETRO_GAME_GEAR\nenum','gb':'enum { RR_GB_UP'}.get(system,'enum {')
    start=text.index(first)
    if system=='gb':
        # The Game Boy table is the adapter's (the one the runtime's platform layer includes), under the fixture's names.
        table='#define PLAYERS 1\n'+text[start:text.index('\n};',text.index('rr_gb_actions[RR_GB_ACTIONS]'))+3].replace('rr_gb_actions','actions').replace('RR_GB_ACTIONS','ACTIONS')
    elif system in ('sms','gg'):
        # The Master System / Game Gear table builds on the runner's pad byte and chooses the console with RETRO_GAME_GEAR.
        table=('#define RETRO_GAME_GEAR 1\n' if system=='gg' else '')+'enum {SMS_PAD_UP=1,SMS_PAD_DOWN=2,SMS_PAD_LEFT=4,SMS_PAD_RIGHT=8,SMS_PAD_B1=16,SMS_PAD_B2=32,SMS_PAD_START=64};\n'+\
            text[start:text.index('\n};',text.index('actions[ACTIONS]'))+3]
    elif system=='md':
        end=text.index('#endif',text.index('actions[',start))+len('#endif')
        table='#define RR_MD_SIX_BUTTONS 1\n'+text[start:end]
    else:
        table=text[start:text.index('};',text.index('actions[',start))+2]
    setup=SIXTEEN_BIT_SETUP.replace('@TABLE@',table).replace('@PLAYERS@','PLAYERS' if system in ('sms','gg','gb') else '4' if system=='cps1' else '2')
    setup=setup.replace('@FIRST@','BUTTON1' if system in ('sms','gg') else 'RR_GB_A' if system=='gb' else 'A')
    return PREAMBLE+setup+test


def source(system, test=TEST):
    """The fixture's C source: the console's real declarations and reader, then `test`."""
    if system in ('md','snes','ng','cps1','nes','sms','gg','gb'):
        return sixteen_bit(system, test)
    raise SystemExit(f'unknown console {system}')


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
