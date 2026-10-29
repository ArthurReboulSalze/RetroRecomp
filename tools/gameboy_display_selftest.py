"""Exercise the generated Game Boy adapter's settings and files using SDL's dummy driver (host kit, phase 5).

The checks are compiled into a generated project, against the patched platform layer: the preferences the kit reads and writes for the
Game Boy (display mode, palette, language, autofire, bindings), the former `Retro-Recomp-GameBoy.ini` of 1.6.2 and before (read, never
written), and that starting and closing a game leaves no file."""
from pathlib import Path
import argparse,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.core import run,toolchain
from retrorecomp.platforms import build_executable
def check(project):
    source=project/'rr_display_checks.cpp'
    source.write_text('''#define SDL_MAIN_HANDLED
#undef NDEBUG
#include <cassert>
#include "runtime/src/platform_sdl.cpp"
extern "C" void gb_dispatch(GBContext *, uint16_t) { assert(false && "No guest CPU in display fixture"); }
static void write_file(const fs::path &path, const char *text) {
    fs::create_directories(path.parent_path());
    FILE *file = fopen(path.string().c_str(), "wb"); assert(file); fputs(text, file); fclose(file);
}
int main() {
    SDL_SetMainReady();
    SDL_SetHintWithPriority(SDL_HINT_RENDER_DRIVER, "software", SDL_HINT_OVERRIDE);
    assert(gb_platform_init(1));
    RrhkUi *ui = rrhk_ui();
    const fs::path datas = fs::path(rr_gb_old_file(ui)).parent_path();
    assert(datas.filename() == "datas" && !fs::exists(datas));
    assert(ui->fullscreen == 0 && ui->filter == 0 && g_palette_idx == 1 && !ui->autofire && ui->language == 0);
    gb_platform_shutdown();
    assert(!fs::exists(datas) && !fs::exists("imgui.ini"));

    /* F4 and F5 are written to the kit's preferences, and read back. */
    assert(gb_platform_init(1));
    for (int cycle = 0; cycle < 6; ++cycle) {
        rrhk_cycle_display();
        assert(ui->fullscreen == (cycle + 1) % 3);
        assert(rr_ini_int(L"GameBoy.Video", L"display_mode", -1, ui->ini_file) == ui->fullscreen);
    }
    bool running = true;
    assert(rr_gb_key_event(ui, SDL_SCANCODE_F5, &running) && g_palette_idx == 0);
    assert(rr_ini_int(L"GameBoy.Video", L"palette", -1, ui->ini_file) == 0);
    assert(rr_gb_key_event(ui, SDL_SCANCODE_F5, &running) && g_palette_idx == 1);
    assert(rr_ini_int(L"GameBoy.Video", L"palette", -1, ui->ini_file) == 1);
    ui->language = 1; ui->autofire = 1;
    gb_platform_shutdown();
    assert(fs::exists(datas / "Retro-Recomp.ini") && !fs::exists("imgui.ini"));
    assert(!fs::exists(datas / "Retro-Recomp-GameBoy.ini"));      /* the former file is never written */
    assert(!fs::exists(fs::current_path() / "Retro-Recomp-GameBoy.ini") && !fs::exists(fs::current_path() / "Retro-Recomp.ini"));

    /* The settings of a game that was last played with the host of 1.6.2 are kept: read from its own file, the kit's win. */
    fs::remove_all(datas);
    write_file(datas / "Retro-Recomp-GameBoy.ini",
        "video.filter=3\\nvideo.display_mode=2\\nvideo.palette=green\\nui.language=fr\\ninput.autofire=1\\n"
        "keyboard.a.0=key:4\\nkeyboard.a.1=none\\nkeyboard.up.0=none\\ncontroller.b.0=button:3\\naudio.volume_percent=30\\n");
    assert(gb_platform_init(1));
    assert(ui->filter == 3 && ui->fullscreen == 2 && g_palette_idx == 0 && ui->language == 1 && ui->autofire == 1);
    assert(ui->keys[0][RR_GB_A] == SDL_SCANCODE_A && ui->keys[0][RR_GB_UP] == SDL_SCANCODE_UNKNOWN);
    assert(ui->keys[0][RR_GB_B] == SDL_SCANCODE_X && ui->buttons[0][RR_GB_B] == SDL_CONTROLLER_BUTTON_Y);
    assert(ui->buttons[0][RR_GB_A] == SDL_CONTROLLER_BUTTON_B);   /* the controller defaults: east is A, south is B */
    assert(!fs::exists(datas / "Retro-Recomp.ini"));              /* reading wrote nothing */
    write_file(datas / "Retro-Recomp.ini", "[Interface]\\nlanguage=de\\n[GameBoy.Video]\\npalette=1\\nfilter=2\\n");
    gb_platform_shutdown();
    assert(gb_platform_init(1));
    assert(ui->language == 4 && g_palette_idx == 1 && ui->filter == 2 && ui->fullscreen == 2 && ui->autofire == 1);
    gb_platform_shutdown();
    puts("PASS: GB startup/close leaves no files; F4 and F5 are kept in the kit's preferences and restored; the former Game Boy file is read for the display mode, filter, palette, language, autofire and bindings, never written; the kit's keys win; dummy driver only.");
    return 0;
}
''',encoding='utf-8')
    cmakefile=project/'CMakeLists.txt'; cmaketext=cmakefile.read_text()
    addition='''
add_executable(rr_display_checks rr_display_checks.cpp)
target_link_libraries(rr_display_checks PRIVATE gbrt)
target_include_directories(rr_display_checks PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_options(rr_display_checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8>")
'''
    if 'add_executable(rr_display_checks' not in cmaketext:
        cmakefile.write_text(cmaketext+addition,encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build'],log=project/'display-checks-build.log')
    run([cmake,'--build',project/'build','--target','rr_display_checks','--config','Release','--parallel','4'],log=project/'display-checks-build.log')
    with tempfile.TemporaryDirectory(prefix='rr-gb-display-') as temp:
        exe=Path(temp)/'checks.exe'; shutil.copy2(build_executable(project/'build','rr_display_checks'),exe)
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
