# ScummVM runtime patch (GPL-3.0-or-later)

This folder is a **derivative of ScummVM** and is licensed under the **GNU General Public License, version 3 or (at your
option) any later version** (full text in [LICENSE](LICENSE)). It is separate from Retro-Recomp's own code, which is MIT:
nothing here is compiled into the converter, and the converter's MIT code does not include or link any of it. The converter
only starts the build of the patched ScummVM (a separate program) and appends the player's game files to the result.

ScummVM itself is not in this repository. The build fetches the pinned release from <https://github.com/scummvm/scummvm>
(the tag and commit are declared in `retrorecomp/scummvm_build.py` and listed in `docs/UPSTREAMS.md`) and applies the patch
series below. ScummVM is the legal property of its developers (see the COPYRIGHT file of the ScummVM tree). FreeType, built
with it, is under the FreeType License (FTL).

## Patch series

| Patch | What it does |
|---|---|
| `patches/0001-retrorecomp-pack-launch-nodialog.patch` | A read-only file system (`backends/fs/packed/`) that serves `pack:\` from files stored byte for byte at the end of the executable; started with no argument, an executable that carries a game runs it with its configuration, saves and log in `datas/games/<Game>-<id>/` next to it, and the interface language of `datas/Retro-Recomp.ini` (en, fr, de, es, it; anything else gives English) as ScummVM's GUI language; the platform creates no folder outside `datas/` in that mode; no modal window (assertions and runtime errors go to stderr, SDL message boxes are skipped under `RR_NO_DIALOGS`); an authored self-test of the pack streams (`RR_PACK_SELFTEST`). |
| `patches/0003-retrorecomp-theme-colours.patch` | The colours of the default theme (`gui/themes/scummremastered`), dark and gold: its palette, the colours written in it, and four check box and radio button icons. No font, layout or file is added. The build makes the theme's zip again from the patched folder. |
| `patches/0002-retrorecomp-options-page.patch` | A "Retro-Recomp" page in the in-game options of an executable that carries a game (menu language, full screen, scaling, volumes, a button to the keys and pad), and the settings shared through `datas/Retro-Recomp.ini` section `[Adventure]`: applied at the start of every adventure executable of the folder, copied back when the run ends. |

Pack layout: `[program][file data ...][index][trailer]`; trailer = `RRADVPK1`, index offset (u64), index size (u64), little
endian; index entry = u16 path length, UTF-8 path with `/`, u64 offset, u64 size. The launch manifest is the pack file
`.rr/launch.ini` (`target`, `name`, `id`).

## Corresponding source

Every executable built from this patch is distributed with the GPL text and a written offer of the corresponding source: the
pinned ScummVM and FreeType trees, this folder, and the build script (`retrorecomp/scummvm_build.py`).
`tools/build_scummvm_source_archive.py` writes that archive.
