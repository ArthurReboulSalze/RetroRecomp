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
  frame-aligned**; timing is the first open question.
- Native recompilation of GSU code is possible in principle (the code is in
  ROM) but is a separate multi-week project; the interpreter stays the
  measured fallback and remains visible.

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
  to the cartridge and at the beam frame driver's boundaries; the GSU IRQ is
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
| `retrorecomp/console16.py` | conversion log line naming the counted GSU interpreter |
| `native/snes_backend.c` | GSU instructions join the visible interpreted counter; report fields `cartridge_chip=superfx`, `coprocessor_mode=interpreted`, GSU state hash |
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
- The report's single `native_percentage` mixes 65816 and GSU counts
  (Dirt Trax FX 0.6 %, Doom 14-27 %). That is honest but unreadable; see
  "Fallback percentage" below.
- Quick states: saving at frame 1,500 and resuming for 300 frames gives the
  same frame, CPU, WRAM, VRAM, GSU-state, Game Pak RAM and APU RAM hashes as
  an uninterrupted 1,800-frame run, for both games. (The PCM hash is
  cumulative per process and is not comparable this way.)
- MAME 0.289 (`.build/tools`, used as a black-box binary, headless, no window)
  at screen frames 600, 1,500 and 3,000: Doom shows the same title and the same
  first room at 1,500, but at 3,000 MAME is on a black transition while the
  export still shows the room. Dirt Trax FX shows the same title, menu and race
  demo, but fades are offset and the race positions differ at 3,000. Content
  agrees; **timing does not**, and neither side is ground truth yet. MAME
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
  has a 20 ms frame. GSU cost is the main factor; it is the strongest argument
  for option B.
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

Benefit: host speed (the interpreted GSU fits in a frame on this PC, but
Vortex already takes about 16 ms of a 16.7 ms NTSC frame) and a growing native
share. Cost: a second recompiler with its own
guards, learning records and checks. Do it only after A is qualified.

### C. Title-level replacement (rejected)

Replacing a game's rendering with host code would be per-title, would not be
derived from the ROM and would hide the original computation. It contradicts
the project rule that cartridges are analyzed from their own ROM.

## Timing and synchronization

- One master clock drives the 65816, PPU, DMA and the GSU (10.74 MHz, or
  21.48 MHz with CLSR). The GSU is caught up lazily at each cartridge access
  and at frame boundaries; the 65816 typically polls SFR.G or waits for the
  GSU IRQ, then DMAs the bitmap to VRAM in vertical blank.
- What to check first, given the MAME offset: start-up delay before the first
  frame, GSU cost per instruction (cache, ROM buffer, multiplier, CLSR),
  65816 wait loops on SFR (whether parked polling advances time exactly),
  and DMA timing from Game Pak RAM through Retro-Recomp's per-byte DMA model.
  The engine's job log (start/stop master clocks per GSU job) separates a
  slow GSU from a late 65816.
- Frame pacing: the PPU only sees what the 65816 copied. A GSU job that ends
  a few lines late shows as a dropped or repeated game frame, not as tearing.
- PAL (Dirt Racer): the GSU counts master clocks, so it follows the PAL
  master clock the build uses; no PAL Super FX cartridge has been converted
  yet.

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
2. **Internal reference** (already active): the native run is compared with
   `RR_SNES_FORCE_INTERP=1`, including the GSU state hash. It proves the native
   65816 matches the 65816 interpreter with the same GSU, not GSU fidelity.
3. **Per-job comparison** once option B exists: compiled GSU against the
   interpreter for each job (registers, RAM hash, stop clock).
4. **Independent frames**: MAME as a black-box reference, with the same input
   scripts, compared on game states (title, menu, first level) rather than
   exact frame numbers until the timing offset is understood; then frame
   alignment as a target. A frame tool like the CPS-1 one (`.build/cps1-*`)
   can be reused.
5. **Gameplay routes** with states and battery saves (Yoshi's Island, Stunt
   Race FX, Star Fox 2), ordinary and packed exports, as for DSP-1/CX4.

## Fallback percentage

Today, in a Super FX game, GSU instructions are 100 % interpreted and dwarf
the 65816 count: one combined percentage would always say "almost all
interpreted". Reports and the interface should show three separate figures:

- 65816: native share (expected near the ordinary SNES level after Standard
  passes, to be measured);
- SPC700: native share (as today);
- GSU: interpreted instructions per frame, then, with option B, the native
  share of GSU instructions, with Game Pak RAM code and CPU-written cache
  lines counted as interpreted.

No zero-fallback claim is made for Super FX games, as for the CX4.

## Licences

| Source | Licence | Use |
|---|---|---|
| snesrecomp (pinned engine, `superfx.c`) | PolyForm Noncommercial 1.0.0, with retained MIT/ISC notices | already the SNES engine of every export ([notices](../licenses/snesrecomp.md)) |
| ares (origin of the GSU semantics) | ISC | permissive; may be consulted for semantics |
| fullsnes (nocash) | documentation | consulted for maps and registers; expected values for authored checks |
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
| 2 | Separate 65816 / SPC700 / GSU figures in report, log and interface | 1-2 |
| 3 | Timing investigation against MAME with the job log; frame-alignment tool | 3-6 |
| 4 | Authored GSU checks in `native/snes_superfx_checks.c` (done, see Fidelity checks) | 2-4 |
| 5 | Qualification campaign and documentation as for DSP-1/CX4; decision to drop "experimental" | 3-5 |
| 6 | Option B: GSU decoder, discovery from job starts and static traversal, C emitter with cycle accounting, guards, learning records, per-job checker | 15-25 |

Steps 1-5 (about 3 to 5 weeks) give released, measured Super FX support with
an interpreted GSU. Step 6 is optional and can follow later.

A real implementation touches, beyond the slice: `retrorecomp/console16.py` and the report/interface code
for separate figures, `retrorecomp/knowledge.py` and the bundled snapshot
schema if GSU entry points are learned, and new `retrorecomp/snes_gsu.py` /
`native/snes_gsu_*.inc` for option B. All are game-side and change the SNES
fingerprint again.
