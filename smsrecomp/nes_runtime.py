"""Private adapter for the pinned NESRecomp host; never edit its checkout."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .core import replace_once, slug
from .paths import ASSETS


def prepare_host(project: Path, engine: Path, rom_sha256: str, title: str) -> None:
    host = (engine / 'runner/cyc/cyc_host.c').read_text(encoding='utf-8')
    host = replace_once(host, '#include "../../common/nes_cart.h"', '#include "nes_cart.h"')
    host = replace_once(host, '#include <string.h>',
        '#include <string.h>\n#include <windows.h>\n'
        'static char retro_save_dir[4096], retro_games_dir[4096], retro_save_file[4096];\n'
        'static int retro_auto_save;\nstatic uint8_t *retro_initial_save;\nstatic size_t retro_initial_size;')
    host = replace_once(host, 'static uint8_t *read_file(const char *path, size_t *size) {',
        'static const volatile char retro_marker[] = "[Retro-Recomp]";\n'
        f'static const volatile char retro_rom_sha256[] = "{rom_sha256}";\n'
        'static uint8_t *read_file(const char *path, size_t *size) {\n'
        '    if (retro_marker[0] != \'[\' || !retro_rom_sha256[0]) return NULL;\n'
        '    if (!strcmp(path, "@embedded")) {\n'
        '        HRSRC resource = FindResourceW(NULL, MAKEINTRESOURCEW(103), MAKEINTRESOURCEW(10));\n'
        '        if (!resource) return NULL;\n'
        '        DWORD length = SizeofResource(NULL, resource);\n'
        '        HGLOBAL handle = LoadResource(NULL, resource);\n'
        '        const void *bytes = handle ? LockResource(handle) : NULL;\n'
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
        '        DWORD length = GetModuleFileNameA(NULL, retro_save_dir, sizeof(retro_save_dir) - 128);\n'
        '        char *slash = length ? strrchr(retro_save_dir, \'\\\\\') : NULL;\n'
        '        if (slash) {\n'
        '            *slash = 0;\n'
        '            snprintf(retro_games_dir, sizeof(retro_games_dir), "%s\\\\datas", retro_save_dir);\n'
        '            snprintf(retro_save_file, sizeof(retro_save_file), "%s\\\\games\\\\' +
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
    (project / 'cyc_host.c').write_text(host, encoding='utf-8')
    saves = (engine / 'runner/cyc/cyc_save.inc').read_text(encoding='utf-8')
    saves = replace_once(saves, '    bool ok=cyc_nvram_export(region,buffer,n);\n    int fd=-1;',
        '    bool ok=cyc_nvram_export(region,buffer,n);\n'
        '    if (ok && retro_auto_save && region == 0 && retro_initial_save &&\n'
        '        n == retro_initial_size && memcmp(buffer,retro_initial_save,n) == 0) {\n'
        '        free(buffer); free(temporary); return true;\n'
        '    }\n'
        '    if (ok && retro_auto_save && region == 0) {\n'
        '        CreateDirectoryA(retro_games_dir,NULL);\n'
        '        char path_copy[4096]; snprintf(path_copy,sizeof(path_copy),"%s\\\\games",retro_games_dir);\n'
        '        CreateDirectoryA(path_copy,NULL);\n'
        '    }\n'
        '    int fd=-1;')
    # retro_games_dir holds <exe>/datas; game saves live in its games child.
    (project / 'cyc_save.inc').write_text(saves, encoding='utf-8')
    shutil.copy2(engine / 'common/nes_cart.h', project / 'nes_cart.h')
    shutil.copy2(engine / 'common/nes_known_dumps.inc', project / 'nes_known_dumps.inc')
    cmake = f'''cmake_minimum_required(VERSION 3.20)
project(RetroRecompNES C)
set(NESRECOMP_CYC_DIR "{(engine / 'runner/cyc').as_posix()}")
set(RETRO_NATIVE_DIR "{(ASSETS / 'native').as_posix()}")
include("${{NESRECOMP_CYC_DIR}}/cyc.cmake")
include("${{CMAKE_CURRENT_SOURCE_DIR}}/cycle/sources.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_executable(game ${{NESRECOMP_CYC_SOURCES}} ${{CYC_PROJECT_SOURCES}}
    cyc_host.c ${{RETRO_NATIVE_DIR}}/nes_host_ui.c
    ${{RETRO_NATIVE_DIR}}/retro_menu.c game_resources.rc)
target_include_directories(game PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} ${{RETRO_NATIVE_DIR}})
target_link_libraries(game PRIVATE ${{NESRECOMP_CYC_LIBRARIES}} gdi32)
target_compile_features(game PRIVATE c_std_11)
target_compile_definitions(game PRIVATE _CRT_SECURE_NO_WARNINGS CYC_WITH_SDL)
if(MSVC)
    target_compile_options(game PRIVATE /bigobj /utf-8)
    set_property(TARGET game PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)
endif()
find_package(SDL2 CONFIG REQUIRED)
target_link_libraries(game PRIVATE SDL2::SDL2)
'''
    (project / 'CMakeLists.txt').write_text(cmake, encoding='utf-8')
