# Nintendo NES profile (experimental)

RetroRecomp identifies `.nes` cartridges, headered `.bin`/`.rom` dumps, and
single-ROM ZIP files, then places their Windows executables in
`Games/Nintendo NES`. The source ROM is read without modification. The
generated executable embeds the cartridge and does not need a separate ROM or
SDL2 DLL. A ROM-specific entry library stays with the converter under
`datas/library/nes`; opening a game does not create learning logs.

The backend is pinned to
[`mstan/nesrecomp` revision `1b0c621`](https://github.com/mstan/nesrecomp/tree/1b0c621a927db17afa9723bf456a89ad15809907).
Its [PolyForm Noncommercial 1.0.0 license](../licenses/nesrecomp.md) permits
noncommercial work and distribution under its terms; the original
RetroRecomp code remains MIT. It is source-available but is not open source
under the OSI definition because commercial use is restricted. Generated NES
executables retain the license notices as Windows resources. No NES engine,
ROM, or generated commercial game executable is included in the converter
source/release archive.

The conversion translates discovered 6502 instruction starts, runs boot and
two scripted input paths, and feeds ROM misses into further passes. It counts
native and interpreted CPU cycles separately. RAM-executed code can still use
the interpreter; ROM instructions crossing certain compilation boundaries may
also remain there. The final program is compared frame by frame with the
**same engine's internal interpreter** on short automated paths. This is not
an independent hardware oracle, a full-game test, or a physical input-latency
measurement. The converter reports all remaining fallback cycles even if
rounding displays near 100% native coverage.

The current cycle backend is NTSC. NES 2.0 PAL/Dendy timing is identified and
refused until a suitable runtime exists. Legacy iNES headers do not reliably
declare timing, so they use NTSC by default. The original Game Boy remains a
separate DMG profile without PAL/NTSC selection.

The NES host uses the shared RetroRecomp menu canvas. Player 1 defaults to
arrows, Z/X, Enter for Start and right Shift for Select. Player 2 defaults to
keypad 5/2/1/3, 8/9, 7 for Start and 4 for Select. The first two gamepads use
D-pad/left stick and A/B, with Start/Back for cartridge Start/Select; left
stick click opens pause and player 1 right stick click restarts. F2 opens
per-player keyboard/gamepad bindings, saved only after an edit in the shared
`datas/Retro-Recomp.ini`. H shows help, P pauses, F1 restarts, F3 cycles sharp,
bilinear, Scale2x and scanlines, F4 cycles window/integer fullscreen/fit,
F6 toggles gamepad autofire, and F7 changes language. F8/F9 quick states are
not implemented on NES yet. Controller sampling once per frame limits the
effective autofire cadence compared with the Sega backend.

Cartridges with battery-backed memory write a ROM-identified `.sav` below
`datas/games` only when that memory changes. The NES Zapper and other special
peripherals are not implemented. NES-specific mappers may be unsupported; a
successful compilation does not prove the entire game.
