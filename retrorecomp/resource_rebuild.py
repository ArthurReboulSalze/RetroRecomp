"""The files a game's resources embed, named to its build (MIT): a changed ROM, image or icon rebuilds the resources that carry it.

The resource compiler (llvm-rc, rc.exe) reads the files content.rc names (RCDATA, ICON, and the .rc files it includes) but reports
none of them to the build, and neither does the assembler's .incbin in the Linux embedding (embedded_resources.S). A work folder
converted again with other bytes under the same names (another image of the same snapshot, a reviewed joystick, another firmware)
then linked the old resources. Found on the ZX Spectrum, 22 November 2026: Match Day II's replay caught it; Head over Heels' stale
joystick byte, which only the window reads, was not caught.

`CMAKE_LINES` are machine-neutral CMake, written after the `game` target: when the project is configured, they read content.rc
(and each .rc file it includes) and embedded_resources.S, and give each of them the files it embeds as OBJECT_DEPENDS; content.rc,
the .rc files it includes and embedded_resources.S are configure dependencies, so a change to what they name configures again. The
build itself then tracks the embedded files: no file is touched by hand, and an unchanged project builds nothing.

On main the Z80-chain machines use it (the ZX Spectrum, the SG-1000, the ColecoVision, the MSX family, the Amstrad CPC). The CPS-1,
the PC Engine, the PC Engine CD and the PlayStation keep their own « touch content.rc », and the Game Boy Advance and the Neo Geo
have none: they move to this helper on their owners' branches.
"""
from __future__ import annotations

_CMAKE = r'''# The files the resources embed rebuild them (retrorecomp/resource_rebuild.py): the resource compiler and the assembler's .incbin
# report nothing they read, so the build names it, from content.rc (and the .rc files it includes) and from embedded_resources.S.
function(rr_embedded_depends source pattern)
  set(rr_path "${CMAKE_CURRENT_SOURCE_DIR}/${source}")
  if(NOT EXISTS "${rr_path}")
    return()
  endif()
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${rr_path}")
  file(STRINGS "${rr_path}" rr_lines REGEX "${pattern}")
  set(rr_files)
  foreach(rr_line IN LISTS rr_lines)
    if(rr_line MATCHES "\"([^\"]+)\"")
      set(rr_file "${CMAKE_MATCH_1}")
      if(NOT IS_ABSOLUTE "${rr_file}")
        set(rr_file "${CMAKE_CURRENT_SOURCE_DIR}/${rr_file}")
      endif()
      list(APPEND rr_files "${rr_file}")
      if(rr_line MATCHES "^#include" AND EXISTS "${rr_file}")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${rr_file}")
        file(STRINGS "${rr_file}" rr_inner REGEX "[ \t](RCDATA|ICON)[ \t]+\"")
        foreach(rr_in IN LISTS rr_inner)
          if(rr_in MATCHES "\"([^\"]+)\"")
            list(APPEND rr_files "${CMAKE_CURRENT_SOURCE_DIR}/${CMAKE_MATCH_1}")
          endif()
        endforeach()
      endif()
    endif()
  endforeach()
  set_source_files_properties(${source} PROPERTIES OBJECT_DEPENDS "${rr_files}")
endfunction()
rr_embedded_depends(content.rc "^#include[ \t]+\"|[ \t](RCDATA|ICON)[ \t]+\"")
rr_embedded_depends(embedded_resources.S "\\.incbin")'''

CMAKE_LINES: tuple[str, ...] = tuple(_CMAKE.splitlines())
