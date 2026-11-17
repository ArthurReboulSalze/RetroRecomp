cmake_minimum_required(VERSION 3.21)
project(RetroPlayerGamepad C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
add_library(retro_gamepad SHARED ../../native/player_gamepad.c)
# Windows: one name with every compiler (mingw would otherwise call it libretro_gamepad.dll). Linux keeps the usual
# lib prefix, the name the converter loads (libretro_gamepad.so; the 1.8.0 Linux build stopped without it).
if(WIN32)
  set_target_properties(retro_gamepad PROPERTIES PREFIX "")
endif()
target_link_libraries(retro_gamepad PRIVATE SDL2::SDL2-static)
if(NOT MSVC)
  target_compile_options(retro_gamepad PRIVATE -O2 -fvisibility=hidden)
  # --exclude-libs is a GNU ld option for ELF; lld in mingw mode (llvm-mingw, the portable toolchain) refuses it, and
  # a Windows DLL exports only what is marked __declspec(dllexport) anyway.
  if(WIN32)
    target_link_options(retro_gamepad PRIVATE -s)
  else()
    target_link_options(retro_gamepad PRIVATE -Wl,--exclude-libs,ALL -s)
  endif()
endif()
