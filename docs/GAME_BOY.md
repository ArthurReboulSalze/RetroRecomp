# Game Boy (original DMG)

Status: **supported**. The original monochrome Game Boy (DMG, 160 × 144) from `.gb` cartridges and single-ROM ZIP files; Game Boy
Color-only cartridges are rejected on purpose. Five measures stay separate on this page and in every report: native code, CPU
fidelity, hardware fidelity, gameplay validation and physical latency.

Contents

1. [At a glance](#at-a-glance)
2. [Structure of the machine](#structure-of-the-machine)
3. [Engine and upstream](#engine-and-upstream)
4. [In the project](#in-the-project)
5. [Controls and options](#controls-and-options)
6. [States and saves](#states-and-saves)
7. [Qualification](#qualification)
8. [Known limits](#known-limits)
9. [History](#history)

## At a glance

| | |
|---|---|
| Status | Supported (profile `retrorecomp/systems/game_boy.py`, id `gb`); gate status in [QUALIFICATION.md](QUALIFICATION.md) |
| Converted | The SM83 code of the cartridge, across ROM banks, into C compiled with the DMG runtime; what the translation cannot reach runs on a counted fallback |
| Accepted files | `.gb` cartridge or a ZIP with exactly one cartridge (the reader also accepts the names `.bin` and `.rom`); 32 KiB to 8 MiB in 16 KiB banks. A headerless dump is recognised when its header checksum, declared size and title agree |
| Refused | Game Boy Color-only cartridges (header flag `0xC0`). Color-compatible cartridges are accepted and run as a DMG: the generated main forces the runtime's model to `dmg` |
| Output | One standalone executable per game under `Export/Games/Game Boy` (a Windows x64 EXE, or a Linux ELF on Linux). The source ROM is read without modification and embedded in the executable |
| Display | The 160 × 144 window of the original Game Boy, no PAL/NTSC choice (`video_modes = ("dmg",)`) |
| Players | One. No second player, no Light Phaser |
| Firmware | None needed |
| Saves | Battery RAM and one quick state, per game (see [States and saves](#states-and-saves)) |
| Not supported | `.gbc`-only games, link cable, Game Boy Camera and Printer, Super Game Boy features |

RetroRecomp 0.12.0 introduced the profile. Conversion and regeneration use the same batch queue, readable game filenames, Windows
version information and optional box-art icon process as the Sega profiles ([BOXART.md](BOXART.md)).

## Structure of the machine

| Part | Handled by | How Retro-Recomp handles it |
|---|---|---|
| Main CPU: Sharp SM83 (the Game Boy's Z80-like core), 4.19 MHz | [CPU_SM83.md](CPU_SM83.md) | Native code translated ahead of time from the ROM entries it finds; the pinned reference interpreter as a counted fallback; counted one-instruction executors for code in WRAM and HRAM ([below](#writable-memory-code-164)) |
| Picture: DMG PPU, 160 × 144, four shades | `runtime/src/ppu.c` of the pinned runtime, compiled into the game | A C hardware model, not translated code. Hardware fidelity is not validated; the upstream PPU dot-timing check passes. The picture goes through the host kit (filters, display modes, palette) |
| Sound: four-channel APU, 44.1 kHz stereo PCM | `runtime/src/audio.c`, with three corrections of ours ([below](#apu-corrections-11-october-2026)) | The wave channel behaviour, the exact timer low bits and the analogue output still need separate accuracy work. The host kit plays the PCM through its callback ring |
| Cartridge: ROM banking and battery RAM | `runtime/src/gbrt.c` | MBC1 (the runtime also detects MBC1M multicart wiring), MBC2, MBC3 with its real-time clock, MBC5, the Wisdom Tree mapper (since 1.6.6, below), and cartridges with no mapper. Cartridge types `0x01-0x03`, `0x05-0x06`, `0x0F-0x13` and `0x19-0x1E` are the ones the runtime banks. Battery RAM and the clock are written only when they changed |
| Timer, interrupts, OAM DMA, joypad | The pinned runtime | Run by the pinned runtime in step with the CPU's cycle counts; the HRAM sprite-DMA wait routine is a guarded helper (below). Input is sampled by the host kit's pad word |
| Peripherals | Joypad only | No link cable, Camera, Printer or Super Game Boy |
| Player shell | The host kit, `native/hostkit/adapters/rrhk_gb.inc` | Window, menus, bindings, controllers, sound device and pacing since 1.6.3 ([HOST_KIT.md](HOST_KIT.md)) |

*In the report (since 1.6.6, gate G2).* The mapper and the sound unit are two entries of `devices` (`cartridge_mapper`, `audio_unit`),
apart from the CPU, with no counter (`fallback_present` is `None`: there is no program of theirs to translate or interpret), the header
facts (type, family, banks, RAM, battery, clock, rumble) and `mapper_modelled_by_runtime`, which is false for the types the runtime does
not bank (MMM01, MBC6, MBC7, camera, TAMA5, HuC1, HuC3). `saves.cartridge_memory` names what the cartridge keeps. Hardware fidelity
stays "not validated" for both.

Where the five measures stand: **native code** is reported per scenario with the interpreter and the one-by-one executors shown
apart, and, since 1.6.7, with the guarded helpers (native bodies that take over a recognised routine of writable code after checking its
live bytes: store and increment, copy, DMA page, interrupt-bracketed DMA) counted apart too, by kind, as entries and guest cycles in
`final_checks[].guarded_helpers`; they are not interpreter sessions and are not added to any other figure; **CPU fidelity** is a comparison against the pinned reference interpreter on short scripted scenarios (see
[Qualification](#qualification)); **hardware fidelity**, **gameplay validation** and **physical latency** are not claimed.

### Sound and input timing

New builds keep the APU's 44.1 kHz stereo PCM and request 256 frames per SDL callback, accepting the backend's actual period and
S16 or native float format. Playback begins one actual callback period plus 10 ms after the first samples, at the corresponding
sample inside the callback block. This avoids waiting for a second guest frame and removes an extra SDL conversion queue when
native float output is available; other output formats retain SDL's conversion path. The 20 ms setting is only the
abnormal-backlog target (the imported 80 ms setting still migrates in memory). The callback discards stale backlog only beyond that
target plus one callback and one guest-frame burst. Normal samples retain their order; pauses, resets, state loads and suspension
clear the audio queue and restart the host deadline. A genuine output underrun re-primes playback. Audio starvation never makes the
guest run ahead of its 59.7275 Hz clock.

Live keyboard and gamepad state is sampled after pacing, immediately before the next CPU slice, and when the cartridge reads
JOYP, limited to one OS poll per millisecond. Reset, save and menu actions remain in the outer event loop. Scripted and headless
checks keep their deterministic input boundaries. Windows uses the same preferred SDL Direct3D 11 renderer and background joystick
updates as the Sega host, while respecting explicit SDL overrides. Generated code uses the speed-oriented optimization level 2.
These are host-buffer and scheduling settings, **not measured physical latency**; the measurements are in the
[journal](GAME_BOY_LOG.md#shared-apu-corrections-and-audio-scheduling-11-october-2026) and in [Audio output](AUDIO.md#game-boy-output).
`tools/gameboy_latency_selftest.py` checks the real adapted input and audio code with authored data, synthetic keyboard state and an
SDL virtual gamepad. Listening tests and physical input-to-display latency remain separate.

## Engine and upstream

The compiler and runtime are [arcanite24/gb-recompiled](https://github.com/arcanite24/gb-recompiled) at pinned revision
`9150f87d82fa98abcb6ea22329170463f9702eb8` (`gameboy.ENGINE_REV`), MIT, adapted under identical terms. It translates SM83 code
across ROM banks into C and includes its separate Game Boy hardware runtime and reference-interpreter fallback. RetroRecomp adapts
only the private generated project (`replace_once` edits, failing loudly when upstream moved): the pinned checkout in
`.deps/gb-recompiled` stays untouched. The [sp00nznet/pokemon](https://github.com/sp00nznet/pokemon) project informed the
integration as an example of a game-specific use of this compiler; its Pokémon code and ROMs are not copied. The table of pins,
the rule for bumping one and the fixes carried as our own patches are in [UPSTREAMS.md](UPSTREAMS.md).

Adaptations we carry on the generated project:

- **Writable-memory code (1.6.4).** WRAM and HRAM instructions outside the pinned RAM stub run one at a time, counted ([below](#writable-memory-code-164)).
- **Guarded multi-instruction helpers** (`native/gb_ram_helpers.h`): a small writable store/increment routine, unrolled byte copies,
  LCD-safe copy/fill loops, HRAM DMA page selection and the interrupt-bracketed sprite-DMA helper in HRAM (its DI/EI instructions
  included; the DMA source page stays live). Every added instruction checks the complete live routine signature; operands stay live;
  unknown or changed code keeps the visible fallback, and the normal DMA, HALT, interrupt and frame safepoints are preserved.
- **Bank-boundary operands** (`gameboy_boundary.py`). Instructions spanning `3FFF/4000` or `7FFF/8000` read their operands from the
  live mapped bus instead of baking bytes from an adjacent physical ROM bank. An unsupported boundary form uses the counted fallback
  rather than executing an assumed operand.
- **Host stack.** Generated cross-body jumps and calls return to the native PC dispatch loop instead of recursively consuming the host
  C stack (Pokemon Yellow exposed the overflow).
- **Battery RAM** is flushed on exit only after a changed value (upstream flushed every cartridge with external RAM), so a launch and
  quit stays file-free.
- **Inline ordinary case of `gb_tick` (1.6.5).** `gb_tick` advances the clock after nearly every instruction and runs a large general
  sequence. `native/gb_tick_fast.h`, included by the runtime file `gbrt.c`, runs the ordinary case in the caller (single speed, no OAM DMA,
  serial transfer, ticking real-time clock, TIMA reload or timer edge in these cycles, none of the test switches) with the same effects in the
  same order, and calls the real `gb_tick` for every other case before changing anything. It reaches the ticks issued by the runtime's own
  functions, mainly the HALT loop of `gb_run_cycles` (a game waiting for vblank steps a few cycles at a time), the timed jumps, calls, returns
  and bus accesses and the interrupt dispatch. Counted on Super Mario Land over 3,600 frames (54.0 million calls): 87.0 percent take the
  inline path, 1.3 percent are handed to the real `gb_tick` (a timer edge, mostly) and 11.7 percent are the direct calls of the generated
  bodies, which keep calling the real `gb_tick` since forcing the inline there would add about 400 bytes at each of thousands of call sites
  per source file. The code of `gbrt.c` grows by roughly 44 KB. It is a speed change only: `tools/gameboy_tick_selftest.py` compares both on random operation streams, field by field. The speed
  gain is not measured here.
- **A frame lasts 70,224 cycles with the LCD off (1.6.5).** The PPU completes a frame only at vblank, so with the LCD off no frame ever
  completed: a game that waits for a key with the screen off (The Ren & Stimpy Show: Veediots!, at the end of frame 215 of the probe)
  stopped every headless probe and every frame-anchored input script, since the frame counter and the script clock advance only at a
  completed frame. The runtime now ends the frame when the frame's cycles reach 70,224 while the LCD is off (`gb_add_cycles`, and its copy in
  `gb_tick_fast.h`); the picture is the last one, as the PPU keeps it, which is also what the windowed loop already showed during an
  LCD-off span. Only the counting of frames moves: at the same total of cycles the full state is identical (Tetris and Super Mario
  Land, `--dump-state`, without `completed_frames`). The consequence for a conversion is that the boot's LCD-off span now counts as
  several frames (15 more in Tetris, 39 more in Super Mario Land over the first 3,600), so the probes of N frames cover fewer cycles
  at the start and their counts and observed entries differ a little from those of 1.6.4.
- **Input refresh.** A JOYP read with no scripted pad asks the host for fresh input (`adapt_input_refresh_hook`).
- **Build reductions** (`gameboy_build.py`; the generated instruction bodies and `/O2` are kept): regular dispatch pages use immutable
  native-function tables, trivial entry wrappers call their shared body directly, custom/native replacement hooks stay, function
  declarations are local to the C files that use them (a new entry does not invalidate every file through the common header), and
  generated entry selectors avoid an MSVC 19.44 switch/goto failure. Large entry sets use a balanced tree and must never become a
  linear chain of thousands of tests. An exact SHA-256/content check restores modification times only for unchanged final sources, so
  objects survive between passes and regenerations; qualification is always run again. On Windows the C files compile with a bounded
  MSVC `/MP` job count shared among concurrent games.
- **Diagnostic traces** record each `(bank, PC)` once per run, with a lazy 4 MiB bitset; nothing is skipped. Exported games do not
  enable learning or write these traces.

### APU corrections, 11 October 2026

Three checked adaptations to the pinned runtime (`retrorecomp/gameboy_hardware.py`) fix missing rising-envelope sound on pulse and
noise channels, preserve pulse duty phase when a note is retriggered, and stop noise LFSR clocks for NR43 shifts 14 and 15. They
follow [Pan Docs' APU details](https://github.com/gbdev/pandocs/blob/master/src/Audio_details.md). No title-specific ROM patch,
interpreter counter suppression, larger audio target or APU state-layout change is used; existing quick states retain their format.
This does not complete the APU model. `tools/gameboy_hardware_selftest.py` builds the adapted runtime and runs 21 authored APU checks
through its public APIs (the original runtime fails seven; the adapted runtime passes all 21), and the pinned PPU dot-timing,
OAM-DMA bus and APU chunk-invariance checks also pass. These checks do not establish a cause for the sprite flicker reported in
unspecified games and are not an audio listening or full-gameplay validation. Do not hide possible original sprite-limit flicker
with frame blending or extra sprites.

### Writable-memory code (1.6.4)

Some games copy routines into WRAM or HRAM and run them there. In the generated dispatch, such an address goes through, in this
order: the guarded multi-instruction helpers, the pinned runtime's RAM stub, and then a counted executor of single instructions
(`rr_gb_try_ram_instruction`, behind `rr_gb_try_ram_dispatch`); code run from `0xFF00-0xFF7F` goes through the pinned runtime's
high-memory stub (`rr_gb_try_highmem_dispatch`). The executor runs one instruction at a time from its live bytes and is checked
opcode by opcode against the interpreter by `tools/gameboy_ram_selftest.py` (177 plain opcodes at 24 random states, and since 1.6.5 the
`CB` prefix with each of its 256 second bytes at 8 random states, four placements in WRAM and HRAM each). **That is not native code and not ahead-of-time translation**: it is a per-opcode switch, cheaper than an interpreter
session, and the ROM routine a trampoline jumps to is native again. `HALT`, `STOP`, `RST`, illegal opcodes and
code spanning two regions still reach the interpreter (the `CB` prefix did until 1.6.5), except `RST 00` to `RST 38` run from `0xFF00-0xFF7F`, which the pinned
high-memory stub executes itself (counted in its own pair).

Counting. The executor, the RAM stub and the high-memory stub each count instructions and guest cycles per probe
(`ram_stub_*`, `ram_single_step_*`, `highmem_stub_*`); the report (schema 2) lists them in
`cpus[].scenarios[].ram_single_step` with `ram_single_step_present`, and while they are not zero `native_code.zero_fallback_on_tested_scenarios`
is false. A 1.6.3 report reads "not measured", never "zero". The counts cover the generated dispatch only: when generated code
enters an interpreter session, the pinned interpreter calls the same stubs itself and those instructions belong to the session (its
loop counts one instruction per iteration, and their cycles are in the session's cycles), so they are not counted a second time. Not
counted: the guarded multi-instruction helpers and the pinned HRAM stub (`gbrt_try_execute_hram_stub`), which recognises the complete
OAM-DMA wait routine by its bytes and runs it as one helper (its instruction count would be a count of calls).

Donkey Kong Land was the case: trampolines copied from the cartridge into WRAM and patched (`LD HL,nn; CALL/JP`) started interpreter
sessions (6,350 sessions and 3,160,836 interpreted cycles in the 6,000-frame boot probe, 388 sessions and 141,688 cycles in the varied
probe). With 1.6.4 the interpreter figures are zero in all four probes, the deep CPU comparisons still match, and the one-by-one
instructions are reported beside them. Wario Land II kept interpreter sessions after 1.6.4: copied routines in WRAM use the `CB` prefix (`BIT 7,A`, `SET 6,(HL)`, `SET 1,(HL)` at `D807`, `D80A` and `D83A`), which the executor declined. A conversion of 29 October 2026 (standard scan level, 3,600 frames per final probe, empty converter library) showed 46,570 interpreter instructions (2,109,380 cycles) in the boot probe and 3,659 to 6,139 (165,472 to 278,064 cycles) in the three input probes. Since 1.6.5 the executor runs the `CB` prefix, and the same conversion reports **zero interpreter instructions and cycles in all four probes**; the `CB` instructions are counted with the one-by-one instructions (`ram_single_step_*`, 91,857 to 116,402 per probe; the RAM stub counts 162,787 to 232,729; `highmem_stub_*` is zero). The deep CPU comparisons match with identical step counts before and after (495,659, 3,840,567, 3,840,567 and 3,494,617 steps), and an A/B comparison of the two kept build folders (327 files each) differs only in the compiled entries and their dispatch chunks, the observed traces, the adapted runtime header and the report counts. Fewer ROM entries are compiled (66,491 against 67,166) because the second pass no longer has interpreter-observed entries to add. Details:
[journal](GAME_BOY_LOG.md#broader-cartridge-cases--9-october-2026) and "Game Boy exports in 1.6.4" in [UPGRADES.md](UPGRADES.md).

## In the project

| Kind | Files |
|---|---|
| Profile | `retrorecomp/systems/game_boy.py` (extensions, options `gb_deep_validation` and `gb_parallel_games`, path shape `sm83`/`gb`, library layout `gb`) |
| Converter | `retrorecomp/gameboy.py` (pipeline, passes, report), `gameboy_coverage.py` (probe and CPU-validation scenarios), `gameboy_runtime.py` (adaptations of the generated project), `gameboy_boundary.py`, `gameboy_build.py`, `gameboy_hardware.py`, `gameboy_host.py` (platform layer on the host kit) |
| Shared converter code used | `scan_levels.py` (`gameboy_budget`), `random_routes.py`, `path_profiles.py` (CPU-keyed `rom_entries`), `report_schema.py` |
| Native | `native/gb_ram_helpers.h`, `gb_ram_checks.c`, `gb_boundary_checks.c`, `gb_audio_checks.c`, `gb_latency_checks.cpp`, `gb_tick_fast.h`, `gb_tick_checks.c`; the adapter `native/hostkit/adapters/rrhk_gb.inc` |
| Self-tests (build C, need a compiler, no ROM) | `tools/gameboy_ram_selftest.py`, `gameboy_boundary_selftest.py`, `gameboy_display_selftest.py`, `gameboy_hardware_selftest.py`, `gameboy_latency_selftest.py`, `gameboy_tick_selftest.py`, `gameboy_sm83_vector_selftest.py` (independent SM83 vectors, [CPU_SM83.md](CPU_SM83.md#6-tests-and-vectors)) |
| Unit tests | `tests/test_game_boy.py`, `test_gameboy_build.py`, `test_gameboy_coverage.py` |
| Stamps | The role and owners of each file are in `retrorecomp/stamp_inputs.py`; editing a Game Boy game file moves the Game Boy game stamp (there is no Game Boy quick-state key) |

## Controls and options

The generated game uses the same compact RetroRecomp SDL menu canvas, font and colors as the other handhelds, with Game Boy actions
behind a small adapter; the imported compiler's extended settings panel is hidden. Since 1.6.3 the whole shell is the host kit's
([HOST_KIT.md](HOST_KIT.md)): one binding per action (the shoulders are not a second A/B) and the Gamepad row of F2. General keys and
the shared speed and sound controls are in [CONTROLS.md](CONTROLS.md).

| Action | Keyboard | Gamepad |
|---|---|---|
| D-pad | Arrows | D-pad / left stick |
| A, B | **W**, **X** (follow the current keyboard layout) | The east and south face buttons (A and B as on the console) |
| Start, Select | **Enter**, either **Shift** | Start, Back |
| Pause menu | P | Guide |

Shared Game Boy settings written with the old default keys by a release before 1.6.0 keep them (they are no longer migrated). Custom
mappings remain available.

- **F1** help, **Shift+F1** reset, **P** pause, **F2** the keyboard and gamepad mapping layout and options.
- **F3** cycles sharp pixels, Scale2x, scanlines and xBR smooth. **F4** cycles window, integer pixel-perfect fullscreen and aspect-fit
  fullscreen.
- **F5** switches immediately between pseudo black-and-white monochrome (the default) and classic green, without a menu or a pause.
  The choice is persistent; holding F5 does not repeatedly toggle it. The palette choice applies to DMG games.
- **F6** toggles fast autofire for held gamepad A/B; **F7** switches the menu language; **F8 / F9** save and load one quick state
  (taken between two frames).
- The fast-forward (Tab held, right trigger), maximum-speed (backquote, left trigger) and mute (M) keys, the volume and the
  output-device choice of the former player came back in 1.6.3 as features of the shell, on every console
  ([CONTROLS.md](CONTROLS.md#speed-and-sound)). The settings of a 1.6.2 export (`audio.muted`, `audio.volume_percent`,
  `audio.device_name` of `Retro-Recomp-GameBoy.ini`) are read where the new keys are absent.

Settings files. Launching and closing without any settings, state or cartridge-RAM write creates no `datas` folder. An explicit
settings change creates `datas/Retro-Recomp.ini` beside the EXEs (since 1.6.3, `[GameBoy.*]` sections; the
`datas/Retro-Recomp-GameBoy.ini` of earlier releases is still read and never written). Games in the Game Boy folder share settings,
while per-game saves are identified by ROM. Generated games never create an `imgui.ini` in the executable folder or the working
directory (the imported ImGui panel is no longer used since 1.6.3). Converter observations are separate, in `Export/datas/library/gb`.

### Options in the converter

**Options → Game Boy** has **Deep Game Boy validation (slow)** (on by default, since v0.15.0: previous preferences saved the old
unchecked default automatically, so that value migrated once, and a user who unchecks it afterward keeps that choice) and the
**Discovery scan** level. From the command line, `--no-gb-deep-validation` opts out for `convert` or `batch` (ignored for other
consoles). **Frames per test** controls the coverage probes, not the deep CPU comparison budget. Passes and frames can be set per
console; empty fields follow the shared values.

**Scan levels** set how long discovery runs. *Standard* (boot, two play runs and the varied replay, with deep validation) is the
default. *Extended* adds one reproducible pseudo-random route of 18,000 frames seeded from the exact ROM, written in the host's
`start:buttons:duration` grammar (`retrorecomp/random_routes.py`); *Thorough* adds a second. *Quick* keeps boot and the two play runs
for a single pass and skips the deep CPU comparison: use it to check a setting, not for a final export. The report records
`scan_level` and the routes' seeds.

### Discovery and validation

The standard all-bank scan uses heuristics and can miss short functions. RetroRecomp also examines unconditional ROM JP/JR entries
independently, including short relays and overlapping instruction starts, then feeds these candidates to the existing native code
generator. Operands crossing a physical bank boundary are excluded from this extra scan. ROM contents and mapper behavior are
preserved. These candidates are discovery hints, not a claim that every ROM byte is code or every entry has been tested.

Each normal-length pass runs a boot scenario plus three reproducible input scenarios: left/right play and a varied
menu/movement/button sequence. The varied path is included from 750 frames onward. The selected frame count applies to each
scenario. Very short tests ending before Start keep only the boot test. All scenarios must reach zero fallback before stopping early;
otherwise their new ROM entries feed the next pass, up to the selected pass limit. Reports include each remaining fallback's bank,
address, reason and cycle count. Scripts are generic probes, not automatic completion of a game or every menu.

The converter library merges and deduplicates ROM entries from all scenarios and earlier validated conversions, keyed by ROM hash and
compiler revision. Static candidates are kept separate from observed entries. Writable RAM and HRAM observations never become
unguarded ROM code. Exported games do not write learning logs, and the interpreter remains available and reported. See
[COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md).

The fallback percentage is deliberately left unknown because the upstream report does not provide a defensible total cycle
denominator. Before export, the mandatory CPU check compares generated and reference execution instruction by instruction for up to
30 boot frames. **Deep Game Boy validation (slow)** adds up to 240 frames per input scenario. With the **extended** and **thorough** scan levels
(since 1.6.7) every scenario of the probes, the pseudo-random routes included, is compared over its whole length, up to 3,600 frames; the report
says for each comparison how many frames were compared and how long the scenario is (`scenario_frames`), and `native_validation.mode` is `full`.
The lockstep run goes at about twenty frames a second, so a route of 18,000 frames is compared over its first 3,600 and says so. Both modes require the requested
comparison frames to finish and reject a mismatch. The differential validator checks all mutable memory and framebuffer bytes after
every instruction and locates the first differing byte on failure. The option only changes the scope of the reference CPU validation;
native ROM discovery, the converter library, the coverage probes and the pass limit are identical in both modes. The conversion
report records `native_validation.mode`, each completed comparison and `stage_seconds` for setup, discovery, translation, build,
coverage probes and CPU validation. Conversion timing excludes final executable compression and publication; first-time dependency
downloads and builds are included in setup. Matching results do not independently validate PPU, APU, input timing, cartridge
peripherals, complete gameplay or physical latency. Timings and their conditions are in the [journal](GAME_BOY_LOG.md#conversion-timings-and-discovery-measurements).

## States and saves

- **Quick state.** F8 saves and F9 loads one state (slot 1, ROM identity by SHA-256), taken between two frames; it is the runtime's own
  file under the game's folder. The Game Boy has its own codec ([GAME_STATES.md](GAME_STATES.md)); the APU corrections did not change its
  layout. There is no Game Boy quick-state key: the RAM counters are host-only context fields outside every state, and a state of a 1.6.2 export loads in a
  1.6.3 export and the reverse ([UPGRADES.md](UPGRADES.md#game-boy-exports-in-163-host-kit-phase-5)).
  Since 1.6.6 `tools/gameboy_states_check.py` (gate G6) drives the two functions the keys call (`gb_context_save_state_file` and
  `gb_context_load_state_file`, through the headless flags `--save-state-file` and `--load-state-file`) in separate processes, on a
  cartridge authored for it (screen on, a square channel playing, vertical-blank and timer interrupts, a foreground counter) and on
  Super Mario Land: a state taken after 120 frames, loaded by a fresh process and run for 120 more, gives the dump of a continuous
  240-frame run field by field (registers, cycles, work and high RAM, LY and PPU mode) and the same picture, sound, RAM and program
  counter on each of the 120 frames (`--frame-trace`); a second state taken after that load continues the same way. A state cut short
  (empty, inside the header, in the body, one byte short), not a state, with a wrong magic, version, ROM hash or ROM size, is refused
  before anything is applied (exit 1 and "Failed to load execution state", the file untouched); a state that does not exist is refused
  and nothing is created. Every conversion runs a shorter version of this on the compressed copy (60 + 60 frames, the dump only, ten
  damaged states and a missing one) and records it in `game_states.validation`; a failure is reported, not fatal. The F8 and F9 keys themselves (the path of slot 1) need a window and are not driven by the check. A byte
  changed inside a state of the right length is not detected: the file has no checksum.
- **Battery RAM and the real-time clock** use `datas/games/<game-title>-<ROM-SHA-prefix>/`, only when written. Battery RAM is flushed on
  exit only after a changed RAM value; a game's own automatic save can therefore create this folder without a manual state save.
  An isolated two-frame launch of Lazlos' Leap (MBC2 with battery RAM) created no `datas` folder. Since 1.6.6
  `tools/gameboy_saves_check.py` (gate G7) exercises this on six cartridges authored for it (no original bytes): MBC1, MBC2, MBC3 with its
  clock, MBC5, MBC1+RAM without a battery, and a battery cartridge whose program never writes. Each is converted and the delivered file is
  run twice, headless, in an empty folder. The first run writes a magic and a pattern into its RAM and leaves `<title>-<sha>.sav` (8 KiB;
  MBC3 also `<title>-<sha>.rtc`); the second finds the magic and reads the pattern back byte for byte (four bits per cell on MBC2; the
  clock registers 17 s, 11 min, 7 h, day 42 with the halt bit come back on MBC3), and rewrites nothing. A cartridge without a battery, and
  a battery cartridge that never writes, create no `datas` folder at all. A battery file or a clock file that is too short, too long, empty
  or not a save is refused: the game starts with blank RAM (or a blank clock; the RAM still loads when only the clock file is damaged), the
  log says "Rejected battery RAM …" and "Automatic persistence save suppressed", the file is left as it was, and the exit is normal. This
  tests the files and the reload, not a commercial game's own save code.

## Qualification

Gate status for the Game Boy is in [QUALIFICATION.md](QUALIFICATION.md) (the column `gb`); the checks below are what exists today.
Deep CPU checks compare instructions and memory for 30 boot frames and 240 frames of each of the three input scenarios, and from the extended level
on over the whole length of every scenario, up to 3,600 frames (the Game Boy
release check compares the CPU once, on a short boot, not on every final scenario as the other writers do). These checks do not cover
all gameplay, certify hardware fidelity or measure physical latency.

### The sixteen gates, with their evidence (1.6.7)

The letters (met, partial, unknown) are in [QUALIFICATION.md](QUALIFICATION.md); this table says where each piece of evidence is and what it
leaves out. A tool or a report field named here exists in the tree of this page.

| Gate | Evidence for the Game Boy | What it leaves out |
|---|---|---|
| G1 Status | `supported`: the profile (`retrorecomp/systems/game_boy.py` takes the default status), the first line of this page and the README table say so; [COMPATIBILITY.md](COMPATIBILITY.md) and [INDEX.md](INDEX.md) describe the machine without any experimental mark; `tools/status_lint.py` shows 0 contradictions and 0 drift items (4 November 2026) | The status rests on the gates below; it claims neither hardware fidelity nor complete games nor latency |
| G2 Report | Schema 2: the SM83 as the main CPU (cycles and instructions, per route), the mapper and the sound unit as two devices with no counter (C models of the runtime, no program to interpret: `mode: c_model`, `hardware_fidelity_validated: false`), `saves.cartridge_memory`, `states`, `packed`; read on the reports of the twelve campaign games on 4 November 2026 | The mapper and the sound unit are C models of the runtime; their fidelity is stated as not validated |
| G3 Native coverage | `final_checks[]`: `interpreter_instructions` and `interpreter_cycles`, the one-by-one counts of writable code (`ram_*`, `highmem_*`), `guarded_helpers` by kind; the fallback percentage stays unknown (no honest denominator); no interpreter instruction on any final route of the twelve campaign games (below), the writable code run one by one is listed per game | Only the routes run; helpers are counted as entries and cycles, not as instructions |
| G4 CPU fidelity | Lockstep against the pinned interpreter: 30 boot frames and 240 per route; from the extended level on, every scenario over its whole length up to 3,600 frames (`native_validation.scenarios[]`, `mode: full`; the long route of 18,000 frames over its first 3,600): the twelve campaign games at the extended level, and 151 of the 152 test ROMs below frame by frame with the picture and the sound, plus one documented divergence (`oam_bug` 7, first version, at step 6,717,022) | The interpreter shares the runtime's devices, so this is no independent oracle for them; its own fidelity is G10 |
| G5 Delivered file | The compressed copy replayed on the same routes with the same verdict (`packed_reference_match`, `packed_candidate_sha256`) | Same routes and lengths as G4 |
| G6 States | Every conversion checks quick states in fresh processes on that copy (`game_states.fresh_process_verified`); `tools/gameboy_states_check.py` on an authored cartridge and a game | F8 and F9 themselves are not driven; the state file has no checksum |
| G7 Saves | `tools/gameboy_saves_check.py`: six authored cartridges (MBC1, MBC2, MBC3 with clock, MBC5, RAM without battery, battery never written), reload byte for byte, damaged files refused | A game's own save code is not tested |
| G8 Liveness | `final_checks[].liveness` on every probe; a conversion is refused when its `varied` route never changes the picture | Counts of changes, not proof that the game is played well |
| G9 Route depth | The reproducible pseudo-random route of the extended and thorough levels; the 1.6.7 campaign (`tools/gameboy_campaign.py`) replays it on the delivered file with six captures a game that a person looks at | Not full games; the pictures are looked at by the specialist agent, not by the owner |
| G10 Independent CPU | `tools/gameboy_sm83_vector_selftest.py`: 402,589 of 404,358 vectors of SingleStepTests/sm83 on plain memory match the interpreter, all of the RAM executors'; and the public test ROMs run on the delivered files (below): blargg `cpu_instrs` 11 of 11, `instr_timing`, `mem_timing` 6 of 6, Mooneye's instruction, interrupt, HALT and timing tests all pass, each with native and interpreter identical for the whole run | The vectors do not run the generated code (the lockstep carries the interpreter to it); the vector model is not a console; `STOP` and `HALT` differ by its conventions; `STOP` itself is not tested by `cpu_instrs`; the test ROMs run at the quick level, one conversion each |
| G11 Independent hardware | The upstream's PPU dot-timing, OAM DMA bus and sound checks (`tools/gameboy_hardware_selftest.py`); and the console's own tests (below): Mooneye 94 of 94 applicable tests (timer, OAM DMA, PPU and interrupt timing, boot state, MBC1, MBC2, MBC5), blargg `oam_bug` 14 of 16, `mem_timing` 6 of 6, `dmg_sound` 18 of 24 (1.6.8) | The wave-channel accesses of `dmg_sound` (3 tests of 12, in both versions) still fail and `oam_bug` `7-timing_effect` gives no verdict; the DMG ABC model only (the other revisions of the console are not applicable); after the reset only the PPU is stepped to the console's start and the divider keeps its value, so the phase between DIV and the PPU is not tested; no hardware capture is used |
| G12 Panel | The exact-cartridge panel of the collection (below) | Cartridges that failed or were skipped are listed on that page and in [KNOWN_FAILURES.md](KNOWN_FAILURES.md) |
| G13 Cross-OS | Windows and Debian 13 (Hermès), each converting the game with the same tree, the same engine revision and an empty library at the quick level, give equal per-frame traces (picture, sound, work RAM and program counter hashes) and equal final states on 15 of 15 routes: boot, two play runs, `varied` and an 18,000-frame pseudo-random route, for Tetris, Exodus and Super Mario Land (3 November 2026); `tools/gameboy_cross_os.py`, section *The cross-OS witness* below | Three of the 606 cartridges, the quick level, no thorough run, so the gate stays `P` in [QUALIFICATION.md](QUALIFICATION.md) (the same bar as the Neo Geo with three sets; the NES reached `Y` with the eight games of its campaign): `Y` would take the games of the campaign above, not these three; the compiler and the SDL build differ by system, which is what the equal traces show to be harmless for these routes, not for every game |
| G14 Owner | No recorded owner decision | His play test |
| G15 Honesty | `hardware_accuracy`, `full_game` and `physical_latency_measured` are false in the report; the interface and the report say "tested scenarios" and "not native" where it applies; the audit of 3 November 2026 of this page, [CPU_SM83.md](CPU_SM83.md) and the strings of the report found no claim of exactness, zero latency or hardware fidelity; repeated on 4 November 2026 on every public line that names the machine (README, `docs/*.md`, the interface texts of the eight languages and the converter strings, searched for the words of exactness, accuracy, perfection, zero latency and completeness, and the matches read): none claims more than the five separate measures | Words in other pages and in the interface strings of other machines are not covered |
| G16 Shared knowledge | Hints are numbers about a ROM (addresses, positions), rechecked on the exact ROM, and the conversion retries without them on failure ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md)) | A hint qualifies a path only after a conversion by another player reaches it and checks it against the reference |

- **Collection campaign, October 2026.** The supplied DMG collection was qualified with 6 concurrent conversions, up to six discovery
  passes and four 7,200-frame input scenarios. Initial batch: 592 qualified exact cartridges from 638 input files, 28 successful
  exact-copy extras skipped and 18 failed input attempts (17 distinct cartridges). Among qualified exports, 487 had zero fallback
  cycles on the scripted scenarios and 105 retained reported fallback; that snapshot embedded 773,878 verified ROM entry hints for
  592 identities, about 1.92 MiB compressed, while keeping failures and their diagnostics local. The targeted 10 October follow-up
  resolves 14 of the 17 failed identities. The current snapshot holds **793,352 ROM entry hints for 606 exact cartridges**; 500
  identities have zero fallback in their checked scenarios and 106 retain reported fallback. These are cumulative qualification results,
  not a fresh full-collection run.
- **The three cartridges that were unqualified** (Paperboy 2, Spiritual Warfare, The Ren & Stimpy Show: Veediots!, probes at the
  600-second timeout in the October campaign) are resolved on the 1.6.6 tree. Paperboy 2 converts alone (152 s, zero interpreter
  cycles; the timeout was not reproduced). Veediots stopped every probe because no frame completes with the LCD off; a frame now
  lasts 70,224 cycles then (1.6.5, [UPGRADES.md](UPGRADES.md)). Spiritual Warfare is a Wisdom Tree cartridge (below). Max passes the CPU
  comparison but retains writable-code fallback.
- **Wisdom Tree cartridges (1.6.6).** Five cartridges of the collection (Spiritual Warfare, Exodus, Joshua & the Battle of Jericho,
  the King James Bible, the NIV Bible & the 20 Lost Levels of Joshua) have a header of type 00, a size code of 00 and 128 KiB to 2 MiB
  of ROM, with the words WISDOM and TREE inside. Their mapper is a latch that switches the whole 32 KiB window by the **address** of a
  write to `0000-7FFF` (the low eight lines; the value is ignored; no RAM; bank 0 at power-on is our choice, the latch being undefined
  in hardware), described by [Pan Docs](https://gbdev.io/pandocs/othermbc.html) and detected as mGBA does; the runtime models it
  (`gameboy_runtime.adapt_wisdom_tree`). Converted one at a time on the 1.6.6 tree, the five pass the CPU comparisons with zero interpreter
  cycles on the final scenarios (Spiritual Warfare: 96 cycles at one site on the varied route; King James Bible and NIV Bible
  also run 271,745 and 388,361 work-RAM instructions one by one, counted apart), and a capture of each shows a real screen. Check:
  `tools/gameboy_wisdom_selftest.py`, on a cartridge authored for it. Hardware fidelity and gameplay beyond the probes are not
  validated for them.
- **The delivered file (1.6.6).** The compressed copy of the build is replayed on the four comparison routes against the reference
  verdict (gate G5), and each probe keeps a liveness record from the per-frame trace `--frame-trace` (gate G8), refused when the
  `varied` route never changes its picture: [UPGRADES.md](UPGRADES.md), `tests/test_gameboy_delivery.py`.
- **Sharing rule.** Only exact-ROM observations backed by successful CPU qualification are promoted into the ROM-free compilation
  snapshot; previous console records are kept; source ROMs and private RAM dumps are never part of it
  ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md)). The observations stay local in `Export/datas/library/gb`.
- **Authored fixtures** (no ROM): 5,777 CPU/memory/timing checks for the first guarded helper, **47,104** comparisons for the
  bank-boundary operands (conditional calls and jumps, several bank selections, flags and PPU phases), **28,277** for the added
  live-guarded helpers, a 65,535-call loop with bounded host stack matching 409,631 reference steps, a 1,024-entry selector fixture
  checking all 65,536 PCs, HALT-bug and DMA guards with complete 86-instruction transfers, the 21 APU checks above, and the RAM
  executor check (177 plain opcodes, and since 1.6.5 the `CB` prefix with its 256 second bytes). Private end-of-scenario states allow additional late CPU checks on affected exports.
- **Reference games.** The earliest three targeted cartridges, checked for 120 boot frames each: Tetris (no bank switching), Super Mario
  Land (MBC1) and Lazlos' Leap (MBC2 with battery RAM). The ten broader cases of 9 October: Kirby's Dream Land, Super Mario Land 2,
  Wario Land, Donkey Kong Land, Kirby's Dream Land 2, Link's Awakening, Metroid II, Pokemon Red, Pokemon Yellow and Wario Land II
  (MBC1, battery MBC3 and MBC5; MBC3 RTC and Color-only behaviour not exercised). All ten pass the mandatory boot and deep left/right
  CPU comparisons, a 6,000-frame varied-input probe and a save/close/relaunch comparison of the entire serialized state after 180
  resumed frames; eight have zero fallback cycles in that longer probe (Donkey Kong Land and Wario Land II executed some writable RAM
  code through the reported interpreter before 1.6.4). The risk cases for campaigns are in `tools/campaign-risk-cases.json`; details
  in the [journal](GAME_BOY_LOG.md).
- **Fallback improvements recorded.** Castlevania Legends 35,968,580 to 3,613,140 cycles, TMNT III: Radical Rescue 55,974,392 to
  15,647,464 and Track & Field 62,096,888 to 28,786,996 (all three keep visible fallback; every deep CPU comparison matched); Super
  Mario Land's 44,272 and 60,656 interpreted cycles at bank 3, address `7FF0` reach zero once the JP relay is compiled. These are
  scripted-path evidence, not whole-game coverage.

### The campaign of twelve games (1.6.7, gates G8 and G9)

Twelve cartridges chosen for what each could break (a reason per game in `tools/gameboy_campaign.py`) were converted one at a time at the
extended level, on the 1.6.7 tree, from an empty library, then replayed on the delivered file with `tools/gameboy_campaign.py`: the
reproducible pseudo-random route of the conversion for its whole length (18,000 frames) and the `varied` route, each with the per-frame trace
and six captures put on one sheet, which was looked at. The ROMs are read in place from the player's folder; the sheets and
the summary stay out of the repository.

All twelve converted to `supported`, with the CPU compared over the whole length of every route (`mode: full`; the long route over its first
3,600 of 18,000 frames), the compressed copy matching the reference on every route, the states verified in fresh processes and **no
interpreter cycle on any final route**. What each sheet shows (the specialist agent's reading, not the owner's):

| Game | Mapper | Long route (18,000 frames) | Writable code run one by one |
|---|---|---|---|
| Tetris | none | Games of falling pieces (score up to 16, a lost game, the top-score table); the `varied` route stays on the licence page and menus | 17,979 |
| Super Mario Land | MBC1 | The title, then the first level with the pause shown; the route is paused for most of its length (31 pictures), so it proves little depth | 17,975 |
| Link's Awakening | MBC1 + RAM | The intro, the title and the name entry on the `varied` route; the long route stays in the first room (2,063 pictures, animations) | 17,901 |
| Wario Land II | MBC3 + RAM | The title, then levels with enemies and a long route that plays: 2,877 pictures | 925,868 |
| Pokémon Red, Pokémon Yellow | MBC3, MBC5 + RAM | The logos, the introduction and the first bedroom; menus and dialogue render (855 and 1,002 pictures) | 17,950; 17,807 |
| Metroid II | MBC1 + RAM | The title, then Samus beside her ship for the whole long route (18 pictures: animation and palette) | 17,981 |
| Final Fantasy Legend II | MBC1 + RAM | The title, the introduction and the character menu (705 pictures); see the letters below | 36,523 |
| Mega Man V | MBC1 | The menu, the first level and its enemies, the life counter changing (5,516 pictures) | 77,317 |
| Contra: The Alien Wars | MBC1 | The title, then a level with enemies and a vehicle (8,690 pictures); upstream issue 24 (it does not start) does not occur on this ROM | 62,241 |
| Exodus | Wisdom Tree | A maze level: score 100 to 500, the timer running down, objects picked up (9,716 pictures) | 0 |
| The Ren & Stimpy Show: Veediots! | MBC1 | A level: the money 0 to 0.75, lives 3 to 1, the timer restarting (3,150 pictures); the screen-off wait does not stall | 3,684 |

What this shows: the delivered file is alive on every game of the panel (pictures and sound change, no stall, no crash) and plays a real
level or game on Tetris, Wario Land II, Mega Man V, Contra, Exodus and Veediots. What it does not show: complete games (the routes press
buttons, they do not play to a goal), the depth of the others (Super Mario Land paused, Link's Awakening and Metroid II in their first
room, Pokémon in its bedroom, Final Fantasy Legend II in its menus), hardware fidelity, or latency. The 12 games are 12 of the 606 qualified cartridges.

Two facts about the method. The probes of the conversions in this campaign were not played from a clean start: a game with battery RAM writes its save
beside the executable when it ends and the next probe of the same folder started from it (the `varied` route of Link's Awakening, run twice in one folder,
shows 179 pictures, then 184); the replays of the campaign do start clean, and from 1.6.7 on every probe empties the `datas` folder of the build first
([UPGRADES.md](UPGRADES.md)). The picture counts of the table are from the replays, the counts of instructions run one by one from the probes. And a route that ends in a menu or on a paused game is evidence of liveness, not
of depth: the lengths of the table are what the route reached, not what the game offers.

### The cross-OS witness (1.6.7, gate G13)

Tetris (no mapper), Exodus (Wisdom Tree) and Super Mario Land (MBC1) were converted on Windows and on Debian 13 (the machine Hermès) from the
same tree (the commit of 3 November 2026), at the quick level, from an empty library, with the pinned engine and the pinned SDL on each side
(29 to 43 s on the PC, 84 to 130 s on Hermès). Then the five routes of each game (boot, two play runs, `varied` and one pseudo-random route
of 18,000 frames, 73,800 frames per system) were replayed on the delivered file of each system, headless, from a private empty folder:
`python tools/gameboy_cross_os.py trace EXE --out DIR` on each system, then `compare DIR_A DIR_B`.

The per-frame traces (picture, sound, work RAM and program counter hashes) and the final states (registers, cycles, work and high RAM,
LY and PPU mode) are **equal on all 15 routes**. The generated sources are equal file for file (107 to 114 per game); the only difference
is the resource embedding, which is by design: a `.rc` file on Windows, `embedded_resources.c` and `.S` on Linux. The sound is compared
as a hash per block of samples inside the trace, not as a file. This says that the converter and the runtime give the same game on the
two systems for these three games and these routes; it says nothing about the other 603 cartridges, the thorough level, the speed on each
system or hardware fidelity.

### The public test ROMs of blargg and Mooneye (1.6.7, gates G10 and G11)

The two public suites were downloaded on 3 November 2026 and kept **outside the repository** (`.build/gb-testroms/`, one new folder per archive); only
names, hashes and verdicts are written here. Mooneye is MIT; the blargg archives carry no licence file and no licence text.

| Archive | Source | SHA-256 |
|---|---|---|
| Mooneye test suite `mts-20260714-0944-31510e1` (zip) | `gekkio.fi/files/mooneye-test-suite/mts-20260714-0944-31510e1/` | `18aa29462dfe1fcd32a2cb3621733abdc72410074918b9245aa99a6920f7d3f2` |
| blargg `cpu_instrs.zip` | Internet Archive, item `blargggameboytestroms` (the gbdev mirror did not answer) | `7ad9fd3b8dc61b9fa399ddc687acde37779025b8be307ca9cbc79d44d8ee8cd7` |
| blargg `instr_timing.zip` | idem | `10d11343126aac60986a57e87cf6816b5b05274da15b8c1ca65154a2853c2f5b` |
| blargg `mem_timing.zip` / `mem_timing-2.zip` | idem | `23fb8a4ddf3b1b000a62735641dee7c8eafb203d5f5ff35ac9cf239b29fe6e62` / `b55d5016e578cb7259b6423461dcebe67af5e077e5c0a7fc81076bb539025f1f` |
| blargg `dmg_sound.zip` / `dmg_sound-2.zip` | idem | `76bb61c85ed79d8894fffa9ab47884d0d543fd6fd24428d65b24bb9a767f9f99` / `458e9ac9dd89ab51bfbdad61d7902f5e6c3a9cbdd67f43f60c9f7ad59aa1a2e5` |
| blargg `oam_bug.zip` / `oam_bug-2.zip` | idem | `305d46d06b4b75f33362a3c402a3a20fcae194f8f1ea15d8c86c2dd27c9e0e63` / `2ad6c4ab79a1a47a32fb3a1940dd136edddfc0d6ebd58d8f59ee96aca22d4c9a` |
| blargg `cgb_sound.zip` (Game Boy Color only, not run) | idem | `0b8775cdeb9cd3a56656795dd76ae82df8e0ce855777a243f17ee5358acfa6bb` |

`python tools/gameboy_testroms.py convert ROOT --work FOLDER` converts each ROM with the converter (quick level, two conversions at a time, an empty library);
`run` then runs the delivered file headless in an empty folder and judges it by the protocol of its suite: the six Fibonacci registers (or serial bytes) of
Mooneye, the word "Passed" or "Failed" on the serial port, or the memory verdict of the newer blargg ROMs (`DE B0 61` at $A001-$A003, 0 at $A000 for a pass).
The frame limit grows by steps until a verdict shows, and the run is then repeated against the pinned interpreter in lockstep (`--differential`) for as many frames
as the test needed (26 to 1,051 frames for blargg, 61 to 601 for Mooneye). Every ROM was converted without error (all `supported`).

The first run (1.6.7 tree) gave 128 of 152. The whole set was converted and run again on the 1.6.8 tree, with the state of the console after the boot ROM, the phase
of the serial clock and the rules of the sound unit that the tests pointed at ([UPGRADES.md](UPGRADES.md#game-boy-the-state-after-the-boot-rom-the-serial-clock-phase-and-the-sound-unit-168-gates-g10-and-g11)); the third column gives both runs.

| Suite and group | Applicable | Passed 1.6.8 (1.6.7) | Failed | No verdict |
|---|---|---|---|---|
| Mooneye `acceptance` (CPU timing, interrupts, HALT, OAM DMA, PPU, timer, serial, boot state) | 66 | 66 (64) | 0 | 0 |
| Mooneye `emulator-only` (MBC1 13, MBC2 7, MBC5 8) | 28 | 28 (28) | 0 | 0 |
| blargg `cpu_instrs` (the 11 single ROMs) | 11 | 11 (11) | 0 | 0 |
| blargg `instr_timing`, `mem_timing` (3), `mem_timing-2` (3) | 7 | 7 (7) | 0 | 0 |
| blargg `oam_bug` and `oam_bug-2` (8 each) | 16 | 14 (14) | 0 | 2 |
| blargg `dmg_sound` and `dmg_sound-2` (12 each) | 24 | 18 (4) | 6 | 0 |
| **Total** | **152** | **144** (128) | **6** (blargg) | **2** |

Not applicable (41): 21 Mooneye ROMs (18 for other models: Super Game Boy, Pocket, DMG revision 0, Game Boy Color and Advance; two tools that dump the boot ROM; and `sprite_priority`, a
test to look at, with no verdict); the 13 `cgb_sound` ROMs; and the 7 blargg ROMs that combine the single ones (the single ones are run). The two
versions of `dmg_sound` and of `oam_bug` give the same verdicts, ROM for ROM.

*What passes.* All CPU and timing tests, including `cpu_instrs` (the 11 groups of every instruction and flag), `instr_timing`, `mem_timing`, Mooneye's `add_sp_e`,
`call`, `jp`, `ret`, `push`, `pop`, `rst`, `ld_hl_sp_e`, `di`, `ei`, `halt` (five), `intr_timing`, `daa`, `ie_push`, `rapid_di_ei`; the eight OAM DMA tests; the thirteen
PPU timing tests (interrupts, STAT, LYC, LCD on); the thirteen timer tests (`tim*`, `div_write`, `tima_reload`, `rapid_toggle`); `mem_oam`, `reg_f`, `unused_hwio-GS`, `boot_regs-dmgABC`,
`boot_div-dmgABCmgb`, and since 1.6.8 `boot_hwio-dmgABCmgb` and `serial/boot_sclk_align-dmgABCmgb` (the state of the registers, the LCD line and the serial clock right after the boot
ROM, for the DMG ABC); the MBC1, MBC2 and MBC5 bank and RAM tests; seven of the eight `oam_bug` tests (the OAM corruption bug of the console); and nine of the twelve `dmg_sound` tests
(registers, length counter, trigger, sweep, sweep details, overflow on trigger, length and sweep period sync, length counter during power, registers after power).

*What fails, and the probable cause.* (Looked at on the screen of each test.)

- **`dmg_sound` `09-wave read while on`, `10-wave trigger while on`, `12-wave write while on`** (both versions): the three read or write the wave RAM, or trigger the wave channel, while it plays, and
  expect the byte the channel is reading at that very cycle (a window of two clocks, and corruption of the RAM on a trigger). The runtime advances the wave channel with the sample clock of the audio
  unit, not by cycle, so the byte it hands back is not the console's. Not attempted: it needs a wave channel exact to the cycle in a unit that is the upstream's (hardware fidelity of the APU
  is not claimed). No game of the 12-game campaign shows the difference.
- **No verdict at 10,800 frames (three minutes of game time):** `oam_bug/7-timing_effect`, in both versions (a blank screen). The test derails before it ends (see below); why it
  leaves its path is not known. It is counted as not passed for the gates. `dmg_sound/07-len sweep period sync`, which had no verdict on the 1.6.7 tree, now passes.

*A finding on the comparison with the interpreter.* On every test but one the native code and the pinned interpreter agree step by step for the whole run (from 200,000 to 92 million steps), on the picture
and the sound as well as on the CPU. On `oam_bug/7-timing_effect` (the first version of the ROM only) the lockstep stops at step 6,717,022 (about 784 frames): the generated code is one four-cycle step behind
the interpreter (PC `$2154`, SP `$C0A6` against PC `$0038`, SP `$C0A4`). Found on 4 November 2026: at that step the program fetches its instructions from the ROM while an OAM DMA transfer is under way. The
pinned interpreter then reads `$FF` for the opcode (its model of the bus conflict: on a console the CPU reads the byte the transfer is moving when the transfer uses the bus the code is fetched from; a transfer whose source is in video RAM leaves the ROM and the work RAM readable) and executes `RST $38`; the generated code executes the instruction it translated. A program that fetched from the bus the transfer uses would read the transfer's bytes on a console, not its code, so this is a run that has already left its path, not a difference a game can reach; the interpreter's `$FF` is a model too. It is **not corrected**: checking
every instruction fetch against the state of the transfer would put a test in the hot path of every game for a case no game has. The second version of the ROM does not get there and matches for
10,800 frames. Why the first version leaves its path (in the native code and in the interpreter alike) is not found.

*What it leaves out.* A pass says that the converted file and the console's own test agree on that behaviour; it is not a claim of cycle-exact hardware: the test suites do not cover everything
(STOP, the Super Game Boy, the whole sound unit, the PPU's pixel details), the state after the boot ROM is the one of the DMG ABC revision only (the other revisions are not applicable and not
modelled), only the PPU is stepped to it and the divider keeps its value (the phase between DIV and the PPU is not tested), and no hardware capture was made. These tests were run one conversion each at the quick level; they
say nothing about a game.

### Letters missing in a menu of Final Fantasy Legend II

On the sheet of Final Fantasy Legend II some letters are missing in the character menu and in the introduction text: the `i` of "Slime" on every
frame, the `o` of "Robot" on some, the `d` of "and" once. It is not a transition (eight consecutive captures show it). It is **not an effect of the 1.6.7
changes**: the same route on a conversion of the 1.6.6 tree (`tools/ab_conversion.py`, quick level) gives the same frames byte for byte at
frames 2,980, 5,960, 5,972, 5,980 and 5,988, the missing letters included. The lockstep comparison cannot tell whether it is the game's own
behaviour or the pinned PPU model, since the interpreter shares the PPU, and no external emulator was used. It is recorded here as an
unexplained observation about the rendering of this game (a candidate for a check against a reference emulator, not a claim about the
hardware); it does not change the status of the conversion.

## Known limits

- **Not native code:** the interpreter fallback is always counted and shown per CPU; the one-by-one WRAM and HRAM instructions are
  reported apart and are not native either. Fallback percentage is unknown on purpose (no defensible denominator).
- **Hardware fidelity:** not validated. The APU is not complete (wave channel, timer low bits, analogue output); the PPU is the pinned
  runtime's model. Sprite-limit flicker reported in some games has no established cause and is not hidden.
- **Gameplay validation:** scripted paths only, no completed games; the user performs visual, gameplay and listening checks.
- **Physical latency:** not measured; host-buffer figures are not latency.
- **Cartridges:** MBC3 RTC persistence has no independent regression test; no `.gbc`-only games, link cable, Camera, Printer or Super
  Game Boy.
- **Cold build time** is high for large cartridges: in the parallel batch Wario Land II took about 24 minutes and Pokemon Yellow's
  corrected cold conversion about 23, mostly compiling large generated C files over two passes. Bundled observations avoid
  rediscovery and another pass but not the first C build. Wario Land II re-run on 29 October 2026 on an empty library: about 10 minutes of conversion in one pass (600 s, against 709 s in two passes before the `CB` prefix was handled).
- **Existing exports** are not replaced; regenerating a cartridge uses the new compiler and runtime adaptations.
- **Window string.** The window says "RAM and high-memory instructions executed one by one (not native)" (in the eight languages
  since 1.6.5): the count is the sum of the one-by-one executor, the RAM stub and the `0xFF00-0xFF7F` stub, as a maximum over the scenarios.

## History

The dated evidence (broader cartridge cases of 9 October 2026 with the 1.6.4 follow-up, the build and correctness follow-up of 10
October, the shared APU corrections and audio measurements of 11 October, conversion timings and the earliest three cartridges) is in
[GAME_BOY_LOG.md](GAME_BOY_LOG.md). The other documents that carry Game Boy facts: [UPGRADES.md](UPGRADES.md) (what each release moved),
[AUDIO.md](AUDIO.md#game-boy-output) (output delay), [COMPATIBILITY.md](COMPATIBILITY.md) (validation scope),
[BUILDING.md](BUILDING.md) (build timings) and [CPU_SM83.md](CPU_SM83.md) (the processor).
