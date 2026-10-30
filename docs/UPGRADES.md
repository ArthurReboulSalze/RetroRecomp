# Upgrading exports without rediscovery

When a new converter version only changes the **player shell** (menus,
options, on-screen text, fonts, filters, sound output, icons, notices) and a
game has nothing new to learn, its export is **upgraded**: the executable is
rebuilt from the paths already learned, without replaying the exploration
routes. Anything that can change which code a game runs, how it is translated
or how it is validated still triggers a full conversion.

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
  1.6.0; the tree of 1.6.1 listed the stamps of 1.6.0 ([history](#exports-of-160-in-161)); the tree of 1.6.2 listed those of
  1.6.1 ([history](#exports-of-161-in-162)); the tree of 1.6.3 listed those of 1.6.2 ([history](#exports-of-162-in-163)); the
  tree of 1.6.4 lists none, a full reconversion of every console ([below](#exports-of-163-in-164)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1. The Mega Drive, Super Nintendo, Neo
  Geo and CPS-1 keys of 1.6.1 (Windows) in the tree of 1.6.2. The same four consoles' keys of 1.6.2 (Windows) in the
  tree of 1.6.3. The Neo Geo key of 1.6.3 (Windows) alone in the tree of 1.6.4: the Mega Drive and Super Nintendo keys did
  not move, and the CPS-1 and NES states changed ([below](#exports-of-163-in-164)).
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

## Exports of 1.5.6 in 1.6.0 (history)

This section is the dated record of the release that moved the stamps; 1.6.0 itself no longer carries these entries
(see [the rule](#the-rule-the-previous-release-only)): a 1.5.6 export, like any export older than 1.6.0, is converted in
full by 1.6.1 and after.

1.6.0 moves every console's game stamp on purpose (standardisation: the paths module of stage B3, the host kit, the
CPS-1 build modules, reproducible stamps). What a conversion generates did not move, so the exports of the last release
before it stay upgradable where that was shown (`LEGACY_GAME_STAMPS`, last value, 27 October 2026):

| Console | 1.5.6 export in 1.6.0 | Why |
| --- | --- | --- |
| Master System, Game Gear, Game Boy, NES, Mega Drive, CPS-1 | **upgraded**: rebuilt from its paths with the new host, rechecked on the quick routes, `upgrade.from_release` = `1.5.6` | the 1.5.6 game stamp reproduced the game part of real receipts, and the generated game sources are identical (below) |
| Super Nintendo | converted in full once | the engine changed what games do after 1.5.2 (`$4016` strobe, Super FX); its states are bound to the exact signature |
| Neo Geo | converted in full once | a 1.5.6 receipt hashes the whole Neo Geo bank in its knowledge part; 1.6.0 hashes the game's own record, so no entry can ever match (do not add one) |
| Sharp X68000 | converted in full once | its request carries an SDK stamp the mechanism does not cover; the pre-1.6.0 observation and library pairs are migrated by step 6a |

**Evidence** (27 October 2026, Windows, Python 3.14.5, quick scan level, two games per console, read in place from the ROM
share, nothing copied; outputs under `.build/legacy-156-20261027/`). Master System: Alex Kidd in Miracle World and Action
Fighter. Game Gear: Factory Panic and OutRun. Game Boy: Alleyway and A-mazing Tater. NES: 3-D WorldRunner and Airwolf. Mega
Drive: Alex Kidd in the Enchanted Castle and Art Alive. CPS-1: Nemo and Pnickies. Each game was converted by the converter of
the `v1.5.6` tag (`git archive`, run as `RetroRecomp.py batch`, not the packaged executable) and by the 1.6.0 tree, from the
very same folder (the generated files hold absolute paths), with the same options (`--scan-level quick --jobs 8
--keep-build`, nothing online).

- *The stamps are the real ones.* The 12 receipts written by 1.5.6 (schema 3) each carry a game part equal to
  `hash(request with engine = the stamp computed from the tag)`: asked about each export, the 1.6.0 code answers
  `match_legacy` for 12 of 12 (a dry run of `freshness.upgradable`, nothing converted), and `match_current` for none. The
  packaged 1.5.6 `Retro-Recomp.exe` prints the same engine stamps as the tag for the seven consoles its `_compilation-stamps`
  command lists (CPS-1 and X68000 are not in that list, so the CPS-1 stamp rests on the receipts written by the tag's code).
  No real 1.5.6 export existed in `Export/`; the receipts above are the evidence.
- *The generated game is identical.* Every file of the 12 project folders was compared, minus object files, run logs and the
  wall-clock seconds of the check results: all generated C sources, tables, trace files and check hashes (frames, audio, CPU,
  RAM, native and interpreted counters) are byte-identical. What differs, per kind:
  - the version text: `RR_RECOMP_VERSION` in the CMake files, `game_resources.rc` (and `RR_CPS1_VERSION` in `cps1_game.h`);
  - the shell, which is host: `console16_host_ui.c` is replaced by `hostkit/shell/rrhk_*.c` and one adapter in the Mega Drive
    and CPS-1 projects (their `CMakeLists.txt` list the new files), `game_options.h` (option rows hold their own text) and its
    checks (`game_options_checks.c`, `neogeo_controls_checks.c`), also copied into the NES project;
  - the state keys: `retro16_state_config.h` (Mega Drive and CPS-1 `RR16_STATE_ABI`), and `console16_state.c` gains one
    `#ifdef RR16_STATE_COMPAT_ABI_24`, which no other console defines; the NES `cycle/raw/generation.json` records the hash of
    the recompiler binary rebuilt in each run and of a log whose only difference is a random temporary folder name; the Mega
    Drive `generation-identity.json` records the code digest of `megadrive.py` (`adapter`);
  - the states written by the CPS-1 checks (`quick.rrstate`, `invalid.rrstate`): same size, and only the 64 bytes of the
    header that hold the key differ.
  Nothing in the Game Boy, Master System, Game Gear projects differs but the version text. None of these is game code, so the
  rebuild of an upgrade (new host, same game) is what a reconversion would produce. Last-minute edits after this run (the
  Mega Drive and Neo Geo state keys, comments, tests) touch no generated game file; the Mega Drive state header gains its
  `RR16_STATE_COMPAT_ABI_24` line.
- *The upgrade runs for real* (`tools/campaign.py upgrade`, copies of the 1.5.6 exports, no `--force`): Master System Alex Kidd,
  Mega Drive Art Alive, Mega Drive Alex Kidd in the Enchanted Castle and CPS-1 Nemo were each reported `quick upgrade`,
  `upgrade.from_release` = `1.5.6`, `check_level` quick, and their final checks (scenario hashes, native and interpreted
  counters, frames) equal those of the 1.5.6 report. The two Mega Drive games keep the interpreter fallback they already had
  in 1.5.6 (Art Alive 11.4 million opcodes in the demo, Alex Kidd in the Enchanted Castle 26 and 96), which the campaign verdict
  (limit 0) marks FAIL; the upgrade neither adds nor removes any. The upgrade report keeps the scan level of the export's own discovery, read from `scan_level`, `scan.level` or `advanced_scan.level` (the Mega Drive, Super Nintendo and NES reports of 1.5.x only have the last), so an Extended or Thorough export of 1.5.6 stays one after an upgrade. Quick states: the Mega Drive, Neo Geo (both added in this work) and CPS-1 exports upgraded from 1.5.6 load the quick states written by the 1.5.6 export on Windows, the Super Nintendo ones do not ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-156-history)).

Measurements stay separate: this is native code, CPU fidelity against the fresh reference on the quick routes and the identity
of the generated game; it says nothing about hardware fidelity, gameplay or latency. A Linux 1.5.6 export is not covered (the
stamps are bytecode digests of Python 3.14.5, the Linux converter is built with another Python).

## Exports of 1.6.0 in 1.6.1

This section is the dated record of the release that listed the stamps of 1.6.0; 1.6.2 no longer carries these entries
(see [the rule](#the-rule-the-previous-release-only)): an export of 1.6.0 is converted in full by 1.6.2.

1.6.1 moves the game, host and build stamps of every console. The reason is the packing notice (a Linux game UPX cannot
pack and test is published unpacked): `packing.py` (build), `publishing.py` (host) and the callers `batch.py`, `core.py`,
`systems/master_system.py` (game, all consoles), `neogeo_conversion.py`, `neogeo_build.py` and `cps1_conversion.py` now pass
the conversion log to the packer, so the interface shows the reason, and the Neo Geo `native-validation.json` says
`validated_candidate: unpacked` when it applies. Nothing a game generates changed, except the Mega Drive runtime
([below](#mega-drive-exports-of-160-in-161)). The release procedure (the rule above) adds the entries of 1.6.0, and only
those, to `LEGACY_GAME_STAMPS` (28 October 2026, the tree of this release):

| Console | 1.6.0 export in 1.6.1 | Game stamp of 1.6.0 (computed from the `v1.6.0` tag) |
| --- | --- | --- |
| Master System | **upgraded**: rebuilt from its paths, rechecked on the quick routes, `upgrade.from_release` = `1.6.0` | `19b8bd2a33d49f8b2d08e2335e7ee5d96178347c941d3da73800b0bb61551732` |
| Game Gear | upgraded | `47c60b9a2034948c0f2c31e8e3a209a368f8ef45490cc6047f73cfb882c637be` |
| Game Boy | upgraded | `c36134ebfc832440005280367b64225bc09b486c3fff560d0f8a1376110712da` |
| NES | upgraded | `511451fc62f41db3f8dee6f57e1d2b2d2623cf8a0171482bd73bcb2bb595432b` |
| Mega Drive | upgraded, with the corrected runtime | `4db8a6f2397ab51d383166778c227e45cadcd3806bd7bf5aaf7e965267744b75` |
| Super Nintendo | upgraded | `cccb132e2e23df78340770cd1c0c562d32645d732e97aa15c4e853e66c06af36` |
| Neo Geo | upgraded (a 1.6.0 receipt hashes the game's own record in its knowledge part, so the stamp can match; the 1.5.6 one never could) | `41577b77c4e78dd15d8644092591e5852efc1c96e9fe5be1dde2bbca8b1fcb61` |
| CPS-1 | upgraded | `699f824303f77ebbf4583bd7c9cc1ee1aa7c167391e247e0010f7fbc72ec5b95` |
| Sharp X68000 | **converted in full once**: no entry | `7de0d3b5731e81f2df6a705a502e165d07349423641dcc2454ce1de9392a6f36` (recorded, not listed) |

- *X68000.* Its request carries `x68_sdk`, a hash of the game stamp of the tree that wrote it and of the machine base. The
  table replaces the `engine` field of the request and nothing else, so an X68000 receipt of 1.6.0 could never be
  recognised: an entry would be dead weight. Do not add one without teaching `request_parts` to recompute `x68_sdk` for a
  listed stamp.
- *Super Nintendo.* An earlier release excluded it (1.5.2: the engine changed what games do). Between 1.6.0 and 1.6.1
  nothing specific to it changed: below `native/` only two Mega Drive files differ from the tag, and the converter modules
  that differ are the shared ones (the packer's notice in `batch`, `core`, `packing`, `publishing`, `artwork`; the removal
  of readers of files older than 1.6.0 in `feedback`, `freshness` and `library`; `console16_state` loses the older
  compatibility keys). None of them changes a Super Nintendo project, and its quick-state key is the same in 1.6.0 and 1.6.1
  ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-160)).

**How the stamps were computed.** The `v1.6.0` tag (commit `84d5a9e`; no listed input differs from `15da7be`, the commit
the packaged converter was built from) exported with `git archive`, then `compilation_inputs.role_stamps(system)['game']`
under Python 3.14.5, the Python of the packaged 1.6.0 converter (`.build/release-1.6.0/package-windows.log`) and of this
tree. The game parts of the tag and of 1.6.1 differ in these listed inputs only: `retrorecomp.batch`, `core`, `feedback`,
`freshness`, `library` (every console); `systems.master_system` (Master System, Game Gear); `x68000_conversion`;
`neogeo_conversion`, `neogeo_build` (Neo Geo; the latter also CPS-1); `cps1_build`, `cps1_conversion`, `cps1_knowledge`
(CPS-1); `console16_state` (Mega Drive, Super Nintendo, Neo Geo, CPS-1); `native/md_z80_bus.inc` and
`native/md_boundary_checks.c` (Mega Drive). The host part differs in `artwork`, `publishing` (and `gameboy_host` for the
Game Boy), the build part in `packing`.

**Evidence, and what is not proved.** The release procedure asks for real receipts written by the released converter (two
games per console, as for 1.5.6). None was produced for 1.6.1: no game was converted for these entries. What exists:

- *Mega Drive, 3 Ninjas Kick Back*
  (`Export/Games/Mega Drive/datas/reports/Game_3_Ninjas_Kick_Back-8cfdc448d062/conversion-report.json`), the only schema 3
  receipt of 1.6.0 in `Export/`, written on 28 October 2026 at 07:16 by the working tree that became `15da7be`. Its **host
  part** equals the hash of the host settings (language `en`, icon tags, online cover, covers on, the title) with the host
  and build stamps computed from the tag: the converter that wrote it had the tag's host and build inputs, hashed under the
  same Python. Its **game part** could not be derived again: it hashes the knowledge stamp of the player's banks as they
  stood before that conversion, and the banks have changed since. It does not confirm the game stamp by itself. The other
  consoles of `Export/` hold receipts of earlier releases only.
- The method is the one that gave the 1.5.6 entries; run on `v1.5.6`, the same computation gives the three 1.5.6 quick-state
  keys that were read from real 1.5.6 exports (Mega Drive, Neo Geo, CPS-1: [GAME_STATES.md](GAME_STATES.md#states-written-by-release-160)).
- An entry cannot accept a wrong export: a receipt matches only if its game part is the hash of the request with `engine`
  equal to the listed stamp, so a stamp the 1.6.0 converter did not write matches nothing and the export is converted in
  full as before. What the table cannot show without receipts is that a matching export is equivalent to a reconversion,
  and that is the claim above (the list of inputs that differ).

A real receipt per console (the 1.5.6 procedure: `tools/campaign.py upgrade` on copies of exports converted by the 1.6.0
tree) remains to be done if "upgraded" is to be proved console by console. An export of 1.6.0 that is upgraded is rebuilt
and rechecked on the quick routes like any upgrade, and the report says so.

**Stars of the collection.** 1.6.0 reread the scan level of Mega Drive, Super Nintendo and NES rows of a 1.5.x inventory
in memory and wrote it back only when **Compiled games** saved the collection. A 1.6.0 player who never opened it may
still have a file whose rows say Standard for games converted deeper by 1.5.x; 1.6.1 no longer rereads it, so those rows
keep one star until the game's report changes (its next conversion). Nothing else depends on that star.

## Game Gear: F5 sprite flicker reduction, and two files change group (1.6.5, in preparation)

Game Gear exports gain the **F5** sprite flicker reduction that the Master System has had since 0.25.0 (off by default, saved in
`[GameGear.Video] reduce_sprite_flicker`; the Game Gear VDP has the same eight-sprite line limit). The renderer change is in
`native/video_mode4.inc` (the three Game Gear guards are gone: with the option off the code does less, not more) and the key, the
F2 row and the setting are in the shared adapter `native/hostkit/adapters/rrhk_sms.c`. The option changes the presentation only: no
ROM patch, collision and overflow flags keep using the original eight sprites, and the checks of the native and the reference
renderer still agree on every scene (`tools/pixel_optimization_selftest.py`, `tools/video_selftest.py`).

Stamps (computed with the tree of 1.6.4 and the tree of this change): the **game stamp of the Master System and the Game Gear moves**
(renderer) and so does their **host stamp** (adapter), so their exports are rebuilt with the upgrade path. In the same change
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
with and without the change, from an empty learning state (the other two are High-Tech World and The Lost Stars, which the change targets). The game stamp of both consoles moves with `core`.

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
stopped at the first affected frame and goes on now. Interpreter fallback stays counted per CPU. The game stamp of both consoles
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

## X68000: exact redraw marks for the background and the sprites (1.6.5)

The machine redraws a screen line only when it is marked, and the pinned base marked **every** line on any write to a background
map or pattern, and sixteen lines for any write to a sprite register, drawn or not. The marks now cover exactly the lines whose
picture can have changed, using the mapping of the line drawing (the previous section):

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

## Exports of 1.6.2 in 1.6.3

1.6.3 moves the game stamp and the host stamp of every console, and the build stamp of none (the packer is the UPX 5.3.0
of 1.6.2). Most of what moves them is the host kit shells of the Master System, Game Gear, Game Boy and X68000, the
shared conversion helpers and the profile registry, and none of that changes what a game is or does; three CPU
corrections do change what a game does or what a conversion generates (the 68000 shifts, the 65816 BRK and COP, the Z80
"functions" engine). The written release procedure ([COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#legacy_game_stamps):
list no console whose game the release really changes) decides which exports of 1.6.2 are upgraded, rebuilt from the paths
already learned and rechecked on the quick routes, and which are converted in full: **upgraded** are the Master System, Game
Gear, Game Boy and NES; **converted in full** are the Mega Drive, Super Nintendo, Neo Geo, CPS-1 and X68000. The later
sections of this file list each change of the release; what follows is what each console's stamps do.

| Console | Game stamp moves because | Host stamp | 1.6.2 export in 1.6.3 |
| --- | --- | --- | --- |
| Master System | host kit phase 4 ([below](#master-system-and-game-gear-exports-in-163-host-kit-phase-4)): the staging call in `core`, the source list in `native/CMakeLists.txt`, `console16_video.h`; the "functions" engine no longer makes a direct call to a paged address ([below](#cpu-fixes-carried-from-the-upstream-review-in-163)) | moves | **upgraded**, `upgrade.from_release` = `1.6.2`; the default banked engine generates the same sources, and a "functions" export that diverges fails the recheck and is converted again |
| Game Gear | the same two | moves | upgraded, as the Master System |
| Game Boy | host kit phase 5 ([below](#game-boy-exports-in-163-host-kit-phase-5)): `gameboy_runtime` (staging, source list, and the embedded resources linked into `gbrt` on Linux), `gameboy`, `gameboy_build`, `console16_video.h`; no game behaviour changes | moves | upgraded |
| NES | the shared conversion helpers in `nes`, `nes_build`, `nes_codegen` and its profile data; the generated sources are the same | moves | upgraded |
| Mega Drive | `m68000` (ROXL and ROXR with a register count of zero, ASL.L by 31: [below](#cpu-fixes-carried-from-the-upstream-review-in-163)), `console16` (shared helpers) | moves | **converted in full once**: the 68000 shifts change what a game does; a ROM the shared base knows starts from its qualified paths with the quick check |
| Super Nintendo | `snes_codegen` (BRK and COP), `console16` (the shared `snes_ppu_header`), `native/snes_cpu/interrupt_checks.c` | moves | **converted in full once**: BRK and COP change what a game does; a ROM the shared base knows starts from its qualified paths with the quick check |
| Neo Geo | `m68000`, `neogeo_build`, `neogeo_conversion`, `neogeo_persistence_checks`, `neogeo_state_checks` (shared helpers and gates), `native/neogeo_m68000_checks.c` | moves | **converted in full once**: the 68000 shifts, as above |
| CPS-1 | `m68000`, `cps1_build`, `cps1_conversion`, `neogeo_build` (shared helpers; this rollover's key line), `cps1_knowledge` | moves | **converted in full once**: the 68000 shifts, as above; `GENERATOR_REVISION` stays 6, see below |
| Sharp X68000 | host kit phase 3 ([above](#x68000-exports-in-163-host-kit-phase-3)), `m68000`, the zeroed OPM chip | moves | **converted in full once**: no entry |

Every console's game stamp also moves for reasons that touch no output: `core` and `conversion_common` (the helpers the
converters share; `conversion_gates` too for the Neo Geo, CPS-1 and X68000), `systems`, `systems.specs` and the profiles
(the registry), `path_profiles`, `paths`
and `random_routes` (the tables read from the profiles), and the checks `host_checks.c`, `lazy_data_checks.c`,
`presentation_checks.c` and `native/CMakeLists.txt`. The tests that pin these refactors against values taken before they
existed are `tests/test_conversion_common.py`, `test_conversion_gates.py`, `test_path_tables_snapshot.py` and
`test_registration_surface.py`.

**The base is intact.** No pinned upstream revision moved between the `v1.6.2` tag and this tree: the engine revisions of the
Master System and Game Gear, Game Boy, NES, Neo Geo (Geolith and Lithogen), CPS-1 (ymfm and the MAME revision of the
catalogue), the Mega Drive and Super Nintendo repositories (`console16.REPOSITORIES`), SDL and the X68000 pin are the same
values in both trees (compared line by line). The corrections above are our own patches on those revisions
([UPSTREAMS.md](UPSTREAMS.md)), so the base of qualified paths, keyed by the revisions, stays valid: a ROM the shared base
knows starts from its qualified paths when its export of 1.6.2 is converted in full, with the quick check, not from
scratch. The CPS-1 generator revision is 6 (raised for the 68000 shifts and the shared helpers
earlier in 1.6.3); the rollover of the quick-state key edits `cps1_build.py`, a pinned generator source, once more, and the
revision is **not** raised to 7: revision 6 has not shipped, no path was qualified by the code between the two edits, and
what a RAM path could notice (the generated files, the serialized bytes) is the same. The pins of
`tests/cps1_generator_pins.json` follow and the comment of the revision says so.

The release procedure (the rule above) replaces the entries of 1.6.1 by those of 1.6.2, and only those, in
`LEGACY_GAME_STAMPS` (29 October 2026, the tree of this release), two per console, the Windows converter's first, **for the
four consoles whose game 1.6.3 does not change**:

| Console | Game stamp of 1.6.2, Windows (Python 3.14) | Game stamp of 1.6.2, Linux (Python 3.13) |
| --- | --- | --- |
| Master System | `b4e9d8b926b55189f2369ea20e6e99123a2ef3b8bbe12ad9a2455c8a9e35f4b2` | `58d4d6ee6bd59653e4815b303a8c332d593b3755419970732171e914d6b0af73` |
| Game Gear | `14ae3fcbdaf43b121500a121128bcae88161279b350a745952ff17e44ae65743` | `0d63e09321860ce6e161b49a24535d13ddc10b5e6d281b91b195ad9472710a6d` |
| Game Boy | `831c25068b495316b763e46ee05a62f4ca4b9a1abbb92692c68979c559406b9a` | `dde2e590f43d5efc0dea2d34ceedee54ee908cdba37d1a1ea6535cde1d6bc1b4` |
| NES | `fa98f9dd4c480eb16ab7e66c491cb52b02100f88631c5f398112a896e79f5ce4` | `6618f7f293fd864e5cc6e3fec4aa89b020e2795593ba924ab30b4e13990b921a` |

Verified the same way and **not listed** (the stamps are kept as evidence, `tests/test_legacy_compat.py` pins them
unlisted, and [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md#release-162-entries-29-october-2026-windows-and-linux)
records them):

| Console | Game stamp of 1.6.2, Windows (Python 3.14) | Game stamp of 1.6.2, Linux (Python 3.13) | Why no entry |
| --- | --- | --- | --- |
| Mega Drive | `ad4dee96cbceb46be2c7cdf200d917586451d53c8abbca0d24c4b6e95a500b85` | `0de9eed2964d4261237a9099334e7bbcad2dead0dab99258674dd0c306b220b0` | the 68000 shifts |
| Super Nintendo | `b6a7c7fd16250e9512258d961d7f2069d8bf6f0988a0be611530219577556d18` | `fa81323602399f6e839ec9a3ee3ba1e0443fe313b5916c46b8a26742bdd55452` | BRK and COP |
| Neo Geo | `aff15893e4d95019cab57539ab28f5438f74613b07e780f2f9412f19b054b838` | `b6d6f5a7ae69485b8b86913241a865b171dcad8cb30ab38ada9dc381b3e62142` | the 68000 shifts |
| CPS-1 | `d4e10fc37d4974cd495d666ac35bb11a29be5a79df2ed3fa8167263f044b54fb` | `4a0de40695a4b51350cf43eb36450211cdff13f785730f1ead61bffc4ae6ea43` | the 68000 shifts |
| Sharp X68000 | `699f09265a9fe722e1cedabd80d711961f8edd8e06385366eb1aa7cc1befab39` | `35980145fc8de1a9afb1b4722831bdbeafb38b097f963532579c412d5f2b2bc2` | `x68_sdk` (below) |

*Why these four are upgraded.* The Game Boy and the NES change no game behaviour (host kit shell, shared helpers, the Linux
resource linking). The Master System and Game Gear change one thing a game could notice, the "functions" engine no longer
calling a paged address directly; the default "banked" engine generates byte-identical sources (checked on Bank Panic), and
a "functions" export that diverges now fails the upgrade recheck and is converted again, which is the precedent written in
COMPILATION_LIBRARY.md ("Validation fixes merged after these entries"): the upgrade rebuilds with the current generator and
rechecks on the quick routes, so upgraded exports get the fix. *Why the others are not.* The 68000 shifts (ROXL and ROXR
with a zero count, ASL.L by 31) and the 65816 BRK and COP change what a game does on those CPUs, and the written rule lists
no console in that case. Their exports of 1.6.2 are converted in full once; a ROM the shared base knows still starts from
its qualified paths, with the quick check (the base is keyed by the pinned upstream revisions, which did not move), so the
cost is the conversion, not the exploration.

- *X68000.* Its request carries `x68_sdk`, a hash of the game stamp of the tree that wrote it and of the machine base, so a
  receipt of 1.6.2 could never be recognised ([history](#exports-of-160-in-161)): an entry would be dead weight, and its
  quick states of 1.6.2 are refused as well ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-162)).
- *Quick states: a separate question from the export upgrade.* Every build of 1.6.3 of the Mega Drive, Super Nintendo,
  Neo Geo and CPS-1 carries the 1.6.2 compatibility key (Windows), so a fully reconverted export accepts the quick states
  of 1.6.2 as an upgraded one would; the key is about the serialized bytes, not about the generated game, and none of them
  moved. The Master System, Game Gear and Game Boy have no key of this kind and load states both ways; the NES key is
  unchanged ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-162)).

**How the stamps were computed.** The `v1.6.2` tag (commit `5bbfe12`, the commit the packaged converters were built from)
exported with an archive of the tag into an empty folder, then `compilation_inputs.role_stamps(system)['game']`, under
Python 3.14.5 on the Windows PC and under Python 3.13.5 (the build virtual environment) on the Linux build host.

**Two converters, two stamps per console.** Code is fingerprinted as bytecode, so the Windows converter of 1.6.2 (built with
Python 3.14) and the Linux one (built with Python 3.13) stamp differently: each listed console lists both, Windows first. Both were
checked against the published converters themselves on 29 October 2026: the `Retro-Recomp.exe` and
`Retro-Recomp-linux-x86_64` assets of the v1.6.2 release (SHA-256 checked against its `SHA256SUMS.txt`) were run with their
internal `_compilation-inputs` command (the Windows one hidden, with no window), and the game, host and build stamps
recomputed from their own input fingerprints equal, on all nine consoles, the stamps of the archive of `v1.6.2` under Python
3.14 (Windows) and 3.13 (the Linux host). Without the Linux entries a Linux export of 1.6.2 would be converted in full. The
check covered all nine consoles, the unlisted ones included, so the stamps recorded for them are verified.

**Evidence, and what is not proved.** No game was converted for these entries and `Export/` holds no receipt written by
1.6.2 for them: the claim rests on the list of changes above and on the published converters' own stamps, not on a receipt
per console. An entry cannot accept a wrong export: a receipt matches only if its game part is the hash of the request with
`engine` equal to the listed stamp, so a stamp the 1.6.2 converter did not write matches nothing and the export is converted
in full as before. What the table cannot show without receipts is that a matching export is equivalent to a reconversion.
Unlike the entries of 1.6.1, one of the changes above can alter what is generated for an upgraded export: the Master
System and Game Gear "functions" engine. The upgrade rechecks the export against the reference on the quick routes and
says so in the report (`upgrade.from_release` = `1.6.2`); a diverging one is converted again. That is not a replay of the
long routes, and it measures neither CPU fidelity, hardware fidelity, gameplay nor physical latency. The consoles whose CPU
behaviour changed (the 68000 shifts, BRK and COP) were taken out of the table rather than argued: the rule lists none of
them.

**Also in this release, host files only.**

- **F2 gamepad combinations from the selected player's pad.** The Quit and Restart combinations of a player's gamepad
  page are captured from that player's own pad only, as the button bindings are since 1.6.2 (divergence 3); a pad of
  another player is ignored and a player without a pad sees "No gamepad for player N". Edited: `native/game_options.h`
  (an optional guard, off unless the host sets it: hosts not on the kit keep taking any pad until they migrate),
  `native/hostkit/shell/rrhk_options.c`, `rrhk_menu.c`, `hostkit/hostkit_internal.h`, all host inputs: the host stamps
  of the consoles that own them move, no game stamp or quick-state key does. Checked on Mega Drive Blockout with
  `tools/hostkit_ab.py pads combo` (two virtual pads: player 2's B ignored while player 1's page waits, then player 1's
  A bound, `quit_pad=1`).

## Exports of 1.6.1 in 1.6.2

*History: since 1.6.3 the entries and keys below are no longer listed by any build ([above](#exports-of-162-in-163)).*

1.6.2 moves the game, host and build stamps of every console, and none of what a game is or does changes with it. The
game-side files that differ from the `v1.6.1` tag are these, and each is a change of what a conversion measures, reports
or builds with, not of what it generates:

- *Timings.* The report gained its `timings` (the time of each phase, [ARCHITECTURE.md](ARCHITECTURE.md), "Report schema
  2"). `batch`, `core`, `console16`, `console16_optimization`, `gameboy`, `nes`, `nes_optimization`, `neogeo_conversion`,
  `cps1_conversion` and `x68000_conversion` wrap their existing steps in `timings.phase(...)`; nothing is skipped or added.
- *Shared base.* The command-line `batch` applies the shared base like the window (`batch`).
- *Quick-state keys.* The 1.6.1 keys join the build as compatibility keys and the 1.6.0 ones are dropped
  (`console16_state`, `neogeo_build`, `cps1_build`; the serialized layout did not change,
  [GAME_STATES.md](GAME_STATES.md#states-written-by-release-161)). `cps1_knowledge.GENERATOR_REVISION` goes from 4 to 5 for
  the same reason as the revision before it: nothing a RAM path could notice moved.
- *NES.* The player shell moves onto the host kit ([below](#nes-exports-of-161-in-162-host-kit-phase-2)): `nes_runtime`
  stages the kit and lists its sources, and `native/console16_video.h` (the kit's video shell includes it) is also owned
  by the NES. The generated sources and the learned paths are the same; an A/B run of the NES shell on Donkey Kong gave
  identical results before and after the move.
- *Packer.* UPX 5.3.0 ([below](#upx-530-packing-a-build-input)): `packing` (build), `licenses/UPX.md` and
  `THIRD_PARTY_NOTICES.md` (host).

The release procedure (the rule above) replaces the entries of 1.6.0 by those of 1.6.1, and only those, in
`LEGACY_GAME_STAMPS` (28 October 2026, the tree of this release):

| Console | 1.6.1 export in 1.6.2 | Game stamp of 1.6.1 (computed from the `v1.6.1` tag) |
| --- | --- | --- |
| Master System | **upgraded**: rebuilt from its paths, rechecked on the quick routes, `upgrade.from_release` = `1.6.1` | `c4589fe7b51645c8fc779fb2511d3dc9c793fa855b5c910089bbdf0cb3dea68d` |
| Game Gear | upgraded | `f860d65789176fa85ad7c7880c766da1754ea98fedac4f50edcf77d664f799cd` |
| Game Boy | upgraded | `e5fc74915974ec27ab05bc9c9ae5ecea03050316ed39d9842b11485d2ffe1e09` |
| NES | upgraded, with the player shell of the host kit | `a8b871f2ab08ffc44633cc562b942fdac9a3cc4d65a7706030b714abf96fa017` |
| Mega Drive | upgraded | `2effe9f498891007f54fadc029a8f55f625ed414c73894fe2cbde5684dcfd188` |
| Super Nintendo | upgraded | `463da5c5cf464363bbc887e524a1933288e9f94c7d748cae624748dc172b6ae4` |
| Neo Geo | upgraded | `1d1a5224f6c89a58ff7f1f79d807918a1c4f1295e0ae3543a253a4d884d2959b` |
| CPS-1 | upgraded | `fb7d9315c9637c103aa81f259712524d9bf29b33e6e9d920ce8f4b5ad83f92db` |
| Sharp X68000 | **converted in full once**: no entry | `428f2fc57bfbd0d11cf3e1bbd7977a967628bc328728746dc784cea0c39241ca` (recorded, not listed) |

- *X68000.* Its request carries `x68_sdk`, a hash of the game stamp of the tree that wrote it and of the machine base, so a
  receipt of 1.6.1 could never be recognised ([history](#exports-of-160-in-161)): an entry would be dead weight.
- *Quick states.* An export of 1.6.1 that is upgraded is rebuilt with the 1.6.1 compatibility key of its console, so the
  quick states of 1.6.1 (Mega Drive, Super Nintendo, Neo Geo and CPS-1, Windows) still resume
  ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-161)).

**How the stamps were computed.** The `v1.6.1` tag (commit `48b1fac`, the commit the packaged converter was built from:
`.build/release-1.6.1/commit.txt`) exported with `git archive` into an empty folder, then
`compilation_inputs.role_stamps(system)['game']` under Python 3.14.5, the Python of the packaged converter and of this tree.
Run the same way on the `v1.6.0` tag, the computation gave the nine stamps of 1.6.0 again, byte for byte, which is the check
that the method and the Python are the ones that produced the entries of the previous table.

**Two converters, two stamps per console.** Code is fingerprinted as bytecode, so the Windows converter of 1.6.1 (built
with Python 3.14) and the Linux one (built with Python 3.13) stamp differently: each console lists both, Windows first. Both
were checked against the published converters themselves on 28 October 2026: the `Retro-Recomp.exe` and
`Retro-Recomp-linux-x86_64` assets of the v1.6.1 release (SHA-256 checked against its `SHA256SUMS.txt`) were run with
their internal `_compilation-inputs` command, and the game, host and build stamps recomputed from their own input
fingerprints equal, on all nine consoles, the stamps of `git archive v1.6.1` under Python 3.14 (Windows) and 3.13 (Hermès,
the Linux build host). Without the Linux entries a Linux export of 1.6.1 would be converted in full.

**Evidence, and what is not proved.** No game was converted for these entries and `Export/` holds no receipt written by
1.6.1: the only schema 3 receipt of 1.6.0 or later there is one Mega Drive game of 1.6.0. The claim rests on the list of
inputs above and on the published converters' own stamps, not on a receipt per console. An entry cannot accept a wrong export: a receipt matches only if its game part
is the hash of the request with `engine` equal to the listed stamp, so a stamp the 1.6.1 converter did not write matches
nothing and the export is converted in full as before. What the table cannot show without receipts is that a matching
export is equivalent to a reconversion. An export of 1.6.1 that is upgraded is rebuilt and rechecked on the quick routes
like any upgrade, and the report says so (`upgrade.from_release` = `1.6.1`); that is not a replay of the long routes, and
it measures neither CPU fidelity, hardware fidelity, gameplay nor physical latency.

## Mega Drive exports of 1.6.0 in 1.6.1

1.6.1 corrects the deferred sound-CPU payment of the Mega Drive runtime (`native/md_z80_bus.inc`, game-side, owned by
`md` only): when the 68000 writes BUSREQ or RESET during the merged final catch-up of a payment that crosses a slice end,
the host checkpoint no longer runs the 68000 a second time before answering the request (Super Street Fighter II
answered a bus request one poll late, which shifted a few YM2612 and PSG writes by 18 68000 clocks). The Mega Drive
game stamp moves for this reason too; the learned paths do not, so the 1.6.0 entry (table above) lets Mega Drive exports
of 1.6.0 be rebuilt with the corrected runtime and rechecked against the reference on the quick routes, like the other
consoles. A rebuilt export therefore runs this one change of timing that its 1.6.0 export did not: the upgrade
rechecks it against the reference on the quick routes, which is not a replay of the long routes. The other consoles do
not own the file, so this change moves none of their stamps (the stamps above move for the packer's notice). The Mega
Drive quick-state key (`RR16_STATE_ABI`) also moves, because it hashes the listed native files of the console; the
serialized layout is unchanged (the two variables the fix touches are read by no other native file, so by no state file), so the release adds the 1.6.0
key as a compatibility key ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-160)).

## NES exports of 1.6.1 in 1.6.2 (host kit phase 2)

1.6.2 moves the NES player shell onto the host kit ([HOST_KIT.md](HOST_KIT.md)): `nes_host_ui.c` and
`nes_audio_output.inc` are replaced by `native/hostkit/shell/rrhk_*.c` (shared with the 16-bit consoles) and the adapter
`native/hostkit/adapters/rrhk_nes.c`. The NES CMake file lists them (staged by `hostkit.stage`, called once from
`nes_runtime.py`). Host stamp of the NES: moves (every kit file, the adapter and `retrorecomp.hostkit` are host inputs).
Host stamp of Mega Drive, Super Nintendo, Neo Geo and CPS-1: moves (the shell gained the callback-ring output and four
per-machine switches). Game stamp of the NES: moves once, because `nes_runtime.py` (game role, owned by `nes`) gained the
staging call and the new source list; the generated sources, the learned paths and the quick-state key
(`RR_NES_STATE_ABI`, which hashes `retro_nes.h`, the state sources and the engine, none of which changed) are
untouched. The 1.6.1 game stamp of the NES is in `LEGACY_GAME_STAMPS` ([above](#exports-of-161-in-162)).

## Exports of 1.6.1 in 1.6.2 (host kit: F2 capture and autofire notice)

Two behaviour decisions of 28 October 2026 land in the kit shell ([HOST_KIT.md](HOST_KIT.md), divergences 3 and 11):
the F2 "press a control" capture accepts the selected player's gamepad only on every console (the NES took any connected
pad; the `capture_any_pad` setting is gone), and F6 shows one shared notice, "Autofire ON" / "Autofire OFF", from the
eight-language catalogue on every console (the NES was silent; its F6 is now the shell's own key, with the same toggle and
the same `[Manettes] autofire` write). Edited files: `hostkit/hostkit.h`, `hostkit/shell/rrhk_events.c` and
`hostkit/adapters/rrhk_nes.c`, all host inputs. The host stamps of the Mega Drive, Super Nintendo, Neo Geo, CPS-1 and NES
move; no game stamp, learned path or quick-state key does. Master System, Game Gear, Game Boy and X68000 were not on the kit
then and kept their own behaviour until they migrated (the X68000 in 1.6.3, the Master System and the Game Gear in 1.6.3 too).

A third decision of the same day, the pad slot policy (divergence 10, D11), lands in the same shell. Pads still go to the
players in plug order by default (Automatic), so an export that is never touched plays exactly as before and writes
nothing new to its preferences. The gamepad page of each player in F2 gains one "Gamepad" row (Enter cycles Automatic,
each connected controller, None; Delete goes back to Automatic): a controller chosen there is pinned to that player,
None leaves the player on the keyboard (a lone pad then drives player 2), and the choice is stored in the player's
gamepad section as `device` (`auto`, `none` or the SDL joystick GUID) and `name` (for display). A pinned controller that
is unplugged leaves its player without a pad until it is plugged in again, and the F2 binding of a player without a pad
says "No gamepad for player N". Five strings join the runtime catalogue in the eight languages (Automatic, None,
"%s (disconnected)", "No gamepad for player %d" and the row's hint). Edited files, all host inputs: `hostkit/hostkit_internal.h`,
`hostkit/shell/rrhk_input.c`, `rrhk_events.c`, `rrhk_menu.c` and `runtime_catalog.inc`. The catalogue is shared by every
shell, so the host stamp of each of the nine consoles moves (checked against the previous tree: the game and build stamps
of all nine stay equal); the same release already moves them, so nothing more is owed to exports of 1.6.1. Learned paths
do not move. The catalogue is also one of the native files the quick-state key of the 16-bit consoles hashes, so the Mega Drive
and Super Nintendo keys move too (the serialized layout does not). The state-key rollover is done in this tree: the
1.6.1 keys of the Mega Drive, Super Nintendo, Neo Geo and CPS-1 are the compatibility keys (Windows) and the 1.6.0 ones
are dropped; the Super Nintendo, which had not moved since 1.6.0, has its first compatibility line, and the Neo Geo and
CPS-1 keys move with the edit of `neogeo_build` and `cps1_build` that the rollover is
([GAME_STATES.md](GAME_STATES.md#states-written-by-release-161)). Exports of 1.6.1 keep their existing `[<Console>.Gamepad.PlayerN]`
keys: the two new keys are read when present and ignored otherwise. When Master System and Game Gear move to the kit this
row replaces their first-player toggle and pad swap.

## X68000 exports in 1.6.3 (host kit phase 3)

1.6.3 moves the X68000 player shell onto the host kit ([HOST_KIT.md](HOST_KIT.md#phase-3-the-x68000-163)): `player_ui.inc`
is replaced by the adapter `native/hostkit/adapters/rrhk_x68k.inc`, which `reference_host.c` includes, and by the kit's
shell, which `native/x68000_reference/CMakeLists.txt` compiles from the tree (the X68000 export is built from the
repository: no staging call, `retrorecomp.hostkit` is not one of its inputs).

*Stamps* (computed from the tree of the tag `v1.6.2` and from this tree with `compilation_inputs.role_stamps`, Python 3.14):

| | game | host | build |
| --- | --- | --- | --- |
| Sharp X68000, 1.6.2 | `699f09265a9fe722e1cedabd80d711961f8edd8e06385366eb1aa7cc1befab39` | `313288846e5d0a842654f46cdad246a075586313ef599e9db83000f3a32cbd80` | `e84c6e39d05d7f47ac5e0a51a2b676351cef673e855923b3bbb276597279a255` |
| Sharp X68000, 1.6.3 | `94d006e26fef109b506c49596446962f687ede9d4817231d3694e66dc79b536f` | `84ab517744f9e12ff2b2be18fe06b7f7c8144a54dd71e5e8f9be7cff8abe1d6e` | unchanged |

- *X68000 game stamp: moves.* `reference_host.c` (the frontend that owns the core, game role) lost its window, picture, sound
  and pad code and gained the frame function, its CMake file lists the kit, `x68000_conversion.py` names the new adapter in a
  docstring, and the X68000 now owns `console16_video.h` (the kit's video shell includes it). The SDK stamp (`x68_sdk`)
  follows. As in every release the X68000 has no entry in `LEGACY_GAME_STAMPS`: an export of 1.6.2 is converted in full once.
  What a conversion generates (the guarded CPU, the learned paths, the media session) is unchanged.
- *X68000 quick-state key: moves.* `RR_X68K_STATE_ABI` hashes `reference_host.c`. A quick state written by an X68000 export
  of 1.6.2 is refused by the export of 1.6.3, as between any two releases ([GAME_STATES.md](GAME_STATES.md)). The state file
  layout, its host auxiliary block and its media section are unchanged.
- *X68000 quick states carry no heap content.* `new MyOPM()` (the FM chip of the pinned fmgen) returned storage that fmgen's
  constructors and `Reset` only partly write, and the serializer saves those members: up to 512 bytes of the 5,207-byte OPM
  section of a 19.4 MB state (4 to 16 bytes in each operator) took whatever the heap held, so two states of one game and moment
  could differ in a window of about 1.7 KB, with leftovers of the process (environment text among them) inside. The chip is
  now allocated zeroed (`tools/x68000_base74.py`, `adapt_fmg_wrap`: a class-specific `operator new`); the layout and the size
  of the state are unchanged. Stamps moved by this change alone: the X68000 game stamp (and its engine stamp) and the SDK stamp;
  the X68000 host and build stamps and every stamp of the other eight consoles are unchanged. The X68000 quick-state key moves
  too (`RR_X68K_STATE_ABI` hashes `tools/x68000_base74.py`), which the release already needs (above). Nothing else of the X68000 payload
  depends on uninitialised memory (the only bytes that follow the chip's initial storage are the ones above, measured by filling
  it with `0xA5`). The writers of the other consoles were read for the same pattern: they write field by field or from zeroed
  static objects, except that the NES state header (`nes_machine_state.inc`, two padding bytes of an automatic `= {0}` struct)
  and the CPS-1 Z80 block (`cps1_machine.c`, a struct copy) dump structs whose padding is zero in practice and not by guarantee;
  they are left alone, because fixing them would move those consoles' state keys.
- *Host stamps: move* for the Mega Drive, Super Nintendo, Neo Geo, CPS-1, NES and X68000 (the shell gained twelve
  per-machine fields and hooks, all optional). *Game and build stamps of the other eight consoles: unchanged* (checked
  against the tree of the tag). Learned paths do not move.
- *Behaviour.* The X68000 follows every rule decided for the other consoles ([HOST_KIT.md](HOST_KIT.md): stick dead zone
  16000, one autofire behaviour with the shared notice, F2 capture from the selected player's pad, the Gamepad row, F8/F9 at
  a safe boundary, one set of window titles). Its preferences keep their layout, and the files written by the old and the new
  host are identical on the measured script.

## Master System and Game Gear exports in 1.6.3 (host kit phase 4)

1.6.3 moves the player shell of the Master System and the Game Gear onto the host kit ([HOST_KIT.md](HOST_KIT.md#phase-4-the-master-system-and-the-game-gear-163)):
`host.c`, `controls.c/.h` and `ui.c/.h` are replaced by the shared shell and the one adapter `native/hostkit/adapters/rrhk_sms.c`.
`native/CMakeLists.txt` compiles them from the folder `core.prepare_native_source` fills (`hostkit.stage(native_source, "sms")`).

*Stamps* (from the tree of the tag `v1.6.2`, from the tree this phase started on (`af0716c`) and from this tree, `compilation_inputs.role_stamps`, Python 3.14):

| | game | host | build |
| --- | --- | --- | --- |
| Master System, 1.6.2 | `b4e9d8b926b55189f2369ea20e6e99123a2ef3b8bbe12ad9a2455c8a9e35f4b2` | `2850d1e1d883a22316cf339392391901ccf186315f0b9bd170cff80b32f5521f` | `61b3ff1284fcf75b79309f140d5c68ed04fb0cc038c443a9176606d9bfd96b9e` |
| Master System, before phase 4 | `6f6624c302d304e014d4c39594c5d6052d12d48a1403b1b995404768462829ad` | `b5eb5b92abbcffc3b6f9bc4947732b32100a7335cfb1d01f890dea7076698149` | unchanged |
| Master System, 1.6.3 | `1b4765ba8c29a21f45c9307aff566854be012fb2bb77adbddbd4c4e20dcb65d0` | `4313934b46e394b8f167e14d3f14e53c63af84b58ea6484f46196f1dab06b55a` | unchanged |
| Game Gear, 1.6.2 | `14ae3fcbdaf43b121500a121128bcae88161279b350a745952ff17e44ae65743` | `65142a4a567014d54340db35ddd33a96abe3028d36a352f137908fce31ddb696` | `99adc3982e7e8255bc3ebcb7fad103a94814dd218893a78549f2c5e0a72d5fbb` |
| Game Gear, before phase 4 | `23ab9843540311e258ebaebf69676f26170147ed142bab4a018254a4c776068d` | `f3e2d3f7644ddeaa7e0049f111b4d74d9e4dad48a50096fc52afce237d1c9558` | unchanged |
| Game Gear, 1.6.3 | `420edf15cd4e548cffe07cf662e3675346006d838a95ce1a805490e9e4e4f90e` | `d89b2f71f96de1240403d6909b70852433d117a45bc0dcedda53dbf67dce2835` | unchanged |

- *Game stamp: moves, as it already had since the tag (for every console).* This phase edits `retrorecomp/core.py` (the staging call;
  owned by every console), `native/CMakeLists.txt` (the source list; owned by every console, used by these two), the two profiles
  (`host_adapter`) and the kit's shared game-role header; the game stamp of every console moves with them. **What a conversion
  generates for these two consoles did not change**: the generated sources, the learned paths and the guest runtime are produced by code
  this phase did not touch, and two conversions (Bank Panic, Pac-Attack) with the tree before and after it ran the same guest. The 1.6.2
  game stamps above are the candidates for `LEGACY_GAME_STAMPS` at the release, the procedure being the one of the other consoles
  (build-only evidence: not entered in this phase).
- *Quick-state key: none.* These two consoles have no key of this kind: the state header carries the ROM's SHA-256, the state schema and
  the hardware model, and `gamestate.inc` and the state path are untouched. The state file written by the new host is byte for byte the one the
  old host writes (Bank Panic and Pac-Attack, same script), and each host loads the other's. A quick state of an export of 1.6.2
  therefore loads in an export of 1.6.3 and the reverse.
- *Host stamps: move* for every console (the shell gained the driven mode, the Pause menu, the window set and the other fields; `host.c`,
  `controls.c/.h` and `ui.c/.h` left every host stamp). *Build stamps: unchanged.* Learned paths do not move.
- *Behaviour.* The Master System and the Game Gear follow every rule decided for the other consoles (stick 16000, one autofire behaviour
  with the shared notice, F2 capture from the selected player's pad, the Gamepad row instead of the first-player toggle and the C swap,
  deferred states, the Windows hint set, whole-pixel placement, one set of window titles). *Preferences:* the new English keys are
  written; the French keys of earlier releases (and `SMSRecomp.ini` while `Retro-Recomp.ini` does not exist) are still read where the new
  key is absent and are never deleted, so settings of 1.6.2 keep their meaning. A game of 1.6.2 does not see a binding changed afterwards in
  1.6.3 (it reads its own keys). Every window now keeps whole pixels in the window mode too ([HOST_KIT.md](HOST_KIT.md), divergence 9): a Mega Drive,
  Super Nintendo, Neo Geo, CPS-1, NES or X68000 export no longer stretches its picture to the window.

## Game Boy exports in 1.6.3 (host kit phase 5)

1.6.3 moves the player shell of the Game Boy onto the host kit, the last console to move ([HOST_KIT.md](HOST_KIT.md#phase-5-the-game-boy-163)):
the window, menus, bindings, controllers, sound device and pacing of the pinned runtime's `platform_sdl.cpp` are replaced by the shared shell
and the adapter `native/hostkit/adapters/rrhk_gb.inc`, which the patched platform file includes. `gb_menu.inc`, `gb_audio_output.inc`,
`gb_input_refresh.inc` and `retrorecomp/gameboy_timing.py` leave the stamps; `native/hostkit/adapters/rrhk_gb.inc` joins them (host).

*Stamps* (from the tree of the tag `v1.6.2`, from the tree this phase started on (`d7a15c3`) and from this tree, `compilation_inputs.role_stamps`, Python 3.14):

| | game | host | build |
| --- | --- | --- | --- |
| Game Boy, 1.6.2 | `831c25068b495316b763e46ee05a62f4ca4b9a1abbb92692c68979c559406b9a` | `e0774f929efa44df3008d132e955584a6a0bba525b6780362f64106ee11aa332` | `a95276b71c11e78625c3d29ba0d915c131f6c40e5da9d093093212e6acf21e78` |
| Game Boy, before phase 5 | `e4c34929f604d05cbe67169ef51afa2833a64133e5def5ff584492c5b831a35a` | `ed43b3b0bcb22fd410d3d248114915019568f1c02cfa1935fefaebbda4fe8468` | unchanged |
| Game Boy, 1.6.3 | `3bf96fc61783d4fcab9b8d0ce94978b538a97297401645339ba229016c34e641` | `d05d23beb298661d00b2a6cb67e8ddc7978ce7405fd6914210c80e9c978d3ea3` | unchanged |

- *Game stamp of the Game Boy: moves.* `gameboy_runtime.py` (game role) stages the kit and lists its shell in the project's CMake file, and
  the Game Boy now owns `console16_video.h` (the kit's video shell includes it). **What a conversion generates is unchanged**: the generated
  sources, the learned paths, the guest runtime and the guest side of the JOYP refresh are produced by code this phase did not touch (two
  conversions, Kirby's Block Ball and Super Mario Land, with the tree before and after run the same guest and validate as before). The
  1.6.2 game stamp above is the candidate for `LEGACY_GAME_STAMPS` at the release, by the procedure of the other consoles (build-only
  evidence, not entered in this phase).
- *Quick-state key: none.* The Game Boy has no key of this kind: its state file is the runtime's, unchanged. A state written by an
  export of 1.6.2 loads in an export of 1.6.3 and the reverse (checked both ways on two games); the two files differ by seven bytes of
  frame-boundary bookkeeping, because the new host takes the state between two frames (decision D6) where the old one took it in the middle
  of one when the slice ended there.
- *Host stamps: move* for every console (the shell gained the stereo ring, three per-machine fields and the audio start-up rule of a driven
  machine; the Game Boy's shell files left every host stamp). *Build stamps: unchanged.* The game stamps of the other eight consoles are
  unchanged (checked against the tree this phase started on). Learned paths do not move.
- *Behaviour.* The Game Boy follows every rule decided for the other consoles (stick 16000, one autofire behaviour with the shared notice,
  F2 capture from the selected player's pad, the Gamepad row, F8/F9 at a frame boundary, the Windows hint set, whole-pixel placement,
  one set of window titles, the callback ring of the kit). **Preferences:** the new English keys are written to
  `datas/Retro-Recomp.ini` (`[GameBoy.Keyboard.Player1]`, `[GameBoy.Gamepad.Player1]`, `[GameBoy.Video]`); the flat
  `datas/Retro-Recomp-GameBoy.ini` of 1.6.2 and before is read where the kit's key is absent (display mode, filter, palette, language,
  autofire, the first binding of the eight buttons) and is never written or deleted, so settings of 1.6.2 keep their meaning; a game of
  1.6.2 does not see a binding changed afterwards in 1.6.3 (it reads its own file). **Retired** (they had no page and no mention in the
  documents): the second binding of each action (the shoulders were also A and B). The fast-forward and maximum-speed keys, the mute
  key, the volume and the output-device choice, retired by the first version of this phase, are back as features of every console (the
  next section). Opposite directions cancel in the pad word instead of both reaching the cartridge. The
  start-up reserve, the 256-sample period and the 10 ms margin of the sound are the Game Boy's own, as before.

## Sound and speed controls of every console in 1.6.3 (host kit decision D12)

The fast-forward (Tab held, right trigger, 250%), the maximum-speed toggle (backquote, left trigger, 500%), the mute (M), the volume
(0 to 200%) and the output-device choice that only the Game Boy had before 1.6.3 are now features of the shell, on all nine consoles
([HOST_KIT.md](HOST_KIT.md#d12), [CONTROLS.md](CONTROLS.md#speed-and-sound)). Only the pacing changes; the sound is dropped while the speed
is not 100%.

- *Edited, all host inputs:* `native/game_options.h` (the sound stage, the options rows, the device cycle), `native/hostkit/hostkit.h`,
  `hostkit_internal.h`, `shell/rrhk_audio.c`, `rrhk_events.c`, `rrhk_input.c`, `rrhk_main.c`, `rrhk_menu.c`, `rrhk_options.c`,
  `rrhk_ring.c`, the adapters `rrhk_md.c`, `rrhk_sms.c`, `rrhk_gb.inc`, `native/audio_output.inc` (Master System and Game Gear output)
  and `retrorecomp/megadrive_audio.py` (the Mega Drive engine's sound callback), `native/runtime_catalog.inc` (ten new strings in
  every language, from `assets/locales`). **Host stamps: move** for every console. **Game stamps and build stamps: unchanged**; the learned
  paths do not move. **Quick-state keys of the 16-bit consoles: move**, because they hash `runtime_catalog.inc`; they already move
  in 1.6.3 (the catalogue of this release), so no further break. The Game Boy has no such key.
- *Behaviour with the new keys untouched:* the same. The volume is 100%, the mute off, the device the system default, the speed 100%;
  at those values the sound stage leaves the samples as they are, byte for byte, and the pacing is the expression it was. Checked on Mega
  Drive Blockout, Master System Bank Panic and Game Boy Kirby's Block Ball with `tools/hostkit_ab.py` (HOST_KIT.md, "D12").
- *Mega Drive:* the engine's own sound callback now calls the shell's stage, which also makes the **audio filter** row of F2 work there
  (it was offered on the Mega Drive, but its callback never applied the filter). An export of 1.6.2 with `audio_filter` set in
  `[MegaDrive.Options]` therefore sounds filtered after the upgrade, as the row says.
- *Preferences:* new keys `audio_volume`, `audio_muted` and `audio_device` under `[<Console>.Options]`. A Game Boy export of 1.6.2 keeps
  its volume, mute and output device: `audio.volume_percent`, `audio.muted` and `audio.device_name` of the flat
  `datas/Retro-Recomp-GameBoy.ini` are read where the new keys are absent (never written, never deleted).
- *Behaviour notes of the sound stage:* a volume, mute or output-device choice applies even if `datas` cannot be written (the page says
  "Config unavailable"); an unplugged output is replaced by the default on every console, the Master System, Game Gear and Mega Drive
  included; at most 32 output devices are offered. Edited for this (host inputs): `audio_output.inc`, `rrhk_audio.c`, `rrhk_events.c`,
  the adapters `rrhk_md.c` and `rrhk_sms.c`, `megadrive_audio.py`.
- *Fixes of the review of phase 5, same release:* a menu or the Pause menu stops a guest that owns the loop (Game Boy, Master System,
  Game Gear) even while a quick-state request waits for its safe boundary (the Game Boy can wait many slices with the LCD off); the Game
  Boy's reset forgets the held autofire buttons as a state load does.

## CPU fixes carried from the upstream review in 1.6.3

The review of the pinned upstreams of 29 October 2026 ([UPSTREAMS.md](UPSTREAMS.md)) brought fixes that 1.6.3 carries as our
own patches on the **same pinned revisions**: the base of qualified paths, keyed by those revisions, stays valid. Each fix is
written from the processor's manual, not copied from the upstream change. They are **CPU fidelity** fixes only: native code,
hardware fidelity, gameplay validation and latency are not measured by them.

- **68000 (Mega Drive, Neo Geo, CPS-1, X68000): shifts at the edges.** ROXL and ROXR with a register count of zero
  (modulo 64) now load C from X, X unchanged, as the MC68000 manual says (C was cleared); ASL.L by 31 computes its
  overflow mask in 64 bits, so V is 0 when the sign never changes (the 32-bit shift was undefined in C and set V on
  $FFFFFFFF). The shared core text (`m68000.adapt_semantics`) feeds the native code and the fallback interpreter of the
  four machines. *Edited:* `retrorecomp/m68000.py` (a game input of the 68000 family). **The `md`, `ng`, `cps1` and `x68`
  game stamps move**. Because this changes what a game does on these CPUs, their 1.6.2 exports are converted in full,
  not upgraded (`LEGACY_GAME_STAMPS` lists no 1.6.2 entry for them; [Exports of 1.6.2 in 1.6.3](#exports-of-162-in-163)).
  This fix moves no host or build stamp, no quick-state key and not the base; `cps1_knowledge.GENERATOR_REVISION` stays 6 (already raised in 1.6.3; its comment names both causes).
  Checked against Musashi on the Neo Geo (`tools/neogeo_m68000_selftest.py`: 672 edge comparisons with X=1 and counts 0,
  17, 31 and 64 for ROXL.W, ROXR.W, ROXR.L and ASL.L; 98 differed before the fix), with 834 SingleStepTests vectors
  replayed on the native and the reference paths (`tests/fixtures/m68k-shifts`, MIT), and by conversions of Blockout,
  NAM-1975, 1941 and R-Type (0 interpreted instructions on the tested routes). The timing of register-count shifts stays
  the pinned core's fixed estimate ([UPSTREAMS.md](UPSTREAMS.md#deferred)).
- **Super Nintendo: BRK and COP.** A BRK in native mode now costs 8 cycles (the bank register K is stacked), 7 in emulation
  mode; COP follows the mode (in emulation mode: no K stacked, 7 cycles, vector $FFF4). One corrected source
  (`snes_codegen.read_core`) feeds both the operation bodies compiled natively and the interpreter copy of the project.
  *Edited:* `retrorecomp/snes_codegen.py`, `console16.py` (game inputs). **The `snes` game stamp moves**: SNES exports of
  1.6.2 are converted in full, not upgraded, for the same reason as the 68000 consoles. This fix moves no host or build
  stamp, no quick-state key and not the base. Checked by `tools/snes_native_selftest.py` (BRK and COP in both modes, native against the reference, LoROM and HiROM)
  and a Super Mario World conversion (0 interpreted opcodes on the tested routes). Hardware NMI and IRQ entry needed no
  change: the adapter's own entry (`rr_snes_cpu_interrupt`, since 1.0.0) already follows the mode (bank stacked only in
  native mode, 7 cycles in emulation mode and 8 in native, vectors `$FFFA/$FFFE` or `$FFEA/$FFEE`), checked in both modes
  by `native/snes_bus_checks.c`.
- **Master System and Game Gear, "functions" engine: no direct call to a paged address.** The generator no longer turns a
  call or jump to an address at or above $0400 into a direct C call when its static walk saw one bank variant only: the
  call goes through the dispatch, which checks the bank mapped at that moment. Only the fixed first KiB is called directly.
  *Edited:* `retrorecomp/core.py` (`patched_generator_source`; the translator rebuilds itself, its patch marker changes).
  **The `sms` and `gg` game stamps move.** The default "banked" engine generates byte-identical sources (checked on Bank
  Panic); "functions" exports are rebuilt. Bank Panic converts and validates as before; Alex Kidd in Miracle World and
  Factory Panic fail with the "functions" engine exactly as before the fix.

Found by the Linux check of 1.6.3 on the same day, no player-visible change on Windows:

- **Game Boy on Linux:** the embedded resources (`embedded_resources.c/.S`) are linked into the `gbrt` library, whose shell
  reads them, instead of the game target (`retrorecomp/gameboy_runtime.py`, a game input: **the `gb` game stamp moves**, on
  both systems). The program is the same.
- **X68000:** a failed validation replay's error output is read as UTF-8 instead of the system's code page
  (`retrorecomp/x68000_conversion.py`): only the text of that error message changes.
- **Super Nintendo:** the MSVC spelling of the `PpuPixelPrioBufs` alignment is applied by one function,
  `console16.snes_ppu_header`, for the converter and the self-tests; the converter's output is unchanged.

## UPX 5.3.0 (packing, a build input)

1.6.2 bundles UPX 5.3.0 (released on 28 October 2026) instead of 5.2.1: `assets/tools/upx.exe` and
`assets/tools/upx-amd64_linux` are the unmodified official builds, checked by SHA-256 against the release assets
(`retrorecomp/packing.py`, `licenses/UPX.md`), and the corresponding source archive in `licenses/` is the 5.3.0 one. The
release contains the fix of [upx/upx issue 18937](https://github.com/upx/upx/issues/18937), the `compressed data violation`
that made Linux games such as the Neo Geo Metal Slug 3 publish unpacked. `packing` is a build module, so the **build stamp
of every console moves**: an export of 1.6.1 is rebuilt from the paths it already learned, rechecked on the quick routes
and packed by the new UPX, like any export whose build changed. The host stamps move too (`licenses/UPX.md` and
`THIRD_PARTY_NOTICES.md` are host inputs); the game stamps do not move for this reason. The Linux fallback (a game UPX cannot pack and test is published unpacked, with the reason in the log and the report) stays as a
safety net; with 5.3.0 the known case is gone: converted on Debian 13 (Hermès) from the 1.6.2 tree on 28 October 2026,
Metal Slug 3 is published packed (78,492,880 bytes unpacked, 45,086,824 packed, UPX 5.3.0 -9), `upx -t` passes on it and
its five packed replays match the reference.

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
