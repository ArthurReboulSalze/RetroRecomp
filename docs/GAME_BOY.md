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
| Cartridge: ROM banking and battery RAM | `runtime/src/gbrt.c` | MBC1 (the runtime also detects MBC1M multicart wiring), MBC2, MBC3 with its real-time clock, MBC5, and cartridges with no mapper. Cartridge types `0x01-0x03`, `0x05-0x06`, `0x0F-0x13` and `0x19-0x1E` are the ones the runtime banks. Battery RAM and the clock are written only when they changed |
| Timer, interrupts, OAM DMA, joypad | The pinned runtime | Run by the pinned runtime in step with the CPU's cycle counts; the HRAM sprite-DMA wait routine is a guarded helper (below). Input is sampled by the host kit's pad word |
| Peripherals | Joypad only | No link cable, Camera, Printer or Super Game Boy |
| Player shell | The host kit, `native/hostkit/adapters/rrhk_gb.inc` | Window, menus, bindings, controllers, sound device and pacing since 1.6.3 ([HOST_KIT.md](HOST_KIT.md)) |

Where the five measures stand: **native code** is reported per scenario with the interpreter and the one-by-one executors shown
apart; **CPU fidelity** is a comparison against the pinned reference interpreter on short scripted scenarios (see
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
| Native | `native/gb_ram_helpers.h`, `gb_ram_checks.c`, `gb_boundary_checks.c`, `gb_audio_checks.c`, `gb_latency_checks.cpp`; the adapter `native/hostkit/adapters/rrhk_gb.inc` |
| Self-tests (build C, need a compiler, no ROM) | `tools/gameboy_ram_selftest.py`, `gameboy_boundary_selftest.py`, `gameboy_display_selftest.py`, `gameboy_hardware_selftest.py`, `gameboy_latency_selftest.py` |
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
30 boot frames. **Deep Game Boy validation (slow)** adds up to 240 frames per input scenario. Both modes require the requested
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
- **Battery RAM and the real-time clock** use `datas/games/<game-title>-<ROM-SHA-prefix>/`, only when written. Battery RAM is flushed on
  exit only after a changed RAM value; a game's own automatic save can therefore create this folder without a manual state save.
  An isolated two-frame launch of Lazlos' Leap (MBC2 with battery RAM) created no `datas` folder. MBC3 RTC persistence has no
  independent regression test yet.

## Qualification

Gate status for the Game Boy is in [QUALIFICATION.md](QUALIFICATION.md) (the column `gb`); the checks below are what exists today.
Deep CPU checks compare instructions and memory for 30 boot frames and 240 frames of each of the three input scenarios (the Game Boy
release check compares the CPU once, on a short boot, not on every final scenario as the other writers do). These checks do not cover
all gameplay, certify hardware fidelity or measure physical latency.

- **Collection campaign, October 2026.** The supplied DMG collection was qualified with 6 concurrent conversions, up to six discovery
  passes and four 7,200-frame input scenarios. Initial batch: 592 qualified exact cartridges from 638 input files, 28 successful
  exact-copy extras skipped and 18 failed input attempts (17 distinct cartridges). Among qualified exports, 487 had zero fallback
  cycles on the scripted scenarios and 105 retained reported fallback; that snapshot embedded 773,878 verified ROM entry hints for
  592 identities, about 1.92 MiB compressed, while keeping failures and their diagnostics local. The targeted 10 October follow-up
  resolves 14 of the 17 failed identities. The current snapshot holds **793,352 ROM entry hints for 606 exact cartridges**; 500
  identities have zero fallback in their checked scenarios and 106 retain reported fallback. These are cumulative qualification results,
  not a fresh full-collection run.
- **Still unqualified:** Paperboy 2, Spiritual Warfare and The Ren & Stimpy Show: Veediots!. Their probes hit the unchanged
  600-second timeout, so their observations are not added to shared knowledge; a timeout is kept as a symptom, not labelled as a
  proven CPU or mapper bug. Max passes the CPU comparison but retains writable-code fallback.
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
