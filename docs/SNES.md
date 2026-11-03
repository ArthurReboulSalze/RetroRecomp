# Super Nintendo

**Status: supported within the standard-cartridge profile.** Ordinary LoROM and HiROM cartridges up to 4 MiB, PAL and
NTSC, two pads, Super Scope, cartridge saves and F8/F9 quick states. Boards with a DSP-1, a CX4, a Super FX (GSU), an
SA-1 or an S-DD1 are supported too (SA-1 and S-DD1 since 1.6.6); the CX4, the GSU and the SA-1 stay counted interpreted
devices, apart from the native 65816 and SPC700 code. Other enhancement circuits and extended mappings are refused with a
clear message. The dated evidence behind this
page is in [SNES_LOG.md](SNES_LOG.md).

Contents: [At a glance](#at-a-glance) · [Structure of the machine](#structure-of-the-machine) ·
[Engine and upstream](#engine-and-upstream) · [In the project](#in-the-project) ·
[Controls and options](#controls-and-options) · [States and saves](#states-and-saves) ·
[Qualification](#qualification) · [Known limits](#known-limits) · [History](#history)

## At a glance

| | |
|---|---|
| Status | Supported (standard profile, DSP-1, CX4, Super FX since 1.5.4). Compatibility is per cartridge and per tested route, not a catalogue guarantee |
| Files accepted | `.sfc`, `.smc`, `.fig` (the Pro Fighter copier: always a 512-byte header before whole 32 KiB blocks, any other size is refused), identifiable `.bin`/`.rom`, and a ZIP holding one cartridge. A 512-byte copier header is removed from the in-memory build input only; the ROM on disk is never changed. An image stored in a copier's interleaved order (its HiROM header at the LoROM position) is refused with its own message; the four `.fig` dumps of the maintainer's library are plain (checked at both header positions) and convert |
| Board scope | LoROM or HiROM, up to 4 MiB (8 MiB for the S-DD1 boards; FastROM, RAM and battery variants included). A LoROM header whose mode byte is `$32` (the ExLoROM value of the S-DD1 boards) but whose chip type says no circuit (0, 1 or 2) is an ordinary LoROM cartridge and is accepted (Duel: Test Drive II, 1 MiB, converted on 29 October 2026 with zero interpreted 65816 and SPC700 opcodes after one learning pass). ExHiROM, larger images and unlisted circuits are refused before any build |
| Region | PAL or NTSC from the header's region byte (0, 1, 13, 15 and 16 mean NTSC, anything else PAL), never from the file name; a stated standard that disagrees with the cartridge is refused |
| Where games are written | `Games/Super Nintendo`, beside the converter (the profile's export folder) |
| Firmware needed | None. The DSP-1 and CX4 models are firmware-free; no firmware file is read or shipped |
| How a new cartridge is handled | Analysed from its own ROM. There is no allowlist: a catalogue entry (eleven exact ROMs in `supernintendo.PROFILES`) only supplies optional settings, and compilation knowledge is bound to the full SHA-256 and the engine revision |
| Interpreter fallback | Always counted and shown: the window title reports it, H explains it, the report keeps it per CPU and per device |

Refused with an explicit message: SPC7110, DSP-2/3/4 and other custom circuitry (`snes_chips.identify`), SA-1 headers other
than map `$23` with type `$34` or `$35`, S-DD1 headers other than map `$32` with type `$43` or `$45`, extended mappings and
images above 4 MiB (8 MiB for the S-DD1 boards: `supernintendo.validate_cartridge`), ordinary cartridge RAM above 128 KiB, and DSP-1
firmware-dump commands.

## Structure of the machine

| Part | What it is here | How Retro-Recomp handles it |
|---|---|---|
| Main CPU | 65816, bus cycles of 6, 8 or 12 master clocks | Native: one compiled operation for every ROM byte, plus guarded operations for RAM code; live operands. Counted interpreter for the rest. See [CPU_65816_SPC700.md](CPU_65816_SPC700.md) |
| Sound CPU | SPC700 on its own 1,025,280 Hz oscillator | Native: PC-directed operations over the uploaded sound programs, guarded by the live opcode. Counted interpreter for unknown code. See [CPU_65816_SPC700.md](CPU_65816_SPC700.md) |
| Sound DSP | S-DSP, 32,040 samples per second, mixed to the host's 48 kHz queue | Hardware model of the pinned engine (not recompiled). Its state is in quick states; the output goes to the host kit's audio queue |
| Video | PPU 1 and PPU 2: modes 0-7, 224 or 239 lines, hires modes 5/6 and pseudo-hires, interlace, OBJ evaluation and fetch, window and colour math | Hardware model of the pinned engine, with our adaptations: PAL/NTSC geometry, persistent OBJ cursor, PPU port collisions, both hires dots and both interlace fields, register journal replay. Rendered by the host kit |
| DMA and HDMA | Eight channels, HDMA from line 0 | Run on the guest bus timeline (byte-level arbitration, refresh holds, parked-CPU handling). The renderer replays recorded PPU writes and never charges that replay as CPU time |
| Memory | 128 KiB work RAM; cartridge ROM (mirrored like the loader's power-of-two storage); cartridge RAM, battery or volatile (ordinary boards up to 128 KiB; Super FX Game Pak RAM from the extended header, 64 KiB by default) | Decoded by one checked cartridge decoder shared by the CPU fast path and the bus; holes return the CPU data latch (open bus) |
| DSP-1 | Maths coprocessor on LoROM or HiROM boards (HiROM: map `$31`, cartridge type `$05` with battery RAM or `$03` without; the DSP-1 window is `$00-$1F:$6000-$7FFF`) | Firmware-free command model (alias decode, camera and raster projection); each command is counted. Commands that dump firmware stop validation. Timing is command modelling, not electrical timing |
| SA-1 | Second 65816 at 10.74 MHz (one SA-1 cycle per two master clocks) with 2 KiB of I-RAM, BW-RAM (8-64 KiB here, the battery for type `$35`), the Super MMC, a timer, DMA and character conversion, multiply/divide, and a mailbox and IRQ in both directions with the S-CPU | The SA-1 core of the pinned engine (the `interp816` 65816 core with its own bus), a counted interpreted device on its own `cartridge_device` line, like the GSU. The S-CPU reaches it at the clock of its own bus cycle (see below). BW-RAM is the battery file and is part of quick states |
| S-DD1 | Decompression chip on the DMA path (map `$32`, types `$43` and `$45`; Street Fighter Alpha 2 is the reference board) | The decompression engine of the pinned engine (public domain, [licence notice](../licenses/snesrecomp.md)); it is not a processor: the report counts the DMA sessions it ran and the bytes it was asked for (`sdd1_dma_sessions`, `sdd1_dma_bytes`) |
| CX4 | HG51B-based coprocessor (Mega Man X2 is the reference board) | Existing instruction core with synthesised constants. Its instructions stay interpreted and are counted on their own device line |
| Super FX (GSU) | MARIO chip, GSU-1 and GSU-2 boards, map `$20`, types `$13`-`$15` and `$1A` | Instruction-level core of the pinned engine, a counted interpreted device. Static recompilation of GSU code is not done: see [SNES_SUPERFX.md](SNES_SUPERFX.md) |
| Controllers | Two pads (auto-read and manual `$4016` strobe), Super Scope on port 2 | Host kit adapter. Super Scope: [GUNS_16BIT.md](GUNS_16BIT.md). The Justifier uses another serial protocol and is catalogued only |

### What is native, what is counted

Three counters are kept apart and never summed. The 65816 figure counts interpreted **opcodes** of the main CPU only. The
SPC700 figure is cycle-based. Each cartridge device (GSU, CX4, SA-1, DSP-1, S-DD1) has its own line, `cartridge_device` in the report,
with interpreted instructions per scenario and per frame; a GSU runs tens of millions of them per scenario and would
swamp both CPU percentages if it were added to them. A native 65816 or SPC700 path therefore cannot hide interpreted
device work, and no zero-total-fallback claim is made for CX4 or Super FX games.

**RAM code nobody has seen (release 1.6.7).** An instruction fetched from RAM (WRAM or the cartridge's RAM for the 65816, the sound
unit's 64 KiB for the SPC700) whose address and opcode no scan has seen executing used to go to the counted interpreter. It now
runs through the compiled body of the opcode it has at that moment, read on the fetch, so code that changes keeps working: the
256 bodies are the interpreter's own (same text, same cycle table), operands and the M/X widths stay live reads on the timed
bus. The three classes are counted apart and add up to the instructions retired by each CPU; the flat report keys keep
`native_entries` and `audio_native_opcodes` as the total of compiled bodies (the comparison against the reference sums them with the
interpreted ones), and say how many of them were unobserved:

| Class | 65816 | SPC700 | Meaning |
|---|---|---|---|
| native | `native_entries` minus `compiled_unobserved_opcodes` | `audio_native_opcodes` minus `audio_compiled_unobserved_opcodes` | ROM, or RAM at an address and opcode a scan has seen executing |
| `compiled_unobserved` | `compiled_unobserved_opcodes` | `audio_compiled_unobserved_opcodes` (and `_cycles`) | RAM compiled by its live opcode at an address no scan has seen |
| interpreted | `interpreted_opcodes` | `audio_interpreted_opcodes` | no compiled body: device registers (MMIO fetch), changed ROM bytes, device instructions |

The observation goes on: each unobserved instruction is recorded as an interpreted one was, so the second learning pass still
turns it into a native one and the conversion keeps both passes. What changes is that a path no scan has visited no longer falls
to the slow interpreter, and that no report can any longer hide that class: it has its own number. The SA-1 has no such
counter (its program is the cartridge device's, counted on its own line). The fixtures: for the 65816, every one of the 256
operations in 32 register modes run from WRAM and from the cartridge's RAM at a position no table holds, native against the
internal reference (state, cycles and bus order equal; 65,890 comparisons in all, both mappings), plus the cases that must stay
interpreted (device registers, a changed ROM byte); for the SPC700, 65,536 more differential cases (131,396 in all). It says
nothing about fidelity beyond what the interpreter has: the bodies are shared, not independent.

Code that stays on the counted path: ROM bytes changed at run time, instruction fetches from volatile I/O (MMIO), and device
instructions. A RAM instruction is checked against its fetched opcode on the timed bus fetch (done once, never from a stale
preview). At most 16,384 variants are kept per cartridge as observations; since 1.6.7 the cap limits what is recorded, not
what runs natively. The discovery runs only in the converter: a generated game never writes learning files.

## Engine and upstream

The pinned engine is [RetroPortingToolKit/snesrecomp](https://github.com/RetroPortingToolKit/snesrecomp) at `a00df26`
(`console16.REPOSITORIES['snes']`), downloaded into `.deps` on the first conversion. Its terms are PolyForm Noncommercial
1.0.0 plus MIT, ISC and other vendor licences ([licenses/snesrecomp.md](../licenses/snesrecomp.md)); Retro-Recomp's MIT
licence does not replace them. We use its 65816 interpreter (LakeSnes lineage), its SPC700/DSP core, its Super FX core
(adapted upstream from the ISC-licensed ares) and `runner/`; we do not use its analyser. The pinned checkout is never
edited: every adaptation is applied to a staged copy in the cartridge's private build folder, and an adaptation
fails closed (`replace`, `replace_once`) if the pinned text changed.

The adaptations (PAL and NTSC timing, bus phases, DMA/HDMA, PPU ports, display, cartridge decoding, the three chips) are the
`snes_*.py` modules listed below. What UPSTREAMS.md records as our own patch, together with the pin review (about 200 commits
ahead, deferred items, planned revision bump), is [UPSTREAMS.md](UPSTREAMS.md). The CPU patch is the one of 1.6.3: in native mode `BRK` takes 8 cycles
(7 in emulation mode) and `COP` follows the mode (no bank pushed in emulation mode, 7 cycles, vector `$FFF4`), in
`snes_codegen.py` (`correct_software_interrupts`). There is no SNES patch in 1.6.4.

**No per-game code (1.6.6).** The pinned bridge (`interp_bridge.c`) carries one shortcut written for a single cartridge: a
byte-verified fast-forward of the `LDA $D9 / BEQ` wait loop at `$C0:84B2` of Super Mario RPG (battle, vertical timer 216), on
unless the environment variable `SNESRECOMP_NO_D9FF` is set. Retro-Recomp ships no code for one title, so the adapter
(`snes_codegen.adapt_bridge`) turns the switch off in every build, whatever the environment says, and fails closed if the pinned
text moves; a test pins both (`tests/test_snes.py`). Cost: the loop is executed instruction by instruction in a battle, which
the SA-1 numbers of [SNES_LOG.md](SNES_LOG.md) and [UPGRADES.md](UPGRADES.md) state.

## In the project

| Where | What |
|---|---|
| `retrorecomp/supernintendo.py` | Exact-ROM catalogue, cartridge validation, activity and device-liveness gates, RAM-variant library (`datas/library/snes/<rom-sha256>/native-ram.json`) |
| `retrorecomp/snes_codegen.py` | 65816 operation map for every ROM byte, RAM guards, BRK/COP correction |
| `retrorecomp/snes_spc.py`, `snes_knowledge.py` | SPC700 PC-directed code and its compressed, bounded exact-ROM opcode map (`spc-native.json`) |
| `retrorecomp/snes_cart.py`, `snes_chips.py`, `snes_gsu.py` | Cartridge RAM layout and decoder; DSP-1, CX4 and Super FX integration and device reporting; GSU decoder and traversal (groundwork only, not used by a conversion) |
| `retrorecomp/snes_timing.py`, `snes_bus.py`, `snes_dma.py`, `snes_ppu_bus.py`, `snes_video.py` | PAL/NTSC timing, timed CPU byte phases and refresh, DMA/HDMA ownership, PPU port collisions, display geometry |
| `retrorecomp/snes_routes.py` | Authored host-input routes (seven routes for six exact Super FX cartridges), replayed from the Extended level |
| `retrorecomp/systems/console16.py` | `SnesProfile`: id `snes`, stamp group `guns16`, devices `superfx`, `dsp1`, `cx4`, quick-state family `rr16`, `.sfc`/`.smc`, path sections `w65c816` and `spc700` |
| `native/snes_backend.c`, `snes_bus.*`, `snes_cart.h`, `snes_dma.h`, `snes_hdma.inc`, `snes_ppu_bus.inc`, `snes_ppu_cache.inc`, `snes_timing.h` | Runtime: bus, cartridge, DMA/HDMA, PPU port and tile-row cache, timing |
| `native/snes_native_steps.h`, `snes_spc_native.h`, `snes_spc_runtime.c`, `snes_battery.*`, `snes_dsp1_*` | Native step dispatch, SPC700 native and runtime, battery file, DSP-1 projection and vectors |
| `native/hostkit/adapters/rrhk_snes.c` | The Super Nintendo adapter of the host kit ([HOST_KIT.md](HOST_KIT.md)) |
| `native/console16_*.c`, `gun16.*` | Shared with the Mega Drive (state, main, video, gun); Neo Geo and CPS-1 hosts compile `console16_state.c` |
| `tools/snes_*_selftest.py` | Native, bus, cart, chip, DMA, HDMA, object, PPU bus and cache, RAM, scheduler, SPC700, timing, video and Super FX self-tests (the C checks are `native/snes_*_checks.c`, `native/snes_cpu/interrupt_checks.c`) |
| `tools/snes_packed_check.py`, `snes_gsu_survey.py`, `snes_superfx_*.py` | Packed-export replay, GSU survey, Super FX model, programs, library and mutations |
| `tests/test_snes*.py` | Unit tests that need no ROM: bus, cart, chips, gates, GSU, knowledge, SPC700, Super FX, timing, video |

Every one of these files has its role and owners in `retrorecomp/stamp_inputs.py`; editing a SNES game file moves the SNES
game stamp and can move the quick-state key ([GAME_STATES.md](GAME_STATES.md)).

### Converting and the scan levels

A conversion builds the cartridge, runs the exports headless under host-input scenarios and compares the native path with
the fully interpreted reference path (CPU registers, memory, visible frames, PCM, clocks, device state) before it teaches
the library anything; a mismatch keeps the previous export. The Super Nintendo uses the shared four scan levels of the
Options tab (`--scan-level quick|standard|extended|thorough`; `--md-advanced-scan` still means thorough):

| Level | Passes and scenarios (defaults: 3 passes, 1,200 frames per test) |
|---|---|
| Quick | One pass, attract (demo) and play, scenario length capped |
| Standard | Demo and play, up to the pass limit, stopping when no new path is found |
| Extended | Standard plus a 12,000-frame attract, one pseudo-random play route of 18,000 frames (seeded by console and exact ROM) and, for a cartridge that has one, its authored route |
| Thorough | 24,000-frame attract and two pseudo-random routes of 18,000 frames, plus the authored route |

A route is ordinary host controller input; nothing in guest memory or code is patched. Authored routes exist only for
Star Fox, Star Fox 2, Stunt Race FX (one-player and two-player), Yoshi's Island, Vortex and Dirt Racer, whose random
route never leaves the menus. Gun games keep their own mouse routes. The report records the level, each scenario's budget,
the fallback counters and each reference comparison. On PAL cartridges, long runs must also report complete display geometry and picture and PCM activity
(`validate_activity`), and a device cartridge whose picture, device and sound all stopped is refused
(`validate_device_liveness`).

Hints from players (F12 fallback recording, [RUNTIME_FEEDBACK.md](RUNTIME_FEEDBACK.md)) arrive as kinds 8 (65816 RAM code)
and 9 (SPC700 opcodes). The qualified knowledge snapshot embedded in the converter is described in
[COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md); it holds numbers about exact ROMs, never ROM bytes, firmware or game assets.

## Controls and options

Shared keys (F1 help, F2 pages, F3 filters, F4 window modes, F6 autofire, F7 menu language, F8/F9 states, Tab fast-forward)
are in [CONTROLS.md](CONTROLS.md). Enter, the cartridge Start, pauses the game itself; P stays free.

| SNES button | Player 1 keyboard | Player 2 keypad | Controller |
|---|---|---|---|
| A / B | W / X | 8 / 9 | A / B |
| X / Y | A / S | 0 / . | X / Y |
| L / R | Q / E | / and * | Shoulders |
| Select / Start | Shift (either) / Enter | 4 / 7 | Back / Start |
| Directions | Arrows | 5 up, 2 down, 1 left, 3 right | D-pad |

Letter defaults and F2 labels follow the active keyboard layout (AZERTY included); saved custom mappings keep their physical
key positions. Player 2 has no reset shortcut. F2 shows twelve actions per player. Autofire is F6.

Super Scope games add the gun page of F2: mouse aim, left button fires, right button is Cursor, middle button or Enter is the
Scope Pause; cross or dot, size 1-12, red/white/green, and a **Scope Turbo** row (on by default, the gun's physical turbo
switch). The settings live in the `SNES.Gun` section of the shared preferences, controls in `SNES`. Details and limits:
[GUNS_16BIT.md](GUNS_16BIT.md).

Display: ordinary output is 256 pixels wide, hires modes 5/6 and pseudo-hires 512; active height is 224 or 239 lines,
448 or 478 texture rows in interlace. Pixel density is accounted for at presentation, so hires does not double the aspect;
fullscreen fitting, filters and mouse coordinates use the logical image. Audio and pacing: [AUDIO.md](AUDIO.md#super-nintendo).
Linux builds optimise the SNES hardware helpers: [LINUX.md](LINUX.md#runtime-performance-work).

Conversion options: the console tab of **Options** sets the scan level, passes and frames per test (see above).

## States and saves

- **Quick states (F8/F9):** one slot in `datas/states/<game-slug>-<rom-sha12>.rrstate`, family `rr16` shared with the Mega
  Drive. The header binds the full ROM SHA-256, console, PAL/NTSC, build signature and an integrity hash; other
  cartridges, standards or builds are rejected. The state holds the CPU residue and beam-driver resume point, APU and PAL
  clock fractions, memory, PPU (including the OBJ cursor, VRAM/CGRAM/OAM latches and field parity), DSP, cartridge and device
  state, and the Super Scope latches. Older incompatible signatures are refused untouched. The build signature hashes the
  files listed for the console and the bytecode fingerprints of the `snes_*` modules; it moves when a SNES game file
  changes. The per-release table and the previous-release rule are in [GAME_STATES.md](GAME_STATES.md).
- **Cartridge saves:** battery RAM (LoROM/HiROM RAM, and Super FX types `$15` and `$1A`) is kept separately from quick states
  in `datas/saves/<game-slug>-<rom-sha12>.rrsram`, bound to the full ROM SHA-256, RAM size and mapping with a payload
  integrity hash. Reading creates no folder; writes are debounced, go through a temporary file and an atomic replacement,
  and are flushed on a normal exit. A corrupt or foreign file never stops the game (since 1.6.7): it is set aside, byte for byte, as `<name>.rrsram.unusable-N` (the first free N from 1 to 99), the game starts with a blank RAM, and a short notice says so in the five game languages; if it cannot be moved it is left untouched and nothing is saved that session (also told). Before 1.6.7 such a file was kept in place and the game ran without saving. Volatile
  cartridge RAM is not persisted. F8/F9 also capture cartridge RAM, so loading an older state restores older progress,
  which is then saved on exit. A conversion probe uses blank RAM and reads a player's save only from an explicit private `--cartridge-save` path.
- **Compatibility across releases:** only the previous release's quick states keep loading
  ([GAME_STATES.md](GAME_STATES.md)); battery files survive any runtime change that keeps the same ROM and layout.

## Qualification

Gates and the matrix: [QUALIFICATION.md](QUALIFICATION.md). The Super Nintendo column (matrix of 27 October 2026, G5 and G8 of
1 November 2026) reads: met for the report contract, native coverage, CPU fidelity run, delivered file, fresh-process states, panel
and shared-knowledge safety (G2-G6, G12, G16; G5 and G6 are campaign steps, not run inside every conversion, see the caveats
there); partial for scope and status wording, saves, liveness (a record exists for the cartridges with a coprocessor only),
route depth, independent CPU and hardware evidence, cross-OS witness and honesty (G1, G7-G11, G13, G15); unknown for owner
acceptance (G14: no decision recorded). The SA-1 and S-DD1 boards of 1.6.6 were proved on four titles and an authored cartridge
(section above), which is panel breadth for G12 and nothing more: they do not close any partial gate.

**Saves on every board (release 1.6.7).** `tools/snes_saves_check.py` converts one cartridge written for the purpose per board
(LoROM 8 KiB and 128 KiB with a battery, LoROM and HiROM with RAM and no battery, HiROM 32 KiB, Super FX, S-DD1 and the HiROM DSP-1
with a battery; the SA-1 has its own in `snes_sa1_selftest.py`) and checks, for each: the save file is written with its board
code, size and whole RAM (the first and the last byte of the RAM included); a second process reads it back; a board without a
battery writes nothing and starts blank; ten kinds of damaged file (a payload byte, the cartridge identity, the board code, the
size, the version, the magic, a byte missing or added, an empty file) are set aside byte for byte as `.unusable-N` while the game starts
blank and saves a new file, and a file that cannot be set aside is left untouched; the valid file loads again afterwards; no temporary file is left; native equals the interpreted reference; the quick states
restore in a fresh process. It proves the adapter and the file format on those boards, not a commercial cartridge's own
save (Stunt Race FX and Yoshi's Island were not played to a save).

The five measures, kept apart:

| Measure | What exists | What is not claimed |
|---|---|---|
| Native code | Zero interpreted 65816 and SPC700 opcodes on the final qualified routes; device instructions counted apart | Zero fallback for every untested path; any native GSU or CX4 code |
| CPU fidelity | Native against the fully interpreted reference on every scenario of every conversion; authored fixtures for all 256 65816 operations (65,890 state/bus comparisons) and 131,396 SPC700 differential cases | That the cores equal the chips: the independent vector set (SingleStepTests, 1.6.7) finds the differences listed in [CPU_65816_SPC700.md](CPU_65816_SPC700.md) (none in native-mode 65816 semantics, some in emulation mode and in the SPC700); the conversion's reference shares the engine's semantics |
| Hardware fidelity | Authored cartridges checked against independent Snes9x, bsnes and the ares contracts (PPU ports, OBJ progression, DMA/HDMA, DSP-1 maths, controller strobe) | Exact or electrical accuracy; sub-dot PPU phases; OAM collisions (the ares and bsnes models disagree and the gate stays open) |
| Gameplay validation | Bounded scripted routes with picture and PCM activity, packed replays and fresh-process states; hands-on confirmation of Super Scope input | Complete playthroughs; every level or mode; visual and listening review, which stays with the player |
| Physical latency | Not measured | Any figure |

Reference and risk cases ([`tools/campaign-risk-cases.json`](../tools/campaign-risk-cases.json)):

- Super Mario World (USA) is the game of the release check.
- Star Fox (Super FX, old header, default 64 KiB RAM) and Super Mario World 2 - Yoshi's Island (GSU-2, 2 MiB, battery RAM).
- Pilotwings (DSP-1): the camera and raster projection commands it exposed are now covered.
- Mega Man X2 (CX4): instructions stay interpreted and are reported on their own device line.
- Super Mario RPG (SA-1): the reference board of the SA-1 work (since 1.6.6); the other 14 SA-1 cartridges of the maintainer's
  library are recognised, three are proved (below).
- Street Fighter Alpha 2 (S-DD1): the reference board of the S-DD1; Star Ocean (6 MiB, both translations of the library) converts since 1.6.7.
- Super Scope 6 (CRC32 B141EA99) for the gun, NTSC only.

### Interpreter-fallback survey (29 October 2026)

A read-only survey of the 36 conversion reports of the maintainer's Super Nintendo exports (versions 0.21.0 to 1.6.4) and
one reconversion with the 1.6.4 tree found **no unexplained interpreted 65816 or SPC700 opcode**:

- 35 reports show 0 interpreted 65816 opcodes and 0 interpreted SPC700 opcodes on every final scenario. The 36th, Mega Man
  X2 (1.1.6), predates the separate device line: its 107,817,178 "interpreted" figure is the CX4 device, which a current
  conversion reports on its own `cartridge_device` line, with the 65816 at 0.
- Secret of Mana (USA), reconverted from an empty library at the Standard level, is the cartridge with the most
  cartridge-resident code (the game logic lives in WRAM from `$7E:8000`). Before learning, the demo ran 14,434,154
  interpreted 65816 opcodes and 4,646,680 interpreted SPC700 opcodes; after one learning pass (7,512 RAM variants at 7,308
  addresses, 69,796 SPC700 opcode variants) both scenarios ran at 0, and the native run equals the internal reference. The
  exported game, replayed on two pseudo-random routes of 6,000 frames that no scan level has run (indices 2 and 3), executed 0
  interpreted opcodes and added no RAM site. Scripted random input stays near the first screens, so this says nothing about
  unvisited game modes.
- So RAM-resident code is the only class that can reach the interpreter on an ordinary cartridge, and it does so by design:
  a RAM instruction was native only where a scan observed it; since 1.6.7 an unobserved one is compiled and counted apart
  (see "What is native, what is counted"). Nothing is hidden. Nothing here is a hardware-fidelity, gameplay or latency claim.
- Open, not fixed: the learned set is capped at 16,384 variants per cartridge, keyed by address and four bytes although the
  native table uses only address and opcode (Earthworm Jim: 81 variants at 2 addresses; Secret of Mana: 9,208 variants at
  8,725 address and opcode pairs in the maintainer's library). Past the cap, the highest addresses are dropped when the
  library is read, and the overflow counter is only in the scenario reports, not in the conversion log.

### HiROM DSP-1 boards without RAM (29 October 2026)

Seven cartridges of the maintainer's library carry map `$31` and cartridge type `$03` (a DSP-1, no RAM): Lock On, Super Air Diver 2,
Suzuka 8 Hours, Michael Andretti's IndyCar Challenge, Ballz 3D, Soukou Kihei Votoms and a translation of Ace o Nerae!. They were
refused as "custom circuitry" although the pinned engine already maps the HiROM DSP-1 (window `$00-$1F:$6000-$7FFF`, status
register at `$7000`, battery RAM at `$20-$3F:$6000-$7FFF` only when the board has RAM): the loader only took type `$05`
(Super Mario Kart and five other HiROM DSP-1 games). Type `$03` is now recognised on map `$31`; DSP-2 (`$20/$05`), DSP-4
(`$30/$03`) and the slow-ROM `$21` variants stay refused. Lock On converts with zero interpreted 65816 and SPC700 opcodes after one
learning pass; its standard scenarios send no command to the DSP-1, so the exported game was replayed on two 9,000-frame
pseudo-random routes (no scan level has run them): 109,558 and 60,081 DSP-1 commands, none failed, still zero interpreted
65816 and SPC700 opcodes. The device is counted apart (`command_model`); this is no hardware-fidelity, gameplay or latency claim,
and the six other cartridges were recognised but not converted here.

### SA-1 and S-DD1 (1 November 2026, release 1.6.6)

**SA-1.** The 15 SA-1 cartridges of the maintainer's library (map `$23`, type `$35` twelve times, `$34` three times; 1-4 MiB;
BW-RAM 8-64 KiB) were refused before; the pinned engine already carries the chip (`sa1.c`, ported from ares). Three are
proved, each converted at the Standard level from an empty library, then replayed (the exported game, not a conversion) on two
pseudo-random routes of 6,000 frames that no scan level has run. The SA-1 is a counted interpreted device: its instructions
are never in the 65816 percentage.

| Cartridge | Board | Interpreted 65816 / SPC700 after one learning pass | SA-1 instructions per frame (scan / long routes) | Picture and sound | Published file |
|---|---|---|---|---|---|
| Super Mario RPG (USA) | `$23/$35`, 4 MiB, 32 KiB BW-RAM with battery | 0 / 0, also on the long routes | 47.7 k, 55.5 k / 42 k | 1,056 and 1,020 visible frames, then 5,632 and 5,749; sound on | native equals reference, fresh-process quick state, 8 invalid files refused |
| Kirby Super Star (USA) | `$23/$35`, 4 MiB, 8 KiB with battery | 0 / 0, also on the long routes | 35.7 k, 34.3 k / 35 k | 1,032 and 1,011, then 5,627 and 5,565; sound on | same |
| Super Bomberman: Panic Bomber W (Japan) | `$23/$34`, 1 MiB, 8 KiB without battery | 0 / 0, also on the long routes | 147.6 k, 145.4 k / 155 k | 1,030 and 863, then 5,516 and 5,516; sound on | same |

Panic Bomber W runs three times the SA-1 instructions of the other two; no host time was measured for any of them. The
battery file of a real export is written by the first process and read back by the second (32,880 and 8,304 bytes for the
first two, bound to the SA-1 board, the BW-RAM is part of the quick state), a damaged file is set aside and the game starts blank.

What the work found and changed (all in the staged copy, none in the pinned checkout, see [UPSTREAMS.md](UPSTREAMS.md)):

- **The S-CPU reaches the SA-1 at the clock of its own bus cycle.** The pinned `cart_read` and `cart_write` synchronise the
  SA-1 to the clock of the end of the previous instruction. Measured on Super Mario RPG over 36.8 million accesses, the SA-1
  then stood behind the S-CPU by more than 32 master clocks at 3.3 % of them, by more than 8,192 at 17 of them (at most
  540,172): that is a statement about the old clock only. With the bus-cycle clock the SA-1 is run up to the clock of the
  access, a whole instruction at a time, so it can end up to one instruction past it. The report counts both sides, each at
  a different point: `sa1_behind_buckets` and `sa1_behind_max` are taken before each sync (how far behind the SA-1 was when
  the S-CPU came to it: the real granularity of the scheme), `sa1_synced_behind_max` after it (zero by construction, kept
  as a check that the sync ran) and `sa1_ahead_max` how far the last instruction ran past the target. The figures are
  measurements on one authored cartridge and on the played routes, not bounds: no worst case is claimed for another game. On the
  final tree, Super Bomberman - Panic Bomber W (Japan) reports a largest gap before a sync of 16,944 master clocks (the S-CPU
  had not touched the coprocessor for that long) and at most 22 clocks past the target after it.
- **The SA-1's IRQ request follows its flags.** The pinned core latched the request and never withdrew it: after a handler
  cleared its flag, the `RTI` took a second IRQ whose vector was read from the ROM (the S-CPU's), and the SA-1 never returned
  to its loop. Found by the authored cartridge below; it concerns every game that interrupts the SA-1 from the S-CPU.
- **The SA-1's NMI is an edge.** The pinned core re-armed its NMI before every instruction while the flag stayed set, so the
  handler never reached the instruction that clears it. On hardware the NMI is edge-triggered: it is now requested once, on the
  rise of the line (the 0 to 1 write of bit 4 of `$2200`). The authored cartridge has an S-CPU to SA-1 NMI case that failed
  before the fix (and a second edge that must run the handler again).
- **Two fast-forwards the pinned bridge carries for single cartridges are off in every build** (a Super Mario RPG wait loop and
  a vblank wait at fixed addresses of Star Ocean and Super Mario RPG): no per-game code. They did not engage in the routes
  above (the SA-1 counts are identical with and without). A battle of Super Mario RPG was not reached by any scripted route,
  so its cost was not measured; the work they skipped is native S-CPU instructions bounded by the clock (at most about 20,000
  per frame for a two-instruction loop), and the SA-1's count follows the master clock, not the S-CPU's.
- **The main CPU's hooks skip the SA-1's core** (it is the same `interp816` as the main CPU's): its instructions would
  otherwise have been counted as the main CPU's and looked up in the main CPU's ROM map.

An authored cartridge written for the purpose (`tools/snes_sa1_selftest.py`, NTSC and PAL) checks, against the processor
manuals and the register documentation rather than against the engine: a counter loop in I-RAM at one instruction per ten
master clocks (1,422,555 against 1,424,427 expected over 40 frames), a message and an IRQ from the S-CPU to the SA-1 and back
with the flags cleared and each handler run once, BW-RAM written by each CPU and read by the other, the coprocessor caught
up at every sync (behind by at most 48 master clocks when the S-CPU came to it, ahead by at most 12 and 14 after it in NTSC and PAL: measurements on this
cartridge, not bounds), native equal to the interpreted reference, the BW-RAM saved across two processes (a
damaged file or a file for another cartridge set aside, the game starting blank) and a quick state restored in a fresh process.

**S-DD1.** Street Fighter Alpha 2 (USA; map `$32`, type `$43`, 4 MiB, no RAM) is the reference board and converts with zero
interpreted 65816 and SPC700 opcodes. The scan runs 57 and 78 decompression DMA sessions (126,368 and 169,376 bytes); the long
routes run 825 and 1,498 (1,490,624 and 2,469,586 bytes); a frame of its attract mode (the score ranking, with the portraits)
shows clean decompressed graphics. The published file passes the same checks as above. The decompressor is the pinned engine's
(public domain, attribution in [the licence notice](../licenses/snesrecomp.md)); native and reference share it, so this finds
no decompression error of its own and the picture is the evidence.

**Not proved, not claimed.** Hardware fidelity of the SA-1 (bus contention between the two CPUs for ROM and BW-RAM, the exact
cycle placement) and of the S-DD1 (the chip's DMA timing); an independent comparison for either (upstream compared one
cartridge, Super Mario RPG, with another emulator for 600 frames); the 12 other SA-1 cartridges, converted by nobody here;
battles and long play; host time per frame. Star Ocean (6 MiB, the only S-DD1 cartridge above 4 MiB; 1.6.7): see the section below.

Evidence by topic: Super FX qualification, gates and costs in [SNES_SUPERFX.md](SNES_SUPERFX.md); the DSP-1/CX4 release
1.0.0 campaign, the live-RAM guards, bus, DMA/HDMA, PPU and cartridge-decoder work in [SNES_LOG.md](SNES_LOG.md).

**Star Ocean (1.6.7).** The S-DD1 cartridge of 6 MiB (map `$32`, type `$45`, 8 KiB of battery RAM) used to convert and stay on a black
screen. The cause was the decoding of the cartridge RAM: the clause the pinned engine uses for LoROM boards serves banks `$F0-$FF`,
addresses `$0000-$7FFF`, as battery RAM, and on an S-DD1 board those banks are the ROM windows of the chip (the board's RAM is in banks
`$70-$73`). A game's reads of its compressed data in `$F0-$FF` therefore returned save RAM. The S-DD1 board now has its own clause (banks
`$70-$73` only, `native/snes_cart.h` and `snes_cart.ram_offset`), and the S-DD1 boards may be up to 8 MiB. Both translations of the
library convert with zero interpreted 65816 and SPC700 opcodes on both routes, the compressed copy matches the reference, and a run of
2,500 frames shows the title menu (captures looked at by the specialist agent). The same conversion with the old clause ran 1
decompression session in those 2,500 frames and showed a black picture; with the narrow clause, 1,240 (an earlier attempt that sent the
CPU reads of `$C0-$FF` to `cart_read` gave the same 1,240, and was dropped once the clause alone was shown to be enough). Street Fighter
Alpha 2, converted again from an empty library with the before and after trees, gives the same hashes. Not claimed: play beyond the
title menu, the S-DD1's DMA timing.

## Known limits

- **Super FX GSU** stays a counted interpreted device. Static recompilation of GSU code (step 6b of
  [SNES_SUPERFX.md](SNES_SUPERFX.md)) is estimated at 25-35 working days and is not planned: the GSU is 7-27 % of host
  frame time. Open there: battery proof for Stunt Race FX and Yoshi's Island at game level, Doom 5- against 9-frame pacing,
  the Dirt Trax FX two-controller route, Stunt Race FX modes no authored route enters.
- **SA-1 and S-DD1** (1.6.6): three SA-1 cartridges and one S-DD1 cartridge are proved on bounded routes; the other
  eleven SA-1 cartridges of the library are only recognised; bus contention between the SA-1 and the S-CPU, cycle placement
  inside an SA-1 instruction and the S-DD1's DMA timing are not modelled or not qualified; no battle of Super Mario RPG was
  reached; the SA-1 interpreter's host cost is not measured (about 35-155 thousand instructions per frame on the three
  proved titles).
- **Not supported:** SPC7110, DSP-2/3/4, extended mappings (ExHiROM), images above 4 MiB (8 MiB for the S-DD1), DSP-1 firmware-dump commands.
  Recognition of a circuit is not product qualification.
- **PPU and bus timing:** instruction-internal and parked-CPU phases, DMA launch and release dividers, DMA/HDMA collision
  arbitration, active-display OAM/CGRAM fetch collisions, mid-line blanking and size changes during object fetch, uncommon
  offset, mosaic and colour-math combinations, and the first subscreen dot of hires modes (the ares description of it is
  itself unconfirmed on hardware) are refinement work, not claims.
- **DSP-1 and CX4 timing** is command modelling and a guarded instruction core, not electrical timing; no claim of complete
  HG51B instruction fidelity follows from the arithmetic cases.
- **Super Scope** is tested NTSC only, one cartridge; brightness sensitivity, infrared interference and CRT sensor delays are
  not simulated. The SNES Justifier is catalogued only.
- **Deferred performance work** (idle detector with hash buckets, APU advance by blocks) and the planned revision bump of
  the engine are in [UPSTREAMS.md](UPSTREAMS.md); they need a timing pass on a quiet machine.
- **Games and routes:** more cartridges and longer routes; scripted input leaves some modes unreached.

## History

Earlier stages in short (full text and counts in [SNES_LOG.md](SNES_LOG.md)):

- **0.20.0:** Super Scope on port 2.
- **Up to 1.0.0 (8 to 13 October 2026):** the 65816 operation map and SPC700 sound-program recompilation, PAL timing, the
  cartridge-RAM decoder with saves and guarded RAM code, hires, interlace and 239-line overscan, the APU frame clock, DMA/HDMA
  on the guest timeline, PPU port collisions, OBJ progression, the nested-IRQ fix.
- **1.0.0:** DSP-1 and CX4 qualified.
- **1.4.1:** every cartridge, Super Mario World included, uses the generic analysis (no Rust, no foreign function list).
- **1.5.4:** Super FX supported, the GSU a counted device.
- **1.6.0:** the host kit takes the player shell; the quick-state key moves.
- **Late October 2026:** the Stunt Race FX two-player route (27 October) and the manual `$4016` joypad strobe (Star Fox 2
  Japanese prototype), both in the Super FX work.
- **1.6.3:** the `BRK` and `COP` correction.
- **1.6.4:** no SNES patch; the quick-state key did not move.
- **1.6.5:** the cartridge is checked once at bind and WRAM code is found through a direct table (speed-ups, identical
  outputs); the HiROM DSP-1 board without RAM (map `$31`, type `$03`), the ordinary LoROM with mode byte `$32` and the Pro
  Fighter `.fig` dumps are accepted; the interpreter-fallback survey (no unexplained interpreted instruction).
- **1.6.6:** SA-1 boards (a second 65816, counted as a device) and S-DD1 boards up to 4 MiB; the S-CPU reaches the SA-1 at
  the clock of its own bus cycle; the SA-1's IRQ follows its flags; the pinned bridge's per-game fast-forwards are off.
