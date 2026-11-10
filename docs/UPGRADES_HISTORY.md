# Upgrading exports: history of releases 1.6.9, 1.6.7 and 1.6.6

The per-release detail of releases 1.6.9, 1.6.7 and 1.6.6, moved from [UPGRADES.md](UPGRADES.md) so that each page stays readable (the text and the
anchors of every section are unchanged). The current release, the one before it, the sections of 1.7.0 and 1.6.8, the rules and the classification of host and
game inputs stay in [UPGRADES.md](UPGRADES.md); the sections of 1.6.5 and before are in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md).

## Exports of 1.6.8 in 1.6.9

1.6.9 is the release after 1.6.8 (published on 4 November 2026). This section is the index of its changes, one line per section
below, with the stamps that section says move. Each section computed its stamps for its own change alone; the totals are under the table.

| Change | Game stamps that move | Host and build stamps | Quick states |
| --- | --- | --- | --- |
| [Master System and Game Gear: two defects of the "functions" engine](#master-system-and-game-gear-two-defects-of-the-functions-engine-found-by-the-panel-169) and [the evidence of the panel](#master-system-and-game-gear-the-report-names-the-devices-and-the-routes-that-stall-and-the-evidence-of-the-panel-169) | Master System, Game Gear | none | no key (they have none) |
| [Capcom CPS-2 opens as an experimental machine](#capcom-cps-2-opens-as-an-experimental-machine-169) | CPS-1 (the board shared with the CPS-2) | host stamp of all nine consoles (the notices) | **the CPS-1 key moves**: CPS-1 and CPS-1.5 states of 1.6.8 refused |
| [Capcom CPS-1.5 leaves the experimental tier](#capcom-cps-15-leaves-the-experimental-tier-169) | CPS-1 (the catalogue) | none | no key moves |
| [An account upload carries only the paths the local base lacks](#an-account-upload-carries-only-the-paths-the-local-base-lacks-169) | none (interface modules) | none | no key moves |
| [Game Boy: the one-by-one line names the 0xFF00-0xFF7F range](#game-boy-the-one-by-one-line-names-the-0xff00-0xff7f-range-169) | Game Boy | none | no key (the Game Boy has none) |
| [Sharp X68000: the profile is supported](#sharp-x68000-the-profile-is-supported-169) and [the paths travel, both ways](#sharp-x68000-the-paths-travel-both-ways-169) | all nine consoles (the `*` group of `stamp_inputs`) | host stamp of every console (the notices) | no key moves |
| [Host kit: nothing blocks a third or fourth player](#host-kit-nothing-blocks-a-third-or-fourth-player-169) | none | **host stamp of all nine consoles** | no key moves (`game_options.h` and the catalogue untouched) |
| [Computers: the keyboard goes to the game or to the computer, per game, from F2](#computers-the-keyboard-goes-to-the-game-or-to-the-computer-per-game-from-f2-169) | none | X68000 host | no key moves |
| [Sharp X68000: the generator of native code and the computer part of the adapter are shared](#sharp-x68000-the-generator-of-native-code-and-the-computer-part-of-the-adapter-are-shared-169) | all nine consoles (`systems/specs.py`, `systems/__init__.py`) | X68000 host | no key moves |
| [PC Engine: an experimental machine](#pc-engine-an-experimental-machine-169) | all nine consoles (the profile modules); the PC Engine's own stamps are new | host stamp of all nine consoles (the notices) | the PC Engine's key is new |

Taken together (`compilation_inputs.role_stamps` of the eleven consoles, the tree of `v1.6.8` against the tree of this release, computed on
5 November 2026): **the game stamp and the host stamp of the nine consoles of 1.6.8 move; no build stamp moves.** The CPS-2 and the PC Engine
are new. `LEGACY_GAME_STAMPS` stays empty, as in every release since 1.6.4: the X68000 sections change modules of the `*` group, which every game
stamp hashes. So every export of 1.6.8 is converted again from its paths, once, when it is upgraded.

**Quick states.** Only **the CPS-1 key** moves (it hashes the board sources the CPS-2 now shares): a quick state written by a CPS-1 or CPS-1.5
export of 1.6.8 is refused cleanly (no compatibility key is carried, [GAME_STATES.md](GAME_STATES.md)); nothing is lost but that state. The files
the keys of the Mega Drive, the Super Nintendo, the Neo Geo, the NES and the X68000 hash did not change between `v1.6.8` and this release (checked
with `git diff` on each key's inputs), so their 1.6.8 quick states load. The Master System, the Game Gear and the Game Boy have no key of this kind.
**Cartridge saves** are kept on every console, the CPS-1 EEPROM included.

## Master System and Game Gear: two defects of the "functions" engine found by the panel (1.6.9)

The 1.6.9 panel of twelve games (see [MASTER_SYSTEM.md](MASTER_SYSTEM.md#the-panel-of-twelve-games-169-gates-g2-g5-g6-g8-g9)) converted with the "functions"
engine showed four games the reference check refuses. Two general causes were found and fixed in the converter's copy of the generator
(`core.patched_generator_source`):

1. **A HALT behind a prefix.** `DD 76` and `FD 76` are a HALT; the decoder calls only the plain `76` a halt, and the generic path wrote through an `ea` that nothing
   declares, so a function the walk found in data made the C build fail (Shining Force II). They now emit the HALT of the plain opcode, with the length of the instruction
   for the address the interrupt pushes.
2. **A callee that returns through another address than the one pushed.** A routine that reads the data after its `CALL` or `RST` (`EX (SP),HL`, `LD E,(HL)`, `INC HL`,
   `EX (SP),HL`, `RET`) returns with the stack where the call left it but to a later address; the C call stack resumed at the next instruction of the caller and ran the data
   bytes as code (Shining Force II: a register changed, a stack byte differed at frame 14). Each call site now compares the address the callee popped (the slot below SP)
   with the one it pushed and, when they differ, continues there as the Z80 does (`RR_CHECK_RET`, the nested continuation of the local-RET rule). A tail jump already did so.

Authored cases for both are in `tools/cpu_selftest.py` (`DB`-after-`CALL` and `DD 76` in dead code); the check now sets `RETRO_RECOMP_STILL_ROUTE_OK=1`, because its programs have no
picture and the liveness refusal of 1.6.6 stopped them (developer checks only; a player's conversion never sets it).

What was run: the 15 games of the 1.6.4 batch plus Micro Machines, Streets of Rage and Gunstar Heroes, "functions" engine, empty library: the 15 give the same
reference match, number of passes and interpreter share as in 1.6.7 (Alex Kidd in Miracle World was run with the shared base then, one pass; it now takes three and ends at 0 percent); Shining Force II now builds and differs from frame 15 instead of frame 14
(1,103 differing frames instead of 3,586); Streets of Rage (frame 7), Gunstar Heroes (569) and Micro Machines (1,493) are unchanged. **Not solved.** Streets of Rage:
the first divergence is a `RET` at `$7DB3` that continues at `$7893` (the continuation of a call up the C stack) where the Z80 continues at `$7B84`, an address pushed inside
the called routine, across a chain of tail jumps. The others are not explained.

**Cost.** Each call site of the "functions" engine executes one more call, `rr_ret_moved`, that reads two bytes of RAM and compares them; the banked engine, the default,
is not touched. Not measured. **What moves.** `core.py` is an input of every console: the game stamp of all nine consoles moves; the games of the "functions" engine are
generated differently (the other consoles and the banked engine are unchanged by the generator).

## Master System and Game Gear: the report names the devices and the routes that stall, and the evidence of the panel (1.6.9)

A lot of evidence and documentation: the way games are converted does not change.

- **The report** (`retrorecomp/sega_evidence.py`, called by `systems/master_system.py` after the conversion for both engines) gains `hardware_devices`
  (the mapper, with a Codemasters header named and marked `not_modelled`; the video chip; the sound chip: none runs a program, none has a counter,
  all say `hardware_fidelity_validated: false`), `route_warnings` (the routes whose picture last changed in the first tenth of their frames), and for
  the banked engine the native instruction count and the halted steps of each final route (`final_checks[]`). The schema reader (`report_schema.py`) shows
  them under `devices`, `cpus[].scenarios[]` and `honesty.route_warnings` (an optional, compatible addition to report v2, described in the module text of
  `report_schema.py`: a 1.6.8 reader ignores it; no schema number changes), adds the device kind `video_unit`, and reads the reference comparison of the "functions"
  engine (which stores no validation record) as agreement on the demo route only.
- **Tools**: `tools/sega_campaign.py` (the panel of twelve, two conversions at a time, replay of the delivered file and the sheets of captures); the
  fresh-process check of 1.6.6 (`tools/sega_states_selftest.py`) run on the twelve harness builds.
- **What moves.** The game stamps of the Master System and of the Game Gear: `sega_evidence` and the two profile modules are inputs of their groups, and an
  export of 1.6.8 of these two consoles is converted once to carry the new report fields. The generated game is the same; no native file changed, so no host
  stamp and no quick-state key moves, and the other consoles do not move. The conversion adds a read of the run logs and one rewrite of the report.

## Capcom CPS-2 opens as an experimental machine (1.6.9)

The CPS-2 (profile `cps2`, [CPS2.md](CPS2.md)) is open to players in 1.6.9 as an **experimental** machine, on the owner's decision of 5 November 2026. It is
new: no export of it exists before this release, so nothing is upgraded, and it takes no path from the shared base and gives none (it is not in the
base). Its games ask for the key file of your own romset and for your own QSound DSP ROM; a set without its key is refused by name. The key never appears
in a report.

What the change moves, computed with `compilation_inputs.role_stamps` on `main` (fb984e7) and on the branch `spec/cps2-170` (game, host, build, first 12
hexadecimal digits of each stamp):

| Console | Game stamp | Host stamp | Build stamp |
|---|---|---|---|
| sms | 0fc2678c8874 → 0fc2678c8874 (same) | c2f2988c6960 → dd7df67bc277 | same |
| gg | 0b4481f823b3 → 0b4481f823b3 (same) | 12a83c918439 → 3922f7ff7cc4 | same |
| gb | 8fd95feffe50 → 8fd95feffe50 (same) | 4b6269df3065 → bef36aab44c1 | same |
| nes | 104e8a79ce3a → 104e8a79ce3a (same) | 6604df0127e0 → d2bce93fbd78 | same |
| md | dd2a92249c7c → dd2a92249c7c (same) | 8fd26081db07 → 9717d27a6f58 | same |
| snes | 01dee3a63706 → 01dee3a63706 (same) | 4ba2df72b1cb → 53b167647e5b | same |
| ng | e577a1ef4123 → e577a1ef4123 (same) | e2589892f5d8 → 3943a838d9ce | same |
| cps1 | 9beae602c913 → 2063dbf59c68 (moves) | 98d1c885071c → 9e772d75d0df | same |
| x68 | 1181dc548b13 → 1181dc548b13 (same) | c0a085c83403 → 7cc6da88f2a7 | same |
| cps2 (new) | 4e8d3e280080 | 72b0b61ab40d | 81a51ad49349 |

- **Only the CPS-1 family's game stamp moves**, and it covers the CPS-1.5: the CPS-2 is built from the same board model, so `native/cps1_machine.c`, the new
  `native/cps1_cps2_board.inc` (the CPS-2 board, included by the machine file), `cps1_eeprom.*`, `cps1_main.c`, `cps1_probe.c`, `cps1_m68kconf.h` and the modules
  `cps1_build`, `cps1_codegen`, `cps1_board`, `cps1_conversion`, `cps1_knowledge`, `cps1`, `cps1_catalogue` and the new `capcom_catalogue` and `capcom_sets`
  are inputs of both. An export of 1.6.8 of a CPS-1 or CPS-1.5 game is rebuilt once on its next conversion. `random_routes.py` is untouched: the CPS-2 plays
  the CPS-1's routes, so no other console's game stamp moves.
- **The host stamp of the nine consoles moves** because `THIRD_PARTY_NOTICES.md` now names MAME's CPS-2 driver and decryption and the provenance of the
  keys (and the licence page `licenses/cps1-machine.md` for the two Capcom consoles); the host stamp was already moving in 1.6.9 with the kit. No build stamp moves.
- **Quick states of CPS-1 and CPS-1.5 exports of 1.6.8 are refused cleanly** (the state key hashes the machine's source); the cartridge saves (the 93C46 EEPROM
  files, named by the romset) are kept and read as before.
- **A hot path of the CPS-1 changed, its cost is not measured.** Reading and writing the 68000's bus now tests the board kind first (`if (M.board.cps2)` in
  `read_word` and `write_word`, a branch per access), and drawing a tile pixel is guarded by `if (tile_priority)` (the CPS-2 writes a priority plane the
  CPS-1 does not need). Both are meant to cost nothing noticeable and the pictures and sounds are identical, but the frame cost of the CPS-1 and CPS-1.5 is
  to be measured with the 1.6.9 comparison of frame costs, on a quiet PC.
- **Nothing about the behaviour of a CPS-1 or CPS-1.5 game changes.** The final A/B comparison (`tools/ab_conversion.py`, one conversion of `1941` and one of `wof` with
  `main` and with the branch, each in its own empty library): the generated 68000 and Z80 steps, the board folder and every piece of evidence (CPU, RAM,
  picture and sound hashes, traces, states, the compressed copy) are identical. The files that differ are the changed native sources (`CMakeLists.txt`,
  `cps1_eeprom.c` and `.h`, `cps1_machine.c` and `.h`, `cps1_main.c`, `cps1_probe.c`, `m68kconf.h`, and the new `cps1_cps2_board.inc`, which a CPS-1
  board never uses), `notices.txt` (the licence page), and in the report the host stamp of the receipt, the engine identifier and the digests of the record
  that carry it (`knowledge.cores`, `record_sha256`), and the compression ratio (the executable being slightly larger).
- **The first conversions of the CPS-2** (eight sets of the panel, 100 to 145 seconds each, executables of 17.8 to 29.8 MiB): 0 interpreted 68000 and Z80
  instructions on both routes, the compressed copy equal to the reference, a quick state continued in a fresh process; the owner played the eight
  ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)).

## Capcom CPS-1.5 leaves the experimental tier (1.6.9)

The QSound boards (18 sets) are a supported part of the CPS-1 since 5 November 2026, on the owner's decision ([CPS1.md](CPS1.md#cps-15-qsound-boards)). The catalogue (`assets/cps1-catalogue.json`) now reads `tier = supported` on every row, so the CPS-1 game stamp moves (and no other: the CPS-1 host and build stamps and the other consoles' stamps are unchanged, checked with `compilation_inputs.role_stamps`). An export of 1.6.8 is rebuilt once on its next conversion, with the same code, pictures and sound; its report then says `completed` and `board_tier: supported` instead of `experimental`. The quick-state key does not move (it does not hash the catalogue), so quick states and cartridge saves are kept. The QSound sets now take part in the shared base of paths; reports of 1.6.8 say `board_tier: experimental` and are not collected.

## An account upload carries only the paths the local base lacks (1.6.9)

An upload to the account (`online._restrict`, the files that "Send" makes) now cuts each record down to the paths the local
base does not hold for the same ROM (`knowledge_exchange.without_known`); a game left with nothing new travels no record (its
conversion note still travels for the rewards). Exchange files written for another player are unchanged: they keep every
qualified path, since the reader may have no base. The owner chose this simple rule on 5 November 2026 to keep the uploads
and the online database small; the service now counts a player's `used` outcomes as the confirmation that a second upload of
the same path used to be. A Super Nintendo record keeps its SPC part whole when part of it is known, and a Neo Geo record
travels whole (their parts are bound to each other). `retrorecomp.online` and `retrorecomp.knowledge_exchange` are interface
modules (`stamp_inputs.INTERFACE_MODULES`): no stamp and no quick-state key moves for this change.

## Game Boy: the one-by-one line names the 0xFF00-0xFF7F range (1.6.9)

The window line and the conversion log counted the instructions run one by one in RAM and in the `0xFF00-0xFF7F` range but
called the second part "high memory", which did not say that this stub also covers the hardware registers. The words change
in the eight interface languages and in `retrorecomp/gameboy.py`'s log lines; the count itself does not change. Because
`retrorecomp.gameboy` belongs to the Game Boy's stamped files, the Game Boy stamp moves: an export of 1.6.8 is rebuilt once
on its next conversion, with the same code, pictures and sound. Quick states and cartridge saves are kept.

## Sharp X68000: the profile is supported (1.6.9)

On 5 November 2026 the owner decided that the X68000 leaves the experimental status ([QUALIFICATION.md](QUALIFICATION.md#owner-acceptance)). The change is the
status and the sentences that stated it: the profile (`status = 'supported'`), the status that the conversion writes in its report and the log line that
said "experimental profile" (`x68000_conversion.py`), three interface texts in the eight languages (the options note, the credits line and the
scope of the sharing, which now says the machine stays local), the tests and the golden report that pinned the old status, and the documents.

**What moves.** Computed with `compilation_inputs.role_stamps` on the commit of the profile and the interface against its parent: **the X68000 game stamp
and nothing else**. The game stamps of the other eight consoles, and the host and build stamps of all nine, are identical. The quick-state key of the
X68000 (`RR_X68K_STATE_ABI`) hashes the reference host and the machine bridge, which this change does not touch: it does not move for this change.

**The notices (a second commit, which can be left out).** `THIRD_PARTY_NOTICES.md` and the four licence pages that said "experimental" of the X68000 (and, in one of them, of the Neo Geo) are host inputs of every console: with that commit **the host stamp of all nine consoles moves** (no game stamp beyond the X68000's, no build stamp), as the notices commit of 1.6.8 did. Without it, five lines of the public notices would still call the machine experimental.

**Impact on existing exports.** An X68000 export of 1.6.8 keeps playing as it is; its report says `experimental` until it is converted again. Upgraded by 1.6.9 it is
converted in full again (its game stamp moved) and its report says `supported`. The generated code, the pictures, the sound, the saves and the hashes of every
route are not changed by this commit: the one thing that differs in the report of a game is the word `status` (see the A/B in QUALIFICATION.md).

## Sharp X68000: the paths travel, both ways (1.6.9)

The X68000 joins the experimental tier of the shared base ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#x68000-joins-the-base-169-5-november-2026)): its
conversions make a numeric record (`x68_knowledge`), take the records of others as hints, and the conversion's report gains a `knowledge` section; the
library's game summary gains a `record`. A new field of the profile, `SharedKnowledge.quick_check_from_shared`, lets a machine keep its scan level when paths
qualified by others exist (the X68000 does, every other machine keeps the quick check).

**What moves, in black and white: the game stamp of all nine consoles.** `retrorecomp.path_profiles`, `retrorecomp.knowledge`, `retrorecomp.knowledge_exchange`,
`retrorecomp.batch` and `retrorecomp.systems.specs` are inputs of the game stamp of every console (the `*` group of `stamp_inputs`), and this branch edits them
(the layout and source checks for the X68000, the dispatch of the schema 3 module, the generic collector, the guard of the quick check, the new field). Computed with
`compilation_inputs.role_stamps` on this branch against the exit commit: the game stamp of the Master System, Game Gear, Game Boy, NES, Mega Drive, Super Nintendo,
Neo Geo, CPS-1 and X68000 moves; no host stamp moves (the host stamps move with the notices commit of the exit, already counted), no build stamp moves.
`LEGACY_GAME_STAMPS` stays empty: **every export of 1.6.8 is converted again, once, when it is upgraded.** The CPS-1 module gains one line (`PATH_CAPS`, the ceilings of its paths by name, the same form as the X68000's) and its profile one argument (`module`, the name
of its knowledge module): no value of the CPS-1 changes, its game stamp was already moving with the files above, so this adds no impact, and the CPS-1 exchange
tests pass unchanged. The profile now declares the module of a machine without a schema 1 form (`SharedKnowledge.module`) instead of the sharing code naming it.

**Quick states.** No key moves for this change (`RR_X68K_STATE_ABI` hashes the reference host and the bridge, untouched).

**Exchange files and the base.** A version 3 file and line 3 of the base carry X68000 records; a converter of 1.6.8 reads a record it does not know as it reads
any unknown machine (skipped), and a version 2 file leaves the games out. The service has to accept records of 90 to 130 KB of JSON (20 KB compressed).

## Host kit: nothing blocks a third or fourth player (1.6.9)

The rules of [HOST_KIT.md D13](HOST_KIT.md#d13), on every console: the gamepad Quit and Restart combinations and the trigger
speed controls are watched on player 1's pad only (any player's Start+Coin held one second restarted a CPS-1 or Neo Geo game
for everyone). **On two-player consoles too, player 2 holding Start+Select (or L3+R3) no longer restarts (or quits) the game;
only player 1's controller does.** A player whose pad column the adapter leaves empty gets player 1's buttons; players 3 and 4
of a board that has them get keyboard keys of their own ([CONTROLS.md](CONTROLS.md#players-3-and-4)); a key or button bound in
F2 swaps with the action that had it.

**What moves.** Computed with `compilation_inputs.role_stamps` of the nine consoles, against main at `a637502` and again after merging `850db7e`: **the host stamp
of all nine consoles** (`native/hostkit/shell/*`, `hostkit_internal.h` and the CPS-1 adapter are host inputs). **No game stamp
and no build stamp moves**: an export of 1.6.8 that has nothing else to rebuild is upgraded (rebuilt from its paths, no
rediscovery).

**Quick states.** The kit commit moves **no quick-state key**: `native/game_options.h` and the catalogue are left byte-identical
on purpose (the kit hides the other players' pads from the checks of `game_options.h` in `rrhk_options.c`), and the shell files lie
below `native/hostkit`, which no key hashes. A one-line CPS-1 help naming the keys of players 2 to 4 is held back for 1.7: its
strings would change `native/runtime_catalog.inc`, which the Mega Drive and Super Nintendo keys hash.

**Preferences.** Nothing is renamed. A file written by 1.6.8 keeps its meaning; keys saved for players 3 and 4 win over the new
defaults, and a default of player 3 or 4 that a saved key of another action already uses is dropped (no key drives two actions).
A stored key 0 or button -1 now reads as "no binding" on every console (the X68000 alone read it so before): F2 writes it when a
swap leaves an action without a key. Two actions that already shared a key in a saved file keep sharing it until one of them is
bound again in F2.

## Computers: the keyboard goes to the game or to the computer, per game, from F2 (1.6.9)

A keyboard game on a computer (the X68000 now, the Amiga when it opens) needs its keys, while the keys bound to the pad would
press the joystick at the same time. The switch that hands the whole keyboard to the computer (Ctrl+Alt+K) is now also a row
of the F2 options page, **Keyboard (Ctrl+Alt+K): game controls / computer only**. On "computer only" the keys bound to the pad
stop and a real gamepad plays the joystick; a notice says so when no gamepad is connected. The choice is **kept per game** in the
game's own `player.cfg`, written at once: a game no longer starts in the mode of the last game played, and each game starts with
the game controls until the player chooses. The texts are English and French for now (the five-language catalogue is left
untouched in 1.6.9 so that the Mega Drive and Super Nintendo quick states stay valid; the other languages come in 1.7).

**What moves.** Computed with `compilation_inputs.role_stamps` of the eleven consoles before and after the change: **the host stamp
of the X68000** only (`native/hostkit/adapters/rrhk_computer.inc` and `rrhk_x68k.inc`). No game or build stamp moves, no quick-state
key moves.

**Preferences.** `[X68000] guest_keyboard` of `datas/Retro-Recomp.ini` is no longer read or written; a game converted by 1.6.8
keeps its own choice, which `player.cfg` already held (`keyboard=`).

## Sharp X68000: the generator of native code and the computer part of the adapter are shared (1.6.9)

The Amiga reuses what the X68000 does with the instructions it runs from RAM instead of copying it, so two files moved and one declaration was added; **nothing a
game does changes**.

- `retrorecomp/m68k_observed.py` holds the generator that `tools/x68000_native.py` held: the decoder tool, the word-count table, the step semantics file, the forms, the guarded
  steps, the page table and the index (`write_steps`), for a machine's C prefix and step type. A profile declares what is its own with
  `SystemProfile.observed_code` (`ObservedCode`: the entry point of its instruction bodies, `module:function`, the prefix, the address apertures, and since the second commit
  the extension and the head of the step files). The X68000 declares `m68k_observed:recompiler_bodies` (the Mega Drive recompiler's semantics with the shared state rules,
  executed by Musashi) declares its address apertures as data in its profile (`ObservedCode.apertures`) and keeps in `tools/x68000_native.py` its bus (`CODE_VIEW`), its Musashi template, its native run and its guard fixtures. No machine is
  named in the shared module (a test reads it), and a machine whose bodies are not Musashi's (the Amiga's Moira, C++ templates) gives with its bodies the text of a step and the header every step file includes
  (`InstructionBodies.step_text`, `semantics_text`) instead of editing the module (a test does it with a fake profile).
- `native/hostkit/adapters/rrhk_computer.inc` holds what `rrhk_x68k.inc` held that every disk computer shares: the guest keyboard and its Ctrl+Alt chords, the captured mouse and the
  mouse-game pad, the floppy drives (swap, eject), the fast-loading key, the function keys, the second help page, the window preferences. The adapter tells it its actions by macros
  (`RRC_*`) and the frontend provides the variables it reads (the list is in the file's header); the machine table, the pad mapping, the picture, the sound and the state stay in
  `rrhk_x68k.inc`. The host kit's shell is not touched.

**Proof that the output is the same.** The generated native project (`cpu.c`, `cpu.h`, the 16 step files, the index, the tables, `generation.json`, the semantics and the word counts)
of three games of the collection (Twins, Double Target, Pac-Land) was written with the converter of `main` and with this tree from the same observations: **120 files, 0 differences**.
The generator's revision (`x68_knowledge.GENERATOR_REVISION`) stays 1, so no qualified path is lost; the pins list the new module. A/B of conversions: see the end of this section.

**What moves** (`compilation_inputs.role_stamps`, this branch against the commit it branches from, `e1424c7`): **the game stamp of all nine consoles** (`retrorecomp/systems/specs.py` and
`retrorecomp/systems/__init__.py` are inputs of every console and gain `ObservedCode` and `SystemProfile.observed_code`), and **the host stamp of the X68000** (the adapter files); no
host stamp of another console, no build stamp. The quick-state key of the X68000 (`RR_X68K_STATE_ABI` hashes the reference host and the bridge) does not move. Every export of 1.6.8 is converted
again once when it is upgraded, as the rest of 1.6.9 already says.

**A/B of conversions** (Windows, standard scan, an empty library each, headless; R-Type, Bubble Bobble, Metal Sight with its five disks and Lemmings with the mouse): the CPU, RAM, picture and PCM hashes of the
three routes are equal to those of the panel replayed on the tree of the exit (12 routes, 0 difference), 0 interpreted opcodes, the compressed copy matching, the same numbers of pictures and audio blocks, the two automatic
disk changes of Metal Sight. The sharing record of Twins made by this tree has the digest of the one made before the move (0c77fd2d4abf65d5, same counts, same engine). The window code of the adapter
(the computer's part) is compiled by every conversion and exercised by the SDL harnesses of `tests/x68000_controls_harness.c` and `x68000_menu_harness.c` (virtual controllers, the guest keyboard, the mouse game,
autofire, the menus and the help page), which pass with one change: the state of the windowed player is `ca` (the computer's) instead of `xa`. What a real window does with a real mouse and a real second
floppy is still the owner's next play to confirm.

## PC Engine: an experimental machine (1.6.9)

The PC Engine / TurboGrafx-16 is added as an **experimental** machine ([PC_ENGINE.md](PC_ENGINE.md)): the converter reads HuCard
dumps (`.pce`, or a ZIP holding one), builds a standalone Windows game on the engine
[rages4calm/pcenginerecomp](https://github.com/rages4calm/pcenginerecomp) pinned at `81b5c231e452`, and reports native and interpreted
instructions per route. The machine is listed when the installation carries its native files (`PC_ENGINE.available()`); there is
no developer switch any more.

**The archive limits move onto the profiles.** The table of the cartridge names a ZIP may hold and their size limits
(`systems.MAX_ARCHIVED_ROM_BYTES`) was a literal in `retrorecomp/systems/__init__.py`, so a new machine that reads ZIPs edited a
module every console's game stamp hashes. Each machine now declares its own limits on its profile
(`SystemProfile.archived_rom_limits`), and the table is built from the registered profiles plus the generic `.bin` and `.rom`
(`systems.GENERIC_ARCHIVED_ROM_BYTES`). The values of the nine consoles are unchanged (`tests/test_registration_surface.py`
compares them with the former table); `.pce` is added by the PC Engine profile. Machines added later (the Game Boy Advance first)
declare their limits on their own profile, so the stamps of the others no longer move for it.

**What moves** (`compilation_inputs.role_stamps`, this branch against `fb984e7`, the main it merged): **the game stamp of all
nine consoles** (`systems/__init__.py` and the profile modules are inputs of the consoles that import them) and **the host stamp
of all nine consoles** (`THIRD_PARTY_NOTICES.md`, a host input, gains the pcenginerecomp row). **No build stamp moves, and no
quick-state key moves.** The PC Engine's own stamps are new (game `1e1f8e8f29ba`, host `11870ec2b6f9`, build `66d912662e5c`, first twelve characters, computed on the tree of the US-cards change below, after the merge of `main` of 6 November 2026). An
export of 1.6.8 is rebuilt from its paths when it is upgraded, with no rediscovery, as for the rest of 1.6.9.

**Checks that need no ROM.** `tests/test_pc_engine.py` (profile, reader, ZIP, report, routes, liveness, state configuration, game
CMake, start choice), the registry test (`tests/test_machine_registry.py` lists the machine in every registry it needs and declines
`random_routes` and `memory_view` on the record), the language test (the PC Engine strings in eight languages, in the font
subsets), and `tools/gui_smoke.py` (the options page of the new machine). Games, ROMs and the engine are not in the repository.

**Deep application folders (release check, 5 November 2026).** The engine names the object library of a module `pce-module-<64 hex>`, and Visual Studio
wrote `pce-module-<64 hex>.dir\Release\pce-module-<64 hex>.lib` below the game's CMake build folder: 166 characters that, under an application folder of
about 60 characters or more (`...\AppData\Local\Programs\Retro-Recomp`, a Downloads folder), passed the 260-character limit of Windows and stopped the link
with `LNK1104`. The engine's target is still created (it validates the manifest and lists the sources) but is never built: the game compiles the module's
sources in an object library of its own, `pce_module` (`pce_build.game_cmake`), so no engine source is patched. **What moves:** only the PC Engine's game
stamp (`pce_build.py` is an input of it); its host and build stamps and every other console's stamps do not. **Limit:** a conversion now works with an
application folder of up to **123 characters** (the folder that holds `.build`, measured: 119 converts Bonk's Adventure with no interpreted instruction and the
packed replay and F8/F9 gates passing, 124 stops). Beyond that the limit is no longer the PC Engine's: it is CMake's own compiler check, which writes
`<build folder>\CMakeFiles\CMakeScratch\TryCompile-xxxxxx\...` (104 characters) in the first configure of any game's build folder, which here is
`<app>\.build\pce\<12 hex>\n\build` (32 characters below the application folder), so the build folder may hold 155 characters; every machine's game builds go through
the same check.

**US TurboGrafx-16 cards (6 November 2026).** The reader tells the two bit orders apart by the first instruction at the reset vector
when the vector is plausible both ways (`pce_rom.py`: 4 of the 91 US cards of the maintainer's library; they stay `linear` as
before, and a bit-reversed dump of them is now read as such), and the console is named **PC Engine / TurboGrafx-16** where it is
listed to the player (the profile name, so the report's `system.name` and the executable's version resource too, the Options page, the
credits, README and the documents; the export folder stays `PC Engine`), and the profile is marked `linux = 'witnessed'` (9 cards equal on a Debian 13 PC, [PC_ENGINE.md](PC_ENGINE.md#linux-witness-6-november-2026)), so a Linux build converts PC Engine cards. **What moves:** only the PC Engine's game stamp (the
reader, the profile and the report writer are inputs of it); its host and build stamps and every other console's stamps do not.
A game exported before this change is rebuilt when it is upgraded; its behaviour does not change. Proof: [PC_ENGINE.md](PC_ENGINE.md#us-turbografx-16-cards-6-november-2026).

**Disk space.** The clean-up after a publication and Options › Common › Disk space know the PC Engine's build folders (`.build/pce/<12 hex>/`, locked while a conversion runs), like the CPS-1's.

**What a PC Engine export is.** Two players, quick states (F8/F9), the host kit's window and controls
([CONTROLS.md](CONTROLS.md#pc-engine)); the report keeps native code, CPU fidelity, hardware fidelity, gameplay and physical latency
apart. The first panel (ten cards) and its limits (the engine's 65,536 instruction identities per module, SuperGrafx refused) are in
[PC_ENGINE.md](PC_ENGINE.md#the-first-panel-5-november-2026).

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
| [Capcom CPS-1.5, the QSound boards](CPS1.md#cps-15-qsound-boards) | CPS-1 (new files `cps1_kabuki.py`, `cps1_qsound.c` and others; see the machine page) | not stated | not stated |

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
[Other machines whose game stamp moves in 1.6.5](UPGRADES_HISTORY_OLDER.md#other-machines-whose-game-stamp-moves-in-165) and [NES.md](NES.md)).

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

