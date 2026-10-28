# Shared compilation knowledge

## Build inputs, and exports of an earlier release that stay upgradable (1.5.0)

Every input that shapes an export is fingerprinted (`retrorecomp/compilation_inputs.py`)
and falls in one of three roles:

| Role | Examples | A change means |
| --- | --- | --- |
| game | translators, CPUs, video, sound, learning, validation, the CMake files of a game | full conversion |
| host | menus, text, fonts, filters, icons, notices | upgrade: rebuilt from the learned paths, quick routes |
| build | `retrorecomp/toolchain.py`: which C toolchain builds the game and with which options; `retrorecomp/packing.py`: how the finished executable is packed (UPX) | upgrade, like a host change |

The **build** stamp goes into the host part of the receipt (`build_inputs` in
`freshness.HOST_SETTINGS`), so changing the compiler, its options or its pinned
versions rebuilds and rechecks the exports without rediscovery. It never touches the
game part.

### Packing is a build input (1.5.0, Linux compression)

`retrorecomp/packing.py` packs the validated executable with the bundled, unmodified
UPX 5.2.1 just before it is published. UPX restores the same program in memory before
it starts; it never chooses which guest code is discovered, translated or validated.
Neo Geo and CPS-1 also replay their routes on the packed executable and compare it with
the reference, so a packing that changed the game would fail there. Until 1.5.0 the module
was game-side by default (every unlisted module is), and turning on Linux compression would
have converted every export in full. It is now in `BUILD_MODULES`, beside the toolchain:

- a later change of packing (another UPX version, other flags, another console packed)
  rebuilds and rechecks the exports on the quick routes, like any build change;
- release 1.4.1 receipts are still accepted through their frozen `LEGACY_GAME_STAMPS`:
  the legacy hash replaces today's game stamp with the listed one, so it does not depend
  on where packing is classified (`tests/test_legacy_compat.py`,
  `LegacyReceiptTests.test_exports_of_release_141_are_upgraded_not_reconverted_on_each_listed_console`;
  `PackingBuildRoleTests` checks that a packing change moves only the build stamp, for every
  console);
- receipts written by unreleased 1.5.0 builds made before this change are converted in full:
  `compilation_inputs.py` is itself a game-side input and changed with this classification.
  No published release wrote such receipts.

Observed on Debian (25 October 2026, one game per console: Master System, Game Gear, Game Boy,
NES, Mega Drive, Super Nintendo, Neo Geo, CPS-1; quick scan level). Exports of the commit before
this change were converted in full by it, as expected (8/8, not upgraded), now compressed. A
copy of this tree whose only difference was a packing constant then **upgraded** those 8
compressed exports without rediscovery (quick checks, 8/8 `upgraded`, zero interpreted
instructions) and rebuilt them byte for byte (the NES export differs by its project-path state
key only, since the tree's folder differed). Sizes and the other checks are in
[BUILDING.md](BUILDING.md#linux-game-compression).

A Linux game that UPX cannot pack and test is published unpacked (1.6.0, see
[BUILDING.md](BUILDING.md#linux-game-compression)). The change is in `packing.py` only, so it
moves the build stamp of every console and no game or host stamp
(`PackingBuildRoleTests`): `LEGACY_GAME_STAMPS` is untouched. The callers were left alone for
that reason. For Neo Geo and CPS-1 the executable replayed against the reference is then the
unpacked one, and the conversion report's `packing` record (`packed` false, `unpacked_reason`)
is what says so; the build's `native-validation.json` still reads `validated_candidate:
packed` for Neo Geo, and the message reaches the command-line output but not the interface
log. Routing both needs a change in game-side modules, which moves every game stamp: done
with a release that changes them anyway.

The X68000 was packed on Linux afterwards, a change of `packing.py` only (another console
packed). Same machine and day, quick scan level, the same user IPL and font ROM: the
uncompressed exports of Active Shoot (Satou Kouji) (disk SHA-256
`50503f58a64f48f39f37d1bc22796eb5f9fd5541ba1ec1ace3b1d1b655b8ddb0`) and Alien Syndrome
(Dempa) (`8fa632f082c4330f20349604977dc3ac3e59e8a292b6e390d08a07356209e030`) made by the
commit before were **upgraded** by it without rediscovery (2/2 `upgraded`, zero interpreted
instructions), and the upgraded, compressed executables are identical to those of a full
conversion by the same commit.

Linux exports of 1.4.1 are not expected to be covered by `LEGACY_GAME_STAMPS`, before or after
this change: the stamps were reproduced from Windows receipts (Python 3.14.5), code fingerprints
are bytecode, and the Linux converter is built with Python 3.13 (not checked with a real Linux
1.4.1 receipt).

### `LEGACY_GAME_STAMPS`

Release 1.5.0 changes game-side files only to build with the portable tools
(llvm-mingw, CMake, Ninja) instead of Visual Studio: toolchain selection, Ninja build
folders, clang-only branches of the CMake files, the compiler in the report, notices of
the statically linked runtime, and the removal of the unused Super Mario World path.
Without further care every 1.4.1 export would be converted in full. Instead
`compilation_inputs.LEGACY_GAME_STAMPS` lists, per console, the game stamp of
release 1.4.1, followed by the ones of releases 1.5.1, 1.5.2 and 1.5.6 where a real receipt confirmed
them ([1.5.1](#release-151-entries-25-october-2026-windows),
[1.5.2](#release-152-entries-26-october-2026-windows),
[1.5.6](#release-156-entries-27-october-2026-windows)). The Super Nintendo has no entry any
more since its engine changed after 1.5.2 (see the 1.5.2 part), and neither has the **Neo Geo** since 1.6.0 (see
[Stage B3](#stage-b3-the-conversions-follow-the-module-27-october-2026)). A receipt whose game part equals the
hash computed with one of these stamps is accepted by `freshness.upgradable()` as the same
game part:

- it is **never current**: it is always rebuilt with the current tools and rechecked on
  the quick routes, with the report's `upgrade.from_release` set to the release that wrote
  it (`1.4.1`, `1.5.1` or `1.5.2`);
- if the rebuild or its checks fail, `batch._convert_one` says so
  ("did not pass its checks … converting the game in full instead") and converts the game
  in full; the earlier executable stays in place until something has passed;
- other settings still count: the knowledge stamp, the scan level, the video standard,
  new gameplay hints (a receipt with new hints is not upgraded).

How the stamps were found and checked:

1. computed from the `v1.4.1` tag with the release's Python (3.14.5):
   `role_stamps(system)['game']` for each console;
2. for each console, one export was made by the released `Retro-Recomp.exe` 1.4.1 in a
   separate workspace; this branch's own `convert` path, asked about that export with the
   tag's stamp as the only legacy entry, reproduced the receipt's game part exactly
   (Master System, Game Gear, Game Boy, NES, Mega Drive, Super Nintendo, Neo Geo, CPS-1).
   A console without such a receipt has no entry and keeps the full conversion. That is the
   case of the **X68000**: its request also carries an SDK stamp (`x68000_conversion.sdk_stamp`)
   computed over the files bundled in the executable, which could not be reproduced from the
   tag, so its exports are converted in full once;
3. the game-side files that differ between the tag and 1.5.0 were reviewed one by one
   (list in the release notes of the work) and the exports of both toolchains were
   compared frame by frame (CPU, memory, image and sound hashes) on 16 games before
   the list was accepted.

Quick states of upgraded exports (checked with the real 1.4.1 executables against their
upgraded exports, a state written by the old one being resumed by the new one):

- Mega Drive, Super Nintendo, Neo Geo and CPS-1: the state key covers native files, the
  repository list or Python module fingerprints, all of which changed, so the 1.4.1 key is
  added to the accepted keys (`RR16_STATE_COMPAT_ABI_23` for Mega Drive, `RR16_STATE_COMPAT_ABI`
  for Super Nintendo and CPS-1, `RR16_STATE_COMPAT_ABI_3` for Neo Geo). The 1.4.1 keys were found in
  the released executables and reproduced from the tag. States are written field by field with
  the same sizes in both builds; frame-by-frame traces of the old and the upgraded executable are
  identical.
- NES: the key covers the engine files as written in the player's project folder, including
  its path, so it is the same before and after the upgrade in the same workspace (checked: the
  tag and this branch give the same key for the same path, and that key is in the released
  executable). It never moved between workspaces.
- Master System, Game Gear, Game Boy: the state header holds the ROM identity, a schema number
  and sizes; the state code is byte for byte the one of 1.4.1. They cannot be saved without a
  window, so only the final video trace (Master System, Game Gear) or the final state dump
  (Game Boy) of the old and the upgraded executable were compared: identical.
- X68000: the state key carries the compiler's identity by design, so a 1.4.1 state is refused
  cleanly ("Requested startup state rejected") by an upgraded export; the profile is experimental.
  The X68000 is not in the list, so it is converted in full anyway.

The Super Nintendo analysis cache identity changed once (the removed Super Mario World repository
was part of it): the analysis of the ROM is redone during the upgrade, in a few minutes, without
rediscovery.

#### Release 1.5.1 entries (25 October 2026, Windows)

Since the `v1.5.1` tag the game-side Python inputs that changed are `retrorecomp/batch.py`
(a game the bundled knowledge holds starts with the quick check, with a full discovery as its
fallback: conversion flow, not the generated game), `retrorecomp/console16.py` (the restored
`subprocess` import below) and `compilation_inputs.py` itself (this list). No file below
`native/` changed. Each verified console's tuple therefore gets the 1.5.1 game stamp as a second
value, found the same way as the 1.4.1 ones:

1. computed from the `v1.5.1` tag (commit `3ef2222`) with Python 3.14.5,
   `role_stamps(system)['game']`, for the nine consoles;
2. one game per console converted by the released Windows `Retro-Recomp.exe` 1.5.1
   (SHA-256 `8018b0444fcdd784c0777b9c2274253fc2f65045c64efc6fdecbeed932a4ad8b`), from the command
   line, in its own workspace (its own `.deps`, `datas` and `Games`), quick scan level, local box
   art only, Visual Studio Build Tools; then this branch's own `batch` path, asked about each
   export with the console's 1.5.1 stamp as the only legacy entry, reproduced the receipt's game
   part exactly: Master System (Fantasy Zone), Game Gear (Bubble Bobble), Game Boy (Tetris),
   NES (1942), Neo Geo (Magician Lord) and CPS-1 (1941 - Counter Attack). Only those six
   consoles have a 1.5.1 entry;
3. this branch then upgraded those six exports for real: "exported by Retro-Recomp 1.5.1 …
   rebuilt with the current tools and rechecked on the quick routes", 6/6 `upgraded`, report
   `upgrade.from_release` = `1.5.1`, `check_level` `quick`, native validation passed, zero
   interpreted instructions. Each upgraded executable then ran offscreen (SDL `offscreen` video,
   `dummy` sound, no window on the desktop) for 12 s without exiting; the CPS-1 and Neo Geo ones
   also completed 600 headless frames with zero interpreted 68000 and Z80 instructions.

Consoles without a 1.5.1 entry, whose 1.5.1 exports are converted in full once:

- **Mega Drive and Super Nintendo**: the released Windows 1.5.1 cannot convert them at all.
  `console16.probe16` lost its `import subprocess` when its launch moved to `core.run_process`,
  and it still reads `subprocess.CREATE_NO_WINDOW` on Windows, so every conversion stops before its
  first check with "name 'subprocess' is not defined" (seen with Columns and F-Zero). No 1.5.1
  Windows receipt exists for these consoles. The import is restored
  (`tests/test_console16.py`, `Probe16LaunchTests`).
- **X68000**: no receipt. Its reference run could not prepare its private game data in the deep
  test workspace (a Windows path-length limit; the first Master System choice, Alex Kidd, failed
  the same way under MSBuild and was replaced by the shorter Fantasy Zone), and its request carries
  the SDK stamp that already kept it out of the 1.4.1 list.

Quick-state keys are unchanged since 1.5.1: the Neo Geo, CPS-1, Mega Drive and Super Nintendo
`RR16_STATE_ABI` values computed from the tag and from this branch are identical, and the other
consoles' keys depend on native files only.

#### Release 1.5.2 entries (26 October 2026, Windows)

Between the `v1.5.2` tag and the Super FX work the game-side inputs that changed are, per
console (input fingerprints of the tag and of this tree compared one by one):

- every console: `retrorecomp/batch.py` (report fields: packing record, device summary, main-CPU
  count read through `snes_chips.main_interpreted`, the same number outside the SNES) and
  `retrorecomp/random_routes.py` (an authored route may carry its own script; only SNES routes do);
- Mega Drive, Neo Geo, CPS-1 and Super Nintendo also: `retrorecomp/console16.py` and
  `console16_optimization.py` (SNES-only branches: authored routes, Super FX message, liveness
  gate, the Windows clang profile build), `native/console16_main.c` (one more report field,
  `last_picture_change_frame`) and `native/retro_console16.h` (a declaration in the SNES section);
  `console16_host_ui.c` changed too, as a host input, behind `#if !(RR16_NG || RR16_CPS1 || RR16_MD)`;
- Super Nintendo also: the engine itself (`native/snes_backend.c`, `snes_ppu_cache.inc`,
  `snes_bus.py`, `snes_cart.py`, `snes_chips.py`, `snes_codegen.py`, `supernintendo.py`, new
  `snes_gsu.py`, `snes_routes.py`, checks).

Outside the Super Nintendo these change no generated game: build-only in the sense of the rule
below. The stamps were found as for 1.5.1:

1. computed from the `v1.5.2` tag (commit `b59575c`) with Python 3.14.5,
   `role_stamps(system)['game']`, for the nine consoles;
2. one game per console converted by the released Windows `Retro-Recomp.exe` 1.5.2, downloaded
   with `gh release download v1.5.2` (SHA-256
   `923f5c8ec5aefb8fa9781ccb55c4684b2e8adc437b3ca1a7bb9bd4ac4b828735`, as in `SHA256SUMS.txt`),
   from the command line, in its own workspace, quick scan level, `--no-online-cover`,
   `RETRO_RECOMP_SERVICE` empty, no window; then this branch's own `batch` path, asked about each
   export with the console's 1.5.2 stamp as the only legacy entry, reproduced the receipt's game
   part exactly for eight consoles: Master System (Fantasy Zone), Game Gear (Bubble Bobble), Game
   Boy (Tetris), NES (1942), Mega Drive (Columns), Super Nintendo (F-Zero), Neo Geo (Magician Lord)
   and CPS-1 (1941 - Counter Attack). Seven get a 1.5.2 entry (all but the Super Nintendo, below);
3. this branch then upgraded those seven exports for real, in the same `Games` folder: 7/7
   `upgraded`, report `upgrade.from_release` = `1.5.2`, `check_level` `quick`, native validation
   passed, zero interpreted main-CPU and sound-CPU instructions. Each upgraded executable ran
   offscreen (SDL `offscreen` video, `dummy` sound, no window) for 12 s without exiting; Mega
   Drive, Neo Geo and CPS-1 also completed 600 headless frames with zero interpreted instructions.

**X68000**: no entry. The released converter could not prepare its private game data under the
deep test workspace (Windows path length, as for 1.5.1); in a short folder it converted
Active Shoot (Satou Kouji) (zero interpreted instructions), but the receipt's game part is not
reproduced, neither with the tag's game stamp alone nor with the tag's `sdk_stamp('game')` as
well: the SDK stamp of the frozen converter still cannot be rebuilt from the tag. Its 1.5.2
exports are converted in full once.

**Super Nintendo**: no entry, and its 1.4.1 entry is removed. Its 1.5.2 receipt matched and, with
the stamp listed experimentally (never committed), the upgrade does rebuild F-Zero with the new
engine and passes the quick checks (same native entries as a full conversion, zero interpreted
65816/SPC700 instructions). But the rule below is about what a game does, and the SNES engine
changes it after 1.5.2: the `$4016` strobe (Madden NFL 95 and Bill Walsh College Football read the
pads differently, now as MAME does), GSU bus ownership and Super FX support
([SNES_SUPERFX.md](SNES_SUPERFX.md)). An upgraded report would also say that "only how the game
is built changed", which is not true any more. So a player's Super Nintendo exports of 1.4.1,
1.5.1 and 1.5.2 are converted in full by the next batch (seen with F-Zero: `upgraded` false,
native validation passed, zero interpreted instructions); a ROM the bundled knowledge holds starts
from its paths with the quick check at the Standard level.

**Validation fixes merged after these entries (26 October 2026, branch `shared-paths-reached-only`)**: they change game-side inputs again for
the Master System, Game Gear, Game Boy, NES, Mega Drive, Super Nintendo and CPS-1
(`systems/master_system.py`, `systems/game_gear.py`, `gameboy.py`, `gameboy_boundary.py`,
`nes.py`, `megadrive.py`, `megadrive_z80.py`, `megadrive_codegen.py`, `supernintendo.py`,
`snes_spc.py`). The 1.5.2 entries are kept, by reading those changes rather than by new release
conversions (the maintainer asked not to run hours of conversions for this): they change which
hints offered by other players a conversion remembers and sends (only those it observes), and
error paths a correctly generated 1.5.2 game never took — a native body with no instruction
(Game Boy: now `RST 38` on `0xFF`, otherwise the interpreter), duplicated Mega Drive RAM variants
(no longer a build failure), and the Sega `functions` backend, which now fails on a reference
divergence like `banked`. What a correctly converted game does is unchanged; the phase 1 audit
measured the same main-CPU and sound-CPU interpreter counts on ten games before and after, and
executables within 1 KB. An upgrade rebuilds the executable with the current compiler and
rechecks it on the quick routes, so upgraded exports get the fixes too; a `functions` Master
System or Game Gear export that diverges now fails that recheck and is converted again. The Neo Geo joined the shared base afterwards (phase 6: `neogeo_knowledge.py`,
`neogeo_conversion.py`); its game stamp changes too and its 1.5.2 entry is kept for the same
reason: the new code reads hints other players offer, retries without them when a conversion
that used some fails, and caps imported RAM rows; a cartridge converted without imported hints
is generated as before. Neither
the Mega Drive / Super Nintendo nor the CPS-1 quick-state keys change with these files (the
console16 key covers `native/` and SNES modules, the CPS-1 key its own build and codegen modules).

Quick-state keys between `v1.5.2` and this tree (same synthetic inputs as
`tests/test_legacy_compat.py`, Windows):

- **Mega Drive and Super Nintendo change**: their `RR16_STATE_ABI` covers every file below
  `native/`, and the console16 and SNES files changed. Checked with real executables: a state
  saved at frame 300 by the 1.5.2 Columns and F-Zero exports is refused by the new exports (exit 7),
  while each export loads its own states. No compatibility key is added: the Mega Drive state
  layout itself did not change, but adding its 1.5.2 key needs the same cross-check as the 1.4.1
  keys; the Super Nintendo engine did change.
- Neo Geo and CPS-1: unchanged (their keys cover their own native and Python files only); the
  1.5.2 Magician Lord and 1941 states load in the upgraded exports.
- NES, Master System, Game Gear, Game Boy, X68000: unchanged (no input of their keys changed).

#### Release 1.5.6 entries (27 October 2026, Windows)

The last release before the 1.6.0 stamp break. Its game stamps are the last value of the Master System, Game Gear, Game Boy,
NES, Mega Drive and CPS-1 entries, found as for 1.5.1 and 1.5.2 with one difference: the 12 receipts (two games per console,
quick level) were written by the converter of the `v1.5.6` tag run from its archive with Python 3.14.5 (`RetroRecomp.py
batch`), not by the packaged `Retro-Recomp.exe`, which showed a start-up picture on the desktop when it was tried and was
not run again. The packaged executable's `_compilation-stamps` equals the tag's `engine_stamp` for the seven consoles it lists
(CPS-1 is not among them). All 12 receipts matched the listed stamps, the generated sources of the same 12 games are
identical to 1.6.0's apart from the version text, the host shell and the state keys, and 1.5.6 exports of those consoles
were upgraded for real. The evidence, the list of files that differ and why, is in [UPGRADES.md](UPGRADES.md#exports-of-156-in-160);
the quick states in [GAME_STATES.md](GAME_STATES.md#states-written-by-release-156). No entry for the Super Nintendo, the Neo
Geo (its 1.5.6 receipt hashes the whole bank) or the X68000.

**Release procedure.** Before each release: remove the `LEGACY_GAME_STAMPS` entries, or
complete them, whenever the release really changes what a game does (translation,
CPU, video, sound, learning, validation). Entries are only valid for a release whose
game-side differences are build-only and were qualified as such.


## Mega Drive collection campaign, first four tranches — 24 October 2026 (local)

The user-approved campaign over the 904 unqualified ROMs of the NAS `megadrive`
folder runs at the extended scan level, eight conversions at a time, in
tranches of 50 (after an eight-game pilot). Each tranche is qualified with the
ordinary builder rule (fresh reference before learning, packed replay,
fresh-process states, current engine, private observations matching the report),
promoted additively and its build caches removed. Pilot and tranches 1–3:
**132 of 158 ROMs qualified**, three of them with remaining 68000 fallback
(Brian Lara Cricket, Brian Lara Cricket 96, Clay Fighter); 26 failures are kept
in the private registers (`.build/md-campaign-20261024/tranche-NN-register.json`).

The snapshot now holds **1,305 exact identities, including 214 Mega Drive and
134 Neo Geo**: 63,964,798 raw / **15,453,304 gzip bytes**, SHA-256
`41315eed4d51597c9621eaeebe5df1945abbb2ce282bf13371b05246b62a90fa`. All 1,164
records of release 1.2.9 are byte-identical; only new identities were added.
The raw size reached 98 % of the former 64 MiB bound (Mega Drive Z80
references, about 13,000 per game, dominate). At the user's request the
decompressed bound is now **128 MiB** (`retrorecomp/knowledge.py`), shared by the
loader, both builders, knowledge exchange and the package audit. Loading and
validating the current snapshot takes about 7 s once per converter process
(4 s for release 1.2.9); a compact Mega Drive format remains possible later. Full-game validation, hardware
fidelity and physical latency remain separate claims.

## Neo Geo library completed — 24 October 2026 (local, not released)

The final campaign covers the last convertible sets of the NAS `neogeo` folder,
at the extended scan level (one extra 18,000-frame pseudo-random credited route
per game), with up to eight concurrent conversions. Eight sets qualify as new
exact identities: World Heroes, World Heroes 2, World Heroes 2 Jet, World
Heroes Perfect, Zed Blade, Zupapa!, Tecmo World Soccer '96 (archive `tws96`,
identified as `twsoc96`) and Mutation Nation (converted in 1.0.2 outside any
campaign, now freshly requalified). Each passes every fresh-reference/packed
route, including the extended route, with zero observed 68000 and Z80 fallback,
plus three MVS and two AES fresh-process state points and the ordinary-save
checks. Their numeric observations are promoted additively.

With these eight, the snapshot reached 1,172 identities (133 Neo Geo), SHA-256
`d7f4677c…`. Every
previous observation and the six other console banks are preserved. A local
`-NoInstall` converter build embeds it; nothing is installed or published.

Voltage Fighter Gowcaizer first failed its AES attract comparison: after a
`JMP (A6)` to a pointer whose high byte carries a flag, the reference keeps the
32-bit PC while native code pushed a 24-bit return address. Native Neo Geo code
now keeps all 32 PC bits for relocated branch targets and return addresses
(code lookups still mask to 24 bits), with an authored flagged-PC region in the
68000 checks. Gowcaizer then qualifies on every route with zero fallback; World
Heroes Perfect and Zed Blade, regenerated as controls, still qualify. Snapshot
after the Neo Geo campaign: **1,173 exact identities, 134 Neo Geo**, 37,986,888 raw / **9,096,841
gzip bytes**, SHA-256 `97b69f45c6eceae144870a1f69ddb7b51cd3374bff3c14392a209e36b63f1ca5`
(diagnosis: `.build/neogeo-final-20261024/gowcaizr-diagnosis.md`). Fight Fever's archive is
an incomplete clone without its parent; `pnyaa.zip` is the already qualified
`pnyaaa` identity. Full-game validation, hardware fidelity and physical latency
remain separate claims. No ROM, BIOS, art or raw private library is included.
Evidence: `.build/neogeo-final-20261024` (`register.json`, `qualification.json`,
`knowledge.json`, `package-audit.json`).

## Capcom CPS-1 — local observations (24 October 2026) and shared paths (27 October 2026)

CPS-1 conversions keep their learned work-RAM 68000 and Z80 RAM code per exact
romset identity in the converter library (`library/cps1/<identity>/
observations.json`, with `compilation.json`). These observations are raw words,
so they stay in the library: they are the player's private build hints. Since
27 October 2026 the opt-in gameplay feedback (kinds 15 and 16) guides a
conversion too but is no longer written into that file, and only the native
runs of a conversion add to it. What CPS-1 *shares* is made apart, as numbers
(see "CPS-1 joins the base" below). These observations only add guarded native
code: every conversion still compares each route with its fresh interpreted
reference.

The first wide qualification (26 parent sets of the NAS, standard scan level,
eight concurrent conversions) needed no learned RAM code at all: zero 68000
and zero Z80 RAM variants for every set, and zero fallback for 25 of them.
Street Fighter II': Champion Edition interprets 0.06% of its 68000
instructions, run from graphics RAM, which native code does not cover yet (and
which therefore cannot be expressed as a path). Per-set results:
[CPS-1 guide](CPS1.md#qualified-sets-24-october-2026-windows).

## X68000: one game key, observations in the library (standardization 6a, 27 October 2026; part of the 1.6.0 stamp break)

The X68000 had two identities. The report, the export's marker, the queue and the
collection used the hash of the ordered disk set (`X68000Input.sha256`, now also
`game_key`); the library, the observations and the runtime feedback used the hash of
the manifest (disks + the player's IPL + font ROM + RAM size + initial drives). Since
1.6.0 **the game is the disk set** everywhere a game is named, and the manifest hash
only names the **machine**:

| What | Key | Why |
| --- | --- | --- |
| report `rom.sha256`, export marker, queue, collection, freshness | game (unchanged) | already so |
| summary `compilation.json`, shown by the Memory view | game: `library/x68/<game>/` | one row per game, the title found from the collection |
| converter observations and receipt | game, then machine: `library/x68/<game>/<machine16>/converter-observations.json` and `converter-qualification.json` | they hold the player's IPL (as words before 1.6.0, as entries over his IPL since 6b), so one set per machine, like the NES keeps one per engine revision; the receipt still names the full manifest hash |
| runtime feedback (`datas/fallbacks/x68-<key>.rrfb`, private bank `_runtime-feedback/<key>.rrfb`) | game | players with another IPL or font ROM record for the same game, and the future shared record can pool them |
| saves, quick states, `datas/games/x68-<key>`, `RR_X68K_SOURCE_IDENTITY`, report `source_identity` | machine (unchanged) | the IPL, font ROM and RAM change the machine state; players' saved data keeps its folder |

Why the disk set and not the manifest as the game: the manifest contains the IPL and
the font ROM of whoever converts. Two players with the same disks and different IPLs
would never share a record. The paths themselves are guarded by the live instruction
words and re-verified against a fresh reference run, so a path learned with another IPL
is harmless (its IPL-window words simply do not match); the IPL stays a named source of
the future record (`ipl`, with the disks), not a part of its key. The font ROM never
decides a code path.

Migration (nothing is deleted): when the library has no observation pair for the
machine and the earlier place (`<converter folder>/datas/x68000-development/<machine
hash>/`) has one, the pair is copied (receipt last, content compared) and the old files
stay; if the copy is impossible, the old folder is read. A summary found under the
machine hash is merged into the game's (the remembered mouse use is kept) and the
emptied folder is removed. Feedback files and the private bank entry of the machine
hash are merged into the game's feedback; the old files stay. The development pair of
the maintainer's stages (`observations.json` + `qualification.json`) is only read in
place. Exports made before 1.6.0 are converted again in full (X68000 has no legacy game
stamp); their feedback file is still found.

**The IPL as a span (standardization 6b).** Every instruction variant observed in the IPL window
(0xFC0000-0xFFFFFD) equals the bytes of the player's own IPL at that address: measured on all 31 local
observation files (30 identities), 196,968 of 196,968 IPL variants (15.2 % of 1,300,231). An observation file of
schema 2 therefore keeps, for that window, a *span* `{source: ipl, sha256, address, offset, length}` (the IPL is
mapped twice, so `[0xFC0000, 0, 131072]` and `[0xFE0000, 0, 131072]`) with its `entries`: `[position in the span,
length in words]`, the only thing a span cannot say. The words are read from the player's IPL when the file is read
(the span names that IPL's hash and is refused with another), so the file holds no firmware byte. RAM, text VRAM and
the SCSI stub (`0xEA0000`, 12 variants in all, built into the machine and not taken from the player's IPL) stay
ordinary variants, and so does any variant that differs from the IPL, or all of them when the file is a SCSI-marked
IPL that the machine replaces. The fold is exact and reversible (the same `(address, words)` set comes back, without
the informational hit counts), schema 1 files read as before and are written as schema 2 on the next conversion, and
a file with spans needs its IPL: nothing about it is shared, and the X68000 stays out of the shared base.

The receipt's `sdk` stamp is stored and **not compared**. The observations are facts
about the guest program (addresses, instruction words), never trusted without the fresh
native/reference comparison of each conversion, so a stamp check would discard them at
every engine change without making any conversion safer. `sdk_stamp` itself hashes the
explicit X68000 input list of `retrorecomp/stamp_inputs.py` (no directory is read), so
it is the same from a tag archive as from a working tree.

## X68000 stage 9 — private multi-disk and mouse exploration

Six new exact sets (Naious, View Point, Air Combat II, Choujin, Power Unit and
Tricorn Final) use fifteen hash-checked, read-only Batocera inputs. Primary,
mouse and keyboard cold sessions each retain fresh reference comparisons;
additional code observations never waive those checks. Known mouse profiles
receive a longer bounded mouse route. The runtime fallback recorder contributes
10,370 private candidates from seven user sessions, including 2,598 Power Unit
encodings. Other games are not marked corrected by that import alone.

Power Unit exposed an automatic insertion race: a loader waiting for physical
removal cannot proceed if the next disk is inserted in the same guest frame.
A bounded empty-drive interval now precedes automatic insertion; its progress
and the previous disk identity survive snapshots. The diagnostic mouse click
then opens the game's menu. This is a media-session fix, not a title-specific
CPU patch or a claim of full gameplay coverage. Windows/Linux corrected final
receipts now cover three fresh bounded routes per set: 124,000 frames and
1,840,161,608 native instructions observed per OS, without fallback on these
routes. Exact CPU/RAM/video/PCM/clock traces and snapshot continuation agree.
Historical local encoding corpora can have different sizes; the receipts keep
their per-platform counts instead of using those counts as a fidelity test.
The durable private receipt is `datas/x68000-development/stage9-qualification.json`,
with a separate receipt per exact machine identity. The public bank is unchanged.
All raw observations, media and qualification artefacts
remain private while X68000 runtime redistribution terms are unresolved.

The reviewed Air Combat front uses a link-only reference and an offline reusable
cache on both systems. Choujin and Power Unit still have no verified front;
their screenshots must not be promoted into the reviewed-cover catalogue.
Automatic card thumbnails now follow updated conversion reports while preserving
manual selections and saved summaries. Both local converters include this fix.

## X68000 stage 8 private expansion — Windows/Debian qualification

Eight further exact sets add Daimakaimura, Super Hang-On, Cotton (Sprite, 1991),
Alien Syndrome, Arkanoid — Revenge of Doh, Bubble Bobble, Nemesis '94 Gradius 2
and Quarth. The ten staged disk images are hash-checked copies from the read-only
Batocera source. No game assets or instruction words are promoted into the public
snapshot while runtime distribution terms remain unresolved.

The observed external SCSI IOCS ROM fetch aperture at EA0000–EA1FFF now uses
the same live instruction guards as RAM, text VRAM and IPL code. Two additional
authored checks qualify execution, modified-word rejection and aperture bounds;
there are now 20 CPU/guard checks. Diagnostics retain at most 16 unmapped PCs in
RAM and write only an explicitly requested end-of-run diagnostic report.

An independent 10,000-frame second input route discovers 2,985 additional exact
instruction variants. They are first retained as private unqualified candidates,
then used by a fresh generation followed by fresh native/reference checks.
Headless diagnostic imports do not test the player's interactive exit recorder.
Never relabel the candidate import itself as a successful native qualification.

Additional captures must be complete and exact-identity compatible. Counts alone
are not new code coverage and no longer repeat an identical reconstruction.
Windows and Debian pass both 8,000/10,000-frame routes for all eight games without
observed fallback: 144,000 main frames and 2,172,707,865 native instructions per
OS. The initial five traces and the second route/restart agree across both OS.
There are 107 X68000, 61 shared-integration and 25 credits/language tests per OS,
plus 20 CPU/guard, 59 device, 11 session and 9 disk vectors. The previously
missing SDK-availability test on Debian is included in the final replay;
26 test/harness files and 493 production source files match across platforms.
The ten original disk images remain hash-identical.

Durable receipts live in `datas/x68000-development/stage8-qualification.json`
and each exact identity's `converter-cross-platform-stage8.json`. Local frozen
converters are rebuilt and their payloads inspected, without embedding private
observations. A later Linux UI/notice resource refresh is recorded separately:
it changes the conservative SDK freshness stamp, not the qualified machine
sources. Do not relabel an old game's proof as a new post-notice qualification.
Never copy private raw captures into public assets; the public bank is unchanged.

## X68000 private development register — 20 October 2026

Stage 7 expands private checks to five additional supplied sets (After Burner
II, Bonanza Bros, Cranked Arrow, Metal Sight and R-Type), beside Cho Ren Sha.
Instruction observations now include guarded text VRAM and actual instruction
lengths. Exact duplicates are compacted before regeneration without weakening
fresh reference checks. Runtime RRFB candidates stay independently bounded.
Two exact-set disk transitions for Metal Sight, a mouse-input profile for
After Burner II and five approved online front-cover references are recorded.
The FM LFO now owns a portable, serialized random state and initializes its
phase; this fixes an authored snapshot test and addresses Linux PCM divergence.
See the local `docs/history/x68000/SHARP_X68000_LIBRARY_STAGE7.md` and final per-game receipts
under `.build/x68000-stage7`. Raw RAM code, firmware, game snapshots and media
remain private. This work does not promote X68000 into the public snapshot.
The final six-game campaign covers 46,000 main frames and 634,977,458 native
instructions per OS, with no fallback observed on those bounded paths.
All five traces per game agree across Windows and Debian. The subsequent
W/X default-binding change has a separate R-Type qualification receipt.
Metal Sight's merged register contains 260,883 variants without truncation;
future enrichment must respect the 262,144-entry bound and retain fresh checks.

Stage 6 adds the local SDK-gated converter profile and a single-file native
player, with shared menus/settings and bounded deferred RRFB kind 13. Every
conversion compares a new independent CPU/RAM/video/PCM/clock replay and a
new-process state continuation. Writable media and SRAM for validation are
fresh copies; real exported user data is preserved across regeneration.
Only exact-identity, hash-qualified earlier observations seed discovery;
runtime feedback stays an unqualified candidate until a fresh comparison.
The small Game memory index contains counts/metadata, never instruction words.
Converter observations and their checksum receipts remain private under
`datas/x68000-development/<exact identity>/` (since 1.6.0 in the library, under the game:
see "X68000: one game key" above). See the local
`docs/history/x68000/SHARP_X68000_CONVERTER.md` and `.build/x68000-stage6/final-proof.json`.
This does not add an eighth production profile or change the public bank.
The stage-6 final evidence is 100 X68000 and 83 integration tests per OS,
62 SDL assertions, and identical 4,000-frame CPU/RAM/video/PCM/clock main
traces across both OS. The main route observes 61,280,215 native instructions
per OS and no fallback. New-process snapshots also cover an active floppy
DMA at boot; modern CPU reset/prefetch/exception latches are now serialized.
A durable `converter-cross-platform.json` receipt references the final proof.

Stage 5 qualifies session controls, F8/F9 and private disk changes on Windows
and Debian. The native/reference and cross-platform main runs agree on every
CPU/RAM/video/PCM/clock trace column, including new-process restoration. Across
both OS, 263,820,886 native instructions are observed without fallback in the
bounded original single-disk Cho Ren Sha routes. There are 92 Python tests per
OS, 11 session and 9 disk vectors, plus the previous hardware/CPU regression.
See `docs/history/x68000/SHARP_X68000_SESSION.md` and `.build/x68000-stage5/final-proof.json`.

An additional exact QA identity combines Cho with two entirely authored disks:
`1beb31ee72d8444f65d7ccc805b4185d012724fbb94830df5924eba473ee7e6a`.
Its real drive-change/restart traces agree between CPUs and platforms, but its
44 fallback instruction executions per OS are explicitly retained. Four
distinct IPL variants were harvested (observation SHA-256
`b618585013c0c234d2a7b58b1304b0280543ff5914071dc973de933ce54b6e72`) under its
own private identity, pending a future native generation. They are not merged
into another game's profile or promoted into the public knowledge snapshot.
Session qualifications for the original game remain separate from stage-4
CPU observation qualifications. Player snapshots contain private RAM/media
and must never become public compilation knowledge.

Stage 4 corrects bounded hardware contracts without modifying the shared
production CPU semantics. Three newly reached RAM PCs are retained privately;
the generated CPU now has 23,618 descriptors including nine authored diagnostic
descriptors. Four fresh paths compare 11,000 complete rows, with 167,794,658
native instructions observed per OS and no observed fallback. The 58 device
vectors, integer clock/PCM ledger and 13 CPU/guard checks are separate gates.
See `docs/history/x68000/SHARP_X68000_HARDWARE.md` and `.build/x68000-stage4` final receipts.
The stage-3 private snapshots are archived before the per-identity register is
updated; raw instruction words remain private. No public X68000 promotion,
eighth production profile or new release is authorized by this work.

Historically, the stage-3 native CPU prototype qualified the exact Cho Ren Sha 68k v1.01
media/firmware/configuration set and authored Human68k fixtures on Windows and
Debian. Four fresh routes compare 11,000 CPU/RAM/pixel/PCM rows per OS, with
173,010,628 native instructions and no observed interpreted instruction. Thirteen
authored CPU/guard checks and 63 Python tests pass on each OS. This is same-machine
CPU agreement, not independent hardware fidelity or full-game qualification.

Useful observations and receipts are retained privately under
`datas/x68000-development/<exact-media-identity>/` (since 1.6.0 under the game in the
library), outside disposable builds.
They include private live words and must **not** be copied into a public snapshot.
The X68000 adapter is not yet a public converter profile and its composite
machine-runtime distribution terms remain unresolved. The existing 1,164-entry
snapshot below is unchanged. Future promotion must reconstruct instructions from
the user's exact supplied inputs and pass fresh validation, without borrowing
another game's profile. See the local `docs/history/x68000/SHARP_X68000_NATIVE.md` and private
`.build/x68000-stage3/cross-platform.json` for the development evidence.

## Release 1.1.8 — Neo Geo campaign and targeted repairs, 20 October 2026

The snapshot contains **1,164 exact identities**, including **125 Neo Geo**:
37,647,952 raw JSON / **9,039,585 gzip bytes**, SHA-256
`26175737d4a2a4ee71b0826f13bde284305ddf1f42a669c4910e65c0b6bd4ecc`.
All previous observations and the six other console banks are preserved. The
same verified numeric snapshot is packaged for Windows and Linux.

The thirty-game campaign initially qualified 28 new identities. Targeted repairs
qualify Riding Hero, arcade-only Irritating Maze and the earlier League Bowling
failure, adding **31 identities over 1.1.7**. The four targeted exports, including
the corrected Super Sidekicks 3 cover, pass 26 fresh-reference/packed routes.
MVS states and ordinary saves pass for all four; the three AES-compatible games
also pass their independent AES checks. Restored runs are checked for observed
CPU fallback before promotion. No shared hint waives a fresh validation gate.

Irritating Maze's trackball controls remain unqualified. Numeric native coverage,
CPU/reference agreement, full-game validation, hardware fidelity and physical
latency are separate claims. No ROM, BIOS, downloaded art, state or raw private
library is included. Evidence: `.build/neogeo-thirty-20261020` and
`.build/neogeo-update-1.1.8-20261020`.

## Release 1.1.7 — 28 additional qualified Neo Geo identities

The verified snapshot contains **1,133 exact identities**, including **94 Neo
Geo**: 36,461,008 raw JSON / **8,869,041 gzip bytes**, SHA-256
`c5ddfb6f6f4cf84df1bff61ee440b1004a838daa4b3a5b045d5460f39781a557`.
All previous observations are preserved and the six other console banks are
unchanged. The same snapshot is packaged for Windows and Linux.

The finite thirty-game campaign produced 29 exports; only **28** pass native
qualification and promotion. There are 196 fresh-reference/packed routes,
three MVS and two AES quick-state points per qualified game, invalid-state
rejection and ordinary-save checks. All 56 AES restored runs are independently
rechecked for zero observed CPU fallback. Ghost Pilots was regenerated to test
the shared input fix. Full-game/hardware fidelity and physical latency are
separate, unmeasured claims.

Voltage Fighter Gowcaizer's hardware/state mismatch and League Bowling's heavy
68000 fallback stay private and excluded from promotion. Reviewed artwork cache
lookups succeeded for the new exports. No ROM, firmware, cover image, game state
or raw private library enters the shared snapshot.
Evidence: `.build/neogeo-thirty-20261019` and `.build/autofire-20261020`.

## Release 1.1.6 — unchanged qualified snapshot

The collection path and scan fixes retain all **1,105 exact identities** and
the same 8,731,196-byte gzip snapshot, SHA-256
`6b36f85f70c4f66fbf320217f030991879a854dd0a750efe3a69790639ebcdb9`.
No cartridge scan, game-runtime change or new qualification is part of this
release. Collection migration, favorites and missing-file cleanup remain private
presentation data, separate from the compilation library.

## Release 1.1.5 — existing qualified snapshot, 19 October 2026

The collection/UI release retains all **1,105 exact identities**, unchanged on
Windows and Linux: 8,731,196 gzip bytes, SHA-256
`6b36f85f70c4f66fbf320217f030991879a854dd0a750efe3a69790639ebcdb9`.
No new cartridge campaign or qualification is part of 1.1.5. Collection statuses,
favorites, ROM paths, cover overrides, cached display summaries and game cards
remain private presentation data, separate from compilation observations.
Regeneration still checks the exact cartridge and follows its usual validation
gates. See [compiled games](COMPILED_GAMES.md).

## Release 1.1.4 — unchanged qualified snapshot, 19 October 2026

The animated-credits update retains the complete verified 1.1.3 snapshot below,
unchanged on Windows and Linux. No cartridge scan, new observation or gameplay
qualification was performed for 1.1.4. Credits UI, MOD files and the native music
player are excluded from generated-game compilation inputs.

## Release 1.1.3 qualified snapshot — 18 October 2026

Release 1.1.3 contains **1,105 exact identities**: SMS 258, GG 13,
Game Boy 606, NES 36, Mega Drive 82, SNES 44 and Neo Geo 66. The snapshot is
**35,498,823 raw / 8,731,196 gzip bytes**, SHA-256
`6b36f85f70c4f66fbf320217f030991879a854dd0a750efe3a69790639ebcdb9`.
The Windows and Linux converters include the same verified snapshot.

Twelve new Game Gear records pass fresh advanced conversion and independent
replays of the compressed exports: 86,400 native/reference frame pairs with
matching CPU, RAM, VDP traces and final images. 3 Count Bout now passes its
previously failing AES state gate as well as MVS/AES reference, packed, state
and ordinary-save checks; its exact MVS cartridge/BIOS identity is promoted.
AES observations remain separate. The 26 unstarted Neo Geo games stay paused.

SPC references now also support bounded PC bitmaps and positive delta groups.
Every original PC/ROM-offset pair is reconstructed and compared before replacing
the representation; existing live-opcode guards and the 64 MiB decompressed
limit remain. All earlier qualified observations, including all 606 Game Boy
records, are preserved. No ROM, BIOS, private raw library, downloaded art,
game state or sample is included. Evidence: `.build/development-20261018`.

Export freshness now fingerprints the relevant console compiler and its numeric
knowledge instead of the application version alone. Unknown source dependencies
remain shared; changed settings, exact-game hints, binary contents or relevant
code still force conversion. Old receipts migrate through fresh conversion.
Frozen/source equivalence is checked with the same allowlisted resources;
private local source profiles deliberately remain distinct dependencies.

The final local review also serializes Game Boy and NES library updates across
concurrent conversions. NES merges ROM/RAM observations before atomic replacement;
Game Boy retains a checksum-verified previous trace until the new manifest is
committed, then removes that temporary backup. A busy library lock times out on
both Windows and Linux. These are storage fixes, not new qualified observations;
the snapshot above is unchanged. See [review evidence](QUALITY_REVIEW.md).

## Partial Neo Geo campaign included in 1.1.0 — 15 October 2026

The fifty-game campaign was stopped at the user's request after its active
conversions finished: **23 successes, one failed AES snapshot check, 26 not
started**. Only the 23 successful exact cartridge/BIOS records are promoted.
The failed 3 Count Bout observations stay private until full requalification.
No remaining game or retry is launched by this knowledge update.

The 1.1.0 snapshot contains **1,092 records,
including 65 Neo Geo**: **53,561,244 raw /
14,594,906 gzip bytes**, SHA-256 `80ee5ce98c53fede21ff64293c19b022393a01ffce40c767b26c89038d94ebc7`.
All earlier numeric observations are preserved; the six other console banks
are unchanged. Exact sorted P/BIOS roots use validated, bounded positive deltas
instead of repeated region/offset pairs. Expansion and real-input consumer
checks preserve the same addresses and reconstructed guards, with no instruction
bytes added. The previous representation remains readable and the decompressed
64 MiB limit remains in force. Despite 23 additions, the compressed snapshot is
**1,690,241 bytes smaller** than release 1.0.3.

Promotion rechecks the original fresh-reference/packed receipts: 161
MVS/AES/enhanced route comparisons with zero observed main/sound fallback,
three MVS and two AES fresh-process state points per game, invalid-state
rejection and ordinary-save checks. The numeric knowledge does not depend on
artwork availability or a later state-validator correction. Old EXEs are not
regenerated here; every future conversion still performs its fresh gates.
Only numeric reconstructible references are embedded, never the private library,
ROMs, BIOS, RAM dumps, saves, covers or audio. AES observations remain separate.
Evidence: `.build/neogeo-fifty-20261015/partial-qualification.json` and
`partial-knowledge.json`. The partial campaign stays paused; only its verified
numeric snapshot is distributed in the converter.

## Eight additional Neo Geo cartridges — 15 October 2026

Eight newly qualified exact cartridge/BIOS identities extend the release 1.0.3
bank to **1,069 records, including 42 Neo Geo**.
The snapshot contains **60,006,996 raw / 16,285,147 gzip bytes**,
SHA-256 `1e0dd405b814685b54fc9fc7dd791ce9065ff5eba43900aa3d21e164317eef70`. Its compressed increase is
**339,019 bytes**; every earlier record and every other console
is preserved unchanged. The 64 MiB decompressed bound remains active.

Fresh standard MVS/AES reference, packed-executable, state and ordinary-save
gates precede promotion. Enhanced-mode discovery for Twinkle Star Sprites adds
previously unreached banked cartridge paths: the same 9,000-frame two-player
route goes from 3,195 interpreted 68000 instructions to zero,
with matching reference CPU/hardware/image/PCM results. Only validated numeric
references enter the bank; no game, BIOS, RAM dump, image, audio or save is added.
AES observations remain separate and private. The eight additional enhanced
replays also pass, without asserting full-game or physical-hardware fidelity.

The release converter bundles this verified snapshot. Two user-approved Neo Geo
front-cover references bring the separate link-only catalogue to 36 entries.
All eight downloaded covers are reused successfully with network access blocked;
the artwork itself stays in the local cache. Evidence:
`.build/neogeo-series-20261015`. See [Neo Geo](NEOGEO.md) for the sampled games.
This verified snapshot is included in release 1.0.3.

## Selective regeneration and Neo Geo modes — 15 October 2026

Release 1.0.2 records the exported binary hash, converter/runtime inputs and
the exact fallback candidates consumed by each successful conversion. Unchanged
exports are kept; new hints, changed settings or a new converter trigger fresh
conversion. Unsupported unchanged hints do not cause an endless rebuild loop.
The force option bypasses freshness only, never validation or overwrite protection.

Neo Geo keeps the original MVS identity for existing saves and knowledge. The
optional verified AES firmware adds a separate AES feedback/save identity.
Both modes have full BIOS native candidates and live guards; the shared MVS bank
only receives numeric observations actually observed on its MVS reference routes.
AES private hints remain separate and are checked on fresh AES routes.

Two requalifications refresh the existing 34 Neo Geo records without increasing
the total of 1,061 exact identities. Other consoles and all older qualified
entries are preserved. The snapshot is 58,541,482 raw / 15,946,128 gzip bytes,
SHA-256 `3f2178f085f25c7f57fb0eb6978943a64d2d37abba93eb66210e475433412a76`.
No BIOS, cartridge, save, capture, audio or raw feedback file is included.

## Shutdown-only gameplay feedback — 15 October 2026

All seven generated-game profiles now collect bounded fallback candidates in
memory and save them only at normal shutdown. The converter imports the exact
game's file on regeneration, then runs its existing fresh validation gates.
Each game-side file is capped at 131,168 bytes; no fallback creates no file.
F12 toggles recording, enabled by default. Each console's Options page also
offers a recovery folder and an **Import fallback hints** button: it retains
an independent private copy without compiling or loading a ROM. Imported
observations survive removal of the original game folder and path changes.
The private feedback bank is distinct from qualified shared knowledge and must
never be bundled. See [Runtime feedback](RUNTIME_FEEDBACK.md) for scope,
per-console candidate types, storage, checks and remaining unsupported cases.

## Optional enhanced Neo Geo mode — 14 October 2026

The standard Metal Slug 3 conversion is freshly qualified after adding the
optional F5 mode, retaining the same cartridge/BIOS identity and all earlier
verified numeric observations. The shared bank contains 1,061 records / 34
Neo Geo, 58,540,943 raw / 15,946,134 gzip bytes,
SHA-256 `120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`. Every other console is preserved. The local
converter includes the verified bank and the new runtime; no public release is
made here. Enhanced-mode scene/cold replays are validated separately and do not
promote private state data or artificially inflate the standard compilation bank.
Evidence: `.build/neogeo-enhanced-20261014`; see [Neo Geo](NEOGEO.md).

## Neo Geo runtime performance requalification — 14 October 2026

Metal Slug 3 and Sengoku 3 are freshly qualified after reducing native dispatch
and sprite-rendering overhead. Nine reference/packed routes, six fresh-process
F8/F9 points and both ordinary-save gates pass. Three additional action replays
match the preceding runtime with zero observed main/sound fallback.

The resulting verified snapshot is **byte-identical** to the preceding bank:
**1,061 records / 34 Neo Geo**, **58,540,943 raw / 15,946,134 gzip bytes**, SHA-256
`120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`.
No new observed code path is needed for this performance change; neither static
candidates nor the raw private library are added to inflate coverage. Every
older observation and every other console's record are retained. The local
converter includes this verified snapshot and the optimized runtime for future
exports. This is not a public release or a full-game hardware qualification.
Evidence: `.build/neogeo-performance-20261014`; see [Neo Geo](NEOGEO.md).

## Early Neo Geo gameplay paths and shared xBR — 14 October 2026

Three fresh qualifications refresh the exact Metal Slug 3, Sengoku 3 and
KOF 2001 cartridge/BIOS records after early gameplay feedback. All four action
buttons join the default discovery routes, with an additional recorded grenade
route for Metal Slug 3. Older verified numeric hints for the same identity/pins
are retained when refreshing a record; the raw private library is never imported.
The larger fixed-ROM/BIOS static scan is not itself promoted as observed knowledge.

The bank remains **1,061 records / 34 Neo Geo** and is now **58,540,943 raw /
15,946,134 gzip bytes**, SHA-256
`120de0085d379d0743183f59cb93885953889c8fb518bd17a1829d60f94930c1`.
It adds **11,738 gzip bytes**; every other console and every earlier verified
observation are preserved. Fresh reference, packed-export, state and ordinary-save
gates still apply. All four replayed action routes have zero observed fallback
and identical CPU/hardware/image/PCM results; these are bounded gameplay paths.

The local converter also bundles the shared xBR cache for all seven profiles.
It changes presentation cost, not compilation observations or the filtered image.
Only newly generated EXEs receive the updated runtime. Evidence and the original
held-out replays remain under `.build/neogeo-gameplay-coverage-20261014`; see
[Neo Geo validation](NEOGEO.md). No public release is made in this task.

## Ten additional Neo Geo cartridges — 14 October 2026

Ten further exact MVS cartridges pass fresh reference/packed comparisons,
three fresh-process F8/F9 points each, invalid-state rejection and ordinary-save
checks. Their numeric observations extend the bank to **1,061 records total,
including 34 Neo Geo**, **58,502,698 raw / 15,934,396 gzip bytes**, SHA-256
`1ccc1f854bc00c83a0fe7b56f95c95fd9b8c0ea99407667ee326638953816a7f`.
The added compressed size is **369,337 bytes** (about 361 KiB); every preceding
record is retained and every other console remains unchanged. The decompressed
64 MiB limit and all fresh-validation gates remain active. This snapshot is
included in the local development converter; no public release is made here.

Only reconstructible numeric P/BIOS/RAM/sound hints are promoted. Inputs,
states, ordinary-save contents, captures and audio stay private. Evidence is
under `.build/neogeo-additional-20261014`; see [the sampled paths](NEOGEO.md).

## Qualified Neo Geo MVS development snapshot

The final campaign refreshes all **24 Neo Geo records**: **1,051 records total**,
**56,898,332 raw / 15,565,059 gzip bytes**, SHA-256
`2513b86760176a0a8ab7585395fc6417f54adcefd29af2ffa5c8d973d6a60e52`.
It adds 15 exact cart/BIOS identities to the previous nine, while preserving
every other console's records byte for byte. The increase is **712,010 gzip
bytes** (about 695 KiB); the 64 MiB decompressed budget remains intact.

Only the current completed reference routes are promoted from a reused build
folder; stale developer journals cannot add roots silently. The promotion gate
also verifies zero fallback in the saved continuous/restored state reports,
in addition to the candidate hash, exact cart/BIOS identity, fresh reference,
packed replay and ordinary-save checks. The six long controller paths retain
their newly discovered numeric entries. No cartridge, BIOS, RAM dump, state,
NVRAM/card contents, image or audio is included. Evidence stays under
`.build/neogeo-final-qualification-20261014`; see [Neo Geo](NEOGEO.md).

## Neo Geo cartridge/save qualification update

After the cartridge-protection and ordinary-save campaign, the development
snapshot contains **1,036 records / nine Neo Geo**, **53,844,079 raw / 14,853,049
gzip bytes**, SHA-256
`f2a2cbf3f240f0b73c9700fc0b456d90141026e349c31b3f71b580ecbbe2eb8c`.
Eight current integrated records are refreshed, including six additions; every
other console and the previously qualified Metal Slug 3 record are retained.
The compressed increase over the preceding integrated snapshot is 450,238 bytes.
The 64 MiB decompressed bound and fresh reference/packed/state gates remain.

The builder additionally requires the ordinary-save route's native counters,
lazy initialization and either fresh-process memory reload or an explicitly
observed no-change route. Discovery of NAM-1975's late card path fixes additional
main-CPU fallback. MSLUGX/PVC and two further SMA variants contribute numeric
P/BIOS/RAM/sound references only; card/NVRAM data, volatile PVC RAM dumps, images,
PCM and private journals stay local. The proof for this refresh is under
`.build/neogeo-cartridge-saves-20261014`. The dated sections below preserve the
earlier snapshots and their original qualification status.

## Neo Geo development observations

The integrated development converter now includes **three BIOS-scoped Neo Geo
records**, qualified through fresh reference, packed-export and F8/F9 checks.
The shared snapshot contains **1,030 records** in total; the previous 1,027
records are retained unchanged. It is **51,870,239 raw / 14,402,811 gzip bytes**,
SHA-256 `eda5f2dec415d1f3907eb9ab00480c734722c72ba2437c91ebd16e09ad6cdf35`.
The added compressed size is 194,846 bytes. No ROM or BIOS bytes are included.

Neo Geo records use the exact prepared region/NGH identity, four selected BIOS
component hashes, MVS Europe, and pinned loader/runtime revisions. Numeric
P/BIOS roots, RAM source offsets and Z80 structural references reconstruct
guards from the user's own input. Wrong firmware, changed regions, out-of-range
references and raw-word/path fields are rejected. Shared hints remain additive:
every conversion still builds a fresh reference before learning and compares
the packed game and fresh-process states before replacing an export.
Local qualified records live in `datas/library/ng/<cart-and-BIOS-key>` beside
the converter. `tools/build_neogeo_knowledge.py` accepts integrated conversion
reports only after reference/packed/state qualification and candidate-hash
verification, and preserves every other console's records. It reads the game's
build folder, which a conversion removes after publication since 1.5.1: convert
the qualifying games with `--keep-build`. Earlier prototype
receipts below remain private; they are not imported as unchecked journals.

The standard-board and protected-board Neo Geo prototypes store private numeric reached-PC/guard and
comparison receipts under its local build directory. Both CPUs are native on
the bounded tested routes; these observations are **not promoted** to the bundled bank. Future Neo Geo
records must be keyed by the original multi-region contents, parent data when
used, the selected BIOS, system/region and pinned loader/runtime/CPU versions.
Static-native and hardware/gameplay qualification still apply before promotion.
The earlier prototype snapshot was unchanged. See [Neo Geo](NEOGEO.md).
Banked Neo Geo roots now include the actual physical P/BIOS offset observed
under the current mapping, rather than a guessed offset from the virtual PC.
Metal Slug, Neo Drift Out, Puzzle Bobble and Samurai Shodown II receipts remain
local under `.build/neogeo-expansion-20261014`. Retain them with their exact
cartridge/BIOS identities; do not import their raw journals into the released
bank or skip ordinary reference, packed-export and state validation.
Protected-board receipts for Fatal Fury 2, KOF '98, KOF '99 and Metal Slug 3
stay under `.build/neogeo-protected-20261014`. Their guarded 68000 RAM entries
retain numeric `(RAM offset, source region, source offset, byte length)` links
only when the exact instruction bytes can be reconstructed from the identified
P/BIOS input. Unreconstructible variants stay in private discovery reports;
do not copy raw RAM words into a reusable or bundled observation record.
Code guards exclude live protection response/random ports and the KOF '98
mutable overlay. Board state, sprite line buffers, snapshots, PCM and captured
images are validation evidence, not compilation observations to distribute.

## Release 1.0.0: SNES device knowledge and lossless SPC ranges

Current bundled snapshot: **1,027 exact ROMs / 44 SNES**, **51,025,629 raw / 14,207,965 gzip bytes**.
SHA-256: `a5b85b347b0512a54bb3a1c75ed3a549544a828ff9208780b5a50bfd50a5029b`. Eight device cartridges pass ordinary,
packed and fresh-process state checks before promotion; four also pass longer
active-device routes. Unchanged console records are preserved. Existing SNES
SPC guards are losslessly encoded as PC ranges and ROM offsets; every previous
pair is checked for semantic equality. Both old pairs and bounded ranges remain
readable. No ROM, RAM dump, firmware, cover or private journal is bundled.
The 64 MiB raw bound remains; hints never bypass conversion validation.

Two conversions from the final audited one-file EXE start with an empty private
library and use this bundled snapshot. See [SNES evidence and limits](SNES.md).
Dated sections below preserve historical counts and publication status.

## Local SNES standard-profile qualification and opcode guards

Previous snapshot: **1,023 exact ROMs / 40 SNES**, **58,832,410 raw /
15,035,601 gzip bytes**, SHA-256
`bc7d03f401b009965ef39bb0e9a80dbd7043edb7bd49032b09aa3a4831a194bd`. Nine SNES records are refreshed; 31 others and every other
console record remain unchanged. Relative to the previous completed 34-record
snapshot, this campaign adds six exact revisions and requalifies three controls.

SNES `ram_opcode_refs` contain only PC/ROM-offset numeric pairs. The user's exact
ROM reconstructs the guarded opcode; operands stay live on the timed bus. This
retains useful observations whose changing four-byte literals had no ROM source.
No raw RAM journal, ROM, firmware, cover or player data is bundled. Shared hints
never bypass ordinary CPU/image/PCM validation. The decompressed 64 MiB bound
is retained. See [SNES scope and evidence](SNES.md).

The final audited local one-file converter embeds this snapshot and passes two
fresh-private-library conversions. The published 0.26.0 package is unchanged.
Earlier dated sections below retain historical snapshot sizes and counts.


## SNES object, cartridge-decoding and nested-IRQ qualification

The local snapshot contains **1,017 exact ROMs / 34 SNES records**. Eight new
revisions are promoted only after their final ordinary and compressed-export
CPU/state/frame/PCM comparisons and fresh-process states pass. Six controls
are requalified; twenty other SNES records and every other console's records
remain identical. Native coverage, hardware checks and reviewed gameplay
are separate evidence: the Axelay case showed why internal image agreement
alone cannot establish hardware fidelity. Timing and mapping fixes belong
to the common runtime, rather than game-name exceptions in the hint bank.

Size: **53,484,310 raw / 13,704,461 gzip bytes**, an increase of 1,817,450
compressed bytes. SHA-256:
`c7ffb62f854250026d38daa135332f7108a01c954c2cccf7230694bcb3345cc0`.
The 1,178 RAM patterns without reconstructible ROM references remain private.
There are no ROM bytes, raw private journals, firmware, covers or player data
in the resource. The decompressed 64 MiB bound is retained.
Shared observations never bypass normal conversion/reference validation.

Evidence: `.build/snes-nested-irq-qualification-20261013/knowledge-build.json`,
`delivery.json`, original independent fixtures and the final frozen-converter
checks. The resource is included in the locally rebuilt one-file converter;
the published 0.26.0 release is unchanged until a publication is requested.

## Super Nintendo bus arbitration requalification

The CPU/DMA/HDMA correction belongs to the common runtime. It does not add
per-game timing patches to the knowledge resource. The six exact SNES controls
undergo ordinary CPU/frame/PCM comparison again before their hints can be
refreshed; packed routes and fresh-process states are checked separately.
CPU bus requests, channel counters, PPU journals and player saves are never
compilation observations. The other twenty SNES records and every other
console's records are preserved. Evidence is kept locally in
`.build/snes-bus-arbitration-20261012/knowledge-build.json` and `delivery.json`.

The qualified observations are unchanged: **1,009 exact ROMs / 26 SNES**,
**46,497,854 raw / 11,887,011 gzip bytes**, with the same snapshot SHA below.
The correction requires regenerating affected game executables; reusing hints
never bypasses their normal validation. No private library, firmware, ROM or
player data is added to the converter.

## Super Nintendo camera and HDMA refresh

The verified local snapshot now contains **1,009 exact ROM records**, including
**26 SNES records**. Pilotwings is added only after its corrected DSP-1 paths
pass normal conversion, packed CPU/frame/PCM comparisons and fresh-process
states. Five existing SNES controls are requalified. Twenty other SNES records
and every other console's records are preserved exactly. A short Mario Kart
race is also compared through native/reference execution; neither that route
nor the library claims full-game coverage. CX4 remains interpreted and counted.

Size: **46,497,854 raw bytes / 11,887,011 gzip bytes**, an increase of 261,660
compressed bytes over the preceding snapshot. SHA-256:
`7eb71dba1a291d38087ff980c63f83aeabf71c40450d6c4db5fa843fda6672f1`.
Nineteen RAM patterns without reconstructible ROM references remain private.
The normal report timestamp must follow both main/sound observation journals;
shared hints never replace that validation. No original ROM, firmware, cover,
player SRAM or state is included. The decompressed 64 MiB bound is unchanged.

Evidence: `.build/snes-horizon-hdma-20261012/knowledge-build.json` and packed
receipts in `delivery.json`. The earlier follow-up below records the prior
snapshot and its former Pilotwings exclusion.

## Super Nintendo DMA and enhancement-circuit follow-up

The verified local resource contains **1,008 exact ROM records**, including
**25 SNES records**. Three DSP-1/CX4 revisions are added and three ordinary
controls requalified. Nineteen other SNES records and every other console's
records are preserved exactly. The hints concern the compiled 65816/SPC700
paths; they do not turn the CX4 device interpreter into native code.
Pilotwings' failed projection route contributes no record.

Size: **45,458,546 raw bytes / 11,625,351 gzip bytes**, an increase of 723,864
compressed bytes. SHA-256:
`12b2a90943ea9987a1ae5711f7798b4b719e697b28456d15689deedb060df9a7`.
Nineteen observed RAM patterns without reconstructible ROM references remain
private. Both CPU and sound journals must precede their successful ordinary
qualification report. Packed replays and fresh-process states are checked
separately. No ROM, firmware, player SRAM/state or artwork is embedded in the
shared resource; the decompressed 64 MiB bound is unchanged.

## Super Nintendo cartridge RAM and save follow-up

The verified local resource contains **1,005 exact ROM records**, including
**22 SNES records**. Four additional RPG revisions are qualified and four
existing controls are requalified; all other records remain unchanged.
The common runtime now covers ordinary cartridge battery files, SRAM code
windows and a larger bounded RAM observation set, with fetched-opcode checking.

Size: **42,665,032 raw bytes / 10,901,487 gzip bytes**, an increase of 953,001
compressed bytes. SHA-256:
`6cd437dfdd1c229085c51efacf85740010973ab9374e1f18bf58f7c6c3a639dd`.
The 4,016 RAM patterns without reconstructible original-ROM references remain
private. The resource still contains only numeric observations and exact-ROM
identities: no ROM, player SRAM, state, artwork or raw sound-driver RAM.
The overall 64 MiB decompressed size bound remains unchanged. Only the SNES
RAM-reference limit grows to 16,384; other console limits stay unchanged.

## Super Nintendo audio and display qualification

The verified follow-up contains **1,001 exact ROM records**, including **18
Super Nintendo records**. Three PAL revisions are added and five SNES controls
are requalified after complete main/sound CPU, memory, video and PCM comparison.
Other consoles and the ten untouched SNES records are preserved exactly.
Updated audio/upload behavior and full display modes come from the common
runtime; no title patch is distributed.

Size: **38,765,930 raw bytes / 9,948,486 gzip bytes**, an increase of 555,244
compressed bytes. SHA-256:
`5bcc7a43d4bacd548d7e9066e0ea6e659966b0f73cbc414108bf0820dba61b6e`.
The 179 RAM patterns without an exact reconstructible ROM source remain private.
Shared records contain numeric ROM references, never raw sound-driver RAM,
operand data, player states, images or ROMs. SNES now also requires both CPU
journals to predate the successful qualification report before promotion.

Actual compressed exports and fresh-process states are checked separately.
See [SNES development and remaining limits](SNES.md). The earlier NES and
released snapshot sections below remain historical evidence.

## Current exploration and cache follow-up

The verified local resource now retains **998 exact ROM records, 36 NES
records and 837 NES RAM entry/opcode references**. Five NES revisions are
requalified on six complete 3,600-frame paths each; the three added paths also
pass in their actual compressed exports, with fresh-process state checks.
The Batman menu replay contributes one newly qualified RAM guard. Other
consoles and the thirty-one unrefreshed NES records remain identical.

Size: **36,397,119 raw bytes / 9,393,242 gzip bytes**, just one compressed byte
more than the preceding lower-ROM/RAM-window snapshot. SHA-256:
`fea6e68bfd4d590852b264f9367b1e0f42617f5088666a1b890b0355424925f7`.

The source cache reuses generated code only. It binds the exact ROM/compiler
and ROM entry input, verifies stored source hashes and applies current RAM
guards separately. Normal tests always run again. Advanced scan observations
are compared with the reference before another compilation pass; final-pass
results are bound to the actual source EXE. Failed or stale journals still
cannot replace qualified shared records. No scripts, raw RAM, player states,
ROMs, artwork or private library enter this resource.

The frozen converter is tested on two separate launches with an initially
empty private library/project. Batman imports all 486 guards from the shared
resource in its first pass; six 600-frame CPU/frame/PCM comparisons pass on
each launch. The second launch regenerates no C source and rebuilds no object
(72 reused), while repeating every reference check. Fresh-process states also
pass. This verifies the bundled resource and stable source/include paths;
dependency/compiler caches are reused, so it is not a cold-toolchain benchmark.

## Lower-ROM and RAM-window qualification after 0.26.0

The local verified snapshot contains **998 exact ROM records**, including
**36 NES records and 836 guarded NES entry/opcode references**. This adds seven
exact NES revisions and requalifies Batman: Return of the Joker; all other
consoles and the twenty-eight unrefreshed NES records are unchanged.
Minelvaton Saga's supplied translated mapper-80 revision contributes 77 guards
for accessible Taito RAM. Only CPU entry addresses and original-PRG opcode
offsets are stored, with the existing exact-ROM and live-opcode checks.

The eight actual compressed exports pass three full 3,600-frame internal
CPU/memory/frame/PCM comparisons each and two fresh-process state continuations
after 720/1,800 frames. Journal freshness remains required. Mapper-40/FME-7
lower ROM aliases are covered by the common translator, not ambiguous seeds
in the upstream upper-address format. Protection state, operands, chip RAM
dumps, player states and cartridge battery contents are never shared.

The snapshot uses **36,397,107 raw bytes and 9,393,241 gzip bytes**, only
**664 compressed bytes more** than the released 0.26.0 snapshot. SHA-256:
`a4a7abf048635759c8d1f18c5ace7b6c71cf49315e63d2e9a9615c7755c8ea57`.

The rebuilt frozen converter passes a real Minelvaton conversion with initially
empty private knowledge and generated projects. It imports all 77 shared guards
in its first pass, reports no interpreted cycles on three 600-frame paths,
matches internal CPU/frame/PCM and passes fresh-process state continuation.
Dependency/compiler caches are reused; this is not a cold-toolchain speed
measurement. The audited EXE contains this exact final snapshot and current
native sources, with no ROM, player state or raw private library.

## Released 0.26.0 snapshot

Release 0.26.0 retains exact-ROM NES RAM entry/opcode observations
alongside ROM seeds. Shared `ram_opcode_refs` contain only a CPU entry address
and an offset of that opcode in the user's PRG ROM. The converter reconstructs
the opcode from the supplied cartridge, then guards its live RAM value before
calling a precompiled instruction body. Operands remain live; no private RAM
dump or operand data enters the shared resource.

NES journal freshness is checked against the successful conversion timestamp,
so later failed/stopped observations cannot replace a qualified shared record.
Local build candidates can accelerate a retry but never skip validation.
RAM-bearing conversions compare all their configured coverage frames against
the internal CPU, including exact PCM. A configure receipt binds the inserted
guards so the pinned build bridge cannot silently regenerate them away.

The qualified snapshot bundled in 0.26.0 contains **991 exact ROMs**, including
**29 NES records and 759 guarded NES RAM entry/opcode references**. The latest
eight-cartridge gate adds four exact revisions and requalifies four records;
all other consoles and twenty-one unrefreshed NES records remain unchanged.
Batman: Return of the Joker contributes 485 guards for enabled FME-7 RAM,
after the actual compressed EXE passed three full 3,600-frame CPU/frame/PCM
comparisons and later fresh-process state checks. The snapshot occupies
36,394,933 raw bytes and 9,392,577 gzip bytes, only 3,089 compressed bytes more
than the preceding guarded-RAM snapshot. SHA-256:
`cbe3c07a9c6dc6fc0b3ab25f495982ebc236175a26288f4f130a09b4e026ef8b`.
The isolated Zelda check used an empty private library and empty generated
project, importing its 186 guards from the shared resource in its first pass.
Dependency/compiler caches were reused; this is not a cold-toolchain speed
measurement. The exact tested record is unchanged in the final snapshot.
The latest isolated FME-7 check likewise starts with empty private knowledge
and generated projects, imports all 485 shared Batman guards in its first
pass and passes three 600-frame internal CPU/frame/PCM comparisons. The
compressed result repeats those comparisons and passes fresh-process state
checks. Its tested record and snapshot hash match the final bundled resource.

Release 0.25.0 includes the final Mega Drive campaign: 24 new exact ROM records
and eight requalified records, only after ordinary strict conversion and actual packed
EXE replay. The snapshot shipped in that release contains **985 exact ROMs**: 258 SMS, 1 GG,
606 GB, 23 NES, **82 MD** and 15 SNES. It occupies 36,384,534 raw bytes and 9,387,948 gzip bytes.
SHA-256: `0f5d8d30e831021fba5301e006af373f0b5f46b941af542ae70bc4ec804ad03c`.

All other consoles and unrefreshed Mega Drive records are unchanged. Numeric
observations reconstruct guarded bodies from the user's exact ROM; raw ROM,
private driver bytes, player states, artwork and diagnostic traces are excluded.
An isolated empty private library converted Golden Axe II using its qualified
shared record in a staged ROM-free resource, with ordinary reference checks,
packed replay and fresh-process states. Integration verifies that the exact
tested ROM record is unchanged in the final shared snapshot.
Dependency/generated-code caches were reused; this was not a cold-toolchain
speed benchmark. The locally packaged converter was audited against this exact
snapshot and current source inputs. The original-ROM archives and protected
Shining Force II player state are unchanged.

The earlier cartridge-hardware refresh is recorded below as historical evidence. The decompressed resource budget is now 64 MiB, shared by the
builder, bounded loader and package audit, to retain qualified observations
across consoles. Distribution still uses gzip. Numeric allowlists, exact-ROM
binding and reference-before-learning gates are unchanged; an oversized refresh
fails before replacing the previous snapshot.

The EEPROM/Sega-mapper development refresh adds four exact Mega Drive ROMs only
after normal strict advanced conversion and final packed-EXE reference checks:
Wily Wars, NBA Jam, NBA Jam Tournament Edition and the original 5 MiB Super
Street Fighter II. All five scenarios per ROM have zero main/sound fallback;
the additional packed checks identify and hash each exact executable. EEPROM
protocol and mapper tests are independent authored fixtures, not shared game
data. Actual battery boot and fresh-process F8/F9 remain separate evidence.

That earlier ROM-free snapshot had 961 identities (258 SMS, 1 GG, 606 GB,
23 NES, 58 MD, 15 SNES), 31,221,890 raw bytes and 8,099,305 compressed bytes.
SHA-256: `ea1a025e31f80fa6c7ace1ba493879d128f913bcaec40ee5914feea8cf995bca`.
All previous records and other consoles are unchanged. MD code observations
for a mapped cartridge use physical ROM offsets, with the learning key checked
against the actual fetched instruction before a bank-changing operation.
The refreshed snapshot is included in the locally rebuilt and audited
`Export/Retro-Recomp.exe`: all 168 resources and 63 frozen Python modules match
the current public source inputs. Raw private libraries, ROMs, chip save bytes
and artwork are not bundled. Evidence:
`.build/md-cartridge-hardware-20261011/qualification.json`. That earlier block did not promote
Mega Drive beyond experimental or qualify all cartridge circuits.

Regeneration also separates current export identity from stale revision reports.
When reports disagree about one filename, the branded full ROM identity in the
EXE resolves ownership. Source names are matched per executable and exact ROM,
so an older revision's generic filename cannot turn the current source into a
duplicate. Ambiguous files remain protected; byte-identical renamed games still
use the normal duplicate rule. This is common batch code for every console.

The advanced Mega Drive scan now explores the original attract sequence for at
least 18,000 frames, alongside the existing play, varied-input, early-start and
menu/dialogue routes. Exact-ROM observations from late transitions need the
same reference comparison and final native regeneration as earlier paths. This
extends qualification coverage; it does not prove the remainder of a game.

Mega Drive partial refresh now also rejects either CPU's local observation file
when it is newer than the successful exact-ROM conversion report. This closes
the stale-report gate after an unfinished/failed later scan. The previously
verified shared record is retained; the new private union needs qualification
before it can replace that record. Missing qualification dates fail closed.
Successful 16-bit conversion reports now record their completion time in UTC
after strict validation and the final observation update. The three reports
produced immediately before this metadata correction were dated only from their
actual successful conversion receipts, after verifying the exact ROM/EXE,
unchanged observations and subsequent long reference/state replay. Their
original reports and receipt hashes remain in the local qualification evidence;
filesystem modification times are never substituted for a missing qualification.
The regression includes both the 68000 and Z80 files and preservation of the
previous snapshot. `tools/megadrive_progression_selftest.py` adds longer real
two-port controller traffic and fresh-process state replay; its reports remain
local and cannot themselves bypass the conversion's normal reference gate.

The suspended-fetch follow-up changes common Mega Drive guarded Z80 execution,
with a counted continuation when the actual opcode differs after a bus wait.
Only Sonic 1, Sonic 2 and Shining Force II are requalified by exact ROM. Their
verified snapshot is embedded in the local converter; other records are intact.
The independent mutation/interrupt fixtures and isolated cold libraries are
not bundled as cartridge knowledge. A new hardware descriptor identifies known
EEPROM boards despite missing save headers and recognizes the tested Sega SRAM
replacement; it supplies no borrowed code roots or runtime save implementation.
Evidence: `.build/md-suspended-fetch-20261011/qualification.json`.

The local-BUSACK follow-up changes common Mega Drive bus-control rendezvous and
sound-CPU machine-cycle scheduling. It also distinguishes immediate interpreter
entry signals from completed-instruction counters without weakening reference
validation. Only Sonic 1, Sonic 2 and Shining Force II are eligible for an
exact-ROM knowledge refresh after qualification. Authored bus/state fixtures,
player states and private raw observations are not bundled. The verified
ROM-free snapshot is included in the locally rebuilt converter. Evidence:
`.build/md-local-busack-20261011/qualification.json`.

The CPU-pause follow-up fixes common Mega Drive STOP deadlines and the wall
clock used after a pending Z80 transaction is released from BUSREQ/reset.
Only Sonic 1, Sonic 2 and Shining Force II are requalified by exact ROM here.
The verified snapshot is refreshed only after native/reference qualification
and embedded in the local converter; player states, ROMs and private raw
observations remain excluded. These timing fixes are shared runtime code,
not per-game hints. Evidence: `.build/md-cpu-pauses-20261011/qualification.json`.

The Z80 phase follow-up changes shared Mega Drive code, including memory-cycle
placement and impossible-budget validation. Only Sonic 1, Sonic 2 and Shining
Force II are eligible for exact-ROM requalification in this block. The refreshed
verified snapshot is included in the locally rebuilt converter after validation;
raw driver observations, player states and the private campaign database are
not bundled. Authored phase fixtures are test sources, not cartridge knowledge.
See [the timing evidence](MEGADRIVE_Z80_TIMING.md).

The Mega Drive internal-wait follow-up changes the common bus scheduler, not
per-game code: explicit 68000 internal work can yield to external Z80 requests,
and retirement retains a modular clock budget. Sonic 1, Sonic 2 and Shining
Force II are requalified by exact ROM after the usual native/reference checks.
Only these three records are eligible for refresh; authored timing fixtures and
player states remain outside the bundled knowledge.

The shared xBR presentation filter is bundled as common host code, with its MIT
notice. It is not a cartridge patch or a compilation observation. Only Super
Mario Bros.' exact NES record is requalified for this display follow-up; the
verified snapshot remains unchanged. No game images enter the shared library.

The NES audio-continuity follow-up changes common output delivery and strengthens
conversion validation with exact native/interpreter PCM comparisons. Only Super
Mario Bros.' exact record is requalified here. No ROM bytes, recordings or
per-game audio workaround enter the shared snapshot; future NES exports use the
same updated host and checks. Native coverage remains separate from sound-device
delivery, physical latency and listening validation.

The Game Boy audio-output follow-up likewise changes the common host, not
cartridge code or APU synthesis. Super Mario Land 2 and Tetris are requalified
by exact ROM identity after coverage and deep reference-CPU checks. The verified snapshot
contains no audio, ROM bytes, private measurements or per-game latency patch.
The updated common output code is bundled with the converter for future exports.

The Master System audio-latency follow-up changes shared host output buffering,
not cartridge translation or PSG behavior. Alex Kidd's exact record is
requalified after native/reference checks; no PCM, audio traces or per-game
latency workaround is added to the bundled knowledge. See [audio evidence and
measurement limits](AUDIO.md).

Master System sprite investigations also distinguish compiler observations from
hardware display limits. Double Dragon exposed the original eight-sprite
overflow and alternating sprite order, not a missing native entry. The shared
renderer now offers an optional presentation enhancement, including stabilization
of confirmed rapidly reversing overlap priorities, while preserving guest
collision/overflow behavior. It also suppresses collisions in the blanked left
column. The fix is shipped as common source, not a per-ROM patch or artwork hint.
Only Double Dragon's exact record is requalified for this follow-up; no bulk
campaign or raw diagnostic data enters the bundled knowledge. See [video
diagnosis and separate evidence](VIDEO.md#sprite-flicker-and-the-optional-master-system-enhancement).

The 68000 step backend now guards RAM bodies against the actual fetched image,
including stale words retained by its two-word prefetch queue. The prepared
body remains stable through retirement. Queue state/hash and impossible bus
budgets are part of exact-ROM validation; shared hints never bypass those gates.
See [prefetch qualification and explicit exclusions](MEGADRIVE_PREFETCH.md).

The MOVE/MOVEM and exception-phase follow-up retains those gates. Destination
extensions use the values fetched after the source read; an incomplete interrupt
cannot become a disk snapshot. External synthetic transaction tests qualify the
shared compiler/runtime separately from cartridge observations. They are not
inserted as game hints, and internal reference agreement alone cannot replace
them. Only the targeted exact-ROM records are refreshed after successful checks.

The earlier Mega Drive video qualification added complete interlace capture and
clock-driven horizontal counters/HBlank after CPU exceptions and RAM mirrors.
Authored video patterns, a separate counter reference and targeted cartridge
conversions stay separate from hardware and gameplay evidence. See the
[video checks and remaining limits](MEGADRIVE_VIDEO.md).
RAM observations retain exact-ROM ownership and live-byte guards. One native
body can cover the same physical RAM bytes at all console aliases without
changing relative PCs or importing another cartridge's code. That refresh requalified
three exact Mega Drive cartridges and added Sonic 2's newly reached observations.
The MOVE/MOVEM and exception-phase qualification revalidated the same three exact cartridges
without adding observations or changing other records. The snapshot remains 955 exact identities,
including 52 Mega Drive revisions, at 7,755,201 compressed bytes. These counts
describe reusable observations, not complete compatibility or gameplay coverage.

RetroRecomp keeps useful discoveries for each console and exact cartridge
revision. Converting more cartridges can expose new compiler or runtime cases;
those findings help us improve the shared source code. Conversion itself does
not automatically rewrite the compiler, and a finite catalogue does not make
scripted tests exhaustive.

## The base of paths beside the converter (since 1.5.4)

Since 1.5.4, **Retro-Recomp.exe contains no paths**. The base of paths is a
separate file, `Retro-Recomp-base.zip`, laid beside the executable by the
installer and the built-in update, and kept up to date in `datas/knowledge/`
(see *The shared base*). Before 1.5.4, `assets/compilation-knowledge.json.gz`
was a snapshot embedded in the executable; it stays in this repository as the
source of the maintainer's campaigns, which enter the base as qualified paths.
New discoveries remain in the converter's local `datas/library`; both sources
are combined when preparing a game. Generated game executables already contain
their compiled code and do not need this base, this library or learning logs
to play. Without any base and without a connection, the converter discovers
everything itself, as before, and says so.

Each record is bound to the console, full ROM SHA256, byte size and compiler
engine revision. A different cartridge revision or engine cannot reuse it.
Missing, invalid or incompatible records leave normal discovery and validation
enabled. Local observations remain available alongside the base.
This also applies to Mega Drive and Super Nintendo: neither the known-game
catalogue nor this base is a conversion allowlist. Eligible unknown
cartridges are analyzed directly, then validated before their discoveries
can enter the base.

The base contains numeric instruction addresses, bank identifiers, hashes
and offsets into the user's own ROM. It contains no ROM bytes, copied audio
drivers, artwork, executable code, credentials, titles or machine paths.

| Console | Reusable information |
| --- | --- |
| Master System / Game Gear | Verified banked instruction entries and ROM offsets for guarded RAM patterns |
| Game Boy | Observed ROM instruction entries by bank |
| NES | Observed ROM entries by 4 KB physical bank |
| Mega Drive | ROM entries and ROM offsets for guarded 68000/Z80 RAM variants |
| Super Nintendo | ROM offsets for guarded RAM variants and SPC700 opcode masks |

RAM patterns can be shared only when their bytes can be reconstructed from the
same user-provided ROM. Other dynamic patterns stay local. Existing live-memory
guards still apply, and an unknown case can use the reported interpreter fallback.
The snapshot never bypasses the native/reference validation gate.

### Maintainer snapshot: Stunt Race FX two-player paths (27 October 2026)

The maintainer snapshot `assets/compilation-knowledge.json.gz` holds the Super FX games' paths
since the nine cartridges of 26 October (built from their Extended conversions; not a game-side
fingerprint input, `compilation_inputs._resource_paths` skips it). Stunt Race FX's record was
refreshed after its authored two-controller route `authored-2p` ([SNES_SUPERFX.md](SNES_SUPERFX.md))
was learned: one Extended conversion on Windows with an empty private library
(`RETRO_RECOMP_LIBRARY_DIR`), then `build_compilation_knowledge.build()` for that one ROM with the
previous snapshot as `--base` (the same tool and the same qualification rule as for the nine
cartridges; a maintainer campaign is qualified at once). Only this record changed: RAM-variant
references 4,209 to 5,139 (none lost; the 930 new ones are the code of the two-player mode),
SPC700 delta lists rewritten (256 lists, 109 of them longer), SNES entries 536,490 to 538,350,
compressed 29,087,239 to **29,093,134 bytes** (+5,895), raw 120,403,159 to 120,437,012 bytes
(budget 128 MiB), SHA-256 `07d0e81bb3e14e042a8bcd4112d6fd0027afa8080997cc491ba25440e760e9e2`; every
other record of every console is identical. Producing the separate base that the installer lays
beside the converter from this file is not part of this change.

## Schema 3 of the paths: CPU-keyed (27 October 2026; travels in the exchange and the base, read by the conversions' code since 1.6.0)

Stage B1 of the standardisation ([STANDARDS.md](STANDARDS.md), "Paths") adds `retrorecomp/path_profiles.py`.
It is the schema 3 of the compilation paths: a game record owns one section per CPU (`m68k`, `z80`,
`mos6502`, `sm83`, `w65c816`, `spc700`) with its memory map, plus cartridge-device sections, and every
pointer names the source it points into (`rom`, or Neo Geo's `p`, `bios`, `m1`, `sm1`). The module holds:

- the per-CPU profiles (`PROFILES`: alignments, address windows, lengths, caps, the SPC700 budget), which
  are plain data a web validator can be generated from (`profile_table()`);
- the integer codecs (`list`, `const`, `delta` with a step, `sdelta`, `ranges`, `bitmap32`) behind
  column-wise tables: lossless, order and repeats included, and bounded before anything is expanded;
- `validate_game`, one validator driven by those profiles, for the seven consoles of the snapshot and, as
  provisional shapes without data, CPS-1, X68000 and the GSU / CX4 / DSP-1 devices;
- `to_v3` and `to_legacy`, adapters to and from the schema 1 records of every console, Neo Geo's own record
  included. `to_legacy(to_v3(record)) == record` exactly.

**What uses it.** Since stage B2 (below) the exchange file, the shared base and the upload carry schema 3. Since
stage B3 (further below) `knowledge.py` delegates to the module, so the module is a **game module** in every
console's game stamp (it left `INTERFACE_MODULES`), and the readers of the local banks accept both schemas. The
local banks (`qualified.json.gz`, `imported.json.gz`, `imported-observations.json.gz`) and the maintainer's snapshot
are still **written** in schema 1; every consumer of the paths still works on schema 1 records.

Where schema 1's shared validator is looser than the local code that uses the hints, schema 3 follows the local
code (`STRICTER_THAN_V2`): Mega Drive RAM references (bus address `0xE00000..0xFFFFFE`, even length 2 to 16),
Mega Drive Z80 references (pc outside `0x4000..0x7FFF`, length exactly 4), Super Nintendo RAM references (length
exactly 4, 24-bit address). The snapshot has no row on the wrong side of any of them.

Measured on the maintainer snapshot (1,609 records, all of them round-trip and validate): 120,327,522 bytes of
compact JSON become 84,116,672 (-30 %), and 28,959,865 bytes of gzip become 17,808,782 (-39 %). Mega Drive goes
from 10.6 to 2.0 MB gzipped, Game Boy from 2.0 to 0.8 MB; Super Nintendo shrinks by only 6 % raw and 9 % gzipped because
its 56 MB of `spc_deltas` are carried as they are (a per-list codec was tried: -35 % raw, +4 % gzipped); Neo
Geo is 4 % larger gzipped. Small records pay about 260 bytes of structure each. The numbers are printed by
`tests/test_paths_schema.py`, not asserted.

`tests/test_paths_schema.py` checks the round trip on fixtures of every shape and on a deterministic sample of
the snapshot, the accept/reject parity with `knowledge.validate_payload` and
`neogeo_knowledge.validate_record` on a mutation corpus (every column of every field swept with boundary and
wrong-type values), and the codecs. `RETRO_RECOMP_PATHS_FULL=1` runs the whole snapshot (about a minute and a
half and 1.2 GB of memory) and the 262,144-row SPC700 caps.

### Schema 3 travels (stage B2, 27 October 2026)

Three things carry schema 3, all of them in interface modules (`knowledge_exchange.py`, `online.py`; no game-side
module is touched, so no game stamp changes):

- **`.rrknowledge` version 3.** The header, the titles and the observations are those of version 2; `knowledge` is
  `{"schema": 3, "games": {"system:identity": <schema 3 record>}}`, validated by `path_profiles.validate_games`.
  `read_exchange` reads versions 1, 2 and 3 and always hands the paths back as schema 1 (its down-projection
  `paths_from_v3`, checked by the schema 3 validator first and by `validate_payload`, Neo Geo's included, second), so
  `import`, the discovery counts, the claims and the builder see the same records whatever the version. A file
  written by `write_knowledge` is **version 2 unless asked otherwise**: a converter or a service older than 1.6.0
  refuses version 3 as "not a knowledge file". `version=3` writes schema 3, and writes version 2 instead when a
  record has no valid schema 3 form (schema 3 is stricter in a few places, `STRICTER_THAN_V2`; `fallback=False`
  raises). Since 1.6.1 an account upload is always written as version 3 (1.6.0 asked `GET status` for
  `knowledge_versions` first, for services that did not read 3; every service of 1.6.0 and later does, so the question
  and `online.upload_version` are gone; a record schema 3 refuses still makes that one file version 2). A file
  exported by hand stays version 2, which every receiver reads.
- **Shared base, format 3 (its only format since 1.6.1).** The base is one line, format 3, `GET base3`. 1.6.0 published
  a second one, line 2 (format 2, `GET base`), for the converters up to 1.5.x; 1.6.1 retired it (see *One line
  (1.6.1)* below). A format 3 entry has the shape of a format 2 entry (`qualified`, `parts`) with schema 3 records and
  `cores` in place of `engine`: the engine identity of the whole record, the very string format 2 called `engine` (a
  Neo Geo record: `<core>:<loader>`); the word is the one a later per-CPU qualification will keep. A format 3 index
  and archive (`manifest.json`, `index.json`, `entries/<sha>.json`, the entries named by the SHA-256 of their
  canonical text, as before) say `"format": 3` in both, and a mismatch is refused, as is any other format. The
  converter reads that format only: `base_entry` returns a format 3 entry with `engine` and schema 1 records (an
  element whose schema 3 record is invalid or has no schema 1 form is skipped like a malformed one, never the game),
  so the qualified bank is still written in schema 1 and `base-use.json`, the claims and the rejections do not know
  the schema of the base.
- **The up-projection.** `knowledge_exchange.entry_to_v3` converts one entry that the builder grouped from the
  uploads' schema 1 records into a format 3 entry (every game keeping its sources); what has no schema 3 form is left
  out and counted. The down-projection (`entry_to_v2`, `project_base`) went with line 2. The builder reads every
  entry back with `base_entry` before it publishes.

**One line (1.6.1).** A converter reads `GET base3` (its manifest, `GET base3/files/retro-recomp-base3-<A>-<N>.zip`
for the differences, a complete base from its registered address, `retro-recomp-base3-<N>.zip`) and nothing else:
`GET base` is not asked any more. The compatibility owed is to the release before (1.6.0): its local base, the
installer's copy and the files it wrote are read as before; a downloaded base of format 2 left by a 1.5.x-era disk is
set aside and the installer's copy (format 3) takes its place, and a manifest in another format ends in the "update
Retro-Recomp" message. Revocations, the quarantine and the cursor come from the same manifest. The service keeps
a small answer at `GET base` for the converters of 1.6.0 alone (they ask it first); this converter never does. When no difference leads from a base to the latest version and no complete base
is newer (the player skipped more versions than the service keeps differences for, a handful of nightly versions),
the update says so (`no_path`) and the base in use stays; a new program brings a newer installer's copy.

Measured on the 72 uploads in the maintainer's cache plus the 1,609 campaign records (1,723 games, 26 October
2026, Hermes test service): the entries come to 128.8 MB of JSON in line 3 against 173.6 MB in line 2, the complete
base is 27.7 MB (line 3) against 42.2 MB (line 2), the index is the same size, and no record lacked a schema 3 form.
The change of the file is paid once: a converter on line 3 downloads differences of the new format, which for
the same games are smaller too.

`tests/test_paths_exchange.py` checks version 3 files (written, read, refused: a schema 1 payload in a version 3
file and the reverse, a record outside its source, a game under another key, a machine that shares nothing yet, a
device, two cores), the fallback to version 2, the import of both versions into the same banks, the entry
up-projection (a skipped element never drops the game), the archives and indexes (format 3 only; format 1 and 2 are
refused), and the update against a fake service: the manifest and differences come from `GET base3` and the stub is
never asked, the installer's copy follows by difference, a downloaded base of format 2 is set aside, `no_path` keeps
the base, and an upload is a version 3 file whatever `GET status` lists.

### Stage B3: the conversions follow the module (27 October 2026)

`knowledge.py` stops keeping paths logic of its own and delegates to `path_profiles.py`. This is the one stage of the
standardisation that moves the game stamps on purpose (1.6.0); what a conversion generates does not move.

- **One table, one validator.** The schema 1 fields (`LEGACY_FIELDS`, row width and row cap) are kept once in
  `path_profiles`; `knowledge.FIELDS` and `neogeo_knowledge.FIELDS` are that very dictionary (the Neo Geo copy is gone),
  and the schema 1 rules of `knowledge.validate_payload` moved there unchanged (`validate_legacy_payload`): the old
  and the new validator give the same verdict on 24,727 cases (the whole mutation corpus of the tests and the sample of the
  snapshot). They are not replaced by `validate_game`, which is stricter in six places (`STRICTER_THAN_V2`): a bank
  that was readable must stay readable. `neogeo_knowledge.key` is `path_profiles.ng_key`.
- **Local banks, both schemas.** `knowledge.read` (the reader of `qualified.json.gz`, `imported.json.gz` and the
  maintainer's file) dispatches on `schema`: 1 as before, 3 through `validate_games` and the adapters, handing back the same
  schema 1 view. The games of a schema 3 bank that have no schema 1 form (CPS-1, X68000) are `knowledge.read_games` /
  `qualified_game` / `imported_game`. Banks are still **written** in schema 1 (`write_packed`, `write_qualified_bank`,
  `discard_imported`). The strong reason to change that, not applied here: CPS-1 and X68000 records cannot be written
  in schema 1, so the day those machines share paths the writers must write schema 3 whenever a game has no schema 1 form,
  and a schema 3 bank must never be rewritten by a schema 1 writer (it would drop those games).
- **`knowledge_stamp`** hashes the game's own record in its schema 1 form (the legacy projection, so a record whose content
  did not change keeps its stamp whatever schema its file is in). Neo Geo hashed the whole Neo Geo bank and took no
  imported hints; it now hashes the record of its key (`SystemProfile.knowledge_identity`: key(prepared cartridge, BIOS),
  the ROM's hash for every other machine), imported record included. CPS-1 and X68000 hashed a constant and hash their
  schema 3 record as soon as a bank holds one (a constant, `{}`, when there is none, as before).
- **One of each.** `knowledge.bundled_record(system, rom, engine)` replaces the copies in `gameboy.py` and `nes.py` (the
  Mega Drive and Super Nintendo modules keep a one-line wrapper that names their engine). The key patterns of the
  interface (`online._ROM_KEY`, `knowledge_exchange._GAME_KEY`) are `path_profiles.game_key()` over `SHARED_SYSTEMS`:
  sharing CPS-1 or the X68000 is one name in that list. The feedback kinds already come from the profiles
  (`feedback.KINDS`), one registry. **Left for later**: the three copies of the decoders from observed rows to paths
  (`feedback.sega_candidates` / `knowledge_build._sega_rows`, `feedback.gb_entries` / the loop in `gameboy._known_entries`,
  `feedback.nes_sites` / `nes._row_sites`): `feedback.py` is being changed by the X68000 identity step (6a), so they are
  merged once that is in.
- **Stamps.** `path_profiles` left `INTERFACE_MODULES` and is listed for every console in `stamp_inputs.INPUTS`; it is
  therefore a game input of all nine consoles, like `knowledge.py`. Every console's **game** stamp moves once; the host
  and build stamps, and `LEGACY_GAME_STAMPS` and `RR16_STATE_COMPAT_ABI` (release procedure) do not. The knowledge
  stamp of a game with an unchanged record is unchanged.
- **Neo Geo leaves `LEGACY_GAME_STAMPS`.** A Neo Geo receipt written before 1.6.0 carries a knowledge part that is the
  hash of the whole Neo Geo bank of its time; 1.6.0 hashes the record of the game's key. The two can never be equal, so
  the 1.4.1, 1.5.1 and 1.5.2 entries could never be recognised (`legacy_games` hashes the game part, knowledge part
  included). They are removed, with a comment in `stamp_inputs.py`, and no Neo Geo entry may be added for 1.5.6 or any
  release before 1.6.0. Nothing is lost: the Neo Geo exports of earlier releases are converted in full by 1.6.0, which
  is the safe outcome. The three real stamps stay in `tests/test_legacy_compat.py` as removed values, like the Super
  Nintendo ones.
- **The Neo Geo receipt carries the key the conversion found.** The key of a ZIP set (cartridge prepared, BIOS) is only
  known once a first conversion prepared its cartridge. The batch decides freshness and upgrades with the parts computed
  before the conversion, and, for a profile that declares `knowledge_identity_after_conversion` (the Neo Geo only),
  computes them again before it writes `export_receipt`, so the receipt holds the record the conversion used and the
  next batch finds the same signature (without it, a set with a record in the shared base was converted twice). The
  other consoles' identity does not depend on the conversion: their receipt is written from the parts of before, as
  before.
- **Writers of schema 1.** `discard_imported`, `write_qualified_bank` and the import of shared files read a bank through
  the schema 1 view and write it back in schema 1. They now refuse (`ValueError`) to rewrite a schema 3 file that holds
  a game with no schema 1 form (CPS-1, X68000, several cores), which they would drop; nothing is written then. A schema 3
  bank whose games all have a schema 1 form is rewritten without loss. Not reachable today (no bank is written in
  schema 3). The local reader also checks every schema 1 projection with `validate_legacy_record`, like the exchange
  reader, and sets a game aside that fails it.

**Evidence (27 October 2026, Windows, Python 3.14.5).** Two real short conversions per console (quick scan, one
pass, 600 frames; the ROMs were read in place on the NAS, nothing copied) of the commit before (`bd26c65`, an archive
of it) and of this one, from the very same folder (the generated files contain absolute paths), with the same planted
banks: the campaign record of each game in the qualified bank and a second, smaller record in the imported bank, plus
ROM-free observations for Master System, Game Gear, Game Boy and NES. Games with a record: Master System
Alex Kidd in Miracle World (101 entries) and Action Fighter; Game Gear Factory Panic and OutRun (synthetic imported
entries: the campaign has none); Game Boy Alleyway (1,023 entries) and A-mazing Tater (570); NES 3-D WorldRunner (7 RAM
opcode references) and Airwolf (27); Mega Drive Alex Kidd in the Enchanted Castle (26 RAM references, 8,880 Z80
references) and Art Alive (8,193 Z80 references); Super Nintendo A.S.P. Air Strike Patrol (44 RAM opcode references,
256 SPC700 delta lists) and Alien 3 (4,446 SPC700 ranges); Neo Geo Joy Joy Kid (2,316 BIOS roots) and Flip Shot (1,735
BIOS roots, 529 RAM references). CPS-1 (Nemo) and two X68000 disks (Arkanoid Revenge of Doh, Alien Syndrome) have no
paths: they only show that nothing else moved. Every generated file of the project folder was compared, minus
the run logs, the timing fields of the check results and the hashes of built executables (two runs of the same code
differ there; they were run twice to show it). Result: **all 3,192 + 419 + 520 source files are byte-identical** for
the nine consoles. The exceptions, all fingerprints of the code and not sources: the Mega Drive's
`generation-identity.json` names the code digest of `megadrive.py` (`adapter`, edited here), the X68000's folder name
and `sdk` field are its code stamp, and its `rr_px68k_reference.dll` differs between two builds of the same code.
Removing the banks changes the sources of the Game Boy, NES, Mega Drive and Super Nintendo games, so the comparison
does see the hints. In the stamps only the game part moves (`role_stamps`: game of the nine consoles changed, host and
build unchanged), and the knowledge stamp of the twelve cartridge games is unchanged; the Neo Geo one changes by
design. Windows only: the Linux comparison is a step of the release procedure, as for the other stamp breaks.

## CPS-1 joins the base (step 5 of the standardisation, 27 October 2026; part of 1.6.0)

Arthur set CPS-1 aside on 26 October (its paths were raw RAM words) and gave the go-ahead on 27 October. CPS-1 is **still an
experimental machine in development** and its engine will change again, so its sharing is built to be withdrawn and to
move: a path is qualified only for the engine revision that validated it, the record has a version of its own, one line
switches the whole sharing off, and the "experimental" label stays in every report and in the interface without gating
anything. The guards of phase 6 hold as for Neo Geo: numbers only, an identity that covers every input, a conversion that
starts again without the shared paths when it fails with them, and an audit of what a bogus entry can do.

**What a CPS-1 path is.** The 68000 program ROM and the Z80 sound ROM are translated whole, so a CPS-1 game has paths
only for the instructions it runs from RAM (work RAM at `0xFF0000`, sound RAM at `0xD000`): code the game copied there
or built there. The fresh reference runs of a conversion (every instruction interpreted, before anything was learned)
see all of it. The rule that turns their words into numbers, as Neo Geo does (`neogeo_codegen.generate`,
`neogeo_knowledge.numeric_record`):

- **68000**: the generator's own decoder gives the length of the *first instruction* of the observed window (the
  other words of the window are other data); those bytes alone are searched at an **even offset** of the assembled
  program image (`maincpu`). Row `[address, offset, length]` (`insn`, `0xFF0000` plus the RAM offset, length 2 to 16).
- **Z80**: the instruction's structural bytes (`megadrive_z80.opcode_key`: opcodes and prefixes, never operands) are
  searched at **any offset** of the sound image (`audiocpu`). Row `[address, offset, 4, mask]` (`insn_masked`, address
  `0xD000` to `0xD7FF`, mask 1 to 15 with bit 0 set).
- **What stays private, counted and never shared**: any observation whose bytes are not in those images (built or
  unpacked at run time), one the decoder cannot translate, one that is malformed. Code run from **graphics RAM** (Street
  Fighter II': Champion Edition) is not even observed: the board reports work-RAM and sound-RAM variants only, so there is
  nothing to tie and the report keeps counting those instructions as interpreted. The conversion report's `knowledge`
  block says, per CPU, how many were observed, tied and kept private (and why).
- **Promotion only from fresh reference runs** (`cps1_knowledge.promote`, called by `cps1_conversion` after every check
  passed): never from feedback rows, never from the paths the conversion was offered. The library's `compilation.json`
  holds the record (`record`, `record_source`, `record_counts`); an older record of the same images and engine is merged in.
- **Feedback kind 14** (a ROM instruction the native code did not cover) is recorded by the game and read by nobody, on
  purpose: the program ROM is swept whole, so an interpreted ROM position is one the decoder rejects, and no path can
  change that. It is diagnostic only: never read, never shared, never promoted (a shared file cannot carry it). Kinds 15 and
  16 are the player's private build hints and are not persisted.

**The record** is a schema 3 document of `path_profiles` (`cps1:<identity>`; the identity is the whole romset's hash of
`cps1.py`, so a player with other files receives nothing): sources `maincpu` and `audiocpu` with their sizes **and SHA-256**
(the images the offsets point into), `layout = {catalogue: <MAME revision>, format: 1}`, a `m68k/cps1` section and a
`z80/cps1-sound` section with one `ram_code` block each. It holds no ROM byte, no RAM word and no code; a receiver
rebuilds the rows from its own images (`cps1_knowledge.expanded_rows`, refused when the images' hashes differ) and the
generator guards every instruction with its live bytes at run time, exactly as for its own observations.

**Why it is safe to be wrong.** The validator accepts numbers inside the images' bounds. A bogus entry (the audit of
phase 1, redone for CPS-1: see below) can only be: a RAM address whose live bytes never equal the instruction (dead code,
the guard `guarded_step` / `rr_cps1_ram_native_lookup` fails), or one whose live bytes do equal it, where the translated
instruction is exactly what the interpreter would run, compared on every route with the fresh reference before anything
is published.

**Storage: side banks, not the schema 1 banks.** CPS-1 has no schema 1 form, and the schema 1 writers (`discard_imported`,
`write_qualified_bank`, the import) refuse to rewrite a schema 3 bank that holds such a game. The two options were: write
schema 3 banks whenever a game without a schema 1 form is present, which would change the bytes of every console's bank
the day CPS-1 appears in the base and make a file written by 1.6.0 unreadable for an older converter sharing the folder; or
store those games apart. The second is the safest and is what is done: `datas/knowledge/qualified-v3.json.gz` (paths the
base qualified for this converter's engine) and `imported-v3.json.gz` (other players' paths), each
`{"schema": 3, "games": {"cps1:<identity>": record}}`. `qualified.json.gz` and `imported.json.gz` are never touched by
CPS-1 (tested: byte for byte the same with and without a CPS-1 game), every game of a side bank is checked on its own when
read (a record of a format this converter does not know, or a damaged one, is set aside alone), and removing the sharing
leaves the files on disk, unread. `knowledge.qualified_game` / `imported_game` read them; the knowledge stamp of a CPS-1 game
hashes its schema 3 record from them.

**A rewrite keeps what it did not read.** The writers of a side bank work from a partial reading (`read_side_bank` sets
aside what it cannot use), so `knowledge.write_side_bank` never writes that reading back as the whole file: it keeps, **as
stored** (the game's JSON unchanged), every game it holds that this converter does not read, namely a machine the switch
withdrew or that has no module yet (X68000), a format it does not know (a newer converter's record), a damaged record and a
game beyond the room (`SIDE_GAMES`, 4,096 readable games). The games the caller passes replace the stored ones of the same
key and the file is removed only when no game at all is left; a write that changes nothing does not touch the file. This
holds the promise above for every writer: `write_qualified_bank` (updates from the base), the import (`.rrknowledge` file or
fetched records) and `discard_imported`, whatever console the update is about. Emptying `EXPERIMENTAL_SHARED` and updating a
Mega Drive bank leaves `qualified-v3.json.gz` and `imported-v3.json.gz` byte for byte as they were, and the games are read
again the day the name returns. A file that decodes to something other than a schema 3 side bank (another schema, written by
another converter) is never written over: the writers call `refuse_to_overwrite_side_bank` before their first file and stop
with a `ValueError`, nothing written; a file that cannot be decoded at all holds nothing to keep and is replaced, as the
schema 1 banks are. Tested in `tests/test_cps1_knowledge.py` (`SideBankKeepsWhatItDoesNotReadTests`: every kind of
unreadable game, each writer, the switch off and on again, the room, the foreign file).

**Engine identity (`cores`).** A record carries the cores of its two sections, 40-digit digests (`cps1_knowledge.engine_parts`)
of: the pins of the Mega Drive recompiler (the 68000 semantics and decoder) and of Geolith (Musashi and the Z80 core); the
text of `native/cps1_native.c`, `cps1_native.h`, `cps1_z80_native.h`, `cps1_machine.c`, `cps1_machine.h` (the guards and the
code view) and `md_prefetch.inc` (the source of the generated `cps1_arithmetic.c`), line ends normalised; and `GENERATOR_REVISION`, for the Python that generates the code (a packaged executable
has no Python text to hash, and a bytecode hash would differ between Python versions and split the players).
`tests/test_cps1_knowledge.py` pins the text of `GENERATOR_SOURCES` (`tests/cps1_generator_pins.json`): editing one without
raising the revision fails the test. The base's `cores` for a record is `<68000 core>:<Z80 core>`. A path is qualified only
for the `cores` that validated it: a changed engine makes the qualified paths leave the qualified side bank and come back as
paths to check, with their level, until a conversion of the new engine reaches them (tested with a base whose engine moves).

**A record that can change.** `layout.format` is the version of the CPS-1 record (1 today; `cps1_knowledge.FORMATS` lists
those this converter reads). A record of another format is **left out alone** (`UnknownFormat`): out of a file
(`read_exchange` lists it in `unreadable_games` and drops its title), out of a base entry, out of a side bank, never the
rest. A new format keeps a reader for the old one; the cores change with the engine anyway.

**The switch.** `path_profiles.EXPERIMENTAL_SHARED = ('cps1',)` (inside `SHARED_SYSTEMS`). Emptied: the converter neither
collects, sends, fetches, imports nor reads CPS-1 paths (the side banks stay on disk, untouched, and come back with the name);
a file that names it is read without it (`WITHDRAWN`: its games are left out one by one, the other games of the file stay);
the web limits and the builder (`BASE_SYSTEMS`) read the same list, so the service stops accepting CPS-1 uploads and line 3
stops listing its games, with no change to line 2, the other consoles or the banks. The label "experimental" is not read by
any sharing code (tested) and stays in the report (`status`, `knowledge.machine_status`) and the interface.

**Exchange and base.** CPS-1 has no schema 1 form, so it travels only in `.rrknowledge` **version 3** files and in the
base (which is format 3 only since 1.6.1; before, line 3 alone, and 1.5.x converters never saw it). In the converter a CPS-1 "record" is the schema 3 document wherever a
record travels (`knowledge_exchange.split_payload`, `validate_mixed_payload`, `schema3_only`); **a file exported from the
interface stays version 2** (`write_knowledge` with no version), because a version 3 file makes a 1.5.x converter refuse the
whole file, the other consoles included: the CPS-1 games are left out of it, are not marked shared, and the end of the export
says how many there are and that they travel through the online account (`knowledge_export_cps1`, eight languages;
`schema3_only_left_out` in the answer, the discoveries counted for them taken off exactly as counted, never below zero).
Version 3 is written only when asked for (`version=3`). An account upload is always version 3 (1.6.1), and the per-account route `POST knowledge/fetch` is never asked for CPS-1 (the base is
its only way in). Raw gameplay observations are never shared for CPS-1. A conversion that fails with
the imported paths starts again without them and the paths leave the imported side bank (the batch's retry covers
`imported_game`; `discard_imported` removes the game from `imported-v3.json.gz` and logs it in `imported-rejected.json`).
The qualification rule of `AGENTS.md` is the base's own (`player_qualified`): a path is qualified for a `cores` when a
conversion of another player reached it, validated against the fresh reference (their record is made only from their own
fresh reference runs, so an upload holding the path proves it), for CPS-1 from converter 1.6.0 on; discoveries wait until then.

**Evidence (27 October 2026, Windows, Python 3.14.5).** Measures kept apart, none of them about hardware fidelity or play.

- *Generated sources unchanged.* The three shortest sets of the NAS (Pnickies `pnickj`, Pokonyan! Balloon, Quiz & Dragons;
  none has any RAM code) converted at the Standard level from an archive of the commit before (`5dc1793`) and of this one,
  unpacked in the very same folder, same options, output under `.build`: **318 generated files identical, one different per
  set** (`retro16_state_config.h`, whose `RR16_STATE_ABI` hashes the code of `cps1_build` and `cps1_codegen`, changed on
  purpose). The route results (CPU, RAM, image and sound hashes, native and interpreted counters, traces) are identical
  and every set stays "native code only" and **experimental**. The same holds for any set with no shared path: nothing
  but the (empty) record in the report differs.
- *Audit "a bogus entry stays dead code or a failing guard", redone for CPS-1.* An attacker's record: 2,000 random 68000
  rows and 2,000 random Z80 rows, valid for the validator (real image sizes and hashes, aligned offsets inside the real
  images), in the imported side bank of Pnickies. The conversion passed with 3,587 guarded variants generated (1,771 for
  the 68000, 1,816 for the Z80; the others did not decode or had no body), the executable grew by 4.3% (2,446,336 to
  2,552,832 bytes), the route hashes and traces equal those of the clean conversion, 0 interpreted opcodes on both CPUs,
  and the promoted record stayed empty (the bogus paths are not what a fresh reference run executed, so they never
  re-enter the shared record). The guards are the live-byte comparisons of `guarded_step` and
  `rr_cps1_ram_native_lookup` / `rr_cps1_z80_ram_lookup`: a variant whose bytes the game never puts at that address never runs.
- *End to end on the Hermès test service* (`std/cps1-base` of the private site deployed there; production untouched; the
  converter header is patched to 1.6.0 in the script, the number the worktree does not carry yet). No available CPS-1 set runs
  RAM code, so the "discovery" is built with `promote()` from windows of **real instruction bytes of the real Pnickies
  program and sound images** (the instructions a game would copy to RAM), decoded by the generator's own decoder; the
  sharing, the service and the base are the real ones. Account A uploads 4 + 2 paths (file version 3, 655 bytes, accepted,
  claims "6 paths, 6 new"; the file holds no instruction bytes). Builder run 1 (version 7): CPS-1 appears in line 3 only (6 games
  in line 2, 7 in line 3), one part, **0 qualified**: the discovery waits. Player C (an installer's copy of line 3, version 7)
  imports it: 6 paths in the imported side bank, 0 qualified, the schema 1 banks hold no CPS-1. Account B (another account,
  its own fresh reference) uploads 5 + 3 paths (663 bytes; "8 paths, 2 new"). Builder run 2 (version 8): **one qualified
  element by players** for the two accounts' common 6 paths, tied to the `cores` of this converter. C updates by the 1.8 KB
  line 3 difference: 6 qualified paths, 8 to check. A real conversion of Pnickies with those paths takes the quick check
  ("paths qualified in the base"), generates 5 + 3 guarded variants, passes against the fresh reference with 0 interpreted
  opcodes. Twelve uploads that carry ROM bytes or malformed numbers are refused (422 `invalid_knowledge`; not gzip 400): an
  extra "words" field, bytes in the sources, a source without its hash, an odd or out-of-window RAM address, an offset past
  the image, a column claiming a billion rows, a raw observation row, schema 3 in a version 2 file, schema 1 in a version 3
  file, a record under another key; a record of format 2 is skipped alone ("empty" file); the good one is accepted (201).
- Local tests: `tests/test_cps1_knowledge.py` (36 tests: translation with attachable and unattachable fixtures of both CPUs,
  the SF2CE case, round trip from the player's own images, the record and its format, the engine moving with each of its
  inputs, the side banks and their bytes, exchange files of both versions, the base with a moving engine, the switch, the
  experimental label, kind 14) and the updated schema tests.

## Sharing discoveries between converters

The toolbar's **Knowledge** menu exports and imports `.rrknowledge` files.
**Export my discoveries** first counts them, without writing anything. A game
is included when the user's own qualified conversions found hints that the
knowledge bundled with this converter version lacks; its whole qualified
record is shared. Unqualified reports, journals modified after their report,
RAM patterns without the source ROM and games whose ROM cannot be found again
are left out and counted in the summary.

Games whose gameplay hints (F12) are newer than their last conversion also
share those **raw observations**. Each one becomes `[kind, address,
auxiliary, length, ROM position]`: the bytes the game recorded are replaced by
where they appear in the player's own ROM. Code the game built in RAM, absent
from its ROM, has no such position and stays local (counted as `ram_only`).
Once a game is reconverted, its observations are consumed and it shares
qualified hints instead, never both for the same discoveries.

Only those games need their ROM; they are found like for Reconvert, from
remembered paths and then each console's ROM folder in Options. Each game's
result is cached in `datas/knowledge/discoveries-cache.json.gz` under its
files' sizes and dates, the compiler, the converter version and the ROM
folders, so a later export only revisits games that changed (on a 1,068-game
collection: 20 s for the first export, 0.1 s for an unchanged one). With
nothing new, a message says so and no file is offered. Otherwise a small
"achievement unlocked" card shows the number of discoveries (hints unknown to
the bundled snapshot, plus raw observations) before the save dialog opens.
`datas/knowledge/shared.json` records, per channel, what each game last
shared, so a later sender can send only what changed.

The file is gzip JSON: a `retro-recomp-knowledge` header (format version,
converter version, UTC date), a short title per game, a payload with the same
schema, fields and limits as `assets/compilation-knowledge.json.gz`, and
(format version 2) the ROM-free observations, at most 4,096 per game. Version
1 files still import, and so do version 3 files (1.6.0), whose payload is the CPU-keyed schema 3 (see *Schema 3 of
the paths*): a file is written as version 2 unless the receiver is known to read 3.
The title is there for people only. The file holds no ROM byte, path,
artwork, code or account data. The export uses the shared builder
`retrorecomp/knowledge_build.py`, which also builds the bundled snapshot.
Master System, Game Gear, Game Boy, NES, Mega Drive and Super Nintendo are
included. Neo Geo, X68000 and CPS-1 keep their own, separately scoped
knowledge and are not exchanged.

**Import shared discoveries** first checks the chosen file. It validates the
whole file: unknown keys, paths, non-numeric values, unknown consoles,
oversized files or unprintable titles reject it. It then counts the hints and
observations that are neither bundled, local nor already imported. With none,
nothing is imported; otherwise the same card shows the count and asks before
importing. Accepted records go to `datas/knowledge/imported.json.gz`,
observations to `imported-observations.json.gz`, titles to
`imported-titles.json`. A conversion reads imported observations back from
the player's own ROM, only for that exact cartridge, and gives them the same
byte guards and checks as local gameplay hints. The import is additive: records of every compiler
revision are kept and merged per ROM. The summary counts new, enriched and
already known games. The private `datas/library` and the bundled snapshot are
never modified.

At conversion time, the bundled record for the exact ROM SHA256, byte size and
compiler revision is merged with the imported record for the same ROM SHA256
and byte size, whatever compiler revision found it: engine revisions are
expected to change rarely per console, and an imported hint only guides
discovery. Hints may still be wrong for another revision, so errors are
handled. Every conversion runs the native/reference validation gate and
reports any remaining interpreter fallback. A conversion that fails while the
imported bank holds hints for its ROM is run once more without them; if that
succeeds, those hints leave the bank and the rejection is logged in
`datas/knowledge/imported-rejected.json`. If it fails again, the hints were
not the cause and stay. An imported record also changes the game's knowledge
stamp, so an export prepared with it is no longer considered current. Shared
files are not qualification evidence: only a qualified local conversion can
add a game to a future bundled snapshot. `RETRO_RECOMP_BUNDLED_KNOWLEDGE=0`
disables both the bundled and imported knowledge.

**Sending to the shared base** (https://retro-recomp.com, open since 1.4.0)
uses the same file. Like exports, it covers Master System, Game Gear, Game Boy,
NES, Mega Drive, Super Nintendo and, since 1.5.4, Neo Geo (see *The shared
base*): the experimental CPS-1 and X68000 are never sent and count for nothing
on the leaderboard until they join the shared base in a later version (the
converter says so when sending). The Knowledge menu and the closing card's *Send and close*
collect the discoveries as above, keep the games not yet sent with this
account (channel `account` of `shared.json`) and upload them after an e-mailed
sign-in code. They are marked as sent only once the server accepted them. A
large first send leaves as several files of at most about 12 MiB of JSON each
(the service refuses more than 16 MiB once decompressed); each accepted file
marks its own games, so an interrupted send resumes where it stopped. The
server checks the structure only; the maintainer revalidates every upload with
`read_exchange`, imports the valid ones into his own converter and reconverts
those ROMs. As for imported files, an upload is not qualification evidence:
only the maintainer's qualified conversions can add a game to a future bundled
snapshot.

Right after each accepted file, the converter sends its **claims**: for every
game of that exact file, the short path keys that `discovery_paths` computes
from it (hints the bundled snapshot lacks and raw observation keys, at most
4,096 of each), whether the snapshot already knew the ROM, and the scan level
of the qualified conversion (standard for raw observations alone). The claims
carry no other data; they let the first finder's points count at once.
Large claims leave in several requests, gzipped. Claims that could not be
delivered (offline, service busy) wait in `datas/account-claims.json` for the
next send; claims the service refuses for good are mentioned once in the log.
With a service that does not know claims, the converter sends the scan levels
as 1.5.0 did.

**Shared paths before a batch, new discoveries after it** (1.5.1). Two
options of Options › Common › Retro-Recomp account, shown once signed in and
both on by default, connect each batch to the shared base. A batch from the
queue and a reconversion from the collection behave the same way.

*Use the shared base.* Before the batch, the converter asks the shared base,
in one request per 128 ROMs, for the paths other players sent for the batch's
exact ROMs (Master System, Game Gear, Game Boy, NES, Mega Drive and Super
Nintendo). The player's own uploads are not served back. Each ROM keeps the
cursor of what it already received, with the best scan level received, in
`datas/knowledge/shared-cursors.json`, beside the imported banks (removing
that folder starts the sync over). Only newer contributions come back; a ROM
whose answer is full is asked again from its new cursor, ten times at most.
What arrives is the same ROM-free numbers as a shared file: every record and
observation row is validated like an imported file and joins
`imported.json.gz` and `imported-observations.json.gz` (an invalid one is
skipped; the banks keep their bounds). The log says how many games received
paths, or that nothing new came.

These paths are then checked exactly like imported hints. Every conversion
still compares native code with the reference CPU. A conversion that fails
while the imported banks hold hints or observations for its ROM runs once
more without them; if that succeeds they leave the banks (logged in
`imported-rejected.json`) and their level no longer allows a quick check.
New shared paths also change the game's knowledge stamp, so an export made
without them is converted again.

The quick path rule: when the best scan level received for a ROM is at least
the level chosen for its console (each console page of Options), and the
imported banks hold its shared paths, the conversion skips discovery. It runs
the quick level from those paths (one pass, capped frames, no long routes),
like an upgrade of the player shell. When the shared level is lower, discovery
runs normally at the chosen level, starting from them. Forcing from the queue
always rediscovers. The log says which ("shared paths, level standard: quick
check instead of discovery", or "…: thorough discovery starting from them"),
and the conversion report records `shared_paths: {level, records, quick}`. A
quick check measures native code against the reference CPU on the quick
routes only, and still reports any interpreter fallback; it is not a gameplay
validation and says nothing about hardware fidelity beyond those checks.

*Send my new discoveries after each batch.* Once the batch is over, a
background worker collects the discoveries as **Send** does, uploads the games
whose discoveries changed since the last send with this account, then sends
the claims of each accepted file. Paths learned from the shared base and
revalidated by the player's own conversion leave like any discovery; another
player's path found again counts as a confirmation. The window stays usable;
nothing runs while an update installs. A failure is one log line, and the
games stay pending for the next batch.

Without an account, with an option off, offline, or with
`RETRO_RECOMP_SERVICE` empty, nothing is fetched or sent and the conversions
run as before (an offline batch still uses the paths received earlier).

What the player sees: a path the shared base did not have yet earns its points
at once for the first player who sends it; a later player's identical path
earns no points but confirms it. Once confirmed by another player or by a
release, the path can rise to Platinum or Diamond and brings RR coins;
confirming paths also brings a few coins. The header shows the points, the RR
coins balance beside them and, under the pseudonym, the title chosen on the
site. Options › Common › Retro-Recomp account shows the balance and a
**Shop on the site** button (the account page's `#shop` section): titles and
the other cosmetic items of the RR coin shop are bought and equipped on
retro-recomp.com; the converter only draws them. The header shows the
equipped name style (gold, gold to amber, sparkling gold with a slow shimmer
that stops while the window is hidden), the pin beside the title, the
portrait frame (drawn larger behind the 44 px portrait, which stays on top)
and the header theme (classic, neon, night, gold). The leaderboard shows
name styles, the console badge shown (one, the site's `RR_SHOP_BADGES`;
`online.SHOP_BADGES`), pins and titles. The public catalog
(`GET shop`, `datas/shop-catalog.json`) is refreshed at most every 30 minutes
(`SHOP_REFRESH`) and frame pictures are downloaded once
(`datas/shop-frame-*`); without a catalog nothing extra is drawn.

After 1.5.2 (26 October 2026, interface modules only: `online`, `gui`,
`compiled_games`, `compiled_games_view`, `knowledge_exchange`, `i18n`):

- **The header follows the site within minutes.** The account (`GET
  account` and the cached `GET board`) is read when the converter starts and
  when its window comes back to the front, at most every 2 minutes
  (`PLAYER_REFRESH`), and 15 seconds after a page of the site was opened from
  the converter; never two readings at once (a forced reading asked for
  meanwhile starts once the running one ends, and only a reading started
  after a send logs the games waiting for their reward). The badge shown
  (one) now sits left of the pseudonym, a first place's badge (`top_badges`)
  with a gold rim and a small "1", the same mark on the leaderboard's lines
  and podium. **Manage my items** (Options › Account, and a right-click on
  the account corner) opens the account page's `#items`.
- **A pseudonym at sign-in.** The code dialog proposes an editable pseudonym
  (`RetroPlayer_` and six random digits like the server's, nothing about the
  computer), sent only once the player edited it; otherwise the server
  generates a stable one (`pseudonym_chosen` false), which the header invites
  to replace (a click on the name, or the right-click menu).
- **Conversions reported.** Each successful conversion made while signed in
  is noted (`datas/account-converted.json`); the next send carries the noted
  games, a record without hints (engine and ROM size only) when they bring
  nothing new, at most 50 per send, and claims them `converted` with the
  deepest level the report's discovery completed (`report_level`: a quick
  check from known or shared paths counts as Standard). The service pays RR
  coins once the upload is checked: a game the snapshot already knew, a game
  completed at the Extended or Thorough level, the first to complete a game
  at the Thorough level; no points. Converters 1.5.2 and older send nothing
  of the kind and get nothing more. At most 50 converted games are rewarded
  per account and day; the others wait, in their order, for the following
  days (`conversions.queued` and `queued_days` of the account view), and the
  log says so after a send.
- **Compiled Games** shows each game's level as stars (Standard, Extended,
  Thorough, read from its report), offers **Go further: Extended / Thorough**
  in the right-click menu (a discovery at that level) and a **Games to
  explore** filter: the games of the shared consoles nobody finished at the
  Thorough level yet (`GET explored`, cached 30 minutes and asked again while
  the filter stays shown). Thorough from a Standard game shows Extended plus
  Thorough coins, since the service adds up the levels passed; 20 and 40
  (`EXTENDED_COINS`, `THOROUGH_COINS`) stand in for the server's figures
  until the filter has read them.
- **Sends.** Automatic sends are at most 15 minutes apart (`SEND_EVERY`); a
  send waiting for that spacing leaves when the window closes or at the next
  start, and waits again behind an import, an export or a ROM search instead
  of being dropped. A send made by hand (Knowledge › Send, or the closing
  card's Send and close) takes the place of the waiting one, so closing
  never sends twice. A window closed at the end of a batch leaves its send
  for the next start.

These are interface and account features: they say nothing about native
coverage, CPU or hardware fidelity, gameplay or latency.

## The shared base

Since 1.5.4 the paths the converter knows live in **one base of paths kept
outside the executable**. The executable embeds no path any more:
`assets/compilation-knowledge.json.gz` stays in the repository only as the
source of the maintainer's campaigns and is not packaged. Every path in the
base is either **qualified** or **pending**, and the difference is kept
visible everywhere.

| State | What it means | What the converter does with it |
| --- | --- | --- |
| **Qualified** | A successful conversion of **another player**, who had received the path, reached it and validated it against the reference. The campaigns of the maintainer are qualified from the start. Qualification is **per engine revision** (for the Neo Geo, emulator core and loader together). | Paths qualified for this converter's engine go to a local qualified bank and rebuild the game from its paths with the quick check, like the former embedded snapshot. |
| **Pending** | What a player discovered and nobody else's conversion has reached yet, and the qualified paths of another engine revision (they return to this state, with their level, when the engine changes, until a conversion on the new engine reaches them again). | Still used, as imported knowledge: they guide discovery and **every conversion checks them again** against the reference CPU and sets them aside when that fails (the conversion runs again without them). |

A pending path is therefore never presented as qualified, and nothing here is
a proof of CPU or hardware fidelity, of gameplay or of latency. A path stays
in the base only if a conversion actually reached it: the player's own
conversion keeps in the local library, and the next upload sends again, only
the paths **that conversion itself observed**; an imported path the execution
never reached enters neither the library nor an upload. Polluted paths cannot
travel from player to player, and they cannot make exports grow.

**Where the base lives.** The installer lays a copy of the base of the release
day beside the executable (`Retro-Recomp-base.zip`); it is only ever read, and
the built-in update replaces it with the file attached to the same release.
The converter keeps what is newer in `datas/knowledge/base/`: `state.json`
(version, hash of the index, whether the index is the copy's or a download's),
the newer `index.json` and, in `entries/`, only the entries the copy lacks. An
entry is looked up in that folder first, then in the copy, and each is verified
by the hash that names it and by its shape. An entry holds the qualified paths
per engine revision and, per upload, the pending record and its ROM-free
observation rows, so that a revocation or a rejection targets one upload and
not the whole game. Entries no index names any more are deleted. Removing the
`datas/knowledge` folder starts the local state over.

**When it is updated.** Never when the program opens, apart from an optional,
read-only check (below). The base is brought up to date **before a batch, at
most once a day**, or when asked with **Knowledge > Sync with the shared base**,
and only with the option *Use the shared base*. The converter reads the
service's small manifest; when the local version has a difference file, only
that file is downloaded (a few entries); otherwise it downloads the latest
complete base attached to a release, then the difference that leads on from
it. Sizes and SHA-256 are verified, every entry is verified, an archive that is
not what the manifest announces is refused, and the new base is applied as a
whole or not at all. No account is needed. An offline service, a format this
version cannot read or a failed download keep the base already here and never
stop the batch; the log says which. With no local base and no connection the
log, and a notice when the batch starts, say that every game is discovered in
full and takes longer; with a local base and no connection they say the local
base is used.

**One line (1.6.1).** 1.6.0 published each version in two formats, line 2 (the original, for converters up to
1.5.x) and line 3 (the CPU-keyed schema 3, *Schema 3 of the paths*). 1.6.1 reads line 3 only and the service builds
and publishes it only; the older converters stop receiving base updates and their player updates the program. The
paths reach the banks as the same schema 1 records, and the qualified bank keeps its shape.

**Startup check.** *Check for updates at startup* (Options, on by default)
looks, at most every six hours and in the background, at whether a newer
program or a newer base exists, and marks the update button. It only looks:
nothing is downloaded until you choose.

**Before a batch.** For each ROM of the batch the converter reads its entry.
The qualified paths of this converter's engine are merged, game by game and
validated, into the qualified bank (`datas/knowledge/qualified.json.gz`); the
other games' records stay. Everything else (pending parts and qualified paths
of another engine, with their level) joins `imported.json.gz` and
`imported-observations.json.gz`, exactly as paths fetched for a signed-in
account do, and `base-use.json` remembers per game the base version, the
entry, the engine revision and the parts applied. Without the option, only the
qualified paths of the local base apply and nothing is downloaded or imported.
Signed in, the per-account sync of 1.5.1 keeps working beside the base and does
not serve again what the base already holds. **Sending** discoveries, claims
and rewards still need an account.

**Revocation and quarantine.** The service's manifest lists the uploads that
were withdrawn since the base was built (an invalid file, a banned account).
The converter treats such a part as unwanted: not imported, and if it was, the
game's imported paths are discarded and rebuilt from the remaining parts
(logged in `imported-rejected.json` with a reason starting "shared base:"). It
also lists the (upload, game) pairs that enough accounts rejected: they are
treated like a revoked upload, for that game only, and brought back if the
quarantine is lifted. Withdrawals travel in the manifest, not in the base
files: they apply from the next batch once the manifest has been read, by the
daily update or by the startup check.

**Rejection.** After a successful conversion made while signed in, the
converter notes what became of the base's pending parts for that game (base
version, entry, uploads applied) and tells the service in the claims that carry
the conversion: `used` when the conversion went through with them, `rejected`
when it failed with them and succeeded without (a rejected entry is also not
imported again here until the base names another for that game). Without an
account nothing is noted and nothing is sent; the local set-aside happens in
any case. Qualified paths are not imported hints and stay.

**Neo Geo.** A Neo Geo game is named in the base by its prepared cartridge and
the BIOS archive its conversion uses together (`neogeo_knowledge.key`, the key
of the local library), not by the ROM file's hash: a player with another BIOS
or another cartridge layout receives nothing. A record holds only numbers
(offsets into the cartridge program, the BIOS and the sound ROMs, RAM and Z80
references, compact ROM roots), checked by the same function on the player's
computer, in the maintainer's reader and on the service. Only what the
player's own conversion reached in the fresh reference runs is sent; raw
gameplay observations of Neo Geo stay private. The prepared cartridge of a ZIP
set only exists once the preparation tool has assembled it, so a set never
prepared on this computer is asked for during its first conversion, right
after its cartridge is prepared; a `.neo` file, or a set prepared before, is
asked for before the batch with the others. A Neo Geo conversion that fails
with imported hints runs again without them inside its own conversion code; if
that passes, the hints are discarded and its report says so
(`knowledge.imported_hints_rejected`). The fresh reference, packed-executable
and state checks stay mandatory, and the report counts the imported hints
apart (`knowledge.use.imported`).

**Measures stay separate.** Native code, CPU fidelity, hardware fidelity,
gameplay validation and physical latency are never merged. A conversion that
used shared paths records it in its report (`shared_paths`: level, records,
`quick`), and a quick check measures native code against the reference CPU on
the quick routes only. **Interpreter use is always measured and reported**, and
the conversion keeps looking to reduce it. The base version used is kept
locally in `base-use.json`, not in the report.

**Before 1.5.4.** In 1.5.2 one maintainer command converted the players'
uploaded games again and folded their paths into the bundled snapshot at each
release; its first run added 33 games (Super Nintendo 27, NES 3, Mega Drive 2,
Game Boy 1), 2,280,968 hints, all verified by the quick check, and the
snapshot went from 15,453,304 to 16,895,274 bytes. That routine is retired:
the content of that snapshot, with the later campaigns, is the maintainer's
qualified part of the base, and players' uploads reach the base without
waiting for a release. The first run also found that Mega Drive and Super
Nintendo checks failed on Windows with a `NameError` (`subprocess` no longer
imported in `console16.probe16` since 1.5.1), fixed in 1.5.2.

## Release 0.24.0 snapshot

| Console | Exact cartridge records |
| --- | ---: |
| Master System | 258 |
| Game Gear | 1 |
| Game Boy | 606 |
| NES | 23 |
| Mega Drive | 51 |
| Super Nintendo | 15 |
| **Total** | **954** |

The snapshot is **7,734,174 bytes compressed (about 7.4 MiB)** and
29,743,114 bytes before compression. These counts describe qualified reusable
observations, not the number of fully playable or universally interpreter-free
games. Each observation remains scoped to its exact cartridge and engine.
The converter includes this snapshot, not the private campaign registers,
downloaded images or raw local learning library.

## Development snapshot, 10 October 2026

The SRAM qualification refreshes one existing MD record and adds one exact
cartridge record after the normal four-scenario native/reference gate. The
development converter now embeds **52 MD records and 955 total records**;
the other consoles and the remaining fifty MD records are unchanged.
The snapshot is **7,755,866 bytes compressed** and 29,846,918 bytes before
compression. Only verified numeric ROM references and opcode masks are shared;
player SRAM, states, artwork and the private library remain local.
Native/reference agreement and serialization tests are distinct from
game-menu saving, complete gameplay and independent hardware fidelity.

## Master System qualification, 9 October 2026

The SMS campaign qualified 256 distinct supplied cartridges, followed by two
additional gun editions: **258 exact cartridges** in total. It used extended
native coverage, up to six passes and 7,200 frames per demo/play scenario, with
up to eight concurrent conversions. Both final scenarios recorded zero fallback cycles;
strict execution and CPU/RAM/framebuffer/VDP comparisons with the reference
passed. This evidence covers the scripted scenarios, not every gameplay path or
physical hardware behavior. Eight byte-identical extra files were skipped and
one misleadingly named Game Gear cartridge was excluded from the SMS batch.

The retained SMS observations occupy about **11 MiB locally**. The shareable SMS
portion is only **12 KiB compressed**: 258 exact ROM identities and 101 verified
ROM entry hints. Extended ROM translation does not need an observation for every
translated byte. The 2,970 observed RAM variants without a verified ROM source
remain local; embedding their raw bytes would violate the ROM-free format.
Existing qualified records for the other five consoles were preserved unchanged.

Discoveries also produced common source fixes: a reference BIT memory access
must not write back and accidentally change a bank register; withdrawn VDP IRQs
must not remain pending across DI/EI; explicit learning writes must support long
Windows paths. These fixes are bundled compiler/runtime behavior and therefore
benefit new cartridges independently of per-game hints. A Sega hardware header
also takes precedence over a misleading `.sms`/`.gg` extension.

## Game Boy qualification, 10 October 2026

The initial supplied DMG batch finished: 638 input files, **592 qualified exact
cartridges**, 28 successful byte-identical extras skipped, and 18 failed input
attempts covering 17 exact cartridges. Six conversions ran concurrently on the
final continuation, with up to six passes and four 7,200-frame scenarios.
Internal instruction-by-instruction CPU/memory comparisons passed for all 592
qualified exports. Of these, 487 recorded zero fallback cycles in the scripted
scenarios; 105 retained reported fallback. This does not establish complete
gameplay coverage, physical hardware fidelity or physical latency.

That campaign's snapshot contained **773,878 numeric Game Boy entry hints** for
those 592 exact identities. Its GB portion occupies **2,014,198 bytes compressed**
(about 1.92 MiB); the snapshot after that campaign was 6,711,274 bytes. Existing records for the
other consoles were preserved. The local converter was rebuilt and its embedded
snapshot audited. No ROM bytes, private RAM contents, artwork or private paths
were added to the reusable knowledge resource.

The initial failures remained separate from shared qualified hints. Five CPU comparisons
disagreed at instructions starting at `0x3FFE` or `0x3FFF`, around the boundary
between fixed and switchable ROM banks. Operand reads under the live bank mapping
were identified for follow-up; the correction and evidence are recorded below.
Other retained failures include headless probe timeouts, a boot access violation
and an incomplete fallback inventory. A timeout alone does not identify a CPU
bug. Follow-up work must preserve the CPU validation gate.

Private evidence is kept in `.build/gb-library-expansion/`: final conversion
results, qualified and residual-fallback inventories, exact-ROM compiler findings,
source integrity, knowledge summary and converter audit. Never publish that
private directory. The 22 approved missing Game Boy cover corrections use the
separate links-only `assets/cover-references.json`; their downloaded images stay
in the local artwork cache.

## Mega Drive startup qualification, 10 October 2026

A targeted follow-up fixed a shared learning/translation boundary: valid 68000
instructions at the end of work RAM were excluded by a maximum-size reservation.
The converter now checks their actual length and retains all live-memory guards.
An additional 1,800-frame early-start replay is part of the advanced scan,
alongside the existing demo, play and varied-input scenarios. Every replay is
compared with the internal CPU/video/audio reference before its observations
enter the library.

Testing the 42 existing exports found five cartridges with fallback when starting
early, despite zero fallback in their previous final scenarios. Those five now
record zero interpreted 68000 and Z80 operations on all four scenarios after
regeneration. Two other cartridges passed the RAM-boundary regression checks.
These are scripted coverage and internal-reference results, not complete gameplay
or independent hardware validation. The full Mega Drive and SNES batches remain paused.

Seven newly qualified exact Mega Drive identities were added to the bundled
snapshot, bringing its Mega Drive catalogue to **35 cartridges**. Previously
qualified records were preserved unchanged. The whole ROM-free snapshot is now
**7,035,273 bytes compressed** after this MD refresh, an increase of **323,999 bytes**; six RAM patterns
without a matching source in their own ROM remain private. The new instruction
windows are represented by offsets into the exact user-provided ROM, never copied
game bytes. Private before/after counts, reference reports and resolved-problem
history are retained under `.build/md-ram-tail-20261010/` and the MD problem register.
The local converter was rebuilt and its embedded snapshot, modules and resources
audited against the current source. The remainder of the paused collection's
observations stays local until its own snapshot refresh.

## Mega Drive first twenty exports, 10 October 2026

After the user removed the Mega Drive executables, a targeted batch regenerated
the first twenty supplied files alphabetically with eight concurrent conversions,
up to six passes and the advanced scan. All twenty passed the four scripted
scenarios: demo, play and varied inputs at 7,200 frames, plus early-start at
1,800 frames. No 68000 or Z80 interpreter operations occurred in the final
scenarios. Internal CPU/memory/visible-frame/audio PCM comparisons passed.
The actual compressed exports also passed 1,800-frame early-start replays
against those references. This does not qualify every gameplay path, physical
latency or hardware fidelity independently of the internal reference.

The verified Japanese Alex Kidd cartridge's empty region header is now handled
by its complete SHA256 identity; its other hashes match the Libretro/No-Intro
Japan record. Other ROM revisions cannot inherit that exception. No cartridge
bytes were modified. Both distinct editions of After Burner II and Aladdin
remain separate exports, and the cartridge header determines PAL/NTSC timing.

Sixteen new exact MD identities were added and four requalified, bringing the
MD snapshot to **51 cartridges and 809,553 numeric hints**. All other consoles
and the remaining 31 MD records are unchanged. The full snapshot occupies
**7,734,174 bytes compressed**, **29,743,114 bytes uncompressed**, an increase
of **650,559 bytes**. No unqualified observations or ROM bytes were included.
Its SHA256 is
`baf35f3b50a1c3a8f80e9fe8fd37b1a9226578a7e958d6b87f9a3780b2f5f952`.
Private batch evidence and the snapshot audit are under
`.build/md-first20-20261010/`. The local converter was rebuilt; its embedded
snapshot, 52 Python modules and 128 resources match the current sources.
The historical collection checkpoint now records
43 qualified cartridges; it is not an inventory of the twenty installed EXEs.
The full MD collection and SNES campaign remain paused.

## Game Boy APU/menu follow-up, 11 October 2026

Super Mario Land and Tetris were requalified after the shared APU corrections
and direct F5 palette toggle. Both passed four 3,600-frame coverage probes
with zero fallback and their deep CPU comparisons. Only these two GB records
were refreshed; all other exact-ROM records were preserved. No new numeric
entry hints were discovered: the current 955-identity multi-console snapshot
remains byte-identical, including 606 GB identities / 793,352 GB hints.
It is verified in the rebuilt converter. The APU expectations are qualified
separately by authored hardware checks, not by these entry hints or the shared
CPU reference; unspecified-game sprite flicker remains unqualified.

## Game Boy targeted compiler follow-up, 10 October 2026

After build, trace and guarded-native-helper improvements, 14 of the initial
17 failed exact cartridges now complete all four 7,200-frame probes and their
deep internal CPU comparisons. Thirteen report zero fallback on those probes;
Max remains qualified with reported writable-code fallback. Three other previously
qualified cartridges have lower RAM fallback, and Mario was requalified as a
performance control. Details and timings are in [the Game Boy profile](GAME_BOY.md).

The refreshed snapshot preserves 588 GB records, requalifies four and adds
14 identities: **606 exact GB cartridges and 793,352 numeric ROM entry hints**.
The GB records compress to **2,063,871 bytes**. The complete multi-console
snapshot is **7,083,615 bytes compressed**, **27,105,549 bytes uncompressed**,
only **48,342 bytes larger** than the preceding MD refresh. Every other console's
records are unchanged. Its SHA-256 is
`ac37d783ee358ad7282f3de0b36220300d55317f35cf5502ff2eed8b739c4e36`.
Only numeric observations from successful exact-ROM qualifications were added;
no game bytes, RAM dumps, images or private paths enter the resource.

Paperboy 2, Spiritual Warfare and The Ren & Stimpy Show: Veediots! remain
unqualified after the unchanged 600-second probe timeout. Their diagnostics
stay private. The cumulative register now has 500 identities with zero fallback
in their qualified scenarios and 106 with residual fallback. This combines the
initial campaign with targeted follow-up, not a new full-library qualification.

Private evidence is in `.build/gb-speed-20261010/`; the collection's
`compiler-findings.json` retains the initial summary, resolved failures and
remaining cases by full ROM SHA-256. The converter embeds the updated snapshot;
existing game exports require regeneration to use changed native helpers or
generated code. The global Mega Drive and SNES campaigns remain paused.

## Workflow for future sessions

1. Read `README.md`, this guide and the local `docs/PROJECT_STATE.md` before
   continuing compiler work. Preserve the source ROMs and unrelated edits.
2. Convert the cartridges needed for the investigation, with up to eight
   simultaneous conversions when resources allow. Keep NAS sources read-only;
   all build files, observations, downloads and exports stay local.
   Exact copies wait for the current conversion of that ROM without blocking
   unrelated games from using free workers. A failed first copy still allows
   a later identical input to retry; successful copies are deduplicated by
   console and exact ROM identity.
3. Inspect new fallback sites or disagreements, fix the shared compiler/runtime
   where appropriate, and run meaningful checks for that change. Record native
   coverage, CPU agreement, hardware fidelity, gameplay and physical latency
   separately. Gameplay and listening checks belong to the user unless requested.
   Maintain a private register by console and full ROM SHA-256 of conversion
   failures and fallback still present in the final probes. Separate main and
   audio CPU counters, retain error messages and diagnostic paths, and keep
   rejected cartridge formats separate from compiler failures. Preserve resolved
   cases in the history. These diagnostics must not enter the shared snapshot.
4. Refresh the compact snapshot from qualified local observations and successful
   conversion reports. Pass all relevant local ROM directories explicitly:

   ```powershell
   python tools/build_compilation_knowledge.py --rom-dir ROMS --reports Export/Games
   ```

   Repeat `--rom-dir` for additional local input directories. Report the compressed
   size and omitted observations. Do not copy the private library wholesale.

   When refreshing one console, preserve the existing qualified snapshot with
   `--base`, especially if old game reports have been deleted:

   ```powershell
   python tools/build_compilation_knowledge.py --rom-dir ROMS/MasterSystem --reports Export/Games --base assets/compilation-knowledge.json.gz
   ```

   The base must be a previously qualified ROM-free snapshot. Its records stay
   unchanged unless the current conversion evidence qualifies a replacement.
   The summary distinguishes retained records, newly qualified identities and
   refreshed identities. A failed new conversion cannot replace a base record.
   Runtime hints remain bound to the exact console, ROM hash, size and engine.
5. Build the converter with `tools/package.ps1`; audit the embedded snapshot and
   exact source/resources with `tools/prepare_publication.py`. Record the results
   and remaining limitations in `docs/PROJECT_STATE.md`. Publication needs an
   explicit user request.

Refresh and embed the snapshot after new qualified discoveries, so the next
converter build shares those hints. New and refreshed records require source
ROMs in the supplied directories and successful qualification. Existing
qualified base records can be retained without rebuilding other consoles. It does
not claim compatibility with every revision or every possible gameplay path.
Updating the converter does not change existing game executables; runtime
changes require regenerating the affected games.

## Gameplay paths missed by startup scripts

The Mega Drive converter now expands reached tables of adjacent direct jump
instructions during offline analysis. Advanced scanning also includes a fresh
menu/dialogue replay with released A/C confirmations for controller games.
Each new replay is compared with the internal CPU/memory/video/PCM reference
before learning. Observations from a copied gameplay state use the same gate;
the player's state and cartridge saves never enter the shared snapshot.

The Shining Force II follow-up reproduced fallback 31 frames after loading a
copied player state and pressing an action button. The prior startup probes had
missed these branches. Three state-based replays and one fresh-boot menu replay
matched the internal reference before 61 ROM instruction observations were
learned. This is a coverage fix, not a claim of complete gameplay validation.

## Common translator corrections

SNES byte-access timing, DMA ownership, refresh holds and PPU collision latches
belong to the common runtime, rather than ROM-specific delay hints. After such
a change, requalify the exact-ROM CPU, memory, visible-frame and PCM routes
before refreshing the bundled snapshot. Bus requests, sprite/palette latches,
player quick states and independent reference captures never enter that
snapshot. Independent hardware-model disagreement must remain documented even
when the two internal CPU paths agree. The current evidence and open gates are
recorded in [SNES development](SNES.md).

Shared observations are not a substitute for correcting the common translator.
The MC68000 synchronous-exception work adds native vector/stack behavior and
independent CPU fixtures; every subsequent Mega Drive generation uses that
correction. Unknown or unsupported instructions remain visible limitations.
The usual exact-ROM reference gate still applies before hints can be promoted.
See [exception verification scope](MEGADRIVE_CPU_EXCEPTIONS.md).

VDP queue, asynchronous read prefetch, separate DMA source/FIFO phases, pending-IRQ and within-slice CPU
resume corrections live in the shared runtime,
rather than per-game hints. Exact-ROM requalification must compare CPU, memory, visible image and
PCM again after such a change. The compilation snapshot contains reached ROM
entries only; queued writes, pending/half/ready read buffers, DMA progress, IRQ latches, player snapshots and
cartridge saves never enter it. The three targeted cartridges are requalified
after the timing change; the wider collection stays paused. See
[video and timing qualification scope](MEGADRIVE_VIDEO.md).

DMA bus suspension and Z80 external-bus ownership also belong to the common
runtime. They are not per-ROM hints. Requalify the bounded exact-ROM targets
after changing them, then refresh the verified shared snapshot and bundle it
in the local converter. Live coroutine stacks and pending host F8/F9 requests
never enter the compilation library. Keep the wider campaigns paused until
their separate hardware/gameplay gates are ready.

Request-driven Z80/68000 arbitration and clocked bus reservations likewise
belong to the common runtime, not a growing list of per-game delays. Only
requalified exact-ROM observations may enter the shared snapshot after this
change. Requests, reservation clocks and live CPU continuations never enter it.
The bounded Sonic 1/2 and Shining Force II qualification is recorded separately
from physical bus fidelity in the local arbitration report.

Ordered main-CPU transactions, clock-debt persistence and common EA timing/read
corrections likewise belong to the shared compiler/runtime. A new bus-budget
failure prevents qualification even if native and reference agree on the same
bad estimate. Requalify the exact ROMs before refreshing their shared records;
do not promote a failed report. Clock state stays in the game's quick state,
not in the compilation snapshot. Evidence for this follow-up is
`.build/md-bus-phases-20261010/qualification.json`.

## Reproducible cold measurements

`RETRO_RECOMP_BUNDLED_KNOWLEDGE=0` disables the shared snapshot. Selecting an
isolated library with `RETRO_RECOMP_LIBRARY_DIR` (or the legacy
`SMSRECOMP_LIBRARY_DIR`) also disables it, so a cold compilation benchmark does
not silently reuse packaged knowledge. Discovery and validation still run.
Record whether local and bundled knowledge were enabled when comparing times.

## Operand-dependent arithmetic qualification

MUL/DIV operand costs, their stream phases, DBcc expiry and divide-overflow
corrections belong to the common compiler/runtime, not per-game observations.
Requalify exact ROMs against the reference and independent bus-budget gates
before refreshing the verified bundled snapshot. Only the three bounded MD
records are refreshed here; raw corpus files, private library data, player
states and runtime timing latches are never embedded as knowledge. See
[CPU phase scope and remaining gates](MEGADRIVE_PREFETCH.md).

## Neo Geo development observations

Stage 3 NAM-1975 stores reached P/BIOS addresses, exact structural Z80 RAM
observations and paired native/reference reports only in its private conversion
project. Cartridge region hashes, all four selected BIOS hashes, loader/core
pins, semantic hash and native EXE SHA identify the evidence. The controller
routes do not bypass reference validation. Native counts are checked separately
from CPU/RAM/image/PCM and serialized hardware-state agreement.

No Neo Geo record enters the production six-console snapshot yet: its
BIOS-aware shared schema and production profile are a subsequent integration
gate. Preserve these qualified numeric observations for that gate, never the
raw P/BIOS/M1/SM1 images, generated instruction C, audio, covers or user states.
The existing verified snapshot remains bundled unchanged. See
[Neo Geo prototype scope](NEOGEO.md).

Stage 4 adds private shared-host/state receipts under
`.build/neogeo-host-20261013`. CPU/image/raw-PCM/extended-state replay gates are
independent of coverage observations. A player's `.rrstate`, framebuffer, raw
audio and INI file are never compilation knowledge and must not enter the bank.
The existing 1,027-record snapshot is unchanged; no Neo Geo promotion occurs.
