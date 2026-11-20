# Performance: CPU time per frame

This page gives, for each machine, the **CPU time per frame**: how long the PC's processor takes to compute one frame
of a converted game, on the player's path. It is the host's cost of running the game. It is **not latency** and not
response time: it says nothing about how long a button takes to reach the picture, which is not measured. It is also
none of the other measures: native code, CPU fidelity, hardware fidelity and gameplay validation are on each machine's
page and in [QUALIFICATION.md](QUALIFICATION.md).

The README's machine table shows these figures in its « CPU per frame » column, written by `tools/qualification_gauges.py`
from the table below: the newest figure on Windows (« Win ») and, where it was measured, on Linux, each with its change
against the previous version measured for that machine on that system, in parentheses (a minus sign means faster). A
machine without a row reads « not measured ». The older release-to-release comparisons are in
[RUNTIME_PERFORMANCE.md](RUNTIME_PERFORMANCE.md).

## How to read a figure

A game shown at 60 frames a second has **16.7 ms** for each frame (20 ms at 50 Hz). A figure of 2 ms means the processor
needs about an eighth of that frame to compute it; the rest of the frame it waits. The figures come from **one PC**:
another processor, another operating system or another load gives other numbers. A small figure is not a faster
reaction to a button, and a large one under 16.7 ms does not make the game slower.

## The method

- **The PC.** A Windows 11 desktop with an AMD Ryzen 9 3900X (12 cores, 24 threads, 3.8 GHz) and 64 GB of RAM, kept quiet
  during the timed pass (no conversion or test running), the game's process pinned to one core at high priority.
- **The path.** The game is the delivered executable, started with no argument, as a player starts it, alone (no
  multiplayer session), in a hidden-window test run of 240 frames: SDL's dummy video and sound drivers, so no window, no
  sound device and the software renderer. There is no scripted input: the boot and the attract mode.
- **The figure.** The shell's own timing report gives the work of each frame: the machine's frame and its delivery, the
  sound queue and the drawing. Frame pacing and the wait for room in the sound queue are left out, since they are waiting,
  not work. The figure also leaves out putting the picture on screen (the present): with a GPU renderer, which a player's
  window uses (Direct3D on Windows, OpenGL on Linux), that costs little; on a PC that falls back to SDL's software renderer
  it can add about 0.4-0.6 ms. Each run gives the work per frame; the table gives the median of three timed runs, after one
  warm-up run that is dropped.
- **Linux** figures are measured in **WSL2** on the same PC, with the same method. WSL2 is a light virtual machine: its CPU
  figures are close to a native Linux's on that processor, not identical, and they are not a measure of another Linux PC.
- **The spread** is (max − min) / median of the runs, in percent: how much the runs disagree.
- **The change** in the README is (this median − the previous version's median) / the previous version's median, rounded to
  the percent, for the same machine, game and system. A change within the spread of either version is noise.
- **The version** is the converter's that built the game, with its commit when it was not a published release; the date
  is the day of the timed pass.

## The figures

| Machine id | Machine | System | Game | Median ms per frame | Spread | Runs x frames | Version | Date |
|---|---|---|---|---|---|---|---|---|
| sms | Master System | Windows | Sonic The Hedgehog | 0.4363 | 2.1 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| sms | Master System | Windows | Sonic The Hedgehog | 0.4432 | 7.7 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| gg | Game Gear | Windows | Sonic The Hedgehog | 0.4934 | 3.7 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| gg | Game Gear | Windows | Sonic The Hedgehog | 0.5004 | 0.7 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| gb | Game Boy | Windows | Super Mario Land | 0.2569 | 6.1 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| gb | Game Boy | Windows | Super Mario Land | 0.2569 | 7.5 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| nes | NES | Windows | Metroid | 2.5531 | 4.5 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| nes | NES | Windows | Metroid | 2.5119 | 2.2 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| md | Mega Drive | Windows | Sonic The Hedgehog 2 | 1.7129 | 1.9 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| md | Mega Drive | Windows | Sonic The Hedgehog 2 | 1.7357 | 0.2 % | 3 x 240 | 1.9.0 (main d8dba7b2) | 2026-11-20 |
| pce | PC Engine | Windows | Blazing Lazers | 5.2165 | 2.0 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| pce | PC Engine | Windows | Blazing Lazers | 5.2231 | 0.6 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| snes | Super Nintendo | Windows | Mega Man X2 | 4.2649 | 2.8 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| snes | Super Nintendo | Windows | Mega Man X2 | 4.2113 | 0.5 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| ng | Neo Geo | Windows | Puzzle De Pon! | 3.0899 | 0.6 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| ng | Neo Geo | Windows | Puzzle De Pon! | 3.1988 | 0.9 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| cps1 | CPS-1 | Windows | Final Fight | 1.0628 | 1.0 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| cps1 | CPS-1 | Windows | Final Fight | 1.0478 | 1.6 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| cps2 | CPS-2 | Windows | 19XX | 1.1482 | 1.6 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| cps2 | CPS-2 | Windows | 19XX | 1.1901 | 0.5 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| x68 | Sharp X68000 | Windows | R-Type | 1.0624 | 1.4 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| x68 | Sharp X68000 | Windows | R-Type | 1.0679 | 1.8 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| amiga | Amiga 500 | Windows | Lotus 2 | 1.1190 | 2.5 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| amiga | Amiga 500 | Windows | Lotus 2 | 1.1189 | 4.0 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| a1200 | Amiga 1200 | Windows | Pinball Illusions | 2.1407 | 1.1 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| a1200 | Amiga 1200 | Windows | Pinball Illusions | 2.1114 | 1.0 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| atarist | Atari ST | Windows | Bomb Jack | 1.5818 | 4.9 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| atarist | Atari ST | Windows | Bomb Jack | 1.4695 | 5.6 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| msx | MSX | Windows | Nemesis | 0.4063 | 2.1 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| msx | MSX | Windows | Nemesis | 0.4037 | 3.0 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| msx2 | MSX2 | Windows | Space Manbow | 0.6924 | 2.3 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| msx2 | MSX2 | Windows | Space Manbow | 0.6790 | 0.6 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| msx2plus | MSX2+ | Windows | Manbow 2 | 0.9668 | 1.0 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| msx2plus | MSX2+ | Windows | Manbow 2 | 0.9600 | 1.7 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| gba | Game Boy Advance | Windows | Advance Wars | 1.4141 | 5.2 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| gba | Game Boy Advance | Windows | Advance Wars | 1.4197 | 0.5 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| n64 | Nintendo 64 | Windows | Super Mario 64 | 4.6941 | 17.3 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| n64 | Nintendo 64 | Windows | Super Mario 64 | 4.6870 | 8.0 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |
| psx | PlayStation | Windows | Ape Escape | 3.6681 | 1.3 % | 3 x 240 | 1.8.0 | 2026-11-20 |
| psx | PlayStation | Windows | Ape Escape | 3.8317 | 2.5 % | 3 x 240 | 1.9.0 (main 4aafb3fd) | 2026-11-20 |

1.8.0 is the published release (tag `v1.8.0`), 1.9.0 the release line before its tag (main `d8dba7b2` for the first five
machines, main `4aafb3fd` for the others); both sides of a machine were converted from source with the same tools and timed
in one pass, interleaved, on an otherwise idle PC. Each row is one game in its attract scene (no input): a busy in-game scene
costs more. The MSX2+ row is a cartridge game (Manbow 2). No Linux figure yet.

## Adding or updating a row

One row per machine, system and version, keyed by the machine's profile id (`retrorecomp/systems`), in the format above:
the system `Windows` or `Linux` (WSL2), the median in ms with four decimals, the spread in percent, the runs and frames, the
converter version as `X.Y.Z` (followed by `(main <commit>)` before a release), the date in ISO form. Keep the older rows:
the README compares the newest version of each machine and system with the one before it. Then run
`python -B tools/qualification_gauges.py --write` so the README's column follows, and `--check` passes. A timed pass
needs a quiet PC and the owner's go first.
