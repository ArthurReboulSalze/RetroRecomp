# Master System

Status: **supported** (Windows and Linux x64 games from your own `.sms` cartridges). One Z80, one scanline VDP model, the
engine and most of the code are shared with the [Game Gear](GAME_GEAR.md). Passing the project's own checks does not
establish hardware fidelity, complete gameplay or physical latency.

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
| Profile | `sms` (`retrorecomp/systems/master_system.py`), the stable id of the oldest profile |
| Input | `.sms`, a ZIP holding exactly one cartridge, and `.bin` / `.rom` dumps whose header says Master System. 8 KiB to 4 MiB, a multiple of 8 KiB; a 512-byte copier header is removed. The original file is read, never modified |
| Console recognition | The `TMR SEGA` header (at `$7FF0`, `$3FF0` or `$1FF0`) tells the two Sega consoles apart by its region nibble (3 or 4 Master System, 5 to 7 Game Gear) and beats a misleading extension, also inside ZIPs. A headerless file keeps its extension |
| Written to | `Export/Games/Master System`, one executable per game with the ROM embedded; reports under `datas/reports` |
| Firmware | None. No BIOS is read or needed |
| Video timing | `ntsc` (262 lines, about 3.580 MHz) or `pal` (313 lines, about 3.547 MHz), chosen per ROM (see below) |
| Players | Two pads; a Light Phaser on port 1 for the games of an explicit catalogue |
| Library | The compilation library of the Master System sits directly in `datas/library` (the other consoles have a subfolder) |
| Linux | The same sources build a Linux x86-64 game ([LINUX.md](LINUX.md)); `tools/linux_sms_selftest.py` is the bounded native check |

**Video standard.** The cartridge header region says Japan or export, not 50 or 60 Hz, so it is never used for timing. A
filename labelled Europe alone proposes PAL; anything else proposes NTSC. Each ROM can be set to Auto, PAL or NTSC in the
converter list, on the command line (`--video-standard`) or in a profile (`[video] standard`). The choice is stored by ROM
SHA-256 and survives a new engine revision. See [SYSTEM_PROFILES.md](SYSTEM_PROFILES.md) and [VIDEO.md](VIDEO.md).

**Scan levels.** Standard runs the "demo" and "play" scripted routes; Extended adds one reproducible pseudo-random route of
18,000 frames, Thorough two (same rule as the other consoles, `retrorecomp/scan_levels.py`). Routes press host pad input only
and are compared with the reference CPU before anything is learned.

## Structure of the machine

| Part | Handled by | How Retro-Recomp handles it |
|---|---|---|
| **Z80**, about 3.58 MHz NTSC / 3.55 MHz PAL (main and only CPU) | [CPU_Z80.md](CPU_Z80.md) | **Native code**: every ROM position of every bank is translated to C at conversion (banked engine). **Reference machine**: a separate Z80 interpreter (`superzazu/z80`, MIT, corrected locally) that runs the same game in lockstep during conversion and is compared register by register. **Counted interpreter**: that same interpreter executes the instructions native code cannot know (unseen RAM code), counted in cycles |
| **ROM and mapper** | Sega mapper, three 16 KiB bank slots (`g_bank[0..2]`, banks seen are tracked) | Bank numbers are part of every translated entry; calls and jumps check the bank in place. Other mappers (Codemasters) and cartridge RAM saves are **not validated** |
| **RAM** 8 KiB | runtime | Code run from RAM is matched by a table of exact byte encodings, re-read at each visit (byte guards); an unseen variant goes to the counted fallback, its four bytes are observed and the next conversion generates a native body for it |
| **VDP** (Mode 4, 192 lines) | `native/video_mode4.inc`, original code | Scanline renderer: palette, scroll and display controls are taken at each line; eight sprites per line with zoom, wrap, priority, collision and overflow flags; left-column blanking; H-INT and V-INT (V-INT from line 193) at their counters. Pixel-clock effects are not modelled. Both CPU paths share this model |
| **PSG** (SN76489, stereo ports are Game Gear only) | `native/psg_runs.inc`, `psg_state.inc` | Synthesised from guest CPU cycles; the host output (`native/audio_output.inc`) is a separate stage with a 256-tap sinc converter to the device rate |
| **FM sound unit** (Japanese consoles) | none | Not emulated, not validated |
| **Pause button / NMI** | host | The pause of the player (keyboard or pad) suspends execution and audio in the host. A real Pause/NMI interrupt is not implemented |
| **Pads** | adapter | Two controllers, two buttons each; the Master System has no Start button on its pad |
| **Light Phaser** | `native/lightphaser.c`, [LIGHT_PHASER.md](LIGHT_PHASER.md) | Virtual gun on port 1 driven by the mouse; sensor timing taken on the cycle; chosen from a cartridge catalogue, never by scanning the Z80 code |

### The two engines

Both engines read the same ROM and share the VDP, PSG, memory and input runtime. They differ in how Z80 code becomes C.

- **Banked (default, `banked-aot-v3`).** The converter walks every instruction position of every ROM bank, including bytes
  that are used as data, and writes a C body for each, specialised for its bytes, constants and offsets (identical encodings
  share one body). The game picks the precompiled body for the current PC and the three mapped banks; there is no decoder and
  no JIT at run time. The Z80 PC and stack stay explicit, so CALL, RET, computed jumps and a bank change in the middle of a
  routine never use the C stack as a stand-in for the console stack. Redundant DD/FD prefixes, EI delay, HALT and interrupt
  acceptance follow the reference CPU. Details and checks are in the local maintainer notes `NATIVE_COVERAGE.md` (in French).
- **Functions (optional).** The pinned upstream generator finds functions by a static walk and emits one C function per
  routine, with direct calls between them, plus our patches (below). It is the older, smaller output. It has no quick states
  and ignores the hints other players imported (its function entries are matched by address, so a hint from the wrong bank
  could replace real code outside the tested routes). Since 1.6.4 it must also pass the same reference gate as the banked
  engine: a divergence fails the conversion and the previous export stays.

In the converter, the checkbox **Extended native coverage - Sega profiles** (options page of the Master System and the Game
Gear, on by default) selects the banked engine; unchecked selects functions. On the command line `--backend banked` is the
default. Functions still fails the reference check on Action Fighter, Alex Kidd: High-Tech World, Alex Kidd: The Lost
Stars, Super Columns, Sonic Spinball and Sonic Triple Trouble (1.6.4 work); the banked engine converts them. Alex Kidd in
Miracle World and Factory Panic now convert with functions; 9 of 15 games tried pass its reference check.

## Engine and upstream

Pinned repositories, recorded in [UPSTREAMS.md](UPSTREAMS.md) and `retrorecomp/upstreams.py`:

| Repository | Pin | Role here | Licence |
|---|---|---|---|
| [mstan/smsggrecomp](https://github.com/mstan/smsggrecomp) | `224d5bb` (`core.ENGINE_REV`) | Z80 recompiler and runner (the "functions" generator, the glue, the VDP, PSG and reference CPU we rebuild from) | No licence declared; noncommercial permission reported by the project owner |
| [mstan/z80-recomp-core](https://github.com/mstan/z80-recomp-core) | `0e6606a` (submodule) | Shared Z80 headers and sources, also used by the Mega Drive | PolyForm Noncommercial 1.0.0 |
| [SingleStepTests/z80](https://github.com/SingleStepTests/z80) | `ebe1875` | Independent Z80 vectors, development tests only, fetched on demand | MIT |

Review of 29 October 2026: smsggrecomp is one commit ahead of the pin (its change, direct calls to paged addresses, is
already our own patch since 1.6.3) and the shared core is identical to `main`; both pins were kept. The pinned checkout is
never edited: our changes are applied to the staged copy.

Our patches on that copy (all CPU-fidelity changes; the pin does not move):

| Patch | Release | Where | Affects |
|---|---|---|---|
| No direct C call to an address at or above `$0400`: the call goes through the dispatch that checks the mapped bank | 1.6.3 | `core.patched_generator_source` | functions engine only |
| HALT: the interrupt that ends it pushes the address after the HALT, and a handler that drops the halted frame ends the function | 1.6.4 | `core.patched_generator_source` | functions engine only |
| Interrupt acceptance: /INT sampled at one instruction boundary and accepted at the next; a VDP port access that changes /INT brings the next sync to the next instruction; a `RET` that unwinds every generated frame continues at the popped address | 1.6.4 | `core.prepare_functions_irq` on the pinned `runner/glue.c` | functions engine only |
| Local copies of the reference CPU and the shared headers: WZ and Q latches, SCF/CCF X/Y flags, `BIT (HL)` without write-back, IM/RETI aliases, OTDR timing, IM0 IRQ, H-counter reads at CPU time | 0.10.0 and later | `retrorecomp/cpu.py` (`prepare_cpu_headers`, `prepare_reference`) | both engines |
| Mode-4 scanline renderer in place of the end-of-frame snapshot | 0.10.9 | `native/video_mode4.inc` (via `prepare_runtime`) | both engines, new conversions |

The banked engine generates the same sources before and after the 1.6.3 and 1.6.4 functions patches (checked on Bank
Panic). Release effects on existing exports are in [UPGRADES.md](UPGRADES.md#master-system-and-game-gear-the-functions-engine-164-lot-f).
How the Z80 is recompiled, the path shape and the CPU tests are described in [CPU_Z80.md](CPU_Z80.md); this page does
not repeat them.

## In the project

| Area | Files |
|---|---|
| Profile | `retrorecomp/systems/master_system.py` (identity, header detection `sega_profile`, PAL/NTSC default, `convert_checked`), shared with `systems/game_gear.py` |
| Converter | `retrorecomp/core.py`: `read_rom`, `convert`, `prepare_runtime`, `patched_generator_source`, `prepare_reference_irq`, `prepare_functions_irq`, `probe`, `default_config`, `ENGINE_REV`. The SDL pin, toolchain and dependency helpers in the same file belong to every console. `retrorecomp/cpu.py` (CPU corrections), `retrorecomp/validation.py`, `profiles/example.sms.toml` (an example profile), `assets/profiles/` (a known-game profile) |
| Paths | `PathSpec` of the profile: section `z80/sms`, shapes `sega5` (a ROM entry: PC, three bank numbers and a checksum; up to 65,536) and `window4` (four-byte RAM patterns; up to 4,096 per ROM), through `retrorecomp/path_profiles.py` |
| Native, engine side | `native/banked_runtime.inc`, `banked_emitter.inc`, `banked_dispatch.c`, `banked_vectors.c`, `banked_cpu_checks.c`, `gamestate.inc`/`.h`, `video_mode4.inc`, `video_frame.h`, `psg_runs.inc`, `psg_state.inc`, `lightphaser.c`/`.h`, `sms_sprite_probe.c`, `audio_output.inc` |
| Host kit adapter | `native/hostkit/adapters/rrhk_sms.c`, one adapter for both Sega consoles (`RETRO_GAME_GEAR` builds the Game Gear). It keeps: the action table, the French legacy preference keys, the guest-driven pad refresh, the Light Phaser mapping, the sprite-flicker option (F5), the Pause menu text, the picture crop and placement rule, and the quick-state requests ([HOST_KIT.md](HOST_KIT.md#phase-4-the-master-system-and-the-game-gear-163)) |
| Self-tests (no commercial ROM) | `tools/banked_selftest.py` (authored ROMs: paging, cross-bank instructions, returns), `banked_cpu_selftest.py` (native bodies against the reference on ROM positions), `banked_vector_selftest.py` (independent Z80 vectors through the production emitter), `fetch_z80_vectors.py`, `gamestate_selftest.py`, `lightphaser_selftest.py`, `frame_stop_selftest.py`, `video_selftest.py`, `native/video_checks.c`, `native/frame_stop_checks.c`, `linux_sms_selftest.py` |
| Tools with a game | `tools/banked_verify.py` (strict native/reference audit of existing exports to 18,000 frames), `sms_sprite_selftest.py` |
| Unit tests | `tests/test_game_gear.py` (both consoles' ROM reading, ZIP and header cases, icons, the generator patches), `tests/test_sega_functions_gate.py` (the reference gate of the functions engine) |

## Controls and options

Defaults (full tables and the shared shortcuts are in [CONTROLS.md](CONTROLS.md)):

| Player | Directions | Buttons | Menu |
|---|---|---|---|
| 1, keyboard | Arrows | W / X | Enter (the console's Pause button is on the console, not on the pad) |
| 2, keyboard | Keypad 5 / 2 / 1 / 3 | Keypad 8 / 9 | Keypad 7 |
| Each gamepad | D-pad / left stick | A / B | Start / Menu |

- **F2** pages: player 1 keyboard and gamepad, player 2 keyboard and gamepad, then the options; a **Light Phaser** page sits
  after the control pages. Each gamepad page ends with a *Gamepad* row (Automatic, a connected controller, or None). Shift+F1
  or the held restart combination restarts; the second player has no gun of its own.
- **F5, sprite flicker reduction** (Master System and, since 1.6.5, Game Gear). Off by default, which keeps the console's eight sprites per line. When
  on, sprites beyond the eighth are drawn and confirmed rapid sprite-list reversals are stabilised (at least 75 % of sprite
  identities matching, 95 % of pairwise priorities agreeing, two reversals within four frames). Collision and overflow flags
  still use the original eight. It changes presentation only, no ROM patch, no frame blending, and can change which character is
  in front; it cannot restore sprites a game leaves out. Saved in `[MasterSystem.Video] reduce_sprite_flicker`. Details and
  the Double Dragon observation: [VIDEO.md](VIDEO.md).
- **Light Phaser.** Mouse aims, left click shoots, right click shoots off-screen; the cursor is hidden over the picture. The
  reticle (cross or dot, size 1 to 5, red, white or green) is an F2 page and an overlay only: it never changes shot
  coordinates or the framebuffer. A red target tag is added to the icon of games that support the gun. See
  [LIGHT_PHASER.md](LIGHT_PHASER.md).
- **Display.** Whole-pixel scaling, centred; F3 cycles Sharp pixels, Scale2x, Scanlines and xBR smooth; F4 the display mode.
  When a game blanks the left 8 columns the view crops them but keeps the scale of the full picture so the image does not
  jump (`game_rect` in the adapter). The picture is 256 × 192.
- **Audio.** Stereo ring with 256-tap sinc conversion to the device rate; volume, mute and device choice are the host kit's.
  See [AUDIO.md](AUDIO.md).
- **Preferences.** `datas/Retro-Recomp.ini` under `[MasterSystem.*]`; the French sections of releases before 1.6.3 and
  `SMSRecomp.ini` are still read where the new key is absent and never deleted.

## States and saves

- **Quick state**: F8 saves one slot, F9 loads it; the request waits for a safe banked-instruction boundary. The file holds
  the ROM SHA-256, the state schema and the hardware model (machine id 1 NTSC, 2 PAL, 3 Game Gear) and resumes from the saved
  guest PC and stack. Only the banked engine supports states. Presentation preferences and sprite-flicker history are not part
  of the state. See [GAME_STATES.md](GAME_STATES.md).
- **Across releases**: the Master System has no state key of the kind the 16-bit consoles have. A state of an export of 1.6.2
  loads in an export of 1.6.3 and the reverse, and the 1.6.4 changes add no field to a state. Not run across every release.
- **Cartridge saves** (battery RAM): not validated on this profile (gate G7 is not applicable in the status matrix).

## Qualification

Status from [QUALIFICATION.md](QUALIFICATION.md) (matrix of 27 October 2026; `Y` met, `P` partial, `?` unknown, `-` not applicable):

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 | G11 | G12 | G13 | G14 | G15 | G16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P | P | Y | Y | P | ? | - | ? | P | Y | P | Y | P | ? | P | Y |

G6 (fresh-process states) and G8 (liveness) are unknown and G14 has no recorded owner decision. Panel size: 258 cartridges.

The five measures, kept apart:

| Measure | Evidence |
|---|---|
| Native code | Both final scenarios at zero fallback on the tested routes for the 258 qualified cartridges; the fallback is always counted per CPU and shown in the window title and the report |
| CPU fidelity | 51,328 independent Z80 vector cases (1,604 families, MIT corpus generated by JSMoo, not console captures) pass for the native bodies and the corrected reference CPU; 524,192 positions of Bubble Bobble's banks compared with all registers; the conversion compares CPU, RAM, VDP traces, per-frame pixel hashes and the final picture with the reference, and refuses the export on a difference |
| Hardware fidelity | Not independently verified: the VDP, PSG and memory model is shared by the native and the reference path, authored chip fixtures check the numeric rules |
| Gameplay validation | Scripted routes (demo, play, optional pseudo-random) only; no full playthrough, no physical two-player session |
| Physical latency | Not measured; no result claims zero latency |

Campaigns: the 9 October 2026 campaign qualified 256 distinct cartridges plus two gun editions (258), with up to six passes
and 7,200 frames per route, strict execution and eight conversions at a time. Five early games (Alex Kidd in Miracle World,
Bomber Raid, Bubble Bobble, Buggy Run, Galaxy Force) passed ten 18,000-frame routes at zero fallback in 0.10.0. The shared
knowledge holds 258 exact Master System identities and 101 verified ROM entry hints (about 12 KiB compressed; the 2,970 RAM
variants without a verified ROM source stay local, because embedding their bytes would break the ROM-free format).

Reference games and risk cases (`tools/campaign-risk-cases.json`): Alex Kidd in Miracle World (regression baseline),
Operation Wolf (Light Phaser), Phantasy Star (cartridge save), Galaxy Force (regression baseline). The 1.6.4 release candidate
uses Bank Panic (Europe). Factory Panic and OutRun belong to the compilation library.

## Known limits

- Codemasters mapper, cartridge saves, FM sound and a hardware Pause/NMI are neither validated nor supported.
- The video model works on scanlines, not VDP pixel clocks: mid-line palette changes are quantised to a line; CRAM dots,
  VRAM-access contention while drawing, SMS1 zoom quirks, other display modes and full PAL hardware fidelity are not
  validated. A region label is a default timing choice, not proof of the console a cartridge was played on.
- RAM code beyond what the converter has seen still runs in the counted interpreter; up to 4,096 RAM windows are learned per
  ROM. Zero fallback is a result on tested routes, never a general promise. A strict conversion refuses any fallback.
- The functions engine fails the reference check on the six games listed above; do not treat it as supported for them. Their causes
  (a `RET` to another address, block-instruction flags while repeating, an interrupt accepted at another instruction boundary) are in
  [UPSTREAMS.md](UPSTREAMS.md#fixes-carried-as-our-own-patches-in-164). Sonic Spinball passes on the Master System and fails on the Game Gear.
- Sprite flicker reduction is a display enhancement, not console behaviour.
- The stereo audio ring of the Master System and Game Gear is the one duplicate of the host kit's ring still left; merging
  needs its own measurement ([HOST_KIT.md](HOST_KIT.md)).
- Not run: a Light Phaser game through the kit adapter on a real display, a PAL Game Gear, a Master System game that blanks
  the left column with the kit's placement, physical controllers and latency.

## History

| Release | What changed for the Master System |
|---|---|
| 0.10.0 | Banked engine `banked-aot-v3` becomes the default; native prefixes, WZ/Q, 51,328 vector cases |
| 0.10.6 / 0.10.8 | Light Phaser; automatic icon tag |
| 0.10.9 / 0.10.10 | Scanline mode-4 renderer; frame limits and host stops wait for the end of a CPU step |
| 0.10.12 / 0.10.15 | F8/F9 quick states; PAL scanline, clock and V-counter timing |
| 9 Oct 2026 | Campaign of 258 cartridges |
| 1.6.3 | Player shell moves to the host kit (phase 4); "functions" engine no longer calls paged addresses directly; Master System game stamp moves, existing exports are upgraded ([UPGRADES.md](UPGRADES.md#master-system-and-game-gear-exports-in-163-host-kit-phase-4)) |
| 1.6.4 | "Functions" engine: HALT, interrupt acceptance and top-level return fixed; Alex Kidd in Miracle World and Factory Panic convert with it |

The fuller dated records stay in [COMPATIBILITY.md](COMPATIBILITY.md), [COMPILATION_LIBRARY.md](COMPILATION_LIBRARY.md) and
[RELEASE_NOTES.md](RELEASE_NOTES.md).
