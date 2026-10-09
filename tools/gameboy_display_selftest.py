"""Exercise actual generated GB menus/preferences using SDL's dummy driver."""
from pathlib import Path
import argparse,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from smsrecomp.core import run,toolchain
def check(project):
    source=project/'rr_display_checks.cpp'
    source.write_text('''#define SDL_MAIN_HANDLED
#undef NDEBUG
#include <cassert>
#include "runtime/src/platform_sdl.cpp"
extern "C" void gb_dispatch(GBContext *, uint16_t) { assert(false && "No guest CPU in display fixture"); }
int main() {
    SDL_SetMainReady(); assert(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_TIMER)==0);
    load_runtime_preferences();
    const fs::path path(runtime_preferences_path());
    assert(!fs::exists(path.parent_path()));
    assert(!g_fullscreen && g_render_filter_mode==GB_RENDER_FILTER_NEAREST);
    g_window=SDL_CreateWindow("Dummy settings fixture",0,0,160,144,SDL_WINDOW_HIDDEN);
    g_renderer=SDL_CreateRenderer(g_window,-1,SDL_RENDERER_SOFTWARE);
    assert(g_window && g_renderer);
    for (int cycle=0;cycle<6;++cycle) {
        rr_gb_cycle_fullscreen();
        int mode=(cycle+1)%3;
        load_runtime_preferences();
        assert(g_fullscreen==(mode!=0));
        assert(g_render_scaling_mode==(mode==2 ? GB_RENDER_SCALING_ASPECT_FIT : GB_RENDER_SCALING_PIXEL_PERFECT));
    }
    for (int cycle=0;cycle<8;++cycle) {
        rr_gb_cycle_filter(); load_runtime_preferences();
        assert((int)g_render_filter_mode==(cycle+1)%4);
    }
    rr_gb_palette_change(); load_runtime_preferences(); assert(g_palette_idx==0);
    g_rr_language=1; g_rr_autofire=true; save_runtime_preferences();
    g_rr_language=0; g_rr_autofire=false; load_runtime_preferences();
    assert(g_rr_language==1 && g_rr_autofire);
    assert(g_keyboard_bindings[GB_INPUT_ACTION_START][0].code==SDL_SCANCODE_RETURN);
    assert(g_keyboard_bindings[GB_INPUT_ACTION_SELECT][0].code==SDL_SCANCODE_LSHIFT);
    SDL_DestroyRenderer(g_renderer); SDL_DestroyWindow(g_window); SDL_Quit();
    puts("PASS: GB actual F3/F4 menu actions, all display modes/filters retained, palette/language/autofire, lazy initial read; dummy driver only.");
    return 0;
}
''',encoding='utf-8')
    cmakefile=project/'CMakeLists.txt'; cmaketext=cmakefile.read_text()
    addition='''
add_executable(rr_display_checks rr_display_checks.cpp)
target_link_libraries(rr_display_checks PRIVATE gbrt)
target_compile_options(rr_display_checks PRIVATE /utf-8)
'''
    if 'add_executable(rr_display_checks' not in cmaketext:
        cmakefile.write_text(cmaketext+addition,encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build'],log=project/'display-checks-build.log')
    run([cmake,'--build',project/'build','--target','rr_display_checks','--config','Release','--parallel','4'],log=project/'display-checks-build.log')
    with tempfile.TemporaryDirectory(prefix='rr-gb-display-') as temp:
        exe=Path(temp)/'checks.exe'; shutil.copy2(project/'build/Release/rr_display_checks.exe',exe)
        env=os.environ.copy(); env['SDL_VIDEODRIVER']='dummy'; env['SDL_AUDIODRIVER']='dummy'
        result=subprocess.run([exe],env=env,capture_output=True,text=True,timeout=30)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)
        print(result.stdout.strip())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('generated_project',type=Path)
    check(p.parse_args().generated_project.resolve())
