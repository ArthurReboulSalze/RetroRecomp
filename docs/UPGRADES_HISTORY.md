# Upgrading exports: history of releases 1.6.6 to 1.6.4

The per-release detail of releases 1.6.6, 1.6.5 and 1.6.4, moved from [UPGRADES.md](UPGRADES.md) so that each page stays readable (the text and the
anchors of every section are unchanged). The current release and the one before it, the rules and the classification of host and game inputs stay in
[UPGRADES.md](UPGRADES.md); the sections of 1.6.3 and before are in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md).

## Exports of 1.6.5 in 1.6.6

1.6.6 was published on 1 November 2026. This section is the index of its changes: one line per section below, with the stamps that section says
move. Each section computed its stamps for its own change alone (the tree of 1.6.5 and the tree with that change), so a line that
says "the other consoles do not move" is about that change, and the table is the place to add them up. The sections of the earlier
releases follow, newest first (1.6.5, then 1.6.4 and before).

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Master System and Game Gear: WZ in the functions engine](#master-system-and-game-gear-wz-in-the-functions-engine-ordered-word-reads-166) | all nine consoles (`retrorecomp.core` is an input of every console) | no host stamp (build not stated) | not stated |
| [Master System and Game Gear: evidence about the delivered file](#master-system-and-game-gear-evidence-about-the-delivered-file-166) | all nine consoles (`retrorecomp.core`); both consoles join the `conversion_gates` group | not stated | not stated |
| [Game Boy: the Wisdom Tree mapper](#game-boy-the-wisdom-tree-mapper-166) | Game Boy | none | no key moves |
| [Game Boy: the packed replay and the liveness record](#game-boy-the-packed-replay-and-the-liveness-record-166-gates-g5-and-g8) | Game Boy | none | no key moves |
| [Game Boy: the saves of the delivered file are proven](#game-boy-the-saves-of-the-delivered-file-are-proven-166-gate-g7) | none (developer files only) | none | no key moves |
| [Game Boy: states in a fresh process are proven](#game-boy-states-in-a-fresh-process-are-proven-166-gate-g6) | none (developer files only) | none | no key moves |
| [Game Boy: the report names the cartridge and the sound unit, and every conversion checks the states](#game-boy-the-report-names-the-cartridge-and-the-sound-unit-and-every-conversion-checks-the-states-166-gates-g2-and-g6) | Game Boy | no host or build stamp | not stated |
| [NES: the delivered file replayed, liveness, fresh-process states, saves in the report](#nes-the-delivered-file-replayed-liveness-fresh-process-states-saves-in-the-report-166) | NES | not stated | not stated |
| [Mega Drive: 2,895 more independent 68000 vectors](#mega-drive-2895-more-independent-68000-vectors-166) | none (no export changes) | none | none |
| [Mega Drive: the delivered file is replayed and its liveness recorded](#mega-drive-the-delivered-file-is-replayed-and-its-liveness-recorded-166) | Mega Drive and Super Nintendo | not stated | not stated |
| [The 68000 decoding rules of the original chip](#the-68000-decoding-rules-of-the-original-chip-166) | Mega Drive, Neo Geo, CPS-1, X68000 | none | not stated |
| [Super Nintendo: the SA-1 boards, and no Super Mario RPG shortcut](#super-nintendo-the-sa-1-boards-and-no-super-mario-rpg-shortcut-166) | Super Nintendo | not stated | states of 1.6.5 refused cleanly; cartridge saves kept |
| [Neo Geo and CPS-1: the sound CPU's Z80 is corrected](#neo-geo-and-cps-1-the-sound-cpus-z80-is-corrected-166) | Neo Geo, CPS-1 | none | Neo Geo state of 1.6.5 refused; CPS-1 state of 1.6.5 still loads |
| [CPS-1 leaves the experimental status](#cps-1-leaves-the-experimental-status-166) | CPS-1 (it already moves for the Z80 corrections: no extra conversion) | none | no key changes |
| [Sharp X68000: D88 images, floppy format read from the content, fuller report](#sharp-x68000-d88-images-floppy-format-read-from-the-content-fuller-report-166) | Sharp X68000 | none | not stated |
| [Windows: a game UPX cannot pack is published unpacked](#windows-a-game-upx-cannot-pack-is-published-unpacked-166) | none | build stamp of every console (`retrorecomp/packing.py`) | none |
| [Option "Compress games": publish without UPX](#option-compress-games-publish-without-upx-166) | none | build stamp of every console (the same file; summed with the row above) | no key moves |
| [Option "Compress games": publish without UPX](#option-compress-games-publish-without-upx-166) | none | build stamp of every console (`retrorecomp/packing.py`) | none |

Taken together, the sections give the game stamp of **every console** a move between 1.6.5 and 1.6.6, through the first line (the
shared `core`); no section that states its host stamps moves one, and the build stamp of every console moves through the packing
change (last row). What the release does with
`LEGACY_GAME_STAMPS` is the release procedure's decision (the rule above).

## Master System and Game Gear: WZ in the functions engine, ordered word reads (1.6.6)

Two changes of the Z80 code of the Master System and the Game Gear. (1) The "functions" engine keeps the internal WZ register as the
banked engine does, and `BIT n,(HL)` takes its X and Y flags from it (they came from H): Alex Kidd: The Lost Stars passes the comparison
with the reference CPU with it (13 of the 15 games tried pass from an empty learning state, 12 before; the other 14 give the same video
trace and the same interpreter share, pass by pass). Cost, functions engine only: one `s->wz` store per memory, I/O, index, 16-bit
arithmetic, jump, call and return instruction (a RET also reads the popped word once and keeps it for WZ and for the local transfer). (2) A word read of the shared runtime header reads the low byte, then the high byte, in two
statements (it was two reads in one C expression, whose order is not defined); it applies to both engines. The generated sources of the
banked engine are byte-identical on Bank Panic and Factory Panic apart from that header and the version resource. The game stamp of all
nine consoles moves (`retrorecomp.core` is an input of every console; `retrorecomp.cpu` belongs to the Master System and the Game Gear
only); no host stamp does.

Two more changes of the "functions" engine, learning and timing. (3) The counted interpreter records the targets of the CALL, RST and JP
(HL)/(IX)/(IY) it takes (ROM only, once per address and slot bank, 4096 per run at most), so one pass learns the call tree a route reaches
instead of one or two entries: a main loop entered through a dispatch miss no longer stays interpreted. Execution is unchanged and the
banked runtime has nothing of it. (4) A repeating block instruction starts with `sms_tick(0)`, the sync every other instruction has, so
an interrupt asserted at its start is accepted after its first iteration (it was one iteration later). From an empty learning state the
15 games of the 1.6.4 batch all pass the comparison with the reference CPU (13 before these two, 9 in 1.6.4); the first pass is
identical for every game, the last pass of each is at 5 % interpreter (cycles) or less against up to 98 % before (Sonic Spinball
98.4 -> 0.19, Factory Panic 72.6 -> 0.0, Sonic Triple Trouble 46.3 -> 0.001, Super Columns 12.1 -> 0.0, Aladdin 85.5 -> 5.0); the play
routes of Shinobi World and Factory Panic now equal the reference over 3600 frames. Banked sources: unchanged. Nothing is claimed for
hardware fidelity, gameplay beyond those routes or latency.

## Master System and Game Gear: evidence about the delivered file (1.6.6)

Every conversion of the two consoles now records what the delivered file does, through the shared `delivery_evidence` module
(`retrorecomp/sega_evidence.py` is their adapter). The runner's `--vdp-trace` gets two columns, `psg_h` and `psg_nz` (the hash and the
non-zero count of the PSG's stereo samples of the frame); they are written, and the PSG is rendered for them, only when a trace is
written (a probe run), never in the game the player runs. `final_checks[].liveness` carries, per route, the frames, the distinct and
changed pictures, the audible frames and the last audible frame, the distinct sound blocks and RAM states (no program counter: that key
is None, not 0). A conversion whose main (`play`) route never changes picture is refused and the previous export stays; a silent route
is reported, not refused. With the banked engine the conversion also compresses a copy of the build as publication does and replays it
on both routes against the fresh reference (`native_validation.packed_reference_match`, `packed_candidate_sha256`); the "functions"
engine records liveness only. What it does not say: nothing about hardware fidelity, latency, or play beyond the routes.

`tools/sega_states_selftest.py` is the check of the quick states across processes (gate G6): with the harness build of an export it saves with F8, loads in a fresh process with F9 and compares every presented picture with the first process after its save, then checks that a state with a byte changed, a truncated one and one of another cartridge are refused (same pictures as a run that never pressed F9, file left as it was) and that F9 with nothing saved creates nothing. Run on Bank Panic (Master System) and Factory Panic (Game Gear), banked engine; no host or game file changes.

Exports: the only generated source that changes is `runtime_glue.c` (the trace patch); on Bank Panic, Factory Panic and Action Fighter
the other generated sources are byte-identical, the shared trace columns, the frame dumps and the RAM are identical, and only the dump
of the PSG state (`frame.png.psg`, a probe output) differs because the PSG is now advanced during traced runs. The game stamp of all
nine consoles moves with `core`, and both consoles join the `conversion_gates` group (their module `sega_evidence` is in their group).

## Game Boy: the Wisdom Tree mapper (1.6.6)

Five unlicensed cartridges of the collection (Spiritual Warfare, Exodus, Joshua & the Battle of Jericho, the King James Bible, the NIV
Bible & the 20 Lost Levels of Joshua) say "ROM only, 32 KiB" in their header, a size code of 00, and are 128 KiB to 2 MiB long: they are
Wisdom Tree cartridges, whose mapper is a single 74LS377 latch next to the ROM chip ([Pan Docs](https://gbdev.io/pandocs/othermbc.html)).
It switches the whole 32 KiB window, both halves together, and takes the bank from the low eight address lines of a write to
`0000-7FFF`; the data is ignored; there is no RAM; the latch is undefined at power-on, so the cartridges repeat the header and the
switching code in every bank. The pinned runtime treated a header of type 00 as a ROM with a fixed second 16 KiB bank, so these
cartridges never saw their other banks: Spiritual Warfare ran off into illegal opcodes (1,029,772 interpreted cycles at four sites in
1.6.5), and the four others "converted" in 0.23.0 with 2 to 72 million interpreted cycles per scenario.

`gameboy_runtime.adapt_wisdom_tree` adds the mapper to the private copy of `gbrt.c`: a cartridge whose header type is 00, whose size is
a whole number of 32 KiB banks larger than 32 KiB and which holds the words WISDOM and TREE (the detection of mGBA) is a Wisdom Tree
cartridge; `gb_resolve_rom_bank` gives 16 KiB banks `2n` and `2n+1` for the two windows, a write below `8000` sets `n`, and a reset
puts bank 0 (a choice: the latch is undefined). The bank is the existing `rom_bank` field, so the format of the quick states does not
change; the flag is host-only and derived from the ROM.

*What moves.* The Game Boy **game stamp**, through `retrorecomp/gameboy_runtime.py` (and `native/gb_wisdom_checks.c`, a check): no host
stamp, no build stamp, no quick-state key. A cartridge that is not a Wisdom Tree one is untouched: the generated sources and the reports
of Tetris, Super Mario Land and Wario Land II are identical, the final executables of Tetris and Super Mario Land write identical
`--dump-state` files on three input scripts, and only `gbrt.h` and `gbrt.c` of the kept build differ. An export of 1.6.5 is converted again
once, as at every release; the exports of these five cartridges made without the mapper are replaced when they are converted again.

*Hot path: touched, by one test.* `gb_resolve_rom_bank` (called by the dispatch of the generated code and by every ROM read) tests the
flag first, and a write below `8000` tests it once. Not timed.

*Proof.* `tools/gameboy_wisdom_selftest.py` builds a cartridge authored for the check (eight banks, no original bytes): 205 checks of the
mapper (the address chooses the bank and the value does not, either half of `0000-7FFF`, wrap on an eight-bank ROM, state save and
load, reset, and four cartridges that must not be detected), then a program that switches to each bank with a value that means another bank
on any other mapper, calls a routine of each window of each bank and keeps the results in work RAM: the generated code gives the right
bytes and matches the pinned interpreter in lockstep over 17,497 steps. The whole conversion of that cartridge gives zero interpreted
cycles. Converted one at a time with this tree (standard level, empty library), the five real cartridges pass the CPU comparisons with
zero interpreter cycles on every final scenario, except Spiritual Warfare (one site, 96 cycles on the varied route); King James Bible and
NIV Bible run 271,745 and 388,361 instructions one by one from work RAM on the varied route, counted apart. A capture of each shows a real
screen (Enter your NAME and a field of play, the instruction screen of Exodus, the title of Joshua, the text of Genesis in two
translations). That says the mapper works for these cartridges; it says nothing about the rest of each game, about the hardware or about
latency.

## Game Boy: the packed replay and the liveness record (1.6.6, gates G5 and G8)

The Game Boy now gives the same two pieces of evidence as the Neo Geo, CPS-1 and X68000, through `retrorecomp/delivery_evidence.py`
(`retrorecomp/gameboy_delivery.py` holds what is the Game Boy's own).

*Liveness (G8).* The generated main takes a flag, `--frame-trace FILE`, that writes one line per completed frame
(`native/gb_frame_trace.h`, included by the private `gbrt.c`): the hash of the 160 x 144 picture, of the stereo samples of the frame,
the count of non-zero samples, a hash of work RAM and high RAM, and the program counter. Each probe keeps its liveness record in
`final_checks[].liveness` (the nine common keys; a key the trace cannot give is `None`). A conversion is refused when its `varied` route (menu,
movement and buttons) never changes its picture; the other routes are reported, since a game may wait for a key their script does not give.

*Packed replay (G5).* After the lockstep comparisons, a compressed copy of the build, packed as publication does, is replayed on the same
routes with the same frame counts and must give the same verdict line as the build on every one: `native_validation.packed_reference_match`
and `packed_candidate_sha256` (equal to the hash of the published file) are written only then. It costs about as much as the CPU validation
(Tetris: 21 s after 19 s), and the Game Boy takes the group `conversion_gates` of the stamps.

*What moves.* The Game Boy **game stamp** (`gameboy_runtime.py`, `gameboy.py`, the new `gameboy_delivery.py`, `native/gb_frame_trace.h` and the
shared gates the Game Boy now imports). No host or build stamp, no quick-state key, nothing in the generated C changes unless the flag is
given, so a player's game plays the same.

*Hot path: touched.* The audio callback of the runtime adds one test of a static pointer per stereo sample (44,100 a second) and the frame
loop one per frame, both skipped unless the flag is given. Not timed.

*Proof.* `tests/test_gameboy_delivery.py` (eleven tests on synthetic traces and a faked compressor: the reading of a line, the nine keys,
`None` against zero, the main route refused only when frozen, a replay on every route, one different verdict refusing the file, and a
file that was not replayed claiming nothing); the recorded behaviour of the probe (`tests/conversion_common_golden.json`) gains the key
`liveness` (`None` without the trace) and nothing else. One conversion of Tetris: the compressed copy matches on its four routes, the
report says so, and the replay-hash equals the published hash.

## Game Boy: the saves of the delivered file are proven (1.6.6, gate G7)

`tools/gameboy_saves_check.py` converts six cartridges authored for the check (MBC1, MBC2, MBC3 with its clock, MBC5, a cartridge with RAM
and no battery, a battery cartridge that never writes) and runs each delivered file twice, headless, in an empty folder. Nothing in the
converter, the runtime or the generated C changes.

*What moves.* Nothing: the tool and its test (`tests/test_gameboy_saves_tool.py`) are developer files, listed in the public files and in no
stamp. An export of 1.6.5 plays and saves as before. No quick-state key.

*Hot path: not touched.*

*Proof.* The six cartridges pass on the 1.6.6 build: the first run leaves the `.sav` (and the `.rtc` on MBC3), the second reads the pattern
back byte for byte, a run that writes nothing leaves every file as it was, a cartridge that keeps nothing creates no `datas` folder, and
a damaged battery or clock file (short, long, empty, junk) is refused with the game starting normally and the file untouched
([GAME_BOY.md](GAME_BOY.md#qualification)). No defect was found in the runtime.

## Game Boy: states in a fresh process are proven (1.6.6, gate G6)

`tools/gameboy_states_check.py` runs the headless state flags of the delivered file in separate processes: a state taken after N frames,
loaded by a fresh process and run for M frames, must give the dump and the per-frame trace (picture, sound, RAM, program counter) of one
continuous run of N + M frames; a state taken after that load must continue the same way; damaged states and a missing one are refused.

*What moves.* Nothing: developer files only (`tools/gameboy_states_check.py`, `tests/test_gameboy_states_tool.py`), in the public files and in no
stamp; the shared cartridge builder lives in `tools/gameboy_saves_check.py`. No quick-state key.

*Hot path: not touched.*

*Proof.* 29 checks pass on a cartridge authored for the purpose (240 different pictures, 45 different sound hashes over the 240 frames) and on
Super Mario Land converted by the 1.6.6 tree. No defect was found in the state codec. The keys F8 and F9 themselves are not driven (they
need a window); the file has no checksum, so a byte changed inside a file of the right length is accepted ([GAME_BOY.md](GAME_BOY.md#states-and-saves)).

## Game Boy: the report names the cartridge and the sound unit, and every conversion checks the states (1.6.6, gates G2 and G6)

*The report.* Beside the CPU, the Game Boy report (schema 2) now lists two units in `devices`, after the coprocessor entry if a machine has
one: the cartridge's mapper (`kind: cartridge_mapper`: the header type, the mapper family, ROM banks, RAM size and cell width, battery,
clock, rumble, and whether the runtime models that mapper at all) and the sound unit (`kind: audio_unit`). Both are C models of the
runtime, not translated from the ROM and not interpreted, so they carry no counter: `fallback_present` is `None` ("not applicable"), not
zero, and they take no part in the native-code verdict. `saves.cartridge_memory` gives the memory the cartridge keeps and the names of the
files the delivered file writes. Hardware fidelity stays false and stated as such. Cartridge types the runtime does not model (MMM01,
MBC6, MBC7, camera, TAMA5, HuC1, HuC3) say `not_modelled`; no conversion is refused because of it.

*The states.* After the packed replay the conversion runs a state check on the same compressed copy, in an empty folder: a state taken after
60 frames, loaded by a fresh process and run for 60 more, must give the dump of a continuous 120-frame run (registers, cycles, work and
high RAM, LY and PPU mode); ten damaged copies of the state and a missing one must be refused and create nothing. The verdict is in
`game_states.fresh_process_verified` and `game_states.validation` (the fields the Neo Geo, CPS-1 and X68000 reports already use); a failure
is reported and does not stop the conversion. It costs about 1.2 s (Tetris).

*What moves.* The Game Boy **game stamp** (`gameboy.py`, `gameboy_delivery.py`, the new `gameboy_cartridge.py`). No host or build stamp. The
executable and every generated file are byte for byte the same (below), so a player's game plays and saves as before. Only
`conversion-report.json` gains keys. Common code touched: `report_schema.py` (the `hardware_devices` reading, additive; `fallback_summary` and
`tools/release_check.py` now take the cartridge coprocessor by its `kind` instead of `devices[0]`, same result for every other machine).

*Hot path: not touched.*

*Proof.* `tests/test_gameboy_cartridge.py` (header facts, the runtime's lists, Wisdom Tree detection, the devices read back through
`read_report`, the native-code verdict and the summary unchanged by the new entries) and `tests/test_gameboy_states_tool.py`. A/B from the
main checkout against the commit this branch left (`tools/ab_conversion.py`): on Tetris all 128 compared files are identical and the only
differences are the new report keys (99 lines: `hardware_devices`, `cartridge_memory` and `game_states`, and the schema-2 `devices`, `saves` and
`states` built from them; timings are not compared).

## NES: the delivered file replayed, liveness, fresh-process states, saves in the report (1.6.6)

*The NES game stamp moves; exports are rebuilt from their learned paths. What a player's game does is the same, except in PAL
(below).* The host file `cyc_host.c` that the converter writes for the game gains, in its headless mode only (`--hash-out`), a hash
of the rendered picture, a hash of the frame's sound and an audible flag on each trace line, and turns the audio on when a
trace is asked for. A game started normally does not run any of it. A/B on Balloon Fight, Asterix and The Legend of Zelda against
the previous tree: every trace line is the same once those three fields are removed (CPU, memory, hardware, registers, cycles),
the reports differ only by the new fields (`final_checks[].liveness`, `reference_frames`, `native_validation.packed_reference_match`,
`packed_candidate_sha256`, `game_states` filled, `saves`).

What a conversion now does that it did not: it compresses a copy of the build and replays it on every route against the fresh
reference (a difference stops the conversion), reads a liveness record of each route and refuses a game whose main route never
changes its picture, and checks F8/F9 in a fresh process on the delivered copy. Conversions take a few seconds more at the default
level and more at the thorough one (each route is replayed once more at native speed).

*PAL: /NMI is sampled at tick 6, not 5, of the 16-tick CPU cycle* (`nes_machine.py`; [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-166)).
A PAL game with its clock aligned one way sees an interrupt one CPU cycle later on every other frame; Asterix, Mr. Gimmick and
Parodius give identical frame, audio and state evidence on their routes.

One conversion of Asterix failed in an A/B run of this tree against `main` on 1 November (14:39) and passed when run again (14:43);
the run's logs were not kept. The likely cause, not proved from those logs, is the one found on a Castlevania III conversion the
same afternoon: Windows Defender deleting UPX's temporary file (a false positive), which `main` now answers by publishing such a
game unpacked.

The NES speed-ups and the completion of RAM routines (the mapper number a constant on every toolchain, the MMC1 A12 rebuild
skipped when it cannot matter, the deferred PPU clock in PAL, the RAM routines completed at the end of a run) are not changes of this
release: they shipped in 1.6.5 (`git tag --contains` gives `v1.6.5` for each; see
[Other machines whose game stamp moves in 1.6.5](#other-machines-whose-game-stamp-moves-in-165) and [NES.md](NES.md)).

## Mega Drive: 2,895 more independent 68000 vectors (1.6.6)

A new fixture, `tests/fixtures/m68k-groups`, holds SingleStepTests vectors for 85 instruction groups the other fixtures do not
have, replayed through the Mega Drive generator by `tools/megadrive_groups_selftest.py`. **No export changes and no stamp moves:**
the fixture, its builder and its self-test are development files, and the harness (`native/md_prefetch_checks.c`) only gained a
mode that lists every failing vector instead of stopping at the first. 2,315 of the vectors agree on every check, and 580 differ
in the ways [CPU_68000.md](CPU_68000.md#what-the-groups-fixture-found-since-166) lists (final state in 51, total clocks in 83, bus
layout in 446); nothing was adapted for them in this release. The three other replays (`md-prefetch`, `m68k-shifts`,
`md-exceptions`) pass as before.

## Mega Drive: the delivered file is replayed and its liveness recorded (1.6.6)

The conversion of a Mega Drive game now does what Neo Geo, CPS-1 and the X68000 do (`retrorecomp/delivery_evidence.py`, the
Mega Drive's part in `retrorecomp/megadrive_evidence.py`, called from `console16.convert16`):

- **Packed replay (G5).** After the reference comparison, a copy of the build is compressed as publication does, and that copy is
  replayed on every route (same arguments, same input scripts, chained routes from their own saved states) and compared with the
  fresh reference of the same route by `reference_differences`, the comparison the build already passes. The report gains
  `native_validation.packed_reference_match` and `packed_candidate_sha256`; the packing record says the compressed copy was replayed.
  A difference stops the conversion and keeps the previous export.
- **Liveness (G8).** The replays pass `--trace` (the 16-bit host already wrote it: picture hash, sound hash, program counter, FM and
  PSG non-zero counts per frame), and each route's trace becomes `final_checks[].liveness`: frames, distinct pictures, picture changes,
  last picture change, audible frames, last audible frame, distinct sound blocks and program counters. A frame is audible when the FM
  or the PSG produced a non-zero sample in it. A key the trace cannot give is `null`, never 0. It is evidence that the picture and the
  sound change on the route; it says nothing about what the picture shows, how deep the route goes, or latency.
- **A frozen main route is refused.** A conversion whose `play` route never changed the picture stops (the game never started or is
  stuck). The attract route presses no button and a game may wait for Start on one title picture, and the long and authored routes may
  sit in a menu, so none of those is refused.

*Edited:* `retrorecomp/console16.py` (the trace option of the probe, the fresh references kept, the replay and the report fields, all
for the Mega Drive only), the new `retrorecomp/megadrive_evidence.py`, and `retrorecomp/systems/console16.py` (the Mega Drive joins the
`conversion_gates` group, which `delivery_evidence` calls). **The `md` game stamp moves; so does the Super Nintendo's**, because
`console16.py` is a game input of both 16-bit consoles; the Super Nintendo path is unchanged and does not run the new steps. No generated
code changes: a Blockout, a Sonic The Hedgehog and a Gunstar Heroes (USA) conversion compared with the tree before the change by
`tools/ab_conversion.py` differ only by the new keys and files (the liveness, the packed fields, `checks/packed/`), the profile data
and the changes of the decoding rules of this release; every generated source, frame, audio and state hash is identical.
**Cost:** one more run of each native route on the compressed copy (not the reference runs, which are the long ones) and one
compression; not timed. A game whose `play` route is frozen would stop converting: none of the three does, and Arthur's collection has
not been re-run for this.

## The 68000 decoding rules of the original chip (1.6.6)

The decoder the converter uses is written for the 68010 and the 68020 as well and accepts more than a 68000 knows. Four machines hold a
68000 (Mega Drive, Neo Geo, CPS-1, X68000), and their offline decoding tools now apply the Motorola manual's rules, in one shared
header (`native/md_exception_decode.h`, which already held the reserved words `$4AFA` and `$4AFB`):

- `MOVEC` (`$4E7A`, `$4E7B`) and `BKPT` (`$4848` to `$484F`) are not 68000 instructions, and `JMP`, `JSR`, `LEA` and `PEA` accept
  only a control addressing mode: (An), d16(An), d8(An,Xn), abs.W, abs.L, d16(PC), d8(PC,Xn). The 390 opcode words that break those
  rules (`LEA` 288, `JSR` 36, `JMP` 36, `PEA` 20, `BKPT` 8, `MOVEC` 2; the 388 of the first four families plus `MOVEC`) were
  translated as if they existed; they are now the illegal instruction exception (vector 4), one word, like `$4AFC`.
- A branch whose 8-bit displacement is `$FF` (`$60FF` to `$6FFF`) is a one-word branch with the displacement -1, as on the 68000.
  The decoder had read the 32-bit displacement of the 68020 and made it three words long. The validator still refuses it as
  speculative code (the tools skip it), so no scan translates it; the change is the length and the target the reference path and
  the X68000 table of instruction lengths see.
  A `$6xFF` that a game really takes is not an address error here: the error is not modelled, and the reference path goes on
  at the odd address, as it did before for any odd program counter (not a regression).

*Edited:* `native/md_exception_decode.h` (moved to the 68000 family of the stamp manifest, so that it moves the stamps of all four
machines, which it did not do for the Neo Geo, CPS-1 and X68000 before), `native/x68000_native/decode.c` (its table of lengths now
applies the same rules), and the new check `native/m68000_decode_rules_checks.c` with `tools/m68000_decode_rules_selftest.py`.
**The `md`, `ng`, `cps1` and `x68` game stamps move.** The generated code differs only where data was read as code: the Neo Geo
sweeps every even address of its fixed apertures, and a speculative scan elsewhere can reach such a word; a word a game really
executes is unchanged unless it is one of the 390. No host or build stamp moves.

Checked on the 65,536 opcode words against an expectation written from the manual's addressing-mode tables (no other word changes
its decoding), on 25 hand-written byte sequences, and on the four real decoding tools and the X68000 length table with the same
bytes; every one of those fails on the previous header (`LEA D0,A0` came out as `LEA`, `MOVEC` as `MOVEC`, `BKPT #0` as `PEA`, the
`$60FF` branch three words long). The Mega Drive, Neo Geo, CPS-1 and 68000 backend self-tests still pass. This is a CPU fidelity
change of what the decoder accepts; it is not a statement about any game's behaviour.

**Conversions compared (A/B, `tools/ab_conversion.py`):** around the header alone (Blockout, `ab-md-166.log`), the generated
sources are identical; only `md_exception_decode.h` itself, the clang profile data and the compression ratio (0.2642 against
0.2641) differ. On three games (Blockout, Sonic The Hedgehog, Gunstar Heroes) with the G5/G8 change added, the exports differ
only by the profile data and the compression ratio, apart from the new evidence keys and files.

## Super Nintendo: the SA-1 boards, and no Super Mario RPG shortcut (1.6.6)

The Super Nintendo game stamp moves (`snes_codegen.py`, `snes_cart.py`, `snes_chips.py`, `supernintendo.py` and the native SNES
files change), so every Super Nintendo export of 1.6.5 is converted again once, as at every release. Quick states of
the previous release are refused cleanly ([GAME_STATES.md](GAME_STATES.md)); cartridge saves are kept. What changes for a player:

- **The pinned engine's wait-loop shortcut for one title is off.** In a Super Mario RPG battle the loop at `$C0:84B2` is executed
  instruction by instruction, as the interpreter would; the cycle count is the same, the host does more work there. No other
  cartridge is affected (the shortcut checked that cartridge's bytes).
- **The vblank-wait fast-forward at fixed addresses of Star Ocean and Super Mario RPG is off too** (no engagement seen in
  the routes run; a second per-game shortcut of the same engine).
- **SA-1 cartridges are accepted** (map `$23`, type `$34` or `$35`, up to 4 MiB); the SA-1 program is a counted interpreted
  device, like the Super FX GSU, and its BW-RAM is the battery file (type `$35`) and part of the quick state. The S-CPU
  reaches it at the clock of its own bus cycle and its IRQ follows its flags (only SA-1 boards run that code).
- **S-DD1 cartridges are accepted up to 4 MiB** (map `$32`, type `$43` or `$45`; Street Fighter Alpha 2). Star Ocean (6 MiB)
  stays refused. The report counts the chip's decompression sessions.
- **Cost:** about 35-155 thousand SA-1 instructions are interpreted per frame in the three SA-1 titles proved; host time was
  not measured (to be timed on a quiet PC).

## Neo Geo and CPS-1: the sound CPU's Z80 is corrected (1.6.6)

The Z80 of Geolith, which plays the sound of the Neo Geo and of the CPS-1, is corrected in the converter's copy (19 strict replacements,
[UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-166)): the WZ and flags of `IN r,(C)`, the X and Y flags of `LD A,I`, `LD A,R`
and of the repeating block instructions, the WZ of `LD IX/IY,(nn)`, the port address and flags of `OUTI` and `OUTD`, IFF1 after `RETI`, and the
undocumented `ED` encodings. They are CPU fidelity corrections checked against 51,328 independent vectors (51,260 states and all clocks agree now,
50,429 and 51,200 before). On conversions of `sf2ce`, `ffight`, `nam1975` and `mslug3` with `tools/ab_conversion.py`, the picture and sound hashes
of every route are identical before and after; the Z80 and hardware hashes (registers and memory of the sound CPU) differ only where a game reads
what was corrected (`LD A,R` in `nam1975`, `LD IX,(nn)` and `IN r,(C)` in `mslug3`).

Stamps (computed with the tree of 1.6.5 and the tree of this change): the **Neo Geo and CPS-1 game stamps move**
(`retrorecomp/neogeo_z80.py` is a game input of both, and `cps1_knowledge.GENERATOR_REVISION` goes to 9); host and build stamps, and the other
seven consoles, do not move **for this change**. A Neo Geo or CPS-1 export of 1.6.5 is converted again in full once. **Quick states**: the Neo Geo key hashes the
fingerprint of `neogeo_z80` (`neogeo_conversion.py`), so a Neo Geo state of 1.6.5 is refused cleanly; the CPS-1 key does not hash that module
and the 34-byte Z80 block of its state did not change, so **a CPS-1 state of 1.6.5 still loads** (it continues with the corrected core, from the
registers it saved).

## CPS-1 leaves the experimental status (1.6.6)

The CPS-1 profile is `supported` (owner's decision of 1 November 2026, on the evidence in [QUALIFICATION.md](QUALIFICATION.md); his own play
trial of the 1.6.6 executable is still to do). What changes for a player and for the files:

- **Reports.** A CPS-1 conversion whose final routes interpreted no 68000 and no Z80 instruction now writes `status: completed` (the
  Neo Geo rule); one that interpreted some keeps `experimental` as its stage, and the window then says "Created · experimental". The
  schema 2 field `knowledge.machine_status` says `supported`.
- **Interface.** The CPS-1 note in Options no longer says "experimental", and the Knowledge pop-up lists CPS-1 with the shared consoles (its
  paths still count only for the engine revision that validated them), in the eight languages. The X68000 keeps its experimental labels.
- **Linux.** The profile is `witnessed` (three sets give the same route hashes on Debian 13), so the Linux converter no longer refuses CPS-1.
  Interactive play, sound and pads on Linux were not witnessed.
- **Shared base.** Nothing moves: CPS-1 stays in the experimental tier (schema 3 only, line 3 of the base, withdrawable with
  `path_profiles.EXPERIMENTAL_SHARED`); the status label is not read by any sharing code.
- **Stamps.** `retrorecomp/systems/cps1.py` is a game input of the CPS-1, so its game stamp moves; it moves already in 1.6.6 for the Z80
  corrections below, so this adds no conversion. Host and build stamps and the other eight consoles do not move (checked against the tree
  just before this change). No quick-state key changes.

## Sharp X68000: D88 images, floppy format read from the content, fuller report (1.6.6)

The converter now takes D88 floppy images and recognises DIM, XDF and D88 by their content rather than by their name
([X68000.md](X68000.md#disk-image-formats)). A standard 2HD D88 is stored as the raw XDF it describes, so the player, the
quick states and the saves are unchanged. **Identities do not move**: a DIM or an XDF has the manifest and the game key it had
in 1.6.5 (the new `stored_from` field is written only for a D88), and a D88 of a disk has the same identity as its XDF. The
conversion report also records more of what it checked (digests of the reference traces, the length and digest of each
exploration route, the quick-state validation, ordinary saves, players and peripherals) under the common report v2; nothing
reads them back to decide a game.

Stamps (computed with the tree of 1.6.5 and the tree of this change): only the **Sharp X68000 game stamp moves**
(`retrorecomp/x68000_media.py`, `retrorecomp/x68000_conversion.py` and `tools/x68000_reference.py` are game inputs of that
console and nothing else); host and build stamps and the other eight consoles do not move **for this change**. An X68000 export of 1.6.5 is converted
again in full once, like the other experimental exports of a release that changes the converter.

## Windows: a game UPX cannot pack is published unpacked (1.6.6)

On Windows a failure of UPX stopped the whole conversion. Windows Defender's machine-learning detection
(`Program:Win32/Contebrew.A!ml`, a false positive) has removed UPX's temporary output while it packed freshly built Neo Geo
and NES games; UPX then ended with "IOException ... Invalid argument" after minutes of conversion work. Windows now does what
Linux has done since 1.6.0 (`packing.compact_windows`): the validated executable is kept beside UPX's work, put back when UPX
cannot pack and test the file, and published unpacked, exactly as built and validated (a larger file, the same program), with the
reason in the conversion log and the report (`packing.packed` false, `packing.unpacked_reason`; the notice says when the antivirus
most likely removed the file). A missing or altered UPX, or an original that cannot be put back, is still an error. Games that
pack and pass are byte for byte what they were. `retrorecomp/packing.py` is a build input of every console: the build stamps move,
no game stamp, no quick-state key.

## Option "Compress games": publish without UPX (1.6.6)

A global option, **Options > Common > Compress games** (preference `compress_games`, on by default: today's behaviour), and the
switch `--compress` / `--no-compress` of `convert` and `batch` (without a switch, the saved option applies). It exists because
Windows Defender's machine-learning detection (`Program:Win32/Contebrew.A!ml`, a false positive) sometimes flags a freshly built,
UPX-packed game; an unpacked game is 3 to 4 times larger and the same program. With the option off `packing.compact_executable`
does not run UPX: the executable is published exactly as built and validated, the conversion log says "Published uncompressed:
the player turned the "Compress games" option off" and the report has `packing.packed` false with that text as
`packing.unpacked_reason`. The gate G5 copy follows without any change to `conversion_gates` or `delivery_evidence`
(`pack_candidate` calls `compact_executable`): the Neo Geo, CPS-1 and X68000 packed replay replays an unpacked copy,
`DeliveredFile.kind` is `unpacked` and the comparison line says "unpacked"; `packing_record` then says in `compared_on` that the
delivered file replayed is not compressed. The window and the command line set the option for the process before a conversion starts
(`packing.set_compression`); a conversion never reads the preferences file itself. The option is an interface preference that no
converter receives (`INTERFACE_PREFERENCES`), so it is not part of a game's request signature: a game that is up to date is not
rebuilt because the option changed (**Force regeneration** or `--force` publishes it again).

Stamps (computed with the tree of the commit before and the tree of this change, `compilation_inputs.role_stamps` of the nine
consoles): only the **build stamp of every console moves**, because `retrorecomp/packing.py` is a build input of every console (it
already moves for the Windows fallback above: the two changes are summed in the row, not twice). The host stamps and the game
stamps do not move. The new interface strings are in `retrorecomp/i18n.py` (an interface module) and in `assets/locales/*.json`
(`assets/locales/` is declared out of every stamp), and `retrorecomp/gui*.py` and `RetroRecomp.py` are out of the stamps too.
`conversion_gates` and `delivery_evidence` are not edited, so the consoles that share them keep their game stamps. No quick-state
key moves. A build change rebuilds an export without rediscovery; an export of 1.6.5 keeps its packed file until it is converted
again.

## Game Gear: F5 sprite flicker reduction, and two files change group (1.6.5)

Game Gear exports gain the **F5** sprite flicker reduction that the Master System has had since 0.25.0 (off by default, saved in
`[GameGear.Video] reduce_sprite_flicker`; the Game Gear VDP has the same eight-sprite line limit). The renderer change is in
`native/video_mode4.inc` (the three Game Gear guards are gone: with the option off the code does less, not more) and the key, the
F2 row and the setting are in the shared adapter `native/hostkit/adapters/rrhk_sms.c`. The option changes the presentation only: no
ROM patch, collision and overflow flags keep using the original eight sprites, and the checks of the native and the reference
renderer still agree on every scene (`tools/pixel_optimization_selftest.py`, `tools/video_selftest.py`).

Stamps (computed with the tree of 1.6.4 and the tree of this change): the **game stamp of the Master System and the Game Gear moves**
(renderer) and so does their **host stamp** (adapter); like every export of 1.6.4, they are converted again in full once. In the same change
`native/video_mode4.inc` and `native/video_checks.c`, which only the Master System and the Game Gear use, move from the group
owned by every console to the group of those two (`retrorecomp/stamp_inputs.py`): the manifest of the seven other consoles loses
two files, so **their game stamp moves once** (host and build stamps do not), and later edits of these two files move only the
two Sega consoles. A Game Gear export of 1.6.4 or before keeps answering "Config unavailable" to F5 until it is rebuilt.

## Master System and Game Gear: repeating block instructions in the functions engine (1.6.5)

Exports made with the "functions" engine are reconverted: a repeating block instruction (`LDIR`, `CPIR`, `OTIR` and the others)
that goes on after an iteration now leaves the flags of the NMOS repeat cycle, as the banked engine and the reference CPU
already did (X and Y from the high byte of the instruction's address, H and P from B for the input and output groups). It
shows when an interrupt is accepted between two iterations and pushes AF; Alex Kidd: High-Tech World passes the comparison with the
reference CPU with it (CPU fidelity on the project's own tested routes, nothing about hardware, gameplay or latency). The default banked engine
generates the same sources (checked byte for byte on Bank Panic and Factory Panic); 13 of the 15 games tried give the same video trace
with and without the change, from an empty learning state (the other two are High-Tech World and The Lost Stars, which the change targets). The game stamp of all nine consoles moves with `core` (`retrorecomp.core` is an input of every console).

A second change of the same engine: a `RET` that pops an address the routine pushed itself ("push continuation; jump; ret") now
continues at that address, as the Z80 does, instead of resuming the caller (each generated function keeps its entry SP; a tail jump
whose callee returned below it does the same; nesting bounded at 256, beyond it the continuation runs in the counted interpreter and is counted as `ret_nest_overflow`, 0 on the 15 games tried). Action Fighter and Super Columns pass the comparison with the
reference CPU with it; the 9 games that passed still pass with the same demo trace, and the banked sources are byte-identical on Bank Panic
and Factory Panic. Cost, functions engine only: one load and one local store per function entry and one compare per `RET`;
nothing per ordinary instruction. The route "play" of three passing games (High-Tech World, Shinobi World, Factory Panic) is not
part of the gate and already differs from the reference in a clean learning state (from frame 3032 for Shinobi World, with or without
this change); it differs from the earlier run after that frame.

A third change: a jump that crosses a 16 KiB slot inside one generated function now goes through the bank-checking dispatch instead of a
`goto` (Sonic Triple Trouble passes the comparison with it; every other game gives the same demo and play trace as before, except Sonic
Spinball, which fails later). From an empty learning state 12 of the 15 games tried pass; Alex Kidd: The Lost Stars, Sonic Spinball
(Game Gear) and Aladdin do not. Cost, functions engine only: a direct jump across slots becomes a dispatch call (a target that is not a function entry costs a few counted interpreter steps until the next pass learns it: Alex Kidd in Miracle World shows 0.154 % interpreted in its first pass against 0.0 % before).

Interpreter share per pass (demo route, `main` before these changes -> this branch, from an empty learning state; native code is 100 minus this): the first pass is within 0.2 points for 14 of the 15 games (Lost Stars 61.9 -> 32.6 %); the last pass is equal or lower for every game that passes (Super Columns 59.6 -> 12.1, Action Fighter 34.1 -> 6.3, Shinobi World 19.0 -> 8.7; High-Tech World 0.222 -> 0.333). It is higher for the games that still fail (Aladdin, Sonic Spinball, Triple Trouble before it passed), where the run beyond the first divergence is no longer the same run. The main loop of Aladdin and Spinball is entered through a dispatch miss in the first pass (99 % interpreted, with or without this change).

## Mega Drive: the clocks of register-count shifts (1.6.5)

A Mega Drive shift or rotate with its count in a register (`LSL.W D1,D0` and the seven other mnemonics) was charged the pinned
core's estimate for a count of four, whatever the count. It is now charged what the MC68000 manual gives: `6 + 2n` clocks for a
byte or a word, `8 + 2n` for a long, `n` being the count modulo 64 read before the shift. The immediate-count and memory forms
keep their figures. The time is set in `retrorecomp/megadrive_codegen.py` (`adapt_shift_timing`), for the native bodies and for
the reference path alike, through the bus hook that `MULU` uses (the prefetch read first, then the internal clocks); the
shared `m68000.py` is not touched, and Neo Geo, CPS-1 and X68000 already charged this time. It is a **CPU
fidelity** fix about clocks; the other four measures are not moved by it. *Edited:* `retrorecomp/megadrive_codegen.py` (a game
input). **The `md`, `cps1` and `x68` game stamps move**, because `megadrive_codegen` is in the stamp groups of the CPS-1 and
the X68000 profiles (they import its `write_changed` and the decoder tool); the CPS-1 and X68000 output is unchanged, as the
hook is applied only by `megadrive_codegen`'s `generate_steps` and `adapt_interpreter`. No host or build stamp, no native file,
no quick-state key, not the base. Because it changes the clocks a Mega Drive game runs on, the Mega Drive exports of 1.6.4 are
converted in full, not upgraded (`LEGACY_GAME_STAMPS` must list no 1.6.4 entry for the Mega Drive; it is empty today); the
CPS-1 and X68000 exports have the same code and only a moved stamp, so the release procedure decides for them as for any
stamp-only move. **Cost:** one out-of-line hook call per register-count shift executed, as `MULU` and `DIVU` already pay (the
`reg_count` test is a compile-time constant in the native steps); not timed. Checked with the 834 SingleStepTests shift vectors replayed with their clocks on the
native and the reference paths (they cover `ROXL`, `ROXR` and `ASL.L`; the other mnemonics share the line but have no vector of
their own yet), and by one conversion of Blockout compared with the tree before the change (`tools/ab_conversion.py`): both
succeed, 0 interpreted 68000 instructions and 0 interpreted Z80 cycles on the demo and the play routes in both, native and
reference runs equal. The frame, RAM, VRAM, FM, Z80 and sequence hashes, the instruction set learned in the first pass and the
generated step sources differ, as expected, because a different count of clocks moves where the interrupts fall (Blockout
has seven register-count shifts); that is a change of clocks, not a regression, and no measure of play, latency or speed is made by it.

## Mega Drive: BUSACK at the end of the sound CPU's machine cycle (1.6.5)

The 68000 now sees the grant of the Z80 bus (`$A11100` bit 0) at the end of the sound CPU's machine cycle in progress when it
wrote BUSREQ, also when the sound CPU already stands ahead (its last instruction of a line retires beyond the line), and as soon as
that date has passed, not only after the 68000 has caught up to the sound CPU's clock. Barkley Shut Up and Jam! (USA), which does
not loop on the bit and stopped converting, now converts. The sound CPU resumes after the release as before. Details and the
ROM-free reproducer: [MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md#busack-after-a-line-end--2026-10-30-165).
*Edited:* `native/md_z80_bus.inc`, `retrorecomp/megadrive_bus.py` and `native/md_boundary_checks.c` (its reproducer), all game
inputs of the Mega Drive only. **The `md` game stamp moves**, and with the native files the Mega Drive quick-state key. A quick
state now also carries the sound CPU's eight latest machine-cycle ends (72 bytes after the machine section's tail), so the first
BUSACK after F9 is dated as in an uninterrupted run; the machine section grows by those bytes and a state of an earlier build is
refused cleanly (quick states are not carried over in 1.6.5). Because a game that polls the bit can
now see the grant one poll earlier, the Mega Drive exports of 1.6.4 are converted in full, not upgraded. **Cost:** one compare and
one store per sound-CPU access, I/O cycle and instruction end, one condition per arbiter loop, and a scan of at most eight entries
per BUSREQ write; nothing on the 68000's instructions or bus accesses; not timed.

Checked by `tools/ab_conversion.py` on 13 games against the tree before the change. All 26 conversions succeed, keep 0 interpreted
68000 instructions and 0 interpreted Z80 cycles on their final demo and play routes, and their native and reference runs agree.
Blockout gives identical outputs (only the changed sources, the clang profile built from them and the packed size ratio differ).
In the 12 others the sound, the Z80 and 68000 state and, for some, the picture sequence change. For each of them both executables
were replayed with a per-frame trace and a per-frame hash of the arbiter's events: on both routes, the first frame that differs is
the first frame whose arbiter events differ, and the first differing event is a 68000 read of `$A11100` that the previous rule
answered "not granted" and that is now "granted", made after the end of the sound CPU's cycle following the request:

| Game | Demo: frame, read / sound CPU (master clocks) | Play: frame, read / sound CPU |
|---|---|---|
| Sonic The Hedgehog 2 (USA) | 682, 637 / 615 | 1337, 1463 / 1440 |
| Sonic The Hedgehog 3 (USA) | 279, 269 / 255 (ahead after the line end) | 279, same |
| Gunstar Heroes (USA) | 808, 3525 / 3420 | 431, 638 / 615 |
| Streets of Rage 2 (USA) | 153, 2726 / 2700 | 153, same |
| Mortal Kombat II (USA) | 1178, 1665 / 1650 | 977, 2355 / 2355 |
| Street Fighter II' Plus - Champion Edition (Japan) | 531, 3169 / 3150 | 332, 3184 / 3165 |
| Super Street Fighter II (USA) | 471, 590 / 585 | 332, 745 / 720 |
| Comix Zone (USA) | 49, 3157 / 3135 | 49, same |
| Thunder Force IV (Japan) | 708, 3387 / 3360 | 346, 3520 / 3495 |
| Contra - Hard Corps (USA) | 2759, 1886 / 1860 | 875, 2511 / 2490 |
| Earthworm Jim (USA) | 1709, 3510 / 3420 | 1989, 218 / 225 (ahead after the line end) |
| Ecco the Dolphin (USA) | 116, 2921 / 2895 | 116, same |

The previous rule recorded the grant only once the 68000 had been run up to the sound CPU's clock, and that run can end one
instruction later, so a poll made there was answered "not granted". These are differences of the bus model observed by the
game, explained frame by frame; they are not measurements on a console and say nothing about play beyond these routes.

## Mega Drive: the supervisor RESET instruction is executed (1.6.5)

A cartridge that executes the 68000 `RESET` instruction (opcode `$4E70`, supervisor mode) used to stop the conversion: the pinned
core halted on it as unimplemented, and the demo probe failed. Boxing Legends of the Ring runs it at boot (at `$30C`, in its second
frame). According to the hardware notes (C. MacDonald, "Fun with reset signals", SpritesMind, 2012) the instruction pulses only the
VRES# line, which goes to the 68000 and to the cartridge port; no other reset is driven. Genesis Plus GX, BlastEm and Musashi
likewise do nothing but spend the clocks (none resets the YM2612). This was not measured here. The instruction is therefore executed
as a native instruction that changes nothing but the program counter and takes its 132 clocks (the manual's figure, one prefetch
read). The pulse itself is not modelled, and no cartridge circuit of this converter reacts to it. **Open case:** a cartridge mapper
that resets on VRES# (the Sega 512 KiB bank mapper, `physical_rom_mapper` `sega_512k`, is the plausible candidate) would return to its
starting banks on a console, whereas here nothing happens; neither Boxing Legends nor Dragon's Revenge uses it. A user-mode `RESET`
still takes the privilege violation (vector 8), checked natively and on the reference path in `tools/megadrive_native_selftest.py`. *Edited:* `retrorecomp/megadrive_codegen.py` (`adapt_reset`, applied to the native bodies and to the reference
path; `m68000.py` is untouched, so Neo Geo, CPS-1 and X68000 keep their own handling). It is a **CPU fidelity** fix; the other four
measures are not moved. **The `md`, `cps1` and `x68` game stamps move** (the module is in their stamp groups; their output is
unchanged), together with the shift-clock change above, and a Mega Drive game that never executes `RESET` generates the same code:
a conversion of Blockout compared with the tree before the change (`tools/ab_conversion.py`) differs only in the generation
identity, the text of the reference interpreter and the step analysis derived from it, with every frame, audio and state hash and
every report field identical. Checked by the manual total of `RESET` on both paths (`tools/megadrive_cycles_selftest.py`: 132
clocks, program counter advanced by two) and by a conversion of Boxing Legends of the Ring, which now succeeds (0 interpreted 68000
instructions and 0 interpreted Z80 cycles on its demo and play routes; the picture and the sound change during them). Dragon's Revenge, listed for the same instruction,
also converts now (same result on its demo and play routes: 0 interpreted 68000 instructions, 0 interpreted Z80 cycles). Gameplay beyond those
routes is not validated for either.

## Mega Drive on Windows: ThinLTO and a clang profile (1.6.5)

On Windows with the portable llvm-mingw tools, a Mega Drive game is now built twice, like a Super Nintendo game since 1.6.4: a
first build with clang's instrumentation and ThinLTO runs a private 1,800-frame `--play` training run, then the engine's own
sources (never the generated cartridge steps) are rebuilt with that profile. It changes how fast the same C runs, not what it does;
`RETRO_RECOMP_PGO=0` switches it off, Visual Studio keeps the ordinary build, and a training run that fails builds without the
profile. *Edited:* `retrorecomp/console16_optimization.py` (`CLANG_PROFILE_CONSOLES = ('snes', 'md')`), shared by the Mega Drive
and the Super Nintendo: it is a **game** input of both, so the **`md` and `snes` game stamps move** (nothing else: no host or
build stamp, no native file, no quick-state key, not the base). The Super Nintendo build is unchanged. The conversion runs one
training pass and one more build per game; no gain is claimed or timed here. Checked by one conversion each of Blockout, Sonic The
Hedgehog and Gunstar Heroes (USA) with `tools/ab_conversion.py`, the tree of 1.6.5 before the change against this one: all six
conversions succeed, and the only differences are the ones that come from the build itself: the profile file
(`hardware-profile.profdata`, only in the new tree), `hardware-optimization.json` (`profile_guided`) and the size ratio of the
packed executable. Every frame, audio, state, RAM, VRAM, FM, PSG and Z80 hash, every counter of the reports (so the counted interpreter fallback of
the 68000 and of the Z80 is the same as before) and every generated source are identical. That is a check of equal outputs; the speed is not measured (a quiet-PC measurement is the lead's).

## Neo Geo: a 64 KiB fixed-graphics ROM is repeated, and the native game gets a clang profile (1.6.5)

Two changes of the Neo Geo converter, both in the game stamp of the Neo Geo.

- **A 64 KiB fixed-graphics ROM (S1) is repeated up to 128 KiB when the cartridge is assembled** (`neogeo.mirror_short_fixed_rom`,
  called by `neogeo_build.convert_reference` right after the preparation tool). Last Hope (NG:DEV.TEAM) is the first such cartridge
  seen: its conversion stopped at the container check ("NEO program/fixed graphics are smaller than the cartridge layout") and now
  converts, with zero interpreted opcodes on the main and sound CPUs. The reference engine indexes the fix region with 12-bit
  tile numbers and no mask, so a shorter region would be read past its end; the chip's unused address line repeats its contents,
  so tile n above 2048 is tile n - 2048. A ROM of 128 KiB or more is not touched: **every other game keeps the bytes of its
  container**, checked on nam1975 by an A/B conversion of the tree before and after (`tools/ab_conversion.py`: every generated and
  adapted source, the report and the evidence under `checks/` identical).
- **The native game is built with ThinLTO and a clang profile on Windows** with the portable llvm-mingw tools
  (`neogeo_optimization.py`, [NEOGEO.md](NEOGEO.md)): the same C is laid out and inlined differently, the outputs are identical
  (A/B on nam1975, puzzledp and mslug3), and the conversion takes about a minute longer.

**What moves.** The Neo Geo game stamp (`neogeo`, `neogeo_build`, `neogeo_conversion` (the probes now run side by side, schedule
only) and `neogeo_optimization` are converter modules of its stamp groups): a Neo Geo export of 1.6.4 is **converted in full once**, with no table entry. The CPS-1 game stamp moves too, because it
shares `neogeo_build`. The Neo Geo quick-state key moves as well (`neogeo_build` is edited and its fingerprint is hashed): from
1.6.5 no compatibility key is carried, so a quick state of 1.6.4 is refused cleanly ([GAME_STATES.md](GAME_STATES.md)); cartridge
saves are kept. The host stamp does not move for these two changes.

## Neo Geo: an attract route that reaches the BIOS restart (1.6.5)

Every Neo Geo cartridge except the NAM-1975 receipt (its historic routes are kept) now replays one more route, `long-attract`: attract
mode with no credit for at least 7,200 frames (`neogeo_validation.BIOS_RESTART_FRAMES`; the 9,000-frame routes that eleven sets already had
are kept, Metal Slug's 5,400 becomes 7,200). Without a credit the BIOS restarts after about 4,200 to 5,400 frames and runs a routine it copies
into work RAM (about 8.3 million instructions); the 3,600-frame attract route and a game started at about 2,400 never reached it, so six
exports measured on a longer route (Breakers Revenge, Rage of the Dragons, Matrimelee, Metal Slug 4, Prehistoric Isle 2, Strikers 1945
Plus) ran the same nine instruction sites of it, 2,319 instructions, in the counted interpreter. The conversion now observes those RAM
variants and translates them. Nothing in a saved state or a save changes.

**What moves.** The Neo Geo game stamp (`neogeo_validation` is a converter module of its stamp groups, and the route table is part of
what a conversion learns from): a Neo Geo export of 1.6.4 is **converted in full once**, with no table entry, as for the other 1.6.5
Neo Geo changes. The host stamp and the quick-state key do not move for this change. The report of a converted game lists one more route.
Cost: one more route replays on the reference and on the packed game; for most cartridges it is not longer than the `play` route, so a
conversion alone waits no longer, and a batch adds about a tenth of its replay work (not timed).

## X68000: DMA channel restart and moved-sprite redraw (1.6.5)

Two defects of the machine base (`tools/x68000_base74.py` adapts the pinned hissorii/px68k files at build time), both found while
checking the deferred px68k-libretro fixes of [UPSTREAMS.md](UPSTREAMS.md#deferred) against our own base.

- **DMA start on a busy channel.** A CCR START on a channel that was still active, or whose completion or error flags the game had
  not acknowledged, ended in an operation timing error (CER `0x02`, ERR and COC set, ACT cleared). It now restarts the channel with
  ACT, COC, BTC, NDT and ERR cleared, as MAME's HD63450 does. Count errors, software abort and the other error codes are unchanged.
  Games that re-arm their ADPCM channel early are the ones that notice (the libretro fork reports one such game).
  `tests/test_x68000_dmac.py` (with `tests/x68000_dmac_harness.c`) runs the adapted `dmac.c` on authored bus bytes and fails on the
  previous code.
- **Redraw lines of a moved sprite.** Lines of the picture are redrawn only when marked, and a write to a sprite register marked
  sixteen lines from `Y + BG_VLINE - 16 - v`. The line drawing selects a sprite row for the lines whose background row,
  `((line << s1) >> s2) - v`, lies in `[Y + BG_VLINE - 16, Y + BG_VLINE - 1]`: the marks sat two `v` lines too high or too low
  whenever the background's vertical start differs from the display's, and covered too few or too many lines when their line counts
  differ, so a part of a moved sprite stayed on screen. The marks now come from the same mapping.
  `tests/test_x68000_sprite_dirty.py` (with `tests/x68000_sprite_dirty_harness.c`) asks the real `BG_DrawLine` which lines show an
  authored sprite and checks that the register write marked them; the previous code left 2 of 16 lines unmarked at a 2-line start
  offset and 32 of 64 with a 256-line background on a 512-line display.

Both changes live in `tools/x68000_base74.py`, a game input of the X68000 (`stamp_inputs.py`) that `RR_X68K_STATE_ABI` also hashes: the
X68000 game stamp and the SDK stamp `x68_sdk` move, the quick states of earlier builds are refused (as at every release), and an
X68000 export is converted in full once, with no table entry. Only games that reach one of the two cases look different or behave differently. This
says nothing about hardware fidelity: neither case was compared with a real machine, and no gameplay validation changes.

## X68000: exact redraw marks for the background and the sprites (1.6.5)

The machine redraws a screen line only when it is marked, and the pinned base marked **every** line on any write to a background
map or pattern, and sixteen lines for any write to a sprite register, drawn or not. The marks now cover exactly the lines whose
picture can have changed, using the mapping of the line drawing ([the section on the DMA channel and the moved sprite](#x68000-dma-channel-restart-and-moved-sprite-redraw-165)):

- a write to a background **map entry** marks the lines of its tile row (8 or 16 lines, on the ring of 512 or 1024 lines, with the
  plane's scroll and the vertical offset of the background);
- a write to a **pattern** is noted by pattern number; the next line drawn (`rr_bg_resolve`, called by `WinDraw_DrawLine`) marks the
  lines of the sprites and map entries that use a noted pattern, once for all the patterns written since the last line;
- a write to a **sprite register** marks nothing for a sprite that is not drawn before and after (priority 0, or off screen);
- a change of the screen-resolution register of the background redraws everything, as the other registers that move the picture
  already did; a saved state resolves the noted patterns first, and a loaded state starts with none.

This is a speed change, not a behaviour change: the picture is meant to be the same as a full redraw. `tests/test_x68000_redraw_marks.py`
(with `tests/x68000_redraw_marks_harness.c`) draws random authored scenes line after line with the real `BG_DrawLine`, once redrawing
only the marked lines and once every line, with random map, pattern, sprite and scroll writes between the lines, and requires the two
to be identical after every line; it redraws 3 to 4 times fewer lines when few things change, and it catches two deliberately broken
variants of the marks. The same bookkeeping applies to the native player and to the reference, so their comparison is unchanged.
`tools/ab_conversion.py` on two games (R-Type, which scrolls, and Puyo Puyo, which hardly does), before and after, compared 314 files
each (CPU, memory, picture, PCM and clock traces, frame images, hashes, quick states, reports): the only differences are the three
adapted sources that changed (`bg.c`, `windraw_compose.c` and the generation record). No timing was taken here; the gain is the number of lines no longer redrawn and is
measured on a quiet machine. The only extra work is one call per drawn line (`rr_bg_resolve`, a test of one flag) and, after pattern
writes, one scan of the two maps (8,192 bytes) and of the 128 sprites per line drawn, instead of the redraw of every line.

The X68000 game stamp, `x68_sdk` and `RR_X68K_STATE_ABI` move (`tools/x68000_base74.py`, `native/x68000_machine/state/snapshot.c`).

## X68000: saved disks, the delivered file replayed, liveness (1.6.5)

Three changes toward the "supported" gates of [QUALIFICATION.md](QUALIFICATION.md):

- **Saved disks (G7).** `native/x68000_reference/payload.c` prepares the game's private data at every start. A writable disk is
  kept as the player left it (as before), but one that cannot be this disk (another size, a folder in its place, a missing
  file) and a host copy that was changed (playlist, IPL, font ROM) no longer stop the game: they are moved to
  `<name>.unusable-N` (never deleted) and written again from the executable. A link or a hard link in place of a file, and
  another running copy of the game, still refuse the start. `tests/test_x68000_payload.py` covers each case.
- **The delivered file replayed (G5).** Every X68000 conversion now compresses a copy of the final player as it is
  published and replays that compressed copy on the main route and on every exploration route against the same fresh reference
  (a difference refuses the export, as on Neo Geo and CPS-1); the F9 fresh-process and early-floppy-DMA checks run on that copy
  too. The report carries `native_validation.packed_reference_match` and `packed_candidate_sha256`. The conversion takes about
  30 to 40 seconds longer (the compressed replays run side by side within the game's share of the CPUs).
- **Liveness (G8).** The report records, per route, the number of different pictures, audio blocks, RAM states and program
  counters of the delivered file (`liveness`), and the conversion refuses a main route whose picture never changes.

`payload.c` and `retrorecomp/x68000_conversion.py` are game inputs of the X68000: the X68000 game stamp and `x68_sdk` move; nothing
the CPU executes changes. An export of 1.6.4 is converted in full once, as at every release.

## X68000: evidence tools for the saved disk and the play routes (1.6.5)

Two developer tools, not part of a conversion and not read by it, for the gates G7 and G8 of [QUALIFICATION.md](QUALIFICATION.md):
`tools/x68000_saves_check.py` converts a game, runs its player, runs it again and runs the player of a second conversion over the same
data folder, and checks that the disk the game wrote is kept each time; `tools/x68000_play_route.py` converts a game with an authored
input script as its main route (`tools/x68000_play_routes.py`, one exact disk set each, numbers only: Lemmings reaches its first
level) and keeps the last picture of the delivered file. `retrorecomp/x68000_conversion.py` names the check of an input script
(`valid_qualification_events`), the same rule as before. The X68000 game stamp moves with that module.

## X68000: a picture line made visible during its machine line (1.6.5)

The frame loop (`native/x68000_machine/machine.c`) chooses the picture line when a machine line begins, and a line outside the CRTC's
window gets the "no line" marker (`0xffffffff`). A game that reprograms the CRTC during that line (as it switches to its own screen mode, on two sets
of the test collection) can make the line visible before it is drawn; the line drawing then received the marker and indexed its line
tables 4 GiB out, which crashed the reference with a segmentation fault between frames 431 and 440 of Tetris v5 and of TF4G v0.3A09
(the 32-bit original wrapped to the byte before the table). A line without a chosen picture line now takes the one the CRTC gives at
that moment (`native/x68000_machine/glue_line.h`, `tests/test_x68000_picture_line.py`); a line chosen earlier is never changed, so
the games that ran before are drawn as they were. A game that never reaches this case sees nothing different.

Both sets now convert (0 interpreted opcodes on the three routes, the compressed copy replayed against the reference). The crash
appeared only on a first start: a saved `sram.dat` changed the start-up enough to avoid it, and a conversion always starts without one.
`glue_line.h` and `machine.c` are game files: the X68000 game stamp and `x68_sdk` move.

**A silent route is accepted (X68000 only).** A main route whose sound is all zero used to refuse the conversion ("did not produce
usable picture and PCM"). A few X68000 games play no sound there, some only through an external Roland MIDI module that will not be
modelled; such a route is now accepted, the conversion log says so and the report carries `native_validation.sound_heard: false`
(sound not validated). The picture is still required. The other machines keep their sound requirement.

**The sound is looked for on every route (X68000, 1.6.5).** Measured on the 84 reviewed mouse sets (`tools/x68000_mouse_survey.py`, the
reference only, no conversion), the 4,000-frame main route has no sound for 14 sets and a picture that stops changing for 15, because a game
that waits for a click or a key speaks and moves only on the route that gives it one: the 10,000-frame mouse route has no sound for 10 and
a frozen picture for 4 (other sets), and no set is frozen on both. The conversion therefore takes `native_validation.sound_heard` from all
the routes it replays and records the routes that had sound (`sound_routes`): Pensan CD, Boyon Boyon, Get Ready, Magritte, Oh! Hajiki! and
Tonkotsu Pro Roku Hachi Kei no longer count as silent on the standard scan level; eight sets stay silent on every route (Fire, Future Wars,
Ganbare! Paichan, Giga Fight 68K, Last Tempest A, Puzzle (1991), See Through v2, Uno). A quick scan, which replays the main route only, is
unchanged. No input is added to any route: the checks of the fresh reference, the compressed copy and the F9 continuation are as before.

The report's `packing.compared_on` now says when a packed copy was replayed (Neo Geo, CPS-1 and X68000:
`unpacked build executable and a packed copy replayed against the reference`); other machines keep `unpacked build
executable`. `retrorecomp/batch.py` and `retrorecomp/packing.py` change, which moves the game stamps of the machines that own them.

The time allowed to one UPX pass on Windows was a fixed 120 seconds. It stopped Dragon Warrior IV (a 512 KiB NES board, a large
executable) after every check had passed, while other conversions shared the CPUs. The limit now grows with the file on Windows and
Linux alike (`packing.upx_timeout`: 10 seconds per MB, never below 300); it only exists to stop a packer that hangs.

## Other machines whose game stamp moves in 1.6.5

Each of these changes a game input of its machine, so the game stamp moves and an export of 1.6.4 is converted again once, as at
every release. Quick states of 1.6.4 are refused cleanly ([GAME_STATES.md](GAME_STATES.md)); cartridge saves are kept.

- **Game Boy.** The one-by-one executor of writable-memory code (`native/gb_ram_helpers.h`) now runs the `CB` prefix (rotates,
  shifts, `BIT`, `RES`, `SET`, on a register or `(HL)`) with the interpreter's own helpers and cycle split (8, 12 for `BIT n,(HL)`,
  16 for the other `(HL)` forms). Wario Land II's interpreter sessions fall to zero; those instructions are counted as one-by-one
  executor instructions, not native code. `retrorecomp/gameboy.py` changes its scope text. Reviewed against the pinned interpreter;
  `tools/gameboy_ram_selftest.py` compares all 256 second bytes at four placements. The runtime's `gb_tick` also gets an inline
  ordinary case, described in [the next section](#game-boy-the-ordinary-case-of-gb_tick-runs-inline-in-the-runtime-165).
- **NES.** The MMC1 bank tables are rebuilt on a PPU A12 change only when that change can alter them
  ([UPSTREAMS.md](UPSTREAMS.md)); generated sources and evidence are identical. The quick-state key is now independent of the build
  folder (`RRNESST2`).
- **Super Nintendo.** The cartridge is checked once when it is bound instead of at every instruction, and code in work RAM is found
  through a direct table; outputs identical on Secret of Mana, Super Mario World, Chrono Trigger and Star Fox. The conversion log
  says when a run went past the 16,384-variant limit of RAM code observations (`retrorecomp/console16.py`, shared with the Mega
  Drive).
- **Neo Geo.** See its own section above (a 64 KiB fixed-graphics ROM repeated, and the clang profile on Windows).
- **Super Nintendo, identification.** A LoROM header whose map mode is `$32` with no chip (type 0, 1 or 2) is an ordinary
  LoROM (Duel/Test Drive II, the Popeye translation); every other `$32` header stays refused (`supernintendo.validate_cartridge`).
- **Super Nintendo, DSP-1 on HiROM.** A HiROM header (map mode `$31`) with chip type `$03` is recognised as a DSP-1 board like
  Super Mario Kart's (`retrorecomp/snes_chips.py`): seven cartridges of the test library, Lock On converted as proof.
- **CPS-1.** `IM 0` on the sound Z80 is counted (generator revision 8); independent 68000 vectors are replayed through the CPS-1
  generator and each route's liveness is recorded, a frozen route being refused.

## Game Boy: the ordinary case of gb_tick runs inline in the runtime (1.6.5)

`gb_tick` advances the clock of a Game Boy export after nearly every instruction and runs a large general sequence (double speed,
real-time clock, OAM DMA, serial, timer, PPU synchronisation, interrupts, audio). `native/gb_tick_fast.h`, included by the runtime file
`gbrt.c`, now runs the ordinary case in the caller, with the same effects in the same order, and calls the real `gb_tick` for every
other case before it changes anything: a ticking real-time clock (cartridge type `0x0F` or `0x10`), OAM DMA pending or active, a serial
transfer, a TIMA reload or a timer edge inside the cycles, double speed, and the runtime's test switches. It is a **speed change
only**: native code, CPU fidelity, hardware fidelity and gameplay validation are not touched, and physical latency stays unmeasured.

*What moves.* The Game Boy **game stamp** (a new game file, `native/gb_tick_fast.h`, and the runtime patch in
`retrorecomp/gameboy_runtime.py`; the Game Boy game stamp already moves in 1.6.5 for the `CB` prefix executor above). No host stamp, no
build stamp, no quick-state key, no change of what a conversion generates: the generated C sources are the same. An export of 1.6.4 is
converted again once, as at every release. The patch is four `replace_once` on the private runtime copy (the include, the macro off
around the definition of `gb_tick` and around `gb_handle_interrupts`, back on for `gb_run_cycles`, and the CGB HDMA stall kept as a
real call); it exists only when the runtime is built without its performance counters, which is the export build.

*Hot path: modified.* This is a per-tick change. For 87.0 percent of the 54.0 million calls of `gb_tick` counted on Super Mario Land
(3,600 frames, title screen without input) it replaces a call to the large general function by the ordinary case in the caller: a test
of conditions on fields `gb_tick` already reads, then the same effects. Where the calls are: 40 million happen while the CPU is halted
(the HALT loop of `gb_run_cycles` steps by 4 cycles while the PPU's next-event deadline is one dot, in mode 3), the others come from the
timed jumps, calls, returns, stack and bus accesses of `gbrt.c`; 1.3 percent are handed to the real `gb_tick` (a timer edge) and 11.7
percent are direct calls of the generated bodies, which keep calling the real function (forcing the inline there would add about 400
bytes at each of thousands of call sites per source file; the compiler does not inline it on its own). The code of `gbrt.c` grows by about
44 KB (41,728 to 85,810 bytes); the generated sources do not change. **The speed gain is not measured**: speed is measured on a quiet PC,
by the lead, with Arthur's agreement; nothing here is a timing.

*Proof.* `tools/gameboy_tick_selftest.py` (with `native/gb_tick_checks.c`) applies 48 random operation streams of 6,000 operations (ticks
of 1 to 456 cycles, writes to the timer, LCD, interrupt, DMA, serial and sound registers, reads, IME changes) to two contexts, one ticking
through the real `gb_tick` and the other through the inline path, and compares them field by field: 309,660 comparisons, the whole context,
the five memory blocks, the PPU, the audio output and registers `FF10`-`FF4B`, plus six cases that must take the real path. Five mutations of
the inline path are caught. Because the runtime itself now uses the inline path, an independent check was added: `tools/ab_conversion.py`
(reference `af885a0` against the branch) on Tetris, Super Mario Land and Wario Land II gives kept build folders that differ only in
`runtime/include/gb_tick_fast.h` (new) and `runtime/src/gbrt.c`, and reports with identical cycles, interpreter and one-by-one counts and CPU
comparison step counts; and the final executables of Tetris and Super Mario Land, run for 3,600 frames on three input scripts with
`--dump-state`, write state files identical byte for byte (registers, cycles, WRAM, HRAM, PPU mode, RTC).

## Game Boy: a frame lasts 70,224 cycles with the LCD off (1.6.5)

With the LCD off the Game Boy has no vblank, and the runtime completed a frame only at vblank: a game that keeps the screen off
while it waits for a key never completed another frame. In the windowed export the loop already ran in slices of 70,224 cycles and
showed the last picture, but the frame counter, the clock of frame-anchored input scripts and the limit of headless runs advance only at a
completed frame, so every headless probe and every scripted route stopped there. The Ren & Stimpy Show: Veediots! did so at the end
of frame 215 of the probe (screen off at cycle 16,201,199, never on again, 30 million instructions without a frame).
`gb_add_cycles` (and its copy in `native/gb_tick_fast.h`) now ends the frame when the frame's cycles reach 70,224 while the LCD is
off; the host shows the picture the PPU kept. This is a **change of the frame count, not of the emulation**.

*What moves.* The Game Boy **game stamp** only (it already moves in 1.6.5): `retrorecomp/gameboy_runtime.py` (one more
`replace_once` on `gbrt.c`) and `native/gb_tick_fast.h`. No host or build stamp, no quick-state key. An export of 1.6.4 is converted
again once, as at every release; a quick state can now be taken during an LCD-off span (the frame is complete there).

*What it changes in a conversion.* The LCD-off span of the boot (several frames, 15 more in Tetris and 39 more in Super Mario Land over the
first 3,600) used to count as one frame; it now counts as the frames it lasts. The probes of N frames therefore cover fewer cycles
at the start, frame-anchored scripts meet other guest cycles, and the counts, the observed entries and the step counts of the reports move
a little (Super Mario Land: 8,232 translated functions before, 8,211 after; nothing becomes interpreted). Existing observations stay valid.
Outside the boot, a frame boundary moves only when the LCD is off at the instant the frame's cycles reach 70,224 (a span that starts
at line n of a frame and lasts more than about 65,664 - 456 n cycles): the effect is one more host frame showing the same picture,
never a change of the emulated state.

*Hot path: modified (one comparison).* The test is made only while the LCD is off, in the function that adds the cycles of a tick,
and in its inline copy. Not timed.

*Proof.* `tools/gameboy_tick_selftest.py` checks that the real tick and the inline tick end the frame at the same cycle, for four tick
sizes, and uses the frame reset of the host loop in its random streams (a mutation of the threshold is caught). At the same total of
cycles the full `--dump-state` of Tetris (3,600 frames before, 3,615 after) and of Super Mario Land (3,600 and 3,639) is identical without
`completed_frames`. Veediots now converts alone in 105 s with zero interpreter cycles and matching CPU comparisons (it stopped
at the first input probe before); Tetris, Super Mario Land and Wario Land II convert on both sides with matching CPU comparisons and
unchanged interpreter figures. Spiritual Warfare (an unlicensed cartridge whose header says ROM only, 32 KiB, for 256 KiB) now also
completes its probes, with 1,029,772 interpreter cycles at four sites and the program running garbage: it is not a game that works,
and a refusal for an inconsistent header would be a separate decision.

## Exports of 1.6.3 in 1.6.4

1.6.4 is a structural release with a full reconversion of every console (decision of the maintainer, 29 October 2026). It
moves the game stamp of all nine consoles and the host stamp of eight (every console but the X68000), and the build stamp
of none (the packer is still the UPX 5.3.0 of 1.6.2). Every export links a new SDL, and six of the nine consoles also change
in their own way (a conversion, a counter, a saved state, a path; the Mega Drive, the Super Nintendo and the Neo Geo change only
through SDL and the registry), so the decision is to reconvert everything, and the written release procedure
([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#legacy_game_stamps): list no console whose game the release really changes)
leaves `LEGACY_GAME_STAMPS` **empty**: the entries of 1.6.2 are removed (the previous release only) and none of 1.6.3 is
added. **Every export of 1.6.3 is converted in full once**, on all nine consoles, Windows and Linux; no export is
upgraded, so no report carries an `upgrade` block with `from_release` = `1.6.3`. A ROM the shared base knows starts from its
qualified paths with the quick check, not from scratch (the base note below). The later sections of this file list each
change of the release; what follows is what each console's stamps do.

| Console | Game stamp moves because (besides SDL and the registry, below the table) | Host stamp | 1.6.3 export in 1.6.4 |
| --- | --- | --- | --- |
| Master System | the "functions" engine samples the interrupt line at one boundary and accepts it at the next, HALT and a RET that unwinds the generated frames ([lot F](#master-system-and-game-gear-the-functions-engine-164-lot-f)): `core` (`patched_generator_source`, `prepare_functions_irq`); the default banked engine generates the same sources | moves | **converted in full once**; no entry |
| Game Gear | the same | moves | converted in full once |
| Game Boy | WRAM and HRAM instructions run one at a time by a counted executor, and counted ([below](#game-boy-exports-in-164-writable-memory-code)): `native/gb_ram_helpers.h`, `native/gb_ram_checks.c`, `gameboy`, `gameboy_runtime` | moves | converted in full once |
| NES | quick-state writer: header and members zeroed and copied ([lot B](#quick-states-of-the-nes-and-cps-1-164-lot-b)): `native/nes_machine_state.inc`, `native/nes_mapper_state.inc`, `native/nes_machine_checks.c` | moves | converted in full once; its states of 1.6.3 are refused |
| Mega Drive | nothing of its own: `systems/console16` (the shared profile module of the Mega Drive and the Super Nintendo) | moves | converted in full once |
| Super Nintendo | nothing of its own: `systems/console16` | moves | converted in full once |
| Neo Geo | `systems/neogeo`, and `neogeo_build` (this rollover's key line) | moves | converted in full once |
| CPS-1 | code run from graphics RAM guarded natively ([below](#cps-1-code-run-from-graphics-ram-is-guarded-natively-164-lot-h), `GENERATOR_REVISION` 7), quick-state writer ([lot B](#quick-states-of-the-nes-and-cps-1-164-lot-b), magic `CPS1S002`): `native/cps1_machine.c`, `cps1_native.c/.h`, `cps1_codegen`, `cps1_build`, `cps1_conversion`, `cps1_knowledge` | moves | converted in full once; its states of 1.6.3 are refused |
| Sharp X68000 | the payload opens extended-length paths on Windows ([lot C](#x68000-payload-paths-deeper-than-260-characters-164-lot-c)): `native/x68000_reference/payload.c`; `systems/x68000` (the shape of its paths) | unchanged | converted in full once; no entry (its request carries `x68_sdk`) |

Two changes move every game stamp, whatever the console: the SDL pin ([lot E](#sdl-23210-a-game-input-of-every-console-164-lot-e):
`core.SDL_REV`, a game input of all nine consoles, linked statically into every export) and the profile registry
([lot A](#the-profile-registry-stamps-of-the-nine-games-and-eight-hosts-move-164-lot-a): `path_profiles`, `hostkit`, `systems`,
`systems.specs` and the profile modules). Neither changes what a game does; both change the stamp, and the decision above
means they need no further argument. The tests that pin these refactors against values taken before they existed are
`tests/test_path_tables_snapshot.py`, `test_registration_surface.py`, `test_conversion_common.py`, `test_conversion_gates.py`
and `test_stamp_inputs.py`.

**The base is intact.** Of the 23 upstreams that `retrorecomp/upstreams.py` declares (three of them have no pin of their own;
each pin was read with `upstreams.pin_of` in the archive of `v1.6.3` and in this tree), exactly one pin moved: SDL
(`core.SDL_REV`, release 2.32.8 to 2.32.10). The engine revisions of the Master
System and Game Gear, Game Boy, NES, Neo Geo (Geolith and Lithogen), CPS-1 (ymfm and the MAME revision of the catalogue), the
Mega Drive and Super Nintendo repositories (`console16.REPOSITORIES`) and the X68000 pins are the same values in both
trees. The base of qualified paths is keyed by those recompiler and engine revisions (`knowledge_build.engines()` for the
Master System, Game Gear, Game Boy, NES, Mega Drive and Super Nintendo), not by SDL, so it stays valid: a ROM the shared base
knows starts from its qualified paths when its export of 1.6.3 is converted in full, with the quick check. The CPS-1 section
cores also hash `GENERATOR_REVISION` and the native files that guard and run a RAM path, which this release changes (revision
7): a CPS-1 path qualified by the code of 1.6.3 would wait for it, and the shipped snapshot holds no qualified CPS-1 path, so
nothing is lost.

**The stamps of 1.6.3, recorded as evidence and not listed.** The `v1.6.3` tag (commit `bb2aa95`) exported with an archive of
the tag into an empty folder, then `compilation_inputs.role_stamps(system)` for each console, under Python 3.14.5 on the
Windows PC and under Python 3.13.5 (the build virtual environment) in a new temporary folder on the Linux build host,
deleted afterwards. Code is fingerprinted as bytecode, so the Windows converter of 1.6.3 (Python 3.14) and the Linux one
(Python 3.13) stamp differently. `tests/test_legacy_compat.py` pins all of them, unlisted
([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#release-163-entries-29-october-2026-windows-and-linux)).

| Console | Game stamp of 1.6.3, Windows (Python 3.14) | Game stamp of 1.6.3, Linux (Python 3.13) |
| --- | --- | --- |
| Master System | `63e727d52b1b7af0ce1c6544bac62c1362e73132efdad799347c49bf07ed7257` | `8efac42db9fee6c3094e9cafc007c87ed7387e736fc4405d7d422e03472a702a` |
| Game Gear | `67487dfd4d724db4f7be9052fd57cafea77f810a9b5a7cf74d7cfdb121b74a4f` | `d5fa178b743638d1e49ed06ad9fbda597dfeb53664decb4f0076acd1a5949561` |
| Game Boy | `20d990464af935b2ea058208029ec0a7f0fdadb955e46275f4ad6dcd33749b28` | `e2a69eded159057ecfeade0d66091bb9248e9ba9a3bc63233b5bfcbcfffb344e` |
| NES | `21c183e6df50d5048ada8f5dfb3596633f4bffcdc6d1fc088d21a5e96a33104c` | `08df3e3cb280c7728d0a9af21d8c3fdf9b527dd2c5bf3b60e13fd80c4d46d3ff` |
| Mega Drive | `c8c3a33789a92f80d41df0c43e546c581e94884055bb07a31ef04ebae583ba9d` | `d4a0f9676a97e96051cc531e95742e19d4311d137127fda088f9476b5282a3b3` |
| Super Nintendo | `6825afd89679334b3aee85318a31b1ad2ad381654be1d7d6951552cedb5950ff` | `d7987cb30048be3cea669466ebfd9f1bbb96cfb8b949afb98fd3c8e78535e586` |
| Neo Geo | `4637299cdbf17baea508a7046e4576ca59acc8dd994c2a51c70558adfb76b360` | `107d2a2b96b83614fec0b941555a280036e08edf32d62145b916f0d8331cc0ba` |
| CPS-1 | `cdfe0c2944e41813548f3847e1742d7d9f395463f7966dddd6ea573518628e43` | `490167ff02e59d7a17f19e863e527589f1d5dbe1a995fb8d016338c1a05148c4` |
| Sharp X68000 | `a58d873ff98ca9a16f973a2621ffa672a1f0dc464f7694ff36f7ebbf4645e84e` | `d85456f6c6e16301deb53ab14699812dae766470b4b88d35192f5e05fd5f4524` |

| Console | Host stamp of 1.6.3, Windows | Host stamp of 1.6.3, Linux |
| --- | --- | --- |
| Master System | `53d443aa47fe5fe20d75f37d8bfeb06bc992af3e938555fbb27c0251180d9f0a` | `81b76644c91e662d3e03c98735e8b99942043fd0be6319aec33e3cc52cd5be6e` |
| Game Gear | `5b99931159ed13039b62ee63a4aa9684eb8998856e8dac85664ef5d74c9c8458` | `a499021dcbad428be4ce18815449a40d782bed6e5fd438dcf79a382d38c094d2` |
| Game Boy | `1efc1dbb44cfb596d6fcc823ba67862594dd552e1a8f52d825c9e4b5c26b1f48` | `56862d16ce57f92894964b8e30ec6b1acd99668b559009bc2df170a78b4ee993` |
| NES | `a722d03bfb4d5059045447f7cd27e93782c704bc76f648f3bf74286f2ff1387a` | `98b830d30a4ee79da2c35f7215346084c140b8dbf8149fe758dc1789736db842` |
| Mega Drive | `c398363d34c83ec7821abdafe71f4e3898d09292c6a7c099e0dacfeae0af980e` | `6dff1958e9e78d15f11326c72d339e214d448af4b655dae68dde830e591a0302` |
| Super Nintendo | `98a5ef5dbefc559d9e1f4df429bde71618db12af86f2644d0a4205f201f85733` | `26f8011512446037c117b68cb683c60778afd91e358a15f65aa218022afe69a2` |
| Neo Geo | `d83c902b3ebda289e120f4fcbdb0cfe29f2d6c42a0e394a3ac802797d7c6973c` | `29890feb1e893aa4cd2b8a36dd967485bd9dc8db8ed0eb0015a7644da04dbeaf` |
| CPS-1 | `7e3b53b34bd2508f49cde41ad692d743c3d14e5f1c6a47b4c8755466503872d0` | `4d5e0e263913a4d6c78ad8b9d191ec4f1f8811ef144bfc2131492a29d2d0c4a3` |
| Sharp X68000 | `b1e94a492351899e885aded7e77486a607c8518ed8e1aa86709753f5efbf7640` | `e4b9192c471a04b521644f79d30a3667b6c00ff379b32016cacce63735d4728c` |

| Console | Build stamp of 1.6.3, Windows | Build stamp of 1.6.3, Linux |
| --- | --- | --- |
| Master System | `61b3ff1284fcf75b79309f140d5c68ed04fb0cc038c443a9176606d9bfd96b9e` | `844581a4aee67b01c2b64819e7d4328c6a0eb920ff65fc67f459734df36abf40` |
| Game Gear | `99adc3982e7e8255bc3ebcb7fad103a94814dd218893a78549f2c5e0a72d5fbb` | `35fd32cf151d92623789c9993895f73d7a6dc706d7a55629abcfe7748750347e` |
| Game Boy | `a95276b71c11e78625c3d29ba0d915c131f6c40e5da9d093093212e6acf21e78` | `fdf983cbb2cf9f658ca6b4ae0e877ac67fa8b594b8a01141bc40744fbc971b64` |
| NES | `daf686c3aacfb39673019978ab0aac5b00fe46e580b55e532254bb2ddde5cd3d` | `0924450ada99b439fc7bd374df29b679b48366e88234b31b7f02b2d19132de8e` |
| Mega Drive | `04d0d103866e5c07fe1867b51182039c13eec54918ad57397effdf9e9cfae061` | `a2e3f1d84f568da91d943cd6a8c66a847c2eb9196214d0a6374668f8669c5920` |
| Super Nintendo | `b2fec61a9627103484912da9782e7371ba4987a726b6dcd173da2ceff6fc9f2f` | `a801be2aa12c5efc034a1211ed47e81e0d3821a8ec47859e42a7c19ff116e255` |
| Neo Geo | `6c23ad79d979182db3455217c001ee583fd0a6cb4df5bc52deabb0ac76b9103c` | `735812b24a5d4b06f7ca72447e8b7b158a7b83c37a81813d25c8d2b24164e693` |
| CPS-1 | `5022eedca09f8a0fffd8cfae1bd0e6c823f277ffe0dd9f3f2f5c27c3e3247a63` | `1710a97d399b07eb651c4982cb4a03ec500d401706920576402ab9b08ff2516e` |
| Sharp X68000 | `e84c6e39d05d7f47ac5e0a51a2b676351cef673e855923b3bbb276597279a255` | `47712564c3a7d72667d0a764f2186a4d23ea492100e73cedd4cc44cc9763c098` |

*Compared with the tree of this release (Windows, Python 3.14, the commit of this rollover): the nine game stamps differ from those
above, eight host stamps differ (the X68000 host stamp is the same), no build stamp differs. The stamps of the tree move again
with every later edit of a hashed file; the release procedure recomputes them for the next release from the tag of this one.*
**Not proved here:** unlike the stamps of 1.6.2, these were not compared with the stamps that the published converters of 1.6.3
give with their own `_compilation-inputs` (the assets of the v1.6.3 release were not downloaded for this record). Nothing
depends on it: no entry is listed, so no receipt can be accepted on the strength of a stamp in this table, and a receipt of
1.6.3 is converted in full whatever it carries. No game was converted for these records and the claim of "converted in
full" rests on the list of changes above, not on a receipt per console.

**Quick states** ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-163)), a separate question from the export
upgrade; the key of each console, computed from the `v1.6.3` tag and from this tree on Windows with the console's own
`write_config` or `state_config`:

| Console | Key of 1.6.3 to 1.6.4 | States of 1.6.3 in 1.6.4 |
| --- | --- | --- |
| Mega Drive | unchanged | load: the key is the build's own, nothing to list |
| Super Nintendo | unchanged | load, as the Mega Drive |
| Neo Geo | moves, only because this rollover edits `neogeo_build` (its fingerprint is hashed); the state files are byte for byte those of 1.6.3 | load (Windows): the 1.6.3 key is the compatibility key `neogeo_build.STATE_ABI_163` |
| CPS-1 | moves: the state changed (`CPS1S002`, [lot B](#quick-states-of-the-nes-and-cps-1-164-lot-b)) | **refused** |
| NES | moves: the state writer changed ([lot B](#quick-states-of-the-nes-and-cps-1-164-lot-b)) | **refused** (no compatibility mechanism) |
| Master System, Game Gear, Game Boy | no key of this kind | not run; none of the changes of this release touches a saved state |
| X68000 | by design a key of the build | not guaranteed; see GAME_STATES.md |

The 1.6.2 keys are removed from `console16_state`, `neogeo_build` and `cps1_build` (the previous release only).
`cps1_build.py` is a pinned CPS-1 generator source and this rollover edits it: `cps1_knowledge.GENERATOR_REVISION` stays 7 (the
revision of lot H, not shipped yet), `tests/cps1_generator_pins.json` follows, and the comment of the revision says so.

## SDL 2.32.10 (a game input of every console, 1.6.4, lot E)

1.6.4 moves SDL2 from release 2.32.8 to release 2.32.10 (`core.SDL_REV`, commit `5d24957`; 36 upstream commits: Nintendo
Switch Pro stick calibration and sensor coefficients, Pipewire device default formats and ALSA default-device information
on Linux, build and platform fixes). SDL is linked statically into every export and the pin is read by `retrorecomp.core`,
a game-role input of all nine consoles, so the game stamp (and the engine stamp) of every console moves; host and build
stamps do not. An export of 1.6.3 is therefore never current, and with the decision of the release (no legacy stamp) it is
converted in full. The base of qualified paths is keyed by the pinned upstream recompiler revisions, not by SDL, so it stays
valid. The SDL static libraries of an existing workspace (`.deps/SDL/install`, `install-llvm`) are rebuilt from the new tag
on the first conversion. Checked here: the ROM-free self-tests of the shared host and a Master System and a Mega Drive
conversion on Windows. This says nothing about audio or controller behaviour on physical devices (hardware fidelity and
latency stay unmeasured).

## Master System and Game Gear: the functions engine (1.6.4, lot F)

Master System and Game Gear exports made with the "functions" engine are reconverted. The engine now samples the interrupt line
at one instruction boundary and accepts it at the next (like the reference CPU and the banked engine), HALT pushes the next
address and ends when the handler dropped its frame, and a RET that unwinds the generated frames continues. The default banked
engine generates the same sources. These are CPU-fidelity corrections of our own patch on the pinned generator and runner
(`core.patched_generator_source`, `core.prepare_functions_irq`, [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164));
the pin does not move. Alex Kidd in Miracle World, Factory Panic and seven more games now pass the comparison with the reference CPU
with that engine; they converted with the banked engine before. That is an agreement with the project's own reference on the tested
routes, not a statement about hardware fidelity, gameplay or physical latency, and the share of native code changes only where a game
stopped at the first affected frame and goes on now. Interpreter fallback stays counted per CPU. The game stamp of all nine consoles
moves with `core`; the host stamp moves with the registry. Their quick states have no key of this kind, and none of these
changes adds a field to a saved state.

## The profile registry: stamps of the nine games and eight hosts move (1.6.4, lot A)

A tenth machine no longer moves the stamp of any existing console ([NEW_MACHINE.md](NEW_MACHINE.md): the acceptance dry run of
29 October 2026, an Atari ST added on a throwaway branch, 41 files and 70 places on 1.6.3 down to 26 and 30, no existing stamp
moved). To get there, `path_profiles.PROFILES` is built from each profile's `PathSpec.shapes`, `hostkit.ADAPTERS` from
`host_adapter`, and the manifest of `stamp_inputs.py` takes the CPU families and the shared groups (`SystemProfile.stamp_groups`)
from the profiles. Those edits touch stamped files (`path_profiles`, `hostkit`, `systems`, `systems.specs` and the profile
modules), so the **game stamp of all nine consoles and the host stamp of eight move once** between 1.6.3 and 1.6.4; the build
stamps and the manifest (names and roles of the inputs of the nine consoles) do not. It changes no game and no host behaviour
(`std_baseline` equals the one of 1.6.3 except for the values that hold a stamp). Learned paths, receipts' schema (3) and the
quick-state keys do not move for this reason.

## Quick states of the NES and CPS-1 (1.6.4, lot B)

Both writers now write only defined bytes ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-163)). **NES:** the header's two
padding bytes are zeroed explicitly and the machine members (processor, machine, cartridge, video, light gun) are copied byte for
byte into a zeroed record (`native/nes_machine_state.inc`; the VRC7 block in `native/nes_mapper_state.inc`); the structures nested
inside those members are still copied as they are, with the padding they have (zero in practice, not by guarantee). The file layout
and size are the same, and the file begins with the same magic. `RR_NES_STATE_ABI` hashes these files, so it moves, and the NES has no
compatibility key mechanism (the loader compares the header's `abi` field with the build's own): a NES state of 1.6.3 is refused
cleanly. **CPS-1:** magic `CPS1S001` becomes `CPS1S002`; the Z80 registers (34 bytes), the sound-latch queue and the OKI voices are
written field by field in little-endian order, and the 68000 block ends at its last integer field (`mmu_sr`) instead of at the first
pointer; the size of a state changes. The key moves with the files and a state of 1.6.3 is refused cleanly. Neither change touches
what a game does: it is about the bytes of the saved file (two saves of one moment are identical), not about CPU fidelity or
hardware fidelity. Checked by the authors of the change: `native/nes_machine_checks.c` (header padding zero, a second save over another
buffer identical) and `tools/nes_state_selftest.py` (two saves of one run identical) for the NES. The CPS-1 writer has no test of its
own in the suite beyond the magic pinned by `tests/test_legacy_compat.py`, and no state was resumed across releases for either console.

## X68000: payload paths deeper than 260 characters (1.6.4, lot C)

`native/x68000_reference/payload.c` prepares a game's private data in its folder. On Windows its wide-character calls stopped at
`MAX_PATH` (260 characters, 248 for a folder), so a game placed deep in a folder tree could not prepare its payload. Every path
now goes through `GetFullPathNameW` (".", "..", "/", trailing dots and spaces are resolved as Win32 does for the short form) and
only the operating-system calls see the extended-length prefixed copy (`\\?\` or `\\?\UNC\`) of a path of 240 characters or more,
including a short relative path that grows past `MAX_PATH` once made absolute; every path kept or returned stays as given, and a
short path is used as it is. `tests/test_x68000_payload.py` (with `tests/x68000_payload_harness.c`) builds the payload code and
fails on the previous code. The X68000 **game stamp** moves (`payload.c` is a game file, `systems/x68000` too) and with it the SDK
stamp `x68_sdk` that its request carries, so a receipt of 1.6.3 is never recognised, with or without a table; the host and build
stamps do not move. Nothing the CPU executes changes: this is a Windows file-system fix.

## Game Boy exports in 1.6.4 (writable-memory code)

The Game Boy runtime now executes the WRAM/HRAM instructions that the pinned RAM stub does not cover **one instruction at a time, from
their live bytes, with a counted executor** (`native/gb_ram_helpers.h`, `rr_gb_try_ram_instruction`;
[UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164)). That is not native code and not ahead-of-time translation: it is
a per-opcode switch, cheaper than an interpreter session. What changes for a game that runs such code (Donkey Kong Land: a trampoline
block copied from the cartridge into WRAM, operands patched at run time) is that the ROM routine the trampoline jumps to runs as native
code again instead of staying inside an interpreter session. What a conversion generates is unchanged (the generated C files are the
same); the adapted runtime header, the dispatch of `game.c` and three context counters change.

*Counted, apart from the interpreter.* The executor, the upstream RAM stub and the upstream stub for code run from 0xFF00-0xFF7F (the last
two were never counted) each count their instructions and guest cycles in every probe: `final_checks` and `history` carry
`ram_stub_instructions`, `ram_stub_cycles`, `ram_single_step_instructions`, `ram_single_step_cycles`, `highmem_stub_instructions`,
`highmem_stub_cycles`; the schema-2 report shows them as `cpus[].scenarios[].ram_single_step`, with
`ram_single_step_present`. While they are not zero the report's `native_code.zero_fallback_on_tested_scenarios` is false and its claim
reads "native ROM code on the tested scenarios; some WRAM/HRAM and 0xFF00-0xFF7F instructions run one at a time by counted executors (not native code)"; the
window appends "N RAM instructions executed one by one (not native)" in the eight languages, and the library marks the game as one with
fallback. The interpreter figures keep their meaning (sessions, instructions, cycles of the interpreter). The counts cover the generated
dispatch only: stubs the pinned interpreter calls inside a session are part of that session (its instruction and cycle counts). The
guarded multi-instruction helpers (named routines checked by a live signature) and the upstream HRAM stub (the OAM-DMA wait routine matched
by its bytes) are not counted, as before. A report of 1.6.3 has no such counts: the flag reads
"not measured", never "zero".

*Stamps* (`compilation_inputs.role_stamps('gb')`, Python 3.14, from the tree of the tag `v1.6.3` and from this tree; to be recomputed at the
release): this change moves the Game Boy game stamp only; its host and build stamps and the other eight consoles' stamps are untouched by it
(they move for other reasons of the release: [Exports of 1.6.3 in 1.6.4](#exports-of-163-in-164)). Learned
paths do not move, and no quick-state key exists for the Game Boy (the counters are host-only context fields, outside every saved state).

An export of 1.6.3 is therefore rebuilt from its learned paths and rechecked on the quick routes. Donkey Kong Land goes, in the
6,000-frame probes, from 3,160,836 interpreter cycles in the boot probe and 141,688 in the varied probe to zero interpreter cycles in all
four, and its deep CPU comparisons still match; the RAM instructions run one at a time are reported beside that figure (see the
conversion report of a game of this release). That is native ROM code plus counted one-by-one execution on the tested scenarios, a
CPU-fidelity agreement with the project's own reference on 240 frames per scenario, and nothing about hardware fidelity, gameplay or
latency.

## CPS-1: code run from graphics RAM is guarded natively (1.6.4, lot H)

`native/cps1_machine.c`, `native/cps1_native.c`, `native/cps1_native.h`, `retrorecomp/cps1_codegen.py`,
`retrorecomp/cps1_build.py` and `retrorecomp/cps1_conversion.py` change, so the CPS-1 game stamp moves (every CPS-1
file is a game file; the host stamp is not touched). Street Fighter II': Champion Edition ran a short routine copied into
graphics RAM and interpreted it (75,546 instructions in the play route); the 68000 native code now also looks up and
guards instructions at 0x900000 to 0x92FFFF, from the library's private `m68k_gfx` observations (learned in pass 1 of the
conversion, translated in pass 2, each instruction still checked against its live words). For every other CPS-1 set
the generated code differs only by one added lookup function (`cps1_step_index.c`) and the native analysis reports
`guarded_gfx_variants` = 0; their traces and behaviour are the same as before (A/B on real conversions). A CPS-1 export of
1.6.3 is not byte-identical to a 1.6.4 conversion, so the legacy list decision of the release applies to it as to the
other consoles. `cps1_knowledge.GENERATOR_REVISION` goes from 6 to 7: no CPS-1 path was qualified yet, so nothing is lost.
`retrorecomp/m68000.py` is not touched: the Mega Drive, Neo Geo and X68000 generated code does not move.

## Neo Geo: a coloured edge mask is painted black on screen (1.6.4, lot NGE)

A Neo Geo export shows all 320 LSPC columns. The BIOS draws a solid fix tile (0x0020) in fix columns 0 and 39 as an overscan
mask: most games keep it black, but a few (2020 Super Baseball, Joy Joy Kid, Puzzle Bobble 2, Ghostlop) leave it grey or
orange and the picture shows a bright 8-pixel band. The picture stays 320 columns wide and is never cropped; what changes is
only what is displayed. The engine's fix-layer routines (`neogeo_build`, the patched `geo_lspc.c`) note the two edge tiles of
each visible tile row, `native/neogeo_fixmask.h` decides per side and per frame (at least 26 of the 28 rows hold one solid tile
of one palette, the colour is not near black, and it differs visibly from the neighbouring picture column), a latch turns the
band on after 30 matching frames and off after 120 others, and the host kit's Neo Geo view (`rrhk_ng.c`, `.pixels`) paints a
latched band black in a copy. `rr16_pixels()` is not touched, so the validation hashes, the reference comparisons and the image
dump read the same pixels as before. There is no per-game list and nothing enters a saved state. Files: the game side
(`native/neogeo_fixmask.h`, `native/neogeo_fixmask_checks.c`, `native/neogeo_main.c`, `retrorecomp/neogeo_build`) moves the Neo
Geo game stamp, the host side (`native/hostkit/adapters/rrhk_ng.c`) its host stamp; both already move in this release. The Neo
Geo quick-state key moves again only because `neogeo_build` is hashed; the state files are unchanged and the 1.6.3
compatibility key above still applies. Verified with a ROM-free check of the detector and the latch
(`tools/neogeo_fixmask_selftest.py`) and with real conversions; the rule is a display heuristic judged on the maintainer's
dumps, not a hardware fact.

