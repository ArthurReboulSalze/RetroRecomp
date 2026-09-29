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
