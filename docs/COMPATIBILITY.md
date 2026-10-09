# Compatibility and evidence

## Current scope

The current development tree includes experimental Mega Drive integration for Sonic
the Hedgehog, Columns, Golden Axe, Castle of Illusion, Menacer 6-Game Cartridge
and T2 - The Arcade Game, plus Aladdin (Japan), Streets of Rage 2 and
The Revenge of Shinobi, Gunstar Heroes (Japan), Ecco the Dolphin and Desert
Strike. Ten further revisions qualify Beyond Oasis, Comix Zone, Contra - Hard
Corps, Dynamite Headdy, Rocket Knight Adventures, Street Fighter II' Plus,
Thunder Force IV, ToeJam & Earl, Vectorman and Wonder Boy in Monster World.
Their qualification also adds user/supervisor stack switching and STOP/IRQ
handling to the common 68000 adapter. Five additional profiles cover Sonic 2,
Earthworm Jim, Mortal Kombat II, Road Rash II and Shining Force II: 27 Mega Drive
revisions in total, including two explicitly qualified PAL images. The common
compiler now also translates MOVEP and the two six-button games expose their
complete controls. Super Nintendo qualifies 11 exact NTSC
revisions: Super Mario World, Super Scope 6, The Legend of Zelda - A Link to the
Past, Super Metroid, Donkey Kong Country and Super Castlevania IV, plus F-Zero,
Mega Man X, Chrono Trigger, Super Bomberman and Super Mario All-Stars. Its native map
supports LoROM and HiROM with the cartridge's actual storage mirroring.
Pop'n TwinBee adds an exact European PAL LoROM revision, bringing the SNES
catalogue to 12 revisions. Its 312-line raster and independent audio clock
are qualified for the progressive 256 x 224 display.
These tested revisions are a regression catalogue, not a conversion allowlist.
New ordinary Mega Drive and SNES LoROM/HiROM cartridges receive their own
ROM-derived profiles and undergo native/reference validation before export.
Unsupported hardware is reported separately; see [current hardware scope](CONSOLES_16BIT.md).
SNES PAL overscan, interlace and 512-pixel display modes remain unqualified.
Mouse Menacer/Super Scope input and shared gun settings are included;
see [16-bit gun controls and validation](GUNS_16BIT.md).
The instruction adapters introduced in version 0.19.0 extend AOT to Sonic and replace
SMW's earlier C-call bridge with static ROM-PC operations and guarded RAM code.
Both reach zero interpreted main-CPU instructions on demo and scripted-play
tests of 3,600 frames each. Their internal CPU, memory and visible-frame
comparisons match the reference over those complete paths. The earlier
Sonic/SMW reference divergences are resolved on these tested paths.
Mega Drive now recompiles the Z80 sound driver as well as the 68000, with
separate fallback counters and guarded RAM operations. Super Nintendo now also
recompiles the SPC700 sound program with PC-directed opcode guards. Its probes
consume the same audio blocks as the game and compare PCM, SPC/DSP state and
port/timer scheduling against the internal reference before learning.
These tests do not establish independent
hardware accuracy or full-game compatibility; see
[16-bit proof scope and evidence](CONSOLES_16BIT.md).

The supported 8-bit profiles build Windows x64 games from Master System,
Game Gear, original Game Boy and Nintendo NES ROMs. The two
SMS/GG profiles use the Sega mapper and offer
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

Ten more Game Boy cartridge cases now pass production CPU checks, 6,000-frame
varied-input probes and save/close/relaunch state comparisons. Eight report zero
fallback on the longer probes; Donkey Kong Land and Wario Land II retain reported
RAM fallback. Common fixes add guarded native RAM helpers and bounded host-stack
dispatch. This broadens the evidence to MBC3/MBC5 without certifying RTC or complete
gameplay. Large cold C builds can still take much longer than the earlier Mario
benchmark. See [the expanded Game Boy checks](GAME_BOY.md#broader-cartridge-cases--9-october-2026).

The supported Nintendo NES profile uses a separate 6502 cycle backend and
accepts headered `.nes` cartridges. Conversion tests count native and fallback
CPU cycles, then compare short frame hashes with the engine's internal
interpreter. Native bodies cover every physical PRG ROM position, with live
bank dispatch and boundary operands. Authored NTSC/PAL compiler checks pass
931,840 recorded instruction cases across fourteen mapper families, including
332,800 added Color Dreams/VRC6/GxROM/Camerica/mapper-78 cases. Eight earlier cartridges
convert successfully; six have zero fallback on the checked paths, while
Kirby and Zelda still execute some RAM code through the reported interpreter.
Fresh isolated cartridge memory prevents battery saves from contaminating
native/reference comparisons. Ten further cartridges pass another 108,000
matching frame pairs and state-resume checks; eight have zero fallback, while
Wizards & Warriors and Micro Machines retain small RAM fallback. See the
[per-game evidence](NES.md#ten-further-cartridge-cases--9-october-2026).
PAL timing, F8/F9 states
and catalogue-selected mouse Zapper input are included. Dendy and dual guns
remain unsupported. RAM execution and unstable PRG windows can still fall
back. Mapper support and complete gameplay vary by title; these tests do not
establish original-hardware fidelity or full-catalogue compatibility.
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
No game binaries, ROMs, captures or private histories from these runs ship here.
The converter can include verified numeric hints and ROM offsets in its compact
[shared compilation library](COMPILATION_LIBRARY.md); these reconstruct guarded
patterns from the user's own exact ROM and never bypass validation.

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

Release 0.20.0 passes 168 Python tests. Earlier input/presentation work
also passed SDL host checks with two virtual controllers and 4,096 simultaneous
input states. Actual
game CPU/RAM/VDP/PCM states are compared across pause/restart. These checks
do not replace physical controller or latency measurements.

Fallback stays observable. Zero fallback on conversion tests must not be
described as universally interpreter-free.
