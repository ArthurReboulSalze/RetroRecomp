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
    SDL_SetMainReady();
    SDL_SetHintWithPriority(SDL_HINT_RENDER_DRIVER, "software", SDL_HINT_OVERRIDE);
    assert(gb_platform_init(1));
    const fs::path path(runtime_preferences_path());
    assert(path.filename()=="Retro-Recomp-GameBoy.ini" && path.parent_path().filename()=="datas");
    assert(!fs::exists(path.parent_path()));
    assert(!g_fullscreen && g_render_filter_mode==GB_RENDER_FILTER_NEAREST);
    assert(ImGui::GetIO().IniFilename==nullptr);
    gb_platform_shutdown();
    assert(!fs::exists(path.parent_path()) && !fs::exists("imgui.ini"));
    assert(gb_platform_init(1));
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
    gb_platform_shutdown();
    assert(fs::exists(path) && !fs::exists("imgui.ini"));
    assert(!fs::exists(fs::current_path()/"Retro-Recomp-GameBoy.ini"));
    assert(gb_platform_init(1));
    assert(g_rr_language==1 && g_rr_autofire);
    gb_platform_shutdown();
    puts("PASS: GB actual startup/close leaves no files; ImGui persistence disabled; settings written only in EXE datas, all display modes/filters retained after reopen; dummy driver only.");
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
        env.pop('GBRECOMP_BENCHMARK',None)
        launch=Path(temp)/'unrelated-working-folder'; launch.mkdir()
        result=subprocess.run([exe],cwd=launch,env=env,capture_output=True,text=True,timeout=30)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)
        assert not list(launch.iterdir()), 'Launching from another folder created stray runtime files'
        assert sorted(p.name for p in Path(temp).iterdir())==['checks.exe','datas','unrelated-working-folder']
        print(result.stdout.strip())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('generated_project',type=Path)
    check(p.parse_args().generated_project.resolve())
