# Mega Drive video qualification

Full-plane vertical scroll now uses the two values fetched before the current
line's horizontal interrupt. Previously, rendering after CPU execution could
apply the following line's scroll too soon, producing visible bands even when
native/reference CPUs agreed. Live VSRAM remains available to guest reads and
the next row; two-cell column scrolling keeps its own path. There is no crop,
cartridge patch or new serialized field. An actual-game software-reference
comparison and 790,288 authored row-pattern assertions per PAL/NTSC backend
cover this correction.

The host now captures all 448/480 output rows produced by interlace mode 2,
alongside the existing 224/240 progressive modes and 256/320 widths. The display
uses the raster height for its aspect ratio, and the output height for textures,
filters and image validation. Integer scaling uses X=2n and Y=n in mode 2;
adaptive scaling keeps the full image on smaller windows. Gun coordinates
remain in raster units. No border is cropped to conceal a rendering defect.

The pinned renderer weaves both fields during each simulated raster frame.
This change qualifies capture, geometry and replay, **not** physical field
alternation, half-line timing, interlaced V-counter mapping or all raster effects.
Those remain separate work before the profile can be promoted.

## Counters and status

The H counter and HBlank now follow elapsed 68000/Z80 slice clocks. Reading
status cannot advance the beam. Read acknowledgement also clears the latched
sprite collision/overflow flags, while peek preserves them. Standard H32/H40
counter values were checked at all 3,420 master-clock positions against
[Genesis Plus GX's counter reference](https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/hvc.h).
Only numerical timing facts enter our implementation; the reference source
and comparison fixtures stay outside the packaged program.

HBlank boundaries use the published
[logic-analyser measurements by Nemesis](https://gendev.spritesmind.net/forum/viewtopic.php?p=17681#p17681).
Reads currently sample the instruction-start clock. IRQ delivery is scheduled
in raster slices, and unusual clock-divider settings are not qualified.
Agreement with a software counter reference is not a claim of exact board timing.

## Queued writes

Data-port writes now enter a four-word FIFO. Each entry retains its address,
command and value; the address register increments when a write is accepted.
Changing the command or auto-increment register cannot redirect an older entry.
VRAM commits one byte per slot (low byte first, including odd-address swaps);
CRAM/VSRAM commit a word. Palette callbacks occur on retirement. Full/empty
status follows queue occupancy; repeated reads cannot empty it without time.
The fifth write waits for the oldest complete entry, charging the accessing
CPU. Read access and timed DMA preserve preceding write order.

Active H32/H40 slots follow the published access pattern and numerical phase
reference. Blanked slots use nominal distributed bandwidth (167/205 slots per
line); exact blanking refresh/HSYNC phase is still unqualified. FIFO entries,
partial bytes and phase are pointer-free guest state, included in F8/F9.
The loader expands five qualified ABI-2 layouts and the preceding ABI-3 FIFO
layout with zeroed new fields; ROM, region, integrity and geometry checks remain
required.

This qualifies the write queue, not a complete cycle-accurate VDP. Exact prefetch
pipeline overlap, CPU instruction/bus access phases, Z80 main-bus contention and mid-line rendering
require separate work.

Hardware evidence: [Sega's software manual, access timing chapter](https://nemesis.hacking-cult.org/MegaDrive/Documentation/GenesisSoftwareManual.pdf),
[Kabuto's hardware measurements](https://www.plutiedev.com/mirror/kabuto-hardware-notes),
[Nemesis's VRAM logic-analyser observations](https://gendev.spritesmind.net/forum/viewtopic.php?t=851),
and [the separate numerical slot reference](https://github.com/ekeeke/Genesis-Plus-GX/blob/master/core/vdp_ctrl.c).
No reference engine code is incorporated into this queue implementation.

## Read prefetch

Read commands now schedule a pointer-free request instead of reading memory
only when the CPU accesses the data port. Older FIFO writes have priority.
CPU VRAM reads obtain the two bytes in successive external-access slots;
CRAM/VSRAM reads obtain a word in one slot. Internal serial tile fetches are
a different operation. This distinction follows the
[VDP port and prefetch description](https://raddad772.github.io/2024/07/21/genesis-vdp-pt-3.html),
alongside [Kabuto's observed buffering/address increment](https://www.plutiedev.com/mirror/kabuto-hardware-notes)
and [Mask of Destiny's bus measurements](https://gendev.spritesmind.net/forum/viewtopic.php?t=1291).
No external implementation is copied into the runtime.

The buffer retains the fetched value even if VRAM changes before the CPU read.
The address increments once when prefetch completes; consuming the value
starts the next request without fetching it immediately. A new command cancels
the previous request/buffer. Reads wait for availability and charge the accessing
68000 or Z80. FIFO waits also advance DMA/IRQ events on the shared clock.
No fixed pipeline-delay constant has been invented.

ABI-6 adds 16 bytes for the request, partial high byte and ready buffer. Pending,
half-read and ready states survive F8/F9 in a fresh process; malformed state is
rejected before machine mutation. The eight explicitly allowed preceding
signatures gain zeroed read fields; their existing FIFO/DMA migrations remain.
Snapshots cannot be captured or loaded while the CPU instruction guard is active.
Guest execution still yields at instruction retirement, preserving a safe
architectural resume point.

The precise prefetch pipeline, invalid-command lockups and control-port
address collisions remain unqualified. The transaction scheduling below now
replaces the former instruction-start stamps and whole-instruction bus grant.
It does not establish exact prefetch placement or electrical bus handshakes.

## Timed DMA and pending interrupts

External transfers fetch words from the main bus into the four-entry FIFO,
independently of destination access slots. A full FIFO suspends further fetches
until a complete entry retires. The main CPU resumes after the last source
fetch, while the FIFO can still hold a tail of destination writes. Older entries
keep their order and freshly fetched data cannot retire in its acceptance event.
VRAM words take two byte slots, while CRAM/VSRAM words take one. VRAM fill and copy continue while
the main CPU runs. Fill starts after its normal triggering FIFO write; copy
uses separate read/write slots. Length, destination and source registers update
as units are accepted (external DMA) or finish (fill/copy), including the 128 KiB source wrap. Transfers can span lines,
frames and quick-state reloads. The scheduler carries instruction overshoot
between lines and distributes the 68000 clock's fractional line budget.

Horizontal and vertical requests remain pending while disabled or CPU-masked.
Status reads preserve them. The accepted interrupt alone clears its latch;
vertical level 6 has priority over horizontal level 4. VINT and the Z80 pulse
use the measured CPU-visible H=02 transition in the first blank line. Acceptance
occurs between retired instructions, respects a held DMA bus, wakes STOP and
uses the existing supervisor-stack exception path.

The transfer rules follow [Kabuto's hardware measurements](https://www.plutiedev.com/mirror/kabuto-hardware-notes)
and [the hardware-tested fill sequence](https://gendev.spritesmind.net/forum/viewtopic.php?f=22&start=37&t=1291).
The separate source-read/FIFO pipeline also follows
[Mask of Destiny's corrected main-bus captures](https://gendev.spritesmind.net/forum/viewtopic.php?t=1563):
fetches depend on FIFO space rather than display-memory access availability.
Pending flags, priority and the CPU-visible VINT edge follow
[Eke's SDK test-ROM measurements](https://gendev.spritesmind.net/forum/viewtopic.php?p=11687).
These facts inform authored code and fixtures, rather than importing another
emulator's implementation.

This remains an access-slot model. Source reads use nominal distributed
bandwidth even during active display; exact source refresh/HSYNC and BR/BG/BGACK
handoff phases are not qualified. The destination tail uses existing access
slots, not a measured fixed pipeline-latency constant. Exact intra-instruction bus
phases, mid-transfer port collisions, pin-level IRQ latency and physical
interlaced fields are unqualified. The scheduler stops at source-bus release,
charges the wait to the next 68000 clock and uses the remaining slice budget.
It no longer delays resume until the next 1/16-line slice. Line-relative CPU
phases subtract the carried master-clock fraction. The main CPU can now yield
before a subsequent bus access inside the same instruction, including the
second word of a long write whose first word triggers DMA. See the
[measured bus request behavior](https://gendev.spritesmind.net/forum/viewtopic.php?t=2943).
Internal CPU/reference agreement shares
this hardware model and cannot independently prove those remaining details.

## Resumable DMA bus ownership

The 68000 waits before each real byte/word transaction while source DMA owns
the main bus. Its live coroutine retains the unfinished expression, so an
accepted first word is not executed twice when the second word resumes.
Interrupt delivery remains gated until instruction retirement. This qualifies
transaction ordering under DMA. Ordinary bus cycles now have separate nominal
timestamps as described below; instruction prefetch and pin-by-pin handoff
remain separate work.

Z80 execution has a separate live coroutine. Banked reads, writes and opcode
fetches wait for the external bus; local RAM, YM2612 and PSG execution continues
until an instruction actually needs that bus. A suspended instruction resumes
its existing local variables and side effects, including a changed stack pointer.
Local execution switches coroutines at scheduler boundaries. External requests
also yield to the arbiter, without switching for every local instruction.
Reset/load/shutdown discard the old Z80
coroutine instead of retaining a continuation into replaced guest memory.

The request-driven arbiter below replaces the former whole-slice DMA hold.
Local execution during DMA follows
[Kabuto's hardware observations](https://www.plutiedev.com/mirror/kabuto-hardware-notes).

ABI-9 keeps ABI-6/7/8's guest section size. F8/F9 requests wait for both CPUs
to retire before disk capture/load; neither coroutine stack enters the file.
Direct unsafe capture/load still fails without creating a file. Eleven explicitly
qualified preceding signatures can load; arbitrary old signatures cannot.
`tools/megadrive_bus_selftest.py` links the actual game backend and exercises
authored long writes across frames, Z80 banked reads/writes/opcode fetches,
BUSREQ, reset and the safe-state gate. Internal CPU agreement, hardware
qualification, gameplay and physical latency remain distinct.

## Request-driven CPU arbitration

A Z80 banked access now submits a timestamped request. The scheduler advances
the 68000 to a safe boundary, waits for an outstanding source DMA or VDP wait,
then reserves a nominal transfer on the shared bus. The transfer starts on a
68000 clock edge and completes on a Z80 clock edge. A reservation crossing a
slice retains its deadline; partitioning the host work cannot repeat or postpone
that same transaction. Earlier instruction effects remain on the live stack.
Local RAM/YM2612/PSG execution continues until an external access is required.

Source DMA can release the Z80 within the current slice, at the final source
fetch, while its destination FIFO tail remains queued. The initiating Z80 loses
elapsed wall time and the 68000 also loses the reserved bus time. Native guard
peeks are separate from actual generated opcode fetch requests, avoiding an
extra transfer solely for checking a guard. Existing VDP wait debt is consumed
before timestamping another access in the same instruction.

The nominal transfer occupies four 68000 clocks, following the ordinary bus
cycle in the [Motorola/NXP manual, section 5](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
This is an architectural scheduling model, **not** a measured Genesis arbiter.
The subsequent transaction work below permits a grant between nominal main-CPU
transactions. BR/BG/BGACK synchronizers, refresh and board-dependent turnaround
remain unqualified. No fixed 3.3/11-cycle measured average is applied as an exact
rule. Derived Z80 clocks are signed and line-relative, including pending requests
across the legacy 32-bit machine-counter wrap.

The actual PAL/NTSC backend has 194 authored checks, including release before
the first destination slot, partitioned reservations, pending F8/F9 rejection,
BUSREQ/reset, frame boundaries and counter wrap. Bounded cartridge comparison
and safe-state replay supplement these expectations; they do not prove full
gameplay, physical latency or pin-level fidelity. Evidence:
`.build/md-arbitration-20261010/qualification.json`.

## Ordered main-CPU transactions and persistent clock phase

The common adapter now charges four nominal 68000 clocks for each real byte or
word transaction. A long access has two ordered words, with a possible bus yield
between them. Instruction-word credits precede operand transactions; retirement
pays the remaining cycles instead of charging them twice. A Z80 writer can
therefore acquire the bus between the high and low words of a main-CPU read.
The already completed high word is retained on the live continuation. DMA and
device waits remain separate from these nominal clocks. TAS retains its nominal
read/modify/write lock; the Genesis board's TAS behavior is not yet qualified.

This follows the four-clock ordinary bus cycle and end-of-current-cycle bus
release in the [Motorola manual, sections 5 and 8](https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf).
It is not a complete two-word prefetch queue: crediting instruction words before
operands does not establish their real overlap with internal CPU work. Z80
operand/prefix microphases and electrical request/grant timing remain open.

The divider fraction and instruction retirement overrun now persist between
frames independently of the legacy diagnostic counter. Nominal clocks are
derived from total elapsed master clocks; a retired instruction's overrun is
subtracted from the next budget, rather than added again on every frame.
At the final line budget, an available bus permits the current instruction to
retire for portable F8/F9 capture. Earlier requests and DMA still suspend it
between transactions. Authored actual-backend checks cover split/whole execution,
a Z80 write between main read words, pending-state rejection, frame debt,
divider continuity through the 32-bit counter wrap and safe reload.

ABI-9 uses the old machine tail's four zeroed padding bytes for a flagged clock
word. The guest section and total state sizes do not grow. Old zero padding
loads through the explicit preceding-signature migrations; invalid new clock
words are rejected before machine mutation. Eleven preceding signatures are
explicitly accepted. Live stacks, pending requests and partial-instruction
cursors are still excluded from disk snapshots.

The added bus accounting exposed a shared CPU timing defect: many single-EA
instructions stored their operand in the decoder's source field, while timing
looked at its unused destination field. Memory TST/CLR/quick/immediate/bit/shift
families and register-to-memory ALU directions now use the actual operand.
CLR and Scc perform their discarded read before the write, retaining one
postincrement/predecrement update. `tools/megadrive_cycles_selftest.py` checks
55 authored cases with literal expectations from manual tables 8-5 through 8-8,
through native and reference execution. These cases isolate total instruction
clocks and memory side effects; they do not test a complete physical bus trace.

The first advanced cartridge qualification exercised this guard: Shining Force II
reached CMPM, whose inherited table had fallen through to four clocks. The
identical native/reference results were rejected. CMPM, memory ADDX/SUBX and
memory ABCD/SBCD now use their explicit manual costs, with authored byte/word/long
cases. Byte CMPM on either A7 operand also advances the stack by a word.
The failure remains in the private findings; it was not promoted to shared hints.

New conversion reports expose an internal bus-budget diagnostic. Any instruction
whose transactions exceed its total cycle estimate blocks qualification even
when both engines agree. Other inherited timing approximations still need
independent checks. The local evidence for this block is
`.build/md-bus-phases-20261010/qualification.json`; native coverage, internal
agreement, hardware checks, user gameplay and physical latency remain distinct.

ABI-5 retains ABI-4's 40 pointer-free DMA/IRQ bytes and the existing FIFO.
An ABI-4 word whose low byte already reached VRAM migrates into a partially
drained FIFO entry, without rereading its source. Previous ABI-2/3 layouts gain
zeroed fields. Only the seven qualified previous signatures are accepted;
bounds and migration feasibility are validated on a private copy before mutation.

## Reproducible checks

`tools/megadrive_video_selftest.py` renders authored tile patterns across all
16 mode/width/height combinations, checks the final output row, shrinking
buffers, row guards, aspect ratio and image hashing. The previous 240-row host
would drop 896 rows across those fixtures. `tools/megadrive_timing_selftest.py`
checks PAL/NTSC, horizontal discontinuities, HBlank boundaries, repeated
status reads, acknowledgement and 6,000 raster/audio ticks per standard.

Additional local checks exercise the actual backend using authored RAM loops
and F8/F9. Commercial-ROM native/reference comparisons, native coverage,
hands-on gameplay and physical latency remain separate evidence axes.
The supported standard profile completed its finite cartridge qualification.
Remaining electrical and VDP collision details are explicitly outside that scope;
see [compatibility evidence](COMPATIBILITY.md).

`tools/megadrive_fifo_selftest.py` reproduces immediate writes/constant FIFO-empty
in the pinned original VDP, then runs PAL/NTSC authored checks on the staged
VDP. These cover every active starting phase, partial bytes, occupancy, captured
commands, backpressure, scanline boundaries, read/DMA ordering and reset.

`tools/megadrive_dma_selftest.py` reproduces instantaneous bulk DMA and lost
VINT on status reads in the original backend, then runs authored PAL/NTSC
checks on the staged VDP. Source/FIFO separation, full-queue backpressure,
bus release before destination completion, phase-partition invariance, legacy
half-word migration, partial VRAM transfers, fill/copy, wrap, queue ordering,
pending IRQs, priority, acknowledgement and pulse timing have explicit expected
results. Actual-backend fixtures separately check exception stacks, a DMA
spanning a frame while the Z80 continues, H32/H40 resume within the first slice,
and cold/fresh-process snapshot replay. Own-RAM Z80 progress does not qualify
its accesses to a main bus held by DMA.

The current local qualification regenerates only Sonic 1, Sonic 2 and Shining
Force II. All five advanced scenarios per cartridge finish with no 68000/Z80
fallback and matching internal CPU, memory, image and PCM evidence. Sonic 2's
unmodified attract sequence additionally supplies a live 448-row capture check
against the reference path. This is an attract-mode check, not multiplayer
gameplay validation. Its newly reached entries are retained only after the
normal comparisons pass, then included in the ROM-free compilation snapshot.
