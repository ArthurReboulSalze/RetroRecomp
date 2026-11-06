# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

This page keeps the rules, the current release and the one before it. The detail of releases 1.6.7 to 1.6.5 is in
[UPGRADES_HISTORY.md](UPGRADES_HISTORY.md), and that of 1.6.4 and before in [UPGRADES_HISTORY_OLDER.md](UPGRADES_HISTORY_OLDER.md) (the same text,
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
quick-state key moves.** The PC Engine's own stamps are new (game `c8545bf9018e`, host `6ea8ea8ac8eb`, build `66d912662e5c`, first twelve characters, computed on the tree of the deep-folder fix below). An
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

**Disk space.** The clean-up after a publication and Options › Common › Disk space know the PC Engine's build folders (`.build/pce/<12 hex>/`, locked while a conversion runs), like the CPS-1's.

**What a PC Engine export is.** Two players, quick states (F8/F9), the host kit's window and controls
([CONTROLS.md](CONTROLS.md#pc-engine)); the report keeps native code, CPU fidelity, hardware fidelity, gameplay and physical latency
apart. The first panel (ten cards) and its limits (the engine's 65,536 instruction identities per module, SuperGrafx refused) are in
[PC_ENGINE.md](PC_ENGINE.md#the-first-panel-5-november-2026).

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
