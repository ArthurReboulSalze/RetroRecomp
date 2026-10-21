cmake_minimum_required(VERSION 3.20)
project(RetroRecompX68000DevCpu LANGUAGES C CXX)
# Private CPU qualification target. Composite PX68k terms remain unresolved
# for distribution; this is deliberately outside converter/release packaging.
set(RR_X68000_GENERATED "" CACHE PATH "Private offline CPU descriptors")
if(NOT EXISTS "${RR_X68000_GENERATED}/m68kcpu.c")
    message(FATAL_ERROR "Run tools/x68000_native.py to prepare the CPU experiment")
endif()
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../x68000_reference" reference)
set_target_properties(x68000_reference_host PROPERTIES OUTPUT_NAME "RetroRecomp-X68000-Native")
get_target_property(RR_CORE_SOURCES rr_px68k_reference SOURCES)
if(RR_X68000_MACHINE_BASE STREQUAL "hissorii")
    # The 74ddbb3 tree already runs Geolith's Musashi through our MIT binding
    # (base74/cpu_bus.c); only the interpreter loop is swapped for the
    # generated dispatcher.
    list(FILTER RR_CORE_SOURCES EXCLUDE REGEX "/m68000/musashi/m68k(cpu|ops)\\.c$")
    if(EXISTS "${RR_X68000_GENERATED}/m68000.c")
        message(FATAL_ERROR "Stale PX68k m68000.c in ${RR_X68000_GENERATED}; regenerate for the hissorii base")
    endif()
    set(RR_GENERATED_BINDING)
else()
    list(REMOVE_ITEM RR_CORE_SOURCES "${PX68K_DIR}/m68000/musashi/m68kcpu.c")
    list(REMOVE_ITEM RR_CORE_SOURCES "${PX68K_DIR}/m68000/musashi/m68kops.c")
    list(REMOVE_ITEM RR_CORE_SOURCES "${PX68K_DIR}/m68000/m68000.c"
        "${PX68K_DIR}/m68000/musashi/softfloat/softfloat.c")
    set(RR_GENERATED_BINDING "${RR_X68000_GENERATED}/m68000.c")
endif()
set_property(TARGET rr_px68k_reference PROPERTY SOURCES "${RR_CORE_SOURCES}")
file(GLOB RR_GENERATED_STEPS CONFIGURE_DEPENDS "${RR_X68000_GENERATED}/steps/*.c")
target_sources(rr_px68k_reference PRIVATE
    "${RR_X68000_GENERATED}/m68kcpu.c"
    ${RR_GENERATED_BINDING}
    "${RR_X68000_GENERATED}/musashi/m68kops.c"
    "${RR_X68000_GENERATED}/cpu.c" "${RR_X68000_GENERATED}/arithmetic.c"
    observe.c guard_checks.c ${RR_GENERATED_STEPS})
get_filename_component(RR_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
target_include_directories(rr_px68k_reference BEFORE PRIVATE "${RR_X68000_GENERATED}/musashi")
target_include_directories(rr_px68k_reference PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RR_X68000_GENERATED}" "${RR_ROOT}/native")
if(NOT RR_X68000_MACHINE_BASE STREQUAL "hissorii")
    target_include_directories(rr_px68k_reference PRIVATE "${PX68K_DIR}/m68000/musashi")
endif()
target_compile_definitions(x68000_reference_host PRIVATE RR_X68000_DEVCPU)
target_compile_definitions(rr_px68k_reference PRIVATE RR_X68000_EXTENDED_CPU_STATE)
target_include_directories(x68000_reference_host PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
