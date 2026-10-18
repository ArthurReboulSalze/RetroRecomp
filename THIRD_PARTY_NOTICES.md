# Third-party notices and licensing scope

The root [MIT license](LICENSE) applies to original RetroRecomp contributions.
It does not relicense third-party code, upstream excerpts used by adapters,
ROMs, artwork, or generated games. Project branding identifies RetroRecomp;
the software license does not grant trademark rights.

## Converter credits music

The credits replay three original four-channel MOD compositions supplied by
Arthur Reboul Salze and created with
[ChipLoom](https://github.com/ArthurReboulSalze/ChipLoom). The converter's native
player statically includes libxmp-lite 4.7.3 and miniaudio 0.11.23; their complete
notices and source links are [included here](assets/credits/NOTICE.md) and in the
credits' legal-notice viewer. These components are not linked into game exports.

## SMS/GG upstream permission and limits

RetroRecomp depends on **mstan/smsggrecomp** at revision
`224d5bb2c150a2c295033d35dec629ef9ee42940`. Its
[pinned README](https://github.com/mstan/smsggrecomp/tree/224d5bb2c150a2c295033d35dec629ef9ee42940#license)
states that its license is **not yet declared**. Public availability on GitHub
is not a general redistribution license. The RetroRecomp project owner reports
receiving the author's explicit permission to use the engine in a
**noncommercial capacity**, with a request for attribution. We credit
[mstan/smsggrecomp](https://github.com/mstan/smsggrecomp) here and in the
[README](README.md). This is a permission communicated to the project owner,
not a published license for all downstream users or commercial use.

The full engine is downloaded during local setup rather than bundled in the
converter executable. Adapters reference and replace portions of upstream code; any
upstream-derived material remains subject to its author's rights. The author's
message does not specify general downstream licensing terms; do not interpret
the MIT badge as clearing the entire toolchain for unrestricted redistribution.

The engine's shared **z80-recomp-core** at revision
`0e6606a41245d54c5fd0c3dc322ef9d6890d3923` uses
**PolyForm Noncommercial 1.0.0**, with an additional clarification from its
author. Its full [license](licenses/z80-recomp-core.md) is retained, including
the commercial licensing contact. This limits permitted uses of that core;
RetroRecomp's MIT license does not remove those limitations.

## Game toolchain and validation

| Component | Terms | Included notice |
| --- | --- | --- |
| smsggrecomp | No public license declared at the pinned revision; project owner reports explicit noncommercial permission with attribution | Limits above |
| z80-recomp-core | PolyForm Noncommercial 1.0.0 and author clarification | [Full text](licenses/z80-recomp-core.md) |
| superzazu/z80 reference interpreter | MIT; copyright Nicolas Allemand | [Full text](licenses/superzazu-z80.md) |
| SDL2 | zlib; copyright Sam Lantinga | [Full text](licenses/SDL2.md) |
| xBR-lv2 pixel-art filter | MIT; copyright Hyllian; CPU/SDL adaptation by RetroRecomp | [Full text and pinned source](licenses/xbr.md) |
| SingleStepTests/z80 independent vectors | MIT; copyright SingleStepTests | [Full text](licenses/SingleStepTests-z80.md) |
| SingleStepTests/m68000 independent CPU fixtures | MIT; copyright SingleStepTests; development tests only | [Full text](licenses/SingleStepTests-m68000.md) |
| arcanite24/gb-recompiled (Game Boy compiler and generated runtime) | MIT; copyright arcanite24 | [Full text](licenses/gb-recompiled.md) |
| Dear ImGui in the Game Boy runtime | MIT; copyright Omar Cornut | [Full text](licenses/dear-imgui.md) |
| mstan/nesrecomp NES compiler and generated cycle runtime | PolyForm Noncommercial 1.0.0; copyright Matthew Stanley | [Full text](licenses/nesrecomp.md) |
| emu2413 in the NES runtime | MIT; copyright Mitsutaka Okazaki | [Full text](licenses/emu2413.md) |
| segagenesisrecomp and m68k-recomp-core (experimental Mega Drive) | PolyForm Noncommercial 1.0.0 plus retained vendor licences | [Notices](licenses/segagenesisrecomp.md) |
| RetroPortingToolKit/snesrecomp (experimental SNES) | PolyForm Noncommercial 1.0.0 plus MIT/ISC and other retained vendor licences | [Notices](licenses/snesrecomp.md) |
| SuperMarioWorldRecomp game analysis | PolyForm Noncommercial 1.0.0 | [Full text](licenses/SuperMarioWorldRecomp.md) |
| Geolith (experimental Neo Geo hardware runtime) | BSD-3-Clause with retained component notices | [Full text](licenses/geolith.md) |
| lithogen and the ROM-free Neo Geo layout catalogue | BSD-3-Clause; Rupert Carmichael and attributed MAME contributors | [Full text and attribution](licenses/lithogen.md) |

Game toolchain source and test vectors are not bundled in the converter executable.
Generated games contain parts of that toolchain and the user's ROM. They are
not automatically covered by the root MIT license and are not distributed here.

## Packaged Windows converter

The experimental Neo Geo converter profile and developer tool use
[Geolith](https://github.com/libretro/geolith-libretro/tree/2dc88e3fa72ff404213a65d6eb5bb33baa687f73)
and [lithogen](https://github.com/carmiker/lithogen/tree/ef0f9bd94e31689def44b49e0f8351e0206b622d).
Their BSD-3-Clause notices, Musashi/Z80/miniz MIT notices, YMFM/Speex notices,
dr_flac alternatives, SDL2 and UPX terms are retained in its embedded component
notice. The loader's MAME-derived layout/decryption notices remain in its source.
No cartridge or BIOS files are distributed with the converter; the private
prototype embeds only locally supplied data. See [prototype scope](docs/NEOGEO.md).

The native Neo Geo prototype also reuses the existing qualified 68000 decoder
and instruction semantics from the pinned GenesisRecomp/m68k-recomp-core
integration. Their applicable notices remain embedded alongside Geolith's
component notices. No proprietary BIOS is redistributed with Retro-Recomp.
Free BIOS replacements are research candidates only, not bundled dependencies.

| Component | Release build | Included notice |
| --- | --- | --- |
| CPython and bundled runtime components | 3.14.5; PSF and component licenses | [Full text](licenses/Python.md) |
| Tcl/Tk | 8.6.15; Tcl/Tk license | [Full text](licenses/Tcl-Tk.md) |
| Pillow and bundled image codecs | 12.3.0; MIT-CMU and component licenses | [Full text](licenses/Pillow.md) |
| PyInstaller | 6.22.3; GPLv2+ with distribution exception | [Full text and exception](licenses/PyInstaller.md) |
| PyInstaller hooks | 2026.7; component terms in the hook package | [Full text](licenses/PyInstaller-hooks.md) |
| UPX executable packer | 5.2.1; GPL with special exception for packed executables | [Full text and exception](licenses/UPX.md), [corresponding source](licenses/upx-5.2.1-src.tar.xz) |
| OpenSSL | 3.0.20; Apache 2.0 | [Full text](licenses/OpenSSL.md) |
| zlib / zlib-ng | zlib terms; CPython uses zlib-ng 2.2.4 | [zlib](licenses/zlib.md), [zlib-ng](licenses/zlib-ng.md) |

PyInstaller's exception permits distribution of frozen applications under
their own license, subject to the application's dependencies. It does not
change those dependencies' licenses. Python and Pillow notices include the
additional components shipped with their respective distributions.

Full notice files are reproduced from the installed packages or the pinned
upstream sources and bundled inside `Retro-Recomp.exe`. The matching
[UPX source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz)
is maintained separately in the public repository and linked from Credits.
The executable download page must also link to that archive. No ROMs, box art,
personal settings, compilation
memories or generated commercial game executables accompany this release.

## Linux menu bitmap font

Linux drag-and-drop and protected cover accounts use tkinterdnd2/tkdnd and
SecretStorage. See [licenses/Linux-desktop.md](licenses/Linux-desktop.md).
The Linux converter also embeds the installed packages' complete notices in
`third-party-runtime/`, including their cryptography dependencies.

The Linux menu embeds the printable ASCII subset of X.Org's Misc Fixed 6x10
bitmap, without resampling. Its original notice is: "Public domain font. Share
and enjoy." The source and checksum are retained in `native/font6x10.h`.
Source: https://sources.debian.org/src/xfonts-base/1%3A1.0.5%2Bnmu1/font-misc-misc/6x10.bdf/

## Multilingual menu fonts

The interface uses renamed subsets of Noto Sans CJK, and generated games use
a small Noto-derived glyph atlas. Copyright Adobe and Google;
SIL Open Font License 1.1. The complete notice is retained in
[licenses/Noto.md](licenses/Noto.md). Full source fonts are not bundled.
