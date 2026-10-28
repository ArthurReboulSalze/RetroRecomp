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
  shown to differ from release N only in how the game is built. The release procedure replaces the entries, it never
  adds to those of an older release. The table was empty in the tree of 1.6.0; the tree of 1.6.1 lists the stamps of 1.6.0
  ([below](#exports-of-160-in-161)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1.
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
  (limit 0) marks FAIL; the upgrade neither adds nor removes any. The upgrade report keeps the scan level of the export's own discovery, read from `scan_level`, `scan.level` or `advanced_scan.level` (the Mega Drive, Super Nintendo and NES reports of 1.5.x only have the last), so an Extended or Thorough export of 1.5.6 stays one after an upgrade. Quick states: the Mega Drive, Neo Geo (both added in this work) and CPS-1 exports upgraded from 1.5.6 load the quick states written by the 1.5.6 export on Windows, the Super Nintendo ones do not ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-156)).

Measurements stay separate: this is native code, CPU fidelity against the fresh reference on the quick routes and the identity
of the generated game; it says nothing about hardware fidelity, gameplay or latency. A Linux 1.5.6 export is not covered (the
stamps are bytecode digests of Python 3.14.5, the Linux converter is built with another Python).

## Exports of 1.6.0 in 1.6.1

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

## Exports of 1.6.1 in 1.6.2 (to complete at the release)

Step 0 of the faster known-game conversions adds the time of each phase to the
report (`timings`, [ARCHITECTURE.md](ARCHITECTURE.md), "Report schema 2"). It
generates nothing differently and checks nothing differently, but it edits
game-side modules: `batch`, `core`, `console16`, `console16_optimization`,
`nes`, `nes_optimization`, `gameboy`, `neogeo_conversion`, `cps1_conversion`
and `x68000_conversion` (and `packing`, a build module), so the game and build
stamps of the nine consoles move. `neogeo_build`, `neogeo_codegen`, `neogeo_z80`,
`cps1_build`, `cps1_codegen`, `console16_state` and the Super Nintendo modules
that the quick-state keys hash are not touched, so no state key moves. Like the
entries for 1.6.0, the 1.6.1 game stamps go into `LEGACY_GAME_STAMPS` at the
release, computed from the tag.

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
untouched. The release procedure decides whether the 1.6.1 game stamp of the NES joins `LEGACY_GAME_STAMPS`.

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
| Sound output after the emulated mixer | `audio_filter.h`, `audio_cushion.h`, `audio_output.inc`, `gb_audio_output.inc`, `hostkit/shell/rrhk_ring.c`, `md_audio_loop.inc`, `md_audio_resample.inc`, `megadrive_audio.py` |
| Artwork, metadata, publishing | `artwork.py`, `cover_*.py`, `metadata.py`, `languages.py`, `publishing.py`, `windows.py`, `licenses/*.md`, `THIRD_PARTY_NOTICES.md`, application icons |
| Checks of the above | `game_options_checks.c`, `language_checks.c`, `xbr_checks.c`, `display_settings_checks.c`, `icon_checks.c`, `audio_checks.c`, `nes_audio_checks.c` |

Each machine family has one shell for its window, menus and input:

| Machine | Shell (host) | Entry used by discovery and validation (game) |
| --- | --- | --- |
| Master System, Game Gear | `host.c`, `ui.c/.h`, `controls.c/.h` | `launcher.c` and the Z80 runtime |
| Game Boy | `gb_menu.inc`, `gb_input_refresh.inc`, `gameboy_host.py`, `gameboy_timing.py` | `game_main.c`, `gameboy_runtime.py` |
| Mega Drive, SNES, Neo Geo, CPS-1, NES | the host kit: `native/hostkit/shell/rrhk_*.c` (shared) and `native/hostkit/adapters/rrhk_<machine>.c`, copied by `hostkit.py` | `console16_main.c`, `neogeo_main.c`, `cps1_main.c`, machine adapters; for the NES, the runner adapted by `nes_runtime.py` |
| Sharp X68000 | `x68000_reference/player_ui.inc` | `x68000_reference/reference_host.c` and the SDK |

Files that are used both by the shell and by headless checks stay game-side:
`platform_io.c/.h` (quick-state files), `embedded_resources.h`, the
machine adapters `cps1_host.c` and `neogeo_host.c` (input and state
mapping), and every CPU, video, sound-chip, timing, learning and validation
file. Since 1.2.8 the Game Boy shell patches live in `gameboy_host.py`,
separate from the runtime patches in `gameboy_runtime.py`; the guest-side
JOYP refresh hook moved from `gameboy_timing.py` to
`gameboy_runtime.adapt_input_refresh_hook`. The generated Game Boy project is
byte-identical before and after that split.

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
