# NES qualification log

The dated journal of the NES qualification work, moved out of [NES.md](NES.md) so that the
machine page stays a reference. Every entry is kept as it was written on its date: counts,
cartridges and wording describe that campaign, not the current state of the converter. For what the
NES profile does today, read [NES.md](NES.md); for the gates, [QUALIFICATION.md](QUALIFICATION.md).
The two oldest campaigns (8 and 9 October 2026, with their cartridge tables) stay in
[NES.md](NES.md#broader-cartridge-validation).

Native coverage, CPU fidelity, hardware fidelity, gameplay validation and physical latency stay
separate evidence areas in every entry below.

## Contents

- [Instruction matrix growth](#instruction-matrix-growth)
- [Discovery levels: evidence and cross-checks](#discovery-levels-evidence-and-cross-checks)
- [Incremental build measurement](#incremental-build-measurement)
- [Guarded RAM and unstable mapper follow-up, 12 October 2026](#guarded-ram-and-unstable-mapper-follow-up--12-october-2026)
- [Lower ROM aliases and protected cartridge RAM](#lower-rom-aliases-and-protected-cartridge-ram--current-development)
- [RAM-board, DMA and restart qualification, 12 October 2026](#ram-board-dma-and-restart-qualification--12-october-2026)
- [Statements replaced by later documents](#statements-replaced-by-later-documents)

## Instruction matrix growth

This paragraph records how `tools/nes_native_selftest.py` grew (the tool itself is described in
[NES.md](NES.md#self-tests)).


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

## Discovery levels: evidence and cross-checks

Recorded with the *Extended* level (then called the advanced scan) and its later cross-checks. The
description of the levels is in [NES.md](NES.md#discovery-levels-and-incremental-builds).


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

## Incremental build measurement

The mechanism (stable paths, receipts, regeneration of changed inputs) is described in
[NES.md](NES.md#discovery-levels-and-incremental-builds).


A local before/after measurement with empty private and bundled knowledge
recompiles Minelvaton twice with identical validation budgets. All fifty final
C sources, per-frame hashes and PCM hashes match. On the second pass, adding
77 RAM guards recompiles **one C file instead of fifty**, reusing 65 objects.
Build time falls from **17.20 to 1.81 seconds** (about 9.5×). Total conversion
time is **542.78 versus 538.43 seconds** on this run: long reference checks
dominate, so this is not a 9.5× whole-conversion or cold-toolchain claim.


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

The page called this section "current development" without a date; it is the work that followed the 12 October 2026 guarded-RAM follow-up above. Its mechanisms are summarised in [NES.md](NES.md#guarded-ram-and-lower-rom-aliases).


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


## Statements replaced by later documents

- The earlier NES page said that a left-stick click pauses the game and a player 1 right-stick click
  restarts it. The common host kit has since replaced those two shortcuts: Enter (the cartridge Start)
  pauses, Shift+F1 or the held Start+Select combination restarts, and L3+R3 held for one second quits.
  See [CONTROLS.md](CONTROLS.md).
- The PPU comparison of 44,800 checkpoints quoted in [NES.md](NES.md#linux-runtime-performance) was
  recorded earlier: 2 configurations x 8 mappers x 2,800 checkpoints gives 44,800, while the current
  `tools/nes_ppu_selftest.py` runs three configurations (3 x 8 x 2,800 = 67,200 checkpoints; not re-run for this page).

