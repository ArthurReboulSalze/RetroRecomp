# MC68000 prefetch and transaction phases

The step backend now retains a two-word instruction queue instead of charging
all instruction reads ahead of its operands. The queue is shared by native
execution and the reference CPU path. Stream reads use the suspendable main
bus, so a DMA or a Z80 grant can stop a fetch without replaying earlier effects.
Opcode dispatch remains separate: covered code executes translated bodies.

RAM guards use fetched words, including stale words after self-modification.
The selected body remains stable until retirement. MOVE extension words are
consumed at their actual stream phase, including a destination extension changed
after the source operand read. The compiled opcode and EA structure stay fixed;
the fetched extensions supply the operand values. Normal fallback reporting and
exact-ROM observation ownership remain in force. This does not introduce runtime
learning files into game exports.

## Independently checked scope

`python tools/megadrive_prefetch_selftest.py` uses 2,089 synthetic cases from
[SingleStepTests/m68000](https://github.com/SingleStepTests/m68000), pinned to
`64b253116a3de04aaac4346c43680960dc9b67e5`. The MIT fixture and source hashes
are in `tests/fixtures/md-prefetch`. No commercial cartridge is included.

Both paths must match initial/final registers, listed RAM, both prefetch words,
and every ordered bus read/write address, data, byte lane and cumulative clock.
The cases cover NOP, MOVE.B/W/L with two EAs, MOVEM.W/L in both directions,
ordinary CLR/ADD EAs, JMP/JSR, LEA/PEA, BSR, Bcc and non-expiring DBcc, plus
MULU/MULS/DIVU/DIVS across source EAs, signs, overflows and cost ranges. Exception
cases add TRAP, line-A/F, privilege faults, CHK, MOVE to SR and RTE. Selection
uses declared EA buckets and bus-error exclusions, never the runtime's results.
Authored additions check stale RAM, self-modification, an extension changed by
the source read, post-instruction trace and autovector entry. These authored
cases are separate from the external corpus. `authored.json` adds 82 literal
expectations: 60 DBcc outcomes including expiry, 18 arithmetic limits, two
post-arithmetic trace entries and two divide-by-zero frames. On DIV overflow,
the external comparison masks only N/Z, which Motorola explicitly declares
undefined. All other SR bits, preserved destination and bus phases remain
checked; authored overflow cases also check our deterministic N/Z convention.

MOVE generally fetches after its destination write; predecrement and ordinary
read-modify-write operations fetch before that write. JSR fetches the first
target word before stacking the return address. Control-EA totals and MOVE's
predecrement destination total were corrected using the independent traces and
[Motorola MC68000 tables](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
Conditional branch totals now distinguish their outcomes. MOVE source extensions
precede its operand read; destination extensions follow it. Absolute-long memory
destinations retain their late fetches. MOVE.L and MOVEM.L predecrement transfers
write the low word first. MOVEM totals distinguish direction, size, register count
and address calculation; memory-to-register forms retain the final discarded read.

DBcc expiry retains the discarded target fetch before the two fall-through
queue reads, for fourteen clocks. MULU counts source one-bits; MULS counts its
Booth transitions, following Motorola's 38+2n rule. DIVU/DIVS costs distinguish
early absolute overflow, sign paths and quotient-loop work. These helpers use
the runtime operands without decoding or interpreting a covered opcode. MUL
fetches its next stream word before its internal loop; DIV does so afterwards.
The unsigned divide high-word equality boundary signals overflow rather than
truncating a quotient of 65536. Divide-by-zero keeps its pre-frame wait; trace
uses the actual arithmetic cost before its own 34-clock entry. See the
[Motorola programming reference](https://www.nxp.com/docs/en/reference-manual/M68000PRM.pdf)
for division flags and overflow semantics. Cost formulas were separately
compared against all 2,915 non-trace, ordinary-bus arithmetic cases in the
pinned raw groups before the executable's selected transaction tests.

Synchronous frames write PC low, SR, then PC high before reading the vector.
CHK's two trap paths retain their different internal waits. Trace finishes the
ordinary instruction's stream phase before entering its own exception.

Autovector entry runs on the live main-CPU continuation: internal wait, PC-low
write, interrupt acknowledge, internal wait, remaining frame, vector reads and
target prefetch. Its nominal total is 44 clocks. The acknowledge uses the shared
suspendable bus and clears the pending source at that phase. The sequence was
cross-checked against [MAME's MC68000 state machine](https://github.com/mamedev/mame/blob/b1181f86023746b912dfc93ed65122a4cac89f49/src/devices/cpu/m68000/m68000-sif.cpp)
and the Motorola manual; it is not a measured Genesis pin trace.

The actual PAL/NTSC backend separately checks a Z80 write between the two operand
words of a MOVE.L with a primed queue, DMA suspension and stale-queue state
replay, plus interrupt suspension before and after acknowledge.
An additional fixture changes STOP's immediate with a Z80 write between MUL's
early and DIV's late read, including a suspended DIV whose F8 capture is blocked.
Explicit internal waits now yield at the main scheduler's deadline, including
MUL's internal-only tail. A Z80 reservation can overlap that internal work;
elapsed clocks are credited once, while a later external fetch still waits for
the bus. An unfinished calculation cannot become an F8 snapshot. The retirement
budget uses modular elapsed time when its 32-bit diagnostic counter wraps.

The actual-backend fixture checks MULU 0×1 and DIVU 0/1 with literal 40/136-clock
expectations, seven divider fractions, three host partitions and counter wrap.
It retains the result, nominal Z80 grant timestamp, work/wall clocks and safe
state boundary. This follows the separation of bus arbitration from internal
calculation in the [Motorola manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf),
section 5.3 and figure 5-20. The current arbiter still uses its nominal transfer
reservation; these checks do not measure BR/BG/BGACK synchronizers or electrical
turnaround. Residual instruction costs without explicit phase placement remain
separate work.
A cold queue's startup fetches consume time once, separately from the
next instruction's steady-state budget. Retirement still rejects impossible
bus budgets even when the internal reference shares the same error.

## Host preparation cost

Translated entries also carry an eight-byte preparation plan computed by the
recompiler. It contains invariant extension counts, EA waits and control flags.
The native path consumes this plan instead of rediscovering those decisions for
every instruction. Actual instruction reads, live SR/branch conditions, late
MOVE extensions, RAM guards and suspended bus transactions remain in their
original order. The reference path still derives its preparation from the
decoded instruction; entries without a plan retain that path.

After `tools/megadrive_prefetch_selftest.py`, run
`python tools/megadrive_prefetch_plan_selftest.py` to compare both preparations
on the same 2,171 synthetic cases. It also times repeated preparation separately
from gameplay. On the Debian test machine, that isolated workload took 0.609 s
with plans versus 0.680 s with dynamic preparation; this is not a framerate
measurement. The ordinary CPU, bus, DMA, interrupt and suspended-fetch checks
remain required. No console clock, audio sample or raster operation is removed.

## States and evidence

ABI-10 appends twelve pointer-free bytes to the CPU section: queue PC, valid
count and two words. F8/F9 preserves stale contents rather than reconstructing
them from current RAM. Partial queue counts, odd or inconsistent queue PCs and
invalid STOP values reject before CPU mutation. Live host continuations are
never serialized; both CPUs must reach a safe boundary.
An interrupt whose frame or target prefetch is incomplete also blocks capture.
A host poll preserves pending interrupts until the main continuation accepts
them. The layout remains ABI-10; the preceding qualified ABI-10 signature is
explicitly accepted, rather than accepting arbitrary signatures.

Previously accepted signatures and the previous ABI-9 signature have explicit
CPU-section migration. Older files have no prefetch history: their next queue
is primed from live memory, with startup bus time, rather than inventing stale
contents. This is architectural compatibility, not a claim that every old
microphase can be recovered. Current native/reference reports must also match
the queue hash; missing queue evidence cannot validate an export.

Targeted proof is retained locally in
`.build/md-idle-arbitration-20261011/qualification.json`. Knowledge is promoted
only after exact-ROM native/reference and bus-budget gates pass. Cartridge
probes, state replay and synthetic CPU traces are separate evidence axes.
Human visual/audio/gameplay acceptance and physical latency are not measured
by these checks.

## Remaining qualification

This is not a complete microcoded MC68000 or a measured Genesis pin trace.
The selected MOVE/MOVEM and exception phases above are qualified by synthetic
traces, not every possible instruction or interrupt condition. Other inherited
microphases remain outside this slice. The corpus does not deliver
post-instruction trace; that boundary uses
authored expectations. Interrupt electrical VPA/E-clock handshakes, level-7 edge
behavior and external vector devices remain unqualified. FC values are retained
in the oracle but are not compared: the current console bus does not route by
those pins. Odd
address/bus-error frames, TAS pin timing and TRAPV are outside this oracle slice.

Z80 operand/prefix phases and remaining unplaced 68000 internal phases,
BR/BG/BGACK synchronizers and board turnaround,
refresh/HSYNC/blanking slots, VDP port collisions, finer raster/IRQ/interlace
fields, other EEPROM/mapper circuits and broader gameplay remain separate
evidence areas. The supported standard profile completed its finite cartridge
qualification; finer electrical behavior is not claimed. See
[compatibility scope](COMPATIBILITY.md).

The cartridge follow-up qualifies [three EEPROM families](MEGADRIVE_EEPROM.md)
and [the Sega bank mapper](MEGADRIVE_MAPPERS.md), retaining already fetched
words across mapping changes and F8/F9. It also fixes shared bus declarations
and makes undeclared/mismatched boundary calls compilation errors.

The [MC68000 manual](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf),
table 8-14 and appendix B, separates nominal interrupt cycles from asynchronous
6800/VPA acknowledgement. E has a ten-clock period (six low, four high);
VPA recognition and setup relative to E can require additional waits. The
current four-clock nominal IACK is not a validated phase model for those pins.
This remains explicit work; no guessed board delays were added to the runtime.

The follow-up fixes one documented H/V interrupt collision. The VDP advances
through the end of the acknowledge transaction before retiring its currently
asserted source. If V arrives after the CPU selected H, V is acknowledged and H
remains pending; the CPU still uses its captured H autovector. This is Sega's
Software Development Manual, revision 1991-07-09, printed page 15
([original scan](https://gendev.spritesmind.net/files/md/tech/Genesis%20Software%20Development%20Manual%20%5BVersion%202.0%5D%20%5B1991-07-09%5D.pdf)).
`tools/megadrive_irq_collision_selftest.py` links the actual backend: each PAL
and NTSC build passes 184 boundary cases and 924 assertions, including selected
vector, stack frame, masked sources and the retained H request. This nominal
source-latch ordering does not qualify the electrical VPA/E-clock response or
the cross-device acknowledge wiring of external interrupts.
