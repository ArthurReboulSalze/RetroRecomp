# vAmiga Core and Moira

The Commodore Amiga profile (experimental, developer installations only: [AMIGA.md](../docs/AMIGA.md)) runs its games on the Amiga
machine of [vAmiga](https://github.com/dirkwhoffmann/vAmiga) by Dirk W. Hoffmann, pinned at
[`f51a6bf9e4e19387a27a31b149ef298f6f6807f8`](https://github.com/dirkwhoffmann/vAmiga/tree/f51a6bf9e4e19387a27a31b149ef298f6f6807f8)
(`retrorecomp/amiga_vamiga.py`, `VAMIGA_REV`). The converter fetches that revision into the workspace on the first conversion;
nothing of vAmiga is stored in this repository.

vAmiga's own `LICENSE` page divides the project in three parts, and Retro-Recomp uses two of them:

| Part | Where | Terms | Used by Retro-Recomp |
| --- | --- | --- | --- |
| The vAmiga application | everything outside `Core/` | GPL-3.0 or later | No: not compiled, not copied, not read to write ours |
| The Amiga machine (the "Core") | `Core/` | **Mozilla Public License 2.0**, stated in each file's header | Yes: the Core files we compile |
| The CPU emulator Moira | `Core/Components/CPU/Moira` | **MIT License**, stated in each file's header | Yes: its instruction templates run the 68000, and the generated native steps call them |

## Mozilla Public License 2.0 (the Core)

The Core files we compile are published under the Mozilla Public License, version 2.0. Their headers read: "Licensed under the
Mozilla Public License v2. See https://mozilla.org/MPL/2.0 for license information." The full text is at
<https://mozilla.org/MPL/2.0/>; it is a file-level (weak) copyleft licence.

* **Our changes to those files are MPL-2.0 too.** `retrorecomp/amiga_vamiga.py` copies `Core/` of the pinned revision into a build
  folder and applies a list of text replacements (each must find its pinned text exactly once, so an upstream change fails loudly
  instead of building something else). The modified Core files stay under the MPL-2.0, keep their headers and their notices, and
  the replacements are the readable record of every change: that script is the "Source Code Form" of our modifications, under
  the MIT licence of Retro-Recomp as a script, and the text it inserts into an MPL-2.0 file is MPL-2.0.
* **Our own files are not covered by the MPL-2.0.** The glue around the machine (`native/amiga_machine/`, the resload layer
  `native/amiga_whdload/`, the host-kit adapter, the converter modules) is Retro-Recomp's own code under the MIT licence; it
  uses the Core through its interfaces and contains no Core file.
* **Source availability.** The pinned revision is public at the address above. A distributed executable that contains compiled Core
  files is accompanied by this notice, the revision, and the build script that shows every change we made.

## MIT License (Moira)

Moira, the 68000 core inside the Core, is published under the MIT License. Its files say "Copyright (C) Dirk W. Hoffmann" and
"Published under the terms of the MIT License"; vAmiga's `LICENSE` page names the MIT License for it without a full text, so the
standard text is reproduced here. The few Moira files that `retrorecomp/amiga_vamiga.py` changes (so that a guarded native step
can call an instruction's template and a hook can run it instead of the jump table) stay MIT.

```
MIT License

Copyright (C) Dirk W. Hoffmann

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Third-party files inside the Core

The Core folder also holds a few files with notices of their own (the single-header JSON and HTTP libraries, MIT; the DMS decruncher
under `rvlib/ThirdParty/xdms`; the expansion-ROM tables under `Components/Zorro`, from AmiEmu). Each keeps its own header. Only
the files the Amiga build compiles matter here; the list is completed when `native/amiga_machine/CMakeLists.txt` is final, and a
file whose terms are not clear is left out of the build rather than carried.

## What is not used

* The vAmiga application (GPL-3.0 or later), its manuals and its graphical front end.
* Any Kickstart or other firmware: the machine is given an authored boot ROM, and no Commodore or Cloanto code is stored, fetched
  or shipped by Retro-Recomp.
* WHDLoad itself: it is closed source and is not run. Our MIT resload layer replaces the part of it a game calls.
