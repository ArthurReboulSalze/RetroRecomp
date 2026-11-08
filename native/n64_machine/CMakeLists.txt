cmake_minimum_required(VERSION 3.20)
project(RetroRecompNintendo64 C CXX)

# The Nintendo 64 player (MIT, ours) on Mupen64Plus-Next (the Mupen64Plus core, GPL-2.0-or-later; ParaLLEl-RDP and ParaLLEl-RSP,
# MIT, with GNU Lightning, LGPL-3.0-or-later), adapted at build time by retrorecomp/n64_core.py. The executable is GPL-3.0 as a
# whole (licenses/mupen64plus-next.md). Never compiled: angrylion, GLideN64's renderer, the new dynamic recompiler.
#   RR_N64_TREE          the adapted core tree (required)
#   RR_N64_GENERATED     the generated native blocks of one game (blocks/*.c): a native build
#   RR_N64_PAYLOAD_DIR   the embedded game and resources (n64_payload.h, game_resources.rc): an exported game
#   RR_N64_STATE_INPUT   what else the quick-state key depends on (the converter's stamp)
set(RR_N64_TREE "" CACHE PATH "Adapted Mupen64Plus-Next tree")
set(RR_N64_GENERATED "" CACHE PATH "Generated native blocks of one game")
set(RR_N64_PAYLOAD_DIR "" CACHE PATH "Private per-game resources; never a public release input")
set(RR_N64_STATE_INPUT "" CACHE STRING "Converter stamp entering the quick-state key")
if(NOT RR_N64_TREE OR NOT EXISTS "${RR_N64_TREE}/mupen64plus-core/src/device/r4300/n64_exec.h")
    message(FATAL_ERROR "RR_N64_TREE must name the adapted Mupen64Plus-Next tree")
endif()

set(R "${RR_N64_TREE}")
set(CORE ${R}/mupen64plus-core)
set(LRC ${R}/libretro-common)
set(RSPHLE ${R}/mupen64plus-rsp-hle)
set(CXD4 ${R}/mupen64plus-rsp-cxd4)
set(PRSP ${R}/mupen64plus-rsp-paraLLEl)
set(PRDPI ${R}/mupen64plus-video-paraLLEl/parallel-rdp)
set(Z ${R}/custom/dependencies/libzlib)
set(GLUE ${CMAKE_CURRENT_SOURCE_DIR}/glue)
get_filename_component(RR_COMMON_NATIVE "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)

set(CORE_C
  ${CORE}/src/asm_defines/asm_defines.c ${CORE}/src/api/callbacks.c ${R}/custom/mupen64plus-core/api/config.c
  ${CORE}/src/api/debugger.c ${CORE}/src/api/frontend.c ${CORE}/src/backends/plugins_compat/audio_plugin_compat.c
  ${CORE}/src/backends/api/video_capture_backend.c ${CORE}/src/backends/plugins_compat/input_plugin_compat.c
  ${CORE}/src/backends/clock_ctime_plus_delta.c ${CORE}/src/backends/dummy_video_capture.c ${CORE}/src/backends/file_storage.c
  ${CORE}/src/device/cart/cart.c ${CORE}/src/device/cart/af_rtc.c ${CORE}/src/device/cart/cart_rom.c
  ${CORE}/src/device/cart/eeprom.c ${CORE}/src/device/cart/flashram.c ${CORE}/src/device/cart/is_viewer.c
  ${CORE}/src/device/cart/sram.c ${CORE}/src/device/controllers/game_controller.c ${CORE}/src/device/controllers/vru_controller.c
  ${CORE}/src/device/controllers/paks/biopak.c ${CORE}/src/device/controllers/paks/mempak.c
  ${CORE}/src/device/controllers/paks/rumblepak.c ${CORE}/src/device/controllers/paks/transferpak.c
  ${CORE}/src/device/dd/dd_controller.c ${CORE}/src/device/dd/disk.c ${CORE}/src/device/device.c
  ${CORE}/src/device/gb/gb_cart.c ${CORE}/src/device/gb/mbc3_rtc.c ${CORE}/src/device/gb/m64282fp.c
  ${CORE}/src/device/memory/memory.c ${CORE}/src/device/pif/bootrom_hle.c ${CORE}/src/device/pif/cic.c
  ${CORE}/src/device/pif/n64_cic_nus_6105.c ${CORE}/src/device/pif/pif.c ${CORE}/src/device/r4300/cached_interp.c
  ${CORE}/src/device/r4300/cp0.c ${CORE}/src/device/r4300/cp1.c ${CORE}/src/device/r4300/cp2.c ${CORE}/src/device/r4300/idec.c
  ${CORE}/src/device/r4300/interrupt.c ${CORE}/src/device/r4300/pure_interp.c ${CORE}/src/device/r4300/r4300_core.c
  ${CORE}/src/device/r4300/tlb.c ${CORE}/src/device/rcp/ai/ai_controller.c ${CORE}/src/device/rcp/mi/mi_controller.c
  ${CORE}/src/device/rcp/pi/pi_controller.c ${CORE}/src/device/rcp/rdp/fb.c ${CORE}/src/device/rcp/rdp/rdp_core.c
  ${CORE}/src/device/rcp/ri/ri_controller.c ${CORE}/src/device/rcp/rsp/rsp_core.c ${CORE}/src/device/rcp/si/si_controller.c
  ${CORE}/src/device/rcp/vi/vi_controller.c ${CORE}/src/device/rdram/rdram.c ${CORE}/src/main/main.c ${CORE}/src/main/util.c
  ${CORE}/src/main/cheat.c ${CORE}/src/main/rom.c ${CORE}/src/main/savestates.c ${CORE}/src/plugin/plugin.c
  ${CORE}/src/plugin/dummy_audio.c ${CORE}/src/plugin/dummy_input.c ${CORE}/subprojects/md5/md5.c)
file(GLOB PNG_C ${R}/custom/dependencies/libpng/png*.c)
list(FILTER PNG_C EXCLUDE REGEX "pngtest|example")
set(MINIZIP_C ${CORE}/subprojects/minizip/zip.c ${CORE}/subprojects/minizip/unzip.c ${CORE}/subprojects/minizip/ioapi.c)
set(ZLIB_C ${Z}/adler32.c ${Z}/compress.c ${Z}/crc32.c ${Z}/deflate.c ${Z}/gzclose.c ${Z}/gzlib.c ${Z}/gzread.c ${Z}/gzwrite.c
  ${Z}/infback.c ${Z}/inffast.c ${Z}/inflate.c ${Z}/inftrees.c ${Z}/trees.c ${Z}/uncompr.c ${Z}/zutil.c)
set(LIBRETRO_C ${R}/libretro/libretro.c ${LRC}/memmap/memalign.c
  ${R}/custom/mupen64plus-core/plugin/emulate_game_controller_via_libretro.c
  ${LRC}/audio/resampler/drivers/sinc_resampler.c ${LRC}/audio/resampler/drivers/nearest_resampler.c
  ${LRC}/audio/resampler/audio_resampler.c ${R}/custom/mupen64plus-core/plugin/audio_libretro/audio_backend_libretro.c
  ${LRC}/file/config_file.c ${LRC}/file/config_file_userdata.c ${LRC}/file/file_path.c ${LRC}/file/file_path_io.c
  ${LRC}/time/rtime.c ${LRC}/compat/compat_strl.c ${LRC}/compat/compat_posix_string.c ${LRC}/compat/compat_strcasestr.c
  ${LRC}/audio/conversion/float_to_s16.c ${LRC}/audio/conversion/s16_to_float.c ${LRC}/features/features_cpu.c
  ${LRC}/lists/string_list.c ${LRC}/encodings/encoding_utf.c ${LRC}/string/stdstring.c ${LRC}/vfs/vfs_implementation.c
  ${LRC}/streams/file_stream.c ${LRC}/compat/fopen_utf8.c ${R}/custom/mupen64plus-core/api/vidext_libretro.c
  ${LRC}/libco/libco.c)
if(WIN32)
  list(APPEND LIBRETRO_C ${R}/GLideN64/src/osal/osal_files_win32.c)
else()
  list(APPEND LIBRETRO_C ${R}/GLideN64/src/osal/osal_files_unix.c)
endif()
set(RSP_C ${RSPHLE}/src/alist.c ${RSPHLE}/src/alist_audio.c ${RSPHLE}/src/alist_naudio.c ${RSPHLE}/src/alist_nead.c
  ${RSPHLE}/src/audio.c ${RSPHLE}/src/cicx105.c ${RSPHLE}/src/hle.c ${RSPHLE}/src/hvqm.c ${RSPHLE}/src/jpeg.c
  ${RSPHLE}/src/memory.c ${RSPHLE}/src/mp3.c ${RSPHLE}/src/musyx.c ${RSPHLE}/src/re2.c ${RSPHLE}/src/plugin.c ${CXD4}/rsp.c)
if(WIN32)
  list(APPEND RSP_C ${PRSP}/win32/mman/sys/mman.c)
endif()
file(GLOB PRDP_CXX ${PRDPI}/parallel-rdp/*.cpp)
foreach(f buffer buffer_pool command_buffer command_pool context cookie descriptor_set device event_manager fence fence_manager
          image memory_allocator pipeline_event query_pool render_pass sampler semaphore semaphore_manager shader texture_format)
  list(APPEND PRDP_CXX ${PRDPI}/vulkan/${f}.cpp)
endforeach()
foreach(f arena_allocator logging thread_id aligned_alloc timer timeline_trace_file thread_name)
  list(APPEND PRDP_CXX ${PRDPI}/util/${f}.cpp)
endforeach()
file(GLOB PRSP_CXX ${PRSP}/rsp/*.cpp ${PRSP}/arch/simd/rsp/*.cpp)
list(APPEND PRSP_CXX ${PRSP}/parallel.cpp ${PRSP}/rsp_disasm.cpp ${PRSP}/jit_allocator.cpp ${PRSP}/rsp_jit.cpp)
set(PRSP_C "")
foreach(f jit_disasm jit_memory jit_names jit_note jit_print jit_size lightning)
  list(APPEND PRSP_C ${PRSP}/lightning/lib/${f}.c)
endforeach()

# What the core's code and ours compiled against it see: the headers of the adapted tree (our glue's first: they stand in for the
# unmarked files left out of it) and the core's build definitions.
add_library(rr_n64_api INTERFACE)
target_include_directories(rr_n64_api BEFORE INTERFACE ${GLUE})
target_include_directories(rr_n64_api INTERFACE ${CMAKE_CURRENT_SOURCE_DIR} ${R}/custom ${R}/custom/mupen64plus-core
  ${R}/custom/android/include ${R}/GLideN64/src ${R}/GLideN64/src/osal ${CORE}/src ${CORE}/src/api ${CORE}/src/device/r4300
  ${R}/custom/mupen64plus-core/plugin/audio_libretro ${LRC}/include ${R}/libretro ${CORE}/subprojects/minizip
  ${CORE}/subprojects/md5 ${R}/custom/dependencies/libpng ${R}/xxHash ${Z}
  ${PRDPI} ${PRDPI}/parallel-rdp ${PRDPI}/vulkan ${PRDPI}/vulkan-headers/include ${PRDPI}/volk ${PRDPI}/util
  ${PRSP}/arch/simd/rsp ${PRSP}/lightning/include)
set(RR_N64_DEFS HAVE_LLE HAVE_PARALLEL_RDP HAVE_PARALLEL_RSP PARALLEL_INTEGRATION GRANITE_VULKAN_MT __STDC_CONSTANT_MACROS
  __STDC_LIMIT_MACROS __LIBRETRO__ USE_FILE32API M64P_PLUGIN_API M64P_CORE_PROTOTYPES _ENDUSER_RELEASE SINC_LOWER_QUALITY
  __VEC4_OPT MUPENPLUSAPI NDEBUG _CRT_SECURE_NO_WARNINGS STATIC_LINKING NO_ASM)
# The platform macro must be the same for C and C++: volk's device table changes layout with it.
if(WIN32)
  list(APPEND RR_N64_DEFS OS_WINDOWS MINGW UNICODE WIN64 VK_USE_PLATFORM_WIN32_KHR)
  target_include_directories(rr_n64_api INTERFACE ${PRSP}/win32/mman)
  target_link_libraries(rr_n64_api INTERFACE -pthread winmm)
else()
  list(APPEND RR_N64_DEFS OS_LINUX)
  target_link_libraries(rr_n64_api INTERFACE -pthread dl m)
endif()
target_compile_definitions(rr_n64_api INTERFACE ${RR_N64_DEFS})
# The core's own code (and the generated blocks, which compile its instruction functions) is built as upstream builds it.
set(RR_N64_CORE_FLAGS -O2 -fsigned-char -fno-strict-aliasing -fcommon -fno-fast-math -w)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "AMD64|x86_64|amd64")
  list(APPEND RR_N64_CORE_FLAGS -msse2)
endif()

# The machine itself, built once per adaptation and toolchain (its sources never change with a game); a game's build names the
# library built so (RR_N64_PREBUILT_CORE) instead of compiling it again. Our hooks (n64_cpu.c) are not in it: they hold the
# game's blocks.
set(RR_N64_PREBUILT_CORE "" CACHE FILEPATH "The machine library built from this tree")
if(RR_N64_PREBUILT_CORE)
  add_library(rr_n64_core STATIC IMPORTED)
  set_target_properties(rr_n64_core PROPERTIES IMPORTED_LOCATION "${RR_N64_PREBUILT_CORE}" INTERFACE_LINK_LIBRARIES rr_n64_api)
else()
  add_library(rr_n64_core STATIC ${CORE_C} ${PNG_C} ${MINIZIP_C} ${ZLIB_C} ${LIBRETRO_C} ${RSP_C} ${PRDP_CXX} ${PRDPI}/volk/volk.c
    ${PRSP_CXX} ${PRSP_C} ${GLUE}/parallel_glue.cpp n64_stubs.c)
  target_link_libraries(rr_n64_core PUBLIC rr_n64_api)
  target_compile_options(rr_n64_core PRIVATE ${RR_N64_CORE_FLAGS}
    $<$<COMPILE_LANGUAGE:C>:-std=gnu11> $<$<COMPILE_LANGUAGE:CXX>:-std=gnu++17 -fpermissive>)
  set_source_files_properties(${PRSP}/lightning/lib/lightning.c PROPERTIES COMPILE_DEFINITIONS HAVE_MMAP=1)
  set_source_files_properties(${PRDPI}/parallel-rdp/rdp_renderer.cpp PROPERTIES COMPILE_OPTIONS "-include;cstdlib")
endif()

# A game's own objects, linked into its executable before the machine library: the hooks of the VR4300 (n64_cpu.c), the generated
# native blocks (blocks/*.c, each calling the core's own instruction functions of n64_exec.h with constant opcodes) and the session.
set(RR_N64_GAME_C n64_cpu.c)
if(RR_N64_GENERATED)
  file(GLOB RR_N64_BLOCKS "${RR_N64_GENERATED}/blocks/*.c")
  if(NOT RR_N64_BLOCKS)
    message(FATAL_ERROR "RR_N64_GENERATED holds no blocks")
  endif()
  list(APPEND RR_N64_GAME_C ${RR_N64_BLOCKS})
  set_source_files_properties(n64_cpu.c PROPERTIES COMPILE_DEFINITIONS RR_N64_NATIVE=1)
endif()
set_source_files_properties(${RR_N64_GAME_C} PROPERTIES COMPILE_OPTIONS "${RR_N64_CORE_FLAGS};-std=gnu11")
set_source_files_properties(n64_session.cpp PROPERTIES COMPILE_OPTIONS "-O2;-fno-fast-math;-std=gnu++17")

# The quick-state key: states of different builds are never mixed.
set(RR_STATE_INPUT "n64-state-v1|${CMAKE_SYSTEM_NAME}|${CMAKE_SYSTEM_PROCESSOR}|${CMAKE_SIZEOF_VOID_P}|${CMAKE_C_COMPILER_ID}|${RR_N64_STATE_INPUT}")
foreach(RR_STATE_SOURCE n64_session.cpp n64_session.h n64_cpu.c "${RR_N64_TREE}/../ready.json")
  if(NOT IS_ABSOLUTE "${RR_STATE_SOURCE}")
    set(RR_STATE_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/${RR_STATE_SOURCE}")
  endif()
  file(SHA256 "${RR_STATE_SOURCE}" RR_STATE_HASH)
  string(APPEND RR_STATE_INPUT "|${RR_STATE_HASH}")
endforeach()
if(RR_N64_GENERATED)
  file(SHA256 "${RR_N64_GENERATED}/blocks/table.c" RR_STATE_HASH)
  string(APPEND RR_STATE_INPUT "|native|${RR_STATE_HASH}")
endif()
string(SHA256 RR_STATE_ABI "${RR_STATE_INPUT}")

if(NOT RR_RECOMP_VERSION)
  set(RR_RECOMP_VERSION "dev")
endif()
add_executable(n64_player n64_player.c n64_session.cpp ${RR_N64_GAME_C} "${RR_COMMON_NATIVE}/platform_io.c")
target_include_directories(n64_player PRIVATE "${RR_COMMON_NATIVE}" "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(n64_player PRIVATE rr_n64_core)
set_target_properties(n64_player PROPERTIES OUTPUT_NAME "RetroRecomp-N64")
target_compile_definitions(n64_player PRIVATE RR_RECOMP_VERSION="${RR_RECOMP_VERSION}" SDL_MAIN_HANDLED RR_N64_STATE_ABI="${RR_STATE_ABI}")
target_compile_options(n64_player PRIVATE -O2 -fno-fast-math)
if(WIN32)
  target_link_options(n64_player PRIVATE -static)
endif()
target_sources(n64_player PRIVATE "${RR_COMMON_NATIVE}/retro_menu.c")
foreach(RR_KIT_FILE audio events input main menu options pointer ring timing video)
  target_sources(n64_player PRIVATE "${RR_COMMON_NATIVE}/hostkit/shell/rrhk_${RR_KIT_FILE}.c")
endforeach()
target_compile_definitions(n64_player PRIVATE RR_N64_WINDOWED=1)
find_package(SDL2 CONFIG REQUIRED)
if(TARGET SDL2::SDL2-static)
  target_link_libraries(n64_player PRIVATE SDL2::SDL2-static)
else()
  target_link_libraries(n64_player PRIVATE SDL2::SDL2)
endif()
if(WIN32)
  target_link_libraries(n64_player PRIVATE gdi32 shell32 user32 ws2_32)
endif()

if(RR_N64_PAYLOAD_DIR)
  target_include_directories(n64_player PRIVATE "${RR_N64_PAYLOAD_DIR}")
  target_compile_definitions(n64_player PRIVATE RR_N64_LINKED)
  if(WIN32)
    # No console window for the game; the headless validation entry stays.
    target_link_options(n64_player PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)
    enable_language(RC)
    target_sources(n64_player PRIVATE "${RR_N64_PAYLOAD_DIR}/game_resources.rc" "${RR_N64_PAYLOAD_DIR}/game_metadata.rc")
  else()
    enable_language(ASM)
    target_sources(n64_player PRIVATE "${RR_N64_PAYLOAD_DIR}/embedded_resources.S" "${RR_N64_PAYLOAD_DIR}/embedded_resources.c")
  endif()
endif()
