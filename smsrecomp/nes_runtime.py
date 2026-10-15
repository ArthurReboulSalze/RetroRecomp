"""Private adapter for the pinned NESRecomp host; never edit its checkout."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .core import replace_once, slug
from .paths import ASSETS
from .nes_machine import prepare_machine
from .nes_build import stage_native
from . import __version__


def prepare_host(project: Path, engine: Path, rom_sha256: str, title: str,
                 *, standard: str = 'ntsc', zapper: bool = False, mapper: int | None = None) -> None:
    machine = prepare_machine(project, engine)
    native = stage_native(project, ASSETS / 'native')
    (project / 'retro_nes_config.h').write_text(
        f'#define RR_NES_ROM_SHA "{rom_sha256}"\n'
        f'#define RR_NES_STATE_NAME L"{slug(title)}-{rom_sha256[:12]}"\n', encoding='utf-8')
    host = (engine / 'runner/cyc/cyc_host.c').read_text(encoding='utf-8')
    host = host.replace('written at run time, not compilable', 'no matching compiled RAM guard')
    host = host.replace('RAM addresses also started an instruction this run (not seedable)',
                        'RAM addresses also started an interpreted instruction this run')
    host = replace_once(host, '    mf = fopen(path, "w");',
                        '    rr_nes_ram_trace_merge(path);\n    mf = fopen(path, "w");')
    host = replace_once(host, '        fclose(mf);\n    }\n    printf("miss-log:',
                        '        rr_nes_ram_trace_write(mf);\n        fclose(mf);\n    }\n    printf("miss-log:')
    host = replace_once(host, '        cyc_run_ram_opcodes = (uint8_t *)calloc(0x800 * 32, 1);',
                        '        cyc_run_ram_opcodes = (uint8_t *)calloc(0x800 * 32, 1);\n        rr_nes_ram_trace_enable();')
    host = replace_once(host, '#include "../../common/nes_cart.h"', '#include "nes_cart.h"')
    host = replace_once(host, '#include <string.h>',
        '#include <string.h>\n#include "platform_io.h"\n#include "embedded_resources.h"\n#include "retro_nes.h"\n'
        'static char retro_save_dir[4096], retro_games_dir[4096], retro_save_file[4096];\n'
        'static int retro_auto_save;\nstatic uint8_t *retro_initial_save;\nstatic size_t retro_initial_size;')
    host = replace_once(host, 'static uint8_t *read_file(const char *path, size_t *size) {',
        'static const volatile char retro_marker[] = "[Retro-Recomp]";\n'
        f'static const volatile char retro_rom_sha256[] = "{rom_sha256}";\n'
        'static uint8_t *read_file(const char *path, size_t *size) {\n'
        '    if (retro_marker[0] != \'[\' || !retro_rom_sha256[0]) return NULL;\n'
        '    if (!strcmp(path, "@embedded")) {\n'
        '        size_t length=0; const void *bytes=rr_resource(103,&length);\n'
        '        uint8_t *copy = bytes ? (uint8_t *)malloc(length) : NULL;\n'
        '        if (copy) { memcpy(copy, bytes, length); *size = length; }\n'
        '        return copy;\n'
        '    }')
    host = replace_once(host, 'const char *rom_path = NULL, *hash_out = NULL,',
                              'const char *rom_path = "@embedded", *hash_out = NULL,')
    host = replace_once(host, "argv[i][0] != '-' && !rom_path", "argv[i][0] != '-' && !strcmp(rom_path, \"@embedded\")")
    host = replace_once(host, 'cyc_sdl_main(cyc_native_program_name ? cyc_native_program_name : rom_path, scale)',
        'cyc_sdl_main(' + json.dumps(title, ensure_ascii=False) + ', scale)')
    host = replace_once(host, '    if (!save_paths_distinct(save_file,datach_save)) {',
        '    if (!save_file && cyc_nvram_size(0)) {\n'
        '        wchar_t directory[32768];\n'
        '        if (rr_executable_directory(directory,32768) && rr_to_utf8(directory,retro_save_dir,sizeof(retro_save_dir))) {\n'
        '            snprintf(retro_games_dir, sizeof(retro_games_dir), "%s" RR_SLASH "datas", retro_save_dir);\n'
        '            snprintf(retro_save_file, sizeof(retro_save_file), "%s" RR_SLASH "games" RR_SLASH "' +
        slug(title) + '-' + rom_sha256[:12] + '.sav", retro_games_dir);\n'
        '            save_file = retro_save_file; retro_auto_save = 1;\n'
        '        }\n'
        '    }\n'
        '    if (!save_paths_distinct(save_file,datach_save)) {')
    host = replace_once(host, '    cyc_power_on((uint8_t)align);',
        '    cyc_power_on((uint8_t)align);\n'
        '    if (retro_auto_save) {\n'
        '        retro_initial_size = cyc_nvram_size(0);\n'
        '        retro_initial_save = (uint8_t *)malloc(retro_initial_size);\n'
        '        if (retro_initial_save) cyc_nvram_export(0, retro_initial_save, retro_initial_size);\n'
        '    }')
    # Headless hooks exercise the same codec and file I/O as F8/F9, including
    # resume in a fresh process. They never run during normal GUI startup.
    host = replace_once(host, 'int main(int argc, char **argv) {', '''
static bool retro_quick_file(const char *name, bool load) {
    wchar_t path[32768];
    if (!rr_from_utf8(name, path, 32768)) return false;
    return rr_nes_state_file(path, load);
}
int main(int argc, char **argv) {
    const char *quick_load = NULL, *quick_save = NULL;
    long quick_frame = -1;
''')
    host = replace_once(host, '        else if (!strcmp(argv[i], "--headless")) headless = true;', '''
        else if (!strcmp(argv[i], "--quick-load") && i + 1 < argc) quick_load = argv[++i], headless = true;
        else if (!strcmp(argv[i], "--quick-save") && i + 1 < argc) quick_save = argv[++i], headless = true;
        else if (!strcmp(argv[i], "--quick-save-frame") && i + 1 < argc) quick_frame = atol(argv[++i]);
        else if (!strcmp(argv[i], "--headless")) headless = true;''')
    host = '#define SDL_MAIN_HANDLED\n#include "runtime_feedback.h"\n' + host
    host = replace_once(host, '    AccCoinDriver drv;', '''
    rr_feedback_start(!headless && cyc_run_native);
    if (quick_load && !retro_quick_file(quick_load, true)) {
        fprintf(stderr, "Quick state load failed\\n"); return 2;
    }
    AccCoinDriver drv;''')
    host = replace_once(host, '        frame++;', '''
        if (quick_save && frame == quick_frame && !retro_quick_file(quick_save, false)) {
            fprintf(stderr, "Quick state save failed\\n"); return 2;
        }
        frame++;''')
    (project / 'cyc_host.c').write_text(host, encoding='utf-8')
    saves = (engine / 'runner/cyc/cyc_save.inc').read_text(encoding='utf-8')
    saves = replace_once(saves, '    bool ok=cyc_nvram_export(region,buffer,n);\n    int fd=-1;',
        '    bool ok=cyc_nvram_export(region,buffer,n);\n'
        '    if (ok && retro_auto_save && region == 0 && retro_initial_save &&\n'
        '        n == retro_initial_size && memcmp(buffer,retro_initial_save,n) == 0) {\n'
        '        free(buffer); free(temporary); return true;\n'
        '    }\n'
        '    if (ok && retro_auto_save && region == 0) {\n'
        '        wchar_t dir[32768];\n'
        '        if(rr_from_utf8(retro_games_dir,dir,32768)) { rr_mkdir(dir);\n'
        '            if(!rr_wide_append(dir,32768,RR_SLASH_W L"games"))rr_mkdir(dir); }\n'
        '    }\n'
        '    int fd=-1;')
    # retro_games_dir holds <exe>/datas; game saves live in its games child.
    (project / 'cyc_save.inc').write_text(saves, encoding='utf-8')
    shutil.copy2(engine / 'common/nes_cart.h', project / 'nes_cart.h')
    shutil.copy2(engine / 'common/nes_known_dumps.inc', project / 'nes_known_dumps.inc')
    cmake = f'''cmake_minimum_required(VERSION 3.20)
project(RetroRecompNES C)
set(NESRECOMP_CYC_DIR "{machine.as_posix()}")
set(RETRO_NATIVE_DIR "{native.as_posix()}")
include("${{NESRECOMP_CYC_DIR}}/cyc.cmake")
include("${{CMAKE_CURRENT_SOURCE_DIR}}/cycle/sources.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_library(nes_hardware OBJECT ${{NESRECOMP_CYC_SOURCES}})
target_include_directories(nes_hardware PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} ${{RETRO_NATIVE_DIR}} "${{CMAKE_CURRENT_SOURCE_DIR}}")
target_compile_features(nes_hardware PRIVATE c_std_11)
target_compile_definitions(nes_hardware PRIVATE _CRT_SECURE_NO_WARNINGS CYC_WITH_SDL
    RR_NES_PAL={int(standard == 'pal')} RR_NES_ZAPPER={int(zapper)})
add_executable(game $<TARGET_OBJECTS:nes_hardware> ${{CYC_PROJECT_SOURCES}}
    cyc_host.c ${{RETRO_NATIVE_DIR}}/nes_host_ui.c
    ${{RETRO_NATIVE_DIR}}/nes_state.c
    ${{RETRO_NATIVE_DIR}}/retro_menu.c ${{RETRO_NATIVE_DIR}}/platform_io.c)
if(WIN32)
    target_sources(game PRIVATE game_resources.rc)
    target_link_libraries(game PRIVATE gdi32)
else()
    enable_language(ASM)
    target_sources(game PRIVATE embedded_resources.c embedded_resources.S)
endif()
target_include_directories(game PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} ${{RETRO_NATIVE_DIR}} "${{CMAKE_CURRENT_SOURCE_DIR}}")
target_link_libraries(game PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
target_compile_features(game PRIVATE c_std_11)
target_compile_definitions(game PRIVATE _CRT_SECURE_NO_WARNINGS CYC_WITH_SDL)
target_compile_definitions(game PRIVATE [[RR_RECOMP_VERSION="{__version__}"]])
target_compile_definitions(game PRIVATE RR_NES_PAL={int(standard == 'pal')} RR_NES_ZAPPER={int(zapper)})
if(MSVC)
    target_compile_options(game PRIVATE /bigobj /utf-8)
    target_compile_options(nes_hardware PRIVATE /bigobj /utf-8)
    set_property(TARGET game nes_hardware PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)
endif()
find_package(SDL2 CONFIG REQUIRED)
target_link_libraries(game PRIVATE SDL2::SDL2)

# GCC's default separate-object build is too costly on smaller Linux CPUs.
# Profile hardware through native execution without linking the full program
# twice with LTO. Only the final native game uses the whole-program link.
set(RR_NES_PGO_AVAILABLE FALSE CACHE INTERNAL "Hardware profile support" FORCE)
set(RR_NES_PROFILE_MODE "" CACHE STRING "Private hardware profile mode")
set(RR_NES_PROFILE_DIR "" CACHE PATH "Private hardware profile directory")
if(UNIX AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
    include(CheckIPOSupported)
    check_ipo_supported(RESULT _rr_ipo LANGUAGES C)
    add_library(nes_training_code OBJECT EXCLUDE_FROM_ALL ${{CYC_PROJECT_SOURCES}})
    target_include_directories(nes_training_code PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} ${{RETRO_NATIVE_DIR}} "${{CMAKE_CURRENT_SOURCE_DIR}}")
    target_compile_features(nes_training_code PRIVATE c_std_11)
    target_compile_definitions(nes_training_code PRIVATE RR_NES_PAL={int(standard == 'pal')} RR_NES_ZAPPER={int(zapper)})
    set_property(TARGET nes_training_code PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
    add_executable(nes_profile EXCLUDE_FROM_ALL $<TARGET_OBJECTS:nes_hardware> $<TARGET_OBJECTS:nes_training_code>
        "${{NESRECOMP_CYC_DIR}}/cyc_host.c"
        "${{RETRO_NATIVE_DIR}}/platform_io.c")
    target_include_directories(nes_profile PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} ${{RETRO_NATIVE_DIR}} "${{CMAKE_CURRENT_SOURCE_DIR}}")
    target_link_libraries(nes_profile PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
    if(_rr_ipo)
        set_property(TARGET nes_hardware game nes_profile PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
        target_link_options(game PRIVATE -flto=2)
        target_link_options(nes_profile PRIVATE -flto=2)
    endif()
    set(RR_NES_PGO_AVAILABLE TRUE CACHE INTERNAL "Hardware profile support" FORCE)
    if(RR_NES_PROFILE_MODE STREQUAL "generate")
        set_property(SOURCE ${{NESRECOMP_CYC_SOURCES}} APPEND PROPERTY COMPILE_OPTIONS "-fprofile-generate=${{RR_NES_PROFILE_DIR}}")
        target_link_options(nes_profile PRIVATE "-fprofile-generate=${{RR_NES_PROFILE_DIR}}")
    elseif(RR_NES_PROFILE_MODE STREQUAL "use")
        set_property(SOURCE ${{NESRECOMP_CYC_SOURCES}} APPEND PROPERTY COMPILE_OPTIONS "-fprofile-use=${{RR_NES_PROFILE_DIR}}" -fprofile-partial-training)
        target_link_options(game PRIVATE "-fprofile-use=${{RR_NES_PROFILE_DIR}}")
    endif()
endif()
'''
    if mapper is not None:
        if not 0 <= mapper <= 4095:
            raise ValueError('Invalid compiled NES mapper identity.')
        cmake += f'''if(UNIX AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
    set_property(SOURCE ${{NESRECOMP_CYC_SOURCES}} APPEND PROPERTY COMPILE_DEFINITIONS RR_NES_STATIC_MAPPER={mapper})
endif()
'''
    (project / 'CMakeLists.txt').write_text(cmake, encoding='utf-8')
    from .feedback import stage
    stage(project, 'nes', rom_sha256, cmake=False)
