# Architecture

## Offline conversion

The Python converter identifies the ROM, loads verified compilation facts,
prepares local adaptations of pinned dependencies and emits C. CMake/MSVC
builds a game with ROM data, CPU code, hardware runtime and SDL2 host.
No JIT compiler is added to the resulting game.

The Neo Geo development prototype shares the corrected 68000 generator helpers
and stack/exception helpers with Mega Drive, behind explicit board interfaces.
Multi-region cartridge/BIOS preparation, a reference MVS host and guarded native
P/BIOS/M1/SM1 instructions are implemented separately from the six supported
profiles. NAM-1975 has bounded zero-fallback native/reference qualification;
the prototype now uses the shared menus, two-player mappings, persistent
display settings and exact-cart/BIOS F8/F9 envelope. Production profile/knowledge
integration and wider hardware support remain separate. See [Neo Geo](NEOGEO.md).

The converter combines its local observations with the compressed, ROM-free
snapshot embedded in `Retro-Recomp.exe`. Records are bound to the console,
exact ROM SHA256, byte size and engine revision. Numeric hints and ROM offsets
do not bypass validation or live-memory guards. See the
[compilation library](COMPILATION_LIBRARY.md) for its schema and refresh workflow.

`retrorecomp/systems` registers a console profile before a ROM reaches the batch
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
heuristic scan. Every normal-length pass probes boot and three scripted input paths; observed
ROM entries are deduplicated and merged across passes and conversions.
Static hints and observed entries remain distinct in the conversion report.
The mandatory reference CPU comparison covers up to 30 boot frames;
deep validation, enabled by default, adds up to 240 frames for each of the three
input paths. These slower
instruction-by-instruction checks are independent of native discovery and
the coverage probes, which run in both modes. Reports identify the
validation mode, checked scenarios and elapsed time for each conversion stage.

Nintendo NES uses a pinned 6502 cycle recompiler and a separate NTSC/PAL hardware
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
console CPU backend. The Game Boy `gb_menu.inc` and the adapters of the host kit (`native/hostkit/adapters/rrhk_sms.c`
for the Master System and Game Gear, `rrhk_nes.c`, `rrhk_x68k.inc`) supply their
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

## Report schema 2

Seven converters write `conversion-report.json` in seven shapes: Master System
and Game Gear, Game Boy, NES, Mega Drive and Super Nintendo, Neo Geo, CPS-1 and
X68000. They count the interpreter in cycles (Master System, Game Gear, Game
Boy, NES) or in opcodes, under several key names, and the one-line fallback
summary is computed twice, in `batch.py` and in the window (`gui_queue.py`).
`retrorecomp/report_schema.py` defines schema 2, the one builder the writers go
through and the one reader of every shape. It is an interface module: no stamp
hashes it, because the report does not change what a game is or does.

- **Shape.** One section per CPU (main, audio) and per cartridge device, with
  interpreted counts per scenario in one unit, instructions. A writer that only
  counted cycles keeps them beside the counts under `cycles`, and the
  instruction count stays `None`. Counters of different CPUs or devices are
  never added together.
- **Five measures.** `validation` holds native code, CPU fidelity, hardware
  fidelity, gameplay and latency as five separate objects, each with a `claim`
  that is never stronger than the flag the writer stored. Scan level, routes,
  states, saves, the packed-executable check and the honesty flags have their
  own sections.
- **Writing (dual-write, one version).** Each of the seven writers ends with
  `write_report(path, report)`. It keeps every key the writer always wrote, with
  the same value, and adds `schema` (first), `read_from` and the sections above
  to the same document, derived from those keys by the code that reads an old
  report. It fills `created_utc` and `target` when the writer had none (Game Boy
  had no time; five writers had no target), and replaces the file atomically.
  `batch.py` adds its fields after the conversion (ROM hash, executable,
  packing, upgrade, shared paths, receipt) and writes again through
  `with_schema_v2`, which derives the sections anew, so they carry what was
  added. Every report has `scan_level` at the top (before 1.6.0 the Mega Drive, Super Nintendo
  and NES kept it under `advanced_scan` only, which is no longer read for the collection or the upgrade record). Keys the old shapes share with
  schema 2 are never written as null (`upgrade`, `export_receipt`, `target`,
  `created_utc`: old readers take a null for a value), and `knowledge`, which
  Neo Geo already used, holds that writer's keys and the schema-2 keys
  together. A later version drops the old keys.
- **Reading.** `read_report(data_or_path)` turns any existing shape, or a
  schema-2 document, into the schema-2 keys without guessing: a field a shape
  does not carry is `None`, never zero. A shape or schema number it does not
  know raises `ReportShapeError`. `fallback_summary(report)` returns the
  fallback figures of the batch result and the window; both read them from here.
  Their `lenient=True` reads a report as the callers always did, whatever the
  file holds beyond a `final_checks` list (an export of an older release, a
  report written by hand). `compiled_games.report_level` also reads
  `scan.level`; `freshness`, `knowledge_build`, `library` and the website read
  the old keys, which are still there.
- **Where the time goes (`timings`, 1.6.2).** The report carries one optional
  object, `timings`: `{phase: seconds, ..., "total": seconds}`, wall clock at
  0.1 s, written by `batch.py` (every write of the report refreshes it, so the
  last one holds the whole game). Schema 2 keeps its number: the key is optional
  on disk, a report from before it, or an object that is not a set of figures,
  reads `None`, and nothing else reads it. `retrorecomp/timings.py` is the one
  recorder (an interface module, no stamp hashes it): `batch._convert_one` starts
  it, each converter marks its steps with `timings.phase(name)` and its learning
  loop with `begin_pass` / `end_passes`, and without a recorder every call does
  nothing. Phases are disjoint (a phase opened inside another takes its time
  from it); what is in none of them is `other`, so the phases add up to `total`
  within 0.1 s each. The batch log ends each game with one line,
  `times: code generation 2.0 s, compile 40.0 s, ..., total 96.8 s`.

  | Phase | What it holds |
  |---|---|
  | `code_generation` | the translators and the analysis that write the game's C (Mega Drive and Super Nintendo: also the preparation of the build project) |
  | `compile` | CMake configure and build together; the host and runtime files and the generated code are one target, so they are not told apart |
  | `profile_training` | the short native run that guides the compiler (Mega Drive, Super Nintendo, NES) |
  | `native_runs` | the generated executable on the tested routes (also the strict-mode runs) |
  | `reference_runs` | the same routes on the reference interpreter, and the comparison; Neo Geo: the reference observation inside `compile_native`, with the writing of the native project files and the hints; Game Boy: the instruction-by-instruction comparison |
  | `reference_and_native_runs` | CPS-1, first pass only: the two kinds share one pool and are not told apart |
  | `packed_replays`, `state_checks`, `save_checks` | the compressed executable against the reference (Neo Geo, CPS-1); F8/F9 in fresh processes (Neo Geo, CPS-1, X68000); ordinary saves (Neo Geo) |
  | `packing` | UPX, wherever it runs (`packing.compact_executable`) |
  | `publication` | placing the executable, without its packing |
  | `discovery` | the learning passes after the first, whole; `0.0` when the game was built in one pass (what a quick check does); absent for Neo Geo, which has no passes |
  | `failed_quick_attempt` | a quick check that did not pass, before the full conversion |
  | `other`, `total` | the rest (ROM, artwork, hashing, report); the whole game, from the start of its conversion to the last report written |

  Master System, Game Gear, Game Boy, NES and the Mega Drive / Super Nintendo
  keep no F8/F9 check in their conversion, so they have no `state_checks`. A figure
  is one run on one machine, not a property of the game; the converters' own
  `conversion_phases_seconds` and `stage_seconds` keep their meaning beside it.
- **Two readings changed on purpose.** The summary's `main_interpreted_opcodes`
  carries the instruction count of the main CPU when the writer measured one
  (Game Boy: 900 where it read 0; the window still shows Game Boy in cycles),
  and a count the writer does not carry still reads 0. The X68000 report writes
  `reference_vdp_trace_match: null`: the key was a constant `true` that compared
  nothing, and the window has not read it for X68000 since the profile chose the
  opcode display.

## Input freshness and presentation

All seven console adapters stage the same `native/xbr_filter.h` and
`native/xbr_sdl.h`. The xBR host retains the previous source pixels and filtered
texture, dilates exact pixel changes by the filter's two-pixel radius, and
recalculates only affected 4x blocks. Resolution changes or failed texture uploads
invalidate reuse. There is no temporal blending or change to the filtered output;
the cache uses local process memory and creates no files. Source staging and the
converter resource manifest carry updates into regenerated exports for every
profile. `tools/xbr_selftest.py` checks cache equivalence across native and
high-resolution/interlaced sizes, padded strides, borders and resets.

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
| Desktop/CLI | `RetroRecomp.py`, `retrorecomp/gui.py` and `retrorecomp/gui_*.py` (the window, below), `retrorecomp/i18n.py` |
| Console profiles | `retrorecomp/systems/__init__.py`, `retrorecomp/systems/master_system.py` |
| Conversion and CPU adaptations | `retrorecomp/core.py`, `retrorecomp/cpu.py`, `native/banked_*` |
| Learning and file identity | `retrorecomp/library.py`, `native/learning.c`, `native/manifest.inc` |
| Inputs and presentation | `native/hostkit/shell/rrhk_*.c` (shared), `native/hostkit/adapters/rrhk_sms.c` |
| Video hardware | `native/video_mode4.inc`, `native/video_frame.h`, generated `runtime_video.c` |
| Covers and icons | `retrorecomp/artwork.py`, `native/icon.c` |
| Regeneration | `retrorecomp/batch.py`, `retrorecomp/publishing.py` |
| Validation | `retrorecomp/validation.py`, `native/*checks.c`, `tools/*selftest.py` |

### The window

The window is the `Application` class of `retrorecomp/gui.py`, assembled from
mixins that each hold one responsibility (standard 12). `gui.py` keeps the
constructor, closing, the single-instance check, the start-up picture and
`launch`, and re-exports every name the module had before the split.

| Module | Responsibility |
| --- | --- |
| `gui_common.py`, `gui_drawing.py` | shared constants and helpers; portraits, styled names, pins, badges, header themes, icons |
| `gui_window.py` | header, background, buttons, language, help, credits and legal notices |
| `gui_queue.py` | the ROM queue: restoring, dropping and importing paths, the list and its menu |
| `gui_conversion.py` | running a batch: preferences, start, stop, progress, results |
| `gui_collection.py` | converted games, new paths, going deeper and reconverting |
| `gui_updates.py` | updates of the converter and of the shared base, build tools |
| `gui_options.py` | the options window and its pages |
| `gui_sharing.py`, `gui_reports.py` | discoveries, the shared base and sending; problem reports |
| `gui_account.py`, `gui_leaderboard.py` | the player corner and sign-in; leaderboard, achievement and closing cards |

All of them are interface modules: no stamp hashes them
(`INTERFACE_MODULES` in `retrorecomp/stamp_inputs.py`). A test or a tool that
replaces a name of the window uses `tools/gui_patching.patch_gui`, which
patches it in every window module that has it, and reads the window's source
through `gui_source()`.

AI exploration is a future direction. The current converter learns from
fixed conversion scripts; it does not ship a local LLM or AI player.
