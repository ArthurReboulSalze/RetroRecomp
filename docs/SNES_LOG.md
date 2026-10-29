# Super Nintendo: development log

The dated journal of the Super Nintendo profile, moved out of [SNES.md](SNES.md)
so that page can stay a reference. Entries are kept as they were written, with
their counts and their status at the time: where an entry says the profile is
"experimental", that was true on its date, and the status line of
[SNES.md](SNES.md) is the current one. The measures stay separate in every entry
(native code, CPU fidelity, hardware fidelity, gameplay validation, physical
latency); no entry claims exact hardware behaviour or zero latency.

Two parts:

- **Part 1** is the former text of `SNES.md`, section by section, in its original
  order (October 2026).
- **Part 2** is the Super Nintendo text that used to live in
  `CONSOLES_16BIT.md` (releases up to 1.4.1), moved here when that page was
  reduced to what the 16-bit family shares. Paragraphs that also mention the
  Mega Drive are kept whole.

- [Part 1: the former text of SNES.md](#part-1-the-former-text-of-snesmd)
  - [Scope paragraph of the former page](#scope-paragraph-of-the-former-page)
  - [DSP-1/CX4 qualification and release 1.0.0](#dsp-1cx4-qualification-and-release-100)
  - [Standard profile and live RAM operands, 13 October 2026](#standard-profile-and-live-ram-operands-13-october-2026)
  - [Object progression and cartridge decoding, 13 October 2026](#object-progression-and-cartridge-decoding-13-october-2026)
  - [Raster IRQ preemption inside NMI](#raster-irq-preemption-inside-nmi)
  - [HDMA while the CPU is parked (Donkey Kong Country palettes)](#hdma-while-the-cpu-is-parked-donkey-kong-country-palettes)
  - [Camera projection and first HDMA line](#camera-projection-and-first-hdma-line)
  - [Earlier PPU/DMA and enhancement-circuit follow-up](#earlier-ppudma-and-enhancement-circuit-follow-up)
  - [Cartridge saves and guarded RAM follow-up](#cartridge-saves-and-guarded-ram-follow-up)
  - [Audio and display follow-up after 0.26.0](#audio-and-display-follow-up-after-0260)
  - [Evidence boundaries](#evidence-boundaries)
  - [CPU, DMA and HDMA arbitration follow-up](#cpu-dma-and-hdma-arbitration-follow-up)
  - [Fine CPU bus phases and PPU collisions](#fine-cpu-bus-phases-and-ppu-collisions)
  - [Manual joypad strobe (Star Fox 2 Japan prototype)](#manual-joypad-strobe-star-fox-2-japan-prototype)
- [Part 2: Super Nintendo text from the former CONSOLES_16BIT.md](#part-2-super-nintendo-text-from-the-former-consoles_16bitmd)
  - [Scope statements of releases 0.24.0 and 0.25.0](#scope-statements-of-releases-0240-and-0250)
  - [Earlier regression examples (Super Nintendo rows)](#earlier-regression-examples-super-nintendo-rows)
  - [Files recognised, headers and titles](#files-recognised-headers-and-titles)
  - [PAL timing, first stage](#pal-timing-first-stage)
  - [Controls, quick states and saves in the shared interface text](#controls-quick-states-and-saves-in-the-shared-interface-text)
  - [The 65816 adapter and the interpreted-opcode counters](#the-65816-adapter-and-the-interpreted-opcode-counters)
  - [Scan scenarios, as the former text counted them](#scan-scenarios-as-the-former-text-counted-them)
  - [SPC700 sound-program recompilation](#spc700-sound-program-recompilation)
  - [65816 and shared comparison limits](#65816-and-shared-comparison-limits)
  - [Expanded qualification after 0.21.0](#expanded-qualification-after-0210)
  - [Build and dependency contract](#build-and-dependency-contract)

## Part 1: the former text of SNES.md

The sections below are the former `SNES.md`, unchanged and in order. Each is a dated stage.


### Scope paragraph of the former page

The opening of the former page, before the stage sections (the current status is in [SNES.md](SNES.md)).

The **Super Nintendo standard-cartridge profile is supported**: ordinary
LoROM/HiROM up to 4 MiB, PAL/NTSC, shared controls, Super Scope, cartridge saves
and F8/F9. Qualified DSP-1, CX4 and Super FX (GSU) boards are supported too. CX4
and GSU device instructions remain interpreted and counted; this is separate from
native 65816/SPC700 coverage (Super FX: [SNES_SUPERFX.md](SNES_SUPERFX.md)). Other enhancement circuits, extended mapping and DSP-1
firmware-dump commands remain unsupported. New cartridges are analyzed from
their own ROM, rather than selected from an allowlist.

### DSP-1/CX4 qualification and release 1.0.0

Eight exact enhanced cartridges compare **57,600 ordinary frame pairs** and
**105,600 pairs in actual packed exports**. Four extended device routes add
**36,000 pairs**; a separately confirmed two-controller race adds **9,000 pairs** and a further state check. Their 65816 and SPC700 work has zero observed fallback on
those routes. CX4 instructions stay interpreted and are reported on their own
device line (`cartridge_device`, apart from the 65816 percentage; see
[SNES_SUPERFX.md](SNES_SUPERFX.md), "Fallback percentage"); no
zero-total-fallback claim is made for CX4 games.

DSP-1 command aliases, polar rotation, range-plus-one and memory-test/size
operations now work through the firmware-free model. Unassigned command bytes
return to idle instead of stopping a cartridge; recognized firmware-dump
commands remain a clear validation error. An authored guest independently
checks 60 result bytes against [Snes9x DSP-1](https://github.com/snes9xgit/snes9x/blob/master/dsp1.cpp),
including rotation aliases and a valid multiplication after unassigned commands.
All 256 DSP-1 byte signatures are bounded by an explicit command decode rather
than a title exception. Timing is command modelling, not electrical accuracy.

The real-engine PAL/NTSC suite passes **96,252 assertions** for DSP arithmetic,
board ports, aliases and device continuation, including 768 authored CX4 ALU
cases per region resumed from suspended state. CX4 retains its existing guarded
clock/cache/state integration and synthesized constants; no firmware file is
loaded or distributed. The eight initial packed exports retain their 0.27.0 build label; only the converter version changes to 1.0.0, with guest execution sources unchanged. Final frozen builds validate 1.0.0. No claim of complete HG51B instruction fidelity follows
from these arithmetic cases.

Eight packed exports pass states at frame 5,400; four extended routes pass states
at frame 7,800. Two builds from the final one-file converter use an initially
empty private library and the bundled snapshot, then pass their varied routes
and fresh-process states. Across these checks: **15 states, 2,280 resumed frames,
120 corrupt-file rejections**. Python: **373 passed / 374 total**, one platform
skip. The initial Mario Kart long route stays at character selection; it is not race evidence. A separate replay confirms player two, reaches racing, exercises over 130,000 DSP commands and passes another state. Compatibility is sampled gameplay, not complete playthroughs.

The converter embeds **1,027 exact cartridge records / 44 SNES**,
**51,025,629 raw / 14,207,965 gzip bytes**, SHA-256 `a5b85b347b0512a54bb3a1c75ed3a549544a828ff9208780b5a50bfd50a5029b`.
SPC range references losslessly group consecutive PCs pointing to the same ROM
opcode. The old snapshot's entire guarded set is preserved; no raw RAM, game
assets, firmware or private journal is added, and the 64 MiB raw bound remains.
Every new observation still needs successful ordinary and packed qualification.

Evidence: `.build/snes-chip-final-20261013/final`, delivery, active-device,
knowledge, frozen-converter and package audit receipts. Earlier standard-profile
hardware evidence below remains separate. Independent full CPU/hardware fidelity
and physical latency are not claimed; finer phases and other enhancement chips
remain follow-up work. Older incompatible quick states are rejected intact.

### Standard profile and live RAM operands, 13 October 2026

Eight additional exact cartridges and a Super Scope control are requalified
with the final runtime. Their ordinary conversions compare **64,800 frames**;
their actual packed exports compare **181,200 frames** across demo, play, varied,
active-control and extended routes. Another **90,000 long-route frames** retain
the earlier evidence for five no-RAM selectors: generated C is byte-identical,
CPU adaptation/operation bodies and hardware sources are unchanged. Every new
export still has its own fresh-process state check. Three RAM-bearing games
rerun their 18,000-frame comparisons and later states with the new guards.
Zero 65816/SPC700 fallback is observed on the qualified routes.

The former RAM guard required four identical bytes, even though native operation
bodies read operands and M/X widths live. Changed parameters unnecessarily
triggered fallback, and dynamic literals could not be shared as ROM references.
Guards now retain the observed exact PC and opcode, check the current timed
fetch, and restrict inspection to the existing ordinary RAM window. Unknown
PCs/opcodes, changed ROM bytes and MMIO retain counted fallback. Numeric
`ram_opcode_refs` reconstruct only the opcode from the user's exact ROM;
no private instruction window or operand dump is bundled.

The native fixture passes **33,102 CPU/state/bus comparisons** in both mappings,
including M/X modes, changed operands, opcode/fetch mutation and 8,192 guarded
positions. Four authored PAL/NTSC SRAM guests retain just one literal per
PC/opcode, execute changed operands natively, preserve their cartridge counter
across processes, and pass states/corrupt-file rejection. Pure Python:
**372 passed / 373 total**, one platform skip. Earlier independent OBJ,
palette, IRQ/open-bus fixtures remain distinct hardware evidence.

The current nine exports pass twelve fresh-process states, 1,920 resumed frames
and 96 malformed-file rejections. The final one-file converter separately builds
Biker Mice and PAL Asterix with initially empty private libraries and its bundled
snapshot, then checks their varied routes and two more guided states. The
verified bank has **1,023 exact ROMs / 40 SNES**, **58,832,410 raw /
15,035,601 gzip bytes**. Nine records are refreshed; 31 other SNES
and every other console record are preserved. Runtime learning in games stays off.

Native coverage, internal CPU/state agreement, independent hardware checks,
reviewed gameplay and physical latency are separate. Retail captures are
qualitative reviews; boot/input polling and gameplay progression can differ
from Snes9x. Some paths cover menus, inventory or attract sequences, rather than
complete missions or playthroughs. Instruction-internal/parked-CPU phases,
disputed OAM collisions and sub-dot transitions remain known refinement work,
not a claim of electrical-exact hardware or measured physical latency.

Evidence: `.build/snes-live-ram-qualification-20261013`, including `delivery.json`,
`extended.json`, `unchanged-long-routes.json`, `scope-control.json`,
`standard-qualification.json`, `knowledge-build.json`, `frozen-results.json`
and `installed.json`. The earlier expanded folder keeps diagnostic/pre-guard
work. Only the final folder qualifies the new RAM guards and installed package.

The following sections retain the preceding hardware work and its historical
counts/status; the current standard-profile scope is defined above.

### Object progression and cartridge decoding, 13 October 2026

Forced blank now consumes its actual OBJ evaluation slots. Unblanking halfway
through a line must not evaluate earlier sprites retroactively. HBlank fetch
uses a persistent cursor: an object's starting X/width, completed tile slots
and skipped blank slots cannot be recomputed from later OAM or size-register
writes. Repeated synchronization at H=0 is idempotent. The cursor belongs to
architectural PPU state, is preserved by raster replay and is included in
F8/F9; incompatible older runtime signatures are rejected.
Original fixtures cover every unblanking position across 1,024 clocks, changes
during fetch, span batching and continuation from a copied architectural state.
The full PAL/NTSC PPU suite now passes 62,252 assertions. The phase contract is
checked against [ares OBJ evaluation/fetch](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/object.cpp).
This does not resolve the separate ares/bsnes OAM-address disagreement.

OBJ size modes 6/7 now render their rectangular heights, including vertical
flip within each square half. The former square-only renderer clipped the
lower half or selected the wrong tile rows. Four original complete images
cover small/large objects, both flips and PAL/NTSC: all 229,376 pixels agree
with independent Snes9x. The normal ROM-free video/APU suite passes 2,770
assertions; `tools/snes_object_selftest.py` retains the authored image goldens.
Mid-line fetching improvements concern port timing; the pixel renderer still
does not model every sub-dot palette/OAM transition.

A wider cartridge selection also exposed a real HiROM failure: Street Fighter
II Turbo reads `$30:6002` without installed SRAM. The CPU fast path incorrectly
treated that undriven read as a bad ROM pointer and stopped at frame 2,322.
Decoded cartridge holes now return the CPU data latch. Word reads use two
decoded byte accesses and preserve bank wrapping rather than reading adjacent
host-ROM bytes. The actual engine fixtures cover all 256 MDR values in four
bank aliases, LoROM/HiROM and ROM/WRAM boundaries: 78,520 bus assertions pass.
Two authored PAL/NTSC guest programs independently match current bsnes on
12 defined result bytes each. Snes9x supplies phantom SRAM bytes on this
zero-RAM fixture; that reference disagreement is recorded rather than used
to change the cartridge's declared hardware.

Contra III revealed another independent issue: its original title overruns
the 21-byte field into the map byte. Nonstandard mapping recovery requires
ordinary hardware, one unambiguous header, an exact power-of-two declared
size, a matching **complete image checksum** and a plausible mapped reset
instruction. Special maps, custom circuits, inconsistent sizes and corrupt
images stay rejected. The loader uses the converter's validated unheadered
mapping; no ROM byte is changed. Original synthetic tests cover both mappings
and the rejection cases. No game-name allowlist or foreign profile is added.

Qualification is deliberately split into native coverage, internal CPU/state
agreement, independent authored hardware checks, sampled gameplay and physical
latency. The standard-cartridge profile can eventually graduate within its
documented scope; unsupported enhancement chips and unmeasured electrical
perfection are separate future work. Known blocking regressions, incomplete
routes and failing fresh-process saves still prevent qualification. The
bounded campaign for this block uses eight additional games and six established
controls, with up to eight concurrent conversions, rather than the whole ROM
collection. The final receipts live under
`.build/snes-object-qualification-final-20261013`.

### Raster IRQ preemption inside NMI

The wider visual review found a hardware bug that internal native/reference
agreement could not detect. Axelay's layers stayed disabled until roughly
line 141. Its NMI handler executes CLI and expects raster IRQs at lines 32/36
to interrupt its remaining work. The bridge formerly waited for the handler's
RTI before handing a pending IRQ to the beam scheduler. The background was
therefore missing despite zero CPU fallback and an internally matching frame.

An armed interrupt-handler run now yields on a pending unmasked IRQ between
instructions. The scheduler keeps the suspended PC and the actual guest stack,
pushes the nested IRQ frame and resumes through architectural RTI. IRQ code is
not skipped, and a host shortcut does not substitute for the restored PC.
The corrected trace takes the two IRQs at lines 32/36 and restores the game's
background. Axelay's scene uses line scrolling rather than Mode 7; the original
diagnostic hypothesis was corrected using its live mode/register trace.

Two original PAL/NTSC fixtures make NMI unmask IRQ and wait for a flag written
by the nested handler. The old bridge remains trapped at `$8114`; the corrected
bridge returns to the main WAI. Independent Snes9x completes 39 NMI and 39
nested IRQ handshakes in each 40-field run. The scheduler suite now has eleven
fixtures. This qualifies the specified preemption/resume behavior, not every
instruction-internal sampling phase or all hardware fidelity.
An early automated input route in Axelay is naturally silent in Snes9x too;
the qualification adds a later start that exercises audible gameplay. Silence
in a menu is not hidden by injecting sound or weakening an active route check.

Final source, compressed exports, fresh-process states and bundled knowledge
are requalified together under `.build/snes-nested-irq-qualification-20261013`.
The preceding two directories keep the diagnostic results, including the
internally matching but visually incorrect preemption baseline. Those receipts
must not be presented as the final hardware qualification.

The 12 October bus/PPU follow-up compared six exact cartridges on packed routes:
**85,200 native/reference frame pairs**, with zero 65816/SPC700 fallback,
no observation overflow and no numeric PCM underflow/drop. CX4 work stays
interpreted and visible. Twelve fresh-process F8/F9 continuations compare
2,160 resumed frames and reject 96 invalid states. Pilotwings now completes
its formerly blocked attract route. A further Mario Kart script reaches a
short race rather than stopping at the character menu. Three ordinary controls
retain PAL/NTSC, audio and display checks. These are sampled paths, not complete
playthroughs or physical latency measurements.
The CPU/state/frame/PCM comparison uses the internal reference path with shared
semantics. Independent DSP math and authored video checks are separate evidence;
these results do not establish exact overall CPU or hardware fidelity.

ROM-free checks pass 369 of 370 Python tests (one non-Windows branch skipped),
38,126 DMA/PPU assertions, 58,154 PPU-port assertions, 9,726 bus/interrupt
assertions, 25,988 device assertions across PAL and NTSC, and 802 video assertions.
The scheduler regressions also pass. Independent camera
outputs and complete authored HDMA images are covered below. That shared
resource had 1,009 exact ROM records, including 26 SNES records. Full
65816/SPC700 coverage on these routes does not make the CX4 device native.
That one-file converter also rebuilt Pilotwings and Mario Kart with initially
empty private libraries, passes two 2,400-frame native/reference comparisons,
and resumes fresh-process states after 2,100 frames. Cached dependencies are
reused; this verifies sharing of exact-ROM hints, not cold-toolchain speed.

### HDMA while the CPU is parked (Donkey Kong Country palettes)

HDMA requested at h=1104 during the CPU's last bus cycles waits for the CPU's
next bus edge. When that instruction parked the CPU on `WAI` (DKC's main loop
at `$80:80F5`), no edge followed, and the frame driver walked parked time on
to the next scanline's refresh (h=538) before servicing it. DKC's two HDMA
channels then wrote colours 0 and 1 mid-line; the CGRAM bus model correctly
redirected those writes to the colour being fetched, so jungle background
palettes drifted towards light tiles over time. A parked CPU has no next edge:
`rr_snes_parked_hdma()` (`native/snes_bus.inc`) now gives the bus to HDMA where
the beam stands, before `advance_parked` and before the frame driver pays beam
debt. Running CPUs keep the edge handshake.

Evidence: a 5,000-frame DKC route had mid-line CGRAM redirections at frames
2919, 3434, 4107, 4183 and 4934, none after the change; video is identical up
to frame 2919, and audio differs only by a few cycles of APU phase (same sample
count and peak). The HDMA, DMA, bus, PPU-bus and scheduler checks pass; DKC
converts with 0 interpreted opcodes and a matching reference. The issue existed
since 1.0.0; quick states saved before the fix keep the damaged palettes until
the game reloads them.

### Camera projection and first HDMA line

DSP-1 camera projection now separates the original camera normal from the
clipped ground-plane angle. Its normalized plane height selects the clipping
bound; near-horizon correction uses Q15 polynomial coefficients synthesized
from pi/4. Target projection retains the pre-correction secant, while raster
projection uses the corrected one. An extreme negative-angle case also exposed
an intermediate Q15 overflow that reversed a projected axis; the intermediate
now stays wide until the outer multiplication.

An authored cartridge supplies **132 camera/target/point/raster sequences** to
independent [Snes9x DSP-1](https://github.com/snes9xgit/snes9x/blob/master/dsp1.cpp).
All 3,432 numeric output bytes agree, including every clipping exponent and
positive/negative boundary cases. The real device tests also retain and resume
six clipped camera states through the byte-port protocol. No firmware or full
firmware lookup table is incorporated; the stored fixtures are original numeric
expectations. These tests qualify the sampled math and protocol paths, not
electrical DSP timing or every possible input.

The renderer's first HDMA unit used to restore its saved table cursor after
writing the registers. The following HBlank repeated that entry, delaying all
later splits by one row. The line-zero unit now consumes its cursor, counter
and descriptor reload exactly once. Authored alternating-brightness cartridges
match independent Snes9x images across **229,376 pixels**, covering PAL/NTSC
and direct/indirect tables. The ROM-free
`tools/snes_hdma_selftest.py` preserves that complete CPU/HDMA/render regression.
HDMA render replay still costs no additional guest CPU time; exact CPU/HDMA
arbitration and launch/release phases remain separate work.

### Earlier PPU/DMA and enhancement-circuit follow-up

Regular DMA now advances the shared master clock for each four-clock read
phase and each four-clock write phase, rather than charging the whole transfer
before its first access. IRQs can latch during the transfer without parking
its remaining device accesses behind the pending handler. Source addresses
still wrap within their bank, fixed/decrement modes retain their behavior,
and a zero byte count transfers 65,536 bytes.

A-bus DMA cannot address mirrored CPU/B-bus registers. WRAM-to-WRAM transfers
through `$2180` cannot advance the WRAM port. Byte reads update the CPU data-bus
latch. HDMA respects its direction bit for direct and indirect tables.
These rules are checked against the documented implementation contracts in
[ares DMA](https://github.com/ares-emulator/ares/blob/master/ares/sfc/cpu/dma.cpp).
The renderer still owns HDMA replay; it must not charge that replay as CPU time.
Launch-divider alignment, release phases and DMA/HDMA collision arbitration
are still unqualified. The existing aggregate startup cost is retained.

VRAM reads/refills and writes now respect forced blank and the latched
224/239-line vblank edge. Blocked writes still advance the programmed address;
blocked buffer refills return zero. An original transfer crossing vblank checks
the actual per-byte result. Active-display OAM/CGRAM fetch collisions remain
separate work; this change does not claim a dot-accurate PPU.
See the [ares PPU port contract](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/io.cpp).

DSP-1 small LoROM ports and HiROM ports/SRAM are decoded separately. The fast
CPU SRAM path now uses the same checked decoder as the cartridge bus. No title
list is needed for these board signatures. DSP-2/3/4 signatures remain refused.
The firmware-free DSP-1 model adds zero-initialized raster output, screen/ground
target calculation, attitude matrices, coordinate transformations, scalar
products and three-axis rotation. Twenty authored sets of numeric outputs
match independent [Snes9x DSP-1](https://github.com/snes9xgit/snes9x/blob/master/dsp1.cpp)
tests exactly. No firmware dump or table is incorporated.

Pilotwings exposed those missing operations and was previously blocked in its
attract route at frame 1,978: projection command `$02` requested zenith `$3801`,
outside the inherited model's qualified range. The failed report remains
historical evidence. The camera correction described above implements clipping
and horizon correction, rather than simply removing the old range guard.
New exact-ROM observations still require successful ordinary and packed
qualification before promotion to shared knowledge.

CX4 uses its existing instruction core and synthesized mathematical constants.
Its instruction work is counted and reported as a separate device entry,
never mixed into the main-CPU percentage. A native 65816/SPC700 path must not
hide interpreted CX4 work. Unknown DSP-1 operations or a stuck CX4 bus stop
conversion validation. Device snapshots include their protocol/matrix/cache
state, fractional clocks and absolute clock anchors. Firmware files in the
working directory cannot silently replace the selected device model.

SA-1, S-DD1, SPC7110 and other custom circuitry remain unsupported by this
integration. Super FX boards are supported, with the GSU as a counted
interpreted device; see [SNES_SUPERFX.md](SNES_SUPERFX.md). Credible SA-1 headers are now recognized and receive an
explicit circuit-support error, instead of being mistaken for invalid ROMs.
Their presence in the imported engine is not product qualification.

### Cartridge saves and guarded RAM follow-up

Ordinary battery-backed LoROM/HiROM RAM is now loaded and saved separately from
F8/F9 quick states. The runtime reads without creating folders and writes only
when the guest has changed its cartridge RAM. Writes are debounced and flushed
on normal exit, through a temporary file and atomic replacement in `datas/saves`.
Files bind the full ROM SHA-256, RAM size and mapping, with payload integrity.
A corrupt or foreign file is preserved and cannot be overwritten with blank RAM.
Volatile cartridge RAM is not persisted. Probes do not read player saves unless
an explicit private `--cartridge-save` path is supplied.

The shared cartridge decoder repairs the LoROM `$F0` write mirror, retains the
upper SRAM aliases of ordinary small LoROM boards, and limits HiROM SRAM to
`$20-$3F/$A0-$BF:$6000-$7FFF`. WRAM, device registers and ROM remain distinct.
The common header's zero RAM exponent means no RAM, not a synthetic 1 KiB bank.
Ordinary RAM allocations are validated and bounded to 128 KiB before loading.
Mapping expectations were checked against the primary
[Snes9x cartridge map](https://github.com/snes9xgit/snes9x/blob/master/memmap.cpp).

The converter can qualify code executed from those SRAM windows as well as WRAM.
Dispatch keeps the exact PC, mapping/image identity and all four live-byte guards;
operands and fetch timing still use the guest bus. Cartridge save contents are
never imported into shared knowledge. Main-CPU observations now retain up to
16,384 variants: Secret of Mana exposed the former 2,048-entry ceiling.
Lookup first locates the PC by binary search, then checks only its candidates.
Observation deduplication uses a bounded hash table. Overflow remains reported,
and unknown or modified code keeps counted interpreter fallback.
Selection also checks the opcode returned by the actual timed bus fetch.
That fetch happens once, before choosing a native body. An original read-hook
fixture changes the opcode during fetching: the old pre-fetch selection fails,
while the current path executes the returned opcode through counted fallback.
No instruction is selected from a stale preview or fetched a second time.

Original fixtures cover both mappings in PAL and NTSC, mutated RAM instructions,
fresh-process battery counters, quick-state replay and rejected files. Independent
Snes9x fixtures agree on the authored guest results with normalized initial SRAM;
this is not a claim of exact CPU/bus-cycle agreement or complete hardware fidelity.
The SNES profile remains experimental.

This follow-up qualifies eight exact revisions, including four additional RPGs.
The final compressed binaries compare 129,600 internal CPU/memory/video/PCM
frame pairs across opening, varied and menu-confirmation routes. They report
zero main/sound interpreter fallback on those paths, with no RAM-observation
overflow. Secret of Mana's confirmation route reaches its early bridge dialogue;
the earlier name-entry route did not cover that code and its failure is retained.
Sixteen fresh-process state continuations compare another 2,880 frames and
reject 128 malformed states. These are bounded routes, not complete playthroughs.

The automated checks include 359 Python tests, 33,102 65816 instruction-state/bus
comparisons, 4,096 guarded positions per mapping beyond the former ceiling, and
36,885 cartridge/file assertions. An original fixture retains all 16,384
observations without duplicate slots and exposes overflow explicitly.
The four PAL/NTSC SRAM programs learn their six initial interpreter calls to
zero and preserve a guest-written counter through a new process.

The one-file converter is exercised on Secret of Mana and Lufia II with an
initially empty private knowledge directory: both perform normal discovery and
reference validation before reaching zero counted CPU/audio fallback on their
second pass. Sound is native from the first pass. Dependencies remain cached,
so this is not a cold-toolchain benchmark. Shared data is still ROM-free;
unreconstructible RAM patterns remain local instead of weakening validation.

Generic cartridge work directories use a short SHA prefix to leave room for
MSVC's nested compiler-tracking files. The complete ROM identity stays in the
profile, receipt and library. An occupied prefix with another identity gets a
longer prefix; an incomplete directory containing another cartridge is preserved.
This addresses the long-path failure exposed by the nested one-file test folder.

### Audio and display follow-up after 0.26.0

The standalone audio host consumes PCM on the game thread. An inherited word-bus
shortcut nevertheless reversed the two bytes of 16-bit APU writes to avoid a
race with an upstream audio thread. That order corrupted Terranigma's sound
commands and eventually its sound-program control flow. The instruction adapter
now uses the ordinary timed low/high byte path for those stores, including APU
port mirrors. Word reads and unrelated register accesses retain their existing
behavior. An original cartridge fixture checks the applied command sequence.

The APU frame clock now accounts for actual elapsed master clocks. The beam
already advances parked CPU time; adding a minimum audio field again was wrong
when overscan switches shortened a host iteration. PAL keeps fractional clock
carry; NTSC retains the existing nominal master-to-APU ratio. The initial partial
field and later height changes no longer invent audio time. This is digital
clock/PCM evidence, not a physical latency or listening measurement.

The display adapter retains both dots of true hires modes 5/6 and pseudo-hires,
and both alternating interlace fields. Ordinary output is 256 pixels wide;
hires is 512. Active height is 224 or 239 raster lines, becoming 448 or 478
texture rows in interlace. Horizontal and vertical pixel density are accounted
for at presentation, so switching to hires does not double the display aspect.
Fullscreen fitting, filters and mouse coordinates use the logical image geometry.

Field modes/parity latch at the beam's V=0 boundary. Interlace alternates the
262/263 NTSC or 312/313 PAL field line count. Overscan changes move the armed
vblank deadline in either direction, including inside busy register polls and
interrupt routines. The register journal distinguishes vblank from visible
writes through a wrap marker, retaining chronological replay past line 224.
Quick states include parity, latched field modes and the retained field image.
They also retain VRAM/CGRAM access addresses, increments, buffers and read/write
latches omitted from the pinned PPU's register/memory snapshot. A real DKC
continuation exposed that omission despite matching its first resumed image.
Older incompatible state signatures remain rejected without rewriting them.

Native/reference comparisons also require complete geometry and captured-row
diagnostics. Long PAL probes still require picture and PCM activity: agreement
between two CPU paths sharing the hardware cannot qualify a silent/blank run.
RAM and sound observations newer than their successful qualification report
cannot replace a previously verified shared record.

### Evidence boundaries

Original ROM-free tests cover APU store order and mirrors, main/sub dots,
color math and windows, mode patterns, image bounds, lower interlace rows,
aspect fitting and busy overscan transitions. Retail qualification compares
CPU, memory, complete visible-frame sequences and PCM before learning; packed
exports and fresh-process states are checked separately.

The eight exact cartridge revisions in this qualification compare 105,600
native/reference frame pairs before packaging and another 105,600 in the
compressed exports. The final tested paths use no counted 65816 or SPC700
interpreter fallback. Sixteen state continuations after a fresh process compare
2,880 more frames, with 128 malformed states rejected without changing the guest.
This covers deterministic routes, not every situation in those games.

The ROM-free checks include 349 Python tests, 33,098 65816 differential cases,
65,860 SPC700 differential cases and nine independent SPC assertions, 802 video
and APU-store assertions, 48,013 clock assertions and nine scheduling fixtures.
The shared Mega Drive presentation checks also pass unchanged.
Sixty hidden SDL software-renderer runs exercise five original display scenes
with all four filters and three saved display modes. Those runs preserve their
private settings files; they are not a visual review on a physical display.

The packaged converter was exercised with an initially empty private knowledge
library on two cartridges. Smash Tennis reaches zero counted CPU/audio fallback
on its first pass. Terranigma learns additional private RAM guards on its first
pass and reaches zero on its second pass; its audio path is native on both.
Normal reference validation remains required. The toolchain cache was reused,
so this is not a fully cold compilation-speed benchmark. The embedded verified
snapshot contains 1,001 exact ROM records, including 18 SNES records, and no ROMs.

Independent Snes9x scene comparisons are private test evidence. The original
239-line overscan pattern matches exactly. Hires/pseudo-hires/interlace patterns
differ only at their first subscreen dot: the implementation follows the
[ares DAC contract](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/dac.cpp),
whose first-dot initialization is itself described as unconfirmed on hardware.
That discrepancy is retained, not reported as an exact independent match.
The [Snes9x reference](https://github.com/snes9xgit/snes9x) is not a product dependency.
No reference DLL, cartridge image or screenshot is distributed in the converter.

Remaining qualification concerns finer PPU access/collision timing, uncommon
offset/mosaic/color-math combinations, additional games and cartridge circuitry.
Independent hardware fidelity, complete playthroughs and physical latency are
separate from native coverage. F8/F9 and ordinary cartridge battery files exist;
additional cartridge circuitry still requires its own integration and qualification.

### CPU, DMA and HDMA arbitration follow-up

HDMA now belongs to the running guest bus timeline. Field initialization is
requested at line zero, master clock 12; line transfers are requested at clock
1104 of each active raster line, including line zero. The beam latches requests;
the DMA engine services them after completing its current byte. Another channel
pauses and resumes ordinary DMA; HDMA taking the same channel cancels that DMA.
Channels retain their updated source/count registers, including the indirect
HDMA pointer which shares the ordinary transfer-size register.

The implementation follows the published transfer/arbitration contracts in
[ares CPU DMA](https://github.com/ares-emulator/ares/blob/master/ares/sfc/cpu/dma.cpp)
and checks their overlap behavior against
[Snes9x DMA](https://github.com/snes9xgit/snes9x/blob/master/dma.cpp).
The local implementation and authored fixtures are original; neither reference
emulator nor firmware is a shipped dependency. Setup, payload and table reads
consume guest clocks. Non-reloading rows still perform their table bus read and
update the CPU data latch. A terminating last indirect channel performs one
pointer-byte read; earlier terminating channels perform both. Invalid A-bus
register sources cannot recursively operate CPU/B-bus registers.

Parked CPU time is separated from the event's timestamp before charging HDMA.
Otherwise a parked scanline stamped each transfer one row late. Empty HDMA
edges do not steal clocks or prematurely stop synchronization as an IRQ would.
IRQ latches can assert during a transfer, but a CPU handler cannot interrupt
its byte phases. CPU-clock divider alignment and exact launch/release phases
remain unqualified; the existing ordinary-DMA startup cost is retained.

Rendering replays recorded PPU bus values, including VRAM/CGRAM/OAM ports,
from a field memory/register/port snapshot. It does not execute HDMA or read
the guest tables again. All guest memory, ports and register latches are
restored after drawing. This also preserves rows whose HDMA source data is
changed later by an IRQ. The journal holds 131,072 ordered writes per field;
overflow remains counted instead of silently replacing entries.

Original tests cover all eight overlapping DMA channels, cancellation/resume,
WAI stalls, clock debt, the vblank exclusion, indirect termination and repeated
rendering without guest side effects. Twelve complete direct/indirect PAL/NTSC
brightness/palette images, including late table mutation, agree pixel for pixel
with independent Snes9x: 688,128 pixels. These fixtures qualify the specified
behavior; they do not prove electrical timing or exhaustive hardware fidelity.
The SNES profile remains experimental.

This bus follow-up requalifies Pilotwings, Super Mario Kart, Mega Man X2,
Super Metroid, Donkey Kong Country and PAL Terranigma. Their packed executables
compare 85,200 native/reference frame pairs, with no counted 65816/SPC700
fallback on those routes and no RAM overflow or digital PCM underflow/drop.
CX4 interpretation remains counted in Mega Man X2. Twelve fresh-process state
continuations compare 2,160 resumed frames and reject 96 malformed files.
The one-file converter also builds Pilotwings and Mario Kart with initially
empty private libraries, performs normal validation and passes two further
fresh-process states. These are bounded gameplay/digital-audio checks; complete
playthroughs, independent entire CPU fidelity and physical latency remain
separate. The six knowledge records are requalified without increasing the
shared resource; it still contains 1,009 exact ROM identities, including 26 SNES.

### Fine CPU bus phases and PPU collisions

The next local block prices real CPU byte transfers as they happen, rather than
advancing the beam once at instruction retirement. Reads sample after the
6/8/12-clock bus cycle minus its last four clocks; writes reach their device at
the end of their cycle. MMIO words use two ordered byte transfers, including
reversed stores. Host code-inspection reads do not consume guest time. APU
synchronization uses the timestamp of the actual access.

DMA requests finish one complete CPU cycle before taking ownership, align to
the eight-clock divider, and release on the next CPU cycle's divider. CPU-owned
DMA uses an eight-clock startup. Direct non-CPU fixture callers retain their
older startup convention. DRAM refresh now holds the live beam for 40 clocks at
the CPU-v2 phase-dependent edge of each line, including during DMA. Refresh
holds are excluded from the DMA-release divider debit. IRQ/NMI entry performs
timed dummy/stack/vector accesses, selects the native or emulation vector,
sets I, clears D and wraps the emulation stack correctly. Internal CPU-register
reads preserve the separate CPU data latch. RDNMI, TIMEUP and HVBJOY retain
their undriven bits instead of returning zeros; an independent authored IRQ
probe exposed this omission.

The phase contracts are checked against primary sources in
[ares CPU memory](https://github.com/ares-emulator/ares/blob/master/ares/sfc/cpu/memory.cpp)
and [CPU timing](https://github.com/ares-emulator/ares/blob/master/ares/sfc/cpu/timing.cpp).
Unused instruction-internal cycles still occur at retirement; their position
inside every addressing mode and parked-CPU handshake is not fully qualified.
This is a concrete improvement in bus chronology, not an electrical-exactness
claim for every 65816 instruction or every CPU revision.

Active-display OAM accesses use the live sprite-evaluation/fetch latch;
active-display CGRAM accesses use the currently selected palette address.
Programmed port increments and low/high write buffers remain separate from that
effective address. CGRAM high writes mask the unused bit; reads retain PPU2
open-bus bits. PPU1 and PPU2 now have distinct read latches. The raster journal
records the effective write address so drawing cannot reinterpret a collision
using the final beam state. Guest port/latch state is restored after drawing
and included in quick states; old incompatible signatures are rejected.

Original PAL/NTSC fixtures provide 58,154 PPU assertions and 9,726 real-engine
bus/interrupt assertions. The latter also execute six authored cartridge
programs and check the bytes they produce, without commercial cartridges or
firmware. Independent current bsnes with its fast PPU disabled matches the
defined palette results in PAL and NTSC. Its OAM results differ: the local
model follows the newer
[ares OAM port contract](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/io.cpp),
which maps the requested byte from a sprite latch, while
[bsnes](https://github.com/bsnes-emu/bsnes/blob/master/bsnes/sfc/ppu/io.cpp)
uses its latch as a byte address. This disagreement stays recorded as an open
hardware gate; OAM collisions are not reported as independently exact.
Neither external emulator nor its DLL or captured states are bundled.

Sprite overflow status is latched after the object fetch sequence finishes;
detecting the 33rd sprite during evaluation must not set STAT77 immediately.
The flags remain sticky until the next field begins. Two further authored
PAL/NTSC programs read status before evaluation finishes, before fetch finishes
and on the following line. Their `00, 00, C0` result matches independent bsnes.
These checks complement the separate, still-disputed OAM address model.
Mid-line blanking, size changes during object fetching and every possible
palette-pipeline phase are outside this bounded qualification.

The six exact controls are requalified again after the bus and CPU data-latch
changes: 43,200 normal-conversion frame pairs and 85,200 pairs in the actual
compressed exports, plus twelve fresh-process state continuations (2,160 resumed
frames, 96 malformed states rejected). The main and sound CPU paths have no
counted fallback on those routes; CX4 interpretation remains explicitly counted.
The rebuilt converter also generates Pilotwings and Mario Kart with an initially
empty private library and its verified bundled snapshot enabled, then checks
the generated exports and fresh-process states. This uses cached dependencies,
not a cold toolchain-speed benchmark. Requalifying the six records does not
change the snapshot bytes or the other consoles' records.

Hidden SDL software-renderer checks also retain the expected video cadence:
480 PAL frames take 9.598656 seconds against 9.598660 expected, and 480 NTSC
frames take 7.986816 against 7.986846. Dummy devices and the video-clock-only
mode are used; this checks pacing rather than physical audio or input latency.

### Manual joypad strobe (Star Fox 2 Japan prototype)

The pinned engine's register write dispatch forwarded only `$4200-$421F` to
the machine model, so a guest store to `$4016` never reached the controller
ports. Games that read the pads through the automatic `$4218-$421F` words were
unaffected, which hid the omission. A game that polls by hand strobes `$4016`
(1 then 0) and clocks 16 serial bits from `$4016`/`$4017`; with the strobe lost,
the shift position stayed wherever earlier reads had left it. The Japanese
Star Fox 2 prototype (header map `$20`, type `$1A`) begins its boot-time
controller check with a `TRB $4016` (a read), so every bit arrived one position
late and the final four bits of the packet, which identify the device, no
longer looked like a standard pad. It stopped on its "controller only" notice
at frame 60 for ever, with the GSU idle and no sound, while MAME starts it.

`snes_bus.runtime` now routes the `$4016` store to the existing strobe model.
Hardware rule, from fullsnes ("SNES Controllers I/O Ports", JOYSER0): while
bit 0 is high both ports continuously reload, the falling edge latches the pad
state and restarts the serial position at the first bit (B); `$4017` stores do
nothing; a standard pad answers 1 on Data1 after its 16 bits and never drives
Data2. Only the documentation was consulted, no GPL emulator code.
`native/snes_bus_checks.c` checks this on the real engine through bus stores
(a stale position, a strobe in the middle of a packet, 17th-bit and Data2
values) and `tests/test_snes_bus.py` guards the adapted source. The same
delivery now also feeds the Super Scope packet latch (`rr16_scope_write_strobe`),
which was written for it. Game fingerprints of every Super Nintendo conversion
change with the adapted engine source, as for any engine adaptation.

## Part 2: Super Nintendo text from the former CONSOLES_16BIT.md

The sections below were moved from `CONSOLES_16BIT.md`, with the stage each one describes.



### Scope statements of releases 0.24.0 and 0.25.0

These sentences come from the introduction and the "Supported scope" part of the
former `CONSOLES_16BIT.md`.

At release 0.25.0 the experimental SNES snapshot had 15 qualified hint records.

The generic SNES path accepts ordinary LoROM/HiROM up to 4 MiB, including
FastROM and RAM/battery variants; extended mappings and other enhancement chips
remain unsupported. DSP-1, CX4 and Super FX have qualified integration with
explicit limits; see [SNES development](SNES.md). PAL/NTSC comes from the
cartridge header.

The published 0.24.0 snapshot includes verified compilation hints for 15 exact
Super Nintendo cartridges (and 51 exact Mega Drive cartridges). These are
regression observations, not a full-catalogue compatibility score.

| Profile | Available today (at the time) | Work still needed (at the time) |
| --- | --- | --- |
| Super Nintendo | Automatic analysis of ordinary LoROM/HiROM cartridges, native 65816 and sound SPC700 paths, PAL/NTSC, shared controls, quick states, battery SRAM and Super Scope; hires/interlace/overscan and guarded SRAM code; DSP-1, CX4 and Super FX boards | Other enhancement chips (SA-1, S-DD1, SPC7110, DSP-2/3/4)/extended mappings, finer independent PPU/timing qualification, additional cartridge circuits and broader gameplay coverage |

### Earlier regression examples (Super Nintendo rows)

The table of cartridges qualified in earlier stages. It records previous tests,
not the conversion scope: any cartridge whose board is supported is analysed
from its own ROM.

| Profile | Qualified cartridge | Timing | Visible image |
| --- | --- | --- | --- |
| Super Nintendo | Super Mario World, USA, CRC32 B19ED489 | NTSC | 256 × 224 |
| Super Nintendo | Super Scope 6, USA, CRC32 B141EA99 | NTSC | 256 × 224 |
| Super Nintendo | The Legend of Zelda - A Link to the Past, USA, CRC32 777AAC2F | NTSC LoROM | 256 × 224 |
| Super Nintendo | Super Metroid, Japan/USA, CRC32 D63ED5F8 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Donkey Kong Country, USA, CRC32 762AF827 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Castlevania IV, USA, CRC32 B64FFB12 | NTSC LoROM | 256 × 224 |
| Super Nintendo | F-Zero, USA, CRC32 AA0E31DE | NTSC LoROM | 256 × 224 |
| Super Nintendo | Mega Man X, USA, CRC32 DED53C64 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Chrono Trigger, USA, CRC32 2D206BF7 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Bomberman, USA, CRC32 63A8E2C6 | NTSC HiROM | 256 × 224 |
| Super Nintendo | Super Mario All-Stars, USA, CRC32 925637C7 | NTSC LoROM | 256 × 224 |
| Super Nintendo | Pop'n TwinBee, Europe, CRC32 588A9707 | PAL LoROM | 256 × 224 |

### Files recognised, headers and titles

The original ROMs remain read-only. Linear `.md`/`.gen` and validated
`.sfc`/`.smc` images, single-cartridge ZIPs, and identifiable `.bin`/`.rom`
files are recognized. A SNES copier header is removed only from the in-memory
build input. Interleaved SMD remains unsupported. No ROM patches or widescreen
mode are applied. The table records previous tests, not the conversion scope.
SNES header titles accept the ASCII and single-byte katakana ranges of
[JIS X 0201](https://github.com/alekmaul/pvsneslib/wiki/SNES-ROM-Header).
The title is decoded without changing the cartridge bytes. Invalid title bytes,
ambiguous headers and inconsistent checksum pairs still fail identification;
unsupported chips or mappings still fail conversion preflight. This recovered
90 prematurely rejected files in the supplied SNES collection, which still need
the usual execution validation.

### PAL timing, first stage


The later audio/display work completes hires dots, interlace field retention and
239-line overscan in the adapter; see [SNES development](SNES.md). The initial
PAL results below describe the earlier progressive-only qualification, including
failures preserved for comparison.

The first European revision uses 312 lines of 1,364 master clocks and
a 21,281,370 Hz video oscillator: approximately 50.00698 fields per second.
The PPU's $213F region bit, raster journal chronology, vblank polling and IRQ
comparators use the same region. PAL includes the longer vblank interval;
an authored interrupt on line 300 verifies that it is not truncated at the
NTSC field boundary.

The SPC oscillator remains 1,025,280 Hz, producing 32,040 native DSP samples
per second. Fractional cycles carry between host iterations, including long
loaders; switching to PAL does not slow the sound driver to 50/60 of its
original rate. Existing qualified NTSC audio scheduling is retained in this
stage. Timing constants were checked against the primary ares implementation:
[system clocks](https://github.com/ares-emulator/ares/blob/master/ares/sfc/system/system.cpp),
[APU oscillator](https://github.com/ares-emulator/ares/blob/master/ares/sfc/system/system.hpp)
and [PPU field geometry](https://github.com/ares-emulator/ares/blob/master/ares/sfc/ppu/ppu.cpp).

This historical initial PAL scope was progressive 256 x 224. Overscan,
interlace and 512-pixel modes were not yet qualified at that stage; the later
[display follow-up](SNES.md) supersedes this restriction. The converter checks the actual active
raster, excluding screen-off register initialization. Long qualification
runs also require picture and PCM activity, in addition to internal
native/reference agreement. A silent or unsupported-display result must
not become a qualified export merely because both CPU paths agree.

The PAL cartridge passes demo/play tests of 3,600 images and a varied
6,000-image input replay with zero interpreted main or sound CPU operations.
These checks establish the tested paths and internal agreement; independent
full hardware fidelity, physical latency and complete gameplay remain separate.

Additional European probes did not qualify: Terranigma remained silent, while
The Firemen and Smash Tennis exercised hires on active lines during extended
input replays. These results identify work for the audio/512-pixel stages;
none of these cartridges is enabled or exported by this PAL stage.

### Controls, quick states and saves in the shared interface text

Two paragraphs of the former "Shared game interface" section (the rest of that
section is shared by the 16-bit family and stays in
[CONSOLES_16BIT.md](CONSOLES_16BIT.md)).

Mega Drive defaults to arrows, W/X/C for A/B/C and Enter for Start. The qualified
Street Fighter II' Plus and Mortal Kombat II profiles expose X/Y/Z and Mode in
F2, using A/S/D and right Shift (either Shift works) by default. Their two
controller ports use the six-button protocol; other profiles retain
three-button pads. SNES defaults to arrows, W/X/A/S for A/B/X/Y, Q/E for L/R,
Shift for Select (left by default, either Shift works since 1.5.0) and Enter
for Start. Player two uses the numeric keypad and has no reset
shortcut. F2 exposes the console's actual controls.

F8/F9 quick states are implemented for the qualified instruction-based profiles,
including PAL. They survive closing and restarting the game and are stored in
`datas/states/<game-slug>-<rom-sha12>.rrstate`. A runtime ABI or ROM mismatch is
rejected. See [captured state and validation](GAME_STATES.md#mega-drive-and-super-nintendo).
Ordinary SNES battery-backed cartridge RAM is saved independently in
`datas/saves`, with exact ROM/mapping identity and atomic writes after guest
changes. Volatile RAM stays in memory. See [SNES cartridge saves](SNES.md).

### The 65816 adapter and the interpreted-opcode counters

Qualified SNES cartridges use a separate 65816 adapter. The converter selects one
compiled operation for every physical ROM byte and writes a ROM-PC dispatch
map. LoROM and HiROM mirrors follow the live cartridge mapping. Non-power-of-two
images match the loader's repeated final block: a 3 MiB image repeats its final
MiB in the fourth MiB. Both original image size and padded storage size are
checked without changing the supplied ROM. Covered operations bypass
the opcode-switch interpreter while retaining the real PC, stack, opcode-fetch
timing and live operand reads. Register-width flags, bank wrapping and memory
accesses therefore retain the pinned engine's semantics. Operands are not
specialized into literals as they are in the Mega Drive adapter.

SNES RAM helpers are learned during converter probes, then compiled with an
exact PC and four-byte live-code guard, covering the longest 65816 instruction.
Changed bytes or an unobserved helper use the counted interpreter. Up to
16,384 variants are stored in `datas/library/snes/<rom-sha256>/native-ram.json`.
Generated games never persist learning observations. The SPC700 sound processor
also uses guarded native operations, described below. Both native and reference tests use the real PC/stack
instruction scheduler instead of the previous paired C-call bridge.

The converter records interpreted main-CPU **opcodes**, separately from the
sound-CPU opcode and cycle counters. Main-CPU percentages refer only to that
CPU; both sound processors have separate cycle-based percentages. The window title
signals interpreter use, including the sound CPU, and H explains that status.

### Scan scenarios, as the former text counted them

This paragraph of the former "Further validation scope" section counted four
Super Nintendo scenarios. In the current code the Super Nintendo runs the
attract (demo) and play scenarios at every level, adds the pseudo-random routes
and, for the cartridges that have one, the authored route from the Extended
level on (see [SNES.md](SNES.md#converting-and-the-scan-levels)). The Mega
Drive replays named there are Mega Drive only.

All seven Mega Drive controller scenarios (four for lightgun games) and the four
Super Nintendo scenarios are compared against the internal CPU/video/audio
reference before new 68000 ROM/RAM entries, Z80 opcode variants, 65816 RAM
variants or SPC700 opcode variants enter the local library.
The converter regenerates code while verified observations are added, within
the existing **Maximum passes** limit. It stops when no new paths are found.
The final report records the scan mode, each scenario's budget, fallback counters
and reference comparisons. Reaching the pass limit can still leave counted fallback.

### SPC700 sound-program recompilation

The Super Nintendo sound CPU now follows a separate PC-directed AOT path.
Conversion selects fixed SPC700 operation bodies and builds guarded address
tables for uploaded sound programs. Live opcode checks reject changed code;
immediate operands and data accesses still use the existing APU bus. The boot
overlay has its own mapping, so underlying RAM is selected only when the
guest disables that overlay. Volatile I/O instruction fetches retain the
counted reference path instead of attempting a side-effecting guard.

Probes collect exact misses and up to four sound-RAM images, allowing the next
pass to cover driver positions it has not executed yet. A compressed, bounded
opcode map in `datas/library/snes/<rom-sha256>/spc-native.json` stores that
converter knowledge. Ordinary play retains counters only and creates no files.
The converter's `memory` command reports sound-map size and variant count.

Native execution uses the live SPC registers and preserves instruction costs,
taken-branch penalties, stopping, timers, DSP access and CPU/APU port scheduling.
Stopped scheduler ticks are recorded separately from retired opcodes. Unknown
code still uses the visible, counted reference fallback; the window title
reflects either CPU's fallback use.

Every SNES conversion pass compares the native and fully interpreted paths
before teaching the library. Headless tests consume the same one-frame audio
blocks as interactive play and compare PCM, SPC registers, APU RAM/timers/ports,
DSP state, instruction counts and cycle totals, alongside the existing
main-CPU and video checks. These are internal shared-semantics comparisons,
not independent hardware measurements or complete-game validation.

The ROM-free SPC700 self-test covers all 256 operations across all status-flag
combinations, PC wrapping, the boot overlay, opcode replacement, volatile
fetches and bus ordering: 65,860 differential cases, with nine additional
assertions for live operands, branch cycles, read-to-clear timers and stopping.

With an empty sound bank, two conversion passes reduced fallback as follows
on 8 October 2026. Each demo and play scenario runs for 3,600 frames; existing
65816 RAM observations were reused. Both CPUs finish at zero fallback on all
four tested paths, with matching PCM and CPU/APU/DSP/video state.

| Qualified NTSC revision | SPC700 fallback in first sound pass, demo / play | Final fallback, demo / play |
| --- | ---: | ---: |
| Super Mario World | 15,845,354 / 15,646,412 | 0 / 0 |
| Super Scope 6 | 14,919,382 / 14,985,769 | 0 / 0 |

The two compressed sound maps total 185,522 bytes. Reset checks repeat the
same 600-frame image and PCM sequence on both games. The host adapter resets
the architectural CPU state and clocks as well as the sound-delivery history
when restarting, while preserving cartridge save RAM.

### 65816 and shared comparison limits

Super Mario World's first ROM-only pass reported 372,060 interpreted main-CPU
instructions in demo and 100,750 in play. Learning 130 RAM variants and
regenerating reduced both to **zero**, over approximately 49 million retired
instructions per scenario. Both full-length reference comparisons match:
visible-frame sequence, final CPU registers/PC, RAM, VRAM, CGRAM, OAM,
high OAM, APU RAM and CPU/master/APU clocks. Authored SNES fixtures pass
33,098 instruction/state/bus comparisons across all 256 operations, register
widths, emulation/native modes, decimal arithmetic, LoROM/HiROM mirrors and changed
RAM/ROM guard rejection. Boot/reset/repeated 600-frame image sequences also
match for Sonic and SMW.

The SNES interrupt scheduler now yields at the field deadline or WAI, retaining
the architectural stack and continuation. An interrupt routine can outlive one
field or park inside the handler. RTI also publishes the actual popped return
address: a game can use a modified interrupt frame to switch guest tasks.
Discarding that destination skipped Zelda's polygon worker even while both
native and reference tests agreed. Three ROM-free fixtures separately check
WAI, a long interrupt and RTI task switching against explicit clock and PC
expectations (`python tools/snes_scheduler_selftest.py`).

Four additional NTSC revisions were checked on 8 October 2026: A Link to the
Past, Super Metroid, Donkey Kong Country and Super Castlevania IV. Each completed
3,600 demo frames, 3,600 standard input frames and 6,000 frames with varied
controller input, with zero interpreted instructions on both CPUs and matching
internal CPU/memory/video/PCM diagnostics. Donkey Kong Country exercises HiROM;
Super Metroid also exercises the 3 MiB-to-4 MiB cartridge mirror.

Reset testing exposed a separate FastROM issue: the upstream MEMSEL shadow
survived restart, changing early boot bus costs and the audio handshake. The
host now clears it with the architectural CPU state and clocks. All four
packed exports repeat their 600-frame image and PCM sequence after reset,
without erasing cartridge SRAM. Packed/raw startup diagnostics match, and a
short isolated launch creates no extra files. Visual, listening and complete
gameplay acceptance remain user checks.

The SDL SNES audio host queues every generated PCM block. Catch-up after a host
scheduling delay waits briefly for room before the next input sample/frame;
it no longer consumes and silently drops a whole block above the 20 ms queue
target. Opening and resuming the device waits for its first block. A 600-frame
dummy-device test with four injected 35 ms delays formerly dropped 3,194 stereo
frames (about 66.5 ms); the corrected host queued all 479,536 frames. Peak queued
PCM was about 36.3 ms and the existing DSP cushion was unchanged. These are
digital queue checks, not a listening test or a physical latency measurement.

The separately maintained [sp00nznet/snesrecomp](https://github.com/sp00nznet/snesrecomp)
was also inspected at `644c7647a9b2a6f286abe14ff07e1751e98c4a17`. It packages
LakeSnes hardware behind a bus/platform adapter for separately recompiled game
code. Its scheduling, graphics and audio integration provide useful comparison
points; both projects have LakeSnes ancestry, so it is not an independent
hardware oracle. No source from that project was added to these builds.

Game packing uses UPX level 9 rather than its exhaustive `--best` search. Private
large-SNES tests compacted approximately 33.5 MB to 7.0 MB in 26.3 seconds and
47.3 MB to 10.0 MB in 36.8 seconds. Integrity verification still precedes atomic
replacement of an existing export. These timings depend on the build and host.

Every conversion compares native and reference execution over the full
requested demo/play length. Missing diagnostics or differing state, images,
timing or instruction totals reject the candidate and preserve the previous
export. Sonic and SMW's earlier reference divergences are resolved on these
bounded paths; this is not a claim that every game path has been explored.

The instruction adapters and references share pinned semantic helpers.
Agreement checks the adapters, not an independent hardware oracle.
Untested gameplay may still encounter interpreter fallback. Hardware
accuracy, full-game compatibility, sound quality and physical latency remain
unvalidated. User gameplay review is still required.

### Expanded qualification after 0.21.0

The five additional Mega Drive revisions pass demo/play checks of 3,600 frames
each and an advanced 6,000-frame replay, with zero interpreted 68000 or Z80
opcodes on the final tested paths. The five additional SNES revisions pass the
two 3,600-frame scenarios and a varied 6,000-frame replay. Chrono Trigger's
additional RAM paths were learned only after matching the reference and the
regenerated replay finishes without fallback. Each comparison covers CPU state, memory,
visible-frame sequences and audio PCM. Standard Mega Drive conversion now also
compares against the internal reference before admitting any observations to
the library; that gate is no longer limited to advanced scans.

The regeneration checks reuse front covers with artwork network transports
blocked, compare packed and unpacked exports over 600 frames, and verify reset
video/audio under equivalent memory conditions. F-Zero and Super Mario All-Stars
initialize cartridge SRAM on their first boot; a normal reset preserves it and
can therefore change the boot timing, PCM or visible sequence. Their native
resets match the reference resets with preserved SRAM; replaying with the same
initial SRAM also reproduces the original video and PCM. No save RAM is cleared
by the player's reset to force a match. Short isolated launches create no extra files. These
checks complement the authored instruction and raster fixtures; the internal
reference still shares the hardware model.

Hidden SDL pacing measurements use dummy devices. A PAL export completed
1,200 frames in 24.144120 seconds against 24.144160 expected; a SNES export
completed 1,200 in 20.015378 against 19.967116 expected under conversion load.
An NTSC Mega Drive sample completed 1,800 in 30.038580 against 30.038678 expected.
These measurements check the presentation deadline, not physical input/audio
latency or the accuracy of an in-game timer.

### Build and dependency contract

These profiles use pinned sources downloaded into `.deps` on first conversion:

| Component | Revision |
| --- | --- |
| [segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | `00c60bc855a7998f92e5614585d52bca8fffcaf2` |
| [snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) | `a00df26a87831113fec91b9225bf16b049d40775` |

A C++ toolchain is required for conversion; the converter offers to install it.
Since 1.4.1, every SNES cartridge, Super Mario World included, uses the
generic instruction-map analysis: no Rust and no separate
SuperMarioWorldRecomp dependency. Generated games need none of those
development tools to run.

Component licences and notices are embedded in each game EXE. The imported
frameworks retain their **PolyForm Noncommercial 1.0.0** terms; RetroRecomp's
MIT licence does not replace them. See [Genesis notices](../licenses/segagenesisrecomp.md) and
[SNES notices](../licenses/snesrecomp.md).

Further work includes broader Mega Drive gameplay and additional mapper qualification,
broader SNES RAM/gameplay coverage, unsupported enhancement chips and finer
CPU/PPU phases. SNES PAL, quick states and ordinary battery saves are implemented
with bounded qualification. The latest SNES bus and collision evidence, including
the independent OAM-model disagreement, is tracked in [SNES development](SNES.md).
Additional structurally different titles still need their own gameplay checks.
Recognition alone does not grant conversion compatibility.
