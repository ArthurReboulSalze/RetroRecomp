# Game Boy (original DMG) profile

RetroRecomp 0.12.0 introduced the original Game Boy profile for `.gb` cartridges
and ZIP files containing exactly one `.gb`. It generates one Windows x64 EXE
under `Export/Games/Game Boy`. Conversion and regeneration use the same
batch queue, readable game filenames, Windows version information and optional
box-art icon process as the Sega profiles. The source ROM is read without
modification; it is embedded in the resulting EXE. Game Boy Color-only
cartridges are rejected. This profile deliberately targets the original
160 × 144 Game Boy display, not Game Boy Color.

The compiler is [arcanite24/gb-recompiled](https://github.com/arcanite24/gb-recompiled)
at pinned revision `9150f87d82fa98abcb6ea22329170463f9702eb8`.
It translates SM83 code across ROM banks into C and includes its separate
Game Boy hardware runtime and reference-interpreter fallback. RetroRecomp
adapts only the private generated project: the pinned dependency checkout
stays untouched. The [sp00nznet/pokemon](https://github.com/sp00nznet/pokemon)
project informed the integration as an example of a game-specific use of
this compiler; its Pokémon code and ROMs are not copied.

## Controls and files

The generated game uses the same compact RetroRecomp SDL menu canvas, font and
colors as Master System and Game Gear, with Game Boy actions behind a small
adapter. The imported compiler's extended settings panel is hidden. F2 opens
the same keyboard/gamepad mapping layout; H opens help; P pauses.
Defaults: arrows, **W/X** for A/B (using the current keyboard layout),
**Enter** for cartridge Start, either **Shift** for cartridge Select;
gamepad D-pad/left stick, face buttons, Start and Back for
the cartridge, and left-stick click for the pause menu. Existing shared Game
Boy settings with recognizable old defaults migrate in memory without
rewriting the INI until a setting is saved. Custom mappings remain available.

F1 resets; F3 cycles sharp pixels, bilinear smoothing, Scale2x and scanlines;
F4 cycles window, integer pixel-perfect fullscreen and aspect-fit fullscreen.
F5 opens the Game Boy display option: pseudo black-and-white monochrome by
default, with classic green available. F6 toggles fast autofire for held
gamepad A/B, F7 switches English/French, and F8/F9 save/load one quick state.
Game Boy has no second player or Light Phaser options. Game Boy Color-only
cartridges are still rejected, so the palette choice applies to DMG games.

Launching and closing without any settings, state or cartridge-RAM write
creates no `datas` folder. An explicit settings change creates
`datas/Retro-Recomp-GameBoy.ini` beside the EXEs. Battery RAM and states use
`datas/games/<game-title>-<ROM-SHA-prefix>/` only when written. Battery RAM
is flushed on exit only after a changed RAM value; a game's own automatic
save can therefore create this folder without a manual state save. Games in the
Game Boy folder share settings, while per-game saves are identified by ROM.
Converter observations are separate, in `Export/datas/library/gb`.

## Audio and input scheduling

New builds use a 20 ms software audio target and request 512 stereo frames per
SDL callback at 44.1 kHz, replacing the imported 80 ms / 2048-frame defaults.
An existing 80 ms setting migrates in memory. The callback discards stale
backlog only beyond the target plus one callback and one guest-frame burst.
Normal samples retain their order; pauses, resets, state loads and suspension
clear the audio queue and restart the host deadline. Audio starvation no longer
makes the guest run ahead of its 59.7275 Hz clock.

Live keyboard/gamepad state is sampled after pacing, immediately before the
next CPU slice, and when the cartridge reads JOYP, limited to one OS poll per
millisecond. Reset, save and menu actions remain in the outer event loop.
Scripted and headless checks keep their deterministic input boundaries.
Windows uses the same preferred SDL Direct3D 11 renderer and background
joystick updates as the Sega host, while respecting explicit SDL overrides.
Generated code uses the speed-oriented optimization level 2.

These are host-buffer and scheduling settings, not measured physical latency.
On a local 600-frame scripted Super Mario Land test with SDL dummy drivers,
the median sampled audio ring fill fell from 71.85 ms to 18.4 ms, with no
underrun samples in either ten-second run. The before/after guest state was
identical after 1200 headless frames with the same script; this checks that
the host changes preserved that execution, not independent APU accuracy.
`tools/gameboy_latency_selftest.py` checks real adapted input/audio code with
authored data, synthetic keyboard state and an SDL virtual gamepad.
Listening tests and physical input-to-display latency remain separate.

## Evidence and limits

The standard all-bank scan uses heuristics and can miss short functions.
RetroRecomp also examines unconditional ROM JP/JR entries independently,
including short relays and overlapping instruction starts, then feeds these
candidates to the existing native code generator. Operands crossing a physical
bank boundary are excluded from this extra scan. ROM contents and mapper
behavior are preserved. These candidates are discovery hints, not a claim
that every ROM byte is code or every entry has been tested.

Each pass runs a boot scenario plus two reproducible input scenarios: Start,
left/right movement and button presses. The selected frame count applies to
each scenario. Very short tests ending before Start keep only the boot test.
All scenarios must reach zero fallback before stopping early; otherwise their
new ROM entries feed the next pass, up to the selected pass limit. Reports
include each remaining fallback's bank, address, reason and cycle count.
Scripts are generic probes, not automatic completion of a game or every menu.

The converter library merges and deduplicates ROM entries from all scenarios
and earlier validated conversions, keyed by ROM hash and compiler revision.
Static candidates are kept separate from observed entries. Writable RAM and
HRAM observations never become unguarded ROM code. Exported games still do not
write learning logs, and the interpreter remains available and reported.

The fallback percentage is deliberately left unknown because the upstream
report does not provide a defensible total cycle denominator. Before export,
the default CPU check compares generated and reference execution instruction
by instruction for up to 30 boot frames. **Deep Game Boy validation (slow)**
adds up to 240 frames per input scenario. This option is off by default and
can add several minutes per game; it is useful when investigating a CPU
discrepancy or validating compiler changes. Both modes require the requested
comparison frames to finish and reject a mismatch. Matching results do not
independently validate PPU, APU, input timing, cartridge peripherals, complete
gameplay or physical latency.

The option only changes the scope of reference CPU validation. Native ROM
discovery, the converter library, the three coverage probes and the pass limit
are identical in both modes. **Frames per test** controls the coverage probes,
not the deep CPU comparison budget. From the CLI, add `--gb-deep-validation`
to `convert` or `batch`; it is ignored for other consoles. The conversion
report records `native_validation.mode`, each completed comparison and
`stage_seconds` for setup, discovery, translation, build, coverage probes and
CPU validation. Conversion timing excludes final executable compression and
publication; first-time dependency downloads/builds are included in setup.

A local Super Mario Land conversion with dependencies already installed and
an empty game-entry library took 135 seconds in standard mode: two passes,
three final 3600-frame probes with zero fallback, and a matching 30-frame
CPU comparison. The earlier deep-validation conversion took 750 seconds.
These are local measurements, not a time limit for every ROM or computer.

On Super Mario Land, two local 3600-frame input runs previously reported
44,272 and 60,656 interpreted cycles, all at ROM bank 3, address 7FF0. Extended
discovery compiles that JP relay before testing: both runs and the 3600-frame
boot reach zero fallback. The before/after state dumps match except for the
fallback counter. This is evidence for those paths, not whole-game coverage.

Three targeted local cartridges have been checked for 120 boot frames each:
Tetris (no bank switching), Super Mario Land (MBC1), and Lazlos' Leap
(MBC2 with battery RAM). Tetris and Lazlos' Leap reported zero
fallback cycles. Super Mario Land first reported one fallback at bank 0,
address `0322` (76 interpreter cycles); a later conversion reused its
converter-side entry trace and reported zero fallback cycles on the same
boot scenario. All three final executables matched their reference CPU for 30
frames. An isolated two-frame launch of Lazlos' Leap created no `datas`
folder, demonstrating that unchanged battery RAM is not flushed on exit.
MBC3 RTC persistence has no independent regression test yet. These checks do
not include a played level or a visual review.

This first profile does not support `.gbc`-only games, link cable,
Game Boy Camera/Printer or Super Game Boy features. See
[compatibility](COMPATIBILITY.md) for the current validation scope.
