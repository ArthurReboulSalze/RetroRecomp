# Architecture

## Offline conversion

The Python converter identifies the ROM, loads verified compilation facts,
prepares local adaptations of pinned dependencies and emits C. CMake/MSVC
builds a game with ROM data, CPU code, hardware runtime and SDL2 host.
No JIT compiler is added to the resulting game.

`smsrecomp/systems` registers a console profile before a ROM reaches the batch
compiler. The Master System profile owns `.sms` identification, its PAL/NTSC
default, output category and backend adapter. New console modules must supply
their own parser, runtime and timing vocabulary. A video mode belongs to its
console profile, never to a global PAL/NTSC switch. See
[console profiles](SYSTEM_PROFILES.md).

Game Gear shares the Sega Z80 toolchain with its own VDP/control profile.
Original Game Boy uses a separate pinned SM83 recompiler and runtime; its
converter-only ROM entry traces live under a `gb` library namespace. Its
fallback report has instruction/cycle counts but no comparable cycle
percentage, and its CPU differential check does not validate the PPU/APU.
`gameboy_coverage.py` adds short ROM branch candidates to the compiler's
heuristic scan. Every pass probes boot and two scripted input paths; observed
ROM entries are deduplicated and merged across passes and conversions.
Static hints and observed entries remain distinct in the conversion report.
The default reference CPU comparison covers up to 30 boot frames; opt-in
deep validation adds up to 240 frames for each input path. These slower
instruction-by-instruction checks are independent of native discovery and
the three coverage probes, which run in both modes. Reports identify the
validation mode, checked scenarios and elapsed time for each conversion stage.

Nintendo NES uses a pinned 6502 cycle recompiler and a separate NTSC hardware
runtime. Its converter first compiles discovered ROM instruction starts, then
probes boot and two scripted inputs. Interpreter ROM misses are retained under
`library/nes/<ROM SHA256>/<engine revision>` for the next pass or regeneration.
The final short internal differential compares frame hashes of native execution
with the same runtime's interpreter. The report keeps exact remaining fallback
cycles; this is distinct from independent hardware fidelity and gameplay.
The source ROM, license notices and Windows icon are embedded as resources in
the game executable, while the engine checkout remains untouched. Battery
saves are written only after NVRAM changes.

Generated games share the RetroRecomp SDL menu canvas in `native/retro_menu.c`:
the 256 × 192 layout, pixel font and blue/fuchsia frame are independent of the
console CPU backend. The Sega `ui.c`, Game Boy `gb_menu.inc` and NES
`nes_host_ui.c` supply their
own actions and labels to that canvas. Game Boy builds copy these files into
each generated project's private runtime; the pinned upstream checkout is
untouched. Future compiler adapters can reuse the canvas rather than exposing
an imported runtime's settings panel.

The default banked backend translates supported instruction starts across
physical ROM banks. Guest PC and mapper state select the appropriate native
body, reducing dependence on discovering every indirect destination. The
classic function backend remains available via `--backend functions`.

## Runtime and fallback

The runtime maintains guest CPU state, bus, VDP, PSG, input ports, timing and
interrupts. Native execution uses those interfaces. Unknown instructions or
RAM variants can use the corrected reference interpreter. Fallback cycles,
in-memory dispatch observations and the window title make that use visible. Fullscreen
does not overlay interpreter diagnostics on gameplay.

## Input freshness and presentation

The Sega host's [audio output](AUDIO.md) uses a short causal sample-rate filter
and a bounded callback ring. Its buffering is separate from guest timing,
native CPU coverage and physical latency measurements.

Starting with 0.10.5, live windows expose an optional input-refresh callback
to the machine runtime. The Master System adapter calls it when the CPU reads
a controller port. The host refreshes keyboard and both gamepads together on
the main thread, at most once per millisecond during CPU execution. Frame
boundaries still sample after pacing, immediately before the next CPU frame.
This avoids holding an entire frame's old snapshot when fresh input is already
available during a longer CPU frame. It is a polling budget, not a claim of
1ms physical latency or a change to the controller's report rate.

The callback is absent in headless checks and is cleared on reset/shutdown.
It changes neither guest cycle timing nor scripted reference input. System
actions stay in the frame event loop so pause/reset can unwind safely. Other
systems can connect their own input-port/latch semantics to the same host
snapshot boundary; they must not read SDL or Windows APIs in generated CPU code.

On Windows the host prefers SDL's Direct3D 11 renderer, whose pinned backend
sets maximum queued frame latency to one, with automatic renderer fallback.
SDL's raw-input message thread is enabled by default. Explicit SDL environment
overrides are respected. The host reports the actual renderer and VSync flag
in its existing log; these settings do not establish input-to-photon latency.

Stick thresholds, button mappings, integer scaling, guest frame pacing and
frame content are preserved. Physical input-to-photon improvement still needs
a controlled hardware measurement. A higher polling rate cannot remove a
game's original input/animation delay or the display's scanout time.

## Light Phaser

The 0.10.6 Light Phaser adapter is another machine-side input endpoint. An
explicit cartridge catalogue embeds the peripheral choice during conversion;
the SDL host only supplies pointer/trigger snapshots. The C hardware adapter
exposes TL, TH and a latched H counter on the same ports to either CPU backend.
Its raster pulses use guest cycles, independent of window size and reticle
settings. In 0.10.7 the host draws the cross/dot overlay and its menu preview
with the same pixel-grid routine. Shape, common size and color are shared
presentation settings; game-generated gun flashes are preserved.
See [Light Phaser](LIGHT_PHASER.md) for selection, tests and fidelity limits.

In 0.10.8, `peripherals.game_tags` maps catalogue classification to stable icon
tag IDs. `artwork.ICON_TAGS` supplies their bundled graphics. The converter
composes badges separately at each ICO resolution, then embeds the complete
resource at build time. The tag choice is separate from gameplay input and
has no rendering or input work during play. Original box art is preserved.

## Improvement between generations

Starting with 0.10.9, the generated video core composes mode-4 lines along the
guest VDP timeline. CRAM and VRAM are used while each active line is processed;
horizontal scrolling is latched at line boundaries and vertical scrolling at
the next frame boundary. Two buffers preserve the completed display while
the guest prepares the next one. Presentation reads that completed buffer,
so vblank palette/VRAM updates cannot rewrite an already displayed frame.

The correction is part of `prepare_runtime` and `native/video_mode4.inc` for
every new Master System conversion. It has no title-specific switches. See
[video timing, authored checks and limits](VIDEO.md). This is a scanline model,
not pixel-clock-exact VDP emulation.

Starting with 0.10.10, a frame limit or host stop reached during a hardware
port callback is deferred until the current CPU step completes. Raster
synchronization still happens before the port operation. Native, reference
and fallback execution therefore stop with complete instructions, rather
than partial register updates. Reset clears the pending stop.

In 0.10.11, presentation can fill fullscreen at a fractional scale while
preserving the visible image's ratio. The same viewport maps mouse gun
coordinates and reticle placement. Integer mode remains the first F4 step.
Held-button autofire affects only mapped gamepad fire actions; each player
and button tracks its own simulated-time phase, without modifying cartridge
instructions or pacing the CPU with the host display.

Generated `.rc` resources also include Windows VERSIONINFO independently of
cover availability. Game title, console, controls and generator version use
standard description/product/version fields; the Shell chooses which fields
appear in its Details pane. No custom property handler or sidecar is required.

Observations are tied to ROM identity and checked against current ROM bytes.
Four-byte RAM windows encountered by fallback during converter probes are stored locally as
`native.patterns`. A later generation can compile those variants, with guards
checking the complete instruction bytes before selecting the native body.
Changed or unknown variants use fallback.

Each candidate is tested through two scripted scenarios, strict native checks
and comparison with the corrected reference CPU. CPU state, RAM, image and
VDP traces, including every completed frame's pixel hash in 0.10.9, are
compared. Both paths share the hardware runtime; agreement
alone cannot certify hardware fidelity.

Publication happens after successful checks. Regeneration replaces the same
filename; a running game is replaced after it exits. Converter observations and
settings stay outside the public repository.
If conversion reports were deleted, generated EXEs can recover their ownership
from the runtime's brand and unique embedded ROM SHA256. Regeneration keeps the
plain game filename and removes owned duplicates; unrelated files and other
ROM revisions are preserved.

## Responsibilities

In 0.10.13, ordinary game startup is read-only: path helpers resolve locations
without creating them, defaults stay in memory, and INI migration waits for an
explicit edit. F8 writes its per-game state directory; F9 reads without creating
it. Automatic run/miss logs are disabled; `--log` explicitly enables diagnostics.
Persistent learning is disabled in normal games. Only headless conversion
probes opt in with `RETRO_RECOMP_LEARNING=1`; even these reads create no library
directory until a new observation must be written. Interactive launch clears
that opt-in. Runtime fallback counters/window reporting remain active.

In 0.10.12, persistent quick states capture machine data at completed banked
instruction boundaries. A versioned, ROM-identified payload is validated in
full before applying it; guest PC dispatch then resumes the native loop.
Host handles/addresses and learning/telemetry are excluded. Generated
`runtime_audio.c` adapts the pinned PSG locally with an explicit state codec;
the dependency itself is unchanged. See [game-state format and limits](GAME_STATES.md).

| Area | Files |
| --- | --- |
| Desktop/CLI | `RetroRecomp.py`, `smsrecomp/gui.py`, `smsrecomp/i18n.py` |
| Console profiles | `smsrecomp/systems/__init__.py`, `smsrecomp/systems/master_system.py` |
| Conversion and CPU adaptations | `smsrecomp/core.py`, `smsrecomp/cpu.py`, `native/banked_*` |
| Learning and file identity | `smsrecomp/library.py`, `native/learning.c`, `native/manifest.inc` |
| Inputs and presentation | `native/host.c`, `native/controls.c`, `native/ui.c` |
| Video hardware | `native/video_mode4.inc`, `native/video_frame.h`, generated `runtime_video.c` |
| Covers and icons | `smsrecomp/artwork.py`, `native/icon.c` |
| Regeneration | `smsrecomp/batch.py`, `smsrecomp/publishing.py` |
| Validation | `smsrecomp/validation.py`, `native/*checks.c`, `tools/*selftest.py` |

AI exploration is a future direction. The current converter learns from
fixed conversion scripts; it does not ship a local LLM or AI player.
