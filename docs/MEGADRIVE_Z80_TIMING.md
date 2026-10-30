# Mega Drive Z80 machine-cycle placement

## BUSACK after a line end — 2026-10-30 (1.6.5)

Barkley Shut Up and Jam! (USA) waits for the Z80 bus without a loop: `MOVE.W #$0100,$A11100`, `BTST #0,$A11100`, then a
`BNE.W` whose target is address 0. When the grant was not visible to that `BTST`, about 112 master clocks after the write,
the 68000 ran the vector table as code and the conversion stopped (it was listed in KNOWN_FAILURES.md).

**Cause.** The last sound-CPU instruction of a line is allowed to retire beyond the line while the 68000 stops at the
line end. At the next line the sound CPU can therefore stand several machine cycles ahead (210 master clocks in Barkley's
frame 43). BUSACK was dated where the sound CPU stood (`rr_local_ack_time = boundary` in `rr_bus_slice`), not at the end of
the machine cycle that was in progress when the 68000 wrote BUSREQ. It was also recorded only after the 68000 had caught up
to the sound CPU's clock, so a poll during that catch-up could not see it. A trace of the game's own frame showed the request
at 22, the sound CPU at 210 and the `BTST` at 162.

**Change** (`native/md_z80_bus.inc`). The clocks at which the latest sound-CPU machine cycles ended are kept: where the next
access, I/O cycle or instruction starts, so internal clocks lengthen the cycle they follow, the convention of the literal
cases in `native/md_bus_checks.c`. They move with each line change (`retrorecomp/megadrive_bus.py`) and are dropped when a
deferred replay goes back before them. BUSACK is dated at the first of them at or after the request, and it is recorded as
soon as the sound CPU stands on a completed cycle at or after a pending request, before the 68000 catches up (which it then
does exactly as before). The sound CPU itself resumes after the release as before; its cycles between that date and where it
stood were already executed. That remains an approximation: a 68000 write to sound RAM during the grant is not seen by reads
the sound CPU made in that interval.

**Evidence.** `tools/megadrive_boundary_selftest.py PROJECT --output DIR --busack` (authored, ROM-free, in
`native/md_boundary_checks.c`): a `LD A,($1000); JP` loop behind 0 to 22 NOPs straddles the line end, and the 68000 writes
BUSREQ from about 140 master clocks before the line change to 190 after it, in the four scheduling modes (1,196 cases, 744 with
the sound CPU ahead at the line start). Before the change: 44 grants later than the request plus one cycle and the Z80 clock
wait (75 master clocks), the worst 152, and 4 `BTST` without the grant (sound CPU ahead by 180, request at 28, grant at 180).
After: none, worst 59. The same run also checks quick states: at the 460 line changes where a state may be taken (no
instruction in flight, no pending handshake), saving and loading the machine section gives exactly the uninterrupted request,
grant and `BTST` answer; dropping the kept cycle ends changes 8 of them. A state of Barkley saved at the end of frame 42 and
loaded gives frames 43 to 60 identical to the uninterrupted run. A second table checks BUSACK within a line (3,840 cases): `NOP`,
Barkley's `LD A,H; CP L; JR Z`, `INC (HL)`, a 256-byte `LDIR`, `EX (SP),HL`, `INC (IX+0)`, `DI; HALT`, `INC HL`, a bank-window
read (a WAIT-extended cycle) and an IM 1 interrupt entry (7 T). Each program's bound is its longest cycle under the convention
above (4 T to 10 T, the `LDIR` write lengthened by its repeat) plus one Z80 clock; none is exceeded (worst 149 master clocks, the
`LDIR`), no grant precedes its request, and the `BTST` sees the grant wherever that bound is shorter than its own delay. The full boundary comparison still requires the four modes to agree on all 32,840 programs; 810 of its
sweep programs (the 68000 polls for the grant) now see the grant at an earlier poll or clock, none of its 72 fixed programs
changes. `megadrive_bus`, `_z80_`, `_z80_resume_`, `_dma_` and `_interrupt_` self-tests give byte-identical results. Barkley
Shut Up and Jam! (USA) now converts: 0 interpreted 68000 instructions and 0 interpreted Z80 cycles on its demo and play routes
(3,600 frames each), native and reference equal. These are CPU-timing and bus-model checks, not a measurement on a console.

## Changed code during a suspended fetch — 2026-10-11

Side-effect-free opcode peeks cannot guarantee that the later bus fetch returns
the same byte: local BUSACK and banked WAIT can suspend after body selection.
The original authored fixture returned NOP after a guard had selected LD A,n;
the old body still retired LD as native. Its failing log is retained under
`.build/md-suspended-fetch-20261011/pre-fix-z80.log`.

Generated fixed bodies now compare the actual opcode/prefix/selector with the
literal guard before executing that stage. A disagreement continues the already
consumed byte in the correct reference semantic family. The outstanding operand
reads remain live; no prefix, displacement, port access or write is replayed.
Nested ignored DD/FD prefixes retain their outer refresh correction. DDCB/FDCB
retain the displacement address and non-M1 final selector's three clocks and
following internal wait. IRQ delivery still occurs once at retirement.

An exceptional continuation is counted immediately as interpreter entry and
the entire completed instruction's nominal cycles belong to that escape.
Unchanged opcode fetches and changed operands remain fixed-operation native.
The reference helper is not an unreported native opcode decoder. Portable-state
layout remains ABI-10; live C continuations cannot be captured and the previous
qualified signature is explicitly admitted.

`tools/megadrive_z80_selftest.py` passes 26,624 mutations in addition to its
28,544 ordinary instruction comparisons and 152 independent phase/IRQ cases.
`tools/megadrive_z80_resume_selftest.py` passes 33 native/reference real-fiber
replays and 1,157 assertions per PAL/NTSC backend, with actual local ownership,
external waits and mapping changes. The reference fixture directly selects
`z80_step` on the same machine fiber; changing an environment variable in one
process would not switch the backend's cached reference flag.

`tools/megadrive_interrupt_selftest.py` additionally passes 3,072 cases and
10,369 assertions per backend for nominal VDP interrupt masks, priority, stack
selection, STOP, DMA, busy instructions and clock wrap. This is a subsequent
qualification step, not proof of electrical IRQ/VPA/level-7 device behavior.
Qualification, cold conversions, old states and packaging are recorded in
`.build/md-suspended-fetch-20261011/qualification.json`.

## STOP and paused Z80 release — follow-up, 2026-10-11

Two scheduler defects are fixed in the common runtime, without cartridge
patches. An idle 68000 in STOP used four-cycle pseudo-instructions and could
delay a free-bus Z80 request from master tick 195 to 210. STOP now advances only
to the requested host deadline, without fetching or retiring instructions.
The normal interrupt path still wakes it; DMA ownership remains enforced.

A Z80 transaction whose grant was already pending could also resume at tick
30 after BUSREQ was released at tick 420. Word and byte writes to BUSREQ/reset
now move the paused wall clock to the release's next Z80 edge. Nominal opcode
cycles are unchanged. A reset discards the old continuation and retains this
release floor when restarting at PC zero. Repeated deassertions do not skip
running instructions. No new serialized fields are introduced; ABI-10 admits
the immediately preceding signature explicitly.

The production-backend fixtures cover divider phases, different host slices,
diagnostic clock wrap, full-frame holds, reset while BUSREQ remains asserted,
and portable-state exclusion until a live instruction retires. The two failing
pre-fix runs and current qualification are kept under
`.build/md-cpu-pauses-20261011/`.

Qualification passes 1,353 bus assertions per PAL/NTSC backend (2,706 total),
the 68000 semantics/exception/prefetch and Z80 timing suites, DMA/IRQ/video/SRAM
regressions and 74 targeted Python tests. Sonic 1/2 and Shining Force II pass
five scenarios each with zero main/sound fallback and impossible timing budgets;
the internal CPU/memory/image/PCM comparisons match. Forty-one old states
across seventeen signatures, packed fresh-process F8/F9, Sonic 2 interlace and
three copied-player SF2 routes pass. Only the three exact-ROM records were
requalified; the ROM-free shared snapshot remains unchanged. This does not
replace human gameplay validation or measure physical audiovisual latency.

This is **not** a complete Z80 local-bus handoff model: BUSACK still reflects
the control register rather than an independently scheduled machine-cycle
acknowledgement, and local-only execution can precede a main-CPU control write
inside a host slice. Those boundaries and guard revalidation remain open.
The [Zilog manual, pages 6 and 11–12](https://www.zilog.com/docs/z80/um0080.pdf)
specifies recognition of BUSREQ at machine-cycle boundaries; the current
host-slice approximation is not evidence of that electrical timing.
The [Motorola manual, section 6.1](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf)
describes STOP as a state without further memory references.

## Scope — 2026-10-11

The sound CPU used to timestamp all accesses at instruction start and add its
whole cycle cost at retirement. An authored `LD A,(nn)` test reproduced a data
request at T0 instead of T10. Word reads also used the high byte first, and
stack pushes used the low byte first. Final register comparisons alone could
not detect these shared native/reference defects.

The common private-source adapter now places opcode fetches (4T), operand
reads/writes (3T), port cycles (4T), and the intervening internal work. It covers
ordinary and repeated prefixes, indexed displacements, DDCB/FDCB's non-M1 final
byte, read/modify/write, stack operations, calls/conditional returns, exchanges,
block operations and nibble rotates. Native bodies still contain a fixed
operation; fetching its bytes performs bus cycles without decoding an opcode.
Opcode guards stay side-effect-free, while operands remain live reads.

Word reads use low/high order; pushes use high/low order. EX (SP) and IM2 preserve
their distinct transaction order. The Genesis IM0 FF acknowledge now costs 13T
and increments R once, instead of adding the RST cost and refresh twice. Other
IM0 data values retain an explicitly counted interpreter escape.

The arbiter advances the live Z80 timestamp per phase. Device waits remain extra
wall time; nominal instruction cycles are not charged again at retirement.
An impossible phase budget is reported as `z80_timing_misses`; conversion rejects
it even if native and reference runs agree with each other. Runtime counters
remain in memory and do not create player logs or directories.

## Local BUSREQ / BUSACK (2026-10-11)

BUSREQ now records a request edge; it no longer makes the status register report
ownership immediately. The running Z80 acknowledges at a nominal machine-cycle
boundary, including repeated M1 cycles in HALT. The 68000 yields after a local
bus-control write so the scheduler can order that edge against Z80 fetches,
operand cycles and internal extensions. Status reads and side-effect-free peeks
share the acknowledged state; a future boundary is not visible early.

A WAIT-extended banked transfer finishes once before BUSACK. A short request
pulse ending before the next boundary grants nothing. Releasing an acknowledged
request advances suspended wall time to the current /15 edge, without executing
the elapsed pause. An IRQ waits while ownership is held. Reset discards an old
continuation before restarting, as in the preceding release fix.

The actual PAL and NTSC backends each pass 1,801 authored bus assertions and 16
additional state/DMA-WAIT assertions. Literal local-cycle expectations cover
ordinary and indexed reads, extended PUSH/JR cycles, HALT, byte/word control
writes, short pulses, IRQ deferral and two host partitions. An actual 68000
program requests, polls and releases the bus. A pending handshake cannot become
an F8 state; stable ownership restores correctly. These are nominal Zilog-cycle
checks, not measurements of a Mega Drive board's synchronizer pins.

The finer suspension also exposed a diagnostic distinction: interpreter entry
can precede retirement by a whole DMA wait. `interpreted_opcodes` still signals
entry immediately. `retired_interpreted_opcodes` and `native_entries` count
completed instructions; native/reference validation compares their sum strictly.
It still rejects a missing or different retirement count. This avoids subtracting
an unfinished interpreter instruction from the native retirement counter.

Disk layout remains ABI-10. A pending request/live C continuation is excluded
from capture; stable BUSACK is reconstructed from the saved BUSREQ flag. The
previous qualified signature is explicitly accepted, not arbitrary signatures.
Current qualification evidence is in `.build/md-local-busack-20261011/`.
Sonic 1, Sonic 2 and Shining Force II pass five scenarios each with zero main/
sound fallback, zero impossible budgets and matching internal CPU/memory/image/
PCM results. Forty-four old states across eighteen signatures, packed F8/F9,
448-row interlaced replay and three copied-player SF2 routes pass. Seventy-five
targeted Python tests pass. Only the three exact-ROM records are refreshed;
the verified ROM-free snapshot remains unchanged and is embedded in the rebuilt,
audited local converter. Gameplay acceptance and physical latency are separate.


## Earlier phase evidence

- 28,544 native/reference instruction comparisons check registers, RAM, ordered
  reads/writes/ports, timestamps and total cycles, including modified operands
  and interrupt combinations. These use shared semantics and are differential
  evidence, not an independent CPU oracle.
- 36 separately authored literal phase sequences run on both paths and across
  cycle-counter wrap; eight additional cases check NMI and IM0 FF/IM1/IM2.
  This gives 152 independent cases, plus the existing guard/HALT/EI checks.
- 1,036 actual-backend assertions pass in each of PAL and NTSC. Unprimed Z80
  instructions test ordinary/indexed/prefix accesses with seven divider phases
  and three host partitions. Earlier 68000 arbitration fixtures explicitly
  execute the Z80's preceding cycles before their chosen request time.
- DMA, IRQ, memory-read, video, clock routing, battery SRAM and partial-state
  migration regressions pass against actual generated objects.

Literal expectations are derived from the [Zilog CPU manual, UM008011-0816](https://www.zilog.com/docs/z80/um0080.pdf)
and [Andre Weissflog's netlist timing analysis](https://floooh.github.io/2021/12/06/z80-instruction-timing.html).
The authored data is in `tests/fixtures/z80_phases.json`; neither it nor these
tests contain cartridge code. Upstream dependencies are not modified.

Local qualification evidence is in `.build/md-z80-phases-20261011/`. The bounded
game scenarios, fresh-process state replay and verified knowledge refresh are
recorded separately in its final `qualification.json`.

Sonic 1, Sonic 2 and Shining Force II pass five scenarios each with no main or
sound fallback, no impossible cycle budgets and matching internal CPU/memory/
image/PCM results. Packed F8/F9 replay, Sonic 2's interlaced attract sequence,
38 older states across 16 signatures and three copied-player SF2 routes pass.
The verified ROM-free snapshot is unchanged after refreshing the three records.
The rebuilt converter passes its resource/module audit; its normal installer
waits for the currently open old converter to close.

## Limits and continuation

These are nominal machine-cycle starts, not sampled electrical pins. In
particular, this does not establish exact board BR/BG/BGACK synchronizers,
turnaround, refresh/HSYNC, electrical local-bus handoff, or subcycle data-latch timing.
Guard revalidation when local or banked code is modified during a suspended
opcode/prefix fetch also remains a separate boundary. Pure local Z80 work can finish the current
instruction beyond a host slice; shared-bus requests suspend at their new
individual timestamps. No complete half-cycle CPU or board model is claimed.

ABI-10's disk layout is unchanged: phase accounting is transient, and an active
CPU continuation cannot be serialized. The previous signature is explicitly
accepted; unknown signatures still fail. User states and ROMs are read-only
inputs to qualification. Global collection campaigns remain paused.

Native coverage, CPU correctness, hardware timing, gameplay progression, and
physical audiovisual latency remain distinct evidence axes. Mega Drive is
supported within its standard cartridge scope; the remaining gates for
[the standard profile](CONSOLES_16BIT.md) are recorded there.
