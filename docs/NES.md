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
two scripted input paths, and feeds ROM misses into further passes. For NROM
cartridges (mapper 0), the private compiler adapter also compiles every ROM
address that can start a complete instruction, including indirect targets not
seen by any probe. The current NROM test compiled 32,767 of 32,768 CPU ROM
positions; the remaining position crosses `$FFFF` into non-ROM memory.
This count is potential native entry coverage, not executed-code coverage.

Gameplay probes now sustain directional input and repeat button presses
throughout the test, with different Start timings. They previously released
all inputs after 300 frames, leaving most of a long test idle. The report
counts native and interpreted CPU cycles separately. RAM-executed code can still use
the interpreter. The adapter translates NROM instructions whose operand bytes
cross a fixed 4 KiB PRG-slot boundary. Bank-switched cartridges retain the
discovered-path compiler, and an instruction crossing `$FFFF` remains
interpreted. The pinned upstream checkout stays untouched.
The final program is compared frame by frame with the
**same engine's internal interpreter** for up to 120 boot frames and 600 frames
of each gameplay probe, so delayed Start is included. This is not
an independent hardware oracle, a full-game test, or a physical input-latency
measurement. The converter reports all remaining fallback cycles even if
rounding displays near 100% native coverage.

On the local Super Mario Bros. NROM test, three 3,600-frame paths went from
5,580 ROM-interpreted cycles to zero after this adapter. A separate long
comparison against the engine's internal interpreter matched all 3,600 frame
states on each of those paths. Seven reset-sequence cycles per run are outside
native and interpreted instruction dispatch; the report now exposes them as
`non_dispatch_cycles`. This result covers those paths only; it does not
establish whole-game coverage or gameplay accuracy for other NES cartridges.

A later run-and-jump probe found 51 more ROM entry sites in 1,800 frames, with
19,307 interpreted cycles (0.036%). Extending it to 3,600 frames found 85 sites.
This exposed the limits of the earlier automated paths despite their zero
fallback result. The richer probes now feed these observations into the normal
conversion passes. Their second pass reached zero interpreted cycles on all
three 3,600-frame paths. The exported executable also matched all 1,800 states
of the earlier run-and-jump reference with zero fallback. These are still
bounded scenarios, not whole-game coverage. No runtime learning logs are enabled
in exported games. The game window uses the same short title as the other
profiles: game name and native/fallback status. Once any ROM, RAM or other CPU
fallback has run, the title continues to indicate it until the game closes.

With full NROM ROM-entry generation, the local Super Mario Bros. conversion
and validation took about 2 minutes 44 seconds on this machine. The packed
executable grew from roughly 1.33 MB to 2.42 MB. Three 3,600-frame scripted
paths used zero interpreter cycles. The converter's internal comparison matched
120 boot frames and 600 frames of each gameplay path; a separate 3,600-frame
gameplay comparison also matched. Only Mario was regenerated for this test.
These figures do not measure physical latency or prove full-game or hardware
fidelity.

## Next compatibility work

- Extend ahead-of-time coverage to ROM windows proven fixed on other mapper
  families, while measuring build time and executable size.
- Handle additional mapper layouts and boundary operands safely when banks can
  change. Validate a small representative set of cartridges per board family.
- Add independent CPU/PPU/APU checks and targeted gameplay cases for interrupts,
  scrolling, audio and timing. Internal interpreter agreement alone is insufficient.
- Implement and validate PAL timing before accepting PAL cartridges. Quick
  states and special controllers remain separate feature work.

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
