"""Compile the real console input readers: Enter is Start, either Shift is Select.

No cartridge, window or sound: the fixture substitutes SDL's keyboard state,
exactly as tools/autofire_selftest.py does, around each console's own
declarations and reader or, for every console, the host kit input module with the action table of the adapter
(the Master System and Game Gear share one table, the Game Boy's is in rrhk_gb.inc). The Game Boy's registers are checked
against the generated runtime by gb_latency_checks.cpp; the Master System pad has no Start button (Enter pauses
in the adapter, checked by host_checks.c).
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrorecomp.paths import ROOT, ASSETS
from retrorecomp.core import toolchain, run
from retrorecomp.platforms import cmake_target_args, build_executable, sdl_install
from autofire_selftest import source


# START_KEY / SHIFT_KEY / OTHER_KEY / P2_KEY are the console's own binding
# slots (lvalues); SHIFT_* name the action Shift serves on that console.
SYSTEMS={
    'gg':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SINGLE_PLAYER 1
''',
    'gb':'''#define START_KEY keys[0][RR_GB_START]
#define START_MASK bits[RR_GB_START]
#define SHIFT_KEY keys[0][RR_GB_SELECT]
#define SHIFT_MASK bits[RR_GB_SELECT]
#define OTHER_KEY keys[0][RR_GB_B]
#define OTHER_MASK bits[RR_GB_B]
#define SINGLE_PLAYER 1
#define P2_KEY keys[1][RR_GB_UP]
#define P2_MASK bits[RR_GB_UP]
''',
    'nes':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SHIFT_KEY keys[0][SELECT]
#define SHIFT_MASK bits[SELECT]
#define OTHER_KEY keys[0][B]
#define OTHER_MASK bits[B]
''',
    'md':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SHIFT_KEY keys[0][MODE]
#define SHIFT_MASK bits[MODE]
#define OTHER_KEY keys[0][Z]
#define OTHER_MASK bits[Z]
''',
    'snes':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SHIFT_KEY keys[0][SELECT]
#define SHIFT_MASK bits[SELECT]
#define OTHER_KEY keys[0][Y]
#define OTHER_MASK bits[Y]
''',
    'ng':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SHIFT_KEY keys[0][COIN]
#define SHIFT_MASK bits[COIN]
#define OTHER_KEY keys[0][D]
#define OTHER_MASK bits[D]
''',
    'cps1':'''#define START_KEY keys[0][START]
#define START_MASK bits[START]
#define SHIFT_KEY keys[0][COIN]
#define SHIFT_MASK bits[COIN]
#define OTHER_KEY keys[0][Z]
#define OTHER_MASK bits[Z]
''',
}
for system in ('nes','md','snes','ng','cps1'):
    SYSTEMS[system]+='#define P2_KEY keys[1][UP]\n#define P2_MASK bits[UP]\n#define P2_START_KEY keys[1][START]\n'

TEST='''
int main(void) {
    SDL_SetMainReady();assert(SDL_Init(SDL_INIT_GAMECONTROLLER)==0);setup();
    memset(held_keys,0,sizeof held_keys);
    assert(sample(0,1)==0);
    /* Enter is the cartridge Start; player 2 keeps its keypad key. */
    assert(START_KEY==SDL_SCANCODE_RETURN);
    held_keys[SDL_SCANCODE_RETURN]=1;assert(sample(0,2)==START_MASK);held_keys[SDL_SCANCODE_RETURN]=0;
#ifndef SINGLE_PLAYER
    assert(P2_START_KEY==SDL_SCANCODE_KP_ENTER || P2_START_KEY==SDL_SCANCODE_KP_7);
    held_keys[P2_START_KEY]=1;assert(sample(0,3)==0 && sample(1,3)==START_MASK);held_keys[P2_START_KEY]=0;
#endif
#ifdef SHIFT_MASK
    /* Shift is Select (coin, Mode): either Shift, left or right. */
    assert(SHIFT_KEY==SDL_SCANCODE_LSHIFT || SHIFT_KEY==SDL_SCANCODE_RSHIFT);
    held_keys[SDL_SCANCODE_LSHIFT]=1;assert(sample(0,4)==SHIFT_MASK && sample(1,4)==0);held_keys[SDL_SCANCODE_LSHIFT]=0;
    held_keys[SDL_SCANCODE_RSHIFT]=1;assert(sample(0,5)==SHIFT_MASK && sample(1,5)==0);held_keys[SDL_SCANCODE_RSHIFT]=0;
    held_keys[SDL_SCANCODE_LSHIFT]=held_keys[SDL_SCANCODE_RSHIFT]=1;assert(sample(0,6)==SHIFT_MASK);
    held_keys[SDL_SCANCODE_LSHIFT]=held_keys[SDL_SCANCODE_RSHIFT]=0;
    /* The other Shift bound to another action, of any player: no alias. */
    SDL_Scancode other=rr_keyboard_shift_twin(SHIFT_KEY),saved=OTHER_KEY;
    held_keys[other]=1;
    OTHER_KEY=other;assert(sample(0,7)==OTHER_MASK);OTHER_KEY=saved;
    assert(sample(0,8)==SHIFT_MASK);
    saved=P2_KEY;P2_KEY=other;assert(sample(0,9)==0 && sample(1,9)==P2_MASK);P2_KEY=saved;
    assert(sample(0,10)==SHIFT_MASK);
    held_keys[other]=0;
    /* A Shift moved to another action takes its twin along. */
    SDL_Scancode shift_saved=SHIFT_KEY;SHIFT_KEY=SDL_SCANCODE_J;
    saved=START_KEY;START_KEY=SDL_SCANCODE_RSHIFT;held_keys[SDL_SCANCODE_LSHIFT]=1;
    assert(sample(0,11)==START_MASK);
    START_KEY=saved;SHIFT_KEY=shift_saved;held_keys[SDL_SCANCODE_LSHIFT]=0;
#endif
    assert(sample(0,12)==0);
    SDL_Quit();puts("PASS Enter = Start, player 2 keypad Start, either Shift = Select/coin unless the other Shift is bound");return 0;
}
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'.build/start-select-selftest')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for system,macros in SYSTEMS.items():(out/(system+'.c')).write_text(source(system,macros+TEST),encoding='utf-8')
    cmake,generator=toolchain();sdl=sdl_install()
    targets='\n'.join(f'add_executable({s} {s}.c)\ntarget_include_directories({s} PRIVATE "{(ASSETS/"native").as_posix()}")\ntarget_link_libraries({s} PRIVATE SDL2::SDL2-static)' for s in SYSTEMS)
    (out/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(StartSelectChecks C)\nfind_package(SDL2 REQUIRED CONFIG)\n'+targets+'\n')
    log=out/'build.log'
    run([cmake,'-S',out,'-B',out/'build','-G',generator,*cmake_target_args(),f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],log=log)
    run([cmake,'--build',out/'build','--config','Release','--parallel','4'],log=log)
    results={}
    env=dict(os.environ,SDL_AUDIODRIVER='dummy',SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS='1')
    for system in SYSTEMS:
        result=subprocess.run([str(build_executable(out/'build',system))],env=env,capture_output=True,text=True,timeout=30)
        results[system]={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        print(system,result.returncode,result.stdout.strip(),result.stderr,flush=True)
    (out/'results.json').write_text(json.dumps(results,indent=2))
    assert all(row['exit_code']==0 for row in results.values()),results

if __name__=='__main__':main()
