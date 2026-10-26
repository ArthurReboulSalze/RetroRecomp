# Super FX (GSU) on the Super Nintendo: study and plan

Status on 26 October 2026: **experimental, not released; the study branch is
paused and unfinished.** Players of release
1.5.2 reported Doom, Dirt Trax FX and Dirt Racer failing with
`SNES enhancement chip Super FX is not integrated yet (map $20, type $14)`.
This page records what Super FX boards are, what the pinned SNES engine
already provides, the first slice built on the study branch, the evidence
gathered, and a costed plan. Nothing here is a fidelity or latency claim.

## Summary

- The pinned engine (`RetroPortingToolKit/snesrecomp` at `a00df26`) already
  contains a **Super FX instruction-level core** (`runner/src/snes/superfx.c`,
  936 lines), wired to the cartridge bus, the shared master clock, the IRQ
  line and save states. Its header states that its instruction, pixel and
  cache semantics were independently adapted from the ISC-licensed
  [ares](https://github.com/ares-emulator/ares) implementation (commit
  `449b937`). It is compiled into every SNES export today; Retro-Recomp only
  refused Super FX headers before reaching it.
- The first slice (this branch) recognizes the four Super FX board types,
  sizes their Game Pak RAM like the engine, lets the native 65816 lookup see
  the board's ROM views, reports the GSU as a **counted interpreted device**
  exactly like the CX4, and marks the conversion **experimental**.
- With it, **all eight local Super FX cartridges convert at the Standard
  level** (2-3 minutes each) with zero interpreted 65816 and SPC700 opcodes on
  their validated routes, matching internal native/reference comparisons,
  exact quick-state round trips and visible 3D or sprite-scaling scenes. Doom
  and Dirt Trax FX against MAME show the same scenes but are **not
  frame-aligned**: the measured causes are simplifications on MAME's side
  (no DRAM refresh, free DMA, a flat GSU cost), so MAME is used as an
  event-order reference, not a frame-alignment oracle.
- Native recompilation of GSU code is possible in principle (the code is in
  ROM) but is a separate multi-week project; the interpreter stays the
  measured fallback and remains visible. A decoder, a static traversal and a
  measurement of all eight cartridges now exist ("Option B: measured"): the
  code is small and regular, but the GSU core is only 7-27 % of host frame
  time, so option B would buy little speed and is not recommended on that
  ground.

## Commercial Super FX cartridges

The header does not encode the GSU revision. The chip column follows the
commonly published board lists and is not measured here. Header bytes were
read (read-only, in memory) from the local NAS dumps on 25 October 2026.

| Game | Chip | Map/type ($FFD5/$FFD6) | ROM | $FFBD (Game Pak RAM) | Battery | Local dump |
|---|---|---|---|---|---|---|
| Star Fox (USA) | MARIO chip (GSU-1 family) | $20 / $13 | 1 MiB | none (maker $01, old header) → 64 KiB default | no | yes |
| Stunt Race FX (USA) | GSU-1 | $20 / $1A | 1 MiB | $06 = 64 KiB | yes | yes |
| Vortex (USA) | GSU-1 | $20 / $14 | 512 KiB | $05 = 32 KiB | no | yes |
| Dirt Trax FX (USA) | GSU-1 | $20 / $14 | 512 KiB | $06 = 64 KiB | no | yes |
| Dirt Racer (Europe) | GSU-1 | $20 / $14 | 512 KiB | $05 = 32 KiB | no | yes (PAL) |
| Super Mario World 2: Yoshi's Island (USA) | GSU-2 | $20 / $15 | 2 MiB | $05 = 32 KiB | yes | yes |
| Doom (USA) | GSU-2 | $20 / $14 | 2 MiB | $06 = 64 KiB | no | yes |
| Winter Gold / FX Skiing | GSU-2 | not measured | — | — | — | no |
| Star Fox 2 (USA, 2017) | GSU-2 | $20 / $15 | 1 MiB | $06 = 64 KiB | yes | yes |
| Star Fox 2 (Japan proto, translated) | GSU-2 | $20 / $1A | 1 MiB | $06 = 64 KiB | yes | yes |

Markers used by the converter: map byte `$20` (LoROM family), cartridge type
`$13`, `$14`, `$15` or `$1A` (high nibble `$1` = Super FX). Game Pak RAM comes
from the extended header byte `$FFBD` (`$400 << n`) when the maker byte
`$FFDA` is `$33`; older headers (Star Fox) get the engine loader's 64 KiB
default. `$FFD8` reads 0 on all of them. Types `$15` and `$1A` are treated as
battery-backed. "Winter Olympic Games - Lillehammer '94" on the NAS is an
ordinary cartridge, not Winter Gold.

### Memory maps

65816 side (as decoded by the engine's `cart.c`):

| Banks | Addresses | Content |
|---|---|---|
| $00-$3F, $80-$BF | $3000-$32FF | GSU registers: $3000-$301F R0-R15 (writing $301F starts the GSU), $3030/$3031 SFR (status, IRQ acknowledge), $3033 BRAMR, $3034 PBR, $3036 ROMBR, $3037 CFGR, $3038 SCBR, $3039 CLSR, $303A SCMR, $303B VCR, $303C RAMBR, $303E/$303F CBR, $3100-$32FF instruction cache |
| $00-$3F, $80-$BF | $6000-$7FFF | 8 KiB mirror of the start of Game Pak RAM |
| $00-$3F, $80-$BF | $8000-$FFFF | ROM, LoROM view |
| $40-$5F, $C0-$DF | $0000-$FFFF | ROM, linear view (2 MiB) |
| $70-$71, $F0-$F1 | $0000-$FFFF | Game Pak RAM (up to 128 KiB) |

While the GSU runs and owns the ROM or RAM bus (SCMR RON/RAN), the 65816 loses
that bus: ROM reads return the interrupt-vector override, which is why Super
FX games run their own 65816 code from WRAM during GSU jobs.

GSU side: code at PBR:R15 (ROM banks $00-$5F, or Game Pak RAM $70-$71),
data via ROMBR (ROM buffer, R14 triggers a fetch) and RAMBR, a 512-byte
instruction cache located by CBR. PLOT/RPIX write a planar bitmap into Game
Pak RAM at SCBR, in 2/4/8 bpp with 128/160/192-line or OBJ layouts (SCMR).
The GSU never touches VRAM: the 65816 DMAs that bitmap from $70:xxxx to VRAM,
normally during vertical blank.

## What the engine already has

- `superfx.c`/`superfx.h`: registers, ALT1-3 and FROM/TO/WITH prefixes, the
  branch delay slot, ROM/RAM buffers with their latencies, pixel caches,
  instruction cache, MULT/FMULT/LMULT timing (CFGR), CLSR clock selection,
  STOP and IRQ (masked by CFGR bit 7), SFR.G. Cost per instruction is counted
  in master clocks (`clsr ? 1 : 2` per GSU cycle, 5/6 for uncached fetches).
- Synchronization: `superfx_sync()` consumes master-clock credit in 6-clock
  quanta. `cart_sync_coprocessors()` catches the GSU up on every 65816 access
  to the cartridge and at the beam frame driver's boundaries (inline for the two
  common cases, see [Host cost](#host-cost-26-october-2026)); the GSU IRQ is
  part of the driver's pending-IRQ test.
- Save states: `superfx_saveload()` streams 696 bytes of architectural state
  (registers, caches, buffers, master clock and credit, IRQ); Game Pak RAM is
  streamed by the cartridge.
- Presentation extras (widescreen replay, PC hooks) are opt-in per title and
  stay off; Retro-Recomp never enables them.

## First slice (this branch)

| File | Change |
|---|---|
| `retrorecomp/snes_chips.py` | `identify()` returns `superfx` for map $20, type $13/$14/$15/$1A on a LoROM header; other `$1x` types stay refused |
| `retrorecomp/snes_cart.py` | Game Pak RAM size and battery as above; that RAM is never a guarded 65816 code window |
| `retrorecomp/snes_codegen.py` | the native 65816 lookup resolves Super FX ROM through its LoROM and linear views (the engine gives these boards no ROM pointer); the fetched-opcode check still rejects bytes replaced by the GSU bus |
| `retrorecomp/supernintendo.py` | support stage `experimental` for Super FX (report status and the "created (experimental)" label) |
| `retrorecomp/console16.py` | conversion log line naming the counted GSU interpreter; main-CPU-only `native_percentage` and the separate `cartridge_device` report entry |
| `native/snes_backend.c` | GSU instructions are counted apart from the 65816 (`rr16_device_interpreted()`); report fields `cartridge_chip=superfx`, `coprocessor_mode=interpreted`, GSU state hash |
| `tests/test_snes_chips.py`, `tests/test_console16.py` | Super FX positive cases; refusal fixtures moved to other unsupported types |

All of these are game-side inputs (`retrorecomp/compilation_inputs.py`): the
SNES game fingerprint changes, so every existing SNES export needs a full
reconversion when this ships. The pinned engine is not modified.

## Evidence from the study branch

### Quick level spike (25 October 2026)

Quick level, one pass, empty private library per game, Windows, headless,
build folders removed after publication. Outputs under
`.build/superfx-spike/` (not committed).

| Game | Conversion | 65816 native entries / interpreted (demo) | GSU interpreted instructions (demo / play, 1,200 frames) | Visible frames | Reference comparison |
|---|---|---|---|---|---|
| Dirt Trax FX | 71 s | 473,606 / 9,048,978 | 71,616,564 / 64,974,903 | 977 / 896 | matches |
| Doom | 79 s | 6,575,618 / 1,066,142 | 16,307,193 / 36,960,441 | 883 / 883 | matches |
| F-Zero (control, ordinary cartridge) | 78 s | 0 interpreted | — | — | matches |

- Doom's steady gameplay runs about **152,000 GSU instructions per frame**
  (frames 1,400-2,600). Running the published Doom export headless for 3,000
  frames took 32-33 s, about 11 ms per frame including process start. This is
  host cost on an unpinned core, not a latency measurement.
- The 65816 of Dirt Trax FX is still mostly interpreted after one quick pass:
  its code runs from WRAM while the GSU owns ROM, and guarded WRAM routines are
  learned over passes. This has to be measured at the Standard level.
- The report's `native_percentage` then mixed 65816 and GSU counts
  (Dirt Trax FX 0.6 %, Doom 14-27 %). Honest but unreadable: the figures are
  now separate, see "Fallback percentage" below.
- Quick states: saving at frame 1,500 and resuming for 300 frames gives the
  same frame, CPU, WRAM, VRAM, GSU-state, Game Pak RAM and APU RAM hashes as
  an uninterrupted 1,800-frame run, for both games. (The PCM hash is
  cumulative per process and is not comparable this way.)
- MAME 0.289 (`.build/tools`, used as a black-box binary, headless, no window)
  at screen frames 600, 1,500 and 3,000: Doom shows the same title and the same
  first room at 1,500, but at 3,000 MAME is on a black transition while the
  export still shows the room. Dirt Trax FX shows the same title, menu and race
  demo, but fades are offset and the race positions differ at 3,000. Content
  agrees; **timing does not**, and neither side is ground truth. The black MAME
  frame at 3,000 is one of the blank frames of MAME's 9-frame Doom render
  cycle, not a demo-timing fact (see "Timing and synchronization"). MAME
  needs the 64-byte SPC700 IPL; the comparison wrote it locally from the pinned
  engine's `apu.c` into the spike folder (CRC `44bb3a40`), nothing distributed.
### Standard level, all eight cartridges (26 October 2026)

Standard scan level, default two passes, empty private library per game, four
conversions at a time on Windows, headless, build folders removed after
publication. Outputs under `.build/superfx-standard/` (not committed). Every
report has status `experimental`.

| Game | Standard | Conversion | GSU instructions demo / play (1,200 frames) | Visible frames demo / play | Game Pak RAM, battery | Host ms/frame (3,000 frames, demo / play) |
|---|---|---|---|---|---|---|
| Star Fox | NTSC | 165 s | 61,130,576 / 47,044,442 | 1,050 / 943 | 64 KiB, no | 13.1 / 11.8 |
| Stunt Race FX | NTSC | 135 s | 2,837,423 / 19,868,394 | 1,072 / 979 | 64 KiB, yes | 10.4 / 10.6 |
| Vortex | NTSC | 172 s | 30,439,017 / 22,452,661 | 894 / 808 | 32 KiB, no | 16.0 / 15.8 |
| Dirt Trax FX | NTSC | 128 s | 71,616,564 / 64,974,903 | 977 / 896 | 64 KiB, no | 11.9 / 11.2 |
| Dirt Racer | PAL | 178 s | 169,935,148 / 183,639,604 | 1,034 / 957 | 32 KiB, no | 15.8 / 16.1 |
| Yoshi's Island | NTSC | 151 s | 15,634,003 / 50,649,004 | 1,111 / 1,010 | 32 KiB, yes | 10.8 / 11.2 |
| Doom | NTSC | 110 s | 16,307,193 / 36,960,441 | 883 / 883 | 64 KiB, no | 12.0 / 11.1 |
| Star Fox 2 | NTSC | 159 s | 84,295,754 / 55,837,942 | 1,027 / 856 | 64 KiB, yes | 12.5 / 10.4 |

- Final checks of all eight: **0 interpreted 65816 opcodes and 0 interpreted
  SPC700 opcodes** on the demo and play routes; the internal reference
  comparison (CPU, memory, visible frames, audio PCM, GSU state) matches.
  At the Standard level the WRAM routines of Dirt Trax FX are learned too.
- Beyond the validated 1,200 frames some 65816 code is still met for the first
  time and interpreted (for example Stunt Race FX: about 4.7 million opcodes by
  frame 3,000 in its demo; Star Fox 2 and Yoshi's Island a few thousand). Long
  routes will have to learn it.
- Quick states (save at 1,500, resume for 300 frames, compared with an
  uninterrupted 1,800-frame run): frame, CPU, WRAM, VRAM, GSU state, Game Pak
  RAM and APU RAM hashes are identical for all eight.
- Pictures at frames 1,500 and 3,000, demo and play: every game shows its own
  content (Star Fox space intro and title, Star Fox 2 map and dialogue, Stunt
  Race FX race, Yoshi's Island intro, Vortex briefing and stage cards, Doom
  rooms, Dirt Trax FX race and menu, Dirt Racer demo). The automatic Start
  presses of the play route do not enter gameplay in Star Fox (title) or Dirt
  Racer (language menu); dedicated input routes are needed. No picture is
  compared with an independent reference here.
- Host cost is unpinned, includes process start and is not a latency claim.
  Vortex (16 ms) is close to the 16.7 ms NTSC frame; Dirt Racer (PAL, 16 ms)
  has a 20 ms frame. A sampling profile of the same builds (see "Option B:
  measured") puts the GSU core at 7-27 % of that time: the PPU and the bus
  dominate, so GSU cost is not the main factor and is a weak argument for
  option B.
- Not yet run: battery save round trips, long routes, packed exports, the
  Japanese Star Fox 2 prototype.

## Options

### A. Counted interpreter (the slice; recommended first)

The GSU runs on the engine's instruction core, every instruction is counted
and shown, and the 65816/SPC700 keep their own native coverage. This is how
the CX4 ships. Its risks are integration ones (DMA from Game Pak RAM, bus
ownership, idle polling, timing) rather than instruction semantics, and the
qualification below is designed to find them.

### B. Static recompilation of GSU code

GSU programs live in ROM and are started by the 65816 writing R15 ($301F)
with PBR set, so their entry points are observable (the engine keeps a job
log of PBR:R15 starts) and their bodies can be traversed statically.
Specific difficulties:

- Decoding depends on prefix state (ALT1/ALT2/ALT3, FROM/TO/WITH), so a
  compiled block is keyed by (PC, prefix state), not by PC alone.
- Every branch and jump has a one-instruction delay slot; `JMP Rn`, `LJMP` and
  `IWT R15,#` need observed targets, like 65816 indirect jumps.
- Cycle cost depends on whether the instruction comes from the 512-byte cache
  or ROM/RAM, and on ROM/RAM buffer waits. Compiled code must reproduce the
  same master-clock totals at every point the 65816 can observe (SFR, Game Pak
  RAM, IRQ), or call the same buffer and pixel-cache helpers as the core.
- Code can run from Game Pak RAM, and the 65816 can write the instruction cache
  directly ($3100-$32FF). Such code stays interpreted; cache-resident code is
  native only while its bytes still match ROM.

Benefit: a growing native share of the GSU and, at most, the host time the GSU
core uses today (7-27 % of the main thread, measured below; the interpreted
GSU already fits in a frame on this PC). Cost: a second recompiler with its
own guards, learning records and checks. Do it only after A is qualified, and
see the recommendation under "Option B: measured".

#### Option B: measured (26 October 2026)

Groundwork now in the repository: `retrorecomp/snes_gsu.py` (a prefix-aware
decoder and a static traversal from entry points; 27 unit tests on
hand-assembled byte sequences) and `tools/snes_gsu_survey.py` (coverage, mix
and timing report from execution dumps). Neither is used by the conversion
path. Instruction semantics come from public documentation (nocash fullsnes);
the points it leaves open (ALT3 forms, the value R15 reads as, the delay slot
pipeline, STOP) were taken from the behaviour of the pinned engine's core and
checked against what it executed. Nothing GPL was read.

Method: the eight local cartridges converted at the Standard level with the
build folder kept; a *local copy* of the engine in each build folder was
patched to dump every executed GSU instruction (address, prefix state, where
the byte came from, count), every taken non-sequential transition and every
job start, then run headless for 6,000 frames with the demo route and 6,000
with `--play`. In total 7.5 billion GSU instructions. The routes are attract
mode and the automatic Start presses: gameplay of later stages is not reached
(Star Fox stays at its title, Dirt Racer at its language menu), so entry points
and indirect targets will grow with longer routes. The dump format is not
produced by the product.

| Game | GSU instructions | Entry points (job starts) | Static from entries | With observed indirect targets | Static code | Game Pak RAM or CPU-cache code |
|---|---|---|---|---|---|---|
| Star Fox | 548 M | 10 (36,516) | 51.9 % | 100.0 % | 11,925 instr. | 0 |
| Stunt Race FX | 668 M | 24 (18,371) | 39.0 % | 100.0 % | 39,134 instr. | 0 |
| Vortex | 774 M | 17 (29,183) | 51.1 % | 100.0 % | 14,297 instr. | 0 |
| Dirt Trax FX | 910 M | 1 (2) | 0.0 % | 100.0 % | 26,981 instr. | 0 |
| Dirt Racer | 2,506 M | 6 (11) | 5.9 % | 100.0 % | 18,617 instr. | 0 |
| Yoshi's Island | 350 M | 33 (106,714) | 91.6 % | 100.0 % | 14,537 instr. | 0 |
| Doom | 1,348 M | 9 (11,774) | 71.1 % | 100.0 % | 13,378 instr. | 0 |
| Star Fox 2 | 432 M | 18 (27,052) | 53.3 % | 100.0 % | 18,820 instr. | 0 |

"Static from entries" is the share of executed instructions that a traversal
from the job entry points alone reaches; the last column but one adds the
targets observed at indirect jumps (so it is a closure over the dumps, not an
independent result). Independent checks: the decoder's ROM view reproduced
every executed ROM opcode (0 mismatches), and the traversal's model of
branches, JMP/LOOP/IWT R15 and delay slots (given the observed indirect targets)
predicted every one of 963 million executed non-sequential transitions (0
unexplained).

| Game | Indirect sites reached | Resolved by constants | Executed, unresolved | Observed targets 1 / 2-3 / 4+ | Most targets at one site | Taken transfers through unresolved |
|---|---|---|---|---|---|---|
| Star Fox | 464 | 417 (+5) | 36 | 21 / 12 / 3 | 8 | 0.60 % |
| Stunt Race FX | 1,011 | 861 (+11) | 119 | 74 / 42 / 3 | 16 | 1.01 % |
| Vortex | 489 | 411 (+7) | 63 | 27 / 27 / 9 | 16 | 0.52 % |
| Dirt Trax FX | 872 | 764 (+41) | 100 | 55 / 27 / 18 | 18 | 3.14 % |
| Dirt Racer | 2,060 | 1,999 (+13) | 61 | 21 / 12 / 28 | 184 | 1.70 % |
| Yoshi's Island | 305 | 283 (+2) | 14 | 8 / 3 / 3 | 6 | 1.65 % |
| Doom | 278 | 241 (+8) | 27 | 14 / 7 / 6 | 5 | 2.34 % |
| Star Fox 2 | 726 | 615 (+8) | 80 | 44 / 31 / 5 | 16 | 1.19 % |

(+n) are sites whose constant-propagated target set was incomplete, mostly
returns through R11 whose callers are not all visible statically.

| Game | PLOT | MULT class | GETB class | Loads and stores | Prefix opcodes | Need an engine helper | Top 20 PCs | PCs with more than one prefix state |
|---|---|---|---|---|---|---|---|---|
| Star Fox | 3.8 % | 1.8 % | 1.1 % | 13.3 % | 18.7 % | 21.6 % | 38.6 % | 3 of 8,149 |
| Stunt Race FX | 6.9 % | 1.5 % | 2.7 % | 9.4 % | 20.5 % | 23.9 % | 27.3 % | 8 of 23,047 |
| Vortex | 5.5 % | 1.1 % | 2.3 % | 8.6 % | 15.9 % | 20.4 % | 44.8 % | 3 of 11,558 |
| Dirt Trax FX | 8.9 % | 2.2 % | 3.6 % | 5.5 % | 23.2 % | 25.8 % | 23.4 % | 139 of 22,035 |
| Dirt Racer | 2.6 % | 0.4 % | 1.0 % | 15.2 % | 21.8 % | 20.3 % | 63.0 % | 79 of 18,232 |
| Yoshi's Island | 0.9 % | 0.4 % | 2.0 % | 10.9 % | 25.2 % | 16.7 % | 18.4 % | 15 of 5,573 |
| Doom | 5.8 % | 1.1 % | 3.0 % | 6.1 % | 33.2 % | 20.8 % | 13.2 % | 115 of 9,373 |
| Star Fox 2 | 3.9 % | 1.6 % | 2.4 % | 12.8 % | 20.0 % | 23.6 % | 32.8 % | 5 of 15,086 |

| Game | Master clocks per instruction | Fetched from the cache | Instructions per line fill | Executed under the PC's usual CBR | Sync calls under 8 instructions | GSU core share of host time (demo / play) |
|---|---|---|---|---|---|---|
| Star Fox | 3.07 | 87.6 % | 307 | 100.0 % | 93.9 % | 12 % / 12 % |
| Stunt Race FX | 2.91 | 83.3 % | 191 | 99.8 % | 94.5 % | 12 % / 14 % |
| Vortex | 1.8 | 92.7 % | 420 | 100.0 % | 88.8 % | 12 % / 7 % |
| Dirt Trax FX | 3.4 | 91.9 % | 672 | 99.9 % | 91.4 % | 21 % / 15 % |
| Dirt Racer | 1.78 | 93.4 % | 2982 | 99.2 % | 90.7 % | 25 % / 27 % |
| Yoshi's Island | 0.88 | 99.3 % | 324 | 100.0 % | 80.7 % | 9 % / 10 % |
| Doom | 2.2 | 99.8 % | 596 | 100.0 % | 92.7 % | 21 % / 19 % |
| Star Fox 2 | 2.48 | 90.6 % | 214 | 100.0 % | 93.0 % | 13 % / 9 % |

What the numbers say:

- **Entry points are few but not all in the job log.** 1 to 33 distinct
  PBR:R15 starts per game. Dirt Trax FX logs 2 starts but executes 4,215 STOPs:
  the 65816 resumes the GSU by setting SFR.G, which writes no R15 and so never
  reaches the engine's job log. Resume points are two bytes after a `STOP ; NOP`
  and can be found statically. A scan of each ROM for absolute stores to
  $301E finds only 1 to 8 per game and the entry address comes from tables, so
  the entries cannot be read off the 65816 code.
- **Static traversal alone is not enough, observation closes it.** From the
  entries alone it reaches 0 to 92 % of what ran; adding the observed targets of
  the 14 to 119 indirect sites per game that constant propagation cannot resolve
  (about half have a single target, up to 184 at a computed dispatch in Dirt
  Racer) reaches everything that ran. Those sites carry 0.5 to 3.1 % of taken
  transfers.
- **Delay slots need the pipeline model.** A multi-byte instruction in a delay
  slot takes its operand bytes from the path actually followed (`BEQ x ; IWT
  R15,#a` is a two-way dispatch), and a relative branch can sit in the slot of
  a computed jump (a jump table of BRAs in Dirt Racer). Both occur; without
  them the traversal missed up to 30 % of the executed code.
- **No Game Pak RAM code and no CPU-written cache lines** in 12,000 frames of
  any of the eight games, so the guard for them is a safety net, not a feature.
- **Prefix state is almost a function of the address**: 98.8 % to 99.97 % of
  PCs have a single prefix state (at most five), so keying code by (PC, state)
  grows it by under 2 % (1.0003 to 1.019 nodes per address).
- **Instruction mix**: 74 to 83 % of executed instructions are register
  arithmetic, prefixes, moves and branches that need no engine service; 17 to
  26 % need a buffer, pixel-cache, multiplier or cache helper. The top 20
  addresses are 13 to 63 % of all instructions (tight LOOP/PLOT and fill loops).
- **Cache**: 83 to 99.8 % of instructions come from the 512-byte cache, one
  line fill per 190 to 2,980 instructions, and 99.2 to 100 % of executions run
  under the most common CBR of their PC (0 to 10 % of PCs are met under several
  CBR values, Dirt Racer most).
- **The 65816 looks at the GSU all the time**: 81 to 94.5 % of the sync calls
  made while the GSU runs advance it by fewer than 8 instructions, 99.3 to 100 %
  by fewer than 32. Compiled code must be able to stop at any instruction and
  resume in the middle of a block.
- **The GSU core is 7 to 27 % of main-thread time** (a 2 kHz sampler on the
  same builds, 3,000 frames per route, attributed through the linker map; the
  sampler and eight parallel runs inflate absolute times). The PPU is 19 to 45 %
  and the bus and bridge code 33 to 53 %. Even an infinitely fast GSU would
  speed a whole frame up by 1.08 to 1.37 times; a four times faster one by 1.06
  to 1.25 times.

Revised estimate and recommendation. An exact native GSU is 25 to 35 working
days (it was 15 to 25): entry and target learning with a schema and bundled
snapshot (3-4), the instruction emitter with exact flags for about 110
instruction forms (6-8), cycle accounting with yielding at every instruction,
cache-line state and the ROM and RAM buffers (7-9, the engine's helpers are
file-static, so the game side must carry its own copies of about 300 lines),
a per-job checker and authored checks (4-6), and qualification on eight games
(5-8). Given that even an infinitely fast GSU saves only 7 to 27 % of frame
time, **do not build the emitter for speed**. Steps 1-5 first. If a native GSU share is wanted for the
fallback figures, build it in stages that each stand alone: (1) learn entries,
resume points and indirect targets as data (the dumps above are the
specification) and report them; (2) run the interpreter from a predecoded
(PC, state) table built by `snes_gsu.py`, which keeps every observable
identical and can be checked job by job; (3) only then emit C.

Design if the emitter is built:

- **Learning and storage.** Entries from the job log (public
  `superfx_job_log`), resume points found statically, indirect targets learned
  with a PC hook on the delay slot of each unresolved site (R15 holds the
  target there; the hook API is public). Records per ROM hash, as for the 65816
  variants, in the knowledge store and the bundled snapshot: 30 to 260
  (site, target) pairs per game for the unresolved sites, 1,520 in Dirt Racer.
  A pass regenerates code after learning, as today.
- **Guards.** Unknown entry or indirect target: leave the compiled code for the
  interpreter and record it. Compile only ROM views; Game Pak RAM and CPU-written
  cache lines (never seen) stay interpreted. Block preconditions: CBR equal to
  the learned value and all its lines valid, no pending ROM or RAM buffer, credit
  for the next instruction (an instruction starts only with at least 6 clocks of
  credit, as in the core). Anything else single-steps in the interpreter.
- **Shared helpers for exact cycles** (the 17 to 26 % above): GETB/GETC and any
  write to R14 (ROM buffer, 5 or 6 clocks, data read when the countdown ends),
  ROMB, LDW/LDB/LMS/LM/STW/STB/SBK/SMS/SM and RAMB (RAM buffer and its address
  and data latches), PLOT and RPIX (two pixel caches, flushed through the clock),
  MULT/UMULT/FMULT/LMULT (CFGR and CLSR timing), CACHE and LJMP (CBR and line
  flush), STOP (IRQ, job log). Everything else is pure register and flag work
  whose cost is a constant 1 or 2 master clocks per cached fetch.
- **Checks.** Per job: compiled against interpreter (registers, Game Pak RAM
  hash, stop clock). Per sync window in debug builds. `snes_gsu_survey.py`'s
  transition check stays as a regression test of the decoder.

### C. Title-level replacement (rejected)

Replacing a game's rendering with host code would be per-title, would not be
derived from the ROM and would hide the original computation. It contradicts
the project rule that cartridges are analyzed from their own ROM.

## Timing and synchronization

- One master clock drives the 65816, PPU, DMA and the GSU (10.74 MHz, or
  21.48 MHz with CLSR). The GSU is caught up lazily at each cartridge access
  and at frame boundaries; the 65816 typically polls SFR.G or waits for the
  GSU IRQ, then DMAs the bitmap to VRAM in vertical blank.
- MAME offset, measured on 26 October 2026 with instrumented build copies and
  MAME Lua taps (Doom, Dirt Trax FX), aligned by events rather than frame
  numbers. Four differences, MAME being the simpler model each time:
  1. DRAM refresh: the export charges 40 master clocks per scanline, MAME
     none (Doom: 8.7 of an 11.07-frame boot drift).
  2. DMA: the export stalls the CPU 8 clocks per byte, MAME charges nothing
     (Doom 2.15 frames, Dirt Trax FX 1.5 frames).
  3. GSU cost: the export follows the ares-derived costs (cache fills,
     ROM/RAM buffer waits, multiplier, PLOT/STW); MAME charges a flat 1
     (Doom, GSU-2) or 2 (Dirt Trax FX, GSU-1, CLSR ignored) clocks per
     instruction. Doom render jobs are 1.5-2.8 times longer in the export.
  4. Doom pacing: a new rendered frame every 5 video frames in the export,
     every 9 in MAME (3 of them blank or partial); not explained by 1-3 and
     still open.
  With refresh off, free DMA and a flat GSU in a build copy, Doom's first GSU
  job moves from 11.07 frames to 0.34 frame behind MAME, and Dirt Trax FX's
  first fade from 97 to 4 frames. The 65816 side agrees within 9 clocks over
  an 87.9 M-clock loader gap; the same GSU jobs run the same instruction
  counts in both. The shipped timing is left unchanged: it follows documented
  hardware behaviour, and no console measurement is available here.
- Frame pacing: the PPU only sees what the 65816 copied. A GSU job that ends
  a few lines late shows as a dropped or repeated game frame, not as tearing.
- PAL (Dirt Racer): the GSU counts master clocks, so it follows the PAL
  master clock the build uses; no PAL Super FX cartridge has been converted
  yet.

## Host cost (26 October 2026)

The exports were close to the frame budget (Vortex 16.2 ms of 16.64, Dirt Racer
over its 20 ms on a busy core). Same guest behaviour, less host work:

| Game (gameplay state, 3,000 frames) | Before | Source adaptations only | With the Windows profile build | Change |
|---|---|---|---|---|
| Vortex (USA), mission, authored input | 15.42 ms | 10.49 ms | **6.49 ms** | -58 % |
| Doom (USA), first level, `--play` | 11.73 ms | 10.44 ms | **6.20 ms** | -47 % |
| F-Zero (USA), race, `--play` (not Super FX, control) | 9.09 ms | 8.87 ms | **5.10 ms** | -44 % |

Windows 11, Ryzen 9 3900X, llvm-mingw, process pinned to one core (core 10), the
three builds run in turn three times, best of three (the spread is under 2 % except
Doom's, 6.2 to 6.7), process start and a 1.3 MB state load included. Gameplay is
a saved state: Vortex at frame 3,300 of an authored route (Start presses, then movement and
fire from the first mission), Doom and F-Zero at frame 1,500 of the `--play` route. This is host time, not a latency or fidelity
figure. Quiet machine; on a busy one every figure grows alike.

What changed, in the order of the gain:

1. **Windows build: ThinLTO and a clang profile** (`retrorecomp/console16_optimization.py`,
   Super Nintendo only; `RETRO_RECOMP_PGO=0` switches it off). The Linux build has been
   profile-guided for a while; Windows compiled the engine at `-O3` without cross-file
   inlining. The game is now built with clang's instrumentation, run for 1,800
   frames of the `--play` route (a 600-frame boot has not yet reached Doom's first level: half
   the gain), and rebuilt with ThinLTO and that profile for the engine's own sources, not
   the generated cartridge code. A failed training run builds without the profile. The
   conversion takes as long as before (F-Zero 95 to 108 s, Doom 154 to 168 s, Vortex 197 to 177 s, three
   at a time) because the validation runs on the faster executable.
2. **The 65816 side's GSU catch-up** (`retrorecomp/snes_chips.py`, `superfx()`,
   `superfx_header()`, `cart_header_sync()`). The catch-up is called after every bus phase
   (read, write, idle cycle, DMA byte: 96,000 times a frame in Vortex).
   In Vortex 49 % of the calls could not start an instruction (under six clocks of credit)
   and 41 % found the GSU stopped (Doom: 77 % and 16 %). Both are now inline and cost the
   same two stores or one division; the full function runs for the rest. `step_clocks` keeps its
   buffer-countdown handling out of line. The instruction ring (the engine's debug server
   reads it; Retro-Recomp games never start that server) is behind `RR_GSU_TRACE`.
3. **The line renderer** (`native/snes_ppu_cache.inc`): offset-per-tile (modes 2 and 4: Vortex)
   reads its two BG3 words once per 8-dot column and line instead of twice per dot;
   an ordinary background (no mosaic, hires, mode 7 or widescreen margin) is decoded once per line in
   runs of 8 dots, not once per dot and priority; window tests become a per-line mask; sprite and
   background priorities with no opaque dot in the line leave the first-hit walk.

Why the catch-up is exactly the same (and why more laziness was not worth it):

- **Banked credit.** `superfx_sync` starts an instruction only while the credit is at least 6.
  A call that leaves it under 6 makes exactly two stores (credit, clock). Same two stores, inline.
- **Stopped GSU.** With SFR.G clear and no ROM-buffer or RAM-store countdown in flight, every
  iteration of the loop calls `step_clocks(6)`, which only subtracts 6. k iterations leave
  `credit - 6k`, k = floor(credit / 6): the remainder of one division. The 2,000,000 iteration
  guard is kept (above 12,000,000 clocks of credit the loop runs as before).
- **Slicing invariance.** Whether the clock is sliced in 19,998-clock steps or in steps of 1 to 97
  clocks must not change anything: the authored checks now run every one of the 3,706 cases twice (large steps,
  random small steps) and compare the 696-byte architectural state, Game Pak RAM, master clock,
  credit and instruction count. 3,706 runs, 0 differences, NTSC and PAL.
- **Why a deferred (lazy) catch-up adds nothing.** It would have to flush before every
  access that can observe the GSU: `$3000-$32FF`, ROM and RAM views (their value depends on
  SFR.G and RON/RAN, which change when the GSU stops), the IRQ test (the frame driver and the bridge read
  `irq_pending` before every opcode when the I flag is clear), saves and reports. Vortex and
  Doom run the GSU with the IRQ unmasked in 100 % of the sync calls made while it runs (the counters:
  83 M of 144 M calls in Vortex, 118 M of 141 M in Doom, none with CFGR bit 7 set), so
  every opcode would flush; and the instructions executed are the same instructions. What was
  left to save was the call itself, which is what the inline paths remove.

Checks (before and after must match exactly):

- Frame, CPU, WRAM, VRAM, CGRAM, OAM, APU, DSP, PCM, SRAM, cycle and master-cycle hashes and
  `coprocessor_state_hash` / `coprocessor_instructions` of Vortex and Doom, demo and `--play`, 1,500 and
  3,000 frames, plus Vortex's authored 5,000-frame mission route: identical (every field of the
  report), and the per-frame frame and audio hashes of all of them. F-Zero the same.
- The Standard conversion's internal native/reference comparison matches for all three.
- Seven other Super Nintendo games converted with the old and the new pipeline (Super Mario World,
  Yoshi's Island, Star Fox, Chrono Trigger, Super Metroid, Axelay, Secret of Mana): the
  demo and `--play` routes of both executables are identical in every report field and per-frame hash.
- `tools/snes_superfx_selftest.py`: 3,706 cases, 407,036 assertions over NTSC and PAL, 0 mismatches
  (and 3 new mutations of the shortcuts, 10 older ones: all noticed).
- `tools/snes_ppu_cache_selftest.py`: 16.8 M pixel, 7.9 M resolved, 7.9 M line and 3.0 M
  widescreen-margin comparisons with the pinned per-dot walk, including sparse scenes, equal.

Where the time goes now (Vortex gameplay, sampler on the profile build): the 65816 interpreter
loop 22 %, the line renderer 19 %, the per-bus-phase charge of the beam, DMA and
HDMA 17 %, the bus read path 10 %, the GSU core 17 % (instruction 9 %, catch-up loop 8 %). The GSU is
no longer the margin problem: the next steps are the poll loops on SFR (the 65816 spends its
spare time reading `$3030`; an exact fast-forward needs the next event to be known) and
batching the bus-phase charge.

## Fidelity checks

1. **Authored GSU programs** (done, 26 October 2026): `native/snes_superfx_checks.c`
   drives the engine's GSU core as the S-CPU does (`$3000-$303F`, a synthetic
   Game Pak ROM, start by writing the high byte of R15, the shared master
   clock advanced with `superfx_sync`) in the NTSC and PAL builds, run by
   `tools/snes_superfx_selftest.py`. The expected values come from
   `tools/snes_superfx_model.py`, an independent model written from the
   fullsnes GSU chapter, not from `superfx.c` and not from GPL code; the few
   rules fullsnes leaves open (FMULT/LMULT carry) follow the ISC-licensed ares
   and are counted separately. Per build: 3,706 cases and 181,282 assertions
   over the ALU and flags, the multipliers, every prefix order and the B flag,
   immediate loads, all branches with their delay slot, JMP/LJMP/LOOP/LINK,
   the ROM buffer, RAM access and RAMB, PLOT/RPIX/COLOR/CMODE in 2/4/8 bpp and
   the 128/160/192/OBJ layouts, CACHE/CBR and the S-CPU window on the code
   cache, code from the cold cache, from a cache preloaded by the S-CPU, from
   ROM and from Game Pak RAM, STOP/IRQ/restart, aborting a job through SFR and
   800 seeded random programs; 1,121 save/load runs resume a job mid-flight in
   a second core and step both in lock step. Timing: exact totals only where
   fullsnes states the price (129 programs at CLSR 0 and 1: one clock per
   cached opcode byte, 3 or 5 per ROM read, multiplier extras by CFGR bit 5)
   plus 52 range checks (GETB, stores, PLOT, RPIX); 69 totals with the cold
   cache fill are **self-consistency only**, fullsnes gives no figure for them.
   `tools/snes_superfx_mutations.py` plants defects one at a time in the staged
   copy of `superfx.c`: 65 of 66 are noticed (the survivor, a PBR write that no longer empties the
   cache, is not stated by fullsnes). The suite found one defect
   (the S-CPU view of the code cache whenever CBR is not a multiple of 100h,
   fixed in `retrorecomp/snes_chips.py`) and records eight differences between
   fullsnes and the core that are not changed because the hardware answer is
   unknown (IRQ flag with the mask set, CACHE with an unchanged CBR, 2 bpp
   transparency, POR high-nibble, FMULT into R4, GETBH/GETBL source of the
   other byte, RAM load clocks and back-to-back STW, pixels pending at STOP).
   A second defect, found in Dirt Racer (27 October 2026), is also fixed in
   `retrorecomp/snes_chips.py`: the core ignored SCMR RON/RAN for the GSU's own
   accesses. fullsnes: with the bit at 0 the S-CPU owns that Game Pak bus and
   the GSU "enters WAIT status" when it accesses it, going on when the bit is 1
   again. Dirt Racer clears RAN, writes its display list into Game Pak RAM from
   the 65816 while its GSU command loop is still running, then sets RAN; a GSU
   that kept running read the list ahead of the writer and took a text
   character for a command, so the "Practice" panel never opened. The core
   cannot suspend inside an instruction, so the wait is taken before the
   instruction starts (`gsu_bus_wait`); `bus_ownership_checks` in
   `native/snes_superfx_checks.c` covers the RAM hand-off and the ROM fetch.
2. **Internal reference** (already active): the native run is compared with
   `RR_SNES_FORCE_INTERP=1`, including the GSU state hash. It proves the native
   65816 matches the 65816 interpreter with the same GSU, not GSU fidelity.
3. **Per-job comparison** once option B exists: compiled GSU against the
   interpreter for each job (registers, RAM hash, stop clock).
4. **Independent frames**: MAME as a black-box reference, with the same input
   scripts, compared on game states and event order (title, menu, first
   level). Exact frame alignment is not a target: MAME's simplified refresh,
   DMA and GSU costs explain the offsets. A frame tool like the CPS-1 one (`.build/cps1-*`)
   can be reused.
5. **Gameplay routes** with states and battery saves (Yoshi's Island, Stunt
   Race FX, Star Fox 2), ordinary and packed exports, as for DSP-1/CX4.

## Fallback percentage

**Done (26 October 2026).** In a Super FX game, GSU instructions are 100 %
interpreted and dwarf the 65816 count: one combined percentage would always
say "almost all interpreted". The three figures are now separate, for the
GSU and equally for the CX4 and DSP-1:

- 65816: `native_percentage` is computed from main-CPU counts only
  (`native_entries` against `main_interpreted_opcodes`); `interpreted_opcodes`
  in each check is now the 65816 count alone;
- SPC700: `audio_native_percentage` and the audio counters, as before;
- cartridge device: a `cartridge_device` entry of the report with the chip
  (`superfx`, `cx4`, `dsp1`), its mode (`interpreted`, or `command_model` for
  the firmware-free DSP-1), `counter_unit: "device instructions"`, and per
  scenario `interpreted_instructions`, `interpreted_per_frame` and
  `commands`. The raw per-check fields (`coprocessor_instructions` and the
  others) stay in `final_checks`, and the conversion log keeps its line
  `SUPERFX: N counted interpreted device instructions.`

Device interpretation is never hidden, only shown on its own line: the game
details in the interface add "Cartridge chip SUPERFX: N interpreted device
instructions (M per frame)" in the eight interface languages, the compiled-games
view still flags the game as having fallback, the running game's window title
reads "Cartridge chip interpreted" when only the device is interpreted, and
problem reports carry `cartridge_device`. Reports written earlier fold the
device into the combined counter; readers use `main_interpreted_opcodes` when
present and derive the device entry from the checks, so they still work.

With option B the device line would become a native share of GSU instructions,
with Game Pak RAM code and CPU-written cache lines counted as interpreted.
No zero-fallback claim is made for Super FX games, as for the CX4.

## Qualification gates (26 October 2026)

Three converter changes close gaps found by the extended qualification (D1, D5, D7):

- **Activity gate** (`supernintendo.validate_device_liveness`, run after each pass and
  before the reference replays). For a cartridge with a counted interpreted device (Super
  FX, CX4) the probe report now carries three liveness frames: `last_picture_change_frame`
  (`native/console16_main.c`), `last_device_frame` and `last_audible_frame`
  (`native/snes_backend.c`). A scenario of 1,200 frames or more is refused when, for its
  last `max(600, frames / 4)` frames, the picture did not change AND the device executed no
  instruction AND no sample was audible; absent or malformed evidence is refused too. A
  static screen that keeps its music, or a silent one where the device or the picture still
  moves, passes; ordinary cartridges and DSP-1 are not checked. The Star Fox 2 Japanese
  prototype (controller notice from frame ~60, GSU count frozen at 770,961) is now refused
  at the Standard level: "stopped doing anything ... after frame 46 of 1,200".
- **Packing record**. `conversion-report.json` has a `packing` entry (packer, version,
  level, whether the published file carries the UPX header, size and SHA-256 before and
  after, `compared_on: unpacked build executable`). The conversion still compares
  native and reference on the unpacked build. `tools/snes_packed_check.py` is the developer
  tool for the packed qualification of one published game: it replays the report's own
  scenarios (demo, play, random and authored routes, regenerated from the ROM identity and
  checked against the report) on the published executable, native against
  `RR_SNES_FORCE_INTERP=1`, applies the activity gate, then runs the fresh-process state
  check, and writes `packed-validation.json`. It is not part of a conversion (it replays
  every scenario twice more).
- **Authored gameplay routes** (`retrorecomp/snes_routes.py`). The random extended route
  stays in the menus of some Super FX games, so a conversion at the Extended level and above
  also replays one authored route (scenario `authored`) when the exact ROM SHA-256 is in
  the table: Star Fox, Star Fox 2 (USA), Stunt Race FX, Yoshi's Island, Vortex and Dirt Racer
  (6,000 to 12,000 frames). A route is host input only (`frame p1 p2` masks, repeated blocks
  stored compactly; no ROM bytes); the report records it under
  `advanced_scan.authored_routes` with its script hash. It shows that inputs reach the game
  state named in `reaches`; it says nothing about correct gameplay. More games add one entry.

Measured on 26 October 2026 (the engine of this branch; native runs only, six cartridges, 24
extended-length runs: demo 12,000, play 1,200, random route 18,000 and the authored route): in
every run the picture, the GSU and the sound were all still active in the last frames (the
gate's quiet tail was 0 of a 600 to 4,500-frame allowance), and the prototype was refused. Stunt
Race FX shows why all three must stop: its GSU is idle after frame 246 on the title screen,
but the picture and the music go on, so it passes. The authored routes reach (pictures taken at
the frames named in `reaches`): Corneria flight (Star Fox), map and wire-frame battles (Star Fox 2),
a Speed Trax race (Stunt Race FX), level 1-1 (Yoshi's Island), the first mission (Vortex) and a
race (Dirt Racer). A full Extended conversion of Stunt Race FX with the new scenario took
2 passes and 1,832 s (empty private library, machine loaded): 0 interpreted 65816 and SPC700
opcodes in the last pass on all four scenarios, native and reference matching, the report
carrying `advanced_scan.authored_routes` and `packing` (14,068,736 bytes unpacked, 3,136,512
packed, ratio 0.2229). `tools/snes_packed_check.py` on that published executable: UPX header
present, SHA-256 equal to the recorded one, 37,200 native/reference frame pairs identical (the
four scenarios match the conversion's own hashes), 0 interpreted 65816/SPC700 opcodes, state
saved at 7,800 and resumed for 180 frames in a fresh process matching, 8 corrupt state files
rejected, 1,002 s.

## Licences

| Source | Licence | Use |
|---|---|---|
| snesrecomp (pinned engine, `superfx.c`) | PolyForm Noncommercial 1.0.0, with retained MIT/ISC notices | already the SNES engine of every export ([notices](../licenses/snesrecomp.md)) |
| ares (origin of the GSU semantics) | ISC | permissive; may be consulted for semantics |
| fullsnes (nocash) | documentation | consulted for maps and registers; expected values for authored checks; instruction semantics of `snes_gsu.py` |
| MAME 0.289 | GPL-2.0+ as a whole, per-file BSD-3 or GPL | run as a separate black-box binary only; no code copied |
| bsnes/higan, Mesen2 | GPL-3.0 | not consulted, no code copied |
| Snes9x | non-commercial licence | not used for Super FX |

## Plan and estimate

Estimates are working days for one developer with the existing tools; ranges
reflect unknown integration bugs.

| Step | Work | Estimate |
|---|---|---|
| 0 | Recognition, counted interpreter path, experimental label, spike on Doom and Dirt Trax FX (this branch) | done |
| 1 | Standard-level conversions of all eight local cartridges (done 26 October, see above); still to do: packed exports, battery save round trips, long routes with inputs that reach gameplay, fix what breaks | 3-6 |
| 2 | Separate 65816 / SPC700 / GSU figures in report, log and interface | done |
| 3 | Timing investigation against MAME (done 26 October: offsets explained by MAME's simplifications; Doom 5- vs 9-frame pacing still open) | done |
| 4 | Authored GSU checks in `native/snes_superfx_checks.c` (see Fidelity checks) | done |
| 5 | Qualification campaign and documentation as for DSP-1/CX4; decision to drop "experimental" | 3-5 |
| 6a | Option B groundwork: GSU decoder, static traversal, survey tool and the measurements above | done (26 October) |
| 6b | Option B remainder: learning records, C emitter with cycle accounting and yielding, guards, per-job checker (staged as under "Option B: measured") | 25-35 (was 15-25 for all of step 6); not recommended for speed |

Steps 1-5 (about 3 to 5 weeks) give released, measured Super FX support with
an interpreted GSU. Step 6b is optional and can follow later.

A real implementation touches, beyond the slice: `retrorecomp/console16.py` and the report/interface code
for separate figures, `retrorecomp/knowledge.py` and the bundled snapshot
schema if GSU entry points are learned, and, for the rest of option B,
`native/snes_gsu_*.inc` beside the existing `retrorecomp/snes_gsu.py`. All are
game-side and change the SNES fingerprint again.
