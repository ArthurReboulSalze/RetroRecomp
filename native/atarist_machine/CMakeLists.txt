cmake_minimum_required(VERSION 3.20)
project(RetroRecompAtariST LANGUAGES C)

# The Atari ST player (MIT, ours) on Hatari's libretro core (GPL-2.0), adapted at build time by retrorecomp/atarist_hatari.py and
# built as its own CMake project (Hatari's build files name CMAKE_SOURCE_DIR, so it is not a subdirectory of this one). A program
# linked with Hatari is distributed under the GPL (licenses/hatari.md).
#   RR_HATARI_TREE        the adapted Hatari tree (required)
#   RR_HATARI_BUILD       Hatari's own build folder, holding src/libretro-hatari.a and the generated config.h (required)
#   RR_ST_GENERATED       the generated native code (steps/*.c, step_semantics.h): a native build
#   RR_ST_PAYLOAD_DIR     the embedded game and resources (atarist_payload.h, game_resources.rc): an exported game
#   RR_ST_STATE_INPUT     what else the quick-state key depends on (the converter's stamp)
set(RR_HATARI_TREE "" CACHE PATH "Adapted Hatari tree")
set(RR_HATARI_BUILD "" CACHE PATH "Hatari's build folder")
set(RR_ST_PAYLOAD_DIR "" CACHE PATH "Private per-game resources; never a public release input")
set(RR_ST_STATE_INPUT "" CACHE STRING "Converter stamp entering the quick-state key")
set(RR_ST_GENERATED "" CACHE PATH "Generated native code of one game")
if(NOT RR_HATARI_TREE OR NOT EXISTS "${RR_HATARI_TREE}/src/retro/main_retro.c")
    message(FATAL_ERROR "RR_HATARI_TREE must name the adapted Hatari tree")
endif()
find_library(RR_HATARI_CORE NAMES retro-hatari libretro-hatari PATHS "${RR_HATARI_BUILD}/src" NO_DEFAULT_PATH REQUIRED)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
get_filename_component(RR_COMMON_NATIVE "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)

# The session sees Hatari's own headers (its machine state: RAM, CPU registers) and the libretro API header (MIT, libretro/).
add_library(rr_atarist_session STATIC atarist_session.c)
target_include_directories(rr_atarist_session PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/libretro")
target_include_directories(rr_atarist_session PRIVATE "${RR_HATARI_BUILD}"
    "${RR_HATARI_TREE}/src/includes" "${RR_HATARI_TREE}/src/cpu" "${RR_HATARI_TREE}/src/debug" "${RR_HATARI_TREE}/src/falcon"
    "${RR_HATARI_TREE}/src")
target_link_libraries(rr_atarist_session PUBLIC "${RR_HATARI_CORE}")
if(NOT WIN32)
    target_link_libraries(rr_atarist_session PUBLIC m)
endif()

# The generated native code of one game (steps/*.c, step_semantics.h): the forms hold the text of Hatari's handlers and the instructions call them, so they see Hatari's CPU headers
# and the cputbl.h of its build.
if(RR_ST_GENERATED)
    file(GLOB RR_ST_STEPS "${RR_ST_GENERATED}/steps/*.c")
    if(NOT RR_ST_STEPS)
        message(FATAL_ERROR "RR_ST_GENERATED holds no native code")
    endif()
    target_sources(rr_atarist_session PRIVATE ${RR_ST_STEPS})
    target_include_directories(rr_atarist_session PRIVATE "${RR_ST_GENERATED}" "${RR_HATARI_TREE}" "${RR_HATARI_TREE}/src/cpu/softfloat"
        "${RR_HATARI_BUILD}/src/cpu")
    target_compile_definitions(rr_atarist_session PRIVATE RR_ST_NATIVE=1)
endif()

# The quick-state key: states of different builds are never mixed.
set(RR_STATE_INPUT "atarist-state-v1|${CMAKE_SYSTEM_NAME}|${CMAKE_SYSTEM_PROCESSOR}|${CMAKE_SIZEOF_VOID_P}|${CMAKE_C_COMPILER_ID}|${RR_ST_STATE_INPUT}")
foreach(RR_STATE_SOURCE atarist_session.c atarist_session.h "${RR_HATARI_TREE}/../ready.json")
    if(NOT IS_ABSOLUTE "${RR_STATE_SOURCE}")
        set(RR_STATE_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/${RR_STATE_SOURCE}")
    endif()
    file(SHA256 "${RR_STATE_SOURCE}" RR_STATE_HASH)
    string(APPEND RR_STATE_INPUT "|${RR_STATE_HASH}")
endforeach()
if(RR_ST_GENERATED)
    file(SHA256 "${RR_ST_GENERATED}/steps/index.c" RR_STATE_HASH)
    string(APPEND RR_STATE_INPUT "|native|${RR_STATE_HASH}")
endif()
string(SHA256 RR_STATE_ABI "${RR_STATE_INPUT}")

add_executable(atarist_player atarist_player.c "${RR_COMMON_NATIVE}/retro_menu.c" "${RR_COMMON_NATIVE}/platform_io.c")
foreach(RR_KIT_FILE audio events input main menu options pointer ring timing video)
    target_sources(atarist_player PRIVATE "${RR_COMMON_NATIVE}/hostkit/shell/rrhk_${RR_KIT_FILE}.c")
endforeach()
target_include_directories(atarist_player PRIVATE "${RR_COMMON_NATIVE}" "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(atarist_player PRIVATE rr_atarist_session)
set_target_properties(atarist_player PROPERTIES OUTPUT_NAME "RetroRecomp-AtariST")
if(NOT RR_RECOMP_VERSION)
    set(RR_RECOMP_VERSION "dev")
endif()
target_compile_definitions(atarist_player PRIVATE RR_RECOMP_VERSION="${RR_RECOMP_VERSION}" SDL_MAIN_HANDLED
    RR_ST_STATE_ABI="${RR_STATE_ABI}")

if(RR_ST_PAYLOAD_DIR)
    target_include_directories(atarist_player PRIVATE "${RR_ST_PAYLOAD_DIR}")
    target_compile_definitions(atarist_player PRIVATE RR_ST_LINKED)
    if(WIN32)
        # No console window for the game; the headless validation entry stays.
        target_link_options(atarist_player PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)
        enable_language(RC)
        target_sources(atarist_player PRIVATE "${RR_ST_PAYLOAD_DIR}/game_resources.rc" "${RR_ST_PAYLOAD_DIR}/game_metadata.rc")
    else()
        enable_language(ASM)
        target_sources(atarist_player PRIVATE "${RR_ST_PAYLOAD_DIR}/embedded_resources.S" "${RR_ST_PAYLOAD_DIR}/embedded_resources.c")
    endif()
endif()

find_package(SDL2 CONFIG REQUIRED)
if(TARGET SDL2::SDL2-static)
    target_link_libraries(atarist_player PRIVATE SDL2::SDL2-static)
else()
    target_link_libraries(atarist_player PRIVATE SDL2::SDL2)
endif()
# -fwrapv: a form is Hatari's handler with the opcode as a literal. ADDX.L D6,D6 then shows the compiler that both operands are one register, and without it the signed sum of the
# handler is taken not to overflow and the flags come out wrong (tools/atarist_vector_selftest.py finds it).
target_compile_options(rr_atarist_session PRIVATE -O2 -fno-fast-math -fwrapv)
# Link-time optimisation of the session and of the generated code together with the player (Hatari's core stays as it is built): the forms reach the shared bus functions directly.
if(RR_ST_GENERATED)
    set_property(TARGET rr_atarist_session atarist_player PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
endif()
target_compile_options(atarist_player PRIVATE -O2 -fno-fast-math)
target_link_libraries(atarist_player PRIVATE m)
if(WIN32)
    target_link_libraries(atarist_player PRIVATE gdi32 shell32 user32 ws2_32)
endif()
