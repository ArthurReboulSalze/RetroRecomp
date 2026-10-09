# Nintendo NES profile

**Status: supported within the validated cartridge and peripheral scope.**
The profile is no longer labelled experimental. Compatibility remains specific
to cartridge layouts and tested paths; this is not a whole-catalogue guarantee
or a claim that every game runs without interpreter fallback.

RetroRecomp accepts `.nes`, headered `.bin`/`.rom`, and single-ROM ZIP files.
It generates standalone Windows games in `Games/Nintendo NES`, with no change
to the source ROM. The converter keeps its ROM entry library under
`datas/library/nes`; exported games do not write learning logs.

The backend is pinned to
[`mstan/nesrecomp` revision `1b0c621`](https://github.com/mstan/nesrecomp/tree/1b0c621a927db17afa9723bf456a89ad15809907).
Its [PolyForm Noncommercial 1.0.0 license](../licenses/nesrecomp.md) applies
separately from RetroRecomp's original MIT code. Generated games embed the
component notices as Windows resources. The converter release contains no
NES ROM or generated commercial game executable. The pinned engine checkout
is unchanged: compiler and machine adapters are staged in private build folders.

## Native coverage

The compiler prepares a native entry for **every physical PRG ROM byte**,
including cartridges with bank switching. Identical instruction/operand
combinations share compiled bodies. Dispatch uses the cartridge's current
4 KiB bank mapping. Known operands become constants; operands crossing a
bank boundary or wrapping from `$FFFF` to RAM are read from the live bus.
Observed hot blocks remain available alongside these smaller native bodies.
This is ahead-of-time generated code, with no opcode interpreter inside the
new dispatch path.

The runtime still checks whether a mapped window is ROM and stable. Execution
from RAM, open bus, and unsupported unstable mappings can use the reference
interpreter. In particular, some oversized MMC1/mapper-153 layouts have
PPU-dependent PRG mappings and retain their safety guard. Translating every
ROM position does not mean that all positions are code or that every game
executes without fallback.

Conversion runs boot and two sustained input scenarios, counts native and
interpreted cycles separately, then compares generated execution with the
**same engine's internal interpreter** for 120 boot frames and up to 600
frames of each input path. Reset cycles outside instruction dispatch are
reported separately. Each invocation runs a private copy of the standalone
EXE, so it starts with fresh cartridge memory. Its temporary battery save is
discarded after the test; existing player saves are never loaded or changed.
This also gives the native and reference runs identical starting conditions.
This detects compiler divergence, not complete gameplay
or independently certified hardware fidelity.

`python tools/nes_native_selftest.py` compares all 256 opcodes across eight
CPU slots, four mapper configurations and four flag/alignment variants,
including page crossings, boundary operands, wrapping PC, NMI and IRQ.
The earlier NROM/MMC1/UxROM/CNROM/MMC3 matrix passed **332,800 instruction cases**
across NTSC and PAL. The extended MMC5/AxROM/MMC2/FME-7 matrix adds **266,240
passing cases**, bringing the recorded total to **599,040** across nine mapper
families. The 9 October expansion adds Color Dreams, VRC6, GxROM, Camerica and
mapper 78: **332,800 additional passing cases**, for **931,840 recorded cases**
across fourteen families. The default self-test includes all fourteen families.
Super Mario Bros. 3, Mega Man 2 and Mega Man also reached
zero fallback on three 1,800-frame scripted paths. These are bounded results,
not a full-catalogue compatibility claim.

## Broader cartridge validation

The 8 October 2026 qualification expands generation beyond the earlier Mario
and Mega Man examples. All eight cartridges below build and pass the conversion
checks. Each has three 3,600-frame coverage scenarios: boot and two sustained
input scripts. The table records the highest interpreted-cycle proportion
across those paths, including RAM and cartridge RAM execution.

| Cartridge | Mapper | Timing | Maximum fallback |
| --- | --- | --- | --- |
| Excitebike (Japan, USA) | 0 / NROM | NTSC | 0% |
| DuckTales (USA) | 2 / UxROM | NTSC | 0% |
| The Legend of Zelda (USA) | 1 / MMC1 | NTSC | 2.91% |
| Kirby's Adventure (USA) | 4 / MMC3 | NTSC | < 0.05% |
| Battletoads (USA) | 7 / AxROM | NTSC | 0% |
| Mike Tyson's Punch-Out!! (Japan, USA) | 9 / MMC2 | NTSC | 0% |
| Castlevania III: Dracula's Curse (USA) | 5 / MMC5 | NTSC | 0% |
| Mr. Gimmick (Europe) | 69 / FME-7 | PAL | 0% |

For this qualification, native/reference comparisons were extended to the full
3,600 frames of each scenario: **86,400 matching frame pairs** across the eight
games, including CPU state, memory, bus trace and hardware/framebuffer hashes.
All eight also passed save/close/relaunch checks with 180 resumed frames,
matching continued machine state and PCM, rejection of corrupt states, and
no files created on ordinary one-frame startup or a missing-state load.
The four added mapper families pass 266,240 authored instruction cases; the
Python regression suite passes 173 tests.

These are scripted startup/input paths, not complete playthroughs. The source
ROMs remain unchanged and are not distributed. Kirby's remaining fallback is
in internal RAM; Zelda's is in the cartridge address range below `$8000`.
Guarded compilation of runtime-loaded code remains a separate improvement.

The wider tests exposed a validation isolation bug: a native run could save
battery RAM that the next reference run would then load. CPU registers and
bus traces could match while the initial memory hash differed. Every probe
now starts a separate private EXE copy with fresh battery memory. Existing
player saves are preserved, and genuine comparison differences still block
the export. This changes the converter's tests, not normal in-game persistence.

## Ten further cartridge cases — 9 October 2026

Ten additional NTSC cartridges build successfully. Each passed full internal
native/reference comparisons on three 3,600-frame scenarios: **108,000 matching
frame pairs**. Save/close/relaunch checks also matched state and PCM over 180
resumed frames, including lazy file creation and corrupt-state rejection.

| Cartridge | Mapper | Maximum fallback on those paths |
| --- | --- | --- |
| Contra | 2 | 0% |
| Super C | 4 | 0% |
| Metroid | 1 | 0% |
| Gradius | 3 | 0% |
| Wizards & Warriors | 7 | < 0.49% — RAM execution |
| Crystal Mines | 11 | 0% |
| Holy Diver | 78 | 0% |
| Micro Machines | 71 | < 0.011% — RAM execution |
| Gumshoe | 66 | 0% |
| Esper Dream 2 | 26 | 0% |

These broaden the tested cartridge cases; they do not establish full gameplay
or independently validate the shared hardware runtime. Gumshoe uses the Zapper;
its aiming and visual review still require user testing. Useful ROM entries join
the [shared compilation library](COMPILATION_LIBRARY.md).

## PAL and NTSC timing

NES 2.0 timing metadata takes priority. A clean legacy iNES PAL flag is also
accepted; otherwise regional filename tags provide a hint. Unlabelled and
mixed-region legacy files default to NTSC. Multi-region NES 2.0 files default
to NTSC and can be overridden. Select **PAL** or **NTSC** per ROM when needed;
Dendy remains unsupported. Filename hints are not a verified cartridge database.

PAL uses 312 scanlines, a 16:5 CPU/PPU master-clock ratio, no NTSC odd-frame
dot skip, and regional APU frame-counter, noise and DMC periods. Audio sampling
and host pacing follow the selected clock. The adapter also handles the PAL
OAM write restriction and red/green emphasis-bit order. The framebuffer is
256 × 240 in both modes.

Authored tests check frame durations, rational clock phase through PPU
register accesses and DMA, audio sample counts, APU IRQ/DMC periods and the
OAM write window. Fine 2C07 register races, complete OAM-refresh circuitry and
analogue PAL colour reproduction have not been independently validated.
The palette remains an approximation. Timing references:
[NESdev cycle chart](https://www.nesdev.org/wiki/Cycle_reference_chart),
[PPU variants](https://www.nesdev.org/wiki/PPU_variants),
[APU frame counter](https://www.nesdev.org/wiki/APU_Frame_Counter).

## Controls, quick states and Zapper

The NES host uses the shared RetroRecomp menu canvas. Player 1 uses arrows,
W/X, Enter for Start and right Shift for Select. Player 2 uses keypad
5/2/1/3, 8/9, 7 for Start and 4 for Select. Gamepads use D-pad/left stick,
A/B and Start/Back; left-stick click pauses and player 1 right-stick click
restarts. F2 edits per-player bindings.

H opens help, P pauses, F1 restarts, F3 cycles sharp/bilinear/Scale2x/scanlines,
F4 cycles window/integer fullscreen/fit fullscreen, F6 toggles gamepad
autofire, and F7 changes language. Autofire is sampled once per guest frame;
the game's own input sampling determines its effective rate.

**F8 saves and F9 loads**, including after closing and reopening the game.
One slot lives in `datas/states/<game-slug>-<rom-sha12>.rrstate`, around
322–334 KiB for the checked configurations. It captures CPU, RAM, PPU,
mapper, CHR RAM, APU and mapper audio, including VRC7, and Zapper sensor state.
The format binds the exact ROM, video mode and runtime ABI, with CRC32
corruption checks. It excludes ROM, native addresses and host pointers.
Compatible recompilation can retain a slot; changed machine code/layout may
invalidate it. A failed or incompatible load leaves the running state intact.
Queued host audio is discarded; fallback counters remain cumulative.

Known single-Zapper games automatically use mouse aim and left-click fire on
port 2, with right-click for an off-screen shot. Identification uses NES 2.0
device metadata, a payload-CRC catalogue and exact title aliases. The CRC
facts are attributed to [MesenNesDB](https://github.com/SourMesen/Mesen2/blob/master/UI/Dependencies/MesenNesDB.txt).
The default reticle is a small red cross. **F5**, or the Zapper page of F2,
selects cross/dot, size and red/white/green. Intentional game flashes are kept.
The sensor uses pixels as the PPU emits them, with bounded light persistence,
following the [Zapper interface](https://www.nesdev.org/wiki/Zapper).
This is an approximate optical response; dual guns and other special
controllers are not implemented.

Opening/closing a game or attempting F9 with no state creates no directory.
Only edited settings, F8, or changed cartridge battery RAM write to `datas`.
Battery saves remain separate in `datas/games`.

## Scrolling at the picture edges

The NES output preserves the full 256 × 240 picture. Super Mario Bros. 3 can
briefly expose tile/attribute updates at the right edge while scrolling,
even when the stationary picture looks correct. This is a documented effect
of the original game's nametable layout, not by itself evidence of a native
CPU translation fault. See [NESdev's attribute-table explanation](https://www.nesdev.org/wiki/PPU_attribute_tables).
No automatic crop or game-specific masking is applied.

A local 1,200-frame scripted comparison of the packed Mario 3 export against
the separate TriCNES-derived oracle matched CPU state and memory/framebuffer
hashes at every frame. The final framebuffer also matched pixel for pixel,
including the rightmost 16 columns. This is bounded software-reference
evidence; it does not certify every gameplay path or host display timing.

## Validation boundary

`python tools/nes_machine_selftest.py` exercises authored NTSC/PAL fixtures:
clock/APU behavior, beam-driven Zapper detection, snapshot round trips,
mapper audio and corrupted-state rejection without mutation.
`python tools/nes_state_selftest.py <game.exe>` saves, closes, relaunches and
compares continued CPU/memory/video/hardware hashes and PCM, while also
checking lazy file creation. It does not open a game window.

Native coverage, CPU differential, hardware fidelity, gameplay and physical
latency remain separate evidence areas. Broader mapper/peripheral tests and
real gameplay remain necessary before treating the whole NES catalogue as
validated. Existing executables gain these features only when regenerated.
