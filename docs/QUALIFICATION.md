# Qualification record

Per-console qualification record for Retro-Recomp. The rules every change
follows and the "supported" checklist are defined in
[STANDARDS.md](STANDARDS.md#supported-checklist); the gates G1-G16 below are
short names for that checklist, numbered by the 27 October 2026 pipeline
inventory. This page records the current status matrix and the
owner-acceptance log. It makes no claim beyond them.

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

## Status matrix (27 October 2026; the X68000 column of 29 October 2026)

`Y` met, `P` partial, `N` no, `?` unknown, `-` not applicable. Consoles:
sms = Master System, gg = Game Gear, gb = Game Boy, nes = Nintendo NES,
md = Mega Drive, snes = Super Nintendo, ng = Neo Geo, cps1 = Capcom CPS-1,
x68 = Sharp X68000.

| Gate | sms | gg | gb | nes | md | snes | ng | cps1 | x68 |
|---|---|---|---|---|---|---|---|---|---|
| G1 | P | P | P | Y | Y | P | Y | Y | Y |
| G2 | P | P | P | P | P | Y | Y | Y | P |
| G3 | Y | Y | P | P | Y | Y | Y | Y | Y |
| G4 | Y | Y | P | P | Y | Y | Y | Y | Y |
| G5 | P | Y | ? | Y | Y | Y | Y | Y | Y |
| G6 | ? | ? | P | Y | Y | Y | Y | Y | Y |
| G7 | - | - | P | P | Y | P | Y | - | Y |
| G8 | ? | ? | ? | P | P | Y | Y | Y | P |
| G9 | P | P | P | P | Y | P | Y | Y | P |
| G10 | Y | Y | P | Y | P | P | P | P | P |
| G11 | P | P | P | P | P | P | P | P | P |
| G12 | Y | P | Y | P | Y | Y | Y | P | P |
| G13 | P | P | P | P | P | P | P | P | Y |
| G14 | ? | ? | ? | ? | Y | ? | Y | ? | ? |
| G15 | P | P | P | P | P | P | Y | Y | P |
| G16 | Y | Y | Y | Y | Y | Y | Y | - | - |

### Caveats

- CPS-1 (29 October 2026): G3, G8 and G9 moved from `P` to `Y` on the evidence of the section below (26 sets, one tree). G9 `Y`
  rests on captures inspected by the specialist agent, not by the owner. G10 stays `P` (68000 vectors only, no Z80 corpus).

- The G5 and G6 rows say "met" where the check exists as a campaign step.
  Only ng, cps1 and (since 1.6.5) x68 run G5 inside every conversion, and ng,
  cps1 and x68 run G6 inside every conversion. Read G5 and G6 as "met per
  conversion" only for those three.
- G14 for NES, SNES, SMS, GG, GB, CPS-1 and X68 means "no recorded owner
  decision found", not proof that none exists. X68000 and CPS-1 owner trials
  were reported in chat on 27 October 2026 and are not written in a document
  yet; they belong in the owner-acceptance table below when recorded.

## Sharp X68000: evidence behind its column (29 October 2026)

The X68000 stays **experimental**. This is what each gate rests on today and what is still missing, with the file that
shows it. `P` means a part is shown and the rest is named; nothing here says exact hardware, gameplay coverage or latency.

| Gate | X68000 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/x68000.py` (status `experimental`), [X68000.md](X68000.md), `tests/test_system_profiles.py` | |
| G2 | P | Common report v2 (`report_schema.py`, `tests/test_report_schema.py`); the report carries `native_validation`, `final_checks`, `exploration_checks`, `liveness`, `packed_candidate_sha256` | Counters per device: the machine has no cartridge device, so one CPU section only; the old keys are still read by freshness and the library |
| G3 | Y | `final_checks[].interpreted_opcodes` is 0 on the main, mouse and keyboard routes of the four risk cases (below) | Only on the routes run |
| G4 | Y | A fresh interpreted reference per conversion, trace equality (`native_validation.reference_match`, `tests/test_x68000_conversion.py`) | |
| G5 | Y | The compressed copy is replayed on every route against the same reference (`packed_reference_match`, `packed_candidate_sha256`, `retrorecomp/x68000_conversion.py`); R-Type, Metal Sight, Lemmings and Super Hang-On matched on 3 routes each | The published file is compressed again by `publishing.py` (UPX is deterministic: the SHA-256 recorded in the report equals the published one on the run checked) |
| G6 | Y | F9 in a fresh process and the early floppy DMA, now on the compressed copy (`state_checks`) | |
| G7 | Y | `tests/test_x68000_payload.py`: a played disk survives every start and a second build of the same machine identity; a disk of another size, a missing one or a folder in its place is moved to `<name>.unusable-N` and replaced from the executable; a changed host file is treated the same way; the game always starts. `tools/x68000_saves_check.py` on a real game (below): the game wrote to its disk, a relaunch and a second conversion found it as it was | The writes found are file time stamps of 4 to 12 bytes (below): no game was seen saving a score or a position on purpose, which needs play beyond the routes |
| G8 | P | `liveness` in every report, per route and for the delivered file (four risk cases below); captures looked at; an authored route that takes Lemmings into its first level (`tools/x68000_play_routes.py`) | R-Type (into its game-over screen), Metal Sight (in play) and Lemmings (on its authored route) reach play; Super Hang-On stays on its title screen (a start sequence of keys and buttons did not leave it in 4,200 frames) |
| G9 | P | 4,000-frame main route, mouse (10,000 frames for mouse games) and keyboard routes; 18,000 and 36,000 frames at the extended and thorough levels | Not full games |
| G10 | P | Musashi as the reference, 20 authored CPU guards (`native/x68000_native/guard_checks.c`, `tools/x68000_native_check.py`) | No independent vectors replayed through the X68000 generator |
| G11 | P | Authored video, audio, timing, session and disk vectors (`tools/x68000_*_check.py`) | No external emulator or hardware comparison |
| G12 | P | 19 sets converted on Windows and Debian; 418 images of the test collection give 33 multi-disk sets and 84 mouse sets reviewed | Three entries of the test collection stopped the reference: Tetris v5 and TF4G v0.3A09 (a crash of the frame loop, fixed in 1.6.5, both convert now) and Pensan CD (it runs, but makes no sound in 4,000 frames, which the conversion refuses) |
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

What the games write (G7). A survey of 378 starts (the single-disk sets and the first disk of each other set, 3,000 frames of the
qualification inputs, the fresh reference) found six sets that change their own disk: Cybermission (Login), Darius Dokomade
Tatakaemasuka, F-1 Fastest Lap (Michael Company), Hoippuru X68K, Sekizui Hansha De Acchoo v613.61 and Twin Soul. Each changes 4 to 12
bytes, the time and date fields of a file's directory entry (Human68k stamps a file it opens for writing). On Cybermission,
`tools/x68000_saves_check.py` converted the game, ran its player (12 bytes changed on its disk), ran it again (the disk was
kept byte for byte), converted the game a second time and ran that new player over the same data folder (the disk was kept, and no
second data folder appeared). The other 372 starts left their disk as it was; none of them saves a score or a position without play.

A conversion took 133 to 186 seconds on the Windows build PC with these three routes (the compressed replays are 28 to 39 of
them). Picture and sound changing is not gameplay validation, and a route that stays on a title screen proves only that the
machine runs.

## Capcom CPS-1: evidence behind its column (29 October 2026)

CPS-1 stays **experimental**. Each gate with the file or measure that shows it and what is still missing; nothing here says
hardware fidelity, gameplay coverage or latency. Details and tables: [CPS1.md](CPS1.md#qualification), dated measurements in
[CPS1_LOG.md](CPS1_LOG.md#29-october-2026-165-tree-the-whole-panel-routes-captures-and-long-routes).

| Gate | CPS-1 | Evidence | What is missing |
|---|---|---|---|
| G1 | Y | `retrorecomp/systems/cps1.py` (status `experimental`), README, COMPATIBILITY, the interface | |
| G2 | Y | Common report v2 with separate 68000 and Z80 counters (`report_schema.py`) | |
| G3 | Y | `final_checks[].interpreted_opcodes` and `audio_interpreted_opcodes` are 0 on both routes of the 26 sets of the table (29 October, one tree) | Only on the routes run |
| G4 | Y | A fresh interpreted reference per route in every conversion (`final_checks[].reference_match`) | |
| G5 | Y | The compressed copy replayed against the reference (`packed.replay.match`, `packing.compared_on`) | |
| G6 | Y | F8/F9 in a fresh process, damaged state refused (`game_states.validation`) | |
| G7 | - | No non-volatile memory on the standard boards | |
| G8 | Y | `final_checks[].liveness` per route (pictures, last picture change, audible frames, last audible frame) for the 26 sets; a route whose picture never changes is refused | Four attract routes are silent (`dynwar`, `ghouls`, `mtwins`, `unsquad`); every set is audible on its play route |
| G9 | Y | The credited play route of each of the 26 sets reaches play (six captures per set, replayed on the delivered file, inspected); the 18,000-frame route ran on `sf2ce`, `ffight` and `1941` | Inspected by the specialist agent, not by the owner; not full games |
| G10 | P | The three SingleStepTests 68000 fixtures replayed through the CPS-1 generator: the native steps agree with 3,787 of 3,787 vectors and with 80 of 82 authored cases (`tools/cps1_vector_selftest.py`) | No independent Z80 vectors (the corpus has to be downloaded); the CPS-1 Musashi reference differs from the vectors in a few named groups |
| G11 | P | MAME 0.289 comparison of 24 sets and of the sound of three (24 and 27 October) | Measured before 1.6.4 and not repeated; the harness of the 27 October run was not kept |
| G12 | P | 26 sets, all measured on one tree | The panel size policy is not decided |
| G13 | P | Final Fight gives the same route hashes on Windows and Debian 13 (27 October) | One set; not repeated on the 1.6.5 tree |
| G14 | ? | No recorded owner decision (draft row below) | Arthur's play test |
| G15 | Y | The five measures stay separate in the report and in [CPS1.md](CPS1.md) | |
| G16 | - | No CPS-1 path is qualified; the sharing can be withdrawn | |

## Panel sizes

No common panel size exists today. The panel sizes noted by the 27 October
2026 inventory are: Neo Geo 24+10, Mega Drive 24+8, Super Nintendo DSP-1/CX4
8, Super FX 9, NES 8+10+8+6, Game Boy 606, Master System 258, CPS-1 26,
X68000 19. Whether G12 needs a common threshold is a policy decision that has
not been recorded.

## Owner acceptance

Owner play tests (gate G14), one row per test. The table starts empty; the
owner fills it in.

| Date | Console | Games tried | Verdict | Notes |
|---|---|---|---|---|
|  |  |  |  |  |
| _Draft, to fill (CPS-1)_ | Capcom CPS-1 | _suggested: `1941` (vertical), `sf2ce`, `ffight`, `captcomm` (four players), `strider`, `mercs` (vertical, three players)_ | _verdict_ | _Prepared 29 October 2026 for the owner to complete. The owner trials of 27 October 2026 were reported in chat and are not recorded here._ |

### Draft for Arthur: Sharp X68000 play test (G14)

A draft, not a record: the verdict and the notes are yours. Suggested games, each on the delivered executable and not on a
reconversion of the day: R-Type (single disk, the control), Metal Sight (five disks: the disk changes), Lemmings (the mouse is
captured at launch, Ctrl+Alt+M releases it), Super Hang-On (two disks, ejected after loading). For each: it starts without a
window of errors; the controls answer (arrows, W and X, Enter; the mouse for Lemmings); the sound is the game's; F8 then F9
restores; a disk change happens by itself where the game asks for one; and for a game that saves on its disk, save, close, start
again and find the save, then reconvert the game and start the new executable to find it again.

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
