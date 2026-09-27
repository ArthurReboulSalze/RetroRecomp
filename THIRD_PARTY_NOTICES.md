# Third-party notices and licensing scope

The root [MIT license](LICENSE) applies to original RetroRecomp contributions.
It does not relicense third-party code, upstream excerpts used by adapters,
ROMs, artwork, or generated games. Project branding identifies RetroRecomp;
the software license does not grant trademark rights.

## Outstanding upstream licensing issue

RetroRecomp depends on **mstan/smsggrecomp** at revision
`224d5bb2c150a2c295033d35dec629ef9ee42940`. Its
[pinned README](https://github.com/mstan/smsggrecomp/tree/224d5bb2c150a2c295033d35dec629ef9ee42940#license)
states that its license is **not yet declared**. Public availability on GitHub
is not a general redistribution license. No additional permission from that
author has been obtained for this release candidate.

The full engine is downloaded during local setup rather than bundled in the
converter ZIP. Adapters reference and replace portions of upstream code; any
upstream-derived material remains subject to its author's rights. An explicit
engine license or permission is still needed to resolve this issue. Do not
interpret the MIT badge as clearing the entire toolchain for redistribution.

The engine's shared **z80-recomp-core** at revision
`0e6606a41245d54c5fd0c3dc322ef9d6890d3923` uses
**PolyForm Noncommercial 1.0.0**, with an additional clarification from its
author. Its full [license](licenses/z80-recomp-core.md) is retained, including
the commercial licensing contact. This limits permitted uses of that core;
RetroRecomp's MIT license does not remove those limitations.

## Game toolchain and validation

| Component | Terms | Included notice |
| --- | --- | --- |
| smsggrecomp | Not declared at the pinned revision | Outstanding issue above |
| z80-recomp-core | PolyForm Noncommercial 1.0.0 and author clarification | [Full text](licenses/z80-recomp-core.md) |
| superzazu/z80 reference interpreter | MIT; copyright Nicolas Allemand | [Full text](licenses/superzazu-z80.md) |
| SDL2 | zlib; copyright Sam Lantinga | [Full text](licenses/SDL2.md) |
| SingleStepTests/z80 independent vectors | MIT; copyright SingleStepTests | [Full text](licenses/SingleStepTests-z80.md) |

Game toolchain source and test vectors are not bundled in the converter ZIP.
Generated games contain parts of that toolchain and the user's ROM. They are
not automatically covered by the root MIT license and are not distributed here.

## Packaged Windows converter

| Component | Release build | Included notice |
| --- | --- | --- |
| CPython and bundled runtime components | 3.14.5; PSF and component licenses | [Full text](licenses/Python.md) |
| Tcl/Tk | 8.6.15; Tcl/Tk license | [Full text](licenses/Tcl-Tk.md) |
| Pillow and bundled image codecs | 12.3.0; MIT-CMU and component licenses | [Full text](licenses/Pillow.md) |
| PyInstaller | 6.22.3; GPLv2+ with distribution exception | [Full text and exception](licenses/PyInstaller.md) |
| PyInstaller hooks | 2026.7; component terms in the hook package | [Full text](licenses/PyInstaller-hooks.md) |
| OpenSSL | 3.0.20; Apache 2.0 | [Full text](licenses/OpenSSL.md) |
| zlib / zlib-ng | zlib terms; CPython uses zlib-ng 2.2.4 | [zlib](licenses/zlib.md), [zlib-ng](licenses/zlib-ng.md) |

PyInstaller's exception permits distribution of frozen applications under
their own license, subject to the application's dependencies. It does not
change those dependencies' licenses. Python and Pillow notices include the
additional components shipped with their respective distributions.

Full notice files are reproduced from the installed packages or the pinned
upstream sources. Their `.md` filenames keep the export free of `.txt` guides;
their license text is retained. No ROMs, box art, personal settings, compilation
memories or generated commercial game executables accompany this release.
