# Mupen64Plus-Next (the Nintendo 64 machine)

The Nintendo 64 profile (experimental: [NINTENDO_64.md](../docs/NINTENDO_64.md)) runs its games on the libretro core
[Mupen64Plus-Next](https://github.com/libretro/mupen64plus-libretro-nx), pinned at
[`15bada85906593376e8fd697f1b0b3af3a20f512`](https://github.com/libretro/mupen64plus-libretro-nx/tree/15bada85906593376e8fd697f1b0b3af3a20f512)
(`retrorecomp/n64_core.py`, `CORE_REV`). The converter fetches that revision into the workspace on the first conversion; nothing of
it is stored in this repository. Its authors are the Mupen64Plus team, the libretro contributors and, for its parts, those named
below and in each file.

## An exported Nintendo 64 game is distributed under the GNU GPL, version 3

What an exported game contains, and the terms of each part (every file the compiler reads was checked against its own notice; the
check is repeated for every change of the pin):

| Part | Licence |
|---|---|
| Mupen64Plus core (`mupen64plus-core`), its HLE RSP plugin and the libretro glue `libretro/libretro.c` | GPL-2.0-or-later |
| The cxd4 RSP interpreter (`mupen64plus-rsp-cxd4`) | CC0-1.0 |
| ParaLLEl-RSP (`mupen64plus-rsp-paraLLEl`) | MIT |
| GNU Lightning, the code generator of ParaLLEl-RSP | LGPL-3.0-or-later |
| ParaLLEl-RDP and its Vulkan helpers (`mupen64plus-video-paraLLEl/parallel-rdp`) | MIT |
| The Vulkan headers and volk | Apache-2.0 / MIT |
| libretro-common | MIT |
| zlib, libpng, minizip, md5, xxHash (in `custom/` and `mupen64plus-core/subprojects/`) | Zlib, Libpng, Zlib, Public Domain, BSD-2-Clause |
| The OS-abstraction files of GLideN64 (`osal_files_*.c`, Mupen64Plus code) | GPL-2.0-or-later |

GNU Lightning is LGPL-3.0-or-later and the Vulkan headers are Apache-2.0: both are compatible with the GPL version 3 and not with
version 2 only. So a program that contains the Mupen64Plus core (GPL-2.0-or-later) with them is distributed under the **GNU
General Public License, version 3**. Its full text: <https://www.gnu.org/licenses/gpl-3.0.html>.

What this means for an exported game:

* **The whole program is GPL-3.0.** Retro-Recomp's own files in it (the session, the player and the VR4300 hooks in
  `native/n64_machine/`, our glue in `native/n64_machine/glue/`, the host kit, the converter's generated blocks) keep their MIT
  notice, which the GPL allows; the combined program is under the GPL, version 3. The generated native blocks compile the core's own
  instruction functions (`n64_exec.h`, taken from `pure_interp.c` at build time) and so carry its GPL-2.0-or-later terms.
* **Its corresponding source** is: Mupen64Plus-Next at the pinned revision above; the changes Retro-Recomp applies to it at build
  time, listed one by one in `retrorecomp/n64_core.py` (`REPLACEMENTS` and the split of the pure interpreter, each a readable text
  replacement that must find its pinned text exactly once); and Retro-Recomp's own sources at the version named in the game's
  notices (<https://github.com/ArthurReboulSalze/Retro-Recomp>). Our changes to the core's files are GPL-2.0-or-later, like those
  files.
* **The game's data is not part of the program's source.** The cartridge image embedded in an export is the player's own; the GPL
  does not make it redistributable, and Retro-Recomp distributes none.
* **No noncommercial code** is in the program.

## Parts of the pinned core that are never used

* **angrylion-rdp-plus** (`mupen64plus-video-angrylion`) is under the old MAME licence, which forbids commercial use. It is never
  copied out of the checkout, never compiled and never in an export or its sources; the converter refuses to build if any angrylion
  file reaches the build folder.
* **The GLideN64 renderer** is GPL-2.0-only, which cannot be combined with GNU Lightning and the Apache-2.0 Vulkan headers: it is
  not compiled. Only its two OS-abstraction files (Mupen64Plus code, GPL-2.0-or-later) are.
* **Eleven upstream files with no licence notice** (the ParaLLEl plugin glue, `z64.h`, the plugin specification header and five
  small libretro headers) are not copied: Retro-Recomp's own MIT files in `native/n64_machine/glue/`, written from the interfaces
  they implement, stand in for those it needs. Their authors were not asked for anything.
* **The new dynamic recompiler** is not compiled: the core's interpreters run, and the native blocks replace hot code.

## Changes Retro-Recomp makes to the core (build time)

Recorded in `retrorecomp/n64_core.py`: only the parts listed in `COPIED` are copied into a build folder; libretro.c includes our
glue's interface; the pure interpreter is split into `n64_exec.h` (its instruction functions and an always-inlined `execute_op`)
and a run loop that calls the hooks of the native blocks and of the observation; the cached interpreter counts the instructions it
runs; the built-in ROM database is read from memory instead of being written into a folder of the host and read back.
