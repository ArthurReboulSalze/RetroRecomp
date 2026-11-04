# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

This page keeps the rules, the current release and the one before it. The detail of releases 1.6.6 to 1.6.4 is in
[UPGRADES_HISTORY.md](UPGRADES_HISTORY.md), and that of 1.6.3 and before in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md) (the same text,
the same anchors).

## When an export is upgraded

A conversion batch (or **Reconvert** in the collection) upgrades a game only
when all of the following hold:

- the previous export has a version 3 receipt (the only one this release
  writes and reads), and its executable is exactly the file that receipt names;
- the request's **game part** is unchanged: game-side converter inputs, scan
  level, passes, frames, video standard, BIOS or machine identity, target,
  ROM and the bundled or imported knowledge for that cartridge;
- no new gameplay hints (F12 feedback) were recorded since that export;
- the previous validation did not fail;
- only the **host part** changed: host inputs, title, language, artwork or
  icon tags.

Older receipts have no game part: the first batch after updating from a release
before 1.6.0 converts each game once in full. A forced conversion from the queue
always rediscovers; **Reconvert** in the collection always rebuilds, but
upgrades when the conditions above hold.

A third role, **build**, covers the choice of the C toolchain
(`retrorecomp/toolchain.py`): changing the compiler or its options also upgrades an
export, because the executable is recompiled and rechecked on the quick routes.
Exports of the **previous release** can be accepted the same way through an explicit list of
equivalent game stamps; see [Build inputs](COMPILATION_LIBRARY.md#build-inputs-and-exports-of-an-earlier-release-that-stay-upgradable-150).

## The rule: the previous release only

Backward compatibility is owed to the previous release and to nothing older (decision of 28 October 2026). For release
N it covers the exports, receipts, quick states and local files that release N-1 wrote, and nothing else:

- `LEGACY_GAME_STAMPS` (`retrorecomp/stamp_inputs.py`) lists the game stamps of release N-1, where its exports were
  shown to differ from release N only in how the game is built (none when the release changes what a game does). The
  release procedure replaces the entries, it never adds to those of an older release. The table was empty in the tree of
  1.6.0; the tree of 1.6.1 listed the stamps of 1.6.0 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-160-in-161)); the tree of 1.6.2 listed those of
  1.6.1 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-161-in-162)); the tree of 1.6.3 listed those of 1.6.2 ([history](UPGRADES_HISTORY_OLDER.md#exports-of-162-in-163)); the
  tree of 1.6.4 lists none, a full reconversion of every console ([below](UPGRADES_HISTORY.md#exports-of-163-in-164)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1. The Mega Drive, Super Nintendo, Neo
  Geo and CPS-1 keys of 1.6.1 (Windows) in the tree of 1.6.2. The same four consoles' keys of 1.6.2 (Windows) in the
  tree of 1.6.3. The Neo Geo key of 1.6.3 (Windows) alone in the tree of 1.6.4: the Mega Drive and Super Nintendo keys did
  not move, and the CPS-1 and NES states changed ([below](UPGRADES_HISTORY.md#exports-of-163-in-164)).
- A receipt of another schema than the current one (3) is never current, and a report is read in the places the current
  writers use (`scan_level`, `scan.level`), not in those of releases before 1.6.0.
- Nothing migrates the files of a release older than N-1 (collection inventories without a recorded base, the X68000
  observation pairs of the development stages, the library of the former name, default key bindings of old settings).

A player coming from an older release reconverts (or reinstalls); nothing is lost on disk, the old files are simply
not read.

## What an upgrade does

The console's normal conversion runs at the **quick** scan level: one pass on
the shortest routes of that console (see [scan levels](CONSOLES_16BIT.md#scan-levels)).
The compiler starts from the same learned paths (local library, bundled and
imported knowledge), so the same code is generated. Native code is still
compared with the reference CPU on those routes, quick states are still
checked where the console checks them, and any interpreter fallback is still
reported. Nothing is skipped silently: the report carries an `upgrade` block
with the reason, the check level and the original discovery (its version,
date, scan level and final checks), kept across successive upgrades. The
collection marks a game as using fallback if either the quick check or the
inherited discovery met it.

An upgrade does not claim more than it checked. It does not replay long or
pseudo-random routes, and it is not a fidelity or latency measurement.

## Lead: the engine sources and SDL follow their pins in an older library (1.6.8)

Every conversion of every console first prepares the shared pieces in `.deps` (`core.dependencies()`): the Master System and
Game Gear engine sources (`.deps/smsggrecomp`, `core.ENGINE_REV`) and the SDL2 sources (`.deps/SDL`, `core.SDL_REV`). Up to
1.6.7, a checkout of another revision than the pin was refused ("Version inattendue de SDL"), and nothing converted. SDL moved
in 1.6.4 (2.32.8 to 2.32.10), so a library whose `.deps` a release up to 1.6.3 had made refused every conversion from 1.6.4 on
(found on 3 November 2026 by the CPS-1 release check, which reused an old workspace). Deleting `.deps/SDL` was the workaround.

From 1.6.8, `core.follow_pin` brings both checkouts to their pins through the shared `conversion_common.pinned_checkout`:

- a clean checkout of another revision fetches the pinned revision (no fetch when the checkout already has it), checks it out
  detached and updates its submodules; the window and the log say "Updating SDL to the pinned revision…". The SDL install is
  keyed by its revision (`platforms.sdl_install_key`) and the Z80 → C translator by its patched sources, so both rebuild by
  themselves, once;
- untracked files (the SDL build and install folders live inside `.deps/SDL`) are not edits;
- the conversion still stops, and the folder is left as it is, when tracked files carry edits (now also at the pinned
  revision, as the other consoles' engines already did), when the folder is not a git checkout, or when the revision cannot be
  fetched (offline). Each case has its own message in the log, in French and English; the window's steps are in the eight
  interface languages. A missing or empty folder is cloned, as before.

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| all nine consoles (`retrorecomp.core` is a game input of every console; read with `compilation_inputs.role_stamps` before and after) | none (`i18n`, `gui_updates` and the locales are interface files) | no key moves (no native file changes) |

What a game does is unchanged: the pins themselves do not move, and a library already at the pins runs the same commands as
before plus the edit check. `tests/test_dependency_pins.py` covers each case with local repositories (no network).

*Review retouches (1.6.8, structure only).* The hash of a silent sound frame is now read in one place: `delivery_evidence.silent_hash`
(per number of samples, the Neo Geo and the CPS-1) and `silent_hashes` (every even count, the Super Nintendo), instead of three
readings of the same multiplies; the sets are the same as before (checked value for value). The DSP-1 and CX4 adaptations of the
Super Nintendo find their pinned text through `snes_chips.anchor`, so a moved text refuses the conversion with its message instead
of a Python error. Game stamps that move: every console (`delivery_evidence`), already moving with the pins above; what a game
does is unchanged.

## Game Boy: the state after the boot ROM, the serial clock phase and the sound unit (1.6.8, gates G10 and G11)

The public test ROMs ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)) showed where the runtime differs from the console right after the boot ROM and in the sound unit.
Four corrections, all `replace_once` patches of the private generated project (a moved upstream marker refuses the conversion; `tests/test_gameboy_boot_apu.py`):

- **The sound unit starts where the boot ROM leaves it** (`gameboy_hardware.adapt_post_boot_apu`): channel 1 is on at volume 0 with the 64 of the length counter the boot ROM's note wrote, so `$FF26` reads
  `$F1` (it read `$F0`). The mix is unchanged: the channel is silent.
- **The LCD starts where the common console leaves it** (`gameboy_runtime.adapt_boot_ppu_phase`): the pinned reset has the LCD where the first revision of the console leaves it, at line 145; the common revision
  (DMG ABC) leaves it in vertical blank with LY already reading 0 (STAT `$85`), late in line 153. Mooneye's `boot_hwio` accepts a window of phases (it passes at the steps tried from 3,950 to 4,108 dots after the reset and fails
  at 3,900 and below and at 4,150 and above); the PPU is stepped by 4,096 dots after its reset in a DMG without boot ROM (line 153, dot 452, mode 1, LY reading 0; no vertical-blank edge is crossed). The exact dot within
  the window is not measured. Only the PPU is stepped, the divider keeps its value: the phase between DIV and the PPU is not tested.
- **A serial transfer with the internal clock ends on the phase of the divider** (`gameboy_runtime.adapt_serial_phase`): the first bit comes at the next falling edge of bit 8 of the divider, not 4,096 dots after the start.
- **Rules of the sound unit** (`gameboy_hardware.adapt_power_off`, `adapt_length_clock`, `adapt_sweep_calculation`): the power switch of `$FF26` keeps the wave RAM and the length counters, and the length part of
  NR11, NR21, NR31 and NR41 is writable while the unit is off; enabling a length in the first half of a length period clocks it once and a trigger of an empty counter loads one less; a sweep with a shift of 0 still
  calculates at every sweep clock (nothing is written back, an overflow turns the channel off); leaving negate mode after a calculation made in it turns channel 1 off. The negate flag lives in the unused `freq` field of
  channel 1, so the saved sound state keeps its size.

*Proof.* On the 152 test ROMs of blargg and Mooneye, 128 passed on the 1.6.7 tree and 144 pass now: `boot_hwio-dmgABCmgb` and `boot_sclk_align-dmgABCmgb` pass, and `dmg_sound` goes from 4 to 18 of 24
(both versions of each test). Native code and interpreter stay equal step by step on every test but `oam_bug` `7-timing_effect` (see [KNOWN_FAILURES.md](KNOWN_FAILURES.md)). Six `dmg_sound` tests (the wave
channel read, trigger and write while it plays) still fail.

*Hot path: not touched.* The generated code and the per-sample mix are unchanged. The serial rule runs when a transfer starts, the PPU rule once at reset, the sound rules on writes to the
power switch, NR10, NRx1 and NRx4 and on the 128 Hz sweep clock. Channel 1 is enabled from the reset, so its timer and its 64 Hz envelope step from frame 0 (a contribution of 0 at volume 0). No timing was taken.

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| Game Boy only (`retrorecomp.gameboy_runtime` and `retrorecomp.gameboy_hardware` are inputs of its `game` stamp; read with `compilation_inputs.role_stamps` against the base of the branch: the other eight consoles do not move) | none | no key moves (the saved sound state keeps its size) |

*What it changes in practice, measured on twelve games.* The twelve games of the 1.6.7 campaign were converted on the 1.6.8 tree and replayed with the three runtimes (1.6.7, the new sound unit alone, everything) on
their four routes (boot, two play runs and the pseudo-random route of 18,000 frames), comparing the picture, sound, work RAM and program counter of every frame (`tools/gameboy_cross_os.py`):

- **The sound rules alone change no picture, no work RAM and no program counter on any frame of the 48 routes**; the sound hash of the frame differs on ten of the twelve games (not on Contra or Pokémon Yellow),
  probably from the phase of channel 1, which now runs from the boot ROM on, and where a length edge case occurs. This was not heard against a console.
- **A behaviour change, decided on 4 November 2026: the LCD starts where the common console leaves it (the DMG ABC, LY reading 0 in vertical blank, confirmed by `boot_hwio`).** The game starts 4,096 dots (nine lines) later in the frame. A game of 1.6.7 that is converted
  again **no longer replays frame for frame what it did**: the program counter and the work RAM at the end of a frame differ from the first frames on most games (table below), and what depends on the timing follows
  (Tetris deals other pieces on its long route; animations and random numbers elsewhere). All twelve stay alive: the number of different pictures per route stays within a few percent except Metroid II's boot route and
  the long routes of Final Fantasy Legend II, Pokémon Red and Tetris, which show more because the game reaches other screens. Same policy as the corrections found by the independent vectors.
- One figure to read with care: the count of frames with a non-zero sample falls on some games (Metroid II 17,645 to 14,304 frames of 18,000). It counts a constant offset of the output filter left at silence
  (142 on each side of 32,768 on Metroid II in 1.6.7), which the new start does not keep; the mixed channels are silent in both.

| Game | Routes (of 4) with the sound hash of 1.6.7, sound rules alone | Routes (of 4) equal to 1.6.7 in picture / sound / work RAM / program counter, everything | Frames with another picture (of 21,600) |
|---|---|---|---|
| Contra: The Alien Wars | 4 | 0 / 0 / 0 / 0 | 768 |
| Exodus | 3 | 4 / 0 / 0 / 0 | 0 |
| Final Fantasy Legend II | 0 | 0 / 0 / 0 / 0 | 20,448 |
| Link's Awakening | 0 | 0 / 0 / 0 / 0 | 2,373 |
| Mega Man V | 3 | 4 / 0 / 4 / 0 | 0 |
| Metroid II | 0 | 3 / 0 / 2 / 0 | 166 |
| Pokémon Red | 0 | 0 / 0 / 0 / 0 | 4,334 |
| Pokémon Yellow | 4 | 0 / 0 / 0 / 0 | 1,257 |
| Super Mario Land | 1 | 0 / 0 / 0 / 0 | 453 |
| Tetris | 0 | 3 / 0 / 3 / 0 | 17,021 |
| The Ren & Stimpy Show: Veediots! | 2 | 4 / 0 / 4 / 4 | 0 |
| Wario Land II | 0 | 4 / 0 / 4 / 4 | 0 |

The routes are the boot, the two play runs and the pseudo-random route of 18,000 frames of each conversion (quick level, an empty library); with the sound rules alone the picture, the work RAM and the program counter are equal to 1.6.7 on every route of every game. Final Fantasy Legend II shows another picture on nearly every frame (its title and menus animate on the timing); this was not looked at screen by screen.

## Sharp X68000: the picture is converted only when the host reads it (1.6.8, frame cost)

*Frame cost (1.6.8 item).* R-Type measured 1.05 against 1.6.6 on 3 November 2026 (+0.028 ms a frame, 0.591 to 0.619, quiet PC, start-up taken out
of both). Found by reading and counting, nothing timed. R-Type draws 256 x 256 pixels a frame (read from the report of a headless run: 65,536 pixels).
**The cause is the colour correction of 1.6.7** ([the intensity bit](#sharp-x68000-the-intensity-bit-of-the-palette-lifts-red-green-and-blue-167)),
in this way: until 1.6.6 the core handed its RGB565 buffer to the host as it was, and the conversion to the window's pixels lived in the window kit
(`player_picture`, only reached when a window is open). 1.6.7 moved the work into the core: every frame, `convert_frame` reads the machine's 16-bit
colour word of each pixel, looks it up in a 65,536-entry table and writes a 32-bit pixel, whatever the host does with the picture. A headless run
(the benchmark, the conversion's own routes without a report, a user's `--headless`) reads nothing, so it paid 65,536 lookups, loads and stores a frame
for no one: about one cycle a pixel is 22 microseconds on a 3 GHz core, which is the size of the +28 microseconds measured, the rest being the 256 KB
table and the 256 KB of 32-bit pixels competing for the cache with the emulation. The other candidates were read and eliminated by count: the
Musashi corrections touch only the overflow path of `DIVU` and `DIVS`, `CHK`, `LINK A7` and the opcodes `F620`-`F627`; the shared state rules touch
`LINK`, `UNLK` and `NEGX`, a local variable and one test that fold at compile time; the libretro comparison base leaves the build files without a
change of compile flag (`-O2`, no profile-guided build for this machine, so no profile to go stale); the host kit changed only in the Super Nintendo adapter.

**The fix.** The core asks libretro's "video enabled" bit (`RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE`) at each frame and converts only when it is set.
The reference host, which is also the host of a window, answers from what it does with the picture: a trace or a report hashes it, a capture or a window
keeps it; a headless run with none of these does not read it, and the core hands it the last converted picture again. The machine, its state,
its sound and every hash are untouched. A host that does not answer is treated as wanting the picture. A saved state redraws through the full
conversion whatever the answer (`rr_x68k_framebuffer`). In a window nothing changes for the player: the conversion still runs each frame, and it is
**not more expensive than in 1.6.6**, where the kit converted the same pixels with three multiplications and divisions each; now a table lookup in the core and
a plain copy in the kit.

**Proof.** (1) Counted, not timed: a build of this tree with a counter in `present_frame` (not kept) ran R-Type for 900 frames. Headless with no report,
as the benchmark runs it: 0 frames converted, 899 skipped. Headless with `--report`: 899 frames converted (138,870,784 pixels, the start-up pictures
being larger than the 256 x 256 of the game), 0 skipped. (2) The machine is untouched: both runs saved a state at frame 800 (`--state-slot`, `--state-save-at`)
and the two files are the same, 19,410,352 bytes, same SHA-256. (3) The fingerprints are the same: the conversion hashes the picture of every route, so its runs convert every
frame: a conversion of R-Type on this tree has the CPU, RAM, picture and sound hashes of the same conversion before the change, on the three routes
(R-Type and Bubble Bobble, 253 values of the checks compared, 0 differ in hashes, counters and interpreted opcodes; the one difference is the report field `packed.method`, added to main after the baseline was converted). (4) `tests/test_x68000_colour.py` fixes the contract in the sources.
The speed itself is not timed here: the measurement on a quiet PC is the lead's.

**What moves.** The Sharp X68000 game stamp (`libretro_api.c` and `reference_host.c` are game inputs): an export of 1.6.7 stays as it is, and a 1.6.8 export is
a full reconversion. **The state compatibility key `RR_X68K_STATE_ABI` moves too** (it hashes `reference_host.c`): a quick state written by a 1.6.7 export is
refused cleanly by a 1.6.8 game (no compatibility key, no crash, no overwrite); the layout of the state is the same. Host and build stamps and the other
consoles do not move.

## Super Nintendo: the ROM address without a division, the 65816 stack pages, the SPC700 EI and DI, the evidence (1.6.8)

*Frame cost (1.6.8 item 1).* Secret of Mana measured 1.04 against 1.6.6 on 3 November 2026 (+0.23 ms a frame, quiet PC, start-up taken
out). Found by reading and counting, nothing timed: the training run of the conversion (1,800 frames, `hardware-profile.profdata`)
counts, per frame, 97,126 calls of `cart_getRomPtr`, 52,020 of `cpu_read8` and 41,870 evaluations of `rr_snes_cart_ram_offset`. The
pinned `cart_getRomPtr` ended every ROM byte read (the CPU, the instruction fetch, a DMA) in `off % cart->romSize`, a 32-bit division,
inlined in `cpu_read8`, `bridge_bus_read`, `rr_snes_cpu_read_begin` and the interpreter's step. What 1.6.7 added on that path is small by the
same count: the image-size comparison of the ExHiROM board in the HiROM read (two instructions), the S-DD1 board test in
`rr_snes_cart_ram_offset`, the emulation-flag tests of the branches and of the indexed direct-page addressing; the hot functions grew by
13 to 38 instructions (`interp816_runOpcode` 439 to 477, `cpu_read8` 373 to 406, `cart_getRomPtr` 186 to 201) and the step's frame by 16 bytes. That is
about half a million instructions a frame at most, under 1 %: it does not explain 4 % alone, and a code layout that moved is a reasonable
remainder. The change: the remainder is the mask when the size is a power of two (every image the loader pads), and is the division for any other
size, so the address is the same in every case (`snes_cart.adapt_cart`, `native/snes_cart_checks.c` compares the pointers of 7 sizes, 2 of them not
powers of two, over every bank); the Super FX board's code lookup, which had its own remainder, divides by the constant length that
`rr_snes_native_bind` has already checked. *Hot path: touched, expected faster, not timed* (the lead asks Arthur for the quiet-PC slot).
Proof: A/B of the 1.6.7 tree and this one, from an empty library, Secret of Mana: the 19 hash fields of each of the six probe files
(native, packed copy, reference; demo and play) are equal; what differs is `cart.c`, the compiler's profile data and the analysis file.

*Stack pages of the 65816 in emulation mode (gate G10).* `PEA`, `PEI`, `PER`, `PHD`, `PLD`, `JSL`, `RTL` and `JSR (a,x)` step the 16-bit
stack pointer without wrapping and set its high byte back to 1 only at the end; the 6502 instructions keep wrapping after every byte
(`snes_codegen.correct_stack_pages`, fail-closed on the pinned text; native mode is the same text as before, and `JSL` is cheaper: no flag test
after each byte). The vectors: 0 semantic differences in the 130,448 cases of the larger run (it was 11) and in the 32,768 of the usual one.
A game that stays in emulation mode and keeps its stack at the edge of page 1 is the only one concerned.
`PEA` also loses a hack of the pinned engine, which zeroed Y when the operand was `$C2AE` (no counterpart on the chip; Super Metroid holds 38 sites of those
bytes and is the likely target). Six cartridges that hold the bytes convert with identical hashes before and after on the standard routes (Super Metroid, Axelay,
Breath of Fire, Terranigma, Samurai Shodown, Battle Clash); a game whose later routes run that exact `PEA` could still move, and would then be showing what the chip does.

*SPC700 `EI` and `DI`* take 3 cycles (the pinned table said 2; the chip's timing and the vectors agree, `snes_spc.interrupt_flag_cycles`).
This one changes what a game does where its sound driver runs these instructions: **Chrono Trigger's driver does** (the observed
positions hold four of them), and its conversion, A/B against the tree before, keeps the same pictures in the demo but a different count of APU
cycles (+11), a different sound hash and a main CPU that is 390 cycles shorter over the 24,000 frames; the other games of the panel that do not
use them are identical. It is its own commit (`878ec77`): it can be left out of a release that wants every hash identical.

*Audible frames.* A frame is audible when its sound hash is not the hash of silence for its number of samples (`snes_evidence.silent_blocks`,
the method of the Neo Geo and the CPS-1; the host does not change). Every final check now carries `liveness.audible_frames` and
`last_audible_frame` instead of `None` (gate G8).

*Report.* `qualification_scope.universal_zero_fallback_claim: false` and `native_validation.independent_cpu_oracle: false` (the conversion's
reference is the engine's own interpreter), read back by the common `honesty` block (gate G15).

*Engine pin* (`snesrecomp` from `a00df26` to `fb8cf15`, the reasons and the four reworked adapters in [UPSTREAMS.md](UPSTREAMS.md#super-nintendo-the-pin-of-168)).
What a game does is unchanged on the panel: the tree of this release at the old pin and at the new one give the same 21 hash fields (picture, sequence,
CPU, RAM, video, colour and sprite memory, sound RAM, PCM, program counter, cycles, device state) in each of the six probe files (native, compressed copy,
reference; demo and play) on eight games, one per board: Secret of Mana (HiROM), Super Mario World (LoROM), Lock On (DSP-1 on HiROM), Street Fighter Alpha 2
(S-DD1), Star Fox (Super FX), Mega Man X3 (CX4), Kirby Super Star (SA-1) and Dragon Quest III (ExHiROM). The twelve games of the panel convert at the new
pin with the native run equal to the reference, the compressed copy equal to it, and 0 interpreted opcodes of the 65816 and of the SPC700. The Linux build (GCC)
of the new engine builds and runs; its per-frame traces equal the Windows ones on four games and twelve routes (Secret of Mana, Super Mario World, Star Fox and
Kirby Super Star: the attract and play routes of 3,600 frames and one pseudo-random route of 18,000 frames of each, `tools/snes_cross_os.py`). Two adaptations are
beyond the anchors: the engine counts the native-mode `BRK` cycle itself (our correction of 1.6.3 is retired, the adapter requires the engine's line), and
its UTF-8 manifest resource is left out of the Windows link (the game carries the converter's manifest; two do not link). Not enabled: what the range offers
behind a build selection (fused ROM reads, fused DSP mixing, APU spans, HD Mode 7).

*Stamps* (`compilation_inputs.role_stamps`, the tree of 1.6.7 against this one):

| Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- |
| the Super Nintendo, the Mega Drive, the Neo Geo and the CPS-1 (`console16.py` is a game input of the four: it holds the pin and the report block); the other five do not (the game stamps of all nine already move with the pins of the lead's section above) | none | the Super Nintendo's `RR16_STATE_ABI` moves (it hashes the pinned revisions and the fingerprints of the `snes_*` modules); so does the Mega Drive's, because `console16_state.write_config` hashes the whole `revisions` dictionary, which holds the snesrecomp pin (moot for the release, which moves it anyway): a quick state of 1.6.7 is refused cleanly; a battery save is not concerned |

*Tools that change no export.* `tools/snes_cross_os.py` (the per-frame witness between two systems, gate G13), `tools/snes_route_captures.py`
(the last picture of each route, gate G9), `tools/snes_game_saves_check.py` (the battery save of a delivered game across three processes,
gate G7). `tools/snes_cpu_vector_selftest.py` takes the larger sample with `--samples 256`.

## Mega Drive: the bus layout of the 68000 follows the independent vectors, and the Z80 hash of the report is portable (1.6.8, in development)

The 452 vectors of `tests/fixtures/m68k-groups` that still differed from the Mega Drive after 1.6.7 (the total of clocks was right, the
layout of the bus transactions was not, [CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166)) are corrected: **2,873 of 2,895
vectors now agree on every check, on the native steps and on the reference path; the 22 left are `ABCD`, `SBCD` and `NBCD` on operands that
are not decimal digits, which the manual leaves undefined.** The causes, by instruction:

| Cause | Vectors | Where it is corrected |
|---|---|---|
| a long read-modify-write to memory (`ADD`, `SUB`, `AND`, `OR`, `EOR`, `NEG`, `NEGX`, `NOT`, `CLR`) writes its low word first | 111 | `retrorecomp/megadrive_bus_rules.py` (the executor's `mem_write`) |
| `ADDX.L`, `SUBX.L` on two predecrement operands: each long is read from its low word; the result is written low word, next prefetch, high word | 13 | the same module (`mem_write_split`) and `rr_md_prefetch_hold`/`release` in `native/md_prefetch.inc` |
| the two internal clocks of the predecrement forms of `ABCD`, `SBCD`, `ADDX`, `SUBX` come before the first read | 98 (the 13 above included) | `native/md_prefetch.inc` (live preparation) and `megadrive_codegen.prefetch_plan` (static plan) |
| a byte or word immediate (or a bit number) with a memory destination: the internal clocks come after the word that follows the immediate | 17 | the same two places, plan flag `RR_PF_IDLE_AFTER_FIRST` |
| `ANDI`, `ORI`, `EORI`, `MOVE` to the condition code register read the second word of the queue again after 8 (4 for `MOVE`) internal clocks, then prefetch as usual | 147 | `rr_pf_finish` |
| `LINK` and `MOVEP` fetch their last word after their writes, not before | 79 | `RR_PF_BEFORE_WRITE` is off for them, in the live preparation and in the plan |

**Not proved:** the long immediate forms with a memory destination that needs an address calculation (`ADDI.L`, `SUBI.L`, `ANDI.L`, `ORI.L`, `EORI.L` and `CMPI.B`, `.W`, `.L` on `-(An)` or `(d8,An,Xn)`) have no vector in the
fixture; their layout stays the pinned model's. The corrections change where the transactions of an instruction fall, not the total of its
clocks, so a frame-timed effect can still shift by the clocks between two accesses (VDP, Z80 and I/O ports see the order and the instant of
each access).

**Z80 hash of the report.** `z80_cpu_hash` (the Mega Drive's report and trace field) hashed the bytes of the Z80 structure: that structure holds a
`unsigned long` (32 bits on Windows, 64 on Linux), bit fields and padding, so the same Z80 gave a different value on the two systems. It is now
taken field by field (`z80_state_hash`, `native/md_backend.c`: registers, flags, interrupt state and the low 32 bits of the cycle count). What reads
it: `retrorecomp/console16.py` (`MD_AUDIO_FIELDS`: copied into each route's `final_checks` row and compared between the native run and the
reference run of the same conversion) and `tools/state_checks.py` (`GUEST_FIELDS`: compared between a run and the run resumed from a quick state).
Both compare two values taken by the same executable, so they are unaffected; no golden, no shared path and no knowledge record holds it. **A report of
1.6.7 and a report of 1.6.8 are no longer comparable on this one field (on Windows too: the value of the same state is different), and the
tool that compares reports across systems (`tools/megadrive_cross_os.py`) must be given two reports of 1.6.8 or later.** Elsewhere: the Neo Geo and
the CPS-1 do not use this structure for their hash (`rr_ng_z80_state_hash` and `cps1_cpu_hash` read registers one at a time; the CPS-1 writes
its Z80 field by field in its states); the engine's machine snapshot, which the Mega Drive quick states use, still writes the Z80 structure as it is,
and is not changed (a state is not claimed portable between systems; changing its layout would need a compat key).

**What moves.** The Mega Drive game stamp (the generated steps and the runtime change). `native/md_prefetch.inc` and `megadrive_codegen.py` are
inputs of the X68000 stamp (`native/md_prefetch.inc`) and of the X68000 and CPS-1 stamps (`megadrive_codegen.py`, `shares:megadrive_codegen`): their
**game stamps move too, with no change of behaviour**: they take only the arithmetic part of `md_prefetch.inc` and apply none of the Mega Drive's rules; the replays of the vectors give the same figures as before (X68000: 2,873 native and
2,889 Musashi of 2,895 on `m68k-groups`, 2,171 of 2,171 on `md-prefetch`; CPS-1: the same, 864 of 864 on `md-exceptions`, 834 of 834 on
`m68k-shifts`). The Neo Geo stamp **does not move**: the new rules are in a module of their own, `megadrive_bus_rules.py`, because
`megadrive_rules.py` is an input of the Neo Geo stamp (it reads the state rules) and is left as it was. Host and build stamps of every console:
unchanged (checked on the stamp baseline, `tools/std_baseline.py`, before and after). **The quick-state key of the Mega Drive moves**: `RR16_STATE_ABI` hashes the native files the console owns
(`console16_state.write_config` through `compilation_inputs.state_native_files`), and `md_backend.c`, `md_prefetch.inc`, `md_native_steps.h` and
`md_prefetch.h` changed (digest `366b24f1…` on `main`, `5bf4260b…` here). The Mega Drive quick states written by a 1.6.7 game are therefore
**refused cleanly by a 1.6.8 game** (the N-1 rule of this page: no compat key, no crash, no overwrite); cartridge saves are not affected. The state
layout itself is not touched. The keys of the Neo Geo, the CPS-1 and the Super Nintendo do not move (same digests; the X68000 does not read that
digest). **CPS-1 path identities:** `retrorecomp/cps1_knowledge.py` lists `native/md_prefetch.inc` in its `NATIVE_INPUTS`, so the identities of the
`cps1-m68k` and `cps1-z80` paths move with this change; the behaviour is unchanged (the CPS-1 and the Neo Geo cut only the multiply and divide part
out of that file, which this change does not touch), and whether to raise `GENERATOR_REVISION` is the CPS-1 specialist's call. New files and their roles: `retrorecomp/megadrive_bus_rules.py` (game, owner Mega Drive), the new tools
`tools/megadrive_mame_compare.py` and `tools/megadrive_cross_os.py` (no stamp), all in `PUBLIC_FILES`.

**Cost.** On the hot path of the translated steps, small and **not measured**: the long read-modify-write sets and clears one flag around its write
and takes one branch in `mem_write`; the preparation of an instruction tests one more plan flag; the end of every instruction with a pending
prefetch switches on four mnemonics (`rr_pf_refetch_idle`). The lead measures the cost per frame at the release, on a quiet PC.

**Checked.**

- *Vectors:* `megadrive_groups_selftest` 2,873 of 2,895 (the 22 listed, same on both paths); `megadrive_prefetch_selftest` 2,171 of 2,171 (with the 82
  authored cases), on `m68k-shifts` 834 of 834; `megadrive_prefetch_plan_selftest` (live preparation against static plan) passed;
  `megadrive_exception_selftest` 864 of 864; `megadrive_cycles_selftest`, `megadrive_native_selftest`, `megadrive_timing_selftest` passed.
- *Campaign of 11 games* (the 1.6.7 list, `batch --system md`, one conversion at a time, quick check from the base), compared with the 1.6.7 tree:
  all `supported`; the hashes of the last frame, of the sequence of frames and of the CPU/prefetch state are **identical on 21 of 22 routes**.
  The exception is the play route of Shinobi III (PAL): the two runs equal each other up to frame 1,096, then at the end of frame 1,097 the 68000 of the new
  tree stands five instructions further (PC `$1924` against `$1912`, Z flag different), the picture hash of that frame is still equal, and the sound and
  the later pictures differ. Both addresses are in the same straight-line routine of the ROM (it reads script bytes with `(A5)+` and writes the fields of
  an object), so neither run is polling anything there. The cause was traced with every 68000 bus access and every instruction retirement of frame 1,097
  logged on both trees (kept builds with a log added in their private copy of the glue, rebuilt and run with `--frames 1200 --play`; nothing of it is in the
  repository): (1) the 68000 and the Z80 meet at the scheduler's rendezvous, a budget of a few clocks set by the Z80's timeline; the old tree yields at the
  access to `$14D4` at clock 92 and the Z80's last instruction overshoots by 5 clocks, the new tree yields elsewhere (clocks 88, 115, 123, 127), because the
  corrected layout moved the 68000's accesses by a few clocks, so the same instructions fall on the other side of a rendezvous; (2) from the fifth
  instruction of the frame the two timelines differ by 5 to 13 clocks (the new tree earlier by 13 at `$0520`); (3) the vertical-blank interrupt, asserted at the
  same absolute clock, is accepted at the next instruction boundary: the old tree takes it after the instruction at `$0520` (vector read of `$78` at clock
  109,578), the new tree runs the loop `$0512`-`$0522` once more and takes it 5 clocks later, so the frame ends five instructions apart. It is the
  arbitration approximation between the two processors that already made BUSACK dating a limit (the rendezvous is not the hardware's cycle-exact bus
  sharing), not a poll of the VDP, the horizontal-vertical counter or the Z80 bus request. The interpreted counts of this campaign are **not**
  comparable with 1.6.7's: the 1.6.8 tree started with an empty private library, so the quick check had no learned variants of RAM code (OutRun
  171,603 and 126,569 interpreted instructions, Contra play 52,785, Sonic 2's Z80 8,604 and 8,346, Sonic 3 two); OutRun converted again with a
  standard scan and no shared base reaches 0 interpreted in its second pass (2.9 and 3.0 million in the first), as any discovery does.
- *Cross-OS witness (gate G13)*, three games (Sonic The Hedgehog 2, NBA Jam - Tournament Edition, Streets of Rage 2, all USA) converted with the
  same tree on Windows and on a Debian 13 PC, standard scan, no shared base, empty library: the demo and play routes of 3,600 frames of each, **6 of 6
  routes identical** on every field of `final_checks` (picture, frame sequence, CPU/prefetch, VDP, RAM, Z80, YM, counters of native and interpreted
  68000 and Z80 instructions, bus and Z80 timing misses). A first round showed `z80_cpu_hash` different on all six: the cause above. Not covered: the
  other cartridges of the panel, long and authored routes, interactive play on Linux.
- *MAME 0.289, pictures (gate G11):* see [QUALIFICATION.md](QUALIFICATION.md#mega-drive-evidence-behind-its-column-4-november-2026).

## Exports of 1.6.6 in 1.6.7

1.6.7 is the release after 1.6.6 (published on 1 November 2026). This section is the index of its changes: one line per section below, with the stamps
that section says move. Each section computed its stamps for its own change alone (the tree before it and the tree with it), so a line that says "the other
consoles do not move" is about that change, and the table is the place to add them up. The sections of the earlier releases follow, newest first (1.6.6, 1.6.5,
then 1.6.4 and before).

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Master System and Game Gear: the "functions" engine replays the delivered copy and starts from the reset state](#master-system-and-game-gear-the-functions-engine-replays-the-delivered-copy-and-starts-from-the-reset-state-167) | all nine consoles (`retrorecomp.core` carries the reset state) | not stated | not stated |
| [Master System and Game Gear: the acceptance of an interrupt is checked state by state](#master-system-and-game-gear-the-acceptance-of-an-interrupt-is-checked-state-by-state-167) | all nine consoles (`banked_runtime.inc` and `banked_cpu_checks.c` are inputs of every console) | not stated | not stated |
| [Game Boy: HALT steps through mode 3, the guarded helpers are counted, the reference runs over the whole length](#game-boy-halt-steps-through-mode-3-the-guarded-helpers-are-counted-the-reference-runs-over-the-whole-length-167) | Game Boy | none | no key |
| [Game Boy: EI enables IME one instruction later](#game-boy-ei-enables-ime-one-instruction-later-167) | Game Boy | none | no key changes |
| [Game Boy: the unwired bits of the I/O registers read 1](#game-boy-the-unwired-bits-of-the-io-registers-read-1-167-gates-g10-and-g11-specgb-167b) | Game Boy | none | no key |
| [Game Boy: independent SM83 vectors](#game-boy-independent-sm83-vectors-167-gate-g10) | none (developer files only) | none | none |
| [NES: a quick state keeps the mapper's PRG register](#nes-a-quick-state-keeps-the-mappers-prg-register-167) | NES | not stated | **`RR_NES_STATE_ABI` moves**: states of 1.6.5 and 1.6.6 refused |
| [NES: the Zapper catalogue holds no database](#nes-the-zapper-catalogue-holds-no-database-167) | NES | not stated | not stated |
| [Mega Drive: instruction rules found by independent vectors](#mega-drive-instruction-rules-found-by-independent-vectors-167) | Mega Drive (and the X68000 and CPS-1 stamps, with no change of behaviour for them) | not stated | "do not move", for this change alone |
| [Super Nintendo: RAM code that no scan has seen is compiled and counted apart](#super-nintendo-ram-code-that-no-scan-has-seen-is-compiled-and-counted-apart-167) | Super Nintendo | not stated | not stated |
| [Super Nintendo: corrections found by the independent vectors](#super-nintendo-corrections-found-by-the-independent-vectors-167) | Super Nintendo | not stated | not stated |
| [Super Nintendo: the S-DD1 cartridges may be 8 MiB, and Star Ocean converts](#super-nintendo-the-s-dd1-cartridges-may-be-8-mib-and-star-ocean-converts-167) | Super Nintendo | not stated | not stated |
| [Super Nintendo: the delivered file is replayed and its liveness recorded on every conversion](#super-nintendo-the-delivered-file-is-replayed-and-its-liveness-recorded-on-every-conversion-167-gates-g5-and-g8) | Super Nintendo, Mega Drive, Neo Geo and CPS-1 (`console16.py` is shared) | not stated | not stated |
| [Super Nintendo: a save file the game cannot use is set aside, never a reason not to start](#super-nintendo-a-save-file-the-game-cannot-use-is-set-aside-never-a-reason-not-to-start-167) | Super Nintendo | host stamp of every console (`runtime_catalog.inc`) | not stated |
| [Super Nintendo: the ExHiROM board is accepted](#super-nintendo-the-exhirom-board-is-accepted-167) | Super Nintendo | not stated | not stated |
| [Super Nintendo: cartridges whose header checksum was never filled in are accepted](#super-nintendo-cartridges-whose-header-checksum-was-never-filled-in-are-accepted-167) | every console (`cartridge16.py` is hashed by every game stamp) | host stamp of every console (the runtime catalogue) | not stated |
| [Tools that change no export](#tools-that-change-no-export-167) | none | none | none |
| [Neo Geo: the liveness of every route](#neo-geo-the-liveness-of-every-route-167-gate-g8) | Neo Geo | none | no key moves |
| [Neo Geo, CPS-1 and X68000: the corrected Musashi](#neo-geo-cps-1-and-x68000-the-corrected-musashi-167) | Neo Geo, CPS-1, X68000 (CPS-1 generator revision 10 to 11) | none | **Neo Geo key moves**: states of 1.6.6 refused |
| [Neo Geo, CPS-1 and X68000: LINK A7, UNLK A7 and NEGX follow the vectors](#neo-geo-cps-1-and-x68000-link-a7-unlk-a7-and-negx-follow-the-vectors-167) | Neo Geo, CPS-1, X68000 (CPS-1 generator revision 11 to 12; the Mega Drive does not move for this change) | none | not stated |
| [Sharp X68000: the intensity bit of the palette lifts red, green and blue](#sharp-x68000-the-intensity-bit-of-the-palette-lifts-red-green-and-blue-167) | Sharp X68000 | none | **`RR_X68K_STATE_ABI` moves**: states of 1.6.6 refused |
| [Sharp X68000: the libretro comparison base leaves the build files](#sharp-x68000-the-libretro-comparison-base-leaves-the-build-files-167) | Sharp X68000 | none | not stated |
| [Sharp X68000: the report states that no universal zero-fallback claim is made](#sharp-x68000-the-report-states-that-no-universal-zero-fallback-claim-is-made-167-gate-g15) | Sharp X68000 | none | the key does not move for this change |
| [Lead: unpacked fallback of the packed replay](#lead-unpacked-fallback-of-the-packed-replay-167) | Master System, Game Gear, Game Boy, NES, Mega Drive, Neo Geo, X68000, CPS-1 (`delivery_evidence.py`) | build stamp of every console (`packing.py`) | no key moves |
| [Lead: the packed Windows game keeps UPX's call filter](#lead-the-packed-windows-game-keeps-upxs-call-filter-167) | none | build stamp of every console | none |
| [Lead: LZMA packing, a reproducible link, a manifest and one identical retry on Windows](#lead-lzma-packing-a-reproducible-link-a-manifest-and-one-identical-retry-on-windows-167) | every console (`core.py`, `platforms.py`) | **host, build and game stamps of every console** | not stated |
| [Capcom CPS-1.5, the QSound boards (experimental tier)](CPS1.md#cps-15-qsound-boards-experimental-tier) | CPS-1 (new files `cps1_kabuki.py`, `cps1_qsound.c` and others; see the machine page) | not stated | not stated |

Taken together, **the game stamp, the host stamp and the build stamp of every console** move between 1.6.6 and 1.6.7 (the LZMA row alone moves all three of
every console). What the release does with `LEGACY_GAME_STAMPS` is the release procedure's decision (the rule above).

**Quick states.** The key of a console is a hash of its native files (the Mega Drive and the Super Nintendo: every listed file of the console, among them
`runtime_catalog.inc`, which changed; CPS-1: `cps1_machine.c`, `cps1_qsound.c` and `cps1_eeprom.c`, which changed; the Neo Geo, the NES and the X68000 say it in
their rows). So the key moves for **the Mega Drive, the Super Nintendo, the Neo Geo, the CPS-1, the NES and the X68000**, and a quick state written by an export
of 1.6.6 is refused cleanly there (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The Master System,
the Game Gear and the Game Boy have no key of this kind. **Cartridge saves** are kept; a Super Nintendo save file the game cannot use is set aside as
`<name>.unusable-N` (never deleted, never replaced) and the game starts with a blank RAM, as the X68000 already did.

## Master System and Game Gear: the "functions" engine replays the delivered copy and starts from the reset state (1.6.7)

Two changes of the "functions" engine of the two consoles, and a check that needed no change.

1. **The delivered copy is replayed (gate G5).** The compressed copy of the build is now started on every route, as the banked engine
   already did, and refused if it differs. The "functions" engine has no fresh reference for the `play` route (only the demo route is
   compared with the interpreter), so the copy is compared with the final pass of the same build; the report says so
   (`packed_replay`: `engine`, `compared_with`, `matched`, `routes`) and does not claim `packed_reference_match` for it. Its liveness is
   the one the report keeps, as for the banked engine.
2. **The documented reset state.** The pinned runner started the CPU with AF = 0 and SP = $DFF0; the reference CPU and the banked
   engine start with AF = SP = $FFFF, as the chip does after a reset. A program that pushes AF in its first frame, before any flag
   instruction, left a different byte on the stack (found on an authored cartridge: the RAM hash of frame 1 differed from the
   interpreted run, the next frame agreed). The glue now starts at $FFFF with A and F at $FF. Games normally set SP at once; the 15 games
   below all still match the interpreter after the change.
3. **No change: the dispatch of a paged address.** The upstream commit `a92717d` (not taken, the pin stays) guards the dispatch of a
   single compiled variant by the live bank. The converter already carries both of its hunks (1.6.3 for the direct calls, and the
   single-variant guard in `core.patched_generator_source`). `tools/sega_bank_dispatch_check.py` writes a cartridge of its own that pages
   $8000 from RAM, bank 2 for 5,000 frames and bank 5 afterwards (the conversion runs 3,600 frames per route, so it learns bank 2 only),
   converts it with the "functions" engine, checks that the generated dispatch tests the bank, and runs 6,000 frames natively and
   interpreted: the VDP traces are identical and the late bank went through the counted interpreter (1,001 calls, 0.005 percent of the
   cycles). It was run once on this tree; it has not been run against an unguarded dispatch.

What was run: 15 games of the 1.6.4 batch, one conversion at a time from an empty learning state, "functions" engine: 15 of 15 match
the interpreter on the VDP trace and the final RAM, the packed copy matches its build on both routes, and the last pass interprets at most
4.96 percent of the cycles (Aladdin; the others 0.15 percent or less). Order independence: Action Fighter, Aladdin, Super Columns, The Lost Stars,
Sonic Spinball (Game Gear) and Triple Trouble, converted in three different orders (6 x 3 = 18 conversions, each order from an empty
state), give the same number of passes, the same interpreter share per pass, the same dispatch misses and the same pictures in every order.
The learned state of a game is kept per ROM, so no game depends on another; what can differ is the state of the same game, and
converting Aladdin, The Lost Stars and Sonic Spinball (Game Gear) again from the state the first conversion left gives the same result in a
single pass. The packed copy's own digest differs from one conversion to the next (the same build, packed again); it is not compared.

Exports: the game stamp of all nine consoles moves with `core` (the reset state is a patch in `core.py`). The Master System and Game
Gear exports made with the "functions" engine change only by the reset state of the CPU; the banked engine is unaffected. The reset
state costs nothing per instruction.

## Master System and Game Gear: the acceptance of an interrupt is checked state by state (1.6.7)

The 1.6.6 review of the banked engine left a doubt: does an accepted interrupt set WZ to the new PC, and is the right return address
pushed when it falls inside a repeating block instruction? Both were already right (WZ has followed the jump since 0.10.4; the PC
the step leaves is the instruction itself while the block goes on and the next one after its last iteration). What was missing was the
proof. `native/banked_runtime.inc` now has the acceptance in two small functions (`banked_after_step`, `banked_accept_irq`) with the
same statements as before, and `native/banked_cpu_checks.c` (run by `tools/banked_cpu_selftest.py`) runs them against the corrected
reference CPU on 720 states (360 execute the instruction named, 360 are HALT or NOP states: a halted CPU runs a NOP): fifteen instructions (a NOP, `LD A,I`, `LD A,R`, `EI`, `HALT`, `RETI`, and the first, a middle and the
last iteration of `LDIR`, `LDDR`, `CPIR`, `CPDR`, `INIR`, `OTIR`, `INDR`, `OTDR`) by IM 0, 1 and 2, interrupts enabled or not,
a halted CPU or not, two register seeds, two stack positions; 348 of them take the interrupt. Registers, WZ, Q, P, the clock, the stack
bytes and the RAM agree on all of them, and after a NOP the documented values (13 clocks, 19 in IM 2, return address pushed low byte
first, two refresh increments, IFF1 and IFF2 cleared, WZ the new PC) are asserted on their own, not through the reference. A deliberate
fault in the function (WZ one too high) fails the check. What this is not: agreement with the project's reference CPU and the
documentation, not hardware captures, and the reference cannot show an error it shares.

Exports: the behaviour of the generated game is unchanged; only the text of `runtime_glue.c` (the two functions) differs. The game
stamps of all nine consoles move (`banked_runtime.inc` and `banked_cpu_checks.c` are inputs of every console in `stamp_inputs.py`; the
generated game of the other consoles is the same). The interrupt path
is taken once per interrupt, not once per instruction; the per-instruction loop gains no work.

## Game Boy: HALT steps through mode 3, the guarded helpers are counted, the reference runs over the whole length (1.6.7)

*The halted fast-forward.* While a game waits in HALT, the runtime jumps to the next PPU event in every mode but the pixel transfer, where it stepped one machine
cycle at a time because the end of the mode depends on the pixel FIFO: about 43 steps a line, in a loop that issues most of the calls of a game that waits for vertical
blank. The transfer ends when the 160th pixel is pushed, at best one pixel a dot (sprites, the window and the scroll only add dots), so the step may now go to one dot
before that, on a four-cycle boundary (`gameboy_runtime.adapt_halt_mode3`); the dot where the mode ends, and the interrupt it may raise, is still reached by a four-cycle
step, so the CPU wakes on the same cycle. It applies once the mode is published as 3 and with more than four pixels left.

*The guarded helpers are counted (gate G3).* The four kinds of native body that take over a recognised routine of writable code (store and increment, copy, DMA page,
interrupt-bracketed DMA) count their entries and the guest cycles of those entries in host-only counters of the context (outside every saved state). The runtime prints
them on a `[RR-HELPERS]` line, the probe reads it (a runtime without the line is refused) and the report gives them per scenario, by kind, in `guarded_helpers` beside the
one-at-a-time counts, never added to the interpreter figures. On the games of the A/B they are mostly zero; Kirby's Dream Land enters the store helper 11,360 times in its
3,600-frame boot route (90,880 guest cycles).

*The reference comparison (gate G4).* The comparison with the reference interpreter covered 30 frames of the boot and 240 of each route, and never the pseudo-random
routes. From the extended level on, every scenario of the probes, the pseudo-random routes included, is compared over its whole length, up to 3,600 frames; the report
says, for each comparison, the frames compared (`frames`) and the length of the scenario (`scenario_frames`), and `native_validation.mode` is `full`. The packed replay uses
the same lengths. The lockstep run goes at roughly seventeen frames a second on a busy PC (73 s for 1,200 frames of one route), which is why the default and the lower
levels are unchanged.

*What moves.* The Game Boy **game stamp** (`gameboy.py`, `gameboy_coverage.py`, `gameboy_runtime.py`, `native/gb_ram_helpers.h`, `native/gb_tick_fast.h`, `native/gb_tick_checks.c` and
`native/gb_ram_checks.c`), once for this whole lot with the EI change above; against the base of the lot every other stamp of every machine is the same. An export of 1.6.6
plays as before until it is converted again; its report has no `guarded_helpers` and no `scenario_frames`, which read as absent, never as zero.

*Hot path: touched, not timed.* `gb_halt_fast_forward_cycles` runs once per halted step and gains one comparison in mode 3; the steps there become longer (in the test fixture the
average step inside mode 3 is 106 dots instead of 4, about 26 times fewer steps). The counting of the guarded helpers costs one increment and one addition of 64 bits per helper entry and one read of `total_cycles` per dispatch of code run from WRAM or HRAM
(`rr_gb_try_store_helper`, taken or not). The gain on a real game is not measured here: it is to be timed on a quiet PC.

*Proof.* `tools/gameboy_halt_selftest.py` builds the runtime with and without the bound and runs a HALT program on random video memory, sprites, window and scroll with
four kinds of wake-up source in 48 variants: the digest of the whole state is identical after each of 66,843 slices of random length, the sound samples agree at all 288
frame ends, the build with the bound takes 66,187 long steps inside mode 3 and the other none, and a bound that runs 20 dots too far is caught (43,419 slices differ). A/B
on five games (Tetris, Super Mario Land, Kirby's Dream Land, Link's Awakening, Wario Land II; old tree before the lot's HALT change, new tree after it, from an empty library):
on the four routes of each, 3,600 frames, the picture, the sound, the work RAM and the program counter of every frame are identical, and so is the final state;
the lockstep comparison takes the same number of steps. The RAM self-test (56,170 checks) asserts the counter of each helper kind; `tests/test_gameboy_helper_counts.py`,
`tests/test_gameboy_halt_bound.py` and the coverage tests cover the rest. Fable reviews the HALT change and the EI change before they are merged.

*A clean start for every probe.* The probes of a conversion ran one after the other in the folder of the build, and a cartridge with battery RAM writes its save beside the
executable when it ends, so the second probe of such a game started from the save of the first (seen in the 12-game campaign: the `varied` route of Link's Awakening, run
twice in the same folder, shows 179 pictures the first time and 184 the second; the 212 its probe reported has other causes that were not isolated). `_probe` (`gameboy.py`) now empties the `datas` folder of the build before each probe, as the state
check already does for the delivered file. What moves: the Game Boy **game stamp** only (`gameboy.py` is an input), nothing in the exported game or the generated files; the
probe figures of a battery cartridge (pictures and counters of the second and later probes in `conversion-report.json`) can differ slightly from an earlier conversion of the same
game, for the better: they now describe a start from nothing.

## Game Boy: EI enables IME one instruction later (1.6.7)

On the console IME is set after the instruction that follows `EI` (Pan Docs, "Interrupts"; `EI` then `DI` lets no interrupt in between). The pinned runtime
stored `ime_pending = 1` for `EI` and turned it into IME at the end of the same tick, in the interpreter, the generated code, the upstream stub and our RAM
executors. The independent SM83 vectors (865 of them) saw it: IME was already set after `EI`. In ordinary flow the interrupt still came after the next
instruction, by accident, because the interrupt test inside `gb_tick` ran before the pending flag was promoted. The change makes the flag a real delay, the same rule
everywhere (`gameboy_runtime.adapt_ei_delay`, `native/gb_tick_fast.h`, `native/gb_ram_helpers.h`): 0, 1 (`EI` just ran), 2, then IME; the first thing every tick does is
advance it, so the interrupt test that follows sees IME in the first tick of the instruction after `EI`. `DI` clears the flag, and an `EI` that finds it armed leaves it
(`EI`, `EI`: IME is on after the second).

*Two cases the review of the change found, both fixed in `adapt_ei_delay`.* (1) `EI ; HALT` with an interrupt already pending and IME off before the `EI`: the pinned
`gbrt_execute_halt` saw IME off and took the HALT bug, then the tick of the HALT turned IME on and the dispatch ran with the bug still set, so the first instruction of the
handler ran twice (a handler that begins with `PUSH AF` unbalances the stack). An armed `EI` (flag 2) now counts as IME about to be on: no HALT bug, the interrupt is taken once
after the HALT, as in 1.6.6 and on the console. (2) `EI` executed with IME already on and an interrupt pending at once: the dispatch switched IME off and the armed flag
switched it back on in the middle of the dispatch (a nested interrupt in the handler); the dispatch now clears the flag with IME (the `EI` does nothing there, as on the console).
Both are asserted in `native/gb_halt_checks.c` (removing either fix makes it fail: the stack comes back unbalanced, or IME stays on) and the `EI ; HALT` case is also in
`tools/gameboy_ei_check.py` on the delivered file.

*What moves.* The Game Boy **game stamp** (`gameboy_runtime.py`, `gb_tick_fast.h`, `gb_ram_helpers.h`); no host or build stamp. An export of 1.6.6 keeps the old rule until it
is converted again. The pending flag is part of a quick state: a state taken between an `EI` and the next instruction by this build holds 2, which an older build
also promotes at its next tick, so no key changes.

*Hot path: touched, not timed.* `gb_tick` and its inline copy test `ime_pending` once per tick as before; the test moved from the end of the function to the start, and the
value it handles has a third state. No other work is added per tick.

*What it changes in practice.* In the game, on five games, nothing: on Tetris, Super Mario Land, Kirby's Dream Land, Link's Awakening and Wario Land II (one conversion at a
time from an empty library, old and new tree), the four routes of each (boot, two plays, varied) were replayed on both delivered files for 3,600 frames and the picture,
the sound, the work RAM and the program counter of every frame are identical, and so is the final state dump. In the lockstep comparison of the conversion, which
runs one instruction at a time, Super Mario Land takes five more steps in the 30-frame boot comparison and in each 240-frame comparison (Tetris, Kirby's Dream Land and
Link's Awakening: the same number); on the old tree its one-step loop took one interrupt right after an `EI` (the `EI` at `$042C`, interrupt taken at `$042D`, cycle
938,248, found with a print in the dispatch) where a normal run took none. Both trees match their own interpreter; the new one takes that interrupt after the next instruction in
both modes. The five extra steps are not explained further than by that single difference, and no picture, sound, RAM or PC difference goes with them.

*Proof.* `tools/gameboy_sm83_vector_selftest.py`: the interpreter matches 402,589 of 404,358 vectors (the 865 `EI` vectors now match; what is left is `STOP` and `HALT`, conventions of
the vector model), the RAM executor all 51,654 and the RAM dispatch all 58,153. `tools/gameboy_ei_check.py`, a cartridge authored for it with an interrupt already pending at the
`EI`: nine cases (ROM code, code copied to WRAM and HRAM, an `EI` at the end of a block, `EI ; DI`, `EI ; EI`, `EI ; HALT`) give the console's answers on the new runtime (the first
eight were also measured on the 1.6.6 runtime, which gave the same), and the generated code agrees with the interpreter in lockstep. The inline tick against the real `gb_tick`
(309,676 checks, with the pending flag drawn from 0, 1 and 2), the RAM self-test (56,170) and the bank-boundary self-test (47,104) pass; the vector counts above were run again
after the two corrections. `tests/test_gameboy_ei_delay.py` covers the patch functions. A/B of the corrected tree against the 1.6.6 tree (`f9d2350`) on Tetris, Link's Awakening and Wario Land II (the
last two have an `EI ; HALT` byte pair in their ROM; Tetris waits in HALT): on the four routes of each, 3,600 frames, the picture, the sound, the work RAM and the program counter
of every frame are identical to 1.6.6, and so are the final state and the number of steps of the lockstep comparison. Fable has reviewed the change; both findings are fixed here.

## Game Boy: the unwired bits of the I/O registers read 1 (1.6.7, gates G10 and G11, spec/gb-167b)

The pinned runtime answers a read of the registers it does not model with the value stored by the last write, so a bit that is not wired on the console reads back
as it was written. On the original Game Boy such a bit reads 1: bits 6 to 1 of the serial control ($FF02), bits 7 to 3 of the timer control ($FF07), the unmapped
$FF03 and $FF08-$FF0E, and, outside colour mode, the registers of the colour models ($FF4C, $FF4E, $FF50, $FF57-$FF67, $FF6D-$FF6F, $FF71, $FF78-$FF7F, and the palette ports $FF68-$FF6B).
The engine already reads $FF by itself outside colour mode at $FF4D, $FF4F, $FF51-$FF56, $FF6C, $FF70 and $FF72-$FF77.
Mooneye's `unused_hwio-GS` found it (it wrote 0 to $FF07 and read 0, expecting the five high bits at 1). `gameboy_runtime.adapt_unused_io_bits` has two `replace_once` anchors in
`gbrt_read8_impl`: the last fall-through of the register read, which ORs the masks and returns $FF for the unmapped addresses, and the branch of the palette ports $FF68-$FF6B,
which now returns $FF outside colour mode before `gb_sync`; the joypad, DIV, IF, the LCD and the sound registers keep their own paths. A moved upstream marker refuses the conversion. `tests/test_gameboy_unused_io.py` covers the patch; the behaviour is proved by
the test ROM (see [GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)).

*What moves.* The Game Boy **game stamp** only (`gameboy_runtime.py` is an input of the Game Boy game role and of no other machine's); no host or build stamp. An export of 1.6.6
or of an earlier 1.6.7 build keeps the old reads until it is converted again. Nothing is saved or restored differently: the stored register value is unchanged, only its read.

*Hot path: touched on a rare path.* Only reads of $FF01-$FF03, $FF07-$FF0E, $FF4C, $FF4E, $FF50, $FF57-$FF67 and $FF6D and above reach the final lines, and $FF68-$FF6B the palette branch; the
joypad, DIV, IF, LCD, sound and HDMA reads return before them. No timing was taken.

*What it changes in practice.* In the game, on three games, nothing: on Tetris, Super Mario Land and Exodus (one conversion at a time from an empty library at the quick level, tree
before and after) the four routes of each (boot, two plays, one pseudo-random route of 18,000 frames, 23,400 frames a game) give identical pictures, sound, work RAM and program counter on
every frame, and the final state of Tetris is identical. The conversion's lockstep against the interpreter passes on the three. A game that reads the unwired bits of $FF02 or $FF07 and
stores them would now store 1s, as on the console; none of the three does.

*Proof.* `tools/gameboy_testroms.py` on the converted Mooneye test: `bits/unused_hwio-GS` failed at $FF07 on the main tree, then at $FF68 with the first version of the patch, and passes
with the palette ports. `boot_hwio-dmgABCmgb` now goes past $FF03 and stops at $FF26 (the sound state after the boot ROM), which is not changed here.

## Game Boy: independent SM83 vectors (1.6.7, gate G10)

`tools/fetch_sm83_vectors.py` caches the pinned SingleStepTests/sm83 corpus into `.deps` (revision `f9c3021`, MIT, a pinned digest of its
500 files, a line per vector); `tools/gameboy_sm83_vector_selftest.py` builds `native/gb_sm83_vector_checks.c` against the pinned runtime and
runs the 404,358 vectors that touch plain memory through the interpreter, the one-instruction RAM executor and the RAM dispatch.

*What moves.* Nothing: developer files, in the public files and in no stamp (the C check is declared out of the stamps like the
CPS-1 vector checks). No export changes.

*Hot path: not touched.*

*Proof and finding.* 401,724 of 404,358 interpreter vectors matched at the time; the three families that differed were pinned with their numbers
(`STOP` and `HALT`: conventions of the vector model; `EI`: IME set when `EI` completes instead of one instruction later, see the next entry for the
fix and for what it changed in practice). Details in [CPU_SM83.md](CPU_SM83.md#6-tests-and-vectors).

## NES: a quick state keeps the mapper's PRG register (1.6.7)

*The NES game stamp moves (`nes_state_layout.py` is one of its inputs) and the state key `RR_NES_STATE_ABI` changes: the quick states of
1.6.5 and 1.6.6 are refused with the usual message and a state is taken again with F8. **The exports of 1.6.5 and 1.6.6 already
published have this defect on the boards below; converting the game again with 1.6.7 corrects it.***

The 1.6.5 state writer (`RRNESST2`) left out the cartridge's `m.prg` register. Its list of members not to save named the cartridge's
`prg` pointer by its last name, and that name also belongs to the register in which MMC1, MMC2 and MMC4, the VRC boards, VRC6, Bandai,
Sunsoft and a few others keep their PRG bank. After F9 the register came back as 0 until the game wrote it again, so a game that reads
its data through the switchable window and does not write the bank register at once ran on bank 0 after the load. The list now names a
member by its path: the pointer stays out, the register is in, and the generated writer changes by that one field and nothing else. The
generator also offers an audit of every member of every saved structure (written, or left out for a declared reason), and a test
requires that the members left out are exactly the ones in the list, each named by its path, so that a name shared by two members can
no longer drop one in silence.

What was seen. On Esper Dream 2 (VRC6, a real game), the check that every conversion runs on the delivered file (save at frame 599 of a
play route, load in a fresh process, compare 180 frames) refused the game with the 1.6.6 source and on `main`: the hardware hash (`hw=`)
differed on every frame after the load while the CPU, memory, picture and sound hashes stayed equal, and `--state-out` showed
`cart.prg` 02 before and 00 after; with the change the same conversion passes. On four authored cartridges
(`tools/nes_state_prg_check.py`: MMC1, VRC6, Bandai and MMC2, a program that selects bank 3 once and never writes the register again)
the conversion is refused with the 1.6.6 source and the check passes at two save points with 1.6.7. On two real MMC1 games (Metroid,
Mega Man 2) F9 was already identical at three save points with the old writer: they write their bank register again within the
first frame, so how much a played game suffered is not measured; it depends on how soon the game writes the register again.

Why Esper Dream 2 passed the 1.6.6 campaign is not proven. The probable cause: the state check (commit `0ff2b27`) entered the tree on
1 November 2026 at 14:25, while the 1.6.6 campaign ran for 1 h 44 min and its proof commit is at 15:33, so the campaign probably began
before the check existed or while it was being written, in the same checkout, and Esper was converted without it. The same 1.6.6 source
with the same options refuses the game today, and no non-determinism was found in the check. The reports of the 1.6.6 campaign were
not read again: their folder (`.build/campaign-1.6.6`) no longer exists.

## NES: the Zapper catalogue holds no database (1.6.7)

*The NES game stamp moves (`nes_catalog.py` is one of its inputs); exports are rebuilt from their learned paths. Which game gets
the Zapper does not change for any game of the maintainer's library.* The catalogue that decides whether a cartridge uses the
Zapper carried 122 payload CRCs taken from MesenNesDB, a file of the GPL-3 Mesen2 repository (the same source as the known-dump
table of the pinned engine's later revisions, which Retro-Recomp does not take). They are removed. A cartridge now uses the Zapper
when its NES 2.0 header names it (default expansion device 8) or when its file name is the exact title of a game known to
support it: the nine licensed games that need it, the licensed and unlicensed ones that support it as an option (as the
compatible-games list of the Wikipedia article on the NES Zapper names them; facts only), and the aliases already carried.

Checked on the 1,063 files of the maintainer's NES library, before and after: the same 19 games, none lost, none gained (the two
that only the CRC table recognised, The Lone Ranger and Day Dreamin' Davey, are now named by title). What changes is outside
that library: a revision, hack or translation of these games whose file name is not one of the titles and whose header does not
name the Zapper is no longer recognised, and its game runs with the two controllers. The Hunt for Red October is on the
Wikipedia list but is not taken, since no other source says the NES game uses the gun.

## Mega Drive: instruction rules found by independent vectors (1.6.7)

The vectors of `tests/fixtures/m68k-groups` ([CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166)) showed 83 total-clock and
51 final-state differences between the pinned 68000 interpreter and the oracle. The Mega Drive now corrects the ones the Motorola manual
defines, in `retrorecomp/megadrive_rules.py` (strict replacements of pinned lines, applied to the steps' text and to the reference path):
`RTR` loads the five condition code bits only; `NEGX` keeps Z on a zero result; the long `ADD`, `SUB`, `AND`, `OR`, `EOR`, `ADDA` and `SUBA` with a register or immediate source take two
clocks more; `CMPA.W` takes two fewer; `BCHG`, `BCLR` and `BSET` by bit number take two fewer below bit 16; `Scc Dn` takes 4 clocks when
false; `BTST Dn,#imm` takes two more. Two more rules follow the vectors alone, not the manual (read to the letter, the manual gives the
old behaviour): `LINK A7` pushes the value A7 had before the decrement and `UNLK A7` ends with the long it popped. Of the 2,895 vectors 2,421 now agree (2,315 before); the 474 left are decimal arithmetic on
non-decimal digits (22, undefined in the manual) and the layout of bus transactions (452, not corrected). `megadrive_cycles_selftest`
changed one authored expectation: `BCLR D0,D0` with D0 = 0 is 8 clocks, not 10 (the vectors give 8 below bit 16, 10 from bit 16).

**What moves.** The Mega Drive game stamp: the steps' clocks and a few results change, so a game that runs one of these instructions
takes slightly different times (a long `ADD.L D0,D1` is 8 clocks, not 6), and frame-timed effects can shift by those clocks; existing exports
are rebuilt on the next conversion. Quick-state keys do not move. `retrorecomp/megadrive_codegen.py` is an input of the Mega Drive, X68000
and CPS-1 stamps (`shares:megadrive_codegen`), so those two stamps move as well, **without any change of behaviour for them**: the four
call lines added there pass the rules for the Mega Drive generator only, and the Mega Drive decoder tool now builds in a folder of its own
(`.build/megadrive-step-decoder-rules`) so that the Neo Geo, CPS-1 and X68000 keep the decoder they had. This is guaranteed by
`tests/test_megadrive_rules.py` (`DecoderToolIsolationTests`: the default decoder writes the very text of 1.6.6; no other machine asks for
the rules), and the CPS-1 vector replay gives the same figures on the branch as on 1.6.6 (2,169 of 2,171 native, 2,091 reference on
`md-prefetch`; 864 and 858 on `md-exceptions`; 834 on `m68k-shifts`). The Neo Geo stamp does not move.

**Cost.** A small one on the hot path of the translated steps. The static clocks are constants and cost nothing, but the three
data-dependent rules are inserted in the translated bodies: every `Scc Dn` and every `BCHG`, `BCLR` or `BSET` by bit number that runs
adds one branch, and a call to `rr_md_arithmetic_phase` when the branch is taken (the hook `MULU` and the register shifts already use).
It is low when the prefetch model is off. The cost per frame is **not measured yet**: it is measured at the release, on a quiet PC.

**Checked (A/B, `tools/ab_conversion.py`, 1.6.6 against this tree, standard scan).** Blockout, Sonic The Hedgehog and Gunstar Heroes
(USA) convert on both sides with status `supported`, zero interpreted 68000 and Z80 instructions on both routes, native equal to the
fresh reference on every route and the compressed copy equal to the reference. As expected the generated steps, the clocks and the
hashes of the picture, the sound and the Z80 differ (the report counts, such as the native entries, move by well under 1 percent), and
the number of distinct pictures of a route stays within 1 percent (Blockout demo 1,592 against 1,591, play 483 against 486; Sonic 2,501 and
2,669 against 2,500 and 2,670; Gunstar 2,046 and 414 against 2,052 and 415). This shows that the corrected clocks keep the conversions
valid; it does not show that any frame-timed effect looks the same, which a play test of the games named in the campaign would.

**Checked (campaign of 11 games, one conversion at a time, `batch --system md`).** Sonic The Hedgehog 2 and 3, Streets of Rage 2, Road
Rash 3, Contra - Hard Corps, Ecco - The Tides of Time, Earthworm Jim 2, Super Street Fighter II, NBA Jam - Tournament Edition, OutRun and
Shinobi III (all USA), chosen for raster effects, split screens, Z80 drivers, banked and EEPROM cartridges, all convert with status
`supported`, zero interpreted 68000 and Z80 instructions on both routes, native equal to the fresh reference and the compressed copy
equal to the reference. The paths of these games are qualified in the base, so the conversion is the 1,200-frame quick check from them,
not a new discovery; a first series that overlapped another by mistake showed interpreted counts for OutRun and Sonic 2 that the clean
series did not reproduce, and is not used. No game was dropped and none needs a line in `KNOWN_FAILURES`.

## Super Nintendo: RAM code that no scan has seen is compiled and counted apart (1.6.7)

A Super Nintendo game whose code lives in RAM (the game logic of Secret of Mana, most sound drivers, Chrono Trigger, Super
Turrican) was native only at the addresses and opcodes a scan had seen executing; anywhere else the instruction went to the
counted interpreter. Since 1.6.7 it runs through the compiled body of the opcode it has when it is fetched (the same bodies,
the same cycle table, operands read live on the timed bus), for the 65816 in WRAM and in the cartridge's RAM and for the
SPC700 in the sound unit's RAM outside `$F0-$FF`. Fetches from device registers, changed ROM bytes and device instructions
stay interpreted and counted.

- **A third counter, `compiled_unobserved`.** Per CPU, native + compiled and not observed + interpreted = the instructions
  retired. `native_entries` and `audio_native_opcodes` keep their flat meaning (every compiled body); the new figures, part of
  them, are `compiled_unobserved_opcodes` and `audio_compiled_unobserved_opcodes` (and `_cycles`) in the scenario rows, and the
  report's per-CPU view subtracts them to give the native count. The fallback is never folded into it. In the common report
  (`retrorecomp/report_schema.py`, schema 2, no version change: an added optional key) each scenario of a CPU that counts
  it carries `compiled_unobserved` (and the audio `cycles` too), and the summary of the batch and the window adds
  `compiled_unobserved_opcodes` and `audio_compiled_unobserved_opcodes`. A writer that does not count it has no such key,
  and its native figure is read as before.
- **Both learning passes stay**, and the observation goes on: an unobserved instruction is recorded as an interpreted one
  was, so the second pass moves it from the new counter to the native one. The pass no longer changes what runs fast or
  correctly.
- **The SNES game stamp moves** (the generated map and the two runtimes changed): an export made before 1.6.7 is rebuilt on its
  next conversion, and a game converted before keeps running as it did.
- **Proof.** The authored fixtures run every 65816 operation in 32 register modes from WRAM and from the cartridge's RAM at a
  position no table holds, and every SPC700 operation in 256 register states, against the internal reference (65,890 and
  131,396 comparisons); five games converted from an empty library with the 1.6.6 tree and with this one give the same
  picture, sound, CPU, RAM, video-memory and sound-unit hashes as each other and as the fully interpreted reference (see
  [SNES.md](SNES.md)). Nothing here measures speed, and nothing is claimed about hardware fidelity: the bodies are the
  interpreter's own.

*Hot path: touched.* An instruction fetched from RAM at a position the observed table does not hold used to go through the
interpreter's dispatch; it now calls the compiled body of its opcode directly (the 65816 `rr_sn_unobserved`, the SPC700
`rr_spc_unobserved`, one function pointer indexed by the opcode), and the observation that follows is the same as before. The path of
observed code and of ROM code is unchanged. The frame cost was not measured for this release (the figures wait for a quiet machine and
the per-release comparison); the change replaces interpreted instructions by compiled ones where it applies.

## Super Nintendo: corrections found by the independent vectors (1.6.7)

The SingleStepTests vectors ([CPU_65816_SPC700.md](CPU_65816_SPC700.md)) found five defects of the pinned cores, corrected as patches
of the pinned bodies applied by the converter (each fail-closed on the pinned text): in emulation mode the 65816 `RTI` takes one cycle
less and pulls no program bank, `TCS` and `TXS` force the stack pointer's high byte to 1, a taken branch that crosses a page takes one
more cycle, and the direct-page indexed addressing and the `(dp,X)` and `(dp),Y` pointers wrap inside the page when the direct page register is
page-aligned (`(dp),Y` is not seen by the vectors: the sample has no case where it differs, and the patch follows the processor manual); the SPC700 `DIV YA,X` follows the hardware formula. A game that runs in emulation mode after its reset vector, as every
cartridge does for a few instructions, is concerned only where it uses these instructions; a game that uses `DIV` gets the hardware
quotient in the overflow cases. **The SNES game stamp moves** (it already moved for the changes above). Three games (Secret of Mana, Super Mario World, Donkey Kong Country 2) converted from an empty library with the tree before and after
give the same picture, sound, CPU, RAM, video-memory and sound-unit hashes on every route (19 hash fields in each of the six probe
files, native, packed copy and reference); what differs is the generated 65816 and SPC700 sources, the compiler's profile data and the
analysis files, and in Secret of Mana the packed size ratio (0.2107 and 0.2108). Street Fighter Alpha 2, against the tree before the
S-DD1 clause as well as these corrections, gives the same hashes. These routes leave emulation mode within the first instructions after
the reset, so no hash moving is what was expected; it says nothing about a game that stays in emulation mode. Not corrected (the list is what the sample found and what was read, not a complete
inventory of the differences between the cores and the processor): the page-1 wrap of the stack accesses of the instructions the 65816
added to the 65C02 set (`PER`, `RTL`, `PHD`, `PLD`, `PEA`, `JSL`, `JSR (a,x)`: a push or pull at the edge of page 1 goes on into the next page
instead of coming back to the start of page 1), `EI`/`DI` timing and the halt timings, listed in [CPU_65816_SPC700.md](CPU_65816_SPC700.md).
Also not corrected: `interp816_doInterrupt` (the interrupt entry the SA-1 core uses) still stacks the program bank and takes the native
vectors in emulation mode, so an SA-1 interrupt taken in emulation mode would push four bytes while the corrected `RTI` pulls three; no
known game does it (the main CPU enters its interrupts through `rr_snes_cpu_interrupt`, which is consistent with the corrected `RTI`), and
the vectors have no interrupt case to cover a change, so it is left as the pinned text.
*Hot path: touched, marginally.* The patched bodies of `RTI`, `TCS`, `TXS`, the page-crossing branch and the indexed direct-page
addressing add one test of the emulation flag each; the SPC700 `DIV` adds a comparison; the rest of the bodies is unchanged. Not timed.

## Super Nintendo: the S-DD1 cartridges may be 8 MiB, and Star Ocean converts (1.6.7)

The cartridge RAM decoding served banks $F0-$FF (addresses $0000-$7FFF) as battery RAM on an S-DD1 board, where those banks are the
ROM windows of the chip; a game reading its compressed data there got save RAM. The S-DD1 board now has its own clause: its RAM is in
banks $70-$73 only (`native/snes_cart.h`, `snes_cart.ram_offset`). The S-DD1 boards are accepted up to 8 MiB (the other boards stay at
4 MiB). Star Ocean (6 MiB) converts: see [KNOWN_FAILURES.md](KNOWN_FAILURES.md). Street Fighter Alpha 2 converted again from an empty
library with the 1.6.6 tree and with this one gives the same hashes. Hot path: none added (the clause is evaluated for cartridge RAM
accesses only, as before, and no extra comparison is made on `cpu_read8`). The SNES game stamp moves with the other 1.6.7 changes above.

## Super Nintendo: the delivered file is replayed and its liveness recorded on every conversion (1.6.7, gates G5 and G8)

The Super Nintendo conversion compresses a copy of the build as publication does, replays it on every route against the fresh
reference of the same route, and records each route's liveness (`final_checks[].liveness`: frames, distinct pictures, picture
changes, last picture change, distinct sound blocks, and `pcm_nonzero` and `visible_frames` of the route; the audible-frame fields
are None because this host writes no per-frame audible flag). It was the case for the Mega Drive in 1.6.6; before 1.6.7 the Super
Nintendo did it only in a developer tool. `retrorecomp/snes_evidence.py` is the Super Nintendo's part, `console16.convert16` calls it
for `md` and `snes` through `delivery_evidence()` (the Mega Drive path and its log line are unchanged, tested). A conversion whose
`play` route never changes the picture is refused. Report: `native_validation.packed_reference_match`, `packed_candidate_sha256`.
`console16.py` is shared with the Mega Drive, the Neo Geo and the CPS-1: their game stamps move with this text.

## Super Nintendo: a save file the game cannot use is set aside, never a reason not to start (1.6.7)

A damaged `.rrsram`, or one made for another cartridge, was kept in place and the game ran without saving. It now follows the rule of
the X68000: the file is moved to `<name>.unusable-N` (never deleted), the game starts with a blank RAM and saves a new file, and a
short notice ("Save unreadable: set aside", five game languages) is shown once; if the file cannot be moved it is left alone, nothing
is saved that session, and the notice says "saving is off". `native/snes_battery.c`, `rrhk_snes.c`, the runtime catalog (two phrases;
`runtime_catalog.inc` is a host file, so the host stamp of every console moves with it and the exports are rebuilt, not reconverted) and the report key `save_set_aside`. All 99 names `<name>.unusable-1` to `-99` taken: nothing is replaced, the file stays in place and the notice says saving is off. Tested on the nine boards of `tools/snes_saves_check.py`.

## Super Nintendo: the ExHiROM board is accepted (1.6.7)

ExHiROM cartridges (map `$25` or `$35`, no chip, an image above 4 MiB: Dragon Quest III and Tales of Phantasia, 6 MiB) are no longer refused. The
bus picks the half of the ROM by the bank's top bit and the loader reads the header at `$40FFC0` (`snes_cart.adapt_cart`, `adapt_loader`,
fail-closed on the pinned text); HiROM and LoROM images are untouched, and the other boards stay at 4 MiB. **The SNES game stamp moves** (it
already moved for the changes above). *Hot path: touched on the HiROM path.* One comparison of the image size is added to `cart_getRomPtr` on
the HiROM path (the bus read of a ROM byte), not to LoROM; not timed. Proof: the authored cartridge of `tools/snes_exhirom_selftest.py`, and
the two games converted (see [SNES.md](SNES.md)).

## Super Nintendo: cartridges whose header checksum was never filled in are accepted (1.6.7)

A cartridge header with a checksum of `$0000` (the complement `$FFFF`, or also `$0000`: the assembler's default, never filled in) was
refused because it cannot be told from damage by its checksum. It is accepted since 1.6.7 only when everything else about it is
credible: a regular map byte, a declared size no larger than the image, and a reset vector that points at a plausible first
instruction. Over the 1,348 files of the maintainer's library exactly four headers change (Power Drive Europe, Fireteam Rogue, Steven
Seagal Is The Final Option and Wile E Coyote's Revenge, the last three prototypes); each converts, with the compressed copy equal to the
reference. **Which game stamps move.** The rule lives in `retrorecomp/cartridge16.py`, which every console's game stamp hashes (the
Mega Drive, Neo Geo and CPS-1 read nothing different from it, but their stamps move); the shared runtime catalogue is a host file, so the host
stamps of all the consoles move in 1.6.7 (rebuilt, not reconverted), as the notes of the release say. Nothing else about an existing export changes.

## Tools that change no export (1.6.7)

- `tools/snes_saves_check.py` (gate G7): cartridges written for the purpose, one per board, check the save file, its damaged forms,
  the absence of a file without a battery and the quick states ([SNES.md](SNES.md)).
- `tools/snes_exhirom_selftest.py`: an authored ExHiROM cartridge (4 MiB and one bank) reads one marker through each of the four views
  of its two halves ([SNES.md](SNES.md)).
- `tools/fetch_snes_vectors.py` and `tools/snes_cpu_vector_selftest.py` (gate G10): the 65816 and the SPC700 against the independent
  SingleStepTests corpora, pinned and fetched into `.deps`; findings in [CPU_65816_SPC700.md](CPU_65816_SPC700.md); the corrections they led to
  are in their own section above (the tools themselves change no export).

## Neo Geo: the liveness of every route (1.6.7, gate G8)

The packed replays of a Neo Geo conversion run with `--trace` and every `final_checks[]` row gains `liveness` (`frames`, `distinct_pictures`,
`picture_changes`, `last_picture_change_frame`, `audible_frames`, `last_audible_frame`, the CPS-1 keys), read from the per-frame trace through
`delivery_evidence.py` unchanged; a route whose picture never changes stops the conversion. Nothing the game does changes: `tools/ab_conversion.py` on
nam1975 shows the 42 new fields (6 keys on 7 routes) and nothing else (hashes, images, traces and states identical). Details:
[NEOGEO_LOG.md](NEOGEO_LOG.md#liveness-of-every-route-gate-g8--2-november-2026).

**What moves.** The Neo Geo game stamp (`neogeo_conversion` is a converter module of its stamp groups): an export of 1.6.6 is **converted in full
once**, with no table entry, to carry the record. The host stamp does not move (no native file is touched), nor does the quick-state key
(`neogeo_conversion` is not among the modules it hashes), nor any other console.

## Neo Geo, CPS-1 and X68000: the corrected Musashi (1.6.7)

The reference 68000 of these three consoles (Geolith's Musashi) is corrected at conversion time by `retrorecomp/musashi_fixes.py` on six points
where the independent 68000 vectors and the translated steps agree and Musashi did not: the flags of a divide overflow, `DIVS` of `0x80000000` by
-1, the flags and clocks of `CHK`, `F620`-`F627` (line F, not the 68040 `MOVE16`) and, added on 3 November 2026, `LINK A7` (it pushes the stack
pointer as it was before the decrement, as the vectors do; see [the next section](#neo-geo-cps-1-and-x68000-link-a7-unlk-a7-and-negx-follow-the-vectors-167)). Details and figures:
[NEOGEO_LOG.md](NEOGEO_LOG.md#the-corrected-musashi-shared-with-the-cps-1-and-the-x68000--3-november-2026).

**What changes in a game.** Only the interpreter (the fresh reference and the counted fallback), and only when the program reaches one of those
cases; the translated code is untouched. On the games compared with `tools/ab_conversion.py` (NAM-1975, Puzzle De Pon! and 1941) the generated
code, the traces, the pictures, the sound hashes and the states are identical; what differs is `engine/m68k/m68kops.c` (by construction) and the
data that follows from compiling it (the profile data of the optimised build and the size ratio of the compressed copy).

**What moves.** The game stamp of the Neo Geo, the CPS-1 and the X68000 (the new module is in their stamp groups): an export of 1.6.6 of these
consoles is converted in full once, with no table entry; the CPS-1 generator revision goes from 10 to 11 (`cps1_build.py` is a pinned source; no
CPS-1 path was qualified, so no qualification is lost). The Mega Drive and the other consoles do not move. The **Neo Geo quick-state key moves
too**: it hashes the fingerprint of `neogeo_build`, which now calls the correction, so a quick state written by an export of 1.6.6 is refused
cleanly by the 1.6.7 export (no compatibility key from 1.6.5, [GAME_STATES.md](GAME_STATES.md)); the layout of the state is the same.

## Neo Geo, CPS-1 and X68000: LINK A7, UNLK A7 and NEGX follow the vectors (1.6.7)

The 2,895 vectors of `tests/fixtures/m68k-groups` (the fixture that made the Mega Drive correct three instructions in 1.6.7, [above](#mega-drive-instruction-rules-found-by-independent-vectors-167)) were replayed through the
generators of the Neo Geo, the CPS-1 and the X68000: the same 33 native vectors differed on all three, because they translate the same pinned interpreter text.
`LINK A7` (6) pushed the stack pointer after its decrement, on the translated steps and on Musashi; `UNLK A7` (4) ended with the increment of the stack
pointer instead of the long it popped; `NEGX.B` with a zero result (1) cleared Z where it must stay as it was; the other 22 are the decimal instructions on
operands that are not digits, which the manual leaves undefined. The three machines now apply the Mega Drive's rules for those three instructions
(`retrorecomp/m68000_state_rules.py` reads the rule text of `megadrive_rules.py`, so there is one copy; each generator calls it right after `adapt_semantics`), and
`musashi_fixes.py` makes Musashi push `A7` as it was for `LINK A7`. Both halves are needed: a step that followed the vectors while the reference did not
would have made a game that runs `LINK A7` fail its own comparison. After the change the state agrees for 2,873 vectors natively and 2,889 on Musashi (2,862
and 2,883 before), identically on the three machines, and every total of clocks equals the vector's; the 22 decimal vectors are recorded per machine
(one list for the three machines, `tests/fixtures/m68k-groups/deviations-musashi-machines.json`) and each replay checks the list both ways.

**What changes in a game.** Only a program that executes one of those three instructions with the case that was wrong (`LINK A7`, `UNLK A7`, `NEGX.B` with a zero
result): the registers and the stack after it. A/B of 3 November 2026 (before: main `d53091b`; after: this tree; standard scan level, one conversion per process,
private library): 1941 (CPS-1) 172 values of the checks compared, 0 differ; NAM-1975 (Neo Geo) 351, 2 differ, both the path of the build folder; R-Type and Bubble Bobble
(X68000) 252 each, 0 differ; all with 0 interpreted opcodes on every route, the packed copy matching and the states resuming. The traces, pictures, sound hashes and states
are the same: no route of these games ran a case where the corrected instructions give a different result. It shows that nothing else moved; it does not say that a game that does run one now
behaves as the original machine, which the vectors (made with MAME) support and no game here exercised.

**Run-time cost.** None, by reading the rules and the generated shape (not timed): the test of the mnemonic in the shared case is on a key that already holds the opcode word, so the compiler folds it; `NEGX` gains one `!r` test that folds the same way, and `LINK` and `UNLK` with a register other than `A7` gain a local the compiler drops. No timing was taken.

**A stale sentence to correct at the next move of the Mega Drive stamp.** The docstring of `retrorecomp/megadrive_rules.py` still says the rules are "applied by the Mega Drive only"; its three state rules are now also read by the Neo Geo, the CPS-1 and the X68000. The file is not touched here, because any edit moves the Mega Drive game stamp.

**What moves.** The game stamp of the Neo Geo, the CPS-1 and the X68000 (`m68000_state_rules`, declared by the three profiles as the group `m68000_state_rules`, and `megadrive_rules`, listed under the four machines because the Mega Drive cannot join a group without editing its profile, join their inputs; the generators and
`musashi_fixes` changed): they were already moving in 1.6.7 with the corrected Musashi, so players are asked for no further reconversion. The CPS-1 generator
revision goes from 11 to 12 (`cps1_knowledge.py`, with the two modules pinned; no CPS-1 path was qualified, so no qualification is lost). **The Mega Drive does not
move**: `megadrive_rules.py`, `megadrive_codegen.py` and its profile are byte for byte what they were, and its stamp and generated code are unchanged (checked against main). The
other consoles do not move.

## Sharp X68000: the intensity bit of the palette lifts red, green and blue (1.6.7)

A palette entry of the X68000 is `GGGGGRRRRRBBBBBI`: five bits per primary and an intensity bit `I` that adds a half step (one level of the 6-bit
DAC, 4 of 255) to the three primaries together. The pinned base kept its picture in RGB565, which has no spare bit for red and blue, and put `I` in
the low bit of green: a pixel with `I` set came out brighter on green only. Arthur agreed to correct it (2 November 2026).

What changes: the machine now keeps the colour word as the X68000 holds it (`host_draw.c` gives the 2014 palette code the masks of that layout, so the
table it builds is the identity and `Ibit` is bit 0), and widens it when the picture is presented (`native/x68000_machine/colour.h`, new): each primary
is `(five bits << 1 | I)` as a 6-bit level, extended to 8 bits (`v << 2 | v >> 4`). The picture handed to the host is XRGB8888 instead of RGB565; the
host kit and the reference host already read both. After a saved state is loaded, the host redraws the picture through the same conversion
(`rr_x68k_framebuffer` returns the converted frame). The contrast of the system port is still applied by the base on the five-bit primaries, and the
half-tone and translucency blends keep the base's arithmetic, which does not depend on the layout of the bits (`Pal_HalfMask` and `Pal_Ix2` are derived from the masks). No game is treated apart.

What a player sees: no layout, timing, sound or code change; colours move by at most 4 of 255 on a channel, and a pixel with `I` set is now
lighter on red and blue too. In the 256-colour graphic mode with special priority, the base adds `Ibit` as an opacity marker to every non-zero
sprite-priority pixel (`x68k/gvram.c`, lines 1673 and 1812 of the pinned file): that pixel now gains 4 of 255 on red, green and blue instead of green alone. The
marker is a defect that was already in the base, and the only place where the `I` bit is made up instead of read from the palette; it is kept as the base has it. The picture hash of every route changes (it hashes the new pixel format); the CPU, RAM and PCM hashes do not: a
conversion of Bubble Bobble before and after gives equal CPU, RAM and PCM hashes on the three routes, 0 interpreted opcodes, a packed copy that
matches, and states that resume. Against MAME 0.289 on the 12 still pictures of Bubble Bobble that match in shape (2,487,394 pixels, `tools/x68000_mame_compare.py`
method, no input), the share of pixels identical to MAME's goes from 93.55 to 97.03 percent, and the mean error per channel
(0.709, 0.770, 0.713 before) is 0.712 on all three after; the largest remaining difference is 24 of 255 (the screen contrast, applied by MAME after
the raw screen, and rounding; not analysed again here). This compares one game's pictures with another emulator, which is not hardware: it does not
establish exact colours, and sound is not part of it.

Stamps: the files are game inputs of the Sharp X68000 (`libretro_api.c`, `base74/host_draw.c`, `base74/bridge.c`, the new `colour.h`,
`x68000_reference/video_checks.c` and `reference_host.c`), so its **game stamp moves** (a full reconversion of every X68000 game; the 1.6.6 exports
keep their old colours until then; their states are refused by the new build because the state compatibility key `RR_X68K_STATE_ABI` itself changes: it hashes `reference_host.c` and `base74/bridge.c`, which this change edits (`native/x68000_reference/CMakeLists.txt`, compared with `state_store.c`)); host and build stamps and the eight other
consoles do not move (checked against the previous commit). Cost: one table lookup per presented pixel, at most 800 x 600 a frame (about 2 percent of one
core at 768 x 512 and 60 frames a second by count; no timing was taken on a quiet machine: the conversion times of the two Bubble Bobble runs, 194 and 197 seconds,
differ by less than the load of the PC). `tests/test_x68000_colour.py` fixes the conversion without a ROM: the masks and the table of the real palette
code, and all 65,536 words against a model written from the rule, with `I` at 0 and at 1.

## Sharp X68000: the libretro comparison base leaves the build files (1.6.7)

`native/x68000_reference/CMakeLists.txt` no longer carries the `current` machine base (the earlier px68k-libretro reference, kept for private
comparison): it named four private adapters that were never part of the public sources (`tools/x68000_hardware.py`,
`x68000_session_hardware.py`, `x68000_disk_hardware.py`, `native/x68000_reference/adapt_upstream.cmake`), so a clean checkout could not build it.
The hissorii base (74ddbb3) is the only one, and any other value is refused with a message. The program does not change: the generated
code, the machine and the states are the same (a conversion of R-Type before and after gives the same trace hashes on every route).
Two files that only that branch compiled leave the tree with it: `native/x68000_reference/session_bridge.c` and `media_probe.c` (no build named them any
more); they are no longer stamp inputs nor public files. A conversion of R-Type after both changes gives the same CPU, RAM, picture and PCM hashes on the three routes.

Stamps: that file is a game input of the Sharp X68000, so its **game stamp moves** (a full reconversion of every X68000 game, with no change in what
a game does); host and build stamps and the other consoles do not move on this account. `tests/test_x68000_cmake.py` shows that the file names no
file that is absent.

## Sharp X68000: the report states that no universal zero-fallback claim is made (1.6.7, gate G15)

The conversion report of the CPS-1 and of the Neo Geo carries `qualification_scope.universal_zero_fallback_claim: false`; the X68000's did not, so
the common `honesty` block read it as unknown (`null`) instead of as a claim the machine does not make. The X68000 report now carries the same block
(`qualification_scope`: the controls its routes drive, floppy disks only, and `universal_zero_fallback_claim: false`). Nothing reads it back to decide a
game, and what a game does does not change.

Stamps: `retrorecomp/x68000_conversion.py` is a game input of the Sharp X68000, so its **game stamp moves** (a full reconversion of every X68000 game,
with no change in what a game does; it comes in the same release as the colour correction above, which moves it already). Host and build stamps, the state
compatibility key and the other eight consoles do not move (checked against main). `tests/test_report_schema.py` fixes the block.

## Lead: unpacked fallback of the packed replay (1.6.7)

Every conversion replays a compressed copy of the build on all its routes against the fresh reference (gate G5). On Linux
one X68000 game builds and runs unpacked and passes `upx -t`, but its compressed copy stops at start (SIGTRAP, exit 133),
and the failed replay refused the whole conversion. Now `delivery_evidence.replay_packed` does what packing already did
when UPX itself failed: when the replay of a copy that really was compressed fails (the replay raises, or the comparison
does not hold), the compressed copy is kept aside and replaced by the build exactly as built, one line says so in the
conversion log, and every route is replayed again on the unpacked file. The compression is blamed only for a failure that
repeats: once the build has passed every route, the compressed copy is replayed once more on the first route that failed.
If it fails again, the unpacked file is delivered (that route is replayed once more on it), `packed_reference_match` is true
for the file actually delivered, and the build is registered (`packing.refuse_compression`, only now) so that the publication
leaves it unpacked too; the report says `packing.packed` false with the notice as `packing.unpacked_reason`. If it passes,
the first error is raised with a note that the failure could not be reproduced (non-deterministic), nothing is delivered and
nothing is registered. If the build fails too, the first error is raised, chained to the second. A file that has not passed
every route is never delivered. It changes nothing for a game whose compressed copy replays, for a file that was not
compressed (option "Compress games" off, UPX failure) or for a user stop. `DeliveredFile` now knows its build; the X68000
replay copies the delivered file into each route's folder at every attempt; Neo Geo's `check_routes` takes the delivered file
and replays through `replay_packed`. The text is in [BUILDING.md](BUILDING.md).

Stamps (computed with the tree of `main` before and the tree of this change, `compilation_inputs.role_stamps` of the nine
consoles): the **game stamp** moves for the eight consoles of `stamp_inputs.sharing('conversion_gates')` (Master System, Game
Gear, Game Boy, NES, Mega Drive, Neo Geo, X68000, CPS-1), because `retrorecomp/delivery_evidence.py` belongs to that group (Neo
Geo's and X68000's own converters, edited too, are already inputs of their game stamps); the Super Nintendo's does not move.
The **build stamp of every console moves**, because `retrorecomp/packing.py` is a build input of every console
(`BUILD_MODULES`). No host stamp moves. A game that replays as before is the same program; exports of 1.6.6 are rebuilt or
reconverted as the release procedure decides. No quick-state key moves.

## Lead: the packed Windows game keeps UPX's call filter (1.6.7)

Since 1.6.6 the packed Super Mario Land was 1.65 MB instead of 1.33 MB while its unpacked build grew by 1.5 KB. UPX 5.3.0
shrinks x86-64 code with a "call trick" filter (win64/pe filter 0x49) that needs one spare byte value: a value that is the
first operand byte of no E8, E9 or 0F 8x byte whose target leaves the code (every such byte counts, inside other instructions
and in tables too). The 1.6.5 build left one (162: UPX chose 0xa2), the 1.6.6 build none, so UPX chose no filter
(`upx --fileinfo`: filter 0x00) and the same compression came out 24 % larger. `--all-filters`, `--brute`, `--ultra-brute`
and `--filter` cannot repair it (the PE packer has this one filter and the filter itself fails); a larger codebase does it by
itself, whatever the game: the NES builds (10 MB or more of code) never had a filter.

`retrorecomp/packing.py` now runs UPX's own scan on the build (`call_filter_length`, the first pass of `ctok.h` in Python,
cross-checked against a brute force in `tests/test_packing.py`; on the thirteen builds below it named the value UPX chose in
each of the nine that kept a filter and the loss in the four that lost it) and, when the whole code has no spare value, writes the
longest length that has one in the SizeOfCode field of the PE header before packing. UPX bounds its filter by that field
(`pefile.cpp`), so it filters that many bytes from BaseOfCode. The delivered packed file carries UPX's own SizeOfCode
(`oh.codesize = osection[1].vsize`): the patched value exists only in UPX's input and in the output of `upx -d`. The Super Mario
Land build of 1.6.6 is filtered over 59 % of its code (cto 87 = 0x57) and packs to 1,367,552 bytes (from 1,647,616; 1.33 MB with
the filter on all the code, which is not possible). The packed file must pass `upx -t` and `upx --fileinfo` must show filter 0x49 (a silent
no-filter result, seen with a SizeOfCode cut at random, passes the test and is 7 % larger); if that fails, or if the header of
the staged copy cannot be written (the antivirus may lock it), the validated build is put back and packed exactly as before; a build whose longest filterable part is under a quarter of the code (the NES) is packed exactly as before. A
build with a spare value over all its code (everything else measured) is untouched: same UPX call, same bytes. The packer, its
SHA-256 checks and its flags are unchanged; the output is deterministic (the publication repacks to the same bytes, checked).
`upx -d` of an affected game gives the build with that one header field changed. The scan reads the code as UPX does (the
section up to its VirtualSize, zeros after) and caps the length at the 16 MiB the filter can address (`max_buf_len`
0x00ffffff, targets under 2^24 with the added value). The conversion log says "UPX call filter kept over N % of the code" for
such a game, and `packing.call_filter` ({filter, code_bytes, filtered_bytes}) records it in the report beside the other
`packing` keys; it is absent for every other game, and the schema-2 `packed` section is unchanged. Windows only: the Linux
ELF has no such field, its packing is unchanged.

Measured on unpacked builds kept by earlier work (UPX as 1.6.6 calls it, then `packing.compact_windows`; every result passes `upx -t`
and repacks to the same bytes; the times are pack plus test on a PC shared with other conversions, so only large differences count):

| Build (console) | Unpacked | Packed before | Packed after | Filter before / after |
|---|---|---|---|---|
| Super Mario Land 1.6.6 (Game Boy) | 5,131,776 | 1,647,616 | 1,367,552 (-17.0 %) | none / 0x49 |
| Sonic the Hedgehog (Master System) | 6,056,960 | 1,861,120 | 1,831,936 (-1.6 %) | none / 0x49 |
| Super Mario Land 1.6.5 and current (Game Boy) | 5,130,240 / 5,134,336 | 1,328,128 / 1,329,152 | same | 0x49 / 0x49 |
| Sonic the Hedgehog (Mega Drive) | 8,191,488 | 2,312,704 | same | 0x49 / 0x49 |
| Puzzle De Pon (Neo Geo) | 11,678,720 | 3,044,864 | same | 0x49 / 0x49 |
| Metroid, Mr. Gimmick (NES) | 12,623,872 / 19,725,312 | 3,107,840 / 4,819,968 | same | none / none |
| Two Super Nintendo games and a Mega Drive game | 24,783,872 / 36,696,576 / 7,707,136 | 5,220,352 / 8,834,560 / 6,095,360 | same | 0x49 / 0x49 |
| Dino, Punisher (CPS-1) | 23,591,424 / 25,851,904 | 7,467,520 / 7,809,536 | same | 0x49 / 0x49 |

Time: 4 to 38 s per game before and after, within the noise (the model adds 0.2 to 2 s, the second UPX pack is only run for the
two games above). The Super Mario Land 1.6.6 game packed this way was converted whole with the 1.6.6 converter and this change
only in `packing.py`: its packed copy replayed on 4 routes against the reference and matched (`packed_reference_match` true).
The NES builds keep no filter (10 MB or more of code, every value is taken within the first 80 KB); `--lzma` would make them 24 % smaller (Metroid 3,107,840 to 2,371,584) at a start-up cost
that was not measured here, a decision for the maintainer.

Stamps (computed with the tree of `main` before and the tree of this change, `compilation_inputs.role_stamps` of the nine
consoles): only the **build stamp of every console moves** (`retrorecomp/packing.py` is a build input of every console,
`BUILD_MODULES`); no game stamp and no host stamp moves. A game packed by the 1.6.6 or the 1.6.7 converter before this change
and rebuilt from its paths is packed again, smaller when it lost its filter.

## Lead: LZMA packing, a reproducible link, a manifest and one identical retry on Windows (1.6.7)

Four changes to how a Windows game is built and packed. None changes what a game does. **None is an antivirus fix**: the
Defender study of 3 November 2026 reproduced no detection on 280 scans, and nothing shows that the method, the link
timestamp or the manifest changes what Defender says about a file.

- **LZMA by default (a size choice).** `packing.WINDOWS_METHOD = 'lzma'` adds `--lzma` to the Windows UPX call (`-9 --lzma
  --compress-resources=0 --compress-icons=0`, the call-filter prefix, `-t` and the `--fileinfo` 0x49 check as before). The
  method is one named constant per OS (`packing.LINUX_METHOD` stays `'nrv'`, UPX's default: Linux is unchanged until the cost
  of `--lzma` on a large ELF, 2.7 s against 0.17 s on a slow laptop in 1.6.0, is measured again). `packing.packing_record`
  and the schema-2 `packed` section carry `method` (`lzma`, `nrv`, or none when the file is not packed); it is optional, a
  report from before reads `None`, no schema number changes. The cost is a start that decompresses a little longer,
  measured on a quiet PC on 3 November 2026 (table below); the owner had approved LZMA if that cost stayed small.
- **A reproducible link.** The portable linker is given `-Wl,--no-insert-timestamp` (`toolchain.LLVM_LINKER_FLAGS`): the PE
  header carries 0 instead of the link time. The static SDL2 is configured with `-ffile-prefix-map=<its source folder>=SDL`
  (`platforms.sdl_compiler_flags`; quoted when the path has a space; not for the Visual Studio fallback, whose `cl.exe` has no
  such option): without it three SDL files (`SDL_render_gl.c`, `SDL_render_gles2.c`, `SDL_render_sw.c`) kept
  `<player's folder>/.deps/SDL/src/...` in the game as assertion strings, so two players got different bytes.
  **The SDL install and its build folder are named after the build settings** (`platforms.sdl_install_key`: SDL revision,
  `SDL_BUILD_FLAGS`, toolchain; `.deps/SDL/install-llvm-<8 hex of the key>` and `build-llvm-<same>`). An SDL installed by 1.6.6 or
  before (`install-llvm`) is therefore never used again by this version, never overwritten and never deleted: the first conversion
  builds the new one beside it (a tree on an older version keeps its own, and two branches that share a `.deps` do not take turns
  replacing one library under a game being linked). The install gets its marker (`retro-recomp-sdl.txt`) as its last step; a folder
  without it is unfinished and is built again, and a build that stops (a timeout, Stop, a crash) keeps its build folder so that the
  next one goes on from it. The three steps (configure, build, install) have a limit of 3600 s (`core.SDL_STEP_TIMEOUT`) instead of
  600 s. The `convert` and `batch` commands build the shared pieces once before the workers start (`batch._prepare_shared`,
  `prepare_shared=True`, outside any compilation budget), so that a batch of several games does not start the same SDL build
  with the one-job share of each worker; the window already does it before a conversion (`dependencies_ready` now reports a
  missing key-named install as not ready, and the dialog says "again (new build settings)" in the eight languages).
  The old `install-llvm` and `build-llvm` stay on disk (about 6 MB and the object files) until the player removes the compiler
  caches. Measured proof: two detached trees of the same commit, each with its **own SDL clone in a different folder**
  (`.build/u3/a/.deps/SDL` and `.build/u3/folder with space/bb/.deps/SDL`; the second started from a copied 1.6.6 install and let
  the `batch` command build the new one), empty libraries, no cover: the same unpacked Super Mario Land (5,135,360 bytes,
  SHA-256 `56bf344c...`) and the same packed game (1,157,632 bytes, `7f55e43c...`), `packed_reference_match` true on 4 routes in
  both, and the same bytes as before the keyed folders. The binary holds no folder of the machine (no `K:`, `Users`, `.deps`,
  `.build`, `worktrees`): SDL's three names read `SDL\src\render\...`. What still varies: nothing found; the strings
  `/home/runner/work/llvm-mingw/...` of the pinned llvm-mingw runtime are the same for every player of the pinned toolchain. The
  title, the cover and the player's options change the binary too (that is a different game, not a variation). Building SDL
  again took 112 s on this PC with two builds running at once (the first conversion after the update; 153 s in an earlier run).
- **An application manifest.** Every Windows game carries resource 1 of type RT_MANIFEST, written inline in the resource script
  (`metadata.MANIFEST_XML`): `asInvoker`, `supportedOS` for Windows 7 to 11, and the DPI awareness the host already asks SDL for
  at start (`rrhk_main.c`: `SDL_HINT_WINDOWS_DPI_AWARENESS "permonitorv2"`; `dpiAware true/pm` and `dpiAwareness
  PerMonitorV2,PerMonitor`), stated before the first window. No UTF-8 code page, no long-path flag, no common-controls version.
  SDL 2.32.10 reads the Windows version only through `WIN_IsWindows8OrGreater`, which is true with or without the manifest, and
  sets its DPI awareness by function pointer: scaling does not change. The manifest is present in the unpacked and the packed
  game (UPX leaves it readable) and the packed game starts (headless). The Visual Studio fallback toolchain gets **no** manifest
  (`metadata._embeds_manifest`): MSBuild embeds its own as resource 1, and a second one is a duplicate resource or LNK1123; a game
  built there keeps MSBuild's default manifest. That toolchain was not tried.
- **One identical retry.** When a Windows pack attempt fails with a sign that the antivirus removed UPX's output
  (`IOException`, `Invalid argument`, `WinError 225`, `virus`, `potentially unwanted`), the validated build is put back, the
  SizeOfCode of the call-filter attempt is written again if it had one, the process waits `DEFENDER_RETRY_WAIT` (5 s, `time.sleep`)
  and runs exactly the same command once. A second failure ends there, as before: the game is published unpacked with the notice
  (and when it was the call-filter attempt, the plain form of the same build is not tried, so that no variant is searched to
  get past a detection). The wait and the retry happen once per packing, whichever form (shortened SizeOfCode or plain) meets the
  sign first. Other failures are not retried.

Measured with `tools/startup_cost.py pack --determinism` on unpacked builds kept by earlier work (the converter's own packing code,
the method switched for each call; every result passes `upx -t`, and packing a second copy gave the same bytes for both
methods in all eight cases; times are pack plus test on a PC shared with two conversions, so only large differences count):

| Build (console) | Unpacked | NRV | LZMA | LZMA / NRV | Pack NRV / LZMA | `upx -t` NRV / LZMA |
|---|---|---|---|---|---|---|
| Sonic the Hedgehog (Master System) | 6,056,960 | 1,831,936 | 1,414,144 | 0.772 | 6.1 s / 3.4 s | 0.07 s / 0.13 s |
| Super Mario Land (Game Boy) | 5,131,776 | 1,367,552 | 1,193,984 | 0.873 | 3.8 s / 3.2 s | 0.06 s / 0.12 s |
| Metroid (NES) | 12,623,872 | 3,107,840 | 2,371,584 | 0.763 | 13.8 s / 8.7 s | 0.09 s / 0.20 s |
| Sonic the Hedgehog (Mega Drive) | 8,191,488 | 2,312,704 | 1,961,984 | 0.848 | 8.0 s / 4.7 s | 0.08 s / 0.17 s |
| DBZ Hyper Dimension (Super Nintendo) | 33,103,360 | 7,424,512 | 6,001,152 | 0.808 | 32.6 s / 19.1 s | 0.48 s / 0.71 s |
| Puzzle De Pon (Neo Geo) | 11,678,720 | 3,044,864 | 2,553,856 | 0.839 | 10.5 s / 9.5 s | 0.19 s / 0.25 s |
| Dino (CPS-1) | 23,591,424 | 7,467,520 | 6,686,208 | 0.895 | 16.6 s / 12.1 s | 0.16 s / 0.26 s |
| R-Type (X68000) | 8,733,184 | 3,716,096 | 3,374,080 | 0.908 | 5.5 s / 4.7 s | 0.13 s / 0.22 s |

`upx -t` decompresses the whole file once, so its difference (+0.05 to +0.23 s here) is an upper bound of the extra start-up
decompression of a game on this PC; the real start is measured by `tools/startup_cost.py start` (see
[BUILDING.md](BUILDING.md)): it needs a quiet PC and the owner's agreement. End to end, Super Mario Land converted whole with
this tree: the packed game is 1,158,144 bytes (the 1.6.7 call-filter build was 1,367,552 with NRV) and its packed copy replayed
on 4 routes against the reference and matched (`packed_reference_match` true); `packing.method` reads `lzma`.

Start-up cost (`tools/startup_cost.py start --runs 9 --core 4`, quiet PC, 3 November 2026, Windows 11, one core pinned):
median milliseconds from the creation of the process to its exit after one headless frame (two for the X68000, whose host
exits with 1 after a single frame). "Second start" is a game started again, the usual case; "first start" is a fresh copy of
the file, which Windows Defender scans before it runs (the first launch after a conversion), and it varies much more. A fresh
copy is still in the file cache (no administrator rights to flush it).

| Game (console, unpacked size) | Second start: unpacked / NRV / LZMA | LZMA - NRV | First start: NRV / LZMA | LZMA - NRV |
|---|---|---|---|---|
| Sonic (SMS, 6.1 MB) | 18 / 49 / 104 | +55 | 601 / 704 | +103 |
| Sonic Drift (GG, 6.1 MB) | 19 / 50 / 123 | +73 | 902 / 1,048 | +146 |
| Super Mario Land (GB, 5.1 MB) | 19 / 44 / 92 | +48 | 514 / 606 | +91 |
| Metroid (NES, 12.6 MB) | 20 / 54 / 151 | +96 | 923 / 1,132 | +210 |
| Kirby's Adventure (NES, 43.4 MB) | 27 / 127 / 409 | +282 | 2,829 / 3,373 | +544 |
| Sonic (MD, 8.2 MB) | 22 / 59 / 141 | +82 | 608 / 783 | +175 |
| SNES campaign g02 (40.0 MB) | 40 / 160 / 287 | +127 | 2,031 / 1,057 | -974 |
| Real Bout Fatal Fury Special (NG, 50.2 MB) | 197 / 318 / 470 | +152 | 2,059 / 2,387 | +328 |
| The Punisher (CPS-1, 25.9 MB) | 61 / 133 / 260 | +127 | 2,172 / 2,098 | -74 |
| R-Type (X68000, 8.7 MB) | 29 / 81 / 221 | +141 | 1,284 / 1,424 | +141 |

LZMA adds 48 to 282 ms to a usual start (the largest, Kirby's Adventure, 43 MB unpacked: +0.28 s) and up to about half a
second to the first launch after a conversion, where the antivirus scan dominates (2 to 3 s for the largest games with either
method). The Neo Geo's F11, which starts the file again, pays the second-start figure (+0.15 s on Real Bout). It measures the
start only: nothing about the native code share, CPU or hardware fidelity, gameplay or physical latency. Linux is not measured
and keeps NRV.

Stamps (`compilation_inputs.role_stamps` of the nine consoles, the tree of `main` against this one): **all three stamps of every
console move**. The build stamp (`toolchain.py`, `packing.py`) and the host stamp (`metadata.py`,
which writes the resource script, and the interface texts) move because of the method, the link flag and the manifest. The **game stamp
moves too, because of `core.py` and `platforms.py`** (the SDL configuration; both are game inputs of every console): the main tree of 1.6.7 already moves
every game stamp for other reasons, so this adds no reconversion, but it does mean a 1.6.6 export is never taken as current by this change
alone. No file is added to the stamps (`tools/startup_cost.py` and the tests are public files outside them). An export is rebuilt from its
paths as for any such change, and is smaller and carries the manifest once rebuilt. For a player the one visible effect is the first
conversion after the update: it builds SDL2 again (112 to 153 s here) before anything else, with a progress dialog in the window and one
build before the workers in a batch. A developer who shares one `.deps/SDL` between several trees (junctions to the main checkout)
gets the new install beside the old one, built once by the tree that converts first, and the other trees on older code keep theirs.

## Host or game: the classification

Every input that shapes an export is fingerprinted (`retrorecomp/compilation_inputs.py`).
`role()` splits them in two. **Host** inputs are the interactive player
shell. They are never used by the headless runs that discover and validate a
game's code; those go through each console's entry (launcher, main, runner),
which is game-side. **Everything not listed as host is game-side**, so a new
or unclassified file triggers a full conversion until it is classified.

The same categories apply to every machine:

| Category | Host inputs |
| --- | --- |
| Shared menu core (identical everywhere) | `retro_menu.c/.h`, `game_options.h`, `autofire.h`, `retro_keyboard.h` |
| On-screen text and fonts | `runtime_catalog.inc`, `runtime_i18n.h`, `font6x10.h`, `font10x20.h` |
| Presentation | `scale2x.h`, `scanlines.h`, `scanline_sdl.h`, `xbr_filter.h`, `xbr_sdl.h`, `display_settings.h`, `icon.c/.h` |
| Sound output after the emulated mixer | `audio_filter.h`, `audio_cushion.h`, `audio_output.inc`, `hostkit/shell/rrhk_ring.c`, `md_audio_loop.inc`, `md_audio_resample.inc`, `megadrive_audio.py` |
| Artwork, metadata, publishing | `artwork.py`, `cover_*.py`, `metadata.py`, `languages.py`, `publishing.py`, `windows.py`, `licenses/*.md`, `THIRD_PARTY_NOTICES.md`, application icons |
| Checks of the above | `game_options_checks.c`, `language_checks.c`, `xbr_checks.c`, `display_settings_checks.c`, `icon_checks.c`, `audio_checks.c`, `nes_audio_checks.c` |

Each machine family has one shell for its window, menus and input:

| Machine | Shell (host) | Entry used by discovery and validation (game) |
| --- | --- | --- |
| Master System, Game Gear | the host kit, staged beside the common runtime: the shell and `hostkit/adapters/rrhk_sms.c` (with `audio_output.inc`) | `launcher.c` and the Z80 runtime |
| Game Boy | the host kit, staged in the project's runtime: the shell, `hostkit/adapters/rrhk_gb.inc` (included by the patched `platform_sdl.cpp`) and `gameboy_host.py` | `game_main.c`, `gameboy_runtime.py` |
| Mega Drive, SNES, Neo Geo, CPS-1, NES | the host kit: `native/hostkit/shell/rrhk_*.c` (shared) and `native/hostkit/adapters/rrhk_<machine>.c`, copied by `hostkit.py` | `console16_main.c`, `neogeo_main.c`, `cps1_main.c`, machine adapters; for the NES, the runner adapted by `nes_runtime.py` |
| Sharp X68000 | the host kit, compiled from the tree: the shell and `hostkit/adapters/rrhk_x68k.inc`, included by the frontend | `x68000_reference/reference_host.c` (frame loop, reports, states, disks) and the SDK |

Files that are used both by the shell and by headless checks stay game-side:
`platform_io.c/.h` (quick-state files), `embedded_resources.h`, the
machine adapters `cps1_host.c` and `neogeo_host.c` (input and state
mapping), and every CPU, video, sound-chip, timing, learning and validation
file. Since 1.2.8 the Game Boy shell patches live in `gameboy_host.py`,
separate from the runtime patches in `gameboy_runtime.py`; the guest-side
JOYP refresh hook moved from `gameboy_timing.py` to
`gameboy_runtime.adapt_input_refresh_hook`. The generated Game Boy project is
byte-identical before and after that split. (Since 1.6.3 `gameboy_timing.py` is gone: the Game Boy shell is the host kit and its
adapter.)

The modules that read the paths (`knowledge.py`, `path_profiles.py`, `feedback.py`,
`neogeo_knowledge.py`, `snes_knowledge.py`) are game-side, `knowledge.py`,
`path_profiles.py` and `feedback.py` for every console: they decide which code a
game starts from. Since 1.6.0 `knowledge.py` delegates to `path_profiles.py`, so
that module is in every console's game stamp (it was an interface module while
only the exchange and the shared base used it). The modules that only share
discoveries (`knowledge_exchange.py`, `knowledge_build.py`, `online.py`) stay
interface modules. Neo Geo receipts of releases before 1.6.0 hashed the whole Neo Geo bank in their knowledge part; 1.6.0 hashes the
game's own record, which is one more reason none of them is listed.
A Neo Geo receipt is written with the game's key as the conversion found it. The paths' own stamp (`knowledge_stamp`) hashes the game's
record, not the bank: see [the paths and the stamps](COMPILATION_LIBRARY.md#stage-b3-the-conversions-follow-the-module-27-october-2026).

## Reproducible stamps

A stamp hashes a list, never what is on disk (docs/STANDARDS.md rule 5). The
list is `INPUTS` in `retrorecomp/stamp_inputs.py`: every converter module and
every file that can enter a stamp, grouped by the consoles that own it, plus
`NOT_INPUTS` for the tracked files that are deliberately out (interface
pictures, locales, credits, the knowledge snapshot, the UPX tools). A file on
disk that is not listed changes no stamp; a listed file that is missing is an
error; `tests/test_stamp_inputs.py` fails when a tracked file is neither
listed nor declared out, or when a listed file is not bundled in the
executable. Text is hashed with CRLF turned into LF (and `.gitattributes`
pins LF for these types), so a Windows working tree, an archive of a tag and
Linux give the same stamps; the two catalogues that are checksummed byte for
byte are hashed as they are. The save-state key of the Mega Drive and Super
Nintendo and the Master System / Game Gear compiler signature read the same
list (the native files their console owns), not the folder.

`compilation_inputs.py` (the algorithm) and `stamp_inputs.py` (the data) are
interface modules: no stamp hashes them, so registering an interface module,
adding a file to one console's list or editing `LEGACY_GAME_STAMPS` moves no
game stamp. A change of the algorithm itself bumps `STAMP_LABEL`, which a test
pins on a synthetic input.

## Adding or changing a file

- Every new file under `native/`, `assets/`, `profiles/` or `licenses/`, and
  every new converter module, is added to `INPUTS` with its owners (or to
  `NOT_INPUTS` / `INTERFACE_MODULES` when no game depends on it). The
  completeness test names what is missing. Its role (host, build or game) comes
  from the tables below.
- A new menu, text, filter or shell file: add it to `HOST_NATIVE` or
  `HOST_MODULES`, and to the tables above, only if no headless discovery or
  validation run uses it.
- A Python patch module must not mix shell and machine patches; split it as
  `gameboy_host.py` / `gameboy_runtime.py` do.
- `tests/test_compilation_inputs.py` checks the classification of every
  machine's shell and entry.
