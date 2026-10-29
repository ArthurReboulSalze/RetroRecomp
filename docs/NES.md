# Nintendo NES

**Status: supported within the validated cartridge and peripheral scope.**
The profile is no longer labelled experimental. Compatibility remains specific
to cartridge layouts and tested paths; this is not a whole-catalogue guarantee
or a claim that every game runs without interpreter fallback.

The dated qualification journal (October 2026 campaigns, matrices, per-cartridge
numbers) is in [NES_LOG.md](NES_LOG.md). The processor is described in
[CPU_6502.md](CPU_6502.md).

## Contents

1. [At a glance](#1-at-a-glance)
2. [Structure of the machine](#2-structure-of-the-machine)
3. [Engine and upstream](#3-engine-and-upstream)
4. [In the project](#4-in-the-project)
5. [Controls and options](#5-controls-and-options)
6. [States and saves](#6-states-and-saves)
7. [Qualification](#7-qualification)
8. [Known limits](#8-known-limits)
9. [History](#9-history)

## 1. At a glance

| | |
|---|---|
| Status | Supported within the validated cartridge and peripheral scope (see above) |
| Accepted files | `.nes`, headered `.bin`/`.rom`, and single-ROM ZIP files |
| Output | A standalone Windows game in `Games/Nintendo NES`, with no change to the source ROM; a native Linux development port shares the same compiler and cartridge observations ([building](BUILDING.md)) |
| Firmware | None: the machine is a cartridge only |
| Library | The converter keeps its ROM entry library under `datas/library/nes` |
| Regions | NTSC and PAL, chosen per ROM; Dendy is not supported |
| Peripherals | Two standard controllers; one Zapper on port 2 |
| Fallback recording | Optional: hints are collected in memory and written only when the game closes; F12 toggles recording ([runtime feedback](RUNTIME_FEEDBACK.md)) |

The converter release contains no NES ROM or generated commercial game
executable. Generated games embed the component notices as Windows resources or
embedded Linux data.

The five measures stay separate on this page and in every report: native
code, CPU fidelity, hardware fidelity, gameplay validation and physical latency.
Interpreter fallback is always counted and shown. No claim of exact hardware
behaviour or zero latency is made.

## 2. Structure of the machine

| Part | Hardware modelled | How Retro-Recomp handles it |
|---|---|---|
| Main CPU | 6502 core of the 2A03 ([CPU_6502.md](CPU_6502.md)) | Ahead-of-time native bodies for every physical PRG ROM byte; guarded native bodies for observed RAM entries; the engine's own interpreter as counted fallback and as the reference |
| Video | PPU, 256 × 240 picture, NTSC (2C02) and PAL (2C07) timing | Native clocked C runtime from the staged engine; every pixel, latch transition and mapper event is clocked; an optimized path is checked against the original one |
| Sound | APU, 48 kHz mono PCM in the host; mapper audio including VRC6 and VRC7 | Native runtime; generated and interpreted execution must produce byte-identical PCM in conversion checks |
| Cartridge | PRG ROM with bank switching, CHR ROM/RAM, work RAM, battery RAM, mapper IRQs | Mapper state is part of the machine; lower ROM aliases and protected cartridge RAM are handled by live bus reads; battery RAM is saved beside the game |
| Peripherals | Two controllers; Zapper (light gun) | Host kit for the pads; the Zapper is an optical approximation fed by the pixels the PPU emits |
| Host | Window, audio, menus, quick states | The NES adapter of the shared [host kit](HOST_KIT.md) |

Mappers named in this page with recorded evidence: 0 (NROM), 1 (MMC1/MMC1A),
2 (UxROM), 3 (CNROM), 4 (MMC3), 5 (MMC5), 7 (AxROM), 9 (MMC2), 11 (Color
Dreams), 16, 21/22/23/25 (VRC2/VRC4), 26 (VRC6), 40, 66 (GxROM), 69 (FME-7),
71 (Camerica), 78, 80/207 (Taito X1-005), 82/552 (Taito X1-017), 153 and 155.
The pinned engine models more boards than have been qualified here; only the
cases listed in [Qualification](#7-qualification) and in [NES_LOG.md](NES_LOG.md) carry evidence.

### Native coverage and fallback

The compiler prepares a native entry for **every physical PRG ROM byte**,
including cartridges with bank switching. Identical instruction/operand
combinations share compiled bodies. Dispatch uses the cartridge's current
4 KiB bank mapping. Known operands become constants; operands crossing a
bank boundary or wrapping from `$FFFF` to RAM are read from the live bus.
Observed hot blocks remain available alongside these smaller native bodies.
This is ahead-of-time generated code, with no opcode interpreter inside the
new dispatch path.

The runtime checks the mapped memory before selecting compiled code. Observed
internal/cartridge RAM entries can use guarded AOT bodies with live operands.
PPU-dependent MMC1/MMC1A and mapper-153 PRG windows use a separate fetch-time
path: the native body is selected from the bank actually read after any DMA
stall. Open bus, unobserved RAM opcodes and unsupported memory windows retain
reported interpreter fallback. Translating every ROM position does not mean
that all positions are code or that every game executes without fallback.

### Guarded RAM and lower ROM aliases

- **Guarded RAM.** Native instruction bodies exist for observed RAM
  entry/opcode pairs, tied to the exact cartridge. The current opcode is
  checked before execution; operands retain their individual live bus reads, so
  changing an operand needs no new variant. Changing an opcode or jumping to an
  unobserved entry retains visible fallback. No runtime compiler, ROM patch,
  opcode interpreter or pixel correction is added to the guarded path. Guards
  use side-effect-free memory probes and never read PPU/APU registers or a
  cartridge register to inspect an entry. Only the converter's explicit probe
  can write its bounded entry journal; ordinary exported-game launches create no
  learning log.
- **Eligible windows.** Internal RAM and modelled plain cartridge RAM, including
  MMC5 mapped RAM, the enabled FME-7 work-RAM window, mapper 153's ordinary RAM
  mode, and accessible VRC2/VRC4 (21, 22, 23, 25), Taito X1-005 (80, 207) and
  X1-017 (82, 552) boards. Excluded: FME-7 ROM/open-bus selections and disabled
  RAM, mapper 153's SDA contention, VRC2 protection latches without RAM, disabled
  VRC4 RAM, the 2 KiB VRC4 hole at `$7000+`, Taito lock values, register windows
  and unmapped holes.
- **PPU-dependent banks.** For PPU-dependent MMC1/MMC1A and mapper 153, the
  opcode's physical bank is latched at the real bus access, after DMA stalls.
  Every operand remains live, and dispatch rechecks the mapping after each
  instruction. If that fetch has no matching compiled body, the interpreter
  continues the already-fetched instruction exactly once; those cycles remain
  in the fallback counters.
- **Lower ROM aliases.** Native dispatch includes cartridge ROM mapped at
  `$6000-$7FFF` by mappers 40 and 69. The mapper's current selection determines
  the physical PRG byte; opcode and operands use individual live bus reads,
  including across `$7000` and `$8000`, and FME-7 ROM/RAM selection is checked
  anew at each fetch. These aliases do not enter the upstream seed format, whose
  address slots start at `$8000`; dense native coverage makes those ambiguous
  seeds unnecessary.

An observed entry/opcode guard is always required; operands are never learned or
folded. This extends recompilation coverage rather than adding new mapper
hardware (the X1-017 IRQ circuitry is still unmodelled). The shared hints are
bound to each exact ROM and reference an opcode byte in the original PRG ROM:
they contain neither an executable RAM dump nor a generated game image. See the
[shared compilation library](COMPILATION_LIBRARY.md). The dated campaigns that
introduced these mechanisms are in [NES_LOG.md](NES_LOG.md).

### PAL and NTSC timing

NES 2.0 timing metadata takes priority. A clean legacy iNES PAL flag is also
accepted; otherwise regional filename tags provide a hint. Unlabelled and
mixed-region legacy files default to NTSC. Multi-region NES 2.0 files default
to NTSC and can be overridden. Select **PAL** or **NTSC** per ROM when needed;
Dendy remains unsupported. Filename hints are not a verified cartridge database.

PAL uses 312 scanlines, a 16:5 CPU/PPU master-clock ratio (NTSC 12:4), no NTSC
odd-frame dot skip, and regional APU frame-counter, noise and DMC periods. Audio
sampling and host pacing follow the selected clock. The adapter also handles the
PAL OAM write restriction and red/green emphasis-bit order. The framebuffer is
256 × 240 in both modes.

Authored tests check frame durations, rational clock phase through PPU
register accesses and DMA, audio sample counts, APU IRQ/DMC periods and the
OAM write window. Fine 2C07 register races, complete OAM-refresh circuitry and
analogue PAL colour reproduction have not been independently validated.
The palette remains an approximation. Timing references:
[NESdev cycle chart](https://www.nesdev.org/wiki/Cycle_reference_chart),
[PPU variants](https://www.nesdev.org/wiki/PPU_variants),
[APU frame counter](https://www.nesdev.org/wiki/APU_Frame_Counter).

### Linux runtime performance

The settled PPU path caches only conditions invalidated by register accesses.
Adjacent dot/half-dot calls are paired only when no CPU, APU or NMI event falls
between them. Every pixel, latch transition and mapper event remains clocked;
there is no frame skipping or simplified PPU mode.

GNU builds profile the hardware through a private native runner, then
link the native game with profile-guided optimization and interprocedural
optimization when available. Training covers 240 boot frames and 600 input
frames with PCM production. The instrumented runner is never exported;
temporary compiler counters and audio are removed. These profiles are compiler
data, not shared cartridge knowledge. Normal fresh native/reference checks
still run on the final game.

`tools/nes_ppu_selftest.py` compares the optimized PPU with the original staged
path over 44,800 checkpoints: eight mapper configurations, PAL/NTSC and all four
CPU/PPU alignments. Hidden PPU fields, framebuffer, bus/memory state and PCM
are checked, alongside the separate clock/APU/Zapper/quick-state fixtures.
This internal comparison is not an independent physical-hardware proof. (The
recorded figure is kept as written; the tool now runs three configurations, see
[Self-tests](#self-tests).)

### Discovery levels and incremental builds

**Options → Nintendo NES → Discovery scan** offers four levels; *Standard* is
the default. *Extended* (the former advanced scan, `--nes-advanced-scan`) adds three
deterministic paths to boot/right/left: released menu/dialogue confirmations,
Select and separate player-2 input, and varied movement/jump/button releases.
Each path respects the configured frame budget; Start is pulsed once per
controller to avoid repeatedly pausing a game. These bounded scripts do not
guarantee every menu, level or a complete playthrough. *Thorough* adds two
reproducible pseudo-random routes of 18,000 frames seeded from the exact ROM
(`retrorecomp/random_routes.py`), compared with the reference like the authored
replays; *Quick* keeps boot and the right-hand play run for a single pass. The
report records the level and each scenario's frame budget under `advanced_scan`.

Every advanced path compares all its frames with the internal interpreter and
exact PCM **before the next learning pass**. The fresh final-pass evidence is
bound to the current EXE hash; it is not reused from another build. Failed
comparisons still block export and shared promotion. The recorded results of
this level are in [NES_LOG.md](NES_LOG.md#discovery-levels-evidence-and-cross-checks).

The converter materialises selected generated C files at stable paths. An
exact ROM/compiler/ROM-entry receipt and source hashes validate raw output;
RAM observations adapt only the selected umbrella. Byte-identical sources
retain timestamps, and staged native headers keep stable include paths across
separate one-file converter launches. Changed inputs and corrupted caches
are regenerated. No previous qualification report is used as a shortcut. The
measurement of this mechanism is in
[NES_LOG.md](NES_LOG.md#incremental-build-measurement).

## 3. Engine and upstream

The backend is pinned to
[`mstan/nesrecomp` revision `1b0c621`](https://github.com/mstan/nesrecomp/tree/1b0c621a927db17afa9723bf456a89ad15809907)
(`nes.ENGINE_REV`). Its [PolyForm Noncommercial 1.0.0 license](../licenses/nesrecomp.md) applies
separately from RetroRecomp's original MIT code. The pinned engine checkout
is unchanged: compiler and machine adapters are staged in private build folders,
where the converter transforms the engine's sources (PAL clocking, the deferred
PPU edges, the Zapper, quick states, extra sprites, folding of the cartridge's
mapper identity, RAM guards and interpreter hooks). Each transformation fails the
conversion if the engine source no longer matches, so a bump of the pin is a
deliberate act. The pins, the review record and the fixes carried as our own
patches are tracked in [UPSTREAMS.md](UPSTREAMS.md); no CPU fix to the NES
engine is carried at present. Cartridge observations from other players join the
[shared compilation library](COMPILATION_LIBRARY.md).

## 4. In the project

| Kind | Paths |
|---|---|
| Profile | `retrorecomp/systems/nes.py` |
| Converter | `retrorecomp/nes.py` (conversion, ROM reading, probes, report), `nes_codegen.py` (private compiler), `nes_machine.py` (staged machine adapter and state ABI), `nes_runtime.py` (private host adapter), `nes_build.py` (exact-input generation and stable build paths), `nes_ram.py` (RAM entry/opcode guards), `nes_optimization.py` (Linux profile-guided build), `nes_catalog.py` (Zapper catalogue) |
| Native | `native/nes_state.c`, `nes_machine_state.inc`, `nes_mapper_state.inc` (quick states), `nes_ppu_fast.inc`, `nes_ppu_lazy.inc`, `nes_sprite_shift.h`, `nes_sprite_extra.inc` (PPU), `nes_dense_codegen.inc`, `nes_live_codegen.inc`, `nes_ram.inc` (dispatch and guards), `native/retro_nes.h` |
| Checks compiled into tests | `native/nes_*_checks.c` (audio, dense, guarded, machine, PPU, lower-ROM windows) |
| Host-kit adapter | `native/hostkit/adapters/rrhk_nes.c` |
| Tools | `tools/nes_native_selftest.py`, `nes_guarded_selftest.py`, `nes_windows_selftest.py`, `nes_machine_selftest.py`, `nes_ppu_selftest.py`, `nes_audio_selftest.py`, `nes_state_selftest.py`, `nes_state_cross.py` |
| Tests | `tests/test_nes.py`, `test_nes_build.py`, `test_nes_ram.py` |

Roles and owners of the native files are declared in
`retrorecomp/stamp_inputs.py`; editing a NES game file moves the NES game stamp
and may affect existing exports ([UPGRADES.md](UPGRADES.md)).

## 5. Controls and options

The NES host is the NES adapter of the shared host kit ([HOST_KIT.md](HOST_KIT.md))
and uses the shared RetroRecomp menu canvas. Player 1 uses arrows,
W/X, Enter for Start and Shift for Select (left by default, either Shift
works since 1.5.0). Player 2 uses keypad
5/2/1/3, 8/9, 7 for Start and 4 for Select. Gamepads use D-pad/left stick,
A/B and Start/Back. F2 edits per-player bindings; the pad defaults for quit
(L3+R3 held) and restart (Start+Select) are the host kit's, described in
[CONTROLS.md](CONTROLS.md).

F1 opens help, Shift+F1 restarts, Enter (Start) pauses the game itself, F3 cycles sharp/Scale2x/scanlines/xBR,
F4 cycles window/integer fullscreen/fit fullscreen, F6 toggles gamepad
autofire, and F7 changes language. Autofire is sampled once per guest frame;
the game's own input sampling determines its effective rate.

On every NES game, **F5** toggles the optional extra sprites described in
[controls](CONTROLS.md); it no longer opens the Zapper page. The
choice is saved in `[NES.Video] reduce_sprite_flicker`; off by default.

### Zapper

Known single-Zapper games automatically use mouse aim and left-click fire on
port 2, with right-click for an off-screen shot. Identification uses NES 2.0
device metadata, a payload-CRC catalogue and exact title aliases. The CRC
facts are attributed to [MesenNesDB](https://github.com/SourMesen/Mesen2/blob/master/UI/Dependencies/MesenNesDB.txt).
The default reticle is a small red cross. The Zapper page of F2, after the four
control pages, selects cross/dot, size and red/white/green. Intentional game flashes are kept.
The sensor uses pixels as the PPU emits them, with bounded light persistence,
following the [Zapper interface](https://www.nesdev.org/wiki/Zapper).
This is an approximate optical response; dual guns and other special
controllers are not implemented.

### Picture edges

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

## 6. States and saves

**F8 saves and F9 loads**, including after closing and reopening the game.
One slot lives in `datas/states/<game-slug>-<rom-sha12>.rrstate`, around
266–270 KiB for the checked configurations (the header says `RRNESST2`). It captures CPU, RAM, PPU,
mapper, CHR RAM, APU and mapper audio, including VRC7, and Zapper sensor state.
The format binds the exact ROM, video mode and runtime ABI, with CRC32
corruption checks. It excludes ROM, native addresses and host pointers.
Every structure is written field by field, one after the other, in little-endian
order and with fixed-size types, so no compiler padding reaches the file and every
byte of it is defined by construction. `retrorecomp/nes_state_layout.py` writes
these serialisers from the struct definitions of the staged engine (CPU, bus,
cartridge, PPU, APU, audio and the VRC7 chip): a pointer, a bit-field or a type
whose size depends on the compiler stops the staging instead of being copied,
and the few members left out (host pointers, the queued host audio) are listed
there with the reason. The ABI key is a hash of the staged engine, the state
sources and these serialisers; it does not depend on the folder the game is
built in, so two builds of the same game in different folders have the same key.
Compatible recompilation can retain a slot; changed machine code/layout may
invalidate it. A failed or incompatible load leaves the running state intact.
Queued host audio is discarded; fallback counters remain cumulative.

States written before 1.6.5 (`RRNESST1`, a raw copy of the structures) are
refused cleanly, not misread: the layout and the key both changed.

Invalid magic, ABI, ROM identity, region, payload and truncated states are
rejected without rewriting the valid or rejected file. Opening/closing a game or
attempting F9 with no state creates no directory. Only edited settings, F8, or
changed cartridge battery RAM write to `datas`. Battery saves remain separate
in `datas/games`. The general rules and the compatibility between releases are in
[GAME_STATES.md](GAME_STATES.md) (the NES line is described in its first sections).

Existing executables gain these features only when regenerated.

## 7. Qualification

The per-gate status of the NES is in [QUALIFICATION.md](QUALIFICATION.md). Native
coverage, CPU differential, hardware fidelity, gameplay and physical latency
remain separate evidence areas. Broader mapper/peripheral tests and real
gameplay remain necessary before treating the whole NES catalogue as validated.

### What a conversion verifies

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

The same comparisons enable the APU and require byte-identical 48 kHz mono
PCM from generated and interpreted execution, in addition to the frame-state
hashes. Missing/invalid audio also blocks export. Reports retain sample counts
and hashes; successful temporary WAV captures are deleted. This strengthens
translation validation without hiding fallback or claiming an independent
hardware oracle. See [NES audio delivery and checks](AUDIO.md#nes-output-continuity)
for the separate host-buffer correction addressing small sound discontinuities.

The wider tests exposed a validation isolation bug: a native run could save
battery RAM that the next reference run would then load. CPU registers and
bus traces could match while the initial memory hash differed. Every probe
now starts a separate private EXE copy with fresh battery memory. Existing
player saves are preserved, and genuine comparison differences still block
the export. This changes the converter's tests, not normal in-game persistence.

### Self-tests

None of these needs a ROM except where the argument says so. The native ones build C code
and need a compiler ([BUILDING.md](BUILDING.md)). They compare software behaviour with the
same engine's internal CPU and bus; they do not certify physical hardware.

| Tool | What it checks |
|---|---|
| `python tools/nes_native_selftest.py` | All 256 opcodes of authored fixtures across CPU slots, mapper modes (default 0, 1, 2, 3, 4, 5, 7, 9, 11, 26, 66, 69, 71, 78: fourteen families), PAL and NTSC, flag/alignment variants, page crossings, boundary operands, wrapping PC, NMI and IRQ |
| `python tools/nes_guarded_selftest.py` | Authored RAM guards and PPU-driven mapper fetch comparisons (mappers 0, 5, 69, 1, 153, 155): all 256 opcodes, changed operands, RAM mirrors, RAM/ROM and RAM/register boundaries, NMI/IRQ, OAM and DMC DMA, pending reset, changed-opcode rejection |
| `python tools/nes_windows_selftest.py` | Lower-ROM selection, protected cartridge RAM (mappers 40, 69, 21, 22, 23, 25, 80, 207, 82, 552), bank boundaries, DMC/OAM DMA, pending IRQ/NMI/reset; altered ROM fetches must keep visible fallback and must not pollute upper-address ROM seeds |
| `python tools/nes_ppu_selftest.py` | Optimized PPU and APU clocks against the original staged path on authored activity: three configurations (NTSC with Zapper, PAL with Zapper, NTSC without Zapper), mappers 0, 1, 2, 4, 5, 69, 85 and 153, 2,800 checkpoints each, plus the extra-sprite check; hidden PPU fields, framebuffer, bus/memory state and PCM |
| `python tools/nes_mmc1_selftest.py` | The MMC1 with the PPU A12 table rebuild skipped against the original, step by step on 13 authored boards (bank tables, mirroring, work RAM bank and enables after each of 15,165 register writes and A12 changes) |
| `python tools/nes_machine_selftest.py` | Authored NTSC/PAL fixtures: clock/APU behaviour, beam-driven Zapper detection, snapshot round trips, mapper audio, corrupted-state rejection without mutation |
| `python tools/nes_audio_selftest.py` | The host kit's callback-ring output and authored PCM timelines, silently |
| `python tools/nes_state_selftest.py <game.exe>` | Needs a generated game. Saves, closes, relaunches and compares continued CPU/memory/video/hardware hashes and PCM; checks lazy file creation; opens no game window. `--save-after 1800 --frames 180 --input <schedule.input>` resumes a held two-player input schedule in a fresh process |
| `python tools/nes_state_cross.py A.exe B.exe` | Needs two builds of one game. A quick state written by one build must continue identically in the other (for example Visual Studio and portable-toolchain builds) |

The Python suite (`tests/test_nes*.py` and the rest of `python -B -m unittest discover -s tests -q`)
needs no ROM. Recorded matrix sizes and test counts of each campaign are in [NES_LOG.md](NES_LOG.md).

### Broader cartridge validation

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
Those historical gaps are addressed by the guarded-RAM follow-up in
[NES_LOG.md](NES_LOG.md#guarded-ram-and-unstable-mapper-follow-up--12-october-2026).

### Ten further cartridge cases — 9 October 2026

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

### Later campaigns

The 12 October 2026 campaigns and the work that followed are recorded in
[NES_LOG.md](NES_LOG.md); their headline results, as written there:

| Campaign | Cartridges | Result recorded |
|---|---|---|
| Guarded RAM and unstable mapper follow-up (12 October 2026) | Zelda, Kirby's Adventure, Wizards & Warriors, Micro Machines, Dragon Warrior III and IV (512 KiB MMC1) | Zero interpreted cycles on three 3,600-frame scenarios, 64,800 matching frame pairs; 274 verified RAM guards retained in the shared resource |
| Lower ROM aliases and protected cartridge RAM | Eight targeted conversions on mappers 23, 25, 80, 82, 4 (PAL) and 69 | No interpreted cycles on the tested paths; 86,400 matching frame pairs on the final EXEs; 2,421,760 lower-ROM matrix comparisons; no mapper-40 retail qualification |
| RAM-board, DMA and restart qualification (12 October 2026) | Batman: Return of the Joker, Mr. Gimmick, Ufouria, Dragon Ball Z III (supplied translation), Castlevania III, Ninja Gaiden II, Battletoads, Contra | Zero interpreted cycles; 86,400 frame pairs; fresh-process state continuations after 720 and 1,800 input frames |

### Independent comparisons

A separate TriCNES-derived software oracle (pinned, not part of the repository) was run on NTSC
exports over scripted frames, comparing bus traces, CPU state and memory/framebuffer hashes, in
several campaigns (four to seven NTSC exports per run, 1,200 to 3,600 frames per path); it does not include PAL or PCM. An
exploratory [FCEUmm](https://github.com/libretro/libretro-fceumm) comparison matches NMI
counts but not a strict CPU-work counter: that check is **not qualified** and production
timing is unchanged ([NES_LOG.md](NES_LOG.md#discovery-levels-evidence-and-cross-checks)). Neither
establishes exact PAL CPU/video/audio fidelity, gameplay or physical latency.

### Reference games and risk cases

The risk cases that campaigns should always include (`tools/campaign-risk-cases.json`):

| Game | Why |
|---|---|
| Castlevania III: Dracula's Curse | Mapper 5 (MMC5) with mapped RAM |
| The Legend of Zelda | MMC1; the largest recorded fallback (2.91 %) is in the cartridge range below `$8000` |
| Mr. Gimmick | Mapper 69 (FME-7) on a PAL cartridge |
| Esper Dream 2 | Mapper 26 (VRC6) with extra mapper audio (translated dump) |
| Gumshoe | Mapper 66 and Zapper input (mouse aim) |

## 8. Known limits

- Dendy timing is not supported; select NTSC or PAL.
- Only one Zapper is implemented, as an approximate optical response; dual guns and other special
  controllers are not.
- Fine 2C07 register races, complete OAM-refresh circuitry, analogue PAL colour reproduction and
  the palette are not independently validated; the palette is an approximation.
- The strict CPU-work counter against the exploratory FCEUmm test is not qualified (different
  startup and frame phases); the tolerance is not widened.
- Open bus, unobserved RAM opcodes and unsupported memory windows retain counted interpreter
  fallback; the Zelda case (2.91 %, below `$8000`) predates the guarded-RAM work.
- Mapper 40 has no retail qualification; the X1-017 IRQ circuitry is not modelled.
- A quick state holds one slot per game and is tied to the ABI key of the build that wrote it:
  a game rebuilt with changed machine code or layout refuses the old slot (cleanly, nothing is
  misread). States of releases before 1.6.5 (`RRNESST1`) are always refused.
- The quick state does not carry the queued host audio or any host pointer; the audio output
  restarts empty after a load.
- Famicom Disk System images are not supported.
- All scripted paths are startup and input scripts, not complete playthroughs. Native coverage,
  CPU differential, hardware fidelity, gameplay and physical latency remain separate evidence
  areas; no zero-latency or exact-fidelity claim is made.

## 9. History

The profile is no longer labelled experimental. The October 2026
campaigns (8 October: eight cartridges; 9 October: ten more and the fourteen-family opcode matrix;
12 October: guarded RAM, unstable mappers and DMA; lower ROM aliases and protected RAM boards) are
detailed in [NES_LOG.md](NES_LOG.md). Release-level changes are in
[RELEASE_NOTES.md](RELEASE_NOTES.md) and [UPGRADES.md](UPGRADES.md).
