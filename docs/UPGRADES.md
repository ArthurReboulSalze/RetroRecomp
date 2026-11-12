# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

This page keeps the rules, the current release and the one before it, and still the sections of 1.7.0 and 1.6.8. The detail of releases 1.6.9, 1.6.7 and 1.6.6 is in
[UPGRADES_HISTORY.md](UPGRADES_HISTORY.md), and that of 1.6.5 and before in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md) (the same text,
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
  tree of 1.6.4 lists none, a full reconversion of every console ([below](UPGRADES_HISTORY_OLDER.md#exports-of-163-in-164)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1. The Mega Drive, Super Nintendo, Neo
  Geo and CPS-1 keys of 1.6.1 (Windows) in the tree of 1.6.2. The same four consoles' keys of 1.6.2 (Windows) in the
  tree of 1.6.3. The Neo Geo key of 1.6.3 (Windows) alone in the tree of 1.6.4: the Mega Drive and Super Nintendo keys did
  not move, and the CPS-1 and NES states changed ([below](UPGRADES_HISTORY_OLDER.md#exports-of-163-in-164)).
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

## Master System, Game Gear: the Z80 chain made ready for a second Z80 machine (1.7.3)

**What changes.** The banked Z80 engine carried the Sega mapper as constants: the bank key `b0, b1, b2`, three 16 KiB slots, a first
KiB that never pages, code from RAM at `pc >= $C000`, the plain Z80 cycle table and /INT sampled at the start of a step. They are now
one description per machine, `Z80Machine` in the new `retrorecomp/z80_chain.py`, which the profiles of the Master System and the Game
Gear name (`z80_machine = SEGA_MAPPER`). The emitter (`native/banked_emitter.inc`) reads it and names no mapper or address of its
own; the step loop (`native/banked_runtime.inc`) is unchanged, and `z80_chain.runtime_source` renders its machine-dependent lines.
The description also has what a second machine will need and no machine uses yet: wait states per M1 cycle, /INT read at the end of
the instruction, and a second way to key the code, by a region map over several sources with RAM in any region (`Z80RegionMap`).
A machine also names the folders of its own build of the translator (`generator_tag`; `core.dependencies` and
`core.compiler_signature` take the machine), and `cpu.prepare_reference` can make the reference CPU count its M1 cycles
(`m1_counter`), from which the counted fallback adds the wait states. For the Sega mapper the tag is empty and the count is off:
the same folders, the same signature, the same reference CPU. No machine is added.

**The output is identical.** For the Master System and the Game Gear nothing a conversion writes changes. Proof, three conversions
with the real command line (portable toolchain, Windows), once from main `f12dc2df` and once from this change, in two separate
checkouts with a library of their own:
- Sonic The Hedgehog (Master System, banked), Sonic The Hedgehog (Game Gear, banked), Alex Kidd in Miracle World (Master System,
  `--backend functions`).
- The 146 files the translator generates and the 77 other sources and inputs of the three projects (the patched glue, the Z80 headers,
  the reference CPU, the configuration) are equal byte for byte; the three build logs differ by the checkout path and the times.
- The three delivered executables are equal byte for byte, and so are the unpacked ones.
- The 29 run records are equal but for wall-clock times and the checkout path (frames, VDP traces, RAM, final CPU state, native and
  interpreted counts).

`tests/test_z80_chain.py` pins that the step loop rendered for the Sega mapper is the file itself, and what another machine renders.
The region-map form was run once in an authored harness (two sources, a map that changes, RAM in a low region, an instruction across
a region edge, one wait state per M1): 23 checks. It is not a qualification of any machine, and it says nothing of CPU fidelity,
hardware fidelity, gameplay or latency.

**Hot path:** no. The generated C of a Master System or Game Gear game is the same text, and the executables are the same bytes.

**What moves:** the game stamps of the Master System and the Game Gear (their profiles, the new module, the group `shares:z80_main`
that now holds `retrorecomp/cpu.py`). `native/banked_emitter.inc` and `retrorecomp/core.py` are game-stamp inputs of every console,
so **every console's game stamp moves** (it moves in 1.7.3 anyway, see the next section). Host and build stamps do not move.

**Quick states:** unchanged.

## Every console: a step still writing goes past its time limit (after 1.7.2)

A player's small PC needed more than 30 minutes to compile Kirby's Adventure, and the conversion stopped at the step's fixed limit
while the compiler was still finishing files. The build and generation steps (`core.run`: CMake, the compilers, the recompilers) now
go past their limit while they are still writing (a compiler prints a line per finished file), as long as their last line is younger
than the limit, up to four times the limit (`PROGRESS_LIMIT_FACTOR`). A step that writes nothing for a whole limit is stopped as
before, and Stop still kills it at once. Replays and probes keep their fixed limit. The shared setup lock (the SDL build) waits as long.
A step stopped this way is named with the time it ran, in minutes. The game report lists the five languages a generated game ships
(`ui_languages`; it listed the converter's eight), and the CPS-1 and CPS-2 print "no interpreter on the routes played" when a set is
ready without a fallback, as the PC Engine does. Proof: `tests/test_stop_now.py` (a writing step past its limit, a silent one stopped at
it, an endless writer stopped at the ceiling, text decoded as `subprocess.run` does). **Hot path:** no, nothing in a game changes.
**What moves:** `retrorecomp/core.py` and `batch.py` are game-stamp inputs of every console, so **every console's game stamp moves**:
an export of 1.7.2 is converted again at the upgrade (the quick upgrade above, from its learned paths). The shared paths of the base are kept (they are qualified by the
recompiler's revision, not by this stamp). **Quick states:** unchanged.
## Mega Drive: the limits of the learned code are counted, never silent (1.7.3)

The Mega Drive keeps three tables of code it learned from the runs: the work-RAM instructions (2,048 distinct variants, in the exported
game's recording table and in the library), the Z80 opcode variants (32,768) and the driver images whose 8,192 positions are all compiled
(4 per run). What did not fit was dropped without a trace: an instruction past the limit is not recorded, so no later pass compiles it, and it
stays on the counted interpreter, but nothing said why. It is now counted and reported at every place that cuts:

| Where it is cut | What counts it |
|---|---|
| the exported game's recording of work-RAM variants (`native/md_backend.c`, 2,048) | `ram_observation_overflows` (observations of a variant that no longer fit), `ram_variants_dropped` (distinct ones, from a table of 4,096; `ram_variants_dropped_exact` is false if that table saturated, and then the distinct count is a lower bound) and `ram_variant_limit`, in the report of each probe (so in each `final_checks` row and in each row of `passes`) and in the conversion log (the line the Super Nintendo already had, now for the Mega Drive too) |
| the library of work-RAM variants (`megadrive.py`: the lowest addresses are kept, as before) | `megadrive.ram_variant_overflow`: distinct variants known against the limit, and how many are past it |
| the Z80 variants the game could not record (`z80_dropped_variants`, already in the probe report) | now also in the conversion log, like the RAM line |
| the library of Z80 variants and the driver images (`megadrive_z80.py`: 32,768 variants, 4 images per run) | `megadrive_evidence.z80_limits`, read after the last learning: the library's size against the limit (`library_full` when it is at it), how many variants the runs observed are not in it (`observed_dropped`), and the driver images past the first four of a run (`images_dropped`); `megadrive_z80.py` itself is not edited (it is a pinned CPS-1 generator source) |

One block ties them together, `learning_limits` in the conversion report (`megadrive_evidence.learning_limits`): the limits, what is known, what is
past each, the game's own counts, `anything_cut`, and the claim that what is past a limit is not recorded and stays on the counted interpreter. When
anything was cut, the conversion log says so in one line. **What is dropped is the same as before:** the variants that are kept are the same, so no
generated code changes; the selection (lowest addresses first) is left as it was, and a "keep the newest" rule is not part of this change. The instructions
past a limit are already counted as interpreted fallback (`ram_fallback_opcodes`, `audio_interpreted_opcodes`, and `main_interpreted_opcodes` in the batch
result); what is new is the cause. The common report v2 (`report_schema.py`, the lead's) does not read `learning_limits` yet.

**Figures.** The 27 October snapshot gave the largest known records: 1,261 work-RAM variants (62 % of 2,048; the cartridge is not among the owner's
exports) and 23,436 Z80 variants (72 % of 32,768, Altered Beast). Read by this change's conversions (quick check, scratch library, shared paths on):
Altered Beast (USA) 34 RAM variants of 2,048 and **23,437 Z80 variants in the library, for a limit of 32,768 (71.5 %)**; Gunstar Heroes (USA) 389 of 2,048 (19 %) and 15,903 Z80 variants
(48.5 %); both with nothing cut, 0 interpreted on both routes, native equal to the reference. A limit **is** reached by an authored cartridge
(`tools/megadrive_variant_cap_selftest.py`: a loop writes 3,000 `MOVEQ` words to work RAM and calls them): 3,001 distinct RAM instructions against 2,048,
the game records 2,048 and reports 953 observations and 953 distinct variants dropped, the library holds exactly 2,048, native equals the reference; the same
cartridge converted whole (`batch`): pass 1 interprets 3,001 main CPU opcodes and says 953 were past the limit, pass 2 runs 2,048 natively and 953 stay
interpreted and counted on both routes, `learning_limits` says 3,001 known for 2,048 (953 past the limit), and the compressed copy matches the reference.
A control with 1,000 words reports 0 everywhere.

**Is a bigger limit cheap?** In the game, yes: the RAM table is `M68KInstr ram_variants[2048]`, 60 bytes each (123 kB; 8,192 would be 491 kB), and each
variant is one more guarded body to compile; the Z80 table indexes with 16 bits, so 32,768 could rise to 65,535 at about 128 kB more. In the shared record,
no: the field caps `('ram_refs', 2048)` and `('z80_refs', 32768)` of `path_profiles.LEGACY_FIELDS` (and the site's checks of the same table) decide what a record
may hold, so a bigger local limit would only be lost when shared. Raising them is a format revision, not a Mega Drive change. With 62 % and 72 % of the
limits used by the largest known games, and four driver images alone able to fill the Z80 limit (4 x 8,192 positions), the counters are what decides: raise a
limit when one of them shows a game that reaches it.

**What moves.** Game stamps: the Mega Drive (`md_backend.c`, `megadrive.py`, `megadrive_evidence.py`, `console16.py`), and the CPS-1, the CPS-2, the Super Nintendo, the
Neo Geo and the PC Engine through `console16.py` alone (their behaviour does not change: the line the Super Nintendo had is now written for both, and the
new block is the Mega Drive's alone). `megadrive_z80.py` is **not** edited (the CPS-1 pins it, `tests/cps1_generator_pins.json`; the Z80 counters read it from
outside), so no CPS-1 generator pin or `GENERATOR_REVISION` is involved. Host and build stamps of every
console: unchanged (stamp baseline, `tools/std_baseline.py`, before and after). **The quick-state key of the Mega Drive moves** (`md_backend.c` is one of the
native files `RR16_STATE_ABI` hashes: `d76e8413…` becomes `3b585e00…`): Mega Drive quick states written by a 1.7.2 game are refused cleanly by a 1.7.3
game (the N-1 rule of this page, no compat key); cartridge saves are not affected, and the state layout is not touched. The keys of the Super Nintendo, the
CPS-1 and the Neo Geo do not move (same digests). The four 68000 generator files that the CPS-1 and the X68000 pin (`m68000.py`, `m68000_state_rules.py`,
`megadrive_rules.py`, `neogeo_codegen.py`) are not touched. New file and its role: `tools/megadrive_variant_cap_selftest.py` (no stamp; in `PUBLIC_FILES`).

**Cost.** None on the hot path: the new code runs only when a RAM instruction does not fit, which is the slow path that already scans 2,048 entries.
The report grows by four numbers per probe.

**Checked.**

- unit tests: `LearnedCodeLimitsAreCountedTests` (the library counts, the Z80 library and its images count, the driver images learned are the first four of
  each run, the report block and its exactness flag), the console, report-writer, stamp and Mega Drive suites;
- `megadrive_variant_cap_selftest`: below and past the limit, native equal to the reference (figures above);
- the authored cartridge converted whole, and Altered Beast and Gunstar Heroes converted from a scratch library (figures above);
- A/B (`tools/ab_conversion.py`, `e4ec565b` against this branch, Gunstar Heroes (USA), standard scan, empty library on both sides): both convert, 504 files
  compared, and **only nine differ**: `md_backend.c` (the change), `generation-identity.json` (the stamps), `hardware-profile.profdata` (the compiler's profile of the
  rebuilt binary) and the six probe result files, whose only differences are the four new keys (`ram_observation_overflows`, `ram_variant_limit`,
  `ram_variants_dropped`, `ram_variants_dropped_exact`); in the conversion report the differences are those keys, `learning_limits` and the new fields of
  `passes`, and the packed size ratio (0.3488 against 0.3487, a different binary). Every generated step, every picture, sound, CPU, RAM, VDP and Z80 hash is equal.

## Master System and Game Gear: the cap on compiled RAM windows is counted (1.7.3)

The banked engine compiles at most 4,096 RAM windows per ROM (`library.PATTERN_LIMIT`; the generator reads the same file). `GameMemory.code_patterns()` cuts at that limit, so the
report's `compiled_windows` and `pending_windows`, both taken from it, could never show that a window was left out. The report now says it: `learning.native_profiles` gains
`window_limit` (4,096) and `windows_over_limit`, the number of distinct windows the ROM's journal, the candidates of its own feedback and the shared hints hold beyond the limit
(0 when none was left out; the journal itself keeps them). Nothing is compiled differently and no game changes: the largest known ROM holds 0 of them in the shared base, so the cap is a
bound today and now a visible one. Reports, not games.

**What moves.** `retrorecomp.core` and `retrorecomp.library` are inputs of every console: the game stamp of all nine consoles then moves with this change like with any edit of `core.py`
(the generated game is the same); the host stamps and the quick-state keys do not move. An export made before carries no `windows_over_limit` (it reads as absent, not as 0).

## Atari ST: the player's own record (1.7.3)

An exported Atari ST game now keeps the player's own record (F12, on by default, in `datas/fallbacks` beside the game): windows of 16 bytes at instructions that ran on the interpreter, with the TOS they
ran on. The next conversion of that game reads it and makes native code of those instructions and of what a walk through each window finds, counted apart (`native_learned`, `native_walked`,
`player_record` in the report); no route proves them, the guard on the latched opcode is the same, and a window of another TOS or whose ROM bytes changed is not used. The record is private and never
shared. The walk is shared with the Amiga (`retrorecomp/m68k_record_walk.py`): the Amiga's `walk_records` now calls it, with identical results on three real records of players (Lotus 2 among them).
Measured on one scripted session each: Turrican II's window of play past its routes from 6.91 % native to 100.00 %, Indiana Jones from 569 interpreted instructions to 0; beyond the routes the native trace
equals the interpreted one. **What moves:** the Atari ST's game stamp and the Amiga's game stamp (the shared walk; no Amiga output changes); no host stamp, not the X68000's. **Quick states:** the Atari ST's
key moves, as between any two Atari ST builds. **Hot path:** nothing on native code; on an interpreted instruction, one test, and a 16-byte read and a record when a new window starts.

## Atari ST: a sweep over the memory at the end of the routes (1.7.3)

A conversion now walks an image of the RAM taken at the last frame of each fresh reference run, with the TOS ROM, from the instructions the routes ran, and compiles what it reaches as native code with the same
guard on the latched opcode (`retrorecomp/m68k_record_walk.py`, shared; `atarist_codegen.sweep`): branches, DBcc, JSR and JMP with an absolute or PC-relative address, and what falls through, from an
observed instruction the image still holds as observed, up to 60,000 instructions added (a capped sweep says so). They are counted apart (`sweep` and `final_checks.native_swept` in the report; the player's
headless report has `native_swept`); no route proves them, and on the routes the count is 0 by construction. The image is read by the conversion and deleted, never copied to the library or to the export; a page
fill (every even address of a page where code ran) is written and tested but off (measured once on Turrican II: 91.48 % native, 59,190 swept, 42.6 MB, trace equal). Measured on Windows, Standard level from an empty library, the delivered game on a play script of 5,200 (Turrican II, TOS 1.04) and
4,500 frames (Bomb Jack, EmuTOS): Turrican II's window of play from 6.91 % native to 73.00 %, Bomb Jack's 17 interpreted instructions to 0; native and interpreted traces of every frame byte-identical. Cost, on a PC shared with other sessions (so the times are indicative), a cold build of the same game's native code without and with the sweep, in turn: Turrican II 24-33 s and 19.6 MB against 61-81 s and 29.3 MB (packed 4.6 against 5.3 MB), Bomb Jack 38 s and 22.5 MB
against 49 s and 25.3 MB (packed 5.6 against 6.0 MB). `tools/atarist_sweep_guard_check.py` shows the guard on an authored program that rewrites a swept block before it runs it (another opcode: the routine never
runs, the interpreter does; the same opcode with another extension word: the routine runs and reads the new word). **What moves:** the Atari ST's game stamp, and the Amiga's game stamp as well, because
`retrorecomp/m68k_record_walk.py` (the walk shared by the two machines, which gained the sweep) is owned by both: no Amiga output changes, the Amiga's own sweep (`amiga_codegen.sweep`) is not touched. No
host stamp, not the X68000's. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds. **Hot path:** nothing on native code (a swept instruction counts into one more counter); the exe is larger and
a conversion compiles longer in proportion to what is swept.

## Commodore Amiga: Denise's line work by table and by word, Agnus's clock step inlined (after 1.7.2, Agnus/Denise step 1)

Hand optimisations of emulated code, through vAmiga's adaptation (`retrorecomp/amiga_vamiga.py`): the same events at the same instants and the same bytes in every buffer after each
function, fewer operations. Denise's draw routines take a shift register's slices from a table and write the line buffer four or two entries at a time; when both parities are armed
at the same offset one pass writes what the two passes wrote. The dual-playfield translation runs vAmiga's own loop once on the 256 possible bytes for a playfield state and then
looks each pixel up. The palette pass takes eight entries at a time where none is border. `Agnus::execute`, called at every colour clock, is defined in its header so it can be
inlined. Agnus and Denise stay emulated; nothing here is specialised from a game. ThinLTO of the Core, the session and the player (`RR_AMIGA_THINLTO`, clang only; llvm-mingw on
Windows) is on: a quiet-PC timing on 10 November 2026 (Lotus 2's native game, 2,400 frames of a racing route, one core, two interleaved runs per build) gave 2.571 ms of
machine time per frame before this step, 2.245 ms with it (-12.7 %) and 1.992 ms with it and ThinLTO (-11.2 % more), past the 3 % bar Arthur set; the two ThinLTO runs differed by
7 %. A second quiet pass on 11 November (four interleaved rounds, the rounds of each build within 3 %): 2.493 ms before, 2.158 ms with this step (-13.4 %), 1.887 ms with ThinLTO
(-12.6 % more); the 7 % did not come back. This is the cost of a frame on one PC, not a latency.
Proof: `tools/amiga_display_selftest.py --against` the build made before the change: 40 scenarios of 4 frames (1,301,275 instructions) and the 12 of the default run, every
instruction's record and every frame's record equal; each of the four new paths broken on purpose in its own build is seen (in 3 to 6 scenarios of 6). Lotus 2's native game and the
reference player, built before and after (and after with ThinLTO), give the same trace on every one of 3,600 frames of a racing route (picture, sound, RAM, registers). The first-read
conversions are not done yet. **What it brings:** the timing above, on one game; an earlier estimate from shares of a loaded PC was 12-17 % (21-25 % on a dual-playfield game). **Hot path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga
builds; the dual-playfield table is derived and rebuilt after a load.

## Commodore Amiga: a line's bitplane slots taken in a batch (after 1.7.2, Agnus/Denise step 2)

Agnus no longer schedules an event for every bitplane slot of a line whose plan allows it. At the start of such a line its bitplane DMA slots are marked taken on the bus, as
vAmiga's own events mark them before anyone else in their colour clock, and they run later in their own order, each at the beam position of its slot, as soon as something could
see them: a custom register access by the CPU or the Copper, a chip RAM write (CPU, Blitter, disk DMA, the host's patches) into a fetch still to come, a read of the open bus,
the start of a register-change event (HSYNC and EOL among them), and vAmiga's own bitplane event. The data bus keeps the colour clock of its last value, so that a fetch run late
never covers a later one. The guard, decided per line: no AGA, never line 0 (where a host frame ends), every bitplane DMA slot between $18 and $E1, no super-hires fetch, each
plane's modulo on its last fetch, every fetch in chip RAM; a new plan in the middle of the line (DDF, BPLCON0, DMACON, the vertical window) or a pointer moved out of chip RAM gives
the rest of the line back to vAmiga's events. Through vAmiga's adaptation (`retrorecomp/amiga_vamiga.py`, MPL-2.0 edits). Agnus stays emulated: the same work, at fewer
scheduled instants; nothing is specialised from a game. The lines and words batched, on events and given back are counted per route in the conversion report
(`final_checks.agnus_denise`, with the device notes under `hardware_devices`).
Proof: `tools/amiga_display_selftest.py` now runs each scenario batched and with `--per-slot` (every line on vAmiga's events) in the same build: 12 scenarios of 4 frames (420,350
instructions; 9,755 lines batched, 488 given back midway, 5,069 on events), every instruction's record and every frame's record equal. `--against` the frozen build of step 0:
40 scenarios of 4 frames (1,297,343 instructions; 32,161 lines batched, 1,940 given back, 16,119 on events), all equal. The scenario program gained reads of write-only registers
(they write the last bus value into them), BPL1DAT writes and pointer writes. A first version missed one case, found by the self-test on 9 NTSC scenarios out of 52: on an NTSC
long line vAmiga runs the bitplane event of position 227, which came before slots still pending; that event now runs them first. Each barrier broken on purpose in its own build is seen against `--per-slot` on 8 other scenarios: the
register-event barrier 8 of 8, the give-back of the marks 8 of 8, the custom read barrier 7, the custom write barrier 6, the bus clock 6, the bitplane-event barrier 2 (the NTSC
ones), the chip RAM write barrier only 1 of 8 (a random write seldom lands ahead of the beam in the same line: that barrier is the least exercised). Lotus 2's native game and
the reference player built with this step (and ThinLTO) give the same trace as the build before step 1 on every one of 3,600 frames of a racing route. First-read conversions
with the real command line (11 November 2026): Lotus 2, Pinball Dreams (NTSC) and Shadow of the Beast, two routes of 3,600 frames each, every frame equal to the fresh
reference, 0 instructions interpreted. **What it brings:** on a quiet PC, 11 November 2026, one core, Lotus 2's racing route of 2,400 frames, four interleaved rounds, the
machine time per frame goes from 1.887 ms (step 1 with ThinLTO) to 1.809 ms (-4.1 %; rounds within 2.1 %), past the 3 % bar; one game, not a latency. **Hot path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other
console. **Quick states:** the Amiga's key moves, as between any two Amiga builds; the batch state is derived, never saved (line 0, where a state is taken, never has one).

## Commodore Amiga: a quiet line's pass in one loop (after 1.7.2, Agnus/Denise step 3)

At the end of every visible line Denise translates its line buffer into colour indices (`translate`), draws the sprites, checks playfield collisions and turns the indices
into the texture row (`colorize`). On a quiet line the colour index of each buffer byte depends only on that byte and on the line's start state, so `translate`'s own loop is run
once on the 256 possible bytes for that state (kept in a table, rebuilt when the state changes) and the row is written in one pass: index through the table, then the palette
or the border colour, eight entries at a time where none is border. Colour changes inside the line are applied between chunks, as `colorize` applies them; the collision check
runs as before. Quiet means: no sprite armed or recorded in the line, no BPLCON0, BPLCON2 or BPLCON4 change in it, no HAM, no super-hires, no border sprites, no hidden bitplanes
or X-ray layers, not AGA, and the next line visible (vAmiga's VBLANK branch reads the buffers `translate` leaves, so the last visible line takes vAmiga's pass). Every other line
takes vAmiga's line pass. Through vAmiga's adaptation (MPL-2.0 edits). Denise stays emulated; the plan's draw list and per-game routine keys were not needed for this first
form, so nothing is specialised from a game: it is a hand optimisation of the same work, with a guard. Counted per route in `final_checks.agnus_denise` (visible lines in one
pass, on vAmiga's pass).
Proof: the display self-test with steps 2 and 3 against `--per-slot` (both off) on the 12 default scenarios (12,176 visible lines in one pass, 1,460 on vAmiga's pass) and
`--against` the frozen build of step 0 on 40 more (37,896 and 6,560), every instruction's and every frame's record equal. A first version differed on Denise's snapshot only, with
the same pictures: `translate` writes its end-of-line entry into the change history before clearing it, and those entries are saved; the one-pass line now does the same. Each
rule broken on purpose in its own build is seen against `--per-slot` on 8 other scenarios: a wrong table entry 6 of 8, a colour change skipped 7, the border ignored in a block 6,
the collision check skipped 8, the sprite guard off 2, the BPLCON-change guard off 6, the history entry not written 1. Lotus 2's native game and the reference player built with steps 2 and 3 give the same trace as the
build before step 1 on every one of 3,600 frames of a racing route; on that route 1,123,512 lines were batched and 3,601 ran on events (line 0 of each frame, none given back),
and 1,029,889 visible lines were passed in one loop against 3,601 on vAmiga's pass (the last visible line of each frame). **What it brings:** on the same quiet pass, 1.809
to 1.710 ms per frame (-5.5 %; rounds within 0.7 %); steps 1 to 3 with ThinLTO together, 2.493 to 1.710 ms (-31.4 %) on Lotus 2's route, one PC, not a latency. **Hot
path:** this is one. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds;
the table is derived, never saved.

## Commodore Amiga: stage 7's bus model in shadow, never in an export (after 1.7.3, stage 7 checkpoints 0-2)

**What changes.** A bus and DMA model of our own (`native/amiga_machine/amiga_bus.*`, MIT) can be computed beside vAmiga, line by
line, to compare its slots and its CPU waits with vAmiga's. Its hooks in vAmiga's adaptation (MPL-2.0 edits) sit under
`#ifdef RR_AMIGA_SHADOW`.
- The CMake option `RR_AMIGA_SHADOW` is OFF by default. An export is never built with it.
- Only the display self-test and private reference players turn it on.
- Without it, every hook is removed by the preprocessor, so an export compiles the same code as before.

**Hot path:** no, in an export: the hooks are not compiled.

**What moves:** the text of the hooks is part of vAmiga's adaptation, so its digest moves, and with it the Amiga's game stamp. No
other console moves.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the idle disk controller's events caught up (after 1.7.3, stage 7 checkpoint 3a)

**What changes.** vAmiga's disk controller has an event about every 56 colour clocks, whether or not a floppy is in use. In a WHDLoad
install that is 1,269 events per frame on every game, between 4 and 21 % of all the machine's events.

**The guard.** The controller is idle when:
- no drive is selected;
- its DMA is off;
- DSKSYNC is not zero;
- its shift register already holds zero.

An idle controller's event only shifts zeros in, writes a zero byte into its FIFO and advances the rotation delay: it cannot raise an
interrupt or touch memory.

**How the events are held back.**
- The events after one are taken off the scheduler, up to 64 of them, and never past the host frame's end (the first instruction after
  line 0's HSYNC) as it is known when they are taken. A frame cut short later can still end with some held back; the events that are
  due run before any quick state is taken (see "quick states on a frame cut short" below).
- One event is scheduled at the time of the last of them. The others run in order when it comes, or when something could see the
  controller first: its registers (DSKLEN, DSKDAT, DSKBYTR, DSKSYNC), the CIA-B port that selects a drive and its motor.
- Their times are those vAmiga's own arithmetic gives: each event runs on the first colour clock at or after its trigger, and the next
  is scheduled from there.
- A barrier inside Agnus's events (a Copper or delayed write) runs the events strictly before its colour clock. A CPU access runs those
  of its own clock too, as vAmiga's order is.

This is done through vAmiga's adaptation (MPL-2.0 edits). Paula stays emulated, and nothing is specialised from a game.

**Proof.**
- The display self-test now compares each scenario with every disk event on vAmiga's scheduler (`--per-slot` turns the catch-up
  off). Its programs also read DSKBYTR, write DSKSYNC (zero now and then) and DSKLEN, and select drive 0 and its motor through CIA-B.
- 52 scenarios of 4 frames: 167,806 disk events held back in 2,725 batches (420 of them run at a barrier), every instruction's and
  every frame's record equal (Paula's and Agnus's snapshots included).
- One held-back event lost on purpose is seen in 52 of 52 scenarios.
- Two first versions were caught by these records:
  - one added the delay to the trigger instead of to the colour clock the event runs on;
  - one let a batch run past the host frame's end.
- Lotus 2's native game and the reference player built with this change give the same trace as the build before step 1 on every one
  of 3,600 frames of a racing route.
- The reference player gives the same trace as before on Rick Dangerous, Lemmings and Civilization (main routes, 3,600 frames each).
- On those four games the disk events left on the scheduler go from 1,269 to 21 per frame.

**What it brings:** timed together with the idle sprite slots below (one quiet-PC pass for all of checkpoint 3).

**Hot path:** this is one.

**What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds. The held-back events that are due run before a state is
taken.

## Commodore Amiga: the idle sprites' slots left out of their lines (after 1.7.3, stage 7 checkpoint 3b)

**What changes.** With sprite DMA on, Agnus has two slot events per sprite on every line (16 per line), even when no sprite is shown.
On Lotus 2 that is 4,563 events per frame with 16 fetches. On Civilization it is 4,321 events with 73 fetches, a third of all its
events.

**The rule.** A sprite's cycle does nothing on a line where its DMA is off and that is not its stop line. Both are known at the line's
start, since the sprite's DMA state is updated at $E1 of the line before.
- Such a sprite's two events are left out of the line's schedule.
- A write to its SPRxPOS or SPRxCTL puts it back for the rest of the line. vAmiga always applies such a write by a register-change
  event, before the slot events of its colour clock.
- Line 0, where the host frame ends, keeps every event, and so does AGA.

This is done through vAmiga's adaptation (MPL-2.0 edits). Agnus stays emulated, and nothing is specialised from a game.

**Proof.**
- The display self-test compares each scenario with every sprite slot on the schedule (`--per-slot`, or `--spr-off` alone).
- 52 scenarios of 4 frames: 892,295 sprite slot events left out, every instruction's and every frame's record equal. (An earlier
  count, 892,752, counted some twice; see "quick states on a frame cut short" below.)
- An armed sprite taken for idle on purpose is seen in 51 of 51 scenarios that show sprites.
- Lotus 2's native game and the reference player built with checkpoints 3a and 3b give the same trace as the build before step 1 on
  every one of 3,600 frames of a racing route.
- The reference player gives the same trace on Rick Dangerous, Lemmings and Civilization (main routes, 3,600 frames each).
- First-read conversions with the real command line, checkpoints 3a and 3b together (11 November 2026): Lotus 2, Rick Dangerous,
  Lemmings and Civilization (with the player's Kickstart 1.3).
  - Two routes of 3,600 frames each, every frame equal to the fresh reference; the compressed copy, the resload log and the quick-state
    restart are equal too.
  - 0 instructions interpreted, but Civilization's 19, which are all the Kickstart's, as in 1.7.2.

**What it brings** (checkpoint 3 as a whole, idle disk and idle sprite slots together): the machine's time per frame, measured
in one quiet-PC pass on 11 Nov 2026 (Windows, one core, native game, 3 rounds of 2,400 frames, median of the rounds):

| Game | Before Agnus/Denise step 1 | Steps 1-3 (1.7.3) | Plus checkpoint 3 | Against steps 1-3 |
|---|--:|--:|--:|--:|
| Lotus 2 | 2.529 ms | 1.748 ms | 1.516 ms | -13.3 % |
| Rick Dangerous | 2.157 ms | 1.368 ms | 1.355 ms | about -1 % (inside the spread) |

- Lotus 2 gains in each round (-12.2 %, -13.8 %, -13.3 %); the rounds spread by 1.5 % at most.
- Rick Dangerous has no sprite event to leave out, and its gain is smaller than the spread of its rounds (up to 4.9 %).
- This is machine time only. It says nothing about physical latency.

**Hot path:** this is one.

**What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console.

**Quick states:** the Amiga's key moves; the line's set of idle sprites is derived, never saved (line 0 has none).

## Commodore Amiga: quick states on a frame cut short, and the idle sprites counted once (after 1.7.3, stage 7)

**What changes.**
- **Before a quick state is taken,** the idle disk controller's held-back events that are due now run, and the next one is scheduled.
  A batch is bounded by the frame's end as known when it starts. A frame cut short after that can end with events held back: VPOSW
  clearing LOF, or BEAMCON0 switching from PAL to NTSC. A snapshot keeps none of those events.
- **After a quick state is loaded,** stage 7's derived state of the timeline that was left goes: the disk controller's held-back
  events, the line's idle sprites, and the mark of Agnus's event loop.
- **The count of idle sprite slot events** counts each slot once, when its line ends. A mid-line DMACON change or a sprite woken
  inside its line used to count some slots twice. This changes the report's counter only, not the machine.

This is done through vAmiga's adaptation (MPL-2.0 edits) and the session. Agnus and Paula stay emulated.

**Proof.**
- The display self-test runs two new scenarios: every frame starts long and PAL and is cut short near its end, through VPOSW in one
  and BEAMCON0 in the other. A quick state is taken at the end of frame 1 and loaded back at the end of frame 3.
  - Every record is equal to the run with every event on vAmiga's scheduler. Held-back events were run at a frame's end 5 times in
    each scenario.
  - Leaving out the run before the snapshot, or the clearing after the load, is seen in both scenarios.
- The 52 random scenarios are unchanged: every record is equal, with no frame ending with events held back.
- Stage 7's model in shadow on wave 1 (Lotus 2, Rick Dangerous, Lemmings and Civilization, 3,600 frames each, the reference player):
  0 differences, and every figure is the same as before this change.
- Lotus 2 converted by the real command line: two routes of 3,600 frames, each frame equal to the fresh reference, with 0
  instructions interpreted. The compressed copy and the quick-state restart are equal too.

**Hot path:** no. The run before a state is taken and the clearing after a load happen only at a quick state; the count of a line's
idle sprite slots happens once per line.

**What moves:** vAmiga's adaptation, the session, and so the Amiga's game stamp. No other console moves.

**Quick states:** the Amiga's key moves. A state of an earlier build is refused, as between any two Amiga builds.

## Commodore Amiga: the Blitter served alone on its colour clock, tried and reverted (stage 7 checkpoint 4)

Not in any build. Checkpoint 4 served the Blitter's event alone when no other slot could be due on its colour clock. Its checks were
equal to vAmiga's. On a quiet PC (12 Nov 2026), it timed 2 to 3 % slower than checkpoint 3 on Lotus 2 and on Rick Dangerous, so it was
reverted. Nothing of it remains, and no stamp moved.

## Commodore Amiga: checkpoint 3's counters in the conversion report (after 1.7.3, stage 7)

**What changes.** Each route's `final_checks.agnus_denise` now also counts what checkpoint 3 did:
- `disk_idle_batches`, `disk_idle_batches_at_event`, `disk_idle_batches_at_barrier` and `disk_events_held_back`, for the idle disk
  controller;
- `sprite_slot_events_left_out`, for the idle sprites.

The `hardware_devices` details of `agnus_copper` and `paula` say what these are. Agnus and Paula stay emulated. A report of an earlier
build reads 0 for each of them.

**Hot path:** no. The counters existed already; the session only writes them at the end of a run.

**What moves:** the Amiga's game stamp (the session and the conversion module); no other console.

**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Neo Geo: the code the reference runs could not keep is counted and reported (after 1.7.3)

**What changes.** The reference runs of a Neo Geo conversion keep at most 4,096 variants of work-RAM 68000 code and 4,096 variants of
Z80 code (`RR_NG_VARIANT_CAP`, `native/neogeo_reference.h`). Past that, a note was dropped without a trace: the Z80 side had no counter,
and the 68000 side wrote a flag (`m68k_ram_observations_truncated`) that nothing read. Now:
- the executable's reference report writes `variant_cap`, `m68k_ram_variants_dropped` and `z80_variants_dropped` beside the flag;
- the conversion report has a `native_discovery` record: the cap, the same figures per route, their maximum over the routes (never a sum),
  the flag read from every route, and `observed_code_dropped`;
- when something was dropped, the conversion says so in its log. Dropped code is not translated: a run that reaches it uses the counted
  interpreter fallback, shown as before in `final_checks` and in the game.

A dropped count is a number of notes, not of distinct variants: a variant met again counts again. No game of the panel reaches the cap
(the most observed 68000 variants are 565, on Matrimelee, and 1 Z80 variant on every set read), so the counters read 0.

**What it does not change.** The code generated for the game: the counters sit after the point where a variant is kept or dropped, and
the generators are untouched. A report of an earlier build has no `native_discovery`.

**Hot path:** no. The counter is a store on the path that already drops a note, at conversion time only (the reference runs).

**What moves:** the Neo Geo game stamp (`native/neogeo_main.c`, `neogeo_reference.c`, `neogeo_reference.h` and `retrorecomp/neogeo_conversion.py`
are Neo Geo files); the CPS-1, CPS-2 and X68000 stamps and the two generator pins do not (`neogeo_codegen.py` is not edited), nor does the
Neo Geo quick-state key (it hashes `neogeo_build`, `neogeo_codegen` and `neogeo_z80`, none edited).
## Super Nintendo: the rows the RAM-code limit leaves out are counted (after 1.7.2, 1.7.3 item of the silent caps)

The three places of `supernintendo.py` that cut the RAM-code tables at `RAM_VARIANT_LIMIT` (16,384 rows) left no trace: the merged read of the
guarded RAM variants, the merged read of the RAM opcode guards, and the merge a conversion writes back into the library (`native-ram.json`). Each keeps the
lowest addresses and drops the rest, as before; what is new is that the number of rows there were is kept (`supernintendo.row_counts(rom)`, per kind: `ram_variants`,
`ram_opcodes`, their `_own` forms and `library_merge`). The conversion report of a Super Nintendo game carries it as `library_rows` (`{kind: {limit, rows,
dropped}}`), and the conversion log says so when a kind left rows out. The line printed when a run met more distinct RAM instructions than the native table keeps
(`ram_observation_overflows`) no longer says those instructions stay on the counted interpreter: since 1.6.7 they run from their live opcode, compiled and counted as
compiled and not observed. **What a game does is unchanged**: nothing that is read, kept or generated differs (counters only).

How near the limit is: two conversions at the standard level from an empty library (Dirt Racer, Star Fox 2 (USA), the two cartridges the shared base holds the most
RAM-code rows for) read 7,827 and 8,517 rows (48 % and 52 % of the limit, 0 left out); native equal to the reference on both routes, the compressed copy equal to it, 0
interpreted opcodes of the 65816 and the SPC700. The shared record of the base is nearer: Dirt Racer 13,354 rows of `ram_opcode_refs` of 16,384 (82 %), Godzilla - Kaijuu
Daikessen 12,330, the two Star Fox 2 11,974 and 11,469, of 314 records (four above 8,192). *Raising the limit:* the local limit is two constants (`RAM_VARIANT_LIMIT` and
`RR_SN_RAM_VARIANT_LIMIT` of `native/snes_native_steps.h`, a power of two for the hash of `snes_backend.c`; 32,768 would add 192 KiB of static arrays to the game, and moves
the Super Nintendo's quick-state key), but it is not the limit that binds: what travels is bounded by the field caps of `path_profiles.LEGACY_FIELDS` (`ram_refs` and
`ram_opcode_refs`, 16,384 rows each), which the exchange validates and from which the site's limits are generated (`tools/build_web_limits.py`); a record over a cap is refused
by a converter that does not know the new one and by the site until its limits are deployed. So a raise is a format and site decision, not a one-line change; none is made here.

Stamps (`compilation_inputs.role_stamps`, the tree of `e4ec565b` against this one): the game stamps of the Super Nintendo move, and of the Mega Drive, the Neo Geo, the CPS-1, the
CPS-2, the PC Engine and the PlayStation with it (`console16.py` is a game input of those machines: it holds the report key and the log line; `supernintendo.py` is the
Super Nintendo's); no host and no build stamp moves, and the quick-state key does not (no native file and no pinned revision changes).

## Atari ST: the disks in the order their names mean, and a program chosen among several (1.7.3)

**What changes.** Two rules of the conversion, both read from names and from the root directory of disk 1, nothing run:
- **Disk order.** A ZIP's disks were taken in the alphabetical order of their member names, which put the wrong disk first when the boot disk is not the first by name
  (Battle Chess: the "Animation Disk" before the "StartUp Disk"; The Chessmaster 2000: "(Games Disk)" before the disk without a label; Mean 18: the "Famous Courses" disks before the
  "Program Disk"). `retrorecomp/atarist_disk.py` now puts them in disk order: the disk without a label and the boot disks (Boot, StartUp, Program, Main, Loader) first, then the numbered
  ones by number or letter (Disk 1, Disk A, Side B, Reel 2, Volume II; Disk 10 follows Disk 9), then the disks that only have a name; a name without brackets is read from its end
  (`game2.st`, `game_b.st`). Of the 79 multi-disk ZIPs of the library tried (names only), exactly those three change order.
- **Several programs on disk 1.** When disk 1 has no `AUTO` folder, the desktop autostart took the only program of the root and nothing otherwise. It now also takes, among several, the
  one program whose name is a word of the game's title (`CRICKET.PRG` for Championship Cricket), or else the only one that is not a utility by a short list of names (setup,
  config, format, read, view, help, backup, copy, unpack...). Two programs that fit, or none, leave the choice to the player, who opens the program at the desktop; `desktop_autostart` in the
  report gives the program, the `candidates` of the root, the `rule` (`only-program`, `title-word`, `only-non-utility`) and the `reason`. A lone program is started as before.

**Library.** Of the 18 ZIPs that stopped on the desktop in the census of 12 November 2026, six now start their program (Battle Chess, The Chessmaster 2000, Championship Cricket, Logical,
Outcast, Rody et Mastico III) and twelve are left to the player (Backgammon Royale, Chess Simulator, Conquests of Camelot, Mean 18 and Mercenary have several programs no rule picks; Battle
Probe, Kick Off 2 - Winning Tactics, Leader Board, Metro-Cross, Pac-Mania, Trailblazer and World Class Leader Board have no program at their root). The decision of the other 257 ZIPs is the one it was.

**Proof** (Windows, EmuTOS 1.4, Standard level, 3,600 frames on two routes, headless; every route of the native game and of its packed copy equals the fresh reference, and the saved state
continues the run): The Chessmaster 2000 (disk order, then `CMASTER.PRG`) reaches its title, which shows an alert from the game ("Lost my BIG pieces!"); Battle Chess (`CHESS.TOS`, the
StartUp disk first) reaches a screen of its own, a prompt that looks like its manual protection; Championship Cricket (`CRICKET.PRG`) reaches a match; Outcast (`OUTCAST_.PRG`) reaches
its title; Mercenary (two programs that both fit) stops on the EmuTOS desktop and the report says why. These are first screens on the tested routes, not played games.

**Hot path:** no. **What moves:** the Atari ST's game stamp (`e6f3506a6be7` to `3b3a9b68ef52`, the conversion modules `atarist.py`, `atarist_disk.py` and `atarist_conversion.py`); its host stamp and its
build stamp do not, and no other machine moves. A game of this machine converted before is reconverted in full on its next conversion; an export keeps playing as it did. **Quick states:**
no native file of the session or the player changes, so the format of a state is the one of before.

## Exports of 1.7.1 in 1.7.2

1.7.2 is the release after 1.7.1 (published on 8 November 2026). This section is the index of its changes, one line per section below (or per machine page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 10 November 2026.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Sony PlayStation: two discs at once no longer fetch Beetle PSX together](#sony-playstation-two-discs-at-once-no-longer-fetch-beetle-psx-together-172) | the PlayStation only (`920cf82497a6` to `4a3b197254a5`) | none | no key moves: the PlayStation key hashes the Beetle adaptation and the session files, which do not change |
| [PC Engine / TurboGrafx-16: the larger capture format, shared paths, the walk repair, and the exit from the experimental status](#pc-engine--turbografx-16-the-larger-capture-format-shared-paths-the-walk-repair-and-the-exit-from-the-experimental-status-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [PC Engine / TurboGrafx-16: a Backup RAM beside the game](#pc-engine--turbografx-16-a-backup-ram-beside-the-game-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [Atari ST: Hatari's timer D patch on, and the native code compiled better](#atari-st-hataris-timer-d-patch-on-and-the-native-code-compiled-better-172) | the Atari ST only | none | the Atari ST key moves, as between any two Atari ST builds |
| [Atari ST: a write after a seek without verify finds its sector](#atari-st-a-write-after-a-seek-without-verify-finds-its-sector-172) | the Atari ST only | none | the Atari ST key moves, as between any two Atari ST builds |
| [Atari ST: Hatari's code specialised per opcode, and chained](#atari-st-hataris-code-specialised-per-opcode-and-chained-172) | the Atari ST only | its host stamp, through its notice (`licenses/hatari.md`) | the Atari ST key moves, as between any two Atari ST builds |
| [PC Engine / TurboGrafx-16: the play route answers the game](#pc-engine--turbografx-16-the-play-route-answers-the-game-172) | the PC Engine only (each section gives its step) | none | the PC Engine key moves (the bridge and the engine revision change) |
| [Commodore Amiga: the icon's DATA ToolType names the data folder](#commodore-amiga-the-icons-data-tooltype-names-the-data-folder-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a file the game saves reaches the disk whole or not at all](#commodore-amiga-a-file-the-game-saves-reaches-the-disk-whole-or-not-at-all-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a conversion that fails with remembered data is tried again without it](#commodore-amiga-a-conversion-that-fails-with-remembered-data-is-tried-again-without-it-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the report and the F2 menu say less than they did](#commodore-amiga-the-report-and-the-f2-menu-say-less-than-they-did-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the keyboard's power-up handshake is over when a slave starts](#commodore-amiga-the-keyboards-power-up-handshake-is-over-when-a-slave-starts-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the player's own record](#commodore-amiga-the-players-own-record-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the keyboard reaches a game that never enables its interrupt; F1-F4 on the long route](#commodore-amiga-the-keyboard-reaches-a-game-that-never-enables-its-interrupt-f1-f4-on-the-long-route-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a long route at the extended level](#commodore-amiga-a-long-route-at-the-extended-level-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the Blitter's copy blits, specialised routines by shape (recompilation stage 6)](#commodore-amiga-the-blitters-copy-blits-specialised-routines-by-shape-172-recompilation-stage-6) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a sweep beyond the routes (recompilation stage 4)](#commodore-amiga-a-sweep-beyond-the-routes-172-recompilation-stage-4) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: 68000 forms translated to C (recompilation stage 3)](#commodore-amiga-68000-forms-translated-to-c-172-recompilation-stage-3) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the instructions' lengths come from Moira, and no recompiler is needed](#commodore-amiga-the-instructions-lengths-come-from-moira-and-no-recompiler-is-needed-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: Moira's code specialised per opcode, and chained (recompilation stage 2)](#commodore-amiga-moiras-code-specialised-per-opcode-and-chained-172-recompilation-stage-2) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: a debugging recorder off, the resload traps without breakpoints (recompilation stage 1)](#commodore-amiga-a-debugging-recorder-off-the-resload-traps-without-breakpoints-172-recompilation-stage-1) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: the guard compares what the CPU has latched](#commodore-amiga-the-guard-compares-what-the-cpu-has-latched-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: Kickstart words a slave patched run native too](#commodore-amiga-kickstart-words-a-slave-patched-run-native-too-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| [Commodore Amiga: an archive with an intro or editor slave beside the game](#commodore-amiga-an-archive-with-an-intro-or-editor-slave-beside-the-game-172) | the Amiga only (each section says so) | none | the Amiga key moves, as between any two Amiga builds |
| Computers: full guest typing gives F1 to the guest, and the help page names Ctrl+Alt+K ([CONTROLS.md](CONTROLS.md); no section of this page) | none | the host stamps of the X68000, the Amiga and the Atari ST (the shared computer adapter and their own) | no key moves |
| Atari ST: states that continue with their sound, disk writes kept beside the state, long routes, the panel ([ATARI_ST.md](ATARI_ST.md); no section of this page) | the Atari ST only | none | the Atari ST key moves |
| Tests: the window and reconvert tests no longer write the player's real `Export/datas` (no section of this page) | none | none | none |

Taken together (`compilation_inputs.role_stamps` of the seventeen profiles, the tree of `v1.7.1` against `main`, Windows, Python 3.14): **the game stamps of the PC Engine,
the Amiga, the Atari ST and the PlayStation move**, **the host stamps of the X68000, the Amiga and the Atari ST move**, and **no build stamp moves**. Every other machine is
unchanged.

| Machine | Game stamp (v1.7.1, now) | Host stamp (v1.7.1, now) | Build stamp |
| --- | --- | --- | --- |
| Master System | `63c93fcb0264` (same) | `62a7e9f65d83` (same) | `fe2d99b3cd5e` (same) |
| Game Gear | `70eafce5937a` (same) | `fa5e7fa22b05` (same) | `f5671c38cf26` (same) |
| Game Boy | `b218f94d2c75` (same) | `2a0942586a4a` (same) | `819a054ad881` (same) |
| NES | `af5a3a096738` (same) | `39c36bfa861a` (same) | `8e0941f93b43` (same) |
| Mega Drive | `ed3a49ab59a8` (same) | `8f4324fbcb85` (same) | `9615ff2e96c8` (same) |
| Super Nintendo | `064bd8544d76` (same) | `d35383911455` (same) | `3f0a58ad3c7c` (same) |
| Neo Geo | `b45ca489a2c9` (same) | `f1fde4b7a652` (same) | `110349f043bd` (same) |
| X68000 | `107b51de2145` (same) | `55ac9db11502`, `be9dae27aacf` | `5903c0449429` (same) |
| CPS-1 | `28dd85714948` (same) | `0220746ac9ad` (same) | `2782cd370f91` (same) |
| CPS-2 | `cb7b5d304275` (same) | `7889559074ad` (same) | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `ebcbc2a403cd`, `aa7913b68d39` | `3da7363bd893` (same) | `66d912662e5c` (same) |
| Game Boy Advance | `1658c523234f` (same) | `7b18d021f143` (same) | `6b70933a9b0a` (same) |
| Amiga | `ba01a0a7e76e`, `6854eee76d0e` | `b264a452712e`, `8ca835ce1027` | `92ca8a0c142c` (same) |
| Atari ST | `fa09328f914f`, `e6f3506a6be7` | `f8a69516f53e`, `3b7c6f50488a` | `54b75964897d` (same) |
| Nintendo 64 | `ec87144eb331` (same) | `3c4f6ccca458` (same) | `4f6fedf926c7` (same) |
| Adventure (ScummVM) | `42dfc172e91c` (same) | `82088d749a09` (same) | `05417bbcea96` (same) |
| Sony PlayStation | `920cf82497a6`, `4a3b197254a5` | `5dbdb5df79ca` (same) | `b6c9cf73b176` (same) |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.1 of the PC Engine, the Amiga, the Atari ST and the PlayStation is
converted again, from its qualified paths, once, when the player updates**, and the window offers it; it is not a quick host-only upgrade. **An X68000 export is upgraded**: its
host stamp alone moves, so it is rebuilt from its paths with no rediscovery. The exports of the other machines are not touched.

**Quick states.** The **PC Engine key moves** (it hashes the engine revision and the bridge files `pce_machine.cpp`, `pce_machine.h` and `pce_main.c`, which change), and the
**Amiga and Atari ST keys move** (each follows its machine's build, which changes): a quick state of 1.7.1 of those three machines is refused cleanly (no compatibility key is
carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The **PlayStation key does not move**: its game stamp moves for the setup gate, but the key hashes the
Beetle adaptation and the session files, which do not change, so a PlayStation state of 1.7.1 loads in the rebuilt export. The X68000 key hashes none of the files that changed (the
change is in the host adapter). The other machines are not rebuilt. **Cartridge saves** are kept on every machine, and the PC Engine's new Backup RAM file starts formatted.

## Sony PlayStation: two discs at once no longer fetch Beetle PSX together (1.7.2)

The pinned Beetle PSX checkout in `.deps` is shared by every disc, but only the game's own work folder was locked. Two discs converted at once on a fresh `.deps` could both clone it. Fetching it now goes through the shared setup gate, as the other machines' setups do. Nothing changes in the machine or in a game.

**What moves:** only the PlayStation's game stamp: game `920cf82497a6` to `4a3b197254a5` (`psx_beetle.py`). Its host and build stamps and every other console's stamps do not move. A PlayStation export of an earlier version is rebuilt when it is upgraded, to the same machine.

## PC Engine / TurboGrafx-16: the larger capture format, shared paths, the walk repair, and the exit from the experimental status (1.7.2)

**Engine pin** `81b5c231` to `6bb848e8` (pcenginerecomp, ABI 29). A card that needs more than 65,536 instruction identities gets the engine's larger capture format (up to 1,048,576, past it left out and counted): Street Fighter II' Champion Edition now runs 0 interpreted instructions on its three routes, where it ran 19.3 %, 33.5 % and 74.7 % interpreted; its game is 25.4 MB packed and its conversion takes about 34 minutes on its own. **Shared paths**, numbers only, in the experimental tier of the base: a record is made from a passed conversion's captures, and a conversion that receives paths gives them to the engine as declared roots, never as captures ([PC_ENGINE.md](PC_ENGINE.md#7-shared-paths)). **The walk repair:** where the play walk left a game paused, one more Run press is kept if the game answers (Gradius at frame 7,811). **The fetch of the engine** goes through the shared setup gate, so two cards at once on a fresh `.deps` no longer clone it together. **Status:** supported, on the owner's decision of 10 November 2026 after playing the fifteen exports of this tree ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). **The limit he saw:** native code covers what the conversion's own routes ran (about one minute of play and five minutes of pseudo-random walk), not the whole game; code past that runs through the interpreter, counted and shown in the game. The routes are thinnest on Boxyboy (after Start it waits on a screen the walk does not confirm), Military Madness, Space Harrier and Santatlantean (their long walks stall on a prompt or a loop); the owner saw it on Boxyboy after Start. A PC Engine game keeps no player's record yet, so the code a player reaches is not made native at the next conversion. The conversion report's `runtime_feedback.recording_default` reads `true` for the PC Engine, but no PC Engine game records anything: its F12 line says the record is off and stays off. 1.7.3 corrects the field together with the record itself. Evidence: the 15-card panel on Windows and on a Debian 13 PC, 45 of 45 routes equal ([PC_ENGINE.md](PC_ENGINE.md#the-panel-of-the-release-tree-9-november-2026)).

**Hot path:** the new pin calls a bus observer on every read and write of the CPU (no observer is set in a game). **Speed**, measured on a quiet PC, 10 November 2026, one core, the headless attract route with no input, the best of three runs of 2,400 frames, host time only: against games built with the 1.7.1 pin `81b5c231` (no published 1.7.1 PC Engine export exists to measure), the frame cost is 1.09x on Blazing Lazers (4.44 to 4.84 ms a frame) and 1.04x on Street Fighter II' CE (4.49 to 4.69 ms; its old game ran 19.3 % interpreted on that route), and Street Fighter II' CE starts in 1.40 s instead of 0.21 s (its game is 25.4 MB). The bus observer of the new pin is ruled out as the cause: the same module of Blazing Lazers built with the observer compiled out costs the same (4.81 against 4.76 ms a frame, within noise). Where the rest comes from (the module the new engine emits, the rest of its runtime, the Backup RAM) is not measured apart. **What moves:** only the PC Engine's game stamp: game `4d4c66fc090c` to `aa7913b68d39` (`native/pce_machine.cpp`, `native/pce_machine.h`, `native/pce_main.c`, `pce_conversion.py`, `pce_build.py`, `pce_knowledge.py`, `systems/pc_engine.py`); its host and build stamps and every other console's stamps do not move. **Exports:** a PC Engine export of an earlier version is rebuilt when it is upgraded; its Backup RAM file is kept. **Quick states:** refused cleanly, as after any change of the bridge.

## PC Engine / TurboGrafx-16: a Backup RAM beside the game (1.7.2)

A game can now keep the 2 KiB of the console's backup unit between runs. Bank `$F7` is mapped as plain RAM by our bridge, on the same engine pin and with no change to the engine. With no file it starts with the file system's header, a written choice ([PC_ENGINE.md](PC_ENGINE.md#6-saves)). The file is `datas/saves/<game>-<card>.rrsram`, beside the other machines' saves; a damaged or wrong-size file is set aside as `.unusable-N` and never blocks a game. Boxyboy, which showed "FILE NOT CONNECTED. COPY THE PASSWORD", now starts and saves.

**What moves:** only the PC Engine's game stamp: game `750e062dca69` to `4d4c66fc090c` (`native/pce_backup.c`, `native/pce_machine.cpp`, `native/pce_main.c`, `pce_conversion.py`, `pce_build.py`, `systems/pc_engine.py`). Its host and build stamps and every other console's stamps do not move. A PC Engine export of an earlier version is rebuilt when it is upgraded. It has no save to lose: it starts formatted. Its quick states are refused cleanly, as after any change of the bridge. Tool, no stamp: `tools/pce_mame_compare.py` gives MAME the same formatted memory.

## Atari ST: Hatari's timer D patch on, and the native code compiled better (1.7.2)

TOS starts the MFP's timer D at a very high rate with its interrupt off, one event every couple of instructions, which is why the chains stayed short. This machine now runs Hatari's own option (`hatari_timerd`): when the code starting the timer is in the TOS's addresses, Hatari starts it far slower, and answers TOS the old value. **This changes the machine, on purpose, on the owner's decision of 9 November 2026: a game that uses this timer as TOS left it sees another rhythm, or another value in its data register.** No fidelity is claimed for it; a game that programs the timer itself is not touched; Hatari's list names Exterminator, The Seven Gates of Jambala and Super Sprint as needing the option off, and none of the ten panel games relies on it ([ATARI_ST.md](ATARI_ST.md#5-known-limits)).
The reference, the native game and its packed copy run the same machine: the frame comparison cannot see the patch, so each run's report says Hatari has it set, a conversion refuses a run without it, and the conversion report states it (`machine.timer_d`). `tools/atarist_hardware_check.py` measures it from RAM and from the ROM.
Compiled better: the test between two instructions inline in each instruction, the fault exits out of the hot path, link-time optimisation of the session and the native code with the player (not of Hatari's core); each changes no statement. The executable grows by about 12 % (Bomb Jack).
Proof: vectors, and all 45,814 forms against the table's handlers on random states, 0 differ, with LTO. The panel at the thorough level: all 40 routes equal to the fresh reference, the packed copy and the state continuation too. The three games tried with the player's TOS 1.04 too. On a Debian 13 PC with GCC and LTO, the panel at the Standard level: 20 of 20 traces byte equal to Windows.
An estimate on a loaded PC, headless, no hashing, host cycles of 3,000 frames. The option alone, off over on: on EmuTOS 1.30 to 1.70, on TOS 1.04 1.56 to 1.80, on three games. Against the export before this change, on the panel: 1.18 to 1.67. The native code over the table: 1.21 to 1.47. Not a timing.
**Hot path:** the chain's test and next are now inlined at each instruction; the rest is unchanged. **What moves:** the Atari ST's game stamp and the Hatari options of its session; no other machine. **Exports:** games from before keep their machine until they are converted again. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds.

## Atari ST: a write after a seek without verify finds its sector (1.7.2)

Hatari's read commands load the track under the head; its write command did not, as an MFM write only ever ended in "record not found" before Retro-Recomp kept what a game writes. A TOS that seeks without verify, as EmuTOS does, then looked for the sector on the track last loaded:
The Lurking Horror's save answered "Failed." on EmuTOS. It now saves on EmuTOS and TOS 1.04, and restores in a new process, on Windows and a Debian 13 PC (`tools/atarist_saves_game.py`). **Exports:** a game that saved on EmuTOS keeps what it has; one
whose save failed had written nothing. **What moves:** the Hatari adaptation, so the Atari ST's game stamp; no other machine.

## Atari ST: Hatari's code specialised per opcode, and chained (1.7.2)

A native step was a call to Hatari's own handler behind a page-table look-up and a comparison of every word in memory, which made it slower than the interpreter (14 to 29 % on a loaded PC). Now a *form* is
Hatari's handler, its generated text compiled again with the opcode as a literal, on one shared copy of Hatari's bus path without its pointers, and each observed instruction (one per address
and opcode) goes straight on to the instruction it knows comes next. This is Hatari's code specialised, not a translation: same bus accesses, same cycles. A form reads its extension words on the bus, so
the guard is the opcode the CPU has latched and a word rewritten in memory needs no tracking; an instruction with the same opcode and other extension words now runs native where it was interpreted. The 68000 loop
sees what it saw: a chain stops, untouched, whenever something is due after an instruction (a clock event, an MFP update, a special flag, an interrupt level above the mask). Chains are short: the MFP's timer D, as TOS
programs it, makes an event every few instructions, about 2 instructions per entry on Bomb Jack (`chain_entries` in the report).
Vectors: every native form equals the interpreter on the vectors that have one, and with `tools/atarist_vector_selftest.py --all-forms` each of the 45,814 forms equals the table's handler on eight random states (366,512 runs, 834,101 bus accesses compared in order and clock, an interrupt line changing during the instruction, through the bank's functions and on direct RAM). The vectors found ADDX.L D6,D6 wrong with a literal opcode: the forms are compiled
with `-fwrapv`, and the same check without it finds that family. The whole panel at the thorough level: every frame of all 40 routes equal to the fresh reference, the packed copy and the state continuation too.
An estimate on a loaded PC, headless, no hashing, host cycles of 3,000 frames, table over native: Bomb Jack 1.05, Turrican II 1.09 to 1.17, Indiana Jones 0.98 to 1.00, Kick Off 2 1.04, Lethal Xcess 1.20; not a timing.
Licence: no text of `m68k_decoder.h` is in a game any more, so the notice of segagenesisrecomp leaves the exports; the decoder still runs during the conversion.
**Hot path:** the look-up and the word comparison are gone from the instructions inside a chain; two calls of one shared test per instruction instead, one count per entry. Handlers keep their pointers on the interpreted path. **What moves:** the
Atari ST's game stamp, and its host stamp through its notice (`licenses/hatari.md`); no other machine. **Quick states:** the Atari ST's key moves, as between any two Atari ST builds. The window title and the note "not fully recompiled" are unchanged.

## PC Engine / TurboGrafx-16: the play route answers the game (1.7.2)

The first panel pressed Run at fixed frames, and on 7 of 18 cards the play route then stayed on a menu, a story, a sound test or a password screen while every check passed. The conversion now tries 1, 2, 3, 4 and 6 Run presses, walks with the directions only for 900 frames (so a password screen is not typed into), keeps the variant whose walk showed the most pictures that the same frames without input never show, and presses Run twice now and then to leave stories and prompts (`pce_conversion.start_candidates`, `reach`, `choose_start`). Quick states are checked with 13 damaged states (all refused and left as they were) and a missing one (refused, creates nothing). The line printed when a game is ready says "no interpreter on the routes played" instead of "native code only", and the profile's scope note says a converted game is built for two players.

**What moves:** only the PC Engine's game stamp (`pce_conversion.py` and `systems/pc_engine.py` are inputs of it): game `750e062dca69` (it was `ebcbc2a403cd` on main); its host and build stamps and every other console's stamps do not. A PC Engine export of an earlier version is rebuilt when it is upgraded: the routes it was checked on change, the game does not. Tools only, no stamp: `tools/pce_mame_compare.py` (the delivered game against MAME 0.289, a private oracle), `tools/pce_route_captures.py` (pictures along each route) and the native vector tier widened on request (`--per-opcode 250`). Evidence: [PC_ENGINE.md](PC_ENGINE.md#the-extended-panel-9-november-2026).

## Commodore Amiga: the icon's DATA ToolType names the data folder (1.7.2)

An install whose slave leaves `ws_CurrentDir` empty and whose icon says `DATA=data` (Drakkhen, NTSC, French, German and the plain one) was read with its
data folder at the archive's top: the `Disk.N` images in `data/` were not found and the game stopped at boot with "DiskLoad failed with DOS error 205
(Disk.1)". The icon (`<slave>.info`, read the way `CUSTOM1` to `5` are) is now asked for `DATA`; when it names a folder of the archive that holds files, that is
the data folder, as WHDLoad lets it replace the slave's `ws_CurrentDir` (a ToolType in parentheses is off; a name that matches nothing leaves the earlier rule).
Run headless with the interpreted machine for 1,500 frames, the four Drakkhen installs reach the end with picture and sound (non-black frames 1,309 to
1,340 of 1,500), where the tree before stops at frame 135 (NTSC). Any other install whose icon carries a `DATA` ToolType (about 14 of the maintainer's library)
may now find its files where it did not; none of them was run again. **What moves:** the Amiga's game stamp for those installs only (the install's files
change); the code is `retrorecomp/amiga_whdload.py`. No other console.

## Commodore Amiga: a file the game saves reaches the disk whole or not at all (1.7.2)

What an install saves (`resload_SaveFile`) goes to `datas/games/amiga-<identity>/saves`. The write went through a temporary file but did not look at the
flush and the close, so a disk that took only part of the bytes could still replace a good save with a short one and tell the game it worked; the game's own view
of the file changed before the disk was asked. Now the temporary file replaces the old one only when every byte is flushed and closed, the game is told the save
failed (disk full) when anything refused, its view of the file and the file on disk stay as they were, and no temporary file stays behind. A name that would
leave the save folder (absolute, a volume or drive colon, a backslash, `.` or `..`) is refused with "write-protected" instead of being written elsewhere;
deleting follows the same rule. On 5th Gear (8 November 2026), with a folder where the file goes so that the replacing rename fails, the save was refused, the run stopped at it
with DOS error 221 as WHDLoad does for a slave that sets NoError, the folder stayed and no temporary file was left. The helper is `native/amiga_machine/amiga_savefile.h` and is checked by an authored program (`tests/test_amiga_resload.py`:
names, a first write, a replacement, a folder in the file's place, a file in the folder's place, a stale temporary). A disk that is really full cannot be made in
that test; a refused rename is. **What moves:** the Amiga's game stamp (`amiga_session.cpp`); no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: a conversion that fails with remembered data is tried again without it (1.7.2)

The library remembers, per install, the instructions earlier conversions saw (and the Kickstart addresses). A remembered file that cannot be read was ignored, but one
that is valid and too large (past the bound of an observation) stopped the conversion for good, since the file was only replaced by a conversion that finished. It
is now ignored like a damaged one, and a conversion that fails after it merged anything from that memory is tried once more without it; on success the
run's own observations replace the remembered ones. Checked on Rick Dangerous (quick level) with a valid file of 1,048,577 lines (13.6 MB): ignored, ready in 6 min 34 s, the file replaced
by the run's own 4,896 lines; the retry itself is tested with a fake conversion, not on a real failure. The report says what the memory added, what was ignored and, after a retry, why (`remembered_data`). The
Amiga does not share paths (G16 `-`). **What moves:** the converter only (`retrorecomp/amiga_conversion.py`), plus the report's wording below.

## Commodore Amiga: the report and the F2 menu say less than they did (1.7.2)

The report states what it measures: `native_coverage` names the Kickstart instructions of the player's image when the install uses one, `qualification_scope.media`
the installs that ask for a Kickstart 1.x, `machine.model` that the memory is laid out as WHDLoad lays it out, `video_model.fps_is: nominal` (the frame rate the
player paces by, not a measurement) and `native_validation.independent_cpu_oracle: false` (the native steps and the reference both run Moira). The F2 menu offers
one player's page (one joystick is wired; the mouse is port 1), no second page that led nowhere. The Options note and the Kickstart check ("recognised", since the
image is known by its size and CRC) are reworded in the eight languages. **What moves:** the Amiga's game stamp (`rrhk_amiga.inc`); no other console.

## Commodore Amiga: the keyboard's power-up handshake is over when a slave starts (1.7.2)

Twylyte and California Games stopped at boot with a guru, which 1.7.1 blamed on a 68020; that was wrong: the real WHDLoad boots them on a 68000
(a private run of Copperline). The cause: vAmiga's keyboard waits a second after a reset and then sends `$FD` and `$FE`. On a real machine that ended
long before WHDLoad started; here the slave starts a frame after the power-on, so the codes arrived about a second into the game, during the
Kickstart's boot, and reached a slave's keyboard handler that a player's key would reach much later (that handler then read a word at an odd
address, an address error on a 68000, as a real key press may also cause on such a slave; not checked). The machine now declares the handshake over
at its power-on (`Keyboard::rrHandshakeOver`, a build-time change of the MPL-2.0 file). Both installs boot with picture and sound; Time Runners 19
still stays black, for another reason not found yet. A game's run shifts by a few instructions around that second (Rick Dangerous: 24 more on each
route, the picture, sound and memory of each frame again equal to the fresh reference). **What moves:** the Amiga's game stamp; no other console.
**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the player's own record (1.7.2)

An exported Amiga game now records windows of 16 bytes at the 68000 instructions it interprets in RAM (feedback kind 22, the shared recorder, F12, written at a normal exit), and a reconversion beside that game makes them native, behind the same guard. What ran counts as `native_learned`, what a walk found after it as `native_walked`, apart from route-proved and swept code. These are private hints of that conversion: never in the library, never shared (G16 stays `-`). No shared file changes, so the 4,096-record limit holds. **What moves:** the Amiga's game stamp; no other console. **Hot path:** the instruction hook gains one test while a game runs, and each interpreted RAM instruction compares its window; a native instruction learned or walked adds one counter, as a swept one does. An export made before this records nothing until it is reconverted.

## Commodore Amiga: the keyboard reaches a game that never enables its interrupt; F1-F4 on the long route (1.7.2)

A key changing now sets `CIAICRF_SP` in CIA-A's interrupt mask, as WHDLoad's autodoc describes, unless the slave has `WHDLF_NoKbd` (`native/amiga_machine/amiga_session.cpp`). Found on Pinball Dreams, whose level 2 handler waits for a mask it never sets: no key reached it, with the native code or on the fresh vAmiga reference. The long route's menu keys gain F1 to F4. **What moves:** the Amiga's game stamp; no other console. **Hot path:** none, it runs when a key changes. An export keeps its old behaviour until it is reconverted.

## Commodore Amiga: a long route at the extended level (1.7.2)

The extended level now adds one route of 18,000 frames, seeded from the install (`computer_routes.long_events`, the same body as the Atari ST's, which a test shows; the ST keeps its own so that its stamps do not move), and the thorough level two. It is for route depth, not for native code: on Apidya and Lemmings 18,000 frames brought under 2 % more instructions. A route does not finish a game. `tools/amiga_route_captures.py` takes pictures along each route of a delivered game (`--capture-every`, headless only). **What moves:** the Amiga's game stamp; no other console. A conversion at the standard level runs the same routes as before.

## Commodore Amiga: the Blitter's copy blits, specialised routines by shape (1.7.2, recompilation stage 6)

A game's copy blits of the shapes its reference runs saw now go through a routine compiled for that shape: vAmiga's own microprogram (its accuracy level 2), whose text `amiga_vamiga.blitter_shape_header` takes at build time
with BLTCON0 and BLTCON1 without their shift fields as template parameters, so the compiler folds the channels, the direction, the fill and the minterm's 256-way switch. One step per bus slot, in the slots the reference uses,
everything else read live. Specialised routines, not a translated program. A routine checks its shape at every slot; a game that changes BLTCON during a blit goes on in vAmiga's table (`left_midway`). Line blits, shapes beyond
the 64 that move the most words, and shapes the routes never saw stay in vAmiga's microprogram. Native and interpreted counters by shape: `final_checks[].blitter`; the report's `hardware_devices` names the Blitter apart from Agnus and
the Copper, Denise and Paula, which stay emulated. The Copper is not compiled ([AMIGA.md](AMIGA.md), section 2).
Proof: `tools/amiga_blitter_selftest.py` runs 1,023 shapes (every channel set with every fill and direction, every minterm) on 8,184 random blits, a quarter with BLTCON changed on the way, through vAmiga's table and through the routine, with the same random bus from slot to slot:
the Blitter's whole snapshot and the slot's bus record after each of 970,162 slots, then Agnus, Paula and chip RAM, 0 differ; a routine that writes a wrong word is seen 16 times out of 16. Rick Dangerous, Apidya, Lemmings and Civilization: every frame equals the fresh reference on both routes,
with the same CPU counts and sound hashes as stage 4 and every copy word in a routine (shapes 1, 4, 3, 12). **What it brings:** little. On a loaded PC a slot took about 2 ns less out of 11 to 20 ns, with runs from 0.83 to 1.57 times, no timing; the Blitter is 0.1 to 3.6 % of a frame, so under 1 % of a frame at best.
**Hot path:** one pointer test per copy-blit slot, and a table lookup per blit. **Size:** 4 to 14 KiB more per compressed game on the four. **What moves:** vAmiga's adaptation and the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds; a state saved during a blit goes on correctly in the table.

## Commodore Amiga: a sweep beyond the routes (1.7.2, recompilation stage 4)

What a player reaches beyond the scripted routes ran on the interpreter. The conversion now reads the memory each route's fresh reference leaves (in its private work folder, removed once read) and
goes outward from the observed code: what branches lead to, what follows them, then the rest of the 4 KiB pages where code ran, since a subroutine called through a pointer is reached by nothing
else; a Kickstart image is walked but not filled. A guess that is not code is only a routine that never runs. The swept instructions carry the same guard, the latched opcode. They count apart when
they run (`final_checks.native_swept`; `native_forms.swept_instructions` is what is known), so a report never presents swept code that did not run as proved on a route; the routes it was read from
ran the observed code, so on them the count stays at 0. Nothing swept enters the library.
Proof: Rick Dangerous, Apidya, Lemmings and Civilization as usual, equal to the reference with the same counts. And a build that learned only the main route, playing the explore route it never saw: every frame
and the resload log equal to the reference on the three games tried; 320,225 instructions swept and run with none interpreted on Rick, 1,227,349 and none on Lemmings. On Apidya it reaches 6 of 9,565: that code is no longer
in memory when the main route ends: later loads overwrite it (an image at frame 130 holds it), so it stays on the counted interpreter. Civilization has no such test: its routes run the same code.
The routes are scripts and these are about a minute of each game; this does not say what share of a whole game a sweep reaches. **Size:** 12,730 to 95,933 more instructions compiled; Rick's exe goes from 2.88 MB to 3.28 MB, Civilization's is 8.33 MB
against the first sweep. **Hot path:** one more count per swept instruction that runs. **What moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: 68000 forms translated to C (1.7.2, recompilation stage 3)

The forms of 50 Moira handlers are now written out as C by a translator (`amiga_translate`): the effective address, the operation and the flags for that opcode, every register a
literal index, calling the machine's bus functions (`read`, `write`, `prefetch`, `readExt`, `sync`) in Moira's order. Extension words are still read on the bus, so the guard stays the latched
opcode. Other forms stay Moira's code specialised. Each route's report counts the two apart (`final_checks.native_translated`, `native_moira_specialised`), and `native_forms` gives the
static counts. Translated share of the instructions executed on two routes of 3,600 frames: Rick Dangerous 99.8 %, Apidya 99.9 %, Lemmings 99.9 %, Civilization 99.0 %. Translated is a statement about the 68000's code:
Agnus, Denise, Paula and the CIAs stay emulated, and this says nothing of hardware fidelity.
Proof: `tools/amiga_vector_selftest.py` now runs every one of the 40,586 translated opcodes against Moira's handler on 32 random states over a random memory, with the interrupt lines
changing at a random bus access: 1,298,752 runs, 0 differ on registers, SR, PC, queue, clock, each bus access, internal buffers, function code and flags. Deliberate errors were reported
(a flag, a clock, a moved poll of the lines, a register, the order of a long write, an address error frame); one was not (a `readBuffer` write that a later prefetch overwrites). This shows equality with Moira, not
with the hardware; the corpus of 6,762 vectors still runs through the steps, all equal. The same four games: every frame equal to the fresh reference, packed copy and state continuation too, with the same counts.
An estimate on a loaded PC, headless (hashing included), interpreted time over native time on 1,200 frames: Rick 1.00, Apidya 1.01, Lemmings 1.00, Civilization 1.00; the 68000 is a small part of a frame here, not a timing.
**Hot path:** one more count per translated instruction; the form's text differs, its bus accesses do not. **What moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the instructions' lengths come from Moira, and no recompiler is needed (1.7.2)

The chain of the native code needs the length of an observed instruction and the address it names. Both came from the decoder of `m68k-recomp-core`, built during each
conversion. The length now comes from Moira's disassembler, in the table of its handlers, and the address from the handler and the instruction's words; a wrong guess could only
miss a chain, which still compares the pc at run time. An Amiga conversion no longer reads anything from segagenesisrecomp or m68k-recomp-core, so no PolyForm Noncommercial
text is involved in it, and a machine with extension words the decoder cannot read (a later Amiga) stays open. An opcode the decoder refused now runs native, Moira's code like
the rest. **Hot path:** none. **What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: Moira's code specialised per opcode, and chained (1.7.2, recompilation stage 2)

A native step was a call to Moira's own handler behind a look-up and a comparison of every word through the memory map, which made it slower than the interpreter. Now a *form*
is Moira's handler compiled for one opcode, with the opcode as a literal and Moira's code inlined, and each observed instruction (one per address and opcode) goes straight on
to the instruction it knows comes next. This is Moira's code specialised, not a translation: same bus accesses, same cycles, same code. A form reads its extension words on
the bus as the interpreter does, so it is right for its opcode at any address: the guard is now the opcode the CPU has latched, and a word rewritten in memory, by anything,
needs no tracking. An instruction with the same opcode and other extension words now runs native where it was interpreted. The run loops see what they saw: the chain stops
whenever a flag is pending for Moira or the Amiga, and returns there on anything it does not know.
Vectors: 6,762 of 6,762 equal to the interpreter on registers, SR, PC, prefetch, clock and each bus access. Rick Dangerous, Apidya, Lemmings and Civilization, two routes of
3,600 frames each: every frame equal to the fresh reference on picture, sound, RAM and registers, the packed copy and the state continuation too, with the same instruction counts.
An estimate on a loaded PC, headless (hashing included), interpreted time over native time on 1,200 frames: Rick 1.00, Apidya 1.07, Lemmings 1.00, Civilization 1.01; not a timing.
Licence: the index no longer contains `m68k_decoder.h`, so no PolyForm text enters an Amiga game, and its notice leaves the exports; the decoder still runs during the conversion.
**Hot path:** the look-up and the word comparison are gone from most instructions; one count, two flag reads and a pc and opcode comparison per instruction added. **What
moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: a debugging recorder off, the resload traps without breakpoints (1.7.2, recompilation stage 1)

Two costs the machine paid for nothing a game can see. vAmiga's logic analyzer, a recorder for its debugger, is connected by default and took 12 to 14 % of a
frame's samples; it is off (`Opt::LA_CONNECT`). The resload traps were debugger breakpoints, which keep every 68000 instruction on Moira's slow path and walk a list (0.6 to
5.6 % of the samples); they are one comparison after each instruction (`rr_moira_trap`, a build-time change of Moira's MIT file). Shares of a sampling profile on a loaded PC,
not a timing. **Hot path:** one comparison per instruction added, the slow path and the breakpoint walk removed. Nothing here is recompilation: the counters do not change. **What
moves:** the Amiga's game stamp; no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the guard compares what the CPU has latched (1.7.2)

A native step was chosen by comparing the instruction's words in memory, while the CPU was about to run the opcode it had already prefetched. A word rewritten just
after its prefetch could therefore run the step of the new word with the old opcode. It never happened on a game (8 games, 16 routes, about 480 million instructions:
memory and the latched words never differed), and an authored program shows it (358 of 367 cases differ from the interpreter); the frame comparison covers the routes
only, so a player's play beyond them had no proof. The guard now compares the latched opcode and next word, and memory beyond them; on the same authored program no step
runs and nothing differs. **Hot path:** three stores per instruction, and two reads through the memory map less. **What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: Kickstart words a slave patched run native too (1.7.2)

A slave patches some of the Kickstart's instructions; a step written from the pristine image then missed its guard for ever, and those instructions, often
in loops, stayed on the interpreter. The observation of a run (`<observations>.kick`, in the conversion's private work folder, with the image itself) now
keeps the words as they stood; the steps come from those and from the image, and the library still keeps the addresses alone, no byte. Civilization: 14,988
Kickstart instructions interpreted on the main route become 19 of 4.42 million; California Games 48, Twylyte 10,638 of 49.0 million (0.022 %), on two routes of
3,600 frames, each frame equal to the fresh interpreted reference, the compressed copy too and the quick state with its sound. Native code and CPU fidelity only.
**What moves:** the Amiga's game stamp; no other console.

## Commodore Amiga: an archive with an intro or editor slave beside the game (1.7.2)

An archive with several slaves was refused. The slave named as the install's own folder is now the game, the others staying aside (`Superfrog/Superfrog.slave` beside
`SuperfrogIntro.slave`): 17 of the 25 such archives of the maintainer's library. A collection where no single slave is so named stays refused, never guessed.
**What moves:** the Amiga's game stamp; an install that was refused converts; nothing else changes.

## Exports of 1.7.0 in 1.7.1

1.7.1 is the release after 1.7.0 (published on 7 November 2026). This section is the index of its changes, one line per section below (or per machine page when a change has no
section here), with the stamps that section says move. Each section computed its stamps for its own change alone, on the tree of its branch; the totals are under the table and were
computed on `main` on 8 November 2026.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Adventure games (ScummVM): the options page, the keys and the supported status](#adventure-games-scummvm-the-options-page-the-keys-and-the-supported-status-171) | the Adventure (ScummVM) game stamp, and nothing else in that section | the Adventure (ScummVM) build stamp (`97d9ad0da628` to `fd819f80e824`) | no key moves; the saves are ScummVM's own, in `datas/` |
| [Host kit and resources: two small shared changes](#host-kit-and-resources-two-small-shared-changes-171) | **every machine's game stamp** (already moving in 1.7.1, so no conversion on top) | **every machine's host stamp** (already moving in 1.7.1); no build stamp | no key moves (the Mega Drive, Super Nintendo and CPS keys hash none of these files) |
| [Sony PlayStation opens as an experimental machine](#sony-playstation-opens-as-an-experimental-machine-171) | a new machine: the PlayStation stamps are new | its own | its key is new |
| [Atari ST opens as an experimental machine](ATARI_ST.md) (no section of this page; the facts are on the machine page) | a new machine: the Atari ST stamps are new | its own | its key is new |
| [Nintendo 64 opens as an experimental machine](NINTENDO_64.md) (no section of this page; the facts are on the machine page) | a new machine: the Nintendo 64 stamps are new | its own | its key is new |
| [Game Boy Advance: guarded native RAM code](GAME_BOY_ADVANCE.md#code-the-cartridge-does-not-hold-guarded-native-ram-code-7-november-2026) (no section of this page) | the Game Boy Advance | none stated | not stated |
| [Commodore Amiga: Examine no longer overwrites the memory behind a slave's FileInfoBlock](#commodore-amiga-examine-no-longer-overwrites-the-memory-behind-a-slaves-fileinfoblock-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: a route the game ends itself](#commodore-amiga-a-route-the-game-ends-itself-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the icon's CUSTOM1 to 5, names with accents, a larger ExpMem and BaseMem, a registered WHDLoad](#commodore-amiga-the-icons-custom1-to-5-names-with-accents-a-larger-expmem-and-basemem-a-registered-whdload-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the Kickstart's code runs as guarded native steps, written from the player's own image](#commodore-amiga-the-kickstarts-code-runs-as-guarded-native-steps-written-from-the-players-own-image-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: CIA-B enters the slave as the system leaves it](#commodore-amiga-cia-b-enters-the-slave-as-the-system-leaves-it-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the chipset's collision detection is on](#commodore-amiga-the-chipsets-collision-detection-is-on-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: the window says so when the whole run is interpreted](#commodore-amiga-the-window-says-so-when-the-whole-run-is-interpreted-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |
| [Commodore Amiga: a quick state continues the sound sample for sample](#commodore-amiga-a-quick-state-continues-the-sound-sample-for-sample-171) | the Amiga only (each section says so) | none | the Amiga's key moves where the section says so (a state of an earlier Amiga build is refused cleanly) |

Taken together (`compilation_inputs.role_stamps` of the seventeen profiles, the tree of `v1.7.0` against `main`): **the game stamp and the host stamp of all fourteen earlier profiles move**
(the thirteen machines of 1.7.0 and Adventure (ScummVM)), and **no build stamp moves except the Adventure (ScummVM) one**. The Atari ST, the Nintendo 64 and the PlayStation are new, with
stamps of their own. The sections above that say "no other console's stamp moves" were computed before the three machines joined the registry and the notices; the sum is larger than
any of them.

| Machine | Game stamp (v1.7.0, now) | Host stamp (v1.7.0, now) | Build stamp |
| --- | --- | --- | --- |
| Master System | `ffb447e12968`, `63c93fcb0264` | `4c698ce40729`, `62a7e9f65d83` | `fe2d99b3cd5e` (same) |
| Game Gear | `9f3d2cd547bb`, `70eafce5937a` | `9e302b729213`, `fa5e7fa22b05` | `f5671c38cf26` (same) |
| Game Boy | `1c847126de1d`, `b218f94d2c75` | `d03f39763f54`, `2a0942586a4a` | `819a054ad881` (same) |
| NES | `88240b6d2e3b`, `af5a3a096738` | `a91c8c6c0d28`, `39c36bfa861a` | `8e0941f93b43` (same) |
| Mega Drive | `3c62c2e5c7a3`, `ed3a49ab59a8` | `b45d74b5e78f`, `8f4324fbcb85` | `9615ff2e96c8` (same) |
| Super Nintendo | `0bc2b194ed99`, `064bd8544d76` | `ebe78ef356a1`, `d35383911455` | `3f0a58ad3c7c` (same) |
| Neo Geo | `328279cbfc1c`, `b45ca489a2c9` | `098ae12034e1`, `f1fde4b7a652` | `110349f043bd` (same) |
| X68000 | `d42bb1882a76`, `107b51de2145` | `4cc410c21d5a`, `55ac9db11502` | `5903c0449429` (same) |
| CPS-1 | `b2ef983bc3fd`, `28dd85714948` | `ff2e8295501f`, `0220746ac9ad` | `2782cd370f91` (same) |
| CPS-2 | `71a11548e45d`, `cb7b5d304275` | `7f31bbdfb091`, `7889559074ad` | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `78f5641c38ec`, `ebcbc2a403cd` | `bdcc346995e1`, `3da7363bd893` | `66d912662e5c` (same) |
| Game Boy Advance | `05e06c23687a`, `1658c523234f` | `f94b7ff7c92f`, `7b18d021f143` | `6b70933a9b0a` (same) |
| Amiga | `ff35e3b8af69`, `ba01a0a7e76e` | `136af9f804ed`, `b264a452712e` | `92ca8a0c142c` (same) |
| Atari ST | new, `fa09328f914f` | new, `f8a69516f53e` | new, `54b75964897d` |
| Nintendo 64 | new, `ec87144eb331` | new, `3c4f6ccca458` | new, `4f6fedf926c7` |
| Adventure (ScummVM) | `be8047b230ac`, `42dfc172e91c` | `4a96d24af08d`, `82088d749a09` | `97d9ad0da628`, `05417bbcea96` |
| Sony PlayStation | new, `920cf82497a6` | new, `5dbdb5df79ca` | new, `b6c9cf73b176` |

(First twelve hexadecimal digits of each stamp.) `LEGACY_GAME_STAMPS` stays empty. **So every export of 1.7.0, on every machine, is converted again, from its qualified paths, once, when the
player updates**, and the window offers it; it is not a quick host-only upgrade.

**Quick states.** The **Mega Drive and Super Nintendo keys move** (`native/runtime_catalog.inc` and `native/runtime_feedback.h`, which those two keys hash, changed): a quick state of 1.7.0 of
those two machines is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The **Amiga's key moves** with its sound-carrying state (an
earlier Amiga state is refused). The keys of the NES, the Neo Geo, the CPS-1, the CPS-2, the PC Engine and the X68000 hash none of the files that changed, so their states of 1.7.0 load; the
Master System, Game Gear and Game Boy have no such key. **Cartridge saves** are kept on every machine; the game saves of Adventure (ScummVM) are ScummVM's own.

## Adventure games (ScummVM): the options page, the keys and the supported status (1.7.1)

"Adventure (ScummVM)" ([SCUMMVM.md](SCUMMVM.md)) leaves the experimental status on the owner's decision of 7 November 2026: `retrorecomp/systems/scummvm.py` says `supported`, the
interface note and the documents follow in the eight languages, and the criteria are written in [SCUMMVM.md](SCUMMVM.md#what-supported-means-here) because the qualification matrix
(gates G1 to G16, risk cases, shared paths) is made for recompiled machines; `tests/test_machine_registry.py` asks of an emulated supported category a Linux witness and that page,
instead. The same release carries the options page and the keys of the game (the ScummVM patch `0002-retrorecomp-options-page.patch`, [SCUMMVM.md](SCUMMVM.md)).

**What moves.** `compilation_inputs.role_stamps` of the fourteen machines on the tree before the status (`fa196008`) and on this one: **only the Adventure (ScummVM) game stamp**,
`4e3367b550d2` before, `0369d5533936` after (the profile is a game input of that machine only; the options-page patch was already counted in `4e3367b550d2`, which replaced the
released `be8047b230ac`). Its build stamp moves too, `97d9ad0da628` to `fd819f80e824` (`scummvm_build.py` finds `.deps` from a packaged exe); the host stamps and the build stamps of every other machine do not move, and no other game stamp moves.

**The ScummVM pack and the CMake fix** move those two stamps again, and only those: game `aa2b67d2bcd4` to `8af339f2af21` (`systems/scummvm.py`, `scummvm_export.py`), build `fd819f80e824` to `de9fefa86a8b` (`scummvm_build.py`). The button itself is interface code (`gui_options.py`, `i18n.py`), which no stamp hashes. A runtime that is already current is not rebuilt; a stale one starts from a new build folder the first time, because folders made before this version carry no record of how they were configured.

**The menu colours** (`0003-retrorecomp-theme-colours.patch`, `_pack_theme` in `scummvm_build.py`) move the same two stamps once more, and only those: game `8af339f2af21` to `42dfc172e91c`, build `de9fefa86a8b` to `05417bbcea96`. The patch digest is part of every runtime's identity, so each engine family's runtime is rebuilt by its next conversion.

**Exports.** An adventure executable of 1.7.0 is converted again when its game stamp is checked (it has the old options and no Ctrl+F1 to Ctrl+F4); no other export is. **Quick states** and **cartridge saves**:
none moves, a game's saves are ScummVM's own, in `datas/`.

## Host kit and resources: two small shared changes (1.7.1)

**What moves.** The game and host stamps of every machine, compared entry by entry before and after. They move in 1.7.1 anyway, so no export is converted again because of this alone. No build stamp moves. The quick-state keys of the Mega Drive, the Super Nintendo and the CPS boards hash none of these files.

**What changes.** Off Windows, `resources.embed_resources` no longer rewrites its three generated files with the same bytes, so a second preparation of a game relinks nothing; the Game Boy Advance's local workaround is gone. On Windows it does nothing, as before. `rrhk_action_pressed` and `rrhk_action_held` give an adapter the actions it handles itself, as the player bound them: the PlayStation's Analog button and the Nintendo 64's Stick actions use them, and neither adapter includes `hostkit_internal.h` any more. The rules are those the adapters had. `RrhkMachine.native_caption` names the window title's words while nothing is interpreted: the PlayStation, the Nintendo 64, the Atari ST and the Amiga say "Native CPU, emulated hardware", every other machine still "Native code".

**Checked.** The unit test of the embedding (on Windows, through `write_embedding`) and the kit's capabilities self-test with a virtual controller. **Not checked yet:** a game of either machine played or converted with these calls, and the embedding on Linux; both belong to the release checks.

## Sony PlayStation opens as an experimental machine (1.7.1)

The Sony PlayStation (profile `psx`, [PLAYSTATION.md](PLAYSTATION.md)) opens to players as an **experimental** machine. No export of
it exists before this release, so nothing is upgraded. It takes no path from the shared base and gives none. The machine is Beetle
PSX, pinned and fetched on the first conversion, with anchored changes listed in `psx_beetle.REPLACEMENTS`; the game executable
is GPL-2.0 as a whole. Its files are game inputs of `psx` alone: no other console's stamp moves for them.

## Commodore Amiga: Examine no longer overwrites the memory behind a slave's FileInfoBlock (1.7.1)

Installs that load their files through the slave's own operating-system emulation (the `Examine` flag: 1,180 of the 2,967
Amiga 500 installs of the maintainer's library that the profile reads, 1,040 of them with a Kickstart) stopped at boot with
"not enough memory" (AmigaDOS 103). The cause, found by tracing exec: the emulation calls `resload_Examine` with a
FileInfoBlock that has only 240 bytes before the next free chunk; the layer cleared and wrote all 260 bytes of a
FileInfoBlock, zeroing that chunk's header, so exec's fast-memory list held one chunk of size 0 and every later
allocation failed. `Examine` and `ExNext` now write only the fields they have values for (the name up to its NUL, the
sizes, the date, an empty comment) and leave the rest of the buffer alone. Another World (FR) and 4D Sports Boxing, the
two cases Arthur met, run; so do Maniac Mansion, Monkey Island 2 and Beneath a Steel Sky (the first two and the last
stopped before the change). **What moves:** the Amiga's game stamp (`native/amiga_whdload/rr_resload.c`); no other console.

## Commodore Amiga: a route the game ends itself (1.7.1)

A scripted route may make a game quit through its own menu (`resload_Abort` with `TDREASON_OK`): 4D Sports Boxing does so at
frame 1,702 of the exploration route. Such a reference run is accepted when it lasted at least 1,000 frames; every later run of
that route (native passes, the compressed copy, the quick-state continuation) must end the same way, and its trace and resload
log, the final call included, must equal the reference's. The report marks the route `ended_by_game` with the frames it ran.
Any other stop still fails the conversion. **What moves:** the Amiga's game stamp (`amiga_conversion.py`, the session and the
player); no other console.

## Commodore Amiga: the icon's CUSTOM1 to 5, names with accents, a larger ExpMem and BaseMem, a registered WHDLoad (1.7.1)

Four changes to what a slave may ask of the layer, found by running 24 installs of the library headless with the player's
Kickstart 1.3. **CUSTOM1 to CUSTOM5** are read from the install's own icon (`<slave>.info`, its ToolTypes, as WHDLoad does; a
ToolType in parentheses is off) and answered to `resload_Control`; there is no per-game setting in the window. 432 of the 2,967
installs carry one (413 CUSTOM1); Might & Magic 3 (DE) needs CUSTOM1=2 to start. **Names**: a guest name is ISO-8859-1 and the
install's file name UTF-8; they are converted both ways (23 archives have accents), so a slave finds a file it names with an
accent. **Memory**: an ExpMem that does not fit the 1.5 MiB of slow RAM (88 installs of the library did not fit) is given to a
Zorro II fast RAM board configured at `$200000` (up to 8 MiB), with the slave area staying in slow RAM; a BaseMem above 1 MiB
gets 2 MiB of chip RAM (3 installs). 72 of the 88 now fit (59 of them with Kickstart 1.x); the other 16 need a 512 KiB
Kickstart (a later step). **Registered**: 198 slaves of the library name
the undocumented `resload_Control` tag `WHDLTAG_Private3` and test its answer for non-zero (zero makes them stop with
`TDREASON_MUSTREG`, "WHDLoad must be registered", or skip patches); it is answered 1, a value of ours, not one read from
WHDLoad. Civilization, which stopped with that reason, runs. **Measure:** headless, interpreted, 1,500 frames, each with a
picture: Settlers, Conquests of the Longbow, Civilization, Ambermoon, Kings Quest 5, UFO Enemy Unknown, Zeewolf, Skidmarks,
Cyber Games (native code, CPU fidelity, hardware fidelity and gameplay are not measured by this run). **Known limit as written in
1.7.1, corrected in 1.7.2:** this note blamed a 68020 for three installs that stop at boot; the real WHDLoad boots them on a 68000 (see
the 1.7.2 entry on the keyboard's handshake).
**What moves:** the Amiga's game stamp (`amiga_session.cpp`, `rr_resload.c`, `amiga_player.c`, `amiga_conversion.py`); no other
console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the Kickstart's code runs as guarded native steps, written from the player's own image (1.7.1)

An install that runs with the player's Kickstart spent most of its instructions in the Kickstart (81 to 98 % in Might & Magic 3,
Civilization and Skidmarks), all on the counted interpreter. The player now observes the Kickstart's instructions by **address
only**; the conversion keeps those addresses in the private memory of that image (`converter-kickstart-addresses.txt`, numbers,
never a byte, one folder per image identity) and, when it writes the guarded steps, reads the words of each instruction from the
player's own image in memory. The steps keep the live-word guard of every step, so a Kickstart word a slave patched falls back to the
counted interpreter. The generated source and the game built from it exist only in that player's private work folder and export;
nothing derived from the image is shared, and the observation file and the library hold addresses only (**changed in 1.7.2:** the run's own
observation of the Kickstart keeps the words as they stood, a slave's patches included, in the conversion's private work folder only; the library
still keeps the addresses alone). **Measure** (Civilization,
the real converter, two routes of 3,600 frames, validated against the fresh interpreted reference, the compressed copy and the
quick state): the interpreted share fell from 97.7 % to 0.34 % (14,988 Kickstart instructions still interpreted, 4.30 million
native on the main route). This is the native-code measure only; CPU fidelity is the frame-by-frame equality with the interpreted
reference on those scripts, and hardware fidelity, gameplay and latency are not measured. **What moves:** the Amiga's game stamp
(`amiga_session.cpp`, `amiga_player.c`, `amiga_conversion.py`); no other console, and no shared 68000 file or path format is touched.
**Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: CIA-B enters the slave as the system leaves it (1.7.1)

Blood Money played noise ("a 56K modem") from the first tune on. Cause, found by comparing with the real WHDLoad (private run of Copperline):
the slave's loader wrapper adds 79 tracks to the offset of a `resload_DiskLoad` when bit 2 of CIA-B's port B (`$BFD100`, the disk side
select) reads 0, and our boot ROM left CIA-B at its reset state, every pin an input, so the bit always read 1: the music samples (track 107)
were read from track 28 instead, whose data the game played as sound (the same lengths, periods and pointers as on the real machine, other
bytes). The real machine has CIA-B DDRA `$C0` and DDRB `$FF` while a slave runs (the disk lines are outputs, so a read gives back the
latch). The boot ROM now sets CIA-B's PRA `$F8`, PRB `$FF` (no drive selected, motor off), DDRA `$C0` and DDRB `$FF`, in that order.
After the change the three sample regions of Blood Money are byte for byte those of the real machine (0 of 74,256 bytes differ) and the
sound has tonal structure instead of flat noise. 26 slaves of the maintainer's library name `$BFD100` in their own code (Blood Money,
Menace, Nebulus, North And South, Lotus, Space Ace and others), so other disk-side readers may have loaded wrong tracks too; the native
steps were never involved (the run on the interpreter plays the same noise). **What moves:** the Amiga's game stamp
(`native/amiga_machine/amiga_session.cpp`); no other console. **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the chipset's collision detection is on (1.7.1)

A real Amiga always detects collisions between sprites and between sprites and the playfields (CLXCON/CLXDAT); vAmiga ships the three
detections off for speed and the Amiga machine did not turn them on, so a game that reads CLXDAT never saw a collision. They are on now
(`native/amiga_machine/amiga_session.cpp`). Library check by counting CLXDAT reads over the standard route: Blood Money reads it (36
reads in 2,500 frames), Xenon 2, Turrican, Shadow of the Beast, R-Type, Menace, Armalyte, Battle Squadron, Rick Dangerous, Lotus 2, Speedball 2 and
Wings of Death do not (nor Apidya). **What moves:** the Amiga's game stamp; no other console. A game that reads CLXDAT may now play
differently from an earlier export of it (the detection a real Amiga performs; the match of the game's behaviour with hardware is not measured). **Quick states:** the Amiga's key moves, as between any two Amiga builds.

## Commodore Amiga: the window says so when the whole run is interpreted (1.7.1)

With `--reference-cpu` (every instruction on the interpreter) the window's title said "Native code", because no hook counts instructions in
that mode. The Amiga adapter now reports the run as interpreted, so the title reads "Interpreter fallback". Reports are unchanged (they count
through the player). **What moves:** the Amiga's host and game stamps (`amiga_player.c`, `rrhk_amiga.inc`); no other console.

## Commodore Amiga: a quick state continues the sound sample for sample (1.7.1)

vAmiga's snapshot leaves out the memory of its sound path, so the samples after a load differed from an unbroken run and the
conversion could not compare them. The adapted core (`retrorecomp/amiga_vamiga.py`, `Ports/AudioPort.h`, MPL-2.0 like the file) now
saves and restores the four samplers' pending samples, the three filters' memory, the sub-sample fraction, the master volume ramps
and the muted flag; the player appends them to its state file and clears the output stream after a load. Headless, a state
saved mid-run and resumed in a fresh process gives the same sound hash on all 200 frames compared (Apidya, Zeewolf, Cyber Games),
with the CPU registers, RAM and picture; the conversion now compares the sound after a load too. **What moves:** the Amiga's game
stamp (the adapted core, `amiga_session.cpp`, `amiga_conversion.py`); no other console. **Quick states:** the state file schema is
now `RRAMIGA-STATE-2`: states of earlier Amiga builds are refused cleanly. Hardware fidelity and physical latency are not
measured by this check.

## Exports of 1.6.9 in 1.7.0

1.7.0 is the release after 1.6.9 (published on 6 November 2026). This section is the index of its changes, one line per section below, with the stamps
that section says move. Each section computed its stamps for its own change alone; the totals are under the table. It lists what is on `main` so far.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Computers: a press of the middle button releases the mouse](#computers-a-press-of-the-middle-button-releases-the-mouse-170) | none | X68000 host (`rrhk_computer.inc`) | no key moves |
| [Game Boy Advance opens as an experimental machine](#game-boy-advance-opens-as-an-experimental-machine-170) | none (a new machine: Game Boy Advance stamps are new) | host stamp of all eleven other consoles (THIRD_PARTY_NOTICES) | none (no earlier export) |
| [Host kit: analog sticks, rumble, the 3D graphics page, larger pictures and disc change](#host-kit-analog-sticks-rumble-the-3d-graphics-page-larger-pictures-and-disc-change-170) | none | **host stamp of all eleven consoles** (the kit, `runtime_catalog.inc`) | **the Mega Drive and Super Nintendo keys move** (the catalogue); no other key |
| [Capcom CPS-2 leaves the experimental status](#capcom-cps-2-leaves-the-experimental-status-170) | CPS-1 (and CPS-1.5, the same board) and CPS-2; the other nine consoles keep theirs (`path_profiles.py` untouched) | **host stamp of every console** (`artwork.py`, box art of the CPS family) | no key moves (`native/cps1_persistence.c`, the EEPROM writer, is hashed by none) |
| [PC Engine / TurboGrafx-16: US cards, the reset-instruction tie-break, the Linux build](UPGRADES_HISTORY.md#pc-engine-an-experimental-machine-169) (the paragraph "US TurboGrafx-16 cards") | the PC Engine only (the reader, the profile and the report writer) | none | not stated |

| [The index of native steps may have its own language](#the-index-of-native-steps-may-have-its-own-language-170) | **every console** (`systems/specs.py`, an input of every game stamp), and the X68000 again (`m68k_observed.py`) | none | no key stated to move |
| [Covers: a subtitle that names the game, and extra names from a profile](#covers-a-subtitle-that-names-the-game-and-extra-names-from-a-profile-170) | none | **host stamp of every console** (`cover_titles.py`, `artwork.py`) | no key moves |
| [Commodore Amiga: an experimental machine](#commodore-amiga-an-experimental-machine-170) | a new machine: the Amiga stamps are new; its profile and converter modules are the only game inputs it adds | the notices (a vAmiga row) and the Amiga files; no build stamp | the Amiga's key is new; no other console's key moves for it |
| [The F12 recorder accepts the hints of every machine](#the-f12-recorder-accepts-the-hints-of-every-machine-170) | **the game stamp of all thirteen machines** (`runtime_feedback.c` and `.h`, `freshness.py`) | none | no key moves for it (the Mega Drive and Super Nintendo keys hash the recorder but already move) |
| [Commodore Amiga: the player's own Kickstart 1.3](#commodore-amiga-the-players-own-kickstart-13-170) | the Amiga only (`f68fb739871c` at the time of the section) | none | the Amiga's key moves (a state of an earlier Amiga build is refused cleanly); no other key |
| [Adventure games (ScummVM): a category of its own](#adventure-games-scummvm-a-category-of-its-own-170) | **the game stamp of the thirteen earlier machines** (`batch.py`, `report_schema.py`; no new conversion on top of the others); the ScummVM stamps are new | **host stamp of the thirteen earlier machines** (the notices, the licence pages); the ScummVM stamps are new | no key moves; the exports have no state of ours |

<!-- Rows of the changes merged after this index go here, in the order of their merge, with their new stamps and keys. -->

Taken together (`compilation_inputs.role_stamps` of the eleven consoles, the tree of `v1.6.9` against `main`, from the stamps each section lists): **the game stamp and the host stamp of the eleven consoles of 1.6.9 move; no build stamp moves** (the Amiga section computed it on the tree of `v1.6.9`; the game stamps move through
`systems/specs.py`, which every game stamp hashes, and the host stamps through the notices, the host kit and the box-art modules). The Game Boy Advance and the Amiga are new. So every export of 1.6.9
is converted again from its paths, once, when it is upgraded. `LEGACY_GAME_STAMPS` stays empty. The recorder change above moves the game stamp of all thirteen machines for itself, and adds no conversion on top of this total. Adventure (ScummVM) is a fourteenth profile with stamps of its own, new; it moves no stamp that was not already moving.

**Quick states.** Only **the Mega Drive and the Super Nintendo keys** move (the host kit's strings are in `native/runtime_catalog.inc`, which those two keys hash): a quick state
written by a Mega Drive or Super Nintendo export of 1.6.9 is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the
NES, the Neo Geo, the CPS-1 and CPS-1.5, the CPS-2 and the X68000 hash none of the files that changed, so their 1.6.9 states load (the PC Engine section does not state its key); the Game Boy Advance and the Amiga have keys of their own, new; the Master System, Game Gear and Game Boy have no key.
**Cartridge saves** are kept on every console; the EEPROM of the CPS-1.5 and the CPS-2 is now written by a worker thread (a stop within about a second of the last change loses that change).

## Computers: a press of the middle button releases the mouse (1.7.0)

On the computers, a press of the middle mouse button (the wheel) now releases a captured mouse, as Ctrl+Alt+M does; the
button never reaches the game (the X68000's and the Amiga's mice had two buttons). The capture notices say so, in English
and French. What moves: the **host stamp of the X68000** (`native/hostkit/adapters/rrhk_computer.inc`, host role); no game
or build stamp, no quick-state key. An export of 1.6.9 keeps working as it is; reconverting it brings the middle-button release.

## Host kit: analog sticks, rumble, the 3D graphics page, larger pictures and disc change (1.7.0)

Five capabilities of the player shell for the PlayStation, written for every machine ([HOST_KIT.md section 2.4](HOST_KIT.md#24-sticks-the-graphics-page-larger-pictures-rumble-and-discs-170),
decision [D14](HOST_KIT.md#d14)): `rrhk_pad_axes` and a Stick dead zone row, the F3 graphics page, a picture that grows past
its opening size, `rrhk_rumble` and a shared Vibration row, a Change disc action, and up to twenty controls per machine
(`RRHK_MAX_ACTIONS` 12 to 20; an F2 page scrolls past fifteen rows; the triggers bindable as buttons with `trigger_buttons`).
Each one is a new field of the machine table (or a limit no machine of 1.6.9 reaches) that is off when an adapter leaves it
out, and **no adapter of 1.6.9 declares one**: on the eleven consoles F3, the menus, the input, the bindings and preferences
(the X68000's `player.cfg` included) and the pictures are unchanged (A/B below).

**What moves.** Computed with `compilation_inputs.role_stamps` of the eleven consoles, the tree of `main` at `27e30e0` against
this change (all five capabilities, the twenty controls and the review fixes, recomputed on the final tree): **the host stamp of all eleven consoles** (`native/hostkit/hostkit.h`, `hostkit_internal.h`, seven files of
`native/hostkit/shell/` and `native/runtime_catalog.inc` are host inputs). **No game stamp and no build stamp moves**: an export
of 1.6.9 that has nothing else to rebuild is upgraded (rebuilt from its paths, no rediscovery).

| Console | Game stamp | Host stamp (before, after) | Build stamp |
| --- | --- | --- | --- |
| Master System | `3e16a0301d90` (same) | `1b834d7b9fbc`, `5e19fd3e1507` | `fe2d99b3cd5e` (same) |
| Game Gear | `4f9d69e86e89` (same) | `c9e0e360f031`, `6a0a2110937d` | `f5671c38cf26` (same) |
| Game Boy | `ff30f88ca9f1` (same) | `772d06158394`, `c545c7240609` | `819a054ad881` (same) |
| NES | `a3537f590fcf` (same) | `21b599f4ec81`, `82968356d271` | `8e0941f93b43` (same) |
| Mega Drive | `a0de8eae71a4` (same) | `7bda64083b03`, `d6f288c77b93` | `9615ff2e96c8` (same) |
| Super Nintendo | `ae2146874e49` (same) | `2a4bc2c7b468`, `45d3816ac86c` | `3f0a58ad3c7c` (same) |
| Neo Geo | `a3733e1113ff` (same) | `1f2e8a0e2450`, `57af9580985d` | `110349f043bd` (same) |
| X68000 | `6c7509bf49d2` (same) | `47212d53043d`, `1df1d70e5a4b` (with the middle-click release above) | `5903c0449429` (same) |
| CPS-1 | `e6380523c2d1` (same) | `0f8432dcd5c5`, `33eca10a92c8` | `2782cd370f91` (same) |
| CPS-2 | `8d2c63c4b35a` (same) | `0f2bade664f6`, `453594c99c49` | `81a51ad49349` (same) |
| PC Engine | `c8545bf9018e` (same) | `6ea8ea8ac8eb`, `98e3865903b4` | `66d912662e5c` (same) |

(First twelve hexadecimal digits of each stamp.)

**Quick states.** The kit's nine new strings are in the five-language game catalogue, `native/runtime_catalog.inc`, which the
**Mega Drive and Super Nintendo** keys hash (`compilation_inputs.state_native_files`): **those two keys move**, and a quick state
written by a Mega Drive or Super Nintendo export of 1.6.9 is refused cleanly by its 1.7.0 build (no compatibility key is carried,
[GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the NES, the Neo Geo, the CPS-1, the CPS-2, the
PC Engine and the X68000 hash none of the changed files and do not move; the Master System, the Game Gear and the Game Boy have
no key of this kind. `native/game_options.h` and `native/retro_menu.c` are unchanged. **Cartridge saves** are kept on every console.

**Preferences.** Nothing is renamed or read differently on the eleven consoles. A machine that declares the new fields adds
`deadzone` to `[<Console>.Gamepad.PlayerN]`, its options' keys to `[<Console>.Video]`, and `rumble` to `[Manettes]`.

**A/B** (Windows, llvm-mingw, offscreen SDL, `tools/hostkit_ab.py` with its virtual clock and modelled audio device; the A side
built from `git archive 27e30e0 native tools`, the B side from this tree, both against the same kept builds):

* X68000 (`build-x68`, the kept conversion of `.build/x68`): the scripts `play` (3,280 frames), `autofire`, `keyboard`, `mouse`,
  `states` and `ui` (518 frames, 47 pictures of help, F2 and options pages in five languages) with the machine's per-frame trace
  (`--trace`): **identical**, every file (pictures, trace, audio, window log, preferences).
* CPS-1, Warriors of Fate (three players, a DIP page; `build --refresh-kit`), the standard battery of 3,968 iterations (both
  players' keys and pads, the filters and display modes, every language, every F2 page, states, preferences): **identical** (61
  files: 3,968 picture hashes, 52 captures, 2,768 audio pushes, the state file, the preferences).
* Both A/B runs were made again on the final tree (the twenty controls, the scrolling pages, `trigger_buttons` and the review fixes): identical
  again, every file.
* ROM-free: `tests/test_hostkit_capabilities.py` (the five capabilities on a fake machine of eighteen controls, its scrolling F2
  page and its triggers as L2 and R2, then the same machine with every field left out), `tests/test_hostkit_players.py`, `tests/test_hostkit.py` and the X68000 harnesses of the suite.

Not measured: a real gamepad (stick values and rumble go through SDL's virtual controller only), a real display, Linux, the other
consoles by A/B (same shell code; only the X68000 and the CPS-1 were run), and a 3D machine itself (none exists yet).

## Game Boy Advance opens as an experimental machine (1.7.0)

The Game Boy Advance (profile `gba`, [GAME_BOY_ADVANCE.md](GAME_BOY_ADVANCE.md)) opens to players as an **experimental** machine in 1.7.0. It is new:
no export of it exists before this release, so nothing is upgraded. It takes no path from the shared base and gives none (it is not in the base). It asks for
your own BIOS (`gba_bios.bin`, checked by its SHA-1); a converted game holds code derived from it and stays private to you. The engine is
[mstan/gbarecomp](https://github.com/mstan/gbarecomp) pinned at `c1a5fda36fb4` (PolyForm Noncommercial, with the author's permission) and its submodule
`arm-recomp-core` (MIT), fetched on the first conversion and carried with 44 anchored patches ([UPSTREAMS.md](UPSTREAMS.md)).

What the change moves, computed with `compilation_inputs.role_stamps` on `main` (27e30e03) and on the branch (game, host, build, first 12 hexadecimal digits):

| Console | Game stamp | Host stamp | Build stamp |
|---|---|---|---|
| sms | 3e16a0301d90 (same) | 1b834d7b9fbc → 033d55196e25 | same |
| gg | 4f9d69e86e89 (same) | c9e0e360f031 → 1a565bafd044 | same |
| gb | ff30f88ca9f1 (same) | 772d06158394 → 67546878fe4b | same |
| nes | a3537f590fcf (same) | 21b599f4ec81 → b49e7d1d6a9a | same |
| md | a0de8eae71a4 (same) | 7bda64083b03 → 75dc61baeb8b | same |
| snes | ae2146874e49 (same) | 2a4bc2c7b468 → ab414537de23 | same |
| ng | a3733e1113ff (same) | 1f2e8a0e2450 → a17e0dd77249 | same |
| cps1 | e6380523c2d1 (same) | 0f8432dcd5c5 → 28aaed430011 | same |
| x68 | 6c7509bf49d2 (same) | 47212d53043d → be0daff05bb1 | same |
| cps2 | 8d2c63c4b35a (same) | 0f2bade664f6 → 56a02d1ee4c6 | same |
| pce | c8545bf9018e (same) | 6ea8ea8ac8eb → 78d65184c1bf | same |
| gba (new) | a90b434c6d70 | 8eb4c3a0974e | 6b70933a9b0a |

- **No game stamp and no build stamp of another console moves.** The profile declares its own ZIP limit (`archived_rom_limits`), its own path order (11), its own
  feedback kind (21) and its own files in `stamp_inputs.py`; no shared module was edited for it besides the registry (an interface module that no stamp hashes).
- **The host stamp of the eleven other consoles moves**, because `THIRD_PARTY_NOTICES.md` (a host input) gains the row of gbarecomp and arm-recomp-core. No
  export changes behaviour: a host stamp that moved only means the licence page of the next conversion is newer.
- `.gba` is no longer a "foreign" extension: a `.gba` file is claimed by the Game Boy Advance profile (or reported as unavailable when the installation lacks its files).

## The index of native steps may have its own language (1.7.0)

The shared generator of observed 68000 code (`retrorecomp/m68k_observed.py`) wrote the index of native steps in the language of the steps. The index is
C (its page tables are array designators); the Amiga's steps are C++ (they call Moira's instruction templates), and a C++ index needed a warning switched
off. `ObservedCode.index_extension` (`retrorecomp/systems/specs.py`) names the extension of `steps/index` when it differs from the steps'; `None`, the
default, keeps the steps' extension. The Amiga sets `'.c'`: its steps are C++ functions with C linkage and its index is C. One line of `write_steps`
reads the field; no other line of the shared module changes. A contract test (`tests/test_observed_index_contract.py`) writes the index of every
machine that declares an `ObservedCode` and compiles it, warnings as errors, in the language its extension names; the former C++ index of the Amiga fails it.

**Proof that the X68000 does not change.** The native project of two games (R-Type and Lemmings, the variants of their recorded observations) was written
with the converter of `main` and with this tree: **78 files, 0 differences** (the decoder's build folder and the logs name the tree and are left out).
The generator's revision (`x68_knowledge.GENERATOR_REVISION`) stays 1, as for the move of the generator in 1.6.9, so no qualified path is lost; the
digest of `retrorecomp/m68k_observed.py` in `tests/x68_generator_pins.json` is updated.

**What moves**: `retrorecomp/systems/specs.py` is an input of the game stamp of all nine consoles, so **the game stamp of every console moves**;
`retrorecomp/m68k_observed.py` moves the game stamp of the X68000 again. No host or build stamp moves. The output of the X68000's generator is
identical, but an export upgraded across this change is converted again once, as the stamps say.

## Commodore Amiga: resload_Abort read as documented, and said in words (1.7.0)

`resload_Abort(success, primary, secondary)` takes its arguments at `(a7)`, as the autodoc's synopsis says (the documented call
jumps through `rts`, so no return address lies above them); the layer read them one slot too far, so an aborting slave
showed three meaningless numbers ("the slave ended the program (103, 53452, 16730414)"). It now reads them at `(a7)`
(skipping a return address when a slave arrived with `jsr`) and says what the slave could not do: "the install could not
read the file '4DBoxing' (not enough memory, AmigaDOS error 103; resload_Abort reason 1)". **What moves:** the Amiga's game
stamp (`native/amiga_whdload/rr_resload.c`); no other console.

## Commodore Amiga: the player's own Kickstart 1.3 (1.7.0)

An install that asks for a Kickstart 1.x (in its slave header or through `resload_LoadKick`) now converts with the player's own
image, chosen in Options > Commodore Amiga ([AMIGA.md](AMIGA.md), section 2a). The image goes only into the conversion's private
work folder and the player's own export; its code is interpreted and counted apart. Installs that need none are converted as
before. Kickstart installs were not run on Linux (the same machine path; not witnessed there).

**What moves** (`compilation_inputs.role_stamps` of `main` at 575c900a against this branch, 6 November 2026): **the game stamp of the Amiga only** (`f68fb739871c`); no other console's stamp moves, no host or build stamp moves.
**Quick states:** the Amiga's key moves (its
session sources changed): Amiga states of earlier builds are refused cleanly, as they are between any two Amiga builds.

## Covers: a subtitle that names the game, and extra names from a profile (1.7.0)

Two generic changes to the box lookup (`retrorecomp/cover_titles.py`, `retrorecomp/artwork.py`). A query without a subtitle that
equals a catalogue entry's main title no longer drops that entry for an edition word found only in its subtitle, when the
subtitle holds other words too ("Speedball 2" finds "Speedball 2 - Brutal Deluxe"; "Super Metroid - Redux", "Tetris DX" and
bracketed tags still count as editions). And a profile may offer extra names for its games' boxes (`cover_titles(path)`, an
optional capability read with `getattr`), tried only after the file's name and the title find nothing: the Amiga offers the
slave's own name, cleaned of its decorations ("Lotus 2" finds "Lotus Turbo Challenge 2").

**Proof without conversions:** the box choice was replayed for the 1,232 conversion reports of `Export` (nine machines) against
the cached catalogues, with the tree before and after: 2 choices change, both Amiga (Lotus 2 and Speedball 2, none before).

**What moves:** both modules are host inputs of every console (`HOST_MODULES`): **the host stamp of every console moves**, no
game stamp; an export of 1.6.9 is upgraded without rediscovery for that part.

## Commodore Amiga: an experimental machine (1.7.0)

The Amiga 500 opens as an experimental profile (`amiga`, [AMIGA.md](AMIGA.md)): WHDLoad installs that need no Kickstart, on the
vAmiga Core (MPL-2.0 per file) and its 68000 Moira (MIT), with our own resload layer. Each Amiga game carries its notices as
resource 203, and THIRD_PARTY_NOTICES has a vAmiga row.

**Offered to players.** The profile is no longer for developer installations only: like the Game Boy Advance and the PC
Engine, it is listed when the installation carries its converter files (`amiga.converter_available`), its options note no
longer says otherwise in the eight languages, and the credits list it as experimental. Linux is `witnessed` (one install
converted and validated on a Debian 13 PC; G13 `P`). Against the merged `main` this moves **the Amiga's game stamp only**
(its profile and converter modules); no other console's stamp moves. The check reads the Amiga's native files only: a
packaged converter keeps its Python modules inside the executable, so a check of `amiga_conversion.py` as a file had hidden
the profile from every packaged 1.7.0 build (found by the release check of the packaged executable; fixed before
publication, the Amiga's game stamp only). The same check then found the Amiga's decoder looking for the shared
generated decoder folder in the packaged converter's unpacked files instead of its working folder (`ROOT`, as the X68000
does); fixed too, the Amiga's game stamp only.

**What moves** (`compilation_inputs.role_stamps` of the tree of `main` at 27e30e03 against this branch, computed on 6 November
2026, the change of `index_extension` above included): **the game stamp and the host stamp of the eleven consoles of 1.6.9**; no
build stamp. The game stamps move through the profile modules and `systems/specs.py`, the host stamps through
THIRD_PARTY_NOTICES. The Amiga's stamps are new. **Quick states:** the Amiga's key is new. Outside the Amiga's own folders the
branch changes no native file (`git diff 27e30e03 -- native`), and the X68000's generated code is identical (section above), so
no other console's key moves and their 1.6.9 states load.

## The F12 recorder accepts the hints of every machine (1.7.0)

A game's player keeps a small set of the interpreter misses it meets (the hints for the next recompilation, written at normal shutdown, recording switched on and off by F12,
[RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md)). `native/runtime_feedback.c` refused every kind above `RR_FB_CPS1_Z80` (16), the last kind of the CPS-1, so **the interpreter misses of
the CPS-2, the PC Engine, the Game Boy Advance and the Amiga, whose kinds are 17 and above, were never recorded**: no hint of those machines could reach a feedback file. The bound is now `RR_FB_MAX_KIND` (`native/runtime_feedback.h`, 23, the largest kind a profile may declare; a larger one
is still refused as garbage), and `tests/test_system_profiles.py` fails when a profile declares a kind above it. Alongside, `retrorecomp/freshness.py` identifies a game that is a
folder (not a file) by its `item.sha256` instead of hashing it as a file, which would fail.

**What moves.** Computed with `compilation_inputs.role_stamps` of the thirteen machines on the tree of `main` before this change (`575c900a`) and on this tree (first twelve
hexadecimal digits of each stamp, 6 November 2026):

| Machine | Game stamp (before, after) | Host stamp | Build stamp |
| --- | --- | --- | --- |
| Master System | `e79637610588`, `49fe6e32e245` | `52732894c705` (same) | `fe2d99b3cd5e` (same) |
| Game Gear | `c42ec7af339f`, `8c00b18cbb84` | `12ddf0d7f71c` (same) | `f5671c38cf26` (same) |
| Game Boy | `e9fd59f69c23`, `84ee8993f728` | `cf765eccafd3` (same) | `819a054ad881` (same) |
| NES | `e1e7dbd43df6`, `70294cfa87ce` | `71877ffa5602` (same) | `8e0941f93b43` (same) |
| Mega Drive | `405fbb268e93`, `a51188bb861f` | `81f2da5cd72d` (same) | `9615ff2e96c8` (same) |
| Super Nintendo | `75e3f274ba12`, `183e40e13480` | `86e398dab378` (same) | `3f0a58ad3c7c` (same) |
| Neo Geo | `d507c3759c6a`, `dc211c9479da` | `b7fe8c803579` (same) | `110349f043bd` (same) |
| X68000 | `2f70a9be8803`, `ad8e4bc0f227` | `1ca7429d24bd` (same) | `5903c0449429` (same) |
| CPS-1 | `e14379ea4193`, `da3f9a93f08f` | `075e0ff74ad2` (same) | `2782cd370f91` (same) |
| CPS-2 | `aece1f235d63`, `d0dfdf7fcd0a` | `6d09623637fd` (same) | `81a51ad49349` (same) |
| PC Engine / TurboGrafx-16 | `dd23d12432c7`, `61785d10f6b3` | `e688aeb8d524` (same) | `66d912662e5c` (same) |
| Game Boy Advance | `25a43b11f017`, `a8f3639ad2c9` | `f91cddfbe6b9` (same) | `6b70933a9b0a` (same) |
| Amiga | `55862e6f7665`, `f6905ac1baf4` | `8e7c7e682d10` (same) | `92ca8a0c142c` (same) |

(First twelve hexadecimal digits of each stamp.) **The game stamp of all thirteen machines moves** (`native/runtime_feedback.c` and `.h` are game inputs of every machine, as is
`retrorecomp/freshness.py`); no host stamp and no build stamp moves for this change. Against the tree of `v1.6.9` the game stamps of the eleven machines of 1.6.9 had already moved
(see the index above), so this adds no conversion to a player who upgrades from 1.6.9.

**What it means for players.** A moved game stamp means that an export is not upgraded in the quick host-only way (rebuilt from its learned paths, without discovery): it is
**converted again, with its discovery routes**, from its qualified paths, once, when the player updates. Every export of 1.6.9, on every console, is in that case in 1.7.0; the cost
is the length of a conversion per game. The reason: an export made by 1.6.9 carries the recorder that drops the hints, and only a rebuilt game carries the new one; Arthur decided it
knowingly (« fix it in 1.7.0 »).

**Quick states.** No key moves for this change: the Mega Drive and Super Nintendo keys hash `runtime_feedback.c` and `.h` too, and they already move for the host kit's catalogue
(a quick state of 1.6.9 of those two machines is refused once, not twice); the other machines' keys hash none of the files changed. **Cartridge saves** are kept.

**Not measured.** The cost of the changed test in the recorder (one comparison per recorded miss) and a game of each new machine played to a normal shutdown to see its feedback file
written: the change is proved by the bound test and by the stamps, not by an A/B of a game.

## Adventure games (ScummVM): a category of its own (1.7.0)

"Adventure (ScummVM)" ([SCUMMVM.md](SCUMMVM.md), profile `scummvm`) is added as an **experimental** category of its own: a folder of an adventure game that ScummVM's
detection recognises becomes one executable holding ScummVM and the player's own game files, **emulated and 0 % native by design**. It is new: no export of it exists before 1.7.0, so
nothing is upgraded, and it takes no part in the shared base of paths or in the qualification matrix. The measures of native code and CPU fidelity do not apply to it; gameplay is
validated game by game (the owner played ten prototype executables, a play trial) and physical latency is not measured. ScummVM and Retro-Recomp's patch of it are under the GPL
(version 3 or later), kept apart from the MIT code and carried with a written offer of the source ([licenses/scummvm.md](../licenses/scummvm.md)); Windows is built and Linux is
witnessed on one small game.

**What moves.** Computed with `compilation_inputs.role_stamps` of the fourteen machines on the tree of `main` before this merge (`f03a713e`) and on this tree (first twelve
hexadecimal digits of each stamp, 6 November 2026):

| Machine | Game stamp (before, after) | Host stamp (before, after) | Build stamp |
| --- | --- | --- | --- |
| Master System | `49fe6e32e245`, `ffb447e12968` | `52732894c705`, `4c698ce40729` | same |
| Game Gear | `8c00b18cbb84`, `9f3d2cd547bb` | `12ddf0d7f71c`, `9e302b729213` | same |
| Game Boy | `84ee8993f728`, `1c847126de1d` | `cf765eccafd3`, `d03f39763f54` | same |
| NES | `70294cfa87ce`, `88240b6d2e3b` | `71877ffa5602`, `a91c8c6c0d28` | same |
| Mega Drive | `a51188bb861f`, `3c62c2e5c7a3` | `81f2da5cd72d`, `b45d74b5e78f` | same |
| Super Nintendo | `183e40e13480`, `0bc2b194ed99` | `86e398dab378`, `ebe78ef356a1` | same |
| Neo Geo | `dc211c9479da`, `328279cbfc1c` | `b7fe8c803579`, `098ae12034e1` | same |
| X68000 | `ad8e4bc0f227`, `d42bb1882a76` | `1ca7429d24bd`, `4cc410c21d5a` | same |
| CPS-1 | `da3f9a93f08f`, `2d6bdc5b1ca4` | `075e0ff74ad2`, `ff2e8295501f` | same |
| CPS-2 | `d0dfdf7fcd0a`, `b841f976989c` | `6d09623637fd`, `7f31bbdfb091` | same |
| PC Engine / TurboGrafx-16 | `61785d10f6b3`, `78f5641c38ec` | `e688aeb8d524`, `bdcc346995e1` | same |
| Game Boy Advance | `a8f3639ad2c9`, `05e06c23687a` | `f91cddfbe6b9`, `f94b7ff7c92f` | same |
| Amiga | `c7a44bc35458`, `a82d6ccb72ca` | `8e7c7e682d10`, `136af9f804ed` | same |
| Adventure (ScummVM) | new, `c7d5b2bf31be` | new, `4a96d24af08d` | new, `1b3f09984ccc` |

Five fixes made before publication move only the stamps of the machine they belong to: the Amiga's availability check (native files only, so a packaged
converter offers the profile), its decoder reading the working folder and resload_Abort said in words give the Amiga the game stamp `ff35e3b8af69`; the ScummVM patch that leaves no route to a modal window, and the folder scan that
refuses with a sentence when the build tools are missing instead of starting a build, give Adventure (ScummVM) the game stamp `be8047b230ac` and the build stamp
`97d9ad0da628` (the released tree). The CPS EEPROM writer's two flags and spin lock go through the Interlocked functions under Visual Studio
(the fallback toolchain compiles C11 atomics only with an experimental switch, so every CPS-1 and CPS-2 conversion failed
there; the portable clang and GCC keep `<stdatomic.h>` and the same code): the game stamps of the CPS-1 `b2ef983bc3fd` and the
CPS-2 `71a11548e45d`, which were moving in 1.7.0 already. On Linux a second Game Boy Advance player preparation no longer rewrites its three embedded resource files with equal bytes
(found by the Linux CI): the Game Boy Advance game stamp in the table above is the released one.

**The game stamp and the host stamp of the thirteen earlier machines move again** (`retrorecomp/batch.py` and `report_schema.py` are game inputs of every machine, and
`THIRD_PARTY_NOTICES.md` and the new licence pages are host inputs); no build stamp moves for them. This adds no conversion on top of 1.7.0: against `v1.6.9` every game stamp had already
moved (the index above). The ScummVM stamps are new.

**Quick states.** No key moves: no native file listed in a key changed, and the ScummVM exports have no F8/F9 state of ours (a game's saves are ScummVM's own, in `datas/`).
**Cartridge saves** of the other machines are kept.

**Not measured.** The speed of a ScummVM game, a Linux run of any engine family but the one witnessed, and the cost of the new test in `batch.py`.

## Capcom CPS-2 leaves the experimental status (1.7.0)

The CPS-2 (profile `cps2`, [CPS2.md](CPS2.md)) is a supported machine, the decision being the owner's ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). What moves,
computed with `compilation_inputs.role_stamps` on the commit the branch was cut from (27e30e03) and on the branch `spec/cps2-exit-170` (first 12 hexadecimal digits of each stamp):

| Console | Game stamp | Host stamp | Build stamp |
|---|---|---|---|
| sms | 3e16a0301d90 → 3e16a0301d90 (same) | 1b834d7b9fbc → 013be1c42081 (moves) | same |
| gg | 4f9d69e86e89 → 4f9d69e86e89 (same) | c9e0e360f031 → 69bcb747bee3 (moves) | same |
| gb | ff30f88ca9f1 → ff30f88ca9f1 (same) | 772d06158394 → d7f2d1b91dbd (moves) | same |
| nes | a3537f590fcf → a3537f590fcf (same) | 21b599f4ec81 → 09e18a69af7c (moves) | same |
| md | a0de8eae71a4 → a0de8eae71a4 (same) | 7bda64083b03 → 774f6daae149 (moves) | same |
| snes | ae2146874e49 → ae2146874e49 (same) | 2a4bc2c7b468 → 423b38546baf (moves) | same |
| ng | a3733e1113ff → a3733e1113ff (same) | 1f2e8a0e2450 → 76460953331d (moves) | same |
| cps1 | e6380523c2d1 → aa1a80f01e09 (moves) | 0f8432dcd5c5 → a01cacaa9528 (moves) | same |
| x68 | 6c7509bf49d2 → 6c7509bf49d2 (same) | 47212d53043d → 1d8e4c116284 (moves) | same |
| cps2 | 8d2c63c4b35a → 34899059c985 (moves) | 0f2bade664f6 → 14e9a20d9fe2 (moves) | same |
| pce | c8545bf9018e → c8545bf9018e (same) | 6ea8ea8ac8eb → 9f41cb76dbf1 (moves) | same |

- **Game stamps: only the CPS-1 and the CPS-2 move**; the other nine consoles keep theirs, because `path_profiles.py` is untouched (a CPS-2 path record has an empty layout, checked by
  `cps1_knowledge.validate_record`). **Host stamps: every console moves**, through `artwork.py` (the optional `cover_titles` capability); build stamps do not move.
- **The CPS-1 and the CPS-2 find their box art.** Their profiles name the libretro-thumbnails `MAME` repository, which files its images under MAME's description
  of each set, and the platform numbers of ScreenScraper (6 and 7, read on its system pages) and TheGamesDB (23, "Arcade"). The search uses the optional profile
  capability `cover_titles(path)`: the set's catalogue title, then its parent's, tried after the file's name and the title (a clone shows its parent's box; no list
  of games). For these machines, a repository that files one box under two spellings of the same name ("Street Fighter II - ..." and "Street Fighter II_ ...") no longer
  makes the choice ambiguous when downloading. Replayed over the reports of `Export`, before and after: no choice of another machine changes. `artwork.py` is a host module
  of every console, so every host stamp moves; the game stamps move only for the CPS-1 family. Existing exports get their icon on the next conversion.
- **The EEPROM of the CPS-1.5 and the CPS-2 is saved off the frame path.** A game changes its cells one after another at start and on a coin, and each change
  wrote the file at once, with a flush to disk that can wait a long while on a busy disk (a frame log of `ssf2` showed single frames of several seconds with the disk
  busy, against 36 ms at most without the write). A worker thread now writes the last contents after the EEPROM has been stable for about a second, and play
  ending writes it at once; a stop of the program within that second loses that last change. `native/cps1_persistence.c` is a host file of the CPS-1 family.
- **The CPS-2 game stamp moves**: its report now says `completed` (not `experimental`), its board tier is `supported`, it shares its paths and its
  profile, translations and notices changed. An export of the CPS-2 of 1.6.9 is rebuilt once on its next conversion, with the same code, pictures and sound.
- **The CPS-1 family's game stamp moves** (the CPS-1 and CPS-1.5 share the board model): `native/cps1_machine.c` now includes `native/cps1_cps2_board.inc`, `cps1_knowledge`
  takes the board as a keyword, `capcom_sets` reads a ROM that FBNeo stores twice over. The final A/B comparison of `1941` and `wof` against `main`
  (`tools/ab_conversion.py`): the generated steps, the board folder and every piece of evidence (CPU, RAM, picture and sound hashes, traces, states, the compressed copy)
  are identical; the files that differ are the changed native sources and the new include, `notices.txt` and the receipt, engine and record digests of the report.
- **Hot path of the CPS-1, as in 1.6.9**: nothing new here (the guards of 1.6.9 stay: a branch per bus access, `if (tile_priority)` per tile pixel); its frame cost is
  still to be measured with the comparison of frame costs of the release, on a quiet PC.
- **The CPS-2 shares its paths** like the CPS-1: its record is tied to its own engine identity (`cps2-m68k` and `cps2-z80` digests), points into the decrypted program, and
  holds no key and no ROM byte. None of the sets observes a path, so nothing is qualified.

## Exports of 1.6.7 in 1.6.8

1.6.8 is the release after 1.6.7 (published on 3 November 2026). This section is the index of its changes, one line per section
below, with the stamps that section says move. Each section computed its stamps for its own change alone; the totals are under the table.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Lead: the engine sources and SDL follow their pins in an older library](#lead-the-engine-sources-and-sdl-follow-their-pins-in-an-older-library-168) (with the review retouches at its end) | all nine consoles (`core.py`, `delivery_evidence.py`) | none | no key moves |
| [Game Boy: the state after the boot ROM, the serial clock phase and the sound unit](#game-boy-the-state-after-the-boot-rom-the-serial-clock-phase-and-the-sound-unit-168-gates-g10-and-g11) | Game Boy | none | no key (the Game Boy has none) |
| [Sharp X68000: the picture is converted only when the host reads it](#sharp-x68000-the-picture-is-converted-only-when-the-host-reads-it-168-frame-cost) | Sharp X68000 | none | **`RR_X68K_STATE_ABI` moves**: states of 1.6.7 refused |
| [Super Nintendo: the ROM address without a division, the 65816 stack pages, the SPC700 EI and DI, the evidence](#super-nintendo-the-rom-address-without-a-division-the-65816-stack-pages-the-spc700-ei-and-di-the-evidence-168) | Super Nintendo, Mega Drive, Neo Geo, CPS-1 (`console16.py`) | none | **the Super Nintendo and Mega Drive keys move** (the snesrecomp pin): states of 1.6.7 refused |
| [Mega Drive: the bus layout of the 68000 follows the independent vectors, and the Z80 hash of the report is portable](#mega-drive-the-bus-layout-of-the-68000-follows-the-independent-vectors-and-the-z80-hash-of-the-report-is-portable-168) | Mega Drive (and the X68000 and CPS-1, with no change of behaviour for them) | none | **the Mega Drive key moves**: states of 1.6.7 refused |
| Notices: the SameBoy palette tables of the Game Boy runtime, and the machines no longer called experimental in the notices | none | **host stamp of every console** (`THIRD_PARTY_NOTICES.md` and the licence pages are host inputs) | none |

Taken together (`compilation_inputs.role_stamps` of the nine consoles, the tree of `v1.6.7` against the tree of this release, computed on
4 November 2026): **the game stamp and the host stamp of every console move; no build stamp moves.** `LEGACY_GAME_STAMPS` stays empty, as in
every release since 1.6.4: the pins section changes `core.py`, which every game stamp hashes, and proving that a console's games come out
the same from it would take a real receipt per console. So every export of 1.6.7 is converted again from its paths when it is upgraded.

**Quick states.** The keys move for **the Mega Drive, the Super Nintendo and the X68000**: a quick state written by a 1.6.7 export is refused
cleanly there (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The keys of the Neo Geo, the
CPS-1 and the NES do not move (the files they hash did not change), so their 1.6.7 quick states load. The Master System, the Game Gear and the
Game Boy have no key of this kind. **Cartridge saves** are kept on every console.

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

*Linux keeps NRV packing (measured, 1.6.8).* The start-up cost of UPX `--lzma` on Linux was measured on 4 November 2026 with
`tools/startup_cost.py` (pack `--determinism`, then start `--runs 9`, one pinned core) on a Debian 13 PC (Intel Core i7-6600U, 2015),
four games converted unpacked from the 1.6.8 tree. LZMA makes the files 25 to 50 % smaller (Secret of Mana 6.8 MB against 13.7 MB) but
adds 100 to 150 ms to the start of the small games and **451 ms** to the largest (Kirby's Adventure and Secret of Mana: 0.62 to 0.67 s
against 0.16 to 0.21 s), beyond the margin of about 0.3 s that decided Windows in 1.6.7. So `packing.LINUX_METHOD` stays `'nrv'`; a faster
machine would likely show less, which is not measured. Both methods passed `upx -t` and packed to the same bytes twice. The tool now
copies with `shutil.copy`, which keeps the executable bit that UPX needs on Linux (it copied with `copyfile`). No stamp moves.

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
**The cause is the colour correction of 1.6.7** ([the intensity bit](UPGRADES_HISTORY.md#sharp-x68000-the-intensity-bit-of-the-palette-lifts-red-green-and-blue-167)),
in this way: until 1.6.6 the core handed its RGB565 buffer to the host as it was, and the conversion to the window's pixels lived in the window kit
(`player_picture`, only reached when a window is open). 1.6.7 moved the work into the core: every frame, `convert_frame` reads the machine's 16-bit
colour word of each pixel, looks it up in a 65,536-entry table and writes a 32-bit pixel, whatever the host does with the picture. A headless run
(the benchmark, a user's `--headless`) reads nothing, so it paid 65,536 lookups, loads and stores a frame
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
expected not to be more expensive than in 1.6.6 (a table lookup in the core and a plain copy in the kit, against three multiplications and divisions per pixel in
the kit), not timed. In a window in fast forward the core converts every frame while the kit reads one in eight: that is outside the measured path, left as it is.

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

## Mega Drive: the bus layout of the 68000 follows the independent vectors, and the Z80 hash of the report is portable (1.6.8)

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
