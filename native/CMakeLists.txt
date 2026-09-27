cmake_minimum_required(VERSION 3.21)
project(RetroRecompGame C RC)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(required ENGINE_DIR GAME_DIR GAME_NAME)
  if(NOT DEFINED ${required})
    message(FATAL_ERROR "${required} is required")
  endif()
endforeach()
find_package(SDL2 CONFIG REQUIRED)
set(RUNNER "${ENGINE_DIR}/runner")
set(GENERATED "${GAME_DIR}/generated")
option(SMSRECOMP_BANKED_AOT "Use native coverage of all Sega ROM banks" ON)
if(SMSRECOMP_BANKED_AOT)
  file(GLOB BANKED_BODIES CONFIGURE_DEPENDS "${GENERATED}/game_banked_ops_*.c")
  if(NOT BANKED_BODIES)
    message(FATAL_ERROR "Missing generated banked native instructions")
  endif()
  set(CPU_SOURCES banked_dispatch.c "${GENERATED}/game_banked_index.c" ${BANKED_BODIES})
  add_compile_definitions(SMSRECOMP_BANKED_AOT)
else()
  set(CPU_SOURCES "${GENERATED}/game_full.c" "${GENERATED}/game_dispatch.c")
endif()
set(RUNTIME_SOURCES
  paths.c
  learning.c
  "${GAME_DIR}/runtime_glue.c"
  "${GAME_DIR}/embedded_rom.c"
  "${GAME_DIR}/runtime_video.c" "${RUNNER}/audio/sn76489.c"
  "${GAME_DIR}/runtime_reference.c"
  ${CPU_SOURCES}
  "${GENERATED}/game_layout.c")
set(ICON_RESOURCE)
if(EXISTS "${GAME_DIR}/game_resources.rc")
  set(ICON_RESOURCE "${GAME_DIR}/game_resources.rc")
endif()
add_executable(${GAME_NAME} WIN32 launcher.c host.c controls.c ui.c icon.c ${ICON_RESOURCE}
  "${GAME_DIR}/runtime_main.c" ${RUNTIME_SOURCES})
set_source_files_properties("${GAME_DIR}/runtime_main.c"
  PROPERTIES COMPILE_DEFINITIONS "main=sms_backend_main")
target_compile_definitions(${GAME_NAME} PRIVATE
  SMS_HAVE_SDL SMSGG_HAVE_GAME_LAYOUT _CRT_SECURE_NO_WARNINGS SDL_MAIN_HANDLED)
target_include_directories(${GAME_NAME} PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}" "${GAME_DIR}" "${GENERATED}" "${RUNNER}" "${RUNNER}/include" "${RUNNER}/video")
target_link_libraries(${GAME_NAME} PRIVATE SDL2::SDL2-static gdi32)
if(MSVC)
  target_compile_options(${GAME_NAME} PRIVATE /W2)
  if(SMSRECOMP_BANKED_AOT)
    target_compile_options(${GAME_NAME} PRIVATE /MP4)
  endif()
endif()

option(SMSRECOMP_HOST_CHECKS "Build local native integration checks" OFF)
option(SMSRECOMP_INPUT_CHECKS "Build authored two-player CPU input checks" OFF)
option(SMSRECOMP_CPU_CHECKS "Build differential banked instruction checks" OFF)
option(SMSRECOMP_ICON_CHECKS "Build hidden Windows icon integration checks" OFF)
if(SMSRECOMP_ICON_CHECKS)
  add_executable(smsrecomp_icon_checks icon_checks.c icon.c ${ICON_RESOURCE})
  target_compile_definitions(smsrecomp_icon_checks PRIVATE _CRT_SECURE_NO_WARNINGS SDL_MAIN_HANDLED)
  target_include_directories(smsrecomp_icon_checks PRIVATE "${GAME_DIR}")
  target_link_libraries(smsrecomp_icon_checks PRIVATE SDL2::SDL2-static)
endif()
if(SMSRECOMP_CPU_CHECKS AND SMSRECOMP_BANKED_AOT)
  set(CHECK_SOURCES ${RUNTIME_SOURCES})
  list(REMOVE_ITEM CHECK_SOURCES "${GAME_DIR}/runtime_glue.c")
  add_executable(smsrecomp_cpu_checks banked_cpu_checks.c ${CHECK_SOURCES})
  target_compile_definitions(smsrecomp_cpu_checks PRIVATE
    SMSGG_HAVE_GAME_LAYOUT _CRT_SECURE_NO_WARNINGS SDL_MAIN_HANDLED)
  target_include_directories(smsrecomp_cpu_checks PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}" "${GAME_DIR}" "${GENERATED}" "${RUNNER}" "${RUNNER}/include" "${RUNNER}/video")
  target_link_libraries(smsrecomp_cpu_checks PRIVATE gdi32)
  if(MSVC)
    target_compile_options(smsrecomp_cpu_checks PRIVATE /MP4 /W2)
  endif()
endif()
if(SMSRECOMP_HOST_CHECKS)
  add_executable(smsrecomp_host_checks host_checks.c icon.c ${ICON_RESOURCE} ${RUNTIME_SOURCES})
  target_compile_definitions(smsrecomp_host_checks PRIVATE
    SMS_HAVE_SDL SMSGG_HAVE_GAME_LAYOUT _CRT_SECURE_NO_WARNINGS SDL_MAIN_HANDLED)
  target_include_directories(smsrecomp_host_checks PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}" "${GAME_DIR}" "${GENERATED}" "${RUNNER}" "${RUNNER}/include" "${RUNNER}/video")
  target_link_libraries(smsrecomp_host_checks PRIVATE SDL2::SDL2-static gdi32)
endif()
if(SMSRECOMP_INPUT_CHECKS)
  add_executable(smsrecomp_input_checks input_checks.c ${RUNTIME_SOURCES})
  target_compile_definitions(smsrecomp_input_checks PRIVATE
    SMSGG_HAVE_GAME_LAYOUT _CRT_SECURE_NO_WARNINGS SDL_MAIN_HANDLED)
  target_include_directories(smsrecomp_input_checks PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}" "${GAME_DIR}" "${GENERATED}" "${RUNNER}" "${RUNNER}/include" "${RUNNER}/video")
  target_link_libraries(smsrecomp_input_checks PRIVATE gdi32)
endif()
