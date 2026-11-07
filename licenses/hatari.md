# Hatari (the Atari ST machine) and the libretro API header

The Atari ST profile (experimental: [ATARI_ST.md](../docs/ATARI_ST.md)) runs its games on [Hatari](https://github.com/hatari/hatari)
by the Hatari team (its `doc/authors.txt`), pinned at
[`c453b85f811fc11bed10e19e5e48fe95377e5a23`](https://github.com/hatari/hatari/tree/c453b85f811fc11bed10e19e5e48fe95377e5a23)
(`retrorecomp/atarist_hatari.py`, `HATARI_REV`). The converter fetches that revision into the workspace on the first conversion;
nothing of Hatari is stored in this repository.

## An exported Atari ST game is distributed under the GNU GPL, version 2

Hatari is free software: "you can redistribute it and/or modify it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License, or (at your option) any later version" (its `readme.txt`).
Three headers of its CPU core taken from WinUAE (`src/cpu/uae/attributes.h`, `types.h`, `vm.h`) say "Licensed under the terms of the
GNU General Public License version 2" without "or later", so a program that contains Hatari's CPU, as every Atari ST game exported by
Retro-Recomp does, is distributed under the **GNU General Public License, version 2**. Its full text is Hatari's `gpl.txt`, at the
pinned revision: <https://github.com/hatari/hatari/blob/c453b85f811fc11bed10e19e5e48fe95377e5a23/gpl.txt>, also at
<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>.

What this means for an exported game:

* **The whole program is GPL-2.0.** Retro-Recomp's own files in it (the Atari ST session and player in `native/atarist_machine/`,
  the host kit, the converter's generated files) keep their MIT notice, which the GPL allows; the combined program is under the
  GPL, version 2.
* **Its corresponding source** is: Hatari at the pinned revision above; the changes Retro-Recomp applies to it at build time, listed
  one by one in `retrorecomp/atarist_hatari.py` (`REPLACEMENTS`, each a readable text replacement that must find its pinned text
  exactly once); the configure options in the same file; and Retro-Recomp's own sources at the version named in the game's notices
  (<https://github.com/ArthurReboulSalze/Retro-Recomp>). Our changes to Hatari's files are GPL-2.0, like those files.
* **The game's data is not part of the program's source.** The floppy images and the TOS image embedded in an export are the
  player's own, or EmuTOS ([emutos.md](emutos.md), under its own GPL, with its complete source in the game); the GPL does not make
  the player's own files redistributable, and Retro-Recomp distributes none of them.
* **No noncommercial code** is in the same program unless its author allowed it: the 68000 decoder of m68k-recomp-core, which
  the native steps use, is included under Matthew Stan's permission of 6 November 2026 to combine it with GPL code in
  Retro-Recomp's exports.

## Hatari parts with other terms

* `src/floppies/ipf_dsk.c` (the IPF reader Retro-Recomp uses; no capsimg library is ever built or linked):
  `SPDX-License-Identifier: BSD-3-Clause`, "Original copyright by: Olivier Galibert (from MAME project)".
* `src/cpu/softfloat/` (QEMU SoftFloat): its own SoftFloat-2a / BSD / GPL-2.0-or-later terms, as in QEMU. Not used by a plain ST
  (no FPU), but compiled with the core.
* `src/debug/a.out.h`: public domain (Guido Flohr).

## Changes Retro-Recomp makes to Hatari (build time)

Recorded in `retrorecomp/atarist_hatari.py`: only the sources are built (no documentation, tests, tools, Python UI); the libretro core
is built as a static library; `src/retro/file_retro.c` includes `windows.h` for its Windows branch; memory snapshots go through the
libretro file system; the built-in IPF reader no longer ejects and reinserts a disk when a state is saved, and a restored state keeps
the saved flux of every track; Hatari's random numbers come from a portable generator saved in states; the cycle-exact 68000 loop
asks the player's step hook before each instruction.

## The libretro API header (MIT)

`native/atarist_machine/libretro/libretro.h` is the libretro API header from
[libretro-common](https://github.com/libretro/libretro-common) at `d9597c359a5ca8399a4e244f816e7e975a92a2aa` (line endings
normalised to LF, otherwise unchanged):

> The following license statement only applies to this libretro API header (libretro.h).
> Copyright (C) 2010-2024 The RetroArch team
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files
> (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify,
> merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included
> in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
> NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
> CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
