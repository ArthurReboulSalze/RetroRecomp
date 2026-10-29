# Runtime performance without changing the output

## Mega Drive on Windows — 1.6.5

The Mega Drive on Windows now gets the build the Super Nintendo got on 26 October: the engine's own sources (not the generated
cartridge code) are compiled with ThinLTO and a clang profile taken from a private 1,800-frame `--play` run, on the portable
llvm-mingw tools (`retrorecomp/console16_optimization.py`, `CLANG_PROFILE_CONSOLES`; `RETRO_RECOMP_PGO=0` switches it off). The
Linux build of the Mega Drive was already profile-guided with GCC. It is a compiler change: the C code, the guest clocks and the
outputs are the same, checked by identical frame, audio and state hashes and report fields between the previous converter and
this one. **No gain is claimed**: it has not been timed, and it does not address the open slowdown reported on the low-power Debian
machine, which already ran the GCC profile build.

## NES — 1.6.5

Three changes to the NES runtime, none of them timed: the host cost is for the maintainer to measure on a quiet machine, and
none is claimed here as a gain.

- **MMC1: the bank tables are rebuilt on a change of PPU address line A12 only when the change can matter** (4 KiB CHR mode
  with registers 0 and 1 differing in bits 2 to 4). It was a rebuild at every change, several times per scanline. The same
  condition was taken upstream later; here it is carried on the pinned revision ([UPSTREAMS.md](UPSTREAMS.md)).
- **The cartridge's mapper number is a compile-time constant on every toolchain** (it was for GNU C on Linux only), so the
  per-cycle mapper tests fold on Windows too.
- **The deferred PPU clock also runs in PAL** (the boards that defer in NTSC, without the Zapper: NROM, UxROM, CNROM, AxROM,
  MMC1 up to 256 KiB and the like; the FME-7 of Mr. Gimmick keeps the direct clock because of its CPU-clocked IRQ counter). PAL
  dots and half dots fall at phases 0 and 2 of a 5-tick period over 16 ticks per CPU cycle; the edges are counted, in three
  runs per phase around the two sampling ticks (/NMI at 5, /IRQ at 9), and executed in order before anything can observe them,
  as in NTSC.

Checks: `tools/nes_mmc1_selftest.py` (13 boards), `tools/nes_static_mapper_selftest.py` (constant against run-time mapper, eight
mappers, NTSC and PAL) and `tools/nes_ppu_selftest.py`, which now has a PAL configuration without the Zapper, asserts which mappers
run the deferred clock, hashes the CPU and follows four vblanks from each alignment (it fails when /NMI is sampled on the wrong side
of the vblank dot, which the 2,800 earlier checkpoints did not catch). Real conversions with `tools/ab_conversion.py`, the tree
before the change against the tree after it with the same empty library: identical generated sources, reports and evidence (frame,
audio and state hashes): for the MMC1 change, The Legend of Zelda, Metroid, Dragon Warrior IV (up to its packing step) and
Balloon Fight (mapper 0, control); for the constant mapper, Metroid (MMC1) and Kirby's Adventure (MMC3); for the PAL deferral,
Asterix (UxROM), Elite (MMC1) and Mr. Gimmick (FME-7, direct clock) with Balloon Fight as the NTSC witness. Only the changed
sources and, for PAL and the constant mapper, the compressed size differ.

## Local follow-up — 26 October 2026

Super Nintendo on Windows: three changes, one of them for every game. Per-frame host cost on a
Ryzen 9 3900X, one pinned core, executables built by the previous and by the new converter
(`--play` from boot, 2,400 frames, best of three, runs interleaved):

| Game | Before | After |
|---|---|---|
| Super Mario World | 10.46 ms | 5.72 ms |
| Super Mario World 2: Yoshi's Island (Super FX) | 10.37 ms | 5.73 ms |
| Star Fox (Super FX) | 10.69 ms | 5.90 ms |
| Chrono Trigger | 8.62 ms | 3.88 ms |
| Super Metroid | 10.72 ms | 5.66 ms |
| Axelay | 9.10 ms | 4.32 ms |
| Secret of Mana | 11.75 ms | 6.26 ms |

Gameplay states of the Super FX games that were close to their frame budget:
Vortex 15.42 to 6.49 ms (budget 16.64), Doom 11.73 to 6.20 ms, details and checks in
[SNES_SUPERFX.md](SNES_SUPERFX.md#host-cost-26-october-2026).

- **ThinLTO and a clang profile** for the Super Nintendo hardware code on the portable llvm-mingw
  tools: the converter builds the game with instrumentation, runs 1,800 frames of the `--play` route,
  then rebuilds with the profile (the Linux build was already profile-guided). Where the training run fails
  the game is built without it; `RETRO_RECOMP_PGO=0` forces that. It is 45 % of the gain in Vortex,
  77 % in Doom and 94 % in F-Zero; the conversion takes as long as before because its validation runs on
  the faster executable.
- **The line renderer** decodes a background once per line in 8-dot runs, reads the offset-per-tile
  words once per column, tests windows once per line and drops layer priorities that have nothing to
  show; **the Super FX catch-up** is inline when it cannot start an instruction or the GSU is stopped.
  Each was checked against the previous code: 35 M random-scene comparisons of the dot walk (including
  widescreen margins) and 3,706 sliced-clock runs of the GSU cases; the identical outputs follow.

Checks: for Vortex, Doom and F-Zero every field of the report (frame, CPU, WRAM, VRAM, CGRAM, OAM, APU,
PCM, SRAM and cycle counters, GSU state) and the per-frame frame and audio hashes are identical to the
previous converter's over demo and `--play` runs of 1,500 and 3,000 frames (and a 5,000-frame authored
mission for Vortex); the same holds for demo and `--play` runs of the seven games in the table.
The converter's internal native/reference comparison matches. These are host costs on the measured routes,
not gameplay qualification, hardware fidelity or latency.

## Local follow-up — 22 October 2026

The NES PPU can now run late without changing what the CPU observes. On NTSC
boards without a PPU-address IRQ counter, a CPU-clocked cartridge device,
MMC5 or the Zapper, PPU edges are counted and executed afterwards in their
original order. This covers NROM, UxROM, CNROM, AxROM, MMC2/MMC4, Color Dreams
and similar boards, plus MMC1 with up to 256 KiB of PRG ROM. The edges run just
before anything can observe them:

- a PPU register or cartridge access;
- the dot that sets or clears vblank (/NMI);
- the next dot after a `$2002` read that clears vblank;
- the end of a frame, a quick-state save or a state hash.

MMC1's A12 hook still runs on every deferred dot, and its RAM bank is
synchronized before RAM accesses and RAM-code guards.

Deferred runs take unrolled 8-dot background tiles, sprite-slot fetches and
prefetch tiles. When no sprite unit can output during a tile, they use a
background-only pixel. The Zapper and the other boards keep the eager
clock but share the visible-scanline dot pair; PAL defers since 1.6.5 (below). MSVC builds apply link-time code
generation to the small machine core only, not to the generated 6502 code.

Checks:

- `tools/nes_ppu_selftest.py` adds an NTSC configuration without the Zapper,
  in which mappers 0 and 2 use the deferred clock. It now covers 67,200
  checkpoints in three configurations.
- The previous converter and the new one built 18 existing cartridge
  projects. These span 13 mapper identities, PAL, the Zapper and
  battery-saved boards, with saves cleared before each run. Every project
  produced byte-identical per-frame CPU, memory and hidden-hardware hashes and
  PCM on two 600-frame input routes and a boot run, both natively and with
  `--interp-only`.

Measured host time, with identical traces:

| Game | Machine and build | Before | After |
|---|---|---|---|
| Battletoads, deferred clock | Windows, Ryzen 9 3900X, one pinned core, 1,500 frames with audio | 14.07 s | 5.06 s |
| Kirby's Adventure, MMC3, eager clock | same | 11.53 s | 9.71 s |
| Super Mario Bros. | Debian AMD A4-5000, GCC LTO and PGO export build, 1,200 frames with audio | 19.45 s | 11.16 s |

These are host costs on the measured routes. They are not gameplay
qualification, hardware-fidelity evidence or a physical latency result. NES
quick states from earlier builds are rejected because the state ABI changed.
MMC3 and the other PPU-watching boards would need IRQ-time prediction to use
the deferred clock.

Master System and Game Gear received three changes:

- **Mode-4 line renderer.** It keeps its 32 host colors until CRAM or the
  palette format changes. Whole background tiles are decoded through
  256-entry plane tables, one for each horizontal flip, and their eight
  pixels and priority flags are stored at once. The sprite coverage arrays
  are cleared only on lines that have sprites.
- **PSG.** It now renders lazily: the same frames are produced from the same
  register values, in the same order. It catches up to the guest time the
  previous timeline had reached before each PSG write, before the line steps
  that drain it at the end of a frame, and before a quick state. Between
  channel events, a run computes only the low-pass recurrence.
- **Banked CPU loop.** It marks bank coverage only when the banks change, and
  advances the measured guest time inline when no line is crossed.

Checks:

- The 30,475,712-pixel corpus still matches the original renderer, including
  the status and collision flags.
- The previous converter and the new one built 15 existing projects: 12
  Master System (6 of them PAL) and 3 Game Gear. Per-frame VDP traces
  (pixels, VRAM, CRAM, registers, RAM) and the PSG WAV were byte-identical
  over 1,800 frames, both natively and with the reference interpreter.
- Persistent-state resume (NTSC and PAL) and the frame-stop I/O checks pass.

Alex Kidd in Miracle World, identical traces:

| Machine and build | Run | Before | After |
|---|---|---|---|
| Windows, one pinned core | 18,000 frames, PSG written to a WAV | 8.32 s | 4.26 s |
| Windows, one pinned core | 18,000 frames, without audio | 5.12 s | 2.94 s |
| Debian A4-5000 | 7,200 frames, with audio | 13.97 s | 6.99 s |
| Debian A4-5000 | 7,200 frames, without audio | 10.26 s | 5.94 s |

The Game Boy runtime was profiled as well. It already runs at about five
times real time on the A4-5000, and link-time code generation gave no gain,
so it is unchanged.

## Local follow-up — 18 October 2026

NES now selects the first ready opaque sprite from the existing byte-local
mask, removing the second eight-unit scalar search. A 262,144-case selection
corpus checks the scalar result and absence of state mutation; the full
44,800-checkpoint PPU/APU/video/bus/PCM comparison remains required.

A proposed 68000 prefetch-cache shortcut was rejected: its small MSVC gain
reversed on GCC on the same authored instruction corpus. No such shortcut is
retained, and no full-game speed improvement is claimed for it. The Debian
user reports Sonic is improved but not fully fluid and accepts this level for
now; further Sonic-specific work is paused in favor of global improvements.

Build throughput is separate from runtime speed. Compiler budgets are local
to concurrent game workers, and Game Boy hashes incremental generated files
with bounded buffers. Translation entries, native optimization and validation
budgets are unchanged. Matching source content alone restores its timestamp;
it never reuses an old qualification result.

Windows and Linux use the same runtime sources. The current optimizations
reduce repeated host work while retaining guest clocks, bus events, sprite
limits selected by the player, PCM samples and filter results.

- **Mega Drive:** prepare immutable 68000 bus plans during generation, avoid
  redundant Z80 scheduler transitions and batch VDP tile spans. Live fetches,
  RAM guards, bus waits and raster events remain in order. Audio recovery uses
  exact integer correlation, and the mixer/resampler avoids repeated divisions
  without changing its output. See the [Linux runtime notes](LINUX.md).
- **Master System and Game Gear:** decode a background tile row once per
  visible span, and a sprite row once per sprite. Scroll-lock boundaries,
  flips, palettes, priority and hardware collision/overflow flags are retained.
  No decoded row is reused across raster writes.
- **NES:** update the eight sprite counters and shifters together using
  byte-local integer operations. Every PPU dot still runs. Idle units, skipped
  dots and disabled rendering retain their original behavior.
- **Super Nintendo:** decode the bitplanes of each cached background row
  together. The existing per-line invalidation, main/subscreen selection,
  windows, mosaic, color math and special display modes remain in their callers.
- **All seven profiles:** share the same Scale2x implementation. SSE2 handles
  four input pixels at a time on x86-64; borders, partial viewports and padding
  retain the scalar result. Other architectures keep a scalar path.
- **Host audio:** the Sega 256-tap resampler retains its coefficients, ordered
  float products, double sums, rounding and sample timeline. SSE2 can process
  the two channels together. Game Boy and NES callbacks walk contiguous FIFO
  spans, retaining volume, mute, startup deadlines and recovery rules.

These are software cost reductions. They do not increase emulated CPU speed,
skip frames or samples, simplify an audio filter, or introduce an approximation
to the console state. They complement the existing xBR cache and Mega Drive
CPU/bus optimizations.

## Reproducible checks

Run these with the native Windows Python or Linux virtual environment:

```
python tools/pixel_optimization_selftest.py
python tools/snes_ppu_cache_selftest.py
python tools/nes_ppu_selftest.py
python tools/audio_selftest.py
python tools/nes_audio_selftest.py
python tools/gameboy_latency_selftest.py
python tools/frame_stop_selftest.py
```

The pixel corpus compares 30,475,712 pixels, 2,097,152 plane extractions,
65,536 exact FIR channel sums and 262,144 sprite-shifter states against scalar
implementations. The original Master System line renderer is retained under
`tests/fixtures/presentation` as the comparison oracle. The separate SNES
corpus checks 16,777,216 tile pixels and 7,864,320 resolved pixels. NES checks
67,200 hidden-state/video/audio/bus checkpoints over eight mapper identities,
four CPU alignments, PAL/NTSC and the deferred PPU clock. Audio schedule checks retain their full
timelines; small machines receive a longer test timeout rather than less work.

On the tested x86-64 machines, the isolated Master System row workload takes
about half its previous time, and Scale2x takes roughly one third to one half.
These are workload measurements, not whole-game framerate claims. The SNES
and callback changes have output-equivalence checks; no separate full-game
speed gain is claimed for them.

CPU/reference agreement, hardware fidelity, gameplay, desktop frame cadence
and physical audio/input latency remain separate evidence. Authored synthetic
checks do not establish universal cartridge compatibility or physical latency.
Linux ARM64 and legacy operating systems still require their own qualification.
The reported Mega Drive slowdown on the low-power Debian machine remains open.
No new full-speed gameplay result is established by these isolated workloads.

## Receiving the changes

Regenerate a game with the updated converter to include the new runtime.
The converter's source fingerprint detects these runtime changes even during
development at the same displayed version. Existing exports are unchanged until
regenerated. Ordinary cartridge saves and preferences remain separate from the
executable; quick states remain bound to their qualified runtime ABI.

These host optimizations add no cartridge observations to the shared knowledge
snapshot. Exact-ROM knowledge and fresh conversion checks retain their normal
roles; synthetic rendering results must not be promoted as game qualification.
