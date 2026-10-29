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
  adds to those of an older release. The table was empty in the tree of 1.6.0; the tree of 1.6.1 listed the stamps of
  1.6.0 ([history](#exports-of-160-in-161)); the tree of 1.6.2 listed those of 1.6.1
  ([history](#exports-of-161-in-162)); the tree of 1.6.3 lists those of 1.6.2 ([below](#exports-of-162-in-163)).
- The quick-state keys of release N-1 are the only `RR16_STATE_COMPAT_ABI` lines a build writes
  ([GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). None in the tree of 1.6.0; the Mega Drive, Neo
  Geo and CPS-1 keys of 1.6.0 (Windows) in the tree of 1.6.1. The Mega Drive, Super Nintendo, Neo
  Geo and CPS-1 keys of 1.6.1 (Windows) in the tree of 1.6.2. The same four consoles' keys of 1.6.2 (Windows) in the
  tree of 1.6.3.
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

## Exports of 1.6.2 in 1.6.3

1.6.3 moves the game stamp and the host stamp of every console, and the build stamp of none (the packer is the UPX 5.3.0
of 1.6.2). Most of what moves them is the host kit shells of the Master System, Game Gear, Game Boy and X68000, the
shared conversion helpers and the profile registry, and none of that changes what a game is or does; three CPU
corrections do reach what a conversion generates, and exports of 1.6.2 are meant to receive them through the upgrade
(rebuilt from the paths already learned, rechecked on the quick routes), which is what the entries below are for. The
later sections of this file list each change of the release; what follows is what each console's stamps do.

| Console | Game stamp moves because | Host stamp | 1.6.2 export in 1.6.3 |
| --- | --- | --- | --- |
| Master System | host kit phase 4 ([below](#master-system-and-game-gear-exports-in-163-host-kit-phase-4)): the staging call in `core`, the source list in `native/CMakeLists.txt`, `console16_video.h`; the "functions" engine no longer makes a direct call to a paged address ([below](#cpu-fixes-carried-from-the-upstream-review-in-163)) | moves | **upgraded**, `upgrade.from_release` = `1.6.2`; the "functions" engine exports regenerate their calls through the dispatch |
| Game Gear | the same two | moves | upgraded |
| Game Boy | host kit phase 5 ([below](#game-boy-exports-in-163-host-kit-phase-5)): `gameboy_runtime` (staging, source list, and the embedded resources linked into `gbrt` on Linux), `gameboy`, `gameboy_build`, `console16_video.h` | moves | upgraded |
| NES | the shared conversion helpers in `nes`, `nes_build`, `nes_codegen` and its profile data; the generated sources are the same | moves | upgraded |
| Mega Drive | `m68000` (ROXL and ROXR with a register count of zero, ASL.L by 31: [below](#cpu-fixes-carried-from-the-upstream-review-in-163)), `console16` (shared helpers) | moves | upgraded: rebuilt with the corrected shifts |
| Super Nintendo | `snes_codegen` (BRK and COP), `console16` (the shared `snes_ppu_header`), `native/snes_cpu/interrupt_checks.c` | moves | upgraded: rebuilt with the corrected BRK and COP |
| Neo Geo | `m68000`, `neogeo_build`, `neogeo_conversion`, `neogeo_persistence_checks`, `neogeo_state_checks` (shared helpers and gates), `native/neogeo_m68000_checks.c` | moves | upgraded: rebuilt with the corrected shifts |
| CPS-1 | `m68000`, `cps1_build`, `cps1_conversion`, `neogeo_build` (shared helpers; this rollover's key line), `cps1_knowledge` | moves | upgraded: rebuilt with the corrected shifts; `GENERATOR_REVISION` stays 6, see below |
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
([UPSTREAMS.md](UPSTREAMS.md)), so the base of qualified paths, keyed by the revisions, stays valid; the paths a conversion
learns do not change with them. The CPS-1 generator revision is 6 (raised for the 68000 shifts and the shared helpers
earlier in 1.6.3); the rollover of the quick-state key edits `cps1_build.py`, a pinned generator source, once more, and the
revision is **not** raised to 7: revision 6 has not shipped, no path was qualified by the code between the two edits, and
what a RAM path could notice (the generated files, the serialized bytes) is the same. The pins of
`tests/cps1_generator_pins.json` follow and the comment of the revision says so.

The release procedure (the rule above) replaces the entries of 1.6.1 by those of 1.6.2, and only those, in
`LEGACY_GAME_STAMPS` (29 October 2026, the tree of this release), two per console, the Windows converter's first:

| Console | Game stamp of 1.6.2, Windows (Python 3.14) | Game stamp of 1.6.2, Linux (Python 3.13) |
| --- | --- | --- |
| Master System | `b4e9d8b926b55189f2369ea20e6e99123a2ef3b8bbe12ad9a2455c8a9e35f4b2` | `58d4d6ee6bd59653e4815b303a8c332d593b3755419970732171e914d6b0af73` |
| Game Gear | `14ae3fcbdaf43b121500a121128bcae88161279b350a745952ff17e44ae65743` | `0d63e09321860ce6e161b49a24535d13ddc10b5e6d281b91b195ad9472710a6d` |
| Game Boy | `831c25068b495316b763e46ee05a62f4ca4b9a1abbb92692c68979c559406b9a` | `dde2e590f43d5efc0dea2d34ceedee54ee908cdba37d1a1ea6535cde1d6bc1b4` |
| NES | `fa98f9dd4c480eb16ab7e66c491cb52b02100f88631c5f398112a896e79f5ce4` | `6618f7f293fd864e5cc6e3fec4aa89b020e2795593ba924ab30b4e13990b921a` |
| Mega Drive | `ad4dee96cbceb46be2c7cdf200d917586451d53c8abbca0d24c4b6e95a500b85` | `0de9eed2964d4261237a9099334e7bbcad2dead0dab99258674dd0c306b220b0` |
| Super Nintendo | `b6a7c7fd16250e9512258d961d7f2069d8bf6f0988a0be611530219577556d18` | `fa81323602399f6e839ec9a3ee3ba1e0443fe313b5916c46b8a26742bdd55452` |
| Neo Geo | `aff15893e4d95019cab57539ab28f5438f74613b07e780f2f9412f19b054b838` | `b6d6f5a7ae69485b8b86913241a865b171dcad8cb30ab38ada9dc381b3e62142` |
| CPS-1 | `d4e10fc37d4974cd495d666ac35bb11a29be5a79df2ed3fa8167263f044b54fb` | `4a0de40695a4b51350cf43eb36450211cdff13f785730f1ead61bffc4ae6ea43` |
| Sharp X68000 | not listed; recorded: `699f09265a9fe722e1cedabd80d711961f8edd8e06385366eb1aa7cc1befab39` | not listed; recorded: `35980145fc8de1a9afb1b4722831bdbeafb38b097f963532579c412d5f2b2bc2` |

- *X68000.* Its request carries `x68_sdk`, a hash of the game stamp of the tree that wrote it and of the machine base, so a
  receipt of 1.6.2 could never be recognised ([history](#exports-of-160-in-161)): an entry would be dead weight, and its
  quick states of 1.6.2 are refused as well ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-162)).
- *Quick states.* An export of 1.6.2 that is upgraded is rebuilt with the 1.6.2 compatibility key of its console, so the
  quick states of 1.6.2 (Mega Drive, Super Nintendo, Neo Geo and CPS-1, Windows) still resume. The Master System, Game Gear
  and Game Boy have no key of this kind and load states both ways; the NES key is unchanged
  ([GAME_STATES.md](GAME_STATES.md#states-written-by-release-162)).

**How the stamps were computed.** The `v1.6.2` tag (commit `5bbfe12`, the commit the packaged converters were built from)
exported with an archive of the tag into an empty folder, then `compilation_inputs.role_stamps(system)['game']`, under
Python 3.14.5 on the Windows PC and under Python 3.13.5 (the build virtual environment) on the Linux build host.

**Two converters, two stamps per console.** Code is fingerprinted as bytecode, so the Windows converter of 1.6.2 (built with
Python 3.14) and the Linux one (built with Python 3.13) stamp differently: each console lists both, Windows first. Both were
checked against the published converters themselves on 29 October 2026: the `Retro-Recomp.exe` and
`Retro-Recomp-linux-x86_64` assets of the v1.6.2 release (SHA-256 checked against its `SHA256SUMS.txt`) were run with their
internal `_compilation-inputs` command (the Windows one hidden, with no window), and the game, host and build stamps
recomputed from their own input fingerprints equal, on all nine consoles, the stamps of the archive of `v1.6.2` under Python
3.14 (Windows) and 3.13 (the Linux host). Without the Linux entries a Linux export of 1.6.2 would be converted in full.

**Evidence, and what is not proved.** No game was converted for these entries and `Export/` holds no receipt written by
1.6.2 for them: the claim rests on the list of changes above and on the published converters' own stamps, not on a receipt
per console. An entry cannot accept a wrong export: a receipt matches only if its game part is the hash of the request with
`engine` equal to the listed stamp, so a stamp the 1.6.2 converter did not write matches nothing and the export is converted
in full as before. What the table cannot show without receipts is that a matching export is equivalent to a reconversion.
Unlike the entries of 1.6.1, three of the changes above do alter what is generated for some exports (the 68000 shifts of
the Mega Drive, Neo Geo and CPS-1, the Super Nintendo BRK and COP, the Master System and Game Gear "functions" engine):
the upgrade is how those exports receive them, and the upgrade rechecks them against the reference on the quick routes and
says so in the report (`upgrade.from_release` = `1.6.2`). That is not a replay of the long routes, and it measures neither
CPU fidelity, hardware fidelity, gameplay nor physical latency.

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
  game stamps move**: exports are rebuilt from their learned paths. Host and build stamps, the quick-state keys and the
  base do not move; `cps1_knowledge.GENERATOR_REVISION` stays 6 (already raised in 1.6.3; its comment names both causes).
  Checked against Musashi on the Neo Geo (`tools/neogeo_m68000_selftest.py`: 672 edge comparisons with X=1 and counts 0,
  17, 31 and 64 for ROXL.W, ROXR.W, ROXR.L and ASL.L; 98 differed before the fix), with 834 SingleStepTests vectors
  replayed on the native and the reference paths (`tests/fixtures/m68k-shifts`, MIT), and by conversions of Blockout,
  NAM-1975, 1941 and R-Type (0 interpreted instructions on the tested routes). The timing of register-count shifts stays
  the pinned core's fixed estimate ([UPSTREAMS.md](UPSTREAMS.md#deferred)).
- **Super Nintendo: BRK and COP.** A BRK in native mode now costs 8 cycles (the bank register K is stacked), 7 in emulation
  mode; COP follows the mode (in emulation mode: no K stacked, 7 cycles, vector $FFF4). One corrected source
  (`snes_codegen.read_core`) feeds both the operation bodies compiled natively and the interpreter copy of the project.
  *Edited:* `retrorecomp/snes_codegen.py`, `console16.py` (game inputs). **The `snes` game stamp moves**: SNES exports are
  rebuilt from their learned paths, without rediscovery. Host and build stamps, the SNES quick-state key and the base do not
  move. Checked by `tools/snes_native_selftest.py` (BRK and COP in both modes, native against the reference, LoROM and HiROM)
  and a Super Mario World conversion (0 interpreted opcodes on the tested routes). Not changed: hardware NMI and IRQ in
  emulation mode, which behave as in native mode (rare: games switch to native mode at start).
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
