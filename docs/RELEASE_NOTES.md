# RetroRecomp v1.2.4 — scan levels per console and options in the main window

- **Discovery scan levels.** Every console tab in Options now sets how long
  discovery runs: **Quick** (one short pass to check a setting), **Standard**
  (the qualified default, unchanged from before), **Extended** and
  **Thorough**, which add one or two reproducible pseudo-random play routes of
  18,000 frames seeded from the exact ROM and compared with the reference
  before any learning. Each tab also offers its own passes and frames (empty
  fields follow the shared values) and a short note on what is recommended and
  why. On Mega Drive and Super Nintendo, Extended runs a 12,000-frame attract
  test with one route and Thorough the former advanced scan; on NES, Extended
  is the former advanced scan and Thorough adds the routes; Master System,
  Game Gear, Game Boy and Neo Geo gain the routes for the first time. On the
  command line, `--scan-level` applies to a whole run; the former switches keep
  their meaning.
- **Sharp X68000.** The default scan is now Standard: main route plus mouse
  and keyboard exploration. Thorough keeps the three 36,000-frame routes that
  qualified the library, and the exploration routes now replay side by side
  within the game's share of the processor: two games converted together in
  6 minutes instead of 21 on the test machine.
- **Options in the main window.** The Options button no longer opens a second
  window: the tabs take the place of the queue, like the compiled-games view,
  and close with "Save and close the options".
- **Finished means finished.** When a batch ends, the log shows a framed
  "RECOMPILATION FINISHED" line with the totals and the elapsed time, the
  window rings and changes its title for twenty seconds, the status line
  starts with "Finished", and the command line prints the same summary.

The generated games do not change: regenerating is not needed, and quick
states, settings, libraries and cartridge saves are unaffected. Because the
converter code changed for every console, it may report existing games as made
by an earlier converter; regenerating them produces the same executables. The
pseudo-random routes broaden the tested paths of the first level; they do not
explore whole games, and none of the levels certifies hardware fidelity.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.2.3 — longer discovery routes on Mega Drive and Super Nintendo

- **Advanced 16-bit scan.** The *Advanced Mega Drive scan* option becomes the
  **Advanced 16-bit scan** and now applies to Super Nintendo cartridges too. On
  both consoles it runs the attract sequence for 24,000 frames and adds two
  **reproducible pseudo-random play routes** of 18,000 frames each: long
  movement phases that often hold a button, short taps, paired Start presses
  that pause and resume, occasional Select and player-two input, and neutral
  pauses between phases. The routes are ordinary controller input seeded from
  the exact ROM, so every conversion of the same cartridge replays the same
  routes and the reference run receives the same script; the report records
  each route's seed and index. Mega Drive keeps its authored varied-input,
  early-start and menu replays. Measured with an empty library on Donkey Kong
  Country, the routes exercised 59 SPC700 opcode variants that the existing
  scenarios did not reach; on Sonic the Hedgehog they added one Z80 driver
  image. Neither game reached a later level this way, so the option broadens
  the tested first-level paths rather than exploring whole games.
- **Documentation index and link check.** `docs/INDEX.md` lists every public
  document by theme, and `tools/check_doc_links.py` verifies the relative links
  of the documentation; it runs in the test suite.

The generated games do not change: regenerating is not needed, and quick
states, settings, libraries and cartridge saves are unaffected. Because the
16-bit compiler code changed, the converter may report Mega Drive and Super
Nintendo games as made by an earlier converter; regenerating them produces the
same executables. With the option enabled, a conversion takes about eight times
longer than the standard scan (16 minutes for Sonic the Hedgehog on the test
machine). The option stays off by default.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.2.2 — the same shortcuts everywhere and finer menu text

- **F1 for help, Shift+F1 to restart, on every console.** The H key is gone:
  F1 opens help and Shift+F1 restarts the game at once, without a confirmation
  screen (the Sharp X68000 used to ask). The Master System and the Sharp
  X68000 no longer have their own restart row in F2; they restart like every
  other console. Earlier restart entries in the INI are simply ignored.
- **Restart and quit from the controller.** By default, holding
  **Start+Select** for one second restarts the game and holding **L3+R3** for
  one second quits it. The game options (F10, or O / Y from a menu) gain
  keyboard and gamepad rows for the restart combination; both can be changed
  or cleared, like the quit rows. A held restart fires once, then waits for the
  buttons to be released.
- **Help in order.** Every help screen lists the function keys from F1 to F12,
  then the console's own controls. The Master System, Game Gear and Game Boy
  help now mention F10.
- **Finer menu text.** Menus use the public-domain X.Org Misc Fixed 10x20
  bitmap, drawn for the window's size: strokes are half as thick as before,
  solid pixels stay solid and only the edges are smoothed. Windows and Linux
  now draw the same letters (Windows used Consolas). The font adds 3.8 KB to a
  game; a 256x192 window keeps the previous 6x10 font.
- **Plain letters only.** In-game menus no longer draw accented characters:
  ñ becomes n, ó becomes o and German umlauts become ae/oe/ue. Games no longer
  carry a glyph table.

Regenerate games to receive these changes. Your compilation library, fallback
hints, settings and cartridge saves are kept. F8/F9 quick states made with
1.2.1 Mega Drive, Super Nintendo and Neo Geo executables are not loaded by
regenerated games, because their state identity covers the runtime sources;
make a new one after regenerating. NES, Master System, Game Gear, Game Boy and
Sharp X68000 quick states are unaffected. The converter's own interface keeps
its accents and its eight languages. Text rendering was checked on generated
screenshots, not on every display.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.2.1 — steadier sound, cleaner menus and more sprites

- **Adaptive sound reserve on every console.** Games now watch their own sound
  output. When the sound device runs dry while the game is still producing
  audio, or stalls and forces old audio to be dropped, the output reserve grows
  by 5 ms (up to +60 ms). It shrinks again after a clean period of twice the
  interval between the last two gaps, four seconds at least. A machine with
  headroom stays at +0 ms, so its latency is unchanged; a small machine keeps
  the reserve it needs instead of crackling. Pauses and menus never count. The
  cost is a few integer operations per audio callback.
- **Sharp X68000 music.** The X68000 player started its sound with a single
  frame queued and no margin, so continuous music could break up on a small
  machine while short sound effects survived. Playback now starts with about
  40 ms queued, plus the adaptive reserve. On the Debian test machine (AMD
  A4-5000), two minutes of R-Type played without a gap.
- **Super Nintendo: Donkey Kong Country background colours.** Light, brick-like
  tiles could appear in the jungle backgrounds and spread as you walked back
  and forth. When the CPU stopped on its wait instruction exactly as a raster
  palette transfer was due, the transfer was performed a line late, mid-picture,
  and landed in the background palettes. A waiting CPU now gives the bus to the
  transfer at once. The issue dated back to 1.0.0; quick states saved before
  this release keep the damaged colours until the game reloads its palettes.
- **More sprites on screen: NES and Game Gear (F5).** On every NES game, F5 now
  draws the objects the console drops beyond eight per line, behind the
  original ones and without changing what the game sees (overflow flag,
  sprite-zero hit and cartridge counters are untouched; MMC5 keeps the original
  limit). Zapper options are now a page of F2 (press Tab). Game Gear gets the
  Master System's existing F5 sprite option.
- **One look for every in-game menu.** All consoles now use the converter's
  identity: near-black panels and gold lettering. Only colours changed; games
  carry no new image or font.
- **Quit with a single key or button.** In the in-game options (F10, or O / Y
  from a menu), the quit binding now accepts one key or one controller button as
  well as a combination. Holding it for one second quits, as before.
- **Lighter games: five in-game languages.** Generated games now include
  English, French, Italian, Spanish and German. The converter keeps Chinese,
  Japanese and Russian for its own interface; games made from it in those
  languages start in English. Each game drops about 38 KB of glyph tables.

Regenerate games to receive these changes. Your compilation library, fallback
hints, settings and cartridge saves are kept. F8/F9 quick states made with
earlier NES, Mega Drive, Super Nintendo and Neo Geo executables are not loaded
by regenerated games; make a new one after regenerating. Master System, Game
Gear, Game Boy and Sharp X68000 quick states are unaffected. Sound figures come
from host-side counters on the test machines; they are not physical latency or
listening qualification.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.2.0 — a performance milestone and the next machines

- **Faster runtimes for seven profiles, with identical traces.** Every change
  was checked against the previous runtime on comparison routes: CPU, memory,
  picture and sound traces stay byte-identical, natively and with the reference
  interpreter where one exists.
  - **NES:** on boards whose cartridge cannot observe the picture processor
    between CPU accesses (NROM, UxROM, CNROM, AxROM, MMC2/MMC4, Color Dreams
    and similar boards, and MMC1 up to 256 KiB of program ROM), it now runs late
    and catches up just before anything could observe it, rendering whole
    tiles at a time. MMC3, MMC5, VRC and other boards keep the eager clock and
    share part of the gain.
  - **Master System and Game Gear:** faster mode-4 lines, a lazily rendered
    sound chip and a lighter CPU loop.
  - **Mega Drive:** Z80 cycles that touch only the sound CPU's own memory no
    longer stop at every 68000 rendezvous; they are settled in order before
    any shared access.
  - **Super Nintendo:** picture work that is constant for a whole line is
    prepared once per line instead of once per pixel.
  - **Neo Geo:** the native 68000 path shares its registers and no longer reads
    program words twice.
  - **Sharp X68000:** wider native coverage and a faster native CPU path.
  - **Game Boy:** profiled and left unchanged; its runtime was already
    optimized in earlier releases.
- **Measured examples** (host time for the same frames, identical traces):

  | Game | Machine | Before | After |
  | --- | --- | --- | --- |
  | Battletoads (NES), 1,500 frames with audio | Windows, one pinned core | 14.07 s | 5.06 s |
  | Super Mario Bros. (NES), 1,200 frames with audio | Debian, AMD A4-5000 | 19.45 s | 11.16 s |
  | Alex Kidd in Miracle World (Master System), 7,200 frames with audio | Debian, AMD A4-5000 | 13.97 s | 6.99 s |
  | R-Type (X68000), 4,000 frames | Debian, AMD A4-5000 | 31.2 s | 14.0 s |
  | Donkey Kong Country (Super Nintendo), 600 frames | Debian, AMD A4-5000 | 18.0 s | 15.8 s |
  | Sonic the Hedgehog (Mega Drive), 1,000 frames | Debian, AMD A4-5000 | 15.4 s | 13.5 s |

  These are host costs on the measured routes. They are not complete-game,
  exact-hardware or latency qualification. See the
  [performance notes](RUNTIME_PERFORMANCE.md).
- **Stable runtimes, a growing library.** Apart from the experimental Sharp
  X68000, the runtime code of the current consoles is now stable and already
  highly optimized on Windows and Linux; further speed gains on them should be
  modest. For these consoles, the main ongoing work is the number of titles:
  the shared compilation library will gain verified entries step by step.
- **The next machines.** The technical groundwork has been reviewed for Capcom
  CPS-1/CPS-2, PC Engine/TurboGrafx-16, Game Boy Advance, Atari ST, Amiga 500
  (WHDLoad-based), Amiga 1200 AGA (WHDLoad-based), Nintendo 64 and PlayStation.
  If development goes as planned, they will join in that order, each in its own
  experimental phase. See the [roadmap](ROADMAP.md).

Regenerate games to receive the faster runtimes. Your compilation library,
fallback hints, settings and cartridge saves (battery, SRAM, memory card) are
kept and need no rebuilding. F8/F9 quick states made with earlier NES, Mega
Drive, Super Nintendo, Neo Geo and X68000 executables are not loaded by
regenerated games; make a new one after regenerating. Master System, Game Gear
and Game Boy quick states are unaffected.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.1.10 — Sharp X68000 conversion fix

- **Fixed:** converting an X68000 game again in a later session of the packaged
  converter could stop with a CMake error. The X68000 sources are now copied to
  a stable folder beside your games' build cache, and build folders created by
  1.1.9 are reconfigured automatically.
- Everything else is unchanged from 1.1.9: see below for the experimental Sharp
  X68000 profile, its notices and the expanded credits.

X68000 games made with 1.1.9 are listed as outdated because the X68000
converter files changed; regenerating them is optional. Other games are current.

---

# RetroRecomp v1.1.9 — Sharp X68000 (experimental) and expanded credits

- **Sharp X68000 is now available as an experimental profile.** Convert DIM/XDF
  disks and ordered M3U sets into standalone Windows and Linux games. Select your
  own IPL and font ROM in Options → Sharp X68000. Exports include shared menus,
  quick states, W/X controls, mouse support, autofire and initial multi-disk
  handling.
- **Measured on 19 game sets, Windows and Debian.** Each export matches a fresh
  reference run (CPU, memory, picture, sound and clock traces) on bounded
  joystick, mouse and keyboard routes and resumes identically after a saved
  state. No fallback interpreter use was observed on those routes. This is not
  complete-game, exact-hardware or latency qualification.
- **A new machine runtime without GPL code.** The X68000 machine is built from
  hissorii's PX68k (WinX68k by Kenjo, xkeropi by NONAKA Kimihiro, FMGEN by cisc)
  with Retro-Recomp's own host code and snapshots and the Musashi CPU core. The
  first conversion fetches these sources at their pinned revisions. Notices:
  [X68000 status](X68000.md).
- **Updated in-app credits.** The X68000 cell names the authors behind its machine
  code, in all eight interface languages. The Master System and Game Gear cells
  acknowledge the author's permission to use SMS/GGrecomp for this noncommercial
  project. The Musashi notice is now included for Neo Geo as well.
- **More machines ahead.** More consoles and classic computers are planned,
  with each new profile introduced and qualified in its own experimental phase.
- The public compilation library retains **1,164 verified identities**. No
  private X68000 RAM observations, disks, firmware, states or game executables
  are included. Windows and Linux use the same public snapshot.

Existing seven-console games do not need regeneration for this release.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.1.8 — Neo Geo fixes, player controls and audio options

Existing exports need regeneration for game-side changes. Updating the converter
preserves your games, settings, covers, favorites and private learning data.

- **Controller browsing:** navigate Compiled Games with the D-pad or left stick;
  A launches the selected game. Held buttons cannot relaunch a game when returning
  to the converter. Navigation is inactive behind games, dialogs and other apps.
- **Optional audio tone controls:** Off, Light and Soft in each game's Options
  panel. Off is the default and preserves the PCM samples; enabled modes reduce
  high frequencies without introducing another queue or changing the sound CPU.
- **Configurable quit combinations:** keyboard or gamepad, unassigned by default.
  Hold the combination for one second; normal saves and fallback recording finish
  during the usual shutdown. Settings are remembered by console in datas.
- **Neo Geo machine selection:** arcade-only cartridges show "Arcade Only" on
  F11, without restarting. Conversion checks the supported machine modes instead
  of failing on an impossible AES run. Required MVS and compatible AES checks
  stay active, and native failures retain their useful error message.
- **Native link-board code:** LINKABLE cartridge program ROM can use the guarded
  native path while serial status reads keep their real device behavior.
- **Cleaner Neo Geo startup:** the host covers the early firmware color test
  until the monochrome intro. Back/Coin no longer drives AES firmware Select
  lines and accidentally opens its menu. Raw hardware tests stay unchanged.
- **Reviewed box art:** Super Sidekicks 3 uses its approved front cover and reuses
  the download cache. Only the online reference is included in the converter.
- **Expanded shared knowledge:** 31 additional exact Neo Geo cartridge/BIOS
  identities bring the verified library to **1,164 records**, including **125
  Neo Geo**, compressed to **8.6 MiB**. Previous observations and the six other
  console banks are preserved; no ROM, BIOS or private raw library is bundled.
- Windows and Linux share these implementations. Physical controller/listening
  validation remains separate from the automated numeric and virtual-pad checks.

Riding Hero and League Bowling now pass their sampled native/reference, packed,
quick-state and ordinary-save checks without observed 68000 or Z80 fallback.
Irritating Maze passes its MVS checks; its trackball controls remain unqualified.
The four targeted exports pass 26 fresh-reference/packed routes. This is bounded
coverage, not a complete playthrough or independent hardware-fidelity claim.
Windows x64 and Linux x86-64 installers and portable downloads are included.
Linux remains qualified on Debian 13 / glibc 2.41; other baselines need testing.

---

# RetroRecomp v1.1.7 — Fast autofire and safer controller defaults

- **Autofire for keyboard and gamepad.** F6 now pulses held, mapped fire buttons
  on all seven consoles. Previously keyboard buttons stayed continuously held,
  so enabling autofire had no effect on them.
- **Fast, regular pulses.** One guest frame pressed, one released replaces the
  earlier 40 Hz timer, which could be poorly sampled by games. This produces
  about 30 pulses/second at 60 Hz, 25 in PAL and 29.6 on Neo Geo. New presses
  respond immediately; repeated reads, pause and state rewinds stay consistent.
  Game-specific firing limits still apply.
- **Free stick clicks.** L3/R3 no longer force pause or reset. They have no default
  game binding and remain manually assignable in F2; saved custom bindings are
  preserved. P pauses and F1 restarts.
- **More shared Neo Geo knowledge.** 28 new exact cartridge/BIOS identities bring
  the verified library to **1,133 records**, including **94 Neo Geo**, compressed
  to **8.5 MiB**. Earlier observations and the six other console banks are kept.
  Failed or interpreter-dependent qualifications are excluded.

**Regenerate existing games to receive these runtime changes.** Updating the
converter preserves games, settings, favorites, covers and private learning data.
Windows x64 and Linux x86-64 installers and portable downloads are included.
Use **Check for updates** to download the matching native converter.
Linux support remains qualified on **Debian 13 / glibc 2.41**.

Validation includes the real input readers for all seven consoles on Windows and
Debian, keyboard state and SDL virtual gamepads, plus Ghost Pilots native/reference,
packed-executable, F8/F9, ordinary-save and shared-menu checks. The new knowledge
passes 196 reference/packed routes and 56 AES state replays. This is bounded
native-coverage/integration evidence, not full-game, independent hardware or
physical-latency certification. No ROM, BIOS, downloaded cover or raw private
library is included in the packages.

---

# RetroRecomp v1.1.6 — Move your collection without broken paths

- **Portable collection paths.** Move Retro-Recomp together with `Games` and
  `datas`. Its own game/report paths and scan folders follow the app. External
  libraries and ROM folders retain their locations.
- **Repair older copied collections.** Opening Compiled Games repairs known
  local paths in a background task, using exact console/cartridge matches and
  copied reports. Old aliases merge into their local entries, keeping favorites.
  A backup of the original inventory is retained.
- **Scans clean up the list.** A completed scan also checks previously saved
  games and removes entries whose files are confirmed missing. Unavailable
  drives and unreadable folders stay listed; cancelled or incomplete scans do
  not prune entries. Two actual copies in separate folders remain distinct.

Tested against a copied collection with **1,968 entries for 984 games**: migration
leaves **984 valid paths**, retains both favorites, and two subsequent scans
produce no duplicate rows. No game is executed during these collection checks.

The verified compilation library is unchanged: **1,105 exact cartridge
identities**, **8.3 MiB** compressed. No game runtime, cartridge qualification,
graphics, audio or gameplay change is included. **Games need no regeneration.**

Windows x64 and Linux x86-64 installers and portable downloads are provided.
Linux remains checked on **Debian 13 / glibc 2.41**. Use **Check for updates** in
the installed 1.1.5 app to download the matching native converter, keeping your
data and shortcuts. See the [installation guide](INSTALLING.md) and
[collection guide](COMPILED_GAMES.md). ROMs, BIOS files, downloaded artwork and
private data are excluded from packages.

---

# RetroRecomp v1.1.5 — Your compiled collection, favorites and game cards

This update brings a persistent game collection and a more compact interface
to Windows and Linux.

- **Compiled Games.** Switch between conversion and your collection. Scan export
  folders when needed, sort and filter games, launch them, or right-click to
  rescan and regenerate. The list is restored on reopening the app.
- **Persistent favorites.** Click the star, sort by favorites or show only your
  favorites. Your choices survive rescans and regeneration.
- **Covers and short game summaries.** The side panel reuses local artwork first,
  with exported icons as a fallback. Choose or search for a front cover and
  regenerate to update the executable's icon. Existing online summaries are
  fetched only on request, for one game or a right-click selection. Cards retain
  their text, language and source locally for offline use.
- **Find original ROMs again.** Set a ROM folder for each console. Regeneration
  searches remembered locations and that folder's subfolders, checking the exact
  cartridge identity before conversion. New reports retain the source path.
- **Faster Game Memory.** Open one console at a time and reuse small cached
  summaries, including consistent console labels for older Master System records.
- **A tidier interface.** Smaller controls and rows, a fully visible Options
  Close button, and compact credits with a speaker icon. Credits pause while
  you use links or the scrollbar, then resume and reverse at either end.

The goal remains native execution from the first export. If fallback is observed,
saved hints can help a later regeneration cover those additional paths. Collection
statuses distinguish saved hints from fallback in earlier conversion checks;
absence of a saved hint is not proof of complete gameplay coverage.

The verified library remains at **1,105 exact cartridge identities** (**8.3 MiB**
compressed), unchanged from 1.1.4. This release updates the converter and its
collection workflow; it adds no new cartridge qualification or game-runtime
performance claim. ROMs, BIOS files, downloaded covers, cards, private observations
and saves are excluded from the release packages.

The 555-test suite passes on Windows and Debian, with platform-specific checks
skipped where unavailable. Eight-language layout checks pass on both systems.
Public metadata lookup was exercised across
all seven consoles; credentialed services still depend on the user's API access.
The project owner approved the interface before publication.

**Installers added:** Windows setup and a Linux per-user `.run` installer now add
application shortcuts and an uninstaller. In-app updates use the same verified
native binaries; games and private data are kept during updates and uninstall.
See the [installation guide](INSTALLING.md). The converter binaries and verified
compilation snapshot are unchanged.

Download **Retro-Recomp-1.1.5-windows-x64-setup.exe** for Windows or
**Retro-Recomp-1.1.5-linux-x86_64-install.run** for Linux. Portable downloads remain
available: **Retro-Recomp.exe** for Windows and
**Retro-Recomp-1.1.5-linux-x86_64.tar.gz** for Linux. The separate Linux executable
is also available for updates. Linux x86-64 is qualified on **Debian 13 / glibc
2.41**; other distribution baselines and ARM64 remain separate work.

---

# RetroRecomp v1.1.4 — Animated credits and ChipLoom music

The credits become a small demoscene presentation in RetroRecomp's charcoal,
white and gold colors, on both Windows and Linux.

- **An animated credits screen.** Fast approaching stars, moving waves, a
  perspective floor and rotating cubes surround the scrolling credits.
  Two checker spheres bounce on the music's kick and snare, with a small
  response to hi-hats. The scrollbar, mouse wheel and keyboard let you take
  over the scrolling; automatic scrolling can be resumed at any time.
- **Real four-channel MOD playback.** Three original tracks created with
  [ChipLoom](https://github.com/ArthurReboulSalze/ChipLoom) are replayed directly
  by a small native player. Reopening credits chooses a different track, never
  the same one twice in a row. A mute button remembers your preference.
- **A centered Options dialog.** Options now open centered over the converter,
  matching the credits window's behavior.

The user has approved the Windows presentation and music. Automated checks
cover scrolling, track selection, mute and close/reopen behavior across eight
languages on Windows and Debian. Three minutes of each module produce identical
PCM to the full reference decoder and matching percussion counts on both OSes.
The player is embedded in the converter only; no extra player installation is
required. See [credits implementation and checks](CREDITS.md).

The verified compilation library remains at **1,105 exact cartridge identities**
(**8.3 MiB** compressed). No cartridge campaign or game-runtime change is part of
this update. **Existing games do not need regeneration.** ROMs, BIOS files,
downloaded covers, private observations and saves are excluded from the release.

Download **Retro-Recomp.exe** for Windows or
**Retro-Recomp-1.1.4-linux-x86_64.tar.gz** for Linux. The separate Linux executable
is available for manual updates. **Check for updates** selects the matching
native executable. Linux remains qualified on Debian 13 / glibc 2.41; broader
distribution support and ARM64 remain future work.

---

# RetroRecomp v1.1.3 — Safer batches and a richer, smaller knowledge library

This release improves conversion reliability across all seven console profiles
on Windows and Linux, with a refreshed interface screenshot and a verified
knowledge library covering **1,105 exact cartridge identities**.

- **Resume interrupted batches.** Unfinished rows return to the list when the
  converter reopens. Resume the whole batch or only the selected games.
- **Keep useful exports.** Freshness checks follow each console's compiler,
  settings and exact-game hints. Interface-only updates no longer force
  recompilation; relevant runtime changes still do.
- **Safer parallel work.** Game Boy and NES merge new observations without
  overwriting discoveries from another conversion. Interrupted Game Boy writes
  recover the previous verified trace. Compiler tasks share the available CPUs.
- **Less temporary memory.** Large export checks and incremental source hashing
  use bounded buffers. Long Unicode titles no longer risk a filename-collision
  loop, and busy library locks have a timeout on both systems.
- **Compiler and runtime refinements.** Stable source/packaged code identities
  avoid unnecessary cache invalidations. NES sprite selection avoids repeated
  work, and Mega Drive rejects invalid banked feedback offsets safely.
- **More verified knowledge, smaller download.** Twelve new Game Gear identities
  and one newly qualified Neo Geo identity bring the library to 1,105 records.
  Lossless SNES reference compaction reduces it to **8.3 MiB**, about 40% smaller
  than 1.1.2, while retaining all earlier observations and all 606 Game Boy records.

The 519-test Python suite passes on Windows and Debian, with 1 and 14 skips.
Native feedback, NES output comparisons and targeted compiler checks pass;
source and packaged identities are checked separately. These checks do not
establish complete gameplay coverage or physical-hardware accuracy.

Linux x86-64 is qualified on Debian 13 / glibc 2.41. The reported Mega Drive
slowdown on the low-power Debian machine has improved but is not fully resolved;
other distributions and ARM64 still need qualification.

Download **Retro-Recomp.exe** for Windows or the **Linux x86-64 tar.gz** for Linux.
The separate Linux executable is also provided for manual updates. Regenerate
existing games to receive runtime changes. ROMs, BIOS files, downloaded artwork,
private observations and save files are excluded from these packages.

---

# RetroRecomp v1.1.2 — Conversion fixes and a tidier header

This update improves conversion startup and window behavior, with the same fixes
and header layout on Windows and Linux.

- **Faster preparation in large export folders.** Converting a small selection
  no longer opens every unrelated game executable already covered by an export
  report. Exact ROM identities, conflicting revisions and unknown exports keep
  their overwrite protections.
- **Clearer progress and closing.** The log announces export checking before
  compilation starts. Stop during preparation prevents new conversions; closing
  the app during a batch finishes active conversions, then exits automatically.
- **A tidier header.** Console format sits beside Language. The Windows/Linux
  version label moves below, next to the gold squares. The banner keeps its
  height, with alignment checked across all eight languages and smaller windows.

The Windows recompilation reported as blocked in 1.1.1 has been retested
successfully by the user with this fix. ROM-free regression checks cover scoped
export inspection, revision conflicts, cancellation and shutdown. The verified
knowledge snapshot remains at **1,092 exact cartridge records**; this update
adds no new cartridge qualifications or game-runtime changes.

Download **Retro-Recomp.exe** for Windows or
**Retro-Recomp-1.1.2-linux-x86_64.tar.gz** for Linux. **Check for updates** selects
the matching executable. Existing games do not need regeneration for these
converter-only fixes. Games, settings, downloaded covers and local knowledge
remain in their existing folders.

Linux is built and checked on **Debian 13/glibc 2.41**; other distributions and
ARM64 remain unqualified. The earlier reported Mega Drive slowdown on the
low-power Debian test machine is still a separate, unresolved issue.
These interface and conversion checks do not establish full-game compatibility,
hardware fidelity, physical latency or whole-game framerate.

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.2/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.1.1 — Shared runtime optimizations for Windows and Linux

This release reduces repeated graphics, audio and CPU-scheduling work in the
generated games. Windows and Linux receive the same runtime changes; regenerate
existing games to include them.

- **Lighter graphics processing.** Master System/Game Gear tile rows, NES sprite
  updates and Super Nintendo background decoding avoid repeated calculations.
  All seven console profiles share an optimized Scale2x filter.
- **Less audio overhead.** Sega filtering and mixing, Mega Drive recovery and
  Game Boy/NES output callbacks retain the same samples on the comparison
  tests while doing less host work. Guest audio and console clocks stay active.
- **Mega Drive engine improvements.** Precomputed 68000 preparation plans,
  fewer redundant Z80 scheduler transitions and batched VDP rendering preserve
  live fetch guards, bus transactions and raster events on the tested cases.
- **Native Linux build improvements.** GCC can optimize the 16-bit hardware
  helpers across source files using a private profiling pass. The final build
  still receives the normal validation; training counters are not exported.
- **Clearer documentation.** The README and new
  [performance notes](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.1/docs/RUNTIME_PERFORMANCE.md)
  describe the scope, reproducible checks and remaining Linux performance work.

ROM-free comparisons pass on Windows x64 and Debian 13 x86-64: over 30 million
pixel comparisons in the shared optimization corpus, separate SNES rendering
checks, 44,800 NES state/video/audio/bus checkpoints per platform, full audio
schedule tests and Mega Drive CPU/bus/VDP regressions. Both optimized and scalar
paths are checked. These bounded checks establish agreement on the tested
cases, not universal hardware fidelity, full-game compatibility or physical latency.

**The reported Mega Drive slowdown on the low-power Debian test machine remains
unresolved.** Isolated routine speedups are not whole-game framerate gains.
Gameplay, listening and desktop performance tests remain separate. Linux still
targets **Debian 13/glibc 2.41**; other distributions and ARM64 are not qualified.

The verified knowledge snapshot remains at **1,092 exact cartridge records**;
this optimization release adds no new cartridge qualifications. Your games,
settings, cover cache and local knowledge are preserved when updating the app.
Quick states remain tied to their qualified runtime ABI; retain ordinary saves
before regenerating games.

Download **Retro-Recomp.exe** for Windows or
**Retro-Recomp-1.1.1-linux-x86_64.tar.gz** for Linux. **Check for updates** selects
the matching Windows EXE or Linux executable asset. Conversion needs the native
build toolchain; playing generated games does not. See the
[Linux guide](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.1/docs/LINUX.md).

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.1/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.1.0 — Windows and Linux, eight languages

RetroRecomp now has a native Linux x86-64 package alongside the Windows app.
Both use the same console implementations, reviewed cover references and
verified compilation knowledge.

- **Native Linux conversion.** First exports for all seven console profiles
  pass their bounded generation checks on Debian 13. Linux games have cover
  launchers, shared menus, controls, saved settings and fallback feedback.
  ARM64, older glibc versions and other distributions remain to be qualified.
- **Eight languages.** English, French, Italian, Spanish, German, Chinese,
  Japanese and Russian in the converter and generated-game menus. F7 cycles
  the game language. Windows retains its original Segoe UI for Latin/Cyrillic;
  compact CJK/Cyrillic game glyphs avoid oversized text.
- **A more flexible interface.** Larger decorative console artwork within the
  original-height banner; the ROM list and log can shrink for smaller screens.
  The redundant platform selector becomes a Windows/Linux version label.
- **Linux drag-and-drop and covers.** Drop files or folders into the app. The
  existing cover cache and reviewed links are shared across platforms. Optional
  Linux API accounts use the desktop keyring, with no plaintext fallback.
- **Manual updates on both systems.** The button selects the matching GitHub
  asset, checks its integrity, replaces the converter and restarts it. Games,
  downloaded covers, settings and local knowledge are preserved.
- **Shared knowledge and cover fixes.** The verified snapshot now contains
  1,092 exact cartridge records, including 65 Neo Geo cartridge/BIOS identities.
  Reviewed front-cover links for Bang Bead and Voltage Fighter Gowcaizer replace
  misleading flyers. ROM-free knowledge remains separate from private feedback.
- **Linux NES optimization.** Lower PPU overhead and profile-guided compilation
  improve the native build while retaining fresh CPU, image and audio checks.

Download **Retro-Recomp.exe** for Windows or the **linux-x86_64.tar.gz** archive
for Linux. The Linux build requires Debian 13/glibc 2.41 compatibility; see the
[Linux guide](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.0/docs/LINUX.md).
Conversion requires the native toolchain; playing exported games does not.
Existing exports need regeneration to receive runtime/menu changes.

Compilation checks are bounded and do not establish full-game compatibility,
physical latency or framerate on every machine. Gameplay and display validation
on the target Linux machine remain separate from native/reference agreement.

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.1.0/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.0.3 — Stronger Neo Geo coverage and corrected covers

This update brings the latest Neo Geo discoveries and reviewed front covers
into the converter, ready for your next generation.

- **More shared knowledge.** Verified hints now cover **1,069 exact cartridge
  revisions**, including **42 Neo Geo cartridge/BIOS identities**. Eight new
  Neo Geo records add about **331 KiB** compressed while preserving every
  earlier record and the existing validation checks.
- **Better Neo Geo coverage.** An additional enhanced-mode route discovers
  banked code missed by the standard routes. On the tested Twinkle Star Sprites
  sequence, the regenerated export drops from 3,195 interpreted 68000
  instructions to zero, with matching reference results.
- **Complete clone archives load correctly.** A self-contained Neo Geo revision
  no longer incorrectly requires a separate parent archive. Split archives
  still check for the components they actually need.
- **Corrected front covers.** The approved Art of Fighting 3 and Rage of the
  Dragons covers replace misleading flyers. Downloads are cached and reused.
  A changed reviewed cover reference makes an automatic-artwork export eligible
  for regeneration; a manually chosen cover keeps priority.

Eight Neo Geo exports pass 49 fresh reference/packed comparisons, MVS/AES quick
states and ordinary-save checks. All eight also pass enhanced-mode comparisons
without observed main or sound CPU fallback. These checks cover retained
gameplay paths, rather than complete playthroughs or physical hardware fidelity.

Download **Retro-Recomp.exe** below, or use **Check for updates** in the app.
Regenerate affected games to receive the new coverage and icons. Updating the
converter preserves games, settings, downloaded covers and your local knowledge.

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.0.3/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.0.2 — Seven supported consoles, smarter regeneration

**Neo Geo leaves experimental status**, following further gameplay tests.
This release makes everyday conversion more selective and reduces repeated
Neo Geo validation work while keeping checks on the delivered executable.

- **Keep games that are already up to date.** An unchanged converter/runtime,
  ROM, options, BIOS and fallback hints no longer trigger another conversion.
  The existing EXE is checked by SHA-256. Changed inputs or new hints regenerate
  normally; Options can force regeneration, and overwrite protection still works.
- **Convert selected games.** Select one or several ROM rows and use the new
  button; the full-list conversion remains available.
- **Enhanced Neo Geo is on by default.** More virtual 68000 capacity and a higher
  sprite limit help with busy scenes. F5 restores the original limits; saved
  preferences remain respected.
- **F11 switches Neo Geo arcade MVS / console AES with a clean restart.** This
  requires the supported AES firmware in your own selected BIOS archive.
  Each mode keeps separate quick states, ordinary saves and fallback hints.
- **Less repeated work.** Independent checks can run in parallel within the
  batch's resource budget. Every reference route is compared on the final packed
  EXE; the duplicate uncompressed replay is removed. Multiple save checkpoints
  share one continuous run, and unchanged compressed cartridge data is reused
  after verifying its hash. Reference, save, malformed-state and persistence
  checks remain mandatory.
- The README now explains the optional Master System sprite flicker reduction
  and Neo Geo enhancements, with their limits and shortcuts.
- Refreshed verified Neo Geo observations are included in the shared library,
  which retains 1,061 exact identities across the seven consoles.

Download **Retro-Recomp.exe** below, or use **Check for updates**.
Regenerate Neo Geo games to receive F11 and the enhanced default. Old exports
without a freshness receipt are regenerated once; future unchanged exports can
then be skipped. A new export is not a guarantee of zero fallback on every path.

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.0.2/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.0.1 — Play. Learn. Recompile.

**Your play sessions can now help improve your next export.** This release also
introduces Neo Geo as an **experimental** seventh console profile.

- Games collect small, deduplicated fallback hints in memory and save them when
  you close the game. There are no feedback writes during play. **F12** toggles
  recording; it is enabled by default. A brief message appears in the existing
  game window while hints are saved.
- **Options → console → Import fallback hints** recovers observations from the
  normal export folder or another folder you choose. They remain in the
  converter's local library even if the original game folder is moved or deleted.
  No ROM selection or recompilation is needed to import them.
- The next generation rechecks those hints against the exact game and uses them
  to improve supported native code coverage. Each feedback file is capped at
  about **128 KiB**. This does not automatically fix graphics or hardware issues.
- **Neo Geo MVS Europe is experimental.** It includes shared controls, filters,
  fullscreen, F8/F9, scores and memory-card saves, with a user-selected BIOS.
  Visual artifacts remain under investigation. An optional F5 enhanced mode
  increases virtual CPU capacity and sprite limits.
- The verified shared bank now contains **1,061 exact revisions**, including
  **34 Neo Geo cartridge/BIOS identities**. Private gameplay feedback is kept
  separate from this verified shared snapshot.
- Shared xBR rendering reuses unchanged image regions without changing the
  filter's output. The README adds a transparent illustration of the learning
  cycle and clearly separates the six supported consoles from experimental Neo Geo.

Download **Retro-Recomp.exe** below, or use **Check for updates** in the app.
**Regenerate existing games to receive F12 and the shutdown feedback recorder.**
Updating the converter preserves your games, settings, local knowledge and
downloaded covers.

No ROMs, BIOS, generated games, downloaded covers or private feedback are included.
Notices are embedded in the executable. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/v1.0.1/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v1.0.0 — Super Nintendo standard profile is now supported

**The standard Super Nintendo profile leaves experimental status.** All six
console profiles are supported within their documented cartridge scope.

- Super Nintendo supports ordinary LoROM/HiROM cartridges in PAL/NTSC, quick
  states, battery saves and Super Scope. DSP-1 and CX4 boards are also qualified;
  CX4 device interpretation remains visible. Other enhancement chips and
  extended cartridge layouts require separate integration.
- SNES audio, display modes, sprite rendering, cartridge decoding, DMA/HDMA and
  interrupt handling have been improved and checked on a wider cartridge set.
  Guarded RAM code keeps changing operands live, reducing unnecessary fallback.
- The verified ROM-free bank now includes **1,027 exact revisions**, with
  **44 SNES records**. Repeated sound-CPU references use a lossless compact
  encoding; existing discoveries are preserved and each new game is validated.
- Drag ROMs, ZIPs or folders directly into the converter. Mixed-console batches
  still use automatic detection and the selected parallel conversion count.
- NES native coverage has further guard and memory-window improvements.

Circuit qualification includes eight packed SNES exports, four longer device
routes, fresh-process states and independent authored DSP arithmetic checks.
Native coverage, hardware checks and sampled gameplay remain separate evidence;
complete playthroughs, every cartridge circuit and physical latency are not claimed.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
**Regenerate SNES and NES exports to receive the runtime improvements.** Updates
preserve games, settings, local knowledge and downloaded covers. Older quick
states with incompatible runtime signatures are rejected without being rewritten.
The next major development target is **Neo Geo**, a larger integration stage.
This release does not include Neo Geo support.

No ROMs, downloaded artwork, generated games, firmware or private settings are
included. Legal notices are inside the executable.

[UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v0.26.0 — stronger NES recompilation and shared knowledge

- NES recompilation now handles more code executed from RAM and cartridges
  whose active ROM bank changes during rendering. Observed routines use
  protected native bodies with live operands; unknown cases retain visible
  interpreter fallback.
- Fourteen targeted cartridge cases were qualified across the two NES
  development blocks. The eight latest compressed exports have zero
  interpreted cycles on their 24 retained paths, with 86,400 matching
  CPU/memory/frame/audio comparisons. Six NTSC revisions also match a separate
  software oracle on 7,200 scripted frames.
- PAL/NTSC tests extend DMA audio/sprite transfers, pending interrupts/reset
  and save-state continuation. The expanded native matrix passes over
  1.26 million instruction cases; the ROM-free Python suite passes 337 tests.
- The converter bundles verified, ROM-free hints for **991 exact cartridge
  revisions**, including **29 NES records and 759 guarded NES RAM entries**.
  The compressed knowledge snapshot is about 9 MiB. Its other-console records
  are preserved, and new games still undergo their own analysis and validation.
- Interrupted NES discoveries can be reused locally on a retry. Only successful
  qualified observations enter the shared snapshot, and build receipts preserve
  the compiled RAM guards during configuration.

Master System, Game Gear, Game Boy, NES and the Mega Drive standard-cartridge
profile remain supported within their documented scope. **Super Nintendo
remains experimental.** These checks cover retained scenarios, not complete
playthroughs, every cartridge circuit or physical latency.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve games, settings, local knowledge and downloaded covers.
**Regenerate NES exports to receive these improvements.** Quick states from
older NES runtimes may be incompatible; rejected files are never overwritten.
No ROMs, downloaded artwork, generated games or private settings are included.

Legal notices are included in the EXE. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v0.25.0 — Mega Drive is now supported

**Mega Drive leaves experimental status. Super Nintendo remains experimental.**
Master System, Game Gear, Game Boy, NES and the Mega Drive standard-cartridge
profile are supported within their documented scope.

- Mega Drive supports PAL/NTSC, three/six-button controllers, quick states,
  SRAM, qualified EEPROM and Sega bank mapping, plus Menacer input.
- A 32-cartridge qualification panel passes its retained scenarios without
  interpreted main or sound CPU instructions. The actual compressed exports
  also pass reference comparisons, state reloads and corrupt-state rejection.
  Five selected routes extend to 36,000 frames.
- Shared Mega Drive rendering, bus, interrupt and instruction handling have
  been refined. Advanced conversion now tests at least 24,000 demo frames to
  discover later execution paths before normal reference validation.
- The converter bundles verified, ROM-free hints for 985 exact cartridge
  revisions across all six consoles, including 82 Mega Drive records. The
  compressed snapshot occupies about 9 MiB; new games still receive their own
  analysis and validation.
- Generated games show their compilation version in **H** help. **F3** adds
  xBR contour smoothing as the last filter, alongside sharp pixels, Scale2x
  and proportional scanlines. Game Boy **F5** switches its palette directly;
  Master System **F5** toggles optional sprite flicker reduction.
- Audio buffering has been refined for Master System, Game Boy and NES to
  reduce avoidable delay while preserving stable sound output.

This qualification covers the documented standard cartridge profile, rather
than every cartridge or a complete playthrough. Native coverage, CPU agreement,
hardware fidelity, gameplay and physical latency remain separate measures.
See [compatibility and evidence](COMPATIBILITY.md) for the scope and remaining work.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve games, settings, local compilation knowledge and downloaded
covers. Regenerate games to receive the compiler/runtime changes. No ROMs,
downloaded artwork, generated games or private settings are included.

Legal notices are included in the EXE. [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).

---

# RetroRecomp v0.24.0 — broader native coverage and smarter cover searches

- Game Boy uses more efficient generated C and reuses byte-identical build
  files, preserving native discovery, optimization and CPU validation. Bank
  boundaries, shared native entry selection and additional guarded RAM helpers
  improve previously failing conversions. Fourteen targeted cartridges now
  pass their checks; thirteen have no fallback on the tested paths.
- Mega Drive learns native instructions at the end of work RAM and tests
  early-start gameplay paths. The latest 20-cartridge batch passes all four
  scenarios per cartridge without main or sound CPU fallback, including
  internal CPU/memory/video/PCM comparisons.
- Cartridge identification accepts additional valid Mega Drive region headers
  and Japanese Super Nintendo header titles, without guessing another game's
  profile or accepting unsupported cartridge hardware.
- Shared cover searches handle articles, punctuation, abbreviations, Roman
  numerals, subtitles and small typos across all six consoles. Sequels, years
  and special editions stay distinct; ambiguous results are not guessed.
- The converter includes 34 reviewed front-cover references and verified,
  ROM-free compilation hints for 954 exact cartridge revisions. The compressed
  knowledge snapshot occupies about 7.4 MiB. No cover images are bundled.
- Game Boy's unused debug layout no longer writes an `imgui.ini` beside games.
  Existing game settings remain in `datas`, as on the other profiles.

**Mega Drive and Super Nintendo remain experimental.** Standard eligible
cartridges are analyzed automatically, with no fixed game allowlist. Broader
native coverage does not certify unusual cartridge hardware, all display/audio
modes or complete gameplay. See [16-bit support and remaining work](CONSOLES_16BIT.md).
Native coverage, CPU agreement, hardware fidelity, gameplay and physical latency
remain separate measures. Game Boy build timings distinguish cold builds from
repeat conversions; the validation scope has not been reduced.

Validation passes 282 ROM-free Python tests, 8,064 authored Mega Drive
instruction/state comparisons, 47,104 Game Boy bank-boundary comparisons,
65,536 native-entry selector checks and 28,277 guarded RAM-helper checks.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve games, settings, local compilation knowledge and downloaded
covers. Regenerate affected games to receive compiler/runtime changes. No ROMs,
downloaded artwork, generated games or private settings are included.

---

# RetroRecomp v0.23.0 — a new look and stronger conversion support

- New charcoal-and-gold identity, cartridge logo, outlined console artwork
  and refreshed English/French interface. The ROM list has a clear empty state,
  and the log panel includes its own scrollbar.
- Parallel batches keep available workers busy when duplicate inputs are waiting.
- Cartridge headers improve Master System/Game Gear detection, including
  renamed files and ZIP archives.
- Eligible Mega Drive and Super Nintendo cartridges can be analyzed even when
  absent from the regression catalogue. Unsupported cartridge hardware is still
  reported, and both profiles remain experimental.
- The bundled compilation library now includes verified Master System hints
  for 258 exact cartridges, with 338 cartridge identities across all six consoles.
  Reference CPU bus/interrupt fixes and long-path support improve new conversions.
- Game Boy adds guarded native support for a common sprite-DMA helper.
- Twelve reviewed front-cover references improve artwork selection and replace
  known incorrect cached images. Only public links and metadata are bundled.

The Master System qualification scenarios used 7,200 frames each for demo and
scripted play, with strict native and reference comparisons. Native coverage,
CPU agreement, hardware fidelity, gameplay and physical latency remain separate
measures. These checks do not guarantee complete compatibility with every game.

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updates preserve your games, settings, compilation library and downloaded covers.
Regenerate a game to receive runtime changes. No ROMs, downloaded artwork,
generated games or private settings are included in this release.

---

# RetroRecomp v0.22.0 — remembered display and 16-bit quick states

- Generated games remember their last display mode and filter, including
  pixel-perfect and aspect-fit fullscreen. Settings remain shared per console.
- F8/F9 quick states now work on qualified Mega Drive and Super Nintendo
  profiles, including after closing the game. Missing loads create no folders.
- The same proportional scanline mask is used across all six consoles.
- Window execution-status text stays in English with either menu language.
- A compact compilation-knowledge library is included in the converter, with
  verified hints for 327 exact cartridge revisions across all six consoles.
  It contains no ROM bytes, artwork or personal settings. New discoveries stay
  local and normal validation remains enabled.
- Broader cartridge checks and guarded RAM execution improve Game Boy, NES and
  16-bit support. Mega Drive now covers 27 qualified revisions and Super Nintendo
  12, including selected PAL revisions. Both 16-bit profiles remain experimental.

234 ROM-free Python tests pass in the development checkout. Fresh-process
quick-state replay matches the uninterrupted image, sound and machine state on
eight tested Mega Drive/SNES games. Display persistence and fractional scanline
geometry are checked separately. These checks do not establish complete gameplay,
independent hardware fidelity or physical latency.

Regenerate games to receive these runtime changes. State compatibility requires
the same ROM, video standard and compatible runtime ABI. See
[state formats and validation](GAME_STATES.md).

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Updating the converter preserves your existing games, settings and cached artwork.
Original component notices remain embedded; their own licensing terms apply.

---

# RetroRecomp v0.21.0 — saved covers and expanded 16-bit support

## Your artwork, ready for regeneration

Downloaded covers are saved in `datas/BoxArt` beside the converter, separated by
console. Regenerating a game reuses its validated image without another network
request, including after a ROM rename or a change of export folder. Front and
three-quarter versions are retained separately, and existing downloads are reused.
Changing API credentials keeps your artwork. Title-screen and screenshot fallbacks
are retained too. Missing or damaged images use the normal search.

## More 16-bit coverage and smoother audio

Mega Drive now includes twenty-two qualified NTSC revisions and an optional
advanced scan. Both its 68000 and sound Z80, and the Super Nintendo's 65816 and
SPC700, use guarded native paths. Super Nintendo adds four qualified revisions
for six in total, with improvements to interrupt scheduling and audio delivery.
See the [current compatibility limits](CONSOLES_16BIT.md).

Box-art searches prefer Internet front covers by default, with alternate public
hosts and fallback images when a box is unavailable. The SNES audio host now keeps
a reserve suited to the output device and initializes its audio clock from boot.

## Update

Use **Check for updates** or download the single Windows x64 **Retro-Recomp.exe**.
Your games, settings, learning library and downloaded artwork stay local and are
preserved by an update. Regenerate games to receive runtime improvements.
No ROMs, downloaded artwork, generated games or private settings are bundled.
Component notices are embedded; the matching [UPX sources](../licenses/upx-5.2.1-src.tar.xz)
remain available in the repository.

Native coverage, agreement with the internal reference, hardware fidelity,
gameplay validation and physical latency remain separate measures. Mega Drive
and Super Nintendo remain experimental; the other four console profiles are supported.

---

# RetroRecomp v0.20.0 — lightguns across more consoles

## Play with the mouse

Mega Drive now supports Menacer aiming in **Menacer 6-Game Cartridge** and
**T2 - The Arcade Game**. Super Nintendo adds **Super Scope 6**. Move the mouse
to aim, left-click to fire, and use **F5** to choose the cross or dot, size and
color. The default red cross has thicker strokes for better visibility.
Original controller-selection and calibration screens remain intact.

T2's gun detection and CPU/audio scheduling have been corrected. Gun input in
all three games has been confirmed by the user after the fix.

## One app, six consoles

The README is shorter and focuses on the multiconsole experience: mixed-folder
batches, compact standalone games and shared menus. Master System, Game Gear
and original Game Boy are supported. NES, Mega Drive and Super Nintendo remain
experimental; the 16-bit profiles accept six qualified Mega Drive revisions
and two Super Nintendo revisions. See the [current game list](CONSOLES_16BIT.md)
and [gun controls](GUNS_16BIT.md). Other gun games are not automatically enabled.
PAL execution and F8/F9 states are still unavailable on the 16-bit profiles.

## Validation

168 ROM-free Python tests and 127 authored native gun checks pass. Each new gun
cartridge passes 3,600-frame demo and scripted-play comparisons with the internal
reference, with zero interpreted main-CPU instructions on those tested paths.
The sound processors remain interpreted. CPU agreement, hardware fidelity,
complete gameplay and physical latency are separate measures; these checks do
not establish complete hardware accuracy or zero latency.

## Update

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Regenerate the affected games to receive the gun improvements. Updating the
converter preserves existing games and settings. No ROMs, downloaded covers,
generated games, personal settings or compilation library are bundled.
Component notices remain embedded in the EXE; their own licensing terms apply.
The matching [UPX source archive](../licenses/upx-5.2.1-src.tar.xz) is in the repository.

---

# RetroRecomp v0.19.0 — more native 16-bit execution and refined scanlines

## Mega Drive

Sonic the Hedgehog now uses the same instruction-AOT path as Columns,
Golden Axe and Castle of Illusion, preserving the real 68000 PC, stack and
interrupt frames. The earlier Sonic-specific callbacks are no longer used
on this path. After learning four missing ROM entries, demo and scripted-play
checks of 3,600 frames each completed with zero interpreted main-CPU opcodes.
Their complete visible-frame sequences and final CPU, memory and VDP state
match the internal reference. Golden Axe also passes the same full-length
regression check. The sound Z80 remains interpreted.

## Super Nintendo

Super Mario World now has a compiled 65816 operation map for every physical
ROM byte, with live LoROM mapping, real PC/stack control flow, timed operand
reads and register-width handling. Conversion tests learn RAM helpers in
a library scoped to the exact cartridge hash; each native helper verifies
its PC and four live bytes before running. Modified or unknown code keeps
the reported fallback. Games never write this learning library themselves.

The first ROM-only pass reported 372,060 interpreted instructions in demo and
100,750 in play. Learning 130 RAM variants reduced both to zero over the next
two 3,600-frame checks, about 49 million retired instructions per scenario.
Visible-frame sequences, final CPU/memory state and CPU/master/APU clocks
match the internal reference. The earlier reference divergence is resolved
on these tested paths. Authored fixtures pass 16,544 instruction/state/bus
comparisons, including register widths and changed-code guards.
The SPC700 sound processor remains interpreted.

## Scanlines and validation

Mega Drive and SNES scanlines now draw a fine translucent gap for each guest
raster row instead of darkening every other game row. A cached mask follows
the actual display height, including fractional fullscreen scaling and HiDPI;
below 2x, the effect stays off to preserve readability. Framebuffers and guest
timing are unchanged. Numeric presentation checks pass, and both compressed
test exports launch with the filter active without creating files or folders.

Both 16-bit converters compare native and reference execution over the full
requested demo/play length. Missing diagnostics or differences reject the
candidate and preserve the previous export. The memory command also reports
the MD/SNES converter's ROM entries, guarded RAM variants and library size.
162 ROM-free Python tests pass. Native/reference agreement uses shared engine
semantics; independent hardware fidelity, complete gameplay and physical
latency remain separate evidence.

## Scope and update

Mega Drive and SNES remain experimental. Compatibility is still restricted
to the four exact qualified NTSC Mega Drive revisions and the qualified USA
revision of Super Mario World. Other games, PAL execution and F8/F9 states
are not enabled for these profiles; SNES cartridge-save persistence is also
unfinished. SNES conversion needs installed stable Rust >= 1.85.
See [qualified cartridges and evidence](CONSOLES_16BIT.md).

Download the single Windows x64 **Retro-Recomp.exe**, or use **Check for updates**.
Regenerate games to receive the new execution paths and scanlines; updating
the converter preserves existing game exports and settings. No ROMs, downloaded
covers, generated games, settings or personal compilation library are bundled.
Component terms and notices remain in the EXE, including the imported
frameworks' PolyForm Noncommercial licences. The matching
[UPX 5.2.1 source archive](../licenses/upx-5.2.1-src.tar.xz) remains in the repository.

# RetroRecomp v0.18.0 — Mega Drive expansion and broader NES support

The Windows converter now includes **six console profiles**. Master System,
Game Gear and original Game Boy remain supported for everyday use. NES,
Mega Drive and Super Nintendo are experimental, with explicit compatibility
limits and separate native, reference-CPU, hardware, gameplay and latency evidence.

## Mega Drive and Super Nintendo

Mega Drive accepts exact qualified NTSC revisions of **Sonic the Hedgehog,
Columns, Golden Axe and Castle of Illusion**. A new instruction-level compiler
for the latter three follows the real 68000 PC, stack and interrupt frames.
Conversion passes learn missing ROM entries and RAM instruction variants;
native RAM code checks every instruction byte before running. Changed or
unknown code uses the reported fallback. Failed reference comparison preserves
the previous export.

With an empty converter library, each of those three games reached zero
interpreted 68000 opcodes in two passes, on demo and scripted-play tests of
3,600 frames each. The complete visible-frame sequences and final CPU/memory/
VDP state matched the internal reference. Cold conversions took about 65–78
seconds per title with two concurrent jobs on the development machine;
these are local measurements, not a speed guarantee. Authored fixtures passed
6,208 instruction/state comparisons, plus stack and modified-RAM guard checks.
The VDP's H32/H40 mode selects the correct 256/320-pixel display width.

The Mega Drive sound Z80 remains interpreted. Sonic retains its earlier
compiler route and reference divergence. The experimental Super Nintendo
profile accepts only the qualified USA revision of **Super Mario World**;
it retains substantial 65816 fallback, interpreted SPC700 sound and reference
divergence. Both profiles share RetroRecomp's menus, controls, filters,
fullscreen, cover icons and compressed exports. PAL and F8/F9 are not enabled
for either profile; persistent SNES cartridge saves are also not implemented.
SNES conversion additionally needs an installed stable Rust toolchain >= 1.85.
See [qualified cartridges, dependencies and evidence](CONSOLES_16BIT.md).

## NES

Native coverage now prepares every physical PRG ROM entry, including
bank-switched cartridges, with dispatch following live mappings and operands
read from the live bus at bank boundaries. RAM execution and unstable mappings
keep their fallback safeguards. Authored NROM/MMC1/UxROM/CNROM/MMC3 checks passed
332,800 instruction cases across NTSC and PAL. Targeted Super Mario Bros. 3,
Mega Man 2 and Mega Man probes reached zero fallback on three 1,800-frame paths.

The NES profile adds selectable PAL timing, persistent F8/F9 quick states and
mouse Zapper input for known gun games, with a configurable red cross by
default. States verify ROM identity, timing, ABI and corruption before loading;
failed loads leave the running game intact. Normal launch/quit and loading a
missing state create no data folder. The full 256 × 240 NES picture remains
visible. See [NES scope and limits](NES.md).

## Controls and update

Key labels and letter defaults follow the active keyboard layout, including
AZERTY, in the Master System, Game Gear, NES and new 16-bit menus. Saved custom
mappings retain their physical key positions; Game Boy already handled this.

Download the standalone Windows x64 **Retro-Recomp.exe**, or use the manual
**Check for updates** button. Regenerate a game to apply runtime changes;
updating the converter preserves existing game executables and settings.
No ROMs, downloaded covers, generated games, settings or personal compilation
library are included. Third-party terms and notices are retained, including
the 16-bit engines' PolyForm Noncommercial licences.

Native/reference agreement is bounded software evidence using shared engine
semantics, not an independent hardware oracle or a full-game playthrough.
Physical latency has not been measured. Gameplay review remains separate.

# RetroRecomp v0.17.0 — improved Sega audio and better box-art icons

Master System and Game Gear exports now use an audio path with shorter
sample-rate conversion staging and a bounded output buffer. It accepts the
Windows device's actual callback period and primes playback to accommodate
PAL/NTSC frame delivery. Pause, restart and state load clear queued sound.
Console clocks, input handling and PSG sound synthesis are unchanged.

ROM-free numeric checks passed for PAL/NTSC timing, stereo separation, filter
response, buffer bounds and callback scheduling. Silent WASAPI output checks
also passed. On the local Alex Kidd cartridge, two 600-frame scenarios kept
identical raw PSG sound, VDP traces and final CPU states before/after the change,
with matching reference CPU states and zero fallback. These are bounded
technical checks; total physical audio latency has not been measured.
See [audio details](AUDIO.md).

**Options → Box art** adds user-configured ScreenScraper, TheGamesDB and IGDB
access. API credentials are stored separately with Windows account protection;
ordinary website accounts alone are not enough for these services. Local
artwork remains first priority, with the public Libretro library as a no-key
fallback. ArcadeItalia is listed for reference; its MAME API does not serve
the current console profiles.

Real three-quarter box images are preferred. When one is unavailable, the
front cover stays flat: no artificial spine or perspective is added. Original
or HD sources are requested when available, and all nine ICO sizes, up to
256 × 256, are rendered directly from the source. Older API thumbnail caches
can be checked again for a better source. Portable Game Boy and NES builds
also locate their bundled licensing notices correctly. See [box-art setup](BOXART.md).

Install the standalone Windows x64 `Retro-Recomp.exe`, or use the manual
**Check for updates** button. **Regenerate a game to apply the new audio path
or icons**; installing the converter does not rewrite existing games.
Master System, Game Gear and original Game Boy remain supported profiles;
NES remains experimental. Authenticated artwork APIs have fixture coverage
but still need live validation with user-supplied developer credentials.
The download contains no ROMs, cover downloads, generated game executables,
settings or personal compilation library. Licensing and upstream attributions
are unchanged.

# RetroRecomp v0.16.0 — broader native NES coverage

The experimental NES profile now compiles every NROM (mapper 0) ROM position
that can begin a complete instruction, including targets not found by scripted
exploration. An instruction crossing `$FFFF` still uses the reported fallback;
bank-switching mappers retain their existing discovery-based compilation. The
upstream NESRecomp checkout is unchanged: RetroRecomp stages a private compiler
adapter during conversion.

On the local Super Mario Bros. cartridge, 32,767 of 32,768 potential CPU ROM
entry positions were compiled. Boot and two scripted input runs of 3,600 frames
each used zero interpreter cycles. The generated game matched the **same
engine's internal interpreter** for 120 boot frames and 600 frames of each
input run; an additional 3,600-frame gameplay comparison also matched. One
private first conversion took about 2 minutes 44 seconds, and the packed Mario
game grew from about 1.33 MB to 2.42 MB. These are measurements of one cartridge
and bounded paths, not proof of complete-game or independent hardware fidelity.
Physical input latency was not measured. The NES profile remains experimental.

NES game windows now show only the game name and `Native code` or `Interpreter
fallback`, matching the compact status used by other profiles. Any ROM, RAM or
other CPU fallback keeps the fallback status visible until the game closes.
Gameplay probes also keep exercising inputs beyond the first 300 frames, and
the in-app fallback footer is shorter. Only Super Mario Bros. was regenerated
locally; other games were not rebuilt for this release.

The Windows x64 download is a standalone `Retro-Recomp.exe`. Existing installs
can use the manual **Check for updates** button. The release contains no ROMs,
covers, generated game executables, settings or personal observation library.
The original RetroRecomp code remains MIT; the NES backend retains its PolyForm
Noncommercial terms and attribution. See the [NES profile](NES.md) and
[third-party notices](../THIRD_PARTY_NOTICES.md).

# RetroRecomp v0.15.0 — faster Game Boy conversion and a cleaner workspace

Original Game Boy is now a supported everyday-use profile rather than an alpha
feature. Deep reference CPU validation is enabled by default, including once
for existing GUI preferences; it can still be disabled under Options → Game Boy
or with `--no-gb-deep-validation`. This changes the depth of CPU checks, not
native ROM discovery or the interpreter fallback policy.

The converter's Options window groups shared export, artwork, batch and
overwrite settings under Common, with separate Master System, Game Gear,
Game Boy and NES tabs for console-specific settings. The Credits and Check for
updates buttons have exchanged places. The ROM list uses the space freed by
removing conversion settings from the main window.

Game Boy now compares matching CPU memory blocks efficiently, builds generated
C code with bounded MSVC parallelism, and runs independent deep comparison
scenarios concurrently. On one local Super Mario Land conversion with a
populated entry library, deep validation took 55.8 seconds; a historical deep
run took about 750 seconds, over 10× longer. Those runs had different cache
and implementation conditions, so this is not a controlled across-game
speedup. An empty-library deep run under the new code took 84.5 seconds.
All three final 3600-frame probes reported zero fallback cycles and the
requested CPU comparisons matched the internal reference. These results do
not establish complete-game compatibility, independent hardware fidelity,
gameplay quality or physical latency. Existing games were not regenerated.
NES remains experimental and Game Boy Color-only cartridges remain unsupported.

# RetroRecomp v0.14.5 — edition names and optional regeneration

Batch conversion now distinguishes different ROM revisions with source-derived
region/revision labels, or stable version A/B labels when the filenames do not
identify the difference. Roman numerals and sequel numbers in titles remain
part of the game name. Identical ROM bytes under different filenames are
reported with the existing game's name; they cannot produce a different game.
The new **Overwrite existing executables** option is on by default. Turning it off
skips already exported games while converting missing ones, including in mixed
console batches. No game was regenerated for this converter change.

The local converter library was audited after a large Master System batch:
6,893,562 bytes in 581 files, but only 101 ROM entries were verified for
reuse, all for one Alex Kidd cartridge (2,631 bytes in a compact JSON pack).
The remaining observations are RAM-related and cannot be shared as verified
ROM entries. The library stays local; no personal paths, ROM-derived code
patterns or conversion histories are bundled into this build.

# RetroRecomp v0.14.4 — concurrent batch conversion (included in v0.14.5)

Mixed-console batches can now convert up to eight different games in parallel.
The GUI and `batch` command default to three concurrent games; choose one for
the previous sequential behavior or adjust the setting for available CPU and
memory. Export names are reserved before builds begin, so editions with the
same title keep separate executables and per-ROM reports. Stopping a batch
allows active conversions to finish without starting more games. Shared
dependency setup is serialized. This changes conversion throughput only;
runtime responsiveness and game validation have not been remeasured.

# RetroRecomp v0.14.3 — clearer update errors (included in v0.14.5)

Connection and firewall failures during the manual update check or download
now show a short English or French message instead of the raw network exception.
HTTP service errors use a separate retry-later message. Download checks and
rollback behavior remain unchanged.

# RetroRecomp v0.14.2 — standalone converter download

The Windows converter is now distributed as one `Retro-Recomp.exe`. Its Credits
window displays the bundled project license and complete third-party notices,
with a link to the matching [UPX 5.2.1 source archive](https://github.com/ArthurReboulSalze/RetroRecomp/blob/e522cbde7ca6e7e6eccc0c901389a4178492e6d7/licenses/upx-5.2.1-src.tar.xz).
The download does not place license folders or source archives beside the EXE.

The manual updater now downloads and verifies that single EXE, replaces the
converter after it closes, and restarts it. Versions through v0.14.1 need one
manual replacement to adopt the new update format. Games and user settings are
preserved. No game executable was regenerated for this packaging change.

# RetroRecomp v0.14.1 — visible upstream credits

The converter now has a **Credits** button. It explains that RetroRecomp
combines several independent console-specific recompilers and runtimes in one
application, credits creator and integrator Arthur Reboul Salze, and links the
upstream repositories used for Master System, Game Gear, Game Boy and NES.
The console list scrolls to accommodate future profiles. Licensing notices
remain available from the same window. The main toolbar also shows the
installed RetroRecomp version beside the Credits and update controls.

The v0.14.0 converter can install this version through its manual **Check for
updates** button. The release includes only the converter and legal notices;
it does not regenerate games or bundle ROMs, covers, settings or game data.
The NES profile remains experimental.

# RetroRecomp v0.14.0 — manual in-app updates

The Windows converter now has a **Check for updates** button. It makes no
update request on startup. A click checks this project's GitHub releases,
including previews, and offers a newer Windows x64 package. On acceptance it
downloads and verifies the ZIP, then uses a temporary helper to replace the
converter after it closes and restart the updated version. A failed file
replacement restores the previous converter. Existing games, preferences,
saved states and compilation memory are left in place. Earlier versions need
one manual installation of v0.14.0 to gain this updater.

The release contains the converter and legal notices only. Master System,
Game Gear and original Game Boy remain the playable profiles; NES remains
experimental. This release does not regenerate any game executables.

# RetroRecomp v0.13.0 — multi-console Windows x64 preview

The Windows converter now includes four profiles in one interface. It accepts
mixed ROM folders, detects recognized formats, and exports games into separate
Master System, Game Gear, Game Boy and Nintendo NES folders. Master System,
Game Gear and original Game Boy are playable; the new NES profile remains
experimental.
Only the converter and legal notices are in the release ZIP: no ROMs, covers,
generated games or personal conversion library are included.

Game Gear keeps the native 160 × 144 LCD crop, 12-bit palette and one-player
controls. Original Game Boy uses a separate SM83 recompiler, DMG presentation
and an optional deep CPU validation mode. Game Boy Color-only cartridges are
unsupported. Generated games are compacted before export. Fallback remains
measured and reported; native coverage alone does not prove CPU, hardware or
gameplay fidelity, nor physical input latency.

An experimental Nintendo NES profile now identifies `.nes` and single-ROM
ZIP cartridges, recompiles observed 6502 paths with pinned NESRecomp, and
exports standalone Windows games under `Games/Nintendo NES`. The converter
keeps ROM-specific entry observations, reports exact native/interpreted CPU
cycles and compares short frame hashes with the same engine's interpreter.
The generated game embeds its ROM and legal notices. Its menu uses the shared
RetroRecomp canvas with two players and the main display shortcuts. NES is
NTSC-only for now; F8/F9 states, broad mapper/gameplay validation and
independent hardware comparison remain open. The NES engine is licensed
PolyForm Noncommercial 1.0.0. Review [third-party notices](../THIRD_PARTY_NOTICES.md)
before redistribution.

# RetroRecomp v0.12.0 — source development build, no release ZIP

Original Game Boy `.gb` and single-ROM ZIP inputs now use a separate pinned
SM83 recompiler and Game Boy runtime. Converted games go into
`Export/Games/Game Boy`, support one player and native 160 × 144 output,
and keep settings and saves lazy in `datas`. The report counts fallback
instructions/cycles without inventing a native percentage. The initial local
Tetris, MBC1 Super Mario Land and battery-backed MBC2 Lazlos' Leap boot tests
ran 120 frames with zero fallback cycles in their final exports; a 30-frame
generated/reference CPU comparison matched for each. Super Mario Land first had 76 fallback cycles; reusing its
observed entry trace removed them on this boot path. Unchanged battery RAM
does not create a data folder on launch/quit. This is not independent hardware
or whole-game validation. This historical source development build was not
packaged as a GitHub release; Game Boy is included in v0.13.0.

Game Boy also seeds short ROM branches and learns from boot plus two scripted
play paths. The default CPU validation keeps a short mandatory boot check;
**Deep Game Boy validation (slow)** optionally adds the much longer per-play
comparisons. Native discovery and coverage tests stay the same in both modes.
Reports now identify validation scope and time spent on each conversion stage.

# RetroRecomp v0.11.0 — source development build, no release ZIP

Game Gear cartridge conversion was first introduced as a console
profile. `.gg` and single-ROM ZIP inputs use Game Gear colors, Start, stereo
port, one-player controls and separate game exports. The original 160 × 144 LCD
view is the only presentation mode. No ROM patch or expanded view is used.
Factory Panic passed targeted
120-frame native/reference checks; whole-game and visual verification remain
open. This historical development build was not published as a GitHub release;
Game Gear is included in v0.13.0.

# RetroRecomp v0.10.17 — Master System for Windows x64

Convert your own Master System ROMs into standalone Windows games. This preview
release brings the supported Sega-mapper backend to a practical, playable
state: add a ROM or a folder, convert, and launch each result directly. The
converter performs more CPU work ahead of time to reduce interpreter fallback
while keeping any fallback use visible.

## What's new since v0.10.4

- Scanline-aware Mode 4 video, PAL/NTSC timing choices and corrected interrupt
  boundaries. A chosen timing is remembered for the exact ROM across converter
  engine updates.
- Mouse Light Phaser support for known gun games, with a configurable reticle
  and optional shooting badges on generated cover icons.
- Two fullscreen sizes, gamepad autofire, and persistent F8/F9 quick states
  for newly generated games.
- Cleaner game folders: normal launch creates no data directory or diagnostic
  log. Settings and states are written when needed; converter learning stays
  in the converter's own library.
- Generated games carry their title, console, required controls and
  RetroRecomp version in standard Windows executable metadata.

## Validation and limits

66 ROM-free Python tests pass. Authored native checks cover CPU-step stopping,
video timing, input and game states. Locally tested titles have reached zero
fallback cycles in specified demo and scripted-play scenarios and passed
native/reference CPU and VDP comparisons. These checks do not establish
whole-game coverage or exact hardware fidelity. Physical input latency and
comparative FPS have not been measured.

The ZIP contains the converter and legal notices only: no ROMs, generated
games, separate box art, settings or compilation library. Git and Visual
Studio C++ Build Tools are needed to convert games; neither Python nor a
development toolchain is needed to play a generated game. See the
[README](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/README.md),
[compatibility notes](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/COMPATIBILITY.md)
and [third-party licensing notices](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/THIRD_PARTY_NOTICES.md).
