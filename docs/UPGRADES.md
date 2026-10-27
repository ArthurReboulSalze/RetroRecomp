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

- the previous export has a version 3 receipt (written since 1.2.8), and its
  executable is exactly the file that receipt names;
- the request's **game part** is unchanged: game-side converter inputs, scan
  level, passes, frames, video standard, BIOS or machine identity, target,
  ROM and the bundled or imported knowledge for that cartridge;
- no new gameplay hints (F12 feedback) were recorded since that export;
- the previous validation did not fail;
- only the **host part** changed: host inputs, title, language, artwork or
  icon tags.

Older receipts have no game part, so the first batch after updating to 1.2.8
still converts each game once in full. A forced conversion from the queue
always rediscovers; **Reconvert** in the collection always rebuilds, but
upgrades when the conditions above hold.

A third role, **build**, covers the choice of the C toolchain
(`retrorecomp/toolchain.py`): changing the compiler or its options also upgrades an
export, because the executable is recompiled and rechecked on the quick routes.
Exports of an earlier release can be accepted the same way through an explicit list of
equivalent game stamps; see [Build inputs](COMPILATION_LIBRARY.md#build-inputs-and-exports-of-an-earlier-release-that-stay-upgradable-150).

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

## Exports of 1.5.6 in 1.6.0

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
| Sound output after the emulated mixer | `audio_filter.h`, `audio_cushion.h`, `audio_output.inc`, `gb_audio_output.inc`, `nes_audio_output.inc`, `md_audio_loop.inc`, `md_audio_resample.inc`, `megadrive_audio.py` |
| Artwork, metadata, publishing | `artwork.py`, `cover_*.py`, `metadata.py`, `languages.py`, `publishing.py`, `windows.py`, `licenses/*.md`, `THIRD_PARTY_NOTICES.md`, application icons |
| Checks of the above | `game_options_checks.c`, `language_checks.c`, `xbr_checks.c`, `display_settings_checks.c`, `icon_checks.c`, `audio_checks.c`, `nes_audio_checks.c` |

Each machine family has one shell for its window, menus and input:

| Machine | Shell (host) | Entry used by discovery and validation (game) |
| --- | --- | --- |
| Master System, Game Gear | `host.c`, `ui.c/.h`, `controls.c/.h` | `launcher.c` and the Z80 runtime |
| Game Boy | `gb_menu.inc`, `gb_input_refresh.inc`, `gameboy_host.py`, `gameboy_timing.py` | `game_main.c`, `gameboy_runtime.py` |
| NES | `nes_host_ui.c` | the runner adapted by `nes_runtime.py` |
| Mega Drive, SNES, Neo Geo, CPS-1 | the host kit: `native/hostkit/shell/rrhk_*.c` (shared) and `native/hostkit/adapters/rrhk_<machine>.c`, copied by `hostkit.py` | `console16_main.c`, `neogeo_main.c`, `cps1_main.c`, machine adapters |
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
interface modules. The Neo Geo has no `LEGACY_GAME_STAMPS` entry since 1.6.0: its knowledge part used to hash the
whole Neo Geo bank, so its exports of earlier releases are converted in full once (do not add an entry for 1.5.6).
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
