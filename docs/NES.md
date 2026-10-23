# Nintendo NES profile

**Status: supported within the validated cartridge and peripheral scope.**
The profile is no longer labelled experimental. Compatibility remains specific
to cartridge layouts and tested paths; this is not a whole-catalogue guarantee
or a claim that every game runs without interpreter fallback.

RetroRecomp accepts `.nes`, headered `.bin`/`.rom`, and single-ROM ZIP files.
It generates standalone Windows games in `Games/Nintendo NES`, with no change
to the source ROM. A native Linux development port shares the same compiler
and cartridge observations; see [building](BUILDING.md). The converter keeps
its ROM entry library under `datas/library/nes`. Optional fallback recording
collects hints in memory and writes them only when the game closes; F12 toggles
recording. See [runtime feedback](RUNTIME_FEEDBACK.md).

The backend is pinned to
[`mstan/nesrecomp` revision `1b0c621`](https://github.com/mstan/nesrecomp/tree/1b0c621a927db17afa9723bf456a89ad15809907).
Its [PolyForm Noncommercial 1.0.0 license](../licenses/nesrecomp.md) applies
separately from RetroRecomp's original MIT code. Generated games embed the
component notices as Windows resources or embedded Linux data. The converter release contains no
NES ROM or generated commercial game executable. The pinned engine checkout
is unchanged: compiler and machine adapters are staged in private build folders.

## Linux runtime performance

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
This internal comparison is not an independent physical-hardware proof.

## Native coverage

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

The same comparisons now enable the APU and require byte-identical 48 kHz mono
PCM from generated and interpreted execution, in addition to the frame-state
hashes. Missing/invalid audio also blocks export. Reports retain sample counts
and hashes; successful temporary WAV captures are deleted. This strengthens
translation validation without hiding fallback or claiming an independent
hardware oracle. See [NES audio delivery and checks](AUDIO.md#nes-output-continuity)
for the separate host-buffer correction addressing small sound discontinuities.

## Advanced exploration and incremental builds

**Options → Nintendo NES → Discovery scan** offers four levels; *Standard* is
the default. *Extended* (the former advanced scan, `--nes-advanced-scan`) adds three
deterministic paths to boot/right/left: released menu/dialogue confirmations,
Select and separate player-2 input, and varied movement/jump/button releases.
Each path respects the configured frame budget; Start is pulsed once per
controller to avoid repeatedly pausing a game. These bounded scripts do not
guarantee every menu, level or a complete playthrough. *Thorough* adds two
reproducible pseudo-random routes of 18,000 frames seeded from the exact ROM
(`smsrecomp/random_routes.py`), compared with the reference like the authored
replays; *Quick* keeps boot and the right-hand play run for a single pass. The
report records the level and each scenario's frame budget under `advanced_scan`.

Every advanced path compares all its frames with the internal interpreter and
exact PCM **before the next learning pass**. The fresh final-pass evidence is
bound to the current EXE hash; it is not reused from another build. Failed
comparisons still block export and shared promotion. Five exact revisions
(Minelvaton, Batman, Zelda, Kirby and PAL Mr. Gimmick) pass six 3,600-frame
paths each: **108,000 final-pass internal CPU/frame/PCM pairs**. The actual
compressed EXEs separately pass the three added paths: **54,000 pairs**,
with ten fresh-process state continuations. The new Batman menu path initially
uses three interpreted cycles; one additional exact RAM entry/opcode guard
removes them. All final paths report zero interpreted cycles.

Four NTSC revisions match the separate TriCNES-derived oracle on twelve added
paths, **16,800 frames** including the complete 3,600-frame Batman menu path.
Private end-frame captures confirm first-level scenes in Kirby and Batman;
this is scene inspection, not a hands-on playthrough. An exploratory independent
[FCEUmm](https://github.com/libretro/libretro-fceumm) authored test matches NMI
counts over fixed NTSC/PAL frame intervals. Its CPU-work counters differ by
roughly 15–16 cycles per 100 fields after accounting for the fixture's carries.
Different startup/frame phases remain a limitation: the strict counter check
is **not qualified**, its tolerance is not widened, and production timing is
unchanged. This does not establish exact PAL CPU/video/audio fidelity.

The converter materialises selected generated C files at stable paths. An
exact ROM/compiler/ROM-entry receipt and source hashes validate raw output;
RAM observations adapt only the selected umbrella. Byte-identical sources
retain timestamps, and staged native headers keep stable include paths across
separate one-file converter launches. Changed inputs and corrupted caches
are regenerated. No previous qualification report is used as a shortcut.

A local before/after measurement with empty private and bundled knowledge
recompiles Minelvaton twice with identical validation budgets. All fifty final
C sources, per-frame hashes and PCM hashes match. On the second pass, adding
77 RAM guards recompiles **one C file instead of fifty**, reusing 65 objects.
Build time falls from **17.20 to 1.81 seconds** (about 9.5×). Total conversion
time is **542.78 versus 538.43 seconds** on this run: long reference checks
dominate, so this is not a 9.5× whole-conversion or cold-toolchain claim.

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
Those historical gaps are addressed by the guarded-RAM follow-up below.

## Guarded RAM and unstable mapper follow-up — 12 October 2026

Release 0.26.0 adds native instruction bodies for observed
RAM entry/opcode pairs, tied to the exact cartridge. The current opcode is
checked before execution; operands retain their individual live bus reads.
Changing an operand therefore needs no new variant. Changing an opcode or
jumping to an unobserved entry retains visible fallback. No runtime compiler,
ROM patch, opcode interpreter or pixel correction is added to the guarded path.

Eligible windows include internal RAM and modelled plain cartridge RAM,
including MMC5's mapped RAM. Guards use side-effect-free memory probes; they
never read PPU/APU registers to inspect an entry. Only the converter's explicit
probe can write its bounded entry journal. Ordinary exported-game launches
still create no learning log. Interrupted build observations stay local until
normal native/reference comparisons qualify them.

For PPU-dependent MMC1/MMC1A and mapper 153, the opcode's physical bank is
latched at the real bus access, after DMA stalls. Every operand remains live,
and dispatch rechecks the mapping after each instruction. If that fetch has
no matching compiled body, the interpreter continues the already-fetched
instruction exactly once; those cycles remain in the fallback counters.

Authored PAL/NTSC tests cover all 256 opcodes, changed operands, RAM mirrors,
RAM/ROM and RAM/register boundaries, NMI/IRQ, OAM DMA, changed-opcode rejection
and PPU-driven outer-bank changes. Additional ordinary MMC1/MMC3/MMC5 cases
preserve the existing ROM-native path. These are differentials against the
same engine's internal CPU, not independent electrical hardware certification.
Run `python tools/nes_guarded_selftest.py` for the new authored matrix.

The targeted retail qualification uses Zelda, Kirby's Adventure, Wizards &
Warriors, Micro Machines and the 512 KiB MMC1 revisions of Dragon Warrior III
and IV. Reports, per-path fallback results and shared hints remain bound to
each exact ROM. Gameplay and physical latency remain separate evidence areas;
these startup/input scenarios are not complete playthroughs.

All six cartridges finished their three 3,600-frame scenarios with zero
interpreted cycles and matching CPU/memory/frame/PCM: **64,800 matching frame
pairs**. Their final compressed EXEs additionally passed three 600-frame
comparisons each, 180-frame fresh-process state continuation, corrupt-state
rejection, ordinary-startup and missing-load lazy-I/O checks. The new authored
matrix passes 155,648 instruction cases; ordinary MMC1/MMC3/MMC5 regressions
pass another 199,680. The ROM-free Python suite passes 335 tests.
The [shared resource](COMPILATION_LIBRARY.md) retains 274 verified RAM guards
for these exact cartridges. Other RAM-bearing board layouts, later gameplay
and independent hardware/physical latency tests remain separate work.

The wider tests exposed a validation isolation bug: a native run could save
battery RAM that the next reference run would then load. CPU registers and
bus traces could match while the initial memory hash differed. Every probe
now starts a separate private EXE copy with fresh battery memory. Existing
player saves are preserved, and genuine comparison differences still block
the export. This changes the converter's tests, not normal in-game persistence.

## Lower ROM aliases and protected cartridge RAM — current development

Native dispatch now includes cartridge ROM mapped at `$6000-$7FFF` by mappers
40 and 69. The mapper's current selection determines the physical PRG byte;
opcode and operands use individual live bus reads, including across `$7000`
and `$8000`. FME-7 ROM/RAM selection is checked anew at each fetch. Lower ROM
aliases do not enter the upstream seed format, whose address slots start at
`$8000`; dense native coverage makes those ambiguous seeds unnecessary.

Guarded RAM code also covers accessible VRC2/VRC4 boards (21, 22, 23, 25),
Taito X1-005 (80, 207) and X1-017 (82, 552). The probe follows the runtime's
read mapping without reading a register or changing state. VRC2 protection
latches without RAM, disabled VRC4 RAM, the 2 KiB VRC4 hole at `$7000+`, Taito
lock values, register windows and unmapped holes remain excluded. An observed
entry/opcode guard is still required; operands are never learned or folded.
This extends recompilation coverage rather than adding new mapper hardware,
including the still unmodelled X1-017 IRQ circuitry.

`python tools/nes_windows_selftest.py` checks authored PAL/NTSC fixtures for
lower-ROM selection, protected RAM, bank boundaries, DMC/OAM DMA and pending
IRQ/NMI/reset. Altered ROM fetches must retain visible fallback and must not
pollute upper-address ROM seeds. Retail exports require their ordinary
native/reference gates independently of this instruction matrix.

The new 34-point matrix passes **2,421,760 instruction comparisons**, including
148,480 lower-ROM cases and 455,680 pending-DMC cases. It rejects 102 protected
or unmapped windows and checks 24 deliberately altered ROM fetches, including
visible fallback and seed-journal isolation. Existing NROM/MMC5/FME-7 PAL/NTSC
guard regressions add 573,440 passing instruction cases. The machine matrix
still passes 11,216 checks across sixteen configurations. These compare
software CPU/bus/machine behavior; they do not certify physical hardware.

Eight targeted conversions include Akumajou Special: Boku Dracula-kun (23),
Bio Miracle Bokutte Upa and Gradius II (25), Fudou Myouou Den and the supplied
translated Minelvaton Saga (80), SD Keiji: Blader (82), PAL Parodius (4), and
Batman: Return of the Joker (69). Their tested boot and two 3,600-frame input
paths report no interpreted cycles. Minelvaton initially used 6,782 RAM
interpreter cycles on each input path; 77 exact entry/opcode guards remove
these calls at the second compilation pass. No ROM patch is applied.
There is no mapper-40 retail qualification in this set.

The seven NTSC exports separately match the pinned TriCNES-derived software
oracle over **8,400 scripted frames**, including bus traces, CPU state and
memory/framebuffer hashes. This oracle check does not include PAL or PCM
and is not a complete gameplay or original-hardware certification.

All eight actual compressed EXEs repeat the full internal checks on the three
3,600-frame paths: **86,400 matching CPU/memory/frame/PCM frame pairs**, with
zero interpreted cycles. Sixteen fresh-process state continuations resume
after 720/1,800 input frames, 180 frames each, including held-input restoration,
lazy file creation and six incompatible/corrupted-state cases. Minelvaton also
matches the separate oracle for a full 3,600-frame input path. These bounded
paths do not establish complete playthroughs or physical latency.

## RAM-board, DMA and restart qualification — 12 October 2026

The additional qualification shipped in 0.26.0 extends guarded code to the enabled FME-7 work-RAM
window and mapper 153's ordinary RAM mode. FME-7 ROM/open-bus selections,
disabled RAM and mapper 153's SDA contention retain fallback. Probes never
read a cartridge register to decide whether an entry is eligible.

Eight additional or refreshed exact revisions cover these cases:

| Cartridge | Mapper | Timing |
| --- | --- | --- |
| Batman: Return of the Joker | 69 | NTSC |
| Mr. Gimmick | 69 | PAL |
| Ufouria: The Saga | 4 | PAL |
| Dragon Ball Z III — supplied translated revision | 16 | NTSC |
| Castlevania III: Dracula's Curse | 5 | NTSC |
| Ninja Gaiden II | 4 | NTSC |
| Battletoads | 7 | NTSC |
| Contra | 2 | NTSC |

Batman initially used 242,079 / 53,757 / 32,853 interpreted cycles on the
three paths. Its 485 observed entry/opcode guards remove those calls without
folding RAM operands. All eight final conversions report zero interpreted
cycles on boot and two 3,600-frame input paths. The supplied ROMs, including
the translated revision, remain unchanged and are not distributed.

The authored guard matrix now includes DMC sample DMA, simultaneous DMC/OAM
transfers, all combinations of pending NMI/IRQ/reset, four clock phases and
PPU-dependent bank changes. Each native/reference pair starts with identical
RAM and CHR-RAM state. Cartridge CHR RAM survives a reset; failing to reset it
between independent test runs produced a false PAL difference, now caught by
an explicit initial-state equality check. This repairs test isolation, not
the console's legitimate persistence behavior.

The quick-state matrix also resumes pending DMA and interrupts on eight
mapper families in PAL/NTSC. Export checks can resume a held two-player input
schedule in a fresh process, including an event exactly at the load frame.
Run `python tools/nes_state_selftest.py <game.exe> --save-after 1800
--frames 180 --input <schedule.input>` for a later scripted restart. Invalid
magic, ABI, ROM identity, region, payload and truncated states are rejected
without rewriting the valid or rejected file.

The expanded PAL/NTSC guard matrix passes **1,261,568 instruction cases**,
including 491,520 DMC fetches, 630,784 pending-reset cases and 84 rejected
guards. The machine/state matrix passes 11,216 assertions and 1,536 pending
transfer/interrupt round trips. All eight final compressed exports match
**86,400 internal CPU/memory/frame/PCM frame pairs** with zero interpreted
cycles on those paths. Each also passes two fresh-process state continuations
after 720 and 1,800 input frames, 180 resumed frames per case and six types of
rejected states. The ROM-free Python suite passes 337 tests.

Six NTSC revisions separately match the pinned TriCNES-derived software
oracle on 1,200 scripted frames each, comparing bus traces, CPU state and
memory/framebuffer hashes. This bounded oracle check does not validate PAL,
physical latency, all hardware circuits or complete playthroughs. Those
claims remain separate from native coverage and internal reference checks.

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

F1 opens help, Shift+F1 restarts, P pauses, F3 cycles sharp/Scale2x/scanlines/xBR,
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
The default reticle is a small red cross. The Zapper page of F2 (press Tab)
selects cross/dot, size and red/white/green. Intentional game flashes are kept.
On every NES game, **F5** toggles the optional extra sprites described in
[controls](CONTROLS.md); it no longer opens the Zapper page.
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
