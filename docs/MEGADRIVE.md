# Mega Drive

Supported profile (`md`): the Sega Mega Drive / Genesis, standard cartridges, NTSC and PAL, with native 68000 and
sound Z80 code and a counted interpreter fallback. Supported means the written criteria of
[STANDARDS.md](STANDARDS.md#supported-checklist), met within the scope below; it does not mean exact hardware, a
full catalogue or measured latency.

## Contents

1. [At a glance](#at-a-glance)
2. [Structure of the machine](#structure-of-the-machine)
3. [Engine and upstream](#engine-and-upstream)
4. [In the project](#in-the-project)
5. [Controls and options](#controls-and-options)
6. [States and saves](#states-and-saves)
7. [Qualification](#qualification)
8. [Known limits](#known-limits)
9. [History](#history)

## At a glance

| | |
|---|---|
| Status | **Supported** within the standard cartridge scope (declared qualified in release 0.25.0, 11 October 2026; the evidence since then is in [QUALIFICATION.md](QUALIFICATION.md)). |
| What is converted | One cartridge into one standalone executable. Each known ROM instruction of the 68000 becomes a C operation with literal operands; the sound Z80 has its own guarded native path. Nothing is taken from a fixed game list: a cartridge is identified by its header and receives a profile generated from its own ROM. |
| Files accepted | `.md` and `.gen` (the profile's extensions); the reader also takes `.bin` and `.rom` that carry `SEGA` at offset `$100`, and a ZIP holding one cartridge. Linear images only, even size, from 32 KiB: up to 4 MiB, or up to 8 MiB for a declared Sega 512 KiB banked cartridge. Interleaved SMD is refused. The ROM is read, never modified. |
| Refused with a message | SVP cartridges (marker `SV` at `$1C8`), cartridges declaring 32X, Pico, Tera or MegaWiFi hardware, a header naming `SSF` that is not the exact `SEGA SSF` declaration, an image above 4 MiB without that mapper, an unrecognised region header. An unsupported serial EEPROM board does not stop the conversion: it is converted with a stated save limitation (quick states stay available). |
| Video standard | Read from the header region, never from the file name: a PAL-only header cannot be forced to NTSC. NTSC and PAL builds use their own line count and master clock. |
| Where games are written | The `Mega Drive` folder of the export tree (`export_folder` of the profile). Saves go to `datas/saves`, quick states to `datas/states`, beside the game. |
| Firmware needed | None. |
| Interpreter fallback | Always counted, per CPU: 68000 in opcodes, sound Z80 in cycles. The window title and the report say which CPU used it. |
| Options | The scan level (quick, standard, extended, thorough) and the converter's usual options; see [Controls and options](#controls-and-options). |

The five measures are kept apart on this machine too: **native code** (how much of the program runs as translated
code), **CPU fidelity** (the native and the reference path agree, and independent vectors where they exist),
**hardware fidelity** (the chips and the board), **gameplay validation** (sampled routes and owner trials) and
**physical latency** (not measured). Passing one proves nothing about the others.

## Structure of the machine

| Part | What it is | How Retro-Recomp handles it | Details |
|---|---|---|---|
| Main CPU | Motorola 68000, about 7.6 MHz (the master clock divided by 7) | **Native code**: every instruction found in the ROM is translated to a C operation with literal operands, executed on the real PC and stack. Work-RAM code is translated when its exact bytes were observed and is guarded at run time. Anything else goes to the counted reference interpreter. A two-word prefetch queue and ordered bus transactions are modelled. | [CPU_68000.md](CPU_68000.md), [exceptions](MEGADRIVE_CPU_EXCEPTIONS.md), [prefetch](MEGADRIVE_PREFETCH.md) |
| Sound CPU | Zilog Z80, about 3.58 MHz (master clock divided by 15), 8 KiB of its own RAM, driver uploaded by the 68000 | **Native code**: fixed-operation C bodies selected by the live PC and guarded by the opcode bytes (prefixes and indexed-CB included); immediate operands stay live reads, because drivers rewrite them. Changed code uses the counted reference path. Nominal machine cycles are placed inside each instruction. | [CPU_Z80.md](CPU_Z80.md), [Z80 timing](MEGADRIVE_Z80_TIMING.md) |
| Buses and arbitration | 68000, Z80 and VDP DMA share the main bus; BUSREQ/BUSACK, Z80 reset, banked Z80 window into the 68000 space | **Engine runtime** adapted by our checked modules: the two CPUs alternate sixteen times per scanline on one request-driven arbiter; DMA source fetches and destination slots are separate; a long 68000 access can yield between its words. BUSACK is dated at the end of the sound CPU's machine cycle in progress at the request, also when the sound CPU already stands ahead after a line end (since 1.6.5). Electrical bus signals are not modelled. | [video and bus](MEGADRIVE_VIDEO.md), [Z80 timing](MEGADRIVE_Z80_TIMING.md) |
| Video | VDP: planes, sprites, 64 KiB VRAM, CRAM, VSRAM, H32 (256) and H40 (320) widths, 224/240 lines, interlace mode 2 (448/480 rows) | **Engine runtime** (C), rendered per scanline, with our corrections: four-word write FIFO with backpressure, timed and resumable DMA, read prefetch, H counter and HBlank from elapsed slice clocks, level-sensitive interrupts. The host captures the full interlaced image. Not a dot-accurate or cycle-accurate VDP. | [MEGADRIVE_VIDEO.md](MEGADRIVE_VIDEO.md) |
| FM sound | Yamaha YM2612 | **Engine runtime** (ymfm). We add the CPU-visible timers A and B (timer A every 1,008 master clocks, B every 16,128). BUSY status and timer-driven CSM synthesis are not complete. | [history](MEGADRIVE_LOG.md#mega-drive-sound-scheduling) |
| PSG | SN76489 | **Engine runtime**: the clean-room SN76489 of the pinned engine. | |
| Work RAM | 64 KiB, decoded across the 32 aliases of `$E00000-$FFFFFF` | Bus reads and writes, instruction fetch, Z80 access and VDP DMA see all aliases; the saved memory and the generated bodies are not multiplied. Instructions at the very end of work RAM are translated too. | [history](MEGADRIVE_LOG.md#mega-drive-cartridge-saves) |
| Cartridge ROM | Linear up to 4 MiB; Sega 512 KiB bank mapper up to 8 MiB (`SEGA SSF` header or product `MK-12056`) | The whole declared ROM is decoded; native bodies are indexed by physical offset and relocated to the current logical address. Banked Z80 reads and DMA use the same mapping. | [MEGADRIVE_MAPPERS.md](MEGADRIVE_MAPPERS.md) |
| Cartridge RAM | Ordinary battery or volatile RAM (word, even-byte or odd-byte layouts, up to 64 KiB, overlay register, write protection) | Initialised in our host adapter after the ROM is loaded; saved in an exact-ROM container. Invalid declarations get a preflight message. | [States and saves](#states-and-saves) |
| Serial EEPROM | X24C01, X24C02 and 24C04 on Sega, Acclaim 16 Mbit and Acclaim 32 Mbit wiring | An original wire model (`native/md_eeprom.h`) with a deterministic 5 ms write time in guest clocks, selected by product and header. Other boards keep a stated limitation. | [MEGADRIVE_EEPROM.md](MEGADRIVE_EEPROM.md) |
| Controllers | Two ports; three-button and six-button pads | The six-button pad is a property of the game (the `6` in the header's device field, or a catalogue entry). No multitap, mouse or other port device exists in the converter. | [Controls](#controls-and-options) |
| Light guns | Menacer (qualified), Konami Justifier | Mouse on port 2 as a gun; sensor, TH line, counters and the level-2 interrupt modelled. The catalogue knows Menacer 6-Game Cartridge, T2 - The Arcade Game, Body Count and the two Lethal Enforcers games; only the first two are gameplay-tested. Justifier has pins and tests, no validated cartridge. | [GUNS_16BIT.md](GUNS_16BIT.md) |
| Region and timing | NTSC: 262 lines, 53,693,175 Hz, about 59.92274 frames/s. PAL: 313 lines, 53,203,424 Hz, about 49.70146 frames/s. 3,420 master clocks per line | Video, audio-chip clocks, status bits and the host deadline use the selected standard. A Japan-only cartridge selects the domestic NTSC version register; a multi-region one prefers overseas NTSC. | [video](MEGADRIVE_VIDEO.md) |
| Not supported | SVP, 32X, Pico, lock-on cartridges, other special mappers, Mega-CD | Refused with an actionable message (see [Known limits](#known-limits)). | |

Where a row says "reference", it means the path that interprets every instruction from live bytes. It shares the
hardware model with the native path, so agreement between them checks the translation, not the hardware.

## Engine and upstream

The converter does not own a Mega Drive recompiler: it pins and adapts [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp).
The table and the review record are in [UPSTREAMS.md](UPSTREAMS.md); the licences are in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and [segagenesisrecomp.md](../licenses/segagenesisrecomp.md).

| Upstream | Pin | Role here | Licence |
|---|---|---|---|
| [mstan/segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) | `00c60bc` (`console16.REPOSITORIES['md']`) | Recompiler and runner: 68000 instruction bodies (shared with Neo Geo, CPS-1 and X68000), VDP, bus, YM2612 and PSG glue. Its Mega-CD code (`runner/cd/`) is not used. | PolyForm Noncommercial 1.0.0 plus the vendored licences it retains |
| [mstan/m68k-recomp-core](https://github.com/mstan/m68k-recomp-core) (submodule) | `921f67b` | 68000 decoder | PolyForm Noncommercial 1.0.0 |
| [mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core) (submodule) | `0e6606a` | Z80 headers and sources, also used by Master System and Game Gear | PolyForm Noncommercial 1.0.0 |
| [RetroPortingToolKit/rbengine](https://github.com/RetroPortingToolKit/rbengine) (submodule) | `2a03e73` | Rollback engine; initialised with the checkout, nothing compiled | MIT |
| [SingleStepTests/m68000](https://github.com/SingleStepTests/m68000) | `64b2531` | Test vectors for prefetch and exceptions (generated from MAME, not measured on hardware) | MIT |
| [SingleStepTests/z80](https://github.com/SingleStepTests/z80) | `ebe1875` | Z80 test vectors (`tools/fetch_z80_vectors.py`) | MIT |

The pinned engine also brings ymfm (YM2612, BSD-3-Clause) and the superzazu Z80 reference core (MIT); the notices
travel inside each game executable. RetroRecomp's own MIT licence does not replace the engine's terms.

**How the engine is adapted.** The pinned checkout under `.deps` is never edited. At conversion time the modules
`megadrive_*.py` rewrite checked private copies of the engine sources (a strict replacement fails closed if the pinned
text changes); the generated project then compiles those copies with the native files of `native/md_*`.

**Our patches.** Fixes to the 68000 are carried as our own patches in `m68000.adapt_semantics`, which Neo Geo, CPS-1 and
X68000 share: since 1.6.3, `ROXL`/`ROXR` with a register count of zero (X copied to C) and `ASL.L` by 31 (overflow
mask). There is no Mega Drive-only patch in 1.6.4. Since 1.6.5 there is one: a register-count shift or rotate
(`Dx,Dy`) is charged its manual time (`6 + 2n` clocks for a byte or word, `8 + 2n` for a long, `n` the count modulo 64),
by `megadrive_codegen.adapt_shift_timing`, in the native bodies and in the reference path, through the `MULU`
order (prefetch read first, then the internal clocks); the shared `m68000.py` is untouched and the other machines already charged this time.

**Open at the upstream.** A revision bump of the engine (106 commits ahead at the review of 29 October 2026) breaks six
anchors, including helpers shared with Neo Geo and CPS-1, and waits for the decision about Mega-CD. See the "Deferred"
list of [UPSTREAMS.md](UPSTREAMS.md).

## In the project

Paths only; the reasons are in [ARCHITECTURE.md](ARCHITECTURE.md) and [STANDARDS.md](STANDARDS.md).

| Area | Files |
|---|---|
| Profile | `retrorecomp/systems/console16.py` (`MegaDriveProfile`: extensions, CPUs, path shapes, stamp groups `megadrive_codegen`, `megadrive_z80`, `md_prefetch`, `guns16`) |
| Identification and header | `retrorecomp/cartridge16.py` (SEGA header, region, linear reader), `retrorecomp/megadrive.py` (profile per ROM, preflight, vectors, learned entries), `retrorecomp/megadrive_hardware.py` (Sega bank mapper and EEPROM board tables) |
| Code generation | `retrorecomp/megadrive_codegen.py` (68000 instruction translation), `retrorecomp/megadrive_z80.py` (Z80 translation), `retrorecomp/megadrive_z80_timing.py` |
| Engine adaptations | `megadrive_runtime.py`, `megadrive_bus.py`, `megadrive_dma.py`, `megadrive_fifo.py`, `megadrive_read.py`, `megadrive_video.py`, `megadrive_audio.py`, `megadrive_memory.py`, `megadrive_cart.py`, `megadrive_sram.py` (all under `retrorecomp/`) |
| 16-bit family (shared with Super Nintendo) | `retrorecomp/console16.py`, `console16_optimization.py`, `console16_state.py`, `guns16.py`, `gun16_runtime.py`; `retrorecomp/m68000.py` is shared with Neo Geo, CPS-1 and X68000 |
| Native runtime | `native/md_backend.c`, `md_step_dispatch.c`, `md_native_steps.h`, `md_bus_scheduler.h`, `md_timing.h` (scheduler and clocks); `md_prefetch.h/.inc`, `md_exception_decode.h` (68000); `md_vdp_dma`, `md_vdp_fifo`, `md_vdp_read`, `md_vdp_pixels` (VDP); `md_z80_bus.inc`, `md_z80_native.h`, `md_z80_runtime.c` (Z80); `md_audio_*`, `md_ym_timers.h` (sound); `md_cart.h/.inc`, `md_battery.c/.h`, `md_eeprom.h` (cartridge); `md_portable_state.inc` (states). Shared with Super Nintendo: `native/console16_*.c/.h`, `native/gun16.c/.h` |
| Host kit adapter | `native/hostkit/adapters/rrhk_md.c` (actions, six-button pad, help lines, gun page, own audio device, timing report) |
| Self-tests (no ROM) | `tools/megadrive_native_selftest.py`, `_cycles_`, `_bus_`, `_dma_`, `_fifo_`, `_read_`, `_video_`, `_raster_`, `_timing_`, `_boundary_`, `_vdp_batch_`, `_interrupt_`, `_irq_collision_`, `_exception_`, `_prefetch_`, `_prefetch_plan_`, `_z80_`, `_z80_resume_`, `_eeprom_`, `_eeprom_state_`, `_mapper_`, `_sram_`, `_save_`, `_audio_bridge_`; `tools/m68000_backend_selftest.py`, `tools/console16_state_selftest.py`, `tools/gun16_selftest.py` (each `megadrive_*_selftest.py` links the matching `native/md_*_checks.c`) |
| Cartridge-driven checks | `tools/megadrive_progression_selftest.py` and `tools/megadrive_audio_selftest.py` (on an already generated executable, with the player's own ROM) |
| Unit tests | `tests/test_megadrive*.py`, `tests/test_console16*.py`, `tests/test_guns16.py`, `tests/test_m68000_shifts.py`; fixtures `tests/fixtures/md-prefetch`, `md-exceptions`, `m68k-shifts` |

## Controls and options

The shared menus (F1 help, F2 settings, F3 filter, F4 display, F6 autofire, F7 language, F8/F9 states) are described in
[CONTROLS.md](CONTROLS.md); only what is specific to this machine is here.

| Action | Keyboard (player 1) | Controller |
|---|---|---|
| Directions | Arrow keys | D-pad |
| A / B / C | W / X / C | A / B / X |
| Start | Enter (also pauses the game itself) | Start |
| X / Y / Z (six-button games) | A / S / D | Y / left shoulder / right shoulder |
| Mode (six-button games) | Right Shift (either Shift works) | Back |

Player two uses the numeric keypad. Letter defaults and F2 labels follow the active keyboard layout (AZERTY included);
a saved custom mapping keeps its physical key positions. Two controller ports are wired; whether a game offers two
players is the game's own choice. F2 lists the controls the console actually has: three buttons and Start, or six
buttons, Mode and Start.

- **Gun games**: the mouse is the gun on port 2, the standard pad stays on port 1. Left click fires (Menacer A /
  trigger), right click is B, middle click is C, Enter is Start. The gun page of F2 (after the control pages) sets cross or
  dot, size 1-12 and red, white or green. F5 is free on Mega Drive gun games. See [GUNS_16BIT.md](GUNS_16BIT.md).
- **Display**: the picture is 256 or 320 wide and 224 or 240 high (448/480 rows in interlace mode 2, kept whole with the
  right aspect); the window opens for 320 x 240. The scanline filter works on the displayed height and leaves the guest
  image untouched. Only presentation changes; game pixels and timing are not touched.
- **Sound**: the engine opens its own audio device; volume, mute, audio filter and output device are host-kit options
  ([HOST_KIT.md](HOST_KIT.md), [AUDIO.md](AUDIO.md)).
- **Scan level** (Options tab of the console, or `--scan-level quick|standard|extended|thorough`; `--md-advanced-scan`
  means thorough): how many routes and frames the conversion explores, up to 24,000 attract frames and two
  pseudo-random routes at the thorough level. The shared description is in
  [CONSOLES_16BIT.md](CONSOLES_16BIT.md#scan-levels); the Mega Drive routes (six-button actions, the T2 menu
  selection, the early-start and menu replays) are in the [log](MEGADRIVE_LOG.md#mega-drive-scan-routes). A longer
  scan raises coverage and conversion time; it does not make the hardware exact.

## States and saves

**Quick states** (F8 save, F9 load): one slot per game in `datas/states/<game-slug>-<rom-sha12>.rrstate`, a Windows
x64 runtime snapshot, not a format shared with other tools. The header checks the full ROM SHA-256, console, NTSC/PAL,
the build's state key, a bounded size and an integrity hash. The key hashes the native files this console owns
([`stamp_inputs.py`](../retrorecomp/stamp_inputs.py)), the layout version (`MD_PORTABLE_STATE_ABI`, currently 11) and the
pinned revisions; a state of another cartridge, mode or build is refused, except the one of the previous release (the
rule is in [GAME_STATES.md](GAME_STATES.md#the-rule-the-previous-release-only)). The state holds the 68000 and Z80
state, the scheduler, RAM, VDP including its FIFO and DMA, FM and PSG chip state, controller latches, YM timer phases,
the gun protocol, the two-word prefetch queue, the cartridge RAM with its lanes and overlay register, the bank-page
registers, the serial EEPROM phase with its staged page and remaining write time, and the sound CPU's latest machine-cycle
ends that date BUSACK (since 1.6.5). Host fibers and pointers are never
written: loading rebuilds the instruction fiber at the stored guest PC, and a save waits for the instruction in flight
to retire. Details and every release's key: [GAME_STATES.md](GAME_STATES.md#mega-drive-and-super-nintendo).

**Cartridge saves**: battery RAM and EEPROM bytes live in `datas/saves/<game-slug>-<rom-sha12>.rrsram`, a small
container that checks the full ROM SHA-256, geometry, payload length and an integrity hash. It holds only cartridge
memory (an 8 KiB save is 8,304 bytes), is independent of the state layout, and survives a rebuilt game. Reading creates
nothing; writes are atomic, after the memory settled or on exit; volatile RAM creates no folder; an unsupported or
damaged file is preserved. F1 keeps the RAM and restores the boot latches; a successful rewind with F9 also updates the
battery file. Conversion probes use blank cartridge memory and never read or write the player's saves.

**Compatibility across releases**: only the previous release is supported (N-1). Layouts of ABI 2 to 11 were migrated
in turn; the older signatures are no longer recognised ([UPGRADES.md](UPGRADES.md), [GAME_STATES.md](GAME_STATES.md)).

## Qualification

Gates and their numbering: [QUALIFICATION.md](QUALIFICATION.md) and [STANDARDS.md](STANDARDS.md#supported-checklist).
The matrix of 27 October 2026 gives Mega Drive: met for scope (G1), native coverage (G3), CPU fidelity against the
fresh reference (G4), packed replay (G5), fresh-process states (G6), saves (G7), route depth (G9), panel (G12),
owner acceptance (G14) and shared-knowledge safety (G16); partial for the report contract (G2), liveness (G8),
independent CPU evidence (G10), independent hardware evidence (G11), the cross-OS witness (G13) and honesty (G15).
Read the caveats there before quoting a letter. The panel is 24 + 8 cartridges.

| Measure | What stands behind it |
|---|---|
| Native code | Zero interpreted 68000 and Z80 instructions on the final tested routes of the qualified cartridges (demo, play, a 6,000-frame varied-input replay, early-start and menu replays, a 24,000-frame attract scan at the thorough level). A scenario that is not tested may still use the fallback. |
| CPU fidelity | Native and reference agree on registers, memory, VDP, FM/PSG samples and Z80 state before anything is learned; authored fixtures (thousands of instruction/state comparisons) and independent vectors: 864 exception cases and 2,089 prefetch/transaction cases from SingleStepTests/m68000 plus 55 authored timing cases, the Z80 vectors, the shift vectors. The vectors come from MAME, not from silicon. |
| Hardware fidelity | Independent fixtures for the VDP FIFO, DMA, read prefetch, counters, the EEPROM wire model, the bank mapper and the interrupt collision. Not claimed: board electrical timing, refresh, exact interlace fields. |
| Gameplay validation | Sampled routes and the owner's play tests, not complete playthroughs. |
| Physical latency | Not measured. |

**Reference and risk cases** (`tools/campaign-risk-cases.json`): Sonic The Hedgehog 2 (interlaced split screen, Z80
timing), Ecco the Dolphin (68000 code in RAM through a `TRAP #0` stub), NBA Jam - Tournament Edition (Acclaim serial
EEPROM), Super Street Fighter II (5 MiB, Sega 512 KiB bank mapper), Gunstar Heroes (heavy Z80 driver, Japan region
lock; zero Z80 fallback is part of its documented result). The gun cartridges are the Menacer 6-Game Cartridge and
T2 - The Arcade Game, tested on NTSC only.

**Shared knowledge**: the converter embeds a ROM-free snapshot of verified hints per exact ROM (the file
`assets/compilation-knowledge.json.gz` holds 227 Mega Drive records, counted on 29 October 2026). Hints never bypass
the native/reference comparison and are bound to the full SHA-256 and the engine revision; see
[COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md) and [COMPATIBILITY.md](COMPATIBILITY.md). These are regression
observations, not a compatibility score of the catalogue.

## Known limits

- **Hardware**: 68000 address and bus errors, electrical interrupt acknowledge (VPA/E-clock), BR/BG/BGACK phases,
  refresh and blanking slots, VDP port collisions and physical interlace field timing are not qualified. The shift clocks
  follow the manual (the independent vectors cover `ROXL`, `ROXR` and `ASL.L`, see [CPU_68000.md](CPU_68000.md)).
  Supervisor `RESET` only takes its clocks (the cartridge-port reset pulse is not modelled); unknown decoder patterns and later-CPU operations remain explicit limitations.
- **Sound**: no complete YM2612 fidelity is claimed (BUSY and timer-driven CSM are missing); the checks inspect digital
  samples, not loudspeakers or listening quality.
- **Cartridges**: SVP, 32X, Pico, lock-on and unrelated licensed or unlicensed mappers are refused; serial EEPROM boards
  beyond the three families convert with a save limitation; Mega-CD is a separate machine decision
  ([NEW_MACHINE.md](NEW_MACHINE.md)), with per-disc recipes and strict native execution that would break our counted
  fallback rule. Special cases and region headers: the [log](MEGADRIVE_LOG.md#earlier-regression-examples).
- **Fallback**: interpreter fallback is a counted limit, never hidden: work-RAM code not yet observed, changed Z80
  opcodes and prefix chains beyond the four-byte guard window can still use it. At most 4 uploaded 8 KiB Z80 driver
  images and 32,768 Z80 variants are stored per ROM in the converter's library; generated games write no learning files.
- **Guns**: Justifier has no gameplay-validated cartridge; Menacer horizontal conversion is an estimate by scanline;
  PAL gun cartridges are not covered by the NTSC tests.
- **Validation**: full playthroughs, the full catalogue, electrical pin precision and physical latency are not claimed.
  Zero fallback on the tested scenarios does not establish complete gameplay or original-hardware fidelity.

## History

The dated sections of the former 16-bit page (release 0.25.0 qualification, compiler and runtime evidence, the
cartridge-save design, regression examples, native 68000 and Z80 coverage, sound scheduling, work-RAM tail
instructions, the Z80 AOT) are kept in [MEGADRIVE_LOG.md](MEGADRIVE_LOG.md). The stages of the timing and
cartridge-circuit work have their own deep dives: [CPU exceptions](MEGADRIVE_CPU_EXCEPTIONS.md),
[EEPROM](MEGADRIVE_EEPROM.md), [mappers](MEGADRIVE_MAPPERS.md), [prefetch](MEGADRIVE_PREFETCH.md),
[video](MEGADRIVE_VIDEO.md), [Z80 timing](MEGADRIVE_Z80_TIMING.md), [lightguns](GUNS_16BIT.md). The family page
[CONSOLES_16BIT.md](CONSOLES_16BIT.md) keeps what the Mega Drive and the Super Nintendo share.
