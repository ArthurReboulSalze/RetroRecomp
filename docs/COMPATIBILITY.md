# Compatibility and evidence

## Current scope

RetroRecomp 0.10.17 builds Windows x64 games from Master System ROMs using the
Sega mapper. Extended native coverage, selectable PAL/NTSC console timing,
quick states and catalogue-selected Light Phaser input are available within
that scope. Game Gear ROMs are rejected. Codemasters mapper, cartridge saves,
FM sound, hardware Pause/NMI and complete pixel-clock raster effects are not
validated or supported. PAL and NTSC timing support is not a claim of exact
hardware fidelity; see [video evidence](VIDEO.md).

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

Since 0.10.9, end-of-frame video snapshots have been replaced with a
scanline renderer for 192-line Mode 4 video. It preserves raster palette and
scroll changes, limits sprites to eight per line, resolves sprite priority,
and models sprite wrap/zoom and collision/overflow status at scanline precision.
Newly converted games inherit these changes. Older executables contain their
original runtime until explicitly regenerated.

Since 0.10.10, frame limits and host stops wait until the current CPU
step completes. All 72 authored I/O boundary cases pass on native, reference
and fallback paths. This fixes partial-register final-state failures without
excluding registers or weakening the validation gate.

Authored chip fixtures exercise these rules independently of the native vs
reference CPU comparison. The conversion check now includes a pixel hash
for every completed frame. CPU paths still share the hardware model; matching
hashes do not replace a hardware capture or gameplay validation. Version
0.10.15 added PAL scanline/clock/V-counter timing and authored boundary checks,
but these do not independently certify PAL hardware fidelity. Pixel-clock CRAM artifacts,
VRAM bus contention and other video modes remain outside the verified scope.
See [video evidence](VIDEO.md) and [console profiles](SYSTEM_PROFILES.md).

| Area | What the evidence establishes |
| --- | --- |
| Native coverage | Execution on a specified path, not a whole-game compatibility score. |
| CPU fidelity | 51,328 cases from 1,604 independent Z80 vector families passed for the 0.10.0 CPU work. The pinned corpus is not a console capture. |
| Hardware fidelity | Native/reference paths share hardware code; agreement does not independently verify the console. |
| Gameplay | Full playthroughs and physical two-player sessions remain unvalidated. |
| Physical latency | Device, OS, display and game response have not been measured. |

The current version passes 66 Python tests. Earlier input/presentation work
also passed SDL host checks with two virtual controllers and 4,096 simultaneous
input states. Actual
game CPU/RAM/VDP/PCM states are compared across pause/restart. These checks
do not replace physical controller or latency measurements.

Fallback stays observable. Zero fallback on conversion tests must not be
described as universally interpreter-free.
