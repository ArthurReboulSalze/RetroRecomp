# Game Gear

Status: **supported** (Windows and Linux x64 games from your own `.gg` cartridges). The Game Gear shares its Z80 engine,
runtime and host adapter with the [Master System](MASTER_SYSTEM.md); this page records what is specific to the handheld.
The project's own checks do not establish hardware fidelity, complete gameplay or physical latency.

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
| Profile | `gg` (`retrorecomp/systems/game_gear.py`) |
| Input | `.gg` cartridges and ZIP files containing exactly one Game Gear cartridge. The original ROM is read without modification. The `TMR SEGA` header (region nibble 5, 6 or 7) beats a wrong extension, also inside ZIPs; a Master System header is refused |
| Written to | `Export/Games/Game Gear`, with a converter library (`library/gg`) and a save-state machine id (3) separate from the Master System |
| Firmware | None |
| Video timing | NTSC only (262 lines, about 3.58 MHz); a PAL choice is rejected |
| Players | One controller, with the cartridge Start input |
| Picture | Always the native **160 × 144 LCD window**, 12-bit CRAM colours, stereo port |

## Structure of the machine

| Part | Handled by | How Retro-Recomp handles it |
|---|---|---|
| **Z80**, about 3.58 MHz | [CPU_Z80.md](CPU_Z80.md) | Same as the Master System: native code (banked engine, or the optional "functions" engine), a reference interpreter in lockstep during conversion, and a counted interpreter fallback. See the [two engines](MASTER_SYSTEM.md#the-two-engines) |
| **ROM and mapper** | Sega mapper | Same mapper and path shapes as the Master System (`z80/sms` section, `sega5` and `window4`). Cartridge saves are not validated |
| **VDP** (Mode 4) | `native/video_mode4.inc` | The same scanline model, with 12-bit colour: CRAM holds two bytes per entry (64 bytes), each 4-bit channel is widened to 8 bits. The VDP works on a larger raster than the screen; the 160 × 144 window is cut from the 256 × 192 frame. The left-column blanking of the Master System is not applied |
| **PSG** with stereo port | `native/psg_runs.inc`, `audio_output.inc` | Port `$06` is the Game Gear stereo register (the PSG catches up to the guest clock before it is written); the host output is stereo |
| **Start button** | port `$00` | Read through the guest-driven pad refresh like the other ports |
| **Light Phaser** | none | Not on this console |
| **Sprite flicker reduction (F5)** | `native/hostkit/adapters/rrhk_sms.c` | Both Sega consoles since 1.6.5, off by default, saved in `[GameGear.Video] reduce_sprite_flicker`, F2 row, help line and pause page. Before 1.6.5 the option was never offered here: F5 answered "Config unavailable" (since 0.25.0, not a 1.6.3 regression) |

The wider internal raster is never revealed in this version, and games are not patched. That avoids incomplete graphics
at the borders and keeps the result faithful to the handheld's visible area. See the
[Game Gear VDP technical reference](https://www.smspower.org/Development/GGVDP) and
[Sega's hardware documentation](https://www.smspower.org/Development/GGOfficialDocs).

## Engine and upstream

The pins, licences and patches are the Master System's: `mstan/smsggrecomp` `224d5bb`, `mstan/z80-recomp-core` `0e6606a`
and the independent `SingleStepTests/z80` vectors, with the three patches of the "functions" engine (1.6.3 and 1.6.4).
See [MASTER_SYSTEM.md](MASTER_SYSTEM.md#engine-and-upstream) and [UPSTREAMS.md](UPSTREAMS.md). A change to shared Sega code
moves the game stamps of both consoles.

## In the project

| Area | Files |
|---|---|
| Profile | `retrorecomp/systems/game_gear.py` (identity, NTSC only, reading through `core.read_game_gear_rom`, conversion through `master_system.convert_checked`, with the header refinement `refine_by_header`) |
| Converter and native | Those of the Master System ([list](MASTER_SYSTEM.md#in-the-project)); the Game Gear branches live in `core.py` (`_read_rom`, the report `video_model` with `visible_pixels` 160 × 144, the Start step in the "play" route), `video_mode4.inc`, `gamestate.inc` (machine id) |
| Host kit adapter | `native/hostkit/adapters/rrhk_sms.c`, built with `RETRO_GAME_GEAR`: one player, a Pause/Menu row and a cartridge Start row, the 160 × 144 window cut inside the 256 × 192 frame |
| Tests | `tests/test_game_gear.py` (ZIP and header detection, icons, generator patches); the Master System self-tests of `tools/` cover the shared engine |

## Controls and options

| Input | Keyboard | Gamepad |
|---|---|---|
| Directions | Arrows | D-pad / left stick |
| Buttons 1 and 2 | W / X | A / B |
| Cartridge Start | Enter | Start |
| Pause / menu | P | Back |
| Help, restart | F1, Shift+F1 | held restart combination |

- **F2** maps the single player's keys and buttons (one gamepad row to pin a controller); there is no second-player or Light
  Phaser page. Game Gear bindings have their own `[GameGear.*]` sections of `datas/Retro-Recomp.ini`, so they do not overwrite
  the Master System's. Before 1.5.0 the cartridge Start was S and the menu Enter; a saved Pause/Menu binding is kept, and a
  saved Enter there wins over the cartridge Start.
- **Display.** The 160 × 144 picture, whole-pixel scaling, F3 filters, F4 display modes as on the other consoles
  ([CONTROLS.md](CONTROLS.md), [VIDEO.md](VIDEO.md)). Audio: [AUDIO.md](AUDIO.md).
- **F5** (sprite flicker reduction), new in 1.6.5 and off by default: it draws the sprites beyond the eighth of a line (the Game Gear
  VDP has the same limit) and stabilises confirmed rapid sprite-list reversals, exactly as on the
  [Master System](MASTER_SYSTEM.md#controls-and-options); collision and overflow flags keep using the original eight. It changes
  the presentation only, never the ROM. Exports of 1.6.4 and before answered "Config unavailable" and show no F2 row until rebuilt.

## States and saves

F8 saves one quick state and F9 loads it, with the banked engine only; the state file carries the ROM identity, the schema
and the Game Gear machine id, and a state whose console flag differs from the running game is refused. A state of an export of 1.6.2 loads in an
export of 1.6.3 and the reverse. Cartridge saves (battery RAM) are not validated. See [GAME_STATES.md](GAME_STATES.md).

## Qualification

Status from [QUALIFICATION.md](QUALIFICATION.md) (matrix of 27 October 2026):

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 | G11 | G12 | G13 | G14 | G15 | G16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P | P | Y | Y | Y | ? | - | ? | P | Y | P | P | P | ? | P | Y |

**The 18 October 2026 qualification, included in 1.1.3,** adds twelve exact cartridges: Sonic, Sonic 2, Tails Adventures, GG
Aleste, Gunstar Heroes, Dynamite Headdy, OutRun, Super Columns, Vampire / Master of Darkness, Wonder Boy: The Dragon's Trap,
Crystal Warriors and Streets of Rage II. Advanced conversions pass their strict CPU/VDP gates. Replaying both 3,600-frame
routes from every compressed export gives 86,400 native/reference frame pairs with matching CPU, RAM, VDP traces and final
images, with no fallback on these routes. Source archives are unchanged. Their numeric records extend the shared Game Gear
bank from one to thirteen exact revisions; they are not a cartridge allowlist.

Risk cases (`tools/campaign-risk-cases.json`): Sonic The Hedgehog 2, Gunstar Heroes, Phantasy Star Gaiden (cartridge save),
Streets of Rage II. The 1.6.4 release candidate uses Factory Panic (Europe); OutRun and Factory Panic are in the compilation
library.

The five measures, kept apart: **native code** (zero fallback on the routes above), **CPU fidelity** (agreement with the
reference CPU on those routes, and the Z80 vectors of the shared engine), **hardware fidelity** (not independently verified;
the VDP model is shared by both paths), **gameplay validation** (two scripted routes, the "play" route also presses Start) and
**physical latency** (not measured).

## Known limits

These targeted automated checks do not establish complete game compatibility or hardware fidelity. Native code coverage, CPU
agreement, hardware fidelity, gameplay and physical latency remain separate measures.

- Off-screen pixels of the VDP raster are not shown and games are not patched.
- The Codemasters mapper, cartridge saves and any PAL Game Gear timing are not validated.
- The scanline model, the unvalidated pixel-clock effects and the functions-engine limits are those of the
  [Master System](MASTER_SYSTEM.md#known-limits).

## History

| Release | Change |
|---|---|
| 1.1.3 (18 Oct 2026) | Twelve cartridges qualified; shared bank from one to thirteen exact revisions |
| 1.5.0 | Cartridge Start on Enter, menu on P |
| 1.6.3 | Host kit move (phase 4), see [UPGRADES.md](UPGRADES.md#master-system-and-game-gear-exports-in-163-host-kit-phase-4) |
| 1.6.4 | "Functions" engine fixes; Factory Panic converts with it |
| 1.6.5 (in preparation) | F5 sprite flicker reduction on the Game Gear, off by default |
