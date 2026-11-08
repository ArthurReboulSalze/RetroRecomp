# ScummVM (runtime of the adventure exes)

Each "Adventure (ScummVM)" executable made by Retro-Recomp is the ScummVM program with Retro-Recomp's patch
([native/scummvm](../native/scummvm/README.md)) and the player's own game files appended to it. That program is licensed under the
**GNU General Public License, version 3 or (at your option) any later version**; the full text is in
[native/scummvm/LICENSE](../native/scummvm/LICENSE) and inside every such executable. ScummVM is the legal property of its
developers, whose names are listed in the COPYRIGHT file of the ScummVM source. The game files remain the property of their
owners; they are the player's own copy and are not covered by the GPL.

| Component | Version | Licence |
| --- | --- | --- |
| ScummVM | tag `v2026.4.0`, commit `7d2709da5136866589f7602f5f5a7b17de03420e` | GPL-3.0-or-later (some third-party parts of ScummVM carry other notices, listed in its `LICENSES/` folder) |
| Retro-Recomp patch | `native/scummvm/patches/` | GPL-3.0-or-later |
| FreeType | tag `VER-2-13-3`, commit `42608f77f20749dd6ddc9e0536788eaad70ea4b5` | FreeType License ([licenses/freetype.md](freetype.md)) |
| SDL2 | the converter's pinned release | zlib ([licenses/SDL2.md](SDL2.md)) |

Retro-Recomp's converter, its build script (`retrorecomp/scummvm_build.py`) and its packer (`retrorecomp/scummvm_export.py`) are
Retro-Recomp's own MIT code: they start the separate ScummVM program and append files to it; none of them includes ScummVM code.

## Written offer of the corresponding source

For at least three years from the date a Retro-Recomp release containing the ScummVM runtime was published, anyone may obtain the
complete corresponding source of that runtime: the ScummVM tree at the commit above, the FreeType tree at the commit above, the
patch series of `native/scummvm`, and the build script `retrorecomp/scummvm_build.py`. Each such release carries this source as a
separate archive, written by `tools/build_scummvm_source_archive.py`, next to its executables in the public repository; the archive
is linked from the release page and from the converter's Credits.
