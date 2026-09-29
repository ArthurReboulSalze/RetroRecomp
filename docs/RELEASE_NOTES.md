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
