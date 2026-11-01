# Zilog Z80

The main processor of the Master System and the Game Gear, and the sound processor of the Mega Drive, the Neo Geo and the
Capcom CPS-1. Three families of translators turn its instructions into guarded native C, count what they cannot translate,
and each is checked against a reference interpreter; the Master System and Game Gear one is also checked against an
independent vector corpus. This page covers the processor; the board, video and sound chips of each machine are on its own
page.

## Contents

1. [Used by](#used-by)
2. [Recompiler and upstream](#recompiler-and-upstream)
3. [How code is found and translated](#how-code-is-found-and-translated)
4. [What stays interpreted, and why](#what-stays-interpreted-and-why)
5. [Semantics and timing](#semantics-and-timing)
6. [Tests and vectors](#tests-and-vectors)
7. [Deep dives](#deep-dives)

The five measures stay separate ([STANDARDS.md](STANDARDS.md), rule 8): **native code** (how much of the Z80 runs as
translated C), **CPU fidelity** (agreement with the reference interpreter or with independent vectors), **hardware
fidelity**, **gameplay validation** and **physical latency**. Where this page says a run "matches", it is CPU fidelity
against the project's own reference or a software corpus on the scenarios run; it says nothing about the chip, about play
beyond those routes, or about latency.

## Used by

| Machine | Role | Clock | Status | Page |
|---|---|---|---|---|
| Master System | main | 3,579,545 Hz NTSC (the pinned `sms_clocks.h`), 3,546,893 Hz PAL (set by `retrorecomp/core.py`) | supported | [MASTER_SYSTEM.md](MASTER_SYSTEM.md) |
| Game Gear | main | about 3.58 MHz, NTSC timing only | supported | [GAME_GEAR.md](GAME_GEAR.md) |
| Mega Drive | sound | master clock divided by 15: 3.58 MHz NTSC, 3.55 MHz PAL (`native/md_timing.h`, `md_z80_bus.inc`) | supported | [MEGADRIVE.md](MEGADRIVE.md) |
| Neo Geo | sound | 4 MHz (Geolith divides its 24 MHz clock by 6) | supported | [NEOGEO.md](NEOGEO.md) |
| Capcom CPS-1 | sound | 3,579,545 Hz, the YM2151 clock (one YM2151 sample per 64 Z80 clocks) | experimental | [CPS1.md](CPS1.md) |

The profiles declare the processor as `Cpu('z80', 'main' | 'sound', unit)`. The interpreted share is counted in the unit
of the profile and never added across CPUs: **cycles** on the Master System, the Game Gear and the Mega Drive,
**instructions** on the Neo Geo and the CPS-1 ([CPU_68000.md](CPU_68000.md) covers the main processors of the last three).
The Master System and the Game Gear have no other processor, so their Z80 is the "main" one and the whole machine's
native share. Machines that would reuse the chain are listed under "Reuse by CPU" in
[NEW_MACHINE.md](NEW_MACHINE.md#reuse-by-cpu).

## Recompiler and upstream

The three families do not share a code generator. They share the rule that the pinned sources are never edited:
corrections are applied to copies made at conversion time, with strict replacements that raise when the pinned text is not
found. The Master System and Game Gear translator is also checked against the independent vector corpus; the Mega Drive
and Neo Geo/CPS-1 translators are checked against authored fixtures and the reference core.

| Family | Translator | Reference CPU | Pin | Licence |
|---|---|---|---|---|
| Master System, Game Gear | [mstan/smsggrecomp](https://github.com/mstan/smsggrecomp) generator and runner, patched at conversion time, plus our banked emitter | SuperZazu Z80 (`runner/external/superzazu`), corrected in a generated copy | `224d5bb` | no licence declared upstream; noncommercial permission reported by the project owner ([UPSTREAMS.md](UPSTREAMS.md)) |
| decoder and runtime headers of the above, and of the Mega Drive | [mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core) (submodule) | | `0e6606a` | PolyForm Noncommercial 1.0.0 |
| Mega Drive sound | SuperZazu helpers inside [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) (`runner/external/superzazu/z80.c`), turned into fixed-operation bodies by our emitter | the same source with our timing adapter | `00c60bc` | MIT for SuperZazu ([notice](../licenses/superzazu-z80.md)) inside a PolyForm Noncommercial engine |
| Neo Geo and CPS-1 sound | Geolith's own Z80 (`src/z80/z80.c`, also SuperZazu-derived), turned into fixed-operation bodies by our emitter | the same source | Geolith `2dc88e3` | MIT file inside BSD-3-Clause [libretro/geolith-libretro](https://github.com/libretro/geolith-libretro) |
| Independent vectors (development only) | [SingleStepTests/z80](https://github.com/SingleStepTests/z80) ([notice](../licenses/SingleStepTests-z80.md)) | | `ebe1875` | MIT |

Pins, licences, the last review and the rules for moving a pin are in [UPSTREAMS.md](UPSTREAMS.md). The PolyForm engines
are downloaded at their pinned revision on the first conversion and never copied into this repository.

Our adapters, all MIT:

- **Master System and Game Gear:** `retrorecomp/core.py` (`patched_generator_source`, `prepare_functions_irq`,
  `prepare_reference_irq`), `retrorecomp/cpu.py` (corrected local copies of the shared headers and of the reference CPU),
  and the native files `native/banked_emitter.inc` (appended to the pinned generator), `banked_runtime.inc`,
  `banked_dispatch.c`.
- **Mega Drive:** `retrorecomp/megadrive_z80.py` (emitter, guarded variants, reference adapter),
  `retrorecomp/megadrive_z80_timing.py` (machine-cycle placement), `native/md_z80_native.h`, `md_z80_runtime.c`,
  `md_z80_bus.inc`.
- **Neo Geo:** `retrorecomp/neogeo_z80.py` (emitter and its word-read adaptation), `native/neogeo_z80_native.h`.
- **CPS-1:** `generate_z80` in `retrorecomp/cps1_codegen.py` (it reuses the Neo Geo emitter), `native/cps1_z80_native.h`.

Every file's role and owners are declared in `retrorecomp/stamp_inputs.py`; editing one moves the game stamps of the
machines that own it ([UPGRADES.md](UPGRADES.md)).

## How code is found and translated

**Paths.** What a conversion learns is stored as numbers about your own ROM, never ROM bytes
([STANDARDS.md](STANDARDS.md), rule 11). Schema 3 (`retrorecomp/path_profiles.py`) keys a game by CPU and memory map; the
Z80 has one map per family. The Master System and the Game Gear share the same map, so the bounds are declared once.

| Map | Shape | Row | Bounds in the profile |
|---|---|---|---|
| `z80/sms` (Master System, Game Gear), source `rom` | `entries`, `sega5` | pc, three opcode bytes, a check value | pc up to $BF00, 65,536 rows |
| | `windows`, `window4` | an offset into the ROM of a four-byte window | 4,096 rows |
| `z80/md-sound` (Mega Drive), source `rom` | `ram_code`, `insn` | address, offset, length (always 4) | address in $0000-$3FFF or $8000-$FFFF, 32,768 rows |
| `z80/ng-sound` (Neo Geo), sources `m1` and `sm1` | `ram_code`, `insn_masked` | address, offset, length 4, guard mask | address in $F800-$FFFF, 32,768 rows |
| `z80/cps1-sound` (CPS-1), source `audiocpu` | `ram_code`, `insn_masked` | address, offset, length 4, guard mask | address in $D000-$D7FF, 4,096 rows |

**Master System and Game Gear: two engines.** The default **banked** engine translates, at conversion, every instruction
start of every physical ROM bank, including bytes that are really data; a translation runs only when the PC reaches it. Each
body is specialised for its bytes, constants and displacements, and identical encodings share one body. The PC, the Z80
stack and the mapper state stay explicit, so a `CALL`, a `RET`, a computed jump or a bank change in the middle of a routine
does not use the C stack as a stand-in for the console's. Variants across $0400, $4000 and $8000 are precompiled, and ROMs
that are not a power of two (24 KiB) are indexed modulo their size. Code run from RAM, and instructions that straddle ROM
and RAM, use a table of full encodings and every visit re-reads all the bytes it depends on. An unknown RAM variant goes
through the counted fallback; its four bytes are stored in the library under the ROM's SHA-256 and compiled on the next pass
(`window4` is the shared form of these windows; at most 4,096 per ROM). The loop compiles, tests and learns until a pass has no fallback
on the tested scenarios, stagnates, or exhausts its passes; `learning.native_profiles` in the report says which. The banked
engine supports the Sega mapper only and refuses other mappers. F8/F9 quick states exist with this engine only.

The optional **functions** engine (`--backend functions`) is the classic one: a static walk from verified entry seeds
(`sega5` rows), one C function per reached routine. Code the walk did not reach is run by the runner's counted hybrid
interpreter (calls and cycles, `interpreter_percent` in the report).

**Mega Drive sound.** The Z80 runs a driver that the 68000 uploads to its 8 KiB of RAM, so the code is mutable.
Generated bodies are fixed operations selected by the live PC and by guards on the bytes that choose the operation
(opcode, prefixes, the indexed `CB` selector). Immediate operands and displacements stay live bus reads, because drivers
rewrite sample pointers and loop counters in RAM. Probes capture up to four uploaded 8 KiB driver images when the Z80 reset
is released and precompile every supported position of them, including paths the demo did not take. At most 32,768
PC and opcode variants are stored for the ROM in the converter library.

**Neo Geo sound.** Every byte position of the cartridge sound program (`m1`) and of the BIOS one (`sm1`) is mapped to a
fixed operation; the mutable routine in the Z80's RAM at $F800-$FFFF is observed and guarded by a mask of its structural
bytes. Immediates, displacements, data and the 16-bit I/O ports are live accesses.

**CPS-1 sound.** The fixed ROM ($0000-$7FFF of the image) and the banked region at image offsets $10000-$17FFF are
translated at every byte position; the sound RAM at $D000-$D7FF is guarded the same way as on the Neo Geo.

## What stays interpreted, and why

The interpreter fallback is always counted, per CPU, and shown: the window title says "Native code" or "Interpreter
fallback", and the conversion report ([ARCHITECTURE.md](ARCHITECTURE.md#report-schema-2)) carries the counts per scenario
beside the five measures. On the Master System and the Game Gear, `--strict` refuses any recourse to the fallback, and the
conversion checks each zero-fallback claim against a strict run of the same scenario.

| Cause | Where | Effect |
|---|---|---|
| A RAM variant not yet observed, or one whose operation bytes changed | all | counted; the next pass compiles the new variant. On the Mega Drive, a changed opcode fetch continues from the byte already consumed, in the right semantic family, and the whole instruction's nominal cycles belong to that counted escape: no prefix, operand or access is replayed |
| Prefix chains longer than the four-byte guard window; uploads never seen | Mega Drive | counted fallback |
| An interrupt that puts an opcode on the data bus (IM 0) | Mega Drive | $FF is handled natively as `RST $38` (13 T-states, R incremented once); any other value is a counted escape |
| An interrupt that puts an opcode on the data bus (IM 0) | Neo Geo, CPS-1 | every IM 0 interrupt runs its supplied opcode on the reference core and is counted (CPS-1 since 1.6.5; the YM2151 interrupt supplies `$FF`, so it only arises when a sound ROM selects IM 0) |
| Code not reached by the static walk | Master System, Game Gear ("functions" engine) | counted hybrid-interpreter calls and cycles |

Not causes of interpretation, but limits of the same engines: mappers other than the Sega mapper are not converted by the
banked engine (Master System, Game Gear), and Game Gear cartridge saves are not validated.

A result of zero interpreted cycles or instructions is always "on the tested scenarios", never a promise for the next route.
The per-machine tables of games and routes are in the machine pages.

## Semantics and timing

**Master System and Game Gear.** The corrected reference and the translated bodies follow the NMOS behaviours the vector
corpus exposes: the undocumented X and Y flags, the internal WZ register, the Q latch (for `SCF` and `CCF`), the P latch
(for `LD A,I` and `LD A,R` followed by an interrupt), the interrupted block repeats, `DD`/`FD` prefix chains treated as
M1 fragments without recursion (chains of 4,097 prefixes are tested), the delay after `EI`, `HALT`, interrupt modes 0,
1 and 2, and the extra 5 T-states of a repeating `OTDR`. `BIT n,(HL)` is a read-only bus operation, because rewriting the byte is not
harmless at the mapper registers at $FFFC-$FFFF. Interrupt requests are sampled as a level at the start of each step, and
accepted after the instruction, the same contract in the reference and the banked engine. The VDP is synchronised at the
CPU time of each access. The corrections are made in generated copies by `retrorecomp/cpu.py` and `core.py`; the pinned
checkout stays clean.

**Mega Drive.** `megadrive_z80_timing.py` places the nominal machine cycles of the Z80 on the bus: three clocks for a
data read or write, four for an opcode fetch and for an I/O access, and the extra internal clocks of indexed addressing.
The Z80 shares the machine with the 68000: bus requests, the grant, the reset line, the banked window onto the 68000's
bus and the scheduler around them are modelled at nominal machine-cycle starts ([MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md)).
BUSACK reflects the control register, local-only Z80 execution can precede a 68000 control write inside a host slice, and
the model does not reproduce the electrical bus-request, bus-grant, refresh or HSYNC signals.

**Neo Geo and CPS-1.** Word reads are made explicitly low byte first, so the order does not depend on the C compiler. The
interrupt and NMI entry, the `EI` delay, `HALT` and the refresh register keep the canonical schedule. External IM 0 opcodes
run on the reference core (counted on the Neo Geo and, since 1.6.5, on the CPS-1).

**Fixes carried as our own patches.** The pins do not move, so the base of qualified paths stays valid; the game stamps of
the machines concerned move and their exports are rebuilt ([UPGRADES.md](UPGRADES.md)). All are CPU fidelity fixes.

| Release | Fix | Machines | Where |
|---|---|---|---|
| 1.6.3 | the "functions" engine no longer makes a direct C call to a paged address (at or above $0400); it goes through the dispatch that checks the bank mapped at that moment. The banked engine is not affected | Master System, Game Gear | `core.patched_generator_source` |
| 1.6.4 | `HALT` in the generated function: the interrupt that ends it pushes the address after the `HALT`, and a handler that dropped the halted frame ends the function | Master System, Game Gear ("functions" engine) | `core.patched_generator_source` |
| 1.6.4 | interrupt acceptance in the runner of the "functions" engine: sampled at one instruction boundary and accepted at the next, as the reference and the banked engine do; a VDP port access that changes the line brings the next sync to the next instruction; a `RET` that unwinds every generated frame continues at the address it popped | Master System, Game Gear ("functions" engine) | `core.prepare_functions_irq` (the reference sampling it matches, `core.prepare_reference_irq`, is older) |
| 1.6.5 | repeating block instructions that go on after an iteration set X and Y from the high byte of the instruction address (and H and P from B for `INIR`, `INDR`, `OTIR`, `OTDR`), as the banked engine and the reference do; visible when an interrupt pushes AF between two iterations | Master System, Game Gear ("functions" engine) | `core.patched_generator_source` |
| 1.6.5 | a `RET` (or a tail jump whose callee returned) below the function's own entry stack slot pops an address the function pushed itself: the generated code continues at that address as a nested call instead of resuming the caller | Master System, Game Gear ("functions" engine) | `core.patched_generator_source` |
| 1.6.5 | a jump that crosses a 16 KiB slot inside one generated function goes through the bank-checking dispatch (the bank of the other slot may have changed since the static walk) instead of a `goto` | Master System, Game Gear ("functions" engine) | `core.patched_generator_source` |

The 1.6.4 fixes let Alex Kidd in Miracle World, Factory Panic and seven more games pass the comparison with the "functions"
engine; they converted with the banked engine before. A game such as Action Fighter still fails that comparison for another
reason and keeps converting with the banked engine ([UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164)).
The other adaptations (block-repeat refresh of R, bank-modulo dispatch, the corrected reference copy, the Mega Drive timing
and escape, the Neo Geo word-read order) are described in the deep dives; their release is not recorded on this page.

**Known approximations.**

- Cycle counts are nominal per instruction. No electrical bus pin is modelled (Mega Drive), and the single-instruction
  vectors do not compare bus signals at each T-state.
- The vectors come from software emulators, not from a recording of a console.
- On the Mega Drive, the bus handoff is not a complete local-bus model: no BR/BG/BGACK synchroniser, turnaround or
  subcycle data-latch timing, and guard revalidation of code modified during a suspended fetch stays open
  ([MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md)). The 68000-side interrupt checks are on
  [CPU_68000.md](CPU_68000.md).

## Tests and vectors

Native self-tests build C and need a compiler ([BUILDING.md](BUILDING.md)); the vector corpus is fetched on demand into the
local dependency folder and never shipped.

| Check | What it covers | Run |
|---|---|---|
| Independent vectors | SingleStepTests/z80 at `ebe1875`, generated by JSMoo from Ares, MIT, not hardware captures. `tools/fetch_z80_vectors.py` keeps an evenly spaced sample of every instruction family; the machine code is translated by the production emitter, compiled and run on a 64 KiB test bus. Registers, documented and undocumented flags, WZ, Q, P, T-states, memory and visible I/O must match; the corrected reference passes the same corpus without masked cases | `tools/banked_vector_selftest.py`, `--reference` |
| Authored ROMs | paging, cross-bank instructions, guest returns, `LDIR` refreshing R at each repeat; expectations come from the Z80 program, not from the generated C | `tools/banked_selftest.py`, `tools/cpu_selftest.py` |
| Native against reference on real positions | the bodies for every position of a converted ROM against the reference, WZ, Q and P included (`banked_cpu_selftest.py`); the strict route audit of an export (`banked_verify.py`) | `tools/banked_cpu_selftest.py`, `tools/banked_verify.py` |
| Generator patches | the patched generator text contains each fix once; a changed pin fails | `tests/test_game_gear.py` |
| Mega Drive sound | authored opcode, RAM, bank and interrupt bodies; mutation of code under suspended Z80 fibers; guards and escapes | `tools/megadrive_z80_selftest.py`, `tools/megadrive_z80_resume_selftest.py`, `tests/test_megadrive_z80.py` |
| Neo Geo sound | ROM-free native ABI, cycle, memory, full-port and guard checks | `tools/neogeo_z80_selftest.py` |
| CPS-1 sound | native dispatch present in native builds only; board tests; the same 51,328 independent vectors replayed through the CPS-1 Z80 generator and its patched Geolith core, native and interpreted, results below | `tests/test_cps1_codegen.py`; `tools/cps1_z80_vector_selftest.py` (builds C, a few seconds once the corpus is cached), `tests/test_cps1_z80_vectors.py` |

The counts recorded for these runs (51,328 independent vectors over 1,604 family files; 28,544 Mega Drive comparisons plus
26,624 mutations; 14,352 Neo Geo comparisons) are those of [MASTER_SYSTEM.md](MASTER_SYSTEM.md),
[MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md) and [NEOGEO_LOG.md](NEOGEO_LOG.md) (and of the local maintainer notes
`NATIVE_COVERAGE.md`) on their dates; rerun the tools for today's.

**CPS-1 replay (30 October 2026, Windows).** `native/cps1_z80_vector_checks.c` runs each vector of the cached sample (51,328 vectors,
1,604 families, 32 each, corpus `ebe1875`) once through the CPS-1 translated Z80 bodies, dispatched by the patched Geolith core
exactly as in a CPS-1 game (with its byte guard), and once through the same core with every instruction interpreted, on a flat
64 KiB bus whose ports answer from the vector. It compares registers (WZ and the alternate set included), written bytes, ports and
the clock count with the vector, and the two paths with each other. P and Q are not compared (the core has neither).

- 38,433 vectors lie in the sound ROM windows and 1,615 in sound RAM: each ran as exactly one native step. 11,280 lie where the
  board has no native step (program counter from `0xC000`, outside sound RAM): each ran interpreted and was counted once.
- The native and the interpreted path agree with each other on all 51,328 vectors, state and clock. Against the vectors, both
  agree on 50,429 (98.2 percent) for the state and on 51,200 (99.7 percent) for the clock. The differences are the Geolith core's,
  shared by both paths, and are pinned in the tool (any change fails it until this page is updated): flags (535 vectors: `SCF` and `CCF`,
  the block instructions, `LD A,I` and `LD A,R`, the flags after `IN r,(C)`), WZ (480: `IN r,(C)`, `LD (nn),IX/IY`, `LD IX/IY,(nn)`,
  `JP (IX/IY)`), the port address of `OUTI`, `OUTD`, `OTIR` and `OTDR` (128), IM of the undocumented `ED 4E` and `ED 6E` (38), IFF1
  after `RETI` (16), and the clock of the undocumented `ED 4E`, `ED 6E`, `ED 77` and `ED 7F`. The table per family is in
  [CPS1_LOG.md](CPS1_LOG.md#30-october-2026-165-tree-z80-vectors-mame-again-and-a-linux-witness). Interrupt acceptance, the
  YM2151 and OKI lines and the board are not covered. The oracle is JSMoo, not silicon.

**Differential checks in every conversion.** Each conversion also runs its routes twice and compares the native run with a
reference that interprets every Z80 instruction: the corrected SuperZazu in lockstep on the Master System and the Game Gear
(final CPU registers with WZ, Q and P, RAM and the VDP trace of each frame must agree), the same Z80 core with every
instruction interpreted on the Mega Drive and the Neo Geo, and the fresh interpreted reference on the CPS-1. A mismatch
refuses the export and keeps the previous one. That is CPU fidelity against the project's own reference on the scenarios
run.

## Deep dives

- `NATIVE_COVERAGE.md` (local maintainer notes, in French): the banked backend of the Master System, its learning loop and its checks.
- [MEGADRIVE_Z80_TIMING.md](MEGADRIVE_Z80_TIMING.md): machine-cycle placement, changed code during a suspended fetch,
  STOP and the paused Z80.
- [MEGADRIVE_LOG.md](MEGADRIVE_LOG.md#mega-drive-native-sound-cpu): the Mega Drive native sound CPU.
- [NEOGEO_LOG.md](NEOGEO_LOG.md#reusing-the-existing-68000): the Neo Geo Z80 emitter and its guards.
- [CPS1.md](CPS1.md): the CPS-1 sound CPU and its comparison with MAME.
- [UPGRADES.md](UPGRADES.md#master-system-and-game-gear-the-functions-engine-164-lot-f): what the 1.6.4 "functions" engine
  fixes change for existing exports.
- [UPSTREAMS.md](UPSTREAMS.md): pins, licence rule, patches carried.
- [NEW_MACHINE.md](NEW_MACHINE.md#reuse-by-cpu) and [STANDARDS.md](STANDARDS.md): what a new Z80 machine reuses and must declare.
