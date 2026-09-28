# Roadmap

Only Master System with the Sega mapper and Windows x64 output is implemented
in 0.10.17. These are goals/research directions, not current support or delivery
commitments.

## Game systems

| Direction | Work needed |
| --- | --- |
| Broader Master System coverage | More gameplay paths, RAM variants, hardware cases and independent checks. |
| Game Gear and other retro consoles | Machine profiles, runtimes, input/presentation and per-system validation. |
| Neo Geo AES/MVS | Main 68000 and sound Z80 execution, graphics, audio, BIOS, timing and cartridges. |
| Amiga A1200/AGA | 68020-class execution, chipset/DMA/Copper behavior, modified code and game environment. |

## Host platforms

| Platform | Goal |
| --- | --- |
| Linux | Native desktop converter/game builds and platform toolchain/packaging. |
| macOS | Native builds for selected Mac architectures and platform integration. |
| Android | Mobile native output, ARM toolchain, touch/controller input and rendering/audio lifecycle. |

SDL2 helps, but its platform support alone does not port RetroRecomp.
Windows-specific build discovery, paths, icon resources and menu font rendering
need alternatives. No Linux, Mac or Android build is in the current ZIP.

## Improvement loop

We want to explore more paths using a local decision or vision model:
observation, input choice, deterministic replay, guarded compilation and
comparison before regeneration. A stopping threshold could combine native
coverage, regression stability and exploration budget. More explored paths
do not prove complete gameplay or hardware fidelity.

The current version reuses verified observations and checks candidates. The
AI player/autonomous exploration loop is not implemented. No model weights,
API credentials or online-model integration are distributed.
