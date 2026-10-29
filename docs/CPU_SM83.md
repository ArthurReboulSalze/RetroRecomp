# SM83 (Game Boy CPU)

The 8-bit processor of the original Game Boy (also called LR35902 or SM83): ROM code is translated ahead of time to C
per (bank, address) entry, a few routines run from RAM have counted executors, and everything else goes through a
counted interpreter.

## Contents

1. [Used by](#1-used-by)
2. [Recompiler and upstream](#2-recompiler-and-upstream)
3. [How code is found and translated](#3-how-code-is-found-and-translated)
4. [What stays interpreted, and why](#4-what-stays-interpreted-and-why)
5. [Semantics and timing](#5-semantics-and-timing)
6. [Tests and vectors](#6-tests-and-vectors)
7. [Deep dives](#7-deep-dives)

The five measures are kept apart on this page as everywhere in the project: **native code**, **CPU fidelity**,
**hardware fidelity**, **gameplay validation** and **physical latency**. This page is about the first two; the video,
sound and cartridge hardware of the machine are on [GAME_BOY.md](GAME_BOY.md).

## 1. Used by

| Machine | Role of the CPU | Clock | Page |
|---|---|---|---|
| Game Boy (original DMG) | Main and only CPU | 4.194304 MHz; a frame is 70,224 cycles, about 59.7275 Hz | [GAME_BOY.md](GAME_BOY.md) |

Game Boy Color-only cartridges (header flag `$C0`) are rejected by the converter; cartridges that also run on the DMG
are converted as DMG games. No other machine of the project has an SM83. In the machine profile the CPU is declared as
`Cpu("sm83", "main", "cycles")`: the interpreter counters are in clock cycles at 4.194304 MHz (a `NOP` is 4 cycles).
The frame constant is in `native/hostkit/adapters/rrhk_gb.inc`.

## 2. Recompiler and upstream

- **Pinned repository**: [arcanite24/gb-recompiled](https://github.com/arcanite24/gb-recompiled) at revision
  `9150f87d82fa98abcb6ea22329170463f9702eb8` (`gameboy.ENGINE_REV` in `retrorecomp/gameboy.py`). Licence: MIT
  ([notice](../licenses/gb-recompiled.md)). The pin and its last review (identical upstream, kept) are in
  [UPSTREAMS.md](UPSTREAMS.md); no Game Boy item is deferred there.
- **What is used**: the compiler `gbrecomp`, which decodes banked programs and writes a C project, and the runtime it
  generates against (`runtime/src/gbrt.c`, `interpreter.c`, `ppu.c`, `audio.c`): the CPU context, the timed bus, the
  interpreter and the stubs for code run from memory. Generated code and the interpreter share the same runtime devices.
- **Our adapter modules.** The pinned checkout is never edited. Changes to the runtime sources are checked text
  replacements (`replace_once`) on the private generated project, which raise when the upstream text moved; the passes
  over the generated C (`gameboy_boundary.py`, `gameboy_build.py`) are regular-expression rewrites guarded by tests.

  | File | What it changes |
  |---|---|
  | `retrorecomp/gameboy.py` | The conversion loop: probes, passes, CPU comparison, report |
  | `retrorecomp/gameboy_coverage.py` | Extra discovery (JP/JR relays), the reproducible probe scenarios, the entry trace format |
  | `retrorecomp/gameboy_runtime.py` | The generated project: dispatch hook for writable-memory code, host-only counters, differential mode, input refresh, entry-trace de-duplication |
  | `retrorecomp/gameboy_boundary.py` | Instructions whose bytes straddle a bank window read their operands on the live bus |
  | `retrorecomp/gameboy_build.py` | Build-only reductions of the generated C (shared bodies, compact dispatch, unchanged files keep their objects) |
  | `native/gb_ram_helpers.h` | The guarded routine helpers and the counted executors for writable memory (`rr_gb_try_ram_dispatch`, `rr_gb_try_ram_instruction`, `rr_gb_try_highmem_dispatch`) |
  | `retrorecomp/gameboy_hardware.py` | Corrections of the APU (hardware, not CPU; see [GAME_BOY.md](GAME_BOY.md)) |
  | `retrorecomp/gameboy_host.py` | The host-kit shell of the exported game (not CPU) |

## 3. How code is found and translated

**Discovery.** The compiler scans every ROM bank with its own heuristics and compiles the entries it finds. A heuristic
scan can miss short functions, so the converter adds three sources of entries and passes them with `--use-trace`:

1. **Static relays** (`branch_entries`): every unconditional `JP nn` or `JR e` whose operands lie wholly inside one
   bank and whose target is below `$8000` is offered as an entry, independently for each byte, overlapping starts
   included. The cartridge header and logo are skipped. These are hints, not a claim that a byte is code.
2. **Observed entries** from the converter's library for this ROM, and from earlier passes of the current conversion.
3. **Entries reached by the probes.** Each probe records every `(bank, pc)` it enters once (`--trace-entries`); entries
   not yet compiled (those that ran through the interpreter among them) are added to the next pass, up to the pass
   limit.

The probes are reproducible: `boot`, `play_r` and `play_l` (right and left play; A pressed in both, B in `play_l`), and `varied`
(menu, movement and buttons, from 750 frames on). The *Extended* and *Thorough* scan levels add one or two
pseudo-random routes seeded from the ROM's hash; *Quick* skips the varied replay and the deep comparison.

**Compilation.** The unit is the entry `(bank, address)` in 16 KiB banks. Bodies keep the original instruction bodies;
dispatch pages are immutable tables of native functions, trivial wrappers share their body, and a large entry set uses a
balanced tree. Generated jumps and calls between bodies return to the program-counter dispatch loop instead of recursing
on the host stack. An instruction whose bytes cross `$3FFF/$4000` or `$7FFF/$8000` keeps its opcode as a native choice,
but reads its operands from the live mapped bus instead of baking the bytes of a neighbouring physical bank; an
unsupported form of this kind falls back through the counted interpreter instead of running with an assumed operand.

**Path shape** (`retrorecomp/path_profiles.py`, schema 3, CPU section `sm83`, map `gb`). Paths are numbers about the
ROM, never ROM bytes. There is one kind, `entries`, in 16 KiB units:

| Shape | Row | Meaning | Limit |
|---|---|---|---|
| `gb_offsets` | `(offset)` | `offset = bank * 0x4000 + (pc mod 0x4000)`; used when every row is ordinary (bank 0 below `$4000`, other banks in `$4000-$7FFF`) | 65,536 rows |
| `gb_rows` | `(offset, pc)` | The same offset with its address, for rows that do not fit the ordinary form | 65,536 rows |

The schema 1 equivalent is `rom_entries`, rows `(bank, pc)`. The local trace of a game is `entries.trace` with lines
`bank:address` (bank in decimal, address in hexadecimal, below `$8000`), beside `trace.json`, in the converter library
`datas/library/gb`. There is **no RAM-code kind**: what a game runs from WRAM or HRAM is never turned into an
unguarded ROM path ("Writable RAM and HRAM observations never become unguarded ROM code"). See
[COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md).

## 4. What stays interpreted, and why

Three different things can execute an instruction that is not an ordinary translated ROM entry body. They are kept apart
on purpose.

| Mechanism | Runs | Counted as |
|---|---|---|
| **Interpreter session** (the pinned runtime's `gb_interpret`) | A target the generated code did not compile: a ROM entry never reached, an unknown bank or page, or writable HRAM code. It keeps interpreting the ROM code the target jumps to until native dispatch resumes | Handoffs, entries, instructions, cycles, and one site per `(bank, address, reason)`; reasons are `address_not_compiled`, `bank_not_compiled`, `page_not_compiled` and `writable_hram` |
| **Counted one-by-one executors** (1.6.4) | One instruction of code living in WRAM, HRAM or `$FF00-$FF7F`, read live from its bytes, from a per-opcode switch | Instructions and cycles of each of three executors, per probe (below) |
| **Guarded helpers** | Whole small routines in HRAM or WRAM, recognised by a complete live signature | Not counted (below) |

**The one-by-one executors.** The pinned runtime has a RAM stub that covers only part of the SM83 opcodes. Any other
opcode run from writable memory (for example `LD HL,nn`, `LD A,(DE)`, `INC BC`, `ADD A,n` in a trampoline a game copies
from its cartridge and patches) used to start an interpreter session that then kept interpreting the ROM routine the
trampoline jumped to. Donkey Kong Land showed it: 6,350 sessions and 3,160,836 interpreted cycles in a 6,000-frame
boot probe. The generated dispatch now tries, in order, the guarded helpers, the upstream RAM stub, and our executor
`rr_gb_try_ram_instruction`. The executor handles 177 non-prefixed, non-branch opcodes (loads, 8 and 16-bit arithmetic,
rotates, `DAA`, `CPL`, `SCF`, `CCF`, stack operations, `DI`, `EI`) from the opcode and operands read live at each
execution, with the pinned interpreter's helpers, operand reads and cycle split. The instruction must lie wholly in
WRAM or HRAM; the HALT bug and WRAM code while an OAM DMA owns the bus decline. The ROM routine reached from RAM runs as
native code again.

That is **not native code and not ahead-of-time translation**. It is cheaper than an interpreter session, and it is
counted: the executor, the upstream RAM stub and the upstream stub for `$FF00-$FF7F` each count instructions and guest
cycles per probe (`ram_single_step_*`, `ram_stub_*`, `highmem_stub_*`). They are never added to the interpreter figures
and never hidden. While they are not zero the report says that some WRAM/HRAM and `$FF00-$FF7F` instructions run one
at a time by counted executors and does not claim zero fallback; the window adds "N RAM instructions executed one by
one (not native)" in the eight languages; the compiled-games view lists the game as having fallback. A report written
before 1.6.4 has no such counts; its flag is null (not measured), never false.

*Scope of the counts.* They cover what the generated dispatch runs. When an interpreter session calls the same stubs
itself, those instructions belong to the session: they are in its instruction and cycle figures and are not counted a
second time. Our executor does not take `CB`-prefixed opcodes, `HALT`, `STOP`, `RST`, illegal opcodes or code that spans
two memory regions: in WRAM and HRAM those stay with the interpreter. The upstream stub for `$FF00-$FF7F` does execute
`RST 00` to `RST 38`.

**The guarded helpers** are ahead-of-time bodies that run one live-checked instruction at a time inside a recognised
routine: the store-and-increment routine (`LD (DE),A`, two `NOP`, `INC DE`, `RET`), unrolled byte copies, the LCD-safe copy and fill loops, HRAM DMA page selection, and the
interrupt-bracketed sprite-DMA routine that the October 2026 collection campaign exposed. The complete signature, including the
backward-branch displacement, is checked before every added instruction, the DMA source page stays live, and any
changed byte, HALT-bug state or WRAM bus owned by DMA takes the usual fallback. The upstream HRAM stub, which matches the
whole OAM-DMA wait routine by its bytes and runs it as one batched helper, is grouped with them. **These helpers are not
counted**: ours are guarded native bodies, one live-checked instruction at a time; the upstream HRAM stub is batched, so
counting it would count calls, not instructions. They are named here so that "zero interpreter cycles" is never read as
"every instruction is a plain ROM entry".

The fallback percentage is deliberately not computed (`interpreter_percent` is empty): the upstream report gives no
defensible denominator of total cycles. The report gives the counts themselves, per scenario, and the sites.

## 5. Semantics and timing

- **Timing.** Every instruction advances the clock in cycles of 4.194304 MHz and the devices (timers, PPU, APU, OAM DMA)
  are stepped from it; memory accesses go through the timed bus. The executors reproduce the interpreter's split of
  cycles between the instruction and its bus accesses, including the read-modify-write forms (`INC (HL)`, `DEC (HL)`).
- **Behaviours the runtime models and the helpers respect.** The one-instruction delay of `EI` (`ime_pending`), the HALT
  bug (`halt_bug`; every executor and guarded helper declines in that state), `POP AF` masking the low flag nibble, and
  the OAM-DMA rule that WRAM code cannot run on the DMA's bus while HRAM can.
- **Interrupts and frames.** The existing interrupt and frame safepoints are kept by every helper; a quick state is
  taken between two frames.
- **CPU-side changes we carry on the pinned runtime** (CPU fidelity of the translated code only; none says anything about
  hardware fidelity, gameplay or latency):
  - writable-memory code executed one instruction at a time and counted: **1.6.4**, with the `gb` game stamp moving
    ([UPGRADES.md](UPGRADES.md#game-boy-exports-in-164-writable-memory-code),
    [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164));
  - the return of generated calls and jumps to the dispatch loop (a bounded host stack for a loop of 65,535 guest
    calls): **0.22.0**, 9 October 2026; the interrupt-bracketed sprite-DMA helper: **0.23.0**, 10 October 2026; live
    operands across bank windows, the copy, fill and DMA-page helpers and the `gameboy_build.py` reductions: **0.24.0**,
    10 October 2026 ([GAME_BOY_LOG.md](GAME_BOY_LOG.md)).
- **Known approximations and open items.** A hardware-level claim about the PPU, APU, MBC3 clock persistence or physical
  latency is not made here. The uncounted helpers above mean that "no interpreter cycles" describes interpreter sessions,
  not every instruction. No SM83 behaviour is claimed beyond the tested scenarios.

## 6. Tests and vectors

| Check | What it compares | Needs |
|---|---|---|
| `tools/gameboy_ram_selftest.py` with `native/gb_ram_checks.c` | Each opcode of the one-by-one executor, in WRAM and HRAM placements and from random states, against the pinned interpreter (registers, flags, memory, cycles, timed bus effects); the guarded helpers; the counters; the 65,535-call bounded-stack loop | a C compiler |
| `tools/gameboy_boundary_selftest.py` with `native/gb_boundary_checks.c` | Instructions crossing a bank window against the internal CPU (CPU, memory, timing) | a C compiler |
| `tools/gameboy_hardware_selftest.py`, `gameboy_latency_selftest.py`, `gameboy_display_selftest.py` | APU, PPU dot timing, OAM DMA bus, input and audio scheduling, the host's display settings and files; related, not CPU tests | a C compiler |
| `tests/test_gameboy_build.py`, `test_gameboy_coverage.py`, `test_game_boy.py` | Dispatch sharing, boundary repair, discovery hints, ROM identification | none (no ROM) |
| Conversion differential | Generated execution against the pinned interpreter, instruction by instruction (registers, mutable memory and framebuffer): 30 frames of boot, and with *Deep Game Boy validation* (the default) 240 frames of each input scenario; a mismatch blocks the export | the player's ROM |

Counts of cases, frames and cartridges, with their dates and conditions, are in [GAME_BOY.md](GAME_BOY.md) and
[GAME_BOY_LOG.md](GAME_BOY_LOG.md); they are not repeated here.

**What the evidence is.** The comparisons are between the generated code and the pinned runtime's own interpreter, which
share the runtime devices: they find divergence introduced by translation and by our executors, and they are not an
independent hardware oracle. There is **no independent SM83 vector set** in this repository (the independent sets pinned
by the project are for the Z80 and the 68000, [UPSTREAMS.md](UPSTREAMS.md)). The upstream project mentions external
suites and comparisons with another emulator in its own repository; they are not run by this one.

| Measure | What this page can say |
|---|---|
| Native code | Interpreter sessions, one-by-one executors and uncounted helpers are three separate lines; ROM code on the tested scenarios is ahead-of-time code |
| CPU fidelity | Generated code equal to the pinned interpreter on the tested frames; not independent |
| Hardware fidelity | Not measured here; see the machine page |
| Gameplay validation | Scripted probes, never a completed game |
| Physical latency | Not measured |

## 7. Deep dives

- [GAME_BOY.md](GAME_BOY.md): the machine, the host, scan levels, validation budgets and limits.
- [GAME_BOY_LOG.md](GAME_BOY_LOG.md): the dated journal with the figures of each campaign.
- [UPGRADES.md](UPGRADES.md#game-boy-exports-in-164-writable-memory-code): what the 1.6.4 executors change for exports and
  stamps.
- [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164): the pin, the scope of the counts, and the checks.
- [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md): how entries are kept, shared and requalified.
- [STANDARDS.md](STANDARDS.md): the separate measures and the criteria for "supported".
