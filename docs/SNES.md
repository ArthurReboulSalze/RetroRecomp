# Super Nintendo development

The **Super Nintendo standard-cartridge profile is supported**: ordinary
LoROM/HiROM up to 4 MiB, PAL/NTSC, shared controls, Super Scope, cartridge saves
and F8/F9. Qualified DSP-1 and CX4 boards are supported too. CX4 device
instructions remain interpreted and counted; this is separate from native
65816/SPC700 coverage. Other enhancement circuits, extended mapping and DSP-1
firmware-dump commands remain unsupported. New cartridges are analyzed from
their own ROM, rather than selected from an allowlist.

## DSP-1/CX4 qualification and release 1.0.0

Eight exact enhanced cartridges compare **57,600 ordinary frame pairs** and
**105,600 pairs in actual packed exports**. Four extended device routes add
**36,000 pairs**; a separately confirmed two-controller race adds **9,000 pairs** and a further state check. Their 65816 and SPC700 work has zero observed fallback on
those routes. CX4 instructions stay interpreted and included in the visible
counter; no zero-total-fallback claim is made for CX4 games.

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

## Standard profile and live RAM operands, 13 October 2026

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

## Object progression and cartridge decoding, 13 October 2026

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

## Raster IRQ preemption inside NMI

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

## HDMA while the CPU is parked (Donkey Kong Country palettes)

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

## Camera projection and first HDMA line

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

## Earlier PPU/DMA and enhancement-circuit follow-up

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
Its instruction work is included in the visible interpreter counter, with
separate main-CPU and device diagnostics. A native 65816/SPC700 path must not
hide interpreted CX4 work. Unknown DSP-1 operations or a stuck CX4 bus stop
conversion validation. Device snapshots include their protocol/matrix/cache
state, fractional clocks and absolute clock anchors. Firmware files in the
working directory cannot silently replace the selected device model.

SA-1, S-DD1, SPC7110 and other custom circuitry remain unsupported by this
integration. Super FX boards are experimental on the study branch, with the
GSU as a counted interpreted device; see [SNES_SUPERFX.md](SNES_SUPERFX.md). Credible SA-1 headers are now recognized and receive an
explicit circuit-support error, instead of being mistaken for invalid ROMs.
Their presence in the imported engine is not product qualification.

## Cartridge saves and guarded RAM follow-up

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

## Audio and display follow-up after 0.26.0

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

## Evidence boundaries

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

## CPU, DMA and HDMA arbitration follow-up

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

## Fine CPU bus phases and PPU collisions

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
