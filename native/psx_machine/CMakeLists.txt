cmake_minimum_required(VERSION 3.20)
project(RetroRecompPlayStation LANGUAGES C)

# The PlayStation session (MIT, ours) on Beetle PSX (GPL-2.0), prepared at build time by retrorecomp/psx_beetle.py.
#   RR_BEETLE_TREE   the prepared Beetle folder (required; it holds rr_sources.cmake)
#   RR_PSX_TOOLS     also build the headless reference tool of the conversion
set(RR_BEETLE_TREE "" CACHE PATH "Prepared Beetle PSX folder")
option(RR_PSX_TOOLS "Build the headless reference tool" ON)
if(NOT RR_BEETLE_TREE OR NOT EXISTS "${RR_BEETLE_TREE}/rr_sources.cmake")
    message(FATAL_ERROR "RR_BEETLE_TREE must name the prepared Beetle PSX folder")
endif()
include("${RR_BEETLE_TREE}/rr_sources.cmake")

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

add_library(rr_beetle STATIC ${RR_BEETLE_SOURCES})
target_include_directories(rr_beetle PUBLIC ${RR_BEETLE_INCLUDES})
target_compile_definitions(rr_beetle PUBLIC ${RR_BEETLE_DEFINES})
if(MSVC)
    target_compile_options(rr_beetle PRIVATE /O2 /w)
else()
    # Beetle's own code is built as upstream builds it (no warnings of ours on it); wrapping signed arithmetic and no
    # type-based aliasing assumptions keep its integer code the same under every compiler.
    target_compile_options(rr_beetle PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)
endif()
if(WIN32)
    target_compile_definitions(rr_beetle PUBLIC _CRT_SECURE_NO_WARNINGS)
else()
    target_link_libraries(rr_beetle PUBLIC m)
endif()

add_library(rr_psx_session STATIC psx_session.c)
target_include_directories(rr_psx_session PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(rr_psx_session PUBLIC rr_beetle)
if(NOT MSVC)
    target_compile_options(rr_psx_session PRIVATE -O2 -Wall -Wextra -Wno-unused-parameter -fno-fast-math)
endif()

if(RR_PSX_TOOLS)
    add_executable(psx_reference psx_reference.c)
    target_link_libraries(psx_reference PRIVATE rr_psx_session)
endif()
