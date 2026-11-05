# Qualification record

Per-console qualification record for Retro-Recomp. The rules every change
follows and the "supported" checklist are defined in
[STANDARDS.md](STANDARDS.md#supported-checklist); the gates G1-G16 below are
short names for that checklist, numbered by the 27 October 2026 pipeline
inventory. This page records the current status matrix and the
owner-acceptance log. It makes no claim beyond them.

## Leaving the experimental status

The bar to leave `experimental` stays very high: every gate is proved, and no gate is relaxed to get there. The final decision is
always the maintainer's own: he decides whether a machine leaves the experimental status, on the panel criterion (G12) and on his
dated acceptance, worded as he gave it (G14). No tool and no agent fills G14, or moves a profile to `supported`, without his explicit
yes.

## Gates

| # | Gate | Short name | Defined by |
|---|---|---|---|
| G1 | Scope and status stated consistently | Status | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G2 | Report contract | Report | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G3 | Native coverage on every final scenario | Native code | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G4 | CPU fidelity: fresh reference run | CPU check | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G5 | Packed replay of the delivered file | Delivered file | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G6 | Fresh-process states | States | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G7 | Saves | Saves | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G8 | Liveness | Liveness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G9 | Route depth | Route depth | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G10 | Independent CPU evidence | CPU vectors | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G11 | Independent hardware evidence | Hardware proof | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G12 | Panel | Panel | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G13 | Cross-OS witness | Cross-OS | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G14 | Owner acceptance | Owner OK | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G15 | Honesty | Honesty | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G16 | Shared-knowledge safety | Shared hints | [STANDARDS.md](STANDARDS.md#supported-checklist) |

## Status matrix (27 October 2026; the X68000, CPS-1, NES and Game Boy columns, and G5 and G8 of the Master System, Game Gear, Super Nintendo and Neo Geo, of 1 November 2026; G8 and G10 of the Neo Geo of 2 November 2026; G10 of the Game Boy and G14 of the NES, CPS-1 and X68000 of 3 November 2026; G1 to G4, G13 and G15 of the Game Boy, G1, G7 to G10 and G15 of the Super Nintendo and G8 of the Mega Drive of 4 November 2026; G14 of the X68000 of 5 November 2026)

### Progress through the qualification list

<!-- qualification-gauges:begin (written by tools/qualification_gauges.py: edit the matrix in letters, not this block) -->

One line per console: how many of the gates that apply to it are met (a half for a partial
one). `unknown` and `no` count 0 and `not applicable` is left out. It is **approximate and not a quality score**: it does not mix the five
measures (native code, CPU fidelity, hardware fidelity, gameplay validation, physical latency), which stay separate in every report, and a
console's status is never a threshold of this bar: leaving the experimental status is the owner's own decision (G14, see
[Leaving the experimental status](#leaving-the-experimental-status)). The status column is read from the profile registry.

| Console | Status | Progress | Gates |
| --- | --- | --- | --- |
| Master System | supported | `██████░░░░` 63 % | ✅ 5 · 🟡 9 · ❔ 1 |
| Game Gear | supported | `██████░░░░` 60 % | ✅ 4 · 🟡 10 · ❔ 1 |
| Game Boy | supported | `█████████░` 91 % | ✅ 14 · 🟡 1 · ❔ 1 |
| Nintendo NES | supported | `█████████░` 91 % | ✅ 13 · 🟡 3 · ❔ 0 |
| Mega Drive | supported | `████████░░` 84 % | ✅ 11 · 🟡 5 · ❔ 0 |
| Super Nintendo | supported | `█████████░` 88 % | ✅ 13 · 🟡 2 · ❔ 1 |
| Neo Geo | supported | `█████████░` 94 % | ✅ 14 · 🟡 2 · ❔ 0 |
| Capcom CPS-1 | supported | `█████████░` 90 % | ✅ 12 · 🟡 3 · ❔ 0 |
| Sharp X68000 | supported | `█████████░` 93 % | ✅ 13 · 🟡 2 · ❔ 0 |

**The matrix, with symbols** (the letters below are its source): ✅ met, 🟡 partial, ❌ no, ❔ unknown, ➖ not applicable.

| Gate (short name) | Master System | Game Gear | Game Boy | Nintendo NES | Mega Drive | Super Nintendo | Neo Geo | Capcom CPS-1 | Sharp X68000 |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| G1 Status | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G2 Report | 🟡 | 🟡 | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ |
| G3 Native code | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G4 CPU check | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G5 Delivered file | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G6 States | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G7 Saves | ➖ | ➖ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ |
| G8 Liveness | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G9 Route depth | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| G10 CPU vectors | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | 🟡 |
| G11 Hardware proof | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 |
| G12 Panel | ✅ | 🟡 | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ |
| G13 Cross-OS | 🟡 | 🟡 | ✅ | ✅ | 🟡 | 🟡 | 🟡 | 🟡 | ✅ |
| G14 Owner OK | ❔ | ❔ | ❔ | ✅ | ✅ | ❔ | ✅ | ✅ | ✅ |
| G15 Honesty | 🟡 | 🟡 | ✅ | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ |
| G16 Shared hints | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ➖ |

<!-- qualification-gauges:end -->

<details>
<summary>The matrix in letters: the source that the tools read</summary>

`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable. Consoles:
sms = Master System, gg = Game Gear, gb = Game Boy, nes = Nintendo NES,
md = Mega Drive, snes = Super Nintendo, ng = Neo Geo, cps1 = Capcom CPS-1,
x68 = Sharp X68000.

| Gate | sms | gg | gb | nes | md | snes | ng | cps1 | x68 |
|---|---|---|---|---|---|---|---|---|---|
| G1 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G2 | P | P | Y | Y | P | Y | Y | Y | Y |
| G3 | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G4 | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| G5 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G6 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G7 | - | - | Y | Y | Y | Y | Y | - | Y |
| G8 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G9 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G10 | Y | Y | Y | Y | P | Y | Y | Y | P |
| G11 | P | P | P | P | P | P | P | P | P |
| G12 | Y | P | Y | P | Y | Y | Y | Y | Y |
| G13 | P | P | Y | Y | P | P | P | P | Y |
| G14 | ? | ? | ? | Y | Y | ? | Y | Y | Y |
| G15 | P | P | Y | P | P | Y | Y | Y | Y |
| G16 | Y | Y | Y | Y | Y | Y | Y | P | - |

</details>

### Caveats

- CPS-1 (29 October 2026): G3, G8 and G9 moved from `P` to `Y` on the evidence of the section below (26 sets, one tree). G9 `Y`
  rests on captures inspected by the specialist agent, not by the owner. G10 is `Y` since 1.6.6 (both CPUs replay independent vectors; the Z80 core is corrected in the converter's copy and only the `SCF`/`CCF` X and Y flags
  remain). G11 and G13 stay `P` with fresher evidence (1 November).

- CPS-1 (1 November 2026): the profile is `supported`. G12 moved from `P` to `Y` on the owner's choice of criterion 1 ("every set of
  the perimeter he owns is converted and validated": 26 of 26); the two boards and the 20 mappers the panel does not cover are noted in
  [CPS1.md](CPS1.md#panel-coverage). G14 is `P`: the owner accepted the exit from the experimental status on the evidence, and the play
  trial list is still to do on the 1.6.6 executable (see *Owner acceptance*). G16 is `P`: the paths are numeric, rechecked and retried
  without hints, but no CPS-1 path is qualified yet and CPS-1 stays in the experimental tier of the shared base (a tier of the base, not the machine's status). G13 stays `P`
  (three sets of 26 on Debian 13; interactive play on Linux not witnessed).

- X68000 (1 November 2026): G2 and G9 moved from `P` to `Y` on the evidence of the section below (1.6.6 tree). G9 `Y` rests on the
  four risk cases and on captures inspected by the specialist agent, not by the owner; the thorough level (36,000 frames) was not run.

- X68000 (5 November 2026): the profile is `supported` since 1.6.9. G14 moved from `P` to `Y` on the owner's decision of 5 November 2026
  (quoted in *Owner acceptance*), taken with G10 and G11 still `P`: 22 vectors of undefined decimal arithmetic, and MAME on five games
  with the sound not compared. The Mega Drive stands with G10 `P`, and every supported machine with G11 `P`. The scope and the follow-ups are
  in [the exit section](#sharp-x68000-scope-and-follow-ups-at-the-exit-5-november-2026).

- The G5 and G6 rows say "met" where the check exists as a campaign step.
  Only ng, cps1, (since 1.6.5) x68 and (since 1.6.6) md, nes and gb run G5 inside every conversion (sms and gg too, but only
  with the banked engine, see below), and ng, cps1, x68 and (since 1.6.6) nes and gb run G6 inside every conversion. Read G5 and G6
  as "met per conversion" only for those.
- Game Boy (1 November 2026): G5 and G6 `Y` per conversion, G7 `Y`, G8 `P`. G5: after the lockstep comparisons the compressed copy is
  replayed on the same routes and must give the same verdict line (`retrorecomp/gameboy_delivery.py`; [UPGRADES_HISTORY.md](UPGRADES_HISTORY.md#game-boy-the-packed-replay-and-the-liveness-record-166-gates-g5-and-g8)).
  G6: every conversion checks the quick states in a fresh process, and `tools/gameboy_states_check.py` does it on an authored
  cartridge and on Super Mario Land. G7: `tools/gameboy_saves_check.py` on six cartridges written for it ([GAME_BOY.md](GAME_BOY.md)).
  G8 is `P`: the liveness record exists on every conversion, but no campaign of captures was inspected for the Game Boy.
- Game Boy (4 November 2026): G1, G2, G3, G4, G13 and G15 moved from `P` to `Y`; G11 stays `P`. Evidence in [GAME_BOY.md](GAME_BOY.md#the-sixteen-gates-with-their-evidence-167):
  G1 `tools/status_lint.py` shows 0 contradictions and 0 drift items; G2 the report of every one of the twelve campaign games has the SM83's counters per route and the mapper and the sound unit as devices
  that state they are C models, with `hardware_fidelity_validated: false` (like the NES, with no counter for a device that runs no program); G3 no interpreter instruction on any final route of the twelve
  games, the writable code run one by one listed per game (Wario Land II 925,868 instructions, the others 0 to 77,317), the native count and the fallback percentage stay unknown; G4 the CPU,
  memory, picture and sound of native code and interpreter equal over every route of the twelve games at the extended level (the long route over its first 3,600 of 18,000 frames) and, since 1.6.8, on the
  151 of the 152 test ROMs frame by frame plus one documented divergence (`oam_bug` 7, first version, at step 6,717,022); G15 the audit of 3 November repeated on every public line that names the machine (README, documents, eight interface languages, converter strings), no claim of exactness,
  zero latency or hardware fidelity found. Limits: G4 is agreement of two executions of the same machine model, not an independent oracle (G10 is); the long route is compared on its first 3,600 frames;
  the audit is a search of the words of exactness, accuracy and completeness with the matches read, not a reading of every page. **G11** stays `P`: Mooneye passes 94 of 94 applicable tests since 1.6.8 (the state
  after the boot ROM now matches the DMG ABC) and `dmg_sound` 18 of 24, but the three wave-channel tests of each version fail, `oam_bug` `7-timing_effect` gives no verdict and no hardware capture was made.
  **G13** `Y`: Windows and a Debian 13 PC convert the twelve games of the campaign from the same tree (`5ff5595`, quick level, empty library) and give equal per-frame traces (picture, sound, work RAM, program counter) and final
  states on 48 of 48 routes (280,800 frames per system); the generated sources are equal but the embedded resources. Limits: twelve of the 606 cartridges, the quick level, four routes each, no thorough run, no comparison with a console.
- NES (1 November 2026): G2, G3, G4, G7, G8 and G9 moved from `P` to `Y` on the evidence of the section *Nintendo NES: evidence behind
  its column* below (campaign of eight games at the thorough level, delivered-file checks, captures). G9 `Y` rests on pictures
  looked at by the specialist agent, not by the owner. G12, G13 and G15 stay `P`, G14 stays `?`.
- Game Boy (3 November 2026): G8 and G9 moved from `P` to `Y` on the campaign of twelve games of 1.6.7 at the extended level
  ([GAME_BOY.md](GAME_BOY.md#the-campaign-of-twelve-games-167-gates-g8-and-g9)): every game `supported`, full CPU comparison, the
  compressed copy identical, no interpreter cycle, states checked. Play is reached on six games (Tetris, Wario Land II, Mega Man V, Contra,
  Exodus, Veediots); the six others show liveness only (a pause, a first room, menus). The sheets were looked at by the specialist agent,
  not by the owner; not full games.
- Game Boy (3 November 2026): G10 moved from `P` to `Y` on two independent pieces of evidence: the 404,358 SingleStepTests vectors on plain memory (402,589 match the
  interpreter, all of the RAM executors'), and the public test ROMs run on the delivered files ([GAME_BOY.md](GAME_BOY.md#the-public-test-roms-of-blargg-and-mooneye-167-gates-g10-and-g11)):
  blargg `cpu_instrs` 11 of 11, `instr_timing`, `mem_timing` 6 of 6, and Mooneye's instruction, interrupt, HALT and timing tests, each with the native code and the pinned interpreter
  equal step by step for the whole run. Limits: `STOP` is covered by neither (the vectors differ by convention, `cpu_instrs` leaves it out), the test ROMs ran at the quick level,
  one conversion each, and one lockstep stops early on a ROM that gives no verdict (`oam_bug` `7-timing_effect`, listed in [KNOWN_FAILURES.md](KNOWN_FAILURES.md)). G11 stays `P`: on 3 November Mooneye
  passed 92 of 94 applicable tests and the sound unit failed 18 of the 24 `dmg_sound` tests (figures of 1.6.8 in the next entry); no hardware capture was made.
- Mega Drive (4 November 2026): G8 moved from `P` to `Y` on the liveness record read on 14 conversions (28 routes) and the captures of 11 games
  ([below](#mega-drive-evidence-behind-its-column-4-november-2026)); the routes that rest on a menu are listed there. G2, G10, G11 and G13 stay `P` with
  fresh evidence and a precise list of what is missing. The captures were looked at by the specialist agent, not by the owner.
- NES (3 November 2026): G13 moved from `P` to `Y`: the eight games of the campaign, converted on Windows and on Debian 13 with the same
  engine revision and the same native sources, give identical per-frame traces and sound on all six routes of 3,600 frames (48 routes). See the row of the NES table below.
  The panel of ten mapper families of 1.6.7 passes at the thorough level (G12 stays `P`: the panel size policy is not decided). A defect of
  the quick-state writer found on the way (the PRG register was not saved, 1.6.5 and 1.6.6) is described in [UPGRADES.md](UPGRADES.md).
- Master System and Game Gear (1 November 2026, completed 2 November): G5 is `P` for both. The compressed copy is replayed by both
  engines since 1.6.7: the banked engine compares it with the fresh reference of each route, the "functions" engine (which has no
  per-route reference) with the final pass of the same build, and the report says which (`packed_replay` for the functions engine). What
  is recorded is synthetic tests (`tests/test_sega_evidence.py`), runs on three banked games and 18 + 3 + 15 functions conversions
  ([UPGRADES.md](UPGRADES.md#master-system-and-game-gear-the-functions-engine-replays-the-delivered-copy-and-starts-from-the-reset-state-167)),
  not a result per console. The Game Gear was `Y` before; nothing recorded separated the two consoles, which share the engine and the adapter.
  G6 is judged on the banked engine, the default: the "functions" engine has no quick states ([MASTER_SYSTEM.md](MASTER_SYSTEM.md)),
  so it has nothing to check and is not claimed.
- Super Nintendo and Neo Geo (1 November 2026): G8 moved from `Y` to `P`. The Super Nintendo has a liveness check for the cartridges
  with a coprocessor only (`supernintendo.validate_device_liveness`), none for an ordinary cartridge; the Neo Geo has no liveness record
  yet (`retrorecomp/neogeo_conversion.py` uses `deliver_packed` and `replay_routes`, not `liveness_summary`). See the section
  *Shared evidence helper*.
- Super Nintendo (4 November 2026): G1, G7, G8, G9, G10 and G15 moved from `P` to `Y` on the evidence of the section *Super Nintendo: evidence behind its
  column* below (twenty-four conversions of two trees, the vectors of both CPUs, captures of the routes inspected by the specialist agent, not by the owner). G8
  returns to `Y` after its move to `P` of 1 November. G11 stays `P`, G14 stays `?`. G13 stays `P` with fresh evidence: four games, 12 routes of 12 identical between Windows and Debian 13 (see the section).
- Neo Geo (2 November 2026): G10 moved from `P` to `Y`. Both CPUs replay independent vectors through the Neo Geo generator, the same ones
  as the CPS-1 and with the same figures ([NEOGEO.md](NEOGEO.md#qualification), [NEOGEO_LOG.md](NEOGEO_LOG.md)). 68000
  (`tools/neogeo_vector_selftest.py`): the three SingleStepTests fixtures (834 + 2,171 + 864 vectors, the 82 authored cases included) all run
  as native steps; the native steps agree with 3,867 of 3,869 on registers, SR, PC, written bytes and clocks. Z80
  (`tools/neogeo_z80_vector_selftest.py`): 51,328 vectors through `neogeo_z80.generate` and the Geolith core corrected in the converter's copy
  (`neogeo_z80.FIXES`), 49,685 as native steps below `0xf800` and 1,643 through observed RAM variants; native and interpreted identical on every
  vector, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle. **Reserves, written as they are:**
  (a) the two authored 68000 vectors that set the trace bit, which neither path delivers (the Neo Geo Musashi is built without trace);
  (b) the 68 Z80 vectors that differ are the X and Y flags of `SCF` and `CCF` and their `DD`/`FD` duplicates (the Q latch of the original chip is
  not carried: a store per instruction and a state field); (c) the shared Musashi, the reference of every conversion, differed from the
  68000 vectors on `DIVU`/`DIVS` flags (and the division clocks), `CHK` flags and clocks and one line-F stack byte; the converter now
  corrects it in its own copy (`retrorecomp/musashi_fixes.py`, 3 November 2026, group `shares:musashi_fixes` of the Neo Geo, CPS-1 and
  X68000 stamps) and the three vector selftests have no known deviation left; N and Z after a divide overflow, and N after a `CHK`
  that does not trap, are undefined on the 68000: the interpreter now gives the values the translated steps give, which are also the
  vectors'; (d) the oracles are MAME (68000) and JSMoo (Z80), not hardware, and the bus is flat: nothing
  of the board, the YM2610, the command latch or the prefetch bus phases.
- Neo Geo (2 November 2026): G8 moved from `P` back to `Y`. The packed replays now run with `--trace` and every `final_checks[]` row carries
  `liveness` with the CPS-1 keys (`frames`, `distinct_pictures`, `picture_changes`, `last_picture_change_frame`, `audible_frames`,
  `last_audible_frame`), counted from frame 1, through `delivery_evidence.py` unchanged (`liveness_summary`, `report_fields`,
  `require_moving_picture`); a route whose picture never changes stops the conversion, as on the CPS-1, and every route of a set is required
  to move (MVS and AES). Read on conversions of the tree: NAM-1975 (7 routes), Puzzle De Pon! (6), Metal Slug 3 (7) and The Irritating Maze
  (4): every route changed its picture on more than a thousand frames and was audible on more than half of them. **Scope:** the record is on
  every conversion from now on; it was read on four sets, not on the 134 identities, and it says that picture and sound change, nothing of what
  they show (the captures of the earlier campaigns are G9's evidence).
- Neo Geo (3 November 2026): G13 stays `P` with fresh evidence. `nam1975`, `mslug3` (SMA) and `twinspri` (2 MiB) converted on Windows and on
  Debian 13 give the same instruction counts, 0 interpreted instructions and the same CPU, RAM, hardware, Z80, picture and sound hashes on all
  19 route rows ([NEOGEO_LOG.md](NEOGEO_LOG.md#cross-os-witness-on-debian-three-sets--3-november-2026)). Three sets of the 134 identities; interactive play
  on Linux is not witnessed.
- G14 for SNES, SMS, GG and GB means "no recorded owner
  decision found", not proof that none exists. The NES, CPS-1 and X68000 play
  tests of 3 November 2026 are in the owner-acceptance table below; the X68000
  one is a passed play test, not a decision to leave the experimental status.

## Shared evidence helper: G5 and G8 (`retrorecomp/delivery_evidence.py`)

Neo Geo, CPS-1 and the X68000 produce the packed replay (G5) and the liveness record (G8) through one
module, and since 1.6.6 so do the Master System and Game Gear, the Game Boy, the Mega Drive and the NES, so a machine
that joins them gives the same evidence in the same shape ([STANDARDS.md](STANDARDS.md) rules 1 and 7). The module
reads rows a machine already writes; it never runs a game.

- **Liveness.** `liveness_summary(rows)` takes one `FrameRow` per frame (picture hash; optionally the sound hash, an
  audible flag, a RAM hash, a program counter) and returns the same nine keys for every machine. A key the machine
  cannot give is `None`, never `0`. `frozen_route` is the one rule that refuses a route whose picture never changed (one
  distinct picture or none); which routes must move stays the machine's call (CPS-1: every route; X68000: the main route
  only, because a game that waits for a click or a key shows a still picture on the others).
- **Report fields stay each machine's own.** The common keys are `frames`, `distinct_pictures`, `picture_changes`,
  `last_picture_change_frame`, `audible_frames`, `last_audible_frame`, `distinct_sound_blocks`, `distinct_ram_states` and
  `distinct_program_counters`. CPS-1 reports the first six (`final_checks[].liveness`). The X68000 reports `frames`,
  `distinct_pictures`, `distinct_audio_blocks` (= `distinct_sound_blocks`), `distinct_ram_states` and
  `distinct_program_counters`, then `nonblack_frames` and `nonzero_samples` from its replay report (`liveness[]`). Frame
  numbers are the machine's own: CPS-1 and Neo Geo count from 1, the X68000 from 0. Neo Geo reports the CPS-1 six keys (`final_checks[].liveness`).
- **Packed replay.** `deliver_packed` compresses a copy of the build as publication does and takes its SHA-256 before any
  replay; `replay_packed` (or `replay_routes` where the machine's callback compares by itself) replays that copy on every
  route and compares it with the fresh reference. `native_validation.packed_reference_match` and
  `packed_candidate_sha256` are written from the delivered file (`validation_fields()`, `report_fields()`); the first
  refuses to be written before every route matched. Since 1.6.7 a compressed copy that fails its replay on the converting
  system is replaced by the build as built and every route is replayed again on it; if that passes, the compressed copy is
  replayed once more on the first route that failed, and only a failure that is reproduced is blamed on the compression: the
  unpacked file is then delivered and reported as such (`packing.unpacked_reason`). A failure that does not reproduce, or a
  build that fails too, raises the first error ([BUILDING.md](BUILDING.md)). It is the same file that passed every route that
  is delivered, packed or not.

The Master System and the Game Gear use it since 1.6.6 (`retrorecomp/sega_evidence.py`): the runner's `--vdp-trace` has two more
columns, `psg_h` (hash of the PSG's stereo samples of the frame) and `psg_nz` (their non-zero count), written only when a trace is
written; every conversion records `final_checks[].liveness` per route (picture from `pixels_h`, sound, RAM; no program counter, so that
key is None) and refuses a conversion whose main (`play`) route never changed picture; the banked engine also replays the compressed
copy of the build on both routes against the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`).
Both engines have the liveness record and the packed replay (the "functions" engine compares the copy with the final pass of its own
build). G8 is `P` for both columns: the record exists on every conversion, but the captures were not inspected as a campaign and the
risk cases were not run to play. G5 stays as recorded: the replay is in the conversion for every game, run on three banked games and
on the functions batches here.

The NES uses it since 1.6.6 (`retrorecomp/nes_checks.py`, `retrorecomp/nes.py`): the headless `--hash-out` line of the exported
game carries `pic=` (the hash of the rendered 256 x 240 picture), `snd=` (the hash of the frame's sound) and `aud=` (1 when a
sample was not zero), the liveness record of each route is read from it, the delivered copy is replayed on every route and its
trace and PCM compared with the fresh reference, and the machine is in the `conversion_gates` group.

The Super Nintendo uses it since 1.6.7 (`retrorecomp/snes_evidence.py`), for every cartridge with or without a coprocessor, as the Mega Drive does
(`megadrive_evidence.py`): the 16-bit host's `--trace` line (frame, picture hash, counters, sound hash) feeds the same record, a frame is audible when its
sound hash is not the hash of silence for its number of samples (since 1.6.8, as the Neo Geo and the CPS-1 do; the host writes no extra column), the
program counter is `None`, and `frozen_route` refuses a `play` route whose picture never changed (the other routes may sit in a menu). The record is in
`final_checks[].liveness` of every conversion, with the route's own `pcm_nonzero` and `visible_frames`; `supernintendo.validate_device_liveness` still
judges the cartridges that have a counted device.

The packed replay (G5) needs, for each machine, a callback that starts the compressed copy with the same arguments as the
probe that made the reference and compares the same fields (Mega Drive and Super Nintendo: `reference_differences`;
Master System and Game Gear: `compare_execution`; NES: the `.hash` lines and the PCM; Game Boy: the verdict line of the
build), and the group `conversion_gates` in the machine's `stamp_groups`.

## Sharp X68000: evidence behind its column (29 October 2026, status of 1 November 2026)

The X68000 is **supported** since 1.6.9 (owner's decision of 5 November 2026, [below](#sharp-x68000-scope-and-follow-ups-at-the-exit-5-november-2026)). This is what each gate rests on today and what is still missing, with the file that
shows it. `P` means a part is shown and the rest is named; nothing here says exact hardware, gameplay coverage or latency.

| Gate | X68000 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/x68000.py` (status `supported` since 1.6.9), [X68000.md](X68000.md), `tests/test_system_profiles.py`, `tools/status_lint.py` | |
| G2 | Y | Common report v2 (`report_schema.py`, `tests/test_report_schema.py`, golden `tests/x68000_common_golden.json`). Since 1.6.6 the sections are filled from the conversion itself: `cpus` (one 68000, native and interpreted counts per route), `validation.cpu_fidelity` (digests of the CPU, RAM, image and PCM traces per route), `scan.routes` (frames, steps and script digest of each exploration route), `states.validation` (fresh process, compressed copy, the frame of the save and the 400 continued frames), `saves`, `input_players`, `peripheral`, `packed.replay` | `devices` is empty and there is no audio CPU section: the machine has no cartridge device and its sound is part of the reference machine, so a counter per device does not apply. `saves.validation.checked_in_this_conversion` is false (the proof is the test and the tool named there, not a step of the conversion) |
| G3 | Y | `final_checks[].interpreted_opcodes` is 0 on the main, mouse and keyboard routes of the four risk cases (below) | Only on the routes run |
| G4 | Y | A fresh interpreted reference per conversion, trace equality (`native_validation.reference_match`, `tests/test_x68000_conversion.py`) | |
| G5 | Y | The compressed copy is replayed on every route against the same reference (`packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/x68000_conversion.py`); R-Type, Metal Sight, Lemmings and Super Hang-On matched on 3 routes each | The published file is compressed again by `publishing.py` (UPX is deterministic: the SHA-256 recorded in the report equals the published one on the run checked); on Debian the compressed copy of Choujin stops at start and is refused (the panel row below) |
| G6 | Y | F9 in a fresh process and the early floppy DMA, now on the compressed copy (`state_checks`) | |
| G7 | Y | `tests/test_x68000_payload.py`: a played disk survives every start and a second build of the same machine identity; a disk of another size, a missing one or a folder in its place is moved to `<name>.unusable-N` and replaced from the executable; a changed host file is treated the same way; the game always starts. `tools/x68000_saves_check.py` on a real game (below): the game wrote to its disk, a relaunch and a second conversion found it as it was | The writes found are file time stamps of 4 to 12 bytes (below): no game was seen saving a score or a position on purpose, which needs play beyond the routes |
| G8 | Y | `liveness` in every report, per route and for the delivered file; captures looked at; the four risk cases below reach play, R-Type and Metal Sight on the standard routes, Lemmings and Super Hang-On on authored routes (`tools/x68000_play_routes.py`) | Scope: the four risk cases, not every set of the panel. 8 of the 84 reviewed mouse sets make no sound on any standard route and 15 show a still picture on the 4,000-frame main route, which a click or a key wakes on another route (Route rules, below) |
| G9 | Y | The four risk cases were converted at the extended level (main, mouse, keyboard and one 18,000-frame pseudo-random route), 0 interpreted opcodes on every route, the compressed copy matching the reference on the four routes (table below); play is reached on the delivered file for R-Type and Metal Sight (standard and long routes), for Super Hang-On (long route, and its authored route) and for Lemmings (authored route; its standard and long routes stay on the menu) | Inspected by the specialist agent, not by the owner; four games, not the 84 mouse sets; the thorough level (36,000 frames) was not run; not full games |
| G10 | P | The 3,869 SingleStepTests vectors (834 shift, 2,089 prefetch plus 82 authored cases, 864 exception) replayed through the X68000 generator and through the same Musashi interpreting every instruction: the translated steps agree with every vector on registers, SR, PC, written bytes and clocks, and the Musashi reference agrees with them too since 3 November 2026 (`retrorecomp/musashi_fixes.py`, the correction shared with the CPS-1 and the Neo Geo) (`tools/x68000_vector_selftest.py`, `tests/test_x68000_vectors.py`, [CPU_68000.md](CPU_68000.md#tests-and-vectors)); Musashi as the reference, 20 authored CPU guards (`native/x68000_native/guard_checks.c`, `tools/x68000_native_check.py`); a fourth fixture, the 2,895 vectors of 85 instruction groups no other fixture holds (`m68k-groups`, 3 November 2026): every vector runs as a native step and every total of clocks equals the vector's, on the native steps and on Musashi alike. The state first agreed for 2,862 vectors natively and 2,883 on Musashi; since the X68000, the CPS-1 and the Neo Geo apply the Mega Drive's state rules for `LINK A7`, `UNLK A7` and `NEGX` to their translated steps (`retrorecomp/m68000_state_rules.py`) and Musashi pushes `A7` as it was for `LINK A7`, it agrees for 2,873 and 2,889. The rest is recorded (`tests/fixtures/m68k-groups/deviations-musashi-machines.json`, checked by `tools/x68000_vector_selftest.py`: a group that differs and is not listed fails, and so does a count that changes) | The oracle is MAME, not silicon; odd-address and bus errors, `TAS`, `TRAPV` and the interrupt pins are outside the fixtures. The 22 native vectors of the fourth fixture that still differ are the decimal instructions (`ABCD` 2, `SBCD` 2, `NBCD` 18) on operands that are not decimal digits, which the manual leaves undefined (Musashi differs on 6 of them, and the native steps and Musashi differ from each other on 45); they are not modelled. No conversion of the panel showed a native/reference difference |
| G11 | P | Authored video, audio, timing, session and disk vectors (`tools/x68000_*_check.py`); MAME 0.289 (its `x68000` driver, run with the IPL and font ROM it expects: the hashes of the owner's firmware are the ones MAME lists) against the delivered game on five games, no input on either side (`tools/x68000_mame_compare.py`, 2 November 2026): **90 of the 104 pictures of MAME that stand still have the same shape in the game** (R-Type 14 of 16, Lemmings 19 of 24, Star Luster 26 of 31, Quarth 19 of 20, Bubble Bobble 12 of 13), the first 200 frames (the Human68k start-up screen) are identical to the pixel on R-Type, and after the disk has loaded the two emulators advance image for image at a constant lag (665 frames on R-Type) | Sound is **not** compared, and colours only on Bubble Bobble: the palette's intensity bit now lifts the three channels as in MAME (the game's picture is XRGB8888 from the machine's own colour word, UPGRADES 1.6.7) and 97.03 percent of the pixels of its 12 matched pictures are identical to MAME's (93.55 before; the shape match of the tool does not depend on colours); the rest comes from the screen contrast of the system port, applied to the palette by the base but by MAME at display, after the raw screen this tool reads, and from rounding. Of the 14 pictures with no match, 4 are explained (2 of R-Type fall beyond the 3,000 frames captured on the game side, 2 are transition frames that agree on 99.97 percent of their pixels) and 10 are **not explained** (Lemmings 5, Star Luster 4, Bubble Bobble 1). Disks load more slowly in MAME, so the lag is per game and not calibrated. MAME is not hardware and marks its driver imperfect |
| G12 | Y | **The owner chose option B (2 November 2026): 21 named games, each with its written reason, none dropped for failing** (the panel and its rule are [below](#sharp-x68000-the-panel-2-november-2026)); all 21 are converted on Windows (22 conversions with R-Type again at 4 MiB), 0 interpreted opcodes on every route, the compressed copy matching, F8/F9 resumed in a fresh process; the collection holds 418 images, 33 multi-disk sets and 84 reviewed mouse sets | The panel covers the categories it names, not the whole collection; the two sets that used to stop the reference (Tetris v5, TF4G v0.3A09) and Pensan CD (silent on its keys) are in it and convert |
| G13 | Y | Windows and Debian trace hashes (CPU, RAM, picture and PCM, main, mouse and keyboard routes) are equal on the 21 games of the panel (2 November 2026) | One game, Choujin, is delivered on Debian unpacked: its UPX-compressed copy stops at start there, so the shared packing step replays it twice and publishes the validated build instead, with the reason in the report (see [KNOWN_FAILURES.md](KNOWN_FAILURES.md)); its hashes equal those of Windows |
| G14 | Y | Play test passed on 3 November 2026 (five games); five more games, drawn at random, played on 5 November 2026 (Double Target, Fancy Qix, Twins, Danger Area, Pac-Land, converted with the 1.6.8 tree), and the owner's decision of the same day to leave the experimental status (quoted in the owner-acceptance table) | The decision was given with G10 and G11 `P`; it is the owner's and he can revert it. Five games drawn at random and played are not a campaign: no claim of gameplay beyond them |
| G15 | Y | The five measures stay separate in the report and in [X68000.md](X68000.md). Read on 3 November 2026 for this gate: every string of the interface that names the machine, in the eight languages, the README and every public document that names the machine, the local documents (`docs/history/x68000`, the research page, the specifications), the host kit's lines and the report writer. No claim of exact hardware, complete gameplay, zero latency or zero fallback was found; the report now states `universal_zero_fallback_claim: false` like the CPS-1 and the Neo Geo (its common `honesty` block read `null` for it), and the roadmap paragraph that still listed the panel and the Linux comparison as missing was rewritten | The word "exact" appears in the documents for media identities and for redraw marks, never for fidelity; the generic help text of the converter ("sometimes beyond the original machine") is not specific to this machine |
| G16 | - | The X68000 shares no paths yet | |

The four risk cases, converted one at a time with the 1.6.5 tree (standard scan level, `--no-online-cover`, an empty library;
"pictures" is the number of different pictures of the delivered file on the route, out of 4,000 frames unless noted):

| Game | Main route | Mouse route | Keyboard route | Interpreted opcodes | Seen on the captures |
|---|---|---|---|---|---|
| R-Type (Irem) | 1,744 pictures, 2,796 audio blocks | 2,169 / 2,829 | 1,693 / 2,845 | 0 | The game-over screen: play was reached |
| Metal Sight (System Sacom) | 311 / 3,241 | 312 / 3,379 | 127 / 2,745 | 0, 2 automatic disk changes | In play (a mech shooter screen) |
| Lemmings (Imagineer) | 993 / 59 | 5,756 / 9 (10,000 frames, 72,288 mouse reads) | 1,003 / 9 | 0 | The menu, with the mouse pointer and a level name; no level reached |
| Lemmings, authored play route (4,000 frames, quick scan) | 1,238 / 911 | | | 0 | Level 1 ("Just dig!") with its lemmings walking out and the time running: play was reached |
| Super Hang-On (Sharp / SPS) | 74 / 3,131 | 1,939 / 8,638 (10,000 frames) | 74 / 3,131 | 0, no automatic disk change | The title screens; the game was not reached |
| Super Hang-On, authored play route (10,000 frames, quick scan) | 2,432 / 9,083 | | | 0 | The first stage, course Africa, the bike running (score 4,310, speed 93 km): play was reached |

The same four games at the extended level (1.6.6 tree, `--scan-level extended`, an empty library, one conversion at a time; the long route is
one pseudo-random route of 18,000 frames; "pictures / audio" as above; interpreted opcodes 0 on every route, `packed_reference_match` true):

| Game | Long route (pictures / audio) | Native instructions on the long route | Seen on the last capture of the long route |
|---|---|---|---|
| R-Type (Irem) | 5,303 / 13,687 | 263,243,083 | The game's own menu (play, rank, demo, sound test) after the game over of the main route |
| Metal Sight (System Sacom) | 3,843 / 17,186 | 245,481,575 | In play (a mech shooter screen), 2 automatic disk changes on the routes |
| Lemmings (Imagineer) | 11,010 / 9 | 283,177,608 | The title menu: the standard routes do not enter a level, the authored route does (above) |
| Super Hang-On (Sharp / SPS) | 8,042 / 17,130 | 268,313,547 | The first stage, course Africa, the bike running (score 10,170, speed 91 km) |

The two authored routes were run again on the 1.6.6 tree: the same pictures and audio blocks as in 1.6.5 (Lemmings 1,238 / 911, Super Hang-On
2,432 / 9,083), 0 interpreted, packed copy matching. The captures (commercial game pictures) stay outside the repository.

What the games write (G7). A survey of 378 starts (the single-disk sets and the first disk of each other set, 3,000 frames of the
qualification inputs, the fresh reference) found six sets that change their own disk: Cybermission (Login), Darius Dokomade
Tatakaemasuka, F-1 Fastest Lap (Michael Company), Hoippuru X68K, Sekizui Hansha De Acchoo v613.61 and Twin Soul. Each changes 4 to 12
bytes, the time and date fields of a file's directory entry (Human68k stamps a file it opens for writing). On Cybermission,
`tools/x68000_saves_check.py` converted the game, ran its player (12 bytes changed on its disk), ran it again (the disk was
kept byte for byte), converted the game a second time and ran that new player over the same data folder (the disk was kept, and no
second data folder appeared). The other 372 starts left their disk as it was; none of them saves a score or a position without play.

Route rules (what the standard routes wake). The 84 reviewed mouse sets, each run on a fresh interpreted reference on the 4,000-frame
main route (keys and buttons) and on the 10,000-frame mouse route (`tools/x68000_mouse_survey.py`; the reference only, no conversion):
sound on the main route for 70, on the mouse route for 74, on at least one of them for 76 (8 sets are silent on both: Fire, Future Wars,
Ganbare! Paichan, Giga Fight 68K, Last Tempest A, Puzzle (1991), See Through v2, Uno); a picture that still changes in the last 1,000
frames for 69 on the main route and 80 on the mouse route, and for every set on at least one of them. The main route is silent for six
sets that the mouse route makes speak (Pensan CD, Boyon Boyon, Get Ready, Magritte, Oh! Hajiki!, Tonkotsu Pro Roku Hachi Kei) and still
for 15 that the mouse route moves. Carrying the first clicks of the mouse route on the main route would give sound to 75 and a moving picture
to 81, losing Klax's sound and the picture of Tonkotsu Pro and Tower of Druaga, and it would change the main route of every listed set, so it
is not done: the conversion looks for sound on every route it replays instead (`native_validation.sound_routes`, UPGRADES.md). A game that
loads for a long time needs a longer route than the main one: Super Hang-On's title counts down about once a second from 99 while the game
sets up its sound module and takes no start before it reaches 0 (about frame 8,500).

A conversion took 133 to 186 seconds on the Windows build PC with these three routes (the compressed replays are 28 to 39 of
them). Picture and sound changing is not gameplay validation, and a route that stays on a title screen proves only that the
machine runs.

## Capcom CPS-1: evidence behind its column (29 October 2026, status of 1 November 2026)

CPS-1 is **supported** since 1.6.6, on the owner's decision of 1 November 2026 taken on this evidence; his own play trial is still to do. Each gate with the file or measure that shows it and what is still missing; nothing here says
hardware fidelity, gameplay coverage or latency. Details and tables: [CPS1.md](CPS1.md#qualification), dated measurements in
[CPS1_LOG.md](CPS1_LOG.md#29-october-2026-165-tree-the-whole-panel-routes-captures-and-long-routes).

| Gate | CPS-1 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/cps1.py` (status `supported`), README, COMPATIBILITY, INDEX, the interface; `tools/status_lint.py` shows 0 contradictions | |
| G2 | Y | Common report v2 with separate 68000 and Z80 counters (`report_schema.py`) | |
| G3 | Y | `final_checks[].interpreted_opcodes` and `audio_interpreted_opcodes` are 0 on both routes of the 26 sets of the table (29 October, one tree) | Only on the routes run |
| G4 | Y | A fresh interpreted reference per route in every conversion (`final_checks[].reference_match`) | |
| G5 | Y | The compressed copy replayed against the reference (`packed.replay.match`, `packing.compared_on`) | |
| G6 | Y | F8/F9 in a fresh process, damaged state refused (`game_states.validation`) | |
| G7 | - | No non-volatile memory on the standard boards | |
| G8 | Y | `final_checks[].liveness` per route (pictures, last picture change, audible frames, last audible frame) for the 26 sets; a route whose picture never changes is refused | Four attract routes are silent (`dynwar`, `ghouls`, `mtwins`, `unsquad`); every set is audible on its play route |
| G9 | Y | The credited play route of each of the 26 sets reaches play (six captures per set, replayed on the delivered file, inspected); the 18,000-frame route ran on `sf2ce`, `ffight` and `1941` | Inspected by the specialist agent, not by the owner; not full games |
| G10 | Y | 68000: the three SingleStepTests fixtures through the CPS-1 generator, the native steps agree with 3,787 of 3,787 vectors and 80 of 82 authored cases (`tools/cps1_vector_selftest.py`). Z80: 51,328 vectors through the CPS-1 Z80 bodies and the Geolith core corrected in the converter's copy since 1.6.6, native and interpreted identical, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle (`tools/cps1_z80_vector_selftest.py`, `neogeo_z80.FIXES`) | The X and Y flags of `SCF`/`CCF` (the Q latch is not carried: a store per Z80 instruction and a state field); the CPS-1 Musashi is built without trace support (the two authored trace vectors are not delivered by either path); since 3 November 2026 the reference agrees with every other vector (`retrorecomp/musashi_fixes.py`). The groups fixture (`m68k-groups`, 2,895 vectors) was replayed too on 3 November 2026, with the same result as the X68000 and the Neo Geo: all clocks equal, state 2,873 native and 2,889 on Musashi, only the decimal instructions on operands that are not digits differ (`tests/fixtures/m68k-groups/deviations-musashi-machines.json`); the status of this gate is unchanged |
| G11 | P | MAME 0.289 on the 1.6.5 tree (`tools/cps1_mame_compare.py`, 30 October and 1 November): 24 sets comparable, the picture of the attract route identical on all of them, of the credited play route on 23; the sound within 0.42 dB (median level) and 0.99 (averaged spectra) on the 24 | `sf2hf` slips by a frame; two sets need PAL dumps the romsets lack; MAME is not hardware; the waveforms are not claimed equal (OKI interpolation) |
| G12 | Y | The owner chose criterion 1 (1 November 2026): every set of the perimeter that he owns is converted and validated, 26 of 26 (the perimeter has 129 sets) | Not covered by the panel and noted in [CPS1.md](CPS1.md#panel-coverage): the boards `CPS_B_17` (`sf2ua`) and `CPS_B_21_BT5` (`varthj`), 20 of the 45 mappers (seen in sets the collection lacks) |
| G13 | P | Final Fight (27 October), Street Fighter II' Champion Edition (30 October) and 1941 (1 November) give the same CPU, RAM, image, sound and trace hashes on Windows and Debian 13 | Three sets of 26 |
| G14 | Y | Exit from the experimental status accepted by the owner on 1 November 2026 on the evidence of 1.6.6; play trial list passed on 3 November 2026 on the 1.6.7 tree (owner-acceptance table) | |
| G15 | Y | The five measures stay separate in the report and in [CPS1.md](CPS1.md) | |
| G16 | P | Numeric paths, rechecked by every conversion, a failing conversion starts again without them; the sharing can be withdrawn in one line | No CPS-1 path is qualified yet; CPS-1 stays in the experimental tier of the shared base (schema 3 only; a tier of the base, not the machine's status) |

## Nintendo NES: evidence behind its column (1 November 2026)

The NES is **supported within its validated cartridge and peripheral scope**. This is what each gate rests on, with the file or
measure that shows it and what is still missing. `Y` here is the letter the evidence supports; the status matrix above carries these
letters since 1 November 2026. Nothing here says exact hardware, gameplay coverage or latency.

Two trees gave the evidence. The campaign (G3, G4, G9) ran on the 1.6.6 tree before the delivered-file checks existed
(the converter of 30 October plus the PAL NMI change); the delivered-file checks (G5 to G8) ran on the tree that has them, on
the games named in each row.

| Gate | NES | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/nes.py` (status `supported`), [NES.md](NES.md), `tools/status_lint.py` | |
| G2 | Y | Common report v2 (`report_schema.py`): the main 6502's counters per route in cycles (native, interpreted in ROM, in RAM, elsewhere), `native_validation`, `final_checks[].liveness`, `game_states` with its fresh-process check, `ordinary_saves`, `packed` with its replay. The 2A03's APU is part of the CPU and no cartridge device runs instructions, so there is no device or audio-CPU section | Counts are in cycles, not instructions (the generated code does not count them: that would be a cost in the hot path); freshness, the library and the website still read the old keys |
| G3 | Y | 1 November 2026, campaign of eight games at the thorough level (below): 0 interpreted cycles on all 64 routes (8 games, 8 routes each). Ballblazer, the one old report that showed fallback (32,283 RAM cycles, 0.22), converts with 0 on the current tree after one RAM entry is learned | Only on the routes run. Of 45 library traces, 9 games run code from RAM (one to 486 entries each); the others have none |
| G4 | Y at the extended and thorough levels | A fresh interpreter reference per route in every conversion: the CPU trace, the memory and hardware hashes and, since 1.6.6, the hash of every picture and every frame's sound, then the exact PCM. At the thorough level every route is compared whole: 57,600 frames per game, **460,800 frame pairs** over the eight campaign games, all equal. At the default level the reference covers 120 or 600 frames of each 3,600-frame route (`final_checks[].reference_frames` says how many) | The reference is the engine's own interpreter, so this is agreement between two executions of the same machine model, not an independent oracle (that is G10) |
| G5 | Y per conversion | Since 1.6.6 the conversion compresses a copy of the build as publication does, replays it on every route and compares each per-frame trace and the PCM with the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/delivery_evidence.py`). Balloon Fight, Asterix, The Legend of Zelda, Mr. Gimmick, Gumshoe and Castlevania III matched on their three default routes (for Balloon Fight the SHA-256 of the published file equals the replayed candidate's) | Replayed on the routes of the conversion's level, not on every game of the library |
| G6 | Y per conversion | Since 1.6.6 F8/F9 are checked in a fresh process on the delivered file (`retrorecomp/nes_checks.py`, `game_states.validation`): a start and a missing load create no file, two saves of one run are identical, a state loaded in another process continues with the same CPU, memory, hardware, picture and sound (180 frames after a save at frame 600 of the play route), and six damaged states (magic, ABI, ROM identity, region, payload, truncation) are refused without touching either file | |
| G7 | Y | `tools/nes_saves_check.py` on a cartridge written for the check (MMC1, battery RAM, a program that counts its launches): the first launch saves 1, the second finds it and saves 2, a second conversion over the same export leaves the file as it was, and the new build saves 3; the conversion's own probes left no file beside the export. The report says what a game saves (`ordinary_saves`: battery or none, the file's path) | No real game was seen saving a score or a position on purpose: that needs play beyond the routes. The check is a developer tool, not run during a conversion |
| G8 | Y | Every route of every conversion carries a liveness record (`final_checks[].liveness`: distinct pictures, picture changes, last picture change, audible frames, last audible frame, distinct sound blocks, RAM states and program counters) read from the per-frame trace, and the conversion refuses a game whose main route (the right-hand play run) never changes its picture. End-of-route pictures of the eight campaign games were looked at (G9) | A route may rest on a title or a menu. The main route moves, but the record shows how little on some games at the default level: the right-hand run of The Legend of Zelda has 124 different pictures in 3,600 frames, and that of Mr. Gimmick has no sound after frame 181 |
| G9 | Y | The thorough level runs six authored routes of 3,600 frames (boot, two play runs, a menu and dialogue run, a Select and second-player run, a varied movement run) and two pseudo-random routes of 18,000 frames seeded from the exact ROM, 57,600 frames per game. `tools/nes_route_captures.py` replays them on the delivered files and takes the last picture: **all eight games reached play on at least one route**. The Legend of Zelda (the overworld, Link in the field), Mr. Gimmick (the first stage, score 130), Esper Dream 2 (rooms and a dialogue), Gumshoe (a water stage with a score), Front Line (the road, score 300), Commando (the field, then the title with a score of 450: a game over), Castlevania III (stage 1-02) and Kirby's Adventure (Vegetable Valley) | First stages only, not full games. The pictures were looked at by the specialist agent, not by the owner. Kirby stays on its first level on both long routes; Gumshoe's second long route ends on a plain blue picture |
| G10 | Y | The separate TriCNES-derived software oracle on NTSC routes (see the validation sections of [NES.md](NES.md)) | PAL has no independent oracle |
| G11 | P | Authored fixtures of the clock, the APU, the Zapper and the mappers ([NES.md](NES.md#self-tests)) | No external emulator or hardware comparison; fine 2C07 register races and the PAL vblank-clear timing are unconfirmed (NESdev lists it as such) |
| G12 | P | The eight games below, the ten games of the 1.6.7 panel of mapper families (mappers 9, 10, 19, 64, 118, 23, 16, 1 at 512 KiB, 2 in PAL and 69: ten of ten pass at the thorough level, [NES.md](NES.md#panel-of-mapper-families-3-november-2026)), the 1.6.4 player-conditions reconversion of Kirby's Adventure and the earlier qualifications of 8 to 12 October | The panel size policy is not decided |
| G13 | Y | Windows and a Debian 13 PC, each converting the game with the same engine revision and the same native sources at the standard level, replay the six routes of the extended level (boot, two play runs, a menu and dialogue run, a Select and second-player run, a varied movement run; 3,600 frames each) with `tools/nes_cross_os.py`: the per-frame trace (program counter and registers, work memory, mapper, PPU and APU hashes, picture and sound hashes) and the SHA-256 of the 48 kHz sound are identical on all 48 routes of the eight games (The Legend of Zelda, Mr. Gimmick, Kirby's Adventure, Castlevania III, Gumshoe, Front Line, Commando, Esper Dream 2: mappers 1, 69, 4, 5, 66, 0, 2 and 26, NTSC and PAL). Quick states resumed across the Visual Studio and portable-toolchain builds (`tools/nes_state_cross.py`) | The two pseudo-random routes of 18,000 frames of the thorough level were not replayed on Debian, nor the ten games of the 1.6.7 panel; the traces were not compared with a reference console. Six of the eight games had identical native sources on both systems; the exception is Kirby's Adventure and Castlevania III, built with the corrected state writer on Windows only and with the previous one on Debian, which shows that the correction changes no trace |
| G14 | Y | Play test passed on 3 November 2026 (six games, owner-acceptance table) | |
| G15 | P | The five measures stay separate in the report and in [NES.md](NES.md) | The older documents have not all been read for this |
| G16 | Y | Numeric hints, rechecked and retried without hints on a failed conversion; the RAM entries a conversion adds are permissions the guard checks | |

The campaign (`tools/campaign.py`, thorough level, one conversion at a time, seed 166): the five risk cases of
`tools/campaign-risk-cases.json` plus Kirby's Adventure for the MMC3 family (a file kept outside the repository for this run) and two
games drawn at random. Each was chosen for a reason written before the run:

| Game | Mapper | Why | Interpreted cycles | Conversion |
|---|---|---|---|---|
| Castlevania III: Dracula's Curse (USA) | MMC5 | Mapped RAM and extra mapper state | 0 | 970 s |
| The Legend of Zelda (USA) | MMC1 | Battery RAM; code runs from cartridge RAM (1,470 guarded entries at this level) | 0 | 813 s |
| Mr. Gimmick (Europe) | FME-7, PAL | PAL timing and a CPU-clocked IRQ counter | 0 | 1,161 s |
| Esper Dream 2 (Japan, translated) | VRC6 | Extra mapper audio | 0 | 843 s |
| Gumshoe (USA, Europe) | 66 | Zapper input | 0 | 797 s |
| Kirby's Adventure (USA) | MMC3 | The most common board; its PPU-address IRQ counter keeps the direct PPU clock | 0 | 861 s |
| Front Line (Japan) | 0 | Drawn at random | 0 | 403 s |
| Commando (USA) | 2 | Drawn at random | 0 | 399 s |

Eight of eight passed the gates of `tools/release_check.py` (conversion, native and reference agreement, fallback limit). Times
are those of one run on the Windows build PC while other sessions were working: they say how long a thorough conversion takes,
not how fast anything runs.

The checks themselves are run by `tools/campaign.py`, `tools/nes_route_captures.py`, `tools/nes_saves_check.py` and
`tools/nes_state_selftest.py`; none of them needs a ROM in the repository.

### CPS-1.5 (QSound boards): the experimental tier of the CPS-1

Not a column of the matrix: the machine stays `supported` and these boards are a tier of their own (`board_tier: experimental` in their
reports, a column of the catalogue), outside the evidence above. What exists on the 1.6.7 tree, dated 2 November 2026, detail in
[CPS1.md](CPS1.md#cps-15-qsound-boards-experimental-tier) and [CPS1_LOG.md](CPS1_LOG.md#2-november-2026-167-tree-the-cps-15-board-without-its-sound-against-mame):
the Kabuki decryption equal to MAME's on six sets; the pictures of the five sets of the test collection (one per family, of 18) agree with MAME 0.289
on 3,599 of 3,600 compared frames; the sound of the high-level QSound model agrees with MAME's **for the same model**: MAME 0.289 plays these boards with
its high-level model by default, so this validates the port against MAME's model, not against the hardware nor against a run of the DSP16.
The five sets of the test collection convert through the whole chain at the Standard level (0 interpreted instructions on both routes, reference equal to native, states, packed copy; 2 November 2026). Not done: the other 13 sets (not in the test collection), a run of the DSP16, the owner's play trial.

## Super Nintendo: evidence behind its column (4 November 2026, release 1.6.8)

The Super Nintendo is **supported within the boards and the routes below**. This is what the gates that moved on 4 November 2026 rest on, with the
file or the measure that shows it and what is still missing. `Y` is the letter the evidence supports, proposed by the specialist session; the status
matrix above carries the letters the lead has accepted. Nothing here says exact hardware, complete gameplay or latency.

Two sets of conversions gave the evidence. The campaign of the 1.6.7 tree (twelve games at the thorough level, 2 and 3 November 2026: Dragon Ball Z -
Hyper Dimension, Marvelous, Masters New - Harukanaru Augusta 3, Jikkyou Oshaberi Parodius, SD F-1 Grand Prix, Kirby's Dream Land 3, Stunt Race FX,
Super Mario World 2, Mega Man X3, Suzuka 8 Hours, Star Ocean, Street Fighter Alpha 2) gave the long routes; the panel of the 1.6.8 tree (twelve games at the
standard level from an empty library, pin `fb8cf15`: Secret of Mana, Super Mario World, Chrono Trigger, Lock On, Donkey Kong Country 2, Street Fighter Alpha 2,
Star Fox, Mega Man X3, Kirby Super Star, Dragon Quest III (ExHiROM), Super Mario Kart, Star Ocean) gave the rest. All twenty-four: native equal to the
reference on every route, the compressed copy equal to it, 0 interpreted opcodes of the 65816 and of the SPC700; the SA-1, Super FX and CX4 programs are counted as
interpreted device instructions on their own line, the DSP-1 and the S-DD1 are command models.

| Gate | Letter | Evidence | Still missing |
|---|---|---|---|
| G1 Scope and status | Y | `retrorecomp/systems/console16.py` (status `supported`), the README row, [COMPATIBILITY.md](COMPATIBILITY.md), the board scope of [SNES.md](SNES.md) and the interface note of the Options window in the eight languages say the same board scope since 4 November (ExHiROM and the 8 MiB S-DD1 were missing from two of them); `tools/status_lint.py` shows 0 contradictions | The README row is shorter than the scope (it does not name the coprocessor boards) |
| G7 Saves | Y | `tools/snes_saves_check.py`: one cartridge written for the purpose per board (9 boards), the file, its ten damaged forms, no battery no file, the quick states; `tools/snes_game_saves_check.py` on delivered games, across three processes: Super Mario World (LoROM, 2 KiB), Dragon Quest III (ExHiROM, 8 KiB), Star Ocean (S-DD1, 8 KiB) and Kirby Super Star (SA-1, 8 KiB: the game rewrites part of its save in its first frame, from what it loaded) write their file, read it back, and set a damaged copy aside byte for byte | Secret of Mana, Chrono Trigger and Donkey Kong Country 2 wrote nothing in their save RAM in 2,000 frames (they start it from their menus): not exercised. A save made by a player from a game's menu is not reached by the routes |
| G8 Liveness | Y | Every conversion records `final_checks[].liveness` per route: pictures, picture changes, last picture change, and since 1.6.8 the audible frames and the last audible frame (a frame is audible when its sound hash is not the hash of silence); a frozen `play` route is refused; the pictures of the routes were looked at for G9 | The pictures were looked at by the specialist agent, not by the owner; Dragon Quest III's demo is silent (0 audible frames of 3,600) |
| G9 Route depth | Y | `tools/snes_route_captures.py` replays the routes of the twelve thorough conversions on their delivered files and takes the last picture (and, for a route that ends on a fade, four pictures): **11 of the 12 games reached play on at least one route**: a fight (Dragon Ball Z, Street Fighter Alpha 2), a round of golf (Augusta 3), a race (SD F-1, Stunt Race FX, Suzuka 8 Hours), a level (Kirby's Dream Land 3, Super Mario World 2, Marvelous), the game's dialogue scenes (Star Ocean), and Parodius at its continue screen (after a game over) | Mega Man X3 stays in its introduction on every route (the pseudo-random input does not leave it in 18,000 frames); first stages only, not full games; the pictures were looked at by the specialist agent, not by the owner |
| G10 Independent CPU evidence | Y | The SingleStepTests vectors on both CPUs ([CPU_65816_SPC700.md](CPU_65816_SPC700.md)): 65816 **0 differences of semantics** in 32,768 cases (native and emulation mode) and in 130,448 of the larger run; SPC700 **0** in 29,959; the compiled operations equal the interpreted ones. The differences that remain are of timing (the 65816's `WAI` and `STP`, the SPC700's `SLEEP` and `STOP`) and of bus order (dummy accesses the cores do not make) | The reference of a conversion is the engine's own interpreter (the report says `independent_cpu_oracle: false`); the vectors are a development-time evidence; the SA-1 core's interrupt entry in emulation mode is not corrected and not measured |
| G13 Cross-OS witness | P | Four games converted on Windows and on a Debian 13 PC (GCC) from the same tree, the same engine revision and an empty library at the standard level, replayed with `tools/snes_cross_os.py`: Secret of Mana (HiROM), Super Mario World (LoROM), Star Fox (Super FX), Kirby Super Star (SA-1). **12 routes of 12 give the same per-frame trace** (picture, counters and sound hash of every frame) **and the same report hashes** (CPU, RAM, video, colour and sprite memory, sound RAM, PCM, program counter, cycles): the attract route and the play route of 3,600 frames, and one pseudo-random route of 18,000 frames of each game (the standard level makes none: the tool adds it, from the ROM's identity, like the conversion's). The GCC build of the new engine builds and runs | Four of the 314 known identities, two boards of the coprocessor kind; the long routes of the thorough level and the chained ones were not replayed on Debian; quick states across the two systems and interactive play on Linux are not witnessed; the DSP-1, CX4 and S-DD1 boards and ExHiROM have no Debian witness |
| G15 Honesty | Y | The five measures stay separate in the report (`honesty`, `qualification_scope.universal_zero_fallback_claim: false`, `native_validation.independent_cpu_oracle: false`) and in [SNES.md](SNES.md). Read on 4 November 2026 for this gate: the README, [COMPATIBILITY.md](COMPATIBILITY.md), [SNES.md](SNES.md), [SNES_SUPERFX.md](SNES_SUPERFX.md), [CPU_65816_SPC700.md](CPU_65816_SPC700.md), [GUNS_16BIT.md](GUNS_16BIT.md) and the interface strings that name the machine in the eight languages (a word search for exact, perfect, accurate, zero latency, 100 % and their translations, then a read of each hit): no claim of exact hardware, complete gameplay, zero latency or zero fallback was found | The older dated journals ([SNES_LOG.md](SNES_LOG.md)) were searched, not read in full |

Unchanged and still partial: **G11** (the independent hardware evidence is authored cartridges against the contracts of Snes9x, bsnes and ares, not an external
emulator or hardware comparison; [SNES.md](SNES.md#qualification)), G14 (no owner decision recorded).

## Mega Drive: evidence behind its column (4 November 2026)

What the specialist agent measured for the gates that were `P` on 3 November, on the 1.6.8 tree (the Mega Drive's column otherwise stands on
the matrix above and on [MEGADRIVE.md](MEGADRIVE.md#qualification)). Nothing here says hardware fidelity, gameplay coverage or latency: MAME is a
model, not hardware, and the numbers are of the delivered files on the routes run. The captures were looked at by the specialist agent, not by the
owner.

| Gate | Mega Drive | Evidence | What is missing |
|---|---|---|---|
| G2 | P | Common report v2 with the 68000 and the Z80 as separate sections, `native_validation` per route, `final_checks[].liveness`, `packed` with its replay (`report_schema.py`) | Read through `read_report` on a 1.6.8 report, these sections are empty: (a) `validation.cpu_fidelity.scenarios[].hashes` (the writer holds the hashes in `final_checks` but `report_schema._cpu_scenarios` writes `None` for the `console16` writer); (b) `states` has `supported`, keys and compatibility only: no `schema`, `machine`, `rom_identity`, `fresh_process_verified` or `validation`, although the conversion chains the end state of a route into the next process; (c) `saves` has the cartridge memory layout and no `ordinary_saves` verdict (the proof is `tools/megadrive_save_selftest.py`, as for the X68000); (d) `runtime.input_players` and `peripheral` are `None` (pad type, guns); (e) the main CPU has no `mode`, `reported_label`, `interpreted_percent` or `cycles` (counts are in instructions); (f) `build.*` (backend, engine and SDL revisions, compiler signature, executable size) is `None`. All of it lives in `console16.py` and `report_schema.py`, which the Super Nintendo shares and whose G2 is `Y` on the same record: either the criterion is met for both or for neither, which is the lead's call, not a Mega Drive change |
| G8 | Y | The liveness record of the delivered file on every route of every conversion (`megadrive_evidence.py` through `delivery_evidence.py`, the same record and the same refusal of a frozen `play` route as the other machines; no third copy). Read on 14 conversions, 28 routes: the 11 games of the 1.6.7 list at the quick level (1,200 frames) and three at the standard level (3,600 frames). The picture changes on every route (101 to 2,126 distinct pictures), the FM or the PSG gives a non-zero sample on every frame of every route (28 of 28), and the last picture change falls in the last 30 frames on 21 of 28 routes. Captures of the 11 games at frame 1,200, demo and play: gameplay or an attract run in Earthworm Jim 2, OutRun, Road Rash 3, Shinobi III and the Sonic 3 intro, a title or a menu in the six others (Contra, Ecco, NBA Jam, Sonic 2, Streets of Rage 2, Super Street Fighter II) | A route may rest on a title or a menu: the `play` route of Streets of Rage 2 stays on its menu from frame 688 (101 pictures in 3,600 frames), Ecco's stops changing at 1,046 of 1,200, OutRun's at 1,114, and the attract routes of Contra (969) and Road Rash 3 (1,076) end early; the two NBA Jam routes of the quick level repeat the logo animation. "Audible" is a non-zero FM or PSG sample, not music. Fourteen conversions, not every cartridge of the panel |
| G10 | P | 2,873 of 2,895 vectors of 85 instruction groups agree on every check, on the native steps and on the reference path ([CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166)); with the 2,171 prefetch vectors (82 authored cases included), the 864 exception vectors and the 834 shift vectors, all of which agree; the Z80 vectors | The oracle is MAME, not silicon; the 22 vectors left are the decimal instructions on operands that are not digits (undefined in the manual, not modelled); the long immediate forms with a memory destination that needs an address calculation (`ADDI.L`, `SUBI.L`, `ANDI.L`, `ORI.L`, `EORI.L`, and `CMPI` of every size) have no vector; odd-address and bus errors, `TAS`, `TRAPV` and the interrupt pins are outside the fixtures |
| G11 | P | MAME 0.289 (`genesis` NTSC, `megadriv` PAL) against the delivered file on 11 games, no input on either side, `tools/megadrive_mame_compare.py` (first run, 4 November 2026): of the **80 pictures of MAME that stand still, 78 have the same shape in the game** (the first 3,000 frames: logos, titles, menus, attract screens), and **on all 78 the 8 levels of every colour channel are the same pixel by pixel**; the game's picture comes a few frames after MAME's (4 to 6 on Sonic 2; the lag is reported, not corrected, and not read on the others) | The two emulators write the 8 levels of a channel differently: MAME 0, 52, 87, 116, 144, 172, 206, 255, the game 0, 49, 87, 119, 146, 174, 206, 255 (at most 3 of 255 apart, four levels of eight), so the share of pixels with the same 24-bit colour is 33 to 100 percent by game (mean 0.90 Contra, 0.33 Road Rash 3, 1.0 Ecco): not a different picture, a different table, and which table is closer to a real console is **not** known (not changed). Two pictures of MAME have no match (the Emerald Hill title card of Sonic 2, an interlaced picture, and one picture of Super Street Fighter II): not explained. **Sound is not compared**: the delivered executable has no option that writes its sound to a file. Nothing that moves, no raster effect, no timing; MAME is not hardware |
| G13 | P | Windows and a Debian 13 PC convert Sonic The Hedgehog 2, NBA Jam - Tournament Edition and Streets of Rage 2 with the same tree (standard scan, no shared base, empty library) and the demo and play routes of 3,600 frames give **the same value on every field of `final_checks`** (`tools/megadrive_cross_os.py compare`): 6 of 6 routes, the picture, frame sequence, CPU/prefetch, VDP, RAM, Z80 and YM hashes, the counters of native and interpreted instructions and the timing misses | Three games of 24 + 8; the long and authored routes were not replayed on Debian, nor was interactive play. A first round differed on `z80_cpu_hash` for all six routes: the hash read the bytes of a structure that holds a `long` (32 bits on Windows, 64 on Linux); it is taken field by field since 1.6.8 ([UPGRADES.md](UPGRADES.md)) |

Plan for G11, in order (none started): (1) an option of the delivered executable that writes the PCM it mixed to a WAV file (the Mega Drive host has none:
about half an AI hour in `native/console16_main.c`, shared with the Super Nintendo, so the lead's), then the comparison of level and averaged spectrum on
the first 20 seconds, as `tools/cps1_mame_compare.py` does for the CPS-1; (2) the same route on both sides with input, MAME's pad read replaced by a tap
on `$A10003` as the CPS-1 tool does for its ports, on the 12 raster-effect games of the 1.6.7 list; (3) frame-by-frame comparison of a raster effect
(Sonic 2's split screen, Ecco, Contra - Hard Corps) with the lag measured and not corrected; (4) the choice of the colour table, a decision that moves every
Mega Drive picture hash. Results are always written as "model against MAME".

## Panel sizes

No common panel size exists today. The panel sizes noted by the 27 October
2026 inventory are: Neo Geo 24+10, Mega Drive 24+8, Super Nintendo DSP-1/CX4
8, Super FX 9, NES 8+10+8+6, Game Boy 606, Master System 258, CPS-1 26,
X68000 21 (19 before 2 November 2026). Whether G12 needs a common threshold is a policy decision that has
not been recorded; for CPS-1 the owner chose, on 1 November 2026, "every set of the perimeter he owns".

### Sharp X68000: the panel (2 November 2026)

**Written rule.** The panel is 21 named games of the owner's collection (option B of 2 November 2026), each chosen for at least one reason in
these categories, and none is ever dropped because it fails: a failure becomes a line of [KNOWN_FAILURES.md](KNOWN_FAILURES.md), not an absence.
The categories are the structure of the floppies (1, 2, 3, 4 and 5 disks, the largest set of the collection has 5), their behaviour (an automatic
disk change, a refusal then the next disk, an eject after loading), the mouse (read through the system calls or through the SCC chip, and a
mouse that wakes a sound), the sound (a silent route accepted, a sound that starts after a click), the picture mode (15 kHz at 55.46 frames a
second, 31 kHz at 61.46), the sets that used to stop, and a spread of genres. Each game is converted at the Standard level from an empty
library, one conversion at a time, on Windows, and again on Debian (the 1.6.6 source, whose X68000 game stamp equals this tree's) with a temporary
copy of the disks that is deleted afterwards. R-Type is converted once more with the 4 MiB option (the option, not a game of the panel).

| Game | Why it is in the panel |
|---|---|
| R-Type (Irem) | one disk, 15 kHz, the release-check game |
| Metal Sight (System Sacom) | 5 disks (the largest set), 31 kHz, automatic disk changes (2 on the routes) |
| Lemmings (Imagineer) | the mouse through the SCC chip |
| Super Hang-On (Sharp / SPS) | 2 disks ejected after loading, a long load, 31 kHz |
| Metal Unit II Power Unit | 3 disks, the third after a refusal |
| Tricorn Final (Xain) | 4 disks, 15 kHz |
| Cranked Arrow (Fukuda Naoto) | 3 disks, another maker |
| Choujin (Fix) | 2 disks ejected after loading, 31 kHz |
| Tetris v5 (Cyber Factory) | stopped the reference (CRTC reprogrammed during a line), fixed in 1.6.5 |
| TF4G v0.3A09 | the same cause, fixed in 1.6.5 |
| Pensan CD (Tanaka Yuu) | silent on its keys, its music starts after a click |
| Uno | silent on every standard route, a card game played with the mouse |
| Boyon Boyon | silent on the main route, sound on the mouse route |
| Populous (Imagineer) | the mouse through the SCC chip |
| Cameltry (Denpa) | the mouse through the SCC chip, 31 kHz |
| Dungeon Master (FTL) | 2 disks (System and User), the mouse |
| Afterburner II (Dempa) | 2 disks, 31 kHz |
| Star Luster (Dempa) | one disk, 31 kHz, 3D |
| Nemesis '94 Gradius 2 | horizontal shooter, one disk, 15 kHz |
| Quarth (Konami) | puzzle, one disk |
| Bubble Bobble (Dempa) | arcade port, one disk |

**Result (Windows, 2 November 2026, 1.6.6 tree).** All 21 convert and are delivered (110 to 226 seconds each on the build PC), with 0 interpreted
opcodes on the main, mouse and keyboard routes, the compressed copy matching the reference, and the F8/F9 state resumed in a fresh process.
Uno is accepted as silent (its report says so); every other game has sound on at least one route. Metal Sight shows its 2 automatic disk changes; the other
multi-disk sets show none on these routes (their disk requests, if any, come later in the game: not observed). R-Type at 4 MiB gives the same pictures
as at 2 MiB.

**Result (Debian, same day).** 20 of the 21 convert and are delivered with the same CPU, RAM, picture and PCM hashes as Windows on every
route. The 21st, Choujin, was refused on Debian at the replay of its compressed copy: the UPX-compressed program stops at start (SIGTRAP) with
`-9`, `-1` and `--lzma`, although `upx -t` passes and the program UPX unpacks from it is byte for byte the one that was validated and runs. Converted on
Debian with `--no-compress` it gives the same hashes as Windows. This is the packing step shared by every console, not the X68000
([KNOWN_FAILURES.md](KNOWN_FAILURES.md)). With the shared fallback of 1.6.7 (main at 1aa7ddd, 3 November 2026) the same conversion on Debian succeeds:
the journal says the compressed copy failed its replay and the unpacked build is replayed instead, `native_validation.packed_reference_match` is true,
`packing.packed` is false with `unpacked_reason` ("... twice ..."), and the published file has the SHA-256 of the validated build; a witness game of the
panel (R-Type) stayed compressed, with no fallback line. So 21 of the 21 are delivered on Debian, one of them unpacked. These checks say that the native code, the picture and the sound of the routes run are the same on the two systems;
they say nothing of complete gameplay, exact hardware or latency.

### Sharp X68000: scope and follow-ups at the exit (5 November 2026)

**What the exit stands on.** The column above, with every gate `Y` except G10 and G11, which stay `P` as they do for the other supported 68000
machines (G10: 22 of 2,895 vectors of undefined decimal arithmetic; G11: MAME, a model and not hardware). The owner decided with both open, after the
play trials of 3 and 5 November 2026. Nothing here says exact hardware, complete gameplay or physical latency.

**Scope stated at the exit** (also in [X68000.md](X68000.md#8-known-limits)): floppy games only; no hard-disk images, no set of more than ten
disks, no copy-protected D88; the few games that play only through an external Roland MIDI module run silent and the report says so (a decision
of 29 October 2026 for this machine only); the mouse and the keyboard are checked by routes and by play on a few games; saves are proved by an
authored program and by file time stamps of real games; the machine stays local (G16 not applicable); the screen contrast of the system port is a
known difference with MAME, not changed.

**Follow-ups** (none of them blocks the exit; each can move a hash and says so when it does): the sound of the five games compared with MAME
(the CPS-1's is within 0.42 dB), the colours compared on the four games that have none, the ten pictures of MAME that no picture of the game matches
(Lemmings 5, Star Luster 4, Bubble Bobble 1), authored vectors for the long immediate forms with a memory destination, the thorough scan level and
disk requests late in a game, a game that saves on purpose, interactive play witnessed on Linux, and a new review of the px68k upstreams.

**Replay on the tree of the exit (5 November 2026, Windows).** The 21 games of the panel and R-Type at 4 MiB were converted again with the tree of the exit commit (standard level, an empty private library for each, no shared base, no online cover, two conversions at a time, 122 to 325 seconds each): **0 interpreted opcodes on all 66 routes** (22 conversions, three routes each), the compressed copy matching the fresh reference on all 22, F8/F9 resumed in a fresh process on all 22, the report says `supported`, sound on 21 of the 22 (Uno is accepted as silent, as before) and the two automatic disk changes of Metal Sight. Against the panel of 2 November (the 1.6.6 tree): the **CPU, RAM and PCM hashes are equal on all 66 routes**; the picture hashes differ on all 66, as expected (the 1.6.7 colour of the intensity bit, [UPGRADES_HISTORY.md](UPGRADES_HISTORY.md)); the numbers of different pictures and of audio blocks of every route are equal. Two further conversions (Twins, Fancy Qix) against the 1.6.8 tree give 513 values each of which only the status and the timings differ: the CPU, RAM, picture and PCM hashes and the trace digest of the three routes are equal. The Debian replay of the same tree is still to do (G13 stands on the 1.6.6 tree until then).

## Owner acceptance

Owner play tests (gate G14), one row per test. The table starts empty; the
owner fills it in.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
|  |  |  |  |  |
| 1 November 2026 | Capcom CPS-1 | none (decision on the evidence, no game played for this row) | Exit from the experimental status validated by Arthur on the basis of the 1.6.6 evidence | The play trial list of `CPS1_ACCEPTATION.md` is still to do on the 1.6.6 executable. The owner trials of 27 October 2026 were reported in chat and are not recorded here. |
| 1 November 2026 | Mega Drive | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| 1 November 2026 | Neo Geo | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| 3 November 2026 | Nintendo NES | The Legend of Zelda, Kirby's Adventure, Mr. Gimmick, Duck Hunt, Battletoads, Castlevania III, converted with the 1.6.7 tree in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The trial list of the NES checklist below; G14 `Y`. |
| 3 November 2026 | Capcom CPS-1 | 1941, Street Fighter II' Champion Edition, Final Fight, Captain Commando, Strider, Mercs, converted with the 1.6.7 tree (generator revision 12) in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The play trial list of `CPS1_ACCEPTATION.md`, which the row of 1 November left to do; G14 moves from `P` to `Y`. |
| 3 November 2026 | Sharp X68000 | R-Type, Metal Sight, Lemmings, Super Hang-On, Bubble Bobble, converted with the 1.6.7 tree in a player's conditions and delivered in `Export` | Arthur: "je viens de faire mes essais NES, CPS et X68000, on est bon" | The play test passed. It is not a decision to leave the experimental status: G10 and G11 are still `P`, and the exit stays the owner's explicit decision once every gate is proved. G14 is `P`. |
| 5 November 2026 | Sharp X68000 | Double Target, Fancy Qix, Twins, Danger Area, Pac-Land, drawn at random (seed 20261105) among the games of his collection not yet in `Export`, converted with the 1.6.8 tree in a player's conditions and delivered in `Export` | Arthur: « Bon, je viens de tester les derniers jeux que tu m'as sortis là sur Sharp X68000 et sur le CPS. Les deux marchent parfaitement. Tu peux sortir le Sharp de l'expérimental, même si on aura forcément quelques évolutions à faire derrière. » | The decision to leave the experimental status, given with G10 and G11 still `P`; it also counts as his last trial on the tree of the exit, whose commit changes the status written in the report and nothing in the player. G14 `Y`. |

### Checklist for Arthur: Sharp X68000 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executable** of the release you are judging
(not a reconversion of the day). `python tools/x68000_owner_trial.py --roms <your X68000 folder> --ipl <iplrom.dat> --cgrom <cgrom.dat>`
converts these five games as a player would, one at a time, under `.build/x68-owner-trial/` (never into Export, each in a private
library), and writes `TRIAL.md` there with where each executable is and what to try; the executables carry your IPL and font ROM, so
they stay on your machine. Nothing here says exact hardware,
complete gameplay or latency; a tick means "it looked and sounded right to you in this test".

| | R-Type (Irem) | Metal Sight (System Sacom) | Lemmings (Imagineer) | Super Hang-On (Sharp / SPS) | Bubble Bobble (Dempa) |
|---|---|---|---|---|---|
| Why it is here | one disk, the control | five disks: the disk changes | mouse game that drives the mouse chip itself | two disks, ejected after loading | an arcade port whose colours were corrected in 1.6.7 |
| It starts without an error window | | | | | |
| Controls: arrows, **W** and **X** (A and B), **Enter** (Start) | | | The mouse is captured at launch (**Ctrl+Alt+M** releases it); the keyboard or a gamepad also moves the pointer and presses its buttons. Click "1 PLAYER", then play level 1 | The title counter counts down from 99 while the game loads (about two minutes of play time); hold **F5** for fast loading; nothing answers before it reaches 0 | Two players share the keyboard and a gamepad; the colours look right, with no green cast on the dark parts |
| Sound is the game's (music and effects) | | | | | |
| The disk changes by itself, with no key from you | not applicable | at each "insert disk" request, until play | not applicable | none expected: it must run as if there were no policy | not applicable |
| **F8** in play, move on, **F9** goes back to the saved moment | | | | | |
| Close the window, start the executable again, **F9** loads the state saved before | | | | | |
| Nothing odd: a frozen picture, silence where there was sound, a wrong colour | | | | | |

Then three checks on the machine itself, each on one game of your choice:

1. **Save, relaunch, reconvert.** The game's disks are copied beside the player on the first start (`datas/games/x68-<identity>/media`)
   and the game writes into its own copy. Pick a game you know writes to its disk (a save, a high score, a configuration), save in it,
   close, start again and find the save; then convert the same game again, start the new executable and find the save once more.
   None of the four games above is known to save on purpose (the only writes seen in 378 starts are file time stamps of 4 to 12 bytes,
   above), so this check needs a game that does: tell me which one and I add it to the risk cases. If a disk was damaged, the player moves
   it to `<name>.unusable-1` and writes the original again; it never deletes it.
2. **A D88 image.** The collection holds only DIM files, so make a D88 of a disk you own with
   `python tools/x68000_disk_rewrite.py "R-Type (Irem).dim" --format d88 R-Type.d88` (outside the repository: it holds the whole disk),
   convert it into another output folder than the DIM's, and play it like the DIM. It is the same game: same identity, same saved data, the
   same pictures and sound. A D88 from elsewhere with a copy-protection layout (deleted or failing sectors, 2DD) is refused with a reason,
   on purpose.
3. **A multi-disk set from a folder.** Add one disk of a numbered set (for example Metal Sight, disk 1 of 5) to the queue: the five disks
   must join as one game. A set named with a gap (disk 3 missing) is queued with the disks found and the gap is reported in the log.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| (to fill) | Sharp X68000 | (to fill) | (to fill) | (to fill) |

### Checklist for Arthur: Nintendo NES play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executable** of the release you are judging.
`python tools/nes_owner_trial.py --roms <your NES folder>` converts these six games as a player would, one at a time, under
`.build/nes-owner-trial/` (never into Export), writes `TRIAL.md` there with the same table and takes one picture of each right-hand
play route. Nothing here says exact hardware, complete gameplay or latency; a tick means "it looked and sounded right to you in this
test".

| | Zelda | Kirby's Adventure | Mr. Gimmick (PAL) | Duck Hunt (Zapper) | Battletoads | Castlevania III |
|---|---|---|---|---|---|---|
| Why it is here | MMC1, battery save, long game | MMC3 scanline IRQ, battery save | 50 Hz cartridge, FME-7 sound chip | the Zapper | two players, AxROM, code in RAM | MMC5, extra sound channels |
| It starts without an error window | | | | | | |
| Controls: arrows, **W** and **X**, **Enter** (Start), **Shift** (Select); player 2 on the keypad | | | | The mouse aims, the left button shoots, the right button shoots off-screen | Both pads answer | |
| Sound is the game's (music and effects) | | | The speed and the pitch of a PAL game | | | The extra pulse channels are heard |
| **F8** in play, move on, **F9** goes back | | | | | | |
| Close the window, start again, **F9** loads the state saved before | | | | | | |
| A save made in the game is still there after closing and starting again | | | not applicable | not applicable | not applicable | not applicable |
| **F3** changes the picture filter, **F4** the window mode | | | | | | |
| Nothing odd: a frozen picture, a flickering status bar, a wrong colour | | | | | | |

Then four checks, each on the game that fits:

1. **Battery save.** Start a game in Zelda or Kirby, save in the game, quit, start again and load it. The file is
   `datas/games/<game>-<12 hex digits>.sav` beside the player; the conversion's own test runs leave none.
2. **Autofire and extra sprites.** On a gamepad, **F6** turns autofire on and off (a notice shows "Autofire ON" or "Autofire OFF"; a game
   samples its pad once per frame, so what it makes of it is the game's). **F5** toggles the extra sprites: in a game that flickers
   (Battletoads, Castlevania III) fewer objects blink; off by default.
3. **The Zapper.** In Duck Hunt, **F2** then the Zapper page (after the four control pages) changes the reticle: cross or dot, size, red,
   white or green. The light is an approximation fed by the pixels the PPU emits: say if a shot you think was good counts as a miss, or
   the opposite, and where on the screen.
4. **Language.** **F7** changes the language of the player's own menus (the game's text is the cartridge's).

Known limits to keep in mind while you play: the Zapper's light is approximate; one Zapper only (no second gun, no other special
controller); the Famicom Disk System is not supported; no Dendy timing (NTSC and PAL only). Keep the five measures apart when you judge: the CPU is checked against independent vectors and
the hardware against authored fixtures, not against a reference console, and a good feel here is neither an exact fidelity nor a
latency measure.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
| (to fill) | Nintendo NES | (to fill) | (to fill) | (to fill) |

## Running the verification campaign

`tools/campaign.py` is a developer tool: it prepares and runs the pre-release
check on a sample of each console, with the verdicts of
`tools/release_check.py`. It is not in the converter or in any release
archive, reads the ROM folders without writing to them, and keeps every
output under `.build/campaign-<version>/`. Run it on the Windows build PC with
the converter about to be published (`Retro-Recomp.exe`, or `RetroRecomp.py`
from a checkout); it does not replace the owner's play tests (G14).

1. **Select.** `python tools/campaign.py select --roms-root <folder with one
   ROM folder per console> --version 1.6.0` (or set `RETRO_RECOMP_ROMS`; no
   private path is written in the tool). Per console, `--count` games (10 by
   default): half drawn at random with `--seed` (the same folder, seed and
   risk file always give the same games), half from the risk cases of
   `tools/campaign-risk-cases.json` (titles and the reason each one is hard,
   from this repository's documents; edit the file to change them). With
   `--random N`, every risk case found is taken plus exactly N random games;
   the 1.6.0 campaign uses `--random 2` with four or five risk cases a
   console, seven games at most (Arthur, 27 October 2026). Each file
   is read by the converter's own detector before it is kept. The result,
   `selection.json`, holds paths and SHA-256 only. `--hermes N` marks N games
   per console for the Linux sample.
2. **Run.** `python tools/campaign.py run <converter> --version 1.6.0 --jobs 4
   --level standard`. Up to 8 conversions run at once inside one batch per
   chunk of games (`--chunk`, default twice `--jobs`); one verdict file and one
   log per game go to `journal/<console>/`. An interrupted run resumes by
   skipping games that have a verdict (`--retry-failed` and `--redo` run them
   again; `--consoles`, `--subset hermes`, `--limit` and `--smallest N` narrow
   the run). Neo Geo takes `--ng-bios`, X68000 `--x68-ipl` and `--x68-cgrom`.
   The new observations stay in the converter workspace of the campaign
   (`out/app` for the frozen converter). On the Linux machine, run `select`
   again there with its own ROM root and the same seed, then `run --subset
   hermes` with the Linux converter.
3. **Report.** `python tools/campaign.py report --version 1.6.0` writes
   `summary.md` and `summary.json`: per console and game, the verdict, the
   scan level, the conversion time, the interpreter fallback per CPU and per
   cartridge device (read through `retrorecomp/report_schema.py`; "not
   measured" stays "not measured"), and the five measures separately with the
   claim each report makes: native code, CPU fidelity, hardware fidelity,
   gameplay validation, physical latency. A pass means the gates of
   `release_check.py` held (conversion, native/reference agreement, fallback
   limit, and for Neo Geo, CPS-1 and X68000 the packed replay and the
   fresh-process states); it says nothing about hardware fidelity, full games
   or latency. A case marked `expect: refusal` passes only when the converter
   refuses the cartridge, and is counted apart as "refused".
4. **Upgrade.** `python tools/campaign.py upgrade <converter> <export folder>
   [...] --from-version 1.5.6` copies existing exports into the campaign
   (the originals are untouched, and each old executable is kept under
   `upgrade/before/`), runs the converter's own batch path without `--force`,
   and records per game whether it was an already-current export, a quick
   upgrade (only the player shell changed) or a full reconversion, with the
   release_check verdict of the new report.
5. **States.** `python tools/campaign.py states pairs` resumes, for Mega Drive
   and Super Nintendo, a state written headless by each old export in its
   upgraded export, through `tools/state16_cross.py --one-way`; the outcome is
   resumed identically, resumed but different, diverged or refused.
   `states files --states-dir <folder>` loads slots saved by hand in the old
   player into the new exports (and, when the old export is known, compares
   both continuations). A refusal is a clean outcome unless a release note
   promises migration. What this proves is only what it ran: a state of real
   play from an older build is checked only when its file is given.
