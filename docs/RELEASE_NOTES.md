# v0.10.4 — first public release candidate

Windows x64 converter for Master System ROMs with the Sega mapper.

- Extended ROM-bank coverage enabled by default; guarded learned RAM variants
  and counted fallback interpreter.
- English/French batch interface, optional cover icons and shared `datas`.
- Two players, Start/Menu and J1 Select/Reset mapping; no J2 reset.
- P/Enter pause, integer fullscreen, four display filters and automatic crop
  of the left hardware mask.
- Compact banner layout, more log space and slogan at bottom right.
- Same-name regeneration with deferred replacement of a running game.

## Contents

The ZIP contains the converter, MIT license and third-party notices. No games,
ROMs, box art, captures, preferences, learned game data, downloaded toolchains
or build reports. No TXT user guides. Git and Visual Studio C++/CMake are
required to convert; Python is unnecessary for the packaged converter.
Games produced locally are standalone.

## Validation and limits

43 application tests, five publication privacy checks and native SDL controls
checks pass. Five local games pass
two 3,600-frame strict scenarios each without fallback on those paths, agreeing
with the corrected reference CPU. Independent Z80 evidence is from 0.10.0;
it was not rerun for UI/input changes. Full gameplay/hardware fidelity and
physical latency remain unverified or unmeasured.

Linux, macOS, Android and more systems are roadmap targets, not included builds.
Review [compatibility](COMPATIBILITY.md) and
[third-party licensing status](../THIRD_PARTY_NOTICES.md).
