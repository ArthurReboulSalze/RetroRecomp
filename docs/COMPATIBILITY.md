# Compatibility and evidence

## Current scope

RetroRecomp 0.13.0 builds Windows x64 games from Master System, Game Gear,
original Game Boy and experimental Nintendo NES ROMs. The two Sega profiles use the Sega mapper and offer
extended native coverage and quick states. Selectable PAL/NTSC timing, two players and
catalogue-selected Light Phaser input apply to Master System. Game Gear uses
one controller, Start input, NTSC timing and the 160 × 144 LCD view.
The native LCD window is always used; games are not patched.
See [Game Gear](GAME_GEAR.md). For the Sega profiles, Codemasters mapper, cartridge saves,
FM sound, hardware Pause/NMI and complete pixel-clock raster effects are not
validated or supported. PAL and NTSC timing support is not a claim of exact
hardware fidelity; see [video evidence](VIDEO.md).

The Game Boy profile uses a separate pinned SM83 compiler and runtime. It
supports `.gb` and single-ROM ZIP input, but rejects Game Boy Color-only
cartridges. Local Tetris, MBC1 Super Mario Land and MBC2
Lazlos' Leap 120-frame boot scenarios reached zero reported fallback cycles
in their final exports; each matched a 30-frame generated/reference CPU comparison. Super
Mario Land first showed 76 fallback cycles, then a ROM-specific entry trace
eliminated them in the repeat boot test. An isolated Lazlos' Leap launch
created no folder despite its battery RAM remaining unchanged. No full-game, cartridge-peripheral,
independent hardware, or physical latency validation follows from these checks.
Later Super Mario Land checks cover boot and two scripted 3600-frame input
paths. Extra short-branch discovery removes a missing bank-3 JP relay, reducing
the two input runs from 44,272 / 60,656 fallback cycles to zero while preserving
their final guest-state dumps. These remain specific tested paths.
See [Game Boy](GAME_BOY.md).

The experimental Nintendo NES profile uses a separate 6502 cycle backend and
accepts headered `.nes` cartridges. Conversion tests count native and fallback
CPU cycles, then compare short frame hashes with the engine's internal
interpreter. Only NTSC timing is supported at present; NES 2.0 PAL/Dendy
cartridges are rejected. Mapper support and complete gameplay vary by title.
See [NES](NES.md).

On the Sega profiles, keyboard/gamepad pause suspends execution and audio in the host. It is not
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
| Native coverage | Execution on a specified path, not a whole-game compatibility score. Game Boy reports fallback cycles but no percentage denominator. |
| CPU fidelity | 51,328 cases from 1,604 independent Z80 vector families passed for the 0.10.0 CPU work. The pinned corpus is not a console capture. |
| Hardware fidelity | Native/reference paths share hardware code; agreement does not independently verify the console. |
| Gameplay | Full playthroughs and physical two-player sessions remain unvalidated. |
| Physical latency | Device, OS, display and game response have not been measured. |

The current version passes 72 Python tests. Earlier input/presentation work
also passed SDL host checks with two virtual controllers and 4,096 simultaneous
input states. Actual
game CPU/RAM/VDP/PCM states are compared across pause/restart. These checks
do not replace physical controller or latency measurements.

Fallback stays observable. Zero fallback on conversion tests must not be
described as universally interpreter-free.
