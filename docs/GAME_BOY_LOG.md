# Game Boy: dated journal

The dated evidence behind [the Game Boy page](GAME_BOY.md), kept in the order it was gathered: the broader cartridge cases
of 9 October 2026 (with the Retro-Recomp 1.6.4 follow-up on writable-memory code), the build and correctness follow-up of
10 October, the shared APU corrections and the audio and input scheduling measurements of 11 October, and the conversion
timings and discovery measurements. The page holds the current state; this file holds the figures and their conditions.
Each section keeps the five measures apart (native code, CPU fidelity, hardware fidelity, gameplay validation and
physical latency) and says what it does not measure.

## Contents

- [Broader cartridge cases, 9 October 2026](#broader-cartridge-cases--9-october-2026)
- [Build and correctness follow-up, 10 October 2026](#build-and-correctness-follow-up--10-october-2026)
- [Shared APU corrections and audio scheduling, 11 October 2026](#shared-apu-corrections-and-audio-scheduling-11-october-2026)
- [Conversion timings and discovery measurements](#conversion-timings-and-discovery-measurements)
- [The earliest three targeted cartridges](#the-earliest-three-targeted-cartridges)

## Broader cartridge cases — 9 October 2026

Ten additional cartridges build successfully: Kirby's Dream Land, Super Mario
Land 2, Wario Land, Donkey Kong Land, Kirby's Dream Land 2, Link's Awakening,
Metroid II, Pokemon Red, Pokemon Yellow and Wario Land II. This expands the
local cases to MBC1, battery-backed MBC3 and MBC5; it does not exercise MBC3 RTC
or Game Boy Color-only behavior.

All ten pass the mandatory instruction-by-instruction boot and deep left/right
CPU comparisons. Regenerated cases also check the added varied path. Each export
passes an additional 6,000-frame varied-input probe and a save/close/relaunch
comparison of the entire serialized state after 180 resumed frames. Eight have
zero fallback cycles in that longer probe. Donkey Kong Land and Wario Land II
still execute some writable RAM code through the reported interpreter.

*Follow-up, Retro-Recomp 1.6.4.* For Donkey Kong Land the cause was a block of small trampolines that the game copies from its
cartridge into WRAM and patches (`LD HL,nn; CALL/JP ...`). Its opcodes (`LD rr,nn`, `LD A,(DE)`, `INC BC`, `ADD A,n`, `LD r,r'`) were not in
the pinned runtime's RAM stub, so each entry started an interpreter session that then kept interpreting the ROM routine it jumped to
(6,350 sessions and 3,160,836 interpreted cycles in a 6,000-frame boot probe, 388 sessions and 141,688 cycles in the varied probe).
WRAM/HRAM instructions outside the stub are now executed one at a time from their live bytes by a counted executor
(`rr_gb_try_ram_instruction`, checked opcode by opcode against the interpreter by `tools/gameboy_ram_selftest.py`). **That is not native
code**: it is a per-opcode switch, cheaper than an interpreter session, and the ROM routine the trampoline jumps to is native again. The
executor, the upstream RAM stub and the upstream stub for code run from 0xFF00-0xFF7F (a per-opcode executor too; the last two were never
counted before) each count their instructions and cycles per probe; the conversion report shows them beside the interpreter figures
(`ram_stub_*`, `ram_single_step_*`, `highmem_stub_*`), and while they are not zero the report does not claim zero fallback or native code
only. The deep CPU comparisons match. `CB`-prefixed opcodes, `HALT`, `STOP` and `RST` executed from RAM still use the reported interpreter.
Wario Land II was not re-run for this note.

*What the counts cover, exactly.* They cover the generated game's dispatch, where the three executors above run one instruction per call.
When the generated code does enter an interpreter session, the pinned interpreter calls the same stubs itself; the instructions they run
there belong to the session: its loop counts one instruction per iteration whether a stub or its own switch executed it, and their cycles are
part of the session's cycles, so they appear in the interpreter figures (already shown as interpreter use) and are not counted a second time
in the `ram_stub_*` or `highmem_stub_*` fields (`tools/gameboy_ram_selftest.py` checks both). The upstream HRAM stub is not counted: it
recognises the complete OAM-DMA wait routine by its bytes and runs it as one helper, like the guarded multi-instruction helpers of this
section, which are not counted either (the wait loop is batched into one call, so its instruction count would be a count of calls).

These cases improved the common runtime in two ways. A guarded native helper
handles a small writable store/increment routine, checking all live bytes and
the normal DMA/HALT boundaries; 5,777 authored CPU/memory/timing checks pass.
Generated cross-body jumps and calls now return to the native PC dispatch loop
instead of recursively consuming the host C stack. An authored loop completes
65,535 guest calls/returns with bounded host stack, matching 409,631 reference
steps and reporting no fallback. Pokemon Yellow exposed this stack overflow.

The varied input path also found ROM entries missing from the simpler scripts
in Wario Land and Link's Awakening. Late reference comparisons matched before
learning; their regenerated exports then reported zero fallback on that path.
Their observations are included in the [shared library](COMPILATION_LIBRARY.md).
The checks remain scripted paths, not completed games or independent PPU/APU
validation. The user performs visual, gameplay and listening checks.

Cold build time is still a limitation for large cartridges. In this parallel
batch, Wario Land II took about 24 minutes and Pokemon Yellow's corrected cold
conversion about 23 minutes, mostly compiling large generated C files over two
passes. The earlier Mario measurements below do not represent every cartridge.
Bundled observations can avoid rediscovery and another pass, but do not remove
the cost of the first C build. The October 10 follow-up below reduces generated
C and preserves unchanged build inputs; large cartridges can still take longer
than the small Mario example.

## Build and correctness follow-up — 10 October 2026

Build reductions keep the original generated instruction bodies and `/O2`:
regular dispatch pages use immutable native-function tables, and trivial entry
wrappers call their shared body directly. Custom/native replacement hooks are
left in place. Function declarations are local to the C files that use them,
so discovering another entry does not invalidate every file through the common
header. Generated entry selectors also avoid an MSVC 19.44 switch/goto codegen
failure reproduced in a cartridge's multi-entry body. Large entry sets use a
balanced tree; they must never become a linear chain of thousands of tests.
An authored 1,024-entry fixture checks all 65,536 possible PCs, including the
unchanged default path, under the native compiler.

The emitter still regenerates and adapts the complete project. An exact
SHA-256/content check restores modification times only for unchanged final
sources, allowing the C build system to retain their objects between passes
and regenerations. Changed sources, runtime headers and build options still
invalidate the corresponding objects. Qualification is always run again:
no saved result replaces the normal coverage or CPU comparisons.

Explicit diagnostic entry traces now record each `(bank, PC)` once per run.
A lazy 4 MiB bitset replaces repeated writes, including traces that previously
grew into gigabytes. No instructions, frames, fallback counts or distinct
entries are skipped. Exported interactive games still do not enable learning
or create these traces automatically.

Instructions spanning `3FFF/4000` or `7FFF/8000` now read their operands from
the live mapped bus instead of baking bytes from an adjacent physical ROM
bank. Supported forms stay native; an unsupported boundary form uses the
counted fallback rather than executing an assumed operand. Authored fixtures
exercise **47,104** CPU/memory/timing comparisons, including conditional calls
and jumps, multiple bank selections, flags and PPU phases.

Additional live-guarded native RAM helpers cover unrolled byte copies,
LCD-safe copy/fill loops and HRAM DMA page selection. Every added instruction
checks its complete live routine signature; operands remain live and changed
code keeps fallback. **28,277** authored checks pass, in addition to the
65,535-call bounded-host-stack regression. These helpers reduce reported
fallback without relabelling arbitrary interpreted instructions as native.

Controlled local build measurements used the same ROMs, installed dependencies,
`/O2` and `/MP4`. Donkey Kong Land's clean **C compilation** fell from 155.45 to
130.22 seconds (16.2% shorter); Super Mario Land's smaller build was essentially
unchanged at 24.69 versus 25.31 seconds. These timings cover C compilation, not
the entire conversion. Both before/after builds produced identical complete
state dumps after the same 7,200-frame input replay. Runtime replay times stayed
within 0.5% (about 5.6 and 6.0 seconds respectively), and the final builds passed
240-frame instruction comparisons. This does not measure physical latency.

Two consecutive full Mario regenerations, with a populated entry library,
took **80.02 and 62.25 seconds**. The first rebuilt changed sources; the second
reused every C object, reducing its build stage from 16.46 to **1.28 seconds**.
Both still completed four 7,200-frame coverage probes and all four deep CPU
comparisons (30 + 240 + 240 + 240 frames), with zero fallback in their probes.
The second run also reused discovery data; this is a regeneration result, not
an empty-library or first-time compilation benchmark.

Of the 17 exact cartridges rejected by the initial collection campaign, **14
now pass the complete targeted qualification**, 13 with zero fallback in their
four final probes. Max passes CPU comparison but retains writable-code fallback.
The bank-boundary correction resolves the five original operand mismatches and
a later CALL mismatch in TaleSpin. Captain America and the Avengers exposed
the native compiler selector failure described above; its final conversion
completed in 101.87 seconds with matching deep CPU comparisons and zero fallback.

Three exact cartridges remain unqualified: **Paperboy 2**, **Spiritual Warfare**
and **The Ren & Stimpy Show: Veediots!**. Their probes still hit the unchanged
600-second timeout, so their observations are not added to shared knowledge.
A timeout is retained as a symptom, not labelled as a proven CPU or mapper bug.

Additional qualified RAM-helper checks reduced the worst final-scenario fallback
cycle counts from 35,968,580 to 3,613,140 in Castlevania Legends, from 55,974,392
to 15,647,464 in TMNT III: Radical Rescue, and from 62,096,888 to 28,786,996 in
Track & Field. All three retain visible fallback; every deep CPU comparison
matched. No full-playthrough, independent hardware or listening validation is
claimed for this follow-up. Existing game exports were not replaced; regenerating
an affected cartridge uses the new compiler and runtime adaptations.

## Shared APU corrections and audio scheduling, 11 October 2026

Three checked adaptations to the pinned runtime fix missing rising-envelope
sound on pulse/noise channels, preserve pulse duty phase when a note is
retriggered, and stop noise LFSR clocks for NR43 shifts 14/15. They follow
[Pan Docs' APU details](https://github.com/gbdev/pandocs/blob/master/src/Audio_details.md).
No title-specific ROM patch, interpreter counter suppression, larger audio
target, or APU state-layout change is used. Existing quick states retain their
format. This does not complete the APU model: wave-channel behaviour, exact
timer low bits and analogue output still need separate accuracy work.

`tools/gameboy_hardware_selftest.py` builds the actual adapted runtime and
runs 21 authored APU checks through its public APIs. The original runtime
fails seven expectations; the adapted runtime passes all 21. The pinned
PPU dot-timing, OAM-DMA bus and APU chunk-invariance checks also pass. These
checks do not establish a cause for the sprite flicker reported in unspecified
games, and are not an audio listening or full-gameplay validation. Do not
hide possible original sprite-limit flicker with frame blending or extra sprites.

These are host-buffer and scheduling settings, not measured physical latency.
In the earlier 20 ms / 512-frame implementation, a local 600-frame scripted
Super Mario Land test with SDL dummy drivers showed that
the median sampled audio ring fill fell from 71.85 ms to 18.4 ms, with no
underrun samples in either ten-second run. The before/after guest state was
identical after 1200 headless frames with the same script; this checks that
the host changes preserved that execution, not independent APU accuracy.
`tools/gameboy_latency_selftest.py` checks real adapted input/audio code with
authored data, synthetic keyboard state and an SDL virtual gamepad.
Listening tests and physical input-to-display latency remain separate.
The subsequent Super Mario Land 2 qualification and output-delay measurements
are described in [Audio output](AUDIO.md#game-boy-output).

## Conversion timings and discovery measurements

A pre-optimization Super Mario Land conversion with dependencies already
installed and an empty game-entry library took 135 seconds in standard mode:
two passes, three final 3600-frame probes with zero fallback, and a matching 30-frame
CPU comparison. The earlier deep-validation conversion took 750 seconds.
The differential validator now uses a fast byte comparison for the common
matching case, while still checking all mutable memory and framebuffer bytes
after every instruction and locating the first differing byte on failure.
On the same generated Mario build, a 30-frame CPU comparison fell from 45.7
to 4.5 seconds. A new deep conversion took 103.9 seconds total with a populated
entry library and warm build cache: 57.7 seconds for 30 + 240 + 240 CPU frames,
and three 3600-frame coverage probes with zero fallback cycles. The earlier
full-conversion conditions differed, so those totals are not a controlled
speedup ratio. These are local measurements, not a time limit for every ROM
or computer.

To isolate the effect of learned ROM entries after this optimization, the same
deep conversion was repeated with an initially empty `RETRO_RECOMP_LIBRARY_DIR`
and the same local Mario ROM, installed dependencies and per-game build
directory. It imported **0 entries**, discovered 1,122 during the first pass,
and needed **2 passes**: 147.8 seconds total, including 70.2 seconds of C
builds, 17.0 seconds of coverage probes and 57.0 seconds of CPU comparisons.
With 1,150 entries imported, it took 103.9 seconds and one pass. The library
saved 43.9 seconds here by avoiding a second build and probe round; it did not
skip the 30 + 240 + 240 CPU comparison frames. Both final runs had zero
fallback cycles in their three 3600-frame coverage probes. The library test
began empty but still used the normal static ROM discovery.

On Windows, generated C files now compile with a bounded MSVC `/MP` job count
shared among concurrent games. The independent deep CPU scenarios run in
parallel when enough logical processors are available; every scenario still
compares the same frames, instructions and mutable memory. The converter keeps
the job count low when several games are processed together. On this 24-thread
machine, a full Mario build of the same generated sources took 30.7 seconds
without `/MP` and 14.2 seconds with `/MP4`. Parallel CPU scenarios took about
27 seconds of wall time instead of 57 seconds sequentially.

End-to-end Mario measurements with this change, installed dependencies and
three 3600-frame coverage probes per pass: **84.5 seconds** in deep mode from
an empty entry library (two passes), **55.8 seconds** in deep mode with 1,150
entries imported (one pass), and **33.0 seconds** in standard mode with those
entries. All final probes reported zero fallback cycles, and all requested CPU
comparisons matched the internal reference. Other games, full gameplay,
hardware behavior and physical input latency were not measured here.

Deep validation is the default from v0.15.0, including existing GUI installs:
previous preferences saved the old unchecked default automatically, so that
value migrates once. A user who unchecks it afterward keeps that choice. The
historical 750-second deep run versus the 55.8-second populated-library run is
over 10× shorter, but the cache and implementation conditions differ; it is
not a controlled speedup measurement across games. An empty-library deep run
under the current implementation took 84.5 seconds.

On Super Mario Land, two local 3600-frame input runs previously reported
44,272 and 60,656 interpreted cycles, all at ROM bank 3, address 7FF0. Extended
discovery compiles that JP relay before testing: both runs and the 3600-frame
boot reach zero fallback. The before/after state dumps match except for the
fallback counter. This is evidence for those paths, not whole-game coverage.

## The earliest three targeted cartridges

The earliest three targeted local cartridges were checked for 120 boot frames each:
Tetris (no bank switching), Super Mario Land (MBC1), and Lazlos' Leap
(MBC2 with battery RAM). Tetris and Lazlos' Leap reported zero
fallback cycles. Super Mario Land first reported one fallback at bank 0,
address `0322` (76 interpreter cycles); a later conversion reused its
converter-side entry trace and reported zero fallback cycles on the same
boot scenario. All three final executables matched their reference CPU for 30
frames. An isolated two-frame launch of Lazlos' Leap created no `datas`
folder, demonstrating that unchanged battery RAM is not flushed on exit.
MBC3 RTC persistence has no independent regression test yet. These checks do
not include a played level or a visual review.
