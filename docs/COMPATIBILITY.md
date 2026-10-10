# Compatibility and evidence

## Current scope

Release 0.24.0 provides six console profiles. Master System, Game Gear,
original Game Boy and NES are supported within their documented scope.
**Mega Drive and Super Nintendo remain experimental**: their standard cartridge
paths work, but unusual hardware and remaining gameplay, display and audio cases
still need qualification. Experimental does not mean a fixed game list.

The shared snapshot contains verified hints for **51 exact Mega Drive cartridges
and 15 exact Super Nintendo cartridges**. New eligible cartridges receive their
own ROM-derived profiles and undergo native/reference validation before export;
neither this snapshot nor the regression catalogue is an allowlist. Unsupported
hardware is reported separately, and another game's profile is never substituted.

The latest 20-cartridge Mega Drive batch used four final scenarios per cartridge:
7,200 frames each for demo, play and varied input, plus 1,800 early-start frames.
All 80 scenarios finished without interpreted 68000 or Z80 instructions and
matched internal CPU, memory, visible-frame and PCM comparisons. The compressed
exports also passed 1,800-frame early-start checks. Native work-RAM tail
instructions and early input discovery remove repeatedly observed fallback sites.
These are path-specific results, not a claim of interpreter-free full gameplay.

Mega Drive supports standard linear cartridges, region-driven PAL/NTSC,
three/six-button controls, quick states and qualified Menacer input. Extra or
banked cartridge hardware, some CPU exceptions and EEPROM saves remain outside
the implemented scope. Super Nintendo supports ordinary LoROM/HiROM, native
main and sound CPU paths, PAL/NTSC, quick states and qualified Super Scope input.
Enhancement chips, extended mappings, hires/interlace/overscan and independent
cartridge save files remain unfinished. Recognizing valid Japanese header titles
recovers rejected inputs; it does not qualify those cartridges for gameplay.
See [16-bit scope and remaining work](CONSOLES_16BIT.md) and
[gun controls](GUNS_16BIT.md).

Both profiles count main and sound CPU fallback separately and compare CPU,
memory, video and digital sound before learning. Passing the internal reference
checks does not establish independent hardware accuracy, complete gameplay or
physical latency.

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

The subsequent collection campaign qualified 606 exact Game Boy cartridges:
500 with zero fallback on the tested scenarios and 106 retaining reported
fallback. Three cartridges remain refused after execution timeouts. Recent
bank-boundary, native-entry selection and guarded RAM-helper corrections recover
fourteen previously failing cases; thirteen have zero fallback in their new
four-scenario checks. Optimized generated C and byte-identical object reuse reduce
build work without changing CPU validation. See [current Game Boy evidence](GAME_BOY.md)
and [included compilation hints](COMPILATION_LIBRARY.md).

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

ROM-free automated tests accompany each release. Earlier input/presentation work
also passed SDL host checks with two virtual controllers and 4,096 simultaneous
input states. Actual
game CPU/RAM/VDP/PCM states are compared across pause/restart. These checks
do not replace physical controller or latency measurements.

Fallback stays observable. Zero fallback on conversion tests must not be
described as universally interpreter-free.
