# Compatibility and evidence

## Current scope

RetroRecomp 0.10.4 builds Windows x64 games from Master System ROMs using the
Sega mapper. Extended coverage is supported within that scope. Game Gear ROMs
are rejected. Linux, macOS and Android builds are not provided yet. PAL/50 Hz,
Codemasters mapper, cartridge saves, FM sound, hardware Pause/NMI and complete
raster effects are not validated or supported in this release.

Keyboard/gamepad pause suspends execution and audio in the host. It is not
a newly implemented Master System Pause/NMI interrupt.

## Local game regression set

Alex Kidd in Miracle World, Bomber Raid, Bubble Bobble, Buggy Run and Galaxy
Force were converted locally. Two 3,600-frame scenarios per title pass strict
native checks without fallback and agree with the corrected reference CPU
for final CPU/RAM/image state and VDP traces.

These checks cover startup, attract paths and scripted inputs. They do not
establish that all levels, multiplayer modes or RAM variants are covered.
No binaries, ROMs, captures or private observations from these runs ship here.

## Separate validation areas

| Area | What the evidence establishes |
| --- | --- |
| Native coverage | Execution on a specified path, not a whole-game compatibility score. |
| CPU fidelity | 51,328 cases from 1,604 independent Z80 vector families passed for the 0.10.0 CPU work. The pinned corpus is not a console capture. |
| Hardware fidelity | Native/reference paths share hardware code; agreement does not independently verify the console. |
| Gameplay | Full playthroughs and physical two-player sessions remain unvalidated. |
| Physical latency | Device, OS, display and game response have not been measured. |

The 0.10.4 input/presentation work passed 43 Python tests and SDL host checks
with two virtual controllers and 4,096 simultaneous input states. Actual
game CPU/RAM/VDP/PCM states are compared across pause/restart. These checks
do not replace physical controller or latency measurements.

Fallback stays observable. Zero fallback on conversion tests must not be
described as universally interpreter-free.
