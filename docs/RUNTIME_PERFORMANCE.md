# Runtime performance without changing the output

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
background-only pixel. PAL, the Zapper and the other boards keep the eager
clock but share the visible-scanline dot pair. MSVC builds apply link-time code
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
