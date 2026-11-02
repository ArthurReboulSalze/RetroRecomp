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

| # | Gate | Defined by |
|---|---|---|
| G1 | Scope and status stated consistently | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G2 | Report contract | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G3 | Native coverage on every final scenario | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G4 | CPU fidelity: fresh reference run | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G5 | Packed replay of the delivered file | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G6 | Fresh-process states | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G7 | Saves | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G8 | Liveness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G9 | Route depth | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G10 | Independent CPU evidence | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G11 | Independent hardware evidence | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G12 | Panel | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G13 | Cross-OS witness | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G14 | Owner acceptance | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G15 | Honesty | [STANDARDS.md](STANDARDS.md#supported-checklist) |
| G16 | Shared-knowledge safety | [STANDARDS.md](STANDARDS.md#supported-checklist) |

## Status matrix (27 October 2026; the X68000, CPS-1, NES and Game Boy columns, and G5 and G8 of the Master System, Game Gear, Super Nintendo and Neo Geo, of 1 November 2026; G8 and G10 of the Neo Geo of 2 November 2026)

`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable. Consoles:
sms = Master System, gg = Game Gear, gb = Game Boy, nes = Nintendo NES,
md = Mega Drive, snes = Super Nintendo, ng = Neo Geo, cps1 = Capcom CPS-1,
x68 = Sharp X68000.

| Gate | sms | gg | gb | nes | md | snes | ng | cps1 | x68 |
|---|---|---|---|---|---|---|---|---|---|
| G1 | P | P | P | Y | Y | P | Y | Y | Y |
| G2 | P | P | P | Y | P | Y | Y | Y | Y |
| G3 | Y | Y | P | Y | Y | Y | Y | Y | Y |
| G4 | Y | Y | P | Y | Y | Y | Y | Y | Y |
| G5 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G6 | P | P | Y | Y | Y | Y | Y | Y | Y |
| G7 | - | - | Y | Y | Y | P | Y | - | Y |
| G8 | P | P | P | Y | P | P | Y | Y | Y |
| G9 | P | P | P | Y | Y | P | Y | Y | Y |
| G10 | Y | Y | P | Y | P | P | Y | Y | P |
| G11 | P | P | P | P | P | P | P | P | P |
| G12 | Y | P | Y | P | Y | Y | Y | Y | P |
| G13 | P | P | P | P | P | P | P | P | Y |
| G14 | ? | ? | ? | ? | Y | ? | Y | P | ? |
| G15 | P | P | P | P | P | P | Y | Y | P |
| G16 | Y | Y | Y | Y | Y | Y | Y | P | - |

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

- The G5 and G6 rows say "met" where the check exists as a campaign step.
  Only ng, cps1, (since 1.6.5) x68 and (since 1.6.6) md, nes and gb run G5 inside every conversion (sms and gg too, but only
  with the banked engine, see below), and ng, cps1, x68 and (since 1.6.6) nes and gb run G6 inside every conversion. Read G5 and G6
  as "met per conversion" only for those.
- Game Boy (1 November 2026): G5 and G6 `Y` per conversion, G7 `Y`, G8 `P`. G5: after the lockstep comparisons the compressed copy is
  replayed on the same routes and must give the same verdict line (`retrorecomp/gameboy_delivery.py`; [UPGRADES.md](UPGRADES.md#game-boy-the-packed-replay-and-the-liveness-record-166-gates-g5-and-g8)).
  G6: every conversion checks the quick states in a fresh process, and `tools/gameboy_states_check.py` does it on an authored
  cartridge and on Super Mario Land. G7: `tools/gameboy_saves_check.py` on six cartridges written for it ([GAME_BOY.md](GAME_BOY.md)).
  G8 is `P`: the liveness record exists on every conversion, but no campaign of captures was inspected for the Game Boy.
- NES (1 November 2026): G2, G3, G4, G7, G8 and G9 moved from `P` to `Y` on the evidence of the section *Nintendo NES: evidence behind
  its column* below (campaign of eight games at the thorough level, delivered-file checks, captures). G9 `Y` rests on pictures
  looked at by the specialist agent, not by the owner. G12, G13 and G15 stay `P`, G14 stays `?`.
- Master System and Game Gear (1 November 2026): G5 is `P` for both. The replay of the compressed copy exists only with the banked
  engine (the "functions" engine records liveness only), and what is recorded for it is synthetic tests
  (`tests/test_sega_evidence.py`) and runs on three games, not a result per console ([UPGRADES.md](UPGRADES.md#master-system-and-game-gear-evidence-about-the-delivered-file-166)).
  The Game Gear was `Y` before; nothing recorded separated the two consoles, which share the engine and the adapter.
- Super Nintendo and Neo Geo (1 November 2026): G8 moved from `Y` to `P`. The Super Nintendo has a liveness check for the cartridges
  with a coprocessor only (`supernintendo.validate_device_liveness`), none for an ordinary cartridge; the Neo Geo has no liveness record
  yet (`retrorecomp/neogeo_conversion.py` uses `deliver_packed` and `replay_routes`, not `liveness_summary`). See the section
  *Shared evidence helper*.
- Neo Geo (2 November 2026): G10 moved from `P` to `Y`. Both CPUs replay independent vectors through the Neo Geo generator, the same ones
  as the CPS-1 and with the same figures ([NEOGEO.md](NEOGEO.md#qualification), [NEOGEO_LOG.md](NEOGEO_LOG.md)). 68000
  (`tools/neogeo_vector_selftest.py`): the three SingleStepTests fixtures (834 + 2,171 + 864 vectors, the 82 authored cases included) all run
  as native steps; the native steps agree with 3,867 of 3,869 on registers, SR, PC, written bytes and clocks. Z80
  (`tools/neogeo_z80_vector_selftest.py`): 51,328 vectors through `neogeo_z80.generate` and the Geolith core corrected in the converter's copy
  (`neogeo_z80.FIXES`), 49,685 as native steps below `0xf800` and 1,643 through observed RAM variants; native and interpreted identical on every
  vector, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle. **Reserves, written as they are:**
  (a) the two authored 68000 vectors that set the trace bit, which neither path delivers (the Neo Geo Musashi is built without trace);
  (b) the 68 Z80 vectors that differ are the X and Y flags of `SCF` and `CCF` and their `DD`/`FD` duplicates (the Q latch of the original chip is
  not carried: a store per instruction and a state field); (c) the shared Musashi, the reference of every conversion, differs from the
  68000 vectors on `DIVU`/`DIVS` flags (and the division clocks), `CHK` flags and clocks and one line-F stack byte (3,783 of 3,869 on state,
  3,823 on clocks), where the translated steps follow the vectors: a game that reached such a case would show a native-against-reference
  difference at conversion, not hide it, and none of the 134 qualified identities has; correcting the Musashi is the lead's decision and
  would move the 68000 stamps of four machines; (d) the oracles are MAME (68000) and JSMoo (Z80), not hardware, and the bus is flat: nothing
  of the board, the YM2610, the command latch or the prefetch bus phases.
- Neo Geo (2 November 2026): G8 moved from `P` back to `Y`. The packed replays now run with `--trace` and every `final_checks[]` row carries
  `liveness` with the CPS-1 keys (`frames`, `distinct_pictures`, `picture_changes`, `last_picture_change_frame`, `audible_frames`,
  `last_audible_frame`), counted from frame 1, through `delivery_evidence.py` unchanged (`liveness_summary`, `report_fields`,
  `require_moving_picture`); a route whose picture never changes stops the conversion, as on the CPS-1, and every route of a set is required
  to move (MVS and AES). Read on conversions of the tree: NAM-1975 (7 routes), Puzzle De Pon! (6), Metal Slug 3 (7) and The Irritating Maze
  (4): every route changed its picture on more than a thousand frames and was audible on more than half of them. **Scope:** the record is on
  every conversion from now on; it was read on four sets, not on the 134 identities, and it says that picture and sound change, nothing of what
  they show (the captures of the earlier campaigns are G9's evidence).
- G14 for NES, SNES, SMS, GG, GB and X68 means "no recorded owner
  decision found", not proof that none exists. X68000 and CPS-1 owner trials
  were reported in chat on 27 October 2026 and are not written in a document
  yet; they belong in the owner-acceptance table below when recorded.

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
  refuses to be written before every route matched.

The Master System and the Game Gear use it since 1.6.6 (`retrorecomp/sega_evidence.py`): the runner's `--vdp-trace` has two more
columns, `psg_h` (hash of the PSG's stereo samples of the frame) and `psg_nz` (their non-zero count), written only when a trace is
written; every conversion records `final_checks[].liveness` per route (picture from `pixels_h`, sound, RAM; no program counter, so that
key is None) and refuses a conversion whose main (`play`) route never changed picture; the banked engine also replays the compressed
copy of the build on both routes against the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`).
The "functions" engine has the liveness record and no packed replay. G8 is `P` for both columns: the record exists on every
conversion, but the captures were not inspected as a campaign and the risk cases were not run to play. G5 stays as recorded: the
replay is in the conversion for every banked game, run on three of them here.

The NES uses it since 1.6.6 (`retrorecomp/nes_checks.py`, `retrorecomp/nes.py`): the headless `--hash-out` line of the exported
game carries `pic=` (the hash of the rendered 256 x 240 picture), `snd=` (the hash of the frame's sound) and `aud=` (1 when a
sample was not zero), the liveness record of each route is read from it, the delivered copy is replayed on every route and its
trace and PCM compared with the fresh reference, and the machine is in the `conversion_gates` group.

The machine that does not use it yet for ordinary cartridges, what it already writes per frame, and the smallest change to feed it (a plan, not a
record: nothing below runs yet):

| Machine | Per-frame data today | Missing | Smallest change |
|---|---|---|---|
| Super Nintendo | The same `--trace` without the Mega Drive columns (frame hash, counters, audio hash); the report already holds `last_picture_change_frame`, `last_audible_frame`, `last_device_frame`, `visible_frames`, `pcm_nonzero`, which `validate_device_liveness` reads for device cartridges only | The trace carries no audible flag and the conversion does not request it; the report has no counts of pictures or audible frames, so an ordinary cartridge has no liveness record | Pass `--trace`, add the non-zero count of the frame's PCM to the trace line (one column, shared with the Mega Drive adapter); keep `validate_device_liveness` and its windowed rule (picture, device and sound all quiet for the last quarter of the run) for the device cartridges and give an ordinary cartridge `frozen_route` on the same record |

The packed replay (G5) needs, for each of these, a callback that starts the compressed copy with the same arguments as the
probe that made the reference and compares the same fields (Mega Drive and Super Nintendo: `reference_differences`;
Master System and Game Gear: `compare_execution`; NES: the `.hash` lines and the PCM; Game Boy: the verdict line of the
build), and the group `conversion_gates` in the machine's `stamp_groups`.

## Sharp X68000: evidence behind its column (29 October 2026, status of 1 November 2026)

The X68000 stays **experimental**. This is what each gate rests on today and what is still missing, with the file that
shows it. `P` means a part is shown and the rest is named; nothing here says exact hardware, gameplay coverage or latency.

| Gate | X68000 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/x68000.py` (status `experimental`), [X68000.md](X68000.md), `tests/test_system_profiles.py` | |
| G2 | Y | Common report v2 (`report_schema.py`, `tests/test_report_schema.py`, golden `tests/x68000_common_golden.json`). Since 1.6.6 the sections are filled from the conversion itself: `cpus` (one 68000, native and interpreted counts per route), `validation.cpu_fidelity` (digests of the CPU, RAM, image and PCM traces per route), `scan.routes` (frames, steps and script digest of each exploration route), `states.validation` (fresh process, compressed copy, the frame of the save and the 400 continued frames), `saves`, `input_players`, `peripheral`, `packed.replay` | `devices` is empty and there is no audio CPU section: the machine has no cartridge device and its sound is part of the reference machine, so a counter per device does not apply. `saves.validation.checked_in_this_conversion` is false (the proof is the test and the tool named there, not a step of the conversion) |
| G3 | Y | `final_checks[].interpreted_opcodes` is 0 on the main, mouse and keyboard routes of the four risk cases (below) | Only on the routes run |
| G4 | Y | A fresh interpreted reference per conversion, trace equality (`native_validation.reference_match`, `tests/test_x68000_conversion.py`) | |
| G5 | Y | The compressed copy is replayed on every route against the same reference (`packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/x68000_conversion.py`); R-Type, Metal Sight, Lemmings and Super Hang-On matched on 3 routes each | The published file is compressed again by `publishing.py` (UPX is deterministic: the SHA-256 recorded in the report equals the published one on the run checked) |
| G6 | Y | F9 in a fresh process and the early floppy DMA, now on the compressed copy (`state_checks`) | |
| G7 | Y | `tests/test_x68000_payload.py`: a played disk survives every start and a second build of the same machine identity; a disk of another size, a missing one or a folder in its place is moved to `<name>.unusable-N` and replaced from the executable; a changed host file is treated the same way; the game always starts. `tools/x68000_saves_check.py` on a real game (below): the game wrote to its disk, a relaunch and a second conversion found it as it was | The writes found are file time stamps of 4 to 12 bytes (below): no game was seen saving a score or a position on purpose, which needs play beyond the routes |
| G8 | Y | `liveness` in every report, per route and for the delivered file; captures looked at; the four risk cases below reach play, R-Type and Metal Sight on the standard routes, Lemmings and Super Hang-On on authored routes (`tools/x68000_play_routes.py`) | Scope: the four risk cases, not every set of the panel. 8 of the 84 reviewed mouse sets make no sound on any standard route and 15 show a still picture on the 4,000-frame main route, which a click or a key wakes on another route (Route rules, below) |
| G9 | Y | The four risk cases were converted at the extended level (main, mouse, keyboard and one 18,000-frame pseudo-random route), 0 interpreted opcodes on every route, the compressed copy matching the reference on the four routes (table below); play is reached on the delivered file for R-Type and Metal Sight (standard and long routes), for Super Hang-On (long route, and its authored route) and for Lemmings (authored route; its standard and long routes stay on the menu) | Inspected by the specialist agent, not by the owner; four games, not the 84 mouse sets; the thorough level (36,000 frames) was not run; not full games |
| G10 | P | Musashi as the reference, 20 authored CPU guards (`native/x68000_native/guard_checks.c`, `tools/x68000_native_check.py`) | No independent vectors replayed through the X68000 generator |
| G11 | P | Authored video, audio, timing, session and disk vectors (`tools/x68000_*_check.py`) | No external emulator or hardware comparison |
| G12 | P | 19 sets converted on Windows and Debian; 418 images of the test collection give 33 multi-disk sets and 84 mouse sets reviewed | Three entries of the test collection stopped the reference: Tetris v5 and TF4G v0.3A09 (a crash of the frame loop, fixed in 1.6.5, both convert now) and Pensan CD (silent on the routes without the mouse; since 1.6.5 a silent route is accepted and reported, and it converts with zero interpreted opcodes) |
| G13 | Y | Windows and Debian trace hashes match on the 19 sets | |
| G14 | ? | No recorded owner decision (draft below) | Arthur's play test |
| G15 | P | The five measures stay separate in the report and in [X68000.md](X68000.md) | The interface and the older documents have not all been read for this |
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
| G10 | Y | 68000: the three SingleStepTests fixtures through the CPS-1 generator, the native steps agree with 3,787 of 3,787 vectors and 80 of 82 authored cases (`tools/cps1_vector_selftest.py`). Z80: 51,328 vectors through the CPS-1 Z80 bodies and the Geolith core corrected in the converter's copy since 1.6.6, native and interpreted identical, 51,260 states (99.87 percent) and all 51,328 clocks agree with the oracle (`tools/cps1_z80_vector_selftest.py`, `neogeo_z80.FIXES`) | The X and Y flags of `SCF`/`CCF` (the Q latch is not carried: a store per Z80 instruction and a state field); the CPS-1 Musashi reference differs from the 68000 vectors in a few groups (division and `CHK` flags, trace), where the translated steps follow the vectors |
| G11 | P | MAME 0.289 on the 1.6.5 tree (`tools/cps1_mame_compare.py`, 30 October and 1 November): 24 sets comparable, the picture of the attract route identical on all of them, of the credited play route on 23; the sound within 0.42 dB (median level) and 0.99 (averaged spectra) on the 24 | `sf2hf` slips by a frame; two sets need PAL dumps the romsets lack; MAME is not hardware; the waveforms are not claimed equal (OKI interpolation) |
| G12 | Y | The owner chose criterion 1 (1 November 2026): every set of the perimeter that he owns is converted and validated, 26 of 26 (the perimeter has 129 sets) | Not covered by the panel and noted in [CPS1.md](CPS1.md#panel-coverage): the boards `CPS_B_17` (`sf2ua`) and `CPS_B_21_BT5` (`varthj`), 20 of the 45 mappers (seen in sets the collection lacks) |
| G13 | P | Final Fight (27 October), Street Fighter II' Champion Edition (30 October) and 1941 (1 November) give the same CPU, RAM, image, sound and trace hashes on Windows and Debian 13 | Three sets of 26 |
| G14 | P | Exit from the experimental status accepted by the owner on 1 November 2026 on the evidence of 1.6.6 (row below) | The owner's play trial list, on the 1.6.6 executable |
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
| G12 | P | The eight games below, the 1.6.4 player-conditions reconversion of Kirby's Adventure and the earlier qualifications of 8 to 12 October | The panel size policy is not decided |
| G13 | P | Quick states resumed across the Visual Studio and portable-toolchain builds (`tools/nes_state_cross.py`) | No campaign on Debian for the NES in 1.6.6 |
| G14 | ? | No recorded owner decision | Arthur's play test |
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

## Panel sizes

No common panel size exists today. The panel sizes noted by the 27 October
2026 inventory are: Neo Geo 24+10, Mega Drive 24+8, Super Nintendo DSP-1/CX4
8, Super FX 9, NES 8+10+8+6, Game Boy 606, Master System 258, CPS-1 26,
X68000 19. Whether G12 needs a common threshold is a policy decision that has
not been recorded; for CPS-1 the owner chose, on 1 November 2026, "every set of the perimeter he owns".

## Owner acceptance

Owner play tests (gate G14), one row per test. The table starts empty; the
owner fills it in.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
|  |  |  |  |  |
| 1 November 2026 | Capcom CPS-1 | none (decision on the evidence, no game played for this row) | Exit from the experimental status validated by Arthur on the basis of the 1.6.6 evidence | The play trial list of `CPS1_ACCEPTATION.md` is still to do on the 1.6.6 executable. The owner trials of 27 October 2026 were reported in chat and are not recorded here. |
| 1 November 2026 | Mega Drive | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| 1 November 2026 | Neo Geo | none recorded (owner acceptance, no game list written) | accepted by the owner (Arthur), who uses these machines and validated them as supported; no written play checklist for this row | Recorded on 1 November 2026 at the maintainer's confirmation of the `Y` of the matrix. |
| _Draft, to fill (CPS-1 trial)_ | Capcom CPS-1 | _suggested: `1941` (vertical), `sf2ce`, `ffight`, `captcomm` (four players), `strider`, `mercs` (vertical, three players)_ | _verdict_ | _Prepared 29 October 2026 for the owner to complete on the 1.6.6 executable._ |

### Checklist for Arthur: Sharp X68000 play test (G14)

A checklist, not a record: the verdicts and the notes are yours. Play the **delivered executable** of the release you are judging
(not a reconversion of the day), with your own IPL and font ROM chosen in Options → Sharp X68000. Nothing here says exact hardware,
complete gameplay or latency; a tick means "it looked and sounded right to you in this test".

| | R-Type (Irem) | Metal Sight (System Sacom) | Lemmings (Imagineer) | Super Hang-On (Sharp / SPS) |
|---|---|---|---|---|
| Why it is here | one disk, the control | five disks: the disk changes | mouse game that drives the mouse chip itself | two disks, ejected after loading |
| It starts without an error window | | | | |
| Controls: arrows, **W** and **X** (A and B), **Enter** (Start) | | | The mouse is captured at launch (**Ctrl+Alt+M** releases it); the keyboard or a gamepad also moves the pointer and presses its buttons. Click "1 PLAYER", then play level 1 | The title counter counts down from 99 while the game loads (about two minutes of play time); hold **F5** for fast loading; nothing answers before it reaches 0 |
| Sound is the game's (music and effects) | | | | |
| The disk changes by itself, with no key from you | not applicable | at each "insert disk" request, until play | not applicable | none expected: it must run as if there were no policy |
| **F8** in play, move on, **F9** goes back to the saved moment | | | | |
| Close the window, start the executable again, **F9** loads the state saved before | | | | |
| Nothing odd: a frozen picture, silence where there was sound, a wrong colour | | | | |

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
