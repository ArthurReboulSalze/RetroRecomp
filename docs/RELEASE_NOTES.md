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
